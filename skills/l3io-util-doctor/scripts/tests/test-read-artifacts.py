#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
"""Tests for read-artifacts.py — run with: uv run test-read-artifacts.py"""
import importlib.util
import os
import shutil
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = Path(HERE) / "fixtures" / "artifacts"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(os.path.dirname(HERE), filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rd = _load("read_artifacts", "read-artifacts.py")


class TestParseFrontmatter(unittest.TestCase):
    def test_reads_a_yaml_block(self):
        got = rd.parse_frontmatter("---\nkey: 'A'\nstatus: done\n---\n\n# Body\n")
        self.assertEqual(got, {"key": "A", "status": "done"})

    def test_no_frontmatter_is_empty(self):
        self.assertEqual(rd.parse_frontmatter("# Just a heading\n"), {})

    def test_unterminated_block_is_empty(self):
        self.assertEqual(rd.parse_frontmatter("---\nkey: 'A'\n"), {})

    def test_malformed_yaml_is_empty(self):
        self.assertEqual(rd.parse_frontmatter("---\na: [1,\n---\n"), {})


class TestReadArtifacts(unittest.TestCase):
    def setUp(self):
        self.recs = rd.read(FIXTURE)

    def _by_kind(self, k):
        return [r for r in self.recs if r["kind"] == k]

    def _tmpdir(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        return d

    def test_story_records_come_from_frontmatter(self):
        self.assertEqual({r["key"] for r in self._by_kind("story")},
                         {"E001-S01-001", "E001-S01-002", "E001-S02-001"})
        got = {r["key"]: r["status"] for r in self._by_kind("story")}
        self.assertEqual(got["E001-S01-001"], "done")
        self.assertEqual(got["E001-S01-002"], "review")

    def test_sprints_are_inferred_from_the_directory_structure(self):
        self.assertEqual({r["key"] for r in self._by_kind("sprint")},
                         {"E001-S01", "E001-S02"})

    def test_the_epic_is_inferred(self):
        self.assertEqual({r["key"] for r in self._by_kind("epic")}, {"E001"})

    def test_inferred_nodes_carry_origin_and_a_note(self):
        for r in self._by_kind("sprint") + self._by_kind("epic"):
            self.assertEqual(r["origin"], "inferred")
            self.assertTrue(r["origin_note"].strip(), r["key"])

    def test_story_records_are_NOT_marked_inferred(self):
        for r in self._by_kind("story"):
            self.assertNotIn("origin", r)

    def test_sprint_status_is_derived_from_its_stories(self):
        got = {r["key"]: r["status"] for r in self._by_kind("sprint")}
        # S01 has done + review -> started, not finished
        self.assertEqual(got["E001-S01"], "in-progress")
        # S02 has only ready-for-dev -> nothing started
        self.assertEqual(got["E001-S02"], "backlog")

    def test_epic_status_is_derived_from_its_sprints(self):
        got = {r["key"]: r["status"] for r in self._by_kind("epic")}
        self.assertEqual(got["E001"], "in-progress")

    def test_all_done_stories_make_the_sprint_and_epic_done(self):
        d = self._tmpdir()
        sd = d / "epic-003" / "sprint-01" / "stories"
        sd.mkdir(parents=True)
        (sd / "E003-S01-001.md").write_text(
            "---\nkey: 'E003-S01-001'\ntitle: T\nstatus: done\n---\n", encoding="utf-8")
        got = {r["key"]: r["status"] for r in rd.read(d)}
        self.assertEqual(got["E003-S01"], "done")
        self.assertEqual(got["E003"], "done")

    def test_a_story_without_frontmatter_is_skipped(self):
        d = self._tmpdir()
        sd = d / "epic-004" / "sprint-01" / "stories"
        sd.mkdir(parents=True)
        (sd / "E004-S01-001.md").write_text("# No frontmatter here\n", encoding="utf-8")
        self.assertEqual(rd.read(d), [])

    def test_a_story_with_an_invalid_status_is_skipped(self):
        d = self._tmpdir()
        sd = d / "epic-005" / "sprint-01" / "stories"
        sd.mkdir(parents=True)
        (sd / "E005-S01-001.md").write_text(
            "---\nkey: 'E005-S01-001'\nstatus: wat\n---\n", encoding="utf-8")
        self.assertEqual(rd.read(d), [])

    def test_empty_tree_yields_zero_records(self):
        self.assertEqual(rd.read(self._tmpdir()), [])

    def test_missing_directory_yields_zero_records(self):
        self.assertEqual(rd.read(Path("/nonexistent/artifacts")), [])

    def test_parents_precede_their_children(self):
        kinds = [r["kind"] for r in self.recs]
        self.assertEqual(kinds.index("epic"), 0)
        self.assertLess(kinds.index("sprint"), kinds.index("story"))


if __name__ == "__main__":
    unittest.main()
