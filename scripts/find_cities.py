"""Locate city dots on the board photo by template matching against known-good cities.

    uv run python scripts/find_cities.py [--radius 18]

Prints a corrected position for every city in europe.py (verify with scripts/city_sheet.py).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

from ttr.game.europe import _CITIES

PHOTO = Path(__file__).with_name("assets") / "board_photo.jpg"
TEMPLATES = ["Brest", "Paris", "Edinburgh", "Barcelona", "Wilno", "Smolensk"]
H = 8  # template half size


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--radius", type=int, default=18)
    args = ap.parse_args()
    img = np.asarray(Image.open(PHOTO).convert("RGB")).astype(float)
    temps = []
    for name in TEMPLATES:
        _, _, px, py, _ = _CITIES[name]
        t = img[int(py) - H : int(py) + H + 1, int(px) - H : int(px) + H + 1]
        temps.append((t - t.mean()) / (t.std() + 1e-6))
    yy, xx = np.mgrid[-H : H + 1, -H : H + 1]
    weight = (np.hypot(xx, yy) <= H)[..., None]
    for name, (_, _, px, py, _) in _CITIES.items():
        best = (-9.0, 0, 0)
        R = args.radius
        for cy in range(int(py) - R, int(py) + R + 1):
            for cx in range(int(px) - R, int(px) + R + 1):
                if not (H <= cy < img.shape[0] - H - 1 and H <= cx < img.shape[1] - H - 1):
                    continue
                w = img[cy - H : cy + H + 1, cx - H : cx + H + 1]
                w = (w - w.mean()) / (w.std() + 1e-6)
                score = max(float((w * t * weight).sum() / weight.sum() / 3) for t in temps)
                if score > best[0]:
                    best = (score, cx, cy)
        moved = abs(best[1] - px) + abs(best[2] - py)
        print(f'    "{name}": ({best[1]}, {best[2]}),  # was {px:.0f},{py:.0f} score {best[0]:.2f} moved {moved:.0f}')


if __name__ == "__main__":
    main()
