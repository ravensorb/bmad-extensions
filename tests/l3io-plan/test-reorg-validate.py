#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
"""reorg-validate.py -- the only thing between an agent's proposal and the user's state tree.

Every test here plants something a validator could wave through. A validator that shrugs at
a field it does not understand, or at a story nobody mentioned, is exactly the hole the
target format exists to close -- so each refusal gets a test, and each acceptance gets one
too, because a validator that refuses everything is equally useless.
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(os.path.dirname(HERE)),
                      "skills", "l3io-plan", "scripts", "reorg-validate.py")
spec = importlib.util.spec_from_file_location("reorg_validate", SCRIPT)
rv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rv)


def story(key, deps=()):
    return {"key": key, "status": "backlog", "classification": "",
            "depends_on": list(deps), "estimate": {}}


def sprint(key, stories):
    return {"key": key, "status": "backlog", "estimate": {}, "stories": list(stories)}


def epic(key, sprints, deps=()):
    return {"key": key, "status": "backlog", "depends_on": list(deps),
            "estimate": {}, "sprints": sprints}


def plan(epics, active=(), archived=()):
    return {"planned": epics,
            "active": [{"key": k, "status": "in-progress", "depends_on": []} for k in active],
            "archived": [{"key": k, "status": "done", "depends_on": []} for k in archived]}


# Two planned epics, three stories, one dependency. The baseline every case varies from.
BASE = plan([
    epic("E001", [sprint("S01", [story("E001-S01-001"),
                                 story("E001-S01-002", ["E001-S01-001"])])]),
    epic("E003", [sprint("S01", [story("E003-S01-001")])]),
])

TOTAL = [
    {"key": "E001-S01-001", "epic": "E001", "sprint": "S01", "order": 1},
    {"key": "E001-S01-002", "epic": "E001", "sprint": "S01", "order": 2},
    {"key": "E003-S01-001", "epic": "E003", "sprint": "S01", "order": 1},
]


def why(errs):
    return " | ".join(e["why"] for e in errs)


class TestAcceptance(unittest.TestCase):
    def test_an_unchanged_total_target_is_valid(self):
        self.assertEqual(rv.validate(BASE, {"target": TOTAL}), [])

    def test_a_real_move_is_valid(self):
        rows = [dict(r) for r in TOTAL]
        rows[0] = {"key": "E001-S01-001", "epic": "E003", "sprint": "S01", "order": 2}
        self.assertEqual(rv.validate(BASE, {"target": rows}), [])

    def test_order_may_have_gaps_and_is_not_required_to_be_dense(self):
        rows = [dict(r) for r in TOTAL]
        rows[0]["order"] = 10
        rows[1]["order"] = 90
        self.assertEqual(rv.validate(BASE, {"target": rows}), [])


class TestDriftIsUnrepresentable(unittest.TestCase):
    """The whole safety argument for handing a target tree to an agent."""

    def _with(self, field, value):
        rows = [dict(r) for r in TOTAL]
        rows[0][field] = value
        return rv.validate(BASE, {"target": rows})

    def test_a_title_is_refused(self):
        self.assertIn("title", why(self._with("title", "reworded")))

    def test_an_estimate_is_refused(self):
        self.assertIn("estimate", why(self._with("estimate", {"elapsed_hours": 99})))

    def test_a_dependency_edit_is_refused(self):
        self.assertIn("depends_on", why(self._with("depends_on", [])))

    def test_a_destination_key_is_refused(self):
        # The agent must never name a new key; the allocator assigns every one.
        self.assertIn("new_key", why(self._with("new_key", "E003-S01-009")))

    def test_an_unknown_top_level_section_is_refused(self):
        errs = rv.validate(BASE, {"target": TOTAL, "rationale": "because"})
        self.assertIn("rationale", why(errs))

    def test_the_refusal_names_the_offending_row(self):
        errs = self._with("title", "x")
        self.assertTrue(any(e["where"].startswith("target[") for e in errs))


class TestTotality(unittest.TestCase):
    def test_an_omitted_story_is_an_error_not_an_implied_leave_alone(self):
        errs = rv.validate(BASE, {"target": TOTAL[:2]})
        self.assertIn("E003-S01-001", why(errs) + " ".join(e["where"] for e in errs))
        self.assertIn("never an implied", why(errs))

    def test_a_duplicated_story_is_refused(self):
        rows = [*TOTAL, dict(TOTAL[0])]
        self.assertIn("more than once", why(rv.validate(BASE, {"target": rows})))

    def test_a_story_inside_a_retired_epic_need_not_be_placed(self):
        rows = [r for r in TOTAL if not r["key"].startswith("E003")]
        errs = rv.validate(BASE, {"target": rows,
                                  "retire": [{"key": "E003", "reason": "obsolete"}]})
        self.assertEqual(errs, [])

    def test_a_story_both_placed_and_inside_a_retired_epic_is_refused(self):
        errs = rv.validate(BASE, {"target": TOTAL,
                                  "retire": [{"key": "E003", "reason": "obsolete"}]})
        self.assertIn("also inside a retired epic", why(errs))


class TestKeysMustResolve(unittest.TestCase):
    def test_an_unknown_story_key_is_refused(self):
        rows = [*TOTAL, {"key": "E099-S01-001", "epic": "E001", "sprint": "S01", "order": 9}]
        self.assertIn("not a planned story", why(rv.validate(BASE, {"target": rows})))

    def test_retiring_something_that_is_not_a_planned_epic_is_refused(self):
        errs = rv.validate(BASE, {"target": TOTAL,
                                  "retire": [{"key": "E001-S01-001", "reason": "r"}]})
        self.assertIn("retirement is epic-level", why(errs))

    def test_a_retirement_without_a_reason_is_refused(self):
        rows = [r for r in TOTAL if not r["key"].startswith("E003")]
        errs = rv.validate(BASE, {"target": rows, "retire": [{"key": "E003", "reason": "  "}]})
        self.assertIn("no reason", why(errs))


class TestDestinations(unittest.TestCase):
    def test_a_missing_destination_epic_is_refused(self):
        rows = [dict(r) for r in TOTAL]
        rows[0]["epic"] = "E099"
        self.assertIn("does not exist in planned/", why(rv.validate(BASE, {"target": rows})))

    def test_a_sprint_created_by_the_same_target_is_accepted(self):
        # The derivation creates it before moving into it; the validator must allow that.
        #
        # Moves the DEPENDENT (E001-S01-002) forward, not the thing it depends on. This test
        # used to move rows[0] — E001-S01-001 — into the new later sprint while 002 stayed in
        # S01, which is a backward dependency across sequential sprints. It passed only
        # because the ordering rule compared `order` within a sprint and never sprint
        # position, so it encoded the hole it was written beside. Its subject is destination
        # creation; an incidental ordering violation is TestCrossSprintOrdering's to assert.
        rows = [dict(r) for r in TOTAL]
        rows[1]["sprint"] = "S04"
        self.assertEqual(rv.validate(BASE, {"target": rows}), [])

    def test_placing_into_an_epic_being_retired_is_refused(self):
        rows = [dict(r) for r in TOTAL]
        rows[0]["epic"] = "E003"
        errs = rv.validate(BASE, {"target": rows,
                                  "retire": [{"key": "E003", "reason": "r"}]})
        self.assertIn("being retired", why(errs))


class TestResultingGraph(unittest.TestCase):
    def test_retiring_an_epic_a_live_story_depends_on_is_refused(self):
        p = plan([
            epic("E001", [sprint("S01", [story("E001-S01-001", ["E003-S01-001"])])]),
            epic("E003", [sprint("S01", [story("E003-S01-001")])]),
        ])
        rows = [{"key": "E001-S01-001", "epic": "E001", "sprint": "S01", "order": 1}]
        errs = rv.validate(p, {"target": rows,
                               "retire": [{"key": "E003", "reason": "r"}]})
        self.assertIn("inside a retired epic", why(errs))

    def test_a_cycle_in_the_resulting_plan_is_refused(self):
        p = plan([epic("E001", [sprint("S01", [
            story("E001-S01-001", ["E001-S01-002"]),
            story("E001-S01-002", ["E001-S01-001"]),
        ])])])
        rows = [{"key": "E001-S01-001", "epic": "E001", "sprint": "S01", "order": 1},
                {"key": "E001-S01-002", "epic": "E001", "sprint": "S01", "order": 2}]
        self.assertIn("cycle", why(rv.validate(p, {"target": rows})))

    def test_a_same_sprint_inversion_is_refused(self):
        rows = [dict(r) for r in TOTAL]
        rows[0]["order"] = 5       # 001 is depended on by 002
        rows[1]["order"] = 1
        self.assertIn("cannot come later", why(rv.validate(BASE, {"target": rows})))

    def test_a_dependency_on_active_work_is_not_an_ordering_error(self):
        p = plan([epic("E001", [sprint("S01", [story("E001-S01-001", ["E005"])])])],
                 active=["E005"])
        rows = [{"key": "E001-S01-001", "epic": "E001", "sprint": "S01", "order": 1}]
        self.assertEqual(rv.validate(p, {"target": rows}), [],
                         "ordering against in-flight work is not this target's to decide")


class TestCrossSprintOrdering(unittest.TestCase):
    """Sprints inside an epic run sequentially, so position is (sprint_index, order).

    The rule used to compare `order` alone and fire only when two stories shared a sprint,
    which left the commoner violation accepted outright. Moving a story forward past its
    dependent is the canonical balancing move, so the gap sat exactly where a balancing pass
    would land.
    """

    TWO = plan([epic("E001", [
        sprint("S01", [story("E001-S01-001", ["E001-S02-001"])]),
        sprint("S02", [story("E001-S02-001")]),
    ])])

    def rows(self, a_sprint, b_sprint):
        return [{"key": "E001-S01-001", "epic": "E001", "sprint": a_sprint, "order": 1},
                {"key": "E001-S02-001", "epic": "E001", "sprint": b_sprint, "order": 1}]

    def test_a_dependency_in_a_later_sprint_of_the_same_epic_is_refused(self):
        # Returned `OK target is valid`, exit 0, before this rule existed.
        errs = rv.validate(self.TWO, {"target": self.rows("S01", "S02")})
        self.assertTrue(errs)
        self.assertIn("LATER sprint", why(errs))

    def test_the_same_pair_placed_in_dependency_order_is_accepted(self):
        # The dependency moves to the earlier sprint: legal, and must stay legal.
        self.assertEqual(rv.validate(self.TWO, {"target": self.rows("S02", "S01")}), [])

    def test_both_in_one_sprint_falls_back_to_order_and_is_refused(self):
        rows = self.rows("S01", "S01")
        rows[0]["order"] = 1          # the dependent
        rows[1]["order"] = 2          # what it depends on — later: illegal
        self.assertIn("same sprint", why(rv.validate(self.TWO, {"target": rows})))

    def test_sprint_index_comes_from_sorted_key_order_not_arithmetic(self):
        # S01, S03, S07 are indices 0, 1, 2. Subtracting the numbers would read S03 and S07
        # as four apart and S01/S03 as adjacent — neither is a fact about execution order.
        p = plan([epic("E001", [
            sprint("S01", [story("E001-S01-001")]),
            sprint("S03", [story("E001-S03-001", ["E001-S07-001"])]),
            sprint("S07", [story("E001-S07-001")]),
        ])])
        rows = [{"key": "E001-S01-001", "epic": "E001", "sprint": "S01", "order": 1},
                {"key": "E001-S03-001", "epic": "E001", "sprint": "S03", "order": 1},
                {"key": "E001-S07-001", "epic": "E001", "sprint": "S07", "order": 1}]
        self.assertIn("LATER sprint", why(rv.validate(p, {"target": rows})),
                      "non-contiguous sprint keys must still order by position")

    def test_a_cross_epic_dependency_is_not_judged_by_this_rule(self):
        # The PHASE graph orders epics, and epics in one phase run concurrently. An unbacked
        # cross-epic edge is the analyzer's to report, not this rule's to refuse.
        p = plan([
            epic("E001", [sprint("S01", [story("E001-S01-001", ["E003-S01-001"])])]),
            epic("E003", [sprint("S01", [story("E003-S01-001")])]),
        ])
        rows = [{"key": "E001-S01-001", "epic": "E001", "sprint": "S01", "order": 1},
                {"key": "E003-S01-001", "epic": "E003", "sprint": "S01", "order": 1}]
        self.assertEqual(rv.validate(p, {"target": rows}), [])

    def test_a_dependency_on_active_work_is_still_skipped(self):
        p = plan([epic("E001", [sprint("S01", [story("E001-S01-001", ["E009"])])])],
                 active=["E009"])
        rows = [{"key": "E001-S01-001", "epic": "E001", "sprint": "S01", "order": 1}]
        self.assertEqual(rv.validate(p, {"target": rows}), [],
                         "ordering against in-flight work is not this target's to decide")

    def test_a_sprint_the_target_creates_is_indexed_too(self):
        # The destination may not exist yet; the index spans existing plus created sprints.
        p = plan([epic("E001", [
            sprint("S01", [story("E001-S01-001", ["E001-S01-002"]), story("E001-S01-002")]),
        ])])
        rows = [{"key": "E001-S01-001", "epic": "E001", "sprint": "S01", "order": 1},
                {"key": "E001-S01-002", "epic": "E001", "sprint": "S09", "order": 1}]
        self.assertIn("LATER sprint", why(rv.validate(p, {"target": rows})),
                      "a dependency moved into a newly created later sprint is still backward")


class TestMalformedInput(unittest.TestCase):
    def test_a_non_mapping_target_is_refused(self):
        self.assertTrue(rv.validate(BASE, ["not", "a", "mapping"]))

    def test_a_non_list_target_section_is_refused(self):
        self.assertIn("must be a list", why(rv.validate(BASE, {"target": "nope"})))

    def test_a_row_that_is_not_a_mapping_is_refused(self):
        self.assertIn("must be a mapping", why(rv.validate(BASE, {"target": ["x"]})))

    def test_a_row_missing_its_destination_is_refused(self):
        self.assertIn("missing required field", why(rv.validate(BASE,
                      {"target": [{"key": "E001-S01-001"}]})))

    def test_an_empty_target_against_a_nonempty_plan_is_refused_for_totality(self):
        self.assertTrue(rv.validate(BASE, {"target": []}))

    def test_an_empty_target_against_an_empty_plan_is_fine(self):
        self.assertEqual(rv.validate(plan([]), {"target": []}), [])


class TestCli(unittest.TestCase):
    def _run(self, plan_obj, target_text, fmt="json"):
        d = tempfile.mkdtemp()
        tp = os.path.join(d, "t.yaml")
        with open(tp, "w", encoding="utf-8") as fh:
            fh.write(target_text)
        stdin = sys.stdin
        sys.stdin = type("S", (), {"read": staticmethod(lambda: json.dumps(plan_obj))})()
        import io
        from contextlib import redirect_stderr, redirect_stdout
        out, err = io.StringIO(), io.StringIO()
        try:
            sys.stdin = io.StringIO(json.dumps(plan_obj))
            with redirect_stdout(out), redirect_stderr(err):
                code = rv.main(["--target", tp, "--format", fmt])
        finally:
            sys.stdin = stdin
        return code, out.getvalue(), err.getvalue()

    def test_a_valid_target_exits_0(self):
        rows = "\n".join(f"- {{key: {r['key']}, epic: {r['epic']}, sprint: {r['sprint']}, "
                         f"order: {r['order']}}}" for r in TOTAL)
        code, out, _ = self._run(BASE, "target:\n" + rows)
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["ok"])

    def test_an_invalid_target_exits_2(self):
        code, out, _ = self._run(BASE, "target:\n- {key: E001-S01-001, epic: E001, "
                                       "sprint: S01, order: 1}")
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(out)["ok"])

    def test_a_missing_target_file_exits_2(self):
        stdin = sys.stdin
        import io
        from contextlib import redirect_stderr
        err = io.StringIO()
        try:
            sys.stdin = io.StringIO(json.dumps(BASE))
            with redirect_stderr(err):
                code = rv.main(["--target", "/nope/absent.yaml"])
        finally:
            sys.stdin = stdin
        self.assertEqual(code, 2)
        self.assertIn("not found", err.getvalue())

    def test_non_dump_plan_stdin_is_refused_rather_than_guessed(self):
        stdin = sys.stdin
        import io
        from contextlib import redirect_stderr
        err = io.StringIO()
        d = tempfile.mkdtemp()
        tp = os.path.join(d, "t.yaml")
        with open(tp, "w", encoding="utf-8") as fh:
            fh.write("target: []\n")
        try:
            sys.stdin = io.StringIO('{"something": "else"}')
            with redirect_stderr(err):
                code = rv.main(["--target", tp])
        finally:
            sys.stdin = stdin
        self.assertEqual(code, 2)
        self.assertIn("refusing", err.getvalue().lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
