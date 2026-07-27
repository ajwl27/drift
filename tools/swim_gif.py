#!/usr/bin/env python3
"""
The same comparison as tools/tune.py, as an animated GIF.

    python3 tools/swim_gif.py swim docs/tune_swim.gif
    python3 tools/swim_gif.py fps  docs/tune_fps.gif

For judging away from the machine, and for arguing about later. Four panels,
same seed, same ecosystem state, differing only in the thing being tuned --
because comparing a single panel against your memory of how it looked a
minute ago is not a comparison.

The fps version is the interesting one: the GIF runs at a single rate and each
panel HOLDS its frame for the right number of ticks, which is exactly what a
slower refresh looks like on the panel. You are not being shown a description
of 8 fps, you are being shown 8 fps.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from drift import (Canvas, W, H, Ecosystem, View, render, to_pil,   # noqa: E402
                   SWIM_SCALE)
from voyage import Track                                            # noqa: E402
from ocean import Ocean                                             # noqa: E402

SWIM_VALUES = (0.07, 0.12, 0.22, 0.38)
FPS_VALUES = (5, 10, 20, 40)
BASE_FPS = 40                # the GIF's own rate
SECONDS = 5.0
START_DAY = 420.0
SC = 2
GAP = 8
LABEL_H = 20


def build(mode, dst, seed=5):
    from PIL import Image, ImageDraw
    track, ocean = Track("drake"), Ocean("data/ocean.bin")
    vals = SWIM_VALUES if mode == "swim" else FPS_VALUES
    n = len(vals)

    ecos = []
    for v in vals:
        e = Ecosystem(seed=seed, start_day=0.0, track=track, ocean=ocean)
        e.swim_scale = v if mode == "swim" else SWIM_SCALE
        e.time_compression = 60.0
        ecos.append(e)
    while ecos[0].t < START_DAY:
        for e in ecos:
            # a coarse step for the spin-up: this is a motion-tuning tool
            # and it only needs a plausible community to look at, not a
            # numerically careful one. Four ecosystems to day 420 takes 17
            # seconds this way and 64 at the simulation's usual step.
            e.step(1.0 / 6.0)

    view = View(plate=False, hud=False)
    cans = [Canvas(W, H) for _ in range(n)]
    tw = n * (W * SC + GAP) + GAP
    th = H * SC + GAP * 2 + LABEL_H
    frames = []
    nframes = int(BASE_FPS * SECONDS)
    dt = 1.0 / BASE_FPS
    for k in range(nframes):
        for i, e in enumerate(ecos):
            e.step(dt * 60.0 / 86400.0)
            hold = 1 if mode == "swim" else max(1, round(BASE_FPS / vals[i]))
            if k % hold == 0:
                render(e, cans[i], view)
        sheet = Image.new("L", (tw, th), 238)
        d = ImageDraw.Draw(sheet)
        for i in range(n):
            x = GAP + i * (W * SC + GAP)
            sheet.paste(to_pil(cans[i]).resize((W * SC, H * SC), 0), (x, GAP))
            lab = ("swim %.2f" % vals[i]) if mode == "swim" else ("%d fps" % vals[i])
            d.text((x + 2, GAP + H * SC + 4), "%d)  %s" % (i + 1, lab), fill=40)
        frames.append(sheet.convert("P", palette=Image.ADAPTIVE, colors=8))

    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    frames[0].save(dst, save_all=True, append_images=frames[1:],
                   duration=int(1000 / BASE_FPS), loop=0, optimize=True)
    print("%s  %d frames at %d fps, %.0f s, %.1f MB"
          % (dst, len(frames), BASE_FPS, SECONDS,
             os.path.getsize(dst) / 1e6))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "swim"
    dst = sys.argv[2] if len(sys.argv) > 2 else "docs/tune_%s.gif" % mode
    build(mode, dst)
