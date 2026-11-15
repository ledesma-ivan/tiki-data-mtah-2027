"""What the "ball seen off the pitch" part of v2 adds, and how much the bench inflates it (#32, exploratory).

Usage: python explore/dead_v2_off_pitch.py [--games 2,3] [--seeds 10] [--seed-start 0] [--clip-restored]
Candidates against v1 (ADR-002), paired, at both ends of the ball range: the bench default (45% of live
frames missing) and --missing 0 (2-8%, only the ball restored at stoppages).

The bench restores the ball at stoppages by interpolating between the positions around them, and that
ball is off the pitch in 27-42% of D frames (raw sample-data: 0-3%; public window of BAR-ATH, ADR-002: 7%).
--clip-restored moves the restored positions onto the pitch, so the off-pitch signal only comes from real
observations: the low end of what the ATD shows. Open data only (AGENTS.md).
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bench  # noqa: E402
import possession  # noqa: E402

pm = bench.pm

CANDIDATES = {
    "v1 without the ball missing": lambda p, b: possession.dead_mask(p, np.where(np.isnan(b[:, :2]), 0.5, b[:, :2])),
    "v2, players only": lambda p, b: possession.dead_mask_v2(p, np.full((len(b), 2), 0.5)),
    "v2 (players + off pitch)": lambda p, b: possession.dead_mask_v2(p, b),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", default="2,3")
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--seed-start", type=int, default=0)
    ap.add_argument("--clip-restored", action="store_true")
    a = ap.parse_args()
    games = [int(g) for g in a.games.split(",")]
    for missing in (0.45, 0.0):
        preds = {}
        f1 = {k: [] for k in ["v1", *CANDIDATES]}
        off_dead = []
        for g in games:
            players, ball, team, events, pitch = bench.load_game(g)
            n = len(ball)
            dead = bench.calibrate_dead.dead_labels([e[:5] for e in events], n)
            graded = np.zeros(n, bool)
            for first, last in bench.calibrate_dead.halves([e[:5] for e in events]):
                graded[first:last + 1] = True
            truth = bench.truth_labels(events, n, dead, "start")
            spans = pm.valid_runs(pm.label_codes(truth))
            restored = dead & np.isnan(ball[:, 0])
            out = {k: [] for k in f1}
            for s in range(a.seed_start, a.seed_start + a.seeds):
                b = bench.degrade(ball, players, dead, missing, 1.5, 0.0, 1000 * g + s, graded, pitch=pitch)
                if a.clip_restored:
                    b[restored, :2] = np.clip(b[restored, :2], 0.0, 1.0)
                bx, by = b[:, 0], b[:, 1]
                off_dead.append(((bx < 0) | (bx > 1) | (by < 0) | (by > 1))[graded & dead].mean())
                ev = bench.owner_evidence(players, b, team, pitch=pitch)
                masks = {"v1": possession.dead_mask(players, b), **{k: f(players, b) for k, f in CANDIDATES.items()}}
                for k, dm in masks.items():
                    out[k].append(bench.segment(dm, ev, spans))
                    f1[k].append(bench.calibrate_dead.score(dm, dead, pm.label_codes(truth) != pm.X)["F1"])
            for k in out:
                preds[(g, "start", "degraded", k)] = (truth, out[k])
        print(f"--missing {missing}{' --clip-restored' if a.clip_restored else ''}: ball off pitch in "
              f"{np.mean(off_dead):.1%} of D frames; candidate - v1, paired, games {games}, "
              f"seeds {a.seed_start}-{a.seed_start + a.seeds - 1}")
        for k in CANDIDATES:
            (point, lo, hi, per_game), = bench.compare(preds, "v1", k, 1000).values()
            print(f"  {k:28} {point:+.3f} [{lo:+.3f}, {hi:+.3f}]  " + "  ".join(f"g{g} {d:+.3f}" for g, d in per_game.items())
                  + f"   D F1 {np.mean(f1[k]):.3f} (v1 {np.mean(f1['v1']):.3f})", flush=True)


if __name__ == "__main__":
    main()
