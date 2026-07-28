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
O2_LO, O2_HI = 0.0, 420.0
O2_Z0, O2_Z1 = 0.0, 50.0             # the two depths the file carries

SST, MLD, NO3, SHELF, IRON, O2S, O2D = range(7)

# version 2 added oxygen by APPENDING after every version 1 field, so the
# offsets of the first five are identical in both and a v1 file just stops
# short. Which is the whole point: adding a field must not invalidate a
# panel already carrying a v1 blob in flash.
V1_FIELDS = (SST, MLD, NO3, SHELF, IRON)
V2_FIELDS = (O2S, O2D)


class Ocean:
    __slots__ = ("b", "ver", "nlon", "nlat", "nmon", "nsea", "base", "n",
                 "_ocean")

    def __init__(self, path="data/ocean.bin"):
        with open(path, "rb") as f:
            self.b = f.read()
        if self.b[:4] != b"DRFO":
            raise ValueError("not an ocean file: %r" % self.b[:4])
        self.ver, self.nlon, self.nlat, self.nmon, self.nsea = \
            struct.unpack_from("<BBBBB", self.b, 4)
        if self.ver not in (1, 2):
            raise ValueError("ocean.bin version %d, expected 1 or 2" % self.ver)
        self.n = self.nlon * self.nlat
        o = 9
        # byte offset of step 0 of each field
        self.base = {}
        layout = [(SST, self.nmon), (MLD, self.nmon), (NO3, self.nsea),
                  (SHELF, 1), (IRON, 1)]
        if self.ver >= 2:
            layout += [(O2S, 1), (O2D, 1)]
        for field, steps in layout:
            self.base[field] = o
            o += steps * self.n
        if o != len(self.b):
            raise ValueError("ocean.bin is %d bytes, expected %d for v%d"
                             % (len(self.b), o, self.ver))
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

    def oxygen(self, lat, lon, z):
        """Dissolved oxygen in umol/kg at depth z, or None on a v1 file.

        Linear between the two carried levels, and linear on out below the
        lower one -- which sounds cavalier and is not, because the panel only
        ever asks about the top 55 m and the second anchor is at 50. Checked
        against the full WOA profile at the worst site on the track, the Peru
        margin off Callao: this returns 115 umol/kg at 55 m where the
        43-level profile says 110.

        Above 50 m it is an interpolation and below it a five-metre
        extrapolation, and the oxycline is straight through both."""
        if self.ver < 2:
            return None
        a = self._static(O2S, lat, lon)
        b = self._static(O2D, lat, lon)
        if a is None or b is None:
            return None
        a = O2_LO + (a / 254.0) * (O2_HI - O2_LO)
        b = O2_LO + (b / 254.0) * (O2_HI - O2_LO)
        f = (z - O2_Z0) / (O2_Z1 - O2_Z0)
        return max(0.0, a + (b - a) * f)

    def iron(self, lat, lon):
        """0..1 ceiling, applied by Liebig's law of the minimum against the
        nitrogen term. Low in the Southern Ocean and the equatorial Pacific,
        restored near land."""
        v = self._static(IRON, lat, lon)
        return 1.0 if v is None else v / 254.0
