"""Reproduce the historical geometry parity check using frozen git source. Open data only.

Usage: python explore/verify_pitch_geometry.py --dataset metrica --seeds 2 --seed-start 20
       python explore/verify_pitch_geometry.py --dataset idsse --idsse-dir ../idsse-data --seeds 1

This checks prediction arrays, not bootstrap samples. Prints aggregate counts only.
The fixed revision must be available in the local git history.
"""
import argparse
import json
import os
import subprocess
import sys
import types

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from explore import pitch_geometry as experiment  # noqa: E402

BASELINE = "32c5d4682a98e8f52aafc33182b805fe1504c93b"
PIPELINES = ("v1", "v2", "radio")


def frozen_bench():
    """Load only source code; __main__ and match-data loaders are never executed."""
    modules = {}
    for name in ("possession", "bench"):
        source = subprocess.check_output(["git", "show", f"{BASELINE}:{name}.py"],
                                         cwd=experiment.bench.ROOT, text=True)
        module = types.ModuleType("frozen_" + name)
        module.__file__ = os.path.join(experiment.bench.ROOT, name + ".py")
        exec(compile(source, f"{BASELINE}:{name}.py", "exec"), module.__dict__)
        modules[name] = module
    # Functions resolve the module global at call time; use the frozen implementation.
    modules["bench"].possession = modules["possession"]
    return modules["bench"]


def verify(dataset, idsse_dir, seeds, seed_start):
    if seeds < 1:
        raise ValueError("seeds must be positive")
    old = frozen_bench()
    checks, games = 0, 0
    for g, players, ball, team, truth, dead, graded, pitch in experiment.cases(dataset, idsse_dir, "provider"):
        games += 1
        anchor = "start" if dataset == "metrica" else "status"
        spans = old.pm.valid_runs(old.pm.label_codes(truth))
        for crowd in (0., 2.):
            current = experiment.predictions(players, ball, team, truth, dead, graded, pitch,
                                             g, seeds, seed_start, crowd, PIPELINES)
            balls = {"as is": [ball], "degraded": [old.degrade(
                ball, players, dead, .45, 1.5, crowd, 1000 * g + s, graded, 0.)
                for s in range(seed_start, seed_start + seeds)]}
            for name in PIPELINES:
                for kind, variants in balls.items():
                    _, actual = current[(g, anchor, kind, name + "/legacy-32c5d46")]
                    if len(actual) != len(variants):
                        raise AssertionError("prediction count differs from frozen baseline")
                    for prediction, b in zip(actual, variants):
                        expected = old.PIPELINES[name](players, b, team, spans, dead)
                        if not np.array_equal(prediction, expected):
                            raise AssertionError("legacy geometry prediction differs from frozen baseline")
                        checks += 1
        print(f"{dataset}: game {g} parity OK", file=sys.stderr, flush=True)
    return dict(baseline=BASELINE, dataset=dataset, games=games, seeds=seeds, seed_start=seed_start,
                crowds=[0, 2], pipelines=PIPELINES, prediction_arrays=checks, equal=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dataset", choices=("metrica", "idsse"), required=True)
    ap.add_argument("--idsse-dir", default=os.path.join(experiment.bench.ROOT, "..", "idsse-data"))
    ap.add_argument("--seeds", type=int, required=True)
    ap.add_argument("--seed-start", type=int, default=0)
    a = ap.parse_args()
    print(json.dumps(verify(a.dataset, a.idsse_dir, a.seeds, a.seed_start), indent=2))


if __name__ == "__main__":
    main()
