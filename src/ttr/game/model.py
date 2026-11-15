"""Static board model and card constants."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import cached_property
from typing import NamedTuple

COLORS: tuple[str, ...] = ("purple", "white", "blue", "yellow", "orange", "black", "red", "green")
LOCO = "loco"
CARD_TYPES: tuple[str, ...] = (*COLORS, LOCO)
CARDS_PER_COLOR = 12
LOCOS_IN_DECK = 14

# Points for claiming a route of a given length.
ROUTE_POINTS: Mapping[int, int] = {1: 1, 2: 2, 3: 4, 4: 7, 5: 10, 6: 15, 7: 18, 8: 21}


class City(NamedTuple):
    name: str
    x: float
    y: float
    label: str  # side of the dot the name is drawn on: n, s, e, w, ne, nw, se, sw


class Route(NamedTuple):
    id: int
    a: str
    b: str
    length: int
    color: str | None  # None = gray: any one colour
    tunnel: bool
    ferry: int  # locomotives required (0 = not a ferry)
    twin: int | None  # the other track of a double route
    # Shape as printed: the bend points between city a and city b (straight segments), and for double
    # routes the side of the centre line this track lies on (+1 / -1).
    path: tuple[tuple[float, float], ...] | None = None
    side: int = 0

    @property
    def points(self) -> int:
        return ROUTE_POINTS[self.length]

    @property
    def label(self) -> str:
        return f"{self.a}–{self.b}"


class Ticket(NamedTuple):
    id: int
    a: str
    b: str
    value: int
    long: bool

    @property
    def label(self) -> str:
        return f"{self.a}–{self.b}"


@dataclass(frozen=True)
class MapData:
    name: str
    width: float
    height: float
    cities: tuple[City, ...]
    routes: tuple[Route, ...]
    tickets: tuple[Ticket, ...]

    @cached_property
    def city_names(self) -> frozenset[str]:
        return frozenset(c.name for c in self.cities)

    @cached_property
    def routes_at(self) -> dict[str, tuple[int, ...]]:
        at: dict[str, list[int]] = {c.name: [] for c in self.cities}
        for r in self.routes:
            at[r.a].append(r.id)
            at[r.b].append(r.id)
        return {k: tuple(v) for k, v in at.items()}

    def to_json(self) -> dict[str, object]:
        return {
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "cities": [c._asdict() for c in self.cities],
            "routes": [{**r._asdict(), "points": r.points} for r in self.routes],
            "tickets": [t._asdict() for t in self.tickets],
            "route_points": dict(ROUTE_POINTS),
            "colors": list(COLORS),
        }
