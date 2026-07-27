#!/usr/bin/env python3
"""
The definition of done for the envelope model.

    python3 tools/check_biogeography.py run          # sweep and check
    python3 tools/check_biogeography.py run 5        # five seeds, judge median
    python3 tools/check_biogeography.py run --obis   # ...and check against OBIS
    python3 tools/check_biogeography.py calibrate    # report A_MAX / A_SCALE

The claim the model makes is that composition matches known biogeography
WITHOUT anything having been told where anything lives. This is that claim
written as assertions rather than as a paragraph, because "looks about right"
is how you end up shipping a model in which one species takes the whole ocean.

Each assertion has a MECHANISM behind it, stated in its own docstring. A test
that passes for the wrong reason is worse than no test, and the way to tell
the difference is to write down what is supposed to cause the result.

Thresholds are set to catch a REGRESSION -- anchoveta vanishing from the
Humboldt, or the gyre becoming as rich as an upwelling -- rather than to be
barely cleared by the best run. Judged over several seeds, because on a
single seed every threshold is really a question about that seed's luck.

OBIS IS A CHECK AND NOT A SOURCE, and the distinction matters enough to
repeat here. Occurrence records record where people have looked: they are
dense off Europe and North America and near-empty across the South Pacific,
so a model fitted to them would inherit two centuries of survey effort as if
it were biogeography. What OBIS can honestly answer is the reverse question
-- "we predict this species here; has anyone ever actually recorded it in
this region?" -- and a NO to that is a real finding.
"""

import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import drift
import fish as F
from ocean import Ocean
from voyage import Track

STEP = 2.0           # days between samples


# --------------------------------------------------------------------------
# regions, by where they are rather than by day number
# --------------------------------------------------------------------------
#
# Boxes, not day ranges. A day range is a fact about one voyage and would
# have to be rewritten for the Beagle; a box is a fact about the ocean, and
# both voyages sail through the same water.
#
# (name, lat_lo, lat_hi, lon_lo, lon_hi)
REGIONS = (
    ("NE_ATLANTIC",   35.0,  60.0, -20.0,   5.0),
    ("TROP_ATLANTIC", -20.0, 15.0, -45.0, -10.0),
    ("PATAGONIA",    -55.0, -38.0, -70.0, -50.0),
    ("SOUTHERN",     -60.0, -50.0, -80.0, -60.0),
    ("HUMBOLDT",     -40.0,  -5.0, -85.0, -70.0),
    ("PACIFIC_GYRE", -30.0,  30.0, -180.0, -120.0),
    ("MOLUCCAS",     -10.0,  10.0, 115.0, 140.0),
    ("BENGUELA",     -38.0, -18.0,   5.0,  25.0),
)


def region_of(lat, lon):
    for name, la0, la1, lo0, lo1 in REGIONS:
        if la0 <= lat <= la1 and lo0 <= lon <= lo1:
            return name
    return None


def sweep(seed, voyage="drake", step=STEP):
    """Run the whole voyage headless and return per-region abundance.

    {region: {species_key: [abundance, ...]}}, plus a per-region list of
    (n_species, total_abundance, prod) samples."""
    track = Track(voyage)
    ocean = Ocean("data/ocean.bin")
    eco = drift.Ecosystem(seed=seed, start_day=0.0, track=track, ocean=ocean)
    total = track.days[-1]
    by_region = {}
    stats = {}
    while eco.t < total:
        eco.step(step)
        la, lo = track.position(eco.t)
        reg = region_of(la, lo)
        if reg is None:
            continue
        rows = eco.census()
        d = by_region.setdefault(reg, {})
        tot = 0.0
        for key, n, suit, ab in rows:
            d.setdefault(key, []).append(ab)
            tot += ab
        epi = sum(ab for key, _, _, ab in rows if key not in F.MESOPELAGIC)
        stats.setdefault(reg, []).append((len(rows), tot, eco.prod, epi))
    return by_region, stats


def share(by_region, reg):
    """Fraction of the region's total abundance held by each species."""
    d = by_region.get(reg, {})
    tot = sum(sum(v) for v in d.values())
    if tot <= 0.0:
        return {}
    return {k: sum(v) / tot for k, v in d.items()}


def effective_species(sh):
    """Inverse Simpson on abundance share: 'how many species is this
    community actually made of'.

    Immune to the trap that a long tail of one-percent species looks like
    diversity, which a raw count is not."""
    s = sum(v * v for v in sh.values())
    return (1.0 / s) if s > 0 else 0.0


# --------------------------------------------------------------------------
# the checks
# --------------------------------------------------------------------------

class Check:
    def __init__(self, name, why):
        self.name = name
        self.why = why
        self.results = []

    def add(self, ok, detail):
        self.results.append((ok, detail))

    def verdict(self):
        """Median over seeds: a check passes if it passed on most of them."""
        if not self.results:
            return False, "no data"
        n_ok = sum(1 for ok, _ in self.results if ok)
        return n_ok * 2 > len(self.results), self.results[0][1]


def run_checks(sweeps):
    checks = []

    def C(name, why):
        c = Check(name, why)
        checks.append(c)
        return c

    anchov = C("anchoveta owns the Humboldt",
               "a shallow-water, cold, very-high-productivity envelope, and "
               "the Humboldt is the only water on the track that is all three")
    anchov_gyre = C("anchoveta absent from the gyre",
                    "the gyre fails its productivity axis and its shore axis, "
                    "and the range table keeps it out of the whole Pacific "
                    "beyond the South-East")
    gyre_poor = C("the gyre is the poorest water on the track",
                  "no nitrate, so the epipelagic band is allocated almost "
                  "nothing; what is left is the mesopelagic, which is what "
                  "that water actually holds")
    gyre_meso = C("what is left in the gyre is mesopelagic",
                  "lanternfish and bristlemouths carry ANY_PROD envelopes and "
                  "live below the thermocline, so they are indifferent to a "
                  "barren surface")
    upwell = C("Benguela resembles the Humboldt",
               "both are eastern boundary upwellings, so their envelopes "
               "match on every axis; they differ only by the range table")
    endemic = C("...but shares no endemic with it",
                "the range table: anchoveta and South Pacific hake are "
                "South-East Pacific, Cape hake is South-East Atlantic")
    tuna = C("tropical tunas present but never dominant",
             "high trophic level, so the abundance term puts them two "
             "decades below the forage fish they eat")
    nototh = C("the Southern Ocean is notothenioid, not tropical",
               "a thermal envelope centred below 5 C excludes everything "
               "else, and the range table is circumpolar")
    diverse = C("no region collapses to one species",
                "competitive exclusion is not possible here -- presence is "
                "an envelope, not a competition -- so a region reduced to "
                "one species means a runaway abundance term, which would "
                "look the same on the plate as an ecological result")

    for by_region, stats in sweeps:
        sh = {r: share(by_region, r) for r, _, _, _, _ in REGIONS}

        h = sh.get("HUMBOLDT", {})
        forage_h = sum(h.get(k, 0.0) for k in
                       (F.ANCHOVETA, F.SARDINE, F.JACKMACK, F.CHUB))
        anchov.add(F.ANCHOVETA in h and forage_h > 0.10,
                   "anchoveta share %.3f, coastal forage %.3f"
                   % (h.get(F.ANCHOVETA, 0.0), forage_h))

        g = sh.get("PACIFIC_GYRE", {})
        anchov_gyre.add(g.get(F.ANCHOVETA, 0.0) == 0.0,
                        "anchoveta share in gyre %.4f" % g.get(F.ANCHOVETA, 0.0))

        # POOREST BY BIOMASS, not by species count. Species count is
        # confounded by how many of a thirty-three species roster happen to
        # live on a given shelf -- the Patagonian shelf scores low not
        # because it is barren but because this roster carries two of its
        # fish -- whereas biomass is the quantity "poorest" actually means.
        # ...and specifically about the EPIPELAGIC half. Total water-column
        # biomass makes a gyre look respectable, because the mesopelagic is
        # near-constant everywhere and four kilometres of it is a lot of
        # fish -- which is true, and is not what anyone means by calling a
        # gyre a desert. The desert is the sunlit half.
        bio = {}
        for reg, rows in stats.items():
            if rows:
                bio[reg] = sum(r[3] for r in rows) / float(len(rows))
        gyre_b = bio.get("PACIFIC_GYRE", 1e30)
        others = [v for k, v in bio.items() if k != "PACIFIC_GYRE"]
        gyre_poor.add(bool(others) and gyre_b <= min(others) * 1.15,
                      "gyre epipelagic biomass %.1f vs next poorest %.1f"
                      % (gyre_b, min(others) if others else -1))

        meso_g = sum(g.get(k, 0.0) for k in F.MESOPELAGIC)
        gyre_meso.add(meso_g > 0.45,
                      "mesopelagic share of gyre %.2f" % meso_g)

        b = sh.get("BENGUELA", {})
        # shared GENERA rather than shared species, which is the actual claim
        gen_h = {F.BY_KEY[k].binomial.split()[0] for k in h}
        gen_b = {F.BY_KEY[k].binomial.split()[0] for k in b}
        shared = gen_h & gen_b
        upwell.add(len(shared) >= 2,
                   "shared genera %s" % (sorted(shared) or "none"))
        endemic.add(F.ANCHOVETA not in b and F.HAKE_CL not in b
                    and F.HAKE_ZA not in h,
                    "Benguela has anchoveta=%s hake_cl=%s; Humboldt has "
                    "hake_za=%s" % (F.ANCHOVETA in b, F.HAKE_CL in b,
                                    F.HAKE_ZA in h))

        t = sh.get("TROP_ATLANTIC", {})
        tunas = (F.SKIPJACK, F.YELLOWFIN, F.BLUEFIN)
        tuna_share = sum(t.get(k, 0.0) for k in tunas)
        # PRESENT means a share worth seeing, not merely a non-zero key.
        # The first version accepted any presence at all and duly passed
        # with a share of 0.000, which is exactly the failure it was written
        # to catch.
        tuna.add(0.0005 < tuna_share < 0.35,
                 "tuna share of tropical Atlantic %.3f" % tuna_share)

        s = sh.get("SOUTHERN", {})
        noto = sum(s.get(k, 0.0) for k in
                   (F.TOOTHFISH, F.ICEFISH, F.SILVERFISH, F.GRENADIER))
        trop = sum(s.get(k, 0.0) for k in
                   (F.SKIPJACK, F.YELLOWFIN, F.DORADO, F.FLYINGFISH,
                    F.TREVALLY, F.GROUPER, F.FUSILIER))
        nototh.add(noto > 0.10 and noto > 4.0 * max(trop, 1e-6),
                   "notothenioid+grenadier %.2f vs tropical %.2f" % (noto, trop))

        # SKIP THINLY-COVERED REGIONS, and say so rather than passing
        # quietly. A box in which only two of thirty-five species score at
        # all will be dominated by one of them whatever the model does, and
        # that is a statement about the roster, not about the ecology. The
        # Patagonian shelf is the case: this roster carries an anchovy and a
        # hake for a shelf that really has a dozen, and Drake sits anchored
        # in one bay of it for fifty-nine days.
        thin = {r for r, rows in stats.items()
                if rows and sum(x[0] for x in rows) / float(len(rows)) < 3.0}
        worst = 0.0
        worst_r = ""
        for reg, d in sh.items():
            if d and reg not in thin:
                m = max(d.values())
                if m > worst:
                    worst, worst_r = m, reg
        # 0.85, not 0.60. A FORAGE FISH DOMINATING A SHELF IS REAL: anchoita
        # biomass on the Patagonian shelf genuinely exceeds hake several
        # times over, and the Humboldt is more lopsided still. The check is
        # guarding against a runaway exponent, not asserting evenness, and a
        # threshold that fails on a true result is a threshold that will be
        # ignored.
        diverse.add(worst < 0.85,
                    "largest single share %.2f (%s)%s"
                    % (worst, worst_r,
                       "  [thin: %s]" % ",".join(sorted(thin)) if thin else ""))

    return checks


# --------------------------------------------------------------------------
# the external check
# --------------------------------------------------------------------------

def obis_check(sweeps, top=4):
    """For the species the model makes dominant in each region, ask OBIS
    whether anyone has ever recorded that species in that box.

    A miss is not automatically a failure -- the South Pacific is barely
    sampled, which is the whole reason OBIS is not the source -- but a miss
    in a WELL-SAMPLED region is a real finding, so the record count for the
    box is printed alongside and the reader can tell the two apart."""
    try:
        from urllib.request import urlopen
        from urllib.parse import quote
    except ImportError:
        print("  (no urllib; skipping)")
        return
    by_region = sweeps[0][0]
    print("\nOBIS CROSS-CHECK  (a check, not a source -- see the docstring)")
    for name, la0, la1, lo0, lo1 in REGIONS:
        sh = share(by_region, name)
        if not sh:
            continue
        wkt = "POLYGON((%g %g,%g %g,%g %g,%g %g,%g %g))" % (
            lo0, la0, lo1, la0, lo1, la1, lo0, la1, lo0, la0)
        picks = sorted(sh, key=lambda k: -sh[k])[:top]
        print("  %-14s" % name)
        for k in picks:
            f = F.BY_KEY[k]
            url = ("https://api.obis.org/v3/occurrence?scientificname=%s"
                   "&geometry=%s&size=0" % (quote(f.binomial.title()), quote(wkt)))
            try:
                with urlopen(url, timeout=45) as r:
                    n = json.loads(r.read().decode()).get("total", 0)
            except Exception as e:
                print("      %-26s query failed (%s)" % (f.binomial.title(), e))
                continue
            mark = "ok " if n > 0 else "MISS"
            print("      %s %-26s %6d records  (model share %.2f)"
                  % (mark, f.binomial.title(), n, sh[k]))


# --------------------------------------------------------------------------
# calibration
# --------------------------------------------------------------------------

def calibrate(seeds=3):
    """A_MAX and A_SCALE, MEASURED rather than chosen.

    A_SCALE should put the scarcest a species ever gets, anywhere on the
    voyage while still being present, at about 1 -- so that every number on
    the plate reads as a multiple of the rarest thing anywhere. A_MAX should
    be the top of the observed range, so the bar uses its whole length."""
    lo, hi = 1e30, 0.0
    for seed in range(1, seeds + 1):
        by_region, _ = sweep(seed)
        for d in by_region.values():
            for vals in d.values():
                for v in vals:
                    if v > 0.0:
                        lo = min(lo, v)
                        hi = max(hi, v)
    print("observed abundance over the voyage: min %.4g  max %.4g" % (lo, hi))
    print("  ratio %.0f, which is %.1f decades" % (hi / lo, math.log10(hi / lo)))
    print("  A_SCALE should be multiplied by %.4g to put the floor at 1.0"
          % (1.0 / lo))
    print("  A_MAX should then be about %.4g" % (hi / lo))
    print("\ndrift.py:      A_SCALE = %.4g" % (drift.A_SCALE / lo))
    print("keyplate.py:   A_MAX = %.4g"
          % (10.0 ** math.ceil(math.log10(hi / lo))))


def main():
    args = sys.argv[1:]
    if args and args[0] == "calibrate":
        calibrate()
        return 0
    n = 1
    for a in args[1:]:
        if a.isdigit():
            n = int(a)
    print("sweeping %d seed%s over the whole voyage ..."
          % (n, "" if n == 1 else "s"))
    sweeps = []
    for seed in range(1, n + 1):
        sweeps.append(sweep(seed))
        sys.stdout.write("  seed %d done\n" % seed)
        sys.stdout.flush()

    checks = run_checks(sweeps)
    print("\nBIOGEOGRAPHY  (%d seed%s, median judged)"
          % (n, "" if n == 1 else "s"))
    bad = 0
    for c in checks:
        ok, detail = c.verdict()
        if not ok:
            bad += 1
        print("  %s %-42s %s" % ("PASS" if ok else "FAIL", c.name, detail))
        if not ok:
            print("       expected because: %s" % c.why)

    by_region, stats = sweeps[0]
    print("\nCOMPOSITION BY REGION")
    for name, _, _, _, _ in REGIONS:
        sh = share(by_region, name)
        if not sh:
            print("  %-14s (not visited)" % name)
            continue
        top = sorted(sh, key=lambda k: -sh[k])[:4]
        rows = stats.get(name, [])
        mean_n = sum(r[0] for r in rows) / float(len(rows)) if rows else 0.0
        print("  %-14s %4.1f spp  eff %4.1f   %s"
              % (name, mean_n, effective_species(sh),
                 ", ".join("%s %.2f" % (F.BY_KEY[k].common, sh[k]) for k in top)))

    if "--obis" in args:
        obis_check(sweeps)

    print("\n%d of %d checks failed" % (bad, len(checks)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
