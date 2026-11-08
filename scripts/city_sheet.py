"""Contact sheet: a zoomed crop around every city of europe.py on the board photo, with a 10 px grid.

uv run python scripts/city_sheet.py OUT.png [--only A,B,...]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

from ttr.game.europe import _CITIES

PHOTO = Path(__file__).with_name("assets") / "board_photo.jpg"
HALF = 30
K = 4
COLS = 6


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    photo = Image.open(PHOTO).convert("RGB")
    names = [n for n in _CITIES if not args.only or n in args.only.split(",")]
    cell = 2 * HALF * K
    rows = (len(names) + COLS - 1) // COLS
    sheet = Image.new("RGB", (COLS * cell, rows * (cell + 14)), "white")
    for i, name in enumerate(names):
        _, _, px, py, _ = _CITIES[name]
        cx, cy = round(px), round(py)
        crop = photo.crop((cx - HALF, cy - HALF, cx + HALF, cy + HALF)).resize((cell, cell), Image.LANCZOS)
        d = ImageDraw.Draw(crop)
        for v in range((cx - HALF) // 10 * 10 + 10, cx + HALF, 10):
            X = (v - cx + HALF) * K
            d.line([(X, 0), (X, cell)], fill=(0, 200, 255))
            d.text((X + 1, 1), str(v), fill=(255, 0, 255))
        for v in range((cy - HALF) // 10 * 10 + 10, cy + HALF, 10):
            Y = (v - cy + HALF) * K
            d.line([(0, Y), (cell, Y)], fill=(0, 200, 255))
            d.text((1, Y + 1), str(v), fill=(255, 0, 255))
        c = HALF * K
        d.ellipse([c - 4, c - 4, c + 4, c + 4], outline=(255, 0, 255), width=2)
        x, y = (i % COLS) * cell, (i // COLS) * (cell + 14)
        sheet.paste(crop, (x, y + 14))
        ImageDraw.Draw(sheet).text((x + 4, y + 1), f"{name} ({cx},{cy})", fill=(0, 0, 0))
    sheet.save(args.out)
    print(args.out)


if __name__ == "__main__":
    main()
