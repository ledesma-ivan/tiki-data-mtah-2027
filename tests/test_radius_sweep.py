"""ADR-005 truth variants in the ADR-009 sweep, with invented tracking and events only."""
import contextlib
import io
import unittest
from unittest.mock import patch

import numpy as np

from explore import radius_sweep as sweep


class RadiusSweepTest(unittest.TestCase):
    def setUp(self):
        n = 400
        self.pitch = (120.0, 70.0)
        self.ball = np.full((n, 2), 0.5)
        self.ball[160:170] = np.nan
        self.players = np.zeros((n, 2, 3))
        self.players[:, :, :2] = [[0.5, 0.5], [0.8, 0.5]]
        self.players[75:120, :, :2] = [[0.8, 0.5], [0.5, 0.5]]
        self.players[180:280, :, :2] = [[0.8, 0.5], [0.5, 0.5]]
        self.players[:, :, 2] = 3.0
        self.team = np.array(["H", "A"])
        self.events = [("PASS", "", 10, 59, 1, "H"),
                       ("RECOVERY", "", 90, 94, 1, "A"),
                       ("RECOVERY", "", 95, 95, 1, "H"),
                       ("PASS", "", 96, 139, 1, "H"),
                       ("BALL OUT", "", 150, 151, 1, "H"),
                       ("SET PIECE", "", 180, 190, 1, "A"),
                       ("PASS", "", 230, 279, 1, "A"),
                       ("PASS", "", 320, 359, 2, "H")]
        loaded = (self.players, self.ball, self.team, self.events, self.pitch)
        loader = patch.object(sweep.bench, "load_game", return_value=loaded)
        self.loader = loader.start()
        self.addCleanup(loader.stop)

    def test_scenarios_keep_a_default_and_b_changes_only_the_reference(self):
        original_ball, original_players = self.ball.copy(), self.players.copy()
        default = sweep.scenarios(3, 2, 7)
        explicit_a = sweep.scenarios(3, 2, 7, truth_variant="A")
        b = sweep.scenarios(3, 2, 7, truth_variant="B")
        for result in (explicit_a, b):
            players, team, dead, truth, spans, balls, pitch = result
            np.testing.assert_array_equal(players, default[0])
            np.testing.assert_array_equal(team, default[1])
            np.testing.assert_array_equal(dead, default[2])
            self.assertEqual(spans, default[4])
            self.assertEqual(pitch, self.pitch)
            self.assertEqual([kind for kind, _ in balls], ["as is", "degraded", "degraded"])
            for (_, expected), (_, actual) in zip(default[5], balls):
                np.testing.assert_array_equal(actual, expected)
            np.testing.assert_array_equal(truth == "D", default[3] == "D")
            np.testing.assert_array_equal(truth == "X", default[3] == "X")
        np.testing.assert_array_equal(default[3], explicit_a[3])
        self.assertTrue((default[3][90:95] == "A").all())
        self.assertTrue((b[3][90:95] == "H").all())
        np.testing.assert_array_equal(self.ball, original_ball)
        np.testing.assert_array_equal(self.players, original_players)

    def test_scenarios_use_the_requested_seed_block_and_loader_geometry(self):
        with patch.object(sweep.bench, "degrade", wraps=sweep.bench.degrade) as degrade:
            result = sweep.scenarios(2, 2, 7, truth_variant="B")
        self.assertEqual([call.args[6] for call in degrade.call_args_list], [2007, 2008])
        self.assertTrue(all(call.kwargs["pitch"] == self.pitch for call in degrade.call_args_list))
        changed_seed = sweep.scenarios(2, 2, 8, truth_variant="B")
        np.testing.assert_array_equal(result[5][2][1], changed_seed[5][1][1])
        self.assertFalse(np.array_equal(result[5][1][1], result[5][2][1], equal_nan=True))

    def test_invalid_scenario_variant_fails_before_loading_data(self):
        with self.assertRaises(ValueError):
            sweep.scenarios(3, 2, 0, truth_variant="C")
        self.loader.assert_not_called()

    def test_cli_default_and_explicit_a_agree_and_b_keeps_all_predictions(self):
        argv = ["--games", "2,3", "--seeds", "2", "--seed-start", "7",
                "--radii", "0.75,1", "--n", "0.25,0.5", "--interp", "12",
                "--gaps", "6,12", "--top", "20"]
        for dead_mode in ("true", "v1"):
            with self.subTest(dead=dead_mode):
                runs, reports = [], []
                for variant, flag in (("A", []), ("A", ["--truth-variant", "A"]),
                                      ("B", ["--truth-variant", "B"])):
                    observations = []
                    official_score = sweep.bench.score

                    def score(truth, pred, n_boot):
                        observations.append((truth.copy(), pred.copy()))
                        return official_score(truth, pred, n_boot)

                    output = io.StringIO()
                    with patch.object(sweep.bench, "score", side_effect=score), \
                            patch.object(sweep.possession, "dead_mask", return_value=np.zeros(len(self.ball), bool)), \
                            patch.object(sweep.bench, "owner_evidence", wraps=sweep.bench.owner_evidence) as evidence, \
                            contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
                        sweep.main(argv + ["--dead", dead_mode] + flag)
                    self.assertTrue(evidence.call_count)
                    self.assertTrue(all(call.kwargs["pitch"] == self.pitch for call in evidence.call_args_list))
                    self.assertIn(f"possession truth variant: {variant} (ADR-005), anchor: start", output.getvalue())
                    self.assertIn("9 combinations", output.getvalue())  # eight candidates and the frozen baseline
                    self.assertEqual(len(observations), 54)  # two games, three balls, nine configurations
                    runs.append(observations)
                    reports.append(output.getvalue())
                self.assertEqual(reports[0], reports[1])
                for default, explicit_a, b in zip(*runs):
                    np.testing.assert_array_equal(default[0], explicit_a[0])
                    np.testing.assert_array_equal(default[1], explicit_a[1])
                    np.testing.assert_array_equal(default[1], b[1])
                    self.assertTrue((default[0] != b[0]).any())

    def test_cli_rejects_unknown_or_pooled_variants_before_loading_data(self):
        for variant in ("C", "A,B"):
            with self.subTest(variant=variant), self.assertRaises(SystemExit) as error, \
                    contextlib.redirect_stderr(io.StringIO()):
                sweep.main(["--truth-variant", variant])
            self.assertEqual(error.exception.code, 2)
        self.loader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
