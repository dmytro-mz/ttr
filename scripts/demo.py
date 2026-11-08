"""Serve a pre-played table and screenshot it (visual checks during development).

uv run python scripts/demo.py [--moves 60] [--bots 3] [--stage play|tickets|over|lobby] [--size 1440x900]
                              [--out shots/game.png] [--serve]
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from ttr.game.engine import Phase
from ttr.web.room import Room
from ttr.web.server import create_app

TOKEN = "d" * 32
PORT = 8765


def prepare(stage: str = "play", moves: int = 60, bots: int = 3, seed: int = 3, delay_scale: float = 0.0) -> Room:
    """A room with one human ("Dima", token TOKEN) and bots, fast-forwarded to `stage`."""
    room = Room("DEMO", delay_scale=delay_scale, seed=seed)
    me = room.join(TOKEN, "Dima")
    for key in ["expert", "conductor", "rookie", "expert"][:bots]:
        room.handle(me.id, {"type": "add_bot", "bot": key})
    if stage == "lobby":
        return room
    room.handle(me.id, {"type": "start"})
    seat = room.seat_of(me.id)
    game = room.game
    assert seat is not None and game is not None
    if stage == "tickets":
        return room
    room.seats[seat].autoplay = True
    target = 10_000 if stage == "over" else moves
    while room.status == "playing" and game.turn < target:
        room.plan()[1]()  # type: ignore[index]
    room.seats[seat].autoplay = False
    while stage == "play" and room.status == "playing" and (game.current != seat or game.phase != Phase.TURN):
        room.plan()[1]()  # type: ignore[index]
    return room


@contextlib.asynccontextmanager
async def serving(app: FastAPI, room: Room, port: int = PORT) -> AsyncIterator[str]:
    """Run the app in this event loop with `room` adopted; yields the player's personal URL."""
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)
    app.state.manager.adopt(room)
    try:
        yield f"http://127.0.0.1:{port}/r/{room.id}?me={TOKEN}"
    finally:
        server.should_exit = True
        await task


async def run(args: argparse.Namespace) -> None:
    room = prepare(args.stage, args.moves, args.bots, args.seed)
    app = create_app()
    async with serving(app, room) as url:
        w, h = args.size.split("x")
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        shot = Path(__file__).with_name("shot.py")
        proc = await asyncio.create_subprocess_exec(sys.executable, str(shot), url, args.out, w, h)
        await proc.wait()
        if args.serve:
            print(f"serving {url}  (Ctrl+C to stop)")
            await asyncio.Event().wait()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--moves", type=int, default=60)
    ap.add_argument("--bots", type=int, default=3)
    ap.add_argument("--stage", default="play", choices=["play", "tickets", "over", "lobby"])
    ap.add_argument("--size", default="1440x900")
    ap.add_argument("--out", default="shots/game.png")
    ap.add_argument("--serve", action="store_true", help="keep serving after the screenshot")
    ap.add_argument("--seed", type=int, default=3)
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
