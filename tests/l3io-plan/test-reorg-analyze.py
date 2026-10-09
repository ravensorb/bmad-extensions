#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""reorg-analyze.py -- the measured half of `/l3io-plan reorg`.

Every test here is about the same property: a finding must be re-derivable. The agent that
reads these argues from them, so a signal that is wrong, or right for the wrong reason, is
worse than one that is absent -- it produces a proposal with a confident rationale nobody
can check.
"""
import importlib.util
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(os.path.dirname(HERE)),
                      "skills", "l3io-plan", "scripts", "reorg-analyze.py")
spec = importlib.util.spec_from_file_location("reorg_analyze", SCRIPT)
ra = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ra)


def story(key, hours=0.0, deps=(), cls=""):
    e = {"estimate": {"elapsed_hours": hours}} if hours else {}
    return {"key": key, "status": "backlog", "classification": cls,
            "depends_on": list(deps), **e}


def plan(epics, active=(), archived=()):
    return {
        "planned": epics,
        "active": [{"key": k, "status": "in-progress", "depends_on": []} for k in active],
        "archived": [{"key": k, "status": "done", "depends_on": []} for k in archived],
    }


def epic(key, sprints, deps=()):
    return {"key": key, "status": "backlog", "depends_on": list(deps),
            "estimate": {}, "sprints": sprints}


def sprint(key, stories):
    return {"key": key, "status": "backlog", "estimate": {}, "stories": list(stories)}


def ids(result, fid):
    return [f for f in result["findings"] if f["id"] == fid]


class TestCriticalPath(unittest.TestCase):
    def test_measures_the_chain_not_the_heaviest_single_story(self):
        # THE DESIGN POINT. A reorg can only change SHAPE; it cannot make a story smaller.
        # A lone 40h story is not a critical path -- there is no serialisation in it to
        # remove -- and reporting it as one would aim the proposal at work it cannot help.
        p = plan([epic("E001", [sprint("S01", [
            story("E001-S01-001", 4, ["E001-S01-002"]),
            story("E001-S01-002", 6, ["E001-S01-003"]),
            story("E001-S01-003", 3),
            story("E001-S01-009", 40),          # heaviest story, depends on nothing
        ])])])
        r = ra.analyze(p)
        cp = ids(r, "critical-path")[0]
        self.assertEqual(cp["measured"]["elapsed_hours"], 13.0)
        self.assertEqual(len(cp["nodes"]), 3)
        self.assertNotIn("E001-S01-009", cp["nodes"])

    def test_says_so_when_there_is_no_chain_at_all(self):
        p = plan([epic("E001", [sprint("S01", [story("E001-S01-001", 5)])])])
        r = ra.analyze(p)
        self.assertTrue(ids(r, "no-critical-path"))
        self.assertFalse(ids(r, "critical-path"))

    def test_unestimated_stories_contribute_zero_rather_than_blocking(self):
        # A plan is usually reorganised BEFORE everything is estimated -- which is exactly
        # when its shape is still cheap to change.
        p = plan([epic("E001", [sprint("S01", [
            story("E001-S01-001", 0, ["E001-S01-002"]), story("E001-S01-002", 7),
        ])])])
        self.assertEqual(ids(ra.analyze(p), "critical-path")[0]["measured"]["elapsed_hours"],
                         7.0)


class TestCycles(unittest.TestCase):
    def test_a_story_cycle_is_reported_as_a_blocker(self):
        p = plan([epic("E001", [sprint("S01", [
            story("E001-S01-001", 1, ["E001-S01-002"]),
            story("E001-S01-002", 1, ["E001-S01-001"]),
        ])])])
        r = ra.analyze(p)
        self.assertTrue(ids(r, "cycle"))
        self.assertEqual(r["summary"]["blockers"], len(ids(r, "cycle")))

    def test_an_epic_cycle_is_reported(self):
        p = plan([epic("E001", [], ["E003"]), epic("E003", [], ["E001"])])
        self.assertTrue(ids(ra.analyze(p), "cycle"))

    def test_a_cycle_does_not_hang_or_corrupt_the_critical_path(self):
        # longest_path must stay total on a cyclic graph: a wrong number reported silently
        # would be worse than a short one beside an explicit cycle finding.
        p = plan([epic("E001", [sprint("S01", [
            story("E001-S01-001", 5, ["E001-S01-002"]),
            story("E001-S01-002", 5, ["E001-S01-001"]),
            story("E001-S01-003", 2, ["E001-S01-004"]),
            story("E001-S01-004", 2),
        ])])])
        r = ra.analyze(p)
        self.assertTrue(ids(r, "cycle"))
        self.assertTrue(ids(r, "critical-path") or ids(r, "no-critical-path"))


class TestDanglingAndActive(unittest.TestCase):
    def test_a_dependency_on_nothing_is_a_blocker(self):
        p = plan([epic("E001", [sprint("S01", [story("E001-S01-001", 1, ["E099-S01-001"])])])])
        f = ids(ra.analyze(p), "dangling-dependency")
        self.assertTrue(f)
        self.assertIn("E099-S01-001", f[0]["nodes"])

    def test_a_dependency_on_active_work_is_not_dangling(self):
        p = plan([epic("E001", [sprint("S01", [story("E001-S01-001", 1, ["E005"])])])],
                 active=["E005"])
        r = ra.analyze(p)
        self.assertFalse(ids(r, "dangling-dependency"))
        self.assertTrue(ids(r, "blocked-by-active"))

    def test_a_dependency_on_archived_work_is_satisfied(self):
        p = plan([epic("E001", [sprint("S01", [story("E001-S01-001", 1, ["E004"])])])],
                 archived=["E004"])
        self.assertFalse(ids(ra.analyze(p), "dangling-dependency"))


class TestGuardrails(unittest.TestCase):
    def test_cross_epic_coupling_is_reported_above_the_threshold(self):
        deps = [story(f"E001-S01-00{i}", 1, ["E003-S01-001"]) for i in (1, 2)]
        p = plan([epic("E001", [sprint("S01", deps)]),
                  epic("E003", [sprint("S01", [story("E003-S01-001", 1)])])])
        f = ids(ra.analyze(p), "cross-epic-coupling")
        self.assertTrue(f)
        self.assertEqual(f[0]["measured"]["edges"], 2)

    def test_a_single_crossing_edge_is_not_reported(self):
        p = plan([epic("E001", [sprint("S01", [story("E001-S01-001", 1, ["E003-S01-001"])])]),
                  epic("E003", [sprint("S01", [story("E003-S01-001", 1)])])])
        self.assertFalse(ids(ra.analyze(p), "cross-epic-coupling"),
                         "one crossing edge is ordinary; reporting it would be noise")

    def test_sprint_imbalance_needs_two_sized_sprints(self):
        p = plan([epic("E001", [sprint("S01", [story("E001-S01-001", 2)]),
                                sprint("S02", [story("E001-S02-001", 30)])])])
        f = ids(ra.analyze(p), "sprint-imbalance")
        self.assertTrue(f)
        self.assertEqual(f[0]["measured"]["ratio"], 15.0)

    def test_an_unestimated_sprint_does_not_trigger_imbalance(self):
        # Sized so the ZERO GUARD is the only thing preventing a finding: 30 against 0 would
        # be an infinite ratio if a zero counted as a real size. An earlier version of this
        # test used 2 against 0, which could not have detected the guard's removal because
        # 2 does not reach the ratio threshold either way -- a test that passes for a reason
        # unrelated to what it claims to check.
        p = plan([epic("E001", [sprint("S01", [story("E001-S01-001", 30)]),
                                sprint("S02", [story("E001-S02-001", 0)])])])
        self.assertFalse(ids(ra.analyze(p), "sprint-imbalance"),
                         "a zero is 'not estimated yet', not 'infinitely smaller'")


class TestUnbackedCrossEpicDependency(unittest.TestCase):
    """A crossing edge the phase graph cannot see.

    Phases are built from EPIC-level `depends_on`. A story dependency crossing E001 -> E003
    with no `E001 depends_on E003` behind it leaves both epics in the same parallel phase,
    running concurrently, while one needs the other finished. Nothing caught this before:
    the validator accepted it, step-05 checked only that the story key existed, and this
    analyzer was silent because one crossing edge sits below the coupling threshold.
    """

    def _pair(self, epic_deps=()):
        return plan([
            epic("E001", [sprint("S01", [story("E001-S01-001", 1, ["E003-S01-001"])])],
                 epic_deps),
            epic("E003", [sprint("S01", [story("E003-S01-001", 1)])]),
        ])

    def test_a_single_unbacked_edge_is_reported(self):
        # THE REGRESSION. One edge, previously reported by nothing at all.
        f = ids(ra.analyze(self._pair()), "unbacked-cross-epic-dependency")
        self.assertTrue(f)
        self.assertEqual(f[0]["severity"], "warn")
        self.assertEqual(f[0]["measured"]["stories"], ["E001-S01-001"])

    def test_no_threshold_unlike_coupling(self):
        # Coupling needs >=2 because "is this boundary wrong?" tolerates one edge. This asks
        # whether the epic graph KNOWS about the edge, where one is already an error.
        r = ra.analyze(self._pair())
        self.assertFalse(ids(r, "cross-epic-coupling"), "one edge is below coupling's bar")
        self.assertTrue(ids(r, "unbacked-cross-epic-dependency"), "but not below this one")

    def test_a_backed_edge_is_not_reported(self):
        self.assertFalse(ids(ra.analyze(self._pair(("E003",))),
                             "unbacked-cross-epic-dependency"))

    def test_the_finding_names_the_declaration_that_would_fix_it(self):
        f = ids(ra.analyze(self._pair()), "unbacked-cross-epic-dependency")[0]
        self.assertIn("depends_on", f["suggests"])
        self.assertIn("E003", f["suggests"])

    def test_it_is_reported_alongside_coupling_when_both_apply(self):
        # Two unbacked edges: both findings fire, measuring different things.
        p = plan([
            epic("E001", [sprint("S01", [story("E001-S01-001", 1, ["E003-S01-001"]),
                                         story("E001-S01-002", 1, ["E003-S01-001"])])]),
            epic("E003", [sprint("S01", [story("E003-S01-001", 1)])]),
        ])
        r = ra.analyze(p)
        self.assertTrue(ids(r, "cross-epic-coupling"))
        self.assertEqual(ids(r, "unbacked-cross-epic-dependency")[0]["measured"]["edges"], 2)

    def test_a_dependency_on_active_work_is_not_an_unbacked_edge(self):
        # Active epics are read-only input and carry no planned stories to cross into.
        p = plan([epic("E001", [sprint("S01", [story("E001-S01-001", 1, ["E005"])])])],
                 active=["E005"])
        self.assertFalse(ids(ra.analyze(p), "unbacked-cross-epic-dependency"))


class TestOrphansAreQuestions(unittest.TestCase):
    def test_an_isolated_story_is_a_question_not_a_retirement(self):
        # The single most dangerous thing this script could get wrong: scoring "nothing
        # depends on this" as "delete this" would be confidently wrong about the most
        # valuable story in the plan.
        p = plan([epic("E001", [sprint("S01", [story("E001-S01-001", 3)])])])
        f = ids(ra.analyze(p), "isolated-story")
        self.assertTrue(f)
        self.assertEqual(f[0]["severity"], "question")
        self.assertNotIn("retire", f[0]["suggests"].lower().replace("retirement", ""))
        self.assertIn("NOT a retirement", f[0]["suggests"])

    def test_no_finding_anywhere_recommends_retirement(self):
        p = plan([epic("E001", [sprint("S01", [story("E001-S01-001", 3)])])])
        for f in ra.analyze(p)["findings"]:
            self.assertNotIn("retire this", f["suggests"].lower())


class TestDeterminismAndShape(unittest.TestCase):
    def test_the_same_plan_gives_the_same_findings_twice(self):
        # A proposal whose reasons cannot be re-derived is one nobody can check.
        p = plan([epic("E001", [sprint("S01", [
            story("E001-S01-001", 4, ["E001-S01-002"]), story("E001-S01-002", 6),
        ])])])
        self.assertEqual(json.dumps(ra.analyze(p), sort_keys=True),
                         json.dumps(ra.analyze(p), sort_keys=True))

    def test_every_finding_carries_the_four_required_fields(self):
        p = plan([epic("E001", [sprint("S01", [
            story("E001-S01-001", 1, ["E001-S01-002"]), story("E001-S01-002", 1, ["E099"]),
        ])])])
        for f in ra.analyze(p)["findings"]:
            for k in ("id", "severity", "nodes", "measured", "suggests"):
                self.assertIn(k, f, f"a finding without {k} cannot be argued from")

    def test_an_empty_plan_analyses_cleanly(self):
        r = ra.analyze(plan([]))
        self.assertEqual(r["summary"]["planned_stories"], 0)
        self.assertEqual(r["summary"]["blockers"], 0)

    def test_active_work_is_never_counted_as_planned(self):
        p = plan([epic("E001", [sprint("S01", [story("E001-S01-001", 1)])])], active=["E005"])
        self.assertEqual(ra.analyze(p)["summary"]["planned_epics"], 1)


class TestCli(unittest.TestCase):
    def _run(self, text):
        out, err = io.StringIO(), io.StringIO()
        stdin = sys.stdin
        sys.stdin = io.StringIO(text)
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = ra.main([])
        finally:
            sys.stdin = stdin
        return code, out.getvalue(), err.getvalue()

    def test_non_json_stdin_exits_2_and_names_the_fix(self):
        code, _o, err = self._run("not json")
        self.assertEqual(code, 2)
        self.assertIn("dump-plan", err)

    def test_an_unknown_shape_is_refused_rather_than_guessed(self):
        code, _o, err = self._run('{"something": "else"}')
        self.assertEqual(code, 2)
        self.assertIn("refusing", err.lower())

    def test_valid_dump_plan_output_analyses(self):
        code, out, _e = self._run(json.dumps(plan([])))
        self.assertEqual(code, 0)
        self.assertIn("findings", json.loads(out))


if __name__ == "__main__":
    unittest.main(verbosity=2)
