"""ADR-003, measurement 3: dead-ball rule B on IDSSE events against the provider's BallStatus.

IDSSE (Bassek et al., Scientific Data 12, 195, 2025; CC BY 4.0): 7 Bundesliga matches with DFL tracking
at 25 Hz whose ball frames carry BallStatus (1 alive, 0 dead) and BallPossession. Open data (AGENTS.md).
Rule B needs its own lists per provider (ADR-003); the DFL ones are RESTARTS, BALL_EVENTS and stops_play.

Usage: python idsse_dead_labels.py [idsse dir]
The dir (default ../idsse-data) holds the files of huggingface.co/datasets/pysport/idsse-data, revision
a715a38dfbaf5f58e431727c2b78d174101a703c, as they come: DFL_03_02_events_raw_* and DFL_04_03_positions_raw_observed_*.
"""
import glob
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime

import numpy as np

from calibrate_dead import MAX_DEAD_S
from possession import runs

DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "idsse-data")
FPS = 25  # DFL positions; load_ball checks it against the frame timestamps

RESTARTS = {"ThrowIn", "FreeKick", "GoalKick", "CornerKick", "Penalty", "KickOff", "RefereeBall"}
# Ball events and stops. Cards, substitutions, VAR and play annotations (Nutmeg, Run, ...) are left out,
# as ADR-003 leaves out CARD: they happen with the ball dead or tag another event.
BALL_EVENTS = RESTARTS | {"Play", "OtherBallAction", "TacklingGame", "BallClaiming", "BallDeflection",
                          "ShotAtGoal", "Foul", "Offside", "FairPlay"}


def stops_play(kind, sub):
    """ADR-003's list for lifting the cap, in DFL terms: shot wide or goal, foul, offside (no ball-out event)."""
    return kind in ("Foul", "Offside") or (kind == "ShotAtGoal" and sub in ("ShotWide", "SuccessfulShot"))


def dead_spans(events, decision=False, cap=MAX_DEAD_S):
    """[(start, end)] seconds of dead ball by rule B (ADR-003) on one section's events, sorted by time.

    events: [(t, kind, sub, decision_t or None)]. A restart closes the span opened by the last ball event
    before it. A span longer than cap seconds is dropped unless that event stops play; cap=None keeps all.
    decision=True opens the span at the restart's DecisionTimestamp when it has one, with no cap: the
    referee's decision is an explicit stop. Kick-offs and dropped balls have none and keep rule B.
    """
    spans, prev = [], None
    for t, kind, sub, dec in events:
        if kind not in BALL_EVENTS:
            continue
        if kind in RESTARTS and prev is not None:
            if decision and dec is not None and dec < t:
                spans.append((dec, t))
            elif cap is None or t - prev[0] <= cap or stops_play(*prev[1:]):
                spans.append((prev[0], t))
        prev = (t, kind, sub)
    return spans


def edge_offsets(truth, pred):
    """Start and end offsets in frames (pred - truth) of the truth runs matched by a pred run with IoU >= 0.5."""
    pred_runs = runs(pred)
    starts, ends = [], []
    for a, b in runs(truth):
        best = max(pred_runs, key=lambda r: min(b, r[1]) - max(a, r[0]), default=None)
        if best is not None and min(b, best[1]) - max(a, best[0]) >= 0.5 * (max(b, best[1]) - min(a, best[0])):
            starts.append(int(best[0] - a))
            ends.append(int(best[1] - b))
    return starts, ends


def seconds(iso):
    return datetime.fromisoformat(iso).timestamp()


def load_events(path):
    """[(t, kind, sub, decision_t or None)] sorted by time. A Delete entry replaces a deleted event: dropped."""
    out = []
    for e in ET.parse(path).getroot().iter("Event"):
        if len(e) and e[0].tag != "Delete":
            k, dec = e[0], e[0].get("DecisionTimestamp")
            out.append((seconds(e.get("EventTime")), k.tag, k[0].tag if len(k) else "", seconds(dec) if dec else None))
    return sorted(out, key=lambda x: x[0])


def load_ball(path):
    """{section: (t[n] seconds, status[n], possession[n])} from the ball's frames; status 1 alive, 0 dead."""
    out = {}
    for _, el in ET.iterparse(path):
        if el.tag == "FrameSet":
            if el.get("TeamId") == "BALL":
                frames = el.findall("Frame")
                t = np.array([seconds(f.get("T")) for f in frames])
                assert np.allclose(np.median(np.diff(t)), 1 / FPS), "not 25 Hz"
                out[el.get("GameSection")] = (t, np.array([int(f.get("BallStatus")) for f in frames], np.int8),
                                              np.array([int(f.get("BallPossession", 0)) for f in frames], np.int8))
            el.clear()  # players' frames are not needed
    return out


RULES = {"B": {}, "B no cap": {"cap": None}, "decision": {"decision": True}}


def measure(events, ball):
    """{rule: [tp, fp, fn, start offsets, end offsets, truth runs]} in frames, over the ball's sections.

    Graded: from each section's first to its last ball event (rule B has nothing before the opening kick-off).
    """
    res = {rule: [0, 0, 0, [], [], 0] for rule in RULES}
    for t, status, _ in ball.values():
        section = [e for e in events if t[0] <= e[0] <= t[-1]]
        times = [e[0] for e in section if e[1] in BALL_EVENTS]
        graded = (t >= times[0]) & (t <= times[-1])
        truth = (status == 0) & graded
        for rule, r in res.items():
            pred = np.zeros(len(t), bool)
            for s, e in dead_spans(section, **RULES[rule]):
                pred[np.searchsorted(t, s):np.searchsorted(t, e)] = True
            pred &= graded
            r[0] += int((pred & truth).sum())
            r[1] += int((pred & ~truth).sum())
            r[2] += int((~pred & truth).sum())
            starts, ends = edge_offsets(truth, pred)
            r[3] += starts
            r[4] += ends
            r[5] += len(runs(truth))
    return res


def report(name, r):
    tp, fp, fn, starts, ends, n_runs = r
    p, rec = tp / (tp + fp), tp / (tp + fn)
    return (f"{name:9} P {p:.3f}  R {rec:.3f}  F1 {2 * p * rec / (p + rec):.3f}  "
            f"matched {len(starts)}/{n_runs}  start {np.median(starts) / FPS:+.2f} s  end {np.median(ends) / FPS:+.2f} s")


if __name__ == "__main__":
    total = {rule: [0, 0, 0, [], [], 0] for rule in RULES}
    for path in sorted(glob.glob(os.path.join(DATA, "DFL_03_02_events_raw_*.xml"))):
        match = re.search(r"DFL-MAT-(\w+)\.xml$", path).group(1)
        ball = load_ball(glob.glob(os.path.join(DATA, f"DFL_04_03_positions_raw_observed_*{match}.xml"))[0])
        res = measure(load_events(path), ball)
        alive = sum(int((s == 1).sum()) for _, s, _ in ball.values())
        spells = [b - a for _, s, p in ball.values() for team in (1, 2) for a, b in runs((s == 1) & (p == team))]
        print(f"\n{match}: {len(spells)} possession spells in live ball (median {np.median(spells) / FPS:.1f} s), "
              f"owner set in {sum(int(((s == 1) & (p > 0)).sum()) for _, s, p in ball.values()) / alive:.1%} of live frames")
        for rule, r in res.items():
            print("  " + report(rule, r))
            total[rule] = [a + b for a, b in zip(total[rule], r)]
    print("\nall matches")
    for rule, r in total.items():
        print("  " + report(rule, r))
