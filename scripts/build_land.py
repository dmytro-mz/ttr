"""Build the country borders in `src/ttr/web/static/land.json` from Natural Earth 1:50m GeoJSON.

Coastlines come from `trace_land.py` (traced from the board photo); this script only writes
`land`/`lakes` when land.json has none yet.

The board is not a true projection: cities sit where the printed board has them. A smoothed
thin-plate spline fitted on the cities' (lon, lat) -> board (x, y) warps the coastline so it
lines up with them.

    curl -LO https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_land.geojson
    (same for ne_50m_lakes and ne_50m_admin_0_boundary_lines_land)
    uv run python scripts/build_land.py /path/to/geojson/dir
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

from ttr.game.europe import EUROPE, _board, city_geo

OUT = Path(__file__).resolve().parents[1] / "src/ttr/web/static/land.json"
WINDOW = (-30.0, 30.0, 60.0, 75.0)  # lon0, lat0, lon1, lat1 kept from the source data
SMOOTH = 4.0
MIN_STEP = 1.6  # board units between kept vertices

# Extra anchors for islands far from any city: (lat, lon, photo x, photo y).
ANCHORS = [
    (53.2, -8.0, 75, 185),  # Ireland
    (42.15, 9.1, 410, 548),  # Corsica
    (40.1, 9.0, 404, 602),  # Sardinia
    (46.15, 33.7, 906, 458),  # Perekop isthmus: keeps Sevastopol on Crimea
    (45.35, 36.5, 948, 474),  # Kerch
    (46.5, 30.7, 846, 446),  # Odessa
]


def _geo_xy(lat: float, lon: float) -> tuple[float, float]:
    return lon * math.cos(math.radians(48)), lat


def _fit() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    geo = city_geo()
    src, dst = [], []
    for c in EUROPE.cities:
        src.append(_geo_xy(*geo[c.name]))
        dst.append((c.x, c.y))
    for lat, lon, px, py in ANCHORS:
        src.append(_geo_xy(lat, lon))
        dst.append(_board(px, py))
    p = np.array(src)
    v = np.array(dst)
    n = len(p)
    d = np.linalg.norm(p[:, None] - p[None], axis=2)
    k = np.where(d > 0, d**2 * np.log(d + 1e-12), 0.0) + SMOOTH * np.eye(n)
    poly = np.hstack([np.ones((n, 1)), p])
    a = np.zeros((n + 3, n + 3))
    a[:n, :n] = k
    a[:n, n:] = poly
    a[n:, :n] = poly.T
    b = np.zeros((n + 3, 2))
    b[:n] = v
    coef = np.linalg.solve(a, b)
    return p, coef[:n], coef[n:]


def _warp(points: np.ndarray, fit: tuple[np.ndarray, np.ndarray, np.ndarray]) -> np.ndarray:
    ctrl, w, aff = fit
    d = np.linalg.norm(points[:, None] - ctrl[None], axis=2)
    u = np.where(d > 0, d**2 * np.log(d + 1e-12), 0.0)
    return u @ w + aff[0] + points @ aff[1:]


def _rings(geom: dict) -> list[list[list[float]]]:
    t, c = geom["type"], geom["coordinates"]
    if t == "Polygon":
        return c
    if t == "MultiPolygon":
        return [ring for poly in c for ring in poly]
    if t == "LineString":
        return [c]
    if t == "MultiLineString":
        return c
    return []


def _path(features: list[dict], fit: tuple[np.ndarray, np.ndarray, np.ndarray], closed: bool) -> str:
    lon0, lat0, lon1, lat1 = WINDOW
    parts = []
    for f in features:
        for ring in _rings(f["geometry"]):
            pts = [(lon, lat) for lon, lat in ring if lon0 <= lon <= lon1 and lat0 <= lat <= lat1]
            if len(pts) < 3:
                continue
            if len(pts) != len(ring) and closed:
                pts = ring  # partially outside: keep the whole ring, the SVG clips it
                pts = [(min(max(lon, lon0), lon1), min(max(lat, lat0), lat1)) for lon, lat in pts]
            xy = _warp(np.array([_geo_xy(lat, lon) for lon, lat in pts]), fit)
            kept = [xy[0]]
            for q in xy[1:]:
                if np.hypot(*(q - kept[-1])) >= MIN_STEP:
                    kept.append(q)
            if len(kept) < (3 if closed else 2):
                continue
            xs, ys = [q[0] for q in kept], [q[1] for q in kept]
            if max(xs) < -80 or min(xs) > EUROPE.width + 80 or max(ys) < -80 or min(ys) > EUROPE.height + 80:
                continue
            cmd = "M" + "L".join(f"{q[0]:.1f},{q[1]:.1f}" for q in kept)
            parts.append(cmd + ("Z" if closed else ""))
    return "".join(parts)


def main(src: Path) -> None:
    fit = _fit()
    load = lambda name: json.loads((src / name).read_text())["features"]  # noqa: E731
    data = json.loads(OUT.read_text()) if OUT.exists() else {}
    if "land" not in data:  # the traced coastline (trace_land.py) is better; this is only a fallback
        data["land"] = _path(load("ne_50m_land.geojson"), fit, closed=True)
        data["lakes"] = _path(load("ne_50m_lakes.geojson"), fit, closed=True)
    data["borders"] = _path(load("ne_50m_admin_0_boundary_lines_land.geojson"), fit, closed=False)
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "."))
