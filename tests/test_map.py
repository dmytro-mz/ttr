import heapq
import itertools
import math
from collections import Counter

import pytest

from ttr.game.europe import EUROPE
from ttr.game.model import COLORS, ROUTE_POINTS


def _shortest(a: str, b: str) -> int:
    dist = {a: 0}
    heap = [(0, a)]
    while heap:
        d, city = heapq.heappop(heap)
        if city == b:
            return d
        if d > dist[city]:
            continue
        for rid in EUROPE.routes_at[city]:
            r = EUROPE.routes[rid]
            other = r.b if r.a == city else r.a
            if d + r.length < dist.get(other, 1 << 30):
                dist[other] = d + r.length
                heapq.heappush(heap, (d + r.length, other))
    raise AssertionError(f"{a} and {b} are not connected")


def test_component_counts_match_the_box() -> None:
    assert len(EUROPE.cities) == 47
    assert len(EUROPE.tickets) == 46
    assert sum(t.long for t in EUROPE.tickets) == 6
    assert sum(r.length for r in EUROPE.routes) > 45 * 5  # enough track for five players


def test_route_ids_and_endpoints() -> None:
    names = EUROPE.city_names
    for i, r in enumerate(EUROPE.routes):
        assert r.id == i
        assert r.a in names and r.b in names and r.a != r.b
        assert 1 <= r.length <= 8
        assert r.color is None or r.color in COLORS
        assert 0 <= r.ferry <= r.length
        assert not (r.tunnel and r.ferry), "no route on this map is both a tunnel and a ferry"
        assert r.points == ROUTE_POINTS[r.length]


def test_double_routes_are_symmetric() -> None:
    doubles = 0
    for r in EUROPE.routes:
        if r.twin is None:
            continue
        t = EUROPE.routes[r.twin]
        assert t.twin == r.id
        assert {t.a, t.b} == {r.a, r.b}
        assert t.length == r.length and t.tunnel == r.tunnel and t.ferry == r.ferry
        doubles += 1
    pairs = Counter(frozenset((r.a, r.b)) for r in EUROPE.routes)
    assert max(pairs.values()) == 2
    assert doubles == 2 * sum(1 for n in pairs.values() if n == 2)


@pytest.mark.parametrize(
    ("a", "b", "length", "kind"),
    [
        ("Stockholm", "Petrograd", 8, "tunnel"),
        ("Kobenhavn", "Stockholm", 3, "double"),
        ("Palermo", "Smyrna", 6, "ferry"),
        ("London", "Dieppe", 2, "ferry"),
        ("Edinburgh", "London", 4, "double"),
        ("Zurich", "Venezia", 2, "tunnel"),
    ],
)
def test_landmark_routes(a: str, b: str, length: int, kind: str) -> None:
    routes = [r for r in EUROPE.routes if {r.a, r.b} == {a, b}]
    assert routes and all(r.length == length for r in routes)
    match kind:
        case "tunnel":
            assert all(r.tunnel for r in routes)
        case "ferry":
            assert all(r.ferry for r in routes)
        case "double":
            assert len(routes) == 2


def test_every_ticket_is_reachable_and_fairly_valued() -> None:
    for t in EUROPE.tickets:
        assert t.a in EUROPE.city_names and t.b in EUROPE.city_names
        assert abs(_shortest(t.a, t.b) - t.value) <= 1, t
        assert t.long == (t.value >= 20)


def test_cities_lie_on_the_board() -> None:
    for c in EUROPE.cities:
        assert 0 < c.x < EUROPE.width and 0 < c.y < EUROPE.height
        assert c.label in {"n", "s", "e", "w", "ne", "nw", "se", "sw"}


def test_every_route_has_a_polyline() -> None:
    for r in EUROPE.routes:
        assert r.path is not None and len(r.path) <= 4, r
        assert all(-20 < x < EUROPE.width + 20 and -20 < y < EUROPE.height + 20 for x, y in r.path), r
        double = r.twin is not None or any(t.twin == r.id for t in EUROPE.routes)
        assert r.side in ((-1, 1) if double else (0,)), r


def _car_centres(r) -> list[tuple[float, float]]:
    """Same layout as board.js: cars spread along the polyline, offset sideways for doubles."""
    city = {c.name: c for c in EUROPE.cities}
    pts = [(city[r.a].x, city[r.a].y), *r.path, (city[r.b].x, city[r.b].y)]
    off = r.side * 5.1
    if off:
        dirs = []
        for p, q in itertools.pairwise(pts):
            d = math.dist(p, q) or 1
            dirs.append(((q[0] - p[0]) / d, (q[1] - p[1]) / d))
        shifted = []
        for i, p in enumerate(pts):
            d0, d1 = dirs[max(0, i - 1)], dirs[min(len(dirs) - 1, i)]
            nx, ny = -d0[1] - d1[1], d0[0] + d1[0]
            k = nx * -d0[1] + ny * d0[0]
            nx, ny = (-d0[1], d0[0]) if abs(k) < 0.3 else (nx / k, ny / k)
            shifted.append((p[0] + nx * off, p[1] + ny * off))
        pts = shifted
    s = [0.0]
    for p, q in itertools.pairwise(pts):
        s.append(s[-1] + math.dist(p, q))
    slot = (s[-1] - 2 * 10.5 - (r.length - 1) * 2.6) / r.length + 2.6

    def at(d: float) -> tuple[float, float]:
        j = next((i for i, v in enumerate(s) if v >= d and i > 0), len(s) - 1)
        t = (d - s[j - 1]) / max(1e-6, s[j] - s[j - 1])
        return (pts[j - 1][0] + (pts[j][0] - pts[j - 1][0]) * t, pts[j - 1][1] + (pts[j][1] - pts[j - 1][1]) * t)

    # Close enough to board.js (which keeps bends in the gaps between cars): cars strung along the line.
    out = []
    for k in range(r.length):
        p, q = at(10.5 + k * slot), at(10.5 + k * slot + slot - 2.6)
        out.append(((p[0] + q[0]) / 2, (p[1] + q[1]) / 2))
    return out


def test_routes_do_not_overlap() -> None:
    cars = {r.id: _car_centres(r) for r in EUROPE.routes}
    for i, r in enumerate(EUROPE.routes):
        for q in EUROPE.routes[i + 1 :]:
            if {r.a, r.b} == {q.a, q.b}:
                continue
            gap = min(math.dist(p, o) for p in cars[r.id] for o in cars[q.id])
            assert gap > 7, f"{r.a}-{r.b} overlaps {q.a}-{q.b}"


def _crosses(p, q, r, s) -> bool:
    def side(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    return side(p, q, r) * side(p, q, s) < 0 and side(r, s, p) * side(r, s, q) < 0


def test_routes_do_not_cross() -> None:
    chains = {r.id: list(itertools.pairwise(_car_centres(r))) for r in EUROPE.routes}
    for i, r in enumerate(EUROPE.routes):
        for q in EUROPE.routes[i + 1 :]:
            if {r.a, r.b} == {q.a, q.b}:
                continue
            hit = any(_crosses(*u, *v) for u in chains[r.id] for v in chains[q.id])
            assert not hit, f"{r.a}-{r.b} crosses {q.a}-{q.b}"


def test_json_has_what_the_client_draws() -> None:
    data = EUROPE.to_json()
    assert len(data["cities"]) == 47
    fields = {"id", "a", "b", "length", "color", "tunnel", "ferry", "twin", "points", "path", "side"}
    assert fields <= set(data["routes"][0])
    assert data["colors"] == list(COLORS)
