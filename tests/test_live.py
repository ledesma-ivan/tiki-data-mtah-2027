"""Checks for the live-play possession model of ADR-014 (#49, #35): signals, decoder and model file. Run: python test_live.py"""
import itertools
import json
import os
import tempfile

import numpy as np

from possession import FPS, LIVE_FEATURES, UNKNOWN, decode_live, live_features, load_live_model, owner_evidence

PITCH = (105.0, 68.0)


def col(name):
    return LIVE_FEATURES.index(name)


def scene(n=300, seed=0):
    """Two players per team walking at random, a ball with gaps, the radio evidence and a stop in the middle."""
    rng = np.random.default_rng(seed)
    players = np.zeros((n, 4, 3))
    players[:, :, 0] = np.clip(np.cumsum(rng.normal(0, 0.002, (n, 4)), axis=0) + [0.2, 0.4, 0.6, 0.8], 0, 1)
    players[:, :, 1] = np.clip(np.cumsum(rng.normal(0, 0.002, (n, 4)), axis=0) + 0.5, 0, 1)
    players[:, :, 2] = rng.uniform(0, 5, (n, 4))
    ball = np.clip(np.cumsum(rng.normal(0, 0.004, (n, 2)), axis=0) + 0.5, 0, 1)
    ball[rng.random(n) < 0.3] = np.nan
    team = np.array(["H", "H", "A", "A"])
    dead = np.zeros(n, bool)
    dead[120:140] = True
    return players, ball, team, dead


def static(points, n=60, ball=(40.5, 34.0)):
    """players[n, k, 3] standing still at points (metres), and the ball at `ball` (metres)."""
    players = np.zeros((n, len(points), 3))
    for j, (x, y) in enumerate(points):
        players[:, j, :2] = x / PITCH[0], y / PITCH[1]
    b = np.tile([ball[0] / PITCH[0], ball[1] / PITCH[1]], (n, 1))
    return players, b


def swap(team):
    return np.where(team == "H", "A", "H")


def test_live_features_are_integers_and_swap_with_the_teams():
    players, ball, team, dead = scene()
    spans = [(0, 200), (210, 300)]
    ev = owner_evidence(players, ball, team, 1.0, 2 * FPS)
    FH, FA = live_features(players, ball, team, ev, dead, spans, PITCH)
    assert FH.dtype == np.int64 and FA.dtype == np.int64
    assert FH.shape == FA.shape == (len(players), len(LIVE_FEATURES)) and len(LIVE_FEATURES) == 49
    ev2 = np.where(ev == "H", "A", np.where(ev == "A", "H", ev)).astype(object)
    GH, GA = live_features(players, ball, swap(team), ev2, dead, spans, PITCH)
    assert (GH == FA).all() and (GA == FH).all()  # the model cannot tell which team is the home one
    again = live_features(players, ball, team, ev, dead, spans, PITCH)
    assert (again[0] == FH).all() and (again[1] == FA).all()


def test_live_features_by_hand():
    # H at 10 m and 40 m, A at 60 m and 95 m, the ball at 40.5 m: H defends x = 0 and attacks towards x = 105 m
    players, ball = static([(10, 34), (40, 34), (60, 34), (95, 34)])
    team = np.array(["H", "H", "A", "A"])
    ev = owner_evidence(players, ball, team, 1.0, 2 * FPS)
    FH, FA = live_features(players, ball, team, ev, np.zeros(len(ball), bool), [(0, len(ball))], PITCH)
    t = 30
    assert FH[t, col("own_nearest")] == 50 and FH[t, col("own_second")] == 3050
    assert FH[t, col("rival_nearest")] == 1950 and FH[t, col("rival_second")] == 5450
    assert FH[t, col("own_n_3m")] == 1 and FH[t, col("own_n_10m")] == 1 and FH[t, col("rival_n_10m")] == 0
    assert FH[t, col("own_advance")] == 2500 - 5250 and FA[t, col("own_advance")] == -(7750 - 5250)
    assert FH[t, col("own_ball_advance")] == 4050 - 5250 and FA[t, col("own_ball_advance")] == 5250 - 4050
    assert FH[t, col("own_closing")] == 0 and FH[t, col("own_team_fwd")] == 0  # nobody moves
    assert FH[t, col("own_ev_past_12")] == 12 and FH[t, col("rival_ev_next_125")] == 0  # 1 m from H's player
    assert FH[t, col("own_ev_since")] == 0 and FH[t, col("rival_ev_since")] == 10 * FPS
    assert FH[t, col("ball_seen")] == 1 and FH[t, col("live_since")] == t and FH[t, col("live_until")] == len(ball) - 1 - t


def test_live_features_cap_jumps_and_mark_missing():
    n = 200
    players, ball = static([(40, 34), (10, 34), (60, 34), (95, 34)], n)
    players[50:, 1, 0] = 20 / PITCH[0]  # an H slot jumps 10 m in one frame, as a substitution does in Metrica (#53)
    players[80:100, 2:, :] = np.nan  # nobody of A tracked for 20 frames
    ball[150:, :] = np.nan  # and no ball at the end
    team = np.array(["H", "H", "A", "A"])
    dead = np.zeros(n, bool)
    ev = owner_evidence(players, ball, team, 1.0, 2 * FPS)
    FH, _ = live_features(players, ball, team, ev, dead, [(0, 120), (130, n)], PITCH)
    inside = np.r_[0:120, 130:n]
    assert (FH[inside, col("own_team_fwd")] == 0).all()  # the jump is not a 50 m/s run
    assert (FH[80:100, col("rival_nearest")] == UNKNOWN).all() and (FH[80:100, col("rival_tracked")] == 0).all()
    assert (FH[80:100, col("rival_advance")] == UNKNOWN).all() and (FH[80:100, col("own_nearest")] == 50).all()
    assert (FH[120:130] == UNKNOWN).all()  # halftime: outside the spans
    assert (FH[160:, col("own_nearest")] == UNKNOWN).all() and (FH[160:, col("own_n_3m")] == UNKNOWN).all()
    assert (FH[160:, col("ball_known")] == 0).all() and (FH[160:, col("ball_seen")] == 0).all()


def objective(labels, score, switch):
    return sum(int(v) if lab == "H" else -int(v) for lab, v in zip(labels, score)) - \
        switch * sum(a != b for a, b in zip(labels[1:], labels[:-1]))


def test_decode_live_matches_brute_force():
    rng = np.random.default_rng(1)
    for _ in range(200):
        n = int(rng.integers(1, 11))
        score = rng.integers(-50, 51, n).astype(np.int64)
        switch = int(rng.integers(0, 121))
        got = list(decode_live(score, switch))
        best = max(objective(seq, score, switch) for seq in itertools.product("HA", repeat=n))
        assert len(got) == n and objective(got, score, switch) == best, (score, switch, got)


def test_decode_live_edges():
    assert len(decode_live(np.zeros(0, np.int64), 10)) == 0
    assert list(decode_live(np.array([-3]), 10)) == ["A"] and list(decode_live(np.array([3]), 10)) == ["H"]
    assert list(decode_live(np.zeros(5, np.int64), 10)) == ["H"] * 5  # ties keep the state, the end tie is H
    assert list(decode_live(np.array([5, -5, 5]), 0)) == ["H", "A", "H"]  # no switch cost: the sign, frame by frame
    assert list(decode_live(np.array([5, -5, 5]), 11)) == ["H"] * 3  # a change costs more than the -5 frame gives
    # a change that ties across frames goes to its earliest frame (backdated, like confirm_changes)
    assert list(decode_live(np.array([-5, 0, 0, 5]), 1)) == ["A", "H", "H", "H"]


TREE = {"feature": [col("own_nearest"), -1, -1], "threshold": [100, 0, 0], "left": [1, 0, 0], "right": [2, 0, 0],
        "value": [0, 1_000_000, -1_000_000]}


def written(text):
    d = tempfile.mkdtemp()
    path = os.path.join(d, "live.json")
    with open(path, "w") as f:
        f.write(text)
    return path


def test_load_live_model():
    assert load_live_model(written('{"mode": "rule"}')) == {"mode": "rule"}
    m = load_live_model(written(json.dumps({"mode": "model", "switch": 40_000_000, "trees": {"init": 0, "trees": [TREE]}})))
    assert m["mode"] == "model" and m["switch"] == 40_000_000
    assert m["trees"]["trees"][0]["feature"].dtype == np.int64
    try:
        load_live_model("no-such-live-model.json")
    except FileNotFoundError as e:
        assert "no-such-live-model.json" in str(e)
    else:
        raise AssertionError("a missing live model must stop the pipeline")


def test_load_live_model_rejects_broken_files():
    """A broken live model stops the pipeline with its path (plan, Review Focus 5)."""
    good = {"mode": "model", "switch": 0, "trees": {"init": 0, "trees": [TREE]}}
    past = {**TREE, "feature": [len(LIVE_FEATURES), -1, -1]}
    looping = {**TREE, "left": [0, 0, 0]}
    broken = {"empty": "", "unknown mode": json.dumps({**good, "mode": "Rule"}),
              "float switch": json.dumps({**good, "switch": 1.5}), "negative switch": json.dumps({**good, "switch": -1}),
              "boolean switch": json.dumps({**good, "switch": True}), "no trees": json.dumps({"mode": "model", "switch": 0}),
              "tree past the features": json.dumps({**good, "trees": {"init": 0, "trees": [past]}}),
              "tree that loops": json.dumps({**good, "trees": {"init": 0, "trees": [looping]}})}
    for name, text in broken.items():
        path = written(text)
        try:
            load_live_model(path)
        except ValueError as e:
            assert path in str(e), (name, e)
        else:
            raise AssertionError(f"{name}: a broken live model must stop the pipeline")


if __name__ == "__main__":
    test_live_features_are_integers_and_swap_with_the_teams()
    test_live_features_by_hand()
    test_live_features_cap_jumps_and_mark_missing()
    test_decode_live_matches_brute_force()
    test_decode_live_edges()
    test_load_live_model()
    test_load_live_model_rejects_broken_files()
    print("ok")
