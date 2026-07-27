#!/usr/bin/env python3
"""
What the motion costs in current.

    python3 tools/power.py

A first-order model, and the numbers it needs are all measured or from a
datasheet except one -- how long a frame takes in C on the target, which is
extrapolated from the CPython measurement and flagged as such. Everything
here is meant to be argued with; the point is that it is arguable, rather
than a shrug.

The headline, before any of the arithmetic: **this piece was decided as a
mains-powered object at the very first design conversation**, when the choice
was "moving, or slowly changing?" and the answer was "moving -- you can watch
it drift". Everything below is therefore about how much it would cost to run
it on a cell anyway, which is worth knowing for the gift boxes.
"""

# --- measured ------------------------------------------------------------
SIM_MS_X86 = 1.48          # per step, CPython, 37 agents, measured
REN_MS_X86 = 2.09          # per frame, CPython, full plate, measured

# --- extrapolated, and the weakest number here ---------------------------
#
# CPython on a modern x86 and hand-written C on a 150 MHz Cortex-M33 are not
# obviously comparable in either direction: CPython carries an interpreter
# overhead of perhaps 50x, and the M33 is perhaps 100x slower per instruction
# than the x86. Those roughly cancel, so the working assumption is that a
# frame costs about the same wall-clock time on the panel as it does here.
# It wants measuring on real hardware before anyone believes it.
C_FACTOR = 1.0

# --- datasheet / vendor --------------------------------------------------
MCU_ACTIVE_MA = 38.0       # RP2350 at 150 MHz, both cores, XIP from flash
MCU_SLEEP_MA = 1.2         # WFI with clocks trimmed, RAM retained
PANEL_MA_PER_HZ = 0.098    # ST7305: ~40 uA at 1 Hz, ~5 mA at 51 Hz -> linear
PANEL_BASE_MA = 0.014
CELL_MAH = 3000.0          # one 18650


def frame_ms():
    return (SIM_MS_X86 + REN_MS_X86) * C_FACTOR


def average_ma(fps):
    duty = min(1.0, frame_ms() * fps / 1000.0)
    mcu = duty * MCU_ACTIVE_MA + (1.0 - duty) * MCU_SLEEP_MA
    panel = PANEL_BASE_MA + PANEL_MA_PER_HZ * fps
    return mcu, panel, duty


CASES = (
    (0.017, "one frame a minute", "the original e-ink-style concept"),
    (1.0, "1 fps", "a clock, not an aquarium"),
    (5.0, "5 fps", "motion, visibly stepped"),
    (10.0, "10 fps", "the floor for the fastest swimmer to read"),
    (15.0, "15 fps", "what was assumed at the first design conversation"),
    (20.0, "20 fps", "the preview's rate"),
    (51.0, "51 fps", "the panel's maximum"),
)


def main():
    print("Frame cost assumed: %.1f ms  (sim %.2f + render %.2f, C_FACTOR %.1f)\n"
          % (frame_ms(), SIM_MS_X86, REN_MS_X86, C_FACTOR))
    print("%-22s %6s %8s %8s %8s %10s  %s"
          % ("", "duty", "MCU mA", "panel mA", "total", "18650", ""))
    for fps, name, note in CASES:
        mcu, panel, duty = average_ma(fps)
        tot = mcu + panel
        days = CELL_MAH / tot / 24.0
        print("%-22s %5.1f%% %8.1f %8.2f %8.1f %7.0f d  %s"
              % (name, 100 * duty, mcu, panel, tot, days, note))
    print()
    base = sum(average_ma(0.017)[:2])
    ten = sum(average_ma(10.0)[:2])
    print("Going from a frame a minute to 10 fps costs %.0fx the current"
          % (ten / base))
    print("and takes an 18650 from %.0f days to %.0f days."
          % (CELL_MAH / base / 24.0, CELL_MAH / ten / 24.0))
    print()
    print("The MCU dominates, not the panel: at 10 fps it is %.0f%% of the "
          "draw." % (100 * average_ma(10.0)[0] / ten))
    print("So the lever that matters is frame cost, not refresh rate --")
    print("halving the render halves the duty cycle and nearly halves the total.")


if __name__ == "__main__":
    main()
