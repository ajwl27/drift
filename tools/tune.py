#!/usr/bin/env python3
"""
The development build. Never ships, never ports.

    python3 tools/tune.py            # swimming speed, four side by side
    python3 tools/tune.py fps        # frame rate, four side by side

Two of the numbers in this project cannot be reasoned to. Swimming speed is
derived from real body lengths per second, which fixes the *ratios* between
organisms but leaves one global multiplier that is purely a judgement about
how a moving thing looks. Frame rate is the same. Both have to be set by eye,
and this is the eye.

The important design decision here is FOUR AT ONCE. Tuning a single panel up
and down means comparing what is on the screen against your memory of what was
on it thirty seconds ago, and memory for motion is terrible -- everything looks
right while you are adjusting it and wrong when you come back. Side by side,
running from the same seed and the same ecosystem state, the difference is
immediate and the choice takes about four seconds.

Keys:
    left / right    shift the whole range of values being compared
    up / down       spread or tighten the range
    1 2 3 4         choose a panel; writes the value and prints it
    space           pause
    r               reseed
    esc             quit
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import drift                                             # noqa: E402
from drift import (Canvas, W, H, Ecosystem, View, render, text,  # noqa: E402
                   SWIM_SCALE, TARGET_FPS)
from voyage import Track                                 # noqa: E402
from ocean import Ocean                                  # noqa: E402

N = 4
GAP = 6
START_DAY = 420.0          # the Humboldt: busy enough to judge motion by


def _fleet(seed, day, track, ocean, scales):
    """N ecosystems from the same seed, run to the same day, differing only
    in swimming speed. Same seed matters more than it looks: the organisms
    are then in the same places with the same genomes, so the only thing your
    eye can be responding to is the motion."""
    out = []
    for sc in scales:
        e = Ecosystem(seed=seed, start_day=0.0, track=track, ocean=ocean)
        e.swim_scale = sc
        out.append(e)
    print("spinning up %d ecosystems to day %.0f ..." % (len(out), day))
    while out[0].t < day:
        for e in out:
            # a coarse step for the spin-up: this is a motion-tuning tool
            # and it only needs a plausible community to look at, not a
            # numerically careful one. Four ecosystems to day 420 takes 17
            # seconds this way and 64 at the simulation's usual step.
            e.step(1.0 / 6.0)
    return out


def run(mode="swim", seed=5):
    import numpy as np
    import pygame

    track = Track("drake")
    ocean = Ocean("data/ocean.bin")
    centre = SWIM_SCALE if mode == "swim" else float(TARGET_FPS)
    spread = 2.6

    def values():
        if mode == "swim":
            return [centre * spread ** ((i - (N - 1) / 2.0) / (N - 1) * 2)
                    for i in range(N)]
        base = (4, 8, 12, 16, 20, 25, 30, 40, 51)
        j = min(range(len(base)), key=lambda k: abs(base[k] - centre))
        idx = [max(0, min(len(base) - 1, j + k - N // 2)) for k in range(N)]
        return [float(base[k]) for k in idx]

    vals = values()
    ecos = _fleet(seed, START_DAY, track, ocean,
                  vals if mode == "swim" else [SWIM_SCALE] * N)

    pygame.init()
    SC = 2
    tw = N * (W * SC + GAP) + GAP
    th = H * SC + GAP * 2 + 22
    screen = pygame.display.set_mode((tw, th))
    pygame.display.set_caption("drift / tune %s" % mode)
    clock = pygame.time.Clock()
    LUT = np.array([[228, 228, 224], [22, 22, 24]], dtype=np.uint8)
    surf = pygame.Surface((W, H))
    font = pygame.font.SysFont("monospace", 13)

    canvases = [Canvas(W, H) for _ in range(N)]
    view = View(plate=False, hud=False)
    paused = False
    frame = 0
    running = True
    while running:
        dt = clock.tick(60) / 1000.0
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    running = False
                elif e.key == pygame.K_SPACE:
                    paused = not paused
                elif e.key == pygame.K_LEFT:
                    centre /= 1.25
                elif e.key == pygame.K_RIGHT:
                    centre *= 1.25
                elif e.key == pygame.K_UP:
                    spread = min(6.0, spread * 1.2)
                elif e.key == pygame.K_DOWN:
                    spread = max(1.1, spread / 1.2)
                elif e.key == pygame.K_r:
                    seed += 1
                    ecos = _fleet(seed, START_DAY, track, ocean,
                                  vals if mode == "swim" else [SWIM_SCALE] * N)
                elif e.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                    k = e.key - pygame.K_1
                    if k < N:
                        chosen = vals[k]
                        if mode == "swim":
                            print("\nSWIM_SCALE = %.4f" % chosen)
                        else:
                            print("\nTARGET_FPS = %d" % int(chosen))
                        print("   paste that into drift.py")
                if e.key in (pygame.K_LEFT, pygame.K_RIGHT,
                             pygame.K_UP, pygame.K_DOWN):
                    vals = values()
                    if mode == "swim":
                        for e2, v in zip(ecos, vals):
                            e2.swim_scale = v

        if not paused:
            for e2 in ecos:
                e2.time_compression = 60.0        # the default speed setting
                e2.step(dt * 60.0 / 86400.0)
        frame += 1

        screen.fill((238, 238, 234))
        for i in range(N):
            # in fps mode each panel redraws at its own rate and holds
            # between, which is exactly what a slower panel would look like
            hold = 1 if mode == "swim" else max(1, int(round(60.0 / vals[i])))
            if frame % hold == 0 or frame == 1:
                render(ecos[i], canvases[i], view)
            arr = np.frombuffer(bytes(canvases[i].buf),
                                dtype=np.uint8).reshape(H, W)
            pygame.surfarray.blit_array(surf, np.transpose(LUT[arr], (1, 0, 2)))
            x = GAP + i * (W * SC + GAP)
            pygame.transform.scale(surf, (W * SC, H * SC),
                                   screen.subsurface((x, GAP, W * SC, H * SC)))
            lab = ("%.3f" % vals[i]) if mode == "swim" else ("%d fps" % vals[i])
            img = font.render("%d)  %s" % (i + 1, lab), True, (30, 30, 30))
            screen.blit(img, (x, GAP + H * SC + 4))
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "swim")
