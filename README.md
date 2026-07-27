# Drift

The fish of a voyage, on a 1-bit reflective panel.

A depth section of the water the ship is sailing through, from the surface to
a thousand metres, with the fish that live in it. Renders at 300x400, one bit
deep, no anti-aliasing — the exact resolution and bit depth of the target
hardware — then upscales nearest-neighbour, so what you see on a laptop is
what the panel will show.

```
pip install pygame numpy pillow
python3 drift.py            # Drake, 1577-1580
python3 drift.py beagle     # HMS Beagle, 1831-1836
```

| key | |
|---|---|
| `space` | pause |
| `m` | next screen now, and switch to the EXHIBIT cadence |
| `v` | next voyage |
| wheel | speed, continuously (shift+wheel for coarse jumps) |
| `1`–`5` | speed presets: real time / 1 min / 1 hr / 6 hr / 1 day per second |
| `c` | clean mode — fish only |
| `p` `n` | footer and screen chrome / the seabed and depth scale |
| `s` `r` | save a PNG / reseed |

Headless, no pygame needed:

```
python3 drift.py --stills out/     # six dates across one year
python3 drift.py --voyage  out/    # all 1018 days as a contact sheet, plus a CSV
```

The voyage runs on the same clock as the water. At the default 1 MIN/SEC a
simulated day takes 24 real minutes and the circumnavigation takes 17 real
days.

Three screens rotate: water, chart, water, key plate. `GALLERY` is the default
at ~2% chrome; `m` switches to `EXHIBIT` at 40% and it lapses back after five
minutes.

## What it does

Nothing in the model is told where anything lives. Each species carries an
**environmental envelope** — the water it tolerates, on four axes — the ocean
carries conditions, and presence falls out. This is Kaschner et al.'s Relative
Environmental Suitability model, which is what AquaMaps runs on for 33,000
species, and it is four numbers per axis:

```
suitability
    1.0        ┌──────────────┐
               │              │
    0.0  ──────┘              └──────
            lo    plo    phi    hi
```

So there is no rule saying `PERU → ANCHOVETA`. The anchoveta carries a
shallow, cold, very-productive envelope, and the Humboldt is the only water on
the track that is all three at once. The model discovers Peru.

Two things sit alongside the envelope and neither is a fudge. **Reachability**
is a separate table, because Atlantic cod are absent from the Benguela not for
any reason to do with the water — an eastern boundary upwelling at 15 °C over
a 150 m shelf is the North Sea in most months — but because the tropical
Atlantic is a barrier no cod has ever crossed. The environment decides what
water suits; history decides what got to it. And **abundance** comes from the
trophic pyramid, so a marlin is rare in barren water because there is nothing
beneath it to eat.

The depth axis is logarithmic, which is load-bearing rather than cosmetic:
`Z0 = 200/3` puts the base of the sunlit zone at exactly half the panel
height. That leaves room for the mesopelagic, and therefore for the **deep
scattering layer** — at dusk the lanternfish rise through the 200 m line
toward the surface and sink again at dawn, driven off real solar elevation at
the ship's actual latitude. It is the largest daily migration of animals on
Earth and it costs one term.

## Layout

| | |
|---|---|
| `drift.py` | the water column and the renderer. `Canvas` is the only part rewritten in C on the port; everything above it ports unchanged. |
| `fish.py` | the roster: envelopes, ranges, sizes, gaits, sources. Pure data and four comparisons. |
| `draw.py` | procedural fish morphology. One body wave, and where it starts is the swimming mode. Canvas only, imports nothing. |
| `voyage.py` | the voyages, as dated waypoint tables, great-circle interpolated. Adding one is a table and a `register()` call. |
| `mapview.py` | orthographic chart, north up. |
| `keyplate.py` | the key plate: a live census of what is in the water, plus voyage progress. |
| `screens.py` | the rotation between the three screens, and the dissolve between them. |
| `ocean.py` | real climatology, sampled by position and month. |
| `tools/console.py` | the development build: every tunable, live, with the number underneath. |
| `tools/check_biogeography.py` | does the emergent composition match known biogeography? `run 5` sweeps five seeds; `--obis` cross-checks against occurrence records. |
| `tools/plot_fish.py` | the whole roster drawn at panel scale; `--gaits` shows the four swimming modes through a beat. |
| `tools/plot_water.py` | the water screen at eight points on the voyage; `--dvm` steps one place through a day. |
| `tools/make_bathy.py` | NOAA ETOPO → the bottom-depth field in `data/ocean.bin`. |
| `tools/make_card.py` | the printed card for the box. |
| `plan.md` | where this is going. |

## The roster

Thirty-five species, chosen to cover every water mass the track crosses.
Depth ranges, temperature ranges, lengths and trophic levels are quoted from
**FishBase** species summaries rather than rounded to taste; where FishBase
gives both an absolute and a usual range, the absolute range sets the
trapezoid's feet and the usual range sets its shoulders, which is what those
two numbers mean.

`tools/check_biogeography.py` asserts the biogeography as a set of claims each
with a mechanism behind it — anchoveta own the Humboldt, the gyre is the
poorest water on the track and what is left in it is mesopelagic, the Benguela
resembles the Humboldt without sharing an endemic with it, the Southern Ocean
is notothenioid — and judges them over several seeds.

**OBIS is a check and not a source.** Occurrence records record where people
have looked: they are dense off Europe and near-empty across the South
Pacific, so a model fitted to them would inherit two centuries of survey
effort as if it were biogeography.

## Data

`data/coast.bin` — Natural Earth 1:50m coastline, Douglas-Peucker at 0.1°,
split at the antimeridian, int16 centidegrees. 14,447 points in 59 kB.
Natural Earth is public domain.

`data/ocean.bin` — 2° global grid, uint8, 490 kB. Sea surface temperature and
mixed layer depth at twelve monthly steps, nitrate at four seasonal steps,
distance-to-coast, an iron ceiling and bottom depth as static fields.

| field | source | licence |
|---|---|---|
| SST | [NOAA OISST v2.1](https://downloads.psl.noaa.gov/Datasets/noaa.oisst.v2.highres/) 1991–2020 climatology | public domain |
| mixed layer depth | [Ifremer / de Boyer Montégut 2024](https://www.seanoe.org/data/00870/98226/) | CC-BY-4.0 |
| nitrate | [World Ocean Atlas 2023](https://www.ncei.noaa.gov/access/world-ocean-atlas-2023/), seasonal, all years | public domain |
| bottom depth | [NOAA ETOPO](https://coastwatch.pfeg.noaa.gov/erddap/griddap/etopo180.html) via ERDDAP, 1 arc-minute | public domain |
| distance to coast | computed from `coast.bin` | — |
| iron | three hand-drawn HNLC boxes | — |

Rebuild the climatology by downloading the first three into a scratch
directory and running `python3 tools/make_ocean.py <dir> data/ocean.bin`.
Bathymetry alone can be added to an existing file with
`python3 tools/make_bathy.py data/ocean.bin`, which fetches what it needs.

## What is honestly wrong with it

**The envelopes are modern and the track is 1577.** The code already used
1991–2020 SST climatology for Drake's voyage, so this is an existing precedent
rather than a new one — but it is now load-bearing in a way it was not,
because fish distributions have moved further than isotherms have.

**A 1577 ocean had far more fish.** The roster shows where species live, not
the abundance Drake would have seen. Cod, bluefin and the great sharks are at
a fraction of their pre-industrial biomass, and no envelope model puts that
back.

**Size is compressed.** At true scale a 14 cm anchoveta in a thousand-metre
frame is a third of a pixel and only the sharks would be visible. The ordering
is preserved — nothing is drawn larger than something genuinely larger than it
— and the key plate prints the real length range, which is where the
compression gets corrected.

**Bathymetry is 2°, and an eastern boundary shelf is not.** The Peru shelf is
5 to 50 km wide with a trench immediately outboard of it, so the grid reports
the average of both. Distance-to-coast, computed at 0.1°, carries the shelf
signal instead; the reasoning is written out in `fish.py`.
