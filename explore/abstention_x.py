"""Does abstaining (X) inside the graded halves help spellF1 or macroF1? (issue #10)

Open data only (Metrica Sample Games 1-3), the bench's degraded ball, the pipeline given by --pipeline (v1 by default).
The scorer forward-fills every X with the last non-X label of the half before matching possessions,
so an X is "repeat my previous answer". Policies, all applied to the same v1 labels:

  none     never X inside a half (what possession.py does today)
  gap      X on live frames where the ball is missing for at least MIN_GAP frames
  edges    X on the frames between a live change and the D that follows it (last EDGE frames of a stretch)

Usage: python explore/abstention_x.py [--seeds 5] [--pipeline v1|v2|radio]
Prints aggregate spellF1 / macroF1 only.
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bench  # noqa: E402
import calibrate_dead  # noqa: E402
import possession  # noqa: E402

MIN_GAP = 2 * possession.FPS
EDGE = possession.FPS


def policy_gap(labels, ball):
    out = labels.copy()
    for a, b in possession.runs(np.isnan(ball[:, 0])):
        if b - a >= MIN_GAP:
            seg = out[a:b]
            seg[(seg == "H") | (seg == "A")] = "X"
    return out


def policy_edges(labels, ball):
    out = labels.copy()
    for a, b in possession.runs((labels == "H") | (labels == "A")):
        out[max(a, b - EDGE):b] = "X"
    return out


POLICIES = {"none": lambda lab, ball: lab, "gap": policy_gap, "edges": policy_edges}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--pipeline", default="v1", help="a bench pipeline: v1, v2, ...")
    args = ap.parse_args()
    table = {name: [] for name in POLICIES}
    for g in (1, 2, 3):
        players, ball, team, events, pitch = bench.load_game(g)
        n = len(ball)
        dead = calibrate_dead.dead_labels([e[:5] for e in events], n)
        graded = np.zeros(n, bool)
        for first, last in calibrate_dead.halves([e[:5] for e in events]):
            graded[first:last + 1] = True
        truth = bench.truth_labels(events, n, dead, "start")
        spans = bench.pm.valid_runs(bench.pm.label_codes(truth))
        for s in range(args.seeds):
            b = bench.degrade(ball, players, dead, 0.45, 1.5, 0.0, 1000 * g + s, graded, 0.0, pitch=pitch)
            labels = bench.PIPELINES[args.pipeline](players, b, team, spans, dead, pitch=pitch)
            for name, fn in POLICIES.items():
                r = bench.score(truth, fn(labels, b), 0)
                table[name].append((r["spell"], r["macro"]))
    print(f"{args.pipeline}, degraded ball, Games 1-3, {args.seeds} seeds each (mean over games and seeds)")
    print(f"{'policy':8s} spellF1  macroF1")
    for name, rows in table.items():
        spell, macro = np.mean(rows, axis=0)
        print(f"{name:8s} {spell:.3f}    {macro:.3f}")


if __name__ == "__main__":
    main()
