#!/usr/bin/env python3
"""
Stage 4's definition of done.

    python3 tools/check_biogeography.py run 4      # sweep 4 seeds and check
    python3 tools/check_biogeography.py a.csv b.csv # check existing sweeps

The plan says the trait model works if the composition matches known
biogeography without anything in the model having been told where anything
lives. This is that check, written as assertions rather than as a paragraph,
because "looks about right" is how you end up shipping a model with one
winner.

It runs over SEVERAL SEEDS and judges the median, which matters more than it
sounds. On a single seed every threshold is really a question about that
seed's weather: the first four runs gave effective-type counts of 2.45, 2.83,
3.20 and 3.66, and a threshold set anywhere in that range would have passed
or failed on luck. Thresholds here are set to catch a REGRESSION -- a model
where diatoms stop owning the Humboldt entirely, or where one type takes
everything again -- not to be barely cleared by the best run.

Two things are measured. First, the effective number of types -- the inverse
Simpson index on voyage biomass share, which answers "how many types is this
community actually made of" and is immune to the trap that a long tail of
one-percent types looks like diversity. Second, the regional predictions from
the plan's checklist, each of which has a mechanism behind it.
"""

import csv
import sys

DRIFTERS = ("centric", "pennate", "chain", "radiolarian", "ceratium")
DIATOMS = ("centric", "pennate", "chain")
MIXOTROPHS = ("radiolarian", "ceratium")


def hill2(shares):
    """Inverse Simpson: 1 / sum(p^2). Five types split evenly gives 5.0; one
    type taking everything gives 1.0."""
    tot = sum(shares) or 1.0
    p = [s / tot for s in shares]
    return 1.0 / sum(x * x for x in p)


def load(path):
    return list(csv.DictReader(open(path)))


def window(rows, lo, hi):
    return [r for r in rows if lo <= int(r["day"]) <= hi]


def group_share(rows, group):
    num = sum(sum(float(r[k]) for k in group) for r in rows)
    den = sum(sum(float(r[k]) for k in DRIFTERS) for r in rows)
    return num / den if den > 0 else 0.0


TESTS = [
    # (name, day window, group, comparison, threshold, why)
    ("cool productive coast favours diatoms", (330, 600), DIATOMS, ">", 0.55,
     "high nutrients and cool water: high mu_max wins the transient"),
    ("oligotrophic gyres favour mixotrophs", (600, 680), MIXOTROPHS, ">", 0.35,
     "nutrients near zero: only the types that also eat can persist"),
    ("Southern Ocean is not a diatom bloom", (180, 270), DIATOMS, "<", 0.80,
     "nitrate is abundant but iron and light are not -- HNLC"),
    ("Indian Ocean gyre favours mixotrophs", (840, 900), MIXOTROPHS, ">", 0.30,
     "warm, stratified, nutrient-starved"),
]
MIN_EFFECTIVE_TYPES = 2.30
MIN_DOMINANTS = 4


def median(v):
    w = sorted(v)
    n = len(w)
    return w[n // 2] if n % 2 else 0.5 * (w[n // 2 - 1] + w[n // 2])


def measure(rows):
    total = {k: sum(float(r[k]) for r in rows) for k in DRIFTERS}
    doms = []
    for r in rows:
        v = {k: float(r[k]) for k in DRIFTERS}
        if sum(v.values()) > 0.5:
            doms.append(max(v, key=v.get))
    return {
        "share": total,
        "hill": hill2(list(total.values())),
        "dominants": len(set(doms)),
        "turnover": sum(1 for a, b in zip(doms, doms[1:]) if a != b),
        "tests": [group_share(window(rows, lo, hi), g)
                  for _, (lo, hi), g, _, _, _ in TESTS],
    }


def check(paths):
    runs = [measure(load(p)) for p in paths]
    n = len(runs)

    print("VOYAGE BIOMASS SHARE  (median over %d seed%s)" % (n, "" if n == 1 else "s"))
    med = {k: median([100 * r["share"][k] / sum(r["share"].values()) for r in runs])
           for k in DRIFTERS}
    for k in sorted(med, key=lambda k: -med[k]):
        print("  %-12s %5.1f%%" % (k, med[k]))

    def line(label, vals, op, thr, fmt="%5.1f%%", scale=100.0):
        lo, mu, hi = min(vals), median(vals), max(vals)
        ok = (mu > thr) if op == ">" else (mu < thr)
        print("  [%s] %-38s %s %s %s   (range %s - %s)" %
              ("PASS" if ok else "FAIL", label,
               fmt % (mu * scale), op, fmt % (thr * scale),
               fmt % (lo * scale), fmt % (hi * scale)))
        return 0 if ok else 1

    print("\nREGIONAL PREDICTIONS")
    failed = 0
    for i, (name, _, _, op, thr, why) in enumerate(TESTS):
        failed += line(name, [r["tests"][i] for r in runs], op, thr)
        print("         %s" % why)

    print("\nDIVERSITY")
    failed += line("effective types (of %d)" % len(DRIFTERS),
                   [r["hill"] for r in runs], ">", MIN_EFFECTIVE_TYPES,
                   fmt="%5.2f ", scale=1.0)
    failed += line("distinct dominants", [float(r["dominants"]) for r in runs],
                   ">", MIN_DOMINANTS - 0.5, fmt="%5.1f ", scale=1.0)
    print("         turnover: %d changes of dominant per 34 panels (median)"
          % median([r["turnover"] for r in runs]))

    print("\n%s" % ("ALL CHECKS PASS" if failed == 0
                    else "%d CHECK(S) FAILED" % failed))
    return failed


if __name__ == "__main__":
    args = sys.argv[1:] or ["docs/voyage_sweep.csv"]
    if args[0] == "run":
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import drift
        nseeds = int(args[1]) if len(args) > 1 else 4
        args = []
        for sd in (7, 11, 23, 41, 99, 137)[:nseeds]:
            out = "/tmp/biogeo_%d" % sd
            print("sweeping seed %d ..." % sd)
            drift.voyage_sweep(out, seed=sd)
            args.append(out + "/voyage.csv")
        print()
    sys.exit(1 if check(args) else 0)
