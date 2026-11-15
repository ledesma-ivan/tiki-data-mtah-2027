"""Dead-ball signals that do not need the ball to go missing: AUC of D against live play (#32, exploratory).

Usage: python explore/dead_v2_features.py
Open data only (AGENTS.md): Sample Games 1-3, the bench's degraded ball (45% of live frames missing, gaps of
1.5 s, seed 0, ball restored at stoppages) and the D labels of ADR-003. AUC 0.5 = no signal; below 0.5 the
signal is reversed (lower means dead). Ball features are scored only where the ball is seen.
"""
import os
import sys
import warnings

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bench  # noqa: E402

FPS = bench.FPS


def auc(score, positive):
    """Rank AUC of score for positive against the rest, ties averaged; NaN scores are left out."""
    ok = ~np.isnan(score)
    s, p = score[ok], positive[ok]
    order = np.argsort(s, kind="mergesort")
    ranks = np.empty(len(s))
    sorted_s = s[order]
    # average ranks over ties
    edges = np.r_[0, np.flatnonzero(np.diff(sorted_s)) + 1, len(s)]
    for a, b in zip(edges[:-1], edges[1:]):
        ranks[order[a:b]] = (a + b + 1) / 2
    n_pos, n_neg = p.sum(), (~p).sum()
    return (ranks[p].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg), ok.mean()


def smooth(x, window):
    """Centred moving mean that ignores NaN (exploration only: float cumsum)."""
    v = np.nan_to_num(x)
    c = np.cumsum(np.r_[0, v])
    k = np.cumsum(np.r_[0, ~np.isnan(x)])
    half = window // 2
    lo = np.clip(np.arange(len(x)) - half, 0, len(x))
    hi = np.clip(np.arange(len(x)) + window - half, 0, len(x))
    n = k[hi] - k[lo]
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n > 0, (c[hi] - c[lo]) / n, np.nan)


def features(players, ball, team, *, pitch):
    speed = players[:, :, 2]
    tracked = ~np.isnan(speed)
    count = tracked.sum(1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        v_mean = np.nanmean(speed, axis=1)
        v_med = np.nanmedian(speed, axis=1)
        top = np.sort(np.where(tracked, speed, -np.inf), axis=1)[:, ::-1]
        top3 = np.where(count >= 3, top[:, :3].mean(1), np.nan)
        x = players[:, :, 0] * pitch[0]
        y = players[:, :, 1] * pitch[1]
        spread = np.sqrt(np.nanvar(x, axis=1) + np.nanvar(y, axis=1))
        # kick-off shape: each team on its own side of halfway (sign agreement with the team mean)
        home = team == "H"
        side_h = np.nanmean(players[:, home, 0], axis=1) < 0.5
        own = np.where(side_h[:, None] == home[None, :], players[:, :, 0] < 0.5, players[:, :, 0] > 0.5)
        own_half = np.where(tracked, own, False).sum(1) / np.maximum(count, 1)
    frac_slow = np.where(count > 0, ((speed < 1.0) & tracked).sum(1) / np.maximum(count, 1), np.nan)
    frac_slow2 = np.where(count > 0, ((speed < 2.0) & tracked).sum(1) / np.maximum(count, 1), np.nan)
    bx, by = ball[:, 0], ball[:, 1]
    step = np.diff(ball[:, :2], axis=0, prepend=np.nan) * pitch
    v_ball = np.sqrt(step[:, 0] ** 2 + step[:, 1] ** 2) * FPS
    edge = np.minimum(np.minimum(bx, 1 - bx) * pitch[0], np.minimum(by, 1 - by) * pitch[1])
    return {
        "v_mean": v_mean, "v_mean 2s": smooth(v_mean, 2 * FPS), "v_med": v_med, "v_med 2s": smooth(v_med, 2 * FPS),
        "top3": top3, "top3 2s": smooth(top3, 2 * FPS), "top3 4s": smooth(top3, 4 * FPS),
        "frac<1": frac_slow, "frac<1 2s": smooth(frac_slow, 2 * FPS), "frac<2 2s": smooth(frac_slow2, 2 * FPS),
        "spread": spread, "own half": own_half, "own half 2s": smooth(own_half, 2 * FPS),
        "ball speed": v_ball, "ball speed 1s": smooth(v_ball, FPS), "ball to edge": edge,
    }


def main():
    rows = {}
    for g in (1, 2, 3):
        players, ball, team, events, pitch = bench.load_game(g)
        n = len(ball)
        dead = bench.calibrate_dead.dead_labels([e[:5] for e in events], n)
        graded = np.zeros(n, bool)
        for first, last in bench.calibrate_dead.halves([e[:5] for e in events]):
            graded[first:last + 1] = True
        degraded = bench.degrade(ball, players, dead, 0.45, 1.5, seed=1000 * g, graded=graded, pitch=pitch)
        f = features(players, degraded, team, pitch=pitch)
        print(f"game {g}: D {dead[graded].mean():.1%} of graded frames")
        for name, values in f.items():
            a, cov = auc(values[graded], dead[graded])
            rows.setdefault(name, []).append((a, cov))
    print(f"\n{'feature':14} " + "  ".join(f"g{g} AUC (cov)" for g in (1, 2, 3)))
    for name, r in rows.items():
        print(f"{name:14} " + "  ".join(f"{a:6.3f} ({c:4.0%})" for a, c in r))


if __name__ == "__main__":
    main()
