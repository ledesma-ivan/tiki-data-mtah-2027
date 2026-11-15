"""ADR-020: evaluation references, whole-match exclusion and diagnostics on invented games only."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import bench
import calibrate_live as CL
from explore import diagnose_changes as DC
from tests.test_calibrate_live import game
from tests.test_bench_variant_b import ev


class EvaluationTest(unittest.TestCase):
    def test_b_reuses_predictions_and_never_changes_training_truth(self):
        g = game(n=1600)
        events = [ev("PASS", 100, 199, "H"), ev("RECOVERY", 300, 300, "A"),
                  ev("PASS", 320, 1499, "H")]
        g = g._replace(dead=CL.CE.calibrate_dead.dead_labels([e[:5] for e in events], 1600))
        a = {k: bench.truth_labels(events, 1600, g.dead, k) for k in ("start", "end")}
        b = {k: bench.truth_labels(events, 1600, g.dead, k, "B") for k in a}
        g = g._replace(truths=a)
        before = CL.game_rows(g)
        labels = a["start"].copy()
        preds = {(g.g, "start", "degraded", name): (a["start"], [labels])
                 for name in ("reference", "candidate")}
        with patch.object(bench, "load_game", return_value=(g.players, g.ball, g.team, events, g.pitch)):
            changed = DC.relabel(preds, [g], "B")
        key = (g.g, "start", "degraded", "candidate")
        self.assertEqual(changed[key][0][300], "H")
        self.assertEqual(preds[key][0][300], "A")
        np.testing.assert_array_equal(changed[key][0], b["start"])
        self.assertIs(changed[key][1][0], labels)
        for x, y in zip(before, CL.game_rows(g), strict=True):
            np.testing.assert_array_equal(x, y)

    def test_incompatible_coverage_is_rejected_instead_of_intersected(self):
        a = np.array(list("HHDAAX"), object)
        for b in (a[:-1], np.array(list("XHDAAX")), np.array(list("HHAAAX"))):
            with self.subTest(b=b), self.assertRaises(ValueError):
                DC.check_coverage(a, b)

    def test_comparison_rejects_different_truths_and_seed_counts(self):
        a = np.array(list("HHHAAA"), object)
        preds = {(2, "start", "degraded", "reference"): (a, [a, a]),
                 (2, "start", "degraded", "candidate"): (a[::-1], [a, a])}
        with self.assertRaises(ValueError):
            DC.comparison(preds, n_draws=20)
        preds[(2, "start", "degraded", "candidate")] = (a, [a])
        with self.assertRaises(ValueError):
            DC.comparison(preds, n_draws=20)

    def test_identical_predictions_have_zero_difference_and_counts_average_seeds(self):
        truth = np.array(["H"] * 25 + ["A"] * 75 + ["D"] * 25, object)
        preds = {(2, "start", "degraded", name): (truth, [truth.copy(), truth.copy()])
                 for name in ("reference", "candidate")}
        result = DC.comparison(preds, n_draws=20)
        self.assertEqual(result[0]["difference"], dict(point=0.0, lo=0.0, hi=0.0))
        metrics = result[0]["models"]["candidate"]
        self.assertEqual(metrics["spellF1"], 1.0)
        self.assertEqual(metrics["true_possessions"], 2)
        self.assertEqual(metrics["predicted_possessions"], 2)
        self.assertEqual(metrics["recall"][0]["true"], 1)
        self.assertEqual(metrics["recall"][0]["recall"], 1.0)
        self.assertEqual(metrics["recall"][1]["true"], 1)

    def test_historical_reconstruction_stops_on_a_different_selection_result(self):
        rows = [dict(bench="Metrica", anchor="start", difference=dict(point=0.00259)),
                dict(bench="IDSSE", anchor="status", difference=dict(point=0.01568))]
        DC.check_reconstruction(rows)
        rows[0]["difference"]["point"] = 0.01
        with self.assertRaises(ValueError):
            DC.check_reconstruction(rows)

    def test_reconstruction_accepts_only_finite_points_within_rounding_uncertainty(self):
        def results(point):
            return [dict(bench="Metrica", anchor="start", difference=dict(point=point)),
                    dict(bench="IDSSE", anchor="status", difference=dict(point=0.0157))]
        for delta in (-0.0001, 0.0, 0.0001):
            DC.check_reconstruction(results(0.0026 + delta))
        for point in (0.0026 - 0.00012, 0.0026 + 0.00012, float("nan"), float("inf"), -float("inf")):
            with self.subTest(point=point), self.assertRaises(ValueError):
                DC.check_reconstruction(results(point))

    def test_failed_reconstruction_keeps_aggregate_evidence_and_does_not_evaluate_b(self):
        truth = np.array(["H"] * 25 + ["A"] * 75, object)
        predictions = {(2, "start", "degraded", name): (truth, [truth.copy()])
                       for name in ("reference", "candidate")}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "diagnosis.json")
            with patch.object(DC, "predict_folds", return_value=({"default": predictions}, [], [])), \
                    patch.object(DC, "relabel", side_effect=AssertionError("B must not be evaluated")), \
                    contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
                DC.main(["--report", path])
            with open(path, encoding="utf-8") as f:
                report = json.load(f)
            self.assertEqual(report["status"], "reconstruction_failed")
            self.assertEqual(report["results"][0]["variant"], "A")
            self.assertEqual(report["results"][0]["difference"]["point"], 0.0)


class FoldTest(unittest.TestCase):
    def test_missing_or_duplicated_halves_fail_before_training(self):
        half = game(n=1600, idsse=True)._replace(g=10)
        other = game(n=1600, idsse=True)._replace(g=11)
        selection = (("idsse", 1), ("metrica", 2))
        invalid = ([half], [half, half], [half, other._replace(match=("idsse", 2))])
        recipe = dict(leaves=7, lam=10.0, short_weight=1.0, short_s=5.0)
        for halves in invalid:
            games = {selection[0]: halves, selection[1]: [game(n=1600)]}
            with self.subTest(units=[g.g for g in halves]), patch.object(CL.CE, "SELECTION", selection), \
                    patch.object(CL.CE, "load", side_effect=games.__getitem__), \
                    patch.object(CL, "fit", side_effect=AssertionError("incomplete matches must not train")) as fit:
                with self.assertRaises(ValueError):
                    DC.predict_folds(recipe, recipe, scenarios={"default": None},
                                     seed_sets={"metrica": [0], "idsse": [0]})
                fit.assert_not_called()

    def test_report_cannot_overwrite_delivered_models_recipe_or_confirmation(self):
        protected = (CL.REPORT, CL.CHOICE, CL.P.LIVE_MODEL_PATH, CL.P.MODEL_PATH)
        with patch.object(CL.CE, "load") as load, contextlib.redirect_stderr(io.StringIO()):
            for path in protected:
                for spelling in (path, os.path.relpath(path)):
                    with self.subTest(path=spelling):
                        with self.assertRaises(SystemExit) as error:
                            DC.cli(["--report", spelling])
                        self.assertEqual(error.exception.code, 2)
            load.assert_not_called()

    def test_every_fit_excludes_both_halves_and_never_loads_reserve(self):
        selection = (("metrica", 2), ("idsse", 1), ("idsse", 2))
        gs = {selection[0]: [game(n=1600)],
              selection[1]: [game(n=1600, idsse=True)._replace(g=10),
                             game(n=1600, seed=1, idsse=True)._replace(g=11)],
              selection[2]: [game(n=1600, seed=2, idsse=True)._replace(g=20, match=selection[2]),
                             game(n=1600, seed=3, idsse=True)._replace(g=21, match=selection[2])]}
        fits = []
        original = CL.fit

        def fit(rows, *args):
            fits.append({r[0] for r in rows})
            return original(rows, *args)

        recipe = dict(leaves=7, lam=10.0, short_weight=1.0, short_s=5.0)
        with patch.object(CL.CE, "SELECTION", selection), \
                patch.object(CL.CE, "load", side_effect=gs.__getitem__), patch.object(CL, "fit", side_effect=fit), \
                contextlib.redirect_stdout(io.StringIO()):
            predictions, folds, games = DC.predict_folds(recipe, recipe, scenarios={"default": None},
                                                        seed_sets={"metrica": [0], "idsse": [0]})
        self.assertEqual(len(folds), 3)
        self.assertEqual(len(fits), 6)
        for i, held in enumerate(selection):
            self.assertEqual(fits[2 * i], set(selection) - {held})
            self.assertEqual(fits[2 * i + 1], set(selection) - {held})
        self.assertEqual(len(games), 5)
        self.assertEqual(len(predictions["default"]), 12)  # two Metrica anchors plus four IDSSE halves, two recipes
        for result in DC.comparison(predictions["default"], n_draws=20):
            self.assertEqual(result["difference"], dict(point=0.0, lo=0.0, hi=0.0))

    def test_reserve_requires_explicit_predeclared_recipes_revision_and_fresh_seeds(self):
        for args in (["--reserve"], ["--reserve", "--seed-start", "80"],
                     ["--seed-start", "80"], ["--reserve", "--seed-start", "20", "--revision", "abc"]):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                DC.cli(args)

    def test_reserve_refuses_the_block_consumed_by_adr021_issue97(self):
        args = ["--reserve", "--seed-start", "80", "--revision", "registered", "--reference",
                "leaves=63", "lam=10", "short_s=5", "short_weight=1", "--candidate",
                "leaves=63", "lam=10", "short_s=5", "short_weight=3"]
        with patch.object(CL, "code_version", return_value={"commit": "registered", "modified": []}), \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            DC.cli(args)

    def test_reserve_rejects_code_edits_after_the_registered_revision(self):
        args = ["--reserve", "--seed-start", "90", "--revision", "registered", "--reference",
                "leaves=63", "lam=10", "short_s=5", "short_weight=1", "--candidate",
                "leaves=63", "lam=10", "short_s=5", "short_weight=3"]
        with patch.object(CL, "code_version", return_value={"commit": "registered", "modified": ["README.md"]}):
            self.assertTrue(DC.cli(args)[0].reserve)
        with patch.object(CL, "code_version", return_value={"commit": "registered",
                                                           "modified": ["explore/diagnose_changes.py"]}), \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            DC.cli(args)


if __name__ == "__main__":
    unittest.main()
