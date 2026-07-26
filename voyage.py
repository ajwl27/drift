#!/usr/bin/env python3
"""
VOYAGE  -  where the boat is, and how to draw the world from there.

Two things live here, and nothing else:

    Track       Drake's circumnavigation as a dated waypoint list, with
                great-circle interpolation between waypoints and genuine
                stationary periods at the anchorages.  Ports as-is.
    project()   Course-up orthographic.  Ports as-is.

Both are pure functions of a day number.  No state, no allocation in the
hot path, no float64 anywhere it matters.

Dates are Julian (Old Style), which is what every account of the voyage
uses, and what makes 13 Dec 1577 -> 26 Sep 1580 come to 1018 days.  Since
1580 is a leap year in both calendars, ordinary date arithmetic is correct
across the whole span.

Confidence tags on each waypoint:
    2  date and place both well attested
    1  place attested, date approximate
    0  reconstructed to fill a gap -- notably the entire Pacific crossing,
       for which no intermediate position was ever recorded
"""

import math

# --------------------------------------------------------------------------
# 1. THE TRACK
# --------------------------------------------------------------------------

DEPARTURE = "13 DEC 1577"
VOYAGE_DAYS = 1018

# (day, lat, lon, confidence, label)
# Day 0 is the departure from Plymouth, 13 December 1577 (Old Style).
# Repeated positions on different days are deliberate: they are the
# careening stops and the winter at Port St Julian, and they are why the
# piece sits in one water mass for weeks at a time.
WAYPOINTS = (
    (   0,  50.37,   -4.14, 2, "PLYMOUTH"),
    (  12,  31.51,   -9.77, 2, "MOGADOR"),
    (  34,  20.77,  -17.03, 2, "CAPE BLANCO"),
    (  46,  15.13,  -23.16, 2, "MAIO"),
    (  49,  14.93,  -23.51, 2, "SANTIAGO"),
    (  77,  -3.85,  -32.42, 1, "FERNANDO DE NORONHA"),
    (  87, -12.97,  -38.50, 2, "BAHIA"),
    ( 122, -35.00,  -56.20, 2, "RIO DE LA PLATA"),
    ( 146, -35.00,  -56.20, 2, "RIO DE LA PLATA"),
    ( 150, -47.75,  -65.90, 1, "PUERTO DESEADO"),
    ( 155, -48.00,  -66.00, 1, "SEAL BAY"),
    ( 188, -49.31,  -67.72, 2, "PORT ST JULIAN"),
    ( 247, -49.31,  -67.72, 2, "PORT ST JULIAN"),      # 59 days at anchor
    ( 250, -52.33,  -68.35, 2, "CAPE VIRGENES"),
    ( 254, -52.80,  -70.40, 2, "ELIZABETH ISLAND"),
    ( 267, -52.72,  -74.71, 2, "CAPE PILAR"),
    ( 298, -51.50,  -75.15, 1, "DIEGO DE ALMAGRO"),
    ( 315, -55.85,  -67.35, 0, "SOUTHERNMOST"),        # see NOTES
    ( 322, -55.77,  -69.44, 2, "ILDEFONSO"),
    ( 346, -39.85,  -73.40, 1, "VALDIVIA"),
    ( 348, -38.37,  -73.90, 2, "ISLA MOCHA"),
    ( 352, -32.78,  -71.53, 2, "QUINTERO"),
    ( 357, -33.05,  -71.62, 2, "VALPARAISO"),
    ( 364, -30.25,  -71.63, 1, "TONGOY"),
    ( 373, -27.30,  -70.93, 1, "SALADA BAY"),
    ( 402, -27.30,  -70.93, 1, "SALADA BAY"),          # 29 days careening
    ( 406, -26.15,  -70.65, 1, "PAN DE AZUCAR"),
    ( 418, -19.60,  -70.22, 2, "PISAGUA"),
    ( 420, -18.48,  -70.32, 2, "ARICA"),
    ( 422, -17.00,  -71.98, 1, "CHULE"),
    ( 429, -12.05,  -77.15, 2, "CALLAO"),
    ( 434,  -5.08,  -81.11, 2, "PAITA"),
    ( 443,   0.60,  -80.13, 2, "CACAFUEGO"),
    ( 455,   8.70,  -83.65, 1, "CANO ISLAND"),
    ( 466,   8.70,  -83.65, 1, "CANO ISLAND"),
    ( 486,  15.75,  -96.12, 2, "GUATULCO"),
    ( 539,  43.31, -124.41, 0, "CAPE ARAGO"),          # see NOTES
    ( 551,  38.03, -122.94, 1, "NOVA ALBION"),
    ( 587,  38.03, -122.94, 1, "NOVA ALBION"),         # 36 days careening
    ( 588,  37.70, -123.00, 1, "FARALLONES"),
    ( 610,  28.00, -155.00, 0, "PACIFIC"),             # pure interpolation
    ( 633,  16.00,  178.00, 0, "PACIFIC"),             # -- see NOTES
    ( 656,   7.50,  134.50, 1, "PALAU"),
    ( 672,   5.90,  125.20, 1, "MINDANAO"),
    ( 679,   5.40,  125.40, 1, "SARANGANI"),
    ( 681,   2.70,  125.40, 1, "SANGIHE"),
    ( 690,   0.80,  127.33, 2, "TERNATE"),
    ( 696,   0.80,  127.33, 2, "TERNATE"),
    ( 701,  -1.62,  123.57, 1, "BANGGAI"),
    ( 729,  -1.62,  123.57, 1, "BANGGAI"),             # 28 days recovering
    ( 757,  -2.00,  123.30, 0, "THE REEF"),
    ( 762,  -4.10,  123.10, 1, "WOWONI"),
    ( 785,  -7.15,  128.40, 1, "DAMAR"),
    ( 817,  -7.73,  109.00, 2, "JAVA"),
    ( 834,  -7.73,  109.00, 2, "JAVA"),
    ( 864, -20.00,   70.00, 0, "INDIAN OCEAN"),        # pure interpolation
    ( 890, -31.50,   29.50, 1, "AFRICAN COAST"),
    ( 915, -34.36,   18.47, 2, "CAPE OF GOOD HOPE"),
    ( 945,   5.45,   -9.57, 2, "CESTOS RIVER"),
    ( 952,   8.48,  -13.23, 2, "SIERRA LEONE"),
    ( 992,  38.00,  -25.00, 0, "AZORES"),              # pure interpolation
    (1018,  50.37,   -4.14, 2, "PLYMOUTH"),
)

NOTES = """
Where the record is thin, and what this piece does about it.

SOUTHERNMOST (day 315).  Blown south after clearing the Strait, Drake
reached an island he named Elizabeth -- not the Elizabeth Island inside the
Strait, a different one, and one nobody has seen since.  Nuno da Silva's log
says 57 degrees S, at which latitude there is no land.  Modern scholarship
treats it as a phantom.  This track uses 55.85 S in the Hermite group, which
is conservative; whether Drake actually saw open water south of the
continent, and so discovered the passage that carries his name, is still
argued.  Turner says yes.  Kelsey says no.

CAPE ARAGO (day 539).  The furthest north Drake reached on the American
coast is disputed across four degrees of latitude.

NOVA ALBION (day 551).  Drakes Bay at Point Reyes is the designated
landmark and the mainstream reading.  It is not settled: the two surviving
manuscript accounts give 44 N against the printed 38 N, and there are twenty
or more candidate sites in the literature, from Baja to Alaska.

THE PACIFIC CROSSING (days 588-656).  Sixty-eight days out of sight of land
and not one intermediate position recorded anywhere.  The two waypoints in
the middle of it are a great-circle construction, nothing more.  They exist
so that the boat crosses the date line at a plausible latitude, and they are
tagged 0 accordingly.  The piece will spend nine weeks in the North Pacific
gyre on the strength of them, which is exactly the stretch where it will
look emptiest -- and correctly so.
"""


def _norm_lon(d):
    return (d + 180.0) % 360.0 - 180.0


def _to_vec(lat, lon):
    la = math.radians(lat)
    lo = math.radians(lon)
    cl = math.cos(la)
    return (cl * math.cos(lo), cl * math.sin(lo), math.sin(la))


def _to_ll(v):
    x, y, z = v
    return (math.degrees(math.asin(max(-1.0, min(1.0, z)))),
            math.degrees(math.atan2(y, x)))


def slerp(a, b, f):
    """Great-circle interpolation between two unit vectors. Constant speed
    along the arc, which is what a ship actually does, and what a linear
    interpolation of latitude and longitude conspicuously does not -- that
    would drift off the great circle and, worse, take the wrong way round
    the world across the date line."""
    d = a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
    d = max(-1.0, min(1.0, d))
    if d > 0.999999:
        return b if f > 0.5 else a
    o = math.acos(d)
    so = math.sin(o)
    ka = math.sin((1.0 - f) * o) / so
    kb = math.sin(f * o) / so
    return (ka * a[0] + kb * b[0], ka * a[1] + kb * b[1], ka * a[2] + kb * b[2])


class Track:
    """The voyage as a continuous function of time.

    Cost per query is a binary search over 62 waypoints and one slerp. On the
    MCU this runs once a frame and disappears into the noise."""

    def __init__(self, waypoints=WAYPOINTS):
        self.wp = waypoints
        self.vec = [_to_vec(w[1], w[2]) for w in waypoints]
        self.days = [w[0] for w in waypoints]

    def _seg(self, day):
        lo, hi = 0, len(self.days) - 1
        if day <= self.days[0]:
            return 0, 0.0
        if day >= self.days[-1]:
            return hi - 1, 1.0
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if self.days[mid] <= day:
                lo = mid
            else:
                hi = mid
        d0, d1 = self.days[lo], self.days[lo + 1]
        span = d1 - d0
        return lo, 0.0 if span <= 0 else (day - d0) / span

    def position(self, day):
        i, f = self._seg(day)
        if f <= 0.0:
            return _to_ll(self.vec[i])
        return _to_ll(slerp(self.vec[i], self.vec[i + 1], f))

    def bearing(self, day, look=2.0):
        """Course made good, degrees clockwise from north. Measured against a
        point a couple of days ahead rather than differentiated, because the
        derivative is undefined the moment the ship is at anchor -- and it is
        at anchor for a sixth of the voyage."""
        la0, lo0 = self.position(day)
        la1, lo1 = self.position(min(day + look, self.days[-1]))
        if abs(la1 - la0) < 1e-7 and abs(_norm_lon(lo1 - lo0)) < 1e-7:
            # stationary: keep looking further ahead until the ship moves
            for extra in (8.0, 30.0, 90.0):
                la1, lo1 = self.position(min(day + extra, self.days[-1]))
                if abs(la1 - la0) > 1e-7 or abs(_norm_lon(lo1 - lo0)) > 1e-7:
                    break
            else:
                return 0.0
        p0 = math.radians(la0)
        p1 = math.radians(la1)
        dl = math.radians(_norm_lon(lo1 - lo0))
        y = math.sin(dl) * math.cos(p1)
        x = math.cos(p0) * math.sin(p1) - math.sin(p0) * math.cos(p1) * math.cos(dl)
        return math.degrees(math.atan2(y, x)) % 360.0

    def speed(self, day, h=0.5):
        """Km per day. Zero at anchor, which the ecosystem uses to decide
        whether the water is being replaced or merely sat in."""
        la0, lo0 = self.position(max(0.0, day - h))
        la1, lo1 = self.position(min(day + h, self.days[-1]))
        return haversine(la0, lo0, la1, lo1) / (2.0 * h)

    def leg(self, day):
        """The waypoint being sailed from, for the caption."""
        i, _ = self._seg(day)
        return self.wp[i][4], self.wp[min(i + 1, len(self.wp) - 1)][4]

    def anchored(self, day):
        """Name of the anchorage if the ship is not making way, else None.

        Exact rather than inferred from speed: a dwell is encoded as the same
        position on two different days, so this is a comparison, not a
        threshold. Which matters, because the ship also crawls at a tenth of a
        knot down the Patagonian coast and that is emphatically not anchored."""
        i, _ = self._seg(day)
        w0 = self.wp[i]
        w1 = self.wp[min(i + 1, len(self.wp) - 1)]
        if (w0[1], w0[2]) == (w1[1], w1[2]) and w1[0] > w0[0]:
            return w0[4]
        return None

    def status(self, day):
        """One line for the footer."""
        at = self.anchored(day)
        return ("ANCHORED  " + at) if at else "AT SEA"

    def next_port(self, day):
        """(name, days away) for the next waypoint the ship is not already
        sitting at. Skips the duplicate entries that encode a dwell, so at
        Port St Julian on day 200 this says CAPE VIRGENES in 50 days rather
        than PORT ST JULIAN in 47."""
        i, _ = self._seg(day)
        here = (self.wp[i][1], self.wp[i][2])
        for j in range(i + 1, len(self.wp)):
            w = self.wp[j]
            if (w[1], w[2]) != here:
                return w[4], w[0] - day
        return self.wp[-1][4], self.wp[-1][0] - day

    def confidence(self, day):
        """Lowest confidence of the two waypoints bracketing this moment.
        The plate says so when it is guessing."""
        i, _ = self._seg(day)
        return min(self.wp[i][3], self.wp[min(i + 1, len(self.wp) - 1)][3])


def haversine(la0, lo0, la1, lo1, R=6371.0):
    p0 = math.radians(la0)
    p1 = math.radians(la1)
    dp = p1 - p0
    dl = math.radians(_norm_lon(lo1 - lo0))
    a = (math.sin(dp / 2) ** 2
         + math.cos(p0) * math.cos(p1) * math.sin(dl / 2) ** 2)
    return 2 * R * math.asin(min(1.0, math.sqrt(a)))


# --------------------------------------------------------------------------
# 2. COURSE-UP ORTHOGRAPHIC
# --------------------------------------------------------------------------
#
# The panel is 240 x 400.  A globe drawn to fit the width leaves a third of
# the frame empty; drawn to fill the height it overflows the width.  Neither
# is what we want.
#
# The move is to stop thinking of it as a map of the world and start
# thinking of it as a view of the world from where the ship is.  Centre the
# projection on the ship, rotate the whole thing so the course points up the
# long axis of the panel, and choose the radius.  Now the tall frame is
# working for us: it shows more of where you are going and where you have
# been than of the empty water either side, which is the correct emphasis
# for a voyage, and it is also how every strip chart from Ogilby onwards has
# been laid out.
#
# One number, R (globe radius in pixels), controls everything:
#
#   R = 118    the whole visible hemisphere fits inside the 240 width, limb
#              and all.  Reads unmistakably as a globe.  Context.
#   R = 233    the limb exactly clears the corners of a 240x400 frame, so
#              there is no white space at all and no visible edge.  This is
#              the smallest R that fills the panel.
#   R = 1400   about 900 km across the frame.  Coastal detail.
#
# and the piece simply moves R between them.

class Camera:
    __slots__ = ("lat", "lon", "R", "ca", "sa", "clat", "slat", "sb", "cb")

    def __init__(self, lat, lon, bearing, R):
        self.lat = lat
        self.lon = lon
        self.R = R
        la = math.radians(lat)
        self.slat = math.sin(la)
        self.clat = math.cos(la)
        b = math.radians(bearing)
        self.sb = math.sin(b)
        self.cb = math.cos(b)

    def project(self, lat, lon, w, h):
        """Returns (x, y, visible). Screen coordinates, origin top-left.

        Twelve multiplies and two trig calls per point. At 9000 coastline
        points that is too much to do every frame on the MCU -- the map is
        rendered once when the interlude begins and held, which is exactly
        what a reflective panel wants anyway."""
        la = math.radians(lat)
        dl = math.radians(lon - self.lon)
        cla = math.cos(la)
        sla = math.sin(la)
        cdl = math.cos(dl)
        cosc = self.slat * sla + self.clat * cla * cdl
        if cosc < 0.0:
            return 0.0, 0.0, False          # on the far side of the world
        x = self.R * cla * math.sin(dl)
        y = self.R * (self.clat * sla - self.slat * cla * cdl)
        # rotate so the course points up the panel
        xr = x * self.cb - y * self.sb
        yr = x * self.sb + y * self.cb
        return w * 0.5 + xr, h * 0.5 - yr, True

    def limb_visible(self, w, h):
        """True if the edge of the world falls inside the frame, i.e. if we
        are zoomed out far enough for this to read as a globe."""
        return self.R < math.hypot(w * 0.5, h * 0.5)


def fill_radius(w, h):
    """The smallest radius at which the globe covers the whole frame."""
    return math.hypot(w * 0.5, h * 0.5)


def span_km(R, px, Rearth=6371.0):
    """How much ocean a given number of pixels covers at the centre of the
    frame, where the orthographic scale is undistorted."""
    return Rearth * math.asin(min(1.0, px / R))
