# Drift — what the panel is showing

A 1-bit reflective panel (300 × 400 px) showing a **vertical section of the water
column, surface to 1000 m, at the position of a ship** sailing a historical
circumnavigation in real time — Drake 1577–80, or the Beagle 1831–36. The fish
drawn are those the model expects in that water on that date. It runs two years
and nine months, then repeats.

| Source (2° grid) | Field | What it drives |
|---|---|---|
| NOAA OISST v2.1, 1991–2020 | SST, monthly | Thermal envelope; surface of *T*(*z*) |
| Ifremer / de Boyer Montégut | Mixed layer depth | Top of the thermocline |
| WOA23 | Nitrate, seasonal | Productivity (Monod, *K* = 8 mmol m⁻³) |
| NOAA ETOPO | Bottom depth | Bathymetric axis; the drawn seabed |
| Natural Earth 1:50m | Coastline | Distance-to-shore axis; the chart |
| FishBase | Depth, thermal range, length, trophic level | Species envelopes (35 spp.) |
| OBIS | Occurrences | **Validation only** — never an input |

Below the mixed layer *T* decays exponentially to ~3 °C (350 m scale height).
Iron is *not* data — three hand-drawn HNLC boxes, as a Liebig ceiling.

**Presence** is Relative Environmental Suitability (Kaschner *et al.* 2006; the
AquaMaps method): trapezoidal responses on bottom depth, temperature *at the
species' own living depth*, productivity and distance to shore, multiplied.
Suitability alone placed *Gadus morhua* in the Benguela — not wrongly, about the
water — so a separate **range table** gates dispersal history. **Abundance**
follows a trophic pyramid at 0.8 decades per level; epipelagic stock scales with
productivity while mesopelagic stock is near-uniform, so a gyre becomes a
populated deep layer under an empty euphotic zone. DVM interpolates FishBase
day/night bands on solar elevation.

**Deliberately not to scale.** Depth is logarithmic (0–200 m fills half the
panel). Size is compressed as *L*⁰·⁴ — ordering preserved, magnitude not. Counts
are 1–32, linear in modelled biomass per unit drawn area, so ink tracks biomass,
not numbers. The climatology is modern, the track is 1577, and pre-industrial
biomass is absent: this maps occupancy, not plenty. At 2° an eastern-boundary
shelf is unresolvable, so distance-to-coast carries that signal.

**Validation.** Ten regional assertions over several seeds — anchoveta dominate
the Humboldt and are absent from the gyre; the Benguela resembles it without
sharing an endemic. Against OBIS, 29 of 32 predicted dominants have records
where predicted; the three misses were real range errors, since fixed.
