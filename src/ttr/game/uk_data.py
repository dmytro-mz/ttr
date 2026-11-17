"""Cities of the UK board, in pixels of the 600x900 board scan (found with the city medallions on the map)."""

from __future__ import annotations

# name: (country, x, y, label side)
CITIES: dict[str, tuple[str, int, int, str]] = {
    # Scotland
    "Stornoway": ("scotland", 392, 42, "nw"),
    "Wick": ("scotland", 544, 88, "w"),
    "Ullapool": ("scotland", 427, 87, "w"),
    "Inverness": ("scotland", 458, 133, "e"),
    "Fort William": ("scotland", 383, 178, "w"),
    "Aberdeen": ("scotland", 536, 214, "w"),
    "Dundee": ("scotland", 482, 248, "w"),
    "Glasgow": ("scotland", 386, 275, "n"),
    "Edinburgh": ("scotland", 443, 293, "e"),
    "Stranraer": ("scotland", 319, 334, "se"),
    # Ireland
    "Londonderry": ("ireland", 219, 259, "nw"),
    "Sligo": ("ireland", 123, 293, "nw"),
    "Galway": ("ireland", 55, 363, "nw"),
    "Tullamore": ("ireland", 131, 416, "n"),
    "Limerick": ("ireland", 56, 430, "n"),
    "Cork": ("ireland", 44, 498, "n"),
    "Dublin": ("ireland", 187, 432, "e"),
    "Rosslare": ("ireland", 139, 511, "s"),
    "Dundalk": ("ireland", 210, 376, "sw"),
    "Belfast": ("ireland", 259, 340, "w"),
    # Wales
    "Holyhead": ("wales", 271, 476, "n"),
    "Aberystwyth": ("wales", 251, 562, "w"),
    "Carmarthen": ("wales", 217, 611, "sw"),
    "Cardiff": ("wales", 258, 653, "sw"),
    "Llandrindod Wells": ("wales", 291, 602, "s"),
    # England
    "Penzance": ("england", 88, 708, "w"),
    "Plymouth": ("england", 178, 717, "n"),
    "Bristol": ("england", 297, 689, "ne"),
    "Southampton": ("england", 346, 766, "sw"),
    "Reading": ("england", 378, 710, "s"),
    "Brighton": ("england", 408, 792, "s"),
    "Dover": ("england", 500, 792, "ne"),
    "London": ("england", 435, 730, "s"),
    "Ipswich": ("england", 510, 722, "se"),
    "Northampton": ("england", 411, 658, "n"),
    "Cambridge": ("england", 466, 676, "ne"),
    "Norwich": ("england", 553, 671, "ne"),
    "Birmingham": ("england", 373, 614, "se"),
    "Nottingham": ("england", 424, 588, "se"),
    "Manchester": ("england", 390, 521, "sw"),
    "Hull": ("england", 492, 531, "se"),
    "Leeds": ("england", 441, 493, "e"),
    "Liverpool": ("england", 344, 489, "w"),
    "Barrow": ("england", 369, 436, "sw"),
    "Carlisle": ("england", 409, 388, "se"),
    "Newcastle": ("england", 476, 407, "se"),
    # Beyond the sea
    "France": ("france", 298, 866, "s"),
    "New York": ("free", 30, 818, "n"),
}

# Cities drawn in more than one place: France has a landing on each side of the board.
CITY_SITES: dict[str, tuple[tuple[int, int], ...]] = {"France": ((569, 834),)}

# Routes that don't start/end at the city's main spot.
UK_ROUTE_ENDS: dict[tuple[str, str], tuple[tuple[int, int], tuple[int, int]]] = {
    ("Dover", "France"): ((500, 792), (569, 834)),
}

CITY_POS: dict[str, tuple[int, int]] = {name: (x, y) for name, (_, x, y, _) in CITIES.items()}
