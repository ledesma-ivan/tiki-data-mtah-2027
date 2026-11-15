"""Transitions of v1 and v2 on the bench, by kind: into D, out of D (restart), between teams (#41 review, question 3).

Usage: python explore/dead_v2_transitions.py
Official scorer (possession_metrics.match_transitions, tolerance 25 frames, typed "to") on the bench defaults
(ADR-006: degraded ball, truth from event start), Sample Games 1-3, seeds 0-9. Latency is the predicted minus
the true frame (negative: early). Open data only (AGENTS.md).
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bench  # noqa: E402

pm = bench.pm
KINDS = ("into D", "out of D", "team change")


def kind(t):
    return KINDS[0] if t[2] == pm.D else KINDS[1] if t[1] == pm.D else KINDS[2]


rows, preds = bench.run([1, 2, 3], 10, 0.45, 1.5, 0.0, ["start"], 0)
for name in ("v1", "v2"):
    stats = {k: {"lat": [], "tp": 0, "fn": 0, "fp": 0} for k in KINDS}
    for g in (1, 2, 3):
        truth, outs = preds[(g, "start", "degraded", name)]
        gt = pm.label_codes(truth)
        spans = pm.valid_runs(gt)
        gt_tr = pm.transitions(gt, spans)
        for p in outs:
            pr = pm.transitions(pm.fill_abstentions(pm.label_codes(p), spans), spans)
            pairs, missed, spurious = pm.match_transitions(gt_tr, pr, 25, "to")
            for a, b in pairs:
                stats[kind(a)]["lat"].append(b[0] - a[0])
                stats[kind(a)]["tp"] += 1
            for a in missed:
                stats[kind(a)]["fn"] += 1
            for b in spurious:
                stats[kind(b)]["fp"] += 1
    for k, s in stats.items():
        p, r = s["tp"] / max(s["tp"] + s["fp"], 1), s["tp"] / max(s["tp"] + s["fn"], 1)
        f1 = 2 * p * r / max(p + r, 1e-9)
        print(f"{name} {k:12} F1 {f1:.3f} (P {p:.3f} R {r:.3f})  median latency {np.median(s['lat']):+.1f} frames"
              f"  ({s['tp']} matched)")
