"""ADR-027 selection only: A/B training, fixed R recipe, paired official scoring. No confirmation mode.

Run under flock /tmp/mtah-heavy.lock, with MTAH_OFFICIAL set to the pinned local scorer.
"""
import datetime
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import calibrate_live as CL  # noqa: E402

CE, P, pm = CL.CE, CL.P, CL.pm
MATCHES = (("metrica", 2), ("metrica", 3)) + tuple(("idsse", m) for m in range(1, 6))
VARIANTS = {"A-start": "A", "B-start": "B"}
RECIPE = dict(leaves=63, lam=10, short_weight=1, short_s=5)
REPORT = ROOT / "explore/ADR-027_selection.json"
ADR = ROOT / "docs/adr/ADR-027-posesion-controlada.md"
PREREG = ROOT / "explore/ADR-027_preregistration.log"
COMMAND = "export MTAH_OFFICIAL=/home/matias/open-data/mtah2027; OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 flock /tmp/mtah-heavy.lock /home/matias/open-data/venv/bin/python explore/controlled_truth.py"


class ExportedScorer:
    """Compiled traversal of exported integer thresholds/leaves, with integer accumulation.

    TreePredictor returns one leaf as float64. Each exported integer is exactly representable
    (checked below), and is converted back to int64 BEFORE summing. Thus this is not rounded
    decision_function: it gives tree_scores exactly. The first two calls of each fold/model
    also run tree_scores and compare every raw score, before any bootstrap or diagnostics.
    """
    def __init__(self, clf, verify_calls=2):
        from sklearn.ensemble._hist_gradient_boosting.predictor import TreePredictor
        self.part = CE.export(clf)
        self.predictors = []
        self.remaining = verify_calls
        self.verified_rows = 0
        for predictors, tree in zip(clf._predictors, self.part["trees"], strict=True):
            original = predictors[0]
            nodes = original.nodes.copy()
            if nodes["is_categorical"].any():
                raise ValueError("only noncategorical integer signals are supported")
            for target, key in (("num_threshold", "threshold"), ("value", "value")):
                nodes[target] = tree[key]
                if not np.array_equal(nodes[target].astype(np.int64), tree[key]):
                    raise ValueError("exported integer cannot be represented exactly")
            self.predictors.append(TreePredictor(nodes, original.binned_left_cat_bitsets, original.raw_left_cat_bitsets))

    def __call__(self, F):
        if F.dtype != np.int64 or np.any(F < -(2**53)) or np.any(F > 2**53):
            raise ValueError("integer signals must be exactly representable in float64")
        X = np.asarray(F, dtype=np.float64, order="C")
        bits = np.zeros((0, 8), dtype=np.uint32)
        mapping = np.zeros(F.shape[1], dtype=np.uint32)
        out = np.full(len(F), self.part["init"], np.int64)
        for predictor in self.predictors:
            out += predictor.predict(X, bits, mapping, 2).astype(np.int64)
        if self.remaining:
            if not np.array_equal(out, P.tree_scores(F, self.part)):
                raise ValueError("compiled evaluator differs from exported integer tree_scores")
            self.remaining -= 1
            self.verified_rows += len(F)
        return out


def training_rows(rows, held):
    """Exclude the entire held match, including both IDSSE halves, and reject unknown partitions."""
    if held not in MATCHES or set(rows) != set(MATCHES):
        raise ValueError("selection partition must be exactly Metrica 2-3 and IDSSE 1-5")
    result = [r for m in MATCHES if m != held for r in rows[m]]
    if any(r[0] == held or r[0] not in MATCHES for r in result):
        raise ValueError("held-out or nonselection match entered training")
    return result


def diagnostics(preds):
    """Micro live accuracy and duration recall; macro mean possessions and spellF1 per unit/seed."""
    out = {}
    for (g, anchor, _, name), (truth, labels) in preds.items():
        key = ("Metrica" if g < 10 else "IDSSE", anchor, name)
        d = out.setdefault(key, dict(correct=0, live=0, n_pred=0, n_true=0, observations=0,
                                    spell_sum=0.0, hits=np.zeros(4), totals=np.zeros(4, np.int64)))
        gt = pm.label_codes(truth)
        spans = pm.valid_runs(gt)
        spells = pm.possession_spells(gt, spans)
        lengths = np.array([b - a for a, b, _ in spells])
        buckets = [lengths < 50, (lengths >= 50) & (lengths < 125),
                   (lengths >= 125) & (lengths <= 375), lengths > 375]
        live = (truth == "H") | (truth == "A")
        for lab in labels:
            pr = pm.fill_abstentions(pm.label_codes(lab), spans)
            predicted = pm.possession_spells(pr, spans)
            overlaps = pm.spell_overlaps(spells, predicted)
            flags = np.array([pm.matched_gt_flags(overlaps, len(spells), t) for t in pm.SPELL_IOUS])
            d["hits"] += [flags[:, mask].sum() / len(pm.SPELL_IOUS) for mask in buckets]
            d["totals"] += [mask.sum() for mask in buckets]
            d["correct"] += int((lab[live] == truth[live]).sum())
            d["live"] += int(live.sum())
            d["n_pred"] += len(predicted)
            d["n_true"] += len(spells)
            d["observations"] += 1
            d["spell_sum"] += float(CL.bench.spell_draws(gt, pm.label_codes(lab), np.arange(len(spells))[None])[0])
    return [dict(bench=b, anchor=a, variant=n, live_accuracy=d["correct"] / max(1, d["live"]),
                 predicted_possessions=d["n_pred"] / d["observations"],
                 true_possessions=d["n_true"] / d["observations"], spell_f1=d["spell_sum"] / d["observations"],
                 recall={label: dict(recall=float(h / t) if t else None, n_true=int(t), matched_mean_iou=float(h))
                         for label, h, t in zip(("0-2", "2-5", "5-15", ">15"), d["hits"], d["totals"])})
            for (b, a, n), d in sorted(out.items())]


def comparisons(preds, evaluation):
    result = []
    for b in ("Metrica", "IDSSE"):
        subset = {k: v for k, v in preds.items() if (k[0] < 10) == (b == "Metrica")}
        for (anchor, _), (point, lo, hi, per) in CL.bench.compare(subset, "A-start", "B-start", 1000).items():
            result.append(dict(bench=b, evaluation_truth=evaluation if b == "Metrica" else "provider",
                               anchor=anchor, point=point, lo=lo, hi=hi,
                               positive_units=sum(v > 0 for v in per.values()), units=len(per),
                               per_unit={str(k): v for k, v in per.items()}))
    return result


def decision(rows):
    def find(bench, truth, anchor):
        return next(r for r in rows if (r["bench"], r["evaluation_truth"], r["anchor"]) == (bench, truth, anchor))
    m = find("Metrica", "B", "start")
    i = find("IDSSE", "provider", "status")
    a = find("Metrica", "A", "start")
    return dict(passes=bool(m["lo"] > 0 and i["lo"] > 0 and a["lo"] >= -0.01),
                mean=(m["point"] + i["point"]) / 2,
                positive_units=m["positive_units"] + i["positive_units"], units=12,
                checks={"Metrica_B_lo_above_0": m["lo"] > 0, "IDSSE_lo_above_0": i["lo"] > 0,
                        "Metrica_A_noninferiority": a["lo"] >= -0.01})


def verify_preregistration():
    digest = hashlib.sha256(ADR.read_bytes()).hexdigest()
    lines = PREREG.read_text().splitlines()
    if lines[0].split()[0] != digest:
        raise ValueError("ADR differs from its preregistration")
    when = datetime.datetime.fromisoformat(lines[1].replace("Z", "+00:00"))
    if when >= datetime.datetime.now(datetime.timezone.utc):
        raise ValueError("preregistration is not earlier than measurement")
    return dict(sha256=digest, utc=lines[1])


def measure(report, start):
    games = {m: CE.load(m) for m in MATCHES}
    all_games = [g for m in MATCHES for g in games[m]]
    rows = {"A-start": {m: [(m, *CL.game_rows(g, short_s=5)) for g in games[m]] for m in MATCHES}}
    rows["B-start"] = {m: [(m, *CL.game_rows(g, short_s=5, training_truth="B")) for g in games[m]]
                       if m[0] == "metrica" else rows["A-start"][m] for m in MATCHES}
    for m in MATCHES:
        for ra, rb in zip(rows["A-start"][m], rows["B-start"][m], strict=True):
            if not np.array_equal(ra[1], rb[1]):
                raise ValueError("A/B changed features or sampling")
    report["features_identical"] = True
    report["fingerprints"] = {nm: CL.fingerprint([r for m in MATCHES for r in rs[m]]) for nm, rs in rows.items()}
    print(f"rows ready: {time.monotonic() - start:.1f} s", flush=True)
    preds = {}
    for held in MATCHES:
        fold = dict(held=list(held), models={}, training_matches=[list(m) for m in MATCHES if m != held])
        models = {}
        for nm in VARIANTS:
            clf = CL.fit(training_rows(rows[nm], held), 63, short_weight=1)
            model = CL.model_of(clf, RECIPE)
            models[nm] = (ExportedScorer(clf), model["switch"])
            fold["models"][nm] = hashlib.sha256(CL.to_json(model).encode()).hexdigest()
        # Exported integer trees, with an exact compiled traversal; never decision_function.
        got = CL.score(games[held], models, CE.SEEDS["select"][held[0]])
        preds.update({k: v for k, v in got.items() if k[3] in VARIANTS})
        fold["exact_evaluator"] = {nm: dict(verified_feature_rows=scorer.verified_rows, raw_scores_differ=0)
                                   for nm, (scorer, _) in models.items()}
        fold["elapsed_s"] = time.monotonic() - start
        report["folds"].append(fold)
        print(f"left out {held}: {fold['elapsed_s']:.1f} s", flush=True)
    report["comparisons"] = comparisons(preds, "A")
    b_preds = CL.reevaluate(preds, all_games, "B")
    report["comparisons"] += [r for r in comparisons(b_preds, "B") if r["bench"] == "Metrica"]
    report["diagnostics"] = dict(A=diagnostics(preds), B=diagnostics(b_preds))
    report["decision"] = decision(report["comparisons"])
    report["status"] = "completed"


def main():
    start = time.monotonic()
    report = dict(protocol="ADR-027", status="running", started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  preregistration=verify_preregistration(), recipe=RECIPE, variants=VARIANTS,
                  selection=[list(m) for m in MATCHES], seeds={"metrica": list(range(10)), "idsse": list(range(5))},
                  bootstrap=1000, code=CL.code_version(), folds=[])
    interrupted = ROOT / "explore/ADR-027_interrupted.json"
    report["previous_runs"] = [json.loads(interrupted.read_text())] if interrupted.exists() else []
    report["evaluator"] = "exported integer thresholds/leaves, compiled traversal, int64 accumulation; first H/A arrays of every model/fold checked against possession.tree_scores"
    failure = None
    try:
        measure(report, start)
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = repr(error)
        failure = error
    report["wall_s"] = time.monotonic() - start
    CL.save(report, str(REPORT))
    d = report.get("decision")
    if d:
        result = "; ".join(f"{r['bench']} {r['evaluation_truth']} {r['anchor']} {r['point']:+.6f} [{r['lo']:+.6f}, {r['hi']:+.6f}]"
                           for r in report["comparisons"])
        verdict = "Pasa selección; espera banco #97 y decisión del equipo" if d["passes"] else "No pasa la regla; no se propone adopción"
    else:
        result, verdict = report["error"], "Corrida fallida; reparar el error sin cambiar familia ni regla"
    with (ROOT / "docs/EXPERIMENTOS.md").open("a") as f:
        f.write(f"| 2026-11-02 | Matias (Codex, gpt-6.1-sol) | `more-than-a-hack-2027-issue-94`, base `de97105`, árbol de trabajo; `{COMMAND}` | ADR-027: entrenamiento A start contra B start, receta R peso 1 y lam 10; inferencia entera | abiertos, selección LOMO: Metrica 2-3 semillas 0-9, IDSSE 1-5 semillas 0-4 | {result}. {report['wall_s']:.1f} s | {verdict} |\n")
    print(json.dumps(dict(status=report["status"], decision=d, wall_s=report["wall_s"])), flush=True)
    if failure:
        raise failure


if __name__ == "__main__":
    main()
