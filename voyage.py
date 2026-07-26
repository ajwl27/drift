#!/usr/bin/env python3
"""
VOYAGE  -  where the boat is, and how to draw the world from there.

Two things live here, and nothing else:

    Track       Drake's circumnavigation as a dated waypoint list, with
                great-circle interpolation between waypoints and genuine
                stationary periods at the anchorages.  Ports as-is.
    project()   Course-up orthographic.  Ports as-is.

Both are pure functions of a day number.  No state, no allocation in the
hot path, no float64 anywhere it matters.

Dates are Julian (Old Style), which is what every account of the voyage
uses, and what makes 13 Dec 1577 -> 26 Sep 1580 come to 1018 days.  Since
1580 is a leap year in both calendars, ordinary date arithmetic is correct
across the whole span.

Confidence tags on each waypoint:
    2  date and place both well attested
    1  place attested, date approximate
    0  reconstructed to fill a gap -- notably the entire Pacific crossing,
       for which no intermediate position was ever recorded
"""

import math

# --------------------------------------------------------------------------
# 1. THE TRACK
# --------------------------------------------------------------------------

class Voyage:
    """One historical track, everything the piece needs to sail it.

    The point of this class is the gift box. Making three or four of these
    objects and giving them away means each one wants a different voyage --
    Drake for one person, the Beagle for another, Cook for whoever likes
    Australia -- and the difference between them should be a table, not a
    fork. So the track is data, the ecosystem never learns which voyage it is
    on, and adding one is: write the waypoints, write the notes, register it.

    On the hardware this is a build-time constant: one voyage compiled in,
    the rest costing nothing. The card that goes in the box is printed from
    `notes`."""

    __slots__ = ("key", "title", "subtitle", "departure", "waypoints", "notes")

    def __init__(self, key, title, subtitle, departure, waypoints, notes=""):
        self.key = key
        self.title = title
        self.subtitle = subtitle
        self.departure = departure
        self.waypoints = waypoints
        self.notes = notes

    @property
    def days(self):
        return self.waypoints[-1][0]

    def __repr__(self):
        return "<Voyage %s, %d days, %d waypoints>" % (
            self.key, self.days, len(self.waypoints))


DEPARTURE = "13 DEC 1577"
VOYAGE_DAYS = 1018

# (day, lat, lon, confidence, label)
# Day 0 is the departure from Plymouth, 13 December 1577 (Old Style).
# Repeated positions on different days are deliberate: they are the
# careening stops and the winter at Port St Julian, and they are why the
# piece sits in one water mass for weeks at a time.
# ROUTED. The hand-written table is the historical record; this one is that
# record with the great circles between its waypoints checked against a
# 0.1 degree land mask and detoured where they crossed a continent. Before
# the pass, 33 of Drake's 61 legs sailed over land -- Guatulco to Cape Arago
# went straight across North America for 4,061 km. Regenerate with:
#
#     python3 tools/make_route.py drake --emit
#
# The inserted points carry confidence 0 and an empty label: they are
# navigation, not history. Waypoints the mask found on land were nudged into
# the nearest water first -- median 16 km, worst 32 km, against historical
# positions good to considerably less than that.
DRAKE_WAYPOINTS = (
    (   0,   50.25,    -4.25, 2, 'PLYMOUTH'),
    (   4,   44.15,   -10.15, 0, ''),
    (  12,   31.55,    -9.85, 2, 'MOGADOR'),
    (  29,   23.95,   -17.55, 0, ''),
    (  34,   20.65,   -17.15, 2, 'CAPE BLANCO'),
    (  46,   15.05,   -23.25, 2, 'MAIO'),
    (  49,   14.85,   -23.65, 2, 'SANTIAGO'),
    (  77,   -3.95,   -32.55, 1, 'FERNANDO DE NORONHA'),
    (  80,   -7.85,   -32.55, 0, ''),
    (  87,  -13.05,   -38.35, 2, 'BAHIA'),
    (  95,  -20.15,   -38.35, 0, ''),
    ( 119,  -35.35,   -53.55, 0, ''),
    ( 122,  -35.05,   -56.25, 2, 'RIO DE LA PLATA'),
    ( 146,  -35.05,   -56.25, 2, 'RIO DE LA PLATA'),
    ( 147,  -38.75,   -56.25, 0, ''),
    ( 150,  -47.85,   -65.75, 1, 'PUERTO DESEADO'),
    ( 153,  -48.05,   -65.75, 0, ''),
    ( 155,  -48.15,   -65.85, 1, 'SEAL BAY'),
    ( 188,  -49.55,   -67.65, 2, 'PORT ST JULIAN'),
    ( 247,  -49.55,   -67.65, 2, 'PORT ST JULIAN'),
    ( 249,  -51.15,   -67.35, 0, ''),
    ( 250,  -52.45,   -68.45, 2, 'CAPE VIRGENES'),
    ( 254,  -52.80,   -70.40, 2, 'ELIZABETH ISLAND'),
    ( 258,  -53.75,   -71.35, 0, ''),
    ( 267,  -52.85,   -74.85, 2, 'CAPE PILAR'),
    ( 279,  -52.45,   -75.45, 0, ''),
    ( 298,  -51.65,   -75.15, 1, 'DIEGO DE ALMAGRO'),
    ( 301,  -52.85,   -75.35, 0, ''),
    ( 304,  -53.95,   -74.25, 0, ''),
    ( 309,  -56.15,   -72.05, 0, ''),
    ( 315,  -55.95,   -67.45, 0, 'SOUTHERNMOST'),
    ( 322,  -55.77,   -69.44, 2, 'ILDEFONSO'),
    ( 324,  -55.85,   -72.35, 0, ''),
    ( 330,  -52.05,   -76.15, 0, ''),
    ( 338,  -45.65,   -75.65, 0, ''),
    ( 342,  -42.45,   -74.55, 0, ''),
    ( 344,  -40.85,   -74.35, 0, ''),
    ( 346,  -39.75,   -73.55, 1, 'VALDIVIA'),
    ( 348,  -38.45,   -74.05, 2, 'ISLA MOCHA'),
    ( 349,  -37.05,   -74.05, 0, ''),
    ( 350,  -35.55,   -73.15, 0, ''),
    ( 352,  -32.85,   -71.65, 2, 'QUINTERO'),
    ( 357,  -32.95,   -71.75, 2, 'VALPARAISO'),
    ( 361,  -31.55,   -72.15, 0, ''),
    ( 364,  -30.35,   -71.75, 1, 'TONGOY'),
    ( 368,  -28.75,   -71.95, 0, ''),
    ( 373,  -27.35,   -71.05, 1, 'SALADA BAY'),
    ( 402,  -27.35,   -71.05, 1, 'SALADA BAY'),
    ( 406,  -26.25,   -70.75, 1, 'PAN DE AZUCAR'),
    ( 412,  -22.95,   -71.05, 0, ''),
    ( 418,  -19.65,   -70.35, 2, 'PISAGUA'),
    ( 420,  -18.55,   -70.45, 2, 'ARICA'),
    ( 422,  -17.15,   -72.15, 1, 'CHULE'),
    ( 423,  -17.35,   -73.95, 0, ''),
    ( 428,  -13.65,   -77.65, 0, ''),
    ( 429,  -11.95,   -77.25, 2, 'CALLAO'),
    ( 432,   -8.15,   -81.55, 0, ''),
    ( 434,   -5.15,   -81.25, 2, 'PAITA'),
    ( 435,   -5.05,   -81.75, 0, ''),
    ( 439,   -2.25,   -81.45, 0, ''),
    ( 443,    0.60,   -80.13, 2, 'CACAFUEGO'),
    ( 448,    4.65,   -80.55, 0, ''),
    ( 454,    8.75,   -84.25, 0, ''),
    ( 455,    8.75,   -83.75, 1, 'CANO ISLAND'),
    ( 466,    8.75,   -83.75, 1, 'CANO ISLAND'),
    ( 486,   15.65,   -96.15, 2, 'GUATULCO'),
    ( 487,   15.25,   -96.45, 0, ''),
    ( 498,   18.55,  -104.45, 0, ''),
    ( 510,   24.15,  -112.45, 0, ''),
    ( 523,   32.15,  -119.25, 0, ''),
    ( 535,   40.15,  -124.85, 0, ''),
    ( 539,   43.25,  -124.55, 0, 'CAPE ARAGO'),
    ( 545,   40.65,  -124.85, 0, ''),
    ( 548,   39.15,  -124.25, 0, ''),
    ( 551,   38.15,  -123.05, 1, 'NOVA ALBION'),
    ( 587,   38.15,  -123.05, 1, 'NOVA ALBION'),
    ( 588,   37.70,  -123.00, 1, 'FARALLONES'),
    ( 610,   28.00,  -155.00, 0, 'PACIFIC'),
    ( 633,   16.00,   178.00, 0, 'PACIFIC'),
    ( 656,    7.55,   134.45, 1, 'PALAU'),
    ( 671,    5.05,   125.15, 0, ''),
    ( 672,    5.75,   124.95, 1, 'MINDANAO'),
    ( 679,    5.35,   125.25, 1, 'SARANGANI'),
    ( 681,    2.65,   125.25, 1, 'SANGIHE'),
    ( 690,    0.65,   127.25, 2, 'TERNATE'),
    ( 696,    0.65,   127.25, 2, 'TERNATE'),
    ( 701,   -1.55,   123.65, 1, 'BANGGAI'),
    ( 729,   -1.55,   123.65, 1, 'BANGGAI'),
    ( 737,   -1.75,   123.75, 0, ''),
    ( 743,   -1.85,   123.65, 0, ''),
    ( 757,   -2.00,   123.30, 0, 'THE REEF'),
    ( 760,   -3.25,   123.55, 0, ''),
    ( 762,   -4.25,   123.25, 1, 'WOWONI'),
    ( 785,   -7.15,   128.40, 1, 'DAMAR'),
    ( 800,   -7.75,   118.85, 0, ''),
    ( 803,   -7.85,   116.55, 0, ''),
    ( 807,   -9.25,   114.95, 0, ''),
    ( 814,   -9.25,   110.15, 0, ''),
    ( 817,   -7.85,   108.95, 2, 'JAVA'),
    ( 834,   -7.85,   108.95, 2, 'JAVA'),
    ( 864,  -20.00,    70.00, 0, 'INDIAN OCEAN'),
    ( 890,  -31.65,    29.65, 1, 'AFRICAN COAST'),
    ( 900,  -35.25,    26.65, 0, ''),
    ( 907,  -35.25,    22.45, 0, ''),
    ( 911,  -35.25,    20.35, 0, ''),
    ( 915,  -34.45,    18.35, 2, 'CAPE OF GOOD HOPE'),
    ( 945,    5.35,    -9.65, 2, 'CESTOS RIVER'),
    ( 951,    7.25,   -13.35, 0, ''),
    ( 952,    8.35,   -13.35, 2, 'SIERRA LEONE'),
    ( 957,   10.75,   -16.65, 0, ''),
    ( 963,   15.95,   -17.95, 0, ''),
    ( 970,   21.25,   -17.95, 0, ''),
    ( 982,   31.75,   -18.55, 0, ''),
    ( 992,   38.00,   -25.00, 0, 'AZORES'),
    (1018,   50.25,    -4.25, 2, 'PLYMOUTH'),
)

NOTES = """
Where the record is thin, and what this piece does about it.

SOUTHERNMOST (day 315).  Blown south after clearing the Strait, Drake
reached an island he named Elizabeth -- not the Elizabeth Island inside the
Strait, a different one, and one nobody has seen since.  Nuno da Silva's log
says 57 degrees S, at which latitude there is no land.  Modern scholarship
treats it as a phantom.  This track uses 55.85 S in the Hermite group, which
is conservative; whether Drake actually saw open water south of the
continent, and so discovered the passage that carries his name, is still
argued.  Turner says yes.  Kelsey says no.

CAPE ARAGO (day 539).  The furthest north Drake reached on the American
coast is disputed across four degrees of latitude.

NOVA ALBION (day 551).  Drakes Bay at Point Reyes is the designated
landmark and the mainstream reading.  It is not settled: the two surviving
manuscript accounts give 44 N against the printed 38 N, and there are twenty
or more candidate sites in the literature, from Baja to Alaska.

THE PACIFIC CROSSING (days 588-656).  Sixty-eight days out of sight of land
and not one intermediate position recorded anywhere.  The two waypoints in
the middle of it are a great-circle construction, nothing more.  They exist
so that the boat crosses the date line at a plausible latitude, and they are
tagged 0 accordingly.  The piece will spend nine weeks in the North Pacific
gyre on the strength of them, which is exactly the stretch where it will
look emptiest -- and correctly so.
"""


# --------------------------------------------------------------------------
# A second voyage, which is the whole point of the Voyage class.
#
# The Beagle is the obvious companion piece: Darwin spent a great deal of the
# five years towing a plankton net off the stern and writing about what came
# up in it, so of every voyage that could go in this frame it is the one
# where the plankton are not a conceit. It also crosses water Drake never
# saw -- the Galapagos, Tahiti, New Zealand, the Australian bight, Keeling
# -- so the two objects sitting side by side would show visibly different
# oceans rather than the same one twice.
#
# Dates are Gregorian throughout and the arithmetic is ordinary.
# ROUTED. The hand-written table is the historical record; this one is that
# record with the great circles between its waypoints checked against a
# 0.1 degree land mask and detoured where they crossed a continent. Before
# the pass, 34 of the Beagle's 63 legs sailed over land -- Mauritius to Cape Town
# went straight through southern Africa for 1,119 km. Regenerate with:
#
#     python3 tools/make_route.py beagle --emit
#
# The inserted points carry confidence 0 and an empty label: they are
# navigation, not history. Waypoints the mask found on land were nudged into
# the nearest water first -- median 18 km, worst 52 km, against historical
# positions good to considerably less than that.
BEAGLE_WAYPOINTS = (
    (   0,   50.25,    -4.25, 2, 'PLYMOUTH'),
    (   6,   38.85,   -15.45, 0, ''),
    (  10,   28.35,   -16.25, 2, 'TENERIFE'),
    (  13,   24.95,   -18.95, 0, ''),
    (  15,   21.65,   -22.25, 0, ''),
    (  17,   18.05,   -22.25, 0, ''),
    (  19,   16.25,   -22.25, 0, ''),
    (  20,   14.55,   -23.15, 0, ''),
    (  20,   14.85,   -23.65, 2, 'SANTIAGO'),
    (  43,   14.85,   -23.65, 2, 'SANTIAGO'),
    (  51,    0.92,   -29.35, 2, 'ST PAUL ROCKS'),
    (  55,   -3.95,   -32.55, 2, 'FERNANDO DE NORONHA'),
    (  58,   -7.85,   -32.55, 0, ''),
    (  63,  -13.05,   -38.35, 2, 'BAHIA'),
    (  81,  -13.05,   -38.35, 2, 'BAHIA'),
    (  91,  -20.15,   -38.35, 0, ''),
    (  98,  -23.35,   -41.55, 0, ''),
    ( 100,  -23.05,   -43.25, 2, 'RIO DE JANEIRO'),
    ( 191,  -23.05,   -43.25, 2, 'RIO DE JANEIRO'),
    ( 201,  -35.35,   -54.05, 0, ''),
    ( 202,  -35.05,   -56.35, 2, 'MONTEVIDEO'),
    ( 250,  -35.05,   -56.35, 2, 'MONTEVIDEO'),
    ( 261,  -37.25,   -56.25, 0, ''),
    ( 273,  -39.45,   -58.15, 0, ''),
    ( 287,  -39.05,   -61.85, 2, 'BAHIA BLANCA'),
    ( 340,  -39.05,   -61.85, 2, 'BAHIA BLANCA'),
    ( 359,  -39.45,   -58.15, 0, ''),
    ( 376,  -37.25,   -56.25, 0, ''),
    ( 390,  -35.05,   -56.35, 2, 'MONTEVIDEO'),
    ( 480,  -35.05,   -56.35, 2, 'MONTEVIDEO'),
    ( 488,  -38.75,   -56.25, 0, ''),
    ( 512,  -47.85,   -65.75, 2, 'PUERTO DESEADO'),
    ( 526,  -49.15,   -66.25, 0, ''),
    ( 536,  -49.55,   -67.65, 2, 'PORT ST JULIAN'),
    ( 548,  -50.65,   -67.75, 0, ''),
    ( 560,  -51.45,   -68.95, 2, 'STRAIT OF MAGELLAN'),
    ( 568,  -53.35,   -66.55, 0, ''),
    ( 584,  -53.35,   -58.85, 0, ''),
    ( 590,  -51.85,   -57.95, 2, 'FALKLAND ISLANDS'),
    ( 620,  -51.85,   -57.95, 2, 'FALKLAND ISLANDS'),
    ( 629,  -50.15,   -56.25, 0, ''),
    ( 640,  -47.95,   -56.25, 0, ''),
    ( 660,  -43.65,   -56.25, 0, ''),
    ( 700,  -35.05,   -56.35, 2, 'MONTEVIDEO'),
    ( 722,  -45.35,   -56.25, 0, ''),
    ( 737,  -50.85,   -61.65, 0, ''),
    ( 749,  -56.35,   -64.75, 0, ''),
    ( 755,  -56.15,   -69.95, 0, ''),
    ( 758,  -54.95,   -69.95, 0, ''),
    ( 760,  -54.85,   -68.30, 2, 'TIERRA DEL FUEGO'),
    ( 768,  -54.95,   -69.45, 0, ''),
    ( 772,  -55.05,   -70.05, 0, ''),
    ( 779,  -55.65,   -70.45, 0, ''),
    ( 800,  -55.98,   -67.27, 2, 'CAPE HORN'),
    ( 814,  -55.75,   -66.85, 0, ''),
    ( 840,  -55.25,   -67.55, 2, 'BEAGLE CHANNEL'),
    ( 868,  -55.65,   -61.15, 0, ''),
    ( 900,  -51.85,   -57.95, 2, 'FALKLAND ISLANDS'),
    ( 903,  -51.65,   -57.35, 0, ''),
    ( 908,  -50.95,   -57.55, 0, ''),
    ( 960,  -50.25,   -68.35, 2, 'SANTA CRUZ RIVER'),
    ( 986,  -52.15,   -68.45, 0, ''),
    (1010,  -53.15,   -70.92, 2, 'PORT FAMINE'),
    (1013,  -53.75,   -71.95, 0, ''),
    (1015,  -53.65,   -72.95, 0, ''),
    (1019,  -53.35,   -74.85, 0, ''),
    (1032,  -49.85,   -76.15, 0, ''),
    (1044,  -46.35,   -76.15, 0, ''),
    (1050,  -45.00,   -74.55, 2, 'CHONOS ARCHIPELAGO'),
    (1064,  -43.25,   -75.25, 0, ''),
    (1072,  -42.35,   -74.55, 0, ''),
    (1076,  -41.85,   -74.55, 0, ''),
    (1080,  -41.75,   -73.85, 2, 'CHILOE'),
    (1112,  -40.45,   -74.25, 0, ''),
    (1127,  -39.85,   -74.15, 0, ''),
    (1140,  -39.75,   -73.45, 2, 'VALDIVIA'),
    (1157,  -36.85,   -73.85, 0, ''),
    (1160,  -36.85,   -73.25, 2, 'CONCEPCION'),
    (1164,  -35.95,   -73.25, 0, ''),
    (1170,  -34.85,   -72.75, 0, ''),
    (1180,  -32.95,   -71.75, 2, 'VALPARAISO'),
    (1240,  -32.95,   -71.75, 2, 'VALPARAISO'),
    (1250,  -29.75,   -71.95, 0, ''),
    (1260,  -26.55,   -71.25, 0, ''),
    (1280,  -20.35,   -70.25, 2, 'IQUIQUE'),
    (1297,  -13.65,   -77.65, 0, ''),
    (1300,  -11.95,   -77.25, 2, 'CALLAO'),
    (1345,  -11.95,   -77.25, 2, 'CALLAO'),
    (1360,   -0.85,   -90.45, 2, 'GALAPAGOS'),
    (1377,   -1.45,   -91.75, 0, ''),
    (1386,   -0.75,   -92.05, 0, ''),
    (1395,   -0.15,   -91.65, 2, 'GALAPAGOS'),
    (1420,  -12.50,  -125.00, 0, 'PACIFIC'),
    (1420,  -12.50,  -125.00, 0, 'PACIFIC'),
    (1425,  -15.45,  -127.95, 0, ''),
    (1450,  -17.45,  -149.65, 2, 'TAHITI'),
    (1462,  -17.45,  -149.65, 2, 'TAHITI'),
    (1490,  -35.15,   174.25, 2, 'BAY OF ISLANDS'),
    (1500,  -35.15,   174.25, 2, 'BAY OF ISLANDS'),
    (1501,  -33.95,   173.35, 0, ''),
    (1515,  -33.95,   151.35, 2, 'SYDNEY'),
    (1533,  -33.95,   151.35, 2, 'SYDNEY'),
    (1540,  -40.25,   151.65, 0, ''),
    (1544,  -43.65,   148.25, 0, ''),
    (1545,  -43.15,   147.55, 2, 'HOBART'),
    (1557,  -43.15,   147.55, 2, 'HOBART'),
    (1558,  -44.05,   147.55, 0, ''),
    (1570,  -44.05,   124.15, 0, ''),
    (1578,  -34.45,   114.55, 0, ''),
    (1580,  -32.05,   115.65, 2, 'KING GEORGE SOUND'),
    (1588,  -32.05,   115.65, 2, 'KING GEORGE SOUND'),
    (1620,  -12.25,    96.75, 2, 'KEELING ISLANDS'),
    (1632,  -12.25,    96.75, 2, 'KEELING ISLANDS'),
    (1636,  -19.25,    89.55, 0, ''),
    (1643,  -19.25,    73.35, 0, ''),
    (1647,  -19.25,    65.25, 0, ''),
    (1648,  -19.55,    61.25, 0, ''),
    (1649,  -19.55,    59.25, 0, ''),
    (1650,  -20.05,    57.45, 2, 'MAURITIUS'),
    (1660,  -20.05,    57.45, 2, 'MAURITIUS'),
    (1661,  -20.45,    55.05, 0, ''),
    (1671,  -35.25,    40.25, 0, ''),
    (1679,  -35.25,    18.65, 0, ''),
    (1680,  -34.55,    17.95, 0, ''),
    (1680,  -33.85,    18.35, 2, 'CAPE TOWN'),
    (1698,  -33.85,    18.35, 2, 'CAPE TOWN'),
    (1716,  -16.05,    -5.85, 2, 'ST HELENA'),
    (1722,   -8.05,   -14.45, 2, 'ASCENSION'),
    (1745,  -13.05,   -38.35, 2, 'BAHIA'),
    (1753,  -14.75,   -38.35, 0, ''),
    (1760,  -16.05,   -38.85, 0, 'BRAZILIAN COAST'),
    (1766,  -10.35,   -32.85, 0, ''),
    (1781,   10.35,   -32.85, 0, ''),
    (1786,   14.45,   -28.75, 0, ''),
    (1788,   16.45,   -26.75, 0, ''),
    (1790,   17.55,   -24.65, 0, ''),
    (1790,   16.95,   -24.85, 2, 'CAPE VERDE'),
    (1800,   38.45,   -28.75, 2, 'AZORES'),
    (1816,   50.65,    -1.85, 2, 'FALMOUTH'),
)

BEAGLE_NOTES = """
Darwin towed a plankton net off the stern for much of the five years and
wrote about what came up in it, which makes this the one voyage where the
organisms in the frame are not a conceit.

THE PACIFIC CROSSING (days 1395-1450). Galapagos to Tahiti, three thousand
miles, and as with Drake the intermediate positions are a great-circle
construction rather than a record.

THE BRAZILIAN RE-CROSSING (day 1745). FitzRoy recrossed the Atlantic to
Bahia to re-check his chronometer readings, adding a month to a voyage
everyone aboard wanted finished. Darwin was furious about it and it is the
reason the track doubles back before going home.

RIO (days 100-191). Three months at anchor while Darwin worked ashore, which
is the longest the piece ever sits in one water mass.
"""


VOYAGES = {}


def register(v):
    VOYAGES[v.key] = v
    return v


register(Voyage(
    "drake", "DRAKE", "GOLDEN HIND  1577-1580", "13 DEC 1577",
    DRAKE_WAYPOINTS, NOTES))

register(Voyage(
    "beagle", "DARWIN", "HMS BEAGLE  1831-1836", "27 DEC 1831",
    BEAGLE_WAYPOINTS, BEAGLE_NOTES))


def _norm_lon(d):
    return (d + 180.0) % 360.0 - 180.0


def _to_vec(lat, lon):
    la = math.radians(lat)
    lo = math.radians(lon)
    cl = math.cos(la)
    return (cl * math.cos(lo), cl * math.sin(lo), math.sin(la))


def _to_ll(v):
    x, y, z = v
    return (math.degrees(math.asin(max(-1.0, min(1.0, z)))),
            math.degrees(math.atan2(y, x)))


def slerp(a, b, f):
    """Great-circle interpolation between two unit vectors. Constant speed
    along the arc, which is what a ship actually does, and what a linear
    interpolation of latitude and longitude conspicuously does not -- that
    would drift off the great circle and, worse, take the wrong way round
    the world across the date line."""
    d = a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
    d = max(-1.0, min(1.0, d))
    if d > 0.999999:
        return b if f > 0.5 else a
    o = math.acos(d)
    so = math.sin(o)
    ka = math.sin((1.0 - f) * o) / so
    kb = math.sin(f * o) / so
    return (ka * a[0] + kb * b[0], ka * a[1] + kb * b[1], ka * a[2] + kb * b[2])


class Track:
    """The voyage as a continuous function of time.

    Cost per query is a binary search over 62 waypoints and one slerp. On the
    MCU this runs once a frame and disappears into the noise."""

    def __init__(self, voyage=None):
        if voyage is None:
            voyage = VOYAGES["drake"]
        elif isinstance(voyage, str):
            voyage = VOYAGES[voyage]
        self.voyage = voyage
        self.wp = voyage.waypoints
        self.vec = [_to_vec(w[1], w[2]) for w in self.wp]
        self.days = [w[0] for w in self.wp]

    def _seg(self, day):
        lo, hi = 0, len(self.days) - 1
        if day <= self.days[0]:
            return 0, 0.0
        if day >= self.days[-1]:
            return hi - 1, 1.0
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if self.days[mid] <= day:
                lo = mid
            else:
                hi = mid
        d0, d1 = self.days[lo], self.days[lo + 1]
        span = d1 - d0
        return lo, 0.0 if span <= 0 else (day - d0) / span

    def position(self, day):
        i, f = self._seg(day)
        if f <= 0.0:
            return _to_ll(self.vec[i])
        return _to_ll(slerp(self.vec[i], self.vec[i + 1], f))

    def bearing(self, day, look=2.0):
        """Course made good, degrees clockwise from north. Measured against a
        point a couple of days ahead rather than differentiated, because the
        derivative is undefined the moment the ship is at anchor -- and it is
        at anchor for a sixth of the voyage."""
        la0, lo0 = self.position(day)
        la1, lo1 = self.position(min(day + look, self.days[-1]))
        if abs(la1 - la0) < 1e-7 and abs(_norm_lon(lo1 - lo0)) < 1e-7:
            # stationary: keep looking further ahead until the ship moves
            for extra in (8.0, 30.0, 90.0):
                la1, lo1 = self.position(min(day + extra, self.days[-1]))
                if abs(la1 - la0) > 1e-7 or abs(_norm_lon(lo1 - lo0)) > 1e-7:
                    break
            else:
                return 0.0
        p0 = math.radians(la0)
        p1 = math.radians(la1)
        dl = math.radians(_norm_lon(lo1 - lo0))
        y = math.sin(dl) * math.cos(p1)
        x = math.cos(p0) * math.sin(p1) - math.sin(p0) * math.cos(p1) * math.cos(dl)
        return math.degrees(math.atan2(y, x)) % 360.0

    def speed(self, day, h=0.5):
        """Km per day. Zero at anchor, which the ecosystem uses to decide
        whether the water is being replaced or merely sat in."""
        la0, lo0 = self.position(max(0.0, day - h))
        la1, lo1 = self.position(min(day + h, self.days[-1]))
        return haversine(la0, lo0, la1, lo1) / (2.0 * h)

    def leg(self, day):
        """The waypoint being sailed from, for the caption."""
        i, _ = self._seg(day)
        return self.wp[i][4], self.wp[min(i + 1, len(self.wp) - 1)][4]

    def anchored(self, day):
        """Name of the anchorage if the ship is not making way, else None.

        Exact rather than inferred from speed: a dwell is encoded as the same
        position on two different days, so this is a comparison, not a
        threshold. Which matters, because the ship also crawls at a tenth of a
        knot down the Patagonian coast and that is emphatically not anchored."""
        i, _ = self._seg(day)
        w0 = self.wp[i]
        w1 = self.wp[min(i + 1, len(self.wp) - 1)]
        if (w0[1], w0[2]) == (w1[1], w1[2]) and w1[0] > w0[0]:
            return w0[4]
        return None

    def status(self, day):
        """One line for the footer."""
        at = self.anchored(day)
        return ("ANCHORED  " + at) if at else "AT SEA"

    def next_port(self, day):
        """(name, days away) for the next waypoint the ship is not already
        sitting at. Skips the duplicate entries that encode a dwell, so at
        Port St Julian on day 200 this says CAPE VIRGENES in 50 days rather
        than PORT ST JULIAN in 47."""
        i, _ = self._seg(day)
        here = (self.wp[i][1], self.wp[i][2])
        for j in range(i + 1, len(self.wp)):
            w = self.wp[j]
            if (w[1], w[2]) != here:
                return w[4], w[0] - day
        return self.wp[-1][4], self.wp[-1][0] - day

    def confidence(self, day):
        """Lowest confidence of the two waypoints bracketing this moment.
        The plate says so when it is guessing."""
        i, _ = self._seg(day)
        return min(self.wp[i][3], self.wp[min(i + 1, len(self.wp) - 1)][3])


def haversine(la0, lo0, la1, lo1, R=6371.0):
    p0 = math.radians(la0)
    p1 = math.radians(la1)
    dp = p1 - p0
    dl = math.radians(_norm_lon(lo1 - lo0))
    a = (math.sin(dp / 2) ** 2
         + math.cos(p0) * math.cos(p1) * math.sin(dl / 2) ** 2)
    return 2 * R * math.asin(min(1.0, math.sqrt(a)))


# --------------------------------------------------------------------------
# 2. COURSE-UP ORTHOGRAPHIC
# --------------------------------------------------------------------------
#
# The panel is 240 x 400.  A globe drawn to fit the width leaves a third of
# the frame empty; drawn to fill the height it overflows the width.  Neither
# is what we want.
#
# The move is to stop thinking of it as a map of the world and start
# thinking of it as a view of the world from where the ship is.  Centre the
# projection on the ship, rotate the whole thing so the course points up the
# long axis of the panel, and choose the radius.  Now the tall frame is
# working for us: it shows more of where you are going and where you have
# been than of the empty water either side, which is the correct emphasis
# for a voyage, and it is also how every strip chart from Ogilby onwards has
# been laid out.
#
# One number, R (globe radius in pixels), controls everything:
#
#   R = 118    the whole visible hemisphere fits inside the 240 width, limb
#              and all.  Reads unmistakably as a globe.  Context.
#   R = 233    the limb exactly clears the corners of a 240x400 frame, so
#              there is no white space at all and no visible edge.  This is
#              the smallest R that fills the panel.
#   R = 1400   about 900 km across the frame.  Coastal detail.
#
# and the piece simply moves R between them.

class Camera:
    __slots__ = ("lat", "lon", "R", "ca", "sa", "clat", "slat", "sb", "cb")

    def __init__(self, lat, lon, bearing, R):
        self.lat = lat
        self.lon = lon
        self.R = R
        la = math.radians(lat)
        self.slat = math.sin(la)
        self.clat = math.cos(la)
        b = math.radians(bearing)
        self.sb = math.sin(b)
        self.cb = math.cos(b)

    def project(self, lat, lon, w, h):
        """Returns (x, y, visible). Screen coordinates, origin top-left.

        Twelve multiplies and two trig calls per point. At 9000 coastline
        points that is too much to do every frame on the MCU -- the map is
        rendered once when the interlude begins and held, which is exactly
        what a reflective panel wants anyway."""
        la = math.radians(lat)
        dl = math.radians(lon - self.lon)
        cla = math.cos(la)
        sla = math.sin(la)
        cdl = math.cos(dl)
        cosc = self.slat * sla + self.clat * cla * cdl
        if cosc < 0.0:
            return 0.0, 0.0, False          # on the far side of the world
        x = self.R * cla * math.sin(dl)
        y = self.R * (self.clat * sla - self.slat * cla * cdl)
        # rotate so the course points up the panel
        xr = x * self.cb - y * self.sb
        yr = x * self.sb + y * self.cb
        return w * 0.5 + xr, h * 0.5 - yr, True

    def limb_visible(self, w, h):
        """True if the edge of the world falls inside the frame, i.e. if we
        are zoomed out far enough for this to read as a globe."""
        return self.R < math.hypot(w * 0.5, h * 0.5)


def fill_radius(w, h):
    """The smallest radius at which the globe covers the whole frame."""
    return math.hypot(w * 0.5, h * 0.5)


def span_km(R, px, Rearth=6371.0):
    """How much ocean a given number of pixels covers at the centre of the
    frame, where the orthographic scale is undistorted."""
    return Rearth * math.asin(min(1.0, px / R))
