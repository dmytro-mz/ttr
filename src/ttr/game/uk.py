"""The Ticket to Ride United Kingdom board (Map Collection 5): 46 cities, 125 routes, 57 destination tickets.

Everything is measured on a scan of the printed board (600x900 px, the units used here): city medallions in
`uk_data.py`, route shapes in `uk_paths.py` (see `scripts/build_uk_paths.py`).
"""

from __future__ import annotations

from ttr.game.model import City, MapData, Route, Ticket
from ttr.game.uk_data import CITIES, CITY_SITES, UK_ROUTE_ENDS
from ttr.game.uk_paths import PATHS

WIDTH = 600.0
HEIGHT = 900.0

# (city, city, length, colour or None for gray, "ferry" | "", locomotives a ferry needs).
# A ferry's locomotive spaces come first (next to the first city). Double routes are listed twice; for the
# two tracks of one line, the order matches `uk_paths.PATHS`.
_ROUTES: list[tuple[str, str, int, str | None, str, int]] = [
    ("Ullapool", "Fort William", 2, "purple", "", False),
    ("Fort William", "Inverness", 2, "black", "", False),
    ("Ullapool", "Wick", 3, "yellow", "", False),
    ("Ullapool", "Inverness", 1, "orange", "", False),
    ("Inverness", "Wick", 2, "red", "", False),
    ("Inverness", "Aberdeen", 3, "purple", "", False),
    ("Inverness", "Dundee", 3, "blue", "", False),
    ("Fort William", "Dundee", 3, "green", "", False),
    ("Fort William", "Glasgow", 2, "orange", "", False),
    ("Dundee", "Edinburgh", 1, "yellow", "", False),
    ("Dundee", "Edinburgh", 1, "red", "", False),
    ("Dundee", "Aberdeen", 1, "white", "", False),
    ("Edinburgh", "Newcastle", 3, "green", "", False),
    ("Edinburgh", "Newcastle", 3, "purple", "", False),
    ("Carlisle", "Newcastle", 1, "yellow", "", False),
    ("Carlisle", "Edinburgh", 2, "orange", "", False),
    ("Glasgow", "Edinburgh", 1, "black", "", False),
    ("Glasgow", "Edinburgh", 1, "blue", "", False),
    ("Stranraer", "Edinburgh", 3, "white", "", False),
    ("Glasgow", "Stranraer", 2, "red", "", False),
    ("Leeds", "Newcastle", 2, "white", "", False),
    ("Leeds", "Newcastle", 2, "orange", "", False),
    ("Leeds", "Hull", 1, "yellow", "", False),
    ("Nottingham", "Hull", 2, "black", "", False),
    ("Barrow", "Leeds", 2, "green", "", False),
    ("Carlisle", "Barrow", 1, "red", "", False),
    ("Nottingham", "Leeds", 2, "purple", "", False),
    ("Manchester", "Leeds", 1, "red", "", False),
    ("Manchester", "Leeds", 1, "blue", "", False),
    ("Liverpool", "Leeds", 2, "black", "", False),
    ("Liverpool", "Manchester", 1, "orange", "", False),
    ("Liverpool", "Manchester", 1, "purple", "", False),
    ("Londonderry", "Belfast", 2, "orange", "", False),
    ("Belfast", "Dundalk", 1, "white", "", False),
    ("Belfast", "Dundalk", 1, "red", "", False),
    ("Dundalk", "Londonderry", 3, "purple", "", False),
    ("Hull", "Norwich", 4, None, "", False),
    ("Norwich", "Nottingham", 4, "white", "", False),
    ("Nottingham", "Cambridge", 2, None, "", False),
    ("Cambridge", "Norwich", 2, "red", "", False),
    ("Cambridge", "Ipswich", 1, "black", "", False),
    ("Norwich", "Ipswich", 1, "green", "", False),
    ("London", "Ipswich", 1, "white", "", False),
    ("London", "Cambridge", 1, "orange", "", False),
    ("London", "Cambridge", 1, "yellow", "", False),
    ("London", "Northampton", 1, "purple", "", False),
    ("London", "Northampton", 1, "blue", "", False),
    ("Northampton", "Cambridge", 1, None, "", False),
    ("Northampton", "Nottingham", 1, "orange", "", False),
    ("Birmingham", "Nottingham", 1, None, "", False),
    ("Birmingham", "Manchester", 2, "black", "", False),
    ("Birmingham", "Manchester", 2, "yellow", "", False),
    ("Birmingham", "Northampton", 1, "white", "", False),
    ("Birmingham", "Northampton", 1, "green", "", False),
    ("Northampton", "Reading", 1, "red", "", False),
    ("Reading", "Southampton", 1, "orange", "", False),
    ("Reading", "London", 1, "green", "", False),
    ("London", "Dover", 2, None, "", False),
    ("Brighton", "London", 1, None, "", False),
    ("Brighton", "Dover", 2, "purple", "", False),
    ("Brighton", "Southampton", 1, "blue", "", False),
    ("Southampton", "Bristol", 2, "green", "", False),
    ("Bristol", "Reading", 2, "white", "", False),
    ("Reading", "Birmingham", 2, None, "", False),
    ("Southampton", "London", 2, "red", "", False),
    ("Southampton", "London", 2, "black", "", False),
    ("Cardiff", "Birmingham", 3, "blue", "", False),
    ("Cardiff", "Birmingham", 3, "orange", "", False),
    ("Llandrindod Wells", "Birmingham", 2, "red", "", False),
    ("Llandrindod Wells", "Manchester", 3, "green", "", False),
    ("Llandrindod Wells", "Holyhead", 3, "blue", "", False),
    ("Dundalk", "Sligo", 3, "black", "", False),
    ("Plymouth", "Bristol", 3, "yellow", "", False),
    ("Llandrindod Wells", "Cardiff", 1, "purple", "", False),
    ("Llandrindod Wells", "Aberystwyth", 1, "white", "", False),
    ("Aberystwyth", "Carmarthen", 1, "yellow", "", False),
    ("Carmarthen", "Cardiff", 1, "red", "", False),
    ("Rosslare", "Dublin", 2, "white", "", False),
    ("Rosslare", "Dublin", 2, "black", "", False),
    ("Tullamore", "Dublin", 1, "green", "", False),
    ("Tullamore", "Dublin", 1, "orange", "", False),
    ("Dublin", "Dundalk", 1, "yellow", "", False),
    ("Dublin", "Dundalk", 1, "blue", "", False),
    ("Rosslare", "Tullamore", 2, "red", "", False),
    ("Rosslare", "Cork", 2, "blue", "", False),
    ("Cork", "Tullamore", 3, "yellow", "", False),
    ("Cork", "Limerick", 1, "purple", "", False),
    ("Limerick", "Tullamore", 1, None, "", False),
    ("Limerick", "Galway", 1, "yellow", "", False),
    ("Tullamore", "Sligo", 3, "blue", "", False),
    ("Tullamore", "Galway", 2, None, "", False),
    ("Tullamore", "Galway", 2, None, "", False),
    ("Galway", "Sligo", 2, "orange", "", False),
    ("Sligo", "Londonderry", 2, "green", "", False),
    ("Aberdeen", "Wick", 3, None, "ferry", True),
    ("Wick", "Stornoway", 5, None, "ferry", True),
    ("Fort William", "Stornoway", 5, None, "ferry", True),
    ("Fort William", "Londonderry", 5, None, "ferry", True),
    ("Stornoway", "Ullapool", 1, None, "ferry", True),
    ("Aberdeen", "Edinburgh", 4, None, "ferry", True),
    ("Aberdeen", "Newcastle", 6, None, "ferry", True),
    ("Londonderry", "Glasgow", 4, None, "ferry", True),
    ("Newcastle", "Hull", 5, None, "ferry", True),
    ("Liverpool", "Barrow", 1, None, "ferry", True),
    ("Stranraer", "Carlisle", 3, None, "ferry", True),
    ("Stranraer", "Londonderry", 3, None, "ferry", True),
    ("Belfast", "Stranraer", 1, None, "ferry", True),
    ("Belfast", "Barrow", 4, None, "ferry", True),
    ("Dover", "France", 2, None, "ferry", True),
    ("Bristol", "Cardiff", 1, None, "ferry", True),
    ("Holyhead", "Liverpool", 2, None, "ferry", True),
    ("Holyhead", "Dundalk", 3, None, "ferry", True),
    ("France", "Southampton", 3, None, "ferry", True),
    ("France", "Southampton", 3, None, "ferry", True),
    ("New York", "Southampton", 10, None, "ferry", True),
    ("Southampton", "Plymouth", 5, None, "ferry", True),
    ("Penzance", "Plymouth", 3, None, "ferry", True),
    ("Penzance", "Plymouth", 2, "black", "", False),
    ("Cardiff", "Penzance", 5, None, "ferry", True),
    ("Cork", "Penzance", 6, None, "ferry", True),
    ("Carmarthen", "Rosslare", 4, None, "ferry", True),
    ("Aberystwyth", "Rosslare", 3, None, "ferry", True),
    ("Holyhead", "Rosslare", 3, None, "ferry", True),
    ("Holyhead", "Dublin", 2, None, "ferry", True),
    ("Aberystwyth", "Holyhead", 2, None, "ferry", True),
]

# Every ticket is a "short" one: this map has no long destinations.
_TICKETS: list[tuple[str, str, int]] = [
    ("Aberdeen", "Glasgow", 5),
    ("Aberystwyth", "Cardiff", 2),
    ("Belfast", "Dublin", 4),
    ("Belfast", "Manchester", 9),
    ("Birmingham", "Cambridge", 2),
    ("Birmingham", "London", 4),
    ("Bristol", "Southampton", 2),
    ("Cambridge", "London", 3),
    ("Cardiff", "London", 8),
    ("Cardiff", "Reading", 4),
    ("Cork", "Leeds", 13),
    ("Dublin", "Cork", 6),
    ("Dublin", "London", 15),
    ("Dundalk", "Carlisle", 7),
    ("Edinburgh", "Birmingham", 12),
    ("Edinburgh", "London", 15),
    ("Fort William", "Edinburgh", 3),
    ("Galway", "Barrow", 12),
    ("Galway", "Dublin", 5),
    ("Glasgow", "Dublin", 9),
    ("Glasgow", "France", 19),
    ("Glasgow", "Manchester", 11),
    ("Holyhead", "Cardiff", 4),
    ("Inverness", "Belfast", 10),
    ("Inverness", "Leeds", 13),
    ("Leeds", "France", 10),
    ("Leeds", "London", 6),
    ("Leeds", "Manchester", 1),
    ("Limerick", "Cardiff", 12),
    ("Liverpool", "Hull", 3),
    ("Liverpool", "Llandrindod Wells", 6),
    ("Liverpool", "Southampton", 6),
    ("London", "Brighton", 3),
    ("London", "France", 7),
    ("Londonderry", "Birmingham", 15),
    ("Londonderry", "Dublin", 6),
    ("Londonderry", "Stranraer", 4),
    ("Manchester", "London", 6),
    ("Manchester", "Norwich", 6),
    ("Manchester", "Plymouth", 8),
    ("Newcastle", "Hull", 3),
    ("Newcastle", "Southampton", 7),
    ("Northampton", "Dover", 3),
    ("Norwich", "Ipswich", 1),
    ("Nottingham", "Ipswich", 3),
    ("Penzance", "London", 10),
    ("Plymouth", "Reading", 5),
    ("Rosslare", "Aberystwyth", 4),
    ("Rosslare", "Carmarthen", 6),
    ("Sligo", "Holyhead", 9),
    ("Southampton", "London", 4),
    ("Stornoway", "Aberdeen", 5),
    ("Stornoway", "Glasgow", 7),
    ("Stranraer", "Tullamore", 6),
    ("Ullapool", "Dundee", 4),
    ("Wick", "Dundee", 4),
    ("Wick", "Edinburgh", 5),
]


def _build() -> MapData:
    cities = [
        City(name=name, x=float(x), y=float(y), label=label, country=country, sites=CITY_SITES.get(name, ()))
        for name, (country, x, y, label) in CITIES.items()
    ]
    routes: list[Route] = []
    seen: dict[tuple[str, str], int] = {}
    for a, b, length, color, kind, locos in _ROUTES:
        twin = next((r.id for r in routes if {r.a, r.b} == {a, b}), None)
        nth = seen[(a, b)] = seen.get((a, b), -1) + 1
        way, side = PATHS[(a, b)][nth]
        ends = UK_ROUTE_ENDS.get((a, b))
        routes.append(
            Route(
                id=len(routes),
                a=a,
                b=b,
                length=length,
                color=color,
                tunnel=False,
                ferry=locos if kind == "ferry" else 0,
                twin=twin,
                path=tuple((float(x), float(y)) for x, y in way),
                side=side,
                ends=((float(ends[0][0]), float(ends[0][1])), (float(ends[1][0]), float(ends[1][1]))) if ends else None,
            )
        )
    for r in routes:
        if r.twin is not None:
            routes[r.twin] = routes[r.twin]._replace(twin=r.id)
    tickets = [Ticket(id=i, a=a, b=b, value=v, long=False) for i, (a, b, v) in enumerate(_TICKETS)]
    return MapData(
        key="uk",
        name="United Kingdom",
        width=WIDTH,
        height=HEIGHT,
        cities=tuple(cities),
        routes=tuple(routes),
        tickets=tuple(tickets),
        technologies=True,
    )


UK = _build()
