"""Ticket to Ride: Europe game state machine (see docs/rules.md).

`Game.step(seat, action)` validates and applies one action and returns the events it caused.
Events carry full information (e.g. the colour of a blind-drawn card); callers that show them
to other players must filter them (`ttr.web.room` does).
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ttr.game import rules
from ttr.game.actions import (
    Action,
    BuildStation,
    Claim,
    DrawCard,
    DrawTickets,
    KeepTickets,
    Pass,
    TunnelDecline,
    TunnelPay,
)
from ttr.game.europe import EUROPE
from ttr.game.model import CARDS_PER_COLOR, COLORS, LOCO, LOCOS_IN_DECK, MapData, Route, Ticket

Event = dict[str, Any]


class Phase(StrEnum):
    INITIAL_TICKETS = "initial_tickets"  # everyone picks their first tickets at once
    TURN = "turn"  # current player picks one of the four actions
    SECOND_CARD = "second_card"  # after a first train card that wasn't a face-up locomotive
    CHOOSE_TICKETS = "choose_tickets"
    TUNNEL = "tunnel"  # tunnel cards revealed, player pays the extra or gives up
    GAME_OVER = "game_over"


class IllegalMove(Exception):
    """The action is not allowed in the current state; the message is user-facing."""


@dataclass
class RulesConfig:
    trains: int = 45
    stations: int = 3
    station_value: int = 4
    hand_size: int = 4
    face_up: int = 5
    max_face_up_locos: int = 2  # a third face-up locomotive wipes the market
    initial_offer: int = 3  # short tickets, plus one long ticket
    initial_keep: int = 2
    ticket_draw: int = 3
    tunnel_reveal: int = 3
    end_trains: int = 2  # a turn ending with this many trains or fewer starts the last round
    express_bonus: int = 10
    double_min_players: int = 4  # with fewer players only one track of a double route is used
    max_turns: int = 1000  # stalemate guard


@dataclass
class Player:
    hand: Counter[str] = field(default_factory=Counter)
    tickets: list[int] = field(default_factory=list)
    offer: list[int] = field(default_factory=list)
    offer_min: int = 0
    trains: int = 45
    stations: list[str] = field(default_factory=list)
    routes: list[int] = field(default_factory=list)
    points: int = 0  # route points scored during play
    turns: int = 0

    @property
    def hand_size(self) -> int:
        return sum(self.hand.values())


@dataclass
class TunnelState:
    route: int
    color: str | None
    locos: int
    revealed: list[str]
    extra: int


@dataclass
class PlayerResult:
    route_points: int
    tickets: list[tuple[int, bool]]  # (ticket id, completed)
    ticket_points: int
    station_points: int
    longest: int
    express: bool
    express_points: int
    borrowed: dict[str, int | None]
    total: int


@dataclass
class GameResult:
    players: list[PlayerResult]
    winners: list[int]


@dataclass(frozen=True)
class View:
    seat: int
    n: int
    phase: Phase
    current: int
    board: MapData
    rules: RulesConfig
    hand: dict[str, int]
    tickets: tuple[int, ...]
    offer: tuple[int, ...]
    offer_min: int
    face_up: tuple[str | None, ...]
    deck_count: int
    discard_count: int
    tickets_left: int
    owners: dict[int, int]
    station_at: dict[str, int]
    trains: tuple[int, ...]
    stations_left: tuple[int, ...]
    hand_counts: tuple[int, ...]
    ticket_counts: tuple[int, ...]
    points: tuple[int, ...]
    final_turns: int | None
    tunnel: TunnelState | None
    claimable: dict[int, list[rules.Payment]]
    station_payments: list[rules.Payment]
    face_up_ok: tuple[bool, ...]
    can_blind: bool

    @property
    def my_trains(self) -> int:
        return self.trains[self.seat]


def build_deck() -> list[str]:
    return [c for c in COLORS for _ in range(CARDS_PER_COLOR)] + [LOCO] * LOCOS_IN_DECK


class Game:
    def __init__(
        self,
        n_players: int,
        seed: int | None = None,
        rules_config: RulesConfig | None = None,
        board: MapData = EUROPE,
        first: int | None = None,
    ) -> None:
        if not 2 <= n_players <= 5:
            raise ValueError("Ticket to Ride: Europe is for 2-5 players")
        self.rules = rules_config or RulesConfig()
        self.board = board
        self.n = n_players
        self.rng = random.Random(seed)
        self.deck = build_deck()
        self.rng.shuffle(self.deck)
        self.discard: list[str] = []
        self.face_up: list[str | None] = [None] * self.rules.face_up
        short = [t.id for t in board.tickets if not t.long]
        long = [t.id for t in board.tickets if t.long]
        self.rng.shuffle(short)
        self.rng.shuffle(long)
        self.ticket_deck: list[int] = short
        self.players = [Player(trains=self.rules.trains) for _ in range(n_players)]
        self.owners: dict[int, int] = {}
        self.station_at: dict[str, int] = {}
        self.current = self.rng.randrange(n_players) if first is None else first
        self.turn = 0
        self.final_turns: int | None = None
        self.last_round_by: int | None = None
        self.tunnel: TunnelState | None = None
        self.result: GameResult | None = None
        self.phase = Phase.INITIAL_TICKETS
        for p in self.players:
            for _ in range(self.rules.hand_size):
                card = self._draw_card()
                assert card is not None
                p.hand[card] += 1
            p.offer = [long.pop()] if long else []
            p.offer += [self.ticket_deck.pop() for _ in range(self.rules.initial_offer)]
            p.offer_min = self.rules.initial_keep
        self._refill_market()

    # ------------------------------------------------------------------ lookups
    def route(self, rid: int) -> Route:
        return self.board.routes[rid]

    def ticket(self, tid: int) -> Ticket:
        return self.board.tickets[tid]

    def station_cost(self, seat: int) -> int:
        return len(self.players[seat].stations) + 1

    def can_draw_card(self) -> bool:
        return bool(self.deck or self.discard) or any(c is not None for c in self.face_up)

    def can_take_face_up(self, slot: int) -> bool:
        card = self.face_up[slot] if 0 <= slot < len(self.face_up) else None
        return card is not None and not (self.phase == Phase.SECOND_CARD and card == LOCO)

    def claimable(self, seat: int) -> dict[int, list[rules.Payment]]:
        """Routes `seat` can claim right now with every way to pay for them."""
        p = self.players[seat]
        out: dict[int, list[rules.Payment]] = {}
        for r in self.board.routes:
            if r.length > p.trains:
                continue
            if not rules.route_open(r, self.owners, seat, self.n, self.rules.double_min_players):
                continue
            options = rules.payment_options(r, p.hand)
            if options:
                out[r.id] = options
        return out

    def station_payments(self, seat: int) -> list[rules.Payment]:
        p = self.players[seat]
        if len(p.stations) >= self.rules.stations or len(self.station_at) >= len(self.board.cities):
            return []
        return rules.station_options(self.station_cost(seat), p.hand)

    def has_move(self, seat: int) -> bool:
        return bool(self.can_draw_card() or self.ticket_deck or self.claimable(seat) or self.station_payments(seat))

    def ticket_status(self, seat: int) -> tuple[list[bool], dict[str, int | None]]:
        p = self.players[seat]
        tickets = [self.ticket(t) for t in p.tickets]
        return rules.best_station_use(self.board, seat, self.owners, self.station_at, tickets)

    def view(self, seat: int) -> View:
        """Everything `seat` may know. Bots only ever see this."""
        p = self.players[seat]
        mine = self.phase not in (Phase.INITIAL_TICKETS, Phase.GAME_OVER) and self.current == seat
        return View(
            seat=seat,
            n=self.n,
            phase=self.phase,
            current=self.current,
            board=self.board,
            rules=self.rules,
            hand=dict(p.hand),
            tickets=tuple(p.tickets),
            offer=tuple(p.offer),
            offer_min=p.offer_min,
            face_up=tuple(self.face_up),
            deck_count=len(self.deck),
            discard_count=len(self.discard),
            tickets_left=len(self.ticket_deck),
            owners=dict(self.owners),
            station_at=dict(self.station_at),
            trains=tuple(q.trains for q in self.players),
            stations_left=tuple(self.rules.stations - len(q.stations) for q in self.players),
            hand_counts=tuple(q.hand_size for q in self.players),
            ticket_counts=tuple(len(q.tickets) for q in self.players),
            points=tuple(q.points for q in self.players),
            final_turns=self.final_turns,
            tunnel=self.tunnel if mine else None,
            claimable=self.claimable(seat) if mine and self.phase == Phase.TURN else {},
            station_payments=self.station_payments(seat) if mine and self.phase == Phase.TURN else [],
            face_up_ok=tuple(self.can_take_face_up(i) for i in range(len(self.face_up))),
            can_blind=bool(self.deck or self.discard),
        )

    # ------------------------------------------------------------------ cards
    def _draw_card(self) -> str | None:
        if not self.deck and self.discard:
            self.deck = self.discard
            self.discard = []
            self.rng.shuffle(self.deck)
        return self.deck.pop() if self.deck else None

    def _restock(self) -> list[Event]:
        # The discards become the new deck as soon as the deck runs out, so it never sits at 0 needlessly.
        if self.deck or not self.discard or self.phase == Phase.GAME_OVER:
            return []
        self.deck, self.discard = self.discard, []
        self.rng.shuffle(self.deck)
        return [{"kind": "reshuffle", "cards": len(self.deck)}]

    def _refill_market(self) -> list[Event]:
        events: list[Event] = []
        for _ in range(10):
            for i, c in enumerate(self.face_up):
                if c is None:
                    self.face_up[i] = self._draw_card()
            locos = sum(1 for c in self.face_up if c == LOCO)
            if locos <= self.rules.max_face_up_locos:
                break
            # Wiping is pointless (and could loop forever) if only locomotives are left to deal.
            pool = self.deck + self.discard
            if sum(1 for c in pool if c != LOCO) < 3:
                break
            self.discard.extend(c for c in self.face_up if c is not None)
            self.face_up = [None] * len(self.face_up)
            events.append({"kind": "market_reset"})
        return events

    # ------------------------------------------------------------------ actions
    def step(self, seat: int, action: Action) -> list[Event]:
        events = self._step(seat, action)
        return [*events, *self._restock()]

    def _step(self, seat: int, action: Action) -> list[Event]:
        if self.phase == Phase.GAME_OVER:
            raise IllegalMove("The game is over")
        if self.phase == Phase.INITIAL_TICKETS:
            if not isinstance(action, KeepTickets):
                raise IllegalMove("Choose your destination tickets first")
            return self._keep_tickets(seat, action)
        if seat != self.current:
            raise IllegalMove("It's not your turn")
        match self.phase, action:
            case Phase.TURN | Phase.SECOND_CARD, DrawCard():
                return self._draw(seat, action)
            case Phase.TURN, Claim():
                return self._claim(seat, action)
            case Phase.TURN, DrawTickets():
                return self._draw_tickets(seat)
            case Phase.TURN, BuildStation():
                return self._build_station(seat, action)
            case Phase.TURN, Pass():
                if self.has_move(seat):
                    raise IllegalMove("You can still make a move")
                return [{"kind": "pass", "seat": seat}, *self._end_turn()]
            case Phase.CHOOSE_TICKETS, KeepTickets():
                return self._keep_tickets(seat, action)
            case Phase.TUNNEL, TunnelPay():
                return self._tunnel_pay(seat, action)
            case Phase.TUNNEL, TunnelDecline():
                return self._tunnel_decline(seat)
        raise IllegalMove(_phase_hint(self.phase))

    def _draw(self, seat: int, action: DrawCard) -> list[Event]:
        p = self.players[seat]
        second = self.phase == Phase.SECOND_CARD
        if action.slot is None:
            card = self._draw_card()
            if card is None:
                raise IllegalMove("The deck is empty")
            p.hand[card] += 1
            events: list[Event] = [{"kind": "draw_blind", "seat": seat, "card": card}]
            ends = second
        else:
            if not self.can_take_face_up(action.slot):
                raise IllegalMove("You can't take a face-up locomotive as your second card")
            card = self.face_up[action.slot]
            assert card is not None
            self.face_up[action.slot] = None
            p.hand[card] += 1
            events = [{"kind": "draw_face_up", "seat": seat, "slot": action.slot, "card": card}]
            ends = second or card == LOCO
            events += self._refill_market()
        if not ends:
            self.phase = Phase.SECOND_CARD
            if not (self.deck or self.discard) and not any(self.can_take_face_up(i) for i in range(len(self.face_up))):
                ends = True
        if ends:
            events += self._end_turn()
        return events

    def _claim(self, seat: int, action: Claim) -> list[Event]:
        p = self.players[seat]
        if not 0 <= action.route < len(self.board.routes):
            raise IllegalMove("No such route")
        r = self.route(action.route)
        if not rules.route_open(r, self.owners, seat, self.n, self.rules.double_min_players):
            raise IllegalMove("That route is not available")
        if r.length > p.trains:
            raise IllegalMove("You don't have enough trains left")
        payment = (action.color, action.locos)
        if not rules.valid_payment(r.length, r.color, r.ferry, p.hand, payment):
            raise IllegalMove("You can't pay for that route with those cards")
        color = action.color if action.locos < r.length else None
        cards = rules.payment_cards(r.length, (color, action.locos))
        p.hand.subtract(cards)
        p.hand += Counter()  # drop zero counts
        if not r.tunnel:
            self.discard.extend(Counter(cards).elements())
            return [*self._occupy(seat, r, cards), *self._end_turn()]
        events: list[Event] = []
        if len(self.deck) < self.rules.tunnel_reveal and self.discard:
            events.append({"kind": "reshuffle", "cards": len(self.discard), "deck_left": len(self.deck)})
        revealed = [c for c in (self._draw_card() for _ in range(self.rules.tunnel_reveal)) if c is not None]
        extra = rules.tunnel_extra(revealed, color)
        events.append(
            {"kind": "tunnel", "seat": seat, "route": r.id, "revealed": revealed, "extra": extra, "cards": cards}
        )
        if extra == 0:
            self.discard.extend(revealed)
            self.discard.extend(Counter(cards).elements())
            return [*events, *self._occupy(seat, r, cards), *self._end_turn()]
        self.tunnel = TunnelState(r.id, color, action.locos, revealed, extra)
        self.phase = Phase.TUNNEL
        return events

    def _tunnel_pay(self, seat: int, action: TunnelPay) -> list[Event]:
        t = self.tunnel
        assert t is not None
        p = self.players[seat]
        if action.locos not in rules.tunnel_pay_options(t.extra, t.color, p.hand):
            raise IllegalMove("You can't pay the extra cards that way")
        extra = {LOCO: action.locos} if action.locos else {}
        if t.extra - action.locos:
            assert t.color is not None
            extra[t.color] = t.extra - action.locos
        p.hand.subtract(extra)
        p.hand += Counter()
        r = self.route(t.route)
        paid = Counter(rules.payment_cards(r.length, (t.color, t.locos))) + Counter(extra)
        self.discard.extend(t.revealed)
        self.discard.extend(paid.elements())
        self.tunnel = None
        return [*self._occupy(seat, r, dict(paid)), *self._end_turn()]

    def _tunnel_decline(self, seat: int) -> list[Event]:
        t = self.tunnel
        assert t is not None
        r = self.route(t.route)
        self.players[seat].hand.update(rules.payment_cards(r.length, (t.color, t.locos)))
        self.discard.extend(t.revealed)
        self.tunnel = None
        return [{"kind": "tunnel_declined", "seat": seat, "route": r.id}, *self._end_turn()]

    def _occupy(self, seat: int, r: Route, cards: dict[str, int]) -> list[Event]:
        p = self.players[seat]
        self.owners[r.id] = seat
        p.routes.append(r.id)
        p.trains -= r.length
        p.points += r.points
        return [{"kind": "claim", "seat": seat, "route": r.id, "cards": cards, "points": r.points}]

    def _draw_tickets(self, seat: int) -> list[Event]:
        if not self.ticket_deck:
            raise IllegalMove("There are no destination tickets left")
        p = self.players[seat]
        k = min(self.rules.ticket_draw, len(self.ticket_deck))
        p.offer = [self.ticket_deck.pop() for _ in range(k)]
        p.offer_min = 1
        self.phase = Phase.CHOOSE_TICKETS
        return [{"kind": "draw_tickets", "seat": seat, "count": k, "tickets": list(p.offer)}]

    def _keep_tickets(self, seat: int, action: KeepTickets) -> list[Event]:
        if not 0 <= seat < self.n:
            raise IllegalMove("No such player")
        p = self.players[seat]
        if not p.offer:
            raise IllegalMove("You have no tickets to choose from")
        keep = list(dict.fromkeys(action.tickets))
        if any(t not in p.offer for t in keep):
            raise IllegalMove("You can only keep tickets you were offered")
        if len(keep) < p.offer_min:
            raise IllegalMove(f"Keep at least {p.offer_min} ticket{'s' if p.offer_min > 1 else ''}")
        returned = [t for t in p.offer if t not in keep]
        p.tickets.extend(keep)
        # Returned long tickets leave the game; short ones go under the pile.
        self.ticket_deck[:0] = [t for t in returned if not self.ticket(t).long]
        p.offer = []
        p.offer_min = 0
        events: list[Event] = [{"kind": "keep_tickets", "seat": seat, "kept": keep, "returned": len(returned)}]
        if self.phase == Phase.INITIAL_TICKETS:
            if all(not q.offer for q in self.players):
                self.phase = Phase.TURN
                events.append({"kind": "start", "seat": self.current})
            return events
        return [*events, *self._end_turn()]

    def _build_station(self, seat: int, action: BuildStation) -> list[Event]:
        p = self.players[seat]
        if action.city not in self.board.city_names:
            raise IllegalMove("No such city")
        if len(p.stations) >= self.rules.stations:
            raise IllegalMove("You have no stations left")
        if action.city in self.station_at:
            raise IllegalMove("That city already has a station")
        cost = self.station_cost(seat)
        payment = (action.color, action.locos)
        if not rules.valid_payment(cost, None, 0, p.hand, payment):
            raise IllegalMove(f"A station costs {cost} card{'s' if cost > 1 else ''} of one colour")
        color = action.color if action.locos < cost else None
        cards = rules.payment_cards(cost, (color, action.locos))
        p.hand.subtract(cards)
        p.hand += Counter()
        self.discard.extend(Counter(cards).elements())
        p.stations.append(action.city)
        self.station_at[action.city] = seat
        return [{"kind": "station", "seat": seat, "city": action.city, "cards": cards}, *self._end_turn()]

    # ------------------------------------------------------------------ turn flow
    def _end_turn(self) -> list[Event]:
        seat = self.current
        p = self.players[seat]
        p.turns += 1
        self.turn += 1
        self.phase = Phase.TURN
        events: list[Event] = []
        if self.final_turns is not None:
            self.final_turns -= 1
            if self.final_turns <= 0:
                return [*events, *self._finish()]
        elif p.trains <= self.rules.end_trains:
            self.final_turns = self.n
            self.last_round_by = seat
            events.append({"kind": "last_round", "seat": seat, "trains": p.trains})
        if self.turn >= self.rules.max_turns:
            return [*events, *self._finish()]
        self.current = (seat + 1) % self.n
        events.append({"kind": "turn", "seat": self.current})
        return events

    def _finish(self) -> list[Event]:
        self.phase = Phase.GAME_OVER
        longest = [rules.longest_path([self.route(r) for r in p.routes]) for p in self.players]
        best = max(longest)
        results = []
        for seat, p in enumerate(self.players):
            done, borrowed = self.ticket_status(seat)
            tickets = list(zip(p.tickets, done, strict=True))
            ticket_points = sum(self.ticket(t).value if d else -self.ticket(t).value for t, d in tickets)
            station_points = (self.rules.stations - len(p.stations)) * self.rules.station_value
            express = best > 0 and longest[seat] == best
            express_points = self.rules.express_bonus if express else 0
            results.append(
                PlayerResult(
                    route_points=p.points,
                    tickets=tickets,
                    ticket_points=ticket_points,
                    station_points=station_points,
                    longest=longest[seat],
                    express=express,
                    express_points=express_points,
                    borrowed=borrowed,
                    total=p.points + ticket_points + station_points + express_points,
                )
            )

        def rank(seat: int) -> tuple[int, int, int]:
            r = results[seat]
            return r.total, sum(1 for _, d in r.tickets if d), int(r.express)

        top = max(rank(s) for s in range(self.n))
        winners = [s for s in range(self.n) if rank(s) == top]
        self.result = GameResult(players=results, winners=winners)
        return [{"kind": "game_over", "winners": winners}]


def _phase_hint(phase: Phase) -> str:
    return {
        Phase.TURN: "Draw cards, claim a route, draw tickets or build a station",
        Phase.SECOND_CARD: "Draw your second train card",
        Phase.CHOOSE_TICKETS: "Choose which destination tickets to keep",
        Phase.TUNNEL: "Pay the extra tunnel cards or give up the route",
    }.get(phase, "That move isn't possible now")
