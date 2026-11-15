"""Forensic replay of only #77's default confirmation, fixed weights 1/3 and seeds 50.

This is a partial replay on an already exposed external reserve, not a fresh validation or a tuning step.
It never loads challenge assets, creates B, exports a model, or selects a recipe.
"""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = ROOT.parent / "historical"
EVIDENCE = ROOT / "docs" / "evidence" / "issue111"
sys.path.insert(0, str(HISTORICAL))
saved_argv, sys.argv = sys.argv, [sys.argv[0]]
import calibrate_live as CL
sys.argv = saved_argv


def sha(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    started = time.time()
    name, recipe = CL.chosen()
    if recipe != {"leaves": 63, "lam": 10} or CL.SHORT_S != 5:
        raise ValueError("Historical recipe differs from the recovered command")
    immutable = {filename: sha(HISTORICAL / filename)
                 for filename in ("calibrate_live.py", "live_choice.json", "live_model.json")}
    rows = [(match, *CL.game_rows(game)) for match in CL.CE.SELECTION for game in CL.CE.load(match)]
    reserve = {match: CL.CE.load(match) for match in CL.CE.RESERVE}
    benches = (("Metrica", reserve[("metrica", 1)], range(50, 60)),
               ("IDSSE", reserve[("idsse", 6)] + reserve[("idsse", 7)], range(50, 55)))
    results, models = [], {}
    for weight in (1, 3):
        CL.SHORT_WEIGHT = weight
        clf = CL.fit(rows, recipe["leaves"])
        scorer = CL.sklearn_scorer(clf)
        exported = {"mode": "model", "switch": CL.switch_of(recipe["lam"]), "trees": CL.CE.export(clf)}
        models[str(weight)] = hashlib.sha256(CL.to_json(exported).encode()).hexdigest()
        for bench, games, seeds in benches:
            predictions = CL.score(games, {name: (scorer, CL.switch_of(recipe["lam"]))}, seeds,
                                   CL.CE.SCENARIOS["default"], true_d=True)
            for (anchor, _), (point, lo, hi, per_game) in CL.bench.compare(predictions, "radio", name, 1000).items():
                row = {"weight": weight, "bench": bench, "anchor": anchor,
                       "point": point, "lo": lo, "hi": hi,
                       "positive_units": sum(value > 0 for value in per_game.values()), "units": len(per_game)}
                results.append(row)
                print(json.dumps(row), flush=True)
    after = {filename: sha(HISTORICAL / filename) for filename in immutable}
    if after != immutable:
        raise ValueError("Partial confirmation modified an immutable historical input")
    report = {"command": "audit_77_default_confirmation.py", "revision": "67b8fe6", "recipe": recipe,
              "python": sys.version, "packages": {name: importlib.metadata.version(name)
                                                    for name in ("numpy", "scikit-learn", "scipy")},
              "thread_environment": {name: os.environ.get(name)
                                     for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")},
              "source_file": str(Path(CL.__file__).resolve()), "script_sha256": sha(Path(__file__)),
              "input_manifest_sha256": sha(EVIDENCE / "current-inputs.json"),
              "revision_manifest_sha256": sha(EVIDENCE / "current-revisions.json"),
              "reserve": "External Metrica 1 and IDSSE 6-7; already exposed; fixed forensic replay only",
              "seeds": {"metrica": list(range(50, 60)), "idsse": list(range(50, 55))},
              "model_hashes_trained_on_selection": models, "results": results,
              "immutable_files_before": immutable, "immutable_files_after": after,
              "conditions_replayed": 3, "full_43_conditions_replayed": False,
              "model_exported": False, "B_loaded": False, "seconds": time.time() - started}
    path = EVIDENCE / "confirmation-default-current.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": path.name, "sha256": sha(path), "seconds": report["seconds"]}), flush=True)


if __name__ == "__main__":
    main()
