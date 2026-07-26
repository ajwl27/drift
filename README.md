# Drift

A generative plankton column for a 1-bit reflective panel.

Renders at 240x400, one bit deep, no anti-aliasing — the exact resolution and
bit depth of the target hardware — then upscales nearest-neighbour, so what
you see on a laptop is what the panel will show.

```
pip install pygame numpy pillow
python3 drift.py
```

| key | |
|---|---|
| `space` | pause |
| wheel | speed, continuously (shift+wheel for coarse jumps) |
| `1`–`5` | speed presets: real time / 1 min / 1 hr / 6 hr / 1 day per second |
| `c` | clean mode — organisms and snow only |
| `h` `p` `n` | HUD / plate furniture / chemoautotroph stipple |
| `s` `r` | save a PNG / reseed |

Headless stills, no pygame needed: `python3 drift.py --stills out/`

## Layout

| | |
|---|---|
| `drift.py` | the ecosystem and the renderer. `Canvas` is the only part rewritten in C on the port; everything above it ports unchanged. |
| `voyage.py` | Drake's circumnavigation as 62 dated waypoints, great-circle interpolated. Pure functions of a day number. |
| `mapview.py` | course-up orthographic on a portrait panel. |
| `keyplate.py` | the key plate: a live census of what is in the water, plus voyage progress. |
| `tools/make_coast.py` | Natural Earth shapefile → the packed coastline in `data/`. |
| `plan.md` | where this is going. |

## Data

`data/coast.bin` — Natural Earth 1:50m coastline, Douglas-Peucker at 0.1°,
split at the antimeridian, int16 centidegrees. 14,447 points in 59 kB.
Natural Earth is public domain.
