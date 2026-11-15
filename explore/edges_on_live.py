"""Step 0 of the next #32 candidate: ADR-010's stop model and the fixes its review listed, on top of the live model.

Usage: python explore/edges_on_live.py [--seeds-metrica 10] [--seeds-idsse 5] [--draws 1000]
Open data only (AGENTS.md), selection matches only (Metrica 2-3, IDSSE 1-5), LOMO: the reserve stays untouched.
A throwaway prototype, kept to reproduce its row of docs/EXPERIMENTOS.md.

Per left-out match, trained on the other 6: the live model of main's recipe (calibrate_live.py: 63 leaves, lambda 10,
v2 stops) and each stop-model variant. Scored on top of that live model against main (v2 stops), with
decision_function, as calibrate_live.py --select. Every variant keeps ADR-010's chosen recipe (edge model, 3 s
windows, 31 leaves) without the restart team, which is worth nothing on top of the live model
(explore/oracles_live.py). Each one adds a fix to the one before:
- normalised weights: ADR-010's per-match weights sum to the number of matches, so with ~10^6 rows a leaf needs far
  more than 200 rows to reach sklearn's minimum hessian (the review's "weights that do not shrink the leaves");
- bank weights: Metrica and IDSSE weigh the same (each match did: IDSSE 5 against 2);
- the free kicks of IDSSE start at the foul (Metrica's convention, the contest's), with the kinds on the kicks' clock
  (explore/edge_clock.py: 87 unknown stops instead of 161);
- noisy players: each training ball also with calibrate_live.TRAIN_NOISE;
- out-of-fold kinds in the edge rows, and one more IDSSE training ball hidden from the model.
"""
import argparse
import collections
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "explore"))
_argv, sys.argv = sys.argv, sys.argv[:1]  # possession, calibrate_dead and idsse_dead_labels read sys.argv[1] at import
import bench  # noqa: E402
import calibrate_edges as CE  # noqa: E402
import calibrate_live as CL  # noqa: E402
import edge_clock as EC  # noqa: E402
import oracles as O  # noqa: E402
import possession as P  # noqa: E402
sys.argv = _argv

pm = bench.pm
FPS = P.FPS
FREE_KICK = P.KINDS.index("FREE KICK")
WINDOW, EDGE_LEAVES = 3 * FPS, 31  # edges_choice.json (ADR-010)
LIVE_LEAVES, LAM = 63, 10  # live_choice.json (ADR-014)
VARIANTS = {
    "ADR-010 recipe": dict(),
    "+ normalised weights": dict(norm=True),
    "+ bank weights": dict(norm=True, bank=True),
    "+ free kicks from the foul": dict(norm=True, bank=True, foul=True),
    "+ noisy players": dict(norm=True, bank=True, foul=True, noise=True),
    "+ out-of-fold kinds, hidden ball": dict(norm=True, bank=True, foul=True, noise=True, oof=True, hide=True),
}


def rowset(v):
    return v.get("foul", False), v.get("noise", False), v.get("hide", False)


def foul_fix(game, match, h):
    """IDSSE half: its true stops with the kinds on the kicks' clock, and its D with each free kick starting at the
    foul, as explore/edge_clock.py finds them. ([(a, b, kind)], dead)"""
    path = CE.idsse_files()[match[1] - 1]
    restarts = CE.restart_frames(path)
    section = sorted(restarts)[h]
    events = restarts[section]
    ev = np.array([f for f, _ in events], dtype=int)
    kk = EC.kicks(game.ball, pitch=game.pitch)
    gaps = [int(ev[i]) - k for k in (EC.at(kk, b) for _, b, _ in game.kinds) if k is not None
            for i in [EC.nearest(ev, k, 20 * FPS)] if i is not None]
    gap = int(np.median(gaps)) if gaps else 0
    fouls = np.array(EC.infringements(path)[section], dtype=int) - gap
    dead, kinds = game.dead.copy(), []
    for j, (a, b, _) in enumerate(game.kinds):
        kick = EC.at(kk, b)
        i = EC.nearest(ev - gap, kick if kick is not None else b, 2 * FPS)
        k = -1 if i is None else events[i][1]
        if k == FREE_KICK:
            foul = EC.at(fouls, a)
            if foul is not None and (game.kinds[j - 1][1] if j else 0) <= foul < b - 1:
                dead[min(a, foul):max(a, foul)] = foul < a  # earlier: D from the foul; later: live until it
                a = foul
        kinds.append((a, b, k))
    return kinds, dead


def rowsets(match, games):
    """{(foul, noise, hide): [Rows]} of one match with calibrate_edges' training balls."""
    sets = collections.defaultdict(list)
    for h, game in enumerate(games):
        fixed = game
        if match[0] == "idsse":
            kinds, dead = foul_fix(game, match, h)
            fixed = game._replace(kinds=kinds, dead=dead)
        for b in CE.TRAIN_BALLS[match[0]]:
            ball = CE.degraded(game, 1000 * game.g + b["seed"], **{k: x for k, x in b.items() if k != "seed"})
            base = CE.game_rows(game, ball)
            clean = CE.game_rows(fixed, ball) if fixed is not game else base
            noisy = CE.game_rows(fixed._replace(players=CL.players_of(game, b["seed"], CL.TRAIN_NOISE)), ball)
            sets[(False, False, False)].append(base)
            sets[(True, False, False)].append(clean)
            sets[(True, True, False)] += [clean, noisy]
            sets[(True, True, True)] += [clean, noisy]
        if match[0] == "idsse":  # the ball hidden from the model, as in Metrica: v2 still sees it
            b = CE.TRAIN_BALLS["idsse"][0]
            ball = CE.degraded(game, 1000 * game.g + b["seed"], **{k: x for k, x in b.items() if k != "seed"})
            r = CE.game_rows(fixed._replace(match=("hidden", match[1])), ball)
            sets[(True, True, True)].append(r._replace(match=match))
    return sets


def weights_of(v):
    """calibrate_edges.weights (each match the same), normalised to mean 1, or each bank the same."""
    def f(rows, n):
        count, matches = collections.Counter(), collections.defaultdict(set)
        for r in rows:
            count[r.match] += n(r)
            matches[r.match[0]].add(r.match)
        share = (lambda m: len(matches[m[0]])) if v.get("bank") else (lambda m: 1)
        w = np.concatenate([np.full(n(r), 1.0 / (count[r.match] * share(r.match))) for r in rows])
        return w * len(w) / w.sum() if v.get("norm") else w
    return f


def fit_kinds(rows, w_fn):
    from sklearn.ensemble import HistGradientBoostingClassifier
    S = np.vstack([r.S for r in rows])
    k = np.concatenate([r.kind for r in rows])
    w = w_fn(rows, lambda r: len(r.kind))
    ok = k >= 0
    clf = HistGradientBoostingClassifier(max_iter=50, max_leaf_nodes=8, min_samples_leaf=10, random_state=0,
                                         early_stopping=False).fit(S[ok], k[ok], sample_weight=w[ok])
    return CE.export_kinds(clf)


def fit_edges(rows, kinds_of, w_fn):
    """calibrate_edges.fit_edges with a weights function and the kinds that fill each Rows' kind column."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    offset, kind_col = P.EDGE_FEATURES.index("offset"), P.EDGE_FEATURES.index("kind")

    def inside(r):
        return (r.E[:, offset] >= -WINDOW) & (r.E[:, offset] < WINDOW)

    w = w_fn(rows, lambda r: int(inside(r).sum()))
    X, y = [], []
    for r in rows:
        m = inside(r)
        E = r.E[m].copy()
        E[:, kind_col] = P.classify(r.S, kinds_of(r))[r.stop[m]]
        X.append(E)
        y.append(r.y[m])
    clf = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1, max_leaf_nodes=EDGE_LEAVES, min_samples_leaf=200,
                                         random_state=0, early_stopping=False).fit(np.vstack(X), np.concatenate(y),
                                                                                   sample_weight=w)
    return CE.export(clf)


def train(sets, matches, v):
    rows = [r for m in matches for r in sets[m][rowset(v)]]
    w = weights_of(v)
    kinds = fit_kinds(rows, w)
    if v.get("oof"):
        oof = {m: fit_kinds([r for x in matches if x != m for r in sets[x][rowset(v)]], w) for m in matches}
        edge = fit_edges(rows, lambda r: oof[r.match], w)
    else:
        edge = fit_edges(rows, lambda r: kinds, w)
    return {"mode": "model", "window": WINDOW, "team_radius_cm": 0, "type": kinds, "edge": edge}


def held_out(games, models, scorer, switch, seeds):
    """{g: (truth codes, {name: [label codes per seed]})}: main (v2 stops) and each stop model, on the live model."""
    out = {}
    for game in games:
        truth = CL.truth_of(game)
        gt = pm.label_codes(truth)
        spans = pm.valid_runs(gt)
        by = {}
        for s in seeds:
            ball = CE.degraded(game, 1000 * game.g + s)
            ev = bench.radio_evidence(game.players, ball, game.team, pitch=game.pitch)
            v2 = P.dead_mask_v2(game.players, ball)
            F = P.frame_features(game.players, ball, game.pitch)
            for name, model in [("main", None)] + list(models.items()):
                dead = v2 if model is None else P.refine(v2, game.players, ball, game.team, spans, model, game.pitch, F)[0]
                FH, FA = P.live_features(game.players, ball, game.team, ev, dead, spans, game.pitch)
                by.setdefault(name, []).append(pm.label_codes(P.segment_live(dead, scorer(FH) - scorer(FA), spans, switch)))
        out[game.g] = (gt, by)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seeds-metrica", type=int, default=10)
    ap.add_argument("--seeds-idsse", type=int, default=5)
    ap.add_argument("--draws", type=int, default=1000)
    a = ap.parse_args()
    seeds = {"metrica": range(a.seeds_metrica), "idsse": range(a.seeds_idsse)}
    t0 = time.time()
    games = {m: CE.load(m) for m in CE.SELECTION}
    sets = {m: rowsets(m, games[m]) for m in CE.SELECTION}
    print(f"stop rows: {sum(len(r.y) for m in sets for r in sets[m][(True, True, True)])} in the largest set "
          f"({time.time() - t0:.0f} s)", flush=True)
    live_rows = {m: [(m, *CL.game_rows(g)) for g in games[m]] for m in CE.SELECTION}
    print(f"live rows ({time.time() - t0:.0f} s)", flush=True)
    switch = CL.switch_of(LAM)
    per = {"metrica": {}, "idsse": {}}
    counts = {name: collections.defaultdict(lambda: np.zeros(9)) for name in list(VARIANTS) + ["plan B"]}
    for held in CE.SELECTION:
        others = [m for m in CE.SELECTION if m != held]
        scorer = CL.sklearn_scorer(CL.fit([r for m in others for r in live_rows[m]], LIVE_LEAVES))
        models = {name: train(sets, others, v) for name, v in VARIANTS.items()}
        base_rows = [r for m in others for r in sets[m][(False, False, False)]]
        kinds0 = CE.fit_kinds(base_rows)
        lead, trim = CE.plan_b_of(base_rows, kinds0)
        models["plan B"] = {"mode": "planb", "window": CE.W_MAX, "team_radius_cm": 0, "type": kinds0, "lead": lead,
                            "trim": trim}
        print(f"  left out {held}: trained ({time.time() - t0:.0f} s)", flush=True)
        per[held[0]].update(held_out(games[held], models, scorer, switch, seeds[held[0]]))
        if held == CE.SELECTION[0]:  # main is calibrate_live.py's pipeline, frame by frame
            g0 = games[held][0]
            ref = CL.score([g0], {"m": (scorer, switch)}, seeds[held[0]][:1], anchors={"start"})[(g0.g, "start", "degraded", "m")]
            assert (pm.label_codes(ref[1][0]) == per["metrica"][g0.g][1]["main"][0]).all(), "main differs"
        for name, model in models.items():
            for key, c in CE.stop_counts(games[held], model, CE.SEEDS["select"]).items():
                counts[name][key] += c
        print(f"  left out {held}: scored ({time.time() - t0:.0f} s)", flush=True)

    names = list(VARIANTS) + ["plan B"]
    print(f"\npaired spellF1 difference against main (v2 stops) on the LOMO live model, 5-95% ({a.draws} draws)")
    print(f"  {'variant':34} {'Metrica':>27} {'IDSSE':>27} {'mean':>8}")
    for name in names:
        cells, means = [], []
        for bench_name in ("metrica", "idsse"):
            p, lo, hi, g = O.paired(per[bench_name], "main", name, a.draws)
            cells.append(f"{p:+.4f} [{lo:+.4f}, {hi:+.4f}] {sum(d > 0 for d in g.values())}/{len(g)}")
            means.append(p)
        print(f"  {name:34} {cells[0]:>27} {cells[1]:>27} {np.mean(means):+8.4f}", flush=True)
    for name in names:
        CE.report_stops(counts[name], f"left-out games, {name}")
    print(f"\ndone in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
