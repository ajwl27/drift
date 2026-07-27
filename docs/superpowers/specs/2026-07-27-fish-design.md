# DRIFT → the fish overhaul

Replace the plankton column with the fish of the water the ship is sailing
through. Same object, same three screens, same panel: what changes is what is
in the water, and therefore the scale, the depth axis, the motion and the
drawings.

## Why this port is small where it looks large

The existing model's thesis is stated in the comment above `TRAITS`:

> There is no column saying where anything lives, and no rule anywhere that
> mentions a place. Each organism carries a size, a growth intercept and a
> thermal preference; the ocean carries conditions; and who wins falls out.

That thesis survives intact, and it is the reason this is a port rather than a
rewrite. The standard method for predicting where a marine species lives —
Kaschner et al.'s Relative Environmental Suitability model, which is what
AquaMaps runs on — is the same idea with different axes. A species carries an
envelope; the ocean carries conditions; presence falls out.

So `voyage.py`, `mapview.py`, `places.py` and `screens.py` are untouched. The
`Canvas`, the fonts, the text layout, the dissolve and the cadence are
untouched. What changes is the ecosystem, the drawings and the depth axis.

## 1. The depth axis

`Z_MAX` goes from 55 m linear to **1000 m logarithmic**.

The log axis is load-bearing, not cosmetic. Fish depth distributions span three
orders of magnitude and a linear axis spends 80% of the panel on water that has
almost nothing in it. On a log axis the sunlit 0–200 m — where a sardine shoal,
a tuna and a flying fish live — takes half the panel, and the mesopelagic still
fits below it.

    depth_to_y(z) = TOP_M + log1p(z / Z0) / log1p(Z_MAX / Z0) * (H - TOP_M - BOT_M)

`Z0` sets how much the top is stretched. It is a judgement about looking, so it
belongs in `tools/console.py` with `SWIM_SCALE` and `TARGET_FPS`.

Three things follow that the current piece cannot do:

**The seafloor.** Drawn when it rises into frame. Over the Patagonian shelf the
bottom is at 90 m and visible; mid-Pacific it is at 4,200 m and the panel bottom
is open water. Bathymetry stops being implied and becomes the most legible
statement of place on the screen.

**Diel vertical migration.** `solar_elevation()` already exists and is already
on the clock. At dusk the deep scattering layer rises toward the surface; at
dawn it sinks. This is the largest daily animal migration on Earth, roughly half
of mesopelagic backscatter participates in it, and it costs one term on the
depth of migrating species.

**The scale lie reverses.** The current panel magnifies about 200×. This one
reduces about 2,500×, so a 12 cm anchoveta at true scale is a third of a pixel.
Drawn size therefore stays compressed — the same deliberate lie the plankton
column already tells, in the opposite direction, and it gets the same treatment:
written down in the source rather than hidden, and corrected on the key plate,
which is where the real length range is printed.

## 2. Presence: the trapezoidal envelope

Per species, per axis, four numbers:

    suitability
        1.0        ┌──────────────┐
                   │              │
        0.0  ──────┘              └──────
                MinD  PrefMin  PrefMax  MaxD

Zero outside `[MinD, MaxD]`, one across `[PrefMin, PrefMax]`, linear on the two
ramps. Four axes, multiplied:

| axis | source | already in `ocean.bin`? |
|---|---|---|
| bottom depth | ETOPO/GEBCO, new field | **no — to be added** |
| sea surface temperature | NOAA OISST climatology | yes |
| productivity | WOA23 nitrate × light | yes |
| distance to shore | computed from `coast.bin` | yes |

Sixteen bytes per species. A 28-species roster is under 1 kB of flash and
compiles to a const table, which is the same shape as `DERIVED` today.

**This is what keeps the thesis.** No rule says `PERU → ANCHOVETA`. The
anchoveta carries a shallow-depth, cold-SST, very-high-productivity envelope,
and the Humboldt is the only water on the track that satisfies all three at
once. The model discovers Peru. Equally, nothing says the South Pacific gyre is
empty — it comes out empty because no envelope in the roster matches water that
warm and that barren, which is the correct reason.

## 3. Trophic coupling

Envelope suitability says who *can* live here. It does not say how many, and on
its own it would put a marlin in barren water as readily as in rich water.

So productivity gates the chain. With the NPZ model deleted, productivity is an
**environmental field** rather than a simulated population — nitrate × light
from `ocean.bin`, sampled exactly as SST is. Forage abundance follows
productivity; predator abundance follows forage.

    nitrate × light ──► forage fish ──► predators

This is one multiplication per trophic level and no state. It is also why
deleting the plankton simplified rather than complicated things: a scalar field
sampled from flash does the job the whole NPZ model was doing, for the purposes
that remain.

## 4. What is deleted

The NPZ model, the picoplankton scalar field, the chemoautotroph stipple, the
resolved detritus, the marine snow, the eighteen procedural cell drawings, the
`Genome` inheritance machinery, division, and per-cell growth.

**The panel must never be bare**, and the honest solution is not decoration. The
mesopelagic is never empty: lanternfish are the most abundant vertebrates on
Earth and bristlemouths (*Cyclothone*) are the most abundant vertebrate genus,
and both live in every ocean on the track. So `N_FLOOR` in a gyre yields
myctophids and a lone wahoo — which is not a fallback, it is what that water
actually contains.

## 5. Motion

`SWIM_BL` in body-lengths per second survives as the right unit — it is the one
number that survives the magnification change, which is exactly why it was
chosen. The values change: 14 BL/s for a flagellate becomes roughly 2–10 BL/s
for fish, and tail-beat frequency scales with length as approximately `f ∝ L⁻¹`.

Gaits become genuinely distinguishable at 300×400, where the plankton gaits were
subtle:

| gait | who | what it looks like |
|---|---|---|
| thunniform | tuna, marlin | stiff body, high-aspect tail, fast and straight |
| carangiform | most fish | rear-third body wave |
| anguilliform | eel, viperfish | whole-body wave |
| shoaling | herring, anchoveta, sardine | many individuals, correlated heading |

Shoaling is the one genuinely new behaviour and the one most worth having: an
anchoveta shoal in the Humboldt should read as a shoal, not as forty independent
random walks.

## 6. Validation

`tools/check_biogeography.py` is rewritten. It keeps its present form —
assertions with a mechanism behind each, judged over several seeds, set to catch
a regression rather than to be barely cleared — and asserts:

- anchoveta dominate the Humboldt and are absent from the gyre
- the South Pacific gyre is the poorest water on the track, and myctophids are
  what is left
- the Benguela and the Humboldt resemble each other, because both are eastern
  boundary upwellings
- tropical tunas are present across the equatorial band and never dominant
- the Southern Ocean legs are notothenioid, not tropical

Cross-checked against **OBIS** occurrence records per region. OBIS is a check
and not a source: occurrence data records where people have looked, so it is
dense off Europe and near-empty mid-Pacific, and using it directly would put the
biogeography of a round-the-world track at the mercy of survey effort.

## 7. Caveats, to be stated in the source

**The envelopes are modern; the track is 1577.** The code already samples
1991–2020 SST climatology for Drake's voyage, so this is an existing precedent
rather than a new lie — but it is now load-bearing in a way it was not, because
fish distributions have moved further than isotherms have.

**A 1577 ocean had far more fish.** The roster shows where species *live*, not
the abundance Drake would have seen. Cod, bluefin and whales in particular are a
fraction of their pre-industrial biomass. The piece is a map of occupancy, not
of plenty, and the card in the box should say so.

## 8. Order of work

1. `fish.py` — the roster: envelopes, sizes, gaits, names, sources
2. bathymetry into `ocean.bin`, and `Ocean.depth_m()`
3. `drift.py` — depth axis, assemblage model, fish drawings, gaits
4. `keyplate.py` — census against the new roster
5. `tools/` — validation against OBIS, and the console's new tunables
6. `README.md` and `plan.md`
