"""Synthetic checks for ADR-027. No open-data loaders are invoked."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import numpy as np

import calibrate_live as CL
from explore import controlled_truth as CT
from tests.test_calibrate_live import game


def event_game():
    g = game(n=1600)
    events = [("PASS", "", 100, 100, 1, "H"), ("RECOVERY", "", 250, 250, 1, "A"),
              ("PASS", "", 280, 280, 1, "H"), ("PASS", "", 350, 350, 1, "H"),
              ("RECOVERY", "", 500, 500, 1, "A"), ("PASS", "", 550, 550, 1, "A"),
              ("PASS", "", 700, 700, 1, "A"), ("PASS", "", 900, 900, 2, "H"),
              ("RECOVERY", "", 1100, 1100, 2, "A"), ("PASS", "", 1150, 1150, 2, "A"),
              ("PASS", "", 1499, 1499, 2, "A")]
    dead = np.zeros(len(g.ball), bool)
    truths = {a: CL.bench.truth_labels(events, len(g.ball), dead, a) for a in ("start", "end")}
    return g._replace(truths=truths, dead=dead, graded=truths["start"] != "X"), events


def flip(a):
    return np.where(a == "H", "A", np.where(a == "A", "H", a)).astype(object)


def test_default_rows_and_eval_do_not_load_events_and_remain_identical():
    g = game(n=1600)
    with patch.object(CL, "metrica_events", side_effect=AssertionError("default loaded B")):
        assert CL.truth_of(g) is g.truths["start"]
        default = CL.game_rows(g)
        explicit = CL.game_rows(g, training_truth="A")
        assert all(np.array_equal(a, b) for a, b in zip(default, explicit))
        assert CL.evaluation_truths(g) is g.truths
    with patch.object(CL, "metrica_events", side_effect=AssertionError("IDSSE loaded events")):
        idsse = game(n=1600, idsse=True)
        assert CL.truth_of(idsse, "B") is idsse.truths["status"]


def test_B_changes_only_targets_and_short_durations():
    g, events = event_game()
    with patch.object(CL, "metrica_events", return_value=events):
        a = CL.game_rows(g)
        b = CL.game_rows(g, training_truth="B")
        assert np.array_equal(a[0], b[0]) and a[0].dtype == np.int64
        assert not np.array_equal(a[1], b[1]) and not np.array_equal(a[2], b[2])
        target = CL.truth_of(g, "B")
        assert target[250] == "H" and target[500] == "A"
        assert (target[701:900] == "X").all() and target[900] == "H"
        # Swapping annotation teams and slot teams swaps labels, not the paired feature set.
        swapped = g._replace(team=flip(g.team), truths={k: flip(v) for k, v in g.truths.items()})
        with patch.object(CL, "metrica_events", return_value=[e[:-1] + (flip(np.array([e[-1]]))[0],) for e in events]):
            assert np.array_equal(CL.truth_of(swapped, "B"), flip(target))
            s = CL.game_rows(swapped, training_truth="B")
        assert np.array_equal(np.sort(s[1]), np.sort(b[1]))
        assert np.array_equal(np.sort(s[2]), np.sort(b[2]))
        # H/A row blocks exchange, leaving the joint paired training set identical.
        left, right = (np.column_stack(r) for r in (s, b))
        np.testing.assert_array_equal(left[np.lexsort(left.T)], right[np.lexsort(right.T)])


def test_unknown_ball_periods_symmetry_and_integer_scores():
    g, events = event_game()
    g = g._replace(ball=np.full_like(g.ball, np.nan))
    def exact(F):
        return (F[:, 0] - F[:, len(CL.P.LIVE_TEAM)]).astype(np.int64)
    with patch.object(CL, "metrica_events", return_value=events):
        X, _, _ = CL.game_rows(g, training_truth="B")
        assert (X[:, CL.P.LIVE_FEATURES.index("own_nearest")] == CL.P.UNKNOWN).all()
        spans = CL.CE.spans_of(g)
        FH, FA = CL.P.live_features(g.players, g.ball, g.team, np.full(len(g.ball), "", object), g.dead, spans, g.pitch)
        assert (FH[701:900] == CL.P.UNKNOWN).all()
        assert FH[900, CL.P.LIVE_FEATURES.index("own_ev_past_125")] == 0
        diff = exact(FH) - exact(FA)
        assert diff.dtype == np.int64
        assert np.array_equal(diff, -(exact(FA) - exact(FH)))
        assert np.array_equal(CL.P.segment_live(g.dead, diff, spans, CL.switch_of(10)),
                              CL.P.segment_live(g.dead, diff, spans, CL.switch_of(10)))


def test_exported_B_model_is_repeatable_and_antisymmetric():
    g, events = event_game()
    with patch.object(CL, "metrica_events", return_value=events):
        rows = [(g.match, *CL.game_rows(g, training_truth="B"))]
    first, second = (CL.model_of(CL.fit(rows, 7, short_weight=1), CT.RECIPE) for _ in range(2))
    assert CL.to_json(first) == CL.to_json(second)
    assert all(v.dtype == np.int64 for tree in first["trees"]["trees"] for v in tree.values())
    ev = CL.bench.radio_evidence(g.players, g.ball, g.team, pitch=g.pitch)
    FH, FA = CL.P.live_features(g.players, g.ball, g.team, ev, g.dead, CL.CE.spans_of(g), g.pitch)
    score = CL.tree_scorer(first["trees"])
    forward, backward = score(FH) - score(FA), score(FA) - score(FH)
    assert forward.dtype == np.int64 and np.array_equal(forward, -backward)
    assert (forward != 0).any()


def test_eval_reuses_arrays_without_retraining_and_rejects_coverage_mismatch():
    g, events = event_game()
    model = {"m": (lambda F: F[:, 0].astype(np.int64), CL.switch_of(10))}
    with patch.object(CL, "metrica_events", return_value=events):
        a = CL.score([g], model, [0])
        with patch.object(CL.P, "live_features", side_effect=AssertionError("evaluating recomputed features")):
            b = CL.reevaluate(a, [g], "B")
        for k in a:
            assert a[k][1] is b[k][1]
        direct = CL.score(iter([g]), model, [0], evaluation_truth="B")
        for k in direct:
            assert np.array_equal(direct[k][0], b[k][0])
            assert np.array_equal(direct[k][1][0], b[k][1][0])
        assert not np.array_equal(a[(2, "start", "degraded", "m")][0], b[(2, "start", "degraded", "m")][0])
        bad = g.truths["start"].copy()
        bad[300] = "X"
        for target in (bad, bad[:-1], np.where(bad == "H", "D", bad)):
            try:
                CL.check_truth_coverage(g.truths["start"], target)
            except ValueError:
                pass
            else:
                raise AssertionError("accepted incompatible coverage")
    for fn in (lambda: CL.truth_of(g, "C"), lambda: CL.score([g], model, [0], evaluation_truth="C")):
        try:
            fn()
        except ValueError:
            pass
        else:
            raise AssertionError("accepted invalid truth")


def test_compiled_exported_scorer_is_exact_at_thresholds_and_unknown():
    rng = np.random.default_rng(94)
    X = rng.integers(-200, 201, (3000, len(CL.P.LIVE_FEATURES)), dtype=np.int64)
    y = (X[:, 0] > 5) ^ (X[:, 1] < -9)
    clf = CL.fit([(("metrica", 2), X, y, np.zeros(len(X), bool))], 7, short_weight=1)
    scorer = CT.ExportedScorer(clf)
    cases = [X[:1000], np.full((1, X.shape[1]), CL.P.UNKNOWN, np.int64)]
    # Each internal threshold and both adjacent integers, including negative thresholds.
    for tree in scorer.part["trees"]:
        for feature, threshold in zip(tree["feature"], tree["threshold"]):
            if feature < 0:
                continue
            F = np.zeros((3, X.shape[1]), np.int64)
            F[:, feature] = threshold + np.array([-1, 0, 1])
            cases.append(F)
    F = np.vstack(cases)
    expected = CL.P.tree_scores(F, scorer.part)
    assert np.array_equal(scorer(F), expected)
    assert np.array_equal(scorer(F), expected)
    assert scorer.verified_rows == 2 * len(F) and scorer.remaining == 0
    assert np.array_equal(scorer(F[::-1]), expected[::-1])
    for bad in (F.astype(float), np.full((1, F.shape[1]), 2**53 + 1, np.int64)):
        try:
            scorer(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("accepted inexact signals")


def test_lomo_holds_both_halves_out_and_rejects_reserve():
    rows = {m: [(m, h) for h in range(2 if m[0] == "idsse" else 1)] for m in CT.MATCHES}
    for held in CT.MATCHES:
        train = CT.training_rows(rows, held)
        assert len(train) == sum(map(len, rows.values())) - len(rows[held])
        assert {r[0] for r in train} == set(CT.MATCHES) - {held}
    try:
        CT.training_rows(dict(rows, forbidden=[]), CT.MATCHES[0])
    except ValueError:
        pass
    else:
        raise AssertionError("accepted nonselection match")


def test_cli_guards_legacy_choice_and_confirm_protocol():
    a, _, _ = CL.cli(["--select", "--training-truth", "B", "--evaluation-truth", "A", "--choice-report", "/tmp/adr027-choice.json"])
    assert a.training_truth == "B" and a.evaluation_truth == "A"
    for argv in (["--select", "--training-truth", "B"], ["--select", "--evaluation-truth", "B", "--choice-report", CL.CHOICE],
                 ["--final", "--training-truth", "B"], ["--rule", "--evaluation-truth", "B"]):
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                CL.cli(argv)
        except SystemExit as e:
            assert e.code == 2
        else:
            raise AssertionError("accepted unsafe CLI options")


def test_select_passes_truths_separately_and_protects_default_choice():
    g, events = event_game()
    idsse = game(n=1600, idsse=True)
    selected = (g.match, idsse.match)
    games = {g.match: [g], idsse.match: [idsse]}
    targets, evaluations, trained = [], [], []
    original_rows, original_score = CL.game_rows, CL.score

    def rows(game_, *args, **kw):
        targets.append(kw["training_truth"])
        return original_rows(game_, *args, **kw)

    def score(games_, models, seeds, **kw):
        evaluations.append(kw["evaluation_truth"])
        return original_score(games_, models, seeds, **kw)

    class FakeClassifier:
        def decision_function(self, F):
            return F[:, CL.P.LIVE_FEATURES.index("own_tracked")] / 10.0

    def fit(rows_, leaves):
        trained.append({r[0] for r in rows_})
        return FakeClassifier()

    with tempfile.TemporaryDirectory() as directory, patch.object(CL, "metrica_events", return_value=events), \
            patch.object(CL.CE, "SELECTION", selected), patch.object(CL.CE, "load", side_effect=games.__getitem__), \
            patch.object(CL, "game_rows", side_effect=rows), patch.object(CL, "score", side_effect=score), \
            patch.object(CL, "fit", side_effect=fit), patch.object(CL, "LEAVES", (7,)), \
            patch.object(CL, "recipes", return_value={"test": dict(leaves=7, lam=10)}), \
            patch.object(CL.CE, "SEEDS", {"select": {"metrica": (0,), "idsse": (0,)}}):
        report = Path(directory) / "choice.json"
        with contextlib.redirect_stdout(io.StringIO()):
            CL.select(training_truth="B", evaluation_truth="B", choice_path=str(report))
        result = json.loads(report.read_text())
        assert result["training_truth"] == result["evaluation_truth"] == "B"
        assert targets == ["B", "B"] and evaluations == ["B", "B"]
        assert trained == [{idsse.match}, {g.match}]
    with patch.object(CL.CE, "load", side_effect=AssertionError("invalid options loaded data")):
        for kw in (dict(training_truth="B"), dict(training_truth="B", choice_path=CL.CHOICE),
                   dict(training_truth="C"), dict(evaluation_truth="C")):
            try:
                CL.select(**kw)
            except ValueError:
                pass
            else:
                raise AssertionError("accepted invalid selection options")


def test_decision_margins_and_diagnostics():
    rows = [dict(bench=b, evaluation_truth=t, anchor=a, lo=lo, point=0.01, positive_units=n)
            for b, t, a, lo, n in (("Metrica", "B", "start", 0.001, 2), ("IDSSE", "provider", "status", 0.001, 10),
                                  ("Metrica", "A", "start", -0.01, 2))]
    assert CT.decision(rows)["passes"]
    rows[0]["lo"] = 0.0
    assert not CT.decision(rows)["passes"]
    rows[0]["lo"], rows[2]["lo"] = 0.001, -0.010001
    assert not CT.decision(rows)["passes"]
    truth = np.array(list("X" + "H" * 49 + "A" * 50 + "H" * 125 + "A" * 376 + "X"), object)
    d = CT.diagnostics({(2, "start", "degraded", "A-start"): (truth, [truth.copy()])})[0]
    assert d["live_accuracy"] == 1 and d["spell_f1"] == 1
    assert d["predicted_possessions"] == d["true_possessions"] == 4
    assert all(v["recall"] == 1 and v["n_true"] == 1 for v in d["recall"].values())


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
