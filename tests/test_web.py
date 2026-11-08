from typing import Any

import pytest
from fastapi.testclient import TestClient

from ttr.game.engine import Phase
from ttr.web.room import Room, RoomError
from ttr.web.server import create_app

TOKENS = ["a" * 32, "b" * 32, "c" * 32]


class Inbox:
    def __init__(self, member_id: str) -> None:
        self.member_id = member_id
        self.messages: list[dict[str, Any]] = []

    def send(self, message: dict[str, Any]) -> None:
        self.messages.append(message)

    @property
    def last_state(self) -> dict[str, Any]:
        return next(m for m in reversed(self.messages) if m["type"] == "state")


def _room(humans: int = 2, bots: tuple[str, ...] = ("expert",)) -> tuple[Room, list[Inbox]]:
    room = Room("TEST", delay_scale=0.0, seed=5)
    inboxes = []
    for i in range(humans):
        member = room.join(TOKENS[i], f"Human {i}")
        inbox = Inbox(member.id)
        room.connect(inbox)
        inboxes.append(inbox)
    host = inboxes[0].member_id
    for key in bots:
        room.handle(host, {"type": "add_bot", "bot": key})
    return room, inboxes


def _human_move(room: Room, inbox: Inbox) -> bool:
    """Play one sensible action for this human through the room protocol, if it's their move."""
    me = room.state_for(inbox.member_id)["game"]["me"]
    if me["offer"]:
        action: dict[str, Any] = {"type": "keep_tickets", "tickets": me["offer"]}
    elif not me["my_turn"]:
        return False
    elif me["tunnel_options"]:
        action = {"type": "tunnel_pay", "locos": me["tunnel_options"][0]}
    elif room.game is not None and room.game.phase == Phase.TUNNEL:
        action = {"type": "tunnel_decline"}
    elif me["claimable"]:
        rid, options = next(iter(me["claimable"].items()))
        color, locos = options[0]
        action = {"type": "claim", "route": int(rid), "color": color, "locos": locos}
    elif me["can_blind"]:
        action = {"type": "draw_card", "slot": None}
    elif any(me["face_up_ok"]):
        action = {"type": "draw_card", "slot": me["face_up_ok"].index(True)}
    elif me["can_tickets"]:
        action = {"type": "draw_tickets"}
    else:
        action = {"type": "pass"}
    room.handle(inbox.member_id, {"type": "action", "action": action})
    return True


def _run(room: Room, inboxes: list[Inbox], limit: int = 5000) -> None:
    for _ in range(limit):
        if room.status != "playing":
            return
        if any(_human_move(room, inbox) for inbox in inboxes):
            continue
        plan = room.plan()
        assert plan is not None, "nobody can move"
        plan[1]()
    raise AssertionError("game did not finish")


def test_full_game_with_humans_and_a_bot() -> None:
    room, inboxes = _room()
    room.handle(inboxes[0].member_id, {"type": "start"})
    assert room.status == "playing"
    _run(room, inboxes)
    assert room.status == "game_over"
    result = inboxes[1].last_state["game"]["result"]
    assert result and len(result["players"]) == 3
    assert all(
        p["total"] == p["route_points"] + p["ticket_points"] + p["station_points"] + p["express_points"]
        for p in result["players"]
    )


def test_no_hidden_information_leaks() -> None:
    room, inboxes = _room()
    room.handle(inboxes[0].member_id, {"type": "start"})
    game = room.game
    assert game is not None
    public_player_keys = {"trains", "stations", "hand", "tickets", "points", "choosing", "longest", "routes"}
    hidden_events = 0
    seen = [0] * len(inboxes)
    for _ in range(4000):
        if room.status != "playing":
            break
        for i, inbox in enumerate(inboxes):
            seat = room.seat_of(inbox.member_id)
            assert seat is not None
            for msg in inbox.messages[seen[i] :]:
                if msg["type"] != "state" or msg["game"] is None:
                    continue
                g = msg["game"]
                for p in g["players"]:
                    assert set(p) == public_player_keys
                    assert isinstance(p["hand"], int) and isinstance(p["tickets"], int)
                assert set(g["me"]["offer"]) <= set(game.players[seat].offer) | set(game.players[seat].tickets)
                for e in (msg["event"] or {}).get("events", []):
                    if e.get("seat") == seat:
                        continue
                    if e["kind"] in ("draw_blind", "draw_tickets", "keep_tickets"):
                        hidden_events += 1
                    if e["kind"] == "draw_blind":
                        assert e["card"] is None
                    if e["kind"] == "draw_tickets":
                        assert e["tickets"] is None
                    if e["kind"] == "keep_tickets":
                        assert isinstance(e["kept"], int)
            seen[i] = len(inbox.messages)
        if any(_human_move(room, inbox) for inbox in inboxes):
            continue
        room.plan()[1]()  # type: ignore[index]
    assert room.status == "game_over"
    assert hidden_events > 50


def test_state_never_contains_other_players_ticket_ids() -> None:
    room, inboxes = _room(humans=2, bots=())
    room.handle(inboxes[0].member_id, {"type": "start"})
    game = room.game
    assert game is not None
    other_tickets = set(game.players[1].offer)
    state = room.state_for(inboxes[0].member_id)
    mine = set(state["game"]["me"]["offer"])
    assert mine.isdisjoint(other_tickets)
    assert "offer" not in state["game"]["players"][1]


def test_only_the_host_runs_the_table() -> None:
    room, inboxes = _room()
    with pytest.raises(RoomError):
        room.handle(inboxes[1].member_id, {"type": "start"})
    with pytest.raises(RoomError):
        room.handle(inboxes[1].member_id, {"type": "add_bot", "bot": "rookie"})


def test_illegal_actions_are_rejected_without_changing_state() -> None:
    room, inboxes = _room()
    room.handle(inboxes[0].member_id, {"type": "start"})
    with pytest.raises(RoomError):
        room.handle(inboxes[0].member_id, {"type": "action", "action": {"type": "draw_card", "slot": None}})
    with pytest.raises(RoomError):
        room.handle(inboxes[0].member_id, {"type": "action", "action": {"type": "nonsense"}})


def test_hints_are_off_unless_the_host_enables_them() -> None:
    room, inboxes = _room()
    room.handle(inboxes[0].member_id, {"type": "start"})
    with pytest.raises(RoomError):
        room.handle(inboxes[0].member_id, {"type": "hint"})


def test_hint_suggests_a_legal_action() -> None:
    room, inboxes = _room()
    room.handle(inboxes[0].member_id, {"type": "settings", "changes": {"hints": True}})
    room.handle(inboxes[0].member_id, {"type": "start"})
    reply = room.handle(inboxes[0].member_id, {"type": "hint"})
    assert reply is not None and reply["type"] == "hint"
    assert reply["action"]["type"] == "keep_tickets"
    room.handle(inboxes[0].member_id, {"type": "action", "action": reply["action"]})


def test_http_and_websocket_smoke() -> None:
    app = create_app(delay_scale=0.0)
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/static/app.js").status_code == 200
        board = client.get("/api/map").json()
        assert len(board["routes"]) == len({r["id"] for r in board["routes"]})
        config = client.get("/api/config").json()
        assert {b["key"] for b in config["bots"]} >= {"rookie", "conductor", "expert"}
        code = client.post("/api/rooms").json()["room"]
        assert client.get(f"/api/rooms/{code}").json()["status"] == "lobby"
        with client.websocket_connect(f"/ws/{code}") as ws:
            ws.send_json({"token": TOKENS[0], "name": "Ada"})
            assert ws.receive_json()["type"] == "welcome"
            state = ws.receive_json()
            assert state["type"] == "state" and state["seats"][0]["name"] == "Ada"
            ws.send_json({"type": "add_bot", "bot": "rookie"})
            while (msg := ws.receive_json())["type"] != "state":
                pass
            assert len(msg["seats"]) == 2
        assert client.get("/api/rooms/NOPE").status_code == 404
