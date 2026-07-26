#!/usr/bin/env python3
"""
Rasterise Natural Earth land polygons into a bitmask, for routing.

    python3 tools/make_landmask.py /tmp/land/ne_10m_land data/land.bin --cell 0.1

This is a BUILD-TIME artefact and never reaches the panel. Its whole job is
to let tools/make_route.py check whether a great circle between two waypoints
crosses a continent, and to find a way round if it does. The output of that is
extra waypoints in a table, which cost a few hundred bytes and no runtime code
at all -- so the finest mask we care to compute here is free.

0.1 degree is about 11 km. That resolves every strait a sailing ship could
use except the very narrowest: Primera Angostura in the Strait of Magellan is
three kilometres across and reads as solid land at any resolution we would
want to carry. Which is fine, and is why the router tolerates SHORT land
crossings -- see make_route.py.

Format: 'DRFL', uint8 version, uint16 nlon, uint16 nlat, then one bit per
cell, row-major from -90, LSB-first within each byte.
"""

import struct
import sys


def rasterise(shp_path, cell):
    import shapefile
    from PIL import Image, ImageDraw

    nlon = int(round(360.0 / cell))
    nlat = int(round(180.0 / cell))
    img = Image.new("1", (nlon, nlat), 0)
    d = ImageDraw.Draw(img)

    sf = shapefile.Reader(shp_path)
    npoly = 0
    for sh in sf.shapes():
        idx = list(sh.parts) + [len(sh.points)]
        for a, b in zip(idx[:-1], idx[1:]):
            pts = sh.points[a:b]
            if len(pts) < 3:
                continue
            # Rings that straddle the antimeridian would smear a horizontal
            # band across the whole map when filled, so they are drawn twice
            # -- once shifted each way -- and the raster is clipped.
            for shift in (0.0, -360.0, 360.0):
                px = [(((x + shift) + 180.0) / cell, (y + 90.0) / cell)
                      for x, y in pts]
                xs = [p[0] for p in px]
                if max(xs) < -1 or min(xs) > nlon + 1:
                    continue
                d.polygon(px, fill=1)
            npoly += 1
    return img, nlon, nlat, npoly


# Straits a sailing ship can use that a 0.1 degree raster closes. These are
# not fudges -- they are corrections to a known artefact of rasterising, and
# each one is a passage that is on every chart ever drawn. Without the first
# of them the router sends Drake round Cape Horn rather than through the
# strait he is famous for, which would be both wrong and ironic.
SEA_CORRIDORS = (
    ("Strait of Magellan", 3,
     ((-52.45, -68.40), (-52.95, -70.30), (-53.55, -70.95),
      (-53.90, -72.40), (-53.10, -73.90), (-52.70, -74.70))),
    ("Beagle Channel", 2,
     ((-54.90, -68.30), (-54.93, -70.00), (-54.60, -71.60))),
    ("Torres Strait", 2, ((-10.60, 142.20), (-10.00, 144.20))),
    ("Sunda Strait", 2, ((-5.70, 105.20), (-6.40, 105.60))),
    ("Strait of Malacca", 2, ((5.60, 98.00), (2.50, 101.30), (1.20, 103.60))),
    ("Makassar Strait", 3, ((-1.00, 118.60), (-4.00, 118.20), (-5.60, 117.60))),
)


def carve(d, corridors, cell, nlon, nlat):
    """Punch the known straits open."""
    n = 0
    for name, halfwidth, pts in corridors:
        px = [(((lo + 180.0) / cell), ((la + 90.0) / cell)) for la, lo in pts]
        d.line(px, fill=0, width=halfwidth * 2 + 1)
        n += 1
    return n


def build(shp_path, dst, cell=0.1):
    from PIL import ImageDraw
    img, nlon, nlat, npoly = rasterise(shp_path, cell)
    ncar = carve(ImageDraw.Draw(img), SEA_CORRIDORS, cell, nlon, nlat)
    px = img.load()
    blob = bytearray(b"DRFL")
    blob += struct.pack("<BHH", 1, nlon, nlat)
    row_bytes = (nlon + 7) // 8
    land = 0
    for j in range(nlat):
        row = bytearray(row_bytes)
        for i in range(nlon):
            if px[i, j]:
                row[i >> 3] |= 1 << (i & 7)
                land += 1
        blob += row
    with open(dst, "wb") as f:
        f.write(blob)
    print("%s  %d bytes (%.1f kB)" % (dst, len(blob), len(blob) / 1024.0))
    print("  %d x %d at %.2f deg from %d rings, %.1f%% land, %d straits carved"
          % (nlon, nlat, cell, npoly, 100.0 * land / (nlon * nlat), ncar))


class LandMask:
    """The reference reader. Build-time only."""

    __slots__ = ("b", "nlon", "nlat", "cell", "off", "row")

    def __init__(self, path="data/land.bin"):
        with open(path, "rb") as f:
            self.b = f.read()
        if self.b[:4] != b"DRFL":
            raise ValueError("not a land mask")
        ver, self.nlon, self.nlat = struct.unpack_from("<BHH", self.b, 4)
        self.cell = 360.0 / self.nlon
        self.off = 9
        self.row = (self.nlon + 7) // 8

    def ij(self, lat, lon):
        i = int((((lon + 180.0) % 360.0)) / self.cell) % self.nlon
        j = min(self.nlat - 1, max(0, int((lat + 90.0) / self.cell)))
        return i, j

    def at(self, lat, lon):
        i, j = self.ij(lat, lon)
        return self.at_ij(i, j)

    def at_ij(self, i, j):
        if not 0 <= j < self.nlat:
            return True                      # off the poles: treat as blocked
        i %= self.nlon
        return bool(self.b[self.off + j * self.row + (i >> 3)] >> (i & 7) & 1)

    def ll(self, i, j):
        return (-90.0 + (j + 0.5) * self.cell,
                -180.0 + (i % self.nlon + 0.5) * self.cell)


if __name__ == "__main__":
    cell = 0.1
    if "--cell" in sys.argv:
        k = sys.argv.index("--cell")
        cell = float(sys.argv[k + 1])
        del sys.argv[k:k + 2]
    build(sys.argv[1], sys.argv[2], cell)
