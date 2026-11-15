"""Checks for the player noise of the #45 review, moved to explore/ for ADR-010. Run: python test_player_noise.py"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "explore"))
from player_noise import NOISE, noisy_players  # noqa: E402


def setup(n=500):
    """Six still players far from a still ball, except an H player 1 m from it and an A player 2 m from it."""
    players = np.zeros((n, 6, 3))
    players[:, :, 0] = [0.1, 0.2, 0.3, 0.7, 0.8, 0.9]
    players[:, :, 1] = 0.2
    players[:, 0, :2] = (0.5 + 1 / 105.3, 0.5)
    players[:, 3, :2] = (0.5 - 2 / 105.3, 0.5)
    players[:, :, 2] = 2.0
    return players, np.full((n, 2), 0.5), np.array(["H"] * 3 + ["A"] * 3)


def test_clean_players_are_untouched():
    players, ball, team = setup()
    assert len(NOISE) == 10
    assert np.array_equal(noisy_players(players, ball, team, np.random.default_rng(1), pitch=(105.3, 68.), **NOISE["clean players"]), players)


def test_every_other_scenario_changes_the_players():
    players, ball, team = setup(5000)  # 5% swaps start about once every 500 frames
    for name, kw in NOISE.items():
        out = noisy_players(players, ball, team, np.random.default_rng(1), pitch=(105.3, 68.), **kw)
        assert out.shape == players.shape, name
        assert np.array_equal(out, players) == (not kw), name


def test_swaps_trade_the_two_players_nearest_the_ball():
    players, ball, team = setup()
    out = noisy_players(players, ball, team, np.random.default_rng(1), pitch=(105.3, 68.), swap=0.5)
    swapped = out[:, 0, 0] == players[0, 3, 0]
    assert swapped.any() and np.array_equal(out[swapped, 3, :2], players[swapped, 0, :2])
    assert np.array_equal(out[:, [1, 2, 4, 5]], players[:, [1, 2, 4, 5]])  # the others stay


if __name__ == "__main__":
    test_clean_players_are_untouched()
    test_every_other_scenario_changes_the_players()
    test_swaps_trade_the_two_players_nearest_the_ball()
    print("ok")
