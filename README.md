# Drift

A generative plankton column for a 1-bit reflective panel.

Renders at 300x400, one bit deep, no anti-aliasing — the exact resolution and
bit depth of the target hardware (a 4.2in ST7305 reflective LCD) — then
upscales nearest-neighbour, so what you see on a laptop is what the panel
will show.

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
| `c` | clean mode — organisms and snow only |
| `h` `p` `n` | HUD / footer and screen chrome / chemoautotroph stipple |
| `s` `r` | save a PNG / reseed |

Headless, no pygame needed:

```
python3 drift.py --stills out/     # six dates across one year
python3 drift.py --voyage  out/    # all 1018 days as a contact sheet, plus a CSV
```

The voyage runs on the same clock as the ecosystem. At the default 1 MIN/SEC a
simulated day takes 24 real minutes and the circumnavigation takes 17 real days.

Three screens rotate: water, chart, water, key plate. `GALLERY` is the default
at ~2% chrome; `m` switches to `EXHIBIT` at 40% and it lapses back after five
minutes.

## Layout

| | |
|---|---|
| `drift.py` | **the piece.** The ecosystem and the renderer. `Canvas` is the only part rewritten in C on the port; everything above it ports unchanged. |
| `console.py` | **the development build.** Every constant in `drift.py` as a slider, live, with the panel next to it and the measured consequence underneath. Never ships. |
| `voyage.py` | the voyages, as dated waypoint tables, great-circle interpolated. Pure functions of a day number. Adding one is a table and a `register()` call. |
| `mapview.py` | orthographic chart, north up. |
| `keyplate.py` | the key plate: a live census of what is in the water, plus voyage progress. |
| `screens.py` | the rotation between the three screens, and the dissolve between them. |
| `ocean.py` | real climatology, sampled by position and month. |
| `tools/make_coast.py` | Natural Earth shapefile → the packed coastline in `data/`. |
| `tools/make_ocean.py` | WOA23 / OISST / Ifremer netCDF → the packed ocean in `data/`. |
| `tools/plot_track.py` | the ocean along the whole voyage, as a diagnostic plot. |
| `tools/bench.py` | where the milliseconds go. Feeds the two measured constants in `tools/power.py`. |
| `tools/look.py` | six panels from six places on one sheet — the only test of whether a gyre looks like a gyre. |
| `tools/check_motion.py` | swimming speeds, drawn-body rotation per frame, and frame-rate independence. |
| `tools/power.py` | battery life, per board and per panel, from measured frame cost. |
| `tools/check_biogeography.py` | does the emergent composition match known biogeography? `run 5` to sweep five seeds and find out. |
| `tools/make_card.py` | the printed card for the box: whole-track chart plus the facts and the caveats. |
| `tools/make_landmask.py` | Natural Earth land polygons → a 0.1° bitmask, build-time only. |
| `tools/check_chlorophyll.py` | the one external check: model biomass vs MODIS chlorophyll along the track. |
| `tools/make_route.py` | audits every leg for land crossings and routes round them. `--check` to report, `--emit` for a new table. |
| `plan.md` | where this is going. |

## Data

`data/coast.bin` — Natural Earth 1:50m coastline, Douglas-Peucker at 0.1°,
split at the antimeridian, int16 centidegrees. 14,447 points in 59 kB.
Natural Earth is public domain.

`data/ocean.bin` — 2° global grid, uint8, 506 kB, format version 2. Sea
surface temperature and mixed layer depth at twelve monthly steps, nitrate at
four seasonal steps, and distance-to-coast, an iron ceiling and dissolved
oxygen at two depths as static fields.

Version 2 appended the oxygen after every version 1 field, so the offsets of
the first five are identical in both and a panel carrying a v1 blob still
reads it.

| field | source | licence |
|---|---|---|
| SST | [NOAA OISST v2.1](https://downloads.psl.noaa.gov/Datasets/noaa.oisst.v2.highres/) 1991–2020 climatology | public domain |
| mixed layer depth | [Ifremer / de Boyer Montégut 2024](https://www.seanoe.org/data/00870/98226/) | CC-BY-4.0 |
| nitrate | [World Ocean Atlas 2023](https://www.ncei.noaa.gov/access/world-ocean-atlas-2023/), seasonal, all years | public domain |
| distance to coast | computed from `coast.bin` | — |
| iron | three hand-drawn HNLC boxes | — |
| dissolved oxygen | [World Ocean Atlas 2023](https://www.ncei.noaa.gov/access/world-ocean-atlas-2023/), annual, all years | public domain |

Rebuild it by downloading those four into a scratch directory and running
`python3 tools/make_ocean.py <dir> data/ocean.bin`.
