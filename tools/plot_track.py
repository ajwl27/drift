#!/usr/bin/env python3
"""
The ocean along Drake's track, plotted before any biology touches it.

    python3 tools/plot_track.py docs/ocean_track.png

This is Stage 3's deliverable and the point of it is separation: if the
climatology is wrong, that is a data bug, and finding it here is an afternoon.
Finding it after the ecosystem is coupled to it is a week, because every
symptom looks like an ecology problem.

Read it against what you know: nitrate should spike in the Southern Ocean and
off Peru and sit at zero across both Pacific gyres; the mixed layer should
deepen in the Patagonian winter and stay shallow through the tropics; iron
should drop only in the Southern Ocean and the equatorial Pacific.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def plot(dst="docs/ocean_track.png"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from voyage import Track, WAYPOINTS
    from ocean import Ocean

    track = Track()
    oc = Ocean("data/ocean.bin")
    total = track.days[-1]

    days = [d * 0.5 for d in range(int(total * 2) + 1)]
    lat, lon, sst, mld, no3, fe, shelf = [], [], [], [], [], [], []
    for d in days:
        la, lo = track.position(d)
        lat.append(la)
        lon.append(lo)
        sst.append(oc.sst(la, lo, d))
        mld.append(oc.mld(la, lo, d))
        no3.append(oc.nitrate(la, lo, d))
        fe.append(oc.iron(la, lo))
        shelf.append(oc.shelf_km(la, lo))

    # the landmarks worth annotating, chosen because each one should show up
    # in at least one of the panels
    marks = [(0, "PLYMOUTH"), (188, "PORT ST JULIAN"), (267, "CAPE PILAR"),
             (315, "CAPE HORN"), (429, "CALLAO"), (551, "NOVA ALBION"),
             (630, "MID PACIFIC"), (690, "TERNATE"), (817, "JAVA"),
             (915, "CAPE OF GOOD HOPE"), (1018, "HOME")]

    panels = [
        ("LATITUDE", lat, "deg", None),
        ("SEA SURFACE TEMPERATURE", sst, "C", None),
        ("MIXED LAYER DEPTH", mld, "m", True),
        ("SURFACE NITRATE", no3, "mmol/m3", None),
        ("IRON CEILING", fe, "0..1", None),
        ("DISTANCE TO COAST", shelf, "km", None),
    ]
    fig, axes = plt.subplots(len(panels), 1, figsize=(15, 13), sharex=True)
    for ax, (name, series, unit, invert) in zip(axes, panels):
        ax.plot(days, series, lw=0.9, color="#1a1a1a")
        ax.set_ylabel("%s\n%s" % (name, unit), fontsize=7.5)
        ax.grid(alpha=0.25, lw=0.4)
        ax.tick_params(labelsize=7)
        if invert:
            ax.invert_yaxis()
        if name == "LATITUDE":
            ax.axhline(0, color="#c04040", lw=0.7, ls="--")
        for d, _ in marks:
            ax.axvline(d, color="#888", lw=0.4, alpha=0.6)
    for d, lab in marks:
        axes[0].annotate(lab, (d, 0), xytext=(d, 78), fontsize=6,
                         rotation=90, ha="center", va="top", color="#444")
    axes[-1].set_xlabel("DAY OF VOYAGE  (13 DEC 1577 -> 26 SEP 1580)", fontsize=8)
    axes[0].set_title("The ocean along Drake's track, from WOA23 / OISST / Ifremer "
                      "climatology at 2 degrees", fontsize=10)
    fig.tight_layout()
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    fig.savefig(dst, dpi=150)
    print("wrote %s" % dst)

    def rng(v):
        w = [x for x in v if x is not None]
        return min(w), sum(w) / len(w), max(w)
    for name, series, unit, _ in panels[1:]:
        lo, mu, hi = rng(series)
        print("  %-24s %8.2f %8.2f %8.2f  %s" % (name, lo, mu, hi, unit))


if __name__ == "__main__":
    plot(sys.argv[1] if len(sys.argv) > 1 else "docs/ocean_track.png")
