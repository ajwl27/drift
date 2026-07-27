#!/usr/bin/env python3
"""
DRIFT CONSOLE  -  the development build. Never ships, never ports.

    python3 tools/console.py

Everything in this piece that cannot be reasoned to, on one screen, live, with
the panel next to it and the measured consequence underneath. Swimming speed,
turn persistence, body lag, the gait parameters, frame rate, time compression,
which screen is up, where in the voyage you are -- all adjustable while it
runs, independently or together.

WHY IT IS SEPARATE
    `drift.py` becomes C. Its one job is to stay portable, so it carries no
    tuning scaffolding at all. This file reaches in and sets module globals,
    which is exactly the sort of thing a development build is allowed to do
    and shipping code is not. Note that it needs NO cooperation from drift.py
    beyond what is already there: the constants it drives are read at call
    time, so assigning to them works.

WHY A/B
    Memory for motion is terrible. Everything looks right while you are
    adjusting it and wrong when you come back, because you are watching the
    change rather than the state. Press TAB and the panel splits: your saved
    settings on the left, live on the right, same seed, same organisms, same
    day, stepped in the same loop. The globals are re-applied before each
    side steps, so *every* parameter can differ between them and not just the
    two that happen to live on the Ecosystem.

WHY THE READOUT
    Underneath the panel are the numbers `tools/check_motion.py` reports --
    rotation per frame, median speed -- computed live. Dragging a slider and
    watching both the picture and the number is the whole point: the eye
    decides, and the number is what gets written down and defended.

KEYS
    up / down       select a parameter          left / right   adjust
    shift + arrow   fine        ctrl + arrow    coarse
    backspace       reset the selected parameter to its default
    1 2 3           water / map / key plate
    z               cycle the map through globe, dolly, chart
    t               true physical size, with a ruler to calibrate it
    c               plate chrome on/off        space   pause
    r               next seed                  shift+R reset every parameter
    tab             snapshot into A and split the view; tab again to close
    e               export a paste-ready block to docs/tuned_values.txt
    esc             quit

MOUSE
    click a row to select it, drag anywhere on its bar to set the value,
    click the buttons along the top and bottom. The wheel is the speed
    control over the panel and walks the voyage over the controls.

    Voyage day and seed commit when you let go rather than while dragging,
    because each one costs a fresh spin-up of several seconds.
"""

import copy
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import drift                                                   # noqa: E402
from drift import (Canvas, W, H, Ecosystem, View,               # noqa: E402
                   PANEL_DIAG_IN)
from mapview import (Coast, R_GLOBE, R_CHART, zoom_radius,     # noqa: E402
                     render_map)
from screens import draw_screen, WATER, MAP, KEY, GALLERY      # noqa: E402
from keyplate import render_key                                # noqa: E402
from voyage import Track                                       # noqa: E402
from keyplate import NAMES                                     # noqa: E402
from ocean import Ocean                                        # noqa: E402

SC = 2                       # panel upscale
PAD = 10
COL = 450                    # width of the control column, set so a
                             # 100 mm calibration ruler fits at a
                             # typical desktop monitor density
RULER_MM = 100               # the calibration bar's true length. Fixed.
COLH = 1000                  # the control column's own height: sliders,
                             # ruler, legend and footer. In true-size mode
                             # the panel is SMALLER than this, so the window
                             # is sized by the controls and not by the art.
FOOT = 74                    # readout strip under the panel

INK = (28, 30, 34)
DIM = (122, 130, 140)
FAINT = (196, 202, 210)
BG = (238, 238, 234)
CARD = (247, 247, 245)
HOT = (30, 96, 176)
PAPER = ((228, 228, 224), (22, 22, 24))


# --------------------------------------------------------------------------
# parameters
# --------------------------------------------------------------------------

class Param:
    """One tunable. `lo`/`hi` are the ends of the slider; `log` says the
    slider is geometric, which is right for anything spanning more than about
    a decade -- a linear frame-rate slider spends four fifths of its travel
    between 40 and 51 fps, where nothing happens."""

    __slots__ = ("key", "label", "lo", "hi", "default", "log", "fmt",
                 "unit", "snap", "group")

    def __init__(self, key, label, lo, hi, default, log=False, fmt="%.3f",
                 unit="", snap=None, group=""):
        self.key = key
        self.label = label
        self.lo = float(lo)
        self.hi = float(hi)
        self.default = default
        self.log = log
        self.fmt = fmt
        self.unit = unit
        self.snap = snap          # a tuple of allowed values, or None
        self.group = group

    def frac(self, v):
        if self.log:
            return ((math.log(max(v, 1e-9)) - math.log(self.lo))
                    / (math.log(self.hi) - math.log(self.lo)))
        return (v - self.lo) / (self.hi - self.lo)

    def value(self, f):
        f = min(1.0, max(0.0, f))
        if self.log:
            v = math.exp(math.log(self.lo)
                         + f * (math.log(self.hi) - math.log(self.lo)))
        else:
            v = self.lo + f * (self.hi - self.lo)
        if self.snap:
            v = min(self.snap, key=lambda s: abs(math.log(max(s, 1e-9))
                                                 - math.log(max(v, 1e-9))))
        return v

    def nudge(self, v, direction, size):
        if self.snap:
            i = self.snap.index(min(self.snap, key=lambda s: abs(s - v)))
            return self.snap[min(len(self.snap) - 1, max(0, i + direction))]
        return self.value(self.frac(v) + direction * size)

    def text(self, v):
        return (self.fmt % v) + self.unit


TCOMPS = (1.0, 10.0, 60.0, 600.0, 3600.0, 21600.0, 86400.0)
TCOMP_NAME = {1.0: "1 sec/sec", 10.0: "10 sec/sec", 60.0: "1 min/sec",
              600.0: "10 min/sec", 3600.0: "1 hr/sec", 21600.0: "6 hr/sec",
              86400.0: "1 day/sec"}

PARAMS = [
    Param("swim", "swim scale", 0.02, 1.0, drift.SWIM_SCALE, log=True,
          fmt="%.3f", group="MOTION"),
    Param("turn", "turn scale", 0.1, 10.0, drift.TURN_SCALE, log=True,
          fmt="%.2f", unit="x", group="MOTION"),
    Param("body", "body lag", 0.02, 2.0, drift.BODY_TAU, log=True,
          fmt="%.2f", unit=" s", group="MOTION"),
    Param("hyaw", "helix yaw", 0.0, 3.0, 1.0, fmt="%.2f", unit="x",
          group="GAIT"),
    Param("hrate", "helix rate", 0.1, 5.0, 1.0, log=True, fmt="%.2f",
          unit="x", group="GAIT"),
    Param("prate", "hop rate", 0.1, 5.0, 1.0, log=True, fmt="%.2f",
          unit="x", group="GAIT"),
    Param("pcoast", "hop coast", 0.1, 5.0, 1.0, log=True, fmt="%.2f",
          unit="x", group="GAIT"),
    Param("tumble", "shear tumble", 10.0, 600.0, drift.TUMBLE_S, log=True,
          fmt="%.0f", unit=" s", group="GAIT"),
    Param("fps", "frame rate", 0.25, 51.0, float(drift.TARGET_FPS), log=True,
          fmt="%.2f", unit=" fps", group="PANEL"),
    Param("tcomp", "time", 1.0, 86400.0, 60.0, log=True, snap=TCOMPS,
          group="PANEL"),
    # These two do not feed the model; they choose which community you are
    # looking at, and changing either means a fresh spin-up. So they are
    # committed on mouse release rather than while dragging -- otherwise a
    # single drag across the voyage would queue fifty spin-ups.
    Param("day", "voyage day", 0.0, 1018.0, 420.0, fmt="%.0f", group="SCENE"),
    Param("seed", "seed", 0.0, 40.0, 5.0, fmt="%.0f", group="SCENE"),
    # Not a model parameter either: how dense YOUR monitor is, which is the
    # only thing standing between the panel on screen and the panel in your
    # hand. Arithmetic gives a starting value; the ruler below gives the
    # right one, because desktop scaling settings quietly change it.
    Param("ppi", "monitor ppi", 60.0, 260.0, 108.79, fmt="%.1f",
          group="DISPLAY"),
]
DEFERRED = ("day", "seed")
PANEL_PPI = math.hypot(W, H) / PANEL_DIAG_IN
PMAP = {p.key: p for p in PARAMS}

# the published per-species gait values, kept so the multipliers above have
# something to multiply. Copied once, at import, before anything is touched.
BASE_YAW = dict(drift.HELIX_YAW)
BASE_HZ = dict(drift.HELIX_HZ)
BASE_HOP = dict(drift.HOP_HZ)
BASE_COAST = dict(drift.COAST_S)

# kind constant -> the identifier drift.py calls it by, so the exported block
# is paste-ready rather than merely informative. NAMES would give the species
# ("MICROMONAS"); the source calls that one FLAGELLATE.
KIND_ID = {}
for _name, _val in vars(drift).items():
    if (isinstance(_val, int) and not isinstance(_val, bool)
            and _name.isupper() and _val in NAMES and _val not in KIND_ID):
        KIND_ID[_val] = _name


def ruler_px(ppi):
    return int(round(ppi / 25.4 * RULER_MM))


def defaults():
    return {p.key: p.default for p in PARAMS}


def apply_state(st, eco):
    """Push a parameter set into the model. Globals for the things drift.py
    reads as globals, attributes for the two it reads per-instance. Called
    immediately before each ecosystem is stepped, which is what lets the two
    sides of an A/B differ in every parameter rather than only those two."""
    drift.BODY_TAU = st["body"]
    drift.TUMBLE_S = st["tumble"]
    for k, v in BASE_YAW.items():
        drift.HELIX_YAW[k] = v * st["hyaw"]
    for k, v in BASE_HZ.items():
        drift.HELIX_HZ[k] = v * st["hrate"]
    for k, v in BASE_HOP.items():
        drift.HOP_HZ[k] = v * st["prate"]
    for k, v in BASE_COAST.items():
        drift.COAST_S[k] = v * st["pcoast"]
    if eco is not None:
        eco.swim_scale = st["swim"]
        eco.turn_scale = st["turn"]
        eco.time_compression = st["tcomp"]


# --------------------------------------------------------------------------
# the simulation side
# --------------------------------------------------------------------------

class Side:
    """One panel: an ecosystem, its parameter set, its own frame clock, and a
    running estimate of what its motion measures."""

    def __init__(self, eco, state, label):
        self.eco = eco
        self.st = state
        self.label = label
        self.canvas = Canvas(W, H)
        self.acc = 0.0
        self.prev_ang = {}
        self.prev_pos = {}
        self.key_t = 0.0         # where the key plate's pan has got to
        self.spin = 0.0          # deg per rendered frame, smoothed
        self.speed = 0.0         # px/s, smoothed
        self.frames = 0

    def due(self, real_dt):
        self.acc += real_dt
        return self.acc >= 1.0 / self.st["fps"]

    def advance(self):
        """One panel frame: step by exactly the interval since the last one,
        which is what the device does -- it steps and draws in the same loop,
        so at 1 fps the simulation really does take one-second steps."""
        dt_real = self.acc
        self.acc = 0.0
        apply_state(self.st, self.eco)
        self.eco.step(dt_real * self.st["tcomp"] / 86400.0)
        self._measure(dt_real)
        self.frames += 1

    def _measure(self, dt_real):
        s2 = n = 0
        dist = 0.0
        nd = 0
        for a in self.eco.agents:
            i = id(a)
            p = self.prev_ang.get(i)
            if p is not None:
                d = (a.ang - p + math.pi) % (2.0 * math.pi) - math.pi
                s2 += d * d
                n += 1
                px, pz = self.prev_pos[i]
                dx = a.x - px
                dx -= W * round(dx / W)          # the panel is a cylinder
                dist += abs(dx)
                nd += 1
            self.prev_ang[i] = a.ang
            self.prev_pos[i] = (a.x, a.z)
        live = {id(a) for a in self.eco.agents}
        for d in (self.prev_ang, self.prev_pos):
            for i in [i for i in d if i not in live]:
                del d[i]
        k = 0.12                                  # exponential smoothing
        if n:
            self.spin += k * (math.degrees(math.sqrt(s2 / n)) - self.spin)
        if nd and dt_real > 1e-6:
            self.speed += k * (dist / nd / dt_real - self.speed)


def spin_up(seed, day, track, ocean, note=None):
    """A community at a given point in the voyage. Coarse steps: this is a
    motion tool and it needs a plausible community to look at, not a
    numerically careful one."""
    eco = Ecosystem(seed=seed, start_day=0.0, track=track, ocean=ocean)
    eco.time_compression = 60.0
    while eco.t < day:
        eco.step(1.0 / 6.0)
        if note and int(eco.t) % 60 == 0:
            note(eco.t / max(day, 1.0))
    return eco


# --------------------------------------------------------------------------
# the console
# --------------------------------------------------------------------------

def run(seed=5, day=420.0):
    import numpy as np
    import pygame

    # Windows scales the desktop and then lies about the resolution unless
    # you opt out, which would put a "true size" mode out by 25% on a machine
    # set to 125%. Harmless everywhere else.
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    pygame.init()
    pygame.key.set_repeat(280, 28)
    font = pygame.font.SysFont("monospace", 13)
    small = pygame.font.SysFont("monospace", 11)
    big = pygame.font.SysFont("monospace", 15, bold=True)
    LUT = np.array(PAPER, dtype=np.uint8)
    surf = pygame.Surface((W, H))

    track = Track("drake")
    ocean = Ocean("data/ocean.bin")
    coast = Coast("data/coast.bin")
    view = View(plate=True)
    true_size = False
    live = None                 # set below; panel_px() only reads it once
                                # true_size is on, which cannot be before then

    def panel_px():
        """Blit size in monitor pixels. In true-size mode this is whatever
        makes the panel physically 4.2 inches (or 2.7, or whatever
        PANEL_DIAG_IN says) on the glass in front of you -- which, for any
        monitor less dense than the panel, means DOWN from 1:1 rather than
        up. A 27in 1440p screen is 109 ppi against the panel's 119, so the
        factor is 0.91 and the render has to be resampled rather than
        replicated."""
        if not true_size:
            return W * SC, H * SC, float(SC)
        f = live.st["ppi"] / PANEL_PPI
        return max(40, int(round(W * f))), max(60, int(round(H * f))), f

    def size(split):
        pw, ph, _ = panel_px()
        w = (2 if split else 1) * (pw + PAD) + PAD + COL + PAD
        if true_size and live is not None:
            # the 100 mm bar is drawn from the control column's left edge,
            # so the window has to be at least that wide from there
            w = max(w, (2 if split else 1) * (pw + PAD) + PAD
                    + ruler_px(live.st["ppi"]) + PAD)
        return w, max(ph + FOOT + PAD * 2, COLH)

    def win_h():
        return size(split)[1]

    screen = pygame.display.set_mode(size(False))
    pygame.display.set_caption("drift / console")

    def splash(msg, frac=None):
        screen.fill(BG)
        screen.blit(big.render(msg, True, INK), (PAD + 16, PAD + 16))
        if frac is not None:
            pygame.draw.rect(screen, FAINT, (PAD + 16, PAD + 44, 300, 6))
            pygame.draw.rect(screen, HOT,
                             (PAD + 16, PAD + 44, int(300 * frac), 6))
        pygame.display.flip()
        pygame.event.pump()

    splash("spinning up to day %d ..." % day, 0.0)
    cache = {}

    def community(sd, dy):
        key = (sd, round(dy / 20.0) * 20)
        if key not in cache:
            splash("spinning up seed %d to day %d ..." % key, 0.0)
            cache[key] = spin_up(key[0], float(key[1]), track, ocean,
                                 lambda f: splash("spinning up seed %d to "
                                                  "day %d ..." % key, f))
            if len(cache) > 6:
                del cache[next(iter(cache))]
        return copy.deepcopy(cache[key])

    st0 = defaults()
    st0["day"], st0["seed"] = float(day), float(seed)
    live = Side(community(seed, day), st0, "live")
    sides = [live]
    split = False

    scr = WATER
    zoom = 2                    # 0 globe, 1 dolly, 2 chart
    sel = 0
    paused = False
    pending = False
    dragging = None
    clock = pygame.time.Clock()
    status = ""

    def recommunity():
        """Re-spin to the currently selected day and seed. Deferred rather
        than live because a spin-up is seconds, not milliseconds."""
        live.eco = community(int(live.st["seed"]), live.st["day"])
        live.prev_ang.clear()
        live.prev_pos.clear()
        return "seed %d, day %d" % (live.st["seed"], live.st["day"])

    # ---- layout -------------------------------------------------------
    def col_x():
        return (2 if split else 1) * (panel_px()[0] + PAD) + PAD

    def rows():
        """(param, y) for each row, plus the group headers."""
        out = []
        y = PAD + 72
        group = None
        for p in PARAMS:
            if p.group != group:
                group = p.group
                y += 16
                out.append((None, y, group))
                y += 20
            out.append((p, y, None))
            y += 34
        return out

    def buttons():
        x0, w0 = col_x(), COL - PAD
        top = [("water", (x0, PAD, 74, 24), scr == WATER),
               ("map", (x0 + 80, PAD, 60, 24), scr == MAP),
               ("key", (x0 + 146, PAD, 60, 24), scr == KEY),
               ("A/B", (x0 + 212, PAD, 54, 24), split)]
        y2 = PAD + 28
        top += [("plate", (x0, y2, 56, 22), view.plate),
                ("1:1 size", (x0 + 62, y2, 70, 22), true_size)]
        yb = win_h() - PAD - 24
        bot = [("reset", (x0, yb, 66, 24), False),
               ("reseed", (x0 + 72, yb, 74, 24), False),
               ("export", (x0 + 152, yb, 70, 24), False),
               ("pause", (x0 + 228, yb, 66, 24), paused)]
        if scr == MAP:
            for i, nm in enumerate(("globe", "dolly", "chart")):
                top.append((nm, (x0 + 138 + i * 62, y2, 56, 22), zoom == i))
        return top, bot, w0

    def hit(pt, box):
        x, y, w, h = box
        return x <= pt[0] <= x + w and y <= pt[1] <= y + h

    # ---- drawing ------------------------------------------------------
    def draw_button(label, box, on):
        pygame.draw.rect(screen, HOT if on else CARD, box, border_radius=4)
        pygame.draw.rect(screen, FAINT if not on else HOT, box, 1,
                         border_radius=4)
        t = small.render(label, True, (255, 255, 255) if on else INK)
        screen.blit(t, (box[0] + (box[2] - t.get_width()) // 2,
                        box[1] + (box[3] - t.get_height()) // 2))

    def draw_panel(side, x):
        pw, ph, f = panel_px()
        arr = np.frombuffer(bytes(side.canvas.buf),
                            dtype=np.uint8).reshape(H, W)
        pygame.surfarray.blit_array(surf, np.transpose(LUT[arr], (1, 0, 2)))
        if abs(f - round(f)) < 1e-6 and f >= 1.0:
            pygame.transform.scale(surf, (pw, ph),
                                   screen.subsurface((x, PAD, pw, ph)))
        else:
            # a soft resample is not a betrayal of the 1-bit look: below 1:1
            # the monitor cannot show every panel pixel, and your eye at
            # arm's length from the real panel is doing the same averaging
            screen.blit(pygame.transform.smoothscale(surf, (pw, ph)),
                        (x, PAD))
        pygame.draw.rect(screen, FAINT, (x, PAD, pw, ph), 1)
        y = PAD + ph + 6
        screen.blit(font.render(side.label, True, INK), (x, y))
        readout = ("%.1f'/frame   %.1f px/s   %d agents"
                   % (side.spin, side.speed, len(side.eco.agents)))

        screen.blit(small.render(readout, True, DIM), (x, y + 20))
        lat, lon = track.position(side.eco.t)
        sub = ("day %.1f   %.1f%s %.1f%s   %s"
               % (side.eco.t, abs(lat), "NS"[lat < 0], abs(lon),
                  "EW"[lon < 0], track.status(side.eco.t)))
        screen.blit(small.render(sub, True, DIM), (x, y + 36))
        if true_size:
            mm = 25.4 / max(live.st["ppi"], 1.0)
            screen.blit(small.render("%.0f x %.0f mm" % (pw * mm, ph * mm),
                                     True, HOT), (x, y + 52))

    def toggle_split():
        """Snapshot the live side into A and widen the window, or fold back.

        A is a deep copy taken at this instant, so the two sides start from
        identical organisms in identical places -- which is the only honest
        way to compare, since otherwise you are comparing two different
        communities and attributing the difference to the parameter."""
        nonlocal split, sides
        split = not split
        if split:
            sides = [Side(copy.deepcopy(live.eco), dict(live.st),
                          "A  (saved)"), live]
            live.label = "B  (live)"
        else:
            sides = [live]
            live.label = "live"
        return pygame.display.set_mode(size(split))

    def export():
        lines = ["# pasted from tools/console.py",
                 "SWIM_SCALE = %.4f" % live.st["swim"],
                 "TURN_SCALE = %.4f" % live.st["turn"],
                 "BODY_TAU = %.3f" % live.st["body"],
                 "TARGET_FPS = %d" % int(round(live.st["fps"])),
                 "", "# gait multipliers, folded into the per-species tables:"]
        for name, base, mult in (("HELIX_YAW", BASE_YAW, live.st["hyaw"]),
                                 ("HELIX_HZ", BASE_HZ, live.st["hrate"]),
                                 ("HOP_HZ", BASE_HOP, live.st["prate"]),
                                 ("COAST_S", BASE_COAST, live.st["pcoast"])):
            body = ", ".join("%s: %.3f" % (KIND_ID.get(k, str(k)), v * mult)
                             for k, v in base.items())
            lines.append("%s = {%s}   # x%.2f" % (name, body, mult))
        lines.append("TUMBLE_S = %.0f" % live.st["tumble"])
        txt = "\n".join(lines)
        os.makedirs("docs", exist_ok=True)
        with open("docs/tuned_values.txt", "w") as fh:
            fh.write(txt + "\n")
        print("\n" + txt + "\n-> docs/tuned_values.txt")
        return "exported to docs/tuned_values.txt"

    running = True
    while running:
        real_dt = clock.tick(60) / 1000.0
        mods = pygame.key.get_mods()
        fine = bool(mods & pygame.KMOD_SHIFT)
        coarse = bool(mods & pygame.KMOD_CTRL)
        stepsz = 0.006 if fine else (0.08 if coarse else 0.022)

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.MOUSEBUTTONDOWN:
                top, bot, _ = buttons()
                done = False
                for label, box, _on in top + bot:
                    if not hit(ev.pos, box):
                        continue
                    done = True
                    if label == "water":
                        scr = WATER
                    elif label == "map":
                        scr = MAP
                    elif label == "key":
                        scr = KEY
                    elif label == "plate":
                        view.plate = not view.plate
                    elif label == "1:1 size":
                        true_size = not true_size
                        screen = pygame.display.set_mode(size(split))
                    elif label in ("globe", "dolly", "chart"):
                        zoom = ("globe", "dolly", "chart").index(label)
                    elif label == "pause":
                        paused = not paused
                    elif label == "reseed":
                        live.st["seed"] += 1
                        status = recommunity()
                    elif label == "reset":
                        keep = (live.st["day"], live.st["seed"])
                        live.st = defaults()
                        live.st["day"], live.st["seed"] = keep
                        status = "reset"
                    elif label == "export":
                        status = export()
                    elif label == "A/B":
                        screen = toggle_split()
                if done:
                    continue
                for i, (p, y, _g) in enumerate(
                        [r for r in rows() if r[0] is not None]):
                    if y - 6 <= ev.pos[1] <= y + 26 and ev.pos[0] >= col_x():
                        sel = i
                        dragging = p
                        break
            elif ev.type == pygame.MOUSEBUTTONUP:
                if dragging is not None and dragging.key in DEFERRED:
                    status = recommunity()
                dragging = None
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
                elif ev.key == pygame.K_UP:
                    sel = (sel - 1) % len(PARAMS)
                elif ev.key == pygame.K_DOWN:
                    sel = (sel + 1) % len(PARAMS)
                elif ev.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    p = PARAMS[sel]
                    d = 1 if ev.key == pygame.K_RIGHT else -1
                    live.st[p.key] = p.nudge(live.st[p.key], d, stepsz)
                    if p.key == "ppi" and true_size:
                        screen = pygame.display.set_mode(size(split))
                    if p.key in DEFERRED:
                        pending = True
                elif ev.key == pygame.K_BACKSPACE:
                    p = PARAMS[sel]
                    live.st[p.key] = p.default
                elif ev.key == pygame.K_SPACE:
                    paused = not paused
                elif ev.key == pygame.K_1:
                    scr = WATER
                elif ev.key == pygame.K_2:
                    scr = MAP
                elif ev.key == pygame.K_3:
                    scr = KEY
                elif ev.key == pygame.K_z:
                    zoom = (zoom + 1) % 3
                elif ev.key == pygame.K_c:
                    view.plate = not view.plate
                elif ev.key == pygame.K_t:
                    true_size = not true_size
                    screen = pygame.display.set_mode(size(split))
                elif ev.key == pygame.K_e:
                    status = export()
                elif ev.key == pygame.K_r and (mods & pygame.KMOD_SHIFT):
                    keep = (live.st["day"], live.st["seed"])
                    live.st = defaults()
                    live.st["day"], live.st["seed"] = keep
                    status = "reset"
                elif ev.key == pygame.K_r:
                    live.st["seed"] += 1
                    status = recommunity()
                elif ev.key == pygame.K_TAB:
                    screen = toggle_split()
            elif ev.type == pygame.KEYUP:
                if pending and ev.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    pending = False
                    status = recommunity()
            elif ev.type == pygame.MOUSEWHEEL:
                # over the panel the wheel is the speed control, which is what
                # it does in the shipping preview; over the controls it walks
                # the voyage, which is what you want when the pointer is there
                if pygame.mouse.get_pos()[0] < col_x():
                    p = PMAP["tcomp"]
                    live.st["tcomp"] = p.nudge(live.st["tcomp"], ev.y, 0.1)
                    status = TCOMP_NAME.get(live.st["tcomp"], "")
                else:
                    live.st["day"] = min(1018.0, max(
                        0.0, live.st["day"] + ev.y * 20.0))
                    status = recommunity()

        if dragging is not None:
            x0 = col_x() + 150
            wpx = COL - PAD - 150 - 74
            f = (pygame.mouse.get_pos()[0] - x0) / float(wpx)
            live.st[dragging.key] = dragging.value(f)
        if true_size and screen.get_size() != size(split):
            screen = pygame.display.set_mode(size(split))

        # ---- advance and render each side -----------------------------
        R = (R_GLOBE, zoom_radius(0.55), R_CHART)[zoom]
        for side in sides:
            if not paused and side.due(real_dt):
                side.advance()
                if scr == MAP:
                    # the zoom is a control here rather than a phase of the
                    # cadence, which is the point: you can sit on the globe
                    # for as long as you like and look at it
                    render_map(side.canvas, coast, track, side.eco.t, R,
                               chrome=view.plate)
                elif scr == KEY:
                    # drive the pan from a wall clock the console owns, so
                    # you can watch a whole pass without waiting for the
                    # cadence to come round to it
                    side.key_t = (getattr(side, "key_t", 0.0)
                                  + 1.0 / side.st["fps"]) % GALLERY.key
                    render_key(side.canvas, side.eco, track, side.eco.t,
                               chrome=view.plate, t_into=side.key_t,
                               dwell=GALLERY.key)
                else:
                    draw_screen(side.canvas, scr,
                                GALLERY.duration(scr) * 0.5, side.eco,
                                track, coast, view, GALLERY)

        # ---- chrome ----------------------------------------------------
        screen.fill(BG)
        for i, side in enumerate(sides):
            draw_panel(side, PAD + i * (W * SC + PAD))
        x0 = col_x()
        pygame.draw.rect(screen, CARD, (x0 - 4, PAD - 4, COL - PAD + 8,
                                        win_h() - 2 * PAD + 8),
                         border_radius=6)
        top, bot, _ = buttons()
        for label, box, on in top + bot:
            draw_button(label, box, on)

        idx = 0
        for p, y, group in rows():
            if p is None:
                screen.blit(small.render(group, True, DIM), (x0, y - 12))
                pygame.draw.line(screen, FAINT, (x0 + 62, y - 7),
                                 (x0 + COL - PAD - 8, y - 7))
                continue
            on = (idx == sel)
            if on:
                pygame.draw.rect(screen, (232, 238, 247),
                                 (x0 - 4, y - 6, COL - PAD + 4, 32),
                                 border_radius=4)
            screen.blit(font.render(p.label, True, INK if on else (70, 76, 84)),
                        (x0, y))
            v = live.st[p.key]
            lab = TCOMP_NAME.get(v, p.text(v)) if p.key == "tcomp" \
                else p.text(v)
            t = font.render(lab, True, HOT if on else INK)
            screen.blit(t, (x0 + COL - PAD - 8 - t.get_width(), y))
            bx, bw = x0 + 150, COL - PAD - 150 - 74
            pygame.draw.line(screen, FAINT, (bx, y + 22), (bx + bw, y + 22), 3)
            kx = bx + int(bw * min(1.0, max(0.0, p.frac(v))))
            pygame.draw.line(screen, (150, 158, 168),
                             (bx + int(bw * p.frac(p.default)), y + 17),
                             (bx + int(bw * p.frac(p.default)), y + 27), 1)
            pygame.draw.circle(screen, HOT if on else (90, 98, 108),
                               (kx, y + 22), 5 if on else 4)
            idx += 1

        ly = rows()[-1][1] + 46
        if true_size:
            # CALIBRATE BY MEASURING, NOT BY ARITHMETIC. The ppi computed
            # from a monitor's advertised size and resolution is right only
            # if the desktop is at 100% scaling and the OS is reporting real
            # pixels, and neither is safe to assume. Hold a ruler to this bar
            # and adjust the ppi slider until it reads 100 mm; then the panel
            # beside it is the size the object will actually be.
            # ALWAYS 100 mm. A ruler whose nominal length changes as you
            # adjust the thing it is calibrating is not a ruler -- you would
            # be chasing a moving target, which is exactly the wrong shape
            # for "turn this until it measures 100". The window widens to
            # hold the bar instead.
            mm = RULER_MM
            bar = ruler_px(live.st["ppi"])
            pygame.draw.line(screen, INK, (x0, ly + 10), (x0 + bar, ly + 10), 2)
            for t in range(11):
                tx = x0 + int(bar * t / 10.0)
                hgt = 8 if t % 5 == 0 else 4
                pygame.draw.line(screen, INK, (tx, ly + 10 - hgt),
                                 (tx, ly + 10), 2 if t % 5 == 0 else 1)
            screen.blit(small.render("%d mm -- hold a ruler here, adjust ppi"
                                     % mm, True, DIM), (x0, ly + 14))
            screen.blit(small.render("panel %.1f ppi / monitor %.1f"
                                     % (PANEL_PPI, live.st["ppi"]), True, DIM),
                        (x0, ly + 29))
            screen.blit(small.render("SCALE = %.4f  (paste into drift.py)"
                                     % panel_px()[2], True, HOT),
                        (x0, ly + 44))
            ly += 66

        # the keys, in the space the sliders do not use. A development build
        # that needs its own README has failed at the first hurdle.
        for line in ("up/down  select        left/right  adjust",
                     "shift    fine          ctrl        coarse",
                     "backspace  reset this one",
                     "",
                     "1 2 3    water / map / key      z  map zoom",
                     "c  plate   t  true size   space  pause   r  seed",
                     "tab      A/B split against a saved copy",
                     "e        export to docs/tuned_values.txt",
                     "shift+R  reset every parameter"):
            screen.blit(small.render(line, True, DIM), (x0, ly))
            ly += 15

        yb = win_h() - PAD - 48
        screen.blit(small.render(status, True, DIM), (x0, yb))
        hint = ("wheel over the panel = speed, over the controls = voyage day"
                "   |   tab = A/B")
        screen.blit(small.render(hint, True, DIM), (x0, yb - 15))
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    d = float(sys.argv[1]) if len(sys.argv) > 1 else 420.0
    run(day=d)
