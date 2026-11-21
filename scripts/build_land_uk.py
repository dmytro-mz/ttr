"""Build `src/ttr/web/static/land-uk.json` (coastline, country tints and borders of the UK map).

Real coastlines from Natural Earth 1:10m map units, bent onto the board: a smoothed thin-plate spline fitted
on the cities' (lon, lat) -> board (x, y) pulls Britain and Ireland to where the printed board puts them.

    curl -LO https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_0_map_units.geojson
    uv run python scripts/build_land_uk.py ne_10m_admin_0_map_units.geojson
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

from ttr.game.uk_data import CITY_POS

OUT = Path(__file__).resolve().parents[1] / "src/ttr/web/static/land-uk.json"
WINDOW = (-11.5, 47.0, 8.0, 58.7)  # lon0, lat0, lon1, lat1 kept from the source data
SMOOTH = 3.0
MIN_STEP = 1.4

# name: (lat, lon). Only used to bend the coastline onto the board.
GEO: dict[str, tuple[float, float]] = {
    "Stornoway": (58.21, -6.39),
    "Wick": (58.44, -3.09),
    "Ullapool": (57.90, -5.16),
    "Inverness": (57.48, -4.22),
    "Fort William": (56.82, -5.11),
    "Aberdeen": (57.15, -2.09),
    "Dundee": (56.46, -2.97),
    "Glasgow": (55.86, -4.25),
    "Edinburgh": (55.95, -3.19),
    "Stranraer": (54.90, -5.03),
    "Londonderry": (54.99, -7.31),
    "Sligo": (54.27, -8.47),
    "Galway": (53.27, -9.05),
    "Tullamore": (53.27, -7.49),
    "Limerick": (52.66, -8.63),
    "Cork": (51.90, -8.47),
    "Dublin": (53.35, -6.26),
    "Rosslare": (52.25, -6.34),
    "Dundalk": (54.00, -6.40),
    "Belfast": (54.60, -5.93),
    "Holyhead": (53.31, -4.63),
    "Aberystwyth": (52.41, -4.08),
    "Carmarthen": (51.86, -4.31),
    "Cardiff": (51.48, -3.18),
    "Llandrindod Wells": (52.24, -3.38),
    "Penzance": (50.12, -5.54),
    "Plymouth": (50.38, -4.14),
    "Bristol": (51.45, -2.59),
    "Southampton": (50.90, -1.40),
    "Reading": (51.45, -0.97),
    "Brighton": (50.82, -0.14),
    "Dover": (51.13, 1.31),
    "London": (51.51, -0.13),
    "Ipswich": (52.06, 1.15),
    "Northampton": (52.24, -0.90),
    "Cambridge": (52.21, 0.12),
    "Norwich": (52.63, 1.30),
    "Birmingham": (52.49, -1.89),
    "Nottingham": (52.95, -1.15),
    "Manchester": (53.48, -2.24),
    "Hull": (53.74, -0.33),
    "Leeds": (53.80, -1.55),
    "Liverpool": (53.41, -2.99),
    "Barrow": (54.11, -3.23),
    "Carlisle": (54.89, -2.94),
    "Newcastle": (54.98, -1.61),
}
# More anchors: (lat, lon, board x, board y). France's two landings, and the coasts opposite them.
ANCHORS = [
    (49.65, -1.62, 298, 866),  # Cotentin
    (50.96, 1.85, 569, 834),  # Calais
    (53.0, -10.2, 12, 360),  # Atlantic coast of Ireland
    (51.5, -9.8, 10, 510),
]

TINT = {  # fill for each country, over the parchment
    "england": "rgba(246,243,236,0.85)",
    "scotland": "rgba(168,196,178,0.6)",
    "wales": "rgba(232,196,150,0.8)",
    "ireland": "rgba(196,214,128,0.5)",
    "france": "rgba(200,214,170,0.6)",
}
UNIT = {
    "England": "england",
    "Scotland": "scotland",
    "Wales": "wales",
    "N. Ireland": "ireland",
    "Ireland": "ireland",
    "France": "france",
}


def _xy(lat: float, lon: float) -> tuple[float, float]:
    return lon * math.cos(math.radians(54)), lat


def _fit() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    src, dst = [], []
    for name, (lat, lon) in GEO.items():
        src.append(_xy(lat, lon))
        dst.append(CITY_POS[name])
    for lat, lon, x, y in ANCHORS:
        src.append(_xy(lat, lon))
        dst.append((x, y))
    p, v = np.array(src), np.array(dst, float)
    n = len(p)
    d = np.linalg.norm(p[:, None] - p[None], axis=2)
    k = np.where(d > 0, d**2 * np.log(d + 1e-12), 0.0) + SMOOTH * np.eye(n)
    poly = np.hstack([np.ones((n, 1)), p])
    a = np.zeros((n + 3, n + 3))
    a[:n, :n], a[:n, n:], a[n:, :n] = k, poly, poly.T
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
    if geom["type"] == "Polygon":
        return [geom["coordinates"][0]]
    return [poly[0] for poly in geom["coordinates"]]


def _ring_path(ring: list[list[float]], fit: tuple[np.ndarray, np.ndarray, np.ndarray]) -> str:
    lon0, lat0, lon1, lat1 = WINDOW
    pts = [(min(max(lon, lon0), lon1), min(max(lat, lat0), lat1)) for lon, lat in ring]
    xy = _warp(np.array([_xy(lat, lon) for lon, lat in pts]), fit)
    kept = [xy[0]]
    for q in xy[1:]:
        if np.hypot(*(q - kept[-1])) >= MIN_STEP:
            kept.append(q)
    xs, ys = [q[0] for q in kept], [q[1] for q in kept]
    if len(kept) < 3 or max(xs) < -60 or min(xs) > 660 or max(ys) < -60 or min(ys) > 960:
        return ""
    area = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(kept, kept[1:] + kept[:1], strict=True))) / 2
    if area < 14:  # specks
        return ""
    return "M" + "L".join(f"{q[0]:.1f},{q[1]:.1f}" for q in kept) + "Z"


def main(src: Path) -> None:
    fit = _fit()
    features = json.loads(src.read_text())["features"]
    land, borders = [], []
    by_country: dict[str, list[str]] = {}
    for f in features:
        country = UNIT.get(f["properties"].get("NAME"))
        if country is None or f["properties"].get("ADM0_A3") not in ("GBR", "IRL", "FRA"):
            continue
        paths = [p for p in (_ring_path(r, fit) for r in _rings(f["geometry"])) if p]
        land += paths
        borders += paths
        by_country.setdefault(country, []).extend(paths)
    data = {
        "land": "".join(land),
        "lakes": "",
        "borders": "".join(borders),
        "regions": [{"fill": TINT[c], "d": "".join(p)} for c, p in by_country.items()],
    }
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB, {len(land)} shapes)")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
