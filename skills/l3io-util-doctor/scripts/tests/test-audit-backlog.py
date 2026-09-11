#!/usr/bin/env python3
"""
Tests for audit-backlog.py. Run with:
  uv run -q --with 'ruamel.yaml>=0.18' python3 skills/l3io-util-doctor/scripts/tests/test-audit-backlog.py
Items are always created through the real pm-status.py CLI, never hand-written.
"""
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "audit-backlog.py")
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
PM = os.path.join(REPO, "skills", "_shared", "pm-status.py")

_spec = importlib.util.spec_from_file_location("audit_backlog", SCRIPT)
ab = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ab)


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.proj = os.path.join(self.d, "proj")
        self.arts = os.path.join(self.proj, "_impl")
        self.state = os.path.join(self.arts, "state")
        os.makedirs(self.state)

    def pm(self, *args):
        p = subprocess.run([sys.executable, PM, *args], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def append(self, title, source, epic="001", sprint="01", severity="Low", description=None):
        argv = ["append-issue", "--state-root", self.state, "--epic", epic, "--sprint", sprint,
                "--title", title, "--source", source, "--severity", severity]
        if description:
            argv += ["--description", description]
        return self.pm(*argv)

    def write(self, rel, text, base=None):
        p = os.path.join(base or self.proj, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        return p

    def run_audit(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = ab.main(["--pm-status", PM, "--state-root", self.state, "--artifacts-root",
                            self.arts, "--project-root", self.proj, "--format", "json"])
        self.assertEqual(code, 0)
        return json.loads(buf.getvalue())

    def verdicts(self):
        return {v["key"]: v for v in self.run_audit()["verdicts"]}


class TestMarkers(Base):
    MARKER = "# bmad-defer: linear scan over the cache. ceiling: <500. upgrade: index.\n"

    def test_marker_removed_is_fixed_candidate(self):
        self.write("src/a.py", "x = 1\n")
        self.append("linear scan over the cache.", "code-marker (src/a.py:3)")
        self.assertEqual(self.verdicts()["BL-E001-001"]["verdict"], "fixed-candidate")

    def test_marker_present_is_open_with_its_line(self):
        self.write("src/a.py", "x = 1\n" + self.MARKER)
        self.append("linear scan over the cache.", "code-marker (src/a.py:9)")
        v = self.verdicts()["BL-E001-001"]
        self.assertEqual(v["verdict"], "open")
        self.assertIn("src/a.py:2", v["evidence"])

    def test_title_text_outside_a_marker_line_does_not_count(self):
        self.write("src/a.py", "# linear scan over the cache, still here\n")
        self.append("linear scan over the cache.", "code-marker (src/a.py:1)")
        self.assertEqual(self.verdicts()["BL-E001-001"]["verdict"], "fixed-candidate")

    def test_marker_embedded_in_a_longer_source_is_recognized(self):
        self.write("src/b.py", "y = 2\n")
        self.append("debug print", "clean-release (code-marker src/b.py:9)")
        self.assertEqual(self.verdicts()["BL-E001-001"]["verdict"], "fixed-candidate")

    def test_deleted_file_is_obsolete_candidate_when_most_files_exist(self):
        self.write("src/b.py", self.MARKER)
        self.write("src/c.py", self.MARKER)
        self.append("linear scan over the cache.", "code-marker (src/gone.py:1)", sprint="01")
        self.append("linear scan over the cache.", "code-marker (src/b.py:1)", sprint="02")
        self.append("linear scan over the cache.", "code-marker (src/c.py:1)", sprint="03")
        self.assertEqual(self.verdicts()["BL-E001-001"]["verdict"], "obsolete-candidate")

    def test_mass_missing_files_suspect_the_project_root(self):
        for i, s in enumerate(("01", "02", "03"), 1):
            self.append(f"thing {i}", f"code-marker (src/missing{i}.py:1)", sprint=s)
        result = self.run_audit()
        self.assertNotIn("obsolete-candidate", {v["verdict"] for v in result["verdicts"]})
        self.assertTrue(any("project-root suspect" in w for w in result["warnings"]))

    def test_marker_path_with_a_space_is_recognized(self):
        self.write("src/my file.py", "x = 1\n")
        self.append("linear scan over the cache.", "code-marker (src/my file.py:3)")
        self.assertEqual(self.verdicts()["BL-E001-001"]["verdict"], "fixed-candidate")

    def test_embedded_marker_path_with_a_space_is_recognized(self):
        self.write("src/my file.py", "x = 1\n")
        self.append("debug print", "clean-release (code-marker src/my file.py:9)")
        self.assertEqual(self.verdicts()["BL-E001-001"]["verdict"], "fixed-candidate")


class TestDuplicates(Base):
    def test_same_epic_lower_severity_is_proposed(self):
        self.append("Missing input validation", "qa (Q-1)", sprint="01", severity="High")
        self.append("Missing input validation", "qa (Q-2)", sprint="02", severity="Low")
        v = self.verdicts()["BL-E001-002"]
        self.assertEqual((v["verdict"], v["ref"]), ("duplicate-candidate", "BL-E001-001"))

    def test_cross_epic_is_not_proposed(self):
        self.append("Missing input validation", "qa (Q-1)", epic="001")
        self.append("Missing input validation", "qa (Q-1)", epic="002")
        self.assertNotEqual(self.verdicts()["BL-E002-001"]["verdict"], "duplicate-candidate")

    def test_higher_severity_is_not_proposed(self):
        self.append("Missing input validation", "qa (Q-1)", sprint="01", severity="Low")
        self.append("Missing input validation", "qa (Q-2)", sprint="02", severity="Critical")
        self.assertNotEqual(self.verdicts()["BL-E001-002"]["verdict"], "duplicate-candidate")

    def test_duplicate_of_a_resolved_wontfix(self):
        self.append("Verbose logging", "qa (Q-1)", sprint="01", severity="Medium")
        self.pm("resolve-issue", "--state-root", self.state, "--key", "BL-E001-001",
                "--resolution", "wontfix", "--note", "by design")
        self.append("Verbose logging", "qa (Q-2)", sprint="02", severity="Low")
        v = self.verdicts()["BL-E001-002"]
        self.assertEqual((v["verdict"], v["ref"]), ("duplicate-candidate", "BL-E001-001"))


class TestPointers(Base):
    def test_see_description(self):
        rel = "_impl/epic-001/sprint-01/closure/review-E001-S01-001.md"
        self.write(rel, "F-1: something\n")
        self.append("A finding", "code-review (E001-S01-001)", description=f"See {rel}")
        v = self.verdicts()["BL-E001-001"]
        self.assertEqual(v["verdict"], "needs-review")
        self.assertTrue(v["pointer"].endswith("review-E001-S01-001.md"))

    def test_code_review_source_derives_the_review_file(self):
        self.write("epic-001/sprint-01/closure/review-E001-S01-002.md", "x\n", base=self.arts)
        self.append("A finding", "code-review (E001-S01-002) — unresolved after 3 fix iterations")
        self.assertTrue(self.verdicts()["BL-E001-001"]["pointer"].endswith("review-E001-S01-002.md"))

    def test_phase_id_searches_only_that_phase_report(self):
        self.write("epic-001/sprint-01/closure/adversarial-review.md", "F-3: real one\n", base=self.arts)
        self.write("epic-001/sprint-01/closure/redteam-report.md", "F-3: other phase\n", base=self.arts)
        self.append("A finding", "adversarial (F-3)")
        self.assertIn("adversarial-review.md:1", self.verdicts()["BL-E001-001"]["pointer"])

    def test_ambiguous_phase_id_is_untraceable(self):
        self.write("epic-001/sprint-01/closure/adversarial-review.md", "F-3\nsee F-3\n", base=self.arts)
        self.append("A finding", "adversarial (F-3)")
        v = self.verdicts()["BL-E001-001"]
        self.assertIsNone(v["pointer"])
        self.assertEqual(v["evidence"], "untraceable")

    def test_epic_level_item_points_into_epic_closure(self):
        self.write("epic-001/epic-closure/redteam-report.md", "R-1: auth bypass\n", base=self.arts)
        self.append("Auth bypass", "epic-redteam (R-1)", sprint="")
        self.assertIn("epic-closure/redteam-report.md:1", self.verdicts()["BL-E001-001"]["pointer"])

    def test_unrecognized_source_is_untraceable_not_an_error(self):
        self.append("Odd", "something nobody writes")
        self.assertEqual(self.verdicts()["BL-E001-001"]["evidence"], "untraceable")


class TestCli(Base):
    def test_json_through_a_subprocess(self):
        self.append("A finding", "qa (Q-1)")
        p = subprocess.run([sys.executable, SCRIPT, "--pm-status", PM, "--state-root", self.state,
                            "--artifacts-root", self.arts, "--project-root", self.proj,
                            "--format", "json"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["verdicts"][0]["key"], "BL-E001-001")

    def test_unlistable_state_exits_2(self):
        with open(os.path.join(self.state, "issues.yaml"), "w", encoding="utf-8") as fh:
            fh.write("backlog: oops\n")
        self.assertEqual(ab.main(["--pm-status", PM, "--state-root", self.state,
                                  "--artifacts-root", self.arts, "--project-root", self.proj]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
