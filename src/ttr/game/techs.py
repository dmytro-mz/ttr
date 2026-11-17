"""Technology cards of the United Kingdom map (Map Collection 5).

Players start without technology: only 1- and 2-space routes in England. Every other route needs the
technologies listed by `required` (a concession for each foreign country it touches, one for its length,
one for ferries). Technologies are bought at the start of a turn with locomotives.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tech:
    key: str
    name: str
    cost: int  # locomotives
    text: str
    icon: str


TECHS: tuple[Tech, ...] = (
    Tech("wales", "Wales Concession", 1, "Claim routes into any of the 5 cities in Wales.", "🏴󠁧󠁢󠁷󠁬󠁳󠁿"),
    Tech("scotland", "Scotland Concession", 1, "Claim routes into any of the 10 cities in Scotland.", "🏴󠁧󠁢󠁳󠁣󠁴󠁿"),
    Tech("ireland_france", "Ireland / France Concession", 1, "Claim routes into Ireland (10 cities) and France.", "☘️"),
    Tech("stoker", "Mechanical Stoker", 1, "Claim routes of 3 spaces.", "🔥"),
    Tech("boiler", "Superheated Steam Boiler", 2, "Claim routes of 4, 5 and 6 spaces (3 still needs the Stoker).", "♨️"),
    Tech("propellers", "Propellers", 2, "Claim ferry routes.", "⚓"),
    Tech("booster", "Booster", 2, "Any 3 cards (instead of 4) count as a locomotive.", "🚀"),
    Tech("lagging", "Boiler Lagging", 2, "+1 point for every route you claim from now on.", "➕"),
    Tech("turbines", "Steam Turbines", 2, "+2 points for every ferry you claim (3 with Boiler Lagging).", "🌀"),
    Tech(
        "double_heading", "Double Heading", 4, "At the end of the game, +2 points for each ticket you completed.", "🚂"
    ),
)
TECH_BY_KEY: dict[str, Tech] = {t.key: t for t in TECHS}

DOUBLE_HEADING_POINTS = 2
LAGGING_POINTS = 1
TURBINES_POINTS = 2
BOOSTER_RATE = 3

# Country of a city -> the concession that unlocks routes into it (England needs none).
CONCESSION: dict[str, str] = {
    "wales": "wales",
    "scotland": "scotland",
    "ireland": "ireland_france",
    "france": "ireland_france",
}
FREE = "free"  # routes touching a city of this country (Southampton–New York) need no technology at all


def required(length: int, ferry: int, countries: tuple[str, str]) -> frozenset[str]:
    """Technologies needed to claim a route of `length` between cities of the given countries."""
    if FREE in countries:
        return frozenset()
    need = {CONCESSION[c] for c in countries if c in CONCESSION}
    if length == 3:
        need.add("stoker")
    elif length >= 4:
        need.add("boiler")
    if ferry:
        need.add("propellers")
    return frozenset(need)
