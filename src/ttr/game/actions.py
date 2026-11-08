"""Player actions and their JSON form (the web protocol uses `to_json` / `from_json`)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ttr.game.model import COLORS


@dataclass(frozen=True)
class DrawCard:
    slot: int | None  # face-up slot 0..4, None = top of the deck


@dataclass(frozen=True)
class Claim:
    route: int
    color: str | None  # the one non-locomotive colour paid with (None when paying only locomotives)
    locos: int


@dataclass(frozen=True)
class TunnelPay:
    locos: int  # locomotives among the extra cards, the rest in the colour already played


@dataclass(frozen=True)
class TunnelDecline:
    pass


@dataclass(frozen=True)
class DrawTickets:
    pass


@dataclass(frozen=True)
class KeepTickets:
    tickets: tuple[int, ...]


@dataclass(frozen=True)
class BuildStation:
    city: str
    color: str | None
    locos: int


@dataclass(frozen=True)
class Pass:
    """Only legal when no other action is possible."""


Action = DrawCard | Claim | TunnelPay | TunnelDecline | DrawTickets | KeepTickets | BuildStation | Pass


class BadAction(ValueError):
    pass


def _int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BadAction(f"{name} must be an integer")
    return value


def _color(value: object) -> str | None:
    if value is None or value in COLORS:
        return value  # type: ignore[return-value]
    raise BadAction("unknown colour")


def from_json(data: object) -> Action:
    if not isinstance(data, dict):
        raise BadAction("action must be an object")
    match data.get("type"):
        case "draw_card":
            slot = data.get("slot")
            return DrawCard(None if slot is None else _int(slot, "slot"))
        case "claim":
            return Claim(
                _int(data.get("route"), "route"), _color(data.get("color")), _int(data.get("locos", 0), "locos")
            )
        case "tunnel_pay":
            return TunnelPay(_int(data.get("locos", 0), "locos"))
        case "tunnel_decline":
            return TunnelDecline()
        case "draw_tickets":
            return DrawTickets()
        case "keep_tickets":
            tickets = data.get("tickets")
            if not isinstance(tickets, list):
                raise BadAction("tickets must be a list")
            return KeepTickets(tuple(_int(t, "ticket") for t in tickets))
        case "station":
            city = data.get("city")
            if not isinstance(city, str):
                raise BadAction("city must be a string")
            return BuildStation(city, _color(data.get("color")), _int(data.get("locos", 0), "locos"))
        case "pass":
            return Pass()
    raise BadAction("unknown action")


def to_json(action: Action) -> dict[str, Any]:
    match action:
        case DrawCard(slot):
            return {"type": "draw_card", "slot": slot}
        case Claim(route, color, locos):
            return {"type": "claim", "route": route, "color": color, "locos": locos}
        case TunnelPay(locos):
            return {"type": "tunnel_pay", "locos": locos}
        case TunnelDecline():
            return {"type": "tunnel_decline"}
        case DrawTickets():
            return {"type": "draw_tickets"}
        case KeepTickets(tickets):
            return {"type": "keep_tickets", "tickets": list(tickets)}
        case BuildStation(city, color, locos):
            return {"type": "station", "city": city, "color": color, "locos": locos}
        case Pass():
            return {"type": "pass"}
    raise BadAction("unknown action")
