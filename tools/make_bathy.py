#!/usr/bin/env python3
"""
Add bottom depth to the packed ocean.

    python3 tools/make_bathy.py data/ocean.bin          # downloads what it needs
    python3 tools/make_bathy.py data/ocean.bin etopo.csv

Bathymetry is the axis fish care about most and the one field the plankton
column never needed. A sardine and a lanternfish are separated less by
temperature than by whether there is a seabed at 90 m or at 4,200 m -- and
over the shelf it is also the thing the panel DRAWS, since the bottom is
visible whenever it rises into frame.

WHY THIS IS A SEPARATE TOOL FROM make_ocean.py.

make_ocean.py rebuilds the whole file from three downloads totalling about
150 MB. None of those three has changed, and re-fetching them to add one
field would be a slow way to reproduce bytes that are already correct. So
this tool appends a field to an existing ocean.bin and bumps its version;
make_ocean.py also knows how to emit the field, so a full rebuild still
produces a complete v2 file. Either path gives the same bytes.

SOURCE. NOAA ETOPO 1 arc-minute global relief, served by ERDDAP as
`etopo180`, subsampled to 0.5 degrees at fetch time -- 4.8 MB rather than the
450 MB of the full grid, which is the entire reason this is done over the
wire rather than from a downloaded netCDF. ETOPO is US Government work and in
the public domain.

    https://coastwatch.pfeg.noaa.gov/erddap/griddap/etopo180.html

THE AVERAGE IS TAKEN OVER THE WET SAMPLES ONLY, and this is the one decision
in the file worth arguing about. A 2 degree cell on any coast is part land
and part sea, and the mean of its altitudes is a number describing neither:
off Valparaiso it would average the Andes with the Peru-Chile Trench and
report dry land in 5,000 m of water. What a ship experiences is the depth
under the keel, so only samples below sea level count, and a cell with no wet
samples at all is land.
"""

import math
import os
import struct
import sys

NLON, NLAT = 180, 90
CELL = 2.0
LAND = 255

# Log-quantised, for the same reason MLD is: depth is not remotely uniform.
# Half the ocean is between 3,000 and 5,000 m and the half of the range a fish
# actually distinguishes is 0 to 500. Linear uint8 would give 43 m per code
# everywhere -- useless on a shelf and absurdly precise in the abyss. Log
# gives 3.7% per code: about 4 m at 100 m, about 150 m at 4,000 m, which is
# the right way round.
BOT_LO, BOT_HI = 1.0, 11000.0

SUB = 0.5                    # degrees, the resolution fetched from ERDDAP
URL = ("https://coastwatch.pfeg.noaa.gov/erddap/griddap/etopo180.csv"
       "?altitude%5B(-89.75):30:(89.75)%5D%5B(-179.75):30:(179.75)%5D")


def q_log(v, lo, hi):
    if v is None or v != v:
        return LAND
    v = max(lo, min(hi, v))
    f = math.log(v / lo) / math.log(hi / lo)
    return max(0, min(254, int(round(f * 254.0))))


def dq_log(b, lo, hi):
    return None if b == LAND else lo * (hi / lo) ** (b / 254.0)


def fetch(path):
    """Pull the subsampled grid from ERDDAP if it is not already on disk."""
    if os.path.exists(path):
        return path
    try:
        from urllib.request import urlopen
    except ImportError:                       # pragma: no cover
        from urllib2 import urlopen
    sys.stderr.write("fetching ETOPO at %.2f deg from ERDDAP ...\n" % SUB)
    with urlopen(URL, timeout=600) as r, open(path, "wb") as f:
        f.write(r.read())
    return path


def cell_depths(csv_path):
    """Mean wet depth per 2 degree cell, in metres. None where all dry.

    Accumulated in one pass with two arrays rather than held as a grid of
    lists -- 259,200 rows is small, but the shape of this loop is what the
    build-time version on the MCU toolchain would use anyway."""
    tot = [0.0] * (NLON * NLAT)
    cnt = [0] * (NLON * NLAT)
    with open(csv_path) as f:
        f.readline()                          # header
        f.readline()                          # units
        for line in f:
            try:
                slat, slon, salt = line.split(",")
                alt = float(salt)
            except ValueError:
                continue                      # ERDDAP emits blanks at gaps
            if alt >= 0.0:
                continue                      # dry: contributes nothing
            lat = float(slat)
            lon = float(slon)
            j = int((lat + 90.0) / CELL)
            i = int((lon + 180.0) / CELL)
            if not (0 <= j < NLAT and 0 <= i < NLON):
                continue
            k = j * NLON + i
            tot[k] += -alt
            cnt[k] += 1
    return [(tot[k] / cnt[k]) if cnt[k] else None for k in range(len(tot))]


def read_ocean(path):
    with open(path, "rb") as f:
        b = bytearray(f.read())
    if bytes(b[:4]) != b"DRFO":
        raise SystemExit("not an ocean file: %r" % bytes(b[:4]))
    ver, nlon, nlat, nmon, nsea = struct.unpack_from("<BBBBB", bytes(b), 4)
    if (nlon, nlat) != (NLON, NLAT):
        raise SystemExit("grid is %dx%d, expected %dx%d"
                         % (nlon, nlat, NLON, NLAT))
    n = nlon * nlat
    base_v1 = 9 + (nmon + nmon) * n + nsea * n + n + n
    if ver == 1:
        if len(b) != base_v1:
            raise SystemExit("v1 file is %d bytes, expected %d"
                             % (len(b), base_v1))
    elif ver == 2:
        # idempotent: drop the existing bottom field and rebuild it, so
        # running this twice is not an error and not a 16 kB leak either
        if len(b) != base_v1 + n:
            raise SystemExit("v2 file is %d bytes, expected %d"
                             % (len(b), base_v1 + n))
        del b[base_v1:]
    else:
        raise SystemExit("ocean.bin version %d, expected 1 or 2" % ver)
    return b, n, nmon, nsea


def build(dst, csv_path):
    b, n, nmon, nsea = read_ocean(dst)
    depths = cell_depths(fetch(csv_path))

    # THE LAND MASK COMES FROM THE FILE, NOT FROM ETOPO.
    #
    # ocean.py's bilinear skips corners marked land, and it decides what is
    # land per field. If bathymetry disagreed with SST about which cells are
    # wet, a position could sample a temperature and no depth, or the other
    # way round -- and the failure would be an occasional silent None in the
    # envelope rather than anything that looks like a bug. So the SST mask
    # (which make_ocean.py already treats as authoritative) is reused
    # verbatim, and ETOPO only supplies a value where SST says there is sea.
    sst0 = 9
    filled = 0
    missing = 0
    out = bytearray()
    for k in range(n):
        if b[sst0 + k] == LAND:
            out.append(LAND)
            continue
        d = depths[k]
        if d is None:
            # SST calls it ocean and ETOPO found no wet sample in the cell.
            # Rare -- a handful of cells in narrow seas -- and 200 m is the
            # right guess for water a coarse relief grid cannot see.
            d = 200.0
            missing += 1
        out.append(q_log(d, BOT_LO, BOT_HI))
        filled += 1
    b[4:9] = struct.pack("<BBBBB", 2, NLON, NLAT, nmon, nsea)
    b += out

    with open(dst, "wb") as f:
        f.write(bytes(b))

    vals = [dq_log(v, BOT_LO, BOT_HI) for v in out if v != LAND]
    vals.sort()
    print("%s  %d bytes (%.1f kB), version 2" % (dst, len(b), len(b) / 1024.0))
    print("  bottom depth over %d ocean cells (%d filled by fallback)"
          % (filled, missing))
    print("  min %.0f m   median %.0f m   max %.0f m"
          % (vals[0], vals[len(vals) // 2], vals[-1]))
    shelf = sum(1 for v in vals if v < 200.0)
    print("  %.1f%% of ocean cells shallower than 200 m" % (100.0 * shelf / len(vals)))


if __name__ == "__main__":
    dst = sys.argv[1] if len(sys.argv) > 1 else "data/ocean.bin"
    csv = sys.argv[2] if len(sys.argv) > 2 else "etopo_half.csv"
    build(dst, csv)
