"""Joint sweep of control radius R, N, interpolation cap and max_gap (issue #33, ADR-009).

Open data only (Metrica Sample Games), the bench's ball degradation (ADR-006). D is the true D
("oracle", isolates the evidence) or the v1 detector. Each row is the mean spellF1 over the games and the
scenarios: the ball as is and the degraded ball with the given seeds. Prints aggregates only.

Usage: python explore/radius_sweep.py --games 2,3 --seeds 3 --dead true
       python explore/radius_sweep.py --games 2,3 --seeds 3 --dead true --truth-variant B
       python explore/radius_sweep.py --games 1 --seeds 10 --seed-start 20 --dead true   (confirmation)
One truth variant per run: A by default, B for ADR-005 sensitivity; both use the start anchor.
"""
import argparse
import itertools
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bench  # noqa: E402
import calibrate_dead  # noqa: E402
import possession  # noqa: E402

FPS = possession.FPS
RADII = [0.75, 1.0, 1.5, 2.0, np.inf]
N_SEC = [0.25, 0.5, 1.0, 2.0]
INTERP = [None, 12, 25, 50, 10**9]  # None = hold the last position (ADR-001); frames otherwise; 10**9 = no cap
GAPS = [6, 12, 25]  # frames
CURRENT = (np.inf, 2.0, None, bench.BASE_GAP)  # the frozen v1 rule, the baseline of EXPERIMENTOS


def scenarios(game, seeds, seed_start, truth_variant="A"):
    if truth_variant not in ("A", "B"):
        raise ValueError("truth_variant must be 'A' or 'B'")
    players, ball, team, events, pitch = bench.load_game(game)
    n = len(ball)
    dead = calibrate_dead.dead_labels([e[:5] for e in events], n)
    graded = np.zeros(n, bool)
    for first, last in calibrate_dead.halves([e[:5] for e in events]):
        graded[first:last + 1] = True
    truth = bench.truth_labels(events, n, dead, "start", variant=truth_variant)
    spans = bench.pm.valid_runs(bench.pm.label_codes(truth))
    balls = [("as is", ball)] + [("degraded", bench.degrade(ball, players, dead, 0.45, 1.5, 0.0, 1000 * game + s, graded, 0.0, pitch=pitch))
                                 for s in range(seed_start, seed_start + seeds)]
    return players, team, dead, truth, spans, balls, pitch


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", default="2,3")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--seed-start", type=int, default=0)
    ap.add_argument("--dead", choices=["true", "v1"], default="true")
    ap.add_argument("--truth-variant", choices=["A", "B"], default="A",
                    help="ADR-005 reference labels: A by default, B for sensitivity (start anchor)")
    ap.add_argument("--top", type=int, default=12)
    for name, default in (("radii", RADII), ("n", N_SEC), ("interp", INTERP), ("gaps", GAPS)):
        ap.add_argument(f"--{name}", default=None, help=f"comma list, default {default}; inf = no limit, hold = None (interp)")
    args = ap.parse_args(argv)
    games = [int(g) for g in args.games.split(",")]
    pick = lambda text, default, cast: default if text is None else [
        None if t == "hold" else (np.inf if t == "inf" and cast is float else (10**9 if t == "inf" else cast(t))) for t in text.split(",")]
    grid = list(itertools.product(pick(args.radii, RADII, float), pick(args.n, N_SEC, float),
                                  pick(args.interp, INTERP, int), pick(args.gaps, GAPS, int)))
    if CURRENT not in grid:
        grid.append(CURRENT)
    scores = {c: {"as is": [], "degraded": []} for c in grid}
    for game in games:
        players, team, true_dead, truth, spans, balls, pitch = scenarios(
            game, args.seeds, args.seed_start, truth_variant=args.truth_variant)
        for kind, ball in balls:
            dead = true_dead if args.dead == "true" else possession.dead_mask(players, ball)
            cache = {}
            for radius, n_sec, interp, gap in grid:
                key = (radius, interp)
                if key not in cache:
                    cache[key] = bench.owner_evidence(players, ball, team, radius=radius, max_interp=interp, pitch=pitch)
                pred = bench.segment(dead, cache[key], spans, round(n_sec * FPS), gap)
                scores[(radius, n_sec, interp, gap)][kind].append(bench.score(truth, pred, 0)["spell"])
        print(f"game {game} done", file=sys.stderr, flush=True)

    rows = []
    for c, s in scores.items():
        asis, deg = float(np.mean(s["as is"])), float(np.mean(s["degraded"]))
        rows.append((c, asis, deg, (asis + deg) / 2, min(asis, deg)))
    rows.sort(key=lambda r: -r[2])  # the degraded ball decides (ADR-006); the ball as is is only a check
    fmt = lambda c: f"R={c[0]:<4} N={c[1]:<4} interp={'hold' if c[2] is None else ('inf' if c[2] == 10**9 else c[2]):<4} gap={c[3]}"
    cur = next(r for r in rows if r[0] == CURRENT)
    print(f"possession truth variant: {args.truth_variant} (ADR-005), anchor: start")
    print(f"games {args.games}, D {args.dead}, seeds {args.seed_start}..{args.seed_start + args.seeds - 1}, "
          f"{len(grid)} combinations; columns: as is / degraded / mean / worst of the two; sorted by the degraded ball")
    print(f"current   {fmt(cur[0])}  {cur[1]:.3f} {cur[2]:.3f} {cur[3]:.3f} {cur[4]:.3f}")
    for c, a, d, m, w in rows[:args.top]:
        print(f"top       {fmt(c)}  {a:.3f} {d:.3f} {m:.3f} {w:.3f}")


if __name__ == "__main__":
    main()
