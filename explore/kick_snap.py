"""Step 0 of the next #32 candidate: the end of each stop moved to the kick that restarts play, on top of the live model.

Usage: python explore/kick_snap.py [--seeds-metrica 10] [--seeds-idsse 5] [--draws 1000] [--cache live_lomo.pkl]
Open data only (AGENTS.md), selection matches only (Metrica 2-3, IDSSE 1-5), LOMO: the reserve stays untouched.
A throwaway prototype, kept to reproduce its row of docs/EXPERIMENTOS.md.

ADR-010's learned edges gain in IDSSE and lose in Metrica on top of the live model, whatever fix they get
(explore/edges_on_live.py): their gain is the real ball of IDSSE's stops, which Metrica's bench does not have, and
what they learn from the players does not carry over. Both truths end a stop at the kick (explore/edge_clock.py), and
the ball near the restart is a real one in IDSSE, in the ATD and in sample-data, where it reappears with the restart.
So, with no training: the end of each v2 stop moves to the onset of the ball moving at KICK m/s or more for RUN frames
(on the degraded ball, as the pipeline sees it) nearest the v2 end within [end - before, end + after); without one,
the v2 end stays. The first run (30/10) took any kick: it fixed free kicks and broke the ends v2 already had right,
because with 45% of the live ball missing the restart's own kick is often not seen and a pass after it is taken. A
restart is a ball at rest that is kicked, so the second run (31/10) also asks for the ball seen at rest (slower than
REST_SPEED) for `rest` frames right before the kick. Scored with the live model of main's recipe trained on the other 6 matches (calibrate_live.py),
against main, with decision_function as calibrate_live.py --select.
"""
import argparse
import collections
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
FPS = P.FPS
LIVE_LEAVES, LAM = 63, 10  # live_choice.json (ADR-014)
RUN = 3
REST_SPEED = 2.0  # m/s: a ball seen slower than this is at rest (placed, held or carried)
# name: (before, after, kick m/s, rest frames: the ball seen at rest for that long right before the kick; 0: any)
VARIANTS = {"kick 4 m/s, -2 s / +3 s": (2 * FPS, 3 * FPS, 4.0, 0),
            "rest 0.5 s, 4 m/s, -2 s / +3 s": (2 * FPS, 3 * FPS, 4.0, FPS // 2),
            "rest 1 s, 4 m/s, -2 s / +3 s": (2 * FPS, 3 * FPS, 4.0, FPS),
            "rest 0.5 s, 4 m/s, -3 s / +3 s": (3 * FPS, 3 * FPS, 4.0, FPS // 2),
            "rest 1 s, 4 m/s, -3 s / +5 s": (3 * FPS, 5 * FPS, 4.0, FPS),
            "rest 0.5 s, 6 m/s, -2 s / +3 s": (2 * FPS, 3 * FPS, 6.0, FPS // 2)}


def kick_onsets(ball, pitch, kick, rest=0):
    """Frames from which the ball moves at kick m/s or more for RUN frames (forward differences): a missing ball,
    or a step from or to one, is never fast. rest > 0: only onsets after rest frames of the ball seen at rest."""
    step = np.diff(ball[:, :2], axis=0, append=np.nan) * np.asarray(pitch)
    speed = np.hypot(step[:, 0], step[:, 1]) * FPS
    fast = speed >= kick
    played = fast.copy()
    for i in range(1, RUN):
        played &= np.r_[fast[i:], np.zeros(i, bool)]
    onsets = np.flatnonzero(played & ~np.r_[False, played[:-1]])
    if rest:
        c = np.r_[0, np.cumsum(speed < REST_SPEED)]  # NaN compares False: a missing ball is never at rest
        onsets = onsets[(onsets >= rest) & (c[onsets] - c[np.maximum(onsets - rest, 0)] == rest)]
    return onsets


def snap(dead, ball, spans, pitch, before, after, kick, rest=0):
    """dead with each stop's end moved to the nearest kick onset in [end - before, end + after) (earlier on ties),
    never before the stop's first frame + 1 nor past the next stop's start, and only inside the spans."""
    out = dead.copy()
    onsets = kick_onsets(ball, pitch, kick, rest)
    for a, b in spans:
        stops = [(a + s, a + e) for s, e in P.runs(dead[a:b])]
        for j, (c, d) in enumerate(stops):
            nxt = stops[j + 1][0] if j + 1 < len(stops) else b
            lo, hi = max(d - before, c + 1), min(d + after, nxt)
            k = onsets[(onsets >= lo) & (onsets < hi)]
            if len(k):
                e = int(k[np.argmin(np.abs(k - d))])
                out[c:d] = False
                out[c:e] = True
    return out


def snapped_rows(game, params):
    """calibrate_live.game_rows with the stops after the snap: the rows the live model trains on in that pipeline."""
    truth = CL.truth_of(game)
    spans = CE.spans_of(game)
    live = (truth == "H") | (truth == "A")
    X, y = [], []
    for v, (b, noise) in enumerate((b, noise) for b in CL.TRAIN_BALLS for noise in (None, CL.TRAIN_NOISE)):
        ball = CE.degraded(game, 1000 * game.g + b["seed"], **{k: x for k, x in b.items() if k != "seed"})
        players = CL.players_of(game, b["seed"], noise)
        dead = snap(P.dead_mask_v2(players, ball), ball, spans, game.pitch, *params)
        FH, FA = P.live_features(players, ball, game.team, bench.radio_evidence(players, ball, game.team, pitch=game.pitch),
                                 dead, spans, game.pitch)
        idx = np.flatnonzero(live & ~dead)[v::CL.STEP]
        X += [FH[idx], FA[idx]]
        y += [truth[idx] == "H", truth[idx] == "A"]
    return np.vstack(X), np.concatenate(y)


def end_counts(game, dead_by_name, seed):
    """{(bench, kind, name): [stops, end within 0.5 s]} on one seed, as calibrate_edges.stop_counts."""
    n = collections.defaultdict(lambda: np.zeros(2))
    for name, dead in dead_by_name.items():
        found = P.runs(dead)
        for a, b, k in game.kinds:
            over = [(c, d) for c, d in found if c < b and d > a]
            c_ = n[(game.match[0], k, name)]
            c_[0] += 1
            if over and sum(min(b, d) - max(a, c) for c, d in over) >= 0.5 * (b - a):
                c_[1] += abs(max(d for _, d in over) - b) <= FPS // 2
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seeds-metrica", type=int, default=10)
    ap.add_argument("--seeds-idsse", type=int, default=5)
    ap.add_argument("--draws", type=int, default=1000)
    ap.add_argument("--cache", default="", help="pickle of the 7 LOMO live classifiers, written once and reused")
    ap.add_argument("--retrain", default="", help="one VARIANTS name: also with the live model retrained on its stops")
    a = ap.parse_args()
    variants = {a.retrain: VARIANTS[a.retrain]} if a.retrain else VARIANTS
    seeds = {"metrica": range(a.seeds_metrica), "idsse": range(a.seeds_idsse)}
    t0 = time.time()
    games = {m: CE.load(m) for m in CE.SELECTION}
    if a.cache and os.path.exists(a.cache):
        with open(a.cache, "rb") as f:
            clfs = pickle.load(f)
    else:
        rows = {m: [(m, *CL.game_rows(g)) for g in games[m]] for m in CE.SELECTION}
        clfs = {m: CL.fit([r for x in CE.SELECTION if x != m for r in rows[x]], LIVE_LEAVES) for m in CE.SELECTION}
        if a.cache:
            with open(a.cache, "wb") as f:
                pickle.dump(clfs, f)
    print(f"live models ready ({time.time() - t0:.0f} s)", flush=True)
    retrained = {}
    if a.retrain:  # the snap is a rule: its rows do not depend on the fold
        srows = {m: [(m, *snapped_rows(g, VARIANTS[a.retrain])) for g in games[m]] for m in CE.SELECTION}
        retrained = {m: CL.fit([r for x in CE.SELECTION if x != m for r in srows[x]], LIVE_LEAVES) for m in CE.SELECTION}
        print(f"live models retrained on the snapped stops ({time.time() - t0:.0f} s)", flush=True)
    switch = CL.switch_of(LAM)
    per = {"metrica": {}, "idsse": {}}
    counts = collections.defaultdict(lambda: np.zeros(2))
    for held in CE.SELECTION:
        scorer = CL.sklearn_scorer(clfs[held])
        scorer_r = CL.sklearn_scorer(retrained[held]) if a.retrain else None
        for game in games[held]:
            truth = CL.truth_of(game)
            gt = pm.label_codes(truth)
            spans = pm.valid_runs(gt)
            by = {}
            for s in seeds[held[0]]:
                ball = CE.degraded(game, 1000 * game.g + s)
                ev = bench.radio_evidence(game.players, ball, game.team, pitch=game.pitch)
                v2 = P.dead_mask_v2(game.players, ball)
                deads = {"main": v2}
                deads.update({name: snap(v2, ball, spans, game.pitch, *p) for name, p in variants.items()})
                for name, dead in deads.items():
                    FH, FA = P.live_features(game.players, ball, game.team, ev, dead, spans, game.pitch)
                    by.setdefault(name, []).append(pm.label_codes(P.segment_live(dead, scorer(FH) - scorer(FA), spans,
                                                                                  switch)))
                    if scorer_r is not None and name != "main":
                        by.setdefault(name + ", retrained", []).append(pm.label_codes(
                            P.segment_live(dead, scorer_r(FH) - scorer_r(FA), spans, switch)))
                if s == seeds[held[0]][0]:
                    for key, c in end_counts(game, deads, s).items():
                        counts[key] += c
            per[held[0]][game.g] = (gt, by)
        print(f"  left out {held}: scored ({time.time() - t0:.0f} s)", flush=True)

    print(f"\npaired spellF1 difference against main (v2 stops) on the LOMO live model, 5-95% ({a.draws} draws)")
    print(f"  {'variant':26} {'Metrica':>30} {'IDSSE':>30} {'mean':>8}")
    for name in list(variants) + [n + ", retrained" for n in variants if a.retrain]:
        cells, means = [], []
        for bench_name in ("metrica", "idsse"):
            p, lo, hi, g = O.paired(per[bench_name], "main", name, a.draws)
            cells.append(f"{p:+.4f} [{lo:+.4f}, {hi:+.4f}] {sum(d > 0 for d in g.values())}/{len(g)}")
            means.append(p)
        print(f"  {name:26} {cells[0]:>30} {cells[1]:>30} {np.mean(means):+8.4f}", flush=True)
    print("\nends within 0.5 s of the true end, first seed (share of the true stops): v2 -> each variant")
    for bench_name in ("idsse", "metrica"):
        for k in sorted({key[1] for key in counts if key[0] == bench_name}):
            base = counts[(bench_name, k, "main")]
            cells = "  ".join(f"{counts[(bench_name, k, name)][1] / base[0]:4.0%}" for name in variants)
            print(f"  {bench_name:7} {P.KINDS[k] if k >= 0 else 'unknown':12} {int(base[0]):4} stops  v2 "
                  f"{base[1] / base[0]:4.0%} -> {cells}")
    print(f"\ndone in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
