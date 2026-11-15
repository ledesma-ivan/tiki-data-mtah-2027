"""Synthetic tests for rejected restart-gap diagnostics; no match files are read."""
import contextlib
import io
import unittest
import warnings

import numpy as np

from calibrate_dead import FPS, MAX_DEAD_S, discarded_gap_report, discarded_gap_stats


class DiscardedGapTests(unittest.TestCase):
    def masks(self, n=4000):
        return np.zeros(n, bool), np.zeros(n, bool), np.ones(n, bool)

    def test_exact_cutoff_is_not_discarded(self):
        events = [("PASS", "", 0, 25, 1),
                  ("SET PIECE", "THROW IN", 25 + MAX_DEAD_S * FPS, 1550, 1)]
        stats = discarded_gap_stats(events, *self.masks())
        self.assertEqual(stats["gaps"], 0)
        self.assertEqual(stats["discarded_frames"], 0)

    def test_just_above_cutoff_is_discarded(self):
        end = 25 + MAX_DEAD_S * FPS + 1
        events = [("PASS", "", 0, 25, 1), ("SET PIECE", "THROW IN", end, end, 1)]
        pred, true, mask = self.masks()
        pred[25:end] = True
        stats = discarded_gap_stats(events, pred, true, mask)
        self.assertEqual(stats["gaps"], 1)
        self.assertEqual(stats["fp_overlap"], MAX_DEAD_S * FPS + 1)
        self.assertEqual(stats["isolated_overlap"], stats["fp_frames"])

    def test_previous_end_is_maximum_not_previous_list_entry(self):
        events = [("PASS", "", 0, 500, 1), ("SHOT", "", 100, 200, 1),
                  ("SET PIECE", "THROW IN", 1900, 1950, 1)]
        self.assertEqual(discarded_gap_stats(events, *self.masks())["gaps"], 0)

    def test_period_boundary_is_not_a_discarded_gap(self):
        events = [("PASS", "", 0, 25, 1), ("SET PIECE", "KICK OFF", 2000, 2025, 2)]
        self.assertEqual(discarded_gap_stats(events, *self.masks())["gaps"], 0)

    def test_goal_kick_counts_but_an_ordinary_pass_does_not(self):
        first = ("PASS", "", 0, 25, 1)
        restart = ("PASS", "GOAL KICK+LONG BALL", 2000, 2025, 1)
        normal = ("PASS", "LONG BALL", 2000, 2025, 1)
        self.assertEqual(discarded_gap_stats([first, restart], *self.masks())["gaps"], 1)
        self.assertEqual(discarded_gap_stats([first, normal], *self.masks())["gaps"], 0)

    def test_overlap_uses_mask_and_excludes_correct_predictions(self):
        events = [("PASS", "", 0, 100, 1), ("SET PIECE", "THROW IN", 2000, 2025, 1)]
        pred, true, mask = self.masks()
        pred[50:250] = True
        true[110:120] = True
        mask[150:] = False
        original = [a.copy() for a in (pred, true, mask)]
        stats = discarded_gap_stats(events, pred, true, mask)
        self.assertEqual(stats["fp_frames"], 90)
        self.assertEqual(stats["fp_overlap"], 40)
        self.assertEqual(stats["discarded_frames"], 50)
        self.assertEqual(sum(row["overlap"] for row in stats["longest"]), 40)
        for observed, expected in zip((pred, true, mask), original):
            np.testing.assert_array_equal(observed, expected)

    def test_long_fp_can_be_unrelated_to_discarded_gap(self):
        events = [("PASS", "", 0, 100, 1), ("SET PIECE", "THROW IN", 2000, 2025, 1)]
        pred, true, mask = self.masks()
        pred[2200:3900] = True
        stats = discarded_gap_stats(events, pred, true, mask)
        self.assertEqual(stats["fp_frames"], 1700)
        self.assertEqual(stats["fp_overlap"], 0)
        self.assertEqual(stats["longest"][0]["overlap"], 0)

    def test_missing_previous_event_produces_no_gap(self):
        events = [("SET PIECE", "THROW IN", 2000, 2025, 1)]
        self.assertEqual(discarded_gap_stats(events, *self.masks())["gaps"], 0)

    def test_empty_report_does_not_warn_or_divide_by_zero(self):
        stream = io.StringIO()
        with warnings.catch_warnings(), contextlib.redirect_stdout(stream):
            warnings.simplefilter("error", RuntimeWarning)
            discarded_gap_report([], *self.masks())
        text = stream.getvalue()
        self.assertIn("FP overlap 0 / 0", text)
        self.assertNotIn("nan", text.lower())
        self.assertNotIn("rank seconds", text)


if __name__ == "__main__":
    unittest.main()
