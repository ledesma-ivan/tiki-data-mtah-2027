"""Audit fixed #77 commands on permitted external inputs; never load challenge assets or B.

Run with MTAH_OFFICIAL pointing to the official code repository and fixed thread settings.
Outputs are provenance, aggregate metrics and hashes only. Historical --final runs in its own worktree.
"""
import argparse
import ast
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = ROOT.parent / "historical"
EVIDENCE = ROOT / "docs" / "evidence" / "issue111"
EXPECTED_MODEL = "1e0579ad8232de7579ac3df6a4d49768fa6702e374e20c57ee9cec2bcb2a8ddf"


def digest(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(name, value):
    path = EVIDENCE / name
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": name, "sha256": digest(path)}, ensure_ascii=False), flush=True)


def revision(tree):
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={tree.as_posix()}", "-C", str(tree), "rev-parse", "HEAD"],
        text=True, encoding="utf-8").strip()


def environment():
    return {"python": sys.version, "executable": sys.executable, "platform": sys.platform,
            "packages": {name: importlib.metadata.version(name) for name in
                         ("numpy", "pandas", "scikit-learn", "scipy", "threadpoolctl")},
            "thread_environment": {name: os.environ.get(name) for name in
                                   ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")},
            "official_code": os.environ.get("MTAH_OFFICIAL"),
            "historical_environment": "SIN CONFIRMAR", "historical_data_revision": "SIN CONFIRMAR"}


def function_body(path, name, replacements=None):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    body = fn.body[1:] if isinstance(fn.body[0], ast.Expr) and isinstance(fn.body[0].value, ast.Constant) else fn.body

    class Replace(ast.NodeTransformer):
        def visit_Name(self, node):
            return ast.copy_location(ast.Name(id=(replacements or {}).get(node.id, node.id), ctx=node.ctx), node)

    return ast.dump(Replace().visit(ast.Module(body=body, type_ignores=[])), include_attributes=False)


def verify_selection():
    started = time.time()
    sys.path.insert(0, str(ROOT))
    saved_argv, sys.argv = sys.argv, [sys.argv[0]]
    import calibrate_live as cl
    sys.argv = saved_argv
    previous_path = ROOT / "live_reconstruction.json"
    previous = json.loads(previous_path.read_text(encoding="utf-8"))
    expected_selection = [("metrica", 2), ("metrica", 3)] + [("idsse", n) for n in range(1, 6)]
    if list(cl.CE.SELECTION) != expected_selection:
        raise ValueError("Unexpected external selection partition")
    rows = {}
    for match in cl.CE.SELECTION:
        games = cl.CE.load(match)
        expected_halves = 2 if match[0] == "idsse" else 1
        if len(games) != expected_halves or any(game.match != match for game in games):
            raise ValueError("Incomplete whole-match group")
        rows[match] = [(match, *cl.game_rows(game, 5)) for game in games]
        print(json.dumps({"external_group": match, "training_rows": sum(len(row[2]) for row in rows[match])}), flush=True)
    checks, row_checks = [], 0
    for fold in previous["folds"]:
        training = [tuple(match) for match in fold["training"]]
        evaluation = [tuple(match) for match in fold["evaluation"]]
        if set(training) & set(evaluation) or set(training + evaluation) != set(expected_selection):
            raise ValueError("Invalid historical exclusion group")
        observed = cl.fingerprint([row for match in training for row in rows[match]])
        for name in ("reference", "candidate"):
            expected = fold["fingerprints"][name]
            checks.append({"evaluation": evaluation, "model": name,
                           "fields_equal": {key: observed[key] == expected[key] for key in observed}})
            row_checks += sum(observed["rows"].get(key) == value for key, value in expected["rows"].items())
    code_checks = {name: function_body(HISTORICAL / "calibrate_live.py", name, replacements) ==
                  function_body(ROOT / "calibrate_live.py", name)
                  for name, replacements in (("fit", {"SHORT_WEIGHT": "short_weight"}),
                                             ("game_rows", {"SHORT_S": "short_s"}), ("score", {}))}
    code_checks.update({name: function_body(HISTORICAL / "calibrate_edges.py", name) ==
                       function_body(ROOT / "calibrate_edges.py", name)
                       for name in ("per_game", "bench_means", "degraded")})
    targets = {("Metrica", "start"): 0.0026, ("IDSSE", "status"): 0.0157}
    gate = []
    for (bench, anchor), expected in targets.items():
        result = next(row for row in previous["results"] if row["bench"] == bench and row["anchor"] == anchor)
        got = result["difference"]["point"]
        gate.append({"bench": bench, "anchor": anchor, "expected": expected, "observed": got,
                     "absolute_error": abs(got - expected), "tolerance": 0.0001,
                     "passes": abs(got - expected) <= 0.0001 + 1e-12})
    report = {"command": "audit_77_reproduction.py --fingerprints", "environment": environment(),
              "code": {"diagnostic": revision(ROOT), "historical": revision(HISTORICAL)},
              "inputs_manifest_sha256": digest(EVIDENCE / "current-inputs.json"),
              "previous_report_sha256": digest(previous_path), "previous_code": previous["code"],
              "fingerprints": checks, "matching_row_correspondences": row_checks,
              "code_body_equal_after_explicit_weight_parameterization": code_checks,
              "complete_primary_A_gate": gate, "B_loaded": False, "reserve_loaded": False,
              "new_models_fitted": 0, "previous_results_reused": True,
              "reuse_scope": "Prior aggregate A results and verified training rows; prior full evaluation-input hashes unavailable",
              "seconds": time.time() - started}
    write("selection-input-verification.json", report)
    print(json.dumps({"row_correspondences_equal": row_checks,
                      "all_fingerprint_fields_equal": all(all(check["fields_equal"].values()) for check in checks),
                      "code_checks": code_checks, "primary_A_checks": gate}), flush=True)


def historical_command(stage):
    command = [sys.executable] + (["calibrate_live.py", "--final"] if stage == "final" else
                                 ["explore/short_weight.py", "--weights", "1", "3", "5"])
    model = HISTORICAL / "live_model.json"
    choice = HISTORICAL / "live_choice.json"
    before = {"model": digest(model), "choice": digest(choice)}
    record = {"command": command, "cwd": str(HISTORICAL), "environment": environment(),
              "revision": revision(HISTORICAL), "before": before,
              "inputs_manifest_sha256": digest(EVIDENCE / "current-inputs.json"),
              "expected_historical_model_sha256": EXPECTED_MODEL}
    write(f"{stage}-current-invocation.json", record)
    started = time.time()
    log = EVIDENCE / f"{stage}-current.txt"
    with log.open("w", encoding="utf-8", newline="\n") as stream:
        process = subprocess.Popen(command, cwd=HISTORICAL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding="utf-8", errors="replace")
        for line in process.stdout:
            stream.write(line)
            stream.flush()
            print(line, end="", flush=True)
        returncode = process.wait()
    record.update(exit_code=returncode, seconds=time.time() - started,
                  after={"model": digest(model), "choice": digest(choice)},
                  log_sha256=digest(log), log_file=log.name)
    record["model_exported"] = stage == "final" and returncode == 0
    record["matches_historical_model"] = (returncode == 0 and record["after"]["model"] == EXPECTED_MODEL
                                          if stage == "final" else None)
    write(f"{stage}-current-result.json", record)
    print(json.dumps({"exit_code": returncode, "model_sha256": record["after"]["model"],
                      "matches_historical_model": record["matches_historical_model"],
                      "choice_unchanged": before["choice"] == record["after"]["choice"],
                      "seconds": record["seconds"]}), flush=True)
    if returncode:
        raise SystemExit(returncode)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--fingerprints", action="store_true")
    action.add_argument("--historical-final", action="store_true")
    action.add_argument("--historical-selection", action="store_true")
    args = parser.parse_args()
    if args.fingerprints:
        verify_selection()
    else:
        historical_command("final" if args.historical_final else "selection")
