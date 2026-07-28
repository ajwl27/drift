#!/usr/bin/env python3
"""
BENCH  -  where the milliseconds go.

    python3 tools/bench.py              # the standard profile
    python3 tools/bench.py --profile    # plus a cProfile of the frame path

Two numbers feed tools/power.py and hence the battery estimate, and both of
them were measured once by hand and then quietly relied on for months. This
puts them under a command, so that a change which doubles the frame cost is
visible on the day it lands rather than at the point where the panel does not
last a month.

Everything here is measured on a fully populated panel unless it says
otherwise, because the peak is what sets the frame budget and the median is
what sets the battery -- so both are reported and they are not the same
number.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import drift                              # noqa: E402


def build(day, seed=7, voyage="drake"):
    from voyage import Track
    from ocean import Ocean
    track = Track(voyage)
    try:
        ocean = Ocean("data/ocean.bin")
    except (IOError, OSError):
        ocean = None
    eco = drift.Ecosystem(seed=seed, track=track, ocean=ocean)
    while eco.t < day:
        eco.step(min(1.0 / 24.0, day - eco.t))
    return eco, track


def timed(fn, n):
    """Best of three passes rather than the mean of one.

    A shared container is a noisy place to measure in, and the thing being
    estimated is how long the work takes when it is allowed to happen -- not
    how long it took while something else had the core. The minimum is the
    only summary of a timing sample that is not contaminated by that."""
    best = None
    for _ in range(3):
        t0 = time.perf_counter()
        for _ in range(n):
            fn()
        dt = (time.perf_counter() - t0) / n
        best = dt if best is None else min(best, dt)
    return best * 1000.0


def main(profile=False):
    dt = 1.0 / 20.0 / 86400.0
    rows = []
    for label, day in (("bloom  (Patagonian shelf)", 185.0),
                       ("median (Moluccas)", 760.0),
                       ("sparse (oligotrophic Pacific)", 655.0)):
        eco, track = build(day)
        n = sum(1 for a in eco.agents if a.vis > 0.03)
        canvas = drift.Canvas(drift.W, drift.H)
        sim = timed(lambda: eco.advance(dt), 600)
        ren = timed(lambda: drift.render(eco, canvas, track=track, day=eco.now),
                    200)
        rows.append((label, n, sim, ren))

    print("\n%-30s %5s %9s %9s %9s" % ("", "cells", "sim ms", "water ms",
                                       "total"))
    for label, n, sim, ren in rows:
        print("%-30s %5d %9.3f %9.2f %9.2f" % (label, n, sim, ren, sim + ren))

    eco, track = build(760.0)
    canvas = drift.Canvas(drift.W, drift.H)
    day = 760.0
    print("\nOTHER SCREENS  (at the median water above)")
    import mapview
    import keyplate
    coast = mapview.Coast("data/coast.bin")
    other = []
    for label, R in (("map  globe", mapview.R_GLOBE),
                     ("map  mid", (mapview.R_GLOBE * mapview.R_CHART) ** 0.5),
                     ("map  chart", mapview.R_CHART)):
        ms = timed(lambda R=R: mapview.render_map(canvas, coast, track, day, R),
                   60)
        other.append((label, ms))
    ms = timed(lambda: keyplate.render_key(canvas, eco, track, day, t_into=30.0),
               60)
    other.append(("key plate", ms))
    for label, ms in other:
        print("%-30s %5s %9s %9.2f" % (label, "", "", ms))

    budget = 1000.0 / drift.TARGET_FPS
    worst = max([r[2] + r[3] for r in rows] + [m for _, m in other])
    print("\nframe budget at %d fps is %.0f ms; worst measured frame is %.2f "
          "(%.0f%%)" % (drift.TARGET_FPS, budget, worst, 100 * worst / budget))
    print("CPython on this machine. The panel runs the same Python with the "
          "Canvas\nprimitives in C, which is where most of the render time "
          "is.")

    if profile:
        import cProfile
        import pstats
        eco, track = build(185.0)
        canvas = drift.Canvas(drift.W, drift.H)

        def loop():
            for _ in range(400):
                eco.advance(dt)
                drift.render(eco, canvas, track=track, day=eco.now)
        pr = cProfile.Profile()
        pr.enable()
        loop()
        pr.disable()
        print()
        pstats.Stats(pr).sort_stats("tottime").print_stats(22)


if __name__ == "__main__":
    main("--profile" in sys.argv)
