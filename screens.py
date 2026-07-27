#!/usr/bin/env python3
"""
SCREENS  -  what is on the panel, and when.

Water is the resting state. Every so often it dissolves into the chart, and
later into the key plate, and back. The whole schedule is one table and one
counter, so on the MCU this is a few dozen bytes of state and a switch.

Two cadences:

    GALLERY   the default, and what the object is for. Roughly two per cent
              of the time is not water.
    EXHIBIT   for a room with people in it. A sixty-seven second cycle, forty
              per cent chrome. Reached by pressing the button, and it lapses
              back to GALLERY on its own after five minutes -- so the piece is
              contemplative by default and becomes explicable the moment
              somebody asks about it.

The timings are set by what each screen needs rather than by round numbers.
The map cannot go below about twelve seconds: the dolly is the entire point
of it, and it wants two seconds holding the globe so the eye registers Earth,
five to seven moving, and five to eight at chart scale to find the coast and
the ship. Any less and it reads as a flash rather than a move. The key plate
is static, so its duration is purely reading time -- five to seven rows at
roughly two seconds each, plus the voyage block.
"""

from drift import Canvas, W, H, render, View
from mapview import render_map, R_GLOBE, R_CHART, zoom_radius
from keyplate import render_key

WATER, MAP, KEY = range(3)

# Twice round per cycle. One appearance of each per hour is too few to catch
# -- a visitor who looks up at the wrong moment waits an hour for the chart --
# and it also wastes the fact that both interludes now END where they began,
# so a second run costs nothing structurally.
SEQUENCE = (WATER, MAP, WATER, KEY, WATER, MAP, WATER, KEY)


class Cadence:
    """THE CYCLE IS THE CONSTANT, AND THE WATER IS THE REMAINDER.

    Timing is set in one-hour cycles, because that is the unit a person in a
    room actually has: you walk past the thing twice in an evening and you
    want to have seen the chart. Within the hour the map appears twice and
    the key plate twice, so the longest anyone waits for either is about half
    an hour.

    The water duration is therefore *derived*, not typed. Lengthen the dolly
    and the water shortens to pay for it, and the hour stays an hour --
    which matters because the alternative is a table of five numbers that
    have to be re-added by hand every time one of them moves, and that table
    is wrong the first time somebody forgets."""

    __slots__ = ("cycle", "globe", "dolly", "chart", "key", "fade")

    def __init__(self, cycle, globe, dolly, chart, key, fade):
        self.cycle = cycle
        self.globe = globe
        self.dolly = dolly
        self.chart = chart
        self.key = key
        self.fade = fade

    @property
    def water(self):
        busy = (SEQUENCE.count(MAP) * self.duration(MAP)
                + SEQUENCE.count(KEY) * self.key)
        n = max(1, SEQUENCE.count(WATER))
        return max(20.0, (self.cycle - busy) / n)

    def duration(self, screen):
        if screen == WATER:
            return self.water
        if screen == KEY:
            return self.key
        # globe, in, chart, out, globe. Two holds on the Earth, one at each
        # end, so the interlude both opens and closes on it -- and the whole
        # move is 2 x globe + 2 x dolly + chart.
        return 2.0 * self.globe + 2.0 * self.dolly + self.chart


# The key plate got longer when the type got bigger, and longer again when
# the pan learned to come back. Fifteen seconds was right for a static list
# of eleven rows at 5 px. Ninety is two unhurried passes over a twelve-row
# list through a window five rows deep, plus three rests -- about four
# seconds a row on the way down and the same on the way up, which is reading
# pace rather than skimming pace.
#
# Ninety seconds is 4% of the GALLERY cycle. The water is still up for
# eighteen minutes at a stretch, which is the ratio that matters.
# Set by eye in tools/console.py rather than reasoned to. The move is much
# slower than the first guess: a minute to dolly in and a minute back out,
# with half-minute rests at each end, which makes the interlude three minutes
# long. That sounds extravagant until you notice it is 7% of a cycle whose
# water segments are eighteen minutes each -- and that a camera move you can
# watch without noticing it is a camera move has to be about this slow.
# globe 25, in 90, chart 40, out 90, globe 25 -> 270 s, four and a half
# minutes, of which two thirds is the dolly. The key plate is 270 s on the
# same shape (see PAN_MOVE in keyplate.py), which leaves 4 x 630 s of water
# and keeps the hour an hour.
#
# EXHIBIT keeps the ratios and compresses: it is for a room with people in it
# who will not stand there for four minutes.
GALLERY = Cadence(cycle=3600.0, globe=25.0, dolly=90.0, chart=40.0,
                  key=270.0, fade=1.5)
EXHIBIT = Cadence(cycle=900.0, globe=8.0, dolly=28.0, chart=12.0,
                  key=84.0, fade=1.0)

EXHIBIT_LAPSE = 300.0          # seconds before EXHIBIT falls back to GALLERY


def map_radius(t_into_map, cad):
    """Five phases: globe, in, chart, out, globe.

        globe   x        still
        in      0.75x    moving
        chart   x        still
        out     0.75x    moving
        globe   x        still

    The moves are much longer than the rests, and that is the correction
    that mattered. The first version made them shorter -- 30 s for the dolly
    -- and 30 s is not a slow zoom. It covers a nine-fold change of scale, so
    the rate is what decides it:

        dolly   peak rate   scale change in a 3 s glance
         30 s     11.9%/s     40%
         60 s      5.8%/s     18%
         90 s      3.8%/s     12%
        120 s      2.8%/s      9%

    "Does not move drastically while looked at" is a statement about the
    three-second column, and 40% is not it. At 90 s a glance sees about a
    tenth, which is on the edge of noticing -- and 90 s is still short enough
    that looking away and back finds a different picture. Film calls 2-4% a
    second a creep; this sits at the top of that.

    The two rests are deliberately NOT equal, which breaks the neat single-x
    formula on purpose. The chart has names, a coastline and the ship on it
    and rewards forty seconds. The globe, now that its labels wait for the
    zoom, is a still picture of the Earth and says what it has to say in
    twenty-five.

    It comes back rather than cutting. A one-way dolly ends at chart scale
    and then dissolves to water, so the last thing the interlude says is a
    close-up of a coastline with nowhere to put it, and the next appearance
    snaps to the globe with no explanation. Going out again spends the same
    thirty seconds saying where that coast was, and leaves the screen on the
    Earth -- a much better thing to dissolve to water from, because a globe
    and a panel of plankton are both wide, quiet images and a chart is not."""
    t = t_into_map
    if t < cad.globe:
        return R_GLOBE
    t -= cad.globe
    if t < cad.dolly:
        return zoom_radius(t / cad.dolly)
    t -= cad.dolly
    if t < cad.chart:
        return R_CHART
    t -= cad.chart
    if t < cad.dolly:
        return zoom_radius(max(0.0, 1.0 - t / cad.dolly))
    return R_GLOBE


class Rotation:
    """Where we are in the cycle. Advance it with real seconds elapsed."""

    __slots__ = ("cad", "i", "t", "exhibit_left")

    def __init__(self, cadence=GALLERY):
        self.cad = cadence
        self.i = 0
        self.t = 0.0
        self.exhibit_left = 0.0

    @property
    def screen(self):
        return SEQUENCE[self.i]

    @property
    def prev_screen(self):
        return SEQUENCE[(self.i - 1) % len(SEQUENCE)]

    def advance(self, dt):
        if self.exhibit_left > 0.0:
            self.exhibit_left -= dt
            if self.exhibit_left <= 0.0:
                self.cad = GALLERY
                self.exhibit_left = 0.0
        self.t += dt
        while self.t >= self.cad.duration(self.screen):
            self.t -= self.cad.duration(self.screen)
            self.i = (self.i + 1) % len(SEQUENCE)

    def skip(self):
        """The button. Jump straight to the next screen, and drop into
        EXHIBIT for a while because somebody is evidently watching."""
        self.i = (self.i + 1) % len(SEQUENCE)
        self.t = 0.0
        self.cad = EXHIBIT
        self.exhibit_left = EXHIBIT_LAPSE

    def fade(self):
        """(f, from_screen) while dissolving in, else None.

        The fade eats the head of each segment rather than sitting between
        segments, so the cycle length is exactly the sum of the durations and
        there is nothing to book-keep."""
        if self.t < self.cad.fade:
            return self.t / self.cad.fade, self.prev_screen
        return None


# --------------------------------------------------------------------------

def draw_screen(canvas, screen, t_into, eco, track, coast, view, cad):
    if screen == MAP:
        render_map(canvas, coast, track, eco.now, map_radius(t_into, cad),
                   chrome=view.plate)
    elif screen == KEY:
        # the plate pans over its whole dwell, so it needs to know how long
        # that is and how far in we are. Both come from the cadence, so the
        # pan speed follows the schedule rather than being tuned against it.
        render_key(canvas, eco, track, eco.now, chrome=view.plate,
                   t_into=t_into, dwell=cad.key)
    else:
        render(eco, canvas, view, track, eco.now)


class Compositor:
    """Holds the two scratch buffers a dissolve needs. Allocated once, which
    is the only way it can work on the MCU: 240x400 at 1 bit is 12 kB packed,
    so two spare buffers is 24 kB out of 520."""

    __slots__ = ("a", "b")

    def __init__(self):
        self.a = Canvas(W, H)
        self.b = Canvas(W, H)

    def frame(self, canvas, rot, eco, track, coast, view):
        cad = rot.cad
        fade = rot.fade()
        if fade is None:
            draw_screen(canvas, rot.screen, rot.t, eco, track, coast, view, cad)
            return
        f, prev = fade
        # the outgoing screen is frozen at its last moment, which is correct:
        # it has finished saying what it had to say
        draw_screen(self.a, prev, cad.duration(prev), eco, track, coast,
                    view, cad)
        draw_screen(self.b, rot.screen, rot.t, eco, track, coast, view, cad)
        canvas.blend_from(self.a, self.b, f)
