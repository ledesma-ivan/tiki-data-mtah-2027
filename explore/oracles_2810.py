"""Where does spellF1 come from? Oracles and a noisy ball on Sample Game 3 (exploratory, 28/10).

Usage: python explore/oracles_2810.py
Re-runs the Game 3 analysis with explicit per-game geometry (ADR-012). For the original numbers quoted
in issues #30-#36 and docs/EXPERIMENTOS.md, use commit 32c5d46. The control-radius numbers, their intervals
and Games 1-2 come from explore/control_radius_2810.py.
Open data only (AGENTS.md). Superseded by bench.py (ADR-006); kept as the record of that analysis.

Known flaws, found by the independent review of 28/10 and kept here so the numbers reproduce:
- degrade() also deletes the ball while it is dead (51% of D frames), unlike the ATD;
- its gap rate overshoots the target (asked 40%, got ~49% of live frames) because gaps overlap;
- section 3 draws both degraded balls from one generator, so their order changes the numbers.
bench.degrade fixes the three.
"""
import json
import os
import sys
import warnings

import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OFFICIAL = os.environ.get("MTAH_OFFICIAL", os.path.join(ROOT, "..", "mtah2027"))
sys.path[:0] = [ROOT, os.path.join(OFFICIAL, "evaluation")]
_argv, sys.argv = sys.argv, sys.argv[:1]  # calibrate_dead reads sys.argv[1] at import
import calibrate_dead as g3  # noqa: E402
sys.argv = _argv
import possession_metrics as pm  # noqa: E402
from bench import owner_evidence  # noqa: E402
from possession import confirm_changes, dead_mask, runs  # noqa: E402

FPS = 25
ON_BALL = {"PASS", "CARRY", "SHOT", "RECOVERY", "SET PIECE"}
TEAM = np.array(["H"] * 11 + ["A"] * 11, dtype=object)

players, ball, pitch = g3.load_game3()
_raw = json.load(open(g3.PREFIX + "events.json"))["data"]
_ev = sorted([(e["type"]["name"], e["start"]["frame"] - 1, e["end"]["frame"] - 1, e["period"],
               "H" if e["team"]["id"] == "FIFATMA" else "A") for e in _raw], key=lambda e: e[1])
n = len(ball)
dead_true = g3.dead_labels(sorted(g3.load_events(), key=lambda e: e[2]), n)

truth_lab = np.full(n, "X", dtype=object)
for _p in sorted({e[3] for e in _ev}):
    _on = [e for e in _ev if e[3] == _p and e[0] in ON_BALL]
    _last = max(e[2] for e in _ev if e[3] == _p)
    for _i, _e in enumerate(_on):
        truth_lab[_e[1]:_on[_i + 1][1] if _i + 1 < len(_on) else _last + 1] = _e[4]
truth_lab[dead_true & (truth_lab != "X")] = "D"
truth = pm.label_codes(truth_lab)
spans = pm.valid_runs(truth)
live = (truth == pm.H) | (truth == pm.A)


def spell(pred_lab):
    s = pm.spell_scores(truth, pm.label_codes(pred_lab), spans)
    return s["mean_f1"], s["n_pred"]


def segment(dead, evidence, n_change):
    lab = np.full(n, "X", dtype=object)
    for a, b in spans:
        lab[a:b] = np.where(dead[a:b], "D", "X")
        for s, e in runs(~dead[a:b]):
            lab[a + s:a + e] = confirm_changes(evidence[a + s:a + e], n_change) if n_change else evidence[a + s:a + e]
    return lab


def degrade(ball, live_missing, rng, mean_gap_s=1.5):
    """The 28/10 noise model, flaws included (see the module docstring)."""
    seen = ~np.isnan(ball[:, 0])
    b = ball[np.maximum.accumulate(np.where(seen, np.arange(n), 0))]
    length = mean_gap_s * FPS
    rate = live_missing / (length * (1 - live_missing))
    gaps = np.zeros(n, bool)
    starts = np.flatnonzero(rng.random(n) < rate)
    for s, ln in zip(starts, rng.exponential(length, len(starts)).astype(int) + 1):
        gaps[s:s + ln] = True
    b[gaps] = np.nan
    return b


def main():
    miss = np.isnan(ball[:, 0])
    graded = truth != pm.X
    m, d = miss[graded], dead_true[graded]
    print(f"[0] ball missing vs dead: P(missing | D) {m[d].mean():.1%}, P(missing | live) {m[~d].mean():.1%}")
    tp = (m & d).sum()
    p, r = tp / m.sum(), tp / d.sum()
    print(f"    missing-only detector: P {p:.3f} R {r:.3f} F1 {2 * p * r / (p + r):.3f}")

    sp = pm.possession_spells(truth, spans)
    dur = np.array([(e - s) / FPS for s, e, *_ in sp])
    print(f"\n[1] possessions {len(sp)}; median {np.median(dur):.1f}s; <2s {np.mean(dur < 2):.0%}, <3s {np.mean(dur < 3):.0%}")
    same = diff = 0
    for a, b in spans:
        seq = truth[a:b]
        for s, e in runs(seq == pm.D):
            if 0 < s and e < len(seq):
                same += seq[s - 1] == seq[e]
                diff += seq[s - 1] != seq[e]
    hand = sum(int(np.sum((truth[a + 1:b] != truth[a:b - 1]) & np.isin(truth[a + 1:b], [pm.H, pm.A])
                          & np.isin(truth[a:b - 1], [pm.H, pm.A]))) for a, b in spans)
    print(f"    boundaries: {hand} live hand-overs, {same + diff} through a D ({same} same team both sides)")

    print("\n[2] oracles (official spellF1)")
    no_d = truth_lab.copy()
    for a, b in spans:
        seg = no_d[a:b]
        for s, e in runs(seg == "D"):
            seg[s:e] = seg[s - 1] if s > 0 else seg[e] if e < len(seg) else "H"
    print(f"    perfect teams, no D        {spell(no_d)[0]:.3f}")
    for shift in (12, 25):
        late = np.full(n, "X", dtype=object)
        late[shift:] = truth_lab[:-shift]
        print(f"    perfect, {shift / FPS:.2f}s late        {spell(late)[0]:.3f}")
    ev = owner_evidence(players, ball, TEAM, pitch=pitch)
    print(f"    nearest-player team accuracy, live frames {np.mean(ev[live] == truth_lab[live]):.1%}")
    for nc in (12, 25, 50, 75):
        f, k = spell(segment(dead_true, ev, nc))
        print(f"    true D + nearest player, N={nc / FPS:.1f}s  {f:.3f}  (n_pred {k}, n_gt {len(sp)})")

    print("\n[3] noisy ball (v1 detector at window 1s / min 2s / thr 0.5; N = 2s)")
    rng = np.random.default_rng(0)
    for name, lm in (("as is", None), ("degraded", 0.2), ("degraded", 0.4)):
        b = ball if lm is None else degrade(ball, lm, rng)
        dm = dead_mask(players, b, FPS, 2 * FPS, 0.5)
        r = g3.score(dm, dead_true, graded)
        e = owner_evidence(players, b, TEAM, pitch=pitch)
        print(f"    {name:9} live missing {np.isnan(b[live, 0]).mean():4.0%}  D F1 {r['F1']:.3f}  "
              f"team acc {np.mean(e[live] == truth_lab[live]):.1%}  spellF1 {spell(segment(dm, e, 2 * FPS))[0]:.3f}  "
              f"with true D {spell(segment(dead_true, e, 2 * FPS))[0]:.3f}")

    print("\n[4] dead ball from players only (mean speed smoothed 2s, min 2s)")
    with warnings.catch_warnings():  # frames with nobody tracked
        warnings.simplefilter("ignore", RuntimeWarning)
        v = np.nanmean(players[:, :, 2], axis=1)
    v = np.convolve(np.nan_to_num(v, nan=9), np.ones(2 * FPS) / (2 * FPS), mode="same")
    for thr in (1.0, 1.5, 2.0):
        dm = v < thr
        for s, e in runs(dm):
            if e - s < 2 * FPS:
                dm[s:e] = False
        r = g3.score(dm, dead_true, graded)
        print(f"    speed < {thr}: P {r['P']:.3f} R {r['R']:.3f} F1 {r['F1']:.3f}, stretches {r['n_pred']} (true {r['n_true']})")

    print("\n[5] nearest-player accuracy by distance to the ball (live, ball seen)")
    seen = ~miss
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        dist = np.nanmin(np.hypot((players[:, :, 0] - ball[:, None, 0]) * pitch[0],
                                  (players[:, :, 1] - ball[:, None, 1]) * pitch[1]), axis=1)
    for lo, hi in ((0, 1), (1, 2), (2, 4), (4, 8), (8, 99)):
        m = live & seen & (dist >= lo) & (dist < hi)
        print(f"    {lo:2}-{hi:<2} m: {m.sum() / (live & seen).sum():5.1%} of frames, accuracy {np.mean(ev[m] == truth_lab[m]):.1%}")


if __name__ == "__main__":
    main()
