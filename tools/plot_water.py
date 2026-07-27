#!/usr/bin/env python3
"""
The water screen at chosen points on the voyage, side by side.

    python3 tools/plot_water.py docs/water.png
    python3 tools/plot_water.py docs/dvm.png --dvm

The contact sheet the whole object is judged by. A panel of the Humboldt and
a panel of the South Pacific gyre next to each other is the piece's central
claim in one picture -- if those two do not look obviously different, nothing
else in the model matters.

`--dvm` holds one position and steps through a day instead, which is the only
way to see the scattering layer rise.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import drift
from drift import Canvas, W, H, View, render, to_pil, text, T_MED
from ocean import Ocean
from voyage import Track

STOPS = [
    (0, "PLYMOUTH"), (49, "CAPE VERDE"), (188, "PORT ST JULIAN"),
    (315, "CAPE HORN"), (357, "VALPARAISO"), (620, "PACIFIC GYRE"),
    (700, "MOLUCCAS"), (1000, "HOMEWARD"),
]


def sheet(path, voyage="drake", seed=3, scale=2):
    from PIL import Image
    track = Track(voyage)
    ocean = Ocean("data/ocean.bin")
    g = 8
    cols = len(STOPS)
    sheet = Image.new("L", (cols * (W + g) + g, H + 2 * g + 22), 245)
    for i, (day, name) in enumerate(STOPS):
        eco = drift.Ecosystem(seed=seed, start_day=float(day), track=track,
                              ocean=ocean)
        # let the population settle and the fish spread out before drawing
        eco.time_compression = 60.0
        for _ in range(240):
            eco.advance(3.5e-5)
        c = Canvas(W, H)
        render(eco, c, View(), track, eco.t)
        text(c, 6, 6, name, scale=T_MED)
        text(c, 6, 20, "%d FISH  %d TAXA" % (len(eco.agents),
                                             len(eco.census())), scale=1)
        sheet.paste(to_pil(c), (g + i * (W + g), g))
    sheet = sheet.resize((sheet.width * scale, sheet.height * scale), 0)
    sheet.save(path)
    print("%s  %dx%d" % (path, sheet.width, sheet.height))


def dvm(path, voyage="drake", day=49, seed=3, scale=2):
    """One place, through a day. The scattering layer is the point.

    STEPPED IN LOCAL SOLAR TIME, NOT UTC. The first version walked UTC hours
    at 168 W, where local noon falls at 2312 UTC -- so the panel labelled
    1200 was in fact an hour past local midnight, and the migration looked
    like noise instead of a cycle. The clock inside the model was right all
    along; the contact sheet was asking it the wrong question."""
    from PIL import Image
    track = Track(voyage)
    ocean = Ocean("data/ocean.bin")
    hours = (0, 3, 6, 9, 12, 15, 18, 21)
    lat, lon = track.position(day)
    g = 8
    sheet = Image.new("L", (len(hours) * (W + g) + g, H + 2 * g), 245)
    for i, hr in enumerate(hours):
        utc = (hr - lon / 15.0) % 24.0
        eco = drift.Ecosystem(seed=seed, start_day=day + utc / 24.0,
                              track=track, ocean=ocean)
        eco.time_compression = 60.0
        for _ in range(240):
            eco.advance(3.5e-5)
        c = Canvas(W, H)
        render(eco, c, View(plate=False), track, eco.t)
        text(c, 6, 6, "%02d00 LOCAL  SUN %+.0f" % (hr, eco.sun), scale=T_MED)
        sheet.paste(to_pil(c), (g + i * (W + g), g))
    sheet = sheet.resize((sheet.width * scale, sheet.height * scale), 0)
    sheet.save(path)
    print("%s  %dx%d" % (path, sheet.width, sheet.height))


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "docs/water.png"
    if "--dvm" in sys.argv:
        dvm(out)
    else:
        sheet(out)
