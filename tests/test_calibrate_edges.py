"""Checks for calibrate_edges.py (ADR-010) on synthetic data. Skipped without scikit-learn (requirements-train.txt).
Run: python test_calibrate_edges.py"""
import sys

import numpy as np

try:
    from sklearn.ensemble import HistGradientBoostingClassifier
except ImportError:
    print("skipped: scikit-learn is not installed (pip install -r requirements-train.txt)")
    sys.exit(0)

from calibrate_edges import SCALE, export, export_kinds, match_kinds, plan_b  # noqa: E402
from possession import KINDS, UNKNOWN, classify, tree_scores  # noqa: E402


def data(n=3000, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.integers(-300, 300, (n, 4)).astype(np.int64)
    X[rng.random((n, 4)) < 0.1] = UNKNOWN
    return X


def fit(X, y, **kw):
    return HistGradientBoostingClassifier(max_iter=30, max_leaf_nodes=7, random_state=0, early_stopping=False, **kw).fit(X, y)


def test_export_gives_the_decisions_of_sklearn():
    X = data()
    y = np.where(X[:, 0] == UNKNOWN, 0, X[:, 0]) + X[:, 1] // 2 > 40
    clf = fit(X, y)
    s, raw = tree_scores(X, export(clf)), clf.decision_function(X)
    assert s.dtype == np.int64 and np.abs(s / SCALE - raw).max() < 1e-4
    sure = np.abs(raw) > 1e-4
    assert ((s > 0) == (raw > 0))[sure].all()


def test_export_kinds_keeps_absent_kinds_out():
    X = data()
    y = np.where(X[:, 0] > 100, 4, np.where(X[:, 1] > 0, 2, 0))  # only THROW IN, GOAL KICK and KICK OFF
    clf = fit(X, y)
    parts = export_kinds(clf)
    assert len(parts) == len(KINDS)
    raw = np.sort(clf.decision_function(X), axis=1)
    sure = raw[:, -1] - raw[:, -2] > 1e-4
    assert (classify(X, parts) == clf.predict(X))[sure].all()
    assert set(classify(X, parts).tolist()) <= {0, 2, 4}


def test_plan_b_takes_the_median_offset_of_each_kind():
    # (true start, true end, v2 start, v2 end, kind)
    pairs = [(100, 200, 110, 190, 0), (300, 400, 306, 380, 0), (500, 600, 503, 590, 0), (700, 800, 690, 810, 3)]
    lead, trim = plan_b(pairs)
    assert len(lead) == len(trim) == len(KINDS)
    assert (lead[0], trim[0], lead[3], trim[3], lead[1], trim[1]) == (6, -10, -10, 10, 0, 0)


def test_match_kinds_takes_the_nearest_restart_within_the_tolerance():
    stops = [(10, 100), (200, 300), (400, 500)]
    throw, corner, free = (KINDS.index(k) for k in ("THROW IN", "CORNER KICK", "FREE KICK"))
    restarts = [(102, throw), (290, corner), (310, free), (700, free)]
    assert match_kinds(stops, restarts, tolerance=50) == [(10, 100, throw), (200, 300, corner), (400, 500, -1)]


if __name__ == "__main__":
    test_export_gives_the_decisions_of_sklearn()
    test_export_kinds_keeps_absent_kinds_out()
    test_plan_b_takes_the_median_offset_of_each_kind()
    test_match_kinds_takes_the_nearest_restart_within_the_tolerance()
    print("ok")
