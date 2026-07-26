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
NUM_W = 16           # right-hand column, four characters of abundance

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


# --------------------------------------------------------------------------
# abundance, on one absolute scale
# --------------------------------------------------------------------------
#
# The number of individuals drawn in the water is a rendering decision, not
# an ecological one -- the count is compressed so that an oligotrophic gyre
# is watchable rather than blank.  That compression is right for the water
# and wrong for a key.  So the key plate reports what the *model* believes,
# not what the renderer drew, and the honest ecology lives here.
#
# The scale: 1 is the scarcest any drawn organism ever gets, anywhere on the
# voyage, while still being present at all.  Everything else is a multiple of
# that.  So 250 beside Chaetoceros means there is 250 times more Chaetoceros
# in this water than there is of the rarest organism at the place it is
# rarest -- one yardstick, good across every species and every day of the
# three years.
#
# A_REF is *measured*, not chosen: Stage 6 runs the whole 1018 days and logs
# per-type abundance daily, and A_REF is the smallest 7-day mean any type
# reaches while present.  A rolling mean rather than an instantaneous
# minimum, because a single straggler on one afternoon is noise, and "the
# place it is rarest" should be a place rather than a moment.  The measured
# value is then baked into flash as a constant.

A_REF = 0.42          # PLACEHOLDER. Stands in until Stage 6 measures it.
A_MAX = 10000.0       # top of the log bar. Also confirmed in Stage 6.


def census(eco):
    """[(kind, count, biomass, x), ...] sorted by abundance, present types
    only. `x` is abundance on the A_REF scale."""
    tally = {}
    for a in eco.agents:
        if a.vis <= 0.03:
            continue
        n, m = tally.get(a.g.kind, (0, 0.0))
        tally[a.g.kind] = (n + 1, m + a.mass)
    rows = [(k, v[0], v[1], v[1] / A_REF) for k, v in tally.items()]
    rows.sort(key=lambda r: -r[3])
    return rows


def abundance_label(x):
    """Four characters at most, because that is what the column is worth.
    Below 10 it is worth a decimal; above 999 nobody cares about the units."""
    if x < 9.95:
        return ("%.1f" % x).rstrip("0").rstrip(".")
    if x < 999.5:
        return "%d" % int(round(x))
    if x < 99500:
        return "%dK" % int(round(x / 1000.0))
    return ">99K"


def abundance_bar(c, x0, y, wpx, x):
    """Log scale, with a tick at each decade.

    Linear would be useless: the range across the voyage is three or four
    orders of magnitude, so on a linear bar everything except the current
    winner is a single pixel. The decade ticks are what stop a log scale from
    being mysterious -- you can see that a bar reaching the second tick means
    a hundredfold, without being told."""
    c.line(x0, y, x0 + wpx, y)
    dec = math.log10(A_MAX)
    k = 1
    while k <= dec + 0.001:
        tx = x0 + wpx * (k / dec)
        c.line(tx, y - 2, tx, y)
        k += 1
    f = max(0.0, min(1.0, math.log10(max(x, 1.0)) / dec))
    c.line(x0, y + 2, x0 + max(1.0, wpx * f), y + 2)
    c.line(x0, y + 1, x0, y + 3)
    c.line(x0 + max(1.0, wpx * f), y + 1, x0 + max(1.0, wpx * f), y + 3)


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
    canvas.line(10, y, w - 11, y)
    y += 4
    if chrome:
        text(canvas, TEXT_X, y, "ABUNDANCE X SCARCEST")
        y += 8

    bar_w = w - 11 - NUM_W - 4 - TEXT_X
    max_rows = int((h - y - 14) // ROW_H)
    for i, (kind, n, mass, x) in enumerate(rows[:max_rows]):
        cy = y + ROW_H // 2
        _specimen(canvas, kind, SPEC_X, cy, seed=i + 1)
        text(canvas, TEXT_X, cy - 11, NAMES.get(kind, "?"))
        text(canvas, TEXT_X, cy - 3, ROLES.get(kind, ""))
        abundance_bar(canvas, TEXT_X, cy + 8, bar_w, x)
        lab = abundance_label(x)
        text(canvas, w - 11 - text_width(lab), cy + 6, lab)
        y += ROW_H

    if chrome and len(rows) > max_rows:
        text(canvas, 10, h - 12, "AND %d MORE" % (len(rows) - max_rows))
    elif chrome:
        text(canvas, 10, h - 12, "%d TAXA" % len(rows))
