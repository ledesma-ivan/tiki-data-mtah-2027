"""Checks for confirm_changes (ADR-001), dead_mask_v2 (ADR-007) and the same-bytes guarantees (#6). Run: python test_possession.py"""
import hashlib
import os
import tempfile

import numpy as np

from possession import (CHANGE_FRAMES, MAX_GAP, PITCH, ball_position, confirm_changes, dead_mask, dead_mask_v2,
                        owner_evidence, runs, write_csv)


def check(evidence, n, expected, **kw):
    """evidence: one character per frame, "." for no evidence ("")."""
    got = "".join(confirm_changes(np.array(["" if c == "." else c for c in evidence], dtype=object), n, **kw))
    assert got == expected, f"{evidence!r} n={n} {kw}: got {got!r}, want {expected!r}"


def players(speeds, k=20):
    """players[n, k, 3] from per-frame, per-player speeds (m/s): a scalar or a list per frame."""
    s = np.array([np.full(k, v, float) if np.isscalar(v) else np.asarray(v, float) for v in speeds])
    p = np.zeros(s.shape + (3,))
    p[:, :, 2] = s
    return p


V2 = dict(cut=2.0, window=10, enter=80, stay=70, min_len=20, lead=0, trim=0)


def inside(n):
    return np.full((n, 2), 0.5)


def dead_runs(speeds, ball=None, k=20, **kw):
    p = players(speeds, k)
    return runs(dead_mask_v2(p, inside(len(p)) if ball is None else ball, **{**V2, **kw}))


def window_count(signal, window):
    """Signal frames inside the window of np.convolve(..., mode="same"), counted one by one."""
    left, right = window - 1 - (window - 1) // 2, (window - 1) // 2
    return np.array([signal[max(0, i - left):i + right + 1].sum() for i in range(len(signal))])


def test_label_uses_the_refined_stops_and_the_restart_team():
    """ADR-010: label moves the v2 stops with the model and starts the next live stretch with the restart team."""
    from possession import HALVES, KINDS, N_FRAMES, label, refine
    n = N_FRAMES
    first, last = HALVES[0]
    p = np.zeros((n, 2, 3))
    p[:, 0, :2], p[:, 1, :2] = (0.5, 0.5), (0.4, 0.0)  # H in the middle, A on the sideline (a throw-in taker)
    p[:, :, 2] = 3.0
    p[first + 1000:first + 1300, :, 2] = 0.5  # 12 s with everybody slow: dead_mask_v2 finds a stop
    ball = np.full((n, 2), np.nan)
    ball[first + 1400:, :] = (0.5 + 0.5 / PITCH[0], 0.5)  # after the stop the ball is next to H
    team = np.array(["H", "A"])
    zero = [0] * (len(KINDS) - 1)
    model = {"mode": "planb", "window": 125, "team_radius_cm": 200, "lead": [10] + zero, "trim": [-5] + zero,
             "type": [{"init": 1, "trees": []}] + [{"init": 0, "trees": []}] * (len(KINDS) - 1)}  # always THROW IN
    dead, initial = refine(dead_mask_v2(p, ball), p, ball, team, [(a, b + 1) for a, b in HALVES], model)
    labels = label(p, ball, team, model, {"mode": "rule"})  # the change rule reads the restart team (ADR-014 does not)
    half = slice(first, last + 1)
    assert ((labels[half] == "D") == dead[half]).all()
    end = first + runs(dead[half])[0][1]
    assert initial[end] == "A" and labels[end] == "A"  # the throw-in taker's team, until H's evidence takes over


def test_label_with_the_live_model():
    """ADR-014: in mode rule, label is today's change rule frame by frame; with a model, the decoder labels every
    live stretch, and the restart team does not start it."""
    from possession import (CONTROL_RADIUS, HALVES, KICKOFFS, KINDS, LIVE_FEATURES, MAX_INTERP, N_FRAMES, before_kickoff,
                            label, refine)
    n = N_FRAMES
    first, last = HALVES[0]
    p = np.zeros((n, 2, 3))
    p[:, 0, :2], p[:, 1, :2] = (0.5, 0.5), (0.4, 0.0)
    p[:, :, 2] = 3.0
    p[first + 1000:first + 1300, :, 2] = 0.5
    ball = np.full((n, 2), np.nan)
    ball[first + 1400:, :] = (0.5 + 0.5 / PITCH[0], 0.5)
    team = np.array(["H", "A"])
    zero = [0] * (len(KINDS) - 1)
    model = {"mode": "planb", "window": 125, "team_radius_cm": 200, "lead": [10] + zero, "trim": [-5] + zero,
             "type": [{"init": 1, "trees": []}] + [{"init": 0, "trees": []}] * (len(KINDS) - 1)}
    spans = [(a, b + 1) for a, b in HALVES]
    dead, initial = refine(dead_mask_v2(p, ball), p, ball, team, spans, model)
    second, kick = HALVES[1][0], KICKOFFS[1]
    assert not dead[second:kick].any()  # players running and the ball in sight: the detector finds no stop there
    dead = before_kickoff(dead)  # ADR-032: but the second half has not kicked off yet
    evidence = owner_evidence(p, ball, team, CONTROL_RADIUS, MAX_INTERP)
    want = np.full(n, "X", dtype=object)
    for a, b in spans:
        want[a:b] = np.where(dead[a:b], "D", "X")
        for s, e in runs(~dead[a:b]):
            want[a + s:a + e] = confirm_changes(evidence[a + s:a + e], CHANGE_FRAMES, initial=initial[a + s])
    rule = label(p, ball, team, model, {"mode": "rule"})
    assert (rule == want).all()
    near = {"feature": np.array([LIVE_FEATURES.index("own_nearest"), -1, -1]), "threshold": np.array([100, 0, 0]),
            "left": np.array([1, 0, 0]), "right": np.array([2, 0, 0]), "value": np.array([0, 1_000_000, -1_000_000])}
    live = {"mode": "model", "switch": 10_000_000, "trees": {"init": 0, "trees": [near]}}
    got = label(p, ball, team, model, live)
    half = slice(first, last + 1)
    end = first + runs(dead[half])[0][1]
    assert ((got[half] == "D") == dead[half]).all() and (got[~np.isin(got, ("D", "X"))] == "H").all()
    assert rule[end] == "A" and got[end] == "H" and (got == "X").sum() == (want == "X").sum()
    assert (rule[second:kick] == "D").all() and (got[second:kick] == "D").all() and got[kick] == "H"


if __name__ == "__main__":
    # Short burst of the rival (2 < n=3) is ignored; the long run is backdated to its first frame.
    check("HHHHAAHHHAAAAA", 3, "HHHHHHHHHAAAAA")
    # Run of exactly n confirms.
    check("HHAAA", 3, "HHAAA")
    # Starts with whoever the evidence names first.
    check("AAAHA", 3, "AAAAA")
    # Several changes in one stretch.
    check("HHHAAAHHH", 3, "HHHAAAHHH")
    # The restart team (ADR-010, #34) starts the stretch: the rival still needs n frames to take over...
    check("..AAA.", 3, "HHAAAA", initial="H")
    # ...and a shorter rival burst leaves the ball with the restart team.
    check("AA.HHH", 3, "HHHHHH", initial="H")
    # No restart team: whoever the evidence names first, as before.
    check("AA.HHH", 3, "AAAHHH", initial="")

    # n is time (#31): frames since the rival's first frame, gaps included. A gap of up to max_gap
    # frames keeps the rival run alive...
    check("HHA..AHH", 4, "HHAAAAAA", max_gap=2)
    # ...one frame more cuts it, and the run starts again after the gap.
    check("HHA...AAAA", 4, "HHHHHHAAAA", max_gap=2)
    # Fewer than n rival frames spread over n frames confirm once n frames have passed...
    check("HHA.A.AHHHH", 4, "HHAAAAAHHHH", max_gap=1)
    # ...and not before.
    check("HHA.AHHHH", 4, "HHHHHHHHH", max_gap=1)
    # Silence after a rival touch confirms nothing: a run is confirmed on a rival frame.
    check("HHA..", 3, "HHHHH", max_gap=2)
    # The holder still cuts the rival run.
    check("HHA.HA.HH", 4, "HHHHHHHHH", max_gap=2)
    # No evidence at all: unchanged.
    check(".....", 3, "HHHHH", max_gap=1)

    # A stoppage (everybody slow) between two stretches of play is one D run; its edges, the whistle and
    # the restart, land within half a window of the speed change.
    (start, end), = dead_runs([4.0] * 100 + [0.5] * 100 + [4.0] * 100)
    assert abs(start - 100) <= 5 and abs(end - 200) <= 5, (start, end)
    # Play with everybody running is never D, and a ball gap cannot trigger it: a missing ball never counts.
    assert dead_runs([4.0] * 300) == []
    gap = inside(300)
    gap[100:200] = np.nan
    assert dead_runs([4.0] * 300, ball=gap) == []
    # The ball seen off the pitch for 60 frames is D even with the players running; for 20 frames it is not.
    out = inside(300)
    out[100:160, 0] = 1.02
    (start, end), = dead_runs([4.0] * 300, ball=out)
    assert abs(start - 100) <= 2 and abs(end - 160) <= 2, (start, end)
    out = inside(300)
    out[100:120, 0] = 1.02
    assert dead_runs([4.0] * 300, ball=out) == []
    # A slow stretch shorter than min_len is not a stoppage.
    assert dead_runs([4.0] * 100 + [0.5] * 15 + [4.0] * 100) == []
    # Hysteresis: 5 of 20 players picking up speed for a moment (75%, between stay and enter) does not
    # split the stoppage; without hysteresis it does.
    dip = [0.5] * 80 + [[4.0] * 5 + [0.5] * 15] * 10 + [0.5] * 80
    assert len(dead_runs([4.0] * 100 + dip + [4.0] * 100)) == 1
    assert len(dead_runs([4.0] * 100 + dip + [4.0] * 100, stay=80)) == 2
    # The share is compared with integers: exactly 80% slow enters at enter=80 and not at 81.
    eight_of_ten = [[0.5] * 8 + [4.0] * 2] * 100
    assert len(dead_runs([4.0] * 50 + eight_of_ten + [4.0] * 50, k=10)) == 1
    assert dead_runs([4.0] * 50 + eight_of_ten + [4.0] * 50, k=10, enter=81) == []
    # lead and trim move each stoppage: its start earlier and its end earlier; one shorter than the
    # trim plus the lead disappears.
    (s0, e0), = dead_runs([4.0] * 100 + [0.5] * 100 + [4.0] * 100)
    assert dead_runs([4.0] * 100 + [0.5] * 100 + [4.0] * 100, lead=25, trim=38) == [(s0 - 25, e0 - 38)]
    assert dead_runs([4.0] * 100 + [0.5] * 30 + [4.0] * 100, lead=0, trim=38) == []
    # Untracked slots (NaN) do not count; a frame with nobody tracked is not dead.
    half_tracked = [[0.5] * 10 + [np.nan] * 10] * 100
    assert len(dead_runs([4.0] * 50 + half_tracked + [4.0] * 50)) == 1
    assert dead_runs([[np.nan] * 20] * 200) == []

    # LF on every OS, so the sha256 does not depend on the machine (#6).
    path = os.path.join(tempfile.mkdtemp(), "output", "possession.csv")
    digest = write_csv(np.array(["X", "H", "D"], dtype=object), path)
    with open(path, "rb") as f:
        data = f.read()
    assert data == b"frame,label\n0,X\n1,H\n2,D\n", data
    assert digest == hashlib.sha256(data).hexdigest()

    # Dead ball from an exact count: a window right at threshold * window is dead (#6).
    rng = np.random.default_rng(0)
    n, ties = 600, 0
    players = np.zeros((n, 2, 3))
    players[:, :, 2] = 5.0  # fast players: only the missing ball signals
    for window in (25, 50, 100):
        for thr in (0.3, 0.5, 0.7):
            missing = rng.random(n) < thr
            ball = np.where(missing[:, None], np.nan, np.full((n, 2), 0.5))
            count = window_count(missing.astype(int), window)
            ties += int((count == thr * window).sum())
            assert (dead_mask(players, ball, window, 1, thr) == (count >= thr * window)).all(), (window, thr)
    assert ties > 0, "no window landed exactly on the threshold"

    # Nearest player by squared distance; an exact tie goes to the first slot (#6).
    players = np.array([[[0.5, 0.6, 0.0], [0.5, 0.4, 0.0], [0.9, 0.9, 0.0]]])
    assert owner_evidence(players, np.array([[0.5, 0.5, 0.0]]), np.array(["H", "A", "H"]))[0] == "H"

    # Control radius and bounded interpolation (ADR-009, #33). Metres in, normalised out.
    def world(ball_m, player_m):
        """players[n, k, 3] and ball[n, 2] from per-frame positions in metres (ball_m: [n, 2], player_m: [n, k, 2])."""
        p = np.zeros(player_m.shape[:2] + (3,))
        p[:, :, 0], p[:, :, 1] = player_m[:, :, 0] / PITCH[0], player_m[:, :, 1] / PITCH[1]
        return p, ball_m / np.array(PITCH)

    teams = np.array(["H", "H", "A"])
    still = lambda n, *xy: np.broadcast_to(np.array(xy, float).reshape(-1, 2), (n, len(xy) // 2, 2)).copy()
    # Nearest player 3 m away: evidence at radius 5, none at radius 1; the default radius is ADR-001.
    p, b = world(np.full((4, 2), 50.0), still(4, 53, 50, 60, 50, 70, 50))
    assert list(owner_evidence(p, b, teams)) == ["H"] * 4
    assert list(owner_evidence(p, b, teams, radius=5)) == ["H"] * 4
    assert list(owner_evidence(p, b, teams, radius=1)) == [""] * 4
    assert list(owner_evidence(p, b, teams, radius=3.01)) == ["H"] * 4  # just inside the radius
    assert list(owner_evidence(p, b, teams, radius=2.99)) == [""] * 4  # just outside

    # A long pass between teammates (H at 10 m and 60 m) that goes by a rival at 35 m: the rival is the nearest
    # player for a few frames, but it never confirms a change.
    n = 40
    ball_m = np.stack([np.linspace(10, 60, n), np.full(n, 34.0)], axis=1)
    mates = np.array([[10.0, 34.0], [60.0, 34.0], [35.0, 35.5]])
    p, b = world(ball_m, np.broadcast_to(mates, (n, 3, 2)).copy())
    held = lambda ev: "".join(confirm_changes(np.array(["H" if e == "H" else "A" if e == "A" else "" for e in ev], dtype=object), 8, max_gap=3))
    # Without the radius the rival is the nearest for the whole middle of the pass: possession flips.
    assert "A" in held(owner_evidence(p, b, teams))
    # With a 2 m radius the rival is evidence for 3 frames only: nothing changes.
    assert set(held(owner_evidence(p, b, teams, radius=2))) == {"H"}

    # The rule with the real parameters (ADR-009): CHANGE_FRAMES = 12 and MAX_GAP = 100. Two rival frames with silence
    # in between confirm a change dated at the first of them; one gap frame longer than MAX_GAP starts a new run.
    real = lambda ev: "".join(confirm_changes(np.array(["" if c == "." else c for c in ev], dtype=object),
                                              CHANGE_FRAMES, MAX_GAP))
    ev = "H" * 5 + "A" + "." * (CHANGE_FRAMES - 2) + "A" + "H" * 3
    assert real(ev) == "H" * 5 + "A" * (CHANGE_FRAMES + 3), real(ev)
    assert real("H" * 5 + "A" + "." * (MAX_GAP + 1) + "A" + "H" * 3) == "H" * (MAX_GAP + 11)  # one frame more cuts the run
    assert real("H" * 5 + "A" + "." * MAX_GAP + "A" + "A" * (CHANGE_FRAMES - 1)) == "H" * 5 + "A" * (MAX_GAP + CHANGE_FRAMES + 1)

    # A steal: the rival keeps the ball for good, and the change is dated at its first frame.
    n = 40
    ball_m = np.full((n, 2), 20.0)
    ball_m[20:] = 40.0
    p, b = world(ball_m, np.broadcast_to(np.array([[20.5, 20.0], [70.0, 10.0], [40.5, 40.0]]), (n, 3, 2)).copy())
    got = held(owner_evidence(p, b, teams, radius=2))
    assert got == "H" * 20 + "A" * 20, got

    # A gap longer than max_interp has no evidence; a shorter one is a straight line between the two seen positions.
    n = 30
    ball_m = np.stack([np.linspace(10, 40, n), np.full(n, 20.0)], axis=1)
    ball_m[10:20] = np.nan  # a 10 frame gap
    p, _ = world(np.nan_to_num(ball_m), np.broadcast_to(np.array([[25.0, 20.0], [90.0, 60.0], [95.0, 60.0]]), (n, 3, 2)).copy())
    b = ball_m / np.array(PITCH)
    assert list(owner_evidence(p, b, teams, radius=3, max_interp=10)[10:20]).count("H") == 6  # frames 12-17: the ball within 3 m of x = 25
    assert list(owner_evidence(p, b, teams, radius=3, max_interp=9)[10:20]) == [""] * 10
    xy = ball_position(b, max_interp=10)
    assert np.allclose(xy[10:20, 0] * PITCH[0], np.linspace(10, 40, n)[10:20])  # on the original line
    # With no cap the ball stays where it was last seen (ADR-001).
    assert np.allclose(ball_position(b)[10:20], b[9, :2])
    # Gaps at the start or the end have nothing to interpolate from.
    edge = b.copy()
    edge[:3], edge[-3:] = np.nan, np.nan
    xy = ball_position(edge, max_interp=100)
    assert np.isnan(xy[:3]).all() and np.isnan(xy[-3:]).all()
    test_label_uses_the_refined_stops_and_the_restart_team()
    test_label_with_the_live_model()
    print("ok")
