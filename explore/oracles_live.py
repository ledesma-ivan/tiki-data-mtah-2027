"""Oracles on top of the live-play model (ADR-014): how much the stops could still give (step 0 of the next #32 candidate).

Usage: python explore/oracles_live.py [--held metrica:2,idsse:1] [--seeds-metrica 10] [--seeds-idsse 5] [--draws 1000]
Open data only (AGENTS.md), selection matches only (Metrica 2-3, IDSSE 1-5): the reserve stays untouched.

The pipeline of main since ADR-014: dead_mask_v2 with the identity stop model, then the live model and its Viterbi in
each live stretch. The live model follows calibrate_live.py's recipe (63 leaves, lambda 10), trained on the 6 selection
matches other than the scored one (LOMO) and scored with decision_function, as calibrate_live.py --select. Rows fix one
kind of D error with the truth, as explore/oracles.py; the second column also starts each live stretch with its true
first team (#34), as a bonus on its first frame. An oracle is a ceiling, not an expected gain.
"""
import argparse
import os
import pickle
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "explore"))
_argv, sys.argv = sys.argv, sys.argv[:1]  # possession, calibrate_dead and idsse_dead_labels read sys.argv[1] at import
import bench  # noqa: E402
import calibrate_edges as CE  # noqa: E402
import calibrate_live as CL  # noqa: E402
import oracles as O  # noqa: E402
import possession as P  # noqa: E402
sys.argv = _argv

pm = bench.pm
LEAVES, LAM = 63, 10  # live_choice.json (ADR-014)
BONUS = 10 ** 12  # far above any switch (2 * lambda * SCALE): the stretch starts with that team
COLS = ("live", "live + restart team")


def decode(dead, score, spans, switch, first=None):
    """possession.segment_live; with first (a truth), each live stretch starts with its first true team."""
    if first is not None:
        score = score.copy()
        for a, b in spans:
            for s, e in P.runs(~dead[a:b]):
                t = first[a + s:a + e]
                k = np.flatnonzero((t == "H") | (t == "A"))
                if len(k):
                    score[a + s] += BONUS if t[k[0]] == "H" else -BONUS
    return P.segment_live(dead, score, spans, switch)


def held_out(game, scorer, switch, seeds):
    """{(D row, column): [label codes per seed]} for one game, and ("v2", "radio") for reference."""
    truth = CL.truth_of(game)
    spans = pm.valid_runs(pm.label_codes(truth))
    by = {}
    for s in seeds:
        ball = CE.degraded(game, 1000 * game.g + s)
        ev = bench.radio_evidence(game.players, ball, game.team, pitch=game.pitch)
        v2 = P.dead_mask_v2(game.players, ball)
        by.setdefault(("v2", "radio"), []).append(pm.label_codes(bench.segment(v2, ev, spans, P.CHANGE_FRAMES, P.MAX_GAP)))
        for row, dead in O.d_variants(v2, game.dead).items():
            FH, FA = P.live_features(game.players, ball, game.team, ev, dead, spans, game.pitch)
            score = scorer(FH) - scorer(FA)
            for col, first in zip(COLS, (None, truth)):
                by.setdefault((row, col), []).append(pm.label_codes(decode(dead, score, spans, switch, first)))
    return pm.label_codes(truth), by


def report(name, per_game, draws):
    keys = list(next(iter(per_game.values()))[1])
    point = {g: np.arange(len(pm.possession_spells(gt, pm.valid_runs(gt))))[None] for g, (gt, _) in per_game.items()}
    mean = {k: np.mean([np.mean([bench.spell_draws(gt, p, point[g])[0] for p in by[k]]) for g, (gt, by) in per_game.items()])
            for k in keys}
    print(f"\n=== {name}: spellF1, mean over games and seeds (default degraded ball, clean players) ===")
    print(f"  {'D':16}" + "".join(f"{c:>22}" for c in COLS))
    for row in O.D_ROWS:
        print(f"  {row:16}" + "".join(f"{mean[(row, c)]:22.3f}" for c in COLS))
    print(f"  (radio, v2: {mean[('v2', 'radio')]:.3f})")
    base = ("v2", "live")
    print(f"\n--- {name}: paired difference against v2 + live, 5-95% ({draws} draws)")
    for key in [("v2", "radio")] + [(r, c) for r in O.D_ROWS for c in COLS if (r, c) != base]:
        p, lo, hi, games = O.paired(per_game, base, key, draws)
        print(f"  {key[0]:16} {key[1]:22} {p:+.3f} [{lo:+.3f}, {hi:+.3f}]  above 0 in "
              f"{sum(d > 0 for d in games.values())}/{len(games)}", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--held", default="", help="matches to score, e.g. metrica:2,idsse:1 (default: the 7 of the selection)")
    ap.add_argument("--seeds-metrica", type=int, default=10)
    ap.add_argument("--seeds-idsse", type=int, default=5)
    ap.add_argument("--draws", type=int, default=1000)
    ap.add_argument("--save", default="", help="pickle of the labels, to report again without recomputing")
    a = ap.parse_args()
    held = [(k, int(v)) for k, v in (x.split(":") for x in a.held.split(",") if x)] or list(CE.SELECTION)
    assert set(held) <= set(CE.SELECTION), "selection matches only: the reserve stays untouched"
    seeds = {"metrica": range(a.seeds_metrica), "idsse": range(a.seeds_idsse)}
    t0 = time.time()
    games = {m: CE.load(m) for m in CE.SELECTION}
    rows = {m: [(m, *CL.game_rows(g)) for g in games[m]] for m in CE.SELECTION}
    print(f"rows: {sum(len(r[2]) for m in rows for r in rows[m])} ({time.time() - t0:.0f} s)", flush=True)
    switch = CL.switch_of(LAM)
    per = {"metrica": {}, "idsse": {}}
    for m in held:
        scorer = CL.sklearn_scorer(CL.fit([r for x in CE.SELECTION if x != m for r in rows[x]], LEAVES))
        for game in games[m]:
            per[m[0]][game.g] = held_out(game, scorer, switch, seeds[m[0]])
        if m == held[0]:  # the baseline is calibrate_live.py's pipeline, frame by frame
            g0 = games[m][0]
            anchor = "start" if m[0] == "metrica" else "status"
            ref = CL.score([g0], {"m": (scorer, switch)}, seeds[m[0]][:1], anchors={anchor})[(g0.g, anchor, "degraded", "m")]
            assert (pm.label_codes(ref[1][0]) == per[m[0]][g0.g][1][("v2", "live")][0]).all(), "baseline differs"
        print(f"  left out {m}: done ({time.time() - t0:.0f} s)", flush=True)
    if a.save:
        with open(a.save, "wb") as f:
            pickle.dump(per, f)
    for bench_name, title in (("metrica", "Metrica (Games 2-3)"), ("idsse", "IDSSE (1-5)")):
        if per[bench_name]:
            report(title, per[bench_name], a.draws)
    print(f"\ndone in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
