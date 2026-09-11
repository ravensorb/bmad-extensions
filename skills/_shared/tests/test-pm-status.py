#!/usr/bin/env python3
"""
Tests for pm-status.py — run with: python3 test-pm-status.py  (or `uv run`).
Exercises the sharded split-directory layout resolution, key-based node addressing
(set-status/set-actual/set-estimate/set-field/verify), epic directory moves
(move-epic/archive-epic), the unconverted --file-based commands (locks,
append-issue, self-install), comment/order preservation, the events.jsonl
transition log, the progress report, and verify exit codes.
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "pm-status.py")

sys.path.insert(0, os.path.dirname(HERE))
import importlib.util

spec = importlib.util.spec_from_file_location("pm_status", SCRIPT)
pm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm)


# -- temp-dir leak guard ---------------------------------------------------------------- #
# Every tempfile.mkdtemp()/mkstemp()/NamedTemporaryFile() made while this suite runs lands in
# one private run directory (tempfile.tempdir), and tearDownModule fails the run if anything
# is left in it. Fixtures without cleanup once left 60,936 directories in /tmp and exhausted
# its inodes. Set in setUpModule, not at import, so a child process that re-imports this
# module never creates a run directory it would not remove.
_RUN_TMP = None


def setUpModule():
    global _RUN_TMP
    _RUN_TMP = tempfile.mkdtemp(prefix="test-pm-status-")
    tempfile.tempdir = _RUN_TMP


def tearDownModule():
    tempfile.tempdir = None
    leaked = sorted(os.listdir(_RUN_TMP))
    shutil.rmtree(_RUN_TMP, ignore_errors=True)
    if leaked:
        raise AssertionError(f"temp-dir leak: {len(leaked)} entr"
                             f"{'y' if len(leaked) == 1 else 'ies'} left by tests without "
                             f"cleanup: {', '.join(leaked[:5])}")


class Base(unittest.TestCase):
    """Minimal fixture: a scratch dir + in-process CLI runner. No status-file
    content is assumed here — commands that need a node tree use
    TestLayoutResolution instead."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)

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


class TestSelfInstall(Base):
    def test_installs_when_absent(self):
        dest = os.path.join(self.d, "sub", "pm-status.py")
        code, out = self.run_main(["self-install", "--dest", dest])
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.exists(dest))
        with open(dest, encoding="utf-8") as fh:
            self.assertIn("pm-status-version:", fh.read())

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
        with open(dest, encoding="utf-8") as fh:
            self.assertIn("pm-status-version:", fh.read())

    def test_force_overwrites(self):
        dest = os.path.join(self.d, "pm-status.py")
        self.run_main(["self-install", "--dest", dest])
        code, out = self.run_main(["self-install", "--dest", dest, "--force"])
        self.assertEqual(code, 0, out)
        self.assertNotIn("skipped", out)

    def test_reinstalls_same_version_with_different_content(self):
        """The regression that shipped: equal marker, different bytes, skipped forever.

        A hand-maintained version marker drifts -- ten commits changed this script under
        2.3.0, and one more changed it after the bump to 2.4.0. Any project that installed
        at those moments kept a stale copy that self-install reported as up to date. One
        sat 920 lines behind with a Critical fix missing. Equal version must therefore mean
        "check the bytes", never "assume identical".
        """
        dest = os.path.join(self.d, "pm-status.py")
        self.run_main(["self-install", "--dest", dest])
        with open(dest, encoding="utf-8") as fh:
            real = fh.read()

        truncated = real[: len(real) // 3]
        self.assertIn("pm-status-version:", truncated,
                      "premise: the stale copy still carries the SAME marker")
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(truncated)

        out_buf, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out_buf), redirect_stderr(err):
                code = pm.main(["self-install", "--dest", dest])
        except SystemExit as e:
            code = e.code
        out = out_buf.getvalue()
        self.assertEqual(code, 0, out)
        self.assertNotIn("skipped", out)
        self.assertIn("content differs from this copy; reinstalling", err.getvalue())
        with open(dest, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), real,
                             "a same-version copy with different content must be replaced")

    def test_skips_only_when_bytes_are_identical(self):
        dest = os.path.join(self.d, "pm-status.py")
        self.run_main(["self-install", "--dest", dest])
        code, out = self.run_main(["self-install", "--dest", dest])
        self.assertEqual(code, 0, out)
        self.assertIn("already this exact script", out)

    def test_refuses_to_downgrade_a_strictly_newer_dest(self):
        """Version still governs the one thing content cannot express: a real downgrade."""
        dest = os.path.join(self.d, "pm-status.py")
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write("# pm-status-version: 99.0.0\nprint('newer')\n")
        code, out = self.run_main(["self-install", "--dest", dest])
        self.assertEqual(code, 0, out)
        self.assertIn("refusing to downgrade", out)
        with open(dest, encoding="utf-8") as fh:
            self.assertIn("print('newer')", fh.read())


class TestLockCommands(Base):
    """set-lock/clear-lock/check-lock using --state-root and --epic."""

    def setUp(self):
        super().setUp()
        self.state_root = os.path.join(self.d, "state")
        epic_dir = os.path.join(self.state_root, "active", "epic-001")
        os.makedirs(epic_dir)
        self.epic_file = os.path.join(epic_dir, "epic.yaml")
        with open(self.epic_file, "w", encoding="utf-8") as fh:
            fh.write("key: 'E001'\ntitle: 'test'\nstatus: in-progress\n")

    def test_set_lock_writes_block(self):
        code, out = self.run_main(["set-lock", "--state-root", self.state_root, "--epic", "E001",
                                   "--session-id", "sess-abc", "--ttl-minutes", "30"])
        self.assertEqual(code, 0)
        _, data = pm.load_node(self.epic_file)
        self.assertIn("_lock", data)
        self.assertEqual(data["_lock"]["session_id"], "sess-abc")
        self.assertEqual(data["_lock"]["ttl_minutes"], 30)
        self.assertIn("claimed_at", data["_lock"])

    def test_set_lock_writes_lock_first(self):
        self.run_main(["set-lock", "--state-root", self.state_root, "--epic", "E001",
                       "--session-id", "sess-abc", "--ttl-minutes", "30"])
        _, data = pm.load_node(self.epic_file)
        self.assertEqual(list(data.keys())[0], "_lock")

    def test_clear_lock_removes_block(self):
        self.run_main(["set-lock", "--state-root", self.state_root, "--epic", "E001",
                       "--session-id", "sess-abc", "--ttl-minutes", "30"])
        code, out = self.run_main(["clear-lock", "--state-root", self.state_root, "--epic", "E001"])
        self.assertEqual(code, 0)
        _, data = pm.load_node(self.epic_file)
        self.assertNotIn("_lock", data)

    def test_clear_lock_idempotent(self):
        # clear on file with no lock must succeed
        code, _ = self.run_main(["clear-lock", "--state-root", self.state_root, "--epic", "E001"])
        self.assertEqual(code, 0)

    def test_check_lock_no_lock_is_free(self):
        code, _ = self.run_main(["check-lock", "--state-root", self.state_root, "--epic", "E001",
                                  "--session-id", "sess-xyz"])
        self.assertEqual(code, 0)

    def test_check_lock_own_session_is_free(self):
        self.run_main(["set-lock", "--state-root", self.state_root, "--epic", "E001",
                       "--session-id", "sess-abc", "--ttl-minutes", "30"])
        code, _ = self.run_main(["check-lock", "--state-root", self.state_root, "--epic", "E001",
                                  "--session-id", "sess-abc"])
        self.assertEqual(code, 0)

    def test_check_lock_other_session_within_ttl_is_blocked(self):
        self.run_main(["set-lock", "--state-root", self.state_root, "--epic", "E001",
                       "--session-id", "sess-abc", "--ttl-minutes", "30"])
        code, out = self.run_main(["check-lock", "--state-root", self.state_root, "--epic", "E001",
                                    "--session-id", "sess-xyz"])
        self.assertEqual(code, 5)
        self.assertIn("sess-abc", out)


class TestSetLockMutualExclusion(Base):
    """set-lock must itself enforce mutual exclusion -- it used to unconditionally
    overwrite `_lock` with no read-compare-write, so two concurrent sessions claiming
    the same epic would silently clobber each other and both proceed. Only check-lock
    compared session_id/TTL, and nothing in the epic loop calls check-lock before
    set-lock, so that comparison never ran. set-lock must now refuse a live foreign
    lock (exit 5, matching check-lock's existing "locked" code), while still allowing
    a no-op claim, an owner's re-claim, and a takeover of an expired lock."""

    def setUp(self):
        super().setUp()
        self.state_root = os.path.join(self.d, "state")
        epic_dir = os.path.join(self.state_root, "active", "epic-001")
        os.makedirs(epic_dir)
        self.epic_file = os.path.join(epic_dir, "epic.yaml")
        with open(self.epic_file, "w", encoding="utf-8") as fh:
            fh.write("key: 'E001'\ntitle: 'test'\nstatus: in-progress\n")

    def _write_lock(self, session_id, claimed_at, ttl_minutes=30, extra=""):
        with open(self.epic_file, "w", encoding="utf-8") as fh:
            fh.write("_lock:\n"
                      f"  session_id: '{session_id}'\n"
                      f"  claimed_at: '{claimed_at}'\n"
                      f"  ttl_minutes: {ttl_minutes}\n"
                      f"{extra}"
                      "title: 'test'\nstatus: in-progress\n")

    def test_claims_when_no_existing_lock(self):
        code, out = self.run_main(["set-lock", "--state-root", self.state_root,
                                    "--epic", "E001", "--session-id", "sess-a",
                                    "--ttl-minutes", "30"])
        self.assertEqual(code, 0, out)
        _, data = pm.load_node(self.epic_file)
        self.assertEqual(data["_lock"]["session_id"], "sess-a")

    def test_same_session_reclaims_without_refusing(self):
        """A retry by the owner must not deadlock itself against its own lock."""
        self.run_main(["set-lock", "--state-root", self.state_root, "--epic", "E001",
                       "--session-id", "sess-a", "--ttl-minutes", "30"])
        _, before = pm.load_node(self.epic_file)
        first_claimed = before["_lock"]["claimed_at"]
        code, out = self.run_main(["set-lock", "--state-root", self.state_root,
                                    "--epic", "E001", "--session-id", "sess-a",
                                    "--ttl-minutes", "30"])
        self.assertEqual(code, 0, out)
        _, after = pm.load_node(self.epic_file)
        self.assertEqual(after["_lock"]["session_id"], "sess-a")
        self.assertIsNotNone(after["_lock"]["claimed_at"])
        # Same-second reclaim can legitimately produce an identical timestamp;
        # the contract under test is "does not deadlock / does not refuse", not
        # that the clock necessarily ticked between two in-process calls -- so
        # this only pins that the field is still present and well-formed.
        self.assertIsInstance(first_claimed, str)

    def test_takes_over_a_stale_lock_from_another_session(self):
        self._write_lock("sess-a", "2020-01-01T00:00:00Z", ttl_minutes=1)
        code, out = self.run_main(["set-lock", "--state-root", self.state_root,
                                    "--epic", "E001", "--session-id", "sess-b",
                                    "--ttl-minutes", "30"])
        self.assertEqual(code, 0, out)
        self.assertIn("sess-a", out, "takeover must name the session it took the lock from")
        _, data = pm.load_node(self.epic_file)
        self.assertEqual(data["_lock"]["session_id"], "sess-b")

    def test_refuses_a_live_foreign_lock(self):
        self.run_main(["set-lock", "--state-root", self.state_root, "--epic", "E001",
                       "--session-id", "sess-a", "--ttl-minutes", "30"])
        code, out = self.run_main(["set-lock", "--state-root", self.state_root,
                                    "--epic", "E001", "--session-id", "sess-b",
                                    "--ttl-minutes", "30"])
        self.assertEqual(code, 5, out)
        self.assertIn("sess-a", out)
        _, data = pm.load_node(self.epic_file)
        self.assertEqual(data["_lock"]["session_id"], "sess-a",
                          "a refused claim must not touch the persisted lock")

    def test_refuses_malformed_lock_not_a_mapping(self):
        with open(self.epic_file, "w", encoding="utf-8") as fh:
            fh.write("_lock: 'just-a-string'\ntitle: 'test'\nstatus: in-progress\n")
        code, out = self.run_main(["set-lock", "--state-root", self.state_root,
                                    "--epic", "E001", "--session-id", "sess-b",
                                    "--ttl-minutes", "30"])
        self.assertEqual(code, 5, out)
        _, data = pm.load_node(self.epic_file)
        self.assertEqual(data["_lock"], "just-a-string",
                          "a refused claim must not touch the persisted lock")

    def test_refuses_malformed_lock_missing_claimed_at(self):
        with open(self.epic_file, "w", encoding="utf-8") as fh:
            fh.write("_lock:\n  session_id: 'sess-a'\n  ttl_minutes: 30\n"
                     "title: 'test'\nstatus: in-progress\n")
        code, out = self.run_main(["set-lock", "--state-root", self.state_root,
                                    "--epic", "E001", "--session-id", "sess-b",
                                    "--ttl-minutes", "30"])
        self.assertEqual(code, 5, out)
        _, data = pm.load_node(self.epic_file)
        self.assertNotIn("claimed_at", data["_lock"])

    def test_refuses_malformed_lock_unparseable_timestamp(self):
        self._write_lock("sess-a", "not-a-timestamp", ttl_minutes=30)
        code, out = self.run_main(["set-lock", "--state-root", self.state_root,
                                    "--epic", "E001", "--session-id", "sess-b",
                                    "--ttl-minutes", "30"])
        self.assertEqual(code, 5, out)
        _, data = pm.load_node(self.epic_file)
        self.assertEqual(data["_lock"]["session_id"], "sess-a",
                          "a refused claim must not touch the persisted lock")


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

class TestAppendIssue(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.f = os.path.join(self.d, "sprint-status-issues.yaml")

    def run_main(self, argv):
        buf = io.StringIO()
        code = 0
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
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

    # --- D1: key is now optional and self-allocating --------------------- #

    def test_key_is_optional(self):
        """--key is no longer required — nothing in any step file ever bound {nnn},
        so the caller must be able to omit it entirely."""
        code, out = self.run_main(["append-issue", "--file", self.f,
                                   "--epic", "001", "--title", "Rate limit",
                                   "--source", "adversarial (ADV-L-01)", "--severity", "Low"])
        self.assertEqual(code, 0, out)

    def test_allocates_001_from_empty_backlog(self):
        code, out = self.run_main(["append-issue", "--file", self.f,
                                   "--epic", "001", "--title", "First finding",
                                   "--source", "qa", "--severity", "Low"])
        self.assertEqual(code, 0, out)
        y, data = pm._load(self.f)
        self.assertEqual(data["backlog"][0]["key"], "BL-E001-001")
        self.assertIn("BL-E001-001", out)

    def test_allocates_next_after_highest_existing(self):
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write("backlog:\n"
                     "- key: BL-E001-007\n  epic: '001'\n  sprint: ''\n"
                     "  title: Prior\n  source: qa\n  severity: Low\n  status: backlog\n")
        code, out = self.run_main(["append-issue", "--file", self.f,
                                   "--epic", "001", "--title", "Next finding",
                                   "--source", "qa", "--severity", "Low"])
        self.assertEqual(code, 0, out)
        y, data = pm._load(self.f)
        self.assertEqual(data["backlog"][-1]["key"], "BL-E001-008")

    def test_allocation_is_per_epic(self):
        self.run_main(["append-issue", "--file", self.f,
                       "--epic", "001", "--title", "E1 finding A",
                       "--source", "qa", "--severity", "Low"])
        self.run_main(["append-issue", "--file", self.f,
                       "--epic", "002", "--title", "E2 finding A",
                       "--source", "qa", "--severity", "Low"])
        code, out = self.run_main(["append-issue", "--file", self.f,
                                   "--epic", "001", "--title", "E1 finding B",
                                   "--source", "qa", "--severity", "Low"])
        self.assertEqual(code, 0, out)
        y, data = pm._load(self.f)
        keys = [i["key"] for i in data["backlog"]]
        self.assertEqual(keys, ["BL-E001-001", "BL-E002-001", "BL-E001-002"])

    def test_allocation_ignores_malformed_existing_keys(self):
        """issues.yaml is hand-editable — a garbage key must not crash allocation."""
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write("backlog:\n"
                     "- key: BL-EXXX-yy\n  epic: '001'\n  sprint: ''\n"
                     "  title: Garbage\n  source: qa\n  severity: Low\n  status: backlog\n"
                     "- not-a-mapping-just-a-string\n"
                     "- key: BL-E001-003\n  epic: '001'\n  sprint: ''\n"
                     "  title: Valid\n  source: qa\n  severity: Low\n  status: backlog\n")
        code, out = self.run_main(["append-issue", "--file", self.f,
                                   "--epic", "001", "--title", "Next finding",
                                   "--source", "qa", "--severity", "Low"])
        self.assertEqual(code, 0, out)
        y, data = pm._load(self.f)
        self.assertEqual(data["backlog"][-1]["key"], "BL-E001-004")

    # --- D2: explicit-key collision and content-duplicate detection ------ #

    def test_explicit_duplicate_key_exits_2(self):
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write(ISSUES_SAMPLE)
        code, out = self.run_main(["append-issue", "--file", self.f,
                                   "--key", "BL-E001-001", "--epic", "001",
                                   "--sprint", "01", "--title", "A different finding",
                                   "--source", "qa", "--severity", "Low"])
        self.assertEqual(code, 2)
        y, data = pm._load(self.f)
        self.assertEqual(len(data["backlog"]), 1, "the duplicate must not be appended")

    def test_explicit_duplicate_key_message_on_stderr(self):
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write(ISSUES_SAMPLE)
        buf_out, buf_err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(buf_out), redirect_stderr(buf_err):
                code = pm.main(["append-issue", "--file", self.f,
                               "--key", "BL-E001-001", "--epic", "001",
                               "--sprint", "01", "--title", "A different finding",
                               "--source", "qa", "--severity", "Low"])
        except SystemExit as e:
            code = e.code
        self.assertEqual(code, 2)
        self.assertIn("Existing issue", buf_err.getvalue())
        y, data = pm._load(self.f)
        self.assertEqual(len(data["backlog"]), 1)

    def test_content_duplicate_is_skipped_exits_0(self):
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write(ISSUES_SAMPLE)
        code, out = self.run_main(["append-issue", "--file", self.f,
                                   "--epic", "001", "--sprint", "01",
                                   "--title", "  Existing   issue  ",
                                   "--source", "adversarial (ADV-L-01)", "--severity", "Low"])
        self.assertEqual(code, 0, out)
        self.assertIn("BL-E001-001", out)
        y, data = pm._load(self.f)
        self.assertEqual(len(data["backlog"]), 1, "no second row should be written")

    def test_content_duplicate_requires_all_four_fields(self):
        """A different source is NOT a duplicate — under-matching would lose findings."""
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write(ISSUES_SAMPLE)
        code, out = self.run_main(["append-issue", "--file", self.f,
                                   "--epic", "001", "--sprint", "01",
                                   "--title", "Existing issue",
                                   "--source", "red-team (RT-L-02)", "--severity", "Low"])
        self.assertEqual(code, 0, out)
        y, data = pm._load(self.f)
        self.assertEqual(len(data["backlog"]), 2, "different source is a distinct finding")

    def test_allow_duplicate_forces_append(self):
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write(ISSUES_SAMPLE)
        code, out = self.run_main(["append-issue", "--file", self.f,
                                   "--epic", "001", "--sprint", "01",
                                   "--title", "Existing issue",
                                   "--source", "adversarial (ADV-L-01)", "--severity", "Low",
                                   "--allow-duplicate"])
        self.assertEqual(code, 0, out)
        y, data = pm._load(self.f)
        self.assertEqual(len(data["backlog"]), 2)

    # --- D3: malformed 'backlog' field is refused, not silently repaired - #

    def _assert_malformed_backlog_refused(self, backlog_yaml_line):
        """Shared body for the {} and 'text' malformed-backlog cases: exit 2,
        a clear stderr message, and the file byte-for-byte unmodified -- a
        `backlog` that cannot say what is already recorded cannot be trusted
        to receive a new item without hiding whatever was there, mirroring
        cmd_adr_reserve's malformed-'reserved' guard."""
        content = backlog_yaml_line
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write(content)
        buf_err = io.StringIO()
        try:
            with redirect_stderr(buf_err):
                code = pm.main(["append-issue", "--file", self.f,
                                "--epic", "001", "--title", "Next finding",
                                "--source", "qa", "--severity", "Low"])
        except SystemExit as e:
            code = e.code
        self.assertEqual(code, 2)
        err = buf_err.getvalue()
        self.assertIn("backlog", err)
        self.assertIn("malformed", err)
        with open(self.f, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), content, "file must be left unmodified on refusal")

    def test_malformed_backlog_dict_is_refused_not_silently_repaired(self):
        self._assert_malformed_backlog_refused("backlog: {}\n")

    def test_malformed_backlog_string_is_refused_not_silently_repaired(self):
        self._assert_malformed_backlog_refused("backlog: text\n")


ISSUES_FIXTURE = """\
backlog:
- key: BL-E001-001
  epic: '001'
  sprint: '01'
  title: Sprint-level issue
  source: qa
  severity: Low
  status: backlog
- key: BL-E001-002
  epic: '001'
  sprint: ''
  title: Epic-level issue
  source: arch-review
  severity: High
  status: backlog
- key: BL-E002-001
  epic: '002'
  sprint: '01'
  title: Other-epic issue
  source: red-team
  severity: Medium
  status: backlog
- key: BL-E000-001
  epic: '000'
  sprint: ''
  title: Repo-global issue
  source: adversarial
  severity: Critical
  status: backlog
"""

from unittest import mock


def _build_issue_tree(root):
    """State tree for issue-lifecycle tests. Epic/sprint nodes are hand-written
    because no verb creates them; every ISSUE is created through the real CLI.
      active/epic-001: S01 in-progress, S02 backlog
      planned/epic-005: S01 backlog
    """
    nodes = {
        "active/epic-001/epic.yaml": "key: 'E001'\ntitle: 'Foundation'\nstatus: in-progress\n",
        "active/epic-001/sprint-01/sprint.yaml":
            "key: 'S01'\nepic: 'E001'\ntitle: 'One'\nstatus: in-progress\n",
        "active/epic-001/sprint-02/sprint.yaml":
            "key: 'S02'\nepic: 'E001'\ntitle: 'Two'\nstatus: backlog\n",
        "planned/epic-005/epic.yaml": "key: 'E005'\ntitle: 'Later'\nstatus: backlog\n",
        "planned/epic-005/sprint-01/sprint.yaml":
            "key: 'S01'\nepic: 'E005'\ntitle: 'Later one'\nstatus: backlog\n",
    }
    for rel, text in nodes.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)


class IssueBase(Base):
    """impl/ is the artifacts root; impl/state the state root."""

    def setUp(self):
        super().setUp()
        self.arts = os.path.join(self.d, "impl")
        self.root = os.path.join(self.arts, "state")
        _build_issue_tree(self.root)
        self.issues = os.path.join(self.root, "issues.yaml")
        self.resolved = os.path.join(self.root, "issues-resolved.yaml")

    def run_all(self, argv):
        out, err = io.StringIO(), io.StringIO()
        code = 0
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        return code, out.getvalue(), err.getvalue()

    def append(self, title, epic="001", sprint="01", severity="Low",
               source="code-review (E001-S01-001)", *extra):
        return self.run_all(["append-issue", "--state-root", self.root, "--epic", epic,
                             "--sprint", sprint, "--title", title, "--source", source,
                             "--severity", severity, *extra])

    def load_open(self):
        return pm._load(self.issues)[1] or {}

    def load_resolved(self):
        return pm._load(self.resolved)[1] or {}

    def open_keys(self):
        return [str(i["key"]) for i in (self.load_open().get("backlog") or [])]

    def resolved_keys(self):
        return [str(i["key"]) for i in (self.load_resolved().get("resolved") or [])]

    def events(self, name=None):
        p = pm.events_path(self.root)
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as fh:
            evs = [json.loads(l) for l in fh if l.strip()]
        return [e for e in evs if name is None or e.get("event") == name]

    def assert_invariants(self):
        """Spec §1.4 invariants 1, 5 and 6, read from the issue files as written. Call it after
        an operation that should leave a valid state -- never in a test that builds an invalid
        one on purpose. Invariant 1's key set is both files plus every key an `issue_opened`
        event recorded, so a key that vanished from both files fails as well as one in both.
        Invariant 6 uses the spec's own form, not pm-status's canonical_bl_key."""
        files = {"issues.yaml": self.open_keys(), "issues-resolved.yaml": self.resolved_keys()}
        for name, keys in files.items():
            twice = sorted({k for k in keys if keys.count(k) > 1})
            self.assertEqual(twice, [], f"invariant 5: a key appears twice in {name}")
            bad = [k for k in keys if not re.fullmatch(r"BL-E[0-9]{3}-[0-9]{3}", k)]
            self.assertEqual(bad, [], f"invariant 6: a non-canonical key in {name}")
        opened = set()
        if os.path.isfile(pm.events_path(self.root)):
            opened = {str(e["key"]) for e in self.events("issue_opened")}
        o, r = set(files["issues.yaml"]), set(files["issues-resolved.yaml"])
        wrong = sorted(k for k in o | r | opened if (k in o) == (k in r))
        self.assertEqual(wrong, [], "invariant 1: a key is in both issue files, or in neither")

    def _crash_promote_before_scheduling(self, key="BL-E001-001", epic="001", sprint="02",
                                         cls="standard", extra=()):
        """Run promote-issue with the scheduling save failing: the story node and document are
        written, the item is not yet scheduled -- the state audit-issues finding 1d describes."""
        with mock.patch.object(pm.IssueStore, "save_open", side_effect=OSError("injected")):
            with self.assertRaises(OSError):
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    pm.main(["promote-issue", "--state-root", self.root, "--artifacts-root",
                             self.arts, "--key", key, "--epic", epic, "--sprint", sprint,
                             "--classification", cls, *extra])


class TestIssueAllocator(IssueBase):
    def test_hand_deleted_highest_key_is_never_reused(self):
        """The reproduced defect: after the newest item is deleted by hand, the old
        allocator ('highest surviving + 1') gave its key to an unrelated finding."""
        for t in ("A first", "B second", "C third"):
            self.assertEqual(self.append(t)[0], 0)
        y, data = pm._load(self.issues)
        data["backlog"] = [i for i in data["backlog"] if i["key"] != "BL-E001-003"]
        pm._atomic_dump(y, data, self.issues)
        code, out, err = self.append("D unrelated")
        self.assertEqual(code, 0, err)
        self.assertIn("BL-E001-004", out)
        self.assertNotIn("BL-E001-003", self.open_keys())

    def test_next_is_written_per_epic(self):
        self.append("A")
        self.append("B")
        self.append("C", epic="005", sprint="01", source="qa (Q-1)")
        nxt = self.load_open()["next"]
        self.assertEqual(int(nxt["001"]), 3)
        self.assertEqual(int(nxt["005"]), 2)

    def test_seeds_from_highest_suffix_in_both_files(self):
        for t in ("A", "B", "C", "D", "E"):
            self.append(t)
        y, data = pm._load(self.issues)
        del data["next"]
        pm._atomic_dump(y, data, self.issues)
        # a pre-existing resolved record that predates `next` (deliberately hand-built)
        with open(self.resolved, "w", encoding="utf-8") as fh:
            fh.write("resolved:\n- key: BL-E001-007\n  epic: '001'\n  title: old\n"
                     "  resolution: fixed\n")
        code, out, err = self.append("F")
        self.assertEqual(code, 0, err)
        self.assertIn("BL-E001-008", out)

    def test_hand_written_item_beyond_stale_next(self):
        self.append("A")
        y, data = pm._load(self.issues)
        from ruamel.yaml.comments import CommentedMap
        data["backlog"].append(CommentedMap([("key", "BL-E001-009"), ("epic", "001"),
                                             ("title", "hand"), ("status", "backlog")]))
        pm._atomic_dump(y, data, self.issues)
        self.assertIn("BL-E001-010", self.append("B")[1])

    def test_malformed_next_warns_and_never_goes_backwards(self):
        self.append("A")
        self.append("B")
        y, data = pm._load(self.issues)
        data["next"] = "garbage"
        pm._atomic_dump(y, data, self.issues)
        code, out, err = self.append("C")
        self.assertEqual(code, 0, err)
        self.assertIn("warning", err)
        self.assertIn("BL-E001-003", out)

    def test_explicit_key_is_canonicalized_and_raises_next(self):
        code, out, err = self.append("A", "001", "01", "Low", "qa", "--key", "BL-E1-5")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.open_keys(), ["BL-E001-005"])
        self.assertIn("BL-E001-006", self.append("B")[1])

    def test_explicit_key_epic_must_match(self):
        code, _, err = self.append("A", "001", "01", "Low", "qa", "--key", "BL-E002-001")
        self.assertEqual(code, 2)
        self.assertIn("epic", err)
        self.assertFalse(os.path.exists(self.issues))

    def test_explicit_key_that_cannot_be_canonical_is_refused(self):
        for bad in ("not-a-key", "BL-E1000-1", "BL-E001-000"):
            self.assertEqual(self.append("A", "001", "01", "Low", "qa", "--key", bad)[0], 2, bad)

    def test_explicit_key_present_in_resolved_file_is_refused(self):
        with open(self.resolved, "w", encoding="utf-8") as fh:
            fh.write("resolved:\n- key: BL-E001-004\n  epic: '001'\n  title: old\n"
                     "  resolution: fixed\n")
        code, _, err = self.append("A", "001", "01", "Low", "qa", "--key", "BL-E001-004")
        self.assertEqual(code, 2)
        self.assertIn("already exists", err)

    def test_state_root_with_mismatched_file_is_refused(self):
        code, _, err = self.run_all(["append-issue", "--state-root", self.root,
                                     "--file", os.path.join(self.d, "other.yaml"),
                                     "--epic", "001", "--title", "A", "--source", "qa",
                                     "--severity", "Low"])
        self.assertEqual(code, 2, err)

    def test_file_only_is_still_accepted(self):
        code, out, err = self.run_all(["append-issue", "--file", self.issues, "--epic", "001",
                                       "--title", "A", "--source", "qa", "--severity", "Low"])
        self.assertEqual(code, 0, err)
        self.assertEqual(self.open_keys(), ["BL-E001-001"])

    def test_neither_file_nor_state_root_is_refused(self):
        code, _, _ = self.run_all(["append-issue", "--epic", "001", "--title", "A",
                                   "--source", "qa", "--severity", "Low"])
        self.assertEqual(code, 2)

    def test_append_writes_issue_opened_event(self):
        self.append("A", "001", "01", "Medium", "qa", "--session-id", "S-1")
        ev = self.events("issue_opened")
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["key"], "BL-E001-001")
        self.assertEqual(ev[0]["session"], "S-1")
        self.assertEqual(ev[0]["cause"], "cli")
        self.assertEqual(ev[0]["severity"], "Medium")
        self.assertIn("ts", ev[0])

    def test_allocation_refuses_past_999(self):
        """A key has three digits: allocating BL-E001-1000 would mint a non-canonical key."""
        self.assertEqual(self.append("A", "001", "01", "Low", "qa", "--key", "BL-E001-999")[0], 0)
        before = _tree_snapshot(self.root)
        code, out, err = self.append("B")
        self.assertEqual(code, 2, out)
        self.assertIn("BL-E001-999", err)
        self.assertEqual(_tree_snapshot(self.root), before)


def _dump_failing_on(n):
    """Patch pm._atomic_dump so its n-th call raises OSError('injected') -- a crash
    between two writes. Use: `with _dump_failing_on(2): ...`. Shared by every
    crash-injection test so the injection logic exists once."""
    real, calls = pm._atomic_dump, {"n": 0}

    def flaky(y, data, path):
        calls["n"] += 1
        if calls["n"] == n:
            raise OSError("injected")
        return real(y, data, path)

    return mock.patch.object(pm, "_atomic_dump", flaky)


class TestResolveIssue(IssueBase):
    def resolve(self, key, resolution, *extra):
        return self.run_all(["resolve-issue", "--state-root", self.root, "--key", key,
                             "--resolution", resolution, *extra])

    def test_resolve_moves_the_item_whole(self):
        self.append("A", "001", "01", "Medium")
        code, out, err = self.resolve("BL-E001-001", "wontfix", "--note", "accepted risk")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.open_keys(), [])
        self.assertEqual(self.resolved_keys(), ["BL-E001-001"])
        entry = self.load_resolved()["resolved"][0]
        self.assertEqual(entry["status"], "resolved")
        self.assertEqual(entry["resolution"], "wontfix")
        self.assertEqual(entry["note"], "accepted risk")
        self.assertEqual(entry["severity"], "Medium")
        self.assertTrue(entry["resolved_at"])
        self.assert_invariants()

    def test_resolving_the_highest_then_appending_never_reuses(self):
        for t in ("A", "B", "C"):
            self.append(t)
        self.assertEqual(self.resolve("BL-E001-003", "obsolete", "--note", "gone")[0], 0)
        self.assertIn("BL-E001-004", self.append("D")[1])
        self.assert_invariants()

    def test_required_flags_refuse_and_write_nothing(self):
        self.append("A")
        with open(self.issues, encoding="utf-8") as fh:
            before = fh.read()
        for argv in (("fixed",), ("wontfix",), ("obsolete",), ("duplicate",),
                     ("fixed", "--ref", "later")):
            code, _, _ = self.resolve("BL-E001-001", *argv)
            self.assertEqual(code, 2, argv)
        with open(self.issues, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), before)
        self.assertFalse(os.path.exists(self.resolved))

    def test_fixed_ref_accepts_story_key_or_sha(self):
        self.append("A")
        self.append("B", "001", "02")
        self.assertEqual(self.resolve("BL-E001-001", "fixed", "--ref", "E001-S01-001")[0], 0)
        self.assertEqual(self.resolve("BL-E001-002", "fixed", "--ref", "abc1234")[0], 0)
        self.assert_invariants()

    def test_duplicate_ref_rules_forbid_chains(self):
        self.append("A")
        self.append("B", "001", "02")
        self.append("C", "001", "03")
        self.assertEqual(self.resolve("BL-E001-002", "duplicate", "--ref", "BL-E001-002")[0], 2)
        self.assertEqual(self.resolve("BL-E001-002", "duplicate", "--ref", "BL-E001-099")[0], 2)
        self.assertEqual(self.resolve("BL-E001-002", "duplicate", "--ref", "BL-E001-001")[0], 0)
        # B is now a resolved duplicate: C may not point at it
        self.assertEqual(self.resolve("BL-E001-003", "duplicate", "--ref", "BL-E001-002")[0], 2)
        self.assert_invariants()

    def test_rerun_is_idempotent(self):
        self.append("A")
        self.resolve("BL-E001-001", "obsolete", "--note", "gone")
        code, out, _ = self.resolve("BL-E001-001", "obsolete", "--note", "gone")
        self.assertEqual(code, 0)
        self.assertIn("already resolved", out)
        self.assertEqual(self.resolved_keys(), ["BL-E001-001"])
        self.assert_invariants()

    def test_unknown_key_exits_3(self):
        self.assertEqual(self.resolve("BL-E001-042", "obsolete", "--note", "x")[0], 3)

    def test_crash_between_writes_is_cleared_by_rerun(self):
        self.append("A")
        with _dump_failing_on(2):
            with self.assertRaises(OSError):
                pm.main(["resolve-issue", "--state-root", self.root, "--key", "BL-E001-001",
                         "--resolution", "obsolete", "--note", "gone"])
        self.assertEqual(self.open_keys(), ["BL-E001-001"])      # premise: both files
        self.assertEqual(self.resolved_keys(), ["BL-E001-001"])
        code, out, _ = self.resolve("BL-E001-001", "obsolete", "--note", "gone")
        self.assertEqual(code, 0)
        self.assertIn("removed the stale open copy", out)
        self.assertEqual(self.open_keys(), [])
        self.assertEqual(self.resolved_keys(), ["BL-E001-001"])
        self.assert_invariants()

    def test_key_duplicated_in_open_file_is_refused(self):
        self.append("A")
        y, data = pm._load(self.issues)
        from ruamel.yaml.comments import CommentedMap
        data["backlog"].append(CommentedMap(data["backlog"][0]))
        pm._atomic_dump(y, data, self.issues)
        code, _, err = self.resolve("BL-E001-001", "obsolete", "--note", "x")
        self.assertEqual(code, 2)
        self.assertIn("1i", err)

    def test_malformed_resolved_list_is_refused(self):
        self.append("A")
        with open(self.resolved, "w", encoding="utf-8") as fh:
            fh.write("resolved: oops\n")
        self.assertEqual(self.resolve("BL-E001-001", "obsolete", "--note", "x")[0], 2)
        self.assertEqual(self.open_keys(), ["BL-E001-001"])

    def test_event_carries_resolution_and_cause(self):
        self.append("A")
        self.resolve("BL-E001-001", "fixed", "--ref", "abc1234", "--session-id", "S-9",
                     "--cause", "triage")
        ev = self.events("issue_resolved")[-1]
        self.assertEqual((ev["resolution"], ev["ref"], ev["session"], ev["cause"]),
                         ("fixed", "abc1234", "S-9", "triage"))
        self.assert_invariants()


class TestConcurrentResolveAppend(unittest.TestCase):
    """Real subprocesses: _file_lock's re-entrancy counter is per process, so
    threads would pass vacuously with the lock removed."""
    N = 6

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.root = os.path.join(self.d, "state")
        _build_issue_tree(self.root)
        with redirect_stdout(io.StringIO()):
            for i in range(1, self.N + 1):
                self.assertEqual(pm.main(["append-issue", "--state-root", self.root, "--epic",
                                          "001", "--title", f"seed {i}", "--source", "qa",
                                          "--severity", "Low"]), 0)

    def test_parallel_resolves_and_appends_lose_nothing(self):
        import subprocess
        procs = [subprocess.Popen([sys.executable, SCRIPT, "resolve-issue", "--state-root",
                                   self.root, "--key", f"BL-E001-{i:03d}", "--resolution",
                                   "obsolete", "--note", "x"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for i in range(1, self.N + 1)]
        procs += [subprocess.Popen([sys.executable, SCRIPT, "append-issue", "--state-root",
                                    self.root, "--epic", "001", "--title", f"new {i}",
                                    "--source", "qa", "--severity", "Low"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                  for i in range(1, self.N + 1)]
        for p in procs:
            _, err = p.communicate(timeout=120)
            self.assertEqual(p.returncode, 0, err.decode())
        _, o = pm._load(os.path.join(self.root, "issues.yaml"))
        _, r = pm._load(os.path.join(self.root, "issues-resolved.yaml"))
        open_keys = [str(i["key"]) for i in o["backlog"]]
        res_keys = [str(i["key"]) for i in r["resolved"]]
        self.assertEqual(sorted(res_keys), [f"BL-E001-{i:03d}" for i in range(1, self.N + 1)])
        self.assertEqual(len(open_keys), self.N)
        self.assertEqual(len(set(open_keys)), self.N, "a key was allocated twice")
        self.assertFalse(set(open_keys) & set(res_keys), "a key is in both files")


class TestAppendDedupeResolved(IssueBase):
    def resolve(self, key, *argv):
        code, _, err = self.run_all(["resolve-issue", "--state-root", self.root,
                                     "--key", key, *argv])
        self.assertEqual(code, 0, err)

    # Spec §2.1: the severity rule covers all three non-fixed resolutions, not wontfix alone.
    # duplicate needs --ref naming another key (the open "Survivor", appended first as
    # BL-E001-001); wontfix and obsolete need --note.
    NON_FIXED = {"wontfix": ("--note", "risk accepted"),
                 "duplicate": ("--ref", "BL-E001-001"),
                 "obsolete": ("--note", "gone")}

    def _append_key(self, title, severity):
        code, out, err = self.append(title, "001", "01", severity)
        self.assertEqual(code, 0, err)
        self.assertTrue(out.startswith("OK append-issue BL-E001-"), out)
        return out.split()[2]

    def test_non_fixed_resolution_same_or_lower_severity_is_skipped(self):
        self.assertEqual(self._append_key("Survivor", "Low"), "BL-E001-001")
        for res, flags in self.NON_FIXED.items():
            with self.subTest(resolution=res):
                key = self._append_key(f"A {res}", "Medium")
                self.resolve(key, "--resolution", res, *flags)
                for sev in ("Medium", "Low"):
                    code, out, _ = self.append(f"A {res}", "001", "01", sev)
                    self.assertEqual(code, 0)
                    self.assertIn(f"skipped -- matches {key} resolved as {res} (severity Medium)",
                                  out)
        self.assertEqual(self.open_keys(), ["BL-E001-001"])

    def test_higher_severity_than_a_non_fixed_resolution_is_appended_as_reraised(self):
        self.assertEqual(self._append_key("Survivor", "Low"), "BL-E001-001")
        for res, flags in self.NON_FIXED.items():
            with self.subTest(resolution=res):
                key = self._append_key(f"A {res}", "Low")
                self.resolve(key, "--resolution", res, *flags)
                code, out, _ = self.append(f"A {res}", "001", "01", "High")
                self.assertEqual(code, 0)
                self.assertIn(f"(re-raised above {key} {res} at Low)", out)
                self.assertIn(out.split()[2], self.open_keys())

    def test_fixed_match_is_a_recurrence(self):
        self.append("A")
        self.resolve("BL-E001-001", "--resolution", "fixed", "--ref", "E001-S01-001")
        code, out, _ = self.append("A")
        self.assertIn("recurrence of BL-E001-001", out)
        self.assertEqual(self.open_keys(), ["BL-E001-002"])

    def test_newest_resolved_match_decides(self):
        self.append("A")
        self.resolve("BL-E001-001", "--resolution", "fixed", "--ref", "E001-S01-001")
        self.append("A")                                     # recurrence -> 002
        self.resolve("BL-E001-002", "--resolution", "wontfix", "--note", "stop")
        code, out, _ = self.append("A")
        self.assertIn("skipped", out)
        self.assertIn("BL-E001-002", out)

    def test_allow_duplicate_bypasses_resolved_match(self):
        self.append("A")
        self.resolve("BL-E001-001", "--resolution", "obsolete", "--note", "gone")
        self.append("A", "001", "01", "Low", "code-review (E001-S01-001)", "--allow-duplicate")
        self.assertEqual(self.open_keys(), ["BL-E001-002"])


class TestListIssues(unittest.TestCase):
    """list-issues reads state-root/issues.yaml; a missing file or a filter set
    matching nothing is success (exit 0), never an error."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.state_root = os.path.join(self.d, "state")
        os.makedirs(self.state_root, exist_ok=True)
        self.issues_file = os.path.join(self.state_root, "issues.yaml")

    def write_fixture(self):
        with open(self.issues_file, "w", encoding="utf-8") as fh:
            fh.write(ISSUES_FIXTURE)

    def run_main(self, argv):
        buf = io.StringIO()
        code = 0
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        return code, buf.getvalue()

    def run_json(self, extra_args):
        import json
        code, out = self.run_main(["list-issues", "--state-root", self.state_root,
                                    "--format", "json"] + extra_args)
        self.assertEqual(code, 0, out)
        return json.loads(out)

    def test_no_filter_returns_everything(self):
        self.write_fixture()
        items = self.run_json([])
        self.assertEqual(len(items), 4)

    def test_epic_filter_matches_key_form(self):
        self.write_fixture()
        items = self.run_json(["--epic", "E001"])
        self.assertEqual({i["key"] for i in items}, {"BL-E001-001", "BL-E001-002"})

    def test_epic_filter_matches_zero_padded_number_form(self):
        self.write_fixture()
        items = self.run_json(["--epic", "001"])
        self.assertEqual({i["key"] for i in items}, {"BL-E001-001", "BL-E001-002"})

    def test_sprint_filter_excludes_epic_level_items(self):
        self.write_fixture()
        items = self.run_json(["--sprint", "S01"])
        self.assertEqual({i["key"] for i in items}, {"BL-E001-001", "BL-E002-001"})
        keys = {i["key"] for i in items}
        self.assertNotIn("BL-E001-002", keys)
        self.assertNotIn("BL-E000-001", keys)

    def test_sprint_filter_matches_unpadded_number_form(self):
        self.write_fixture()
        items = self.run_json(["--sprint", "1"])
        self.assertEqual({i["key"] for i in items}, {"BL-E001-001", "BL-E002-001"})

    def test_severity_filter(self):
        self.write_fixture()
        items = self.run_json(["--severity", "High"])
        self.assertEqual({i["key"] for i in items}, {"BL-E001-002"})

    def test_severity_filter_repeated_ors_values(self):
        self.write_fixture()
        items = self.run_json(["--severity", "Low", "--severity", "High"])
        self.assertEqual({i["key"] for i in items}, {"BL-E001-001", "BL-E001-002"})

    def test_combined_filters_and(self):
        self.write_fixture()
        items = self.run_json(["--epic", "001", "--severity", "Low"])
        self.assertEqual({i["key"] for i in items}, {"BL-E001-001"})

    def test_epic_and_sprint_combined_and(self):
        self.write_fixture()
        items = self.run_json(["--epic", "001", "--sprint", "01"])
        self.assertEqual({i["key"] for i in items}, {"BL-E001-001"})

    def test_missing_file_exits_0_with_empty_json(self):
        # no write_fixture() — issues.yaml does not exist
        items = self.run_json([])
        self.assertEqual(items, [])

    def test_missing_file_exits_0_with_empty_text(self):
        code, out = self.run_main(["list-issues", "--state-root", self.state_root])
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", out)

    def test_text_format_is_readable_table(self):
        self.write_fixture()
        code, out = self.run_main(["list-issues", "--state-root", self.state_root])
        self.assertEqual(code, 0)
        self.assertIn("BL-E001-001", out)
        self.assertIn("KEY", out)

    def test_format_json_emits_valid_parseable_json(self):
        self.write_fixture()
        items = self.run_json(["--epic", "E002"])
        self.assertIsInstance(items, list)
        self.assertEqual(items[0]["key"], "BL-E002-001")
        self.assertEqual(items[0]["severity"], "Medium")


class TestLayoutResolution(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.root = os.path.join(self.d, "state")
        # active/epic-001/sprint-01/{sprint.yaml,E001-S01-003.yaml} + epic.yaml
        sd = os.path.join(self.root, "active", "epic-001", "sprint-01")
        os.makedirs(sd)
        with open(os.path.join(self.root, "active", "epic-001", "epic.yaml"), "w") as f:
            f.write("key: 'E001'\nstatus: in-progress\n")
        with open(os.path.join(sd, "sprint.yaml"), "w") as f:
            f.write("key: 'S01'\nepic: 'E001'\nstatus: in-progress\n")
        with open(os.path.join(sd, "E001-S01-003.yaml"), "w") as f:
            f.write("key: 'E001-S01-003'\nepic: 'E001'\nsprint: 'S01'\nstatus: review\n")
        # a planned epic, to prove the folder search spans all three
        os.makedirs(os.path.join(self.root, "planned", "epic-005"))
        with open(os.path.join(self.root, "planned", "epic-005", "epic.yaml"), "w") as f:
            f.write("key: 'E005'\nstatus: backlog\n")

    def test_dirname_conversions(self):
        self.assertEqual(pm.epic_dirname("E001"), "epic-001")
        self.assertEqual(pm.epic_dirname("E42"), "epic-042")
        self.assertEqual(pm.sprint_dirname("S01"), "sprint-01")
        self.assertEqual(pm.sprint_dirname("S7"), "sprint-07")

    def test_parse_story_key(self):
        self.assertEqual(pm.parse_story_key("E001-S01-003"), ("E001", "S01", "003"))

    def test_parse_story_key_rejects_malformed(self):
        with self.assertRaises(ValueError):
            pm.parse_story_key("not-a-key")

    def test_find_epic_dir_searches_all_status_folders(self):
        self.assertTrue(pm.find_epic_dir(self.root, "E001").endswith("active/epic-001"))
        self.assertTrue(pm.find_epic_dir(self.root, "E005").endswith("planned/epic-005"))
        self.assertIsNone(pm.find_epic_dir(self.root, "E999"))

    def test_node_file_resolution(self):
        self.assertTrue(pm.epic_file(self.root, "E001").endswith("active/epic-001/epic.yaml"))
        self.assertTrue(pm.sprint_file(self.root, "E001", "S01").endswith("sprint-01/sprint.yaml"))
        self.assertTrue(pm.story_file(self.root, "E001-S01-003").endswith("sprint-01/E001-S01-003.yaml"))
        self.assertIsNone(pm.story_file(self.root, "E001-S01-999"))

    def test_load_node_returns_bare_mapping(self):
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(node["key"], "E001-S01-003")
        self.assertNotIn("epics", node)

    def test_save_node_roundtrips(self):
        p = pm.story_file(self.root, "E001-S01-003")
        y, node = pm.load_node(p)
        node["status"] = "done"
        pm.save_node(y, node, p)
        _, again = pm.load_node(p)
        self.assertEqual(again["status"], "done")

    def test_check_backrefs_detects_misplacement(self):
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(pm.check_backrefs(node, "E001", "S01"), [])
        self.assertTrue(pm.check_backrefs(node, "E002", "S01"))

    def test_check_backrefs_flags_absent_epic_backref(self):
        """A file with no `epic:` at all must FAIL, not pass. migrate-state adds these
        back-references as a brand-new step, so "absent" is precisely the case this
        check exists to catch — treating absent as OK made the migration's only
        automated gate blind to its own newest transformation."""
        p = pm.story_file(self.root, "E001-S01-003")
        with open(p, "w") as f:
            f.write("key: 'E001-S01-003'\nsprint: 'S01'\nstatus: review\n")
        _, node = pm.load_node(p)
        problems = pm.check_backrefs(node, "E001", "S01")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("epic back-reference absent", problems[0])

    def test_check_backrefs_flags_absent_sprint_backref(self):
        p = pm.story_file(self.root, "E001-S01-003")
        with open(p, "w") as f:
            f.write("key: 'E001-S01-003'\nepic: 'E001'\nstatus: review\n")
        _, node = pm.load_node(p)
        problems = pm.check_backrefs(node, "E001", "S01")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("sprint back-reference absent", problems[0])

    def test_check_backrefs_flags_both_absent(self):
        p = pm.story_file(self.root, "E001-S01-003")
        with open(p, "w") as f:
            f.write("key: 'E001-S01-003'\nstatus: review\n")
        _, node = pm.load_node(p)
        self.assertEqual(len(pm.check_backrefs(node, "E001", "S01")), 2)

    def test_check_backrefs_absent_sprint_on_sprint_node_is_not_checked(self):
        """Sprint nodes are checked with sprint_key=None (they have no `sprint:` of
        their own to verify), so only the `epic:` back-reference is required there."""
        _, node = pm.load_node(pm.sprint_file(self.root, "E001", "S01"))
        self.assertEqual(pm.check_backrefs(node, "E001"), [])


class TestElapsedHoursUnification(TestLayoutResolution):
    """estimate-side time_hours and actual-side elapsed_hours are one name now —
    ESTIMATE_TO_ACTUAL is gone, and the deprecated --time-hours* CLI flags still
    write the elapsed_hours* destinations."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_estimate_writes_elapsed_hours_not_time_hours(self):
        code, out = self.run_main(["estimate-story", "--state-root", self.root,
                                   "--story", "E001-S01-003", "--classification", "standard"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertIn("elapsed_hours", node["estimate"])
        self.assertNotIn("time_hours", node["estimate"])

    def test_deprecated_time_hours_flag_still_writes_elapsed_hours(self):
        # set-estimate has no --node flag (unlike set-actual) — kind is inferred
        # from --story vs --epic[/--sprint]
        code, out = self.run_main(["set-estimate", "--state-root", self.root,
                                   "--story", "E001-S01-003",
                                   "--time-hours", "3"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(float(node["estimate"]["elapsed_hours"]), 3.0)
        self.assertNotIn("time_hours", node["estimate"])

    def test_estimate_to_actual_map_is_gone(self):
        self.assertFalse(hasattr(pm, "ESTIMATE_TO_ACTUAL"))

    def test_wall_clock_metric_is_elapsed_hours(self):
        self.assertEqual(pm.WALL_CLOCK_METRICS, ("elapsed_hours",))


class TestHitlHours(TestLayoutResolution):
    """hitl_hours is the fifth metric: real, observed supervision time — distinct
    from man_hours, which stays a counterfactual developer-effort estimate."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_metric_fields_has_five_in_canonical_order(self):
        self.assertEqual(pm.METRIC_FIELDS,
                         ("elapsed_hours", "man_hours", "hitl_hours", "tokens_k", "cost"))

    def test_bands_carry_hitl_for_every_classification(self):
        for cls in pm.CLASSIFICATIONS:
            self.assertIn("hitl_hours", pm.BASE_BANDS[cls])

    def test_estimate_story_emits_hitl_hours(self):
        code, out = self.run_main(["estimate-story", "--state-root", self.root,
                                   "--story", "E001-S01-003", "--classification", "complex"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        # complex band 0.3-1.0, midpoint 0.65, x cold-start scope 1.0 x fix 1.25
        self.assertAlmostEqual(float(node["estimate"]["hitl_hours"]), 0.81, places=2)

    def test_set_actual_accepts_hitl_hours(self):
        code, out = self.run_main(["set-actual", "--state-root", self.root, "--node", "story",
                                   "--story", "E001-S01-003", "--hitl-hours", "0.3",
                                   "--no-calibrate"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertAlmostEqual(float(node["actual"]["hitl_hours"]), 0.3, places=2)

    def test_set_actual_hitl_hours_produces_scope_sample(self):
        """A metric recorded on the node but never sampled can never calibrate.
        This drives the real CLI path (set-estimate then set-actual, calibration
        left ON) and reads pm-calibration.yaml back, so a regression that once
        again drops hitl_hours from derive_story_sample's metric loop fails
        here — asserting on the node alone would not have caught it."""
        code, out = self.run_main(["set-estimate", "--state-root", self.root,
                                   "--story", "E001-S01-003", "--hitl-hours", "0.5",
                                   "--fix-factor", "1.0"])
        self.assertEqual(code, 0, out)

        code, out = self.run_main(["set-actual", "--state-root", self.root, "--node", "story",
                                   "--story", "E001-S01-003", "--hitl-hours", "0.6",
                                   "--runtime", "other"])
        self.assertEqual(code, 0, out)

        _, cal = pm.load_calibration(self.root)
        # no classification was set on the fixture story -> derive_story_sample's
        # default bucket, "standard"
        samples = pm._component_samples(cal, "scope", "standard", "hitl_hours")
        self.assertEqual(len(samples), 1, cal)
        # fix_factor=1.0, no completion_evidence -> provenance "backout":
        # sample = actual x applied_ratio(1.0, none recorded) / estimate
        self.assertAlmostEqual(samples[0], 0.6 * 1.0 / 0.5, places=4)

    def test_calibration_show_lists_hitl_hours_rows(self):
        """cmd_calibration's display loops must enumerate hitl_hours too, or a
        component that IS calibrating (see the test above) would still never
        show up in `calibration show` — same-shaped blind spot, different
        symptom."""
        code, out = self.run_main(["calibration", "show", "--state-root", self.root,
                                   "--format", "json"])
        self.assertEqual(code, 0, out)
        data = json.loads(out)
        buckets = [c["bucket"] for c in data["components"] if c["component"] == "scope"]
        self.assertTrue(any(b.endswith("/hitl_hours") for b in buckets), buckets)
        buckets = [c["bucket"] for c in data["components"] if c["component"] == "closure"]
        self.assertTrue(any(b.endswith("/hitl_hours") for b in buckets), buckets)

    def test_calibration_show_omits_closure_cost_row(self):
        """Task 10: closure cost is derived at rollup time (tokens x rates),
        never sampled or displayed on its own — a lingering closure/cost row
        would advertise a component that can no longer activate."""
        code, out = self.run_main(["calibration", "show", "--state-root", self.root,
                                   "--format", "json"])
        self.assertEqual(code, 0, out)
        data = json.loads(out)
        buckets = [c["bucket"] for c in data["components"] if c["component"] == "closure"]
        self.assertFalse(any(b.endswith("/cost") for b in buckets), buckets)


class TestAtomicAndCLI(TestLayoutResolution):
    """Reuses TestLayoutResolution's tree fixture."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_no_temp_files_left(self):
        self.run_main(["set-status", "--state-root", self.root,
                       "--story", "E001-S01-003", "--status", "done"])
        sd = os.path.dirname(pm.story_file(self.root, "E001-S01-003"))
        leftovers = [n for n in os.listdir(sd) if n.startswith(".pm-status.")]
        self.assertEqual(leftovers, [])


class TestKeyBasedAddressing(TestLayoutResolution):
    """Reuses TestLayoutResolution's tree fixture."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_set_status_by_story_key(self):
        code, out = self.run_main(
            ["set-status", "--state-root", self.root, "--story", "E001-S01-003", "--status", "done"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(node["status"], "done")

    def test_set_status_by_epic_key(self):
        code, out = self.run_main(
            ["set-status", "--state-root", self.root, "--epic", "E001", "--status", "done"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.epic_file(self.root, "E001"))
        self.assertEqual(node["status"], "done")

    def test_set_status_by_sprint_key(self):
        code, out = self.run_main(
            ["set-status", "--state-root", self.root, "--epic", "E001",
             "--sprint", "S01", "--status", "done"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.sprint_file(self.root, "E001", "S01"))
        self.assertEqual(node["status"], "done")

    def test_missing_node_exits_3(self):
        code, _ = self.run_main(
            ["set-status", "--state-root", self.root, "--story", "E001-S01-999", "--status", "done"])
        self.assertEqual(code, 3)

    def test_set_actual_writes_all_four_metrics(self):
        code, out = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "story", "--story", "E001-S01-003",
             "--elapsed-hours", "1.8", "--man-hours", "7", "--tokens-input", "300",
             "--tokens-output", "55", "--model", "claude-sonnet-5"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(int(node["actual"]["tokens_k"]["total"]), 355)
        self.assertEqual(node["actual"]["man_hours"], 7)

    def test_claude_runtime_still_rejects_na(self):
        code, _ = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "story", "--story", "E001-S01-003",
             "--tokens-na", "--runtime", "claude"])
        self.assertEqual(code, 2)

    def test_set_estimate_story_uses_single_values(self):
        # --cost is not passed here: cost is derived from tokens x rates and
        # set-estimate rejects it outright (see TestEstimateTokensAndCost).
        code, out = self.run_main(
            ["set-estimate", "--state-root", self.root, "--story", "E001-S01-003",
             "--man-hours", "6", "--time-hours", "1.5", "--tokens-k", "320"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(node["estimate"]["man_hours"], 6.0)
        self.assertNotIn("man_hours_low", node["estimate"])
        self.assertNotIn("cost", node["estimate"])

    def test_set_field_dot_path(self):
        code, out = self.run_main(
            ["set-field", "--state-root", self.root, "--story", "E001-S01-003",
             "--field", "review.summary", "--value", "looks good"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(node["review"]["summary"], "looks good")

    def test_backref_mismatch_exits_4(self):
        p = pm.story_file(self.root, "E001-S01-003")
        with open(p, "w") as f:
            f.write("key: 'E001-S01-003'\nepic: 'E999'\nsprint: 'S01'\nstatus: review\n")
        code, _ = self.run_main(
            ["set-status", "--state-root", self.root, "--story", "E001-S01-003", "--status", "done"])
        self.assertEqual(code, 4)


class TestStructuredActualTokens(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _set(self, *extra):
        return self.run_main(["set-actual", "--state-root", self.root, "--node", "story",
                              "--story", "E001-S01-003", "--no-calibrate"] + list(extra))

    def test_writes_classes_total_and_derived_cost(self):
        code, out = self._set("--tokens-input", "412", "--tokens-output", "34",
                              "--tokens-cache-write", "4300", "--tokens-cache-read", "253",
                              "--model", "claude-opus-5", "--runtime", "claude")
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        tk = node["actual"]["tokens_k"]
        self.assertEqual(int(tk["total"]), 4999)
        self.assertEqual(int(tk["cache_write"]), 4300)
        self.assertAlmostEqual(float(node["actual"]["cost"]), 29.91, places=2)
        self.assertEqual(str(node["actual"]["model"]), "claude-opus-5")

    def test_cost_flag_is_rejected(self):
        code, out = self._set("--cost", "12.00")
        self.assertEqual(code, 2, out)

    def test_tokens_require_a_model(self):
        code, out = self._set("--tokens-input", "100")
        self.assertEqual(code, 2, out)

    def test_unknown_model_is_rejected(self):
        code, out = self._set("--tokens-input", "100", "--model", "nope")
        self.assertEqual(code, 2, out)

    def test_tokens_na_allowed_under_runtime_other(self):
        code, out = self._set("--tokens-na", "--runtime", "other")
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertTrue(pm._is_na(node["actual"]["tokens_k"]))
        self.assertTrue(pm._is_na(node["actual"]["cost"]))

    def test_tokens_na_forbidden_under_runtime_claude(self):
        code, out = self._set("--tokens-na", "--runtime", "claude")
        self.assertEqual(code, 2, out)


class TestVerify(TestLayoutResolution):
    """Reuses TestLayoutResolution's tree fixture. Covers cmd_verify against the
    --state-root interface for story/sprint scope. --scope epic is a distinct
    branch (back-reference integrity across the whole subtree, not per-node
    completion) — see TestVerifyEpicScope below."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _complete(self, path, story=False):
        from ruamel.yaml.comments import CommentedMap
        y, node = pm.load_node(path)
        node["status"] = "done"
        actual = CommentedMap()
        actual["elapsed_hours"] = 0.4
        actual["man_hours"] = 3
        actual["hitl_hours"] = 0.1
        actual["tokens_k"] = {"total": 120, "input": 80, "output": 30,
                               "cache_write": 6, "cache_read": 4}
        actual["cost"] = 0.71
        actual["model"] = "claude-sonnet-5"
        node["actual"] = actual
        if story:
            ce = CommentedMap()
            ce["fix_iterations"] = 0
            ce["tests_passing"] = 10
            node["completion_evidence"] = ce
        pm.save_node(y, node, path)

    def test_scope_story_passes_when_complete(self):
        self._complete(pm.story_file(self.root, "E001-S01-003"), story=True)
        code, out = self.run_main(
            ["verify", "--state-root", self.root, "--scope", "story", "--story", "E001-S01-003"])
        self.assertEqual(code, 0, out)
        self.assertIn("PASS", out)

    def test_scope_story_fails_exit_4_when_incomplete(self):
        # fixture default: status=review, no actual block, no completion_evidence
        code, out = self.run_main(
            ["verify", "--state-root", self.root, "--scope", "story", "--story", "E001-S01-003"])
        self.assertEqual(code, 4)
        self.assertIn("status=", out)

    def test_scope_sprint_passes_when_complete(self):
        self._complete(pm.sprint_file(self.root, "E001", "S01"))
        code, out = self.run_main(
            ["verify", "--state-root", self.root, "--scope", "sprint", "--epic", "E001", "--sprint", "S01"])
        self.assertEqual(code, 0, out)
        self.assertIn("PASS", out)

    def test_nonexistent_node_exits_3(self):
        code, _ = self.run_main(
            ["verify", "--state-root", self.root, "--scope", "story", "--story", "E001-S01-999"])
        self.assertEqual(code, 3)


class TestVerifyDerivedCost(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _done_story(self, cost, total=4999):
        p = pm.story_file(self.root, "E001-S01-003")
        y, node = pm.load_node(p)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        node["actual"] = {"elapsed_hours": 3.1, "man_hours": 14, "hitl_hours": 0.3,
                          "tokens_k": {"total": total, "input": 412, "output": 34,
                                       "cache_write": 4300, "cache_read": 253},
                          "cost": cost, "model": "claude-opus-5"}
        pm.save_node(y, node, p)

    def test_passes_when_cost_matches_the_tokens(self):
        self._done_story(29.91)
        code, out = self.run_main(["verify", "--state-root", self.root, "--scope", "story",
                                   "--story", "E001-S01-003", "--runtime", "claude"])
        self.assertEqual(code, 0, out)

    def test_fails_a_hand_edited_cost(self):
        self._done_story(9.99)
        code, out = self.run_main(["verify", "--state-root", self.root, "--scope", "story",
                                   "--story", "E001-S01-003", "--runtime", "claude"])
        self.assertEqual(code, 4, out)
        # Pinned to the mismatch semantics, not just the word "cost" — a fixture
        # that produced any other failure mentioning "cost" would wrongly pass.
        self.assertIn("actual.cost=9.99 != derived 29.91", out)

    def test_fails_when_cost_is_off_by_exactly_one_cent(self):
        # The boundary that matters: both the stored and derived cost are
        # already rounded to cents, so the smallest genuine divergence is
        # exactly one cent. A tolerance of > 0.01 does not reliably fire on
        # that divergence — verified concretely: 30k input tokens at
        # claude-haiku-4-5 ($1.00/M) derives to exactly 0.03; a hand-edited
        # 0.02 is one cent off, and in float64 abs(0.02 - 0.03) equals
        # 0.009999999999999998, which is NOT > 0.01 (the old tolerance would
        # have let this pass) but IS > 0.005 (the new tolerance catches it).
        # This is not float noise working in our favor by luck in one
        # direction — it is the precise case the old tolerance was blind to.
        p = pm.story_file(self.root, "E001-S01-003")
        y, node = pm.load_node(p)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        node["actual"] = {"elapsed_hours": 1.0, "man_hours": 2, "hitl_hours": 0.1,
                          "tokens_k": {"total": 30, "input": 30, "output": 0,
                                       "cache_write": 0, "cache_read": 0},
                          "cost": 0.02, "model": "claude-haiku-4-5"}
        pm.save_node(y, node, p)
        code, out = self.run_main(["verify", "--state-root", self.root, "--scope", "story",
                                   "--story", "E001-S01-003", "--runtime", "claude"])
        self.assertEqual(code, 4, out)
        self.assertIn("actual.cost=0.02 != derived 0.03", out)

    def test_fails_when_total_is_not_the_sum(self):
        self._done_story(29.91, total=999)
        code, out = self.run_main(["verify", "--state-root", self.root, "--scope", "story",
                                   "--story", "E001-S01-003", "--runtime", "claude"])
        self.assertEqual(code, 4, out)
        self.assertIn("total", out)

    def test_fails_when_hitl_hours_absent(self):
        p = pm.story_file(self.root, "E001-S01-003")
        y, node = pm.load_node(p)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        node["actual"] = {"elapsed_hours": 3.1, "man_hours": 14,
                          "tokens_k": "N/A", "cost": "N/A"}
        pm.save_node(y, node, p)
        code, out = self.run_main(["verify", "--state-root", self.root, "--scope", "story",
                                   "--story", "E001-S01-003"])
        self.assertEqual(code, 4, out)
        self.assertIn("hitl_hours", out)


class TestVerifyTokenRatesWiring(TestLayoutResolution):
    """--token-rates on `verify` (Decision 1 of the task-8 brief, not in the
    original design doc): without this wiring, a project using
    modules.l3io-pm.token_rates overrides would have every node recomputed at
    DEFAULT rates and fail verification universally. This is the permanent
    covering test for that wiring — a prior version of this proof lived only
    in a throwaway script and left the wiring one refactor away from silently
    regressing with the full suite still green."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _done_story_priced_only_under_override(self):
        p = pm.story_file(self.root, "E001-S01-003")
        y, node = pm.load_node(p)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        # "acme-model" does not exist in TOKEN_RATES; it is priced only by the
        # --token-rates override below (input $10/M, everything else free).
        # 100k input tokens -> 100 * 10.0 / 1000 = 1.00.
        node["actual"] = {"elapsed_hours": 1.0, "man_hours": 2, "hitl_hours": 0.1,
                          "tokens_k": {"total": 100, "input": 100, "output": 0,
                                       "cache_write": 0, "cache_read": 0},
                          "cost": 1.00, "model": "acme-model"}
        pm.save_node(y, node, p)

    def test_fails_with_unknown_model_message_without_override(self):
        self._done_story_priced_only_under_override()
        code, out = self.run_main(["verify", "--state-root", self.root, "--scope", "story",
                                   "--story", "E001-S01-003"])
        self.assertEqual(code, 4, out)
        self.assertIn("unknown model 'acme-model'", out)

    def test_passes_when_token_rates_override_supplies_the_model(self):
        self._done_story_priced_only_under_override()
        overrides = json.dumps({"acme-model": {"input": 10.0, "output": 0,
                                                "cache_write": 0, "cache_read": 0}})
        code, out = self.run_main(["verify", "--state-root", self.root, "--scope", "story",
                                   "--story", "E001-S01-003", "--token-rates", overrides])
        self.assertEqual(code, 0, out)


class TestVerifyEpicScope(TestLayoutResolution):
    """verify --scope epic — deferred from Task 2 (ruling R3), implemented in Task 4
    since it depends on list_sprint_dirs/list_story_files. Unlike story/sprint scope,
    this branch checks only back-reference integrity across the whole epic subtree,
    not per-node completion."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_scope_epic_passes_on_good_fixture(self):
        code, out = self.run_main(
            ["verify", "--state-root", self.root, "--scope", "epic", "--epic", "E001"])
        self.assertEqual(code, 0, out)
        self.assertIn("PASS", out)

    def test_scope_epic_fails_exit_4_on_corrupted_backref(self):
        p = pm.story_file(self.root, "E001-S01-003")
        with open(p, "w") as f:
            f.write("key: 'E001-S01-003'\nepic: 'E999'\nsprint: 'S01'\nstatus: review\n")
        err = io.StringIO()
        try:
            with redirect_stderr(err):
                code = pm.main(
                    ["verify", "--state-root", self.root, "--scope", "epic", "--epic", "E001"])
        except SystemExit as e:
            code = e.code
        self.assertEqual(code, 4)
        self.assertIn("epic back-reference 'E999' != path epic 'E001'", err.getvalue())

    def test_scope_epic_nonexistent_exits_3(self):
        code, _ = self.run_main(
            ["verify", "--state-root", self.root, "--scope", "epic", "--epic", "E999"])
        self.assertEqual(code, 3)

    def test_scope_epic_fails_exit_4_when_story_backref_absent(self):
        """migrate-state Stage E2 relies on this scope to prove Stage B actually wrote
        the `epic:`/`sprint:` back-references it introduces. A story file missing them
        entirely must fail the gate."""
        p = pm.story_file(self.root, "E001-S01-003")
        with open(p, "w") as f:
            f.write("key: 'E001-S01-003'\nstatus: review\n")
        err = io.StringIO()
        try:
            with redirect_stderr(err):
                code = pm.main(
                    ["verify", "--state-root", self.root, "--scope", "epic", "--epic", "E001"])
        except SystemExit as e:
            code = e.code
        self.assertEqual(code, 4)
        self.assertIn("back-reference absent", err.getvalue())

    def test_scope_epic_fails_exit_4_when_sprint_backref_absent(self):
        sp = pm.sprint_file(self.root, "E001", "S01")
        with open(sp, "w") as f:
            f.write("key: 'S01'\nstatus: in-progress\n")
        err = io.StringIO()
        try:
            with redirect_stderr(err):
                code = pm.main(
                    ["verify", "--state-root", self.root, "--scope", "epic", "--epic", "E001"])
        except SystemExit as e:
            code = e.code
        self.assertEqual(code, 4)
        self.assertIn("epic back-reference absent", err.getvalue())

    def test_scope_epic_reports_missing_sprint_and_corrupted_story_together(self):
        """Addition B: a sprint with no sprint.yaml must still be descended into, so a
        corrupted story co-located with the missing sprint.yaml is also reported —
        not silently skipped by the `continue` that used to follow the missing-file
        failure."""
        sd2 = os.path.join(self.root, "active", "epic-001", "sprint-02")
        os.makedirs(sd2)
        with open(os.path.join(sd2, "E001-S02-001.yaml"), "w") as f:
            f.write("key: 'E001-S02-001'\nepic: 'E999'\nsprint: 'S02'\nstatus: review\n")

        err = io.StringIO()
        try:
            with redirect_stderr(err):
                code = pm.main(
                    ["verify", "--state-root", self.root, "--scope", "epic", "--epic", "E001"])
        except SystemExit as e:
            code = e.code
        self.assertEqual(code, 4)
        failures = err.getvalue()
        self.assertEqual(failures.count("FAIL "), 2, failures)
        self.assertIn("sprint.yaml missing", failures)
        self.assertIn("E001-S02-001", failures)


class TestRollups(TestLayoutResolution):
    """Sprint/epic aggregates computed from child files, and the `show` CLI
    that renders them. Reuses TestLayoutResolution's E001/S01/E001-S01-003
    fixture, adding two more stories to sprint-01."""

    def setUp(self):
        super().setUp()
        sd = os.path.join(self.root, "active", "epic-001", "sprint-01")
        with open(os.path.join(sd, "E001-S01-001.yaml"), "w") as f:
            f.write("key: 'E001-S01-001'\nepic: 'E001'\nsprint: 'S01'\nstatus: done\n"
                    "actual:\n  elapsed_hours: 1.0\n  man_hours: 4\n  tokens_k: 100\n  cost: 1.50\n")
        with open(os.path.join(sd, "E001-S01-002.yaml"), "w") as f:
            f.write("key: 'E001-S01-002'\nepic: 'E001'\nsprint: 'S01'\nstatus: done\n"
                    "actual:\n  elapsed_hours: 2.0\n  man_hours: 6\n  tokens_k: 200\n  cost: 3.00\n")

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_list_story_files_sorted(self):
        files = pm.list_story_files(self.root, "E001", "S01")
        names = [os.path.basename(p) for p in files]
        self.assertEqual(names, ["E001-S01-001.yaml", "E001-S01-002.yaml", "E001-S01-003.yaml"])

    def test_list_story_files_excludes_sprint_yaml(self):
        self.assertNotIn("sprint.yaml",
                         [os.path.basename(p) for p in pm.list_story_files(self.root, "E001", "S01")])

    def test_rollup_sprint_counts_by_status(self):
        r = pm.rollup_sprint(self.root, "E001", "S01")
        self.assertEqual(r["story_count"], 3)
        self.assertEqual(r["by_status"]["done"], 2)
        self.assertEqual(r["by_status"]["review"], 1)

    def test_rollup_sprint_sums_actuals(self):
        r = pm.rollup_sprint(self.root, "E001", "S01")
        self.assertAlmostEqual(r["actual_totals"]["man_hours"], 10.0)
        self.assertAlmostEqual(r["actual_totals"]["tokens_k"], 300.0)
        self.assertAlmostEqual(r["actual_totals"]["cost"], 4.50)

    def test_rollup_epic_aggregates_sprints(self):
        r = pm.rollup_epic(self.root, "E001")
        self.assertEqual(r["sprint_count"], 1)
        self.assertEqual(r["story_count"], 3)

    def test_show_sprint_outputs_summary(self):
        code, out = self.run_main(
            ["show", "--state-root", self.root, "--epic", "E001", "--sprint", "S01"])
        self.assertEqual(code, 0, out)
        self.assertIn("E001-S01-003", out)
        self.assertIn("done", out)

    def test_show_epic_outputs_summary(self):
        code, out = self.run_main(
            ["show", "--state-root", self.root, "--epic", "E001"])
        self.assertEqual(code, 0, out)
        self.assertIn("S01", out)
        self.assertIn("stories=3", out)

    def test_show_nonexistent_epic_exits_3(self):
        code, _ = self.run_main(
            ["show", "--state-root", self.root, "--epic", "E999"])
        self.assertEqual(code, 3)

    def test_show_nonexistent_sprint_exits_3(self):
        code, _ = self.run_main(
            ["show", "--state-root", self.root, "--epic", "E001", "--sprint", "S99"])
        self.assertEqual(code, 3)


class TestLockOnEpicFile(TestLayoutResolution):
    """Lock commands using --state-root --epic instead of --file."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_set_lock_writes_lock_first(self):
        code, out = self.run_main(
            ["set-lock", "--state-root", self.root, "--epic", "E001", "--session-id", "sess-a"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.epic_file(self.root, "E001"))
        self.assertEqual(list(node.keys())[0], "_lock")
        self.assertEqual(node["_lock"]["session_id"], "sess-a")

    def test_check_lock_exit_5_for_other_session(self):
        self.run_main(["set-lock", "--state-root", self.root, "--epic", "E001",
                       "--session-id", "sess-a"])
        code, out = self.run_main(
            ["check-lock", "--state-root", self.root, "--epic", "E001", "--session-id", "sess-b"])
        self.assertEqual(code, 5)
        self.assertIn("LOCKED", out)

    def test_check_lock_free_for_own_session(self):
        self.run_main(["set-lock", "--state-root", self.root, "--epic", "E001",
                       "--session-id", "sess-a"])
        code, out = self.run_main(
            ["check-lock", "--state-root", self.root, "--epic", "E001", "--session-id", "sess-a"])
        self.assertEqual(code, 0)
        self.assertIn("FREE", out)

    def test_clear_lock_removes_block(self):
        self.run_main(["set-lock", "--state-root", self.root, "--epic", "E001",
                       "--session-id", "sess-a"])
        code, out = self.run_main(["clear-lock", "--state-root", self.root, "--epic", "E001"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.epic_file(self.root, "E001"))
        self.assertNotIn("_lock", node)


class TestLockOnMissingEpic(Base):
    """Test lock commands on nonexistent epics to verify contract asymmetry."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def setUp(self):
        super().setUp()
        self.state_root = os.path.join(self.d, "state")
        os.makedirs(self.state_root)

    def test_clear_lock_missing_epic_noop(self):
        """clear-lock on nonexistent epic returns 0 (no-op), not 3."""
        code, out = self.run_main(
            ["clear-lock", "--state-root", self.state_root, "--epic", "E999"])
        self.assertEqual(code, 0, out)
        self.assertIn("no-op", out)

    def test_check_lock_missing_epic_is_free(self):
        """check-lock on nonexistent epic returns 0 and outputs FREE, not 3."""
        code, out = self.run_main(
            ["check-lock", "--state-root", self.state_root, "--epic", "E999",
             "--session-id", "sess-a"])
        self.assertEqual(code, 0, out)
        self.assertIn("FREE", out)

    def test_set_lock_missing_epic_exits_3(self):
        """set-lock on nonexistent epic returns 3 (node not found)."""
        code, out = self.run_main(
            ["set-lock", "--state-root", self.state_root, "--epic", "E999",
             "--session-id", "sess-a"])
        self.assertEqual(code, 3, out)

    def test_clear_lock_existing_epic_no_lock_noop(self):
        """clear-lock on existing epic with no _lock returns 0 (regression guard)."""
        epic_dir = os.path.join(self.state_root, "active", "epic-999")
        os.makedirs(epic_dir)
        epic_file_path = os.path.join(epic_dir, "epic.yaml")
        with open(epic_file_path, "w", encoding="utf-8") as fh:
            fh.write("key: 'E999'\nstatus: in-progress\n")
        code, out = self.run_main(
            ["clear-lock", "--state-root", self.state_root, "--epic", "E999"])
        self.assertEqual(code, 0, out)
        self.assertIn("no _lock present", out)


class TestEpicMoves(TestLayoutResolution):
    """move-epic / archive-epic — epic directory moves between status folders."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_move_epic_planned_to_active(self):
        with redirect_stderr(io.StringIO()):             # no .git here: the fallback warns
            new = pm.move_epic(self.root, "E005", "active")
        self.assertTrue(new.endswith("active/epic-005"))
        self.assertTrue(os.path.isdir(new))
        self.assertFalse(os.path.isdir(os.path.join(self.root, "planned", "epic-005")))

    def test_move_epic_preserves_tree(self):
        with redirect_stderr(io.StringIO()):             # no .git here: the fallback warns
            pm.move_epic(self.root, "E001", "archived")
        self.assertTrue(os.path.exists(os.path.join(
            self.root, "archived", "epic-001", "sprint-01", "E001-S01-003.yaml")))

    def test_move_epic_updates_status_field(self):
        with redirect_stderr(io.StringIO()):             # no .git here: the fallback warns
            pm.move_epic(self.root, "E005", "active")
        _, node = pm.load_node(pm.epic_file(self.root, "E005"))
        self.assertEqual(node["status"], "in-progress")

    def test_move_epic_rejects_bad_status(self):
        with self.assertRaises(ValueError):
            pm.move_epic(self.root, "E001", "nonsense")

    def test_move_epic_refuses_existing_destination(self):
        os.makedirs(os.path.join(self.root, "archived", "epic-001"))
        with self.assertRaises(FileExistsError):
            pm.move_epic(self.root, "E001", "archived")

    def test_archive_epic_alias(self):
        code, out = self.run_main(["archive-epic", "--state-root", self.root, "--epic", "E001"])
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.isdir(os.path.join(self.root, "archived", "epic-001")))

    def test_version_constant_and_marker_agree(self):
        """self-install parses the `# pm-status-version:` marker off a copy on disk and
        compares it to PM_STATUS_VERSION. If the two ever diverge, propagation breaks
        silently — so assert the invariant rather than pinning a literal that has to be
        edited on every release."""
        marker = pm._parse_version_line(SCRIPT)
        self.assertIsNotNone(marker, "top-of-file pm-status-version marker not found")
        self.assertEqual(marker, tuple(int(x) for x in pm.PM_STATUS_VERSION.split(".")))

    def test_move_epic_already_in_place_is_noop(self):
        """E001 already lives under active/ — moving it to 'active' must return the
        existing path unchanged and must not touch epic.yaml's status field."""
        before = pm.epic_file(self.root, "E001")
        _, before_node = pm.load_node(before)
        self.assertEqual(before_node["status"], "in-progress")

        dest = pm.move_epic(self.root, "E001", "active")
        self.assertEqual(os.path.abspath(dest), os.path.abspath(
            os.path.join(self.root, "active", "epic-001")))

        _, after_node = pm.load_node(pm.epic_file(self.root, "E001"))
        self.assertEqual(after_node["status"], "in-progress")
        self.assertNotIn("updated_at", after_node)  # untouched — no write happened

    # --- CLI-level exit-code contract: cmd_move_epic must translate the
    # move_epic() exceptions to the documented exit codes when invoked through
    # pm.main(...), not just when move_epic() is called directly. ---

    def test_cli_move_epic_missing_epic_exits_3(self):
        code, out = self.run_main(
            ["move-epic", "--state-root", self.root, "--epic", "E999", "--to", "archived"])
        self.assertEqual(code, 3, out)

    def test_cli_move_epic_existing_destination_exits_2(self):
        os.makedirs(os.path.join(self.root, "archived", "epic-001"))
        code, out = self.run_main(
            ["move-epic", "--state-root", self.root, "--epic", "E001", "--to", "archived"])
        self.assertEqual(code, 2, out)

    def test_cli_move_epic_invalid_to_is_rejected(self):
        # argparse `choices` rejects this before cmd_move_epic ever runs; assert the
        # observed exit code (2, argparse's own usage-error convention) rather than
        # assuming it flows through cmd_move_epic's own exception mapping.
        code, out = self.run_main(
            ["move-epic", "--state-root", self.root, "--epic", "E001", "--to", "nonsense"])
        self.assertEqual(code, 2, out)

    def test_cli_archive_epic_alias_missing_epic_exits_3(self):
        code, out = self.run_main(
            ["archive-epic", "--state-root", self.root, "--epic", "E999"])
        self.assertEqual(code, 3, out)


class TestEpicMovesGitBacked(unittest.TestCase):
    """move_epic's *preferred* path is `git mv`, not the shutil fallback —
    TestLayoutResolution's fixture is a plain tempdir with no .git ancestor, so
    every TestEpicMoves case above exercises only the fallback. This class builds
    a real git repo so the git-mv branch actually runs, and asserts the property
    the whole directory-move design exists for: `git log --follow` survives the
    move."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.root = os.path.join(self.d, "state")
        sd = os.path.join(self.root, "active", "epic-001", "sprint-01")
        os.makedirs(sd)
        with open(os.path.join(self.root, "active", "epic-001", "epic.yaml"), "w") as f:
            f.write("key: 'E001'\nstatus: in-progress\n")
        with open(os.path.join(sd, "sprint.yaml"), "w") as f:
            f.write("key: 'S01'\nepic: 'E001'\nstatus: in-progress\n")
        with open(os.path.join(sd, "E001-S01-003.yaml"), "w") as f:
            f.write("key: 'E001-S01-003'\nepic: 'E001'\nsprint: 'S01'\nstatus: review\n")

        self._run_git(["init", "-q", "."])
        self._run_git(["config", "user.email", "pm-status-tests@example.invalid"])
        self._run_git(["config", "user.name", "pm-status-tests"])
        self._run_git(["add", "-A"])
        self._run_git(["commit", "-q", "-m", "seed"])

    def _run_git(self, args):
        import subprocess
        r = subprocess.run(["git"] + args, cwd=self.root, capture_output=True, text=True)
        if r.returncode != 0:
            self.fail(f"git {' '.join(args)} failed: {r.stdout}{r.stderr}")
        return r.stdout

    def test_move_epic_uses_git_mv_and_stays_tracked(self):
        moved_story = os.path.join(self.root, "archived", "epic-001", "sprint-01",
                                    "E001-S01-003.yaml")
        pm.move_epic(self.root, "E001", "archived")
        self.assertTrue(os.path.exists(moved_story))

        # If shutil.move had run instead of `git mv`, the destination files would be
        # untracked (git status would show them as new/untracked "??", not present
        # in `git ls-files`). Showing up in `git ls-files` at the new path proves
        # the git-mv branch — not the fallback — actually executed.
        tracked = self._run_git(["ls-files", "archived/epic-001"])
        self.assertIn("archived/epic-001/sprint-01/E001-S01-003.yaml", tracked)
        self.assertIn("archived/epic-001/epic.yaml", tracked)

    def test_move_epic_with_relative_state_root_still_uses_git_mv(self):
        """Regression: a RELATIVE --state-root used to resolve twice — once against the
        caller's process cwd when the operands were built, and again against
        `cwd=state_root` inside the subprocess — so `git mv` was handed a path that did
        not exist, failed, and fell silently through to `shutil.move`: exit 0, no
        warning, no rename recorded. Every other test here uses an absolute tempdir, so
        that branch went untested. move_epic now absolutizes both operands and the cwd."""
        prev_cwd = os.getcwd()
        os.chdir(self.d)
        try:
            pm.move_epic("state", "E001", "archived")  # relative state root
        finally:
            os.chdir(prev_cwd)

        moved_story = os.path.join(self.root, "archived", "epic-001", "sprint-01",
                                   "E001-S01-003.yaml")
        self.assertTrue(os.path.exists(moved_story))

        # git must have RECORDED the rename, not just seen a delete+add.
        status = self._run_git(["status", "--porcelain"])
        self.assertTrue(any(ln.startswith("R") for ln in status.splitlines()),
                        f"expected a staged rename (R), got:\n{status}")
        tracked = self._run_git(["ls-files", "archived/epic-001"])
        self.assertIn("archived/epic-001/sprint-01/E001-S01-003.yaml", tracked)
        # Nothing left untracked by a shutil fallback. The ONE expected untracked entry is the
        # state root's .gitignore, which the epic lock wrote so lock files are never committed.
        untracked = [ln for ln in status.splitlines() if ln.startswith("??")]
        self.assertEqual(untracked, ["?? .gitignore"], status)
        # The epic's lock file, state/epic-001.lock, sits outside the moved directory by design
        # (epic_lock_path) and is now ignored -- pinned exactly among the IGNORED entries, so a
        # stray lock inside the moved tree still fails.
        ignored = [ln for ln in self._run_git(["status", "--porcelain", "--ignored"]).splitlines()
                   if ln.startswith("!!")]
        self.assertEqual(ignored, ["!! epic-001.lock"], status)

    def test_move_epic_warns_on_stderr_when_git_mv_falls_back(self):
        """The fallback is a real loss of history, so it must never be silent."""
        non_git = tempfile.mkdtemp()
        try:
            root = os.path.join(non_git, "state")
            os.makedirs(os.path.join(root, "active", "epic-001"))
            with open(os.path.join(root, "active", "epic-001", "epic.yaml"), "w") as f:
                f.write("key: 'E001'\nstatus: in-progress\n")
            err = io.StringIO()
            with redirect_stderr(err):
                pm.move_epic(root, "E001", "archived")
            msg = err.getvalue()
            self.assertIn("WARNING", msg)
            self.assertIn("git mv", msg)
            self.assertIn("--follow", msg)
        finally:
            import shutil
            shutil.rmtree(non_git, ignore_errors=True)

    def test_move_epic_preserves_history_via_git_log_follow(self):
        pre_move_log = self._run_git(
            ["log", "--oneline", "--",
             "active/epic-001/sprint-01/E001-S01-003.yaml"]).strip()
        self.assertTrue(pre_move_log, "fixture commit should already show in git log")

        pm.move_epic(self.root, "E001", "archived")
        # commit the move itself — git mv only stages the rename; --follow across
        # an uncommitted-but-staged rename works too, but committing matches how
        # the tool is actually used and removes any ambiguity.
        self._run_git(["commit", "-q", "-m", "archive epic"])

        follow_log = self._run_git(
            ["log", "--follow", "--oneline", "--",
             "archived/epic-001/sprint-01/E001-S01-003.yaml"])
        lines = [ln for ln in follow_log.splitlines() if ln.strip()]
        self.assertEqual(len(lines), 2, follow_log)  # "seed" + "archive epic"
        self.assertIn("seed", follow_log)


class TestCalibrationIO(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.root = os.path.join(self.d, "state")
        os.makedirs(self.root)

    def test_missing_file_yields_skeleton_not_error(self):
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(cal["version"], 2)
        self.assertEqual(cal["granularity"], "story")
        self.assertIn("scope", cal)
        self.assertIn("closure", cal)
        self.assertIn("fix", cal)

    def test_granularity_persists_in_file_not_a_binding(self):
        y, cal = pm.load_calibration(self.root)
        cal["granularity"] = "sprint"
        pm.save_calibration(y, cal, self.root)
        _, again = pm.load_calibration(self.root)
        self.assertEqual(again["granularity"], "sprint")

    def test_weighted_ratio_favours_recent_samples(self):
        # oldest first; decay 0.8 means later samples dominate
        older_heavy = pm.weighted_ratio([2.0, 1.0])
        newer_heavy = pm.weighted_ratio([1.0, 2.0])
        self.assertLess(older_heavy, newer_heavy)

    def test_weighted_ratio_single_sample_is_that_sample(self):
        self.assertAlmostEqual(pm.weighted_ratio([1.4]), 1.4)

    def test_component_below_threshold_is_not_active(self):
        y, cal = pm.load_calibration(self.root)
        cal["scope"]["complex"] = {"man_hours": {"samples": [1.2, 1.3]}}
        pm.save_calibration(y, cal, self.root)
        _, cal2 = pm.load_calibration(self.root)
        self.assertIsNone(pm.active_scope_ratio(cal2, "complex", "man_hours"))

    def test_component_at_threshold_is_active(self):
        y, cal = pm.load_calibration(self.root)
        cal["scope"]["complex"] = {"man_hours": {"samples": [1.2, 1.3, 1.4]}}
        pm.save_calibration(y, cal, self.root)
        _, cal2 = pm.load_calibration(self.root)
        self.assertIsNotNone(pm.active_scope_ratio(cal2, "complex", "man_hours"))

    def test_fix_needs_both_cohorts_at_threshold(self):
        y, cal = pm.load_calibration(self.root)
        cal["fix"]["complex"] = {
            "clean": {"mean_man_hours": 7.0, "samples": 5},
            "reworked": {"mean_man_hours": 9.0, "samples": 0},
        }
        pm.save_calibration(y, cal, self.root)
        _, cal2 = pm.load_calibration(self.root)
        self.assertIsNone(pm.active_fix_factor(cal2, "complex"))

    def test_fix_active_when_both_cohorts_reach_threshold(self):
        y, cal = pm.load_calibration(self.root)
        cal["fix"]["complex"] = {
            "clean": {"mean_man_hours": 8.0, "samples": 3},
            "reworked": {"mean_man_hours": 10.0, "samples": 3},
        }
        pm.save_calibration(y, cal, self.root)
        _, cal2 = pm.load_calibration(self.root)
        self.assertAlmostEqual(pm.active_fix_factor(cal2, "complex"), 1.25)

    def test_v1_file_migrates_and_preserves_original(self):
        p = pm.calibration_path(self.root)
        with open(p, "w") as f:
            f.write("version: 1\nratio: 1.3\n")
        y, cal = pm.load_calibration(self.root)
        cal = pm.migrate_calibration(y, cal, self.root)
        self.assertEqual(cal["version"], 2)
        self.assertTrue(os.path.exists(p + ".v1"))
        # closure and fix start fresh, never seeded from the blended ratio.
        # Assert emptiness per bucket rather than comparing a CommentedMap to a
        # plain dict, which is fragile across ruamel versions.
        for level in ("sprint", "epic"):
            self.assertEqual(len(cal["closure"][level]), 0)
        for c in ("simple", "standard", "complex"):
            self.assertEqual(len(cal["fix"][c]), 0)
        # the blended v1 ratio landed on scope, and only on scope
        self.assertGreater(len(cal["scope"]["complex"]), 0)

    def test_show_on_missing_file_exits_0(self):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(["calibration", "show", "--state-root", self.root])
        except SystemExit as e:
            code = e.code
        self.assertEqual(code, 0)
        self.assertIn("cold-start", buf.getvalue().lower())


class TestCalibrationMetricsMigration(unittest.TestCase):
    """`migrate_calibration_metrics` reshapes a pre-metrics-rework calibration
    file in place, without bumping `version` (still 2 — compatibility is by
    shape-tolerant reads, never a version gate).

    Gating is by a POSITIVE MARKER (`CALIBRATION_METRICS_MARKER`,
    `metrics_migrated_at`), stamped once a real pass through the function
    finishes — even a no-op one. An earlier design inferred "not yet
    migrated" from the presence/absence of the old `cost`/`time_hours` keys;
    the coordinator rejected it because that inference has a silent blind
    spot on a non-Claude-runtime project (cost is always N/A there, so a
    file that also lacks time_hours samples would read as "already
    migrated" and never have its man_hours/fix samples quarantined — see
    test_man_hours_quarantined_even_without_cost_or_time_hours_markers,
    which falsifies that design). `man_hours` and `fix` now quarantine
    unconditionally on the one authoritative pass, no corroborating marker
    needed.

    The main "before" fixture (in setUp) is hand-authored, not built by
    running a real command: `git log -S` over this file's whole history
    turns up no commit where a calibration SCOPE/CLOSURE bucket ever used a
    literal "time_hours" key (METRIC_FIELDS already read "elapsed_hours" as
    far back as the file goes) or calibrated `cost` unconditionally without
    excluding it — the "old rules" this task migrates away from predate
    what this repo tracks. There is no real command left in this codebase
    whose output would produce that shape, so hand-authoring the fixture
    (matching the task brief's own Step-1 fixture) is the only option.
    Where a REAL write path can produce genuine data instead (the `fix`
    cohort structure has not changed shape at all, and neither has a lone
    `man_hours` sample), the tests below use it — see
    test_fix_cohort_built_via_real_writes_is_quarantined_wholesale and
    test_man_hours_written_after_the_one_time_cutover_is_never_revisited.
    """

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.root = os.path.join(self.d, "state")
        os.makedirs(self.root)
        with open(pm.calibration_path(self.root), "w") as f:
            f.write(
                "version: 2\n"
                "granularity: story\n"
                "scope:\n"
                "  complex:\n"
                "    man_hours: {samples: [1.1, 1.2, 1.3]}\n"
                "    time_hours: {samples: [0.9, 1.0, 1.1]}\n"
                "    tokens_k: {samples: [4.0, 4.5, 5.0]}\n"
                "    cost: {samples: [2.0, 2.1, 2.2]}\n"
                "closure:\n"
                "  sprint:\n"
                "    cost: {samples: [1.5]}\n"
            )

    def _migrate(self):
        y, cal = pm.load_calibration(self.root)
        log = pm.migrate_calibration_metrics(y, cal, self.root)
        pm.save_calibration(y, cal, self.root)
        return cal, log

    def test_version_is_not_bumped(self):
        cal, _ = self._migrate()
        self.assertEqual(int(cal["version"]), 2)

    def test_cost_component_is_dropped(self):
        cal, _ = self._migrate()
        self.assertNotIn("cost", cal["scope"]["complex"])
        self.assertNotIn("cost", cal["closure"]["sprint"])

    def test_man_hours_is_quarantined_not_deleted(self):
        cal, _ = self._migrate()
        self.assertNotIn("man_hours", cal["scope"]["complex"])
        self.assertEqual(cal["legacy"]["scope"]["complex"]["man_hours"]["samples"],
                         [1.1, 1.2, 1.3])

    def test_time_hours_carried_forward_under_the_new_name(self):
        cal, _ = self._migrate()
        self.assertNotIn("time_hours", cal["scope"]["complex"])
        self.assertEqual(cal["scope"]["complex"]["elapsed_hours"]["samples"],
                         [0.9, 1.0, 1.1])

    def test_tokens_carried_and_flagged_when_out_of_range(self):
        cal, log = self._migrate()
        self.assertIn("tokens_k", cal["scope"]["complex"])
        self.assertTrue(any("FLAG" in line and "tokens_k" in line for line in log))

    def test_new_components_are_seeded_empty(self):
        cal, _ = self._migrate()
        self.assertEqual(cal["orchestration"]["sprint"], {})
        self.assertEqual(cal["token_mix"]["samples"], [])

    def test_pre_migration_file_reads_as_cold_start_not_an_error(self):
        """Shape-tolerant reads are what let `version` stay at 2: a read-only
        command must handle an unmigrated file without raising and without
        migrating it."""
        _, cal = pm.load_calibration(self.root)
        self.assertIsNone(pm.active_orchestration_fraction(cal, "sprint", "tokens_k"))
        self.assertEqual(pm.observed_mix(cal), pm.COLD_START_TOKEN_MIX)
        self.assertFalse(os.path.exists(pm.calibration_path(self.root) + ".pre-metrics"))

    def test_backup_written_and_migration_idempotent(self):
        self._migrate()
        self.assertTrue(os.path.exists(pm.calibration_path(self.root) + ".pre-metrics"))
        cal2, log2 = self._migrate()
        self.assertEqual(log2, [])
        self.assertEqual(cal2["scope"]["complex"]["elapsed_hours"]["samples"],
                         [0.9, 1.0, 1.1])

    def test_backup_preserves_the_exact_pre_migration_bytes(self):
        # Not just "a backup exists" — it must be the file as it stood BEFORE
        # any reshaping, taken before the drop/rename/quarantine mutations,
        # not some already-mutated snapshot.
        with open(pm.calibration_path(self.root), "rb") as f:
            original = f.read()
        self._migrate()
        with open(pm.calibration_path(self.root) + ".pre-metrics", "rb") as f:
            backed_up = f.read()
        self.assertEqual(backed_up, original)

    def test_closure_bucket_left_empty_not_removed_after_its_only_key_drops(self):
        # closure.sprint had only `cost`; dropping it must leave an empty
        # mapping behind, not delete the "sprint" bucket itself (a future
        # closure sample still needs somewhere to land under "sprint").
        cal, _ = self._migrate()
        self.assertIn("sprint", cal["closure"])
        self.assertEqual(len(cal["closure"]["sprint"]), 0)

    def test_man_hours_quarantined_even_without_cost_or_time_hours_markers(self):
        """The coordinator's motivating case: a non-Claude-runtime project
        never accumulates `cost` samples (cost is N/A there and skipped by
        calibration), and may equally have no `time_hours` samples for any
        other reason. Such a file's ONLY sign of pre-rework vintage is the
        man_hours samples themselves — no unambiguous key at all.

        This is the test that falsifies inferring "already migrated" from
        legacy-key presence/absence: that design would read "no cost, no
        time_hours" as "nothing to do" and leave old-definition man_hours
        ratios silently in force forever. Gating on a positive marker
        instead means an unmigrated file gets the full treatment regardless
        of which sample types it happens to contain.
        """
        root = os.path.join(self.d, "no-cost-no-time-state")
        os.makedirs(root)
        with open(pm.calibration_path(root), "w") as f:
            f.write(
                "version: 2\n"
                "granularity: story\n"
                "scope:\n"
                "  standard:\n"
                "    man_hours: {samples: [3.0, 3.1, 3.2]}\n"
            )
        y, cal = pm.load_calibration(root)
        log = pm.migrate_calibration_metrics(y, cal, root)
        pm.save_calibration(y, cal, root)
        self.assertTrue(any("QUARANTINE" in line and "man_hours" in line for line in log))
        self.assertNotIn("man_hours", cal["scope"]["standard"])
        self.assertEqual(cal["legacy"]["scope"]["standard"]["man_hours"]["samples"],
                         [3.0, 3.1, 3.2])

    def test_man_hours_written_after_the_one_time_cutover_is_never_revisited(self):
        """Data-safety proof, built via the REAL write path (not a
        hand-authored fixture): the migration's one authoritative pass runs
        on a project's VERY FIRST write, before that write's own sample is
        even appended — even when there is nothing yet to migrate — and
        stamps CALIBRATION_METRICS_MARKER right there. Every man_hours
        sample written by every subsequent real write to that same project,
        no matter how many, is therefore never revisited: the marker gate
        short-circuits before any bucket is even inspected again.

        This is the replacement for an earlier test of the same name's
        intent that reasoned about per-bucket "corroborating markers" — a
        mechanism the coordinator correctly rejected (see
        migrate_calibration_metrics's docstring and
        test_man_hours_quarantined_even_without_cost_or_time_hours_markers).
        The safety property survives; the mechanism producing it changed.
        """
        fresh_root = os.path.join(self.d, "fresh-state")
        os.makedirs(fresh_root)
        est = {"man_hours": 6, "elapsed_hours": 1.5, "tokens_k": 320,
               "cost": 4.80, "fix_factor": 1.25, "scope_ratio": 1.0}
        act = {"man_hours": 7, "elapsed_hours": 1.8, "tokens_k": {"total": 355},
               "cost": 5.32}

        def _node(key):
            return {"key": key, "classification": "standard",
                    "estimate": dict(est), "actual": dict(act),
                    "completion_evidence": {"fix_iterations": 0}}

        pm.record_story_sample(fresh_root, _node("E001-S01-001"))  # real write path
        _, cal = pm.load_calibration(fresh_root)
        self.assertIn(pm.CALIBRATION_METRICS_MARKER, cal)  # stamped on the very first write
        self.assertNotIn("legacy", cal)  # nothing existed yet to quarantine
        self.assertEqual(len(pm._component_samples(cal, "scope", "standard", "man_hours")), 1)

        pm.record_story_sample(fresh_root, _node("E001-S01-002"))  # a later real write
        _, cal2 = pm.load_calibration(fresh_root)
        self.assertEqual(len(pm._component_samples(cal2, "scope", "standard", "man_hours")), 2)
        self.assertNotIn("legacy", cal2)  # neither sample was ever touched

    def test_fix_cohort_built_via_real_writes_is_quarantined_wholesale(self):
        """The `fix` payload here is 100% real: built by calling
        `record_story_sample` (the actual write path) three times, on a
        FRESH root, so the `clean` cohort crosses MIN_SAMPLES exactly as a
        real project would. The first of those three writes stamps
        CALIBRATION_METRICS_MARKER (the migration's own one-time-pass
        marker) since nothing existed yet to migrate — correctly, per
        test_man_hours_written_after_the_one_time_cutover_is_never_revisited.

        To then prove `fix` DOES quarantine wholesale on a genuinely
        unmigrated file (decision: no per-metric split, no corroborating
        marker needed — see migrate_calibration_metrics's docstring), this
        strips that marker before calling migrate_calibration_metrics
        directly: no real pre-Task-11 project's calibration file could ever
        have carried a marker this task itself introduces, so stripping it
        is the accurate way to simulate genuine pre-upgrade disk state.
        Everything else here — the fix cohort itself, and the assertion
        that it moved intact — is real data from real writes, not
        hand-authored.
        """
        fresh_root = os.path.join(self.d, "fix-quarantine-state")
        os.makedirs(fresh_root)
        for i in range(3):
            node = {"key": f"E001-S01-{i:03d}", "classification": "complex",
                    "estimate": {"man_hours": 6, "elapsed_hours": 1.5, "tokens_k": 320,
                                 "cost": 4.80, "fix_factor": 1.25, "scope_ratio": 1.0},
                    "actual": {"man_hours": 7, "elapsed_hours": 1.8,
                               "tokens_k": {"total": 355}, "cost": 5.32},
                    "completion_evidence": {"fix_iterations": 0}}
            pm.record_story_sample(fresh_root, node)
        _, cal = pm.load_calibration(fresh_root)
        self.assertEqual(int(cal["fix"]["complex"]["clean"]["samples"]), 3)
        self.assertIn(pm.CALIBRATION_METRICS_MARKER, cal)  # stamped by the first of these 3 writes
        pre_mean = float(cal["fix"]["complex"]["clean"]["mean_man_hours"])

        y, cal = pm.load_calibration(fresh_root)
        del cal[pm.CALIBRATION_METRICS_MARKER]
        pm.save_calibration(y, cal, fresh_root)

        y, cal = pm.load_calibration(fresh_root)
        log = pm.migrate_calibration_metrics(y, cal, fresh_root)
        pm.save_calibration(y, cal, fresh_root)

        self.assertTrue(any("QUARANTINE" in line and "fix" in line for line in log))
        self.assertEqual(len(cal["fix"]["complex"]), 0)
        self.assertAlmostEqual(float(cal["legacy"]["fix"]["complex"]["clean"]["mean_man_hours"]),
                               pre_mean)
        self.assertEqual(int(cal["legacy"]["fix"]["complex"]["clean"]["samples"]), 3)

    def test_cli_migrate_metrics_action_reports_changes_then_zero(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = pm.main(["calibration", "migrate-metrics", "--state-root", self.root])
        self.assertEqual(code, 0)
        first = buf.getvalue()
        self.assertIn("OK calibration migrate-metrics", first)
        self.assertNotIn("(0 changes)", first)

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            code2 = pm.main(["calibration", "migrate-metrics", "--state-root", self.root])
        self.assertEqual(code2, 0)
        self.assertIn("(0 changes)", buf2.getvalue())


class TestCalibrationMetricsMigrationReadOnlySafety(TestLayoutResolution):
    """Read-only commands (`calibration show`, `estimate-story`,
    `estimate-rollup`) must never trigger the metrics migration — proved by
    comparing the calibration file's raw BYTES before and after, not merely
    checking that no exception was raised.
    """

    LEGACY_YAML = (
        "version: 2\n"
        "granularity: story\n"
        "scope:\n"
        "  complex:\n"
        "    man_hours: {samples: [1.1, 1.2, 1.3]}\n"
        "    time_hours: {samples: [0.9, 1.0, 1.1]}\n"
        "    tokens_k: {samples: [4.0, 4.5, 5.0]}\n"
        "    cost: {samples: [2.0, 2.1, 2.2]}\n"
        "closure:\n"
        "  sprint:\n"
        "    cost: {samples: [1.5]}\n"
    )

    def setUp(self):
        super().setUp()
        with open(pm.calibration_path(self.root), "w") as f:
            f.write(self.LEGACY_YAML)
        with open(pm.calibration_path(self.root), "rb") as f:
            self.before = f.read()

    def _unchanged(self):
        with open(pm.calibration_path(self.root), "rb") as f:
            after = f.read()
        self.assertEqual(after, self.before)

    def test_calibration_show_leaves_file_untouched(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = pm.main(["calibration", "show", "--state-root", self.root])
        self.assertEqual(code, 0)
        self._unchanged()

    def test_estimate_story_leaves_calibration_file_untouched(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = pm.main(["estimate-story", "--state-root", self.root,
                            "--story", "E001-S01-003", "--classification", "complex"])
        self.assertEqual(code, 0, buf.getvalue())
        self._unchanged()

    def test_estimate_rollup_leaves_calibration_file_untouched(self):
        sd = os.path.join(self.root, "active", "epic-001", "sprint-01")
        with open(os.path.join(sd, "E001-S01-003.yaml"), "w") as f:
            f.write("key: 'E001-S01-003'\nepic: 'E001'\nsprint: 'S01'\n"
                    "estimate:\n  man_hours: 4\n  elapsed_hours: 1\n"
                    "  tokens_k: 10\n  cost: 0.5\n")
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(io.StringIO()):
            code = pm.main(["estimate-rollup", "--state-root", self.root,
                            "--epic", "E001", "--sprint", "S01"])
        self.assertEqual(code, 0, buf.getvalue())
        self._unchanged()


class TestEstimateFactors(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_set_estimate_records_factors(self):
        # No --cost: cost is derived from tokens x rates and set-estimate
        # rejects it (see TestEstimateTokensAndCost.test_cost_low_flag_is_rejected).
        code, out = self.run_main(
            ["set-estimate", "--state-root", self.root, "--story", "E001-S01-003",
             "--man-hours", "6", "--time-hours", "1.5", "--tokens-k", "320",
             "--fix-factor", "1.25", "--scope-ratio", "1.1"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertAlmostEqual(float(node["estimate"]["fix_factor"]), 1.25)
        self.assertAlmostEqual(float(node["estimate"]["scope_ratio"]), 1.1)

    def test_factors_are_optional_and_absent_when_not_given(self):
        code, out = self.run_main(
            ["set-estimate", "--state-root", self.root, "--story", "E001-S01-003",
             "--man-hours", "6"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertNotIn("fix_factor", node["estimate"])


class TestStorySampling(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.root = os.path.join(self.d, "state")
        os.makedirs(self.root)

    def _story(self, iterations, est=None, act=None):
        est = est or {"man_hours": 6, "elapsed_hours": 1.5, "tokens_k": 320,
                      "cost": 4.80, "fix_factor": 1.25, "scope_ratio": 1.0}
        # tokens_k is a mapping on actuals (Task 6) — only "total" is read by
        # the sampler, so these fixtures carry just that key.
        act = act or {"man_hours": 7, "elapsed_hours": 1.8, "tokens_k": {"total": 355},
                      "cost": 5.32}
        node = {"key": "E001-S01-003", "classification": "complex",
                "estimate": est, "actual": act}
        if iterations is not None:
            node["completion_evidence"] = {"fix_iterations": iterations}
        return node

    def test_zero_iterations_gives_exact_provenance(self):
        s = pm.derive_story_sample(self._story(0))
        self.assertEqual(s["provenance"], "exact")

    def test_reworked_story_uses_backout_provenance(self):
        s = pm.derive_story_sample(self._story(3))
        self.assertEqual(s["provenance"], "backout")

    def test_absent_iterations_uses_backout(self):
        s = pm.derive_story_sample(self._story(None))
        self.assertEqual(s["provenance"], "backout")

    def test_legacy_estimate_without_factors_is_marked(self):
        est = {"man_hours": 6, "elapsed_hours": 1.5, "tokens_k": 320, "cost": 4.80}
        s = pm.derive_story_sample(self._story(0, est=est))
        self.assertEqual(s["provenance"], "legacy")

    def test_scope_ratio_computed_correctly_for_elapsed_hours(self):
        # estimate.elapsed_hours 1.5 vs actual.elapsed_hours 1.8, fix_factor 1.25
        s = pm.derive_story_sample(self._story(0))
        self.assertAlmostEqual(s["scope_ratios"]["elapsed_hours"], 1.8 * 1.25 / 1.5)

    def test_scope_ratio_computed_correctly_for_hitl_hours(self):
        # derive_story_sample iterates METRIC_FIELDS, not a hand-restated tuple —
        # this proves hitl_hours flows through the same as every other metric.
        est = {"man_hours": 6, "hitl_hours": 0.5, "elapsed_hours": 1.5, "tokens_k": 320,
               "cost": 4.80, "fix_factor": 1.25, "scope_ratio": 1.0}
        act = {"man_hours": 7, "hitl_hours": 0.6, "elapsed_hours": 1.8,
               "tokens_k": {"total": 355}, "cost": 5.32}
        s = pm.derive_story_sample(self._story(0, est=est, act=act))
        self.assertAlmostEqual(s["scope_ratios"]["hitl_hours"], 0.6 * 1.25 / 0.5)

    def test_na_metrics_are_skipped_not_zeroed(self):
        act = {"man_hours": 7, "elapsed_hours": 1.8, "tokens_k": "N/A", "cost": "N/A"}
        s = pm.derive_story_sample(self._story(0, act=act))
        self.assertNotIn("tokens_k", s["scope_ratios"])
        self.assertNotIn("cost", s["scope_ratios"])
        self.assertIn("man_hours", s["scope_ratios"])

    def test_dollar_prefixed_cost_does_not_break_derivation(self):
        # cost values can be stored '$'-prefixed (metrics-contract.md §9). cost
        # is derived from tokens x rates now and never scope-calibrates (Task
        # 7) — but a '$'-prefixed cost sitting alongside the calibrated
        # metrics must still not crash derivation or leak into scope_ratios.
        est = {"man_hours": 6, "elapsed_hours": 1.5, "tokens_k": 320,
               "cost": "$4.80", "fix_factor": 1.25, "scope_ratio": 1.0}
        act = {"man_hours": 7, "elapsed_hours": 1.8, "tokens_k": {"total": 355},
               "cost": "$5.32"}
        s = pm.derive_story_sample(self._story(0, est=est, act=act))
        self.assertNotIn("cost", s["scope_ratios"])
        self.assertAlmostEqual(s["scope_ratios"]["elapsed_hours"], 1.8 * 1.25 / 1.5)

    def test_no_estimate_yields_no_sample(self):
        node = {"key": "E001-S01-003", "classification": "complex",
                "actual": {"man_hours": 7}}
        self.assertIsNone(pm.derive_story_sample(node))

    def test_record_appends_to_scope_and_fix_cohort(self):
        pm.record_story_sample(self.root, self._story(0))
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(len(pm._component_samples(cal, "scope", "complex", "man_hours")), 1)
        self.assertEqual(int(cal["fix"]["complex"]["clean"]["samples"]), 1)

    def test_record_appends_the_observed_token_mix(self):
        # A real set-actual write always carries all four classes alongside
        # `total` (tokens_block builds them together) — a fixture with only
        # `total` (the rest of this file's default) can't exercise this.
        act = {"man_hours": 7, "elapsed_hours": 1.8,
               "tokens_k": {"total": 355, "input": 100, "output": 20,
                            "cache_write": 100, "cache_read": 135},
               "cost": 5.32}
        pm.record_story_sample(self.root, self._story(0, act=act))
        _, cal = pm.load_calibration(self.root)
        samples = cal["token_mix"]["samples"]
        self.assertEqual(len(samples), 1)
        self.assertAlmostEqual(samples[0]["input"], 100 / 355, places=4)
        self.assertAlmostEqual(sum(samples[0][c] for c in pm.TOKEN_CLASSES), 1.0, places=3)

    def test_record_skips_token_mix_when_actual_lacks_a_total(self):
        # tokens_k stays a scalar (legacy pre-Task-6 shape, or N/A) — no
        # `.get`, so the mix step must not raise and must not append.
        act = {"man_hours": 7, "elapsed_hours": 1.8, "tokens_k": "N/A", "cost": "N/A"}
        pm.record_story_sample(self.root, self._story(0, act=act))
        _, cal = pm.load_calibration(self.root)
        self.assertNotIn("token_mix", cal)

    def test_reworked_story_joins_reworked_cohort(self):
        pm.record_story_sample(self.root, self._story(2))
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(int(cal["fix"]["complex"]["reworked"]["samples"]), 1)
        self.assertEqual(int(cal["fix"]["complex"].get("clean", {}).get("samples", 0)), 0)

    def test_v1_file_is_migrated_not_corrupted_on_record(self):
        p = pm.calibration_path(self.root)
        with open(p, "w") as f:
            f.write("version: 1\nratio: 1.3\n")
        with redirect_stderr(io.StringIO()):    # migration announces its steps on stderr
            pm.record_story_sample(self.root, self._story(0))
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(cal["version"], pm.CALIBRATION_SCHEMA_VERSION)
        self.assertTrue(os.path.exists(p + ".v1"))
        # The v1->v2 migration seeds scope["complex"]["man_hours"] with the
        # old blended ratio as one sample; the metrics migration (Task 11)
        # then runs in the SAME record_story_sample call, immediately after,
        # and quarantines that seed — it is exactly as pre-rework as any
        # other legacy man_hours sample, just arrived via a different
        # upgrade path. Only the fresh sample this call itself derives lands
        # in scope; the v1 seed survives, moved, under `legacy`.
        self.assertEqual(len(pm._component_samples(cal, "scope", "complex", "man_hours")), 1)
        self.assertEqual(cal["legacy"]["scope"]["complex"]["man_hours"]["samples"], [1.3])
        self.assertEqual(int(cal["fix"]["complex"]["clean"]["samples"]), 1)


class TestClosureSampling(TestLayoutResolution):
    def _write(self, path, mapping):
        y = pm._yaml()
        with open(path, "w") as f:
            y.dump(mapping, f)

    def _sprint_with_stories(self, story_actuals, sprint_actual, sprint_estimate=None,
                             story_estimates=None):
        sd = os.path.join(self.root, "active", "epic-001", "sprint-01")
        for f in os.listdir(sd):
            if f.endswith(".yaml") and f != "sprint.yaml":
                os.remove(os.path.join(sd, f))
        for i, a in enumerate(story_actuals, start=1):
            m = {"key": f"E001-S01-{i:03d}", "epic": "E001", "sprint": "S01",
                 "status": "done"}
            if a is not None:
                m["actual"] = {"man_hours": a}
            if story_estimates is not None:
                m["estimate"] = {"man_hours": story_estimates[i - 1]}
            self._write(os.path.join(sd, f"E001-S01-{i:03d}.yaml"), m)
        sm = {"key": "S01", "epic": "E001", "status": "done"}
        if sprint_actual is not None:
            sm["actual"] = {"man_hours": sprint_actual}
        if sprint_estimate is not None:
            sm["estimate"] = sprint_estimate
        self._write(os.path.join(sd, "sprint.yaml"), sm)

    def test_residual_is_parent_minus_children(self):
        self._sprint_with_stories([3.0, 4.0], 9.0,
                                  {"man_hours_low": 1.0, "man_hours_high": 3.0})
        s, reason = pm.derive_closure_sample(self.root, "sprint", "E001", "S01")
        self.assertIsNotNone(s, reason)
        self.assertAlmostEqual(s["closure_actual"]["man_hours"], 2.0)

    def test_missing_child_actual_skips_with_reason(self):
        self._sprint_with_stories([3.0, None], 9.0,
                                  {"man_hours_low": 1.0, "man_hours_high": 3.0})
        s, reason = pm.derive_closure_sample(self.root, "sprint", "E001", "S01")
        self.assertIsNone(s)
        self.assertIn("actual", reason.lower())

    def test_negative_residual_skips_with_reason(self):
        self._sprint_with_stories([5.0, 5.0], 8.0,
                                  {"man_hours_low": 1.0, "man_hours_high": 3.0})
        s, reason = pm.derive_closure_sample(self.root, "sprint", "E001", "S01")
        self.assertIsNone(s)
        self.assertIn("negative", reason.lower())

    def test_no_parent_actual_skips(self):
        self._sprint_with_stories([3.0, 4.0], None,
                                  {"man_hours_low": 1.0, "man_hours_high": 3.0})
        s, reason = pm.derive_closure_sample(self.root, "sprint", "E001", "S01")
        self.assertIsNone(s)

    def test_record_appends_closure_sample(self):
        # children estimated 3+4=7, parent estimated 8-9 (mid 8.5) -> estimated
        # closure overhead 1.5; actual overhead 9-(3+4)=2 -> ratio 2/1.5
        self._sprint_with_stories([3.0, 4.0], 9.0,
                                  {"man_hours_low": 8.0, "man_hours_high": 9.0},
                                  story_estimates=[3.0, 4.0])
        pm.record_closure_sample(self.root, "sprint", "E001", "S01")
        _, cal = pm.load_calibration(self.root)
        samples = pm._component_samples(cal, "closure", "sprint", "man_hours")
        self.assertEqual(len(samples), 1)
        self.assertAlmostEqual(float(samples[0]), round(2.0 / 1.5, 4))

    def test_closure_ratio_divides_by_estimated_overhead_not_whole_estimate(self):
        # THE C2 REGRESSION: dividing by the whole parent estimate midpoint (8.5)
        # would give 0.2353 and make the learned roll-up worse than cold start.
        self._sprint_with_stories([3.0, 4.0], 9.0,
                                  {"man_hours_low": 8.0, "man_hours_high": 9.0},
                                  story_estimates=[3.0, 4.0])
        s, reason = pm.derive_closure_sample(self.root, "sprint", "E001", "S01")
        self.assertIsNotNone(s, reason)
        self.assertAlmostEqual(s["ratios"]["man_hours"], 2.0 / 1.5)

    def test_applied_closure_ratio_is_divided_back_out(self):
        # a parent estimate written with an active ratio carries it on the block;
        # the sample must remove it, or the loop settles on a geometric mean
        self._sprint_with_stories([3.0, 4.0], 9.0,
                                  {"man_hours_low": 8.0, "man_hours_high": 9.0,
                                   "closure_ratios": {"man_hours": 2.0}},
                                  story_estimates=[3.0, 4.0])
        s, _ = pm.derive_closure_sample(self.root, "sprint", "E001", "S01")
        self.assertAlmostEqual(s["ratios"]["man_hours"], 2.0 * 2.0 / 1.5)

    def test_parent_actual_equal_to_children_sum_is_skipped_not_sampled_as_zero(self):
        """C2: the pre-fix closure step files instructed an EXACT sum of children,
        which makes the residual identically zero. `residual < 0` was guarded;
        `residual == 0` was not, so a 0.0 landed in the sample list as if it were
        a measurement. Exercise the number those step files actually produced."""
        self._sprint_with_stories([3.0, 4.0], 7.0,
                                  {"man_hours_low": 8.0, "man_hours_high": 9.0},
                                  story_estimates=[3.0, 4.0])
        s, reason = pm.derive_closure_sample(self.root, "sprint", "E001", "S01")
        self.assertIsNone(s, f"a bare-sum actual must produce NO sample, got {s}")
        self.assertIn("zero residual", reason)
        pm.record_closure_sample(self.root, "sprint", "E001", "S01")
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(pm._component_samples(cal, "closure", "sprint", "man_hours"), [])

    def test_bare_sum_of_unrepresentable_decimals_is_still_skipped(self):
        """The zero-residual guard must not be exact float equality.

        `residual = pv - total` is unrounded float arithmetic. Every other test in
        this file uses exactly-representable values (3.0 + 4.0 = 7.0), so an
        `== 0` check passes all of them while missing every real project that
        records hours in tenths. Both directions are exercised because a bare sum
        over decimals lands on either side of zero depending on the values, and
        the negative one used to be reported as a "miscount" that did not happen.
        """
        for children, parent, drift in (([0.3, 0.6], 0.9, "positive"),
                                        ([1.1, 2.2], 3.3, "negative")):
            with self.subTest(drift=drift):
                # the premise: these do NOT sum exactly, in either direction
                self.assertNotEqual(sum(children), parent)
                self._sprint_with_stories(
                    children, parent,
                    {"man_hours_low": parent + 1.0, "man_hours_high": parent + 3.0},
                    story_estimates=list(children))
                s, reason = pm.derive_closure_sample(self.root, "sprint", "E001", "S01")
                self.assertIsNone(s, f"{drift} float drift produced a sample: {s}")
                self.assertIn("zero residual", reason)
                self.assertNotIn("miscounted", reason)
                pm.record_closure_sample(self.root, "sprint", "E001", "S01")
                _, cal = pm.load_calibration(self.root)
                self.assertEqual(
                    pm._component_samples(cal, "closure", "sprint", "man_hours"), [])
                _, snode = pm.load_node(pm.sprint_file(self.root, "E001", "S01"))
                self.assertNotIn(pm.CALIBRATION_MARKER, snode)

    def test_tolerance_does_not_swallow_a_genuine_small_residual(self):
        """The other half of the guard: a real closure overhead, however small,
        must still record. A tolerance wide enough to eat one is the same defect
        with a different sign."""
        self._sprint_with_stories([0.3, 0.6], 0.9001,
                                  {"man_hours_low": 1.0, "man_hours_high": 3.0},
                                  story_estimates=[0.3, 0.6])
        s, reason = pm.derive_closure_sample(self.root, "sprint", "E001", "S01")
        self.assertIsNotNone(s, reason)
        self.assertAlmostEqual(s["closure_actual"]["man_hours"], 0.0001, places=7)

    def test_three_bare_sum_closes_never_train_the_ratio_to_zero(self):
        """The composite failure, not the single sample: three sprints closed with
        `actual == Σ children` used to leave `closure.sprint.man_hours` holding
        [0.0, 0.0, 0.0]. `weighted_ratio` returns 0.0 for that, 0.0 is not None,
        and `cmd_estimate_rollup` accepts it — so the closure band contributed
        nothing to every later estimate, permanently. The component must stay
        cold-start (None) instead."""
        for n in range(1, 4):
            skey = f"S{n:02d}"
            sd = os.path.join(self.root, "active", "epic-001", f"sprint-{n:02d}")
            os.makedirs(sd, exist_ok=True)
            for i in (1, 2):
                self._write(os.path.join(sd, f"E001-{skey}-{i:03d}.yaml"),
                            {"key": f"E001-{skey}-{i:03d}", "epic": "E001", "sprint": skey,
                             "status": "done", "estimate": {"man_hours": 5.0},
                             "actual": {"man_hours": 5.0}})
            self._write(os.path.join(sd, "sprint.yaml"),
                        {"key": skey, "epic": "E001", "status": "done",
                         "estimate": {"man_hours_low": 11.0, "man_hours_high": 13.0},
                         "actual": {"man_hours": 10.0}})   # the BARE SUM
            pm.record_closure_sample(self.root, "sprint", "E001", skey)
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(pm._component_samples(cal, "closure", "sprint", "man_hours"), [])
        self.assertIsNone(pm.active_closure_ratio(cal, "sprint", "man_hours"))

    def test_zero_estimated_overhead_skips_the_metric(self):
        # parent estimated exactly its children -> nothing to measure against
        self._sprint_with_stories([3.0, 4.0], 9.0,
                                  {"man_hours_low": 7.0, "man_hours_high": 7.0},
                                  story_estimates=[3.0, 4.0])
        s, _ = pm.derive_closure_sample(self.root, "sprint", "E001", "S01")
        self.assertNotIn("man_hours", s["ratios"])
        self.assertIn("man_hours", s["skipped"])

    def test_cost_is_never_closure_sampled(self):
        # Task 10: cost is now derived from the rolled-up tokens_k range at
        # estimate-rollup time, so it must never accumulate its own closure
        # ratio — CLOSURE_RANGE_KEYS drops "cost" entirely (previously
        # test_dollar_prefixed_cost_contributes_to_closure_sample asserted the
        # opposite; a lingering cost closure sample would band a value the
        # estimate no longer bands). man_hours is present alongside the
        # dollar-prefixed cost actuals so the sample still succeeds overall —
        # this proves cost is skipped by design, not because nothing else
        # produced a residual.
        sd = os.path.join(self.root, "active", "epic-001", "sprint-01")
        for f in os.listdir(sd):
            if f.endswith(".yaml") and f != "sprint.yaml":
                os.remove(os.path.join(sd, f))
        self._write(os.path.join(sd, "E001-S01-001.yaml"),
                    {"key": "E001-S01-001", "epic": "E001", "sprint": "S01",
                     "status": "done", "actual": {"man_hours": 3.0, "cost": "$3.00"}})
        self._write(os.path.join(sd, "E001-S01-002.yaml"),
                    {"key": "E001-S01-002", "epic": "E001", "sprint": "S01",
                     "status": "done", "actual": {"man_hours": 4.0, "cost": "$4.00"}})
        self._write(os.path.join(sd, "sprint.yaml"),
                    {"key": "S01", "epic": "E001", "status": "done",
                     "actual": {"man_hours": 9.0, "cost": "$9.00"},
                     "estimate": {"man_hours_low": 8.0, "man_hours_high": 9.0,
                                  "cost_low": 1.0, "cost_high": 3.0}})
        s, reason = pm.derive_closure_sample(self.root, "sprint", "E001", "S01")
        self.assertIsNotNone(s, reason)
        self.assertAlmostEqual(s["closure_actual"]["man_hours"], 2.0)
        self.assertNotIn("cost", s["closure_actual"])
        self.assertNotIn("cost", s["ratios"])
        self.assertNotIn("cost", s["skipped"])
        self.assertNotIn("cost", pm.CLOSURE_RANGE_KEYS)

    def test_v1_file_is_migrated_not_corrupted_on_closure_record(self):
        # RULING B: record_closure_sample is a write path — a stale v1
        # calibration file must be migrated before a sample is appended, or
        # the sample lands in a "closure" structure v1 doesn't have.
        self._sprint_with_stories([3.0, 4.0], 9.0,
                                  {"man_hours_low": 8.0, "man_hours_high": 9.0},
                                  story_estimates=[3.0, 4.0])
        p = pm.calibration_path(self.root)
        with open(p, "w") as f:
            f.write("version: 1\nratio: 1.3\n")
        with redirect_stderr(io.StringIO()):    # migration announces its steps on stderr
            pm.record_closure_sample(self.root, "sprint", "E001", "S01")
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(cal["version"], pm.CALIBRATION_SCHEMA_VERSION)
        self.assertTrue(os.path.exists(p + ".v1"))
        self.assertEqual(len(pm._component_samples(cal, "closure", "sprint", "man_hours")), 1)

    def test_a_stored_zero_closure_sample_is_ignored_on_read(self):
        """A file written before the write-side guard existed still holds zeros.

        A migration only repairs files someone remembers to migrate. The read
        side is what every estimate goes through, so it is where the rule has
        to hold for a file that already exists.
        """
        _, cal = pm.load_calibration(self.root)
        cal.setdefault("closure", {})["sprint"] = {
            "tokens_k": {"samples": [3.7378, 0.0, 132.8062, 48.2812]},
        }
        # 0.0 must not be averaged in, and must not count toward MIN_SAMPLES.
        got = pm.active_closure_ratio(cal, "sprint", "tokens_k")
        self.assertIsNotNone(got)
        self.assertAlmostEqual(
            got, pm.weighted_ratio([3.7378, 132.8062, 48.2812]), places=6)

    def test_zeros_do_not_count_toward_the_activation_threshold(self):
        _, cal = pm.load_calibration(self.root)
        cal.setdefault("closure", {})["sprint"] = {
            "man_hours": {"samples": [0.0, 0.0, 0.0, 1.5]},
        }
        # Three zeros plus one real sample is one sample, not four.
        self.assertIsNone(pm.active_closure_ratio(cal, "sprint", "man_hours"))

    def test_malformed_samples_are_handled_the_same_way_by_count_and_average(self):
        """bool subclasses int; a numeric string is a number everywhere else in
        this file. Whatever the filter decides, len() and the average must agree."""
        _, cal = pm.load_calibration(self.root)
        cal.setdefault("closure", {})["sprint"] = {
            "man_hours": {"samples": [True, "2.0", 3.0]},
        }
        got = pm.active_closure_ratio(cal, "sprint", "man_hours")
        # True is not a number; "2.0" is. Two real samples -> below MIN_SAMPLES.
        self.assertIsNone(got)


class TestClosureComposedWithOrchestration(TestLayoutResolution):
    """C1: the closure and orchestration components COMPOSED, which no test did.

    Each component was correct alone. Together they were not: since the
    orchestration band joined the roll-up, `pmid - Σ children estimate` is the
    closure band PLUS the orchestration band, while the residual it divides
    (`parent actual - Σ children actual`) is closure-only — orchestration lives
    in its own block. Every test of closure ran with the orchestration
    component inactive (fraction 0, band contributing nothing), so the extra
    term was always zero and the defect was invisible across 648 green tests.

    The numbers here are the reviewer's, measured on the shipped code: children
    summing to 20, an ACTIVE orchestration fraction of 0.5, a true closure
    overhead of 5. The sample must be 1.4286; the pre-fix code recorded 0.3704.
    """

    CHILD = 10.0          # each of two children, estimated and actualed at 10
    TRUE_CLOSURE = 5.0    # the closing level's own closure-phase spend
    ORCH_FRACTION = 0.5

    def run_main(self, argv):
        buf, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(err):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        self.assertEqual(code, 0, buf.getvalue() + err.getvalue())
        return buf.getvalue()

    def _write(self, path, mapping):
        y = pm._yaml()
        with open(path, "w") as f:
            y.dump(mapping, f)

    def _children(self, skey="S01", n=2):
        sd = os.path.join(self.root, "active", "epic-001",
                          "sprint-" + skey.lstrip("S").zfill(2))
        os.makedirs(sd, exist_ok=True)
        for f in os.listdir(sd):
            if f.endswith(".yaml") and f != "sprint.yaml":
                os.remove(os.path.join(sd, f))
        for i in range(1, n + 1):
            self._write(os.path.join(sd, f"E001-{skey}-{i:03d}.yaml"),
                        {"key": f"E001-{skey}-{i:03d}", "epic": "E001", "sprint": skey,
                         "status": "done", "estimate": {"man_hours": self.CHILD},
                         "actual": {"man_hours": self.CHILD}})
        self._write(os.path.join(sd, "sprint.yaml"),
                    {"key": skey, "epic": "E001", "status": "in-progress"})

    def _seed(self, orchestration=None, closure=None):
        with pm.calibration_lock(self.root):
            y, cal = pm.load_calibration(self.root)
            if orchestration is not None:
                cal["orchestration"]["sprint"]["man_hours"] = {"samples": [orchestration] * 3}
            if closure is not None:
                cal["closure"]["sprint"]["man_hours"] = {"samples": [closure] * 3}
            # an ongoing project's file always carries this after its first write;
            # without it the next set-actual would quarantine the seed as pre-rework
            cal[pm.CALIBRATION_METRICS_MARKER] = pm._now_iso()
            pm.save_calibration(y, cal, self.root)

    def _rollup_mid(self, skey="S01"):
        self.run_main(["estimate-rollup", "--state-root", self.root,
                       "--epic", "E001", "--sprint", skey])
        _, node = pm.load_node(pm.sprint_file(self.root, "E001", skey))
        est = node["estimate"]
        return (float(est["man_hours_low"]) + float(est["man_hours_high"])) / 2.0

    def test_active_orchestration_band_is_not_counted_as_closure_overhead(self):
        self._children()
        self._seed(orchestration=self.ORCH_FRACTION)
        mid = self._rollup_mid()
        # 20 x (1 + 1.0x0.10 + 0.5x0.8) = 30 ... 20 x (1 + 1.0x0.25 + 0.5x1.2) = 37
        self.assertAlmostEqual(mid, 33.5, places=4)
        _, node = pm.load_node(pm.sprint_file(self.root, "E001", "S01"))
        self.assertAlmostEqual(
            float(node["estimate"]["orchestration_ratios"]["man_hours"]), 0.5, places=4)

        parent_actual = 2 * self.CHILD + self.TRUE_CLOSURE      # 25
        self.run_main(["set-actual", "--state-root", self.root, "--node", "sprint",
                       "--epic", "E001", "--sprint", "S01",
                       "--man-hours", str(parent_actual)])
        _, cal = pm.load_calibration(self.root)
        samples = pm._component_samples(cal, "closure", "sprint", "man_hours")
        self.assertEqual(len(samples), 1)
        # expected closure overhead = 33.5 - 20 - 20x0.5x1.0 = 3.5  ->  5 / 3.5
        self.assertAlmostEqual(float(samples[0]), 1.4286, places=4)
        # the pre-fix denominator (33.5 - 20 = 13.5) gave 5/13.5 = 0.3704
        self.assertNotAlmostEqual(float(samples[0]), 0.3704, places=3)

    def test_learned_closure_ratio_reconciles_children_plus_closure_plus_orchestration(self):
        """Design §6.1's central claim: the roll-up IS Σ children + closure +
        orchestration. With both components active at their observed values the
        midpoint must land on 20 + 5 + 10 = 35 exactly."""
        self._children()
        self._seed(orchestration=self.ORCH_FRACTION, closure=1.4286)
        mid = self._rollup_mid()
        expected = (2 * self.CHILD) + self.TRUE_CLOSURE + (2 * self.CHILD * self.ORCH_FRACTION)
        self.assertAlmostEqual(mid, expected, places=2)

    def test_sample_is_stable_once_the_ratio_is_active(self):
        """A correct denominator makes the loop a fixed point: re-observing the
        same 5.0 of overhead against an estimate built with ratio 1.4286
        reproduces 1.4286. With the orchestration band left in the denominator
        it did not — it shrank on every generation."""
        self._children()
        self._seed(orchestration=self.ORCH_FRACTION, closure=1.4286)
        self._rollup_mid()
        self.run_main(["set-actual", "--state-root", self.root, "--node", "sprint",
                       "--epic", "E001", "--sprint", "S01",
                       "--man-hours", str(2 * self.CHILD + self.TRUE_CLOSURE)])
        _, cal = pm.load_calibration(self.root)
        samples = pm._component_samples(cal, "closure", "sprint", "man_hours")
        self.assertAlmostEqual(float(samples[-1]), 1.4286, places=3)

    def test_inactive_orchestration_leaves_the_denominator_untouched(self):
        """The guard must be a no-op when the component is cold-start, or it
        would silently change every existing closure sample."""
        self._children()
        self._seed()
        mid = self._rollup_mid()
        self.assertAlmostEqual(mid, 20 * 1.175, places=4)     # closure band only
        self.run_main(["set-actual", "--state-root", self.root, "--node", "sprint",
                       "--epic", "E001", "--sprint", "S01",
                       "--man-hours", str(2 * self.CHILD + self.TRUE_CLOSURE)])
        _, cal = pm.load_calibration(self.root)
        samples = pm._component_samples(cal, "closure", "sprint", "man_hours")
        self.assertAlmostEqual(float(samples[0]), round(5.0 / (20 * 0.175), 4), places=4)

    def test_orch_mid_tracks_the_spread_it_is_derived_from(self):
        self.assertAlmostEqual(pm.ORCH_MID,
                               (pm.ORCH_SPREAD[0] + pm.ORCH_SPREAD[1]) / 2.0)


class TestSetActualCalibrates(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _estimated_story(self):
        p = pm.story_file(self.root, "E001-S01-003")
        with open(p, "w") as f:
            f.write("key: 'E001-S01-003'\nepic: 'E001'\nsprint: 'S01'\n"
                    "status: review\nclassification: complex\n"
                    "completion_evidence:\n  fix_iterations: 0\n"
                    "estimate:\n  man_hours: 6\n  elapsed_hours: 1.5\n"
                    "  tokens_k: 320\n  cost: 4.80\n  fix_factor: 1.25\n"
                    "  scope_ratio: 1.0\n")

    def test_actual_write_emits_a_sample(self):
        self._estimated_story()
        code, out = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "story",
             "--story", "E001-S01-003", "--elapsed-hours", "1.8",
             "--man-hours", "7", "--tokens-input", "355", "--model", "claude-sonnet-5"])
        self.assertEqual(code, 0, out)
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(len(pm._component_samples(cal, "scope", "complex", "man_hours")), 1)

    def test_no_calibrate_suppresses_the_sample(self):
        self._estimated_story()
        code, out = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "story",
             "--story", "E001-S01-003", "--man-hours", "7", "--no-calibrate"])
        self.assertEqual(code, 0, out)
        self.assertFalse(os.path.exists(pm.calibration_path(self.root)))

    def test_story_without_estimate_writes_actual_and_no_sample(self):
        code, out = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "story",
             "--story", "E001-S01-003", "--man-hours", "7"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(node["actual"]["man_hours"], 7)

    def test_calibration_failure_does_not_fail_the_actual_write(self):
        self._estimated_story()
        # make the calibration path unwritable by putting a directory there
        os.makedirs(pm.calibration_path(self.root))
        out_buf, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out_buf), redirect_stderr(err):
                code = pm.main(
                    ["set-actual", "--state-root", self.root, "--node", "story",
                     "--story", "E001-S01-003", "--man-hours", "7"])
        except SystemExit as e:
            code = e.code
        self.assertEqual(code, 0, out_buf.getvalue())          # actuals are primary
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(node["actual"]["man_hours"], 7)
        self.assertIn("actual written, but calibration sample failed", err.getvalue())

    def test_claude_runtime_still_rejects_na(self):
        self._estimated_story()
        code, _ = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "story",
             "--story", "E001-S01-003", "--tokens-na", "--runtime", "claude"])
        self.assertEqual(code, 2)

    def test_estimate_story_tokens_k_produces_a_real_scope_sample(self):
        """RULING (Task 10 fix round 1): `_estimated_story` above hand-writes
        estimate.tokens_k as a bare int — the same blind spot `_child_estimate_value`
        had before Task 10 fixed it, and it can only ever confirm the shape its
        author had in mind. `estimate-story` actually writes tokens_k as a
        `tokens_block` MAPPING (Tasks 6/7); `derive_story_sample` read it with
        `_num_or_none(est.get("tokens_k"))` directly, which returns None for a
        mapping, so the tokens_k scope component silently received zero samples
        in production. This drives the real CLI end to end — estimate-story then
        set-actual — the same style Task 10's own roll-up tests used to catch the
        first instance, and confirms a sample with the expected magnitude, not
        just a nonzero count."""
        code, out = self.run_main(["estimate-story", "--state-root", self.root,
                                   "--story", "E001-S01-003", "--classification", "standard",
                                   "--model", "claude-opus-5"])
        self.assertEqual(code, 0, out)
        code, out = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "story",
             "--story", "E001-S01-003", "--tokens-input", "20", "--tokens-output", "8",
             "--tokens-cache-write", "30", "--tokens-cache-read", "50",
             "--model", "claude-opus-5", "--runtime", "claude"])
        self.assertEqual(code, 0, out)
        _, cal = pm.load_calibration(self.root)
        samples = pm._component_samples(cal, "scope", "standard", "tokens_k")
        self.assertEqual(len(samples), 1, cal)
        # Both sides are FRESH (input + output + cache_write), never the total.
        # estimate fresh 88 (band mid 70 x cold-start ratio 1.0 x fix 1.25);
        # actual fresh 20+8+30 = 58 -- the 50 cache_read is excluded, because it
        # measures corpus x agent count rather than the size of this story.
        # No completion_evidence -> provenance "backout":
        #   sample = actual_fresh x applied(1.0) / estimate_fresh = 58/88
        self.assertAlmostEqual(float(samples[0]), 58.0 / 88.0, places=4)
        self.assertLess(float(samples[0]), 108.0 / 88.0,
                        "the old total-based basis is what this replaced")


class TestEstimateStory(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_cold_start_uses_band_midpoint_times_fix_prior(self):
        code, out = self.run_main(
            ["estimate-story", "--state-root", self.root, "--story", "E001-S01-003",
             "--classification", "complex"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        est = node["estimate"]
        mid = (pm.BASE_BANDS["complex"]["man_hours"][0] +
               pm.BASE_BANDS["complex"]["man_hours"][1]) / 2
        self.assertAlmostEqual(float(est["man_hours"]),
                               round(mid * 1.0 * pm.COLD_START_FIX_FACTOR, 2))
        self.assertAlmostEqual(float(est["fix_factor"]), pm.COLD_START_FIX_FACTOR)
        # per-metric, not a single scalar: the sample derivation divides the
        # applied ratio back out and cannot reconstruct four from one
        for m in ("man_hours", "hitl_hours", "elapsed_hours", "tokens_k"):
            self.assertAlmostEqual(float(est["scope_ratios"][m]),
                                   pm.COLD_START_SCOPE_RATIO)
        # cost is derived from tokens x rates now, never scope-calibrated —
        # it must not appear among the applied ratios at all
        self.assertNotIn("cost", est["scope_ratios"])
        self.assertNotIn("scope_ratio", est)

    def test_calibrated_ratio_is_applied_once_active(self):
        y, cal = pm.load_calibration(self.root)
        cal["scope"]["complex"] = {"man_hours": {"samples": [1.5, 1.5, 1.5]}}
        pm.save_calibration(y, cal, self.root)
        self.run_main(["estimate-story", "--state-root", self.root,
                       "--story", "E001-S01-003", "--classification", "complex"])
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        ratios = node["estimate"]["scope_ratios"]
        self.assertAlmostEqual(float(ratios["man_hours"]), 1.5)
        # only man_hours had samples — the other three stay cold-start, which is
        # exactly why one recorded scalar cannot stand in for all four
        self.assertAlmostEqual(float(ratios["tokens_k"]), pm.COLD_START_SCOPE_RATIO)

    def test_unknown_story_exits_3(self):
        code, _ = self.run_main(
            ["estimate-story", "--state-root", self.root, "--story", "E001-S01-999",
             "--classification", "simple"])
        self.assertEqual(code, 3)

    def test_classification_is_written_to_the_node(self):
        self.run_main(["estimate-story", "--state-root", self.root,
                       "--story", "E001-S01-003", "--classification", "simple"])
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(node["classification"], "simple")


class TestEstimateTokensAndCost(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_split_preserves_the_total_exactly(self):
        got = pm.split_tokens(1160, pm.COLD_START_TOKEN_MIX)
        self.assertEqual(sum(got[c] for c in pm.TOKEN_CLASSES), 1160)
        self.assertEqual(got["input"], 174)
        self.assertEqual(got["cache_read"], 580)

    def test_split_absorbs_rounding_into_the_largest_class(self):
        got = pm.split_tokens(101, {"input": 0.33, "output": 0.33,
                                    "cache_write": 0.33, "cache_read": 0.01})
        self.assertEqual(sum(got[c] for c in pm.TOKEN_CLASSES), 101)

    def test_estimate_story_derives_cost_from_the_split(self):
        code, out = self.run_main(["estimate-story", "--state-root", self.root,
                                   "--story", "E001-S01-003", "--classification", "standard",
                                   "--model", "claude-opus-5"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        est = node["estimate"]
        tk = est["tokens_k"]
        # standard band 40-100, midpoint 70, x scope 1.0 x fix 1.25 = 88 FRESH tokens.
        # The band is fresh-scale (see FRESH_TOKEN_CLASSES), so cache_read is projected
        # from the mix on top rather than carved out of the band: under the cold-start
        # mix the fresh share is 0.15+0.05+0.30 = 0.50 and cache_read is 0.50, so
        # cache_read = 88 x (0.50/0.50) = 88 and the total is 176. The total exceeding
        # the band is the point -- it used to equal it, which is what put a
        # cache-inclusive actual and a fresh band on bases ~1000x apart.
        self.assertEqual(sum(int(tk[c]) for c in pm.FRESH_TOKEN_CLASSES), 88)
        self.assertEqual(int(tk["total"]), 176)
        self.assertEqual(sum(int(tk[c]) for c in pm.TOKEN_CLASSES), 176)
        self.assertAlmostEqual(float(est["cost"]),
                               pm.cost_from_tokens(tk, "claude-opus-5"), places=2)

    def _set_estimate_rejected(self, *extra):
        """Run set-estimate addressing the sprint the way it actually resolves
        kind — via node_args (--epic/--sprint), never --node (that flag
        belongs to set-actual/verify, not set-estimate). Captures stderr so
        the assertion can tell "our rejection fired" apart from "argparse
        choked on an unrecognized flag" — both exit 2, and only the message
        text distinguishes them. This is the same class of --node mismatch
        caught in Task 4; TestEstimateTokensAndCost.test_cost_low_flag_is_rejected
        had it too until this fix."""
        err = io.StringIO()
        try:
            with redirect_stderr(err):
                code = pm.main(["set-estimate", "--state-root", self.root,
                                "--epic", "E001", "--sprint", "S01"] + list(extra))
        except SystemExit as e:
            code = e.code
        return code, err.getvalue()

    def test_cost_low_flag_is_rejected(self):
        code, err = self._set_estimate_rejected("--cost-low", "9.00")
        self.assertEqual(code, 2, err)
        self.assertIn("cost is derived from tokens x rates", err)
        self.assertNotIn("unrecognized arguments", err)

    def test_cost_high_flag_is_rejected(self):
        code, err = self._set_estimate_rejected("--cost-high", "9.00")
        self.assertEqual(code, 2, err)
        self.assertIn("cost is derived from tokens x rates", err)
        self.assertNotIn("unrecognized arguments", err)

    def test_cost_flag_is_rejected_on_set_estimate(self):
        # --cost is the story-form alias (see build_parser); exercised on the
        # sprint node too since set-estimate declares it unconditionally, not
        # only for --story.
        code, err = self._set_estimate_rejected("--cost", "9.00")
        self.assertEqual(code, 2, err)
        self.assertIn("cost is derived from tokens x rates", err)
        self.assertNotIn("unrecognized arguments", err)

    def test_observed_mix_falls_back_below_three_samples(self):
        cal = pm.new_calibration()
        self.assertEqual(pm.observed_mix(cal), pm.COLD_START_TOKEN_MIX)

    def test_observed_mix_used_at_three_samples(self):
        cal = pm.new_calibration()
        cal["token_mix"] = {"samples": [
            {"input": 0.5, "output": 0.1, "cache_write": 0.2, "cache_read": 0.2},
            {"input": 0.5, "output": 0.1, "cache_write": 0.2, "cache_read": 0.2},
            {"input": 0.5, "output": 0.1, "cache_write": 0.2, "cache_read": 0.2},
        ]}
        self.assertAlmostEqual(pm.observed_mix(cal)["input"], 0.5, places=3)

    def test_observed_mix_skips_a_non_mapping_sample(self):
        # A stray non-mapping entry -- hand-edit of the committed, shared
        # pm-calibration.yaml, a bad merge, partial corruption -- must not
        # crash observed_mix (and therefore estimate-story) with an
        # AttributeError from calling .get() on something that isn't a
        # mapping. It falls back to cold-start like every other malformed
        # shape here, same as a missing key or a non-numeric value would.
        cal = pm.new_calibration()
        cal["token_mix"] = {"samples": [
            "not-a-mapping",
            {"input": 0.5, "output": 0.1, "cache_write": 0.2, "cache_read": 0.2},
            {"input": 0.5, "output": 0.1, "cache_write": 0.2, "cache_read": 0.2},
        ]}
        # only 2 real mappings present (below MIN_SAMPLES=3 once the stray
        # scalar is excluded) -> cold-start, not a crash and not a mix
        # computed from garbage.
        self.assertEqual(pm.observed_mix(cal), pm.COLD_START_TOKEN_MIX)

    def test_estimate_story_token_rates_override_changes_the_cost(self):
        base_code, base_out = self.run_main(
            ["estimate-story", "--state-root", self.root, "--story", "E001-S01-003",
             "--classification", "standard", "--model", "claude-opus-5"])
        self.assertEqual(base_code, 0, base_out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        base_cost = float(node["estimate"]["cost"])

        override = '{"claude-opus-5": {"input": 50.0, "output": 250.0, ' \
                    '"cache_write": 62.5, "cache_read": 5.0}}'
        code, out = self.run_main(
            ["estimate-story", "--state-root", self.root, "--story", "E001-S01-003",
             "--classification", "standard", "--model", "claude-opus-5",
             "--token-rates", override])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        overridden_cost = float(node["estimate"]["cost"])
        # rates 10x'd -> cost must actually move, proving --token-rates
        # reaches cost_from_tokens rather than being parsed and dropped
        # (the exact defect class Task 3 hit)
        self.assertAlmostEqual(overridden_cost, base_cost * 10, places=1)
        self.assertGreater(overridden_cost, base_cost)

    def test_estimate_story_unknown_model_exits_nonzero(self):
        code, out = self.run_main(
            ["estimate-story", "--state-root", self.root, "--story", "E001-S01-003",
             "--classification", "standard", "--model", "not-a-real-model"])
        self.assertEqual(code, 2, out)


class TestEstimateRollup(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _story_estimates(self, values):
        sd = os.path.join(self.root, "active", "epic-001", "sprint-01")
        for f in os.listdir(sd):
            if f.endswith(".yaml") and f != "sprint.yaml":
                os.remove(os.path.join(sd, f))
        for i, v in enumerate(values, start=1):
            with open(os.path.join(sd, f"E001-S01-{i:03d}.yaml"), "w") as f:
                f.write(f"key: 'E001-S01-{i:03d}'\nepic: 'E001'\nsprint: 'S01'\n"
                        f"estimate:\n  man_hours: {v}\n  elapsed_hours: 1\n"
                        f"  tokens_k: 10\n  cost: 0.5\n")

    def test_sprint_rollup_sums_children_plus_closure(self):
        self._story_estimates([4, 6])
        code, out = self.run_main(
            ["estimate-rollup", "--state-root", self.root, "--epic", "E001",
             "--sprint", "S01"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.sprint_file(self.root, "E001", "S01"))
        est = node["estimate"]
        self.assertGreaterEqual(float(est["man_hours_high"]), 10.0)
        self.assertLessEqual(float(est["man_hours_low"]), float(est["man_hours_high"]))

    def test_rollup_writes_range_form_not_single_values(self):
        self._story_estimates([4, 6])
        self.run_main(["estimate-rollup", "--state-root", self.root,
                       "--epic", "E001", "--sprint", "S01"])
        _, node = pm.load_node(pm.sprint_file(self.root, "E001", "S01"))
        self.assertIn("man_hours_low", node["estimate"])
        self.assertNotIn("man_hours", node["estimate"])

    def test_unknown_epic_exits_3(self):
        code, _ = self.run_main(
            ["estimate-rollup", "--state-root", self.root, "--epic", "E999"])
        self.assertEqual(code, 3)

    def test_epic_rollup_sums_sprints(self):
        self._story_estimates([4, 6])
        self.run_main(["estimate-rollup", "--state-root", self.root,
                       "--epic", "E001", "--sprint", "S01"])
        code, out = self.run_main(
            ["estimate-rollup", "--state-root", self.root, "--epic", "E001"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.epic_file(self.root, "E001"))
        self.assertIn("man_hours_low", node["estimate"])

    def test_epic_missed_by_the_pre_check_exits_3_and_writes_nothing(self):
        # Final review M1. find_epic_dir scans active -> planned -> archived, so a move-epic
        # the other way can land mid-scan: the pre-check reads None while the epic exists.
        # That fell through to the body WITHOUT the epic lock; the body re-resolved the moved
        # epic, reached save_node, and the write guard raised a RuntimeError traceback. The
        # pre-check's answer must be final: exit 3, no traceback, nothing written.
        self._story_estimates([4, 6])
        code, out = self.run_main(["estimate-rollup", "--state-root", self.root,
                                   "--epic", "E001", "--sprint", "S01"])
        self.assertEqual(code, 0, out)
        real_epic_file, calls = pm.epic_file, []
        self.assertIsNotNone(real_epic_file(self.root, "E001"))       # the epic does exist
        lock = pm.epic_lock_path(self.root, "E001")
        lock_before = os.path.exists(lock)
        before = _tree_snapshot(self.root)

        def pre_check_misses(state_root, epic):
            calls.append(epic)
            return None if len(calls) == 1 else real_epic_file(state_root, epic)

        err = io.StringIO()
        with mock.patch.object(pm, "epic_file", pre_check_misses):
            try:
                with redirect_stdout(io.StringIO()), redirect_stderr(err):
                    code = pm.main(["estimate-rollup", "--state-root", self.root,
                                    "--epic", "E001"])
            except SystemExit as e:
                code = e.code
            except Exception as e:                      # what the CLI shows as a traceback
                self.fail(f"estimate-rollup raised {type(e).__name__}: {e}")
        self.assertEqual(code, 3, err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())
        self.assertEqual(calls, ["E001"], "only the pre-check may resolve the epic")
        self.assertEqual(_tree_snapshot(self.root), before)
        self.assertEqual(os.path.exists(lock), lock_before, "no lock file for a missed epic")


class TestRollupOrchestrationBand(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _story_estimate(self):
        self.run_main(["estimate-story", "--state-root", self.root,
                       "--story", "E001-S01-003", "--classification", "standard",
                       "--model", "claude-opus-5"])

    def test_warns_and_omits_band_while_unseeded(self):
        self._story_estimate()
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, out = self.run_main(["estimate-rollup", "--state-root", self.root,
                                       "--epic", "E001", "--sprint", "S01"])
        self.assertEqual(code, 0, out)
        self.assertIn("orchestration is unestimated", buf.getvalue())
        _, node = pm.load_node(pm.sprint_file(self.root, "E001", "S01"))
        self.assertEqual(node["estimate"]["orchestration_ratios"]["tokens_k"], 0)

    def test_band_applied_once_active(self):
        self._story_estimate()
        with pm.calibration_lock(self.root):
            y, cal = pm.load_calibration(self.root)
            for m in ("man_hours", "hitl_hours", "elapsed_hours", "tokens_k"):
                cal["orchestration"]["sprint"][m] = {"samples": [2.0, 2.0, 2.0]}
            pm.save_calibration(y, cal, self.root)
        code, out = self.run_main(["estimate-rollup", "--state-root", self.root,
                                   "--epic", "E001", "--sprint", "S01"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.sprint_file(self.root, "E001", "S01"))
        est = node["estimate"]
        self.assertAlmostEqual(float(est["orchestration_ratios"]["tokens_k"]), 2.0, places=2)
        # story total 176 (88 fresh + 88 projected cache_read, see
        # test_estimate_story_derives_cost_from_the_split) x
        # (1 + closure 0.10 + orchestration 2.0*0.8) = 176 * 2.70 = 475.2
        self.assertEqual(int(est["tokens_k_min"]), 475)

    def test_rollup_derives_cost_from_rolled_up_tokens(self):
        """cost is no longer banded independently (Task 10): it must be priced
        from the ALREADY-BANDED tokens_k_min/max, not from its own residual."""
        self._story_estimate()
        with redirect_stderr(io.StringIO()):    # unseeded orchestration warns; not under test here
            code, out = self.run_main(["estimate-rollup", "--state-root", self.root,
                                       "--epic", "E001", "--sprint", "S01"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.sprint_file(self.root, "E001", "S01"))
        est = node["estimate"]
        _, cal = pm.load_calibration(self.root)
        mix = pm.observed_mix(cal)
        expect_low = pm.cost_from_tokens(pm.split_tokens(float(est["tokens_k_min"]), mix),
                                         "claude-opus-5")
        expect_high = pm.cost_from_tokens(pm.split_tokens(float(est["tokens_k_max"]), mix),
                                          "claude-opus-5")
        self.assertAlmostEqual(float(est["cost_low"]), expect_low, places=2)
        self.assertAlmostEqual(float(est["cost_high"]), expect_high, places=2)
        self.assertEqual(est["model"], "claude-opus-5")

    def test_model_flag_selects_rate_card(self):
        self._story_estimate()
        with redirect_stderr(io.StringIO()):    # unseeded orchestration warns; not under test here
            code, out = self.run_main(["estimate-rollup", "--state-root", self.root,
                                       "--epic", "E001", "--sprint", "S01",
                                       "--model", "claude-haiku-4-5"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.sprint_file(self.root, "E001", "S01"))
        est = node["estimate"]
        self.assertEqual(est["model"], "claude-haiku-4-5")
        _, cal = pm.load_calibration(self.root)
        mix = pm.observed_mix(cal)
        expect_low = pm.cost_from_tokens(pm.split_tokens(float(est["tokens_k_min"]), mix),
                                         "claude-haiku-4-5")
        self.assertAlmostEqual(float(est["cost_low"]), expect_low, places=2)

    def test_partial_seed_still_warns_and_names_only_inactive_metrics(self):
        """RULING (Task 10 fix round 1): `not any(orch_applied.values())` only
        fires when EVERY metric is inactive. Orchestration calibrates per
        metric, and a metric is sampled only when every child carries a numeric
        actual for it, so a mixed runtime can activate man_hours while
        tokens_k never does — `any()` is then True and the warning would stay
        silent on exactly the metric it exists to flag. Seed only man_hours
        (the other two prior tests seed none or all four) and confirm the
        warning still fires, names the still-inactive metrics, and does not
        name the metric that actually activated."""
        self._story_estimate()
        with pm.calibration_lock(self.root):
            y, cal = pm.load_calibration(self.root)
            cal["orchestration"]["sprint"]["man_hours"] = {"samples": [2.0, 2.0, 2.0]}
            pm.save_calibration(y, cal, self.root)
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, out = self.run_main(["estimate-rollup", "--state-root", self.root,
                                       "--epic", "E001", "--sprint", "S01"])
        self.assertEqual(code, 0, out)
        msg = buf.getvalue()
        self.assertIn("orchestration is unestimated", msg)
        self.assertIn("tokens_k", msg)
        self.assertIn("hitl_hours", msg)
        self.assertIn("elapsed_hours", msg)
        self.assertNotIn("man_hours", msg)
        _, node = pm.load_node(pm.sprint_file(self.root, "E001", "S01"))
        est = node["estimate"]
        self.assertGreater(float(est["orchestration_ratios"]["man_hours"]), 0)
        self.assertEqual(est["orchestration_ratios"]["tokens_k"], 0)

    def test_token_rates_override_moves_the_derived_cost(self):
        """A parsed-but-unapplied flag is a defect class this branch already
        hit once (Task 3's review) — assert the override actually changes the
        priced number, not just that it's accepted without error."""
        self._story_estimate()
        with redirect_stderr(io.StringIO()):    # unseeded orchestration warns; not under test here
            code, out = self.run_main(["estimate-rollup", "--state-root", self.root,
                                       "--epic", "E001", "--sprint", "S01"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.sprint_file(self.root, "E001", "S01"))
        baseline_cost = float(node["estimate"]["cost_low"])

        overrides = json.dumps({"claude-opus-5": {"input": 500.0}})
        with redirect_stderr(io.StringIO()):    # unseeded orchestration warns; not under test here
            code, out = self.run_main(["estimate-rollup", "--state-root", self.root,
                                       "--epic", "E001", "--sprint", "S01",
                                       "--token-rates", overrides])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.sprint_file(self.root, "E001", "S01"))
        overridden_cost = float(node["estimate"]["cost_low"])
        self.assertGreater(overridden_cost, baseline_cost)

    def test_unknown_model_exits_2(self):
        self._story_estimate()
        err = io.StringIO()
        with redirect_stderr(err):
            code, out = self.run_main(["estimate-rollup", "--state-root", self.root,
                                       "--epic", "E001", "--sprint", "S01",
                                       "--model", "not-a-real-model"])
        self.assertEqual(code, 2, out)
        self.assertIn("unknown model", err.getvalue().lower())


class TestParallelClosureResidual(TestLayoutResolution):
    """A negative residual must skip THAT METRIC, never the whole sample — and
    wall-clock going negative is the expected topology under parallel execution,
    not a miscount."""

    def _write(self, path, mapping):
        y = pm._yaml()
        with open(path, "w") as f:
            y.dump(mapping, f)

    def _parallel_sprint(self):
        sd = os.path.join(self.root, "active", "epic-001", "sprint-01")
        for f in os.listdir(sd):
            if f.endswith(".yaml") and f != "sprint.yaml":
                os.remove(os.path.join(sd, f))
        for i, (mh, eh) in enumerate([(12.0, 4.0), (12.0, 4.0)], start=1):
            self._write(os.path.join(sd, f"E001-S01-{i:03d}.yaml"),
                        {"key": f"E001-S01-{i:03d}", "epic": "E001", "sprint": "S01",
                         "status": "done",
                         "estimate": {"man_hours": 12.0, "elapsed_hours": 4.0},
                         "actual": {"man_hours": mh, "elapsed_hours": eh}})
        # two stories ran concurrently: sprint wall-clock 3.0 < children's 8.0,
        # while man-hours still add up (26 vs 24 -> 2.0 of closure overhead)
        self._write(os.path.join(sd, "sprint.yaml"),
                    {"key": "S01", "epic": "E001", "status": "done",
                     "estimate": {"man_hours_low": 25.0, "man_hours_high": 29.0,
                                  "elapsed_hours_low": 9.0, "elapsed_hours_high": 11.0},
                     "actual": {"man_hours": 26.0, "elapsed_hours": 3.0}})

    def test_parallel_wall_clock_does_not_discard_the_man_hours_sample(self):
        self._parallel_sprint()
        s, reason = pm.derive_closure_sample(self.root, "sprint", "E001", "S01")
        self.assertIsNotNone(s, reason)
        self.assertAlmostEqual(s["closure_actual"]["man_hours"], 2.0)
        self.assertIn("man_hours", s["ratios"])
        self.assertNotIn("elapsed_hours", s["ratios"])

    def test_negative_wall_clock_is_not_reported_as_a_miscount(self):
        self._parallel_sprint()
        s, _ = pm.derive_closure_sample(self.root, "sprint", "E001", "S01")
        reason = s["skipped"]["elapsed_hours"]
        self.assertIn("parallel", reason.lower())
        self.assertNotIn("miscounted", reason.lower())

    def test_negative_man_hours_residual_still_warns_of_a_miscount(self):
        self._parallel_sprint()
        sd = os.path.join(self.root, "active", "epic-001", "sprint-01")
        self._write(os.path.join(sd, "sprint.yaml"),
                    {"key": "S01", "epic": "E001", "status": "done",
                     "estimate": {"man_hours_low": 25.0, "man_hours_high": 29.0},
                     "actual": {"man_hours": 20.0, "elapsed_hours": 3.0}})
        s, reason = pm.derive_closure_sample(self.root, "sprint", "E001", "S01")
        self.assertIsNone(s)
        self.assertIn("miscounted", reason.lower())

    def test_parallel_sprint_records_the_man_hours_closure_sample(self):
        self._parallel_sprint()
        note = pm.record_closure_sample(self.root, "sprint", "E001", "S01")
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(len(pm._component_samples(cal, "closure", "sprint", "man_hours")), 1)
        self.assertIn("parallel", note.lower())


class TestSampleIdempotency(TestLayoutResolution):
    """A second set-actual on the same node must not append a second sample set.
    --no-calibrate exists, but relying on the caller to remember it is exactly
    the failure mode the mechanization was built to end."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _estimated_story(self):
        p = pm.story_file(self.root, "E001-S01-003")
        with open(p, "w") as f:
            f.write("key: 'E001-S01-003'\nepic: 'E001'\nsprint: 'S01'\n"
                    "status: review\nclassification: complex\n"
                    "completion_evidence:\n  fix_iterations: 0\n"
                    "estimate:\n  man_hours: 6\n  elapsed_hours: 1.5\n"
                    "  tokens_k: 320\n  cost: 4.80\n  fix_factor: 1.25\n"
                    "  scope_ratios:\n    man_hours: 1.0\n    elapsed_hours: 1.0\n"
                    "    tokens_k: 1.0\n    cost: 1.0\n")

    def _set_actual(self):
        return self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "story",
             "--story", "E001-S01-003", "--man-hours", "7"])

    def test_replayed_set_actual_appends_nothing(self):
        self._estimated_story()
        self._set_actual()
        code, out = self._set_actual()
        self.assertEqual(code, 0, out)
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(len(pm._component_samples(cal, "scope", "complex", "man_hours")), 1)
        self.assertEqual(int(cal["fix"]["complex"]["clean"]["samples"]), 1)

    def test_replay_is_reported_not_silent(self):
        self._estimated_story()
        self._set_actual()
        _, out = self._set_actual()
        self.assertIn("replay", out.lower())

    def test_first_write_stamps_the_marker(self):
        self._estimated_story()
        self._set_actual()
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertIn(pm.CALIBRATION_MARKER, node)

    def test_closure_sample_is_idempotent_too(self):
        sd = os.path.join(self.root, "active", "epic-001", "sprint-01")
        y = pm._yaml()
        for f in os.listdir(sd):
            if f.endswith(".yaml") and f != "sprint.yaml":
                os.remove(os.path.join(sd, f))
        for i, v in enumerate([3.0, 4.0], start=1):
            with open(os.path.join(sd, f"E001-S01-{i:03d}.yaml"), "w") as f:
                y.dump({"key": f"E001-S01-{i:03d}", "epic": "E001", "sprint": "S01",
                        "estimate": {"man_hours": v}, "actual": {"man_hours": v}}, f)
        with open(os.path.join(sd, "sprint.yaml"), "w") as f:
            y.dump({"key": "S01", "epic": "E001", "status": "done",
                    "estimate": {"man_hours_low": 8.0, "man_hours_high": 9.0},
                    "actual": {"man_hours": 9.0}}, f)
        pm.record_closure_sample(self.root, "sprint", "E001", "S01")
        note = pm.record_closure_sample(self.root, "sprint", "E001", "S01")
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(len(pm._component_samples(cal, "closure", "sprint", "man_hours")), 1)
        self.assertIn("replay", note.lower())


class TestConcurrentSampling(unittest.TestCase):
    """load->modify->save must run under ONE lock. Locking only the save let
    parallel appends read the same pre-append state and clobber each other —
    silently, at the DEFAULT max_parallel_subagents of 4."""

    N = 12

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.root = os.path.join(self.d, "state")
        self.sd = os.path.join(self.root, "active", "epic-001", "sprint-01")
        os.makedirs(self.sd)
        with open(os.path.join(self.root, "active", "epic-001", "epic.yaml"), "w") as f:
            f.write("key: 'E001'\nstatus: in-progress\n")
        with open(os.path.join(self.sd, "sprint.yaml"), "w") as f:
            f.write("key: 'S01'\nepic: 'E001'\nstatus: in-progress\n")
        for i in range(1, self.N + 1):
            with open(os.path.join(self.sd, f"E001-S01-{i:03d}.yaml"), "w") as f:
                f.write(f"key: 'E001-S01-{i:03d}'\nepic: 'E001'\nsprint: 'S01'\n"
                        f"status: review\nclassification: complex\n"
                        f"completion_evidence:\n  fix_iterations: 0\n"
                        f"estimate:\n  man_hours: 6\n  fix_factor: 1.25\n"
                        f"  scope_ratios:\n    man_hours: 1.0\n")

    def test_concurrent_appends_lose_no_samples(self):
        import subprocess
        procs = [subprocess.Popen(
            [sys.executable, SCRIPT, "set-actual", "--state-root", self.root,
             "--node", "story", "--story", f"E001-S01-{i:03d}", "--man-hours", str(6 + i)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for i in range(1, self.N + 1)]
        for p in procs:
            out, err = p.communicate(timeout=120)
            self.assertEqual(p.returncode, 0, err.decode())
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(len(pm._component_samples(cal, "scope", "complex", "man_hours")),
                         self.N)
        self.assertEqual(int(cal["fix"]["complex"]["clean"]["samples"]), self.N)


class TestConcurrentAdrReservation(unittest.TestCase):
    """adr-reserve's load->modify->save must run under ONE lock (adr_register_lock),
    mirroring TestConcurrentSampling above. Locking only the write would let two
    parallel reservations both read the same pre-write `next` and print the same
    number to two different agents -- the exact collision (0013 x2, 0014 x2) that
    made ADR numbers need a register in the first place."""

    N = 12

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.root = os.path.join(self.d, "state")
        os.makedirs(self.root)

    def test_concurrent_reservations_hand_out_every_number_exactly_once(self):
        import subprocess
        procs = [subprocess.Popen(
            [sys.executable, SCRIPT, "adr-reserve", "--state-root", self.root,
             "--epic", "E001", "--slug", f"slug-{i}"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for i in range(1, self.N + 1)]
        # Collected from each process's OWN stdout -- not read back from the
        # register file -- because the file converging on `next: N+1` only
        # proves N writes happened; it does not prove no two callers were ever
        # HANDED the same number, which is the actual defect being guarded.
        numbers = []
        for p in procs:
            out, err = p.communicate(timeout=120)
            self.assertEqual(p.returncode, 0, err.decode())
            numbers.extend(out.decode().split())
        expected = {f"{n:04d}" for n in range(1, self.N + 1)}
        self.assertEqual(set(numbers), expected,
                         f"duplicate or skipped number across {self.N} concurrent "
                         f"reservations: got {sorted(numbers)}")
        self.assertEqual(len(numbers), self.N, "a process printed more/fewer than one line")


class TestConcurrentAppendIssue(unittest.TestCase):
    """append-issue's load->allocate->modify->save must run under ONE lock
    (issues_lock), mirroring TestConcurrentAdrReservation above. Locking only the
    write would let two parallel appends both read the same pre-write highest
    number and allocate the same key to two different findings -- the same
    collision class ADR numbers hit in production (0013 x2, 0014 x2).

    Real subprocesses, not threads: `_file_lock`'s reentrancy counter (`_ISSUES_LOCK`)
    is per-process state, so threads sharing one process would pass this test
    vacuously even with the lock removed.
    """

    N = 8

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.f = os.path.join(self.d, "issues.yaml")

    def test_concurrent_appends_get_distinct_sequential_keys(self):
        import subprocess
        procs = [subprocess.Popen(
            [sys.executable, SCRIPT, "append-issue", "--file", self.f,
             "--epic", "001", "--title", f"concurrent finding {i}",
             "--source", "qa", "--severity", "Low"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for i in range(1, self.N + 1)]
        # Collected from each process's OWN stdout, same reasoning as the ADR
        # test: the file converging on N items only proves N writes happened,
        # not that no two callers were ever handed the same key.
        printed_keys = []
        for p in procs:
            out, err = p.communicate(timeout=120)
            self.assertEqual(p.returncode, 0, err.decode())
            printed_keys.extend(
                tok for tok in out.decode().split() if tok.startswith("BL-E001-"))
        expected = {f"BL-E001-{n:03d}" for n in range(1, self.N + 1)}
        self.assertEqual(set(printed_keys), expected,
                         f"duplicate or skipped key across {self.N} concurrent "
                         f"appends: got {sorted(printed_keys)}")
        self.assertEqual(len(printed_keys), self.N,
                         "a process printed more/fewer than one allocated key")

        y, data = pm._load(self.f)
        self.assertEqual(len(data["backlog"]), self.N)
        self.assertEqual({item["key"] for item in data["backlog"]}, expected)


class TestConcurrentSetLock(unittest.TestCase):
    """set-lock's read-existing-lock -> compare -> write-claim cycle must run under ONE
    lock (the fourth `_file_lock` family, keyed on the epic node path), mirroring
    TestConcurrentAdrReservation/TestConcurrentAppendIssue above. Without it, N
    sessions racing to claim one epic could all read "no live foreign lock" and all
    write a claim -- the exact mutual-exclusion bug this test guards: two concurrent
    sessions silently overwriting each other's ownership of the same epic.

    Real subprocesses, not threads: `_file_lock`'s reentrancy counter is per-process
    state, so threads sharing one process would pass this test vacuously even with the
    lock removed -- this is the second time that vacuous-test shape has bitten this
    file (see TestConcurrentAppendIssue), so it is called out again here rather than
    assumed obvious.
    """

    N = 8

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.root = os.path.join(self.d, "state")
        epic_dir = os.path.join(self.root, "active", "epic-001")
        os.makedirs(epic_dir)
        with open(os.path.join(epic_dir, "epic.yaml"), "w", encoding="utf-8") as fh:
            fh.write("key: 'E001'\ntitle: 'test'\nstatus: in-progress\n")

    def test_exactly_one_session_claims_the_lock(self):
        import subprocess
        procs = [subprocess.Popen(
            [sys.executable, SCRIPT, "set-lock", "--state-root", self.root,
             "--epic", "E001", "--session-id", f"sess-{i}", "--ttl-minutes", "30"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for i in range(self.N)]
        codes = []
        for p in procs:
            out, err = p.communicate(timeout=120)
            codes.append(p.returncode)
            self.assertIn(p.returncode, (0, 5),
                           f"unexpected exit code {p.returncode}: "
                           f"stdout={out.decode()!r} stderr={err.decode()!r}")

        winners = [i for i, c in enumerate(codes) if c == 0]
        losers = [i for i, c in enumerate(codes) if c == 5]
        self.assertEqual(len(winners), 1,
                          f"expected exactly one winner among {self.N} racers, "
                          f"got exit codes {codes}")
        self.assertEqual(len(losers), self.N - 1,
                          f"every non-winner must exit 5 (locked), got {codes}")

        _, node = pm.load_node(pm.epic_file(self.root, "E001"))
        winner_session = f"sess-{winners[0]}"
        self.assertEqual(node["_lock"]["session_id"], winner_session,
                          "the persisted _lock must name the process that actually won, "
                          "not merely whichever wrote last")


class TestConvergence(TestLayoutResolution):
    """Multi-generation convergence — the property every single-sample test
    misses. Each case drives the real loop (estimate -> actual -> re-estimate)
    against a FIXED ground truth for enough generations that a ratio activates
    and feeds back into the next estimate.

    Pre-fix, the scope loop settled on sqrt(truth x band_mid) and the closure
    loop moved the roll-up AWAY from its own observed total. Both are asserted
    against here directly.
    """

    TRUTH_MAN_HOURS = 24.0                     # stable ground truth, well above
    BAND_MID = 12.0                            # the complex band midpoint (8-16)

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        self.assertEqual(code, 0, buf.getvalue())
        return buf.getvalue()

    # --- scope ------------------------------------------------------------ #
    def _new_story(self, i):
        key = f"E001-S01-{i:03d}"
        with open(os.path.join(self.root, "active", "epic-001", "sprint-01",
                               f"{key}.yaml"), "w") as f:
            f.write(f"key: '{key}'\nepic: 'E001'\nsprint: 'S01'\nstatus: review\n")
        return key

    def _scope_generation(self, i):
        """One full turn of the loop, in the order step-03-dev-loop.md runs it:
        estimate -> fix_iterations -> actual (which samples)."""
        key = self._new_story(i)
        self.run_main(["estimate-story", "--state-root", self.root, "--story", key,
                       "--classification", "complex"])
        _, node = pm.load_node(pm.story_file(self.root, key))
        est = node["estimate"]
        self.run_main(["set-field", "--state-root", self.root, "--story", key,
                       "--field", "completion_evidence.fix_iterations", "--value", "0"])
        self.run_main(["set-actual", "--state-root", self.root, "--node", "story",
                       "--story", key, "--man-hours", str(self.TRUTH_MAN_HOURS)])
        return float(est["man_hours"]) / float(est["fix_factor"])

    def test_scope_estimate_converges_toward_the_ground_truth(self):
        scope_estimates = [self._scope_generation(i) for i in range(1, 13)]
        final = scope_estimates[-1]
        # the scope component (estimate net of the fix reserve) reaches truth
        self.assertAlmostEqual(final, self.TRUTH_MAN_HOURS, delta=0.05 * self.TRUTH_MAN_HOURS)
        # and it moved TOWARD it, not away
        self.assertLess(abs(final - self.TRUTH_MAN_HOURS),
                        abs(scope_estimates[0] - self.TRUTH_MAN_HOURS))

    def test_scope_does_not_settle_on_the_geometric_mean(self):
        # the pre-fix fixed point: sqrt(truth x band_mid) = sqrt(24 x 12) = 16.97
        geometric = (self.TRUTH_MAN_HOURS * self.BAND_MID) ** 0.5
        final = [self._scope_generation(i) for i in range(1, 13)][-1]
        self.assertGreater(abs(final - geometric), 2.0)

    def test_scope_ratio_reaches_truth_over_band_midpoint(self):
        for i in range(1, 13):
            self._scope_generation(i)
        _, cal = pm.load_calibration(self.root)
        ratio = pm.active_scope_ratio(cal, "complex", "man_hours")
        self.assertAlmostEqual(ratio, self.TRUTH_MAN_HOURS / self.BAND_MID, delta=0.05)

    # --- perfect estimate: no drift --------------------------------------- #
    def test_calibrated_component_does_not_drift_on_a_perfect_estimate(self):
        y, cal = pm.load_calibration(self.root)
        cal["scope"]["complex"] = {"man_hours": {"samples": [2.0, 2.0, 2.0]}}
        # This fixture simulates an ONGOING project that already has 3 real
        # calibrated samples — not a legacy import — so it must also carry
        # the migration marker: a real post-Task-11 deployment's file always
        # does after its first write, and without it the very next
        # set-actual below would (correctly, for a genuinely unmigrated
        # file) quarantine this seed as pre-rework data.
        cal[pm.CALIBRATION_METRICS_MARKER] = pm._now_iso()
        pm.save_calibration(y, cal, self.root)
        for i in range(20, 26):
            key = self._new_story(i)
            self.run_main(["estimate-story", "--state-root", self.root, "--story", key,
                           "--classification", "complex"])
            _, node = pm.load_node(pm.story_file(self.root, key))
            est = node["estimate"]
            # the estimate is exactly right: its scope half equals the truth it
            # was built from, and the story consumed no fix reserve
            actual = float(est["man_hours"]) / float(est["fix_factor"])
            self.run_main(["set-field", "--state-root", self.root, "--story", key,
                           "--field", "completion_evidence.fix_iterations", "--value", "0"])
            self.run_main(["set-actual", "--state-root", self.root, "--node", "story",
                           "--story", key, "--man-hours", str(actual)])
            _, cal2 = pm.load_calibration(self.root)
            self.assertAlmostEqual(pm.active_scope_ratio(cal2, "complex", "man_hours"),
                                   2.0, delta=1e-6)

    def test_backout_path_sample_is_neutral_when_actual_equals_estimate(self):
        node = {"key": "E001-S01-003", "classification": "complex",
                "completion_evidence": {"fix_iterations": 2},
                "estimate": {"man_hours": 10.0, "fix_factor": 1.25,
                             "scope_ratios": {"man_hours": 1.4}},
                "actual": {"man_hours": 10.0}}
        s = pm.derive_story_sample(node)
        self.assertAlmostEqual(s["scope_ratios"]["man_hours"], 1.4)

    # --- closure ----------------------------------------------------------- #
    CHILD_ESTIMATE = 10.0
    CHILDREN = 4
    TRUE_CLOSURE_OVERHEAD = 8.0

    def _make_sprint(self, n):
        """A sprint whose 4 stories were each estimated exactly right, plus a
        closure overhead that is the same 8.0 every single time."""
        skey = f"S{n:02d}"
        sd = os.path.join(self.root, "active", "epic-001", f"sprint-{n:02d}")
        os.makedirs(sd, exist_ok=True)
        y = pm._yaml()
        for i in range(1, self.CHILDREN + 1):
            with open(os.path.join(sd, f"E001-{skey}-{i:03d}.yaml"), "w") as f:
                y.dump({"key": f"E001-{skey}-{i:03d}", "epic": "E001", "sprint": skey,
                        "status": "done",
                        "estimate": {"man_hours": self.CHILD_ESTIMATE},
                        "actual": {"man_hours": self.CHILD_ESTIMATE}}, f)
        with open(os.path.join(sd, "sprint.yaml"), "w") as f:
            y.dump({"key": skey, "epic": "E001", "status": "in-progress"}, f)
        return skey

    def _rollup_mid(self, skey):
        self.run_main(["estimate-rollup", "--state-root", self.root,
                       "--epic", "E001", "--sprint", skey])
        _, node = pm.load_node(pm.sprint_file(self.root, "E001", skey))
        est = node["estimate"]
        return (float(est["man_hours_low"]) + float(est["man_hours_high"])) / 2.0

    def _closure_generation(self, n):
        skey = self._make_sprint(n)
        mid = self._rollup_mid(skey)
        total_actual = self.CHILDREN * self.CHILD_ESTIMATE + self.TRUE_CLOSURE_OVERHEAD
        self.run_main(["set-actual", "--state-root", self.root, "--node", "sprint",
                       "--epic", "E001", "--sprint", skey,
                       "--man-hours", str(total_actual)])
        return mid

    def test_learned_closure_rollup_is_closer_to_truth_than_cold_start(self):
        truth = self.CHILDREN * self.CHILD_ESTIMATE + self.TRUE_CLOSURE_OVERHEAD  # 48
        cold_start = self._closure_generation(2)
        for n in range(3, 9):
            self._closure_generation(n)
        learned = self._rollup_mid(self._make_sprint(9))
        self.assertLess(abs(learned - truth), abs(cold_start - truth))
        self.assertAlmostEqual(learned, truth, delta=0.01 * truth)

    def test_closure_ratio_is_stable_across_generations(self):
        # every generation observes the same 8.0 of overhead, so the ratio must
        # stop moving once it is active — not oscillate around a geometric mean
        for n in range(2, 9):
            self._closure_generation(n)
        _, cal = pm.load_calibration(self.root)
        samples = [float(s) for s in
                   pm._component_samples(cal, "closure", "sprint", "man_hours")]
        self.assertGreaterEqual(len(samples), 6)
        for s in samples[3:]:
            self.assertAlmostEqual(s, samples[0], delta=0.01)


class TestEvents(Base):
    """events.jsonl — the append-only transition log that supplies dwell time."""

    def setUp(self):
        super().setUp()
        self.root = os.path.join(self.d, "state")
        d = os.path.join(self.root, "active", "epic-001", "sprint-01")
        os.makedirs(d)
        with open(os.path.join(self.root, "active", "epic-001", "epic.yaml"), "w") as fh:
            fh.write("key: 'E001'\ntitle: 'Foundation'\nstatus: in-progress\n")
        with open(os.path.join(d, "sprint.yaml"), "w") as fh:
            fh.write("key: 'S01'\nepic: 'E001'\nstatus: in-progress\n")
        with open(os.path.join(d, "E001-S01-001.yaml"), "w") as fh:
            fh.write("key: 'E001-S01-001'\nepic: 'E001'\nsprint: 'S01'\nstatus: in-progress\n")

    def read_events(self):
        p = pm.events_path(self.root)
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as fh:
            return [json.loads(l) for l in fh if l.strip()]

    def test_set_status_appends_event_with_from_and_to(self):
        code, _ = self.run_main(["set-status", "--state-root", self.root,
                                 "--story", "E001-S01-001", "--status", "review"])
        self.assertEqual(code, 0)
        evs = self.read_events()
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["event"], "status")
        self.assertEqual(evs[0]["node"], "story")
        self.assertEqual(evs[0]["key"], "E001-S01-001")
        self.assertEqual(evs[0]["from"], "in-progress")
        self.assertEqual(evs[0]["to"], "review")
        self.assertEqual(evs[0]["epic"], "E001")
        self.assertEqual(evs[0]["sprint"], "S01")

    def test_no_events_flag_suppresses(self):
        self.run_main(["set-status", "--state-root", self.root,
                       "--story", "E001-S01-001", "--status", "review", "--no-events"])
        self.assertEqual(self.read_events(), [])

    def test_session_id_recorded_when_given(self):
        self.run_main(["set-status", "--state-root", self.root, "--story", "E001-S01-001",
                       "--status", "review", "--session-id", "sess-abc"])
        self.assertEqual(self.read_events()[0]["session"], "sess-abc")

    def test_session_is_null_by_default(self):
        self.run_main(["set-status", "--state-root", self.root,
                       "--story", "E001-S01-001", "--status", "review"])
        self.assertIsNone(self.read_events()[0]["session"])

    def test_epic_and_sprint_events_carry_right_node_kind(self):
        self.run_main(["set-status", "--state-root", self.root, "--epic", "E001",
                       "--sprint", "S01", "--status", "done"])
        self.run_main(["set-status", "--state-root", self.root, "--epic", "E001",
                       "--status", "done"])
        evs = self.read_events()
        self.assertEqual(evs[0]["node"], "sprint")
        self.assertEqual(evs[0]["key"], "S01")
        self.assertEqual(evs[0]["epic"], "E001")
        self.assertEqual(evs[1]["node"], "epic")
        self.assertEqual(evs[1]["key"], "E001")
        self.assertIsNone(evs[1]["sprint"])

    def test_set_actual_appends_actual_event(self):
        self.run_main(["set-actual", "--state-root", self.root, "--node", "story",
                       "--story", "E001-S01-001", "--elapsed-hours", "2",
                       "--man-hours", "3", "--tokens-input", "10",
                       "--model", "claude-sonnet-5", "--no-calibrate"])
        evs = [e for e in self.read_events() if e["event"] == "actual"]
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["key"], "E001-S01-001")

    def test_append_failure_warns_but_write_succeeds(self):
        # Plant a directory where the log file goes, so open(..., "a") must fail.
        os.makedirs(pm.events_path(self.root))
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, _ = self.run_main(["set-status", "--state-root", self.root,
                                     "--story", "E001-S01-001", "--status", "review"])
        self.assertEqual(code, 0)
        self.assertIn("could not append event", buf.getvalue())
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-001"))
        self.assertEqual(node["status"], "review")

    def test_concurrent_appends_lose_no_lines(self):
        import threading

        def worker(i):
            pm.append_event(self.root, {"event": "status", "n": i})

        ts = [threading.Thread(target=worker, args=(i,)) for i in range(40)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(len(self.read_events()), 40)


class TestDwellAndFlags(Base):
    """Per-status dwell time (exact from events, approximate from updated_at) and
    the fixed stuck thresholds."""

    def test_parse_iso_handles_z_suffix(self):
        dt = pm._parse_iso("2026-08-17T10:00:00Z")
        self.assertEqual(dt.year, 2026)
        self.assertIsNone(pm._parse_iso(None))
        self.assertIsNone(pm._parse_iso("not-a-date"))

    def test_dwell_prefers_events_and_is_exact(self):
        root = os.path.join(self.d, "state")
        os.makedirs(root)
        pm.append_event(root, {"ts": "2026-08-17T06:00:00Z", "event": "status",
                               "node": "story", "key": "E001-S01-001",
                               "from": "in-progress", "to": "review"})
        idx = pm.build_events_index(root)
        node = {"key": "E001-S01-001", "status": "review",
                "updated_at": "2026-08-17T09:00:00Z"}
        now = pm._parse_iso("2026-08-17T10:00:00Z")
        hours, exact = pm.dwell_hours(node, idx, now=now)
        self.assertAlmostEqual(hours, 4.0, places=3)
        self.assertTrue(exact)

    def test_dwell_falls_back_to_updated_at_when_no_events(self):
        node = {"key": "E001-S01-001", "status": "review",
                "updated_at": "2026-08-17T08:00:00Z"}
        now = pm._parse_iso("2026-08-17T10:00:00Z")
        hours, exact = pm.dwell_hours(node, {}, now=now)
        self.assertAlmostEqual(hours, 2.0, places=3)
        self.assertFalse(exact)

    def test_dwell_falls_back_when_latest_event_status_disagrees(self):
        # Hand-edited YAML: state says done, the last event said review.
        root = os.path.join(self.d, "state")
        os.makedirs(root)
        pm.append_event(root, {"ts": "2026-08-17T06:00:00Z", "event": "status",
                               "node": "story", "key": "E001-S01-001",
                               "from": "in-progress", "to": "review"})
        idx = pm.build_events_index(root)
        node = {"key": "E001-S01-001", "status": "done",
                "updated_at": "2026-08-17T09:30:00Z"}
        now = pm._parse_iso("2026-08-17T10:00:00Z")
        hours, exact = pm.dwell_hours(node, idx, now=now)
        self.assertAlmostEqual(hours, 0.5, places=3)
        self.assertFalse(exact)

    def test_dwell_none_when_no_timestamp_at_all(self):
        hours, exact = pm.dwell_hours({"key": "X", "status": "review"}, {})
        self.assertIsNone(hours)
        self.assertFalse(exact)

    def test_index_takes_latest_event_per_key(self):
        root = os.path.join(self.d, "state")
        os.makedirs(root)
        for ts, to in [("2026-08-17T06:00:00Z", "review"),
                       ("2026-08-17T07:00:00Z", "in-progress")]:
            pm.append_event(root, {"ts": ts, "event": "status", "node": "story",
                                   "key": "E001-S01-001", "to": to})
        idx = pm.build_events_index(root)
        self.assertEqual(idx["E001-S01-001"]["to"], "in-progress")

    def test_index_ignores_actual_events_and_bad_lines(self):
        root = os.path.join(self.d, "state")
        os.makedirs(root)
        pm.append_event(root, {"ts": "2026-08-17T06:00:00Z", "event": "status",
                               "node": "story", "key": "K", "to": "review"})
        pm.append_event(root, {"ts": "2026-08-17T07:00:00Z", "event": "actual",
                               "node": "story", "key": "K"})
        with open(pm.events_path(root), "a", encoding="utf-8") as fh:
            fh.write("{ not json\n")
        idx = pm.build_events_index(root)
        self.assertEqual(idx["K"]["to"], "review")

    def test_index_empty_when_log_absent(self):
        self.assertEqual(pm.build_events_index(os.path.join(self.d, "nope")), {})

    def test_flags_fire_at_threshold_per_level(self):
        self.assertEqual(pm.compute_flags("story", "K", "review", 4.5, True)[0]["kind"], "stuck")
        self.assertEqual(pm.compute_flags("story", "K", "review", 3.5, True), [])
        self.assertEqual(pm.compute_flags("story", "K", "in-progress", 5.0, True)[0]["kind"], "stuck")
        self.assertEqual(pm.compute_flags("sprint", "S01", "in-progress", 25.0, True)[0]["kind"], "stuck")
        self.assertEqual(pm.compute_flags("sprint", "S01", "in-progress", 5.0, True), [])
        self.assertEqual(pm.compute_flags("epic", "E001", "in-progress", 80.0, True)[0]["kind"], "stuck")

    def test_ready_for_dev_never_flagged(self):
        self.assertEqual(pm.compute_flags("story", "K", "ready-for-dev", 500.0, True), [])

    def test_done_never_flagged_and_none_dwell_never_flagged(self):
        self.assertEqual(pm.compute_flags("story", "K", "done", 500.0, True), [])
        self.assertEqual(pm.compute_flags("story", "K", "review", None, False), [])

    def test_flag_carries_approximate_marker(self):
        f = pm.compute_flags("story", "K", "review", 9.0, False)[0]
        self.assertFalse(f["exact"])
        self.assertEqual(f["threshold"], 4.0)
        self.assertEqual(f["status"], "review")


class TestProgressModel(Base):
    """The project-wide walk: hierarchy, archived filtering, flags, tolerance."""

    def setUp(self):
        super().setUp()
        self.root = os.path.join(self.d, "state")
        self.mk("active", "epic-001", "E001", "Foundation", "in-progress",
                sprints={"sprint-01": ("S01", "done", [("E001-S01-001", "done"),
                                                       ("E001-S01-002", "done")]),
                         "sprint-02": ("S02", "in-progress", [("E001-S02-001", "review"),
                                                              ("E001-S02-002", "backlog")])})
        self.mk("archived", "epic-002", "E002", "Auth", "done",
                sprints={"sprint-01": ("S01", "done", [("E002-S01-001", "done")])})
        self.mk("planned", "epic-004", "E004", "Telemetry", "backlog", sprints={})

    def mk(self, folder, edir, ekey, title, status, sprints):
        ed = os.path.join(self.root, folder, edir)
        os.makedirs(ed, exist_ok=True)
        with open(os.path.join(ed, "epic.yaml"), "w") as fh:
            fh.write(f"key: '{ekey}'\ntitle: '{title}'\nstatus: {status}\n"
                     f"updated_at: '2026-08-17T09:00:00Z'\n")
        for sdir, (skey, sstatus, stories) in sprints.items():
            sd = os.path.join(ed, sdir)
            os.makedirs(sd, exist_ok=True)
            with open(os.path.join(sd, "sprint.yaml"), "w") as fh:
                fh.write(f"key: '{skey}'\nepic: '{ekey}'\nstatus: {sstatus}\n"
                         f"updated_at: '2026-08-17T09:00:00Z'\n")
            for stkey, ststatus in stories:
                with open(os.path.join(sd, f"{stkey}.yaml"), "w") as fh:
                    fh.write(f"key: '{stkey}'\nepic: '{ekey}'\nsprint: '{skey}'\n"
                             f"status: {ststatus}\nupdated_at: '2026-08-17T09:00:00Z'\n")

    def test_list_all_epics_spans_all_status_folders(self):
        got = pm.list_all_epics(self.root)
        self.assertEqual(got, [("E001", "active"), ("E002", "archived"), ("E004", "planned")])

    def test_archived_omitted_by_default(self):
        m = pm.build_progress_model(self.root)
        keys = [e["key"] for e in m["unplanned_epics"]]
        self.assertIn("E001", keys)
        self.assertIn("E004", keys)
        self.assertNotIn("E002", keys)

    def test_archived_present_with_include_archived(self):
        m = pm.build_progress_model(self.root, include_archived=True)
        self.assertIn("E002", [e["key"] for e in m["unplanned_epics"]])

    def test_totals_count_archived_even_when_hidden(self):
        m = pm.build_progress_model(self.root)
        self.assertEqual(m["totals"]["epics"], {"in-progress": 1, "done": 1, "backlog": 1})
        self.assertEqual(m["totals"]["stories"]["done"], 3)   # 2 in E001 + 1 in archived E002
        self.assertEqual(m["totals"]["stories"]["review"], 1)

    def test_epic_detail_hierarchy(self):
        m = pm.build_progress_model(self.root)
        e = next(x for x in m["unplanned_epics"] if x["key"] == "E001")
        self.assertEqual(e["title"], "Foundation")
        self.assertEqual(e["dir_status"], "active")
        self.assertEqual(e["sprint_count"], 2)
        self.assertEqual(e["story_count"], 4)
        self.assertEqual([s["key"] for s in e["sprints"]], ["S01", "S02"])
        s2 = e["sprints"][1]
        self.assertEqual([st["key"] for st in s2["stories"]],
                         ["E001-S02-001", "E001-S02-002"])

    def test_placement_anomaly_flagged(self):
        p = os.path.join(self.root, "planned", "epic-004", "epic.yaml")
        with open(p, "w") as fh:
            fh.write("key: 'E004'\ntitle: 'Telemetry'\nstatus: done\n")
        m = pm.build_progress_model(self.root)
        self.assertIn("placement", [f["kind"] for f in m["flags"]])

    def test_unparseable_node_is_flagged_not_fatal(self):
        p = os.path.join(self.root, "active", "epic-001", "sprint-02", "E001-S02-001.yaml")
        with open(p, "w") as fh:
            fh.write("key: [unclosed\n")
        m = pm.build_progress_model(self.root)
        self.assertIn("unreadable", [f["kind"] for f in m["flags"]])

    def test_stuck_story_flagged_from_updated_at(self):
        now = pm._parse_iso("2026-08-17T20:00:00Z")   # 11h after the fixture stamp
        m = pm.build_progress_model(self.root, now=now)
        stuck = [f for f in m["flags"] if f["kind"] == "stuck"]
        self.assertIn("E001-S02-001", [f["key"] for f in stuck])      # review, 11h > 4h
        self.assertNotIn("E001-S02-002", [f["key"] for f in stuck])   # backlog, never

    def test_stale_lock_flagged(self):
        p = os.path.join(self.root, "active", "epic-001", "epic.yaml")
        with open(p, "w") as fh:
            fh.write("_lock:\n  session_id: 'sess-1'\n  claimed_at: '2026-08-17T00:00:00Z'\n"
                     "  ttl_minutes: 30\nkey: 'E001'\ntitle: 'Foundation'\n"
                     "status: in-progress\nupdated_at: '2026-08-17T09:00:00Z'\n")
        now = pm._parse_iso("2026-08-17T10:00:00Z")
        m = pm.build_progress_model(self.root, now=now)
        self.assertIn("stale-lock", [f["kind"] for f in m["flags"]])
        e = next(x for x in m["unplanned_epics"] if x["key"] == "E001")
        self.assertTrue(e["lock"]["stale"])

    def test_empty_state_root_yields_empty_model(self):
        empty = os.path.join(self.d, "nothing")
        os.makedirs(empty)
        m = pm.build_progress_model(empty)
        self.assertEqual(m["unplanned_epics"], [])
        self.assertEqual(m["phases"], [])
        self.assertIsNone(m["plan"])


class TestFlagScoping(TestProgressModel):
    """Each node's own `flags` must describe only that node. The aggregate lives at
    model['flags']. Mixing the two made an epic row report 'stuck' whenever any
    descendant story was stuck, and left sprints unable to report their own."""

    def test_epic_own_flags_exclude_descendant_stuck(self):
        now = pm._parse_iso("2026-08-17T20:00:00Z")   # story review 11h > 4h; epic 11h < 72h
        m = pm.build_progress_model(self.root, now=now)
        e = next(x for x in m["unplanned_epics"] if x["key"] == "E001")
        self.assertEqual([f["kind"] for f in e["flags"]], [])
        story = e["sprints"][1]["stories"][0]
        self.assertEqual(story["key"], "E001-S02-001")
        self.assertEqual([f["kind"] for f in story["flags"]], ["stuck"])

    def test_sprint_carries_its_own_flags_key(self):
        now = pm._parse_iso("2026-08-19T09:00:00Z")   # 48h: sprint in-progress > 24h
        m = pm.build_progress_model(self.root, now=now)
        e = next(x for x in m["unplanned_epics"] if x["key"] == "E001")
        s02 = e["sprints"][1]
        self.assertEqual(s02["key"], "S02")
        self.assertIn("flags", s02)
        self.assertEqual([f["kind"] for f in s02["flags"]], ["stuck"])
        s01 = e["sprints"][0]                         # done — never flagged
        self.assertEqual(s01["flags"], [])

    def test_epic_own_flags_still_carry_placement_and_lock(self):
        p = os.path.join(self.root, "planned", "epic-004", "epic.yaml")
        with open(p, "w") as fh:
            fh.write("key: 'E004'\ntitle: 'Telemetry'\nstatus: done\n")
        m = pm.build_progress_model(self.root)
        e = next(x for x in m["unplanned_epics"] if x["key"] == "E004")
        self.assertEqual([f["kind"] for f in e["flags"]], ["placement"])

    def test_model_flags_aggregate_every_level(self):
        now = pm._parse_iso("2026-08-19T09:00:00Z")
        m = pm.build_progress_model(self.root, now=now)
        levels = {f["level"] for f in m["flags"] if f["kind"] == "stuck"}
        self.assertIn("story", levels)
        self.assertIn("sprint", levels)

    def test_unreadable_story_attaches_to_its_sprint(self):
        p = os.path.join(self.root, "active", "epic-001", "sprint-02", "E001-S02-001.yaml")
        with open(p, "w") as fh:
            fh.write("key: [unclosed\n")
        m = pm.build_progress_model(self.root)
        e = next(x for x in m["unplanned_epics"] if x["key"] == "E001")
        s02 = e["sprints"][1]
        self.assertIn("unreadable", [f["kind"] for f in s02["flags"]])
        self.assertIn("unreadable", [f["kind"] for f in m["flags"]])

    def test_tree_does_not_mark_epic_stuck_for_a_stuck_story(self):
        now = pm._parse_iso("2026-08-17T20:00:00Z")
        m = pm.build_progress_model(self.root, now=now)
        lines = pm.render_tree(m).splitlines()
        epic_line = next(l for l in lines if l.strip().startswith("E001 "))
        self.assertNotIn("stuck", epic_line)
        story_line = next(l for l in lines if "E001-S02-001" in l)
        self.assertIn("stuck", story_line)

    def test_tree_has_no_trailing_whitespace(self):
        m = pm.build_progress_model(self.root)
        for line in pm.render_tree(m).splitlines():
            self.assertEqual(line, line.rstrip(), f"trailing whitespace: {line!r}")


class TestPlanJoin(TestProgressModel):
    """Joining plan-output-meta.yaml -> snapshot phases onto the state hierarchy."""

    def write_plan(self, epics_p1=("E001", "E002"), snapshot="plan-2026-08-17-v1.yaml"):
        pd = os.path.join(self.d, "planning")
        os.makedirs(pd, exist_ok=True)
        with open(os.path.join(pd, "plan-output-meta.yaml"), "w") as fh:
            fh.write(f'current_plan: "{snapshot}"\ngenerated: "2026-08-17T08:00:00Z"\n'
                     f"readiness: green\nphase_count: 2\n")
        with open(os.path.join(pd, snapshot), "w") as fh:
            fh.write('generated: "2026-08-17T08:00:00Z"\nreadiness: green\nphases:\n')
            fh.write(f"  - phase: 1\n    parallel: true\n    epics: {list(epics_p1)}\n"
                     f"    dependencies: []\n")
            fh.write("  - phase: 2\n    parallel: false\n    epics: ['E004']\n"
                     "    dependencies: ['E001']\n")
        return os.path.join(pd, "plan-output-meta.yaml")

    def test_load_plan_follows_pointer_to_snapshot(self):
        plan = pm.load_plan(self.write_plan())
        self.assertEqual(plan["meta"]["readiness"], "green")
        self.assertEqual(len(plan["phases"]), 2)
        self.assertEqual(list(plan["phases"][0]["epics"]), ["E001", "E002"])

    def test_load_plan_returns_none_when_missing(self):
        self.assertIsNone(pm.load_plan(os.path.join(self.d, "nope.yaml")))

    def test_load_plan_tolerates_dangling_snapshot(self):
        ptr = self.write_plan(snapshot="does-not-exist.yaml")
        os.remove(os.path.join(os.path.dirname(ptr), "does-not-exist.yaml"))
        buf = io.StringIO()
        with redirect_stderr(buf):
            plan = pm.load_plan(ptr)
        self.assertIsNotNone(plan["meta"])
        self.assertEqual(plan["phases"], [])
        self.assertIn("missing snapshot", buf.getvalue())

    def test_model_groups_epics_into_phases(self):
        plan = pm.load_plan(self.write_plan())
        m = pm.build_progress_model(self.root, plan=plan)
        self.assertEqual(len(m["phases"]), 2)
        self.assertEqual(m["phases"][0]["epic_total"], 2)
        self.assertEqual([e["key"] for e in m["phases"][0]["epics_detail"]], ["E001"])
        self.assertEqual(m["plan"]["readiness"], "green")

    def test_archived_counted_in_denominator_but_not_displayed(self):
        plan = pm.load_plan(self.write_plan(epics_p1=("E001", "E002")))
        m = pm.build_progress_model(self.root, plan=plan)
        ph = m["phases"][0]
        self.assertEqual(ph["epic_total"], 2)
        self.assertEqual(ph["epic_done"], 1)                       # E002 is archived+done
        self.assertEqual([e["key"] for e in ph["epics_detail"]], ["E001"])

    def test_planned_epics_do_not_appear_as_unplanned(self):
        plan = pm.load_plan(self.write_plan())
        m = pm.build_progress_model(self.root, plan=plan)
        self.assertEqual(m["unplanned_epics"], [])   # E001,E002,E004 all named in phases


class TestReport(TestPlanJoin):
    """The report subcommand and its three renderers."""

    def snapshot_tree(self):
        seen = {}
        for base, _, files in os.walk(self.root):
            for f in files:
                p = os.path.join(base, f)
                seen[p] = os.path.getmtime(p)
        return seen

    def test_json_format_round_trips(self):
        code, out = self.run_main(["report", "--state-root", self.root, "--format", "json"])
        self.assertEqual(code, 0)
        m = json.loads(out)
        self.assertIn("totals", m)
        self.assertIn("unplanned_epics", m)

    def test_tree_renders_hierarchy(self):
        code, out = self.run_main(["report", "--state-root", self.root, "--format", "tree"])
        self.assertEqual(code, 0)
        self.assertIn("E001", out)
        self.assertIn("S02", out)
        self.assertIn("E001-S02-001", out)
        self.assertNotIn("E002", out)          # archived, hidden by default

    def test_tree_shows_archived_with_all(self):
        _, out = self.run_main(["report", "--state-root", self.root,
                                "--format", "tree", "--all"])
        self.assertIn("E002", out)

    def test_tree_renders_phases_when_plan_given(self):
        ptr = self.write_plan()
        _, out = self.run_main(["report", "--state-root", self.root, "--plan", ptr,
                                "--format", "tree"])
        self.assertIn("Phase 1", out)
        self.assertIn("readiness", out.lower())

    def test_md_format_emits_tables(self):
        _, out = self.run_main(["report", "--state-root", self.root, "--format", "md"])
        self.assertIn("|", out)
        self.assertIn("generated by", out.lower())

    def test_out_writes_file_and_prints_confirmation(self):
        dest = os.path.join(self.d, "progress-report.md")
        code, out = self.run_main(["report", "--state-root", self.root,
                                   "--format", "md", "--out", dest])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(dest))
        self.assertIn("OK report", out)

    def test_read_only_without_out(self):
        before = self.snapshot_tree()
        self.run_main(["report", "--state-root", self.root, "--format", "tree"])
        self.assertEqual(before, self.snapshot_tree())
        self.assertFalse(os.path.exists(pm.events_path(self.root)))

    def test_empty_tree_renders_without_raising(self):
        empty = os.path.join(self.d, "empty-state")
        os.makedirs(empty)
        code, out = self.run_main(["report", "--state-root", empty, "--format", "tree"])
        self.assertEqual(code, 0)
        self.assertIn("no epics", out.lower())

    def test_stuck_marker_appears_in_tree(self):
        p = os.path.join(self.root, "active", "epic-001", "sprint-02", "E001-S02-001.yaml")
        with open(p, "w") as fh:
            fh.write("key: 'E001-S02-001'\nepic: 'E001'\nsprint: 'S02'\n"
                     "status: review\nupdated_at: '2000-01-01T00:00:00Z'\n")
        _, out = self.run_main(["report", "--state-root", self.root, "--format", "tree"])
        self.assertIn("E001-S02-001", out)
        self.assertIn("stuck", out.lower())

    def test_missing_state_root_exits_3(self):
        with redirect_stderr(io.StringIO()):
            code, _ = self.run_main(["report", "--state-root",
                                     os.path.join(self.d, "absent"), "--format", "tree"])
        self.assertEqual(code, 3)

    def test_bad_format_is_usage_error(self):
        with redirect_stderr(io.StringIO()):
            code, _ = self.run_main(["report", "--state-root", self.root,
                                     "--format", "nope"])
        self.assertEqual(code, 2)


class TestStatusFilter(TestPlanJoin):
    """`--status` selects which state folders are displayed. Denominators must keep
    counting every epic regardless, or a progress bar changes meaning with the view."""

    def test_default_is_planned_and_active(self):
        m = pm.build_progress_model(self.root)
        keys = {e["key"] for e in m["unplanned_epics"]}
        self.assertEqual(keys, {"E001", "E004"})       # active + planned, no archived

    def test_active_only(self):
        m = pm.build_progress_model(self.root, statuses={"active"})
        self.assertEqual({e["key"] for e in m["unplanned_epics"]}, {"E001"})

    def test_planned_only(self):
        m = pm.build_progress_model(self.root, statuses={"planned"})
        self.assertEqual({e["key"] for e in m["unplanned_epics"]}, {"E004"})

    def test_all_three(self):
        m = pm.build_progress_model(self.root, statuses={"planned", "active", "archived"})
        self.assertEqual({e["key"] for e in m["unplanned_epics"]}, {"E001", "E002", "E004"})

    def test_totals_count_everything_regardless_of_filter(self):
        narrow = pm.build_progress_model(self.root, statuses={"active"})
        wide = pm.build_progress_model(self.root, statuses={"planned", "active", "archived"})
        self.assertEqual(narrow["totals"], wide["totals"])

    def test_phase_denominator_is_filter_independent(self):
        plan = pm.load_plan(self.write_plan())        # phase 1 = E001, E002 (E002 archived+done)
        narrow = pm.build_progress_model(self.root, plan=plan, statuses={"active"})
        wide = pm.build_progress_model(self.root, plan=plan,
                                       statuses={"planned", "active", "archived"})
        self.assertEqual(narrow["phases"][0]["epic_total"], wide["phases"][0]["epic_total"])
        self.assertEqual(narrow["phases"][0]["epic_done"], wide["phases"][0]["epic_done"])
        # ...but the displayed list narrows
        self.assertEqual([e["key"] for e in narrow["phases"][0]["epics_detail"]], ["E001"])

    def test_model_records_the_filter_it_applied(self):
        m = pm.build_progress_model(self.root, statuses={"active"})
        self.assertEqual(m["statuses"], ["active"])

    def test_cli_status_flag(self):
        code, out = self.run_main(["report", "--state-root", self.root,
                                   "--status", "active", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual({e["key"] for e in json.loads(out)["unplanned_epics"]}, {"E001"})

    def test_cli_status_accepts_comma_list(self):
        code, out = self.run_main(["report", "--state-root", self.root,
                                   "--status", "active,archived", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual({e["key"] for e in json.loads(out)["unplanned_epics"]}, {"E001", "E002"})

    def test_cli_all_still_means_everything(self):
        code, out = self.run_main(["report", "--state-root", self.root,
                                   "--all", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual({e["key"] for e in json.loads(out)["unplanned_epics"]},
                         {"E001", "E002", "E004"})

    def test_cli_rejects_an_unknown_status(self):
        with redirect_stderr(io.StringIO()):
            code, _ = self.run_main(["report", "--state-root", self.root,
                                     "--status", "inprogress", "--format", "json"])
        self.assertEqual(code, 2)

    def test_tree_names_the_filter_when_narrowed(self):
        _, out = self.run_main(["report", "--state-root", self.root,
                                "--status", "active", "--format", "tree"])
        self.assertIn("active", out.lower())
        self.assertNotIn("E004", out)


class TestDispatchEvents(Base):
    def setUp(self):
        super().setUp()
        self.root = os.path.join(self.d, "state")
        os.makedirs(self.root)

    def test_open_then_close_leaves_nothing_open(self):
        code, out = self.run_main(["dispatch", "--state-root", self.root, "--event", "open",
                                   "--agent", "dev-story", "--epic", "E001", "--sprint", "S01",
                                   "--story", "E001-S01-003"])
        self.assertEqual(code, 0, out)
        code, out = self.run_main(["dispatch", "--state-root", self.root, "--event", "close",
                                   "--agent", "dev-story", "--epic", "E001", "--sprint", "S01",
                                   "--story", "E001-S01-003"])
        self.assertEqual(code, 0, out)
        self.assertEqual(pm.open_dispatches(self.root, 0), [])

    def test_unclosed_dispatch_past_threshold_is_reported(self):
        self.run_main(["dispatch", "--state-root", self.root, "--event", "open",
                       "--agent", "code-review", "--epic", "E001", "--sprint", "S01"])
        # 0-minute threshold: any open dispatch qualifies
        stalled = pm.open_dispatches(self.root, 0)
        self.assertEqual(len(stalled), 1)
        self.assertEqual(stalled[0]["agent"], "code-review")
        self.assertEqual(stalled[0]["sprint"], "S01")

    def test_threshold_excludes_young_dispatches(self):
        self.run_main(["dispatch", "--state-root", self.root, "--event", "open",
                       "--agent", "dev-story", "--epic", "E001"])
        self.assertEqual(pm.open_dispatches(self.root, 15), [])


class TestPartialTokenClasses(TestLayoutResolution):
    """I3: under runtime=claude an incomplete class set was zero-filled and then
    blessed by verify. `--tokens-output 10` alone wrote total=10 with three
    classes at 0, derived a cost from that, and verify PASSed — internally
    consistent, therefore unfalsifiable. Cache classes dominate real runs, so one
    forgotten flag understates a node by an order of magnitude."""

    def run_main(self, argv):
        buf, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(err):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue() + err.getvalue()

    def _set(self, extra):
        return self.run_main(["set-actual", "--state-root", self.root, "--node", "story",
                              "--story", "E001-S01-003", "--model", "claude-opus-5",
                              "--no-calibrate"] + extra)

    def test_claude_rejects_a_single_class(self):
        code, out = self._set(["--runtime", "claude", "--tokens-output", "10"])
        self.assertEqual(code, 2, out)
        self.assertIn("all four token classes", out)
        self.assertIn("--tokens-input", out)
        self.assertIn("--tokens-cache-write", out)
        self.assertIn("--tokens-cache-read", out)

    def test_claude_rejects_three_of_four(self):
        code, out = self._set(["--runtime", "claude", "--tokens-input", "1",
                               "--tokens-output", "2", "--tokens-cache-write", "3"])
        self.assertEqual(code, 2, out)
        self.assertIn("cache-read", out)

    def test_explicit_zero_counts_as_given(self):
        code, out = self._set(["--runtime", "claude", "--tokens-input", "10",
                               "--tokens-output", "0", "--tokens-cache-write", "0",
                               "--tokens-cache-read", "0"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(int(node["actual"]["tokens_k"]["total"]), 10)

    def test_runtime_other_still_accepts_a_partial_set(self):
        # A runtime that exposes only some classes is exactly what --runtime
        # other is for; the strict rule must not leak into it.
        code, out = self._set(["--runtime", "other", "--tokens-output", "10"])
        self.assertEqual(code, 0, out)

    def test_nothing_is_written_when_the_partial_set_is_rejected(self):
        self._set(["--runtime", "claude", "--tokens-output", "10"])
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertNotIn("actual", node)


class TestVerifyRejectsScalarTokens(TestLayoutResolution):
    """I4: verify skipped the cost invariant entirely when tokens_k was a bare
    scalar (`if hasattr(tk, "get")`), so `tokens_k: 500` beside `cost: 9999.99`
    returned PASS under runtime=claude. Design §4.3 says a hand-edited cost
    cannot survive verify."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _scalar_node(self, cost=9999.99):
        p = pm.story_file(self.root, "E001-S01-003")
        y, node = pm.load_node(p)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        node["actual"] = {"elapsed_hours": 1.0, "man_hours": 8, "hitl_hours": 0.2,
                          "tokens_k": 500, "cost": cost, "model": "claude-opus-5"}
        pm.save_node(y, node, p)

    def test_scalar_tokens_fail_under_runtime_claude(self):
        self._scalar_node()
        code, out = self.run_main(["verify", "--state-root", self.root, "--scope", "story",
                                   "--story", "E001-S01-003", "--runtime", "claude"])
        self.assertEqual(code, 4, out)
        self.assertIn("not the per-class mapping", out)

    def test_scalar_tokens_fail_under_require_tokens(self):
        self._scalar_node()
        code, out = self.run_main(["verify", "--state-root", self.root, "--scope", "story",
                                   "--story", "E001-S01-003", "--require-tokens"])
        self.assertEqual(code, 4, out)

    def test_scalar_tokens_still_pass_under_runtime_other(self):
        # set-estimate writes a scalar, and a runtime with no per-class
        # visibility has nothing better — the scalar form stays legitimate here.
        self._scalar_node()
        code, out = self.run_main(["verify", "--state-root", self.root, "--scope", "story",
                                   "--story", "E001-S01-003", "--runtime", "other"])
        self.assertEqual(code, 0, out)

    def test_na_tokens_are_not_reported_as_a_scalar(self):
        p = pm.story_file(self.root, "E001-S01-003")
        y, node = pm.load_node(p)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        node["actual"] = {"elapsed_hours": 1.0, "man_hours": 8, "hitl_hours": 0.2,
                          "tokens_k": "N/A", "cost": "N/A"}
        pm.save_node(y, node, p)
        code, out = self.run_main(["verify", "--state-root", self.root, "--scope", "story",
                                   "--story", "E001-S01-003", "--runtime", "claude"])
        self.assertEqual(code, 4, out)
        self.assertNotIn("not the per-class mapping", out)
        self.assertIn("N/A", out)


class TestSpendBreakout(Base):
    """I8: design §9 specifies `report` breaking spend out by story / closure /
    orchestration. `_accumulate_actuals` read only `node["actual"]`, and neither
    `rollup_sprint` nor `build_progress_model` ever read `orchestration` — so the
    72%-of-spend term this whole rework exists to surface was written to disk and
    then omitted from every report that renders it.
    """

    def setUp(self):
        super().setUp()
        self.root = os.path.join(self.d, "state")
        self.sd = os.path.join(self.root, "active", "epic-001", "sprint-01")
        os.makedirs(self.sd)
        self._w(os.path.join(self.root, "active", "epic-001", "epic.yaml"),
                {"key": "E001", "title": "Foundation", "status": "in-progress",
                 "actual": self._m(3.0, 12, 0.7, 2600),
                 "orchestration": self._m(0.3, 0, 0.05, 1000)})
        self._w(os.path.join(self.sd, "sprint.yaml"),
                {"key": "S01", "epic": "E001", "status": "done",
                 "actual": self._m(2.5, 10, 0.5, 2400),
                 "orchestration": self._m(0.6, 0, 0.1, 7200)})
        for i in (1, 2):
            self._w(os.path.join(self.sd, f"E001-S01-{i:03d}.yaml"),
                    {"key": f"E001-S01-{i:03d}", "epic": "E001", "sprint": "S01",
                     "status": "done", "actual": self._m(1.0, 4, 0.2, 1000)})

    @staticmethod
    def _m(elapsed, man, hitl, tokens):
        tk = {"total": tokens, "input": tokens, "output": 0,
              "cache_write": 0, "cache_read": 0}
        return {"elapsed_hours": elapsed, "man_hours": man, "hitl_hours": hitl,
                "tokens_k": tk, "cost": pm.cost_from_tokens(tk, "claude-opus-5"),
                "model": "claude-opus-5"}

    @staticmethod
    def _w(path, mapping):
        y = pm._yaml()
        with open(path, "w") as f:
            y.dump(mapping, f)

    # --- roll-ups ---------------------------------------------------------- #
    def test_sprint_rollup_splits_the_three_buckets(self):
        r = pm.rollup_sprint(self.root, "E001", "S01")
        self.assertEqual(r["spend"]["stories"]["tokens_k"], 2000)
        self.assertEqual(r["spend"]["closure"]["tokens_k"], 400)      # 2400 - 2000
        self.assertEqual(r["spend"]["orchestration"]["tokens_k"], 7200)

    def test_epic_rollup_adds_its_own_closure_and_orchestration(self):
        r = pm.rollup_epic(self.root, "E001")
        self.assertEqual(r["spend"]["stories"]["tokens_k"], 2000)
        # sprint closure 400 + epic closure (2600 - 2400) = 600
        self.assertEqual(r["spend"]["closure"]["tokens_k"], 600)
        self.assertEqual(r["spend"]["orchestration"]["tokens_k"], 8200)
        self.assertEqual(pm._spend_total(r["spend"])["tokens_k"], 10800)

    def test_buckets_partition_the_spend_without_double_counting(self):
        r = pm.rollup_epic(self.root, "E001")
        total = pm._spend_total(r["spend"])["tokens_k"]
        parts = sum(r["spend"][b].get("tokens_k", 0) for b in pm.SPEND_BUCKETS)
        self.assertEqual(total, parts)

    def test_missing_parent_actual_yields_no_closure_rather_than_a_bogus_one(self):
        self._w(os.path.join(self.sd, "sprint.yaml"),
                {"key": "S01", "epic": "E001", "status": "done"})
        r = pm.rollup_sprint(self.root, "E001", "S01")
        self.assertEqual(r["spend"]["closure"], {})
        self.assertEqual(r["spend"]["stories"]["tokens_k"], 2000)

    def test_negative_residual_clamps_to_zero_not_negative_spend(self):
        self._w(os.path.join(self.sd, "sprint.yaml"),
                {"key": "S01", "epic": "E001", "status": "done",
                 "actual": self._m(0.5, 1, 0.0, 100)})     # below the children's sum
        r = pm.rollup_sprint(self.root, "E001", "S01")
        self.assertEqual(r["spend"]["closure"]["tokens_k"], 0)

    # --- rendered surfaces ------------------------------------------------- #
    def test_show_prints_the_breakout(self):
        code, out = self.run_main(["show", "--state-root", self.root, "--epic", "E001"])
        self.assertEqual(code, 0, out)
        self.assertIn("spend/orchestration", out)
        self.assertIn("tokens_k=8200", out)
        self.assertIn("spend/TOTAL", out)

    def test_report_tree_carries_orchestration(self):
        code, out = self.run_main(["report", "--state-root", self.root])
        self.assertEqual(code, 0, out)
        self.assertIn("Spend (actual, by attribution", out)
        self.assertIn("orchestration", out)
        self.assertIn("tokens_k=8200", out)
        self.assertIn("tokens_k=10800", out)

    def test_report_md_carries_orchestration(self):
        code, out = self.run_main(["report", "--state-root", self.root, "--format", "md"])
        self.assertEqual(code, 0, out)
        self.assertIn("## Spend", out)
        self.assertIn("| orchestration |", out)
        self.assertIn("8200", out)

    def test_report_json_carries_the_buckets(self):
        code, out = self.run_main(["report", "--state-root", self.root, "--format", "json"])
        self.assertEqual(code, 0, out)
        model = json.loads(out)
        self.assertEqual(model["spend"]["orchestration"]["tokens_k"], 8200)
        self.assertEqual(model["spend_total"]["tokens_k"], 10800)

    def test_spend_covers_archived_epics_even_when_the_listing_does_not(self):
        # "what has this project cost" must not change with the display filter.
        code, out = self.run_main(["report", "--state-root", self.root,
                                   "--status", "archived", "--format", "json"])
        self.assertEqual(code, 0, out)
        model = json.loads(out)
        self.assertEqual(model["spend"]["orchestration"]["tokens_k"], 8200)

    def test_spend_section_is_omitted_when_nothing_was_spent(self):
        empty = os.path.join(self.d, "empty-state")
        os.makedirs(os.path.join(empty, "active"))
        code, out = self.run_main(["report", "--state-root", empty])
        self.assertEqual(code, 0, out)
        self.assertNotIn("Spend (actual", out)

    def test_float_summation_noise_is_not_rendered(self):
        code, out = self.run_main(["report", "--state-root", self.root])
        self.assertEqual(code, 0, out)
        self.assertNotIn("0000000", out)
        self.assertIn("elapsed_hours=3.9", out)


class TestMalformedEventLog(Base):
    """I5/M3: open_dispatches dereferenced every valid-JSON line without an
    isinstance guard and read the file without an OSError guard, while
    build_events_index next door had both. A line containing `42` — a torn write
    on an append-only log with concurrent writers — crashed `report` with
    AttributeError and exit 1, taking down the stall dashboard itself."""

    def setUp(self):
        super().setUp()
        self.root = os.path.join(self.d, "state")
        os.makedirs(os.path.join(self.root, "active"))

    def _append(self, raw):
        with open(pm.events_path(self.root), "a", encoding="utf-8") as fh:
            fh.write(raw + "\n")

    def test_bare_scalar_line_does_not_crash_open_dispatches(self):
        self.run_main(["dispatch", "--state-root", self.root, "--event", "open",
                       "--agent", "dev-story", "--epic", "E001", "--sprint", "S01"])
        self._append("42")
        stalled = pm.open_dispatches(self.root, 0)
        self.assertEqual(len(stalled), 1)
        self.assertEqual(stalled[0]["agent"], "dev-story")

    def test_json_list_line_is_skipped_too(self):
        self._append('["dispatch_open"]')
        self.run_main(["dispatch", "--state-root", self.root, "--event", "open",
                       "--agent", "code-review", "--epic", "E001"])
        self.assertEqual(len(pm.open_dispatches(self.root, 0)), 1)

    def test_report_survives_a_torn_line(self):
        self.run_main(["dispatch", "--state-root", self.root, "--event", "open",
                       "--agent", "dev-story", "--epic", "E001", "--sprint", "S01"])
        self._append("42")
        self._append('{"ts": "bogus", "event": ')       # torn: invalid JSON
        code, out = self.run_main(["report", "--state-root", self.root,
                                   "--stall-minutes", "0"])
        self.assertEqual(code, 0, out)
        self.assertIn("STALLED DISPATCH", out)
        self.assertIn("dev-story", out)


class TestReportStalls(Base):
    def setUp(self):
        super().setUp()
        self.root = os.path.join(self.d, "state")
        os.makedirs(os.path.join(self.root, "active"))

    def test_report_lists_stalled_dispatch(self):
        self.run_main(["dispatch", "--state-root", self.root, "--event", "open",
                       "--agent", "dev-story", "--epic", "E001", "--sprint", "S01"])
        code, out = self.run_main(["report", "--state-root", self.root,
                                   "--stall-minutes", "0"])
        self.assertEqual(code, 0, out)
        self.assertIn("STALLED DISPATCH", out)
        self.assertIn("dev-story", out)

    def test_report_silent_when_nothing_stalled(self):
        code, out = self.run_main(["report", "--state-root", self.root])
        self.assertEqual(code, 0, out)
        self.assertNotIn("STALLED DISPATCH", out)


class TestRates(Base):
    def test_cost_from_tokens_opus5(self):
        tokens = {"input": 174, "output": 58, "cache_write": 348, "cache_read": 580}
        # (174*5 + 58*25 + 348*6.25 + 580*0.50) / 1000
        self.assertAlmostEqual(pm.cost_from_tokens(tokens, "claude-opus-5"), 4.79, places=2)

    def test_same_tokens_cost_double_on_a_10_per_m_tier(self):
        tokens = {"input": 174, "output": 58, "cache_write": 348, "cache_read": 580}
        self.assertAlmostEqual(pm.cost_from_tokens(tokens, "claude-fable-5"), 9.57, places=2)

    def test_cache_write_dominates_a_cache_heavy_mix(self):
        tokens = {"input": 412, "output": 34, "cache_write": 4300, "cache_read": 253}
        self.assertAlmostEqual(pm.cost_from_tokens(tokens, "claude-opus-5"), 29.91, places=2)

    def test_unknown_model_is_a_hard_error(self):
        with self.assertRaises(KeyError):
            pm.cost_from_tokens({"input": 1}, "claude-not-a-model")

    def test_missing_class_counts_as_zero(self):
        self.assertAlmostEqual(pm.cost_from_tokens({"output": 10}, "claude-opus-5"), 0.25, places=2)

    def test_overrides_win(self):
        over = {"claude-opus-5": {"input": 1.0, "output": 1.0,
                                 "cache_write": 1.0, "cache_read": 1.0}}
        self.assertAlmostEqual(
            pm.cost_from_tokens({"input": 1000}, "claude-opus-5", over), 1.00, places=2)

    def test_rates_subcommand_prints_the_effective_table(self):
        code, out = self.run_main(["rates", "--model", "claude-opus-5"])
        self.assertEqual(code, 0, out)
        self.assertIn("cache_write", out)
        self.assertIn("6.25", out)

    def test_rates_subcommand_rejects_unknown_model(self):
        with redirect_stderr(io.StringIO()):
            code, out = self.run_main(["rates", "--model", "nope"])
        self.assertEqual(code, 2, out)

    def test_rates_lists_override_only_models(self):
        # design §5: `rates` prints the EFFECTIVE table after config overrides.
        # Listing sorted(TOKEN_RATES) alone hid exactly the models a project had
        # to add by hand (Bedrock/Vertex cards), which is when inspecting the
        # table matters most.
        over = json.dumps({"bedrock-opus": {"input": 6.0, "output": 30.0,
                                            "cache_write": 7.5, "cache_read": 0.6}})
        code, out = self.run_main(["rates", "--token-rates", over])
        self.assertEqual(code, 0, out)
        self.assertIn("bedrock-opus", out)
        self.assertIn("claude-opus-5", out)

    def test_rates_reports_a_partial_override_model_without_crashing(self):
        over = json.dumps({"partial-model": {"input": 6.0}})
        code, out = self.run_main(["rates", "--token-rates", over])
        self.assertEqual(code, 0, out)
        self.assertIn("partial-model", out)
        self.assertIn("cache_read=n/a", out)

    def test_partial_rate_card_is_a_hard_error_when_pricing(self):
        over = {"partial-model": {"input": 6.0}}
        with self.assertRaises(KeyError) as ctx:
            pm.cost_from_tokens({"input": 1, "cache_read": 1}, "partial-model", over)
        self.assertIn("cache_read", ctx.exception.args[0])


class TestOrchestrationBlock(TestLayoutResolution):
    """The orchestration component: a FRACTION of children's actuals, not a
    ratio against an estimate — see pm.record_orchestration_sample's docstring
    for why. Sprint/epic only; a story's orchestration is its parent sprint's.
    """

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _story_actual(self, tokens_total):
        p = pm.story_file(self.root, "E001-S01-003")
        y, node = pm.load_node(p)
        node["status"] = "done"
        node["actual"] = {"elapsed_hours": 1.0, "man_hours": 8, "hitl_hours": 0.2,
                          "tokens_k": {"total": tokens_total, "input": tokens_total,
                                       "output": 0, "cache_write": 0, "cache_read": 0},
                          "cost": pm.cost_from_tokens({"input": tokens_total},
                                                      "claude-opus-5"),
                          "model": "claude-opus-5"}
        pm.save_node(y, node, p)

    def test_orchestration_writes_to_its_own_block(self):
        code, out = self.run_main(["set-actual", "--state-root", self.root, "--node", "sprint",
                                   "--epic", "E001", "--sprint", "S01",
                                   "--block", "orchestration",
                                   "--tokens-input", "1000", "--model", "claude-opus-5",
                                   "--elapsed-hours", "2", "--no-calibrate"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.sprint_file(self.root, "E001", "S01"))
        self.assertIn("orchestration", node)
        self.assertNotIn("orchestration", node.get("actual") or {})
        self.assertEqual(int(node["orchestration"]["tokens_k"]["total"]), 1000)

    def test_orchestration_block_rejected_on_a_story(self):
        err = io.StringIO()
        try:
            with redirect_stderr(err):
                code = pm.main(["set-actual", "--state-root", self.root, "--node", "story",
                                "--story", "E001-S01-003", "--block", "orchestration",
                                "--elapsed-hours", "1"])
        except SystemExit as e:
            code = e.code
        self.assertEqual(code, 2, err.getvalue())
        self.assertIn("orchestration", err.getvalue().lower())
        self.assertIn("sprint", err.getvalue().lower())

    def test_fraction_sample_is_orchestration_over_children(self):
        self._story_actual(1000)
        code, out = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "sprint",
             "--epic", "E001", "--sprint", "S01", "--block", "orchestration",
             "--tokens-input", "3000", "--model", "claude-opus-5"])
        self.assertEqual(code, 0, out)
        _, cal = pm.load_calibration(self.root)
        samples = cal["orchestration"]["sprint"]["tokens_k"]["samples"]
        self.assertAlmostEqual(float(samples[-1]), 3.0, places=3)

    def test_fraction_inactive_below_three_samples(self):
        cal = pm.new_calibration()
        self.assertIsNone(pm.active_orchestration_fraction(cal, "sprint", "tokens_k"))

    def test_fraction_active_at_three_samples(self):
        cal = pm.new_calibration()
        cal["orchestration"]["sprint"]["tokens_k"] = {"samples": [2.0, 2.0, 2.0]}
        self.assertAlmostEqual(
            pm.active_orchestration_fraction(cal, "sprint", "tokens_k"), 2.0, places=3)

    def test_fraction_still_inactive_at_two_samples_boundary(self):
        # Proves activation is a strict >= MIN_SAMPLES (3), not off-by-one at 2.
        cal = pm.new_calibration()
        cal["orchestration"]["sprint"]["tokens_k"] = {"samples": [2.0, 2.0]}
        self.assertIsNone(pm.active_orchestration_fraction(cal, "sprint", "tokens_k"))

    def test_orchestration_never_calibrates_cost(self):
        # cost is derived from tokens x rates — a second, drift-capable
        # fraction for it would be redundant with the token fraction.
        self._story_actual(1000)
        self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "sprint",
             "--epic", "E001", "--sprint", "S01", "--block", "orchestration",
             "--tokens-input", "3000", "--model", "claude-opus-5"])
        _, cal = pm.load_calibration(self.root)
        self.assertNotIn("cost", cal["orchestration"]["sprint"])

    def test_denominator_requires_every_child_not_just_some(self):
        # A second story in the same sprint, WITHOUT an actual. A naive
        # partial-sum denominator (sum whatever children happen to have)
        # would still produce a tokens_k sample from the one story that does
        # have an actual — silently understating the true children total and
        # permanently inflating the fraction. record_orchestration_sample
        # must treat that as no sample for the metric, not a smaller one.
        self._story_actual(1000)
        sd = os.path.join(self.root, "active", "epic-001", "sprint-01")
        with open(os.path.join(sd, "E001-S01-004.yaml"), "w") as f:
            f.write("key: 'E001-S01-004'\nepic: 'E001'\nsprint: 'S01'\nstatus: review\n")
        code, out = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "sprint",
             "--epic", "E001", "--sprint", "S01", "--block", "orchestration",
             "--tokens-input", "3000", "--model", "claude-opus-5"])
        self.assertEqual(code, 0, out)
        self.assertIn("no orchestration sample", out.lower())
        self.assertIn("missing this metric's actual", out.lower())
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(len(cal["orchestration"]["sprint"]), 0)

    def test_second_orchestration_call_does_not_double_count(self):
        # Assert on the calibration file's sample COUNT, not the command's
        # exit code — a replay that is silently accepted (exit 0, no new
        # sample) must read as success to the caller while still recording
        # nothing extra in the shared file.
        self._story_actual(1000)
        argv = ["set-actual", "--state-root", self.root, "--node", "sprint",
                "--epic", "E001", "--sprint", "S01", "--block", "orchestration",
                "--tokens-input", "3000", "--model", "claude-opus-5"]
        code1, out1 = self.run_main(argv)
        self.assertEqual(code1, 0, out1)
        code2, out2 = self.run_main(list(argv))
        self.assertEqual(code2, 0, out2)
        self.assertIn("replay", out2.lower())
        _, cal = pm.load_calibration(self.root)
        samples = cal["orchestration"]["sprint"]["tokens_k"]["samples"]
        self.assertEqual(len(samples), 1)

    def test_orchestration_marker_is_distinct_from_closure_marker(self):
        # The whole reason for a SEPARATE marker: a sprint node carries both
        # a closure/actual sample and an orchestration sample. If they shared
        # CALIBRATION_MARKER, whichever ran first would silently suppress
        # the other. Record a closure sample first, then confirm the
        # orchestration sample still records.
        self._story_actual(1000)
        story_path = pm.story_file(self.root, "E001-S01-003")
        _, story_node = pm.load_node(story_path)
        story_node["estimate"] = {"man_hours_low": 3, "man_hours_high": 3}
        pm.save_node(pm._yaml(), story_node, story_path)
        sprint_path = pm.sprint_file(self.root, "E001", "S01")
        _, sprint_node = pm.load_node(sprint_path)
        sprint_node["estimate"] = {"man_hours_low": 12, "man_hours_high": 12}
        pm.save_node(pm._yaml(), sprint_node, sprint_path)
        code, out = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "sprint",
             "--epic", "E001", "--sprint", "S01", "--man-hours", "9"])
        self.assertEqual(code, 0, out)
        _, node_after_closure = pm.load_node(sprint_path)
        self.assertIn(pm.CALIBRATION_MARKER, node_after_closure)
        self.assertNotIn(pm.ORCHESTRATION_MARKER, node_after_closure)

        code, out = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "sprint",
             "--epic", "E001", "--sprint", "S01", "--block", "orchestration",
             "--tokens-input", "3000", "--model", "claude-opus-5"])
        self.assertEqual(code, 0, out)
        self.assertNotIn("replay", out.lower())
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(len(cal["orchestration"]["sprint"]["tokens_k"]["samples"]), 1)
        _, node_after_both = pm.load_node(sprint_path)
        self.assertIn(pm.ORCHESTRATION_MARKER, node_after_both)

    def test_epic_level_replay_guard_does_not_double_count(self):
        # Same exposure exists at epic level: _closure_nodes resolves the
        # epic's own file as the parent for level="epic", so the guard added
        # in record_orchestration_sample covers it via the same code path,
        # with no epic-specific branch needed. Proven here rather than
        # asserted.
        sprint_path = pm.sprint_file(self.root, "E001", "S01")
        _, sprint_node = pm.load_node(sprint_path)
        sprint_node["actual"] = {"elapsed_hours": 1.0, "man_hours": 8, "hitl_hours": 0.2,
                                 "tokens_k": {"total": 1000, "input": 1000, "output": 0,
                                              "cache_write": 0, "cache_read": 0},
                                 "cost": pm.cost_from_tokens({"input": 1000}, "claude-opus-5"),
                                 "model": "claude-opus-5"}
        pm.save_node(pm._yaml(), sprint_node, sprint_path)
        argv = ["set-actual", "--state-root", self.root, "--node", "epic",
                "--epic", "E001", "--block", "orchestration",
                "--tokens-input", "3000", "--model", "claude-opus-5"]
        code1, out1 = self.run_main(argv)
        self.assertEqual(code1, 0, out1)
        code2, out2 = self.run_main(list(argv))
        self.assertEqual(code2, 0, out2)
        self.assertIn("replay", out2.lower())
        _, cal = pm.load_calibration(self.root)
        samples = cal["orchestration"]["epic"]["tokens_k"]["samples"]
        self.assertEqual(len(samples), 1)

    def test_calibration_show_lists_orchestration_component(self):
        y, cal = pm.load_calibration(self.root)
        cal["orchestration"]["sprint"]["tokens_k"] = {"samples": [2.0, 2.0, 2.0]}
        pm.save_calibration(y, cal, self.root)
        code, out = self.run_main(["calibration", "show", "--state-root", self.root])
        self.assertEqual(code, 0, out)
        self.assertIn("orchestration", out)
        self.assertIn("sprint/tokens_k", out)



class TestFreshTokenScopeBasis(Base):
    """The scope ratio measures fresh tokens, not the cache-inclusive total.

    BASE_BANDS' tokens_k numbers are fresh-token scale (20-200k) while actuals are
    captured cache-inclusive. A real story measured 182,121k with 97.4% cache reads,
    so `actual.total / band` silently absorbed a ~1000x basis gap. The per-class
    evidence showed it was a basis error and not signal: the complex bucket read
    285.291 over five samples straddling the accounting change, standard 7.386 over
    three that did not.
    """

    def _story(self, fresh, cache_read, band_mid=140.0):
        """A closed story whose estimate came from the complex band."""
        return {
            "key": "E001-S01-001", "classification": "complex",
            "estimate": {"fix_factor": 1.0,
                         "scope_ratios": {"tokens_k": 1.0},
                         "tokens_k": {"total": band_mid}},
            "actual": {"tokens_k": {"total": fresh + cache_read,
                                    "input": fresh * 0.2, "output": fresh * 0.1,
                                    "cache_write": fresh * 0.7,
                                    "cache_read": cache_read}},
            "completion_evidence": {"fix_iterations": 0},
        }

    def test_ratio_ignores_cache_read(self):
        fresh, cache_read = 4735.0, 177386.0        # the observed 97.4% split
        sample = pm.derive_story_sample(self._story(fresh, cache_read))
        got = sample["scope_ratios"]["tokens_k"]
        self.assertAlmostEqual(got, fresh / 140.0, places=3)
        poisoned = (fresh + cache_read) / 140.0
        self.assertGreater(poisoned / got, 30,
                           "premise: the old basis was orders of magnitude larger")

    def test_cache_read_volume_does_not_move_the_ratio(self):
        """Same story, ten times the corpus. Scope is unchanged, so the ratio must be."""
        a = pm.derive_story_sample(self._story(4735.0, 177386.0))["scope_ratios"]["tokens_k"]
        b = pm.derive_story_sample(self._story(4735.0, 1773860.0))["scope_ratios"]["tokens_k"]
        self.assertAlmostEqual(a, b, places=6)

    def test_no_fresh_tokens_yields_no_scope_sample(self):
        n = self._story(0.0, 177386.0)
        sample = pm.derive_story_sample(n)
        self.assertNotIn("tokens_k", (sample or {}).get("scope_ratios", {}))


class TestTokenBasisMigration(Base):
    def _cal(self, extra=""):
        root = os.path.join(self.d, "state")
        os.makedirs(root, exist_ok=True)
        with open(os.path.join(root, "pm-calibration.yaml"), "w", encoding="utf-8") as fh:
            fh.write("version: 2\nmetrics_migrated_at: '2026-01-01T00:00:00+00:00'\n"
                     "scope:\n  complex:\n    tokens_k:\n      samples: [285.291, 300.0, 270.0]\n"
                     "    man_hours:\n      samples: [1.1, 1.2, 1.3]\n"
                     "token_mix:\n  samples:\n  - {input: 0.01, output: 0.005, "
                     "cache_write: 0.011, cache_read: 0.974}\n" + extra)
        return root

    def test_purges_poisoned_tokens_k_but_keeps_everything_else(self):
        root = self._cal()
        y, cal = pm.load_calibration(root)
        log = pm.migrate_calibration_token_basis(y, cal, root)
        self.assertTrue(any("PURGE" in l for l in log), log)
        self.assertEqual(cal["scope"]["complex"]["tokens_k"]["samples"], [])
        self.assertEqual(cal["scope"]["complex"]["man_hours"]["samples"], [1.1, 1.2, 1.3],
                         "man_hours was never measured in tokens")
        self.assertEqual(len(cal["token_mix"]["samples"]), 1,
                         "token_mix is per-class fractions — basis-independent, and the "
                         "evidence for this very change")
        self.assertEqual(cal.get("version"), 2, "no schema version bump")

    def test_migration_is_one_shot(self):
        root = self._cal()
        y, cal = pm.load_calibration(root)
        pm.migrate_calibration_token_basis(y, cal, root)
        cal["scope"]["complex"]["tokens_k"]["samples"] = [1.0, 1.1, 1.2]
        self.assertEqual(pm.migrate_calibration_token_basis(y, cal, root), [])
        self.assertEqual(cal["scope"]["complex"]["tokens_k"]["samples"], [1.0, 1.1, 1.2],
                         "post-migration samples are on the new basis and must survive")

    def test_read_only_never_applies_a_pre_basis_ratio(self):
        cal = {"scope": {"complex": {"tokens_k": {"samples": [285.291, 300.0, 270.0]}}}}
        self.assertIsNone(pm.active_scope_ratio(cal, "complex", "tokens_k"),
                          "an unmigrated file must fall back to cold start, not apply 285x")
        cal[pm.TOKEN_BASIS_MARKER] = "2026-01-01T00:00:00+00:00"
        self.assertIsNotNone(pm.active_scope_ratio(cal, "complex", "tokens_k"))


class TestTranscriptUsage(Base):
    """The three traps in "read the usage fields", each reproduced.

    Two inflate and one deflates, which is why an agent that hit all three produced a
    plausible-looking wrong answer (the errors partly cancel) rather than an
    obviously broken one. Shapes here match a real transcript: 2,482 assistant records
    over 953 distinct message ids, with nested cache_creation summing to the flat field
    in every record.
    """

    def _write(self, name, records):
        p = os.path.join(self.d, name)
        with open(p, "w", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r) + "\n")
        return p

    def _asst(self, mid, inp, out, cw, cr, sidechain=False):
        return {"type": "assistant", "isSidechain": sidechain,
                "message": {"id": mid, "usage": {
                    "input_tokens": inp, "output_tokens": out,
                    "cache_creation_input_tokens": cw,
                    "cache_read_input_tokens": cr,
                    # the nested form carries the SAME tokens as the flat field
                    "cache_creation": {"ephemeral_5m_input_tokens": cw,
                                       "ephemeral_1h_input_tokens": 0}}}}

    def test_trap1_repeated_records_of_one_message_count_once(self):
        """A streaming message is written many times with identical id and usage."""
        recs = [self._asst("msg_a", 10, 20, 30, 40)] * 5 + [self._asst("msg_b", 1, 2, 3, 4)]
        res = pm.read_transcript_usage(self._write("t.jsonl", recs))
        self.assertEqual(res["records"], 6)
        self.assertEqual(res["unique_messages"], 2)
        self.assertEqual(res["tokens"], {"input": 11, "output": 22,
                                         "cache_write": 33, "cache_read": 44})

    def test_trap2_nested_cache_creation_is_not_added_to_the_flat_field(self):
        res = pm.read_transcript_usage(self._write("t.jsonl", [self._asst("m", 0, 0, 500, 0)]))
        self.assertEqual(res["tokens"]["cache_write"], 500,
                         "the nested mapping is the same tokens as the flat field")

    def test_trap3_sidechain_subagent_turns_are_counted(self):
        recs = [self._asst("main", 1, 1, 1, 1),
                self._asst("sub", 100, 100, 100, 100, sidechain=True)]
        res = pm.read_transcript_usage(self._write("t.jsonl", recs))
        self.assertEqual(res["sidechain_messages"], 1)
        self.assertEqual(res["tokens"]["input"], 101,
                         "dropping subagent turns is the deflating half of the error")

    def test_a_directory_sums_a_run_split_across_files(self):
        sub = os.path.join(self.d, "run")
        os.makedirs(sub)
        self._write(os.path.join("run", "a.jsonl"), [self._asst("a", 1, 1, 1, 1)])
        self._write(os.path.join("run", "b.jsonl"), [self._asst("b", 2, 2, 2, 2)])
        res = pm.read_transcript_usage(sub)
        self.assertEqual(res["files"], 2)
        self.assertEqual(res["tokens"]["input"], 3)

    def test_non_assistant_and_torn_lines_are_skipped_not_fatal(self):
        p = os.path.join(self.d, "t.jsonl")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "user", "message": {"usage": {"input_tokens": 999}}}) + "\n")
            fh.write("{not json\n")
            fh.write("42\n")
            fh.write(json.dumps(self._asst("m", 5, 0, 0, 0)) + "\n")
        res = pm.read_transcript_usage(p)
        self.assertEqual(res["tokens"]["input"], 5)

    def test_all_three_traps_together_match_a_hand_check(self):
        """The combined case: without the fixes this reads high on two axes and low on one."""
        recs = ([self._asst("m1", 10, 10, 100, 1000)] * 3 +
                [self._asst("m2", 10, 10, 100, 1000, sidechain=True)] * 2)
        res = pm.read_transcript_usage(self._write("t.jsonl", recs))
        self.assertEqual(res["tokens"], {"input": 20, "output": 20,
                                         "cache_write": 200, "cache_read": 2000})
        naive_records = 5 * 1000
        self.assertLess(res["tokens"]["cache_read"], naive_records,
                        "summing records rather than ids overstates")

    def test_usage_command_emits_pasteable_set_actual_flags(self):
        # A realistic fixture carries sessionId: the CLI checks identity before summing,
        # so a transcript without one is refused (see TestTranscriptIdentity).
        rec = self._asst("m", 1000, 2000, 3000, 4000)
        rec["sessionId"] = "SESS-1"
        rec["timestamp"] = "2026-08-01T12:00:00.000Z"
        p = self._write("t.jsonl", [rec])
        # Scoped, because the flags are withheld on an unscoped read: a session total is
        # not a node's actual (see TestTranscriptScoping).
        code, out = self.run_main(["usage", p, "--claude-session", "SESS-1",
                                   "--since", "2026-08-01T11:00:00.000Z",
                                   "--until", "2026-08-01T13:00:00.000Z",
                                   "--model", "claude-opus-5"])
        self.assertEqual(code, 0, out)
        self.assertIn("--tokens-input 1.000", out)
        self.assertIn("--tokens-cache-write 3.000", out)
        self.assertIn("cost", out)


class TestTranscriptIdentity(Base):
    """"Which transcript is mine" — the trap that produced the original bad number.

    Pointed at a task `.output` artifact rather than a session transcript, a count
    reported an output count several times below what the agent that ran the story
    reported. The cache
    figures matched closely, so nothing looked wrong: it was file choice, not arithmetic.
    A reader that can be aimed at the wrong file has not fixed that, it has moved it one
    step earlier — so identity is checked before any summing happens.
    """

    def _sess_file(self, name, sid, n=2):
        p = os.path.join(self.d, name)
        with open(p, "w", encoding="utf-8") as fh:
            for i in range(n):
                fh.write(json.dumps({
                    "type": "assistant", "sessionId": sid,
                    "message": {"id": f"m{i}", "usage": {
                        "input_tokens": 1, "output_tokens": 1,
                        "cache_creation_input_tokens": 1, "cache_read_input_tokens": 1}}}) + "\n")
        return p

    def test_refuses_a_file_carrying_no_session_id(self):
        """The .output artifact shape: assistant records, plausible usage, no sessionId."""
        p = os.path.join(self.d, "task.output.jsonl")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "assistant",
                                 "message": {"id": "m", "usage": {"output_tokens": 11931}}}) + "\n")
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, _ = self.run_main(["usage", p, "--claude-session", "S1"])
        self.assertEqual(code, 2)
        self.assertIn("not a session transcript", buf.getvalue())

    def test_refuses_a_transcript_belonging_to_another_session(self):
        p = self._sess_file("other.jsonl", "SOMEONE-ELSE")
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, _ = self.run_main(["usage", p, "--claude-session", "MINE"])
        self.assertEqual(code, 2)
        self.assertIn("SOMEONE-ELSE", buf.getvalue())

    def test_refuses_a_file_mixing_sessions(self):
        p = os.path.join(self.d, "mixed.jsonl")
        with open(p, "w", encoding="utf-8") as fh:
            for sid in ("A", "B"):
                fh.write(json.dumps({"type": "assistant", "sessionId": sid,
                                     "message": {"id": sid, "usage": {"output_tokens": 1}}}) + "\n")
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, _ = self.run_main(["usage", p])
        self.assertEqual(code, 2)
        self.assertIn("mixes", buf.getvalue())

    def test_accepts_the_matching_session(self):
        p = self._sess_file("mine.jsonl", "MINE")
        code, out = self.run_main(["usage", p, "--claude-session", "MINE"])
        self.assertEqual(code, 0, out)
        self.assertIn("MINE", out)
        self.assertIn("identity checked", out)

    def test_refuses_to_guess_when_nothing_identifies_the_session(self):
        old = os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
        try:
            buf = io.StringIO()
            with redirect_stderr(buf):
                code, _ = self.run_main(["usage"])
            self.assertEqual(code, 2)
            self.assertIn("Refusing to", buf.getvalue())
        finally:
            if old is not None:
                os.environ["CLAUDE_CODE_SESSION_ID"] = old

    def test_override_is_available_but_labels_the_result_unverified(self):
        """The escape hatch must not let the output claim provenance it never checked."""
        p = self._sess_file("other.jsonl", "SOMEONE-ELSE")
        code, out = self.run_main(["usage", p, "--claude-session", "MINE",
                                   "--allow-unidentified"])
        self.assertEqual(code, 0, out)
        self.assertIn("UNVERIFIED", out)
        self.assertIn("identity NOT checked", out)
        self.assertNotIn("session MINE ", out)

    def test_resolver_finds_a_transcript_by_session_id(self):
        paths, sid = pm.resolve_session_transcript("definitely-not-a-real-session-id")
        self.assertEqual(paths, [])
        self.assertEqual(sid, "definitely-not-a-real-session-id")


class TestTranscriptScoping(Base):
    """Identity is not scope. Both defects found in 2.4.6's reader.

    The reader resolved the right transcript and verified it, then summed all of it.
    A session file spans everything that session ever did: one observed file covered a
    whole epic lineage and totalled ~66x the sprint being closed, which as a node actual
    would have poisoned calibration for the rest of the epic. Separately, the no-argument
    path reported sidechain=0 on every run, because subagent turns are not in the parent
    file at all -- they live in <session-id>/subagents/agent-*.jsonl.
    """

    def _rec(self, mid, ts, out=10, sid="S1", side=False):
        return {"type": "assistant", "sessionId": sid, "isSidechain": side,
                "timestamp": ts,
                "message": {"id": mid, "usage": {
                    "input_tokens": 0, "output_tokens": out,
                    "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}}

    def _write(self, name, recs):
        p = os.path.join(self.d, name)
        os.makedirs(os.path.dirname(p), exist_ok=True) if os.path.dirname(name) else None
        with open(p, "w", encoding="utf-8") as fh:
            for r in recs:
                fh.write(json.dumps(r) + "\n")
        return p

    def test_window_excludes_records_outside_the_bracket(self):
        p = self._write("t.jsonl", [
            self._rec("before", "2026-08-01T10:00:00.000Z", out=1000),
            self._rec("inside", "2026-08-01T12:00:00.000Z", out=7),
            self._rec("after",  "2026-08-01T14:00:00.000Z", out=1000)])
        res = pm.read_transcript_usage(
            p, since=pm._parse_iso("2026-08-01T11:00:00.000Z"),
            until=pm._parse_iso("2026-08-01T13:00:00.000Z"))
        self.assertEqual(res["tokens"]["output"], 7)
        self.assertEqual(res["outside_window"], 2)
        self.assertTrue(res["windowed"])

    def test_unwindowed_read_sums_the_whole_session(self):
        """The defect, reproduced: without a window the total is the session, not the node."""
        p = self._write("t.jsonl", [
            self._rec("a", "2026-08-01T10:00:00.000Z", out=1000),
            self._rec("b", "2026-08-01T12:00:00.000Z", out=7)])
        res = pm.read_transcript_usage(p)
        self.assertEqual(res["tokens"]["output"], 1007)
        self.assertFalse(res["windowed"])

    def test_dispatch_window_uses_first_open_and_last_close(self):
        """A story is re-dispatched per fix iteration; all of it is that story's spend."""
        root = os.path.join(self.d, "state")
        os.makedirs(root, exist_ok=True)
        with open(os.path.join(root, "events.jsonl"), "w", encoding="utf-8") as fh:
            for ev, ts in [("dispatch_open", "2026-08-01T10:00:00+00:00"),
                           ("dispatch_close", "2026-08-01T11:00:00+00:00"),
                           ("dispatch_open", "2026-08-01T12:00:00+00:00"),
                           ("dispatch_close", "2026-08-01T13:00:00+00:00")]:
                fh.write(json.dumps({"ts": ts, "event": ev, "agent": "bmad-dev-story",
                                     "epic": "E001", "story": "E001-S01-001"}) + "\n")
            fh.write(json.dumps({"ts": "2026-08-01T20:00:00+00:00", "event": "dispatch_open",
                                 "agent": "bmad-dev-story", "epic": "E001",
                                 "story": "E001-S01-999"}) + "\n")
        a, b = pm.dispatch_window(root, story="E001-S01-001")
        self.assertEqual(a, pm._parse_iso("2026-08-01T10:00:00+00:00"))
        self.assertEqual(b, pm._parse_iso("2026-08-01T13:00:00+00:00"),
                         "last close, so fix iterations are included")

    def test_dispatch_window_ignores_other_nodes(self):
        root = os.path.join(self.d, "state")
        os.makedirs(root, exist_ok=True)
        with open(os.path.join(root, "events.jsonl"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": "2026-08-01T10:00:00+00:00", "event": "dispatch_open",
                                 "agent": "x", "story": "OTHER"}) + "\n")
        self.assertEqual(pm.dispatch_window(root, story="MINE"), (None, None))

    def test_cli_refuses_a_node_with_no_dispatch_bracket(self):
        root = os.path.join(self.d, "state")
        os.makedirs(root, exist_ok=True)
        open(os.path.join(root, "events.jsonl"), "w").close()
        p = self._write("t.jsonl", [self._rec("m", "2026-08-01T10:00:00.000Z")])
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, _ = self.run_main(["usage", p, "--claude-session", "S1",
                                     "--story", "E001-S01-001", "--state-root", root])
        self.assertEqual(code, 2)
        self.assertIn("no dispatch bracket", buf.getvalue())

    def test_cli_withholds_set_actual_flags_when_unscoped(self):
        """The pasteable flags are what gets misused, so they are not offered unscoped."""
        p = self._write("t.jsonl", [self._rec("m", "2026-08-01T10:00:00.000Z")])
        code, out = self.run_main(["usage", p, "--claude-session", "S1"])
        self.assertEqual(code, 0, out)
        self.assertIn("UNSCOPED", out)
        self.assertIn("withheld", out)
        self.assertNotIn("--tokens-input", out)

    def test_cli_emits_flags_once_scoped(self):
        p = self._write("t.jsonl", [self._rec("m", "2026-08-01T12:00:00.000Z", out=42)])
        code, out = self.run_main(["usage", p, "--claude-session", "S1",
                                   "--since", "2026-08-01T11:00:00.000Z",
                                   "--until", "2026-08-01T13:00:00.000Z"])
        self.assertEqual(code, 0, out)
        self.assertIn("--tokens-output 0.042", out)
        self.assertNotIn("UNSCOPED", out)

    def test_resolver_includes_the_subagents_directory(self):
        """Subagent turns are not in the parent file — sidechain=0 was the symptom."""
        root = os.path.join(self.d, "projects")
        proj = os.path.join(root, "-some-project")
        subs = os.path.join(proj, "SESS", "subagents")
        os.makedirs(subs)
        open(os.path.join(proj, "SESS.jsonl"), "w").close()
        open(os.path.join(subs, "agent-aaa.jsonl"), "w").close()
        open(os.path.join(subs, "agent-bbb.jsonl"), "w").close()
        real = os.path.expanduser
        try:
            os.path.expanduser = lambda p: root if p == "~/.claude/projects" else real(p)
            paths, sid = pm.resolve_session_transcript("SESS")
        finally:
            os.path.expanduser = real
        self.assertEqual(sid, "SESS")
        self.assertEqual(len(paths), 3, paths)
        self.assertEqual(sum(1 for p in paths if "subagents" in p), 2)


class TestFixIterationsTyping(Base):
    """fix_iterations stored as text broke the scope-versus-fix split silently.

    set-field takes --value as text and wrote it verbatim, so the field landed quoted.
    The provenance test then depended on that text parsing as an int: '0' happened to
    work, '0.0' raised ValueError and lost the whole sample, and any non-numeric text --
    an unsubstituted placeholder, an empty string -- read as provenance=backout on a
    story that needed no rework. That divides the scope ratio by a 1.25 fix factor it
    never incurred, and leaves the `clean` cohort empty so `fix` can never activate.
    """

    def test_iter_count_accepts_every_shape_that_means_zero(self):
        for v in (0, "0", 0.0, "0.0", "00", " 0 "):
            self.assertEqual(pm._iter_count(v), 0, f"{v!r} means zero iterations")

    def test_iter_count_rejects_what_is_not_a_count(self):
        for v in ("{fix_iterations}", "", None, "none", -1, 1.5, True):
            self.assertIsNone(pm._iter_count(v), f"{v!r} is not an iteration count")

    def test_float_string_no_longer_loses_the_sample(self):
        """'0.0' raised ValueError inside derive_story_sample and aborted it entirely."""
        node = {"classification": "standard",
                "estimate": {"fix_factor": 1.25, "scope_ratios": {"man_hours": 1.0},
                             "man_hours": 8.75},
                "actual": {"man_hours": 9.0},
                "completion_evidence": {"fix_iterations": "0.0"}}
        sample = pm.derive_story_sample(node)
        self.assertEqual(sample["provenance"], "exact")
        self.assertEqual(sample["fix_iterations"], 0)


class TestSetFieldTyping(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        return code, buf.getvalue()

    def test_set_field_stores_fix_iterations_as_a_number(self):
        code, out = self.run_main(["set-field", "--state-root", self.root,
                                   "--story", "E001-S01-003",
                                   "--field", "completion_evidence.fix_iterations",
                                   "--value", "0"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        v = node["completion_evidence"]["fix_iterations"]
        self.assertIsInstance(v, int, f"stored as {type(v).__name__}: {v!r}")
        self.assertEqual(v, 0)

    def test_set_field_refuses_a_non_numeric_fix_iterations(self):
        """An unsubstituted template placeholder is the realistic way this arrives."""
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, _ = self.run_main(["set-field", "--state-root", self.root,
                                     "--story", "E001-S01-003",
                                     "--field", "completion_evidence.fix_iterations",
                                     "--value", "{fix_iterations}"])
        self.assertEqual(code, 2)
        self.assertIn("non-negative whole number", buf.getvalue())

    # test_set_field_stores_tests_passing_as_a_bool removed: Task 4 makes
    # completion_evidence.tests_passing derived-only. See TestTestRunEvidence
    # below for the replacement (set-field now refuses this field outright).


class TestTestRunEvidence(TestLayoutResolution):
    # TestLayoutResolution supplies the node tree but not run_main -- every class
    # extending it defines its own (see TestSetFieldTyping above). Same three lines:
    def run_main(self, argv):
        buf = io.StringIO()
        code = 0
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        return code, buf.getvalue()

    def test_a_recorded_run_appends_and_derives_the_boolean(self):
        self.run_main(["add-test-run", "--state-root", self.root, "--story", "E001-S01-003",
                       "--command", "npm test", "--exit-code", "0"])
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        runs = node["completion_evidence"]["test_runs"]
        self.assertEqual(runs[0]["command"], "npm test")
        self.assertEqual(runs[0]["exit_code"], 0)
        self.assertIs(node["completion_evidence"]["tests_passing"], True)

    def test_one_failing_run_makes_the_derived_boolean_false(self):
        for cmd, rc in (("npm test", "0"), ("pytest", "1")):
            self.run_main(["add-test-run", "--state-root", self.root, "--story", "E001-S01-003",
                           "--command", cmd, "--exit-code", rc])
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertIs(node["completion_evidence"]["tests_passing"], False)

    def test_tests_passing_can_no_longer_be_asserted_by_hand(self):
        """The whole point: the agent records what it ran, not what it concluded."""
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, _ = self.run_main(["set-field", "--state-root", self.root,
                                     "--story", "E001-S01-003",
                                     "--field", "completion_evidence.tests_passing",
                                     "--value", "true"])
        self.assertEqual(code, 2)
        self.assertIn("add-test-run", buf.getvalue())

    def test_a_malformed_stored_exit_code_fails_rather_than_crashes(self):
        """test_runs is hand-editable YAML; a non-numeric exit_code must derive False,
        never raise and never derive True."""
        path = pm.story_file(self.root, "E001-S01-003")
        y, node = pm.load_node(path)
        ce = node.setdefault("completion_evidence", {})
        ce["test_runs"] = [{"command": "old flaky run", "exit_code": "flaky"}]
        pm.save_node(y, node, path)

        code, out = self.run_main(["add-test-run", "--state-root", self.root,
                                   "--story", "E001-S01-003",
                                   "--command", "npm test", "--exit-code", "0"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(path)
        self.assertIs(node["completion_evidence"]["tests_passing"], False)

    def test_no_recorded_runs_leaves_tests_passing_absent(self):
        """The exact regression all(()) == True would reintroduce: a story that never
        called add-test-run must never read as tests_passing: true."""
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        ce = node.get("completion_evidence") or {}
        self.assertNotIn("tests_passing", ce)

    def test_a_rerun_of_the_same_command_supersedes_its_earlier_failure(self):
        """The normal fix-then-rerun cycle the step file asks for: pytest -> 1, fix,
        pytest -> 0. The derived boolean reads the LAST run of each distinct command,
        so this closes True -- and BOTH entries stay in test_runs, because the failed
        run is the evidence that made the field falsifiable."""
        for rc in ("1", "0"):
            self.run_main(["add-test-run", "--state-root", self.root,
                           "--story", "E001-S01-003",
                           "--command", "pytest", "--exit-code", rc])
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        ce = node["completion_evidence"]
        self.assertIs(ce["tests_passing"], True)
        self.assertEqual([(r["command"], r["exit_code"]) for r in ce["test_runs"]],
                         [("pytest", 1), ("pytest", 0)])

    def test_a_different_command_still_failing_derives_false(self):
        """Last-run-wins is per command, not global: re-running one suite green never
        speaks for a different suite whose latest run is red."""
        for cmd, rc in (("pytest", "1"), ("pytest", "0"), ("npm test", "1")):
            self.run_main(["add-test-run", "--state-root", self.root,
                           "--story", "E001-S01-003",
                           "--command", cmd, "--exit-code", rc])
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        ce = node["completion_evidence"]
        self.assertIs(ce["tests_passing"], False)
        self.assertEqual(len(ce["test_runs"]), 3)

    def test_negative_exit_code_is_refused(self):
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, _ = self.run_main(["add-test-run", "--state-root", self.root,
                                     "--story", "E001-S01-003",
                                     "--command", "npm test", "--exit-code", "-1"])
        self.assertEqual(code, 2)


class TestCalibrationRedrive(TestLayoutResolution):
    def _close_story(self, iters):
        p = pm.story_file(self.root, "E001-S01-003")
        y, node = pm.load_node(p)
        node["classification"] = "standard"
        node["estimate"] = {"fix_factor": 1.25, "scope_ratios": {"man_hours": 1.0},
                            "man_hours": 8.75}
        node["actual"] = {"man_hours": 9.0}
        node["completion_evidence"] = {"fix_iterations": iters}
        pm.save_node(y, node, p)

    def test_redrive_repairs_a_sample_poisoned_by_the_string_bug(self):
        # A node closed under the bug: text that does not parse, read as backout.
        self._close_story("{fix_iterations}")
        poisoned = pm.derive_story_sample(pm.load_node(pm.story_file(self.root, "E001-S01-003"))[1])
        self.assertEqual(poisoned["provenance"], "backout", "premise: the bug's reading")

        # The node is corrected (as a run would now write it), then redriven.
        self._close_story(0)
        rep = pm.redrive_story_samples(self.root)
        self.assertEqual(rep["provenance"], {"exact": 1})
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(cal["fix"]["standard"]["clean"]["samples"], 1,
                         "the clean cohort fills, so fix can eventually activate")

    def test_redrive_rebuilds_rather_than_appends(self):
        self._close_story(0)
        pm.redrive_story_samples(self.root)
        rep = pm.redrive_story_samples(self.root)
        self.assertEqual(rep["sampled"], 1)
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(len(cal["scope"]["standard"]["man_hours"]["samples"]), 1,
                         "a second redrive must replace, never double-count")

    def test_redrive_leaves_untouched_components_alone(self):
        self._close_story(0)
        with pm.calibration_lock(self.root):
            y, cal = pm.load_calibration(self.root)
            cal["token_mix"] = {"samples": [{"input": 0.1, "output": 0.1,
                                             "cache_write": 0.3, "cache_read": 0.5}]}
            cal["closure"] = {"sprint": {"man_hours": {"samples": [1.1]}}}
            pm.save_calibration(y, cal, self.root)
        pm.redrive_story_samples(self.root)
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(len(cal["token_mix"]["samples"]), 1)
        self.assertEqual(cal["closure"]["sprint"]["man_hours"]["samples"], [1.1])


class TestSyncStoryDoc(Base):
    # Base (test-pm-status.py:30) supplies run_main; TestLayoutResolution does NOT,
    # which is why every class extending it defines its own. This command needs no
    # node tree, so Base is the right fixture.
    def setUp(self):
        super().setUp()
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.doc = os.path.join(self.dir, "epic-001", "sprint-01", "stories",
                                "E001-S01-003.md")
        os.makedirs(os.path.dirname(self.doc), exist_ok=True)

    def _write(self, text):
        with io.open(self.doc, "w", encoding="utf-8") as fh:
            fh.write(text)

    def _read(self):
        with io.open(self.doc, encoding="utf-8") as fh:
            return fh.read()

    def test_status_in_frontmatter_is_rewritten(self):
        self._write("---\nkey: E001-S01-003\nstatus: backlog\n---\n\n# Story\n\nBody.\n")
        code, _ = self.run_main(["sync-story-doc", "--artifacts-root", self.dir,
                            "--story", "E001-S01-003", "--status", "done"])
        self.assertEqual(code, 0)
        self.assertIn("status: done", self._read())

    def test_body_and_key_order_survive_the_rewrite(self):
        # The body carries a genuine standalone fence line (a markdown thematic
        # break) -- not a dash run mid-sentence, which the closing-fence search
        # ("\n---") could never mistake for the real one anyway. This is the
        # actual hazard the implementation must get right: it must stop at the
        # FIRST "\n---" (the frontmatter's own close) and leave every later one
        # in the body untouched.
        self._write("---\nkey: E001-S01-003\nstatus: backlog\ntitle: A thing\n---\n\n"
                    "# Story\n\nIntro paragraph.\n\n---\n\nAfter a thematic break.\n")
        self.run_main(["sync-story-doc", "--artifacts-root", self.dir,
                  "--story", "E001-S01-003", "--status", "review"])
        out = self._read()
        self.assertIn("Intro paragraph.", out)
        self.assertIn("\n\n---\n\nAfter a thematic break.\n", out,
                      "the body's own thematic-break fence must survive verbatim")
        self.assertLess(out.index("key:"), out.index("status:"))
        self.assertLess(out.index("status:"), out.index("title:"))

    def test_a_missing_story_file_warns_but_never_fails_the_caller(self):
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, _ = self.run_main(["sync-story-doc", "--artifacts-root", self.dir,
                                "--story", "E001-S01-999", "--status", "done"])
        self.assertEqual(code, 0)
        self.assertIn("no story file", buf.getvalue())

    def test_an_invalid_status_is_refused(self):
        self._write("---\nstatus: backlog\n---\n\nBody.\n")
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, _ = self.run_main(["sync-story-doc", "--artifacts-root", self.dir,
                                "--story", "E001-S01-003", "--status", "finished"])
        self.assertEqual(code, 2)

    # Finding 1 (fix round 1): a set-status this command follows has already
    # succeeded, so a frontmatter that fails to load as a mapping must never
    # raise past this command -- warn on stderr and return 0. Three realistic
    # shapes of "frontmatter a human could actually leave behind":

    def test_frontmatter_that_parses_to_a_list_never_fails_the_caller(self):
        self._write("---\n- a\n- b\n---\n\nBody.\n")
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, _ = self.run_main(["sync-story-doc", "--artifacts-root", self.dir,
                                "--story", "E001-S01-003", "--status", "done"])
        self.assertEqual(code, 0)
        self.assertIn("not a mapping", buf.getvalue())

    def test_frontmatter_that_parses_to_a_bare_scalar_never_fails_the_caller(self):
        self._write("---\njust a string\n---\n\nBody.\n")
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, _ = self.run_main(["sync-story-doc", "--artifacts-root", self.dir,
                                "--story", "E001-S01-003", "--status", "done"])
        self.assertEqual(code, 0)
        self.assertIn("not a mapping", buf.getvalue())

    def test_frontmatter_with_invalid_yaml_never_fails_the_caller(self):
        self._write("---\nkey: [unclosed\n---\n\nBody.\n")
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, _ = self.run_main(["sync-story-doc", "--artifacts-root", self.dir,
                                "--story", "E001-S01-003", "--status", "done"])
        self.assertEqual(code, 0)
        self.assertIn("does not parse as YAML", buf.getvalue())


class TestAdrRegister(TestLayoutResolution):
    # TestLayoutResolution supplies the node tree but NOT run_main -- every class
    # extending it defines its own (see TestSetFieldTyping above).
    def run_main(self, argv):
        buf = io.StringIO()
        code = 0
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        return code, buf.getvalue()

    def test_numbers_are_unique_across_repeated_reservations(self):
        seen = []
        for slug in ("a", "b", "c"):
            code, out = self.run_main(["adr-reserve", "--state-root", self.root,
                                  "--epic", "E001", "--slug", slug])
            self.assertEqual(code, 0)
            seen.extend(out.split())
        self.assertEqual(len(set(seen)), 3, f"collision in {seen}")
        self.assertEqual(seen, ["0001", "0002", "0003"])

    def test_a_batch_reserves_a_contiguous_range(self):
        _, out = self.run_main(["adr-reserve", "--state-root", self.root, "--epic", "E001",
                           "--slug", "batch", "--count", "3"])
        self.assertEqual(out.split(), ["0001", "0002", "0003"])

    def test_in_flight_reservations_are_visible_before_any_file_exists(self):
        """A directory listing shows who FINISHED. Only a register knows who is in flight."""
        self.run_main(["adr-reserve", "--state-root", self.root, "--epic", "E001", "--slug", "x"])
        _, cal = pm.load_adr_register(self.root)
        self.assertEqual(cal["reserved"][0]["number"], 1)
        self.assertEqual(cal["reserved"][0]["slug"], "x")

    def test_malformed_reserved_field_is_refused_not_silently_repaired(self):
        """Unlike a malformed `next` (recoverable), a malformed `reserved` must
        refuse loudly: silently replacing it with [] would hide who is already
        in flight, which is the one thing this register exists to preserve."""
        with open(pm.adr_register_path(self.root), "w") as f:
            f.write("next: 1\nreserved: not-a-list\n")
        buf = io.StringIO()
        with redirect_stderr(buf):
            code, out = self.run_main(["adr-reserve", "--state-root", self.root,
                                       "--epic", "E001", "--slug", "x"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        err = buf.getvalue()
        self.assertIn("reserved", err)
        self.assertIn("malformed", err)


class TestRuntimeChoices(TestLayoutResolution):
    """T-RC: runtime argparse choices include codex and copilot."""

    def run_main(self, argv):
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        try:
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, out_buf.getvalue() + err_buf.getvalue()

    def test_codex_is_a_valid_runtime_choice(self):
        # set-actual with --runtime codex but no tokens — should fail for a
        # different reason than "invalid choice", proving codex is accepted
        code, out = self.run_main([
            "set-actual", "--state-root", self.root, "--node", "story",
            "--story", "E001-S01-003", "--runtime", "codex",
            "--elapsed-hours", "1.0", "--man-hours", "4.0", "--hitl-hours", "0.2",
            "--no-calibrate",
        ])
        # exit 0 or 2 (usage error about tokens), never 2 with "invalid choice"
        self.assertNotIn("invalid choice", out)

    def test_copilot_is_a_valid_runtime_choice(self):
        code, out = self.run_main([
            "set-actual", "--state-root", self.root, "--node", "story",
            "--story", "E001-S01-003", "--runtime", "copilot",
            "--elapsed-hours", "1.0", "--man-hours", "4.0", "--hitl-hours", "0.2",
            "--no-calibrate",
        ])
        self.assertNotIn("invalid choice", out)

    def test_invalid_runtime_rejected(self):
        code, out = self.run_main([
            "set-actual", "--state-root", self.root, "--node", "story",
            "--story", "E001-S01-003", "--runtime", "github-copilot",
            "--elapsed-hours", "1.0",
        ])
        self.assertEqual(code, 2)
        self.assertIn("invalid choice", out)

    def test_codex_is_valid_runtime_choice_for_verify(self):
        code, out = self.run_main([
            "verify", "--state-root", self.root, "--scope", "story",
            "--story", "E001-S01-003", "--runtime", "codex",
        ])
        self.assertNotIn("invalid choice", out)

    def test_copilot_is_valid_runtime_choice_for_verify(self):
        code, out = self.run_main([
            "verify", "--state-root", self.root, "--scope", "story",
            "--story", "E001-S01-003", "--runtime", "copilot",
        ])
        self.assertNotIn("invalid choice", out)

    def test_openai_models_in_token_rates(self):
        for model in ("codex-1", "gpt-5", "gpt-5.4",
                      "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"):
            self.assertIn(model, pm.TOKEN_RATES, f"{model} missing from TOKEN_RATES")
            self.assertEqual(
                set(pm.TOKEN_RATES[model].keys()), set(pm.TOKEN_CLASSES),
                f"{model} missing a TOKEN_CLASSES key"
            )


class TestModelMismatch(TestLayoutResolution):
    """T-MM: model mismatch annotation in set-actual, verify, and calibration show."""

    def run_main(self, argv):
        import io
        from contextlib import redirect_stdout, redirect_stderr
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        try:
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, out_buf.getvalue() + err_buf.getvalue()

    def _write_story_with_estimate_model(self, model: str):
        p = pm.story_file(self.root, "E001-S01-003")
        with open(p, "w") as f:
            f.write(
                f"key: 'E001-S01-003'\nepic: 'E001'\nsprint: 'S01'\nstatus: review\n"
                f"estimate:\n  model: {model}\n"
            )

    def test_set_actual_notes_model_mismatch(self):
        self._write_story_with_estimate_model("claude-opus-5")
        code, out = self.run_main([
            "set-actual", "--state-root", self.root, "--node", "story",
            "--story", "E001-S01-003", "--runtime", "codex", "--no-calibrate",
            "--elapsed-hours", "2.0", "--man-hours", "8.0", "--hitl-hours", "0.5",
            "--tokens-input", "100", "--tokens-output", "20", "--tokens-cache-read", "300",
            "--model", "gpt-5.6-terra",
        ])
        self.assertEqual(code, 0)
        self.assertIn("model mismatch", out)
        self.assertIn("claude-opus-5", out)
        self.assertIn("gpt-5.6-terra", out)

    def test_set_actual_no_mismatch_note_when_models_match(self):
        self._write_story_with_estimate_model("gpt-5.6-terra")
        code, out = self.run_main([
            "set-actual", "--state-root", self.root, "--node", "story",
            "--story", "E001-S01-003", "--runtime", "codex", "--no-calibrate",
            "--elapsed-hours", "2.0", "--man-hours", "8.0", "--hitl-hours", "0.5",
            "--tokens-input", "100", "--tokens-output", "20", "--tokens-cache-read", "300",
            "--model", "gpt-5.6-terra",
        ])
        self.assertEqual(code, 0)
        self.assertNotIn("model mismatch", out)

    def test_verify_warns_on_model_mismatch(self):
        p = pm.story_file(self.root, "E001-S01-003")
        with open(p, "w") as f:
            f.write(
                "key: 'E001-S01-003'\nepic: 'E001'\nsprint: 'S01'\nstatus: done\n"
                "estimate:\n  model: claude-opus-5\n"
                "actual:\n"
                "  elapsed_hours: 2.0\n  man_hours: 8.0\n  hitl_hours: 0.5\n"
                "  tokens_k:\n    input: 100\n    output: 20\n"
                "    cache_write: 0\n    cache_read: 300\n    total: 420\n"
                "  cost: 0.16\n  model: gpt-5.6-terra\n"
                "completion_evidence:\n  tests_passing: true\n"
            )
        code, out = self.run_main([
            "verify", "--state-root", self.root, "--scope", "story",
            "--story", "E001-S01-003", "--runtime", "codex",
        ])
        self.assertIn("WARN", out)
        self.assertIn("claude-opus-5", out)
        self.assertIn("gpt-5.6-terra", out)

    def test_calibration_show_warns_on_mixed_models(self):
        from ruamel.yaml import YAML as _YAML
        cal_path = os.path.join(self.root, "pm-calibration.yaml")
        cal = {
            "version": 2,
            "granularity": "story",
            "scope": {
                "standard": {
                    "elapsed_hours": {
                        "samples": [0.9, 1.1],
                        "models_seen": ["claude-opus-5", "gpt-5.6-terra"],
                    }
                }
            },
            "closure": {}, "orchestration": {}, "fix": {},
        }
        _yaml = _YAML()
        with open(cal_path, "w") as f:
            _yaml.dump(cal, f)
        code, out = self.run_main(["calibration", "--state-root", self.root, "show"])
        self.assertEqual(code, 0)
        self.assertIn("WARN", out)
        self.assertIn("mixed-model", out)


class TestCodexRuntime(TestLayoutResolution):
    """T-CX: --runtime codex enforcement in set-actual and verify."""

    def run_main(self, argv):
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        try:
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, out_buf.getvalue() + err_buf.getvalue()

    def _set(self, *extra):
        return self.run_main([
            "set-actual", "--state-root", self.root, "--node", "story",
            "--story", "E001-S01-003", "--runtime", "codex", "--no-calibrate",
            "--elapsed-hours", "2.0", "--man-hours", "8.0", "--hitl-hours", "0.5",
        ] + list(extra))

    def _verify(self, *extra):
        return self.run_main([
            "verify", "--state-root", self.root, "--scope", "story",
            "--story", "E001-S01-003", "--runtime", "codex",
        ] + list(extra))

    def test_tokens_na_forbidden_under_codex(self):
        code, out = self._set("--tokens-na")
        self.assertEqual(code, 2)
        self.assertIn("codex", out)

    def test_codex_requires_input_output_cache_read(self):
        # missing --tokens-cache-read
        code, out = self._set(
            "--tokens-input", "100", "--tokens-output", "20", "--model", "codex-1",
        )
        self.assertEqual(code, 2)
        self.assertIn("cache-read", out)

    def test_codex_cache_write_defaults_to_zero(self):
        # omitting --tokens-cache-write should succeed; cache_write stored as 0
        code, out = self._set(
            "--tokens-input", "100", "--tokens-output", "20",
            "--tokens-cache-read", "300", "--model", "codex-1",
        )
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        tk = node["actual"]["tokens_k"]
        self.assertEqual(int(tk["cache_write"]), 0)
        self.assertEqual(int(tk["total"]), 420)  # 100+20+0+300

    def test_codex_derives_cost_from_three_classes(self):
        code, out = self._set(
            "--tokens-input", "100", "--tokens-output", "20",
            "--tokens-cache-read", "300", "--model", "codex-1",
        )
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        # cost = (100*5 + 20*30 + 0*6.25 + 300*2.5) / 1000 = (500+600+0+750)/1000 = 1.85
        self.assertAlmostEqual(float(node["actual"]["cost"]), 1.85, places=2)

    def test_verify_fails_on_scalar_tokens_under_codex(self):
        # Write a node with scalar tokens_k (like TestVerifyRejectsScalarTokens does),
        # then verify under codex — scalar form must fail for codex just as for claude.
        f = pm.story_file(self.root, "E001-S01-003")
        y, node = pm.load_node(f)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        node["actual"] = {
            "elapsed_hours": 2.0, "man_hours": 8.0, "hitl_hours": 0.5,
            "tokens_k": 420, "cost": "N/A", "model": "codex-1",
        }
        pm.save_node(y, node, f)
        code, out = self._verify()
        self.assertEqual(code, 4)
        self.assertIn("not the per-class mapping", out)

    def test_verify_na_tokens_fails_under_codex(self):
        # Write tokens_k=N/A to a done node, then verify — N/A is forbidden under codex.
        f = pm.story_file(self.root, "E001-S01-003")
        y, node = pm.load_node(f)
        node["status"] = "done"
        node["completion_evidence"] = {"fix_iterations": 0}
        node["actual"] = {
            "elapsed_hours": 2.0, "man_hours": 8.0, "hitl_hours": 0.5,
            "tokens_k": "N/A", "cost": "N/A", "model": "codex-1",
        }
        pm.save_node(y, node, f)
        code, out = self._verify()
        self.assertEqual(code, 4)
        self.assertIn("N/A", out)


class TestCopilotRuntime(TestLayoutResolution):
    """T-CP: --runtime copilot enforcement in set-actual and verify."""

    def run_main(self, argv):
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        try:
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, out_buf.getvalue() + err_buf.getvalue()

    def _set(self, *extra):
        return self.run_main([
            "set-actual", "--state-root", self.root, "--node", "story",
            "--story", "E001-S01-003", "--runtime", "copilot", "--no-calibrate",
            "--elapsed-hours", "2.0", "--man-hours", "8.0", "--hitl-hours", "0.5",
        ] + list(extra))

    def _verify(self):
        return self.run_main([
            "verify", "--state-root", self.root, "--scope", "story",
            "--story", "E001-S01-003", "--runtime", "copilot",
        ])

    def test_tokens_na_forbidden_under_copilot(self):
        code, out = self._set("--tokens-na")
        self.assertEqual(code, 2)
        self.assertIn("copilot", out)

    def test_copilot_requires_input_and_output(self):
        # only input, no output
        code, out = self._set("--tokens-input", "150")
        self.assertEqual(code, 2)
        self.assertIn("--tokens-output", out)

    def test_copilot_stores_scalar_total(self):
        code, out = self._set("--tokens-input", "150", "--tokens-output", "50")
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        tk = node["actual"]["tokens_k"]
        # scalar, not a mapping
        self.assertFalse(hasattr(tk, "get"), f"expected scalar, got mapping: {tk}")
        self.assertEqual(int(tk), 200)  # 150 + 50

    def test_copilot_stores_cost_na(self):
        code, out = self._set("--tokens-input", "150", "--tokens-output", "50")
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertTrue(pm._is_na(node["actual"]["cost"]))

    def test_copilot_model_not_required(self):
        # no --model; should succeed (cost=N/A means no pricing needed)
        code, out = self._set("--tokens-input", "150", "--tokens-output", "50")
        self.assertEqual(code, 0, out)

    def test_verify_passes_with_scalar_tokens_and_na_cost_under_copilot(self):
        # Write a complete done node with scalar tokens_k and cost=N/A, then verify
        f = pm.story_file(self.root, "E001-S01-003")
        y, n = pm.load_node(f)
        n.setdefault("actual", {})
        n["actual"].update({
            "elapsed_hours": 2.0, "man_hours": 8.0, "hitl_hours": 0.5,
            "tokens_k": 200, "cost": "N/A",
        })
        n["status"] = "done"
        n.setdefault("completion_evidence", {})
        pm.save_node(y, n, f)
        code, out = self._verify()
        self.assertEqual(code, 0, out)

    def test_verify_rejects_na_tokens_k_under_copilot(self):
        f = pm.story_file(self.root, "E001-S01-003")
        y, n = pm.load_node(f)
        n.setdefault("actual", {})
        n["actual"].update({
            "elapsed_hours": 2.0, "man_hours": 8.0, "hitl_hours": 0.5,
            "tokens_k": "N/A", "cost": "N/A",
        })
        n["status"] = "done"
        n.setdefault("completion_evidence", {})
        pm.save_node(y, n, f)
        code, _ = self._verify()
        self.assertEqual(code, 4)


class TestUpdateIssue(IssueBase):
    def test_unknown_key_names_both_files(self):
        """Match resolve-issue: an unknown key is in neither file, and both are named."""
        code, _, err = self.update("BL-E001-042", "High")
        self.assertEqual(code, 3)
        self.assertIn("issues.yaml", err)
        self.assertIn("issues-resolved.yaml", err)

    def update(self, key, sev, *extra):
        return self.run_all(["update-issue", "--state-root", self.root, "--key", key,
                             "--severity", sev, *extra])

    def test_severity_actually_changes(self):
        """The assertion epic-closure §4's old 'promote via append-issue' never had:
        that path printed OK and changed nothing."""
        self.append("A", "001", "01", "Low")
        code, out, err = self.update("BL-E001-001", "High", "--note", "wider blast radius")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.load_open()["backlog"][0]["severity"], "High")
        ev = self.events("issue_updated")[-1]
        self.assertEqual((ev["from"], ev["to"], ev["note"]), ("Low", "High", "wider blast radius"))

    def _same_severity_noop(self, *extra):
        """Update BL-E001-001 to the severity it already has; assert no write and no event."""
        self.append("A", "001", "01", "Low")

        def read(p):
            with open(p, "rb") as fh:
                return fh.read()
        issues, events = read(self.issues), read(pm.events_path(self.root))
        code, out, err = self.update("BL-E001-001", "Low", *extra)
        self.assertEqual(code, 0, err)
        self.assertEqual(read(self.issues), issues)
        self.assertEqual(read(pm.events_path(self.root)), events)
        return out

    def test_same_severity_is_a_noop(self):
        """It used to save the file, log an issue_updated event with from == to, and print
        `severity Low -> Low`: a change record for a change that did not happen."""
        self.assertEqual(self._same_severity_noop(),
                         "OK update-issue BL-E001-001 severity Low unchanged\n")

    def test_same_severity_with_a_note_says_the_note_was_not_recorded(self):
        # Final review M5: the note lives only in the issue_updated event, which a no-op does
        # not write, so the caller's "why" was dropped with no hint that it had been.
        self.assertEqual(self._same_severity_noop("--note", "no change"),
                         "OK update-issue BL-E001-001 severity Low unchanged (note not recorded)\n")

    def test_resolved_key_exits_2_naming_resolution(self):
        self.append("A")
        self.run_all(["resolve-issue", "--state-root", self.root, "--key", "BL-E001-001",
                      "--resolution", "obsolete", "--note", "gone"])
        code, _, err = self.update("BL-E001-001", "High")
        self.assertEqual(code, 2)
        self.assertIn("obsolete", err)

    def test_unknown_key_exits_3(self):
        self.assertEqual(self.update("BL-E001-077", "High")[0], 3)

    def test_invalid_severity_is_a_usage_error(self):
        self.append("A")
        self.assertEqual(self.update("BL-E001-001", "Severe")[0], 2)

    def test_key_duplicated_in_open_file_is_refused(self):
        self.append("A")
        y, data = pm._load(self.issues)
        from ruamel.yaml.comments import CommentedMap
        data["backlog"].append(CommentedMap(data["backlog"][0]))
        pm._atomic_dump(y, data, self.issues)
        code, _, err = self.update("BL-E001-001", "High")
        self.assertEqual(code, 2)
        self.assertIn("1i", err)

    def test_key_in_both_files_is_refused_as_resolved(self):
        """Resolve's crash window leaves a key in both files; it is resolved, so an
        update must be refused, not applied to the stale open copy."""
        self.append("A", "001", "01", "Low")
        with _dump_failing_on(2):
            with self.assertRaises(OSError):
                pm.main(["resolve-issue", "--state-root", self.root, "--key",
                         "BL-E001-001", "--resolution", "obsolete", "--note", "x"])
        self.assertEqual(self.open_keys(), ["BL-E001-001"])       # premise: both files
        code, _, err = self.update("BL-E001-001", "High")
        self.assertEqual(code, 2)
        self.assertIn("obsolete", err)
        self.assertEqual(self.load_open()["backlog"][0]["severity"], "Low")


class TestListIssuesLifecycle(IssueBase):
    def ls(self, *extra):
        code, out, err = self.run_all(["list-issues", "--state-root", self.root,
                                       "--format", "json", *extra])
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_resolved_flag_and_resolution_filter(self):
        self.append("A")
        self.append("B", "001", "02")
        self.run_all(["resolve-issue", "--state-root", self.root, "--key", "BL-E001-001",
                      "--resolution", "obsolete", "--note", "x"])
        self.assertEqual([i["key"] for i in self.ls()], ["BL-E001-002"])
        self.assertEqual([i["key"] for i in self.ls("--resolved")], ["BL-E001-001"])
        self.assertEqual(self.ls("--resolved", "--resolution", "fixed"), [])

    def test_all_returns_both_lists(self):
        self.append("A")
        self.append("B", "001", "02")
        self.run_all(["resolve-issue", "--state-root", self.root, "--key", "BL-E001-002",
                      "--resolution", "obsolete", "--note", "x"])
        data = self.ls("--all")
        self.assertEqual([i["key"] for i in data["open"]], ["BL-E001-001"])
        self.assertEqual([i["key"] for i in data["resolved"]], ["BL-E001-002"])

    def test_flag_combinations_that_make_no_sense_exit_2(self):
        for argv in (["--resolution", "fixed"], ["--resolved", "--status", "backlog"]):
            code, _, _ = self.run_all(["list-issues", "--state-root", self.root,
                                       "--format", "json", *argv])
            self.assertEqual(code, 2, argv)
        code, _, _ = self.run_all(["list-issues", "--state-root", self.root, "--all"])
        self.assertEqual(code, 2, "--all is JSON only")

    def test_origin_archived_follows_the_epic_directory(self):
        self.append("Later thing", "005", "01", "Low", "qa (Q-1)")
        self.assertFalse(self.ls()[0]["origin_archived"])
        self.assertEqual(self.run_all(["archive-epic", "--state-root", self.root,
                                       "--epic", "E005"])[0], 0)
        self.assertTrue(self.ls()[0]["origin_archived"])
        code, out, _ = self.run_all(["list-issues", "--state-root", self.root])
        self.assertIn("archived", out)

    def test_status_filter(self):
        self.append("A")
        y, data = pm._load(self.issues)      # a scheduled item (promote lands in Task 8)
        data["backlog"][0]["status"] = "scheduled"
        pm._atomic_dump(y, data, self.issues)
        self.append("B", "001", "02")
        self.assertEqual([i["key"] for i in self.ls("--status", "scheduled")], ["BL-E001-001"])
        self.assertEqual([i["key"] for i in self.ls("--status", "backlog")], ["BL-E001-002"])

    def test_all_on_missing_state_root_creates_nothing(self):
        ghost = os.path.join(self.d, "nope")
        code, out, _ = self.run_all(["list-issues", "--state-root", ghost, "--all",
                                     "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"open": [], "resolved": []})
        self.assertFalse(os.path.exists(ghost))

    def test_all_on_a_state_root_without_issue_files_creates_nothing(self):
        code, out, _ = self.run_all(["list-issues", "--state-root", self.root, "--all",
                                     "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"open": [], "resolved": []})
        self.assertFalse(os.path.exists(self.issues + ".lock"),
                         "a read-only command left a lock file behind")

    def test_all_refuses_a_malformed_list(self):
        with open(self.issues, "w", encoding="utf-8") as fh:
            fh.write("backlog: oops\n")
        code, _, _ = self.run_all(["list-issues", "--state-root", self.root, "--all",
                                   "--format", "json"])
        self.assertEqual(code, 2)


class TestListAllConsistency(unittest.TestCase):
    """--all reads both files under issues_lock: a concurrent resolve can never show
    a key in both lists or in neither."""
    N = 8

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.root = os.path.join(self.d, "state")
        _build_issue_tree(self.root)
        for i in range(1, self.N + 1):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(pm.main(["append-issue", "--state-root", self.root, "--epic",
                                          "001", "--title", f"t{i}", "--source", "qa",
                                          "--severity", "Low"]), 0)

    def test_snapshots_are_consistent_under_concurrent_resolves(self):
        import subprocess
        procs = [subprocess.Popen([sys.executable, SCRIPT, "resolve-issue", "--state-root",
                                   self.root, "--key", f"BL-E001-{i:03d}", "--resolution",
                                   "obsolete", "--note", "x"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for i in range(1, self.N + 1)]
        snapshots = []
        for _ in range(15):
            r = subprocess.run([sys.executable, SCRIPT, "list-issues", "--state-root",
                                self.root, "--all", "--format", "json"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            snapshots.append(json.loads(r.stdout))
        for p in procs:
            p.communicate(timeout=120)
        for s in snapshots:
            o = {i["key"] for i in s["open"]}
            r = {i["key"] for i in s["resolved"]}
            self.assertFalse(o & r, "key in both lists")
            self.assertEqual(len(o | r), self.N, "a key vanished")


class TestEstimateCores(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_compute_story_estimate_raises_instead_of_exiting(self):
        path = pm.story_file(self.root, "E001-S01-003")
        with open(path, encoding="utf-8") as fh:
            before = fh.read()
        _, node = pm.load_node(path)
        with self.assertRaises(pm.PMError) as cm:
            pm.compute_story_estimate(self.root, node, "standard", "no-such-model", None)
        self.assertEqual(cm.exception.code, 2)
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), before, "core must never save")

    def test_compute_story_estimate_fills_node_in_memory(self):
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        applied = pm.compute_story_estimate(self.root, node, "simple", pm.DEFAULT_ESTIMATE_MODEL, None)
        self.assertIn("man_hours", applied)
        self.assertIn("cost", node["estimate"])
        self.assertEqual(node["classification"], "simple")

    def test_rollup_parent_estimate_raises_for_missing_sprint(self):
        with self.assertRaises(pm.PMError) as cm:
            pm.rollup_parent_estimate(self.root, "E001", "S09", pm.DEFAULT_ESTIMATE_MODEL, None)
        self.assertEqual(cm.exception.code, 3)

    def test_rollup_parent_estimate_raises_when_nothing_to_roll_up(self):
        with self.assertRaises(pm.PMError) as cm:
            pm.rollup_parent_estimate(self.root, "E001", "S01", pm.DEFAULT_ESTIMATE_MODEL, None)
        self.assertEqual(cm.exception.code, 2)

    def test_cli_unknown_model_still_exits_2_and_writes_nothing(self):
        path = pm.story_file(self.root, "E001-S01-003")
        with open(path, encoding="utf-8") as fh:
            before = fh.read()
        code, _ = self.run_main(["estimate-story", "--state-root", self.root, "--story",
                                 "E001-S01-003", "--classification", "simple",
                                 "--model", "no-such-model"])
        self.assertEqual(code, 2)
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), before)

    def test_compute_story_estimate_leaves_node_untouched_when_it_raises(self):
        path = pm.story_file(self.root, "E001-S01-003")
        _, node = pm.load_node(path)
        pm.compute_story_estimate(self.root, node, "simple", pm.DEFAULT_ESTIMATE_MODEL, None)
        before_est = json.dumps(node["estimate"], sort_keys=True, default=str)
        before_cls = node["classification"]
        with self.assertRaises(pm.PMError):
            pm.compute_story_estimate(self.root, node, "complex", "no-such-model", None)
        self.assertEqual(json.dumps(node["estimate"], sort_keys=True, default=str), before_est,
                         "a failed estimate must not half-overwrite the previous one")
        self.assertEqual(node["classification"], before_cls)


class TestStoryDocInit(TestLayoutResolution):
    def setUp(self):
        super().setUp()
        self.arts = os.path.join(self.d, "impl")
        self.doc = os.path.join(self.arts, "epic-001", "sprint-01", "stories", "E001-S01-003.md")

    def run_all(self, argv):
        out, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, out.getvalue(), err.getvalue()

    def init(self):
        return self.run_all(["story-doc-init", "--state-root", self.root,
                             "--artifacts-root", self.arts, "--story", "E001-S01-003"])

    def test_creates_skeleton_from_the_state_node(self):
        code, out, err = self.init()
        self.assertEqual(code, 0, err)
        self.assertIn("created", out)
        with open(self.doc, encoding="utf-8") as fh:
            text = fh.read()
        self.assertTrue(text.startswith("---\n"))
        meta = pm._yaml().load(text.split("---\n")[1])
        self.assertEqual(meta["key"], "E001-S01-003")
        self.assertEqual(meta["status"], "review")
        self.assertIn("## Acceptance Criteria", text)
        # the node has no title and no classification: the skeleton falls back to the story
        # key for both the title and the heading, and to `standard`
        self.assertEqual(meta["title"], "E001-S01-003")
        self.assertEqual(meta["classification"], "standard")
        self.assertIn("---\n\n# E001-S01-003\n\n", text)

    def test_a_title_with_a_quote_and_a_colon_survives_the_frontmatter(self):
        title = "Don't split: the user's cache: v2"
        code, _, err = self.run_all(["set-field", "--state-root", self.root, "--story",
                                     "E001-S01-003", "--field", "title", "--value", title])
        self.assertEqual(code, 0, err)
        code, out, err = self.init()
        self.assertEqual(code, 0, err)
        with open(self.doc, encoding="utf-8") as fh:
            text = fh.read()
        from ruamel.yaml import YAML
        meta = YAML(typ="safe", pure=True).load(text.split("---\n")[1])   # not pm's own loader
        self.assertEqual(meta["title"], title)
        self.assertIn(f"---\n\n# {title}\n\n", text)

    def test_existing_document_is_left_untouched(self):
        os.makedirs(os.path.dirname(self.doc))
        with open(self.doc, "w", encoding="utf-8") as fh:
            fh.write("hand written\n")
        code, out, _ = self.init()
        self.assertEqual(code, 0)
        self.assertIn("exists", out)
        with open(self.doc, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "hand written\n")

    def test_missing_state_node_exits_3(self):
        code, _, _ = self.run_all(["story-doc-init", "--state-root", self.root,
                                   "--artifacts-root", self.arts, "--story", "E001-S01-099"])
        self.assertEqual(code, 3)

    def test_must_not_exist_refuses_an_existing_document(self):
        os.makedirs(os.path.dirname(self.doc))
        open(self.doc, "w").close()
        with self.assertRaises(pm.PMError) as cm:
            pm.init_story_doc(self.root, self.arts, "E001-S01-003", must_not_exist=True)
        self.assertEqual(cm.exception.code, 2)

    def test_context_and_acceptance_lines(self):
        pm.init_story_doc(self.root, self.arts, "E001-S01-003",
                          context_md="## Context\n\nfrom BL-E001-002",
                          ac_lines=["The deferred finding BL-E001-002 is resolved: X"])
        with open(self.doc, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("## Context\n\nfrom BL-E001-002", text)
        self.assertIn("- The deferred finding BL-E001-002 is resolved: X", text)
        self.assertLess(text.index("## Context"), text.index("## Acceptance Criteria"))

    def test_failed_write_leaves_no_temp_file_and_no_document(self):
        with mock.patch.object(pm.os, "replace", side_effect=OSError("injected")), \
             mock.patch.object(pm.os, "link", side_effect=OSError("injected")):
            with self.assertRaises(OSError):
                pm.init_story_doc(self.root, self.arts, "E001-S01-003")
        stories = os.path.dirname(self.doc)
        self.assertFalse(os.path.exists(self.doc))
        self.assertEqual([n for n in os.listdir(stories) if n.endswith(".tmp")], [],
                         "a failed write left a temp file behind")


def _tree_snapshot(top):
    snap = {}
    for dp, _, files in os.walk(top):
        for f in files:
            if f.endswith(".lock"):
                continue
            p = os.path.join(dp, f)
            with open(p, "rb") as fh:
                snap[os.path.relpath(p, top)] = fh.read()
    return snap


def _wait_until_blocked_on(proc, lock_path, what="child", hang_guard=30.0):
    """Return once `proc` is SEEN blocked on `lock_path`'s flock; fail if it exits first.

    The verdict comes from one of two positive events, never from elapsed time:
    - `proc` appears in /proc/locks as a blocked waiter -- a `->` line carrying its pid on
      `lock_path`'s inode -- so it is honoring the lock, and this returns;
    - `proc` exits first, so it never waited and the lock was not honored: AssertionError.
    A fixed sleep can only fail when an unlocked writer happens to finish inside the window,
    so on a loaded runner it passes having checked nothing. `hang_guard` only stops a wedged
    child from hanging the suite: tripping it kills the child and fails loudly; it never
    passes a test.

    Linux-only -- decorate callers with
    `@unittest.skipUnless(os.path.exists("/proc/locks"), ...)`. A waiter's line reads
    `25: -> FLOCK  ADVISORY  WRITE <pid> <maj>:<min>:<inode> 0 EOF`; the inode is matched,
    not the device, whose numbering is filesystem-specific. Start `proc` directly (no shell
    or wrapper), so `proc.pid` is the process that takes the lock."""
    import time
    ino, pid = str(os.stat(lock_path).st_ino), str(proc.pid)
    deadline = time.monotonic() + hang_guard
    while True:
        if proc.poll() is not None:
            out, err = proc.communicate()
            raise AssertionError(f"{what} (pid {pid}) exited {proc.returncode} without waiting "
                                 f"on {lock_path} -- the lock was not honored\n"
                                 f"stdout: {out!r}\nstderr: {err!r}")
        with open("/proc/locks", encoding="ascii", errors="replace") as fh:
            for line in fh:
                f = line.split()
                if len(f) > 6 and f[1] == "->" and f[5] == pid and f[6].rsplit(":", 1)[-1] == ino:
                    return
        if time.monotonic() > deadline:
            proc.kill()
            proc.communicate()
            raise AssertionError(f"hang guard: {what} (pid {pid}) neither exited nor blocked on "
                                 f"{lock_path} within {hang_guard}s")
        time.sleep(0.01)


class TestPromoteIssue(IssueBase):
    def promote(self, *keys, epic="001", sprint="02", cls="standard", extra=()):
        argv = ["promote-issue", "--state-root", self.root, "--artifacts-root", self.arts]
        for k in keys:
            argv += ["--key", k]
        argv += ["--epic", epic, "--sprint", sprint, "--classification", cls, *extra]
        return self.run_all(argv)

    def story(self, key="E001-S02-001"):
        return pm.load_node(pm.story_file(self.root, key))[1]

    def test_promote_creates_estimated_story_and_schedules_item(self):
        self.append("Replace linear scan", "001", "01", "Medium")
        code, out, err = self.promote("BL-E001-001")
        self.assertEqual(code, 0, err)
        self.assertIn("E001-S02-001", out)
        node = self.story()
        self.assertEqual(node["status"], "backlog")
        self.assertEqual(list(node["resolves"]), ["BL-E001-001"])
        self.assertIn("cost", node["estimate"])
        self.assertIn("estimate", pm.load_node(pm.sprint_file(self.root, "E001", "S02"))[1])
        self.assertIn("estimate", pm.load_node(pm.epic_file(self.root, "E001"))[1])
        item = self.load_open()["backlog"][0]
        self.assertEqual((item["status"], item["story"]), ("scheduled", "E001-S02-001"))
        with open(pm.story_doc_path(self.arts, "E001-S02-001"), encoding="utf-8") as fh:
            doc = fh.read()
        self.assertIn("## Context", doc)
        self.assertIn("- The deferred finding BL-E001-001 is resolved: Replace linear scan", doc)
        ev = self.events("issue_scheduled")
        self.assertEqual((ev[-1]["key"], ev[-1]["story"]), ("BL-E001-001", "E001-S02-001"))
        self.assertNotIn("via", ev[-1])     # repair's link carries via; promote's shape is unchanged
        self.assert_invariants()

    def test_refusals_write_nothing(self):
        self.append("A")
        cases = [
            (dict(sprint="01"), 2),                               # sprint in-progress
            (dict(extra=("--model", "no-such-model")), 2),
            (dict(extra=("--token-rates", "{")), 2),
            (dict(sprint="09"), 3),                               # sprint missing
            (dict(epic="042", sprint="01"), 3),                   # epic missing
        ]
        for kwargs, want in cases:
            before = _tree_snapshot(self.d)
            code, _, err = self.promote("BL-E001-001", **kwargs)
            self.assertEqual(code, want, (kwargs, err))
            self.assertEqual(_tree_snapshot(self.d), before, kwargs)
        before = _tree_snapshot(self.d)
        self.assertEqual(self.promote("BL-E001-999")[0], 2)                   # not open
        self.assertEqual(self.promote("BL-E001-001", "BL-E001-001x")[0], 2)   # bad key
        self.assertEqual(_tree_snapshot(self.d), before)

    def test_two_keys_need_a_title(self):
        self.append("A")
        self.append("B", "001", "02")
        self.assertEqual(self.promote("BL-E001-001", "BL-E001-002")[0], 2)
        code, _, err = self.promote("BL-E001-001", "BL-E001-002", extra=("--title", "Batch"))
        self.assertEqual(code, 0, err)
        self.assertEqual(list(self.story()["resolves"]), ["BL-E001-001", "BL-E001-002"])
        self.assertEqual({i["status"] for i in self.load_open()["backlog"]}, {"scheduled"})
        self.assert_invariants()

    def test_archived_epic_is_refused(self):
        self.append("Later", "005", "01", "Low", "qa (Q-1)")
        self.run_all(["archive-epic", "--state-root", self.root, "--epic", "E005"])
        before = _tree_snapshot(self.d)
        code, _, err = self.promote("BL-E005-001", epic="005", sprint="01")
        self.assertEqual(code, 2)
        self.assertIn("archived", err)
        self.assertEqual(_tree_snapshot(self.d), before)

    def test_already_scheduled_is_refused_naming_the_story(self):
        self.append("A")
        self.promote("BL-E001-001")
        code, _, err = self.promote("BL-E001-001")
        self.assertEqual(code, 2)
        self.assertIn("E001-S02-001", err)

    def test_live_foreign_lock_refuses_own_lock_allows(self):
        self.append("A")
        self.run_all(["set-lock", "--state-root", self.root, "--epic", "E001",
                      "--session-id", "other"])
        before = _tree_snapshot(self.d)
        code, _, err = self.promote("BL-E001-001")
        self.assertEqual(code, 5, err)
        self.assertIn("epic E001 is LOCKED by other", err)
        self.assertEqual(_tree_snapshot(self.d), before)          # M14(c): exit 5 writes nothing
        code, _, err = self.promote("BL-E001-001", extra=("--session-id", "other"))
        self.assertEqual(code, 0, err)

    def _set_epic_lock(self, lock_yaml):
        """Give epic E001 a hand-written `_lock` -- a deliberately built state (no verb writes
        a malformed or back-dated lock), keeping the rest of the node as the verbs left it."""
        from ruamel.yaml import YAML
        with pm.epic_node_lock(self.root, "E001"):       # every epic.yaml write holds it
            p = pm.epic_file(self.root, "E001")
            y, n = pm.load_node(p)
            n["_lock"] = YAML().load(lock_yaml)
            pm.save_node(y, n, p)

    def test_foreign_lock_verdict_matches_check_lock(self):
        """For a WELL-FORMED lock, promote takes check-lock's verdict (carryover 16) -- its
        TTL semantics, including ttl_minutes 0 as always stale."""
        now = pm._now_iso()
        cases = {  # name: (lock, check-lock's verdict -- pinned, so check-lock cannot drift)
            "live":     (f"session_id: other\nclaimed_at: '{now}'\nttl_minutes: 30\n", 5),
            "stale":    ("session_id: other\nclaimed_at: '2020-01-01T00:00:00Z'\n"
                         "ttl_minutes: 1\n", 0),
            "ttl-zero": (f"session_id: other\nclaimed_at: '{now}'\nttl_minutes: 0\n", 0),
        }
        for i, (name, (lock, verdict)) in enumerate(cases.items(), start=1):
            self.append(f"L{i}")
            self._set_epic_lock(lock)
            check, _, _ = self.run_all(["check-lock", "--state-root", self.root, "--epic",
                                        "E001", "--session-id", "me"])
            self.assertEqual(check, verdict, name)
            before = _tree_snapshot(self.d)
            code, _, err = self.promote(f"BL-E001-{i:03d}")
            self.assertEqual(code, check, (name, err))
            if code == 5:
                self.assertEqual(_tree_snapshot(self.d), before, name)

    def test_unevaluable_foreign_lock_refuses_and_writes_nothing(self):
        """Ruling 24: promote is a write verb, so a foreign lock it cannot evaluate refuses
        (exit 5) -- even where check-lock, a read, reports it free -- and writes nothing."""
        now = pm._now_iso()
        cases = {  # name: (lock, check-lock's verdict, pinned; None where check-lock raises)
            "not-a-mapping":   ("'just-a-string'\n", 0),
            "no-timestamp":    ("session_id: other\nttl_minutes: 30\n", 0),
            "bad-timestamp":   ("session_id: other\nclaimed_at: 'not-a-time'\nttl_minutes: 30\n", 0),
            "naive-timestamp": ("session_id: other\nclaimed_at: '2026-01-01T00:00:00'\n"
                                "ttl_minutes: 30\n", None),
            "no-session":      (f"claimed_at: '{now}'\nttl_minutes: 30\n", 5),
            "non-integer-ttl": (f"session_id: other\nclaimed_at: '{now}'\nttl_minutes: abc\n", None),
        }
        self.append("A")
        for name, (lock, verdict) in cases.items():
            self._set_epic_lock(lock)
            if verdict is not None:
                check, _, _ = self.run_all(["check-lock", "--state-root", self.root, "--epic",
                                            "E001", "--session-id", "me"])
                self.assertEqual(check, verdict, name)             # check-lock is unchanged
            before = _tree_snapshot(self.d)
            code, _, err = self.promote("BL-E001-001")
            self.assertEqual(code, 5, (name, err))
            self.assertIn("epic E001", err, name)
            self.assertIn("cannot be evaluated", err, name)
            self.assertIn("clear-lock", err, name)
            self.assertEqual(_tree_snapshot(self.d), before, name)
        # the refusal does not reach a lock that names THIS session: set-lock re-claims it too
        self._set_epic_lock("session_id: me\nttl_minutes: 30\n")
        code, _, err = self.promote("BL-E001-001", extra=("--session-id", "me"))
        self.assertEqual(code, 0, err)

    def test_a_padded_holder_session_is_foreign(self):
        """Ruling F2: the holder is compared to the caller EXACTLY, as check-lock and set-lock
        compare it. promote used to strip a hand-edited 'me ' and read it as its own -- then
        wave an otherwise unevaluable lock through."""
        now = pm._now_iso()
        self.append("A")
        me = ("--session-id", "me")
        # well-formed and live: foreign to `me`, and check-lock's verdict agrees
        self._set_epic_lock(f"session_id: 'me '\nclaimed_at: '{now}'\nttl_minutes: 30\n")
        check, _, _ = self.run_all(["check-lock", "--state-root", self.root, "--epic", "E001",
                                    "--session-id", "me"])
        self.assertEqual(check, 5)
        before = _tree_snapshot(self.d)
        code, _, err = self.promote("BL-E001-001", extra=me)
        self.assertEqual(code, 5, err)
        self.assertEqual(_tree_snapshot(self.d), before)
        # no claimed_at: foreign, so unevaluable -- stripping read it as own and wrote the story
        self._set_epic_lock("session_id: 'me '\nttl_minutes: 30\n")
        before = _tree_snapshot(self.d)
        code, _, err = self.promote("BL-E001-001", extra=me)
        self.assertEqual(code, 5, err)
        self.assertIn("cannot be evaluated (claimed_at is missing or unparseable)", err)
        self.assertEqual(_tree_snapshot(self.d), before)
        # only the presence check strips: a whitespace-only holder is no session_id at all
        self._set_epic_lock(f"session_id: '  '\nclaimed_at: '{now}'\nttl_minutes: 30\n")
        before = _tree_snapshot(self.d)
        code, _, err = self.promote("BL-E001-001", extra=me)
        self.assertEqual(code, 5, err)
        self.assertIn("cannot be evaluated (no session_id)", err)
        self.assertEqual(_tree_snapshot(self.d), before)

    def test_allocation_skips_an_artifact_only_document(self):
        self.append("A")
        stories = os.path.join(self.arts, "epic-001", "sprint-02", "stories")
        os.makedirs(stories)
        with open(os.path.join(stories, "E001-S02-001.md"), "w", encoding="utf-8") as fh:
            fh.write("an unrelated story nobody bootstrapped\n")
        code, out, err = self.promote("BL-E001-001")
        self.assertEqual(code, 0, err)
        self.assertIn("E001-S02-002", out)
        with open(os.path.join(stories, "E001-S02-001.md"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "an unrelated story nobody bootstrapped\n")

    def test_retry_resumes_a_promote_that_stopped_before_scheduling(self):
        self.append("A")
        self._crash_promote_before_scheduling()
        self.assertEqual(list(self.story()["resolves"]), ["BL-E001-001"])    # premise
        self.assertEqual(self.load_open()["backlog"][0]["status"], "backlog")
        code, out, err = self.promote("BL-E001-001")
        self.assertEqual(code, 0, err)
        self.assertIn("resumed", out)
        self.assertIsNone(pm.story_file(self.root, "E001-S02-002"), "no second story")
        self.assertEqual(self.load_open()["backlog"][0]["story"], "E001-S02-001")
        self.assert_invariants()

    def test_promote_never_writes_an_estimate_less_node(self):
        """Spec §6.1/§7: the node and its estimate land in ONE save. If the estimate fails
        after validation, no story node may be left on disk (it would have no estimate)."""
        self.append("A")
        with mock.patch.object(pm, "compute_story_estimate",
                               side_effect=pm.PMError(2, "injected")):
            code, _, err = self.promote("BL-E001-001")
        self.assertNotEqual(code, 0)
        self.assertIn("injected", err)
        self.assertIsNone(pm.story_file(self.root, "E001-S02-001"),
                          "a story node was written before its estimate")
        item = self.load_open()["backlog"][0]
        self.assertEqual(item["status"], "backlog")
        self.assertNotIn("story", item)
        self.assertFalse(os.path.exists(pm.story_doc_path(self.arts, "E001-S02-001")))

    def test_set_field_refuses_resolves(self):
        self.append("A")
        self.promote("BL-E001-001")
        code, _, err = self.run_all(["set-field", "--state-root", self.root, "--story",
                                     "E001-S02-001", "--field", "resolves", "--value", "x"])
        self.assertEqual(code, 2)
        self.assertIn("promote-issue", err)

    def test_key_in_both_files_is_refused_as_resolved(self):
        self.append("A")
        with _dump_failing_on(2):
            with self.assertRaises(OSError):
                pm.main(["resolve-issue", "--state-root", self.root, "--key", "BL-E001-001",
                         "--resolution", "obsolete", "--note", "x"])
        before = _tree_snapshot(self.d)
        code, _, err = self.promote("BL-E001-001")
        self.assertEqual(code, 2)
        self.assertIn("already resolved", err)
        self.assertEqual(_tree_snapshot(self.d), before)

    def test_list_issues_status_scheduled_sees_a_real_promotion(self):
        self.append("A")
        self.append("B", "001", "02")
        self.promote("BL-E001-001")
        code, out, err = self.run_all(["list-issues", "--state-root", self.root,
                                       "--status", "scheduled", "--format", "json"])
        self.assertEqual(code, 0, err)
        self.assertEqual([i["key"] for i in json.loads(out)], ["BL-E001-001"])

    @unittest.skipUnless(os.path.exists("/proc/locks"), "needs /proc/locks to see a flock waiter")
    def test_concurrent_resolve_cannot_orphan_a_promoted_story(self):
        """A resolve racing a promote must never leave an estimated story listing a resolved
        item: promote holds issues_lock from its item check through scheduling."""
        # The resolve starts inside promote's first roll-up. It must be SEEN blocked on
        # issues_lock there, and again at the second roll-up (batch B). A fixed wait window
        # passed without checking anything whenever an unlocked resolve was merely slower than
        # the window.
        import subprocess
        self.append("A")
        real_rollup = pm.rollup_parent_estimate
        lock = pm.issues_paths(self.root)[0] + ".lock"
        procs, failures = [], []

        def racing_rollup(*a, **kw):
            try:
                if not procs:
                    p = subprocess.Popen([sys.executable, SCRIPT, "resolve-issue", "--state-root",
                                          self.root, "--key", "BL-E001-001", "--resolution",
                                          "obsolete", "--note", "raced"],
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    procs.append(p)
                    self.addCleanup(p.kill)              # reaps on failure; no-op once done
                _wait_until_blocked_on(procs[0], lock, "resolve-issue")
            except AssertionError as e:
                failures.append(e)          # re-raised below, whatever promote does with it
                raise
            return real_rollup(*a, **kw)

        with mock.patch.object(pm, "rollup_parent_estimate", racing_rollup):
            try:
                code, out, err = self.promote("BL-E001-001")
            except AssertionError:
                pass
        if failures:
            raise failures[0]
        _, rerr = procs[0].communicate(timeout=30)
        self.assertEqual(code, 0, err)
        self.assertEqual(procs[0].returncode, 0, rerr.decode())
        self.assertEqual(list(self.story()["resolves"]), ["BL-E001-001"])
        self.assertEqual(self.resolved_keys(), ["BL-E001-001"])      # the resolve ran after
        self.assertEqual(self.load_resolved()["resolved"][0].get("story"), "E001-S02-001")
        self.assert_invariants()

    @unittest.skipUnless(os.path.exists("/proc/locks"), "needs /proc/locks to see a flock waiter")
    def test_promote_holds_the_epic_lock_through_both_rollups(self):
        # Spec §2.4 step 3: promote rolls up the sprint, then the epic, while it still holds
        # epic_node_lock, so no other epic.yaml writer can interleave with those saves. A real
        # `set-field --epic` subprocess takes the same lock (batch D1). It is launched from inside
        # the FIRST roll-up.
        # - It must be SEEN blocked on the epic lock as each roll-up starts.
        # - It must still be waiting, with its field absent, after each roll-up's save.
        # - Its write then lands only after promote releases the lock, beside the epic roll-up's
        #   estimate, which that write must leave intact.
        import subprocess
        self.append("A")
        real_rollup = pm.rollup_parent_estimate
        lock = pm.epic_lock_path(self.root, "E001")
        procs, failures, after, holds = [], [], [], []

        def watched_rollup(state_root, epic, sprint, *a, **kw):
            level = f"sprint {sprint}" if sprint else "epic"
            try:
                # The hold promote took must be the one still held at each roll-up. A release
                # and retake between them opens a NEW lock file object, so `is` catches it
                # deterministically, whether or not the waiting set-field won the gap. Keeping
                # the reference in `holds` stops the old object from being freed and reused.
                holds.append((pm._EPIC_NODE_LOCK["fh"], pm._EPIC_NODE_LOCK["depth"]))
                self.assertGreaterEqual(holds[-1][1], 1, f"no epic lock held at the {level} roll-up")
                self.assertIs(holds[-1][0], holds[0][0],
                              f"the epic lock was released and retaken before the {level} roll-up")
                if not procs:
                    p = subprocess.Popen([sys.executable, SCRIPT, "set-field", "--state-root",
                                          self.root, "--epic", "001", "--field", "notes.b9",
                                          "--value", "landed"],
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    procs.append(p)
                    self.addCleanup(p.kill)              # reaps on failure; no-op once done
                _wait_until_blocked_on(procs[0], lock, f"set-field --epic (at the {level} roll-up)")
            except AssertionError as e:
                failures.append(e)          # re-raised below, whatever promote does with it
                raise
            result = real_rollup(state_root, epic, sprint, *a, **kw)
            after.append((level, procs[0].poll(), pm.load_node(pm.epic_file(self.root, "E001"))[1]))
            return result

        with mock.patch.object(pm, "rollup_parent_estimate", watched_rollup):
            try:
                code, out, err = self.promote("BL-E001-001")
            except AssertionError:
                pass
        if failures:
            raise failures[0]
        _, serr = procs[0].communicate(timeout=30)
        self.assertEqual(code, 0, err)
        self.assertEqual(procs[0].returncode, 0, serr.decode())
        self.assertEqual([lvl for lvl, _, _ in after], ["sprint S02", "epic"])
        self.assertEqual(len(holds), 2)
        self.assertIsNotNone(holds[0][0])
        self.assertIs(holds[1][0], holds[0][0], "one epic lock hold spans both roll-ups")
        self.assertTrue(all(depth >= 1 for _, depth in holds), holds)
        for lvl, rc, node in after:
            self.assertIsNone(rc, f"set-field finished during the {lvl} roll-up")
            self.assertNotIn("notes", node, f"set-field's write landed during the {lvl} roll-up")
        rolled = after[-1][2]["estimate"]                # what the epic roll-up saved
        node = pm.load_node(pm.epic_file(self.root, "E001"))[1]
        self.assertEqual(node["notes"]["b9"], "landed")
        self.assertEqual(node["estimate"], rolled, "set-field's save undid the epic roll-up")
        self.assert_invariants()

    @unittest.skipUnless(os.path.exists("/proc/locks"), "needs /proc/locks to see a flock waiter")
    def test_clear_lock_waits_for_promote_and_is_not_undone(self):
        # A clear-lock racing promote's epic roll-up must not be silently reverted (batch D1).
        # promote saves the epic's estimate roll-up under epic_node_lock; a clear-lock that
        # did not hold that lock could land between the roll-up's load and its save, and
        # promote's copy would then restore the `_lock` the operator had just removed. The
        # clear is launched from inside the epic roll-up's save -- after the load, before the
        # write. (A comment, not a docstring: verbose unittest prints a docstring to stderr.)
        import subprocess
        self.append("A")
        code, _, err = self.run_all(["set-lock", "--state-root", self.root, "--epic", "E001",
                                     "--session-id", "me"])
        self.assertEqual(code, 0, err)
        real_save = pm.save_node
        lock = pm.epic_lock_path(self.root, "E001")
        procs, failures = [], []

        def racing_save(y, node, path, *a, **kw):
            if os.path.basename(path) == "epic.yaml" and not procs:
                p = subprocess.Popen([sys.executable, SCRIPT, "clear-lock", "--state-root",
                                      self.root, "--epic", "E001"],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                procs.append(p)
                try:    # deterministic: seen blocked on the epic lock, or it exited first
                    _wait_until_blocked_on(p, lock, "clear-lock")
                except AssertionError as e:
                    failures.append(e)      # re-raised below, whatever promote does with it
                    raise
            return real_save(y, node, path, *a, **kw)

        with mock.patch.object(pm, "save_node", racing_save):
            try:
                code, out, err = self.promote("BL-E001-001", extra=("--session-id", "me"))
            except AssertionError:
                pass
        if failures:
            raise failures[0]
        _, cerr = procs[0].communicate(timeout=30)
        self.assertEqual(code, 0, err)
        self.assertEqual(procs[0].returncode, 0, cerr.decode())
        node = pm.load_node(pm.epic_file(self.root, "E001"))[1]
        self.assertNotIn("_lock", node, "promote's roll-up save restored a cleared lock")
        self.assertIn("estimate", node)                              # the roll-up itself landed

    def test_keys_split_across_stories_refuse_to_triage(self):
        self.append("A")
        self._crash_promote_before_scheduling()
        self.append("B", "001", "02")
        before = _tree_snapshot(self.d)
        code, _, err = self.promote("BL-E001-001", "BL-E001-002", extra=("--title", "Batch"))
        self.assertEqual(code, 2)
        self.assertIn("triage", err)
        self.assertEqual(_tree_snapshot(self.d), before)

    def test_two_live_stories_claiming_one_key_refuse_to_triage(self):
        # Spec §2.4: more than one story claims the key -> exit 2, pointing to triage (audit 1h),
        # nothing written. The second claimant is a hand-written node (a deliberately corrupt
        # state), once beside the first and once in another epic -- the walk covers every epic.
        self.append("A")
        self._crash_promote_before_scheduling()        # E001-S02-001 lists it; still backlog
        second = {"E001-S02-002": ("active", "epic-001", "sprint-02"),
                  "E005-S01-001": ("planned", "epic-005", "sprint-01")}
        for skey, where in second.items():
            p = os.path.join(self.root, *where, f"{skey}.yaml")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(f"key: '{skey}'\nepic: '{skey[:4]}'\nsprint: '{skey[5:8]}'\n"
                         f"status: backlog\nresolves: [BL-E001-001]\n")
            before = _tree_snapshot(self.d)
            code, out, err = self.promote("BL-E001-001")
            self.assertEqual(code, 2, (skey, out, err))
            self.assertIn(f"BL-E001-001 already claimed by ['E001-S02-001', '{skey}']", err)
            self.assertIn("run /l3io-util-doctor triage (audit-issues 1d/1h)", err)
            self.assertEqual(_tree_snapshot(self.d), before, skey)
            os.remove(p)

    def test_resume_refuses_when_the_claimant_lists_other_keys(self):
        self.append("A")
        self.append("B", "001", "02")
        self._crash_promote_before_scheduling(extra=("--key", "BL-E001-002", "--title", "Batch"))
        before = _tree_snapshot(self.d)
        code, _, err = self.promote("BL-E001-001")
        self.assertEqual(code, 2)
        self.assertIn("triage", err)
        self.assertEqual(_tree_snapshot(self.d), before)

    def test_resume_refuses_a_claimant_in_another_epic(self):
        """A retry naming a different --epic (or --sprint) must not resume a claimant
        elsewhere: its lock was never taken and its roll-up would target the wrong epic."""
        self.append("A")
        self._crash_promote_before_scheduling()                   # claimant E001-S02-001
        s3 = os.path.join(self.root, "active", "epic-001", "sprint-03", "sprint.yaml")
        os.makedirs(os.path.dirname(s3))
        with open(s3, "w", encoding="utf-8") as fh:              # a second backlog sprint
            fh.write("key: 'S03'\nepic: 'E001'\ntitle: 'Three'\nstatus: backlog\n")
        for epic, sprint in (("005", "01"), ("001", "03")):
            before = _tree_snapshot(self.d)
            code, out, err = self.promote("BL-E001-001", epic=epic, sprint=sprint)
            self.assertEqual(code, 2, (epic, sprint, out, err))
            self.assertIn("E001-S02-001", err)
            self.assertIn("--epic 001 --sprint 02", err)
            self.assertEqual(_tree_snapshot(self.d), before, (epic, sprint))
        code, out, err = self.promote("BL-E001-001")               # the named retry resumes
        self.assertEqual(code, 0, err)
        self.assertIn("(resumed)", out)
        self.assert_invariants()


class TestEpicWritersHoldTheEpicLock(IssueBase):
    """Every epic.yaml read-modify-write holds epic_node_lock (batch D1).

    While this test holds E001's lock, every writer of E001's epic.yaml must wait. Each one
    runs as a real subprocess, because the lock's re-entrancy counter is per process. A
    move-epic that lands while they wait must not strand them: each re-resolves the epic
    under the lock and writes into the moved directory, never into a recreated ghost of the
    old one. The lock file lives outside the epic directory, which is why a move cannot
    carry it away from a waiter."""

    @unittest.skipUnless(os.path.exists("/proc/locks"), "needs /proc/locks to see a flock waiter")
    def test_every_epic_writer_waits_and_follows_a_move(self):
        import subprocess
        self.append("A")
        sr = self.root
        for argv in (["set-lock", "--state-root", sr, "--epic", "E001", "--session-id", "me"],
                     ["set-estimate", "--state-root", sr, "--epic", "E001", "--sprint", "S01",
                      "--man-hours-low", "1", "--man-hours-high", "2"]):
            code, _, err = self.run_all(argv)
            self.assertEqual(code, 0, err)
        writers = {
            "set-field": ["set-field", "--state-root", sr, "--epic", "001",
                          "--field", "notes.d1", "--value", "x"],
            "set-estimate": ["set-estimate", "--state-root", sr, "--epic", "001",
                             "--man-hours-low", "4", "--man-hours-high", "5"],
            "set-actual": ["set-actual", "--state-root", sr, "--node", "epic", "--epic", "001",
                           "--man-hours", "3"],
            "set-status": ["set-status", "--state-root", sr, "--epic", "001",
                           "--status", "backlog"],
            "clear-lock": ["clear-lock", "--state-root", sr, "--epic", "E001"],
            "estimate-rollup": ["estimate-rollup", "--state-root", sr, "--epic", "001"],
            "move-epic": ["move-epic", "--state-root", sr, "--epic", "E001", "--to", "planned"],
            "promote-issue": ["promote-issue", "--state-root", sr, "--artifacts-root", self.arts,
                              "--key", "BL-E001-001", "--epic", "001", "--sprint", "02",
                              "--classification", "standard", "--session-id", "me"],
        }
        epic_yaml = pm.epic_file(sr, "E001")
        with open(epic_yaml, "rb") as fh:
            before = fh.read()
        procs = {}
        lock = pm.epic_lock_path(sr, "E001")
        with pm.epic_node_lock(sr, "E001"):
            for name, argv in writers.items():
                procs[name] = subprocess.Popen([sys.executable, SCRIPT, *argv],
                                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.addCleanup(procs[name].kill)            # reaps on failure; no-op once done
            for name, p in procs.items():   # deterministic: each seen blocked, or it exited first
                _wait_until_blocked_on(p, lock, name)
            with open(epic_yaml, "rb") as fh:
                during = fh.read()
            with redirect_stderr(io.StringIO()):             # no .git here: the fallback warns
                pm.move_epic(sr, "E001", "planned")          # re-entrant: this process holds it
        results = {n: (p.communicate(timeout=60), p.returncode) for n, p in procs.items()}
        self.assertEqual(during, before)
        for name, ((out, err), rc) in results.items():
            self.assertEqual(rc, 0, f"{name}: {out.decode()} {err.decode()}")
        self.assertFalse(os.path.exists(os.path.join(sr, "active", "epic-001")),
                         "a writer recreated the epic's old directory after the move")
        path = pm.epic_file(sr, "E001")
        self.assertTrue(path.endswith(os.path.join("planned", "epic-001", "epic.yaml")), path)
        node = pm.load_node(path)[1]
        self.assertEqual(node["notes"]["d1"], "x")
        self.assertEqual(float(node["actual"]["man_hours"]), 3.0)
        self.assertEqual(node["status"], "backlog")
        self.assertNotIn("_lock", node)
        self.assertIn("estimate", node)
        self.assertTrue(os.path.exists(os.path.join(sr, "planned", "epic-001", "sprint-02",
                                                    "E001-S02-001.yaml")))


class TestEpicNodeLockScope(unittest.TestCase):
    """The epic lock's reach, attacked directly (batch D1): the rule is enforced at the one
    write chokepoint (`_atomic_dump`), so these plant writes by routes the verbs never
    take, rather than trusting the verb inventory to be complete."""

    # TestLayoutResolution's tree, without inheriting (and so re-running) its tests.
    setUp = TestLayoutResolution.setUp
    tearDown = TestLayoutResolution.tearDown

    def _touch(self, path):
        y, node = pm.load_node(path)
        node["touched"] = True
        pm.save_node(y, node, path)

    def test_an_epic_yaml_write_without_the_lock_is_refused_on_every_route(self):
        path = pm.epic_file(self.root, "E001")
        with open(path, "rb") as fh:
            before = fh.read()
        y, node = pm.load_node(path)
        routes = {"save_node": lambda: pm.save_node(y, node, path),
                  "save_node(use_flock)": lambda: pm.save_node(y, node, path, use_flock=True),
                  "_atomic_dump": lambda: pm._atomic_dump(y, node, path),
                  "_mark_sampled": lambda: pm._mark_sampled(node, path, y)}
        for name, route in routes.items():
            with self.assertRaises(RuntimeError, msg=name):
                route()
        with open(path, "rb") as fh:
            self.assertEqual(fh.read(), before)

    def test_another_epics_lock_does_not_cover_the_write(self):
        with pm.epic_node_lock(self.root, "E005"):
            with self.assertRaises(RuntimeError):
                self._touch(pm.epic_file(self.root, "E001"))

    def test_the_same_epic_under_any_spelling_covers_the_write(self):
        with pm.epic_node_lock(os.path.relpath(self.root), "1"):    # relative root, bare key
            self._touch(pm.epic_file(self.root, "E001"))
        self.assertTrue(pm.load_node(pm.epic_file(self.root, "E001"))[1]["touched"])

    def test_sprint_and_story_nodes_are_not_gated(self):
        self._touch(pm.sprint_file(self.root, "E001", "S01"))
        self._touch(pm.story_file(self.root, "E001-S01-003"))

    def test_reentry_on_the_same_epic_nests_without_a_second_flock(self):
        with pm.epic_node_lock(self.root, "E001"):
            fh = pm._EPIC_NODE_LOCK["fh"]
            with pm.epic_node_lock(self.root, "001"):
                self.assertEqual(pm._EPIC_NODE_LOCK["depth"], 2)
                self.assertIs(pm._EPIC_NODE_LOCK["fh"], fh)
                self._touch(pm.epic_file(self.root, "E001"))
            self.assertEqual(pm._EPIC_NODE_LOCK["depth"], 1)
        self.assertEqual(pm._EPIC_NODE_LOCK["depth"], 0)

    def test_a_second_epics_lock_cannot_nest(self):
        # The re-entrancy counter is per lock family, so a nested second epic's lock would
        # silently skip its flock -- refused outright instead.
        with pm.epic_node_lock(self.root, "E001"):
            with self.assertRaises(RuntimeError):
                with pm.epic_node_lock(self.root, "E005"):
                    pass
            self._touch(pm.epic_file(self.root, "E001"))     # the outer hold survives
        self.assertEqual(pm._EPIC_NODE_LOCK["depth"], 0)

    def test_the_lock_file_is_outside_the_epic_directory_and_survives_a_move(self):
        lock = pm.epic_lock_path(self.root, "E001")
        with pm.epic_node_lock(self.root, "E001"):
            pass
        self.assertTrue(os.path.exists(lock))
        self.assertFalse(os.path.realpath(lock).startswith(
            os.path.realpath(pm.find_epic_dir(self.root, "E001")) + os.sep))
        with redirect_stderr(io.StringIO()):                 # no .git here: the fallback warns
            pm.move_epic(self.root, "E001", "archived")
        self.assertEqual(pm.epic_lock_path(self.root, "E001"), lock)
        self.assertTrue(os.path.exists(lock))

    def test_a_fresh_epic_lock_under_issues_or_calibration_lock_is_refused(self):
        # Lock order: epic_node_lock is taken first, never under issues_lock or
        # calibration_lock -- the reverse of promote's epic -> issues is a deadlock.
        outers = {"issues_lock": lambda: pm.issues_lock(pm.issues_paths(self.root)[0]),
                  "calibration_lock": lambda: pm.calibration_lock(self.root)}
        for name, outer in outers.items():
            with outer():
                with self.assertRaises(RuntimeError, msg=name) as cm:
                    with pm.epic_node_lock(self.root, "E001"):
                        pass
                self.assertIn("lock order", str(cm.exception), name)
            self.assertEqual(pm._EPIC_NODE_LOCK["depth"], 0, name)
            self.assertIsNone(pm._EPIC_NODE_LOCK["path"], name)

    def test_same_epic_reentry_under_issues_lock_is_allowed(self):
        # promote's shape: epic lock, then issues_lock, then the roll-up re-enters the epic.
        with pm.epic_node_lock(self.root, "E001"):
            with pm.issues_lock(pm.issues_paths(self.root)[0]):
                with pm.epic_node_lock(self.root, "001"):
                    self._touch(pm.epic_file(self.root, "E001"))

    def test_set_actual_cost_is_refused_before_the_epic_lock(self):
        # --cost is a usage error on any node, so it is refused before the epic lock: it
        # neither waits behind a holder nor creates the lock file.
        path = pm.epic_file(self.root, "E001")
        with open(path, "rb") as fh:
            before = fh.read()
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            with self.assertRaises(SystemExit) as cm:
                pm.main(["set-actual", "--state-root", self.root, "--node", "epic",
                         "--epic", "E001", "--man-hours", "1", "--cost", "5"])
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("--cost is not accepted", err.getvalue())
        self.assertFalse(os.path.exists(pm.epic_lock_path(self.root, "E001")))
        with open(path, "rb") as fh:
            self.assertEqual(fh.read(), before)


class TestConcurrentPromote(unittest.TestCase):
    N = 4

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.arts = os.path.join(self.d, "impl")
        self.root = os.path.join(self.arts, "state")
        _build_issue_tree(self.root)
        for i in range(1, self.N + 1):
            with redirect_stdout(io.StringIO()):
                pm.main(["append-issue", "--state-root", self.root, "--epic", "001", "--sprint",
                         "01", "--title", f"t{i}", "--source", "qa", "--severity", "Low"])

    def test_parallel_promotes_get_distinct_stories_and_a_complete_rollup(self):
        import subprocess
        procs = [subprocess.Popen([sys.executable, SCRIPT, "promote-issue", "--state-root",
                                   self.root, "--artifacts-root", self.arts, "--key",
                                   f"BL-E001-{i:03d}", "--epic", "001", "--sprint", "02",
                                   "--classification", "simple"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for i in range(1, self.N + 1)]
        for p in procs:
            _, err = p.communicate(timeout=180)
            self.assertEqual(p.returncode, 0, err.decode())
        stories = pm.list_story_files(self.root, "E001", "S02")
        self.assertEqual(len(stories), self.N)
        after_race = dict(pm.load_node(pm.sprint_file(self.root, "E001", "S02"))[1]["estimate"])
        with redirect_stderr(io.StringIO()):
            pm.rollup_parent_estimate(self.root, "E001", "S02", pm.DEFAULT_ESTIMATE_MODEL, None)
        fresh = dict(pm.load_node(pm.sprint_file(self.root, "E001", "S02"))[1]["estimate"])
        self.assertEqual(after_race["man_hours_low"], fresh["man_hours_low"],
                         "the last roll-up saved during the race missed a story")


class TestDoneHook(IssueBase):
    def setUp(self):
        super().setUp()
        self.append("A")
        code, _, err = self.run_all(["promote-issue", "--state-root", self.root,
                                     "--artifacts-root", self.arts, "--key", "BL-E001-001",
                                     "--epic", "001", "--sprint", "02",
                                     "--classification", "simple"])
        self.assertEqual(code, 0, err)

    def set_status(self, status, *extra, story="E001-S02-001"):
        return self.run_all(["set-status", "--state-root", self.root, "--story", story,
                             "--status", status, *extra])

    def story_status(self, key="E001-S02-001"):
        return pm.load_node(pm.story_file(self.root, key))[1]["status"]

    def test_done_resolves_the_items_the_story_lists(self):
        code, out, err = self.set_status("done", "--session-id", "S-3")
        self.assertEqual(code, 0, err)
        self.assertIn("resolved BL-E001-001 (fixed, ref E001-S02-001)", out)
        self.assertEqual(self.open_keys(), [])
        entry = self.load_resolved()["resolved"][0]
        self.assertEqual((entry["resolution"], entry["ref"]), ("fixed", "E001-S02-001"))
        ev = self.events("issue_resolved")[-1]
        self.assertEqual((ev["cause"], ev["session"]), ("set-status", "S-3"))

    def test_hook_runs_under_no_events(self):
        self.set_status("done", "--no-events")
        self.assertEqual(self.resolved_keys(), ["BL-E001-001"])

    def test_second_done_is_a_noop(self):
        self.set_status("done")
        code, out, _ = self.set_status("done")
        self.assertEqual(code, 0)
        self.assertIn("ok BL-E001-001 already resolved (fixed)", out)
        self.assertEqual([l for l in out.splitlines() if l.startswith("resolved BL-")], [],
                         "a `resolved BL-` line must mean a NEW resolution only")
        self.assertEqual(self.resolved_keys(), ["BL-E001-001"])

    def test_hook_failure_warns_and_set_status_still_exits_0(self):
        with mock.patch.object(pm, "resolve_issue_core", side_effect=SystemExit(2)):
            code, _, err = self.set_status("done")
        self.assertEqual(code, 0)
        self.assertIn("done hook failed", err)
        self.assertEqual(self.story_status(), "done")
        self.assertEqual(self.open_keys(), ["BL-E001-001"])

    def test_malformed_issues_file_warns_and_status_stands(self):
        with open(self.issues, "w", encoding="utf-8") as fh:
            fh.write("backlog: oops\n")
        code, _, err = self.set_status("done")
        self.assertEqual(code, 0)
        self.assertIn("pm-status.py: warning -- done hook failed for E001-S02-001: PMError(", err)
        self.assertIn("has a malformed 'backlog' field", err)
        self.assertIn("; the status write stands. Run /l3io-util-doctor triage (audit-issues "
                      "finding 1c) to finish it.", err)
        self.assertEqual(self.story_status(), "done")

    def test_other_statuses_do_not_resolve(self):
        self.set_status("in-progress")
        self.set_status("review")
        self.assertEqual(self.open_keys(), ["BL-E001-001"])

    def test_story_without_resolves_touches_no_issue_file(self):
        p = os.path.join(self.root, "active", "epic-001", "sprint-01", "E001-S01-001.yaml")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("key: 'E001-S01-001'\nepic: 'E001'\nsprint: 'S01'\nstatus: review\n")
        self.set_status("done", story="E001-S01-001")
        self.assertFalse(os.path.exists(self.resolved))

    def test_set_field_refuses_status(self):
        code, _, err = self.run_all(["set-field", "--state-root", self.root, "--story",
                                     "E001-S02-001", "--field", "status", "--value", "done"])
        self.assertEqual(code, 2)
        self.assertIn("set-status", err)
        self.assertEqual(self.story_status(), "backlog")
        self.assertEqual(self.open_keys(), ["BL-E001-001"])

    def _story_bytes(self, key):
        with open(pm.story_file(self.root, key), "rb") as fh:
            return fh.read()

    def test_set_field_refuses_a_subpath_of_resolves(self):
        """`resolves.x` used to walk into the node and save a mapping under resolves:."""
        p = os.path.join(self.root, "active", "epic-001", "sprint-01", "E001-S01-001.yaml")
        with open(p, "w", encoding="utf-8") as fh:              # a story with no resolves:
            fh.write("key: 'E001-S01-001'\nepic: 'E001'\nsprint: 'S01'\nstatus: review\n")
        before = self._story_bytes("E001-S01-001")
        code, _, err = self.run_all(["set-field", "--state-root", self.root, "--story",
                                     "E001-S01-001", "--field", "resolves.x", "--value", "v"])
        self.assertEqual(code, 2, err)
        self.assertIn("--field resolves.x is not directly writable", err)
        self.assertEqual(self._story_bytes("E001-S01-001"), before)

    def test_set_field_refuses_a_subpath_of_status(self):
        before = self._story_bytes("E001-S02-001")
        code, _, err = self.run_all(["set-field", "--state-root", self.root, "--story",
                                     "E001-S02-001", "--field", "status.x", "--value", "done"])
        self.assertEqual(code, 2, err)
        self.assertIn("--field status.x is not directly writable", err)
        self.assertEqual(self._story_bytes("E001-S02-001"), before)
        # the rule is `<name>.` -- a sibling name that merely starts with it stays writable
        code, _, err = self.run_all(["set-field", "--state-root", self.root, "--story",
                                     "E001-S02-001", "--field", "status_note", "--value", "x"])
        self.assertEqual(code, 0, err)

    def test_set_field_refuses_a_subpath_of_every_derived_field(self):
        """Scope from the source of truth: every DERIVED_NODE_FIELDS entry, not a hand list."""
        before = self._story_bytes("E001-S02-001")
        for name in pm.DERIVED_NODE_FIELDS:
            code, _, err = self.run_all(["set-field", "--state-root", self.root, "--story",
                                         "E001-S02-001", "--field", f"{name}.x", "--value", "v"])
            self.assertEqual(code, 2, (name, err))
            self.assertIn("is not directly writable", err, name)
        self.assertEqual(self._story_bytes("E001-S02-001"), before)

    def test_set_field_refuses_a_parent_path_of_a_derived_field(self):
        """`--field completion_evidence` replaced the whole mapping, discarding test_runs and
        the tests_passing derived from them."""
        code, _, err = self.run_all(["add-test-run", "--state-root", self.root, "--story",
                                     "E001-S02-001", "--command", "pytest", "--exit-code", "0"])
        self.assertEqual(code, 0, err)                          # premise: real test_runs exist
        before = self._story_bytes("E001-S02-001")
        code, _, err = self.run_all(["set-field", "--state-root", self.root, "--story",
                                     "E001-S02-001", "--field", "completion_evidence",
                                     "--value", "x"])
        self.assertEqual(code, 2, err)
        self.assertIn("--field completion_evidence is not directly writable (it contains "
                      "completion_evidence.tests_passing)", err)
        self.assertIn("add-test-run", err)
        self.assertEqual(self._story_bytes("E001-S02-001"), before)
        # the rule is `<field>.` -- a sibling name that merely starts with it stays writable
        code, _, err = self.run_all(["set-field", "--state-root", self.root, "--story",
                                     "E001-S02-001", "--field", "completion_evidence_note",
                                     "--value", "x"])
        self.assertEqual(code, 0, err)

    def test_set_field_refuses_every_parent_path_of_every_derived_field(self):
        """Scope from the source of truth: every proper dot-prefix of every DERIVED_NODE_FIELDS
        entry, not a hand list."""
        parents = {".".join(name.split(".")[:i]) for name in pm.DERIVED_NODE_FIELDS
                   for i in range(1, name.count(".") + 1)}
        self.assertTrue(parents, "no derived field has a parent path: this loop checks nothing")
        before = self._story_bytes("E001-S02-001")
        for field in sorted(parents):
            code, _, err = self.run_all(["set-field", "--state-root", self.root, "--story",
                                         "E001-S02-001", "--field", field, "--value", "v"])
            self.assertEqual(code, 2, (field, err))
            self.assertIn(f"--field {field} is not directly writable (it contains ", err, field)
        self.assertEqual(self._story_bytes("E001-S02-001"), before)

    def _set_resolves(self, value):
        p = pm.story_file(self.root, "E001-S02-001")
        y, n = pm.load_node(p)
        n["resolves"] = value
        pm.save_node(y, n, p)

    def test_non_list_resolves_warns_and_set_status_still_exits_0(self):
        self._set_resolves(5)
        code, _, err = self.set_status("done")
        self.assertEqual(code, 0, err)
        self.assertIn("malformed resolves", err)
        self.assertEqual(self.story_status(), "done")
        self.assertEqual(self.open_keys(), ["BL-E001-001"])

    def test_string_resolves_is_treated_as_one_key(self):
        self._set_resolves("BL-E001-001")
        code, out, err = self.set_status("done")
        self.assertEqual(code, 0, err)
        self.assertIn("resolved BL-E001-001 (fixed, ref E001-S02-001)", out)
        self.assertEqual(self.resolved_keys(), ["BL-E001-001"])

    def test_unresolvable_key_warning_names_triage(self):
        self._set_resolves(["BL-E001-001", "BL-E001-050"])
        code, _, err = self.set_status("done")
        self.assertEqual(code, 0, err)
        self.assertIn("could not resolve BL-E001-050 for E001-S02-001", err)
        self.assertIn("-- run /l3io-util-doctor triage", err)
        self.assertEqual(self.resolved_keys(), ["BL-E001-001"])

    def test_hook_lines_follow_set_status_and_a_failed_key_does_not_stop_later_ones(self):
        # The existing mixed test lists the real key FIRST, so it never shows a key resolving
        # AFTER an earlier key's PMError, and it reads stdout and stderr apart, so it pins no
        # order. Here the keys are listed unknown -> already resolved -> open, and both streams
        # go to ONE buffer: its line order is the order the lines were written.
        self.append("B", "001", "02")
        code, _, err = self.run_all(["resolve-issue", "--state-root", self.root, "--key",
                                     "BL-E001-002", "--resolution", "wontfix", "--note", "ok"])
        self.assertEqual(code, 0, err)
        self._set_resolves(["BL-E001-050", "BL-E001-002", "BL-E001-001"])
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            code = pm.main(["set-status", "--state-root", self.root, "--story", "E001-S02-001",
                            "--status", "done"])
        lines = buf.getvalue().splitlines()
        self.assertEqual(code, 0, lines)
        want = ["OK set-status ",
                "pm-status.py: warning -- could not resolve BL-E001-050 for E001-S02-001: ",
                "ok BL-E001-002 already resolved (wontfix)",
                "resolved BL-E001-001 (fixed, ref E001-S02-001)"]
        self.assertEqual(len(lines), len(want), lines)
        for line, prefix in zip(lines, want):
            self.assertTrue(line.startswith(prefix), (prefix, lines))
        self.assertTrue(lines[0].endswith(" -> done"), lines[0])
        entry = [r for r in self.load_resolved()["resolved"] if r["key"] == "BL-E001-001"]
        self.assertEqual([(r["resolution"], r["ref"]) for r in entry], [("fixed", "E001-S02-001")])


class TestAuditIssues(IssueBase):
    def audit(self):
        code, out, err = self.run_all(["audit-issues", "--state-root", self.root,
                                       "--format", "json"])
        self.assertIn(code, (0, 4), err)
        return code, json.loads(out)["findings"]

    def found(self, fid, key):
        code, findings = self.audit()
        self.assertEqual(code, 4)
        self.assertIn((fid, key), {(f["id"], f["key"]) for f in findings}, findings)

    def promote(self, key="BL-E001-001", epic="001", sprint="02"):
        code, _, err = self.run_all(["promote-issue", "--state-root", self.root,
                                     "--artifacts-root", self.arts, "--key", key, "--epic", epic,
                                     "--sprint", sprint, "--classification", "simple"])
        self.assertEqual(code, 0, err)

    def edit_story(self, key, fn):
        p = pm.story_file(self.root, key)
        y, n = pm.load_node(p)
        fn(n)
        pm.save_node(y, n, p)

    def edit_open(self, fn):
        y, data = pm._load(self.issues)
        fn(data)
        pm._atomic_dump(y, data, self.issues)

    def test_clean_lifecycle_exits_0(self):
        self.append("A")
        self.promote()
        self.run_all(["set-status", "--state-root", self.root, "--story", "E001-S02-001",
                      "--status", "done"])
        self.assertEqual(self.audit(), (0, []))

    def test_missing_state_root_is_clean(self):
        code, out, _ = self.run_all(["audit-issues", "--state-root",
                                     os.path.join(self.d, "nope")])
        self.assertEqual(code, 0)

    def test_json_format_reports_a_malformed_issue_file(self):
        """Triage T2 and health-check Check 13 parse this JSON: a malformed file must still
        yield a parseable document carrying the error, with exit 4."""
        with open(self.issues, "w", encoding="utf-8") as fh:
            fh.write("backlog: oops\n")
        code, out, err = self.run_all(["audit-issues", "--state-root", self.root,
                                       "--format", "json"])
        self.assertEqual(code, 4, err)
        doc = json.loads(out)
        self.assertEqual(doc["findings"], [])
        self.assertIn("malformed 'backlog'", doc["error"])
        code, out, err = self.run_all(["audit-issues", "--state-root", self.root])
        self.assertEqual((code, out), (4, ""))                  # text mode is unchanged
        self.assertIn("malformed 'backlog'", err)

    def test_audit_without_issue_files_leaves_no_lock_file(self):
        code, _ = self.audit()
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(self.issues + ".lock"),
                         "a read-only command left a lock file behind")

    def test_1a_key_in_both_files(self):
        self.append("A")
        with _dump_failing_on(2):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                with self.assertRaises(OSError):
                    pm.main(["resolve-issue", "--state-root", self.root, "--key",
                             "BL-E001-001", "--resolution", "obsolete", "--note", "x"])
        self.found("1a", "BL-E001-001")

    def test_1b_scheduled_to_a_missing_story(self):
        self.append("A")
        self.promote()
        os.remove(pm.story_file(self.root, "E001-S02-001"))
        self.found("1b", "BL-E001-001")

    def test_1b_resolves_names_an_unknown_key(self):
        self.append("A")
        self.promote()
        self.edit_story("E001-S02-001", lambda n: n["resolves"].append("BL-E001-050"))
        self.found("1b", "BL-E001-050")

    def test_1c_done_story_with_item_still_open(self):
        self.append("A")
        self.promote()
        self.edit_story("E001-S02-001", lambda n: n.__setitem__("status", "done"))  # hook bypassed
        self.found("1c", "BL-E001-001")

    def test_1d_promote_stopped_before_scheduling(self):
        self.append("A")
        self._crash_promote_before_scheduling(cls="simple")
        self.found("1d", "BL-E001-001")

    def test_1e_stale_next(self):
        self.append("A")
        self.append("B", "001", "02")
        self.edit_open(lambda d: d["next"].__setitem__("001", 1))
        self.found("1e", "BL-E001")

    def test_1f_bad_open_status(self):
        self.append("A")
        self.edit_open(lambda d: d["backlog"][0].__setitem__("status", "weird"))
        self.found("1f", "BL-E001-001")

    def test_1g_scheduled_to_an_archived_story_that_never_finished(self):
        self.append("Later", "005", "01", "Low", "qa (Q-1)")
        self.promote("BL-E005-001", "005", "01")
        self.run_all(["archive-epic", "--state-root", self.root, "--epic", "E005"])
        self.found("1g", "BL-E005-001")

    def test_1h_two_stories_claim_one_item(self):
        self.append("A")
        self.promote()
        p = os.path.join(self.root, "active", "epic-001", "sprint-02", "E001-S02-002.yaml")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("key: 'E001-S02-002'\nepic: 'E001'\nsprint: 'S02'\nstatus: backlog\n"
                     "resolves: [BL-E001-001]\n")
        self.found("1h", "BL-E001-001")

    def test_1i_duplicate_key_in_a_file(self):
        self.append("A")
        from ruamel.yaml.comments import CommentedMap
        self.edit_open(lambda d: d["backlog"].append(CommentedMap(d["backlog"][0])))
        self.found("1i", "BL-E001-001")

    def test_1j_story_reverted_after_done(self):
        self.append("A")
        self.promote()
        for st in ("done", "in-progress"):
            self.run_all(["set-status", "--state-root", self.root, "--story", "E001-S02-001",
                          "--status", st])
        self.found("1j", "BL-E001-001")

    def test_text_format_names_the_repair(self):
        self.append("A")
        self.edit_open(lambda d: d["backlog"][0].__setitem__("status", "weird"))
        code, out, _ = self.run_all(["audit-issues", "--state-root", self.root])
        self.assertEqual(code, 4)
        self.assertIn("1f", out)
        self.assertIn("repair:", out)

    def _crash_resolve_before_open_save(self, key="BL-E001-001"):
        """resolve-issue with its second write failing: the key is left in BOTH files (1a)."""
        with _dump_failing_on(2):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                with self.assertRaises(OSError):
                    pm.main(["resolve-issue", "--state-root", self.root, "--key", key,
                             "--resolution", "obsolete", "--note", "x"])

    def test_a_key_in_both_files_is_audited_only_for_1a(self):
        """Ruling 8, resolved first: the stale open copy is not evaluated (here it looks 1d)."""
        self.append("A")
        self._crash_promote_before_scheduling(cls="simple")     # story lists it, item backlog
        self._crash_resolve_before_open_save()
        _, findings = self.audit()
        self.assertEqual([(f["id"], f["key"]) for f in findings], [("1a", "BL-E001-001")])

    def test_a_duplicated_key_is_reported_only_as_1i(self):
        """An ambiguous key is never evaluated through an arbitrary copy (single_open)."""
        from ruamel.yaml.comments import CommentedMap
        self.append("A")

        def dup_weird_first(d):
            c = CommentedMap(d["backlog"][0])
            c["status"] = "weird"
            d["backlog"].insert(0, c)
        self.edit_open(dup_weird_first)
        _, findings = self.audit()
        self.assertEqual([(f["id"], f["key"]) for f in findings], [("1i", "BL-E001-001")])


class TestRepairIssue(TestAuditIssues):
    """Inherits TestAuditIssues' helpers, so each corrupt state is built the same way
    the audit test proved it detectable. The inherited audit tests run again here too;
    that is harmless and keeps the fixture code in one place."""

    def repair(self, key, action, *extra):
        return self.run_all(["repair-issue", "--state-root", self.root, "--key", key,
                             "--action", action, *extra])

    def ids(self):
        return {(f["id"], f["key"]) for f in self.audit()[1]}

    def test_unschedule_clears_1b(self):
        self.append("A")
        self.promote()
        os.remove(pm.story_file(self.root, "E001-S02-001"))
        code, _, err = self.repair("BL-E001-001", "unschedule")
        self.assertEqual(code, 0, err)
        item = self.load_open()["backlog"][0]
        self.assertEqual(item["status"], "backlog")
        self.assertNotIn("story", item)
        self.assertNotIn(("1b", "BL-E001-001"), self.ids())
        self.assert_invariants()

    def test_unschedule_writes_an_issue_unscheduled_event(self):
        """scheduled -> backlog is a status transition, and the events are its history."""
        self.append("A")
        self.promote()
        os.remove(pm.story_file(self.root, "E001-S02-001"))
        code, _, err = self.repair("BL-E001-001", "unschedule", "--session-id", "S-5")
        self.assertEqual(code, 0, err)
        ev = self.events("issue_unscheduled")
        self.assertEqual(len(ev), 1)
        self.assertEqual((ev[0]["key"], ev[0]["epic"], ev[0]["story"], ev[0]["session"],
                          ev[0]["cause"]), ("BL-E001-001", "001", "E001-S02-001", "S-5", "cli"))
        self.assertIn("ts", ev[0])

    def test_unschedule_clears_1g(self):
        self.append("Later", "005", "01", "Low", "qa (Q-1)")
        self.promote("BL-E005-001", "005", "01")
        self.run_all(["archive-epic", "--state-root", self.root, "--epic", "E005"])
        self.assertEqual(self.repair("BL-E005-001", "unschedule")[0], 0)
        self.assertNotIn(("1g", "BL-E005-001"), self.ids())
        # the archived story still lists the key, but its claim is dead: no 1d, no loop
        self.assertEqual(self.audit(), (0, []))
        self.assert_invariants()

    def test_repromote_after_1g_creates_a_new_story(self):
        self.append("Later", "005", "01", "Low", "qa (Q-1)")
        self.promote("BL-E005-001", "005", "01")
        self.run_all(["archive-epic", "--state-root", self.root, "--epic", "E005"])
        self.assertEqual(self.repair("BL-E005-001", "unschedule")[0], 0)
        code, out, err = self.run_all(["promote-issue", "--state-root", self.root,
                                       "--artifacts-root", self.arts, "--key", "BL-E005-001",
                                       "--epic", "001", "--sprint", "02",
                                       "--classification", "simple"])
        self.assertEqual(code, 0, err)
        self.assertIn("-> E001-S02-001", out)
        self.assertNotIn("resumed", out)
        self.assertIsNotNone(pm.story_file(self.root, "E001-S02-001"))
        item = self.load_open()["backlog"][0]
        self.assertEqual((item["status"], item["story"]), ("scheduled", "E001-S02-001"))
        self.assertEqual(self.audit(), (0, []))      # the dead archived claim is not 1h
        self.assert_invariants()

    def test_1j_ignores_a_ref_story_that_never_listed_the_key(self):
        """resolve --ref <a story still in progress> is legitimate. That story never listed
        the key, so 1j must not fire -- and reopen must not manufacture a 1b from it."""
        self.append("A")
        self.promote()                                          # E001-S02-001 lists 001 only
        self.run_all(["set-status", "--state-root", self.root, "--story", "E001-S02-001",
                      "--status", "in-progress"])
        self.append("B", "001", "02")
        code, _, err = self.run_all(["resolve-issue", "--state-root", self.root, "--key",
                                     "BL-E001-002", "--resolution", "fixed", "--ref",
                                     "E001-S02-001"])
        self.assertEqual(code, 0, err)
        self.assertEqual(self.audit(), (0, []))
        code, _, err = self.repair("BL-E001-002", "reopen")
        self.assertEqual(code, 2)
        self.assertIn("reopen: audit finding 1j does not hold for BL-E001-002", err)
        self.assertEqual(self.resolved_keys(), ["BL-E001-002"])

    def test_link_refuses_a_key_with_a_resolved_entry(self):
        self.append("A")
        self._crash_promote_before_scheduling(cls="simple")
        self._crash_resolve_before_open_save()                  # 1a; the stale copy looks 1d
        before = _tree_snapshot(self.d)
        code, _, err = self.repair("BL-E001-001", "link", "--story", "E001-S02-001")
        self.assertEqual(code, 2)
        self.assertIn("link: BL-E001-001 is already resolved (obsolete)", err)
        self.assertIn("rerun resolve-issue", err)
        self.assertEqual(_tree_snapshot(self.d), before)

    def test_unschedule_refuses_a_key_with_a_resolved_entry(self):
        self.append("A")
        self.promote()
        self._crash_resolve_before_open_save()                  # 1a; the stale copy is scheduled
        os.remove(pm.story_file(self.root, "E001-S02-001"))     # ...and now looks 1b
        self.assertEqual([(f["id"], f["key"]) for f in self.audit()[1]],
                         [("1a", "BL-E001-001")])               # the stale copy is not 1b
        before = _tree_snapshot(self.d)
        code, _, err = self.repair("BL-E001-001", "unschedule")
        self.assertEqual(code, 2)
        self.assertIn("unschedule: BL-E001-001 is already resolved (obsolete)", err)
        self.assertIn("rerun resolve-issue", err)
        self.assertEqual(_tree_snapshot(self.d), before)
        code, _, err = self.run_all(["resolve-issue", "--state-root", self.root, "--key",
                                     "BL-E001-001", "--resolution", "obsolete", "--note", "x"])
        self.assertEqual(code, 0, err)                          # the advised repair works
        self.assertEqual(self.audit(), (0, []))
        self.assert_invariants()

    def _set_next(self, *pairs):
        from ruamel.yaml.comments import CommentedMap
        self.edit_open(lambda d: d.__setitem__("next", CommentedMap(pairs)))

    def e1(self):
        return [f for f in self.audit()[1] if f["id"] == "1e"]

    def test_audit_reports_an_unquoted_numeric_next_key_as_an_alias(self):
        """next: {1: 5} -- a hand edit with an int key -- must not crash the audit's sort. By the
        user's decision it is 1e whatever its value: allocate reads only the canonical '001'."""
        self.append("A")
        self.append("C", "005", "01", "Low", "qa (Q-1)")
        self._set_next((1, 5), ("005", 2))
        code, findings = self.audit()                   # parseable JSON: the sort did not crash
        self.assertEqual(code, 4)
        e1 = [f for f in findings if f["id"] == "1e"]
        self.assertEqual([(f["key"], f["epic"]) for f in e1], [("BL-E001", "001")], findings)
        self.assertIn("non-canonical key 1 ", e1[0]["detail"])
        self.assertIn("run repair-issue --action reseed", e1[0]["detail"])
        self.assertEqual(e1[0]["repair"], "repair-issue --action reseed")

    def test_audit_reports_every_string_next_alias_as_1e(self):
        self.append("A")
        for alias in ("1", "01", "E001"):
            self._set_next(("001", 9), (alias, 9))          # both values healthy
            e1 = self.e1()
            self.assertEqual(len(e1), 1, (alias, e1))
            self.assertIn(f"non-canonical key {alias!r} ", e1[0]["detail"])

    def test_audit_reports_a_next_beyond_the_key_space_as_1e(self):
        """Keys run 001-999, so next is at most 1000."""
        self.append("A")
        self._set_next(("001", 1000))
        self.assertEqual(self.audit(), (0, []))
        self._set_next(("001", 1001))
        e1 = self.e1()
        self.assertEqual([(f["key"], f["epic"]) for f in e1], [("BL-E001", "001")])
        self.assertIn("next['001'] = 1001 exceeds the BL key space", e1[0]["detail"])

    def test_an_alias_beyond_the_key_space_gets_the_hand_fix_repair(self):
        # Final review M7. reseed refuses any alias above 1000 (exit 2), so an alias finding
        # that still said "run repair-issue --action reseed" routed triage to a repair that
        # cannot run. Above 1000 it carries the key-space finding's hand-fix text; at 1000
        # reseed folds the alias in by max, so reseed stays its repair.
        self.append("A")
        self._set_next(("001", 2), (1, 1000))
        e1 = self.e1()
        self.assertEqual(len(e1), 1, e1)
        self.assertIn("non-canonical key 1 ", e1[0]["detail"])
        self.assertIn("run repair-issue --action reseed", e1[0]["detail"])
        self.assertEqual(e1[0]["repair"], "repair-issue --action reseed")

        self._set_next(("001", 2), (1, 1001))
        e1 = self.e1()
        alias = [f for f in e1 if "non-canonical key 1 " in f["detail"]]
        space = [f for f in e1 if "exceeds the BL key space" in f["detail"]]
        self.assertEqual((len(e1), len(alias), len(space)), (2, 1, 1), e1)
        self.assertNotIn("run repair-issue --action reseed", alias[0]["detail"])
        self.assertIn("fix it by hand", alias[0]["detail"])
        self.assertEqual(alias[0]["repair"], space[0]["repair"])
        self.assertTrue(alias[0]["repair"].startswith("report only -- fix it by hand"),
                        alias[0]["repair"])
        self.assertEqual(self.repair("BL-E001-001", "reseed")[0], 2)   # why: reseed refuses

    def test_reseed_refuses_a_value_beyond_the_key_space_and_writes_nothing(self):
        self.append("A")
        self.append("B", "001", "02")
        for pairs, named in (((("001", 1), (1, 5000)), "next[1] = 5000"),     # 1e: '001' stale
                             ((("001", 5000),), "next['001'] = 5000")):
            self._set_next(*pairs)
            before = _tree_snapshot(self.d)
            code, _, err = self.repair("BL-E001-001", "reseed")
            self.assertEqual(code, 2, (pairs, err))
            self.assertIn(named, err)
            self.assertIn("by hand", err)
            self.assertEqual(_tree_snapshot(self.d), before, pairs)

    def test_reseed_merges_every_alias_into_the_canonical_key_by_max(self):
        self.append("A")
        self.append("B", "001", "02")
        self._set_next(("001", 2), (1, 7), ("1", 4))
        code, _, err = self.repair("BL-E001-001", "reseed")
        self.assertEqual(code, 0, err)
        self.assertEqual(dict(self.load_open()["next"]), {"001": 7})
        self.assertEqual(self.audit(), (0, []))

    def test_allocate_reads_only_the_canonical_next_key(self):
        """User decision: an alias never feeds allocation -- audit and reseed deal with it."""
        self.append("A")
        self._set_next((1, 50))
        code, out, err = self.append("B", "001", "02")
        self.assertEqual(code, 0, err)
        self.assertIn("BL-E001-002", out)

    def test_reseed_drops_a_numeric_alias_so_1e_clears(self):
        self.append("A")
        self.append("B", "001", "02")
        self.append("C", "005", "01", "Low", "qa (Q-1)")
        self._set_next((1, 1), ("005", 2))
        self.found("1e", "BL-E001")
        code, _, err = self.repair("BL-E001-001", "reseed")
        self.assertEqual(code, 0, err)
        nxt = self.load_open()["next"]
        self.assertNotIn(1, nxt)
        self.assertEqual(int(nxt["001"]), 3)
        self.assertEqual(self.audit(), (0, []))

    def test_reseed_never_lowers_next_when_dropping_an_alias(self):
        self.append("A")
        self.append("B", "001", "02")
        self._set_next(("001", 50), (1, 1))
        self.found("1e", "BL-E001")
        self.assertEqual(self.repair("BL-E001-001", "reseed")[0], 0)
        self.assertEqual(dict(self.load_open()["next"]), {"001": 50})
        self.assertEqual(self.audit(), (0, []))

    def test_unschedule_refused_on_a_healthy_item(self):
        self.append("A")
        self.promote()
        with open(self.issues, encoding="utf-8") as fh:
            before = fh.read()
        code, _, err = self.repair("BL-E001-001", "unschedule")
        self.assertEqual(code, 2)
        self.assertIn("unschedule: audit finding 1b/1g does not hold for BL-E001-001", err)
        with open(self.issues, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), before)

    def test_link_clears_1d_and_is_refused_for_the_wrong_story(self):
        self.append("A")
        self._crash_promote_before_scheduling(cls="simple")
        code, _, err = self.repair("BL-E001-001", "link")                              # no --story
        self.assertEqual(code, 2)
        self.assertIn("--action link needs --story", err)
        code, _, err = self.repair("BL-E001-001", "link", "--story", "E001-S02-009")
        self.assertEqual(code, 2)
        self.assertIn("link: audit finding 1d does not hold for BL-E001-001 and E001-S02-009", err)
        code, _, err = self.repair("BL-E001-001", "link", "--story", "E001-S02-001")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.audit(), (0, []))
        self.assert_invariants()

    def test_link_event_says_it_came_from_repair(self):
        """link's issue_scheduled event must be distinguishable from promote's."""
        self.append("A")
        self._crash_promote_before_scheduling(cls="simple")     # no event: it stopped first
        code, _, err = self.repair("BL-E001-001", "link", "--story", "E001-S02-001")
        self.assertEqual(code, 0, err)
        ev = self.events("issue_scheduled")
        self.assertEqual(len(ev), 1)
        self.assertEqual((ev[0]["key"], ev[0]["story"], ev[0]["via"]),
                         ("BL-E001-001", "E001-S02-001", "repair-link"))

    def test_reseed_clears_1e(self):
        self.append("A")
        self.append("B", "001", "02")
        self.edit_open(lambda d: d["next"].__setitem__("001", 1))
        self.assertEqual(self.repair("BL-E001-001", "reseed")[0], 0)
        self.assertEqual(int(self.load_open()["next"]["001"]), 3)
        self.assertEqual(self.audit(), (0, []))
        self.assert_invariants()

    def test_reseed_rebuilds_a_malformed_map(self):
        self.append("A")
        self.edit_open(lambda d: d.__setitem__("next", "garbage"))
        self.assertEqual(self.repair("BL-E001-001", "reseed")[0], 0)
        self.assertEqual(int(self.load_open()["next"]["001"]), 2)
        self.assert_invariants()

    def test_reseed_rebuilds_a_malformed_next_for_both_epics_at_once(self):
        # A malformed `next` is rebuilt for EVERY epic with a key in either file, from one
        # reseed. Epic 005's only key is in the resolved file, so its entry has to come from
        # there.
        self.append("A")
        self.append("B", "001", "02")
        self.append("C", "005", "01", "Low", "qa (Q-1)")
        code, _, err = self.run_all(["resolve-issue", "--state-root", self.root, "--key",
                                     "BL-E005-001", "--resolution", "obsolete", "--note", "gone"])
        self.assertEqual(code, 0, err)
        self.edit_open(lambda d: d.__setitem__("next", "garbage"))
        self.assertEqual(self.ids(), {("1e", "next")})
        code, _, err = self.repair("BL-E001-001", "reseed")
        self.assertEqual(code, 0, err)
        self.assertEqual({str(e): int(v) for e, v in self.load_open()["next"].items()},
                         {"001": 3, "005": 2})
        self.assertEqual(self.audit(), (0, []))
        self.assert_invariants()

    def test_reseed_folds_each_epics_aliases_by_max_and_both_epics_end_clean(self):
        # Batch A's alias rule, across two epics. Aliases are merged by max, then removed, and
        # only the named epic's aliases (reseed is per epic). The other epic stays 1e until its
        # own reseed. Both epics then audit clean.
        self.append("A")
        self.append("B", "001", "02")
        self.append("C", "005", "01", "Low", "qa (Q-1)")
        self._set_next(("001", 2), (1, 7), ("005", 1), ("5", 4), ("E005", 3))
        self.assertEqual({f["epic"] for f in self.e1()}, {"001", "005"})       # premise
        self.assertEqual(self.repair("BL-E001-001", "reseed")[0], 0)
        self.assertEqual(dict(self.load_open()["next"]),
                         {"001": 7, "005": 1, "5": 4, "E005": 3})       # 005 not touched
        self.assertEqual({f["epic"] for f in self.e1()}, {"005"})
        self.assertEqual(self.repair("BL-E005-001", "reseed")[0], 0)
        self.assertEqual(dict(self.load_open()["next"]), {"001": 7, "005": 4})
        self.assertEqual(self.audit(), (0, []))
        self.assert_invariants()

    def test_reseed_refused_when_next_is_fine(self):
        self.append("A")
        code, _, err = self.repair("BL-E001-001", "reseed")
        self.assertEqual(code, 2)
        self.assertIn("reseed: audit finding 1e does not hold for epic 001", err)

    def test_reopen_clears_1j(self):
        self.append("A")
        self.promote()
        for st in ("done", "in-progress"):
            self.run_all(["set-status", "--state-root", self.root, "--story", "E001-S02-001",
                          "--status", st])
        code, _, err = self.repair("BL-E001-001", "reopen", "--session-id", "S-4")
        self.assertEqual(code, 0, err)
        item = self.load_open()["backlog"][0]
        self.assertEqual((item["status"], item["story"]), ("scheduled", "E001-S02-001"))
        self.assertNotIn("resolution", item)
        self.assertEqual(self.resolved_keys(), [])
        self.assertEqual(self.events("issue_reopened")[-1]["session"], "S-4")
        self.assertEqual(self.audit(), (0, []))
        self.assert_invariants()

    def test_reopen_refused_without_1j(self):
        self.append("A")
        self.run_all(["resolve-issue", "--state-root", self.root, "--key", "BL-E001-001",
                      "--resolution", "obsolete", "--note", "x"])
        code, _, err = self.repair("BL-E001-001", "reopen")
        self.assertEqual(code, 2)
        self.assertIn("reopen: audit finding 1j does not hold for BL-E001-001", err)

    def test_reopen_interrupted_after_the_open_write_completes_on_rerun(self):
        self.append("A")
        self.promote()
        for st in ("done", "in-progress"):
            self.run_all(["set-status", "--state-root", self.root, "--story", "E001-S02-001",
                          "--status", st])
        with _dump_failing_on(2):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                with self.assertRaises(OSError):
                    pm.main(["repair-issue", "--state-root", self.root, "--key", "BL-E001-001",
                             "--action", "reopen"])
        self.assertEqual(self.repair("BL-E001-001", "reopen")[0], 0)
        self.assertEqual(self.open_keys(), ["BL-E001-001"], "no duplicate open copy")
        self.assertEqual(self.resolved_keys(), [])
        self.assert_invariants()


class TestUnreadableStoryNode(IssueBase):
    """Ruling F1: a story node the walk cannot read is a refusal naming the file, never a
    traceback. promote-issue and repair-issue exit 2 before any write; audit-issues reports it
    through its existing error channel (exit 4; JSON {"findings": [], "error": MSG})."""

    def setUp(self):
        super().setUp()
        self.append("A")
        self.bad = os.path.join(self.root, "active", "epic-001", "sprint-01", "E001-S01-001.yaml")

    def write_story(self, path, text):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def promote(self):
        return self.run_all(["promote-issue", "--state-root", self.root, "--artifacts-root",
                             self.arts, "--key", "BL-E001-001", "--epic", "001", "--sprint", "02",
                             "--classification", "simple"])

    def break_story(self):
        self.write_story(self.bad, "key: 'E001-S01-001'\nresolves: [BL-E001-001\n")

    def test_promote_refuses_an_unparseable_story_node_and_writes_nothing(self):
        self.break_story()
        before = _tree_snapshot(self.d)
        code, out, err = self.promote()
        self.assertEqual(code, 2, (out, err))
        self.assertIn(f"{self.bad} does not parse:", err)
        self.assertIn("-- fix the file by hand", err)
        self.assertNotIn("Traceback", err)
        self.assertEqual(_tree_snapshot(self.d), before)

    def test_repair_refuses_an_unparseable_story_node_and_writes_nothing(self):
        self.edit_next_stale()
        self.break_story()
        before = _tree_snapshot(self.d)
        code, out, err = self.run_all(["repair-issue", "--state-root", self.root, "--key",
                                       "BL-E001-001", "--action", "reseed"])
        self.assertEqual(code, 2, (out, err))
        self.assertIn(f"{self.bad} does not parse:", err)
        self.assertEqual(_tree_snapshot(self.d), before)

    def edit_next_stale(self):
        """A real 1e, so reseed would otherwise act: the refusal is the walk's, not the gate's."""
        y, data = pm._load(self.issues)
        data["next"]["001"] = 1
        pm._atomic_dump(y, data, self.issues)

    def test_audit_reports_an_unparseable_story_node_through_its_error_channel(self):
        self.break_story()
        code, out, err = self.run_all(["audit-issues", "--state-root", self.root,
                                       "--format", "json"])
        self.assertEqual(code, 4, err)
        doc = json.loads(out)
        self.assertEqual(doc["findings"], [])
        self.assertIn(f"{self.bad} does not parse:", doc["error"])
        code, out, err = self.run_all(["audit-issues", "--state-root", self.root])
        self.assertEqual((code, out), (4, ""))
        self.assertIn(f"{self.bad} does not parse:", err)

    # Ruling F4: a node that loads but is not a mapping, or is not valid UTF-8, is refused
    # exactly as a parse error is. name: (file bytes, the reason the refusal must give)
    UNREADABLE = {
        "list":        (b"- key: 'E001-S01-001'\n- resolves: [BL-E001-001]\n", "is not a mapping"),
        "scalar":      (b"just some text\n", "is not a mapping"),
        "invalid-utf8": (b"key: 'E001-S01-001'\ntitle: '\xff\xfe'\n", "is not valid UTF-8"),
    }

    def test_every_unreadable_shape_is_refused_by_every_walking_verb(self):
        for name, (raw, reason) in self.UNREADABLE.items():
            with self.subTest(name):
                self._refused_by_every_walking_verb(name, raw, reason)

    def _refused_by_every_walking_verb(self, name, raw, reason):
        with open(self.bad, "wb") as fh:
            fh.write(raw)
        want = f"{self.bad} {reason}"
        before = _tree_snapshot(self.d)
        code, out, err = self.promote()
        self.assertEqual(code, 2, (name, out, err))
        self.assertIn(want, err, name)
        self.assertIn("-- fix the file by hand", err, name)
        self.assertNotIn("Traceback", err, name)
        self.assertEqual(_tree_snapshot(self.d), before, name)
        self.edit_next_stale()                      # a real 1e: the refusal is the walk's
        before = _tree_snapshot(self.d)
        code, out, err = self.run_all(["repair-issue", "--state-root", self.root, "--key",
                                       "BL-E001-001", "--action", "reseed"])
        self.assertEqual(code, 2, (name, out, err))
        self.assertIn(want, err, name)
        self.assertEqual(_tree_snapshot(self.d), before, name)
        code, out, err = self.run_all(["audit-issues", "--state-root", self.root,
                                       "--format", "json"])
        self.assertEqual(code, 4, (name, err))
        doc = json.loads(out)
        self.assertEqual(doc["findings"], [], name)
        self.assertIn(want, doc["error"], name)

    def test_promote_refuses_a_claimant_with_a_malformed_key(self):
        """The resume path parses the claimant's key: a malformed one raised ValueError."""
        claimant = os.path.join(self.root, "active", "epic-001", "sprint-02", "E001-S02-001.yaml")
        self.write_story(claimant, "key: 'E001-S02'\nepic: 'E001'\nsprint: 'S02'\n"
                                   "status: backlog\nresolves: [BL-E001-001]\n")
        before = _tree_snapshot(self.d)
        code, out, err = self.promote()
        self.assertEqual(code, 2, (out, err))
        self.assertIn(f"story node {claimant} has a malformed key 'E001-S02' -- fix it by hand, "
                      f"then rerun", err)
        self.assertNotIn("Traceback", err)
        self.assertEqual(_tree_snapshot(self.d), before)


class TestIssueInvariants(IssueBase):
    # IssueBase.assert_invariants is only worth calling if it can fail. Each case builds, on
    # purpose, one state that a spec §1.4 invariant forbids, and requires the helper to reject
    # it under that invariant's name.

    def _fresh(self):
        shutil.rmtree(self.root)
        _build_issue_tree(self.root)
        for t in ("A", "B"):
            code, _, err = self.append(t)
            self.assertEqual(code, 0, err)
        self.assert_invariants()                                    # premise: a clean state

    def _edit_open(self, fn):
        y, data = pm._load(self.issues)
        fn(data)
        pm._atomic_dump(y, data, self.issues)

    def test_assert_invariants_rejects_each_forbidden_state(self):
        from ruamel.yaml.comments import CommentedMap

        def in_both_files():            # a resolve that crashed between its two writes
            with _dump_failing_on(2), redirect_stdout(io.StringIO()), \
                    redirect_stderr(io.StringIO()):
                with self.assertRaises(OSError):
                    pm.main(["resolve-issue", "--state-root", self.root, "--key", "BL-E001-001",
                             "--resolution", "obsolete", "--note", "x"])

        def non_canonical(d):
            d["backlog"].append(CommentedMap([("key", "BL-E1-9"), ("epic", "001"),
                                              ("title", "hand"), ("status", "backlog")]))

        cases = [
            ("invariant 1", in_both_files),
            ("invariant 1", lambda: self._edit_open(lambda d: d["backlog"].pop(0))),   # in neither
            ("invariant 5", lambda: self._edit_open(
                lambda d: d["backlog"].append(CommentedMap(d["backlog"][0])))),
            ("invariant 6", lambda: self._edit_open(non_canonical)),
        ]
        for i, (invariant, corrupt) in enumerate(cases):
            with self.subTest(case=i, invariant=invariant):
                self._fresh()
                corrupt()
                with self.assertRaises(AssertionError) as cm:
                    self.assert_invariants()
                self.assertIn(invariant + ":", str(cm.exception))


class TestEventWriteFailure(IssueBase):
    # Spec §6.1 "Events": a failing event write never fails the verb. Here events.jsonl is a
    # directory, so append_event's open() raises inside its catch-all. Each issue verb must
    # still exit 0 and write its state, and must say on stderr that the event was lost.

    def break_events(self):
        p = pm.events_path(self.root)
        if os.path.exists(p):
            os.remove(p)
        os.mkdir(p)
        return p

    def assert_event_lost(self, err, path):
        self.assertIn("pm-status.py: warning — could not append event: ", err)
        self.assertIn(repr(path), err)

    def promote(self):
        code, _, err = self.run_all(["promote-issue", "--state-root", self.root,
                                     "--artifacts-root", self.arts, "--key", "BL-E001-001",
                                     "--epic", "001", "--sprint", "02",
                                     "--classification", "simple"])
        return code, err

    def test_resolve_issue_still_resolves(self):
        self.append("A")
        p = self.break_events()
        code, out, err = self.run_all(["resolve-issue", "--state-root", self.root, "--key",
                                       "BL-E001-001", "--resolution", "obsolete", "--note", "x"])
        self.assertEqual(code, 0, err)
        self.assertEqual((self.open_keys(), self.resolved_keys()), ([], ["BL-E001-001"]))
        self.assert_event_lost(err, p)
        self.assert_invariants()

    def test_update_issue_still_updates(self):
        self.append("A", "001", "01", "Low")
        p = self.break_events()
        code, out, err = self.run_all(["update-issue", "--state-root", self.root, "--key",
                                       "BL-E001-001", "--severity", "High"])
        self.assertEqual(code, 0, err)
        self.assertEqual(self.load_open()["backlog"][0]["severity"], "High")
        self.assert_event_lost(err, p)
        self.assert_invariants()

    def test_promote_issue_still_promotes(self):
        self.append("A")
        p = self.break_events()
        code, err = self.promote()
        self.assertEqual(code, 0, err)
        node = pm.load_node(pm.story_file(self.root, "E001-S02-001"))[1]
        self.assertEqual(list(node["resolves"]), ["BL-E001-001"])
        self.assertIn("estimate", node)
        item = self.load_open()["backlog"][0]
        self.assertEqual((item["status"], item["story"]), ("scheduled", "E001-S02-001"))
        self.assert_event_lost(err, p)
        self.assert_invariants()

    def test_repair_issue_still_repairs(self):
        self.append("A")
        code, err = self.promote()
        self.assertEqual(code, 0, err)
        os.remove(pm.story_file(self.root, "E001-S02-001"))       # 1b: the story is gone
        p = self.break_events()
        code, out, err = self.run_all(["repair-issue", "--state-root", self.root, "--key",
                                       "BL-E001-001", "--action", "unschedule"])
        self.assertEqual(code, 0, err)
        item = self.load_open()["backlog"][0]
        self.assertEqual(item["status"], "backlog")
        self.assertNotIn("story", item)
        self.assert_event_lost(err, p)
        self.assert_invariants()


class TestLockFilesIgnored(IssueBase):
    """Lock files must never be committed. Every lock acquisition ensures
    {state_root}/.gitignore carries `*.lock` -- on every acquisition, not only when a lock
    file is first created, so a project whose lock files already exist is covered on its
    next lock. Best-effort: a failure warns on stderr and never fails the verb."""

    STORY = "E001-S01-001"

    def setUp(self):
        super().setUp()
        # Memoized per process: reset so each test sees a fresh process's behavior.
        pm._LOCK_IGNORE_CHECKED.clear()
        self.addCleanup(pm._LOCK_IGNORE_CHECKED.clear)
        self.gi = os.path.join(self.root, ".gitignore")

    def gi_bytes(self):
        with open(self.gi, "rb") as fh:
            return fh.read()

    def gi_lines(self):
        return self.gi_bytes().decode("utf-8").splitlines()

    def write_story(self):
        p = os.path.join(self.root, "active", "epic-001", "sprint-01", f"{self.STORY}.yaml")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(f"key: '{self.STORY}'\nepic: 'E001'\nsprint: 'S01'\nstatus: in-progress\n")
        return p

    def add_test_run(self):
        return self.run_all(["add-test-run", "--state-root", self.root, "--story", self.STORY,
                             "--command", "pytest -q", "--exit-code", "0"])

    def test_first_lock_creates_gitignore(self):
        code, _, err = self.append("A")
        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.exists(self.issues + ".lock"), "premise: a lock was taken")
        self.assertIn("*.lock", self.gi_lines())

    def test_epic_lock_creates_gitignore(self):
        code, _, err = self.run_all(["set-lock", "--state-root", self.root, "--epic", "E001",
                                     "--session-id", "s1", "--ttl-minutes", "30"])
        self.assertEqual(code, 0, err)
        self.assertIn("*.lock", self.gi_lines())

    def test_second_lock_leaves_bytes_unchanged(self):
        self.append("A")
        before = self.gi_bytes()
        pm._LOCK_IGNORE_CHECKED.clear()          # as a second process would see it
        code, _, err = self.run_all(["set-lock", "--state-root", self.root, "--epic", "E001",
                                     "--session-id", "s1", "--ttl-minutes", "30"])
        self.assertEqual(code, 0, err)
        self.append("B")
        self.assertEqual(self.gi_bytes(), before)

    def test_existing_gitignore_is_appended_once_never_rewritten(self):
        with open(self.gi, "wb") as fh:
            fh.write(b"# team rules\nscratch/\n*.tmp")       # no trailing newline
        self.append("A")
        self.assertEqual(self.gi_bytes(), b"# team rules\nscratch/\n*.tmp\n*.lock\n")
        pm._LOCK_IGNORE_CHECKED.clear()
        self.append("B")
        self.assertEqual(self.gi_bytes(), b"# team rules\nscratch/\n*.tmp\n*.lock\n")

    def test_existing_gitignore_with_the_line_is_untouched(self):
        original = b"*.lock\n# local\nnotes/\n"
        with open(self.gi, "wb") as fh:
            fh.write(original)
        self.append("A")
        self.assertEqual(self.gi_bytes(), original)

    def test_unwritable_target_warns_and_the_verb_still_succeeds(self):
        os.mkdir(self.gi)                         # a directory where the file should be
        code, _, err = self.append("A")
        self.assertEqual(code, 0, err)
        self.assertIn(f"pm-status.py: warning -- could not add *.lock to {self.gi}: ", err)
        self.assertEqual(err.count("could not add *.lock"), 1, err)
        self.assertEqual(self.open_keys(), ["BL-E001-001"], "the verb's state must be written")

    def test_undecodable_gitignore_warns_and_is_left_alone(self):
        original = b"\xff\xfe not utf-8\n"
        with open(self.gi, "wb") as fh:
            fh.write(original)
        code, _, err = self.append("A")
        self.assertEqual(code, 0, err)
        self.assertIn(f"pm-status.py: warning -- could not add *.lock to {self.gi}: ", err)
        self.assertEqual(self.gi_bytes(), original)
        self.assertEqual(self.open_keys(), ["BL-E001-001"])

    def test_add_test_run_sidecar_ignores_at_the_state_root_only(self):
        story = self.write_story()
        code, _, err = self.add_test_run()
        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.exists(story + ".lock"), "premise: the sidecar was taken")
        self.assertIn("*.lock", self.gi_lines())
        for d in (os.path.dirname(story), os.path.join(self.root, "active", "epic-001"),
                  os.path.join(self.root, "active")):
            self.assertFalse(os.path.exists(os.path.join(d, ".gitignore")),
                             f"a .gitignore was created inside {d}")

    def test_read_only_commands_on_a_root_without_issue_files_create_nothing(self):
        for argv in (["list-issues", "--state-root", self.root, "--all", "--format", "json"],
                     ["audit-issues", "--state-root", self.root]):
            code, _, err = self.run_all(argv)
            self.assertEqual(code, 0, err)
        self.assertFalse(os.path.exists(self.gi), "a read-only command created .gitignore")
        self.assertFalse(os.path.exists(self.issues + ".lock"))

    # -- real git ---------------------------------------------------------------------- #
    def git(self, *args, check=True):
        import subprocess
        return subprocess.run(["git", "-C", self.d, *args], capture_output=True, text=True,
                              check=check)

    def init_repo(self):
        if shutil.which("git") is None:
            self.skipTest("git not available")
        self.d = os.path.realpath(self.d)
        self.arts = os.path.join(self.d, "impl")
        self.root = os.path.join(self.arts, "state")
        self.issues = os.path.join(self.root, "issues.yaml")
        self.gi = os.path.join(self.root, ".gitignore")
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.invalid")
        self.git("config", "user.name", "t")
        self.git("config", "commit.gpgsign", "false")

    def test_git_sees_the_gitignore_and_no_lock_files_and_the_gate_still_passes(self):
        self.init_repo()
        self.write_story()
        self.assertEqual(self.append("A")[0], 0)
        self.assertEqual(self.add_test_run()[0], 0)
        porcelain = self.git("status", "--porcelain", "--untracked-files=all").stdout
        paths = [line[3:] for line in porcelain.splitlines()]
        self.assertIn("impl/state/.gitignore", paths)
        self.assertEqual([p for p in paths if p.endswith(".lock")], [], porcelain)
        self.assertTrue(os.path.exists(self.issues + ".lock"), "premise: lock files exist")
        # step-00-activate's gate: the state-root DIRECTORY must not be ignored.
        gate = self.git("check-ignore", "-q", self.root, check=False)
        self.assertEqual(gate.returncode, 1, "the state root must stay NOT ignored")


if __name__ == "__main__":
    unittest.main(verbosity=2)
