"""Bench pieces on synthetic data (ADR-006): truth, ATD-like noise, segmentation, CSV events.

Needs the official scorer next to the repo (../mtah2027, or $MTAH_OFFICIAL), like bench.py.
"""
import hashlib
import os
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import bench

# calibrate_live.py --final (30/10, after #53): the ADR-014 recipe on the 10 open matches, every row weighing 1; back from
# git after ADR-019 (#91). A new delivered model changes this line
DELIVERED_LIVE_SHA256 = "1f8b706e0c30e5e0d3e97d69285dd3bbc1ea1b270c8efaa64f6ddf8190b763c1"  # ADR-033


def ev(typ, start, end, team, period=1, sub=""):
    return (typ, sub, start, end, period, team)


class TruthTest(unittest.TestCase):
    EVENTS = [ev("PASS", 10, 20, "H"), ev("BALL LOST", 20, 22, "H"), ev("RECOVERY", 30, 31, "A"),
              ev("PASS", 31, 40, "A"), ev("CHALLENGE", 45, 46, "H"), ev("PASS", 50, 59, "A")]

    def test_start_anchor_holds_until_next_on_ball_event(self):
        labels = bench.truth_labels(self.EVENTS, 70, np.zeros(70, bool))
        self.assertEqual("".join(labels[:10]), "X" * 10)  # before the first on-ball event: not graded
        self.assertEqual("".join(labels[10:30]), "H" * 20)  # BALL LOST is not on-ball: H holds
        self.assertEqual("".join(labels[30:60]), "A" * 30)  # a CHALLENGE by H does not hand it over
        self.assertEqual("".join(labels[60:]), "X" * 10)  # after the period's last event

    def test_end_anchor_moves_the_hand_over_to_the_event_end(self):
        labels = bench.truth_labels(self.EVENTS, 70, np.zeros(70, bool), anchor="end")
        self.assertEqual("".join(labels[20:31]), "H" * 11)
        self.assertEqual(labels[31], "A")

    def test_dead_frames_become_d_but_ungraded_stay_x(self):
        dead = np.zeros(70, bool)
        dead[5:15] = dead[24:30] = True
        labels = bench.truth_labels(self.EVENTS, 70, dead)
        self.assertEqual("".join(labels[5:15]), "X" * 5 + "D" * 5)
        self.assertEqual("".join(labels[24:30]), "D" * 6)

    def test_end_anchor_never_goes_before_the_start(self):
        events = [ev("SET PIECE", 0, -1, "A"), ev("PASS", 5, 9, "H")]  # a kick-off with end frame 0
        labels = bench.truth_labels(events, 12, np.zeros(12, bool), anchor="end")
        self.assertEqual("".join(labels), "A" * 9 + "H" + "XX")  # the period ends at its last event end

    def test_a_lost_goal_kick_hands_the_ball_to_the_kicker_at_the_restart(self):
        # Metrica types a long goal kick that the rival wins as BALL LOST + GOAL KICK
        events = [ev("PASS", 0, 10, "H"), ev("BALL OUT", 10, 11, ""), ev("BALL LOST", 20, 30, "A", sub="GOAL KICK"),
                  ev("RECOVERY", 30, 31, "H"), ev("PASS", 31, 39, "H")]
        dead = np.zeros(40, bool)
        dead[11:20] = True
        for anchor in ("start", "end"):
            labels = bench.truth_labels(events, 40, dead, anchor)
            self.assertEqual("".join(labels[11:30]), "D" * 9 + "A" * 10, anchor)
            self.assertEqual(labels[-1], "H")

    def test_periods_are_independent(self):
        events = [ev("PASS", 0, 5, "H", 1), ev("PASS", 10, 15, "A", 2)]
        labels = bench.truth_labels(events, 20, np.zeros(20, bool))
        self.assertEqual("".join(labels), "H" * 6 + "XXXX" + "A" * 6 + "XXXX")


class DegradeTest(unittest.TestCase):
    N = 200_000

    def setUp(self):
        t = np.linspace(0, 1, self.N)
        self.ball = np.stack([t, 1 - t], axis=1)
        self.dead = np.zeros(self.N, bool)
        self.dead[50_000:60_000] = True
        self.ball[self.dead] = np.nan  # sample-data drops the ball while it is dead
        self.players = np.zeros((self.N, 2, 3))

    def test_dead_frames_get_the_ball_back_and_never_lose_it(self):
        out = bench.degrade(self.ball, self.players, self.dead, 0.45, 1.5, pitch=bench.PITCH)
        self.assertFalse(np.isnan(out[self.dead]).any())
        # interpolated between the last position before the stoppage and the first after it
        self.assertAlmostEqual(out[55_000, 0], (self.ball[49_999, 0] + self.ball[60_000, 0]) / 2, places=4)

    def test_live_missing_share_is_close_to_the_target(self):
        for target in (0.2, 0.45):
            out = bench.degrade(self.ball, self.players, self.dead, target, 1.5, pitch=bench.PITCH)
            self.assertAlmostEqual(np.isnan(out[~self.dead, 0]).mean(), target, delta=0.04)

    def test_gaps_are_bursts_of_the_expected_length(self):
        p, length = 0.3, 2.0
        out = bench.degrade(self.ball, self.players, self.dead, p, length, pitch=bench.PITCH)
        gaps = [(e - s) / bench.FPS for s, e in bench.possession.runs(np.isnan(out[:, 0]))]
        # overlapping gaps merge: a busy period of Poisson-started exponential gaps lasts L (e^rL - 1) / rL
        rl = -np.log1p(-p)
        self.assertAlmostEqual(np.mean(gaps), length * np.expm1(rl) / rl, delta=0.3)

    def test_same_seed_same_ball_other_seed_other_ball(self):
        a = bench.degrade(self.ball, self.players, self.dead, 0.45, 1.5, seed=7, pitch=bench.PITCH)
        b = bench.degrade(self.ball, self.players, self.dead, 0.45, 1.5, seed=7, pitch=bench.PITCH)
        c = bench.degrade(self.ball, self.players, self.dead, 0.45, 1.5, seed=8, pitch=bench.PITCH)
        np.testing.assert_array_equal(a, b)
        self.assertFalse(np.array_equal(np.isnan(a), np.isnan(c)))

    def test_target_counts_the_ball_already_missing(self):
        ball = self.ball.copy()
        live = np.flatnonzero(~self.dead)
        ball[live[::2]] = np.nan  # half of the live frames already have no ball
        low = bench.degrade(ball, self.players, self.dead, 0.2, 1.5, pitch=bench.PITCH)
        self.assertAlmostEqual(np.isnan(low[~self.dead, 0]).mean(), 0.5, delta=0.01)  # nothing added
        high = bench.degrade(ball, self.players, self.dead, 0.7, 1.5, pitch=bench.PITCH)
        self.assertAlmostEqual(np.isnan(high[~self.dead, 0]).mean(), 0.7, delta=0.04)

    def test_frames_outside_the_periods_do_not_count(self):
        graded = np.ones(self.N, bool)
        graded[:40_000] = False
        ball = self.ball.copy()
        ball[:40_000] = np.nan  # before kick-off: no ball, and no truth either
        out = bench.degrade(ball, self.players, self.dead, 0.3, 1.5, graded=graded, pitch=bench.PITCH)
        self.assertAlmostEqual(np.isnan(out[graded & ~self.dead, 0]).mean(), 0.3, delta=0.04)

    def test_observations_inside_a_stoppage_are_kept(self):
        ball = np.array([[0, 0], [np.nan, np.nan], [0.9, 0.9], [np.nan, np.nan], [0, 0]])
        dead = np.array([False, True, True, True, False])
        out = bench.degrade(ball, np.zeros((5, 1, 3)), dead, 0.0, 1.5, pitch=bench.PITCH)
        np.testing.assert_allclose(out[:, 0], [0, 0.45, 0.9, 0.45, 0])

    def test_input_is_not_modified(self):
        before = self.ball.copy()
        bench.degrade(self.ball, self.players, self.dead, 0.45, 1.5, pitch=bench.PITCH)
        np.testing.assert_array_equal(before, self.ball)

    def test_dead_missing_targets_graded_frames_after_restoration(self):
        dead = self.dead.copy()
        dead[80_000:180_000] = True
        graded = np.ones(self.N, bool)
        graded[50_000:60_000] = False
        ball = self.ball.copy()
        ball[dead] = np.nan  # 100% missing before restoration, not an additional 34%
        out = bench.degrade(ball, self.players, dead, 0.45, 1.5, graded=graded, dead_missing=0.34, pitch=bench.PITCH)
        self.assertAlmostEqual(np.isnan(out[dead & graded, 0]).mean(), 0.34, delta=0.04)
        self.assertFalse(np.isnan(out[dead & ~graded]).any())
        self.assertAlmostEqual(np.isnan(out[~dead & graded, 0]).mean(), 0.45, delta=0.04)

    def test_zero_dead_missing_keeps_the_previous_ball_exactly(self):
        # Freeze the previous implementation's live-gap draws, not only the D-frame behaviour.
        rng = np.random.default_rng(7)
        rate = -np.log1p(-0.45) / (1.5 * bench.FPS)
        starts = np.flatnonzero(rng.random(self.N) < rate)
        gaps = np.zeros(self.N, bool)
        for s, ln in zip(starts, rng.exponential(1.5 * bench.FPS, len(starts)).astype(int) + 1):
            gaps[s:s + ln] = True
        expected = np.stack([np.linspace(0, 1, self.N), np.linspace(1, 0, self.N)], axis=1)
        expected[gaps & ~self.dead] = np.nan
        out = bench.degrade(self.ball, self.players, self.dead, 0.45, 1.5, seed=7, dead_missing=0, pitch=bench.PITCH)
        np.testing.assert_allclose(out, expected, rtol=0, atol=1e-15)


class RunTest(unittest.TestCase):
    def test_seed_start_uses_reproducible_fresh_balls_and_reports_dead_missing(self):
        n = 20_000
        ball = np.full((n, 2), 0.5)
        players = np.zeros((n, 2, 3))
        events = [ev("PASS", 0, 5_000, "H"), ev("BALL OUT", 5_000, 5_001, "H"),
                  ev("SET PIECE", 15_000, n - 1, "A")]
        balls = []

        def pipeline(players, ball, team, spans, dead, *, pitch):
            balls.append(ball.copy())
            return np.where(dead, "D", "H")

        with patch.object(bench, "load_game", return_value=(players, ball, np.array(["H", "A"]), events, bench.PITCH)), \
                patch.dict(bench.PIPELINES, {"test": pipeline}, clear=True):
            kwargs = dict(games=[1], seeds=1, live_missing=0.45, mean_gap_s=1.5, crowd=0,
                          anchors=["start"], n_boot=0, dead_missing=0.34)
            bench.run(**kwargs)
            default = balls[-1]
            rows, _ = bench.run(**kwargs, seed_start=10)
            fresh = balls[-1]
            bench.run(**kwargs, seed_start=10)
        np.testing.assert_array_equal(fresh, balls[-1])
        self.assertFalse(np.array_equal(np.isnan(default), np.isnan(fresh)))
        self.assertEqual(rows[-1][1][0]["dead_missing"], np.isnan(fresh[5_001:15_000, 0]).mean())


class SegmentTest(unittest.TestCase):
    def test_dead_cuts_and_change_rule_inside_live_stretches(self):
        n = bench.BASE_N  # segment's default rule is the frozen v1 one, not possession.py's current parameters
        evidence = np.array(["H"] * 100 + ["A"] * (n + 10) + ["H"] * 30, dtype=object)
        dead = np.zeros(len(evidence), bool)
        dead[40:60] = True
        labels = bench.segment(dead, evidence, [(10, len(evidence))])
        self.assertEqual("".join(labels[:10]), "X" * 10)  # outside the graded span
        self.assertEqual("".join(labels[40:60]), "D" * 20)
        self.assertEqual(labels[99], "H")
        self.assertEqual(labels[100], "A")  # backdated to the first frame of the run
        self.assertEqual(labels[-1], "A")  # 30 frames of H are shorter than the change rule

    def test_restart_team_starts_the_live_stretch_after_a_stop(self):
        evidence = np.array(["H"] * 40 + [""] * 20 + ["A"] * 5 + ["H"] * bench.BASE_N, dtype=object)
        dead = np.zeros(len(evidence), bool)
        dead[40:60] = True
        initial = np.full(len(evidence), "", dtype=object)
        initial[60] = "H"  # the restart team, read on the first live frame after the stop (ADR-010, #34)
        self.assertEqual(bench.segment(dead, evidence, [(0, len(evidence))])[60], "A")  # first evidence, as before
        labels = bench.segment(dead, evidence, [(0, len(evidence))], initial=initial)
        self.assertEqual("".join(labels[60:]), "H" * (5 + bench.BASE_N))  # 5 frames of A do not take it over


class StopsPipelineTest(unittest.TestCase):
    def test_stops_is_the_radio_pipeline_with_the_refined_stops_and_the_restart_team(self):
        n = 600
        players = np.zeros((n, 2, 3))
        players[:, 0, :2], players[:, 1, :2] = (0.5, 0.5), (0.4, 0.0)  # H in the middle, A on the sideline
        players[:, :, 2] = 3.0
        players[200:400, :, 2] = 0.5  # a stop for dead_mask_v2
        ball = np.full((n, 2), np.nan)
        ball[450:] = (0.5 + 0.5 / bench.PITCH[0], 0.5)
        team = np.array(["H", "A"])
        kinds = len(bench.possession.KINDS)
        model = {"mode": "planb", "window": 125, "team_radius_cm": 200, "lead": [10] + [0] * (kinds - 1),
                 "trim": [-5] + [0] * (kinds - 1), "type": [{"init": 1, "trees": []}] + [{"init": 0, "trees": []}] * (kinds - 1)}
        spans = [(0, n)]
        with patch.object(bench, "stops_model", lambda: model):
            got = bench.PIPELINES["stops"](players, ball, team, spans, None, pitch=bench.PITCH)
        p = bench.possession
        dead, initial = p.refine(p.dead_mask_v2(players, ball), players, ball, team, spans, model, bench.PITCH)
        want = bench.segment(dead, bench.radio_evidence(players, ball, team, pitch=bench.PITCH), spans, p.CHANGE_FRAMES, p.MAX_GAP, initial)
        self.assertEqual(list(got), list(want))
        self.assertIn("D", set(got))

    def test_the_delivered_model_changes_nothing_until_adr_010_confirms_one(self):
        """stops_model.json is the identity model (calibrate_edges.py --identity) until a candidate passes the
        reserve: the CSV of ADR-009, frame by frame. A confirmed model replaces this test with its numbers."""
        rng = np.random.default_rng(3)
        n = 3000
        players = np.zeros((n, 4, 3))
        players[:, :, :2] = rng.uniform(0.05, 0.95, (n, 4, 2))
        players[:, :, 2] = np.repeat(rng.uniform(0, 4, (n // 100, 4)), 100, axis=0)
        players[600:750, :, 2] = 0.5  # everybody slow for 6 s: a stop for dead_mask_v2
        ball = rng.uniform(0, 1, (n, 2))
        ball[rng.random(n) < 0.3] = np.nan
        team = np.array(["H", "H", "A", "A"])
        spans = [(0, 1400), (1600, n)]
        bench.stops_model.cache_clear()
        got = bench.PIPELINES["stops"](players, ball, team, spans, None, pitch=bench.PITCH)
        self.assertIn("D", set(got))  # a real stop, so moving its edges would show
        self.assertEqual(list(got), list(bench.pipeline_radio(players, ball, team, spans, None, pitch=bench.PITCH)))
        m = bench.stops_model()
        kinds = len(bench.possession.KINDS)
        self.assertEqual((m["mode"], m["team_radius_cm"], m["lead"], m["trim"]), ("planb", 0, [0] * kinds, [0] * kinds))

    def test_the_delivered_live_model_is_the_one_adr_014_confirmed(self):
        """live_model.json is the recipe that passed the reserve (63 leaves, lambda 10: 43 of 43 conditions, against radio
        with the training balls of ADR-033), trained on the 10 open matches by calibrate_live.py --final. Pinned by its
        content: core.autocrlf can change the
        file's bytes on a checkout, never the model."""
        import calibrate_live
        bench.live_model.cache_clear()
        m = bench.live_model()
        self.assertEqual((m["mode"], m["switch"], len(m["trees"]["trees"])), ("model", calibrate_live.switch_of(10), 300))
        self.assertEqual(hashlib.sha256(calibrate_live.to_json(m).encode()).hexdigest(), DELIVERED_LIVE_SHA256)

    def test_the_live_pipeline_decodes_with_a_model(self):
        n = 2000
        players = np.zeros((n, 4, 3))
        players[:, :2, :2], players[:, 2:, :2] = (0.3, 0.5), (0.7, 0.5)  # H on the left, A on the right
        players[:, :, 2] = 3.0
        ball = np.tile([0.3 + 0.5 / bench.PITCH[0], 0.5], (n, 1))
        ball[1000:] = (0.7 + 0.5 / bench.PITCH[0], 0.5)  # the ball goes from H to A halfway
        team = np.array(["H", "H", "A", "A"])
        spans = [(0, n)]
        p = bench.possession
        near = {"feature": np.array([p.LIVE_FEATURES.index("own_nearest"), -1, -1]), "threshold": np.array([100, 0, 0]),
                "left": np.array([1, 0, 0]), "right": np.array([2, 0, 0]), "value": np.array([0, 1_000_000, -1_000_000])}
        live = {"mode": "model", "switch": 10_000_000, "trees": {"init": 0, "trees": [near]}}
        with patch.object(bench, "live_model", lambda: live):
            got = bench.PIPELINES["live"](players, ball, team, spans, None, pitch=bench.PITCH)
        dead, _ = p.refine(p.dead_mask_v2(players, ball), players, ball, team, spans, bench.stops_model(), bench.PITCH)
        score = p.live_score(players, ball, team, bench.radio_evidence(players, ball, team, pitch=bench.PITCH), dead,
                             spans, live["trees"], bench.PITCH)
        self.assertEqual(list(got), list(p.segment_live(dead, score, spans, live["switch"])))
        self.assertEqual((got[500], got[1500]), ("H", "A"))


def spells_with_gaps(teams, length=100, gap=100):
    """Possessions of `length` frames separated by `gap` frames of D, as labels."""
    out = []
    for t in teams:
        out += [t] * length + ["D"] * gap
    return np.array(out, dtype=object)


class ScoringTest(unittest.TestCase):
    def test_score_matches_the_official_evaluation_with_abstentions(self):
        truth = np.array(["X"] * 5 + ["H"] * 100 + ["X"] * 5, dtype=object)
        pred = np.array(["X"] * 5 + ["H"] * 40 + ["X"] * 20 + ["H"] * 40 + ["X"] * 5, dtype=object)
        s = bench.score(truth, pred, 0)
        official = bench.pm.evaluate(bench.pm.label_codes(truth), bench.pm.label_codes(pred), bootstrap_n=0)
        self.assertEqual(s["spell"], official["spell_f1_mean"])
        self.assertEqual(s["spell"], 1.0)  # the scorer fills an abstention: one possession, not two
        self.assertEqual(s["n_pred"], 1)

    def test_spell_draws_reproduce_the_official_point_and_bootstrap(self):
        rng = np.random.default_rng(1)
        truth = spells_with_gaps(rng.choice(["H", "A"], 60))
        pred = truth.copy()
        pred[rng.random(len(pred)) < 0.004] = "A"  # a few one-frame flickers split some possessions
        gt, pr = bench.pm.label_codes(truth), bench.pm.label_codes(pred)
        spans = bench.pm.valid_runs(gt)
        n_gt = len(bench.pm.possession_spells(gt, spans))
        point = bench.spell_draws(gt, pr, np.arange(n_gt)[None])[0]
        self.assertAlmostEqual(point, bench.pm.spell_scores(gt, pr, spans)["mean_f1"], places=12)
        picks = np.random.RandomState(bench.pm.BOOTSTRAP_SEED).randint(0, n_gt, (500, n_gt))
        lo, hi = np.percentile(bench.spell_draws(gt, pr, picks), bench.pm.BOOTSTRAP_PERCENTILES)
        olo, ohi = bench.pm.bootstrap_spell_f1(gt, pr, spans, 500)
        self.assertAlmostEqual(lo, olo, places=12)
        self.assertAlmostEqual(hi, ohi, places=12)

    def _compare(self, truth, a, b):
        preds = {(1, "start", "degraded", "A"): (truth, [a]), (1, "start", "degraded", "B"): (truth, [b])}
        return bench.compare(preds, "A", "B", 1000)[("start", "degraded")]

    def test_identical_pipelines_differ_by_exactly_zero(self):
        truth = spells_with_gaps(["H", "A"] * 30)
        self.assertEqual(self._compare(truth, truth, truth)[:3], (0.0, 0.0, 0.0))

    def test_seed_resampling_is_paired_and_includes_seed_noise(self):
        truth = spells_with_gaps(["H", "A"] * 30)
        wrong = spells_with_gaps(["A", "H"] * 30)
        a, b = [truth, wrong], [wrong, truth]
        preds = {(1, "start", "degraded", "A"): (truth, a),
                 (1, "start", "degraded", "B"): (truth, b)}
        result = bench.compare(preds, "A", "B", 1000)
        point, lo, hi, _ = result[("start", "degraded")]
        self.assertEqual(point, 0.0)
        self.assertEqual((lo, hi), (-1.0, 1.0))  # without seed resampling every draw was exactly 0
        self.assertEqual(result, bench.compare(preds, "A", "B", 1000))
        self.assertEqual(bench.compare(preds, "A", "A", 1000)[("start", "degraded")][:3], (0.0, 0.0, 0.0))

    def test_games_have_equal_weight_even_with_different_seed_counts(self):
        truth = spells_with_gaps(["H", "A"] * 30)
        wrong = spells_with_gaps(["A", "H"] * 30)
        preds = {(1, "start", "degraded", "A"): (truth, [wrong]),
                 (1, "start", "degraded", "B"): (truth, [truth]),
                 (2, "start", "degraded", "A"): (truth, [truth] * 3),
                 (2, "start", "degraded", "B"): (truth, [wrong] * 3)}
        self.assertEqual(bench.compare(preds, "A", "B", 1000)[("start", "degraded")][:3], (0.0, 0.0, 0.0))

    def test_a_tiny_gain_with_a_wide_spread_is_inside_the_noise(self):
        # The review's counterexample (PR #38): A gets IoU 0.55 on all 100 possessions (0.600, with
        # no spread at all); B is perfect on 61 and gives the other 39 to the rival (0.610). B sits
        # above A's bootstrap interval, but the paired difference spans zero.
        teams = ["H", "A"] * 50
        truth = spells_with_gaps(teams)
        a = spells_with_gaps(teams, length=55, gap=145)
        flip = {"H": "A", "A": "H"}
        b = spells_with_gaps([t if i < 61 else flip[t] for i, t in enumerate(teams)])
        point, lo, hi, _ = self._compare(truth, a, b)
        self.assertAlmostEqual(point, 0.01, places=3)
        self.assertLess(lo, 0)
        self.assertGreater(hi, 0)


class CsvEventsTest(unittest.TestCase):
    def test_games_1_and_2_format(self):
        csv = ("Team,Type,Subtype,Period,Start Frame,Start Time [s],End Frame,End Time [s],From,To,"
               "Start X,Start Y,End X,End Y\n"
               "Away,SET PIECE,KICK OFF,1,1,0.04,0,0,P19,,NaN,NaN,NaN,NaN\n"
               "Home,BALL LOST,GOAL KICK-INTERCEPTION,2,90,3.6,95,3.8,P1,,0.1,0.5,0.3,0.5\n"
               ",BALL OUT,,1,50,2.0,51,2.04,,,NaN,NaN,NaN,NaN\n")
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "events.csv")
            with open(path, "w") as f:
                f.write(csv)
            events = bench.load_csv_events(path)
        self.assertEqual(events, [("SET PIECE", "KICK OFF", 0, -1, 1, "A"),
                                  ("BALL OUT", "", 49, 50, 1, ""),
                                  ("BALL LOST", "GOAL KICK+INTERCEPTION", 89, 94, 2, "H")])


if __name__ == "__main__":
    unittest.main()
