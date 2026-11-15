"""Per-game geometry regressions (#52). Synthetic fixtures only, including loader caches."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import bench
import calibrate_dead
import possession
from explore import idsse_bench


def normalise(player_m, ball_m, pitch):
    players = np.zeros(player_m.shape[:-1] + (3,))
    players[..., :2] = player_m / pitch
    players[..., 2] = 5.0
    return players, ball_m / pitch


def legacy_evidence(players, ball, team, radius=np.inf, max_interp=None):
    """Frozen arithmetic from 32c5d46; independent of the new distance helper."""
    bxy = possession.ball_position(ball, max_interp)
    dx = (players[:, :, 0] - bxy[:, None, 0]) * 105.3
    dy = (players[:, :, 1] - bxy[:, None, 1]) * 68.0
    d = np.where(np.isnan(dx), np.inf, dx * dx + dy * dy)
    ev = team[d.argmin(1)].astype(object)
    nearest = d.min(1)
    ev[~(np.isfinite(nearest) & (nearest <= radius * radius))] = ""
    return ev


class GeometryTest(unittest.TestCase):
    def test_bench_evidence_rejects_missing_pitch_without_breaking_delivery_calls(self):
        pitch = (90., 80.)
        p, b = normalise(np.array([[[20.99, 20.]]]), np.array([[20., 20.]]), pitch)
        team = np.array(["H"])
        with self.assertRaises(TypeError):
            bench.owner_evidence(p, b, team, 1.)
        self.assertEqual(list(bench.owner_evidence(p, b, team, 1., pitch=pitch)), ["H"])
        # Delivery callers keep the historical default geometry and result.
        np.testing.assert_array_equal(possession.owner_evidence(p, b, team, 1.), legacy_evidence(p, b, team, 1.))

    def test_distance_arithmetic_preserves_float32_and_float64_inputs(self):
        rng = np.random.default_rng(52)
        for dtype in (np.float32, np.float64):
            p = rng.random((500, 3, 3)).astype(dtype)
            b = rng.random((500, 2)).astype(dtype)
            dx = (p[:, :, 0] - b[:, None, 0]) * 105.3
            dy = (p[:, :, 1] - b[:, None, 1]) * 68.
            expected = dx * dx + dy * dy
            actual = possession.squared_distances(p, b, pitch=possession.PITCH)
            self.assertEqual(actual.dtype, expected.dtype)
            np.testing.assert_array_equal(actual, expected)
            for interp in (None, 50):
                team = np.array(["H", "A", "H"])
                np.testing.assert_array_equal(possession.owner_evidence(p, b, team, 1., interp),
                                              legacy_evidence(p, b, team, 1., interp))

    def test_distances_and_radius_are_in_metres_on_both_axes(self):
        offsets = np.array([[0.999, 0], [1.001, 0], [0, 0.999], [0, 1.001],
                            [0.6, 0.799], [0.6, 0.801]])
        ball_m = np.full((len(offsets), 2), 20.)
        player_m = np.stack([ball_m + offsets, ball_m + [2., 2.]], axis=1)
        expected_d = ((player_m - ball_m[:, None]) ** 2).sum(axis=2)
        for pitch in ((105.3, 68.), (105., 68.), (90., 80.), (120., 60.)):
            with self.subTest(pitch=pitch):
                p, b = normalise(player_m, ball_m, pitch)
                np.testing.assert_allclose(possession.squared_distances(p, b, pitch=pitch), expected_d, atol=1e-12)
                ev = possession.owner_evidence(p, b, np.array(["A", "H"]), radius=1, pitch=pitch)
                self.assertEqual(list(ev), ["A", "", "A", "", "A", ""])

    def test_nearest_team_depends_on_physical_distance_not_normalised_distance(self):
        ball_m = np.array([[20., 20.]])
        player_m = np.array([[[20.9, 20.], [20., 20.95]]])
        for pitch in ((90., 80.), (120., 60.)):
            p, b = normalise(player_m, ball_m, pitch)
            self.assertEqual(list(possession.owner_evidence(p, b, np.array(["H", "A"]), pitch=pitch)), ["H"])

    def test_delivery_defaults_and_labels_match_frozen_implementation(self):
        rng = np.random.default_rng(52)
        players = rng.random((600, 6, 3))
        players[:, :, 2] *= 5
        ball = players[:, 0, :2].copy()
        ball[100:140] = np.nan
        ball[250:350] = np.nan
        players[400:410] = np.nan
        players[500:520, 1] = players[500:520, 0]  # exact ties
        team = np.array(["H", "A", "H", "A", "H", "A"])
        for radius, interp in ((np.inf, None), (1., None), (1., 50)):
            expected = legacy_evidence(players, ball, team, radius, interp)
            for kw in ({}, {"pitch": possession.PITCH}):
                np.testing.assert_array_equal(possession.owner_evidence(players, ball, team, radius, interp, **kw), expected)
        with patch.object(possession, "N_FRAMES", 600), patch.object(possession, "HALVES", [(10, 590)]):
            actual = possession.label(players, ball, team)
            with patch.object(possession, "owner_evidence", legacy_evidence):
                expected = possession.label(players, ball, team)
        np.testing.assert_array_equal(actual, expected)

    def test_all_bench_pipelines_use_the_supplied_pitch(self):
        n = 600
        ball_m = np.full((n, 2), 20.)
        player_m = np.broadcast_to([[20.99, 20.], [20., 21.01]], (n, 2, 2)).copy()
        player_m[200:400] = [[21.01, 20.], [20., 20.99]]
        ball_m[260:270] = np.nan  # interpolation also preserves the physical geometry
        results = {}
        for pitch in ((90., 80.), (120., 60.)):
            p, b = normalise(player_m, ball_m, pitch)
            for name, fn in bench.PIPELINES.items():
                out = fn(p, b, np.array(["H", "A"]), [(0, n)], np.zeros(n, bool), pitch=pitch)
                self.assertEqual(out[100], "H")
                self.assertEqual(out[300], "A")
                # live (ADR-014) also reads where each team is on the pitch (advance, ball_advance), so the same
                # distances on a pitch of another length are another scene: only the owners above must hold
                if name in results and name != "live":
                    np.testing.assert_array_equal(out, results[name])
                results[name] = out

    def test_crowd_degradation_preserves_physical_neighbourhoods(self):
        n = 20_000
        ball_m = np.full((n, 2), 20.)
        player_m = np.broadcast_to([[22.999, 20.], [20., 22.999], [18., 18.]], (n, 3, 2)).copy()
        player_m[n // 2:, 0, 0] = 23.001
        masks = []
        for pitch in ((90., 80.), (120., 60.)):
            p, b = normalise(player_m, ball_m, pitch)
            out = bench.degrade(b, p, np.zeros(n, bool), 0.45, 1.5, crowd=2, seed=52, pitch=pitch)
            masks.append(np.isnan(out))
        np.testing.assert_array_equal(*masks)
        wrong = bench.degrade(b, p, np.zeros(n, bool), 0.45, 1.5, crowd=2, seed=52, pitch=bench.PITCH)
        self.assertFalse(np.array_equal(masks[-1], np.isnan(wrong)))

    def test_invalid_or_missing_pitch_fails_instead_of_falling_back(self):
        for pitch in (None, (), (105.,), (105., 68., 1.), (0., 68.), (-1., 68.), (np.nan, 68.), (105., np.inf)):
            with self.subTest(pitch=pitch), self.assertRaises(ValueError):
                possession.pitch_dimensions(pitch)
        with self.assertRaises(TypeError):
            bench.radio_evidence(None, None, None)
        with self.assertRaises(TypeError):
            bench.degrade(None, None, None, 0.45, 1.5)

    def test_bench_runner_passes_loader_geometry_to_noise_and_pipeline(self):
        n, pitch = 200, (96., 72.)
        players = np.zeros((n, 2, 3))
        ball = np.full((n, 2), 0.5)
        events = [("PASS", "", 0, n - 1, 1, "H")]
        seen = []

        def pipeline(p, b, team, spans, dead, *, pitch):
            seen.append(pitch)
            return np.full(n, "H", object)

        with patch.object(bench, "load_game", return_value=(players, ball, np.array(["H", "A"]), events, pitch)), \
                patch.object(bench, "degrade", wraps=bench.degrade) as noise, \
                patch.dict(bench.PIPELINES, {"test": pipeline}, clear=True):
            bench.run([1], 1, 0.45, 1.5, 2, ["start"], 0)
        self.assertEqual(seen, [pitch, pitch])
        self.assertEqual(noise.call_args.kwargs["pitch"], pitch)


class LoaderGeometryTest(unittest.TestCase):
    def test_metrica_csv_cold_cache_warm_cache_and_legacy_cache(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(bench, "ROOT", tmp), \
                patch.object(bench, "load_csv_events", return_value=[]):
            for game in (1, 2):
                prefix = Path(tmp) / "data" / f"Sample_Game_{game}" / f"Sample_Game_{game}_"
                prefix.parent.mkdir(parents=True)
                for side in ("Home", "Away"):
                    Path(f"{prefix}RawTrackingData_{side}_Team.csv").write_text(
                        "ignored\nignored\nPeriod,Frame,Time,Player1,y,bx,by\n1,1,0,0.1,0.2,0.3,0.4\n"
                        "1,2,0.04,0.11,0.22,0.3,0.4\n")
                cold = bench.load_game(game)
                self.assertEqual(cold[-1], (105., 68.))
                np.testing.assert_allclose(cold[0][1, :, 2], np.hypot(1.05, 1.36) * 25)
                warm = bench.load_game(game)
                np.testing.assert_array_equal(cold[0], warm[0])
                self.assertEqual(cold[-1], warm[-1])
                for geometry in ({}, {"pitch": (90., 70.)}):
                    np.savez_compressed(f"{prefix}tracking.npz", players=np.full_like(cold[0], 999),
                                        ball=cold[1], team=cold[2], **geometry)
                    np.testing.assert_array_equal(bench.load_game(game)[0], cold[0])

    def test_game3_pitch_survives_cache_and_bench_loader(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = str(Path(tmp) / "Sample_Game_3_")
            cache = prefix + "tracking.npz"
            xy = np.zeros((2, 46))
            xy[1, :44:2] = .01
            Path(prefix + "tracking.txt").write_text("".join(
                f"{i}:" + ",".join(map(str, row)) + "\n" for i, row in enumerate(xy, 1)))
            channels = ''.join(f'<PlayerChannel id="p{j}_{axis}" playerId="p{j}" channelId="{axis}"/>'
                               for j in range(22) for axis in ('x', 'y'))
            refs = ''.join(f'<PlayerChannelRef playerChannelId="p{j}_{axis}"/>'
                           for j in range(22) for axis in ('x', 'y'))
            Path(prefix + "metadata.xml").write_text(
                '<main><GlobalConfig><ProviderGlobalParameters>'
                '<ProviderParameter><Name>first_half_start</Name><Value>1</Value></ProviderParameter>'
                '<ProviderParameter><Name>first_half_end</Name><Value>2</Value></ProviderParameter>'
                '</ProviderGlobalParameters></GlobalConfig>' + channels
                + '<DataFormatSpecification startFrame="1" endFrame="2">' + refs
                + '</DataFormatSpecification></main>')
            Path(prefix + "events.json").write_text('{"data": []}')
            with patch.object(calibrate_dead, "PREFIX", prefix), patch.object(calibrate_dead, "CACHE", cache), \
                    patch.object(calibrate_dead, "PITCH", (96., 72.)):
                cold = bench.load_game(3)
                warm = bench.load_game(3)
                self.assertEqual(cold[-1], calibrate_dead.PITCH)
                self.assertEqual(warm[-1], cold[-1])
                np.testing.assert_array_equal(warm[0], cold[0])
                np.testing.assert_allclose(cold[0][1, :, 2], .96 * 25)
                np.savez_compressed(cache, players=np.full_like(cold[0], 999), ball=cold[1])
                np.testing.assert_array_equal(bench.load_game(3)[0], cold[0])

    def test_idsse_metadata_pitch_survives_parse_cache_and_both_speed_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            for i, pitch in enumerate(((100., 70.), (110., 65.))):
                path = str(Path(tmp) / f"DFL_04_03_positions_raw_observed_{i}.xml")
                Path(path.replace("DFL_04_03_positions_raw_observed", "DFL_02_01_matchinformation")).write_text(
                    f'<Match PitchX="{pitch[0]}" PitchY="{pitch[1]}">\n<Team TeamId="home" Role="home"/>\n</Match>')
                lines = []
                for side in ("home", "away", "BALL"):
                    lines.append(f'<FrameSet GameSection="firstHalf" TeamId="{side}" PersonId="p">')
                    for frame in (1, 2):
                        lines.append(f'<Frame N="{frame}" T="0" X="{frame}" Y="2" D="0" S="18" '
                                     'BallPossession="1" BallStatus="1"/>')
                    lines.append('</FrameSet>')
                Path(path).write_text('\n'.join(lines))
                for source in ("provider", "positions"):
                    section, p, b, team, truth, speed, actual_pitch = idsse_bench.load(path, source)[0]
                    self.assertEqual(actual_pitch, pitch)
                    np.testing.assert_allclose((b - .5) * pitch, [[1., 2.], [2., 2.]])
                    np.testing.assert_allclose((p[..., :2] - .5) * pitch, np.broadcast_to(
                        np.array([[1., 2.], [2., 2.]])[:, None], (2, 2, 2)))
                    np.testing.assert_allclose(p[1, :, 2], 5. if source == "provider" else 25.)


class PerGameConsumersTest(unittest.TestCase):
    def test_stops_and_calibration_use_the_match_pitch_for_the_restart_team(self):
        import calibrate_edges as calibration

        n = 600
        team = np.array(["H", "A"])
        player_m = np.broadcast_to([[20.99, 20.], [20., 21.01]], (n, 2, 2)).copy()
        model = {"mode": "planb", "window": 125, "team_radius_cm": 100,
                 "lead": [0] * len(possession.KINDS), "trim": [0] * len(possession.KINDS),
                 "type": [{"init": 0, "trees": []}] * len(possession.KINDS)}
        for pitch in ((90., 80.), (120., 60.)):
            p, b = normalise(player_m, np.full((n, 2), 20.), pitch)
            p[200:400, :, 2] = .5
            dead = possession.dead_mask_v2(p, b)
            self.assertTrue(dead.any())
            with patch.object(bench, "stops_model", return_value=model):
                out = bench.pipeline_stops(p, b, team, [(0, n)], dead, pitch=pitch)
            for _, end in possession.runs(dead):
                self.assertEqual(out[end], "H")  # H is inside 1 m; A is outside it.
            np.testing.assert_array_equal(out, calibration.candidate(p, b, team, [(0, n)], model, pitch=pitch))

    def test_training_loaders_and_consumers_keep_the_loader_pitch(self):
        import calibrate_edges as calibration

        n, pitch = 600, (90., 80.)
        p, b = normalise(np.broadcast_to([[20.99, 20.], [20., 21.01]], (n, 2, 2)),
                         np.full((n, 2), 20.), pitch)
        p[200:400, :, 2] = .5
        team = np.array(["H", "A"])
        events = [("PASS", "", 0, 199, 1, "H"), ("BALL OUT", "", 199, 200, 1, "H"),
                  ("SET PIECE", "THROW IN", 400, 401, 1, "H"), ("PASS", "", 401, n - 1, 1, "H")]
        with patch.object(bench, "load_game", return_value=(p, b, team, events, pitch)):
            metrica, = calibration.load_metrica(1)
        self.assertEqual(metrica.pitch, pitch)
        with patch.object(calibration, "idsse_files", return_value=["synthetic.xml"]), \
                patch.object(calibration, "restart_frames", return_value={"first": [(400, 0)]}), \
                patch.object(calibration.idsse_bench, "load", return_value=[
                    ("first", p, b, team, metrica.truths["start"], np.zeros(p.shape[:2]), pitch)]):
            idsse, = calibration.load_idsse(1)
        self.assertEqual(idsse.pitch, pitch)
        for game in (metrica, idsse):
            with patch.object(bench, "degrade", wraps=bench.degrade) as noise:
                calibration.degraded(game, 52)
                self.assertEqual(noise.call_args.kwargs["pitch"], pitch)
            with patch.object(possession, "frame_features", wraps=possession.frame_features) as frames, \
                    patch.object(possession, "stop_features", wraps=possession.stop_features) as stops:
                rows = calibration.game_rows(game, b)
                self.assertGreater(len(rows.S), 0)
                self.assertEqual(frames.call_args.args[2], pitch)
                self.assertTrue(stops.call_args_list)
                self.assertTrue(all(call.args[-1] == pitch for call in stops.call_args_list))
            scored = calibration.score([game], {"identity": possession.load_model()}, [0],
                                       noise={"sigma": .3}, scenario={"crowd": 2})
            for anchor in game.truths:
                np.testing.assert_array_equal(scored[(game.g, anchor, "degraded", "identity")][1][0],
                                              scored[(game.g, anchor, "degraded", "radio")][1][0])

    def test_position_noise_and_identity_swaps_have_the_same_physical_scale(self):
        from explore.player_noise import noisy_players

        n = 5000
        player_m = np.broadcast_to([[24.99, 20.], [20., 24.98]], (n, 2, 2)).copy()
        physical = []
        for pitch in ((90., 80.), (120., 60.)):
            p, b = normalise(player_m, np.full((n, 2), 20.), pitch)
            out = noisy_players(p, b, np.array(["H", "A"]), np.random.default_rng(52),
                                sigma=.6, swap=.5, pitch=pitch)
            physical.append(out[..., :2] * pitch)
        np.testing.assert_allclose(*physical, rtol=0, atol=1e-12)

    def test_ball_clock_uses_speed_in_metres_on_each_axis(self):
        from explore.edge_clock import kicks

        for pitch in ((90., 80.), (120., 60.)):
            for axis in (0, 1):
                for speed in (3.5, 4.5):
                    ball_m = np.full((80, 2), 20.)
                    ball_m[30:, axis] += np.arange(50) * speed / possession.FPS
                    np.testing.assert_array_equal(kicks(ball_m / pitch, pitch=pitch), [30] if speed > 4 else [])


if __name__ == "__main__":
    unittest.main()
