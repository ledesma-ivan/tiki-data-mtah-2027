"""Synthetic tests for the D labels of ADR-003; no match files are read."""
import unittest

from calibrate_dead import FPS, MAX_DEAD_S, dead_labels
from possession import runs


def d_runs(events, n):
    return [(int(a), int(b)) for a, b in runs(dead_labels(events, n))]


class DeadLabelTests(unittest.TestCase):
    def test_event_on_the_restart_frame_is_not_the_previous_one(self):
        # Metrica tags the keeper's RECOVERY on the goal-kick frame
        events = [("SHOT", "OFF TARGET+OUT", 0, 100, 1), ("RECOVERY", "", 300, 300, 1),
                  ("PASS", "GOAL KICK", 300, 325, 1)]
        self.assertEqual(d_runs(events, 400), [(100, 300)])

    def test_lost_goal_kick_is_a_restart(self):
        events = [("BALL OUT", "", 0, 100, 1), ("BALL LOST", "GOAL KICK+INTERCEPTION", 400, 450, 1)]
        self.assertEqual(d_runs(events, 500), [(100, 400)])

    def test_card_is_not_the_previous_event(self):
        events = [("FAULT RECEIVED", "", 0, 100, 1), ("CARD", "YELLOW", 400, 400, 1),
                  ("SET PIECE", "FREE KICK+INDIRECT", 600, 625, 1)]
        self.assertEqual(d_runs(events, 700), [(100, 600)])

    def test_cap_is_lifted_only_after_a_stop(self):
        start = 100 + MAX_DEAD_S * FPS + 1
        restart = ("SET PIECE", "THROW IN", start, start, 1)
        self.assertEqual(d_runs([("BALL OUT", "", 0, 100, 1), restart], start + 10), [(100, start)])
        self.assertEqual(d_runs([("PASS", "", 0, 100, 1), restart], start + 10), [])
        advantage = ("CHALLENGE", "GROUND+ADVANTAGE+WON", 0, 100, 1)
        self.assertEqual(d_runs([advantage, restart], start + 10), [])


if __name__ == "__main__":
    unittest.main()
