# Sharded State Layout: Relocation and Per-Story Sharding Implementation Plan

> **Release: 2.0.1 (patch).** The state-layout generations were originally labeled v1/v2/v3
> during design, but those labels read as product/release versions rather than layout
> generations — so they were replaced with descriptive names: the *legacy flat* layout
> (flat `sprint-status.yaml`) → the *legacy per-epic* layout (`_bmad/state/`) → the
> *sharded* layout (current). 2.0.0 is one day old and activation hard-blocks on older
> layouts with a migrate instruction, so this ships as a patch fixing that release.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move l3io-pm state out of the gitignored `_bmad/state/` into a committed, per-story-sharded tree at `{implementation_artifacts}/state/` that mirrors the artifact tree.

**Architecture:** `pm-status.py` gains a layout module that resolves node keys to file paths, so skills pass keys instead of paths and layout knowledge lives in exactly one place. State shards to one file per story, with epic directories moving between `planned/`, `active/`, and `archived/` folders via `git mv`. Nested `sprints:`/`stories:` lists are replaced by directory structure.

**Tech Stack:** Python 3.11+, `ruamel.yaml>=0.18` (round-trip YAML), `unittest`, Node.js (sync tooling), Markdown skill files.

**Spec:** `docs/superpowers/specs/2026-08-16-v3-state-relocation-design.md`

## Global Constraints

- **Never edit per-skill copies** of shared files. Author in `skills/_shared/`, then run `npm run sync:scripts`. CI runs `npm run check:scripts` and fails on drift.
- **Canonical shared sources:** `skills/_shared/pm-status.py`, `skills/_shared/tests/test-pm-status.py`, `skills/_shared/status-files.md`, `skills/_shared/steps/**`.
- **Commits:** Conventional Commits, DCO sign-off required (`git commit -s`). Breaking changes use `feat!`. Valid types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `revert`, `WIP`. Scopes: `l3io-pm`, `l3io-sec`, `l3io-util`, `l3io-arch`, `infra`, `ci-cd`.
- **Run tests with:** `python3 skills/_shared/tests/test-pm-status.py` (this is exactly what CI runs in `.github/workflows/checks.yml`).
- **No external organization references** in code, comments, commit messages, or generated files.
- **Zero-padding is fixed:** epic dirs `epic-{nnn}` (3 digits), sprint dirs `sprint-{nn}` (2 digits), epic keys `E{nnn}`, sprint keys `S{nn}`, story keys `E{nnn}-S{nn}-{nnn}`, backlog keys `BL-E{nnn}-{nnn}`.
- **Metric fields are fixed:** actuals use `elapsed_hours`, `man_hours`, `tokens_k`, `cost` (all four required). Story estimates use single values (`man_hours`, `time_hours`, `tokens_k`, `cost`); sprint/epic estimates use ranges (`man_hours_low/high`, `time_hours_low/high`, `tokens_k_min/max`, `cost_low/high`). Both carry `confidence`.
- **Under `--runtime claude`**, `tokens_k` and `cost` must never be `N/A` — this is enforced at write time and must be preserved.
- **Status vocabularies:** story `backlog|ready-for-dev|in-progress|review|done`; sprint and epic `backlog|in-progress|done`.
- **Exit codes are contractual:** 0 success, 2 usage error, 3 node not found, 4 verification failure, 5 epic locked. Do not renumber.

---

## File Structure

**Modified — canonical shared sources:**

| File | Responsibility after this plan |
|---|---|
| `skills/_shared/pm-status.py` | Adds a layout resolution layer (key → path), bare-node I/O, computed roll-ups, `show`, directory-move epic transitions. Internal version → 2.0.1. |
| `skills/_shared/tests/test-pm-status.py` | Adds tree-fixture helpers and coverage for layout resolution, roll-ups, moves, and back-reference validation. |
| `skills/_shared/status-files.md` | Rewritten as the sharded layout contract, including the two-tree distinction. |
| `skills/_shared/steps/shared/step-00-activate.md` | Three-way detection, ambiguity block, orphan check, new bindings. |
| `skills/_shared/steps/**` (others) | Inline state paths replaced with key-based `pm-status.py` calls. |

**Modified — skill-local:**

| File | Responsibility |
|---|---|
| `skills/l3io-util-cleanup/assets/migrate-state.md` | legacy-flat→sharded and legacy-per-epic→sharded migration. |
| `skills/l3io-util-cleanup/SKILL.md` | Drift check added to health scan; `sort-status` reduced. |
| `skills/*/assets/module-setup.md` (7 skills) | Gitignore verification gate. |
| `CLAUDE.md` | Sharded state layout, calibration commit status. |
| `docs/superpowers/specs/2026-08-14-v2-migration-design.md`, `docs/superpowers/plans/2026-08-14-v2-migration.md` | Superseding notes only — content preserved as historical record. |

**Not modified:** `_bmad/sync-mapping.yaml` handling, `pm-status.py self-install --dest` target (`_bmad/scripts/`), `skills/_shared/resolve_config.py`, `skills/_shared/memlog.py`.

---

## Task 1: Layout resolution and bare-node I/O

Adds the layer that turns a node key into a file path. Pure functions, no CLI changes — every later task builds on this.

**Files:**
- Modify: `skills/_shared/pm-status.py` (add after `_pad`, around line 148)
- Test: `skills/_shared/tests/test-pm-status.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces:
  - `STATUS_DIRS = ("active", "planned", "archived")`
  - `epic_dirname(epic_key: str) -> str` — `'E001'` → `'epic-001'`
  - `sprint_dirname(sprint_key: str) -> str` — `'S01'` → `'sprint-01'`
  - `parse_story_key(key: str) -> tuple[str, str, str]` — `'E001-S01-003'` → `('E001', 'S01', '003')`
  - `find_epic_dir(state_root: str, epic_key: str) -> str | None` — absolute path or None
  - `epic_file(state_root, epic_key) -> str | None`
  - `sprint_file(state_root, epic_key, sprint_key) -> str | None`
  - `story_file(state_root, story_key) -> str | None`
  - `load_node(path) -> tuple[YAML, CommentedMap | None]`
  - `save_node(y, node, path, use_flock=False) -> None`
  - `check_backrefs(node, epic_key, sprint_key=None) -> list[str]` — returns mismatch descriptions, empty when consistent

- [ ] **Step 1: Write the failing tests**

Append to `skills/_shared/tests/test-pm-status.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 skills/_shared/tests/test-pm-status.py TestLayoutResolution -v`
Expected: FAIL with `AttributeError: module 'pm_status' has no attribute 'epic_dirname'`

- [ ] **Step 3: Implement the layout layer**

Insert into `skills/_shared/pm-status.py` immediately after the `_pad` function:

```python
# --------------------------------------------------------------------------- #
# Sharded layout resolution — the ONLY place that knows where nodes live on disk
# --------------------------------------------------------------------------- #
STATUS_DIRS = ("active", "planned", "archived")  # active first: hottest path


def epic_dirname(epic_key: str) -> str:
    """'E001' -> 'epic-001'. Accepts unpadded input ('E42' -> 'epic-042')."""
    n = str(epic_key).strip().lstrip("Ee")
    if not n.isdigit():
        raise ValueError(f"bad epic key: {epic_key!r}")
    return f"epic-{int(n):03d}"


def sprint_dirname(sprint_key: str) -> str:
    """'S01' -> 'sprint-01'. Accepts unpadded input ('S7' -> 'sprint-07')."""
    n = str(sprint_key).strip().lstrip("Ss")
    if not n.isdigit():
        raise ValueError(f"bad sprint key: {sprint_key!r}")
    return f"sprint-{int(n):02d}"


def parse_story_key(key: str) -> tuple:
    """'E001-S01-003' -> ('E001', 'S01', '003')."""
    parts = str(key).strip().split("-")
    if len(parts) != 3 or not parts[0].startswith("E") or not parts[1].startswith("S"):
        raise ValueError(f"bad story key: {key!r} (expected E{{nnn}}-S{{nn}}-{{nnn}})")
    return parts[0], parts[1], parts[2]


def find_epic_dir(state_root: str, epic_key: str):
    """Absolute path to the epic's directory, whichever status folder holds it."""
    name = epic_dirname(epic_key)
    for status in STATUS_DIRS:
        p = os.path.join(state_root, status, name)
        if os.path.isdir(p):
            return p
    return None


def epic_file(state_root: str, epic_key: str):
    d = find_epic_dir(state_root, epic_key)
    if d is None:
        return None
    p = os.path.join(d, "epic.yaml")
    return p if os.path.exists(p) else None


def sprint_file(state_root: str, epic_key: str, sprint_key: str):
    d = find_epic_dir(state_root, epic_key)
    if d is None:
        return None
    p = os.path.join(d, sprint_dirname(sprint_key), "sprint.yaml")
    return p if os.path.exists(p) else None


def story_file(state_root: str, story_key: str):
    epic_key, sprint_key, _ = parse_story_key(story_key)
    d = find_epic_dir(state_root, epic_key)
    if d is None:
        return None
    p = os.path.join(d, sprint_dirname(sprint_key), f"{story_key}.yaml")
    return p if os.path.exists(p) else None


def load_node(path: str):
    """Load a bare node file (no `epics:` wrapper). Returns (yaml, node|None)."""
    return _load(path)


def save_node(y, node, path: str, use_flock: bool = False) -> None:
    _flock_write_or_plain(use_flock, y, node, path)


def check_backrefs(node, epic_key: str, sprint_key: str = None) -> list:
    """Compare a node's parent back-references against its resolved location."""
    problems = []
    if node is None:
        return ["node is empty"]
    got_epic = str(node.get("epic", "")).strip()
    if got_epic and got_epic != str(epic_key).strip():
        problems.append(f"epic back-reference {got_epic!r} != path epic {epic_key!r}")
    if sprint_key is not None:
        got_sprint = str(node.get("sprint", "")).strip()
        if got_sprint and got_sprint != str(sprint_key).strip():
            problems.append(f"sprint back-reference {got_sprint!r} != path sprint {sprint_key!r}")
    return problems
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 skills/_shared/tests/test-pm-status.py TestLayoutResolution -v`
Expected: PASS, 8 tests

- [ ] **Step 5: Run the full suite for regressions**

Run: `python3 skills/_shared/tests/test-pm-status.py`
Expected: PASS — Task 1 adds only new functions, so all pre-existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add skills/_shared/pm-status.py skills/_shared/tests/test-pm-status.py
git commit -s -m "feat(l3io-pm): add sharded layout resolution and bare-node I/O to pm-status.py

Key-to-path resolution across planned/active/archived, bare-node load
and save, and parent back-reference validation. No CLI changes yet."
```

---

## Task 2: Key-based addressing for node subcommands

Switches `set-status`, `set-actual`, `set-estimate`, `set-field`, and `verify` from `--file` to `--state-root` plus keys.

**Files:**
- Modify: `skills/_shared/pm-status.py` (`_resolve_node`, the five `cmd_*` functions, `build_parser`)
- Test: `skills/_shared/tests/test-pm-status.py`

**Interfaces:**
- Consumes: `story_file`, `sprint_file`, `epic_file`, `load_node`, `save_node`, `check_backrefs` (Task 1)
- Produces:
  - `resolve_node_path(state_root, args, kind) -> tuple[str, str]` — `(path, label)`; exits 3 if unresolvable
  - CLI: `--state-root` replaces `--file` on the five subcommands above

- [ ] **Step 1: Write the failing tests**

Append to `skills/_shared/tests/test-pm-status.py`:

```python
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
             "--elapsed-hours", "1.8", "--man-hours", "7", "--tokens-k", "355", "--cost", "5.32"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(node["actual"]["tokens_k"], 355)
        self.assertEqual(node["actual"]["man_hours"], 7)

    def test_claude_runtime_still_rejects_na(self):
        code, _ = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "story", "--story", "E001-S01-003",
             "--tokens-k", "N/A", "--runtime", "claude"])
        self.assertEqual(code, 2)

    def test_set_estimate_story_uses_single_values(self):
        code, out = self.run_main(
            ["set-estimate", "--state-root", self.root, "--story", "E001-S01-003",
             "--man-hours", "6", "--time-hours", "1.5", "--tokens-k", "320", "--cost", "4.80"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(node["estimate"]["man_hours"], 6.0)
        self.assertNotIn("man_hours_low", node["estimate"])

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 skills/_shared/tests/test-pm-status.py TestKeyBasedAddressing -v`
Expected: FAIL — `--state-root` is an unrecognized argument (exit 2 from argparse).

- [ ] **Step 3: Replace `_resolve_node` with path-based resolution**

In `skills/_shared/pm-status.py`, replace `_resolve_node` (currently lines 180-193) with:

```python
def resolve_node_path(state_root: str, args, kind: str):
    """Resolve a node kind + keys to (path, label). Exits 3 when the node is absent."""
    if kind == "story":
        if not args.story:
            _die_usage("--story is required for a story node")
        p = story_file(state_root, args.story)
        label = f"story {args.story}"
    elif kind == "sprint":
        if not (args.epic and args.sprint):
            _die_usage("--epic and --sprint are required for a sprint node")
        p = sprint_file(state_root, args.epic, args.sprint)
        label = f"epic {args.epic} sprint {args.sprint}"
    elif kind == "epic":
        if not args.epic:
            _die_usage("--epic is required for an epic node")
        p = epic_file(state_root, args.epic)
        label = f"epic {args.epic}"
    else:
        _die_usage(f"unknown node kind: {kind}")
    if p is None:
        _die_notfound(label)
    return p, label


def _load_checked(state_root: str, args, kind: str):
    """Resolve, load, and validate back-references. Exits 3 (missing) or 4 (misplaced)."""
    path, label = resolve_node_path(state_root, args, kind)
    y, node = load_node(path)
    if node is None:
        _die_notfound(f"{label} — file {path} is empty")
    if kind == "story":
        ek, sk, _ = parse_story_key(args.story)
        problems = check_backrefs(node, ek, sk)
    elif kind == "sprint":
        problems = check_backrefs(node, args.epic)
    else:
        problems = []
    if problems:
        sys.stderr.write(f"pm-status.py: back-reference mismatch for {label}: {'; '.join(problems)}\n")
        sys.exit(4)
    return y, node, path, label
```

- [ ] **Step 4: Update the five command functions**

Replace the opening of `cmd_set_status` (its `_load` / `_resolve_node` block) with:

```python
def cmd_set_status(args) -> int:
    kind = _infer_kind(args)
    valid = {"story": VALID_STORY_STATUS, "sprint": VALID_SPRINT_STATUS, "epic": VALID_EPIC_STATUS}[kind]
    if args.status not in valid:
        _die_usage(f"invalid {kind} status '{args.status}' — expected one of {sorted(valid)}")

    y, node, path, label = _load_checked(args.state_root, args, kind)
    node["status"] = args.status
    node["updated_at"] = _now_iso()
    if args.title:
        node["title"] = args.title
    save_node(y, node, path, getattr(args, "flock", False))

    if args.ledger:
        scope = args.scope or (args.story or f"{args.epic}" + (f"/{args.sprint}" if args.sprint else ""))
        _append_ledger(args.ledger, scope, f"status -> {args.status}")
    sys.stdout.write(f"OK set-status {label} -> {args.status}\n")
    return 0
```

Apply the same substitution in `cmd_set_actual`, `cmd_set_estimate`, `cmd_set_field`, and `cmd_verify`: replace their `y, data = _load(args.file)` / `_resolve_node(data, args, kind)` / `_flock_write_or_plain(..., args.file)` triple with `_load_checked(args.state_root, args, kind)` and `save_node(y, node, path, ...)`. The node-mutation logic in each is unchanged — `node` is now the bare mapping rather than a member of a nested list.

`cmd_verify` needs one extra change beyond the substitution. Its `--scope` currently accepts only `{story,sprint}`, but Task 7's activation step calls it with `--scope epic`. Widen the choices:

```python
    v.add_argument("--scope", required=True, choices=["story", "sprint", "epic"])
```

and add the `epic` branch to `cmd_verify`, which validates the epic node's own required fields and then walks every sprint and story file under the epic directory, accumulating failures:

```python
    if args.scope == "epic":
        failures = []
        for sd in list_sprint_dirs(args.state_root, args.epic):
            skey = "S" + os.path.basename(sd).split("-")[1]
            sp = sprint_file(args.state_root, args.epic, skey)
            if sp is None:
                failures.append(f"{skey}: sprint.yaml missing")
                continue
            _, snode = load_node(sp)
            failures += [f"{skey}: {p}" for p in check_backrefs(snode, args.epic)]
            for stf in list_story_files(args.state_root, args.epic, skey):
                _, stnode = load_node(stf)
                if stnode is None:
                    failures.append(f"{os.path.basename(stf)}: empty")
                    continue
                failures += [f"{stnode.get('key', '?')}: {p}"
                             for p in check_backrefs(stnode, args.epic, skey)]
        if failures:
            for f in failures:
                sys.stderr.write(f"FAIL {f}\n")
            return 4
        sys.stdout.write(f"PASS epic {args.epic}\n")
        return 0
```

Note this branch depends on `list_sprint_dirs` and `list_story_files`, which Task 4 introduces. Implement the `epic` scope branch in Task 4 rather than here if working strictly in order; the `--scope` choices widening belongs here so the flag exists when Task 7 references it.

- [ ] **Step 5: Swap the CLI arguments**

In `build_parser`, for `set-status`, `set-actual`, `set-estimate`, `set-field`, and `verify`, replace each `X.add_argument("--file", required=True)` with:

```python
    X.add_argument("--state-root", required=True,
                   help="path to {implementation_artifacts}/state")
```

Update the module docstring's Subcommands block (lines 29-45) to show `--state-root S` in place of `--file F` for these five.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 skills/_shared/tests/test-pm-status.py TestKeyBasedAddressing -v`
Expected: PASS, 9 tests

- [ ] **Step 7: Delete obsolete legacy-per-epic tests and run the full suite**

The pre-existing `TestKeyLookup` and `--file`-based tests address the nested-list layout and are now invalid. Delete the `SAMPLE`, `SAMPLE_LEGACY`, and `SAMPLE_LEGACY_EPIC` fixtures and every test class that consumes them, keeping only `TestAtomicAndCLI::test_no_temp_files_left` (rewritten against the tree fixture) and the `self-install` tests, which are layout-independent.

Run: `python3 skills/_shared/tests/test-pm-status.py`
Expected: PASS with no failures or errors.

- [ ] **Step 8: Commit**

```bash
git add skills/_shared/pm-status.py skills/_shared/tests/test-pm-status.py
git commit -s -m "fix(l3io-pm): address nodes by key instead of file path

set-status, set-actual, set-estimate, set-field, and verify now take
--state-root plus node keys. Back-reference mismatches exit 4.
"
```

---

## Task 3: Lock subcommands on epic.yaml

**Files:**
- Modify: `skills/_shared/pm-status.py` (`cmd_set_lock`, `cmd_clear_lock`, `cmd_check_lock`, `build_parser`)
- Test: `skills/_shared/tests/test-pm-status.py`

**Interfaces:**
- Consumes: `epic_file`, `load_node`, `save_node` (Task 1)
- Produces: `set-lock` / `clear-lock` / `check-lock` taking `--state-root --epic`; exit-5 contract preserved

- [ ] **Step 1: Write the failing tests**

```python
class TestLockOnEpicFile(TestLayoutResolution):
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 skills/_shared/tests/test-pm-status.py TestLockOnEpicFile -v`
Expected: FAIL — `--state-root` unrecognized on lock subcommands.

- [ ] **Step 3: Implement**

Replace the three lock command bodies' file resolution. In each, substitute `args.file` with a resolved path:

```python
def _epic_path_or_die(args) -> str:
    p = epic_file(args.state_root, args.epic)
    if p is None:
        _die_notfound(f"epic {args.epic}")
    return p
```

Then in `cmd_set_lock` replace `y, data = _load(args.file)` with `path = _epic_path_or_die(args)` followed by `y, data = load_node(path)`, and `_atomic_dump(y, ordered, args.file)` with `_atomic_dump(y, ordered, path)`. Apply the same substitution in `cmd_clear_lock` and `cmd_check_lock` (the latter reads only — no write).

In `build_parser`, for `set-lock`, `clear-lock`, and `check-lock`, replace `--file` with:

```python
    X.add_argument("--state-root", required=True)
    X.add_argument("--epic", required=True, help="epic key, e.g. E001")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 skills/_shared/tests/test-pm-status.py TestLockOnEpicFile -v`
Expected: PASS, 4 tests

- [ ] **Step 5: Commit**

```bash
git add skills/_shared/pm-status.py skills/_shared/tests/test-pm-status.py
git commit -s -m "fix(l3io-pm): resolve lock subcommands by epic key

set-lock, clear-lock, and check-lock take --state-root --epic. The
exit-5 locked contract and TTL staleness handling are unchanged.
"
```

---

## Task 4: Computed roll-ups and the `show` subcommand

Restores the ability to read a whole sprint or epic at once, now that no single file holds one.

**Files:**
- Modify: `skills/_shared/pm-status.py`
- Test: `skills/_shared/tests/test-pm-status.py`

**Interfaces:**
- Consumes: `find_epic_dir`, `sprint_dirname`, `load_node` (Task 1)
- Produces:
  - `list_sprint_dirs(state_root, epic_key) -> list[str]` — sorted absolute paths
  - `list_story_files(state_root, epic_key, sprint_key) -> list[str]` — sorted absolute paths
  - `rollup_sprint(state_root, epic_key, sprint_key) -> dict` — `{key, status, story_count, by_status, actual_totals}`
  - `rollup_epic(state_root, epic_key) -> dict` — `{key, status, sprint_count, story_count, by_status, actual_totals}`
  - CLI: `show --state-root R (--epic E | --epic E --sprint S)`

- [ ] **Step 1: Write the failing tests**

```python
class TestRollups(TestLayoutResolution):
    def setUp(self):
        super().setUp()
        sd = os.path.join(self.root, "active", "epic-001", "sprint-01")
        with open(os.path.join(sd, "E001-S01-001.yaml"), "w") as f:
            f.write("key: 'E001-S01-001'\nepic: 'E001'\nsprint: 'S01'\nstatus: done\n"
                    "actual:\n  elapsed_hours: 1.0\n  man_hours: 4\n  tokens_k: 100\n  cost: 1.50\n")
        with open(os.path.join(sd, "E001-S01-002.yaml"), "w") as f:
            f.write("key: 'E001-S01-002'\nepic: 'E001'\nsprint: 'S01'\nstatus: done\n"
                    "actual:\n  elapsed_hours: 2.0\n  man_hours: 6\n  tokens_k: 200\n  cost: 3.00\n")

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
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(["show", "--state-root", self.root, "--epic", "E001", "--sprint", "S01"])
        except SystemExit as e:
            code = e.code
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("E001-S01-003", out)
        self.assertIn("done", out)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 skills/_shared/tests/test-pm-status.py TestRollups -v`
Expected: FAIL with `AttributeError: module 'pm_status' has no attribute 'list_story_files'`

- [ ] **Step 3: Implement roll-ups**

Add to `skills/_shared/pm-status.py` after the layout functions:

```python
def list_sprint_dirs(state_root: str, epic_key: str) -> list:
    """Sorted sprint directories for an epic. Lexical sort is correct order (zero-padded)."""
    d = find_epic_dir(state_root, epic_key)
    if d is None:
        return []
    return sorted(os.path.join(d, n) for n in os.listdir(d)
                  if n.startswith("sprint-") and os.path.isdir(os.path.join(d, n)))


def list_story_files(state_root: str, epic_key: str, sprint_key: str) -> list:
    """Sorted story files in a sprint, excluding sprint.yaml."""
    d = find_epic_dir(state_root, epic_key)
    if d is None:
        return []
    sd = os.path.join(d, sprint_dirname(sprint_key))
    if not os.path.isdir(sd):
        return []
    return sorted(os.path.join(sd, n) for n in os.listdir(sd)
                  if n.endswith(".yaml") and n != "sprint.yaml")


def _accumulate_actuals(totals: dict, node) -> None:
    actual = (node or {}).get("actual") or {}
    for m in METRIC_FIELDS:
        v = actual.get(m)
        if v is None or _is_na(v):
            continue
        try:
            totals[m] = totals.get(m, 0.0) + float(v)
        except (TypeError, ValueError):
            continue


def rollup_sprint(state_root: str, epic_key: str, sprint_key: str) -> dict:
    by_status, totals, stories = {}, {}, []
    for p in list_story_files(state_root, epic_key, sprint_key):
        _, node = load_node(p)
        if node is None:
            continue
        st = str(node.get("status", "unknown"))
        by_status[st] = by_status.get(st, 0) + 1
        _accumulate_actuals(totals, node)
        stories.append({"key": node.get("key", os.path.basename(p)), "status": st})
    sp = sprint_file(state_root, epic_key, sprint_key)
    _, snode = load_node(sp) if sp else (None, None)
    return {
        "key": sprint_key,
        "status": str((snode or {}).get("status", "unknown")),
        "story_count": len(stories),
        "by_status": by_status,
        "actual_totals": totals,
        "stories": stories,
    }


def rollup_epic(state_root: str, epic_key: str) -> dict:
    by_status, totals, sprints, story_count = {}, {}, [], 0
    for sd in list_sprint_dirs(state_root, epic_key):
        skey = "S" + os.path.basename(sd).split("-")[1]
        r = rollup_sprint(state_root, epic_key, skey)
        sprints.append(r)
        story_count += r["story_count"]
        for k, v in r["by_status"].items():
            by_status[k] = by_status.get(k, 0) + v
        for k, v in r["actual_totals"].items():
            totals[k] = totals.get(k, 0.0) + v
    ep = epic_file(state_root, epic_key)
    _, enode = load_node(ep) if ep else (None, None)
    return {
        "key": epic_key,
        "status": str((enode or {}).get("status", "unknown")),
        "sprint_count": len(sprints),
        "story_count": story_count,
        "by_status": by_status,
        "actual_totals": totals,
        "sprints": sprints,
    }


def cmd_show(args) -> int:
    if args.sprint:
        r = rollup_sprint(args.state_root, args.epic, args.sprint)
        sys.stdout.write(f"{args.epic}/{r['key']}  status={r['status']}  stories={r['story_count']}\n")
        for s in r["stories"]:
            sys.stdout.write(f"  {s['key']:<20} {s['status']}\n")
        sys.stdout.write(f"  actuals: {_fmt_actuals(r['actual_totals'])}\n")
        return 0
    r = rollup_epic(args.state_root, args.epic)
    sys.stdout.write(f"{r['key']}  status={r['status']}  sprints={r['sprint_count']}  "
                     f"stories={r['story_count']}\n")
    for sp in r["sprints"]:
        sys.stdout.write(f"  {sp['key']:<8} status={sp['status']:<12} stories={sp['story_count']}\n")
    sys.stdout.write(f"  actuals: {ute(r['actual_totals'])}\n")
    return 0


def _fmt_actuals(totals: dict) -> str:
    """Render an actuals dict in stable METRIC_FIELDS order."""
    return "  ".join(f"{m}={totals.get(m, 0)}" for m in METRIC_FIELDS)
```

Register in `build_parser`:

```python
    sh = sub.add_parser("show", help="render a computed sprint or epic roll-up")
    sh.add_argument("--state-root", required=True)
    sh.add_argument("--epic", required=True)
    sh.add_argument("--sprint", default="")
    sh.set_defaults(func=cmd_show)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 skills/_shared/tests/test-pm-status.py TestRollups -v`
Expected: PASS, 6 tests

- [ ] **Step 5: Commit**

```bash
git add skills/_shared/pm-status.py skills/_shared/tests/test-pm-status.py
git commit -s -m "feat(l3io-pm): add computed roll-ups and the show subcommand

Sprint and epic aggregates are computed from child files, replacing the
single-file read that per-story sharding removes. Actual totals skip N/A
values rather than guessing."
```

---

## Task 5: Epic directory moves and version bump

Replaces the node-move `archive-epic` with directory moves between status folders, preferring `git mv` so history follows.

**Files:**
- Modify: `skills/_shared/pm-status.py`
- Test: `skills/_shared/tests/test-pm-status.py`

**Interfaces:**
- Consumes: `find_epic_dir`, `epic_dirname`, `epic_file`, `load_node`, `save_node` (Task 1)
- Produces:
  - `move_epic(state_root, epic_key, to_status) -> str` — returns the new absolute directory path
  - CLI: `move-epic --state-root R --epic E --to {planned,active,archived}`
  - `archive-epic --state-root R --epic E` retained as an alias for `--to archived`
  - `PM_STATUS_VERSION = "2.0.1"`

- [ ] **Step 1: Write the failing tests**

```python
class TestEpicMoves(TestLayoutResolution):
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

    def test_version_increments_for_self_install(self):
        self.assertEqual(pm.PM_STATUS_VERSION, "2.0.1")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 skills/_shared/tests/test-pm-status.py TestEpicMoves -v`
Expected: FAIL with `AttributeError: module 'pm_status' has no attribute 'move_epic'`

- [ ] **Step 3: Implement**

```python
STATUS_FOR_DIR = {"planned": "backlog", "active": "in-progress", "archived": "done"}


def move_epic(state_root: str, epic_key: str, to_status: str) -> str:
    """Move an epic directory between status folders, preferring `git mv`.

    The directory name never changes — only its parent folder — so git records a
    rename and `git log --follow` keeps working on every file in the tree.
    """
    if to_status not in STATUS_DIRS:
        raise ValueError(f"bad status folder {to_status!r} — expected one of {list(STATUS_DIRS)}")
    src = find_epic_dir(state_root, epic_key)
    if src is None:
        raise FileNotFoundError(f"epic {epic_key} not found under {state_root}")
    dest_parent = os.path.join(state_root, to_status)
    dest = os.path.join(dest_parent, epic_dirname(epic_key))
    if os.path.abspath(src) == os.path.abspath(dest):
        return dest
    if os.path.exists(dest):
        raise FileExistsError(f"destination already exists: {dest}")
    os.makedirs(dest_parent, exist_ok=True)

    moved = False
    try:
        import subprocess
        r = subprocess.run(["git", "mv", src, dest], cwd=state_root,
                           capture_output=True, text=True)
        moved = r.returncode == 0
    except (OSError, ImportError):
        moved = False
    if not moved:
        import shutil
        shutil.move(src, dest)

    p = os.path.join(dest, "epic.yaml")
    if os.path.exists(p):
        y, node = load_node(p)
        if node is not None:
            node["status"] = STATUS_FOR_DIR[to_status]
            node["updated_at"] = _now_iso()
            save_node(y, node, p)
    return dest


def cmd_move_epic(args) -> int:
    to = getattr(args, "to", None) or "archived"
    try:
        dest = move_epic(args.state_root, args.epic, to)
    except FileNotFoundError as e:
        _die_notfound(str(e))
    except (ValueError, FileExistsError) as e:
        _die_usage(str(e))
    sys.stdout.write(f"OK move-epic {args.epic} -> {to} ({dest})\n")
    return 0
```

Register both subcommands in `build_parser`, replacing the existing `archive-epic` parser:

```python
    mv = sub.add_parser("move-epic", help="move an epic directory between status folders")
    mv.add_argument("--state-root", required=True)
    mv.add_argument("--epic", required=True)
    mv.add_argument("--to", required=True, choices=list(STATUS_DIRS))
    mv.set_defaults(func=cmd_move_epic)

    ae = sub.add_parser("archive-epic", help="alias for move-epic --to archived")
    ae.add_argument("--state-root", required=True)
    ae.add_argument("--epic", required=True)
    ae.set_defaults(func=cmd_move_epic, to="archived")
```

Bump both version markers — line 6 (`# pm-status-version: 2.0.1`) and `PM_STATUS_VERSION = "2.0.1"`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 skills/_shared/tests/test-pm-status.py TestEpicMoves -v`
Expected: PASS, 7 tests

- [ ] **Step 5: Run the full suite**

Run: `python3 skills/_shared/tests/test-pm-status.py`
Expected: PASS — this is the last pm-status.py task; the whole suite must be green.

- [ ] **Step 6: Sync payload copies and verify no drift**

```bash
npm run sync:scripts && npm run check:scripts
```
Expected: `check:scripts` exits 0.

- [ ] **Step 7: Commit**

```bash
git add skills/_shared/pm-status.py skills/_shared/tests/test-pm-status.py skills/*/scripts/
git commit -s -m "fix(l3io-pm): move epics between status folders as directories

Epic transitions become git mv of the epic directory, so per-story git
history follows through planned -> active -> archived. Adds move-epic,
keeps archive-epic as an alias, bumps pm-status.py to 2.0.1 so self-install
replaces stranded 2.0.0 copies.
"
```

---

## Task 6: Rewrite the state layout contract

`status-files.md` is loaded at runtime by every PM skill. It must describe the sharded layout once the code does.

**Files:**
- Modify: `skills/_shared/status-files.md` (full rewrite)

**Interfaces:**
- Consumes: the layout and CLI from Tasks 1-5
- Produces: the canonical contract every PM skill reads at activation

- [ ] **Step 1: Rewrite the file**

Replace the entire contents of `skills/_shared/status-files.md` with a document covering, in this order:

1. **File locations** — the `{implementation_artifacts}/state/` tree with `planned/`, `active/`, `archived/`, `issues.yaml`, `pm-calibration.yaml`.
2. **The two trees** — copy the table and the two asymmetries verbatim from the spec's "The two trees" section, including the closing line *"Every epic with artifacts has state; not every epic with state has artifacts yet."* This is the section that resolves the most common misreading of the layout, so it must be present in the runtime contract, not only in the spec.
3. **Key schema** — epic `E{nnn}`, sprint `S{nn}`, story `E{nnn}-S{nn}-{nnn}`, backlog `BL-E{nnn}-{nnn}`; nodes use `key:`.
4. **Per-file schema** — bare nodes with no `epics:` wrapper; directory replaces `sprints:`/`stories:`; back-references `epic:`/`sprint:` on child files. Include all three YAML examples from the spec.
5. **Placement rule** — "an epic's directory lives in the folder named for its status," with the `planned/ → active/ → archived/` transition line.
6. **Ownership lock** — `_lock` as the first key of `epic.yaml`; `check-lock` exit 5.
7. **Addressing** — all node operations go through `pm-status.py` with `--state-root` and keys; skills never construct state paths.
8. **Ordering** — zero-padded naming makes lexical order correct order.
9. **Concurrency** — no flock needed for epic-scoped writes; `issues.yaml` remains the one shared append target and still takes `--flock`.
10. **Read resolution at activation** — the three-way detection table and the bindings `{pm_state_root}`, `{pm_issues_file}`, `{pm_calibration_file}`.
11. **Dependency fields** — `depends_on` on `epic.yaml` (epic keys) and on story files (story keys), validated by `l3io-pm-plan`.

- [ ] **Step 2: Verify no stale legacy per-epic references remain**

Run: `grep -n "_bmad/state\|sprint-status-planned\|sprint-status-archived\|sprint-status-issues\|--file" skills/_shared/status-files.md`
Expected: no output.

- [ ] **Step 3: Sync and check**

```bash
npm run sync:scripts && npm run check:scripts
```
Expected: exit 0; `references/status-files.md` updated in pm-execute, pm-plan, and pm-sync.

- [ ] **Step 4: Commit**

```bash
git add skills/_shared/status-files.md skills/*/references/status-files.md
git commit -s -m "fix(l3io-pm): rewrite status-files.md as the sharded layout contract

Documents the sharded tree, per-file schema, the placement rule, and the
state-tree vs artifact-tree distinction that the layout depends on.
"
```

---

## Task 7: Activation detection and bindings

**Files:**
- Modify: `skills/_shared/steps/shared/step-00-activate.md`

**Interfaces:**
- Consumes: the contract from Task 6
- Produces: bindings `{pm_state_root}`, `{pm_issues_file}`, `{pm_calibration_file}`, `{pm_status}`, `{session_id}`, `{active_epic_keys}` for every downstream step

- [ ] **Step 1: Replace sections 1-6**

In `skills/_shared/steps/shared/step-00-activate.md`, replace the binding block in section 1 (lines 21-25) with:

```markdown
- Set `{pm_state_root}` = `{implementation_artifacts}/state`
- Set `{pm_issues_file}` = `{pm_state_root}/issues.yaml`
- Set `{pm_calibration_file}` = `{pm_state_root}/pm-calibration.yaml`
```

Replace section 2 in full with:

````markdown
## 2. Detect state layout

Count how many of these three layouts are present — do **not** stop at the first match:

```bash
SHARDED=$([ -d "{implementation_artifacts}/state" ] && echo 1 || echo 0)
LEGACY_EPIC=$([ -d "{project-root}/_bmad/state" ] && echo 1 || echo 0)
LEGACY_FLAT=$([ -f "{implementation_artifacts}/sprint-status.yaml" ] && echo 1 || echo 0)
echo "sharded=$SHARDED legacy-per-epic=$LEGACY_EPIC legacy-flat=$LEGACY_FLAT"
```

**If more than one is 1** → halt immediately. An interrupted migration left state in two
places, and guessing which is authoritative would fork the project's state:
```
BLOCKED: multiple state layouts detected (sharded=$SHARDED legacy-per-epic=$LEGACY_EPIC legacy-flat=$LEGACY_FLAT). An earlier migration
did not finish. Do not run any l3io-pm skill until this is resolved — inspect both
locations and remove the stale one, then re-run /l3io-util-cleanup migrate-state.
```

**If only sharded** → current layout. Continue to section 3.

**If only the legacy per-epic layout or only the legacy flat layout** → halt:
```
⚠️  Legacy state layout detected (legacy per-epic layout = _bmad/state/, legacy flat layout = flat sprint-status.yaml).
Run /l3io-util-cleanup migrate-state to upgrade before continuing.
```
BLOCKED: legacy state layout — migrate required.

**If all three are 0** → possible first run. Before creating anything, rule out an orphan
caused by `implementation_artifacts` having been repointed:

```bash
git -C {project-root} ls-files -- '*/state/active/epic-*/epic.yaml' 2>/dev/null | head -5
find {project-root} -maxdepth 5 -type d -name active -path '*/state/*' 2>/dev/null | head -5
```

If either prints a path that is not under `{implementation_artifacts}/state`, halt:
```
BLOCKED: state found at <printed-path> but implementation_artifacts resolves to
{implementation_artifacts}. Did implementation_artifacts change? Refusing to start a
blank project over existing state.
```

If both print nothing → genuine first run. Continue to section 3.
````

Replace section 3 with:

```markdown
## 3. Create state directories

```bash
mkdir -p {pm_state_root}/active {pm_state_root}/planned {pm_state_root}/archived
mkdir -p {planning_artifacts}
```

Verify the state root is not gitignored — this is what keeps state in version control:

```bash
git -C {project-root} check-ignore -q {pm_state_root} && echo IGNORED || echo TRACKED
```

If `IGNORED`, halt:
```
BLOCKED: {pm_state_root} is gitignored. Project state must be committed. Add to .gitignore:
  !{pm_state_root}/
  !{pm_state_root}/**
```
```

Replace section 5 with:

```markdown
## 5. List active epics

```bash
ls -d {pm_state_root}/active/epic-*/ 2>/dev/null || echo "(none)"
```

Bind `{active_epic_keys}` = the `E{nnn}` key for each directory found (`epic-001` → `E001`).
An empty list is valid on first run.
```

Replace section 6's verify command with:

```bash
python3 {pm_status} verify --state-root {pm_state_root} --epic {epic_key} --scope epic
```

Update section 8's status line to reference `{pm_state_root}`.

- [ ] **Step 2: Verify no stale references remain**

Run: `grep -n "bmad_state_root\|bmad_active_root\|bmad_planned_file\|bmad_archived_file\|E\*-status.yaml" skills/_shared/steps/shared/step-00-activate.md`
Expected: no output.

- [ ] **Step 3: Sync, check, and commit**

```bash
npm run sync:scripts && npm run check:scripts
git add skills/_shared/steps/shared/step-00-activate.md skills/*/steps/shared/step-00-activate.md
git commit -s -m "fix(l3io-pm): three-way state detection with ambiguity and orphan guards

Activation counts all three layouts and blocks when more than one is
present rather than guessing. Adds a git-based orphan check for a
repointed implementation_artifacts, and a gitignore gate on the state root.
"
```

---

## Task 8: Migration to the sharded layout

**Files:**
- Modify: `skills/l3io-util-cleanup/assets/migrate-state.md` (full rewrite)

**Interfaces:**
- Consumes: `move_epic` and the layout from Tasks 1-5; the contract from Task 6
- Produces: `/l3io-util-cleanup migrate-state` handling legacy-flat→sharded and legacy-per-epic→sharded

- [ ] **Step 1: Rewrite migrate-state.md**

Replace the file with a procedure structured as:

**Pre-flight** — detect the source layout using the same three-way count as Task 7. Block if `{implementation_artifacts}/state/` already exists. Block if more than one source layout is present.

**Stage A (legacy flat only)** — apply the existing in-memory normalizations, unchanged from the current file's Step 2: epic `deferred`→`backlog` or `in-progress` by whether any sprint is done; epic `superseded`→`done` preserving `superseded_by`; sprint `deferred`→`backlog`; story `deferred`→ extracted as a `BL-E{nnn}-{nnn}` issue with `severity: Low` and `source: migrate-state (deferred)`; story `superseded`→`done`; `id:`→`key:` with zero-padding. This yields a legacy-per-epic-shaped in-memory tree, which Stage B then explodes. Do not duplicate this logic — it already exists and is the only correct source for these rules.

**Stage B (both paths)** — explode the nested tree into the sharded layout:

```
for each epic node:
    status_dir = {done: archived, in-progress: active, backlog|deferred: planned}[epic.status]
    mkdir -p {pm_state_root}/{status_dir}/epic-{nnn}/
    write epic.yaml   ← epic node minus `sprints:`, plus depends_on
    for each sprint node:
        mkdir -p .../sprint-{nn}/
        write sprint.yaml  ← sprint node minus `stories:`, plus epic: back-reference
        for each story node:
            write {story-key}.yaml  ← story node, plus epic:/sprint: back-references
```

**Stage C** — move `sprint-status-issues.yaml` → `{pm_state_root}/issues.yaml`, and `{project-root}/_bmad/pm-calibration.yaml` → `{pm_state_root}/pm-calibration.yaml`.

**Stage D** — back up originals as `.legacy` using cp-if-not-exists (never overwrite an existing backup), then prompt: move to `_bmad/migration-backup/` (default) / delete / keep in place.

**Stage E** — post-migration verification, all three required to pass:

```bash
# 1. state root must be committed
git -C {project-root} check-ignore -q {pm_state_root} && echo "FAIL: gitignored" || echo "OK: tracked"

# 2. every story file must resolve and carry correct back-references
python3 {pm_status} verify --state-root {pm_state_root} --epic {each_epic_key} --scope epic

# 3. drift check — state files vs story artifacts, per sprint
diff <(ls {pm_state_root}/*/epic-{nnn}/sprint-{nn}/*.yaml 2>/dev/null \
        | xargs -n1 basename | sed 's/.yaml//' | grep -v '^sprint$') \
     <(ls {implementation_artifacts}/epic-{nnn}/sprint-{nn}/stories/*.md 2>/dev/null \
        | xargs -n1 basename | sed 's/.md//')
```

Report each epic migrated, story counts per sprint, and any drift found. Drift is reported, never auto-corrected — an orphan on either side needs a human decision.

- [ ] **Step 2: Verify no stale references remain**

Run: `grep -n "_bmad/state\|E{nnn}-status.yaml\|sprint-status-planned" skills/l3io-util-cleanup/assets/migrate-state.md`
Expected: matches appear **only** as legacy per-epic *source* paths being read, never as destinations. Inspect each hit and confirm.

- [ ] **Step 3: Commit**

```bash
git add skills/l3io-util-cleanup/assets/migrate-state.md
git commit -s -m "fix(l3io-util): migrate state to the sharded layout

Handles legacy flat and legacy per-epic (_bmad/state) sources, exploding the nested
tree into per-story files under {implementation_artifacts}/state/, and
verifies the result is tracked, resolvable, and free of drift.
"
```

---

## Task 9: Health check drift detection and sort-status reduction

**Files:**
- Modify: `skills/l3io-util-cleanup/SKILL.md` (section `### Step HC2 — Scan (8 checks, read-only)` at line 126; `sort-status` docs at line 38 and the command table around line 80; `## Target Folder Structure` at line 274)

**Interfaces:**
- Consumes: the layout from Task 6, the migration from Task 8
- Produces: a 9th health check; `sort-status` reduced to a naming-convention validator

- [ ] **Step 1: Add the drift check**

In `### Step HC2`, retitle to `(9 checks, read-only)` and append:

````markdown
9. **State/artifact drift** — for each sprint directory under `{pm_state_root}/*/epic-*/sprint-*/`,
   compare story state files against story artifacts:

   ```bash
   diff <(ls {pm_state_root}/*/epic-{nnn}/sprint-{nn}/*.yaml 2>/dev/null \
           | xargs -n1 basename | sed 's/.yaml//' | grep -v '^sprint$') \
        <(ls {implementation_artifacts}/epic-{nnn}/sprint-{nn}/stories/*.md 2>/dev/null \
           | xargs -n1 basename | sed 's/.md//')
   ```

   Lines starting `<` are state files with no story artifact; `>` are story artifacts with
   no state. Also flag any file whose `epic:`/`sprint:` back-reference disagrees with its
   directory. Severity: **Medium**. Report only — never auto-correct, since an orphan on
   either side needs a human decision about which side is right.

   A planned epic with state and no artifacts is **not** drift — stories are authored after
   planning. Only flag epics in `active/` and `archived/`.
````

- [ ] **Step 2: Reduce sort-status**

Ordering can no longer drift: nodes are files, and zero-padded names (`epic-001`, `sprint-01`, `E001-S01-003`) make lexical order correct order. Replace the `sort-status` description at line 38 with:

```markdown
- **`sort-status`:** Validates state file and directory naming against the zero-padded
  convention (`epic-{nnn}/`, `sprint-{nn}/`, `E{nnn}-S{nn}-{nnn}.yaml`). Ordering itself
  can no longer drift under the sharded layout — directory listing order is correct order — so
  this mode no longer reorders anything. It reports misnamed entries, which would sort
  incorrectly and break key resolution.
```

Update the command table entry near line 80 to match.

- [ ] **Step 3: Reconcile epic directory padding (BLOCKING — the mirror depends on it)**

The repo currently contradicts itself on artifact epic-directory width, and the mirror rule is false until this is fixed:

| Source | Epic dir | Sprint dir |
|---|---|---|
| `status-files.md`, `steps/plan/step-03-story-elaboration.md`, `module-help.csv` | `epic-{nnn}` (3 digits) | `sprint-{nn}` (2) |
| `l3io-util-cleanup/SKILL.md` "Target Folder Structure" | `epic-{EE}` (**2 digits**) | `sprint-{SS}` (2) |

util-cleanup states *"`EE` and `SS` are zero-padded two-digit values"* — and it is the skill that physically reorganizes artifacts into that layout, so it would create `epic-01/` while state creates `epic-001/`, breaking the identical-path-suffix property the drift check rests on.

**Resolution: 3-digit epics win.** They match the epic key `E{nnn}`, the story key `E{nnn}-S{nn}-{nnn}`, and every legacy-per-epic-era file. util-cleanup is the stale outlier.

In `skills/l3io-util-cleanup/SKILL.md`:

1. Replace every `epic-{EE}` with `epic-{nnn}` and every `sprint-{SS}` with `sprint-{nn}`.
2. Replace the sentence "`EE` and `SS` are zero-padded two-digit values (`01`, `02`, etc.)." with:
   "`nnn` is a zero-padded three-digit epic number (`001`, `002`) and `nn` a zero-padded two-digit sprint number (`01`, `02`), matching the epic key `E{nnn}` and sprint key `S{nn}`."
3. Add a renaming check to the health scan: flag any existing `{implementation_artifacts}/epic-{nn}/` directory using the old two-digit form, and offer to rename it to the three-digit form. Report it at **High** severity — the mirror and every state path resolution depend on it.

Verify: `grep -n "epic-{EE}\|sprint-{SS}\|two-digit" skills/l3io-util-cleanup/SKILL.md` returns no output.

- [ ] **Step 4: Update the target folder structure**

Replace `## Target Folder Structure` (line 274) with the sharded tree from the spec, showing both `state/` and the top-level `epic-{nnn}/` artifact directories, and the note that the two trees mirror each other.

- [ ] **Step 5: Verify**

Run: `grep -n "8 checks" skills/l3io-util-cleanup/SKILL.md`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add skills/l3io-util-cleanup/SKILL.md
git commit -s -m "feat(l3io-util): add state/artifact drift check, reduce sort-status

The mirrored layout makes drift a directory diff, added as health check
9. Zero-padded naming makes lexical order correct order, so sort-status
becomes a naming validator rather than a reordering pass."
```

---

## Task 10: Gitignore verification in module setup

**Files:**
- Modify: `skills/l3io-pm-execute/assets/module-setup.md`, `skills/l3io-pm-plan/assets/module-setup.md`, `skills/l3io-pm-help/assets/module-setup.md`, `skills/l3io-pm-sync/assets/module-setup.md`

**Interfaces:**
- Consumes: `{pm_state_root}` from Task 7
- Produces: setup fails loudly rather than silently creating ignored state

Only the four PM skills manage state. `l3io-sec-redteam`, `l3io-util-cleanup`, and `l3io-arch-review` do not create state and are not modified.

- [ ] **Step 1: Add the gate to each of the four files**

After the block defining `implementation_artifacts` (near line 35 in the pm-execute copy), insert:

````markdown
### Verify state is version-controlled

l3io-pm state must be committed — it is shared with the team, appears in PRs, and must
survive a fresh clone. Verify the state root is not gitignored:

```bash
git -C {project-root} check-ignore -q {implementation_artifacts}/state && echo IGNORED || echo TRACKED
```

If `IGNORED`, stop and tell the user to add these lines to `.gitignore`, then re-run setup:

```
!{implementation_artifacts}/state/
!{implementation_artifacts}/state/**
```

Do not proceed with `IGNORED` — state written to an ignored path is silently lost on a
fresh clone, which is the failure this check exists to prevent.
````

- [ ] **Step 2: Verify all four carry the gate**

Run: `grep -l "check-ignore" skills/l3io-pm-*/assets/module-setup.md | wc -l`
Expected: `4`

- [ ] **Step 3: Commit**

```bash
git add skills/l3io-pm-*/assets/module-setup.md
git commit -s -m "feat(l3io-pm): gate module setup on state being version-controlled

Setup refuses to proceed when the state root is gitignored. The absence
of this check is what silently un-versioned state under the legacy per-epic layout."
```

---

## Task 11: Convert step files to key-based calls

**Files:**
- Modify: all files under `skills/_shared/steps/` that construct state paths or call `pm-status.py --file`

**Interfaces:**
- Consumes: the CLI from Tasks 2-5, bindings from Task 7
- Produces: no step file constructs a state path

- [ ] **Step 1: Enumerate the work**

```bash
grep -rln "_bmad/state\|--file {.*state\|E{nnn}-status.yaml\|sprint-status-" skills/_shared/steps/
```

Fix every file the command lists. Expected to include `steps/sync/step-03-operations.md`, `steps/shared/step-estimate.md`, `steps/sprint/step-02-story-prep.md`, `steps/sprint/step-04-sprint-closure.md`, and `steps/execute/step-06-epic-closure.md`.

- [ ] **Step 2: Apply these substitutions**

| Old | New |
|---|---|
| `--file {bmad_active_root}/E{nnn}-status.yaml --story K` | `--state-root {pm_state_root} --story K` |
| `--file {bmad_active_root}/E{nnn}-status.yaml --epic E --sprint S` | `--state-root {pm_state_root} --epic E --sprint S` |
| `--file {bmad_issues_file}` (append-issue) | `--file {pm_issues_file}` (unchanged — `issues.yaml` is still a real file) |
| `--file {project-root}/_bmad/pm-calibration.yaml` | `{pm_calibration_file}` |
| `archive-epic --active-file A --archive-file B --epic E` | `archive-epic --state-root {pm_state_root} --epic E` |
| reading a whole sprint from one YAML | `python3 {pm_status} show --state-root {pm_state_root} --epic E --sprint S` |

`append-issue` keeps `--file` deliberately: `issues.yaml` is a flat file, not a resolvable node.

- [ ] **Step 3: Fix the self-install deadlock in `step-00-activate.md` (BLOCKING — breaks every upgrade)**

An upgrading user is currently deadlocked:

1. Section 2 (detect layout) **blocks** on a legacy layout, so sections 3-8 never run.
2. Section 4 is where `pm-status.py` self-installs — so it never runs, and the installed copy stays at the pre-upgrade version.
3. `migrate-state` checks only that `{pm_status}` **exists**, not its version. It exists, so migration proceeds.
4. Stage E calls `verify --state-root …`, a flag the stale copy does not have → argparse error.

The migration runs and then fails its own verification against a stale script.

**Fix, in two parts:**

(a) In `skills/_shared/steps/shared/step-00-activate.md`, move the `self-install` block (currently section 4) to run **before** the layout detection in section 2. Self-install is layout-independent — it copies a file and needs no state — so nothing about detection depends on it, and running it first guarantees a current script no matter which branch detection takes. Renumber the remaining sections. Bind `{pm_status}` there, since later sections use it.

(b) In `skills/l3io-util-cleanup/assets/migrate-state.md`, upgrade the existence check into a version check:

```bash
grep -m1 "pm-status-version:" {pm_status}
```

If the marker is absent or reads lower than the version this release ships, BLOCK with:

```
BLOCKED: {pm_status} is version {found}, but this migration needs {required} or newer.
Run any l3io-pm skill once to self-install the current copy, then re-run migrate-state.
```

Verify the deadlock is actually gone by tracing the upgrade path in your report: stale script present → activation self-installs before detecting → detection blocks with the migrate instruction → `migrate-state` finds a current script and its version check passes.

- [ ] **Step 4: Harden the orphan-check pathspec**

In `skills/_shared/steps/shared/step-00-activate.md`, the orphan probe uses:

```bash
git -C {project-root} ls-files -- '*/state/active/epic-*/epic.yaml'
```

Git's fnmatch-pathname semantics require at least one literal path segment before `state/`, so this does **not** match a root-level `state/active/epic-*/epic.yaml` — the case where `implementation_artifacts` equals `project-root`, which is a plausible configuration. The companion `find` probe covers it today, making that redundancy load-bearing rather than incidental. Add a second pathspec without the leading `*/`:

```bash
git -C {project-root} ls-files -- '*/state/active/epic-*/epic.yaml' 'state/active/epic-*/epic.yaml'
```

- [ ] **Step 5: Acceptance gate — every one of these must return zero**

This is the definition of "all skills can run". Each command below currently returns a non-zero count; every one must return 0 before this task is done. Paste the actual output into your report.

```bash
# (a) CLI forms that no longer exist in pm-status.py 2.0.1
grep -rn -- "--active-file\|--archive-file\|--source {" skills/_shared/ | wc -l    # currently 1

# (b) bindings activation no longer produces
grep -rl "{bmad_state_root}\|{bmad_active_root}\|{bmad_planned_file}\|{bmad_archived_file}\|{bmad_issues_file}" \
  skills/_shared/steps/ | wc -l                                                    # currently 10 files

# (c) --file passed to subcommands that dropped it
grep -rn -- "--file {bmad" skills/_shared/steps/ | wc -l                           # currently 12

# (d) state paths constructed by step files instead of resolved by pm-status.py
grep -rn "_bmad/state\|E{nnn}-status.yaml\|sprint-status-planned\|sprint-status-archived" \
  skills/_shared/steps/ | wc -l
```

The ten files behind (b) are: `steps/shared/step-estimate.md`, `steps/execute/step-06-epic-closure.md`, `steps/closure/sprint-closure.md`, `steps/execute/step-05-epic-loop.md`, `steps/execute/step-04-arch-gate.md`, `steps/execute/step-03-load-plan.md`, `steps/execute/step-02-scope-resolve.md`, `steps/sprint/step-03-dev-loop.md`, `steps/plan/step-02-readiness-check.md`, `steps/plan/step-04-load-state.md`.

Exception: `--file {pm_issues_file}` on `append-issue` is correct and must remain — `issues.yaml` is a flat file, not a resolvable node. Check (c) matches `{bmad` specifically so it will not flag that.

- [ ] **Step 5b: Verify no step file constructs a state path**

Run: `grep -rn "_bmad/state\|E{nnn}-status.yaml\|sprint-status-planned\|sprint-status-archived" skills/_shared/steps/`
Expected: no output.

- [ ] **Step 6: Sync, check, and commit**

```bash
npm run sync:scripts && npm run check:scripts
git add skills/_shared/steps/ skills/*/steps/
git commit -s -m "fix(l3io-pm): call pm-status.py with keys instead of paths

Step files no longer construct state paths; layout knowledge lives only
in pm-status.py, so a future layout change stops being breaking for skills.
"
```

---

## Task 12: Repo docs, superseding notes, and release

**Files:**
- Modify: `CLAUDE.md`, `docs/superpowers/specs/2026-08-14-v2-migration-design.md`, `docs/superpowers/plans/2026-08-14-v2-migration.md`

**Interfaces:**
- Consumes: everything above
- Produces: a releasable 2.0.1

- [ ] **Step 1: Update CLAUDE.md**

Rewrite the **State files** bullet list to the sharded tree. Replace the `_bmad/state/` paths with `{implementation_artifacts}/state/{planned,active,archived}/epic-{nnn}/`, `issues.yaml`, and `pm-calibration.yaml`. Add the placement rule sentence and a one-line statement of the two-tree distinction.

In the **Estimation calibration** paragraph, change "The file is project-scoped and not committed by default" to "The file lives at `{implementation_artifacts}/state/pm-calibration.yaml` and is committed — learned ratios are team knowledge and expensive to rebuild."

In the **Status writes** paragraph, replace the description of per-node addressing with `--state-root` plus keys, and note that skills never construct state paths.

- [ ] **Step 2: Add superseding notes**

At the top of both legacy per-epic design documents, immediately under the title, insert:

```markdown
> **Superseded (2026-08-16).** The state-layout sections of this document — `_bmad/state/`,
> per-epic `E{nnn}-status.yaml` files, and the three flat status files — are superseded by
> `docs/superpowers/specs/2026-08-16-v3-state-relocation-design.md`. This document is
> preserved as the historical record of the legacy per-epic migration design; do not
> implement from its state layout sections.
```

Change nothing else in either file.

- [ ] **Step 3: Full verification**

```bash
python3 skills/_shared/tests/test-pm-status.py
npm run check:scripts
grep -rn "_bmad/state" skills/ CLAUDE.md
```
Expected: tests PASS; `check:scripts` exit 0; the `grep` matches **only** in `migrate-state.md` (reading legacy per-epic sources) and `step-00-activate.md` (detecting the legacy per-epic layout). Any other hit is a missed conversion — fix before releasing.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/superpowers/
git commit -s -m "docs: update CLAUDE.md for sharded state layout, mark legacy docs superseded"
```

- [ ] **Step 5: Enforce script sync as a release gate**

Today nothing *prevents* a release with stale payload copies — `check:scripts` runs in CI (after the fact) and `postbump` re-syncs only after the version bump, using `git add -u`, which stages tracked files only. Make sync a hard precondition.

In `.versionrc.cjs`, add a `prerelease` hook alongside the existing `postbump` and broaden postbump's staging:

```js
  scripts: {
    // Hard gate: refuse to release when payload copies have drifted from
    // skills/_shared/. Drift here means someone edited a shared source without
    // running `npm run sync:scripts` — releasing would ship mismatched copies.
    prerelease: "node scripts/sync-shared-scripts.mjs --check",
    // After the bump, payloads legitimately re-sync (version strings are embedded),
    // so regenerate and stage. `-A` (not `-u`) so NEW skill files are included.
    postbump: "node scripts/sync-bmad-versions.mjs && node scripts/sync-shared-scripts.mjs && git add -A skills/ .claude-plugin/ && git add -u"
  },
```

`prerelease` runs for every `release:*` alias, so the gate cannot be bypassed by choosing a different bump type.

Verify the gate actually fires by proving it fails on drift and passes when clean:

```bash
# 1. introduce deliberate drift in a payload copy
printf '\n# drift probe\n' >> skills/l3io-pm-execute/scripts/pm-status.py
node scripts/sync-shared-scripts.mjs --check; echo "exit=$?   # MUST be non-zero"

# 2. restore and confirm the gate passes
npm run sync:scripts
node scripts/sync-shared-scripts.mjs --check; echo "exit=$?   # MUST be 0"
git diff --stat   # must be empty — sync restored the copy exactly
```

A gate that has never been observed failing is not a gate. Do not proceed until step 1 prints a non-zero exit.

In `CLAUDE.md`, replace the existing staging warning under `## Commands` with: the `prerelease` gate refuses to release on payload drift, and `postbump` now stages with `git add -A skills/` so newly added skill files are included rather than silently dropped.

- [ ] **Step 6: Stage untracked files, then release**

`postbump` runs `git add -u`, which stages only already-tracked files. Any new file added by this plan must be staged first or it is silently excluded from the release commit.

```bash
git status --porcelain | grep '^??'   # must be empty; git add anything listed
npm run release:patch
```

- [ ] **Step 7: Verify the release**

```bash
git show --stat HEAD
grep -n '"version"' package.json
grep -rn "2.0.1" .claude-plugin/marketplace.json | head -3
```
Expected: version `2.0.1` in `package.json`, `marketplace.json`, and all `module.yaml` files; `skills/*/scripts/pm-status.py` present in the release commit.

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §1 Layout (tree, placement rule, sharding) | 1, 5, 6 |
| §1 Per-file schema (bare nodes, back-refs) | 1, 2, 6 |
| §1 Ordering becomes structural | 9 |
| §1 Mirror rule and drift detection | 8, 9 |
| §1 The two trees | 6 (runtime contract), 12 (CLAUDE.md) |
| §2 Detection order + ambiguity block | 7 |
| §2 Orphan detection | 7 |
| §2 Gitignore verification | 7, 10 |
| §3 Keys instead of paths | 2, 3, 11 |
| §3 Bindings | 7 |
| §3 Subcommand changes (`show`, roll-ups, archive, flock) | 4, 5 |
| §4 Migration legacy-flat→sharded, legacy-per-epic→sharded | 8 |
| §5 Deferred/rejected scope | Not implemented, by design |
| §6 Affected files | 6-12 |
| Release (patch 2.0.1) | 5 (version marker), 12 (release) |

No spec requirement is unassigned.

**Type consistency:** `state_root` is the parameter name throughout; `--state-root` is the flag throughout. `epic_key`/`sprint_key`/`story_key` are used consistently. `move_epic` is defined in Task 5 and referenced by name only in Task 8. `METRIC_FIELDS` is reused from existing code rather than redefined. `STATUS_DIRS` (Task 1) is reused by `move_epic` (Task 5) and `STATUS_FOR_DIR` maps its members to status values.

**Known ordering constraint:** Tasks 1-5 must run in order (each builds on the previous), and Task 6 must land before Tasks 7-11 so the contract is current when the step files are rewritten against it. Tasks 9 and 10 are independent of each other and could run in either order.
