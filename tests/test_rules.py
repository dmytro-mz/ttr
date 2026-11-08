from ttr.game import rules
from ttr.game.europe import EUROPE
from ttr.game.model import LOCO, Route, Ticket


def _route(a: str, b: str) -> Route:
    return next(r for r in EUROPE.routes if {r.a, r.b} == {a, b})


def _r(rid: int, a: str, b: str, length: int) -> Route:
    return Route(rid, a, b, length, None, False, 0, None)


def test_coloured_route_payments() -> None:
    r = Route(0, "A", "B", 3, "red", False, 0, None)
    hand = {"red": 2, "blue": 5, LOCO: 2}
    assert rules.payment_options(r, hand) == [("red", 1), ("red", 2)]
    assert rules.payment_options(r, {"blue": 9}) == []


def test_gray_route_any_single_colour_and_all_locos() -> None:
    r = Route(0, "A", "B", 2, None, False, 0, None)
    opts = rules.payment_options(r, {"red": 2, "blue": 1, LOCO: 2})
    assert ("red", 0) in opts and ("blue", 1) in opts and ("red", 1) in opts
    assert opts[-1] == (None, 2)
    assert opts[0][1] == 0  # fewest locomotives first
    assert ("blue", 0) not in opts


def test_ferry_needs_locomotives() -> None:
    r = Route(0, "A", "B", 4, None, False, 2, None)
    assert rules.payment_options(r, {"red": 4, LOCO: 1}) == []
    assert rules.payment_options(r, {"red": 2, LOCO: 2}) == [("red", 2)]
    assert rules.valid_payment(4, None, 2, {"red": 2, LOCO: 2}, ("red", 2))
    assert not rules.valid_payment(4, None, 2, {"red": 4, LOCO: 2}, ("red", 1))


def test_valid_payment_rejects_wrong_colour_and_missing_cards() -> None:
    hand = {"red": 3, LOCO: 1}
    assert rules.valid_payment(3, "red", 0, hand, ("red", 0))
    assert not rules.valid_payment(3, "blue", 0, hand, ("red", 0))
    assert not rules.valid_payment(4, "red", 0, hand, ("red", 0))
    assert not rules.valid_payment(3, "red", 0, hand, ("red", 2))
    assert not rules.valid_payment(3, None, 0, hand, ("mauve", 0))


def test_tunnel_extra_cards() -> None:
    assert rules.tunnel_extra(["red", LOCO, "blue"], "red") == 2
    assert rules.tunnel_extra(["red", "red", "red"], None) == 0  # paid with locomotives only
    assert rules.tunnel_extra([LOCO, "red"], None) == 1
    assert rules.tunnel_pay_options(2, "red", {"red": 1, LOCO: 1}) == [1]
    assert rules.tunnel_pay_options(2, "red", {"red": 2, LOCO: 2}) == [0, 1, 2]
    assert rules.tunnel_pay_options(1, None, {"red": 5}) == []


def test_double_routes_by_player_count() -> None:
    r = _route("Paris", "Bruxelles")
    assert r.twin is not None
    owners = {r.twin: 1}
    assert not rules.route_open(r, owners, seat=0, n_players=3, double_min_players=4)
    assert rules.route_open(r, owners, seat=0, n_players=4, double_min_players=4)
    assert not rules.route_open(r, owners, seat=1, n_players=5, double_min_players=4)  # never both tracks
    assert not rules.route_open(r, {r.id: 2}, seat=0, n_players=5, double_min_players=4)


def test_longest_path_counts_trains_and_allows_revisiting_cities() -> None:
    loop = [_r(0, "A", "B", 2), _r(1, "B", "C", 2), _r(2, "C", "A", 2), _r(3, "A", "D", 5)]
    assert rules.longest_path(loop) == 11
    fork = [_r(0, "A", "B", 3), _r(1, "B", "C", 4), _r(2, "B", "D", 6)]
    assert rules.longest_path(fork) == 10
    assert rules.longest_path([]) == 0


def test_station_borrows_the_best_opponent_route() -> None:
    mine = _route("Paris", "Frankfurt")
    theirs = _route("Frankfurt", "Berlin")
    other = _route("Frankfurt", "Essen")
    owners = {mine.id: 0, theirs.id: 1, other.id: 1}
    ticket = Ticket(0, "Paris", "Berlin", 9, False)
    done, used = rules.best_station_use(EUROPE, 0, owners, {"Frankfurt": 0}, [ticket])
    assert done == [True]
    assert used["Frankfurt"] in {theirs.id, theirs.twin}
    done, _ = rules.best_station_use(EUROPE, 0, owners, {}, [ticket])
    assert done == [False]
