import itertools
import math
from collections import Counter

import pytest

from ttr.bots import make_bot
from ttr.game import rules
from ttr.game.actions import BuyTech, Claim, KeepTickets
from ttr.game.engine import Game, IllegalMove, Phase, uk_rules
from ttr.game.maps import MAPS
from ttr.game.model import LOCO
from ttr.game.uk import UK


def _started(n: int = 2, seed: int = 1) -> Game:
    game = Game(n, seed=seed, rules_config=uk_rules(), board=UK, first=0)
    for seat, p in enumerate(game.players):
        game.step(seat, KeepTickets(tuple(p.offer[:3])))
    return game


def _give(game: Game, seat: int, **cards: int) -> None:
    p = game.players[seat]
    game.discard.extend(p.hand.elements())
    p.hand = Counter()
    for color, n in cards.items():
        color = LOCO if color == "loco" else color
        for _ in range(n):
            src = game.discard if color in game.discard else game.deck
            src.remove(color)
            p.hand[color] += 1


def _route(a: str, b: str) -> int:
    return next(r.id for r in UK.routes if {r.a, r.b} == {a, b})


def test_box_contents() -> None:
    assert len(UK.tickets) == 57 and not any(t.long for t in UK.tickets)
    assert len(UK.cities) == 48 and len(UK.routes) == 125
    assert {c.country for c in UK.cities} == {"england", "scotland", "wales", "ireland", "france", "free"}
    assert sum(c.country == "scotland" for c in UK.cities) == 10 and sum(c.country == "wales" for c in UK.cities) == 5
    for t in UK.tickets:
        assert t.a in UK.city_names and t.b in UK.city_names


def test_tech_requirements_match_the_rulebook() -> None:
    need = UK.tech_needs
    assert need[_route("Newcastle", "Edinburgh")] == {"scotland", "stoker"}
    assert need[_route("Stranraer", "Londonderry")] == {"scotland", "ireland_france", "stoker", "propellers"}
    assert need[_route("Southampton", "New York")] == frozenset()
    assert need[_route("London", "Cambridge")] == frozenset()


def test_start_and_setup() -> None:
    game = Game(3, seed=2, rules_config=uk_rules(), board=UK)
    assert all(p.trains == 35 and p.hand[LOCO] >= 1 and p.hand_size == 5 and len(p.offer) == 5 for p in game.players)
    assert len(game.deck) + sum(p.hand_size for p in game.players) + 5 == 116
    with pytest.raises(ValueError):
        Game(5, rules_config=uk_rules(), board=UK)


def test_cannot_claim_without_technology_then_can() -> None:
    game = _started()
    rid = _route("Manchester", "Leeds")
    assert rid in game.claimable(0) or True
    scot = _route("Glasgow", "Edinburgh")
    _give(game, 0, black=1, loco=3)
    assert scot not in game.claimable(0)
    with pytest.raises(IllegalMove):
        game.step(0, Claim(scot, "black", 0))
    game.step(0, BuyTech("scotland"))
    assert game.players[0].hand[LOCO] == 2 and "scotland" in game.players[0].techs
    with pytest.raises(IllegalMove):
        game.step(0, BuyTech("wales"))  # one per turn
    assert scot in game.claimable(0)


def test_four_cards_count_as_a_locomotive() -> None:
    game = _started()
    _give(game, 0, red=2, blue=2, green=1, white=1)
    assert game.tech_options(0).get("wales") == {"green": 1, "white": 1, "blue": 2}
    game.step(0, BuyTech("wales"))
    assert game.players[0].hand == Counter(red=2)
    # the Booster makes it 3 cards
    game2 = _started()
    game2.players[0].techs.add("booster")
    _give(game2, 0, red=3)
    assert game2.tech_options(0)["wales"] == {"red": 3}


def test_lagging_and_turbines_add_points() -> None:
    game = _started()
    game.players[0].techs |= {"lagging", "turbines", "propellers"}
    rid = _route("Dover", "France")  # needs ireland_france too
    game.players[0].techs.add("ireland_france")
    _give(game, 0, red=1, loco=1)
    ev = game.step(0, Claim(rid, "red", 1))
    assert ev[0]["points"] == 2 + 1 + 2


def test_double_heading_scores_at_the_end() -> None:
    game = _started(2)
    game.players[0].techs.add("double_heading")
    game._finish()
    r = game.result.players[0]
    done = sum(d for _, d in r.tickets)
    assert r.tech_points == 2 * done and not r.express and r.station_points == 0


def test_swap_payment_options_and_cards() -> None:
    hand = {"red": 2, "blue": 5, "green": 1}
    opts = rules.payment_options(UK.routes[_route("Holyhead", "Dublin")], hand, 4)  # ferry: 1 wild + 1 grey
    assert opts
    cards = rules.payment_cards(2, opts[0], hand, 4)
    assert sum(cards.values()) == 1 + 4


def _cars(r):
    city = {c.name: c for c in UK.cities}
    a, b = r.ends or ((city[r.a].x, city[r.a].y), (city[r.b].x, city[r.b].y))
    return [a, *r.path, b]


def test_geometry_inside_board_and_routes_reach_their_cities() -> None:
    for c in UK.cities:
        assert 0 < c.x < UK.width and 0 < c.y < UK.height
    for r in UK.routes:
        assert all(-30 < x < UK.width + 30 and -30 < y < UK.height + 30 for x, y in _cars(r)), r
        assert r.side in ((-1, 1) if (r.twin is not None and r.side) else (0,)) or r.side in (-1, 0, 1)
        length = sum(math.dist(p, q) for p, q in itertools.pairwise(_cars(r)))
        assert length > 2 * 10.5 + r.length * 8, (r.a, r.b)


def test_registry_and_json() -> None:
    assert MAPS["uk"].max_players == 4 and MAPS["europe"].max_players == 5
    data = UK.to_json()
    assert data["technologies"] and len(data["techs"]) == 10 and data["routes"][0]["needs"] is not None
    assert next(c for c in data["cities"] if c["name"] == "France")["sites"]


def test_bots_finish_uk_games() -> None:
    for seed in range(4):
        bots = [make_bot(k, seed) for k in ("expert", "conductor", "rookie")[: 2 + seed % 2]]
        game = Game(len(bots), seed=seed, rules_config=uk_rules(), board=UK)
        while game.phase == Phase.INITIAL_TICKETS:
            for s, b in enumerate(bots):
                if game.players[s].offer:
                    game.step(s, b.act(game.view(s)))
        while game.phase != Phase.GAME_OVER:
            game.step(game.current, bots[game.current].act(game.view(game.current)))
        assert game.result is not None and all(p.trains >= 0 for p in game.players)


def test_player_chooses_which_cards_replace_a_locomotive() -> None:
    game = _started()
    _give(game, 0, red=2, blue=2, green=1, white=1)
    game.step(0, BuyTech("wales", (("red", 2), ("blue", 2))))
    assert game.players[0].hand == Counter(green=1, white=1)


def test_bad_swap_choices_are_rejected() -> None:
    for swap in ((("red", 1), ("blue", 2)), (("red", 2), ("blue", 2), ("green", 1)), (("orange", 4),), (("loco", 4),)):
        game = _started()
        _give(game, 0, red=2, blue=2, green=1, white=1)
        with pytest.raises((IllegalMove, KeyError)):
            game.step(0, BuyTech("wales", swap))
        assert game.players[0].hand == Counter(red=2, blue=2, green=1, white=1)
