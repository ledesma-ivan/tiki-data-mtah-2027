"""Checks for calibrate_live.py (ADR-014, ADR-019) on synthetic data. Run: python -m tests.test_calibrate_live (needs
requirements-train.txt)"""
import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

import calibrate_live as CL
from calibrate_edges import SCALE, Game, export
from possession import LIVE_FEATURES, UNKNOWN, load_live_model, tree_scores


def game(n=4000, seed=0, idsse=False):
    """A Metrica-like synthetic game (IDSSE-like with idsse): two players per team, the ball near H in the first half of
    every 400 frames and near A in the second, a stop and X frames at both ends."""
    rng = np.random.default_rng(seed)
    players = np.zeros((n, 4, 3))
    players[:, :, 0] = np.clip(np.cumsum(rng.normal(0, 0.002, (n, 4)), axis=0) + [0.2, 0.4, 0.6, 0.8], 0, 1)
    players[:, :, 1] = 0.5
    players[:, :, 2] = 3.0
    players[2000:2300, :, 2] = 0.5  # everybody slow while the truth says live: a stop of dead_mask_v2 only
    owner = np.where((np.arange(n) // 200) % 2 == 0, 1, 3)  # slot 1 (H) or slot 3 (A)
    ball = np.clip(players[np.arange(n), owner, :2] + [0.003, 0], 0.01, 0.99)
    dead = np.zeros(n, bool)
    dead[1000:1100] = True
    truth = np.where(owner == 1, "H", "A").astype(object)
    truth[dead] = "D"
    truth[:100] = truth[-100:] = "X"
    graded = truth != "X"
    team = np.array(["H", "H", "A", "A"])
    if idsse:
        return Game(11, ("idsse", 1), players, ball, team, {"status": truth}, dead, graded, [], (105.0, 68.0))
    return Game(2, ("metrica", 2), players, ball, team, {"start": truth, "end": truth}, dead, graded, [], (105.0, 68.0))


def test_game_rows_gives_one_positive_and_one_negative_per_sampled_live_frame():
    g = game()
    X, y, short = CL.game_rows(g)
    live = ((g.truths["start"] == "H") | (g.truths["start"] == "A")).sum()
    bound = sum(len(range(v, live, CL.STEP)) for v in range(2 * len(CL.TRAIN_BALLS)))
    assert X.dtype == np.int64 and X.shape[1] == len(LIVE_FEATURES) and 2 * y.sum() == len(y)
    assert len(y) < 2 * bound * 0.95  # the stop of dead_mask_v2 (300 of 3700 live frames) gives no rows...
    assert (X[:, LIVE_FEATURES.index("live_since")] != UNKNOWN).all()  # ...nor does any frame the decoder never sees
    assert short.dtype == bool and len(short) == len(y)


def test_switch_and_recipes():
    assert CL.switch_of(20) == 40 * SCALE and CL.switch_of(5) == 10 * SCALE
    r = CL.recipes()
    assert len(r) == 8 and {v["leaves"] for v in r.values()} == {31, 63} and {v["lam"] for v in r.values()} == {5, 10, 20, 40}


def test_fit_and_the_two_scorers():
    rng = np.random.default_rng(2)
    X = rng.integers(0, 100, (3000, len(LIVE_FEATURES))).astype(np.int64)
    y = X[:, 0] > 50
    short = rng.random(3000) < 0.3
    clf = CL.fit([(("metrica", 2), X[:1500], y[:1500], short[:1500]), (("idsse", 1), X[1500:], y[1500:], short[1500:])], 7)
    exact, fast = CL.tree_scorer(export(clf)), CL.sklearn_scorer(clf)
    assert ((fast(X) > 0) == y).mean() > 0.99
    assert np.abs(exact(X) - fast(X)).max() <= len(clf._predictors) + 1  # one rounding per leaf, plus the init


def test_score_gives_bench_compare_its_format():
    g = game()
    X, y, short = CL.game_rows(g)
    clf = CL.fit([(g.match, X, y, short)], 7)
    preds = CL.score([g], {"m": (CL.sklearn_scorer(clf), CL.switch_of(5))}, [0], anchors={"start"}, true_d=True)
    assert set(preds) == {(2, "start", "degraded", k) for k in ("radio", "m", "radio, true D", "m, true D")}
    truth, labels = preds[(2, "start", "degraded", "m")]
    assert len(labels) == 1 and len(labels[0]) == len(truth) and set(labels[0]) <= {"H", "A", "D", "X"}
    assert tree_scores(X[:5], export(clf)).dtype == np.int64


# -- ADR-019: recipes, the comparison against the delivered recipe (#83) and the guarded export (#84) --------------

def test_recipes_are_explicit_and_invalid_ones_are_rejected():
    base = CL.recipe_of([])
    assert set(base) == {"leaves", "lam", "short_weight", "short_s"}
    heavier = CL.recipe_of(["short_weight=3"])  # the other side of the #77 pair
    assert heavier["short_weight"] == 3 and {k: v for k, v in heavier.items() if k != "short_weight"} == \
        {k: v for k, v in base.items() if k != "short_weight"}
    assert CL.recipe_of(["leaves=31", "lam=5"])["leaves"] == 31 and CL.recipe_of(["lam=5"])["lam"] == 5
    for bad in (["weight=1"], ["short_weight=0"], ["short_weight=-1"], ["short_weight=abc"], ["leaves=1"],
                ["leaves=2.5"], ["lam=0"], ["short_s=nan"], ["short_weight=inf"], ["short_weight"]):
        try:
            CL.recipe_of(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")


def test_the_short_cut_and_weight_are_arguments():
    delivered = CL.SHORT_WEIGHT
    g = game()
    _, y, none = CL.game_rows(g, short_s=0.001)  # no true possession lasts less than a millisecond
    _, _, every = CL.game_rows(g, short_s=1e9)
    assert not none.any() and every.all() and len(every) == len(y)
    rng = np.random.default_rng(3)
    X = rng.integers(0, 100, (3000, len(LIVE_FEATURES))).astype(np.int64)
    y = X[:, 0] + rng.integers(-30, 30, 3000) > 50  # noisy, so the weights move the leaves
    short = X[:, 1] < 30
    rows = [(("metrica", 2), X, y, short)]
    one, three = (CL.fit(rows, 7, short_weight=w).decision_function(X) for w in (1, 3))
    assert np.abs(one - three).max() > 1e-3  # the weight changes the model...
    no_short = [(("metrica", 2), X, y, np.zeros(3000, bool))]
    a, b = (CL.fit(no_short, 7, short_weight=w).decision_function(X) for w in (1, 3))
    assert np.array_equal(a, b)  # ...only through the short frames
    assert CL.SHORT_WEIGHT == delivered  # and no global changed on the way


def benches(seeds=(0,)):
    return (("Metrica", [game()], list(seeds)), ("IDSSE", [game(idsse=True)], list(seeds)))


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


def fitted(short_weight=3.0):
    g = game()
    return CL.fit([(g.match, *CL.game_rows(g))], 7, short_weight=short_weight)


def test_a_model_against_itself_gives_exact_zeros_and_does_not_confirm():
    """Two scorers of the same model, scored on the same balls and players: every paired difference is exactly 0 (with
    seeds out of step or a comparison against radio it would not be), and a tie never confirms."""
    clf = fitted()
    models = {"reference": (CL.sklearn_scorer(clf), CL.switch_of(10)), "candidate": (CL.sklearn_scorer(clf), CL.switch_of(10))}
    with quiet():
        conds, history = CL.conditions(benches(seeds=(0, 1)), models, "reference", "candidate", n_draws=100)
    assert len(conds) == 43
    assert sorted((c["scenario"], c["bench"], c["anchor"]) for c in conds) == sorted(CL.CONDITIONS)
    assert sum(c["scenario"] == "default" for c in conds) == 3  # Metrica with both truths and IDSSE
    assert all(c["point"] == c["lo"] == c["hi"] == 0 and c["holds"] is False for c in conds)
    assert not CL.decide(conds, 0)
    assert any(h["against"] == "radio" for h in history)  # radio stays as the line that does not decide


def test_a_worse_candidate_does_not_confirm():
    zero = lambda F: np.zeros(len(F), np.int64)  # noqa: E731  no evidence at all
    models = {"reference": (CL.sklearn_scorer(fitted()), CL.switch_of(10)), "candidate": (zero, CL.switch_of(10))}
    with quiet():
        conds, _ = CL.conditions(benches(), models, "reference", "candidate", n_draws=100)
    default = [c for c in conds if c["scenario"] == "default"]
    assert len(default) == 3 and all(c["point"] < 0 for c in default)  # candidate minus reference, not the other way
    assert not CL.decide(conds, 0)


def passing():
    """The 43 conditions of ADR-019, every one holding by a small margin."""
    return [dict(scenario=s, bench=b, anchor=a, point=0.02, lo=0.01, hi=0.03) for s, b, a in CL.CONDITIONS]


def test_decide_needs_every_declared_condition_and_the_exact_trees():
    assert CL.decide(passing(), 0)
    tie = passing()
    next(c for c in tie if c["scenario"] == "default")["lo"] = 0.0  # the interval touches 0
    assert not CL.decide(tie, 0)
    flat = passing()
    next(c for c in flat if c["scenario"] != "default")["point"] = 0.0
    assert not CL.decide(flat, 0)
    assert not CL.decide(passing()[:-1], 0)  # a missing condition
    assert not CL.decide(passing()[:-1] + passing()[:1], 0)  # 43 entries, one of them twice
    assert not CL.decide(passing(), 1)  # the exported trees disagree with decision_function on one frame
    assert not CL.decide(passing(), None)
    assert not CL.decide(passing(), False)  # a boolean is not a frame count, even if False == 0
    boolean = passing()
    next(c for c in boolean if c["scenario"] == "default")["lo"] = True  # nor a bound, even if True > 0
    try:
        verdict = CL.decide(boolean, 0)
    except TypeError:
        verdict = False
    assert not verdict


def rows_of_two_games():
    return [(g.match, *CL.game_rows(g)) for g in (game(), game(idsse=True))]


def approved(rows):
    """A report that lets --final export the delivered recipe trained on rows."""
    fingerprint = dict(CL.fingerprint(rows), selection_model=CL.model_digest(
        [r for r in rows if r[0] in CL.CE.SELECTION], CL.recipe_of([])))
    return {"protocol": CL.PROTOCOL, "status": "confirmed", "candidate": CL.recipe_of([]),
            "reference": CL.recipe_of(["short_weight=3"]), "conditions": passing(), "exact": {"frames_differ": 0},
            "fingerprint": fingerprint}


def test_final_refuses_without_an_approved_compatible_report_and_keeps_the_model():
    rows = rows_of_two_games()
    changed_rows = [rows[0][:2] + (~rows[0][2],) + rows[0][3:]] + rows[1:]  # the code that builds the rows changed
    base = approved(rows)
    no_scorer = dict(base, fingerprint={k: v for k, v in base["fingerprint"].items() if k != "scorer"})
    cases = {"missing": None, "broken": "{not json", "rejected": dict(base, status="rejected"),
             "other recipe": dict(base, candidate=CL.recipe_of(["short_weight=3"])),
             "inexact trees": dict(base, exact={"frames_differ": 2}),
             "unsupported status": dict(base, conditions=passing()[:-1]),  # says confirmed, the numbers do not
             "no fingerprint": {k: v for k, v in base.items() if k != "fingerprint"},
             "rows changed": approved(changed_rows), "other protocol": dict(base, protocol="ADR-014"),
             "frames as a boolean": dict(base, exact={"frames_differ": False}), "no scorer": no_scorer}
    with tempfile.TemporaryDirectory() as tmp:
        model, report = os.path.join(tmp, "live_model.json"), os.path.join(tmp, "live_confirmation.json")
        before = b'{"mode":"rule"}\n'
        with open(model, "wb") as f:
            f.write(before)
        for name, content in cases.items():
            if os.path.exists(report):
                os.remove(report)
            if content is not None:
                with open(report, "w", encoding="utf-8") as f:
                    f.write(content if isinstance(content, str) else json.dumps(content))
            problems = CL.final(report, model, rows)
            assert problems, f"{name}: exported anyway"
            with open(model, "rb") as f:
                assert f.read() == before, f"{name}: the model changed"
        assert sorted(os.listdir(tmp)) == ["live_confirmation.json", "live_model.json"]


def test_final_with_an_approved_report_writes_the_model_and_its_provenance():
    rows = rows_of_two_games()
    with tempfile.TemporaryDirectory() as tmp:
        model, report = os.path.join(tmp, "live_model.json"), os.path.join(tmp, "live_confirmation.json")
        with open(report, "w", encoding="utf-8") as f:
            json.dump(approved(rows), f)
        with quiet():
            assert CL.final(report, model, rows) == []
        assert load_live_model(model)["mode"] == "model"
        with open(model, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        with open(report, encoding="utf-8") as f:
            provenance = json.load(f)["final"]
        assert provenance["sha256"] == digest
        assert provenance["matches"] == ["metrica 2", "idsse 1"]  # selection and reserve: not an independent evaluation
        assert sorted(os.listdir(tmp)) == ["live_confirmation.json", "live_model.json"]  # no temporary file left


def refused_with_rows(report_content, rows):
    """final()'s problems for report_content and rows, checking that the model file keeps its bytes."""
    with tempfile.TemporaryDirectory() as tmp:
        model, report = os.path.join(tmp, "live_model.json"), os.path.join(tmp, "live_confirmation.json")
        with open(model, "wb") as f:
            f.write(b'{"mode":"rule"}\n')
        with open(report, "w", encoding="utf-8") as f:
            json.dump(report_content, f)
        with quiet():
            problems = CL.final(report, model, rows)
        with open(model, "rb") as f:
            assert f.read() == b'{"mode":"rule"}\n'
    return problems


def test_final_refuses_when_the_training_code_or_the_order_changed():
    rows = rows_of_two_games()
    report = approved(rows)
    assert refused_with_rows(report, rows[::-1])  # the same rows in another order train other weights
    original = CL.fit
    CL.fit = lambda rows_, leaves, short_weight=CL.SHORT_WEIGHT: original(rows_, leaves, 2 * short_weight)  # other weights
    try:
        assert refused_with_rows(report, rows)
    finally:
        CL.fit = original


def test_a_candidate_against_radio_decides_on_the_43_conditions():
    """ADR-033: --reference radio keeps the 43 conditions and the rule, with radio as the reference."""
    a, candidate, reference = CL.cli(["--confirm", "--seed-start", "110", "--reference", "radio"])
    assert reference == CL.RADIO and candidate == CL.recipe_of([])
    models = {"candidate": (CL.sklearn_scorer(fitted()), CL.switch_of(10))}
    with quiet():
        conds, history = CL.conditions(benches(), models, CL.RADIO, "candidate", n_draws=100)
    assert sorted((c["scenario"], c["bench"], c["anchor"]) for c in conds) == sorted(CL.CONDITIONS)
    assert history and all(h["against"] != h["model"] for h in history)  # no radio against itself
    assert CL.decide(conds, 0) == all(c["holds"] for c in conds)
    for argv in (["--confirm", "--seed-start", "110", "--reference", "radio", "lam=5"],
                 ["--confirm", "--seed-start", "110", "--reference", "Radio"]):
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                CL.cli(argv)
        except SystemExit as e:
            assert e.code == 2, argv
            continue
        raise AssertionError(f"accepted {argv}")


def test_usage_errors_stop_before_any_data():
    a, candidate, reference = CL.cli(["--confirm", "--seed-start", "70", "--candidate", "lam=5",
                                      "--candidate", "leaves=31"])
    assert (candidate["lam"], candidate["leaves"], a.seed_start) == (5, 31, 70)  # a repeated option adds its changes
    assert reference == CL.recipe_of([])
    for argv in (["--confirm", "--seed-start", "70"],  # the candidate is the reference
                 ["--confirm", "--candidate", "short_weight=3"],  # no block of seeds
                 ["--confirm", "--seed-start", "70", "--reference", "weight=1"],
                 ["--final", "--candidate", "lam=5"], ["--select", "--seed-start", "70"]):
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                CL.cli(argv)
        except SystemExit as e:
            assert e.code == 2, argv
            continue
        raise AssertionError(f"accepted {argv}")


def test_confirm_trains_on_the_selection_only_and_writes_a_report_final_can_check():
    """confirm() end to end on synthetic matches named as the real partition: no reserve match enters training, the
    report holds every field, its status follows its numbers and its fingerprint is the one final() computes."""
    synthetic = {("metrica", 2): [game(n=1600, seed=1)], ("idsse", 1): [game(n=1600, seed=2, idsse=True)],
                 ("metrica", 1): [game(n=1600, seed=3)._replace(g=1, match=("metrica", 1))],
                 ("idsse", 6): [game(n=1600, seed=4, idsse=True)._replace(g=61, match=("idsse", 6))],
                 ("idsse", 7): [game(n=1600, seed=5, idsse=True)._replace(g=71, match=("idsse", 7))]}
    trained_on = []
    saved = CL.CE.load, CL.CE.SELECTION, CL.CE.RESERVE, CL.fit
    original = CL.fit

    def recording_fit(rows, *args, **kwargs):
        trained_on.append({r[0] for r in rows})
        return original(rows, *args, **kwargs)

    CL.CE.load, CL.CE.SELECTION, CL.CE.RESERVE = synthetic.__getitem__, (("metrica", 2), ("idsse", 1)), \
        (("metrica", 1), ("idsse", 6), ("idsse", 7))
    CL.fit = recording_fit
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "live_confirmation.json")
            with quiet():
                returned = CL.confirm(70, CL.recipe_of([]), CL.recipe_of(["short_weight=3"]), path, n_draws=50)
            with open(path, encoding="utf-8") as f:
                report = json.load(f)
        assert report == json.loads(json.dumps(returned))
        assert trained_on and all(m <= {("metrica", 2), ("idsse", 1)} for m in trained_on)  # never the reserve
        assert set(CL.REPORT_KEYS) <= set(report)
        assert (report["status"] == "confirmed") == CL.decide(report["conditions"], report["exact"]["frames_differ"])
        rows = [(m, *CL.game_rows(g)) for m in CL.CE.SELECTION + CL.CE.RESERVE for g in synthetic[m]]
        CL.fit = original
        expected = dict(CL.fingerprint(rows), selection_model=CL.model_digest(rows[:2], CL.recipe_of([])))
        assert report["fingerprint"] == json.loads(json.dumps(expected))
    finally:
        CL.CE.load, CL.CE.SELECTION, CL.CE.RESERVE, CL.fit = saved


def test_the_cli_exits_with_an_error_and_leaves_the_delivered_model_alone():
    with open(CL.P.LIVE_MODEL_PATH, "rb") as f:
        before = f.read()
    with tempfile.TemporaryDirectory() as tmp:
        missing = os.path.join(tmp, "no-report.json")
        done = subprocess.run([sys.executable, os.path.join(CL.ROOT, "calibrate_live.py"), "--final", "--report", missing],
                              capture_output=True, text=True)
    assert done.returncode == 2, done.stdout + done.stderr
    with open(CL.P.LIVE_MODEL_PATH, "rb") as f:
        assert f.read() == before


if __name__ == "__main__":
    test_game_rows_gives_one_positive_and_one_negative_per_sampled_live_frame()
    test_switch_and_recipes()
    test_fit_and_the_two_scorers()
    test_score_gives_bench_compare_its_format()
    test_recipes_are_explicit_and_invalid_ones_are_rejected()
    test_the_short_cut_and_weight_are_arguments()
    test_a_model_against_itself_gives_exact_zeros_and_does_not_confirm()
    test_a_worse_candidate_does_not_confirm()
    test_decide_needs_every_declared_condition_and_the_exact_trees()
    test_final_refuses_without_an_approved_compatible_report_and_keeps_the_model()
    test_final_with_an_approved_report_writes_the_model_and_its_provenance()
    test_final_refuses_when_the_training_code_or_the_order_changed()
    test_a_candidate_against_radio_decides_on_the_43_conditions()
    test_usage_errors_stop_before_any_data()
    test_confirm_trains_on_the_selection_only_and_writes_a_report_final_can_check()
    test_the_cli_exits_with_an_error_and_leaves_the_delivered_model_alone()
    print("ok")
