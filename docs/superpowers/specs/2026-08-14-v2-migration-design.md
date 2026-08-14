# bmad-extensions v2.0.0 Migration Design

**Date:** 2026-08-14
**Type:** Architectural — major version migration
**Approach:** Hybrid (copy proven architecture, author differences fresh)

---

## Overview

A full architectural overhaul of bmad-extensions from v1.x to v2.0.0. Breaking changes throughout. Existing users must run `/l3io-util-cleanup migrate-state` before using any PM skill after upgrading.

Key changes:
- `src/` → `skills/` directory rename with flat skill layout
- State files move to `_bmad/state/` with per-epic sharding
- `l3io-pm-sprint-execute` + `l3io-pm-epic-execute` merged into `l3io-pm-execute`
- `l3io-pm-plan-execution` renamed to `l3io-pm-plan`
- Two new skills: `l3io-pm-help`, `l3io-pm-sync` (GitHub Issues only)
- `l3io-sec-agent-redteam` renamed to `l3io-sec-redteam`
- New `_bmad/scripts/`: `resolve_config.py`, `memlog.py`
- Skills restructured into `steps/` subdirectories with shared step files

---

## Section 1: Repository Structure & Skill Inventory

### Directory rename

`src/` → `skills/`, including `src/_shared/` → `skills/_shared/`.

The nesting level also flattens: previously `src/<module>/<skill>/`, now `skills/<skill>/`. Module grouping moves to `marketplace.json` metadata only.

`.claude/commands/` symlinks updated from `src/<module>/<skill>/SKILL.md` → `skills/<skill>/SKILL.md`.

### Skill inventory

| Old name | New name | Change |
|---|---|---|
| `l3io-pm-sprint-execute` | *(removed)* | merged into `l3io-pm-execute` |
| `l3io-pm-epic-execute` | *(removed)* | merged into `l3io-pm-execute` |
| `l3io-pm-plan-execution` | `l3io-pm-plan` | renamed + steps architecture |
| *(new)* | `l3io-pm-execute` | merges sprint + epic execution |
| *(new)* | `l3io-pm-help` | new — recommends next action |
| *(new)* | `l3io-pm-sync` | new — GitHub Issues sync |
| `l3io-sec-agent-redteam` | `l3io-sec-redteam` | directory + symlink rename only |
| `l3io-util-cleanup` | `l3io-util-cleanup` | adds `migrate-state` mode |
| `l3io-arch-review` | `l3io-arch-review` | unchanged |

### Shared steps layout

`skills/_shared/steps/` is the canonical source for step files shared across PM skills:

```
skills/_shared/
  pm-status.py
  status-files.md
  tests/
    test-pm-status.py
  steps/
    shared/
      step-00-activate.md     ← runs first in every PM skill
      step-01-classify-work.md
      step-estimate.md
    execute/
      step-02-scope-resolve.md
      step-03-load-plan.md
      step-04-arch-gate.md
      step-05-epic-loop.md
      step-06-epic-closure.md
    sprint/
      step-02-story-prep.md
      step-03-dev-loop.md
      step-04-sprint-closure.md
    plan/
      step-02-readiness-check.md
      step-03-story-elaboration.md
      step-04-load-state.md
      step-05-dependency-graph.md
      step-06-plan-output.md
    closure/
      sprint-closure.md
      epic-closure.md
    sync/
      step-02-detect-platform.md
      step-03-operations.md
      step-04-resolve.md
```

`sync-shared-scripts.mjs` syncs all step files into their consuming skill directories alongside `pm-status.py` and `status-files.md`.

---

## Section 2: State Layout (Breaking Change)

### New location

State files move from `{implementation_artifacts}/` to `{project-root}/_bmad/state/`.

### Directory structure

```
{project-root}/_bmad/state/
  active/
    E001-status.yaml    ← one file per in-progress epic
    E002-status.yaml
  sprint-status-planned.yaml    ← backlog epics (was sprint-status-backlog.yaml)
  sprint-status-issues.yaml     ← new: open issues tracked separately
  sprint-status-archived.yaml   ← done epics (same semantics as before)
```

### Per-epic sharding

Each `active/E{nnn}-status.yaml` contains exactly one epic with its in-progress and done sprints. This eliminates contention between parallel subagents operating on different epics.

### Lock mechanism

Each `active/E{nnn}-status.yaml` gains a `_lock` block:
```yaml
_lock:
  session_id: "l3io-pm-2026-08-14T10:00:00-abc123"
  claimed_at: "2026-08-14T10:00:00"
  ttl_minutes: 30
```

`pm-status.py` gains `set-lock`, `check-lock`, `clear-lock` subcommands. `l3io-pm-help` flags stale locks (claimed_at older than ttl_minutes).

### Legacy auto-detect and blocking

`step-00-activate.md` (shared, runs in every PM skill) checks for `_bmad/state/` on activation:

- **Present** → new layout, continue
- **Absent + `{implementation_artifacts}/sprint-status.yaml` exists** → legacy layout detected, block:
  ```
  ⚠️  Legacy state layout detected. Run /l3io-util-cleanup migrate-state to upgrade
  the state files to the new layout before continuing.
  ```
- **Absent + no legacy file** → first run, create directories and continue

### `migrate-state` mode in `l3io-util-cleanup`

New mode added to `l3io-util-cleanup`. Reads legacy files:
- `sprint-status.yaml` (or `sprint-status-active.yaml`)
- `sprint-status-backlog.yaml`
- `sprint-status-archived.yaml`

Writes new layout:
- In-progress epics → `_bmad/state/active/E{nnn}-status.yaml` (one per epic)
- Backlog → `_bmad/state/sprint-status-planned.yaml`
- Archived → `_bmad/state/sprint-status-archived.yaml`
- Issues → `_bmad/state/sprint-status-issues.yaml` (empty on migration)

Backs up originals as `.legacy`, then prompts user to move/delete/keep backups. Never overwrites an existing `.legacy` backup.

---

## Section 3: Skills Redesign

### `l3io-pm-execute`

Merges `l3io-pm-sprint-execute` + `l3io-pm-epic-execute` into one skill with two execution modes.

**Headless mode** (dispatched by the epic loop with a context block containing `headless: true`):
```
steps/shared/step-00-activate.md
steps/sprint/step-02-story-prep.md
steps/sprint/step-03-dev-loop.md
steps/sprint/step-04-sprint-closure.md
```

**Normal mode** (user invokes directly):
```
steps/shared/step-00-activate.md
steps/shared/step-01-classify-work.md
steps/execute/step-02-scope-resolve.md
steps/execute/step-03-load-plan.md
steps/execute/step-04-arch-gate.md
steps/execute/step-05-epic-loop.md
steps/execute/step-06-epic-closure.md
```

`step-01-classify-work` determines scope: full run, single epic (`l3io-pm-execute E001`), or single sprint (`l3io-pm-execute E001 S02`).

### `l3io-pm-plan`

Rename + steps refactor of `l3io-pm-plan-execution`. Same logic split into:
```
steps/shared/step-00-activate.md
steps/shared/step-01-classify-work.md
steps/plan/step-02-readiness-check.md
steps/plan/step-03-story-elaboration.md
steps/plan/step-04-load-state.md
steps/plan/step-05-dependency-graph.md
steps/plan/step-06-plan-output.md
```

Outputs `plan-output-meta.yaml` to `{planning_artifacts}/`.

### `l3io-pm-help`

Single-step skill (no `steps/` subdirectory). Reads `_bmad/state/` snapshot and applies a priority-ordered decision table to recommend the exact next command:

| Condition | Recommendation |
|---|---|
| No state files, no epics | Run story creation first |
| No `plan-output-meta.yaml` | Run `/l3io-pm-plan` |
| Plan readiness = red | Run `/l3io-pm-plan` to resolve gaps |
| Plan readiness = amber | Run `/l3io-pm-plan` or proceed with `/l3io-pm-execute` |
| Stale lock on an epic | Run `pm-status.py clear-lock` for that epic |
| Active epic, no blocked sprint | Run `/l3io-pm-execute {key}` |
| No active epics, plan green | Run `/l3io-pm-execute` |
| All epics done | Run `/l3io-pm-sync` to push closure |
| Deferred epics | Surface count, suggest `/l3io-pm-plan` |

### `l3io-pm-sync`

GitHub Issues only. Modes: `status` (default), `setup`, `push`, `pull`, `sync`.

Steps:
```
steps/shared/step-00-activate.md
steps/sync/step-02-detect-platform.md
steps/sync/step-03-operations.md
steps/sync/step-04-resolve.md
```

Scripts (authored fresh, no ADO):
- `detect-platform.py` — confirms GitHub, reads sync-mapping.yaml
- `sync-state.py` — bidirectional sync engine (GitHub Issues ↔ `_bmad/state/`)
- `drift-report.py` — compares local state vs GitHub, reports drift

`setup` mode creates `sync-mapping.yaml` linking epic/story keys to GitHub issue numbers.

### `l3io-sec-redteam`

Directory rename from `l3io-sec-agent-redteam` only. SKILL.md, `customize.toml` (`[agent]` root key), and all references unchanged. `.claude/commands/` symlink updated.

### `l3io-util-cleanup`

Existing modes unchanged. New `migrate-state` mode added via `assets/migrate-state.md` step file.

### `l3io-arch-review`

Unchanged. Open-source standards files (dotnet, nodejs, python, docker, github-actions, powershell, shell) remain as-is.

---

## Section 4: New `_bmad/scripts/` Components

### `resolve_config.py`

4-layer TOML merge for central BMad config. Layer priority (highest last):
1. `_bmad/config.toml` (installer-owned team)
2. `_bmad/config.user.toml` (installer-owned user)
3. `_bmad/custom/config.toml` (human-authored team, committed)
4. `_bmad/custom/config.user.toml` (human-authored user, gitignored)

Usage: `python3 {project-root}/_bmad/scripts/resolve_config.py --project-root {project-root} --key modules.l3io-pm`

No third-party dependencies — stdlib `tomllib` only (Python 3.11+).

### `memlog.py`

Append-only memory log with atomic writes. Subcommands: `init`, `append`, `set`.

Used by skills needing persistent, session-resumable working memory (the security agent's sanctum, and future stateful skills).

File shape: `{workspace}/.memlog.md` with YAML frontmatter + flat chronological entry list.

### `resolve_customization.py` (update)

Existing per-skill script updated to v2 (improved keyed-merge logic for arrays with mixed `code`/`id` fields). Drop-in replacement in every skill's `scripts/` directory.

### Installation

All three scripts (`resolve_config.py`, `memlog.py`, `resolve_customization.py`) are shipped in `skills/_shared/` and synced by `sync-shared-scripts.mjs` into each PM skill's `scripts/` directory (alongside `pm-status.py`).

`step-00-activate.md` installs them into `{project-root}/_bmad/scripts/` with simple copy-if-absent logic:
```bash
mkdir -p {project-root}/_bmad/scripts
# pm-status.py via self-install (version-guarded):
uv run {skill-root}/scripts/pm-status.py self-install --dest {project-root}/_bmad/scripts/pm-status.py
# resolve_config.py and memlog.py via direct copy if absent:
cp -n {skill-root}/scripts/resolve_config.py {project-root}/_bmad/scripts/resolve_config.py
cp -n {skill-root}/scripts/memlog.py {project-root}/_bmad/scripts/memlog.py
```

`pm-status.py` keeps its existing version-guarded `self-install` (skips if already up-to-date). The other two use `cp -n` (no-overwrite) since they have no version header to check against.

---

## Section 5: Build Pipeline

### `sync-shared-scripts.mjs` rewrite

Updated for `skills/` root and flat layout. New sync manifest:

- `sharedStepFiles` → all PM skills (`l3io-pm-execute`, `l3io-pm-plan`, `l3io-pm-sync`)
- `planStepFiles` → `l3io-pm-plan`
- `executeStepFiles` → `l3io-pm-execute`
- `syncStepFiles` → `l3io-pm-sync`
- `pmScriptFiles` (`pm-status.py`, `test-pm-status.py`) → `l3io-pm-execute`, `l3io-pm-plan`, `l3io-pm-sync`
- `pmRefFiles` (`status-files.md`) → `l3io-pm-execute`, `l3io-pm-plan`, `l3io-pm-sync`

Old `pmScriptDirs` and `allPmDirs` arrays empty (old skills removed at cutover).

### `sync-bmad-versions.mjs`

Updated glob pattern finds `module.yaml` under `skills/` (flat) instead of `src/<module>/<skill>/`.

### `.claude/commands/` symlinks

Removed: `l3io-pm-sprint-execute`, `l3io-pm-epic-execute`, `l3io-pm-plan-execution`, `l3io-sec-agent-redteam`
Added: `l3io-pm-execute`, `l3io-pm-plan`, `l3io-pm-help`, `l3io-pm-sync`, `l3io-sec-redteam`

### `.claude-plugin/marketplace.json`

Skill list updated to new inventory. `postbump` handles version sync automatically.

### Staging reminder

Before `npm run release:major`, explicitly `git add` all new files under `skills/` — the `postbump` hook uses `git add -u` (only already-tracked files).

---

## Section 6: Versioning & Release

**Version: `1.1.1` → `2.0.0`**

Released via `npm run release:major`.

### CHANGELOG entry

Top-level `BREAKING CHANGE` block:
- State layout migration: files move to `_bmad/state/`, per-epic sharding in `active/`
- Skill consolidation: sprint-execute + epic-execute → `l3io-pm-execute`
- Renamed: `l3io-pm-plan-execution` → `l3io-pm-plan`, `l3io-sec-agent-redteam` → `l3io-sec-redteam`
- New skills: `l3io-pm-help`, `l3io-pm-sync` (GitHub Issues)
- New runtime scripts: `resolve_config.py`, `memlog.py`
- Directory: `src/` → `skills/`, flat skill layout
- Migration: run `/l3io-util-cleanup migrate-state` before using any PM skill

### Commit convention

All commits signed (`-s` DCO). Breaking structural changes use `feat!` scope. No external project references in any commit message, comment, or changelog entry.

---

## No-Avanade Rule

Zero references to any external organization in: code, comments, docstrings, commit messages, CHANGELOG, this spec, or any generated file. When copying scripts, strip or generalize any attribution to `bmad-extensions` / `l3io`.
