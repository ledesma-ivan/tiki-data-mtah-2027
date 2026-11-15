"""Open-data bench: the full pipeline on Metrica sample-data, scored with the official scorer (ADR-006).

Usage: python bench.py [--games 1,2,3] [--seeds 10] [--seed-start 0] [--missing 0.45]
                       [--dead-missing 0] [--gap 1.5] [--crowd 0]
                       [--truth start,end] [--truth-variant A|B] [--bootstrap 1000]
Data: data/Sample_Game_{1,2,3} (metrica-sports/sample-data, cite it in the doc).
Scorer: $MTAH_OFFICIAL/evaluation/possession_metrics.py, default ../mtah2027 (the official repo).

Open data only (AGENTS.md). Never run on BAR-ATH: that is what possession.py is for.
"""
import argparse
import functools
import json
import os
import re
import sys

import numpy as np
import pandas as pd

import possession
from open_tracking import SPEED_VERSION, cache_matches, derived_speed, frame_numbers, source_signature

_argv, sys.argv = sys.argv, sys.argv[:1]  # calibrate_dead reads sys.argv[1] at import
import calibrate_dead  # noqa: E402
sys.argv = _argv

ROOT = os.path.dirname(os.path.abspath(__file__))
OFFICIAL = os.environ.get("MTAH_OFFICIAL", os.path.join(ROOT, "..", "mtah2027"))
sys.path.insert(0, os.path.join(OFFICIAL, "evaluation"))
import possession_metrics as pm  # noqa: E402  the official scorer: reuse it, never re-implement it

FPS = 25
PITCH = (105.0, 68.0)  # sample-data metadata
ON_BALL = {"PASS", "CARRY", "SHOT", "RECOVERY", "SET PIECE"}  # ADR-005


# -- open data ---------------------------------------------------------------------------------

def load_game(g):
    """(players[n,k,3], ball[n,2], team[k], events, pitch), indexed by frame - 1.

    events: [(type, subtype, start, end, period, team)] sorted by start, frames 0-based, several
    subtypes joined with "+", team "H" / "A" / "". pitch: (length, width) in metres (ADR-012).
    """
    if g == 3:
        players, ball, pitch = calibrate_dead.load_game3()
        team = np.array(["H"] * 11 + ["A"] * 11)  # slots keep their team through substitutions
        with open(calibrate_dead.PREFIX + "events.json") as f:
            raw = json.load(f)["data"]
        events = []
        for e in raw:
            s = e["subtypes"] or []
            s = [s] if isinstance(s, dict) else s
            side = {"FIFATMA": "H", "FIFATMB": "A"}.get((e.get("team") or {}).get("id"), "")
            events.append((e["type"]["name"], "+".join(x["name"] for x in s),
                           e["start"]["frame"] - 1, e["end"]["frame"] - 1, e["period"], side))
        return players, ball, team, sorted(events, key=lambda e: e[2]), pitch
    if g not in (1, 2):
        raise ValueError("supported Metrica games: 1, 2, 3")
    pitch = possession.pitch_dimensions(PITCH)
    prefix = os.path.join(ROOT, "data", f"Sample_Game_{g}", f"Sample_Game_{g}_")
    cache = prefix + "tracking.npz"
    sources = source_signature([f"{prefix}RawTrackingData_{side}_Team.csv" for side in ("Home", "Away")])
    cached = False
    if os.path.exists(cache):
        with np.load(cache) as z:
            if cache_matches(z, pitch, sources):
                players, ball, team = z["players"], z["ball"], z["team"]
                cached = True
    if not cached:
        xy, speeds, team = [], [], []
        clock = None
        for side, label in (("Home", "H"), ("Away", "A")):
            t = pd.read_csv(f"{prefix}RawTrackingData_{side}_Team.csv", skiprows=2)
            if tuple(t.columns[:2]) != ("Period", "Frame"):
                raise ValueError("tracking CSV must start with Period,Frame columns")
            frames = frame_numbers(t["Frame"])
            periods = t["Period"].fillna("").astype(str).to_numpy()
            if clock is not None and (not np.array_equal(frames, clock[0])
                                      or not np.array_equal(periods, clock[1])):
                raise ValueError("team tracking clocks do not match")
            clock = frames, periods
            a = t.iloc[:, 3:].to_numpy(float)  # player x, y pairs, then the ball
            positions = a[:, :-2].reshape(len(a), -1, 2)
            # Player columns are roster identities, not reusable positional slots.
            identities = [label + "/" + col if re.fullmatch(r"Player\d+", col) else ""
                          for col in t.columns[3:-2:2]]
            dense = np.full((frames[-1], positions.shape[1], 2), np.nan)
            dense[frames - 1] = positions
            xy.append(dense)
            speed = derived_speed(positions, identities, periods, frames, scale=pitch, fps=FPS)
            dense_speed = np.full(dense.shape[:2], np.nan)
            dense_speed[frames - 1] = speed
            speeds.append(dense_speed)
            team += [label] * xy[-1].shape[1]
            ball = np.full((frames[-1], 2), np.nan)
            ball[frames - 1] = a[:, -2:]
        xy = np.concatenate(xy, axis=1)
        speed = np.concatenate(speeds, axis=1)
        players, team = np.concatenate([xy, speed[..., None]], axis=2), np.array(team)
        np.savez_compressed(cache, players=players, ball=ball, team=team, pitch=pitch,
                            speed_version=SPEED_VERSION, sources=sources)
    return players, ball, team, load_csv_events(prefix + "RawEventsData.csv"), pitch


def load_csv_events(path):
    """Games 1 and 2 events in the common format; their subtypes use "-" where Game 3's use "+"."""
    e = pd.read_csv(path)
    events = [(typ, "" if pd.isna(sub) else sub.replace("-", "+"), int(s) - 1, int(end) - 1, int(per),
               {"Home": "H", "Away": "A"}.get(side, ""))
              for typ, sub, s, end, per, side in zip(e["Type"], e["Subtype"], e["Start Frame"], e["End Frame"],
                                                     e["Period"], e["Team"])]
    return sorted(events, key=lambda e: e[2])


# -- truth -------------------------------------------------------------------------------------

def truth_labels(events, n, dead, anchor="start", variant="A"):
    """H/A/D/X per frame from the events (ADR-005), cut by dead (ADR-003).

    The possession is the team of the last on-ball event, from that event's start (anchor="start")
    or end (anchor="end", sensitivity variant) until the next one. A restart (ADR-003: SET PIECE or
    a GOAL KICK subtype, even when typed BALL LOST) hands the ball to its team at its start, with
    either anchor: play restarts with a clear possessor (CHALLENGE.md). Before a period's first
    on-ball event and outside the periods: X (not graded).

    A (default) follows every on-ball event. B confirms a rival only after two consecutive
    on-ball events with different START frames, even with the end anchor. Same-frame events
    do not confirm or move the first candidate. The change is backdated to the first event's
    anchor; an event by the holder cancels it. Dead intervals, restarts and periods clear the
    pending candidate. Restarts assign their team immediately, without confirmation.
    With the end anchor, an event crossing a dead interval cannot confirm a new live spell.
    """
    if anchor not in ("start", "end"):
        raise ValueError("anchor must be 'start' or 'end'")
    if variant not in ("A", "B"):
        raise ValueError("variant must be 'A' or 'B'")
    labels = np.full(n, "X", dtype=object)
    restart = lambda e: e[0] == "SET PIECE" or "GOAL KICK" in e[1]
    # some events end before they start (kick-offs in Games 1 and 2: end frame 0)
    at = lambda e: e[2] if anchor == "start" or restart(e) else max(e[2], e[3])
    for period in sorted({e[4] for e in events}):
        last = max(e[3] for e in events if e[4] == period)
        on = sorted((e for e in events if e[4] == period and (e[0] in ON_BALL or restart(e)) and e[5]), key=at)
        owner, pending, previous = None, None, None
        for i, e in enumerate(on):
            frame = at(e)
            nxt = at(on[i + 1]) if i + 1 < len(on) else last + 1
            if variant == "A":
                labels[frame:nxt] = e[5]
                continue
            if previous is not None and dead[previous:frame + 1].any():
                pending = None
            if owner is None or restart(e):
                owner, pending = e[5], None
            elif not dead[e[2]:frame + 1].any():
                if e[5] == owner:
                    pending = None
                elif pending is None:
                    pending = (frame, e[2])
                elif e[2] != pending[1]:
                    labels[pending[0]:frame] = e[5]
                    owner, pending = e[5], None
            labels[frame:nxt] = owner
            previous = frame
    labels[dead & (labels != "X")] = "D"
    return labels


# -- ATD-like noise ----------------------------------------------------------------------------

def degrade(ball, players, dead, live_missing, mean_gap_s, crowd=0.0, seed=0, graded=None, dead_missing=0.0, *, pitch):
    """Ball track that looks like the automatic one: restored at stoppages, then bursty gaps.

    Sample-data drops the ball while it is dead (Game 3: missing on 99.8% of D frames, 2.0% of live
    ones), which the ATD does not do. So, first, D frames without a ball get one, interpolated
    between the nearest observations around them; real observations inside a stoppage are kept.
    Then live frames lose the ball in gaps with exponential lengths (mean mean_gap_s; overlapping
    gaps merge into longer ones) until, in expectation, live_missing of all live frames have no
    ball, counting the ones that already had none. If the input already misses more, no gap is
    added. crowd > 0 makes a gap start (1 + crowd) times likelier when 3+ players are within 3 m of
    the ball, as occlusions do. The same model then targets dead_missing of dead frames, counting
    missing observations after restoration; 0 keeps all restored D frames. graded (default: every
    frame) marks the frames inside the periods: neither target counts halftime or before kick-off.
    pitch must be the geometry used to normalise this game's positions, in metres (ADR-012).
    """
    pitch = possession.pitch_dimensions(pitch)
    rng = np.random.default_rng(seed)
    n = len(ball)
    out = ball.astype(float).copy()
    seen = ~np.isnan(out[:, 0])
    if seen.any():
        t = np.arange(n)
        for c in range(2):
            filled = np.interp(t, t[seen], out[seen, c])
            out[dead & ~seen, c] = filled[dead & ~seen]
    live = ~dead if graded is None else graded & ~dead
    weight = np.ones(n)
    if crowd:
        d = np.hypot((players[:, :, 0] - out[:, None, 0]) * pitch[0], (players[:, :, 1] - out[:, None, 1]) * pitch[1])
        weight += crowd * (np.sum(d < 3, axis=1) >= 3)
    length = mean_gap_s * FPS
    # Poisson starts at rate r with exponential lengths L cover 1 - exp(-r L) of the frames, overlaps
    # included: r = -ln(1 - p) / L hits the target p in expectation (crowd weighting: approximately).
    dead_graded = dead if graded is None else graded & dead
    for mask, target in ((live, live_missing), (dead_graded, dead_missing)):
        if not mask.any():
            continue
        already = np.isnan(out[mask, 0]).mean()
        extra = max(0.0, (target - already) / (1 - already)) if already < 1 else 0.0
        if extra >= 1:
            out[mask] = np.nan
            continue
        rate = -np.log1p(-extra) / (length * weight[mask].mean()) if extra > 0 else 0.0
        gaps = np.zeros(n, bool)
        starts = np.flatnonzero(rng.random(n) < rate * weight)
        for s, ln in zip(starts, rng.exponential(length, len(starts)).astype(int) + 1):
            gaps[s:s + ln] = True
        out[gaps & mask] = np.nan
    return out


# -- pipelines ---------------------------------------------------------------------------------

BASE_N, BASE_GAP = 2 * FPS, FPS // 2  # the change rule of v1, frozen: the baseline does not move when possession.py does


def segment(dead, evidence, spans, n_frames=BASE_N, max_gap=BASE_GAP, initial=None):
    """possession.label's last two steps for any game: D cuts, then the change rule (ADR-001).

    initial: per frame, "" or the team that restarts play there (ADR-010, #34); each live stretch reads
    it on its first frame.
    """
    labels = np.full(len(dead), "X", dtype=object)
    for a, b in spans:
        labels[a:b] = np.where(dead[a:b], "D", "X")
        for s, e in possession.runs(~dead[a:b]):
            labels[a + s:a + e] = possession.confirm_changes(evidence[a + s:a + e], n_frames, max_gap,
                                                             None if initial is None else initial[a + s])
    return labels


def owner_evidence(players, ball, team, radius=np.inf, max_interp=None, *, pitch):
    """Bench entry point: omitting the game's geometry is an error (ADR-012)."""
    return possession.owner_evidence(players, ball, team, radius, max_interp, pitch=pitch)


def pipeline_v1(players, ball, team, spans, dead_true, *, pitch):
    """possession.py before ADR-009: the nearest player as evidence, N = 2 s, max_gap = 0.48 s (frozen)."""
    return segment(possession.dead_mask(players, ball), owner_evidence(players, ball, team, pitch=pitch), spans)


def pipeline_v2(players, ball, team, spans, dead_true, *, pitch):
    """ADR-007 detector (dead_mask_v2) with the frozen v1 evidence and change rule: the baseline before ADR-009."""
    return segment(possession.dead_mask_v2(players, ball), owner_evidence(players, ball, team, pitch=pitch), spans)


def oracle_dead(players, ball, team, spans, dead_true, *, pitch):
    """Diagnostic: the frozen v1 evidence and change rule with the true D. Isolates the evidence."""
    return segment(dead_true, owner_evidence(players, ball, team, pitch=pitch), spans)


def radio_evidence(players, ball, team, *, pitch):
    return owner_evidence(players, ball, team, possession.CONTROL_RADIUS, possession.MAX_INTERP, pitch=pitch)


def pipeline_radio(players, ball, team, spans, dead_true, *, pitch):
    """possession.py since ADR-009: dead_mask_v2, control radius, bounded interpolation, N and max_gap together."""
    return segment(possession.dead_mask_v2(players, ball), radio_evidence(players, ball, team, pitch=pitch), spans,
                   possession.CHANGE_FRAMES, possession.MAX_GAP)


def oracle_radio(players, ball, team, spans, dead_true, *, pitch):
    """Diagnostic: the ADR-009 evidence and change rule with the true D."""
    return segment(dead_true, radio_evidence(players, ball, team, pitch=pitch), spans, possession.CHANGE_FRAMES, possession.MAX_GAP)


@functools.lru_cache(maxsize=1)
def stops_model():
    return possession.load_model()


def pipeline_stops(players, ball, team, spans, dead_true, *, pitch):
    """possession.py since ADR-010: the radio pipeline with the v2 stops' edges moved and the restart team.

    stops_model.json is trained on the 10 open matches, so on this bench it scores games it has seen: the
    ADR-010 decision comes from calibrate_edges.py's selection and reserve, not from here.
    """
    dead, initial = possession.refine(possession.dead_mask_v2(players, ball), players, ball, team, spans, stops_model(),
                                      pitch=pitch)
    return segment(dead, radio_evidence(players, ball, team, pitch=pitch), spans, possession.CHANGE_FRAMES, possession.MAX_GAP,
                   initial)


@functools.lru_cache(maxsize=1)
def live_model():
    return possession.load_live_model()


def pipeline_live(players, ball, team, spans, dead_true, *, pitch):
    """possession.py since ADR-014: the stops pipeline with decode_live on the delivered live model in each live
    stretch, or the stops pipeline itself while live_model.json is the rule. A delivered model is trained on the 10
    open matches, so here it scores games it has seen: the ADR-014 decision comes from calibrate_live.py."""
    live = live_model()
    if live["mode"] != "model":
        return pipeline_stops(players, ball, team, spans, dead_true, pitch=pitch)
    dead, _ = possession.refine(possession.dead_mask_v2(players, ball), players, ball, team, spans, stops_model(),
                                pitch=pitch)
    score = possession.live_score(players, ball, team, radio_evidence(players, ball, team, pitch=pitch), dead, spans,
                                  live["trees"], pitch)
    return possession.segment_live(dead, score, spans, live["switch"])


PIPELINES = {"v1": pipeline_v1, "v2": pipeline_v2, "v1, true D": oracle_dead, "radio": pipeline_radio,
             "radio, true D": oracle_radio, "stops": pipeline_stops, "live": pipeline_live}


# -- scoring -----------------------------------------------------------------------------------

def score(truth, pred, n_boot, live_missing=None, dead_missing=None):
    """Official metrics via possession_metrics.evaluate (X filled as the scorer does), D frame F1."""
    gt, pr = pm.label_codes(truth), pm.label_codes(pred)
    r = pm.evaluate(gt, pr, bootstrap_n=n_boot)
    d = calibrate_dead.score(pr == pm.D, gt == pm.D, gt != pm.X)
    return {"spell": r["spell_f1_mean"], "lo": r["spell_bootstrap_low"], "hi": r["spell_bootstrap_high"],
            "n_gt": r["n_gt_spells"], "n_pred": r["n_pred_spells"], "macro": r["macro_f1"], "dead_f1": d["F1"],
            "missing": live_missing, "dead_missing": dead_missing}


def spell_draws(gt, pred, picks):
    """spellF1 of pred under each row of picks (indices into the true possessions), [n_draws].

    The official bootstrap (possession_metrics.bootstrap_spell_f1) with the resampling exposed, so
    two predictions can be scored on the SAME draws: a paired bootstrap of their difference, which
    the official one does not offer. Built only from the scorer's own pieces; with
    picks = RandomState(seed).randint(0, n_gt, (n_draws, n_gt)) it gives exactly its draws.
    """
    spans = pm.valid_runs(gt)
    filled = pm.fill_abstentions(pred, spans)
    gt_spells, pred_spells = pm.possession_spells(gt, spans), pm.possession_spells(filled, spans)
    overlaps = pm.spell_overlaps(gt_spells, pred_spells)
    n_gt, n_pred = len(gt_spells), len(pred_spells)
    flags = np.vstack([pm.matched_gt_flags(overlaps, n_gt, t) for t in pm.SPELL_IOUS])
    tp = flags[:, picks].sum(axis=2)  # [threshold, draw]
    fp = np.maximum(0, n_pred - tp)
    f1 = np.where(tp > 0, 2.0 * tp / np.maximum(1, 2 * tp + fp + (n_gt - tp)), 0.0)
    return f1.mean(axis=0)


def run(games, seeds, live_missing, mean_gap_s, crowd, anchors, n_boot, seed_start=0, dead_missing=0.0,
        truth_variant="A"):
    """Scores and compare() inputs for ONE truth definition (A by default, B for sensitivity).

    Row/prediction keys stay (game, anchor, ball, pipeline). Run A and B separately; never merge
    their prediction dictionaries. Scores carry truth_variant so report() identifies each run.
    """
    if truth_variant not in ("A", "B"):
        raise ValueError("truth_variant must be 'A' or 'B'")
    rows, preds = [], {}
    for g in games:
        players, ball, team, events, pitch = load_game(g)
        n = len(ball)
        dead = calibrate_dead.dead_labels([e[:5] for e in events], n)
        graded = np.zeros(n, bool)
        for first, last in calibrate_dead.halves([e[:5] for e in events]):
            graded[first:last + 1] = True
        balls = [("as is", [ball])]
        if seeds:
            balls.append(("degraded", [degrade(ball, players, dead, live_missing, mean_gap_s, crowd, 1000 * g + s,
                                               graded, dead_missing, pitch=pitch) for s in range(seed_start, seed_start + seeds)]))
        for anchor in anchors:
            truth = truth_labels(events, n, dead, anchor, variant=truth_variant)
            spans = pm.valid_runs(pm.label_codes(truth))
            live = (truth == "H") | (truth == "A")
            dead_graded = graded & dead
            for ball_name, variants in balls:
                for name, fn in PIPELINES.items():
                    out = [fn(players, b, team, spans, dead, pitch=pitch) for b in variants]
                    key = (g, anchor, ball_name, name)
                    preds[key] = (truth, out)
                    rows.append((key, [{**score(truth, p, n_boot if i == 0 else 0, np.isnan(b[live, 0]).mean(),
                                               np.isnan(b[dead_graded, 0]).mean() if dead_graded.any() else 0.0),
                                        "truth_variant": truth_variant}
                                       for i, (p, b) in enumerate(zip(out, variants))]))
    return rows, preds


def compare(preds, a, b, n_draws, seed=pm.BOOTSTRAP_SEED):
    """Paired bootstrap of spellF1(b) - spellF1(a) (ADR-006).

    Per game, every draw resamples the true possessions once and scores both pipelines, and every
    seed of the degraded ball, on it. It also resamples n_seeds seeds with replacement per draw,
    shared by A and B. Average those differences over sampled seeds, then over the selected games
    (games are not resampled). The interval carries possession and simulated-ball noise.
    Returns {(anchor, ball): (point, lo, hi, {game: point})}.
    """
    out = {}
    for anchor, ball in sorted({(k[1], k[2]) for k in preds}):
        per_game, pooled = {}, []
        for g in sorted({k[0] for k in preds if k[1:3] == (anchor, ball)}):
            truth, pa = preds[(g, anchor, ball, a)]
            _, pb = preds[(g, anchor, ball, b)]
            gt = pm.label_codes(truth)
            n_gt = len(pm.possession_spells(gt, pm.valid_runs(gt)))
            rng = np.random.RandomState(seed + g)
            picks = rng.randint(0, n_gt, (n_draws, n_gt))
            seed_picks = rng.randint(0, len(pa), (n_draws, len(pa)))
            point = np.arange(n_gt)[None]
            diffs = [spell_draws(gt, pm.label_codes(y), picks) - spell_draws(gt, pm.label_codes(x), picks)
                     for x, y in zip(pa, pb, strict=True)]  # a seed missing on one side must not pair silently
            per_game[g] = float(np.mean([spell_draws(gt, pm.label_codes(y), point)[0] -
                                         spell_draws(gt, pm.label_codes(x), point)[0] for x, y in zip(pa, pb, strict=True)]))
            pooled.append(np.take_along_axis(np.array(diffs).T, seed_picks, axis=1).mean(axis=1))
        pooled = np.mean(pooled, axis=0)
        lo, hi = np.percentile(pooled, pm.BOOTSTRAP_PERCENTILES)
        out[(anchor, ball)] = (float(np.mean(list(per_game.values()))), float(lo), float(hi), per_game)
    return out


def report(rows):
    """One line per row: first seed with its bootstrap, then the mean and range over seeds."""
    variants = {s.get("truth_variant", "A") for _, scores in rows for s in scores}
    if len(variants) > 1:
        raise ValueError("report A and B separately; their scores use different reference labels")
    if variants:
        print(f"possession truth variant: {next(iter(variants))} (ADR-005)")
    print(f"{'game':>4} {'truth':5} {'ball':8} {'pipeline':11} {'miss':>4} {'D miss':>6} {'spellF1':>7} {'5-95% boot':>14}"
          f" {'seeds mean (min-max)':>21} {'macroF1':>7} {'pred/gt':>9} {'D F1':>5}")
    for (g, anchor, ball, name), scores in rows:
        sp = np.array([s["spell"] for s in scores])
        first = scores[0]
        boot = f"[{first['lo']:.3f}, {first['hi']:.3f}]" if first["lo"] is not None else ""
        seeds = f"{sp.mean():.3f} ({sp.min():.3f}-{sp.max():.3f})" if len(sp) > 1 else ""
        miss = np.mean([s["missing"] for s in scores])
        dead_miss = np.mean([s["dead_missing"] for s in scores])
        print(f"{g:>4} {anchor:5} {ball:8} {name:11} {miss:4.0%} {dead_miss:6.0%} {first['spell']:7.3f} {boot:>14} {seeds:>21}"
              f" {first['macro']:7.3f} {first['n_pred']:4}/{first['n_gt']:<4} {first['dead_f1']:5.3f}")
    print("\nmean over games of the mean over seeds (spellF1)")
    for k in sorted({r[0][1:] for r in rows}):
        vals = [np.mean([s["spell"] for s in sc]) for key, sc in rows if key[1:] == k]
        print(f"  {k[0]:5} {k[1]:8} {k[2]:11} {np.mean(vals):.3f}  ({len(vals)} games)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--games", default="1,2,3")
    ap.add_argument("--seeds", type=int, default=10, help="degraded-ball seeds per game; 0 = as is only")
    ap.add_argument("--seed-start", type=int, default=0, help="first seed index; use a fresh block for confirmation")
    ap.add_argument("--missing", type=float, default=0.45,
                    help="target share of live frames without ball, counting the ones already missing")
    ap.add_argument("--dead-missing", type=float, default=0.0,
                    help="target share of dead frames without ball, counted after restoration")
    ap.add_argument("--gap", type=float, default=1.5, help="mean ball gap in seconds")
    ap.add_argument("--crowd", type=float, default=0.0, help="extra gap rate when the ball is crowded")
    ap.add_argument("--truth", default="start,end", help="possession truth anchors (ADR-005 and variant)")
    ap.add_argument("--truth-variant", choices=("A", "B"), default="A",
                    help="A: last on-ball event; B: two rival events in distinct frames (ADR-005)")
    ap.add_argument("--bootstrap", type=int, default=1000)
    ap.add_argument("--compare", nargs=2, metavar=("A", "B"), help="paired bootstrap of B - A (ADR-006)")
    a = ap.parse_args(argv)
    anchors = a.truth.split(",")
    if not anchors or any(anchor not in ("start", "end") for anchor in anchors):
        ap.error("--truth must contain start and/or end, separated by commas")
    rows, preds = run([int(g) for g in a.games.split(",")], a.seeds, a.missing, a.gap, a.crowd,
                      anchors, a.bootstrap, a.seed_start, a.dead_missing, truth_variant=a.truth_variant)
    report(rows)
    if a.compare:
        print(f"\npaired spellF1 difference, {a.compare[1]} - {a.compare[0]} (mean over games and seeds)")
        for (anchor, ball), (point, lo, hi, per_game) in compare(preds, *a.compare, max(a.bootstrap, 1)).items():
            games = "  ".join(f"g{g} {d:+.3f}" for g, d in per_game.items())
            verdict = "B better" if lo > 0 else "A better" if hi < 0 else "inside the noise"
            print(f"  {anchor:5} {ball:8} {point:+.3f} [{lo:+.3f}, {hi:+.3f}]  {games}  -> {verdict}")


if __name__ == "__main__":
    main()
