"""Put regions of the board photo next to the same regions of our rendered board, to spot layout mistakes.

    uv run python scripts/board_shot.py shots/full3x.png --view=-36,-36,1072 --size 3216x2166
    uv run python scripts/compare_board.py shots/full3x.png shots/cmp [--grid 3x3]

Writes OUT_<row><col>.png: photo on the left, our board on the right.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

from ttr.game.europe import _board

PHOTO = Path(__file__).with_name("assets") / "board_photo.jpg"
RENDER_SCALE = 3  # px per board unit in the render, whose top-left is board (-36, -36)
MAP = (15, 58, 1012, 702)  # photo px covered by the board's 0..1000 x 0..650


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("render")
    ap.add_argument("out")
    ap.add_argument("--grid", default="3x3")
    ap.add_argument("--px", type=int, default=760, help="output height of each half")
    args = ap.parse_args()
    cols, rows = map(int, args.grid.split("x"))
    photo = Image.open(PHOTO).convert("RGB")
    render = Image.open(args.render).convert("RGB")
    x0, y0, x1, y1 = MAP
    w, h = (x1 - x0) / cols, (y1 - y0) / rows
    pad = 25
    for r in range(rows):
        for c in range(cols):
            px0, py0 = x0 + c * w - pad, y0 + r * h - pad
            px1, py1 = px0 + w + 2 * pad, py0 + h + 2 * pad
            a = photo.crop((int(px0), int(py0), int(px1), int(py1)))
            bx0, by0 = _board(px0, py0)
            bx1, by1 = _board(px1, py1)
            k = RENDER_SCALE
            b = render.crop((int((bx0 + 36) * k), int((by0 + 36) * k), int((bx1 + 36) * k), int((by1 + 36) * k)))
            hh = args.px
            a = a.resize((int(a.width * hh / a.height), hh), Image.LANCZOS)
            b = b.resize((a.width, hh), Image.LANCZOS)
            sheet = Image.new("RGB", (a.width * 2 + 8, hh), (0, 0, 0))
            sheet.paste(a, (0, 0))
            sheet.paste(b, (a.width + 8, 0))
            label = f"photo x{int(px0)}-{int(px1)} y{int(py0)}-{int(py1)}"
            ImageDraw.Draw(sheet).text((6, 4), label, fill=(255, 0, 255))
            out = f"{args.out}_{r}{c}.png"
            sheet.save(out)
            print(out)


if __name__ == "__main__":
    main()
