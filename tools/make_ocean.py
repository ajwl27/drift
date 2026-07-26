#!/usr/bin/env python3
"""
Turn public ocean climatology into the small binary the panel carries in flash.

    python3 tools/make_ocean.py /tmp/ocean data/ocean.bin

Inputs, all public domain or CC-BY, all downloaded once and thrown away:

    sst.nc      NOAA OISST v2.1 monthly climatology 1991-2020, 0.25 deg, 44 MB
                https://downloads.psl.noaa.gov/Datasets/noaa.oisst.v2.highres/
    mld.nc      Ifremer / de Boyer Montegut mixed layer depth, 1 deg, monthly,
                CC-BY-4.0, 6 MB.  https://www.seanoe.org/data/00870/98226/
    n13..n16.nc World Ocean Atlas 2023 nitrate, seasonal, 1 deg, ~24 MB each
                https://www.ncei.noaa.gov/access/world-ocean-atlas-2023/

Output: a 2 x 2 degree global grid, 180 x 90 cells, several fields, uint8.

Why 2 degrees and not 5.  Five was the plan, on the reasoning that 550 km is
coarser than a 240 x 400 panel can express.  That reasoning is right for
temperature and wrong for nutrients, which is the field with all the
structure and the only one the piece is really about.  Measured, at the sites
that matter (surface nitrate, austral winter, mmol/m3):

                     1 deg   2 deg   3 deg   5 deg
    Peru 15S           9.2     9.2     9.7     9.0
    Benguela           6.9     6.1     7.0     3.8
    Equatorial Pac     5.1     4.8     4.3     3.5
    S Pacific gyre     0.0     0.0     0.0     0.1

Five degrees loses nearly half the Benguela signal, because an eastern
boundary upwelling is a 100 km strip and a 550 km cell averages it with 450
km of ocean that is not upwelling.  Two degrees keeps it.  The cost is 475 kB
instead of 130, out of four megabytes -- which is not a real cost, and the
Humboldt is the single most dramatic thing that happens on the whole voyage.

Everything is carried at 2 degrees rather than only the nutrients, because a
second grid would double the reader for no benefit anyone can see.  If flash
ever gets tight, SST and MLD would drop to 5 degrees for a saving of 320 kB
and no visible change at all.

Two fields are computed here rather than downloaded:

    shelf   distance from the coastline, from the same Natural Earth data the
            map uses.  A 469 MB bathymetry download to answer "is this
            coastal" would be absurd when the answer is already sitting in
            data/coast.bin.  It also carries the iron: shelf sediment and
            continental dust are where iron comes from, which is why the
            Southern Ocean blooms downstream of South Georgia and nowhere
            else.
    iron    three hand-drawn boxes for the HNLC regions.  There is no
            hobbyist-downloadable iron climatology -- Mahowald's pages are
            dead and the living equivalents are CMIP6 input4MIPs on ESGF,
            which is not a weekend download.  Simplified NPZ models routinely
            prescribe this, and Drake's track crosses two of the three boxes,
            so leaving it out would make the Southern Ocean and the equatorial
            Pacific bloom -- the one thing an HNLC region is defined by not
            doing.

Format, little-endian:

    magic  'DRFO'                       4 B
    uint8  version                      1
    uint8  n_lon (180), n_lat (90)      2
    uint8  n_month_sst, n_season_no3    2
    then, each row-major [step][lat][lon], uint8:
        sst      12 steps    -2 .. 34 C          255 = land
        mld      12 steps    log-scaled 5..600 m 255 = land
        no3       4 steps     0 .. 40 mmol/m3    255 = land
        shelf     1 step      distance to coast, 0..2000 km
        iron      1 step      0 = scarce .. 255 = replete
"""

import math
import struct
import sys
import os

NLON, NLAT = 180, 90         # 2 x 2 degrees
CELL = 2.0
NMON, NSEA = 12, 4
LAND = 255

SST_LO, SST_HI = -2.0, 34.0
MLD_LO, MLD_HI = 5.0, 600.0          # quantised in log space, see note
NO3_LO, NO3_HI = 0.0, 40.0
SHELF_MAX = 2000.0                   # km, saturates


def lon_of(i):
    return -180.0 + (i + 0.5) * CELL


def lat_of(j):
    return -90.0 + (j + 0.5) * CELL


def q(v, lo, hi):
    if v is None or v != v:
        return LAND
    f = (v - lo) / (hi - lo)
    return max(0, min(254, int(round(f * 254.0))))


def dq(b, lo, hi):
    return None if b == LAND else lo + (b / 254.0) * (hi - lo)


def q_log(v, lo, hi):
    """MLD is heavily right-skewed -- 10 to 50 m nearly everywhere, with
    winter deep-mixing excursions past 500 m. Linear uint8 would spend nine
    tenths of its codes on values that never occur and quantise the common
    range to nothing."""
    if v is None or v != v:
        return LAND
    v = max(lo, min(hi, v))
    f = math.log(v / lo) / math.log(hi / lo)
    return max(0, min(254, int(round(f * 254.0))))


def dq_log(b, lo, hi):
    return None if b == LAND else lo * (hi / lo) ** (b / 254.0)


# --------------------------------------------------------------------------

def regrid(da, lon_name, lat_name):
    """Box-average a global field onto the 2 degree grid.

    Done by hand rather than with xarray's coarsen because the sources have
    different resolutions and different longitude conventions, and because
    a 2 degree target from 0.25 or 1 degree source is simple binning -- a
    real regridder here would be ceremony."""
    import numpy as np
    lon = np.asarray(da[lon_name].values, dtype=float)
    lat = np.asarray(da[lat_name].values, dtype=float)
    lon = ((lon + 180.0) % 360.0) - 180.0        # unify to -180..180
    v = np.asarray(da.values, dtype=float)
    if v.ndim != 2:
        raise ValueError("expected a 2-D slice, got %r" % (v.shape,))
    # source cell -> target cell index
    ilon = np.clip(((lon + 180.0) / CELL).astype(int), 0, NLON - 1)
    ilat = np.clip(((lat + 90.0) / CELL).astype(int), 0, NLAT - 1)
    out = np.full((NLAT, NLON), np.nan)
    acc = np.zeros((NLAT, NLON))
    cnt = np.zeros((NLAT, NLON))
    good = np.isfinite(v)
    # np.add.at over the 2-D index pair
    jj = np.broadcast_to(ilat[:, None], v.shape)[good]
    ii = np.broadcast_to(ilon[None, :], v.shape)[good]
    np.add.at(acc, (jj, ii), v[good])
    np.add.at(cnt, (jj, ii), 1.0)
    nz = cnt > 0
    out[nz] = acc[nz] / cnt[nz]
    return out


def fill_gaps(grid, ocean, rounds=40):
    """Nearest-neighbour flood fill over ocean cells the source did not cover.

    WOA nutrient sampling is sparse -- it is ship casts, not satellite -- so
    there are ocean cells with no nitrate, especially at high latitude and in
    the narrow water around Tierra del Fuego. Quantised naively those become
    the land sentinel, and the reader then cannot tell "no data" from "not
    ocean" and returns nothing. Which is how the track plot came to have a
    hole in the nitrate exactly where Drake rounded the Horn.

    Fill from the neighbours instead. It is an admission that we do not know,
    made in the only form the format can carry."""
    import numpy as np
    g = np.array(grid, dtype=float)
    need = ocean & ~np.isfinite(g)
    for _ in range(rounds):
        if not need.any():
            break
        acc = np.zeros_like(g)
        cnt = np.zeros_like(g)
        for dj, di in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            n = np.roll(np.roll(g, dj, axis=0), di, axis=1)
            ok = np.isfinite(n)
            acc[ok] += n[ok]
            cnt[ok] += 1.0
        can = need & (cnt > 0)
        g[can] = acc[can] / cnt[can]
        need = ocean & ~np.isfinite(g)
    return g


def load_sst(path):
    import xarray as xr
    ds = xr.open_dataset(path, decode_times=False)
    out = [regrid(ds["sst"].isel(time=m), "lon", "lat") for m in range(12)]
    ds.close()
    return out


def load_mld(path):
    import xarray as xr
    ds = xr.open_dataset(path, decode_times=False)
    name = "mld_dr003" if "mld_dr003" in ds else list(ds.data_vars)[-1]
    out = [regrid(ds[name].isel(time=m), "lon", "lat") for m in range(12)]
    ds.close()
    return out


def load_no3(paths):
    import xarray as xr
    out = []
    for p in paths:
        ds = xr.open_dataset(p, decode_times=False)
        # n_an is the objectively analysed mean. Depth 0 is the surface, and
        # the 43-level depth dimension is why these files are 24 MB apiece.
        da = ds["n_an"].isel(time=0).sel(depth=0.0, method="nearest")
        out.append(regrid(da, "lon", "lat"))
        ds.close()
    return out


def load_shelf(coast_path):
    """Great-circle distance from each cell centre to the nearest coastline
    vertex. Brute force: 16,200 cells against 14,447 points is 234 million
    distance evaluations, which numpy does in a couple of seconds and which
    only ever runs here, never on the panel."""
    import numpy as np
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from tools.make_coast import read
    pts = [p for line in read(coast_path) for p in line]
    clon = np.radians(np.array([p[0] for p in pts]))
    clat = np.radians(np.array([p[1] for p in pts]))
    cx, cy, cz = (np.cos(clat) * np.cos(clon), np.cos(clat) * np.sin(clon),
                  np.sin(clat))
    out = np.zeros((NLAT, NLON))
    for j in range(NLAT):
        la = math.radians(lat_of(j))
        for i in range(NLON):
            lo = math.radians(lon_of(i))
            x, y, z = (math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo),
                       math.sin(la))
            d = np.max(cx * x + cy * y + cz * z)      # max cos = min angle
            out[j, i] = 6371.0 * math.acos(max(-1.0, min(1.0, float(d))))
    return out


# Three boxes, and the reasoning for each is in the header. Values are an
# iron ceiling in 0..1, applied by Liebig's law of the minimum against the
# nitrogen limitation.
HNLC = (
    # (lat0, lat1, lon0, lon1, ceiling)
    (-90.0, -50.0, -180.0, 180.0, 0.18),   # Southern Ocean, the big one
    (-10.0,  10.0, -180.0, -95.0, 0.28),   # equatorial Pacific, east of the
    (-10.0,  10.0,  150.0, 180.0, 0.34),   # dateline; Drake crosses both
    ( 40.0,  60.0,  150.0, 180.0, 0.35),   # subarctic North Pacific
    ( 40.0,  60.0, -180.0, -140.0, 0.35),
)


def load_iron(shelf_km):
    """Open ocean inside an HNLC box is iron-starved; everywhere else is
    replete enough not to matter. Proximity to land restores it, because
    shelf sediment and continental dust are where the iron comes from -- which
    is why the Southern Ocean blooms downstream of South Georgia and nowhere
    else."""
    import numpy as np
    out = np.ones((NLAT, NLON))
    for j in range(NLAT):
        la = lat_of(j)
        for i in range(NLON):
            lo = lon_of(i)
            for (a, b, c, d, ceil) in HNLC:
                if a <= la < b and c <= lo < d:
                    out[j, i] = min(out[j, i], ceil)
            # shelf and island iron, e-folding over 400 km
            # 180 km, not 400. At 400 the Drake Passage came out at an
            # iron ceiling of 0.63 -- comfortably enough to bloom, in the
            # stretch of water most famous for not blooming.
            near = math.exp(-shelf_km[j, i] / 180.0)
            out[j, i] = min(1.0, out[j, i] + (1.0 - out[j, i]) * near)
    return out


# --------------------------------------------------------------------------

def build(src, dst, coast="data/coast.bin"):
    import numpy as np
    sst = load_sst(os.path.join(src, "sst.nc"))
    mld = load_mld(os.path.join(src, "mld.nc"))
    no3 = load_no3([os.path.join(src, "n%d.nc" % k) for k in (13, 14, 15, 16)])
    shelf = load_shelf(coast)
    iron = load_iron(shelf)

    # SST is the most completely sampled field, so it defines the land mask;
    # MLD and nitrate have their own gaps (marginal seas, polar winter) which
    # would otherwise punch holes in the ocean.
    land = ~np.isfinite(sst[0])
    ocean = ~land
    # Every field is filled over the ocean mask before quantising, so a gap
    # in a source is never mistaken for land downstream.
    sst = [fill_gaps(g, ocean) for g in sst]
    mld = [fill_gaps(g, ocean) for g in mld]
    no3 = [fill_gaps(g, ocean) for g in no3]

    blob = bytearray(b"DRFO")
    blob += struct.pack("<BBBBB", 1, NLON, NLAT, NMON, NSEA)

    def emit(grid, fn, lo, hi):
        for j in range(NLAT):
            for i in range(NLON):
                blob.append(LAND if land[j, i] else fn(grid[j, i], lo, hi))

    for m in range(12):
        emit(sst[m], q, SST_LO, SST_HI)
    for m in range(12):
        emit(mld[m], q_log, MLD_LO, MLD_HI)
    for s in range(4):
        emit(no3[s], q, NO3_LO, NO3_HI)
    for j in range(NLAT):                       # shelf: valid over land too
        for i in range(NLON):
            blob.append(q(min(shelf[j, i], SHELF_MAX), 0.0, SHELF_MAX))
    for j in range(NLAT):
        for i in range(NLON):
            blob.append(q(iron[j, i], 0.0, 1.0))

    with open(dst, "wb") as f:
        f.write(blob)

    print("%s  %d bytes (%.1f kB)" % (dst, len(blob), len(blob) / 1024.0))
    print("  grid %dx%d at %.0f deg, %d ocean cells of %d"
          % (NLON, NLAT, CELL, int(ocean.sum()), NLON * NLAT))
    for name, g in (("sst  Jan", sst[0]), ("sst  Jul", sst[6]),
                    ("mld  Jan", mld[0]), ("mld  Jul", mld[6]),
                    ("no3  DJF", no3[0]), ("no3  JJA", no3[2]),
                    ("shelf", shelf), ("iron", iron)):
        v = g[ocean]
        v = v[np.isfinite(v)]
        print("  %-9s min %8.2f  median %8.2f  max %8.2f"
              % (name, v.min(), np.median(v), v.max()))


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2])
