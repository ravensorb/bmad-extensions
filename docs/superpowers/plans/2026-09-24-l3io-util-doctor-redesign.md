# l3io-util-doctor Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the doctor's two hand-rolled, untested node-writing procedures with five tested readers, one shared `import-node` verb, and an eight-step engine whose gate makes an empty parse unable to reach the destructive disposal step.

**Architecture:** Detection and judgement stay in prose; parsing and writing become code. Each reader is a pure function from a source tree to a list of normalised records. One new `pm-status.py` verb writes a record as a node, under the existing lock/event/exit-code contract. A guard with a tree-derived scope keeps state-path assembly inside the resolver section.

**Tech Stack:** Python 3.11+ with PEP-723 inline metadata, run via `uv run` (never bare `python3`); `ruamel.yaml>=0.18` for round-trip YAML; `unittest` for Python suites; Node with `node --test` for the `scripts/*.mjs` gates.

**Spec:** `docs/superpowers/specs/2026-09-23-l3io-util-doctor-redesign-design.md`

## Global Constraints

- **Never hand-roll what a maintained library does.** YAML is parsed with `ruamel.yaml`, never a hand-written reader. Frontmatter is parsed as YAML, not by regex.
- **Never write a custom test runner or assertion framework.** Python suites are `unittest`, run by `uv run <file>`. Node gates are `node --test`.
- **`uv run` only.** Every PEP-723 script is invoked as `uv run <script>`. A bare `python3 <script>.py` fails `check:docs` check 17. The one tolerance is a markdown line that names `uv` + `unavailable` or `fallback` on the same line as the invocation.
- **`pm-status.py` is one file** (ADR-0001). Do not split it, and do not add a second shipped runtime script beside it.
- **Never hand-edit a payload copy** under `skills/<skill>/scripts/`. Edit `skills/_shared/` and run `npm run sync:scripts`.
- **Never hand-edit `payload-manifest.json`.** Regenerate with `npm run check:manifest -- --write` after any payload change.
- **Never hand-edit the version marker or `PM_STATUS_VERSION`**, and never move the version backwards.
- **Conventional Commits with DCO sign-off:** `git commit -s`. Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `revert`, `WIP`. Scopes used here: `l3io-util`, `l3io-pm`, `infra`.
- **Gates that must pass before a commit lands:** `npm run check:docs`, `check:scripts`, `check:module`, `check:version`, `check:manifest`, `test:scripts`, plus `uv run skills/_shared/tests/test-pm-status.py`. Task 12 is the one deliberate exception and says so.
- **State statuses are fixed sets.** Story: `backlog`, `ready-for-dev`, `in-progress`, `review`, `done`. Sprint and epic: `backlog`, `in-progress`, `done`.
- **Placement rule:** an epic directory lives in the folder named for its status — `planned/` = `backlog`, `active/` = `in-progress`, `archived/` = `done`.
- **Derive scope from the source of truth, never from a hand-kept list.**

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `skills/l3io-util-doctor/scripts/detect-layout.py` | *(modify)* adds flat-file schema classification | 1 |
| `skills/l3io-util-doctor/scripts/state-record.py` | the normalised record: construction, validation, dedupe | 2 |
| `skills/_shared/pm-status.py` | *(modify)* `ensure_node_path()` in the resolver section; `import-node` verb | 3, 4 |
| `skills/l3io-util-doctor/scripts/read-l3io-flat.py` | reader: l3io legacy flat `epics:` list | 5 |
| `skills/l3io-util-doctor/scripts/read-bmad-flat.py` | reader: base-BMad `development_status:` mapping | 6 |
| `skills/l3io-util-doctor/scripts/read-per-epic.py` | reader: legacy `_bmad/state/` per-epic files | 7 |
| `skills/l3io-util-doctor/scripts/read-split.py` | reader: split three-file layout | 8 |
| `skills/l3io-util-doctor/scripts/read-artifacts.py` | reader: story `.md` frontmatter + sprint inference | 9 |
| `skills/l3io-util-doctor/scripts/migrate-engine.py` | the eight-step run: detect → … → dispose | 10, 11 |
| `scripts/check-docs.mjs` | *(modify)* check 26, the two-half resolver guard | 12 |
| `skills/l3io-util-doctor/assets/migrate-state.md` | *(rewrite)* prose around the engine | 13 |
| `skills/l3io-util-doctor/steps/bootstrap-state.md` | *(rewrite)* prose around the engine | 14 |
| `skills/l3io-util-doctor/scripts/tests/*.py` | one suite per reader, plus the engine suite | 2, 5-11 |
| `skills/l3io-util-doctor/scripts/tests/fixtures/` | one fixture project per source layout | 2, 5-9 |

**Why readers are separate files:** each is a pure function with one input shape. A reader can be understood, tested and rejected on its own. They are single-consumer code and live in the doctor's own `scripts/` per ADR-0001 — they are *not* added to `skills/_shared/`.

---

## Task 1: Schema discrimination in detect-layout.py

**Files:**
- Modify: `skills/l3io-util-doctor/scripts/detect-layout.py`
- Test: `skills/l3io-util-doctor/scripts/tests/test-detect-layout.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `classify_flat(path: Path) -> str` returning one of `"bmad"`, `"l3io"`, `"empty"`, `"unreadable"`. New CLI flag `--classify`. New exit code **3** = the flat file carries BMad's schema.

**Why exit 3 and not 2:** `argparse` itself exits **2** on a usage error. Reusing 2 would make "bad flags" and "BMad schema found" indistinguishable to a caller. The existing contract (0 = no collision, 1 = collision) is unchanged.

- [ ] **Step 1: Write the failing test**

Add to `skills/l3io-util-doctor/scripts/tests/test-detect-layout.py`:

```python
class TestClassifyFlat(unittest.TestCase):
    def _write(self, text):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        p = d / "sprint-status.yaml"
        p.write_text(text, encoding="utf-8")
        return p

    def test_bmad_mapping_is_bmad(self):
        p = self._write(
            "development_status:\n"
            "  epic-1: backlog\n"
            "  1-1-user-authentication: done\n"
        )
        self.assertEqual(mod.classify_flat(p), "bmad")

    def test_l3io_list_is_l3io(self):
        p = self._write("epics:\n  - key: 'E001'\n    status: backlog\n")
        self.assertEqual(mod.classify_flat(p), "l3io")

    def test_empty_file_is_empty(self):
        self.assertEqual(mod.classify_flat(self._write("")), "empty")

    def test_unparseable_is_unreadable(self):
        self.assertEqual(mod.classify_flat(self._write("a: [1,\n")), "unreadable")

    def test_neither_key_is_unreadable(self):
        self.assertEqual(mod.classify_flat(self._write("other: 1\n")), "unreadable")

    def test_classify_cli_exits_3_on_bmad(self):
        p = self._write("development_status:\n  epic-1: backlog\n")
        code = mod.main(["--artifacts", str(p.parent), "--classify"])
        self.assertEqual(code, 3)
```

Add `import shutil`, `import tempfile` and `from pathlib import Path` to the file's imports if they are not already present.

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run skills/l3io-util-doctor/scripts/tests/test-detect-layout.py`
Expected: FAIL with `AttributeError: module has no attribute 'classify_flat'`

- [ ] **Step 3: Add the ruamel dependency to the PEP-723 header**

`detect-layout.py` currently declares no dependencies. Change its header to:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
```

- [ ] **Step 4: Implement `classify_flat`**

```python
def classify_flat(path: Path) -> str:
    """Classify a flat sprint-status.yaml by its top-level schema.

    BMad's own file (bmad-sprint-planning/sprint-status-template.yaml) is a
    `development_status:` MAPPING of node-id -> status. This package's legacy flat
    file is an `epics:` LIST. They share this filename and default directory, so the
    discriminator must be the schema, never the path.

    Returns 'bmad', 'l3io', 'empty', or 'unreadable'. Never raises.
    """
    from ruamel.yaml import YAML
    from ruamel.yaml.error import YAMLError

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "unreadable"
    if not text.strip():
        return "empty"
    try:
        data = YAML(typ="safe").load(text)
    except YAMLError:
        return "unreadable"
    if not isinstance(data, dict):
        return "unreadable"
    if isinstance(data.get("development_status"), dict):
        return "bmad"
    if isinstance(data.get("epics"), list):
        return "l3io"
    return "unreadable"
```

- [ ] **Step 5: Wire the `--classify` flag into `main()`**

Add the argument beside the existing `--artifacts`:

```python
    parser.add_argument(
        "--classify", action="store_true",
        help="classify the flat sprint-status.yaml by schema instead of checking for a collision",
    )
```

And branch before the existing collision check:

```python
    if args.classify:
        flat = Path(args.artifacts) / "sprint-status.yaml"
        if not flat.is_file():
            sys.stdout.write("flat-schema: absent\n")
            return 0
        schema = classify_flat(flat)
        sys.stdout.write(f"flat-schema: {schema}\n")
        return 3 if schema == "bmad" else 0
```

- [ ] **Step 6: Update the module docstring's exit-code table**

Add below the existing `Exit 0` / `Exit 1` lines:

```
Exit 3 -- --classify only: the flat sprint-status.yaml carries BMad's `development_status:`
          mapping, not this package's `epics:` list. Deleting or migrating it as if it were
          ours would destroy the file bmad-sprint-planning, bmad-build and bmad-retrospective
          all read. argparse owns exit 2, which is why this is 3.
```

- [ ] **Step 7: Run the tests**

Run: `uv run skills/l3io-util-doctor/scripts/tests/test-detect-layout.py`
Expected: PASS, all tests including the pre-existing collision cases.

- [ ] **Step 8: Regenerate the manifest and run the gates**

```bash
npm run check:manifest -- --write
npm run check:docs && npm run check:scripts && npm run check:module && npm run check:version && npm run check:manifest
```
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add skills/l3io-util-doctor/scripts/detect-layout.py \
        skills/l3io-util-doctor/scripts/tests/test-detect-layout.py \
        skills/l3io-util-doctor/payload-manifest.json
git commit -s -m "feat(l3io-util): detect-layout classifies a flat status file by schema

BMad's sprint-status.yaml is a development_status: mapping; ours is an epics:
list. They share a filename and a directory, so the discriminator has to be the
schema. --classify exits 3 on BMad's, because argparse owns exit 2."
```

---

## Task 2: The normalised record

**Files:**
- Create: `skills/l3io-util-doctor/scripts/state-record.py`
- Create: `skills/l3io-util-doctor/scripts/tests/test-state-record.py`
- Create: `skills/l3io-util-doctor/scripts/tests/fixtures/README.md`

**Interfaces:**
- Consumes: nothing.
- Produces — every reader imports these:
  - `make_record(kind: str, key: str, status: str, title: str, source: str, origin: str | None = None, origin_note: str | None = None) -> dict`
  - `validate(rec: dict) -> list[str]` — returns problem strings, empty when valid
  - `dedupe(records: list[dict]) -> list[dict]` — merges duplicate keys, one rule
  - `VALID_STATUS: dict[str, set[str]]` keyed by kind

- [ ] **Step 1: Write the failing test**

Create `skills/l3io-util-doctor/scripts/tests/test-state-record.py`:

```python
#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# ///
"""Tests for state-record.py — run with: uv run test-state-record.py"""
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "state-record.py")
spec = importlib.util.spec_from_file_location("state_record", SCRIPT)
sr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sr)


class TestMakeRecord(unittest.TestCase):
    def test_minimal_record_is_valid(self):
        r = sr.make_record("epic", "E001", "backlog", "First epic", "sprint-status.yaml:3")
        self.assertEqual(sr.validate(r), [])
        self.assertEqual(r["kind"], "epic")
        self.assertEqual(r["key"], "E001")

    def test_origin_absent_by_default(self):
        r = sr.make_record("epic", "E001", "backlog", "t", "s")
        self.assertNotIn("origin", r)

    def test_origin_recorded_when_given(self):
        r = sr.make_record("sprint", "E001-S01", "done", "t", "s",
                           origin="inferred", origin_note="from status transitions")
        self.assertEqual(r["origin"], "inferred")
        self.assertEqual(r["origin_note"], "from status transitions")


class TestValidate(unittest.TestCase):
    def test_bad_kind_reported(self):
        r = sr.make_record("saga", "X", "backlog", "t", "s")
        self.assertIn("unknown kind 'saga'", sr.validate(r))

    def test_bad_status_for_kind_reported(self):
        r = sr.make_record("epic", "E001", "ready-for-dev", "t", "s")
        problems = sr.validate(r)
        self.assertTrue(any("invalid epic status" in p for p in problems), problems)

    def test_story_status_ready_for_dev_is_valid(self):
        r = sr.make_record("story", "E001-S01-001", "ready-for-dev", "t", "s")
        self.assertEqual(sr.validate(r), [])

    def test_empty_key_reported(self):
        r = sr.make_record("epic", "", "backlog", "t", "s")
        self.assertIn("key is empty", sr.validate(r))

    def test_empty_source_reported(self):
        r = sr.make_record("epic", "E001", "backlog", "t", "")
        self.assertIn("source is empty", sr.validate(r))


class TestDedupe(unittest.TestCase):
    def test_shell_and_full_epic_merge_to_one(self):
        shell = sr.make_record("epic", "E001", "backlog", "", "a.yaml:1")
        full = sr.make_record("epic", "E001", "in-progress", "Real title", "b.yaml:9")
        out = sr.dedupe([shell, full])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["title"], "Real title")
        self.assertEqual(out[0]["status"], "in-progress")

    def test_richer_record_wins_regardless_of_order(self):
        shell = sr.make_record("epic", "E001", "backlog", "", "a.yaml:1")
        full = sr.make_record("epic", "E001", "in-progress", "Real title", "b.yaml:9")
        self.assertEqual(sr.dedupe([full, shell])[0]["title"], "Real title")

    def test_distinct_keys_are_untouched(self):
        a = sr.make_record("epic", "E001", "backlog", "A", "x:1")
        b = sr.make_record("epic", "E002", "backlog", "B", "x:2")
        self.assertEqual(len(sr.dedupe([a, b])), 2)

    def test_same_key_different_kind_is_not_merged(self):
        a = sr.make_record("epic", "E001", "backlog", "A", "x:1")
        b = sr.make_record("sprint", "E001", "backlog", "B", "x:2")
        self.assertEqual(len(sr.dedupe([a, b])), 2)

    def test_first_seen_order_is_preserved(self):
        a = sr.make_record("epic", "E002", "backlog", "B", "x:2")
        b = sr.make_record("epic", "E001", "backlog", "A", "x:1")
        self.assertEqual([r["key"] for r in sr.dedupe([a, b])], ["E002", "E001"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run skills/l3io-util-doctor/scripts/tests/test-state-record.py`
Expected: FAIL — `state-record.py` does not exist.

- [ ] **Step 3: Implement `state-record.py`**

```python
#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# ///
"""
state-record.py -- the normalised record every doctor reader emits.

Why this exists
----------------
Six migration procedures each parsed their own source shape AND wrote state directly,
in prose, so none of them was reachable by a test. Splitting them into readers that
emit ONE record shape makes the parsing testable and leaves exactly one writer
(`pm-status.py import-node`). This module is that shape, plus the two rules that
must hold once rather than per reader: validation, and the dedupe rule.

The dedupe rule has its own history. An epic shell and its full epic used to merge
into two records with one key, landing in two status folders -- on BOTH source paths,
and only one of them was ever filed. The rule now lives here, applied once where the
lists are joined, so a new reader cannot reintroduce it.

This is single-consumer code for l3io-util-doctor (ADR-0001) -- it is NOT shared, and
must not be added to skills/_shared/.
"""
from __future__ import annotations

KINDS = ("epic", "sprint", "story")

VALID_STATUS = {
    "epic": {"backlog", "in-progress", "done"},
    "sprint": {"backlog", "in-progress", "done"},
    "story": {"backlog", "ready-for-dev", "in-progress", "review", "done"},
}

# Ordered worst -> best. dedupe() keeps the record carrying the most information, and a
# status further along this list is later in the lifecycle -- the one a shell record
# could not have invented.
_STATUS_RANK = {
    "backlog": 0, "ready-for-dev": 1, "in-progress": 2, "review": 3, "done": 4,
}


def make_record(kind, key, status, title, source, origin=None, origin_note=None) -> dict:
    """Build a record. `origin` is omitted entirely unless given -- absent means
    'read directly from the source', which is why no schema version bump is needed."""
    rec = {
        "kind": kind,
        "key": key,
        "status": status,
        "title": title,
        "source": source,
    }
    if origin is not None:
        rec["origin"] = origin
        rec["origin_note"] = origin_note or ""
    return rec


def validate(rec: dict) -> list:
    """Return a list of problem strings; empty means valid."""
    problems = []
    kind = rec.get("kind")
    if kind not in KINDS:
        problems.append(f"unknown kind {kind!r}")
    if not str(rec.get("key", "")).strip():
        problems.append("key is empty")
    if kind in VALID_STATUS:
        status = rec.get("status")
        if status not in VALID_STATUS[kind]:
            problems.append(
                f"invalid {kind} status {status!r} -- expected one of "
                f"{sorted(VALID_STATUS[kind])}"
            )
    if not str(rec.get("source", "")).strip():
        problems.append("source is empty")
    return problems


def _richness(rec: dict) -> tuple:
    """How much information a record carries. Higher wins a merge."""
    return (
        1 if str(rec.get("title", "")).strip() else 0,
        _STATUS_RANK.get(rec.get("status"), -1),
    )


def dedupe(records: list) -> list:
    """Merge records sharing (kind, key), keeping the richest. Order-independent.

    One rule, applied once, where the lists are joined. An epic shell (no title,
    status backlog) and its full epic are ONE node, not two -- and must not land in
    two status folders.
    """
    best = {}
    order = []
    for rec in records:
        ident = (rec.get("kind"), rec.get("key"))
        if ident not in best:
            best[ident] = rec
            order.append(ident)
        elif _richness(rec) > _richness(best[ident]):
            best[ident] = rec
    return [best[i] for i in order]
```

- [ ] **Step 4: Run the tests**

Run: `uv run skills/l3io-util-doctor/scripts/tests/test-state-record.py`
Expected: PASS (13 tests).

- [ ] **Step 5: Create the fixture directory contract**

Create `skills/l3io-util-doctor/scripts/tests/fixtures/README.md`:

```markdown
# Reader fixtures

One directory per source layout. Each is a minimal but REAL project tree — the
readers are tested against trees shaped like the ones they will meet, not against
hand-built dicts that confirm the author's assumption about the shape.

| Directory | Layout | Reader |
|---|---|---|
| `l3io-flat/` | `sprint-status.yaml` with an `epics:` list | `read-l3io-flat.py` |
| `bmad-flat/` | `sprint-status.yaml` with a `development_status:` mapping | `read-bmad-flat.py` |
| `per-epic/` | `_bmad/state/epic-*.yaml`, one file per epic | `read-per-epic.py` |
| `split/` | `sprint-status{,-backlog,-archived}.yaml` | `read-split.py` |
| `artifacts/` | story `.md` files only, no status file | `read-artifacts.py` |

**Every fixture must be referenced by a test.** `test-engine.py` asserts the set of
directories here equals the set of readers — so deleting a fixture fails the suite
instead of silently shrinking the corpus.
```

- [ ] **Step 6: Regenerate the manifest and run the gates**

```bash
npm run check:manifest -- --write
npm run check:docs && npm run check:scripts && npm run check:module && npm run check:manifest
```

- [ ] **Step 7: Commit**

```bash
git add skills/l3io-util-doctor/scripts/state-record.py \
        skills/l3io-util-doctor/scripts/tests/test-state-record.py \
        skills/l3io-util-doctor/scripts/tests/fixtures/README.md \
        skills/l3io-util-doctor/payload-manifest.json
git commit -s -m "feat(l3io-util): the normalised record every doctor reader emits

Validation and the dedupe rule live here so they hold once rather than per
reader. The shell-plus-full-epic merge was missing on BOTH source paths and
only one was filed; it is now one rule at the join."
```

---

## Task 3: `ensure_node_path()` in the resolver section

**Files:**
- Modify: `skills/_shared/pm-status.py` — move `STATUS_FOR_DIR` (currently `:6097`) into the resolver section beside `STATUS_DIRS` (`:477`); add `ensure_node_path()` after `resolve_node_path()` (ends `:596`); add `require_exists` to `_epic_write_lock` (`:627`)
- Test: `skills/_shared/tests/test-pm-status.py`

**Interfaces:**
- Consumes: `find_epic_dir(state_root, epic_key)`, `epic_dirname(epic_key)`, `sprint_dirname(sprint_key)`, `parse_story_key(key)` — all already in the resolver section.
- Produces:
  - `DIR_FOR_STATUS: dict[str, str]` — derived as the inverse of `STATUS_FOR_DIR`, never hand-written
  - `ensure_node_path(state_root: str, args, kind: str, status: str) -> tuple[str, str]` returning `(path, label)`, creating parent directories
  - `_epic_write_lock(args, kind, require_exists: bool = True)` — the new parameter defaults to current behaviour, so every existing caller is unchanged

**Why this function is the only new one, and why it lives here:** `CLAUDE.md` states `pm-status.py` "is the only place that resolves a key to a file location." A `mkdir` in a subcommand body is exactly how that breaks — and it is what `assets/migrate-state.md:352` and `steps/bootstrap-state.md:226` do today.

- [ ] **Step 1: Write the failing test**

Append to `skills/_shared/tests/test-pm-status.py`:

```python
class TestEnsureNodePath(Base):
    class _Args:
        def __init__(self, **kw):
            self.epic = kw.get("epic")
            self.sprint = kw.get("sprint")
            self.story = kw.get("story")
            self.state_root = kw.get("state_root")

    def test_dir_for_status_is_the_inverse_of_status_for_dir(self):
        for folder, status in pm.STATUS_FOR_DIR.items():
            self.assertEqual(pm.DIR_FOR_STATUS[status], folder)
        self.assertEqual(len(pm.DIR_FOR_STATUS), len(pm.STATUS_FOR_DIR))

    def test_new_epic_lands_in_the_folder_named_for_its_status(self):
        a = self._Args(epic="E001", state_root=self.d)
        path, label = pm.ensure_node_path(self.d, a, "epic", "in-progress")
        self.assertEqual(path, os.path.join(self.d, "active", "epic-001", "epic.yaml"))
        self.assertTrue(os.path.isdir(os.path.dirname(path)))
        self.assertEqual(label, "epic E001")

    def test_backlog_epic_lands_in_planned(self):
        a = self._Args(epic="E002", state_root=self.d)
        path, _ = pm.ensure_node_path(self.d, a, "epic", "backlog")
        self.assertEqual(path, os.path.join(self.d, "planned", "epic-002", "epic.yaml"))

    def test_done_epic_lands_in_archived(self):
        a = self._Args(epic="E003", state_root=self.d)
        path, _ = pm.ensure_node_path(self.d, a, "epic", "done")
        self.assertEqual(path, os.path.join(self.d, "archived", "epic-003", "epic.yaml"))

    def test_existing_epic_dir_is_reused_not_relocated(self):
        a = self._Args(epic="E001", state_root=self.d)
        pm.ensure_node_path(self.d, a, "epic", "backlog")          # creates planned/
        path, _ = pm.ensure_node_path(self.d, a, "epic", "done")   # must NOT create archived/
        self.assertEqual(path, os.path.join(self.d, "planned", "epic-001", "epic.yaml"))
        self.assertFalse(os.path.isdir(os.path.join(self.d, "archived", "epic-001")))

    def test_sprint_dir_is_created_under_its_epic(self):
        a = self._Args(epic="E001", sprint="S02", state_root=self.d)
        pm.ensure_node_path(self.d, a, "epic", "backlog")
        path, label = pm.ensure_node_path(self.d, a, "sprint", "in-progress")
        self.assertEqual(
            path, os.path.join(self.d, "planned", "epic-001", "sprint-02", "sprint.yaml"))
        self.assertTrue(os.path.isdir(os.path.dirname(path)))
        self.assertEqual(label, "epic E001 sprint S02")

    def test_story_path_is_created_under_its_sprint(self):
        a = self._Args(epic="E001", story="E001-S02-003", state_root=self.d)
        pm.ensure_node_path(self.d, a, "epic", "backlog")
        path, _ = pm.ensure_node_path(self.d, a, "story", "ready-for-dev")
        self.assertEqual(
            path,
            os.path.join(self.d, "planned", "epic-001", "sprint-02", "E001-S02-003.yaml"))

    def test_sprint_without_an_epic_dir_exits_3(self):
        a = self._Args(epic="E404", sprint="S01", state_root=self.d)
        with self.assertRaises(SystemExit) as cm:
            pm.ensure_node_path(self.d, a, "sprint", "backlog")
        self.assertEqual(cm.exception.code, 3)

    def test_unknown_status_exits_2(self):
        a = self._Args(epic="E001", state_root=self.d)
        with self.assertRaises(SystemExit) as cm:
            pm.ensure_node_path(self.d, a, "epic", "nonsense")
        self.assertEqual(cm.exception.code, 2)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run skills/_shared/tests/test-pm-status.py -k EnsureNodePath`
Expected: FAIL with `AttributeError: module 'pm_status' has no attribute 'DIR_FOR_STATUS'`

- [ ] **Step 3: Move `STATUS_FOR_DIR` into the resolver section and derive its inverse**

Delete this line at `:6097`:

```python
STATUS_FOR_DIR = {"planned": "backlog", "active": "in-progress", "archived": "done"}
```

Insert it immediately below `STATUS_DIRS` at `:477`, with the derived inverse:

```python
STATUS_DIRS = ("active", "planned", "archived")  # active first: hottest path

# Layout knowledge belongs in the resolver section with everything else that knows
# where a node lives. DIR_FOR_STATUS is DERIVED, never written out a second time --
# two hand-kept halves of one mapping is how they drift apart.
STATUS_FOR_DIR = {"planned": "backlog", "active": "in-progress", "archived": "done"}
DIR_FOR_STATUS = {status: folder for folder, status in STATUS_FOR_DIR.items()}
```

`move_epic()` at the old site keeps working unchanged — the name is still module-level.

- [ ] **Step 4: Implement `ensure_node_path()`**

Insert directly after `resolve_node_path()` ends (`:596`):

```python
def ensure_node_path(state_root: str, args, kind: str, status: str):
    """Resolve a node kind + keys to (path, label), CREATING the directory when absent.

    The counterpart to resolve_node_path() for the one case that function cannot serve:
    a node that does not exist yet. It is the ONLY function that creates a state
    directory, and it lives here -- in the section that is the only place a key becomes
    a location -- on purpose. A mkdir in a subcommand body is exactly how that invariant
    breaks; check 26 in check-docs.mjs fails the build if one appears.

    A NEW epic is placed by its status, per the placement rule. An epic that already has
    a directory is left where it is: relocating on a status change is move-epic's job,
    which uses `git mv` so history survives. Sprints and stories require their epic's
    directory to exist and exit 3 when it does not.
    """
    if kind == "epic" and status not in DIR_FOR_STATUS:
        _die_usage(
            f"cannot place a new epic with status {status!r} -- "
            f"expected one of {sorted(DIR_FOR_STATUS)}"
        )
    if kind == "epic":
        if not args.epic:
            _die_usage("--epic is required for an epic node")
        d = find_epic_dir(state_root, args.epic)
        if d is None:
            d = os.path.join(state_root, DIR_FOR_STATUS[status], epic_dirname(args.epic))
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "epic.yaml"), f"epic {args.epic}"

    if kind == "sprint":
        if not (args.epic and args.sprint):
            _die_usage("--epic and --sprint are required for a sprint node")
        d = find_epic_dir(state_root, args.epic)
        if d is None:
            _die_notfound(f"epic {args.epic} (create it before its sprints)")
        sd = os.path.join(d, sprint_dirname(args.sprint))
        os.makedirs(sd, exist_ok=True)
        return os.path.join(sd, "sprint.yaml"), f"epic {args.epic} sprint {args.sprint}"

    if kind == "story":
        if not args.story:
            _die_usage("--story is required for a story node")
        epic_key, sprint_key, _ = parse_story_key(args.story)
        d = find_epic_dir(state_root, epic_key)
        if d is None:
            _die_notfound(f"epic {epic_key} (create it before its stories)")
        sd = os.path.join(d, sprint_dirname(sprint_key))
        os.makedirs(sd, exist_ok=True)
        return os.path.join(sd, f"{args.story}.yaml"), f"story {args.story}"

    _die_usage(f"unknown node kind: {kind}")
```

- [ ] **Step 5: Add `require_exists` to `_epic_write_lock`**

Replace the definition at `:627`:

```python
def _epic_write_lock(args, kind, require_exists: bool = True):
    """epic_node_lock around a node verb's read-modify-write when the node is an epic; no
    lock for a sprint or story, whose files are not epic.yaml. Resolves the epic first, so
    an absent one exits 3 exactly as before with no lock file created; the verb resolves
    again inside the hold, since a move-epic may land while it waits.

    require_exists=False is for import-node, whose whole purpose is the node that does not
    exist yet. It still takes the lock -- a concurrent import of the same epic must
    serialise -- it just does not demand the node be there first. Every other caller keeps
    the default, so their behaviour is unchanged.
    """
    if kind != "epic":
        return contextlib.nullcontext()
    if require_exists:
        resolve_node_path(args.state_root, args, "epic")
    return epic_node_lock(args.state_root, args.epic)
```

- [ ] **Step 6: Run the new tests, then the whole suite**

```bash
uv run skills/_shared/tests/test-pm-status.py -k EnsureNodePath
uv run skills/_shared/tests/test-pm-status.py
```
Expected: the 9 new tests pass; the full suite passes with no regressions.

- [ ] **Step 7: Sync payloads, regenerate manifests, run the gates**

```bash
npm run sync:scripts
npm run check:manifest -- --write
npm run check:docs && npm run check:scripts && npm run check:module && npm run check:version && npm run check:manifest
```

- [ ] **Step 8: Commit**

```bash
git add skills/_shared/pm-status.py skills/_shared/tests/test-pm-status.py \
        skills/l3io-pm-setup/scripts/pm-status.py \
        skills/l3io-util-doctor/scripts/pm-status.py \
        skills/l3io-pm-setup/payload-manifest.json \
        skills/l3io-util-doctor/payload-manifest.json
git commit -s -m "feat(l3io-pm): ensure_node_path -- the one function that creates a node dir

Lives in the resolver section with everything else that turns a key into a
location. STATUS_FOR_DIR moves up beside it and its inverse is derived, not
written twice. _epic_write_lock gains require_exists=False for the caller whose
node does not exist yet; every existing caller keeps the default."
```

---

## Task 4: The `import-node` verb

**Files:**
- Modify: `skills/_shared/pm-status.py` — add `cmd_import_node()` after `cmd_set_status()` (ends `:3821`); register the parser near `story-doc-init` (`:6489`)
- Test: `skills/_shared/tests/test-pm-status.py`

**Interfaces:**
- Consumes: `ensure_node_path(state_root, args, kind, status)` and `_epic_write_lock(args, kind, require_exists=False)` from Task 3; plus existing `_infer_kind(args)`, `save_node(y, node, path, use_flock)`, `append_event(state_root, payload)`, `_event_keys(kind, args)`, `_now_iso()`, `_yaml()`, `parse_story_key(key)`, `VALID_STORY_STATUS`, `VALID_SPRINT_STATUS`, `VALID_EPIC_STATUS`.
- Produces: CLI verb `import-node` with flags `--state-root`, `--epic`, `--sprint`, `--story`, `--status`, `--title`, `--classification`, `--origin`, `--origin-note`, `--no-events`, `--session-id`. Exit 0 on write or skip, 2 on invalid status, 3 on a missing parent epic.

**Why a copy of `cmd_set_status` and not a change to it:** `set-status` calls `_load_checked`, which exits 3 on a missing node. That refusal is correct and must stay — `set-status` must never create anything. `import-node` is the same handler with that one step swapped for `ensure_node_path`. `cmd_set_status` is not modified.

- [ ] **Step 1: Write the failing test**

Append to `skills/_shared/tests/test-pm-status.py`:

```python
class TestImportNode(Base):
    def _events(self):
        p = os.path.join(self.d, "events.jsonl")
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def test_creates_an_epic_and_its_directory(self):
        code, out = self.run_main([
            "import-node", "--state-root", self.d, "--epic", "E001",
            "--status", "backlog", "--title", "First epic"])
        self.assertEqual(code, 0, out)
        path = os.path.join(self.d, "planned", "epic-001", "epic.yaml")
        self.assertTrue(os.path.exists(path))
        _, node = pm.load_node(path)
        self.assertEqual(node["key"], "E001")
        self.assertEqual(node["status"], "backlog")
        self.assertEqual(node["title"], "First epic")

    def test_creates_a_sprint_with_its_epic_backreference(self):
        self.run_main(["import-node", "--state-root", self.d, "--epic", "E001",
                       "--status", "backlog", "--title", "E"])
        code, out = self.run_main([
            "import-node", "--state-root", self.d, "--epic", "E001", "--sprint", "S01",
            "--status", "in-progress", "--title", "Sprint one"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(
            os.path.join(self.d, "planned", "epic-001", "sprint-01", "sprint.yaml"))
        self.assertEqual(node["epic"], "E001")
        self.assertEqual(node["key"], "S01")

    def test_creates_a_story_with_both_backreferences(self):
        self.run_main(["import-node", "--state-root", self.d, "--epic", "E001",
                       "--status", "backlog", "--title", "E"])
        code, out = self.run_main([
            "import-node", "--state-root", self.d, "--story", "E001-S01-002",
            "--status", "done", "--title", "A story", "--classification", "feature"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(
            os.path.join(self.d, "planned", "epic-001", "sprint-01", "E001-S01-002.yaml"))
        self.assertEqual(node["epic"], "E001")
        self.assertEqual(node["sprint"], "S01")
        self.assertEqual(node["classification"], "feature")

    def test_the_new_node_passes_check_backrefs(self):
        self.run_main(["import-node", "--state-root", self.d, "--epic", "E001",
                       "--status", "backlog", "--title", "E"])
        self.run_main(["import-node", "--state-root", self.d, "--story", "E001-S01-002",
                       "--status", "done", "--title", "S"])
        code, out = self.run_main([
            "set-status", "--state-root", self.d, "--story", "E001-S01-002",
            "--status", "review"])
        self.assertEqual(code, 0, out)

    def test_origin_is_written_when_given_and_absent_otherwise(self):
        self.run_main(["import-node", "--state-root", self.d, "--epic", "E001",
                       "--status", "backlog", "--title", "E"])
        self.run_main(["import-node", "--state-root", self.d, "--epic", "E002",
                       "--status", "backlog", "--title", "E2",
                       "--origin", "inferred", "--origin-note", "from transitions"])
        _, plain = pm.load_node(os.path.join(self.d, "planned", "epic-001", "epic.yaml"))
        _, marked = pm.load_node(os.path.join(self.d, "planned", "epic-002", "epic.yaml"))
        self.assertNotIn("origin", plain)
        self.assertEqual(marked["origin"], "inferred")
        self.assertEqual(marked["origin_note"], "from transitions")

    def test_invalid_status_for_kind_exits_2(self):
        code, _ = self.run_main([
            "import-node", "--state-root", self.d, "--epic", "E001",
            "--status", "ready-for-dev", "--title", "E"])
        self.assertEqual(code, 2)

    def test_sprint_without_its_epic_exits_3(self):
        code, _ = self.run_main([
            "import-node", "--state-root", self.d, "--epic", "E404", "--sprint", "S01",
            "--status", "backlog", "--title", "orphan"])
        self.assertEqual(code, 3)

    def test_existing_node_is_skipped_not_overwritten(self):
        self.run_main(["import-node", "--state-root", self.d, "--epic", "E001",
                       "--status", "backlog", "--title", "Original"])
        code, out = self.run_main([
            "import-node", "--state-root", self.d, "--epic", "E001",
            "--status", "done", "--title", "Clobber"])
        self.assertEqual(code, 0, out)
        self.assertIn("SKIP", out)
        _, node = pm.load_node(os.path.join(self.d, "planned", "epic-001", "epic.yaml"))
        self.assertEqual(node["title"], "Original")
        self.assertEqual(node["status"], "backlog")

    def test_an_event_is_appended(self):
        self.run_main(["import-node", "--state-root", self.d, "--epic", "E001",
                       "--status", "backlog", "--title", "E"])
        evs = [e for e in self._events() if e.get("event") == "import"]
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["to"], "backlog")
        self.assertIsNone(evs[0]["from"])

    def test_no_events_flag_suppresses_the_append(self):
        self.run_main(["import-node", "--state-root", self.d, "--epic", "E001",
                       "--status", "backlog", "--title", "E", "--no-events"])
        self.assertEqual([e for e in self._events() if e.get("event") == "import"], [])

    def test_a_skip_appends_no_event(self):
        self.run_main(["import-node", "--state-root", self.d, "--epic", "E001",
                       "--status", "backlog", "--title", "E"])
        self.run_main(["import-node", "--state-root", self.d, "--epic", "E001",
                       "--status", "backlog", "--title", "E"])
        self.assertEqual(len([e for e in self._events() if e.get("event") == "import"]), 1)

    def test_set_status_still_refuses_a_missing_node(self):
        """import-node must not have loosened set-status."""
        code, _ = self.run_main([
            "set-status", "--state-root", self.d, "--epic", "E999", "--status", "done"])
        self.assertEqual(code, 3)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run skills/_shared/tests/test-pm-status.py -k ImportNode`
Expected: FAIL — `invalid choice: 'import-node'`

- [ ] **Step 3: Implement `cmd_import_node()`**

Insert after `cmd_set_status()` ends (`:3821`):

```python
def cmd_import_node(args) -> int:
    """Create a state node from a migration record. The counterpart to set-status for a
    node that does not exist yet.

    This is cmd_set_status with ONE step swapped -- ensure_node_path() where set-status
    calls _load_checked() -- because _load_checked exits 3 on a missing node, which is
    correct for set-status and fatal for this verb. set-status itself is untouched: it
    must never create anything.

    Idempotent by SKIP, not by overwrite. A migration retried after a partial run must
    not clobber a node a later step already edited, so an existing file is left exactly
    as it is and reported.
    """
    from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQ

    kind = _infer_kind(args)
    valid = {
        "story": VALID_STORY_STATUS,
        "sprint": VALID_SPRINT_STATUS,
        "epic": VALID_EPIC_STATUS,
    }[kind]
    if args.status not in valid:
        _die_usage(
            f"invalid {kind} status '{args.status}' -- expected one of {sorted(valid)}")

    with _epic_write_lock(args, kind, require_exists=False):
        path, label = ensure_node_path(args.state_root, args, kind, args.status)
        if os.path.exists(path):
            sys.stdout.write(f"SKIP import-node {label} -- already exists\n")
            return 0

        node = {}
        if kind == "epic":
            node["key"] = SQ(args.epic)
            node["title"] = args.title or ""
            node["goal"] = ""
        elif kind == "sprint":
            node["key"] = SQ(args.sprint)
            node["epic"] = SQ(args.epic)
            node["title"] = args.title or ""
        else:
            epic_key, sprint_key, _ = parse_story_key(args.story)
            node["key"] = SQ(args.story)
            node["epic"] = SQ(epic_key)
            node["sprint"] = SQ(sprint_key)
            node["title"] = args.title or ""
            node["classification"] = args.classification or "unknown"

        node["status"] = args.status
        node["updated_at"] = _now_iso()
        if args.origin:
            node["origin"] = args.origin
            node["origin_note"] = args.origin_note or ""

        save_node(_yaml(), node, path, getattr(args, "flock", False))

        if not getattr(args, "no_events", False):
            payload = {
                "ts": _now_iso(), "event": "import", "from": None, "to": args.status,
                "session": getattr(args, "session_id", None),
            }
            payload.update(_event_keys(kind, args))
            append_event(args.state_root, payload)

    sys.stdout.write(f"OK import-node {label} -> {args.status}\n")
    return 0
```

- [ ] **Step 4: Register the subcommand**

Beside where `story-doc-init` is registered (`:6489`):

```python
    imp = sub.add_parser("import-node",
                         help="create a state node from a migration record")
    imp.add_argument("--state-root", required=True)
    imp.add_argument("--epic")
    imp.add_argument("--sprint")
    imp.add_argument("--story")
    imp.add_argument("--status", required=True)
    imp.add_argument("--title", default="")
    imp.add_argument("--classification", default="unknown")
    imp.add_argument("--origin", choices=["inferred"],
                     help="mark the node as reconstructed rather than read")
    imp.add_argument("--origin-note", default="",
                     help="why the node was inferred; recorded beside --origin")
    imp.add_argument("--no-events", action="store_true")
    imp.add_argument("--session-id")
    imp.set_defaults(func=cmd_import_node)
```

- [ ] **Step 5: Run the new tests, then the whole suite**

```bash
uv run skills/_shared/tests/test-pm-status.py -k ImportNode
uv run skills/_shared/tests/test-pm-status.py
```
Expected: 12 new tests pass; full suite green, including `test_set_status_still_refuses_a_missing_node`.

- [ ] **Step 6: Sync, regenerate, run the gates**

```bash
npm run sync:scripts
npm run check:manifest -- --write
npm run check:docs && npm run check:scripts && npm run check:module && npm run check:version && npm run check:manifest
```

`check:docs` check 4 judges every documented `{pm_status}` invocation against the real argparse surface, so it will now accept `import-node` in step files.

- [ ] **Step 7: Commit**

```bash
git add skills/_shared/pm-status.py skills/_shared/tests/test-pm-status.py \
        skills/l3io-pm-setup/scripts/pm-status.py \
        skills/l3io-util-doctor/scripts/pm-status.py \
        skills/l3io-pm-setup/payload-manifest.json \
        skills/l3io-util-doctor/payload-manifest.json
git commit -s -m "feat(l3io-pm): import-node creates a state node from a migration record

cmd_set_status with one step swapped: ensure_node_path where set-status calls
_load_checked. set-status is untouched and still exits 3 on a missing node --
a test asserts it. Idempotent by skip, never by overwrite, so a retried
migration cannot clobber a node a later step edited."
```

---

## Task 5: Reader — l3io legacy flat

**Files:**
- Create: `skills/l3io-util-doctor/scripts/read-l3io-flat.py`
- Create: `skills/l3io-util-doctor/scripts/tests/test-read-l3io-flat.py`
- Create: `skills/l3io-util-doctor/scripts/tests/fixtures/l3io-flat/sprint-status.yaml`

**Interfaces:**
- Consumes: `state-record.py`'s `make_record`, `validate`, `dedupe` (Task 2).
- Produces: `read(path: Path) -> list[dict]`; CLI `read-l3io-flat.py --file PATH [--format json]` printing a JSON list to stdout. Exit 0 on a successful parse (including zero records), 1 when the file is absent.

**The contract every reader shares:** a reader NEVER writes, NEVER decides whether a migration should proceed, and NEVER refuses on an empty result. Emptiness is a fact it reports; the gate in Task 11 is what acts on it. Keeping that judgement out of the readers is what lets one gate cover every cause of an empty parse, including causes not yet known.

- [ ] **Step 1: Write the fixture**

Create `skills/l3io-util-doctor/scripts/tests/fixtures/l3io-flat/sprint-status.yaml`:

```yaml
# Legacy flat layout: one epics: list, sprints and stories nested inside it.
epics:
  - key: 'E001'
    title: Authentication
    status: in-progress
    sprints:
      - key: 'S01'
        title: Login flow
        status: done
        stories:
          - key: 'E001-S01-001'
            title: Password login
            status: done
            classification: feature
          - key: 'E001-S01-002'
            title: Session cookies
            status: review
      - key: 'S02'
        title: OAuth
        status: in-progress
        stories:
          - key: 'E001-S02-001'
            title: Google provider
            status: ready-for-dev
  - key: 'E002'
    title: Reporting
    status: backlog
    sprints: []
```

- [ ] **Step 2: Write the failing test**

Create `skills/l3io-util-doctor/scripts/tests/test-read-l3io-flat.py`:

```python
#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
"""Tests for read-l3io-flat.py — run with: uv run test-read-l3io-flat.py"""
import importlib.util
import os
import shutil
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "read-l3io-flat.py")
FIXTURE = Path(HERE) / "fixtures" / "l3io-flat" / "sprint-status.yaml"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(os.path.dirname(HERE), filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rd = _load("read_l3io_flat", "read-l3io-flat.py")
sr = _load("state_record", "state-record.py")


class TestReadL3ioFlat(unittest.TestCase):
    def setUp(self):
        self.recs = rd.read(FIXTURE)

    def _by_kind(self, kind):
        return [r for r in self.recs if r["kind"] == kind]

    def _tmp(self, text):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        p = d / "sprint-status.yaml"
        p.write_text(text, encoding="utf-8")
        return p

    def test_counts_match_the_fixture(self):
        self.assertEqual(len(self._by_kind("epic")), 2)
        self.assertEqual(len(self._by_kind("sprint")), 2)
        self.assertEqual(len(self._by_kind("story")), 3)

    def test_keys_are_exact(self):
        self.assertEqual({r["key"] for r in self._by_kind("epic")}, {"E001", "E002"})
        self.assertEqual({r["key"] for r in self._by_kind("sprint")},
                         {"E001-S01", "E001-S02"})
        self.assertEqual({r["key"] for r in self._by_kind("story")},
                         {"E001-S01-001", "E001-S01-002", "E001-S02-001"})

    def test_statuses_are_carried_through(self):
        got = {r["key"]: r["status"] for r in self.recs}
        self.assertEqual(got["E001"], "in-progress")
        self.assertEqual(got["E002"], "backlog")
        self.assertEqual(got["E001-S01"], "done")
        self.assertEqual(got["E001-S01-002"], "review")

    def test_every_record_validates(self):
        for r in self.recs:
            self.assertEqual(sr.validate(r), [], f"{r['key']}: {sr.validate(r)}")

    def test_no_record_is_marked_inferred(self):
        for r in self.recs:
            self.assertNotIn("origin", r)

    def test_source_names_the_file(self):
        for r in self.recs:
            self.assertIn("sprint-status.yaml", r["source"])

    def test_epic_with_no_sprints_still_yields_its_epic(self):
        self.assertIn("E002", {r["key"] for r in self._by_kind("epic")})

    def test_a_bmad_schema_file_yields_ZERO_records(self):
        """The live defect, as a test. This reader must not invent nodes from
        BMad's development_status: mapping -- and must not refuse either. It
        reports emptiness; the engine's gate is what blocks."""
        p = self._tmp("development_status:\n  epic-1: backlog\n")
        self.assertEqual(rd.read(p), [])

    def test_empty_file_yields_zero_records(self):
        self.assertEqual(rd.read(self._tmp("")), [])

    def test_unparseable_file_yields_zero_records(self):
        self.assertEqual(rd.read(self._tmp("a: [1,\n")), [])

    def test_an_epic_without_a_key_is_skipped(self):
        p = self._tmp("epics:\n  - title: nameless\n    status: backlog\n")
        self.assertEqual(rd.read(p), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run it to verify it fails**

Run: `uv run skills/l3io-util-doctor/scripts/tests/test-read-l3io-flat.py`
Expected: FAIL — `read-l3io-flat.py` does not exist.

- [ ] **Step 4: Implement the reader**

```python
#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
"""
read-l3io-flat.py -- read this package's LEGACY flat sprint-status.yaml into records.

The legacy layout is one `epics:` LIST with sprints nested inside each epic and stories
nested inside each sprint. Do not confuse it with BMad's own sprint-status.yaml, which is
a `development_status:` MAPPING at the same default path -- read-bmad-flat.py handles that
one, and detect-layout.py --classify decides which is present.

Reader contract: pure. No writes, no locking, no interaction, and NO refusal on an empty
result. A file this reader cannot make sense of yields zero records, which is a fact for
the engine's gate to act on -- not a judgement for the reader to make.

Usage:  read-l3io-flat.py --file PATH [--format json]
Exit 0 -- parsed (zero records is success)
Exit 1 -- the file does not exist
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "state_record", os.path.join(_HERE, "state-record.py"))
sr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sr)


def read(path: Path) -> list:
    """Parse a legacy flat status file into normalised records."""
    from ruamel.yaml import YAML
    from ruamel.yaml.error import YAMLError

    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    if not text.strip():
        return []
    try:
        data = YAML(typ="safe").load(text)
    except YAMLError:
        return []
    if not isinstance(data, dict) or not isinstance(data.get("epics"), list):
        return []

    name = Path(path).name
    out = []
    for epic in data["epics"]:
        if not isinstance(epic, dict):
            continue
        ekey = str(epic.get("key", "")).strip()
        if not ekey:
            continue
        out.append(sr.make_record(
            "epic", ekey, str(epic.get("status", "backlog")),
            str(epic.get("title", "")), f"{name}:epics[{ekey}]"))

        for sprint in epic.get("sprints") or []:
            if not isinstance(sprint, dict):
                continue
            skey = str(sprint.get("key", "")).strip()
            if not skey:
                continue
            out.append(sr.make_record(
                "sprint", f"{ekey}-{skey}", str(sprint.get("status", "backlog")),
                str(sprint.get("title", "")), f"{name}:epics[{ekey}].sprints[{skey}]"))

            for story in sprint.get("stories") or []:
                if not isinstance(story, dict):
                    continue
                stkey = str(story.get("key", "")).strip()
                if not stkey:
                    continue
                out.append(sr.make_record(
                    "story", stkey, str(story.get("status", "backlog")),
                    str(story.get("title", "")),
                    f"{name}:epics[{ekey}].sprints[{skey}].stories[{stkey}]"))

    return sr.dedupe(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="read a legacy flat sprint-status.yaml")
    parser.add_argument("--file", required=True, help="path to sprint-status.yaml")
    parser.add_argument("--format", choices=["json"], default="json")
    args = parser.parse_args(argv)

    p = Path(args.file)
    if not p.is_file():
        sys.stderr.write(f"read-l3io-flat.py: no such file: {p}\n")
        return 1
    json.dump(read(p), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tests**

Run: `uv run skills/l3io-util-doctor/scripts/tests/test-read-l3io-flat.py`
Expected: PASS (11 tests), including `test_a_bmad_schema_file_yields_ZERO_records`.

- [ ] **Step 6: Regenerate the manifest and run the gates**

```bash
npm run check:manifest -- --write
npm run check:docs && npm run check:scripts && npm run check:module && npm run check:manifest
```

- [ ] **Step 7: Commit**

```bash
git add skills/l3io-util-doctor/scripts/read-l3io-flat.py \
        skills/l3io-util-doctor/scripts/tests/test-read-l3io-flat.py \
        skills/l3io-util-doctor/scripts/tests/fixtures/l3io-flat/ \
        skills/l3io-util-doctor/payload-manifest.json
git commit -s -m "feat(l3io-util): reader for the legacy flat epics: list

Pure function, tested against a real fixture tree. Includes the live defect as
a test: a BMad-schema file yields zero records here, and the reader neither
invents nodes nor refuses -- the engine's gate is what blocks on emptiness."
```

---

## Task 6: Reader — base BMad

**Files:**
- Create: `skills/l3io-util-doctor/scripts/read-bmad-flat.py`
- Create: `skills/l3io-util-doctor/scripts/tests/test-read-bmad-flat.py`
- Create: `skills/l3io-util-doctor/scripts/tests/fixtures/bmad-flat/sprint-status.yaml`

**Interfaces:**
- Consumes: `state-record.py`'s `make_record`, `dedupe`.
- Produces: `read(path: Path) -> list[dict]`; `parse_id(node_id: str) -> tuple[str, str] | None` returning `(kind, key)`; CLI identical in shape to Task 5.

**The schema this reads**, from `.claude/skills/bmad-sprint-planning/sprint-status-template.yaml:53-66` — a flat mapping of node id to status, with two id shapes and **no sprint concept**:

```yaml
development_status:
  epic-1: backlog
  1-1-user-authentication: done
```

`epic-N` is an epic. `E-S-slug` (two leading integers then a slug) is story S of epic E. Sprints do not exist in this schema, so every story this reader emits lands in sprint `S01` and no sprint records are produced — the engine's plan creates the sprint node implicitly through the story's path. Reconstructing real sprint boundaries is Task 9's job, on a different source.

- [ ] **Step 1: Write the fixture**

Create `skills/l3io-util-doctor/scripts/tests/fixtures/bmad-flat/sprint-status.yaml`:

```yaml
# Base BMad's own schema: a flat mapping, no sprints, ids in two shapes.
development_status:
  epic-1: in-progress
  1-1-user-authentication: done
  1-2-session-cookies: in-progress
  epic-2: backlog
  2-1-report-export: backlog
```

- [ ] **Step 2: Write the failing test**

Create `skills/l3io-util-doctor/scripts/tests/test-read-bmad-flat.py`:

```python
#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
"""Tests for read-bmad-flat.py — run with: uv run test-read-bmad-flat.py"""
import importlib.util
import os
import shutil
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = Path(HERE) / "fixtures" / "bmad-flat" / "sprint-status.yaml"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(os.path.dirname(HERE), filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rd = _load("read_bmad_flat", "read-bmad-flat.py")


class TestParseId(unittest.TestCase):
    def test_epic_id(self):
        self.assertEqual(rd.parse_id("epic-1"), ("epic", "E001"))

    def test_epic_id_zero_pads(self):
        self.assertEqual(rd.parse_id("epic-12"), ("epic", "E012"))

    def test_story_id(self):
        self.assertEqual(rd.parse_id("1-1-user-authentication"),
                         ("story", "E001-S01-001"))

    def test_story_id_second_number_is_the_story_number(self):
        self.assertEqual(rd.parse_id("2-7-report-export"), ("story", "E002-S01-007"))

    def test_unrecognised_id_is_none(self):
        self.assertIsNone(rd.parse_id("sprint-3"))
        self.assertIsNone(rd.parse_id("just-a-slug"))
        self.assertIsNone(rd.parse_id(""))


class TestReadBmadFlat(unittest.TestCase):
    def setUp(self):
        self.recs = rd.read(FIXTURE)

    def _by_kind(self, k):
        return [r for r in self.recs if r["kind"] == k]

    def _tmp(self, text):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        p = d / "sprint-status.yaml"
        p.write_text(text, encoding="utf-8")
        return p

    def test_counts(self):
        self.assertEqual(len(self._by_kind("epic")), 2)
        self.assertEqual(len(self._by_kind("story")), 3)

    def test_no_sprints_are_emitted_here(self):
        self.assertEqual(self._by_kind("sprint"), [])

    def test_keys(self):
        self.assertEqual({r["key"] for r in self._by_kind("epic")}, {"E001", "E002"})
        self.assertEqual({r["key"] for r in self._by_kind("story")},
                         {"E001-S01-001", "E001-S01-002", "E002-S01-001"})

    def test_statuses_carry_through(self):
        got = {r["key"]: r["status"] for r in self.recs}
        self.assertEqual(got["E001"], "in-progress")
        self.assertEqual(got["E001-S01-001"], "done")
        self.assertEqual(got["E002"], "backlog")

    def test_title_comes_from_the_slug(self):
        got = {r["key"]: r["title"] for r in self.recs}
        self.assertEqual(got["E001-S01-001"], "User authentication")

    def test_an_l3io_schema_file_yields_ZERO_records(self):
        p = self._tmp("epics:\n  - key: 'E001'\n    status: backlog\n")
        self.assertEqual(rd.read(p), [])

    def test_unknown_status_value_is_dropped_not_guessed(self):
        self.assertEqual(rd.read(self._tmp("development_status:\n  epic-1: wat\n")), [])

    def test_a_review_status_maps_to_in_progress_for_an_epic(self):
        recs = rd.read(self._tmp("development_status:\n  epic-1: review\n"))
        self.assertEqual(recs[0]["status"], "in-progress")

    def test_a_review_status_stays_review_for_a_story(self):
        recs = rd.read(self._tmp("development_status:\n  1-1-thing: review\n"))
        self.assertEqual(recs[0]["status"], "review")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run it to verify it fails**

Run: `uv run skills/l3io-util-doctor/scripts/tests/test-read-bmad-flat.py`
Expected: FAIL — `read-bmad-flat.py` does not exist.

- [ ] **Step 4: Implement the reader**

```python
#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
"""
read-bmad-flat.py -- read BASE BMAD's sprint-status.yaml into records.

This is the file `bmad-sprint-planning`, `bmad-build` and `bmad-retrospective` all read.
Its schema (bmad-sprint-planning/sprint-status-template.yaml:53-66) is a flat
`development_status:` MAPPING of node id to status, with two id shapes:

    development_status:
      epic-1: backlog                  # an epic
      1-1-user-authentication: done    # epic 1, story 1

There is NO sprint concept in this schema. Every story emitted here is keyed into sprint
S01, and no sprint records are produced -- the engine creates the sprint node from the
story's own path. Reconstructing real sprint boundaries needs story artifacts, which is
read-artifacts.py's job, and those nodes are marked `origin: inferred`.

Statuses are MAPPED from a table, never guessed: an id whose status is not one this
package recognises is DROPPED, because calibration would consume a wrong status as a real
sample. An epic has no `review`/`ready-for-dev` state, so those fold to the nearest epic
status rather than being discarded.

Reader contract: pure. No writes, no refusal on an empty result.

Usage:  read-bmad-flat.py --file PATH [--format json]
Exit 0 -- parsed (zero records is success)
Exit 1 -- the file does not exist
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "state_record", os.path.join(_HERE, "state-record.py"))
sr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sr)

_EPIC_ID = re.compile(r"^epic-(\d+)$")
_STORY_ID = re.compile(r"^(\d+)-(\d+)-(.+)$")

_STORY_STATUS_MAP = {
    "backlog": "backlog",
    "ready-for-dev": "ready-for-dev",
    "in-progress": "in-progress",
    "review": "review",
    "done": "done",
}
_EPIC_STATUS_MAP = {
    "backlog": "backlog",
    "ready-for-dev": "backlog",
    "in-progress": "in-progress",
    "review": "in-progress",
    "done": "done",
}


def parse_id(node_id: str):
    """Classify a BMad development_status key. Returns (kind, our_key) or None."""
    node_id = (node_id or "").strip()
    m = _EPIC_ID.match(node_id)
    if m:
        return "epic", f"E{int(m.group(1)):03d}"
    m = _STORY_ID.match(node_id)
    if m:
        epic_n, story_n = int(m.group(1)), int(m.group(2))
        return "story", f"E{epic_n:03d}-S01-{story_n:03d}"
    return None


def _title_from_slug(node_id: str) -> str:
    m = _STORY_ID.match((node_id or "").strip())
    if not m:
        return ""
    return m.group(3).replace("-", " ").replace("_", " ").strip().capitalize()


def read(path: Path) -> list:
    from ruamel.yaml import YAML
    from ruamel.yaml.error import YAMLError

    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    if not text.strip():
        return []
    try:
        data = YAML(typ="safe").load(text)
    except YAMLError:
        return []
    if not isinstance(data, dict):
        return []
    status_map = data.get("development_status")
    if not isinstance(status_map, dict):
        return []

    name = Path(path).name
    out = []
    for node_id, raw_status in status_map.items():
        parsed = parse_id(str(node_id))
        if parsed is None:
            continue
        kind, key = parsed
        raw = str(raw_status).strip()
        table = _EPIC_STATUS_MAP if kind == "epic" else _STORY_STATUS_MAP
        if raw not in table:
            continue
        out.append(sr.make_record(
            kind, key, table[raw],
            _title_from_slug(str(node_id)) if kind == "story" else "",
            f"{name}:development_status[{node_id}]"))

    return sr.dedupe(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="read base BMad's sprint-status.yaml")
    parser.add_argument("--file", required=True)
    parser.add_argument("--format", choices=["json"], default="json")
    args = parser.parse_args(argv)

    p = Path(args.file)
    if not p.is_file():
        sys.stderr.write(f"read-bmad-flat.py: no such file: {p}\n")
        return 1
    json.dump(read(p), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tests**

Run: `uv run skills/l3io-util-doctor/scripts/tests/test-read-bmad-flat.py`
Expected: PASS (14 tests).

- [ ] **Step 6: Regenerate the manifest and run the gates**

```bash
npm run check:manifest -- --write
npm run check:docs && npm run check:scripts && npm run check:module && npm run check:manifest
```

- [ ] **Step 7: Commit**

```bash
git add skills/l3io-util-doctor/scripts/read-bmad-flat.py \
        skills/l3io-util-doctor/scripts/tests/test-read-bmad-flat.py \
        skills/l3io-util-doctor/scripts/tests/fixtures/bmad-flat/ \
        skills/l3io-util-doctor/payload-manifest.json
git commit -s -m "feat(l3io-util): reader for base BMad's development_status mapping

The schema this package could not read at all -- there were zero functional
references to development_status before this. Statuses are mapped from a table,
never guessed: an unrecognised value drops the node, because calibration would
consume a wrong status as a real sample."
```

---

## Task 7: Reader — legacy per-epic `_bmad/state/`

**Files:**
- Create: `skills/l3io-util-doctor/scripts/read-per-epic.py`
- Create: `skills/l3io-util-doctor/scripts/tests/test-read-per-epic.py`
- Create: `skills/l3io-util-doctor/scripts/tests/fixtures/per-epic/_bmad/state/epic-001.yaml`
- Create: `skills/l3io-util-doctor/scripts/tests/fixtures/per-epic/_bmad/state/epic-002.yaml`

**Interfaces:**
- Consumes: `state-record.py`'s `make_record`, `dedupe`.
- Produces: `read(state_dir: Path) -> list[dict]`; CLI `read-per-epic.py --dir PATH [--format json]`. Note this reader takes a **directory**, not a file — the layout is one file per epic.

- [ ] **Step 1: Write the fixtures**

`skills/l3io-util-doctor/scripts/tests/fixtures/per-epic/_bmad/state/epic-001.yaml`:

```yaml
key: 'E001'
title: Authentication
status: in-progress
sprints:
  - key: 'S01'
    title: Login flow
    status: done
    stories:
      - key: 'E001-S01-001'
        title: Password login
        status: done
```

`skills/l3io-util-doctor/scripts/tests/fixtures/per-epic/_bmad/state/epic-002.yaml`:

```yaml
key: 'E002'
title: Reporting
status: backlog
sprints: []
```

- [ ] **Step 2: Write the failing test**

Create `skills/l3io-util-doctor/scripts/tests/test-read-per-epic.py`:

```python
#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
"""Tests for read-per-epic.py — run with: uv run test-read-per-epic.py"""
import importlib.util
import os
import shutil
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = Path(HERE) / "fixtures" / "per-epic" / "_bmad" / "state"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(os.path.dirname(HERE), filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rd = _load("read_per_epic", "read-per-epic.py")


class TestReadPerEpic(unittest.TestCase):
    def setUp(self):
        self.recs = rd.read(FIXTURE)

    def _by_kind(self, k):
        return [r for r in self.recs if r["kind"] == k]

    def _tmpdir(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        return d

    def test_both_epic_files_are_read(self):
        self.assertEqual({r["key"] for r in self._by_kind("epic")}, {"E001", "E002"})

    def test_nested_children_are_emitted(self):
        self.assertEqual({r["key"] for r in self._by_kind("sprint")}, {"E001-S01"})
        self.assertEqual({r["key"] for r in self._by_kind("story")}, {"E001-S01-001"})

    def test_statuses_carry_through(self):
        got = {r["key"]: r["status"] for r in self.recs}
        self.assertEqual(got["E001"], "in-progress")
        self.assertEqual(got["E001-S01"], "done")
        self.assertEqual(got["E002"], "backlog")

    def test_source_names_the_epic_file(self):
        got = {r["key"]: r["source"] for r in self.recs}
        self.assertIn("epic-001.yaml", got["E001"])
        self.assertIn("epic-002.yaml", got["E002"])

    def test_an_epic_shell_and_its_full_epic_merge_to_one(self):
        """The dedupe defect, as a test. Two files naming E001 -- a shell and the
        real one -- must produce ONE record, not two that land in two folders."""
        d = self._tmpdir()
        (d / "epic-001.yaml").write_text(
            "key: 'E001'\ntitle: ''\nstatus: backlog\n", encoding="utf-8")
        (d / "epic-001-full.yaml").write_text(
            "key: 'E001'\ntitle: Real\nstatus: in-progress\n", encoding="utf-8")
        recs = [r for r in rd.read(d) if r["kind"] == "epic"]
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["title"], "Real")

    def test_missing_directory_yields_zero_records(self):
        self.assertEqual(rd.read(Path("/nonexistent/state")), [])

    def test_unparseable_file_is_skipped_not_fatal(self):
        d = self._tmpdir()
        (d / "epic-001.yaml").write_text("key: 'E001'\nstatus: backlog\n", encoding="utf-8")
        (d / "epic-002.yaml").write_text("a: [1,\n", encoding="utf-8")
        self.assertEqual({r["key"] for r in rd.read(d)}, {"E001"})

    def test_a_file_without_a_key_is_skipped(self):
        d = self._tmpdir()
        (d / "epic-001.yaml").write_text("title: nameless\nstatus: backlog\n",
                                         encoding="utf-8")
        self.assertEqual(rd.read(d), [])

    def test_files_are_read_in_sorted_order(self):
        d = self._tmpdir()
        (d / "epic-002.yaml").write_text("key: 'E002'\nstatus: backlog\n", encoding="utf-8")
        (d / "epic-001.yaml").write_text("key: 'E001'\nstatus: backlog\n", encoding="utf-8")
        self.assertEqual([r["key"] for r in rd.read(d)], ["E001", "E002"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run it to verify it fails**

Run: `uv run skills/l3io-util-doctor/scripts/tests/test-read-per-epic.py`
Expected: FAIL — `read-per-epic.py` does not exist.

- [ ] **Step 4: Implement the reader**

```python
#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
"""
read-per-epic.py -- read the legacy per-epic layout at {project-root}/_bmad/state/.

One YAML file per epic, each a bare epic node with `sprints:` nested inside it and
`stories:` inside those. Files are read in sorted order so the result is deterministic.

An unparseable file is SKIPPED, not fatal: one corrupt epic must not hide the other nine
from the migration plan the user is about to confirm.

Reader contract: pure. No writes, no refusal on an empty result.

Usage:  read-per-epic.py --dir PATH [--format json]
Exit 0 -- parsed (zero records is success)
Exit 1 -- the directory does not exist
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "state_record", os.path.join(_HERE, "state-record.py"))
sr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sr)


def _read_one(path: Path) -> list:
    from ruamel.yaml import YAML
    from ruamel.yaml.error import YAMLError

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    if not text.strip():
        return []
    try:
        epic = YAML(typ="safe").load(text)
    except YAMLError:
        return []
    if not isinstance(epic, dict):
        return []
    ekey = str(epic.get("key", "")).strip()
    if not ekey:
        return []

    name = path.name
    out = [sr.make_record(
        "epic", ekey, str(epic.get("status", "backlog")),
        str(epic.get("title", "")), f"{name}:{ekey}")]

    for sprint in epic.get("sprints") or []:
        if not isinstance(sprint, dict):
            continue
        skey = str(sprint.get("key", "")).strip()
        if not skey:
            continue
        out.append(sr.make_record(
            "sprint", f"{ekey}-{skey}", str(sprint.get("status", "backlog")),
            str(sprint.get("title", "")), f"{name}:{ekey}.sprints[{skey}]"))
        for story in sprint.get("stories") or []:
            if not isinstance(story, dict):
                continue
            stkey = str(story.get("key", "")).strip()
            if not stkey:
                continue
            out.append(sr.make_record(
                "story", stkey, str(story.get("status", "backlog")),
                str(story.get("title", "")),
                f"{name}:{ekey}.sprints[{skey}].stories[{stkey}]"))
    return out


def read(state_dir: Path) -> list:
    """Parse every epic file under state_dir into normalised records."""
    d = Path(state_dir)
    if not d.is_dir():
        return []
    out = []
    for path in sorted(d.glob("*.yaml")):
        out.extend(_read_one(path))
    return sr.dedupe(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="read the legacy per-epic state layout")
    parser.add_argument("--dir", required=True, help="the _bmad/state directory")
    parser.add_argument("--format", choices=["json"], default="json")
    args = parser.parse_args(argv)

    d = Path(args.dir)
    if not d.is_dir():
        sys.stderr.write(f"read-per-epic.py: no such directory: {d}\n")
        return 1
    json.dump(read(d), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tests**

Run: `uv run skills/l3io-util-doctor/scripts/tests/test-read-per-epic.py`
Expected: PASS (9 tests), including the dedupe case.

- [ ] **Step 6: Regenerate the manifest and run the gates**

```bash
npm run check:manifest -- --write
npm run check:docs && npm run check:scripts && npm run check:module && npm run check:manifest
```

- [ ] **Step 7: Commit**

```bash
git add skills/l3io-util-doctor/scripts/read-per-epic.py \
        skills/l3io-util-doctor/scripts/tests/test-read-per-epic.py \
        skills/l3io-util-doctor/scripts/tests/fixtures/per-epic/ \
        skills/l3io-util-doctor/payload-manifest.json
git commit -s -m "feat(l3io-util): reader for the legacy per-epic _bmad/state layout

Includes the shell-plus-full-epic dedupe case as a test -- the defect that was
present on both source paths and filed on only one. An unparseable epic file is
skipped rather than fatal, so one corrupt file cannot hide the rest from the
plan the user confirms."
```

---

## Task 8: Reader — split three-file layout

**Files:**
- Create: `skills/l3io-util-doctor/scripts/read-split.py`
- Create: `skills/l3io-util-doctor/scripts/tests/test-read-split.py`
- Create: `skills/l3io-util-doctor/scripts/tests/fixtures/split/sprint-status.yaml`
- Create: `skills/l3io-util-doctor/scripts/tests/fixtures/split/sprint-status-backlog.yaml`
- Create: `skills/l3io-util-doctor/scripts/tests/fixtures/split/sprint-status-archived.yaml`

**Interfaces:**
- Consumes: `read-l3io-flat.py`'s `read(path)` — each split file carries the same `epics:` list shape, so this reader composes that one rather than reimplementing it. Also `state-record.py`'s `dedupe`.
- Produces: `read(artifacts_dir: Path) -> list[dict]`; `SPLIT_FILES: tuple[str, ...]`; CLI `read-split.py --dir PATH [--format json]`.

**Why this reader composes rather than parses:** the three split files are the same schema as the legacy flat file, partitioned by status. Parsing it twice would be the second copy that drifts. This reader's whole job is *which files*, and joining them under one dedupe rule.

- [ ] **Step 1: Write the fixtures**

`skills/l3io-util-doctor/scripts/tests/fixtures/split/sprint-status.yaml`:

```yaml
epics:
  - key: 'E001'
    title: Authentication
    status: in-progress
    sprints:
      - key: 'S01'
        title: Login flow
        status: in-progress
        stories:
          - key: 'E001-S01-001'
            title: Password login
            status: review
```

`skills/l3io-util-doctor/scripts/tests/fixtures/split/sprint-status-backlog.yaml`:

```yaml
epics:
  - key: 'E002'
    title: Reporting
    status: backlog
    sprints: []
```

`skills/l3io-util-doctor/scripts/tests/fixtures/split/sprint-status-archived.yaml`:

```yaml
epics:
  - key: 'E003'
    title: Onboarding
    status: done
    sprints:
      - key: 'S01'
        title: Welcome tour
        status: done
        stories:
          - key: 'E003-S01-001'
            title: Tour steps
            status: done
```

- [ ] **Step 2: Write the failing test**

Create `skills/l3io-util-doctor/scripts/tests/test-read-split.py`:

```python
#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
"""Tests for read-split.py — run with: uv run test-read-split.py"""
import importlib.util
import os
import shutil
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = Path(HERE) / "fixtures" / "split"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(os.path.dirname(HERE), filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rd = _load("read_split", "read-split.py")


class TestReadSplit(unittest.TestCase):
    def setUp(self):
        self.recs = rd.read(FIXTURE)

    def _by_kind(self, k):
        return [r for r in self.recs if r["kind"] == k]

    def _tmpdir(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        return d

    def test_all_three_files_contribute(self):
        self.assertEqual({r["key"] for r in self._by_kind("epic")},
                         {"E001", "E002", "E003"})

    def test_children_from_active_and_archived(self):
        self.assertEqual({r["key"] for r in self._by_kind("sprint")},
                         {"E001-S01", "E003-S01"})
        self.assertEqual({r["key"] for r in self._by_kind("story")},
                         {"E001-S01-001", "E003-S01-001"})

    def test_statuses_carry_through(self):
        got = {r["key"]: r["status"] for r in self.recs}
        self.assertEqual(got["E001"], "in-progress")
        self.assertEqual(got["E002"], "backlog")
        self.assertEqual(got["E003"], "done")

    def test_source_distinguishes_the_three_files(self):
        got = {r["key"]: r["source"] for r in self.recs}
        self.assertIn("sprint-status.yaml", got["E001"])
        self.assertIn("sprint-status-backlog.yaml", got["E002"])
        self.assertIn("sprint-status-archived.yaml", got["E003"])

    def test_absent_optional_files_are_fine(self):
        d = self._tmpdir()
        (d / "sprint-status.yaml").write_text(
            "epics:\n  - key: 'E001'\n    title: A\n    status: backlog\n",
            encoding="utf-8")
        self.assertEqual({r["key"] for r in rd.read(d)}, {"E001"})

    def test_a_key_in_two_files_yields_one_record(self):
        d = self._tmpdir()
        (d / "sprint-status.yaml").write_text(
            "epics:\n  - key: 'E001'\n    title: Real\n    status: in-progress\n",
            encoding="utf-8")
        (d / "sprint-status-backlog.yaml").write_text(
            "epics:\n  - key: 'E001'\n    title: ''\n    status: backlog\n",
            encoding="utf-8")
        recs = [r for r in rd.read(d) if r["kind"] == "epic"]
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["title"], "Real")

    def test_empty_directory_yields_zero_records(self):
        self.assertEqual(rd.read(self._tmpdir()), [])

    def test_missing_directory_yields_zero_records(self):
        self.assertEqual(rd.read(Path("/nonexistent/artifacts")), [])

    def test_split_files_constant_is_the_three_names(self):
        self.assertEqual(
            rd.SPLIT_FILES,
            ("sprint-status.yaml", "sprint-status-backlog.yaml",
             "sprint-status-archived.yaml"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run it to verify it fails**

Run: `uv run skills/l3io-util-doctor/scripts/tests/test-read-split.py`
Expected: FAIL — `read-split.py` does not exist.

- [ ] **Step 4: Implement the reader**

```python
#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
"""
read-split.py -- read the split three-file status layout into records.

The split layout partitions the SAME `epics:` list schema as the legacy flat file across
three files by status:

    sprint-status.yaml            active
    sprint-status-backlog.yaml    backlog
    sprint-status-archived.yaml   done

So this reader does not parse anything itself -- it composes read-l3io-flat.py and owns
only two decisions: WHICH files, and joining them under one dedupe rule. A second parser
for the same schema is the copy that drifts.

Every file is optional; a project may carry any subset.

Reader contract: pure. No writes, no refusal on an empty result.

Usage:  read-split.py --dir PATH [--format json]
Exit 0 -- parsed (zero records is success)
Exit 1 -- the directory does not exist
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_HERE, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sr = _load("state_record", "state-record.py")
flat = _load("read_l3io_flat", "read-l3io-flat.py")

SPLIT_FILES = (
    "sprint-status.yaml",
    "sprint-status-backlog.yaml",
    "sprint-status-archived.yaml",
)


def read(artifacts_dir: Path) -> list:
    """Parse every present split file into one deduped record list."""
    d = Path(artifacts_dir)
    if not d.is_dir():
        return []
    out = []
    for name in SPLIT_FILES:
        p = d / name
        if p.is_file():
            out.extend(flat.read(p))
    return sr.dedupe(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="read the split three-file status layout")
    parser.add_argument("--dir", required=True,
                        help="the implementation_artifacts directory")
    parser.add_argument("--format", choices=["json"], default="json")
    args = parser.parse_args(argv)

    d = Path(args.dir)
    if not d.is_dir():
        sys.stderr.write(f"read-split.py: no such directory: {d}\n")
        return 1
    json.dump(read(d), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tests**

Run: `uv run skills/l3io-util-doctor/scripts/tests/test-read-split.py`
Expected: PASS (9 tests).

- [ ] **Step 6: Regenerate the manifest and run the gates**

```bash
npm run check:manifest -- --write
npm run check:docs && npm run check:scripts && npm run check:module && npm run check:manifest
```

- [ ] **Step 7: Commit**

```bash
git add skills/l3io-util-doctor/scripts/read-split.py \
        skills/l3io-util-doctor/scripts/tests/test-read-split.py \
        skills/l3io-util-doctor/scripts/tests/fixtures/split/ \
        skills/l3io-util-doctor/payload-manifest.json
git commit -s -m "feat(l3io-util): reader for the split three-file status layout

Composes read-l3io-flat rather than parsing the same schema a second time; it
owns only which files and the join. Every file is optional."
```

---

## Task 9: Reader — story artifacts, with sprint inference

**Files:**
- Create: `skills/l3io-util-doctor/scripts/read-artifacts.py`
- Create: `skills/l3io-util-doctor/scripts/tests/test-read-artifacts.py`
- Create: `skills/l3io-util-doctor/scripts/tests/fixtures/artifacts/epic-001/sprint-01/stories/E001-S01-001.md`
- Create: `skills/l3io-util-doctor/scripts/tests/fixtures/artifacts/epic-001/sprint-01/stories/E001-S01-002.md`
- Create: `skills/l3io-util-doctor/scripts/tests/fixtures/artifacts/epic-001/sprint-02/stories/E001-S02-001.md`

**Interfaces:**
- Consumes: `state-record.py`'s `make_record`, `dedupe`, `VALID_STATUS`.
- Produces: `read(artifacts_dir: Path) -> list[dict]`; `parse_frontmatter(text: str) -> dict`; CLI `read-artifacts.py --dir PATH [--format json]`.

**This is the reader that replaces `bootstrap-state.md`'s inline writer.** It walks `{implementation_artifacts}/epic-XX/sprint-YY/stories/*.md`, reads each story's YAML frontmatter, and derives the sprint and epic nodes from the directory structure the stories already sit in. Sprint and epic nodes are **marked `origin: inferred`** because nothing in the source states them — the story files imply them by location.

**Frontmatter is parsed as YAML, never by regex** (Global Constraints). A story `.md` with no parseable frontmatter is skipped rather than guessed at.

- [ ] **Step 1: Write the fixtures**

`.../artifacts/epic-001/sprint-01/stories/E001-S01-001.md`:

```markdown
---
key: 'E001-S01-001'
title: Password login
status: done
classification: feature
---

# Password login

As a user I want to sign in with a password.
```

`.../artifacts/epic-001/sprint-01/stories/E001-S01-002.md`:

```markdown
---
key: 'E001-S01-002'
title: Session cookies
status: review
---

# Session cookies
```

`.../artifacts/epic-001/sprint-02/stories/E001-S02-001.md`:

```markdown
---
key: 'E001-S02-001'
title: Google provider
status: ready-for-dev
classification: feature
---

# Google provider
```

- [ ] **Step 2: Write the failing test**

Create `skills/l3io-util-doctor/scripts/tests/test-read-artifacts.py`:

```python
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
```

- [ ] **Step 3: Run it to verify it fails**

Run: `uv run skills/l3io-util-doctor/scripts/tests/test-read-artifacts.py`
Expected: FAIL — `read-artifacts.py` does not exist.

- [ ] **Step 4: Implement the reader**

```python
#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
"""
read-artifacts.py -- derive records from story .md artifacts alone, for a project that
has stories but no status file.

This replaces the inline write_node() in steps/bootstrap-state.md, which assembled state
paths at six sites and wrote nodes directly -- bypassing the epic write lock, the event
log and status validation.

Stories are READ: each `{artifacts}/epic-XX/sprint-YY/stories/*.md` carries YAML
frontmatter with its key, title and status. Sprints and epics are INFERRED from the
directory structure the stories already sit in, and are marked `origin: inferred` with a
note, because nothing in the source states them -- the stories imply them by location.
Absence of `origin` means "read directly", which is why no schema version bump is needed.

Inference rule, stated ONCE and applied at both levels so they cannot drift:
    done        -- every child is done
    backlog     -- no child has started (all backlog or ready-for-dev)
    in-progress -- otherwise

Frontmatter is parsed as YAML, never by regex. A story with no parseable frontmatter, or
with a status this package does not recognise, is SKIPPED: guessing would feed calibration
a sample nobody measured.

Reader contract: pure. No writes, no refusal on an empty result.

Usage:  read-artifacts.py --dir PATH [--format json]
Exit 0 -- parsed (zero records is success)
Exit 1 -- the directory does not exist
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "state_record", os.path.join(_HERE, "state-record.py"))
sr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sr)

_EPIC_DIR = re.compile(r"^epic-(\d+)$")
_SPRINT_DIR = re.compile(r"^sprint-(\d+)$")

_NOT_STARTED = {"backlog", "ready-for-dev"}


def parse_frontmatter(text: str) -> dict:
    """Return the YAML frontmatter block as a dict, or {} when absent or malformed."""
    from ruamel.yaml import YAML
    from ruamel.yaml.error import YAMLError

    if not text.startswith("---"):
        return {}
    lines = text.splitlines()
    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break
    if end is None:
        return {}
    try:
        data = YAML(typ="safe").load("\n".join(lines[1:end]))
    except YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _roll_up(child_statuses: list) -> str:
    """One rule, used for both sprint-from-stories and epic-from-sprints."""
    if not child_statuses:
        return "backlog"
    if all(s == "done" for s in child_statuses):
        return "done"
    if all(s in _NOT_STARTED for s in child_statuses):
        return "backlog"
    return "in-progress"


def read(artifacts_dir: Path) -> list:
    """Derive records from a tree of story artifacts."""
    root = Path(artifacts_dir)
    if not root.is_dir():
        return []

    stories = []
    grouped = {}

    for epic_dir in sorted(root.iterdir()):
        m_epic = _EPIC_DIR.match(epic_dir.name) if epic_dir.is_dir() else None
        if not m_epic:
            continue
        epic_key = f"E{int(m_epic.group(1)):03d}"

        for sprint_dir in sorted(epic_dir.iterdir()):
            m_sprint = _SPRINT_DIR.match(sprint_dir.name) if sprint_dir.is_dir() else None
            if not m_sprint:
                continue
            sprint_num = int(m_sprint.group(1))
            sprint_key = f"{epic_key}-S{sprint_num:02d}"

            stories_dir = sprint_dir / "stories"
            if not stories_dir.is_dir():
                continue
            for md in sorted(stories_dir.glob("*.md")):
                try:
                    meta = parse_frontmatter(md.read_text(encoding="utf-8"))
                except OSError:
                    continue
                key = str(meta.get("key", "")).strip()
                status = str(meta.get("status", "")).strip()
                if not key or status not in sr.VALID_STATUS["story"]:
                    continue
                stories.append(sr.make_record(
                    "story", key, status, str(meta.get("title", "")),
                    str(md.relative_to(root))))
                grouped.setdefault((epic_key, sprint_key), []).append(status)

    if not stories:
        return []

    sprints = []
    by_epic = {}
    for (epic_key, sprint_key), statuses in sorted(grouped.items()):
        status = _roll_up(statuses)
        sprints.append(sr.make_record(
            "sprint", sprint_key, status, f"Sprint {sprint_key.split('-S')[1]}",
            f"{len(statuses)} story file(s) under {sprint_key}",
            origin="inferred",
            origin_note="derived from the story artifacts in this sprint directory"))
        by_epic.setdefault(epic_key, []).append(status)

    epics = []
    for epic_key, sprint_statuses in sorted(by_epic.items()):
        epics.append(sr.make_record(
            "epic", epic_key, _roll_up(sprint_statuses), "",
            f"{len(sprint_statuses)} sprint directory/ies under {epic_key}",
            origin="inferred",
            origin_note="derived from the sprint directories holding this epic's stories"))

    return sr.dedupe(epics + sprints + stories)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="derive records from story artifacts")
    parser.add_argument("--dir", required=True,
                        help="the implementation_artifacts directory")
    parser.add_argument("--format", choices=["json"], default="json")
    args = parser.parse_args(argv)

    d = Path(args.dir)
    if not d.is_dir():
        sys.stderr.write(f"read-artifacts.py: no such directory: {d}\n")
        return 1
    json.dump(read(d), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tests**

Run: `uv run skills/l3io-util-doctor/scripts/tests/test-read-artifacts.py`
Expected: PASS (17 tests).

- [ ] **Step 6: Regenerate the manifest and run the gates**

```bash
npm run check:manifest -- --write
npm run check:docs && npm run check:scripts && npm run check:module && npm run check:manifest
```

- [ ] **Step 7: Commit**

```bash
git add skills/l3io-util-doctor/scripts/read-artifacts.py \
        skills/l3io-util-doctor/scripts/tests/test-read-artifacts.py \
        skills/l3io-util-doctor/scripts/tests/fixtures/artifacts/ \
        skills/l3io-util-doctor/payload-manifest.json
git commit -s -m "feat(l3io-util): derive records from story artifacts, sprints inferred

Replaces the inline write_node() in bootstrap-state.md. Stories are read from
YAML frontmatter; sprints and epics are inferred from the directory structure
and marked origin: inferred with a note. One roll-up rule serves both levels so
they cannot drift apart. A story with no parseable frontmatter, or an
unrecognised status, is skipped rather than guessed."
```

---

## Task 10: The engine — detect, read, resolve, plan

**Files:**
- Create: `skills/l3io-util-doctor/scripts/migrate-engine.py`
- Create: `skills/l3io-util-doctor/scripts/tests/test-engine.py`

**Interfaces:**
- Consumes: every reader's `read()` (Tasks 5-9); `detect-layout.py`'s `classify_flat` (Task 1); `state-record.py`'s `dedupe` and `validate` (Task 2).
- Produces:
  - `READERS: dict[str, callable]` keyed by layout name, each taking `(artifacts_dir, project_root)`
  - `detect(artifacts_dir: Path, project_root: Path) -> str` returning one of `"l3io-flat"`, `"bmad-flat"`, `"per-epic"`, `"split"`, `"artifacts"`, `"none"`
  - `gather(layout: str, artifacts_dir: Path, project_root: Path) -> list[dict]`
  - `source_is_empty(layout, artifacts_dir, project_root) -> bool`
  - `build_plan(records: list[dict]) -> dict` with keys `records`, `counts`, `problems`
  - `render_plan(layout: str, plan: dict) -> str`
  - CLI `migrate-engine.py --artifacts DIR --project-root DIR --plan [--format json|text]`

Task 11 adds `gate`, `write`, `verify_against_plan` and `dispose` to this same file.

- [ ] **Step 1: Write the failing test**

Create `skills/l3io-util-doctor/scripts/tests/test-engine.py`:

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run skills/l3io-util-doctor/scripts/tests/test-engine.py`
Expected: FAIL — `migrate-engine.py` does not exist.

- [ ] **Step 3: Implement the read-only half**

Create `skills/l3io-util-doctor/scripts/migrate-engine.py`:

```python
#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
"""
migrate-engine.py -- the eight-step migration run.

    detect -> read -> resolve -> plan -> GATE -> write -> verify -> dispose

The gate sits BEFORE the write, and that position is the whole point. The previous prose
migration ran its completeness checks AFTER writing and before deleting the source, so a
parse that produced zero nodes passed every check vacuously and then `rm -f`'d a live
BMad tracking file while reporting success. A gate placed before the write cannot do
that, whatever the cause of the empty parse -- including causes nobody has met yet.

Steps 1-4 are read-only and safe to run at any time. Steps 5-8 run only under --apply.

Usage:
  migrate-engine.py --artifacts DIR --project-root DIR --plan [--format json|text]
  migrate-engine.py --artifacts DIR --project-root DIR --apply --state-root DIR \\
                    --pm-status PATH [--dispose]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_HERE, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sr = _load("state_record", "state-record.py")
detect_layout = _load("detect_layout", "detect-layout.py")
_l3io = _load("read_l3io_flat", "read-l3io-flat.py")
_bmad = _load("read_bmad_flat", "read-bmad-flat.py")
_per_epic = _load("read_per_epic", "read-per-epic.py")
_split = _load("read_split", "read-split.py")
_artifacts = _load("read_artifacts", "read-artifacts.py")

# Keyed by the fixture directory name. test-engine.py asserts this key set equals the
# directories on disk, so a deleted fixture fails the suite rather than shrinking the
# corpus silently.
READERS = {
    "l3io-flat": lambda art, root: _l3io.read(art / "sprint-status.yaml"),
    "bmad-flat": lambda art, root: _bmad.read(art / "sprint-status.yaml"),
    "per-epic": lambda art, root: _per_epic.read(root / "_bmad" / "state"),
    "split": lambda art, root: _split.read(art),
    "artifacts": lambda art, root: _artifacts.read(art),
}

_KIND_ORDER = ("epic", "sprint", "story")


def detect(artifacts_dir: Path, project_root: Path) -> str:
    """Name the source layout present, or 'none'.

    Order matters. The split layout is checked FIRST because a split project also carries
    sprint-status.yaml, so checking the flat file first would misread every split project.
    And the flat file's SCHEMA is what separates l3io-flat from bmad-flat -- never its
    path, which both share.
    """
    art, root = Path(artifacts_dir), Path(project_root)

    if (art / "sprint-status-backlog.yaml").is_file() or \
       (art / "sprint-status-archived.yaml").is_file():
        return "split"

    flat = art / "sprint-status.yaml"
    if flat.is_file():
        schema = detect_layout.classify_flat(flat)
        if schema == "bmad":
            return "bmad-flat"
        if schema == "l3io":
            return "l3io-flat"

    legacy = root / "_bmad" / "state"
    if legacy.is_dir() and any(legacy.glob("*.yaml")):
        return "per-epic"

    if art.is_dir() and any(art.glob("epic-*/sprint-*/stories/*.md")):
        return "artifacts"

    return "none"


def gather(layout: str, artifacts_dir: Path, project_root: Path) -> list:
    """Run the reader for `layout`. An unknown layout yields zero records."""
    reader = READERS.get(layout)
    if reader is None:
        return []
    return sr.dedupe(reader(Path(artifacts_dir), Path(project_root)))


def source_is_empty(layout: str, artifacts_dir: Path, project_root: Path) -> bool:
    """True when the source this layout names holds no bytes worth parsing.

    Distinguishes 'there was nothing to migrate' (fine) from 'there was something and we
    parsed none of it' (the gate's business).
    """
    art, root = Path(artifacts_dir), Path(project_root)
    if layout in ("l3io-flat", "bmad-flat"):
        candidates = [art / "sprint-status.yaml"]
    elif layout == "split":
        candidates = [art / n for n in _split.SPLIT_FILES]
    elif layout == "per-epic":
        candidates = sorted((root / "_bmad" / "state").glob("*.yaml"))
    elif layout == "artifacts":
        candidates = sorted(art.glob("epic-*/sprint-*/stories/*.md"))
    else:
        candidates = []
    for p in candidates:
        try:
            if p.is_file() and p.read_text(encoding="utf-8").strip():
                return False
        except OSError:
            continue
    return True


def build_plan(records: list) -> dict:
    """Order records parents-first and report counts plus validation problems.

    Parents first is a hard requirement, not a nicety: `import-node` exits 3 on a sprint
    whose epic directory does not exist yet.
    """
    ordered = sorted(
        records,
        key=lambda r: _KIND_ORDER.index(r["kind"])
        if r.get("kind") in _KIND_ORDER else len(_KIND_ORDER))
    counts = {k: 0 for k in _KIND_ORDER}
    problems = []
    for rec in ordered:
        for p in sr.validate(rec):
            problems.append(f"{rec.get('kind')} {rec.get('key')!r}: {p}")
        if rec.get("kind") in counts:
            counts[rec["kind"]] += 1
    return {"records": ordered, "counts": counts, "problems": problems}


def render_plan(layout: str, plan: dict) -> str:
    lines = [
        f"MIGRATION PLAN -- source layout: {layout}",
        "=" * 64,
        f"  epics   {plan['counts']['epic']:>4}",
        f"  sprints {plan['counts']['sprint']:>4}",
        f"  stories {plan['counts']['story']:>4}",
    ]
    inferred = [r for r in plan["records"] if r.get("origin") == "inferred"]
    if inferred:
        lines.append(f"  ({len(inferred)} node(s) inferred, marked origin: inferred)")
    if plan["problems"]:
        lines.append("")
        lines.append("PROBLEMS:")
        lines.extend(f"  - {p}" for p in plan["problems"])
    lines.append("=" * 64)
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="the doctor's migration engine")
    parser.add_argument("--artifacts", required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--plan", action="store_true", help="read-only: show the plan")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args(argv)

    art, root = Path(args.artifacts), Path(args.project_root)
    layout = detect(art, root)
    if layout == "none":
        sys.stdout.write("No migratable source layout found -- nothing to do.\n")
        return 0

    plan = build_plan(gather(layout, art, root))
    if args.format == "json":
        json.dump({"layout": layout, **plan}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_plan(layout, plan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests**

Run: `uv run skills/l3io-util-doctor/scripts/tests/test-engine.py`
Expected: PASS (18 tests), including `test_every_fixture_directory_has_a_reader`.

- [ ] **Step 5: Prove the fixture-corpus test is not vacuous**

Temporarily rename one fixture directory:

```bash
mv skills/l3io-util-doctor/scripts/tests/fixtures/split \
   skills/l3io-util-doctor/scripts/tests/fixtures/split-moved
uv run skills/l3io-util-doctor/scripts/tests/test-engine.py -k FixtureCorpus
```
Expected: **FAIL**. If it passes, the test is not doing its job — fix it before restoring.

```bash
mv skills/l3io-util-doctor/scripts/tests/fixtures/split-moved \
   skills/l3io-util-doctor/scripts/tests/fixtures/split
```

- [ ] **Step 6: Regenerate the manifest and run the gates**

```bash
npm run check:manifest -- --write
npm run check:docs && npm run check:scripts && npm run check:module && npm run check:manifest
```

- [ ] **Step 7: Commit**

```bash
git add skills/l3io-util-doctor/scripts/migrate-engine.py \
        skills/l3io-util-doctor/scripts/tests/test-engine.py \
        skills/l3io-util-doctor/payload-manifest.json
git commit -s -m "feat(l3io-util): migration engine, read-only half

detect -> read -> resolve -> plan. Detection checks the split layout before the
flat file because both carry sprint-status.yaml, and separates l3io from BMad by
SCHEMA, never by path. Plans order parents first because import-node exits 3 on a
sprint whose epic does not exist. The fixture set is asserted equal to the reader
set, so deleting a fixture fails the suite."
```

---

## Task 11: The engine — gate, write, verify, dispose

**Files:**
- Modify: `skills/l3io-util-doctor/scripts/migrate-engine.py`
- Modify: `skills/l3io-util-doctor/scripts/tests/test-engine.py`

**Interfaces:**
- Consumes: from Task 10 — `detect`, `gather`, `build_plan`, `source_is_empty`, `render_plan`, `READERS`, `_split.SPLIT_FILES`. From Task 4 — the `pm-status.py import-node` CLI.
- Produces:
  - `gate(layout, plan, artifacts_dir, project_root) -> str | None` — a refusal message, or `None` to proceed
  - `write(plan, state_root, pm_status) -> tuple[int, list[str]]` returning `(written, errors)`
  - `verify_against_plan(plan, state_root) -> list[str]`
  - `dispose(layout, artifacts_dir, project_root) -> list[str]` returning the paths renamed
  - CLI flags `--apply`, `--state-root`, `--pm-status`, `--dispose`

- [ ] **Step 1: Write the failing tests**

Append to `skills/l3io-util-doctor/scripts/tests/test-engine.py`:

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run skills/l3io-util-doctor/scripts/tests/test-engine.py -k Gate`
Expected: FAIL — `module 'migrate_engine' has no attribute 'gate'`

- [ ] **Step 3: Implement the gate**

Insert into `migrate-engine.py` before `main()`:

```python
def gate(layout: str, plan: dict, artifacts_dir: Path, project_root: Path):
    """The pre-write gate. Returns a refusal message, or None to proceed.

    Two refusals, both BEFORE anything is written:

      1. The source holds content and the plan is EMPTY. This is the general form of the
         live defect -- a BMad-schema sprint-status.yaml read as if it were ours yields
         zero records, and the old prose then deleted the source while reporting success.
         The gate does not care WHY the parse produced nothing, which is exactly what
         makes it worth more than fixing any single cause.
      2. Any record failed validation. A plan that cannot be written correctly must not
         be half-written.
    """
    total = sum(plan["counts"].values())
    if total == 0 and not source_is_empty(layout, artifacts_dir, project_root):
        return (
            "BLOCKED: the source holds content but the plan is empty -- nothing would "
            f"be migrated.\n  layout detected: {layout}\n"
            "  Nothing has been written and the source is untouched.\n"
            "  A flat sprint-status.yaml carrying BMad's `development_status:` mapping "
            "is the common cause;\n  run `detect-layout.py --classify` to confirm which "
            "schema is present."
        )
    if plan["problems"]:
        listed = "\n".join(f"    - {p}" for p in plan["problems"][:10])
        more = "" if len(plan["problems"]) <= 10 else \
            f"\n    ... and {len(plan['problems']) - 10} more"
        return (
            f"BLOCKED: {len(plan['problems'])} record(s) failed validation.\n"
            f"{listed}{more}\n  Nothing has been written and the source is untouched."
        )
    return None
```

- [ ] **Step 4: Implement write, verify and dispose**

```python
def _node_argv(rec: dict) -> list:
    """The node-addressing flags for one record. Keys are E001 / E001-S01 / E001-S01-002."""
    kind, key = rec["kind"], rec["key"]
    if kind == "epic":
        return ["--epic", key]
    if kind == "sprint":
        epic_key, sprint_num = key.split("-S")
        return ["--epic", epic_key, "--sprint", f"S{sprint_num}"]
    return ["--story", key]


def write(plan: dict, state_root: Path, pm_status: str):
    """Write every planned record with `pm-status.py import-node`.

    Every node goes through the one writer verb -- never a direct file write -- so each
    lands under the same epic write lock, event log and status validation as any other
    state write. Returns (written_count, errors); a SKIP is not counted as written, which
    is what makes a retried migration idempotent.
    """
    import subprocess

    written, errors = 0, []
    for rec in plan["records"]:
        argv = ["uv", "run", pm_status, "import-node",
                "--state-root", str(state_root),
                "--status", rec["status"], "--title", rec.get("title", "")]
        argv += _node_argv(rec)
        if rec.get("origin"):
            argv += ["--origin", rec["origin"],
                     "--origin-note", rec.get("origin_note", "")]

        proc = subprocess.run(argv, capture_output=True, text=True)
        if proc.returncode != 0:
            errors.append(
                f"{rec['kind']} {rec['key']}: exit {proc.returncode} -- "
                f"{proc.stderr.strip()}")
        elif not proc.stdout.startswith("SKIP"):
            written += 1
    return written, errors


def _node_relpath(rec: dict):
    """(epic_key, path-relative-to-the-epic-directory) for one record."""
    kind, key = rec["kind"], rec["key"]
    if kind == "epic":
        return key, "epic.yaml"
    if kind == "sprint":
        epic_key, sprint_num = key.split("-S")
        return epic_key, os.path.join(f"sprint-{int(sprint_num):02d}", "sprint.yaml")
    epic_key, sprint_part, _ = key.split("-", 2)
    return epic_key, os.path.join(f"sprint-{int(sprint_part[1:]):02d}", f"{key}.yaml")


def verify_against_plan(plan: dict, state_root: Path) -> list:
    """Read the tree back and compare it to THE PLAN, not to itself.

    Stage E of the old prose checked its result against the set it had just produced, so
    an empty set verified clean. This reads each planned record's node off disk and
    compares key and status, so a node that was never written, or was written wrong, is
    reported.
    """
    from ruamel.yaml import YAML

    problems = []
    root = Path(state_root)
    for rec in plan["records"]:
        epic_key, rel = _node_relpath(rec)
        epic_dirname = f"epic-{int(epic_key[1:]):03d}"

        found = None
        for folder in ("active", "planned", "archived"):
            cand = root / folder / epic_dirname / rel
            if cand.is_file():
                found = cand
                break
        if found is None:
            problems.append(f"{rec['kind']} {rec['key']}: planned but not found on disk")
            continue
        try:
            node = YAML(typ="safe").load(found.read_text(encoding="utf-8"))
        except Exception as exc:
            problems.append(f"{rec['kind']} {rec['key']}: unreadable on disk -- {exc}")
            continue
        if not isinstance(node, dict):
            problems.append(f"{rec['kind']} {rec['key']}: not a mapping on disk")
            continue
        if str(node.get("status")) != rec["status"]:
            problems.append(
                f"{rec['kind']} {rec['key']}: status on disk {node.get('status')!r} "
                f"!= planned {rec['status']!r}")
    return problems


def dispose(layout: str, artifacts_dir: Path, project_root: Path) -> list:
    """Rename the source aside. NEVER deletes.

    The old Stage F `rm -f`'d the source. A rename to `.legacy` is recoverable by a human
    with no backup to find, and detect-layout.py deliberately does not match the `.legacy`
    name, so a migrated project reads clean afterwards.

    The 'artifacts' layout has no source to retire: story .md files are artifacts, and
    artifacts are never moved.
    """
    art, root = Path(artifacts_dir), Path(project_root)
    if layout in ("l3io-flat", "bmad-flat"):
        candidates = [art / "sprint-status.yaml"]
    elif layout == "split":
        candidates = [art / n for n in _split.SPLIT_FILES]
    elif layout == "per-epic":
        candidates = sorted((root / "_bmad" / "state").glob("*.yaml"))
    else:
        candidates = []

    moved = []
    for p in candidates:
        if p.is_file():
            p.rename(p.with_suffix(p.suffix + ".legacy"))
            moved.append(str(p))
    return moved
```

- [ ] **Step 5: Extend `main()` with `--apply`**

Add the flags beside the existing ones:

```python
    parser.add_argument("--apply", action="store_true", help="write the plan")
    parser.add_argument("--state-root", help="required with --apply")
    parser.add_argument("--pm-status", help="path to pm-status.py; required with --apply")
    parser.add_argument("--dispose", action="store_true",
                        help="rename the source aside after a verified write")
```

Immediately after `args = parser.parse_args(argv)`:

```python
    if args.apply and not (args.state_root and args.pm_status):
        parser.error("--apply requires --state-root and --pm-status")
```

And replace the tail of `main()` (everything after `plan = build_plan(...)`) with:

```python
    if not args.apply:
        if args.format == "json":
            json.dump({"layout": layout, **plan}, sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            sys.stdout.write(render_plan(layout, plan))
        return 0

    refusal = gate(layout, plan, art, root)
    if refusal:
        sys.stderr.write(refusal + "\n")
        return 1

    written, errors = write(plan, Path(args.state_root), args.pm_status)
    if errors:
        sys.stderr.write("FAILED during write -- source untouched:\n")
        for e in errors:
            sys.stderr.write(f"  {e}\n")
        return 1

    problems = verify_against_plan(plan, Path(args.state_root))
    if problems:
        sys.stderr.write("FAILED verification against the plan -- source untouched:\n")
        for p in problems:
            sys.stderr.write(f"  {p}\n")
        return 1

    sys.stdout.write(f"OK wrote {written} node(s); verified against the plan.\n")
    if args.dispose:
        for p in dispose(layout, art, root):
            sys.stdout.write(f"  retired {p} -> {p}.legacy\n")
    return 0
```

- [ ] **Step 6: Run the full engine suite**

Run: `uv run skills/l3io-util-doctor/scripts/tests/test-engine.py`
Expected: PASS (33 tests), including the gate BLOCK case, the corrupted-node verify case, and idempotency.

- [ ] **Step 7: Prove the gate test actually exercises the gate**

Temporarily change `gate()`'s first branch to `return None`:

Run: `uv run skills/l3io-util-doctor/scripts/tests/test-engine.py -k test_non_empty_source_with_empty_plan_BLOCKS`
Expected: **FAIL**. If it passes, the test is not exercising the gate — fix the test before restoring the code.

Restore `gate()` and re-run the whole suite.

- [ ] **Step 8: Regenerate the manifest and run the gates**

```bash
npm run check:manifest -- --write
npm run check:docs && npm run check:scripts && npm run check:module && npm run check:manifest
```

- [ ] **Step 9: Commit**

```bash
git add skills/l3io-util-doctor/scripts/migrate-engine.py \
        skills/l3io-util-doctor/scripts/tests/test-engine.py \
        skills/l3io-util-doctor/payload-manifest.json
git commit -s -m "feat(l3io-util): the gate, the write, and verification against the plan

The gate sits before the write, so an empty parse cannot reach disposal whatever
its cause. Verification compares the tree to the PLAN rather than to itself --
the old Stage E checked its own output, which is why an empty set passed. Dispose
renames to .legacy and never deletes. Every node goes through import-node, so a
migrated node is under the same lock, events and validation as any other write."
```

---

## Task 12: The two-half resolver guard

**Files:**
- Modify: `scripts/check-docs.mjs` — add `resolverInvariant()`, register it as check 26, add its header entry
- Modify: `scripts/tests/check-docs.test.mjs`

**Interfaces:**
- Consumes: nothing from earlier tasks — it reads the tree.
- Produces: `export function resolverInvariant(opts = {}) -> { violations: string[], scannedFiles: string[] }`, and check 26 in the `check:docs` run.

**The rule has two halves, and the second is the one that matters:**

1. Inside `skills/_shared/pm-status.py` — `epic-`/`sprint-` path assembly appears only between the resolver section's markers.
2. Across `skills/` — no file assembles a state path, with `skills/_shared/status-files.md` and its synced `references/status-files.md` copies exempt, because the canonical contract has to describe the layout.

**Scope is derived from the tree, never from a list of known offenders.** A guard scoped to `migrate-state.md` would pass over `bootstrap-state.md`'s six sites and report success — the same shape as the vacuous Stage E, one level up.

**This task lands RED on purpose.** Check 26 fails the moment it exists, naming the remaining sites in `migrate-state.md` and `bootstrap-state.md`. Tasks 13 and 14 remove them. The guard has to exist before the cleanup so the cleanup is measured against it rather than declared complete.

- [ ] **Step 1: Write the failing test**

Append to `scripts/tests/check-docs.test.mjs`:

```javascript
import { resolverInvariant } from '../check-docs.mjs'

test('check 26: scope is derived from the tree, not enumerated', () => {
  const { scannedFiles } = resolverInvariant()
  assert.ok(scannedFiles.length > 20,
    `expected the scan to reach the whole skills tree, saw ${scannedFiles.length}`)
  assert.ok(scannedFiles.some(f => f.includes('l3io-util-doctor')),
    'the doctor must be in scope')
  assert.ok(scannedFiles.some(f => f.includes('l3io-pm-execute')),
    'every skill must be in scope, not only the doctor')
})

test('check 26: a planted markdown violation is caught', () => {
  const { violations } = resolverInvariant({
    extraSources: [{
      file: 'skills/fake-skill/steps/planted.md',
      text: 'mkdir -p {pm_state_root}/{status_dir}/epic-{nnn}/',
    }],
  })
  assert.ok(violations.some(v => v.includes('planted.md')),
    `expected the planted violation to be caught, got: ${JSON.stringify(violations)}`)
})

test('check 26: the canonical contract is exempt', () => {
  const { violations } = resolverInvariant({
    extraSources: [{
      file: 'skills/_shared/status-files.md',
      text: 'state/{planned,active,archived}/epic-{nnn}/sprint-{nn}/',
    }],
  })
  assert.ok(!violations.some(v => v.includes('_shared/status-files.md')),
    'the canonical contract must not be reported')
})

test('check 26: a planted pm-status.py violation outside the resolver section is caught', () => {
  const { violations } = resolverInvariant({
    plantInPmStatus: { line: 4000, text: '    d = os.path.join(root, "epic-{nnn}")' },
  })
  assert.ok(violations.some(v => v.includes('pm-status.py:4000')),
    `expected the planted pm-status violation, got: ${JSON.stringify(violations)}`)
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `node --test scripts/tests/check-docs.test.mjs`
Expected: FAIL — `resolverInvariant is not exported`

- [ ] **Step 3: Implement `resolverInvariant()`**

Add to `scripts/check-docs.mjs`. Use the file's existing file-reading and skill-walking helpers rather than adding new ones — match whatever `allSkillDocs()` and its siblings already do.

```javascript
// ---------------------------------------------------------------------------
// 26. State paths are assembled ONLY in pm-status.py's resolver section.
//
// CLAUDE.md states pm-status.py "is the only place that resolves a key to a file
// location". Two doctor procedures were standing exceptions: bootstrap-state.md at SIX
// sites (with its own inline ruamel write_node, bypassing the epic write lock, the event
// log and status validation) and migrate-state.md at three. Both are now routed through
// `import-node`; this check is what keeps them routed.
//
// TWO HALVES, and the second is the load-bearing one:
//   (a) inside pm-status.py -- assembly appears only between the resolver section's
//       marker comments. The markers are matched by TEXT, not line number, so the bounds
//       survive edits above them.
//   (b) across skills/ -- no file assembles a state path at all.
//
// SCOPE IS DERIVED from the tree (every .md and .py under skills/), never enumerated. A
// guard scoped to the two known offenders would have passed over any third one and
// reported success -- the same shape as the vacuous Stage E gate it exists to prevent.
//
// EXEMPTIONS, derived rather than listed by hand: skills/_shared/status-files.md is the
// canonical state-layout contract and has to describe the layout; its synced
// references/status-files.md copies are the same bytes, so they are exempt by the same
// rule rather than by a second entry.
//
// KNOWN GAP: this matches literal `epic-`/`sprint-` assembly adjacent to a path separator
// or a state-root token. It does NOT catch a path built from a variable whose value is
// "epic-" assigned elsewhere. That is a FALSE-NEGATIVE direction, stated here rather than
// left for a reader to discover.
const RESOLVER_START_MARKER =
  'Sharded layout resolution — the ONLY place that knows where nodes live'
const RESOLVER_END_MARKER =
  'computed roll-ups — sprint/epic aggregates over per-story child files'

const STATE_PATH_RE =
  /(?:mkdir\s+-p\s+|["'`(]|\/)\s*\{?[\w.\-/{}]*\}?\/?(?:epic-\{?n{2,3}\}?|epic-\{int|sprint-\{?n{1,2}\}?)/

function isStatusFilesContract(file) {
  return file === 'skills/_shared/status-files.md' ||
    file.endsWith('/references/status-files.md')
}

export function resolverInvariant(opts = {}) {
  const violations = []
  const scannedFiles = []

  // (a) pm-status.py: assembly only inside the resolver section.
  const pmPath = 'skills/_shared/pm-status.py'
  const pmLines = readRepoFile(pmPath).split('\n')
  if (opts.plantInPmStatus) {
    pmLines.splice(opts.plantInPmStatus.line - 1, 0, opts.plantInPmStatus.text)
  }
  const start = pmLines.findIndex(l => l.includes(RESOLVER_START_MARKER))
  const end = pmLines.findIndex(l => l.includes(RESOLVER_END_MARKER))
  if (start < 0 || end < 0) {
    violations.push(`${pmPath}: resolver section markers not found — cannot judge scope`)
  } else {
    pmLines.forEach((line, i) => {
      const n = i + 1
      if (n > start + 1 && n < end + 1) return       // inside the resolver section
      if (line.trimStart().startsWith('#')) return   // a comment, not code
      if (STATE_PATH_RE.test(line)) {
        violations.push(
          `${pmPath}:${n} assembles a state path outside the resolver section: ${line.trim()}`)
      }
    })
  }

  // (b) skills/: nothing assembles a state path. Scope derived by walking the tree.
  const sources = [
    ...walkSkillFiles(['.md', '.py']).map(f => ({ file: f, text: readRepoFile(f) })),
    ...(opts.extraSources || []),
  ]
  for (const { file, text } of sources) {
    if (file === pmPath || file.endsWith('/scripts/pm-status.py')) continue
    scannedFiles.push(file)
    if (isStatusFilesContract(file)) continue
    text.split('\n').forEach((line, i) => {
      if (STATE_PATH_RE.test(line)) {
        violations.push(`${file}:${i + 1} assembles a state path: ${line.trim()}`)
      }
    })
  }

  return { violations, scannedFiles }
}
```

If `readRepoFile` and `walkSkillFiles` do not already exist under those names, use the file's existing equivalents — do not add new helpers. Confirm with:

```bash
grep -n 'function readFileSafe\|function allSkillDocs\|function walkSkill\|function readRepoFile' scripts/check-docs.mjs
```

- [ ] **Step 4: Register the check and add its header entry**

Register beside the other checks:

```javascript
  const { violations: resolverViolations } = resolverInvariant()
  report(26, 'resolver-invariant', resolverViolations)
```

Match `report()`'s real signature — confirm with `grep -n 'function report' scripts/check-docs.mjs`.

Add to the numbered list in the file's header comment:

```
//  26. State paths are assembled only in pm-status.py's resolver section — two halves
//      (inside pm-status.py; across all of skills/), scope derived from the tree, with
//      the canonical status-files.md contract exempt. See the block above
//      resolverInvariant() for the KNOWN GAP.
```

- [ ] **Step 5: Run the unit tests**

Run: `node --test scripts/tests/check-docs.test.mjs`
Expected: PASS, including both planted-violation cases.

- [ ] **Step 6: Run the gate against the real tree and record what it names**

```bash
npm run check:docs 2>&1 | tee /tmp/check26-before.txt
```
Expected: **FAIL**, naming sites in `assets/migrate-state.md` and `steps/bootstrap-state.md`.

Keep that output — Tasks 13 and 14 assert it narrows and then empties.

- [ ] **Step 7: Commit, with the red gate explained**

```bash
git add scripts/check-docs.mjs scripts/tests/check-docs.test.mjs
git commit -s -m "feat(infra): check 26 keeps state-path assembly in the resolver section

Two halves: inside pm-status.py, and across all of skills/. Scope is derived by
walking the tree, never enumerated -- a guard scoped to the two known offenders
would pass over a third and report success, the same shape as the vacuous Stage E
it prevents. The canonical status-files.md contract is the one exemption, matched
by rule rather than listed.

check:docs FAILS at this commit, naming the remaining sites in migrate-state.md
and bootstrap-state.md. That is deliberate: the guard exists before the cleanup so
the cleanup is measured against it. Tasks 13 and 14 remove those sites."
```

---

## Task 13: Rewrite `migrate-state.md` around the engine

**Files:**
- Rewrite: `skills/l3io-util-doctor/assets/migrate-state.md` (817 lines → roughly 150)
- Modify: `skills/l3io-util-doctor/steps/migrate-state.md` if its forwarder names removed stages

**Interfaces:**
- Consumes: `migrate-engine.py`'s `--plan` and `--apply` CLI (Tasks 10-11); `detect-layout.py --classify` (Task 1).
- Produces: prose that detects, explains, confirms and interprets — and assembles no paths.

**What prose keeps and what it loses.** Keeps: resolving config, explaining what was found, showing the plan, taking the confirmation, interpreting a BLOCK, reporting. Loses: every `mkdir`, every `write …` directive, every `rm -f`, and both list-joining sites.

- [ ] **Step 1: Record what the old file did, before replacing it**

```bash
grep -n 'mkdir -p\|^write \|rm -f' skills/l3io-util-doctor/assets/migrate-state.md \
  | tee /tmp/migrate-state-old-sites.txt
wc -l skills/l3io-util-doctor/assets/migrate-state.md
```

- [ ] **Step 2: Replace the file**

Replace the entire contents of `skills/l3io-util-doctor/assets/migrate-state.md` with:

````markdown
## Migrate State Mode

Invoked with `migrate-state`. Upgrades any earlier state layout to the current sharded
tree under `{implementation_artifacts}/state/`.

**The parsing and writing are not done here.** `scripts/migrate-engine.py` owns them and
`scripts/tests/test-engine.py` covers them. This file owns what a script cannot: deciding
what to tell the user, taking the confirmation, and interpreting a refusal.

Six hand-written procedures used to live here, none reachable by a test. One deleted a
live BMad tracking file while reporting success, because its completeness checks ran
*after* the write and passed vacuously over an empty set. The engine's gate now sits
before the write, so that cannot happen for this cause or any other.

### Step MS1 — Resolve config

Resolve `{implementation_artifacts}` and `{project-root}` exactly as every other mode does
(`references/config-resolution.md`). Bind:

- `{pm_state_root}` = `{implementation_artifacts}/state`
- `{pm_status}` = `{project-root}/_bmad/scripts/pm-status.py`
- `{engine}` = `{skill-root}/scripts/migrate-engine.py`

### Step MS2 — Show the plan

```bash
uv run {engine} --artifacts {implementation_artifacts} --project-root {project-root} --plan
```

Read-only. Prints the detected layout, the node counts, and how many nodes would be
marked `origin: inferred`.

If it prints `No migratable source layout found`, report that and stop. That is a normal
outcome, not a failure.

### Step MS3 — Explain what was detected

Tell the user in one short paragraph which layout was found and what it means. One case
needs more than a sentence:

**If the layout is `bmad-flat`**, say plainly that this project is tracked by base BMad's
own `sprint-status.yaml`; that `bmad-sprint-planning`, `bmad-build` and
`bmad-retrospective` all read it; and that the migration renames it to `.legacy` rather
than deleting it — so those skills will stop finding it. Ask whether to proceed. This is a
real change to how their project is tracked, and it is the one decision here that is not
mechanical.

### Step MS4 — Confirm

Ask: "Proceed with the migration? The source will be renamed to `.legacy`, never deleted."

If no: print `Migration cancelled — no changes made.` and stop.

### Step MS5 — Apply

```bash
uv run {engine} --artifacts {implementation_artifacts} --project-root {project-root} \
  --apply --state-root {pm_state_root} --pm-status {pm_status} --dispose
```

The engine gates, writes every node through `{pm_status} import-node`, verifies the result
against the plan, and only then renames the source aside.

### Step MS6 — Interpret the outcome

**Exit 0** — report the counts it printed and point at `stats`:

```
DONE — migrated {n} node(s) to {pm_state_root}.
  The previous source is preserved as *.legacy.
  Run `/l3io-util-doctor stats` to see the result.
```

**Exit 1 with `BLOCKED:`** — the gate refused. Nothing was written and the source is
untouched. Relay the engine's message verbatim; do not paraphrase it and do not retry. The
most common cause is named in the message: a flat `sprint-status.yaml` holding BMad's
`development_status:` mapping. Confirm with:

```bash
uv run {skill-root}/scripts/detect-layout.py --artifacts {implementation_artifacts} --classify
```

**Exit 1 with `FAILED`** — the write or the verification failed. Nothing was disposed of
and the source is intact. Relay the errors. The state tree may hold partially written
nodes; they are valid nodes, and re-running is safe because `import-node` skips what
already exists.

### Step MS7 — Calibration and anomalies

If `{project-root}/_bmad/pm-calibration.yaml` exists, move it to
`{pm_state_root}/pm-calibration.yaml` with `git mv`. It is the only file that moves rather
than being rewritten.

Record anything the user should know about as a backlog item:

```bash
uv run {pm_status} append-issue --state-root {pm_state_root} --epic {epic_key} \
  --severity Low --source migrate-state --description "{what was odd}"
```

---
````

- [ ] **Step 3: Update the forwarder if it names removed stages**

```bash
cat skills/l3io-util-doctor/steps/migrate-state.md
```

If it names Stages A-F, rewrite it to name Steps MS1-MS7. If it only points at
`assets/migrate-state.md`, leave it unchanged.

- [ ] **Step 4: Verify every old site is gone**

```bash
grep -n 'mkdir -p\|^write \|rm -f' skills/l3io-util-doctor/assets/migrate-state.md
```
Expected: no output.

- [ ] **Step 5: Confirm check 26 has narrowed**

```bash
npm run check:docs 2>&1 | tee /tmp/check26-after-13.txt
```
Expected: still FAILS, but naming **only** `bootstrap-state.md` sites. If any
`migrate-state.md` line is still named, it was missed — fix it before committing.

- [ ] **Step 6: Run the other gates**

```bash
npm run check:manifest -- --write
npm run check:scripts && npm run check:module && npm run check:version && npm run check:manifest
```

- [ ] **Step 7: Commit**

```bash
git add skills/l3io-util-doctor/assets/migrate-state.md \
        skills/l3io-util-doctor/steps/migrate-state.md \
        skills/l3io-util-doctor/payload-manifest.json
git commit -s -m "refactor(l3io-util): migrate-state is prose around the engine

817 lines of untested procedure become detect, explain, confirm and interpret.
Every mkdir, every write directive, every rm -f and both list-joining sites are
gone; the engine owns them and its suite covers them. The bmad-flat case gets the
one explanation that is not mechanical: this is the file base BMad's own skills
read, and it is renamed rather than deleted.

check 26 still fails, now naming only bootstrap-state.md. Task 14 closes it."
```

---

## Task 14: Rewrite `bootstrap-state.md` around the engine

**Files:**
- Rewrite: `skills/l3io-util-doctor/steps/bootstrap-state.md`

**Interfaces:**
- Consumes: `migrate-engine.py`'s `--plan`/`--apply` with the `artifacts` layout, served by Task 9's reader.
- Produces: prose with no inline `write_node()` and no assembled paths.

**This is the task that turns check 26 green.** `bootstrap-state.md` carries six of the eight sites and the inline `ruamel` writer that bypasses the epic write lock, the event log and status validation.

- [ ] **Step 1: Record the old sites**

```bash
grep -n 'mkdir -p\|pm_state_root}/{status_dir}\|write_node\|ruamel' \
  skills/l3io-util-doctor/steps/bootstrap-state.md | tee /tmp/bootstrap-old-sites.txt
```

- [ ] **Step 2: Replace the file**

Replace the entire contents of `skills/l3io-util-doctor/steps/bootstrap-state.md` with:

````markdown
## Bootstrap State Mode

Invoked with `bootstrap-state`. Creates state nodes for a project that has story
artifacts but no state tree — typically a project adopting l3io-pm after writing stories
by hand.

**This mode used to write nodes itself**, through an inline `write_node()` calling
`ruamel` directly and assembling state paths at six sites. That bypassed the epic write
lock, the event log and status validation, and nothing tested it. It now runs the same
engine every other migration runs; `scripts/read-artifacts.py` is the reader that serves
it and `scripts/tests/test-read-artifacts.py` covers it.

### Step BS1 — Resolve config

Resolve `{implementation_artifacts}` and `{project-root}` as every other mode does
(`references/config-resolution.md`). Bind:

- `{pm_state_root}` = `{implementation_artifacts}/state`
- `{pm_status}` = `{project-root}/_bmad/scripts/pm-status.py`
- `{engine}` = `{skill-root}/scripts/migrate-engine.py`

### Step BS2 — Show what would be created

```bash
uv run {engine} --artifacts {implementation_artifacts} --project-root {project-root} --plan
```

Read-only. If the detected layout is not `artifacts`, this project already has a status
file — stop and tell the user to run `migrate-state` instead, which handles that source.

If it reports `No migratable source layout found`, there are no story files under
`{implementation_artifacts}/epic-XX/sprint-YY/stories/`. Say so and stop.

### Step BS3 — Explain the inference

The plan reports how many nodes would be `origin: inferred`. Tell the user what that
means, because it is the one thing here they might want to change:

> Your story files carry their own status. Sprints and epics do not exist in this project
> yet, so they are reconstructed from the directory structure your stories sit in, and each
> reconstructed node is marked `origin: inferred` with a note saying so. A sprint is `done`
> when every story in it is done, `backlog` when none has started, and `in-progress`
> otherwise. The same rule gives each epic its status.

If the user wants different sprint boundaries, they change the directory structure and
re-run — the reader follows the tree, so the tree is the control.

### Step BS4 — Confirm

Ask: "Create these state nodes? Existing nodes will be left exactly as they are."

If no: print `Bootstrap cancelled — no changes made.` and stop.

### Step BS5 — Apply

```bash
uv run {engine} --artifacts {implementation_artifacts} --project-root {project-root} \
  --apply --state-root {pm_state_root} --pm-status {pm_status}
```

No `--dispose`: there is no source to retire. The story `.md` files stay exactly where
they are — they are artifacts, and artifacts are never moved.

Every node is written through `{pm_status} import-node`, so each lands under the epic
write lock with an event recorded and its status validated. A node that already exists is
skipped, never overwritten, so re-running after a partial run is safe.

### Step BS6 — Report

**Exit 0:**

```
DONE — created {n} state node(s) under {pm_state_root}.
  {i} node(s) marked origin: inferred.
  Run `/l3io-util-doctor stats` to see the result.
```

**Exit 1 with `BLOCKED:`** — relay the engine's message verbatim. Nothing was written.

**Exit 1 with `FAILED`** — relay the errors. Nodes already written are valid, and
re-running is safe.

### Step BS7 — What bootstrap does not fill in

Epics created this way carry an empty `title` and `goal`, because nothing in a story
artifact states them. Tell the user they can set them directly:

```bash
uv run {pm_status} set-field --state-root {pm_state_root} --epic {epic_key} \
  --field title --value "{the epic's title}"
```

Estimates and actuals are **not** created. A bootstrapped node has no `estimate` block,
and that is correct: an estimate nobody made is a number calibration would learn from.

---
````

- [ ] **Step 3: Verify the old sites are gone**

```bash
grep -n 'mkdir -p\|pm_state_root}/{status_dir}\|write_node\|ruamel' \
  skills/l3io-util-doctor/steps/bootstrap-state.md
```
Expected: no output.

- [ ] **Step 4: Check 26 must now be GREEN**

Run: `npm run check:docs`
Expected: **PASS**. Check 26 reports no violations.

If it still names a site, that site is real — fix it rather than exempting it.

- [ ] **Step 5: Run every gate and every suite**

```bash
npm run check:manifest -- --write
npm run check:docs && npm run check:scripts && npm run check:module && \
  npm run check:version && npm run check:manifest && npm run test:scripts
uv run skills/_shared/tests/test-pm-status.py
for t in state-record detect-layout read-l3io-flat read-bmad-flat read-per-epic \
         read-split read-artifacts engine; do
  uv run skills/l3io-util-doctor/scripts/tests/test-$t.py || echo "FAILED: $t"
done
```
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add skills/l3io-util-doctor/steps/bootstrap-state.md \
        skills/l3io-util-doctor/payload-manifest.json
git commit -s -m "refactor(l3io-util): bootstrap-state is prose around the engine

Removes the inline write_node() and all six state-path assembly sites -- the
larger of the two standing exceptions to the resolver invariant. Nodes now go
through import-node, so each is under the epic write lock with an event recorded
and its status validated.

check 26 is green as of this commit."
```

---

## Task 15: Documentation and the shipped surface

**Files:**
- Modify: `CLAUDE.md` — the `pm-status.py` verb paragraph and the `l3io-util-doctor` Module Layout note
- Modify: `skills/l3io-util-doctor/SKILL.md` — the `migrate-state` and `bootstrap-state` routing rows
- Modify: `docs/l3io-util-reference.md` — the doctor's documented surface

**Interfaces:**
- Consumes: everything above. Produces: documentation that states what is now true. No new code.

- [ ] **Step 1: Update `CLAUDE.md`'s verb list**

Find the sentence beginning "Three subcommands beyond the status/actuals core". Change
"Three" to "Four" and append after the `adr-reserve` clause:

```
**`import-node`** creates a node that does not exist yet, from a migration record — it is
`cmd_set_status` with `ensure_node_path` where that verb calls `_load_checked`, so a
migrated node lands under the same epic write lock, event log and status validation as any
other write. It is idempotent by skip, never by overwrite. `set-status` is unchanged and
still exits 3 on a missing node.
```

- [ ] **Step 2: Update `CLAUDE.md`'s Module Layout note**

Append to the `l3io-util-doctor` paragraph:

```
Its migrations are not prose: `scripts/migrate-engine.py` runs detect → read → resolve →
plan → gate → write → verify → dispose, with five readers beside it (one per source
layout) and `pm-status.py import-node` as the only writer. The gate sits before the write
because the previous prose ran its completeness checks after it, so an empty parse passed
vacuously and then deleted the source. Check 26 keeps state-path assembly inside
`pm-status.py`'s resolver section.
```

- [ ] **Step 3: Update the doctor's `SKILL.md` rows**

For `migrate-state` and `bootstrap-state`, make the description name the engine rather
than the stages. **Keep the keyword and the file pointer exactly as they are** — check 4
and `check:module` both judge those.

- [ ] **Step 4: Confirm `module-help.csv` needs no change**

```bash
grep -n 'migrate\|bootstrap' skills/l3io-util-doctor/assets/module-help.csv
```

Neither mode currently has a row — only `DR`, `DS` and `DD` do. If that is still true,
this file needs no change. Do not add rows the menu did not previously carry.

- [ ] **Step 5: Update the user-facing reference**

In `docs/l3io-util-reference.md`, find the `migrate-state` and `bootstrap-state` sections
and state the three behaviour changes a user would notice:

- the source is renamed to `.legacy`, never deleted
- a migration that would move nothing is refused rather than run
- bootstrapped sprints and epics are marked `origin: inferred`

- [ ] **Step 6: Run every gate and every suite**

```bash
npm run check:manifest -- --write
npm run check:docs && npm run check:scripts && npm run check:module && \
  npm run check:version && npm run check:manifest && npm run test:scripts
uv run skills/_shared/tests/test-pm-status.py
for t in state-record detect-layout read-l3io-flat read-bmad-flat read-per-epic \
         read-split read-artifacts engine; do
  uv run skills/l3io-util-doctor/scripts/tests/test-$t.py || echo "FAILED: $t"
done
```
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add CLAUDE.md skills/l3io-util-doctor/SKILL.md docs/l3io-util-reference.md \
        skills/l3io-util-doctor/payload-manifest.json
git commit -s -m "docs: the doctor's migrations are an engine, not prose

Records import-node as the fourth verb beyond the status/actuals core, the
engine's eight steps, and the three changes a user would notice: the source is
renamed rather than deleted, a migration that would move nothing is refused, and
inferred nodes say so."
```

---

## Self-Review

**1. Spec coverage** — every section of the spec maps to a task:

| Spec § | Task |
|---|---|
| §2 three tiers | 13, 14 — the tiers are a routing and confirmation property, stated in prose; no code change |
| §2 detect **and** convert base BMad | 1 (discriminate), 6 (reader), 10 (detect), 11 (`test_cli_apply_on_a_bmad_project_migrates_it_rather_than_blocking`) |
| §2 infer sprints | 9 |
| §2 mark inferred nodes, no version bump | 2 (`origin` omitted when absent), 4, 9 |
| §2 PASS / FAIL / UNABLE | 11 — the gate is the UNABLE outcome made structural |
| §3 five readers, one writer, prose for judgement | 5-9, 4, 13-14 |
| §3 layout detection has one home | 1, 10 |
| §4 do not split `pm-status.py` | honoured — no task splits it |
| §4 the two-half guard | 12 |
| §5 `import-node`, exactly one new resolver function | 3, 4 |
| §6 the normalised record | 2 |
| §6 the eight-step run | 10, 11 |
| §7 fixtures per layout; the four named tests | 5-11 |
| §8 gaps 1, 2, 5, 9 | 1, 11, 2, 9 |

The four named tests from spec §7, each with a home and each proven non-vacuous:
- **empty-plan gate BLOCKs** — Task 11 Step 1, mutation-checked at Task 11 Step 7
- **verification compares against the plan** — Task 11, `test_verify_catches_a_node_corrupted_on_disk`
- **the source survives a failed run** — Task 11, `test_the_source_survives_a_blocked_run`
- **removing a fixture fails rather than passes** — Task 10, `test_every_fixture_directory_has_a_reader`, mutation-checked at Task 10 Step 5

**2. Placeholder scan** — no `TBD`, no "add appropriate error handling", no "similar to Task N". Every code step carries its code.

**3. Type consistency** — checked across tasks:
- `read(path)` for file readers (5, 6); `read(dir)` for directory readers (7, 8, 9). Task 10's `READERS` lambdas absorb the difference so the engine sees one shape.
- `make_record(kind, key, status, title, source, origin=None, origin_note=None)` — identical call shape in 5, 6, 7, 9.
- `ensure_node_path(state_root, args, kind, status)` — defined in 3, called in 4 with that exact arity.
- `_epic_write_lock(args, kind, require_exists=True)` — parameter added in 3, used in 4.
- Sprint keys are `E001-S01` everywhere; `_node_argv()` and `_node_relpath()` in Task 11 are the only two places that split them, and both split on `-S`.
- `sr.VALID_STATUS` is defined in Task 2 and consumed by name in Task 9.

**Three things found and fixed while reviewing:**

1. **Task 12 lands red, and a reviewer would have rejected it.** Check 26 fails the moment it exists and stays red until Task 14. That ordering is deliberate — the guard must exist before the cleanup so the cleanup is measured rather than declared — but it needed saying. Task 12's Steps 6-7 now state it, and Tasks 13 and 14 each assert the expected narrowing.

2. **Two mutation checks were missing.** A test that passes without exercising its branch is the exact failure this design is organised against, so the two load-bearing tests now have explicit "prove it fails" steps: Task 10 Step 5 (rename a fixture) and Task 11 Step 7 (neuter the gate).

3. **Task 6's "no sprint records" needed explaining, not just stating.** BMad's schema has no sprint concept, so the reader emits none; the sprint node is created from the story's own path by `ensure_node_path`. Without that sentence, Task 10's `test_bmad_flat_plan_counts` asserting `sprint: 0` reads like a bug.
