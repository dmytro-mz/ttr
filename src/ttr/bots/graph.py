"""Board graph helpers for bots: city connections (a double route is one connection) and paths."""

from __future__ import annotations

import heapq
from collections.abc import Callable
from functools import cache

from ttr.game.model import MapData

Conn = frozenset[str]


@cache
def connections(board: MapData) -> dict[Conn, tuple[int, ...]]:
    out: dict[Conn, list[int]] = {}
    for r in board.routes:
        out.setdefault(frozenset((r.a, r.b)), []).append(r.id)
    return {k: tuple(v) for k, v in out.items()}


@cache
def neighbours(board: MapData) -> dict[str, tuple[tuple[str, Conn], ...]]:
    adj: dict[str, list[tuple[str, Conn]]] = {c.name: [] for c in board.cities}
    for key in connections(board):
        a, b = tuple(key)
        adj[a].append((b, key))
        adj[b].append((a, key))
    return {k: tuple(v) for k, v in adj.items()}


def shortest_path(
    board: MapData, src: str, dst: str, cost: Callable[[Conn], float | None]
) -> tuple[float, list[Conn]] | None:
    """Dijkstra over connections; `cost` returns None for unusable connections."""
    adj = neighbours(board)
    best = {src: 0.0}
    prev: dict[str, tuple[str, Conn]] = {}
    heap = [(0.0, src)]
    while heap:
        d, city = heapq.heappop(heap)
        if city == dst:
            path = []
            while city != src:
                city, key = prev[city]
                path.append(key)
            return d, path[::-1]
        if d > best[city]:
            continue
        for nxt, key in adj[city]:
            c = cost(key)
            if c is None:
                continue
            nd = d + c
            if nd < best.get(nxt, float("inf")):
                best[nxt] = nd
                prev[nxt] = (city, key)
                heapq.heappush(heap, (nd, nxt))
    return None
