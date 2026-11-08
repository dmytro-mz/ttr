"""Render only the board (no game UI) at high resolution, optionally cropped by CSS zoom.

uv run python scripts/board_shot.py OUT.png [--claimed] [--width 2400]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
from pathlib import Path

import uvicorn
from fastapi.responses import HTMLResponse

from ttr.web.server import create_app

PAGE = """<!doctype html><html><head><link rel="stylesheet" href="/static/style.css">
<style>body{overflow:hidden;background:#222;margin:0} .board-view{width:100vw;height:100vh}</style></head><body>
<div id="app"></div><div id="toasts"></div>
<script type="module">
import { Board } from "/static/board.js";
import { s } from "/static/dom.js";
const get = (url) => fetch(url).then((r) => r.json());
const [map, land] = await Promise.all([get("/api/map"), get("/static/land.json")]);
const sym = s("symbol", {id: "land-sym", viewBox: "0 0 1000 650"}, s("path", {d: land.land}));
document.body.append(s("svg", {width: 0, height: 0}, s("defs", {}, sym)));
const b = new Board(map, land);
document.getElementById("app").append(b.el);
const v = new URLSearchParams(location.search).get("view");
if (v) {
  const [x, y, w] = v.split(",").map(Number);
  b.view = {x, y, w, h: w * b.full.h / b.full.w};
  b.applyView({ commit: true });
}
</script></body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--view", default="", help="x,y,width of the board area to show")
    ap.add_argument("--size", default="2000x1300")
    args = ap.parse_args()
    app = create_app()
    app.add_api_route("/board", lambda: HTMLResponse(PAGE))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8766, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    w, h = args.size.split("x")
    url = f"http://127.0.0.1:8766/board?view={args.view}"
    subprocess.run([sys.executable, str(Path(__file__).with_name("shot.py")), url, args.out, w, h], check=True)


if __name__ == "__main__":
    main()
