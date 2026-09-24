# l3io-util Reference

Project state diagnostics, progress reporting, and housekeeping utilities for BMad projects.

## Overview

`l3io-util` provides project state diagnostics, the plan-aware progress dashboard, one-time
migrations, and repeatable maintenance for BMad PM artifacts and state files. It is
standalone — no orchestrator relationship. Run the single skill `/l3io-util-doctor` with no
argument for a **project health check** that scans for all known issues and proposes the
right actions in priority order behind one confirmation, or pass a keyword to jump straight
to a mode.

Skill: `/l3io-util-doctor [command]`.

> **Renamed in 2.1.0.** This skill was `l3io-util-cleanup` through 2.0.x. "Cleanup"
> described about three of its modes, while the default behavior is a
> diagnose-report-repair health check. The deprecated `/l3io-util-cleanup` forwarder has
> been **removed on `main`** and ships in the next release — it is still present in 2.5.1,
> the current release. See [Upgrading](upgrading.md). Update any scripts or docs that still
> invoke the old name.

## Configuration

Config is resolved via `{project-root}/_bmad/scripts/resolve_config.py` — `core.*` for shared settings, `modules.l3io-util.*` for this module, and `modules.l3io-pm.*` for the artifact paths it reorganizes. No section is required; every value has a default.

**Self-installs `pm-status.py` at activation**, before dispatching to any mode (skipping only for `help`/`?`). This skill is the documented post-`quick-update` entry point, so it cannot assume some other skill has already refreshed the installed copy at `{project-root}/_bmad/scripts/pm-status.py` — several of its modes invoke it directly, and a stale copy fails those calls with an opaque argparse error rather than one that points at the real cause. The install compares bytes and reinstalls on any difference, refusing only to overwrite a strictly newer copy — the same content-guarded, non-downgrading self-install the PM skills use.

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
| `stats` (aliases `backlog`, `issues`) | Plan-aware progress dashboard — renders the phase → epic → sprint → story hierarchy with per-status dwell times and stuck-item flags, a live-view hint, and (per affected epic) the stale-lock `clear-lock` remedy, then appends backlog size by severity, last closed sprint/epic, and calibration file state. Delegates the state walk to `pm-status.py report` rather than duplicating it; falls back to counts only when `pm-status.py` is not installed yet. Archived epics count toward phase denominators but are listed only with `--all`. `/l3io-pm-help progress` forwards here rather than rendering its own copy of the tree. See [l3io-pm reference § Progress Reporting](l3io-pm-reference.md#progress-reporting). Step ST4 then lists the consolidated `backlog:` list per item, grouped by severity — items carry a `kind` — `defect` (the default, and assumed when the field is absent) plus `spec-change` and `spec-proposal`, which spec sync files and `triage`'s spec pass resolves. The `backlog` and `issues` aliases land here and always print that table; it was a separate mode until it was folded in, since it made the same single `list-issues --all` call `stats` already makes. |
| `check-deps` | Verifies every BMad skill this package dispatches resolves in this project, reports deprecated shims still in use, and names optional dependencies whose phases will self-skip. Read-only. |
| `check-pm-status` | Reports whether the installed helper script at `{project-root}/_bmad/scripts/` is current, stale, or absent, by comparing its `--version` output against this doctor's `module_version`. Used by `l3io-pm-help` at activation to warn about a stale copy; also runnable directly. Read-only. |

### One-time migrations (run in this order)

| Command | What it does |
|---------|--------------|
| `migrate-schema` | Upgrades an existing `sprint-status.yaml` to the current field schema — adds missing fields with zero/empty defaults, never overwrites existing values. |
| `split-status` | Splits a single `sprint-status.yaml` into the three-file layout (`sprint-status.yaml` active / `sprint-status-backlog.yaml` / `sprint-status-archived.yaml`). One-way; original preserved as `sprint-status.yaml.legacy`. |
| `migrate-state` | Makes a legacy project usable by the PM skills again — migrates a legacy state layout (flat `sprint-status.yaml`, or legacy per-epic `_bmad/state/`) to the sharded state tree. The source is renamed to `.legacy`, never deleted. A migration that would move nothing is refused rather than run. |
| `bootstrap-state` | Creates state nodes from story `.md` artifacts — for projects whose stories were created via the legacy `bmad-create-story` without going through `l3io-pm-plan`. Bootstrapped sprints and epics are marked `origin: inferred`. Never overwrites existing state nodes; safe to repeat. |
| `migrate-adrs` | Moves ADRs from the old per-epic home (`{implementation_artifacts}/epic-*/arch/`) to `{project-root}/docs/adr/`, the one ADR home (ADR-0005). Renumbers a colliding ADR only inside its own epic's artifacts. Plans first, confirms, then commits once. |

### Ongoing maintenance (safe to repeat)

| Command | What it does |
|---------|--------------|
| `reconcile-status` | Fixes placement/structure drift: misplaced epics, nested per-epic `backlog:` arrays (flatten to the top-level list), stale non-`backlog` items, empty epic shells. |
| `sort-status` | Read-only. Validates zero-padded naming (`epic-{nnn}/`, `sprint-{nn}/`, `E{nnn}-S{nn}-{nnn}.yaml`) in the sharded state tree and reports misnamed entries. Performs no reordering and applies no fixes — ordering itself cannot drift under the sharded layout, since each node is its own file and zero-padded names already make directory-listing order the correct order. |
| `triage` | Audits the backlog and resolves findings that are already fixed — confirms every write, including when the health check runs it. Also carries the **spec pass**: every open `spec-change` and `spec-proposal` item is shown with its commit diff or proposal file and confirmed, rejected, or skipped one at a time. Rejecting reverts the spec edit, resolves the item `wontfix`, and refiles the drift as a code fix at its original severity; skipping leaves it open for Check 18 to flag once a later commit builds on it. |
| `layout-cleanup` | Reorganizes flat artifact files into the `epic-XX/sprint-YY` folder hierarchy, reconciles references, verifies state. |
| `redrive` | Rebuilds the `scope` and `fix` calibration components from the story nodes on disk — repairs samples poisoned by a fixed defect that once stored `fix_iterations` as a string and misclassified them as `backout` instead of `exact`. Backs up the calibration file first (only if no backup already exists); `closure`, `orchestration`, and `token_mix` are untouched. Safe to run repeatedly. |

### Source & external sync

| Command | What it does |
|---------|--------------|
| `harvest-debt` | Sweeps the source tree for `bmad-defer:` deferred-shortcut markers and harvests new ones into the consolidated backlog. Language-generic, re-runnable (dedupes by `source`). Report-only by default; merge is confirmed. |
| `update-ai-rules` | Rewrites any reference to a legacy state layout (flat `sprint-status*.yaml`, the three-file split, or `_bmad/state/`) in the project's AI instruction files (`CLAUDE.md`, `.github/copilot-instructions.md`, `GEMINI.md`, `AGENTS.md`, `.cursorrules`, …) so they describe the current sharded state tree. Creates the **currently running** AI system's instruction file if it does not exist; never creates one for another AI system. Also auto-invoked after `split-status`. |

### BMad customization layer — specified, not shipped

There is **no `overlay` keyword** on `/l3io-util-doctor`. The mode was specified and then held
back, because `skills/l3io-util-doctor/assets/overlays/` ships no overlay TOML: all three of its
actions (`list`, `diff`, `verify`) would report "nothing ships yet" by construction. Its full
contract is kept as `skills/l3io-util-doctor/assets/overlays/overlay-mode.md`, beside the
directory it describes, and Phase 3 of the customization-layer design restores the keyword along
with the content.

**Nothing in this package ever writes `{project-root}/_bmad/custom/`.** That space belongs to
the end user, and BMad Builder is explicit that there is no supported pattern for a module to
write into it. The specified `diff` action stages a file under `{implementation_artifacts}/`
and **prints one `cp` command** for you to run yourself — placing the file is the act the mode
exists not to perform. You choose the scope by choosing the filename:
`_bmad/custom/<skill>.toml` is the committed team layer, `_bmad/custom/<skill>.user.toml` is
gitignored. If that upstream constraint is ever lifted, it changes by ADR, not quietly.

### Setup & housekeeping

| Command | What it does |
|---------|--------------|
| `setup` / `configure` / `install` | Registers the `l3io-util` module config for the project. |
| `clean-legacy` | Removes migration backup files and directories after confirmation: `*.yaml.legacy` files, the `state/pm-calibration.yaml.v1` calibration schema backup (beside the live calibration file, not under `_bmad/`), `_bmad/pm-calibration.yaml.legacy`, the `_bmad/state.legacy/` directory, and the `_bmad/migration-backup/` directory. |
| `help` / `?` | Prints the command list and exits — no project scan. |

## `pm-status.py` subcommands this skill runs

The doctor self-installs `pm-status.py` at activation (above) because its modes call it
directly. These are the subcommands they invoke; the authoritative signature for each one is
in the [l3io-pm reference](l3io-pm-reference.md), which documents the whole CLI.

| Subcommand | Used by | For |
|---|---|---|
| `report` | `stats` | The state walk behind the progress dashboard — the tree, dwell times and stuck flags are rendered from its output rather than duplicated here. |
| `list-issues` | `stats`, `triage` | Reads the backlog, whole (`--all`) or filtered by `--kind` for the spec pass. |
| `audit-issues` | `triage`, the health check | The backlog integrity audit whose findings `triage` then resolves. |
| `resolve-issue` | `triage` | Closes an item that is already fixed, with a `--resolution` and a `--ref`. |
| `repair-issue` | `triage` | `unschedule`, `reopen`, `link` and `reseed` repairs for the findings the audit reports. |
| `append-issue` | `migrate-state` | Files a migration finding into the backlog rather than dropping it. |
| `import-node` | `migrate-state`, `bootstrap-state` | Creates a missing state node from a migration record; idempotent by skip (an existing node is left exactly as-is, no event appended). |
| `verify` | `migrate-state`, `bootstrap-state` | Reads a migrated or bootstrapped node back and confirms it landed. |
| `set-status` | `migrate-state`, `bootstrap-state` | The single atomic status write; these modes never edit a state YAML by hand. |
| `set-field` | `bootstrap-state` | Sets an arbitrary field on an existing node; refuses `completion_evidence.tests_passing` and other derived fields outright (exit 2). Used to fill `title` on bootstrapped epics. |
| `clear-lock` | `stats` | The stale-lock remedy `stats` prints per affected epic. |
| `calibration` | `redrive` | `redrive` rebuilds the `scope` and `fix` components through it. |
| `dispatch` | `triage` | Opens and closes the dispatch record for a subagent the mode fans out to. |

## Project Health Check

The default mode runs nineteen numbered read-only checks (Checks 1–19, plus 2b and 2c), prints a findings table (✓ pass / ⚠ flagged), and — unless invoked as `check`/`status` — proposes the flagged actions in a fixed priority sequence behind a single confirmation:

`rename-active → rename-epic-dirs → migrate-schema → split-status → migrate-state → bootstrap-state → reconcile-status → layout-cleanup → sort-status → harvest-debt → migrate-adrs → triage → update-ai-rules → redrive → untrack-locks → clean-legacy`

Three of those actions are **not modes** and have no keyword — the health check runs each one
inline, from the check that detects it:

- `rename-active` (Check 1) renames `sprint-status-active.yaml` → `sprint-status.yaml`, content
  unchanged. It refuses on a conflict and renames back if the result does not parse.
- `rename-epic-dirs` (Check 10) renames legacy two-digit `epic-{nn}/` artifact directories to
  the three-digit `epic-{nnn}/` form, skipping any whose destination already exists.
- `untrack-locks` (Check 14) makes sure `state/.gitignore` has a `*.lock` line, then runs
  `git rm --cached` over the tracked `*.lock` files under the state root. The files stay on
  disk, and the removal is staged for your next commit.

Each executed action runs its full mode (dry-run + verify still shown); per-mode confirmations are suppressed since the user already confirmed — except `triage`, which keeps its own confirmations, because every triage action resolves or rewrites backlog items the single confirmation did not show item by item. If any action fails, the sequence stops and reports.

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

`EE` is a zero-padded three-digit epic value (`epic-{nnn}`); `SS` is a zero-padded two-digit sprint value (`sprint-{nn}`). See [architecture](architecture.md) for the artifact conventions the PM orchestrators enforce and this module migrates toward.
