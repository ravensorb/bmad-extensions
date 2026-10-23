# pm-status.py Package Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `skills/_shared/pm-status.py` (exactly 10,000 lines, at ADR-0001's hard cap) into a Python package whose module boundaries are drawn by 4.0.0 fate, so the v7 cut deletes a directory.

**Architecture:** The file becomes `skills/_shared/pm_status/`, invoked as `uv run …/pm_status/__main__.py`. Modules are extracted one at a time with the full suite green at every commit; a re-export facade in `__init__.py` keeps the 1,009-method suite byte-identical through the moves. The install contract — a plain directory staged and swapped by two renames — changes last, in one commit.

**Tech Stack:** Python 3.11+ (PEP 723 inline metadata, `uv run`), `ruamel.yaml`, `unittest`; Node for the gate tooling (`scripts/check-docs.mjs`, `scripts/sync-shared-scripts.mjs`).

**Spec:** `docs/superpowers/specs/2026-10-22-pm-status-package-split-design.md`

## Global Constraints

- **Per-file cap: 1,500 lines**, over every `.py` in the package. Enforced from Task 6; until then check 12 keeps its existing 10,000 limit, re-pointed. Never disable the gate.
- **Never hand-edit a per-skill payload copy.** Author in `skills/_shared/`, then `npm run sync:scripts`, then `node scripts/write-payload-manifest.mjs`. `check:manifest` fails after any skill edit until regenerated.
- **The suite stays byte-identical through Tasks 2–5** except the Task 1 bootstrap change. If a task needs a test edited to pass, the extraction is wrong — fix the facade instead.
- **Every task's commit must pass all 12 gates** in `.github/workflows/checks.yml`. Derive the list from that file, never from memory.
- **Python runs via `uv run`**, never bare `python3`. The PEP 723 header lives in `pm_status/__main__.py` only.
- Conventional Commits with DCO sign-off (`git commit -s`).
- v6 line, release 3.6.0. `self-install` is v6-only machinery, retired at 4.0.0 — do not generalise it.

## Review Focus

Five failure modes the spec implies that no extraction test naturally covers. Each has a test pinned to the task that owns the code.

1. **A crashed install leaves `pm-status.old-<pid>/` or `pm-status.staging-<pid>/`** and the next run must sweep them, or the directory accumulates 10,000-line copies silently. → Task 7.
2. **The window between the two renames**: an invocation landing there finds no `pm-status/` and must fail loudly with the path, not write a wrong answer. → Task 7.
3. **A module whose `register()` is never called** loses its verbs with no behavioural test firing — the test that invokes the verb just fails to find it, which reads as a test bug. → Task 6.
4. **`__file__`-relative path resolution** breaks when code moves into a submodule one directory deeper. → Task 4 (`core/`), where `self-install` and version reading live.
5. **The facade omitting a name the suite imports** fails at import time for the whole suite, not as one test. → Task 1.

---

### Task 1: Package skeleton, gates re-pointed, suite green

Moves the file wholesale into the package with **no reorganisation**. Everything that names the old path changes here so the build is green from this commit on.

**Files:**
- Create: `skills/_shared/pm_status/__main__.py` (the current file's full content, `git mv`)
- Create: `skills/_shared/pm_status/__init__.py`
- Delete: `skills/_shared/pm-status.py`
- Modify: `skills/_shared/tests/test-pm-status.py:29-37` (bootstrap)
- Modify: `scripts/sync-shared-scripts.mjs:62` (sync group)
- Modify: `scripts/check-docs.mjs` (`PM_STATUS` const used by checks 4, 10, 12, 26, 30)
- Modify: `scripts/check-types.mjs`, `scripts/check-pm-status-version.mjs`, `scripts/check-bmb.mjs` (path references)

**Interfaces:**
- Produces: the package root `skills/_shared/pm_status/`, importable as `import pm_status` when `skills/_shared/` is on `sys.path`. `pm_status.<name>` resolves every module-level name the old file exposed.

- [ ] **Step 1: Move the file and create the facade**

`git mv skills/_shared/pm-status.py skills/_shared/pm_status/__main__.py`

`__init__.py` re-exports the module-level surface so `pm.<name>` keeps working:

```python
"""Facade: re-exports __main__'s surface so the suite's `pm.<name>` calls keep resolving.

MIGRATION INSTRUMENT, not the end state. Tasks 2-5 move code into submodules behind this;
shrinking it to a real public surface is separate work after the suite is repointed.

NOT `from .__main__ import *`: star-import skips underscore-prefixed names, and the suite
calls internals directly (`_file_sha`, `_parse_version_line`, `_load_checked`). Copying vars()
carries them; filtering only `__dunder__` is what keeps `__name__` and friends out.
"""
from . import __main__ as _main
globals().update({k: v for k, v in vars(_main).items() if not k.startswith("__")})
```

Importing `__main__` as a submodule does not execute `main()` — the `if __name__ == "__main__"`
guard is false under import.

- [ ] **Step 2: Repoint the test bootstrap**

In `test-pm-status.py`, replace the `spec_from_file_location` block. `sys.path.insert(0, os.path.dirname(HERE))` already exists, so a plain import works:

```python
SCRIPT = os.path.join(os.path.dirname(HERE), "pm_status", "__main__.py")
sys.path.insert(0, os.path.dirname(HERE))
import pm_status as pm
```

`SCRIPT` stays, because the suite spawns it as a subprocess (`[sys.executable, SCRIPT, …]`).

- [ ] **Step 3: Run the suite to verify the move changed nothing**

Run: `npm run test:python`
Expected: all suites pass, same count as before the move.

This step is also the test for **Review Focus #5**. A name missing from the facade raises
`AttributeError` on first use, or `ImportError` at collection — the whole suite fails rather
than one test, which is the loud failure we want. Record the pre-move count before Step 1 so
"same count" is checkable rather than remembered.

- [ ] **Step 4: Re-point every gate that names the old path**

Change each path constant from `skills/_shared/pm-status.py` to `skills/_shared/pm_status/__main__.py`. `check:docs`'s `PM_STATUS_LINE_LIMIT` keeps the value **10000** — the file is still one lump and the cap tightens in Task 6.

The sync group at `sync-shared-scripts.mjs:62` is `{ src, rel }` for one file; it becomes a tree sync in Task 8. For now point it at `pm_status/__main__.py` with `rel` `scripts/pm_status/__main__.py`, and add `__init__.py` as a second entry.

- [ ] **Step 5: Capture the CLI surface baseline**

Record `--help` for all 43 subcommands; Task 6 diffs against it.

```bash
for s in $(uv run skills/_shared/pm_status/__main__.py --help | grep -oE '^\s{4}[a-z][a-z0-9-]+' | tr -d ' '); do
  echo "=== $s"; uv run skills/_shared/pm_status/__main__.py "$s" --help
done > /tmp/cli-surface-before.txt
```

Commit this file to the branch as `docs/superpowers/plans/cli-surface-before.txt` so a fresh subagent in Task 6 can read it.

- [ ] **Step 6: Sync, regenerate manifests, run all gates**

Run: `npm run sync:scripts && node scripts/write-payload-manifest.mjs`, then every gate in `.github/workflows/checks.yml`.
Expected: 12/12 PASS.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -s -m "refactor(l3io-pm): move pm-status.py into a pm_status package"
```

---

### Task 2: Extract `instructions/`

The lowest-risk extraction and the one that proves the pattern: 737 lines of pure string transforms with no I/O (`# agent instruction block -- the marker engine`).

**Files:**
- Create: `skills/_shared/pm_status/instructions/__init__.py`, `instructions/markers.py`
- Modify: `skills/_shared/pm_status/__main__.py` (remove the moved block, import from the module)

**Interfaces:**
- Consumes: nothing from other modules — it is pure by construction.
- Produces: every name in the marker-engine section, importable as `pm_status.instructions.markers.<name>`, and still reachable as `pm_status.<name>` through the Task 1 facade.

- [ ] **Step 1: Move the section into `instructions/markers.py`**

The block runs from the `# agent instruction block -- the marker engine: pure string transforms, no I/O` banner to the `# spend attribution` banner. Fits the 1,500 cap at 737 lines; do not split it.

- [ ] **Step 2: Re-export from `__main__.py`**

`from .instructions.markers import *` at the point the block was removed, so `__main__`'s namespace is unchanged and the facade keeps working.

- [ ] **Step 3: Run the suite**

Run: `npm run test:python`
Expected: pass, with **no test file edited**. A failure here means a name did not survive the move — fix the re-export, not the test.

- [ ] **Step 4: Sync, regenerate, run all gates, commit**

```bash
npm run sync:scripts && node scripts/write-payload-manifest.mjs
git add -A && git commit -s -m "refactor(l3io-pm): extract the instruction marker engine"
```

---

### Task 3: Extract `metrics/`

The half that survives 4.0.0 and the half under active development. ~2,600 lines across five sections, one of which exceeds the cap.

**Files:**
- Create: `metrics/__init__.py`, `metrics/calibration.py`, `metrics/samples.py`, `metrics/spend.py`, `metrics/progress.py`, `metrics/render.py`
- Modify: `pm_status/__main__.py`

**Interfaces:**
- Consumes: locking and YAML helpers, still in `__main__.py` until Task 4. Import them as `from .. import __main__ as _main` **only if needed**; prefer moving a helper's *use* and leaving the helper until Task 4.
- Produces: `pm_status.metrics.<module>.<name>` for every name in these sections.

- [ ] **Step 1: Move the four under-cap sections**

`spend.py` (spend attribution, 178), `progress.py` (progress model, 288), `render.py` (renderers, 240). Each is one banner-delimited block.

- [ ] **Step 2: Split calibration across `calibration.py` and `samples.py`**

Calibration is 1,891 lines, over the 1,500 cap. The seam is the one the spec names: the **learning model** (ratio derivation, the three components, decay weighting) versus the **sample store** (reading, migrating and appending `pm-calibration.yaml`, including the v1→v2 migration). `CALIBRATION_SCHEMA_VERSION` belongs with the store.

Both files must end under 1,500 lines; verify with `wc -l`.

- [ ] **Step 3: Re-export and run the suite**

Run: `npm run test:python`
Expected: pass, no test file edited.

- [ ] **Step 4: Sync, regenerate, run all gates, commit**

```bash
git commit -s -m "refactor(l3io-pm): extract the metrics modules"
```

---

### Task 4: Extract `core/`

Infrastructure every other module needs. Owns **Review Focus #4**: `self-install` and version reading resolve paths from `__file__`, which moves one directory deeper here.

**Files:**
- Create: `core/__init__.py`, `core/locking.py`, `core/yamlio.py`, `core/version.py`, `core/install.py`, `core/values.py`
- Modify: `pm_status/__main__.py`

**Interfaces:**
- Produces: `core.locking` (the `flock` helpers and `_file_lock`), `core.yamlio` (ruamel round-trip load/dump), `core.version` (`PM_STATUS_VERSION`, `_parse_version_line`, `_file_sha`), `core.install` (`cmd_self_install`), `core.values` (the value helpers, 33 lines).

- [ ] **Step 1: Write the failing test for `__file__` resolution after the move**

In `test-pm-status.py`, pin that self-install resolves the package root rather than its own module directory:

```python
def test_self_install_resolves_the_package_root_not_the_module_dir(self):
    # core/install.py is one level deeper than __main__.py was. A bare
    # dirname(__file__) here points at core/, and the install would copy
    # the wrong tree.
    root = pm.core.install.package_root()
    self.assertTrue(os.path.isfile(os.path.join(root, "__main__.py")))
    self.assertEqual(os.path.basename(root), "pm_status")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run skills/_shared/tests/test-pm-status.py -k package_root`
Expected: FAIL — `package_root` does not exist.

- [ ] **Step 3: Move the sections and implement `package_root()`**

Implement `package_root() -> str` in `core/install.py`, returning the `pm_status/` directory regardless of which submodule asks. `cmd_self_install` uses it in place of `os.path.abspath(__file__)`.

Everything else moves unchanged: the `flock` helpers, the ruamel round-trip, `PM_STATUS_VERSION` and `_parse_version_line`, `_file_sha`, the value helpers.

- [ ] **Step 4: Run the suite**

Run: `npm run test:python`
Expected: pass, including the new test.

- [ ] **Step 5: Sync, regenerate, run all gates, commit**

```bash
git commit -s -m "refactor(l3io-pm): extract the core infrastructure modules"
```

---

### Task 5: Extract `state/`

The largest extraction, ~5,400 lines, and the directory 4.0.0 deletes. Two sections exceed the cap.

**Files:**
- Create: `state/__init__.py`, `state/layout.py`, `state/nodes.py`, `state/locks.py`, `state/reorg.py`, `state/storydoc.py`, `state/issues/__init__.py`, `state/issues/store.py`, `state/issues/audit.py`, `state/issues/repair.py`
- Modify: `pm_status/__main__.py`, `scripts/check-docs.mjs` (check 26's target)

**Interfaces:**
- Produces: `state.layout` — **the only place that resolves a node key to a path**, which is what check 26 asserts.

- [ ] **Step 1: Move `layout.py` and re-point check 26**

Check 26 currently asserts state paths are assembled only in "`pm-status.py`'s resolver section", a comment marker. Its target becomes `state/layout.py`, a module boundary. Each module docstring records the 4.0.0 fate; the directory is named `state/`, **not** `v6/`.

- [ ] **Step 2: Split the issue store (2,410 lines) across three files**

`store.py` (read/write of `issues.yaml` and `issues-resolved.yaml`, the per-epic key allocator), `audit.py` (findings 1a–1l), `repair.py` (the `repair-issue` actions). Each under 1,500; verify with `wc -l`.

- [ ] **Step 3: Split subcommands by fate, not by file order**

The 1,733-line subcommand section is not one unit: `cmd_set_status`, `cmd_import_node` and the node verbs belong in `state/nodes.py`; the lock verbs in `state/locks.py`; `cmd_sync_story_doc` and `cmd_story_doc_init` in `state/storydoc.py`. Verbs that survive 4.0.0 (`cmd_set_actual`, `cmd_verify`'s estimate half, `cmd_adr_reserve`, `cmd_notice`, `cmd_dispatch`) stay out of `state/` — they go to `metrics/` or `core/`.

`cmd_verify` splits: node loading to `state/nodes.py`, estimate/actual verification and the cost recompute to `metrics/`.

- [ ] **Step 4: Run the suite**

Run: `npm run test:python`
Expected: pass, no test file edited.

- [ ] **Step 5: Confirm every file is under the cap**

Run: `find skills/_shared/pm_status -name '*.py' -exec wc -l {} + | sort -rn | head -5`
Expected: the largest is under 1,500.

- [ ] **Step 6: Sync, regenerate, run all gates, commit**

```bash
git commit -s -m "refactor(l3io-pm): extract the v6 state modules"
```

---

### Task 6: Distributed registration and the per-file cap

Owns **Review Focus #3**. `__main__.py` is now a CLI shell; each module registers its own verbs so deleting `state/` at 4.0.0 removes 27 of them.

**Files:**
- Modify: `pm_status/__main__.py`, every module's `__init__.py`
- Modify: `scripts/check-docs.mjs` (check 12)
- Modify: `scripts/tests/check-docs.test.mjs`

**Interfaces:**
- Produces: `register(subparsers) -> None` on each of `core`, `metrics`, `instructions`, `state`. `__main__.py` calls all four.

- [ ] **Step 1: Write the failing test for the surface guarantee**

The risk is a module whose `register()` is never called — its verbs vanish and no behavioural test reports it. Pin the count:

```python
def test_every_registered_subcommand_is_reachable(self):
    import argparse
    parser = pm.build_parser()
    actions = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    self.assertEqual(len(actions), 1)
    self.assertEqual(len(actions[0].choices), 43)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run skills/_shared/tests/test-pm-status.py -k every_registered_subcommand`
Expected: FAIL — fewer than 43 while registration is still central, or `build_parser` absent.

- [ ] **Step 3: Implement `register(subparsers)` per module**

Each module's `__init__.py` gains `register(subparsers)` adding only its own verbs. `__main__.py`'s `build_parser()` creates the subparsers object and calls the four in a fixed order.

- [ ] **Step 4: Verify the CLI surface is byte-identical**

```bash
for s in $(uv run skills/_shared/pm_status/__main__.py --help | grep -oE '^\s{4}[a-z][a-z0-9-]+' | tr -d ' '); do
  echo "=== $s"; uv run skills/_shared/pm_status/__main__.py "$s" --help
done > /tmp/cli-surface-after.txt
diff docs/superpowers/plans/cli-surface-before.txt /tmp/cli-surface-after.txt
```

Expected: **no output.** Any diff is a dropped or reordered registration.

- [ ] **Step 5: Tighten check 12 to a per-file cap**

Replace the single-file read with a walk of `skills/_shared/pm_status/**/*.py`, failing on any file over **1,500** lines. The failure message names the file, its count, the limit, and `docs/adr/0001-pm-status-single-self-installed-file.md`. Delete the now-false "Option C, a bundler, is the first candidate" sentence — ADR-0001 retired Option C.

Add a test in `check-docs.test.mjs` that plants a 1,501-line `.py` in the fixture's package and asserts check 12 fails naming that file.

- [ ] **Step 6: Run the suite and all gates, commit**

```bash
git commit -s -m "refactor(l3io-pm): distribute parser registration, cap files at 1500 lines"
```

---

### Task 7: The new install contract

Owns **Review Focus #1 and #2**. `self-install` installs a directory, not a file.

**Files:**
- Modify: `pm_status/core/install.py`
- Modify: `skills/_shared/tests/test-pm-status.py`

**Interfaces:**
- Produces: `cmd_self_install` installing to a `pm-status/` **directory** under `--dest`'s parent; `tree_digest(root) -> str`; `sweep_stale(parent) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_sweep_removes_crashed_install_siblings(self):
    d = tempfile.mkdtemp()
    for name in ("pm-status.old-999", "pm-status.staging-999"):
        os.makedirs(os.path.join(d, name))
    os.makedirs(os.path.join(d, "pm-status"))
    removed = pm.core.install.sweep_stale(d)
    self.assertEqual(sorted(removed), ["pm-status.old-999", "pm-status.staging-999"])
    self.assertTrue(os.path.isdir(os.path.join(d, "pm-status")))

def test_a_missing_install_fails_loudly_naming_the_path(self):
    d = tempfile.mkdtemp()
    r = subprocess.run([sys.executable, os.path.join(d, "pm-status", "__main__.py"), "show"],
                       capture_output=True, text=True)
    self.assertNotEqual(r.returncode, 0)
    self.assertIn("pm-status", r.stderr + r.stdout)

def test_tree_digest_changes_with_any_file(self):
    ...  # digest(tree) != digest(tree with one byte changed in any file)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run skills/_shared/tests/test-pm-status.py -k "sweep_stale or tree_digest"`
Expected: FAIL — the functions do not exist.

- [ ] **Step 3: Implement the four-step install**

Per spec §4: stage into `pm-status.staging-<pid>/`; compare `tree_digest` against the installed tree and skip when identical; `os.rename` the live directory to `pm-status.old-<pid>/`; `os.rename` staging into place and delete the old.

If the second rename fails, rename the old directory back and report failure. Call `sweep_stale` at the **start** of every run so a crashed predecessor is collected.

`tree_digest(root)` is SHA-256 over sorted `(relpath, file-sha256)` pairs. The downgrade refusal (`_parse_version_line`, strictly-newer installed is refused) is unchanged.

- [ ] **Step 4: Implement the legacy-file removal**

Delete `_bmad/scripts/pm-status.py` after a successful swap **only when its SHA-256 matches a version this package shipped**. A patched copy does not match, survives, and is reported on stderr. Test both branches.

- [ ] **Step 5: Run the suite and all gates, commit**

```bash
git commit -s -m "feat(l3io-pm): install pm-status as a package directory"
```

---

### Task 8: The binding flip

One commit, 156 sites. Lands last, after the package is proven.

**Files:**
- Modify: 94 `.md` under `skills/` carrying `{pm_status}`; 48 naming `_bmad/scripts/pm-status.py`; 14 invoking `self-install`
- Modify: `scripts/sync-shared-scripts.mjs` (tree sync)

- [ ] **Step 1: Convert the sync group to a tree**

`sync-shared-scripts.mjs:62`'s `{ src, rel }` pair becomes a recursive walk of `skills/_shared/pm_status/`, delivering every `.py` under `scripts/pm_status/`. `--check` compares trees. `--dump-deliveries` must keep working — check 24 derives its scope by spawning it, and a broken dump surfaces as ~90 unrelated failures naming nothing useful.

- [ ] **Step 2: Flip the bindings**

`{pm_status}` becomes `{project-root}/_bmad/scripts/pm-status/__main__.py`. Author in `skills/_shared/`; never edit a per-skill copy.

- [ ] **Step 3: Verify no site was missed**

Run: `grep -rn '_bmad/scripts/pm-status\.py' skills/ docs/ scripts/ | grep -v upgrading.md`
Expected: no output. `docs/upgrading.md` keeps historical references deliberately.

- [ ] **Step 4: Run all gates and the full suites, commit**

Checks 4, 10 and 30 parse these invocations, so a missed site fails a gate.

```bash
git commit -s -m "feat(l3io-pm): point every binding at the installed package"
```

---

### Task 9: ADR amendment and documentation

**Files:**
- Modify: `docs/adr/0001-pm-status-single-self-installed-file.md`
- Modify: `CLAUDE.md`, `scripts/CLAUDE.md`, `docs/upgrading.md`

- [ ] **Step 1: Amend ADR-0001**

Per spec §8: the four spike measurements including that the ADR's own named test (`os.replace` on a directory) **fails**; that atomicity is reachable via a symlink; the POSIX-only finding defusing the Windows objection; the decision to adopt Option B with the **plain-directory** install because `self-install` retires at 4.0.0; and the per-file 1,500 cap replacing check 12. No new ADR number — ADR-0001 says the argument belongs there, and it already carries a 2026-10-23 amendment.

- [ ] **Step 2: Update the shared-file table and the self-install paragraph**

`CLAUDE.md`'s shared-file table row for `pm-status.py` becomes the package. The self-install paragraph keeps the 2026-10-23 wipe note and gains the directory install. `scripts/CLAUDE.md` gets the per-file cap.

- [ ] **Step 3: Add an upgrading note**

`docs/upgrading.md`: the installed runtime moves from `_bmad/scripts/pm-status.py` to `_bmad/scripts/pm-status/`, happens automatically at next activation, and the old file is removed when unmodified.

- [ ] **Step 4: Run all gates, commit**

Check 18 gates the check-count prose in three files; check 1 allows `upgrading.md` to name the old path when explaining the change.

```bash
git commit -s -m "docs(infra): record the package split in ADR-0001 and the contracts"
```
