#!/usr/bin/env python3
"""
What frame rate costs in battery life.

    python3 tools/power.py

Every number below is measured, from a datasheet, or from someone else's
measurement with the source named -- except one, the CPython-to-C factor,
which is an extrapolation and is therefore swept rather than asserted. The
point is not to produce a figure; it is to produce a figure you can argue
with, and to be clear about which part of it is soft.

THE HEADLINE, before any arithmetic: **this piece was decided as a
mains-powered object at the first design conversation**, when the choice was
"moving, or slowly changing?" and the answer was "moving -- you can watch it
drift". Everything here is therefore about what it would cost to run on a
cell anyway, which is what matters for the gift boxes.

THE SHAPE OF THE ANSWER: battery life is set by the MCU's *duty cycle*, and
duty cycle is frame_ms x fps. Frame rate and frame cost are therefore exactly
as important as each other, and the panel -- the thing you would assume a
display costs money to run -- is a rounding error until the MCU is nearly
asleep.
"""

# --------------------------------------------------------------------------
# MEASURED  -  this machine, CPython 3.11, day 300 of the Drake voyage
# --------------------------------------------------------------------------
#
#   e = Ecosystem(seed=5, ...) spun to day 300, 43 agents
#   timeit(lambda: e.step(dt))                        -> 1.47 ms
#   timeit(lambda: draw_screen(c, WATER, ...))        -> 2.01 ms
#   timeit(lambda: draw_screen(c, MAP, ...))          -> 8.41 ms
#   timeit(lambda: draw_screen(c, KEY, ...))          -> 1.65 ms
#
SIM_MS = 1.47
REN_MS = {"water": 2.01, "map": 8.41, "key": 1.65}

# GALLERY cadence, from screens.py: water 1080 s, map 18 s, water 1080 s,
# key 15 s. The map costs four times the water view and occupies 0.8% of the
# time, so it contributes 3% of the render budget: worth knowing, not worth
# optimising.
CADENCE = {"water": 2160.0, "map": 18.0, "key": 15.0}


def render_ms():
    tot = sum(CADENCE.values())
    return sum(REN_MS[k] * v for k, v in CADENCE.items()) / tot


# --------------------------------------------------------------------------
# EXTRAPOLATED  -  the weakest number here, so it is a range and not a value
# --------------------------------------------------------------------------
#
# How long a frame takes in C on a 150 MHz Cortex-M33, given how long it takes
# in CPython on this x86. Two large factors point opposite ways and roughly
# cancel:
#
#   CPython vs C on the same machine        30-70x slower
#   M33 at 150 MHz vs a modern x86 core     ~45x slower per thread
#                                           (225 DMIPS against ~10,000)
#
# so the working estimate is that a frame costs about the same wall-clock on
# the panel as it does here. The RP2350's M33 has a single-precision FPU,
# which the float-heavy simulation needs, and the renderer is integer raster
# and should beat the ratio. Swept 0.5x to 2x below. It wants measuring on
# real hardware before anybody believes any of it.
C_FACTORS = (0.5, 1.0, 2.0)

# --------------------------------------------------------------------------
# SOURCED
# --------------------------------------------------------------------------
#
# MCU -- Raspberry Pi Pico 2 (RP2350A), measured at the board rather than the
# die. Two independent sets agree closely:
#   bablokb/pico-sleepcurrent   busy 13.2 mA, light/deep sleep 1.7 mA,
#                               deep sleep + PowerManager 170 uA
#   cs.stanford.edu/~nick       busy 21.9 mA, lightsleep(50 ms) 1.92 mA,
#                               1.56 mA fed at 3V3 directly
# Both at 5 V through the board's buck-boost. "Busy" there is a MicroPython
# loop; real dual-core work at 150 MHz executing from XIP flash draws more, so
# the active figure is taken above the top of the observed range.
# Those measurements are at 5 V. A single Li-ion cell sits at about 3.7 V,
# and mAh ratings are quoted at the cell, so the same power costs more
# current there. Converting by power equivalence (and assuming the converter
# is no worse at one input voltage than the other) is the honest way to keep
# the two consistent.
MEAS_V, CELL_V = 5.0, 3.7
MCU_ACTIVE_5V = 22.0         # top of the observed busy range, rounded up
MCU_IDLE_5V = 1.8            # stock Pico 2, WFI, RAM retained
MCU_IDLE_TUNED_5V = 0.20     # measured with PowerManager; custom board, LDO

MCU_ACTIVE_MA = MCU_ACTIVE_5V * MEAS_V / CELL_V
MCU_IDLE_MA = MCU_IDLE_5V * MEAS_V / CELL_V
MCU_IDLE_TUNED_MA = MCU_IDLE_TUNED_5V * MEAS_V / CELL_V

# PANEL -- ST7305 reflective LCD, 240x400, which supports 0.25-51 Hz (ST7305
# datasheet, section 1). No backlight: a reflective panel costs nothing to be
# looked at, which is most of why it was chosen.
#
# Vendor figures for this driver generation, via the Espruino discussion:
#   ST7302, 250x122   30 uA at 4 Hz low-power mode  -> 7.5 uA per Hz
#                     under 1 mA at 32 Hz high-power mode
#   ST7305, 2.9"      "about 100 uA or less" in low-power mode
#
# Scaling the ST7302 figure by pixel count (96,000 / 30,500 = 3.15x) gives
# 23.6 uA/Hz for our panel, which predicts 94 uA at 4 Hz -- and the ST7305's
# own "100 uA or less" is exactly that. Two independent numbers agreeing is
# the best evidence available short of a bench.
PANEL_UA_PER_HZ = 23.6
PANEL_BASE_UA = 15.0

# CELLS. Capacity is nominal; usable is lower cold and lower after a few
# hundred cycles, so treat these as optimistic by 10-15%.
CELLS = (("18650, 3000 mAh", 3000.0),
         ("2 x 18650", 6000.0),
         ("LiPo pouch, 1200 mAh", 1200.0),
         ("4 x AA alkaline", 2400.0))

# Li-ion self-discharge, about 2% a month, which is a floor no amount of
# efficiency gets under: 60 mAh a month on a 3000 mAh cell is 83 uA of
# permanent leak.
SELF_DISCHARGE_MA = 0.083


def draw(fps, c_factor=1.0, idle=MCU_IDLE_MA):
    """(mcu mA, panel mA, duty, frame ms). The MCU is either awake at
    MCU_ACTIVE_MA or asleep at `idle`, and the whole model is the fraction of
    the time it spends in each."""
    frame_ms = (SIM_MS + render_ms()) * c_factor
    duty = min(1.0, frame_ms * fps / 1000.0)
    mcu = duty * MCU_ACTIVE_MA + (1.0 - duty) * idle
    panel = (PANEL_BASE_UA + PANEL_UA_PER_HZ * fps) / 1000.0
    return mcu, panel, duty, frame_ms


def total(fps, c_factor=1.0, idle=MCU_IDLE_MA):
    mcu, panel, _, _ = draw(fps, c_factor, idle)
    return mcu + panel


def life_days(total_ma, mah):
    return mah / (total_ma + SELF_DISCHARGE_MA) / 24.0


CASES = ((0.25, "one frame per 4 s", "the panel's slowest setting"),
         (1.0, "1 fps", "a clock, not an aquarium"),
         (2.0, "2 fps", ""),
         (5.0, "5 fps", "motion, visibly stepped"),
         (8.0, "8 fps", ""),
         (10.0, "10 fps", "floor for the fastest swimmer to read"),
         (15.0, "15 fps", "assumed at the first design conversation"),
         (20.0, "20 fps", "the preview's rate"),
         (30.0, "30 fps", ""),
         (51.0, "51 fps", "the panel's maximum"))


def main():
    print("Frame: sim %.2f + render %.2f (cadence-weighted) = %.2f ms in "
          "CPython\n" % (SIM_MS, render_ms(), SIM_MS + render_ms()))

    print("=== 1. Frame rate against battery life, one 18650 (3000 mAh) ===\n")
    print("%-20s %7s %8s %9s %9s %7s %14s  %s"
          % ("", "duty", "MCU mA", "panel mA", "total mA", "days",
             "range (C 2x-0.5x)", ""))
    for fps, name, note in CASES:
        mcu, panel, duty, _ = draw(fps)
        tot = mcu + panel
        lo = life_days(total(fps, 2.0), 3000.0)
        hi = life_days(total(fps, 0.5), 3000.0)
        print("%-20s %6.1f%% %8.2f %9.3f %9.2f %7.0f %6.0f - %-6.0f  %s"
              % (name, 100 * duty, mcu, panel, tot,
                 life_days(tot, 3000.0), lo, hi, note))
    print("\n'days' is at the central C-factor; the range sweeps it 0.5x-2x,")
    print("which is the honest width of the extrapolation to C on the M33.")

    print("\n=== 2. What each step down in frame rate actually buys ===\n")
    print("%-14s %10s %8s   %s" % ("", "total mA", "days", "gain on the last"))
    prev = None
    for fps in (51.0, 30.0, 20.0, 10.0, 5.0, 2.0, 1.0, 0.25):
        tot = total(fps)
        d = life_days(tot, 3000.0)
        gain = "" if prev is None else "%.2fx" % (d / prev)
        print("%-14s %10.2f %8.0f   %s" % ("%g fps" % fps, tot, d, gain))
        prev = d
    d = lambda f: life_days(total(f), 3000.0)          # noqa: E731
    print("\nThe returns stop, and they stop early. 51 -> 10 fps multiplies")
    print("life by %.1fx; 10 -> 1 fps by %.1fx; 1 -> 0.25 fps by %.2fx. Below"
          % (d(10) / d(51), d(1) / d(10), d(0.25) / d(1)))
    print("a few frames a second there is almost nothing left to win, because")
    print("the MCU is asleep %.1f%% of the time and you are paying its idle"
          % (100 * (1 - draw(1.0)[2])))
    print("current whatever you do. Which is section 2b.")

    print("\n=== 2b. The same table on a board that can actually sleep ===\n")
    print("This is the finding. On a stock Pico 2 the idle current is %.1f mA,"
          % MCU_IDLE_MA)
    print("so the panel spends its life paying that whatever the frame rate")
    print("is, and frame rate is only a %.0fx lever end to end. Get the idle"
          % (life_days(total(0.25), 3000.0) / life_days(total(51.0), 3000.0)))
    print("down to %.2f mA and the same span becomes a %.0fx lever."
          % (MCU_IDLE_TUNED_MA,
             life_days(total(0.25, 1.0, MCU_IDLE_TUNED_MA), 3000.0)
             / life_days(total(51.0, 1.0, MCU_IDLE_TUNED_MA), 3000.0)))
    print()
    print("%-12s %12s %12s   %s"
          % ("", "stock Pico 2", "tuned board", "ratio"))
    for fps in (51.0, 30.0, 20.0, 15.0, 10.0, 5.0, 2.0, 1.0, 0.25):
        a = life_days(total(fps), 3000.0)
        b = life_days(total(fps, 1.0, MCU_IDLE_TUNED_MA), 3000.0)
        print("%-12s %9.0f d %10.0f d   %.1fx"
              % ("%g fps" % fps, a, b, b / a))
    print("\nUntil the sleep current is dealt with, dropping the frame rate")
    print("is fighting the wrong number.")

    print("\n=== 3. The other levers, all at 20 fps ===\n")
    base = total(20.0)
    rows = (("as it stands", base),
            ("frame cost halved (better C, or partial update)",
             total(20.0, 0.5)),
            ("custom board, tuned idle (%.2f mA)" % MCU_IDLE_TUNED_MA,
             total(20.0, 1.0, MCU_IDLE_TUNED_MA)),
            ("both together", total(20.0, 0.5, MCU_IDLE_TUNED_MA)),
            ("...and 10 fps as well", total(10.0, 0.5, MCU_IDLE_TUNED_MA)))
    for name, ma in rows:
        print("%-48s %7.2f mA %6.0f d   %s"
              % (name, ma, life_days(ma, 3000.0),
                 "" if ma >= base else "%.2fx" % (base / ma)))
    print("\nHalving the frame cost buys %.2fx and halving the frame rate"
          % (life_days(total(20.0, 0.5), 3000.0)
             / life_days(total(20.0), 3000.0)))
    print("buys %.2fx -- the same lever, because duty cycle is frame_ms x fps"
          % (life_days(total(10.0), 3000.0)
             / life_days(total(20.0), 3000.0)))
    print("and it does not care which factor you shrink. One of them costs")
    print("you the motion and the other costs you nothing to look at.")

    print("\n=== 4. The panel is not the problem ===\n")
    for fps in (1.0, 10.0, 20.0, 51.0):
        mcu, panel, _, _ = draw(fps)
        print("%5g fps:  MCU %6.2f mA (%2.0f%%)    panel %.3f mA (%.0f%%)"
              % (fps, mcu, 100 * mcu / (mcu + panel), panel,
                 100 * panel / (mcu + panel)))
    print("\nA reflective LCD has no backlight, so being looked at is free.")
    print("Even at its 51 Hz maximum the panel draws about a milliamp, a")
    print("twentieth of what the MCU costs to feed it. Every saving worth")
    print("having is on the compute side.")

    print("\n=== 5. Cells, at the rates the piece is likely to run ===\n")
    for fps in (10.0, 20.0):
        tot = total(fps)
        print("  at %g fps (%.2f mA):" % (fps, tot))
        for name, mah in CELLS:
            d = life_days(tot, mah)
            print("      %-24s %5.0f days  (%.1f months)"
                  % (name, d, d / 30.4))
    print("\nSelf-discharge (%.0f uA) is included. Below about half a"
          % (SELF_DISCHARGE_MA * 1000))
    print("milliamp total it is a significant fraction, and no design")
    print("gets under it.")

    print("\n=== 6. What this does not model ===\n")
    for line in (
            "Regulator loss. A buck-boost at a 2 mA load runs well off its",
            "  efficiency peak; add 15-25% for anything fed from a cell",
            "  through one. An LDO from a single Li-ion cell is often better",
            "  at these currents despite the dropout.",
            "Wake-up cost. Leaving sleep, relocking the PLL and re-enabling",
            "  XIP is tens of microseconds -- nothing at 20 fps, but 5-10% of",
            "  the budget at 0.25 fps where the frames are all that happens.",
            "Panel current on a fully changing image. The vendor figures are",
            "  typical, and every pixel moving every frame will be worse.",
            "Temperature. A cell at 0 C gives perhaps 70% of its rating.",
            "The map screen's 8.4 ms. It is 0.8% of the time and folded into",
            "  the weighted average above; if the cadence ever became",
            "  map-heavy this model would need redoing."):
        print(line)


if __name__ == "__main__":
    main()
