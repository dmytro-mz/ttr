"""Heuristic planner bot.

Each turn it plans cheapest paths for its open tickets over connections that are still free
(own routes cost nothing, routes shared with an earlier ticket's plan cost nothing when
`overlap` is on, blocked ones can be bridged by a station), then:

1. last turn of the game: the single move worth the most points;
2. claim the longest planned route it can pay for (or build a station that completes a ticket);
3. nothing left to plan: draw more tickets while trains are plentiful, else dump trains into
   the longest affordable routes;
4. otherwise draw the train cards the plan is short of.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations

from ttr.bots.base import Bot
from ttr.bots.graph import Conn, connections, shortest_path
from ttr.game import rules
from ttr.game.actions import (
    Action,
    BuildStation,
    Claim,
    DrawCard,
    DrawTickets,
    KeepTickets,
    Pass,
    TunnelDecline,
    TunnelPay,
)
from ttr.game.engine import Phase, View
from ttr.game.model import COLORS, LOCO, Route, Ticket


@dataclass(frozen=True)
class PlannerConfig:
    overlap: bool = True  # plan tickets together so they share routes
    more_tickets: bool = True
    ticket_min_trains: int = 22  # draw new tickets only with at least this many trains
    ticket_budget: float = 0.5  # share of remaining trains new tickets may plan to use
    initial_budget: int = 30
    use_stations: bool = True
    loco_greed: float = 0.1  # how readily it takes a face-up locomotive (counts as both draws)
    endgame: bool = True  # last-turn optimisation and train dumping
    min_dump_length: int = 3  # when dumping trains, ignore routes shorter than this
    station_penalty: float = 14.0  # path cost of bridging a blocked connection with a station
    long_bias: float = 0.15  # prefer paths over long routes (more points per train)
    pressure_trains: int = 0  # when anyone is down to this many trains, cash in cards for points


@dataclass
class Plan:
    conns: list[Conn] = field(default_factory=list)  # to claim, in planning order
    trains: int = 0
    feasible: list[Ticket] = field(default_factory=list)
    failed: list[Ticket] = field(default_factory=list)
    bridges: list[Conn] = field(default_factory=list)  # blocked connections a station must bridge


class PlannerBot(Bot):
    def __init__(self, seed: int | None = None, config: PlannerConfig | None = None) -> None:
        super().__init__(seed)
        self.config = config or PlannerConfig()

    # ------------------------------------------------------------------ entry point
    def act(self, view: View) -> Action:
        match view.phase:
            case Phase.INITIAL_TICKETS | Phase.CHOOSE_TICKETS:
                return self.choose_tickets(view)
            case Phase.TUNNEL:
                return self.tunnel(view)
            case Phase.SECOND_CARD:
                return self.draw(view, second=True)
        return self.turn(view)

    # ------------------------------------------------------------------ planning
    def _conn_state(self, view: View, key: Conn) -> tuple[str, Route | None]:
        """("mine" | "open" | "blocked", cheapest open track)."""
        ids = connections(view.board)[key]
        if any(view.owners.get(r) == view.seat for r in ids):
            return "mine", None
        open_tracks = [
            view.board.routes[r]
            for r in ids
            if rules.route_open(view.board.routes[r], view.owners, view.seat, view.n, view.rules.double_min_players)
        ]
        if not open_tracks:
            return "blocked", None
        return "open", min(open_tracks, key=lambda r: self._effort(r, view.hand))

    def _effort(self, r: Route, hand: dict[str, int]) -> float:
        cost = r.length + 0.6 * r.ferry + (0.7 if r.tunnel else 0.0) - self.config.long_bias * (r.points - r.length)
        if r.color is not None:
            cost += 0.15 * max(0, r.length - hand.get(r.color, 0))
        return cost

    def plan(self, view: View, tickets: list[Ticket]) -> Plan:
        plan = Plan()
        planned: set[Conn] = set()
        stations_left = view.stations_left[view.seat] if self.config.use_stations else 0
        my_station_cities = {c for c, s in view.station_at.items() if s == view.seat}
        cache: dict[Conn, tuple[str, Route | None]] = {}

        def state(key: Conn) -> tuple[str, Route | None]:
            if key not in cache:
                cache[key] = self._conn_state(view, key)
            return cache[key]

        for t in sorted(tickets, key=lambda t: -t.value):

            def cost(key: Conn) -> float | None:
                kind, track = state(key)
                if kind == "mine":
                    return 0.0
                if key in planned:
                    return 0.0 if self.config.overlap else 0.5 * float(track.length if track else 0)
                if kind == "open":
                    assert track is not None
                    return self._effort(track, view.hand)
                if key & my_station_cities:
                    return 0.5
                if len(plan.bridges) < stations_left and not all(c in view.station_at for c in key):
                    return self.config.station_penalty
                return None

            found = shortest_path(view.board, t.a, t.b, cost)
            if found is None:
                plan.failed.append(t)
                continue
            _, path = found
            new = [k for k in path if state(k)[0] == "open" and k not in planned]
            bridges = [k for k in path if state(k)[0] == "blocked" and not (k & my_station_cities)]
            trains = sum(state(k)[1].length for k in new)  # type: ignore[union-attr]
            if plan.trains + trains > view.my_trains or len(plan.bridges) + len(bridges) > stations_left:
                plan.failed.append(t)
                continue
            plan.feasible.append(t)
            plan.trains += trains
            plan.conns.extend(new)
            plan.bridges.extend(k for k in bridges if k not in plan.bridges)
            planned.update(new)
        return plan

    def _open_tickets(self, view: View) -> list[Ticket]:
        tickets = [view.board.tickets[t] for t in view.tickets]
        done, _ = rules.best_station_use(view.board, view.seat, view.owners, view.station_at, tickets)
        return [t for t, d in zip(tickets, done, strict=True) if not d]

    def _ticket_score(self, view: View, tickets: list[Ticket]) -> int:
        done, _ = rules.best_station_use(view.board, view.seat, view.owners, view.station_at, tickets)
        return sum(t.value if d else -t.value for t, d in zip(tickets, done, strict=True))

    # ------------------------------------------------------------------ tickets
    def choose_tickets(self, view: View) -> Action:
        offer = [view.board.tickets[t] for t in view.offer]
        current = self._open_tickets(view)
        base = self.plan(view, current)
        initial = view.phase == Phase.INITIAL_TICKETS
        budget = self.config.initial_budget if initial else int(view.my_trains * self.config.ticket_budget)
        best: tuple[float, tuple[Ticket, ...]] | None = None
        for k in range(view.offer_min, len(offer) + 1):
            for subset in combinations(offer, k):
                plan = self.plan(view, current + list(subset))
                score = 0.0
                for t in subset:
                    score += t.value if t in plan.feasible else -1.2 * t.value
                score -= sum(t.value for t in current if t in plan.failed and t not in base.failed)
                extra = plan.trains - base.trains
                score -= 0.35 * extra + 3.0 * len(plan.bridges)
                if plan.trains > budget:
                    score -= 2.0 * (plan.trains - budget)
                if best is None or score > best[0]:
                    best = (score, subset)
        assert best is not None
        return KeepTickets(tuple(t.id for t in best[1]))

    # ------------------------------------------------------------------ main turn
    def turn(self, view: View) -> Action:
        if view.final_turns is not None and self.config.endgame:
            last = self.last_turn(view)
            if last is not None:
                return last
        open_tickets = self._open_tickets(view)
        plan = self.plan(view, open_tickets)
        claim = self.claim_from_plan(view, plan)
        if claim is not None:
            return claim
        station = self.station_move(view, open_tickets)
        if station is not None:
            return station
        if self.config.endgame and min(view.trains) <= self.config.pressure_trains:
            dump = self.dump_trains(view, any_length=True, reserve=plan.trains)
            if dump is not None:
                return dump
        if not plan.conns and not plan.bridges:
            if (
                self.config.more_tickets
                and view.tickets_left
                and view.final_turns is None
                and view.my_trains >= self.config.ticket_min_trains
                and min(view.trains) > 12
            ):
                return DrawTickets()
            dump = self.dump_trains(view)
            if dump is not None:
                return dump
        if view.can_blind or any(view.face_up_ok):
            return self.draw(view, second=False, plan=plan)
        if view.claimable:
            rid, options = max(view.claimable.items(), key=lambda kv: view.board.routes[kv[0]].length)
            color, locos = options[0]
            return Claim(rid, color, locos)
        if view.tickets_left:
            return DrawTickets()
        if view.station_payments:
            free = [c.name for c in view.board.cities if c.name not in view.station_at]
            color, locos = view.station_payments[0]
            return BuildStation(free[0], color, locos)
        return Pass()

    def _best_payment(self, view: View, route: Route, reserve: Counter[str]) -> rules.Payment | None:
        options = view.claimable.get(route.id)
        if not options:
            return None

        def cost(p: rules.Payment) -> float:
            color, locos = p
            spare = view.hand.get(color or LOCO, 0) - reserve.get(color or LOCO, 0)
            return locos * 2.5 + (0 if color is None else -0.1 * spare)

        return min(options, key=cost)

    def _demand(self, view: View, plan: Plan, skip: Conn | None = None) -> Counter[str]:
        demand: Counter[str] = Counter()
        for key in plan.conns:
            if key == skip:
                continue
            _, track = self._conn_state(view, key)
            if track is None:
                continue
            if track.color is not None:
                demand[track.color] += track.length - track.ferry
            demand[LOCO] += track.ferry
        return demand

    def claim_from_plan(self, view: View, plan: Plan) -> Action | None:
        candidates: list[tuple[float, Route, rules.Payment]] = []
        for key in plan.conns:
            ids = connections(view.board)[key]
            for rid in ids:
                if rid not in view.claimable:
                    continue
                r = view.board.routes[rid]
                payment = self._best_payment(view, r, self._demand(view, plan, skip=key))
                if payment is None:
                    continue
                prio = r.length + (1.5 if r.length >= 4 else 0) - 0.6 * payment[1] - (0.5 if r.tunnel else 0)
                candidates.append((prio, r, payment))
        if not candidates:
            return None
        _, r, (color, locos) = max(candidates, key=lambda c: c[0])
        return Claim(r.id, color, locos)

    def station_move(self, view: View, open_tickets: list[Ticket]) -> Action | None:
        if not self.config.use_stations or not view.station_payments or not open_tickets:
            return None
        best: tuple[int, str] | None = None
        for city in {c for rid in view.owners for c in (view.board.routes[rid].a, view.board.routes[rid].b)}:
            if city in view.station_at:
                continue
            trial = dict(view.station_at)
            trial[city] = view.seat
            done, _ = rules.best_station_use(view.board, view.seat, view.owners, trial, open_tickets)
            gain = sum(2 * t.value for t, d in zip(open_tickets, done, strict=True) if d)
            if gain and (best is None or gain > best[0]):
                best = (gain, city)
        if best is None or best[0] <= view.rules.station_value * 2:
            return None
        color, locos = min(view.station_payments, key=lambda p: (p[1], -view.hand.get(p[0] or LOCO, 0)))
        return BuildStation(best[1], color, locos)

    def dump_trains(self, view: View, any_length: bool = False, reserve: int = 0) -> Action | None:
        claimable = {
            rid: opts
            for rid, opts in view.claimable.items()
            if view.board.routes[rid].length <= view.my_trains - reserve
        }
        if not claimable:
            return None
        mine = {
            c
            for rid, s in view.owners.items()
            if s == view.seat
            for c in (view.board.routes[rid].a, view.board.routes[rid].b)
        }

        def value(rid: int) -> float:
            r = view.board.routes[rid]
            touches = 1.0 if {r.a, r.b} & mine else 0.0
            locos = claimable[rid][0][1]
            return r.points + touches - 1.5 * locos

        rid = max(claimable, key=value)
        r = view.board.routes[rid]
        short = r.length < self.config.min_dump_length
        if short and not any_length and view.my_trains > 6 and view.final_turns is None:
            return None
        color, locos = claimable[rid][0]
        return Claim(rid, color, locos)

    def last_turn(self, view: View) -> Action | None:
        tickets = [view.board.tickets[t] for t in view.tickets]
        base = self._ticket_score(view, tickets)
        best: tuple[float, Action] | None = None
        for rid, options in view.claimable.items():
            r = view.board.routes[rid]
            owners = dict(view.owners)
            owners[rid] = view.seat
            done, _ = rules.best_station_use(view.board, view.seat, owners, view.station_at, tickets)
            gain = r.points + sum(t.value if d else -t.value for t, d in zip(tickets, done, strict=True)) - base
            if r.tunnel:
                gain *= 0.75
            color, locos = options[0]
            if best is None or gain > best[0]:
                best = (gain, Claim(rid, color, locos))
        if view.station_payments:
            for city in view.board.city_names - set(view.station_at):
                trial = dict(view.station_at)
                trial[city] = view.seat
                done, _ = rules.best_station_use(view.board, view.seat, view.owners, trial, tickets)
                score = sum(t.value if d else -t.value for t, d in zip(tickets, done, strict=True))
                gain = score - base - view.rules.station_value
                if gain > 0 and (best is None or gain > best[0]):
                    color, locos = view.station_payments[0]
                    best = (gain, BuildStation(city, color, locos))
        return best[1] if best is not None and best[0] > 0 else None

    # ------------------------------------------------------------------ cards
    def _card_values(self, view: View, plan: Plan | None) -> dict[str, float]:
        hand = Counter(view.hand)
        values = dict.fromkeys(COLORS, 0.1)
        if plan is None or not plan.conns:
            if hand:
                top = max(COLORS, key=lambda c: hand[c])
                values[top] = 1.0
            return values
        demand = self._demand(view, plan)
        gray = 0
        for key in plan.conns:
            _, track = self._conn_state(view, key)
            if track is not None and track.color is None:
                gray = max(gray, track.length - track.ferry)
        for c in COLORS:
            short = demand[c] - hand[c]
            if short > 0:
                values[c] = 1.0 + 0.25 * min(short, 4)
        if gray:
            for c in COLORS:
                if demand[c] == 0 and hand[c]:
                    values[c] = max(values[c], 0.5 + 0.2 * min(hand[c], gray))
        return values

    def draw(self, view: View, second: bool, plan: Plan | None = None) -> Action:
        if plan is None:
            plan = self.plan(view, self._open_tickets(view))
        values = self._card_values(view, plan)
        choices = [
            (values.get(c, 0.0), i)
            for i, c in enumerate(view.face_up)
            if c is not None and c != LOCO and view.face_up_ok[i]
        ]
        best = max(choices, default=(0.0, -1))
        if best[0] >= 1.0:
            return DrawCard(best[1])
        if not second and LOCO in view.face_up:
            need_locos = self._demand(view, plan)[LOCO] > view.hand.get(LOCO, 0)
            if need_locos or self.rng.random() < self.config.loco_greed * 0.5:
                return DrawCard(view.face_up.index(LOCO))
        if view.can_blind:
            return DrawCard(None)
        if choices:
            return DrawCard(best[1])
        slot = next(i for i, ok in enumerate(view.face_up_ok) if ok)
        return DrawCard(slot)

    def tunnel(self, view: View) -> Action:
        t = view.tunnel
        assert t is not None
        options = rules.tunnel_pay_options(t.extra, t.color, view.hand)
        if not options:
            return TunnelDecline()
        r = view.board.routes[t.route]
        if t.extra >= 3 and r.length <= 2 and view.final_turns is None:
            return TunnelDecline()
        return TunnelPay(min(options))


class RookieBot(Bot):
    """A beginner: random tickets, random affordable routes, mostly blind draws."""

    def act(self, view: View) -> Action:
        rng = self.rng
        if view.phase in (Phase.INITIAL_TICKETS, Phase.CHOOSE_TICKETS):
            k = rng.randint(view.offer_min, len(view.offer))
            return KeepTickets(tuple(rng.sample(view.offer, k)))
        if view.phase == Phase.TUNNEL:
            assert view.tunnel is not None
            options = rules.tunnel_pay_options(view.tunnel.extra, view.tunnel.color, view.hand)
            return TunnelPay(options[0]) if options else TunnelDecline()
        face_up = [i for i, ok in enumerate(view.face_up_ok) if ok]
        if view.phase == Phase.SECOND_CARD:
            if view.can_blind and (not face_up or rng.random() < 0.6):
                return DrawCard(None)
            return DrawCard(rng.choice(face_up))
        if view.claimable and rng.random() < 0.45:
            rid = rng.choice(list(view.claimable))
            color, locos = view.claimable[rid][0]
            return Claim(rid, color, locos)
        if view.can_blind or face_up:
            if view.can_blind and (not face_up or rng.random() < 0.6):
                return DrawCard(None)
            return DrawCard(rng.choice(face_up))
        if view.claimable:
            rid = rng.choice(list(view.claimable))
            color, locos = view.claimable[rid][0]
            return Claim(rid, color, locos)
        if view.tickets_left:
            return DrawTickets()
        return Pass()
