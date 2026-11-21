"""The playable maps, each with its rules."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ttr.game.engine import RulesConfig, uk_rules
from ttr.game.europe import EUROPE
from ttr.game.model import MapData
from ttr.game.uk import UK


@dataclass(frozen=True)
class MapInfo:
    key: str
    label: str
    board: MapData
    rules: Callable[[], RulesConfig]
    min_players: int
    max_players: int
    blurb: str

    def public(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "min_players": self.min_players,
            "max_players": self.max_players,
            "blurb": self.blurb,
            "trains": self.rules().trains,
            "technologies": self.rules().technologies,
        }


MAPS: dict[str, MapInfo] = {
    m.key: m
    for m in (
        MapInfo(
            "europe",
            "Europe",
            EUROPE,
            RulesConfig,
            2,
            5,
            "The classic: 45 trains, tunnels, ferries and stations. 2–5 players.",
        ),
        MapInfo(
            "uk",
            "United Kingdom",
            UK,
            uk_rules,
            2,
            4,
            "Map Collection 5: 35 trains, 57 tickets and technology cards that unlock longer routes, "
            "Wales, Scotland, Ireland and ferries. 2–4 players.",
        ),
    )
}
DEFAULT_MAP = "europe"
