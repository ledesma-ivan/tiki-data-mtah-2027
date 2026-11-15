"""Control-radius evidence and ball interpolation vs nearest player (exploratory, 28/10).

Usage: python explore/control_radius_2810.py
With the true D, so the evidence is measured alone.
- Part 1, Game 3: the 28/10 sweep. The degraded ball is the flawed 28/10 one
  (explore/oracles_2810.py), drawn from a fresh generator.
- Part 2, Games 1-3: nearest player at N = 2 s vs radius 1 m at N = 0.5 s, ball as is, with the
  official bootstrap, on the bench's loaders and truth (bench.py, ADR-006).
Open data only (AGENTS.md). The joint sweep of R, N and the interpolation cap goes in the bench (#33).
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oracles_2810 as o  # noqa: E402


def interp(b):
    out = b.copy()
    t = np.arange(len(b))
    seen = ~np.isnan(b[:, 0])
    for c in range(2):
        out[:, c] = np.interp(t, t[seen], b[seen, c])
    return out


def evidence(b, radius, fill, players=None, team=None, *, pitch):
    """Team of the nearest player within radius of the ball, "" if nobody; gaps forward-filled or interpolated."""
    players = o.players if players is None else players
    team = o.TEAM if team is None else team
    if fill == "ffill":
        seen = ~np.isnan(b[:, 0])
        bxy = b[np.maximum.accumulate(np.where(seen, np.arange(len(b)), 0)), :2]
    else:
        bxy = interp(b)[:, :2]
    dx = (players[:, :, 0] - bxy[:, None, 0]) * pitch[0]
    dy = (players[:, :, 1] - bxy[:, None, 1]) * pitch[1]
    d = np.where(np.isnan(dx), np.inf, np.hypot(dx, dy))
    ev = np.asarray(team, dtype=object)[d.argmin(1)]
    ev[d.min(1) > radius] = ""
    return ev


def main():
    for name, b in (("Game 3 ball", o.ball), ("degraded ball", o.degrade(o.ball, 0.4, np.random.default_rng(0)))):
        print(f"{name} | true D | spellF1 by N")
        for fill in ("ffill", "interp"):
            for radius in (np.inf, 2.0, 1.0):
                e = evidence(b, radius, fill, pitch=o.pitch)
                cov = np.mean(e[o.live] != "")
                hit = o.live & (e != "")
                acc = np.mean(e[hit] == o.truth_lab[hit])
                res = "  ".join(f"N={nc / o.FPS:.1f}s {o.spell(o.segment(o.dead_true, e, nc))[0]:.3f}" for nc in (12, 25, 50))
                print(f"  {fill:6} R={radius:<4} coverage {cov:5.1%} acc {acc:5.1%} | {res}")

    import bench  # after part 1: importing it does not touch the generator part 1 uses
    print("\nGames 1-3, ball as is, true D, official spellF1 with its 5-95% bootstrap (1000)")
    for g in (1, 2, 3):
        players, ball, team, events, pitch = bench.load_game(g)
        dead = bench.calibrate_dead.dead_labels([e[:5] for e in events], len(ball))
        truth = bench.truth_labels(events, len(ball), dead)
        spans = bench.pm.valid_runs(bench.pm.label_codes(truth))
        cells = []
        for radius, n_s in ((np.inf, 2.0), (1.0, 0.5)):
            e = evidence(ball, radius, "ffill", players, team, pitch=pitch)
            lab = np.full(len(ball), "X", dtype=object)
            for a, b in spans:
                lab[a:b] = np.where(dead[a:b], "D", "X")
                for s0, e0 in o.runs(~dead[a:b]):
                    lab[a + s0:a + e0] = o.confirm_changes(e[a + s0:a + e0], int(n_s * o.FPS))
            r = bench.score(truth, lab, 1000)
            cells.append(f"R={radius} N={n_s}s {r['spell']:.3f} [{r['lo']:.3f}, {r['hi']:.3f}]")
        print(f"  game {g}: " + "   ".join(cells))


if __name__ == "__main__":
    main()
