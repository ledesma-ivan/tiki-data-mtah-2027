"""Step 0 of #49 (ADR-014): does a per-frame possession model with a decoder beat the radio pipeline?

Usage: python explore/live_possession_step0.py [--test metrica:3,idsse:5] [--train ...] [--seeds 5]
           [--lams 0,5,10,20,40,80,160] [--noise "<player_noise.NOISE key>" [--noise-train]] [--test-missing 0.45]
Open data only (AGENTS.md): Metrica sample-data (data/) and IDSSE (../idsse-data), through calibrate_edges' loaders,
which cache a .npz and a .restarts.json next to each IDSSE positions file. Selection matches only (Metrica 2-3,
IDSSE 1-5): the reserve (Metrica 1, IDSSE 6-7) stays untouched for the ADR's confirmation.

A throwaway prototype, kept to reproduce the 30/10 rows of docs/EXPERIMENTOS.md: float signals and sklearn's own
predictions, not the integer pipeline of ADR-014 (calibrate_live.py). Model: HistGradientBoosting on per-frame
signals of each team (P(team T has the ball)), both orientations, then a two-state Viterbi with a switch penalty
lam (in logits) inside each live stretch of dead_mask_v2, against the radio pipeline on the same degraded balls.
"""
import argparse
import os
import sys
import time

import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--test", default="metrica:3,idsse:5")
ap.add_argument("--train", default="", help="default: the selection matches not in --test")
ap.add_argument("--seeds", type=int, default=5)
ap.add_argument("--lams", default="0,5,10,20,40,80,160")
ap.add_argument("--step", type=int, default=5)
ap.add_argument("--draws", type=int, default=1000)
ap.add_argument("--noise", default="", help="a player_noise.NOISE key, applied to the test players")
ap.add_argument("--noise-train", action="store_true", help="also to the training players")
ap.add_argument("--test-missing", type=float, default=0.45, help="live_missing of the test balls (0: the full ball)")
a = ap.parse_args()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "explore"))
_argv, sys.argv = sys.argv, sys.argv[:1]  # possession and calibrate_dead read sys.argv[1] at import
import bench  # noqa: E402
import calibrate_edges as CE  # noqa: E402
import possession as P  # noqa: E402
sys.argv = _argv
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402

pm = bench.pm
FPS = P.FPS
L, W = bench.PITCH
BIG = 1e6
SELECTION = [("metrica", 2), ("metrica", 3)] + [("idsse", m) for m in range(1, 6)]


def parse(s):
    return [(k, int(v)) for k, v in (x.split(":") for x in s.split(",") if x)]


def past_future(x, w):
    c = np.r_[0.0, np.cumsum(x)]
    i = np.arange(len(x))
    return c[i] - c[np.maximum(i - w, 0)], c[np.minimum(i + w, len(x))] - c[i]


def since_until(mask, cap):
    n = len(mask)
    i = np.arange(n)
    last = np.maximum.accumulate(np.where(mask, i, -1))
    nxt = np.minimum.accumulate(np.where(mask, i, n)[::-1])[::-1]
    return np.where(last >= 0, np.minimum(i - last, cap), cap), np.where(nxt < n, np.minimum(nxt - i, cap), cap)


def box_mean(x, w):
    ok = ~np.isnan(x)
    k = np.ones(w)
    s = np.convolve(np.where(ok, x, 0.0), k, mode="same")
    c = np.convolve(ok.astype(float), k, mode="same")
    return np.where(c > 0, s / np.maximum(c, 1), np.nan)


def halves_of(game):
    return [(0, len(game.ball))] if game.match[0] == "idsse" else P.runs(game.graded)


def direction(players, team, halves):
    """+1 on frames where H defends x = 0 in that half (its mean x is the lower), else -1."""
    s = np.zeros(len(players))
    for a_, b_ in halves:
        xh = np.nanmean(players[a_:b_][:, team == "H", 0])
        xa = np.nanmean(players[a_:b_][:, team == "A", 0])
        s[a_:b_] = 1.0 if xh < xa else -1.0
    return s


def stretch_pos(dead, spans, cap=10 * FPS):
    since = np.full(len(dead), cap, float)
    until = np.full(len(dead), cap, float)
    for a_, b_ in spans:
        for s_, e_ in P.runs(~dead[a_:b_]):
            idx = np.arange(e_ - s_)
            since[a_ + s_:a_ + e_] = np.minimum(idx, cap)
            until[a_ + s_:a_ + e_] = np.minimum(idx[::-1], cap)
    return since, until


def noisy(game, seed):
    if not a.noise:
        return game.players
    from player_noise import NOISE, noisy_players
    return noisy_players(game.players, game.ball, game.team, np.random.default_rng(10_000 * game.g + seed),
                         pitch=game.pitch, **NOISE[a.noise])


def features(game, ball, dead, spans, players):
    """(F_H, F_A): per-frame features of each team as the "own" side, the other as "rival", plus shared ones."""
    team = game.team
    L, W = game.pitch  # ADR-012: each game's own geometry
    xy = P.ball_position(ball, P.MAX_INTERP)
    bx, by = xy[:, 0] * L, xy[:, 1] * W
    px, py = players[:, :, 0] * L, players[:, :, 1] * W
    vx, vy = np.gradient(px, axis=0) * FPS, np.gradient(py, axis=0) * FPS
    speed = players[:, :, 2]
    ev = bench.radio_evidence(players, ball, team, pitch=game.pitch)
    sdir = direction(players, team, halves_of(game))
    r = np.arange(len(ball))
    own = {}
    for T in "HA":
        m = team == T
        sT = sdir if T == "H" else -sdir
        dx, dy = px[:, m] - bx[:, None], py[:, m] - by[:, None]
        d = np.hypot(dx, dy)
        d = np.where(np.isnan(d), np.inf, d)
        ds = np.sort(d, axis=1)
        j = d.argmin(1)
        f = {"d1": ds[:, 0], "d2": ds[:, 1], "n3": (d < 3).sum(1), "n10": (d < 10).sum(1),
             "near_speed": speed[:, m][r, j],
             "closing": -(vx[:, m][r, j] * dx[r, j] + vy[:, m][r, j] * dy[r, j]) / np.maximum(ds[:, 0], 0.1),
             "n_tracked": (~np.isnan(px[:, m])).sum(1)}
        e = (ev == T).astype(float)
        for w in (12, 50, 125):
            f[f"ev_past_{w}"], f[f"ev_fut_{w}"] = past_future(e, w)
        f["ev_since"], f["ev_until"] = since_until(e > 0, 250)
        with np.errstate(all="ignore"):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                f["adv"] = sT * (np.nanmean(px[:, m], 1) - L / 2)
                f["spread_x"], f["spread_y"] = np.nanstd(px[:, m], 1), np.nanstd(py[:, m], 1)
                f["team_v"] = box_mean(sT * np.nanmean(vx[:, m], 1), FPS)
        f["ball_adv"] = sT * (bx - L / 2)
        k = FPS // 5
        f["ball_vx"] = sT * np.r_[np.full(k, np.nan), bx[k:] - bx[:-k]] * (FPS / k)
        own[T] = f
    seen = ~np.isnan(ball[:, 0])
    unseen, next_seen = since_until(seen, 250)
    k = FPS // 5
    bsp = np.hypot(np.r_[np.full(k, np.nan), bx[k:] - bx[:-k]], np.r_[np.full(k, np.nan), by[k:] - by[:-k]]) * (FPS / k)
    st_since, st_until = stretch_pos(dead, spans)
    shared = np.stack([seen, unseen, next_seen, ~np.isnan(bx), bsp, st_since, st_until], axis=1).astype(float)
    names = list(own["H"])
    FH = np.hstack([np.stack([own["H"][n] for n in names], 1), np.stack([own["A"][n] for n in names], 1), shared])
    FA = np.hstack([np.stack([own["A"][n] for n in names], 1), np.stack([own["H"][n] for n in names], 1), shared])
    clean = lambda F: np.where(np.isfinite(F), F, BIG)
    return clean(FH), clean(FA), ev


def truth_of(game):
    return game.truths["start"] if game.match[0] == "metrica" else game.truths["status"]


def viterbi2(s, lam):
    """0 (H) / 1 (A) per frame maximizing sum(+s/2 on H, -s/2 on A) - lam * switches."""
    n = len(s)
    out = np.empty(n, np.int8)
    if n == 0:
        return out
    half = (s / 2).tolist()
    vh, va = half[0], -half[0]
    back = bytearray(n)
    for t in range(1, n):
        h_sw, a_sw = va - lam, vh - lam
        b = 0
        if h_sw > vh:
            nh = h_sw
            b = 1
        else:
            nh = vh
        if a_sw > va:
            na = a_sw
            b |= 2
        else:
            na = va
        vh, va = nh + half[t], na - half[t]
        back[t] = b
    state = 0 if vh >= va else 1
    for t in range(n - 1, -1, -1):
        out[t] = state
        b = back[t]
        if state == 0 and b & 1:
            state = 1
        elif state == 1 and b & 2:
            state = 0
    return out


def decode(dead, s, spans, lam):
    labels = np.full(len(dead), "X", dtype=object)
    for a_, b_ in spans:
        labels[a_:b_] = np.where(dead[a_:b_], "D", "X")
        for st, en in P.runs(~dead[a_:b_]):
            labels[a_ + st:a_ + en] = np.where(viterbi2(s[a_ + st:a_ + en], lam) == 0, "H", "A")
    return labels


def main():
    t0 = time.time()
    test = parse(a.test)
    train = parse(a.train) or [m for m in SELECTION if m not in test]
    assert not set(train + test) - set(SELECTION), "selection matches only: the reserve stays untouched"
    print(f"train {train}  test {test}", flush=True)

    X, y, w = [], [], []
    for match in train:
        games = CE.load(match)
        rows_match = []
        for game in games:
            truth = truth_of(game)
            spans = CE.spans_of(game)
            live = (truth == "H") | (truth == "A")
            for b, seed in enumerate((100, 101)):
                ball = CE.degraded(game, 1000 * game.g + seed)
                players = noisy(game, seed) if a.noise_train else game.players
                FH, FA, _ = features(game, ball, P.dead_mask_v2(players, ball), spans, players)
                idx = np.flatnonzero(live)[b::a.step]
                rows_match.append((np.vstack([FH[idx], FA[idx]]), np.r_[truth[idx] == "H", truth[idx] == "A"]))
        n = sum(len(r[1]) for r in rows_match)
        for Xm, ym in rows_match:
            X.append(Xm)
            y.append(ym)
            w.append(np.full(len(ym), 1.0 / n))
        print(f"  rows of {match}: {n}  ({time.time() - t0:.0f} s)", flush=True)
    X, y, w = np.vstack(X), np.concatenate(y), np.concatenate(w)
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.1, max_leaf_nodes=31, min_samples_leaf=200,
                                         random_state=0, early_stopping=False).fit(X, y, sample_weight=w * len(w))
    print(f"trained on {len(y)} rows ({time.time() - t0:.0f} s)", flush=True)

    lams = [float(v) for v in a.lams.split(",")]
    preds, acc = {}, {}
    for match in test:
        for game in CE.load(match):
            truth = truth_of(game)
            anchor = "start" if match[0] == "metrica" else "status"
            spans = CE.spans_of(game)
            live = (truth == "H") | (truth == "A")
            for s_ in range(a.seeds):
                ball = CE.degraded(game, 1000 * game.g + s_, live_missing=a.test_missing)
                players = noisy(game, s_)
                v2 = P.dead_mask_v2(players, ball)
                FH, FA, ev = features(game, ball, v2, spans, players)
                pH, pA = clf.predict_proba(FH)[:, 1], clf.predict_proba(FA)[:, 1]
                eps = 1e-6
                lg = lambda p: np.log(np.clip(p, eps, 1 - eps)) - np.log(np.clip(1 - p, eps, 1 - eps))
                s = lg(pH) - lg(pA)
                acc.setdefault((match[0], "model per frame"), []).append(np.mean((s[live] > 0) == (truth[live] == "H")))
                out = {"radio": bench.segment(v2, ev, spans, P.CHANGE_FRAMES, P.MAX_GAP),
                       "radio, true D": bench.segment(game.dead, ev, spans, P.CHANGE_FRAMES, P.MAX_GAP)}
                for lam in lams:
                    out[f"model {lam:g}"] = decode(v2, s, spans, lam)
                    out[f"model {lam:g}, true D"] = decode(game.dead, s, spans, lam)
                for name, labels in out.items():
                    preds.setdefault((game.g, anchor, "degraded", name), (truth, []))[1].append(labels)
                    ok = live & np.isin(labels, ("H", "A"))
                    acc.setdefault((match[0], name), []).append(np.mean(labels[ok] == truth[ok]))
            print(f"  scored {match} game {game.g} ({time.time() - t0:.0f} s)", flush=True)

    names = sorted({k[3] for k in preds})
    print("\nmean spellF1 over games and seeds | per-frame accuracy on true live frames labelled H/A | spells pred/gt")
    for anchor in ("start", "status"):
        keys = [k for k in preds if k[1] == anchor]
        if not keys:
            continue
        bench_name = "metrica" if anchor == "start" else "idsse"
        print(f"  {bench_name}")
        for name in names:
            sp, npred, ngt = [], [], []
            for k in keys:
                if k[3] != name:
                    continue
                truth, labs = preds[k]
                gt = pm.label_codes(truth)
                n_gt = len(pm.possession_spells(gt, pm.valid_runs(gt)))
                point = np.arange(n_gt)[None]
                for lab in labs:
                    pc = pm.label_codes(lab)
                    sp.append(bench.spell_draws(gt, pc, point)[0])
                    npred.append(len(pm.possession_spells(pm.fill_abstentions(pc, pm.valid_runs(gt)), pm.valid_runs(gt))))
                    ngt.append(n_gt)
            print(f"    {name:22} spellF1 {np.mean(sp):.3f}  acc {np.mean(acc[(bench_name, name)]):.3f}  "
                  f"spells {np.mean(npred):.0f}/{np.mean(ngt):.0f}")
        print(f"    {'model per frame':22} acc {np.mean(acc[(bench_name, 'model per frame')]):.3f} (sign of the score)")

    print(f"\npaired spellF1 difference against radio (or radio, true D), 5-95%, {a.draws} draws")
    for name in names:
        if not name.startswith("model"):
            continue
        base = "radio, true D" if name.endswith("true D") else "radio"
        for (anchor, ball), (point, lo, hi, per_game) in bench.compare(preds, base, name, a.draws).items():
            games = "  ".join(f"g{g} {d:+.3f}" for g, d in per_game.items())
            print(f"  {anchor:6} {name:22} {point:+.3f} [{lo:+.3f}, {hi:+.3f}]  {games}")
    print(f"\ndone in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
