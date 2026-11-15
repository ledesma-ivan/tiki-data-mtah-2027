"""Synthetic checks for the CI runner and complete-matrix validation. Run: python test_ci_checks.py"""
import contextlib
import copy
import hashlib
import io
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import ci_checks as ci


class MatrixTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.common = ci.common_metadata()
        self.paths = []
        cfg = ci.config()
        for runner, python in itertools.product(cfg["matrix"]["os"], cfg["matrix"]["python"]):
            report = {**self.common, "runtime": {"runner": runner, "system": cfg["systems"][runner], "python": python},
                      "counts": {"H": self.common["fixture"]["frames"] - 3, "A": 1, "D": 1, "X": 1},
                      "sha256": "a" * 64}
            path = self.root / f"hash-{runner}-{python}" / "synthetic.json"
            path.parent.mkdir()
            path.write_text(json.dumps(report), encoding="utf-8")
            self.paths.append(path)

    def compare(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return ci.compare_reports(self.root)

    def test_complete_matrix_passes(self):
        self.assertEqual(len(self.paths), 6)
        self.assertEqual(self.compare(), "a" * 64)

    def test_different_valid_hash_fails(self):
        path = self.paths[-1]
        report = json.loads(path.read_text())
        report["sha256"] = "b" * 64
        path.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, "bytes or label counts differ"):
            self.compare()

    def test_missing_job_fails_even_when_remaining_hashes_match(self):
        shutil.rmtree(self.paths[-1].parent)
        with self.assertRaisesRegex(ValueError, "incomplete matrix"):
            self.compare()

    def test_duplicate_job_fails(self):
        shutil.copytree(self.paths[0].parent, self.root / "hash-duplicate")
        with self.assertRaisesRegex(ValueError, "extra"):
            self.compare()

    def test_missing_or_extra_report_fails(self):
        self.paths[0].unlink()
        with self.assertRaisesRegex(ValueError, "expected only synthetic.json"):
            self.compare()
        self.paths[0].write_text("{}")
        self.paths[0].with_suffix(".csv").write_text("unexpected")
        with self.assertRaisesRegex(ValueError, "expected only synthetic.json"):
            self.compare()

    def test_empty_and_malformed_reports_fail(self):
        for text in ("", "{", "null", "[]", "{}"):
            with self.subTest(text=text):
                self.paths[0].write_text(text)
                with self.assertRaises(ValueError):
                    self.compare()

    def test_invalid_metadata_fails(self):
        path = self.paths[0]
        original = json.loads(path.read_text())
        changes = [("sha256", ""), ("sha256", "g" * 64), ("sha256", None),
                   ("runtime", {**original["runtime"], "python": "3.14.8"}),
                   ("runtime", {**original["runtime"], "system": "Windows"}),
                   ("dependencies", {}), ("scorer", {}), ("sources", {}),
                   ("counts", {"H": 1, "A": 1, "D": 1, "X": 1}),
                   ("counts", {**original["counts"], "A": True}),
                   ("counts", {**original["counts"], "A": 0})]
        for key, value in changes:
            with self.subTest(key=key, value=value):
                path.write_text(json.dumps({**original, key: value}))
                with self.assertRaises(ValueError):
                    self.compare()

    def test_cli_fails_on_incomplete_matrix(self):
        shutil.rmtree(self.paths[-1].parent)
        result = subprocess.run([sys.executable, str(ci.ROOT / "ci_checks.py"), "compare", str(self.root)],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("incomplete matrix", result.stderr)


class RunnerTest(unittest.TestCase):
    def test_source_metadata_is_unchanged_by_windows_checkout_line_endings(self):
        expected = ci.common_metadata()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ci.SOURCES:
                source = (ci.ROOT / name).read_text(encoding="utf-8")
                (root / name).write_bytes(source.replace("\n", "\r\n").encode("utf-8"))
            with patch.object(ci, "ROOT", root):
                self.assertEqual(ci.common_metadata(), expected)

    def test_main_blocks_run_and_match_data_environment_is_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            (root / "tests" / "test_main.py").write_text(
                'import os\nfrom pathlib import Path\nif __name__ == "__main__":\n'
                '    assert "MTAH_DATA" not in os.environ\n    Path("ran").touch()\n')
            with patch.dict(os.environ, {"MTAH_DATA": "not-a-real-data-directory"}), \
                    contextlib.redirect_stdout(io.StringIO()):
                ci.run_tests(root)
            self.assertTrue((root / "ran").exists())

    def test_script_failure_stops_the_runner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            (root / "tests" / "test_01.py").write_text('raise SystemExit(7)\n')
            (root / "tests" / "test_02.py").write_text('from pathlib import Path\nPath("should-not-run").touch()\n')
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(subprocess.CalledProcessError) as error:
                ci.run_tests(root)
            self.assertEqual(error.exception.returncode, 7)
            self.assertFalse((root / "should-not-run").exists())

    def test_optimized_assertions_are_rejected(self):
        with patch.dict(os.environ, {"PYTHONOPTIMIZE": "1"}), self.assertRaisesRegex(ValueError, "assertions"):
            ci.check_environment()

    def test_download_fetches_only_the_pinned_verified_code(self):
        cfg = copy.deepcopy(ci.config())
        content = b"# Synthetic stand-in for scorer source\n"
        cfg["scorer"]["sha256"] = hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory() as directory, patch.object(ci, "config", return_value=cfg), \
                patch.object(ci.urllib.request, "urlopen", return_value=io.BytesIO(content)) as request, \
                contextlib.redirect_stdout(io.StringIO()):
            ci.download_scorer(directory)
            request.assert_called_once_with(
                f'https://raw.githubusercontent.com/{cfg["scorer"]["repository"]}/{cfg["scorer"]["revision"]}'
                '/evaluation/possession_metrics.py', timeout=60)
            paths = [p for p in Path(directory).rglob("*") if p.is_file()]
            self.assertEqual(paths, [Path(directory) / "evaluation" / "possession_metrics.py"])
            self.assertEqual(paths[0].read_bytes(), content)

    def test_scorer_checksum_failure_writes_no_code(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(ci.urllib.request, "urlopen", return_value=io.BytesIO(b"wrong source")), \
                self.assertRaisesRegex(ValueError, "SHA-256"):
            try:
                ci.download_scorer(directory)
            finally:
                self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
