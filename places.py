#!/usr/bin/env python3
"""
PLACES  -  what to call the coastline.

A chart with an unnamed coast is a shape. You can tell it is land and you
cannot tell whether it is Patagonia or Portugal, which means the map screen
was answering "where is the ship" with a dot and a latitude and leaving the
more interesting half of the question alone.

WHY NOT CITIES
    The obvious source is Natural Earth's populated places, and it is the
    wrong one. This is a piece about a voyage of 1577-1580, and the gift
    boxes cover others from 1519 to 1836. Montevideo was founded in 1726 and
    Wellington in 1839; a chart of Drake's circumnavigation labelled with
    either is a chart of a voyage that did not happen. Filtering a modern
    city list by founding date is possible and is a research project, and the
    result would still be a list of settlements on a chart drawn by people
    who navigated by capes.

WHAT THIS IS INSTEAD
    Two layers, both period-safe by construction:

    1. THE VOYAGE'S OWN ANCHORAGES. Already in the waypoint table, already
       named, already dated -- PLYMOUTH, MOGADOR, PORT ST JULIAN. Free, and
       the most useful labels on the chart, because they are the places this
       particular ship stopped.

    2. GEOGRAPHY. Capes, straits, bays, island groups, passages. A headland
       has no founding date. These are the names a mariner of any century
       would have used and mostly did, and they are what actually tells you
       where you are: CAPE HORN says more about a position at 56 S than any
       town within five hundred miles of it.

The table below is hand-built. Sixty-odd entries at eight bytes each is half
a kilobyte in flash, which is nothing, and hand-building it is what keeps a
modern coastal conurbation from creeping in.
"""

import math

# (lat, lon, rank, name)
#
# rank 1  visible even on the globe: the handful of names that orient a
#         hemisphere
# rank 2  chart scale: the ones that tell you which stretch of coast this is
# rank 3  close in only
FEATURES = (
    # --- Atlantic, north and east -------------------------------------
    (49.5, -6.5, 2, "SCILLY"),
    (48.5, -5.1, 2, "USHANT"),
    (44.0, -4.0, 2, "BAY OF BISCAY"),
    (38.7, -27.2, 2, "AZORES"),
    (36.0, -5.6, 1, "GIBRALTAR"),
    (32.6, -16.9, 2, "MADEIRA"),
    (28.3, -16.6, 2, "CANARIES"),
    (20.8, -17.0, 2, "CAPE BLANCO"),
    (16.0, -24.0, 1, "CAPE VERDE"),
    (14.7, -17.5, 2, "CAPE VERT"),
    (4.5, 5.0, 2, "GULF OF GUINEA"),
    (-7.9, -14.4, 2, "ASCENSION"),
    (-15.9, -5.7, 1, "ST HELENA"),
    (-37.1, -12.3, 2, "TRISTAN DA CUNHA"),
    # --- Atlantic, west ------------------------------------------------
    (64.0, -21.9, 2, "ICELAND"),
    (47.6, -52.7, 2, "NEWFOUNDLAND"),
    (32.3, -64.8, 2, "BERMUDA"),
    (24.5, -76.5, 2, "BAHAMAS"),
    (15.0, -70.0, 1, "CARIBBEAN"),
    (9.4, -79.9, 1, "PANAMA"),
    (-3.8, -32.4, 2, "FERNANDO DE NORONHA"),
    (-8.0, -35.0, 2, "CAPE ST ROQUE"),
    (-13.0, -38.5, 2, "BAHIA"),
    (-22.9, -43.2, 2, "RIO DE JANEIRO"),
    (-35.0, -56.0, 1, "RIVER PLATE"),
    (-42.0, -64.0, 2, "GULF OF SAN MATIAS"),
    (-49.3, -67.7, 2, "PORT ST JULIAN"),
    (-51.7, -59.0, 1, "FALKLANDS"),
    # --- the bottom of the world ---------------------------------------
    (-52.5, -69.5, 1, "STRAIT OF MAGELLAN"),
    (-54.5, -68.5, 2, "TIERRA DEL FUEGO"),
    (-55.98, -67.27, 1, "CAPE HORN"),
    (-58.0, -63.0, 1, "DRAKE PASSAGE"),
    (-62.5, -59.5, 2, "SOUTH SHETLANDS"),
    (-64.5, -62.0, 2, "ANTARCTIC PENINSULA"),
    (-54.4, -36.6, 2, "SOUTH GEORGIA"),
    (-46.4, 51.8, 2, "CROZET"),
    (-49.3, 69.4, 2, "KERGUELEN"),
    # --- Africa and the Indian -----------------------------------------
    (-33.9, 18.4, 1, "CAPE OF GOOD HOPE"),
    (-34.4, 20.0, 2, "CAPE AGULHAS"),
    (-19.0, 39.0, 2, "MOZAMBIQUE CHANNEL"),
    (-18.9, 47.5, 2, "MADAGASCAR"),
    (-20.3, 57.6, 2, "MAURITIUS"),
    (12.5, 45.0, 2, "GULF OF ADEN"),
    (6.9, 79.9, 2, "CEYLON"),
    (-6.2, 106.8, 2, "JAVA"),
    (3.0, 98.0, 2, "SUMATRA"),
    (2.0, 128.0, 1, "MOLUCCAS"),
    (-2.0, 120.0, 2, "CELEBES"),
    (14.6, 121.0, 2, "PHILIPPINES"),
    # --- Pacific --------------------------------------------------------
    (-33.0, -71.6, 2, "VALPARAISO"),
    (-12.0, -77.1, 2, "CALLAO"),
    (-0.7, -90.3, 1, "GALAPAGOS"),
    (-33.6, -78.8, 2, "JUAN FERNANDEZ"),
    (-27.1, -109.4, 2, "EASTER ISLAND"),
    (-9.8, -139.0, 2, "MARQUESAS"),
    (-17.6, -149.5, 2, "SOCIETY ISLANDS"),
    (-21.2, -175.2, 2, "TONGA"),
    (-17.7, 178.0, 2, "FIJI"),
    (-41.3, 174.8, 1, "NEW ZEALAND"),
    (-42.9, 147.3, 2, "TASMANIA"),
    (-33.9, 151.2, 1, "BOTANY BAY"),
    (-16.9, 145.8, 2, "GREAT BARRIER REEF"),
    (-10.6, 142.3, 2, "TORRES STRAIT"),
    (13.5, 144.8, 2, "LADRONES"),
    (21.3, -157.9, 2, "SANDWICH ISLANDS"),
    (38.0, -123.0, 2, "NOVA ALBION"),
    (23.0, -110.0, 2, "CAPE ST LUCAS"),
    (55.9, -159.0, 2, "ALASKA"),
    (65.8, -168.9, 1, "BERING STRAIT"),
)


def visible(cam, w, h, max_rank):
    """[(x, y, name), ...] for everything on this side of the world and
    inside the frame. The camera does the projection and the culling; this
    only filters by rank and by whether the point came back."""
    out = []
    for lat, lon, rank, name in FEATURES:
        if rank > max_rank:
            continue
        x, y, vis = cam.project(lat, lon, w, h)
        if not vis:
            continue
        if -20 <= x <= w + 20 and -10 <= y <= h + 10:
            out.append((x, y, rank, name))
    return out


def rank_for(R, r_globe, r_chart):
    """How much naming a given zoom can carry, 0 to 3.

    **Zero on the globe.** The opening shot is the Earth, and a label at that
    scale covers a thousand miles of the thing it is labelling. Writing on it
    is not information, it is furniture -- and holding the globe silent for
    three seconds is what makes the words mean something when they arrive.

    Then a handful through the move, and everything at chart scale, where the
    frame is a few hundred miles across and every name in it is telling you
    which stretch of coast you are looking at.

    Geometric in R, because zoom is."""
    f = (math.log(max(R, 1.0)) - math.log(r_globe)) / \
        (math.log(r_chart) - math.log(r_globe))
    if f < 0.22:
        return 0
    if f < 0.62:
        return 1
    return 3
