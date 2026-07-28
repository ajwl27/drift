#!/usr/bin/env python3
"""
DRAW  -  fish, procedurally, on a 1-bit panel.

Canvas only. Ports with everything else, and it is deliberately free of any
import from drift: a drawing function takes a canvas, a centre, a length, an
angle and a shape, and knows nothing about ecology, depth or the voyage.

ONE BODY WAVE, AND WHERE IT STARTS IS THE SWIMMING MODE.

Every fish here is drawn by the same function. The species differ in a body
profile, a tail, a fin set and a few marks -- and in one number, `wave`,
which says how far along the body the travelling wave begins:

    wave 0.80   THUNNIFORM       tuna, marlin, shark. The body is a rigid
                                 aerofoil; only the last fifth moves.
    wave 0.65   CARANGIFORM      the default. Rear third.
    wave 0.45   SUBCARANGIFORM   herring, cod. Rear half.
    wave 0.05   ANGUILLIFORM     viperfish, snoek. The whole animal is the
                                 wave.

That is not a convenient abstraction that happens to look right -- it is the
actual basis on which fish locomotion has been classified since Breder 1926,
and it is why a tuna and an eel are unmistakable from across a room at
fifteen pixels. Getting it from one parameter rather than four hand-animated
cycles is the whole reason it was worth doing this way.

THE SILHOUETTE IS THE SPECIES. At this size there is no colour, no texture
and no detail below a pixel, so everything a viewer can use to tell a
skipjack from a sardine is in the outline: how deep the body is, where it is
deepest, whether the tail is a crescent or a fork, whether there is a bill,
whether the eye is enormous. Those are exactly the characters a field guide
uses, for the same reason.
"""

import math

# --- tails ----------------------------------------------------------------
(LUNATE,      # tuna, marlin: a stiff crescent, the two lobes nearly meeting
 FORKED,      # herring, jack: a deep V
 TRUNCATE,    # cod: cut square
 ROUNDED,     # grouper: a fan
 HETERO,      # shark: upper lobe much longer than lower
 LANCET,      # grenadier, viperfish: tapers to a point, barely a tail at all
 ) = range(6)


class Form:
    """A body plan. Sixteen of these cover thirty-three species.

    All lengths are fractions of the total length, all heights fractions of
    the total length too -- so a Form is scale-free and one table serves a
    4 cm bristlemouth and a 10 m whale shark."""

    __slots__ = ("depth", "peak", "nose", "tail", "tail_h", "wave",
                 "dorsal", "dorsal2", "anal", "pect", "pect_ang",
                 "bill", "eye", "photo", "finlets", "barbel", "jaw")

    def __init__(self, depth=0.18, peak=0.32, nose=0.5, tail=FORKED,
                 tail_h=0.26, wave=0.65, dorsal=None, dorsal2=None,
                 anal=None, pect=0.10, pect_ang=0.5, bill=0.0, eye=0.030,
                 photo=0, finlets=0, barbel=0.0, jaw=0.0):
        self.depth = depth        # max half-depth
        self.peak = peak          # where along the body that maximum is
        self.nose = nose          # 0 pointed, 1 blunt
        self.tail = tail
        self.tail_h = tail_h      # half-span of the caudal fin
        self.wave = wave          # where the body wave starts -> swim mode
        self.dorsal = dorsal      # (u0, u1, height) or None
        self.dorsal2 = dorsal2
        self.anal = anal
        self.pect = pect          # pectoral fin length
        self.pect_ang = pect_ang  # radians below the horizontal
        self.bill = bill          # snout extension, as a fraction of length
        self.eye = eye            # eye radius
        self.photo = photo        # photophores along the ventral line
        self.finlets = finlets    # the little detached fins of a scombrid
        self.barbel = barbel      # chin barbel length (gadoids, stomiids)
        self.jaw = jaw            # protruding lower jaw with teeth


# --------------------------------------------------------------------------
# the body
# --------------------------------------------------------------------------

def _profile(u, f):
    """Half-depth at position u along the body, 0 at the snout, 0 at the
    tail base. A skewed hump: the peak sits at f.peak, which is what makes a
    tuna (peak 0.35, blunt) look nothing like an eel (peak 0.2, even).

    Raised to a power on each side rather than a plain sine, because a sine
    is symmetric and no fish is: the front of a fish is short and steep, the
    back is long and shallow, and that asymmetry is most of what reads as
    'facing that way'."""
    if u <= 0.0 or u >= 1.0:
        return 0.0
    if u < f.peak:
        t = u / f.peak
        # the nose parameter blends between a point and a blunt head
        return f.depth * (t ** (0.85 - 0.55 * f.nose))
    t = (1.0 - u) / (1.0 - f.peak)
    return f.depth * (t ** 1.15)


def _wave(u, f, phase, amp):
    """Lateral displacement of the midline at u.

    The wave travels backward down the body -- that is what pushes water
    astern and the fish forward -- so the phase term is `+u`, not `-u`. Get
    the sign wrong and the animal swims by pulling itself along with its
    nose, which reads, unmistakably and hilariously, as backwards.

    The envelope is quadratic from `wave` to the tail. Real amplitude
    envelopes are close to quadratic, and more to the point a linear one
    leaves a visible kink at the point where the wave starts."""
    if u <= f.wave:
        return 0.0
    e = (u - f.wave) / (1.0 - f.wave)
    return amp * e * e * math.sin(phase + 5.0 * u)


def draw_fish(c, cx, cy, length, ang, f, phase=0.0, amp=None, seed=0):
    """One fish, centred at (cx, cy), `length` pixels long, swimming toward
    `ang`.

    Below about eight pixels the fins and the eye are dropped and what is
    left is a body and a tail, because at that size drawing them puts three
    marks in one pixel and the result is a blob. The silhouette survives; the
    ornament is what goes."""
    L = float(length)
    if L < 3.0:
        return
    ca = math.cos(ang)
    sa = math.sin(ang)
    if amp is None:
        amp = 0.055 if f.wave > 0.7 else 0.075

    def tw(u, v):
        """Body coordinates to world. u runs 0 at the snout to 1 at the tail
        base; v is perpendicular, positive to the fish's left."""
        s = (0.5 - u) * L
        w = v * L
        return (cx + s * ca - w * sa, cy + s * sa + w * ca)

    detail = L >= 8.0
    fine = L >= 16.0

    # --- the outline -----------------------------------------------------
    n = 13 if L < 20 else 19
    upper = []
    lower = []
    mid = []
    for i in range(n + 1):
        u = i / float(n)
        d = _profile(u, f)
        m = _wave(u, f, phase, amp)
        mid.append((u, m))
        upper.append(tw(u, m + d))
        lower.append(tw(u, m - d))

    if f.bill > 0.0:
        # the bill is an extension of the midline forward of the snout, and
        # it is drawn as a line rather than as part of the outline because at
        # this width it IS a line
        bx, by = tw(-f.bill, mid[0][1])
        sx, sy = tw(0.0, mid[0][1])
        c.line(sx, sy, bx, by)

    c.polyline(upper)
    c.polyline(lower)

    # --- the tail --------------------------------------------------------
    u_t = 1.0
    m_t = _wave(u_t, f, phase, amp)
    bx, by = tw(u_t, m_t)
    h = f.tail_h
    if f.tail == LUNATE:
        # A CRESCENT IS A FORK CUT ALMOST TO THE ROOT, and that is the whole
        # of it. The first version built the two lobes out of four separate
        # strokes and a return curve, which at fifteen pixels stopped being
        # attached to the fish: the join was one pixel wide and the eye read
        # a floating crescent beside a blunt-ended body.
        #
        # One closed outline, notch at 0.02 rather than the fork's 0.07, tips
        # swept well aft. Fewer strokes, and it holds together at every size
        # the panel uses.
        t1 = tw(1.0 + 0.17, m_t + h)
        t2 = tw(1.0 + 0.17, m_t - h)
        notch = tw(1.0 + 0.02, m_t)
        c.polyline([(bx, by), t1, notch, t2, (bx, by)])
    elif f.tail == FORKED:
        t1 = tw(1.0 + 0.17, m_t + h)
        t2 = tw(1.0 + 0.17, m_t - h)
        notch = tw(1.0 + 0.07, m_t)
        c.polyline([(bx, by), t1, notch, t2, (bx, by)])
    elif f.tail == TRUNCATE:
        t1 = tw(1.0 + 0.13, m_t + h)
        t2 = tw(1.0 + 0.13, m_t - h)
        c.polyline([(bx, by), t1, t2, (bx, by)])
    elif f.tail == ROUNDED:
        pts = [(bx, by)]
        for i in range(7):
            a = -1.0 + 2.0 * i / 6.0
            pts.append(tw(1.0 + 0.14 * math.cos(a * 1.4), m_t + h * math.sin(a * 1.4)))
        pts.append((bx, by))
        c.polyline(pts)
    elif f.tail == HETERO:
        # shark: the upper lobe is much the longer, and the notch in it is
        # the single most recognisable thing about a shark's outline
        t1 = tw(1.0 + 0.30, m_t + h * 1.15)
        t2 = tw(1.0 + 0.13, m_t - h * 0.62)
        c.polyline([(bx, by), t1])
        c.polyline([t1, tw(1.0 + 0.17, m_t + h * 0.30), tw(1.0 + 0.20, m_t + h * 0.44)])
        c.polyline([(bx, by), t2, tw(1.0 + 0.10, m_t)])
    else:                                          # LANCET
        c.polyline([(bx, by), tw(1.0 + 0.10, m_t + h * 0.35),
                    tw(1.0 + 0.20, m_t), tw(1.0 + 0.10, m_t - h * 0.35),
                    (bx, by)])

    if not detail:
        return

    # --- fins ------------------------------------------------------------
    def fin(spec, sign):
        """A fin FOLLOWS THE BACK it sits on.

        The first version drew every fin as a triangle from one end of the
        base to the other via an apex, which is right for a short fin and
        badly wrong for a long one. A dorado's dorsal runs from just behind
        the head to the tail: as a triangle that is a single enormous wedge
        over the whole animal, and what it read as was a balloon rather than
        a fish. Sampled along the base with a bulge added to the body's own
        contour, the same three numbers describe a fin instead."""
        if not spec:
            return
        u0, u1, hh = spec
        span = u1 - u0
        n = 3 if span < 0.15 else (5 if span < 0.35 else 8)
        pts = []
        for i in range(n + 1):
            t = i / float(n)
            u = u0 + span * t
            d = _profile(u, f)
            m = _wave(u, f, phase, amp)
            # sin^0.6 rather than sin: a fin rises from its base faster than
            # a sinusoid and holds its height across the middle, which is
            # what makes a long dorsal look like a ridge and not a hill
            bulge = hh * math.sin(math.pi * t) ** 0.6
            pts.append(tw(u, sign * (d + bulge) + m))
        c.polyline(pts)

    fin(f.dorsal, 1.0)
    fin(f.dorsal2, 1.0)
    fin(f.anal, -1.0)

    if f.finlets and fine:
        # the detached finlets of a scombrid, above and below, between the
        # second dorsal and the tail. Tiny, and completely diagnostic.
        for i in range(f.finlets):
            u = 0.74 + 0.055 * i
            if u > 0.96:
                break
            d = _profile(u, f)
            m = _wave(u, f, phase, amp)
            for s in (1.0, -1.0):
                p = tw(u, s * d + m)
                q = tw(u + 0.030, s * (d + 0.022) + m)
                c.line(p[0], p[1], q[0], q[1])

    # --- pectoral --------------------------------------------------------
    if f.pect > 0.0:
        u = f.peak * 0.92
        d = _profile(u, f)
        m = _wave(u, f, phase, amp)
        root = tw(u, -d * 0.35 + m)
        tip = tw(u + f.pect * math.cos(f.pect_ang) * 0.9,
                 -d * 0.35 - f.pect * math.sin(f.pect_ang) + m)
        c.line(root[0], root[1], tip[0], tip[1])
        if fine and f.pect > 0.20:
            # a big pectoral is a surface, not a spar -- the flying fish and
            # the whale shark both need it filled out to read
            mid2 = tw(u + f.pect * 0.55, -d * 0.35 - f.pect * 0.30 + m)
            c.polyline([root, mid2, tip])

    # --- head ------------------------------------------------------------
    ue = 0.045 + 0.11 * f.peak
    de = _profile(ue, f)
    me = _wave(ue, f, phase, amp)
    ex, ey = tw(ue, me + de * 0.34)
    er = f.eye * L
    if er >= 1.6:
        c.circle(ex, ey, er)
        if er >= 3.0:
            c.px(int(ex), int(ey))
    elif er >= 0.7:
        c.px(int(ex), int(ey))

    if f.jaw > 0.0 and fine:
        # a protruding lower jaw with teeth showing: the viperfish, and the
        # reason it is the one fish on the panel that looks like a threat
        j0 = tw(0.0, me)
        j1 = tw(f.jaw, me - _profile(f.jaw, f) * 0.85)
        c.line(j0[0], j0[1], j1[0], j1[1])
        for i in range(3):
            u = 0.02 + 0.035 * i
            p = tw(u, me - _profile(u, f) * 0.30)
            q = tw(u, me - _profile(u, f) * 0.85)
            c.line(p[0], p[1], q[0], q[1])

    if f.barbel > 0.0 and fine:
        # Hangs DOWN and slightly forward, and it is short. Drawn long and
        # straight it stopped being a barbel and became a spear held out in
        # front of the animal -- which on the viperfish, the one fish here
        # that genuinely looks dangerous, read as a bug rather than a beard.
        d0 = _profile(0.04, f)
        b0 = tw(0.04, me - d0 * 0.85)
        b1 = tw(0.04 - f.barbel * 0.45, me - d0 * 0.85 - f.barbel * 0.55)
        c.line(b0[0], b0[1], b1[0], b1[1])

    # --- photophores -----------------------------------------------------
    #
    # The rows of light organs along the belly of a mesopelagic fish. They
    # are the reason a myctophid is called a lanternfish, they are how the
    # animal hides its silhouette from below, and on a 1-bit panel they are
    # the one mark that says 'this thing lives in the dark' without a word.
    if f.photo and detail:
        for i in range(f.photo):
            u = 0.24 + (0.62 * i / max(1, f.photo - 1))
            d = _profile(u, f)
            m = _wave(u, f, phase, amp)
            px, py = tw(u, m - d * 0.80)
            c.px(int(px), int(py))


# --------------------------------------------------------------------------
# the body plans
# --------------------------------------------------------------------------
#
# Sixteen forms for thirty-three species. Where two species share a plan they
# differ in the proportions that matter -- a skipjack is stubbier than a
# bluefin and both are scombrids -- and where a species is morphologically
# singular it gets its own.

SCOMBRID = Form(          # tuna: the fastest shape in the sea
    depth=0.155, peak=0.36, nose=0.55, tail=LUNATE, tail_h=0.15, wave=0.80,
    dorsal=(0.34, 0.47, 0.075), dorsal2=(0.58, 0.66, 0.045),
    anal=(0.60, 0.68, 0.042), pect=0.14, pect_ang=0.35, finlets=4, eye=0.030)

MACKERELISH = Form(       # slimmer, and the wave reaches further forward
    depth=0.115, peak=0.34, nose=0.40, tail=LUNATE, tail_h=0.13, wave=0.70,
    dorsal=(0.28, 0.40, 0.055), dorsal2=(0.56, 0.64, 0.038),
    anal=(0.58, 0.66, 0.036), pect=0.10, pect_ang=0.40, finlets=5, eye=0.032)

WAHOOISH = Form(          # very long, very fast, a low continuous dorsal
    depth=0.090, peak=0.30, nose=0.20, tail=LUNATE, tail_h=0.115, wave=0.78,
    dorsal=(0.20, 0.62, 0.030), anal=(0.66, 0.76, 0.030),
    pect=0.09, pect_ang=0.35, finlets=5, eye=0.024)

CLUPEID = Form(           # herring, sardine, anchoveta: compressed, deep
    depth=0.150, peak=0.38, nose=0.30, tail=FORKED, tail_h=0.13, wave=0.45,
    dorsal=(0.42, 0.56, 0.060), anal=(0.68, 0.80, 0.035),
    pect=0.09, pect_ang=0.55, eye=0.044)

ANCHOVYISH = Form(        # smaller eye is wrong for an anchovy -- it has a
                          # famously large one, and a blunt overshot snout
    depth=0.125, peak=0.34, nose=0.15, tail=FORKED, tail_h=0.12, wave=0.42,
    dorsal=(0.44, 0.56, 0.050), anal=(0.70, 0.82, 0.032),
    pect=0.08, pect_ang=0.60, eye=0.055)

CARANGID = Form(          # jack, trevally: deep, keeled, a hard fork
    depth=0.200, peak=0.33, nose=0.55, tail=FORKED, tail_h=0.15, wave=0.68,
    dorsal=(0.30, 0.40, 0.055), dorsal2=(0.48, 0.72, 0.050),
    anal=(0.56, 0.76, 0.045), pect=0.17, pect_ang=0.45, eye=0.048)

BILLFISH = Form(          # marlin: the bill, and the sail of a first dorsal
    depth=0.130, peak=0.30, nose=0.35, tail=LUNATE, tail_h=0.16, wave=0.82,
    dorsal=(0.26, 0.46, 0.115), dorsal2=(0.66, 0.72, 0.030),
    anal=(0.64, 0.72, 0.038), pect=0.15, pect_ang=0.70, bill=0.20, eye=0.030)

CORYPHAENID = Form(       # dorado: a blunt vertical forehead and a dorsal
                          # fin that runs the entire length of the animal
    depth=0.150, peak=0.22, nose=0.90, tail=FORKED, tail_h=0.175, wave=0.62,
    dorsal=(0.14, 0.82, 0.045), anal=(0.55, 0.82, 0.034),
    pect=0.10, pect_ang=0.50, eye=0.034)

EXOCOETID = Form(         # flying fish: the pectorals ARE the animal
    depth=0.105, peak=0.30, nose=0.35, tail=FORKED, tail_h=0.15, wave=0.55,
    dorsal=(0.66, 0.78, 0.045), anal=(0.68, 0.78, 0.035),
    pect=0.46, pect_ang=0.62, eye=0.050)

SHARK = Form(             # blue shark: slim, long pectorals, that tail
    depth=0.115, peak=0.30, nose=0.25, tail=HETERO, tail_h=0.14, wave=0.74,
    dorsal=(0.40, 0.52, 0.080), dorsal2=(0.72, 0.78, 0.028),
    anal=(0.74, 0.80, 0.026), pect=0.26, pect_ang=0.62, eye=0.028)

WHALESHARKISH = Form(     # broad, blunt, slow, and the head is a shovel
    depth=0.145, peak=0.24, nose=1.00, tail=HETERO, tail_h=0.15, wave=0.76,
    dorsal=(0.46, 0.58, 0.085), dorsal2=(0.74, 0.80, 0.030),
    anal=(0.76, 0.82, 0.028), pect=0.19, pect_ang=0.55, eye=0.016)

GADOID = Form(            # cod, hake: elongate, three dorsals, a barbel
    depth=0.135, peak=0.28, nose=0.70, tail=TRUNCATE, tail_h=0.1, wave=0.45,
    dorsal=(0.26, 0.40, 0.050), dorsal2=(0.46, 0.64, 0.045),
    anal=(0.52, 0.70, 0.040), pect=0.11, pect_ang=0.45,
    barbel=0.045, eye=0.040)

GRENADIERISH = Form(      # a body that tapers away to nothing: no tail fin
                          # worth the name, which is the whole look of it
    depth=0.130, peak=0.20, nose=0.60, tail=LANCET, tail_h=0.055, wave=0.30,
    dorsal=(0.16, 0.26, 0.055), dorsal2=(0.32, 0.92, 0.018),
    anal=(0.34, 0.92, 0.016), pect=0.10, pect_ang=0.45, eye=0.050)

NOTOTHENIOID = Form(      # toothfish, icefish: a big head and huge pectorals
                          # on a body with no swimbladder at all
    depth=0.155, peak=0.26, nose=0.80, tail=TRUNCATE, tail_h=0.115, wave=0.50,
    dorsal=(0.24, 0.36, 0.048), dorsal2=(0.42, 0.80, 0.042),
    anal=(0.50, 0.80, 0.038), pect=0.22, pect_ang=0.30, eye=0.052)

MYCTOPHID = Form(         # lanternfish: enormous eye, adipose fin, and rows
                          # of photophores down the belly
    depth=0.165, peak=0.28, nose=0.60, tail=FORKED, tail_h=0.13, wave=0.60,
    dorsal=(0.40, 0.54, 0.055), dorsal2=(0.76, 0.80, 0.022),
    anal=(0.62, 0.76, 0.038), pect=0.10, pect_ang=0.55,
    eye=0.085, photo=7)

GONOSTOMATID = Form(      # bristlemouth: small, plain, and everywhere
    depth=0.100, peak=0.26, nose=0.40, tail=FORKED, tail_h=0.1, wave=0.35,
    dorsal=(0.46, 0.58, 0.035), anal=(0.62, 0.80, 0.030),
    pect=0.06, pect_ang=0.50, eye=0.045, photo=9)

STERNOPTYCHID = Form(     # hatchetfish: a deep silver blade of a body with
                          # the eyes pointing straight up
    depth=0.310, peak=0.40, nose=0.75, tail=FORKED, tail_h=0.11, wave=0.72,
    dorsal=(0.46, 0.60, 0.055), anal=(0.62, 0.82, 0.045),
    pect=0.13, pect_ang=0.90, eye=0.090, photo=8)

STOMIID = Form(           # viperfish: the whole body is the wave, the jaw
                          # does not close, and there is a lure on a barbel
    depth=0.075, peak=0.14, nose=0.45, tail=LANCET, tail_h=0.09, wave=0.05,
    dorsal=(0.16, 0.24, 0.070), anal=(0.80, 0.90, 0.030),
    pect=0.07, pect_ang=0.40, eye=0.048, photo=10, barbel=0.16, jaw=0.11)

GEMPYLID = Form(          # snoek: a long snaky predator with a low dorsal
    depth=0.080, peak=0.22, nose=0.25, tail=FORKED, tail_h=0.1, wave=0.20,
    dorsal=(0.16, 0.66, 0.030), anal=(0.66, 0.84, 0.026),
    pect=0.08, pect_ang=0.40, finlets=3, eye=0.038)

SERRANID = Form(          # grouper: robust, big mouth, a fan of a tail
    depth=0.215, peak=0.30, nose=0.85, tail=ROUNDED, tail_h=0.14, wave=0.62,
    dorsal=(0.26, 0.68, 0.060), anal=(0.68, 0.80, 0.048),
    pect=0.17, pect_ang=0.35, eye=0.048)

CAESIONID = Form(         # fusilier: a streamlined midwater planktivore
    depth=0.150, peak=0.32, nose=0.45, tail=FORKED, tail_h=0.15, wave=0.62,
    dorsal=(0.30, 0.66, 0.040), anal=(0.66, 0.80, 0.035),
    pect=0.13, pect_ang=0.45, eye=0.046)
