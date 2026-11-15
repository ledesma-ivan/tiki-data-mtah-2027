"""Stop model of ADR-010 (#32 and #34): trains, picks and exports it, on open data only.

Usage:
  python calibrate_edges.py --select    LOMO over the 7 selection matches (Metrica Games 2-3, IDSSE 1-5): every
                                        recipe against the radio pipeline; the best goes to edges_choice.json
  python calibrate_edges.py --confirm   the chosen recipe, trained on the selection, on the reserve (Metrica Game 1,
                                        IDSSE 6-7): ADR-011's conditions, the ball kept on the pitch and NOISE
  python calibrate_edges.py --final     the chosen recipe trained on the 10 matches -> stops_model.json
  python calibrate_edges.py --identity  stops_model.json that changes nothing, while no candidate is confirmed
Training needs requirements-train.txt (scikit-learn); possession.py runs without it. Open data only (AGENTS.md):
Metrica sample-data (data/) and IDSSE (../idsse-data, revision a715a38). Nothing here reads BAR-ATH or the public
window. The ball is learned from IDSSE only: in Metrica it is hidden from the model (ADR-010).
"""
import collections
import glob
import json
import os
import re
import sys

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "explore"))
_argv, sys.argv = sys.argv, sys.argv[:1]  # possession, calibrate_dead and idsse_dead_labels read sys.argv[1] at import
import bench  # noqa: E402
import calibrate_dead  # noqa: E402
import idsse_bench  # noqa: E402
import idsse_dead_labels  # noqa: E402
import oracles  # noqa: E402
import possession as P  # noqa: E402
sys.argv = _argv

pm = bench.pm
FPS = P.FPS
SCALE = 1_000_000  # leaf values in millionths of the raw score
IDSSE = os.path.join(ROOT, "..", "idsse-data")
DFL_KINDS = {"ThrowIn": "THROW IN", "FreeKick": "FREE KICK", "GoalKick": "GOAL KICK", "CornerKick": "CORNER KICK",
             "KickOff": "KICK OFF", "Penalty": "OTHER", "RefereeBall": "OTHER"}
W_MAX = 5 * FPS  # widest window of the recipes: rows are built once and cut to each window
STEP = 2  # every other frame of a window trains the edge model: the signals are smooth
# Training balls: Metrica's only sets the v2 stops (the model never sees it); IDSSE's spans what we do not know
# of the ATD with levels fixed without the public GT: 0, 20 and 45% missing with the ball in play and 0 and 50% in the
# stops (ADR-033; it replaces the 6.5-45% and 0-34% of ADR-002, measured on the public window).
TRAIN_BALLS = {"metrica": [dict(seed=s) for s in (100, 101)],
               "idsse": [dict(seed=100 + i, live_missing=live, dead_missing=dead)
                         for i, (live, dead) in enumerate((v, d) for v in (0.0, 0.2, 0.45) for d in (0.0, 0.5))]}
DEFAULT = dict(live_missing=0.45, mean_gap_s=1.5, crowd=0.0, dead_missing=0.0)

Game = collections.namedtuple("Game", "g match players ball team truths dead graded kinds pitch")


# -- open data -------------------------------------------------------------------------------------

def load_metrica(g, truth_variant="A"):
    """[Game] for Sample Game g: the truth from the events (ADR-005, both anchors), D from ADR-003."""
    players, ball, team, events, pitch = bench.load_game(g)
    n = len(ball)
    dead = calibrate_dead.dead_labels([e[:5] for e in events], n)
    graded = np.zeros(n, bool)
    for first, last in calibrate_dead.halves([e[:5] for e in events]):
        graded[first:last + 1] = True
    truths = {anchor: bench.truth_labels(events, n, dead, anchor, variant=truth_variant) for anchor in ("start", "end")}
    kinds = [(a, b, P.KINDS.index(k) if k in P.KINDS else P.KINDS.index("OTHER"))
             for a, b, k, _ in oracles.restarts_metrica(events)]
    return [Game(g, ("metrica", g), players, ball, team, truths, dead, graded, kinds, pitch)]


def idsse_files():
    return sorted(glob.glob(os.path.join(IDSSE, "DFL_04_03_positions_raw_observed_*.xml")))


def restart_frames(path):
    """{section: [(frame, KINDS index)]} of the DFL restart events on the ball frames' clock, cached next to the file."""
    cache = path + ".restarts.json"
    if os.path.exists(cache):
        with open(cache) as f:
            return json.load(f)
    match = re.search(r"DFL-MAT-(\w+)\.xml$", path).group(1)
    events = idsse_dead_labels.load_events(glob.glob(os.path.join(IDSSE, f"DFL_03_02_events_raw_*{match}.xml"))[0])
    out = {section: [(int(np.searchsorted(t, et)), P.KINDS.index(DFL_KINDS[k])) for et, k, _, _ in events
                     if k in DFL_KINDS and t[0] <= et <= t[-1]]
           for section, (t, _, _) in idsse_dead_labels.load_ball(path).items()}
    with open(cache, "w") as f:
        json.dump(out, f)
    return out


def match_kinds(stops, restarts, tolerance=2 * FPS):
    """[(a, b, kind)]: each stop takes the kind of the restart nearest its end b within tolerance frames (the
    earlier on ties), or -1 when there is none."""
    out = []
    for a, b in stops:
        near = [(abs(f - b), f, k) for f, k in restarts if abs(f - b) <= tolerance]
        out.append((a, b, min(near)[2] if near else -1))
    return out


def load_idsse(m, speed="provider"):
    """[Game] per half of IDSSE match m (file name order, from 1): the truth of BallStatus and BallPossession.
    speed: "provider" (as possession.py reads the ATD's) or "positions" (as the Metrica bench computes it)."""
    path = idsse_files()[m - 1]
    restarts = restart_frames(path)
    games = []
    for h, (section, players, ball, team, truth, _, pitch) in enumerate(idsse_bench.load(path, speed)):
        dead = truth == "D"
        games.append(Game(10 * m + h, ("idsse", m), players, ball, team, {"status": truth}, dead, truth != "X",
                          match_kinds(P.runs(dead), restarts[section]), pitch))
    return games


def load(match, speed="provider"):
    return load_metrica(match[1]) if match[0] == "metrica" else load_idsse(match[1], speed)


def degraded(game, seed, **kw):
    p = {**DEFAULT, **kw}
    return bench.degrade(game.ball, game.players, game.dead, p["live_missing"], p["mean_gap_s"], p["crowd"], seed,
                         game.graded, p["dead_missing"], pitch=game.pitch)


def spans_of(game):
    return pm.valid_runs(pm.label_codes(next(iter(game.truths.values()))))


# -- training rows -----------------------------------------------------------------------------------

Rows = collections.namedtuple("Rows", "match S kind pairs E stop y")


def game_rows(game, ball):
    """Training rows of one game and one degraded ball: the v2 stops of the graded spans as dead_mask_v2 finds
    them, their formation (S) and true kind (-1: no true stop under it, or unknown), the (true start, true end,
    v2 start, v2 end) of the found ones, and edge rows (E, kind column 0 until a classifier fills it) every STEP
    frames of a W_MAX window on each side of each edge, with their stop index and the true D."""
    seen = ball if game.match[0] == "idsse" else np.full_like(ball, np.nan)  # Metrica: the model never sees its ball
    F = P.frame_features(game.players, seen, game.pitch)
    xy = P.ball_position(seen, P.MAX_INTERP)
    v2 = P.dead_mask_v2(game.players, ball)
    true_stops = [(a, b, k) for a, b, k in game.kinds]
    S, kinds, pairs, E, stop, y = [], [], [], [], [], []
    for a, b in spans_of(game):
        stops = [(a + s, a + e) for s, e in P.runs(v2[a:b])]
        for j, (c, d) in enumerate(stops):
            prev_end = stops[j - 1][1] if j else a
            nxt = stops[j + 1][0] if j + 1 < len(stops) else b
            best = max(true_stops, key=lambda t: min(d, t[1]) - max(c, t[0]), default=None)
            found = best is not None and min(d, best[1]) - max(c, best[0]) >= 0.5 * (best[1] - best[0])
            S.append(P.stop_features(game.players, xy, game.team, c, d, game.pitch))
            kinds.append(best[2] if found else -1)
            pairs.append((best[0], best[1], c, d) if found else (-1, -1, c, d))
            for lo, hi, edge, side in ((max(c - W_MAX, prev_end), min(c + W_MAX, d), c, 0),
                                       (max(d - W_MAX, c + 1), min(d + W_MAX, nxt), d, 1)):
                keep = np.arange(lo, hi)[::STEP]
                keep = keep[game.graded[keep]]
                if len(keep):
                    E.append(P.window_rows(F, lo, hi, edge, side, d - c, 0)[keep - lo])
                    stop.append(np.full(len(keep), len(S) - 1))
                    y.append(game.dead[keep])
    width = len(P.EDGE_FEATURES)
    return Rows(game.match, np.array(S, np.int64).reshape(-1, len(P.STOP_FEATURES)), np.array(kinds, np.int64),
                np.array(pairs, np.int64).reshape(-1, 4), np.vstack(E) if E else np.zeros((0, width), np.int64),
                np.concatenate(stop) if stop else np.zeros(0, np.int64), np.concatenate(y) if y else np.zeros(0, bool))


def match_rows(match, games=None):
    """Rows of every game of a match, with its training balls."""
    games = games or load(match)
    return [game_rows(g, degraded(g, 1000 * g.g + b["seed"], **{k: v for k, v in b.items() if k != "seed"}))
            for g in games for b in TRAIN_BALLS[match[0]]]


# -- models ------------------------------------------------------------------------------------------

def export(clf, k=0):
    """{"init", "trees"} of class column k of a fitted HistGradientBoostingClassifier: integer thresholds (the
    features are integers, so x <= t is x <= floor(t)) and leaf values in SCALE units."""
    trees = []
    for it in clf._predictors:
        nodes = it[k].nodes
        leaf = nodes["is_leaf"].astype(bool)
        trees.append({"feature": np.where(leaf, -1, nodes["feature_idx"]).astype(np.int64),
                      "threshold": np.where(leaf, 0, np.floor(nodes["num_threshold"])).astype(np.int64),
                      "left": nodes["left"].astype(np.int64), "right": nodes["right"].astype(np.int64),
                      "value": np.where(leaf, np.rint(nodes["value"] * SCALE), 0).astype(np.int64)})
    return {"init": int(np.rint(np.ravel(clf._baseline_prediction)[k] * SCALE)), "trees": trees}


def export_kinds(clf):
    """One exported part per KINDS entry; a kind the training never saw can never win."""
    cols = {int(c): i for i, c in enumerate(clf.classes_)}
    return [export(clf, cols[k]) if k in cols else {"init": -SCALE * 1000, "trees": []} for k in range(len(P.KINDS))]


def plan_b(pairs):
    """lead and trim per KINDS index: the median offsets (frames) of the v2 start and end against the true ones;
    pairs: [(true start, true end, v2 start, v2 end, kind)]. A kind without pairs keeps the v2 edges (0)."""
    lead, trim = [0] * len(P.KINDS), [0] * len(P.KINDS)
    for k in range(len(P.KINDS)):
        p = np.array([x for x in pairs if x[4] == k], np.int64).reshape(-1, 5)
        if len(p):
            lead[k], trim[k] = int(np.rint(np.median(p[:, 2] - p[:, 0]))), int(np.rint(np.median(p[:, 3] - p[:, 1])))
    return lead, trim


def weights(rows, n):
    """Every match weighs the same: rows of a match share 1 / its row count."""
    count = collections.Counter()
    for r in rows:
        count[r.match] += n(r)
    return np.concatenate([np.full(n(r), 1.0 / count[r.match]) for r in rows])


def fit_kinds(rows):
    from sklearn.ensemble import HistGradientBoostingClassifier
    S = np.vstack([r.S for r in rows])
    k = np.concatenate([r.kind for r in rows])
    w = weights(rows, lambda r: len(r.kind))
    ok = k >= 0
    clf = HistGradientBoostingClassifier(max_iter=50, max_leaf_nodes=8, min_samples_leaf=10, random_state=0,
                                         early_stopping=False).fit(S[ok], k[ok], sample_weight=w[ok])
    return export_kinds(clf)


def fit_edges(rows, kinds, window, leaves):
    """Exported edge model: rows inside the window, the kind column from the exported classifier."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    offset, kind_col = P.EDGE_FEATURES.index("offset"), P.EDGE_FEATURES.index("kind")
    X, y, w = [], [], []
    wt = weights(rows, lambda r: int(((r.E[:, offset] >= -window) & (r.E[:, offset] < window)).sum()))
    for r in rows:
        inside = (r.E[:, offset] >= -window) & (r.E[:, offset] < window)
        E = r.E[inside].copy()
        E[:, kind_col] = P.classify(r.S, kinds)[r.stop[inside]]
        X.append(E)
        y.append(r.y[inside])
    clf = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1, max_leaf_nodes=leaves, min_samples_leaf=200,
                                         random_state=0, early_stopping=False).fit(np.vstack(X), np.concatenate(y),
                                                                                   sample_weight=wt)
    return export(clf)


def plan_b_of(rows, kinds):
    pairs = []
    for r in rows:
        pred = P.classify(r.S, kinds)
        pairs += [(*p, k) for p, k in zip(r.pairs.tolist(), pred.tolist()) if p[0] >= 0]
    return plan_b(pairs)


def candidate(players, ball, team, spans, model, *, pitch):
    """possession.label's steps for one game, with this stop model: v2, refined stops and restart team, ADR-009."""
    dead, initial = P.refine(P.dead_mask_v2(players, ball), players, ball, team, spans, model, pitch=pitch)
    return bench.segment(dead, bench.radio_evidence(players, ball, team, pitch=pitch), spans, P.CHANGE_FRAMES, P.MAX_GAP, initial)


def to_json(model):
    """stops_model.json text: compact, with the trees as lists."""
    def part(p):
        return {"init": p["init"], "trees": [{k: v.tolist() for k, v in t.items()} for t in p["trees"]]}
    out = {k: v for k, v in model.items() if k not in ("edge", "type")}
    if "edge" in model:
        out["edge"] = part(model["edge"])
    out["type"] = [part(p) for p in model["type"]]
    return json.dumps(out, separators=(",", ":")) + "\n"


# -- selection, confirmation and the delivered model (ADR-010 "Cómo se mide", ADR-011) ----------------------

SELECTION = (("metrica", 2), ("metrica", 3)) + tuple(("idsse", m) for m in range(1, 6))
RESERVE = (("metrica", 1), ("idsse", 6), ("idsse", 7))
SEEDS = {"select": {"metrica": range(0, 10), "idsse": range(0, 5)},
         "confirm": {"metrica": range(20, 30), "idsse": range(20, 25)}}
SCENARIOS = {"default": {}, "--missing 0": dict(live_missing=0.0), "--missing 0.2": dict(live_missing=0.2),
             "--gap 3": dict(mean_gap_s=3.0), "--crowd 2": dict(crowd=2.0), "--dead-missing 0.5": dict(dead_missing=0.5),
             "--missing 0 --dead-missing 0.5": dict(live_missing=0.0, dead_missing=0.5)}  # no level from the GT (ADR-033)
CHOICE = os.path.join(ROOT, "edges_choice.json")


def recipes():
    """The 15 candidates of the selection: plan B and four edge models, each without the restart team and
    with it at 2 and 4 m."""
    out = {}
    for radius in (0, 200, 400):
        team = f", team {radius // 100} m" if radius else ""
        out["plan B" + team] = dict(mode="planb", window=W_MAX, leaves=0, radius=radius)
        for window in (3 * FPS, 5 * FPS):
            for leaves in (15, 31):
                out[f"model {window // FPS} s, {leaves} leaves{team}"] = dict(mode="model", window=window, leaves=leaves,
                                                                             radius=radius)
    return out


def train(rows, chosen):
    """{name: possession model dict} for the recipes in chosen, sharing the classifier and each edge fit."""
    kinds = fit_kinds(rows)
    lead, trim = plan_b_of(rows, kinds)
    edges, models = {}, {}
    for name, r in chosen.items():
        model = {"mode": r["mode"], "window": r["window"], "team_radius_cm": r["radius"], "type": kinds}
        if r["mode"] == "planb":
            model.update(lead=lead, trim=trim)
        else:
            key = (r["window"], r["leaves"])
            if key not in edges:
                edges[key] = fit_edges(rows, kinds, *key)
            model["edge"] = edges[key]
        models[name] = model
    return models


def score(games, models, seeds, scenario=None, noise=None, clip=False, anchors=None):
    """Labels per seed for "radio" (main) and each model: {(g, anchor, "degraded", name): (truth, [labels])},
    bench.compare's format. noise: a NOISE entry for the players; clip: the restored ball of the stops kept on
    the pitch (ADR-010, criterion 2, as explore/dead_v2_off_pitch.py)."""
    from player_noise import noisy_players
    preds = {}
    for game in games:
        for s in seeds:
            ball = degraded(game, 1000 * game.g + s, **(scenario or {}))
            if clip:
                restored = game.dead & np.isnan(game.ball[:, 0])
                ball[restored, :2] = np.clip(ball[restored, :2], 0.0, 1.0)
            players = game.players if noise is None else noisy_players(
                game.players, game.ball, game.team, np.random.default_rng(10_000 * game.g + s), pitch=game.pitch, **noise)
            F = P.frame_features(players, ball, game.pitch)
            ev = bench.radio_evidence(players, ball, game.team, pitch=game.pitch)
            v2 = P.dead_mask_v2(players, ball)
            for anchor, truth in game.truths.items():
                if anchors and anchor not in anchors:
                    continue
                spans = pm.valid_runs(pm.label_codes(truth))
                out = {"radio": bench.segment(v2, ev, spans, P.CHANGE_FRAMES, P.MAX_GAP)}
                for name, model in models.items():
                    dead, initial = P.refine(v2, players, ball, game.team, spans, model, game.pitch, F)
                    out[name] = bench.segment(dead, ev, spans, P.CHANGE_FRAMES, P.MAX_GAP, initial)
                for name, labels in out.items():
                    preds.setdefault((game.g, anchor, "degraded", name), (truth, []))[1].append(labels)
    return preds


def per_game(preds, name):
    """{(g, anchor): mean over seeds of spellF1(name) - spellF1(radio)}, the point value of bench.compare."""
    out = {}
    for (g, anchor, ball, nm), (truth, labels) in preds.items():
        if nm != name:
            continue
        gt = pm.label_codes(truth)
        point = np.arange(len(pm.possession_spells(gt, pm.valid_runs(gt))))[None]
        base = preds[(g, anchor, ball, "radio")][1]
        out[(g, anchor)] = float(np.mean([bench.spell_draws(gt, pm.label_codes(x), point)[0] -
                                          bench.spell_draws(gt, pm.label_codes(r), point)[0] for x, r in zip(labels, base)]))
    return out


def bench_means(diffs):
    """Mean difference per bench (Metrica with the truth from the event start, ADR-006) and their plain average
    (ADR-011): (metrica, idsse, both)."""
    m = [d for (g, anchor), d in diffs.items() if g < 10 and anchor == "start"]
    i = [d for (g, anchor), d in diffs.items() if g >= 10]
    return float(np.mean(m)), float(np.mean(i)), float((np.mean(m) + np.mean(i)) / 2)


def select():
    """LOMO over the 7 selection matches: each recipe is trained on 6 and scored on the one left out."""
    games = {m: load(m) for m in SELECTION}
    rows = {m: match_rows(m, games[m]) for m in SELECTION}
    every = recipes()
    diffs = {name: {} for name in every}
    counts = {name: collections.defaultdict(lambda: np.zeros(9)) for name in every}
    for held in SELECTION:
        models = train([r for m in SELECTION if m != held for r in rows[m]], every)
        preds = score(games[held], models, SEEDS["select"][held[0]], anchors={"start", "status"})
        for name in every:
            diffs[name].update(per_game(preds, name))
            for key, c in stop_counts(games[held], models[name], SEEDS["select"]).items():
                counts[name][key] += c
        print(f"  left out {held}: done", flush=True)
    table = sorted(((bench_means(d), name) for name, d in diffs.items()), key=lambda x: -x[0][2])
    print("\nselection (LOMO, default degraded ball): paired spellF1 difference against radio")
    print(f"  {'recipe':34} {'Metrica':>8} {'IDSSE':>8} {'mean':>8}")
    for (m, i, both), name in table:
        print(f"  {name:34} {m:+8.4f} {i:+8.4f} {both:+8.4f}")
    print("  per game: " + "  ".join(f"{g}{a[0]} {d:+.3f}" for (g, a), d in sorted(diffs[table[0][1]].items())))
    for _, name in table[:3]:
        report_stops(counts[name], f"selection, left-out games, {name}")
    (m, i, both), name = table[0]
    with open(CHOICE, "w") as f:
        json.dump({"recipe": name, **every[name], "metrica": round(m, 4), "idsse": round(i, 4), "mean": round(both, 4)},
                  f, indent=1)
        f.write("\n")
    print(f"\nchosen: {name} -> {os.path.basename(CHOICE)}")


def chosen():
    with open(CHOICE) as f:
        c = json.load(f)
    return c["recipe"], {k: c[k] for k in ("mode", "window", "leaves", "radius")}


def confirm():
    """The chosen recipe, trained on the selection, on the reserve with fresh seeds (ADR-010, ADR-011)."""
    name, recipe = chosen()
    rows = [r for m in SELECTION for r in match_rows(m)]
    model = train(rows, {name: recipe})[name]
    reserve = {m: load(m) for m in RESERVE}
    metrica, idsse = reserve[("metrica", 1)], reserve[("idsse", 6)] + reserve[("idsse", 7)]
    passed = []
    print(f"confirmation of {name!r}: Metrica Game 1 (seeds 20-29), IDSSE 6-7 (seeds 20-24); paired difference "
          "against radio, 5-95%, 1000 draws")
    for scen, kw in SCENARIOS.items():
        for bench_name, games, seeds in (("Metrica", metrica, SEEDS["confirm"]["metrica"]),
                                         ("IDSSE", idsse, SEEDS["confirm"]["idsse"])):
            for (anchor, _), (point, lo, hi, per) in bench.compare(score(games, {name: model}, seeds, kw), "radio", name,
                                                                   1000).items():
                ok = lo > 0 if scen == "default" else point > 0
                passed.append(ok)
                print(f"  {scen:32} {bench_name:7} {anchor:6} {point:+.4f} [{lo:+.4f}, {hi:+.4f}]  "
                      f"{sum(d > 0 for d in per.values())}/{len(per)} above 0  {'ok' if ok else 'FAILS'}", flush=True)
    for (anchor, _), (point, lo, hi, _) in bench.compare(score(metrica, {name: model}, SEEDS["confirm"]["metrica"],
                                                               clip=True), "radio", name, 1000).items():
        passed.append(point > 0)
        print(f"  {'ball of the stops on the pitch':32} Metrica {anchor:6} {point:+.4f} [{lo:+.4f}, {hi:+.4f}]  "
              f"{'ok' if point > 0 else 'FAILS'}", flush=True)
    from player_noise import NOISE
    for noise_name, kw in NOISE.items():
        for bench_name, games, seeds in (("Metrica", metrica, SEEDS["confirm"]["metrica"]),
                                         ("IDSSE", idsse, SEEDS["confirm"]["idsse"])):
            preds = score(games, {name: model}, seeds, noise=kw, anchors={"start", "status"})
            (_, _), (point, lo, hi, _) = next(iter(bench.compare(preds, "radio", name, 1000).items()))
            passed.append(point > 0)
            print(f"  {noise_name[:32]:32} {bench_name:7} {point:+.4f} [{lo:+.4f}, {hi:+.4f}]  "
                  f"{'ok' if point > 0 else 'FAILS'}", flush=True)
    report_stops(stop_counts(metrica + idsse, model, SEEDS["confirm"]), "stops of the reserve (first seed)")
    print(f"\n{'CONFIRMED' if all(passed) else 'NOT CONFIRMED'}: {sum(passed)}/{len(passed)} conditions")


def stop_counts(games, model, seeds):
    """{(bench, true kind): counts} on the first seed of each game, for report_stops: stops, v2 start and end
    within 0.5 s, the model's start and end within 0.5 s, found by v2, kind right, restart team right and named."""
    def hull(found_runs, a, b):
        """(first start, last end) of the runs over the true stop [a, b), if they cover half of it."""
        over = [(c, d) for c, d in found_runs if c < b and d > a]
        if over and sum(min(b, d) - max(a, c) for c, d in over) >= 0.5 * (b - a):
            return min(c for c, _ in over), max(d for _, d in over)
        return None

    # per true kind: stops, v2 start, v2 end, model start, model end, found by v2, kind right, team right, team named
    n = collections.defaultdict(lambda: np.zeros(9))
    for game in games:
        ball = degraded(game, 1000 * game.g + seeds[game.match[0]][0])
        truth = next(iter(game.truths.values()))
        spans = pm.valid_runs(pm.label_codes(truth))
        v2 = P.dead_mask_v2(game.players, ball)
        new, initial = P.refine(v2, game.players, ball, game.team, spans, model, game.pitch)
        xy = P.ball_position(ball, P.MAX_INTERP)
        v2_runs, new_runs = P.runs(v2), P.runs(new)
        for a, b, k in game.kinds:
            c = n[(game.match[0], k)]
            c[0] += 1
            old, now = hull(v2_runs, a, b), hull(new_runs, a, b)
            if old:
                c[1:3] += abs(old[0] - a) <= FPS // 2, abs(old[1] - b) <= FPS // 2
                c[5] += 1
                c[6] += P.classify(P.stop_features(game.players, xy, game.team, *old, game.pitch)[None], model["type"])[0] == k
            if now:
                c[3:5] += abs(now[0] - a) <= FPS // 2, abs(now[1] - b) <= FPS // 2
                restart = truth[min(b, len(truth) - 1)]
                if now[1] < len(truth) and restart in ("H", "A") and initial[now[1]]:
                    c[7:9] += initial[now[1]] == restart, 1
    return n


def report_stops(counts, title):
    """Edges within 0.5 s by bench and true kind, v2 against the model; the kind's accuracy and the restart
    team's (ADR-010 "Se reporta además")."""
    print(f"\n{title}: edges within 0.5 s, v2 -> model (share of the true stops); kind right (of the found by v2); "
          "restart team right (of the named)")
    for bench_name, k in sorted(counts):
        c = counts[(bench_name, k)]
        print(f"  {bench_name:7} {P.KINDS[k] if k >= 0 else 'unknown':12} {int(c[0]):4} stops  start {c[1] / c[0]:4.0%} -> "
              f"{c[3] / c[0]:4.0%}  end {c[2] / c[0]:4.0%} -> {c[4] / c[0]:4.0%}  kind {c[6] / max(c[5], 1):4.0%}  "
              f"team {c[7] / max(c[8], 1):4.0%} of {int(c[8])}")


def identity_model():
    """A stop model that leaves dead_mask_v2's stops as they are and names no restart team: the pipeline of
    ADR-009, byte for byte, while no ADR-010 candidate is confirmed."""
    zero = [0] * len(P.KINDS)
    return {"mode": "planb", "window": W_MAX, "team_radius_cm": 0, "lead": zero, "trim": list(zero),
            "type": [{"init": 0, "trees": []} for _ in P.KINDS]}


def write(model, name):
    import hashlib
    text = to_json(model)
    with open(P.MODEL_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"wrote {os.path.basename(P.MODEL_PATH)} ({name}): {len(text)} bytes, "
          f"sha256 {hashlib.sha256(text.encode()).hexdigest()}")


def final():
    """The chosen recipe trained on the 10 matches: the delivered stops_model.json, with its sha256."""
    name, recipe = chosen()
    write(train([r for m in SELECTION + RESERVE for r in match_rows(m)], {name: recipe})[name], name)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    step = ap.add_mutually_exclusive_group(required=True)
    step.add_argument("--select", action="store_true")
    step.add_argument("--confirm", action="store_true")
    step.add_argument("--final", action="store_true")
    step.add_argument("--identity", action="store_true", help="stops_model.json that changes nothing (ADR-009 as is)")
    a = ap.parse_args()
    if a.identity:
        write(identity_model(), "identity")
    else:
        select() if a.select else confirm() if a.confirm else final()
