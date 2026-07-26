#!/usr/bin/env python3
"""
DRIFT  -  a generative plankton column for a 1-bit reflective panel.

Stage 0: runs on a laptop, renders at the EXACT resolution and bit depth of the
target hardware, then upscales nearest-neighbour so what you see is what the
panel will show. No anti-aliasing, no greyscale, no cheating.

Architecture is deliberately split so the port to RP2350 is mechanical:

    Canvas       ~200 lines of integer raster primitives.  Reimplement these
                 six functions in C and everything above them ports unchanged.
    Environment  pure float maths, no state.  Ports as-is.
    Ecosystem    NPZ model + individual agents.  Ports as-is.
    Renderer     calls Canvas only.  Ports as-is.
    preview()    pygame.  Thrown away on the port.

Run:
    pip install pygame numpy
    python3 drift.py

Keys:
    space       pause
    wheel       speed, continuously (shift+wheel for coarse jumps)
    1 2 3 4 5   speed presets: real time / 1 min / 1 hr / 6 hr / 1 day per sec
    m           next screen now, and switch to the EXHIBIT cadence
    c           CLEAN MODE -- organisms and snow only, all chrome hidden
    h           toggle HUD
    p           toggle the footer / map and key plate chrome
    n           toggle the chemoautotroph stipple
    s           save a PNG
    r           reseed the world
    esc         quit

The voyage runs on the same clock as the ecosystem -- there is no separate
voyage rate. At the default 1 MIN/SEC a simulated day takes 24 real minutes
and the whole circumnavigation takes 17 real days: slow enough to be a thing
that sits there, fast enough that it has moved between one look and the
next.

Headless (writes stills, no pygame needed):
    python3 drift.py --stills out/
"""

import math
import random
import sys

# --------------------------------------------------------------------------
# 1. CONFIG
# --------------------------------------------------------------------------

W, H = 240, 400            # panel resolution, portrait. Sharp 2.7" rotated.
SCALE = 2                  # preview upscale only

LAT = 52.0800              # Melbourn
LON = 0.0200

Z_MAX = 55.0              # metres of water column mapped to the panel height
MAX_PHYTO = 30             # separate caps, or phytoplankton crowd out the
MAX_ZOO = 7                # grazers entirely during a bloom
MAX_AGENTS = MAX_PHYTO + MAX_ZOO   # render cost lives here
SNOW_COUNT = 80            # fine unresolved detritus, decorative
MAX_DETRITUS = 46          # resolved particles, from actual deaths

NBINS = 22                 # depth bins for the biogeochemistry
BIN_M = Z_MAX / NBINS

EMERGE_D = 0.55            # days for a new cell to fade in
DIE_D = 0.40               # days for a dying cell to fade out

# --- physics of the moving water -----------------------------------------
T_M2 = 0.517500            # principal lunar semidiurnal tide, days (12h25m)
U_TIDE = 150.0             # tidal excursion amplitude, px/day
U_RESID = 38.0             # residual drift, px/day
SHEAR_Z = 22.0             # e-folding depth of the current profile, m

# --- nitrogen ------------------------------------------------------------
PSI = 1.4                  # ammonium inhibition of nitrate uptake
V_NIT = 2.2                # max nitrification rate
K_NIT = 0.55
Y_NIT = 0.150              # chemoautotroph yield per unit N oxidised
LOSS_NIT = 0.085
I_NIT_INHIB = 0.004        # nitrification is photoinhibited -> it lives deep
REMIN = 0.115              # detritus remineralisation rate, /day
W_DET = 9.0                # detritus sinking, m/day

# biology
MU_MAX = 1.45              # max phyto division rate, /day
I_K = 0.095                # light half-saturation (normalised irradiance)
K_S = 0.45                 # nutrient half-saturation
K_WATER = 0.035            # background light attenuation, /m
K_CHL = 0.055               # extra attenuation per unit biomass (self-shading)
N_DEEP = 13.0              # deep nutrient reservoir
GRAZE_RADIUS = 26.0        # metres... artistic licence, see note below
RESPIRATION = 0.06

# NOTE ON SCALE. The depth axis is real: it drives light, nutrients and diel
# migration. Organism size is NOT to scale -- a 60 um diatom would be a
# fraction of a pixel. Treat the panel as a plate, or an imaging cytometer
# field, with depth mapped vertically. Scientific illustration has always
# done this.


# --------------------------------------------------------------------------
# 2. CANVAS  -  1-bit framebuffer, integer primitives
# --------------------------------------------------------------------------

class Canvas:
    """One byte per pixel here for speed and clarity. On the MCU this becomes
    a packed 1bpp buffer of W*H/8 bytes -- 12 kB at 240x400 -- and only these
    primitives need rewriting."""

    __slots__ = ("w", "h", "buf")

    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.buf = bytearray(w * h)

    def clear(self):
        # bytearray slice assignment is the fastest memset available
        self.buf[:] = b"\x00" * (self.w * self.h)

    def px(self, x, y):
        x = int(x); y = int(y)
        if 0 <= x < self.w and 0 <= y < self.h:
            self.buf[y * self.w + x] = 1

    def line(self, x0, y0, x1, y1):
        x0 = int(x0); y0 = int(y0); x1 = int(x1); y1 = int(y1)
        w = self.w; h = self.h; buf = self.buf
        # cheap whole-line reject
        if (x0 < 0 and x1 < 0) or (x0 >= w and x1 >= w):
            return
        if (y0 < 0 and y1 < 0) or (y0 >= h and y1 >= h):
            return
        dx = x1 - x0
        dy = y1 - y0
        sx = 1 if dx >= 0 else -1
        sy = 1 if dy >= 0 else -1
        dx = dx if dx >= 0 else -dx
        dy = dy if dy >= 0 else -dy
        err = dx - dy
        while True:
            if 0 <= x0 < w and 0 <= y0 < h:
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


def text(canvas, x, y, s, spacing=1):
    """Returns the x cursor after drawing, so labels can be chained."""
    for ch in s.upper():
        g = FONT.get(ch)
        if g is None:
            g = FONT[" "]
        for col in range(3):
            bits = g[col]
            for row in range(5):
                if bits & (1 << row):
                    canvas.px(x + col, y + row)
        x += 3 + spacing
    return x


def text_width(s, spacing=1):
    return len(s) * (3 + spacing) - spacing


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

    def __init__(self, rng, track=None):
        self.rng = rng
        self.track = track          # None -> stand still at Melbourn
        self.cloud = 0.5
        self.storm = 0.0
        self.temp_anomaly = 0.0

    def where(self, t_days):
        if self.track is None:
            return LAT, LON
        return self.track.position(t_days)

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

    def mixed_layer_depth(self, t_days):
        doy = self.hemisphere_doy(t_days)
        # deepest around mid-February, shallowest around mid-August
        seasonal = 0.5 + 0.5 * math.cos(2 * math.pi * (doy - 46) / 365.25)
        mld = 18.0 + 62.0 * seasonal
        return mld * (1.0 + 0.45 * self.storm)

    def mixing(self, t_days):
        """Turbulent intensity, 0..1."""
        mld = self.mixed_layer_depth(t_days)
        return min(1.0, 0.28 + 0.55 * (mld / Z_MAX) + 0.6 * self.storm)

    def current(self, t_days, z):
        """Horizontal velocity, px/day.  A semidiurnal M2 tide under a
        spring-neap envelope, plus a steady residual, both sheared with
        depth.  Everything advects together, which is what makes the
        assemblage read as one body of water rather than independent
        particles doing random walks."""
        spring_neap = 0.62 + 0.38 * math.cos(2 * math.pi * (t_days - 2.0) / 14.765)
        tide = U_TIDE * spring_neap * math.sin(2 * math.pi * t_days / T_M2)
        shear = 0.30 + 0.70 * math.exp(-z / SHEAR_Z)
        return (tide + U_RESID) * shear * (1.0 + 0.5 * self.storm)

    def temperature(self, t_days, z):
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
# 4. ORGANISMS  -  procedural morphology
# --------------------------------------------------------------------------

RADIOLARIAN, CENTRIC, PENNATE, CHAIN, CERATIUM, COPEPOD, TINTINNID = range(7)

AUTO, MIXO, HETERO = range(3)

# Who eats how.  Diatoms are strict phototrophs.  Ceratium and the
# radiolarian are mixotrophs -- they photosynthesise AND ingest, which is why
# they persist through the nutrient-starved summer when the diatoms cannot.
# Copepods and tintinnids are heterotrophs.  The chemoautotrophs are not
# agents at all; see Ecosystem.nit.
TROPHY = {
    CENTRIC: AUTO, PENNATE: AUTO, CHAIN: AUTO,
    RADIOLARIAN: MIXO, CERATIUM: MIXO,
    COPEPOD: HETERO, TINTINNID: HETERO,
}
PHOTO_KINDS = (CENTRIC, PENNATE, CHAIN)
MIXO_KINDS = (RADIOLARIAN, CERATIUM)
DRIFTER_KINDS = PHOTO_KINDS + MIXO_KINDS      # everything under MAX_PHYTO
HET_KINDS = (COPEPOD, TINTINNID)

# Visual radius as a multiple of the nominal draw radius.  A Chaetoceros
# chain throws setae out to 3.4r and spans 6r along its axis, so using the
# bare radius for separation was why everything overlapped.
EXTENT = {
    RADIOLARIAN: 1.75, CENTRIC: 1.00, PENNATE: 1.05, CHAIN: 2.60,
    CERATIUM: 1.80, COPEPOD: 1.35, TINTINNID: 1.20,
}


class Genome:
    """A handful of numbers that fully determine an individual's appearance.
    Same genome, same drawing, forever -- so a cell that divides produces two
    daughters that look like siblings, not strangers."""

    __slots__ = ("kind", "size", "sym", "ornament", "aspect", "curl", "seed")

    def __init__(self, kind, rng):
        self.kind = kind
        self.seed = rng.randrange(1 << 30)
        self.sym = rng.choice((6, 7, 8, 9, 10, 12))
        self.ornament = rng.uniform(0.3, 1.0)
        self.aspect = rng.uniform(0.25, 0.55)
        self.curl = rng.uniform(-0.5, 0.5)
        if kind == RADIOLARIAN:
            self.size = rng.uniform(9, 15)
        elif kind == CENTRIC:
            self.size = rng.uniform(8, 14)
        elif kind == PENNATE:
            self.size = rng.uniform(11, 19)
        elif kind == CHAIN:
            self.size = rng.uniform(4.5, 7.0)
        elif kind == CERATIUM:
            self.size = rng.uniform(8, 12)
        elif kind == TINTINNID:
            self.size = rng.uniform(7, 10)
        else:
            self.size = rng.uniform(8, 12)

    def child(self, rng):
        g = Genome.__new__(Genome)
        g.kind = self.kind
        g.seed = self.seed ^ rng.randrange(1 << 12)
        g.sym = self.sym
        g.ornament = max(0.2, min(1.0, self.ornament + rng.gauss(0, 0.05)))
        g.aspect = max(0.2, min(0.7, self.aspect + rng.gauss(0, 0.03)))
        g.curl = self.curl + rng.gauss(0, 0.06)
        g.size = self.size * rng.uniform(0.93, 1.07)
        return g


def draw_radiolarian(c, cx, cy, r, ang, g):
    """Spherical test, radial spines, a lattice between two shells."""
    n = g.sym
    c.circle(cx, cy, r)
    inner = r * (0.48 + 0.14 * g.ornament)
    c.circle(cx, cy, inner)
    for i in range(n):
        a = ang + 2 * math.pi * i / n
        ca = math.cos(a); sa = math.sin(a)
        # strut between the two shells
        c.line(cx + inner * ca, cy + inner * sa, cx + r * ca, cy + r * sa)
        # spine projecting beyond the test, with a terminal knob
        tip = r * (1.42 + 0.30 * g.ornament)
        c.line(cx + r * ca, cy + r * sa, cx + tip * ca, cy + tip * sa)
        c.px(int(cx + tip * ca), int(cy + tip * sa))
    # pored equator: small arcs between adjacent spines
    if g.ornament > 0.55:
        for i in range(n):
            a0 = ang + 2 * math.pi * i / n
            a1 = a0 + 2 * math.pi / n
            mid = r * 0.78
            c.arc(cx, cy, mid, a0, a1)


def draw_centric(c, cx, cy, r, ang, g):
    """Coscinodiscus-like. Concentric rings and radial striae."""
    c.circle(cx, cy, r)
    c.circle(cx, cy, r * 0.72)
    if g.ornament > 0.5:
        c.circle(cx, cy, r * 0.34)
    n = int(10 + 14 * g.ornament)
    for i in range(n):
        a = ang + 2 * math.pi * i / n
        ca = math.cos(a); sa = math.sin(a)
        c.line(cx + r * 0.74 * ca, cy + r * 0.74 * sa,
               cx + r * 0.97 * ca, cy + r * 0.97 * sa)
    # central pore
    c.px(int(cx), int(cy))


def draw_pennate(c, cx, cy, r, ang, g):
    """Navicula-like boat. Two arcs, a raphe, transverse striae."""
    half = r
    width = r * g.aspect
    ca = math.cos(ang); sa = math.sin(ang)

    def to_world(u, v):
        return (cx + u * ca - v * sa, cy + u * sa + v * ca)

    top = []; bot = []
    steps = 14
    for i in range(steps + 1):
        t = -1.0 + 2.0 * i / steps
        # lens profile, pointed at both ends
        v = width * (1.0 - t * t) ** 0.62
        top.append(to_world(t * half, -v))
        bot.append(to_world(t * half, v))
    c.polyline(top)
    c.polyline(bot)
    c.line(top[0][0], top[0][1], bot[0][0], bot[0][1])
    c.line(top[-1][0], top[-1][1], bot[-1][0], bot[-1][1])
    # raphe
    p0 = to_world(-half * 0.86, 0); p1 = to_world(half * 0.86, 0)
    c.line(p0[0], p0[1], p1[0], p1[1])
    # striae
    n = int(6 + 8 * g.ornament)
    for i in range(1, n):
        t = -1.0 + 2.0 * i / n
        v = width * (1.0 - t * t) ** 0.62
        a = to_world(t * half, -v * 0.85)
        b = to_world(t * half, v * 0.85)
        c.line(a[0], a[1], b[0], b[1])


def draw_chain(c, cx, cy, r, ang, g):
    """Chaetoceros. Boxy cells in a row with long crossing setae -- the most
    instantly readable phytoplankton silhouette there is."""
    n_cells = 3 + int(g.ornament * 3)
    cw = r                       # half-width along the chain
    ch = r * 1.15                # half-height across it
    ca = math.cos(ang); sa = math.sin(ang)

    def to_world(u, v):
        return (cx + u * ca - v * sa, cy + u * sa + v * ca)

    total = n_cells * 2 * cw
    u0 = -total / 2.0
    for i in range(n_cells):
        a = u0 + i * 2 * cw
        b = a + 2 * cw
        corners = [to_world(a, -ch), to_world(b, -ch),
                   to_world(b, ch), to_world(a, ch)]
        c.polyline(corners, close=True)
        # setae from both ends of each cell, swept and curved
        for u, sgn in ((a, -1), (b, -1), (a, 1), (b, 1)):
            pts = []
            L = r * 3.4
            for k in range(5):
                t = k / 4.0
                pts.append(to_world(u + L * t * 0.30 * (1 if sgn > 0 else -1)
                                    + L * t * g.curl * 0.4,
                                    sgn * (ch + L * t)))
            c.polyline(pts)


def draw_ceratium(c, cx, cy, r, ang, g):
    """Dinoflagellate with one apical and two antapical horns."""
    ca = math.cos(ang); sa = math.sin(ang)

    def to_world(u, v):
        return (cx + u * ca - v * sa, cy + u * sa + v * ca)

    body_w = r * 0.40
    pts_l = []; pts_r = []
    steps = 10
    for i in range(steps + 1):
        t = -1.0 + 2.0 * i / steps
        v = body_w * (1.0 - t * t) ** 0.5
        pts_l.append(to_world(t * r * 0.55, -v))
        pts_r.append(to_world(t * r * 0.55, v))
    c.polyline(pts_l)
    c.polyline(pts_r)
    # girdle
    gl = to_world(0, -body_w * 0.95); gr = to_world(0, body_w * 0.95)
    c.line(gl[0], gl[1], gr[0], gr[1])
    # apical horn
    apex = to_world(-r * 0.55, 0)
    tip = to_world(-r * 1.75, r * 0.12 * g.curl)
    c.line(apex[0], apex[1], tip[0], tip[1])
    # two antapical horns
    for sgn in (-1, 1):
        base = to_world(r * 0.5, sgn * body_w * 0.6)
        mid = to_world(r * 1.05, sgn * body_w * 1.5)
        end = to_world(r * 1.45, sgn * body_w * 3.0)
        c.polyline([base, mid, end])


def draw_copepod(c, cx, cy, r, ang, g, gravid=False):
    """The grazer. Prosome, urosome, antennae, caudal setae."""
    ca = math.cos(ang); sa = math.sin(ang)

    def to_world(u, v):
        return (cx + u * ca - v * sa, cy + u * sa + v * ca)

    bw = r * 0.42
    left = []; right = []
    steps = 10
    for i in range(steps + 1):
        t = i / steps
        # teardrop: broad at the head, tapering aft
        v = bw * (1.0 - t) ** 0.5 * (0.45 + 0.55 * math.sin(math.pi * (0.25 + 0.75 * t)))
        u = -r * 0.75 + t * r * 1.15
        left.append(to_world(u, -v))
        right.append(to_world(u, v))
    c.polyline(left)
    c.polyline(right)
    c.line(left[0][0], left[0][1], right[0][0], right[0][1])
    # urosome: three tapering segments
    u = r * 0.40
    for k in range(3):
        wseg = bw * (0.34 - 0.07 * k)
        a = to_world(u, -wseg); b = to_world(u + r * 0.18, -wseg)
        d = to_world(u + r * 0.18, wseg); e = to_world(u, wseg)
        c.polyline([a, b, d, e])
        u += r * 0.18
    # caudal setae
    for sgn in (-1, 1):
        s0 = to_world(u, sgn * bw * 0.18)
        s1 = to_world(u + r * 0.55, sgn * bw * 0.55)
        c.line(s0[0], s0[1], s1[0], s1[1])
    # first antennae, swept back
    for sgn in (-1, 1):
        a0 = to_world(-r * 0.62, sgn * bw * 0.35)
        a1 = to_world(-r * 0.20, sgn * bw * 1.5)
        a2 = to_world(r * 0.45, sgn * bw * 2.3)
        c.polyline([a0, a1, a2])
    if gravid:
        eg = to_world(r * 0.42, bw * 0.9)
        c.circle(eg[0], eg[1], max(2, r * 0.20))


def draw_tintinnid(c, cx, cy, r, ang, g):
    """Ciliate in a conical lorica with a ciliary fringe at the rim.
    A heterotroph -- it eats small cells and detritus."""
    ca = math.cos(ang); sa = math.sin(ang)

    def tw(u, v):
        return (cx + u * ca - v * sa, cy + u * sa + v * ca)

    rim = r * 0.60
    L = r * 1.5
    base_u = -L * 0.35
    apex = tw(L * 0.85, 0)
    c.line(*(tw(base_u, -rim) + apex))
    c.line(*(tw(base_u, rim) + apex))

    lip = []
    for i in range(9):
        t = -1.0 + 2.0 * i / 8
        lip.append(tw(base_u - rim * 0.30 * (1 - t * t), t * rim))
    c.polyline(lip)

    for k in (0.30, 0.58):
        w = rim * (1.0 - k * 0.85)
        c.line(*(tw(base_u + L * 1.2 * k, -w) + tw(base_u + L * 1.2 * k, w)))

    for i in range(7):
        t = -1.0 + 2.0 * i / 6
        u = base_u - rim * 0.30 * (1 - t * t)
        c.line(*(tw(u, t * rim) + tw(u - r * 0.55, t * rim * 1.3)))


DRAW = {
    RADIOLARIAN: draw_radiolarian,
    CENTRIC: draw_centric,
    PENNATE: draw_pennate,
    CHAIN: draw_chain,
    CERATIUM: draw_ceratium,
    TINTINNID: draw_tintinnid,
}


# --------------------------------------------------------------------------
# 5. ECOSYSTEM  -  NPZ dynamics carried by individual agents
# --------------------------------------------------------------------------

class Agent:
    __slots__ = ("g", "x", "z", "ang", "spin", "mass", "age", "vigour",
                 "gravid", "flash", "vis", "doomed", "mode")

    def __init__(self, g, x, z, mass, rng, vis=0.02):
        self.g = g
        self.x = x
        self.z = z
        self.ang = rng.uniform(0, 2 * math.pi)
        self.spin = rng.gauss(0, 0.25)
        self.mass = mass
        self.age = 0.0
        self.vigour = 1.0
        self.gravid = False
        self.flash = 0.0
        self.vis = vis            # 0..1 visual presence. This is what stops
        self.doomed = False       # cells popping in and out of existence.
        self.mode = TROPHY[g.kind]


class Detritus:
    """Dead organic matter. Sinks, remineralises to ammonium at whatever
    depth it reaches, and can be eaten on the way down. This is what closes
    the nitrogen loop and feeds the chemoautotrophs."""

    __slots__ = ("x", "z", "mass", "offs")

    def __init__(self, x, z, mass, rng):
        self.x = x
        self.z = z
        self.mass = mass
        n = 2 + int(min(3.0, mass) * 2)
        self.offs = [(rng.gauss(0, 1.7), rng.gauss(0, 1.7)) for _ in range(n)]


def visual_radius(a):
    """Single source of truth for on-screen size, used by both the renderer
    and the separation force so the two cannot disagree."""
    return a.g.size * (0.30 + 0.70 * min(1.6, a.mass) / 1.6) * a.vis


class Ecosystem:
    def __init__(self, seed=None, start_day=0.0, track=None):
        self.rng = random.Random(seed)
        self.env = Environment(self.rng, track)
        self.track = track
        self.t = start_day
        r = self.rng
        # Depth-resolved nitrogen in two pools. New production (nitrate) and
        # regenerated production (ammonium) behave differently, and the
        # difference is exactly what the chemoautotrophs live on.
        self.no3 = [3.0 + N_DEEP * (i / NBINS) ** 1.4 for i in range(NBINS)]
        self.nh4 = [0.25] * NBINS
        self.nit = [0.06] * NBINS          # chemoautotroph biomass per bin
        self.agents = []
        self.det = []
        self.snow = [[r.uniform(0, W), r.uniform(0, H),
                      r.uniform(0.6, 2.4), r.random() < 0.30]
                     for _ in range(SNOW_COUNT)]
        for _ in range(14):
            self._spawn_drifter().vis = 1.0
        for _ in range(3):
            self._spawn_het(COPEPOD).vis = 1.0
        for _ in range(2):
            self._spawn_het(TINTINNID).vis = 1.0

    # -- helpers -----------------------------------------------------------

    def _bin(self, z):
        i = int(z / BIN_M)
        return 0 if i < 0 else (NBINS - 1 if i >= NBINS else i)

    def _spawn_drifter(self, parent=None):
        r = self.rng
        if parent is None:
            g = Genome(r.choice(DRIFTER_KINDS), r)
            z = r.uniform(2, Z_MAX * 0.85)
            # arrive at an edge and drift in, rather than appearing mid-frame
            x = r.uniform(-5, 5) if r.random() < 0.5 else r.uniform(W - 5, W + 5)
            a = Agent(g, x % W, z, r.uniform(0.5, 0.9), r, 0.02)
        else:
            g = parent.g.child(r)
            z = max(0.5, min(Z_MAX - 0.5, parent.z + r.gauss(0, 4.0)))
            a = Agent(g, (parent.x + r.gauss(0, 5.0)) % W, z, parent.mass, r,
                      0.35)          # a daughter is already a real cell
        self.agents.append(a)
        return a

    def _spawn_het(self, kind):
        r = self.rng
        a = Agent(Genome(kind, r), r.uniform(0, W), r.uniform(5, Z_MAX * 0.8),
                  r.uniform(0.8, 1.4), r, 0.02)
        self.agents.append(a)
        return a

    def _die(self, a):
        if a.doomed:
            return
        a.doomed = True
        if len(self.det) < MAX_DETRITUS and a.mass > 0.2:
            self.det.append(Detritus(a.x, a.z, a.mass * 0.8, self.rng))

    def light_at(self, z, surface, chl=None):
        if chl is None:
            chl = self.biomass / MAX_PHYTO
        return surface * math.exp(-(K_WATER + K_CHL * chl) * z)

    # -- biogeochemistry ---------------------------------------------------

    def _mix_nitrogen(self, dt, mld, mixing):
        nb = max(1, min(NBINS, int(mld / BIN_M) + 1))
        f = min(1.0, mixing * 2.4 * dt)
        for pool in (self.no3, self.nh4):
            m = sum(pool[:nb]) / nb
            for i in range(nb):
                pool[i] += (m - pool[i]) * f
        kd = min(0.32, 1.2 * dt)
        for pool in (self.no3, self.nh4):
            prev = pool[:]
            for i in range(1, NBINS - 1):
                pool[i] = prev[i] + kd * (prev[i - 1] - 2 * prev[i] + prev[i + 1])
        self.no3[NBINS - 1] += (N_DEEP - self.no3[NBINS - 1]) * min(1.0, 0.7 * dt)
        for i in range(NBINS):
            self.no3[i] = max(0.01, min(N_DEEP * 1.3, self.no3[i]))
            self.nh4[i] = max(0.0, min(N_DEEP * 0.6, self.nh4[i]))

    def _nitrify(self, dt, surface, chl):
        """Chemoautotrophy. These organisms take no light at all -- they run
        on the chemical energy of oxidising ammonium to nitrate. Nitrification
        is photoinhibited in the real ocean, which is precisely why this
        population lives below the euphotic zone."""
        for i in range(NBINS):
            I = self.light_at((i + 0.5) * BIN_M, surface, chl)
            inhib = 1.0 / (1.0 + (I / I_NIT_INHIB) ** 2)
            nh4 = self.nh4[i]
            rate = V_NIT * (nh4 / (nh4 + K_NIT)) * inhib * self.nit[i]
            rate = min(rate, nh4 * 0.6 / max(dt, 1e-9))
            self.nh4[i] -= rate * dt
            self.no3[i] += rate * dt
            self.nit[i] += (rate * Y_NIT - LOSS_NIT * self.nit[i]) * dt
            self.nit[i] = max(0.004, min(1.2, self.nit[i]))

    def _step_detritus(self, dt):
        keep = []
        for d in self.det:
            d.z += W_DET * dt
            loss = d.mass * REMIN * dt
            d.mass -= loss
            self.nh4[self._bin(d.z)] += loss * 0.85
            if d.z >= Z_MAX:
                self.nh4[NBINS - 1] += d.mass * 0.5
            elif d.mass > 0.08:
                keep.append(d)
        self.det = keep

    def _ingest(self, a, dt, small_only):
        """Heterotrophy. Mixotrophs and heterotrophs share this; they differ
        only in what they accept and how fast. Returns mass ingested."""
        rng = self.rng
        got = 0.0
        reach = 30.0 if a.g.kind == COPEPOD else 18.0
        zreach = reach * 0.30
        for d in self.det:
            if abs(d.z - a.z) < zreach and abs(d.x - a.x) < reach:
                if rng.random() < 1.2 * dt:
                    take = min(d.mass, 0.45)
                    d.mass -= take
                    got += take * 0.55
                    break
        rate = 2.0 if a.g.kind == COPEPOD else 0.85
        for p in self.agents:
            if p is a or p.doomed or p.g.kind not in DRIFTER_KINDS:
                continue
            if small_only and p.mass > 1.05:
                continue
            if abs(p.z - a.z) < zreach and abs(p.x - a.x) < reach:
                if rng.random() < rate * dt:
                    self._die(p)
                    got += p.mass * 0.45
                    self.nh4[self._bin(p.z)] += p.mass * 0.22   # sloppy feeding
                    break
        return got

    # -- main step ---------------------------------------------------------

    def step(self, dt):
        if dt <= 0:
            return
        rng = self.rng
        env = self.env
        env.step(dt)
        self.t += dt
        t = self.t

        surface = env.surface_light(t)
        mld = env.mixed_layer_depth(t)
        mixing = env.mixing(t)
        chl = self.biomass / MAX_PHYTO
        daylight = min(1.0, surface / 0.20)

        self._mix_nitrogen(dt, mld, mixing)
        self._nitrify(dt, surface, chl)
        self._step_detritus(dt)
        # Export flux: the unresolved fine fraction of dead matter also
        # sinks and remineralises. Without this the deep water has no
        # ammonium and the chemoautotrophs have nothing to oxidise.
        export = self.biomass * 0.022 * dt
        lo = NBINS // 2
        for i in range(lo, NBINS):
            self.nh4[i] += export / (NBINS - lo)

        drifters = [a for a in self.agents
                    if a.g.kind in DRIFTER_KINDS and not a.doomed]
        hets = [a for a in self.agents
                if a.g.kind in HET_KINDS and not a.doomed]
        n_drift = len(drifters)
        n_cope = sum(1 for h in hets if h.g.kind == COPEPOD)
        n_tint = len(hets) - n_cope
        born = []

        # ---- advection and fade, common to everything --------------------
        for a in self.agents:
            a.x += env.current(t, a.z) * dt
            turb = mixing * (1.0 if a.z < mld else 0.35)
            a.x += rng.gauss(0, 26.0 * turb) * dt
            a.z += rng.gauss(0, 30.0 * turb) * dt
            a.age += dt
            a.flash = max(0.0, a.flash - dt * 6.0)
            if a.doomed:
                a.vis -= dt / DIE_D
            else:
                a.vis = min(1.0, a.vis + dt / EMERGE_D)

        # ---- phototrophs and mixotrophs ----------------------------------
        for a in drifters:
            i = self._bin(a.z)
            I = self.light_at(a.z, surface, chl)
            f_light = I / (I + I_K)
            nh4 = self.nh4[i]
            no3 = self.no3[i]
            # ammonium is cheaper, so it is taken preferentially and it
            # suppresses nitrate uptake
            f_nh4 = nh4 / (nh4 + K_S)
            f_no3 = (no3 / (no3 + K_S)) * math.exp(-PSI * nh4)
            f_nut = min(1.0, f_nh4 + f_no3)
            f_temp = 1.8 ** ((env.temperature(t, a.z) - 11.0) / 10.0)

            ingested = 0.0
            if a.mode == MIXO:
                ingested = self._ingest(a, dt, small_only=True)
                mu = (0.62 * MU_MAX * f_light * f_nut * f_temp
                      - RESPIRATION - 0.12 * min(1.3, mld / Z_MAX))
            else:
                mu = (MU_MAX * f_light * f_nut * f_temp
                      - RESPIRATION - 0.34 * min(1.3, mld / Z_MAX))

            grow = a.mass * mu * dt
            a.mass = min(2.45, a.mass + grow + ingested * 0.6)
            a.vigour = max(0.0, min(1.0, a.vigour + (mu * 2.2 - 0.10) * dt))
            a.ang += a.spin * dt * 2.0

            if grow > 0:
                want = grow * 0.16
                share = f_nh4 / max(1e-6, f_nh4 + f_no3)
                take = min(nh4, want * share)
                self.nh4[i] = max(0.0, nh4 - take)
                self.no3[i] = max(0.01, self.no3[i] - (want - take))

            if a.mode == MIXO:
                # motile: swims up for light by day, down for nutrients at
                # night. The opposite phase to the copepods.
                target = 5.0 + 30.0 * (1.0 - daylight)
                a.z += (target - a.z) * min(1.0, 1.2 * dt)
            else:
                drag = 0.45 if a.g.kind == CHAIN else 1.0
                a.z += (0.4 + 3.6 * (1.0 - a.vigour)) * drag * dt

            if a.mass > 1.9 and n_drift + len(born) < MAX_PHYTO:
                a.mass *= 0.5
                a.age = 0.0
                a.flash = 1.0
                born.append(a)
            if a.z > Z_MAX or a.mass < 0.16 or a.age > 55:
                self._die(a)

        # ---- heterotrophs -------------------------------------------------
        for a in hets:
            if a.g.kind == COPEPOD:
                # diel vertical migration, with individual variation so they
                # do not sweep up and down as one rigid block
                target = 7.0 + 14.0 * a.g.curl + 34.0 * daylight
                a.z += (target - a.z) * min(1.0, 2.2 * dt)
                a.mass += self._ingest(a, dt, small_only=False) * 1.4
                a.mass -= 0.20 * dt
                cap_ok = n_cope + sum(1 for b in born if b.g.kind == COPEPOD) < MAX_ZOO
            else:
                target = 9.0 + 24.0 * (0.5 + 0.5 * a.g.curl)
                a.z += (target - a.z) * min(1.0, 0.5 * dt)
                a.mass += self._ingest(a, dt, small_only=True) * 1.1
                a.mass -= 0.16 * dt
                cap_ok = n_tint + sum(1 for b in born if b.g.kind == TINTINNID) < 4
            a.spin += rng.gauss(0, 2.5) * dt
            a.spin *= math.exp(-4.0 * dt)          # dt-consistent damping
            a.ang += a.spin * dt
            a.gravid = a.mass > 1.9
            if a.mass > 2.4 and cap_ok:
                a.mass = 1.1
                born.append(a)
            if a.mass < 0.35 or a.age > 90:
                self._die(a)

        # ---- births -------------------------------------------------------
        for parent in born:
            if parent.g.kind in DRIFTER_KINDS:
                self._spawn_drifter(parent)
            else:
                c = self._spawn_het(parent.g.kind)
                c.x = (parent.x + rng.gauss(0, 8)) % W
                c.z = parent.z
                c.mass = 0.7

        # ---- remove only once fully faded out ------------------------------
        self.agents = [a for a in self.agents if a.vis > 0.0]

        # ---- a resilient overwintering community: never a bare column ------
        n_phyto = sum(1 for a in self.agents if a.g.kind in DRIFTER_KINDS)
        if n_phyto < 10 and rng.random() < 2.5 * dt:
            self._spawn_drifter().mass = rng.uniform(0.35, 0.60)
        if sum(1 for a in self.agents if a.g.kind == COPEPOD) < 1 and rng.random() < 0.8 * dt:
            self._spawn_het(COPEPOD)
        if sum(1 for a in self.agents if a.g.kind == TINTINNID) < 1 and rng.random() < 0.6 * dt:
            self._spawn_het(TINTINNID)

        # ---- marine snow ---------------------------------------------------
        zpx = (H - TOP_M - BOT_M) / Z_MAX
        for s in self.snow:
            s[1] += (16.0 + 30.0 * s[2]) * dt
            s[0] = (s[0] + env.current(t, max(0.0, (s[1] - TOP_M) / zpx)) * dt * 0.7) % W
            if s[1] > H:
                s[1] = -2.0
                s[0] = rng.uniform(0, W)

        # ---- separation: a layout force, not physics -----------------------
        rate = min(1.0, dt * 26.0)
        ags = self.agents
        n = len(ags)
        rad = [EXTENT[a.g.kind] * visual_radius(a) for a in ags]
        for i in range(n):
            a = ags[i]
            ra = rad[i]
            for j in range(i + 1, n):
                b = ags[j]
                dx = b.x - a.x
                if dx > W * 0.5:
                    dx -= W
                elif dx < -W * 0.5:
                    dx += W
                dz = (b.z - a.z) * zpx
                d2 = dx * dx + dz * dz
                want = (ra + rad[j]) * 0.58
                if 0.25 < d2 < want * want:
                    d = math.sqrt(d2)
                    push = (want - d) * 0.5 * rate
                    ux = dx / d
                    uz = dz / d
                    a.x -= ux * push
                    b.x += ux * push
                    a.z -= uz * push / zpx
                    b.z += uz * push / zpx

        for a in self.agents:
            a.x %= W
            a.z = max(0.4, min(Z_MAX - 0.4, a.z))

    # -- diagnostics --------------------------------------------------------

    @property
    def biomass(self):
        return sum(a.mass for a in self.agents if a.g.kind in DRIFTER_KINDS)

    @property
    def n_zoo(self):
        return sum(1 for a in self.agents if a.g.kind in HET_KINDS)

    @property
    def nit_total(self):
        return sum(self.nit)


# --------------------------------------------------------------------------
# 6. RENDERER
# --------------------------------------------------------------------------

MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
          "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")

TOP_M, BOT_M = 4, 28          # margins. Were 9/26 when there was a border
                              # to clear; the footer is all that is left.


def depth_to_y(z):
    return TOP_M + (z / Z_MAX) * (H - TOP_M - BOT_M)


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

    Clean mode is not a separate render path -- it is simply every piece of
    furniture switched off, leaving organisms, detritus and marine snow on
    bare paper. On the hardware this whole object collapses to two bits in a
    config byte and `toggle_clean` becomes the KEY button."""

    __slots__ = ("plate", "hud", "chemo", "snow", "_saved")

    def __init__(self, plate=True, hud=True, chemo=True, snow=True):
        self.plate = plate
        self.hud = hud
        self.chemo = chemo
        self.snow = snow
        self._saved = None

    @property
    def clean(self):
        return not (self.plate or self.hud)

    def toggle_clean(self):
        """Remembers what was on, so leaving clean mode restores the exact
        view you had rather than a default."""
        if self.clean:
            self.plate, self.hud = self._saved or (True, True)
            self._saved = None
        else:
            self._saved = (self.plate, self.hud)
            self.plate = False
            self.hud = False


_STIPPLE = None


def _stipple_points():
    """A fixed point set with fixed ranks. Reusing it every frame means the
    chemoautotroph haze changes density without shimmering."""
    global _STIPPLE
    if _STIPPLE is None:
        r = random.Random(20260726)
        _STIPPLE = [(r.randrange(9, W - 9), r.randrange(TOP_M + 2, H - BOT_M - 2),
                     r.random()) for _ in range(1100)]
    return _STIPPLE


DEFAULT_VIEW = View()


def render(eco, canvas, view=DEFAULT_VIEW, track=None, day=None):
    canvas.clear()
    zpx = (H - TOP_M - BOT_M) / Z_MAX

    # chemoautotrophs: too small and too numerous to be agents, so they are
    # drawn as a stipple whose density follows the nitrifier population.
    # They fill the deep water that used to be dead space.
    if view.chemo:
        for (x, y, rank) in _stipple_points():
            i = min(NBINS - 1, max(0, int(((y - TOP_M) / zpx) / BIN_M)))
            if rank < eco.nit[i] * 0.40:
                canvas.px(x, y)

    if view.snow:
        for s in eco.snow:
            canvas.px(int(s[0]), int(s[1]))
            if s[3]:
                canvas.px(int(s[0]) + 1, int(s[1]))

    for d in eco.det:
        y = depth_to_y(d.z)
        for (ox, oy) in d.offs:
            canvas.px(int(d.x + ox), int(y + oy))

    for a in eco.agents:
        if a.vis <= 0.03:
            continue
        r = visual_radius(a)
        if r < 1.2:
            continue
        y = depth_to_y(a.z)
        ext = EXTENT[a.g.kind] * r
        # draw across the seam so nothing teleports when it wraps
        for xoff in (0.0, -W, W):
            xx = a.x + xoff
            if xx + ext < 0 or xx - ext > W:
                continue
            if a.g.kind == COPEPOD:
                draw_copepod(canvas, xx, y, r, a.ang, a.g, a.gravid)
            else:
                DRAW[a.g.kind](canvas, xx, y, r, a.ang, a.g)
            if a.flash > 0.25:
                canvas.circle(xx, y, r * 1.9)

    if view.plate:
        draw_plate(eco, canvas, track, day)
    if view.hud:
        draw_hud(eco, canvas)


def draw_plate(eco, c, track=None, day=None):
    """The footer, and nothing else.

    This used to be a full plate -- double border, depth scale with numbered
    ticks, a tide staff. All of it went. The borderless views turned out to
    look better than the framed one, and once the border is gone the depth
    scale has nothing to sit against and reads as clutter. What survives is
    the three things you actually want to know: what this is, where it is,
    and how far through.

    The progress bar is a hairline with a single tick, because the number of
    days is not interesting and the proportion is.

    Two lines, and the columns mean something: identity on the left, state on
    the right. So the eye learns in a day that the right-hand column is where
    the answer to 'where are we and what are we doing' lives."""
    y = H - 24
    text(c, 8, y, "DRIFT")

    if track is not None and day is not None:
        la, lo = track.position(day)
        pos = "%02d%s%02d'%s  %03d%s%02d'%s" % (
            abs(int(la)), "\xb0", int(abs(la) % 1 * 60), "N" if la >= 0 else "S",
            abs(int(lo)), "\xb0", int(abs(lo) % 1 * 60), "E" if lo >= 0 else "W")
        text(c, W - 8 - text_width(pos), y, pos)
        st = track.status(day)
        text(c, W - 8 - text_width(st), y + 9, st)
        f = day / track.days[-1]
    else:
        # standing at Melbourn, no voyage: fall back to the date
        text(c, W - 8 - text_width(date_label(eco.t)), y, date_label(eco.t))
        f = (eco.t % 365.25) / 365.25

    by = H - 6
    c.line(8, by, W - 9, by)
    x = 8 + (W - 17) * f
    c.line(x, by - 3, x, by + 1)


def draw_hud(eco, c):
    e = eco.env
    surf = e.surface_light(eco.t)
    nsurf = eco.no3[0] + eco.nh4[0]
    lines = [
        "T %s  Y%d" % (date_label(eco.t), int(eco.t / 365.25) + 1),
        "LIGHT %3d  CLOUD %3d" % (int(surf * 100), int(e.cloud * 100)),
        "MLD %3dM  MIX %3d" % (int(e.mixed_layer_depth(eco.t)),
                               int(e.mixing(eco.t) * 100)),
        "TIDE %+4d PX/D" % int(e.current(eco.t, 0.0)),
        "NO3 %4.1f  NH4 %4.1f" % (eco.no3[0], eco.nh4[0]),
        "SURF N %4.1f" % nsurf,
        "CHEMO %4.1f" % eco.nit_total,
        "BIOM %5.1f  DET %2d" % (eco.biomass, len(eco.det)),
        "N %2d  HET %2d" % (len(eco.agents), eco.n_zoo),
    ]
    y = 26
    for ln in lines:
        text(c, 12, y, ln)
        y += 8


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
    from PIL import Image
    import numpy as np
    arr = np.frombuffer(bytes(canvas.buf), dtype=np.uint8).reshape(H, W)
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
    view = View(hud=False)
    targets = [30, 105, 135, 175, 240, 320]
    saved = []
    i = 0
    while eco.t < 340 and i < len(targets):
        eco.step(1.0 / 24.0)
        if eco.t >= targets[i]:
            render(eco, canvas, view)
            path = os.path.join(outdir, "drift_%03d.png" % targets[i])
            to_pil(canvas).resize((W * 2, H * 2), 0).save(path)
            saved.append((path, date_label(eco.t), eco.biomass,
                          len(eco.agents), eco.n_zoo,
                          eco.no3[0] + eco.nh4[0], eco.nit_total))
            i += 1
    for p, d, b, n, z, nut, chemo in saved:
        print("%s  %s  biomass %5.1f  agents %2d  het %2d  surfN %4.1f  chemo %4.1f"
              % (p, d, b, n, z, nut, chemo))


LUT = None   # built lazily, preview only


def preview():
    global LUT
    import pygame
    import numpy as np
    LUT = np.array([[228, 228, 224], [22, 22, 24]], dtype=np.uint8)
    pygame.init()
    screen = pygame.display.set_mode((W * SCALE, H * SCALE))
    pygame.display.set_caption("Drift")
    clock = pygame.time.Clock()

    from voyage import Track
    from mapview import Coast
    from screens import Rotation, Compositor, GALLERY

    track = Track()
    coast = Coast("data/coast.bin")
    eco = Ecosystem(seed=None, start_day=0.0, track=track)
    canvas = Canvas(W, H)
    view = View()
    rot = Rotation(GALLERY)
    comp = Compositor()
    speed = PRESETS[1]          # 1 min per second: a voyage day every 24 real
    paused = False              # minutes, the whole circumnavigation in 17 days
    toast = 0.0                 # seconds left on the transient speed readout
    shot = 0

    surf = pygame.Surface((W, H))
    running = True
    while running:
        real_dt = clock.tick(20) / 1000.0
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
                elif e.key == pygame.K_h:
                    view.hud = not view.hud
                elif e.key == pygame.K_p:
                    view.plate = not view.plate
                elif e.key == pygame.K_n:
                    view.chemo = not view.chemo
                elif e.key == pygame.K_m:
                    rot.skip()
                elif e.key == pygame.K_r:
                    eco = Ecosystem(seed=None, start_day=eco.t, track=track)
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

        if not paused:
            dt = real_dt * speed
            # sub-step so fast-forward stays numerically sane
            steps = max(1, min(64, int(dt / 0.015) + 1))
            for _ in range(steps):
                eco.step(dt / steps)
            # home again. The second circumnavigation gets a fresh seed, so
            # the same ocean grows a different community -- one line, and it
            # is the difference between a loop and a repeat.
            if eco.t >= track.days[-1]:
                eco = Ecosystem(seed=None, start_day=0.0, track=track)
            rot.advance(real_dt)

        toast = max(0.0, toast - real_dt)

        comp.frame(canvas, rot, eco, track, coast, view)
        status = speed_label(speed) + ("  PAUSED" if paused else "")
        if view.hud:
            text(canvas, 12, H - 38, status)
        elif toast > 0.0:
            # clean mode keeps its own counsel, except for a moment after you
            # touch the wheel
            text(canvas, 8, H - 10, status)

        # blit the 1-bit buffer via numpy -- a per-pixel Python loop here
        # costs ~96k operations a frame and stutters badly
        arr = np.frombuffer(bytes(canvas.buf), dtype=np.uint8).reshape(H, W)
        pygame.surfarray.blit_array(surf, np.transpose(LUT[arr], (1, 0, 2)))
        pygame.transform.scale(surf, (W * SCALE, H * SCALE), screen)
        pygame.display.flip()

    pygame.quit()


def voyage_sweep(outdir, every=30, seed=7):
    """Run the whole circumnavigation headless and lay it out as a contact
    sheet, one panel per `every` days.

    This is the only test that matters. Everything else checks that a piece
    works; this checks whether the object is any good -- and it is the thing
    Stage 6 is built around, so it exists now, in embryo, rather than being
    written at the end when it is too late to change anything."""
    import os
    from voyage import Track
    from PIL import Image

    os.makedirs(outdir, exist_ok=True)
    track = Track()
    eco = Ecosystem(seed=seed, start_day=0.0, track=track)
    canvas = Canvas(W, H)
    view = View(hud=False)
    total = track.days[-1]

    tiles, log = [], []
    nxt = 0.0
    while eco.t < total:
        eco.step(1.0 / 12.0)
        if eco.t >= nxt:
            render(eco, canvas, view, track, eco.t)
            tiles.append(to_pil(canvas))
            la, lo = track.position(eco.t)
            log.append((int(eco.t), la, lo, eco.env.temperature(eco.t, 2.0),
                        eco.env.mixed_layer_depth(eco.t), eco.biomass,
                        len(eco.agents), eco.n_zoo, track.status(eco.t)))
            nxt += every

    cols = 9
    rows = (len(tiles) + cols - 1) // cols
    g = 6
    sheet = Image.new("L", (cols * (W + g) + g, rows * (H + g) + g), 245)
    for i, t in enumerate(tiles):
        sheet.paste(t, (g + (i % cols) * (W + g), g + (i // cols) * (H + g)))
    path = os.path.join(outdir, "voyage.png")
    sheet.save(path)

    with open(os.path.join(outdir, "voyage.csv"), "w") as f:
        f.write("day,lat,lon,sst,mld,biomass,agents,zoo,status\n")
        for r in log:
            f.write("%d,%.2f,%.2f,%.1f,%.0f,%.1f,%d,%d,%s\n" % r)

    bio = [r[5] for r in log]
    n = [r[6] for r in log]
    print("%s  %d panels" % (path, len(tiles)))
    print("biomass  min %5.1f  median %5.1f  max %5.1f"
          % (min(bio), sorted(bio)[len(bio) // 2], max(bio)))
    print("agents   min %5d  median %5d  max %5d"
          % (min(n), sorted(n)[len(n) // 2], max(n)))
    empty = sum(1 for v in n if v < 6)
    print("panels with fewer than 6 organisms: %d of %d" % (empty, len(n)))
    return log


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--stills":
        stills(sys.argv[2])
    elif len(sys.argv) > 2 and sys.argv[1] == "--voyage":
        voyage_sweep(sys.argv[2])
    else:
        preview()
