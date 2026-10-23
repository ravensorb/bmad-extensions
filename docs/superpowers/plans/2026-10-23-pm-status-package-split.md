# pm-status.py Package Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `skills/_shared/pm-status.py` (10,000 lines, at ADR-0001's hard cap) into a Python package whose module boundaries are drawn by 4.0.0 fate, so the v7 cut deletes a directory.

**Architecture:** The file became `skills/_shared/pm_status/`, invoked as `uv run …/pm_status/__main__.py`. Modules are extracted **in dependency order, root first**, with the full suite green at every commit. A `sys.modules` alias in `__init__.py` keeps `mock.patch.object(pm, …)` working.

**Tech Stack:** Python 3.11+ (PEP 723 inline metadata, `uv run`), `ruamel.yaml`, `unittest`; Node for gate tooling.

**Spec:** `docs/superpowers/specs/2026-10-22-pm-status-package-split-design.md`

> **REVISED 2026-10-23, after measurement.** Tasks 1–3 shipped. The original tasks 2–6 were
> sized from the distance between `# ---` banners; a banner marks where a topic *begins*, not
> where a module *ends*, so every span silently absorbed whatever followed. Measured against the
> real definitions, "instructions" is **277 lines, not 737**, and the `state` bucket contained a
> genuine **cycle** with `issues`. Tasks 4+ below are re-derived from
> `.superpowers/sdd/2026-10-23-pm-status-package-split/boundary-measurement.md`, which lists all
> 366 definitions with spans and assigned modules.

## Global Constraints

- **Per-file cap: 1,500 lines** over every `.py` in the package. **Enforced since Task 9** (moved forward from Task 12: the number was stated here, in `boundary-measurement.md` and in `metrics/__init__.py`'s docstring and checked nowhere, which is this repo's dominant failure mode). `__main__.py` is the one file still on ADR-0001's 10,000 limit, because it only drops under 1,500 when Task 11 lands; folding it in is Task 12's remaining job.
- **Never hand-edit a per-skill payload copy.** Author in `skills/_shared/`, then `npm run sync:scripts`, then `node scripts/write-payload-manifest.mjs`.
- **Test ASSERTIONS never change.** A `mock.patch` *target* may be repointed in the same commit that moves the name it targets — see the module-qualified-call rule below.
- **Call across modules through the module object** — `core._atomic_dump(...)`, never `from .core import _atomic_dump`. A `from X import name` binding is a private copy, so patching the defining module would not reach it. This is what keeps the suite's ~15 patch sites meaningful.
- **Nothing directly in `pm_status/`** except `__main__.py` and `__init__.py`. That directory is `sys.path[0]` under the shipped invocation, so a module there named like a stdlib one shadows it.
- **Every extraction widens the gates that read only `__main__.py`**: `check-types.mjs` `TARGET`, and `check-docs.mjs` checks 4, 10, 12 and 26. Code that leaves `__main__.py` without this silently leaves the gate.
- Every task passes all 12 gates in `.github/workflows/checks.yml` — derive the list from that file. Conventional Commits with DCO (`git commit -s`). Python via `uv run`.
- v6 line, release 3.6.0. `self-install` is v6-only, retired at 4.0.0.

## Review Focus

1. **Relative imports under the shipped invocation.** `uv run …/__main__.py` executes a script, so `from .x import` raises "no known parent package" — while the suite's `import pm_status` works. **The suite cannot see this failure.** → Task 4, and a script-path smoke test after every extraction.
2. **Gate scope silently narrowing** as code leaves `__main__.py`. → Task 4 fixes the scopes; every later task verifies.
3. **A `from X import name` binding defeating a `mock.patch`** — the test passes while guarding nothing. → the module-qualified-call rule, checked per extraction.
4. **`package_root()` resolving from `__file__`** returns the wrong directory once it moves into a subpackage. → Task 5.
5. **A module whose `register()` is never called** loses its verbs with no behavioural test firing. → Task 12.

---

## Completed

- **Task 1 — package skeleton** (`3bf05f1..356b2af`). `git mv` into `pm_status/__main__.py`; `__init__.py` does `sys.modules[__name__] = _main`; sync converted to a tree walk; all path-naming gates re-pointed. Review clean.
- **Task 2 — install contract** (`356b2af..fb3a154`). `self-install` installs the package directory: stage → rename-aside → rename-in, `tree_digest`, `sweep_stale`, guarded rollback, legacy-file removal gated on a shipped hash. Review clean.
- **Task 3 — binding flip** (`fb3a154..a94089c`). `{pm_status}` → `…/_bmad/scripts/pm-status/__main__.py` across all four skills; three doctor scripts repaired. Review clean.

---

### Task 4: Bootstrap prologue, gate scope, and the script-path smoke test

**Nothing may be extracted before this lands.** It is the prerequisite the measurement surfaced.

**Files:** `pm_status/__main__.py`; `scripts/check-types.mjs`; `scripts/check-docs.mjs`; `skills/_shared/tests/test-pm-status.py`; `CLAUDE.md`

**Produces:** a package that runs correctly both as a script and as an import; gates whose scope is the package rather than one file.

- [ ] **Step 1: Write the failing smoke test**

It must invoke the way the shipped binding does — as a **script path**, not an import:

```python
def test_runs_as_a_script_path_not_only_as_an_import(self):
    r = subprocess.run([sys.executable, SCRIPT, "--version"], capture_output=True, text=True)
    self.assertEqual(r.returncode, 0, r.stderr)
```

- [ ] **Step 2: Add a relative import, then run it to verify it fails**

Temporarily add `from . import __init__ as _probe` near the top of `__main__.py`.
Expected: the script run FAILS with "attempted relative import with no known parent package" while `import pm_status` still succeeds. That asymmetry is the defect. Remove the probe afterwards.

- [ ] **Step 3: Add the bootstrap prologue**

At the very top of `__main__.py`, before any relative import: when `__package__` is empty, put the package's parent on `sys.path`, import `pm_status.__main__`, and delegate to its `main()`. Must work in four modes — direct script, script from another cwd, `import pm_status`, and `python -m pm_status`.

- [ ] **Step 4: Widen the gate scopes**

`check-types.mjs` `TARGET` and `check-docs.mjs` checks 4, 10, 12 and 26 each read `pm_status/__main__.py` only. Make each cover every `.py` under `skills/_shared/pm_status/`. Check 12 applies per file (Task 9 then tightened it to 1,500 for every file except `__main__.py`).

- [ ] **Step 5: Fix the stale invocation path in `CLAUDE.md`**

Line ~284 still reads `{skill-root}/../l3io-setup/scripts/pm-status.py self-install …`; it should be `scripts/pm_status/__main__.py`.

- [ ] **Step 6: Run all 12 gates and the full suites, commit**

### Task 5: Extract `core/` (~1,003 lines)

The dependency root: constants, YAML round-trip, atomic writes, lock-ignore, every lock including the epic lock, errors, `STATUS_DIRS`, key parsers and canonicalisers, the event-log **writer**, value helpers, `self-install`, `package_root`.

**Depends on:** nothing, *after* seven relocations the measurement names — `STATUS_DIRS`, the epic-lock set, `parse_story_key`, `epic_dirname`, `calibration_path`, `adr_register_path`, `NOTICES_FILENAME` sit upstream of where they belong and move down into `core` with it.

- [ ] **Step 1: Relocate the seven upstream items, suite green, commit separately** — so a later bisect separates the relocation from the extraction.
- [ ] **Step 2: Move the bucket into `core/`**, splitting if any file would exceed 1,500 (the measurement suggests locks/io versus self-install).
- [ ] **Step 3: Fix `package_root()`** — it resolves from `__file__` and must return the `pm_status/` directory from one level deeper. There is a Task-1 test pinning this.
- [ ] **Step 4: Repoint the six patch targets that land here** — `_atomic_dump`, `_load`, `_atomic_text_write`, `notices_lock`, `agent_instructions_lock`, `_SHIPPED_SHAS` — and convert their consumers to module-qualified calls. Assertions unchanged.
- [ ] **Step 5: Script-path smoke test, all gates, full suites, commit**

### Task 6: Extract `instructions/` (277 lines)

Marker engine plus instruction-file sync. A leaf over `core`; needs three `core` names.

- [ ] **Step 1: Move the bucket.** This is 277 lines, not the 737 the original plan claimed — do not expand the span to reach that number.
- [ ] **Step 2: Script-path smoke test, all gates, full suites, commit**

### Task 7: Extract `nodes/` (431 lines)

Layout resolution, load/save, ensure, story-document skeleton, `deps_list`, node-field schemas. Sits **below** `issues`, which is what breaks the cycle in the original `state` bucket.

- [ ] **Step 1: Move the bucket.** `nodes` is the only place a node key resolves to a path — check 26's target moves here.
- [ ] **Step 2: Repoint `save_node` and `epic_file` patch targets**; both have many consumers, so module-qualified calls are mandatory, not stylistic.
- [ ] **Step 3: Script-path smoke test, all gates, full suites, commit**

### Task 8: Extract `metrics/` (3,475 lines, 7 files)

Calibration (1,220 — the largest single file and still under the cap), estimates, spend/usage, progress model, renderers, event-log **readers** (the writer went to `core`).

- [ ] **Step 1: Move the bucket as seven files**, each verified under 1,500 with `wc -l`.
- [ ] **Step 2: Repoint `rollup_parent_estimate`, `compute_story_estimate`, `dispatch_window`**
- [ ] **Step 3: Script-path smoke test, all gates, full suites, commit**

### Task 9: Extract `issues/` (1,967 lines, 4 files)

Store (538), promote (577), audit (702), ADR allocator (150). Above `nodes`, below `verbs`.

- [x] **Step 1: Move the bucket as four files.** `pm.IssueStore` is unaffected by the move; `resolve_issue_core` is the patch target that lands here. It was the last BARE one, so `TestPatchTargetsAreDefinedInMain` now has no known next firing and its non-empty anchor counts every `pm`-rooted patch site rather than the bare ones alone.
- [x] **Step 2: Script-path smoke test, all gates, full suites, commit**

### Task 10: Extract `verbs/` (1,100 lines)

`set-status`, `set-field`, `set-estimate`, `set-depends-on`, `import-node`, `sync-story-doc`, locks, `notice`, `show`, `list-*`, `verify`. Above `issues`.

- [ ] **Step 1: Move the bucket**, splitting to stay under 1,500.
- [ ] **Step 2: Script-path smoke test, all gates, full suites, commit**

### Task 11: Extract `plan/` (847 lines)

`move-epic`, `reparent-story`, `dump-plan`, `retire-epic`, the reorg journal and undo.

- [ ] **Step 1: Move the bucket.** `__main__.py` should now hold only the 320-line module docstring (check 10 reads it there), imports, `build_parser`, `main` and the prologue — about 900 lines.
- [ ] **Step 2: Script-path smoke test, all gates, full suites, commit**

### Task 12: Distributed registration and the per-file cap

**Files:** `pm_status/__main__.py`, each module's `__init__.py`, `scripts/check-docs.mjs`, `scripts/tests/check-docs.test.mjs`

- [ ] **Step 1: Write the 43-subcommand regression guard.** `build_parser()` already exists and already registers all 43, so this test **passes before the change** — it is a regression guard, not a TDD driver. Confirm it passes first, so it is measuring the right thing.
- [ ] **Step 2: Implement `register(subparsers)` per module**; `build_parser()` calls them in a fixed order.
- [ ] **Step 3: Mutation-check the guard** — delete one module's `register()` call and confirm the test fails. A guard that cannot fail is the failure mode this task exists to prevent.
- [ ] **Step 4: Verify the CLI surface is byte-identical** against `.superpowers/sdd/2026-10-23-pm-status-package-split/cli-surface-before.txt`. Any diff is a dropped or reordered registration.
- [x] **Step 5: Tighten check 12 to a per-file 1,500-line cap** over `pm_status/**/*.py`. The message names the file, its count, the limit, and ADR-0001. Delete the "Option C, a bundler, is the first candidate" sentence — ADR-0001 retired Option C. Add a test planting a 1,501-line file. **Done in Task 9**, except for `__main__.py`, which is still above 1,500 until Task 11 lands and so stays on ADR-0001's 10,000 limit. All that remains here is deleting `PM_STATUS_LINE_LIMIT` and its `__main__.py` exception once the entry file is under the module cap.
- [ ] **Step 6: Run all gates and the full suites, commit**

### Task 13: ADR amendment and documentation

- [ ] **Step 1: Amend ADR-0001** per spec §8 — the spike measurements including that its own named test fails; atomicity reachable via symlink; the POSIX-only finding; Option B adopted with the plain-directory install because `self-install` retires at 4.0.0; the per-file cap. No new ADR number.
- [ ] **Step 2: Record what the measurement changed.** The module map in spec §3 was derived from banner spans and was wrong; `boundary-measurement.md` is the real carve. The spec's §3 table needs correcting or explicitly superseding.
- [ ] **Step 3: Update `CLAUDE.md`, `scripts/CLAUDE.md`, `docs/upgrading.md`** — shared-file table row, per-file cap, and the runtime move from `_bmad/scripts/pm-status.py` to `_bmad/scripts/pm-status/`.
- [ ] **Step 4: Run all gates, commit**
