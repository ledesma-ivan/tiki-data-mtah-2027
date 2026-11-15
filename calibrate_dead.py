"""Dead-ball calibration on Metrica Sample Game 3 (open data), ADR-002 step 4.

Labels: D from the events (ADR-003: the previous event -> the next restart). The detector is possession.dead_mask.
Never calibrated on the public window of BAR-ATH (challenge rules).
Data: Metrica Sports sample-data, https://github.com/metrica-sports/sample-data (cite it in the doc).

Usage: python calibrate_dead.py [path/to/Sample_Game_3]
"""
import itertools
import json
import os
import sys
import warnings

import numpy as np

from possession import dead_mask, pitch_dimensions, runs
from open_tracking import SPEED_VERSION, cache_matches, derived_speed, frame_numbers, game3_continuity, source_signature

G3 = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "Sample_Game_3")
PREFIX = os.path.join(G3, "Sample_Game_3_")
CACHE = PREFIX + "tracking.npz"

FPS = 25
PITCH = (105.0, 68.0)  # metres, from the metadata FieldSize
N_SLOTS = 22
MAX_DEAD_S = 60  # cap for gaps that do not start at a stop: longer = missing events, not dead ball


def game3_result(players, ball, pitch):
    """Surface missing continuity on cold and warm loads, without exposing rows."""
    if not np.isfinite(players[:, :, 2]).any():
        warnings.warn("Game 3 has no finite derived speeds; check identity/period metadata and tracking continuity",
                      RuntimeWarning, stacklevel=2)
    return players, ball, pitch


def load_game3():
    """(players[n,22,3], ball[n,2], pitch) indexed by frameCount - 1; speed in m/s."""
    pitch = pitch_dimensions(PITCH)
    sources = source_signature([PREFIX + "tracking.txt", PREFIX + "metadata.xml"])
    if os.path.exists(CACHE):
        with np.load(CACHE) as z:
            if cache_matches(z, pitch, sources):
                return game3_result(z["players"], z["ball"], pitch)
    with open(PREFIX + "tracking.txt") as f:
        a = np.array([line.rstrip("\n").replace(";", ",").replace(":", ",").split(",")
                      for line in f], dtype=float)
    frames = frame_numbers(a[:, 0])
    if a.shape[1] != 1 + N_SLOTS * 2 + 2:
        raise ValueError("unexpected Game 3 tracking columns")
    # Preserve frameCount - 1 alignment, including missing rows.
    xy = np.full((frames[-1], N_SLOTS, 2), np.nan)
    ball = np.full((frames[-1], 2), np.nan)
    xy[frames - 1] = a[:, 1:1 + N_SLOTS * 2].reshape(-1, N_SLOTS, 2)
    ball[frames - 1] = a[:, 1 + N_SLOTS * 2:]
    clock = np.arange(1, len(xy) + 1)
    identities, periods = game3_continuity(PREFIX + "metadata.xml", clock, N_SLOTS)
    speed = derived_speed(xy, identities, periods, clock, scale=pitch, fps=FPS)
    players = np.concatenate([xy, speed[..., None]], axis=2)
    np.savez_compressed(CACHE, players=players, ball=ball, pitch=pitch,
                        speed_version=SPEED_VERSION, sources=sources)
    return game3_result(players, ball, pitch)


def load_events():
    """[(type, subtype, start, end, period)] with 0-based frames; subtype "" or "A+B" for several."""
    out = []
    for e in json.load(open(PREFIX + "events.json"))["data"]:
        s = e["subtypes"] or []
        s = [s] if isinstance(s, dict) else s
        out.append((e["type"]["name"], "+".join(x["name"] for x in s),
                    e["start"]["frame"] - 1, e["end"]["frame"] - 1, e["period"]))
    return out


def halves(events):
    """[(first, last)] frame range of each period, from its first and last event."""
    return [(min(e[2] for e in events if e[4] == p), max(e[3] for e in events if e[4] == p))
            for p in sorted({e[4] for e in events})]


def dead_labels(events, n):
    """Ground-truth dead ball per frame (bool[n]), derived from the events (ADR-003).

    events: [(type, subtype, start, end, period)], sorted by start, frames 0-based.
    Option B: every restart implies the ball was dead before it, so D runs from the end of the
    previous event (same period) to the restart's start. Advantage play yields no D because it
    has no restart.
      restarts: SET PIECE (90: THROW IN, FREE KICK, CORNER KICK, KICK OFF), GOAL KICK (11: 8 PASS, 3 BALL LOST)
    A gap longer than MAX_DEAD_S is dropped unless the previous event stops play by itself: it
    points at a missing event, not a real stoppage.
    """
    d = np.zeros(n, bool)
    for a, s, cap in restart_gaps(events):
        if 0 < s - a <= cap:
            d[a:s] = True
    return d


def restart_gaps(events):
    """[(previous_end, restart_start, cap)] for every restart that has an earlier event in its period.

    The single definition of "restart" and "previous event" (ADR-003), shared by dead_labels and
    the discarded-gap audit. events must be sorted by start.
    - restart: SET PIECE, or any event with a GOAL KICK subtype (a lost goal kick is a BALL LOST).
    - previous: the latest end among the period's events that START before the restart, except a
      CARD. Metrica tags a RECOVERY on the goal-kick frame, and a card is shown with the ball dead.
    - cap: MAX_DEAD_S in frames, or inf when the previous event stops play by itself.
    """
    gaps = []
    for i, (typ, sub, s, _, per) in enumerate(events):
        if typ != "SET PIECE" and "GOAL KICK" not in sub:
            continue
        # sorted by start, not end: the latest end among earlier events is the real "previous"
        prev = max((e for e in events[:i] if e[4] == per and e[2] < s and e[0] != "CARD"),
                   key=lambda e: e[3], default=None)
        if prev is not None:
            gaps.append((prev[3], s, np.inf if stops_play(prev[0], prev[1]) else MAX_DEAD_S * FPS))
    return gaps


def stops_play(typ, sub):
    """True if the ball is dead after this event by definition: out, goal, foul, offside, hand ball.

    It only lifts the cap, so a stop missing from this list fails safe: the cap still applies.
    """
    parts = set(sub.split("+"))
    return (typ in ("BALL OUT", "FAULT RECEIVED") or (typ == "CHALLENGE" and "FAULT" in parts)
            or (typ == "SHOT" and bool(parts & {"OUT", "GOAL"})) or bool(parts & {"OFFSIDE", "HAND BALL"}))


def score(pred, true, mask):
    """Frame P/R/F1 of D, and segments: label count, pred count, share of label segments matched
    at IoU >= 0.5, median start and end offset in seconds of those matches (+ = pred late)."""
    p, t = pred & mask, true & mask
    tp = (p & t).sum()
    prec, rec = tp / max(p.sum(), 1), tp / max(t.sum(), 1)
    f1 = 2 * prec * rec / max(prec + rec, 1e-9)
    ps, ts = runs(p), runs(t)
    starts, ends = [], []
    for a, b in ts:
        best = max(ps, key=lambda s: min(b, s[1]) - max(a, s[0]), default=None)
        if best and (min(b, best[1]) - max(a, best[0])) / (max(b, best[1]) - min(a, best[0])) >= 0.5:
            starts.append((best[0] - a) / FPS)
            ends.append((best[1] - b) / FPS)
    return dict(P=prec, R=rec, F1=f1, n_true=len(ts), n_pred=len(ps), matched=len(starts) / max(len(ts), 1),
                start_s=np.median(starts) if starts else np.nan, end_s=np.median(ends) if ends else np.nan)


def fp_run_groups(pred, true, mask):
    """Return (frame_count, side) for each FP run, in chronological order.

    Keep the report's existing gap <= 2 s rule. A run before a labeled D is
    'before_start'; one after it is 'after_end'. Runs near both neighbors are
    'between_two', so no frame is counted twice. Everything else is 'isolated'.
    Each category counts the WHOLE FP run, not only frames within 2 s of a D.
    Proximity describes disagreements with labels; it does not establish their cause.
    """
    tr = runs(true & mask)
    grouped = []
    for s, e in runs(pred & ~true & mask):
        before = any(0 <= a - e <= 2 * FPS for a, _ in tr)
        after = any(0 <= s - b <= 2 * FPS for _, b in tr)
        side = ("between_two" if before and after else "before_start" if before
                else "after_end" if after else "isolated")
        grouped.append((e - s, side))
    return grouped


def fp_report(pred, true, mask, players, ball):
    """Describe FP signals, nearby label edges, and the ten longest FP durations.

    These are disagreements with event-derived labels, not verified detector errors.
    Missing-ball or slow-player signals and proximity to a D help diagnose them.
    A short FP fragment can belong to a long prediction: its length alone does not
    justify increasing the detector's minimum duration. See fp_run_groups for sides.
    Aggregates and durations only; no frame indices or event timestamps.
    """
    fp = pred & ~true & mask
    n_fp = int(fp.sum())
    print(f"FP frames {n_fp} ({n_fp / FPS / 60:.1f} min)")
    if n_fp == 0:
        print("FP runs 0; no false-positive segments to diagnose.")
        return

    bx, by = ball[:, 0], ball[:, 1]
    speed = players[:, :, 2]
    has_speed = (~np.isnan(speed)).any(axis=1)
    slow = np.zeros(len(speed), dtype=bool)
    # Unknown speed stays False, as with nanmean(...) < 1, without an empty mean.
    slow[has_speed] = np.nanmean(speed[has_speed], axis=1) < 1
    sig = {"missing": np.isnan(bx), "offpitch": (bx < 0) | (bx > 1) | (by < 0) | (by > 1),
           "slow": slow}
    only_slow = fp & sig["slow"] & ~sig["missing"] & ~sig["offpitch"]
    print("share of FP frames with signal on: " + "  ".join(f"{k} {v[fp].mean():.0%}" for k, v in sig.items())
          + f"  | only slow {only_slow.sum() / n_fp:.0%}")
    grouped = fp_run_groups(pred, true, mask)
    dur = np.array([frames for frames, _ in grouped]) / FPS
    near = np.array([side != "isolated" for _, side in grouped])
    print(f"FP runs {len(grouped)}  median {np.median(dur):.1f}s  <2s: {(dur < 2).mean():.0%}"
          f"  touching a labeled D: {near.mean():.0%}")

    print("FP location (whole runs; gap <= 2s; exclusive categories)")
    print("side          runs  frames seconds share_frames")
    for side in ("before_start", "after_end", "between_two", "isolated"):
        counts = [frames for frames, group in grouped if group == side]
        frames = sum(counts)
        print(f"{side:13} {len(counts):4} {frames:7} {frames / FPS:7.2f} {frames / n_fp:11.1%}")

    print("longest FP runs (durations only)")
    print("rank frames seconds side")
    for rank, (frames, side) in enumerate(sorted(grouped, key=lambda row: -row[0])[:10], 1):
        print(f"{rank:4} {frames:6} {frames / FPS:7.2f} {side}")


def discarded_gap_stats(events, pred, true, mask):
    """Measure FP overlap with restart gaps rejected by the cap (MAX_DEAD_S, ADR-003).

    Uses restart_gaps, the same restarts, previous-event rule and cap as dead_labels.
    This is only an audit mask: it never changes labels or scores. Rejected gaps can
    contain missing events or real stoppages, so overlap alone does not decide which.
    events must be sorted by start, as in the calibration entry point.
    """
    discarded = np.zeros(len(mask), dtype=bool)
    n_gaps = 0
    for previous_end, start, cap in restart_gaps(events):
        if start - previous_end > cap:
            n_gaps += 1
            discarded[max(0, previous_end):min(start, len(mask))] = True
    discarded &= mask
    fp = pred & ~true & mask
    grouped = fp_run_groups(pred, true, mask)
    details = []
    for (start, end), (frames, side) in zip(runs(fp), grouped):
        details.append(dict(frames=int(frames), side=side,
                            overlap=int(discarded[start:end].sum())))
    isolated = [row for row in details if row["side"] == "isolated"]
    return dict(gaps=n_gaps, discarded_frames=int(discarded.sum()),
                fp_frames=int(fp.sum()), fp_overlap=int((fp & discarded).sum()),
                isolated_frames=sum(row["frames"] for row in isolated),
                isolated_overlap=sum(row["overlap"] for row in isolated),
                longest=sorted(details, key=lambda row: -row["frames"])[:10])


def fp_edge_events(events, pred, true, mask, top=3):
    """Event types around the `top` longest FP runs: what the labels saw at their edges.

    Per run: the event that ended last before it, the one that starts first after it, and a
    count of the event types inside it. Types and durations only, no frame indices.
    A restart type missing from restart_gaps would show up here as the "after" event.
    events must be sorted by start.
    """
    def name(ev):
        return ev[0] + ("/" + ev[1] if ev[1] else "")

    rows = sorted(zip(runs(pred & ~true & mask), fp_run_groups(pred, true, mask)), key=lambda r: -r[1][0])
    out = []
    for (s, e), (frames, side) in rows[:top]:
        before = max((ev for ev in events if ev[3] <= s), key=lambda ev: ev[3], default=None)
        after = min((ev for ev in events if ev[2] >= e), key=lambda ev: ev[2], default=None)
        inside = {}
        for ev in events:
            if ev[2] < e and ev[3] > s:
                inside[name(ev)] = inside.get(name(ev), 0) + 1
        out.append(dict(seconds=frames / FPS, side=side, before=name(before) if before else "-",
                        after=name(after) if after else "-", inside=inside))
    return out


def fp_edge_report(events, pred, true, mask):
    print("\nlongest FP runs: event types at their edges")
    for rank, r in enumerate(fp_edge_events(events, pred, true, mask), 1):
        inside = ", ".join(f"{k} x{v}" for k, v in sorted(r["inside"].items(), key=lambda kv: -kv[1])[:5])
        print(f"{rank}. {r['seconds']:.1f}s {r['side']}  before: {r['before']}  after: {r['after']}"
              f"  inside: {inside or 'no events'}")


def discarded_gap_report(events, pred, true, mask):
    """Print durations and overlap counts only, without changing the evaluation."""
    stats = discarded_gap_stats(events, pred, true, mask)
    print(f"\ndiscarded restart gaps > {MAX_DEAD_S}s not starting at a stop (diagnostic only)")
    print(f"gaps {stats['gaps']}  union frames in evaluation mask {stats['discarded_frames']}")
    print(f"FP overlap {stats['fp_overlap']} / {stats['fp_frames']} frames "
          f"({stats['fp_overlap'] / max(stats['fp_frames'], 1):.1%} of all FP)")
    print(f"isolated FP overlap {stats['isolated_overlap']} / {stats['isolated_frames']} frames "
          f"({stats['isolated_overlap'] / max(stats['isolated_frames'], 1):.1%} of isolated FP)")
    if stats["longest"]:
        print("longest FP runs: overlap with discarded gaps")
        print("rank seconds side          overlap_s coverage")
        for rank, row in enumerate(stats["longest"], 1):
            print(f"{rank:4} {row['frames'] / FPS:7.2f} {row['side']:13} "
                  f"{row['overlap'] / FPS:9.2f} {row['overlap'] / row['frames']:7.1%}")
    print("Overlap is a diagnostic clue; it does not establish that a rejected gap was dead ball.")


if __name__ == "__main__":
    players, ball, pitch = load_game3()
    events = sorted(load_events(), key=lambda e: e[2])
    true = dead_labels(events, len(ball))
    mask = np.zeros(len(ball), dtype=bool)
    for first, last in halves(events):
        mask[first:last + 1] = True
    print(f"frames {mask.sum()}  label D {true[mask].mean():.1%}")

    rows = []
    for w, m, t in itertools.product([1, 2, 4], [1, 2, 3, 5], [0.3, 0.5, 0.7]):
        r = score(dead_mask(players, ball, w * FPS, m * FPS, t), true, mask)
        rows.append((w, m, t, r))
    print("window_s min_s thr     P     R    F1  n_true n_pred matched start_s end_s")
    for w, m, t, r in sorted(rows, key=lambda x: -x[3]["F1"])[:10]:
        print(f"{w:8} {m:5} {t:4} {r['P']:.3f} {r['R']:.3f} {r['F1']:.3f} {r['n_true']:7} {r['n_pred']:6}"
              f" {r['matched']:7.2f} {r['start_s']:7.2f} {r['end_s']:5.2f}")
    print("\nfalse positives at window 1, min 2, thr 0.5")
    pred = dead_mask(players, ball, 1 * FPS, 2 * FPS, 0.5)
    fp_report(pred, true, mask, players, ball)
    discarded_gap_report(events, pred, true, mask)
    fp_edge_report(events, pred, true, mask)
