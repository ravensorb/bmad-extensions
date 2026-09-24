#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
"""Tests for migrate-engine.py — run with: uv run test-engine.py"""
import importlib.util
import os
import shutil
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = Path(HERE) / "fixtures"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(os.path.dirname(HERE), filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


eng = _load("migrate_engine", "migrate-engine.py")


def _copy(name):
    """Copy a fixture into a temp dir. Returns (project_path, tempdir_to_remove)."""
    d = Path(tempfile.mkdtemp())
    shutil.copytree(FIXTURES / name, d / "proj")
    return d / "proj", d


class TestFixtureCorpus(unittest.TestCase):
    def test_every_fixture_directory_has_a_reader(self):
        """Deleting a fixture must fail the suite, not silently shrink the corpus."""
        on_disk = {p.name for p in FIXTURES.iterdir()
                   if p.is_dir() and not p.name.startswith(".")}
        self.assertEqual(on_disk, set(eng.READERS), "fixture set != reader set")

    def test_the_corpus_has_all_five_layouts(self):
        self.assertEqual(len(eng.READERS), 5)


class TestDetect(unittest.TestCase):
    def _detect(self, fixture):
        p, d = _copy(fixture)
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        return eng.detect(p, p)

    def test_l3io_flat(self):
        self.assertEqual(self._detect("l3io-flat"), "l3io-flat")

    def test_bmad_flat(self):
        self.assertEqual(self._detect("bmad-flat"), "bmad-flat")

    def test_split(self):
        self.assertEqual(self._detect("split"), "split")

    def test_per_epic(self):
        self.assertEqual(self._detect("per-epic"), "per-epic")

    def test_artifacts(self):
        self.assertEqual(self._detect("artifacts"), "artifacts")

    def test_nothing_present(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        self.assertEqual(eng.detect(d, d), "none")

    def test_split_wins_over_flat_because_both_carry_sprint_status(self):
        p, d = _copy("split")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        self.assertTrue((p / "sprint-status.yaml").is_file())
        self.assertEqual(eng.detect(p, p), "split")


class TestGatherAndPlan(unittest.TestCase):
    def test_l3io_flat_plan_counts(self):
        p, d = _copy("l3io-flat")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        plan = eng.build_plan(eng.gather("l3io-flat", p, p))
        self.assertEqual(plan["counts"], {"epic": 2, "sprint": 2, "story": 3})
        self.assertEqual(plan["problems"], [])

    def test_bmad_flat_plan_counts(self):
        p, d = _copy("bmad-flat")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        plan = eng.build_plan(eng.gather("bmad-flat", p, p))
        self.assertEqual(plan["counts"], {"epic": 2, "sprint": 0, "story": 3})

    def test_a_plan_orders_parents_before_children(self):
        """import-node exits 3 on a sprint whose epic is absent, so order matters."""
        p, d = _copy("l3io-flat")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        kinds = [r["kind"]
                 for r in eng.build_plan(eng.gather("l3io-flat", p, p))["records"]]
        self.assertEqual(kinds, sorted(kinds, key=["epic", "sprint", "story"].index))

    def test_invalid_records_are_reported_as_problems(self):
        plan = eng.build_plan([
            {"kind": "epic", "key": "", "status": "backlog", "title": "", "source": "x"}])
        self.assertTrue(plan["problems"])

    def test_an_unknown_layout_gathers_nothing(self):
        p, d = _copy("l3io-flat")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        self.assertEqual(eng.gather("no-such-layout", p, p), [])

    def test_source_is_empty_is_false_when_the_file_has_content(self):
        p, d = _copy("bmad-flat")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        self.assertFalse(eng.source_is_empty("l3io-flat", p, p))

    def test_source_is_empty_is_true_for_an_empty_file(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        (d / "sprint-status.yaml").write_text("", encoding="utf-8")
        self.assertTrue(eng.source_is_empty("l3io-flat", d, d))

    def test_render_plan_names_the_layout_and_the_counts(self):
        p, d = _copy("l3io-flat")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        text = eng.render_plan("l3io-flat", eng.build_plan(eng.gather("l3io-flat", p, p)))
        self.assertIn("l3io-flat", text)
        self.assertIn("epics", text)


if __name__ == "__main__":
    unittest.main()
