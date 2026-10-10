#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["networkx>=3.6"]
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
                      "skills", "l3io-plan", "scripts", "plan-graph.py")
spec = importlib.util.spec_from_file_location("plan_graph", SCRIPT)
pg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pg)


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


class TestDependencyChain(unittest.TestCase):
    def test_measures_the_chain_not_the_heaviest_single_story(self):
        # THE DESIGN POINT, now in hops. A story with no dependencies has no serialisation
        # in it at all, however heavy it is, so it cannot be the longest chain — reporting
        # it as one would point the reader at work the chain has nothing to do with.
        p = plan([epic("E001", [sprint("S01", [
            story("E001-S01-001", 4, ["E001-S01-002"]),
            story("E001-S01-002", 6, ["E001-S01-003"]),
            story("E001-S01-003", 3),
            story("E001-S01-009", 40),          # heaviest story, depends on nothing
        ])])])
        r = pg.analyze(p)
        cp = ids(r, "dependency-chain")[0]
        self.assertEqual(cp["measured"]["hops"], 2, "three stories chained is two hops")
        self.assertEqual(len(cp["nodes"]), 3)
        self.assertNotIn("E001-S01-009", cp["nodes"])

    def test_the_chain_is_identical_with_and_without_estimates(self):
        # WHY HOPS REPLACED HOURS. The weighted path needed data that is usually absent
        # exactly when a plan is cheapest to reshape, so the objective degraded to nothing
        # on the plans that most needed it. Hops are the same measurement either way.
        chain = [story("E001-S01-001", 0, ["E001-S01-002"]),
                 story("E001-S01-002", 0, ["E001-S01-003"]),
                 story("E001-S01-003", 0)]
        bare = plan([epic("E001", [sprint("S01", chain)])])
        priced = plan([epic("E001", [sprint("S01", [
            story("E001-S01-001", 4, ["E001-S01-002"]),
            story("E001-S01-002", 90, ["E001-S01-003"]),
            story("E001-S01-003", 7)])])])
        a, b = ids(pg.analyze(bare), "dependency-chain"), \
            ids(pg.analyze(priced), "dependency-chain")
        self.assertEqual(a[0]["measured"]["hops"], b[0]["measured"]["hops"])
        self.assertEqual(a[0]["nodes"], b[0]["nodes"])

    def test_the_chain_is_reported_as_context_not_as_a_target(self):
        # A reorg never edits depends_on, so no move it can make shortens this chain.
        # Severity must stay info, and the text must not invite the agent to aim at it.
        p = plan([epic("E001", [sprint("S01", [
            story("E001-S01-001", 4, ["E001-S01-002"]), story("E001-S01-002", 6)])])])
        f = ids(pg.analyze(p), "dependency-chain")[0]
        self.assertEqual(f["severity"], "info")
        self.assertIn("cannot shorten it", f["suggests"])

    def test_says_so_when_there_is_no_chain_at_all(self):
        p = plan([epic("E001", [sprint("S01", [story("E001-S01-001", 5)])])])
        r = pg.analyze(p)
        self.assertTrue(ids(r, "no-dependency-chain"))
        self.assertFalse(ids(r, "dependency-chain"))

    def test_an_unestimated_plan_still_yields_actionable_findings(self):
        # THE PREMISE OF THE WHOLE STRUCTURAL REORIENTATION, pinned. A plan with no estimates
        # anywhere must still produce something a proposal can be argued from, because that
        # is the state a plan is usually in when its shape is cheapest to change.
        p = plan([
            epic("E001", [sprint("S01", [story("E001-S01-001", 0, ["E003-S01-001"]),
                                         story("E001-S01-002", 0, ["E003-S01-001"])])]),
            epic("E003", [sprint("S01", [story("E003-S01-001", 0)])]),
        ])
        r = pg.analyze(p)
        actionable = [f for f in r["findings"] if f["severity"] in ("blocker", "warn")]
        self.assertTrue(actionable, "a reorg must be arguable before anything is estimated")
        self.assertIn("cross-epic-coupling", [f["id"] for f in actionable])


class TestCycles(unittest.TestCase):
    def test_a_story_cycle_is_reported_as_a_blocker(self):
        p = plan([epic("E001", [sprint("S01", [
            story("E001-S01-001", 1, ["E001-S01-002"]),
            story("E001-S01-002", 1, ["E001-S01-001"]),
        ])])])
        r = pg.analyze(p)
        self.assertTrue(ids(r, "cycle"))
        self.assertEqual(r["summary"]["blockers"], len(ids(r, "cycle")))

    def test_an_epic_cycle_is_reported(self):
        p = plan([epic("E001", [], ["E003"]), epic("E003", [], ["E001"])])
        self.assertTrue(ids(pg.analyze(p), "cycle"))

    def test_a_cycle_does_not_hang_or_corrupt_the_critical_path(self):
        # longest_path must stay total on a cyclic graph: a wrong number reported silently
        # would be worse than a short one beside an explicit cycle finding.
        p = plan([epic("E001", [sprint("S01", [
            story("E001-S01-001", 5, ["E001-S01-002"]),
            story("E001-S01-002", 5, ["E001-S01-001"]),
            story("E001-S01-003", 2, ["E001-S01-004"]),
            story("E001-S01-004", 2),
        ])])])
        r = pg.analyze(p)
        self.assertTrue(ids(r, "cycle"))
        self.assertTrue(ids(r, "dependency-chain") or ids(r, "no-dependency-chain"))


class TestDanglingAndActive(unittest.TestCase):
    def test_a_dependency_on_nothing_is_a_blocker(self):
        p = plan([epic("E001", [sprint("S01", [story("E001-S01-001", 1, ["E099-S01-001"])])])])
        f = ids(pg.analyze(p), "dangling-dependency")
        self.assertTrue(f)
        self.assertIn("E099-S01-001", f[0]["nodes"])

    def test_a_dependency_on_active_work_is_not_dangling(self):
        p = plan([epic("E001", [sprint("S01", [story("E001-S01-001", 1, ["E005"])])])],
                 active=["E005"])
        r = pg.analyze(p)
        self.assertFalse(ids(r, "dangling-dependency"))
        self.assertTrue(ids(r, "blocked-by-active"))

    def test_a_dependency_on_archived_work_is_satisfied(self):
        p = plan([epic("E001", [sprint("S01", [story("E001-S01-001", 1, ["E004"])])])],
                 archived=["E004"])
        self.assertFalse(ids(pg.analyze(p), "dangling-dependency"))


class TestGuardrails(unittest.TestCase):
    def test_cross_epic_coupling_is_reported_above_the_threshold(self):
        deps = [story(f"E001-S01-00{i}", 1, ["E003-S01-001"]) for i in (1, 2)]
        p = plan([epic("E001", [sprint("S01", deps)]),
                  epic("E003", [sprint("S01", [story("E003-S01-001", 1)])])])
        f = ids(pg.analyze(p), "cross-epic-coupling")
        self.assertTrue(f)
        self.assertEqual(f[0]["measured"]["edges"], 2)

    def test_a_single_crossing_edge_is_not_reported(self):
        p = plan([epic("E001", [sprint("S01", [story("E001-S01-001", 1, ["E003-S01-001"])])]),
                  epic("E003", [sprint("S01", [story("E003-S01-001", 1)])])])
        self.assertFalse(ids(pg.analyze(p), "cross-epic-coupling"),
                         "one crossing edge is ordinary; reporting it would be noise")

    def test_sprint_imbalance_needs_two_sized_sprints(self):
        p = plan([epic("E001", [sprint("S01", [story("E001-S01-001", 2)]),
                                sprint("S02", [story("E001-S02-001", 30)])])])
        f = ids(pg.analyze(p), "sprint-imbalance")
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
        self.assertFalse(ids(pg.analyze(p), "sprint-imbalance"),
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
        f = ids(pg.analyze(self._pair()), "unbacked-cross-epic-dependency")
        self.assertTrue(f)
        self.assertEqual(f[0]["severity"], "warn")
        self.assertEqual(f[0]["measured"]["stories"], ["E001-S01-001"])

    def test_no_threshold_unlike_coupling(self):
        # Coupling needs >=2 because "is this boundary wrong?" tolerates one edge. This asks
        # whether the epic graph KNOWS about the edge, where one is already an error.
        r = pg.analyze(self._pair())
        self.assertFalse(ids(r, "cross-epic-coupling"), "one edge is below coupling's bar")
        self.assertTrue(ids(r, "unbacked-cross-epic-dependency"), "but not below this one")

    def test_a_backed_edge_is_not_reported(self):
        self.assertFalse(ids(pg.analyze(self._pair(("E003",))),
                             "unbacked-cross-epic-dependency"))

    def test_the_finding_names_the_declaration_that_would_fix_it(self):
        f = ids(pg.analyze(self._pair()), "unbacked-cross-epic-dependency")[0]
        self.assertIn("depends_on", f["suggests"])
        self.assertIn("E003", f["suggests"])

    def test_it_is_reported_alongside_coupling_when_both_apply(self):
        # Two unbacked edges: both findings fire, measuring different things.
        p = plan([
            epic("E001", [sprint("S01", [story("E001-S01-001", 1, ["E003-S01-001"]),
                                         story("E001-S01-002", 1, ["E003-S01-001"])])]),
            epic("E003", [sprint("S01", [story("E003-S01-001", 1)])]),
        ])
        r = pg.analyze(p)
        self.assertTrue(ids(r, "cross-epic-coupling"))
        self.assertEqual(ids(r, "unbacked-cross-epic-dependency")[0]["measured"]["edges"], 2)

    def test_a_dependency_on_active_work_is_not_an_unbacked_edge(self):
        # Active epics are read-only input and carry no planned stories to cross into.
        p = plan([epic("E001", [sprint("S01", [story("E001-S01-001", 1, ["E005"])])])],
                 active=["E005"])
        self.assertFalse(ids(pg.analyze(p), "unbacked-cross-epic-dependency"))


class TestUnneededEpicDependency(unittest.TestCase):
    """The signal a reorg produces, and the one it cannot act on itself.

    A reorg removes dependencies crossing an epic boundary, but cannot edit epic-level
    `depends_on` — the target format has no field for it. So the declaration outlives the
    edges that earned it, phases come from the declaration, and the parallelism the reorg
    was for never arrives.
    """

    def _pair(self, epic_deps=(), story_deps=()):
        return plan([
            epic("E001", [sprint("S01", [story("E001-S01-001", 1, story_deps)])], epic_deps),
            epic("E003", [sprint("S01", [story("E003-S01-001", 1)])]),
        ])

    def test_fires_when_no_story_edge_justifies_the_declaration(self):
        f = ids(pg.analyze(self._pair(epic_deps=("E003",))), "unneeded-epic-dependency")
        self.assertTrue(f)
        self.assertEqual(f[0]["nodes"], ["E001", "E003"])
        self.assertEqual(f[0]["measured"]["edges"], 0)

    def test_silent_while_a_story_edge_justifies_it(self):
        self.assertFalse(ids(pg.analyze(self._pair(epic_deps=("E003",),
                                                   story_deps=("E003-S01-001",))),
                             "unneeded-epic-dependency"))

    def test_silent_when_the_epic_declares_nothing(self):
        self.assertFalse(ids(pg.analyze(self._pair()), "unneeded-epic-dependency"))

    def test_it_is_info_and_never_warn(self):
        # THE ROUTING CONSTRAINT. The plan-run advisory maps `warn` to "run /l3io-plan
        # reorg", and reorg is exactly the tool that cannot fix this — it never edits
        # epic-level depends_on. At `warn` this would point a user at a refusal.
        f = ids(pg.analyze(self._pair(epic_deps=("E003",))), "unneeded-epic-dependency")
        self.assertEqual(f[0]["severity"], "info")

    def test_a_dangling_declaration_is_left_to_the_dangling_finding(self):
        # depends_on an epic that does not exist is a different problem with its own report.
        r = pg.analyze(self._pair(epic_deps=("E099",)))
        self.assertFalse(ids(r, "unneeded-epic-dependency"))
        self.assertTrue(ids(r, "dangling-dependency"))

    def test_it_never_recommends_dropping_without_the_caveat(self):
        # An epic dependency can encode sequencing no story edge expresses.
        f = ids(pg.analyze(self._pair(epic_deps=("E003",))), "unneeded-epic-dependency")[0]
        self.assertIn("sequencing decision", f["suggests"])


class TestOrphansAreQuestions(unittest.TestCase):
    def test_an_isolated_story_is_a_question_not_a_retirement(self):
        # The single most dangerous thing this script could get wrong: scoring "nothing
        # depends on this" as "delete this" would be confidently wrong about the most
        # valuable story in the plan.
        p = plan([epic("E001", [sprint("S01", [story("E001-S01-001", 3)])])])
        f = ids(pg.analyze(p), "isolated-story")
        self.assertTrue(f)
        self.assertEqual(f[0]["severity"], "question")
        self.assertNotIn("retire", f[0]["suggests"].lower().replace("retirement", ""))
        self.assertIn("NOT a retirement", f[0]["suggests"])

    def test_no_finding_anywhere_recommends_retirement(self):
        p = plan([epic("E001", [sprint("S01", [story("E001-S01-001", 3)])])])
        for f in pg.analyze(p)["findings"]:
            self.assertNotIn("retire this", f["suggests"].lower())


class TestDeterminismAndShape(unittest.TestCase):
    def test_the_same_plan_gives_the_same_findings_twice(self):
        # A proposal whose reasons cannot be re-derived is one nobody can check.
        p = plan([epic("E001", [sprint("S01", [
            story("E001-S01-001", 4, ["E001-S01-002"]), story("E001-S01-002", 6),
        ])])])
        self.assertEqual(json.dumps(pg.analyze(p), sort_keys=True),
                         json.dumps(pg.analyze(p), sort_keys=True))

    def test_every_finding_carries_the_four_required_fields(self):
        p = plan([epic("E001", [sprint("S01", [
            story("E001-S01-001", 1, ["E001-S01-002"]), story("E001-S01-002", 1, ["E099"]),
        ])])])
        for f in pg.analyze(p)["findings"]:
            for k in ("id", "severity", "nodes", "measured", "suggests"):
                self.assertIn(k, f, f"a finding without {k} cannot be argued from")

    def test_an_empty_plan_analyses_cleanly(self):
        r = pg.analyze(plan([]))
        self.assertEqual(r["summary"]["planned_stories"], 0)
        self.assertEqual(r["summary"]["blockers"], 0)

    def test_active_work_is_never_counted_as_planned(self):
        p = plan([epic("E001", [sprint("S01", [story("E001-S01-001", 1)])])], active=["E005"])
        self.assertEqual(pg.analyze(p)["summary"]["planned_epics"], 1)


class TestCli(unittest.TestCase):
    def _run(self, text):
        out, err = io.StringIO(), io.StringIO()
        stdin = sys.stdin
        sys.stdin = io.StringIO(text)
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = pg.main(['analyze'])
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


class TestPhases(unittest.TestCase):
    """The execution order, which used to be an agent running Kahn's algorithm from prose.

    This is the computation that decides what runs CONCURRENTLY, which made it the worst
    candidate in the system for being done from memory, every plan run, over the whole epic
    set.
    """

    def _plan(self, *epics):
        return {"planned": [{"key": k, "status": "backlog", "depends_on": list(d),
                             "estimate": {}, "sprints": []} for k, d in epics],
                "active": [], "archived": []}

    def test_generations_group_epics_by_when_they_may_run(self):
        r = pg.phases(self._plan(("E001", []), ("E002", []),
                                 ("E003", ["E001", "E002"]), ("E004", ["E003"])))
        self.assertEqual([p["epics"] for p in r["phases"]],
                         [["E001", "E002"], ["E003"], ["E004"]])
        self.assertEqual(r["phase_count"], 3)
        self.assertEqual(r["epic_count"], 4)

    def test_parallel_means_more_than_one_epic_and_nothing_else(self):
        # The old prose said "more than one epic, OR a single-epic phase with no ordering
        # constraint", and its own worked example then marked one single-epic phase parallel
        # and another sequential — the rule and the example disagreed. It never mattered,
        # because l3io-execute's epic loop guards on `parallel_flag=true AND len(epics) > 1`
        # independently. Meaning the one thing it can act on removes the contradiction.
        r = pg.phases(self._plan(("E001", []), ("E002", []), ("E003", ["E001", "E002"])))
        self.assertEqual([p["parallel"] for p in r["phases"]], [True, False])

    def test_a_lone_epic_with_no_dependencies_is_not_parallel(self):
        r = pg.phases(self._plan(("E001", [])))
        self.assertEqual(r["phases"][0]["parallel"], False,
                         "one epic cannot run concurrently with itself")

    def test_each_phase_records_what_it_waited_for(self):
        r = pg.phases(self._plan(("E001", []), ("E002", []), ("E003", ["E001", "E002"])))
        self.assertEqual(r["phases"][0]["dependencies"], [])
        self.assertEqual(r["phases"][1]["dependencies"], ["E001", "E002"])

    def test_a_dependency_outside_the_planned_set_does_not_order_a_phase(self):
        # Active and archived epics are read-only context; they carry no phase of their own.
        r = pg.phases(self._plan(("E001", ["E099"]), ("E002", [])))
        self.assertEqual(r["phases"][0]["epics"], ["E001", "E002"])

    def test_a_cycle_emits_no_phases_and_says_why(self):
        # A cyclic graph has no topological order at all. Emitting a plausible-looking one
        # would be worse than emitting none, because execution would act on it.
        r = pg.phases(self._plan(("E001", ["E002"]), ("E002", ["E001"])))
        self.assertEqual(r["phases"], [])
        self.assertIn("cycle", r["error"])

    def test_an_empty_plan_yields_no_phases_and_no_error(self):
        r = pg.phases({"planned": [], "active": [], "archived": []})
        self.assertEqual(r["phases"], [])
        self.assertNotIn("error", r)

    def test_the_same_plan_yields_the_same_phases_twice(self):
        p = self._plan(("E003", []), ("E001", []), ("E002", ["E001", "E003"]))
        self.assertEqual(json.dumps(pg.phases(p), sort_keys=True),
                         json.dumps(pg.phases(p), sort_keys=True))

    def test_the_cli_emits_phases(self):
        out, err = io.StringIO(), io.StringIO()
        stdin = sys.stdin
        sys.stdin = io.StringIO(json.dumps(self._plan(("E001", []))))
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = pg.main(["phases"])
        finally:
            sys.stdin = stdin
        self.assertEqual(code, 0, err.getvalue())
        self.assertEqual(json.loads(out.getvalue())["phase_count"], 1)

if __name__ == "__main__":
    unittest.main(verbosity=2)
