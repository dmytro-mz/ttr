"""Zoomed crop of an image with a pixel grid (for measuring things on the board photo).

uv run python scripts/crop.py IMG X Y W H OUT.png [--scale 3] [--grid 20]
"""

from __future__ import annotations

import argparse

from PIL import Image, ImageDraw


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("img")
    ap.add_argument("x", type=int)
    ap.add_argument("y", type=int)
    ap.add_argument("w", type=int)
    ap.add_argument("h", type=int)
    ap.add_argument("out")
    ap.add_argument("--scale", type=int, default=3)
    ap.add_argument("--grid", type=int, default=20)
    args = ap.parse_args()
    im = Image.open(args.img).convert("RGB").crop((args.x, args.y, args.x + args.w, args.y + args.h))
    k = args.scale
    im = im.resize((args.w * k, args.h * k), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    g = args.grid
    for gx in range((args.x // g + 1) * g, args.x + args.w, g):
        X = (gx - args.x) * k
        d.line([(X, 0), (X, im.height)], fill=(255, 0, 255) if gx % 100 == 0 else (0, 200, 255), width=1)
        d.text((X + 2, 2), str(gx), fill=(255, 0, 255))
    for gy in range((args.y // g + 1) * g, args.y + args.h, g):
        Y = (gy - args.y) * k
        d.line([(0, Y), (im.width, Y)], fill=(255, 0, 255) if gy % 100 == 0 else (0, 200, 255), width=1)
        d.text((2, Y + 2), str(gy), fill=(255, 0, 255))
    im.save(args.out)
    print(args.out)


if __name__ == "__main__":
    main()
