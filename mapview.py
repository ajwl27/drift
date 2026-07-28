#!/usr/bin/env python3
"""
MAPVIEW  -  drawing the world from the boat, on a 240x400 1-bit panel.

Calls Canvas primitives only, so it ports to the MCU with the rest of the
renderer. The coastline is walked straight out of the packed binary produced
by tools/make_coast.py; on the MCU that array lives in flash and is read in
place, so this whole module needs no heap.
"""

import math
import struct

from drift import (Canvas, W, H, text, text_width, text_height, fit_scale,
                   label, trim, wrap, T_BIG, T_MED)
from voyage import Camera, Track, fill_radius, span_km
import places


# --------------------------------------------------------------------------
# coastline, walked in place
# --------------------------------------------------------------------------

CHUNK = 24            # coastline points per cullable piece


class Coast:
    """9084 points at 0.2 degree tolerance, 38 kB. Kept as one bytes object
    and indexed, never unpacked into Python tuples -- which is both faster
    here and an honest model of what the C version does with a const array
    in flash.

    CULLED BY BOUNDING CAP, which is the only reason the continuous zoom is
    affordable.

    The map used to be a still: rendered once when the interlude began and
    held, which is what a reflective panel wants and which made nine thousand
    projections a frame a non-problem because there was one frame. It is not
    a still any more -- it opens on the globe and travels in to the chart and
    back out -- so the coastline is now redrawn twenty times a second, and
    projecting the whole world to discover that Kamchatka is off the bottom
    of a chart of Peru is nine thousand transcendental functions spent on
    nothing. Measured at 16 ms a frame, against 2 ms for the water.

    So the line data is cut into chunks of two dozen points, and each chunk
    carries the smallest spherical cap that contains it: a unit vector and an
    angular radius, twenty bytes. A chunk is drawn only if its cap can reach
    the frame, which is one dot product and one comparison. At chart scale
    that rejects nineteen chunks in twenty before a single point is touched,
    and on the globe it still rejects the entire far hemisphere.

    Chunks overlap by one point so the joins do not open up.

    The projection is inlined below rather than calling Camera.project. Nine
    thousand bound-method calls is not a rounding error at this scale, and
    the arithmetic is four lines."""

    __slots__ = ("b", "n", "chunks")

    def __init__(self, path):
        with open(path, "rb") as f:
            self.b = f.read()
        self.n = struct.unpack_from("<H", self.b, 0)[0]
        self.chunks = []
        o = 2
        for _ in range(self.n):
            m = struct.unpack_from("<H", self.b, o)[0]
            base = o + 2
            o += 2 + 4 * m
            k = 0
            while k < m - 1:
                j = min(k + CHUNK, m)
                self.chunks.append(self._cap(base + 4 * k, j - k))
                k = j - 1              # overlap by one, so the joins hold
        self.chunks = tuple(self.chunks)

    def _cap(self, base, m):
        """(base, m, cx, cy, cz, cos_rad, sin_rad) for one chunk.

        The cap centre is the normalised mean of the points' unit vectors and
        the radius is the furthest of them from it. Not the minimal enclosing
        cap -- that is a nicer problem than this deserves -- but within a few
        percent of it for a two-dozen-point piece of coastline, and it only
        ever has to be conservative."""
        pts = struct.unpack_from("<%dh" % (2 * m), self.b, base)
        sx = sy = sz = 0.0
        vs = []
        for k in range(m):
            lo = math.radians(pts[2 * k] * 0.01)
            la = math.radians(pts[2 * k + 1] * 0.01)
            cla = math.cos(la)
            v = (cla * math.cos(lo), cla * math.sin(lo), math.sin(la))
            vs.append(v)
            sx += v[0]; sy += v[1]; sz += v[2]
        n = math.sqrt(sx * sx + sy * sy + sz * sz) or 1.0
        cx, cy, cz = sx / n, sy / n, sz / n
        worst = 1.0
        for (x, y, z) in vs:
            d = cx * x + cy * y + cz * z
            if d < worst:
                worst = d
        rad = math.acos(max(-1.0, min(1.0, worst)))
        return (base, m, cx, cy, cz, math.cos(rad), math.sin(rad))

    def draw(self, c, cam, w=W, h=H):
        b = self.b
        unpack = struct.unpack_from
        line = c.line
        R = cam.R
        slat = cam.slat; clat = cam.clat
        cb = cam.cb; sb = cam.sb
        lon0 = cam.lon
        hw = w * 0.5; hh = h * 0.5
        cos_ = math.cos; sin_ = math.sin; rad_ = math.radians

        # how far off the camera axis anything can be and still land inside
        # the frame: R*sin(c) <= half-diagonal
        f = math.hypot(hw, hh) / R
        cmax = math.pi * 0.5 if f >= 1.0 else math.asin(f)
        ccm = cos_(cmax); scm = sin_(cmax)
        # camera centre as a unit vector, in the same frame as the caps
        la0 = rad_(cam.lat); lo0 = rad_(lon0)
        ex = clat * cos_(lo0); ey = clat * sin_(lo0); ez = slat

        segs = 0
        for (base, m, cx, cy, cz, crad, srad) in self.chunks:
            # cos(cmax + rad); if the chunk's nearest point is further off
            # axis than that, none of it can be in frame
            thr = ccm * crad - scm * srad
            if (cx * ex + cy * ey + cz * ez) < thr:
                continue
            pts = unpack("<%dh" % (2 * m), b, base)
            px = py = 0.0
            ipx = ipy = -9999
            pv = False
            for k in range(m):
                la = rad_(pts[2 * k + 1] * 0.01)
                dl = rad_(pts[2 * k] * 0.01 - lon0)
                cla = cos_(la)
                sla = sin_(la)
                cdl = cos_(dl)
                if slat * sla + clat * cla * cdl < 0.0:
                    pv = False
                    continue
                x = R * cla * sin_(dl)
                y = R * (clat * sla - slat * cla * cdl)
                x, y = hw + x * cb - y * sb, hh - (x * sb + y * cb)
                ix = int(x); iy = int(y)
                if pv:
                    # SEGMENTS THAT LAND ON THE PIXEL THEY START FROM ARE
                    # NOT DRAWN, and the anchor does not move, so the next
                    # one is measured from here and the line stays connected.
                    #
                    # The coastline is generalised to 0.2 degrees, which at
                    # globe scale is half a pixel: two thirds of the nine
                    # thousand segments were a call into the line routine to
                    # set a pixel that was already set.
                    #
                    # Measured against drawing every segment, over eighteen
                    # views spanning the voyage: 581 pixels differ out of
                    # 68,000 drawn, 1.7% at globe scale and nothing at all at
                    # chart scale. Those are places where the coast bends
                    # inside a single pixel and the chord across the bend
                    # rounds the other way.
                    #
                    # The first version of this test allowed a whole pixel of
                    # drift instead, on the reasoning that a sub-pixel error
                    # cannot matter. It cost a FIFTH of the ink on the globe:
                    # every island small enough to fit inside the tolerance
                    # stopped being drawn at all. Bounded error is not the
                    # same as no error when the thing being drawn is smaller
                    # than the bound -- so the test is on the pixel the point
                    # lands in, not on the distance to it.
                    if ix == ipx and iy == ipy:
                        continue
                    if not ((x < 0 and px < 0) or (x >= w and px >= w)
                            or (y < 0 and py < 0) or (y >= h and py >= h)):
                        line(px, py, x, y)
                        segs += 1
                px, py, pv = x, y, True
                ipx, ipy = ix, iy
        return segs


# --------------------------------------------------------------------------
# the view
# --------------------------------------------------------------------------

def draw_limb(c, cam, w=W, h=H):
    """The edge of the world. Only drawn when it is actually in frame, which
    is the whole point of the zoom: at chart scale there is no edge, and
    pretending otherwise would be a lie about what you are looking at."""
    if cam.limb_visible(w, h):
        c.circle(w * 0.5, h * 0.5, cam.R)


def _dotted(c, pts, every=4):
    """1 bit has no grey, so the only way to make a line recede is to break
    it. Everything subordinate on this map is dotted; only the coastline and
    the track behind the ship are solid. That is the whole tonal hierarchy,
    and it has to carry the drawing."""
    n = 0
    for i in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]
        d = int(max(abs(x1 - x0), abs(y1 - y0)))
        for k in range(d + 1):
            if n % every == 0:
                t = k / d if d else 0.0
                c.px(int(x0 + (x1 - x0) * t), int(y0 + (y1 - y0) * t))
            n += 1


def draw_graticule(c, cam, w=W, h=H, step=30):
    """Meridians and parallels, dotted and sparse.

    Two rules learned the hard way. Thirty degrees, not fifteen: at fifteen
    the grid out-inks the coastline and the map stops being a map. And stop
    the meridians at 70 degrees rather than running them to the pole, or
    they converge into a starburst that reads as damage."""
    for lat in range(-60, 61, step):
        run = []
        for lon in range(-180, 181, 4):
            x, y, vis = cam.project(lat, lon, w, h)
            if vis:
                run.append((x, y))
            else:
                if len(run) > 1:
                    _dotted(c, run)
                run = []
        if len(run) > 1:
            _dotted(c, run)
    for lon in range(-180, 180, step):
        run = []
        for lat in range(-70, 71, 4):
            x, y, vis = cam.project(lat, lon, w, h)
            if vis:
                run.append((x, y))
            else:
                if len(run) > 1:
                    _dotted(c, run)
                run = []
        if len(run) > 1:
            _dotted(c, run)


def draw_track(c, track, cam, day, w=W, h=H, ahead=True, tick=30.0):
    """Where the boat has been is the only solid line on the map besides the
    coast, so it always reads. Where it is going is dotted at a wider pitch.

    Every thirtieth day gets a short cross-tick, the way a log line is
    marked. That does two things: it turns an anonymous curve into a record
    of elapsed time, and it makes the anchorages legible without a single
    word of annotation -- at Port St Julian the ship sits still for
    fifty-nine days, so two ticks land on top of each other and the track
    grows a knot."""
    seg = []
    d = 0.0
    while d <= day:
        la, lo = track.position(d)
        x, y, vis = cam.project(la, lo, w, h)
        if vis:
            seg.append((x, y, d))
        else:
            _flush_track(c, seg, tick)
            seg = []
        d += 2.0
    _flush_track(c, seg, tick)

    if ahead:
        run = []
        d = day
        while d <= track.days[-1]:
            la, lo = track.position(d)
            x, y, vis = cam.project(la, lo, w, h)
            if vis:
                run.append((x, y))
            else:
                if len(run) > 1:
                    _dotted(c, run, every=6)
                run = []
            d += 4.0
        if len(run) > 1:
            _dotted(c, run, every=6)


def _flush_track(c, seg, tick):
    if len(seg) < 2:
        return
    for i in range(len(seg) - 1):
        c.line(seg[i][0], seg[i][1], seg[i + 1][0], seg[i + 1][1])
    last = -1e9
    for i in range(len(seg) - 1):
        x, y, d = seg[i]
        if d - last < tick:
            continue
        last = d
        dx = seg[i + 1][0] - x
        dy = seg[i + 1][1] - y
        n = math.hypot(dx, dy)
        if n < 0.5:
            dx, dy, n = 0.0, 1.0, 1.0
        c.line(x - dy / n * 2, y + dx / n * 2, x + dy / n * 2, y - dx / n * 2)


def draw_ship(c, cam, w=W, h=H, r=5):
    """The boat is always dead centre, so this is really a reticle. Open ring
    with a gap fore and aft, so the track reads through it."""
    cx, cy = w * 0.5, h * 0.5
    c.arc(cx, cy, r, math.radians(20), math.radians(160))
    c.arc(cx, cy, r, math.radians(200), math.radians(340))
    c.line(cx, cy - r - 4, cx, cy - r - 1)          # course pointer
    c.px(int(cx), int(cy))


def draw_scale(c, cam, w=W, h=H, alpha=1.0):
    """A bar scale, because the zoom changes and a map without one is
    decoration rather than a chart."""
    nice = (200, 500, 1000, 2000, 5000)
    target = span_km(cam.R, w * 0.30)
    km = min(nice, key=lambda v: abs(math.log(v / max(target, 1.0))))
    px = cam.R * math.sin(km / 6371.0)
    if px < 12 or px > w - 30:
        return
    # clear of the two caption lines below it, whichever of them is present
    y = h - 14 - 3 * (text_height(T_MED) + 5) - 6
    x0 = 10
    if alpha > 0.4:
        c.line(x0, y, x0 + px, y)
        c.line(x0, y - 4, x0, y + 4)
        c.line(x0 + px, y - 4, x0 + px, y + 4)
    # always above the left end of the bar: a label chasing the right end
    # collides with the frame edge at wide zooms and with the bar itself at
    # narrow ones, and above-left is the only position that never does either
    label(c, x0, y - text_height(T_MED) - 5, "%d KM" % km, scale=T_MED,
          alpha=alpha)


def draw_caption(c, track, day, w=W, h=H, alpha=1.0):
    conf = track.confidence(day)
    la, lo = track.position(day)
    ns = "N" if la >= 0 else "S"
    ew = "E" if lo >= 0 else "W"
    # Day first and big: it is the one number on the chart a passer-by can
    # act on, and it answers "how far through is this thing" without needing
    # the bar. The position underneath at reading size.
    # One size for the whole block. DAY used to be T_BIG with OF 1018 tucked
    # beside it at T_MED, which made a headline out of the counter -- and the
    # counter is the least interesting number on the chart now that the
    # status line carries the actual date.
    label(c, 10, 8, "DAY %d OF %d" % (int(day), track.days[-1]),
          scale=T_MED, alpha=alpha)
    label(c, 10, 8 + text_height(T_MED) + 5, "%d%s%s  %d%s%s"
          % (abs(int(la)), "\xb0", ns, abs(int(lo)), "\xb0", ew),
          scale=T_MED, alpha=alpha)

    # Bottom left: what the ship is doing. When under way it is worth saying
    # where to, because a course line with no destination is only half a
    # statement. The confidence flag rides on this line rather than getting
    # its own, since the only positions we are unsure of are ones at sea.
    # Two lines, because one of them is often long and neither may be cut.
    # "TRACK INFERRED" is gone: it was an honest confidence flag and it was
    # also the only line on the chart that talked about the model rather than
    # the voyage, which on a piece meant to be looked at is a footnote read
    # aloud. The uncertainty is documented in the plan and in the card that
    # goes in the box; it does not need to be on the panel every ninety
    # seconds.
    lines = list(wrap(track.status(day), w - 20))
    if track.anchored(day) is None:
        port, away = track.next_port(day)
        lines.append(trim("NEXT: %s %dD" % (port, int(away)), w - 20))
    y = h - 10 - text_height(T_MED) - (len(lines) - 1) * (text_height(T_MED) + 5)
    for i, ln in enumerate(lines):
        label(c, 10, y + i * (text_height(T_MED) + 5), ln, scale=T_MED,
              alpha=alpha)


# North stays up.
#
# The original argument for course-up was that it makes a portrait panel the
# right shape: a voyage wants to show ahead and behind more than the water
# either side, and Drake's track is mostly north-south down the Atlantic and
# up the Americas. That argument is still true, and it is still not worth it.
# Course-up means the world rotates under you, so the same coastline arrives
# at a different angle every time and you have to re-read the map from
# scratch on every appearance. North-up is the convention for a reason: the
# shape of South America becomes something you recognise instead of something
# you decode. The panel is a little less efficiently filled and the map is a
# great deal more legible, and legibility wins on a screen you glance at.
#
# Camera keeps the rotation -- it is two multiplies and it costs nothing to
# leave in -- so this is one constant to flip if it ever wants revisiting.
NORTH_UP = True


def chrome_alpha(R):
    """How solidly the PLACE NAMES are drawn at this zoom.

    Nothing on the globe, fully on by a third of the way in. The names arrive
    through the ordered dither as the camera moves, so the chart resolves into
    being labelled rather than having a legend dropped on it.

    This governs the names and nothing else. The day, the position, the status
    and the scale bar are drawn solid at every zoom: they answer "where is the
    ship and how far through is this" and that question is exactly as live on
    the globe as it is at chart scale. It was briefly applied to those too,
    which made the opening shot beautifully clean and also made it say
    nothing."""
    f = (math.log(max(R, 1.0)) - math.log(R_GLOBE)) / \
        (math.log(R_CHART) - math.log(R_GLOBE))
    return max(0.0, min(1.0, (f - 0.05) / 0.28))


def draw_places(c, cam, track, day, R, w=W, h=H, alpha=1.0):
    """Names on the coast.

    Two sources, both period-safe: the voyage's own anchorages, which are in
    the waypoint table already, and geography -- capes, straits, island
    groups -- which has no founding date. See places.py for why this is not
    a list of cities.

    Placement is greedy against a list of boxes already occupied, in priority
    order: the ship's own stops first, then geography by rank, then by
    distance from the middle of the frame. A label that will not fit is
    dropped rather than shuffled, because a chart where the names have been
    nudged off their features to make room is worse than a chart with fewer
    names."""
    # the zones the chrome owns: the day block at the top, and the scale bar
    # plus two caption lines at the bottom. Measured from the same constants
    # those use, so moving one moves the other.
    taken = [(0, 0, w, 8 + 2 * text_height(T_MED) + 5 + 8),
             (0, h - 14 - 4 * (text_height(T_MED) + 5) - 14, w, h)]

    def fits(x, y, tw, th):
        for bx, by, bw, bh in taken:
            if (x < bx + bw and x + tw > bx
                    and y < by + bh and y + th > by):
                return False
        return 0 <= x and x + tw <= w and 0 <= y and y + th <= h

    # Rank governs both what appears and what wins the space, and it has to
    # depend on zoom or the anchorages swamp everything: at globe scale the
    # first version filled the Pacific with twelve Peruvian roadsteads and
    # never got as far as CAPE HORN. On the globe you want the half-dozen
    # names that orient a hemisphere; at chart scale you want every stop the
    # ship made. The two places that are always worth naming, at any zoom,
    # are where the ship is and where it is going next.
    mr = places.rank_for(R, R_GLOBE, R_CHART)
    if mr <= 0 or alpha <= 0.02:
        return
    cap = (0, 5, 9, 14)[mr]
    port, _away = track.next_port(day)
    here = track.anchored(day)

    cands = []
    seen = set()
    for wp in track.wp:                              # the ship's own stops
        if not wp[4] or wp[4] in seen:
            continue
        seen.add(wp[4])
        rank = 0 if wp[4] in (port, here) else 2
        if rank > mr:
            continue
        x, y, vis = cam.project(wp[1], wp[2], w, h)
        if vis and -20 <= x <= w + 20 and -10 <= y <= h + 10:
            cands.append((rank, x, y, wp[4]))
    for x, y, rank, name in places.visible(cam, w, h, mr):
        if name in seen:
            continue
        cands.append((rank, x, y, name))
    cands.sort(key=lambda t: (t[0], abs(t[2] - h * 0.5) + abs(t[1] - w * 0.5)))

    th = text_height(T_MED)
    for _rank, x, y, name in cands[:cap]:
        s = trim(name, w - 40)
        tw = text_width(s, scale=T_MED)
        # right of the mark by preference, left if that runs off the frame
        for ox in (7, -7 - tw):
            tx, ty = x + ox, y - th // 2
            if fits(tx - 2, ty - 2, tw + 4, th + 4):
                if alpha > 0.5:
                    c.circle(x, y, 2)
                label(c, tx, ty, s, scale=T_MED, alpha=alpha)
                taken.append((tx - 3, ty - 3, tw + 6, th + 6))
                break


def render_map(canvas, coast, track, day, R, chrome=True, w=W, h=H):
    """One frame of the map interlude."""
    canvas.clear()
    la, lo = track.position(day)
    cam = Camera(la, lo, 0.0 if NORTH_UP else track.bearing(day), R)
    if chrome:
        draw_graticule(canvas, cam, w, h)
    coast.draw(canvas, cam, w, h)
    draw_limb(canvas, cam, w, h)
    draw_track(canvas, track, cam, day, w, h)
    if chrome:
        draw_places(canvas, cam, track, day, R, w, h, chrome_alpha(R))
    draw_ship(canvas, cam, w, h)
    if chrome:
        draw_scale(canvas, cam, w, h)
        draw_caption(canvas, track, day, w, h)
    return cam


# --------------------------------------------------------------------------
# the zoom
# --------------------------------------------------------------------------
#
# The interlude is a camera move, not a screen.  It opens on the globe --
# limb visible, whole track in frame, unmistakably the Earth -- and dollies
# in until the frame is full of local water.  The half-empty globe is only
# ever on screen while moving through it, so the panel is never sitting
# there wasting a third of itself.

R_GLOBE = W / 2.0 - 2.0           # whole hemisphere inside the frame width,
                                  # with two pixels of air so the limb is not
                                  # cut by the edge. Derived rather than
                                  # written down, because the panel changed
                                  # once and this was the only constant that
                                  # did not follow it.
R_FILL = fill_radius(W, H)        # 233.2: limb exactly clears the corners
R_CHART = 1400.0                  # ~900 km across the frame


def zoom_radius(f):
    """f in 0..1 across the interlude. Geometric in R, because a linear ramp
    in radius reads as a lurch -- the eye judges zoom multiplicatively."""
    f = max(0.0, min(1.0, f))
    # ease in and out
    s = f * f * (3.0 - 2.0 * f)
    return R_GLOBE * (R_CHART / R_GLOBE) ** s
