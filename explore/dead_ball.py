"""Which tracking signals go with a dead ball? Descriptive look at the public 5 minutes.

Not tuning: no threshold chosen here is meant to be read off these numbers (RULES.md).
Usage: python explore/dead_ball.py [data dir]    (default $MTAH_DATA; public GT from ../mtah2027)
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
MTAH = os.path.join(ROOT, "..", "mtah2027")
sys.path.insert(0, ROOT)
from possession import load_atd  # noqa: E402


def runs(mask):
    """Lengths of consecutive True runs."""
    d = np.diff(np.r_[0, mask.astype(int), 0])
    return np.flatnonzero(d == -1) - np.flatnonzero(d == 1)


if __name__ == "__main__":
    players, ball, team = load_atd()
    gt = pd.read_csv(os.path.join(MTAH, "evaluation", "gt", "BAR-ATH_possession_gt_public.csv"))
    g = gt["label"].to_numpy()
    graded = g != "X"
    dead = g == "D"
    print(f"frames {len(g)}  tracking {len(ball)}  home slots {(team == 'H').sum()}  away {(team == 'A').sum()}")

    bx, by, bs = ball.T
    feats = {
        "ball missing": np.isnan(bx),
        "ball outside 0-1": (bx < 0) | (bx > 1) | (by < 0) | (by > 1),
        "ball speed < 0.5": bs < 0.5,
        "mean player speed < 1": np.nanmean(players[:, :, 2], axis=1) < 1,
        "players tracked < 15": (~np.isnan(players[:, :, 0])).sum(1) < 15,
    }
    print(f"\nwhole match: ball missing {np.isnan(bx).mean():.1%}")
    print(f"ball x range {np.nanmin(bx):.2f}..{np.nanmax(bx):.2f}  speed p50/p99 {np.nanpercentile(bs, 50):.2f}/{np.nanpercentile(bs, 99):.2f}")
    print(f"player speed p50/p99 {np.nanpercentile(players[:, :, 2], 50):.2f}/{np.nanpercentile(players[:, :, 2], 99):.2f}")

    print(f"\npublic window: {graded.sum()} graded, {dead.sum()} dead ({dead[graded].mean():.1%})")
    print(f"dead stretches: {len(runs(dead))}, length s: {np.round(runs(dead) / 25, 1).tolist()}")
    print(f"\n{'signal':28s} {'P(sig|dead)':>12s} {'P(sig|alive)':>13s}")
    alive = graded & ~dead
    for name, m in feats.items():
        print(f"{name:28s} {m[dead].mean():12.1%} {m[alive].mean():13.1%}")
