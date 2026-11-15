"""Does weighting the short possessions in training help? (open data only; changes no label, threshold or model file)

Another team of the challenge counts the possessions under 5 s three times in training. Same LOMO as `calibrate_live.py --select` over
the 7 selection matches, the ADR-014 recipe only, with each given weight for the frames whose true possession lasts less
than CL.SHORT_S (the first weight is the control). Prints the paired spellF1 difference against radio per bench and the
games that beat the control.

    python explore/short_weight.py [--weights 1 3 5]

This script picked 3 (#77), but it did not confirm against weight 1 (ADR-019: 41 of 43), so calibrate_live.py trains
with SHORT_WEIGHT = 1 again (#91); the control is --weights 1. The confirmation of a weight against another one is
`calibrate_live.py --confirm` (ADR-019), for #77, with weight 3 delivered: `--reference short_weight=1 --seed-start 70`.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
_argv, sys.argv = sys.argv, sys.argv[:1]  # possession and calibrate_dead read sys.argv[1] at import
import calibrate_live as CL  # noqa: E402
CE = CL.CE
sys.argv = _argv


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--weights", type=float, nargs="+", default=[1, 3])
    a = ap.parse_args()
    _, recipe = CL.chosen()
    games = {m: CE.load(m) for m in CE.SELECTION}
    rows = {m: [(m, *CL.game_rows(g)) for g in games[m]] for m in CE.SELECTION}
    diffs = {w: {} for w in a.weights}
    for held in CE.SELECTION:
        train = [r for m in CE.SELECTION if m != held for r in rows[m]]
        models = {f"w{w:g}": (CL.sklearn_scorer(CL.fit(train, recipe["leaves"], short_weight=w)), CL.switch_of(recipe["lam"]))
                  for w in a.weights}
        preds = CL.score(games[held], models, CE.SEEDS["select"][held[0]], anchors={"start", "status"})
        for w in a.weights:
            diffs[w].update(CE.per_game(preds, f"w{w:g}"))
        print(f"  left out {held}: done", flush=True)
    print(f"\nselection (LOMO, {recipe}): paired spellF1 difference against radio; short = true possession < {CL.SHORT_S} s")
    print(f"  {'weight':8} {'Metrica':>8} {'IDSSE':>8} {'mean':>8}   games better than control")
    base = diffs[a.weights[0]]
    for w in a.weights:
        m, i, both = CE.bench_means(diffs[w])
        wins = sum(diffs[w][k] > base[k] for k in base)
        print(f"  {w:<8g} {m:+8.4f} {i:+8.4f} {both:+8.4f}   {wins}/{len(base)}")


if __name__ == "__main__":
    main()
