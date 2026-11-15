"""Sweep of the players-only dead-ball detector on the bench (#32, exploratory; ADR-006 sweep rule).

Usage: python explore/dead_v2_sweep.py [--games 2,3] [--seeds 3] [--seed-start 0] [--top 12]
           [--cut 1.5,2,2.5] [--window 1,2,3] [--enter 0.7,0.8,0.9] [--hyst 0,0.1,0.2] [--min 1,2,3]
           [--start-pad 0] [--end-shift 0]
Selection games and seed block are fixed before running (ADR-006): select on Games 2 and 3 (seeds 0-9);
Game 1 is reserved for the confirmation with fresh seeds (bench.py --compare). Open data only (AGENTS.md).

Detector: possession.dead_mask_v2 (share of tracked players slower than `cut` m/s in a centred window of
`window` s, entering D at `enter`, staying while >= enter - hyst, D stretches of at least `min` s), then each
D stretch starts `start-pad` s earlier and ends `end-shift` s later (negative: earlier). Prints the paired
spellF1 difference against v1 (possession.dead_mask, ADR-002) and the frame F1 and edge offsets of D.
"""
import argparse
import itertools
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bench  # noqa: E402
import possession  # noqa: E402

FPS = bench.FPS
pm = bench.pm


def floats(s):
    return [float(x) for x in s.split(",")]


def shift_edges(dead, start_pad, end_shift):
    out = np.zeros_like(dead)
    for s, e in possession.runs(dead):
        s2, e2 = max(0, s - start_pad), min(len(dead), e + end_shift)
        if e2 > s2:
            out[s2:e2] = True
    return out


def spell(gt, pred):
    n_gt = len(pm.possession_spells(gt, pm.valid_runs(gt)))
    return bench.spell_draws(gt, pm.label_codes(pred), np.arange(n_gt)[None])[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", default="2,3")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--seed-start", type=int, default=0)
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--cut", default="1.5,2,2.5")
    ap.add_argument("--window", default="1,2,3")
    ap.add_argument("--enter", default="0.7,0.8,0.9")
    ap.add_argument("--hyst", default="0,0.1,0.2")
    ap.add_argument("--min", default="1,2,3")
    ap.add_argument("--start-pad", default="0")
    ap.add_argument("--end-shift", default="0")
    a = ap.parse_args()
    grid = [dict(cut=c, window=int(round(w * FPS)), enter=int(round(100 * en)), stay=int(round(100 * (en - h))),
                 min_len=int(round(m * FPS)), pad=int(round(p * FPS)), shift=int(round(sh * FPS)))
            for c, w, en, h, m, p, sh in itertools.product(
                floats(a.cut), floats(a.window), floats(a.enter), floats(a.hyst), floats(a.min),
                floats(a.start_pad), floats(a.end_shift))]
    games = [int(g) for g in a.games.split(",")]
    per_game = {i: {} for i in range(len(grid))}
    diag = {i: [] for i in range(len(grid))}
    t0 = time.time()
    for g in games:
        players, ball, team, events, pitch = bench.load_game(g)
        n = len(ball)
        dead = bench.calibrate_dead.dead_labels([e[:5] for e in events], n)
        graded = np.zeros(n, bool)
        for first, last in bench.calibrate_dead.halves([e[:5] for e in events]):
            graded[first:last + 1] = True
        gt = pm.label_codes(bench.truth_labels(events, n, dead, "start"))
        spans = pm.valid_runs(gt)
        balls = [bench.degrade(ball, players, dead, 0.45, 1.5, 0.0, 1000 * g + s, graded, pitch=pitch)
                 for s in range(a.seed_start, a.seed_start + a.seeds)]
        evid = [bench.owner_evidence(players, b, team, pitch=pitch) for b in balls]
        base = [spell(gt, bench.segment(possession.dead_mask(players, b), e, spans)) for b, e in zip(balls, evid)]
        cache = {}
        for i, p in enumerate(grid):
            key = (p["cut"], p["window"], p["enter"], p["stay"], p["min_len"])
            if key not in cache:
                # the players part only: a ball always inside the pitch never adds D
                cache[key] = possession.dead_mask_v2(players, np.full((n, 2), 0.5), *key, lead=0, trim=0)
            dm = shift_edges(cache[key], p["pad"], p["shift"])
            per_game[i][g] = float(np.mean([spell(gt, bench.segment(dm, e, spans)) - b0 for e, b0 in zip(evid, base)]))
            diag[i].append(bench.calibrate_dead.score(dm, dead, gt != pm.X))
        print(f"game {g} done ({time.time() - t0:.0f} s); v1 spellF1 {np.mean(base):.3f}", flush=True)
    order = sorted(per_game, key=lambda i: -np.mean([per_game[i][g] for g in games]))
    print(f"\ntop {a.top} of {len(grid)} by mean paired difference over games {games}, seeds "
          f"{a.seed_start}-{a.seed_start + a.seeds - 1} (truth from event start)")
    for i in order[:a.top]:
        p, d = grid[i], diag[i]
        print(f"  cut {p['cut']} win {p['window'] / FPS:g}s enter {p['enter']} stay {p['stay']} min {p['min_len'] / FPS:g}s"
              f" pad {p['pad'] / FPS:g}s shift {p['shift'] / FPS:+g}s  diff {np.mean([per_game[i][g] for g in games]):+.4f}  "
              + "  ".join(f"g{g} {per_game[i][g]:+.3f}" for g in games)
              + f"  D P {np.mean([x['P'] for x in d]):.3f} R {np.mean([x['R'] for x in d]):.3f}"
              f" F1 {np.mean([x['F1'] for x in d]):.3f}  pred/true {sum(x['n_pred'] for x in d)}/{sum(x['n_true'] for x in d)}"
              f"  edges {np.mean([x['start_s'] for x in d]):+.2f}/{np.mean([x['end_s'] for x in d]):+.2f}s")


if __name__ == "__main__":
    main()
