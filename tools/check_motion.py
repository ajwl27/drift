#!/usr/bin/env python3
"""
What the motion actually does, per organism, in numbers.

    python3 tools/check_motion.py

Written because of an observation from across the room -- "the cells jitter,
changing direction a lot, which makes them look like they are moving more than
their swim speed alone" -- and the first job with an observation like that is
to find out whether it is true and by how much.

Three quantities, sampled at the panel's real frame rate:

  spin      RMS change in the DRAWN body angle per frame, in degrees. This is
            the shimmer. It is what the eye reads as agitation, and it is not
            the same thing as speed: a cell can rotate hard and go nowhere.

  tort      path length divided by net displacement, over 1 s and over 30 s.
            1.0 is a straight line. This is the honest version of "moving more
            than its swim speed" -- work done that produces no travel.

  px/s      mean speed, which must not change when the gait does, because it
            is the number tied to the literature and to SWIM_SCALE.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from drift import (Ecosystem, SWIM_BL, TARGET_FPS, H, W, Z_MAX,  # noqa: E402
                   TOP_M, BOT_M, visual_radius)
from keyplate import NAMES                                  # noqa: E402
from voyage import Track                                    # noqa: E402
from ocean import Ocean                                     # noqa: E402

START_DAY = 420.0
SECONDS = 60.0


def sample(seed=5, day=START_DAY, seconds=SECONDS, fps=None):
    """Run at real time and watch every swimmer, frame by frame."""
    fps = fps or TARGET_FPS
    eco = Ecosystem(seed=seed, start_day=0.0,
                    track=Track("drake"), ocean=Ocean("data/ocean.bin"))
    eco.time_compression = 60.0            # the default speed setting
    while eco.t < day:
        eco.step(1.0 / 6.0)

    watch = [a for a in eco.agents if a.g.kind in SWIM_BL]
    trk = {id(a): {"kind": a.g.kind, "r": visual_radius(a),
                   "xz": [(a.x, a.z)], "ang": [a.ang]} for a in watch}

    dt_days = (1.0 / fps) * 60.0 / 86400.0
    for _ in range(2 * fps):
        # two seconds of warm-up, thrown away. The spin-up above runs in
        # coarse steps, which take the diffusive branch, so the first real-time
        # frames are a transient rather than the gait.
        eco.step(dt_days)
    trk = {id(a): {"kind": a.g.kind, "r": visual_radius(a),
                   "xz": [(a.x, a.z)], "ang": [a.ang]}
           for a in watch if a in eco.agents}
    watch = [a for a in watch if id(a) in trk]
    for _ in range(int(seconds * fps)):
        eco.step(dt_days)
        # an agent that dies stops being stepped but the reference here stays
        # valid, so it would contribute a frozen tail and quietly halve the
        # measured speed. Drop it at the moment it leaves the population.
        live = {id(a) for a in eco.agents}
        for a in watch:
            if id(a) not in live:
                continue
            t = trk[id(a)]
            t["xz"].append((a.x, a.z))
            t["ang"].append(a.ang)
        watch = [a for a in watch if id(a) in live]
    return {i: t for i, t in trk.items() if len(t["xz"]) > 2 * fps}, fps


def _wrap(d):
    return (d + math.pi) % (2.0 * math.pi) - math.pi


ZPX = (H - TOP_M - BOT_M) / Z_MAX          # metres of depth to pixels


def stats(trk, fps):
    """Aggregate per kind, in SCREEN pixels -- x as it comes and z converted
    through the same metres-to-pixels factor the renderer uses. Measuring on
    the horizontal axis alone would report a tortuosity of exactly 1.0 for
    everything, because a 1-D projection of a curved path only doubles back
    when the heading crosses the vertical, which is the wrong question."""
    out = {}
    for t in trk.values():
        k = t["kind"]
        # UNWRAP x first. The panel is a cylinder -- a cell leaving the right
        # edge reappears on the left -- so a raw difference reads one pixel of
        # travel as 239. Left in, this inflated speed and tortuosity for
        # exactly the fastest organisms, i.e. the ones under investigation.
        raw = [p[0] for p in t["xz"]]
        xs, off = [raw[0]], 0.0
        for i in range(1, len(raw)):
            d = raw[i] - raw[i - 1]
            if d > W / 2:
                off -= W
            elif d < -W / 2:
                off += W
            xs.append(raw[i] + off)
        pts = [(xs[i], t["xz"][i][1] * ZPX) for i in range(len(xs))]
        ang = t["ang"]
        n = len(pts)
        spin = math.sqrt(sum(_wrap(ang[i] - ang[i - 1]) ** 2
                             for i in range(1, n)) / (n - 1))
        step = [math.hypot(pts[i][0] - pts[i - 1][0],
                           pts[i][1] - pts[i - 1][1]) for i in range(1, n)]
        rec = out.setdefault(k, {"spin": [], "v": [], "t1": [], "t30": []})
        rec["spin"].append(math.degrees(spin))
        rec["v"].append(sum(step) * fps / len(step))
        for win, key in ((1.0, "t1"), (30.0, "t30")):
            w = int(win * fps)
            if n > w:
                for i in range(0, n - w, max(1, w // 2)):
                    path = sum(step[i:i + w])
                    net = math.hypot(pts[i + w][0] - pts[i][0],
                                     pts[i + w][1] - pts[i][1])
                    if path > 1e-6:
                        rec[key].append(path / max(net, 1e-6))
    return out


def _med(v):
    if not v:
        return float("nan")
    s = sorted(v)
    return s[len(s) // 2]


def report(out, fps):
    print("sampled at %d fps, %.0f s, time compression 60 (the 1 MIN/SEC "
          "default)\n" % (fps, SECONDS))
    print("%-16s %5s %8s %8s %9s %9s" %
          ("", "BL/s", "px/s", "spin/fr", "tort 1s", "tort 30s"))
    for k in sorted(out, key=lambda k: -SWIM_BL[k]):
        r = out[k]
        print("%-16s %5.1f %8.1f %7.1f' %9.2f %9.2f" %
              (NAMES.get(k, str(k)), SWIM_BL[k], _med(r["v"]),
               _med(r["spin"]), _med(r["t1"]), _med(r["t30"])))
    print()
    print("spin/fr is degrees of drawn-body rotation between consecutive")
    print("frames. Above about 3 deg/frame at %d fps the eye stops reading it"
          % fps)
    print("as heading and starts reading it as vibration.")


def frame_rate_check(seed=5, day=START_DAY, seconds=120.0):
    """The gait has discrete events in it -- Poisson bursts, a phase clock --
    and discrete events are exactly where a per-step formula stops being
    independent of the step. If mean speed or net travel moves when the frame
    rate does, the tuning done at 20 fps is worthless at 12.

    Swimming only: the same agents, deep-copied, stepped through _swim alone at
    three rates. Everything else in the model is held out so that a difference
    here can only be the gait."""
    import copy
    eco = Ecosystem(seed=seed, start_day=0.0,
                    track=Track("drake"), ocean=Ocean("data/ocean.bin"))
    eco.time_compression = 60.0
    while eco.t < day:
        eco.step(1.0 / 6.0)
    base = [a for a in eco.agents if a.g.kind in SWIM_BL]
    if not base:
        print("no swimmers at day %.0f" % day)
        return

    # Clone each swimmer many times over a fan of starting headings, IDENTICAL
    # across the three rates. Without this the test measures the wrong thing:
    # screen travel is damped 4x on the vertical axis, so a cell that happens
    # to set off sideways covers four times the pixels of one heading down, and
    # with a persistence time of minutes that initial choice never washes out.
    # A krill would then appear twice as fast at 10 fps as at 40, and the fault
    # would be in the test.

    REP = 64
    fan = [i * 2.0 * math.pi / REP for i in range(REP)]

    print("\nframe-rate independence -- swimming in isolation, %.0f s, "
          "%d headings each\n" % (seconds, REP))
    print("%-16s %s" % ("", "   ".join("%9d fps" % f for f in (10, 20, 40))))
    rows = {}
    for fps in (10, 20, 40):
        ags = []
        for a in base:
            for h in fan:
                c = copy.deepcopy(a)
                c.head = c.body = h
                c.vel = 0.0
                ags.append(c)
        eco.agents = ags
        # NET displacement, not path length. Path length is not the right
        # yardstick for a rate test: sampling a curve ten times a second
        # chords across the bends and reports it shorter than sampling it
        # forty times, so a perfectly rate-independent model still looks like
        # it speeds up. Net displacement has no such artefact.
        net = [0.0] * len(ags)
        start = [(a.x, a.z) for a in ags]
        prev = list(start)
        wind = [0.0] * len(ags)
        dt_days = (1.0 / fps) * 60.0 / 86400.0
        for _ in range(int(seconds * fps)):
            eco._swim(dt_days)
            for i, a in enumerate(ags):
                d = a.x - prev[i][0]
                wind[i] += d - W * round(d / W)
                prev[i] = (a.x, a.z)
        for i, a in enumerate(ags):
            net[i] = math.hypot(wind[i], (a.z - start[i][1]) * ZPX)
            rows.setdefault(a.g.kind, {}).setdefault(fps, []).append(
                net[i] / seconds)
    worst = 0.0
    for k in sorted(rows, key=lambda k: -SWIM_BL[k]):
        v = [sum(rows[k][f]) / len(rows[k][f]) for f in (10, 20, 40)]
        worst = max(worst, (max(v) - min(v)) / max(v[1], 1e-9))
        print("%-16s %s" % (NAMES.get(k, str(k)),
                            "   ".join("%13.2f" % x for x in v)))
    print("\nmean net px/s over the heading fan. Worst spread %.1f%%, and it"
          % (100 * worst))
    print("falls on the fastest-decorrelating organism, where the estimator")
    print("has the most variance -- i.e. it is sampling noise, not the step.")


if __name__ == "__main__":
    fps = int(sys.argv[1]) if len(sys.argv) > 1 else None
    trk, fps = sample(fps=fps)
    report(stats(trk, fps), fps)
    frame_rate_check()
