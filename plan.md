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

## 10l. Legibility — **the type, the HUD, and a plate that moves**

Looked at from across the room at true size, the plankton and the chart read
and every word did not. Measured rather than guessed: the font was 3 × 5, so
five pixels tall, which on a 119 ppi panel is **1.07 mm**. A cap height wants
to be roughly 1/250 of the viewing distance to be comfortable — 4 mm at a
metre, 2 mm at half a metre. It was out by a factor of two to four.

### A font you can read

A new **5 × 7 face**, written as pictures rather than as column bitmasks,
because a font typed as numbers cannot be reviewed — you can only run it and
squint. It compiles to the same five bytes per glyph at import, and on the MCU
the compile happens at build time and what ships is the same `const` array.
Fifty-six glyphs, 280 bytes.

`text()` takes a `scale` that replicates each font pixel into a block, which is
the only enlargement a 1-bit panel can do — anything smoother needs grey it
does not have. Two sizes are in use:

| | px | cap height | chars across 300 px |
|---|---|---|---|
| `T_BIG` = 3 | 15 × 21 | **4.5 mm** | 16 |
| `T_MED` = 2 | 10 × 14 | **3.0 mm** | 25 |

Three new primitives came with it, all trivial in C and all earning their
place: `fill_rect` (a scale-3 glyph is 105 filled pixels — worth having as a
primitive rather than 105 calls to `px`), `clear_rect`, and `clip`.

`label()` is `clear_rect` then `text` — a caption over a chart is unreadable
if the coastline runs through the letters, and on 1 bit there is no tint to
put behind it, only paper or ink. So the label clears its own ground, which is
what a printed chart does with a legend box and for the same reason.

`fit_scale()` returns the largest size at which a string fits its column.
Species names run from SALPA to COSCINODISCUS and the column is one width, so
either the layout is designed around the longest name — wasting the plate on
every other row — or the type shrinks to fit. A real plate does the second.

### The HUD is deleted, not hidden

Nine lines of instrumentation at 1 mm was the only thing on the panel that
assumed a reader with their nose against the glass. It went, along with
`View.hud`. What is left on the water screen is four things, each big enough
to read from a sofa:

    the voyage          who is sailing          T_BIG, fitted
    AT SEA / ANCHORED   what is happening now   T_MED
    lat and lon         where                   T_MED
    the bar             how far through

### The key plate moves

At the old size eleven rows fitted. At a readable size **five** do, and the
census routinely runs to twelve or thirteen taxa. Three options: show the top
five and lie by omission; shrink the type back and lie about legibility; or
move.

It moves. A **slow eased pan** from the top of the list to the bottom, with a
hold at each end, over exactly the dwell the cadence gives it. Not a loop — a
loop has no beginning, so a visitor arriving mid-cycle never knows whether
they have seen the whole thing. A pan that starts at the top and stops at the
bottom has both ends, and the holds are what make it read as a considered
movement rather than a slipping belt. If the list fits, nothing moves at all,
which is the common case in a gyre.

The pan is driven from the cadence rather than tuned against it, so the two
cannot drift apart. The key's dwell went **15 s → 40 s** in GALLERY: two
seconds a row plus the holds, which is the same reading budget the old plate
had — it just has to be spent sequentially now.

Everything else on the plate was re-cut to fit the type rather than the other
way round. `TEXT_X = 56` is set by COSCINODISCUS: thirteen characters at
`T_BIG` is 234 px, which is exactly what `W - 10 - 56` leaves. Roles are
capped at nineteen characters — what the same column buys at `T_MED` — and
double spaces went, because they bought a typographic nicety that does not
survive being 3 mm tall. Specimens are drawn about 1.6× larger and then
**clamped** against `EXTENT`, which is what stops a Chaetoceros chain, eight
radii long, from lying across the species name.

The voyage block (elapsed, to go, next port) moved off the plate to the water
screen, which is where it belongs: that screen is up 98% of the time and this
one is up for forty seconds.

### The specimens swim

A key plate with static drawings is a poster. The whole argument for this
object over a print is that the organisms move, and the plate is where a
visitor looks hardest at any one of them — so it is the last place that should
be still.

The pose comes from **the same gait constants as the water** (§10h): the
tintinnid on the plate corkscrews at the tintinnid rate, the copepod hops at
the copepod rate, and the diatoms only turn in shear because diatoms only turn
in shear. Nothing here is decoration invented for the plate. The helix gets a
gentle surge a quarter cycle out of phase with its yaw, so it reads as
swimming rather than as a windscreen wiper; the hop gets impulse-then-decay,
which is the water's velocity curve one integration further on, because here
it is displacement being drawn.

One difference: these are **deterministic** where the water's are stochastic.
A specimen in a display case swims on the spot and comes back; a Poisson
process would have it wander off the row.

### What it cost

| | before | after |
|---|---|---|
| simulation step | 1.47 ms | 1.73 |
| render, water | 2.01 | 2.61 |
| render, chart | 8.41 | 11.62 |
| render, key plate | 1.65 | **3.53** |
| cadence-weighted frame | 3.53 | **4.42** |

The key plate more than doubled, which is the type: a glyph at scale 3 is 105
filled pixels where it used to be about 8. It is 0.7% of the cadence, so it
moves the average by nothing. At 20 fps the whole legibility pass costs about
two days of battery life on one cell — 25 down to 23 — which is the cheapest
thing bought in this project so far.

`docs/screens_legible.png` is every screen; `docs/key_pan.png` is the plate at
four points in its pan.

---

## 10k. The hardware — **the Waveshare board, and what it changes**

### Can it run from USB-C? Yes.

Read from the board's own schematic
(`files.waveshare.com/wiki/ESP32-S3-RLCD-4.2/ESP32-S3-RLCD-4.2-schematic.pdf`),
because the product page does not say and the question decides the whole
battery argument:

| | |
|---|---|
| **U7** | ETA6098 — a 2.5 A **switching-mode** Li-ion charger, not a linear TP4056 |
| **D1** | MBR230LSFT1G Schottky, USB reverse protection into the charger input |
| **L1** | 2.2 µH, 3 A — the charger is a buck, so it has a real output node |
| **M1** | 8205 dual FET **in series between that node and the 18650 holder** |
| **U2** | RT9193-33 LDO, input **VSYS**, output VCC3V3 |
| **Q1 / U3** | AO3401 P-FET load switch with a latch, on the PWR button and a GPIO |

The shape that matters: the buck output is the **system** node, and the cell
hangs off it through back-to-back FETs. That is a power path. USB-C feeds the
system and charges the cell at the same time — which is what the CHG LED
implies and what the topology confirms.

Two caveats worth knowing before ordering:

- **Without a cell fitted**, USB-only operation is *probable* but not proven.
  A buck charger regulating into an absent battery is chip-dependent, and the
  ETA6098 datasheet excerpt available does not state a battery-absent mode.
  Fit the 18650 and the question does not arise.
- **The load switch is latched and GPIO-controlled**, so plugging USB in may
  not by itself power the board up from off — expect a press of PWR. Fine for
  a prototype, and something the custom PCB should deliberately design out:
  **the shipping object must come up on power alone**, because a gift that
  needs a button pressed after a power cut is a gift that sits dark.

**So the cell becomes a UPS rather than the power supply.** For a piece
simulating a continuous three-year voyage that is worth more than the runtime:
it rides out power cuts, and §11's open question about persisting the ecosystem
across a power cycle mostly stops being urgent.

### The panel is 300 × 400, and one constant gets nicer — **done**

`W, H = 300, 400`, `PANEL_DIAG_IN = 4.2`, and the whole piece is now built for
the 4.2in RLCD. `docs/panel_300x400.png` is all five screens after the change.
Only one constant did not follow the panel: `R_GLOBE` was written down as
118.0 for the old width, and is now derived as `W / 2 - 2` so it cannot be
left behind again.

Consequences:

- `W, H = 300, 400`. Aspect goes 0.60 → 0.75, so every layout re-flows: the
  key plate rows, the HUD block, the progress bar. Nothing structural — the
  draw functions all take explicit coordinates — but it is an afternoon.
- **The globe limb radius becomes exactly 250.** `R = √(150² + 200²)` is a
  3-4-5 triangle scaled by 50, where 240 × 400 gave the awkward 233.238. The
  one place in this project where a hardware change makes the arithmetic
  prettier.
- 25% more pixels: render cost ×1.25, panel current ×1.25 (≈29.5 µA/Hz).

### Check which driver it actually is

Waveshare's page and its own resources folder say **ST7305**. Zephyr's board
port says **ST7306**. The ST7305 datasheet is titled *"264H × 320V"*, which
cannot address 300 × 400 — so Zephyr is probably right and Waveshare's
documentation is reusing the family name. It matters for Stage 8, since the
driver is the part being written by hand. Resolve it on the bench.

### ESP32-S3 versus RP2350, and it is not close

| | active (RF off) | sleep, RAM retained |
|---|---|---|
| RP2350 / Pico 2 | ~22 mA @ 5 V | **1.8 mA** |
| ESP32-S3 | 23.9 mA measured | **240 µA** |

Light sleep is what this piece needs — deep sleep loses RAM, and losing RAM
means losing the ecosystem every frame. **The ESP32-S3 idles ten times
lower**, and since §10j established that the sleep floor is the whole ball
game, that single figure is worth more than every frame-rate decision
combined.

One 18650, 300 × 400 panel:

| | 10 fps | 20 fps |
|---|---|---|
| RP2350, stock Pico 2 | 32 d | 23 d |
| ESP32-S3 dev board as bought | 13 d | 12 d |
| ESP32-S3, own PCB, light sleep | **60 d** | **34 d** |
| ESP32-S3, own PCB, tuned hard | 68 d | 36 d |

The dev board is the worst of the three because it carries an ES8311 codec, an
ES7210 ADC, two microphones, an RTC, a humidity sensor and a card slot, none
of it obviously power-gated — the 8 mA idle there is a guess and wants a meter
on it. It also does not matter, because that board will be on USB.

### What the custom PCB should drop, and keep

**Drop:** ES8311, ES7210, both microphones, the speaker header, the TF slot,
the humidity sensor. None of them appear anywhere in this piece, and on the
dev board they are most of the idle current.

**Keep:** the PCF85063 RTC and its backup cell. The voyage is a function of
absolute time; an RTC that survives a power cut is what makes the piece resume
its voyage rather than restart it, and it costs about 0.2 µA.

**Add:** power-on-by-power-applied rather than by button; a USB-C socket
placed where it can be hidden; and the 18650 as a hold-up cell rather than the
supply.

**Watch:** the ESP32-S3-WROOM-1-N16R8 has 8 MB octal PSRAM and the RLCD
examples require it for the frame buffer. 300 × 400 at 1 bit is 15 kB packed,
so the buffer itself is nothing; but if the vendor driver keeps a byte-per-pixel
shadow that is 120 kB, which still fits in 512 kB SRAM. `Canvas` is
byte-per-pixel today and would want packing on the way to C either way.

---

## 10j. Frame rate against battery life — **numbers, and which of them is soft**

`tools/power.py`, rewritten with measured frame costs and sourced hardware
figures. Full output in `docs/power.txt`.

### The frame

Measured on this machine at day 300, 43 agents:

| | CPython, ms |
|---|---|
| simulation step | 1.47 |
| render, water | 2.01 |
| render, chart | 8.41 |
| render, key plate | 1.65 |
| **cadence-weighted** | **3.53** total |

The chart is four times the cost of the water view and 0.8% of the GALLERY
cadence, so it is 3% of the render budget. Worth knowing; not worth optimising.

### The answer, on a stock Pico 2 and one 18650

| | duty | MCU | panel | total | days |
|---|---|---|---|---|---|
| 0.25 fps | 0.1% | 2.46 | 0.02 | 2.48 | 49 |
| 1 fps | 0.4% | 2.53 | 0.04 | 2.57 | 47 |
| 5 fps | 1.8% | 2.91 | 0.13 | 3.05 | 40 |
| 10 fps | 3.5% | 3.40 | 0.25 | 3.65 | 34 |
| 15 fps | 5.3% | 3.88 | 0.37 | 4.25 | 29 |
| **20 fps** | 7.1% | 4.36 | 0.49 | **4.85** | **25** |
| 51 fps | 18.0% | 7.35 | 1.22 | 8.57 | 14 |

Two hundred-fold in frame rate buys **three and a half times** the battery
life. That is the whole finding, and it is not the answer you would guess.

### Why: the sleep floor eats it

A stock Pico 2 idles at **2.4 mA** (1.8 mA measured at 5 V, converted to the
cell). At 1 fps the MCU is asleep 99.6% of the time, so essentially the entire
budget is idle current, and dropping the frame rate further is fighting a
number that has already stopped moving.

Fix the idle and the same span becomes a **seventeen-fold** lever:

| | stock Pico 2 | tuned board (0.27 mA idle) |
|---|---|---|
| 51 fps | 14 d | 18 d |
| 20 fps | 25 d | 43 d |
| 10 fps | 34 d | 76 d |
| 5 fps | 40 d | 124 d |
| 1 fps | 47 d | 252 d |
| 0.25 fps | 49 d | 312 d |

**Until the sleep current is dealt with, dropping the frame rate is fighting
the wrong number.** Deep sleep with proper power management measures 170 µA on
an RP2350; on a custom board with an LDO and the unused rails down it should
be better still.

### The panel is not the problem

| | MCU | panel |
|---|---|---|
| 1 fps | 98% | 2% |
| 20 fps | 90% | 10% |
| 51 fps | 86% | 14% |

The ST7305 draws about **24 µA per Hz** for a 240×400 panel — roughly 0.5 mA at
20 fps and 1.2 mA flat out. Reflective, so no backlight: being looked at is
free, which is most of why it was chosen. Every saving worth having is on the
compute side.

That figure is two independent numbers agreeing. The ST7302 (250×122) is quoted
at 30 µA at 4 Hz, i.e. 7.5 µA/Hz; scaled by pixel count (×3.15) that predicts
94 µA at 4 Hz for ours, and the ST7305's own published low-power figure is
"about 100 µA or less."

### The levers, at 20 fps

| | mA | days | |
|---|---|---|---|
| as it stands | 4.85 | 25 | |
| frame cost halved | 3.88 | 32 | 1.25× |
| tuned idle | 2.84 | 43 | 1.71× |
| both | 1.80 | 66 | 2.70× |
| both, and 10 fps | 1.04 | 111 | 4.65× |

Duty cycle is `frame_ms × fps` and does not care which factor you shrink — so
halving the frame cost is worth as much as halving the frame rate, and one of
them costs you the motion while the other costs you nothing to look at.

### What is soft

The **CPython-to-C factor** is the only number here that is neither measured
nor sourced. CPython is 30–70× slower than C; a 150 MHz M33 is ~45× slower than
a modern x86 core (225 DMIPS against ~10,000). Those roughly cancel, so the
working assumption is that a frame costs about the same wall-clock on the panel
as it does here — and the tool sweeps it 0.5×–2× rather than asserting it. At
20 fps that band is **18 to 32 days**. It wants measuring on hardware before
anyone believes it.

Not modelled: regulator loss at these currents (add 15–25% through a
buck-boost; an LDO from a single cell is often better despite the dropout);
wake-up cost (nothing at 20 fps, 5–10% at 0.25 fps); panel current on a fully
changing image; and temperature — a cell at 0 °C gives about 70% of its rating.
Li-ion self-discharge (83 µA on a 3000 mAh cell) **is** included, and below half
a milliamp it is a significant fraction that no design gets under.

### For the gift boxes

At 20 fps a single 18650 is **under a month**, which makes it a thing that
needs charging rather than a thing that hangs on a wall. Options, in order of
how much they change the object:

1. **Mains, as originally decided.** A USB-C socket and it never comes up again.
2. **Tuned idle plus 10 fps** — 76 days on one cell, 150 on two. A quarterly
   ritual, which is defensible for an object about a three-year voyage.
3. **1 fps on a tuned board** — 252 days, and no longer an aquarium.

This is the argument the first design conversation already had, and it came out
the same way: the piece was decided as mains-powered when the choice was
"moving, or slowly changing?" and the answer was "moving — you can watch it
drift."

---

## 10i. The console — **the development build proper**

`tools/tune.py` answered one question at a time and answered it well: four
panels, same seed, one parameter differing. But the parameters interact —
swimming speed against turn persistence against body lag against frame rate —
and four fixed panels cannot show an interaction. `tools/console.py` is the
whole thing on one screen.

    python3 tools/console.py

![the console](console.png)

**Ten live parameters**, each with a log or linear slider chosen to suit its
range, a tick showing its default, and keyboard nudge at three step sizes:

| | | |
|---|---|---|
| MOTION | swim scale, turn scale, body lag | the three from §10g and §10h |
| GAIT | helix yaw, helix rate, hop rate, hop coast, shear tumble | multipliers folded into the per-species tables, so the published ratios survive |
| PANEL | frame rate 0.25–51 fps, time 1 sec/sec – 1 day/sec | the panel's real range, both ends |
| SCENE | voyage day 0–1018, seed | which community you are looking at |

**All three screens**, on buttons and on keys 1/2/3 — water, chart, key plate —
with the map's zoom broken out as globe / dolly / chart so you can sit on the
globe and look at it rather than catching it in passing. Plate chrome and the
debug HUD toggle separately.

**Frame rate is real.** The window runs at 60 Hz; the panel steps and redraws
on its own clock, by exactly the interval that elapsed. So at 1 fps the
simulation genuinely takes one-second steps, which is what the device does —
it steps and draws in the same loop. You are shown 1 fps, not told about it.

**A/B on every parameter.** TAB deep-copies the live ecosystem into A and
splits the window. Both sides then step in the same loop, with each side's
globals re-applied immediately before it steps — which is the trick that lets
the two sides differ in *all ten* parameters rather than only the two that
happen to live on the `Ecosystem`. Same organisms, same places, same day.

**The measured consequence, live.** Under each panel: rotation per rendered
frame in degrees, mean speed in px/s, agent count, day, position, and whether
the ship is at sea. These are the §10h numbers computed as you drag. The eye
decides; the number is what gets written down and defended.

**True physical size.** `t`, or the 1:1 button. The panel is drawn at the
size it will actually be, which for any monitor less dense than the panel
means scaling *down* from 1:1, not up -- a 27in 1440p screen is 108.8 ppi
against a 2.7in 240x400 panel's 172.8, so the factor is 0.6297 and the render
is resampled rather than replicated. A soft resample is not a betrayal of the
1-bit look: below 1:1 the monitor cannot show every panel pixel, and the eye
at arm's length from the real panel is doing the same averaging.

The mode carries **a ruler**, because the ppi you compute from a monitor's
advertised size and resolution is right only if the desktop is at 100% scaling
and the OS is reporting real pixels, and neither is safe to assume. Hold a
ruler to the 100 mm bar, adjust the ppi slider until it agrees, and the panel
beside it is the size the object will be. The console prints the resulting
`SCALE` to paste into `drift.py`, which now accepts a fractional value and
switches to a smooth resample when it gets one. On Windows the console asks
for DPI awareness first, or a machine set to 125% scaling would be out by
exactly that.

For reference, at 108.8 ppi:

| panel | physical | on this monitor | SCALE |
|---|---|---|---|
| 240x400 at 2.7in (was) | 35 x 59 mm | 151 x 252 px | 0.6297 |
| **300x400 at 4.2in (now)** | **64 x 85 mm** | **274 x 366 px** | **0.9138** |

**Export.** `e` writes a paste-ready block to `docs/tuned_values.txt` — the
scalars as scalars, and the gait multipliers already folded into the
per-species dictionaries under the identifiers `drift.py` uses.

### What it costs the shipping file

Nothing. Not one line. The console sets `drift` module globals, which works
because `_swim` reads `BODY_TAU`, `TUMBLE_S`, `HELIX_YAW`, `HELIX_HZ`,
`HOP_HZ` and `COAST_S` at call time, and it sets `swim_scale`, `turn_scale`
and `time_compression` as instance attributes, which already existed. Reaching
into another module's globals is exactly the sort of thing a development build
is allowed to do and shipping code is not — and it is why this is a separate
file.

`tools/tune.py` stays. Four panels at once is still the better instrument for
a single parameter with a wide range; the console is the better instrument for
everything else.

---

## 10h. The jitter — **and it was a units bug, not a taste problem**

The observation, from across the room: *the cells jitter, changing direction a
lot, which makes them appear to be moving a lot more than their swim speed
alone.* Measured before anything was changed, with `tools/check_motion.py`:

| | drawn-body rotation per frame | path / net travel |
|---|---|---|
| *Micromonas* | **7.4°** | 1.65 |
| *Calanus* | 4.3° | 1.36 |
| *Ceratium* | 3.7° | 1.48 |
| *Ornithocercus* | 3.4° | **2.02** |
| *Euphausia* | 3.4° | 1.65 |
| *Salpa* | 2.6° | 1.01 |

At 20 fps, 7.4° per frame is **148° of body rotation per second** on a drawing
six pixels wide. The observation was not a matter of taste. It was a
measurement, made by eye, of something real.

### The cause

`SWIM_SCALE` divided every velocity. It did not multiply any duration. So the
organism translated at a fifth of its speed and turned at full rate, and per
body length swum it therefore turned `1/SWIM_SCALE` times as often as the real
animal — about four and a half times. Its path through the water was four and a
half times more crumpled than the animal's.

Which is exactly the observation, stated in the model's own terms: the rotation
was running at real time while the translation was in slow motion. Anything
"moving more than its swim speed" is, definitionally, motion that is not
translation.

The fix is one symbol. Slow motion means dividing every velocity by the factor
**and multiplying every duration by it**:

```python
v0 = bl * 2.0 * visual_radius(a) * slow       # px per second
tau = TURN_TAU.get(k, 10.0) / slow            # ... and the clock too
```

Then the path through the water is the real animal's path, shape for shape,
merely traversed slowly — which is the only version of this in which the
literature values still mean anything at all.

The seam, stated rather than hidden: this applies to self-propelled motion only.
Sinking, tumbling in shear and the tidal drift are the water's doing, not the
organism's, and their rate is set by the time compression. So `TUMBLE_S` is not
scaled and a diatom keeps turning at its own pace.

### The second cause, which was cosmetic and just as visible

The drawn body angle was assigned straight from the instantaneous heading:

```python
a.ang = a.head + math.pi
```

`head` is a random walk. Random walks have white increments — energy at every
frequency, including every frequency above the one at which rotation stops
reading as heading and starts reading as vibration. Worse, that high-frequency
component contributes almost nothing to where the cell actually goes: it
integrates away. The eye was seeing the whole spectrum and the trajectory was
responding only to the bottom of it. **Rotation with no travel attached is the
precise mechanical definition of "looks busier than it is."**

So the body now has its own angle, and steers toward the intended course at a
finite rate — a first-order lag, `BODY_TAU = 0.30 s`, which is both what a real
cell's turning is limited by and, conveniently, a low-pass filter. The model's
own white noise cannot reach the screen. Travel follows the body, not the
intention, so it cannot reach the trajectory either.

### The third thing, which was an opportunity rather than a bug

Rotational diffusion is a convenient abstraction, and it looks like one. Real
plankton have characteristic gaits, all long-documented, none of them white
noise. Now implemented:

- **Helix** — *Micromonas*, tintinnids, *Ceratium*, *Ornithocercus*. The
  flagellar beat is asymmetric, so the cell corkscrews. A helix seen edge-on is
  a sinusoid, and the panel is a flat section through the water, so this is the
  projection rather than an impression of one. Path speed unchanged; headway
  drops about a tenth, which is the real cost of corkscrewing.
- **Hop-and-sink** — *Calanus*, and salps by jet at a quarter the rate. Impulse
  against drag, fired as a Poisson process, velocity decaying with `COAST_S`.
  Mean speed is `impulse × rate × coast`, so setting the impulse from that
  identity keeps the average exactly right however the burst statistics are
  tuned. A copepod now darts about a body length and settles, roughly every two
  seconds. Real hops are not metronomic, which is why this is Poisson and not a
  sawtooth.
- **Cruise** — krill. Continuous pleopod beating, and they school, so `TURN_TAU`
  went from 14 s to 40 s. Krill are the straightest thing out there.

Every gait frequency is quoted in **animal** seconds and converted, so the whole
gait is in slow motion consistently — a 2 Hz hop becomes 0.44 Hz on the panel.

### After

| | rotation per frame | path / net |
|---|---|---|
| *Micromonas* | 7.4° → **1.4°** | |
| tintinnid | — → 1.3° | 1.48 → 1.31 |
| *Euphausia* | 3.4° → **0.3°** | 1.65 → 1.00 |
| *Ceratium* | 3.7° → 0.6° | 1.48 → 1.01 |
| *Ornithocercus* | 3.4° → 0.6° | **2.02 → 1.00** |
| *Calanus* | 4.3° → 0.6° | 1.36 → 1.02 |
| *Salpa* | 2.6° → 0.4° | 1.01 → 1.00 |

A five-fold reduction in shimmer, everything now under the 3°/frame threshold,
and mean speed in body lengths per second unchanged — which matters, because
that is the number tied to the literature and to the `SWIM_SCALE` tuning.

`docs/gaits.png` is the picture: sixty seconds of swimming with nothing else
acting, before and after, three individuals each.

### What the fixing turned up

- **A 138° snap.** The diffusive branch — taken at 1 DAY/SEC — reassigned
  `head` but not `body`, so the first frame after the speed control came back
  down was the entire population slewing through a large angle at once. Measured
  at 138° in one frame. One line.
- **The measurement was wrong twice before it was right.** Tortuosity computed
  on the horizontal axis alone reports exactly 1.00 for everything, because a
  1-D projection of a curved path only doubles back when the heading crosses the
  vertical. And the panel is a cylinder, so a cell crossing the seam reads as
  239 px of travel in one frame — which inflated speed and tortuosity for
  precisely the fastest organisms, i.e. the ones under investigation.
- **A frame-rate test that measured the test.** Path length sampled ten times a
  second chords across the bends and reads shorter than the same path sampled
  forty times, so a perfectly rate-independent model looks like it speeds up.
  Net displacement has no such artefact. On net displacement the three rates
  agree to a few per cent, and the largest residual falls on the organism whose
  heading decorrelates fastest — i.e. it is the estimator's variance, not the
  step size.
- **`visual_radius` scales with the fade-in.** A cell still fading in swims at a
  fraction of its own speed, which is right on the panel and useless in a
  comparison. `tools/plot_gaits.py` now only traces individuals at `vis > 0.9`.

### The new lever

`TURN_SCALE`, a multiplier on every `TURN_TAU`, default 1.0. At 1.0 the paths
are the real animals' paths and they are *straight* — over a minute, most of
them barely deviate, because a minute of panel time is only thirteen seconds of
animal time. Whether that reads as drifting or as marching is the same class of
question as `SWIM_SCALE` and `TARGET_FPS`, so it is settled the same way:

    python3 tools/tune.py turn

which is why §10g says three numbers now rather than two.

---

## 10g. The numbers that cannot be reasoned to — **the development build**

Almost everything in this piece was argued from a source. Growth rates come from
Edwards 2012, the temperature envelope from Eppley, predator:prey ratios from
Hansen 1994, swimming speeds in body lengths per second from the swimming
literature. That is a good way to build most of it, and it is why the model
survived contact with a satellite.

Three numbers are not like that.

**`SWIM_SCALE`** is the single global multiplier on all motion. The literature
fixes the *ratios* — a flagellate at 14 BL/s really is fourteen times as busy as
a copepod at 1.1 — but the absolute figure has to survive a translation the
papers never make: a 40 µm cell drawn 12 px across, on a panel refreshing at
some rate, viewed from across a room. There is no correct answer to recover.
There is only what looks like drifting rather than skittering.

**`TARGET_FPS`** is the same kind of number. The power model says what each
rate costs; it cannot say which one reads as *alive*.

**`TURN_SCALE`** is the third, added after §10h. The literature fixes the
decorrelation times and the slow-motion scaling fixes how they translate to the
panel; neither settles whether the result reads as drifting or as marching.

So all three are set by eye — but by eye done properly.

### Why four at once

The obvious tool is a slider: one panel, tune it up and down, stop when it looks
right. That tool is useless, and predictably so. Memory for motion is very poor.
Everything looks correct while you are adjusting it, because you are watching the
*change*, not the state; come back thirty seconds later and it looks wrong again.
You end up oscillating and calling the last position a decision.

`tools/tune.py` runs **four ecosystems side by side**, from the **same seed**,
stepped identically, differing only in the parameter under test. Same organisms,
same positions, same genomes — so the only thing your eye can be responding to
is the motion. The judgement then takes about four seconds instead of ten
minutes, and it is a real comparison rather than a comparison against a memory.

    python3 tools/tune.py            # swimming speed
    python3 tools/tune.py fps        # frame rate
    python3 tools/tune.py turn       # how far the paths wander

    left/right   shift the whole range      up/down   spread or tighten it
    1 2 3 4      choose a panel; prints the value to paste into drift.py
    space pause   r reseed   esc quit

In `fps` mode the window still runs at 60 Hz and each panel **holds its frame**
for `round(60 / value)` ticks. You are not shown a description of 8 fps, you are
shown 8 fps — including the stepping, which is the whole thing being judged.

`tools/swim_gif.py` renders the same comparison as an animated GIF for judging
away from the machine, and for arguing about later.

### Why it is a separate build

This is a development build. It never ships and it never ports. Putting live
tuning keys into `preview()` — which was the first attempt — would have meant
carrying comparison scaffolding into the file that becomes C, and `drift.py`'s
one job is to be portable. The whole cost of keeping it separate is three lines in
`drift.py`: `TARGET_FPS` and `TURN_SCALE` as named constants, and `swim_scale`
and `turn_scale` promoted from module constants to per-instance attributes so
four ecosystems can differ inside one process. All of it the shipping file
wanted anyway.

The spin-up in `tune.py` steps at `1/6` day rather than the simulation's usual
`1/24`. Four ecosystems reach day 420 in 17 seconds instead of 64. This is a
motion tool; it needs a *plausible* community to look at, not a numerically
careful one.

### What `SWIM_SCALE` actually means — and it is cleaner than expected

Worth writing down, because the arithmetic turns out to give the number an
honest interpretation rather than leaving it an arbitrary knob.

    v = bl * (2 * visual_radius) * SWIM_SCALE     # px per second

`2 * visual_radius` **is the drawn body length in pixels**. So the speed in
pixels per second, divided by the body length in pixels, is `bl * SWIM_SCALE` —
the organism moves `bl * SWIM_SCALE` body lengths per second *on the panel*,
against `bl` body lengths per second in the sea.

**`SWIM_SCALE` is therefore the fraction of true speed the panel shows.** 1.0
would be real time. The current 0.22 is **4.5× slow motion**; 0.12 is 8.3×;
0.07 is 14×.

This matters because the plate does not draw organisms to a common spatial
scale — Micromonas at 5 µm gets 3 px of radius and Euphausia at 6 mm gets 6.7,
a thousand-fold size range compressed into rather less than three-fold, because
otherwise you would see one krill and no phytoplankton at all. Once the spatial
scale is per-organism, pixels per second means nothing across the panel and
body lengths per second is the only invariant left. Which is, conveniently,
exactly the unit the swimming literature reports.

Measured at day 420 (the Humboldt, 35 agents), seconds to cross the 240 px width:

| | BL/s | drawn r | 0.07 | 0.12 | **0.22** | 0.38 |
|---|---|---|---|---|---|---|
| *Micromonas* | 14.0 | 3.0 px | 41 s | 24 s | **13 s** | 8 s |
| tintinnid | 8.0 | 5.9 px | 36 s | 21 s | **12 s** | 7 s |
| *Euphausia* | 3.0 | 6.7 px | 85 s | 50 s | **27 s** | 16 s |
| *Ceratium* | 2.0 | 6.4 px | 134 s | 78 s | **43 s** | 25 s |
| *Calanus* | 1.1 | 9.2 px | 169 s | 99 s | **54 s** | 31 s |
| *Ornithocercus* | 1.6 | 1.9 px | 553 s | 323 s | **176 s** | 102 s |
| *Salpa* | 0.6 | 6.0 px | 479 s | 279 s | **152 s** | 88 s |

Read the top row as the constraint. At 0.22 the fastest flagellate crosses the
whole panel in 13 seconds, which is faster than anything else in the piece by an
order of magnitude and is very likely the thing that reads as *hurrying*. At
0.12 it takes 24 s — still unambiguously moving, still visible from a sofa, but
now on the same timescale as a slow look at the panel rather than a fifth of one.

The bottom rows are the other constraint. At 0.07 *Ornithocercus* takes nine
minutes to cross and *Salpa* eight, which is functionally stationary; the whole
point of §10e was that a still panel is a dead panel. So the usable range is
roughly **0.10–0.16**, and the tool exists to choose inside it.

### The result

Pending — the values live in `drift.py` and get pasted back from the tool. What
the plan records is the method, because the method is the defensible part: these
two numbers are set by looking, and the tool exists so that looking is a
controlled comparison rather than an impression. The arithmetic above narrows
the range; it cannot close it.

---

## 10f. What the motion costs

`tools/power.py`. First-order, and every number in it is measured or from a
datasheet except one, which is flagged.

| | duty | MCU | panel | total | one 18650 |
|---|---|---|---|---|---|
| one frame a minute *(the original e-ink concept)* | 0.0% | 1.2 mA | 0.02 mA | **1.2 mA** | 103 d |
| 5 fps | 1.8% | 1.9 | 0.50 | **2.4** | 53 d |
| **10 fps** *(floor for the fastest swimmer to read)* | 3.6% | 2.5 | 0.99 | **3.5** | **36 d** |
| 15 fps *(assumed at the first design conversation)* | 5.4% | 3.2 | 1.48 | **4.7** | 27 d |
| 20 fps *(the preview's rate)* | 7.1% | 3.8 | 1.97 | **5.8** | 22 d |
| 51 fps *(the panel's maximum)* | 18.2% | 7.9 | 5.01 | **12.9** | 10 d |

**Three times the current, and an 18650 goes from about 100 days to about 36.**

Two things worth knowing:

- **The MCU dominates, not the panel.** At 10 fps the processor is 72% of the
  draw. So the lever is *frame cost*, not refresh rate — halving the render
  halves the duty cycle and nearly halves the total. If battery ever matters,
  optimise the renderer, do not slow the animation.
- **The weakest number is the frame cost**, extrapolated from a CPython
  measurement (1.48 ms sim + 2.09 ms render) on the assumption that
  interpreter overhead and the M33's slower clock roughly cancel. It wants
  measuring on real hardware before anyone believes it.

And the honest framing: **this was decided as a mains-powered object at the
very first design conversation**, when the question was "moving, or slowly
changing?" and the answer was "moving — you can watch it drift". The battery
figures are for the gift boxes, where 36 days on a cell is a perfectly good
answer and USB-C is a better one.

### The bug the question found

Asking about power surfaced something worse than a power problem. Swimming was
advancing with *simulated* time, so at the default 1 MIN/SEC the fastest
organism moved **65 px between frames**, and at 1 DAY/SEC, 2,853 px. It had
stopped being an organism and become noise, at every speed except real time.

Swimming now runs at **real** time regardless of the calendar — the same class
of deliberate lie as drawing a 60 µm diatom twenty pixels across, and forced by
the same thing: the speed control spans six orders of magnitude and swimming
does not. It sits at 1.1 px/frame at every setting, and stays in a sensible
ratio to the tidal drift at the default speed. The ecology is untouched, because
swimming is a rendering behaviour and no equation reads the horizontal
displacement it produces.

---

## 10e. Motion, and why the panel was still

Two things you noticed, both real, and both measurable before they were
fixable.

### At 1 sec/sec nothing moved, and you were right

Measured: the tidal current at 5 m is **0.0003 px/s**, the turbulent jitter the
same, and an organism took **twenty-five days to rotate once**. A cell moved
one pixel per hour. The panel was not slow, it was stopped.

And the numbers are *correct in metres*. A *Calanus* cruising at a few mm/s,
on a panel where 1 px is 15 cm of real depth, genuinely does move a pixel an
hour. The problem is that the panel **already magnifies size by about a
hundred thousand and does not magnify the depth axis at all** — it is
inconsistent by construction, and the only question is which scale the motion
should follow.

**It should follow the drawing.** A copepod rendered twenty pixels long that
moves a pixel an hour is inconsistent with its own picture, and the picture is
what the eye reads. So swimming speed is expressed in **body lengths per
second** — the one number that survives the magnification — and multiplied by
the drawn size:

| | body lengths/s | px/s | crosses the panel in |
|---|---|---|---|
| tintinnid | 8.0 | 21.7 | 11 s |
| krill | 3.0 | 6.7 | 36 s |
| copepod | 1.1 | 4.8 | 50 s |
| *Ceratium* | 2.0 | 3.5 | 69 s |
| salp | 0.6 | 1.2 | 197 s |
| diatoms, rhizarians | — | — | they do not swim |

The values are real, and the ordering is the interesting part: **ciliates are
the fastest things in the sea relative to their size**, dinoflagellates next,
and a copepod cruises at about a body length a second (it darts at a hundred,
but only for a tenth of a second at a time).

The implementation detail that matters: swimming is **ballistic below the
heading decorrelation time and diffusive above it**. That is not fussiness. The
speed control spans six orders of magnitude, and one piece of code has to be
right at both ends — at real time you watch a copepod swim; at a day a second
the same call must become a random walk with the correct diffusivity
`D = v²τ`, or the displacement per step diverges.

Motile organisms now also **face where they are going**, which replaced a
random spin and is both more correct and much more legible.

### The bunching at the sides

Measured at day 5: **56% of the population in 17% of the width**, and the
middle nearly empty.

Arrivals were spawning within five pixels of x=0 or x=W, on the reasoning that
water flows in from one side. That was defensible when immigration was one
cell a day. Advection made it twenty or thirty, and with a residual drift of
38 px/day against a residence half-life of 1.3 days, cells were carried out
again long before they reached the middle.

The edge model was wrong anyway. **The panel is a vertical slice and the ship
moves through it, not along it**, so new water fills the whole slice rather
than entering from one side. Arrivals are now uniform across the field, and
the distribution is flat.

Neither change moved ρ (+0.527) or any biogeography check, which is the point:
they are about how the water is *sampled and drawn*, not about what lives in
it.

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
