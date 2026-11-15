"""Checks for the stop edges and the restart team (ADR-010, #32 and #34) on synthetic data. Run: python test_stops.py"""
import json
import os
import tempfile

import numpy as np

from possession import (EDGE_FEATURES, FPS, FRAME_FEATURES, KINDS, PITCH, STOP_FEATURES, UNKNOWN, ball_position,
                        classify, fit_step, frame_features, kick_onsets, load_model, refine, restart_team, snap_ends,
                        stop_features, tree_scores, window_rows)


def tree(feature, threshold, left, right, value):
    return {k: np.array(v, np.int64) for k, v in
            dict(feature=feature, threshold=threshold, left=left, right=right, value=value).items()}


def test_tree_by_hand():
    # root: f0 <= 5 -> leaf 10; else f1 <= -1 -> leaf 20, else leaf 30
    part = {"init": 1, "trees": [tree([0, -1, 1, -1, -1], [5, 0, -1, 0, 0], [1, 0, 3, 0, 0], [2, 0, 4, 0, 0],
                                      [0, 10, 0, 20, 30])]}
    X = np.array([[5, 0], [6, -1], [6, 0], [UNKNOWN, 7]], np.int64)
    s = tree_scores(X, part)
    assert s.dtype == np.int64 and s.tolist() == [11, 21, 31, 11], s
    assert tree_scores(X, {"init": 1, "trees": [part["trees"][0]] * 2}).tolist() == [21, 41, 61, 21]


def test_fit_step():
    f, t = False, True
    assert fit_step(np.array([f, f, t, t]), rising=True) == 2
    assert fit_step(np.array([t, t, f, f]), rising=False) == 2
    assert fit_step(np.array([f, t, f, t]), rising=True) == 1  # tie between 1 and 3: the earliest
    assert fit_step(np.array([f, f, f]), rising=True) == 3  # all live: the stop starts after the window
    assert fit_step(np.array([t, t, t]), rising=True) == 0
    assert fit_step(np.array([f, f, f]), rising=False) == 0  # all live: the stop ends before the window
    assert fit_step(np.array([t, t, t]), rising=False) == 3
    assert fit_step(np.array([], bool), rising=True) == 0


def synthetic(n=200, k=4):
    players = np.full((n, k, 3), np.nan)
    players[:, :, 0] = np.linspace(0.2, 0.8, k)
    players[:, :, 1] = 0.5
    players[:, :, 2] = 2.0  # m/s: none slow (< 1.75), none fast (>= 4)
    ball = np.full((n, 2), np.nan)
    ball[:, 0] = players[0, 0, 0] + 3 / PITCH[0]  # 3 m from the first player
    ball[:, 1] = 0.5
    return players, ball


def col(name):
    return FRAME_FEATURES.index(name)


def test_frame_features():
    players, ball = synthetic()
    F = frame_features(players, ball)
    assert F.dtype == np.int64 and F.shape == (len(ball), len(FRAME_FEATURES))
    assert (F == frame_features(players, ball)).all()
    i = 100
    assert F[i, col("n_tracked")] == 4 and F[i, col("slow_pct")] == 0 and F[i, col("n_fast")] == 0
    assert F[i, col("mean_speed")] == 200 and F[i, col("mean_speed_3s")] == 200 and F[i, col("speed_change_1s")] == 0
    assert F[i, col("ball_seen")] == 1 and F[i, col("ball_unseen")] == 0 and F[i, col("ball_speed")] == 0
    assert F[i, col("ball_nearest")] == 300 and F[i, col("ball_nearest_speed")] == 200 and F[i, col("ball_off")] == 0
    assert F[i, col("ball_line")] == round(ball[i, 0] * PITCH[0] * 100)  # 24 m to the goal line, 34 m to the sideline

    # no ball at all: seen 0, unseen capped, every position signal unknown
    F = frame_features(players, np.full_like(ball, np.nan))
    assert F[i, col("ball_seen")] == 0 and F[i, col("ball_unseen")] == 250 and F[i, col("ball_known")] == 0
    for name in ("ball_speed", "ball_off", "ball_line", "ball_nearest", "ball_nearest_speed"):
        assert F[i, col(name)] == UNKNOWN, name

    # nobody tracked: the player signals are unknown, the count is 0
    F = frame_features(np.full_like(players, np.nan), ball)
    assert F[i, col("n_tracked")] == 0
    for name in ("slow_pct", "mean_speed", "max_speed", "slow_pct_1s", "mean_speed_3s", "speed_change_1s",
                 "ball_nearest", "ball_nearest_speed"):
        assert F[i, col(name)] == UNKNOWN, name


def test_frame_features_see_players_stopping():
    players, ball = synthetic()
    players[100:, :, 2] = 0.5  # everybody slow from frame 100
    F = frame_features(players, ball)
    assert F[99, col("slow_pct")] == 0 and F[100, col("slow_pct")] == 100
    assert F[100, col("speed_change_1s")] == 50 - 200  # next second minus the previous one
    assert F[100, col("slow_change_1s")] == 100


def test_window_rows():
    F = np.arange(30, dtype=np.int64).reshape(10, 3)
    R = window_rows(F, 2, 6, edge=4, side=1, stop_len=50, kind=3)
    assert R.dtype == np.int64 and R.shape == (4, 3 + 4)
    assert (R[:, :3] == F[2:6]).all()
    assert R[:, 3].tolist() == [-2, -1, 0, 1] and (R[:, 4] == 1).all() and (R[:, 5] == 50).all() and (R[:, 6] == 3).all()


def at(x_m, y_m):
    """Normalised position from metres."""
    return x_m / PITCH[0], y_m / PITCH[1]


def scene(points, n=10):
    """players[n, k, 3] standing still at the (x, y) metre points, speed 0.5 m/s."""
    players = np.zeros((n, len(points), 3))
    for j, p in enumerate(points):
        players[:, j, :2] = at(*p)
    players[:, :, 2] = 0.5
    return players


def no_ball(n=10):
    return np.full((n, 2), np.nan)


def test_restart_team():
    team = np.array(["H", "A", "A"])
    players = scene([(30, 20), (35, 20), (60, 40)])
    ball = no_ball()
    ball[:, :] = at(30.5, 20)
    xy = ball_position(ball)
    assert restart_team(players, xy, team, 5, KINDS.index("FREE KICK"), 200) == "H"  # 0.5 m from the ball
    assert restart_team(players, xy, team, 5, KINDS.index("FREE KICK"), 30) == ""  # nobody within 0.3 m
    xy = ball_position(no_ball())
    assert restart_team(players, xy, team, 5, KINDS.index("FREE KICK"), 200) == ""  # no ball, no place to look
    sideline = scene([(30, 20), (50, -0.3), (60, 40)])  # A throws in from just outside the line
    assert restart_team(sideline, xy, team, 5, KINDS.index("THROW IN"), 200) == "A"
    corner = scene([(104.8, 67.7), (100, 60), (90, 34)])
    assert restart_team(corner, xy, team, 5, KINDS.index("CORNER KICK"), 200) == "H"
    goal_kick = scene([(80, 30), (90, 30), (102.5, 34)])  # the keeper in the goal area
    assert restart_team(goal_kick, xy, team, 5, KINDS.index("GOAL KICK"), 200) == "A"
    kick_off = scene([(52.6, 34.2), (60, 34), (40, 20)])
    assert restart_team(kick_off, xy, team, 5, KINDS.index("KICK OFF"), 200) == "H"
    assert restart_team(scene([(40, 34), (60, 34), (70, 20)]), xy, team, 5, KINDS.index("KICK OFF"), 200) == ""


def test_stop_features_of_a_kick_off():
    team = np.array(["H"] * 3 + ["A"] * 3)
    players = scene([(51.5, 34), (45, 20), (30, 50), (62, 34), (70, 10), (80, 60)], n=60)
    s = stop_features(players, ball_position(no_ball(60)), team, 0, 60)
    assert s.dtype == np.int64 and s.shape == (len(STOP_FEATURES),)
    v = dict(zip(STOP_FEATURES, s.tolist()))
    assert v["own_half_pct"] == 100 and v["n_near_center"] == 1 and v["min_center"] == 115  # 1.15 m from the spot
    assert v["ball_known"] == 0 and v["ball_center"] == UNKNOWN and v["stop_len"] == 60
    assert v["min_sideline"] == 800 and v["n_in_boxes"] == 0  # the A player at y = 60 m is 8 m from the sideline


def leaf_only(value):
    return {"init": value, "trees": []}


def test_classify_takes_the_first_best_class():
    parts = [leaf_only(v) for v in (0, 5, 2, 5, 1, 0)]
    assert classify(np.zeros((2, len(STOP_FEATURES)), np.int64), parts).tolist() == [1, 1]


SIDE, OFFSET = EDGE_FEATURES.index("side"), EDGE_FEATURES.index("offset")
# start window (side 0): D from offset -20 on; end window (side 1): D up to offset -31
EDGE = {"init": 0, "trees": [tree([SIDE, OFFSET, OFFSET, -1, -1, -1, -1], [0, -21, -31, 0, 0, 0, 0],
                                  [1, 3, 5, 0, 0, 0, 0], [2, 4, 6, 0, 0, 0, 0], [0, 0, 0, -1, 1, 1, -1])]}
TYPE = [leaf_only(1)] + [leaf_only(0)] * (len(KINDS) - 1)  # always the first kind


def walk(n=400):
    players = np.zeros((n, 2, 3))
    players[:, 0, :2], players[:, 1, :2] = at(30, 30), at(70, 30)
    players[:, :, 2] = 3.0
    return players, np.full((n, 2), np.nan), np.array(["H", "A"])


def test_refine_with_the_edge_model():
    players, ball, team = walk()
    dead = np.zeros(400, bool)
    dead[100:200] = True
    model = {"mode": "model", "window": 50, "team_radius_cm": 0, "edge": EDGE, "type": TYPE}
    new, initial = refine(dead, players, ball, team, [(0, 400)], model)
    assert np.flatnonzero(new).tolist() == list(range(80, 170)) and (initial == "").all()


def planb(lead, trim, radius=0):
    return {"mode": "planb", "window": 50, "team_radius_cm": radius, "type": TYPE,
            "lead": [lead] + [0] * (len(KINDS) - 1), "trim": [trim] + [0] * (len(KINDS) - 1)}


def test_refine_with_plan_b():
    players, ball, team = walk()
    dead = np.zeros(400, bool)
    dead[100:200] = True
    new, _ = refine(dead, players, ball, team, [(0, 400)], planb(10, -5))
    assert np.flatnonzero(new).tolist() == list(range(90, 205))


def test_refine_keeps_stops_inside_their_neighbours():
    players, ball, team = walk()
    dead = np.zeros(400, bool)
    dead[0:50] = dead[100:150] = dead[151:200] = dead[300] = True
    new, _ = refine(dead, players, ball, team, [(0, 400)], planb(10, -10))
    # the first stop cannot start before the span; the one-frame live gap closes, and nothing reaches past 400
    assert np.flatnonzero(new).tolist() == list(range(0, 60)) + list(range(90, 210)) + list(range(290, 311))
    new, _ = refine(dead, players, ball, team, [(0, 400)], planb(-5, 5))  # a one-frame stop keeps one frame
    assert new[300] and new[299:302].sum() == 1


def test_refine_names_the_restart_team():
    players, ball, team = walk()
    ball[:, :] = at(70.5, 30)  # next to the A player
    dead = np.zeros(400, bool)
    dead[100:200] = True
    _, initial = refine(dead, players, ball, team, [(0, 400)], planb(0, 0, radius=200))
    assert initial[200] == "A" and (np.delete(initial, 200) == "").all()


def refine_stop_by_stop(dead, players, ball, team, spans, model):
    """The plain version of refine's model mode: one window at a time, the way ADR-010 describes it."""
    from possession import MAX_INTERP, runs
    out = dead.copy()
    xy, F, w = ball_position(ball, MAX_INTERP), frame_features(players, ball), model["window"]
    for a, b in spans:
        stops = [(a + s, a + e) for s, e in runs(dead[a:b])]
        prev_end = a
        for j, (c, d) in enumerate(stops):
            nxt = stops[j + 1][0] if j + 1 < len(stops) else b
            kind = int(classify(stop_features(players, xy, team, c, d)[None], model["type"])[0])
            lo, hi = max(c - w, prev_end), min(c + w, d)
            s = min(lo + fit_step(tree_scores(window_rows(F, lo, hi, c, 0, d - c, kind), model["edge"]) > 0, True), d - 1)
            lo, hi = max(d - w, s + 1), min(d + w, nxt)
            e = lo + fit_step(tree_scores(window_rows(F, lo, hi, d, 1, d - c, kind), model["edge"]) > 0, False)
            out[c:d] = False
            out[s:e] = True
            prev_end = e
    return out


def test_refine_matches_the_stop_by_stop_version():
    players, ball, team = walk(3000)
    rng = np.random.default_rng(7)
    players[:, :, 2] = rng.uniform(0, 4, (3000, 2))  # speeds that change, so the features do
    model = {"mode": "model", "window": 40, "team_radius_cm": 0, "type": TYPE,
             "edge": {"init": 0, "trees": [tree([OFFSET, EDGE_FEATURES.index("mean_speed"), -1, -1, -1], [-3, 150, 0, 0, 0],
                                                [1, 3, 0, 0, 0], [2, 4, 0, 0, 0], [0, 0, 1, 1, -1])]}}
    for seed in range(20):
        dead = np.random.default_rng(seed).random(3000) < 0.5
        dead = np.repeat(dead[::30], 30)[:3000]  # stops and gaps of 30 frames or more
        dead[np.random.default_rng(seed + 100).integers(0, 3000, 40)] ^= True  # and some of one frame
        spans = [(0, 1200), (1500, 3000)]
        got, _ = refine(dead, players, ball, team, spans, model)
        assert (got == refine_stop_by_stop(dead, players, ball, team, spans, model)).all(), seed


def test_identity_model_leaves_the_v2_stops_and_names_nobody():
    from calibrate_edges import identity_model
    players, ball, team = walk()
    ball[:, :] = at(70.5, 30)
    dead = np.zeros(400, bool)
    dead[0:50] = dead[100:150] = dead[151:200] = dead[300] = True
    new, initial = refine(dead, players, ball, team, [(0, 400)], identity_model())
    assert (new == dead).all() and (initial == "").all()


KICK = {"mode": "kick", "before": 50, "after": 75, "kick_cms": 400, "rest": 25, "rest_cms": 200}


def ball_from_steps(steps_ms, x0=50.0):
    """A ball along y = 34 m whose step from frame t to t + 1 moves steps_ms[t] m/s."""
    x = x0 + np.r_[0, np.cumsum(np.asarray(steps_ms, float) / FPS)]
    ball = np.full((len(x), 2), np.nan)
    ball[:, 0], ball[:, 1] = x / PITCH[0], 34 / PITCH[1]
    return ball


def rolling(n, rest_until, speed_ms):
    """At rest until frame rest_until, then speed_ms m/s."""
    return ball_from_steps([0.0] * rest_until + [speed_ms] * (n - 1 - rest_until))


def test_kick_onsets():
    ball = rolling(100, 40, 4.0)  # 16 cm a frame from frame 40: exactly 4 m/s
    assert kick_onsets(ball, 400, 25, 200).tolist() == [40]
    assert kick_onsets(ball, 401, 25, 200).tolist() == []  # just under the kick speed
    assert kick_onsets(ball, 400, 40, 200).tolist() == [40] and kick_onsets(ball, 400, 41, 200).tolist() == []
    assert kick_onsets(ball, 400, 0, 200).tolist() == [40]  # rest 0: any kick
    gap = ball.copy()
    gap[30] = np.nan  # a missing ball is never at rest
    assert kick_onsets(gap, 400, 25, 200).tolist() == []
    gap = ball.copy()
    gap[42] = np.nan  # nor fast: the kick needs KICK_RUN fast steps in a row, and after the gap the ball was not at rest
    assert kick_onsets(gap, 400, 25, 200).tolist() == [] and kick_onsets(gap, 400, 0, 200).tolist() == [43]
    assert kick_onsets(rolling(100, 40, 1.9), 400, 25, 200).tolist() == []  # a carried ball is no kick


def test_snap_ends_moves_each_end_to_its_kick():
    dead = np.zeros(400, bool)
    dead[100:200] = True
    later = rolling(400, 230, 5.0)  # the kick 30 frames after the v2 end
    assert np.flatnonzero(snap_ends(dead, later, [(0, 400)], KICK)).tolist() == list(range(100, 230))
    earlier = rolling(400, 180, 5.0)  # 20 frames before it
    assert np.flatnonzero(snap_ends(dead, earlier, [(0, 400)], KICK)).tolist() == list(range(100, 180))
    for ball in (rolling(400, 300, 5.0), rolling(400, 120, 5.0), np.full((400, 2), np.nan)):
        assert (snap_ends(dead, ball, [(0, 400)], KICK) == dead).all()  # out of the window, or no ball: it stays
    assert (snap_ends(dead, later, [(0, 210)], KICK) == dead).all()  # the half ends before the kick
    two = dead.copy()
    two[220:260] = True  # the next stop starts before the kick, which then ends that one
    assert np.flatnonzero(snap_ends(two, later, [(0, 400)], KICK)).tolist() == list(range(100, 200)) + list(range(220, 230))
    tie = ball_from_steps([0.0] * 190 + [5.0] * 5 + [0.0] * 15 + [5.0] * 189)  # kicks at 190 and at 210
    assert np.flatnonzero(snap_ends(dead, tie, [(0, 400)], {**KICK, "rest": 0})).tolist() == list(range(100, 190))
    assert np.flatnonzero(snap_ends(dead, tie, [(0, 400)], KICK)).tolist() == list(range(100, 190))  # 210: not at rest
    short = np.zeros(400, bool)
    short[178:181] = True  # an end never moves before the stop's second frame
    assert np.flatnonzero(snap_ends(short, rolling(400, 160, 5.0), [(0, 400)], KICK)).tolist() == [178, 179, 180]


def test_refine_in_kick_mode_snaps_the_ends_and_names_nobody():
    players, _, team = walk()
    dead = np.zeros(400, bool)
    dead[100:200] = True
    new, initial = refine(dead, players, rolling(400, 230, 5.0), team, [(0, 400)], KICK)
    assert np.flatnonzero(new).tolist() == list(range(100, 230)) and (initial == "").all()


def test_load_model_rejects_broken_files():
    """A broken stop model stops the pipeline with its path, never runs half right (plan, Review Focus 5)."""
    good = {"mode": "planb", "window": 50, "team_radius_cm": 0, "type": TYPE,
            "lead": [0] * len(KINDS), "trim": [0] * len(KINDS)}
    looping = {"init": 0, "trees": [{"feature": [0, -1], "threshold": [0, 0], "left": [0, 0], "right": [1, 0],
                                     "value": [0, 1]}]}  # node 0 sends x <= 0 back to itself
    broken = {"empty": "", "unknown mode": json.dumps({**good, "mode": "planB"}),
              "three kinds": json.dumps({**good, "type": TYPE[:3]}),
              "short lead": json.dumps({**good, "lead": [0, 0]}),
              "float trim": json.dumps({**good, "trim": [0.5] * len(KINDS)}),
              "no window": json.dumps({**good, "window": 0}),
              "model without edges": json.dumps({**good, "mode": "model"}),
              "tree that loops": json.dumps({**good, "type": [looping] + TYPE[1:]}),
              "kick without rest": json.dumps({k: v for k, v in KICK.items() if k != "rest"}),
              "kick with a float speed": json.dumps({**KICK, "kick_cms": 400.5}),
              "kick with a bool": json.dumps({**KICK, "rest": True}),
              "kick looking back a negative time": json.dumps({**KICK, "before": -1}),
              "kick with no window after the end": json.dumps({**KICK, "after": 0}),
              "kick at no speed": json.dumps({**KICK, "kick_cms": 0})}
    with tempfile.TemporaryDirectory() as d:
        for name, text in broken.items():
            path = os.path.join(d, name.replace(" ", "_") + ".json")
            with open(path, "w") as f:
                f.write(text)
            try:
                load_model(path)
            except ValueError as e:
                assert path in str(e), (name, e)
            else:
                raise AssertionError(f"{name}: a broken model must stop the pipeline")


def test_load_model():
    try:
        load_model("no-such-model.json")
    except FileNotFoundError as e:
        assert "no-such-model.json" in str(e)
    else:
        raise AssertionError("a missing model must stop the pipeline")
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "m.json")
        edge = {"init": 0, "trees": [{f: v.tolist() for f, v in EDGE["trees"][0].items()}]}
        with open(path, "w") as f:
            json.dump({"mode": "model", "window": 50, "team_radius_cm": 0, "edge": edge, "type": TYPE}, f)
        m = load_model(path)
        with open(path, "w") as f:
            json.dump(KICK, f)
        k = load_model(path)
    assert m["edge"]["trees"][0]["feature"].dtype == np.int64 and len(m["type"]) == len(KINDS)
    assert k == KICK


if __name__ == "__main__":
    test_tree_by_hand()
    test_fit_step()
    test_frame_features()
    test_frame_features_see_players_stopping()
    test_window_rows()
    test_restart_team()
    test_stop_features_of_a_kick_off()
    test_classify_takes_the_first_best_class()
    test_refine_with_the_edge_model()
    test_refine_with_plan_b()
    test_refine_keeps_stops_inside_their_neighbours()
    test_refine_names_the_restart_team()
    test_refine_matches_the_stop_by_stop_version()
    test_identity_model_leaves_the_v2_stops_and_names_nobody()
    test_kick_onsets()
    test_snap_ends_moves_each_end_to_its_kick()
    test_refine_in_kick_mode_snaps_the_ends_and_names_nobody()
    test_load_model_rejects_broken_files()
    test_load_model()
    print("ok")
