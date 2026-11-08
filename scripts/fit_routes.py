"""Fit every route's printed shape on the board photo and write src/ttr/game/europe_paths.py.

    uv run python scripts/fit_routes.py [--only A-B,C-D] [--keep]

Each connection becomes a cubic Bézier between its two cities (photo pixels -> board units later).
The control points are searched so the curve runs over photo pixels of the route's colour; double routes
fit both tracks at once and record which side each colour is on. Check the result with
`uv run python scripts/overlay.py shots/ov.png --tiles --routes`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from ttr.game.europe import _CITIES, _ROUTES

HERE = Path(__file__).parent
PHOTO = HERE / "assets" / "board_photo.jpg"
FIT_JSON = HERE / "assets" / "route_fit.json"
OUT_PY = HERE.parent / "src" / "ttr" / "game" / "europe_paths.py"

REF = {
    "black": (56, 79, 82),
    "gray": (160, 162, 162),
    "blue": (30, 165, 220),
    "yellow": (225, 205, 10),
    "purple": (170, 130, 175),
    "red": (200, 60, 50),
    "orange": (225, 145, 60),
    "green": (160, 205, 90),
    "white": (222, 222, 230),
    "_land": (222, 207, 190),
    "_land2": (201, 203, 200),
    "_land3": (205, 185, 150),
    "_sea": (188, 196, 206),
    "_sea2": (170, 185, 195),
    "_ink": (110, 80, 60),
}
NAMES = list(REF)
CITY_R = 11.0  # photo px kept free around a city centre
TRACK = 5.2  # half distance between double tracks (photo px)
SLOT = 33.5  # photo px per car incl. gap, measured on straight routes
# Car centres read off the photo (from city a to city b) for routes where the search latches onto a
# neighbouring route of the same colour; the curve is least-squares fitted through them.
MANUAL = {
    ("Stockholm", "Petrograd"): [
        *[(600, 100), (627, 97), (665, 86), (700, 85)],
        *[(737, 85), (774, 85), (811, 85), (845, 90)],
    ],
    ("Marseille", "Roma"): [(384, 511), (412, 490), (437, 502), (460, 531)],
    ("Palermo", "Roma"): [(522, 657), (539, 620), (520, 593), (500, 562)],
    ("Brindisi", "Palermo"): [(568, 600), (562, 632), (537, 662)],
    ("Athina", "Brindisi"): [(657, 657), (622, 653), (595, 627), (580, 595)],
    # Both ferries leave Sevastopol as two parallel vertical cars, then split without crossing.
    ("Sevastopol", "Constantinople"): [(888, 517), (878, 552), (853, 564), (828, 580)],
    ("Sevastopol", "Erzurum"): [(902, 517), (904, 553), (918, 588), (945, 612)],
}


def car_centres(A, B, ctrl, length) -> np.ndarray:
    """Car centres as the board lays them out: equal slots along the curve between the city discs."""
    pts, s = sample(A, ctrl[:2], ctrl[2:], B)
    slot = (s[-1] - 2 * CITY_R) / length
    return along(pts, s, CITY_R + slot * (np.arange(length) + 0.5))[0]


def fit_through(A: np.ndarray, B: np.ndarray, cars: list[tuple[float, float]]) -> tuple[np.ndarray, float]:
    """Cubic control points (x1, y1, x2, y2) placing the route's cars on the given centres; and the worst miss."""
    target = np.array(cars, float)
    pts = np.array([A, *cars, B], float)
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
    t = d / d[-1]
    b0, b1, b2, b3 = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t**2, t**3
    rhs = pts - np.outer(b0, A) - np.outer(b3, B)
    sol, *_ = np.linalg.lstsq(np.c_[b1, b2], rhs, rcond=None)
    ctrl = sol.reshape(-1)

    def err(c):
        return float(((car_centres(A, B, c, len(target)) - target) ** 2).sum())

    best = err(ctrl)
    rng = np.random.default_rng(0)
    step = np.linalg.norm(B - A) * 0.1
    for it in range(4000):
        cand = ctrl + rng.normal(0, step, 4)
        e = err(cand)
        if e < best:
            best, ctrl = e, cand
        if it % 400 == 399:
            step *= 0.6
    miss = np.linalg.norm(car_centres(A, B, ctrl, len(target)) - target, axis=1).max()
    return ctrl, float(miss)


def classify(img: np.ndarray) -> np.ndarray:
    ref = np.array([REF[n] for n in NAMES], float)
    lum = img.mean(-1, keepdims=True)
    chroma = img - lum
    rl = ref.mean(-1)
    rc = ref - rl[:, None]
    d = (lum - rl) ** 2 + 2.5 * ((chroma[..., None, :] - rc) ** 2).sum(-1)
    return d.argmin(-1)


def bezier(p0, p1, p2, p3, t):
    u = 1 - t
    return (u**3)[:, None] * p0 + (3 * u * u * t)[:, None] * p1 + (3 * u * t * t)[:, None] * p2 + (t**3)[:, None] * p3


def sample(p0, p1, p2, p3, n=160):
    t = np.linspace(0, 1, n)
    pts = bezier(p0, p1, p2, p3, t)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    return pts, s


def along(pts, s, dist):
    i = np.clip(np.searchsorted(s, dist), 1, len(s) - 1)
    f = ((dist - s[i - 1]) / np.maximum(1e-9, s[i] - s[i - 1]))[:, None]
    p = pts[i - 1] + (pts[i] - pts[i - 1]) * f
    tan = pts[i] - pts[i - 1]
    tan /= np.maximum(1e-9, np.linalg.norm(tan, axis=1))[:, None]
    return p, tan


class Fitter:
    def __init__(self) -> None:
        img = np.asarray(Image.open(PHOTO).convert("RGB")).astype(float)
        k = np.ones(3) / 3
        for axis in (0, 1):
            img = np.apply_along_axis(lambda v: np.convolve(v, k, mode="same"), axis, img)
        self.cls = classify(img)
        self.h, self.w = self.cls.shape

    def score(self, A, B, ctrl, colors, length, offsets):
        p1, p2 = ctrl[:2], ctrl[2:]
        pts, s = sample(A, p1, p2, B)
        total = s[-1]
        inner = total - 2 * CITY_R
        if inner <= 5:
            return -9.0
        d = np.linspace(CITY_R + 3, total - CITY_R - 3, 40)
        p, tan = along(pts, s, d)
        nrm = np.stack([-tan[:, 1], tan[:, 0]], axis=1)
        hit = 0.0
        for color, off in zip(colors, offsets, strict=True):
            q = p + nrm * off
            xi = np.clip(q[:, 0].round().astype(int), 0, self.w - 1)
            yi = np.clip(q[:, 1].round().astype(int), 0, self.h - 1)
            hit += float((self.cls[yi, xi] == NAMES.index(color)).mean())
        hit /= len(colors)
        want = length * SLOT - 2 + 2 * CITY_R
        len_pen = abs(total - want) / want
        straight = np.linalg.norm(B - A)
        wander = max(0.0, total / straight - 1)
        return hit - 0.9 * len_pen - 0.05 * wander

    def fit(self, A, B, colors, length, sides):
        d = B - A
        n = np.array([-d[1], d[0]]) / np.linalg.norm(d)
        L = np.linalg.norm(d)
        best = (-9.0, None, None)
        for offs in sides:
            for k1 in np.linspace(-0.9, 0.9, 31):
                for k2 in np.linspace(-0.9, 0.9, 31):
                    ctrl = np.concatenate([A + d / 3 + n * k1 * L, A + 2 * d / 3 + n * k2 * L])
                    sc = self.score(A, B, ctrl, colors, length, offs)
                    if sc > best[0]:
                        best = (sc, ctrl, offs)
        sc, ctrl, offs = best
        rng = np.random.default_rng(0)
        step = L * 0.08
        for it in range(900):
            cand = ctrl + rng.normal(0, step, 4)
            c = self.score(A, B, cand, colors, length, offs)
            if c > sc:
                sc, ctrl = c, cand
            if it % 150 == 149:
                step *= 0.6
        return sc, ctrl, offs


def connections():
    groups: dict[frozenset, list[tuple[str, str, int, str | None, str, int]]] = {}
    for r in _ROUTES:
        groups.setdefault(frozenset(r[:2]), []).append(r)
    return groups


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    only = {frozenset(p.split("-")) for p in args.only.split(",") if p}
    fitter = Fitter()
    old = {tuple(e["key"]): e for e in json.loads(FIT_JSON.read_text())} if FIT_JSON.exists() else {}
    results = []
    for key, tracks in connections().items():
        a, b = tracks[0][0], tracks[0][1]
        if only and key not in only and (a, b) in old:
            results.append(old[(a, b)])
            continue
        A = np.array(_CITIES[a][2:4], float)
        B = np.array(_CITIES[b][2:4], float)
        colors = [t[3] or "gray" for t in tracks]
        length = tracks[0][2]
        sides = [(0.0,)] if len(tracks) == 1 else [(-TRACK, TRACK), (TRACK, -TRACK)]
        if (a, b) in MANUAL:
            (ctrl, miss), offs = fit_through(A, B, MANUAL[(a, b)]), sides[0]
            sc = fitter.score(A, B, ctrl, colors, length, offs)
            print(f"{a:>14} - {b:<14} manual, worst car off by {miss:.1f} px")
        else:
            sc, ctrl, offs = fitter.fit(A, B, colors, length, sides)
        pts, s = sample(A, ctrl[:2], ctrl[2:], B)
        entry = {"key": [a, b], "score": round(sc, 3), "ctrl": [round(float(v), 1) for v in ctrl], "tracks": []}
        for color, off in zip(colors, offs, strict=True):
            d = np.linspace(0, s[-1], 30)
            p, tan = along(pts, s, d)
            q = p + np.stack([-tan[:, 1], tan[:, 0]], axis=1) * off
            slot = (s[-1] - 2 * CITY_R) / length
            cd = CITY_R + slot * (np.arange(length) + 0.5)
            cp, ct = along(pts, s, cd)
            cq = cp + np.stack([-ct[:, 1], ct[:, 0]], axis=1) * off
            entry["tracks"].append(
                {
                    "color": color,
                    "side": 1 if off > 0 else (-1 if off < 0 else 0),
                    "line": q.round(1).tolist(),
                    "cars": cq.round(1).tolist(),
                }
            )
        print(f"{a:>14} - {b:<14} score {sc:+.2f}")
        results.append(entry)
    FIT_JSON.write_text(json.dumps(results))
    write_module(results)


def write_module(results) -> None:
    lines = [
        '"""Route shapes traced from the board photo by scripts/fit_routes.py (generated — do not edit by hand)."""',
        "",
        "# (city a, city b): (cubic Bézier control points x1, y1, x2, y2 in photo pixels, side of each track",
        "# in _ROUTES order: +1 / -1 for double routes, 0 for single ones).",
        "PATHS: dict[tuple[str, str], tuple[tuple[float, float, float, float], tuple[int, ...]]] = {",
    ]
    for e in results:
        a, b = e["key"]
        c = ", ".join(f"{v:.1f}" for v in e["ctrl"])
        sides = ", ".join(str(t["side"]) for t in e["tracks"])
        lines.append(f'    ("{a}", "{b}"): (({c}), ({sides},)),')
    lines.append("}")
    OUT_PY.write_text("\n".join(lines) + "\n")
    print(OUT_PY)


if __name__ == "__main__":
    main()
