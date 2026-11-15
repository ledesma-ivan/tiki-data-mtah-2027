"""What brings an edge model trained on IDSSE to Metrica's stop edges: the speed or the convention (#32, ADR-018, step 0).

Usage: python explore/edge_transfer.py [--seeds 3]
Needs calibrate_edges.py and possession.py of branch feat/bordes-convencion-metrica-32-34-codigo (ADR-018, Rejected):
main does not keep that recipe, so this script runs there, not on main.
ADR-010's model, trained on both benches, overshot in Metrica ("Por qué Metrica no acompaña"). Here the edge model of
ADR-018's recipe (ADR-010's 3 s windows and 31 leaves, its training balls plus a hidden one, clean and noisy players,
weights that average 1 and out-of-fold kinds) is trained on IDSSE 1-5 alone, three ways, and scored on the stops of
Metrica Games 2-3, which it never saw:
- provider: as ADR-010 trains IDSSE, with the provider's speeds;
- positions: with speeds from the positions, computed as the Metrica bench does;
- Metrica convention: the provider's speeds, and the free kicks' D starting at the infringement, where Metrica's
  truth starts it (calibrate_edges.dfl_clock).
IDSSE kinds are on the corrected DFL clock in the three. References: the v2 edges, and a model trained on the other
Metrica selection game (same recipe, its own kinds). The ball is degraded as in the bench (45% of live frames, 1.5 s gaps)
and the models are scored twice: seeing it, as the bench's pipeline does, and with it hidden from them (dead_mask_v2
still sees it; the kind classifier does not), as they are trained in Metrica. In Metrica the bench restores the ball of
the stops (ADR-007). Every model is scored on the same true stops: one it no longer covers by half is a miss, and the
medians are over the stops that every model covers.
Open data only (AGENTS.md): the selection matches of ADR-010 (Metrica 2-3, IDSSE 1-5); the reserve is not touched.
"""
import argparse
import collections
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
_argv, sys.argv = sys.argv, sys.argv[:1]  # calibrate_edges' imports read sys.argv[1]
import calibrate_edges as C  # noqa: E402
import possession as P  # noqa: E402
sys.argv = _argv

FPS = P.FPS
IDSSE = tuple(("idsse", m) for m in range(1, 6))
METRICA = (("metrica", 2), ("metrica", 3))


def rows_of(games):
    """calibrate_edges.match_rows for these games, match by match."""
    out = []
    for m in sorted({g.match for g in games}):
        out += C.match_rows(m, [g for g in games if g.match == m])
    return out


def model_of(rows, convention="provider"):
    return C.train(rows, {"m": dict(mode="model", convention=convention, radius=0)})["m"]


def offsets(game, models, seeds, hidden=False):
    """{(name, kind): [(start offset, end offset) or None]} in frames (+ = late), one entry per true stop with a kind
    and seed, in the same order for the v2 ("v2") and each model; None where that model's stops do not cover it by
    half. hidden: the models do not see the ball."""
    out = collections.defaultdict(list)
    spans = C.spans_of(game)
    for s in seeds:
        ball = C.degraded(game, 1000 * game.g + s)
        v2 = P.dead_mask_v2(game.players, ball)
        seen = np.full_like(ball, np.nan) if hidden else ball
        F = P.frame_features(game.players, seen, game.pitch)
        dead = {"v2": v2} | {name: P.refine(v2, game.players, seen, game.team, spans, m, game.pitch, F)[0]
                             for name, m in models.items()}
        for name, d in dead.items():
            r = P.runs(d)
            for a, b, k in game.kinds:
                if k < 0:
                    continue
                over = [(c, e) for c, e in r if c < b and e > a]
                covered = over and sum(min(b, e) - max(a, c) for c, e in over) >= 0.5 * (b - a)
                out[(name, k)].append((min(c for c, _ in over) - a, max(e for _, e in over) - b) if covered else None)
    return out


def cells(found, names, col):
    """Per model: share within 0.5 s over every true stop (a stop it does not cover is a miss) and median offset in s
    over the stops that every model covers; and how many those are."""
    n = len(found[names[0]])
    paired = [i for i in range(n) if all(found[name][i] is not None for name in names)]
    out = []
    for name in names:
        hit = sum(x is not None and abs(x[col]) <= FPS // 2 for x in found[name]) / n
        med = f"{np.median([found[name][i][col] for i in paired]) / FPS:+5.2f}" if paired else "  n/a"
        out.append(f"{hit:4.0%} {med}")
    return out, len(paired)


def report(found, names, title):
    print("\n" + title)
    kinds = sorted({k for _, k in found})
    groups = [(P.KINDS[k], {name: found[(name, k)] for name in names}) for k in kinds]
    groups.append(("all kinds", {name: [x for k in kinds for x in found[(name, k)]] for name in names}))
    for label, rows in groups:
        n = len(rows[names[0]])
        print(f"  {label:12} stops {n:4}, covered by half: " + "  ".join(
            f"{name} {sum(x is not None for x in rows[name]) / n:4.0%}" for name in names))
        for edge, col in (("start", 0), ("end", 1)):
            out, paired = cells(rows, names, col)
            print(f"  {'':12} {edge:5} paired {paired:4}  " + "  ".join(f"{name}: {c}" for name, c in zip(names, out)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seeds", type=int, default=3)
    a = ap.parse_args()
    t0 = time.time()
    idsse = {speed: [g for m in IDSSE for g in C.load(m, speed, clock=True)] for speed in ("provider", "positions")}
    ratio = []
    for g in idsse["positions"]:
        prov = next(p for p in idsse["provider"] if p.g == g.g).players[:, :, 2]
        pos = g.players[:, :, 2]
        moving = pos > 2
        ratio.append(np.nanmedian(prov[moving] / pos[moving]))
    print(f"IDSSE 1-5: provider speed / speed from the positions, median per half over players at > 2 m/s: "
          f"{min(ratio):.3f} to {max(ratio):.3f}", flush=True)
    metrica = {m: C.load(m) for m in METRICA}
    rows = rows_of(idsse["provider"])
    models = {"provider": model_of(rows), "positions": model_of(rows_of(idsse["positions"])),
              "Metrica convention": model_of(rows, "metrica")}
    del rows
    print(f"trained on IDSSE 1-5 ({time.time() - t0:.0f} s)", flush=True)
    views = {False: collections.defaultdict(list), True: collections.defaultdict(list)}
    for m in METRICA:
        other = next(x for x in METRICA if x != m)
        own = {**models, "Metrica, other game": model_of(rows_of(metrica[other]))}
        for g in metrica[m]:
            for hidden, found in views.items():
                for key, v in offsets(g, own, range(a.seeds), hidden).items():
                    found[key] += v
    names = ["v2", "provider", "positions", "Metrica convention", "Metrica, other game"]
    for hidden, found in views.items():
        report(found, names, f"Metrica Games 2-3, seeds 0-{a.seeds - 1}, the ball {'hidden from' if hidden else 'seen by'} "
               f"the models: edges against the truth by kind, share of every true stop within 0.5 s (uncovered = miss) and "
               f"median s over the stops every model covers (+ = late) "
               f"({time.time() - t0:.0f} s)")
