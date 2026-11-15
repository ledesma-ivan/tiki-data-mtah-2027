"""ATD-like errors in the players, from the review of #45 (29/10): the same yardstick to train and to confirm ADR-010.

Identity swaps near the ball, Gaussian position noise and slots lost in bursts; the 10 NOISE scenarios are the
ones of that review. Open data only (AGENTS.md). Checks: python test_player_noise.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import possession  # noqa: E402
from dead_v2_players_noise import degrade_players  # noqa: E402

FPS = possession.FPS

NOISE = {
    "clean players": {},
    "position noise 0.3 m per axis (1 s correlated)": dict(sigma=0.3),
    "position noise 0.6 m per axis (1 s correlated)": dict(sigma=0.6),
    "position noise 1.0 m per axis (1 s correlated)": dict(sigma=1.0),
    "position jitter 0.5 m per axis (each frame)": dict(sigma=0.5, corr_s=0.0),
    "10% of slot-frames lost (2 s bursts)": dict(dropout=0.10),
    "25% of slot-frames lost (2 s bursts)": dict(dropout=0.25),
    "cross-team swaps near the ball, rate for 5% of frames": dict(swap=0.05),
    "cross-team swaps near the ball, rate for 15% of frames": dict(swap=0.15),
    "noise 0.6 m + 10% lost + swaps 5%": dict(sigma=0.6, dropout=0.10, swap=0.05),
}


def noisy_players(players, ball, team, rng, sigma=0.0, corr_s=1.0, dropout=0.0, swap=0.0, *, pitch):
    """players with ATD-like errors: identity swaps between the H and A players nearest the ball (both within 5 m)
    lasting ~1 s, then Gaussian position noise (box-filtered over corr_s, sigma metres per axis), then slots lost in
    bursts (dead_v2_players_noise.degrade_players). Speeds are left as they are."""
    pitch = possession.pitch_dimensions(pitch)
    out = players.copy()
    n, k = out.shape[:2]
    if swap:
        rate = -np.log1p(-swap) / FPS
        starts = np.flatnonzero(rng.random(n) < rate)
        home, away = np.flatnonzero(team == "H"), np.flatnonzero(team == "A")
        for s, ln in zip(starts, rng.exponential(FPS, len(starts)).astype(int) + 1):
            if np.isnan(ball[s, 0]):
                continue
            d = np.hypot((players[s, :, 0] - ball[s, 0]) * pitch[0], (players[s, :, 1] - ball[s, 1]) * pitch[1])
            d = np.where(np.isnan(d), np.inf, d)
            h, a = home[d[home].argmin()], away[d[away].argmin()]
            if d[h] <= 5 and d[a] <= 5:
                out[s:s + ln, [h, a]] = out[s:s + ln, [a, h]]
    if sigma:
        w = max(1, int(round(corr_s * FPS)))
        for axis in range(2):
            c = np.vstack([np.zeros((1, k)), np.cumsum(rng.standard_normal((n + w - 1, k)), axis=0)])
            out[:, :, axis] += (c[w:] - c[:-w]) / np.sqrt(w) * sigma / pitch[axis]
    if dropout:
        out = degrade_players(out, rng, dropout=dropout)
    return out
