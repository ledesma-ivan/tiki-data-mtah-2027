"""IDSSE as the second bench that decides versions, next to bench.py (ADR-011; first used for ADR-007).

Usage: python explore/idsse_bench.py [--compare A B] [--matches 1,...,7] [--seeds 5] [--seed-start 0]
           [--missing 0.45] [--dead-missing 0] [--gap 1.5] [--crowd 0] [--bootstrap 1000] [--speed provider|positions]
The options mean what they mean in bench.py; --matches counts the files in name order, from 1.
IDSSE (Bassek et al., Scientific Data 12, 195, 2025; CC BY 4.0): 7 Bundesliga matches with DFL tracking at
25 Hz, revision a715a38 in ../idsse-data, as for idsse_dead_labels.py. Open data only (AGENTS.md).

The truth is built the way the official one is (CHALLENGE.md: D "where the corrected tracking marks the ball
dead, and otherwise takes the team the tracking names as owning it"): D where BallStatus is 0, else the team
of BallPossession (1 home, 2 guest, checked against the nearest player), with no events and no parameters.
Each half is one game for bench.compare's paired bootstrap. The ball comes as is (DFL tracks it on every
frame, also while dead) and degraded with bench.degrade (by default 45% of live frames without it, 1.5 s
gaps), as on the Metrica bench, with seed 1000 * game + s. Speeds: the provider's (S, km/h), as possession.py reads the ATD's, or from the
positions, as the Metrica bench computes them. The first run parses each positions XML into a .npz next to it.
"""
import argparse
import glob
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bench  # noqa: E402
import possession  # noqa: E402
from open_tracking import derived_speed  # noqa: E402

pm = bench.pm
FPS = bench.FPS
FRAMESET = re.compile(r'<FrameSet GameSection="([^"]+)"[^>]* TeamId="([^"]+)" PersonId="([^"]+)"')
FRAME = re.compile(r'<Frame N="(\d+)" T="[^"]*" X="([^"]*)" Y="([^"]*)"(?: Z="[^"]*")? D="[^"]*" S="([^"]*)"')
POSSESSION = re.compile(r'BallPossession="(\d)"')
STATUS = re.compile(r'BallStatus="(\d)"')


def parse(positions):
    """Cache one match: per section, positions in metres, the provider's speed, ball, BallStatus, BallPossession.

    The DFL files put one element per line, so lines are matched with regexes instead of building a tree.
    """
    with open(positions.replace("DFL_04_03_positions_raw_observed", "DFL_02_01_matchinformation"),
              encoding="utf-8") as f:
        info = f.read()
    home = re.search(r'<Team TeamId="([^"]+)"[^>]* Role="home"', info).group(1)
    pitch = possession.pitch_dimensions([float(v) for v in re.search(r'PitchX="([\d.]+)" PitchY="([\d.]+)"', info).groups()])
    sets, key, rows, bad = {}, None, [], 0
    with open(positions, encoding="utf-8") as f:
        for line in f:
            s = line.lstrip()
            if s.startswith("<Frame "):
                m = FRAME.match(s)
                if not m:
                    bad += 1
                    continue
                if key[1] == "BALL":
                    p = POSSESSION.search(s)
                    rows.append(m.groups() + (p.group(1) if p else "0", STATUS.search(s).group(1)))
                else:
                    rows.append(m.groups())
            elif s.startswith("<FrameSet "):
                key, rows = FRAMESET.match(s).groups(), []
            elif s.startswith("</FrameSet>"):
                sets[key] = np.array(rows, float)
    assert bad == 0, f"{bad} frames did not match the expected attributes"
    out = {"pitch": np.array(pitch)}
    for section in sorted({k[0] for k in sets if k[1] == "BALL"}):
        b = sets[next(k for k in sets if k[0] == section and k[1] == "BALL")]
        n0, n = int(b[0, 0]), len(b)
        assert (np.diff(b[:, 0]) == 1).all(), "ball frames are not contiguous"
        people = sorted(k for k in sets if k[0] == section and k[1] not in ("BALL", "referee"))
        assert len({k[1] for k in people}) == 2, {k[1] for k in people}
        xy, speed = np.full((n, len(people), 2), np.nan), np.full((n, len(people)), np.nan)
        for j, k in enumerate(people):
            a = sets[k]
            i = a[:, 0].astype(int) - n0
            ok = (i >= 0) & (i < n)
            xy[i[ok], j], speed[i[ok], j] = a[ok, 1:3], a[ok, 3]
        out.update({section + "_xy": xy, section + "_speed": speed, section + "_ball": b[:, 1:3],
                    section + "_team": np.array(["H" if k[1] == home else "A" for k in people]),
                    section + "_owner": b[:, 4].astype(np.int8), section + "_status": b[:, 5].astype(np.int8)})
    np.savez_compressed(positions + ".npz", **out)


def load(positions, speed_source):
    """[(section, players, ball, team, truth, position_speed, pitch)]: x/y 0-1, speed m/s, pitch metres."""
    if not os.path.exists(positions + ".npz"):
        parse(positions)
    z = np.load(positions + ".npz")
    pitch = possession.pitch_dimensions(z["pitch"])
    length, width = pitch
    norm = lambda a: np.stack([(a[..., 0] + length / 2) / length, (a[..., 1] + width / 2) / width], axis=-1)
    out = []
    for section in sorted({k.rsplit("_", 1)[0] for k in z.files if k != "pitch"}):
        xy = z[section + "_xy"]
        # parse() keys columns by (GameSection, TeamId, PersonId), one player per
        # column; each section is independent, and omitted frames stay NaN.
        from_positions = derived_speed(xy, np.arange(xy.shape[1]).astype(str),
                                       np.full(len(xy), section), np.arange(len(xy)), fps=FPS)
        speed = z[section + "_speed"] / 3.6 if speed_source == "provider" else from_positions  # S is km/h
        status, owner = z[section + "_status"], z[section + "_owner"]
        truth = np.where(status == 0, "D", np.where(owner == 1, "H", np.where(owner == 2, "A", "X"))).astype(object)
        out.append((section, np.concatenate([norm(xy), speed[..., None]], axis=2), norm(z[section + "_ball"]),
                    z[section + "_team"], truth, from_positions, pitch))
    z.close()
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dir", default=os.path.join(bench.ROOT, "..", "idsse-data"))
    ap.add_argument("--matches", default="1,2,3,4,5,6,7", help="files in name order, from 1 (ADR-011 partitions)")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--seed-start", type=int, default=0, help="first seed index; use a fresh block for confirmation")
    ap.add_argument("--missing", type=float, default=0.45,
                    help="target share of live frames without ball, counting the ones already missing")
    ap.add_argument("--dead-missing", type=float, default=0.0, help="target share of dead frames without ball")
    ap.add_argument("--gap", type=float, default=1.5, help="mean ball gap in seconds")
    ap.add_argument("--crowd", type=float, default=0.0, help="extra gap rate when the ball is crowded")
    ap.add_argument("--bootstrap", type=int, default=1000)
    ap.add_argument("--speed", choices=("provider", "positions"), default="provider")
    ap.add_argument("--compare", nargs=2, metavar=("A", "B"), default=("v1", "v2"),
                    help="pipelines of bench.PIPELINES; paired bootstrap of B - A (ADR-006, ADR-011)")
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(a.dir, "DFL_04_03_positions_raw_observed_*.xml")))
    matches = [int(m) for m in a.matches.split(",")]
    preds, scores = {}, {}
    for m in matches:
        for h, (section, players, ball, team, truth, from_positions, pitch) in enumerate(load(files[m - 1], a.speed)):
            g = 10 * m + h
            live, dead, graded = (truth == "H") | (truth == "A"), truth == "D", truth != "X"
            ev = bench.owner_evidence(players, ball, team, pitch=pitch)
            moving = from_positions > 2
            ratio = np.nanmedian(players[:, :, 2][moving] / from_positions[moving])
            print(f"game {g} ({os.path.basename(files[m - 1])[-10:-4]} {section}): {len(truth)} frames, "
                  f"D {dead.mean():.1%}, nearest player = BallPossession on {(ev[live] == truth[live]).mean():.1%} "
                  f"of live frames, speed / position speed {ratio:.2f}", flush=True)
            spans = pm.valid_runs(pm.label_codes(truth))
            balls = {"as is": [ball], "degraded": [bench.degrade(ball, players, dead, a.missing, a.gap, a.crowd,
                                                                 1000 * g + s, graded, a.dead_missing, pitch=pitch)
                                                   for s in range(a.seed_start, a.seed_start + a.seeds)]}
            for ball_name, variants in balls.items():
                for name in a.compare:
                    out = [bench.PIPELINES[name](players, b, team, spans, dead, pitch=pitch) for b in variants]
                    preds[(g, "status", ball_name, name)] = (truth, out)
                    for p, b in zip(out, variants):  # official metrics, then D against BallStatus with its edge offsets
                        miss = (np.isnan(b[live, 0]).mean(), np.isnan(b[dead & graded, 0]).mean())
                        scores.setdefault((ball_name, name), []).append(
                            {**bench.score(truth, p, 0, *miss), **bench.calibrate_dead.score(p == "D", dead, graded)})
    print(f"\nmean over {len(matches)} matches x 2 halves (matches {a.matches}, seeds {a.seed_start}-"
          f"{a.seed_start + a.seeds - 1}, speed: {a.speed})")
    for (ball_name, name), sc in sorted(scores.items()):
        print(f"  {ball_name:8} {name:13} spellF1 {np.mean([s['spell'] for s in sc]):.3f}  "
              f"miss {np.mean([s['missing'] for s in sc]):.0%}  D miss {np.mean([s['dead_missing'] for s in sc]):.0%}  "
              f"F1 of D {np.mean([s['dead_f1'] for s in sc]):.3f}  edges against BallStatus (median per half, + = late) "
              f"{np.nanmean([s['start_s'] for s in sc]):+.2f} / {np.nanmean([s['end_s'] for s in sc]):+.2f} s")
    print(f"\npaired spellF1 difference, {a.compare[1]} - {a.compare[0]} (mean over halves and seeds; "
          f"only the degraded ball decides, ADR-011)")
    for (anchor, ball_name), (point, lo, hi, per_game) in bench.compare(preds, *a.compare, a.bootstrap).items():
        verdict = "B better" if lo > 0 else "A better" if hi < 0 else "inside the noise"
        print(f"  {ball_name:8} {point:+.3f} [{lo:+.3f}, {hi:+.3f}]  halves above 0: "
              f"{sum(d > 0 for d in per_game.values())}/{len(per_game)}  -> {verdict}")
