"""Transition timing in the bench: F1 at tau = 25 frames and median latency of the possession changes (ADR-009).

Open data only (Metrica Sample Games 1-3), the bench's degraded ball, verdict from the start of the event.
Prints means over games and seeds, nothing else.

The median mixes three kinds of transition: the entry to D, the exit from D and the change of team. The D edges
are set by DEAD_LEAD and DEAD_TRIM, so this number says little about the team changes; the split by kind is in
the ADR-009 (measured with match_transitions, as in explore/dead_v2_transitions.py).

Usage: python explore/edge_latency.py [--seed-start 20] [--seeds 5]
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bench  # noqa: E402

PIPELINES = ["v1", "v2", "radio", "v1, true D", "radio, true D"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-start", type=int, default=20)
    ap.add_argument("--seeds", type=int, default=5)
    args = ap.parse_args()
    pm = bench.pm
    res = {(p, k): [] for p in PIPELINES for k in ("as is", "degraded")}
    for g in (1, 2, 3):
        players, ball, team, events, pitch = bench.load_game(g)
        n = len(ball)
        dead = bench.calibrate_dead.dead_labels([e[:5] for e in events], n)
        graded = np.zeros(n, bool)
        for first, last in bench.calibrate_dead.halves([e[:5] for e in events]):
            graded[first:last + 1] = True
        gt = pm.label_codes(bench.truth_labels(events, n, dead, "start"))
        spans = pm.valid_runs(gt)
        balls = [("as is", ball)] + [("degraded", bench.degrade(ball, players, dead, 0.45, 1.5, 0.0, 1000 * g + s, graded, 0.0, pitch=pitch))
                                     for s in range(args.seed_start, args.seed_start + args.seeds)]
        for kind, b in balls:
            for p in PIPELINES:
                pred = bench.PIPELINES[p](players, b, team, spans, dead, pitch=pitch)
                t = pm.evaluate(gt, pm.label_codes(pred), bootstrap_n=0)["transitions"][25]
                res[(p, kind)].append((t["f1"], t["median_latency"], t["mean_abs_latency"], t["n_pred"] / max(1, t["n_gt"])))
    print(f"seeds {args.seed_start}..{args.seed_start + args.seeds - 1}; columns: F1 at tau=25, median latency (frames), mean |latency|, predicted/true changes")
    for (p, k), v in res.items():
        a = np.nanmean(np.array(v, float), axis=0)
        print(f"{p:14s}{k:9s}  {a[0]:.3f}  {a[1]:+.1f}  {a[2]:.1f}  {a[3]:.2f}")


if __name__ == "__main__":
    main()
