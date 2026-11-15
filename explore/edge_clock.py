"""The stop edges of each bench's truth and of the v2 on the ball's clock, by restart kind (#32, ADR-010).

Usage: python explore/edge_clock.py [--seeds 3]
explore/edge_offsets_by_kind.py shows that the benches disagree on where the v2 edges fall, mostly at free kicks.
Two causes are possible: the speed (IDSSE has the provider's, Metrica's comes from the positions) or where each
provider marks a stop (Metrica's corrected tracking drops the ball, DFL sets BallStatus). Both benches have the
ball, so its physics is the common clock:
- restart: the frame from which the ball moves at KICK m/s or more for RUN frames, nearest the truth's restart;
- start with the ball out (throw-in, goal kick, corner): the first frame the ball is seen off the pitch;
- start after a foul (free kick): the infringement. Metrica's truth starts at the previous event, so it is 0 there
  by construction; IDSSE's is the DFL Foul or Offside event, moved onto the tracking clock by the median gap
  between each section's restart events and kicks. The same gap gives the IDSSE kinds (ADR-010 left 31% unknown).
IDSSE runs with the provider's speeds and with speeds from the positions, computed as the Metrica bench does.
Open data only (AGENTS.md): the selection matches of ADR-010 (Metrica Games 2-3, IDSSE 1-5). The v2 runs on the
degraded ball, as in the bench; the clock uses the ball as it comes. All ten open pitches are 105 x 68 m (#52).
"""
import argparse
import collections
import glob
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
_argv, sys.argv = sys.argv, sys.argv[:1]  # calibrate_edges' imports read sys.argv[1]
import calibrate_edges as C  # noqa: E402
import idsse_dead_labels  # noqa: E402
import possession as P  # noqa: E402
sys.argv = _argv

FPS = P.FPS
KICK, RUN = 4.0, 3  # the ball is played: at least 4 m/s for 3 frames in a row
REACH = 3 * FPS  # how far from the truth's edge its physical edge is looked for
OUT = ("THROW IN", "GOAL KICK", "CORNER KICK")


def onsets(mask):
    return np.flatnonzero(mask & ~np.r_[False, mask[:-1]])


def kicks(ball, *, pitch):
    """Frames from which the ball moves at KICK m/s or more for RUN frames (forward differences, metres)."""
    step = np.diff(ball[:, :2], axis=0, append=np.nan) * P.pitch_dimensions(pitch)
    fast = np.hypot(step[:, 0], step[:, 1]) * FPS >= KICK  # a missing ball is never fast
    played = fast.copy()
    for i in range(1, RUN):
        played &= np.r_[fast[i:], np.zeros(i, bool)]
    return onsets(played)


def outs(ball):
    x, y = ball[:, 0], ball[:, 1]
    return onsets((x < 0) | (x > 1) | (y < 0) | (y > 1))  # a missing ball is never off the pitch


def nearest(frames, f, reach=REACH):
    """Index of the frame nearest f within reach (frames sorted: the earlier on ties), or None."""
    d = np.abs(np.asarray(frames) - f)
    return int(np.argmin(d)) if len(d) and d.min() <= reach else None


def at(frames, f, reach=REACH):
    i = nearest(frames, f, reach)
    return None if i is None else int(frames[i])


def infringements(path):
    """{section: [frames]} of the DFL Foul and Offside events on the ball frames' clock, cached next to the file."""
    cache = path + ".fouls.json"
    if not os.path.exists(cache):
        match = re.search(r"DFL-MAT-(\w+)\.xml$", path).group(1)
        events = idsse_dead_labels.load_events(glob.glob(os.path.join(C.IDSSE, f"DFL_03_02_events_raw_*{match}.xml"))[0])
        out = {section: [int(np.searchsorted(t, et)) for et, k, _, _ in events
                         if k in ("Foul", "Offside") and t[0] <= et <= t[-1]]
               for section, (t, _, _) in idsse_dead_labels.load_ball(path).items()}
        with open(cache, "w") as f:
            json.dump(out, f)
    with open(cache) as f:
        return json.load(f)


def stops(game, match, h):
    """[(kind, a, b, start reference, kick)] of the true stops with a kind (None where a reference is missing), the
    DFL clock gap in frames and the IDSSE unknown kinds before and after moving the events onto the kicks' clock."""
    kk, oo = kicks(game.ball, pitch=game.pitch), outs(game.ball)
    gap, unknown, kinds = 0, (0, 0), [k for _, _, k in game.kinds]
    if match[0] == "idsse":
        path = C.idsse_files()[match[1] - 1]
        section = sorted(C.restart_frames(path))[h]
        events = C.restart_frames(path)[section]
        ev = np.array([f for f, _ in events], dtype=int)
        gaps = [int(ev[i]) - k for k in (at(kk, b) for _, b, _ in game.kinds) if k is not None
                for i in [nearest(ev, k, 20 * FPS)] if i is not None]
        gap = int(np.median(gaps)) if gaps else 0
        fouls = np.array(infringements(path)[section], dtype=int) - gap
        anchors = [at(kk, b) if at(kk, b) is not None else b for _, b, _ in game.kinds]
        kinds = [-1 if (i := nearest(ev - gap, f, 2 * FPS)) is None else events[i][1] for f in anchors]
        unknown = (sum(k < 0 for _, _, k in game.kinds), sum(k < 0 for k in kinds))
    out = []
    for (a, b, _), k in zip(game.kinds, kinds):
        if k < 0:
            continue
        name = P.KINDS[k]
        start = (at(oo, a) if name in OUT else
                 (a if match[0] == "metrica" else at(fouls, a)) if name == "FREE KICK" else None)
        out.append((name, a, b, start, at(kk, b)))
    return out, gap, unknown


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seeds", type=int, default=3)
    a = ap.parse_args()
    count = collections.defaultdict(lambda: [0, 0])  # (edge, kind, bench) -> [stops, with a reference]
    truth, v2, v2_truth = collections.defaultdict(list), collections.defaultdict(list), collections.defaultdict(list)
    gaps, unknown = [], np.zeros(2, int)
    for match in C.SELECTION:
        bench_name = match[0]
        for speed in ("provider", "positions") if bench_name == "idsse" else ("positions",):
            first = speed == ("provider" if bench_name == "idsse" else "positions")
            for h, g in enumerate(C.load(match, speed)):
                ss, gap, unk = stops(g, match, h)
                if first and bench_name == "idsse":
                    gaps.append((match[1], h, gap / FPS))
                    unknown += unk
                hulls = []
                for s in range(a.seeds):
                    hulls.append(P.runs(P.dead_mask_v2(g.players, C.degraded(g, 1000 * g.g + s))))
                for name, ta, tb, start, kick in ss:
                    for edge, true_f, ref in (("start", ta, start), ("end", tb, kick)):
                        if first:
                            count[(edge, name, bench_name)][0] += 1
                            if ref is not None:
                                count[(edge, name, bench_name)][1] += 1
                                truth[(edge, name, bench_name)].append((true_f - ref) / FPS)
                        for runs in hulls:
                            over = [(c, d) for c, d in runs if c < tb and d > ta]
                            if not over or sum(min(tb, d) - max(ta, c) for c, d in over) < 0.5 * (tb - ta):
                                continue
                            edge_f = min(c for c, _ in over) if edge == "start" else max(d for _, d in over)
                            v2_truth[(edge, name, bench_name, speed)].append((edge_f - true_f) / FPS)
                            if ref is not None:
                                v2[(edge, name, bench_name, speed)].append((edge_f - ref) / FPS)
    q = lambda v: "{:+5.2f} [{:+5.2f}, {:+5.2f}]".format(*np.percentile(v, [50, 25, 75])) if v else "  n/a"
    print("DFL clock gap (median restart event - kick, s) per match and half:",
          ", ".join(f"{m}.{h + 1} {s:+.2f}" for m, h, s in gaps))
    print(f"IDSSE stops without a kind: {unknown[0]} with the events as they come, {unknown[1]} on the kicks' clock")
    refs = {"end": "the kick", "start": "the ball off the pitch or the infringement (none for the other kinds)"}
    for edge in ("end", "start"):
        print(f"\n{edge} of the stops against {refs[edge]}: s, median [25%, 75%], + = after it")
        for (e, name, bench_name), (total, with_ref) in sorted(count.items()):
            if e != edge or not with_ref:
                continue
            speeds = ("provider", "positions") if bench_name == "idsse" else ("positions",)
            print(f"  {name:12} {bench_name:7} {with_ref:3}/{total:<3} truth {q(truth[(e, name, bench_name)])}  v2 "
                  + "  ".join(f"({sp[:3]}) {q(v2[(e, name, bench_name, sp)])}" for sp in speeds)
                  + "   v2 - truth " + "  ".join(f"({sp[:3]}) {q(v2_truth[(e, name, bench_name, sp)])}"
                                                  for sp in speeds))
