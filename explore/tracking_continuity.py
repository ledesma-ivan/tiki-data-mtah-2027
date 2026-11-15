"""Fixed before/after loader experiment (#53, ADR-015). Open data and aggregates only.

Usage: python explore/tracking_continuity.py --dataset metrica --seeds 10 --seed-start 20
       python explore/tracking_continuity.py --dataset idsse --idsse-dir data/idsse-open --speed positions

Legacy is 9e2a4b6's backward slot difference, without player/period cuts. Detector,
truth, geometry, noise and parameters are shared. No calibration or model training.
"""
import argparse
import glob
import json
import os
import sys
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import bench  # noqa: E402
from explore import idsse_bench, pitch_geometry  # noqa: E402


def legacy_speed(xy, *args, **kwargs):
    """Frozen difference from 9e2a4b6; scale is 1 for IDSSE's metre positions."""
    step = np.diff(xy, axis=0, prepend=np.nan) * kwargs.get('scale', (1., 1.))
    return np.hypot(step[..., 0], step[..., 1]) * bench.FPS


def cases(dataset, idsse_dir, speed):
    if dataset == 'metrica':
        for case in pitch_geometry.cases(dataset, idsse_dir, speed):
            g, players, ball, team, truth, dead, graded, pitch = case
            # The legacy loader assumed dense clocks. Verify that on these open
            # files before reconstructing its inputs from the corrected loader.
            if g == 3:
                frames = pd.read_csv(bench.calibrate_dead.PREFIX + 'tracking.txt', sep=':',
                                     header=None, usecols=[0]).iloc[:, 0].to_numpy()
            else:
                prefix = os.path.join(bench.ROOT, 'data', f'Sample_Game_{g}', f'Sample_Game_{g}_')
                frames = pd.read_csv(prefix + 'RawTrackingData_Home_Team.csv', skiprows=2,
                                     usecols=[1]).iloc[:, 0].to_numpy()
            if not np.array_equal(frames, np.arange(1, len(players) + 1)):
                raise ValueError('legacy experiment requires contiguous open Metrica frames')
            before = players.copy()
            before[:, :, 2] = legacy_speed(players[:, :, :2], scale=pitch)
            yield case, before
    else:
        files = sorted(glob.glob(os.path.join(idsse_dir, 'DFL_04_03_positions_raw_observed_*.xml')))
        if not files:
            raise ValueError('no open IDSSE positions XML files found')
        for m, path in enumerate(files, 1):
            current = idsse_bench.load(path, speed)
            # Use the raw metre positions from the existing cache, avoiding a
            # normalise/denormalise round trip in the historical calculation.
            with patch.object(idsse_bench, 'derived_speed', legacy_speed):
                old = idsse_bench.load(path, speed)
            for h, ((_, players, ball, team, truth, _, pitch), previous) in enumerate(zip(current, old)):
                yield (10 * m + h, players, ball, team, truth, truth == 'D', truth != 'X', pitch), previous[1]


def absolute_metrics(preds, name, kind, bootstrap):
    """Equal game/half weight; same possession/seed draws as bench.compare."""
    points, dead_f1, draws = [], [], []
    for (g, _, ball, pipeline), (truth, variants) in sorted(preds.items()):
        if (ball, pipeline) != (kind, name):
            continue
        gt = bench.pm.label_codes(truth)
        n_gt = len(bench.pm.possession_spells(gt, bench.pm.valid_runs(gt)))
        rng = np.random.RandomState(bench.pm.BOOTSTRAP_SEED + g)
        picks = rng.randint(0, n_gt, (bootstrap, n_gt))
        seed_picks = rng.randint(0, len(variants), (bootstrap, len(variants)))
        samples = [bench.spell_draws(gt, bench.pm.label_codes(p), picks) for p in variants]
        draws.append(np.take_along_axis(np.array(samples).T, seed_picks, axis=1).mean(axis=1))
        points.append(np.mean([bench.spell_draws(gt, bench.pm.label_codes(p), np.arange(n_gt)[None])[0]
                               for p in variants]))
        dead_f1.append(np.mean([bench.calibrate_dead.score(p == 'D', truth == 'D', truth != 'X')['F1']
                                for p in variants]))
    lo, hi = np.percentile(np.mean(draws, axis=0), bench.pm.BOOTSTRAP_PERCENTILES)
    return dict(spell=float(np.mean(points)), low=float(lo), high=float(hi), dead_f1=float(np.mean(dead_f1)))


def run(dataset, idsse_dir, speed, seeds, seed_start, bootstrap, pipelines):
    if seeds < 1 or bootstrap < 1:
        raise ValueError('seeds and bootstrap must be positive')
    preds, changed, masked, finite_changed = {}, 0, 0, 0
    for case, before in cases(dataset, idsse_dir, speed):
        g, players, ball, team, truth, dead, graded, pitch = case
        old, new = before[:, :, 2], players[:, :, 2]
        changed += int(np.sum(~((old == new) | (np.isnan(old) & np.isnan(new)))))
        masked += int(np.sum(np.isfinite(old) & np.isnan(new)))
        both = np.isfinite(old) & np.isfinite(new)
        finite_changed += int(np.sum(old[both] != new[both]))
        spans = bench.pm.valid_runs(bench.pm.label_codes(truth))
        balls = {'as is': [ball], 'degraded': [bench.degrade(
            ball, players, dead, .45, 1.5, 0., 1000 * g + s, graded, 0., pitch=pitch)
            for s in range(seed_start, seed_start + seeds)]}
        for version, p in [('legacy-9e2a4b6', before), ('continuity', players)]:
            for kind, variants in balls.items():
                for name in pipelines:
                    preds[(g, 'start' if dataset == 'metrica' else 'status', kind, name + '/' + version)] = (
                        truth, [bench.PIPELINES[name](p, b, team, spans, dead, pitch=pitch) for b in variants])
        print(f'{dataset}: game {g} done', file=sys.stderr, flush=True)
    prediction_arrays, different_arrays, different_labels = 0, 0, 0
    for key, (_, variants) in preds.items():
        if not key[-1].endswith('/continuity'):
            continue
        previous = preds[(*key[:-1], key[-1].replace('/continuity', '/legacy-9e2a4b6'))][1]
        for before, after in zip(previous, variants):
            prediction_arrays += 1
            different_arrays += int(not np.array_equal(before, after))
            different_labels += int(np.sum(before != after))
    rows = []
    for name in pipelines:
        before, after = name + '/legacy-9e2a4b6', name + '/continuity'
        for (anchor, kind), (point, lo, hi, per_game) in bench.compare(preds, before, after, bootstrap).items():
            rows.append(dict(pipeline=name, truth=anchor, ball=kind, games=len(per_game),
                             before=absolute_metrics(preds, before, kind, bootstrap),
                             after=absolute_metrics(preds, after, kind, bootstrap),
                             difference=point, low=lo, high=hi))
    return dict(dataset=dataset, speed=speed if dataset == 'idsse' else 'positions',
                baseline='9e2a4b6', seeds=seeds, seed_start=seed_start, bootstrap=bootstrap,
                bootstrap_seed=bench.pm.BOOTSTRAP_SEED, missing=.45, mean_gap_s=1.5, crowd=0., dead_missing=0.,
                parameters=dict(radius=bench.possession.CONTROL_RADIUS, change_frames=bench.possession.CHANGE_FRAMES,
                                max_interp=bench.possession.MAX_INTERP, max_gap=bench.possession.MAX_GAP),
                speed_cells_changed=changed, formerly_finite_now_unknown=masked,
                retained_finite_changed=finite_changed, prediction_arrays=prediction_arrays,
                different_prediction_arrays=different_arrays, different_labels=different_labels, rows=rows)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--dataset', choices=('metrica', 'idsse'), required=True)
    ap.add_argument('--idsse-dir', default=os.path.join(bench.ROOT, '..', 'idsse-data'))
    ap.add_argument('--speed', choices=('provider', 'positions'), default='provider')
    ap.add_argument('--seeds', type=int, default=5)
    ap.add_argument('--seed-start', type=int, default=0)
    ap.add_argument('--bootstrap', type=int, default=1000)
    ap.add_argument('--pipelines', nargs='+', choices=tuple(bench.PIPELINES), default=['v1', 'v2', 'radio'])
    a = ap.parse_args()
    print(json.dumps(run(a.dataset, a.idsse_dir, a.speed, a.seeds, a.seed_start, a.bootstrap, a.pipelines), indent=2))
