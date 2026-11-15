"""Candidates for option C of #91, also measured with Metrica's truth B (open data, selection only; changes no file).

CHALLENGE.md counts a change of possession only when the rival gains *controlled* possession: a touch without control,
a deflection or an aerial duel won without control do not count. Truth A of the Metrica bench (ADR-005, the one that
trains and confirms) changes the owner with every on-ball event; truth B confirms a rival only after two consecutive
on-ball events, closer to that definition. Each recipe is trained with the LOMO of `calibrate_live.py --select` over the
7 selection matches and scored against weight 1 with lambda 10 (the recipe before #77), on the same balls and players,
with truths A and B (Metrica, start anchor) and IDSSE's:

    python explore/candidates_91.py --part candidates   weights 2 and 3, weight 3 also trained with 1.0 m of position
                                                        noise, w1 + w3 (the mean, as lambda 20 on the sum), weight 1
                                                        trained with truth B, lambdas 15 and 20; default ball and 1.0 m
                                                        of position noise
    python explore/candidates_91.py --part lambda       lambda 10 to 30, with weight 1 and with weight 1 trained with B
    python explore/candidates_91.py --part noise        lambda 10 to 25 with weight 1, and weight 3, with the combined
                                                        noise of training and with 15% of cross-team swaps
    [--json PATH]                                       also writes every (game, seed, condition, truth, model) record

Prints per bench, condition and truth: spellF1, the paired difference against w1 (games or halves where it is better),
the difference against radio and the possessions predicted over the true ones; --part candidates also prints the recall
at IoU 0.5 by true duration and the precision by predicted duration. The reserve is never loaded (ADR-011), nor BAR-ATH
or the public window. Exploratory: it decides nothing; a candidate is confirmed on the reserve with a fixed protocol.
"""
import argparse
import collections
import json
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
_argv, sys.argv = sys.argv, sys.argv[:1]  # possession and calibrate_dead read sys.argv[1] at import
import calibrate_live as CL  # noqa: E402
sys.argv = _argv
CE, P, bench, pm = CL.CE, CL.P, CL.bench, CL.pm
N10 = CL.NOISE["position noise 1.0 m per axis (1 s correlated)"]
BUCKETS = (0, 2, 5, 15, 1e9)  # seconds
T0 = time.time()


def parts(lam):
    """{part: (conditions, fits, decodes)}. fits: {name: (training variants, truth, short weight)}, variants 0-7 are
    calibrate_live's and 8-11 add 1.0 m of position noise; decodes: {name: (models summed, lambda)}."""
    w1 = {"w1": (8, "A", 1.0)}
    return {
        "candidates": ({"default": None, "noise 1.0 m": N10},
                       {**w1, "w2": (8, "A", 2.0), "w3": (8, "A", 3.0), "w3n": (12, "A", 3.0), "wB": (8, "B", 1.0)},
                       {"w1": (("w1",), lam), "w1_l20": (("w1",), 20), "w2": (("w2",), lam), "w3": (("w3",), lam),
                        "w3_l15": (("w3",), 15), "w3_l20": (("w3",), 20), "w3n": (("w3n",), lam),
                        "ens13": (("w1", "w3"), 2 * lam), "wB": (("wB",), lam), "wB_l20": (("wB",), 20)}),
        "lambda": ({"default": None, "noise 1.0 m": N10}, {**w1, "wB": (8, "B", 1.0)},
                   {**{(f"w1_l{v:g}" if v != lam else "w1"): (("w1",), v) for v in (10, 12.5, 15, 17.5, 20, 25, 30)},
                    **{f"wB_l{v:g}": (("wB",), v) for v in (10, 12.5, 15, 17.5, 20, 25, 30)}}),
        "noise": ({k: CL.NOISE[k] for k in ("noise 0.6 m + 10% lost + swaps 5%",
                                            "cross-team swaps near the ball, rate for 15% of frames")},
                  {**w1, "w3": (8, "A", 3.0)},
                  {**{(f"w1_l{v:g}" if v != lam else "w1"): (("w1",), v) for v in (10, 15, 20, 25)},
                   "w3": (("w3",), lam)}),
    }


def log(msg):
    print(f"[{(time.time() - T0) / 60:6.1f} min] {msg}", flush=True)


def add_truth_b(game):
    """Metrica: game.truths["B"], truth B with the start anchor (ADR-005); it shares D and X with A."""
    if "start" not in game.truths:
        return
    _, ball, _, events, _ = bench.load_game(game.g)
    tb = bench.truth_labels(events, len(ball), game.dead, "start", variant="B")
    ta = game.truths["start"]
    assert (np.isin(ta, ("H", "A")) == np.isin(tb, ("H", "A"))).all() and ((ta == "X") == (tb == "X")).all()
    game.truths["B"] = tb


def rows_of(game):
    """The rows of CL.game_rows (variants 0-7) plus variants 8-11 with 1.0 m of noise; y and short under A and B."""
    ta = CL.truth_of(game)
    tb = game.truths.get("B", ta)
    spans = CE.spans_of(game)
    live = (ta == "H") | (ta == "A")
    sa, sb = CL.run_seconds(ta) < CL.SHORT_S, CL.run_seconds(tb) < CL.SHORT_S
    variants = [(b, nz) for b in CL.TRAIN_BALLS for nz in (None, CL.TRAIN_NOISE)] + [(b, N10) for b in CL.TRAIN_BALLS]
    out = []
    for v, (b, nz) in enumerate(variants):
        ball = CE.degraded(game, 1000 * game.g + b["seed"], **{k: x for k, x in b.items() if k != "seed"})
        players = CL.players_of(game, b["seed"], nz)
        v2 = P.dead_mask_v2(players, ball)
        FH, FA = P.live_features(players, ball, game.team, bench.radio_evidence(players, ball, game.team, pitch=game.pitch),
                                 v2, spans, game.pitch)
        idx = np.flatnonzero(live & ~v2)[v::CL.STEP]
        out.append(dict(X=np.vstack([FH[idx], FA[idx]]),
                        yA=np.concatenate([ta[idx] == "H", ta[idx] == "A"]),
                        yB=np.concatenate([tb[idx] == "H", tb[idx] == "A"]),
                        sA=np.concatenate([sa[idx]] * 2), sB=np.concatenate([sb[idx]] * 2)))
    return out


def train_rows(per_match, held, n_var, truth):
    rows = []
    for m, games in per_match.items():
        if m == held:
            continue
        for variants in games:
            vs = variants[:n_var]
            rows.append((m, np.vstack([v["X"] for v in vs]), np.concatenate([v["y" + truth] for v in vs]),
                         np.concatenate([v["s" + truth] for v in vs])))
    return rows


def flags(gt_sp, pr_sp, thr=0.5):
    """The scorer's greedy one-to-one match at one IoU, returned for both sides."""
    fg, fp = np.zeros(len(gt_sp), bool), np.zeros(len(pr_sp), bool)
    for iou, i, j in pm.spell_overlaps(gt_sp, pr_sp):
        if iou < thr:
            break
        if not (fg[i] or fp[j]):
            fg[i] = fp[j] = True
    return fg, fp


def bucket_counts(spells, hit):
    d = np.array([(b - a) / CL.FPS for a, b, _ in spells])
    return [[int(((d >= lo) & (d < hi)).sum()), int(((d >= lo) & (d < hi) & hit).sum())]
            for lo, hi in zip(BUCKETS[:-1], BUCKETS[1:])]


def run(conds, fits, decodes, leaves):
    assert not set(CE.RESERVE) & set(CE.SELECTION)
    games = {m: CE.load(m) for m in CE.SELECTION}
    for gs in games.values():
        for g in gs:
            add_truth_b(g)
    log(f"loaded {sum(len(v) for v in games.values())} games of {len(games)} selection matches; {leaves} leaves")
    per_match = {m: [rows_of(g) for g in gs] for m, gs in games.items()}
    log("training rows done")
    res = []
    for held in CE.SELECTION:
        scorers = {k: CL.sklearn_scorer(CL.fit(train_rows(per_match, held, n, t), leaves, short_weight=w))
                   for k, (n, t, w) in fits.items()}
        log(f"left out {held}: {len(scorers)} models trained")
        for game in games[held]:
            truths = {"A": CL.truth_of(game)}
            if "B" in game.truths:
                truths["B"] = game.truths["B"]
            spans = pm.valid_runs(pm.label_codes(truths["A"]))
            for cond, noise in conds.items():
                for s in CE.SEEDS["select"][held[0]]:
                    ball = CE.degraded(game, 1000 * game.g + s)
                    players = CL.players_of(game, s, noise)
                    ev = bench.radio_evidence(players, ball, game.team, pitch=game.pitch)
                    v2 = P.dead_mask_v2(players, ball)
                    labels = {"radio": bench.segment(v2, ev, spans, P.CHANGE_FRAMES, P.MAX_GAP)}
                    FH, FA = P.live_features(players, ball, game.team, ev, v2, spans, game.pitch)
                    d = {k: f(FH) - f(FA) for k, f in scorers.items()}
                    for name, (keys, lm) in decodes.items():
                        labels[name] = P.segment_live(v2, sum(d[k] for k in keys), spans, CL.switch_of(lm))
                    for tname, truth in truths.items():
                        gt = pm.label_codes(truth)
                        runs = pm.valid_runs(gt)
                        gsp = pm.possession_spells(gt, runs)
                        for name, lab in labels.items():
                            pred = pm.fill_abstentions(pm.label_codes(lab), runs)
                            psp = pm.possession_spells(pred, runs)
                            fg, fp = flags(gsp, psp)
                            res.append(dict(g=int(game.g), bench="Metrica" if held[0] == "metrica" else "IDSSE",
                                            seed=int(s), cond=cond, truth=tname, model=name,
                                            f1=pm.spell_scores(gt, pred, runs)["mean_f1"],
                                            n_pred=len(psp), n_gt=len(gsp),
                                            rec=bucket_counts(gsp, fg), prec=bucket_counts(psp, fp)))
            log(f"  scored game {game.g}")
    return res


def summarize(res, buckets):
    by = collections.defaultdict(list)
    for r in res:
        by[(r["bench"], r["cond"], r["truth"], r["g"], r["seed"])].append(r)
    table = collections.defaultdict(lambda: collections.defaultdict(list))
    for key, rs in by.items():
        f = {r["model"]: r for r in rs}
        for name, r in f.items():
            table[key[:3]][(name, key[3])].append(
                (r["f1"], r["f1"] - f["w1"]["f1"], r["f1"] - f["radio"]["f1"], r["n_pred"], r["n_gt"]))
    for (bn, cond, tn), cells in sorted(table.items()):
        print(f"\n{bn} | {cond} | truth {tn}: spellF1, paired diff vs w1 (games better than w1), diff vs radio, "
              f"spells pred/true")
        names = sorted({n for n, _ in cells}, key=lambda n: (n != "radio", n != "w1", n))
        gs = sorted({g for _, g in cells})
        for n in names:
            per_g = [np.mean(cells[(n, g)], axis=0) for g in gs]
            a = np.mean(per_g, axis=0)
            print(f"  {n:8} {a[0]:.4f}  {a[1]:+.4f} ({sum(p[1] > 0 for p in per_g)}/{len(gs)})  {a[2]:+.4f}  "
                  f"{a[3]:.0f}/{a[4]:.0f}")
    if not buckets:
        return
    agg = collections.defaultdict(lambda: np.zeros((len(BUCKETS) - 1, 4)))
    for r in res:
        a = agg[(r["bench"], r["cond"], r["truth"], r["model"])]
        a[:, :2] += r["rec"]
        a[:, 2:] += r["prec"]
    edges = [f"{lo:g}-{hi:g} s" if hi < 1e9 else f">{lo:g} s" for lo, hi in zip(BUCKETS[:-1], BUCKETS[1:])]
    for key in sorted({k[:3] for k in agg}):
        print(f"\n{' | '.join(key)}: recall at IoU 0.5 by true duration (true) || precision by predicted duration "
              f"(predicted), summed over seeds; {', '.join(edges)}")
        for m in ("radio", "w1", "w1_l20", "w3", "wB_l20"):
            a = agg[(*key, m)]
            rec = "  ".join(f"{h / max(n, 1):.2f} ({n:.0f})" for n, h in a[:, :2])
            pre = "  ".join(f"{h / max(n, 1):.2f} ({n:.0f})" for n, h in a[:, 2:])
            print(f"  {m:7} R: {rec} || P: {pre}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--part", choices=("candidates", "lambda", "noise"), required=True)
    ap.add_argument("--json", help="write every record to this file")
    a = ap.parse_args()
    _, recipe = CL.chosen()
    conds, fits, decodes = parts(recipe["lam"])[a.part]
    res = run(conds, fits, decodes, recipe["leaves"])
    if a.json:
        with open(a.json, "w") as f:
            json.dump(res, f)
    summarize(res, a.part == "candidates")


if __name__ == "__main__":
    main()
