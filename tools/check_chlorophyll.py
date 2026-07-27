#!/usr/bin/env python3
"""
The one check that can say the model is wrong.

    python3 tools/check_chlorophyll.py /tmp/chl docs/chlorophyll.png

Everything else in this project is internal: the biogeography checker asks
whether the model matches what the literature says should happen, which is
really asking whether I encoded the literature correctly. This asks something
the model cannot influence -- does it put biomass where a satellite actually
sees chlorophyll, along the same track, in the same months?

The comparison is RANK, not value. Model biomass is in arbitrary units and
chlorophyll is in mg/m3, and no amount of scaling makes those the same
quantity: a gyre dominated by picoplankton has chlorophyll without having
many drawable organisms. What the piece claims is ORDERING -- that the water
gets richer off Peru than in the mid-Pacific -- and Spearman is the statistic
for a claim about ordering. Reporting a Pearson r on these would be
implying a calibration nobody has done.

Reference data: MODIS-Aqua monthly chlorophyll (ERDDAP erdMH1chlamday),
subsampled to 2 degrees, three years averaged per month to damp ENSO. Three
years is not a climatology and this is not a validation in the sense a
biogeochemist would accept. It is a falsifiable check, which is a different
and much more useful thing to have.

Fetch the reference with:

    S=48
    for m in 01 02 ... 12; do for y in 2011 2013 2016; do
      curl -o chl_${y}${m}.csv \\
      "https://coastwatch.pfeg.noaa.gov/erddap/griddap/erdMH1chlamday.csv?\\
chlorophyll%5B(${y}-${m}-16T00:00:00Z)%5D%5B(89.97917):${S}:(-89.97917)%5D\\
%5B(-179.9792):${S}:(179.9792)%5D"
    done; done
"""

import csv
import glob
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CELL = 2.0
NLON, NLAT = 180, 90


def load_reference(d):
    """[12][NLAT][NLON] of chlorophyll, or None where the satellite never
    sees water -- cloud, ice, or land."""
    acc = [[[0.0] * NLON for _ in range(NLAT)] for _ in range(12)]
    cnt = [[[0] * NLON for _ in range(NLAT)] for _ in range(12)]
    files = sorted(glob.glob(os.path.join(d, "chl_*.csv")))
    if not files:
        raise SystemExit("no chl_*.csv in %s -- see the module docstring" % d)
    for path in files:
        m = int(os.path.basename(path)[8:10]) - 1
        with open(path) as f:
            r = csv.reader(f)
            next(r), next(r)                       # header, units
            for row in r:
                try:
                    v = float(row[3])
                except (ValueError, IndexError):
                    continue
                if not (v > 0.0):
                    continue
                la, lo = float(row[1]), float(row[2])
                j = min(NLAT - 1, max(0, int((la + 90.0) / CELL)))
                i = min(NLON - 1, max(0, int((lo + 180.0) / CELL)))
                acc[m][j][i] += math.log10(v)      # average in log space
                cnt[m][j][i] += 1
    grid = [[[None] * NLON for _ in range(NLAT)] for _ in range(12)]
    n = 0
    for m in range(12):
        for j in range(NLAT):
            for i in range(NLON):
                if cnt[m][j][i]:
                    grid[m][j][i] = 10.0 ** (acc[m][j][i] / cnt[m][j][i])
                    n += 1
    print("reference: %d files, %d cells with data of %d"
          % (len(files), n, 12 * NLAT * NLON))
    return grid


def sample(grid, lat, lon, day, rings=3):
    """Nearest cell with data, searching outward. Satellite chlorophyll has
    real holes -- persistent cloud in the ITCZ, polar night in the Southern
    Ocean winter, which is precisely where Drake spent June."""
    m = int((day % 365.25) / 365.25 * 12) % 12
    j0 = min(NLAT - 1, max(0, int((lat + 90.0) / CELL)))
    i0 = min(NLON - 1, max(0, int((lon + 180.0) / CELL)))
    for r in range(rings + 1):
        best = None
        for dj in range(-r, r + 1):
            for di in range(-r, r + 1):
                if r and max(abs(di), abs(dj)) != r:
                    continue
                j, i = j0 + dj, (i0 + di) % NLON
                if not 0 <= j < NLAT:
                    continue
                v = grid[m][j][i]
                if v is not None:
                    best = v if best is None else min(best, v)
        if best is not None:
            return best
    return None


def spearman(xs, ys):
    def rank(v):
        order = sorted(range(len(v)), key=lambda k: v[k])
        r = [0.0] * len(v)
        k = 0
        while k < len(order):
            j = k
            while j + 1 < len(order) and v[order[j + 1]] == v[order[k]]:
                j += 1
            avg = (k + j) / 2.0 + 1.0
            for t in range(k, j + 1):
                r[order[t]] = avg
            k = j + 1
        return r
    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    syy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return sxy / (sxx * syy) if sxx and syy else 0.0


def run(refdir, out_png, sweeps=None):
    from voyage import Track
    grid = load_reference(refdir)

    if sweeps is None:
        sweeps = sorted(glob.glob("/tmp/biogeo_*/voyage.csv")) or \
            ["docs/voyage_sweep.csv"]
    track = Track("drake")

    days, model, sat = [], [], []
    for path in sweeps:
        with open(path) as f:
            for row in csv.DictReader(f):
                d = float(row["day"])
                la, lo = track.position(d)
                v = sample(grid, la, lo, d)
                if v is None:
                    continue
                days.append(d)
                model.append(float(row["biomass"]))
                sat.append(v)
    if not days:
        raise SystemExit("no overlapping samples")

    rho = spearman(model, sat)
    print("%d samples from %d sweep(s)" % (len(days), len(sweeps)))
    print("Spearman rho = %+.3f" % rho)

    # Where does it disagree? Rank residual, so the answer is a place.
    def ranks(v):
        o = sorted(range(len(v)), key=lambda k: v[k])
        r = [0] * len(v)
        for p, k in enumerate(o):
            r[k] = p / float(len(v) - 1)
        return r
    rm, rs = ranks(model), ranks(sat)
    resid = [(rm[k] - rs[k], days[k]) for k in range(len(days))]
    resid.sort()
    print("\nmodel too POOR relative to satellite (worst 5):")
    for r, d in resid[:5]:
        la, lo = track.position(d)
        print("   day %4d  %6.1f %7.1f   rank gap %+.2f" % (d, la, lo, r))
    print("model too RICH relative to satellite (worst 5):")
    for r, d in resid[-5:][::-1]:
        la, lo = track.position(d)
        print("   day %4d  %6.1f %7.1f   rank gap %+.2f" % (d, la, lo, r))

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return rho
    fig, ax = plt.subplots(2, 1, figsize=(14, 7), sharex=True)
    o = sorted(range(len(days)), key=lambda k: days[k])
    ax[0].plot([days[k] for k in o], [sat[k] for k in o], lw=0.9,
               color="#1a1a1a", label="MODIS chlorophyll, mg/m3")
    ax[0].set_yscale("log")
    ax[0].set_ylabel("satellite\nchl mg/m3", fontsize=8)
    ax[0].grid(alpha=0.25, lw=0.4)
    ax[1].plot([days[k] for k in o], [model[k] for k in o], lw=0.9,
               color="#1a1a1a")
    ax[1].set_yscale("log")
    ax[1].set_ylabel("model\nbiomass", fontsize=8)
    ax[1].set_xlabel("day of voyage", fontsize=8)
    ax[1].grid(alpha=0.25, lw=0.4)
    ax[0].set_title("Model biomass against MODIS chlorophyll along Drake's "
                    "track  (Spearman rho = %+.3f)" % rho, fontsize=10)
    fig.tight_layout()
    os.makedirs(os.path.dirname(out_png) or ".", exist_ok=True)
    fig.savefig(out_png, dpi=150)
    print("\nwrote %s" % out_png)
    return rho


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else "/tmp/chl"
    o = sys.argv[2] if len(sys.argv) > 2 else "docs/chlorophyll.png"
    run(d, o)
