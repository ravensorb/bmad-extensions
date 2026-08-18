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
            with redirect_stdout(buf):
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
        self.root = os.path.join(self.d, "state")
        os.makedirs(self.root)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.d, ignore_errors=True)

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
        pm.record_story_sample(self.root, self._story(0))
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(cal["version"], pm.CALIBRATION_SCHEMA_VERSION)
        self.assertTrue(os.path.exists(p + ".v1"))
        # migration seeds scope["complex"]["man_hours"] with the old blended
        # ratio as one sample; record_story_sample appends a second on top —
        # proof the migrated structure, not a corrupted v1 shape, took the write.
        self.assertEqual(len(pm._component_samples(cal, "scope", "complex", "man_hours")), 2)
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

    def test_zero_estimated_overhead_skips_the_metric(self):
        # parent estimated exactly its children -> nothing to measure against
        self._sprint_with_stories([3.0, 4.0], 9.0,
                                  {"man_hours_low": 7.0, "man_hours_high": 7.0},
                                  story_estimates=[3.0, 4.0])
        s, _ = pm.derive_closure_sample(self.root, "sprint", "E001", "S01")
        self.assertNotIn("man_hours", s["ratios"])
        self.assertIn("man_hours", s["skipped"])

    def test_dollar_prefixed_cost_contributes_to_closure_sample(self):
        # RULING A: cost is stored '$'-prefixed (metrics-contract.md §9); the
        # numeric guard must not drop it before the '$' is stripped, or cost
        # closure samples never accumulate under real data.
        sd = os.path.join(self.root, "active", "epic-001", "sprint-01")
        for f in os.listdir(sd):
            if f.endswith(".yaml") and f != "sprint.yaml":
                os.remove(os.path.join(sd, f))
        self._write(os.path.join(sd, "E001-S01-001.yaml"),
                    {"key": "E001-S01-001", "epic": "E001", "sprint": "S01",
                     "status": "done", "actual": {"cost": "$3.00"}})
        self._write(os.path.join(sd, "E001-S01-002.yaml"),
                    {"key": "E001-S01-002", "epic": "E001", "sprint": "S01",
                     "status": "done", "actual": {"cost": "$4.00"}})
        self._write(os.path.join(sd, "sprint.yaml"),
                    {"key": "S01", "epic": "E001", "status": "done",
                     "actual": {"cost": "$9.00"},
                     "estimate": {"cost_low": 1.0, "cost_high": 3.0}})
        s, reason = pm.derive_closure_sample(self.root, "sprint", "E001", "S01")
        self.assertIsNotNone(s, reason)
        self.assertAlmostEqual(s["closure_actual"]["cost"], 2.0)

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
        pm.record_closure_sample(self.root, "sprint", "E001", "S01")
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(cal["version"], pm.CALIBRATION_SCHEMA_VERSION)
        self.assertTrue(os.path.exists(p + ".v1"))
        self.assertEqual(len(pm._component_samples(cal, "closure", "sprint", "man_hours")), 1)


class TestSetActualCalibrates(TestLayoutResolution):
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
        code, out = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "story",
             "--story", "E001-S01-003", "--man-hours", "7"])
        self.assertEqual(code, 0, out)          # actuals are primary
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(node["actual"]["man_hours"], 7)

    def test_claude_runtime_still_rejects_na(self):
        self._estimated_story()
        code, _ = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "story",
             "--story", "E001-S01-003", "--tokens-na", "--runtime", "claude"])
        self.assertEqual(code, 2)


class TestEstimateStory(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
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
            with redirect_stdout(buf):
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
        # standard band 40-100, midpoint 70, x scope 1.0 x fix 1.25 = 88 total
        self.assertEqual(int(tk["total"]), 88)
        self.assertEqual(sum(int(tk[c]) for c in pm.TOKEN_CLASSES), 88)
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
            with redirect_stdout(buf):
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

    def tearDown(self):
        import shutil
        shutil.rmtree(self.d, ignore_errors=True)

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
            with redirect_stdout(buf):
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
        code, out = self.run_main(["rates", "--model", "nope"])
        self.assertEqual(code, 2, out)


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
