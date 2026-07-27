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

from drift import (Canvas, W, H, text, text_width, text_height, fit_scale,
                   T_BIG, T_MED, DRAW, DRIFTER_KINDS,
                   HET_KINDS, EXTENT, Genome, COPEPOD, draw_copepod,
                   RADIOLARIAN, CENTRIC, PENNATE, CHAIN, CERATIUM, TINTINNID,
                   COCCO, FLAGELLATE, THALASSIO, RHIZO, CORETHRON,
                   ACANTHARIA, FORAM, ORNITHO, TRICHO, SALP, KRILL,
                   GAIT, HELIX, HOP, CRUISE, HELIX_HZ, HELIX_YAW, HOP_HZ,
                   COAST_S, SWIM_SCALE, TUMBLE_S)
import random

NAMES = {
    RADIOLARIAN: "RADIOLARIA",
    CENTRIC: "COSCINODISCUS",
    PENNATE: "NAVICULA",
    CHAIN: "CHAETOCEROS",
    CERATIUM: "CERATIUM",
    COPEPOD: "CALANUS",
    TINTINNID: "TINTINNID",
    COCCO: "EMILIANIA",
    FLAGELLATE: "MICROMONAS",
    THALASSIO: "THALASSIOSIRA",
    RHIZO: "RHIZOSOLENIA",
    CORETHRON: "CORETHRON",
    ACANTHARIA: "ACANTHARIA",
    FORAM: "GLOBIGERINA",
    ORNITHO: "ORNITHOCERCUS",
    TRICHO: "TRICHODESMIUM",
    SALP: "SALPA",
    KRILL: "EUPHAUSIA",
}

# Second line under each name: what it does for a living. Three words, so a
# visitor gets the ecology without being lectured.
# Nineteen characters is the hard limit: that is what W - 10 - TEXT_X buys
# at T_MED, and a role that has to shrink to fit is a role nobody reads. The
# double spaces went for the same reason -- they cost two characters and
# bought a typographic nicety that does not survive being 3 mm tall.
ROLES = {
    RADIOLARIAN: "MIXOTROPH DRIFTS",
    CENTRIC: "DIATOM SINKS",
    PENNATE: "DIATOM GLIDES",
    CHAIN: "DIATOM CHAINS",
    CERATIUM: "MIXOTROPH SWIMS",
    COPEPOD: "GRAZER MIGRATES",
    TINTINNID: "GRAZER FILTERS",
    COCCO: "PLATED DRIFTS",
    FLAGELLATE: "NANOPLANKTON SWIMS",
    THALASSIO: "DIATOM BEADS",
    RHIZO: "DIATOM NEEDLES",
    CORETHRON: "DIATOM POLAR",
    ACANTHARIA: "MIXOTROPH RADIATES",
    FORAM: "MIXOTROPH CHAMBERED",
    ORNITHO: "MIXOTROPH SAILS",
    TRICHO: "FIXES NITROGEN",
    SALP: "GRAZER FILTERS",
    KRILL: "GRAZER SWARMS",
}

# Laid out for type you can read from a sofa rather than type that fits.
# At T_BIG a name is 21 px tall and at T_MED a role is 14, so a row is 66
# where it used to be 34 -- five rows on the panel instead of eleven, which
# is why the plate now moves.
ROW_H = 66
SPEC_X = 28          # centre of the specimen column
TEXT_X = 56          # set by the longest name: COSCINODISCUS is thirteen
                     # characters, which at T_BIG is 234 px, which is exactly
                     # what W - 10 - 56 leaves. The column is the type, not
                     # the other way round.
SPEC_HALF = 26       # nothing in the specimen column may reach further than
                     # this from its centre, or it climbs into the name
NUM_W = 44           # right-hand column, four characters of abundance

# Drawing radius per type for the key column, hand-set rather than derived.
# EXTENT is a separation radius and is deliberately isotropic, so it does not
# describe a Chaetoceros chain, which is compact across its axis and up to
# twelve radii long down it. A plate key is a composed object; composing it
# by hand is the honest way to do it.
# Hand-set, then clamped. The hand-set value is the one that makes a row
# look right; the clamp is what stops a Chaetoceros chain -- eight radii long
# and compact across -- from lying across the species name. EXTENT is the
# separation radius and is deliberately isotropic, so it overstates the
# round ones and understates nothing, which makes it the safe thing to clamp
# against.
_KEY_R_WANT = {
    RADIOLARIAN: 13.0, CENTRIC: 15.0, PENNATE: 16.0, CHAIN: 5.2,
    CERATIUM: 12.0, COPEPOD: 15.0, TINTINNID: 13.0,
    COCCO: 14.0, FLAGELLATE: 10.5, THALASSIO: 5.4, RHIZO: 7.2,
    CORETHRON: 9.0, ACANTHARIA: 15.0, FORAM: 10.5, ORNITHO: 13.0,
    TRICHO: 9.0, SALP: 5.8, KRILL: 9.5,
}
KEY_R = {k: min(r, SPEC_HALF / max(EXTENT.get(k, 1.5), 0.5))
         for k, r in _KEY_R_WANT.items()}

# --------------------------------------------------------------------------
# the specimens swim
# --------------------------------------------------------------------------
#
# A key plate with static drawings is a poster. The whole argument for this
# object over a print is that the organisms move, and the plate is where a
# visitor is looking hardest at any one of them -- so it is the last place
# that should be still.
#
# The pose comes from the SAME gait constants as the water (drift.py, 10h),
# which is the point: the tintinnid on the plate corkscrews at the tintinnid
# rate, the copepod hops at the copepod rate, and the diatoms only turn in
# shear because diatoms only turn in shear. Nothing here is decoration
# invented for the plate.
#
# The one difference is that these are DETERMINISTIC where the water's are
# stochastic. A specimen in a display case swims on the spot and comes back;
# a Poisson process would have it wander off the row.

BASE_ANG = -0.35           # the angle every specimen was drawn at before

# --------------------------------------------------------------------------
# THE PLATE HAS ITS OWN MOTION, AND SHOULD
# --------------------------------------------------------------------------
#
# The first version drove the plate straight off SWIM_SCALE, which had two
# problems. The small one was a bug: SWIM_SCALE is read here as a module
# constant while the console sets it per-Ecosystem, so the swimming sliders
# moved the water and did nothing to the plate at all.
#
# The large one is that it should not have been the same number anyway. The
# water is a scene -- a thing happening at a distance that you watch for
# minutes and are not meant to track any individual through. The plate is a
# specimen case: one organism, held still, at fifteen pixels of radius, with
# a visitor's whole attention on it while they read its name. Those want
# different motion. A scene can afford business; a specimen under
# examination that will not keep still is just hard to look at, and a whole
# column of them turning at once reads as fidgeting.
#
# So the plate gets its own constants, all of them multipliers on what the
# water does, and all of them below 1. Tunable in tools/console.py under
# KEY PLATE, because "how much movement is too much on a thing being read"
# is a judgement by eye like every other number in this file's neighbourhood.
KEY_RATE = 0.55            # everything on the plate runs at this fraction of
                           # the water's already-slowed rate
KEY_YAW = 0.45             # helix yaw amplitude, against the water's
KEY_SURGE = 0.45           # fore-and-aft sway
KEY_SPIN_S = 420.0         # seconds for a non-swimmer to turn once. The water
                           # uses TUMBLE_S = 90, which on the plate had a
                           # radiolarian visibly rotating while you read two
                           # words next to it. Seven minutes is a drift.
KEY_BEAT = 0.60            # appendage beat rate

# Beats per second, in ANIMAL time, for the parts that move independently of
# the whole animal. Krill row their pleopods several times a second whatever
# else they are doing; the passive flexers are slower because nothing is
# driving them but the water.
BEAT_HZ = {KRILL: 5.0, CHAIN: 0.5, CORETHRON: 0.4}

# Which draw functions take a `phase`. An explicit set rather than a
# try/except on TypeError: catching TypeError around a call that might raise
# one for a completely different reason would swallow a real bug and then
# draw the thing twice.
ANIMATED = (COPEPOD, KRILL, SALP, CHAIN, CORETHRON)


def specimen_pose(kind, t):
    """(angle, forward offset in radii, beat phase in radians).

    `t` is real seconds. Everything is expressed in ANIMAL time and then
    slowed by SWIM_SCALE, exactly as the water is, so the plate and the panel
    behind it run at the same speed.

    The forward offset is deliberately small and always SINUSOIDAL. The first
    version used the water's impulse-and-decay curve, which is right for a
    copepod crossing open water and wrong for one in a display case: it darts
    forward, decays back, and then the cycle restarts, and what that reads as
    is a teleport. A specimen on a plate has to come back the way it went, so
    the translation is a gentle sway and the WORK is done by the appendages
    -- which is also what you would actually see, since a tethered copepod
    rows its antennae and stays put."""
    slow = SWIM_SCALE * KEY_RATE
    ta = t * slow                                  # animal seconds
    gait = GAIT.get(kind)
    beat = BEAT_HZ.get(kind)
    ph = 2.0 * math.pi * beat * ta * KEY_BEAT if beat is not None else 0.0
    if gait == HELIX:
        f = HELIX_HZ[kind]
        yaw = HELIX_YAW[kind] * KEY_YAW
        hp = 2.0 * math.pi * f * ta
        # the corkscrew, seen edge-on: a yaw oscillation, and a gentle surge
        # a quarter cycle out of phase so it reads as swimming rather than
        # as a windscreen wiper
        return (BASE_ANG + yaw * math.sin(hp),
                0.32 * KEY_SURGE * math.cos(hp), hp)
    if gait == HOP:
        hp = 2.0 * math.pi * HOP_HZ[kind] * ta
        # one antennal stroke per hop, and a sway a quarter cycle behind it,
        # because the body follows the limbs rather than leading them
        return BASE_ANG, 0.16 * KEY_SURGE * math.sin(hp - 1.4), hp
    if gait == CRUISE:
        return (BASE_ANG + 0.05 * KEY_YAW * math.sin(2.0 * math.pi * 0.35 * ta),
                0.0, ph)
    # not a swimmer: turning in shear, and nothing else. On its own clock,
    # much slower than the water's, because a specimen rotating while you
    # read the two words beside it is a specimen you cannot read.
    return (BASE_ANG + 2.0 * math.pi * (t % KEY_SPIN_S) / KEY_SPIN_S, 0.0, ph)


def _specimen(c, kind, cx, cy, seed=1, t=0.0):
    """One drawn individual, sized so every row occupies the same column.
    A stable seed per row keeps the specimen from shimmering between frames;
    the pose is the only thing allowed to change."""
    rng = random.Random(seed * 7919 + kind)
    g = Genome(kind, rng)
    r = KEY_R.get(kind, 14.0)
    ang, fwd, ph = specimen_pose(kind, t)
    dx = fwd * r * math.cos(ang)
    dy = fwd * r * math.sin(ang)
    if kind == COPEPOD:
        draw_copepod(c, cx + dx, cy + dy, r, ang, g, False, phase=ph)
    elif kind in ANIMATED:
        DRAW[kind](c, cx + dx, cy + dy, r, ang, g, phase=ph)
    else:
        DRAW[kind](c, cx + dx, cy + dy, r, ang, g)


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
        c.line(tx, y - 3, tx, y)
        k += 1
    f = max(0.0, min(1.0, math.log10(max(x, 1.0)) / dec))
    fx = x0 + max(2.0, wpx * f)
    # a filled bar rather than a hairline: at this size a one-pixel rule
    # under a one-pixel rule reads as a printing fault
    c.fill_rect(x0, y + 2, max(2.0, wpx * f), 3)
    c.line(x0, y + 1, x0, y + 6)
    c.line(fx, y + 1, fx, y + 6)


def _hms_days(d):
    y, r = divmod(int(d), 365)
    if y:
        return "%dY %03dD" % (y, r)
    return "%dD" % r


def draw_header(c, track, day, y0=8):
    """One line of context and nothing more.

    The voyage block -- lat, lon, elapsed, to go, next port -- moved to the
    water screen, which is where it belongs: that screen is up 98% of the
    time and this one is up for fifteen seconds. Repeating it here at a size
    you can read would eat half the plate and leave room for two species,
    and two species is not a census."""
    n = None
    sc = fit_scale(track.voyage.title, W - 20)
    text(c, 10, y0, track.voyage.title, scale=sc)
    y = y0 + text_height(sc) + 6
    text(c, 10, y, track.status(day)[:24], scale=T_MED)
    return y + text_height(T_MED) + 6


# --------------------------------------------------------------------------
# the plate, and why it moves
# --------------------------------------------------------------------------
#
# At the old type size eleven rows fitted. At a size a person can read from
# a sofa, five do -- and the census routinely has ten or twelve taxa in it,
# so something has to give. The options were: show the top five and lie by
# omission; shrink the type back and lie about legibility; or move.
#
# It moves. A slow pan from the top of the list to the bottom, with a hold
# at each end, over exactly the time the plate is on screen. Not a loop: a
# loop has no beginning, so a visitor who arrives mid-cycle never knows
# whether they have seen the whole thing. A pan that starts at the top and
# stops at the bottom has both, and the holds are what make it read as a
# considered movement rather than a slipping belt.
#
# If the list fits, nothing moves at all. That is the common case in a gyre,
# and a plate that jiggles when it has no need to would be the worst of both.

PAN_HOLD = 0.13            # fraction of the dwell spent still, at each of
                           # the three rests: top, bottom, top again


def _pan(t_into, dwell, span):
    """Pixels to shift the list up, given how far into the plate's dwell we
    are.

    Down, then back up. A one-way pan ends with the list at the bottom and
    the top of it out of sight, which means the plate spends its last moment
    showing you the least interesting end and then cuts away -- and the next
    time it appears it starts from the top again, so the transition is a
    jump. There and back leaves it where it started, and gives a visitor two
    passes at a list they may only have half read the first time.

    Three rests: at the top, at the bottom of the travel, and at the top
    again. Eased at every one of them, because a linear pan starts and stops
    with a visible jerk and a reversal without a rest reads as a bounce."""
    if span <= 0 or dwell <= 0:
        return 0.0
    f = max(0.0, min(1.0, t_into / dwell))
    leg = (1.0 - 3.0 * PAN_HOLD) / 2.0          # each travel, as a fraction
    if f < PAN_HOLD:
        return 0.0
    if f < PAN_HOLD + leg:
        u = (f - PAN_HOLD) / leg
    elif f < 2.0 * PAN_HOLD + leg:
        return span
    elif f < 2.0 * PAN_HOLD + 2.0 * leg:
        u = 1.0 - (f - 2.0 * PAN_HOLD - leg) / leg
    else:
        return 0.0
    u = max(0.0, min(1.0, u))
    return span * u * u * (3.0 - 2.0 * u)


def render_key(canvas, eco, track, day, chrome=True, w=W, h=H,
               t_into=0.0, dwell=0.0, t=None):
    canvas.clear()
    t = eco.t * 86400.0 if t is None else t     # real seconds, for the gaits

    top = draw_header(canvas, track, day) if chrome else 10
    canvas.line(10, top, w - 11, top)
    top += 8

    rows = census(eco)
    bot = h - 10
    if chrome:
        bot -= text_height(T_MED) + 12

    span = max(0.0, len(rows) * ROW_H - (bot - top))
    off = _pan(t_into, dwell, span)

    bar_w = w - 10 - NUM_W - 8 - TEXT_X
    canvas.clip(0, top, w, bot)
    for i, (kind, n, mass, x) in enumerate(rows):
        ry = top - off + i * ROW_H
        if ry > bot or ry + ROW_H < top:
            continue                            # off the plate, skip the work
        cy = ry + ROW_H // 2
        _specimen(canvas, kind, SPEC_X, cy, seed=i + 1, t=t)
        name = NAMES.get(kind, "?")
        nsc = fit_scale(name, w - 10 - TEXT_X)
        text(canvas, TEXT_X, ry + 4, name, scale=nsc)
        ty = ry + 4 + text_height(nsc) + 4
        role = ROLES.get(kind, "")
        # lo=T_MED, not lo=1: if a role ever outgrows its column the right
        # answer is to shorten the words, not to print them at a size that
        # defeats the point of this whole pass
        text(canvas, TEXT_X, ty, role,
             scale=fit_scale(role, w - 10 - TEXT_X, hi=T_MED, lo=T_MED))
        by = ty + text_height(T_MED) + 9
        abundance_bar(canvas, TEXT_X, by, bar_w, x)
        lab = abundance_label(x)
        text(canvas, w - 10 - text_width(lab, scale=T_MED), by - 4, lab,
             scale=T_MED)
    canvas.clip()

    if chrome:
        # the fade marks: a hairline at whichever end has more list behind it,
        # so it is obvious the plate is a window onto something longer
        if off > 1.0:
            canvas.line(w // 2 - 8, top + 1, w // 2 + 8, top + 1)
        if off < span - 1.0:
            canvas.line(w // 2 - 8, bot - 2, w // 2 + 8, bot - 2)
        text(canvas, 10, h - 10 - text_height(T_MED),
             "%d TAXA IN THIS WATER" % len(rows), scale=T_MED)
