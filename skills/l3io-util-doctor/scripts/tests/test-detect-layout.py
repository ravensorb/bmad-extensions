#!/usr/bin/env python3
"""
Tests for detect-layout.py. Run with:
  uv run skills/l3io-util-doctor/scripts/tests/test-detect-layout.py

Every case drives the real CLI through subprocess -- never the detect() function directly --
so the test exercises the same exit code and stdout a health-check run would see.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


# -- temp-dir leak guard ---------------------------------------------------------------- #
# setUpModule points tempfile.tempdir (this test process) AND the TMPDIR environment variable
# (inherited by every subprocess it spawns) at one private run directory; tearDownModule fails
# the run if anything is left in it, then removes it and restores both to their prior values.
# The one name it ignores is `uv-*.lock`, which `uv run` leaves in TMPDIR by design.
_RUN_TMP = None
_PREV_TMPDIR = None             # the TMPDIR environment variable, or None
_PREV_TEMPFILE_TEMPDIR = None   # tempfile.tempdir as it was before setUpModule


def setUpModule():
    global _RUN_TMP, _PREV_TMPDIR, _PREV_TEMPFILE_TEMPDIR
    _PREV_TEMPFILE_TEMPDIR = tempfile.tempdir
    _RUN_TMP = tempfile.mkdtemp(prefix="test-detect-layout-")
    tempfile.tempdir = _RUN_TMP
    _PREV_TMPDIR = os.environ.get("TMPDIR")
    os.environ["TMPDIR"] = _RUN_TMP


def tearDownModule():
    tempfile.tempdir = _PREV_TEMPFILE_TEMPDIR
    if _PREV_TMPDIR is None:
        os.environ.pop("TMPDIR", None)
    else:
        os.environ["TMPDIR"] = _PREV_TMPDIR
    leaked = sorted(n for n in os.listdir(_RUN_TMP)
                    if not (n.startswith("uv-") and n.endswith(".lock")))
    shutil.rmtree(_RUN_TMP, ignore_errors=True)
    if leaked:
        raise AssertionError(f"temp-dir leak: {len(leaked)} entr"
                             f"{'y' if len(leaked) == 1 else 'ies'} left by tests without "
                             f"cleanup: {', '.join(leaked[:5])}")


HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "detect-layout.py")


class TestLayoutCollision(unittest.TestCase):
    def detect(self, **files):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        if files.get("flat"):
            Path(d, "sprint-status.yaml").touch()
        if files.get("legacy"):
            Path(d, "sprint-status.yaml.legacy").touch()
        if files.get("sharded"):
            Path(d, "state").mkdir()
        r = subprocess.run(["uv", "run", str(SCRIPT), "--artifacts", d],
                            capture_output=True, text=True)
        return r.returncode, r.stdout, d

    def test_both_layouts_is_a_collision(self):
        code, out, d = self.detect(flat=True, sharded=True)
        self.assertEqual(code, 1)
        # Assert the documented message shape verbatim -- both real paths present, not just
        # the "layout-collision" label -- so a mutation that drops the paths (leaving the
        # label intact) is caught rather than surviving on a substring match.
        expected = f"layout-collision: both {Path(d, 'sprint-status.yaml')} and {Path(d, 'state')}/ exist\n"
        self.assertEqual(out, expected)

    def test_post_migrate_legacy_rename_is_clean(self):
        # The load-bearing case: migrate-state renames the flat file to .legacy. If this
        # still reported a collision, the finding would never clear after the documented fix
        # and would become permanent noise.
        code, out, _ = self.detect(legacy=True, sharded=True)
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_sharded_only_is_clean(self):
        code, out, _ = self.detect(sharded=True)
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_flat_only_is_not_a_collision(self):
        code, out, _ = self.detect(flat=True)
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_neither_present_is_clean(self):
        code, out, _ = self.detect()
        self.assertEqual(code, 0)
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
