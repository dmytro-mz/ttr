"""Static board model and card constants."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cached_property
from typing import NamedTuple

from ttr.game import techs

COLORS: tuple[str, ...] = ("purple", "white", "blue", "yellow", "orange", "black", "red", "green")
LOCO = "loco"
CARD_TYPES: tuple[str, ...] = (*COLORS, LOCO)
CARDS_PER_COLOR = 12
LOCOS_IN_DECK = 14

# Points for claiming a route of a given length.
ROUTE_POINTS: Mapping[int, int] = {1: 1, 2: 2, 3: 4, 4: 7, 5: 10, 6: 15, 7: 18, 8: 21, 10: 40}


class City(NamedTuple):
    name: str
    x: float
    y: float
    label: str  # side of the dot the name is drawn on: n, s, e, w, ne, nw, se, sw
    country: str = ""  # only the UK map uses it (technology concessions)
    sites: tuple[tuple[float, float], ...] = ()  # more places where the same city is drawn (France on the UK map)


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
    # Where the route starts and ends when that isn't the city's main spot (a city with several sites).
    ends: tuple[tuple[float, float], tuple[float, float]] | None = None

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
    key: str
    name: str
    width: float
    height: float
    cities: tuple[City, ...]
    routes: tuple[Route, ...]
    tickets: tuple[Ticket, ...]
    technologies: bool = False

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

    @cached_property
    def tech_needs(self) -> dict[int, frozenset[str]]:
        """Per route: the technologies needed to claim it (empty on maps without technologies)."""
        if not self.technologies:
            return {r.id: frozenset() for r in self.routes}
        country = {c.name: c.country for c in self.cities}
        return {r.id: techs.required(r.length, r.ferry, (country[r.a], country[r.b])) for r in self.routes}

    def to_json(self) -> dict[str, object]:
        return {
            "key": self.key,
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "cities": [c._asdict() for c in self.cities],
            "routes": [
                {**r._asdict(), "points": r.points, "needs": sorted(self.tech_needs[r.id])} for r in self.routes
            ],
            "tickets": [t._asdict() for t in self.tickets],
            "route_points": dict(ROUTE_POINTS),
            "technologies": self.technologies,
            "techs": [dataclasses.asdict(t) for t in techs.TECHS] if self.technologies else [],
            "colors": list(COLORS),
        }
