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

from drift import Canvas, W, H, text, text_width
from voyage import Camera, Track, fill_radius, span_km


# --------------------------------------------------------------------------
# coastline, walked in place
# --------------------------------------------------------------------------

class Coast:
    """9084 points at 0.2 degree tolerance, 38 kB. Kept as one bytes object
    and indexed, never unpacked into Python tuples -- which is both faster
    here and an honest model of what the C version does with a const array
    in flash."""

    __slots__ = ("b", "n", "offs")

    def __init__(self, path):
        with open(path, "rb") as f:
            self.b = f.read()
        self.n = struct.unpack_from("<H", self.b, 0)[0]
        self.offs = []
        o = 2
        for _ in range(self.n):
            m = struct.unpack_from("<H", self.b, o)[0]
            self.offs.append((o + 2, m))
            o += 2 + 4 * m

    def draw(self, c, cam, w=W, h=H):
        b = self.b
        unpack = struct.unpack_from
        segs = 0
        for (base, m) in self.offs:
            px = py = 0.0
            pv = False
            for k in range(m):
                lon, lat = unpack("<hh", b, base + 4 * k)
                x, y, vis = cam.project(lat * 0.01, lon * 0.01, w, h)
                if pv and vis:
                    # both ends on this side of the world: clip to frame
                    if not ((x < 0 and px < 0) or (x >= w and px >= w)
                            or (y < 0 and py < 0) or (y >= h and py >= h)):
                        c.line(px, py, x, y)
                        segs += 1
                px, py, pv = x, y, vis
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


def draw_scale(c, cam, w=W, h=H):
    """A bar scale, because the zoom changes and a map without one is
    decoration rather than a chart."""
    nice = (200, 500, 1000, 2000, 5000)
    target = span_km(cam.R, w * 0.30)
    km = min(nice, key=lambda v: abs(math.log(v / max(target, 1.0))))
    px = cam.R * math.sin(km / 6371.0)
    if px < 12 or px > w - 30:
        return
    y = h - 30
    x0 = 12
    c.line(x0, y, x0 + px, y)
    c.line(x0, y - 3, x0, y + 3)
    c.line(x0 + px, y - 3, x0 + px, y + 3)
    text(c, x0 + px + 4, y - 2, "%d KM" % km)


def draw_caption(c, track, day, w=W, h=H):
    frm, to = track.leg(day)
    conf = track.confidence(day)
    la, lo = track.position(day)
    text(c, 12, 14, "DAY %d OF %d" % (int(day), track.days[-1]))
    ns = "N" if la >= 0 else "S"
    ew = "E" if lo >= 0 else "W"
    text(c, 12, 22, "%02d%s%s  %03d%s%s"
         % (abs(int(la)), "\xb0", ns, abs(int(lo)), "\xb0", ew))
    lab = to if conf >= 1 else to + " (INFERRED)"
    text(c, 12, h - 16, lab[:34])


def render_map(canvas, coast, track, day, R, chrome=True, w=W, h=H):
    """One frame of the map interlude."""
    canvas.clear()
    la, lo = track.position(day)
    cam = Camera(la, lo, track.bearing(day), R)
    if chrome:
        draw_graticule(canvas, cam, w, h)
    coast.draw(canvas, cam, w, h)
    draw_limb(canvas, cam, w, h)
    draw_track(canvas, track, cam, day, w, h)
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

R_GLOBE = 118.0                   # whole hemisphere inside the 240 width
R_FILL = fill_radius(W, H)        # 233.2: limb exactly clears the corners
R_CHART = 1400.0                  # ~900 km across the frame


def zoom_radius(f):
    """f in 0..1 across the interlude. Geometric in R, because a linear ramp
    in radius reads as a lurch -- the eye judges zoom multiplicatively."""
    f = max(0.0, min(1.0, f))
    # ease in and out
    s = f * f * (3.0 - 2.0 * f)
    return R_GLOBE * (R_CHART / R_GLOBE) ** s
