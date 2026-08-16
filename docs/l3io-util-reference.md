# l3io-util Reference

Artifact migration & housekeeping utilities for BMad projects.

## Overview

`l3io-util` provides one-time migrations and repeatable maintenance for BMad PM artifacts and status files. It is standalone — no orchestrator relationship. Run the single skill `/l3io-util-cleanup` with no argument for a **project health check** that scans for all known issues and proposes the right actions in priority order behind one confirmation, or pass a keyword to jump straight to a mode.

Skill: `/l3io-util-cleanup [command]`.

## Configuration

Config is resolved via `{project-root}/_bmad/scripts/resolve_config.py` — `core.*` for shared settings, `modules.l3io-util.*` for this module, and `modules.l3io-pm.*` for the artifact paths it reorganizes. No section is required; every value has a default.

Key settings (with defaults):

- `output_folder` — default: `{project-root}/_bmad-output`
- `implementation_artifacts` — default: `{output_folder}/implementation-artifacts`
- `planning_artifacts` — default: `{output_folder}/planning-artifacts`
- `harvest_exclude_dirs` — default: `[]`. Extra directories excluded from the `harvest-debt` source sweep, on top of the built-in exclusions (`node_modules`, `.git`, `dist`, `build`, `vendor`, `.venv`, `target`, `out`, and the artifact directories).

## Commands

### Diagnostic (read-only — never changes files)

| Command | What it does |
|---------|--------------|
| *(no argument)* | Project health check — runs all checks and, after one confirmation, executes the flagged actions in priority order. |
| `check` / `status` | Same scan as the health check, but reports the findings table and exits without changing anything. |
| `stats` | Project state dashboard — epic/sprint/story counts by status, backlog size by severity, last closed sprint/epic, calibration file state. |
| `backlog` | Lists the consolidated `backlog:` list grouped by severity. |

### One-time migrations (run in this order)

| Command | What it does |
|---------|--------------|
| `migrate-schema` | Upgrades an existing `sprint-status.yaml` to the current field schema — adds missing fields with zero/empty defaults, never overwrites existing values. |
| `split-status` | Splits a single `sprint-status.yaml` into the three-file layout (`sprint-status.yaml` active / `sprint-status-backlog.yaml` / `sprint-status-archived.yaml`). One-way; original preserved as `sprint-status.yaml.legacy`. |

### Ongoing maintenance (safe to repeat)

| Command | What it does |
|---------|--------------|
| `normalize` | Convenience — runs `reconcile-status` then `sort-status` in one confirmed pass. |
| `reconcile-status` | Fixes placement/structure drift: misplaced epics, nested per-epic `backlog:` arrays (flatten to the top-level list), stale non-`backlog` items, empty epic shells. |
| `sort-status` | Validates and applies sort order for epics, sprints, stories, and backlog items across all three files. Reorders only — never edits values. |
| `layout-cleanup` | Reorganizes flat artifact files into the `epic-XX/sprint-YY` folder hierarchy, reconciles references, verifies state. |

### Source & external sync

| Command | What it does |
|---------|--------------|
| `harvest-debt` | Sweeps the source tree for `bmad-defer:` deferred-shortcut markers and harvests new ones into the consolidated backlog. Language-generic, re-runnable (dedupes by `source`). Report-only by default; merge is confirmed. |
| `update-ai-rules` | Updates AI instruction files (`CLAUDE.md`, `.github/copilot-instructions.md`, `GEMINI.md`, `AGENTS.md`, `.cursorrules`, …) that reference the legacy single `sprint-status.yaml` to document the three-file split layout. Also auto-invoked after `split-status`. |

### Setup & housekeeping

| Command | What it does |
|---------|--------------|
| `setup` / `configure` / `install` | Registers the `l3io-util` module config for the project. |
| `clean-legacy` | Removes `*.yaml.legacy` and `*.yaml.v1` migration/calibration backup files after confirmation. |
| `rename-active` | Renames `sprint-status-active.yaml` → `sprint-status.yaml` (the health check runs this automatically when the old naming is found). |
| `help` / `?` | Prints the command list and exits — no project scan. |

## Project Health Check

The default mode runs nine read-only checks, prints a findings table (✓ pass / ⚠ flagged), and — unless invoked as `check`/`status` — proposes the flagged actions in a fixed priority sequence behind a single confirmation:

`rename-active → migrate-schema → split-status → reconcile-status → layout-cleanup → sort-status → harvest-debt → update-ai-rules → clean-legacy`

Each executed action runs its full mode (dry-run + verify still shown); per-mode confirmations are suppressed since the user already confirmed. If any action fails, the sequence stops and reports.

## Safety Rules

- Dry-run first — the full plan is shown before any file changes.
- Never overwrite an existing destination; on conflict, keep the source and record it.
- Move files, never edit their contents (layout cleanup); status-file modes re-parse YAML after every write and restore the original on any parse failure.
- Reference updates only auto-apply for unambiguous single-target matches; ambiguous references are recorded for manual review.

## Target Folder Structure

```
{implementation_artifacts}/epic-{EE}/sprint-{SS}/stories/{story-key}.md
{implementation_artifacts}/epic-{EE}/sprint-{SS}/closure/...
{implementation_artifacts}/epic-{EE}/sprint-{SS}/tests/...
{implementation_artifacts}/epic-{EE}/epic-closure/...
{planning_artifacts}/epic-{EE}/[sprint-{SS}/]...
```

`EE`/`SS` are zero-padded two-digit values. See [architecture](architecture.md) for the artifact conventions the PM orchestrators enforce and this module migrates toward.
