"""Does v2 hold when the players are noisy too? Paired v2 - v1 with degraded player tracking (#32, exploratory).

Usage: python explore/dead_v2_players_noise.py [--games 1,2,3] [--seeds 10] [--seed-start 10]
The bench degrades only the ball (ADR-006, Negative: it does not model player noise), and v2 reads only the
players. Here the players are degraded too, the same way for v1 and v2, on top of the default ball
(45% of live frames missing, gaps of 1.5 s): speed noise, slots lost in bursts, and speeds smoothed over
0.5 s as a provider might. Open data only (AGENTS.md); parameters fixed beforehand, nothing is tuned here.
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bench  # noqa: E402
import possession  # noqa: E402

FPS = bench.FPS
pm = bench.pm


def degrade_players(players, rng, noise=0.0, dropout=0.0, smooth_s=0.0, gap_s=2.0):
    """Copy of players with speed noise (m/s, Gaussian), slots lost in bursts and smoothed speeds."""
    out = players.copy()
    n, k = out.shape[:2]
    speed = out[:, :, 2]
    if smooth_s:
        w = int(round(smooth_s * FPS))
        filled = np.nan_to_num(speed)
        c = np.cumsum(np.vstack([np.zeros((1, k)), filled]), axis=0)
        cnt = np.cumsum(np.vstack([np.zeros((1, k)), ~np.isnan(speed)]), axis=0)
        lo = np.clip(np.arange(n) - w // 2, 0, n)
        hi = np.clip(np.arange(n) + w - w // 2, 0, n)
        with np.errstate(invalid="ignore", divide="ignore"):
            sm = (c[hi] - c[lo]) / (cnt[hi] - cnt[lo])
        speed = np.where(np.isnan(speed), np.nan, sm)
    if noise:
        speed = np.maximum(0.0, speed + rng.normal(0, noise, speed.shape))
    if dropout:
        length = gap_s * FPS
        rate = -np.log1p(-dropout) / length
        for j in range(k):
            starts = np.flatnonzero(rng.random(n) < rate)
            for s, ln in zip(starts, rng.exponential(length, len(starts)).astype(int) + 1):
                speed[s:s + ln, j] = np.nan
                out[s:s + ln, j, :2] = np.nan
    out[:, :, 2] = speed
    return out


SCENARIOS = {
    "clean players": {},
    "speed noise 0.3 m/s": dict(noise=0.3),
    "speed noise 0.6 m/s": dict(noise=0.6),
    "10% of slot-frames lost": dict(dropout=0.10),
    "25% of slot-frames lost": dict(dropout=0.25),
    "speeds smoothed 0.5 s": dict(smooth_s=0.5),
    "noise 0.3 + 10% lost + smoothed": dict(noise=0.3, dropout=0.10, smooth_s=0.5),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", default="1,2,3")
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--seed-start", type=int, default=10)
    a = ap.parse_args()
    games = [int(g) for g in a.games.split(",")]
    loaded = {}
    for g in games:
        players, ball, team, events, pitch = bench.load_game(g)
        n = len(ball)
        dead = bench.calibrate_dead.dead_labels([e[:5] for e in events], n)
        graded = np.zeros(n, bool)
        for first, last in bench.calibrate_dead.halves([e[:5] for e in events]):
            graded[first:last + 1] = True
        truth = bench.truth_labels(events, n, dead, "start")
        spans = pm.valid_runs(pm.label_codes(truth))
        balls = [bench.degrade(ball, players, dead, 0.45, 1.5, 0.0, 1000 * g + s, graded, pitch=pitch)
                 for s in range(a.seed_start, a.seed_start + a.seeds)]
        loaded[g] = (players, team, dead, truth, spans, balls, pitch)
    print(f"v2 - v1, paired, games {games}, seeds {a.seed_start}-{a.seed_start + a.seeds - 1}, truth from event start")
    for name, kw in SCENARIOS.items():
        preds, f1 = {}, {"v1": [], "v2": []}
        for g, (players, team, dead, truth, spans, balls, pitch) in loaded.items():
            out = {"v1": [], "v2": []}
            for s, ball in enumerate(balls):
                p = degrade_players(players, np.random.default_rng(10_000 * g + a.seed_start + s), **kw)
                ev = bench.owner_evidence(p, ball, team, pitch=pitch)
                for key, dm in (("v1", possession.dead_mask(p, ball)), ("v2", possession.dead_mask_v2(p, ball))):
                    out[key].append(bench.segment(dm, ev, spans))
                    f1[key].append(bench.calibrate_dead.score(dm, dead, pm.label_codes(truth) != pm.X)["F1"])
            for key in out:
                preds[(g, "start", "degraded", key)] = (truth, out[key])
        (point, lo, hi, per_game), = bench.compare(preds, "v1", "v2", 1000).values()
        print(f"  {name:32} {point:+.3f} [{lo:+.3f}, {hi:+.3f}]  "
              + "  ".join(f"g{g} {d:+.3f}" for g, d in per_game.items())
              + f"   D F1 v1 {np.mean(f1['v1']):.3f}  v2 {np.mean(f1['v2']):.3f}", flush=True)


if __name__ == "__main__":
    main()
