import pytest

from ttr.bots import REGISTRY, make_bot
from ttr.game.engine import Phase
from ttr.runner import play_game


@pytest.mark.parametrize("key", sorted(REGISTRY))
def test_every_bot_finishes_games_legally(key: str) -> None:
    for seed in range(3):
        game = play_game([make_bot(key, seed), make_bot("rookie", seed + 100), make_bot(key, seed + 200)], seed=seed)
        assert game.phase == Phase.GAME_OVER and game.result is not None
        assert game.turn < game.rules.max_turns


def test_bots_are_deterministic_per_seed() -> None:
    a = play_game([make_bot("expert", 1), make_bot("conductor", 2)], seed=9)
    b = play_game([make_bot("expert", 1), make_bot("conductor", 2)], seed=9)
    assert a.result is not None and b.result is not None
    assert [r.total for r in a.result.players] == [r.total for r in b.result.players]
    assert a.owners == b.owners


def test_planners_beat_the_rookie() -> None:
    wins = 0
    for seed in range(10):
        game = play_game([make_bot("conductor", seed), make_bot("rookie", seed)], seed=seed)
        assert game.result is not None
        wins += game.result.winners == [0]
    assert wins >= 9


def test_expert_uses_its_trains() -> None:
    left = []
    for seed in range(6):
        game = play_game(
            [make_bot("expert", seed), make_bot("expert", seed + 50), make_bot("expert", seed + 99)], seed=seed
        )
        left += [p.trains for p in game.players]
    assert sum(left) / len(left) < 8
