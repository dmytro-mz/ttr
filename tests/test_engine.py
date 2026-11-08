from collections import Counter

import pytest

from ttr.bots import make_bot
from ttr.game.actions import BuildStation, Claim, DrawCard, DrawTickets, KeepTickets, Pass, TunnelDecline, TunnelPay
from ttr.game.engine import Game, IllegalMove, Phase, RulesConfig
from ttr.game.model import LOCO
from ttr.runner import play_game

TOTAL_CARDS = 8 * 12 + 14


def _route(game: Game, a: str, b: str, **kw: object) -> int:
    for r in game.board.routes:
        if {r.a, r.b} == {a, b} and all(getattr(r, k) == v for k, v in kw.items()):
            return r.id
    raise KeyError((a, b))


def _started(n: int = 3, seed: int = 1, **rules: object) -> Game:
    """A game past the initial ticket choice, seat 0 to move."""
    game = Game(n, seed=seed, rules_config=RulesConfig(**rules), first=0)  # type: ignore[arg-type]
    for seat, p in enumerate(game.players):
        game.step(seat, KeepTickets(tuple(p.offer)))
    assert game.phase == Phase.TURN and game.current == 0
    return game


def _give(game: Game, seat: int, **cards: int) -> None:
    """Replace a hand, keeping the card total intact by moving cards to/from the discard pile."""
    p = game.players[seat]
    game.discard.extend(p.hand.elements())
    p.hand = Counter()
    for color, n in cards.items():
        color = LOCO if color == "loco" else color
        for _ in range(n):
            source = game.discard if color in game.discard else game.deck
            source.remove(color)
            p.hand[color] += 1


def card_total(game: Game) -> int:
    held = 0
    if game.tunnel is not None:
        r = game.route(game.tunnel.route)
        held = r.length + len(game.tunnel.revealed)
    return (
        len(game.deck)
        + len(game.discard)
        + sum(1 for c in game.face_up if c is not None)
        + sum(p.hand_size for p in game.players)
        + held
    )


# ---------------------------------------------------------------------- setup
def test_setup_deals_hands_tickets_and_market() -> None:
    game = Game(4, seed=7)
    assert game.phase == Phase.INITIAL_TICKETS
    for p in game.players:
        assert p.hand_size == 4 and p.trains == 45
        assert len(p.offer) == 4 and sum(game.ticket(t).long for t in p.offer) == 1
    assert sum(c is not None for c in game.face_up) == 5
    assert sum(c == LOCO for c in game.face_up) <= 2
    assert card_total(game) == TOTAL_CARDS
    assert len(game.ticket_deck) == 40 - 4 * 3


def test_initial_tickets_are_simultaneous_and_need_two() -> None:
    game = Game(2, seed=3, first=1)
    with pytest.raises(IllegalMove):
        game.step(0, DrawCard(None))
    with pytest.raises(IllegalMove):
        game.step(0, KeepTickets((game.players[0].offer[0],)))
    long = next(t for t in game.players[0].offer if game.ticket(t).long)
    short = [t for t in game.players[0].offer if not game.ticket(t).long]
    left = len(game.ticket_deck)
    game.step(0, KeepTickets((short[0], short[1])))
    assert game.phase == Phase.INITIAL_TICKETS
    assert len(game.ticket_deck) == left + 1  # returned short ticket goes under the pile
    assert long not in game.ticket_deck  # returned long tickets leave the game
    game.step(1, KeepTickets(tuple(game.players[1].offer)))
    assert game.phase == Phase.TURN and game.current == 1


# ---------------------------------------------------------------------- cards
def test_two_blind_draws_end_the_turn() -> None:
    game = _started()
    game.step(0, DrawCard(None))
    assert game.phase == Phase.SECOND_CARD and game.current == 0
    game.step(0, DrawCard(None))
    assert game.current == 1 and game.players[0].hand_size == 6


def _set_face_up(game: Game, slot: int, card: str) -> None:
    """Swap a specific card from the deck into a face-up slot."""
    old = game.face_up[slot]
    game.deck.remove(card)
    if old is not None:
        game.deck.append(old)
    game.face_up[slot] = card


def test_face_up_locomotive_counts_as_both_cards() -> None:
    game = _started()
    _set_face_up(game, 2, LOCO)
    game.step(0, DrawCard(2))
    assert game.current == 1
    assert card_total(game) == TOTAL_CARDS


def test_no_face_up_locomotive_as_second_card() -> None:
    game = _started()
    _set_face_up(game, 0, "red")
    game.step(0, DrawCard(0))
    assert game.phase == Phase.SECOND_CARD
    _set_face_up(game, 1, LOCO)
    assert not game.view(0).face_up_ok[1]
    with pytest.raises(IllegalMove):
        game.step(0, DrawCard(1))
    assert card_total(game) == TOTAL_CARDS


def test_three_face_up_locomotives_wipe_the_market() -> None:
    game = _started()
    for slot in range(3):
        _set_face_up(game, slot, LOCO)
    events = game._refill_market()
    assert any(e["kind"] == "market_reset" for e in events)
    assert sum(c == LOCO for c in game.face_up) <= 2


def test_discards_are_reshuffled_into_an_empty_deck() -> None:
    game = _started()
    game.discard.extend(game.deck)
    game.deck.clear()
    game.step(0, DrawCard(None))
    assert game.deck and not game.discard


def test_deck_is_restocked_as_soon_as_it_runs_out() -> None:
    game = _started()
    game.discard.extend(game.deck[:-1])
    del game.deck[:-1]
    events = game.step(0, DrawCard(None))
    assert any(e["kind"] == "reshuffle" for e in events)
    assert game.deck and not game.discard


def test_tunnel_with_no_cards_left_reveals_nothing() -> None:
    game = _started()
    rid = _route(game, "Zurich", "Venezia")
    _give(game, 0, green=2)
    game.players[2].hand.update(game.deck + game.discard)
    game.deck.clear()
    game.discard.clear()
    events = game.step(0, Claim(rid, "green", 0))
    assert events[0]["kind"] == "tunnel" and events[0]["revealed"] == [] and game.owners[rid] == 0


def test_tunnel_reveal_reshuffles_the_discards_when_the_deck_runs_short() -> None:
    game = _started()
    rid = _route(game, "Zurich", "Venezia")
    _give(game, 0, green=2)
    game.discard.extend(game.deck[1:])
    del game.deck[1:]
    events = game.step(0, Claim(rid, "green", 0))
    kinds = [e["kind"] for e in events]
    assert kinds.index("reshuffle") < kinds.index("tunnel")
    assert len(next(e for e in events if e["kind"] == "tunnel")["revealed"]) == 3


# ---------------------------------------------------------------------- routes
def test_claim_scores_and_spends_trains_and_cards() -> None:
    game = _started()
    rid = _route(game, "Edinburgh", "London", color="orange")
    _give(game, 0, orange=3, loco=1)
    game.step(0, Claim(rid, "orange", 1))
    p = game.players[0]
    assert game.owners[rid] == 0 and p.points == 7 and p.trains == 41 and p.hand_size == 0
    assert game.current == 1


def test_claim_rejects_bad_payment_and_taken_routes() -> None:
    game = _started()
    rid = _route(game, "Edinburgh", "London", color="orange")
    _give(game, 0, orange=3)
    with pytest.raises(IllegalMove):
        game.step(0, Claim(rid, "orange", 0))
    _give(game, 0, orange=4)
    game.step(0, Claim(rid, "orange", 0))
    _give(game, 1, orange=4)
    with pytest.raises(IllegalMove):
        game.step(1, Claim(rid, "orange", 0))


def test_one_track_of_a_double_route_with_three_players() -> None:
    game = _started(3)
    black = _route(game, "Edinburgh", "London", color="black")
    orange = _route(game, "Edinburgh", "London", color="orange")
    _give(game, 0, black=4)
    game.step(0, Claim(black, "black", 0))
    _give(game, 1, orange=4)
    assert orange not in game.claimable(1)
    with pytest.raises(IllegalMove):
        game.step(1, Claim(orange, "orange", 0))


def test_both_tracks_with_four_players_but_not_by_the_same_one() -> None:
    game = _started(4)
    black = _route(game, "Edinburgh", "London", color="black")
    orange = _route(game, "Edinburgh", "London", color="orange")
    _give(game, 0, black=4, orange=4)
    game.step(0, Claim(black, "black", 0))
    assert orange not in game.claimable(0)
    _give(game, 1, orange=4)
    game.step(1, Claim(orange, "orange", 0))
    assert game.owners[orange] == 1


def test_ferry_requires_locomotives() -> None:
    game = _started()
    rid = _route(game, "London", "Dieppe")
    _give(game, 0, red=2)
    with pytest.raises(IllegalMove):
        game.step(0, Claim(rid, "red", 0))
    _give(game, 0, red=1, loco=1)
    game.step(0, Claim(rid, "red", 1))
    assert game.owners[rid] == 0


def _tunnel_game(revealed: list[str]) -> tuple[Game, int]:
    game = _started()
    rid = _route(game, "Zurich", "Venezia")
    _give(game, 0, green=4, loco=1)
    for c in revealed:
        (game.deck if c in game.deck else game.discard).remove(c)
    game.deck.extend(reversed(revealed))
    return game, rid


def test_tunnel_without_extra_cards_is_claimed_at_once() -> None:
    game, rid = _tunnel_game(["red", "blue", "white"])
    game.step(0, Claim(rid, "green", 0))
    assert game.owners[rid] == 0 and game.current == 1
    assert game.players[0].hand == Counter(green=2, loco=1)
    assert card_total(game) == TOTAL_CARDS


def test_tunnel_extra_cards_paid_or_declined() -> None:
    game, rid = _tunnel_game(["green", LOCO, "red"])
    game.step(0, Claim(rid, "green", 0))
    assert game.phase == Phase.TUNNEL and game.tunnel is not None and game.tunnel.extra == 2
    assert card_total(game) == TOTAL_CARDS
    with pytest.raises(IllegalMove):
        game.step(0, TunnelPay(2))  # only one locomotive left in hand
    game.step(0, TunnelPay(1))
    assert game.owners[rid] == 0 and game.players[0].hand == Counter(green=1)
    assert card_total(game) == TOTAL_CARDS

    game, rid = _tunnel_game(["green", "green", "green"])
    game.step(0, Claim(rid, "green", 0))
    game.step(0, TunnelDecline())
    assert rid not in game.owners and game.players[0].hand == Counter(green=4, loco=1)
    assert game.current == 1 and card_total(game) == TOTAL_CARDS


# ---------------------------------------------------------------------- tickets & stations
def test_draw_tickets_keep_at_least_one() -> None:
    game = _started()
    game.step(0, DrawTickets())
    assert game.phase == Phase.CHOOSE_TICKETS
    offer = game.players[0].offer
    with pytest.raises(IllegalMove):
        game.step(0, KeepTickets(()))
    game.step(0, KeepTickets((offer[0],)))
    assert offer[0] in game.players[0].tickets and game.current == 1


def test_stations_cost_more_each_time_and_one_per_city() -> None:
    game = _started()
    _give(game, 0, red=1)
    game.step(0, BuildStation("Paris", "red", 0))
    assert game.station_at["Paris"] == 0 and game.station_cost(0) == 2
    _give(game, 1, blue=2)
    with pytest.raises(IllegalMove):
        game.step(1, BuildStation("Paris", "blue", 0))
    game.step(1, BuildStation("Wien", "blue", 0))
    game.step(2, DrawCard(None))
    game.step(2, DrawCard(None))
    _give(game, 0, red=1, blue=1)
    with pytest.raises(IllegalMove):
        game.step(0, BuildStation("Roma", "red", 1))  # two cards of one colour (locomotives are wild)
    _give(game, 0, red=1, loco=1)
    game.step(0, BuildStation("Roma", "red", 1))


def test_pass_only_without_any_move() -> None:
    game = _started()
    with pytest.raises(IllegalMove):
        game.step(0, Pass())


# ---------------------------------------------------------------------- end of game
def test_final_round_gives_everyone_one_more_turn() -> None:
    game = _started(3)
    game.players[0].trains = 5
    rid = _route(game, "Edinburgh", "London", color="orange")
    _give(game, 0, orange=4)
    game.step(0, Claim(rid, "orange", 0))
    assert game.final_turns == 3 and game.last_round_by == 0
    for seat in (1, 2, 0):
        assert game.phase != Phase.GAME_OVER and game.current == seat
        game.step(seat, DrawCard(None))
        game.step(seat, DrawCard(None))
    assert game.phase == Phase.GAME_OVER and game.result is not None


def test_scoring_tickets_stations_and_express() -> None:
    game = _started(2)
    for p in game.players:
        p.tickets = []
    paris_wien = next(t for t in game.board.tickets if {t.a, t.b} == {"Paris", "Wien"})
    game.players[0].tickets = [paris_wien.id]
    for a, b in [("Paris", "Zurich"), ("Zurich", "Munchen"), ("Munchen", "Wien")]:
        rid = _route(game, a, b)
        game.owners[rid] = 0
        game.players[0].routes.append(rid)
        game.players[0].points += game.route(rid).points
    game.players[1].stations = ["Roma"]
    game.station_at["Roma"] = 1
    game._finish()
    res = game.result
    assert res is not None
    r0, r1 = res.players
    assert r0.tickets == [(paris_wien.id, True)] and r0.ticket_points == paris_wien.value
    assert r0.station_points == 12 and r1.station_points == 8
    assert r0.express and not r1.express and r0.express_points == 10
    assert r0.total == r0.route_points + paris_wien.value + 12 + 10
    assert res.winners == [0]


@pytest.mark.parametrize("n", [2, 3, 4, 5])
def test_bot_games_keep_every_card(n: int) -> None:
    for seed in range(4):
        bots = [make_bot("rookie" if s % 2 else "expert", seed * 10 + s) for s in range(n)]
        game = Game(n, seed=seed)
        while game.phase != Phase.GAME_OVER:
            if game.phase == Phase.INITIAL_TICKETS:
                seat = next(i for i, p in enumerate(game.players) if p.offer)
            else:
                seat = game.current
            game.step(seat, bots[seat].act(game.view(seat)))
            assert card_total(game) == TOTAL_CARDS
            assert all(p.trains >= 0 and len(p.stations) <= 3 for p in game.players)
            assert sum(c == LOCO for c in game.face_up) <= 2 or len(game.deck) + len(game.discard) < 5
        assert game.result is not None and game.turn < game.rules.max_turns


def test_play_game_runner() -> None:
    game = play_game([make_bot("expert", 1), make_bot("conductor", 2)], seed=4)
    assert game.result is not None
    assert all(
        r.total == r.route_points + r.ticket_points + r.station_points + r.express_points for r in game.result.players
    )
