"""Contact sheets: one zoomed photo tile per connection with only its fitted curve and car centres drawn.

uv run python scripts/route_sheet.py shots/rs   ->  shots/rs_0.png, shots/rs_1.png, ...
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

PHOTO = Path(__file__).with_name("assets") / "board_photo.jpg"
FIT = Path(__file__).with_name("assets") / "route_fit.json"
TILE = 330
PAD = 22


def tile(photo: Image.Image, entry: dict) -> Image.Image:
    pts = [p for t in entry["tracks"] for p in t["line"]]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    half = max(max(xs) - min(xs), max(ys) - min(ys)) / 2 + PAD
    x0, y0 = cx - half, cy - half
    k = TILE / (2 * half)
    im = photo.crop((round(x0), round(y0), round(x0 + 2 * half), round(y0 + 2 * half))).resize((TILE, TILE))
    d = ImageDraw.Draw(im)

    def P(x: float, y: float) -> tuple[float, float]:
        return ((x - x0) * k, (y - y0) * k)

    for track in entry["tracks"]:
        d.line([P(*p) for p in track["line"]], fill=(255, 0, 255), width=1)
        for c in track["cars"]:
            X, Y = P(*c)
            d.ellipse([X - 3, Y - 3, X + 3, Y + 3], outline=(0, 255, 255), width=2)
    label = f"{'-'.join(entry['key'])} {'/'.join(t['color'] for t in entry['tracks'])}"
    d.rectangle([0, 0, 8 + 6 * len(label), 14], fill=(0, 0, 0))
    d.text((4, 2), label, fill=(255, 255, 0))
    return im


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--rows", type=int, default=3)
    ap.add_argument("--only", default="", help="comma-separated A-B pairs")
    args = ap.parse_args()
    only = {frozenset(p.split("-")) for p in args.only.split(",") if p}
    photo = Image.open(PHOTO).convert("RGB")
    entries = [e for e in json.loads(FIT.read_text()) if not only or frozenset(e["key"]) in only]
    per = args.cols * args.rows
    for s in range(0, len(entries), per):
        sheet = Image.new("RGB", (args.cols * TILE, args.rows * TILE), (40, 40, 40))
        for i, e in enumerate(entries[s : s + per]):
            sheet.paste(tile(photo, e), ((i % args.cols) * TILE, (i // args.cols) * TILE))
        path = f"{args.out}_{s // per}.png"
        sheet.save(path)
        print(path)


if __name__ == "__main__":
    main()
