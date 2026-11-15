"""Event-based D (ADR-003, the bench truth) against the D of the corrected tracking (#41 review, question 3).

Usage: python explore/dead_truth_events_vs_tracking.py
CHALLENGE.md: the official ground truth is D "where the corrected tracking marks the ball dead".
Sample-data's corrected tracking drops the ball while it is dead, so a missing ball is that mark here.
For each event-D stretch, the tracking-D stretch that overlaps it most; offsets are tracking minus events
in seconds (start < 0: the tracking marks it dead earlier; end > 0: it keeps it dead longer).
Open data only (AGENTS.md): Metrica Sample Games 1-3.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bench  # noqa: E402
from possession import runs  # noqa: E402

for g in (1, 2, 3):
    players, ball, team, events, pitch = bench.load_game(g)
    n = len(ball)
    dead_ev = bench.calibrate_dead.dead_labels([e[:5] for e in events], n)
    graded = bench.truth_labels(events, n, dead_ev) != "X"
    dead_ev &= graded
    dead_tr = np.isnan(ball[:, 0]) & graded
    tp, fp, fn = (dead_ev & dead_tr).sum(), (dead_tr & ~dead_ev).sum(), (dead_ev & ~dead_tr).sum()
    tr_runs = runs(dead_tr)
    starts, ends = [], []
    for s, e in runs(dead_ev):
        overlap = [min(e, b) - max(s, a) for a, b in tr_runs]
        k = int(np.argmax(overlap)) if overlap else -1
        if k >= 0 and overlap[k] > 0:
            starts.append((tr_runs[k][0] - s) / bench.FPS)
            ends.append((tr_runs[k][1] - e) / bench.FPS)
    q = lambda x: "median {:+.2f} s (p25 {:+.2f}, p75 {:+.2f})".format(*np.percentile(x, [50, 25, 75]))
    print(f"game {g}: {len(runs(dead_ev))} event stoppages, {len(starts)} with a tracking pair; "
          f"tracking D against event D per frame: P {tp / (tp + fp):.3f} R {tp / (tp + fn):.3f}")
    print(f"  start {q(starts)}")
    print(f"  end   {q(ends)}")
