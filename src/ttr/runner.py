from __future__ import annotations

from collections.abc import Sequence

from ttr.bots.base import Bot
from ttr.game.engine import Game, Phase, RulesConfig


def play_game(bots: Sequence[Bot], seed: int | None = None, rules: RulesConfig | None = None) -> Game:
    game = Game(len(bots), seed=seed, rules_config=rules)
    while game.phase == Phase.INITIAL_TICKETS:
        for seat, bot in enumerate(bots):
            if game.players[seat].offer:
                game.step(seat, bot.act(game.view(seat)))
    while game.phase != Phase.GAME_OVER:
        seat = game.current
        game.step(seat, bots[seat].act(game.view(seat)))
    return game
