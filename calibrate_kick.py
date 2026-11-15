"""The end of each stop at the kick that restarts play (ADR-017, #32): picks it, confirms it and writes it, on open data.

Usage:
  python calibrate_kick.py --select    LOMO over the 7 selection matches (Metrica Games 2-3, IDSSE 1-5): every recipe on
                                       top of the live model of ADR-014's recipe trained on the other 6, against main
                                       (the v2 stops); the best goes to kick_choice.json
  python calibrate_kick.py --confirm   once: the chosen recipe against main, on the live model of ADR-014's recipe
                                       trained on the selection, on the reserve (Metrica Game 1, IDSSE 6-7) with fresh
                                       seeds (Metrica 60-69, IDSSE 60-64): ADR-010's 43 conditions
  python calibrate_kick.py --final     stops_model.json with the chosen recipe; live_model.json does not change
Needs requirements-train.txt (scikit-learn) for the live model; possession.py runs without it. Open data only
(AGENTS.md): Metrica sample-data (data/) and IDSSE (../idsse-data). Nothing here reads BAR-ATH or the public window,
and the reserve enters only --confirm (ADR-011). The stops are possession.snap_ends, the delivered integer rule; the
live model scores with decision_function, as in calibrate_live.py. The live model keeps training on the v2 stops:
retrained on the snapped ones it lost the gain in Metrica in step 0 (explore/kick_snap.py --retrain, ADR-017).
"""
import collections
import hashlib
import json
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "explore"))
_argv, sys.argv = sys.argv, sys.argv[:1]  # possession, calibrate_dead and idsse_dead_labels read sys.argv[1] at import
import bench  # noqa: E402
import calibrate_edges as CE  # noqa: E402
import calibrate_live as CL  # noqa: E402
import possession as P  # noqa: E402
sys.argv = _argv

pm = bench.pm
FPS = P.FPS
KICK_CMS, REST_CMS = 400, 200  # the ball played: 4 m/s for KICK_RUN frames (explore/edge_clock.py); at rest: under 2 m/s
CHOICE = os.path.join(ROOT, "kick_choice.json")
SEED_START = 60  # the reserve's block for this candidate: ADR-010 used 20, ADR-014 20, 30 and 40, and #77 50


def recipes():
    """The 18 candidates: the ball at rest for 0.5, 1 or 1.5 s before the kick, looked for from 2 or 3 s before the
    v2 end to 3, 5 or 8 s after it."""
    return {f"rest {r / FPS:.1f} s, -{b // FPS} s / +{a // FPS} s":
            {"mode": "kick", "before": b, "after": a, "kick_cms": KICK_CMS, "rest": r, "rest_cms": REST_CMS}
            for r in (FPS // 2, FPS, 3 * FPS // 2) for b in (2 * FPS, 3 * FPS) for a in (3 * FPS, 5 * FPS, 8 * FPS)}


def score(games, live, switch, seeds, models, scenario=None, noise=None, clip=False, anchors=None):
    """Labels per seed for "main" (the v2 stops) and each kick model of {name: model}: bench.compare's format,
    {(g, anchor, "degraded", name): (truth, [labels])}. live: {"main": scorer}, the live model of every pipeline unless
    {name: scorer} gives a model its own; noise: a NOISE entry for the players; clip: the restored ball of the stops
    kept on the pitch (ADR-010, criterion 2)."""
    preds = {}
    for game in games:
        for s in seeds:
            ball = CE.degraded(game, 1000 * game.g + s, **(scenario or {}))
            if clip:
                restored = game.dead & np.isnan(game.ball[:, 0])
                ball[restored, :2] = np.clip(ball[restored, :2], 0.0, 1.0)
            players = CL.players_of(game, s, noise)
            ev = bench.radio_evidence(players, ball, game.team, pitch=game.pitch)
            v2 = P.dead_mask_v2(players, ball)
            for anchor, truth in game.truths.items():
                if anchors and anchor not in anchors:
                    continue
                spans = pm.valid_runs(pm.label_codes(truth))
                for name, model in [("main", None)] + list(models.items()):
                    dead = v2 if model is None else P.snap_ends(v2, ball, spans, model, game.pitch)
                    scorer = live.get(name, live["main"])
                    FH, FA = P.live_features(players, ball, game.team, ev, dead, spans, game.pitch)
                    preds.setdefault((game.g, anchor, "degraded", name), (truth, []))[1].append(
                        P.segment_live(dead, scorer(FH) - scorer(FA), spans, switch))
    return preds


def end_report(games, model, seeds, title):
    """Ends within 0.5 s of the true end, v2 against the model, by bench and true kind, on each game's first seed."""
    n = collections.defaultdict(lambda: np.zeros(3))
    for game in games:
        ball = CE.degraded(game, 1000 * game.g + seeds[game.match[0]][0])
        spans = CE.spans_of(game)
        v2 = P.dead_mask_v2(game.players, ball)
        for col, dead in ((1, v2), (2, P.snap_ends(v2, ball, spans, model, game.pitch))):
            found = P.runs(dead)
            for a, b, k in game.kinds:
                over = [(c, d) for c, d in found if c < b and d > a]
                if col == 1:
                    n[(game.match[0], k)][0] += 1
                if over and sum(min(b, d) - max(a, c) for c, d in over) >= 0.5 * (b - a):
                    n[(game.match[0], k)][col] += abs(max(d for _, d in over) - b) <= FPS // 2
    print(f"\n{title}: ends within 0.5 s of the true end, v2 -> kick (share of the true stops, first seed)")
    for (bench_name, k), c in sorted(n.items()):
        print(f"  {bench_name:7} {P.KINDS[k] if k >= 0 else 'unknown':12} {int(c[0]):4} stops  {c[1] / c[0]:4.0%} -> "
              f"{c[2] / c[0]:4.0%}")


def extras(preds, name):
    """Per bench, reported without deciding: the share of true live frames labelled H/A that are right, and the
    possessions predicted over the true ones, for main and the model (calibrate_live.extras against main)."""
    out = {}
    for (g, anchor, _, nm), (truth, labels) in preds.items():
        if nm not in ("main", name) or anchor == "end":
            continue
        gt = pm.label_codes(truth)
        runs_ = pm.valid_runs(gt)
        live = (truth == "H") | (truth == "A")
        for lab in labels:
            ok = live & np.isin(lab, ("H", "A"))
            spells = len(pm.possession_spells(pm.fill_abstentions(pm.label_codes(lab), runs_), runs_))
            out.setdefault(("Metrica" if g < 10 else "IDSSE", nm), []).append(
                (np.mean(lab[ok] == truth[ok]), spells, len(pm.possession_spells(gt, runs_))))
    for (bench_name, nm), v in sorted(out.items()):
        a = np.array(v)
        print(f"  {bench_name:7} {nm:28} live frames right {a[:, 0].mean():.3f}  possessions {a[:, 1].mean():.0f} of "
              f"{a[:, 2].mean():.0f}")


def select():
    """LOMO over the 7 selection matches: each live model is trained on 6, and every recipe scored on the one left out."""
    t0 = time.time()
    live_name, live_recipe = CL.chosen()
    switch = CL.switch_of(live_recipe["lam"])
    games = {m: CE.load(m) for m in CE.SELECTION}
    rows = {m: [(m, *CL.game_rows(g)) for g in games[m]] for m in CE.SELECTION}
    print(f"live rows ({time.time() - t0:.0f} s)", flush=True)
    every = recipes()
    preds = {}
    for held in CE.SELECTION:
        scorer = CL.sklearn_scorer(CL.fit([r for m in CE.SELECTION if m != held for r in rows[m]], live_recipe["leaves"]))
        preds.update(score(games[held], {"main": scorer}, switch, CE.SEEDS["select"][held[0]], every,
                           anchors={"start", "status"}))
        print(f"  left out {held}: done ({time.time() - t0:.0f} s)", flush=True)
    table = []
    for name in every:
        c = bench.compare(preds, "main", name, 1000)
        m, i = c[("start", "degraded")], c[("status", "degraded")]
        table.append(((m[0] + i[0]) / 2, name, m, i))
    table.sort(key=lambda x: -x[0])
    print(f"\nselection (LOMO, default degraded ball, clean players, live model {live_name!r}): paired spellF1 "
          "difference against main, 5-95%, 1000 draws")
    print(f"  {'recipe':24} {'Metrica':>32} {'IDSSE':>32} {'mean':>8}")
    for both, name, m, i in table:
        cells = [f"{p:+.4f} [{lo:+.4f}, {hi:+.4f}] {sum(d > 0 for d in per.values())}/{len(per)}" for p, lo, hi, per in (m, i)]
        print(f"  {name:24} {cells[0]:>32} {cells[1]:>32} {both:+8.4f}")
    both, name, m, i = table[0]
    print("  per game: " + "  ".join(f"{g} {d:+.3f}" for g, d in sorted({**m[3], **i[3]}.items())))
    end_report([g for ms in CE.SELECTION for g in games[ms]], every[name], CE.SEEDS["select"], f"selection, {name}")
    with open(CHOICE, "w") as f:
        json.dump({"recipe": name, **every[name], "metrica": round(m[0], 4), "idsse": round(i[0], 4), "mean": round(both, 4)},
                  f, indent=1)
        f.write("\n")
    print(f"\nchosen: {name} -> {os.path.basename(CHOICE)} ({time.time() - t0:.0f} s)")


def chosen():
    with open(CHOICE) as f:
        c = json.load(f)
    return c["recipe"], {"mode": "kick", **{k: c[k] for k in P.KICK_KEYS}}


def confirm(seed_start=SEED_START):
    """The chosen recipe against main, on the live model trained on the selection, on the reserve with fresh seeds:
    ADR-011's conditions in both benches, the ball of the stops on the pitch and NOISE (ADR-010's 43)."""
    from player_noise import NOISE
    t0 = time.time()
    name, model = chosen()
    live_name, live_recipe = CL.chosen()
    switch = CL.switch_of(live_recipe["lam"])
    clf = CL.fit([(m, *CL.game_rows(g)) for m in CE.SELECTION for g in CE.load(m)], live_recipe["leaves"])
    live = {"main": CL.sklearn_scorer(clf)}
    print(f"live model trained ({time.time() - t0:.0f} s)", flush=True)
    reserve = {m: CE.load(m) for m in CE.RESERVE}
    metrica, idsse = reserve[("metrica", 1)], reserve[("idsse", 6)] + reserve[("idsse", 7)]
    seeds = {"metrica": range(seed_start, seed_start + 10), "idsse": range(seed_start, seed_start + 5)}
    benches = (("Metrica", metrica, seeds["metrica"]), ("IDSSE", idsse, seeds["idsse"]))
    passed = []
    print(f"confirmation of {name!r} on the live model {live_name!r}: Metrica Game 1 (seeds "
          f"{seeds['metrica'][0]}-{seeds['metrica'][-1]}), IDSSE 6-7 (seeds {seeds['idsse'][0]}-{seeds['idsse'][-1]}); "
          "paired difference against main, 5-95%, 1000 draws", flush=True)
    for scen, kw in CE.SCENARIOS.items():
        for bench_name, games, s in benches:
            preds = score(games, live, switch, s, {name: model}, kw)
            for (anchor, _), (point, lo, hi, per) in bench.compare(preds, "main", name, 1000).items():
                ok = lo > 0 if scen == "default" else point > 0
                passed.append(ok)
                print(f"  {scen:32} {bench_name:7} {anchor:6} {point:+.4f} [{lo:+.4f}, {hi:+.4f}]  "
                      f"{sum(d > 0 for d in per.values())}/{len(per)} above 0  {'ok' if ok else 'FAILS'}", flush=True)
            if scen == "default":
                extras(preds, name)
    for (anchor, _), (point, lo, hi, _) in bench.compare(score(metrica, live, switch, seeds["metrica"], {name: model},
                                                               clip=True), "main", name, 1000).items():
        passed.append(point > 0)
        print(f"  {'ball of the stops on the pitch':32} Metrica {anchor:6} {point:+.4f} [{lo:+.4f}, {hi:+.4f}]  "
              f"{'ok' if point > 0 else 'FAILS'}", flush=True)
    for noise_name, kw in NOISE.items():
        for bench_name, games, s in benches:
            preds = score(games, live, switch, s, {name: model}, noise=kw, anchors={"start", "status"})
            (_, _), (point, lo, hi, _) = next(iter(bench.compare(preds, "main", name, 1000).items()))
            passed.append(point > 0)
            print(f"  {noise_name[:32]:32} {bench_name:7} {point:+.4f} [{lo:+.4f}, {hi:+.4f}]  "
                  f"{'ok' if point > 0 else 'FAILS'}", flush=True)
    end_report(metrica + idsse, model, seeds, "the reserve")
    exact = {"main": CL.tree_scorer(CE.export(clf))}
    first = seeds["metrica"][:1]
    a = score(metrica[:1], live, switch, first, {name: model}, anchors={"start"})[(1, "start", "degraded", name)][1][0]
    b = score(metrica[:1], exact, switch, first, {name: model}, anchors={"start"})[(1, "start", "degraded", name)][1][0]
    print(f"\nexported trees against decision_function (Metrica Game 1, first seed): {(a != b).sum()} frames differ")
    print(f"\n{'CONFIRMED' if all(passed) else 'NOT CONFIRMED'}: {sum(passed)}/{len(passed)} conditions "
          f"({time.time() - t0:.0f} s)")


def final():
    """stops_model.json with the chosen recipe. A rule has nothing to retrain, and live_model.json stays as it is."""
    name, model = chosen()
    text = json.dumps(model, separators=(",", ":")) + "\n"
    with open(P.MODEL_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"wrote {os.path.basename(P.MODEL_PATH)} ({name}): {len(text)} bytes, "
          f"sha256 {hashlib.sha256(text.encode()).hexdigest()}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    step = ap.add_mutually_exclusive_group(required=True)
    step.add_argument("--select", action="store_true")
    step.add_argument("--confirm", action="store_true")
    step.add_argument("--final", action="store_true")
    ap.add_argument("--seed-start", type=int, default=SEED_START, help="first reserve seed of --confirm")
    a = ap.parse_args()
    if a.select:
        select()
    elif a.confirm:
        confirm(a.seed_start)
    else:
        final()
