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

SAMPLE_V2 = """\
epics:
- key: 'E001'
  title: 'Epic 001'
  status: in-progress
  sprints:
  - key: 'S01'
    title: 'Sprint 01'
    status: in-progress
    stories:
    - key: E001-S01-001
      title: 'Story one'
      status: ready-for-dev
      classification: standard
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


class TestKeyLookup(Base):
    def setUp(self):
        super().setUp()
        self.f2 = os.path.join(self.d, "active-E001.yaml")
        with open(self.f2, "w", encoding="utf-8") as fh:
            fh.write(SAMPLE_V2)

    def test_find_epic_by_key(self):
        _, data = pm._load(self.f2)
        e = pm.find_epic(data, "E001")
        self.assertIsNotNone(e)
        self.assertEqual(e["key"], "E001")

    def test_find_sprint_by_key(self):
        _, data = pm._load(self.f2)
        s = pm.find_sprint(data, "E001", "S01")
        self.assertIsNotNone(s)
        self.assertEqual(s["key"], "S01")

    def test_find_story_in_v2_file(self):
        _, data = pm._load(self.f2)
        st = pm.find_story(data, "E001-S01-001")
        self.assertIsNotNone(st)

    def test_id_fallback_still_works(self):
        # Original SAMPLE uses 'id' — must not break
        _, data = pm._load(self.f)
        e = pm.find_epic(data, "01")
        self.assertIsNotNone(e)


class TestLockCommands(Base):
    def setUp(self):
        super().setUp()
        self.f2 = os.path.join(self.d, "E001-status.yaml")
        with open(self.f2, "w", encoding="utf-8") as fh:
            fh.write("epics:\n- key: 'E001'\n  title: 'test'\n  status: in-progress\n  sprints: []\n")

    def test_set_lock_writes_block(self):
        code, out = self.run_main(["set-lock", "--file", self.f2,
                                   "--session-id", "sess-abc", "--ttl-minutes", "30"])
        self.assertEqual(code, 0)
        _, data = pm._load(self.f2)
        self.assertIn("_lock", data)
        self.assertEqual(data["_lock"]["session_id"], "sess-abc")
        self.assertEqual(data["_lock"]["ttl_minutes"], 30)
        self.assertIn("claimed_at", data["_lock"])

    def test_set_lock_preserves_epics(self):
        self.run_main(["set-lock", "--file", self.f2,
                       "--session-id", "sess-abc", "--ttl-minutes", "30"])
        _, data = pm._load(self.f2)
        self.assertIn("epics", data)
        self.assertEqual(len(data["epics"]), 1)

    def test_clear_lock_removes_block(self):
        self.run_main(["set-lock", "--file", self.f2,
                       "--session-id", "sess-abc", "--ttl-minutes", "30"])
        code, out = self.run_main(["clear-lock", "--file", self.f2])
        self.assertEqual(code, 0)
        _, data = pm._load(self.f2)
        self.assertNotIn("_lock", data)

    def test_clear_lock_idempotent(self):
        # clear on file with no lock must succeed
        code, _ = self.run_main(["clear-lock", "--file", self.f2])
        self.assertEqual(code, 0)

    def test_check_lock_no_lock_is_free(self):
        code, _ = self.run_main(["check-lock", "--file", self.f2, "--session-id", "sess-xyz"])
        self.assertEqual(code, 0)

    def test_check_lock_own_session_is_free(self):
        self.run_main(["set-lock", "--file", self.f2,
                       "--session-id", "sess-abc", "--ttl-minutes", "30"])
        code, _ = self.run_main(["check-lock", "--file", self.f2, "--session-id", "sess-abc"])
        self.assertEqual(code, 0)

    def test_check_lock_other_session_within_ttl_is_blocked(self):
        self.run_main(["set-lock", "--file", self.f2,
                       "--session-id", "sess-abc", "--ttl-minutes", "30"])
        code, out = self.run_main(["check-lock", "--file", self.f2, "--session-id", "sess-xyz"])
        self.assertEqual(code, 5)
        self.assertIn("sess-abc", out)


class TestFlock(Base):
    def test_set_status_with_flock_flag_succeeds(self):
        # Basic: --flock should not break normal operation
        code, out = self.run_main([
            "set-status", "--file", self.f, "--story", "PROJ-E01-S01-ST01",
            "--status", "in-progress", "--flock",
        ])
        self.assertEqual(code, 0)
        _, data = pm._load(self.f)
        st = pm.find_story(data, "PROJ-E01-S01-ST01")
        self.assertEqual(st["status"], "in-progress")

    def test_set_actual_with_flock_flag_succeeds(self):
        code, out = self.run_main([
            "set-actual", "--file", self.f, "--node", "story",
            "--story", "PROJ-E01-S01-ST01",
            "--elapsed-hours", "2.5", "--man-hours", "3.0",
            "--tokens-k", "N/A", "--cost", "N/A",
            "--runtime", "other", "--flock",
        ])
        self.assertEqual(code, 0)

    def test_set_estimate_with_flock_flag_succeeds(self):
        code, out = self.run_main([
            "set-estimate", "--file", self.f,
            "--epic", "01",
            "--man-hours-low", "10", "--man-hours-high", "16",
            "--flock",
        ])
        self.assertEqual(code, 0)


class TestSetEstimate(Base):
    def setUp(self):
        super().setUp()
        self.f2 = os.path.join(self.d, "E001-status.yaml")
        with open(self.f2, "w", encoding="utf-8") as fh:
            fh.write(
                "epics:\n- key: 'E001'\n  title: 'test'\n  status: in-progress\n"
                "  sprints:\n  - key: 'S01'\n    title: 'sp'\n    status: in-progress\n"
                "    stories:\n    - key: E001-S01-001\n      title: 's'\n      status: backlog\n"
                "      classification: standard\n"
            )

    def test_set_estimate_epic(self):
        code, out = self.run_main([
            "set-estimate", "--file", self.f2,
            "--epic", "E001",
            "--man-hours-low", "10", "--man-hours-high", "16",
            "--time-hours-low", "3", "--time-hours-high", "5",
            "--confidence", "medium",
        ])
        self.assertEqual(code, 0)
        _, data = pm._load(self.f2)
        e = pm.find_epic(data, "E001")
        self.assertIn("estimate", e)
        self.assertEqual(e["estimate"]["man_hours_low"], 10.0)
        self.assertEqual(e["estimate"]["man_hours_high"], 16.0)
        self.assertEqual(e["estimate"]["confidence"], "medium")

    def test_set_estimate_sprint(self):
        code, out = self.run_main([
            "set-estimate", "--file", self.f2,
            "--epic", "E001", "--sprint", "S01",
            "--tokens-k-min", "120", "--tokens-k-max", "200",
            "--cost-low", "0.80", "--cost-high", "1.40",
        ])
        self.assertEqual(code, 0)
        _, data = pm._load(self.f2)
        s = pm.find_sprint(data, "E001", "S01")
        self.assertIn("estimate", s)
        self.assertEqual(s["estimate"]["tokens_k_min"], 120)
        self.assertEqual(s["estimate"]["confidence"], "low")  # missing some fields → low

    def test_set_estimate_story(self):
        code, out = self.run_main([
            "set-estimate", "--file", self.f2,
            "--story", "E001-S01-001",
            "--man-hours", "4", "--time-hours", "1.5",
            "--tokens-k", "40", "--cost", "0.28",
        ])
        self.assertEqual(code, 0)
        _, data = pm._load(self.f2)
        st = pm.find_story(data, "E001-S01-001")
        self.assertIn("estimate", st)
        self.assertEqual(st["estimate"]["man_hours"], 4.0)

    def test_set_estimate_story_uses_single_value_fields(self):
        # Stories get single values (not low/high) for man_hours, time_hours, tokens_k, cost
        code, _ = self.run_main([
            "set-estimate", "--file", self.f2, "--story", "E001-S01-001",
            "--man-hours", "4", "--time-hours", "1.5",
        ])
        self.assertEqual(code, 0)
        _, data = pm._load(self.f2)
        est = pm.find_story(data, "E001-S01-001")["estimate"]
        self.assertIn("man_hours", est)
        self.assertNotIn("man_hours_low", est)  # stories use single value, not range


ISSUES_SAMPLE = """\
backlog:
- key: BL-E001-001
  epic: '001'
  sprint: '01'
  title: Existing issue
  source: adversarial (ADV-L-01)
  severity: Low
  status: backlog
"""

ARCHIVE_SAMPLE = """\
epics:
- key: E001
  title: Auth Layer
  status: done
  sprints: []
"""


class TestSetField(Base):
    def setUp(self):
        super().setUp()
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write(SAMPLE_V2)

    def test_sets_simple_field(self):
        code, out = self.run_main(["set-field", "--file", self.f,
                                   "--node", "epic.E001",
                                   "--field", "closed.date",
                                   "--value", "2026-08-15"])
        self.assertEqual(code, 0, out)
        y, data = pm._load(self.f)
        epic = pm.find_epic(data, "E001")
        self.assertEqual(epic["closed"]["date"], "2026-08-15")

    def test_sets_nested_field_creates_intermediate(self):
        code, out = self.run_main(["set-field", "--file", self.f,
                                   "--node", "epic.E001",
                                   "--field", "retrospective.summary",
                                   "--value", "All done"])
        self.assertEqual(code, 0, out)
        y, data = pm._load(self.f)
        epic = pm.find_epic(data, "E001")
        self.assertEqual(epic["retrospective"]["summary"], "All done")

    def test_node_not_found_exits_3(self):
        code, _ = self.run_main(["set-field", "--file", self.f,
                                  "--node", "epic.E999",
                                  "--field", "closed.date",
                                  "--value", "2026-08-15"])
        self.assertEqual(code, 3)


class TestAppendIssue(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.f = os.path.join(self.d, "sprint-status-issues.yaml")

    def run_main(self, argv):
        buf = io.StringIO()
        code = 0
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        return code, buf.getvalue()

    def test_creates_file_if_absent(self):
        code, out = self.run_main(["append-issue", "--file", self.f,
                                   "--key", "BL-E001-001", "--epic", "001",
                                   "--sprint", "01", "--title", "Rate limit",
                                   "--source", "adversarial (ADV-L-01)", "--severity", "Low"])
        self.assertEqual(code, 0, out)
        y, data = pm._load(self.f)
        self.assertEqual(len(data["backlog"]), 1)
        self.assertEqual(data["backlog"][0]["key"], "BL-E001-001")

    def test_appends_to_existing_list(self):
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write(ISSUES_SAMPLE)
        self.run_main(["append-issue", "--file", self.f,
                       "--key", "BL-E001-002", "--epic", "001",
                       "--sprint", "", "--title", "New issue",
                       "--source", "red-team (RT-M-01)", "--severity", "Medium"])
        y, data = pm._load(self.f)
        self.assertEqual(len(data["backlog"]), 2)
        self.assertEqual(data["backlog"][1]["key"], "BL-E001-002")

    def test_invalid_severity_rejected(self):
        code, _ = self.run_main(["append-issue", "--file", self.f,
                                  "--key", "BL-E001-003", "--epic", "001",
                                  "--sprint", "", "--title", "T",
                                  "--source", "S", "--severity", "Trivial"])
        self.assertEqual(code, 2)


class TestArchiveEpic(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.src = os.path.join(self.d, "E001-status.yaml")
        self.dest = os.path.join(self.d, "sprint-status-archived.yaml")
        with open(self.src, "w", encoding="utf-8") as fh:
            fh.write(ARCHIVE_SAMPLE)

    def run_main(self, argv):
        buf = io.StringIO()
        code = 0
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        return code, buf.getvalue()

    def test_archives_to_new_dest(self):
        code, out = self.run_main(["archive-epic", "--source", self.src, "--dest", self.dest])
        self.assertEqual(code, 0, out)
        y, data = pm._load(self.dest)
        self.assertEqual(len(data["epics"]), 1)
        self.assertEqual(data["epics"][0]["key"], "E001")
        self.assertEqual(data["epics"][0]["status"], "done")

    def test_appends_to_existing_archived(self):
        with open(self.dest, "w", encoding="utf-8") as fh:
            fh.write("epics:\n- key: E000\n  title: Old\n  status: done\n  sprints: []\n")
        self.run_main(["archive-epic", "--source", self.src, "--dest", self.dest])
        y, data = pm._load(self.dest)
        self.assertEqual(len(data["epics"]), 2)
        self.assertEqual(data["epics"][1]["key"], "E001")

    def test_missing_source_exits_3(self):
        code, _ = self.run_main(["archive-epic", "--source", "/nonexistent.yaml", "--dest", self.dest])
        self.assertEqual(code, 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
