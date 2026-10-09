#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
"""reorg-derive.py -- the operation list is computed, never written by an agent.

The ordering tests are the substance here. Each one pins a sequence that, if it were wrong,
would fail only at apply time, in somebody's real tree, halfway through.
"""
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(os.path.dirname(HERE)),
                      "skills", "l3io-plan", "scripts", "reorg-derive.py")
spec = importlib.util.spec_from_file_location("reorg_derive", SCRIPT)
rd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rd)


def story(key):
    return {"key": key, "status": "backlog", "classification": "",
            "depends_on": [], "estimate": {}}


def sprint(key, keys):
    return {"key": key, "status": "backlog", "estimate": {},
            "stories": [story(k) for k in keys]}


def epic(key, sprints):
    return {"key": key, "status": "backlog", "depends_on": [], "estimate": {},
            "sprints": sprints}


def plan(epics):
    return {"planned": epics, "active": [], "archived": []}


BASE = plan([
    epic("E001", [sprint("S01", ["E001-S01-001", "E001-S01-002"])]),
    epic("E003", [sprint("S01", ["E003-S01-001"])]),
])


def row(key, e, sp, order=1):
    return {"key": key, "epic": e, "sprint": sp, "order": order}


def opnames(ops):
    return [o["op"] for o in ops]


class TestOrdering(unittest.TestCase):
    def test_a_missing_destination_sprint_is_created_before_anything_moves_into_it(self):
        # reparent-story REFUSES a missing destination, so a create that came later would
        # fail every move into it.
        ops = rd.derive(BASE, {"target": [
            row("E001-S01-001", "E003", "S09"),
            row("E001-S01-002", "E001", "S01"),
            row("E003-S01-001", "E003", "S01"),
        ]})
        self.assertEqual(ops[0]["op"], "create-sprint")
        self.assertEqual((ops[0]["epic"], ops[0]["sprint"]), ("E003", "S09"))
        self.assertEqual(opnames(ops)[1], "reparent-story")

    def test_an_existing_destination_is_not_created(self):
        ops = rd.derive(BASE, {"target": [
            row("E001-S01-001", "E003", "S01"),
            row("E001-S01-002", "E001", "S01"),
            row("E003-S01-001", "E003", "S01"),
        ]})
        self.assertNotIn("create-sprint", opnames(ops))

    def test_moves_into_one_sprint_follow_the_targets_order(self):
        # Key order IS processing order, so this is the only control the format has over it.
        ops = rd.derive(BASE, {"target": [
            row("E001-S01-001", "E003", "S01", order=2),
            row("E001-S01-002", "E003", "S01", order=1),
            row("E003-S01-001", "E003", "S01", order=3),
        ]})
        moved = [o["story"] for o in ops if o["op"] == "reparent-story"]
        self.assertEqual(moved, ["E001-S01-002", "E001-S01-001"])

    def test_retirements_come_last(self):
        p = plan([epic("E001", [sprint("S01", ["E001-S01-001"])]),
                  epic("E041", [sprint("S01", ["E041-S01-001"])])])
        ops = rd.derive(p, {"target": [row("E001-S01-001", "E001", "S01"),
                                       row("E041-S01-001", "E001", "S01")],
                            "retire": [{"key": "E041", "reason": "r"}]})
        self.assertEqual(opnames(ops)[-1], "retire-epic")

    def test_a_story_leaving_a_retiring_epic_moves_before_the_retire(self):
        # Otherwise it is archived along with the epic it was supposed to escape.
        p = plan([epic("E001", [sprint("S01", ["E001-S01-001"])]),
                  epic("E041", [sprint("S01", ["E041-S01-001"])])])
        ops = rd.derive(p, {"target": [row("E001-S01-001", "E001", "S01"),
                                       row("E041-S01-001", "E001", "S01")],
                            "retire": [{"key": "E041", "reason": "r"}]})
        names = opnames(ops)
        self.assertLess(names.index("reparent-story"), names.index("retire-epic"))


class TestNoOps(unittest.TestCase):
    def test_a_story_already_where_the_target_puts_it_emits_nothing(self):
        ops = rd.derive(BASE, {"target": [
            row("E001-S01-001", "E001", "S01"),
            row("E001-S01-002", "E001", "S01"),
            row("E003-S01-001", "E003", "S01"),
        ]})
        self.assertEqual(ops, [], "an unchanged total target is not work")

    def test_an_empty_target_derives_nothing(self):
        self.assertEqual(rd.derive(BASE, {"target": []}), [])

    def test_a_reorder_within_the_same_sprint_is_not_a_move(self):
        # The documented limit: `order` cannot reorder a story that stays put, because the
        # only way to do that is to re-key it. Pinning it so nobody assumes otherwise.
        ops = rd.derive(BASE, {"target": [
            row("E001-S01-001", "E001", "S01", order=9),
            row("E001-S01-002", "E001", "S01", order=1),
            row("E003-S01-001", "E003", "S01"),
        ]})
        self.assertEqual(ops, [])


class TestRediffing(unittest.TestCase):
    """The property the target-state model exists to provide."""

    def test_re_deriving_after_a_partial_apply_yields_exactly_the_remainder(self):
        target = {"target": [row("E001-S01-001", "E003", "S01"),
                             row("E001-S01-002", "E003", "S01"),
                             row("E003-S01-001", "E003", "S01")]}
        first = rd.derive(BASE, target)
        self.assertEqual(len(first), 2)

        # Simulate applying only the first move: E001-S01-001 is now in E003/S01, re-keyed.
        after = plan([
            epic("E001", [sprint("S01", ["E001-S01-002"])]),
            epic("E003", [sprint("S01", ["E003-S01-001", "E003-S01-002"])]),
        ])
        moved_target = {"target": [row("E001-S01-002", "E003", "S01"),
                                   row("E003-S01-001", "E003", "S01"),
                                   row("E003-S01-002", "E003", "S01")]}
        second = rd.derive(after, moved_target)
        self.assertEqual(len(second), 1, "a half-finished reorg must be detectable, not silent")
        self.assertEqual(second[0]["story"], "E001-S01-002")

    def test_deriving_twice_from_the_same_state_is_identical(self):
        t = {"target": [row("E001-S01-001", "E003", "S01"),
                        row("E001-S01-002", "E001", "S01"),
                        row("E003-S01-001", "E003", "S01")]}
        self.assertEqual(json.dumps(rd.derive(BASE, t), sort_keys=True),
                         json.dumps(rd.derive(BASE, t), sort_keys=True))


class TestOperationShape(unittest.TestCase):
    def test_a_move_records_where_it_came_from(self):
        ops = rd.derive(BASE, {"target": [row("E001-S01-001", "E003", "S01"),
                                          row("E001-S01-002", "E001", "S01"),
                                          row("E003-S01-001", "E003", "S01")]})
        self.assertEqual(ops[0]["from"], ["E001", "S01"])

    def test_no_operation_ever_names_a_destination_key(self):
        # The allocator assigns every new key; an op that named one would be the agent
        # choosing a key by another route.
        ops = rd.derive(BASE, {"target": [row("E001-S01-001", "E003", "S09"),
                                          row("E001-S01-002", "E001", "S01"),
                                          row("E003-S01-001", "E003", "S01")]})
        for o in ops:
            self.assertNotIn("new_key", o)
            self.assertNotIn("to_story", o)

    def test_a_malformed_row_is_skipped_rather_than_crashing(self):
        ops = rd.derive(BASE, {"target": ["nonsense", {"no_key": 1},
                                          row("E001-S01-001", "E003", "S01")]})
        self.assertEqual([o["op"] for o in ops], ["reparent-story"])


class TestCli(unittest.TestCase):
    def _run(self, plan_obj, target_text):
        d = tempfile.mkdtemp()
        tp = os.path.join(d, "t.yaml")
        with open(tp, "w", encoding="utf-8") as fh:
            fh.write(target_text)
        stdin = sys.stdin
        out, err = io.StringIO(), io.StringIO()
        try:
            sys.stdin = io.StringIO(json.dumps(plan_obj))
            with redirect_stdout(out), redirect_stderr(err):
                code = rd.main(["--target", tp])
        finally:
            sys.stdin = stdin
        return code, out.getvalue(), err.getvalue()

    def test_emits_operations_as_json(self):
        code, out, _ = self._run(BASE, "target:\n- {key: E001-S01-001, epic: E003, "
                                       "sprint: S01, order: 1}\n")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["count"], 1)

    def test_non_dump_plan_stdin_is_refused(self):
        code, _o, err = self._run({"nope": 1}, "target: []\n")
        self.assertEqual(code, 2)
        self.assertIn("refusing", err.lower())

    def test_a_missing_target_file_exits_2(self):
        stdin = sys.stdin
        err = io.StringIO()
        try:
            sys.stdin = io.StringIO(json.dumps(BASE))
            with redirect_stderr(err):
                code = rd.main(["--target", "/nope/absent.yaml"])
        finally:
            sys.stdin = stdin
        self.assertEqual(code, 2)
        self.assertIn("not found", err.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
