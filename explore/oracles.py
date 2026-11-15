"""Oracles on the open-data benches: how much each piece of the pipeline could still give (step 0 of #32).

Usage: python explore/oracles.py [--seeds-metrica 10] [--seeds-idsse 5] [--draws 1000] [--only metrica|idsse]
Open data only (AGENTS.md): Metrica sample-data (data/) and IDSSE (../idsse-data, as explore/idsse_bench.py).

Each oracle replaces one piece of the pipeline in main (dead_mask_v2 with the ADR-009 evidence and change rule)
with the truth, on the bench's degraded ball (45% of live frames without it, 1.5 s gaps), and scores the result
with the official scorer's pieces (bench.spell_draws). Rows fix one kind of D error: missing stops, false stops,
the start or the end edge of the found ones, or all of D. Columns change the evidence: the true team at the start
of every live stretch (#34), the full ball, or the true team on every live frame. The baseline is checked frame by
frame against bench.pipeline_radio. An oracle is a ceiling, not an expected gain.
"""
import argparse
import glob
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "explore"))
_argv, sys.argv = sys.argv, sys.argv[:1]  # possession and calibrate_dead read sys.argv[1] at import
import bench  # noqa: E402
import calibrate_dead  # noqa: E402
import idsse_bench  # noqa: E402
import possession  # noqa: E402
sys.argv = _argv

pm = bench.pm
runs = possession.runs
FPS = bench.FPS
N, GAP = possession.CHANGE_FRAMES, possession.MAX_GAP
D_ROWS = ("v2", "+missing stops", "-false stops", "start edge", "end edge", "edges", "true D")
EV_COLS = ("radio", "radio + restart team", "full ball", "full ball + restart team", "live perfect")


def confirm(evidence, initial=None):
    """possession.confirm_changes (ADR-001, #31) with an optional starting team: the oracle of #34."""
    out = np.empty(len(evidence), dtype=object)
    current = initial or next((e for e in evidence if e), "H")
    run_start = last_seen = None
    for i, e in enumerate(evidence):
        if e == current:
            run_start = None
        elif e:
            if run_start is None or i - last_seen - 1 > GAP:
                run_start = i
            last_seen = i
            if i - run_start + 1 >= N:
                out[run_start:i] = e
                current, run_start = e, None
        out[i] = current
    return out


def segment(dead, ev, spans, start_team=None):
    """bench.segment with the ADR-009 change rule; start_team (the truth) seeds each live stretch."""
    labels = np.full(len(dead), "X", dtype=object)
    for a, b in spans:
        labels[a:b] = np.where(dead[a:b], "D", "X")
        for s, e in runs(~dead[a:b]):
            init = None
            if start_team is not None:
                t = start_team[a + s:a + e]
                k = np.flatnonzero((t == "H") | (t == "A"))
                init = t[k[0]] if len(k) else None
            labels[a + s:a + e] = confirm(ev[a + s:a + e], init)
    return labels


def live_perfect(dead, truth, spans):
    """Oracle: the predicted D, and the true team everywhere else (carried over true D frames)."""
    team = np.where((truth == "H") | (truth == "A"), truth, "").astype(object)
    i = np.arange(len(team))
    prev = np.maximum.accumulate(np.where(team != "", i, -1))
    nxt = np.minimum.accumulate(np.where(team != "", i, len(team))[::-1])[::-1]
    filled = np.where(prev >= 0, team[np.maximum(prev, 0)], team[np.minimum(nxt, len(team) - 1)])
    labels = np.full(len(dead), "X", dtype=object)
    for a, b in spans:
        labels[a:b] = np.where(dead[a:b], "D", filled[a:b])
    return labels


def cover(mask, a, b):
    return float(mask[a:b].mean()) if b > a else 0.0


def extent(pred_runs, a, b):
    """(first start, last end) of the predicted runs that overlap [a, b)."""
    over = [(c, d) for c, d in pred_runs if c < b and d > a]
    return min(c for c, _ in over), max(d for _, d in over)


def d_variants(pred, true):
    """The predicted D with one kind of error fixed by the truth: a true stop is found when the
    prediction covers half of it; a predicted stop is false when the truth covers less than half."""
    tr, pr = runs(true), runs(pred)
    found = [(a, b) for a, b in tr if cover(pred, a, b) >= 0.5]
    add = pred.copy()
    for a, b in tr:
        if cover(pred, a, b) < 0.5:
            add[a:b] = True
    drop = pred.copy()
    for a, b in pr:
        if cover(true, a, b) < 0.5:
            drop[a:b] = False
    hull = [(a, b) + extent(pr, a, b) for a, b in found]  # the predicted stop(s) over each found one
    start, end, edges = pred.copy(), pred.copy(), pred.copy()
    for a, b, c, d in hull:
        for m in (start, end, edges):
            m[c:d] = False
    for a, b, c, d in hull:
        start[a:max(d, a + 1)] = True  # the true start, the predicted end
        end[c:max(b, c + 1)] = True  # the predicted start, the true end
        edges[a:b] = True
    return dict(zip(D_ROWS, (pred, add, drop, start, end, edges, true)))


def variants(players, ball_deg, ball_full, team, truth, dead_true, spans, *, pitch):
    """{(D row, evidence column): label codes} for one degraded ball, and the v2 mask on it."""
    dead_v2 = possession.dead_mask_v2(players, ball_deg)
    ev = bench.radio_evidence(players, ball_deg, team, pitch=pitch)
    ev_full = bench.radio_evidence(players, ball_full, team, pitch=pitch)
    out = {}
    for row, dead in d_variants(dead_v2, dead_true).items():
        cols = {"radio": segment(dead, ev, spans), "radio + restart team": segment(dead, ev, spans, truth),
                "full ball": segment(dead, ev_full, spans),
                "full ball + restart team": segment(dead, ev_full, spans, truth),
                "live perfect": live_perfect(dead, truth, spans)}
        for col, labels in cols.items():
            out[(row, col)] = pm.label_codes(labels)
    return out, dead_v2


def first_team(labels, s, horizon=2 * FPS):
    """First H/A label in [s, s + horizon), or "" when the stretch stays D or X."""
    w = labels[s:s + horizon]
    k = np.flatnonzero((w == pm.H) | (w == pm.A))
    return "HA"[w[k[0]]] if len(k) else ""


def restarts_metrica(events):
    """[(dead_start, restart_frame, kind, team)] for the true stops of ADR-003 (calibrate_dead.restart_gaps)."""
    out = []
    for i, (typ, sub, s, _, per, side) in enumerate(events):
        if typ != "SET PIECE" and "GOAL KICK" not in sub:
            continue
        prev = max((e for e in events[:i] if e[4] == per and e[2] < s and e[0] != "CARD"), key=lambda e: e[3],
                   default=None)
        if prev is None:
            continue
        cap = np.inf if calibrate_dead.stops_play(prev[0], prev[1]) else calibrate_dead.MAX_DEAD_S * FPS
        if 0 < s - prev[3] <= cap:
            kind = "GOAL KICK" if "GOAL KICK" in sub else (sub.split("+")[0] or "SET PIECE")
            out.append((prev[3], s, kind, side))
    return out


def restarts_truth(truth, dead_true):
    """[(dead_start, restart_frame, "", team)] from a truth with D runs and owners (IDSSE)."""
    return [(a, b, "", truth[b]) for a, b in runs(dead_true) if b < len(truth) and truth[b] in ("H", "A")]


def stop_rows(restarts, dead_v2, preds, codes_true_d):
    """Per true stop: kind, seconds, found by v2, restart team right in the radio pipeline and with the
    true D, and for found stops the start and end offsets in seconds of the predicted hull (+ = late)."""
    rows, pr = [], runs(dead_v2)
    for a, s, kind, side in restarts:
        found = cover(dead_v2, a, s) >= 0.5
        c, d = extent(pr, a, s) if found else (np.nan, np.nan)
        rows.append((kind, (s - a) / FPS, found, first_team(preds, s) == side, first_team(codes_true_d, s) == side,
                     (c - a) / FPS, (d - s) / FPS))
    return rows


def paired(per_game, a, b, n_draws, seed=pm.BOOTSTRAP_SEED):
    """bench.compare on label codes: paired bootstrap of spellF1(b) - spellF1(a), games x seeds."""
    games, pooled = {}, []
    for g, (gt, by) in sorted(per_game.items()):
        n_gt = len(pm.possession_spells(gt, pm.valid_runs(gt)))
        rng = np.random.RandomState(seed + g)
        picks = rng.randint(0, n_gt, (n_draws, n_gt))
        pa, pb = by[a], by[b]
        seed_picks = rng.randint(0, len(pa), (n_draws, len(pa)))
        point = np.arange(n_gt)[None]
        diffs = [bench.spell_draws(gt, y, picks) - bench.spell_draws(gt, x, picks) for x, y in zip(pa, pb)]
        games[g] = float(np.mean([bench.spell_draws(gt, y, point)[0] - bench.spell_draws(gt, x, point)[0]
                                  for x, y in zip(pa, pb)]))
        pooled.append(np.take_along_axis(np.array(diffs).T, seed_picks, axis=1).mean(axis=1))
    lo, hi = np.percentile(np.mean(pooled, axis=0), pm.BOOTSTRAP_PERCENTILES)
    return float(np.mean(list(games.values()))), float(lo), float(hi), games


def collect(name, games, n_seeds, seed_of):
    """Run every variant on every game and seed.

    games: [(g, players, ball, team, truth, dead_true, graded, restarts, pitch)], with dead_true and graded
    exactly as bench.run (Metrica) and idsse_bench (IDSSE) build them, so the degraded balls match theirs.
    """
    per_game, stops, t0 = {}, [], time.time()
    for g, players, ball, team, truth, dead_true, graded, restarts, pitch in games:
        gt = pm.label_codes(truth)
        spans = pm.valid_runs(gt)
        by = {}
        for s in range(n_seeds):
            deg = bench.degrade(ball, players, dead_true, 0.45, 1.5, 0.0, seed_of(g, s), graded, pitch=pitch)
            out, dead_v2 = variants(players, deg, ball, team, truth, dead_true, spans, pitch=pitch)
            if s == 0 and g == games[0][0]:  # the baseline must be the bench's radio pipeline, frame by frame
                ref = pm.label_codes(bench.pipeline_radio(players, deg, team, spans, dead_true, pitch=pitch))
                assert (ref == out[("v2", "radio")]).all(), "baseline differs from bench.pipeline_radio"
            for k, v in out.items():
                by.setdefault(k, []).append(v)
            stops += stop_rows(restarts, dead_v2 & graded, out[("v2", "radio")], out[("true D", "radio")])
        per_game[g] = (gt, by)
        print(f"  {name} game {g}: {n_seeds} seeds, {time.time() - t0:.0f} s", flush=True)
    return per_game, stops


def report(name, per_game, stops, n_draws):
    n_gt = {g: len(pm.possession_spells(gt, pm.valid_runs(gt))) for g, (gt, _) in per_game.items()}
    point = {g: np.arange(k)[None] for g, k in n_gt.items()}
    mean = {}
    for key in next(iter(per_game.values()))[1]:
        mean[key] = np.mean([np.mean([bench.spell_draws(gt, p, point[g])[0] for p in by[key]])
                             for g, (gt, by) in per_game.items()])
    print(f"\n=== {name}: spellF1, mean over games and seeds (degraded ball, radio pipeline) ===")
    print(f"{'D':16}" + "".join(f"{c:>26}" for c in EV_COLS))
    for row in D_ROWS:
        print(f"{row:16}" + "".join(f"{mean[(row, c)]:26.3f}" for c in EV_COLS))
    base = ("v2", "radio")
    print(f"\n--- {name}: paired difference against v2 + radio, 5-95% ({n_draws} draws)")
    for key in [(r, "radio") for r in D_ROWS[1:]] + [("v2", c) for c in EV_COLS[1:]] + \
               [("true D", "radio + restart team"), ("true D", "full ball"), ("true D", "full ball + restart team")]:
        p, lo, hi, games = paired(per_game, base, key, n_draws)
        above = sum(d > 0 for d in games.values())
        print(f"  {key[0]:16} {key[1]:26} {p:+.3f} [{lo:+.3f}, {hi:+.3f}]  above 0 in {above}/{len(games)}")
    print(f"\n--- {name}: true stops (all seeds pooled)")
    a = np.array(stops, dtype=object)
    secs, found = a[:, 1].astype(float), a[:, 2].astype(bool)
    team_ok, team_ok_true = a[:, 3].astype(bool), a[:, 4].astype(bool)
    bins = [(0, 3), (3, 6), (6, 10), (10, 20), (20, 1e9)]
    print("  length (s)   share of stops   found by v2   restart team right: radio / with true D")
    for lo_s, hi_s in bins:
        m = (secs >= lo_s) & (secs < hi_s)
        if m.any():
            print(f"  {lo_s:>3}-{hi_s if hi_s < 1e9 else '':<5}   {m.mean():14.0%}   {found[m].mean():11.0%}"
                  f"   {team_ok[m].mean():17.0%} / {team_ok_true[m].mean():.0%}")
    print(f"  all          {1:14.0%}   {found.mean():11.0%}   {team_ok.mean():17.0%} / {team_ok_true.mean():.0%}")
    kinds = a[:, 0]
    if any(kinds):
        print("  kind          share   median s   found by v2   restart team right: radio / with true D")
        for k in sorted(set(kinds), key=lambda k: -(kinds == k).sum()):
            m = kinds == k
            print(f"  {k:12} {m.mean():6.0%}   {np.median(secs[m]):8.1f}   {found[m].mean():11.0%}"
                  f"   {team_ok[m].mean():17.0%} / {team_ok_true[m].mean():.0%}")
    off_s, off_e = a[:, 5].astype(float), a[:, 6].astype(float)
    print("  edges of found stops (s, + = late): median, 10-90%, share within 0.5 s / 1 s")
    groups = [("all", found)] + ([(k, found & (kinds == k)) for k in sorted(set(kinds), key=lambda k: -(kinds == k).sum())]
                                 if any(kinds) else [])
    for k, m in groups:
        if m.sum() < 5:
            continue
        parts = []
        for name_, off in (("start", off_s[m]), ("end", off_e[m])):
            p10, p50, p90 = np.percentile(off, [10, 50, 90])
            parts.append(f"{name_} {p50:+5.2f} [{p10:+5.2f}, {p90:+5.2f}] {np.mean(abs(off) <= 0.5):4.0%} / "
                         f"{np.mean(abs(off) <= 1):4.0%}")
        print(f"  {k:12} " + "   ".join(parts))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seeds-metrica", type=int, default=10)
    ap.add_argument("--seeds-idsse", type=int, default=5)
    ap.add_argument("--draws", type=int, default=1000)
    ap.add_argument("--only", choices=("metrica", "idsse"))
    a = ap.parse_args()
    if a.only != "idsse":
        games = []
        for g in (1, 2, 3):
            players, ball, team, events, pitch = bench.load_game(g)
            dead = calibrate_dead.dead_labels([e[:5] for e in events], len(ball))
            truth = bench.truth_labels(events, len(ball), dead, "start")
            graded = np.zeros(len(ball), bool)
            for first, last in calibrate_dead.halves([e[:5] for e in events]):
                graded[first:last + 1] = True
            games.append((g, players, ball, team, truth, dead, graded, restarts_metrica(events), pitch))
        per_game, stops = collect("metrica", games, a.seeds_metrica, lambda g, s: 1000 * g + s)
        report("Metrica (3 games)", per_game, stops, a.draws)
        del per_game, games
    if a.only != "metrica":
        games = []
        files = sorted(glob.glob(os.path.join(ROOT, "..", "idsse-data", "DFL_04_03_positions_raw_observed_*.xml")))
        for m, path in enumerate(files):
            for h, (section, players, ball, team, truth, _, pitch) in enumerate(idsse_bench.load(path, "provider")):
                dead = truth == "D"
                games.append((10 * (m + 1) + h, players, ball, team, truth, dead, truth != "X",
                              restarts_truth(truth, dead), pitch))
        per_game, stops = collect("idsse", games, a.seeds_idsse, lambda g, s: 1000 * g + s)
        report(f"IDSSE ({len(files)} matches, {len(games)} halves)", per_game, stops, a.draws)
