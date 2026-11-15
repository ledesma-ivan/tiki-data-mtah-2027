"""Where dead_mask_v2 puts the stop edges against each bench's truth, by restart kind (ADR-010, #32).

Usage: python explore/edge_offsets_by_kind.py [--seeds 3] [--reserve]
Open data only (AGENTS.md): the selection matches of ADR-010 (Metrica Games 2-3, IDSSE 1-5); --reserve adds
Metrica Game 1 and IDSSE 6-7, which only the confirmation may look at. The ball is degraded as in the bench
(45% of live frames without it, 1.5 s gaps). A true stop counts when the v2 stops over it cover half of it.
"""
import argparse
import collections
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
_argv, sys.argv = sys.argv, sys.argv[:1]  # calibrate_edges' imports read sys.argv[1]
import calibrate_edges as C  # noqa: E402
import possession as P  # noqa: E402
sys.argv = _argv

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--reserve", action="store_true")
    a = ap.parse_args()
    off = collections.defaultdict(lambda: ([], []))
    for m in C.SELECTION + (C.RESERVE if a.reserve else ()):
        for g in C.load(m):
            for s in range(a.seeds):
                v2 = P.runs(P.dead_mask_v2(g.players, C.degraded(g, 1000 * g.g + s)))
                for x, y, k in g.kinds:
                    over = [(c, d) for c, d in v2 if c < y and d > x]
                    if k >= 0 and over and sum(min(y, d) - max(x, c) for c, d in over) >= 0.5 * (y - x):
                        off[(k, m[0])][0].append(min(c for c, _ in over) - x)
                        off[(k, m[0])][1].append(max(d for _, d in over) - y)
    print("v2 edges against the truth, s (+ = v2 late): median [25%, 75%] of the start and of the end")
    for (k, bench_name), (starts, ends) in sorted(off.items()):
        q = [np.percentile(np.array(v) / P.FPS, [50, 25, 75]) for v in (starts, ends)]
        print(f"  {P.KINDS[k]:12} {bench_name:7} {len(starts):4} stops  start {q[0][0]:+5.2f} [{q[0][1]:+5.2f}, "
              f"{q[0][2]:+5.2f}]  end {q[1][0]:+5.2f} [{q[1][1]:+5.2f}, {q[1][2]:+5.2f}]")
