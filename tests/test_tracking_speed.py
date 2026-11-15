"""Open-loader continuity and cache regressions (#53); synthetic fixtures only."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import bench
import calibrate_dead
from explore import idsse_bench
from open_tracking import derived_speed, frame_numbers, game3_continuity


def metadata(path, slots=2, end=8):
    """Slot 0 changes player at frame 3; period 2 starts at frame 5."""
    channels = ''.join(f'<PlayerChannel id="{p}_{axis}" playerId="{p}" channelId="{axis}"/>'
                       for p in ['old', 'new'] + [f'p{j}' for j in range(1, slots)] for axis in ('x', 'y'))
    specs = ''
    for start, stop, first in ((1, 2, 'old'), (3, end, 'new')):
        refs = ''.join(f'<PlayerChannelRef playerChannelId="{p}_{axis}"/>'
                       for p in [first] + [f'p{j}' for j in range(1, slots)] for axis in ('x', 'y'))
        specs += f'<DataFormatSpecification startFrame="{start}" endFrame="{stop}">{refs}</DataFormatSpecification>'
    params = ''.join(f'<ProviderParameter><Name>{name}</Name><Value>{value}</Value></ProviderParameter>'
                     for name, value in [('first_half_start', 1), ('first_half_end', 4),
                                         ('second_half_start', 5), ('second_half_end', end)])
    Path(path).write_text('<main xmlns="urn:test"><GlobalConfig><ProviderGlobalParameters>' + params
                         + '</ProviderGlobalParameters></GlobalConfig>' + channels + specs + '</main>')


def rewrite(path, old, new):
    """Same-size edit that the (size, mtime) cache key sees even if both writes share a tick (#99)."""
    path.write_text(path.read_text().replace(old, new))
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))


class SpeedTest(unittest.TestCase):
    def test_continuous_movement_substitution_period_missing_and_other_player(self):
        xy = np.zeros((8, 2, 2))
        xy[:, :, 0] = np.arange(8)[:, None] * .04
        xy[2:, 0, 0] += 40  # replacement must not become a 1001 m/s spike
        xy[5, 0] = np.nan
        ids = np.array([['old' if i < 2 else 'new', 'other'] for i in range(8)])
        v = derived_speed(xy, ids, ['1'] * 4 + ['2'] * 4, np.arange(1, 9))
        np.testing.assert_allclose(v[:, 0], [np.nan, 1, np.nan, 1, np.nan, np.nan, np.nan, 1])
        np.testing.assert_allclose(v[:, 1], [np.nan, 1, 1, 1, np.nan, 1, 1, 1])

    def test_unknown_metadata_frame_gap_and_nonfinite_coordinates(self):
        xy = np.zeros((6, 1, 2))
        xy[4, 0, 1] = np.inf
        v = derived_speed(xy, [['p'], ['p'], [''], ['p'], ['p'], ['p']],
                          ['1', '1', '1', '', '1', '1'], [1, 3, 4, 5, 6, 7])
        self.assertTrue(np.isnan(v).all())
        v = derived_speed(np.zeros((3, 1, 2)), ['p'], ['1'] * 3, [1, 2, 3])
        np.testing.assert_array_equal(v[:, 0], [np.nan, 0, 0])

    def test_bad_clocks_fail(self):
        for frames in ([], [0, 1], [1, 1], [2, 1], [1, 2.5], [1, np.nan]):
            with self.subTest(frames=frames), self.assertRaises(ValueError):
                frame_numbers(frames)

    def test_metadata_resolves_player_not_channel_name_and_inclusive_ranges(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'metadata.xml'
            metadata(path)
            ids, periods = game3_continuity(path, np.arange(1, 10), 2)
            self.assertEqual(list(ids[:, 0]), ['old', 'old'] + ['new'] * 6 + [''])
            self.assertEqual(list(ids[:, 1]), ['p1'] * 8 + [''])
            self.assertEqual(list(periods), ['first_half'] * 4 + ['second_half'] * 4 + [''])
            path.write_text(path.read_text().replace('playerId="new"', 'playerId="old"'))
            ids, _ = game3_continuity(path, np.arange(1, 9), 2)
            self.assertEqual(set(ids[:, 0]), {'old'})

    def test_missing_and_unresolvable_metadata_stays_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'metadata.xml'
            ids, periods = game3_continuity(path, np.arange(1, 9), 2)
            self.assertTrue((ids == '').all() and (periods == '').all())
            metadata(path)
            path.write_text(path.read_text().replace('playerChannelId="new_y"', 'playerChannelId="missing"'))
            ids, _ = game3_continuity(path, np.arange(1, 9), 2)
            self.assertTrue((ids[2:, 0] == '').all())
            self.assertTrue((ids[:, 1] == 'p1').all())

    def test_incomplete_periods_and_conflicting_format_fail_conservatively(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'metadata.xml'
            metadata(path)
            text = path.read_text()
            path.write_text(text.replace('<Name>second_half_end</Name><Value>8</Value>',
                                         '<Name>second_half_end</Name><Value/>'))
            _, periods = game3_continuity(path, np.arange(1, 9), 2)
            self.assertTrue((periods[4:] == '').all())
            path.write_text(text.replace('startFrame="3"', 'startFrame="2"'))
            with self.assertRaisesRegex(ValueError, 'overlapping'):
                game3_continuity(path, np.arange(1, 9), 2)

    def test_missing_format_boundary_has_a_clear_validation_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'metadata.xml'
            metadata(path)
            path.write_text(path.read_text().replace('startFrame="1"', ''))
            with self.assertRaisesRegex(ValueError, 'startFrame/endFrame'):
                game3_continuity(path, np.arange(1, 9), 2)

    def test_swapping_slots_invalidates_both_without_affecting_other_players(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'metadata.xml'
            metadata(path, slots=3)
            text = path.read_text().replace('playerId="new"', 'playerId="p1"')
            start = text.index('<DataFormatSpecification startFrame="3"')
            text = text[:start] + text[start:].replace('playerChannelId="p1_', 'playerChannelId="old_')
            path.write_text(text)
            frames = np.arange(1, 5)
            ids, periods = game3_continuity(path, frames, 3)
            xy = np.zeros((4, 3, 2))
            xy[:, :, 0] = frames[:, None] * .04
            xy[2:, 0, 0] += 40
            xy[2:, 1, 0] -= 40
            speed = derived_speed(xy, ids, periods, frames)
            np.testing.assert_allclose(speed[:, :2], [[np.nan] * 2, [1] * 2, [np.nan] * 2, [1] * 2])
            np.testing.assert_allclose(speed[:, 2], [np.nan, 1, 1, 1])


class LoaderTest(unittest.TestCase):
    def test_game3_cold_warm_old_cache_and_metadata_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = str(Path(tmp) / 'Sample_Game_3_')
            cache = prefix + 'tracking.npz'
            metadata(prefix + 'metadata.xml', slots=22)
            xy = np.zeros((8, 46))
            xy[:, :44:2] = np.arange(8)[:, None] * .001
            xy[2:, 0] += .5
            xy[5, 0] = np.nan
            # Frame 7 is omitted entirely; frame 8 cannot bridge that gap.
            Path(prefix + 'tracking.txt').write_text(''.join(
                f'{i}:' + ','.join(map(str, row)) + '\n' for i, row in enumerate(xy, 1) if i != 7))
            with patch.object(calibrate_dead, 'PREFIX', prefix), patch.object(calibrate_dead, 'CACHE', cache):
                cold = calibrate_dead.load_game3()
                np.testing.assert_allclose(cold[0][:, 0, 2],
                                           [np.nan, 2.625, np.nan, 2.625, np.nan, np.nan, np.nan, np.nan])
                np.testing.assert_allclose(cold[0][:, 1, 2],
                                           [np.nan, 2.625, 2.625, 2.625, np.nan, 2.625, np.nan, np.nan])
                for a, b in zip(cold[:2], calibrate_dead.load_game3()[:2]):
                    np.testing.assert_array_equal(a, b)
                # The #52 cache has the correct pitch but obsolete speed arithmetic.
                np.savez_compressed(cache, players=np.full_like(cold[0], 999), ball=cold[1], pitch=cold[2])
                np.testing.assert_array_equal(calibrate_dead.load_game3()[0], cold[0])
                Path(prefix + 'metadata.xml').unlink()
                with self.assertWarnsRegex(RuntimeWarning, 'no finite derived speeds'):
                    missing = calibrate_dead.load_game3()[0]
                self.assertTrue(np.isnan(missing[:, :, 2]).all())
                with self.assertWarnsRegex(RuntimeWarning, 'no finite derived speeds'):
                    np.testing.assert_array_equal(calibrate_dead.load_game3()[0], missing)
                metadata(prefix + 'metadata.xml', slots=22)
                np.testing.assert_array_equal(calibrate_dead.load_game3()[0], cold[0])
                # A raw tracking edit must invalidate a warm cache as well.
                path = Path(prefix + 'tracking.txt')
                rewrite(path, '2:0.001,', '2:0.002,')
                updated = calibrate_dead.load_game3()[0]
                self.assertAlmostEqual(updated[1, 0, 2], 5.25)
                np.testing.assert_array_equal(calibrate_dead.load_game3()[0], updated)

    def test_csv_periods_gaps_missing_ids_and_cache(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(bench, 'ROOT', tmp), \
                patch.object(bench, 'load_csv_events', return_value=[]):
            for g in (1, 2):
                prefix = str(Path(tmp) / 'data' / f'Sample_Game_{g}' / f'Sample_Game_{g}_')
                Path(prefix).parent.mkdir(parents=True)
                text = ('ignored\nignored\nPeriod,Frame,Time,Player1,y,Player,y2,bx,by\n'
                        '1,1,0,0,0,0,0,0,0\n1,2,.04,.001,0,0,0,0,0\n'
                        '2,3,.08,.8,0,0,0,0,0\n2,4,.12,.801,0,0,0,0,0\n'
                        '2,6,.20,.802,0,0,0,0,0\n2,7,.24,.803,0,0,0,0,0\n')
                for side in ('Home', 'Away'):
                    Path(prefix + f'RawTrackingData_{side}_Team.csv').write_text(text)
                p, b, team, _, pitch = bench.load_game(g)
                np.testing.assert_allclose(p[:, 0, 2], [np.nan, 2.625, np.nan, 2.625, np.nan, np.nan, 2.625])
                self.assertTrue(np.isnan(p[:, 1, 2]).all())
                np.testing.assert_array_equal(bench.load_game(g)[0], p)
                np.savez_compressed(prefix + 'tracking.npz', players=p + 999, ball=b, team=team, pitch=pitch)
                np.testing.assert_array_equal(bench.load_game(g)[0], p)
                path = Path(prefix + 'RawTrackingData_Away_Team.csv')
                rewrite(path, '2,7,.24', '2,8,.24')
                with self.assertRaisesRegex(ValueError, 'clocks'):
                    bench.load_game(g)

    def test_csv_rejects_unknown_clock_column_names(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(bench, 'ROOT', tmp):
            prefix = Path(tmp) / 'data' / 'Sample_Game_1' / 'Sample_Game_1_'
            prefix.parent.mkdir(parents=True)
            Path(str(prefix) + 'RawTrackingData_Home_Team.csv').write_text(
                'ignored\nignored\nUnknown,Frame,Time,Player1,y,bx,by\n1,1,0,0,0,0,0\n')
            with self.assertRaisesRegex(ValueError, 'Period,Frame'):
                bench.load_game(1)

    def test_idsse_person_section_missing_and_provider_speed_with_existing_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / 'DFL_04_03_positions_raw_observed_test.xml')
            Path(path.replace('DFL_04_03_positions_raw_observed', 'DFL_02_01_matchinformation')).write_text(
                '<Match PitchX="105" PitchY="68"><Team TeamId="h" Role="home"/></Match>')
            lines = []
            for section in ('firstHalf', 'secondHalf'):
                for side, person, frames, x in [('BALL', 'ball', range(1, 6), 0),
                                                 ('h', 'old', [1, 2], 0), ('h', 'new', [3, 4, 5], 40),
                                                 ('a', 'other', [1, 2, 4, 5], 10)]:
                    lines.append(f'<FrameSet GameSection="{section}" TeamId="{side}" PersonId="{person}">')
                    for frame in frames:
                        lines.append(f'<Frame N="{frame}" T="0" X="{x + frame * .04}" Y="0" D="0" '
                                     'S="18" BallPossession="1" BallStatus="1"/>')
                    lines.append('</FrameSet>')
            Path(path).write_text('\n'.join(lines))
            cold = idsse_bench.load(path, 'positions')
            warm = idsse_bench.load(path, 'positions')
            provider = idsse_bench.load(path, 'provider')
            for (_, p, _, _, _, v, _), cached, supplied in zip(cold, warm, provider):
                np.testing.assert_array_equal(p, cached[1])
                np.testing.assert_allclose(v[:, 0], [np.nan, 1, np.nan, np.nan, 1])  # other
                np.testing.assert_allclose(v[:, 1], [np.nan, np.nan, np.nan, 1, 1])  # new
                np.testing.assert_allclose(v[:, 2], [np.nan, 1, np.nan, np.nan, np.nan])  # old
                np.testing.assert_allclose(supplied[1][:, :, 2][np.isfinite(p[:, :, 0])], 5.)


if __name__ == '__main__':
    unittest.main()
