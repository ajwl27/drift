#!/usr/bin/env python3
"""
KEYPLATE  -  the third screen: what you are looking at, and where.

Every natural-history plate has a key. This is that key, and it does the one
thing neither the water nor the map can do: it tells a person who has just
walked into the room what the object is.

It lists only the organisms actually present, drawn at a comparable size and
sorted by abundance, so it is a census rather than a legend -- it changes as
the ship sails, and watching the list turn over between Callao and the
mid-Pacific is arguably the clearest statement the piece makes.

Canvas only. Ports with everything else.
"""

import math

from drift import (Canvas, W, H, text, text_width, DRAW, DRIFTER_KINDS,
                   HET_KINDS, EXTENT, Genome, COPEPOD, draw_copepod,
                   RADIOLARIAN, CENTRIC, PENNATE, CHAIN, CERATIUM, TINTINNID)
import random

NAMES = {
    RADIOLARIAN: "RADIOLARIA",
    CENTRIC: "COSCINODISCUS",
    PENNATE: "NAVICULA",
    CHAIN: "CHAETOCEROS",
    CERATIUM: "CERATIUM",
    COPEPOD: "CALANUS",
    TINTINNID: "TINTINNID",
}

# Second line under each name: what it does for a living. Three words, so a
# visitor gets the ecology without being lectured.
ROLES = {
    RADIOLARIAN: "MIXOTROPH  DRIFTS",
    CENTRIC: "DIATOM  SINKS",
    PENNATE: "DIATOM  GLIDES",
    CHAIN: "DIATOM  CHAINS",
    CERATIUM: "MIXOTROPH  SWIMS",
    COPEPOD: "GRAZER  MIGRATES",
    TINTINNID: "GRAZER  FILTERS",
}

ROW_H = 34
SPEC_X = 24          # centre of the specimen column
TEXT_X = 56

# Drawing radius per type for the key column, hand-set rather than derived.
# EXTENT is a separation radius and is deliberately isotropic, so it does not
# describe a Chaetoceros chain, which is compact across its axis and up to
# twelve radii long down it. A plate key is a composed object; composing it
# by hand is the honest way to do it.
KEY_R = {
    RADIOLARIAN: 8.0, CENTRIC: 9.5, PENNATE: 10.0, CHAIN: 3.2,
    CERATIUM: 7.5, COPEPOD: 9.5, TINTINNID: 8.0,
}


def _specimen(c, kind, cx, cy, seed=1):
    """One drawn individual, sized so every row occupies the same column.
    A stable seed per row keeps the specimen from shimmering between
    frames."""
    rng = random.Random(seed * 7919 + kind)
    g = Genome(kind, rng)
    r = KEY_R.get(kind, 9.0)
    if kind == COPEPOD:
        draw_copepod(c, cx, cy, r, -0.35, g, False)
    else:
        DRAW[kind](c, cx, cy, r, -0.35, g)


def census(eco):
    """[(kind, count, biomass), ...] sorted by biomass, present types only."""
    tally = {}
    for a in eco.agents:
        if a.vis <= 0.03:
            continue
        n, m = tally.get(a.g.kind, (0, 0.0))
        tally[a.g.kind] = (n + 1, m + a.mass)
    rows = [(k, v[0], v[1]) for k, v in tally.items()]
    rows.sort(key=lambda r: -r[2])
    return rows


def _hms_days(d):
    y, r = divmod(int(d), 365)
    if y:
        return "%dY %03dD" % (y, r)
    return "%dD" % r


def draw_progress(c, track, day, y0=12):
    """Where we are, how long we have been, how long is left, and what is
    next. Four lines, and the fourth is the one people actually care about."""
    la, lo = track.position(day)
    total = track.days[-1]
    port, away = track.next_port(day)
    ns = "N" if la >= 0 else "S"
    ew = "E" if lo >= 0 else "W"

    text(c, 10, y0, "DRAKE  1577-1580")
    text(c, 10, y0 + 9, "%02d%s%02d'%s   %03d%s%02d'%s"
         % (abs(int(la)), "\xb0", int(abs(la) % 1 * 60), ns,
            abs(int(lo)), "\xb0", int(abs(lo) % 1 * 60), ew))
    text(c, 10, y0 + 18, "AT SEA %s" % _hms_days(day))
    text(c, 10, y0 + 27, "TO GO  %s" % _hms_days(total - day))
    lab = "NEXT   %s %dD" % (port[:13], int(away))
    text(c, 10, y0 + 36, lab)

    # progress bar: the voyage as a line, with a mark where we are
    bx0, bx1, by = 10, W - 11, y0 + 48
    c.line(bx0, by, bx1, by)
    c.line(bx0, by - 2, bx0, by + 2)
    c.line(bx1, by - 2, bx1, by + 2)
    px = bx0 + (bx1 - bx0) * (day / total)
    c.line(px, by - 4, px, by + 4)
    # ticks at each anchorage, so the bar shows the shape of the voyage
    here = None
    for wp in track.wp:
        p = (wp[1], wp[2])
        if p == here:
            x = bx0 + (bx1 - bx0) * (wp[0] / total)
            c.line(x, by - 2, x, by + 2)
        here = p
    return by + 10


def render_key(canvas, eco, track, day, chrome=True, w=W, h=H):
    canvas.clear()
    y = draw_progress(canvas, track, day) if chrome else 10

    rows = census(eco)
    total = sum(r[2] for r in rows) or 1.0
    canvas.line(10, y, w - 11, y)
    y += 6

    max_rows = (h - y - 14) // ROW_H
    for i, (kind, n, mass) in enumerate(rows[:max_rows]):
        cy = y + ROW_H // 2
        _specimen(canvas, kind, SPEC_X, cy, seed=i + 1)
        text(canvas, TEXT_X, cy - 11, NAMES.get(kind, "?"))
        text(canvas, TEXT_X, cy - 3, ROLES.get(kind, ""))
        # share of biomass as a bar, count as a number. Two different
        # questions -- how much of the water is this, and how many are there
        # -- and for a bloom of small cells the answers diverge sharply.
        bw = int((w - 22 - TEXT_X) * (mass / total))
        canvas.line(TEXT_X, cy + 8, TEXT_X + max(1, bw), cy + 8)
        cnt = "%d" % n
        text(canvas, w - 11 - text_width(cnt), cy + 6, cnt)
        y += ROW_H

    if chrome and len(rows) > max_rows:
        text(canvas, 10, h - 12, "AND %d MORE" % (len(rows) - max_rows))
    elif chrome:
        text(canvas, 10, h - 12, "%d TAXA  %d INDIVIDUALS"
             % (len(rows), sum(r[1] for r in rows)))
