#!/usr/bin/env python3
"""
Draw the actual paths, because a table of tortuosities is not an argument you
can check by looking.

    python3 tools/plot_gaits.py trace out.json    # dump traces from this tree
    python3 tools/plot_gaits.py plot old.json new.json docs/gaits.png

The two-step shape is deliberate. The old motion model and the new one cannot
both be imported into one process, so the trace step is written to run
unchanged inside a git worktree at the previous commit -- it touches only
Ecosystem, _swim and the agent fields that both versions have -- and the plot
step reads the two dumps and puts them next to each other.

Every organism is started from the same place on the same heading and given
sixty panel-seconds. Nothing else acts on it: no growth, no grazing, no
advection, no vertical migration. What is drawn is swimming and only swimming.
"""

import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SECONDS = 60.0
FPS = 20
START_DAY = 300.0
REPS = 3               # a few individuals each, so a lucky path is obvious


def trace(dst, seed=5):
    from drift import (Ecosystem, SWIM_BL, H, Z_MAX, TOP_M, BOT_M,
                       visual_radius)
    from voyage import Track
    from ocean import Ocean
    import copy

    zpx = (H - TOP_M - BOT_M) / Z_MAX
    # No single moment of the voyage holds all seven swimmers at once -- that
    # is the ecology working -- so sweep a few seeds until each has been seen.
    first = {}
    ocean = Ocean("data/ocean.bin")
    for s in (seed, seed + 1, seed + 2, seed + 3):
        eco = Ecosystem(seed=s, start_day=0.0,
                        track=Track("drake"), ocean=ocean)
        eco.time_compression = 60.0
        while eco.t < START_DAY:
            eco.step(1.0 / 6.0)
        for a in eco.agents:
            # only fully faded-in individuals. visual_radius scales with `vis`,
            # and swimming speed scales with visual_radius, so a cell still
            # fading in swims at a fraction of its own speed -- which is right
            # on the panel and useless in a comparison, because the two trees
            # would be timing different individuals at different points in
            # their fade. This cost an hour before it was spotted.
            if a.g.kind in SWIM_BL and getattr(a, "vis", 1.0) > 0.9:
                first.setdefault(a.g.kind, a)
        if len(first) == len(SWIM_BL):
            break

    out = {}
    dt_days = (1.0 / FPS) * 60.0 / 86400.0
    for kind, proto in first.items():
        paths = []
        for rep in range(REPS):
            a = copy.deepcopy(proto)
            a.x, a.z = 0.0, 25.0
            a.head = 0.35 + rep * 0.02
            for f in ("body", "ang", "vel", "phase"):
                if hasattr(a, f):
                    setattr(a, f, {"body": a.head, "ang": a.head + math.pi,
                                   "vel": 0.0, "phase": rep * 3.0}[f])
            eco.agents = [a]
            xs, ys, x0 = [0.0], [0.0], a.x
            wind = 0.0
            for _ in range(int(SECONDS * FPS)):
                px = a.x
                eco._swim(dt_days)
                d = a.x - px
                wind += d - 240.0 * round(d / 240.0)   # the panel is a cylinder
                xs.append(wind)
                ys.append((a.z - 25.0) * zpx)
            paths.append([xs, ys])
        # the drawn body length, so the plot can report speed in body lengths
        # per second. The two trees necessarily sample different individuals --
        # changing the Agent constructor changes every subsequent random draw --
        # and pixels per second is not comparable between two cells of
        # different size. Body lengths per second is.
        out[str(kind)] = {"paths": paths, "bl_px": 2.0 * visual_radius(proto)}

    # the names live in keyplate, which both trees have
    from keyplate import NAMES
    out["_names"] = {str(k): NAMES.get(k, str(k)) for k in first}
    with open(dst, "w") as fh:
        json.dump(out, fh)
    print("%s  %d kinds" % (dst, len(first)))


def plot(old_js, new_js, dst):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    old = json.load(open(old_js))
    new = json.load(open(new_js))
    names = dict(new.get("_names", {}))
    names.update(old.get("_names", {}))
    kinds = [k for k in new if not k.startswith("_") and k in old]
    kinds.sort(key=lambda k: -max(abs(x) for x in new[k]["paths"][0][0]))

    n = len(kinds)
    fig, axes = plt.subplots(2, n, figsize=(2.05 * n, 5.4), sharey="row")
    if n == 1:
        axes = axes.reshape(2, 1)
    for col, k in enumerate(kinds):
        for row, (src, tag) in enumerate(((old, "before"), (new, "after"))):
            ax = axes[row][col]
            rec = src.get(k) or {"paths": [], "bl_px": 1.0}
            paths, bl_px = rec["paths"], max(rec["bl_px"], 1e-6)
            for xs, ys in paths:
                ax.plot(xs, ys, lw=0.8, color="#22262c" if row else "#9aa3ad")
            if paths:
                p = t = 0.0
                for xs, ys in paths:
                    p += sum(math.hypot(xs[i] - xs[i - 1], ys[i] - ys[i - 1])
                             for i in range(1, len(xs))) / len(paths)
                    t += math.hypot(xs[-1] - xs[0], ys[-1] - ys[0]) / len(paths)
                ax.text(0.03, 0.04, "%.2f BL/s   tort %.2f"
                        % (p / SECONDS / bl_px, p / max(t, 1e-9)),
                        transform=ax.transAxes, fontsize=6.5, color="#5a6470")
            ax.set_aspect("equal", adjustable="datalim")
            ax.set_xticks([])
            ax.set_yticks([])
            for s in ax.spines.values():
                s.set_color("#ccd2d8")
            if row == 0:
                ax.set_title(names.get(k, k).title(), fontsize=8, pad=4)
            if col == 0:
                ax.set_ylabel(tag, fontsize=8)
    fig.suptitle("Sixty seconds of swimming, and nothing else acting.  Three "
                 "individuals each, equal aspect, every panel to its own "
                 "scale.\nSpeed is in body lengths per second so the two rows "
                 "compare; tortuosity is path length over net travel, and 1.00 "
                 "is a straight line.", fontsize=8.5)
    fig.tight_layout(rect=(0, 0.02, 1, 0.96))
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    fig.savefig(dst, dpi=150)
    print(dst)


if __name__ == "__main__":
    if sys.argv[1] == "trace":
        trace(sys.argv[2])
    else:
        plot(sys.argv[2], sys.argv[3], sys.argv[4])
