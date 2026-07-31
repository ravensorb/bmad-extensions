#!/usr/bin/env python3
"""
Tests for pm-status.py — run with: python3 test-pm-status.py  (or `uv run`).
Exercises node addressing across the split layout, atomic set-status/set-actual,
comment/order preservation, the progress ledger, and verify exit codes.
"""
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "pm-status.py")

sys.path.insert(0, os.path.dirname(HERE))
import importlib.util

spec = importlib.util.spec_from_file_location("pm_status", SCRIPT)
pm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm)

SAMPLE = """\
# active status file — comments must survive round-trips
epics:
- id: '01'
  title: 'Epic 01 — Foundation'
  goal: 'Stand up the core'
  status: in-progress
  sprints:
  - id: '01'
    title: 'Sprint 01 — Foundation'
    status: in-progress
    stories:
    - key: PROJ-E01-S01-ST01   # first story
      title: 'Story one'
      status: ready-for-dev
      classification: complex
    - key: PROJ-E01-S01-ST02
      title: 'Story two'
      status: backlog
"""


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.f = os.path.join(self.d, "sprint-status.yaml")
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write(SAMPLE)
        self.ledger = os.path.join(self.d, "progress.log")

    def run_main(self, argv):
        """Call main() in-process; return (exit_code, stdout)."""
        buf = io.StringIO()
        code = 0
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        return code, buf.getvalue()

    def read(self):
        with open(self.f, encoding="utf-8") as fh:
            return fh.read()


class TestSetStatus(Base):
    def test_story_status_transition(self):
        code, out = self.run_main(["set-status", "--file", self.f,
                                   "--story", "PROJ-E01-S01-ST01", "--status", "in-progress"])
        self.assertEqual(code, 0, out)
        y, data = pm._load(self.f)
        st = pm.find_story(data, "PROJ-E01-S01-ST01")
        self.assertEqual(st["status"], "in-progress")
        self.assertIn("updated_at", st)

    def test_preserves_comments_and_order(self):
        self.run_main(["set-status", "--file", self.f,
                       "--story", "PROJ-E01-S01-ST01", "--status", "review"])
        text = self.read()
        self.assertIn("# active status file — comments must survive round-trips", text)
        self.assertIn("# first story", text)
        # key order within the epic node is preserved (title before goal before status)
        self.assertLess(text.index("title: 'Epic 01"), text.index("goal:"))
        self.assertLess(text.index("goal:"), text.index("status: in-progress"))

    def test_sprint_addressing_with_padding(self):
        # bare "1" must resolve to zero-padded '01'
        code, out = self.run_main(["set-status", "--file", self.f,
                                   "--epic", "1", "--sprint", "1", "--status", "done"])
        self.assertEqual(code, 0, out)
        y, data = pm._load(self.f)
        sp = pm.find_sprint(data, "01", "01")
        self.assertEqual(sp["status"], "done")

    def test_invalid_status_rejected(self):
        code, _ = self.run_main(["set-status", "--file", self.f,
                                 "--story", "PROJ-E01-S01-ST01", "--status", "shipped"])
        self.assertEqual(code, 2)

    def test_node_not_found(self):
        code, _ = self.run_main(["set-status", "--file", self.f,
                                 "--story", "NOPE", "--status", "done"])
        self.assertEqual(code, 3)

    def test_writes_ledger(self):
        self.run_main(["set-status", "--file", self.f, "--story", "PROJ-E01-S01-ST01",
                       "--status", "done", "--ledger", self.ledger, "--scope", "E01/S01/ST01"])
        with open(self.ledger, encoding="utf-8") as fh:
            line = fh.read().strip()
        self.assertIn("E01/S01/ST01", line)
        self.assertIn("status -> done", line)


class TestSetActual(Base):
    def test_writes_actual_block(self):
        code, out = self.run_main(["set-actual", "--file", self.f, "--node", "story",
                                   "--story", "PROJ-E01-S01-ST01", "--elapsed-hours", "0.4",
                                   "--man-hours", "30", "--tokens-k", "168", "--cost", "$1.10"])
        self.assertEqual(code, 0, out)
        y, data = pm._load(self.f)
        st = pm.find_story(data, "PROJ-E01-S01-ST01")
        self.assertEqual(st["actual"]["tokens_k"], 168)
        self.assertEqual(st["actual"]["elapsed_hours"], 0.4)
        self.assertEqual(st["actual"]["cost"], "$1.10")

    def test_claude_runtime_forbids_na_tokens(self):
        code, _ = self.run_main(["set-actual", "--file", self.f, "--node", "story",
                                 "--story", "PROJ-E01-S01-ST01", "--tokens-k", "N/A",
                                 "--runtime", "claude"])
        self.assertEqual(code, 2)

    def test_other_runtime_allows_na(self):
        code, out = self.run_main(["set-actual", "--file", self.f, "--node", "story",
                                   "--story", "PROJ-E01-S01-ST01", "--tokens-k", "N/A",
                                   "--cost", "N/A", "--runtime", "other"])
        self.assertEqual(code, 0, out)


class TestVerify(Base):
    def _complete_story(self, runtime="other", tokens="168", cost="$1.10"):
        self.run_main(["set-status", "--file", self.f, "--story", "PROJ-E01-S01-ST01", "--status", "done"])
        self.run_main(["set-actual", "--file", self.f, "--node", "story",
                       "--story", "PROJ-E01-S01-ST01", "--elapsed-hours", "0.4",
                       "--man-hours", "30", "--tokens-k", tokens, "--cost", cost, "--runtime", runtime])
        # add a completion_evidence block by hand
        y, data = pm._load(self.f)
        st = pm.find_story(data, "PROJ-E01-S01-ST01")
        from ruamel.yaml.comments import CommentedMap
        ce = CommentedMap(); ce["fix_iterations"] = 0; ce["tests_passing"] = 42
        st["completion_evidence"] = ce
        pm._atomic_dump(y, data, self.f)

    def test_pass_when_complete(self):
        self._complete_story()
        code, out = self.run_main(["verify", "--file", self.f, "--scope", "story",
                                   "--story", "PROJ-E01-S01-ST01"])
        self.assertEqual(code, 0, out)
        self.assertIn("PASS", out)

    def test_fail_when_not_done(self):
        code, out = self.run_main(["verify", "--file", self.f, "--scope", "story",
                                   "--story", "PROJ-E01-S01-ST01"])
        self.assertEqual(code, 4)
        self.assertIn("status=", out)

    def test_fail_na_tokens_under_require(self):
        self._complete_story(runtime="other", tokens="N/A", cost="N/A")
        code, out = self.run_main(["verify", "--file", self.f, "--scope", "story",
                                   "--story", "PROJ-E01-S01-ST01", "--require-tokens"])
        self.assertEqual(code, 4)
        self.assertIn("N/A", out)

    def test_na_tokens_ok_without_require(self):
        self._complete_story(runtime="other", tokens="N/A", cost="N/A")
        code, out = self.run_main(["verify", "--file", self.f, "--scope", "story",
                                   "--story", "PROJ-E01-S01-ST01"])
        self.assertEqual(code, 0, out)


class TestProgress(Base):
    def test_append(self):
        self.run_main(["progress", "--ledger", self.ledger, "--msg", "PROGRESS: task 2/5", "--scope", "E01/S01"])
        self.run_main(["progress", "--ledger", self.ledger, "--msg", "PROGRESS: task 3/5", "--scope", "E01/S01"])
        with open(self.ledger, encoding="utf-8") as fh:
            lines = fh.read().strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("task 3/5", lines[1])


class TestSelfInstall(Base):
    def test_installs_when_absent(self):
        dest = os.path.join(self.d, "sub", "pm-status.py")
        code, out = self.run_main(["self-install", "--dest", dest])
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.exists(dest))
        self.assertIn("pm-status-version:", open(dest, encoding="utf-8").read())

    def test_skips_when_same_or_newer(self):
        dest = os.path.join(self.d, "pm-status.py")
        self.run_main(["self-install", "--dest", dest])
        code, out = self.run_main(["self-install", "--dest", dest])
        self.assertEqual(code, 0, out)
        self.assertIn("skipped", out)

    def test_upgrades_older_dest(self):
        dest = os.path.join(self.d, "pm-status.py")
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write("# pm-status-version: 0.0.1\nprint('old')\n")
        code, out = self.run_main(["self-install", "--dest", dest])
        self.assertEqual(code, 0, out)
        self.assertIn("0.0.1 ->", out)
        self.assertIn("pm-status-version:", open(dest, encoding="utf-8").read())

    def test_force_overwrites(self):
        dest = os.path.join(self.d, "pm-status.py")
        self.run_main(["self-install", "--dest", dest])
        code, out = self.run_main(["self-install", "--dest", dest, "--force"])
        self.assertEqual(code, 0, out)
        self.assertNotIn("skipped", out)


class TestAtomicAndCLI(Base):
    def test_end_to_end_subprocess(self):
        """Smoke-test the actual CLI entrypoint (not just in-process main)."""
        r = subprocess.run([sys.executable, SCRIPT, "set-status", "--file", self.f,
                            "--story", "PROJ-E01-S01-ST01", "--status", "done"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("OK set-status", r.stdout)

    def test_no_temp_files_left(self):
        self.run_main(["set-status", "--file", self.f, "--story", "PROJ-E01-S01-ST01", "--status", "done"])
        leftovers = [n for n in os.listdir(self.d) if n.startswith(".pm-status.")]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
