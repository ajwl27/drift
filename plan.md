# Drift — the voyage

*Plan for adding Drake's circumnavigation to the plankton column.*

---

## The thing we are building

A framed panel showing a slice of open water. Plankton drift, divide, graze and
sink in fine 1-bit line work. Underneath it all, a boat is sailing Drake's track
of 1577–80, one voyage day per real day, and the community in the water changes
because the water changes. Every so often the water dissolves away and the panel
becomes a chart — the globe, the ship, the track behind it — and then dissolves
back.

It takes two years and ten months to complete, and then it starts again.

The point is not that the plankton are correct. The point is that **nobody told
them where to live.** The organisms carry traits; the ocean carries conditions;
the winners fall out. When the panel fills with diatom chains off Peru it is
because the model discovered that high growth rate beats good nutrient affinity
when nutrients are abundant — not because a table said `PERU → DIATOMS`.

---

## The five decisions, and what they cost

You set these up front. Here is what each one actually implies.

### 1. Science-inspired, not wedded to it. Never a dead screen.

This is the constraint that shapes everything else, so it needs a real answer
rather than a fudge factor.

The honest ecology is brutal: a subtropical gyre carries roughly **1/30th** the
phytoplankton biomass of a coastal upwelling. Rendered literally, the Pacific
crossing is nine weeks of three organisms on blank paper. That is defensible and
it is also unwatchable.

The wrong fix is a floor on the biomass, because it breaks the model that makes
the piece worth building.

**The right fix is that oligotrophic water is not empty of interest — it is empty
of *biomass*.** Those are different things, and the difference is exactly where
the visual interest lives:

| | Gyre | Upwelling |
|---|---|---|
| Individuals on screen | ~10 | ~40 |
| Individual size | large | small |
| Form | solitary, radial, ornate | chained, linear, plain |
| Who | Acantharia, foraminifera, coccolithophores, *Ornithocercus*, salps, *Trichodesmium* | *Chaetoceros*, *Rhizosolenia*, *Coscinodiscus*, *Corethron*, copepods |
| Reads as | a Haeckel plate | a diatom smear |
| Ink on the panel | ~ same | ~ same |

Real oligotrophic plankton *are* the ornate ones — rhizarians and radiolarians and
sail-bearing dinoflagellates are gyre organisms, because in water with nothing in
it the winning strategy is to be big, long-lived, mixotrophic and unpalatable.
So the aesthetically necessary move and the ecologically correct one are the same
move. That is the single most important finding in this plan.

Three concrete mechanisms:

- **Compress count, not biomass.** Let the model's biomass be honest, then map it
  to individuals sub-linearly: `n_visible ∝ biomass^0.45`, floor 8, cap 46. A
  30× biomass ratio becomes a 4× count ratio. The contrast survives; the empty
  screen does not.
- **Size inversely with density.** Ink area per individual scales *up* as biomass
  falls, so total ink stays roughly constant while the character changes
  completely. This is the mechanism doing most of the work.
- **The stipple layer carries the gyre.** Picoplankton (*Prochlorococcus*) genuinely
  dominate gyre biomass and are genuinely sub-micron — unrenderable as
  individuals. Victorian plates solved this with a dot screen, and so do we: the
  existing chemoautotroph stipple generalises into a picoplankton haze whose
  density tracks small-cell biomass. In the gyre the water is *textured* rather
  than populated. Marine snow does the rest.

**Where we knowingly depart from the science**, all of it logged here so it stays
a decision rather than a bug:

- Organism size is not to scale, and never was. A 60 µm diatom is a fraction of a
  pixel.
- Modern climatology under a Tudor track. The 1578 ocean was pre-industrial and
  mid–Little Ice Age. Lean into it: *the ocean as it is now, along the track as it
  was then.*
- Functional-group accuracy, not species accuracy. The morphologies are
  representative, not identification-grade.
- Depth axis rescales with the local mixed layer (see §5), which no real plate
  would do.

### 1b. The room sensors are out — **decided**

The original concept coupled the ecosystem to the room: a light sensor for cloud
cover, a BME280 for temperature and pressure. The voyage replaces all three with
a real ocean, and two forcings driving the same model would have fought each
other — a bright afternoon in a Cambridgeshire office has no business overruling
the Humboldt Current.

Consequences, all good: the BOM loses the sensor package; `Environment.cloud`,
`storm` and `temp_anomaly` stop being a random walk and become either real
climatology or a seeded pseudo-weather deterministic in day number; and the
piece becomes fully reproducible, so day 429 of every voyage has the same
weather. That last one matters more than it sounds — it means the whole 1018
days can be rendered offline for review, which is what Stage 6 needs.

What is lost is the piece's connection to the room. That was a real virtue and
it is worth naming rather than quietly dropping. The voyage buys something
better in its place: the object is no longer about *here*, it is about
*elsewhere*, which is a stronger idea for something you look at from a desk.

### 2. It has to run on the hardware

Confirmed targets: **RP2350** (dual Cortex-M33, hardware single-precision FPU,
520 kB SRAM, 4 MB QSPI flash on a Pico 2, 150 MHz) or **ESP32-S3** (dual LX7,
hardware FPU, 512 kB SRAM + 2–16 MB PSRAM, 4–32 MB flash).

Everything below is costed against the smaller of those. The rule that has held
since the first line of `drift.py` holds here too: **`Canvas` is the only thing
that gets rewritten in C.** Anything that calls `Canvas` and nothing else ports
unchanged. `voyage.py` and `mapview.py` were written to that rule and obey it.

One thing worth knowing before you order: the ST7305 is **not** a Sharp Memory
LCD. Sharp's MIP panels hold an image at essentially zero current; the ST7305 is
a reflective active-matrix TFT that still refreshes (0.25–51 Hz selectable,
~40 µA at 1 Hz, ~5 mA at 51 Hz). It is still excellent for this — but budget it
as a low-power display, not a zero-power one. Also note the ESPHome driver for
the 400×300 variant carries a **~360 kB lookup table**, which is fine on an
ESP32-S3 with PSRAM and impossible on a bare Pico 2. If you go RP2350, plan on
writing the driver rather than porting that one.

### 3. Morphology is the main visual interest

So morphology is not decoration on top of the model — it *is* the model's output
channel. Nineteen types, chosen for silhouette separation as much as for ecology,
spanning a 6:1 size range down to a measured legibility floor. See §6 and §8.

### 4. Alternate between map and water, no minimap

Agreed, and solved. See §7. The prototype is already in the repo and the images
are in the conversation.

### 5. Don't waste screen on the map. 6. Interpolate, don't jump.

Both solved. §7 and §4.

---

## Architecture: what changes

```
                     BEFORE                        AFTER
  Canvas             1-bit primitives              unchanged
  Environment        fiction + Melbourn solar      driven by Track + climatology
  Ecosystem          one implicit species pool     16 typed pools, traits from size
  Renderer           7 draw functions              16 draw functions
  View               plate / hud / chemo / snow    + map, + transition phase
  --                 --                            Track      (new, done)
  --                 --                            Camera     (new, done)
  --                 --                            Ocean      (new, §5)
```

The core loop does not change. `step()` keeps its shape; what changes is that
`MU_MAX`, `K_S`, `W_DET` and friends stop being module constants and become
columns of a per-type trait table. That is a couple of hours of mechanical
refactoring, not a rewrite — and it is the highest-leverage two hours in the
project, because everything downstream depends on it.

---

## 4. The track — **done**

`voyage.py`, in the repo, working.

62 dated waypoints, Plymouth to Plymouth, 13 Dec 1577 → 26 Sep 1580 = **1018
days**. Interpolation is **slerp between unit vectors** — great-circle, constant
speed along the arc. Linear interpolation of lat/lon was never an option: it
leaves the great circle, and near the date line it takes the wrong way round the
world.

Validation already run:

- Great-circle sum: **35,789 nautical miles.** The figure usually quoted for the
  voyage is ~36,000. Nothing was tuned to hit that.
- **210 of 1018 days at anchor** (21%) — Port St Julian 59 days, Nova Albion 36,
  Banggai 28, Salada Bay 29, Java 17. These are in the table as repeated
  positions on different days, so they fall out of the interpolation for free.
  They matter: a fifth of the piece is spent sitting in one water mass watching it
  develop, which is the closest this object gets to the original Melbourn concept.
- Leg speeds all plausible (0.1–4.7 knots) except one: **Río de la Plata →
  Puerto Deseado, 1630 km in 4 days = 9.2 knots.** Both dates are attested; the
  passage is genuinely fast. Left as-is and flagged in `NOTES` rather than
  quietly smoothed.

Every waypoint carries a confidence tag, and the plate says so when it is
guessing:

- **2** — date and place both well attested (the Strait transit, Ternate, the
  return).
- **1** — place attested, date approximate.
- **0** — reconstructed. Notably: the southernmost point after the post-Magellan
  storm (da Silva logged 57°S, at which latitude there is no land — the island is
  treated as a phantom by modern scholarship, and whether Drake actually saw the
  passage that bears his name is still argued); Nova Albion, where the two
  surviving manuscripts say 44°N against the printed 38°N and there are twenty-odd
  candidate sites; and **the entire Pacific crossing**, 68 days out of sight of
  land with not one intermediate position recorded anywhere.

That last one is worth stating plainly, because it is where the piece is at
maximum risk of looking broken: **nine weeks in the North Pacific gyre, on a
track we invented, showing the emptiest water on Earth.** It is also, if the
never-empty work in §1 lands, the most beautiful stretch — a handful of enormous
ornate solitary organisms in a haze of picoplankton, for two months. Get this
stretch right and the rest is easy.

`Track` also exposes `speed(day)`, which is 0 at anchor. The ecosystem uses it to
decide whether the water is being *replaced* or merely *sat in* — at anchor the
community develops in place and the lag terms matter; under way, advection
imports whatever suits the new conditions.

---

## 5. The ocean — what we carry in flash

Real climatology, sampled by position and month. It costs almost nothing and it
removes an enormous amount of hand-tuning.

| Field | Source | Grid | Time | Bytes |
|---|---|---|---|---|
| Sea surface temperature | NOAA OISST v2.1 climatology (`sst.mon.ltm.1991-2020.nc`, 44 MB, one file, 12 months already baked in) | 5° | monthly | 31 kB |
| Mixed layer depth | Ifremer / de Boyer Montégut 2024, CC-BY, 6 MB, 1°, monthly | 5° | monthly | 31 kB |
| Surface nitrate | World Ocean Atlas 2023, `all` time span (nutrients have no decadal monthly product — sampling is too sparse) | 5° | annual | 2.6 kB |
| Iron / HNLC ceiling | **hand-coded, 3 boxes** — see below | 5° | static | 0.3 kB |
| Shelf vs. abyssal | ETOPO 2022 60″, box-averaged, thresholded | 5° | static | 2.6 kB |
| **Coastline** | **Natural Earth 50m, DP 0.1°, antimeridian-split, int16 centidegrees** | — | — | **59 kB** |
| | | | **Total** | **~127 kB** |

Against 4 MB of flash this is a rounding error. 2° grids would cost ~810 kB and
still fit — but 5° is already finer than a 240×400 panel can express, so it buys
nothing.

**Gotchas, all verified:** WOA files carry a 102-level depth dimension you must
`.sel(depth=0)` before anything else (that is why the files are 20–60 MB for a
surface field); OISST is 0–360°E while WOA and ETOPO are −180–180; land is
`_FillValue` ≈ 9.97e36 and needs an explicit sentinel (reserve 255) rather than
being allowed into the min/max scaling; MLD is heavily right-skewed (10–50 m
typical, 500 m+ in winter deep mixing) so quantise it on a log scale or you throw
away the whole useful range.

**On iron.** This is the one place where dropping a term visibly breaks the
piece. The Southern Ocean and the equatorial Pacific are HNLC — nitrate is
abundant and chlorophyll is low, *because iron is missing*. Drake's track crosses
both. Ignore iron and the model will draw nitrate down and bloom in exactly the
two regions famous for not blooming: the one thing an HNLC region is defined by
not doing. There is no clean hobbyist-downloadable iron climatology (Mahowald's
old pages are dead; the living equivalents are CMIP6 input4MIPs on ESGF, which is
not a weekend download), so: **three hand-coded boxes** — south of 50°S, the
equatorial Pacific 10°N–10°S east of the dateline, and the subarctic North
Pacific — as a 2-bit iron ceiling applied via Liebig's law of the minimum. A few
hundred bytes, and it is the difference between the Southern Ocean reading
correctly and reading as a lie.

**Depth axis.** The current panel is a fixed 0–55 m column, which is wrong for a
voyage where the mixed layer runs from ~10 m in the tropics to 500 m+ in the
Southern Ocean winter. Make `Z_MAX` track the local MLD — `Z_MAX = clamp(1.6 ×
MLD, 45, 160)` — interpolated smoothly over days so it never jumps, with the
depth scale on the plate relabelling as it goes. The numbers changing beside the
column, slowly, over weeks, is a quietly excellent detail.

---

## 6. Biology — traits in, biogeography out

### The mechanism, in one paragraph

Everything reduces to a race between three timescales: how fast nutrients are
resupplied, how fast phytoplankton grow, and how fast grazers respond. Two
allometric facts drive the whole thing, and both are well established:

```
mu_max ∝ V^-0.25      Edwards et al. 2012, marine, 95% CI (-0.20, -0.29)
K_N    ∝ V^+0.30      Edwards et al. 2012, marine, 95% CI (+0.26, +0.42)
sink   ∝ V^+0.39      Ward et al. 2012
```

Small cells have low K and win at low, steady nutrient supply (Tilman's R\*).
Large cells have higher absolute uptake and — crucially — **diatoms specifically
sit above the allometric line for growth rate** (Edwards et al., p<0.001; Ward et
al. give the intercept as 3.8 for diatoms vs 2.1 for other eukaryotes, 1.4
*Synechococcus*, 1.0 *Prochlorococcus*), so they win transients. That is the
entire content of "diatoms are the weeds."

And then the loophole (Irigoien et al. 2005), which is what makes a *bloom* rather
than just a different steady state: microzooplankton generation time ≈ prey
generation time, so they track small cells almost exactly and hold the gyre in
tight low-biomass control. Mesozooplankton take weeks. So when nutrients pulse,
large fast diatoms escape control entirely — the grazer that could eat them
cannot reproduce fast enough to matter. **We already have this**: the existing
model's copepods and tintinnids are exactly the slow and fast grazer. It needs the
timescale separation made explicit and correct, not new machinery.

### Design: typed pools, traits derived from size

The literature approach is a continuous trait space with randomly-seeded types.
We should **not** do that, for one reason: morphology is the output channel
(decision 3), and a continuous trait space has no morphology.

Instead: **16 discrete functional types, each with a morphology and a size. Every
other trait is computed from size via the allometry above, plus one per-type
growth intercept and two or three flags.** That is Darwin-with-16-types, it gives
morphology for free, and it is far less code.

Per type, stored in flash (~24 B each, 400 B total):

```
size_um   growth_intercept   T_opt   T_width   mode(AUTO|MIXO|HETERO)
flags: CHAIN | DIAZOTROPH | CALCIFIER | MOTILE | GRAZER_MICRO | GRAZER_MESO
```

Per individual, in RAM: existing `Agent` plus a `type` byte and a lognormal
growth jitter (σ≈0.35) so no two cells of a type are identical. **The jitter is
not cosmetic** — it is what lets a subset of individuals land on an unusually
favourable trait combination and found a bloom, which is how real diversity works.

Derived per step, not stored:

```
mu_max(i) = MU0 * intercept[t] * jitter(i) * (size/SIZE_REF)^-0.25 * eppley(T) * niche(T, T_opt, T_width)
K_N(i)    = K0 * (size/SIZE_REF)^0.30
K_Fe(i)   = KFE0 * (size/SIZE_REF)^0.27 * (25 if DIAZOTROPH else 1)
w_sink(i) = W0 * (size/SIZE_REF)^0.39 * (0.45 if CHAIN else 1)
mu(i)     = mu_max * min(f_N, f_Fe) * f_light - respiration - grazing
```

`eppley(T) = 0.851 · 1.066^T` (Eppley 1972) is the envelope; `niche()` is a
Gaussian on `T_opt` with width `T_width`. Two lines, and temperature
biogeography stops being something we tune.

Diazotrophs (*Trichodesmium*) get: no N limitation at all (they fix it), a much
lower `mu_max` (0.25 d⁻¹ measured — Breitbarth et al. 2007), a **hard cutoff below
20 °C** and an optimum at 24–30 °C, and a 25× iron demand (nitrogenase carries 15
Fe atoms per subunit; measured Fe:C is 180–214 vs 1–7 mmol/mol for diatoms —
Berman-Frank et al. 2001). Those four numbers are the entire reason the
subtropical gyres are habitable at all, and they are the reason *Trichodesmium* is
abundant in the dust-fed Atlantic and scarce in the iron-poor Pacific. Getting
this right means the Atlantic and Pacific gyres look *different*, which is a level
of subtlety nobody will consciously notice and everybody will feel.

### Seeding — "everything is everywhere, the environment selects"

Extinction lock is the failure mode that kills this: a type disappears from a bad
region and is never available when it becomes favourable again. Fix: every type
has a small probability per day of appearing as a single cell, weighted by how
favourable the local environment currently is for it. Cheap, and it is also
literally true of the ocean.

### What we can drop, and what we cannot

Drop, with justification: separate NO₃/NH₄/PO₄/SiO₄ (collapse to one N — the
pattern depends on the *scaling* of K, not which nutrient it is); Droop
internal-quota dynamics (Monod is enough; we lose some bloom lag); a real P-I
curve (one light multiplier); explicit mixotrophy for most types.

Do **not** drop: the K-vs-μmax trade-off (it is the whole exercise); the fast/slow
grazer timescale split (without it you get the right steady states and no blooms);
iron (§5).

### Expected biogeography, as a checklist to test against

| Water | Should be dominated by | Because |
|---|---|---|
| Subtropical gyre (N & S Atlantic, N & S Pacific) | pico haze, coccolithophores, *Trichodesmium*, Acantharia, forams, salps | lowest K wins at steady trickle supply; diazotrophs supply the N |
| Equatorial upwelling (Pacific) | small cells under tight microzoo control — **not** a diatom bloom | HNLC: nitrate is there, iron is not |
| Coastal upwelling (Humboldt, Benguela) | diatom chains, *Rhizosolenia*, copepods | N *and* Fe abundant + pulsed → high-intercept μmax wins the transient |
| Southern Ocean | diatoms and salps where iron reaches, otherwise HNLC small cells | iron-limited except near shelves and islands |
| High-latitude spring bloom (Plymouth, Patagonia) | diatoms, then a copepod crash | Sverdrup: MLD shoals, light arrives, grazers lag |
| Warm oligotrophic Indian Ocean / Coral Triangle | pico + diazotrophs | warm enough for N fixation, P-replete relative to N |

Drake's track hits every row of that table. If the model reproduces it without
being told, the feature works.

---

## 7. The map — **solved, prototype in the repo**

### The portrait problem

A globe drawn to fit 240 px wide leaves a third of a 400 px frame empty. Drawn to
fill the height it overflows the width. A minimap you have ruled out, correctly.

**So stop drawing a map of the world and draw the world from where the ship is.**
Orthographic centred on the boat, **rotated so the course points up the long axis
of the panel.** The tall frame now shows more of where you are going and where you
have been than of the empty water either side — which is the correct emphasis for
a voyage, and is how every strip chart since Ogilby has been laid out. Drake's
track is mostly north–south down the Atlantic and up the Americas, and the
crossings are mostly east–west; course-up means the long axis follows the track in
both cases. **Portrait stops being a constraint and becomes the right shape.**

One number controls everything — `R`, the globe radius in pixels:

| R | Frame covers | Reads as |
|---|---|---|
| 118 | whole hemisphere, limb inside the 240 width | unmistakably the Earth |
| **233.2** | 6,886 × 13,129 km — **the limb exactly clears the corners** | full frame, no visible edge, no white space |
| 600 | 2,566 × 4,330 km | regional |
| 1400 | 1,094 × 1,827 km | coastal |

`R = √(120² + 200²) = 233.2` is the exact answer to "don't waste screen": the
smallest radius at which the globe covers a 240×400 rectangle completely.

### The interlude is a camera move, not a screen

This is what makes the wasted-space question disappear:

```
water  ──dissolve──▶  R=118 globe  ──dolly, 8 s──▶  R≈900 chart  ──hold 6 s──▶  ──dissolve──▶  water
```

The half-empty globe is only ever on screen *while moving through it*. Zoom is
geometric in R with smoothstep easing, because the eye judges zoom
multiplicatively and a linear ramp in radius reads as a lurch.

Dissolve on 1 bit: an ordered **Bayer threshold ramp**. Compare each pixel's Bayer
value to the transition phase and take it from the old buffer or the new one.
Cheap, no grey needed, and it looks like an engraving being replaced rather than a
screen wipe.

### Tonal hierarchy — the thing that took two attempts

1 bit has no grey, so the only way to make a line recede is to break it. Dot pitch
*is* the tonal scale:

- **Solid:** coastline, and the track behind the ship.
- **Dotted, pitch 4:** graticule.
- **Dotted, pitch 6:** the track ahead.

Two things learned by rendering it wrong first: a 15° graticule out-inks the
coastline and the map stops being a map (30° works); and meridians run to the pole
converge into a starburst that reads as damage (stop them at 70°).

The track carries a **cross-tick every 30 days**, like a marked log line. This
turns an anonymous curve into a record of elapsed time — and it makes the
anchorages legible with no annotation at all, because at Port St Julian the ship
sits for 59 days and two ticks land on top of each other, so the track grows a
knot.

### Performance — and the reason it will actually run

Naively, projecting 14,447 coastline points costs 2 sin + 2 cos + ~15 multiplies
each. That is too much per frame for a smooth dolly.

But orthographic-plus-course-up is **a pure dot product against an orthonormal
basis**, and the bearing rotation folds into the basis vectors once per frame. So
store the coastline as **precomputed int16 unit vectors** instead of lat/lon and
the per-point cost becomes **9 multiply-adds and no trig at all.**

Verified numerically against the trig form: max disagreement **1.4 × 10⁻¹³ px**.

- Flash cost: 87 kB instead of 58 kB. We have 4 MB.
- RP2350 at 150 MHz with hardware FPU: ~18 cycles/point → **1.7 ms per full map
  redraw.** The dolly can run at 30 fps with the CPU asleep most of the time.

This is the single finding that decides whether the map is feasible on the
hardware, and it says yes with two orders of magnitude to spare.

### When the map appears

- **Scheduled:** roughly every 20 minutes, ~20 s long. Slightly irregular so it
  never feels like a clock.
- **Event-triggered**, which is the part that matters — the map should appear when
  there is something to see: making a landfall (within ~150 km of a coastline
  point), weighing anchor, crossing the equator, crossing the antimeridian,
  entering a new ocean basin, and the largest single change in community
  composition in the last 30 days.
- **Manual:** `m` in the preview, the KEY button on the panel.
- **Never** during a bloom peak. If the water is doing something, stay in the
  water.

### Clean mode on the map

`c` already hides plate furniture. On the map it hides graticule, scale bar and
caption, leaving **coastline, track and ship** on bare paper. That is a beautiful,
very spare object — and in mid-Pacific it is nearly blank, which is honest but
worth seeing before committing. The rendered comparison is in `docs/map_clean.png`.

---

## 7a. The water view — stripped — **done**

The double border, the numbered depth scale and the tide staff are gone. The
borderless renders read better than the framed ones, and once the border goes
the depth scale has nothing to sit against and becomes clutter.

What survives is a single footer line and a hairline:

```
DRIFT                              12°03'S  077°09'W
──────────────────────┴─────────────────────────────
```

Name, position, and the voyage as a bar with one tick. The bar rather than a day
count, because *how far through* is the interesting quantity and *day 429* is
not. `TOP_M`/`BOT_M` drop from 9/26 to 4/18, so the water column also gains
13 px of height — the strip that used to be border.

`c` still takes even this away.

## 7b. The third screen — the key plate — **prototype in the repo**

`keyplate.py`, working. See `docs/three_screens.png`.

This solves a problem the other two screens cannot. Water and map are both
beautiful and both mute: a person who walks into the room has no way in. Every
natural-history plate ever printed has a key, and that is exactly the idiom —
so the third screen is the plate's key, and it makes the object legible without
making it a gadget.

The important design choice: **it lists only what is actually in the water right
now, sorted by abundance.** That makes it a census rather than a legend. It
changes as the ship sails, and watching the list turn over between Callao and
mid-Pacific is probably the clearest single statement the piece makes.

Each row carries: a drawn specimen, the name, a three-word role
(`DIATOM CHAINS`, `GRAZER MIGRATES`) so the ecology arrives without a lecture,
and abundance on one absolute scale.

### The abundance scale — and where the honest ecology went

The number of individuals drawn in the water is a **rendering** decision, not an
ecological one: §1 compresses the count so a gyre is watchable rather than blank.
That compression is right for the water and wrong for a key.

So the key plate reports what the **model** believes, not what the renderer drew
— and that resolves the tension in §1 completely. The water view is allowed to
compress, because the honest numbers are one screen away. We never have to lie;
we just put the truth on the screen designed to carry it.

**The scale, as you described it:** 1 is the scarcest any drawn organism ever
gets, anywhere on the voyage, while still being present at all. Everything else
is a multiple. `93` beside *Chaetoceros* means there is ninety-three times more
*Chaetoceros* in this water than there is of the rarest organism at the place it
is rarest. One yardstick, valid across every species and every day of the three
years.

Three implementation decisions that make it work:

- **`A_REF` is measured, not chosen.** Stage 6 runs all 1018 days logging per-type
  abundance daily; `A_REF` is the smallest **7-day rolling mean** any type reaches
  while present. A rolling mean rather than an instantaneous minimum, because one
  straggler on one afternoon is noise — and *"the place it is rarest"* should be a
  place rather than a moment. The measured value is then two bytes in flash.
- **The bar is logarithmic**, with a tick at every decade. The range across the
  voyage is three to four orders of magnitude; on a linear bar everything except
  the current winner would be one pixel wide. The decade ticks are what stop a log
  scale being mysterious — you can see that a bar reaching the second tick means a
  hundredfold without being told.
- **Four characters, maximum**: `4.3`, `93`, `250`, `12K`, `>99K`. A decimal below
  10, where the difference between 1.2 and 4.3 is the whole story; no units above
  999, where nobody cares.

The nice consequence: a species that is *always* rare — Acantharia, say — reads
`2` or `3` forever, and its bar never leaves the first decade. That is true, and
saying it plainly is more interesting than a share-of-biomass bar that would have
shown it as a large fraction of nothing.

Above the list, the voyage block you asked for: position in degrees and minutes,
time at sea, time remaining, and **next port with days to run** — which is the
line people will actually look at. Plus a progress bar for the whole voyage with
a tick at every anchorage, so the *shape* of the voyage is visible at a glance:
long empty runs, then clusters of stops.

Two implementation notes worth recording, both learned by getting them wrong:

- Specimens need a **hand-set drawing radius per type**, not one derived from
  `EXTENT`. `EXTENT` is an isotropic separation radius; a *Chaetoceros* chain is
  compact across its axis and up to twelve radii long down it, so at a shared
  nominal size it sprawls straight across the name beside it.
- Seed each specimen's genome from its **row index**, not the RNG, or the
  drawings shimmer between frames.

At 34 px per row the plate holds **8 organisms** above the voyage block, which
comfortably covers the 5–7 types typically present. In clean mode the voyage
block and footer drop away and it becomes a bare list of drawn organisms and
names — arguably the nicest of the three clean screens.

### Cadence — with one honest reservation

Your proposal: `10 s map → 20 s water → 10 s key → 20 s water`, a 60-second loop.

That is **33% of the time not showing water.** It is the right cadence for a
room with people in it — a visitor arriving at random will see the map or the
key within half a minute and understand the object immediately. It is probably
the wrong cadence for the thing sitting on your shelf for two years and ten
months, where the interruption arrives 1,440 times a day and the aquarium
becomes a slideshow.

So: **make it two named cadences and let the button choose.**

**Timings, concretely.** These are set by how long each screen actually needs,
not by round numbers.

*The map needs 12 s minimum and wants 18.* The dolly is the whole point of it,
and a dolly cannot be hurried: ~2 s holding the globe so the eye registers
"Earth", 5–7 s moving, 5–8 s at chart scale to find the coast and the ship. Below
about 12 s it reads as a flash rather than a move, and the design collapses.

*The key plate wants 15 s and tolerates 11.* Five to seven rows at roughly 2 s
each to scan a specimen and a name, plus the voyage block. It is static, so there
is no motion to wait out — this is purely reading time.

*Dissolves are 1.5 s each*, which is slow enough to read as an engraving being
replaced rather than a screen wipe.

| | `GALLERY` (default) | `EXHIBIT` (yours) |
|---|---|---|
| water | **18 min** | **20 s** |
| dissolve | 1.5 s | 1 s |
| map — globe hold | 3 s | 2 s |
| map — dolly in | 7 s | 5 s |
| map — chart hold | 8 s | 5 s |
| dissolve | 1.5 s | 1 s |
| water | **18 min** | **20 s** |
| dissolve | 1.5 s | 1 s |
| key plate | 15 s | 11 s |
| dissolve | 1.5 s | 1 s |
| **cycle** | **36 min** | **67 s** |
| **chrome** | 39 s, **1.8%** | 27 s, **40%** |

`EXHIBIT` comes out at 40% rather than your 33% because the map is given 12 s
instead of 10 — the extra two seconds are the difference between the dolly
landing and not.

The button (`m` in the preview, KEY on the panel) does the obvious thing: one
press advances to the next screen immediately; **a press also drops the piece
into `EXHIBIT` for five minutes and then it quietly returns to `GALLERY`.** So
the object is contemplative by default and becomes explicable the moment someone
asks about it — which is precisely the situation you described with parents in
the room.

Ordering within the loop matters more than it looks. `map → water → key → water`
is right: map and key are both "information" screens and should never be
adjacent, or the piece has a long chrome stretch and then a long water stretch
instead of alternating.

One cost to note: the ST7305 draws ~40 µA at 1 Hz and ~5 mA at 51 Hz, and
dissolves need the fast rate. `EXHIBIT` spends roughly 13% of its time
transitioning, so it is meaningfully more expensive than `GALLERY`. Irrelevant on
mains; relevant if this ever runs on a cell, and another argument for
`EXHIBIT` being a temporary mode rather than the default.

---

## 7c. The ocean, in place — **done**

`ocean.py` + `data/ocean.bin`. 475 kB of uint8 in flash: twelve monthly steps
of sea surface temperature and mixed layer depth, four seasonal steps of
nitrate, and two static fields, on a 2° grid.

**2°, not the 5° the plan assumed.** Five degrees is right for temperature and
wrong for nutrients, which is the field with all the structure and the only one
the piece is really about. Measured, surface nitrate in austral winter, mmol/m³:

| | 1° | 2° | 3° | 5° |
|---|---|---|---|---|
| Peru 15°S | 9.2 | 9.2 | 9.7 | 9.0 |
| Benguela | 6.9 | 6.1 | 7.0 | **3.8** |
| Equatorial Pacific | 5.1 | 4.8 | 4.3 | **3.5** |
| S Pacific gyre | 0.0 | 0.0 | 0.0 | 0.1 |

Five degrees loses nearly half the Benguela, because an eastern-boundary
upwelling is a 100 km strip and a 550 km cell averages it with 450 km of ocean
that is not upwelling. 475 kB out of four megabytes is not a real cost.

**Two fields are computed rather than downloaded.** `shelf` is distance to the
coastline, taken from the same Natural Earth data the map already uses — a
469 MB bathymetry download to answer "is this coastal" would be absurd when the
answer is already in `data/coast.bin`. It also carries the iron, since shelf
sediment and continental dust are where iron comes from, which is why the
Southern Ocean blooms downstream of South Georgia and nowhere else. `iron` is
the three hand-drawn HNLC boxes, as planned.

**Three things went wrong, all worth recording:**

- **Coverage gaps read as land.** WOA nutrients are ship casts, not satellite,
  so there are ocean cells with no nitrate — and quantised naively they became
  the land sentinel, which the reader cannot distinguish from "not ocean". The
  track plot had a hole in the nitrate exactly where Drake rounded the Horn.
  Every field is now nearest-neighbour filled over the ocean mask before
  quantising. Zero missing days in 1,019.
- **The iron shelf term was far too generous.** At a 400 km e-folding the Drake
  Passage came out at an iron ceiling of 0.63 — comfortably enough to bloom, in
  the stretch of water most famous for not blooming. 180 km fixes it.
- **The gyres bloomed.** `K_S` was 0.45, under half the published value for a
  large diatom (1.25 mmol/m³, Litchman 2006) and low enough that a subtropical
  gyre saturated it; and the deep-nitrate floor of 2.0 was two orders above real
  gyre surface nitrate. With `K_S = 1.2` and a floor of 0.3 the contrast appears:
  **gyre biomass 4, Humboldt 46.** Emergent, not prescribed.

The result is in `docs/upwelling_vs_gyre.png` and it does something better than
the contrast: **the gyre carries more taxa than the upwelling** — 6 against 3 —
which is exactly what Barton et al. and Follows & Dutkiewicz report, and which
nothing in the model was told to do.

**What is still wrong**, and belongs to Stage 4 rather than to more tuning: the
warm oligotrophic tropics — the Coral Triangle, the Panama Bight — are still too
productive. Temperature roughly triples the growth rate at 30 °C, which is
correct (it is under the Eppley envelope), and a single implicit species has no
way to express that the organisms which can exploit that warmth in nutrient-poor
water are *small* ones with low half-saturation. That is precisely what the trait
table is for. Tuning it further now would be fitting one species to a job that
needs sixteen.

---

## 7d. The traits — **done**

`TRAITS` in `drift.py`, and `tools/check_biogeography.py run 5` is the gate.

Everything is derived from **size**, using the published exponents rather than
invented numbers: `mu_max ∝ V^-0.25`, `K_N ∝ V^+0.30`, `sink ∝ V^+0.39`,
`respiration ∝ V^-0.25`. Diatoms get a higher intercept, not a different
exponent. Grazing is a log-normal size kernel with per-type predator:prey
ratios from Hansen et al. 1994 — copepods 18:1, ciliates 8:1, dinoflagellates
3:1 — so a new organism's place in the food web is decided by how big it is.

**There is no column saying where anything lives.**

Four failures on the way, each of which was the model saying something true:

1. **Founder effect, mistaken for competition.** The reseed only fired when the
   population was already depleted, so once the panel was full nothing new could
   arrive. *Chaetoceros* held the tropics at 100% for two hundred days on water
   *Navicula* should have taken. Arrivals are now continuous, and the cap is paid
   for afterwards by whichever individuals have the lowest vigour. A hard cap is a
   rendering constraint; making it cull the least fit is the only way to stop it
   behaving like an ecological one.
2. **The smallest type took 91% of the voyage.** Pure allometry says a small cell
   has both a higher growth rate *and* a lower half-saturation — it is better at
   everything, and with size as the only axis it wins the ocean. What a large
   diatom buys with its size is not physiology, it is **not being eaten**. So
   `defence` became a trait — and it is a happy convergence, because the features
   that make an organism worth drawing (setae, frustule, horns, spines) are the
   same ones that make it hard to swallow.
3. **The mixotrophs could not hold the gyres**, because there was nothing for them
   to eat and the microzooplankton had no prey at all — the smallest resolved cell
   was a 30 µm diatom and the entire small-cell class was missing. Picoplankton now
   exist as a scalar per depth bin with the lowest half-saturation in the model,
   competing for the same nitrogen, grazed by everything below copepod size, and
   rendered through the stipple exactly as §1 planned. They are what a subtropical
   gyre is actually made of.
4. **The three diatoms were one organism with three drawings** — optima of 12, 14
   and 15 °C with widths of 12–14. At 8, 15 and 20 °C with narrow widths they are a
   cold bloom-former, a temperate generalist and a subtropical shelf diatom.

**Result**, median over five seeds:

| | | |
|---|---|---|
| cool productive coast → diatoms | 79% | > 55% |
| oligotrophic gyres → mixotrophs | 67% | > 35% |
| Southern Ocean is not a diatom bloom | 48% | < 80% |
| Indian Ocean gyre → mixotrophs | 70% | > 30% |
| effective types (inverse Simpson) | 3.20 of 5 | > 2.30 |
| distinct dominants | 5 | ≥ 4 |
| changes of dominant across the voyage | 15 | |

The checker judges the **median over five seeds**, which matters more than it
sounds: the first four runs gave effective-type counts of 2.45, 2.83, 3.20 and
3.66, and a threshold set anywhere in that range would have passed or failed on
luck. The thresholds are set to catch a regression, not to be cleared by the
best run.

`docs/biogeography.png` is the payoff: southern Chile as a *Chaetoceros* chain
bloom, the Humboldt as a *Navicula* smear thick with grazers, and both gyres as
sparse radiolarian-and-*Ceratium* assemblages over a heavy picoplankton stipple.

---

## 8. Morphology roster

Sixteen types. Chosen for silhouette separation at ~20 px as much as for ecology,
because two organisms that read the same are one organism and a waste of flash.

**Keep (7, already built):** radiolarian, *Coscinodiscus*, *Navicula*,
*Chaetoceros* chain, *Ceratium*, copepod, tintinnid.

### Size, and how small a cell can be

Measured rather than guessed, by rendering each morphology at descending radii
and counting ink. **Below r ≈ 3.0 every one of them collapses into a blob** —
the radiolarian loses its spines, the centric loses its central pore, the
tintinnid stops being a cone. At r = 3.0 all seven survive, and a radial form is
about 7 px across.

Marine snow is 1–2 px. So there is a clean **threefold gap** between the
smallest legible organism and the largest speck, which is what keeps them two
categories rather than a continuum. `R_MIN = 3.0` is now a hard floor in
`visual_radius`, applied before the fade so an arriving cell still grows into
place.

That answers the question of whether smaller cells are possible: **yes, down to
about 7 px across, and no further.** It also says which of the new organisms can
be small ones — a coccolithophore at 5–8 px sits exactly on the floor and is
still unmistakable, because its tell is a scalloped edge rather than an internal
structure that has to be resolved.

**Add (9), plus 3 small forms):**

| Organism | Geometry, for the drawing function | Water |
|---|---|---|
| **Coccolithophore** (*Emiliania*) | sphere whose *edge* is broken into 10–14 shallow scallops. 10–20 overlapping oval placoliths, imbricated like roof tiles. The scalloped edge is the entire tell — do not draw a smooth circle. | gyre |
| **Trichodesmium** | two forms. Tuft: 20–200 parallel filaments, bundle 8:1–15:1, ends frayed not pointed. Puff: 100–300 filaments radiating, slightly wavy. | warm gyre |
| **Acantharia** | **exactly 20 spicules**, as 10 diametral rods through one shared centre (Müller's law). Body = inner 20–35% of diameter; spicules 2–3× body radius, perfectly straight. Body:spike ratio is what separates it from everything else spiky. | gyre |
| **Salp chain** | repeating hooped-barrel-plus-dot units. Solitary 2:1–2.5:1 with 8–9 muscle hoops; aggregate 4–6 hoops, chains of 4–80. **The most distinctive silhouette on the whole list** — nothing else looks like it. | Southern Ocean, gyre |
| **Rhizosolenia** | needle, aspect ratio **10:1–20:1** (the most elongated thing in the set), one axial spine per pole, chains end-to-end. | upwelling |
| **Corethron** | stubby barrel 1:1–1.5:1 with a coronet of 10–20 spines from **each** end face, 2–5× cell diameter. "Two spiky pom-poms joined by a stub." | Southern Ocean |
| **Ornithocercus** | small body (25–35% of the structure) engulfed by two enormous fenestrated sails with 5–10 radial ribs each, total 2–3× body diameter. The most ornate, most asymmetric outline available. | warm gyre |
| **Krill** | aspect 5–6:1, 6 abdominal segments, tail fan 1.5–2× body width, two stalked-eye bumps, short antennae. At 20 px: segmented rod + fan, versus the copepod's teardrop + whip antennae. | Southern Ocean |
| **Foraminiferan** (*Globigerina*) | 4–5 overlapping circles in a ~90° spiral, each 1.3–1.4× the last, overlapping by 40–50%. Lobed grape-cluster. | gyre |

**And three genuinely small forms**, drawn at or near the r = 3 floor, to widen
the size range downward as asked. Each is chosen because its identifying feature
is an *outline* rather than an interior detail, which is the only kind of feature
that survives at 7 px:

| Organism | Geometry | Water |
|---|---|---|
| **Coccolithophore** (*Emiliania*) | listed above; belongs here too. A circle whose edge breaks into 10–14 shallow scallops. At r = 3 the scallops are 1 px notches and still read. | gyre |
| **Small flagellate** (cryptophyte / *Micromonas* type) | teardrop, aspect 1.6:1, two flagella of 1.5× body length trailing from the narrow end. At r = 3 it is a dot with two hairs — and two hairs is enough to say "alive" rather than "detritus". | everywhere, dominant in gyres |
| **Thalassiosira** | small centric, cells linked into a straight chain by a single central thread, 3–6 cells. The *thread* is the tell, not the cell: a dotted line of discs reads at any size. | coastal, spring bloom |

Together with `R_MIN`, these take the size range from roughly 4:1 to 6:1 and put
real organisms at the bottom of it — which matters more for the gyre than the
upwelling, since small cells are exactly what wins there.

**Deliberately not included**, because they collide with something already in:
*Noctiluca* (a perfect smooth circle — collides with the coccolithophore, and the
coccolithophore is more useful); *Hastigerina* and *Rhabdosphaera* (both "small
body + radiating spikes" — the set already has the radiolarian and Acantharia in
that slot, and a third would turn the group into mush); *Phaeocystis* (soft
dotted blob — reads as noise at 20 px); pteropods (lovely, genuinely distinct,
but they are not really plankton the model simulates — hold as a candidate).

**Reference plates**, all public domain: Haeckel *Kunstformen* Tafel 21
(Acantharia — this is the one, not Tafel 50), Tafel 2 (Globigerina), Tafel 4 and
84 (diatoms), Tafel 56 (Calanus). Haeckel's *Challenger* Radiolaria report Part I
is titled "Porulosa (Spumellaria and Acantharia)" and is the primary source for
spicule arrangement. Schütt, *Die Peridineen der Plankton-Expedition* (1895) for
*Ornithocercus*, *Dinophysis* and the full range of *Ceratium* horn variants.
*Kunstformen* has no coccolithophore, salp or krill plate.

**One rule to enforce:** reserve the picoplankton dither pattern exclusively for
picoplankton. If that exact density is ever reused as shading or texture on an
organism, it stops being a legible semantic layer and becomes noise.

---

## 8b. Other voyages — **done**, and it changes what the object is for

You want to make several of these as gifts. That turns a fixed track into a
parameter, and it is a small refactor with a large consequence.

`Voyage` is now a container — title, subtitle, departure, waypoints, notes —
and `VOYAGES` is a registry. `Track(voyage)` takes one. **The ecosystem never
learns which voyage it is on**, which is what makes this cheap: it only ever
sees a latitude, a longitude and a day number. Adding a voyage is writing a
table and registering it. On the hardware it is a build-time constant, so the
others cost nothing.

Two are in: **Drake** (Golden Hind, 1577–80, 1018 days, 35,789 nm, 20% at
anchor) and **Darwin** (HMS *Beagle*, 1831–36, 1816 days, 39,535 nm, 30% at
anchor).

The Beagle is the right second one, and not only because it's famous. Darwin
towed a plankton net off the stern for much of the five years and wrote about
what came up in it, so of every voyage that could go in this frame it is the
one where the organisms are not a conceit. It also crosses water Drake never
saw — the Galapagos, Tahiti, New Zealand, the Australian bight, Keeling — so
two of these side by side show visibly different oceans rather than the same
one twice.

**Candidates for the rest**, in order of how different the ocean would look:

| Voyage | Why it earns a box | Watch out for |
|---|---|---|
| **Cook, *Endeavour* 1768–71** | Your Australia one. Tahiti, the transit of Venus, New Zealand circumnavigated, the east coast, the Barrier Reef. Ocean nobody else on this list crosses. | Well documented, so the track is easy and long. |
| **Magellan–Elcano 1519–22** | The first. Ends with 18 of 270 men alive, which the card can say plainly. | The Pacific crossing is 99 days of nothing — even emptier than Drake's. |
| **Tasman 1642–43** | Discovered Tasmania and New Zealand, and the Southern Ocean legs are the most productive water on any of these tracks. | Short; would run in under a year. |
| **Shackleton, *Endurance* 1914–17** | The Weddell Sea and the *James Caird*. Krill, salps and Corethron are already in the roster and it is the only track that would be dominated by them. | The ship is beset and drifting for ten months — which the model handles, because drifting is just a slow track. |
| **Slocum, *Spray* 1895–98** | First solo circumnavigation. A quieter, more personal object. | |

**The card** — `tools/make_card.py <voyage>` emits the chart and a Markdown
card. The chart is the **whole track on one globe**, drawn with the same 1-bit
renderer the panel uses, which makes the paper the *complement* of the object
rather than a picture of it: the panel is always centred on the ship and never
shows the voyage entire. The card carries the facts, the notes on where the
record is thin, and the section headed *What is honestly wrong with it* —
because a gift that admits its own approximations is a better object than one
that doesn't.

---

## 8c. Advection — a proposal, not yet built

Your idea, recorded because I think it is the strongest structural change left
in the project and it subsumes several of the fixes already made.

At present the community at a position is **grown in place**: whatever is there
divides, gets eaten, and slowly turns over, with a trickle of immigration. That
is the right model for a moored instrument. It is the wrong model for a ship.

Drake makes 80–180 km on a good day. The water the panel is showing is
therefore **new water every day or two** — the community is overwhelmingly
*advected in* from ahead, not descended from what was there yesterday. Which
means the correct dynamic is a flush: cells enter at the leading edge, leave at
the trailing one, and the composition of what enters is set by what belongs in
the water the ship is entering.

What that would buy, beyond being right:

- **The lag disappears.** Composition currently trails the environment by the
  turnover time of the population, which is why the Humboldt takes a week to
  become a diatom smear after the ship arrives. With advection it changes as
  fast as the ocean under it does.
- **The founder effect goes away structurally** rather than by the immigration
  and cull machinery in §7d. Whoever fills the cap is flushed out shortly
  afterwards regardless.
- **Counts and ratios become directly controllable** at the inflow, which is
  the honest place to apply the §1 visual compression: you are choosing what
  arrives, not overruling what grew.
- **`Track.speed(day)` already exists and is already zero at anchor.** So the
  flush rate is a function we have: under way the water is replaced, at anchor
  it is sat in and the community develops in place — which is exactly the
  distinction the piece already makes on the footer, and it would become a
  visible difference in behaviour rather than only a caption.

The risk is that it makes the ecosystem a *display* of the climatology rather
than a model of it — if everything is imported, nothing is grown, and the NPZ
dynamics stop mattering. The balance point is that inflow composition should be
seeded from the environment but the **local dynamics still decide who thrives**,
so a bloom is still something that happens rather than something delivered.

Probably Stage 7, after the tuning pass has said what the current mechanism
actually gets wrong.

---

## 9. Stages

Each stage ends in something that runs. Nothing is ordered until Stage 3.

| | Stage | Deliverable | Effort |
|---|---|---|---|
| **0** | ✅ Clean mode, wheel speed control | done, committed | — |
| **1** | ✅ Track + course-up map | `voyage.py`, `mapview.py`, `data/coast.bin`, committed | — |
| **2** | ✅ Screen rotation | `screens.py` — Bayer dissolve, GALLERY/EXHIBIT cadences, `m` key. Voyage on one clock with the ecosystem. `--voyage` renders all 1018 days. | done |
| **3** | ✅ Ocean data pipeline | `tools/make_ocean.py`, `ocean.py`, `data/ocean.bin` (475 kB at 2°), `tools/plot_track.py` → `docs/ocean_track.png`. Environment wired to it. | done |
| **4** | ✅ Trait refactor | Trait table + allometry + defence + picoplankton. `tools/check_biogeography.py run 5` is the gate, and it passes. | done |
| **5** | ✅ New morphologies | Eleven added, roster of 18. Extents measured rather than guessed. All checks pass. | done |
| **5b** | ✅ Sea routing | `tools/make_landmask.py` + `tools/make_route.py`. Both voyages audit at zero land crossings. Build-time only. | done |
| **6a** | ✅ External validation | `tools/check_chlorophyll.py`. MODIS chlorophyll along the track. The result is in §10c and it is the most important thing the project has learned. | done |
| **7** | ✅ Advection | Your idea, and it took ρ from +0.070 to **+0.528**. See §10d. | done |
| **6** | The tuning pass | Run all 1018 days headless. Contact sheet, one panel per 30 days. Type composition vs. day as CSV. **Compare against MODIS chlorophyll climatology sampled along the track** — the falsifiable check. Then tune. | ~2 sessions |
| **7** | Port | `Canvas` in C, ST7305 driver, trait table and ocean data as `const` arrays. | the long pole |
| **8** | Enclosure | SolidWorks, print, finish. | |

**Why 4 and 5 were separate.** The temptation is to do them together, because new
organisms are the fun part and a trait refactor is not. Resist it: if the
biogeography comes out wrong and sixteen morphologies changed at the same time,
there is no way to tell whether the model is wrong or the drawing is. Stage 4
must be provably right with the existing seven silhouettes first.

**Stage 6 must include looking at the pictures, as a step.** The grazer mass
bug in Stage 5 — krill outweighing everything they ate, a food pyramid
standing on its point — was invisible to every metric in the checker and
obvious in one glance at a key plate. Metrics catch what you thought to
measure.

**Stage 6 is not optional and is bigger than it looks.** Everything before it is
mechanism; Stage 6 is the only stage where anyone finds out whether the object is
any good. Budget for it honestly.

---

## 10. What kills this

Ranked by probability × damage.

0. **Grazers eat the ocean to zero.** *Already happened, already fixed —
   recorded here because it is the template for the rest.* The first full-voyage
   sweep put the panel at exactly zero phytoplankton on day 120 off the Río de la
   Plata, and kept it near zero for fifty days. Not nutrients (surface N was 13.6)
   and not light (peak irradiance 0.54): the tropical bloom off Brazil built up
   eight copepods, the ship moved into cooler water, phytoplankton growth fell with
   temperature, and the grazers took six weeks to follow it down — eating
   everything in the meantime. That lag is the *same* mechanism the design relies
   on to produce blooms at all, which is why it cannot simply be damped. The fix
   was a Holling type III functional response: sigmoid in prey abundance, half
   saturating around ten agents, so below that the grazers stop finding prey and
   the population always keeps a seed. A refuge, not a floor — nothing is clamped,
   the ecology just stops being able to reach zero. Verified over five seeds
   sampling every simulated day: never below 5 individuals in 5,090 days.
1. **Competitive exclusion — one type wins everywhere.** The most likely failure,
   and the one that makes the whole feature pointless. Mitigations, all in the
   design: continuous seeding, per-individual growth jitter, the fast/slow grazer
   split, and genuinely varying environmental forcing. Detection: Stage 4's
   composition-vs-day CSV. If three types account for >90% of the voyage, stop and
   fix it before Stage 5.
2. **Sixteen morphologies become mush.** Every added organism raises the chance
   that two read the same at 20 px. Mitigation: the "deliberately not included"
   list above already dropped five candidates for exactly this reason, and each new
   draw function gets checked at final resolution before the next one starts.
3. **The chrome screens feel like an interruption.** At `GALLERY` pace it is ~3%
   of the time; at `EXHIBIT` pace, 33%. If it lands wrong it will be the only
   thing anyone notices. Mitigation: `GALLERY` as the default, `EXHIBIT` as a
   five-minute mode behind the button, event triggers so the map appears when
   there is something to see, never during a bloom, and a slow dissolve rather
   than a cut.
4. **The Pacific.** Nine weeks of the emptiest water on Earth on an invented
   track. Mitigation: §1. Test it *first* in Stage 6 — jump straight to day 610 and
   look at it before reviewing anything else.
5. **Stage 4 sprawls.** A trait refactor has no visible output and therefore no
   natural stopping point. Mitigation: the §6 checklist is the definition of done.
   Six rows pass, stage over.
6. **The ST7305 driver.** Patchy AliExpress sourcing, and the one mature driver
   needs 360 kB of PSRAM the Pico 2 does not have. Mitigation: order the panel
   early (Stage 2, not Stage 7) so a sourcing problem surfaces while there is still
   a year of software to write.

---

## 10d. Advection — **built, and it worked**

Your idea, promoted from §8c to Stage 7 because the satellite check said it was
the fix for the headline defect rather than a nice-to-have. It was.

| | Spearman ρ vs MODIS chlorophyll |
|---|---|
| before | +0.070 |
| **after** | **+0.528** |
| ceiling, set by the drivers themselves | +0.675 |

**The model now recovers 78% of the available signal**, from 10%.

How it works. Departures are **random** — advection does not care how fit a
cell is. Arrivals are **fitness-weighted**, evaluated with the same traits and
the same equations the resident cells use, because the water upstream has been
growing them; and never zero-weighted, because a model that only imports
winners cannot discover anything. The **number** of arrivals follows the
capacity of the water, so the count tracks the ocean while each individual's
mass — and which type actually thrives — stay with the local dynamics. A bloom
is still something that happens.

The flush rate is `0.55 × speed / 100 km/day`, a residence half-life of about
1.3 days under way and **zero at anchor**, so `Track.speed()` finally does
something visible: under way the water is replaced, at anchor the community
develops in place. The footer has said "AT SEA" or "ANCHORED" since Stage 2;
now it means something.

**This is also where §1's compression finally got implemented.** The plan said
"let the model's biomass be honest, then map it to individuals sub-linearly" —
and what actually existed was a hard agent cap with a cull, which is a
different thing and a worse one. Capacity is now computed uncapped and
compressed once, at the inflow, exactly as designed.

Two bugs found on the way, both by measurement:

- **Capacity used the best instantaneous growth *rate***, which is a different
  quantity from standing stock: a rate goes to zero in polar winter while the
  stock does not, and capacity collapsed to the floor over half the voyage. It
  now uses nutrient × iron × a light-and-temperature gate — deliberately the
  same combination the satellite says correlates at +0.68, because that
  measurement is the best evidence available for what sets standing stock.
- **Light was sampled instantaneously**, so any step landing near midnight
  concluded the ocean could support nothing. Daily mean, cached per simulated
  day.

Everything else improved as a side effect, which is the sign of a structural
fix rather than a tuned one:

| | before | after |
|---|---|---|
| effective types per panel | 3.87 | **5.15** |
| distinct dominants | 10 | **12** |
| small cells present | 55% of days | **78%** |
| *Trichodesmium* in warm gyres | 1.5% | **6.6%** |
| seed-to-seed spread on the diatom test | 38–91% | **46–69%** |

That last row is the quiet one. The community now tracks the water instead of
its own internal cycle, so it is far less sensitive to the seed — which is
what you would expect if the mechanism is right and not what tuning gives you.

And **looking at the pictures** caught the last one: the tropical gyres had
filled with *Euphausia*, a Southern Ocean animal, because heterotroph growth
never read the thermal niche that had been sitting in the trait table all
along. Only the phototrophs were using it.

---

## 10c. What the satellite said — **the headline result**

`tools/check_chlorophyll.py` compares model biomass against MODIS-Aqua
chlorophyll along the same track in the same months. It is the only check in
the project the model cannot influence: everything else asks whether I encoded
the literature correctly.

The comparison is **rank**, not value — model biomass is in arbitrary units and
chlorophyll is in mg/m³, and the claim the piece makes is about *ordering*, not
calibration. Spearman is the statistic for that, and it is invariant under any
monotone transform, so the visual compression in §1 cannot flatter or damage it.

**The result:**

| | Spearman ρ vs satellite |
|---|---|
| deep nitrate × iron | **+0.675** |
| sea surface temperature | −0.638 |
| deep nitrate | +0.661 |
| **model biomass** | **+0.026** |
| model agent count | +0.070 |

**The ocean data is right and the ecology destroys the signal.** The drivers
carry a strong, correctly-signed relationship to real chlorophyll; the
population's response to them carries none.

Three follow-ups narrowed it:

- **It is not noise.** Smoothing model biomass over 30, 50, 90 and 150 days
  moves ρ from +0.026 to −0.004. There is no signal being averaged out.
- **It is not the compression.** Spearman is rank-based; a compressive map
  changes nothing.
- **The response curve is monotone over most of its range** — binned by driver
  strength, model biomass climbs 9 → 30 across seven of eight bins. It then
  collapses to 8 in the top bin, which is cold, deep-mixed, nutrient-rich water.

That last one produced two real fixes, both using data already in flash. **A
shelf sea cannot mix deeper than the bottom** — the MLD climatology is an
open-ocean product and reported a hundred-metre winter mixed layer over sixty
metres of Patagonian shelf, so the model applied a deep-mixing light penalty to
one of the most productive stretches on the track. And **the Sverdrup term must
saturate**: once a column is fully mixed, mixing it harder changes nothing, but
the linear form was still climbing and taking 0.44/day out of a cell whose
maximum growth was 1.0.

**And the satellite overturned one of my own tests.** The checker asserted "the
Southern Ocean is not a diatom bloom" over days 180–270. Every sample in that
window is within **90 km of land** — Drake hugged the coast the whole way down,
so it is the Patagonian *shelf*, not the open Southern Ocean. Shelf water is
iron-replete, and MODIS reads **1.7 mg/m³** there on day 180, among the richest
readings on the whole voyage. The model blooming there is correct; the test was
wrong. It is now two tests: the shelf should be productive, and the *Pacific
crossing* — 440 to 750 km offshore, the only genuinely open-ocean stretch of the
entire track — should not bloom. Both pass.

### But ρ is still only +0.070, and that is the real finding

The fixes above are correct and they barely moved it. Which says the problem is
not a parameter.

A population with a **memory of weeks to months** — predator–prey cycles, cell
ages, founder effects, the cap and cull machinery — is being carried through
water that changes **every day or two**. Whatever the biomass is on a given day,
it reflects where the community is in its own internal cycle far more than it
reflects the water it is in. That is a timescale mismatch, and no amount of
tuning fixes a timescale mismatch.

**Which is exactly what §8c proposes.** The advection idea is no longer a nice
structural improvement — it is the fix for the headline defect, and the
independent check says so. It should be Stage 7 and it should be next.

The number to beat is **ρ = +0.070**, against a ceiling of **+0.675** set by the
drivers themselves. That is now a measurable target rather than a matter of
taste, which is the best thing this check has given the project.

---

## 10b. The clock — **decided**

The voyage runs on **the same clock as the ecosystem**. There is no separate
voyage rate to keep in step, and `Ecosystem.t` is simply days since Plymouth.

Default speed is **1 MIN/SEC**: a simulated day takes 24 real minutes and the
whole circumnavigation takes **17 real days**. Slow enough that nothing appears
to be happening while you watch it; fast enough that it has visibly moved
between one look and the next, which is the property that makes an object like
this worth having on a shelf rather than worth watching once.

The alternative — one voyage day per real day, 2 years 10 months — is a more
remarkable fact about an object and a worse experience of one. At that rate the
ship advances half a degree between breakfast and supper.

At day 1018 the piece starts again **with a fresh seed**, so the second
circumnavigation grows a different community in the same ocean. One line, and
it is the difference between a loop and a repeat.

---

## 11. Decisions still open

1. **Ecosystem persistence across a power cycle.** If the RTC survives and the
   state is written to flash occasionally, the piece resumes where it was. If not,
   every power cut restarts the voyage. Flash wear says write rarely; the concept
   says never lose the voyage. Probably: persist day number and RNG seed only, and
   let the community re-derive itself in a few simulated days.
3. **What happens at day 1018.** Start again identically? Start again with a new
   seed, so the second circumnavigation has a different community in the same
   ocean? The second is better and costs one line.
4. **Land at close zoom.** Outline only (Tudor-chart correct, very spare), or
   hatched/stippled fill at high zoom? Outline is safer; hatching would look
   magnificent and could easily look like a mistake.
