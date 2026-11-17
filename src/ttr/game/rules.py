"""Pure rule helpers shared by the engine, the bots and the web room (no game state here)."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from itertools import product

from ttr.game.model import COLORS, LOCO, MapData, Route, Ticket

Payment = tuple[str | None, int]  # (the one non-locomotive colour used or None, number of locomotives)


def route_open(route: Route, owners: Mapping[int, int], seat: int, n_players: int, double_min_players: int) -> bool:
    """Whether `seat` may claim `route` given who owns what."""
    if route.id in owners:
        return False
    if route.twin is not None and route.twin in owners:
        if owners[route.twin] == seat:
            return False
        if n_players < double_min_players:
            return False
    return True


def payment_options(route: Route, hand: Mapping[str, int], swap_rate: int = 0) -> list[Payment]:
    """Every distinct legal way to pay for `route` from `hand`, fewest locomotives first.

    With `swap_rate` > 0 (UK map) that many cards of any colours also count as one locomotive.
    """
    return _options(route.length, route.color, route.ferry, hand, swap_rate)


def station_options(cost: int, hand: Mapping[str, int]) -> list[Payment]:
    return _options(cost, None, 0, hand)


def wild_cards(
    hand: Mapping[str, int],
    used: Mapping[str, int],
    wilds: int,
    swap_rate: int,
    swap: Mapping[str, int] | None = None,
) -> dict[str, int] | None:
    """Cards that pay `wilds` locomotive spaces on top of `used`: real locomotives first, then groups of
    `swap_rate` other cards. The player may pick those with `swap` (exactly the cards needed, no locomotives);
    otherwise they come from the smallest piles so big sets survive. None if the hand can't do it."""
    left = Counter({c: n - used.get(c, 0) for c, n in hand.items() if n - used.get(c, 0) > 0})
    if any(used.get(c, 0) > hand.get(c, 0) for c in used):
        return None
    real = min(wilds, left[LOCO])
    cards = {LOCO: real} if real else {}
    groups = wilds - real
    if not groups:
        return cards
    if not swap_rate:
        return None
    need = groups * swap_rate
    others = Counter({c: n for c, n in left.items() if c != LOCO})
    if swap:
        if sum(swap.values()) != need or any(c == LOCO or n < 0 or n > others[c] for c, n in swap.items()):
            return None
        return {**cards, **{c: n for c, n in swap.items() if n}}
    if sum(others.values()) < need:
        return None
    for c in sorted(others, key=lambda c: (others[c], c)):
        take = min(others[c], need)
        if take:
            cards[c] = take
            need -= take
        if not need:
            break
    return cards


def _options(
    length: int, color: str | None, min_locos: int, hand: Mapping[str, int], swap_rate: int = 0
) -> list[Payment]:
    out: list[Payment] = []
    seen: set[Payment] = set()
    for c in (color,) if color else COLORS:
        have = hand.get(c, 0)
        for wilds in range(min_locos, length + 1):
            need = length - wilds
            if need and have < need:
                continue
            used = {c: need} if need else {}
            if wild_cards(hand, used, wilds, swap_rate) is None:
                continue
            pay: Payment = (c if need else None, wilds)
            if pay not in seen:
                seen.add(pay)
                out.append(pay)
    out.sort(key=lambda p: (p[1], -hand.get(p[0] or LOCO, 0)))
    return out


def payment_cards(
    length: int,
    payment: Payment,
    hand: Mapping[str, int] | None = None,
    swap_rate: int = 0,
    swap: Mapping[str, int] | None = None,
) -> dict[str, int]:
    """The cards a payment spends. Without `hand` every wild space is a real locomotive."""
    color, wilds = payment
    cards: dict[str, int] = {color: length - wilds} if length - wilds else {}
    if hand is None:
        return {**({LOCO: wilds} if wilds else {}), **cards}
    wild = wild_cards(hand, cards, wilds, swap_rate, swap)
    assert wild is not None
    for c, n in wild.items():
        cards[c] = cards.get(c, 0) + n
    return cards


def valid_payment(
    length: int,
    color: str | None,
    min_locos: int,
    hand: Mapping[str, int],
    payment: Payment,
    swap_rate: int = 0,
    swap: Mapping[str, int] | None = None,
) -> bool:
    pay_color, wilds = payment
    if not isinstance(wilds, int) or wilds < min_locos or wilds > length:
        return False
    rest = length - wilds
    if rest == 0:
        if pay_color is not None and pay_color not in COLORS:
            return False
    elif pay_color not in COLORS or (color is not None and pay_color != color) or hand.get(pay_color, 0) < rest:
        return False
    used = {pay_color: rest} if rest else {}
    return wild_cards(hand, used, wilds, swap_rate, swap) is not None


def tech_cards(
    cost: int, hand: Mapping[str, int], swap_rate: int, swap: Mapping[str, int] | None = None
) -> dict[str, int] | None:
    """Cards spent on a technology costing `cost` locomotives, or None if the hand can't afford it."""
    return wild_cards(hand, {}, cost, swap_rate, swap)


def tunnel_extra(revealed: Sequence[str], color: str | None) -> int:
    """Extra cards a tunnel costs: revealed cards matching the colour played (locomotives always match)."""
    return sum(1 for c in revealed if c == LOCO or (color is not None and c == color))


def tunnel_pay_options(extra: int, color: str | None, hand: Mapping[str, int]) -> list[int]:
    """Locomotive counts the player can use for the extra tunnel cards (rest in `color`)."""
    if color is None:
        return [extra] if hand.get(LOCO, 0) >= extra else []
    return [k for k in range(extra + 1) if hand.get(LOCO, 0) >= k and hand.get(color, 0) >= extra - k]


# ---------------------------------------------------------------------- networks / scoring
class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        p = self.parent.setdefault(x, x)
        if p != x:
            p = self.parent[x] = self.find(p)
        return p

    def union(self, a: str, b: str) -> None:
        self.parent[self.find(a)] = self.find(b)


def connected_pairs(routes: Iterable[Route]) -> _UnionFind:
    uf = _UnionFind()
    for r in routes:
        uf.union(r.a, r.b)
    return uf


def ticket_done(uf: _UnionFind, ticket: Ticket) -> bool:
    return uf.find(ticket.a) == uf.find(ticket.b)


def best_station_use(
    board: MapData,
    seat: int,
    owners: Mapping[int, int],
    stations: Mapping[str, int],
    tickets: Sequence[Ticket],
) -> tuple[list[bool], dict[str, int | None]]:
    """Which tickets are complete when each station borrows its best opponent route.

    Returns per-ticket completion and, per station city, the borrowed route id (or None).
    Each station may use one route of another player that touches its city.
    """
    own = [board.routes[rid] for rid, s in owners.items() if s == seat]
    cities = sorted(c for c, s in stations.items() if s == seat)
    choices: list[list[int | None]] = []
    for city in cities:
        borrowed: list[int | None] = [None]
        seen: set[frozenset[str]] = set()
        for rid in board.routes_at[city]:
            owner = owners.get(rid)
            key = frozenset((board.routes[rid].a, board.routes[rid].b))
            if owner is not None and owner != seat and key not in seen:
                seen.add(key)
                borrowed.append(rid)
        choices.append(borrowed)
    best: tuple[int, list[bool], tuple[int | None, ...]] | None = None
    for combo in product(*choices) if choices else [()]:
        uf = connected_pairs(own + [board.routes[r] for r in combo if r is not None])
        done = [ticket_done(uf, t) for t in tickets]
        score = sum(t.value if d else -t.value for t, d in zip(tickets, done, strict=True))
        if best is None or score > best[0]:
            best = (score, done, combo)
    assert best is not None
    return best[1], dict(zip(cities, best[2], strict=True))


def longest_path(routes: Sequence[Route]) -> int:
    """Length (in trains) of the longest continuous path; routes may not repeat, cities may."""
    adj: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
    for i, r in enumerate(routes):
        adj[r.a].append((r.b, i, r.length))
        adj[r.b].append((r.a, i, r.length))
    best = 0

    def dfs(node: str, used: int, total: int) -> None:
        nonlocal best
        best = max(best, total)
        for nxt, i, length in adj[node]:
            if not used >> i & 1:
                dfs(nxt, used | 1 << i, total + length)

    for city in adj:
        dfs(city, 0, 0)
    return best
