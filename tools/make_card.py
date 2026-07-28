#!/usr/bin/env python3
"""
The card that goes in the box.

    python3 tools/make_card.py drake docs/card_drake

Emits two files: a whole-track chart drawn with the same 1-bit renderer the
panel uses, at print resolution, and a Markdown card with the facts and the
honest caveats. Same drawing, same conventions, so the paper and the object
belong to each other rather than the paper being marketing for the object.

The chart is the whole voyage at once -- which the panel itself never shows,
because the panel is always centred on the ship. That makes the card the
complement of the object rather than a picture of it.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from drift import Canvas, to_pil, text, text_width          # noqa: E402
from voyage import Track, VOYAGES, haversine                # noqa: E402
from mapview import Coast, Camera, draw_track, draw_limb, draw_graticule  # noqa: E402


CW, CH = 420, 420           # the card's chart is square; the panel's is not


def facts(track):
    wp = track.wp
    km = sum(haversine(wp[i][1], wp[i][2], wp[i + 1][1], wp[i + 1][2])
             for i in range(len(wp) - 1))
    still = sum(wp[i + 1][0] - wp[i][0] for i in range(len(wp) - 1)
                if (wp[i][1], wp[i][2]) == (wp[i + 1][1], wp[i + 1][2]))
    lats = [w[1] for w in wp]
    inferred = sum(1 for w in wp if w[3] == 0)
    return {
        "days": track.days[-1],
        "nm": km / 1.852,
        "km": km,
        "anchor_days": still,
        "anchor_pct": 100.0 * still / track.days[-1],
        "north": max(lats),
        "south": min(lats),
        "waypoints": len(wp),
        "inferred": inferred,
    }


def chart(track, coast, path, scale=4):
    """The whole track on one globe, centred so all of it is visible."""
    c = Canvas(CW, CH)
    c.clear()
    # centre on the mean position, which for a circumnavigation is nowhere in
    # particular -- so the globe is set to show the busiest hemisphere
    lats = [w[1] for w in track.wp]
    lat0 = sum(lats) / len(lats)
    lon0 = track.wp[len(track.wp) // 3][2]
    cam = Camera(lat0, lon0, 0.0, CW * 0.46)
    draw_graticule(c, cam, CW, CH, step=30)
    coast.draw(c, cam, CW, CH)
    draw_limb(c, cam, CW, CH)
    draw_track(c, track, cam, track.days[-1], CW, CH, ahead=False)
    for w in track.wp:
        if w[3] >= 2:
            x, y, vis = cam.project(w[1], w[2], CW, CH)
            if vis:
                c.circle(x, y, 2)
    to_pil(c).resize((CW * scale, CH * scale), 0).save(path)
    return path


CARD = """# {title}
## {subtitle}

*{days} days · {nm:,.0f} nautical miles · {anchor_pct:.0f}% of it at anchor*

![the track]({chart})

---

Inside the frame is a section of open water from the surface down to
{depth} metres, and a boat sailing this track at one day per {rate}. The fish
in it are not a decoration on the voyage — they are what the model works out
*should* be living in the water the ship is in, from the real temperature,
seabed depth, nitrate and iron of that patch of ocean in that month.

Nothing in it was told where anything lives. Each species carries the water it
tolerates — how deep, how warm, how productive, how far from a coast — and
presence falls out. When it fills with a shoal of anchoveta that is because
the model found the only water on the whole track that is shallow, cold and
very productive at once; when it thins to a few small things hanging below
two hundred metres, that is a subtropical gyre, and it is supposed to look
like that.

The depth axis is logarithmic, so the sunlit top two hundred metres gets half
the panel. Watch it at dusk: the deep scattering layer — lanternfish,
hatchetfish, and the most abundant vertebrates on Earth — rises through that
line towards the surface, and sinks again at dawn. It is the largest daily
migration of animals there is.

Press the button and it will show you the chart, and then a list of what is
currently in the water, with names.

---

### The track

{waypoints} dated positions, great-circle interpolated. It reaches {north}
in the north and {south} in the south. {inferred} of the positions are
reconstructed rather than recorded — mostly the long ocean crossings, where
nobody wrote anything down for weeks at a time.

{notes}

---

### What is honestly wrong with it

The ocean is the ocean **as it is now**. There is no climatology for the
sixteenth century, so this is a modern ocean under an old track — and the
piece leans into that rather than pretending otherwise.

The fish are drawn to be recognisable — a tuna is a tuna and an eel is an eel
— but they are compressed in size. At true scale a 14 cm anchoveta in a frame
this deep would be a third of a pixel and you would see only the sharks. The
order is honest: nothing is drawn larger than something genuinely larger than
it. The key plate prints the real length beside each name, which is where
that compression gets corrected.

**And there were far more fish then.** This shows where species live, not how
many there were. Cod, bluefin and the great sharks are at a fraction of the
biomass Drake sailed through, and no envelope model can put that back.

---

*Sources: NOAA OISST, NOAA World Ocean Atlas 2023, Ifremer mixed-layer depth
climatology, NOAA ETOPO, Natural Earth. Species envelopes from FishBase after
the method of Kaschner et al. 2006; swimming after Breder 1926 and Bainbridge
1958; occurrence cross-check against OBIS.*
"""


def build(key, stem, depth=1000, rate="24 real minutes"):
    track = Track(key)
    coast = Coast("data/coast.bin")
    os.makedirs(os.path.dirname(stem) or ".", exist_ok=True)
    png = stem + "_chart.png"
    chart(track, coast, png)
    f = facts(track)
    def dms(v):
        return "%d\u00b0N" % round(v) if v >= 0 else "%d\u00b0S" % round(-v)

    fields = dict(f)
    fields.update(
        title=track.voyage.title,
        subtitle=track.voyage.subtitle,
        chart=os.path.basename(png),
        depth=depth, rate=rate,
        north=dms(f["north"]), south=dms(f["south"]),
        notes=track.voyage.notes.strip())
    md = CARD.format(**fields)
    with open(stem + ".md", "w") as fh:
        fh.write(md)
    print("%s.md  +  %s" % (stem, os.path.basename(png)))
    print("  %d days, %.0f nm, %d%% at anchor, %d of %d positions reconstructed"
          % (f["days"], f["nm"], f["anchor_pct"], f["inferred"], f["waypoints"]))


if __name__ == "__main__":
    key = sys.argv[1] if len(sys.argv) > 1 else "drake"
    stem = sys.argv[2] if len(sys.argv) > 2 else "docs/card_" + key
    build(key, stem)
