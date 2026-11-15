"""Ball possession per frame for BAR-ATH: tracking -> evidence -> dead-ball cuts -> CSV.

Usage: python possession.py [data dir]    writes output/possession.csv and prints its sha256
The data dir defaults to $MTAH_DATA and holds tactical/BAR-ATH_tactical_* (AGENTS.md).
Decisions: docs/adr/ADR-001 (change rule), docs/adr/ADR-007 (dead ball, replaces the ADR-002 detector,
which stays as dead_mask for calibrate_dead.py and the bench baseline), docs/adr/ADR-010 (stop edges and the
team that restarts play: stops_model.json, trained on open data by calibrate_edges.py; in mode "kick", ADR-017's end
of each stop at the kick that restarts play, chosen by calibrate_kick.py), docs/adr/ADR-014 (who has
the ball in live play: live_model.json, trained on open data by calibrate_live.py; in mode "rule", ADR-001's rule).
Same bytes on every machine with requirements.txt (#6): no random step, exact arithmetic, LF endings.
"""
import hashlib
import json
import os
import re
import sys
import warnings

import numpy as np

DATA = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("MTAH_DATA", "")
TAC = os.path.join(DATA, "tactical", "BAR-ATH_tactical")
CACHE = TAC + "_atd.npz"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "possession.csv")

N_FRAMES = 199319
N_SLOTS = 46
FPS = 25
PITCH = (105.3, 68.0)  # metres; tracking is normalised 0-1
# Video frames of each half, from games.half_video_blocks() in the official repo.
HALVES = [(11185, 90651), (110808, 190197)]
# The kick-off of each half (FAQ.md of the official repo): the second half is graded from 110,808 but kicks off at
# 113,742, and those 2,934 frames are D. The first half is graded from its kick-off.
KICKOFFS = (11185, 113742)

# Control radius, N, the interpolation cap and max_gap were chosen together in the bench (ADR-009, #33).
CONTROL_RADIUS = 1.0  # metres: the nearest player is evidence only inside it
CHANGE_FRAMES = FPS // 2
MAX_INTERP = 2 * FPS  # frames: a ball gap longer than this has no position, so no evidence
MAX_GAP = 4 * FPS  # frames without evidence that a rival run survives (#31)
# Not calibrated. Placeholders until the sample-data calibration (ADR-002).
DEAD_WINDOW = 2 * FPS
DEAD_MIN = 3 * FPS
DEAD_SCORE = 0.5


def load_atd():
    """(players[n,46,3], ball[n,3], team[46]) indexed by video frame (= frameCount - 1)."""
    if os.path.exists(CACHE):
        z = np.load(CACHE)
        return z["players"], z["ball"], z["team"]
    rows = []
    with open(TAC + "_atd.txt") as f:
        for line in f:
            _, players, ball = line.rstrip("\n").split(":")
            rows.append(players.replace(";", ",") + "," + ball)
    a = np.array([r.split(",") for r in rows], dtype=float)
    players = a[:, : N_SLOTS * 3].reshape(-1, N_SLOTS, 3)
    ball = a[:, N_SLOTS * 3:]
    meta = open(TAC + "_atd.xml", encoding="utf-8").read()
    home_id = re.search(r'<Team id="([^"]+)">\s*<Name>Barcelona', meta).group(1)
    slot_team = dict(re.findall(r'<Player id="(\d+)" teamId="([^"]+)"', meta))
    team = np.array(["H" if slot_team[str(i + 1)] == home_id else "A" for i in range(N_SLOTS)])
    # ponytail: the cache is not keyed to this parser; delete *_atd.npz after changing load_atd.
    try:
        np.savez_compressed(CACHE, players=players, ball=ball, team=team)
    except OSError:  # read-only data dir: run without the cache
        pass
    return players, ball, team


def ball_position(ball, max_interp=None):
    """Ball x, y per frame with its gaps filled; NaN where there is no position to use.

    max_interp=None: a gap reuses the last known position, without limit (ADR-001).
    max_interp=k: a gap of at most k frames between two seen positions is a straight line between
    them; a longer gap, or one at the start or end, stays NaN (ADR-009, #33).
    """
    n = len(ball)
    seen = ~np.isnan(ball[:, 0])
    i = np.arange(n)
    prev = np.maximum.accumulate(np.where(seen, i, 0))
    if max_interp is None:
        return ball[prev, :2]
    nxt = np.minimum.accumulate(np.where(seen, i, n)[::-1])[::-1]
    ok = seen | (seen[prev] & (nxt < n) & (nxt - prev - 1 <= max_interp))
    nxt = np.minimum(nxt, n - 1)
    span = np.maximum(nxt - prev, 1)
    t = ((i - prev) / span)[:, None]  # IEEE divide, multiply and add only: the same on every CPU (#6)
    xy = ball[prev, :2] + t * (ball[nxt, :2] - ball[prev, :2])
    xy[seen] = ball[seen, :2]
    xy[~ok] = np.nan
    return xy


def pitch_dimensions(pitch):
    """Validate a (length, width) pair in metres; never substitute another game's geometry."""
    dims = np.asarray(pitch, dtype=float)
    if dims.shape != (2,) or not np.isfinite(dims).all() or (dims <= 0).any():
        raise ValueError("pitch must contain two finite, positive dimensions in metres")
    # Python scalars preserve NumPy's input-dtype promotion, as the original PITCH did.
    return tuple(dims.tolist())


def squared_distances(players, bxy, *, pitch):
    """Player-to-ball squared distances in m² from normalised positions."""
    length, width = pitch_dimensions(pitch)
    dx = (players[:, :, 0] - bxy[:, None, 0]) * length
    dy = (players[:, :, 1] - bxy[:, None, 1]) * width
    # Keep the delivery pipeline's IEEE arithmetic and first-slot tie breaking.
    return np.where(np.isnan(dx), np.inf, dx * dx + dy * dy)


def owner_evidence(players, ball, team, radius=np.inf, max_interp=None, *, pitch=PITCH):
    """Team of the tracked player nearest the ball, per frame; "" where there is no evidence.

    No evidence: nobody tracked, no ball position (ball_position), or, with a finite radius, the nearest
    player farther than `radius` metres (ADR-009, #33). pitch is (length, width) in metres;
    the default preserves the delivery API. Bench callers use bench.owner_evidence, which requires pitch.
    """
    bxy = ball_position(ball, max_interp)
    # squared distance: IEEE multiply and add only, so ties break the same on every platform
    # (np.hypot comes from each platform's libm)
    d = squared_distances(players, bxy, pitch=pitch)
    ev = team[d.argmin(1)].astype(object)
    nearest = d.min(1)
    ev[~(np.isfinite(nearest) & (nearest <= radius * radius))] = ""
    return ev


def dead_mask(players, ball, window=DEAD_WINDOW, min_len=DEAD_MIN, threshold=DEAD_SCORE):
    """Dead-ball detector (ADR-002): smoothed score of three signals plus a minimum length.

    players[n, k, 3] = x, y (0-1), speed (m/s); ball[n, >=2] = x, y (0-1).
    The window counts signal frames as integers: exact on every CPU. A float average goes through
    BLAS, and its rounding at the threshold changes with the CPU's kernel (#6).
    """
    bx, by = ball[:, 0], ball[:, 1]
    with warnings.catch_warnings():  # frames with nobody tracked: mean of nothing, treated as not slow
        warnings.simplefilter("ignore", RuntimeWarning)
        slow = np.nanmean(players[:, :, 2], axis=1) < 1
    signals = np.stack([np.isnan(bx), (bx < 0) | (bx > 1) | (by < 0) | (by > 1), slow])
    score = dead_score(signals)
    if score.dtype != bool:
        raise TypeError("dead_score must stay boolean: the exact window count depends on it (#6)")
    count = np.convolve(score.astype(np.int64), np.ones(window, dtype=np.int64), mode="same")
    dead = count >= threshold * window
    for start, end in runs(dead):
        if end - start < min_len:
            dead[start:end] = False
    return dead


def dead_score(signals):
    """Per-frame dead-ball score in [0, 1] from boolean signals[k, n] (ADR-002, step 1).

    Rows: 0 ball missing, 1 ball off the pitch, 2 players slow.
    The result is smoothed over DEAD_WINDOW and compared with DEAD_SCORE.
    """
    # Any one signal counts: no labels yet to weight them. DEAD_MIN filters short tracking gaps.
    # ponytail: OR has no weights; weight signals once sample-data dead-ball labels exist, as
    # integers so dead_mask can keep counting exactly (#6).
    return signals.max(0)


def runs(mask):
    """[(start, end)) of consecutive True stretches."""
    d = np.diff(np.r_[0, mask.astype(int), 0])
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


# Dead ball v2 (ADR-007), chosen on open data with the bench (ADR-006): Games 2-3 to pick, Game 1 to confirm.
SLOW_CUT = 1.75  # m/s: a tracked player slower than this counts as slow
SLOW_WINDOW = 5 * FPS
SLOW_ENTER = 85  # % of slow player-frames in the window that starts a stoppage
SLOW_STAY = 75  # % that keeps it going (hysteresis)
SLOW_MIN = 3 * FPS
DEAD_LEAD = FPS  # a stoppage starts 1 s earlier: players slow down after the whistle
DEAD_TRIM = 38  # and ends 38 frames (1.52 s) earlier: they speed up after the restart
OFF_MIN = FPS  # the ball seen off the pitch (half of a DEAD_WINDOW) for at least 1 s is also dead


def dead_mask_v2(players, ball, cut=SLOW_CUT, window=SLOW_WINDOW, enter=SLOW_ENTER, stay=SLOW_STAY, min_len=SLOW_MIN,
                 lead=DEAD_LEAD, trim=DEAD_TRIM, off_min=OFF_MIN):
    """Dead-ball detector v2 (ADR-007): slow players with hysteresis, or the ball seen off the pitch.

    players[n, k, 3] = x, y (0-1), speed (m/s); ball[n, >=2] = x, y (0-1).
    1. Share of slow tracked players in a centred window: a stoppage starts where it reaches `enter` %,
       lasts while it stays at `stay` % or more and counts if it is at least min_len frames long. Its start
       then moves `lead` frames earlier and its end `trim` frames earlier.
    2. The ball seen off the pitch in half of a DEAD_WINDOW, for at least off_min frames.
    A missing ball never counts: in the ATD it goes missing by occlusion, so its absence does not mean a
    dead ball. Counts are integers and shares are compared as 100 * count >= pct * total, so the result
    is exact on every CPU (#6).
    """
    speed = players[:, :, 2]
    tracked = ~np.isnan(speed)
    k = np.ones(window, dtype=np.int64)
    slow = np.convolve((tracked & (speed < cut)).sum(1).astype(np.int64), k, mode="same")
    total = np.convolve(tracked.sum(1).astype(np.int64), k, mode="same")
    start_here = (total > 0) & (100 * slow >= enter * total)
    keep = (total > 0) & (100 * slow >= stay * total)
    dead = np.zeros(len(players), bool)
    for start, end in runs(keep):
        if end - start >= min_len and start_here[start:end].any():
            dead[max(0, start - lead):max(0, end - trim)] = True
    bx, by = ball[:, 0], ball[:, 1]
    off = (bx < 0) | (bx > 1) | (by < 0) | (by > 1)  # NaN compares False: a missing ball is never off the pitch
    off_count = np.convolve(off.astype(np.int64), np.ones(DEAD_WINDOW, dtype=np.int64), mode="same")
    for start, end in runs(2 * off_count >= DEAD_WINDOW):
        if end - start >= off_min:
            dead[start:end] = True
    return dead


def confirm_changes(evidence, n_frames, max_gap=MAX_GAP, initial=None):
    """Possession labels for one live-ball stretch (ADR-001).

    evidence: array of "H" / "A" / "" per frame ("" = no tracked player near the ball).
    Returns an array of "H" / "A", same length.

    The rule: possession passes to the other team only when it is the likely owner for n_frames
    frames in a row, and the change is dated to the FIRST frame of that run, not the frame where
    it gets confirmed. The stretch starts with `initial`, the team that restarts play (ADR-010, #34),
    or, without one, with whoever the evidence names first.

    n_frames is time, not a count of rival frames (#31): the run is measured from its first rival
    frame, and frames with no evidence inside it count as the rival's. A gap of more than max_gap
    frames ends the run, as the holder's evidence does. A run is confirmed on a rival frame.
    """
    out = np.empty(len(evidence), dtype=object)
    # ponytail: arbitrary "H" when the stretch has no restart team and no evidence at all
    current = initial or next((e for e in evidence if e), "H")
    run_start = last_seen = None
    for i, e in enumerate(evidence):
        if e == current:
            run_start = None
        elif e:
            if run_start is None or i - last_seen - 1 > max_gap:
                run_start = i
            last_seen = i
            if i - run_start + 1 >= n_frames:
                out[run_start:i] = e  # backdate to the first frame of the run
                current, run_start = e, None
        out[i] = current
    return out


# -- Stop edges and the team that restarts play (ADR-010, #32 and #34) --------------------------------------
# dead_mask_v2 still finds the stops. A per-frame model of D runs in a window around each of their edges and the
# edge moves to the step that fits it best; the formation names the restart kind, and the player nearest the
# restart point names the team that restarts play. calibrate_edges.py trains the trees on open data and exports
# them to stops_model.json with integer thresholds and leaves: signals, trees and sums are integers (#6).

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stops_model.json")
UNKNOWN = -1_000_000  # a signal that cannot be computed (no ball, nobody tracked), as an integer like the rest
FAST = 4.0  # m/s
UNSEEN_CAP = 10 * FPS  # frames since the ball was last seen, capped
FRAME_FEATURES = ("n_tracked", "slow_pct", "mean_speed", "max_speed", "n_fast", "slow_pct_1s", "slow_pct_3s",
                  "mean_speed_1s", "mean_speed_3s", "speed_change_1s", "speed_change_3s", "slow_change_1s",
                  "ball_seen", "ball_unseen", "ball_known", "ball_speed", "ball_off", "ball_line", "ball_nearest",
                  "ball_nearest_speed")
EDGE_FEATURES = FRAME_FEATURES + ("offset", "side", "stop_len", "kind")


def _int(a, scale):
    """rint(a * scale) as int64, the same on every CPU (IEEE multiply and round); NaN becomes UNKNOWN."""
    out = np.full(a.shape, UNKNOWN, np.int64)
    ok = ~np.isnan(a)
    out[ok] = np.rint(a[ok] * scale).astype(np.int64)
    return out


def _isqrt(d2):
    """floor(sqrt) of non-negative int64: IEEE sqrt is correctly rounded, so it is exact on every CPU."""
    return np.floor(np.sqrt(d2.astype(np.float64))).astype(np.int64)


def _ratio(num, den, scale=1):
    """scale * num // den where den > 0, else UNKNOWN."""
    out = np.full(num.shape, UNKNOWN, np.int64)
    ok = den > 0
    out[ok] = scale * num[ok] // den[ok]
    return out


def _diff(a, b):
    return np.where((a != UNKNOWN) & (b != UNKNOWN), a - b, UNKNOWN)


def _sums(a, w):
    """Sums of int64 a over w frames: centred, past [i - w, i) and future [i, i + w)."""
    c = np.r_[0, np.cumsum(a)]
    i = np.arange(len(a))
    centre = c[np.minimum(i + w - w // 2, len(a))] - c[np.maximum(i - w // 2, 0)]
    return centre, c[i] - c[np.maximum(i - w, 0)], c[np.minimum(i + w, len(a))] - c[i]


def frame_features(players, ball, pitch=PITCH):
    """Integer signals per frame, in FRAME_FEATURES order: the block's motion and the ball's (ADR-010).

    players[n, k, 3] = x, y (0-1), speed (m/s); ball[n, >=2] = x, y (0-1); pitch in metres. Speeds in cm/s,
    distances in cm, shares in %, frames as counts; UNKNOWN where a signal cannot be computed.
    """
    n = len(players)
    i = np.arange(n)
    speed = players[:, :, 2]
    tracked = ~np.isnan(speed)
    spd = np.where(tracked, _int(speed, 100), 0)
    n_tr = tracked.sum(1).astype(np.int64)
    n_slow = (tracked & (speed < SLOW_CUT)).sum(1).astype(np.int64)
    sum_spd = spd.sum(1)
    f = {"n_tracked": n_tr, "slow_pct": _ratio(n_slow, n_tr, 100), "mean_speed": _ratio(sum_spd, n_tr),
         "max_speed": np.where(n_tr > 0, spd.max(1), UNKNOWN), "n_fast": (tracked & (speed >= FAST)).sum(1)}
    for w, tag in ((FPS, "1s"), (3 * FPS, "3s")):
        (c_tr, p_tr, f_tr), (c_sl, p_sl, f_sl), (c_sp, p_sp, f_sp) = _sums(n_tr, w), _sums(n_slow, w), _sums(sum_spd, w)
        f["slow_pct_" + tag] = _ratio(c_sl, c_tr, 100)
        f["mean_speed_" + tag] = _ratio(c_sp, c_tr)
        f["speed_change_" + tag] = _diff(_ratio(f_sp, f_tr), _ratio(p_sp, p_tr))
        if tag == "1s":
            f["slow_change_1s"] = _diff(_ratio(f_sl, f_tr, 100), _ratio(p_sl, p_tr, 100))

    seen = ~np.isnan(ball[:, 0])
    last = np.maximum.accumulate(np.where(seen, i, -1))
    xy = ball_position(ball, MAX_INTERP)
    known = ~np.isnan(xy[:, 0])
    bx, by = _int(xy[:, 0], pitch[0] * 100), _int(xy[:, 1], pitch[1] * 100)
    length, width = round(pitch[0] * 100), round(pitch[1] * 100)
    k = FPS // 5  # ball speed over 0.2 s
    before = np.r_[np.zeros(k, bool), known[:-k]] & known
    dx, dy = bx - np.r_[np.zeros(k, np.int64), bx[:-k]], by - np.r_[np.zeros(k, np.int64), by[:-k]]
    px, py = _int(players[:, :, 0], pitch[0] * 100), _int(players[:, :, 1], pitch[1] * 100)
    near_ok = ~np.isnan(players[:, :, 0]) & known[:, None]
    d2 = np.where(near_ok, (px - bx[:, None]) ** 2 + (py - by[:, None]) ** 2, np.iinfo(np.int64).max)
    j = d2.argmin(1)
    has = near_ok.any(1)
    f.update({"ball_seen": seen.astype(np.int64), "ball_unseen": np.where(last < 0, UNSEEN_CAP, np.minimum(i - last, UNSEEN_CAP)),
              "ball_known": known.astype(np.int64),
              "ball_speed": np.where(before, _isqrt(dx * dx + dy * dy) * (FPS // k), UNKNOWN),
              "ball_off": np.where(known, (bx < 0) | (bx > length) | (by < 0) | (by > width), UNKNOWN),
              "ball_line": np.where(known, np.minimum.reduce([bx, length - bx, by, width - by]), UNKNOWN),
              "ball_nearest": np.where(has, _isqrt(np.where(has, d2[i, j], 0)), UNKNOWN),
              "ball_nearest_speed": np.where(has & tracked[i, j], spd[i, j], UNKNOWN)})
    return np.stack([f[name] for name in FRAME_FEATURES], axis=1).astype(np.int64)


def window_rows(F, lo, hi, edge, side, stop_len, kind):
    """Edge-model rows (EDGE_FEATURES) for frames lo..hi-1: their signals plus the stop's context.

    edge: the dead_mask_v2 edge the window is centred on; side 0 for a start, 1 for an end; kind: KINDS index.
    """
    ctx = np.empty((hi - lo, 4), np.int64)
    ctx[:, 0] = np.arange(lo, hi) - edge
    ctx[:, 1], ctx[:, 2], ctx[:, 3] = side, stop_len, kind
    return np.hstack([F[lo:hi], ctx])


def tree_scores(X, part):
    """Integer raw score of exported trees: init plus one leaf per tree; x <= threshold goes left (#6).

    part: {"init": int, "trees": [{"feature", "threshold", "left", "right", "value"} as int64 arrays]}, one
    node per index; a leaf has feature -1.
    """
    s = np.full(len(X), part["init"], np.int64)
    rows = np.arange(len(X))
    for t in part["trees"]:
        node = np.zeros(len(X), np.int64)
        inner = t["feature"][node] >= 0
        while inner.any():
            at = node[inner]
            left = X[rows[inner], t["feature"][at]] <= t["threshold"][at]
            node[inner] = np.where(left, t["left"][at], t["right"][at])
            inner = t["feature"][node] >= 0
        s += t["value"][node]
    return s


def fit_step(dead_pred, rising):
    """The edge t in 0..m of a window that leaves the fewest frames on the wrong side; ties: the earliest.

    rising: live before t and D from t on (a stop's start); otherwise D before t and live from t on (its end).
    """
    d = np.r_[0, np.cumsum(dead_pred, dtype=np.int64)]
    t = np.arange(len(dead_pred) + 1)
    cost = 2 * d - t + len(dead_pred) - d[-1] if rising else t - 2 * d + d[-1]
    return int(np.argmin(cost))


KINDS = ("THROW IN", "FREE KICK", "GOAL KICK", "CORNER KICK", "KICK OFF", "OTHER")
STOP_FEATURES = ("min_sideline", "min_corner", "min_center", "min_goal_area", "n_in_boxes", "own_half_pct",
                 "team_x_gap", "n_near_center", "ball_known", "ball_sideline", "ball_goal_line", "ball_center", "stop_len")
# Laws of the game, in cm: middle of the goal area's depth, penalty area depth and half width, centre circle
GOAL_AREA, BOX_DEPTH, BOX_HALF_WIDTH, CIRCLE = 275, 1650, 2016, 915
FAR = np.iinfo(np.int64).max


def _landmarks(pitch):
    length, width = round(pitch[0] * 100), round(pitch[1] * 100)
    return length, width, length // 2, width // 2


def stop_features(players, xy, team, a, b, pitch=PITCH):
    """Integer formation signals (STOP_FEATURES) over the 2 s before a stop's end b, to name its restart kind.

    xy: ball_position(ball, MAX_INTERP). Minima over players and frames, the players in the penalty areas
    (median frame), the share in their own half and the ones in the centre circle (last frame), and the ball
    at the last frame of the stop.
    """
    lo = max(a, b - 2 * FPS)
    length, width, cx, cy = _landmarks(pitch)
    px, py = _int(players[lo:b, :, 0], pitch[0] * 100), _int(players[lo:b, :, 1], pitch[1] * 100)
    ok = ~np.isnan(players[lo:b, :, 0])

    def dist(x, y):
        return _isqrt((px - x) ** 2 + (py - y) ** 2)

    def lowest(v):
        return int(v[ok].min()) if ok.any() else UNKNOWN

    centre = dist(cx, cy)
    in_boxes = (ok & ((px < BOX_DEPTH) | (px > length - BOX_DEPTH)) & (np.abs(py - cy) < BOX_HALF_WIDTH)).sum(1)
    side = {t: ok & (team == t) for t in "HA"}
    mean_x = {t: int(px[m].sum()) // int(m.sum()) if m.any() else UNKNOWN for t, m in side.items()}
    both = UNKNOWN not in mean_x.values()
    last = ok[-1]
    left = "H" if mean_x["H"] <= mean_x["A"] else "A"
    own = last & np.where(team == left, px[-1] < cx, px[-1] >= cx)
    bx, by = _int(xy[b - 1:b, 0], pitch[0] * 100)[0], _int(xy[b - 1:b, 1], pitch[1] * 100)[0]
    known = bx != UNKNOWN
    f = {"min_sideline": lowest(np.minimum(py, width - py)),
         "min_corner": lowest(np.minimum.reduce([dist(x, y) for x in (0, length) for y in (0, width)])),
         "min_center": lowest(centre), "min_goal_area": lowest(np.minimum(dist(GOAL_AREA, cy), dist(length - GOAL_AREA, cy))),
         "n_in_boxes": int(np.sort(in_boxes)[(len(in_boxes) - 1) // 2]),
         "own_half_pct": 100 * int(own.sum()) // int(last.sum()) if both and last.any() else UNKNOWN,
         "team_x_gap": abs(mean_x["H"] - mean_x["A"]) if both else UNKNOWN,
         "n_near_center": int((last & (centre[-1] <= CIRCLE)).sum()), "ball_known": int(known),
         "ball_sideline": min(by, width - by) if known else UNKNOWN,
         "ball_goal_line": min(bx, length - bx) if known else UNKNOWN,
         "ball_center": int(_isqrt(np.array([(bx - cx) ** 2 + (by - cy) ** 2]))[0]) if known else UNKNOWN,
         "stop_len": b - a}
    return np.array([f[k] for k in STOP_FEATURES], np.int64)


def classify(Xs, parts):
    """KINDS index per row of stop features: the class whose exported trees score highest (first on ties)."""
    return np.argmax(np.stack([tree_scores(Xs, p) for p in parts], axis=1), axis=1)


def restart_team(players, xy, team, e, kind, radius_cm, pitch=PITCH):
    """Team of the tracked player nearest the restart point at frame e if within radius_cm, else "" (#34).

    The point is the ball where it is known (xy = ball_position(ball, MAX_INTERP)); otherwise where the kind
    puts the taker: the player nearest a sideline (throw-in), a corner flag (corner kick) or the middle of a
    goal area (goal kick), or the centre spot (kick-off). A free kick or another kind has no point without a ball.
    """
    length, width, cx, cy = _landmarks(pitch)
    ok = ~np.isnan(players[e, :, 0])
    px, py = _int(players[e, :, 0], pitch[0] * 100), _int(players[e, :, 1], pitch[1] * 100)

    def d2(x, y):
        return np.where(ok, (px - x) ** 2 + (py - y) ** 2, FAR)

    name = KINDS[kind]
    if not ok.any():
        return ""
    if not np.isnan(xy[e, 0]):
        point = _int(xy[e, 0:1], pitch[0] * 100)[0], _int(xy[e, 1:2], pitch[1] * 100)[0]
    elif name == "KICK OFF":
        point = cx, cy
    elif name in ("THROW IN", "CORNER KICK", "GOAL KICK"):
        near = {"THROW IN": lambda: np.where(ok, np.minimum(py, width - py), FAR),
                "CORNER KICK": lambda: np.minimum.reduce([d2(x, y) for x in (0, length) for y in (0, width)]),
                "GOAL KICK": lambda: np.minimum(d2(GOAL_AREA, cy), d2(length - GOAL_AREA, cy))}[name]()
        j = int(np.argmin(near))
        point = px[j], py[j]
    else:
        return ""
    d = d2(*point)
    j = int(np.argmin(d))
    return str(team[j]) if d[j] <= radius_cm * radius_cm else ""


def refine(dead, players, ball, team, spans, model, pitch=PITCH, F=None):
    """Stops with their edges moved and the team that restarts after each (ADR-010): (dead[n], initial[n]).

    spans: [(a, b)) stretches the stops live in (the halves); edges never leave them, never cross the
    neighbouring stops and a stop keeps at least one frame. Mode "model": each edge moves to the step that fits
    the edge model inside a window of model["window"] frames on each side; mode "planb": by lead[kind] and
    trim[kind] frames. initial[e] is the restart team on the first live frame e after a stop ("" if none). Mode
    "kick" (ADR-017): each end moves to the kick that restarts play (snap_ends), and nobody is named.
    F: frame_features(players, ball, pitch), when the caller already has it.
    """
    if model["mode"] == "kick":
        return snap_ends(dead, ball, spans, model, pitch), np.full(len(dead), "", dtype=object)
    out, initial = dead.copy(), np.full(len(dead), "", dtype=object)
    xy = ball_position(ball, MAX_INTERP)
    w = model["window"]
    if model["mode"] == "model" and F is None:
        F = frame_features(players, ball, pitch)
    for a, b in spans:
        stops = [(a + s, a + e) for s, e in runs(dead[a:b])]
        if not stops:
            continue
        kinds = classify(np.array([stop_features(players, xy, team, c, d, pitch) for c, d in stops]), model["type"])
        if model["mode"] == "model":
            # each edge's widest window inside the span; the real one is a slice once the neighbours have moved
            wide = [((max(c - w, a), min(c + w, d)), (max(d - w, a + 1), min(d + w, b))) for c, d in stops]
            rows = [window_rows(F, lo, hi, edge, side, d - c, k) for (c, d), k, both in zip(stops, kinds, wide)
                    for (lo, hi), edge, side in zip(both, (c, d), (0, 1))]
            pred = np.split(tree_scores(np.vstack(rows), model["edge"]) > 0, np.cumsum([len(r) for r in rows])[:-1])
        prev_end = a
        for j, (c, d) in enumerate(stops):
            nxt = stops[j + 1][0] if j + 1 < len(stops) else b
            kind = int(kinds[j])
            if model["mode"] == "planb":
                s = min(max(c - model["lead"][kind], prev_end), d - 1)
                e = min(max(d - model["trim"][kind], s + 1), nxt)
            else:
                (slo, _), (elo, _) = wide[j]
                lo, hi = max(c - w, prev_end), min(c + w, d)
                s = min(lo + fit_step(pred[2 * j][lo - slo:hi - slo], True), d - 1)
                lo, hi = max(d - w, s + 1), min(d + w, nxt)
                e = lo + fit_step(pred[2 * j + 1][lo - elo:hi - elo], False)
            out[c:d] = False
            out[s:e] = True
            if model["team_radius_cm"] > 0 and e < b:
                initial[e] = restart_team(players, xy, team, e, kind, model["team_radius_cm"], pitch)
            prev_end = e
    return out, initial


def load_model(path=MODEL_PATH):
    """The stop model that calibrate_edges.py exports, with its trees as int64 arrays.

    {"mode": "model" | "planb", "window": frames, "team_radius_cm": int (0: no restart team),
     "edge": {"init", "trees"} (mode "model"), "lead", "trim": frames per KINDS (mode "planb"),
     "type": [{"init", "trees"} per KINDS]}, or {"mode": "kick", **KICK_KEYS as integers} (ADR-017). A missing file
    stops the pipeline (FileNotFoundError), and so does a broken one (ValueError with its path): unknown mode, a list
    per kind of the wrong length, a number that is not an integer, a kick window or speed out of range, or a tree whose
    arrays differ in length or whose children do not come after their node.
    """
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        m = json.loads(text)
        if m["mode"] == "kick":
            if any(not isinstance(m[k], int) or isinstance(m[k], bool) or m[k] < 0 for k in KICK_KEYS) \
                    or min(m["after"], m["kick_cms"], m["rest_cms"]) < 1:
                raise ValueError("kick: integer before, rest >= 0 and after, kick_cms, rest_cms >= 1 expected")
            return {"mode": "kick", **{k: m[k] for k in KICK_KEYS}}
        if m["mode"] not in ("model", "planb") or not isinstance(m["window"], int) or m["window"] < 1 \
                or not isinstance(m["team_radius_cm"], int) or m["team_radius_cm"] < 0:
            raise ValueError("unknown mode, or window / team_radius_cm out of range")
        if len(m["type"]) != len(KINDS):
            raise ValueError(f"{len(KINDS)} kinds expected")
        m["type"] = [_tree_part(p, len(STOP_FEATURES)) for p in m["type"]]
        if m["mode"] == "model":
            m["edge"] = _tree_part(m["edge"], len(EDGE_FEATURES))
        else:
            m["lead"], m["trim"] = _ints(m["lead"], len(KINDS)).tolist(), _ints(m["trim"], len(KINDS)).tolist()
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        raise ValueError(f"{path}: not a stop model ({e!r})") from e
    return m


def _ints(v, n=None):
    if not isinstance(v, list) or not all(isinstance(x, int) and not isinstance(x, bool) for x in v):
        raise ValueError("integers expected")
    if n is not None and len(v) != n:
        raise ValueError(f"{n} values expected, {len(v)} found")
    return np.array(v, np.int64)


def _tree_part(p, width):
    """{"init", "trees"} from a model file with its trees as int64 arrays; ValueError if a tree is malformed: arrays
    of different lengths, a feature index of `width` or more, or children that do not come after their node."""
    if not isinstance(p.get("init"), int):
        raise ValueError("integer init expected")
    trees = []
    for t in p["trees"]:
        t = {k: _ints(t[k]) for k in ("feature", "threshold", "left", "right", "value")}
        inner = np.flatnonzero(t["feature"] >= 0)
        if len({len(v) for v in t.values()}) != 1 or (t["feature"] >= width).any() or \
                ((t["left"][inner] <= inner) | (t["right"][inner] <= inner) |
                 (t["left"][inner] >= len(t["feature"])) | (t["right"][inner] >= len(t["feature"]))).any():
            raise ValueError("malformed tree")
        trees.append(t)
    return {"init": p["init"], "trees": trees}


# -- The end of a stop at the kick that restarts play (ADR-017, #32) --------------------------------------------
# Both truths end a stop at the kick, and the ball near a restart is a real one in the ATD and in IDSSE. A restart is a
# ball at rest that is kicked, so the end of each stop moves to the nearest such kick. Positions in integer cm (#6).

KICK_RUN = 3  # fast steps in a row: the ball is played (explore/edge_clock.py)
KICK_KEYS = ("before", "after", "kick_cms", "rest", "rest_cms")


def kick_onsets(ball, kick_cms, rest, rest_cms, pitch=PITCH):
    """Frames t from which the ball moves at kick_cms cm/s or more for KICK_RUN steps (t -> t + 1 and the next ones),
    after `rest` steps slower than rest_cms (rest 0: any kick). A step from or to a missing ball is neither fast nor
    at rest. Squared speeds are compared as integers, so the result is exact on every CPU (#6)."""
    bx, by = _int(ball[:, 0], pitch[0] * 100), _int(ball[:, 1], pitch[1] * 100)
    seen = (bx != UNKNOWN) & (by != UNKNOWN)
    ok = seen[1:] & seen[:-1]
    d2 = np.where(ok, (bx[1:] - bx[:-1]) ** 2 + (by[1:] - by[:-1]) ** 2, 0) * (FPS * FPS)  # (cm/s)^2 of each step
    fast = np.r_[ok & (d2 >= kick_cms * kick_cms), False]
    slow = np.r_[ok & (d2 < rest_cms * rest_cms), False]
    played = fast.copy()
    for i in range(1, KICK_RUN):
        played &= np.r_[fast[i:], np.zeros(i, bool)]
    onsets = np.flatnonzero(played & ~np.r_[False, played[:-1]])
    c = np.r_[0, np.cumsum(slow)]
    return onsets[(onsets >= rest) & (c[onsets] - c[np.maximum(onsets - rest, 0)] == rest)]


def snap_ends(dead, ball, spans, model, pitch=PITCH):
    """Stops with each end moved to the kick that restarts play (ADR-017): the kick_onsets frame nearest the end within
    [end - before, end + after), the earlier on ties; without one, the end stays. spans: [(a, b)) stretches (the
    halves); an end never moves before its stop's second frame, onto the next stop or out of its span."""
    out = dead.copy()
    onsets = kick_onsets(ball, model["kick_cms"], model["rest"], model["rest_cms"], pitch)
    for a, b in spans:
        stops = [(a + s, a + e) for s, e in runs(dead[a:b])]
        for j, (c, d) in enumerate(stops):
            nxt = stops[j + 1][0] if j + 1 < len(stops) else b
            k = onsets[(onsets >= max(d - model["before"], c + 1)) & (onsets < min(d + model["after"], nxt))]
            if len(k):
                e = int(k[np.argmin(np.abs(k - d))])
                out[c:d] = False
                out[c:e] = True
    return out


# -- Live-play possession (ADR-014, #49 and #35) ----------------------------------------------------------------
# Per frame, integer signals of each team around the ball, its radio evidence before and after, its block and the
# ball; exported trees score them with each team as the own one, and the difference of the two scores feeds a
# two-state Viterbi inside each live stretch. calibrate_live.py trains them on open data (live_model.json).

LIVE_TEAM = ("nearest", "second", "n_3m", "n_10m", "nearest_speed", "closing", "ev_past_12", "ev_past_50",
             "ev_past_125", "ev_next_12", "ev_next_50", "ev_next_125", "ev_since", "ev_until", "tracked", "advance",
             "spread_x", "spread_y", "team_fwd", "ball_advance", "ball_fwd")
LIVE_SHARED = ("ball_seen", "ball_unseen", "ball_next_seen", "ball_known", "ball_speed", "live_since", "live_until")
LIVE_FEATURES = tuple("own_" + f for f in LIVE_TEAM) + tuple("rival_" + f for f in LIVE_TEAM) + LIVE_SHARED
EV_WINDOWS = (12, 2 * FPS, 5 * FPS)
MAX_SPEED_CM = 1200  # cm/s: a slot moving faster over 0.2 s jumped (substitution, period change, #53)


def _since_until(mask, cap=UNSEEN_CAP):
    """Frames since the last True and until the next one (0 on a True frame), capped."""
    n = len(mask)
    i = np.arange(n)
    last = np.maximum.accumulate(np.where(mask, i, -1))
    nxt = np.minimum.accumulate(np.where(mask, i, n)[::-1])[::-1]
    return (np.where(last >= 0, np.minimum(i - last, cap), cap).astype(np.int64),
            np.where(nxt < n, np.minimum(nxt - i, cap), cap).astype(np.int64))


def _lag(a, k):
    out = np.full_like(a, UNKNOWN)
    out[k:] = a[:-k]
    return out


def _live_span(players, ball, team, evidence, dead, pitch):
    """({"H": [n, LIVE_TEAM], "A": ...}, [n, LIVE_SHARED]) for one span (a half): live_features' work."""
    n = len(players)
    i = np.arange(n)
    length = round(pitch[0] * 100)
    xy = ball_position(ball, MAX_INTERP)
    known = ~np.isnan(xy[:, 0])
    bx, by = _int(xy[:, 0], pitch[0] * 100), _int(xy[:, 1], pitch[1] * 100)
    px, py = _int(players[:, :, 0], pitch[0] * 100), _int(players[:, :, 1], pitch[1] * 100)
    tracked = px != UNKNOWN
    spd = _int(players[:, :, 2], 100)
    k = FPS // 5  # velocities over 0.2 s
    moved = tracked & (_lag(px, k) != UNKNOWN)
    vx = np.where(moved, (px - _lag(px, k)) * (FPS // k), UNKNOWN)
    vy = np.where(moved, (py - _lag(py, k)) * (FPS // k), UNKNOWN)
    jump = moved & (vx * vx + vy * vy > MAX_SPEED_CM * MAX_SPEED_CM)
    vx[jump] = vy[jump] = UNKNOWN
    dx, dy = px - bx[:, None], py - by[:, None]
    near_ok = tracked & known[:, None]
    d2 = np.where(near_ok, dx * dx + dy * dy, FAR)
    centre = length // 2
    sums = {T: int(np.where(tracked[:, team == T], px[:, team == T], 0).sum()) for T in "HA"}
    counts = {T: int(tracked[:, team == T].sum()) for T in "HA"}
    mean = {T: sums[T] // counts[T] if counts[T] else 0 for T in "HA"}
    side = {"H": 1 if mean["H"] <= mean["A"] else -1}  # the team whose mean x is lower attacks towards x = length
    side["A"] = -side["H"]
    bmoved = known & (_lag(bx, k) != UNKNOWN)
    bvx = np.where(bmoved, (bx - _lag(bx, k)) * (FPS // k), UNKNOWN)
    bvy = np.where(bmoved, (by - _lag(by, k)) * (FPS // k), UNKNOWN)
    out = {}
    for T in "HA":
        m = np.flatnonzero(team == T)
        s = side[T]
        dt = d2[:, m]
        order = np.sort(dt, axis=1)
        has1 = order[:, 0] < FAR
        has2 = order[:, 1] < FAR if len(m) > 1 else np.zeros(n, bool)
        j = m[dt.argmin(1)]
        ok_v = has1 & (vx[i, j] != UNKNOWN)
        dist = np.maximum(_isqrt(np.where(has1, order[:, 0], 0)), 10)
        tr = tracked[:, m]
        cnt = tr.sum(1).astype(np.int64)
        mx = np.where(cnt > 0, np.where(tr, px[:, m], 0).sum(1) // np.maximum(cnt, 1), UNKNOWN)
        my = np.where(cnt > 0, np.where(tr, py[:, m], 0).sum(1) // np.maximum(cnt, 1), UNKNOWN)
        var_x = np.where(tr, (px[:, m] - mx[:, None]) ** 2, 0).sum(1) // np.maximum(cnt, 1)
        var_y = np.where(tr, (py[:, m] - my[:, None]) ** 2, 0).sum(1) // np.maximum(cnt, 1)
        v_ok = tr & (vx[:, m] != UNKNOWN)
        v_sum = _sums(np.where(v_ok, vx[:, m], 0).sum(1), FPS)[0]
        v_cnt = _sums(v_ok.sum(1).astype(np.int64), FPS)[0]
        e = (evidence == T).astype(np.int64)
        c = np.r_[0, np.cumsum(e)]
        f = {"nearest": np.where(has1, _isqrt(np.where(has1, order[:, 0], 0)), UNKNOWN),
             "second": np.where(has2, _isqrt(np.where(has2, order[:, 1] if len(m) > 1 else 0, 0)), UNKNOWN),
             "n_3m": np.where(known, (dt <= 300 * 300).sum(1), UNKNOWN),
             "n_10m": np.where(known, (dt <= 1000 * 1000).sum(1), UNKNOWN),
             "nearest_speed": np.where(has1, spd[i, j], UNKNOWN),
             "closing": np.where(ok_v, -(vx[i, j] * dx[i, j] + vy[i, j] * dy[i, j]) // dist, UNKNOWN),
             "tracked": cnt,
             "advance": np.where(cnt > 0, s * (mx - centre), UNKNOWN),
             "spread_x": np.where(cnt > 0, _isqrt(var_x), UNKNOWN),
             "spread_y": np.where(cnt > 0, _isqrt(var_y), UNKNOWN),
             "team_fwd": np.where(v_cnt > 0, s * v_sum // np.maximum(v_cnt, 1), UNKNOWN),
             "ball_advance": np.where(known, s * (bx - centre), UNKNOWN),
             "ball_fwd": np.where(bvx != UNKNOWN, s * bvx, UNKNOWN)}
        for w, tag in zip(EV_WINDOWS, ("12", "50", "125")):
            f["ev_past_" + tag] = c[i] - c[np.maximum(i - w, 0)]
            f["ev_next_" + tag] = c[np.minimum(i + w, n)] - c[i]
        f["ev_since"], f["ev_until"] = _since_until(e > 0)
        out[T] = np.stack([f[name] for name in LIVE_TEAM], axis=1).astype(np.int64)
    seen = ~np.isnan(ball[:, 0])
    unseen, next_seen = _since_until(seen)
    live_since = np.full(n, UNKNOWN, np.int64)
    live_until = np.full(n, UNKNOWN, np.int64)
    for a, b in runs(~dead):
        idx = np.arange(b - a)
        live_since[a:b], live_until[a:b] = np.minimum(idx, UNSEEN_CAP), np.minimum(idx[::-1], UNSEEN_CAP)
    shared = {"ball_seen": seen.astype(np.int64), "ball_unseen": unseen, "ball_next_seen": next_seen,
              "ball_known": known.astype(np.int64),
              "ball_speed": np.where(bvx != UNKNOWN, _isqrt(np.where(bvx != UNKNOWN, bvx * bvx + bvy * bvy, 0)), UNKNOWN),
              "live_since": live_since, "live_until": live_until}
    return out, np.stack([shared[name] for name in LIVE_SHARED], axis=1).astype(np.int64)


def live_features(players, ball, team, evidence, dead, spans, pitch=PITCH):
    """Integer signals of ADR-014 per frame, (F_H, F_A): LIVE_FEATURES with H, then A, as the own team.

    players[n, k, 3] = x, y (0-1), speed (m/s); ball[n, >=2] = x, y (0-1); evidence: owner_evidence with the control
    radius ("H" / "A" / ""); dead: the final D. Each span (a half) is computed apart, so no window crosses halftime,
    and frames outside the spans are UNKNOWN. Distances in cm, speeds in cm/s, frames and counts; UNKNOWN where a
    signal cannot be computed (no ball position, nobody tracked). Swapping the teams swaps F_H and F_A.
    """
    n = len(players)
    own = {T: np.full((n, len(LIVE_TEAM)), UNKNOWN, np.int64) for T in "HA"}
    shared = np.full((n, len(LIVE_SHARED)), UNKNOWN, np.int64)
    for a, b in spans:
        rows, shared[a:b] = _live_span(players[a:b], ball[a:b], team, evidence[a:b], dead[a:b], pitch)
        for T in "HA":
            own[T][a:b] = rows[T]
    return np.hstack([own["H"], own["A"], shared]), np.hstack([own["A"], own["H"], shared])


def decode_live(score, switch):
    """H / A per frame of one live stretch: the sequence that maximizes sum(score on H, -score on A) - switch * changes.

    score: int64 per frame (the own-team score with H minus the one with A); switch: integer cost of a change. A
    two-state Viterbi in Python integers, so it is exact on every machine (#6). On a tie the last frame is H, and a
    change that ties across frames goes to its earliest one (backdated, like confirm_changes).
    """
    s = [int(v) for v in score]
    n = len(s)
    out = np.empty(n, dtype=object)
    if not n:
        return out
    vh, va = s[0], -s[0]
    back = bytearray(n)  # bit 0: H came from A; bit 1: A came from H
    for t in range(1, n):
        from_a, from_h = va - switch, vh - switch
        b = 0
        if from_a > vh:
            vh_new, b = from_a, 1
        else:
            vh_new = vh
        if from_h > va:
            va, b = from_h, b | 2
        vh = vh_new + s[t]
        va -= s[t]
        back[t] = b
    state = "H" if vh >= va else "A"
    for t in range(n - 1, -1, -1):
        out[t] = state
        if state == "H" and back[t] & 1:
            state = "A"
        elif state == "A" and back[t] & 2:
            state = "H"
    return out


LIVE_MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "live_model.json")


def load_live_model(path=LIVE_MODEL_PATH):
    """The live-play model that calibrate_live.py exports (ADR-014): {"mode": "rule"}, which keeps confirm_changes,
    or {"mode": "model", "switch": int >= 0, "trees": {"init", "trees"}} with int64 trees over LIVE_FEATURES. A
    missing file stops the pipeline (FileNotFoundError), and so does a broken one (ValueError with its path)."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        m = json.loads(text)
        if m["mode"] == "rule":
            return {"mode": "rule"}
        switch = m["switch"]
        if m["mode"] != "model" or not isinstance(switch, int) or isinstance(switch, bool) or switch < 0:
            raise ValueError("unknown mode, or a switch that is not a non-negative integer")
        return {"mode": "model", "switch": switch, "trees": _tree_part(m["trees"], len(LIVE_FEATURES))}
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        raise ValueError(f"{path}: not a live model ({e!r})") from e


def live_score(players, ball, team, evidence, dead, spans, trees, pitch=PITCH):
    """Per frame, the trees' score with H as the own team minus the one with A (int64): what decode_live reads."""
    FH, FA = live_features(players, ball, team, evidence, dead, spans, pitch)
    return tree_scores(FH, trees) - tree_scores(FA, trees)


def segment_live(dead, score, spans, switch):
    """H / A / D inside the spans and X outside: D where dead, and decode_live in each live stretch (ADR-014)."""
    labels = np.full(len(dead), "X", dtype=object)
    for a, b in spans:
        labels[a:b] = np.where(dead[a:b], "D", "X")
        for s, e in runs(~dead[a:b]):
            labels[a + s:a + e] = decode_live(score[a + s:a + e], switch)
    return labels


def before_kickoff(dead):
    """dead with every graded frame before its half's kick-off marked dead: the ball is not in play yet (ADR-032)."""
    out = dead.copy()
    for (first, _), kick in zip(HALVES, KICKOFFS):
        out[first:kick] = True
    return out


def label(players, ball, team, model=None, live=None):
    """Full-length H/A/D/X array, one entry per tactical video frame.

    model: the stop model (load_model's dict); by default stops_model.json, without which nothing runs.
    live: the live-play model (load_live_model's dict); by default live_model.json, also required. In mode "rule"
    each live stretch keeps the change rule (ADR-001, ADR-009); in mode "model", decode_live labels it (ADR-014).
    """
    model = model or load_model()
    live = live or load_live_model()
    evidence = owner_evidence(players, ball, team, CONTROL_RADIUS, MAX_INTERP)
    spans = [(a, b + 1) for a, b in HALVES]
    dead, initial = refine(dead_mask_v2(players, ball), players, ball, team, spans, model)
    dead = before_kickoff(dead)
    if live["mode"] == "model":
        return segment_live(dead, live_score(players, ball, team, evidence, dead, spans, live["trees"]), spans,
                            live["switch"])
    labels = np.full(N_FRAMES, "X", dtype=object)
    for first, last in HALVES:
        half = slice(first, last + 1)
        labels[half] = np.where(dead[half], "D", "X")
        for start, end in runs(~dead[half]):
            labels[first + start:first + end] = confirm_changes(evidence[first + start:first + end], CHANGE_FRAMES,
                                                                initial=initial[first + start])
    return labels


def write_csv(labels, path):
    """frame,label CSV with LF line endings on every OS (#6). Returns the file's sha256."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("frame,label\n" + "".join(f"{i},{lab}\n" for i, lab in enumerate(labels)))
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


if __name__ == "__main__":
    if not DATA:
        sys.exit("set MTAH_DATA or pass the data dir (AGENTS.md)")
    labels = label(*load_atd())
    digest = write_csv(labels, OUT)
    print(f"wrote {OUT}: " + "  ".join(f"{k} {(labels == k).sum()}" for k in "HADX") + f"  sha256 {digest}")
