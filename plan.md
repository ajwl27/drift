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
channel. Sixteen types, chosen for silhouette separation as much as for ecology.
See §6.

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

## 8. Morphology roster

Sixteen types. Chosen for silhouette separation at ~20 px as much as for ecology,
because two organisms that read the same are one organism and a waste of flash.

**Keep (7, already built):** radiolarian, *Coscinodiscus*, *Navicula*,
*Chaetoceros* chain, *Ceratium*, copepod, tintinnid.

**Add (9):**

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

## 9. Stages

Each stage ends in something that runs. Nothing is ordered until Stage 3.

| | Stage | Deliverable | Effort |
|---|---|---|---|
| **0** | ✅ Clean mode, wheel speed control | done, committed | — |
| **1** | ✅ Track + course-up map | `voyage.py`, `mapview.py`, `data/coast.bin`, committed | — |
| **2** | ✅ Screen rotation | `screens.py` — Bayer dissolve, GALLERY/EXHIBIT cadences, `m` key. Voyage on one clock with the ecosystem. `--voyage` renders all 1018 days. | done |
| **3** | Ocean data pipeline | `tools/make_ocean.py`, `data/ocean.bin` (127 kB), `Ocean` class, replacing the latitudinal stopgap. **Deliverable: a plot of SST/MLD/nitrate sampled along the whole track** — before any biology touches it. | ~1 session |
| **4** | Trait refactor | Constants → 16-row trait table. **Same 7 organisms, no new morphology.** Validate against the §6 checklist. This is the risky stage; do it alone. | ~2 sessions |
| **5** | New morphologies | 9 draw functions, one at a time, each checked at 20 px on the real canvas before the next. Each also needs a name, a three-word role and a `KEY_R` for the key plate. | ~2 sessions |
| **6** | The tuning pass | Run all 1018 days headless. Contact sheet, one panel per 30 days. Type composition vs. day as CSV. **Compare against MODIS chlorophyll climatology sampled along the track** — the falsifiable check. Then tune. | ~2 sessions |
| **7** | Port | `Canvas` in C, ST7305 driver, trait table and ocean data as `const` arrays. | the long pole |
| **8** | Enclosure | SolidWorks, print, finish. | |

**Why 4 and 5 are separate.** The temptation is to do them together, because new
organisms are the fun part and a trait refactor is not. Resist it: if the
biogeography comes out wrong and sixteen morphologies changed at the same time,
there is no way to tell whether the model is wrong or the drawing is. Stage 4
must be provably right with the existing seven silhouettes first.

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
