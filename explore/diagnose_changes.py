"""ADR-020: out-of-training selection diagnostics, historical weight 3 minus weight 1 (open data only).

    python explore/diagnose_changes.py [--report live_diagnosis.json]

LOMO on selection only; both halves stay together. Training always uses Metrica A/start or IDSSE/status.
The same predictions are evaluated against A and B, separately, with paired bootstrap from ADR-019.
Default degradation, selection seeds, clean players and the two declared noise sensitivities. No model is exported.
The reserve was already examined (#76); --reserve requires explicit recipes, a preregistered revision and fresh seeds.
"""
import argparse
import collections
import hashlib
import json
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
_argv, sys.argv = sys.argv, sys.argv[:1]  # possession and calibrate_dead read sys.argv[1] at import
import calibrate_live as CL  # noqa: E402
CE, pm = CL.CE, CL.pm
sys.argv = _argv

FPS = 25
BUCKETS = ((0, 2), (2, 5), (5, 15), (15, 1e9))  # seconds
CAUSES = ("wrong team", "predicted dead", "split", "merged", "boundaries")
# Each historical mean was rounded to four decimals: their difference has at most 0.0001 rounding error.
RECONSTRUCTION_TOLERANCE = 0.0001
SCENARIOS = {"default": None,
             "position noise 1.0 m per axis (1 s correlated)": CL.NOISE["position noise 1.0 m per axis (1 s correlated)"],
             "noise 0.6 m + 10% lost + swaps 5%": CL.NOISE["noise 0.6 m + 10% lost + swaps 5%"]}


def historical_recipes():
    """The fixed #77 comparison, independent of which recipe the team eventually delivers."""
    base = ["leaves=63", "lam=10", "short_s=5"]
    return CL.recipe_of(base + ["short_weight=1"]), CL.recipe_of(base + ["short_weight=3"])


def check_coverage(a, b):
    """Both truths index the same frames, with the same X/D and official valid runs; never intersect them."""
    if a.shape != b.shape or a.ndim != 1:
        raise ValueError("A/B frame lengths or dimensions differ")
    if any(not np.array_equal(a == label, b == label) for label in ("X", "D")):
        raise ValueError("A/B X or D coverage differs")
    if pm.valid_runs(pm.label_codes(a)) != pm.valid_runs(pm.label_codes(b)):
        raise ValueError("A/B scorer runs differ")


def relabel(preds, games, variant="A"):
    """Evaluation-only references: keep the very same prediction arrays, generated on each A anchor's coverage.
    B only applies to Metrica: IDSSE/status is reported once, in A's container."""
    if variant not in ("A", "B"):
        raise ValueError("variant must be A or B")
    truths = {}
    for g in games:
        if variant == "B" and g.match[0] != "metrica":
            continue
        other = g if variant == "A" else CE.load_metrica(g.g, truth_variant="B")[0]
        if (other.g, other.match) != (g.g, g.match):
            raise ValueError("evaluation game/frame identity differs")
        for anchor, truth in g.truths.items():
            check_coverage(truth, other.truths[anchor])
            truths[g.g, anchor] = other.truths[anchor]
    out = {}
    for key, (truth, labels) in preds.items():
        identity = key[:2]
        if identity not in truths:
            if variant == "B" and key[0] >= 10:
                continue
            raise ValueError("unknown evaluation game or anchor")
        check_coverage(truth, truths[identity])
        out[key] = truths[identity], labels
    return out


def predict_folds(reference, candidate, scenarios=None, seed_sets=None, reserve=False):
    """Fit both recipes per whole-match fold; return scenario predictions on A, fold provenance and evaluated games.
    Cached training rows never use an evaluation truth or a reserve match in LOMO mode."""
    scenarios = SCENARIOS if scenarios is None else scenarios
    seed_sets = CE.SEEDS["select"] if seed_sets is None else seed_sets
    selection, reserve_groups = tuple(CE.SELECTION), tuple(CE.RESERVE)
    if len(set(selection)) != len(selection) or set(selection) & set(reserve_groups):
        raise ValueError("invalid selection/reserve partition")
    groups = selection + reserve_groups if reserve else selection
    games = {m: CE.load(m) for m in groups}
    units = []
    for m, halves in games.items():
        expected = 2 if m[0] == "idsse" else 1
        if len(halves) != expected or any(g.match != m for g in halves):
            raise ValueError("loader must return the complete match, including both IDSSE halves")
        units.extend(g.g for g in halves)
    if len(units) != len(set(units)):
        raise ValueError("evaluation game/half identifiers must be unique")
    recipes = {"reference": reference, "candidate": candidate}
    rows = {cut: {m: [(m, *CL.game_rows(g, cut)) for g in games[m]] for m in selection}
            for cut in {r["short_s"] for r in recipes.values()}}
    preds, folds, evaluated = {s: {} for s in scenarios}, [], []
    held_groups = [reserve_groups] if reserve else [(m,) for m in selection]
    for held in held_groups:
        training = tuple(m for m in selection if m not in held)
        if not training or set(training) & set(held):
            raise ValueError("evaluation match appears in training")
        models, fingerprints = {}, {}
        for name, recipe in recipes.items():
            train = [r for m in training for r in rows[recipe["short_s"]][m]]
            if {r[0] for r in train} != set(training):
                raise ValueError("training rows have unexpected whole-match groups")
            clf = CL.fit(train, recipe["leaves"], recipe["short_weight"])
            models[name] = CL.sklearn_scorer(clf), CL.switch_of(recipe["lam"])
            fingerprints[name] = dict(CL.fingerprint(train), selection_model=hashlib.sha256(
                CL.to_json(CL.model_of(clf, recipe)).encode()).hexdigest())
        test = [g for m in held for g in games[m]]
        for scenario, noise in scenarios.items():
            for source in ("metrica", "idsse"):
                subset = [g for g in test if g.match[0] == source]
                if not subset:
                    continue
                scored = CL.score(subset, models, seed_sets[source], CE.SCENARIOS["default"], noise=noise)
                for key, value in scored.items():
                    if key[3] not in recipes:
                        continue
                    if key in preds[scenario]:
                        raise ValueError("evaluation unit predicted in multiple folds")
                    preds[scenario][key] = value
        folds.append({"training": list(training), "evaluation": list(held),
                      "units": [{"game": g.g, "match": g.match} for g in test], "fingerprints": fingerprints})
        evaluated.extend(test)
        print(f"fold {len(folds)}/{len(held_groups)}: excluded {held}; trained on {len(training)} matches", flush=True)
    return preds, folds, evaluated


def cause(gt, pred_codes, pred_spells):
    """Why a true spell (a, b, team) has no prediction at IoU 0.5. The first test that holds, by the frames it covers."""
    a, b, team = gt
    seg = pred_codes[a:b]
    if (seg == (pm.A if team == pm.H else pm.H)).mean() >= 0.5:  # label_codes: ints, H 0, A 1, D 2
        return "wrong team"
    if (seg == pm.D).mean() >= 0.5:
        return "predicted dead"
    over = [s for s in pred_spells if s[2] == team and s[0] < b and a < s[1]]
    if len(over) >= 2:
        return "split"
    if len(over) == 1 and over[0][1] - over[0][0] > 2 * (b - a):
        return "merged"
    return "boundaries"


def diagnose(preds, name, anchor):
    """Counts over every game and seed of one bench: (true spells, predicted spells, live minutes, by bucket, causes)."""
    n_true = n_pred = 0
    minutes = 0.0
    hit, tot = collections.Counter(), collections.Counter()
    causes = collections.Counter()
    for (g, a, _, nm), (truth, outs) in preds.items():
        if a != anchor or nm != name:
            continue
        gt = pm.label_codes(truth)
        runs = pm.valid_runs(gt)
        gt_spells = pm.possession_spells(gt, runs)
        for out in outs:
            pc = pm.fill_abstentions(pm.label_codes(out), runs)
            pred_spells = pm.possession_spells(pc, runs)
            flags = pm.matched_gt_flags(pm.spell_overlaps(gt_spells, pred_spells), len(gt_spells), 0.5)
            n_true += len(gt_spells)
            n_pred += len(pred_spells)
            minutes += ((truth == "H") | (truth == "A")).sum() / FPS / 60
            for sp, ok in zip(gt_spells, flags):
                secs = (sp[1] - sp[0]) / FPS
                k = next(i for i, (lo, hi) in enumerate(BUCKETS) if lo <= secs < hi)
                tot[k] += 1
                hit[k] += bool(ok)
                if not ok:
                    causes[cause(sp, pc, pred_spells)] += 1
    return n_true, n_pred, minutes, hit, tot, causes


def metrics(preds, name, anchor):
    """Counts averaged over seeds per unit, then summed over units; spellF1 averages units equally, as compare does."""
    true = predicted = minutes = 0.0
    hit, total, errors = collections.Counter(), collections.Counter(), collections.Counter()
    scores = []
    for (g, a, ball, model), (truth, outs) in preds.items():
        if (a, model) != (anchor, name):
            continue
        count = len(outs)
        n_true, n_pred, live, hits, totals, causes = diagnose({(g, a, ball, model): (truth, outs)}, name, anchor)
        true += n_true / count
        predicted += n_pred / count
        minutes += live / count
        for target, source in ((hit, hits), (total, totals), (errors, causes)):
            for k, v in source.items():
                target[k] += v / count
        scores.append(np.mean([CL.bench.score(truth, p, 0)["spell"] for p in outs]))
    missed = sum(errors.values())
    return {"spellF1": float(np.mean(scores)), "true_possessions": true, "predicted_possessions": predicted,
            "predicted_true_ratio": predicted / true if true else None, "live_minutes": minutes,
            "predicted_per_live_minute": predicted / minutes if minutes else None,
            "true_per_live_minute": true / minutes if minutes else None,
            "recall": [{"seconds": [lo, hi if hi < 1e9 else None], "true": total[i], "matched": hit[i],
                        "recall": hit[i] / total[i] if total[i] else None} for i, (lo, hi) in enumerate(BUCKETS)],
            "missed": missed, "errors": {c: {"count": errors[c], "proportion": errors[c] / missed if missed else 0.0}
                                          for c in CAUSES}}


def comparison(preds, n_draws=1000):
    """One reference per call; reject unpaired units, truths or seed counts before reusing ADR-019's comparator."""
    expected = {(g, a, b) for g, a, b, _ in preds}
    for g, anchor, ball in expected:
        keys = [(g, anchor, ball, name) for name in ("reference", "candidate")]
        if any(k not in preds for k in keys):
            raise ValueError("reference/candidate evaluation units differ")
        (truth, pa), (other, pb) = (preds[k] for k in keys)
        if not np.array_equal(truth, other) or len(pa) != len(pb) or not pa:
            raise ValueError("reference/candidate truths or seeds differ")
        if any(p.shape != truth.shape for p in pa + pb):
            raise ValueError("prediction frame coverage differs")
    if any(k[3] not in ("reference", "candidate") for k in preds):
        raise ValueError("comparison contains an unexpected recipe")
    out = []
    for source, bench_name in (("metrica", "Metrica"), ("idsse", "IDSSE")):
        subset = {k: v for k, v in preds.items() if (k[0] < 10) == (source == "metrica")}
        if not subset:
            continue
        for (anchor, _), (point, lo, hi, per) in CL.bench.compare(subset, "reference", "candidate", n_draws).items():
            out.append({"bench": bench_name, "anchor": anchor, "difference": dict(point=point, lo=lo, hi=hi),
                        "per_game": {str(g): v for g, v in per.items()},
                        "models": {name: metrics(subset, name, anchor) for name in ("reference", "candidate")}})
    return out


def check_reconstruction(results):
    """The #77 selection means were rounded separately to four decimals; allow their rounding uncertainty only."""
    expected = {("Metrica", "start"): 0.0026, ("IDSSE", "status"): 0.0157}
    for key, value in expected.items():
        result = next((r for r in results if (r["bench"], r["anchor"]) == key), None)
        got = None if result is None else result["difference"]["point"]
        if got is None or not np.isfinite(got) or abs(got - value) > RECONSTRUCTION_TOLERANCE + 1e-12:
            raise ValueError(f"historical reconstruction differs for {key}: got {got}, expected approximately {value}; "
                             "explain before evaluating B")


def cli(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", default=os.path.join(ROOT, "live_diagnosis.json"))
    ap.add_argument("--reserve", action="store_true")
    ap.add_argument("--seed-start", type=int)
    ap.add_argument("--revision", help="reserve: code revision registered before this run")
    ap.add_argument("--reference", nargs="+", action="extend", default=[])
    ap.add_argument("--candidate", nargs="+", action="extend", default=[])
    a = ap.parse_args(argv)
    protected = (CL.REPORT, CL.CHOICE, CL.P.LIVE_MODEL_PATH, CL.P.MODEL_PATH)
    identity = lambda path: os.path.normcase(os.path.realpath(path))
    if identity(a.report) in map(identity, protected):
        ap.error("diagnostic output must not replace a delivered model, recipe or ADR-019 confirmation")
    if a.reserve:
        required = set(CL.RECIPE_TYPES)
        if a.seed_start is None or a.seed_start < 90 or not a.revision or any(
                {v.partition("=")[0] for v in changes} != required for changes in (a.reference, a.candidate)):
            ap.error("--reserve needs --seed-start >=90 (#97 consumed block 80), --revision and both complete recipes")
        code = CL.code_version()
        changed_code = [p for p in (code["modified"] or []) if p.endswith(".py") or
                        os.path.basename(p).startswith("requirements")]
        if a.revision != code["commit"] or changed_code:
            ap.error("--revision must identify the current code, with no local code/dependency edits")
        try:
            reference, candidate = CL.recipe_of(a.reference), CL.recipe_of(a.candidate)
        except ValueError as e:
            ap.error(str(e))
    else:
        if a.seed_start is not None or a.revision or a.reference or a.candidate:
            ap.error("selection reconstructs the fixed #77 pair; recipe/revision/seed options require --reserve")
        reference, candidate = historical_recipes()
    return a, reference, candidate


def main(argv=None):
    a, reference, candidate = cli(argv)
    started = time.time()
    code = CL.code_version()
    seeds = ({"metrica": range(a.seed_start, a.seed_start + 10), "idsse": range(a.seed_start, a.seed_start + 5)}
             if a.reserve else CE.SEEDS["select"])
    mode = "reserve_check" if a.reserve else "selection_lomo"
    print(f"ADR-020 {mode}: descriptive, not an independent confirmation; the reserve was already examined (#76)", flush=True)
    predictions, folds, games = predict_folds(reference, candidate, seed_sets=seeds, reserve=a.reserve)
    primary = comparison(predictions["default"])
    report = {"protocol": "ADR-020", "mode": mode, "code": code, "reference": reference, "candidate": candidate,
              "seeds": {k: list(v) for k, v in seeds.items()}, "ball_seed": "1000 * game.g + seed",
              "player_seed": "10000 * game.g + seed", "ball_scenario": CE.SCENARIOS["default"],
              "scenarios": SCENARIOS, "bootstrap": {"draws": 1000, "percentiles": [5, 95]}, "folds": folds,
              "note": "selection already used to choose recipes; B is descriptive; counts average seeds per unit; "
                      "IDSSE halves stay together in training; no models or predictions exported"}
    if not a.reserve:
        try:
            check_reconstruction(primary)
        except ValueError as e:
            report.update(status="reconstruction_failed", problems=[str(e)], seconds=time.time() - started,
                          results=[dict(r, scenario="default", variant="A" if r["bench"] == "Metrica" else "status")
                                   for r in primary])
            CL.save(report, a.report)
            raise
        print("historical A/start + IDSSE/status reconstruction: OK; now evaluating B", flush=True)
    results = []
    for scenario, preds in predictions.items():
        for variant in ("A", "B"):
            rows = primary if scenario == "default" and variant == "A" else comparison(relabel(preds, games, variant))
            for row in rows:
                row.update(variant=variant if row["bench"] == "Metrica" else "status", scenario=scenario)
                delta = row["difference"]
                print(f"{scenario}: {row['bench']} {row['variant']}/{row['anchor']} "
                      f"{delta['point']:+.6f} [{delta['lo']:+.6f}, {delta['hi']:+.6f}]", flush=True)
                results.append(row)
    report.update(status="complete", results=results, seconds=time.time() - started)
    CL.save(report, a.report)
    print(f"aggregate report: {a.report}; {time.time() - started:.0f} s", flush=True)
    return report


if __name__ == "__main__":
    main()
