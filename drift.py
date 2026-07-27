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
    v           next voyage
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

    python3 drift.py beagle     # or any key in voyage.VOYAGES

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
TARGET_FPS = 20            # preview frame rate. Both this and SWIM_SCALE are
                           # judgements about how a moving thing looks, so
                           # they are set with tools/tune.py rather than by
                           # reasoning, and pasted back here.

LAT = 52.0800              # Melbourn
LON = 0.0200

Z_MAX = 55.0              # metres of water column mapped to the panel height
MAX_PHYTO = 30             # separate caps, or phytoplankton crowd out the
MAX_ZOO = 7                # grazers entirely during a bloom
IMMIGRATION = 0.35         # background arrivals per day even at anchor: the
                           # "everything is everywhere" term, now subordinate
                           # to advection.

# --- advection -----------------------------------------------------------
# The community was grown in place, which is the right model for a moored
# instrument and the wrong one for a ship. Drake makes 80 to 180 km on a good
# day; the panel is showing NEW WATER every day or two, so the community is
# overwhelmingly carried in from ahead rather than descended from what was
# there yesterday.
#
# This is not a refinement. The satellite check said the drivers correlate
# with real chlorophyll at rho +0.68 and the population's response at +0.03,
# and that smoothing recovered nothing -- a population carrying a memory of
# weeks was being towed through water that changes in days, so its biomass
# reflected where it was in its own internal cycle rather than the water it
# was in. No parameter fixes a timescale mismatch.
FLUSH_PER_100KM = 0.55     # fraction of the field replaced per day at 100
                           # km/day. Residence half-life about 1.3 days under
                           # way, which is fast enough to track the water and
                           # slow enough to watch a cell drift and divide.
CAP_EXP = 0.45             # n_visible goes as capacity^0.45 -- this is the
                           # compression from the plan's section 1, which
                           # until now was never actually implemented: the
                           # agent count was capped and culled instead, which
                           # is a different thing and a worse one.
CAP_SCALE = 13.0
N_FLOOR = 9                # the panel is never bare
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
K_S = 1.20                 # nutrient half-saturation. Was 0.45, which is
                           # under half the published value for a large
                           # diatom (1.25 mmol/m3, Litchman 2006) and, more
                           # to the point, low enough that a subtropical gyre
                           # saturated it and bloomed.
K_WATER = 0.035            # background light attenuation, /m
K_CHL = 0.055               # extra attenuation per unit biomass (self-shading)
N_DEEP = 13.0              # deep nutrient reservoir
GRAZE_RADIUS = 26.0        # metres... artistic licence, see note below
RESPIRATION = 0.06         # per day, at the reference size. Scaled
                           # allometrically per type -- see RESP_EXP.
K_PREY = 10.0              # prey half-saturation, in agents. See _graze_f.

# --- picoplankton --------------------------------------------------------
# Not agents. A 0.7 um Prochlorococcus is a thousandth of a pixel, and there
# are a hundred thousand of them per millilitre -- they are the single largest
# pool of living carbon on the track and they cannot be drawn as individuals.
# So they are a scalar per depth bin, rendered as the stipple.
#
# Carrying them is not decoration. They are what a subtropical gyre is
# actually made of, they are the prey the microzooplankton had none of, and
# they are what a mixotroph eats when there is nothing else. Without them the
# gyres had no small-cell class at all, and the smallest thing that WAS
# resolved -- a 30 um pennate diatom -- inherited the ecological role of a
# picoplankton without paying any of its costs.
MU_PICO = 1.70             # /day. Small, fast, shade-adapted.
K_PICO = 0.10              # the lowest half-saturation in the model, which is
                           # the whole reason they own the oligotrophic ocean
I_K_PICO = 0.045           # shade-adapted relative to the larger cells
LOSS_PICO = 0.16
T_OPT_PICO, T_W_PICO = 24.0, 13.0     # warm-restricted (Flombaum et al. 2013)
PICO_MAX = 4.0
PICO_GRAZE = 0.55          # how fast a microzooplankton clears its bin

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
            return N_DEEP
        la, lo = self.where(t_days)
        n = self.ocean.nitrate(la, lo, t_days)
        if n is None:
            return N_DEEP
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
        if self.ocean is not None:
            la, lo = self.where(t_days)
            sst = self.ocean.sst(la, lo, t_days)
            if sst is not None:
                surf = sst + self.temp_anomaly
                mld = self.mixed_layer_depth(t_days)
                if z <= mld:
                    return surf
                deep = min(surf, 4.0 + 8.0 * math.cos(math.radians(la)))
                return surf - (surf - deep) * min(1.0, (z - mld) / 40.0)
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

(RADIOLARIAN, CENTRIC, PENNATE, CHAIN, CERATIUM, COPEPOD, TINTINNID,
 COCCO, FLAGELLATE, THALASSIO, RHIZO, CORETHRON, ACANTHARIA, FORAM,
 ORNITHO, TRICHO, SALP, KRILL) = range(18)

AUTO, MIXO, HETERO = range(3)

KIND_NAME = {
    RADIOLARIAN: "radiolarian", CENTRIC: "centric", PENNATE: "pennate",
    CHAIN: "chain", CERATIUM: "ceratium", COPEPOD: "copepod",
    TINTINNID: "tintinnid", COCCO: "cocco", FLAGELLATE: "flagellate",
    THALASSIO: "thalassio", RHIZO: "rhizo", CORETHRON: "corethron",
    ACANTHARIA: "acantharia", FORAM: "foram", ORNITHO: "ornitho",
    TRICHO: "tricho", SALP: "salp", KRILL: "krill",
}

# Who eats how.  Diatoms are strict phototrophs.  Ceratium and the
# radiolarian are mixotrophs -- they photosynthesise AND ingest, which is why
# they persist through the nutrient-starved summer when the diatoms cannot.
# Copepods and tintinnids are heterotrophs.  The chemoautotrophs are not
# agents at all; see Ecosystem.nit.
TROPHY = {
    CENTRIC: AUTO, PENNATE: AUTO, CHAIN: AUTO, COCCO: AUTO,
    FLAGELLATE: AUTO, THALASSIO: AUTO, RHIZO: AUTO, CORETHRON: AUTO,
    TRICHO: AUTO,
    RADIOLARIAN: MIXO, CERATIUM: MIXO, ACANTHARIA: MIXO, FORAM: MIXO,
    ORNITHO: MIXO,
    COPEPOD: HETERO, TINTINNID: HETERO, SALP: HETERO, KRILL: HETERO,
}
PHOTO_KINDS = (CENTRIC, PENNATE, CHAIN, COCCO, FLAGELLATE, THALASSIO,
               RHIZO, CORETHRON, TRICHO)
MIXO_KINDS = (RADIOLARIAN, CERATIUM, ACANTHARIA, FORAM, ORNITHO)
DRIFTER_KINDS = PHOTO_KINDS + MIXO_KINDS      # everything under MAX_PHYTO
HET_KINDS = (COPEPOD, TINTINNID, SALP, KRILL)

# Trichodesmium fixes its own nitrogen, so nothing else in the model applies
# to it in the usual way: no N limitation at all, a hard temperature floor,
# and an iron demand twenty-five times everyone else's because nitrogenase
# carries fifteen iron atoms per subunit (Berman-Frank et al. 2001, measured
# Fe:C of 180-214 against 1-7 for a diatom). Those three numbers are the
# entire reason the subtropical gyres are habitable, and the reason
# Trichodesmium is abundant in the dust-fed Atlantic and scarce in the
# iron-poor Pacific.
DIAZOTROPHS = (TRICHO,)
DIAZO_T_MIN = 20.0         # Breitbarth et al. 2007: fixation stops below this
DIAZO_FE_COST = 25.0


# --- swimming ------------------------------------------------------------
#
# At one simulated second per real second the panel was completely still: the
# tidal current is 0.0003 px/s, the turbulent jitter the same, and an organism
# took twenty-five days to rotate once. Which is correct in metres and wrong
# on the panel -- because the panel already magnifies SIZE by about a hundred
# thousand and does not magnify the depth axis at all. It is inconsistent by
# construction, and the question is only which scale the motion should follow.
#
# It should follow the drawing. A copepod rendered twenty pixels long that
# moves a pixel an hour is inconsistent with its own picture, and the eye
# reads the picture. So swimming speed is expressed in BODY LENGTHS per
# second -- which is the one number that survives the magnification -- and
# multiplied by the drawn size.
#
# Values are real. Ciliates are the fastest things in the sea relative to
# their size; dinoflagellates are next; copepods cruise at about a body
# length a second and dart at a hundred; diatoms and rhizarians do not swim at
# all and only sink and tumble.
SWIM_BL = {
    FLAGELLATE: 14.0, TINTINNID: 8.0, KRILL: 3.0, CERATIUM: 2.0,
    ORNITHO: 1.6, COPEPOD: 1.1, SALP: 0.6,
}
SWIM_SCALE = 0.22          # global damper, set by eye: the fastest thing
                           # crosses the panel in about ten seconds

# Swimming runs at REAL time, not simulated time.
#
# It is the same class of deliberate lie as drawing a 60 micron diatom twenty
# pixels across, and it is forced by the same thing: the speed control spans
# six orders of magnitude and swimming does not. Scaled with the calendar, a
# tintinnid moves 65 px between frames at the default 1 MIN/SEC and 2,853 px
# at 1 DAY/SEC -- it stops being an organism and becomes noise. Held at real
# time it stays around 20 px/s at every setting, which also keeps it in a
# sensible ratio to the tidal drift at the default speed.
#
# The ecology is unaffected: swimming is a rendering behaviour, and the
# horizontal displacement it produces is not something any equation reads.
TURN_TAU = {               # seconds before a heading decorrelates. Ciliates
    FLAGELLATE: 3.0, TINTINNID: 4.0, CERATIUM: 12.0, ORNITHO: 14.0,
    COPEPOD: 9.0, KRILL: 14.0, SALP: 25.0,
}                          # spiral tightly; a salp holds a course.
TUMBLE_S = 90.0            # seconds for a non-swimmer to turn once in shear

# Per-grazer housekeeping. Which of them migrate vertically, how efficiently
# each converts what it eats, and how many of each the panel will carry.
MIGRATORS = (COPEPOD, KRILL)
HET_ASSIM = {COPEPOD: 1.4, TINTINNID: 1.1, KRILL: 1.3, SALP: 1.6}
# Per class, and they must sum to no more than MAX_ZOO or the total cap is a
# fiction that only the seeding path respects.
HET_CAP = {COPEPOD: 3, TINTINNID: 2, KRILL: 2, SALP: 2}

# Visual radius as a multiple of the nominal draw radius.  A Chaetoceros
# chain throws setae out to 3.4r and spans 6r along its axis, so using the
# bare radius for separation was why everything overlapped.
# MEASURED, not estimated: every morphology drawn at four radii and twenty-four
# genomes, and the furthest ink from centre recorded. The hand-guessed values
# were wrong for half the roster and wrong by a factor of two for the chains,
# which is exactly the sort of error that shows up as unexplained overlap.
EXTENT = {
    ACANTHARIA: 1.05, CENTRIC: 1.05, CERATIUM: 2.10, CHAIN: 8.40,
    COCCO: 1.40, COPEPOD: 1.75, CORETHRON: 3.15, FLAGELLATE: 3.50,
    FORAM: 2.80, KRILL: 2.52, ORNITHO: 1.47, PENNATE: 1.05,
    RADIOLARIAN: 2.10, RHIZO: 4.90, SALP: 5.60, THALASSIO: 6.65,
    TINTINNID: 1.47, TRICHO: 3.15,
}


# --------------------------------------------------------------------------
# TRAITS
# --------------------------------------------------------------------------
#
# The point of this table is what is NOT in it.  There is no column saying
# where anything lives, and no rule anywhere that mentions a place.  Each
# organism carries a size, a growth intercept and a thermal preference; the
# ocean carries conditions; and who wins falls out.  If the panel fills with
# diatom chains off Peru it is because the model worked out that a high
# maximum growth rate beats a good nutrient affinity when nutrients are
# abundant -- not because a table said PERU -> DIATOMS.
#
# Almost everything is DERIVED from size, using published allometry rather
# than invented numbers:
#
#     mu_max  proportional to  V^-0.25     Edwards et al. 2012, marine,
#     K_N     proportional to  V^+0.30     95% CI (-0.20,-0.29) and
#     sinking proportional to  V^+0.39     (+0.26,+0.42); Ward et al. 2012
#
# and since V goes as ESD cubed, those become ESD^-0.75, ESD^+0.90 and
# ESD^+1.17.  That single trade-off -- small cells scavenge better, large
# cells grow faster in absolute terms -- is the entire engine of size-based
# biogeography, and it is why this is a two-hour refactor rather than a new
# model.
#
# The one genuine taxonomic exception, and it is the important one: Edwards
# et al. find that when you control for volume, between-taxon differences
# mostly vanish EXCEPT that diatoms grow significantly faster than
# dinoflagellates and others at the same size (p<0.001).  Ward et al. put the
# intercept at 3.8 for diatoms against 2.1 for other eukaryotes.  So diatoms
# get a higher INTERCEPT, not a different exponent.  That is the whole of
# "diatoms are the weeds", and it is one number.

ESD_REF = 50.0             # microns; the size the base rates are quoted at
MU_EXP = -0.75             # per ESD, from Edwards' V^-0.25
# ...but ONLY above about 20 microns. Extrapolating a monotonic power law down
# to a 5 micron flagellate says it grows at 4.5 divisions a day, which is
# roughly double anything ever measured -- and in the model it produced a
# super-organism with the best growth rate AND the best nutrient affinity that
# took 97% of the voyage.
#
# The real relationship is UNIMODAL. Maranon et al. 2013 showed maximum growth
# rate peaks at intermediate cell size and falls away on both sides: below the
# optimum a cell cannot shrink its metabolic machinery in proportion, so the
# advantage of being small is affinity, not speed. Which is exactly the
# trade-off the model was missing -- small cells should own the oligotrophic
# ocean because nothing else can find the nutrients, not because they are also
# the fastest thing in it.
ESD_PEAK = 20.0            # microns, where mu_max tops out
MU_EXP_SMALL = 0.45        # below the peak, growth rate RISES with size.
                           # 0.70 was too steep -- it put a nanoflagellate at
                           # 0.6 divisions a day, and they measure 1 to 2.
                           # Maranon's peak is broad, not sharp.
K_EXP = 0.90               # per ESD, from Edwards' V^+0.30
W_EXP = 1.17               # per ESD, from Ward's V^+0.39
RESP_EXP = -0.75           # Respiration goes as V^0.75, so MASS-SPECIFIC
                           # respiration goes as V^-0.25 -- the same exponent
                           # as growth, and per ESD the same -0.75. This is
                           # the large cell's half of the bargain: it grows
                           # slowly, and it also burns slowly, so it survives
                           # the gaps that starve a fast small one. Leaving it
                           # flat gave every type the same maintenance cost
                           # and quietly deleted the entire K-strategist
                           # advantage from the model.
Q10_EPPLEY = 1.066         # Eppley 1972: mu_max envelope goes as 1.066^T
T_REF = 15.0

# kind: (esd_um, intercept, T_opt, T_width, buoyancy, defence)
#   esd_um     equivalent spherical diameter. A Chaetoceros cell is ~10 um but
#              behaves as a 40 um chain, and that is what the traits should
#              see -- the chain is the organism, ecologically.
#   intercept  1.00 for diatoms, 0.55 for other eukaryotes (2.1/3.8, Ward).
#   T_opt      thermal optimum, C. The niche is Gaussian about it, riding on
#              the Eppley envelope so a warm-adapted type genuinely has a
#              higher ceiling rather than merely a shifted one.
#   T_width    and the width matters as much as the centre. The three diatoms
#              started at optima of 12, 14 and 15 with widths of 12 to 14 --
#              which is not three organisms, it is one organism with three
#              drawings, and whichever was marginally best took all three
#              niches. Chaetoceros socialis is a cold-water bloom former,
#              Coscinodiscus a temperate-to-subtropical shelf diatom; giving
#              them 8 C and 20 C with narrow widths is both truer and the
#              thing that finally makes them different organisms.
#   defence    multiplier on how readily this type is grazed. THIS IS THE
#              TRADE-OFF, and leaving it out is what made the model collapse
#              to one winner. Pure allometry says a small cell has both a
#              higher growth rate and a lower half-saturation than a large
#              one -- it is better at everything -- so with size as the only
#              axis the smallest type wins the entire ocean, and it did: 91%
#              of the voyage. What a large diatom buys with its size is not
#              a physiological advantage, it is not being eaten. Chaetoceros
#              setae are an anti-grazing structure, Coscinodiscus has a thick
#              frustule, Ceratium has horns, the radiolarian has spines.
#              Which is a happy convergence: the features that make an
#              organism worth drawing are the same ones that make it hard to
#              swallow. Coscinodiscus gets 0.30 rather than 0.50 for the same
#              reason: a heavily silicified 100 um frustule is famously
#              rejected by copepods, and at 0.50 it was strictly dominated by
#              the chain on every axis and sat at 2% of the voyage.
#   buoyancy   multiplier on the allometric sinking rate. Chains resist
#              sinking, and so does a large centric -- Coscinodiscus is mostly
#              vacuole and regulates its density, which is the whole reason a
#              cell that size is viable. At buoyancy 1.0 it sank out of a 55 m
#              column in under a week and went functionally extinct across the
#              entire voyage. Motile forms barely sink at all.
TRAITS = {
    # -- the small class. Undefended, fast, and eaten by everything: this is
    #    what the microzooplankton were missing and what a gyre runs on.
    FLAGELLATE:  (   5.0, 0.55, 18.0, 15.0, 0.00, 1.00),
    COCCO:       (   8.0, 0.55, 20.0, 12.0, 0.30, 0.45),
    THALASSIO:   (  15.0, 1.00, 10.0, 10.0, 0.40, 0.60),
    # -- diatoms, on three distinct thermal niches
    PENNATE:     (  30.0, 1.00, 15.0,  9.0, 1.00, 1.00),
    CHAIN:       (  40.0, 1.00,  8.0,  8.0, 0.45, 0.30),
    CORETHRON:   (  80.0, 1.00,  3.0,  7.0, 0.40, 0.18),
    CENTRIC:     ( 100.0, 1.00, 20.0,  9.0, 0.45, 0.30),
    RHIZO:       ( 200.0, 1.00, 18.0, 10.0, 0.12, 0.22),
    # -- the nitrogen fixer. Slow, warm-restricted, iron-hungry.
    TRICHO:      ( 500.0, 0.97, 27.0,  6.0, 0.00, 0.15),
    # Trichodesmium's intercept is set from the measurement, not guessed: it
    # yields 0.25 divisions a day at its optimum, which is what Breitbarth et
    # al. 2007 report. The intercept column is exactly where taxon-specific
    # departure from the allometry belongs, and here it is carrying a real
    # fact -- a 500 um COLONY is built of small cells, so it has small-cell
    # physiology with large-cell grazing protection. Sizing it by the colony
    # alone crushed it to 0.05 a day and it never appeared anywhere.
    # -- mixotrophs: the gyre's ornate survivors
    ORNITHO:     ( 100.0, 0.55, 27.0,  7.0, 0.05, 0.28),
    CERATIUM:    ( 150.0, 0.55, 24.0,  8.0, 0.05, 0.35),
    RADIOLARIAN: ( 300.0, 0.55, 25.0, 11.0, 0.10, 0.25),
    ACANTHARIA:  ( 400.0, 0.55, 23.0, 12.0, 0.15, 0.15),
    FORAM:       ( 500.0, 0.55, 22.0, 13.0, 0.50, 0.25),
    # -- grazers
    TINTINNID:   (  60.0, 0.55, 18.0, 12.0, 0.00, 0.60),
    COPEPOD:     ( 1500.0, 0.55, 12.0, 14.0, 0.00, 1.00),
    KRILL:       ( 6000.0, 0.55,  4.0,  8.0, 0.00, 1.00),
    SALP:        ( 5000.0, 0.55, 17.0, 12.0, 0.00, 1.00),
}

# Optimal predator:prey length ratio, PER FEEDING TYPE.
#
# A single ratio of 10 for everything is the number Ward et al. use, and it is
# a mean across all zooplankton rather than a fact about any of them. Hansen,
# Bjornsen & Hansen (1994) measured it by group, and the groups differ by more
# than an order of magnitude: copepods around 18:1, ciliates around 8:1,
# dinoflagellates close to 1:1 because they engulf prey their own size.
#
# This is not a detail. At a flat 10:1 a 1500 um copepod's optimum is a 150 um
# cell, so it grazed the large slow types hard and barely touched the small
# fast ones -- which left the smallest, fastest-growing, lowest-half-saturation
# type with the best traits in the model AND almost no predator. It took 88%
# of the entire voyage. At the measured 18:1 the copepod's optimum moves to
# 83 um, which sits between the centric and the pennate and grazes both.
#
# The lesson worth keeping: competitive exclusion here was not a bug in the
# competition. It was a missing predator.
GRAZE_RATIO = {
    COPEPOD: 18.0,          # Hansen et al. 1994
    KRILL: 60.0,            # a filter feeder: takes cells far smaller than a
                            # copepod does relative to its size
    SALP: 200.0,            # mucous-net filter, effectively unselective
    TINTINNID: 8.0,         # ciliates
    CERATIUM: 3.0,          # dinoflagellates engulf prey near their own size
    ORNITHO: 3.0,
    RADIOLARIAN: 5.0,       # large rhizarian, catches a wide range on spines
    ACANTHARIA: 5.0,
    FORAM: 5.0,
}
# Kernel width, per predator. A salp's mucous net is famously indiscriminate
# -- it takes anything from bacteria to other salps -- so a narrow log-normal
# would be the wrong shape entirely, not merely the wrong centre.
GRAZE_W = {SALP: 2.2, KRILL: 1.3}
GRAZE_SIGMA = 0.90         # width of the kernel, in natural logs. Ward et al.
# use 0.5; 0.9 here because with only five drifters the size axis is sparse
# and a narrow kernel leaves gaps that no predator covers. Stage 5's small
# forms are what let this come back to the literature value.


def _derive():
    """Precompute the per-type rates once. On the MCU this is a const table
    generated at build time; the point of computing it here is that the
    allometry stays visible in the source instead of becoming magic numbers."""
    out = {}
    for k, (esd, icept, topt, twidth, buoy, defence) in TRAITS.items():
        s = esd / ESD_REF
        if esd >= ESD_PEAK:
            mu = s ** MU_EXP
        else:
            mu = ((ESD_PEAK / ESD_REF) ** MU_EXP
                  * (esd / ESD_PEAK) ** MU_EXP_SMALL)
        out[k] = (
            icept * mu,                        # 0 growth multiplier
            s ** K_EXP,                        # 1 half-saturation multiplier
            buoy * s ** W_EXP,                 # 2 sinking multiplier
            topt, twidth,                      # 3, 4
            Q10_EPPLEY ** (topt - T_REF),      # 5 Eppley ceiling at T_opt
            math.log(esd),                     # 6 for the grazing kernel
            RESPIRATION * s ** RESP_EXP,       # 7 -> shifted, see below
            defence,                           # 8
        )
    return out


DERIVED = _derive()


def temp_factor(kind, T):
    """Eppley envelope times a Gaussian niche.

    The envelope alone would say every organism grows three times faster in
    the tropics, which is why the warm oligotrophic Pacific was blooming. The
    niche alone would lose the real fact that warm water genuinely does
    support faster maximum growth. Both together say: each type has a
    temperature it likes, and types that like warm water have a higher
    ceiling when they get it."""
    d = DERIVED[kind]
    x = (T - d[3]) / d[4]
    return d[5] * math.exp(-x * x)


def graze_pref(pred_kind, prey_kind):
    """Log-normal size preference. A copepod at 1500 um wants prey near
    150 um; a tintinnid at 60 um wants 6 um. Nothing switches on species."""
    ratio = GRAZE_RATIO.get(pred_kind, 10.0)
    sig = GRAZE_W.get(pred_kind, GRAZE_SIGMA)
    r = DERIVED[pred_kind][6] - DERIVED[prey_kind][6] - math.log(ratio)
    return math.exp(-(r * r) / (2.0 * sig * sig)) * DERIVED[prey_kind][8]


class Genome:
    """A handful of numbers that fully determine an individual's appearance.
    Same genome, same drawing, forever -- so a cell that divides produces two
    daughters that look like siblings, not strangers."""

    __slots__ = ("kind", "size", "sym", "ornament", "aspect", "curl", "seed",
                 "jitter")

    def __init__(self, kind, rng):
        self.kind = kind
        self.seed = rng.randrange(1 << 30)
        # lognormal spread on maximum growth rate, sigma ~0.35. Two cells of
        # the same type are not the same organism.
        self.jitter = math.exp(rng.gauss(0.0, 0.35))
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
        elif kind == COCCO:
            self.size = rng.uniform(3.2, 5.0)
        elif kind == FLAGELLATE:
            self.size = rng.uniform(3.0, 4.4)
        elif kind == THALASSIO:
            self.size = rng.uniform(3.0, 4.6)
        elif kind == RHIZO:
            self.size = rng.uniform(4.0, 6.5)
        elif kind == CORETHRON:
            self.size = rng.uniform(5.0, 8.0)
        elif kind == ACANTHARIA:
            self.size = rng.uniform(9, 15)
        elif kind == FORAM:
            self.size = rng.uniform(6, 10)
        elif kind == ORNITHO:
            self.size = rng.uniform(7, 11)
        elif kind == TRICHO:
            self.size = rng.uniform(5.0, 8.0)
        elif kind == SALP:
            self.size = rng.uniform(4.5, 7.0)
        elif kind == KRILL:
            self.size = rng.uniform(7, 11)
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
        # heritable, but it drifts -- so a lineage founded by a fast individual
        # stays fast for a while and then regresses, rather than either being
        # fixed forever or resampled from scratch every division
        g.jitter = max(0.35, min(3.0, self.jitter * math.exp(rng.gauss(0.0, 0.12))))
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
    # striae. Gated on size: at r under 5 the cross-lines land on adjacent
    # pixels and fill the cell in solid, so the lens silhouette -- the only
    # thing that identifies it -- disappears into a blob.
    if r < 5.0:
        return
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


# --------------------------------------------------------------------------
# The eleven added in Stage 5.
#
# One rule governs all of them, and it comes out of the measurement in the
# plan: at r = 3 an organism is about seven pixels across, and the only kind
# of feature that survives at seven pixels is an OUTLINE. Anything whose
# identity lives in interior detail becomes a blob. So each of these is
# designed around a silhouette -- a scalloped rim, a straight rod through a
# centre, a row of hoops, a needle -- and the interior detail is what appears
# as it grows, not what it depends on.
# --------------------------------------------------------------------------


def draw_coccolithophore(c, cx, cy, r, ang, g):
    """Emiliania. A sphere plated with overlapping oval coccoliths.

    The tell is the EDGE, not the plates: a coccosphere's outline is broken
    into shallow scallops where the rims of the plates stand proud. That
    survives to r = 3, where the scallops are one-pixel notches and it still
    is not a circle -- which is the whole reason this is the small organism
    the roster needed."""
    # Fewer, deeper scallops when small. At r = 3 a circumference of about
    # nineteen pixels cannot carry fourteen notches -- they alias into a
    # smooth circle, which is the one thing this must not look like.
    n = (7 if r < 5.0 else 10 + int(4 * g.ornament))
    amp = 0.24 if r < 5.0 else 0.14
    pts = []
    steps = max(14, int(r * 3))
    for i in range(steps):
        a = ang + 2 * math.pi * i / steps
        rr = r * (1.0 + amp * math.cos(n * (a - ang)))
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    c.polyline(pts, close=True)
    if r >= 5.5:
        # a few plates seen face-on across the near hemisphere
        for k in range(3):
            a = ang + 2.4 * k + g.curl
            px = cx + r * 0.42 * math.cos(a)
            py = cy + r * 0.42 * math.sin(a)
            c.ellipse(px, py, r * 0.34, r * 0.22, a + 1.2)


def draw_flagellate(c, cx, cy, r, ang, g):
    """A small naked flagellate -- cryptophyte, Micromonas, the nanoplankton
    that has no defence and no ornament and is eaten by everything.

    At r = 3 this is a dot with two hairs. Two hairs is enough: it says alive
    rather than detritus, which is the only distinction that matters at this
    size and the reason marine snow cannot be mistaken for it."""
    ca = math.cos(ang); sa = math.sin(ang)

    def tw(u, v):
        return (cx + u * ca - v * sa, cy + u * sa + v * ca)

    # Fatter than a diatom and blunter than a dinoflagellate: at r = 3 the
    # body has to read as a bulb, or two trailing flagella make it look like
    # a small Ceratium, which is a different organism in a different ocean.
    w = r * 0.78
    pts = []
    for i in range(13):
        t = -1.0 + 2.0 * i / 12
        # teardrop: blunt at the front, drawn out aft
        v = w * (1.0 - t) ** 0.55 * (1.0 + t) ** 0.85 * 0.78
        pts.append(tw(t * r, -v))
    for i in range(12, -1, -1):
        t = -1.0 + 2.0 * i / 12
        v = w * (1.0 - t) ** 0.55 * (1.0 + t) ** 0.85 * 0.78
        pts.append(tw(t * r, v))
    c.polyline(pts, close=True)
    # The two flagella have to diverge, or at small r they land on the same
    # pixels and it reads as one tail -- which is a different organism.
    for sgn in (-1, 1):
        f = []
        for k in range(5):
            t = k / 4.0
            u = r * (1.0 + 1.05 * t)
            v = sgn * (w * 0.35 + r * 0.75 * t * t) + sgn * 0.22 * r * math.sin(g.curl * 4)
            f.append(tw(u, v))
        c.polyline(f)


def draw_thalassiosira(c, cx, cy, r, ang, g):
    """Small centrics strung on a single central thread.

    The thread is the tell, not the cell. A dotted line of discs reads at any
    size, which is why this works small where a lone small centric would just
    be a ring."""
    n = 3 + int(g.ornament * 3)
    ca = math.cos(ang); sa = math.sin(ang)
    gap = r * 2.6
    u0 = -gap * (n - 1) * 0.5
    prev = None
    for i in range(n):
        u = u0 + i * gap
        px = cx + u * ca
        py = cy + u * sa
        c.circle(px, py, r)
        if r >= 4.0:
            c.px(int(px), int(py))
        if prev is not None:
            c.line(prev[0], prev[1], px, py)
        prev = (px, py)


def draw_rhizosolenia(c, cx, cy, r, ang, g):
    """A needle. Aspect twelve to one, which makes it the most elongated
    thing in the set and therefore unmistakable at any size -- there is
    nothing else it could be confused with, because nothing else is a line."""
    L = r * 3.4
    w = r * 0.30
    ca = math.cos(ang); sa = math.sin(ang)

    def tw(u, v):
        return (cx + u * ca - v * sa, cy + u * sa + v * ca)

    top = []; bot = []
    for i in range(11):
        t = -1.0 + 2.0 * i / 10
        v = w * (1.0 - t * t) ** 0.30
        top.append(tw(t * L, -v))
        bot.append(tw(t * L, v))
    c.polyline(top)
    c.polyline(bot)
    for sgn in (-1, 1):
        a = tw(sgn * L, 0)
        b = tw(sgn * L * 1.30, sgn * w * 0.5 * g.curl)
        c.line(a[0], a[1], b[0], b[1])
    if r >= 5.0:
        n = 3 + int(3 * g.ornament)
        for i in range(1, n):
            t = -1.0 + 2.0 * i / n
            p = tw(t * L, -w * 0.9)
            q = tw(t * L, w * 0.9)
            c.line(p[0], p[1], q[0], q[1])


def draw_corethron(c, cx, cy, r, ang, g):
    """Two spiky pom-poms joined by a stub. A stubby barrel with a coronet of
    long spines from each end face -- a Southern Ocean diatom, and one of the
    few things in the set whose silhouette is symmetric about both axes."""
    ca = math.cos(ang); sa = math.sin(ang)

    def tw(u, v):
        return (cx + u * ca - v * sa, cy + u * sa + v * ca)

    hl = r * 0.75
    hw = r * 0.62
    c.polyline([tw(-hl, -hw), tw(hl, -hw), tw(hl, hw), tw(-hl, hw)], close=True)
    n = 5 + int(4 * g.ornament)
    for sgn in (-1, 1):
        for i in range(n):
            f = -1.0 + 2.0 * i / (n - 1)
            a = tw(sgn * hl, f * hw)
            b = tw(sgn * (hl + r * 1.9), f * hw * 1.9 + sgn * r * 0.3 * g.curl)
            c.line(a[0], a[1], b[0], b[1])


def draw_acantharia(c, cx, cy, r, ang, g):
    """Twenty spicules, arranged as ten rods passing through one centre.

    That is Muller's law and it is exactly what makes this readable: the
    spicules are perfectly straight and they all meet, so at r = 3 it is a
    star of clean lines rather than the fuzz a radiolarian becomes. The body
    is deliberately small -- a quarter of the diameter -- because the
    body-to-spike ratio is the only thing separating it from everything else
    that is spiky."""
    body = r * 0.26
    if r >= 4.5:
        c.circle(cx, cy, body)
    else:
        c.px(int(cx), int(cy))
    # Ten rods is Muller's law and it is right at full size. At r = 3 twenty
    # spicule tips fall on a circumference of nineteen pixels and the star
    # fills in solid, so the count drops and the shape survives instead.
    n = 10 if r >= 6.0 else (7 if r >= 4.0 else 5)
    for i in range(n):
        a = ang + math.pi * i / n
        ca = math.cos(a); sa = math.sin(a)
        c.line(cx - r * ca, cy - r * sa, cx + r * ca, cy + r * sa)


def draw_foraminiferan(c, cx, cy, r, ang, g):
    """Globigerina. Four or five chambers in a spiral, each about a third
    larger than the last and overlapping it by half -- a lobed cluster of
    grapes, which is a silhouette nothing else in the set produces."""
    n = 4 if r >= 5.0 else 3
    rr = r * 0.46
    a = ang
    px, py = cx - r * 0.3, cy - r * 0.2
    for i in range(n):
        c.circle(px, py, rr)
        a += 1.55
        step = rr * 1.15
        px += step * math.cos(a)
        py += step * math.sin(a)
        rr *= 1.30
    if r >= 8.0:
        # the spinose kind: a few long radial spines from the last chamber
        for k in range(5):
            b = ang + 0.7 + k * 1.15
            cb, sb = math.cos(b), math.sin(b)
            c.line(px + rr * 0.9 * cb, py + rr * 0.9 * sb,
                   px + rr * 1.9 * cb, py + rr * 1.9 * sb)


def draw_ornithocercus(c, cx, cy, r, ang, g):
    """A small body engulfed by two enormous fenestrated sails. The most
    ornate and most asymmetric outline available, and a warm-gyre organism --
    which is the point, since the gyres are where the roster needed
    something worth looking at."""
    ca = math.cos(ang); sa = math.sin(ang)

    def tw(u, v):
        return (cx + u * ca - v * sa, cy + u * sa + v * ca)

    b = r * 0.32
    if r >= 4.5:
        c.ellipse(cx, cy, b * 1.15, b, ang)
    else:
        c.px(int(cx), int(cy))
    for sgn in (-1, 1):
        rim = []
        ribs = (2 if r < 5.0 else 4 + int(4 * g.ornament))
        for i in range(ribs + 1):
            t = -1.0 + 2.0 * i / ribs
            u = t * r * 1.05
            v = sgn * (b + r * 0.95 * (1.0 - t * t) ** 0.55)
            rim.append(tw(u, v))
            base = tw(u * 0.42, sgn * b * 0.85)
            c.line(base[0], base[1], rim[-1][0], rim[-1][1])
        c.polyline(rim)
    tip = tw(-r * 1.25, r * 0.10 * g.curl)
    apex = tw(-b * 1.1, 0)
    c.line(apex[0], apex[1], tip[0], tip[1])


def draw_trichodesmium(c, cx, cy, r, ang, g):
    """A tuft of parallel filaments with frayed ends -- the nitrogen fixer,
    and the reason the subtropical gyres are habitable at all.

    Drawn as a bundle rather than a cell because that is what you see: a
    raft of trichomes, which at sea is visible from the deck as 'sea
    sawdust'."""
    ca = math.cos(ang); sa = math.sin(ang)

    def tw(u, v):
        return (cx + u * ca - v * sa, cy + u * sa + v * ca)

    # Filament count follows the width available. At r = 3 the bundle is four
    # pixels across and eleven filaments is a solid black bar.
    n = (3 if r < 4.0 else (5 if r < 6.5 else 6 + int(5 * g.ornament)))
    L = r * 2.6
    for i in range(n):
        f = -1.0 + 2.0 * i / (n - 1)
        v = f * r * 0.72
        wob = 0.20 * r * math.sin(f * 5.0 + g.curl * 4.0)
        pts = []
        for k in range(5):
            t = -1.0 + 2.0 * k / 4
            spread = 1.0 + 0.35 * t * t          # frayed at the ends
            pts.append(tw(t * L, v * spread + wob * (1.0 - t * t)))
        c.polyline(pts)


def draw_salp(c, cx, cy, r, ang, g):
    """A chain of hooped barrels. The most distinctive silhouette on the
    whole list -- nothing else looks remotely like it, at any size."""
    ca = math.cos(ang); sa = math.sin(ang)

    def tw(u, v):
        return (cx + u * ca - v * sa, cy + u * sa + v * ca)

    n = 3 + int(g.ornament * 3)
    ul = r * 1.05
    hw = r * 0.52
    u0 = -(n - 1) * ul
    for i in range(n):
        u = u0 + i * 2 * ul
        c.polyline([tw(u - ul * 0.86, -hw), tw(u + ul * 0.86, -hw)])
        c.polyline([tw(u - ul * 0.86, hw), tw(u + ul * 0.86, hw)])
        hoops = 3 + int(3 * g.ornament)
        for k in range(hoops):
            t = -0.80 + 1.60 * k / max(1, hoops - 1)
            p = tw(u + t * ul, -hw)
            q = tw(u + t * ul, hw)
            c.line(p[0], p[1], q[0], q[1])
        e = tw(u + ul * 0.30, hw * 0.35)
        c.px(int(e[0]), int(e[1]))


def draw_krill(c, cx, cy, r, ang, g):
    """Segmented rod plus a tail fan, against the copepod's teardrop plus whip
    antennae. Those two silhouettes are the reason both can be in the set."""
    ca = math.cos(ang); sa = math.sin(ang)

    def tw(u, v):
        return (cx + u * ca - v * sa, cy + u * sa + v * ca)

    hw = r * 0.34
    L = r * 1.35
    c.polyline([tw(-L, -hw * 0.8), tw(-L * 0.35, -hw),
                tw(L * 0.55, -hw * 0.55), tw(L * 0.55, hw * 0.55),
                tw(-L * 0.35, hw), tw(-L, hw * 0.8)], close=True)
    for k in range(1, 6):
        u = -L * 0.35 + (L * 0.90) * k / 6.0
        c.line(*(tw(u, -hw * 0.9) + tw(u, hw * 0.9)))
    for sgn in (-1, 1):                        # tail fan
        a = tw(L * 0.55, sgn * hw * 0.5)
        b = tw(L * 1.25, sgn * hw * 1.7)
        d = tw(L * 1.15, 0)
        c.polyline([a, b, d])
    for sgn in (-1, 1):                        # stalked eyes and antennae
        e = tw(-L * 1.05, sgn * hw * 0.55)
        c.px(int(e[0]), int(e[1]))
        c.line(*(tw(-L, sgn * hw * 0.4) + tw(-L * 1.7, sgn * hw * 1.0)))


DRAW = {
    RADIOLARIAN: draw_radiolarian,
    CENTRIC: draw_centric,
    PENNATE: draw_pennate,
    CHAIN: draw_chain,
    CERATIUM: draw_ceratium,
    TINTINNID: draw_tintinnid,
    COCCO: draw_coccolithophore,
    FLAGELLATE: draw_flagellate,
    THALASSIO: draw_thalassiosira,
    RHIZO: draw_rhizosolenia,
    CORETHRON: draw_corethron,
    ACANTHARIA: draw_acantharia,
    FORAM: draw_foraminiferan,
    ORNITHO: draw_ornithocercus,
    TRICHO: draw_trichodesmium,
    SALP: draw_salp,
    KRILL: draw_krill,
}


# --------------------------------------------------------------------------
# 5. ECOSYSTEM  -  NPZ dynamics carried by individual agents
# --------------------------------------------------------------------------

class Agent:
    __slots__ = ("g", "x", "z", "ang", "spin", "mass", "age", "vigour",
                 "gravid", "flash", "vis", "doomed", "mode", "head")

    def __init__(self, g, x, z, mass, rng, vis=0.02):
        self.g = g
        self.x = x
        self.z = z
        self.ang = rng.uniform(0, 2 * math.pi)
        self.head = rng.uniform(0, 2 * math.pi)
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


R_MIN = 3.0
# Measured, not guessed. Rendering each morphology at descending radii and
# counting ink: below about 3.0 every one of them collapses into a blob --
# the radiolarian loses its spines, the centric loses its central pore, the
# tintinnid stops being a cone. At 3.0 all seven are still structured, and a
# radial form is about 7 px across. Marine snow is 1 to 2 px, so there is a
# clean threefold gap between the smallest organism and the largest speck,
# which is what keeps them separate categories rather than a continuum.


def visual_radius(a):
    """Single source of truth for on-screen size, used by both the renderer
    and the separation force so the two cannot disagree.

    The floor is applied before the fade, not after: a fully arrived cell is
    never drawn below the legibility threshold, but one that is still fading
    in still grows into place rather than popping."""
    r = a.g.size * (0.30 + 0.70 * min(1.6, a.mass) / 1.6)
    return max(R_MIN, r) * a.vis


class Ecosystem:
    def __init__(self, seed=None, start_day=0.0, track=None, ocean=None):
        self.rng = random.Random(seed)
        self.env = Environment(self.rng, track, ocean)
        self.track = track
        self.t = start_day
        r = self.rng
        # Depth-resolved nitrogen in two pools. New production (nitrate) and
        # regenerated production (ammonium) behave differently, and the
        # difference is exactly what the chemoautotrophs live on.
        self.no3 = [3.0 + N_DEEP * (i / NBINS) ** 1.4 for i in range(NBINS)]
        self.nh4 = [0.25] * NBINS
        self.nit = [0.06] * NBINS          # chemoautotroph biomass per bin
        self.pico = [0.35] * NBINS         # picoplankton, the unresolved
                                           # small-cell class. See the note.
        self.agents = []
        self.det = []
        self._graze_f = 1.0
        # per-instance so that several ecosystems with different swimming
        # speeds can be run side by side in one process, which is the only
        # way to compare them honestly -- sequentially you are comparing the
        # second one against your memory of the first
        self.swim_scale = SWIM_SCALE
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

    def _fitness(self, t):
        """Realised growth rate per drifter type in the water the ship is
        entering, as the weights for what arrives.

        This is the part that makes advection honest rather than a lookup. We
        are not saying which organisms live here; we are computing, from the
        same traits and the same equations the resident cells use, which ones
        would be growing in the water upstream -- because that water has been
        growing them. Eighteen evaluations of an expression the model already
        contains, once per step."""
        env = self.env
        surface = env.surface_light(t)
        chl = self.biomass / MAX_PHYTO
        I = self.light_at(8.0, surface, chl)
        T = env.temperature(t, 8.0)
        mld = env.mixed_layer_depth(t)
        n = self._deep_n
        fe = self._iron
        r = mld / Z_MAX
        out = {}
        for k in DRIFTER_KINDS:
            d = DERIVED[k]
            if k in DIAZOTROPHS:
                f_nut = (fe / (fe + 0.12 * d[1] * DIAZO_FE_COST)
                         if T >= DIAZO_T_MIN else 0.0)
            else:
                ks = K_S * d[1]
                f_nut = min(1.0, n / (n + ks), fe / (fe + 0.12 * d[1]))
            mu = (MU_MAX * d[0] * (I / (I + I_K)) * f_nut * temp_factor(k, T)
                  - d[7] - 0.30 * r / (0.55 + r))
            if TROPHY[k] == MIXO:
                mu = 0.62 * mu + 0.10        # mixotrophs eat as well
            out[k] = max(0.0, mu)
        return out

    def _capacity(self, t):
        """How much life this water can carry, uncapped. The compression to a
        countable number of sprites happens once, here, rather than being
        smeared across a cap and a cull.

        Nutrient supply times an iron ceiling times a light-and-temperature
        gate -- which is deliberately the same combination the satellite check
        found correlates with real chlorophyll at rho +0.68, because that
        measurement is the best evidence available for what sets standing
        stock. The first attempt used the best instantaneous growth RATE
        instead, which is a different quantity: a rate goes to zero in polar
        winter while the standing stock does not, and capacity collapsed to
        the floor over half the voyage."""
        env = self.env
        I = self.light_at(6.0, env.daily_light(t), self.biomass / MAX_PHYTO)
        T = env.temperature(t, 6.0)
        mld = env.mixed_layer_depth(t)
        # growth potential ignoring nutrients: can anything grow here at all?
        g = max(MU_MAX * DERIVED[k][0] * temp_factor(k, T) for k in PHOTO_KINDS)
        g *= I / (I + I_K)
        gate = g / (g + 0.55)
        deep = 0.35 + 0.65 / (1.0 + (mld / (2.2 * Z_MAX)) ** 2)
        return self._deep_n * self._iron * gate * deep

    def _advect(self, dt, t):
        """Replace the water as the ship moves through it.

        Departures are random: advection does not care how fit a cell is.
        Arrivals are fitness-weighted, because they come from water that has
        been growing them. And the number of them follows the capacity of the
        water ahead, compressed -- so the count tracks the ocean while each
        individual's mass, and which type actually thrives, stay in the hands
        of the local dynamics. A bloom is still something that happens."""
        if self.track is None:
            return
        rng = self.rng
        speed = self.track.speed(t)
        rate = FLUSH_PER_100KM * speed / 100.0
        cap = self._capacity(t)
        n_target = max(N_FLOOR, min(MAX_PHYTO,
                                    int(round(CAP_SCALE * cap ** CAP_EXP))))
        self._n_target = n_target

        live = [a for a in self.agents
                if a.g.kind in DRIFTER_KINDS and not a.doomed]
        n = len(live)

        if rate > 0.0:
            p = rate * dt
            for a in live:
                if rng.random() < p:
                    self._leave(a)
            n -= sum(1 for a in live if a.doomed)

        # arrivals, pulled toward the target. The rate is the flush rate plus
        # a restoring term, so the population converges even at anchor.
        want = n_target - n
        arrive = (rate * n_target + max(0.0, want) * 0.9 + IMMIGRATION) * dt
        while arrive > 0.0:
            if rng.random() < min(1.0, arrive):
                if n < MAX_PHYTO:
                    a = self._spawn_drifter(kind=self._fit_kind(t))
                    a.mass = rng.uniform(0.45, 0.95)
                    n += 1
            arrive -= 1.0
        if n > n_target + 2:
            self._enforce_cap(n_target)

    def _fit_kind(self, t):
        """Weighted by fitness, but never zero: a type that is losing here
        still arrives occasionally, because the ocean is not sterile of it and
        because a model that only imports winners cannot discover anything."""
        f = self._fitness(t)
        rng = self.rng
        w = [0.04 + f.get(k, 0.0) for k in DRIFTER_KINDS]
        pick = rng.random() * sum(w)
        for k, wt in zip(DRIFTER_KINDS, w):
            pick -= wt
            if pick <= 0.0:
                return k
        return DRIFTER_KINDS[-1]

    def _leave(self, a):
        """Carried out of frame. Not death: no detritus, no ammonium."""
        if not a.doomed:
            a.doomed = True

    def _seed_kind(self):
        """Which type arrives next.

        Weighted toward whatever is currently absent -- "everything is
        everywhere, the environment selects". Without this the model
        extinction-locks: a type that loses in one ocean is gone from the
        pool, so when the ship reaches water that would suit it there is
        nothing left to succeed. That failure would look exactly like
        competitive exclusion working correctly, which is what makes it
        dangerous.

        Weighting rather than forcing: a type that is genuinely unsuited still
        arrives and still dies, which is the point."""
        r = self.rng
        present = {}
        for a in self.agents:
            if not a.doomed:
                present[a.g.kind] = present.get(a.g.kind, 0) + 1
        w = [1.0 / (1.0 + 2.5 * present.get(k, 0)) for k in DRIFTER_KINDS]
        pick = r.random() * sum(w)
        for k, wt in zip(DRIFTER_KINDS, w):
            pick -= wt
            if pick <= 0.0:
                return k
        return DRIFTER_KINDS[-1]

    def _spawn_drifter(self, parent=None, kind=None):
        r = self.rng
        if parent is None:
            g = Genome(kind if kind is not None else self._seed_kind(), r)
            z = r.uniform(2, Z_MAX * 0.85)
            # Across the whole field, not at an edge.
            #
            # Arrivals used to appear within five pixels of x=0 or x=W, on the
            # reasoning that water flows in from one side. That was defensible
            # when immigration was one cell a day and became badly wrong when
            # advection made it twenty or thirty: cells entered at the seam,
            # and with a residual drift of 38 px/day against a residence
            # half-life of 1.3 days they were carried out again long before
            # they reached the middle. Measured at day 5, 56% of the
            # population sat in 17% of the width.
            #
            # And the edge model was wrong anyway. The panel is a vertical
            # SLICE and the ship moves through it, not along it, so new water
            # fills the whole slice rather than entering from one side.
            x = r.uniform(0, W)
            a = Agent(g, x, z, r.uniform(0.5, 0.9), r, 0.02)
        else:
            g = parent.g.child(r)
            z = max(0.5, min(Z_MAX - 0.5, parent.z + r.gauss(0, 4.0)))
            a = Agent(g, (parent.x + r.gauss(0, 5.0)) % W, z, parent.mass, r,
                      0.35)          # a daughter is already a real cell
        self.agents.append(a)
        return a

    def _seed_het(self):
        """Which grazer arrives. Same absence-weighting as the drifters: a
        krill that loses in the tropics has to still be available when the
        ship reaches the Southern Ocean eighteen months later."""
        r = self.rng
        present = {}
        for a in self.agents:
            if not a.doomed:
                present[a.g.kind] = present.get(a.g.kind, 0) + 1
        w = [1.0 / (1.0 + 2.0 * present.get(k, 0)) for k in HET_KINDS]
        pick = r.random() * sum(w)
        for k, wt in zip(HET_KINDS, w):
            pick -= wt
            if pick <= 0.0:
                return k
        return HET_KINDS[0]

    def _spawn_het(self, kind):
        r = self.rng
        a = Agent(Genome(kind, r), r.uniform(0, W), r.uniform(5, Z_MAX * 0.8),
                  r.uniform(0.8, 1.4), r, 0.02)
        self.agents.append(a)
        return a

    def _enforce_cap(self, limit=None):
        """Cull to MAX_PHYTO, weakest first. Vigour is the running integral of
        realised growth rate, so it is exactly the right measure: the cells
        that go are the ones the environment was already failing."""
        live = [a for a in self.agents
                if a.g.kind in DRIFTER_KINDS and not a.doomed]
        excess = len(live) - (MAX_PHYTO if limit is None else limit)
        if excess <= 0:
            return
        live.sort(key=lambda a: (a.vigour, a.mass))
        for a in live[:excess]:
            self._die(a)

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

    _deep_n = N_DEEP
    _iron = 1.0
    _n_target = 20
    time_compression = 1.0     # simulated seconds per real second; the
                               # preview sets it from the speed control

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
        deep = self._deep_n
        self.no3[NBINS - 1] += (deep - self.no3[NBINS - 1]) * min(1.0, 0.7 * dt)
        for i in range(NBINS):
            self.no3[i] = max(0.01, min(deep * 1.3, self.no3[i]))
            self.nh4[i] = max(0.0, min(deep * 0.6, self.nh4[i]))

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

    def _swim(self, dt):
        """Move the motile ones at their own speed, and turn them to face it.

        Ballistic below the heading decorrelation time and diffusive above it,
        which is not fussiness -- it is the only way one piece of code can be
        right at both ends of a speed control that spans six orders of
        magnitude. At real time you watch a copepod swim; at a day a second
        the same call has to become a random walk with the correct
        diffusivity, D = v^2 * tau, or the displacement per step diverges."""
        rng = self.rng
        dt_s = dt * 86400.0 / max(1.0, self.time_compression)
        zpx = (H - TOP_M - BOT_M) / Z_MAX
        for a in self.agents:
            k = a.g.kind
            bl = SWIM_BL.get(k)
            if bl is None:
                # not a swimmer: tumbling in shear, and nothing else
                a.ang += rng.gauss(0.0, 1.0) * math.sqrt(
                    min(dt_s, 4.0 * TUMBLE_S)) * (2.0 * math.pi / TUMBLE_S) * 0.35
                continue
            v = bl * 2.0 * visual_radius(a) * self.swim_scale  # px per second
            tau = TURN_TAU.get(k, 10.0)
            if dt_s < tau:
                a.head += rng.gauss(0.0, math.sqrt(dt_s / tau))
                dx = v * dt_s * math.cos(a.head)
                dz = v * dt_s * math.sin(a.head)
            else:
                step = v * math.sqrt(tau * dt_s)              # D = v^2 tau
                a.head = rng.uniform(0.0, 2.0 * math.pi)
                dx = rng.gauss(0.0, step) * 0.7071
                dz = rng.gauss(0.0, step) * 0.7071
            a.x += dx
            # vertical swimming is damped: the diel migration and the sinking
            # terms own the depth axis, and a copepod that could cross fifty
            # metres in a minute would make nonsense of both
            a.z += dz * 0.25 / zpx
            a.ang = a.head + math.pi          # the drawings face -u

    def _step_pico(self, dt, surface, chl, t):
        """Picoplankton, as a scalar field. Monod on the same nitrogen the
        agents compete for, so this is a real competitor and not a backdrop --
        in a gyre it wins that competition, draws the surface down to nothing,
        and that is precisely why the large cells cannot get started."""
        env = self.env
        for i in range(NBINS):
            z = (i + 0.5) * BIN_M
            I = self.light_at(z, surface, chl)
            n = self.nh4[i] + self.no3[i]
            x = (env.temperature(t, z) - T_OPT_PICO) / T_W_PICO
            f_t = (Q10_EPPLEY ** (T_OPT_PICO - T_REF)) * math.exp(-x * x)
            mu = (MU_PICO * (I / (I + I_K_PICO)) * (n / (n + K_PICO))
                  * f_t * min(1.0, self._iron / (self._iron + 0.04))
                  - LOSS_PICO)
            grow = self.pico[i] * mu * dt
            self.pico[i] = max(0.02, min(PICO_MAX, self.pico[i] + grow))
            if grow > 0.0:
                want = grow * 0.16
                take = min(self.nh4[i], want)
                self.nh4[i] -= take
                self.no3[i] = max(0.01, self.no3[i] - (want - take))
            else:
                self.nh4[i] += -grow * 0.5      # lysis returns ammonium

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

    def _ingest(self, a, dt):
        """Heterotrophy, by size rather than by species.

        Was a small_only boolean, which is a rule about who eats whom written
        by hand. This is a log-normal preference kernel centred on a
        predator:prey length ratio of ten -- so a copepod at 1500 um takes
        150 um prey and a tintinnid at 60 um takes 6 um prey, and neither of
        them was told anything about the other. Add a new organism to the
        roster and its position in the food web is already decided by how big
        it is."""
        rng = self.rng
        got = 0.0
        reach = 30.0 if a.g.kind == COPEPOD else 18.0
        zreach = reach * 0.30
        for dd in self.det:
            if abs(dd.z - a.z) < zreach and abs(dd.x - a.x) < reach:
                if rng.random() < 1.2 * dt:
                    take = min(dd.mass, 0.45)
                    dd.mass -= take
                    got += take * 0.55
                    break
        # the unresolved small-cell class. A copepod is far too big to filter
        # picoplankton directly; everything smaller lives on it, and in a gyre
        # it is the only food there is.
        if a.g.kind != COPEPOD:
            i = self._bin(a.z)
            take = min(self.pico[i] - 0.02,
                       PICO_GRAZE * self.pico[i] * dt)
            if take > 0.0:
                self.pico[i] -= take
                got += take * 0.85
        rate = (2.0 if a.g.kind == COPEPOD else 0.85) * self._graze_f
        for p in self.agents:
            if p is a or p.doomed or p.g.kind not in DRIFTER_KINDS:
                continue
            if abs(p.z - a.z) < zreach and abs(p.x - a.x) < reach:
                if rng.random() < rate * graze_pref(a.g.kind, p.g.kind) * dt:
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
        self._deep_n = env.deep_nitrate(t)
        self._iron = env.iron(t)
        mld = env.mixed_layer_depth(t)
        mixing = env.mixing(t)
        chl = self.biomass / MAX_PHYTO
        daylight = min(1.0, surface / 0.20)

        self._mix_nitrogen(dt, mld, mixing)
        self._step_pico(dt, surface, chl, t)
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
        # Holling type III grazing. Without this the model has no prey refuge
        # at all: encounter rate falls only as fast as the prey thin out, so
        # a grazer population built up during a bloom will follow the prey
        # all the way to literally zero -- which it did, on day 120, off the
        # Rio de la Plata, with nutrients abundant and light plentiful. A
        # sigmoid response is what real grazers show and what NPZ models have
        # used since Fasham: below about ten prey the grazers effectively
        # stop finding them, and the population always keeps a seed.
        nd = len(drifters)
        self._graze_f = (nd * nd) / (nd * nd + K_PREY * K_PREY)
        hets = [a for a in self.agents
                if a.g.kind in HET_KINDS and not a.doomed]
        n_drift = len(drifters)
        born = []

        # ---- swimming ------------------------------------------------------
        self._swim(dt)

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
            d = DERIVED[a.g.kind]
            ks = K_S * d[1]          # a big cell needs more, per the allometry
            f_nh4 = nh4 / (nh4 + ks)
            f_no3 = (no3 / (no3 + ks)) * math.exp(-PSI * nh4)
            # Liebig: whichever of nitrogen and iron is scarcer sets the
            # ceiling. In an HNLC region nitrogen is abundant and this term is
            # entirely iron, which is the whole point of carrying the field.
            # Iron half-saturation scales with size the same way nitrogen does
            # (Sunda & Huntsman 1997), so a big cell is iron-limited first.
            f_fe = self._iron / (self._iron + 0.12 * d[1])
            if a.g.kind in DIAZOTROPHS:
                # fixes its own nitrogen, so the N terms simply do not apply.
                # What binds instead is iron, at twenty-five times the demand,
                # and a hard temperature floor.
                T = env.temperature(t, a.z)
                f_fe = self._iron / (self._iron + 0.12 * d[1] * DIAZO_FE_COST)
                f_nut = f_fe if T >= DIAZO_T_MIN else 0.0
            else:
                f_nut = min(1.0, f_nh4 + f_no3, f_fe)
            f_temp = temp_factor(a.g.kind, env.temperature(t, a.z))
            # a.g.jitter is the lognormal spread on growth rate. It is not
            # cosmetic: it is what lets a subset of individuals land on an
            # unusually favourable combination and found a bloom, which is how
            # real diversity within a type actually behaves.
            mu_max = MU_MAX * d[0] * a.g.jitter

            ingested = 0.0
            if a.mode == MIXO:
                ingested = self._ingest(a, dt)
                r = mld / Z_MAX
                mu = (0.62 * mu_max * f_light * f_nut * f_temp
                      - d[7] - 0.11 * r / (0.55 + r))
            else:
                # Sverdrup: a cell mixed below the critical depth spends most
                # of its time in the dark, so deep mixing is a loss term. It
                # SATURATES, though -- once the column is fully mixed, mixing
                # it harder changes nothing, and the linear form here was still
                # climbing at 1.3x and taking 0.44/day out of a cell whose
                # maximum growth was 1.0. That is what emptied the Southern
                # Ocean, in water the satellite says is among the richest on
                # the track.
                r = mld / Z_MAX
                mu = (mu_max * f_light * f_nut * f_temp
                      - d[7] - 0.30 * r / (0.55 + r))

            grow = a.mass * mu * dt
            a.mass = min(2.45, a.mass + grow + ingested * 0.6)
            a.vigour = max(0.0, min(1.0, a.vigour + (mu * 2.2 - 0.10) * dt))

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
                # Sinking is allometric and buoyancy is per-type. A starving
                # cell sinks faster, which is real -- nutrient-stressed diatoms
                # go from under 1 m/day to over 10 -- and it is also what
                # exports a dead bloom out of the lit layer.
                a.z += (0.4 + 3.6 * (1.0 - a.vigour)) * d[2] * dt

            if a.mass > 1.9 and n_drift + len(born) < MAX_PHYTO:
                a.mass *= 0.5
                a.age = 0.0
                a.flash = 1.0
                born.append(a)
            if a.z > Z_MAX or a.mass < 0.16 or a.age > 55:
                self._die(a)

        # ---- heterotrophs -------------------------------------------------
        for a in hets:
            k = a.g.kind
            if k in MIGRATORS:
                # diel vertical migration, with individual variation so they
                # do not sweep up and down as one rigid block. Copepods and
                # krill both do it; ciliates and salps do not.
                target = 7.0 + 14.0 * a.g.curl + 34.0 * daylight
                a.z += (target - a.z) * min(1.0, 2.2 * dt)
            else:
                target = 9.0 + 24.0 * (0.5 + 0.5 * a.g.curl)
                a.z += (target - a.z) * min(1.0, 0.5 * dt)
            # Grazers get the thermal niche the drifters have always had.
            # Without it a krill with a 4 C optimum fed happily in 28 C water
            # and the tropical gyres filled with Euphausia, which is a
            # Southern Ocean animal. The niche was in the trait table the
            # whole time; only the phototrophs were reading it.
            tf = temp_factor(k, env.temperature(t, a.z))
            a.mass += self._ingest(a, dt) * HET_ASSIM[k] * min(1.6, tf)
            # maintenance is allometric here too: a salp costs little to run
            a.mass -= DERIVED[k][7] * 3.2 * dt
            # A grazer that cannot divide because its class is full used to
            # keep eating and keep growing, with nothing bounding it -- the
            # drifters had min(2.45, ...) and the heterotrophs had nothing.
            # Krill reached a mass of 59 and the grazers ended up outweighing
            # everything they were eating, which is not a food chain, it is a
            # pyramid standing on its point.
            a.mass = min(2.6, a.mass)
            nk = sum(1 for h in hets if h.g.kind == k and not h.doomed)
            n_all = sum(1 for h in hets if not h.doomed) + len(born)
            cap_ok = (nk + sum(1 for b in born if b.g.kind == k)
                      < HET_CAP.get(k, 2)) and n_all < MAX_ZOO

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

        # ---- immigration, and a cap held by fitness rather than by arrival --
        #
        # The reseed used to fire only when the population was below twelve,
        # which meant that once the panel was full nothing new could ever
        # arrive. Whoever filled the cap first held it until conditions
        # crashed them -- so the community was decided by founder effect, and
        # a type that would have won on the traits simply never got in. The
        # composition log showed Chaetoceros holding the tropics at 100% for
        # two hundred days on water that Navicula should have taken.
        #
        # So: arrivals are continuous and independent of how full it is, and
        # the cap is paid for afterwards by whichever individuals are doing
        # worst. A hard cap is a rendering constraint; making it a rendering
        # constraint that culls the least fit is the only way to stop it
        # behaving like an ecological one.
        self._advect(dt, t)
        self._enforce_cap()
        if sum(1 for a in self.agents if a.g.kind in HET_KINDS) < MAX_ZOO:
            if rng.random() < 1.2 * dt:
                self._spawn_het(self._seed_het())

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

    def composition(self):
        """Biomass by type. The only diagnostic that can tell whether the
        trait model works, because total biomass looks identical whether one
        type wins everywhere or five take turns."""
        out = {}
        for a in self.agents:
            if a.doomed or a.vis <= 0.03:
                continue
            out[a.g.kind] = out.get(a.g.kind, 0.0) + a.mass
        return out

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
            if rank < eco.nit[i] * 0.30 + eco.pico[i] * 0.28:
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
    text(c, 8, y, track.voyage.title if track is not None else "DRIFT")

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
    speed = PRESETS[1]          # 1 min per second: a voyage day every 24 real
    paused = False              # minutes, the whole circumnavigation in 17 days
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
                elif e.key == pygame.K_h:
                    view.hud = not view.hud
                elif e.key == pygame.K_p:
                    view.plate = not view.plate
                elif e.key == pygame.K_n:
                    view.chemo = not view.chemo
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
            dt = real_dt * speed
            # sub-step so fast-forward stays numerically sane
            steps = max(1, min(64, int(dt / 0.015) + 1))
            for _ in range(steps):
                eco.step(dt / steps)
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
    view = View(hud=False)
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
        f.write("day,lat,lon,sst,mld,deepN,iron,biomass,agents,zoo,"
                + ",".join(KIND_NAME[k] for k in DRIFTER_KINDS) + ",status\n")
        for r in log:
            f.write("%d,%.2f,%.2f,%.1f,%.0f,%.1f,%.2f,%.1f,%d,%d,"
                    % r[:10]
                    + ",".join("%.1f" % v for v in r[10:-1])
                    + ",%s\n" % r[-1])

    bio = [r[7] for r in log]
    n = [r[8] for r in log]
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
        voyage_sweep(sys.argv[2],
                     voyage=sys.argv[3] if len(sys.argv) > 3 else "drake")
    else:
        preview()
