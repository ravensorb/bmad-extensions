#!/usr/bin/env python3
"""
Tests for pm-status.py — run with: python3 test-pm-status.py  (or `uv run`).
Exercises the sharded split-directory layout resolution, key-based node addressing
(set-status/set-actual/set-estimate/set-field/verify), epic directory moves
(move-epic/archive-epic), the unconverted --file-based commands (locks,
append-issue, self-install), comment/order preservation, the progress ledger,
and verify exit codes.
"""
import io
import os
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


class Base(unittest.TestCase):
    """Minimal fixture: a scratch dir + in-process CLI runner. No status-file
    content is assumed here — commands that need a node tree use
    TestLayoutResolution instead."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
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


class TestListIssues(unittest.TestCase):
    """list-issues reads state-root/issues.yaml; a missing file or a filter set
    matching nothing is success (exit 0), never an error."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
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

    def tearDown(self):
        import shutil
        shutil.rmtree(self.d, ignore_errors=True)

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
            with redirect_stdout(buf):
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
             "--elapsed-hours", "1.8", "--man-hours", "7", "--tokens-k", "355", "--cost", "5.32"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(node["actual"]["tokens_k"], 355)
        self.assertEqual(node["actual"]["man_hours"], 7)

    def test_claude_runtime_still_rejects_na(self):
        code, _ = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "story", "--story", "E001-S01-003",
             "--tokens-k", "N/A", "--runtime", "claude"])
        self.assertEqual(code, 2)

    def test_set_estimate_story_uses_single_values(self):
        code, out = self.run_main(
            ["set-estimate", "--state-root", self.root, "--story", "E001-S01-003",
             "--man-hours", "6", "--time-hours", "1.5", "--tokens-k", "320", "--cost", "4.80"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(node["estimate"]["man_hours"], 6.0)
        self.assertNotIn("man_hours_low", node["estimate"])

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


class TestVerify(TestLayoutResolution):
    """Reuses TestLayoutResolution's tree fixture. Covers cmd_verify against the
    --state-root interface for story/sprint scope. --scope epic is a distinct
    branch (back-reference integrity across the whole subtree, not per-node
    completion) — see TestVerifyEpicScope below."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
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
        actual["tokens_k"] = 120
        actual["cost"] = "$1.10"
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


class TestVerifyEpicScope(TestLayoutResolution):
    """verify --scope epic — deferred from Task 2 (ruling R3), implemented in Task 4
    since it depends on list_sprint_dirs/list_story_files. Unlike story/sprint scope,
    this branch checks only back-reference integrity across the whole epic subtree,
    not per-node completion."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
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
        code, _ = self.run_main(
            ["verify", "--state-root", self.root, "--scope", "epic", "--epic", "E001"])
        self.assertEqual(code, 4)

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
            with redirect_stdout(buf):
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
            with redirect_stdout(buf):
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
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_move_epic_planned_to_active(self):
        new = pm.move_epic(self.root, "E005", "active")
        self.assertTrue(new.endswith("active/epic-005"))
        self.assertTrue(os.path.isdir(new))
        self.assertFalse(os.path.isdir(os.path.join(self.root, "planned", "epic-005")))

    def test_move_epic_preserves_tree(self):
        pm.move_epic(self.root, "E001", "archived")
        self.assertTrue(os.path.exists(os.path.join(
            self.root, "archived", "epic-001", "sprint-01", "E001-S01-003.yaml")))

    def test_move_epic_updates_status_field(self):
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

    def test_version_increments_for_self_install(self):
        self.assertEqual(pm.PM_STATUS_VERSION, "2.0.2")

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

    def tearDown(self):
        import shutil
        shutil.rmtree(self.d, ignore_errors=True)

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
        self.assertNotIn("??", status)  # nothing left untracked by a shutil fallback

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
        self.root = os.path.join(self.d, "state")
        os.makedirs(self.root)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.d, ignore_errors=True)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
