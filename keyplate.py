#!/usr/bin/env python3
"""
KEYPLATE  -  the third screen: what you are looking at, and where.

Every natural-history plate has a key. This is that key, and it does the one
thing neither the water nor the map can do: it tells a person who has just
walked into the room what the object is.

It lists only the species actually present, drawn at a comparable size and
sorted by abundance, so it is a census rather than a legend -- it changes as
the ship sails, and watching the list turn over between Valparaiso and the
mid-Pacific is arguably the clearest statement the piece makes.

Canvas only. Ports with everything else.
"""

import math
import random

import draw
import fish as F
from drift import (Canvas, W, H, text, text_width, text_height, fit_scale,
                   trim, wrap, T_BIG, T_MED)

# --------------------------------------------------------------------------
# what each row says
# --------------------------------------------------------------------------
#
# TWO LINES: a common name, then a length and a genus.
#
# The old plate led with the genus -- COSCINODISCUS, RHIZOSOLENIA -- which was
# right for organisms that have no common name anybody knows. Fish are the
# opposite case: ANCHOVETA and BLUE MARLIN mean something to a visitor and
# ENGRAULIS and MAKAIRA do not, and the plate exists to be read by somebody
# who has just walked in.
#
# So the genus moves to the second line, where it does two jobs. It is the
# taxonomic anchor a natural-history plate ought to carry, and it disambiguates
# the one collision in the roster: there are two lanternfish, a boreal North
# Atlantic one and a circumglobal one, and they are both called lanternfish by
# everyone including FishBase. BENTHOSEMA and CERATOSCOPELUS on the size line
# tells them apart without a paragraph.
#
# The unit closes up to the number -- 2-5MM, not 2-5 MM. It buys the one
# character that lets every line fit at reading size, and it groups the
# quantity with its unit, which stops the eye parsing "CM ANCHOVETA".
#
# Lengths are the FishBase common-to-max range, which is what a visitor with a
# ruler would be measuring. This is the one thing they genuinely cannot get
# from the plate: everything is drawn at a comparable size on purpose, which
# is what makes the morphologies comparable and is also, unavoidably, a lie
# about scale. The size line is where that lie gets corrected.

ROW_H = 64           # name, size and genus, bar
SPEC_X = 32          # centre of the specimen column
TEXT_X = 68          # set by the longest name at reading size: CHUB MACKEREL
                     # is thirteen characters, 195 px at T_BIG, against a
                     # column of W - 10 - 68 = 222.
SPEC_HALF = 30       # nothing in the specimen column may reach further than
                     # this from its centre. 32 + 30 = 62 against a text
                     # column starting at 68, so six clear pixels.
SWAY_HEADROOM = 0.08 # BODY LENGTHS of fore-and-aft sway reserved in the
                     # clamp -- and the unit is the whole of the fix. The
                     # plankton plate reserved 0.5 RADII, and carrying that
                     # number across to a length-based drawing reserved six
                     # times the room the sway actually uses. Every specimen
                     # was clamped to 23 px in a 64 px row and the plate
                     # looked like a list with punctuation beside it. The
                     # sway is KEY_SWAY, which is 0.055, so 0.08 is the
                     # honest reservation with a little over.

# --------------------------------------------------------------------------
# the specimens swim
# --------------------------------------------------------------------------
#
# A key plate with static drawings is a poster. The whole argument for this
# object over a print is that the animals move, and the plate is where a
# visitor is looking hardest at any one of them -- so it is the last place
# that should be still.
#
# The pose comes from the SAME body wave as the water (draw.py), which is the
# point: the tuna on the plate beats only its tail because that is what a
# tuna does, and the viperfish undulates end to end because that is what a
# viperfish does. Nothing here is decoration invented for the plate.
#
# The one difference is that these are DETERMINISTIC where the water's are
# stochastic. A specimen in a display case swims on the spot and comes back;
# a Poisson process would have it wander off the row.

BASE_ANG = math.pi   # specimens face LEFT, into the type they are labelling,
                     # which is how every field guide in existence sets a
                     # plate
KEY_RATE = 0.55      # the plate runs slower than the water. A scene can
                     # afford business; a specimen under examination that will
                     # not keep still is just hard to look at, and a column of
                     # them beating at once reads as fidgeting.
KEY_SWAY = 0.055     # fore-and-aft sway, in body lengths
KEY_PITCH = 0.10     # radians of slow nose-up/nose-down roll


def specimen_pose(key, t):
    """(angle, forward offset in body lengths, tail phase).

    `t` is real seconds. The tail beat is the species' own, from Bainbridge's
    relation in fish.py, slowed by KEY_RATE.

    The sway is SINUSOIDAL and small. The water's fish translate; a specimen
    on a plate has to come back the way it went, so the travel is a gentle
    drift and the work is done by the body -- which is also what you would
    actually see, since a fish holding station in a current still beats its
    tail."""
    f = F.BY_KEY[key]
    hz = F.beat_hz(f) * KEY_RATE
    ph = 2.0 * math.pi * hz * t
    # two slow sinusoids whose periods do not divide into each other, so the
    # roll never repeats over any span anyone will watch and still needs no
    # state. The per-species factor comes from the key constant itself, so
    # every animal has its own rhythm and none of them had to be typed in.
    p = 17.0 * (0.7 + 0.11 * (key % 7))
    roll = (KEY_PITCH * math.sin(2.0 * math.pi * t / p)
            + 0.6 * KEY_PITCH * math.sin(2.0 * math.pi * t / (p * 1.618) + 1.1))
    sway = KEY_SWAY * math.sin(2.0 * math.pi * t / (p * 0.53))
    return BASE_ANG + roll, sway, ph


def _measure_reach(key, L=40.0, phases=8, pad=90):
    """How far the drawing actually reaches from its centre, in body lengths,
    over a whole beat.

    MEASURED, NOT ESTIMATED. The old plate clamped against the ecosystem's
    separation radius, which is isotropic by design and describes a different
    thing: it read 1.8 where the copepod drew 1.5 and 8.4 where a chain drew
    rather more. Wrong in both directions, and neither error visible until
    something touched the type.

    Each species is drawn once at import, through a full cycle of its own
    animation, into a scratch canvas, and the furthest lit pixel from the
    centre is its reach. That is not an estimate of the silhouette, it is the
    silhouette. On the MCU the same measurement runs at build time and what
    ships is a table of numbers."""
    c = Canvas(2 * pad, 2 * pad)
    form = F.FORM[key]
    for i in range(phases):
        ph = 2.0 * math.pi * i / phases
        draw.draw_fish(c, pad, pad, L, BASE_ANG + KEY_PITCH * math.sin(ph),
                       form, phase=ph)
    buf = c.buf
    far = 0.0
    for y in range(2 * pad):
        row = y * 2 * pad
        dy = y - pad
        for x in range(2 * pad):
            if buf[row + x]:
                d = (x - pad) ** 2 + dy * dy
                if d > far:
                    far = d
    return math.sqrt(far) / L


# The length every specimen would be drawn at if nothing were in the way, and
# then what actually fits. A plate key is a composed object: the wanted value
# is the one that makes a row look right, and the clamp is what stops a
# 2 metre wahoo from lying across the species name.
KEY_L_WANT = 46.0
REACH = {k: _measure_reach(k) for k in F.ALL_KEYS}
KEY_L = {k: min(KEY_L_WANT, SPEC_HALF / max(REACH[k] + SWAY_HEADROOM, 0.15))
         for k in F.ALL_KEYS}


def _specimen(c, key, cx, cy, t=0.0):
    """One drawn individual, sized so every row occupies the same column."""
    L = KEY_L[key]
    ang, fwd, ph = specimen_pose(key, t)
    fwd = max(-SWAY_HEADROOM, min(SWAY_HEADROOM, fwd))
    dx = fwd * L * math.cos(ang)
    dy = fwd * L * math.sin(ang)
    draw.draw_fish(c, cx + dx, cy + dy, L, ang, F.FORM[key], phase=ph)


# --------------------------------------------------------------------------
# abundance, on one absolute scale
# --------------------------------------------------------------------------
#
# The number of individuals drawn in the water is a rendering decision, not an
# ecological one -- the count is compressed so that a gyre is watchable rather
# than blank, and the trophic pyramid is compressed on top of that. Both are
# right for the water and wrong for a key.
#
# So the plate reports what the MODEL believes, not what the renderer drew,
# and the honest ecology lives here. The scale: 1 is about the scarcest any
# species ever gets anywhere on the voyage while still being present at all.
# Everything else is a multiple of that. So a bar reaching the second tick
# means a hundredfold, and it means it against one yardstick good across every
# species and every day of the three years.
#
# A_MAX is measured by tools/check_biogeography.py over the whole track rather
# than chosen, and baked in here.

A_MAX = 10000.0       # top of the log bar


def census(eco):
    """[(key, count, suitability, abundance), ...] sorted by abundance."""
    return eco.census()


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
        c.line(tx, y - 3, tx, y)
        k += 1
    f = max(0.0, min(1.0, math.log10(max(x, 1.0)) / dec))
    fx = x0 + max(2.0, wpx * f)
    # a filled bar rather than a hairline: at this size a one-pixel rule under
    # a one-pixel rule reads as a printing fault
    c.fill_rect(x0, y + 2, max(2.0, wpx * f), 3)
    c.line(x0, y + 1, x0, y + 6)
    c.line(fx, y + 1, fx, y + 6)


def draw_header(c, track, day, y0=8):
    """One line of context and nothing more.

    The voyage block -- lat, lon, elapsed, to go -- lives on the water screen,
    which is where it belongs: that screen is up 98% of the time and this one
    is up for four minutes. Repeating it here at a size you can read would eat
    half the plate and leave room for two species, and two species is not a
    census."""
    sc = fit_scale(track.voyage.title, W - 20)
    text(c, 10, y0, track.voyage.title, scale=sc)
    y = y0 + text_height(sc) + 6
    for ln in wrap(track.status(day), W - 20, maxlines=2):
        text(c, 10, y, ln, scale=T_MED)
        y += text_height(T_MED) + 3
    return y + 3


# --------------------------------------------------------------------------
# the plate, and why it moves
# --------------------------------------------------------------------------
#
# At a size a person can read from a sofa, five rows fit -- and the census
# routinely has eight or ten species in it, so something has to give. The
# options were: show the top five and lie by omission; shrink the type back
# and lie about legibility; or move.
#
# It moves. A slow pan from the top of the list to the bottom, with a hold at
# each end, over exactly the time the plate is on screen. Not a loop: a loop
# has no beginning, so a visitor who arrives mid-cycle never knows whether
# they have seen the whole thing. A pan that starts at the top and stops at
# the bottom has both, and the holds are what make it read as a considered
# movement rather than a slipping belt.
#
# If the list fits, nothing moves at all. That is the common case in a gyre,
# and a plate that jiggles when it has no need to would be the worst of both.
PAN_STILL = 1.0            # relative length of each of the three rests
PAN_MOVE = 3.0             # ... and of each of the two travels


def _pan(t_into, dwell, span):
    """Pixels to shift the list up, given how far into the plate's dwell we
    are. Down, then back up, eased at every rest."""
    if span <= 0 or dwell <= 0:
        return 0.0
    unit = dwell / (3.0 * PAN_STILL + 2.0 * PAN_MOVE)
    still = unit * PAN_STILL
    move = unit * PAN_MOVE
    t = max(0.0, t_into)
    if t < still:
        return 0.0
    t -= still
    if t < move:
        u = t / move
    elif t < move + still:
        return span
    elif t < 2.0 * move + still:
        u = 1.0 - (t - move - still) / move
    else:
        return 0.0
    u = max(0.0, min(1.0, u))
    return span * u * u * (3.0 - 2.0 * u)


def render_key(canvas, eco, track, day, chrome=True, w=W, h=H,
               t_into=0.0, dwell=0.0, t=None):
    canvas.clear()
    # REAL seconds, not simulated ones. eco.t moves once per simulated hour,
    # and a tail beat driven off a staircase does not move at all in between.
    t = eco.real_t if t is None else t

    top = draw_header(canvas, track, day) if chrome else 10
    canvas.line(10, top, w - 11, top)
    top += 8

    rows = census(eco)
    bot = h - 10
    if chrome:
        bot -= text_height(T_MED) + 12

    span = max(0.0, len(rows) * ROW_H - (bot - top))
    off = _pan(t_into, dwell, span)

    bar_w = w - 10 - TEXT_X
    canvas.clip(0, top, w, bot)
    for i, (key, n, suit, ab) in enumerate(rows):
        ry = top - off + i * ROW_H
        if ry > bot or ry + ROW_H < top:
            continue                            # off the plate, skip the work
        f = F.BY_KEY[key]
        cy = ry + ROW_H // 2
        avail = w - 10 - TEXT_X
        _specimen(canvas, key, SPEC_X, cy, t=t)
        nsc = fit_scale(f.common, avail)
        text(canvas, TEXT_X, ry + 5, f.common, scale=nsc)
        ty = ry + 5 + text_height(nsc) + 5
        # lo=T_MED, not lo=1: if a line ever outgrows its column the right
        # answer is to shorten the words, not to print them at a size that
        # defeats the point of the whole pass
        # TRIMMED, not shrunk. fit_scale with lo=T_MED cannot go below
        # reading size -- which is the whole point of it -- so a line that
        # does not fit simply runs off the panel: "5-10CM CERATOSCOPELUS" is
        # 231 px against a 222 px column and lost its last two letters to
        # the edge. Trimming puts the truncation where it can be seen and
        # keeps the type readable, which is the trade this plate has made
        # everywhere else.
        line = trim("%s %s" % (f.size_label, f.binomial.split()[0]),
                    avail, scale=T_MED)
        text(canvas, TEXT_X, ty, line, scale=T_MED)
        by = ty + text_height(T_MED) + 10
        abundance_bar(canvas, TEXT_X, by, bar_w, ab)
    canvas.clip()

    if chrome:
        # the fade marks: a hairline at whichever end has more list behind it,
        # so it is obvious the plate is a window onto something longer
        if off > 1.0:
            canvas.line(w // 2 - 8, top + 1, w // 2 + 8, top + 1)
        if off < span - 1.0:
            canvas.line(w // 2 - 8, bot - 2, w // 2 + 8, bot - 2)
        text(canvas, 10, h - 10 - text_height(T_MED),
             "%d SPECIES IN THIS WATER" % len(rows), scale=T_MED)
