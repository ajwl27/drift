#!/usr/bin/env python3
"""Turn a Natural Earth coastline shapefile into the compact binary the panel
carries in flash.

    python3 tools/make_coast.py ne_50m_coastline data/coast.bin --tol 0.2

Format, little-endian throughout:

    uint16  n_polylines
    then per polyline:
        uint16  n_points
        n_points * (int16 lon_centideg, int16 lat_centideg)

Centidegrees give ~1.1 km at the equator, which is a tenth of a pixel at the
tightest zoom the piece ever uses, and fits int16 with room to spare
(+-18000 / +-9000).  Polylines are split at the antimeridian during
preprocessing so the renderer never has to think about it.
"""

import math
import struct
import sys


def load_shapefile(path):
    import shapefile
    sf = shapefile.Reader(path)
    out = []
    for sh in sf.shapes():
        idx = list(sh.parts) + [len(sh.points)]
        for a, b in zip(idx[:-1], idx[1:]):
            pts = [(float(x), float(y)) for x, y in sh.points[a:b]]
            if len(pts) >= 2:
                out.append(pts)
    return out


def split_antimeridian(pts):
    """Natural Earth stores lon in -180..180, so a polyline that crosses the
    date line contains a 360-degree jump. Left in, it draws a line straight
    across the map. Split there instead."""
    runs = [[pts[0]]]
    for p, q in zip(pts[:-1], pts[1:]):
        if abs(q[0] - p[0]) > 180.0:
            runs.append([q])
        else:
            runs[-1].append(q)
    return [r for r in runs if len(r) >= 2]


def douglas_peucker(pts, tol):
    """Iterative, so a 60k-point coastline cannot blow the stack."""
    n = len(pts)
    if n < 3:
        return pts
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        ax, ay = pts[i]
        bx, by = pts[j]
        dx, dy = bx - ax, by - ay
        den = math.hypot(dx, dy)
        best, bi = -1.0, -1
        for k in range(i + 1, j):
            px, py = pts[k]
            if den < 1e-12:
                d = math.hypot(px - ax, py - ay)
            else:
                d = abs(dx * (ay - py) - (ax - px) * dy) / den
            if d > best:
                best, bi = d, k
        if best > tol:
            keep[bi] = True
            stack.append((i, bi))
            stack.append((bi, j))
    return [p for p, k in zip(pts, keep) if k]


def build(src, dst, tol):
    raw = load_shapefile(src)
    lines = []
    for pts in raw:
        for run in split_antimeridian(pts):
            s = douglas_peucker(run, tol)
            if len(s) >= 2:
                lines.append(s)

    blob = bytearray(struct.pack("<H", len(lines)))
    for pts in lines:
        blob += struct.pack("<H", len(pts))
        for lon, lat in pts:
            blob += struct.pack("<hh", int(round(lon * 100.0)),
                                int(round(lat * 100.0)))
    with open(dst, "wb") as f:
        f.write(blob)

    npts = sum(len(p) for p in lines)
    print("%s -> %s" % (src, dst))
    print("  %d polylines, %d points, tolerance %.2f deg" % (len(lines), npts, tol))
    print("  %d bytes (%.1f kB)" % (len(blob), len(blob) / 1024.0))


def read(path):
    """The reference decoder. The MCU version walks the same bytes in place
    without allocating anything."""
    with open(path, "rb") as f:
        b = f.read()
    o = 0
    (n,), o = struct.unpack_from("<H", b, o), o + 2
    lines = []
    for _ in range(n):
        (m,), o = struct.unpack_from("<H", b, o), o + 2
        pts = []
        for _ in range(m):
            lon, lat = struct.unpack_from("<hh", b, o)
            o += 4
            pts.append((lon / 100.0, lat / 100.0))
        lines.append(pts)
    return lines


if __name__ == "__main__":
    tol = 0.2
    if "--tol" in sys.argv:
        i = sys.argv.index("--tol")
        tol = float(sys.argv[i + 1])
        del sys.argv[i:i + 2]
    build(sys.argv[1], sys.argv[2], tol)
