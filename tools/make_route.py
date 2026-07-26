#!/usr/bin/env python3
"""
Stop the boat sailing over land.

    python3 tools/make_route.py drake --check      # just report
    python3 tools/make_route.py drake              # report and emit a fix

A great circle between two waypoints is the shortest path over a sphere, and
a sphere has no continents on it. Drake's track has the ship crossing the
Andes, the Isthmus of Panama and most of Sulawesi; the Beagle's crosses
Patagonia. It is the one thing on the map that reads instantly as wrong,
because everyone knows boats do not do that.

The fix runs HERE, at build time, and produces extra waypoints. The panel
gains nothing to execute -- Track is unchanged, and the cost is a few hundred
bytes of table. Which matters most for the voyages that do not exist yet: a
new one should be a waypoint list and nothing else, and nobody should have to
sit with an atlas checking sixty legs by eye.

Two decisions worth stating.

SHORT CROSSINGS ARE ALLOWED. Primera Angostura in the Strait of Magellan is
three kilometres wide; at any raster resolution worth carrying it is solid
land, and a router forbidden to cross it would send Drake round Cape Horn
instead -- which is both wrong and ironic. So the test is not "does this leg
touch land" but "does it cross more than TOLERANCE_KM of it". That permits
genuine strait transits and catches continents, which is exactly the
distinction a person would draw.

THE ROUTE IS COASTAL, NOT OPTIMAL. A* on a plain sea grid hugs the shore,
because the shortest way round a headland is to scrape it. Real ships stand
off. So sea cells near land carry a cost penalty, and the resulting track
rounds capes at a plausible distance rather than clipping them.
"""

import heapq
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from make_landmask import LandMask                     # noqa: E402
from voyage import Track, VOYAGES, haversine, slerp, _to_vec, _to_ll  # noqa: E402

TOLERANCE_KM = 25.0        # land a leg may cross before it counts as broken
SAMPLE_KM = 8.0            # how finely a leg is walked when testing
COAST_PENALTY = 2.2        # extra cost for a sea cell adjacent to land
COAST_RINGS = 3            # how far that penalty reaches
STRAIT_KM = 350.0          # a leg shorter than this with no route round it is
                           # a strait transit, not a broken track


# --------------------------------------------------------------------------
# detection
# --------------------------------------------------------------------------

def walk(a, b, step_km=SAMPLE_KM):
    """Great-circle samples between two (lat, lon), roughly step_km apart."""
    d = haversine(a[0], a[1], b[0], b[1])
    n = max(2, int(d / step_km) + 1)
    va, vb = _to_vec(*a), _to_vec(*b)
    return [_to_ll(slerp(va, vb, i / float(n))) for i in range(n + 1)], d


def land_runs(mask, a, b):
    """[(km_into_leg, km_long)] for each unbroken stretch of land the great
    circle between a and b passes over, ignoring the endpoints themselves --
    an anchorage is supposed to be on the coast."""
    pts, d = walk(a, b)
    if len(pts) < 3:
        return [], d
    step = d / (len(pts) - 1)
    runs = []
    start = None
    for i, p in enumerate(pts):
        on = mask.at(p[0], p[1]) if 0 < i < len(pts) - 1 else False
        if on and start is None:
            start = i
        elif not on and start is not None:
            runs.append((start * step, (i - start) * step))
            start = None
    if start is not None:
        runs.append((start * step, (len(pts) - 1 - start) * step))
    return runs, d


def audit(voyage, mask, tol=TOLERANCE_KM):
    wp = voyage.waypoints
    bad = []
    for i in range(len(wp) - 1):
        a, b = (wp[i][1], wp[i][2]), (wp[i + 1][1], wp[i + 1][2])
        if a == b:
            continue
        runs, d = land_runs(mask, a, b)
        worst = max((r[1] for r in runs), default=0.0)
        total = sum(r[1] for r in runs)
        if worst > tol:
            bad.append((i, wp[i][4], wp[i + 1][4], d, worst, total))
    return bad


# --------------------------------------------------------------------------
# routing
# --------------------------------------------------------------------------

def _cost_field(mask):
    """Distance-to-land in cells, capped, as a per-cell multiplier. Computed
    lazily per query region rather than globally, because a global transform
    on a 3600x1800 grid in pure Python is not worth it for sixty legs."""
    cache = {}

    def near_land(i, j):
        key = (i % mask.nlon, j)
        v = cache.get(key)
        if v is None:
            v = 0
            for r in range(1, COAST_RINGS + 1):
                hit = False
                for dj in (-r, r):
                    for di in range(-r, r + 1):
                        if mask.at_ij(i + di, j + dj):
                            hit = True
                            break
                    if hit:
                        break
                if not hit:
                    for di in (-r, r):
                        for dj in range(-r + 1, r):
                            if mask.at_ij(i + di, j + dj):
                                hit = True
                                break
                        if hit:
                            break
                if hit:
                    v = COAST_RINGS - r + 1
                    break
            cache[key] = v
        return v

    return near_land


def _open(mask, i, j, need=14):
    """Crude 'is this open water rather than a puddle': count sea cells in the
    5x5 around it. An anchorage at the head of an estuary snaps to the nearest
    sea cell, and at 0.1 degrees that cell can be a one-cell pocket the
    rasteriser left behind, with no way out -- which is exactly why Montevideo
    to Bahia Blanca came back unroutable on a coast with open ocean beside
    it."""
    n = 0
    for dj in range(-2, 3):
        for di in range(-2, 3):
            if not mask.at_ij(i + di, j + dj):
                n += 1
    return n >= need


def _nearest_sea(mask, i, j, limit=60, need=14):
    if not mask.at_ij(i, j) and _open(mask, i, j, need):
        return i, j
    fallback = None
    for r in range(1, limit):
        for dj in range(-r, r + 1):
            for di in range(-r, r + 1):
                if max(abs(di), abs(dj)) != r:
                    continue
                if not 0 <= j + dj < mask.nlat:
                    continue
                if mask.at_ij(i + di, j + dj):
                    continue
                if _open(mask, i + di, j + dj, need):
                    return i + di, j + dj
                if fallback is None:
                    fallback = (i + di, j + dj)
    return fallback or (i, j)


def route(mask, a, b, margin_deg=14.0):
    """A* from a to b over sea cells, inside a bounding box around the leg.

    The box is the leg plus a margin, which keeps the search small and is
    also the only thing stopping a blocked leg from exploring the entire
    Pacific before giving up."""
    near = _cost_field(mask)
    cell = mask.cell
    ia, ja = _nearest_sea(mask, *mask.ij(*a))
    ib, jb = _nearest_sea(mask, *mask.ij(*b))

    jlo = max(0, int(min(ja, jb) - margin_deg / cell))
    jhi = min(mask.nlat - 1, int(max(ja, jb) + margin_deg / cell))
    # longitude window, handled on the wrapped axis
    di = (ib - ia) % mask.nlon
    if di > mask.nlon // 2:
        di -= mask.nlon
    pad = int(margin_deg / cell)
    span = abs(di) + 2 * pad
    # The window has to start at the WESTERN end of the leg, not at the start
    # point. Anchoring it at `ia` and running east put the goal outside the
    # box on every westbound leg -- which is why Guatulco to Cape Arago,
    # a route with the entire Pacific available to it, came back unroutable.
    base = (ia + min(0, di) - pad) % mask.nlon

    def in_box(i, j):
        if not jlo <= j <= jhi:
            return False
        return (i - base) % mask.nlon <= span

    def h(i, j):
        la, lo = mask.ll(i, j)
        lb, lob = mask.ll(ib, jb)
        return haversine(la, lo, lb, lob)

    start = (ia, ja)
    goal = (ib, jb)
    gs = {start: 0.0}
    prev = {}
    pq = [(h(*start), start)]
    seen = set()
    km_per_cell = 111.32 * cell
    while pq:
        _, cur = heapq.heappop(pq)
        if cur in seen:
            continue
        seen.add(cur)
        if cur == goal:
            break
        ci, cj = cur
        clat = -90.0 + (cj + 0.5) * cell
        ew = km_per_cell * max(0.05, math.cos(math.radians(clat)))
        for dii, djj in ((1, 0), (-1, 0), (0, 1), (0, -1),
                         (1, 1), (1, -1), (-1, 1), (-1, -1)):
            ni, nj = ci + dii, cj + djj
            if not in_box(ni, nj) or mask.at_ij(ni, nj):
                continue
            ni %= mask.nlon
            step = math.hypot(dii * ew, djj * km_per_cell)
            step *= 1.0 + COAST_PENALTY * near(ni, nj) / COAST_RINGS
            g = gs[cur] + step
            if g < gs.get((ni, nj), 1e18):
                gs[(ni, nj)] = g
                prev[(ni, nj)] = cur
                heapq.heappush(pq, (g + h(ni, nj), (ni, nj)))
    if goal not in prev and goal != start:
        return None
    path = [goal]
    while path[-1] != start:
        path.append(prev[path[-1]])
    path.reverse()
    return [mask.ll(i, j) for i, j in path]


def simplify(pts, tol_km=45.0):
    """Douglas-Peucker on the routed path, so a leg gains three or four
    waypoints rather than four hundred."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        best, bi = -1.0, -1
        for k in range(i + 1, j):
            # perpendicular distance approximated as the excess path length,
            # which is well behaved near the poles where lat/lon is not
            d = (haversine(*pts[i], *pts[k]) + haversine(*pts[k], *pts[j])
                 - haversine(*pts[i], *pts[j]))
            if d > best:
                best, bi = d, k
        if best > tol_km:
            keep[bi] = True
            stack.append((i, bi))
            stack.append((bi, j))
    return [p for p, k in zip(pts, keep) if k]


def _safe_simplify(mask, path, tol, pa, pb):
    """Simplify, then put back whatever the simplification broke.

    Two things learned here. Douglas-Peucker on a route that hugs a coast will
    happily cut the corner it was routed round, so the first pass came back
    with MORE bad legs than it started with -- every detour it inserted was
    itself a straight line across the headland the detour existed to avoid.

    And the re-test has to run on the chain that will actually be SAILED,
    which starts and ends at the true waypoints, not at the sea cells the
    router snapped them to. Testing the snapped path left every final approach
    unchecked, which is why seventeen short legs into anchorages still crossed
    a headland after the first fix -- the interesting part of a coastal leg is
    precisely the bit between the last open water and the anchorage."""
    idx = [i for i, p in enumerate(path) if p in set(simplify(path, 45.0))]
    if idx[0] != 0:
        idx.insert(0, 0)
    if idx[-1] != len(path) - 1:
        idx.append(len(path) - 1)
    for _ in range(14):
        chain = [pa] + [path[i] for i in idx[1:-1]] + [pb]
        added = False
        for k in range(len(chain) - 1):
            runs, _ = land_runs(mask, chain[k], chain[k + 1])
            if max((r[1] for r in runs), default=0.0) <= tol:
                continue
            a, b = idx[k], idx[k + 1]
            if b <= a + 1:
                continue
            idx.insert(k + 1, (a + b) // 2)
            added = True
            break
        if not added:
            break
    return [path[i] for i in idx[1:-1]]


def beach(wp, mask, verbose=True):
    """Move any waypoint the mask thinks is on land into the nearest open
    water, keeping its label.

    The last eight failures were all the same thing and none of them was a
    routing bug: the ANCHORAGE is inland at 0.1 degrees. Hobart is up the
    Derwent, Bahia Blanca is at the head of an estuary, the Chonos anchorage
    is inside a fjord maze -- so the final hop from open water to the
    waypoint crossed land no matter how well the rest of the leg was routed.

    Nudging is more accurate rather than less. A recorded position is a town
    or a bay on a chart, not a set of coordinates a ship floated at, and the
    displacements here are single-figure kilometres against historical
    positions good to tens. Every move is reported, so it stays a decision."""
    out = []
    moved = []
    for w in wp:
        if not mask.at(w[1], w[2]):
            out.append(w)
            continue
        # A gentler openness test than the router uses. At need=14 the nudge
        # took Hobart 55 km out of the Derwent and the Chonos anchorage 143 km
        # into the Pacific -- technically water, and no longer the place. Six
        # of twenty-five is enough to reject a one-cell rasterising artefact
        # while keeping an estuary an estuary.
        i, j = _nearest_sea(mask, *mask.ij(w[1], w[2]), need=6)
        la, lo = mask.ll(i, j)
        d = haversine(w[1], w[2], la, lo)
        out.append((w[0], round(la, 2), round(lo, 2)) + tuple(w[3:]))
        if w[4]:
            moved.append((w[4], d))
    if verbose and moved:
        moved.sort(key=lambda m: -m[1])
        ds = sorted(m[1] for m in moved)
        print("  %d waypoints nudged into water: median %.0f km, worst %.0f km"
              % (len(moved), ds[len(ds) // 2], ds[-1]))
        for name, d in moved[:4]:
            print("      %-24s %4.0f km" % (name, d))
    return tuple(out)


def repair(voyage, mask, tol=TOLERANCE_KM, verbose=True):
    """Return a new waypoint tuple with detours inserted."""
    wp = list(beach(voyage.waypoints, mask, verbose))
    out = [wp[0]]
    fixed = failed = straits = 0
    for i in range(len(wp) - 1):
        a, b = wp[i], wp[i + 1]
        pa, pb = (a[1], a[2]), (b[1], b[2])
        if pa == pb:
            out.append(b)
            continue
        runs, _ = land_runs(mask, pa, pb)
        if max((r[1] for r in runs), default=0.0) <= tol:
            out.append(b)
            continue
        path = None
        for margin in (14.0, 30.0, 60.0):
            path = route(mask, pa, pb, margin_deg=margin)
            if path and len(path) >= 3:
                break
        if not path or len(path) < 3:
            # A SHORT leg with no way round it is a strait, not a mistake.
            # Primera Angostura is three kilometres wide and reads as solid
            # land at 0.1 degrees; refusing to cross it would send Drake round
            # Cape Horn instead of through the passage he is famous for
            # finding. So short unroutable legs are accepted as transits and
            # long ones are reported as genuine failures.
            d_leg = haversine(pa[0], pa[1], pb[0], pb[1])
            if verbose:
                print("  %s %-22s -> %-22s  %s"
                      % ("~" if d_leg < STRAIT_KM else "!", a[4], b[4],
                         "narrow passage, accepted" if d_leg < STRAIT_KM
                         else "NO SEA ROUTE"))
            if d_leg < STRAIT_KM:
                straits += 1
            else:
                failed += 1
            out.append(b)
            continue
        mid = _safe_simplify(mask, path, tol, pa, pb)
        if not mid:
            out.append(b)
            continue
        # spread the days along the detour by distance, so speed stays even
        chain = [pa] + mid + [pb]
        seg = [haversine(*chain[k], *chain[k + 1]) for k in range(len(chain) - 1)]
        tot = sum(seg) or 1.0
        span = b[0] - a[0]
        acc = 0.0
        for k, p in enumerate(mid):
            acc += seg[k]
            day = a[0] + span * acc / tot
            out.append((int(round(day)), round(p[0], 2), round(p[1], 2), 0, ""))
        out.append(b)
        fixed += 1
        if verbose:
            extra = sum(seg) - haversine(*pa, *pb)
            print("  + %-22s -> %-22s  %d points, %+.0f km"
                  % (a[4], b[4], len(mid), extra))
    # days must stay non-decreasing after rounding
    clean = [out[0]]
    for w in out[1:]:
        d = max(w[0], clean[-1][0])
        clean.append((d,) + tuple(w[1:]))
    if verbose:
        print("  %d rerouted, %d narrow passages accepted, %d unroutable, "
              "%d -> %d waypoints" % (fixed, straits, failed, len(wp),
                                      len(clean)))
    return tuple(clean)


def emit(name, wps):
    """Print the table as Python, ready to paste into voyage.py."""
    print("\n%s = (" % name)
    for d, la, lo, c, lab in wps:
        print("    (%4d, %7.2f, %8.2f, %d, %r)," % (d, la, lo, c, lab))
    print(")")


if __name__ == "__main__":
    key = sys.argv[1] if len(sys.argv) > 1 else "drake"
    mask = LandMask("data/land.bin")
    v = VOYAGES[key]
    bad = audit(v, mask)
    print("%s: %d of %d legs cross more than %.0f km of land"
          % (key, len(bad), len(v.waypoints) - 1, TOLERANCE_KM))
    for i, fa, fb, d, worst, total in bad:
        print("  %-22s -> %-22s  leg %5.0f km, worst run %5.0f km, total %5.0f"
              % (fa, fb, d, worst, total))
    if "--check" not in sys.argv:
        print()
        wps = repair(v, mask)
        left = audit(type(v)(v.key, v.title, v.subtitle, v.departure, wps), mask)
        print("  after: %d bad legs" % len(left))
        if "--emit" in sys.argv:
            emit(key.upper() + "_WAYPOINTS", wps)
