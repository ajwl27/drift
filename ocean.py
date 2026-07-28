#!/usr/bin/env python3
"""
OCEAN  -  real climatology, sampled by where the ship is and what month it is.

475 kB of uint8 in flash, read in place -- twelve monthly steps of sea
surface temperature and mixed layer depth, four seasonal steps of nitrate,
and two static fields, on a 2 degree grid. No allocation in the hot path, one
bilinear blend and one linear interpolation in time per query, and the whole
thing is called a handful of times a simulated day.

Replaces the latitudinal stopgap in Environment. What it buys, beyond
accuracy: the Humboldt, the Benguela, the Southern Ocean nitrate reservoir
and the oligotrophic gyres stop being things we would have had to invent and
become things the model discovers.

The land problem is the only fiddly part. A 2 degree cell containing
Ternate is mostly Halmahera, and Drake anchors in a good many places whose
grid cell is more land than water. So the bilinear blend weights only the
ocean corners, and if all four are land it spirals outward to the nearest
ocean cell. Sampling the ocean from a position that a coarse grid thinks is
dry is not an edge case here, it is most of the interesting anchorages.
"""

import math
import struct

CELL = 2.0
LAND = 255

SST_LO, SST_HI = -2.0, 34.0
MLD_LO, MLD_HI = 5.0, 600.0
NO3_LO, NO3_HI = 0.0, 40.0
SHELF_MAX = 2000.0
BOT_LO, BOT_HI = 1.0, 11000.0        # log-quantised; see tools/make_bathy.py

SST, MLD, NO3, SHELF, IRON, BOTTOM = range(6)


class Ocean:
    __slots__ = ("b", "nlon", "nlat", "nmon", "nsea", "base", "n", "_ocean")

    def __init__(self, path="data/ocean.bin"):
        with open(path, "rb") as f:
            self.b = f.read()
        if self.b[:4] != b"DRFO":
            raise ValueError("not an ocean file: %r" % self.b[:4])
        ver, self.nlon, self.nlat, self.nmon, self.nsea = struct.unpack_from(
            "<BBBBB", self.b, 4)
        if ver not in (1, 2):
            raise ValueError("ocean.bin version %d, expected 1 or 2" % ver)
        self.n = self.nlon * self.nlat
        o = 9
        # byte offset of step 0 of each field. Version 2 appends bottom depth
        # after the v1 fields, so every v1 offset is unchanged and a v2 reader
        # can still open a v1 file -- it simply has no bathymetry, which
        # bottom_m() reports honestly rather than guessing at.
        fields = [(SST, self.nmon), (MLD, self.nmon), (NO3, self.nsea),
                  (SHELF, 1), (IRON, 1)]
        if ver >= 2:
            fields.append((BOTTOM, 1))
        self.base = {}
        for field, steps in fields:
            self.base[field] = o
            o += steps * self.n
        if o != len(self.b):
            raise ValueError("ocean.bin is %d bytes, expected %d" % (len(self.b), o))
        # which cells are ocean, for the land search. One bit each would do on
        # the MCU; here a tuple of bools is clearer and costs 2.6 kB.
        s0 = self.base[SST]
        self._ocean = tuple(self.b[s0 + k] != LAND for k in range(self.n))

    # -- indexing ---------------------------------------------------------

    def _idx(self, i, j):
        return (j % self.nlat) * self.nlon + (i % self.nlon)

    def _raw(self, field, step, i, j):
        return self.b[self.base[field] + step * self.n + self._idx(i, j)]

    def _nearest_ocean(self, i, j):
        """Spiral outward until an ocean cell turns up. Bounded at 6 rings,
        which is 30 degrees -- if there is no water within that, the caller
        has bigger problems than interpolation."""
        if self._ocean[self._idx(i, j)]:
            return i, j
        for r in range(1, 7):
            best = None
            bd = 1e9
            for dj in range(-r, r + 1):
                for di in range(-r, r + 1):
                    if max(abs(di), abs(dj)) != r:
                        continue
                    jj = j + dj
                    if not 0 <= jj < self.nlat:
                        continue
                    if self._ocean[self._idx(i + di, jj)]:
                        d = di * di + dj * dj
                        if d < bd:
                            bd, best = d, (i + di, jj)
            if best:
                return best
        return i, j

    # -- sampling ---------------------------------------------------------

    def _bilinear(self, field, step, lat, lon):
        """Ocean-weighted bilinear. Corners on land contribute nothing, and
        their weight is redistributed rather than dragging the value toward a
        sentinel."""
        x = (lon + 180.0) / CELL - 0.5
        y = (lat + 90.0) / CELL - 0.5
        i0 = math.floor(x)
        j0 = math.floor(y)
        fx = x - i0
        fy = y - j0
        acc = 0.0
        wsum = 0.0
        for dj, wy in ((0, 1.0 - fy), (1, fy)):
            jj = j0 + dj
            if not 0 <= jj < self.nlat:
                continue
            for di, wx in ((0, 1.0 - fx), (1, fx)):
                w = wx * wy
                if w <= 0.0:
                    continue
                v = self._raw(field, step, i0 + di, jj)
                if v == LAND:
                    continue
                acc += v * w
                wsum += w
        if wsum > 1e-9:
            return acc / wsum
        i, j = self._nearest_ocean(int(round(x)), max(0, min(self.nlat - 1, int(round(y)))))
        v = self._raw(field, step, i, j)
        return None if v == LAND else float(v)

    def _cyclic(self, field, nsteps, lat, lon, day):
        """Linear in time between climatological steps, wrapping at the year.
        Without this the ocean would change in twelve discrete jolts a year,
        and the ecosystem would see each one as a shock."""
        doy = day % 365.25
        u = doy / 365.25 * nsteps - 0.5
        s0 = math.floor(u)
        f = u - s0
        a = self._bilinear(field, int(s0) % nsteps, lat, lon)
        b = self._bilinear(field, int(s0 + 1) % nsteps, lat, lon)
        if a is None:
            return b
        if b is None:
            return a
        return a + (b - a) * f

    def _static(self, field, lat, lon):
        return self._bilinear(field, 0, lat, lon)

    # -- the public fields -------------------------------------------------

    def sst(self, lat, lon, day):
        v = self._cyclic(SST, self.nmon, lat, lon, day)
        return None if v is None else SST_LO + (v / 254.0) * (SST_HI - SST_LO)

    def mld(self, lat, lon, day):
        v = self._cyclic(MLD, self.nmon, lat, lon, day)
        if v is None:
            return None
        return MLD_LO * (MLD_HI / MLD_LO) ** (v / 254.0)

    def nitrate(self, lat, lon, day):
        v = self._cyclic(NO3, self.nsea, lat, lon, day)
        return None if v is None else NO3_LO + (v / 254.0) * (NO3_HI - NO3_LO)

    def shelf_km(self, lat, lon):
        v = self._static(SHELF, lat, lon)
        return SHELF_MAX if v is None else (v / 254.0) * SHELF_MAX

    def bottom_m(self, lat, lon):
        """Depth of the seabed, metres. None if this file has no bathymetry.

        INTERPOLATED IN LOG SPACE, which is not fussiness, and which comes
        free: the field is log-quantised, so blending the stored BYTES and
        dequantising afterwards is a geometric mean rather than an arithmetic
        one. MLD already works this way for the same reason.

        It matters at every continental margin, and the track is mostly
        continental margin. The arithmetic mean of a 90 m shelf cell and a
        4,000 m abyssal one is 2,045 m -- a depth that exists nowhere on a
        real margin, and one that would put a shelf species in open ocean for
        a full cell either side of the shelf break. The geometric mean is
        600 m, which is the upper slope, which is what is actually there."""
        if BOTTOM not in self.base:
            return None
        v = self._static(BOTTOM, lat, lon)
        return None if v is None else BOT_LO * (BOT_HI / BOT_LO) ** (v / 254.0)

    def iron(self, lat, lon):
        """0..1 ceiling, applied by Liebig's law of the minimum against the
        nitrogen term. Low in the Southern Ocean and the equatorial Pacific,
        restored near land."""
        v = self._static(IRON, lat, lon)
        return 1.0 if v is None else v / 254.0
