#!/usr/bin/env python3
"""
LOOK  -  render the panel at chosen moments and lay them out side by side.

    python3 tools/look.py out.png            # the standard six
    python3 tools/look.py out.png 420.9 660.5

The point of this is comparison. Every other tool in here answers a question
with a number, which is right for the ecology and useless for the only
question that finally matters: does a gyre look like a gyre next to a shelf.
Six panels on one sheet, captioned with where and when, is the cheapest form
of that question.

Each moment is reached by running the model from day zero, because the state
of the water is the sum of everything that has happened to it -- so this is
minutes, not seconds, and it is worth it.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import drift                              # noqa: E402
from voyage import Track                  # noqa: E402
from ocean import Ocean                   # noqa: E402

# (day, LOCAL hour, caption).
#
# Local, not UTC, and this is not pedantry. The model's day fraction is UTC,
# and the first version of this file asked for noon by writing day + 0.5 --
# which off Peru at 78 W is five in the morning. Every night panel came out
# in daylight and every day panel in the dark, and the bioluminescence looked
# broken when it was the captions that were wrong.
MOMENTS = (
    (185, 12, "PATAGONIAN SHELF  NOON"),
    (185, 0, "PATAGONIAN SHELF  MIDNIGHT"),
    (432, 12, "PERU / OMZ  NOON"),
    (432, 0, "PERU / OMZ  MIDNIGHT"),
    (620, 12, "N PACIFIC GYRE  NOON"),
    (620, 0, "N PACIFIC GYRE  MIDNIGHT"),
)


def at_local_hour(day, local_hour):
    """The panel's sun keeps the ROOM's hour (see SUN_CLOCK_ROOM in
    drift.py), and this tool pins the phase so that day fraction zero is
    local midnight. So a local hour is just a day fraction, with no
    longitude in it at all.

    It was not always so simple. The first version of this file wrote
    `day + 0.5` for noon, which under the old ship's-time clock is five in
    the morning off Peru: every night panel came out in daylight and the
    bioluminescence looked broken when it was the captions that were
    wrong."""
    return day + (local_hour % 24.0) / 24.0


def frames(moments, seed=7, voyage="drake", real_s=6.0, fps=20):
    """Run once, stopping at each moment in turn.

    At each stop the model is also run forward for a few REAL seconds at one
    to one, without advancing the ecology much, so that the swimming has
    settled and the bioluminescence has had time to happen. A frame taken the
    instant the ecology ticks has every animal on the depth the migration just
    put it on and nothing lit."""
    track = Track(voyage)
    try:
        ocean = Ocean("data/ocean.bin")
    except (IOError, OSError):
        ocean = None
    eco = drift.Ecosystem(seed=seed, track=track, ocean=ocean)
    # Pin the sun instead of taking it from the wall clock, or this tool
    # renders a different set of panels depending on what time you run it.
    eco.env.sync_sun_to_room(0.0, hour=0.0)
    out = []
    stops = sorted((at_local_hour(d, h), cap) for d, h, cap in moments)
    for day, caption in stops:
        while eco.t < day - 1e-9:
            eco.step(min(1.0 / 24.0, day - eco.t))
        for _ in range(int(real_s * fps)):
            eco.advance(1.0 / fps / 86400.0)
        c = drift.Canvas(drift.W, drift.H)
        drift.render(eco, c, track=track, day=eco.now)
        n = sum(1 for a in eco.agents if a.vis > 0.03)
        lit = sum(1 for a in eco.agents
                  if 0 <= eco.real_t - a.flash < drift.FLASH_S)
        mig = [a.z for a in eco.agents if a.g.kind in drift.MIGRATORS]
        zm = sum(mig) / len(mig) if mig else float("nan")
        out.append((c, "%s   n=%d  grazers at %.0fm  o2floor=%s  lit=%d"
                    % (caption, n, zm,
                       "-" if eco._o2_rule is None else "%.0fm" % eco._o2_rule,
                       lit)))
        print("  %-30s n=%2d  night=%.2f dvm=%.2f  grazers %4.1f m  o2=%s "
              " lit=%d"
              % (caption, n, eco._night, eco._dvm, zm,
                 "-" if eco._o2_rule is None else "%.0fm" % eco._o2_rule, lit))
    return out


def sheet(path, moments=MOMENTS, **kw):
    from PIL import Image, ImageDraw
    tiles = frames(moments, **kw)
    pad, cap = 14, 16
    w, h = drift.W, drift.H
    cols = min(3, len(tiles))
    rows = (len(tiles) + cols - 1) // cols
    img = Image.new("L", (cols * (w + pad) + pad,
                          rows * (h + pad + cap) + pad), 200)
    d = ImageDraw.Draw(img)
    for i, (c, label) in enumerate(tiles):
        x = pad + (i % cols) * (w + pad)
        y = pad + (i // cols) * (h + pad + cap)
        img.paste(drift.to_pil(c), (x, y))
        d.text((x, y + h + 3), label, fill=40)
    img.save(path)
    print("%s  %dx%d" % (path, img.width, img.height))


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/look.png"
    if len(sys.argv) > 2:
        ms = tuple((int(float(a)), 12, "DAY %s NOON" % a) for a in sys.argv[2:])
        sheet(out, ms)
    else:
        sheet(out)
