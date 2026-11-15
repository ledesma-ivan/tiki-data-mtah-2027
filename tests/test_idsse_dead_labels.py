"""Synthetic tests for rule B (ADR-003) on DFL events; no IDSSE files are read."""
import unittest

import numpy as np

from calibrate_dead import MAX_DEAD_S
from idsse_dead_labels import dead_spans, edge_offsets


def ev(t, kind, sub="", decision=None):
    return (t, kind, sub, decision)


class DeadSpanTests(unittest.TestCase):
    def test_restart_closes_the_span_opened_by_the_last_ball_event(self):
        events = [ev(10, "Play", "Pass"), ev(12, "TacklingGame"), ev(20, "ThrowIn", "Play", 15)]
        self.assertEqual(dead_spans(events), [(12, 20)])
        self.assertEqual(dead_spans(events, decision=True), [(15, 20)])

    def test_cards_substitutions_and_annotations_are_not_the_previous_event(self):
        events = [ev(10, "Foul"), ev(14, "Caution"), ev(16, "Substitution"), ev(17, "Nutmeg"),
                  ev(30, "FreeKick", "Play")]
        self.assertEqual(dead_spans(events), [(10, 30)])

    def test_opening_kick_off_has_no_span(self):
        self.assertEqual(dead_spans([ev(0, "KickOff", "Play"), ev(5, "Play", "Pass")]), [])

    def test_cap_is_lifted_only_after_a_stop(self):
        late = MAX_DEAD_S + 1
        self.assertEqual(dead_spans([ev(0, "Play", "Pass"), ev(late, "ThrowIn", "Play")]), [])
        self.assertEqual(dead_spans([ev(0, "Foul"), ev(late, "FreeKick", "Play")]), [(0, late)])
        goal = ev(0, "ShotAtGoal", "SuccessfulShot")
        self.assertEqual(dead_spans([goal, ev(late, "KickOff", "Play")]), [(0, late)])
        saved = ev(0, "ShotAtGoal", "SavedShot")
        self.assertEqual(dead_spans([saved, ev(late, "CornerKick", "Play")]), [])

    def test_no_cap_keeps_long_stops(self):
        late = MAX_DEAD_S + 1
        self.assertEqual(dead_spans([ev(0, "Play", "Pass"), ev(late, "ThrowIn", "Play")], cap=None), [(0, late)])

    def test_decision_opens_the_span_without_cap_and_falls_back_to_rule_b(self):
        late = MAX_DEAD_S + 1
        events = [ev(0, "Play", "Pass"), ev(late, "ThrowIn", "Play", late - 5)]
        self.assertEqual(dead_spans(events, decision=True), [(late - 5, late)])
        # kick-offs and dropped balls carry no DecisionTimestamp
        goal = ev(0, "ShotAtGoal", "SuccessfulShot")
        self.assertEqual(dead_spans([goal, ev(40, "KickOff", "Play")], decision=True), [(0, 40)])


class EdgeTests(unittest.TestCase):
    def test_offsets_only_for_truth_runs_matched_with_iou_half(self):
        truth = np.zeros(40, bool)
        truth[5:10] = truth[20:25] = truth[30:40] = True
        pred = np.zeros(40, bool)
        pred[4:10] = True  # IoU 5/6: matched, starts 1 frame early
        pred[30:33] = True  # IoU 3/10: not matched; the run at 20 has no prediction at all
        self.assertEqual(edge_offsets(truth, pred), ([-1], [0]))


if __name__ == "__main__":
    unittest.main()
