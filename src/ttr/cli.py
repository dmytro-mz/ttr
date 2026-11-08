from __future__ import annotations

import logging
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(add_completion=False, help="Ticket to Ride: Europe — web game and bots")
console = Console()


def _play(args: tuple[list[str], int]) -> tuple[list[str], list[int], list[int]]:
    from ttr.bots import make_bot
    from ttr.runner import play_game

    keys, seed = args
    shift = seed % len(keys)
    seated = keys[shift:] + keys[:shift]
    game = play_game([make_bot(k, seed * 31 + i) for i, k in enumerate(seated)], seed=seed)
    assert game.result is not None
    return seated, game.result.winners, [p.total for p in game.result.players]


@app.command("eval")
def eval_cmd(
    bots: Annotated[
        str, typer.Option("-a", help="Comma-separated bot keys, e.g. expert,conductor")
    ] = "expert,conductor",
    games: Annotated[int, typer.Option("-n", help="Number of games")] = 400,
    workers: int = 8,
) -> None:
    """Bot tournament with rotating seats: win share and mean score per bot."""
    keys = [k.strip() for k in bots.split(",") if k.strip()]
    wins = dict.fromkeys(keys, 0.0)
    scores: dict[str, list[int]] = {k: [] for k in keys}
    started = time.time()
    with ProcessPoolExecutor(workers) as ex:
        for seated, winners, totals in ex.map(_play, [(keys, s) for s in range(games)], chunksize=8):
            for w in winners:
                wins[seated[w]] += 1 / len(winners)
            for k, t in zip(seated, totals, strict=True):
                scores[k].append(t)
    table = Table(title=f"{games} games · {time.time() - started:.1f}s")
    for col in ("bot", "win share", "mean score"):
        table.add_column(col)
    per_key = {k: keys.count(k) for k in keys}
    for k in dict.fromkeys(keys):
        table.add_row(k, f"{wins[k] / games / per_key[k]:.3f}", f"{sum(scores[k]) / len(scores[k]):.1f}")
    console.print(table)


def _lan_ip() -> str | None:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))  # no packet is sent; picks the outbound interface
            ip = s.getsockname()[0]
        except OSError:
            return None
    return None if ip.startswith("127.") else ip


def _start_tunnel(port: int) -> tuple[subprocess.Popen[str], str]:
    import re
    import shutil

    exe = shutil.which("cloudflared")
    if exe is None:
        raise typer.BadParameter("--tunnel needs cloudflared: `brew install cloudflared`")
    proc = subprocess.Popen(
        [exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.stderr is not None
    pattern = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
    deadline = time.time() + 30
    for line in proc.stderr:
        if match := pattern.search(line):
            return proc, match.group(0)
        if time.time() > deadline:
            break
    proc.terminate()
    raise typer.BadParameter("cloudflared did not report a public URL")


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Interface to bind; 0.0.0.0 lets your LAN join")] = "0.0.0.0",
    port: int = 8000,
    public_url: Annotated[str | None, typer.Option(help="Base URL used in invite links")] = None,
    tunnel: Annotated[bool, typer.Option(help="Open a public cloudflared tunnel and invite through it")] = False,
) -> None:
    """Host the multiplayer web game. Share the table link; friends join from their browser."""
    import uvicorn

    from ttr.bots import REGISTRY
    from ttr.web.server import create_app

    ip = _lan_ip() if host == "0.0.0.0" else None
    lan_url = f"http://{ip}:{port}" if ip else None
    proc = None
    if tunnel:
        proc, public_url = _start_tunnel(port)
    console.print("[bold green]Ticket to Ride: Europe server[/]")
    console.print(f"  local:   http://localhost:{port}")
    if lan_url:
        console.print(f"  network: {lan_url}   (same Wi-Fi / LAN)")
    if public_url:
        console.print(f"  public:  {public_url}")
    elif not lan_url:
        console.print("[dim]  bind --host 0.0.0.0 or use --tunnel to invite people from other machines")
    console.print(f"  bots:    {', '.join(b.label for b in REGISTRY.values())}")
    console.print("[dim]  table activity is logged below (Ctrl+C to stop)\n")
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S"))
    web_log = logging.getLogger("ttr.web")
    web_log.addHandler(handler)
    web_log.setLevel(logging.INFO)
    web_log.propagate = False
    try:
        uvicorn.run(create_app(public_url=public_url, lan_url=lan_url), host=host, port=port, log_level="warning")
    finally:
        if proc is not None:
            proc.terminate()


def main() -> None:
    app()
