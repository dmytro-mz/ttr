"""A multiplayer table: members, seats (humans or bots), lobby settings and the game.

All mutations are synchronous and run on the event loop thread. Every change is pushed to
each listener as a full per-viewer snapshot (`Room.state_for`) tagged with the event that
caused it, so clients can animate it. Hidden information (hands, tickets, blind draws) only
goes to its owner until the game is over.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import random
import secrets
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from ttr.bots import REGISTRY, Bot, PlannerBot
from ttr.game import actions
from ttr.game.actions import Action
from ttr.game.engine import Event, Game, IllegalMove, Phase, RulesConfig
from ttr.game.rules import longest_path, tunnel_pay_options

log = logging.getLogger(__name__)

MAX_SEATS = 5
MIN_SEATS = 2
MAX_NAME = 20
MAX_CHAT = 240
CHAT_INTERVAL = 0.4
HOST_GRACE = 20.0
REACTIONS = ("👍", "😂", "😱", "😡", "🎉", "🤔", "😭", "🔥", "👏", "🙈")
BOT_SPEEDS = {"slow": 1.8, "normal": 1.0, "fast": 0.4}
TURN_TIMERS = (0, 30, 60, 90, 180)
PLAYER_COLORS = ("red", "blue", "green", "yellow", "black")

Plan = tuple[float, Callable[[], None]]


class RoomError(Exception):
    """A rejected request; the message is shown to the user."""


class Listener(Protocol):
    member_id: str

    def send(self, message: dict[str, Any]) -> None: ...


@dataclass
class Settings:
    turn_timer: int = 0  # seconds per human turn, 0 = off
    bot_speed: str = "normal"
    hints: bool = False
    doubles_all: bool = False  # house rule: both tracks of double routes open in 2-3 player games

    def update(self, changes: dict[str, Any]) -> None:
        for key, value in changes.items():
            if key == "turn_timer" and value in TURN_TIMERS:
                self.turn_timer = int(value)
            elif key == "bot_speed" and value in BOT_SPEEDS:
                self.bot_speed = str(value)
            elif key in ("hints", "doubles_all") and isinstance(value, bool):
                setattr(self, key, value)
            else:
                raise RoomError(f"invalid setting {key}={value!r}")


@dataclass
class Member:
    id: str
    token: str
    name: str
    connections: int = 0
    disconnected_at: float | None = None
    last_chat: float = 0.0


@dataclass
class Seat:
    name: str
    member_id: str | None = None  # None: a bot
    bot: str | None = None  # REGISTRY key
    agent: Bot | None = None
    autoplay: bool = False  # a human seat temporarily played by the autopilot

    @property
    def is_bot(self) -> bool:
        return self.member_id is None


def clean_text(text: object, limit: int) -> str:
    if not isinstance(text, str):
        return ""
    return " ".join(text.split())[:limit]


def bots_public() -> list[dict[str, Any]]:
    return [{"key": b.key, "label": b.label, "stars": b.stars, "description": b.description} for b in REGISTRY.values()]


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _cards_text(cards: dict[str, int]) -> str:
    return " ".join(f"[{c}]×{n}" if n > 1 else f"[{c}]" for c, n in cards.items() if n)


class Room:
    def __init__(self, room_id: str, delay_scale: float = 1.0, seed: int | None = None) -> None:
        self.id = room_id
        self.delay_scale = delay_scale
        self.rng = random.Random(seed)
        self.members: dict[str, Member] = {}
        self.seats: list[Seat] = []
        self.host_id: str | None = None
        self.settings = Settings()
        self.status = "lobby"  # lobby | playing | game_over
        self.game: Game | None = None
        self.game_no = 0
        self.log: deque[dict[str, Any]] = deque(maxlen=400)
        self.listeners: set[Listener] = set()
        self.seq = 0
        self.last_activity = time.monotonic()
        self.closed = False
        self.last_claim: tuple[int, int] | None = None  # (route, seat) for the board highlight
        self._autopilot = PlannerBot(seed=self.rng.randrange(2**31))
        self._wake = asyncio.Event()
        self._due: tuple[tuple[Any, ...], float] | None = None
        self._deadline: tuple[tuple[Any, ...], float] | None = None
        self._longest: tuple[int, list[int]] | None = None

    # ------------------------------------------------------------------ members
    def join(self, token: str, name: object, origin: str = "") -> Member:
        name = clean_text(name, MAX_NAME)
        member = next((m for m in self.members.values() if m.token == token), None)
        if member is None:
            member = Member(id=secrets.token_hex(4), token=token, name=name or f"Player {len(self.members) + 1}")
            self.members[member.id] = member
            where = f" from {origin}" if origin else ""
            if self.host_id is None:
                self.host_id = member.id
                log.info("table %s opened by %s%s", self.id, member.name, where)
            else:
                log.info("table %s: %s joined%s", self.id, member.name, where)
            self._say(f"{member.name} joined the table")
            if self.status == "lobby" and len(self.seats) < MAX_SEATS:
                self.seats.append(Seat(name=member.name, member_id=member.id))
        elif name and name != member.name:
            self._rename(member, name)
        return member

    def connect(self, listener: Listener) -> None:
        member = self.members[listener.member_id]
        if member.connections == 0 and member.disconnected_at is not None:
            log.info("table %s: %s is back", self.id, member.name)
        member.connections += 1
        member.disconnected_at = None
        self.listeners.add(listener)
        self.last_activity = time.monotonic()
        seat = self.seat_of(member.id)
        if seat is not None and self.seats[seat].autoplay:
            self.seats[seat].autoplay = False
            self._say(f"{member.name} is back and takes over from the autopilot")
        listener.send({"type": "welcome", "you": member.id, "log": list(self.log), "bots": bots_public()})
        self._emit({"kind": "presence"})

    def disconnect(self, listener: Listener) -> None:
        self.listeners.discard(listener)
        member = self.members.get(listener.member_id)
        if member is None:
            return
        member.connections = max(0, member.connections - 1)
        if member.connections == 0:
            member.disconnected_at = time.monotonic()
            log.info("table %s: %s left", self.id, member.name)
        self.last_activity = time.monotonic()
        self._emit({"kind": "presence"})

    def check_host(self) -> None:
        """Hand the host role to a connected member once the host has been gone a while."""
        host = self.members.get(self.host_id or "")
        if host is not None and host.connections:
            return
        if host is not None and host.disconnected_at and time.monotonic() - host.disconnected_at < HOST_GRACE:
            return
        online = [m for m in self.members.values() if m.connections]
        if not online:
            return
        seated = [m for m in online if self.seat_of(m.id) is not None]
        new = (seated or online)[0]
        self.host_id = new.id
        log.info("table %s: %s is now the host", self.id, new.name)
        self._say(f"{new.name} is now the host")
        self._emit({"kind": "presence"})

    def seat_of(self, member_id: str) -> int | None:
        for i, seat in enumerate(self.seats):
            if seat.member_id == member_id:
                return i
        return None

    def _lineup(self) -> str:
        return ", ".join(f"{s.name} (bot)" if s.is_bot else s.name for s in self.seats) or "nobody seated"

    def describe(self) -> str:
        """One line for the server console: who is at this table and what it's doing."""
        host = self.members.get(self.host_id or "")
        online = sum(1 for m in self.members.values() if m.connections)
        seated = {s.member_id for s in self.seats}
        watching = sum(1 for m in self.members.values() if m.connections and m.id not in seated)
        parts = [self.id, self.status.replace("_", " "), f"host {host.name if host else '-'}", self._lineup()]
        parts.append(f"{online} online" + (f", {watching} watching" if watching else ""))
        return " · ".join(parts)

    @property
    def idle_for(self) -> float:
        return 0.0 if self.listeners else time.monotonic() - self.last_activity

    # ------------------------------------------------------------------ requests
    def handle(self, member_id: str, msg: dict[str, Any]) -> dict[str, Any] | None:
        member = self.members[member_id]
        kind = msg.get("type")
        self.last_activity = time.monotonic()
        host_only = {"add_bot", "remove_seat", "settings", "start", "play_again", "to_lobby", "autoplay", "shuffle"}
        if kind in host_only and member_id != self.host_id:
            raise RoomError("Only the host can do that")
        match kind:
            case "rename":
                name = clean_text(msg.get("name"), MAX_NAME)
                if name:
                    self._rename(member, name)
                    self._emit({"kind": "presence"})
            case "chat":
                self._chat(member, msg.get("text"))
            case "react":
                self._react(member, msg.get("emoji"))
            case "sit":
                self._sit(member)
            case "stand":
                self._stand(member)
            case "add_bot":
                self._add_bot(str(msg.get("bot")))
            case "remove_seat":
                self._remove_seat(msg.get("seat"))
            case "shuffle":
                self._require_lobby()
                self.rng.shuffle(self.seats)
                self._emit({"kind": "lobby"})
            case "settings":
                self._require_lobby()
                changes = msg.get("changes")
                if not isinstance(changes, dict):
                    raise RoomError("invalid settings")
                self.settings.update(changes)
                self._emit({"kind": "lobby"})
            case "start" | "play_again":
                self.start()
            case "to_lobby":
                self._to_lobby()
            case "action":
                self._human_action(member, msg.get("action"))
            case "autoplay":
                self._set_autoplay(msg.get("seat"), bool(msg.get("on")))
            case "hint":
                return self._hint(member)
            case _:
                raise RoomError(f"unknown request {kind!r}")
        return None

    def _rename(self, member: Member, name: str) -> None:
        log.info("table %s: %s is now called %s", self.id, member.name, name)
        self._say(f"{member.name} is now called {name}")
        member.name = name
        seat = self.seat_of(member.id)
        if seat is not None:
            self.seats[seat].name = name

    def _chat(self, member: Member, text: object) -> None:
        text = clean_text(text, MAX_CHAT)
        if not text:
            return
        now = time.monotonic()
        if now - member.last_chat < CHAT_INTERVAL:
            raise RoomError("Slow down a little")
        member.last_chat = now
        self._append_log({"kind": "chat", "member": member.id, "name": member.name, "text": text})

    def _react(self, member: Member, emoji: object) -> None:
        if emoji not in REACTIONS:
            raise RoomError("unknown reaction")
        message = {"type": "react", "member": member.id, "seat": self.seat_of(member.id), "emoji": emoji}
        for listener in list(self.listeners):
            listener.send(message)

    def _require_lobby(self) -> None:
        if self.status != "lobby":
            raise RoomError("Only possible in the lobby")

    def _sit(self, member: Member) -> None:
        self._require_lobby()
        if self.seat_of(member.id) is not None:
            return
        if len(self.seats) >= MAX_SEATS:
            raise RoomError("The table is full")
        self.seats.append(Seat(name=member.name, member_id=member.id))
        self._emit({"kind": "lobby"})

    def _stand(self, member: Member) -> None:
        self._require_lobby()
        seat = self.seat_of(member.id)
        if seat is not None:
            del self.seats[seat]
            self._emit({"kind": "lobby"})

    def _add_bot(self, key: str) -> None:
        self._require_lobby()
        bot = REGISTRY.get(key)
        if bot is None:
            raise RoomError("Unknown bot")
        if len(self.seats) >= MAX_SEATS:
            raise RoomError("The table is full")
        names = {s.name for s in self.seats}
        name, n = bot.label, 1
        while name in names:
            n += 1
            name = f"{bot.label} {n}"
        self.seats.append(Seat(name=name, bot=key))
        self._emit({"kind": "lobby"})

    def _remove_seat(self, seat: object) -> None:
        self._require_lobby()
        if not isinstance(seat, int) or not 0 <= seat < len(self.seats):
            raise RoomError("No such seat")
        del self.seats[seat]
        self._emit({"kind": "lobby"})

    def _set_autoplay(self, seat: object, on: bool) -> None:
        if self.status != "playing" or not isinstance(seat, int) or not 0 <= seat < len(self.seats):
            raise RoomError("No such seat")
        target = self.seats[seat]
        if target.is_bot:
            raise RoomError("That seat is already a bot")
        member = self.members[target.member_id or ""]
        if on and member.connections:
            raise RoomError(f"{target.name} is still connected")
        target.autoplay = on
        self._say(f"The autopilot plays for {target.name}" if on else f"{target.name} plays again")
        self._emit({"kind": "presence"})

    # ------------------------------------------------------------------ game flow
    def start(self) -> None:
        if self.status == "playing":
            raise RoomError("A game is already running")
        n = len(self.seats)
        if n < MIN_SEATS:
            raise RoomError("Add at least one more player or bot")
        for seat in self.seats:
            seat.agent = REGISTRY[seat.bot].make(self.rng.randrange(2**31)) if seat.bot else None
            seat.autoplay = False
        rules = RulesConfig(double_min_players=2) if self.settings.doubles_all else RulesConfig()
        self.game = Game(n, seed=self.rng.randrange(2**63), rules_config=rules)
        self.game_no += 1
        self.status = "playing"
        self.last_claim = None
        self._longest = None
        log.info("table %s: game %d started with %s", self.id, self.game_no, self._lineup())
        self._say(f"Game {self.game_no} starts! Choose at least 2 of your 4 destination tickets.")
        self._emit({"kind": "game_start"})

    def _to_lobby(self) -> None:
        if self.status == "lobby":
            return
        self.status = "lobby"
        self.game = None
        for seat in self.seats:
            seat.agent = None
            seat.autoplay = False
        for member in self.members.values():
            if member.connections and self.seat_of(member.id) is None and len(self.seats) < MAX_SEATS:
                self.seats.append(Seat(name=member.name, member_id=member.id))
        self._say("Back to the lobby")
        self._emit({"kind": "lobby"})

    def _game(self) -> Game:
        if self.game is None or self.status != "playing":
            raise RoomError("No game in progress")
        return self.game

    def _is_auto(self, seat: int) -> bool:
        s = self.seats[seat]
        return s.is_bot or s.autoplay

    def _agent(self, seat: int) -> Bot:
        return self.seats[seat].agent or self._autopilot

    def _human_action(self, member: Member, data: object) -> None:
        seat = self.seat_of(member.id)
        if seat is None:
            raise RoomError("You are watching this game")
        self._game()
        try:
            action = actions.from_json(data)
        except actions.BadAction as e:
            raise RoomError(str(e)) from None
        if self.seats[seat].autoplay:
            self.seats[seat].autoplay = False
        self._apply(seat, action)

    def _auto_move(self, seat: int) -> None:
        game = self._game()
        self._apply(seat, self._agent(seat).act(game.view(seat)))

    def _apply(self, seat: int, action: Action) -> None:
        game = self._game()
        try:
            events = game.step(seat, action)
        except IllegalMove as e:
            raise RoomError(str(e)) from None
        for ev in events:
            self._narrate(ev)
        if any(ev["kind"] == "claim" for ev in events):
            self._longest = None
        if game.phase == Phase.GAME_OVER:
            self.status = "game_over"
            self._end_game()
        self._emit({"kind": "move", "seat": seat, "events": events})

    def _narrate(self, ev: Event) -> None:
        game = self.game
        assert game is not None
        seat = ev.get("seat")
        name = self.seats[seat].name if seat is not None else ""
        match ev["kind"]:
            case "draw_face_up":
                self._say(f"{name} took a face-up [{ev['card']}]", seat)
            case "draw_blind":
                self._say(f"{name} drew a card from the deck", seat)
            case "market_reset":
                self._say("Three locomotives face up — the five cards are replaced")
            case "reshuffle" if "deck_left" in ev:
                left = _plural(ev["deck_left"], "card")
                self._say(
                    f"🔀 Only {left} left for the tunnel — {_plural(ev['cards'], 'discarded card')} "
                    "shuffled in to reveal the rest"
                )
            case "reshuffle":
                self._say(f"🔀 The deck ran out — {_plural(ev['cards'], 'discarded card')} shuffled into a new deck")
            case "claim":
                r = game.route(ev["route"])
                self.last_claim = (r.id, seat)
                self._say(f"{name} claimed {r.label} with {_cards_text(ev['cards'])} (+{ev['points']})", seat)
            case "tunnel":
                r = game.route(ev["route"])
                shown = " ".join(f"[{c}]" for c in ev["revealed"]) or "nothing"
                extra = ev["extra"]
                tail = f"{_plural(extra, 'extra card')} needed" if extra else "no extra cards!"
                self._say(f"{name} digs the {r.label} tunnel: {shown} — {tail}", seat)
            case "tunnel_declined":
                self._say(f"{name} gave up the {game.route(ev['route']).label} tunnel", seat)
            case "draw_tickets":
                self._say(f"{name} draws {_plural(ev['count'], 'destination ticket')}", seat)
            case "keep_tickets":
                kept = len(ev["kept"])
                self._say(
                    f"{name} kept {_plural(kept, 'ticket')}"
                    + (f", returned {ev['returned']}" if ev["returned"] else ""),
                    seat,
                )
            case "start":
                self._say(f"Everyone has their tickets. {name} goes first!", seat)
            case "station":
                self._say(f"{name} built a station in {ev['city']} with {_cards_text(ev['cards'])}", seat)
            case "last_round":
                self._say(f"🚂 {name} is down to {_plural(ev['trains'], 'train')} — everyone gets one last turn!", seat)
            case "pass":
                self._say(f"{name} can't do anything and passes", seat)

    def _end_game(self) -> None:
        game = self.game
        assert game is not None and game.result is not None
        res = game.result
        winners = " & ".join(self.seats[w].name for w in res.winners)
        scores = ", ".join(f"{s.name} {r.total}" for s, r in zip(self.seats, res.players, strict=True))
        log.info("table %s: game %d won by %s (%s)", self.id, self.game_no, winners, scores)
        self._say(f"🏆 {winners} won! Final scores: {scores}")

    # ------------------------------------------------------------------ hints
    def _hint(self, member: Member) -> dict[str, Any]:
        if not self.settings.hints:
            raise RoomError("Hints are turned off at this table")
        seat = self.seat_of(member.id)
        if seat is None:
            raise RoomError("You are watching this game")
        game = self._game()
        if not self._waiting_on(seat):
            raise RoomError("It's not your turn")
        action = self._autopilot.act(game.view(seat))
        return {"type": "hint", "action": actions.to_json(action)}

    def _waiting_on(self, seat: int) -> bool:
        game = self.game
        if game is None or self.status != "playing":
            return False
        if game.phase == Phase.INITIAL_TICKETS:
            return bool(game.players[seat].offer)
        return game.current == seat

    # ------------------------------------------------------------------ automation
    def _wait(self, key: tuple[Any, ...], delay: float) -> float:
        now = time.monotonic()
        if self._due is None or self._due[0] != key:
            self._due = (key, now + delay * self.delay_scale)
        return max(0.0, self._due[1] - now)

    def _bot_delay(self, base: float) -> float:
        return base * BOT_SPEEDS[self.settings.bot_speed]

    def plan(self) -> Plan | None:
        """The next automatic step as (seconds to wait, action), or None to wait for a human."""
        if self.status != "playing" or self.game is None:
            return None
        game = self.game
        if game.phase == Phase.INITIAL_TICKETS:
            for seat in range(len(self.seats)):
                if game.players[seat].offer and self._is_auto(seat):
                    delay = self._wait(("tickets", self.game_no, seat), self._bot_delay(1.2))
                    return delay, lambda s=seat: self._auto_move(s)
        elif self._is_auto(game.current):
            base = {Phase.SECOND_CARD: 0.8, Phase.TUNNEL: 1.6, Phase.CHOOSE_TICKETS: 1.4}.get(game.phase, 1.1)
            delay = self._wait(("move", self.game_no, game.turn, game.phase), self._bot_delay(base))
            return delay, lambda s=game.current: self._auto_move(s)
        if self._deadline is not None:
            return max(0.0, self._deadline[1] - time.monotonic()), self._timeout
        return None

    def _refresh_deadline(self) -> None:
        timer = self.settings.turn_timer
        key: tuple[Any, ...] | None = None
        game = self.game
        if timer and self.status == "playing" and game is not None:
            if game.phase == Phase.INITIAL_TICKETS:
                if any(game.players[s].offer and not self._is_auto(s) for s in range(len(self.seats))):
                    key = ("tickets", self.game_no)
            elif not self._is_auto(game.current):
                key = ("turn", self.game_no, game.turn)
        if key is None:
            self._deadline = None
        elif self._deadline is None or self._deadline[0] != key:
            # Choosing the first tickets takes longer than an ordinary turn.
            self._deadline = (key, time.monotonic() + timer * (2 if key[0] == "tickets" else 1))

    def _timeout(self) -> None:
        game = self._game()
        if game.phase == Phase.INITIAL_TICKETS:
            for seat in range(len(self.seats)):
                if game.players[seat].offer and not self._is_auto(seat):
                    self._say(f"⏱ {self.seats[seat].name} ran out of time — the autopilot picks tickets")
                    self._auto_move(seat)
            return
        seat = game.current
        self._say(f"⏱ {self.seats[seat].name} ran out of time — the autopilot moves")
        turn = game.turn
        while self.status == "playing" and game.current == seat and game.turn == turn:
            self._auto_move(seat)

    async def drive(self) -> None:
        """Run bot moves and timeouts until the room is closed."""
        while not self.closed:
            self._wake.clear()
            plan = self.plan()
            if plan is None:
                await self._wake.wait()
                continue
            delay, step = plan
            if delay > 0:
                try:
                    await asyncio.wait_for(self._wake.wait(), delay)
                    continue
                except TimeoutError:
                    pass
            try:
                step()
            except Exception:
                log.exception("room %s: automatic step failed", self.id)
                self._say("⚠️ A bot crashed; the game is back in the lobby")
                self._to_lobby()
            await asyncio.sleep(0)

    def close(self) -> None:
        self.closed = True
        self._wake.set()

    # ------------------------------------------------------------------ output
    def _append_log(self, entry: dict[str, Any]) -> None:
        entry["ts"] = time.time()
        self.log.append(entry)
        for listener in list(self.listeners):
            listener.send({"type": "log", "entry": entry})

    def _say(self, text: str, seat: int | None = None) -> None:
        self._append_log({"kind": "game", "text": text, "seat": seat})

    def _emit(self, event: dict[str, Any]) -> None:
        self._refresh_deadline()
        self.seq += 1
        event["seq"] = self.seq
        for listener in list(self.listeners):
            listener.send(self.state_for(listener.member_id, event))
        self._wake.set()

    def state_for(self, member_id: str, event: dict[str, Any] | None = None) -> dict[str, Any]:
        you = self.seat_of(member_id)
        seats = []
        for i, s in enumerate(self.seats):
            member = self.members.get(s.member_id or "")
            seats.append(
                {
                    "seat": i,
                    "name": s.name,
                    "member": s.member_id,
                    "bot": s.bot,
                    "color": PLAYER_COLORS[i % len(PLAYER_COLORS)],
                    "connected": True if member is None else member.connections > 0,
                    "autoplay": s.autoplay,
                }
            )
        seated = {s.member_id for s in self.seats}
        spectators = [
            {"member": m.id, "name": m.name, "connected": m.connections > 0}
            for m in self.members.values()
            if m.id not in seated
        ]
        if event is not None and event.get("kind") == "move":
            event = {**event, "events": [self._filter_event(e, you) for e in event["events"]]}
        return {
            "type": "state",
            "seq": self.seq,
            "event": event,
            "room": self.id,
            "status": self.status,
            "host": self.host_id,
            "you": {"member": member_id, "seat": you},
            "settings": dataclasses.asdict(self.settings),
            "seats": seats,
            "spectators": spectators,
            "game": self._game_state(you),
        }

    def _filter_event(self, ev: Event, you: int | None) -> Event:
        if self.status == "game_over" or ev.get("seat") == you:
            return ev
        if ev["kind"] == "draw_blind":
            return {**ev, "card": None}
        if ev["kind"] == "draw_tickets":
            return {**ev, "tickets": None}
        if ev["kind"] == "keep_tickets":
            return {**ev, "kept": len(ev["kept"])}
        return ev

    def _longest_paths(self, game: Game) -> list[int]:
        key = len(game.owners)
        if self._longest is None or self._longest[0] != key:
            self._longest = (key, [longest_path([game.route(r) for r in p.routes]) for p in game.players])
        return self._longest[1]

    def _game_state(self, you: int | None) -> dict[str, Any] | None:
        game = self.game
        if game is None:
            return None
        over = game.phase == Phase.GAME_OVER
        longest = self._longest_paths(game)
        players = []
        for seat, p in enumerate(game.players):
            players.append(
                {
                    "trains": p.trains,
                    "stations": list(p.stations),
                    "hand": p.hand_size,
                    "tickets": len(p.tickets),
                    "points": p.points,
                    "choosing": bool(p.offer),
                    "longest": longest[seat],
                    "routes": len(p.routes),
                }
            )
        tunnel = None
        if game.tunnel is not None:
            t = game.tunnel
            tunnel = {
                "route": t.route,
                "seat": game.current,
                "revealed": t.revealed,
                "extra": t.extra,
                "color": t.color,
            }
        state: dict[str, Any] = {
            "phase": game.phase.value,
            "current": game.current if game.phase not in (Phase.INITIAL_TICKETS, Phase.GAME_OVER) else None,
            "turn": game.turn,
            "final_turns": game.final_turns,
            "last_round_by": game.last_round_by,
            "deck": len(game.deck),
            "discard": len(game.discard),
            "face_up": list(game.face_up),
            "tickets_left": len(game.ticket_deck),
            "owners": {str(r): s for r, s in game.owners.items()},
            "stations": dict(game.station_at),
            "players": players,
            "tunnel": tunnel,
            "last_claim": list(self.last_claim) if self.last_claim else None,
            "double_min_players": game.rules.double_min_players,
            "me": self._my_state(game, you) if you is not None else None,
            "result": self._result(game) if over else None,
            "time_left": None,
        }
        if self._deadline is not None:
            state["time_left"] = round(max(0.0, self._deadline[1] - time.monotonic()), 2)
            state["time_total"] = self.settings.turn_timer * (2 if self._deadline[0][0] == "tickets" else 1)
        return state

    def _my_state(self, game: Game, seat: int) -> dict[str, Any]:
        p = game.players[seat]
        done, borrowed = game.ticket_status(seat)
        playing = self.status == "playing" and not self.seats[seat].autoplay
        my_turn = playing and game.current == seat and game.phase not in (Phase.INITIAL_TICKETS, Phase.GAME_OVER)
        me: dict[str, Any] = {
            "hand": dict(p.hand),
            "tickets": [{"id": t, "done": d} for t, d in zip(p.tickets, done, strict=True)],
            "borrowed": borrowed,
            "offer": list(p.offer) if playing else [],
            "offer_min": p.offer_min,
            "my_turn": my_turn,
            "claimable": {},
            "station_options": [],
            "station_cost": game.station_cost(seat),
            "face_up_ok": [],
            "can_blind": False,
            "can_tickets": False,
            "tunnel_options": [],
            "can_pass": False,
        }
        if my_turn:
            if game.phase in (Phase.TURN, Phase.SECOND_CARD):
                me["face_up_ok"] = [game.can_take_face_up(i) for i in range(len(game.face_up))]
                me["can_blind"] = bool(game.deck or game.discard)
            if game.phase == Phase.TURN:
                me["claimable"] = {str(r): opts for r, opts in game.claimable(seat).items()}
                me["station_options"] = game.station_payments(seat)
                me["can_tickets"] = bool(game.ticket_deck)
                me["can_pass"] = not game.has_move(seat)
            if game.phase == Phase.TUNNEL and game.tunnel is not None:
                me["tunnel_options"] = tunnel_pay_options(game.tunnel.extra, game.tunnel.color, p.hand)
        return me

    def _result(self, game: Game) -> dict[str, Any]:
        assert game.result is not None
        return {
            "winners": game.result.winners,
            "players": [
                {
                    **dataclasses.asdict(r),
                    "tickets": [{"id": t, "done": d} for t, d in r.tickets],
                }
                for r in game.result.players
            ],
        }
