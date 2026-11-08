"""Trace the printed board's coastline from the board photo into `land.json` (keys `land` and `lakes`).

The printed map is stylised, so real coastlines never line up with it; the photo is the reference.
Sea is the blue-grey paper, land the cream/grey one. Route spaces, cities and ink are masked out and
filled in from their surroundings before thresholding. Borders still come from `build_land.py`.

    uv run python scripts/build_land.py /path/to/geojson   # borders (and a first coastline)
    uv run python scripts/trace_land.py [--debug shots/mask.png]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

ASSETS = Path(__file__).with_name("assets")
PHOTO = ASSETS / "board_photo.jpg"
FIT = ASSETS / "route_fit.json"
OUT = Path(__file__).resolve().parents[1] / "src/ttr/web/static/land.json"

MAP = (15, 58, 1012, 702)  # photo pixels of the board's map area (board 0..1000 x 0..650)
INSET = (8, 8, 8, 16)  # left, top, right, bottom: the photo's frame bleeds this far into the map rectangle
UP = 4  # supersampling for smooth contours
SEA_T = 8.0  # (blue - red) above this is sea
SEA_ART = [(232, 70, 386, 156), (268, 175, 315, 205)]  # scoring table and biplane drawn in the North Sea
MIN_ISLAND = 40.0  # photo px^2
MIN_LAKE = 45.0
LAKE_BLUE = 6.0  # enclosed water must be clearly blue on average; greyish inland paper is not


def _board(px: float, py: float) -> tuple[float, float]:
    x0, y0, x1, y1 = MAP
    return (px - x0) * 1000 / (x1 - x0), (py - y0) * 650 / (y1 - y0)


def _known_mask(img: np.ndarray) -> np.ndarray:
    """1 where the pixel shows bare paper (not a route, city, label or drawing)."""
    h, w = img.shape[:2]
    unknown = np.zeros((h, w), np.uint8)
    for entry in json.loads(FIT.read_text()):
        for track in entry["tracks"]:
            pts = np.array(track["line"], np.float32).reshape(-1, 1, 2)
            cv2.polylines(unknown, [np.round(pts).astype(np.int32)], False, 255, 17)
    from ttr.game.europe import _CITIES

    for _, _, px, py, _ in _CITIES.values():
        cv2.circle(unknown, (int(px), int(py)), 15, 255, -1)
    lum = img.mean(axis=2)
    chroma = img.max(axis=2) - img.min(axis=2)
    gray_car = (chroma < 16) & (lum < 188)
    ink = ((lum < 125) | (chroma > 55) | gray_car).astype(np.uint8) * 255
    unknown |= cv2.dilate(ink, np.ones((5, 5), np.uint8))
    return (unknown == 0).astype(np.float32)


def _fill(score: np.ndarray, known: np.ndarray) -> np.ndarray:
    """Normalized convolution: unknown pixels take the weighted average of nearby known ones."""
    out = score * known
    for sigma in (2.0, 5.0, 12.0):
        num = cv2.GaussianBlur(out * known, (0, 0), sigma)
        den = cv2.GaussianBlur(known, (0, 0), sigma)
        est = num / np.maximum(den, 1e-6)
        out = np.where(known > 0, out, np.where(den > 0.02, est, out))
        known = np.maximum(known, (den > 0.02).astype(np.float32))
    return out


def _path(contours: list[np.ndarray]) -> str:
    parts = []
    for c in contours:
        c = cv2.approxPolyDP(c, 0.35 * UP, True).reshape(-1, 2) / UP
        if len(c) < 3:
            continue
        pts = [_board(x + 0.5, y + 0.5) for x, y in c]
        parts.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z")
    return "".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", help="write the land mask over the photo here")
    args = ap.parse_args()
    img = cv2.cvtColor(cv2.imread(str(PHOTO)), cv2.COLOR_BGR2RGB).astype(np.float32)
    score = img[..., 2] - img[..., 0] - SEA_T  # > 0: sea
    known = _known_mask(img)
    for x0, y0, x1, y1 in SEA_ART:
        score[y0:y1, x0:x1] = 20.0
        known[y0:y1, x0:x1] = 1.0
    filled = cv2.GaussianBlur(_fill(score, known), (0, 0), 1.6)
    x0, y0, x1, y1 = (MAP[0] + INSET[0], MAP[1] + INSET[1], MAP[2] - INSET[2], MAP[3] - INSET[3])
    pad = 12 + max(INSET)
    crop = filled[y0:y1, x0:x1]
    crop = cv2.copyMakeBorder(crop, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
    big = cv2.resize(crop, None, fx=UP, fy=UP, interpolation=cv2.INTER_CUBIC)
    land = (big < 0).astype(np.uint8)
    k = np.ones((3 * UP, 3 * UP), np.uint8)
    land = cv2.morphologyEx(land, cv2.MORPH_OPEN, k)
    land = cv2.morphologyEx(land, cv2.MORPH_CLOSE, k)

    contours, hier = cv2.findContours(land, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    outer, holes = [], []
    for c, (_, _, _, parent) in zip(contours, hier[0], strict=True):
        area = cv2.contourArea(c) / UP**2
        c = c.astype(np.float32) - pad * UP + np.array([x0 * UP, y0 * UP], np.float32)
        if parent < 0 and area >= MIN_ISLAND:
            outer.append(c)
        elif parent >= 0 and area >= MIN_LAKE:
            inside = np.zeros(score.shape, np.uint8)
            cv2.fillPoly(inside, [np.round(c / UP).astype(np.int32)], 1)
            sel = (inside > 0) & (known > 0)
            if sel.any() and score[sel].mean() > LAKE_BLUE:
                holes.append(c)
    data = json.loads(OUT.read_text()) if OUT.exists() else {"borders": ""}
    data["land"] = _path(outer)
    data["lakes"] = _path(holes)
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    print(f"wrote {OUT} ({len(outer)} land shapes, {len(holes)} lakes, {OUT.stat().st_size // 1024} KB)")

    if args.debug:
        dbg = img.astype(np.uint8).copy()
        for c in outer + holes:
            cv2.polylines(dbg, [np.round(c / UP).astype(np.int32)], True, (255, 0, 0), 1)
        cv2.imwrite(args.debug, cv2.cvtColor(dbg, cv2.COLOR_RGB2BGR))


if __name__ == "__main__":
    main()
