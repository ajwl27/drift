#!/usr/bin/env python3
"""
FISH  -  the roster, and the envelope that decides where each one lives.

This is the successor to drift.py's TRAITS table, and it keeps that table's
one rule: THERE IS NO COLUMN SAYING WHERE ANYTHING LIVES. No species record
mentions Peru, or the Humboldt, or the Moluccas. Each carries an envelope --
the water it tolerates -- the ocean carries conditions, and presence falls
out.

The method is Kaschner et al. 2006's Relative Environmental Suitability
model, which is what AquaMaps runs on for 33,000 species. Per axis, four
numbers describing a trapezoid:

    suitability
        1.0        +--------------+
                   |              |
        0.0  ------+              +------
                lo    plo    phi    hi

Zero outside [lo, hi], one across [plo, phi], linear on the ramps. Four axes
-- bottom depth, temperature at the depth the fish lives, productivity, and
distance to shore -- multiplied together. Sixteen numbers a species; the whole
roster is under a kilobyte and compiles to a const table.

TWO DEPTHS, AND THEY ARE NOT THE SAME NUMBER. This is the one thing in the
file that is easy to get wrong:

    bottom      how deep the SEABED is here. An envelope axis. It is what
                separates a shelf species from an oceanic one, and it is why
                bathymetry had to be added to ocean.bin.
    z           how deep the FISH swims. Not an envelope axis at all -- it is
                where the thing is drawn on the panel.

A Patagonian toothfish over a 3,000 m abyss and one over a 400 m shelf are
both at home; what changes is where in the column it sits. Conflating the two
would have put every deep-living species over deep water, which is wrong for
most of them and catastrophically wrong for the demersal ones.

SOURCES. Depth ranges, temperature ranges, lengths and trophic levels are
FishBase species summaries, retrieved July 2026, and the numbers in the
comments are quoted from them rather than rounded to taste. Where FishBase
gives both an absolute and a "usual" range, the absolute range sets [lo, hi]
and the usual range sets [plo, phi] -- which is exactly the trapezoid's
meaning and is why the two-range format was worth keeping.

The bottom-depth and shore envelopes are DERIVED rather than quoted, because
FishBase reports an environment class rather than a bathymetric preference.
The mapping is stated once, in SHELF/SLOPE/OCEANIC/REEF below, and applied
uniformly -- so it is one assumption written down once rather than twenty-six
judgements made silently.
"""

import math

import draw

# --------------------------------------------------------------------------
# 1. THE ROSTER
# --------------------------------------------------------------------------

(ANCHOVETA, SARDINE, HERRING, MACKEREL, CHUB, PILCHARD_EU, JACKMACK,
 SKIPJACK, YELLOWFIN, BLUEFIN, WAHOO, MARLIN, DORADO, FLYINGFISH,
 BLUESHARK, WHALESHARK, TREVALLY, GROUPER, FUSILIER,
 COD, HAKE_EU, HAKE_CL, HAKE_ZA, HAKE_AR, ANCHOITA, SNOEK, GRENADIER,
 TOOTHFISH, ICEFISH, SILVERFISH,
 LANTERNFISH, WARMING, BRISTLEMOUTH, HATCHETFISH, VIPERFISH) = range(35)

# --- swimming modes -------------------------------------------------------
#
# Fish swimming is classified by how much of the body participates in the
# wave, and the classes are visibly different at 300x400 in a way the
# plankton gaits never quite were. Breder 1926, and the terminology has not
# moved since.
(THUNNIFORM,      # tuna, marlin, wahoo, the sharks. The body is a rigid
                  # aerofoil and only the tail beats. Fastest thing in the
                  # sea and it holds a course like a torpedo.
 CARANGIFORM,     # the default. Rear third undulates.
 SUBCARANGIFORM,  # herring, sardine, cod. More of the body joins in.
 ANGUILLIFORM,    # viperfish, grenadier. The whole body is the wave.
 ) = range(4)

# --- habitat classes, and the ONLY place bathymetry preference is set ------
#
# FishBase gives an environment string, not a bottom-depth envelope. Rather
# than invent twenty-six bathymetric preferences by eye, four classes are
# defined here and every species is assigned to one. If the mapping is wrong
# it is wrong in one legible place.
#
#   (lo, plo, phi, hi) in metres of bottom depth, and the shore envelope in
#   kilometres from the coastline.
#
# WHICH OF THE TWO AXES CARRIES THE SHELF SIGNAL, AND WHY IT IS NOT DEPTH.
#
# The obvious design gives shelf species a shallow bottom-depth envelope and
# is defeated by the resolution of the grid. Measured along Drake's Chilean
# and Peruvian leg -- the most important water on the whole track -- the 2
# degree bathymetry reports 500 to 4,300 m, mostly over 1,000. That is not an
# error in the data: the Peru shelf is 5 to 50 km wide with the Peru-Chile
# Trench immediately outboard of it, so a 2 degree cell genuinely averages a
# shelf with a trench, and no interpolation recovers a feature an eighth the
# width of a cell.
#
# Run against depth, the anchoveta -- the single most important species on
# the voyage, and the largest fishery on Earth -- never appeared at all.
#
# Distance to coast does not have this problem. It is computed from
# coast.bin at 0.1 degrees, twenty times finer, and along the same leg it
# reports 35 to 190 km, which is exactly the band the anchoveta occupies and
# is what FishBase means by "dependent on the coastal extent of the Peru
# Current".
#
# So for coastal classes the SHORE axis discriminates and the DEPTH axis is
# demoted to excluding true abyss. That is a statement about the grid rather
# than about fish, which is why it is written here rather than hidden in
# thirty-three species records.
SHELF   = ((0.0,    0.0, 1000.0,  6000.0), (0.0,   0.0,  150.0,  400.0))
SLOPE   = ((50.0,  150.0, 3000.0, 7000.0), (0.0,   0.0,  400.0,  900.0))
OCEANIC = ((0.0,  1000.0, 6000.0, 11000.0), (0.0, 100.0, 9000.0, 9000.0))
REEF    = ((0.0,    0.0,  600.0,  3000.0), (0.0,   0.0,   90.0,  260.0))
# Mesopelagic species are oceanic in bathymetry but indifferent to shore --
# the deep scattering layer is present over any water deep enough to hold it.
MESO    = ((200.0, 800.0, 6000.0, 11000.0), (0.0, 0.0, 9000.0, 9000.0))


class Fish:
    """One species: what it is, what water it tolerates, how it moves.

    Everything the panel needs and nothing else. On the MCU this is a const
    struct and the whole roster is a flash array."""

    __slots__ = ("key", "binomial", "common", "group", "size_label",
                 "len_common", "len_max", "trophic",
                 "temp", "bottom", "prod", "shore",
                 "z", "dvm_day", "dvm_night",
                 "gait", "shoal", "swim_bl", "note")

    def __init__(self, key, binomial, common, group, size_label,
                 len_common, len_max, trophic, temp, habitat, prod,
                 z, gait, shoal, swim_bl, dvm=None, note=""):
        self.key = key
        self.binomial = binomial
        self.common = common
        self.group = group
        self.size_label = size_label
        self.len_common = len_common          # cm, FishBase "common length"
        self.len_max = len_max                # cm, FishBase "max length"
        self.trophic = trophic                # FishBase trophic level
        # TEMPERATURE AT THE DEPTH THE FISH LIVES AT -- not sea surface
        # temperature. This distinction was got wrong first time and the
        # error was total rather than marginal: tested against SST, every
        # mesopelagic species vanished from the tropics, because a 23 C
        # surface is outside the envelope of an animal that has never
        # experienced it. A lanternfish at 600 m is in 5 C water whether the
        # surface above it is the Denmark Strait or the Coral Sea, and
        # FishBase's quoted range for such a species is a range of the water
        # it actually occupies. So the axis is evaluated at temp_depth()
        # below, and for anything living above the thermocline that is still
        # just SST.
        self.temp = temp                      # (lo, plo, phi, hi) degrees C
        self.bottom, self.shore = habitat     # one of SHELF/SLOPE/OCEANIC/...
        self.prod = prod                      # (lo, plo, phi, hi), index 0..1
        self.z = z                            # (min, max) swimming depth, m
        self.dvm_day, self.dvm_night = dvm if dvm else (None, None)
        self.gait = gait
        self.shoal = shoal                    # 0 solitary .. 1 dense shoal
        self.swim_bl = swim_bl                # body lengths per second, cruise
        self.note = note


def _f(*a, **k):
    return Fish(*a, **k)


# PRODUCTIVITY ENVELOPES, and what the number means.
#
# The index is defined in drift.Environment.productivity(): a Monod
# saturation on surface nitrate times the day's light, normalised to 0..1.
# Roughly, on the track:
#
#     South Pacific gyre        0.02      the barren middle
#     mid-Atlantic subtropics   0.15
#     equatorial Pacific        0.45
#     Benguela                  0.58
#     Humboldt                  0.66
#     Southern Ocean, summer    0.70
#
# So an envelope of (0.45, 0.60, 1.0, 1.0) means "upwelling only" without the
# word upwelling appearing anywhere, and (0.0, 0.0, 0.25, 0.55) means "cannot
# compete where it is rich", which is the honest shape for an oligotrophic
# specialist.
ANY_PROD = (0.0, 0.0, 1.0, 1.0)

ROSTER = (
    # ----------------------------------------------------------------------
    # THE FORAGE FISH. Small, planktivorous, shoaling, and the reason the
    # upwellings are worth sailing through. Everything above them in the
    # water depends on their being here.
    # ----------------------------------------------------------------------

    # FishBase: 3-80 m, 13-23 C (pref 17-20.8), 14 cm common / 20 cm max,
    # trophic 2.9, pelagic-neritic. Distribution "dependent on the coastal
    # extent of the Peru Current" -- which is a fact about water, and the
    # envelope is how it gets said without naming the current.
    _f(ANCHOVETA, "ENGRAULIS RINGENS", "ANCHOVETA", "ANCHOVY", "12-20CM",
       14.0, 20.0, 2.9,
       temp=(13.0, 16.0, 21.0, 23.0), habitat=SHELF,
       prod=(0.45, 0.62, 1.0, 1.0),
       z=(3.0, 80.0), gait=SUBCARANGIFORM, shoal=1.00, swim_bl=2.6,
       note="the largest single-species fishery on Earth"),

    # FishBase: 0-200 m, 9-21 C, 20 cm common / 39.5 cm max, trophic 2.8,
    # pelagic-neritic. The same animal in the Benguela and the Humboldt, and
    # the reason those two look alike on the plate.
    _f(SARDINE, "SARDINOPS SAGAX", "SARDINE", "SARDINE", "15-30CM",
       20.0, 39.5, 2.8,
       temp=(9.0, 13.0, 20.0, 21.0), habitat=SHELF,
       prod=(0.35, 0.52, 1.0, 1.0),
       z=(0.0, 200.0), gait=SUBCARANGIFORM, shoal=1.00, swim_bl=2.4),

    # FishBase: 0-364 m (usual 0-200), 0-18 C, 30 cm common / 45 cm max,
    # trophic 3.4, benthopelagic, temperate. Schools strongly.
    _f(HERRING, "CLUPEA HARENGUS", "HERRING", "HERRING", "20-35CM",
       30.0, 45.0, 3.4,
       temp=(0.0, 4.0, 14.0, 18.0), habitat=SHELF,
       prod=(0.20, 0.38, 1.0, 1.0),
       z=(0.0, 200.0), gait=SUBCARANGIFORM, shoal=1.00, swim_bl=2.5),

    # FishBase: 0-1000 m (usual 0-200), 7-17.5 C, 30 cm common / 60 cm max,
    # trophic 3.6, pelagic-neritic. "Large schools near the surface."
    _f(MACKEREL, "SCOMBER SCOMBRUS", "MACKEREL", "MACKEREL", "25-40CM",
       30.0, 60.0, 3.6,
       temp=(7.0, 9.0, 16.0, 17.5), habitat=SHELF,
       prod=(0.15, 0.32, 1.0, 1.0),
       z=(0.0, 200.0), gait=CARANGIFORM, shoal=0.90, swim_bl=3.0),

    # FishBase: 10-100 m, 12-20 C, 20 cm max, trophic 3.1, pelagic-neritic.
    # The Iberian and North African shelf, which is Drake's first month.
    _f(PILCHARD_EU, "SARDINA PILCHARDUS", "PILCHARD", "SARDINE", "15-25CM",
       18.0, 27.5, 3.1,
       temp=(10.0, 13.0, 19.0, 22.0), habitat=SHELF,
       prod=(0.20, 0.38, 1.0, 1.0),
       z=(10.0, 100.0), gait=SUBCARANGIFORM, shoal=1.00, swim_bl=2.4),

    # FishBase: 0-300 m (usual 50-200), 10-27 C, 30 cm common / 64 cm max,
    # trophic 3.4, coastal pelagic. 60N-48S and explicitly "anti-tropical".
    #
    # THE ANTI-TROPICAL DISTRIBUTION IS THE INTERESTING PART, and it costs
    # nothing to reproduce: a species that lives in cool coastal water is
    # found in both hemispheres and not at the equator, without any rule
    # having to say so, because the equator is where that water is not. The
    # chub mackerel is in the Humboldt and the Benguela and the Iberian
    # shelf, and it is the clearest single case in the roster of one envelope
    # producing a disjunct range.
    _f(CHUB, "SCOMBER JAPONICUS", "CHUB MACKEREL", "MACKEREL", "25-45CM",
       30.0, 64.0, 3.4,
       temp=(10.0, 13.0, 22.0, 27.0), habitat=SHELF,
       prod=(0.15, 0.32, 1.0, 1.0),
       z=(50.0, 200.0), gait=CARANGIFORM, shoal=0.90, swim_bl=2.9),

    # FishBase: 10-306 m (usual 10-70), 14.1-22.6 C, 45 cm common / 70 cm
    # max, trophic 3.3, pelagic-oceanic. Ranges much further offshore than
    # the anchoveta, which is why it gets SLOPE and the anchoveta SHELF.
    _f(JACKMACK, "TRACHURUS MURPHYI", "JACK MACKEREL", "JACK", "30-50CM",
       45.0, 70.0, 3.3,
       temp=(14.1, 15.5, 20.0, 22.6), habitat=SLOPE,
       prod=(0.25, 0.45, 1.0, 1.0),
       z=(10.0, 306.0), gait=CARANGIFORM, shoal=0.85, swim_bl=2.8),

    # FishBase: 0-1000 m, -1.8 to 0.9 C, 15 cm common / 26.6 cm max, trophic
    # 3.2, pelagic-oceanic, polar. The forage fish of the Southern Ocean and
    # the coldest envelope in the roster.
    _f(SILVERFISH, "PLEURAGRAMMA ANTARCTICA", "SILVERFISH", "NOTOTHEN",
       "10-25CM", 15.0, 26.6, 3.2,
       temp=(-1.9, -1.8, 0.5, 1.5), habitat=SLOPE,
       prod=(0.20, 0.40, 1.0, 1.0),
       z=(0.0, 1000.0), gait=SUBCARANGIFORM, shoal=0.95, swim_bl=1.8),

    # ----------------------------------------------------------------------
    # THE OCEANIC PREDATORS. Fast, warm, and thinly spread -- which is what
    # the trophic term is for: they are common only where their prey is.
    # ----------------------------------------------------------------------

    # FishBase: 0-260 m, 15-30 C, 80 cm common / 110 cm max, trophic 4.4,
    # pelagic-oceanic. "Strong tendency to school in surface waters."
    _f(SKIPJACK, "KATSUWONUS PELAMIS", "SKIPJACK", "TUNA", "40-80CM",
       80.0, 110.0, 4.4,
       temp=(15.0, 20.0, 29.0, 30.0), habitat=OCEANIC,
       prod=(0.04, 0.12, 0.85, 1.0),
       z=(0.0, 260.0), gait=THUNNIFORM, shoal=0.70, swim_bl=2.2),

    # FishBase: 1-1602 m (usual 1-250), 15-31 C, 150 cm common / 239 cm max,
    # trophic 4.4. "Rarely caught below 250 m in tropical regions" -- oxygen,
    # not temperature, and the z range says so.
    _f(YELLOWFIN, "THUNNUS ALBACARES", "YELLOWFIN", "TUNA", "1.0-1.5M",
       150.0, 239.0, 4.4,
       temp=(15.0, 20.0, 30.0, 31.0), habitat=OCEANIC,
       prod=(0.04, 0.12, 0.85, 1.0),
       z=(1.0, 250.0), gait=THUNNIFORM, shoal=0.55, swim_bl=2.0),

    # FishBase: 0-985 m (usual 0-100), 3-30 C, 200 cm common / 458 cm max,
    # trophic 4.5. The widest thermal envelope of any tuna -- it is warm
    # blooded, which is the whole reason it can be off Norway and off the
    # Canaries in the same year.
    _f(BLUEFIN, "THUNNUS THYNNUS", "BLUEFIN", "TUNA", "1.5-3M",
       200.0, 458.0, 4.5,
       temp=(3.0, 7.5, 25.0, 30.0), habitat=OCEANIC,
       prod=(0.08, 0.20, 0.95, 1.0),
       z=(0.0, 200.0), gait=THUNNIFORM, shoal=0.60, swim_bl=1.8,
       note="a fraction of its pre-industrial biomass"),

    # FishBase: 0-20 m (usual 0-12), 18.2-27.6 C, 170 cm common / 250 cm max,
    # trophic 4.3, pelagic-oceanic. Solitary, and it lives in the top twelve
    # metres of the open ocean -- so it is one of the few things that shows
    # up in a gyre.
    _f(WAHOO, "ACANTHOCYBIUM SOLANDRI", "WAHOO", "MACKEREL", "1-2M",
       170.0, 250.0, 4.3,
       temp=(18.2, 21.0, 27.0, 27.6), habitat=OCEANIC,
       prod=(0.0, 0.02, 0.60, 1.0),
       z=(0.0, 20.0), gait=THUNNIFORM, shoal=0.10, swim_bl=2.4),

    # FishBase: 0-1000 m, 22-31 C, 290 cm common / 500 cm max, trophic 4.5.
    # "Typically found as scattered individuals rather than schools" and
    # "prefers blue water" -- so a low productivity preference is not an
    # invention, it is the species account.
    _f(MARLIN, "MAKAIRA NIGRICANS", "BLUE MARLIN", "BILLFISH", "2-4M",
       290.0, 500.0, 4.5,
       temp=(22.0, 24.0, 30.0, 31.0), habitat=OCEANIC,
       prod=(0.0, 0.02, 0.55, 0.95),
       z=(0.0, 200.0), gait=THUNNIFORM, shoal=0.0, swim_bl=1.6),

    # FishBase: 0-85 m (usual 5-10), 21-30 C, 100 cm common / 210 cm max,
    # trophic 4.4, pelagic-neritic. Lives in the top ten metres and follows
    # flotsam, which is why every account of a tropical crossing mentions it.
    _f(DORADO, "CORYPHAENA HIPPURUS", "DORADO", "DOLPHINFISH", "0.6-1.2M",
       100.0, 210.0, 4.4,
       temp=(21.0, 24.0, 29.0, 30.0), habitat=OCEANIC,
       prod=(0.02, 0.08, 0.75, 1.0),
       z=(0.0, 30.0), gait=CARANGIFORM, shoal=0.35, swim_bl=2.6),

    # FishBase: 0-20 m, 23.2-29.2 C, 20 cm common / 30 cm max, trophic 3.0.
    # The single most-reported animal in every sixteenth-century account of
    # the tropics, for the obvious reason.
    _f(FLYINGFISH, "EXOCOETUS VOLITANS", "FLYING FISH", "FLYINGFISH",
       "15-25CM", 20.0, 30.0, 3.0,
       temp=(23.2, 25.0, 29.0, 29.2), habitat=OCEANIC,
       prod=(0.0, 0.02, 0.70, 1.0),
       z=(0.0, 20.0), gait=CARANGIFORM, shoal=0.75, swim_bl=3.2),

    # FishBase: 0-1082 m (usual 1-220), 7-21 C, 335 cm common / 400 cm max,
    # trophic 4.4. "Probably the widest ranging chondrichthyian", 70N-55S,
    # and the envelope reproduces that without a range map.
    _f(BLUESHARK, "PRIONACE GLAUCA", "BLUE SHARK", "SHARK", "2-3.5M",
       335.0, 400.0, 4.4,
       temp=(7.0, 10.0, 20.0, 21.0), habitat=OCEANIC,
       prod=(0.02, 0.08, 0.80, 1.0),
       z=(1.0, 220.0), gait=THUNNIFORM, shoal=0.0, swim_bl=0.9),

    # FishBase: 0-1928 m (usual 0-100), 18-30 C, 1000 cm common / 2000 cm
    # max, trophic 3.6. The largest fish there is, and a filter feeder, so
    # it goes where the plankton is -- a high productivity preference on an
    # animal that eats at trophic level 3.6.
    _f(WHALESHARK, "RHINCODON TYPUS", "WHALE SHARK", "SHARK", "5-12M",
       1000.0, 2000.0, 3.6,
       temp=(18.0, 21.0, 29.0, 30.0), habitat=OCEANIC,
       prod=(0.10, 0.30, 1.0, 1.0),
       z=(0.0, 100.0), gait=THUNNIFORM, shoal=0.0, swim_bl=0.4),

    # FishBase: 0-146 m, 26-29 C, 60 cm common / 120 cm max, trophic 4.5,
    # reef-associated. Ternate and the Moluccas, which is where Drake spent
    # the winter of 1579 -- reached by an envelope, not by a place name.
    _f(TREVALLY, "CARANX SEXFASCIATUS", "TREVALLY", "JACK", "40-80CM",
       60.0, 120.0, 4.5,
       temp=(22.3, 26.0, 29.0, 30.0), habitat=REEF,
       prod=(0.05, 0.15, 0.90, 1.0),
       z=(1.0, 96.0), gait=CARANGIFORM, shoal=0.80, swim_bl=2.8),

    # FishBase: 0-50 m (usually to 20), 24.6-29 C, 36.5 cm max, trophic 3.8,
    # reef-associated, 35N-35S Indo-Pacific. The reef's resident ambush
    # predator: it does not shoal and it does not travel.
    _f(GROUPER, "EPINEPHELUS MERRA", "GROUPER", "SERRANID", "20-36CM",
       22.0, 36.5, 3.8,
       temp=(24.6, 26.0, 29.0, 30.0), habitat=REEF,
       prod=(0.03, 0.10, 0.90, 1.0),
       z=(0.0, 50.0), gait=CARANGIFORM, shoal=0.0, swim_bl=1.2),

    # FishBase: 1-60 m, 26.1-29.1 C, 35 cm common / 60 cm max, trophic 3.4,
    # reef-associated. "Forms schools in midwater and feeds on zooplankton"
    # -- the reef's equivalent of the anchoveta, and the reason the Moluccas
    # have anything for the trevally and the grouper to eat.
    _f(FUSILIER, "CAESIO CUNING", "FUSILIER", "CAESIONID", "25-45CM",
       35.0, 60.0, 3.4,
       temp=(26.1, 27.0, 29.1, 30.0), habitat=REEF,
       prod=(0.03, 0.10, 1.0, 1.0),
       z=(1.0, 60.0), gait=CARANGIFORM, shoal=0.95, swim_bl=2.5),

    # ----------------------------------------------------------------------
    # THE SHELF AND SLOPE. Demersal and benthopelagic: these are the species
    # that make the seafloor worth drawing, because they are only ever
    # present when it is in frame.
    # ----------------------------------------------------------------------

    # FishBase: 0-600 m (usual 150-200), 0-15 C, 100 cm common / 200 cm max,
    # trophic 4.1, benthopelagic.
    _f(COD, "GADUS MORHUA", "COD", "GADOID", "0.5-1M",
       100.0, 200.0, 4.1,
       temp=(0.0, 2.0, 12.0, 15.0), habitat=SHELF,
       prod=(0.15, 0.30, 1.0, 1.0),
       z=(20.0, 600.0), gait=SUBCARANGIFORM, shoal=0.30, swim_bl=1.4,
       note="pre-industrial biomass was many times this"),

    # FishBase: 18-1075 m (usual 70-400), 6.9-15.4 C, 45 cm common / 140 cm
    # max, trophic 4.4, demersal.
    _f(HAKE_EU, "MERLUCCIUS MERLUCCIUS", "HAKE", "GADOID", "40-70CM",
       45.0, 140.0, 4.4,
       temp=(6.9, 9.0, 14.0, 15.4), habitat=SLOPE,
       prod=(0.12, 0.28, 1.0, 1.0),
       z=(70.0, 400.0), gait=SUBCARANGIFORM, shoal=0.25, swim_bl=1.3),

    # FishBase: 50-500 m, 9.3-14 C, 50 cm common / 87 cm max, trophic 4.3,
    # bathydemersal, 5S-46S off Chile and Peru. "Exhibits vertical migration
    # to midwater at night for feeding" -- so it is a demersal fish with a
    # migration, and it gets one.
    _f(HAKE_CL, "MERLUCCIUS GAYI", "PACIFIC HAKE", "GADOID", "40-70CM",
       50.0, 87.0, 4.3,
       temp=(9.3, 10.0, 13.0, 14.0), habitat=SLOPE,
       prod=(0.20, 0.38, 1.0, 1.0),
       z=(50.0, 500.0), gait=SUBCARANGIFORM, shoal=0.30, swim_bl=1.3,
       dvm=((150.0, 500.0), (50.0, 250.0))),

    # FishBase: 50-1000 m (usual 150-450), 7.7-14.4 C, 50 cm common / 140 cm
    # max, trophic 3.9, bathydemersal, 11S-37S. The Benguela's answer to the
    # Humboldt's hake, and a good illustration of why the range table is
    # needed: these two are near-identical animals in near-identical water,
    # separated by the whole width of the South Atlantic.
    _f(HAKE_ZA, "MERLUCCIUS CAPENSIS", "CAPE HAKE", "GADOID", "40-70CM",
       50.0, 140.0, 3.9,
       temp=(7.7, 9.0, 13.0, 14.4), habitat=SLOPE,
       prod=(0.20, 0.38, 1.0, 1.0),
       z=(150.0, 450.0), gait=SUBCARANGIFORM, shoal=0.30, swim_bl=1.3),

    # FishBase: 50-800 m (usual 100-200), 4.5-18 C, 50 cm common / 95 cm max,
    # trophic 4.0, benthopelagic, 20S-56S. The Patagonian shelf's dominant
    # predator and one of the largest fisheries in the South Atlantic.
    _f(HAKE_AR, "MERLUCCIUS HUBBSI", "ARGENTINE HAKE", "GADOID", "40-70CM",
       50.0, 95.0, 4.0,
       temp=(4.5, 5.5, 12.0, 18.0), habitat=SLOPE,
       prod=(0.18, 0.34, 1.0, 1.0),
       z=(100.0, 200.0), gait=SUBCARANGIFORM, shoal=0.30, swim_bl=1.3),

    # FishBase: 30-200 m, 4.6-18.7 C, 10 cm common / 17 cm max, trophic 2.5,
    # pelagic-neritic, 21S-50S. The Humboldt's anchoveta has an Atlantic
    # counterpart, and the pair is the clearest case in the roster of the
    # range table doing its job: near-identical envelopes, opposite coasts.
    _f(ANCHOITA, "ENGRAULIS ANCHOITA", "ANCHOVY", "ANCHOVY", "8-17CM",
       10.0, 17.0, 2.5,
       temp=(4.6, 7.0, 16.0, 18.7), habitat=SHELF,
       prod=(0.25, 0.42, 1.0, 1.0),
       z=(30.0, 200.0), gait=SUBCARANGIFORM, shoal=1.00, swim_bl=2.6),

    # FishBase: 0-550 m (usual 100-500), 13-18 C, 75 cm common / 200 cm max,
    # trophic 3.6, benthopelagic. Circumpolar in the southern hemisphere,
    # 21S-56S -- the Benguela and the Chilean coast both.
    _f(SNOEK, "THYRSITES ATUN", "SNOEK", "SNAKE MACKEREL", "0.6-1.2M",
       75.0, 200.0, 3.6,
       temp=(6.2, 13.0, 18.0, 19.0), habitat=SLOPE,
       prod=(0.25, 0.45, 1.0, 1.0),
       z=(100.0, 500.0), gait=ANGUILLIFORM, shoal=0.55, swim_bl=1.9),

    # FishBase: 30-500 m, 4.5-9.7 C, 80 cm common / 115 cm max, trophic 3.8.
    # "Schooling species which are concentrated on the outer part of the
    # continental shelf" -- so SLOPE, and a shoal term.
    _f(GRENADIER, "MACRURONUS MAGELLANICUS", "GRENADIER", "GADOID", "0.6-1M",
       80.0, 115.0, 3.8,
       temp=(4.5, 5.5, 9.0, 9.7), habitat=SLOPE,
       prod=(0.20, 0.38, 1.0, 1.0),
       z=(30.0, 500.0), gait=ANGUILLIFORM, shoal=0.70, swim_bl=1.5),

    # FishBase: 0-2144 m (usual 70-1500), 1.8-8.8 C, 70 cm common / 215 cm
    # max, trophic 4.5. 33S-66S. The deepest-living thing in the roster that
    # is not mesopelagic, and the reason the panel's lower half is not empty
    # off Patagonia.
    _f(TOOTHFISH, "DISSOSTICHUS ELEGINOIDES", "TOOTHFISH", "NOTOTHEN",
       "0.7-2M", 70.0, 215.0, 4.5,
       temp=(1.8, 2.5, 7.0, 8.8), habitat=SLOPE,
       prod=(0.15, 0.30, 1.0, 1.0),
       z=(70.0, 1500.0), gait=SUBCARANGIFORM, shoal=0.0, swim_bl=1.0),

    # FishBase: 0-700 m (usual 30-250), -1.1 to 2.9 C, 35 cm common / 66 cm
    # max, trophic 3.2, benthopelagic, polar. Has no haemoglobin at all,
    # which is only possible in water this cold.
    _f(ICEFISH, "CHAMPSOCEPHALUS GUNNARI", "ICEFISH", "NOTOTHEN", "25-50CM",
       35.0, 66.0, 3.2,
       temp=(-1.9, -1.1, 2.5, 2.9), habitat=SHELF,
       prod=(0.20, 0.38, 1.0, 1.0),
       z=(30.0, 250.0), gait=CARANGIFORM, shoal=0.60, swim_bl=1.6,
       note="no haemoglobin -- only possible this cold"),

    # ----------------------------------------------------------------------
    # THE MESOPELAGIC. The largest fish biomass in the ocean, present over
    # every deep water on the track, and the reason the panel is never bare.
    # Three of the four migrate, which is what makes dusk worth watching.
    # ----------------------------------------------------------------------

    # FishBase: 0-1407 m (usual 300-400), 1.6-12.8 C, 10.3 cm max, trophic
    # 3.1. DVM quoted exactly: "375-800 m during daytime and 12-200 m during
    # night". That one sentence is the entire dusk migration.
    _f(LANTERNFISH, "BENTHOSEMA GLACIALE", "LANTERNFISH", "MYCTOPHID",
       "5-10CM", 7.0, 10.3, 3.1,
       temp=(1.6, 3.0, 12.0, 14.0), habitat=MESO,
       prod=ANY_PROD,
       z=(375.0, 800.0), gait=CARANGIFORM, shoal=0.85, swim_bl=2.0,
       dvm=((375.0, 800.0), (12.0, 200.0)),
       note="the most abundant vertebrates on Earth"),

    # FishBase: 391-2056 m, "between 700 and 1500 m during the day; between
    # 20 and 200 m at night", 3-8.8 C, 10.2 cm max, trophic 3.4. All three
    # oceans, 42N-65S.
    #
    # THE LONGEST COMMUTE ON THE PANEL, and the reason there are two
    # lanternfish rather than one. Benthosema above it is a boreal North
    # Atlantic animal and stops at 7 N; this one carries the family across
    # the tropics and down to the Subtropical Convergence, which is most of
    # the track. Its migration is close to fifteen hundred metres, twice a
    # day, by an animal ten centimetres long -- and on a log depth axis that
    # is a layer sweeping up through two thirds of the panel at dusk.
    _f(WARMING, "CERATOSCOPELUS WARMINGII", "LANTERNFISH", "MYCTOPHID",
       "5-10CM", 7.5, 10.2, 3.4,
       temp=(3.0, 4.0, 8.8, 11.0), habitat=MESO,
       prod=ANY_PROD,
       z=(700.0, 1500.0), gait=CARANGIFORM, shoal=0.85, swim_bl=2.0,
       dvm=((700.0, 1500.0), (20.0, 200.0))),

    # FishBase: 10-2000 m (usual 200-900), 3.9-16.3 C, 4.6 cm max, trophic
    # 3.1. Does NOT migrate -- "generally horizontally oriented", it hangs.
    # The most abundant vertebrate genus there is, and the widest thermal
    # envelope in the roster, so it is present essentially everywhere deep.
    _f(BRISTLEMOUTH, "CYCLOTHONE BRAUERI", "BRISTLEMOUTH", "GONOSTOMATID",
       "3-5CM", 3.5, 4.6, 3.1,
       temp=(3.9, 6.0, 16.0, 18.0), habitat=MESO,
       prod=ANY_PROD,
       z=(200.0, 900.0), gait=ANGUILLIFORM, shoal=0.20, swim_bl=1.2,
       note="the most abundant vertebrate genus on Earth"),
    # STANDS FOR THE GENUS, and the OBIS check is what made that explicit:
    # braueri itself is Atlantic-centred and has no records in the Moluccas,
    # while Cyclothone as a genus is in every ocean and is the most abundant
    # vertebrate genus there is. The plate prints CYCLOTHONE, which is true at
    # the rank it is being used at. Every roster of thirty-five species
    # standing in for thousands does this somewhere; this is the one place it
    # is load-bearing, so it is the one place it is written down.

    # FishBase: 0-2400 m (usual 100-700), 5.5-21.3 C, 5.1 cm max, trophic
    # 3.1. "Marked vertical migrations": day 200-700 (peak 350-550), night
    # 100-650 (preferring 150-380). A shorter migration than the myctophid's
    # and the numbers say so.
    _f(HATCHETFISH, "ARGYROPELECUS HEMIGYMNUS", "HATCHETFISH", "STERNOPTYCHID",
       "2-5CM", 3.0, 5.1, 3.1,
       temp=(5.5, 8.0, 20.0, 21.3), habitat=MESO,
       prod=ANY_PROD,
       z=(350.0, 550.0), gait=CARANGIFORM, shoal=0.30, swim_bl=1.4,
       dvm=((350.0, 550.0), (150.0, 380.0))),

    # FishBase: 200-4700 m (usual 494-1000), 2.8-11.4 C, 35 cm max, trophic
    # 4.2, bathypelagic. "May migrate to near-surface waters at night", and
    # it eats myctophids -- so it follows them up, which is the correct
    # reason for a predator to migrate.
    _f(VIPERFISH, "CHAULIODUS SLOANI", "VIPERFISH", "STOMIID", "20-35CM",
       25.0, 35.0, 4.2,
       temp=(2.8, 5.0, 11.0, 13.0), habitat=MESO,
       prod=ANY_PROD,
       z=(494.0, 1000.0), gait=ANGUILLIFORM, shoal=0.0, swim_bl=0.8,
       dvm=((494.0, 1000.0), (50.0, 600.0))),
)

# --------------------------------------------------------------------------
# 1b. RANGE  -  where a species has actually got to
# --------------------------------------------------------------------------
#
# THIS IS A DIFFERENT KIND OF FACT FROM THE ENVELOPE, AND IT GETS ITS OWN
# TABLE FOR THAT REASON.
#
# The envelope answers "what water can this animal live in". It is physiology,
# it is measurable in a tank, and it is the whole of the model above. Run on
# its own it produced a result that is both completely logical and completely
# wrong: Atlantic cod and Atlantic herring in the Benguela, off South Africa,
# at high suitability.
#
# They are not wrong because the water is wrong. The Benguela is an eastern
# boundary upwelling at 15 C over a 150 m shelf, and so is the North Sea in
# most months -- the envelope matched because the water genuinely matches. Cod
# are absent from the Benguela because they never got there: the tropical
# Atlantic is a two-thousand-mile barrier of water too warm to cross, and no
# cod has ever been on the other side of it.
#
# That is a fact about history and dispersal, not about the sea, and folding
# it into the envelope would have been a lie about what an envelope means.
# AquaMaps does the same thing for the same reason, calling it a bounding box.
#
# So the thesis survives, in its real form: THE ENVIRONMENT DECIDES
# SUITABILITY AND HISTORY DECIDES REACHABILITY. Nothing here says PERU ->
# ANCHOVETA. It says the anchoveta is a South-East Pacific animal, which is a
# fact about the anchoveta.
#
# Latitude bands are FishBase distribution limits, quoted. Basins are read off
# the same distribution statements.

ATLANTIC, INDIAN, PACIFIC = 1, 2, 4
ALL_BASINS = ATLANTIC | INDIAN | PACIFIC
INDO_PACIFIC = INDIAN | PACIFIC

# (south limit, north limit), basins
RANGE = {
    # -- North Atlantic endemics. The reason this table exists.
    COD:         ((35.0,  83.0), ATLANTIC),
    HERRING:     ((35.0,  80.0), ATLANTIC),
    MACKEREL:    ((30.0,  75.0), ATLANTIC),
    PILCHARD_EU: ((15.0,  60.0), ATLANTIC),
    HAKE_EU:     ((18.0,  76.0), ATLANTIC),
    HAKE_ZA:     ((-37.0, -11.0), ATLANTIC),
    BLUEFIN:     ((-58.0, 69.0), ATLANTIC),
    LANTERNFISH: ((  7.0, 81.0), ATLANTIC),

    # -- South-East Pacific. The Humboldt's own.
    ANCHOVETA:   ((-43.0, -5.0), PACIFIC),
    HAKE_CL:     ((-46.0, -5.0), PACIFIC),
    # PACIFIC only. It was given the Atlantic as well for the Argentine
    # shelf, where it is marginal -- and the basin test cannot say "south-west
    # Atlantic", so that allowance also let it into the Benguela, where the
    # jack mackerel is Trachurus capensis and OBIS has no record of murphyi at
    # all. Losing a marginal Argentine occurrence is the cheaper error.
    JACKMACK:    ((-51.0,  2.0), PACIFIC),

    # Anti-tropical, and the latitude band cannot express that -- a single
    # (south, north) pair covering both hemispheres necessarily spans the
    # equator. It does not need to: the thermal envelope excludes the tropics
    # on its own, which is the point made in the species note.
    CHUB:        ((-48.0,  60.0), ALL_BASINS),

    # -- southern hemisphere, circumpolar or nearly so
    SNOEK:       ((-56.0, -21.0), ALL_BASINS),
    GRENADIER:   ((-60.0, -34.0), PACIFIC | ATLANTIC),
    HAKE_AR:     ((-56.0, -20.0), ATLANTIC),
    ANCHOITA:    ((-50.0, -21.0), ATLANTIC),
    TOOTHFISH:   ((-66.0, -33.0), ALL_BASINS),
    ICEFISH:     ((-66.0, -48.0), ALL_BASINS),
    SILVERFISH:  ((-78.0, -60.0), ALL_BASINS),

    # -- Indo-Pacific reef. Absent from the Atlantic entirely: the Isthmus of
    #    Panama closed three million years ago and the Benguela is too cold.
    TREVALLY:    ((-36.0, 32.0), INDO_PACIFIC),
    GROUPER:     ((-35.0, 35.0), INDO_PACIFIC),
    FUSILIER:    ((-28.0, 31.0), INDO_PACIFIC),

    # -- genuinely cosmopolitan. Every ocean, and the latitude band is the
    #    only thing that limits them.
    SARDINE:     ((-47.0, 61.0), ALL_BASINS),
    SKIPJACK:    ((-47.0, 63.0), ALL_BASINS),
    YELLOWFIN:   ((-50.0, 50.0), ALL_BASINS),
    WAHOO:       ((-48.0, 59.0), ALL_BASINS),
    MARLIN:      ((-45.0, 50.0), ALL_BASINS),
    DORADO:      ((-40.0, 50.0), ALL_BASINS),
    FLYINGFISH:  ((-36.0, 44.0), ALL_BASINS),
    BLUESHARK:   ((-55.0, 70.0), ALL_BASINS),
    WHALESHARK:  ((-48.0, 45.0), ALL_BASINS),
    # -48, not the -65 FishBase gives as an extreme: the species account says
    # "south to the Subtropical Convergence", which is about 45 S, and the
    # OBIS cross-check found no record of it anywhere in the Drake Passage.
    # A limit taken from a distribution statement beats one taken from the
    # furthest stray specimen.
    WARMING:     ((-48.0, 42.0), ALL_BASINS),
    BRISTLEMOUTH:((-40.0, 67.0), ALL_BASINS),
    HATCHETFISH: ((-56.0, 60.0), ALL_BASINS),
    VIPERFISH:   ((-56.0, 70.0), ALL_BASINS),
}


# --------------------------------------------------------------------------
# 1c. MORPHOLOGY  -  which body plan each species is drawn with
# --------------------------------------------------------------------------
#
# Sixteen plans for thirty-three species, and where several share one they
# still differ: draw.py's Form is scale-free, and the length, the swimming
# mode and the drawn size come from the species record. Two scombrids are the
# same plan and not the same drawing.
#
# The dependency runs one way -- fish imports draw, draw imports nothing --
# so the morphology module stays a pure function of shape and can be tested
# without an ocean.
FORM = {
    ANCHOVETA: draw.ANCHOVYISH, SARDINE: draw.CLUPEID,
    HERRING: draw.CLUPEID, PILCHARD_EU: draw.CLUPEID,
    MACKEREL: draw.MACKERELISH, CHUB: draw.MACKERELISH,
    JACKMACK: draw.CARANGID, TREVALLY: draw.CARANGID,
    SKIPJACK: draw.SCOMBRID, YELLOWFIN: draw.SCOMBRID,
    BLUEFIN: draw.SCOMBRID, WAHOO: draw.WAHOOISH,
    MARLIN: draw.BILLFISH, DORADO: draw.CORYPHAENID,
    FLYINGFISH: draw.EXOCOETID,
    BLUESHARK: draw.SHARK, WHALESHARK: draw.WHALESHARKISH,
    COD: draw.GADOID, HAKE_EU: draw.GADOID, HAKE_CL: draw.GADOID,
    HAKE_ZA: draw.GADOID, HAKE_AR: draw.GADOID, ANCHOITA: draw.ANCHOVYISH,
    GRENADIER: draw.GRENADIERISH,
    TOOTHFISH: draw.NOTOTHENIOID, ICEFISH: draw.NOTOTHENIOID,
    SILVERFISH: draw.NOTOTHENIOID,
    SNOEK: draw.GEMPYLID,
    GROUPER: draw.SERRANID, FUSILIER: draw.CAESIONID,
    LANTERNFISH: draw.MYCTOPHID, WARMING: draw.MYCTOPHID,
    BRISTLEMOUTH: draw.GONOSTOMATID, HATCHETFISH: draw.STERNOPTYCHID,
    VIPERFISH: draw.STOMIID,
}


def basin_at(lat, lon):
    """Which ocean this is, coarsely.

    Coarse on purpose. The only job is to keep an Indo-Pacific reef fish out
    of the Atlantic and an anchoveta out of the Benguela, and both of those
    are decided by continents thousands of kilometres wide. A precise basin
    mask would be a second grid in flash to answer a question that two
    comparisons answer.

    Two boundaries need the latitude, and they are the two the track crosses:

        the Americas    the Isthmus of Panama is at 9 N, so north of it the
                        divide runs up to about 100 W (the Gulf of Mexico is
                        Atlantic, California is Pacific) and south of it down
                        the Andes at about 70 W (Valparaiso is Pacific at
                        71.6 W, the Rio de la Plata is Atlantic at 56 W).
        the Southern    below 45 S there is no divide at all. The Southern
        Ocean           Ocean is continuous, which is why so much of the
                        southern roster is circumpolar."""
    if lat < -45.0:
        return ALL_BASINS
    west = -100.0 if lat >= 9.0 else -70.0
    if west <= lon < 20.0:
        return ATLANTIC
    if 20.0 <= lon < 120.0:
        return INDIAN
    return PACIFIC


def reachable(key, lat, lon):
    """Has this species got here at all? Independent of whether it would like
    the water if it had."""
    r = RANGE.get(key)
    if r is None:
        return True
    (south, north), basins = r
    if not south <= lat <= north:
        return False
    return bool(basins & basin_at(lat, lon))


BY_KEY = {f.key: f for f in ROSTER}
ALL_KEYS = tuple(f.key for f in ROSTER)

# The mesopelagic. Present over any deep water anywhere on the track, so when
# nothing else suits, these are what is left -- and that is not a fallback,
# it is the truth about a subtropical gyre.
#
# Derived from the habitat class rather than typed out, because it is used to
# split the panel into two bands and a species left off the list by hand
# would be allocated to the wrong half of the screen for the rest of the
# voyage. There is exactly one definition of "mesopelagic" in this file.
MESOPELAGIC = tuple(f.key for f in ROSTER if f.bottom is MESO[0])
MIGRATORS = tuple(f.key for f in ROSTER if f.dvm_day is not None)
FORAGE = tuple(f.key for f in ROSTER if f.trophic < 3.5)
PREDATORS = tuple(f.key for f in ROSTER if f.trophic >= 4.0)


# --------------------------------------------------------------------------
# 2. THE ENVELOPE
# --------------------------------------------------------------------------

def trapezoid(v, env):
    """Kaschner's response curve: 0 outside [lo, hi], 1 across [plo, phi],
    linear on the ramps.

    Guarded against degenerate envelopes -- a species whose preferred range
    touches its absolute range gives a zero-width ramp, and a division by
    zero there would be a silent NaN rather than a crash, which is the worst
    of both."""
    lo, plo, phi, hi = env
    if v <= lo or v >= hi:
        return 0.0
    if v < plo:
        return (v - lo) / (plo - lo) if plo > lo else 1.0
    if v <= phi:
        return 1.0
    return (hi - v) / (hi - phi) if hi > phi else 1.0


EPI_Z = 200.0                # the base of the sunlit zone
SURFACE_REF = 10.0           # where "sea surface temperature" is measured


def temp_depth(fish):
    """The depth at which this species' thermal envelope is evaluated.

    Two regimes, split at the base of the sunlit zone, and the split is about
    WHERE THE PUBLISHED NUMBER CAME FROM rather than about the fish.

    A species living mostly above 200 m has its temperature range derived
    from occurrence records matched against SEA SURFACE temperature -- that
    is what the satellite measures and what the databases join on. So the
    envelope of an epipelagic fish must be tested against the surface, and
    testing it at the midpoint of its depth range instead quietly converts a
    surface tolerance into a thermocline tolerance.

    That is not hypothetical. Chub mackerel is explicitly anti-tropical --
    "absent from the Indian Ocean except for South Africa" -- and its 27 C
    ceiling excludes a 29 C tropical surface exactly as it should. Evaluated
    at the midpoint of its 50-200 m range it was being offered 22 C
    thermocline water instead, and it turned up in the Moluccas, on the
    equator, at high suitability.

    Below 200 m the opposite holds: those ranges come from nets and CTD
    casts at depth, and a bristlemouth's 3.9-16.3 C is the water it is
    actually in. Its midpoint of 550 m is about 10 C in the tropics and 4 C
    in the Southern Ocean -- a far narrower spread than the forty degrees the
    surface spans, and precisely why the mesopelagic species are cosmopolitan
    and the surface ones are not.

    For a migrator the DAY band is used. It is the deeper and more thermally
    stable half, and a value that swung twice a day would make presence
    itself flicker on and off at dusk -- a rendering artefact dressed up as
    biology."""
    lo, hi = fish.dvm_day if fish.dvm_day is not None else fish.z
    mid = 0.5 * (lo + hi)
    return SURFACE_REF if mid < EPI_Z else mid


def suitability(fish, temp, bottom_m, prod, shore_km):
    """Relative environmental suitability, 0..1.

    The axes MULTIPLY, which is Liebig's law of the minimum in its
    multiplicative form and is what AquaMaps does: a species needs every axis
    to be acceptable, and being perfect on three of them does not buy any
    tolerance on the fourth. An anchoveta in water of the right temperature
    and productivity but four kilometres deep scores zero, and should."""
    if temp is None:
        return 0.0
    s = trapezoid(temp, fish.temp)
    if s <= 0.0:
        return 0.0
    s *= trapezoid(bottom_m, fish.bottom)
    if s <= 0.0:
        return 0.0
    s *= trapezoid(prod, fish.prod)
    if s <= 0.0:
        return 0.0
    return s * trapezoid(shore_km, fish.shore)


def assemblage(temp_at, bottom_m, prod, shore_km, lat=None, lon=None,
               floor=0.02):
    """[(key, suitability), ...] for everything that can live in this water,
    richest first.

    `temp_at` is a CALLABLE, depth in metres -> temperature, not a scalar.
    That is the whole of the surface-versus-depth fix: each species is asked
    about the water it actually lives in rather than the water on top of it.
    In practice it is Environment.temperature bound to the current day.

    The floor exists because a trapezoid has hard zeros and four of them
    multiplied make a lot of exact zeros. Without it, water that is slightly
    wrong for everything returns an empty list and the panel goes blank --
    and blank is never the right answer, because there is no water on this
    planet with no fish in it."""
    out = []
    for f in ROSTER:
        if lat is not None and not reachable(f.key, lat, lon):
            continue
        s = suitability(f, temp_at(temp_depth(f)), bottom_m, prod, shore_km)
        if s > floor:
            out.append((f.key, s))
    out.sort(key=lambda r: -r[1])
    return out


# --------------------------------------------------------------------------
# 3. VERTICAL DISTRIBUTION
# --------------------------------------------------------------------------
#
# Where in the column a fish is drawn. Two regimes, and the difference
# between them is the best thing on the panel.

def depth_band(fish, night):
    """(top, bottom) metres for this species right now.

    A migrator has two bands and is in one or the other; everything else has
    one band and stays in it. Interpolating between the two at dusk is done
    by the caller, which owns the clock."""
    if fish.dvm_day is None:
        return fish.z
    return fish.dvm_night if night else fish.dvm_day


def migrate_f(sun_elev):
    """0 at full day, 1 at full night, smooth across the twilight.

    Driven off solar elevation rather than off a clock time, so the migration
    happens at the right moment at every latitude and on every date -- which
    matters on a track that reaches 56 S in the southern winter, where the
    day is five hours long. The threshold is civil twilight, near enough:
    the ascent begins as the sun goes down and the layer is up by full dark.

    Smoothstep rather than linear. The real ascent is not at constant speed
    -- it is fastest in the middle -- and more to the point a linear ramp
    starts and stops with a visible corner on a panel this size."""
    lo, hi = -8.0, 2.0
    u = (hi - sun_elev) / (hi - lo)
    u = max(0.0, min(1.0, u))
    return u * u * (3.0 - 2.0 * u)


def swim_depth(fish, sun_elev, r):
    """Where one individual sits, in metres.

    `r` is that individual's fixed 0..1 rank within its band, so a fish keeps
    its position in the layer as the layer moves rather than being
    re-randomised every frame -- the layer rises as a body, which is what a
    scattering layer does and is the whole visual point of it."""
    if fish.dvm_day is None:
        lo, hi = fish.z
        return lo + (hi - lo) * r
    f = migrate_f(sun_elev)
    d_lo, d_hi = fish.dvm_day
    n_lo, n_hi = fish.dvm_night
    lo = d_lo + (n_lo - d_lo) * f
    hi = d_hi + (n_hi - d_hi) * f
    return lo + (hi - lo) * r


# --------------------------------------------------------------------------
# 4. DRAWN SIZE, AND THE LIE IN IT
# --------------------------------------------------------------------------
#
# The panel spans a thousand metres of depth. At true scale a 14 cm anchoveta
# is a third of a pixel and a 10 m whale shark is twenty -- so true scale
# renders the entire forage base invisible and shows only the sharks, which
# is exactly backwards from what is in the water.
#
# So size is compressed, on a power law, and the exponent is the whole of the
# decision:
#
#     p = 1.0    true scale. Anchoveta invisible.
#     p = 0.40   whale shark 5.5x the anchoveta, against a true 71x
#     p = 0.0    everything the same size. The key plate does this, on
#                purpose, because it is comparing morphologies.
#
# 0.40 is chosen so that the smallest thing in the roster -- a 3.5 cm
# bristlemouth -- is still about ten pixels and therefore still a drawing
# rather than a smudge, while the largest is under a third of the panel.
#
# THE ORDERING IS PRESERVED, which is the part that matters. Every fish is
# drawn smaller than every fish genuinely larger than it, so the panel never
# tells a lie about which of two species is bigger. It only compresses by how
# much -- and the key plate prints the real length range underneath, which is
# where that compression gets corrected.
SIZE_EXP = 0.40
SIZE_PX = 6.0              # pixels at 1 cm, before the exponent


def draw_length(fish, jitter=1.0):
    """Drawn length in pixels for one individual."""
    return SIZE_PX * (fish.len_common * jitter) ** SIZE_EXP


# --------------------------------------------------------------------------
# 5. MOTION
# --------------------------------------------------------------------------
#
# Tail-beat frequency against length, from Bainbridge 1958, whose result has
# survived seventy years: for a fish swimming steadily, speed in body lengths
# per second is very nearly (3f - 4)/4 with f in beats per second. Inverted,
# a fish cruising at 2 BL/s beats at about 4 Hz -- and since BL/s is roughly
# size-independent while absolute speed is not, beat frequency falls with
# length exactly as everyone has always observed.
#
# It is inverted here rather than tabulated because that keeps one number per
# species (swim_bl) doing both jobs, and because a table of beat frequencies
# would be twenty-six numbers nobody could check.

def beat_hz(fish):
    """Tail beats per second at cruise. Bainbridge 1958, inverted."""
    return max(0.6, (4.0 * fish.swim_bl + 4.0) / 3.0)


# How straight a course each mode holds, in seconds before the heading
# decorrelates. A thunniform swimmer is a torpedo and an anguilliform one
# is not; this is the same TURN_TAU idea as the plankton had, with values
# that suit animals three orders of magnitude larger.
TURN_TAU = {
    THUNNIFORM: 22.0,
    CARANGIFORM: 11.0,
    SUBCARANGIFORM: 9.0,
    ANGUILLIFORM: 6.0,
}

# Shoaling. A shoal is not a drawing decision, it is a coupling: each fish
# steers toward the mean heading of its species, and `shoal` is how hard.
# At 1.0 an anchoveta shoal turns as one animal; at 0.0 a marlin ignores
# every other marlin, which is what a marlin does.
SHOAL_K = 2.2              # gain on the heading correction, per second
