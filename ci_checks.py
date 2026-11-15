"""Synthetic CI setup, script runner and strict cross-platform hash comparison (ADR-016).

python ci_checks.py scorer DIR     download only the pinned official scorer into DIR
python ci_checks.py tests          run each tests/test_*.py with this interpreter (python -m tests.NAME)
python ci_checks.py matrix         print the Actions matrix as JSON
python ci_checks.py compare DIR    validate all six downloaded metadata artifacts
"""
import argparse
import hashlib
from importlib.metadata import version
import itertools
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parent
REQUIREMENTS = ("requirements.txt", "requirements-train.txt", "requirements-ci.txt")
SOURCES = ("ci_config.json", "ci_checks.py", "repro_check.py", "possession.py",
           "stops_model.json", "live_model.json", *REQUIREMENTS)


def config():
    return json.loads((ROOT / "ci_config.json").read_text(encoding="utf-8"))


def dependencies():
    """The declared runtime versions, without importing the numerical stack."""
    pinned = {}
    for name in REQUIREMENTS:
        for line in (ROOT / name).read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith("-r "):
                continue
            package, value = line.split("==")
            pinned[package] = value
    return pinned


def common_metadata():
    cfg = config()
    # Git may check out source files with CRLF on Windows. Only source hashes are normalised;
    # the synthetic CSV's digest always covers the exact bytes written by possession.write_csv.
    sources = {name: hashlib.sha256((ROOT / name).read_text(encoding="utf-8").encode("utf-8")).hexdigest()
               for name in SOURCES}
    return {"schema": 1, "fixture": cfg["fixture"], "scorer": cfg["scorer"],
            "dependencies": dependencies(), "sources": sources}


def scorer_bytes(content):
    if hashlib.sha256(content).hexdigest() != config()["scorer"]["sha256"]:
        raise ValueError("official scorer SHA-256 differs from ci_config.json")
    return content


def download_scorer(destination):
    scorer = config()["scorer"]
    url = (f'https://raw.githubusercontent.com/{scorer["repository"]}/{scorer["revision"]}'
           '/evaluation/possession_metrics.py')
    with urllib.request.urlopen(url, timeout=60) as response:
        content = scorer_bytes(response.read())
    path = Path(destination) / "evaluation" / "possession_metrics.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    print(f'official scorer {scorer["revision"]} sha256 {scorer["sha256"]}')


def check_environment():
    if sys.flags.optimize or os.environ.get("PYTHONOPTIMIZE", "0") not in ("", "0"):
        raise ValueError("synthetic tests require assertions: remove -O and PYTHONOPTIMIZE")
    if platform.python_implementation() != "CPython" or platform.python_version() not in config()["matrix"]["python"]:
        raise ValueError("use a CPython version pinned in ci_config.json")
    expected = dependencies()
    if {package: version(package) for package in expected} != expected:
        raise ValueError("install the exact versions in requirements-ci.txt")
    official = Path(os.environ.get("MTAH_OFFICIAL", ROOT.parent / "mtah2027"))
    scorer_bytes((official / "evaluation" / "possession_metrics.py").read_bytes())


def run_tests(root=ROOT):
    """Execute main blocks too; unittest discovery alone misses script assertions."""
    tests = sorted((Path(root) / "tests").glob("test_*.py"))
    if not tests:
        raise ValueError("no synthetic test scripts found")
    env = dict(os.environ, PYTHONUTF8="1")
    env.pop("MTAH_DATA", None)
    for path in tests:
        print(f"== {path.name}", flush=True)
        subprocess.run([sys.executable, "-u", "-m", f"tests.{path.stem}"], cwd=root, env=env, check=True)
    print(f"OK: {len(tests)} synthetic test scripts", flush=True)


def runtime_metadata(runner):
    cfg = config()
    if runner not in cfg["matrix"]["os"] or cfg["systems"][runner] != platform.system():
        raise ValueError("runner does not match this operating system")
    return {"runner": runner, "system": platform.system(), "python": platform.python_version()}


def validate_report(report, runner, python, common):
    if not isinstance(report, dict) or set(report) != set(common) | {"runtime", "counts", "sha256"}:
        raise ValueError("unexpected metadata fields")
    if any(report[key] != value for key, value in common.items()):
        raise ValueError("fixture, scorer, dependencies or source revision differs")
    expected_runtime = {"runner": runner, "system": config()["systems"][runner], "python": python}
    if report["runtime"] != expected_runtime:
        raise ValueError("runtime does not match its matrix job")
    if not isinstance(report["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", report["sha256"]):
        raise ValueError("invalid CSV SHA-256")
    counts = report["counts"]
    if (not isinstance(counts, dict) or set(counts) != set("HADX")
            or any(type(v) is not int or v <= 0 for v in counts.values())
            or sum(counts.values()) != common["fixture"]["frames"]):
        raise ValueError("counts must cover every frame and all four labels")


def compare_reports(directory):
    cfg, directory = config(), Path(directory)
    jobs = {f"hash-{runner}-{python}": (runner, python)
            for runner, python in itertools.product(cfg["matrix"]["os"], cfg["matrix"]["python"])}
    actual = {p.name for p in directory.iterdir()}
    if actual != set(jobs):
        raise ValueError(f"incomplete matrix: missing {sorted(set(jobs) - actual)}, extra {sorted(actual - set(jobs))}")
    common, results = common_metadata(), []
    for name, (runner, python) in jobs.items():
        folder = directory / name
        if not folder.is_dir() or {p.name for p in folder.iterdir()} != {"synthetic.json"}:
            raise ValueError(f"{name}: expected only synthetic.json")
        report = json.loads((folder / "synthetic.json").read_text(encoding="utf-8"))
        validate_report(report, runner, python, common)
        results.append((report["sha256"], report["counts"]))
        print(f'{name}: {report["sha256"]}')
    if any(result != results[0] for result in results[1:]):
        raise ValueError("synthetic CSV bytes or label counts differ across the matrix")
    print(f"OK: {len(jobs)} jobs, one synthetic CSV SHA-256 {results[0][0]}")
    return results[0][0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("matrix")
    commands.add_parser("tests")
    for name in ("scorer", "compare"):
        commands.add_parser(name).add_argument("directory", type=Path)
    args = parser.parse_args()
    if args.command == "matrix":
        print(json.dumps(config()["matrix"], separators=(",", ":")))
    elif args.command == "scorer":
        download_scorer(args.directory)
    elif args.command == "tests":
        check_environment()
        run_tests()
    else:
        compare_reports(args.directory)


if __name__ == "__main__":
    main()
