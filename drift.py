#!/usr/bin/env python3
"""
DRIFT  -  the fish of a voyage, on a 1-bit reflective panel.

A depth section of the water the ship is sailing through, from the surface to
a thousand metres, with the fish that live in it. Renders at the EXACT
resolution and bit depth of the target hardware, then upscales
nearest-neighbour so what you see is what the panel will show. No
anti-aliasing, no greyscale, no cheating.

Architecture is deliberately split so the port to the ESP32-S3 is mechanical:

    Canvas       ~200 lines of integer raster primitives.  Reimplement these
                 six functions in C and everything above them ports unchanged.
    Environment  pure float maths, no state.  Ports as-is.
    fish.py      the roster and the envelope.  Pure data and four
                 comparisons.  Ports as-is.
    draw.py      procedural morphology.  Canvas only.  Ports as-is.
    Ecosystem    who is in this water, and how they swim.  Ports as-is.
    preview()    pygame.  Thrown away on the port.

Run:
    pip install pygame numpy pillow
    python3 drift.py
    python3 drift.py beagle     # or any key in voyage.VOYAGES

Keys:
    space       pause
    wheel       speed, continuously (shift+wheel for coarse jumps)
    1 2 3 4 5   speed presets: real time / 1 min / 1 hr / 6 hr / 1 day per sec
    m           next screen now, and switch to the EXHIBIT cadence
    v           next voyage
    c           CLEAN MODE -- fish and water only, all chrome hidden
    h           toggle HUD
    p           toggle the footer / map and key plate chrome
    n           toggle the seabed and the depth scale
    s           save a PNG
    r           reseed the world
    esc         quit

Headless (writes stills, no pygame needed):
    python3 drift.py --stills out/
"""

import math
import random
import sys

import draw
import fish as F

# --------------------------------------------------------------------------
# 1. CONFIG
# --------------------------------------------------------------------------

W, H = 300, 400            # panel resolution, portrait. The 4.2in RLCD on
                           # the ESP32-S3-RLCD-4.2, which is the panel this
                           # is built for.
PANEL_DIAG_IN = 4.2        # the physical panel, for true-size preview only
SCALE = 0.9138             # preview upscale, and this value is TRUE PHYSICAL
                           # SIZE on a 27in 1440p monitor (108.79 ppi) for a
                           # 4.2in 300x400 panel at 119.05 ppi. Fractional, so
                           # the preview resamples rather than replicating --
                           # see the note in preview(). tools/console.py has a
                           # ruler that computes this for any monitor; set it
                           # to 2 for a big blocky view instead.
TARGET_FPS = 20            # preview frame rate.

LAT = 52.0800              # Melbourn, when there is no track
LON = 0.0200

# --------------------------------------------------------------------------
# THE DEPTH AXIS, AND WHY IT IS LOGARITHMIC
# --------------------------------------------------------------------------
#
# The plankton column was 55 m, linear, magnified about two hundred times.
# This is a thousand metres, reduced about two and a half thousand times, and
# the axis has to change shape as well as scale.
#
# Fish depth distributions span three orders of magnitude. On a linear
# thousand-metre axis the entire sunlit ocean -- every sardine, tuna, flying
# fish and shark on the roster -- is squeezed into the top fifth of the panel
# and the remaining four fifths hold a scattering of mesopelagics. That is a
# true picture of the volume and a useless picture of the life.
#
# On a log axis the top 200 m gets half the panel and the mesopelagic gets the
# other half. Z0 is chosen to make that exactly true:
#
#     log1p(200/Z0) / log1p(1000/Z0) = 1/2   ->   Z0 = 200/3
#
# which is worth writing as an identity rather than a tuned constant, because
# "the sunlit zone gets half the panel" is the decision and 66.7 is only its
# consequence.
Z_MAX = 1000.0             # metres of water column mapped to the panel height
Z0 = 200.0 / 3.0           # the log axis knee -- see above
Z_SUN = 200.0              # the epipelagic boundary, drawn as a hairline

MAX_AGENTS = 34            # render cost lives here
MESO_N = 10                # mesopelagic slots when the water is fully
                           # suitable for them. Near-constant by design: this
                           # community is the same under a gyre and under an
                           # upwelling, which is the whole reason it is
                           # allocated separately from the sunlit half.
N_FLOOR = 6                # THE PANEL IS NEVER BARE, and in a gyre this is
                           # not a fallback: the mesopelagic is never empty,
                           # lanternfish are the most abundant vertebrates on
                           # Earth, and six fish in barren water is what that
                           # water actually holds.

# --- how many, and of what ------------------------------------------------
#
# Suitability says who CAN live here. It does not say how many, and two real
# facts set that:
#
#   1. Trophic transfer is about ten per cent per level, so each step up the
#      food chain is an order of magnitude less biomass. This is the whole of
#      the trophic coupling: a marlin is rare in barren water because there is
#      nothing beneath it, without any rule mentioning marlin or barren water.
#   2. For a given biomass, larger animals are fewer -- numbers go as 1/mass,
#      and mass as length cubed.
#
# Together those give numbers proportional to 10^-(T-2.5) / L^3, and applied
# literally that is a ratio of about 5,800 anchoveta to one skipjack. Which is
# true, and unwatchable: the skipjack would appear about twice a voyage.
#
# So the ratio is COMPRESSED, by a power, exactly as the plankton model
# compressed its capacity term and for the same reason. At ABUND_EXP = 0.22
# the same pair comes out near seven to one -- the ordering is preserved,
# every fish is rarer than everything it eats, and a skipjack turns up often
# enough to be seen. It is a deliberate lie about magnitude and an honest one
# about direction, and the key plate's abundance bar is where the magnitude
# gets told properly.
ABUND_EXP = 0.22
TROPHIC_REF = 2.5          # the base of the pyramid, near a pure planktivore
CAP_EXP = 0.45             # n_visible goes as capacity^0.45
CAP_SCALE = 5.4            # SET BY THE TWO ENDS OF THE TRACK, not by taste.
                           # The South Pacific gyre and the Humboldt are the
                           # poorest and richest water Drake crosses, and
                           # their capacities come out at 1.9 and 37.8, so
                           # capacity^0.45 puts them 4.5-fold apart. Scaling
                           # that so the Humboldt fills the panel at 32 fish
                           # leaves the gyre at 7 -- which is the ratio the
                           # panel can actually show, and CAP_SCALE is what
                           # it takes. At 21.0 both ends clipped at MAX_AGENTS
                           # and the whole voyage looked identically full.

# --- how fast the community changes ---------------------------------------
#
# The ship makes 80 to 180 km on a good day and the assemblage is recomputed
# from the water continuously, so composition tracks position for free. What
# does not come for free is the RATE: snapping the population to a new target
# the instant the envelope changes would make fish blink in and out as the
# ship crosses a front.
#
# TURNOVER_D is the e-folding time of that relaxation. At 1.6 days the
# community has substantially changed after a good day's sail and still holds
# together while you watch it, which is the same trade the plankton model's
# FLUSH_PER_100KM was making.
TURNOVER_D = 1.6
ECO_DT = 1.0 / 24.0         # the ecology's own clock: one simulated hour
EMERGE_D = 0.5             # days for a new arrival to fade in
DIE_D = 0.4                # days for a departure to fade out

# --- productivity ---------------------------------------------------------
#
# With the NPZ model gone, productivity is an ENVIRONMENTAL FIELD rather than
# a simulated population: nitrate from flash, times light, times the iron
# ceiling. One Monod, one product, no state -- and it does the job the whole
# plankton model was doing for the purposes that remain, which is the reason
# deleting that model simplified things rather than complicating them.
N_FALLBACK = 13.0          # the nitrate reservoir with no ocean file
K_PROD = 8.0               # Monod half-saturation on the nitrate reservoir
L_SAT = 0.30               # daily mean irradiance at which light stops
                           # limiting. Above this, productivity is nutrients.

# --- motion ---------------------------------------------------------------
#
# Swimming runs at REAL time, not simulated time -- the same decision, for the
# same reason, as the plankton column. The speed control spans six orders of
# magnitude and swimming does not: scaled with the calendar, a skipjack moves
# the width of the panel between frames at 1 DAY/SEC and stops being an animal.
#
# The ecology is unaffected, because with presence decided by an envelope
# there is no equation that reads a fish's x coordinate.
SWIM_SCALE = 0.22          # fraction of true speed shown. Higher than the
                           # plankton's 0.09: a tuna at 2 BL/s and 45 px long
                           # crosses the panel in three seconds at full speed,
                           # which is a glimpse rather than a fish.
TURN_SCALE = 1.0           # multiplier on every TURN_TAU
BODY_TAU = 0.45            # seconds for the body to swing to a new heading
SHOAL_TAU = 30.0           # seconds before a shoal's collective heading
                           # decorrelates. Long: a shoal commits.
VERT_DAMP = 0.18           # how much of a fish's swimming goes into depth.
                           # Low on purpose -- the depth axis belongs to the
                           # diel migration and the species' own band, and a
                           # tuna that could cross the thermocline in a second
                           # would make nonsense of both.


# --------------------------------------------------------------------------
# 2. CANVAS  -  1-bit framebuffer, integer primitives
# --------------------------------------------------------------------------

class Canvas:
    """One byte per pixel here for speed and clarity. On the MCU this becomes
    a packed 1bpp buffer of W*H/8 bytes -- 12 kB at 240x400 -- and only these
    primitives need rewriting."""

    __slots__ = ("w", "h", "buf", "cx0", "cy0", "cx1", "cy1")

    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.buf = bytearray(w * h)
        self.cx0 = self.cy0 = 0
        self.cx1, self.cy1 = w, h          # exclusive

    def clip(self, x0=None, y0=None, x1=None, y1=None):
        """Set the drawable rectangle, or reset it with no arguments.

        Four integers and a comparison per pixel, which is nothing in C, and
        it is what lets a list scroll under a fixed heading without the list
        drawing over it. Every primitive goes through px() or line(), so
        honouring it in those two places covers the whole library."""
        self.cx0 = 0 if x0 is None else max(0, int(x0))
        self.cy0 = 0 if y0 is None else max(0, int(y0))
        self.cx1 = self.w if x1 is None else min(self.w, int(x1))
        self.cy1 = self.h if y1 is None else min(self.h, int(y1))

    def clear(self):
        # bytearray slice assignment is the fastest memset available
        self.buf[:] = b"\x00" * (self.w * self.h)

    def px(self, x, y):
        x = int(x); y = int(y)
        if self.cx0 <= x < self.cx1 and self.cy0 <= y < self.cy1:
            self.buf[y * self.w + x] = 1

    def clear_rect(self, x, y, w, h):
        """Knock a hole in whatever is already drawn.

        A caption over a chart is unreadable if the coastline runs through
        the letters, and on 1 bit there is no tint to put behind it -- only
        paper or ink. So the label clears its own ground first, which is what
        a printed chart does with a legend box and for the same reason."""
        x0 = max(int(x), self.cx0); y0 = max(int(y), self.cy0)
        x1 = min(int(x) + int(w), self.cx1); y1 = min(int(y) + int(h), self.cy1)
        if x1 <= x0 or y1 <= y0:
            return
        row = b"\x00" * (x1 - x0)
        bw = self.w
        for yy in range(y0, y1):
            self.buf[yy * bw + x0:yy * bw + x1] = row

    def fill_rect(self, x, y, w, h):
        """Solid block. Only the scaled font needs it, and it needs it a lot
        -- a 15x21 glyph at scale 3 is 105 of these -- so it is worth having
        as a primitive rather than as nine calls to px()."""
        x0 = max(int(x), self.cx0); y0 = max(int(y), self.cy0)
        x1 = min(int(x) + int(w), self.cx1); y1 = min(int(y) + int(h), self.cy1)
        if x1 <= x0 or y1 <= y0:
            return
        row = b"\x01" * (x1 - x0)
        bw = self.w
        for yy in range(y0, y1):
            self.buf[yy * bw + x0:yy * bw + x1] = row

    def line(self, x0, y0, x1, y1):
        x0 = int(x0); y0 = int(y0); x1 = int(x1); y1 = int(y1)
        w = self.w; h = self.h; buf = self.buf
        # cheap whole-line reject
        if (x0 < 0 and x1 < 0) or (x0 >= w and x1 >= w):
            return
        if (y0 < 0 and y1 < 0) or (y0 >= h and y1 >= h):
            return
        cx0 = self.cx0; cy0 = self.cy0; cx1 = self.cx1; cy1 = self.cy1
        dx = x1 - x0
        dy = y1 - y0
        sx = 1 if dx >= 0 else -1
        sy = 1 if dy >= 0 else -1
        dx = dx if dx >= 0 else -dx
        dy = dy if dy >= 0 else -dy
        err = dx - dy
        while True:
            if cx0 <= x0 < cx1 and cy0 <= y0 < cy1:
                buf[y0 * w + x0] = 1
            if x0 == x1 and y0 == y1:
                break
            e2 = err + err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    def polyline(self, pts, close=False):
        n = len(pts)
        if n < 2:
            return
        for i in range(n - 1):
            a = pts[i]; b = pts[i + 1]
            self.line(a[0], a[1], b[0], b[1])
        if close:
            self.line(pts[-1][0], pts[-1][1], pts[0][0], pts[0][1])

    def circle(self, cx, cy, r):
        """Midpoint circle. Crisper than parametric sampling at small radii."""
        cx = int(cx); cy = int(cy); r = int(r)
        if r < 1:
            self.px(cx, cy)
            return
        x = r; y = 0; err = 1 - r
        while x >= y:
            for sx, sy in ((x, y), (y, x), (-x, y), (-y, x),
                           (-x, -y), (-y, -x), (x, -y), (y, -x)):
                self.px(cx + sx, cy + sy)
            y += 1
            if err < 0:
                err += 2 * y + 1
            else:
                x -= 1
                err += 2 * (y - x) + 1

    def arc(self, cx, cy, r, a0, a1, steps=None):
        if steps is None:
            steps = max(4, int(abs(a1 - a0) * r * 0.6))
        pts = []
        for i in range(steps + 1):
            a = a0 + (a1 - a0) * i / steps
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        self.polyline(pts)

    def ellipse(self, cx, cy, rx, ry, rot=0.0, steps=None):
        if steps is None:
            steps = max(8, int((rx + ry) * 0.9))
        ca = math.cos(rot); sa = math.sin(rot)
        pts = []
        for i in range(steps):
            a = 2 * math.pi * i / steps
            px = rx * math.cos(a); py = ry * math.sin(a)
            pts.append((cx + px * ca - py * sa, cy + px * sa + py * ca))
        self.polyline(pts, close=True)

    def blend_from(self, a, b, f):
        """Ordered-dither dissolve: f=0 is all of a, f=1 is all of b.

        A crossfade needs greys, and there are none. So the fade happens in
        *area* instead: an 8x8 Bayer matrix decides, per pixel, which of the
        two images to take, and raising the threshold moves pixels across in
        the scattered order the matrix defines. It looks like an engraving
        being replaced rather than a screen wiping, which is the whole reason
        to do it this way rather than a hard cut.

        This is a framebuffer operation and so it belongs to Canvas, which
        means it belongs to the C layer: on the MCU it is a loop over 12 kB of
        packed 1bpp with a threshold lookup, and costs nothing. Here it is
        96,000 Python iterations a frame, so the preview takes the numpy
        path -- exactly like the blit."""
        thr = f * 64.0
        w, h = self.w, self.h
        try:
            import numpy as np
        except ImportError:
            np = None
        if np is not None:
            m = np.asarray(BAYER8, dtype=np.uint8)
            mask = np.tile(m, ((h + 7) // 8, (w + 7) // 8))[:h, :w] < thr
            av = np.frombuffer(bytes(a.buf), dtype=np.uint8).reshape(h, w)
            bv = np.frombuffer(bytes(b.buf), dtype=np.uint8).reshape(h, w)
            self.buf[:] = np.where(mask, bv, av).tobytes()
            return
        ab, bb, db = a.buf, b.buf, self.buf
        for y in range(h):
            row = y * w
            br = BAYER8[y & 7]
            for x in range(w):
                i = row + x
                db[i] = bb[i] if br[x & 7] < thr else ab[i]

    def rect(self, x0, y0, x1, y1):
        self.line(x0, y0, x1, y0)
        self.line(x1, y0, x1, y1)
        self.line(x1, y1, x0, y1)
        self.line(x0, y1, x0, y0)


# 8x8 ordered dither, values 0..63. The classic recursive Bayer matrix: any
# threshold on it scatters the chosen pixels as evenly as possible, which is
# why a dissolve driven by it reads as a texture changing rather than a
# pattern sweeping across.
BAYER8 = (
    ( 0, 32,  8, 40,  2, 34, 10, 42),
    (48, 16, 56, 24, 50, 18, 58, 26),
    (12, 44,  4, 36, 14, 46,  6, 38),
    (60, 28, 52, 20, 62, 30, 54, 22),
    ( 3, 35, 11, 43,  1, 33,  9, 41),
    (51, 19, 59, 27, 49, 17, 57, 25),
    (15, 47,  7, 39, 13, 45,  5, 37),
    (63, 31, 55, 23, 61, 29, 53, 21),
)


# --- tiny 3x5 font, column-major, bit 0 = top row -------------------------

FONT = {
    "0": (31, 17, 31), "1": (2, 31, 0),  "2": (25, 21, 23), "3": (17, 21, 31),
    "4": (7, 4, 31),   "5": (23, 21, 29), "6": (31, 21, 29), "7": (1, 1, 31),
    "8": (31, 21, 31), "9": (23, 21, 31),
    "A": (31, 5, 31),  "B": (31, 21, 10), "C": (31, 17, 17), "D": (31, 17, 14),
    "E": (31, 21, 17), "F": (31, 5, 1),   "G": (31, 17, 29), "H": (31, 4, 31),
    "I": (17, 31, 17), "J": (24, 16, 31), "K": (31, 4, 27),  "L": (31, 16, 16),
    "M": (31, 3, 31),  "N": (31, 6, 31),  "O": (31, 17, 31), "P": (31, 5, 7),
    "Q": (15, 9, 23),  "R": (31, 5, 23),  "S": (23, 21, 29), "T": (1, 31, 1),
    "U": (31, 16, 31), "V": (15, 16, 15), "W": (31, 24, 31), "X": (27, 4, 27),
    "Y": (3, 28, 3),   "Z": (25, 21, 19),
    " ": (0, 0, 0),  ".": (0, 16, 0),  ",": (0, 24, 0),  "-": (4, 4, 4),
    ":": (0, 10, 0), "/": (16, 4, 1),  "'": (0, 3, 0),   "\xb0": (3, 3, 0),
    "+": (4, 14, 4), "(": (14, 17, 0), ")": (0, 17, 14),
}


# --- 5x7 font, the one you can actually read ------------------------------
#
# The 3x5 above is 5 pixels tall, which on a 119 ppi panel is 1.07 mm. It was
# fine when the only text was a debug HUD nobody was meant to read from a
# sofa. It is not fine as the only writing on the object.
#
# Written as pictures rather than as numbers because a font typed as column
# bitmasks cannot be reviewed -- you can only run it and squint. These
# compile to the same five column bytes per glyph at import, and on the MCU
# the compile happens at build time and what ships is the same const array.
_G7 = (
    ("0", ".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."),
    ("1", "..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."),
    ("2", ".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"),
    ("3", "#####", "...#.", "..#..", "...#.", "....#", "#...#", ".###."),
    ("4", "...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    ("5", "#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    ("6", "..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."),
    ("7", "#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."),
    ("8", ".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    ("9", ".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."),
    ("A", ".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    ("B", "####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    ("C", ".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."),
    ("D", "###..", "#..#.", "#...#", "#...#", "#...#", "#..#.", "###.."),
    ("E", "#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    ("F", "#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    ("G", ".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".####"),
    ("H", "#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    ("I", ".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."),
    ("J", "..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."),
    ("K", "#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    ("L", "#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    ("M", "#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    ("N", "#...#", "#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#"),
    ("O", ".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    ("P", "####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    ("Q", ".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"),
    ("R", "####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    ("S", ".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    ("T", "#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    ("U", "#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    ("V", "#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    ("W", "#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"),
    ("X", "#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"),
    ("Y", "#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    ("Z", "#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"),
    (" ", ".....", ".....", ".....", ".....", ".....", ".....", "....."),
    (".", ".....", ".....", ".....", ".....", ".....", ".##..", ".##.."),
    (",", ".....", ".....", ".....", ".....", ".##..", ".##..", ".#..."),
    (":", ".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."),
    (";", ".....", ".##..", ".##..", ".....", ".##..", ".#...", "#...."),
    ("'", ".#...", ".#...", ".....", ".....", ".....", ".....", "....."),
    ('"', "#.#..", "#.#..", ".....", ".....", ".....", ".....", "....."),
    ("-", ".....", ".....", ".....", "#####", ".....", ".....", "....."),
    ("/", "....#", "...#.", "..#..", "..#..", ".#...", "#....", "#...."),
    ("\xb0", ".##..", "#..#.", ".##..", ".....", ".....", ".....", "....."),
    ("(", "..#..", ".#...", "#....", "#....", "#....", ".#...", "..#.."),
    (")", "..#..", "...#.", "....#", "....#", "....#", "...#.", "..#.."),
    ("+", ".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."),
    ("\xd7", ".....", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "....."),
    (">", ".....", ".#...", "..#..", "...#.", "..#..", ".#...", "....."),
    ("<", ".....", "...#.", "..#..", ".#...", "..#..", "...#.", "....."),
    ("=", ".....", ".....", "#####", ".....", "#####", ".....", "....."),
    ("?", ".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#.."),
    ("!", "..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."),
    ("%", "##..#", "##..#", "...#.", "..#..", ".#...", "#..##", "#..##"),
)


def _compile7(rows):
    cols = []
    for c in range(5):
        bits = 0
        for r in range(7):
            if rows[r][c] == "#":
                bits |= 1 << r
        cols.append(bits)
    return tuple(cols)


# A font is (glyphs, width, height). Two of them: the 3x5 for anything that
# must be tiny, and the 5x7 for everything a person is meant to read.
FONT3 = ({k: v for k, v in FONT.items()}, 3, 5)
FONT7 = ({ch: _compile7(rows) for ch, *rows in _G7}, 5, 7)

# Legibility. A cap height wants to be roughly 1/250 of the viewing distance
# to be comfortable, so at a metre that is 4 mm and at half a metre 2 mm. On
# a 119 ppi panel, 7 px is 1.5 mm, 14 px is 3.0 and 21 px is 4.5.
#
# These are set by eye like SWIM_SCALE and TARGET_FPS -- the arithmetic gives
# the bracket and the room gives the answer -- so they are tunable in
# tools/console.py rather than argued for here.
T_BIG = 3                  # 15 x 21 px, cap 4.5 mm. Names, and the one
                           # number a passer-by should be able to read.
T_MED = 2                  # 10 x 14 px, cap 3.0 mm. Everything else.


def text(canvas, x, y, s, spacing=1, scale=T_MED, font=None, alpha=1.0):
    """Returns the x cursor after drawing, so labels can be chained.

    `scale` replicates each font pixel into a scale x scale block, which is
    the only enlargement that suits a 1-bit panel: anything smoother needs
    grey it does not have.

    `alpha` below 1 thins the letterforms through the same 8x8 ordered dither
    the screen dissolves use. It is not antialiasing -- there is no grey to
    antialias with -- it is a texture getting denser, and it is how writing
    arrives on the chart as the camera moves in rather than appearing all at
    once like a caption card."""
    glyphs, gw, gh = font or FONT7
    blank = glyphs[" "]
    step = (gw + spacing) * scale
    thr = int(alpha * 64.0)
    if thr <= 0:
        return x + step * len(s)
    solid = thr >= 64
    for ch in s.upper():
        g = glyphs.get(ch, blank)
        for col in range(gw):
            bits = g[col]
            if not bits:
                continue
            for row in range(gh):
                if not (bits & (1 << row)):
                    continue
                px0 = x + col * scale
                py0 = y + row * scale
                if solid and scale > 1:
                    canvas.fill_rect(px0, py0, scale, scale)
                elif solid:
                    canvas.px(px0, py0)
                else:
                    for dy in range(scale):
                        for dx in range(scale):
                            xx = int(px0) + dx
                            yy = int(py0) + dy
                            if BAYER8[yy & 7][xx & 7] < thr:
                                canvas.px(xx, yy)
        x += step
    return x


def text_width(s, spacing=1, scale=T_MED, font=None):
    _, gw, _ = font or FONT7
    return len(s) * ((gw + spacing) * scale) - spacing * scale


def text_height(scale=T_MED, font=None):
    _, _, gh = font or FONT7
    return gh * scale


def label(canvas, x, y, s, scale=None, spacing=1, font=None, pad=3,
          alpha=1.0):
    """Text with its own ground cleared. Returns the x cursor.

    Everything written over the chart goes through this. Over the water it
    is unnecessary and harmless; over a coastline it is the difference
    between a caption and a smudge."""
    scale = T_MED if scale is None else scale
    if alpha <= 0.02:
        return x
    w = text_width(s, spacing, scale, font)
    h = text_height(scale, font)
    canvas.clear_rect(x - pad, y - pad, w + 2 * pad, h + 2 * pad)
    return text(canvas, x, y, s, spacing, scale, font, alpha)


def trim(s, avail, scale=None, spacing=1, font=None):
    """As much of `s` as fits, cut at a word boundary if there is one near
    the end. Truncation is better than overflow and much better than
    shrinking: a line that runs off the panel loses its last word silently,
    and a line that shrinks to fit loses all of them."""
    scale = T_MED if scale is None else scale
    _, gw, _ = font or FONT7
    step = (gw + spacing) * scale
    n = max(0, int((avail + spacing * scale) // step))
    if n >= len(s):
        return s
    cut = s[:n]
    sp = cut.rfind(" ")
    return cut[:sp] if sp > n - 5 else cut


def wrap(s, avail, scale=None, spacing=1, font=None, maxlines=2):
    """Break at spaces to fit a column, up to `maxlines`, then trim.

    Trimming alone was not good enough: ANCHORED RIO DE LA PLATA cut to fit
    reads "ANCHORED RIO DE LA", which is not a shorter version of the truth
    but a different and meaningless one. Two lines cost fourteen pixels and
    say the whole thing."""
    scale = T_MED if scale is None else scale
    words = s.split()
    lines, cur = [], ""
    for wd in words:
        t = (cur + " " + wd).strip()
        if cur and text_width(t, spacing, scale, font) > avail:
            lines.append(cur)
            cur = wd
            if len(lines) == maxlines:
                break
        else:
            cur = t
    if cur and len(lines) < maxlines:
        lines.append(cur)
    return [trim(ln, avail, scale, spacing, font) for ln in lines] or [""]


def fit_scale(s, avail, spacing=1, font=None, hi=None, lo=1):
    """The largest scale at which `s` fits in `avail` pixels.

    Species names run from SALPA to COSCINODISCUS and the column is one
    width, so either the layout is designed around the longest name -- which
    wastes the plate on every other row -- or the type shrinks to fit. This
    is the second, and it is what a real plate does too."""
    hi = T_BIG if hi is None else hi
    for sc in range(hi, lo - 1, -1):
        if text_width(s, spacing, sc, font) <= avail:
            return sc
    return lo


# --------------------------------------------------------------------------
# 3. ENVIRONMENT  -  astronomy, light, mixing.  Stateless.
# --------------------------------------------------------------------------

def solar_elevation(day_of_year, hour_utc, lat=LAT, lon=LON):
    """NOAA low-precision solar position. Good to a fraction of a degree,
    which is far more than this needs."""
    g = 2 * math.pi / 365.0 * (day_of_year - 1 + (hour_utc - 12) / 24.0)
    decl = (0.006918
            - 0.399912 * math.cos(g) + 0.070257 * math.sin(g)
            - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
            - 0.002697 * math.cos(3 * g) + 0.001480 * math.sin(3 * g))
    eqtime = 229.18 * (0.000075
                       + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                       - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    true_solar = (hour_utc * 60.0 + eqtime + 4.0 * lon) % 1440.0
    ha = math.radians(true_solar / 4.0 - 180.0)
    la = math.radians(lat)
    sin_elev = (math.sin(la) * math.sin(decl)
                + math.cos(la) * math.cos(decl) * math.cos(ha))
    return math.asin(max(-1.0, min(1.0, sin_elev)))


class Environment:
    """Everything the ecosystem knows about the physical world.

    In the finished object, `cloud`, `temp_anomaly` and `storm` get replaced
    by the real sensor package: a light sensor on the front, and a BME280 for
    temperature and pressure. Until then they are a plausible fiction."""

    def __init__(self, rng, track=None, ocean=None):
        self.rng = rng
        self.track = track          # None -> stand still at Melbourn
        self.ocean = ocean          # None -> the latitudinal stopgap
        self.cloud = 0.5
        self.storm = 0.0
        self.temp_anomaly = 0.0
        self._light_day = -1
        self._light_mean = 0.0

    def where(self, t_days):
        if self.track is None:
            return LAT, LON
        return self.track.position(t_days)

    # -- the real ocean ----------------------------------------------------
    #
    # Every one of these falls back to the stopgap when there is no ocean
    # file, so drift.py still runs standalone and the seasonal-cycle test
    # still means something.

    def deep_nitrate(self, t_days):
        """The reservoir below the nutricline, which is what actually sets
        how productive a patch of ocean can be.

        Derived from WOA surface nitrate rather than used directly: the
        surface value is what is left after the community has drawn it down,
        so it understates supply. Scaling it is cruder than carrying a real
        depth profile and it gets the ordering right, which is what matters.

        The floor matters more than the slope. At a floor of 2.0 the gyres
        still bloomed, because tropical warmth roughly triples the growth
        rate and 2 mmol is plenty to feed on. Real gyre surface nitrate is
        two orders below that. Dropping the floor to 0.3 is what finally
        makes an oligotrophic gyre behave like one."""
        if self.ocean is None:
            return N_FALLBACK
        la, lo = self.where(t_days)
        n = self.ocean.nitrate(la, lo, t_days)
        if n is None:
            return N_FALLBACK
        return max(0.3, min(30.0, 0.3 + 2.6 * n))

    def iron(self, t_days):
        """0..1, applied by Liebig against the nitrogen term. This is the one
        field that has to be here rather than emergent: without it the model
        draws down the Southern Ocean's twenty-odd micromolar of nitrate and
        blooms, in the stretch of water most famous for not blooming."""
        if self.ocean is None:
            return 1.0
        la, lo = self.where(t_days)
        return self.ocean.iron(la, lo)

    def shelf_km(self, t_days):
        if self.ocean is None:
            return 200.0
        la, lo = self.where(t_days)
        return self.ocean.shelf_km(la, lo)

    def hemisphere_doy(self, t_days):
        """Day of year, flipped in the southern hemisphere.

        The cheapest possible way to make the voyage reach the water, and the
        most visible: everything seasonal in this model is phased off a day
        number, so offsetting that number by half a year below the equator
        gives correct southern seasons for free. Drake crossed the line four
        times, so the piece catches four reversals -- and two spring blooms in
        opposite hemispheres in the same voyage year.

        This is a stopgap. Stage 3 replaces it with real climatology, at which
        point the hemisphere handles itself."""
        doy = t_days % 365.25
        lat, _ = self.where(t_days)
        if lat < 0.0:
            doy = (doy + 182.625) % 365.25
        return doy

    def step(self, dt_days):
        r = self.rng
        # cloud does a slow random walk, bounded
        self.cloud += r.gauss(0, 0.9) * dt_days
        self.cloud = max(0.05, min(0.95, self.cloud))
        # storms: rare, sharp onset, exponential decay
        if r.random() < 0.09 * dt_days:
            self.storm = min(1.0, self.storm + r.uniform(0.4, 1.0))
        self.storm *= math.exp(-dt_days / 2.5)
        self.temp_anomaly += r.gauss(0, 0.8) * dt_days
        self.temp_anomaly = max(-2.5, min(2.5, self.temp_anomaly))

    def surface_light(self, t_days):
        """Normalised 0..1 irradiance just below the surface, at the ship.

        Not flipped by hemisphere -- the real solar geometry already handles
        that, because it takes the actual latitude. This is the one seasonal
        term in the model that was correct all along and just needed telling
        where it was."""
        doy = (t_days % 365.25) + 1
        hour = (t_days % 1.0) * 24.0
        lat, lon = self.where(t_days)
        elev = solar_elevation(doy, hour, lat, lon)
        if elev <= 0:
            return 0.0
        clear = 0.25 + 0.75 * (1.0 - self.cloud)
        return math.sin(elev) * clear

    def daily_light(self, t_days):
        """Mean surface irradiance over the whole day.

        Capacity is a property of the water, not of the hour -- and sampling
        instantaneous light meant that on any step that happened to land near
        midnight the model concluded the ocean could support nothing. Cached
        per simulated day, so this is six solar evaluations a day rather than
        six a step."""
        d = int(t_days)
        if self._light_day != d:
            self._light_day = d
            self._light_mean = sum(
                self.surface_light(d + (k + 0.5) / 6.0) for k in range(6)) / 6.0
        return self._light_mean

    def mixed_layer_depth(self, t_days):
        if self.ocean is not None:
            la, lo = self.where(t_days)
            m = self.ocean.mld(la, lo, t_days)
            if m is not None:
                # A shelf sea cannot mix deeper than the bottom. The MLD
                # climatology is an open-ocean product and does not know that,
                # so on the Patagonian shelf it reports a winter mixed layer of
                # a hundred metres over water sixty metres deep -- and the
                # model then applied a deep-mixing light penalty to one of the
                # most productive stretches of water on the whole track. The
                # shelf field is already in flash for the iron; this is the
                # same number used for the thing it is actually diagnostic of.
                shelf = self.ocean.shelf_km(la, lo)
                if shelf < 300.0:
                    m = min(m, 30.0 + 0.24 * shelf)
                # Clamped to a little beyond the panel's column. Beyond that
                # the only thing a deeper mixed layer does is saturate the
                # light-limitation term, which it already has.
                return min(Z_MAX * 1.6, m) * (1.0 + 0.45 * self.storm)
        doy = self.hemisphere_doy(t_days)
        # deepest around mid-February, shallowest around mid-August
        seasonal = 0.5 + 0.5 * math.cos(2 * math.pi * (doy - 46) / 365.25)
        mld = 18.0 + 62.0 * seasonal
        return mld * (1.0 + 0.45 * self.storm)

    def mixing(self, t_days):
        """Turbulent intensity, 0..1."""
        mld = self.mixed_layer_depth(t_days)
        return min(1.0, 0.28 + 0.55 * (mld / Z_MAX) + 0.6 * self.storm)

    # THE TIDE IS GONE, and it is worth saying why rather than leaving a
    # hole. The plankton column advected its cells with an M2 tide and a
    # residual, scaled by DRIFT_SCALE, because at that magnification the
    # water's own motion was the only motion there was -- a copepod swims a
    # body length a second and the panel was fifty millimetres wide.
    #
    # Here the panel is several hundred metres wide and a skipjack crosses it
    # under its own power in a few seconds. A tidal excursion of 150 px/day
    # against a fish doing 45 px/second is four decimal places of nothing, and
    # a control for it would have been a control that does nothing. What
    # replaced it is not a smaller tide: it is TURNOVER_D, which advects the
    # COMMUNITY rather than the individuals, and which is the term that
    # actually matters when the ship is making 100 km a day.

    def productivity(self, t_days):
        """0..1, how productive this water is. The base of the food chain.

        With the NPZ model deleted this is an environmental field rather than
        a simulated population: a Monod saturation on the nitrate reservoir,
        times light, times the iron ceiling. No state, one sample from flash,
        and it feeds the trophic term exactly as a modelled phytoplankton
        standing stock would have.

        LIGHT IS DELIBERATELY NOT IN HERE, and leaving it in was a total
        failure rather than a marginal one: the panel was EMPTY at Plymouth
        on day zero. Drake sailed on 13 December, a North Sea midwinter has
        almost no light, so the productivity index came out at 0.09 and every
        species in northern Europe failed its productivity axis at once.

        The error was conflating two different things. Whether a water mass
        is productive is a property of the water -- its nutrient supply, and
        whether there is iron to use it -- and it is what decides WHO lives
        there. How much that water is producing this week is a property of
        the season, and it decides HOW MANY. A cod does not leave the North
        Sea in December.

        So light moved to season() below, and what is left is the part that
        is genuinely about the water: a Monod saturation on the nitrate
        reservoir under an iron ceiling. Iron cannot be dropped -- without it
        the Southern Ocean reads as the richest water on the planet, which is
        the region most famous for having every nutrient it needs and nothing
        to use them with, and the track crosses two such regions."""
        n = self.deep_nitrate(t_days)
        return (n / (n + K_PROD)) * min(1.0, self.iron(t_days))

    def season(self, t_days):
        """0..1. How hard this water is working right now, as opposed to what
        it is capable of. Scales the number of fish, never the species list.

        The floor is 0.25 rather than 0: a dark sea in February holds fewer
        fish than the same sea in June, and it does not hold none."""
        return 0.25 + 0.75 * min(1.0, self.daily_light(t_days) / L_SAT)

    def bottom_m(self, t_days):
        """Depth of the seabed under the ship, metres.

        The fallback is deliberately deep rather than shallow. Without an
        ocean file there is no bathymetry, and guessing shallow would put
        shelf species everywhere on a track that is mostly open ocean;
        guessing deep gives the mesopelagic, which is the honest answer to
        'somewhere at sea, no further information'."""
        if self.ocean is None:
            return 4000.0
        la, lo = self.where(t_days)
        d = self.ocean.bottom_m(la, lo)
        return 4000.0 if d is None else d

    # THE THERMOCLINE, AND WHY IT HAD TO BE REWRITTEN FOR A KILOMETRE.
    #
    # The old profile went from the mixed layer to a deep value LINEARLY over
    # forty metres, and clamped. That was defensible when the panel was 55 m
    # deep -- forty metres was most of the column and nothing was ever asked
    # about deeper water.
    #
    # On a thousand-metre axis it is catastrophic: every depth below about
    # 90 m returns the deep value, so the model believed the tropical Pacific
    # was 12 C at 125 metres. It is about 23. The visible symptom was chub
    # mackerel -- an explicitly ANTI-tropical species -- turning up on the
    # equator, because the water it was being offered at its own living depth
    # was cold enough for it.
    #
    # The real ocean decays roughly exponentially from the mixed layer to a
    # deep value that is nearly the same everywhere: the abyss is 2-4 C under
    # the equator and under Iceland alike, because it is all filled from the
    # poles. So the scale height does the work and the deep value barely
    # varies. Checked against the tropical Pacific: 23.6 C at 125 m, 10.7 at
    # 500, 5.6 at 1000, against observed values of roughly 22, 9 and 5.
    THERMO_Z = 350.0           # e-folding depth of the thermocline, metres
    T_ABYSS = 3.0              # the deep ocean, which is cold everywhere

    def temperature(self, t_days, z):
        if self.ocean is not None:
            la, lo = self.where(t_days)
            sst = self.ocean.sst(la, lo, t_days)
            if sst is not None:
                surf = sst + self.temp_anomaly
                mld = self.mixed_layer_depth(t_days)
                if z <= mld:
                    return surf
                deep = min(surf, self.T_ABYSS + 1.5 * math.cos(math.radians(la)))
                return deep + (surf - deep) * math.exp(-(z - mld) / self.THERMO_Z)
        doy = self.hemisphere_doy(t_days)
        lat, _ = self.where(t_days)
        # A crude latitudinal gradient standing in for real SST until Stage 3
        # brings the climatology in. Warm at the equator, near freezing at the
        # poles, with the seasonal swing largest at high latitude.
        clat = math.cos(math.radians(lat))
        mean = -1.5 + 30.0 * clat ** 1.7
        swing = 1.5 + 6.0 * (1.0 - clat)
        surf = mean + swing * math.sin(2 * math.pi * (doy - 115) / 365.25)
        surf += self.temp_anomaly
        mld = self.mixed_layer_depth(t_days)
        if z <= mld:
            return surf
        deep = min(surf, 4.0 + 6.0 * clat)
        return surf - (surf - deep) * min(1.0, (z - mld) / 40.0)

# --------------------------------------------------------------------------
# 4. THE WATER COLUMN
# --------------------------------------------------------------------------
#
# What is in this water, and how it swims. There is no population dynamics
# here and there should not be: fish turn over on a scale of years and the
# whole voyage is 1018 days, so a birth-and-death model would run for three
# simulated years and show almost nothing. What the panel shows instead is
# OCCUPANCY -- the ship sails into new water, and the water has different
# fish in it, because it is different water.
#
# That is not a simplification of the ecology. It is the correct model for
# what is being depicted, and it is why the whole of section 5 of the old
# file -- NPZ, picoplankton, detritus, division, inheritance -- is gone rather
# than adapted.


def _wrap_pi(d):
    while d > math.pi:
        d -= 2.0 * math.pi
    while d < -math.pi:
        d += 2.0 * math.pi
    return d


class Agent:
    """One fish. Everything about an individual that is not in its species."""

    __slots__ = ("key", "x", "z", "r", "head", "body", "phase", "vis",
                 "dying", "jit", "flip")

    def __init__(self, key, x, z, r, rng):
        self.key = key
        self.x = x
        self.z = z
        # RANK WITHIN THE DEPTH BAND, FIXED FOR LIFE. This one number is what
        # makes the deep scattering layer a layer: every individual keeps its
        # place in the band as the band moves, so at dusk the whole thing
        # rises together and holds its shape. Re-randomising the depth each
        # frame gives the same average migration and looks like static.
        self.r = r
        self.head = rng.uniform(0.0, 2.0 * math.pi)
        self.body = self.head
        self.phase = rng.uniform(0.0, 2.0 * math.pi)
        self.vis = 0.02
        self.dying = False
        # lognormal spread on length, so a shoal is not a rubber stamp
        self.jit = math.exp(rng.gauss(0.0, 0.16))
        self.flip = 0


class Ecosystem:
    """The water column at the ship, and the fish in it.

    Named for continuity with the module it replaces and with the three
    screens that ask it questions. It carries no ecology in the NPZ sense --
    what it carries is an assemblage, a population that relaxes toward it, and
    the swimming."""

    def __init__(self, seed=None, start_day=0.0, track=None, ocean=None):
        self.rng = random.Random(seed)
        self.t = start_day
        self.real_t = 0.0
        self.time_compression = 60.0
        self.env = Environment(self.rng, track, ocean)
        self.agents = []
        self.assemblage = []          # [(key, suitability)], richest first
        self.share = {}               # key -> fraction of the panel it should
                                      # hold, from suitability x abundance
        self.have = {}                # key -> smoothed present count
        self.shoal_head = {}          # key -> the shoal's collective heading
        self.swim_scale = SWIM_SCALE
        self.turn_scale = TURN_SCALE
        self.prod = 0.0
        self.season = 1.0
        self.bottom = 6000.0
        self.sun = 0.0
        self.n_want = N_FLOOR
        self.n_band = (0, 0)
        self._eco_due = 0.0
        self._sample()
        self._restock(instant=True)

    # -- what the water is -------------------------------------------------

    @property
    def now(self):
        return self.t

    def sun_elev(self):
        """Solar elevation in degrees at the ship, right now. The diel
        migration is driven off this rather than off a clock hour, so it
        happens at the right moment at every latitude and on every date --
        which matters on a track that reaches 56 S in the southern winter."""
        doy = (self.t % 365.25) + 1
        hour = (self.t % 1.0) * 24.0
        la, lo = self.env.where(self.t)
        return math.degrees(solar_elevation(doy, hour, la, lo))

    def _sample(self):
        """Ask the ocean where we are what lives here."""
        env = self.env
        t = self.t
        la, lo = env.where(t)
        self.prod = env.productivity(t)
        self.bottom = env.bottom_m(t)
        self.sun = self.sun_elev()
        # temperature as a FUNCTION of depth, not a number -- see the note on
        # assemblage() in fish.py. This closure is the whole of the fix.
        self.season = env.season(t)
        temp_at = lambda z: env.temperature(t, z)
        shore = env.shelf_km(t)
        self.assemblage = F.assemblage(
            temp_at, self.bottom, self.prod, shore, la, lo)
        if not self.assemblage:
            # THE PANEL IS NEVER BARE. Four trapezoids multiplied make a lot
            # of exact zeros, and water that is slightly wrong for everything
            # returns nothing at all -- which happened, at Plymouth, on the
            # day the voyage starts.
            #
            # The floor is dropped rather than a species being invented: take
            # whatever scores highest however badly, and if literally nothing
            # scores, take the mesopelagic, which is present over any water
            # deep enough to hold it. There is no sea on this planet with no
            # fish in it, so there is no state of this model that should show
            # one.
            self.assemblage = F.assemblage(
                temp_at, self.bottom, self.prod, shore, la, lo, floor=0.0)[:4]
        if not self.assemblage and self.bottom > 400.0:
            self.assemblage = [(k, 0.05) for k in F.MESOPELAGIC]
        self._shares()

    def _weight(self, key, s):
        """Suitability times the abundance term.

        10^-(T - 2.5) is the trophic pyramid; L^-3 is numbers at a fixed
        biomass; the exponent compresses the product so the panel can show
        both ends of it. See ABUND_EXP, where the compression is argued for."""
        f = F.BY_KEY[key]
        n = (10.0 ** -(f.trophic - TROPHIC_REF)) / (f.len_common ** 3)
        return s * (n ** ABUND_EXP)

    def _shares(self):
        """How much of the panel each species should hold.

        ALLOCATED IN TWO BANDS, AND THAT IS THE CORRECTION THAT MATTERED.

        Allocated as one pool, hatchetfish and bristlemouths took the whole
        panel almost everywhere on the track -- they are tiny, so the size
        term favours them, and they suit nearly every water, so their
        suitability is near one wherever it is deep. Off Peru they crowded
        out the anchoveta; in the Moluccas they crowded out the reef.

        But the panel is a VERTICAL SECTION, and those species live in the
        bottom half of it. Competing for the same slots as a sardine is not
        something they do in the sea and not something they should do here.

        So the two bands are allocated separately, and the rule for each is
        the real one:

            mesopelagic   near-constant everywhere. Mesopelagic biomass is
                          famously uniform across the world ocean -- it is
                          the one fish community that barely knows whether
                          it is under a gyre or an upwelling.
            epipelagic    scales with productivity, hard. This is the half
                          that empties out in a gyre and fills in the
                          Humboldt, which is the single thing the water
                          screen is trying to say.

        A gyre therefore reads as a full deep layer under an empty sunlit
        one, which is exactly what a gyre is."""
        epi = [(k, s) for k, s in self.assemblage if k not in F.MESOPELAGIC]
        meso = [(k, s) for k, s in self.assemblage if k in F.MESOPELAGIC]

        n_meso = 0
        if meso:
            suit = sum(s for _, s in meso)
            n_meso = int(round(min(MESO_N, MESO_N * suit / 2.5)))
            n_meso = max(2, n_meso)
        n_epi = 0
        if epi:
            cap = (sum(s for _, s in epi)
                   * max(0.05, self.prod) * self.season * 12.0)
            n_epi = int(round(CAP_SCALE * (cap ** CAP_EXP))) if cap > 0 else 0
        total = max(N_FLOOR, min(MAX_AGENTS, n_meso + n_epi))
        # trim the surface half first if the pair overflows the panel: the
        # deep layer is the one that is there whatever the water is doing
        if n_meso + n_epi > total:
            n_epi = max(0, total - n_meso)
        self.n_want = total
        self.n_band = (n_epi, n_meso)

        self.share = {}
        for group, n in ((epi, n_epi), (meso, n_meso)):
            if not group or n <= 0:
                continue
            raw = {k: self._weight(k, s) for k, s in group}
            tot = sum(raw.values())
            if tot <= 0.0:
                continue
            for k, v in raw.items():
                self.share[k] = (v / tot) * (float(n) / total)

    # -- the population ----------------------------------------------------

    Z_MIN = 6.0                # NOTHING IS DRAWN AT ZERO METRES. A fish
                               # centred on the surface row is half off the
                               # top of the panel, and several species have
                               # depth ranges that legitimately start at 0.
                               # Six metres is one fish-length down on the
                               # log axis, which is enough to clear the swell
                               # line and still read as 'at the surface'.

    def z_floor(self):
        """The deepest a fish may be drawn: the seabed, or the bottom of the
        panel, whichever is shallower.

        WITHOUT THIS, FISH SWIM THROUGH ROCK. Every species carries a depth
        range from FishBase, and those ranges are what the animal does
        SOMEWHERE -- a cod's 0-600 m is the range of the species, not a
        promise that there are 600 m underneath it. In 55 m of Plymouth Sound
        the whole roster was distributed down its own ranges and half of it
        was drawn below a seabed that was visibly right there on the panel."""
        return max(12.0, min(Z_MAX - 1.0, self.bottom * 0.97))

    def _spawn(self, key, instant=False):
        f = F.BY_KEY[key]
        r = self.rng.random()
        a = Agent(key, self.rng.uniform(0, W),
                  max(self.Z_MIN,
                      min(F.swim_depth(f, self.sun, r), self.z_floor())),
                  r, self.rng)
        if instant:
            a.vis = 1.0
        self.agents.append(a)
        return a

    def _restock(self, instant=False):
        """Bring the population to what the water wants, in one go. Used at
        construction and after a voyage change; the gradual version is
        _relax()."""
        self.agents = []
        self.have = {}
        for key, n in self._wanted().items():
            for _ in range(n):
                self._spawn(key, instant=instant)
            self.have[key] = float(n)

    def _wanted(self):
        """key -> integer count the water wants right now.

        Largest-remainder allocation rather than rounding each share
        independently: rounding gives a total that drifts from n_want by
        several fish, and on a panel carrying six of them in a gyre that is
        the difference between sparse and empty."""
        if not self.share:
            return {}
        exact = {k: v * self.n_want for k, v in self.share.items()}
        out = {k: int(v) for k, v in exact.items()}
        left = self.n_want - sum(out.values())
        if left > 0:
            rem = sorted(exact, key=lambda k: -(exact[k] - int(exact[k])))
            for k in rem[:left]:
                out[k] += 1
        # anything the water clearly holds gets at least one individual, or a
        # species can be present in the census and invisible in the water,
        # which reads as a bug in the plate
        for k, v in self.share.items():
            if v > 0.10 and out.get(k, 0) == 0:
                out[k] = 1
        return out

    def _relax(self, dt):
        """Move the population toward what the water wants, at TURNOVER_D."""
        want = self._wanted()
        k_relax = 1.0 - math.exp(-dt / TURNOVER_D)
        # smoothed counts, so a species does not flicker in and out when its
        # share sits near a rounding boundary
        for key in set(list(want) + list(self.have)):
            cur = self.have.get(key, 0.0)
            self.have[key] = cur + (want.get(key, 0) - cur) * k_relax

        alive = {}
        for a in self.agents:
            if not a.dying:
                alive[a.key] = alive.get(a.key, 0) + 1
        for key, target in self.have.items():
            n = int(round(target))
            cur = alive.get(key, 0)
            for _ in range(max(0, n - cur)):
                self._spawn(key)
            if cur > n:
                # retire the ones nearest the panel edge: a fish fading out
                # where it is already half off screen is the least visible
                # way to lose one
                cand = [a for a in self.agents
                        if a.key == key and not a.dying]
                cand.sort(key=lambda a: -abs(a.x - W * 0.5))
                for a in cand[:cur - n]:
                    a.dying = True
        for key in list(self.have):
            if self.have[key] < 0.02 and key not in want:
                del self.have[key]

    def _fade(self, dt):
        out = []
        for a in self.agents:
            if a.dying:
                a.vis -= dt / DIE_D
                if a.vis <= 0.0:
                    continue
            elif a.vis < 1.0:
                a.vis = min(1.0, a.vis + dt / EMERGE_D)
            out.append(a)
        self.agents = out

    # -- swimming ----------------------------------------------------------

    def _swim(self, dt):
        """Move the fish, at real time, and turn them to face where they go.

        Ballistic below the heading decorrelation time and diffusive above it,
        which is the one way a single piece of code can be right at both ends
        of a speed control spanning six orders of magnitude."""
        rng = self.rng
        dt_s = dt * 86400.0 / max(1.0, self.time_compression)
        self.real_t += dt_s
        slow = max(1e-3, self.swim_scale)
        body_k = 1.0 - math.exp(-dt_s / BODY_TAU)

        # the shoals' collective headings wander slowly, and every member
        # steers toward its own species' heading in proportion to how
        # gregarious that species is. One number per species per frame buys
        # the single most recognisable behaviour in the sea.
        floor = self.z_floor()
        sk = math.sqrt(min(dt_s, 4.0 * SHOAL_TAU) / SHOAL_TAU)
        for key in self.share:
            h = self.shoal_head.get(key)
            if h is None:
                h = rng.uniform(0.0, 2.0 * math.pi)
            self.shoal_head[key] = h + rng.gauss(0.0, sk)

        for a in self.agents:
            f = F.BY_KEY[a.key]
            L = F.draw_length(f, a.jit)
            v0 = f.swim_bl * L * slow                       # px per second
            tau = F.TURN_TAU[f.gait] / slow * self.turn_scale

            # --- depth: the band owns it -----------------------------------
            #
            # Relaxed toward the species' band rather than set to it, so a
            # migrating layer ASCENDS instead of teleporting. The time
            # constant is in panel seconds because it is a drawing rate: the
            # real ascent takes about an hour, and at one second per second
            # so does this one.
            z_want = max(self.Z_MIN,
                         min(F.swim_depth(f, self.sun, a.r), floor))
            a.z += (z_want - a.z) * (1.0 - math.exp(-dt_s / 900.0))

            if dt_s >= tau:
                # far past decorrelation: one step is a whole random walk and
                # only the diffusivity has to be right, D = v^2 tau
                step = v0 * math.sqrt(tau * dt_s)
                a.head = rng.uniform(0.0, 2.0 * math.pi)
                a.body = a.head
                a.x = (a.x + rng.gauss(0.0, step)) % W
                a.phase += dt_s * slow
                continue

            a.head += rng.gauss(0.0, math.sqrt(dt_s / tau))
            if f.shoal > 0.05:
                a.head += _wrap_pi(self.shoal_head[a.key] - a.head) * \
                    min(1.0, f.shoal * F.SHOAL_K * dt_s)
            a.phase += 2.0 * math.pi * F.beat_hz(f) * dt_s * slow

            a.body += _wrap_pi(a.head - a.body) * body_k
            a.x = (a.x + v0 * dt_s * math.cos(a.body)) % W
            a.z = max(self.Z_MIN, min(floor,
                               a.z + v0 * dt_s * math.sin(a.body) * VERT_DAMP
                               * (Z_MAX / H)))

    # -- the clock ---------------------------------------------------------

    def _ecology(self, dt):
        """Resample the water and move the population toward it. Does NOT
        touch the clock -- both entry points below own that, and having two
        callers each advance `t` in their own way is exactly how the first
        version of this deadlocked."""
        self.env.step(dt)
        self._sample()
        self._relax(dt)
        self._fade(dt)

    def step(self, dt):
        """Headless entry: advance the clock and run the ecology together.

        tools/ and the --stills and --voyage paths drive this in a
        `while eco.t < N` loop, so it MUST advance t. It does not swim: a
        contact sheet does not care where in its stroke a fish is."""
        self.t += dt
        self._ecology(dt)

    def advance(self, dt_days):
        """Frame-rate entry: swim every frame, run the ecology hourly.

        Resampling a 2-degree climatology sixty times a second answers the
        same question sixty times, so the ecology is accumulated and run on
        the hour. The clock itself advances smoothly, because the footer
        prints a position and a date and those should not tick."""
        if dt_days <= 0.0:
            self._swim(0.0)
            return
        self._swim(dt_days)
        self.t += dt_days
        self._eco_due += dt_days
        if self._eco_due >= ECO_DT:
            self._ecology(self._eco_due)
            self._eco_due = 0.0

    # -- what the plate asks ----------------------------------------------

    def census(self):
        """[(key, count, suitability, abundance), ...], richest first.

        The count is what is DRAWN and the abundance is what the model
        BELIEVES -- and they are deliberately different numbers. The drawn
        count is compressed so a gyre is watchable; the abundance is not, and
        it is what the plate's bar reports."""
        tally = {}
        for a in self.agents:
            if a.vis <= 0.03:
                continue
            tally[a.key] = tally.get(a.key, 0) + 1
        suit = dict(self.assemblage)
        rows = []
        for key, n in tally.items():
            f = F.BY_KEY[key]
            s = suit.get(key, 0.0)
            # individuals per unit volume, on one absolute scale across the
            # whole voyage: suitability times the uncompressed pyramid
            ab = s * self.prod * (10.0 ** -(f.trophic - TROPHIC_REF)) \
                * (20.0 / f.len_common) ** 3 * A_SCALE
            rows.append((key, n, s, ab))
        rows.sort(key=lambda r: -r[3])
        return rows

    def biomass(self):
        """Kilograms of fish drawn on the panel.

        W(g) = 0.01 L(cm)^3 is the standard condition factor for a
        roughly fusiform fish, and it is close enough for every shape here.
        Reported rather than used: nothing in the model reads it, but a
        number that says a gyre panel holds 200 g of fish and a Humboldt
        panel holds nine kilos says the thing the picture is trying to."""
        return sum(0.01 * (F.BY_KEY[a.key].len_common * a.jit) ** 3
                   for a in self.agents if a.vis > 0.03) / 1000.0


# The abundance scale's zero point. Set so that the scarcest species the
# model ever shows, at the place it is scarcest, comes out near 1 -- which
# makes every other number on the plate a multiple of "the rarest thing
# anywhere on the voyage". Measured by tools/check_biogeography.py over the
# whole track rather than chosen, and baked in here.
A_SCALE = 4200.0


# --------------------------------------------------------------------------
# 5. RENDERER
# --------------------------------------------------------------------------

MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
          "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")

TOP_M, BOT_M = 4, 28          # margins in CLEAN mode, where the water has
                              # the whole panel
PLATE_M = 90                  # ...and with the footer up. Measured, not
                              # guessed: the title sits at H-12-10-2*19-21-5,
                              # which is 86 px of furniture, and 90 leaves a
                              # gap rather than a collision.
                              # THE COLUMN HAS TO
                              # KNOW ABOUT THE FOOTER. At a fixed margin of
                              # 28 the axis ran to within 28 px of the bottom
                              # edge while the footer occupied the last 70,
                              # so everything below about 600 m was drawn
                              # behind the caption -- which is to say the
                              # entire mesopelagic, the half of the panel the
                              # log axis exists to show, was invisible
                              # whenever the plate was up. Which is 98% of
                              # the time.

_LOGSPAN = math.log1p(Z_MAX / Z0)


def depth_to_y(z, bot=BOT_M):
    """Metres to panel row, logarithmically. Z0 puts 200 m at half height --
    see the note in the config, where the identity is derived."""
    if z <= 0.0:
        return float(TOP_M)
    f = math.log1p(z / Z0) / _LOGSPAN
    return TOP_M + f * (H - TOP_M - bot)


def y_to_depth(y, bot=BOT_M):
    """The inverse, for drawing the scale."""
    f = (y - TOP_M) / float(H - TOP_M - bot)
    return Z0 * (math.exp(f * _LOGSPAN) - 1.0)


def date_label(t_days):
    doy = int(t_days % 365.25) + 1
    cum = (31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
    m = 0
    while m < 11 and doy > cum[m]:
        m += 1
    d = doy - (cum[m - 1] if m > 0 else 0)
    return "%02d %s" % (d, MONTHS[m])


class View:
    """What chrome is drawn, and nothing about the simulation.

    Clean mode is not a separate render path -- it is every piece of
    furniture switched off, leaving fish on bare paper. On the hardware this
    collapses to two bits in a config byte."""

    __slots__ = ("plate", "floor", "_saved")

    def __init__(self, plate=True, floor=True):
        self.plate = plate
        self.floor = floor        # the seabed, the surface and the depth scale
        self._saved = None

    @property
    def clean(self):
        return not self.plate

    def toggle_clean(self):
        if self.clean:
            self.plate = self._saved if self._saved is not None else True
            self._saved = None
        else:
            self._saved = self.plate
            self.plate = False


DEFAULT_VIEW = View()

# A fixed relief profile for the seabed. Fixed, so the bottom does not
# shimmer between frames -- the ship moves over it, but the rock does not
# reorganise itself sixty times a second. Two octaves is enough to read as
# ground rather than as a ruled line.
_RELIEF = None


def _relief():
    global _RELIEF
    if _RELIEF is None:
        r = random.Random(20260727)
        a = [r.uniform(-1.0, 1.0) for _ in range(9)]
        b = [r.uniform(-1.0, 1.0) for _ in range(23)]
        _RELIEF = (a, b)
    return _RELIEF


def _relief_at(x):
    a, b = _relief()
    i = x * (len(a) - 1) / float(W)
    j = x * (len(b) - 1) / float(W)
    i0, j0 = int(i), int(j)
    fi, fj = i - i0, j - j0
    va = a[i0] + (a[min(i0 + 1, len(a) - 1)] - a[i0]) * fi
    vb = b[j0] + (b[min(j0 + 1, len(b) - 1)] - b[j0]) * fj
    return va * 1.0 + vb * 0.38


def draw_seabed(c, bottom_m, bot=BOT_M):
    """The bottom, when it is in frame.

    THIS IS THE MOST LEGIBLE STATEMENT OF PLACE THE PANEL MAKES. Over the
    Patagonian shelf the seabed sits a third of the way down and the whole
    column is above it; two days later, over the Argentine abyssal plain,
    it is gone and the panel is open water to a thousand metres. Nothing
    else on the water screen says 'somewhere different' that quickly.

    Drawn as a ridge line with hatching below rather than a solid fill: a
    filled black third of a 1-bit panel is a very heavy object, and on a
    reflective display it is also the slowest thing to refresh."""
    if bottom_m is None or bottom_m >= Z_MAX:
        return
    y0 = depth_to_y(bottom_m, bot)
    if y0 >= H - bot - 2:
        return
    amp = max(2.0, min(9.0, (H - BOT_M - y0) * 0.10))
    pts = []
    for x in range(0, W + 4, 4):
        xx = min(x, W - 1)
        pts.append((xx, y0 + _relief_at(xx) * amp))
    c.polyline(pts)
    # hatching: diagonal strokes below the ridge, thinning downward, so the
    # ground reads as solid without being solid
    step = 7
    for x in range(-H, W, step):
        for k in range(0, 3):
            sx = x + k * 2
            ridge = y0 + _relief_at(max(0, min(W - 1, sx))) * amp
            y1 = min(H - bot - 1, ridge + 5 + k * 6)
            if y1 <= ridge + 1:
                continue
            c.line(sx, ridge + 1, sx + (y1 - ridge - 1), y1)


def draw_surface(c, t):
    """The sea surface: a slow swell across the top two rows."""
    pts = []
    for x in range(0, W + 3, 3):
        xx = min(x, W - 1)
        y = TOP_M + 1.6 + 1.4 * math.sin(xx * 0.055 + t * 0.35) \
            + 0.7 * math.sin(xx * 0.021 - t * 0.21)
        pts.append((xx, y))
    c.polyline(pts)


def _depth_label(c, y, s, bot=BOT_M, above=True):
    """Right-aligned against the panel edge, which is the only way it fits.

    Left at a fixed x it ran off the right-hand side: "1000M" at reading
    size is fifty pixels and the column started thirty from the edge. The
    label is set by its own width, not by a guess at it."""
    w = text_width(s, scale=T_MED)
    ty = y - text_height(T_MED) - 1 if above else y + 2
    ty = max(TOP_M, min(H - bot - text_height(T_MED) - 1, ty))
    label(c, W - 6 - w, ty, s, scale=T_MED, pad=2)
    return W - 10 - w


def draw_depth_scale(c, eco, bot=BOT_M):
    """Two marks, and only one of them is fixed.

    The 200 m line earns its place: it is where the light runs out, it is
    the boundary every species record in the roster is written against, and
    at dusk it is the line the scattering layer comes up through.

    The other is the SEABED, labelled with its actual depth, and it is worth
    more than any fixed tick would be. A ruler down the side would make this
    a chart; a number that reads SEABED 71M off Patagonia and is simply
    absent two days later in four kilometres of water makes it a window."""
    y = depth_to_y(Z_SUN, bot)
    if y < H - bot - 6:
        right = _depth_label(c, y, "200M", bot)
        for xd in range(6, int(right) - 4, 9):
            c.line(xd, y, xd + 4, y)

    b = eco.bottom
    if b is not None and b < Z_MAX:
        yb = depth_to_y(b, bot)
        if TOP_M + 8 < yb < H - bot - 4:
            _depth_label(c, yb, "SEABED %dM" % int(round(b)), bot)


def render(eco, canvas, view=DEFAULT_VIEW, track=None, day=None):
    canvas.clear()
    bot = PLATE_M if view.plate else BOT_M

    if view.floor:
        draw_surface(canvas, eco.real_t)
        draw_depth_scale(canvas, eco, bot)
        draw_seabed(canvas, eco.bottom, bot)

    # NIGHT. Drawn as nothing at all -- there is no way to darken a
    # reflective panel, and a stipple over the whole frame would obliterate
    # the fish. What night does here is move the animals, which is a truer
    # statement about the deep sea than a shading would be: the scattering
    # layer coming up IS the night, and it is visible from across a room.

    for a in eco.agents:
        if a.vis <= 0.03:
            continue
        f = F.BY_KEY[a.key]
        L = F.draw_length(f, a.jit)
        if L < 4.0:
            continue
        y = depth_to_y(a.z, bot)
        form = F.FORM[a.key]
        ext = L * 0.75
        # draw across the seam so nothing teleports when it wraps
        for xoff in (0.0, -W, W):
            xx = a.x + xoff
            if xx + ext < 0 or xx - ext > W:
                continue
            draw.draw_fish(canvas, xx, y, L, a.body, form, phase=a.phase)

    if view.plate:
        draw_plate(eco, canvas, track, day)


def draw_plate(eco, c, track=None, day=None):
    """The footer, and nothing else -- at a size that can be read.

    Four things, each big enough to read from across a room:

        the voyage        who is sailing
        AT SEA / ANCHORED what is happening now
        lat and lon       where
        the bar           how far through
    """
    if track is None or day is None:
        lab = date_label(eco.t)
        f = (eco.t % 365.25) / 365.25
        st = pos = None
    else:
        la, lo = track.position(day)
        lab = track.voyage.title
        st = track.status(day)
        pos = "%d%s%02d'%s  %d%s%02d'%s" % (
            abs(int(la)), "\xb0", int(abs(la) % 1 * 60), "N" if la >= 0 else "S",
            abs(int(lo)), "\xb0", int(abs(lo) % 1 * 60), "E" if lo >= 0 else "W")
        f = day / track.days[-1]

    m = 10
    by = H - 12                                   # the progress bar
    line_h = text_height(T_MED) + 5

    lines = (wrap(st, W - 2 * m) if st else []) + ([pos] if pos else [])
    y = by - 10 - line_h * len(lines)
    sc = fit_scale(lab, W - 2 * m)
    label(c, m, y - text_height(sc) - 5, lab, scale=sc)
    for i, ln in enumerate(lines):
        label(c, m, y + i * line_h, ln, scale=T_MED)

    c.line(m, by, W - m - 1, by)
    x = m + (W - 2 * m - 1) * f
    c.line(x, by - 4, x, by + 2)
    c.line(m, by - 2, m, by + 2)
    c.line(W - m - 1, by - 2, W - m - 1, by + 2)


# --------------------------------------------------------------------------
# 7. PREVIEW
# --------------------------------------------------------------------------

# Speed is one number: simulated days elapsed per real second. Everything
# else -- presets, the wheel, the readout -- is a view onto it.
SPEED_MIN = 1.0 / 86400.0          # real time: 1 sim second per real second
SPEED_MAX = 8.0                    # a year in 46 real seconds
SPEED_STEP = 2.0 ** 0.25           # one wheel notch: 4 notches per doubling
SPEED_COARSE = 2.0                 # shift+wheel: one notch per doubling

# Keys 1-5. Landmarks on a continuum, not the only available speeds.
PRESETS = (
    1.0 / 86400.0,                 # real time
    1.0 / 1440.0,                  # 1 min per sec
    1.0 / 24.0,                    # 1 hour per sec
    0.25,                          # 6 hours per sec
    1.0,                           # 1 day per sec
)
# Snap radius is half a notch, in log space. That is the principled value:
# if a preset is nearer than the next detent, the wheel lands on the preset.
# Anything smaller and presets fall between notches and become unreachable
# by scrolling; anything larger and the wheel sticks to them.
SNAP_TOL = 0.5 * math.log(SPEED_STEP)


def clamp_speed(v):
    return max(SPEED_MIN, min(SPEED_MAX, v))


def snap_speed(v):
    """So that scrolling past a preset lands exactly on it, and the readout
    says '1 HR/SEC' rather than '1.1 HR/SEC'."""
    for p in PRESETS:
        if abs(math.log(v / p)) < SNAP_TOL:
            return p
    return v


def speed_label(dps):
    """dps is simulated days per real second. Report it in whatever unit
    keeps the number small, because that is how you actually think about it."""
    s = dps * 86400.0                       # simulated seconds per real second
    if s < 59.5:
        v, u = s, "SEC"
    elif s < 3570.0:
        v, u = s / 60.0, "MIN"
    elif s < 85000.0:
        v, u = s / 3600.0, "HR"
    else:
        v, u = s / 86400.0, "DAY"
    if v < 9.95:
        n = ("%.1f" % v).rstrip("0").rstrip(".")
    else:
        n = "%d" % int(round(v))
    return "%s %s/SEC" % (n, u)


def to_pil(canvas):
    """Any canvas, not just the panel -- the card generator draws a square
    one, and hard-coding the panel's shape here meant it could not."""
    from PIL import Image
    import numpy as np
    arr = np.frombuffer(bytes(canvas.buf), dtype=np.uint8).reshape(
        canvas.h, canvas.w)
    # ink is 1 -> dark; paper is 0 -> light. Matches a reflective panel.
    img = np.where(arr > 0, 26, 232).astype(np.uint8)
    return Image.fromarray(img, mode="L")


def stills(outdir):
    """Render a set of dates without needing pygame -- useful for judging the
    seasonal cycle at a glance."""
    import os
    os.makedirs(outdir, exist_ok=True)
    eco = Ecosystem(seed=7, start_day=1.0)
    canvas = Canvas(W, H)
    view = View()
    targets = [30, 105, 135, 175, 240, 320]
    saved = []
    i = 0
    while eco.t < 340 and i < len(targets):
        eco.step(1.0 / 24.0)
        if eco.t >= targets[i]:
            render(eco, canvas, view)
            path = os.path.join(outdir, "drift_%03d.png" % targets[i])
            to_pil(canvas).resize((W * 2, H * 2), 0).save(path)
            saved.append((path, date_label(eco.t), eco.biomass(),
                          len(eco.agents), len(eco.assemblage),
                          eco.prod, eco.bottom))
            i += 1
    for p, d, b, n, taxa, prod, bot in saved:
        print("%s  %s  biomass %5.1f  fish %2d  taxa %2d  prod %.2f  bottom %5.0fm"
              % (p, d, b, n, taxa, prod, bot))


LUT = None   # built lazily, preview only


def preview():
    global LUT
    import pygame
    import numpy as np
    LUT = np.array([[228, 228, 224], [22, 22, 24]], dtype=np.uint8)
    pygame.init()
    # SCALE may be fractional -- notably when it is set to show the panel at
    # its true physical size, where the monitor is usually LESS dense than
    # the panel and the factor comes out below 1. Nearest-neighbour is right
    # for integer upscaling and wrong for anything else, so pick per case.
    pw, ph = int(round(W * SCALE)), int(round(H * SCALE))
    smooth = abs(SCALE - round(SCALE)) > 1e-6 or SCALE < 1.0
    screen = pygame.display.set_mode((pw, ph))
    pygame.display.set_caption("Drift")
    clock = pygame.time.Clock()

    from voyage import Track, VOYAGES
    from mapview import Coast
    from ocean import Ocean
    from screens import Rotation, Compositor, GALLERY

    track = Track(sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in
                  __import__("voyage").VOYAGES else "drake")
    coast = Coast("data/coast.bin")
    ocean = Ocean("data/ocean.bin")
    eco = Ecosystem(seed=None, start_day=0.0, track=track, ocean=ocean)
    canvas = Canvas(W, H)
    view = View()
    rot = Rotation(GALLERY)
    comp = Compositor()
    # ONE SECOND PER SECOND, and this is the piece rather than a preview
    # setting. Drake was at sea for 1018 days; so is this. A gift that takes
    # two years and nine months to round the Horn is saying something about
    # the voyage that no amount of compression can, and it is the reason the
    # motion was tuned where it was -- at 1:1 the only thing that changes on
    # a human timescale is the swimming, so the swimming has to be right.
    #
    # The wheel still works. It is for looking ahead, not for living in.
    speed = PRESETS[0]
    paused = False
    toast = 0.0                 # seconds left on the transient speed readout
    shot = 0

    surf = pygame.Surface((W, H))
    running = True
    while running:
        real_dt = clock.tick(TARGET_FPS) / 1000.0
        wheel = 0
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.MOUSEWHEEL:
                wheel += e.y
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button in (4, 5):
                wheel += 1 if e.button == 4 else -1     # older SDL fallback
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    running = False
                elif e.key == pygame.K_SPACE:
                    paused = not paused
                    toast = 1.4
                elif e.key in (pygame.K_1, pygame.K_2, pygame.K_3,
                               pygame.K_4, pygame.K_5):
                    speed = PRESETS[e.key - pygame.K_1]
                    toast = 1.4
                elif e.key == pygame.K_c:
                    view.toggle_clean()
                elif e.key == pygame.K_p:
                    view.plate = not view.plate
                elif e.key == pygame.K_n:
                    view.floor = not view.floor
                elif e.key == pygame.K_m:
                    rot.skip()
                elif e.key == pygame.K_v:
                    # next voyage. The ecosystem is rebuilt because it is
                    # sailing somewhere else now, and it never knew which
                    # voyage it was on in the first place.
                    keys = sorted(VOYAGES)
                    i = (keys.index(track.voyage.key) + 1) % len(keys)
                    track = Track(keys[i])
                    eco = Ecosystem(seed=None, start_day=0.0, track=track,
                                    ocean=ocean)
                    print("voyage: %s" % track.voyage.subtitle)
                elif e.key == pygame.K_r:
                    eco = Ecosystem(seed=None, start_day=eco.t, track=track,
                                    ocean=ocean)
                elif e.key == pygame.K_s:
                    to_pil(canvas).resize((W * 4, H * 4), 0).save(
                        "drift_%03d.png" % shot)
                    print("saved drift_%03d.png" % shot)
                    shot += 1

        if wheel:
            mods = pygame.key.get_mods()
            step = SPEED_COARSE if (mods & pygame.KMOD_SHIFT) else SPEED_STEP
            speed = clamp_speed(snap_speed(speed * step ** wheel))
            toast = 1.4

        eco.time_compression = speed * 86400.0
        if not paused:
            # advance(), not step(): swimming every frame and the ecology on
            # its own clock. The substepping that used to live here moved in
            # there, where it belongs.
            eco.advance(real_dt * speed)
            # home again. The second circumnavigation gets a fresh seed, so
            # the same ocean grows a different community -- one line, and it
            # is the difference between a loop and a repeat.
            if eco.t >= track.days[-1]:
                eco = Ecosystem(seed=None, start_day=0.0, track=track,
                                ocean=ocean)
            rot.advance(real_dt)

        toast = max(0.0, toast - real_dt)

        comp.frame(canvas, rot, eco, track, coast, view)
        status = speed_label(speed) + ("  PAUSED" if paused else "")
        if toast > 0.0:
            # the panel keeps its own counsel, except for a moment after you
            # touch the wheel. Drawn over the footer rather than beside it,
            # because at this type size there is no beside left.
            label(canvas, 10, H - 30, status, scale=T_MED)

        # blit the 1-bit buffer via numpy -- a per-pixel Python loop here
        # costs ~96k operations a frame and stutters badly
        arr = np.frombuffer(bytes(canvas.buf), dtype=np.uint8).reshape(H, W)
        pygame.surfarray.blit_array(surf, np.transpose(LUT[arr], (1, 0, 2)))
        if smooth:
            # a soft resample is not a betrayal of the 1-bit aesthetic here:
            # below 1:1 the monitor cannot show every panel pixel, and the eye
            # at arm's length from the real panel is doing the same averaging
            screen.blit(pygame.transform.smoothscale(surf, (pw, ph)), (0, 0))
        else:
            pygame.transform.scale(surf, (pw, ph), screen)
        pygame.display.flip()

    pygame.quit()


def voyage_sweep(outdir, every=30, seed=7, log_every=10, voyage="drake"):
    """Run the whole circumnavigation headless and lay it out as a contact
    sheet, one panel per `every` days.

    This is the only test that matters. Everything else checks that a piece
    works; this checks whether the object is any good -- and it is the thing
    Stage 6 is built around, so it exists now, in embryo, rather than being
    written at the end when it is too late to change anything."""
    import os
    from voyage import Track
    from ocean import Ocean
    from PIL import Image

    os.makedirs(outdir, exist_ok=True)
    track = Track(voyage)
    try:
        ocean = Ocean("data/ocean.bin")
    except (IOError, OSError):
        ocean = None
        print("no data/ocean.bin -- running on the latitudinal stopgap")
    eco = Ecosystem(seed=seed, start_day=0.0, track=track, ocean=ocean)
    canvas = Canvas(W, H)
    view = View()
    total = track.days[-1]

    # The contact sheet wants a panel a month; the statistics want three
    # times that. A regional window three panels wide is noise -- the gyre
    # test swung between 5% and 57% across seeds on that sample -- so the log
    # is sampled finer than the sheet.
    tiles, log = [], []
    nxt, nxt_log = 0.0, 0.0
    while eco.t < total:
        eco.step(1.0 / 12.0)
        if eco.t >= nxt:
            render(eco, canvas, view, track, eco.t)
            tiles.append(to_pil(canvas))
            nxt += every
        if eco.t >= nxt_log:
            nxt_log += log_every
            la, lo = track.position(eco.t)
            comp = eco.composition()
            log.append((int(eco.t), la, lo, eco.env.temperature(eco.t, 2.0),
                        eco.env.mixed_layer_depth(eco.t),
                        eco.env.deep_nitrate(eco.t), eco.env.iron(eco.t),
                        eco.biomass, len(eco.agents), eco.n_zoo)
                       + tuple(comp.get(k, 0.0) for k in DRIFTER_KINDS)
                       + (track.status(eco.t),))

    cols = 9
    rows = (len(tiles) + cols - 1) // cols
    g = 6
    sheet = Image.new("L", (cols * (W + g) + g, rows * (H + g) + g), 245)
    for i, t in enumerate(tiles):
        sheet.paste(t, (g + (i % cols) * (W + g), g + (i // cols) * (H + g)))
    path = os.path.join(outdir, "voyage.png")
    sheet.save(path)

    with open(os.path.join(outdir, "voyage.csv"), "w") as f:
        f.write("day,lat,lon,sst,mld,deepN,iron,prod,bottom,fish,"
                + ",".join(F.BY_KEY[k].common.lower().replace(" ", "_")
                           for k in F.ALL_KEYS) + ",status\n")
        for r in log:
            f.write("%d,%.2f,%.2f,%.1f,%.0f,%.1f,%.2f,%.3f,%.0f,%d,"
                    % r[:10]
                    + ",".join("%.2f" % v for v in r[10:-1])
                    + ",%s\n" % r[-1])

    prod = [r[7] for r in log]
    n = [r[9] for r in log]
    print("%s  %d panels" % (path, len(tiles)))
    print("prod     min %5.2f  median %5.2f  max %5.2f"
          % (min(prod), sorted(prod)[len(prod) // 2], max(prod)))
    print("fish     min %5d  median %5d  max %5d"
          % (min(n), sorted(n)[len(n) // 2], max(n)))
    empty = sum(1 for v in n if v < 6)
    print("panels with fewer than 6 fish: %d of %d" % (empty, len(n)))
    return log


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--stills":
        stills(sys.argv[2])
    elif len(sys.argv) > 2 and sys.argv[1] == "--voyage":
        voyage_sweep(sys.argv[2],
                     voyage=sys.argv[3] if len(sys.argv) > 3 else "drake")
    else:
        preview()
