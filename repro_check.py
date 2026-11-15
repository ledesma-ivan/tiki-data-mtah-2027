"""Synthetic end-to-end run of possession.py for the cross-platform CI (#54, ADR-016).

Usage: python repro_check.py [out.csv] [--metadata report.json --runner macos-15]
Prints label counts and the CSV's sha256; by default the temporary CSV is deleted after hashing.
Builds a whole match of fake tracking (no match data, AGENTS.md), runs possession.label on it and writes the
CSV with possession.write_csv: evidence, dead-ball detector, stop model, live decoder and CSV writing all run.
The CI compares the printed sha256 across operating systems and Python versions: it must be the same.
The fixture itself is platform independent: PCG64 integers, integer arithmetic in centimetres, and one
correctly rounded division to normalise, so a different hash can only come from the pipeline.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile

import numpy as np

_argv, sys.argv = sys.argv, sys.argv[:1]  # possession reads sys.argv[1] at import
import possession as P  # noqa: E402
sys.argv = _argv

LENGTH_CM, WIDTH_CM = 10530, 6800  # possession.PITCH in centimetres
ACTIVE = 11  # tracked players per team; the other slots stay empty, like substitutes
SEED = 54
ROOT = Path(__file__).resolve().parent


def segments(rng, n):
    """(start, end, dead) stretches covering n frames: live 10-40 s, dead 3-20 s, alternating."""
    out, start, dead = [], 0, False
    while start < n:
        length = int(rng.integers(3 * P.FPS, 20 * P.FPS) if dead else rng.integers(10 * P.FPS, 40 * P.FPS))
        out.append((start, min(start + length, n), dead))
        start, dead = start + length, not dead
    return out


def fold(p, size):
    """Reflect an unbounded integer walk into [0, size]."""
    q = np.mod(p, 2 * size)
    return np.where(q > size, 2 * size - q, q)


def fixture(seed=SEED, n=P.N_FRAMES):
    """(players[n,46,3], ball[n,3], team[46]) of a fake match, normalised like the ATD."""
    rng = np.random.Generator(np.random.PCG64(seed))
    segs = segments(rng, n)
    step = np.empty((n, P.N_SLOTS, 2), np.int64)
    for a, b, dead in segs:  # cm per frame: live up to 24 per axis (~3 m/s), dead up to 2 (< 1.75 m/s)
        s = 2 if dead else 24
        step[a:b] = rng.integers(-s, s + 1, (b - a, P.N_SLOTS, 2), dtype=np.int64)
    start = np.stack([rng.integers(0, LENGTH_CM, P.N_SLOTS), rng.integers(0, WIDTH_CM, P.N_SLOTS)], 1)
    xy = start[None] + np.cumsum(step, axis=0)
    x, y = fold(xy[..., 0], LENGTH_CM), fold(xy[..., 1], WIDTH_CM)
    speed = (np.abs(step[..., 0]) + np.abs(step[..., 1])) * P.FPS / 100  # m/s, L1 is enough for a fixture
    players = np.stack([x / LENGTH_CM, y / WIDTH_CM, speed], -1)
    team = np.array(["H"] * (P.N_SLOTS // 2) + ["A"] * (P.N_SLOTS - P.N_SLOTS // 2))
    active = np.r_[np.arange(ACTIVE), P.N_SLOTS // 2 + np.arange(ACTIVE)]
    players[:, np.setdiff1d(np.arange(P.N_SLOTS), active)] = np.nan

    ball_cm = np.empty((n, 2), np.int64)
    for a, b, dead in segs:
        if dead:  # the ball rests where play stopped, a third of the time off the pitch
            rest = ball_cm[a - 1] if a else np.array([LENGTH_CM // 2, WIDTH_CM // 2])
            ball_cm[a:b] = [-150, rest[1]] if rng.integers(3) == 0 else rest
            continue
        t = a
        while t < b:  # a carrier, from either team, keeps it 0.5-8 s, the ball up to 50 cm off its feet
            u = min(t + int(rng.integers(P.FPS // 2, 8 * P.FPS)), b)
            k = active[rng.integers(len(active))]
            ball_cm[t:u, 0] = x[t:u, k] + rng.integers(-50, 51)
            ball_cm[t:u, 1] = y[t:u, k] + rng.integers(-50, 51)
            t = u
    ball = np.zeros((n, 3))
    ball[:, 0], ball[:, 1] = ball_cm[:, 0] / LENGTH_CM, ball_cm[:, 1] / WIDTH_CM
    t = 0
    while t < n:  # gaps of 1-75 frames, about a third of the frames, like occlusions
        g = int(rng.integers(1, 76))
        if rng.integers(3) == 0:
            ball[t:t + g] = np.nan
        t += g
    return players, ball, team


def synthetic_destination(path):
    """Keep synthetic files out of the delivery directory, including through symlinks."""
    destination = Path(path).resolve()
    if destination.is_relative_to((ROOT / "output").resolve()):
        raise ValueError("synthetic files must be written outside the repository's output directory")
    return destination


def run(out):
    """Use only generated arrays and the committed models; never call a tracking loader."""
    out = synthetic_destination(out)
    labels = P.label(*fixture())
    counts = {k: int((labels == k).sum()) for k in "HADX"}
    if len(labels) != P.N_FRAMES or sum(counts.values()) != P.N_FRAMES or not all(counts.values()):
        raise ValueError(f"the fixture must cover every frame and exercise every label: {counts}")
    digest = P.write_csv(labels, str(out))
    print("synthetic  " + "  ".join(f"{k} {v}" for k, v in counts.items()) + f"  sha256 {digest}")
    return digest, counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", nargs="?", type=Path)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--runner")
    args = parser.parse_args()
    if bool(args.metadata) != bool(args.runner):
        parser.error("--metadata and --runner must be used together")
    try:
        args.csv = synthetic_destination(args.csv) if args.csv else None
        args.metadata = synthetic_destination(args.metadata) if args.metadata else None
    except ValueError as error:
        parser.error(str(error))
    if args.metadata and args.csv and args.metadata == args.csv:
        parser.error("CSV and metadata must have different paths")
    if args.metadata:
        from ci_checks import check_environment, common_metadata, runtime_metadata, validate_report
        check_environment()
        common, runtime = common_metadata(), runtime_metadata(args.runner)
        if common["fixture"] != {"seed": SEED, "frames": P.N_FRAMES, "slots": P.N_SLOTS}:
            raise ValueError("fixture configuration differs from ci_config.json")
    with tempfile.TemporaryDirectory(prefix="mtah-synthetic-") as directory:
        digest, counts = run(args.csv or Path(directory) / "synthetic.csv")
    if args.metadata:
        report = {**common, "runtime": runtime, "counts": counts, "sha256": digest}
        validate_report(report, args.runner, runtime["python"], common)
        args.metadata.parent.mkdir(parents=True, exist_ok=True)
        args.metadata.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
