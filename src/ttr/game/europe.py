"""The Ticket to Ride: Europe board: 47 cities, 101 routes (11 doubles), 46 destination tickets."""

from __future__ import annotations

from ttr.game.europe_paths import PATHS
from ttr.game.model import City, MapData, Route, Ticket

# Board size in SVG units; the score track is drawn around it.
WIDTH = 1000.0
HEIGHT = 650.0

# name: (lat, lon, board x, board y, label side). Board positions follow the printed board
# (measured on a 1024 px photo, see `_board`); lat/lon only anchor the coastline warp
# (`scripts/build_land.py`), so moving a city here means re-running that script.
_CITIES: dict[str, tuple[float, float, float, float, str]] = {
    "Edinburgh": (55.95, -3.19, 160, 100, "n"),
    "London": (51.51, -0.13, 227, 246, "w"),
    "Amsterdam": (52.37, 4.90, 324, 250, "nw"),
    "Bruxelles": (50.85, 4.35, 302, 296, "nw"),
    "Dieppe": (49.92, 1.08, 213, 337, "s"),
    "Brest": (48.39, -4.49, 123, 365, "w"),
    "Paris": (48.86, 2.35, 266, 378, "sw"),
    "Essen": (51.46, 7.01, 403, 261, "sw"),
    "Frankfurt": (50.11, 8.68, 392, 327, "se"),
    "Kobenhavn": (55.68, 12.57, 477, 157, "se"),
    "Stockholm": (59.33, 18.07, 580, 83, "nw"),
    "Berlin": (52.52, 13.40, 506, 277, "nw"),
    "Danzig": (54.35, 18.65, 616, 202, "sw"),
    "Riga": (56.95, 24.10, 700, 112, "se"),
    "Petrograd": (59.93, 30.33, 868, 106, "ne"),
    "Wilno": (54.69, 25.28, 775, 245, "sw"),
    "Warszawa": (52.23, 21.01, 668, 268, "se"),
    "Smolensk": (54.78, 32.04, 880, 246, "sw"),
    "Moskva": (55.75, 37.62, 965, 222, "nw"),
    "Kyiv": (50.45, 30.52, 817, 318, "ne"),
    "Kharkov": (49.99, 36.23, 952, 368, "nw"),
    "Rostov": (47.24, 39.70, 992, 422, "sw"),
    "Sochi": (43.60, 39.73, 987, 506, "sw"),
    "Sevastopol": (44.60, 33.52, 898, 492, "w"),
    "Erzurum": (39.90, 41.27, 970, 627, "sw"),
    "Angora": (39.93, 32.86, 889, 651, "w"),
    "Constantinople": (41.01, 28.98, 812, 598, "e"),
    "Smyrna": (38.42, 27.14, 768, 674, "ne"),
    "Athina": (37.98, 23.73, 683, 649, "ne"),
    "Sofia": (42.70, 23.32, 701, 539, "s"),
    "Bucuresti": (44.43, 26.10, 760, 477, "se"),
    "Budapest": (47.50, 19.04, 610, 413, "ne"),
    "Wien": (48.21, 16.37, 564, 387, "nw"),
    "Munchen": (48.14, 11.58, 450, 370, "e"),
    "Zurich": (47.37, 8.54, 383, 431, "nw"),
    "Marseille": (43.30, 5.37, 352, 525, "s"),
    "Venezia": (45.44, 12.32, 468, 463, "se"),
    "Zagrab": (45.81, 15.98, 551, 477, "e"),
    "Sarajevo": (43.86, 18.41, 633, 532, "nw"),
    "Roma": (41.90, 12.50, 475, 550, "sw"),
    "Brindisi": (40.63, 17.94, 562, 575, "ne"),
    "Palermo": (38.12, 13.36, 512, 680, "w"),
    "Barcelona": (41.39, 2.17, 213, 620, "s"),
    "Pamplona": (42.81, -1.64, 201, 530, "nw"),
    "Madrid": (40.42, -3.70, 101, 610, "w"),
    "Lisboa": (38.72, -9.14, 32, 630, "e"),
    "Cadiz": (36.53, -6.29, 100, 681, "n"),
}


def _board(px: float, py: float) -> tuple[float, float]:
    """Photo pixel -> board units (the photo's map area spans x 15..1012, y 58..702)."""
    return round((px - 15) * WIDTH / 997, 1), round((py - 58) * HEIGHT / 644, 1)


def city_geo() -> dict[str, tuple[float, float]]:
    return {name: (lat, lon) for name, (lat, lon, *_) in _CITIES.items()}


# (city, city, length, color or None for gray, "tunnel" | "ferry" | "", locomotives a ferry needs).
# Double routes are listed twice; their order decides which track is drawn on which side.
_ROUTES: list[tuple[str, str, int, str | None, str, int]] = [
    ("Edinburgh", "London", 4, "black", "", 0),
    ("Edinburgh", "London", 4, "orange", "", 0),
    ("London", "Amsterdam", 2, None, "ferry", 2),
    ("London", "Dieppe", 2, None, "ferry", 1),
    ("London", "Dieppe", 2, None, "ferry", 1),
    ("Dieppe", "Brest", 2, "orange", "", 0),
    ("Dieppe", "Paris", 1, "purple", "", 0),
    ("Dieppe", "Bruxelles", 2, "green", "", 0),
    ("Brest", "Paris", 3, "black", "", 0),
    ("Brest", "Pamplona", 4, "purple", "", 0),
    ("Paris", "Bruxelles", 2, "yellow", "", 0),
    ("Paris", "Bruxelles", 2, "red", "", 0),
    ("Paris", "Frankfurt", 3, "white", "", 0),
    ("Paris", "Frankfurt", 3, "orange", "", 0),
    ("Paris", "Zurich", 3, None, "tunnel", 0),
    ("Paris", "Marseille", 4, None, "", 0),
    ("Paris", "Pamplona", 4, "blue", "", 0),
    ("Paris", "Pamplona", 4, "green", "", 0),
    ("Bruxelles", "Amsterdam", 1, "black", "", 0),
    ("Bruxelles", "Frankfurt", 2, "blue", "", 0),
    ("Amsterdam", "Essen", 3, "yellow", "", 0),
    ("Amsterdam", "Frankfurt", 2, "white", "", 0),
    ("Essen", "Frankfurt", 2, "green", "", 0),
    ("Essen", "Berlin", 2, "blue", "", 0),
    ("Essen", "Kobenhavn", 3, None, "ferry", 1),
    ("Essen", "Kobenhavn", 3, None, "ferry", 1),
    ("Frankfurt", "Berlin", 3, "black", "", 0),
    ("Frankfurt", "Berlin", 3, "red", "", 0),
    ("Frankfurt", "Munchen", 2, "purple", "", 0),
    ("Munchen", "Zurich", 2, "yellow", "tunnel", 0),
    ("Munchen", "Venezia", 2, "blue", "tunnel", 0),
    ("Munchen", "Wien", 3, "orange", "", 0),
    ("Zurich", "Marseille", 2, "purple", "tunnel", 0),
    ("Zurich", "Venezia", 2, "green", "tunnel", 0),
    ("Marseille", "Pamplona", 4, "red", "", 0),
    ("Marseille", "Barcelona", 4, None, "", 0),
    ("Marseille", "Roma", 4, None, "tunnel", 0),
    ("Pamplona", "Barcelona", 2, None, "tunnel", 0),
    ("Pamplona", "Madrid", 3, "black", "tunnel", 0),
    ("Pamplona", "Madrid", 3, "white", "tunnel", 0),
    ("Madrid", "Barcelona", 2, "yellow", "", 0),
    ("Madrid", "Lisboa", 3, "purple", "", 0),
    ("Madrid", "Cadiz", 3, "orange", "", 0),
    ("Lisboa", "Cadiz", 2, "blue", "", 0),
    ("Kobenhavn", "Stockholm", 3, "yellow", "", 0),
    ("Kobenhavn", "Stockholm", 3, "white", "", 0),
    ("Stockholm", "Petrograd", 8, None, "tunnel", 0),
    ("Berlin", "Danzig", 4, None, "", 0),
    ("Berlin", "Warszawa", 4, "purple", "", 0),
    ("Berlin", "Warszawa", 4, "yellow", "", 0),
    ("Berlin", "Wien", 3, "green", "", 0),
    ("Danzig", "Riga", 3, "black", "", 0),
    ("Danzig", "Warszawa", 2, None, "", 0),
    ("Riga", "Petrograd", 4, None, "", 0),
    ("Riga", "Wilno", 4, "green", "", 0),
    ("Warszawa", "Wilno", 3, "red", "", 0),
    ("Warszawa", "Kyiv", 4, None, "", 0),
    ("Warszawa", "Wien", 4, "blue", "", 0),
    ("Wilno", "Petrograd", 4, "blue", "", 0),
    ("Wilno", "Smolensk", 3, "yellow", "", 0),
    ("Wilno", "Kyiv", 2, None, "", 0),
    ("Petrograd", "Moskva", 4, "white", "", 0),
    ("Smolensk", "Moskva", 2, "orange", "", 0),
    ("Smolensk", "Kyiv", 3, "red", "", 0),
    ("Moskva", "Kharkov", 4, None, "", 0),
    ("Kyiv", "Kharkov", 4, None, "", 0),
    ("Kyiv", "Bucuresti", 4, None, "", 0),
    ("Kyiv", "Budapest", 6, None, "tunnel", 0),
    ("Kharkov", "Rostov", 2, "green", "", 0),
    ("Rostov", "Sevastopol", 4, None, "", 0),
    ("Rostov", "Sochi", 2, None, "", 0),
    ("Sochi", "Sevastopol", 2, None, "ferry", 1),
    ("Sochi", "Erzurum", 3, "red", "tunnel", 0),
    ("Sevastopol", "Bucuresti", 4, "white", "", 0),
    ("Sevastopol", "Constantinople", 4, None, "ferry", 2),
    ("Sevastopol", "Erzurum", 4, None, "ferry", 2),
    ("Erzurum", "Angora", 3, "black", "", 0),
    ("Angora", "Constantinople", 2, None, "tunnel", 0),
    ("Angora", "Smyrna", 3, "orange", "tunnel", 0),
    ("Smyrna", "Constantinople", 2, None, "tunnel", 0),
    ("Smyrna", "Athina", 2, None, "ferry", 1),
    ("Smyrna", "Palermo", 6, None, "ferry", 2),
    ("Constantinople", "Bucuresti", 3, "yellow", "", 0),
    ("Constantinople", "Sofia", 3, "blue", "", 0),
    ("Bucuresti", "Sofia", 2, None, "tunnel", 0),
    ("Bucuresti", "Budapest", 4, None, "tunnel", 0),
    ("Budapest", "Wien", 1, "red", "", 0),
    ("Budapest", "Wien", 1, "white", "", 0),
    ("Budapest", "Zagrab", 2, "orange", "", 0),
    ("Budapest", "Sarajevo", 3, "purple", "", 0),
    ("Wien", "Zagrab", 2, None, "", 0),
    ("Zagrab", "Venezia", 2, None, "", 0),
    ("Zagrab", "Sarajevo", 3, "red", "", 0),
    ("Sarajevo", "Sofia", 2, None, "tunnel", 0),
    ("Sarajevo", "Athina", 4, "green", "", 0),
    ("Sofia", "Athina", 3, "purple", "", 0),
    ("Athina", "Brindisi", 4, None, "ferry", 1),
    ("Brindisi", "Roma", 2, "white", "", 0),
    ("Brindisi", "Palermo", 3, None, "ferry", 1),
    ("Palermo", "Roma", 4, None, "ferry", 1),
    ("Roma", "Venezia", 2, "black", "", 0),
]

_LONG_TICKETS: list[tuple[str, str, int]] = [
    ("Brest", "Petrograd", 20),
    ("Cadiz", "Stockholm", 21),
    ("Edinburgh", "Athina", 21),
    ("Kobenhavn", "Erzurum", 21),
    ("Lisboa", "Danzig", 20),
    ("Palermo", "Moskva", 20),
]

_TICKETS: list[tuple[str, str, int]] = [
    ("Amsterdam", "Pamplona", 7),
    ("Amsterdam", "Wilno", 12),
    ("Angora", "Kharkov", 10),
    ("Athina", "Angora", 5),
    ("Athina", "Wilno", 11),
    ("Barcelona", "Bruxelles", 8),
    ("Barcelona", "Munchen", 8),
    ("Berlin", "Bucuresti", 8),
    ("Berlin", "Moskva", 12),
    ("Berlin", "Roma", 9),
    ("Brest", "Marseille", 7),
    ("Brest", "Venezia", 8),
    ("Bruxelles", "Danzig", 9),
    ("Budapest", "Sofia", 5),
    ("Edinburgh", "Paris", 7),
    ("Essen", "Kyiv", 10),
    ("Frankfurt", "Kobenhavn", 5),
    ("Frankfurt", "Smolensk", 13),
    ("Kyiv", "Petrograd", 6),
    ("Kyiv", "Sochi", 8),
    ("London", "Berlin", 7),
    ("London", "Wien", 10),
    ("Madrid", "Dieppe", 8),
    ("Madrid", "Zurich", 8),
    ("Marseille", "Essen", 8),
    ("Palermo", "Constantinople", 8),
    ("Paris", "Wien", 8),
    ("Paris", "Zagrab", 7),
    ("Riga", "Bucuresti", 10),
    ("Roma", "Smyrna", 8),
    ("Rostov", "Erzurum", 5),
    ("Sarajevo", "Sevastopol", 8),
    ("Smolensk", "Rostov", 8),
    ("Sofia", "Smyrna", 5),
    ("Stockholm", "Wien", 11),
    ("Venezia", "Constantinople", 10),
    ("Warszawa", "Smolensk", 6),
    ("Zagrab", "Brindisi", 6),
    ("Zurich", "Brindisi", 6),
    ("Zurich", "Budapest", 6),
]


def _build() -> MapData:
    cities = []
    for name, (_, _, px, py, label) in _CITIES.items():
        x, y = _board(px, py)
        cities.append(City(name=name, x=x, y=y, label=label))
    routes: list[Route] = []
    for a, b, length, color, kind, locos in _ROUTES:
        twin = next((r.id for r in routes if {r.a, r.b} == {a, b}), None)
        way, sides = PATHS[(a, b)]
        routes.append(
            Route(
                id=len(routes),
                a=a,
                b=b,
                length=length,
                color=color,
                tunnel=kind == "tunnel",
                ferry=locos if kind == "ferry" else 0,
                twin=twin,
                path=tuple(_board(x, y) for x, y in way),
                side=sides[0 if twin is None else 1],
            )
        )
    for r in routes:
        if r.twin is not None:
            routes[r.twin] = routes[r.twin]._replace(twin=r.id)
    tickets = [Ticket(id=i, a=a, b=b, value=v, long=True) for i, (a, b, v) in enumerate(_LONG_TICKETS)]
    tickets += [Ticket(id=len(tickets) + i, a=a, b=b, value=v, long=False) for i, (a, b, v) in enumerate(_TICKETS)]
    return MapData(
        name="Europe", width=WIDTH, height=HEIGHT, cities=tuple(cities), routes=tuple(routes), tickets=tuple(tickets)
    )


EUROPE = _build()
