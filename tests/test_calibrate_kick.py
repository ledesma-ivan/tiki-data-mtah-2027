"""Checks for calibrate_kick.py (ADR-017) on synthetic data. Run: python -m tests.test_calibrate_kick (needs requirements-train.txt)"""
import json
import os
import tempfile

import numpy as np

import calibrate_kick as CK
from possession import FPS, load_model
from tests.test_calibrate_live import game


def test_recipes_are_valid_kick_models():
    r = CK.recipes()
    assert len(r) == 18
    assert {m["rest"] for m in r.values()} == {FPS // 2, FPS, 3 * FPS // 2}
    assert {m["before"] for m in r.values()} == {2 * FPS, 3 * FPS} and {m["after"] for m in r.values()} == {3 * FPS, 5 * FPS, 8 * FPS}
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "m.json")
        for model in r.values():
            with open(path, "w") as f:
                json.dump(model, f)
            assert load_model(path) == model


def test_score_gives_bench_compare_its_format():
    g = game()
    zero = lambda F: np.zeros(len(F), np.int64)  # noqa: E731  a live model with no opinion
    name, recipe = next(iter(CK.recipes().items()))
    preds = CK.score([g], {"main": zero}, 10_000_000, [0], {name: recipe}, anchors={"start"})
    assert set(preds) == {(2, "start", "degraded", k) for k in ("main", name)}
    truth, labels = preds[(2, "start", "degraded", name)]
    assert len(labels) == 1 and len(labels[0]) == len(truth) and set(labels[0]) <= {"H", "A", "D", "X"}


if __name__ == "__main__":
    test_recipes_are_valid_kick_models()
    test_score_gives_bench_compare_its_format()
    print("ok")
