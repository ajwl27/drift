#!/usr/bin/env python3
"""
Every fish in the roster, drawn, as a contact sheet.

    python3 tools/plot_fish.py docs/roster.png
    python3 tools/plot_fish.py docs/gaits.png --gaits

The point is that a body plan cannot be reviewed by reading its parameters.
Sixteen Forms are sixteen sets of a dozen numbers, and whether one of them is
a fish or a mistake is not a question those numbers answer -- it is answered
by looking, at the size the panel draws them, in one bit.

`--gaits` renders one species across a full tail-beat cycle instead, which is
the only way to check that the wave travels backward and that the amplitude
envelope has no kink in it.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import math

import draw
import fish
from drift import Canvas, text, T_MED, to_pil


def sheet(path, cols=5, cell_w=190, cell_h=104, scale=3):
    keys = list(fish.ALL_KEYS)
    rows = (len(keys) + cols - 1) // cols
    c = Canvas(cols * cell_w, rows * cell_h + 16)

    text(c, 6, 4, "DRIFT ROSTER  %d SPECIES  DRAWN AT PANEL SCALE" % len(keys),
         scale=T_MED)

    for i, k in enumerate(keys):
        f = fish.BY_KEY[k]
        form = fish.FORM[k]
        cx = (i % cols) * cell_w + cell_w // 2
        cy = (i // cols) * cell_h + cell_h // 2 + 16
        # drawn at the size the panel would use, so this sheet shows the
        # real relative sizes and not a flattering uniform one
        L = fish.draw_length(f)
        draw.draw_fish(c, cx, cy - 6, L, 0.0, form, phase=0.9)
        text(c, cx - cell_w // 2 + 4, cy + cell_h // 2 - 20,
             f.common[:22], scale=1)
        text(c, cx - cell_w // 2 + 4, cy + cell_h // 2 - 13,
             "%s  %.0fPX" % (f.size_label, L), scale=1)
    to_pil(c).resize((c.w * scale, c.h * scale), 0).save(path)
    print("%s  %dx%d, %d species" % (path, c.w * scale, c.h * scale, len(keys)))


def gaits(path, scale=4):
    """One of each swimming mode, through a beat."""
    picks = [(fish.YELLOWFIN, "THUNNIFORM"), (fish.TREVALLY, "CARANGIFORM"),
             (fish.HERRING, "SUBCARANGIFORM"), (fish.VIPERFISH, "ANGUILLIFORM")]
    steps = 6
    cw, ch = 132, 62
    c = Canvas(steps * cw, len(picks) * ch + 14)
    text(c, 6, 3, "ONE BODY WAVE, FOUR PLACES TO START IT", scale=T_MED)
    for r, (k, name) in enumerate(picks):
        f = fish.BY_KEY[k]
        text(c, 4, r * ch + 16, name, scale=1)
        for s in range(steps):
            ph = 2.0 * math.pi * s / steps
            draw.draw_fish(c, s * cw + cw // 2, r * ch + ch // 2 + 18,
                           92.0, 0.0, fish.FORM[k], phase=ph)
    to_pil(c).resize((c.w * scale, c.h * scale), 0).save(path)
    print("%s  %dx%d" % (path, c.w * scale, c.h * scale))


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "docs/roster.png"
    if "--gaits" in sys.argv:
        gaits(out)
    else:
        sheet(out)
