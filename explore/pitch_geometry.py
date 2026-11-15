"""Fixed before/after geometry experiment (#52, ADR-012). Open data only; aggregates only.

Usage: python explore/pitch_geometry.py --dataset metrica --seeds 10 --seed-start 20 --bootstrap 1000
       python explore/pitch_geometry.py --dataset idsse --idsse-dir ../idsse-data --seeds 5 --bootstrap 1000

The old configuration is 32c5d46: 105.3 x 68 m for evidence and 105 x 68 m for crowd noise.
Both versions use identical raw inputs, truth, parameters and random seeds. The only treatment is
the pitch passed to evidence and degradation. Each IDSSE half is a game, as in idsse_bench.py.
"""
import argparse
import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bench  # noqa: E402
from explore import idsse_bench  # noqa: E402

LEGACY_EVIDENCE_PITCH = (105.3, 68.0)
LEGACY_CROWD_PITCH = (105.0, 68.0)


def cases(dataset, idsse_dir, speed):
    """Yield game inputs with the bench's existing truth and degradation masks."""
    if dataset == "metrica":
        for g in (1, 2, 3):
            players, ball, team, events, pitch = bench.load_game(g)
            dead = bench.calibrate_dead.dead_labels([e[:5] for e in events], len(ball))
            graded = np.zeros(len(ball), bool)
            for first, last in bench.calibrate_dead.halves([e[:5] for e in events]):
                graded[first:last + 1] = True
            yield g, players, ball, team, bench.truth_labels(events, len(ball), dead), dead, graded, pitch
    else:
        files = sorted(glob.glob(os.path.join(idsse_dir, "DFL_04_03_positions_raw_observed_*.xml")))
        if not files:
            raise ValueError("no open IDSSE positions XML files found")
        for m, path in enumerate(files):
            for h, (_, players, ball, team, truth, _, pitch) in enumerate(idsse_bench.load(path, speed)):
                yield 10 * (m + 1) + h, players, ball, team, truth, truth == "D", truth != "X", pitch


def predictions(players, ball, team, truth, dead, graded, pitch, g, seeds, seed_start, crowd, pipelines):
    """Paired predictions, preserving 32c5d46's degradation geometry explicitly."""
    spans = bench.pm.valid_runs(bench.pm.label_codes(truth))
    out = {}
    for version, evidence_pitch, crowd_pitch in (("legacy-32c5d46", LEGACY_EVIDENCE_PITCH, LEGACY_CROWD_PITCH),
                                                 ("per-game", pitch, pitch)):
        balls = {"as is": [ball], "degraded": [bench.degrade(
            ball, players, dead, 0.45, 1.5, crowd, 1000 * g + s, graded, 0.0, pitch=crowd_pitch)
            for s in range(seed_start, seed_start + seeds)]}
        for kind, variants in balls.items():
            for name in pipelines:
                out[(g, "start" if g < 10 else "status", kind, name + "/" + version)] = (truth, [
                    bench.PIPELINES[name](players, b, team, spans, dead, pitch=evidence_pitch) for b in variants])
    return out


def mean_spell(preds, name, kind):
    values = []
    for (_, _, ball, pipeline), (truth, variants) in preds.items():
        if (ball, pipeline) != (kind, name):
            continue
        gt = bench.pm.label_codes(truth)
        n_gt = len(bench.pm.possession_spells(gt, bench.pm.valid_runs(gt)))
        values.append(np.mean([bench.spell_draws(gt, bench.pm.label_codes(p), np.arange(n_gt)[None])[0]
                               for p in variants]))
    return float(np.mean(values))


def run(dataset, idsse_dir, speed, seeds, seed_start, bootstrap, crowds, pipelines):
    if seeds < 1 or bootstrap < 1:
        raise ValueError("seeds and bootstrap must be positive")
    rows = []
    for crowd in crowds:
        preds, pitches = {}, set()
        for g, players, ball, team, truth, dead, graded, pitch in cases(dataset, idsse_dir, speed):
            pitches.add(pitch)
            preds.update(predictions(players, ball, team, truth, dead, graded, pitch, g, seeds, seed_start, crowd, pipelines))
            print(f"{dataset}: game {g}, crowd {crowd:g} done", file=sys.stderr, flush=True)
        for name in pipelines:
            before, after = name + "/legacy-32c5d46", name + "/per-game"
            for (anchor, kind), (point, lo, hi, per_game) in bench.compare(preds, before, after, bootstrap).items():
                rows.append(dict(crowd=crowd, pipeline=name, truth=anchor, ball=kind, games=len(per_game),
                                 before=mean_spell(preds, before, kind), after=mean_spell(preds, after, kind),
                                 difference=point, low=lo, high=hi, pitches=sorted(pitches)))
    return dict(dataset=dataset, speed=speed if dataset == "idsse" else "positions", seeds=seeds,
                seed_start=seed_start, bootstrap=bootstrap, bootstrap_seed=bench.pm.BOOTSTRAP_SEED,
                legacy_evidence_pitch=LEGACY_EVIDENCE_PITCH, legacy_crowd_pitch=LEGACY_CROWD_PITCH,
                missing=0.45, mean_gap_s=1.5, dead_missing=0.,
                parameters=dict(radius=bench.possession.CONTROL_RADIUS, change_frames=bench.possession.CHANGE_FRAMES,
                                max_interp=bench.possession.MAX_INTERP, max_gap=bench.possession.MAX_GAP), rows=rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dataset", choices=("metrica", "idsse"), required=True)
    ap.add_argument("--idsse-dir", default=os.path.join(bench.ROOT, "..", "idsse-data"))
    ap.add_argument("--speed", choices=("provider", "positions"), default="provider")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--seed-start", type=int, default=0)
    ap.add_argument("--bootstrap", type=int, default=1000)
    ap.add_argument("--crowds", default="0,2")
    ap.add_argument("--pipelines", nargs="+", choices=tuple(bench.PIPELINES), default=["v1", "v2", "radio"])
    a = ap.parse_args()
    result = run(a.dataset, a.idsse_dir, a.speed, a.seeds, a.seed_start, a.bootstrap,
                 [float(c) for c in a.crowds.split(",")], a.pipelines)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
