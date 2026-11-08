"""Bot registry. Every entry shows up in the web lobby and in `ttr eval`."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ttr.bots.base import Bot
from ttr.bots.planner import PlannerBot, PlannerConfig, RookieBot


@dataclass(frozen=True)
class BotType:
    key: str
    label: str
    stars: int
    description: str
    make: Callable[[int | None], Bot]


REGISTRY: dict[str, BotType] = {
    b.key: b
    for b in (
        BotType("rookie", "Rookie", 1, "Just learned the rules: random tickets, random routes.", RookieBot),
        BotType(
            "conductor",
            "Conductor",
            3,
            "Plans each ticket on its own, rarely takes new tickets, never builds stations.",
            lambda seed: PlannerBot(
                seed,
                PlannerConfig(
                    overlap=False,
                    ticket_min_trains=26,
                    use_stations=False,
                    loco_greed=0.2,
                    initial_budget=26,
                    endgame=False,
                    long_bias=0.0,
                ),
            ),
        ),
        BotType(
            "expert",
            "Expert",
            5,
            "Plans tickets together, draws more tickets, uses stations and optimises the last turn.",
            lambda seed: PlannerBot(seed),
        ),
    )
}


def make_bot(key: str, seed: int | None = None) -> Bot:
    return REGISTRY[key].make(seed)


__all__ = ["REGISTRY", "Bot", "BotType", "PlannerBot", "PlannerConfig", "RookieBot", "make_bot"]
