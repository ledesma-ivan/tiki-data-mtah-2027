"""Synthetic checks for the dead-ball FP report. No match files are loaded."""
import contextlib
import io
import unittest
import warnings

import numpy as np

from calibrate_dead import FPS, fp_edge_events, fp_report, fp_run_groups


class FalsePositiveReportTests(unittest.TestCase):
    def masks(self, pred_runs=(), true_runs=(), n=600):
        pred, true = np.zeros(n, bool), np.zeros(n, bool)
        for start, end in pred_runs:
            pred[start:end] = True
        for start, end in true_runs:
            true[start:end] = True
        return pred, true, np.ones(n, bool)

    def report(self, pred, true, mask, speeds=None):
        players = np.full((len(pred), 2, 3), np.nan)
        if speeds is not None:
            players[:, :, 2] = speeds
        ball = np.full((len(pred), 2), np.nan)
        stream = io.StringIO()
        with warnings.catch_warnings(), contextlib.redirect_stdout(stream):
            warnings.simplefilter("error", RuntimeWarning)
            fp_report(pred, true, mask, players, ball)
        return stream.getvalue()

    def test_before_and_after_are_exclusive(self):
        args = self.masks([(175, 275)], [(200, 250)])
        self.assertEqual(fp_run_groups(*args), [(25, "before_start"), (25, "after_end")])

    def test_bridge_counted_once(self):
        args = self.masks([(200, 325)], [(200, 250), (275, 325)])
        self.assertEqual(fp_run_groups(*args), [(25, "between_two")])

    def test_two_second_gap_is_inclusive(self):
        gap = 2 * FPS
        before = self.masks([(100, 125)], [(125 + gap, 250)])
        after = self.masks([(250 + gap, 325)], [(200, 250)])
        self.assertEqual(fp_run_groups(*before), [(25, "before_start")])
        self.assertEqual(fp_run_groups(*after), [(25, "after_end")])

    def test_gap_beyond_two_seconds_is_isolated(self):
        args = self.masks([(100, 125), (301, 325)], [(176, 250)])
        self.assertEqual(fp_run_groups(*args), [(25, "isolated"), (24, "isolated")])

    def test_long_extension_counts_the_whole_run(self):
        args = self.masks([(20, 250)], [(200, 250)])
        self.assertEqual(fp_run_groups(*args), [(180, "before_start")])

    def test_no_labels_is_isolated(self):
        args = self.masks([(10, 35)])
        self.assertEqual(fp_run_groups(*args), [(25, "isolated")])

    def test_mask_excludes_ungraded_predictions_and_labels(self):
        pred, true, mask = self.masks([(0, 25), (100, 125), (500, 525)], [(150, 200)])
        mask[:50] = False
        mask[150:200] = False
        mask[500:] = False
        self.assertEqual(fp_run_groups(pred, true, mask), [(25, "isolated")])

    def test_no_false_positives_has_no_warning_or_nan(self):
        args = self.masks([(200, 250)], [(200, 250)])
        self.assertEqual(fp_run_groups(*args), [])
        text = self.report(*args)
        self.assertIn("FP frames 0", text)
        self.assertIn("FP runs 0", text)
        self.assertNotIn("nan", text.lower())

    def test_missing_speeds_are_not_slow_and_do_not_warn(self):
        args = self.masks([(100, 125)], [(200, 250)])
        self.assertIn("slow 0%", self.report(*args))
        self.assertIn("slow 100%", self.report(*args, speeds=[0.5, np.nan]))

    def test_longest_list_is_sorted_and_limited_to_ten(self):
        pred_runs = [(30 * i, 30 * i + i + 3) for i in range(12)]
        text = self.report(*self.masks(pred_runs))
        rows = text.split("rank frames seconds side\n")[1].strip().splitlines()
        self.assertEqual([int(row.split()[1]) for row in rows], list(range(14, 4, -1)))

    def test_categories_cover_every_fp_frame_without_mutating_inputs(self):
        pred, true, mask = self.masks([(0, 25), (175, 350), (550, 575)], [(200, 250), (275, 325)])
        original = [a.copy() for a in (pred, true, mask)]
        grouped = fp_run_groups(pred, true, mask)
        self.assertEqual(sum(frames for frames, _ in grouped), int((pred & ~true & mask).sum()))
        self.assertEqual(set(side for _, side in grouped),
                         {"before_start", "after_end", "between_two", "isolated"})
        for observed, expected in zip((pred, true, mask), original):
            np.testing.assert_array_equal(observed, expected)

    def test_edge_events_name_neighbours_and_inner_types(self):
        events = [("PASS", "", 0, 100, 1), ("CARRY", "", 150, 300, 1), ("SET PIECE", "THROW IN", 450, 500, 1)]
        pred, true, mask = self.masks([(120, 400)])
        (row,) = fp_edge_events(events, pred, true, mask)
        self.assertEqual((row["before"], row["after"], row["inside"]), ("PASS", "SET PIECE/THROW IN", {"CARRY": 1}))
        self.assertEqual(fp_edge_events(events, *self.masks()), [])


if __name__ == "__main__":
    unittest.main()
