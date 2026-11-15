"""Live-play possession model of ADR-014 (#49, with #35): trains, picks and exports it, on open data only.

Usage:
  python calibrate_live.py --select    LOMO over the 7 selection matches (Metrica Games 2-3, IDSSE 1-5): every recipe
                                       against the radio pipeline; the best goes to live_choice.json
  python calibrate_live.py --confirm --seed-start N [--candidate KEY=VALUE ...] [--reference KEY=VALUE ...]
                                       ADR-019: a candidate recipe against a reference recipe (both the delivered one
                                       plus the changes given), each trained on the selection, on the reserve (Metrica
                                       Game 1, IDSSE 6-7) with fresh seeds: the 43 conditions of ADR-010 and ADR-014
                                       against the reference. Writes live_confirmation.json; exits 1 unless confirmed.
                                       --reference radio: against the pipeline that trains nothing, for a retrain that
                                       asks whether the model works, not whether it improves (ADR-033)
  python calibrate_live.py --final     the delivered recipe trained on the 10 matches -> live_model.json, only with a
                                       confirmed live_confirmation.json for that recipe, the same training rows and the
                                       same training code; otherwise exits 2 and leaves live_model.json as it was
  [--report PATH]                      the report --confirm writes and --final needs, live_confirmation.json by default
  --select [--training-truth A|B] [--evaluation-truth A|B] [--choice-report PATH]
                                       independent training and scoring conventions (ADR-027), A by default;
                                       IDSSE always keeps provider truth. Nondefault truths require a separate
                                       choice report and are not enabled for --confirm or --final. This remains
                                       the historical hyperparameter grid; ADR-027's fixed two-recipe experiment
                                       is explore/controlled_truth.py
  python calibrate_live.py --rule      live_model.json that keeps the change rule (ADR-009 as is)
Recipe keys: leaves, lam (the switch penalty, in logits), short_weight and short_s (the frames of a true possession
shorter than short_s seconds count short_weight times in training). Example (#77, with weight 3 delivered): --confirm
--reference short_weight=1 --seed-start 70. Training needs requirements-train.txt (scikit-learn); possession.py runs
without it.
Open data only (AGENTS.md): Metrica sample-data (data/) and IDSSE (../idsse-data, revision a715a38). Nothing here
reads BAR-ATH or the public window, and the reserve enters only --confirm and --final (ADR-011).

--select and --confirm score with scikit-learn's decision_function, compiled: on integer signals it takes the same
decisions as the exported trees, whose leaves differ by less than 1e-6 logit. possession.py uses the exported trees,
and --confirm counts the frames where the two paths differ: any difference fails the confirmation (ADR-019).
"""
import collections
import functools
import hashlib
import json
import math
import os
import subprocess
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "explore"))
_argv, sys.argv = sys.argv, sys.argv[:1]  # possession, calibrate_dead and idsse_dead_labels read sys.argv[1] at import
import bench  # noqa: E402
import calibrate_edges as CE  # noqa: E402
import possession as P  # noqa: E402
from player_noise import NOISE, noisy_players  # noqa: E402
sys.argv = _argv

pm = bench.pm
STEP = 16  # one row every 16 live frames of each variant, offset by variant: the signals are smooth
# What we do not know of the ATD, at levels fixed beforehand and none measured with the public truth (ADR-033, #111):
# the ball missing on 0-45% of live frames (0 removes nothing; 45% from DATA.md's 41%, ADR-006) and on 0 or 50% of
# dead ones; each ball goes once with clean players and once with TRAIN_NOISE.
TRAIN_BALLS = (dict(seed=100, live_missing=0.0), dict(seed=101, live_missing=0.2, dead_missing=0.5),
               dict(seed=102, live_missing=0.45), dict(seed=103, live_missing=0.45, mean_gap_s=3.0, dead_missing=0.5))
TRAIN_NOISE = NOISE["noise 0.6 m + 10% lost + swaps 5%"]
# The frames of a true possession shorter than SHORT_S count SHORT_WEIGHT times in training: they are 9 in 10 of the
# possessions the model misses (explore/diagnose_changes.py) and the metric counts every possession alike. 1 keeps
# the earlier recipe. 3 was picked on the selection (explore/short_weight.py) and passed the 43 conditions against
# radio (#77), but not against weight 1 (ADR-019: 41 of 43, live_confirmation.json), so the delivery is back to 1 (#91).
SHORT_S, SHORT_WEIGHT = 5, 1.0
FPS = 25
LEAVES, LAMBDAS = (31, 63), (5, 10, 20, 40)
CHOICE = os.path.join(ROOT, "live_choice.json")
REPORT = os.path.join(ROOT, "live_confirmation.json")
PROTOCOL = "ADR-019"
RADIO = "radio"  # --reference radio: the candidate against the pipeline that trains nothing (ADR-033)
RECIPE_TYPES = {"leaves": int, "lam": float, "short_weight": float, "short_s": float}
REPORT_KEYS = ("protocol", "status", "candidate", "reference", "conditions", "exact", "fingerprint")
# The 43 conditions of ADR-019 (those of ADR-010 and ADR-014, against the reference): the seven scenarios in both
# benches (Metrica with both truths), the ball of the stops on the pitch and the ten NOISE entries.
CONDITIONS = ([(s, b, a) for s in CE.SCENARIOS for b, a in (("Metrica", "end"), ("Metrica", "start"), ("IDSSE", "status"))]
              + [("ball of the stops on the pitch", "Metrica", a) for a in ("end", "start")]
              + [(s, b, a) for s in NOISE for b, a in (("Metrica", "start"), ("IDSSE", "status"))])


@functools.lru_cache(maxsize=3)
def metrica_events(g):
    """Cache only open-data events, not the tracking arrays returned by the existing loader."""
    return bench.load_game(g)[3]


def check_truth_coverage(original, alternative):
    """A/B must score identical frames and stops; never silently intersect their coverage (ADR-020)."""
    if len(original) != len(alternative) or any(not np.array_equal(original == label, alternative == label)
                                               for label in ("X", "D")):
        raise ValueError("evaluation truths have different lengths or X/D masks")
    if pm.valid_runs(pm.label_codes(original)) != pm.valid_runs(pm.label_codes(alternative)):
        raise ValueError("evaluation truths have different valid runs")


def evaluation_truths(game, evaluation_truth="A"):
    """Explicit evaluation convention, independent of training. IDSSE always keeps its provider truth."""
    if evaluation_truth not in ("A", "B"):
        raise ValueError("truth must be A or B")
    if evaluation_truth == "A" or "status" in game.truths:
        return game.truths
    events = metrica_events(game.g)
    truths = {anchor: bench.truth_labels(events, len(game.ball), game.dead, anchor, variant="B")
              for anchor in game.truths}
    for anchor, truth in truths.items():
        check_truth_coverage(game.truths[anchor], truth)
    return truths


def truth_of(game, training_truth="A"):
    """Training target and duration convention: Metrica start A/B, or IDSSE provider (ADR-027)."""
    truths = evaluation_truths(game, training_truth)
    return truths["start"] if "start" in truths else truths["status"]


def reevaluate(preds, games, evaluation_truth="A"):
    """Reuse the exact prediction arrays under another truth, after checking frame alignment and coverage."""
    truths = {g.g: evaluation_truths(g, evaluation_truth) for g in games}
    out = {}
    for key, (old, labels) in preds.items():
        truth = truths[key[0]][key[1]]
        check_truth_coverage(old, truth)
        if any(len(lab) != len(truth) for lab in labels):
            raise ValueError("prediction and truth lengths differ")
        out[key] = truth, labels
    return out


def players_of(game, seed, noise):
    return game.players if noise is None else noisy_players(game.players, game.ball, game.team,
                                                            np.random.default_rng(10_000 * game.g + seed),
                                                            pitch=game.pitch, **noise)


def run_seconds(truth):
    """Duration in seconds of the run of equal truth labels each frame belongs to."""
    run = np.concatenate([[0], np.cumsum(truth[1:] != truth[:-1])])
    return np.bincount(run)[run] / FPS


def game_rows(game, short_s=SHORT_S, *, training_truth="A"):
    """(X, y, short) of one game: every STEP-th frame, offset by variant, that is live in the truth and in dead_mask_v2 on
    that variant, for each TRAIN_BALLS ball with clean and noisy players; once with H and once with A as the own team.
    y: the own team has the ball; short: its true possession lasts less than short_s seconds."""
    truth = truth_of(game, training_truth)
    spans = CE.spans_of(game)
    live = (truth == "H") | (truth == "A")
    secs = run_seconds(truth)
    X, y, short = [], [], []
    for v, (b, noise) in enumerate((b, noise) for b in TRAIN_BALLS for noise in (None, TRAIN_NOISE)):
        ball = CE.degraded(game, 1000 * game.g + b["seed"], **{k: x for k, x in b.items() if k != "seed"})
        players = players_of(game, b["seed"], noise)
        v2 = P.dead_mask_v2(players, ball)
        FH, FA = P.live_features(players, ball, game.team, bench.radio_evidence(players, ball, game.team, pitch=game.pitch),
                                 v2, spans, game.pitch)
        idx = np.flatnonzero(live & ~v2)[v::STEP]
        X += [FH[idx], FA[idx]]
        y += [truth[idx] == "H", truth[idx] == "A"]
        short += [secs[idx] < short_s] * 2
    return np.vstack(X), np.concatenate(y), np.concatenate(short)


def fit(rows, leaves, short_weight=SHORT_WEIGHT):
    """HistGradientBoostingClassifier on rows = [(match, X, y, short)], every match with the same total weight before
    the short possessions count short_weight times: a match with more short possessions then weighs more (#77; part of
    the recipe, ADR-019)."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    count = collections.Counter()
    for match, X, *_ in rows:
        count[match] += len(X)
    X = np.vstack([r[1] for r in rows])
    y = np.concatenate([r[2] for r in rows])
    w = np.concatenate([np.where(r[3], short_weight, 1.0) / count[r[0]] for r in rows])
    return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.1, max_leaf_nodes=leaves, min_samples_leaf=200,
                                          random_state=0, early_stopping=False).fit(X, y, sample_weight=w * len(w) / w.sum())


def tree_scorer(trees):
    """F -> int64 raw scores of exported trees (what possession.py runs)."""
    return lambda F: P.tree_scores(F, trees)


def sklearn_scorer(clf):
    """F -> int64 raw scores of the classifier in the exported trees' units (the fast path of --select and --confirm)."""
    return lambda F: np.rint(clf.decision_function(F) * CE.SCALE).astype(np.int64)


def switch_of(lam):
    """decode_live's switch for a penalty of lam logits per change: the scores are in SCALE units and count twice."""
    return int(round(2 * lam * CE.SCALE))


def recipes():
    """The 8 candidates of the selection: LEAVES by LAMBDAS (the switch penalty, in logits)."""
    return {f"{leaves} leaves, lambda {lam}": dict(leaves=leaves, lam=lam) for leaves in LEAVES for lam in LAMBDAS}


def score(games, models, seeds, scenario=None, noise=None, clip=False, anchors=None, true_d=False,
          *, evaluation_truth="A"):
    """Labels per seed for "radio" (main) and each model of {name: (scorer, switch)}: bench.compare's format,
    {(g, anchor, "degraded", name): (truth, [labels])}. noise: a NOISE entry for the players; clip: the restored ball
    of the stops kept on the pitch (ADR-010, criterion 2); true_d: also "radio, true D" and "<name>, true D"."""
    if evaluation_truth not in ("A", "B"):
        raise ValueError("truth must be A or B")
    if evaluation_truth != "A":
        games = list(games)  # reevaluate needs the same games after prediction, including for an iterator input
    preds = {}
    for game in games:
        for s in seeds:
            ball = CE.degraded(game, 1000 * game.g + s, **(scenario or {}))
            if clip:
                restored = game.dead & np.isnan(game.ball[:, 0])
                ball[restored, :2] = np.clip(ball[restored, :2], 0.0, 1.0)
            players = players_of(game, s, noise)
            ev = bench.radio_evidence(players, ball, game.team, pitch=game.pitch)
            v2 = P.dead_mask_v2(players, ball)
            for anchor, truth in game.truths.items():
                if anchors and anchor not in anchors:
                    continue
                spans = pm.valid_runs(pm.label_codes(truth))
                out = {}
                for tag, dead in (("", v2),) + (((", true D", game.dead),) if true_d else ()):
                    out["radio" + tag] = bench.segment(dead, ev, spans, P.CHANGE_FRAMES, P.MAX_GAP)
                    FH, FA = P.live_features(players, ball, game.team, ev, dead, spans, game.pitch)
                    scores = {}
                    for name, (scorer, switch) in models.items():
                        if scorer not in scores:
                            scores[scorer] = scorer(FH) - scorer(FA)
                        out[name + tag] = P.segment_live(dead, scores[scorer], spans, switch)
                for name, labels in out.items():
                    preds.setdefault((game.g, anchor, "degraded", name), (truth, []))[1].append(labels)
    return preds if evaluation_truth == "A" else reevaluate(preds, games, evaluation_truth)


def extras(preds, names):
    """Per bench, reported without deciding: the share of true live frames labelled H/A that are right, and the
    possessions predicted over the true ones, for radio and the models."""
    out = {}
    for (g, anchor, _, nm), (truth, labels) in preds.items():
        if nm not in ("radio", *names) or anchor == "end":
            continue
        gt = pm.label_codes(truth)
        runs_ = pm.valid_runs(gt)
        live = (truth == "H") | (truth == "A")
        for lab in labels:
            ok = live & np.isin(lab, ("H", "A"))
            spells = len(pm.possession_spells(pm.fill_abstentions(pm.label_codes(lab), runs_), runs_))
            out.setdefault(("Metrica" if g < 10 else "IDSSE", nm), []).append(
                (np.mean(lab[ok] == truth[ok]), spells, len(pm.possession_spells(gt, runs_))))
    for (bench_name, nm), v in sorted(out.items()):
        a = np.array(v)
        print(f"  {bench_name:7} {nm:24} live frames right {a[:, 0].mean():.3f}  possessions {a[:, 1].mean():.0f} of "
              f"{a[:, 2].mean():.0f}")


def select(*, training_truth="A", evaluation_truth="A", choice_path=None):
    """LOMO over the 7 selection matches: each leaves size is trained on 6, and every recipe scored on the one left out."""
    if training_truth not in ("A", "B") or evaluation_truth not in ("A", "B"):
        raise ValueError("truth must be A or B")
    if (training_truth, evaluation_truth) != ("A", "A") and choice_path is None:
        raise ValueError("nondefault truths require a separate choice_path; they cannot change the delivered recipe")
    choice_path = CHOICE if choice_path is None else choice_path
    if (training_truth, evaluation_truth) != ("A", "A") and os.path.realpath(choice_path) == os.path.realpath(CHOICE):
        raise ValueError("nondefault truths cannot write live_choice.json")
    t0 = time.time()
    games = {m: CE.load(m) for m in CE.SELECTION}
    rows = {m: [(m, *game_rows(g, training_truth=training_truth)) for g in games[m]] for m in CE.SELECTION}
    print(f"rows: {sum(len(r[2]) for m in rows for r in rows[m])} ({time.time() - t0:.0f} s)", flush=True)
    every = recipes()
    diffs = {name: {} for name in every}
    for held in CE.SELECTION:
        clfs = {leaves: fit([r for m in CE.SELECTION if m != held for r in rows[m]], leaves) for leaves in LEAVES}
        scorers = {leaves: sklearn_scorer(clf) for leaves, clf in clfs.items()}  # one per size: score() caches by it
        models = {name: (scorers[r["leaves"]], switch_of(r["lam"])) for name, r in every.items()}
        preds = score(games[held], models, CE.SEEDS["select"][held[0]], anchors={"start", "status"},
                      evaluation_truth=evaluation_truth)
        for name in every:
            diffs[name].update(CE.per_game(preds, name))
        print(f"  left out {held}: done ({time.time() - t0:.0f} s)", flush=True)
    table = sorted(((CE.bench_means(d), name) for name, d in diffs.items()), key=lambda x: -x[0][2])
    print("\nselection (LOMO, default degraded ball, clean players): paired spellF1 difference against radio")
    print(f"  {'recipe':24} {'Metrica':>8} {'IDSSE':>8} {'mean':>8}")
    for (m, i, both), name in table:
        print(f"  {name:24} {m:+8.4f} {i:+8.4f} {both:+8.4f}")
    (m, i, both), name = table[0]
    print("  per game: " + "  ".join(f"{g}{a[0]} {d:+.3f}" for (g, a), d in sorted(diffs[name].items())))
    result = {"recipe": name, **every[name], "metrica": round(m, 4), "idsse": round(i, 4), "mean": round(both, 4)}
    if (training_truth, evaluation_truth) != ("A", "A"):
        result.update(training_truth=training_truth, evaluation_truth=evaluation_truth)
    with open(choice_path, "w") as f:
        json.dump(result, f, indent=1)
        f.write("\n")
    print(f"\nchosen: {name} -> {os.path.basename(choice_path)} ({time.time() - t0:.0f} s)")


def chosen():
    with open(CHOICE) as f:
        c = json.load(f)
    return c["recipe"], {k: c[k] for k in ("leaves", "lam")}


def recipe_of(changes=()):
    """The delivered recipe (live_choice.json, SHORT_WEIGHT and SHORT_S) with the KEY=VALUE changes (ADR-019)."""
    _, picked = chosen()
    recipe = dict(picked, short_weight=SHORT_WEIGHT, short_s=SHORT_S)
    for change in changes:
        key, sep, value = change.partition("=")
        if not sep or key not in recipe:
            raise ValueError(f"not a recipe change: {change!r} (KEY=VALUE, keys {', '.join(RECIPE_TYPES)})")
        recipe[key] = value
    out = {k: RECIPE_TYPES[k](v) for k, v in recipe.items()}  # int("2.5") and float("abc") raise ValueError
    if out["leaves"] < 2 or not all(math.isfinite(out[k]) and out[k] > 0 for k in ("lam", "short_weight", "short_s")):
        raise ValueError(f"not a valid recipe: {out}")
    return out


def holds(c):
    """ADR-019 on one condition: the 5-95% interval above 0 in the default scenario, the point above 0 elsewhere."""
    v = c["lo"] if c["scenario"] == "default" else c["point"]
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise TypeError(f"not a number: {v!r}")
    return v > 0


def decide(conds, frames_differ):
    """ADR-019's verdict, from the numbers alone: every declared condition present once and holding, and the exported
    trees taking the same decisions as decision_function."""
    keys = sorted((c["scenario"], c["bench"], c["anchor"]) for c in conds)
    return type(frames_differ) is int and frames_differ == 0 and keys == sorted(CONDITIONS) and all(map(holds, conds))


def paired(preds, a, b, n_draws, **where):
    """bench.compare(preds, a, b) as report rows, rounded as the report keeps them."""
    return [dict(where, anchor=anchor, point=round(point, 6), lo=round(lo, 6), hi=round(hi, 6),
                 above=f"{sum(d > 0 for d in per.values())}/{len(per)}")
            for (anchor, _), (point, lo, hi, per) in bench.compare(preds, a, b, n_draws).items()]


def conditions(benches, models, ref, cand, n_draws=1000):
    """cand against ref, both scored on the same balls and players (ADR-019): (the 43 conditions, the lines that do not
    decide: each model against radio and the two with the true D). benches: (("Metrica", games, seeds), ("IDSSE", ...))."""
    conds, history = [], []

    def keep(rows):
        for c in rows:
            c["holds"] = holds(c)
            print(f"  {c['scenario'][:32]:32} {c['bench']:7} {c['anchor']:6} {c['point']:+.4f} [{c['lo']:+.4f}, "
                  f"{c['hi']:+.4f}]  {c['above']} above 0  {'ok' if c['holds'] else 'FAILS'}", flush=True)
        conds.extend(rows)

    for scen, kw in CE.SCENARIOS.items():
        for bench_name, games, seeds in benches:
            preds = score(games, models, seeds, kw, true_d=scen == "default")
            keep(paired(preds, ref, cand, n_draws, scenario=scen, bench=bench_name))
            if scen == "default":
                for a, b in [p for p in (("radio", ref), ("radio", cand), (ref + ", true D", cand + ", true D"))
                             if p[0] != p[1]]:  # ref may be radio itself (ADR-033)
                    for h in paired(preds, a, b, n_draws, bench=bench_name, model=b, against=a):
                        print(f"  ({b} against {a}, not deciding) {bench_name} {h['anchor']} {h['point']:+.4f} "
                              f"[{h['lo']:+.4f}, {h['hi']:+.4f}]", flush=True)
                        history.append(h)
                extras(preds, (ref, cand))
    _, games, seeds = benches[0]
    keep(paired(score(games, models, seeds, clip=True), ref, cand, n_draws, scenario="ball of the stops on the pitch",
                bench="Metrica"))
    for noise_name, kw in NOISE.items():
        for bench_name, games, seeds in benches:
            preds = score(games, models, seeds, noise=kw, anchors={"start", "status"})
            keep(paired(preds, ref, cand, n_draws, scenario=noise_name, bench=bench_name))
    return conds, history


def scorer_sha256():
    """The official scorer, hashed as ci_checks.py hashes sources: its text with LF line ends."""
    with open(pm.__file__, encoding="utf-8") as f:
        return hashlib.sha256(f.read().encode("utf-8")).hexdigest()


def fingerprint(rows):
    """What the exported weights depend on besides the recipe and the training code (ADR-019): the signal schema, the
    sha256 of each match's training rows (they sum up the code that builds them and the open data), their order, the
    official scorer and the libraries."""
    import sklearn
    digests = {}
    for match, *arrays in rows:
        h = digests.setdefault(f"{match[0]} {match[1]}", hashlib.sha256())
        for a in arrays:
            h.update(np.ascontiguousarray(a).tobytes())
    return {"features": list(P.LIVE_FEATURES), "rows": {m: h.hexdigest() for m, h in digests.items()},
            "order": [f"{m[0]} {m[1]}" for m, *_ in rows], "scorer": scorer_sha256(),
            "versions": {"numpy": np.__version__, "scikit-learn": sklearn.__version__}}


def model_of(clf, recipe):
    return {"mode": "model", "switch": switch_of(recipe["lam"]), "trees": CE.export(clf)}


def model_digest(rows, recipe):
    """sha256 of the live_model.json text of recipe trained on rows: the part of the fingerprint that covers the
    training and export code (ADR-019)."""
    return hashlib.sha256(to_json(model_of(fit(rows, recipe["leaves"], recipe["short_weight"]), recipe)).encode()).hexdigest()


def code_version():
    """The commit the run comes from and the tracked files that differ from it; None for both without git."""
    try:
        head, diff = (subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout
                      for args in (("rev-parse", "HEAD"), ("diff", "--name-only", "HEAD")))
        return {"commit": head.strip(), "modified": diff.split()}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "modified": None}


def replace(path, text):
    """path gets text in one step: a temporary file next to it replaces it, so a failure never leaves half a file."""
    with open(path + ".tmp", "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(path + ".tmp", path)


def save(report, path):
    replace(path, json.dumps(report, indent=1) + "\n")


def confirm(seed_start, candidate, reference, path=REPORT, n_draws=1000):
    """ADR-019: candidate against reference, each trained on the selection, on the reserve with fresh seeds. Writes the
    report to path, confirmed or not, and returns it. reference RADIO: against the pipeline that trains nothing
    (ADR-033)."""
    t0 = time.time()
    games = {m: CE.load(m) for m in CE.SELECTION + CE.RESERVE}
    rows = {m: [(m, *game_rows(g, candidate["short_s"])) for g in games[m]] for m in games}
    recipes_ = {"candidate": (candidate, rows)}
    if reference != RADIO:
        ref_rows = rows if reference["short_s"] == candidate["short_s"] else \
            {m: [(m, *game_rows(g, reference["short_s"])) for g in games[m]] for m in CE.SELECTION}
        recipes_["reference"] = (reference, ref_rows)
    clfs = {name: fit([r for m in CE.SELECTION for r in rs[m]], r["leaves"], r["short_weight"])
            for name, (r, rs) in recipes_.items()}
    models = {name: (sklearn_scorer(clfs[name]), switch_of(r["lam"])) for name, (r, _) in recipes_.items()}
    # the provenance before the reserve is scored: a failure here costs no look at the reserve
    selection_model = hashlib.sha256(to_json(model_of(clfs["candidate"], candidate)).encode()).hexdigest()
    prints = dict(fingerprint([r for m in CE.SELECTION + CE.RESERVE for r in rows[m]]), selection_model=selection_model)
    code = code_version()
    print(f"rows and the two models: {time.time() - t0:.0f} s", flush=True)
    metrica, idsse = games[("metrica", 1)], games[("idsse", 6)] + games[("idsse", 7)]
    seeds = {"metrica": list(range(seed_start, seed_start + 10)), "idsse": list(range(seed_start, seed_start + 5))}
    print(f"ADR-019: candidate {candidate} against reference {reference}; Metrica Game 1 (seeds {seeds['metrica'][0]}-"
          f"{seeds['metrica'][-1]}), IDSSE 6-7 (seeds {seeds['idsse'][0]}-{seeds['idsse'][-1]}); paired difference, "
          f"candidate minus reference, 5-95%, {n_draws} draws", flush=True)
    conds, history = conditions((("Metrica", metrica, seeds["metrica"]), ("IDSSE", idsse, seeds["idsse"])), models,
                                RADIO if reference == RADIO else "reference", "candidate", n_draws)
    key = (metrica[0].g, "start", "degraded", "candidate")
    exact = {"candidate": (tree_scorer(CE.export(clfs["candidate"])), models["candidate"][1])}
    a = score(metrica[:1], {"candidate": models["candidate"]}, seeds["metrica"][:1], anchors={"start"})[key][1][0]
    b = score(metrica[:1], exact, seeds["metrica"][:1], anchors={"start"})[key][1][0]
    frames = int((a != b).sum())
    report = {"protocol": PROTOCOL, "status": "confirmed" if decide(conds, frames) else "rejected",
              "candidate": candidate, "reference": reference,
              "partitions": {part: [f"{m} {n}" for m, n in ms] for part, ms in (("selection", CE.SELECTION),
                                                                                ("reserve", CE.RESERVE))},
              "seeds": seeds, "conditions": conds,
              "exact": {"frames_differ": frames, "where": "Metrica Game 1, first seed, truth from the event start"},
              "not_deciding": history, "fingerprint": prints, "code": code}
    save(report, path)
    print(f"\nexported trees against decision_function (Metrica Game 1, first seed): {frames} frames differ")
    print(f"\n{report['status'].upper()}: {sum(holds(c) for c in conds)}/{len(conds)} conditions hold "
          f"-> {os.path.basename(path)} ({time.time() - t0:.0f} s)")
    return report


def to_json(model):
    """live_model.json text: compact, with the trees as lists."""
    out = dict(model)
    if "trees" in out:
        t = out["trees"]
        out["trees"] = {"init": t["init"], "trees": [{k: v.tolist() for k, v in tree.items()} for tree in t["trees"]]}
    return json.dumps(out, separators=(",", ":")) + "\n"


def write(model, name, path=P.LIVE_MODEL_PATH):
    """The model file, written in one step (replace)."""
    text = to_json(model)
    replace(path, text)
    digest = hashlib.sha256(text.encode()).hexdigest()
    print(f"wrote {os.path.basename(path)} ({name}): {len(text)} bytes, sha256 {digest}")
    return digest


def read_report(path):
    """(report, problems): the confirmation report, or why there is none to use."""
    try:
        with open(path, encoding="utf-8") as f:
            report = json.load(f)
    except FileNotFoundError:
        return None, [f"{path} is missing: confirm the recipe first (--confirm)"]
    except (OSError, ValueError) as e:
        return None, [f"{path} cannot be read: {e}"]
    return (report, []) if isinstance(report, dict) else (None, [f"{path} is not a confirmation report"])


def report_problems(report, recipe):
    """Why report cannot back the export of recipe, the fingerprint aside (ADR-019): [] when it can."""
    missing = [k for k in REPORT_KEYS if k not in report]
    if missing:
        return [f"fields missing from the report: {', '.join(missing)}"]
    problems = []
    if report["protocol"] != PROTOCOL:
        problems.append(f"the report follows {report['protocol']!r}, not {PROTOCOL}")
    if report["status"] != "confirmed":
        problems.append(f"the confirmation was {report['status']!r}")
    try:
        if not decide(report["conditions"], report["exact"].get("frames_differ")):
            problems.append("the conditions and the exported trees in the report do not confirm")
    except (AttributeError, KeyError, TypeError) as e:
        problems.append(f"the conditions in the report are malformed ({e!r})")
    if report["candidate"] != recipe:
        problems.append(f"the report confirms {report['candidate']}, not the delivered recipe {recipe}")
    return problems


def final(path=REPORT, model_path=P.LIVE_MODEL_PATH, rows=None):
    """ADR-019: the delivered recipe trained on the 10 matches, written only with a confirmed report for that recipe, the
    same training rows and the same training code. Returns what stopped it, [] when it wrote the model and its
    provenance in the report."""
    recipe = recipe_of()
    report, problems = read_report(path)
    if not problems:
        problems = report_problems(report, recipe)
    if problems:
        return problems
    if rows is None:
        rows = [(m, *game_rows(g, recipe["short_s"])) for m in CE.SELECTION + CE.RESERVE for g in CE.load(m)]
    now = fingerprint(rows)
    confirmed = report["fingerprint"] if isinstance(report["fingerprint"], dict) else {}
    changed = [k for k in now if confirmed.get(k) != now[k]]
    if changed:
        return [f"the fingerprint differs from the confirmed one in: {', '.join(changed)}"]
    if model_digest([r for r in rows if r[0] in CE.SELECTION], recipe) != confirmed.get("selection_model"):
        return ["the recipe trained on the selection with today's code is not the confirmed model: the training or the "
                "export changed"]
    model = model_of(fit(rows, recipe["leaves"], recipe["short_weight"]), recipe)
    report["final"] = {"matches": list(dict.fromkeys(f"{m[0]} {m[1]}" for m, *_ in rows)),
                       "sha256": write(model, f"recipe {recipe}", model_path),
                       "note": "trained on the selection and the reserve: not an independent evaluation (ADR-011)"}
    save(report, path)
    return []


def cli(argv=None):
    """The command line of the module docstring: (args, candidate, reference), the recipes only with --confirm. A usage
    error exits with code 2 before any data is read."""
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    step = ap.add_mutually_exclusive_group(required=True)
    step.add_argument("--select", action="store_true")
    step.add_argument("--confirm", action="store_true")
    step.add_argument("--final", action="store_true")
    step.add_argument("--rule", action="store_true", help="live_model.json that keeps the change rule (ADR-009 as is)")
    ap.add_argument("--seed-start", type=int, help="--confirm: first reserve seed, of a block no confirmation used")
    ap.add_argument("--candidate", nargs="+", action="extend", default=[], metavar="KEY=VALUE",
                    help="--confirm: changes to the delivered recipe for the candidate")
    ap.add_argument("--reference", nargs="+", action="extend", default=[], metavar="KEY=VALUE",
                    help="--confirm: changes to the delivered recipe for the reference, or radio (ADR-033)")
    ap.add_argument("--report", default=REPORT, help="the confirmation report --confirm writes and --final needs")
    ap.add_argument("--training-truth", choices=("A", "B"), default="A", help="--select: Metrica training target and short durations")
    ap.add_argument("--evaluation-truth", choices=("A", "B"), default="A", help="--select: scoring convention only")
    ap.add_argument("--choice-report", help="--select: separate recipe report, required for nondefault truths")
    a = ap.parse_args(argv)
    nondefault = (a.training_truth, a.evaluation_truth) != ("A", "A")
    if (nondefault or a.choice_report) and not a.select:
        ap.error("truth options and --choice-report go only with --select; confirmation/export remain ADR-019")
    if nondefault and (not a.choice_report or os.path.realpath(a.choice_report) == os.path.realpath(CHOICE)):
        ap.error("nondefault truths need --choice-report outside live_choice.json")
    if not a.confirm:
        if a.seed_start is not None or a.candidate or a.reference:
            ap.error("--seed-start, --candidate and --reference go only with --confirm")
        return a, None, None
    if a.seed_start is None:
        ap.error("--confirm needs --seed-start, the first seed of a block no confirmation used (ADR-019)")
    try:
        candidate = recipe_of(a.candidate)
        reference = RADIO if a.reference == [RADIO] else recipe_of(a.reference)
    except ValueError as e:
        ap.error(str(e))
    if candidate == reference:
        ap.error(f"the candidate and the reference are the same recipe ({candidate}): change one with --candidate or "
                 "--reference")
    return a, candidate, reference


if __name__ == "__main__":
    a, candidate, reference = cli()
    if a.rule:
        write({"mode": "rule"}, "rule")
    elif a.select:
        select(training_truth=a.training_truth, evaluation_truth=a.evaluation_truth, choice_path=a.choice_report)
    elif a.confirm:
        sys.exit(0 if confirm(a.seed_start, candidate, reference, a.report)["status"] == "confirmed" else 1)
    else:
        problems = final(a.report)
        for p in problems:
            print(f"--final refused (ADR-019): {p}", file=sys.stderr)
        sys.exit(2 if problems else 0)
