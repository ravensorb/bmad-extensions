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


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
PM_STATUS = os.path.join(REPO, "skills", "_shared", "pm-status.py")


class TestGate(unittest.TestCase):
    def test_non_empty_source_with_empty_plan_BLOCKS(self):
        """THE live defect, as a test. A BMad-schema file read by the l3io reader
        yields zero records over a non-empty source: the run must refuse."""
        p, d = _copy("bmad-flat")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        plan = eng.build_plan(eng.gather("l3io-flat", p, p))   # wrong reader on purpose
        self.assertEqual(plan["counts"], {"epic": 0, "sprint": 0, "story": 0})
        msg = eng.gate("l3io-flat", plan, p, p)
        self.assertIsNotNone(msg)
        self.assertIn("BLOCKED", msg)

    def test_empty_source_with_empty_plan_is_allowed(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        (d / "sprint-status.yaml").write_text("", encoding="utf-8")
        self.assertIsNone(eng.gate("l3io-flat", eng.build_plan([]), d, d))

    def test_a_good_plan_passes(self):
        p, d = _copy("l3io-flat")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        plan = eng.build_plan(eng.gather("l3io-flat", p, p))
        self.assertIsNone(eng.gate("l3io-flat", plan, p, p))

    def test_validation_problems_block(self):
        p, d = _copy("l3io-flat")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        plan = eng.build_plan([
            {"kind": "epic", "key": "", "status": "backlog", "title": "", "source": "x"}])
        self.assertIn("BLOCKED", eng.gate("l3io-flat", plan, p, p))


class TestWriteVerifyDispose(unittest.TestCase):
    def _run(self, fixture, layout):
        p, d = _copy(fixture)
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        state = Path(d) / "state"
        plan = eng.build_plan(eng.gather(layout, p, p))
        written, errors = eng.write(plan, state, PM_STATUS)
        return p, d, state, plan, written, errors

    def test_write_creates_every_node(self):
        _, _, state, plan, written, errors = self._run("l3io-flat", "l3io-flat")
        self.assertEqual(errors, [])
        self.assertEqual(written, len(plan["records"]))
        self.assertTrue((state / "active" / "epic-001" / "epic.yaml").exists())
        self.assertTrue((state / "planned" / "epic-002" / "epic.yaml").exists())
        self.assertTrue(
            (state / "active" / "epic-001" / "sprint-01" / "E001-S01-001.yaml").exists())

    def test_verify_against_plan_passes_after_a_good_write(self):
        _, _, state, plan, _, _ = self._run("l3io-flat", "l3io-flat")
        self.assertEqual(eng.verify_against_plan(plan, state), [])

    def test_verify_catches_a_node_corrupted_on_disk(self):
        """Proves verification compares against the PLAN, not against itself."""
        _, _, state, plan, _, _ = self._run("l3io-flat", "l3io-flat")
        (state / "active" / "epic-001" / "epic.yaml").write_text(
            "key: 'E001'\nstatus: backlog\n", encoding="utf-8")
        problems = eng.verify_against_plan(plan, state)
        self.assertTrue(any("E001" in p for p in problems), problems)

    def test_verify_catches_a_missing_node(self):
        _, _, state, plan, _, _ = self._run("l3io-flat", "l3io-flat")
        (state / "planned" / "epic-002" / "epic.yaml").unlink()
        self.assertTrue(any("E002" in p for p in eng.verify_against_plan(plan, state)))

    def test_inferred_nodes_keep_their_origin_through_the_write(self):
        p, d, state, plan, _, errors = self._run("artifacts", "artifacts")
        self.assertEqual(errors, [])
        from ruamel.yaml import YAML
        node = YAML(typ="safe").load(
            (state / "active" / "epic-001" / "sprint-01" / "sprint.yaml")
            .read_text(encoding="utf-8"))
        self.assertEqual(node["origin"], "inferred")

    def test_dispose_renames_and_never_deletes(self):
        p, d, state, plan, _, _ = self._run("l3io-flat", "l3io-flat")
        moved = eng.dispose("l3io-flat", p, p)
        self.assertEqual(moved, [str(p / "sprint-status.yaml")])
        self.assertFalse((p / "sprint-status.yaml").exists())
        self.assertTrue((p / "sprint-status.yaml.legacy").exists())

    def test_dispose_retires_nothing_for_the_artifacts_layout(self):
        p, d, state, plan, _, _ = self._run("artifacts", "artifacts")
        self.assertEqual(eng.dispose("artifacts", p, p), [])
        self.assertTrue(
            (p / "epic-001" / "sprint-01" / "stories" / "E001-S01-001.md").exists())

    def test_the_source_survives_a_blocked_run(self):
        p, d = _copy("bmad-flat")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        before = (p / "sprint-status.yaml").read_text(encoding="utf-8")
        plan = eng.build_plan(eng.gather("l3io-flat", p, p))
        self.assertIsNotNone(eng.gate("l3io-flat", plan, p, p))
        self.assertEqual((p / "sprint-status.yaml").read_text(encoding="utf-8"), before)
        self.assertFalse((p / "sprint-status.yaml.legacy").exists())

    def test_apply_is_idempotent(self):
        p, d, state, plan, written1, _ = self._run("l3io-flat", "l3io-flat")
        written2, errors2 = eng.write(plan, state, PM_STATUS)
        self.assertEqual(errors2, [])
        self.assertEqual(written2, 0, "a second apply must write nothing")

    def test_cli_apply_end_to_end(self):
        p, d = _copy("l3io-flat")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        state = Path(d) / "state"
        code = eng.main([
            "--artifacts", str(p), "--project-root", str(p), "--apply",
            "--state-root", str(state), "--pm-status", PM_STATUS, "--dispose"])
        self.assertEqual(code, 0)
        self.assertTrue((state / "active" / "epic-001" / "epic.yaml").exists())
        self.assertTrue((p / "sprint-status.yaml.legacy").exists())

    def test_cli_apply_on_a_bmad_project_migrates_it_rather_than_blocking(self):
        """detect() picks the right reader, so the BMad project is CONVERTED."""
        p, d = _copy("bmad-flat")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        state = Path(d) / "state"
        code = eng.main([
            "--artifacts", str(p), "--project-root", str(p), "--apply",
            "--state-root", str(state), "--pm-status", PM_STATUS])
        self.assertEqual(code, 0)
        self.assertTrue((state / "active" / "epic-001" / "epic.yaml").exists())


if __name__ == "__main__":
    unittest.main()
