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
                   wrap,
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

# ONE LINE UNDER THE NAME: how big it is and what it is. Nothing else.
#
# This went through three versions and the third is the shortest, which is
# usually the sign.
#
# It began as "GRAZER  SWARMS" -- a trophic role and a verb, in telegraphese,
# because the column had nineteen characters and no grammar would fit in
# them. Then it grew a third line carrying one memorable thing about each
# organism: A PILLBOX OF GLASS, ROWS WITH ANTENNAE. Those were nice to read
# and they were the wrong register for this object. A plate key states; it
# does not narrate. The moment one row says something charming the next row
# has to as well, and what began as a caption is a voice.
#
# So: size and class, both of them checkable, and the drawing does the rest.
# The morphology is right there at fifteen pixels and it is the whole reason
# the piece exists -- a line of prose underneath it is a second-hand account
# of something the viewer is already looking at.
#
# The unit closes up to the number -- 2-5MM, not 2-5 MM. It buys the one
# character that lets every line fit at reading size, and it groups the
# quantity with its unit, which stops the eye parsing "MM COPEPOD".
#
# Sizes are hand-written LENGTH ranges rather than the model's equivalent
# spherical diameters, because ESD is a modelling convenience and a viewer
# holding a ruler to a krill is measuring its length. This is the one thing a
# visitor genuinely cannot get from the plate: everything is drawn at a
# comparable size on purpose, which is what makes the morphologies comparable
# and is also, unavoidably, a lie about scale. The caption is where that lie
# gets corrected, and correcting it is enough work for one line.
SIZES = {
    FLAGELLATE: "1-3UM", COCCO: "5-10UM", THALASSIO: "10-30UM",
    CHAIN: "10-50UM", PENNATE: "20-60UM", CORETHRON: "50-100UM",
    ORNITHO: "50-120UM", TINTINNID: "50-200UM", CENTRIC: "50-500UM",
    CERATIUM: "0.1-0.5MM", RHIZO: "0.2-1MM", RADIOLARIAN: "0.1-2MM",
    ACANTHARIA: "0.1-1MM", FORAM: "0.3-1MM", TRICHO: "1-3MM",
    COPEPOD: "2-5MM", KRILL: "1-6CM", SALP: "1-10CM",
}

# Group words, all twelve characters or fewer so that "size GROUP" fits the
# column at reading size. DINOPHYTE rather than DINOFLAGELLATE and
# FORAMINIFER rather than FORAMINIFERAN for exactly that reason; both are
# correct, and a word that has to be shrunk to fit is a word nobody reads.
GROUPS = {
    RADIOLARIAN: "RADIOLARIAN", CENTRIC: "DIATOM", PENNATE: "DIATOM",
    CHAIN: "DIATOM", CERATIUM: "DINOPHYTE", COPEPOD: "COPEPOD",
    # GREEN ALGA, not PICOPLANKTON: picoplankton is a size class and the
    # size is already on the same line, so it would be the only entry in this
    # table that told you nothing new. Micromonas is a prasinophyte.
    TINTINNID: "CILIATE", COCCO: "HAPTOPHYTE", FLAGELLATE: "GREEN ALGA",
    THALASSIO: "DIATOM", RHIZO: "DIATOM", CORETHRON: "DIATOM",
    ACANTHARIA: "ACANTHARIAN", FORAM: "FORAMINIFER", ORNITHO: "DINOPHYTE",
    TRICHO: "CYANOPHYTE", SALP: "TUNICATE", KRILL: "KRILL",
}

ROW_H = 64           # name, size and class, bar
SPEC_X = 26          # centre of the specimen column
TEXT_X = 56          # set by the longest name: COSCINODISCUS is thirteen
                     # characters, which at T_BIG is exactly W - 10 - 56.
                     # The column is set by the type, not the other way
                     # round, and what the type does not need goes to the
                     # specimen and to the gutter between them.
SPEC_HALF = 24       # nothing in the specimen column may reach further than
                     # this from its centre. 26 + 24 = 50 against a text
                     # column starting at 56, so six clear pixels.
                     #
                     # Six is enough BECAUSE the reach is now measured rather
                     # than inferred. The old two-pixel gutter did not fail
                     # for being narrow, it failed because the number it was
                     # measured against was wrong -- and a gutter sized to
                     # absorb an unknown error is just a wider unknown.
SWAY_HEADROOM = 0.50 # radii of fore-and-aft sway reserved in the clamp.
                     # This is the term the first version missed. KEY_R was
                     # clamped against EXTENT, which is the STATIC reach, and
                     # then the sway moved the whole organism up to half a
                     # radius further on top of it. Measured on the copepod:
                     # antenna tip 1.5 radii out, plus 0.48 of sway, landing
                     # at x = 52.8 against a text column at 52. It touched,
                     # and it touched by less than a pixel, which is why it
                     # took a photograph to find.
# No right-hand number. The bar carries the abundance and the figure beside
# it was answering a question nobody had: "1.4" is 1.4 times the scarcest any
# organism ever gets anywhere on the voyage, which is a real quantity, an
# honest one, and completely opaque at a glance. The bar with its decade
# ticks says the same thing in the only way that reads from a sofa -- longer
# is more, each tick is ten times -- and it says it without asking anyone to
# hold a reference value in their head.

# Drawing radius per type for the key column, hand-set rather than derived.
# EXTENT is a separation radius and is deliberately isotropic, so it does not
# describe a Chaetoceros chain, which is compact across its axis and up to
# twelve radii long down it. A plate key is a composed object; composing it
# by hand is the honest way to do it.
# Hand-set, then clamped to what actually fits. The hand-set value is the one
# that makes a row look right; the clamp is what stops a Chaetoceros chain --
# eight radii long and compact across -- from lying across the species name.
#
# THE CLAMP MEASURES RATHER THAN GUESSES. The first version clamped against
# EXTENT, which is the ecosystem's separation radius: isotropic by design,
# and describing a different thing entirely. For the copepod it read 1.8
# radii where the drawing reaches 1.5, so it was too tight; for a Chaetoceros
# chain it reads 8.4 where the drawing reaches rather more. Wrong in both
# directions, and neither error visible until something touched the type.
#
# So each species is drawn once at import, through a full turn of its own
# animation, into a scratch canvas -- and the furthest lit pixel from the
# centre is its reach. That is not an estimate of the silhouette, it is the
# silhouette. On the MCU the same measurement runs at build time and what
# ships is a table of eighteen numbers.
_KEY_R_WANT = {
    RADIOLARIAN: 13.0, CENTRIC: 15.0, PENNATE: 16.0, CHAIN: 5.2,
    CERATIUM: 12.0, COPEPOD: 15.0, TINTINNID: 13.0,
    COCCO: 14.0, FLAGELLATE: 10.5, THALASSIO: 5.4, RHIZO: 7.2,
    CORETHRON: 9.0, ACANTHARIA: 15.0, FORAM: 10.5, ORNITHO: 13.0,
    TRICHO: 9.0, SALP: 5.8, KRILL: 9.5,
}

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
# water does, and all of them below 1. Tunable in console.py under
# KEY PLATE, because "how much movement is too much on a thing being read"
# is a judgement by eye like every other number in this file's neighbourhood.
KEY_RATE = 1.00            # everything on the plate runs at this fraction of
                           # the water's already-slowed rate
KEY_YAW = 0.45             # helix yaw amplitude, against the water's
KEY_SURGE = 1.50           # fore-and-aft sway. Above 1 on purpose: the sway
                           # is what makes a specimen read as suspended in
                           # water rather than pinned to a card, and it is
                           # the cheapest thing on the plate that does.
KEY_SPIN_S = 40.0          # the base period of the slow roll, in seconds
KEY_BEAT = 0.60            # appendage beat rate

# Sway, per gait, as a multiple of KEY_SURGE. A copepod is *swimming* -- it
# rows, it lurches, it is the only thing on the plate under its own power in
# any visible way -- so it moves furthest. A helical swimmer surges with its
# corkscrew. A cruiser holds station. And a diatom, which has no say in
# anything, still rides the water: gently, and that gentleness is the point,
# because it is what tells you the difference between the two without a word
# being written.
SWAY = {"hop": 1.00, "helix": 0.55, "cruise": 0.30, "drift": 0.22}

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
def _roll(kind, t):
    """The slow roll every specimen has, swimmer or not.

    Three requirements, all from watching it: it has to change direction, it
    has to differ between species, and it has to apply to everything. A
    constant rotation is a turntable in a shop window -- it never arrives
    anywhere and you stop believing it after ten seconds.

    Two sinusoids whose periods do not divide into each other. The sum never
    repeats over any span anyone will watch, it reverses of its own accord at
    intervals that are not the same twice, and it is still completely
    deterministic -- no seed, no state, nothing to drift out of step when the
    plate scrolls a row off the screen and back on. The per-species factor
    comes from the kind constant itself, so every organism has its own rhythm
    and none of them had to be typed in."""
    p = KEY_SPIN_S * (0.70 + 0.11 * (kind % 7))
    return (0.55 * math.sin(2.0 * math.pi * t / p)
            + 0.30 * math.sin(2.0 * math.pi * t / (p * 1.618) + 1.1))


def specimen_pose(kind, t):
    slow = SWIM_SCALE * KEY_RATE
    ta = t * slow                                  # animal seconds
    gait = GAIT.get(kind)
    beat = BEAT_HZ.get(kind)
    ph = 2.0 * math.pi * beat * ta * KEY_BEAT if beat is not None else 0.0
    roll = _roll(kind, t)
    if gait == HELIX:
        f = HELIX_HZ[kind]
        yaw = HELIX_YAW[kind] * KEY_YAW
        hp = 2.0 * math.pi * f * ta
        # the corkscrew, seen edge-on: a yaw oscillation, and a surge a
        # quarter cycle out of phase so it reads as swimming rather than as
        # a windscreen wiper
        return (BASE_ANG + roll + yaw * math.sin(hp),
                0.32 * KEY_SURGE * SWAY["helix"] * math.cos(hp), hp)
    if gait == HOP:
        hp = 2.0 * math.pi * HOP_HZ[kind] * ta
        # one antennal stroke per hop, and a sway a quarter cycle behind it,
        # because the body follows the limbs rather than leading them
        return (BASE_ANG + roll,
                0.32 * KEY_SURGE * SWAY["hop"] * math.sin(hp - 1.4), hp)
    if gait == CRUISE:
        cp = 2.0 * math.pi * 0.35 * ta
        return (BASE_ANG + roll + 0.05 * KEY_YAW * math.sin(cp),
                0.32 * KEY_SURGE * SWAY["cruise"] * math.cos(cp * 0.5), ph)
    # Not a swimmer -- but not inert either. It is in water, and water moves,
    # so it rides: a slow roll on its own clock and a small sway on another,
    # neither of them the organism's doing. That is the whole difference
    # between a diatom and a copepod, said without a word.
    dp = 2.0 * math.pi * t / (KEY_SPIN_S * 1.9)
    return (BASE_ANG + roll,
            0.32 * KEY_SURGE * SWAY["drift"] * math.sin(dp), ph)


def _specimen(c, kind, cx, cy, seed=1, t=0.0):
    """One drawn individual, sized so every row occupies the same column.
    A stable seed per row keeps the specimen from shimmering between frames;
    the pose is the only thing allowed to change."""
    rng = random.Random(seed * 7919 + kind)
    g = Genome(kind, rng)
    r = KEY_R.get(kind, 14.0)
    ang, fwd, ph = specimen_pose(kind, t)
    # saturate rather than collide: the sway slider goes to 4x in the console
    # and the column does not, so past the reserved headroom the motion stops
    # growing instead of climbing into the name
    fwd = max(-SWAY_HEADROOM, min(SWAY_HEADROOM, fwd))
    dx = fwd * r * math.cos(ang)
    dy = fwd * r * math.sin(ang)
    if kind == COPEPOD:
        draw_copepod(c, cx + dx, cy + dy, r, ang, g, False, phase=ph)
    elif kind in ANIMATED:
        DRAW[kind](c, cx + dx, cy + dy, r, ang, g, phase=ph)
    else:
        DRAW[kind](c, cx + dx, cy + dy, r, ang, g)


def _measure_reach(kind, r=10.0, phases=8, pad=110):
    """How far the drawing actually goes, in radii, over its whole cycle."""
    c = Canvas(2 * pad, 2 * pad)
    g = Genome(kind, random.Random(7919 + kind))
    for i in range(phases):
        a = BASE_ANG + 2.0 * math.pi * i / phases
        ph = 2.0 * math.pi * i / phases
        if kind == COPEPOD:
            draw_copepod(c, pad, pad, r, a, g, False, phase=ph)
        elif kind in ANIMATED:
            DRAW[kind](c, pad, pad, r, a, g, phase=ph)
        else:
            DRAW[kind](c, pad, pad, r, a, g)
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
    return math.sqrt(far) / r


REACH = {k: _measure_reach(k) for k in _KEY_R_WANT}
KEY_R = {k: min(r, SPEC_HALF / max(REACH[k] + SWAY_HEADROOM, 0.5))
         for k, r in _KEY_R_WANT.items()}

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
    sc = fit_scale(track.voyage.title, W - 20)
    text(c, 10, y0, track.voyage.title, scale=sc)
    y = y0 + text_height(sc) + 6
    # wrapped, not cut at 24 characters. ANCHORED RIO DE LA PLATA
    # (15 APR 1578) truncated to fit loses the date, which is the half of the
    # line worth having.
    for ln in wrap(track.status(day), W - 20, maxlines=2):
        text(c, 10, y, ln, scale=T_MED)
        y += text_height(T_MED) + 3
    return y + 3


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

# THE SAME SHAPE AS THE MAP, FOR THE SAME REASON.
#
#     top      x        still
#     down     3x       moving
#     bottom   x        still
#     up       3x       moving
#     top      x        still
#
# Three rests and two moves, and the moves three times the rests -- so at a
# 270 s dwell that is 30 s reading the head of the list, ninety seconds
# travelling, 30 s at the foot, ninety back, and 30 s at the head again.
#
# The long travel is the point and it took a correction to get to. Short
# travels make the rests do all the reading, which means the middle of a long
# census is only ever seen flashing past. At ninety seconds the pan runs at
# about thirteen pixels a second and a row takes six seconds to cross, which
# is slow enough to read while it moves -- so every row gets read, and none
# of it moves fast enough to catch the eye of somebody who is not looking.
PAN_STILL = 1.0            # relative length of each of the three rests
PAN_MOVE = 3.0             # ... and of each of the two travels


def _pan(t_into, dwell, span):
    """Pixels to shift the list up, given how far into the plate's dwell we
    are.

    Down, then back up. A one-way pan ends with the list at the bottom and
    the top of it out of sight, so the plate spends its last moment showing
    the least interesting end and then cuts away -- and next time it appears
    it starts from the top again, so the transition is a jump. There and back
    leaves it where it started, and gives a visitor two passes at a list they
    may only have half read the first time.

    Eased at every rest, because a linear pan starts and stops with a visible
    jerk and a reversal without a rest reads as a bounce."""
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
    # REAL seconds, not simulated ones. eco.t is a staircase now -- it moves
    # once per simulated hour -- and a gait driven off a staircase does not
    # move at all in between.
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
    for i, (kind, n, mass, x) in enumerate(rows):
        ry = top - off + i * ROW_H
        if ry > bot or ry + ROW_H < top:
            continue                            # off the plate, skip the work
        cy = ry + ROW_H // 2
        avail = w - 10 - TEXT_X
        _specimen(canvas, kind, SPEC_X, cy, seed=i + 1, t=t)
        name = NAMES.get(kind, "?")
        nsc = fit_scale(name, avail)
        text(canvas, TEXT_X, ry + 5, name, scale=nsc)
        ty = ry + 5 + text_height(nsc) + 5
        # lo=T_MED, not lo=1: if a line ever outgrows its column the right
        # answer is to shorten the words, not to print them at a size that
        # defeats the point of this whole pass
        line = "%s %s" % (SIZES.get(kind, ""), GROUPS.get(kind, ""))
        text(canvas, TEXT_X, ty, line.strip(),
             scale=fit_scale(line, avail, hi=T_MED, lo=T_MED))
        by = ty + text_height(T_MED) + 10
        abundance_bar(canvas, TEXT_X, by, bar_w, x)
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
