"""ADR-005 option B and its bench/CLI integration, with invented events only."""
import contextlib
import io
import unittest
from unittest.mock import patch

import numpy as np

import bench


def ev(kind, start, end, team, period=1, subtype=""):
    return kind, subtype, start, end, period, team


class VariantBTruthTest(unittest.TestCase):
    def labels(self, events, n=80, dead=None, anchor="start", variant="B"):
        if dead is None:
            dead = np.zeros(n, bool)
        return bench.truth_labels(events, n, dead, anchor, variant)

    def test_interception_and_first_time_pass_backdate_to_the_first_event(self):
        for holder, rival in (("H", "A"), ("A", "H")):
            events = [ev("PASS", 0, 9, holder), ev("RECOVERY", 20, 21, rival),
                      ev("PASS", 28, 35, rival), ev("RECOVERY", 50, 51, holder),
                      ev("PASS", 55, 59, holder)]
            for anchor, start, end in (("start", 20, 50), ("end", 21, 51)):
                with self.subTest(holder=holder, anchor=anchor):
                    b = self.labels(events, anchor=anchor)
                    self.assertTrue((b[start:end] == rival).all())
                    self.assertEqual(b[start - 1], holder)
                    self.assertEqual(b[end], holder)
                    np.testing.assert_array_equal(b, self.labels(events, anchor=anchor, variant="A"))

    def test_a_single_short_rival_event_is_absorbed(self):
        events = [ev("PASS", 0, 9, "H"), ev("RECOVERY", 20, 20, "A"),
                  ev("RECOVERY", 25, 25, "H"), ev("PASS", 30, 59, "H")]
        self.assertTrue((self.labels(events)[0:60] == "H").all())
        self.assertTrue((self.labels(events, variant="A")[20:25] == "A").all())

    def test_recovery_and_carry_in_the_same_frame_do_not_confirm(self):
        events = [ev("PASS", 0, 9, "H"), ev("RECOVERY", 20, 20, "A"),
                  ev("CARRY", 20, 20, "A"), ev("RECOVERY", 25, 25, "H"),
                  ev("PASS", 30, 59, "H")]
        self.assertTrue((self.labels(events)[:60] == "H").all())
        self.assertTrue((self.labels(events, variant="A")[20:25] == "A").all())

    def test_distinct_frames_mean_distinct_starts_with_the_end_anchor_too(self):
        events = [ev("PASS", 0, 9, "H"), ev("RECOVERY", 20, 21, "A"),
                  ev("CARRY", 20, 28, "A"), ev("PASS", 40, 59, "H")]
        self.assertTrue((self.labels(events, anchor="end")[9:60] == "H").all())

    def test_same_frame_duplicates_do_not_move_the_first_candidate(self):
        events = [ev("PASS", 0, 9, "H"), ev("RECOVERY", 20, 21, "A"),
                  ev("CARRY", 20, 24, "A"), ev("PASS", 28, 59, "A")]
        for anchor, start in (("start", 20), ("end", 21)):
            with self.subTest(anchor=anchor):
                labels = self.labels(events, anchor=anchor)
                self.assertEqual(labels[start - 1], "H")
                self.assertTrue((labels[start:60] == "A").all())

    def test_a_holder_event_breaks_the_rival_sequence(self):
        events = [ev("PASS", 0, 9, "H"), ev("RECOVERY", 20, 21, "A"),
                  ev("PASS", 25, 29, "H"), ev("SHOT", 40, 59, "A")]
        self.assertTrue((self.labels(events)[:60] == "H").all())

    def test_duels_and_other_off_ball_events_do_not_break_confirmation(self):
        events = [ev("PASS", 0, 9, "H"), ev("RECOVERY", 20, 21, "A"),
                  ev("CHALLENGE", 22, 23, "H"), ev("BALL LOST", 24, 24, "A"),
                  ev("PASS", 28, 59, "A")]
        self.assertTrue((self.labels(events)[20:60] == "A").all())

    def test_dead_interval_resets_confirmation_even_without_a_restart_event(self):
        events = [ev("PASS", 0, 9, "H"), ev("RECOVERY", 20, 21, "A"),
                  ev("PASS", 35, 39, "A"), ev("PASS", 50, 59, "H")]
        dead = np.zeros(80, bool)
        dead[25:30] = True
        labels = self.labels(events, dead=dead)
        self.assertTrue((labels[20:25] == "H").all())
        self.assertTrue((labels[25:30] == "D").all())
        self.assertTrue((labels[30:60] == "H").all())

    def test_restart_assigns_its_team_and_never_confirms_a_pre_stop_event(self):
        events = [ev("PASS", 0, 9, "H"), ev("RECOVERY", 20, 21, "A"),
                  ev("SET PIECE", 35, 39, "A"), ev("RECOVERY", 50, 51, "H"),
                  ev("PASS", 55, 59, "H")]
        for has_dead in (False, True):
            for anchor in ("start", "end"):
                with self.subTest(has_dead=has_dead, anchor=anchor):
                    dead = np.zeros(80, bool)
                    if has_dead:
                        dead[25:35] = True
                    labels = self.labels(events, dead=dead, anchor=anchor)
                    self.assertTrue((labels[20:25] == "H").all())
                    self.assertTrue((labels[25:35] == ("D" if has_dead else "H")).all())
                    self.assertTrue((labels[35:50] == "A").all())

    def test_all_adr003_restart_types_assign_the_kicker_at_their_start(self):
        for kind in ("SET PIECE", "PASS", "BALL LOST"):
            for anchor in ("start", "end"):
                with self.subTest(kind=kind, anchor=anchor):
                    events = [ev("PASS", 0, 9, "H"), ev(kind, 30, 39, "A", subtype="GOAL KICK"),
                              ev("RECOVERY", 50, 51, "H"), ev("PASS", 55, 59, "H")]
                    dead = np.zeros(80, bool)
                    dead[10:30] = True
                    labels = self.labels(events, dead=dead, anchor=anchor)
                    self.assertTrue((labels[10:30] == "D").all())
                    self.assertTrue((labels[30:50] == "A").all())

    def test_a_delayed_end_from_before_a_stop_cannot_confirm_after_it(self):
        events = [ev("PASS", 0, 5, "H"), ev("RECOVERY", 10, 55, "A"),
                  ev("SET PIECE", 30, 31, "H"), ev("PASS", 35, 36, "A"),
                  ev("PASS", 70, 79, "H")]
        dead = np.zeros(80, bool)
        dead[20:30] = True
        labels = self.labels(events, dead=dead, anchor="end")
        self.assertTrue((labels[30:80] == "H").all())

    def test_events_inside_dead_ball_do_not_count_as_confirmation(self):
        events = [ev("PASS", 0, 9, "H"), ev("RECOVERY", 20, 20, "A"),
                  ev("PASS", 22, 24, "A"), ev("PASS", 35, 39, "A"),
                  ev("PASS", 50, 59, "H")]
        dead = np.zeros(80, bool)
        dead[15:30] = True
        labels = self.labels(events, dead=dead)
        self.assertTrue((labels[15:30] == "D").all())
        self.assertTrue((labels[30:60] == "H").all())

    def test_periods_reset_owner_and_pending_confirmation(self):
        events = [ev("PASS", 0, 9, "H"), ev("RECOVERY", 20, 29, "A"),
                  ev("PASS", 40, 59, "A", period=2)]
        self.assertEqual("".join(self.labels(events)), "H" * 30 + "X" * 10 + "A" * 20 + "X" * 20)

    def test_dead_and_ungraded_coverage_is_preserved(self):
        events = [ev("FAULT RECEIVED", 0, 5, "H"), ev("PASS", 10, 19, "H"),
                  ev("RECOVERY", 25, 26, "A"), ev("SET PIECE", 40, 49, "A")]
        dead = np.zeros(80, bool)
        dead[5:15] = dead[30:40] = True
        for anchor in ("start", "end"):
            a = self.labels(events, dead=dead, anchor=anchor, variant="A")
            b = self.labels(events, dead=dead, anchor=anchor)
            np.testing.assert_array_equal(a == "X", b == "X")
            np.testing.assert_array_equal(a == "D", b == "D")

    def test_empty_or_off_ball_only_periods_stay_ungraded(self):
        for events in ([], [ev("CARD", 0, 10, "H"), ev("PASS", 20, 29, "")]):
            self.assertTrue((self.labels(events) == "X").all())

    def test_invalid_variant_and_anchor_fail_explicitly(self):
        with self.assertRaises(ValueError):
            self.labels([], variant="typo")
        with self.assertRaises(ValueError):
            self.labels([], anchor="typo")


class VariantBBenchTest(unittest.TestCase):
    def setUp(self):
        n = 600
        self.ball = np.full((n, 2), 0.5)
        players = np.zeros((n, 2, 3))
        events = [ev("PASS", 0, 99, "H"), ev("RECOVERY", 200, 204, "A"),
                  ev("RECOVERY", 205, 205, "H"), ev("PASS", 206, n - 1, "H")]
        self.loaded = (players, self.ball, np.array(["H", "A"]), events, (105.0, 68.0))
        self.seen_balls = []

        def pipeline(players, ball, team, spans, dead, *, pitch):
            self.seen_balls.append(ball.copy())
            return np.where(dead, "D", "H")

        self.loader = patch.object(bench, "load_game", return_value=self.loaded).start()
        patch.dict(bench.PIPELINES, {"home": pipeline}, clear=True).start()
        self.addCleanup(patch.stopall)
        self.kwargs = dict(games=[3], seeds=2, live_missing=0.45, mean_gap_s=1.5, crowd=0,
                           anchors=["start", "end"], n_boot=0)

    def test_b_uses_the_same_noise_and_predictions_but_different_reference_labels(self):
        rows_a, preds_a = bench.run(**self.kwargs)
        balls_a = self.seen_balls.copy()
        self.seen_balls.clear()
        rows_b, preds_b = bench.run(**self.kwargs, truth_variant="B")
        self.assertEqual(len(balls_a), len(self.seen_balls))
        for a, b in zip(balls_a, self.seen_balls):
            np.testing.assert_array_equal(a, b)
        self.assertEqual(set(preds_a), set(preds_b))
        for key in preds_a:
            truth_a, pa = preds_a[key]
            truth_b, pb = preds_b[key]
            self.assertTrue((truth_a != truth_b).any())
            for a, b in zip(pa, pb):
                np.testing.assert_array_equal(a, b)
            np.testing.assert_array_equal(truth_a == "X", truth_b == "X")
        self.assertTrue(all(s["truth_variant"] == "A" for _, scores in rows_a for s in scores))
        self.assertTrue(all(s["truth_variant"] == "B" for _, scores in rows_b for s in scores))
        self.assertGreater(rows_a[0][1][0]["n_gt"], rows_b[0][1][0]["n_gt"])
        for result in bench.compare(preds_b, "home", "home", 25).values():
            self.assertEqual(result[:3], (0.0, 0.0, 0.0))

    def test_report_identifies_b_and_refuses_to_pool_a_and_b(self):
        rows_a, _ = bench.run(**self.kwargs)
        rows_b, _ = bench.run(**self.kwargs, truth_variant="B")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            bench.report(rows_b)
        self.assertIn("possession truth variant: B", output.getvalue())
        with self.assertRaises(ValueError):
            bench.report(rows_a + rows_b)

    def test_cli_selects_b_and_keeps_a_as_the_default(self):
        for variant, flag in (("A", []), ("B", ["--truth-variant", "B"])):
            with self.subTest(variant=variant), patch.object(bench, "run", wraps=bench.run) as run:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    bench.main(["--games", "3", "--seeds", "0", "--bootstrap", "0",
                                "--compare", "home", "home"] + flag)
                self.assertEqual(run.call_args.kwargs["truth_variant"], variant)
                self.assertIn(f"possession truth variant: {variant}", output.getvalue())
                self.assertIn("paired spellF1 difference", output.getvalue())

    def test_invalid_options_fail_before_loading_data(self):
        with self.assertRaises(ValueError):
            bench.run(**self.kwargs, truth_variant="C")
        for argv in (["--truth-variant", "C"], ["--truth", "typo"]):
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                bench.main(argv)
        self.loader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
