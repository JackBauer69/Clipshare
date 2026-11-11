"""Regression tests for portable, version-matched third-party license collection."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import collect_licenses


class LicenseCollectionTests(unittest.TestCase):
    def test_existing_installation_license_has_priority(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "runtime-LICENSE"
            fallback = Path(directory) / "fallback-LICENSE"
            runtime.write_text("runtime license", encoding="utf-8")
            fallback.write_text("upstream license", encoding="utf-8")
            self.assertEqual(
                collect_licenses.first_existing((runtime,), "Python", fallback),
                runtime,
            )

    def test_fallback_is_used_when_runtime_notice_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            fallback = Path(directory) / "fallback-LICENSE"
            fallback.write_text("upstream license", encoding="utf-8")
            self.assertEqual(
                collect_licenses.first_existing((Path(directory) / "missing",), "Python", fallback),
                fallback,
            )

    def test_missing_notices_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SystemExit):
                collect_licenses.first_existing(
                    (Path(directory) / "missing",), "Python",
                    Path(directory) / "also-missing",
                )

    def test_cpython_fallback_is_version_limited(self):
        self.assertEqual(
            collect_licenses.python_license_fallback((3, 12, 10)),
            collect_licenses.UPSTREAM / "Python-3.12.10-LICENSE.txt",
        )
        self.assertIsNone(collect_licenses.python_license_fallback((3, 11, 9)))
        self.assertIsNone(collect_licenses.python_license_fallback((3, 13, 0)))

    def test_tcl_and_tk_use_distinct_upstream_notices(self):
        tcl = collect_licenses.tcltk_license("tcl8.6", 8.6)
        tk = collect_licenses.tcltk_license("tk8.6", 8.6)
        self.assertTrue(tcl.is_file())
        self.assertTrue(tk.is_file())
        self.assertNotEqual(tcl, tk)
        self.assertNotEqual(tcl.read_bytes(), tk.read_bytes())

    def test_unknown_tcltk_version_is_rejected(self):
        with self.assertRaises(SystemExit):
            collect_licenses.tcltk_license("tcl8.6", 8.7)
        with self.assertRaises(SystemExit):
            collect_licenses.tcltk_license("tk8.6", 8.5)

    def test_missing_upstream_notice_is_not_silenced(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(collect_licenses, "UPSTREAM", Path(directory)):
                with self.assertRaises(SystemExit):
                    collect_licenses.tcltk_license("tk8.6", 8.6)


if __name__ == "__main__":
    unittest.main()
