"""Draw the map data (cities, fitted route curves) over the board photo to check it.

uv run python scripts/overlay.py OUT.png [--region X Y W H] [--scale 2] [--routes] [--land]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

from ttr.game.europe import _CITIES

PHOTO = Path(__file__).with_name("assets") / "board_photo.jpg"
FIT = Path(__file__).with_name("assets") / "route_fit.json"
LAND = Path(__file__).resolve().parents[1] / "src/ttr/web/static/land.json"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--region", type=int, nargs=4, default=[0, 0, 1024, 768])
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--routes", action="store_true")
    ap.add_argument("--land", action="store_true", help="draw coastlines (red) and borders (blue) from land.json")
    ap.add_argument("--tiles", action="store_true", help="write OUT_a..f.png covering the board in 6 tiles")
    args = ap.parse_args()
    if args.tiles:
        base = args.out.removesuffix(".png")
        for i, (x, y) in enumerate([(0, 30), (330, 30), (660, 30), (0, 370), (330, 370), (660, 370)]):
            render(f"{base}_{'abcdef'[i]}.png", (x, y, 364, 370), args.scale, args.routes, args.land)
    else:
        render(args.out, tuple(args.region), args.scale, args.routes, args.land)


def render(out: str, region: tuple[int, int, int, int], k: int, routes: bool, land: bool = False) -> None:
    x0, y0, w, h = region
    im = Image.open(PHOTO).convert("RGB").crop((x0, y0, x0 + w, y0 + h)).resize((w * k, h * k), Image.LANCZOS)
    d = ImageDraw.Draw(im)

    def P(x: float, y: float) -> tuple[float, float]:
        return ((x - x0) * k, (y - y0) * k)

    if land:
        data = json.loads(LAND.read_text())
        for key, colour in (("land", (255, 40, 40)), ("borders", (40, 40, 255))):
            for part in data[key].split("M")[1:]:
                pts = [tuple(map(float, xy.split(","))) for xy in part.rstrip("Z").split("L")]
                pts = [P(x * 997 / 1000 + 15, y * 644 / 650 + 58) for x, y in pts]
                if len(pts) > 1:
                    d.line(pts, fill=colour, width=1)
    if routes and FIT.exists():
        for entry in json.loads(FIT.read_text()):
            for track in entry["tracks"]:
                pts = [P(*p) for p in track["line"]]
                d.line(pts, fill=(255, 0, 255), width=2)
                for c in track["cars"]:
                    cx, cy = P(*c)
                    d.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], outline=(0, 255, 255), width=2)
    for name, (_, _, px, py, _) in _CITIES.items():
        X, Y = P(px, py)
        d.line([(X - 8, Y), (X + 8, Y)], fill=(255, 0, 255), width=2)
        d.line([(X, Y - 8), (X, Y + 8)], fill=(255, 0, 255), width=2)
        d.text((X + 6, Y + 4), name, fill=(255, 0, 255))
    im.save(out)
    print(out)


if __name__ == "__main__":
    main()
