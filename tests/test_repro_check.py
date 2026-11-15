"""Synthetic end-to-end checks for the CI fixture. Run: python test_repro_check.py"""
import contextlib
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import repro_check as repro


class FixtureTest(unittest.TestCase):
    def test_delivery_paths_are_rejected_before_computing_or_writing(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(repro, "ROOT", Path(directory)), \
                patch.object(repro.P, "label") as label, contextlib.chdir(directory):
            delivery = Path(directory) / "output" / "possession.csv"
            delivery.parent.mkdir()
            delivery.write_text("synthetic sentinel", encoding="utf-8")
            for destination in (delivery, Path("output/possession.csv"), Path("scratch/../output/possession.csv")):
                with self.subTest(destination=destination), self.assertRaisesRegex(ValueError, "outside"):
                    repro.run(destination)
            label.assert_not_called()
            self.assertEqual(delivery.read_text(encoding="utf-8"), "synthetic sentinel")

    def test_cli_rejects_csv_and_metadata_delivery_paths_before_running(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(repro, "ROOT", Path(directory)), \
                patch.object(repro, "run") as run:
            delivery = Path(directory) / "output" / "possession.csv"
            for arguments in ([str(delivery)], ["--metadata", str(delivery), "--runner", "macos-15"]):
                with self.subTest(arguments=arguments), patch.object(repro.sys, "argv", ["repro_check.py", *arguments]), \
                        contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                    repro.main()
                self.assertEqual(error.exception.code, 2)
            run.assert_not_called()
            self.assertFalse(delivery.parent.exists())

    def test_symlink_to_delivery_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(repro, "ROOT", Path(directory)), \
                patch.object(repro.P, "label") as label:
            output = Path(directory) / "output"
            output.mkdir()
            alias = Path(directory) / "alias"
            try:
                alias.symlink_to(output, target_is_directory=True)
            except OSError:
                self.skipTest("creating symlinks requires OS permission")
            with self.assertRaisesRegex(ValueError, "outside"):
                repro.run(alias / "synthetic.csv")
            label.assert_not_called()
            self.assertEqual(list(output.iterdir()), [])

    def test_fixture_repeats_exactly_including_missing_observations(self):
        first, second = repro.fixture(n=5000), repro.fixture(n=5000)
        for a, b in zip(first, second):
            np.testing.assert_array_equal(a, b)
        players, ball, team = first
        self.assertTrue(np.isnan(ball).any())
        self.assertTrue(np.isnan(players).any())
        self.assertEqual(set(team), {"H", "A"})

    def test_changed_input_changes_computed_labels_and_csv_bytes(self):
        digests = []
        n = 5000
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(repro.P, "N_FRAMES", n), patch.object(repro.P, "HALVES", [(100, 2199), (2600, 4799)]), \
                patch.object(repro.P, "KICKOFFS", (100, 2600)), \
                patch.object(repro.P, "load_atd", side_effect=AssertionError("must not load tracking")), \
                contextlib.redirect_stdout(io.StringIO()):
            for seed in (54, 55):
                sample = repro.fixture(seed=seed, n=n)
                path = Path(directory) / f"synthetic-{seed}.csv"
                with patch.object(repro, "fixture", return_value=sample):
                    digest, counts = repro.run(path)
                content = path.read_bytes()
                self.assertEqual(digest, hashlib.sha256(content).hexdigest())
                self.assertTrue(all(counts.values()))
                self.assertEqual(sum(counts.values()), n)
                self.assertEqual(len(content.splitlines()), n + 1)
                self.assertNotIn(b"\r", content)
                digests.append(digest)
        self.assertNotEqual(*digests)

    def test_default_temporary_csv_is_deleted(self):
        paths = []

        def fake_run(path):
            paths.append(Path(path))
            paths[-1].write_text("synthetic")
            return "a" * 64, {}

        with patch.object(repro.sys, "argv", ["repro_check.py"]), patch.object(repro, "run", side_effect=fake_run):
            repro.main()
        self.assertEqual(len(paths), 1)
        self.assertFalse(paths[0].exists())
        self.assertFalse(paths[0].parent.exists())


if __name__ == "__main__":
    unittest.main()
