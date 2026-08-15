---
name: l3io-util-cleanup
description: Migration utilities. Use when the user needs to reorganize legacy flat BMad artifact outputs into the structured epic/sprint folder layout, migrate sprint-status.yaml to the current field schema, split it into the three-file layout, reconcile epic placement across the three split files and normalize the backlog to a flat list, harvest deferred-shortcut code markers into the backlog, validate and sort the ordering of epics and sprints in the status files, or update AI system instruction files with the current status file layout. Run without arguments for an auto-diagnostic that scans project state and proposes the right actions.
---

# Artifact Layout Cleanup

## Overview

Migration and housekeeping utilities for BMad artifacts.

**Default behavior (no argument or unrecognized text):** Runs a project health check — scans for all known issues, reports findings in a priority table, and proposes the right actions in the correct execution order. One confirmation runs them all.

Modes (pass as argument to skip directly to that mode):

**Diagnostic (read-only)**
- **`check` / `status`:** Read-only health check — same diagnostic scan as the default but prints the findings table and exits without prompting to make changes.
- **`stats`:** Project state dashboard — counts of epics, sprints, and stories by status, backlog size by severity, and last closed sprint/epic. No files changed.
- **`backlog`:** Lists all items in the consolidated `backlog:` list in a readable table grouped by severity. No files changed.

**One-time migrations (run in this order)**
- **`migrate-schema`:** Upgrades an existing `sprint-status.yaml` to the current field schema — adds missing fields with zero/empty defaults, never overwrites existing values.
- **`split-status`:** Splits a single `sprint-status.yaml` into the three-file layout the PM skills now use — `sprint-status.yaml` (active/in-progress epics), `sprint-status-backlog.yaml`, `sprint-status-archived.yaml` — partitioning every epic/sprint by status. One-time migration; the original is preserved as `sprint-status.yaml.legacy`. (Run `migrate-schema` first if the file predates the current field schema.)
- **`migrate-state`:** Migrates from old sprint-status*.yaml layout to new _bmad/state/ per-epic layout. Preserves originals as .legacy files.

**Ongoing maintenance (safe to repeat)**
- **`normalize`:** Convenience shortcut — runs `reconcile-status` then `sort-status` in one confirmed pass. Use for routine maintenance instead of running two commands separately.
- **`reconcile-status`:** Audits the three split status files for placement and structure issues: epics in the wrong file for their `status`, nested per-epic `backlog:` arrays that should be flattened into the consolidated top-level list, stale backlog items whose status is no longer `backlog`, and empty epic shells in the backlog file. Dry-run first; confirms before writing. Safe to run at any time.
- **`sort-status`:** Validates that epics, sprints, stories, and backlog items in all three split status files are in the expected sort order, and applies sorting if needed. Dry-run first; confirms before writing. Safe to run at any time — never edits field values, only reorders nodes.
- **`layout-cleanup`:** Runs only the artifact layout reorganization (the original default behavior) — reorganizes flat artifact outputs into the structured epic/sprint folder hierarchy, reconciles references, verifies state consistency.

**Source & external sync**
- **`harvest-debt`:** Greps the whole source tree for `bmad-defer:` deferred-shortcut markers (the comment crumbs developers and dev subagents leave when they take an intentional simplification) and harvests them into the consolidated `backlog:` list so deferrals do not rot into "later means never." Language-generic — recognizes the comment syntax of every common language. Re-runnable: dedupes against already-harvested markers. Report-only by default; backlog merge is confirmed. Respects `harvest_exclude_dirs` in the `l3io-util` config section for additional exclusions beyond the built-in list.
- **`update-ai-rules`:** Scans for AI system instruction files in the project (`CLAUDE.md`, `.github/copilot-instructions.md`, `GEMINI.md`, `AGENTS.md`, `.cursorrules`, and others) and updates any references to the legacy `sprint-status.yaml` to document the current three-file split layout. For files that already exist: updates existing references. For the currently running AI system's file if it does not exist: creates it with a status layout section. Never creates files for other AI systems. Also auto-invoked after a successful `split-status` run. Safe to run repeatedly.

**Setup & housekeeping**
- **`clean-legacy`:** Removes `.yaml.legacy` migration backup files and `.v1` calibration backup files left behind by one-time migration commands. Dry-run first; confirms before deleting. Safe to run once migrations have been verified.
- **`rename-active`:** Renames `sprint-status-active.yaml` → `sprint-status.yaml`. Rarely needed directly — the health check detects and runs this automatically when the old naming is found.

**One-time use (layout cleanup):** Designed to be run once per project. Running again after a successful cleanup produces zero moves (everything already placed) or conflicts (for new flat files added since the first run).

## Conventions

- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## On Activation

**Recognized keywords** — if the user's argument exactly matches any of these, skip directly to that mode:

| Keyword | Mode |
|---|---|
| `help` or `?` | Print the command list below and exit — no project scan. |
| `check` or `status` | [Project Health Check](#project-health-check) (read-only — scan only, no changes) |
| `stats` | [Stats Mode](#stats-mode) (read-only — project state dashboard) |
| `backlog` | [Backlog Mode](#backlog-mode) (read-only — list consolidated backlog items) |
| `normalize` | [Normalize Mode](#normalize-mode) — reconcile-status then sort-status in one confirmed pass |
| `layout-cleanup` | [Execution Sequence](#execution-sequence) (layout reorganization only) |
| `migrate-schema` | [Schema Migration Mode](#schema-migration-mode) |
| `split-status` | [Split Status Mode](#split-status-mode) |
| `harvest-debt` | [Harvest Debt Mode](#harvest-debt-mode) |
| `reconcile-status` | [Reconcile Status Mode](#reconcile-status-mode) |
| `sort-status` | [Sort Status Mode](#sort-status-mode) |
| `rename-active` | [Rename Active Mode](#rename-active-mode) |
| `update-ai-rules` | [Update AI Rules Mode](#update-ai-rules-mode) |
| `clean-legacy` | [Clean Legacy Mode](#clean-legacy-mode) — remove migration backup files |
| `migrate-state` | [Migrate State Mode](#migrate-state-mode) |
| `setup`, `configure`, `install` | Load `assets/module-setup.md`, then continue to [Project Health Check](#project-health-check) |

**Everything else** (no argument, unrecognized text, or a natural-language description) → skip to [Project Health Check](#project-health-check).

**Help output** — when `help` or `?` is passed, print exactly this and exit:

```
l3io-util-cleanup — Artifact & Status File Utilities
====================================================
Usage: /l3io-util-cleanup [command]

Diagnostic (read-only)
  (no argument)      Project health check — scan and propose all needed actions
  check / status     Read-only health check — report findings, no changes
  stats              Project state dashboard — epic/sprint/story/backlog counts
  backlog            List consolidated backlog items grouped by severity

One-time migrations (run in this order)
  migrate-schema     Add missing fields to sprint-status.yaml (zero/empty defaults)
  split-status       Split sprint-status.yaml into 3-file layout (active/backlog/archived)
  migrate-state      Migrate sprint-status*.yaml to new _bmad/state/ per-epic layout

Ongoing maintenance (safe to repeat)
  normalize          Reconcile then sort all status files in one pass
  reconcile-status   Fix misplaced epics, nested backlogs, stale items, empty shells
  sort-status        Sort epics, sprints, stories, and backlog items in all status files
  layout-cleanup     Reorganize flat artifact files into epic/sprint folder structure

Source & external sync
  harvest-debt       Sweep source for bmad-defer: markers and harvest into backlog
  update-ai-rules    Update AI instruction files to reference the 3-file status layout

Setup & housekeeping
  setup              Register l3io-util module config for this project
  clean-legacy       Remove .legacy and .v1 migration backup files after confirmation
  rename-active      (Rarely needed) Rename sprint-status-active.yaml → sprint-status.yaml;
                     the health check detects and runs this automatically when needed.

Run without arguments to let the health check decide what's needed.
```

If `{project-root}/_bmad/config.yaml` does not have an `l3io-util` section, load `assets/module-setup.md` to register the module first.

Load config from `{project-root}/_bmad/config.yaml` and `{project-root}/_bmad/config.user.yaml` (root level and `l3io-util` section). Resolve:
- `implementation_artifacts`
- `planning_artifacts`
- `output_folder`

If `implementation_artifacts` is not set, default to `{output_folder}/implementation-artifacts`.

## Project Health Check

The default mode — runs when no recognized keyword is passed, or when `check`/`status` is passed. Scans the project and reports what needs attention in a structured table. When not in read-only mode (`check`/`status`), proposes the ordered set of actions and executes them after a single confirmation.

### Step HC1 — Load config

Load config same as described above under On Activation.

### Step HC2 — Scan (8 checks, read-only)

Run all checks. No files are changed at this step.

**Check 1 — Status file naming**
Does `{implementation_artifacts}/sprint-status-active.yaml` exist?
- Yes → flag `rename-active` · Priority: Critical (must run before any other status-file action)
- No → ✓

**Check 2 — Status file layout**
Do `sprint-status-backlog.yaml` OR `sprint-status-archived.yaml` exist in `{implementation_artifacts}/`?
- Neither exists, but `sprint-status.yaml` is present with content that includes done or backlog epics → flag `split-status` · Priority: High
- Neither exists and no `sprint-status.yaml` → new project, no status-file action needed
- At least one split file exists → split layout in use, ✓

**Check 2b — State layout migration**
Does `{project-root}/_bmad/state/active/` exist?
- No, but old sprint-status files (split or single) exist in `{implementation_artifacts}/` → flag `migrate-state` · Priority: High (runs after `split-status` if both are flagged)
- Yes → ✓

**Check 3 — Status file schema**
For each present status file, spot-check the first epic node and first sprint node for missing required fields (the full field list is in Schema Migration Mode Step M2). If any required field is absent, the full `migrate-schema` analysis is needed.
- Gaps detected → flag `migrate-schema` · Priority: Medium (run before `split-status` if both are needed)
- No gaps → ✓

**Check 4 — Artifact layout**
Scan the top level of `{implementation_artifacts}` and `{planning_artifacts}` for flat classifiable files (story files matching heuristic 1, sprint/epic closure files matching heuristics 2–3, test files matching heuristic 4, misplaced planning docs matching heuristic 5 — all from [File Classification Heuristics](#file-classification-heuristics)).
- Flat classifiable files found → flag `layout-cleanup` · Priority: Medium · note count
- None → ✓

**Check 5 — Status file ordering**
If split layout exists, run the ordering validation from Sort Status Mode Step SO2 on each present split file.
- Out-of-order nodes found → flag `sort-status` · Priority: Low
- In order → ✓

**Check 6 — Deferred code markers**
Run the `bmad-defer:` grep from Harvest Debt Mode (Step H2 grep command). Dedupe against the existing `backlog:` list (Step H3 logic). Count new (unharvested) markers.
- New markers found → flag `harvest-debt` · Priority: Low · note count
- None or all already harvested → ✓

**Check 7 — AI instruction references**
Run the scan from Update AI Rules Mode Step AR1 across all well-known instruction file locations.
- Stale `sprint-status.yaml` references found → flag `update-ai-rules` · Priority: Low · list files
- All current or absent → ✓

**Check 8 — Status file placement and backlog structure**
Only runs if the split layout is present. Parse all three split files and check:
1. Any epic whose placement file does not match its `status` (e.g., `status: done` in `sprint-status.yaml`)?
2. Any nested per-epic `backlog:` arrays inside `epics[N].backlog:` in any of the three files (should be in the flat top-level `backlog:` list only)?
3. Any items in the top-level `backlog:` list with `status` other than `backlog` (stale resolved/promoted items)?
4. Any epic shells in `sprint-status-backlog.yaml` with an empty or absent `sprints:` list where that epic is already in-progress in `sprint-status.yaml` (empty shells with no remaining backlog sprints)?
- Any issue found → flag `reconcile-status` · Priority: High · note count per category
- Split layout absent → skip (not applicable until after `split-status`)
- No issues → ✓

**Check 9 — Migration backup files**
Scan `{implementation_artifacts}/` for `*.yaml.legacy` files (e.g., `sprint-status.yaml.legacy`) and `{project-root}/_bmad/` for `*.yaml.v1` calibration backups (e.g., `pm-calibration.yaml.v1`).
- Any found → flag `clean-legacy` · Priority: Low · note count
- None → ✓

### Step HC3 — Report findings

Print the health check table. Use ✓ for passing checks, ⚠ for flagged items:

```
PROJECT HEALTH CHECK — {implementation_artifacts}
================================================================
Check                           Status                         Action
----------------------------------------------------------------
Status file naming              ⚠ sprint-status-active.yaml    rename-active
Status file layout              ✓ Split layout in use          —
Status file schema              ✓ All fields current           —
Status placement & backlog      ⚠ 1 misplaced epic, 3 nested  reconcile-status
Artifact layout                 ⚠ 3 flat file(s) detected     layout-cleanup
Status file ordering            ✓ All sorted                   —
Deferred code markers           ⚠ 2 new marker(s)             harvest-debt
AI instruction references       ✓ Current                      —
Migration backup files          ⚠ 1 .legacy file found         clean-legacy
================================================================
```

If flagged items exist, append the recommended execution sequence (only flagged actions shown, in priority order):
```
Recommended actions (in order): rename-active → reconcile-status → layout-cleanup → harvest-debt
```

If nothing is flagged:
```
✓ Project is healthy — no actions needed.
```

### Step HC4 — Exit if read-only

If invoked with `check` or `status`: print the report above and exit. No further steps.

### Step HC5 — Propose and confirm

If no items are flagged: print "✓ Nothing to do." and exit.

Otherwise ask:
```
Run {N} recommended action(s) in sequence?
  Y — run all ({action_list})
  n — exit, no changes
```

If `n`: print "Exiting — no changes made." and exit.

### Step HC6 — Execute in order

Run each approved action in this fixed priority sequence (skip any that were not flagged):

1. `rename-active`
2. `migrate-schema`
3. `split-status`
4. `migrate-state`
5. `reconcile-status`
6. `layout-cleanup`
7. `sort-status`
8. `harvest-debt`
9. `update-ai-rules`
10. `clean-legacy`

Before each action, print a separator header:
```
─── Running: {action-name} ──────────────────────────────────
```

Each action runs its full mode implementation from its own section. **Suppress the per-mode confirmation prompts** — the user already confirmed in HC5; proceed as if they answered yes at each mode's own confirm step. The per-mode dry-run output and verify steps still run and are shown.

If any action fails (exits with FAILED), stop and report — do not run remaining actions.

### Step HC7 — Final summary

```
HEALTH CHECK COMPLETE
================================================================
  Ran:     {comma-separated list with ✓ or ✗ per action}
  Clean:   {comma-separated list of checks that passed with ✓}
================================================================
{overall status line}
```

If all actions succeeded: "Project is now healthy."
If any action failed: "One or more actions failed — see output above for details."

---

## Target Folder Structure

```
{implementation_artifacts}/epic-{EE}/sprint-{SS}/stories/{story-key}.md
{implementation_artifacts}/epic-{EE}/sprint-{SS}/closure/...
{implementation_artifacts}/epic-{EE}/sprint-{SS}/tests/...
{implementation_artifacts}/epic-{EE}/epic-closure/...
{implementation_artifacts}/epic-{EE}/tests/...
{planning_artifacts}/epic-{EE}/...
{planning_artifacts}/epic-{EE}/sprint-{SS}/...
```

`EE` and `SS` are zero-padded two-digit values (`01`, `02`, etc.).

## Safety Rules

- Dry-run first — show full cleanup plan before changing any files
- Never overwrite an existing destination file
- If destination exists: keep source in place, record conflict
- Preserve file contents exactly — move only, no edits
- Reference updates: auto-update only exact old-path matches that map to one known moved file; if ambiguous, record for manual review — never auto-update ambiguous references

## File Classification Heuristics

1. **Story files** (flat implementation root): regex `^([0-9]+)-[0-9]+.*\.md$` — epic from first capture group; default sprint = `01` unless user provides mapping. Move to: `epic-{EE}/sprint-{SS}/stories/{story-key}.md`
2. **Sprint closure files** (flat implementation root): patterns `epic-*-sprint-*-retro-*.md`, `*-sprint-*-adversarial-*.md`, `*-sprint-*-redteam-*.md`, `*-sprint-*-clean-release-*.md`, `*-sprint-*-ux-review-*.md`, `*-sprint-*-arch-drift-*.md`. Move to: `epic-{EE}/sprint-{SS}/closure/{filename}`
3. **Epic closure files** (flat implementation root): patterns `epic-*-adversarial-*.md` (epic-scoped), `epic-*-redteam-*.md`, `epic-*-arch-drift-*.md`, `epic-*-functional-completeness-*.md`, `epic-*-clean-release-*.md`, `epic-*-ux-review-*.md`. Move to: `epic-{EE}/epic-closure/{filename}`
4. **Test evidence files** (flat roots): patterns `*qa*.md`, `*test*.md`, `*verification*.md`. Sprint-scoped → `epic-{EE}/sprint-{SS}/tests/`. Epic-scoped → `epic-{EE}/tests/`.
5. **Planning artifacts** (misplaced under `{planning_artifacts}` or `{implementation_artifacts}`): covers brainstorming, architecture, research, UX specs, and requirements docs — never story or epic tracking files (those are implementation artifacts). Classify by filename pattern:
   - **Architecture**: `*architecture*`, `*arch-spec*`, `*system-design*`, `*tech-design*`
   - **Requirements / PRD**: `*requirements*`, `*prd*`, `*brief*`, `*spec*` (excluding story files matched by heuristic 1)
   - **UX spec**: `*ux-spec*`, `*ux-design*`, `*wireframe*`, `*mockup*`, `*ui-spec*`
   - **Research / spike**: `*research*`, `*spike*`, `*investigation*`, `*discovery*`
   - **Brainstorming**: `*brainstorm*`, `*ideation*`, `*mind-map*`
   Determine placement scope from the filename: if `sprint-{SS}` or `sprintSS` is present → `{planning_artifacts}/epic-{EE}/sprint-{SS}/{filename}`; otherwise → `{planning_artifacts}/epic-{EE}/{filename}`. If epic cannot be inferred from the filename, ask for a mapping before proceeding.
6. **Unknown files**: leave in place; record as "unclassified".

## Execution Sequence

### Step 1 — Scan and Classify

Recursively scan **all files** under `{implementation_artifacts}` and `{planning_artifacts}` — including any subdirectories at any depth (flat roots, unusual subfolders, nested paths). Do not limit the scan to top-level files.

For each file found, determine whether it is already correctly placed:
- A file is **correctly placed** if its current path exactly matches the target path the heuristics would produce. Skip it — record as `already-placed`.
- A file is **misplaced** if it is classifiable but lives outside its correct target location (flat root, wrong epic/sprint folder, unusual subfolder, etc.). Add it to the move map.
- A file is **unclassified** if no heuristic can determine its destination. Leave in place and record.

Apply classification heuristics to all misplaced files. Build move map: source path → destination path + classification.

For files where epic/sprint cannot be reliably determined from filename alone, ask for a mapping before proceeding to Step 2.

### Step 2 — Dry-Run Table

Print the full move plan:

```
DRY RUN — Artifact Cleanup
===========================================================
Source                          → Destination                         Class            Status
-----------------------------------------------------------
{source-path}                   → {dest-path}                        story            move
{source-path}                   → {dest-path}                        sprint-closure   move
{source-path}                   → {dest-path}                        story            conflict (dest exists)
{source-path}                   → (already correct)                  story            already-placed
{source-path}                   → (no destination found)             —                unclassified
===========================================================
Summary: {move-count} to move, {already-placed-count} already correct, {conflict-count} conflicts, {unclassified-count} unclassified
```

### Step 3 — Confirmation

Ask: "Proceed with {move-count} file moves? Conflicts and unclassified files will not be touched."

If no: print "Cleanup cancelled — no files changed." and exit.

### Step 4 — Create Directories

Create all required destination directories that do not exist yet.

### Step 5 — Execute Moves

Move each confirmed file to its destination. On conflict (destination already exists): skip, record. Log each move.

### Step 6 — Reference Reconciliation

Search reference-holding files: the split status files (`sprint-status.yaml`, `sprint-status-backlog.yaml`, `sprint-status-archived.yaml`) or legacy `sprint-status.yaml.legacy` (whichever are present), story `.md` files, planning docs, closure and test reports. For each moved file, replace exact old-path occurrences with the new path. If one old path could match multiple targets or context is ambiguous, record for manual review — do not auto-update.

### Step 7 — State Verification

Verify post-move state:
- Epic and sprint folder names are zero-padded (`epic-01` not `epic-1`, `sprint-02` not `sprint-2`)
- Story files under `stories/`, closure outputs under `closure/`, tests under `tests/`
- Check story state entries in whichever status files are present (split layout or legacy `sprint-status.yaml`) for references to missing story files
- Flag any residual flat files that were not classified and remain in the root

**Ordering check (status files):** If the split layout exists (`sprint-status.yaml`, `sprint-status-backlog.yaml`, or `sprint-status-archived.yaml`), check their sort order:
- Epics ordered ascending by `id` (numeric) in each file
- Sprints ordered ascending by `id` (numeric) within each epic
- Stories ordered ascending by `key` (lexicographic) within each sprint
- Backlog items in `sprint-status-backlog.yaml` ordered by `epic` ascending (numeric; blank entries last), then `sprint`, then `key`

If any ordering issue is found, include it in the State Issues count and append to the summary:
```
Status file ordering: {N} issue(s) detected in {files} — run `/l3io-util-cleanup sort-status` to fix
```
If all files are in order, append:
```
Status file ordering: ✓ all files sorted correctly
```

### Step 8 — Deferred Work Files

For each epic that has conflicts, unclassified files, or manual-review reference items, write a consolidated deferred work file:

```
{implementation_artifacts}/epic-{EE}/cleanup-deferred.md
```

Format:
```markdown
# Cleanup Deferred Work — Epic {EE}
Generated: {date}

## Conflicts (destination already exists — not moved)
- `{source-path}` → `{dest-path}` [{classification}]

## Unclassified Files (no heuristic match — left in place)
- `{source-path}`

## Reference Updates Requiring Manual Review
- File: `{reference-file}` — old path `{old-path}` matched multiple targets or context was ambiguous
```

Omit any section that has no entries. If an epic has no deferred items, do not write the file.

If a `cleanup-deferred.md` already exists for an epic (from a prior run), append new findings under a dated `## Run {date}` heading rather than overwriting.

### Step 9 — Summary Report

Print:
```
DONE - Moved: N, Conflicts: N, Unclassified: N, Refs Updated: N, Ref Conflicts: N, State Issues: N
  Implementation root: {implementation_artifacts}
  Planning root:       {planning_artifacts}
  Deferred work files: {deferred_file_list} (or "none")
```

### Step 10 — Completeness Verification Loop

Maintain `{cleanup_iteration}` = 1 (incremented each time Step 1–8 runs).

After Step 8, recursively re-scan all files under `{implementation_artifacts}` and `{planning_artifacts}` (same full-depth scan as Step 1) for any remaining misplaced classifiable files — excluding known conflicts, already-placed files, and intentionally unclassified files recorded in the previous pass.

If no classifiable files remain: print `Cleanup complete — no residual files found after {cleanup_iteration} pass(es).` and exit.

If classifiable files remain and `{cleanup_iteration}` < 4: announce the residual files found, then automatically loop back to Step 1 with only those files in scope. Increment `{cleanup_iteration}`.

If `{cleanup_iteration}` ≥ 4 and classifiable files still remain, halt:
```
Cleanup HALT — {residual_count} classifiable file(s) remain after {cleanup_iteration} passes.
Residual files: {residual_file_list}
These may require manual mapping or indicate ambiguous filenames the heuristics cannot resolve.
```
Present the residual list and wait for `{user_name}` guidance before exiting.

---

## Schema Migration Mode

Invoked with `migrate-schema` argument. Upgrades an existing `sprint-status.yaml` to the current field schema. Adds missing fields with zero/empty defaults. Never overwrites existing non-null values. Never guesses at values — only mechanical defaults (zero for numbers, empty for strings, `'unknown'` for enums).

### Default Values for Missing Fields

| Field type | Default |
|---|---|
| Numeric (`time_hours_low/high`, `tokens_k_min/max`, `man_hours_low/high`, `elapsed_hours`, `man_hours`, `fix_iterations`, `tests_passing`, `files_changed`) | `0` |
| Cost string (`cost_low`, `cost_high`) | `'$0.00'` |
| `classification` enum | `'unknown'` |
| `severity` enum | `'unknown'` |
| `source`, `description`, `goal` | `''` |
| Epic/sprint `title` | Derived mechanically: `'Epic {id}'` / `'Sprint {id}'` |
| `bugs_fixed` list | Omit block entirely when `fix_iterations` defaults to `0` |
| `closed`, `retrospective` | Omit — only present when the actual value is known |

### Migration Steps

**Step M1 — Load config and locate status files**

Load config (same as layout cleanup). Detect which layout is present:

1. If `{implementation_artifacts}/sprint-status-backlog.yaml` OR `{implementation_artifacts}/sprint-status-archived.yaml` exists → **split layout**: bind `{status_files}` to all present split files: `sprint-status.yaml`, `sprint-status-backlog.yaml`, `sprint-status-archived.yaml` (include only those that exist; also include `sprint-status-active.yaml` if present and `sprint-status.yaml` is absent, for backward compatibility).
2. Else if `{implementation_artifacts}/sprint-status.yaml` exists → **legacy single-file**: bind `{status_files}` = `[ sprint-status.yaml ]`.
3. Else: print `No status files found at {implementation_artifacts} — nothing to migrate.` and exit.

Steps M2–M7 operate on each file in `{status_files}`. The dry-run table (Step M3) groups all files; confirmation (Step M4) covers all at once.

**Step M2 — Analyze**

Parse each file in `{status_files}`. For each node — epic, sprint, story, backlog item — collect every field that is absent from the current schema. Build a change list: file + node path + field name + proposed default value.

Schema fields to verify (add if absent):

*Epic node:*
- `title` (derive: `'Epic {id}'`)
- `goal`
- `estimate` block: `time_hours_low`, `time_hours_high`, `tokens_k_min`, `tokens_k_max`, `cost_low`, `cost_high`, `man_hours_low`, `man_hours_high`
- `actual` block (only when `status: done`): `elapsed_hours`, `man_hours`

*Sprint node:*
- `title` (derive: `'Sprint {id}'`)
- `estimate` block: `time_hours_low`, `time_hours_high`, `tokens_k_min`, `tokens_k_max`, `cost_low`, `cost_high`, `man_hours_low`, `man_hours_high`
- `actual` block (only when `status: done`): `elapsed_hours`, `man_hours`

*Story node:*
- `title` (derive from story `.md` file's first heading if the file exists; otherwise `''`)
- `classification`
- `completion_evidence` block (only when `status: done`): `fix_iterations`, `tests_passing`, `files_changed`

*Backlog item node:*
- `source` (verify/add if absent)
- `severity` (verify/add if absent)
- `description` (verify/add if absent)

**Step M3 — Dry-run table**

```
SCHEMA MIGRATION DRY RUN — {status_files}
================================================================
File                          Node                              Field                Value
----------------------------------------------------------------
sprint-status.yaml            epics[01]                         title                'Epic 01'
sprint-status.yaml            epics[01]                         goal                 ''
sprint-status.yaml            epics[01]                         estimate.time_hours_low  0
sprint-status.yaml            epics[01].sprints[01]             title                'Sprint 01'
sprint-status.yaml            epics[01].sprints[01].stories[ST01]  classification    'unknown'
sprint-status-backlog.yaml    epics[02].backlog[BL-01]          source               ''
...
================================================================
Summary: {field_count} fields to add across {epic_count} epics,
         {sprint_count} sprints, {story_count} stories, {backlog_count} backlog items
         ({file_count} file(s) affected)
No existing values will be changed.
```

If `{field_count}` is 0 across all files: print `Status files are already current — no fields to add.` and exit.

**Step M4 — Confirm**

Ask: "Proceed with schema migration? Existing values will not be changed."

If no: print `Migration cancelled — no changes made.` and exit.

**Step M5 — Write**

Apply all changes to each file in `{status_files}`. Preserve the existing field order within each node; append new fields after existing ones in their parent node. New blocks (`estimate`, `actual`, `completion_evidence`) are appended as a whole after existing peer fields.

**Step M6 — Verify**

Re-parse each written file in `{status_files}` as YAML. If any file fails to parse, restore its original content and print:
```
FAILED — {file} is not valid YAML. Original restored. Parse error: {error}
```

**Step M7 — Report**

```
DONE — Schema migration complete.
  Fields added: {field_count}
  Files: {status_files}
```

---

## Split Status Mode

Invoked with `split-status` argument. Splits a single `sprint-status.yaml` into the
three-file layout the PM skills (`l3io-pm-execute`)
now read and write. One-time, one-way migration. The original is never deleted — it is
renamed to `sprint-status.yaml.legacy` as the rollback. All [Safety Rules](#safety-rules)
apply: dry-run first, never overwrite an existing destination, preserve node contents
exactly.

This is the same partition the PM skills perform automatically on first run when they find
only a legacy file (see their `references/status-files.md`); running it here is the explicit,
reviewed path.

### Target files

In `{implementation_artifacts}/`:
- `sprint-status.yaml` — `epics:` with `status: in-progress`.
- `sprint-status-backlog.yaml` — `epics:` = not-yet-started work; `backlog:` = consolidated deferred-issue list.
- `sprint-status-archived.yaml` — `epics:` with `status: done`.

### Placement rule (partition)

Granularity is **epic + sprint**; stories always travel inside their owning sprint node.

| Source node | Destination |
|---|---|
| Epic with `status: done` | `archived` — whole epic subtree, unchanged. |
| Epic with `status: in-progress` | `active` — epic node carrying only its `in-progress` and `done` sprints (with all their stories). |
| Backlog (not-yet-started) sprints of an in-progress epic | `backlog` — under an epic **shell** (`id`, `title`, `goal`, and a `sprints:` list of just those sprints). |
| Epic with `status: backlog` | `backlog` — whole epic subtree, unchanged. |
| Each item in any epic's nested `backlog:` array | `backlog` top-level `backlog:` list, flattened, each tagged with `epic:` (the owning epic id) and `sprint:` (the owning sprint id if the item names one, else `''`). |

A node lands in exactly one file. Files with no content are not written (a missing file is
treated as empty by the readers).

### Steps

**Step S1 — Load config and locate status file**

Load config (same as layout cleanup). Resolve `{status_file}` = `{implementation_artifacts}/sprint-status.yaml`. If absent, print:
```
sprint-status.yaml not found at {status_file} — nothing to split.
```
and exit. If any of the three target files already exists, print a conflict warning and exit
(the split has likely already been run); do not overwrite.

**Step S2 — Partition**

Parse `{status_file}`. Walk every epic, sprint, and nested `backlog:` array and assign each
node to `active`, `backlog`, or `archived` per the placement rule. Build the three in-memory
documents plus the flattened consolidated `backlog:` list.

**Step S3 — Dry-run table**

```
SPLIT STATUS DRY RUN — {status_file}
================================================================
Target file                       Epics  Sprints  Stories  Backlog
----------------------------------------------------------------
sprint-status.yaml                  {a_e}   {a_s}    {a_st}      —
sprint-status-backlog.yaml          {b_e}   {b_s}    {b_st}   {bl_count}
sprint-status-archived.yaml         {r_e}   {r_s}    {r_st}      —
================================================================
Original preserved as: sprint-status.yaml.legacy
No node contents are modified — placement only.
```

**Step S4 — Confirm**

Ask: "Proceed with the split? The original is kept as sprint-status.yaml.legacy."

If no: print `Split cancelled — no changes made.` and exit.

**Step S5 — Write**

Write each non-empty target document to its file. Then rename `{status_file}` →
`{status_file}.legacy` (rename, never delete).

**Step S6 — Verify**

Re-parse each written target file as YAML. Confirm every epic/sprint/story from the original
appears in exactly one target file and no node was dropped or duplicated. If any check fails,
restore by renaming `.legacy` back to `sprint-status.yaml`, remove the partial target files,
and print:
```
FAILED — {reason}. Original restored to sprint-status.yaml; target files removed.
```

**Step S7 — Report**

```
DONE — Split complete.
  Active:   {a_e} epics / {a_s} sprints / {a_st} stories
  Backlog:  {b_e} epics / {b_s} sprints / {b_st} stories / {bl_count} deferred items
  Archived: {r_e} epics / {r_s} sprints / {r_st} stories
  Original: {status_file}.legacy
```

**Step S8 — Post-split ordering validation**

After a successful split the nodes are placed correctly but may not be sorted within their files (the original file's order is preserved exactly during the split). Automatically run the ordering validation from [Sort Status Mode](#sort-status-mode) now:
- If all files are already in order: append `Ordering: ✓ all files sorted correctly` to the report and exit.
- If ordering issues are found: present the dry-run table (Step SO3) and ask: "Sort the {N} ordering issue(s) now?" If yes, proceed through Steps SO5–SO7. If no, print `Ordering issues recorded — run /l3io-util-cleanup sort-status to fix later.` and exit.

**Step S9 — AI Rules Update**

After the split (and optional sort), automatically run Step AR1 of [Update AI Rules Mode](#update-ai-rules-mode) to scan for AI instruction files that reference the old `sprint-status.yaml`. If any are found, display the findings and ask: "Update {N} AI instruction file reference(s) now?" If yes, proceed through Steps AR2–AR6. If no, print: `Run /l3io-util-cleanup update-ai-rules to update AI instruction files later.` and exit.

---

## Harvest Debt Mode

Invoked with `harvest-debt` argument. Sweeps the source tree for `bmad-defer:` deferred-shortcut
markers and harvests them into the consolidated `backlog:` list so intentional simplifications stay
visible instead of rotting into "later means never." Report-only by default; the backlog merge is a
separate confirmed step. All [Safety Rules](#safety-rules) apply — dry-run first, never overwrite,
never guess. Re-runnable: a marker already harvested is not added twice.

### The deferral marker contract (the shared source of truth)

A deferral marker is a single source-code comment in this form (the comment leader varies by
language; everything after `bmad-defer:` is the payload):

```
<comment-leader> bmad-defer: <what was simplified>. ceiling: <the limit this assumes>. upgrade: <the trigger to revisit>.
```

Examples across languages (all matched):

```python
# bmad-defer: linear scan over the cache. ceiling: <500 entries. upgrade: switch to an index past that.
```
```go
// bmad-defer: in-memory rate limit. ceiling: single instance. upgrade: move to Redis when horizontally scaled.
```
```sql
-- bmad-defer: full-table count. ceiling: <100k rows. upgrade: maintain a counter table beyond that.
```

- **Recognized comment leaders** (so the sweep is language-generic): `#`, `//`, `--`, `;`, `%`,
  `/*` (C-style block open), `<!--` (HTML/XML/Markdown), `'` (VB/VBScript). The marker keyword
  `bmad-defer:` is matched **case-insensitively**.
- **Payload parsing:** the text after `bmad-defer:` up to `ceiling:` is `<what>`; the text after
  `ceiling:` up to `upgrade:` is the `<ceiling>`; the text after `upgrade:` is the `<upgrade>`
  trigger. `ceiling`/`upgrade` are optional in the text — a marker that names **no** `upgrade:`
  trigger is tagged **`no-trigger`** (these rot silently and are escalated; see severity below).
- This is the same marker the PM dev and clean-release phases write and read — keep the keyword and
  field names stable; other skills depend on this exact contract.

### Grep contract

Search the whole tree from `{project-root}`, **case-insensitive**, with line numbers, skipping
vendored/build/VCS output:

```bash
grep -rniE '(#|//|--|;|%|/\*|<!--|'\'') ?bmad-defer:' . \
  --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=dist --exclude-dir=build \
  --exclude-dir=vendor --exclude-dir=.venv --exclude-dir=target --exclude-dir=out \
  --exclude-dir='{implementation_artifacts}' --exclude-dir='{planning_artifacts}'
```

Append `--exclude-dir={dir}` for each directory listed in `harvest_exclude_dirs` (resolved in Step H1).

Artifact directories are excluded — markers are a **source-code** convention, not an artifact one,
and a marker quoted inside a backlog description must never re-harvest itself.

### Steps

**Step H1 — Load config and resolve the backlog file**

Load config (same as layout cleanup). Also resolve:
- `harvest_exclude_dirs` — from the `l3io-util` section; default `[]`. Additional directories to exclude from the sweep on top of the built-in exclusion list. Each entry is passed as an additional `--exclude-dir` argument in the [Grep contract](#grep-contract).

Resolve the harvest target using the same read-resolution the PM skills use (split layout is authoritative):

1. If `{implementation_artifacts}/sprint-status-backlog.yaml` exists → bind `{status_backlog}` to it.
2. Else if a legacy `{implementation_artifacts}/sprint-status.yaml` exists → print:
   ```
   Found legacy sprint-status.yaml but no split layout. Run `split-status` first, then re-run harvest-debt.
   ```
   and exit (do not write into a legacy file; harvest only targets the split `backlog:` list).
3. Else → no state yet. The backlog file will be created lazily in Step H6 containing only a
   top-level `backlog:` list (a valid, readers-tolerated shape).

**Step H2 — Sweep and parse**

Run the [Grep contract](#grep-contract). For each hit, parse one marker record:
`{file}` (path relative to `{project-root}`), `{line}`, `{what}`, `{ceiling}` (or empty),
`{upgrade}` (or empty), and `no_trigger` = true when `{upgrade}` is empty. If the sweep finds
nothing, print `No bmad-defer: markers found. Clean tree — nothing to harvest.` and exit.

**Step H3 — Dedupe against the existing backlog**

Read the `backlog:` list from `{status_backlog}` (empty if the file or list is absent). A marker is
**already harvested** if an existing item has `source` containing `code-marker ({file}:{line})` — this matches both entries written by `harvest-debt` itself (`source: 'code-marker ({file}:{line})'`) and entries written by sprint closure Step 9 (`source: 'clean-release (code-marker {file}:{line})'`), so running either tool first does not produce duplicates when the other runs later. Dedupe is matched by `source` field, not by key — so legacy `DEBT-NN` keyed entries from prior runs are also correctly deduped by their source field. Partition the swept markers:
- `new` — not present in the backlog.
- `existing` — already harvested (skip; do not duplicate or re-key).

**Step H4 — Dry-run ledger**

Group `new` markers by file and print the ledger (this is also the report-only output — a user who
declines Step H5 still gets this):

```
DEBT HARVEST DRY RUN — bmad-defer: markers
================================================================
{file}
  L{line} — {what}
            ceiling: {ceiling | '(none)'}   upgrade: {upgrade | 'NO-TRIGGER — rots silently'}
...
================================================================
Markers found: {total}  ·  new: {new_count}  ·  already harvested: {existing_count}  ·  no-trigger: {no_trigger_count}
Backlog target: {status_backlog}
```

If `{new_count}` is 0: print `All {total} marker(s) already harvested — backlog is current.` and exit.

**Step H5 — Confirm merge**

Ask: "Harvest {new_count} new marker(s) into the backlog at {status_backlog}? Existing entries are untouched."

If no: print `Harvest cancelled — report only, no changes made.` and exit.

**Step H6 — Merge into the backlog**

Append one item per `new` marker to the top-level `backlog:` list of `{status_backlog}`, following
the consolidated backlog schema (the PM skills' `references/status-files.md` is the schema source of
truth). Generate keys by continuing the highest existing `BL-E00-NN` suffix (check existing items with `epic: '00'`; also check for any legacy `DEBT-NN` items to avoid gap collisions):

```yaml
- key: BL-E00-01                       # BL-E00-{nn} — repo-global, not epic-scoped
  epic: '00'                           # '00' = repo-global marker
  sprint: ''
  title: {what}                        # first clause of the marker, trimmed
  source: 'code-marker ({file}:{line})'
  severity: Low                        # Medium when no_trigger — a deferral with no revisit trigger rots silently
  status: backlog
  description: '{what} (ceiling: {ceiling | none}; upgrade: {upgrade | NONE — no revisit trigger}).'
```

Severity rule: a marker that names an `upgrade:` trigger is `Low`; a `no-trigger` marker is `Medium`
(it has no built-in escape from rotting, so it earns a higher gate). Never invent a ceiling or
upgrade the comment did not state — record `none`/`NONE`.

**Step H7 — Verify**

Re-parse `{status_backlog}` as YAML. If parsing fails, restore the pre-merge content and print:
```
FAILED — Written backlog is not valid YAML. Original restored. Parse error: {error}
```

**Step H8 — Report**

```
DONE — Debt harvest complete.
  Markers swept:     {total}
  Harvested (new):   {new_count}  (Low: {low_count}, Medium/no-trigger: {no_trigger_count})
  Already harvested: {existing_count}
  Backlog:           {status_backlog}
```

Markers stay in the source until the developer removes them when the shortcut is upgraded; harvest
records them, it never edits source. A future run re-sweeps and dedupes, so removing a marker simply
stops it reappearing (the backlog item it created persists until triaged like any other).

---

## Reconcile Status Mode

Invoked with `reconcile-status` argument. Audits the three split status files for four categories of drift and fixes them in one confirmed pass. Dry-run first; confirms before any writes. Safe to run at any time — re-runnable with no side effects when everything is already correct.

### What it fixes

1. **Misplaced epics** — `sprint-status.yaml` is the home for all non-done epics regardless of status (in-progress, backlog, pending, deferred, not-started, or any other status). Only `status: done` epics belong in `sprint-status-archived.yaml`. The backlog file holds the flat deferred-issues list and epic shells only — no full epic nodes.
   - `status: done` epic found in `sprint-status.yaml` or `sprint-status-backlog.yaml` → move to `sprint-status-archived.yaml`
   - Any non-`done` epic (in-progress, backlog, pending, deferred, or any other status) found as a full epic node in `sprint-status-backlog.yaml` or `sprint-status-archived.yaml` → move to `sprint-status.yaml`

2. **Nested backlog arrays** — nested `backlog:` arrays inside epic nodes (the `epics[N].backlog:` key in any of the three files) must be flattened into the top-level `backlog:` list in `sprint-status-backlog.yaml`. New items are deduped against the existing list (by `source` field first, then by `key`). The per-epic nested `backlog:` key is removed from the epic node after the items are merged.

3. **Stale resolved/promoted items** — items in the top-level `backlog:` list of `sprint-status-backlog.yaml` with `status` other than `backlog` should not remain in the list. Per the schema contract, resolved and promoted items are removed immediately; this step catches any that were left behind.

4. **Empty epic shells** — an epic shell in `sprint-status-backlog.yaml` is a partial epic node (`id`, `title`, `goal`, `sprints:`) that tracks backlog sprints of an in-progress epic. If the shell's `sprints:` list is empty (or absent) AND the corresponding epic is already in `sprint-status.yaml` as `in-progress`, the shell is stale and should be removed.

### Steps

**Step RC1 — Load config and resolve status files**

Load config (same as layout cleanup). Check for the split layout:
- If neither `sprint-status-backlog.yaml` nor `sprint-status-archived.yaml` exists in `{implementation_artifacts}/`:
  ```
  No split layout found. Run /l3io-util-cleanup split-status first, then re-run reconcile-status.
  ```
  Exit.

Bind `{status_active}` = `sprint-status.yaml`, `{status_backlog}` = `sprint-status-backlog.yaml`, `{status_archived}` = `sprint-status-archived.yaml`. Process only files that exist; treat absent files as empty.

**Step RC2 — Audit**

Parse all present files. Collect four finding sets:

**A — Misplaced epics**

For each epic node in each file, compare its `status` to the file it was found in. `sprint-status.yaml` is the home for **all non-done epics** regardless of status — in-progress, backlog, pending, deferred, not-started, or any other status. `sprint-status-backlog.yaml` holds shells and the flat deferred-issues list only; no full epic nodes belong there.

| File | Correct placement | Misplaced if |
|---|---|---|
| `sprint-status.yaml` | any epic with `status ≠ done` | has `status: done` → move to `sprint-status-archived.yaml` |
| `sprint-status-backlog.yaml` (full epic, not shell) | (no full epics belong here) | has any `status` field → move to `sprint-status.yaml` (unless `status: done`, then move to archived) |
| `sprint-status-archived.yaml` | `status: done` only | `status ≠ done` → move to `sprint-status.yaml` |

Note: epic shells in `sprint-status-backlog.yaml` (identified by having no `status` field — they carry only `id`, `title`, `goal`, and `sprints:`) are not misplaced epics; they are handled by finding set D.

Record each misplaced epic as `{ epic_id, title, current_status, current_file, correct_file }`.

**B — Nested backlog arrays**

For each epic node in all three files, check whether the node has a `backlog:` key (a per-epic nested backlog array). Collect every item in those arrays. For each item, check against the existing top-level `backlog:` list in `{status_backlog}`:
- Match by `source` field (same value → duplicate)
- If no `source`, match by `key` (same key → duplicate)
- Partition items into `new` and `duplicate`.

Record each finding as `{ epic_id, found_in_file, item_count, new_count, duplicate_count }`.

**C — Stale backlog items**

In the top-level `backlog:` list of `{status_backlog}`, collect every item where `status` is not `backlog`. Record each as `{ key, epic, title, current_status }`.

**D — Empty epic shells**

In `{status_backlog}`, identify epic nodes that are shells (no `status` field, has `sprints:` key). For each shell, check whether its `sprints:` list is empty or absent AND whether the corresponding epic id appears in `{status_active}` as `in-progress`. If both conditions are true, record as an empty shell `{ epic_id, title }`.

**Step RC3 — Dry-run report**

Print a consolidated findings table:

```
RECONCILE STATUS DRY RUN — {implementation_artifacts}
================================================================

A. Misplaced Epics: {A_count}
  Epic {id} "{title}" — status: {status} found in {current_file}
                      → move to {correct_file}
  ...

B. Nested Backlog Arrays: {B_total} item(s) across {B_epics} epic(s)
  {current_file} epics[{id}].backlog: {item_count} item(s) → flatten to top-level backlog:
    {new_count} new, {duplicate_count} duplicate(s) (skipped)
  ...

C. Stale Backlog Items: {C_count}
  {key} (status: {current_status}) — "{title}" → remove from backlog:
  ...

D. Empty Epic Shells: {D_count}
  Epic {id} shell in sprint-status-backlog.yaml — sprints: [] and epic is in-progress → remove shell
  ...

================================================================
Total changes: {total} across {file_count} file(s).
Nothing will be modified until confirmed.
```

If all four sets are empty:
```
✓ Status files are reconciled — no placement or backlog structure issues found.
```
Exit.

**Step RC4 — Confirm**

Ask: "Apply {total} reconciliation change(s) shown above?"

If no: print `Reconcile cancelled — no changes made.` and exit.

**Step RC5 — Execute**

Apply changes in this order to minimize intermediate invalid state. After each file write, re-parse as YAML; on any parse failure, restore that file's pre-reconcile content and print:
```
FAILED — {file} is not valid YAML after reconcile step {letter}. File restored. Remaining steps not applied.
```
Stop on any failure; do not apply further changes.

1. **A — Misplaced epics**: For each misplaced epic, read the full epic node from its current file, append it to the correct file (maintaining ascending `id` order within the `epics:` list), then remove it from the source file. Write both affected files.

2. **B — Nested backlog arrays**: For each epic node with a nested `backlog:` array, append the `new` items to the top-level `backlog:` list in `{status_backlog}`. Assign new keys for any item that lacks a `BL-E{epic}-{nn}` formatted key by continuing from the highest existing suffix for that epic (check all existing items in the top-level list with the same `epic` value). Remove the `backlog:` key from the epic node. Write `{status_backlog}` and the source file containing the epic node.

3. **C — Stale items**: Remove each stale item from the top-level `backlog:` list in `{status_backlog}`. Write `{status_backlog}`.

4. **D — Empty shells**: Remove each empty shell epic node from the `epics:` list in `{status_backlog}`. Write `{status_backlog}`.

**Step RC6 — Verify**

Re-parse all three files. Confirm:
- No epic appears in more than one file.
- Every epic's placement file matches its `status` (shells in `{status_backlog}` are exempt — they have no `status` field).
- No `epics[N].backlog:` keys remain in any file.
- No items with `status != backlog` remain in the top-level `backlog:` list.
- No empty shells remain in `{status_backlog}`.

If any check fails, list the remaining issues as warnings rather than errors (the file state is safe — the verify step is informational after a successful write).

**Step RC7 — Report**

```
DONE — Status reconciliation complete.
  Epics moved:              {A_count}  (to archived: {to_arch}, to active: {to_act}, to backlog: {to_bl})
  Backlog items flattened:  {B_new} new  ({B_dup} duplicate(s) skipped)
  Stale items removed:      {C_count}
  Empty shells removed:     {D_count}
  Files modified:           {file_list}
```

If `{A_count + B_new + C_count + D_count}` = 0 (nothing to do):
```
DONE — No reconciliation needed. Status files are already consistent.
```

---

## Sort Status Mode

Invoked with `sort-status` argument. Validates that epics, sprints, stories, and backlog items in the three split status files are in the expected sort order and applies sorting where needed. Safe to run at any time — never modifies field values, only reorders list nodes. Dry-run first; confirms before writing.

**Expected sort order:**

| Scope | Key | Direction |
|---|---|---|
| Epics within each status file | `id` parsed as integer | Ascending |
| Sprints within each epic | `id` parsed as integer | Ascending |
| Stories within each sprint | `key` lexicographic | Ascending |
| Backlog items in `sprint-status-backlog.yaml` | `epic` (int, blank → 9999) then `sprint` (int, blank → 9999) then `key` | Ascending |

### Steps

**Step SO1 — Load config and resolve status files**

Load config (same as layout cleanup). Resolve the split layout files:
- `{status_active}` = `{implementation_artifacts}/sprint-status.yaml`
- `{status_backlog}` = `{implementation_artifacts}/sprint-status-backlog.yaml`
- `{status_archived}` = `{implementation_artifacts}/sprint-status-archived.yaml`

Process only files that exist; silently skip absent ones. If no split-layout files exist (no backlog or archived files) but `sprint-status.yaml` exists alone (full-content, not yet split), print:
```
No split layout found. Run /l3io-util-cleanup split-status first, then re-run sort-status.
```
and exit.

**Step SO2 — Validate ordering**

Parse each present file. For each file check:
1. Epics list: is each epic's `id` (parsed as int) ≥ the previous epic's `id`? If not, record the file and the out-of-order `id` pair.
2. Within each epic, sprints list: same check by `id`.
3. Within each sprint, stories list: is each story's `key` ≥ the previous key (lexicographic)? Record out-of-order pairs.
4. In `{status_backlog}`, top-level `backlog:` list: sort key = (`epic` as int with blank → 9999, `sprint` as int with blank → 9999, `key`). Record any pair that violates this order.

Accumulate all findings as `{ordering_issues}`.

**Step SO3 — Dry-run report**

If `{ordering_issues}` is empty:
```
STATUS ORDER CHECK — all files in order.
  sprint-status.yaml:          {a_epics} epics, {a_sprints} sprints, {a_stories} stories — ✓ sorted
  sprint-status-backlog.yaml:  {b_epics} epics, {b_sprints} sprints, {b_stories} stories, {bl_count} backlog items — ✓ sorted
  sprint-status-archived.yaml: {r_epics} epics, {r_sprints} sprints, {r_stories} stories — ✓ sorted
```
Exit.

Otherwise:
```
STATUS ORDER DRY RUN
================================================================
File                              Scope                           Issue
----------------------------------------------------------------
sprint-status.yaml                epics                           id 03 appears before id 02
sprint-status.yaml                epic 01 → sprints               id 02 appears before id 01
sprint-status-backlog.yaml        backlog items                   BL-E00-03 appears before BL-E00-01
...
================================================================
{N} ordering issue(s) found across {M} file(s).
Proposed: epics by id ↑, sprints by id ↑ within epic, stories by key ↑ within sprint,
          backlog by epic ↑ → sprint ↑ → key ↑ (blank epic/sprint sort last).
```

**Step SO4 — Confirm**

Ask: "Sort {N} issue(s) across {M} file(s)? Field values are not changed — list order only."

If no: print `Sort cancelled — no changes made.` and exit.

**Step SO5 — Sort and write**

For each file with ordering issues:
1. Sort the top-level `epics:` list by `int(id)` ascending.
2. Within each epic node, sort its `sprints:` list by `int(id)` ascending.
3. Within each sprint node, sort its `stories:` list by `key` ascending (lexicographic).
4. In `{status_backlog}` only: sort the top-level `backlog:` list by the composite key (`epic` as int with `''` → 9999, `sprint` as int with `''` → 9999, `key` lexicographic).
5. Preserve all field values exactly — ordering changes only.
6. Write the reordered file to disk.

**Step SO6 — Verify**

Re-parse each rewritten file as YAML. If any file fails to parse, restore its pre-sort content and print:
```
FAILED — {file} is not valid YAML after sort. Original restored. Parse error: {error}
```

**Step SO7 — Report**

```
DONE — Status sort complete.
  sprint-status.yaml:          {a_changes} list(s) reordered  (or "✓ already sorted")
  sprint-status-backlog.yaml:  {b_changes} list(s) reordered, {bl_changes} backlog items reordered  (or "✓ already sorted")
  sprint-status-archived.yaml: {r_changes} list(s) reordered  (or "✓ already sorted")
```

---

## Rename Active Mode

Invoked with `rename-active` argument. One-time migration for projects using the old
`sprint-status-active.yaml` filename. Renames the file to `sprint-status.yaml` so the PM
skills and the core BMad framework skills find the right file without overrides. Content is
not changed — placement only.

### Steps

**Step RA1 — Load config and check preconditions**

Load config (same as layout cleanup). Resolve paths:
- Old name: `{implementation_artifacts}/sprint-status-active.yaml`
- New name: `{implementation_artifacts}/sprint-status.yaml`

If `sprint-status-active.yaml` does NOT exist:
```
sprint-status-active.yaml not found at {implementation_artifacts} — nothing to rename.
```
Exit.

If `sprint-status.yaml` already exists:
```
Conflict: sprint-status.yaml already exists at {implementation_artifacts}. Cannot rename sprint-status-active.yaml — resolve manually (e.g. remove or merge the existing sprint-status.yaml first).
```
Exit.

**Step RA2 — Dry-run**

```
RENAME ACTIVE DRY RUN
Will rename: {implementation_artifacts}/sprint-status-active.yaml
         → {implementation_artifacts}/sprint-status.yaml
Content unchanged — filename only.
```

**Step RA3 — Confirm**

Ask: "Rename sprint-status-active.yaml → sprint-status.yaml?"

If no: print `Rename cancelled — no changes made.` and exit.

**Step RA4 — Rename**

Rename `sprint-status-active.yaml` → `sprint-status.yaml`.

**Step RA5 — Verify**

Re-parse `sprint-status.yaml` as YAML to confirm the file is valid. Confirm the old name
`sprint-status-active.yaml` no longer exists at that path. If YAML parse fails, rename the
file back and print:
```
FAILED — sprint-status.yaml is not valid YAML after rename. Restored to sprint-status-active.yaml. Parse error: {error}
```

**Step RA6 — Report**

```
DONE — Renamed sprint-status-active.yaml → sprint-status.yaml. No content changed.
```

---

## Update AI Rules Mode

Invoked with `update-ai-rules` argument, or automatically from [Split Status Mode](#split-status-mode) Step S9. Scans for AI system instruction files in the project and updates any references to the legacy `sprint-status.yaml` to document the current three-file split layout. For instruction files that already exist: updates existing references. For the currently running AI system's file that does not yet exist: creates it with a status layout section. Never creates instruction files for other AI systems. Safe to run repeatedly — already-updated files are skipped.

### Supported AI instruction file locations

| AI System | Instruction file |
|---|---|
| Claude Code | `{project-root}/CLAUDE.md` |
| GitHub Copilot | `{project-root}/.github/copilot-instructions.md` |
| Google Gemini | `{project-root}/GEMINI.md` |
| Generic agents | `{project-root}/AGENTS.md` |
| Cursor | `{project-root}/.cursorrules` or `{project-root}/cursor.md` |
| Cline | `{project-root}/.clinerules` or `{project-root}/CLINE.md` |

### Detection rule

A `sprint-status.yaml` reference is flagged for update if it is NOT immediately followed by `.legacy` and the same paragraph or section does not already mention `sprint-status-backlog.yaml` or `sprint-status-archived.yaml`. References that are already updated (mention the split layout) are skipped.

### Steps

**Step AR1 — Scan**

Check each well-known instruction file location. For each file that exists, grep for `sprint-status\.yaml` (case-sensitive) and collect all matches with surrounding context (2 lines before/after). Apply the detection rule. Build a findings list: `{file}` + `{line}` + `{context}`.

Also determine the current AI runtime (Claude, Copilot, Gemini, etc.) from execution context. If the current runtime's instruction file does not exist and was not found above, add it to a `{to_create}` list.

If no existing instruction files found AND `{to_create}` is empty: print `No AI instruction files found — nothing to update.` and exit.

If existing files found but no flagged references AND `{to_create}` is empty: print `AI instruction files are already current — no sprint-status.yaml references detected.` listing files checked, and exit.

**Step AR2 — Dry-run**

```
AI RULES DRY RUN
================================================================
Existing files to update:
  File                                  Line   Current reference
  ─────────────────────────────────────────────────────────────
  CLAUDE.md                              42    sprint-status.yaml
  .github/copilot-instructions.md        17    _bmad-output/sprint-status.yaml

Files to create (current AI runtime):
  {file} — new section: PM state file layout

Files checked (no changes needed):
  {files_with_no_hits}
================================================================
{N} reference(s) to update across {M} existing file(s). {C} file(s) to create.
```

**Step AR3 — Confirm**

Ask: "Update {N} reference(s) in {M} file(s) and create {C} new file(s)?"

If no: print `Update cancelled — no changes made.` and exit.

**Step AR4 — Apply updates to existing files**

For each file in the findings list, read the full content. For each flagged reference, construct a contextually appropriate replacement:

- **Inline path** (e.g., `some/path/sprint-status.yaml`): append ` (split layout: sprint-status.yaml / sprint-status-backlog.yaml / sprint-status-archived.yaml)` as a trailing inline note.
- **Standalone keyword** (e.g., "reads sprint-status.yaml"): replace with a brief description: "`sprint-status.yaml` (in-progress epics), `sprint-status-backlog.yaml` (backlog), `sprint-status-archived.yaml` (archived)".
- **Section or block** describing the state file: replace the entire description block with the three-file layout explanation, preserving surrounding format.

Read 3 lines of surrounding context before choosing the replacement strategy. Write the updated content to disk.

**Step AR5 — Create new file for current runtime**

For each file in `{to_create}`, create the file (and any parent directories, e.g. `.github/`) and write a minimal AI instruction section covering the PM state file layout:

```markdown
## BMad PM — State File Layout

Sprint and epic state is tracked in three split status files under `{implementation_artifacts}/`:

- `sprint-status.yaml` — epics currently in-progress, with their active and done sprints and all stories
- `sprint-status-backlog.yaml` — not-yet-started epics and sprints, plus the consolidated deferred-issue backlog list
- `sprint-status-archived.yaml` — completed epics (moved here wholesale at epic close)

A legacy single `sprint-status.yaml` (full-content, pre-split) is auto-split on first PM skill run, or explicitly with `/l3io-util-cleanup split-status`.
```

Adapt the heading style and surrounding content to match the existing file format for that AI system.

**Step AR6 — Verify and report**

Re-read each updated and created file. Confirm no `sprint-status.yaml` (non-legacy) references remain. If any remain, list them as unresolved.

```
DONE — AI rules update complete.
  References updated: {N} across {M} file(s)
  Files created:      {C}
  Unresolved:         {U} (list if > 0)
  Files checked (no changes needed): {files}
```

---

## Normalize Mode

Invoked with `normalize` argument. Convenience shortcut that runs [Reconcile Status Mode](#reconcile-status-mode) followed by [Sort Status Mode](#sort-status-mode) in a single confirmed pass. Use for routine maintenance instead of running two separate commands.

### Steps

**Step NM1 — Load config**

Load config (same as layout cleanup). Check for the split layout — if neither `sprint-status-backlog.yaml` nor `sprint-status-archived.yaml` exists, print:
```
No split layout found. Run /l3io-util-cleanup split-status first, then re-run normalize.
```
Exit.

**Step NM2 — Reconcile**

Run the full Reconcile Status Mode (Steps RC1–RC7) with one modification: **present the dry-run report but defer confirmation** — print the reconcile findings and the sort findings together in Step NM3 before asking to proceed.

If reconcile finds nothing to fix (`total` = 0), note that and proceed directly to the sort analysis.

**Step NM3 — Sort analysis**

Run the ordering validation from Sort Status Mode (Step SO2) on each present split file. Collect `{ordering_issues}`.

If sort finds nothing to fix, note that.

**Step NM4 — Combined dry-run and confirm**

Print the reconcile dry-run output (or "✓ Nothing to reconcile") followed by the sort dry-run output (or "✓ Nothing to sort"), then ask:

```
Apply {reconcile_total} reconciliation change(s) and {sort_issues} sort fix(es)?
  Y — proceed
  n — exit, no changes
```

If `n`: print `Normalize cancelled — no changes made.` and exit.

If both totals are 0: print `✓ Status files are already normalized — nothing to do.` and exit.

**Step NM5 — Execute reconcile**

If reconcile has changes: apply Steps RC5–RC7 (execute, verify, report). On failure, stop and report — do not proceed to sort.

**Step NM6 — Execute sort**

If sort has changes: apply Steps SO5–SO7 (sort and write, verify, report). On failure, report.

**Step NM7 — Summary**

```
DONE — Normalize complete.
  Reconcile: {reconcile summary line or "nothing to do"}
  Sort:      {sort summary line or "nothing to do"}
```

---

## Stats Mode

Invoked with `stats` argument. Read-only project state dashboard — parses all three split status files and prints counts. No files are changed.

### Steps

**Step ST1 — Load config**

Load config (same as layout cleanup). Detect which layout is present:
- Split layout (any of the three files exist) → parse all present files.
- Legacy single `sprint-status.yaml` only → parse it; note that split layout has not been applied.
- No status files → print `No status files found at {implementation_artifacts}.` and exit.

**Step ST2 — Parse and count**

Parse all present files. Accumulate:

- **Epics** by `status` (backlog, in-progress, done) — count per status, total.
- **Sprints** by `status` (backlog, in-progress, done) — count per status, total.
- **Stories** by `status` (backlog, ready-for-dev, in-progress, review, done) — count per status, total.
- **Backlog items** (top-level `backlog:` list in `sprint-status-backlog.yaml`) — count by severity (Critical, High, Medium, Low, unknown), total.
- **Last closed sprint** — the sprint with the highest `id` across all epics where `status: done`; note its epic and sprint id.
- **Last closed epic** — the epic with the highest `id` in `sprint-status-archived.yaml`; note its id and title.
- **Calibration file** — check if `{project-root}/_bmad/pm-calibration.yaml` exists; if so, note its version and the number of scope/closure/fix sample entries.

**Step ST3 — Print dashboard**

```
PROJECT STATE — {implementation_artifacts}
================================================================
Epics
  in-progress:  {n}    backlog: {n}    done: {n}    total: {n}
Sprints
  in-progress:  {n}    backlog: {n}    done: {n}    total: {n}
Stories
  done:         {n}    in-progress: {n}    review: {n}
  ready-for-dev:{n}    backlog: {n}         total: {n}
Backlog items
  Critical: {n}  High: {n}  Medium: {n}  Low: {n}  total: {n}
----------------------------------------------------------------
Last sprint closed:  Epic {EE} / Sprint {SS}  (or "none")
Last epic closed:    Epic {EE} — {title}      (or "none")
Calibration file:    {version}, {n} scope samples  (or "not found")
Layout:              {Split (3-file) | Legacy (single file)}
================================================================
```

---

## Backlog Mode

Invoked with `backlog` argument. Read-only — lists all items in the consolidated `backlog:` list from `sprint-status-backlog.yaml` in a readable table grouped by severity. No files are changed.

### Steps

**Step BL1 — Load config and resolve backlog file**

Load config (same as layout cleanup). If `{implementation_artifacts}/sprint-status-backlog.yaml` does not exist, print:
```
No backlog file found at {implementation_artifacts}/sprint-status-backlog.yaml.
Run /l3io-util-cleanup split-status to create the split layout first.
```
Exit.

**Step BL2 — Parse**

Read the top-level `backlog:` list. If the list is absent or empty, print `Backlog is empty — no items found.` and exit.

**Step BL3 — Print table**

Group items by severity (Critical → High → Medium → Low → unknown). Within each group, sort by `epic` ascending then `key` ascending. Print:

```
BACKLOG — {implementation_artifacts}/sprint-status-backlog.yaml
================================================================
Sev      Key           Epic  Sprint  Title
----------------------------------------------------------------
Critical
  CRIT   BL-E01-01     01    02      {title (truncated to 50 chars)}
  ...
High
  HIGH   BL-E01-02     01    —       {title}
  ...
Medium
  MED    BL-E00-01     00    —       {title}
  ...
Low
  LOW    BL-E02-01     02    03      {title}
  ...
================================================================
Total: {n} item(s)  (Critical: {n}  High: {n}  Medium: {n}  Low: {n})
```

Truncate titles at 50 characters with `…`. Sprint shown as `—` when blank.

---

## Clean Legacy Mode

Invoked with `clean-legacy` argument. Removes migration backup files left behind by one-time migration commands: `.yaml.legacy` files in `{implementation_artifacts}/` and `.yaml.v1` calibration backup files in `{project-root}/_bmad/`. Dry-run first; confirms before deleting. Safe to run once migrations have been verified.

### Steps

**Step CL1 — Load config and scan**

Load config (same as layout cleanup). Scan for:
1. `*.yaml.legacy` files anywhere under `{implementation_artifacts}/` (e.g., `sprint-status.yaml.legacy`).
2. `*.yaml.v1` files in `{project-root}/_bmad/` (e.g., `pm-calibration.yaml.v1`).

If nothing found: print `No legacy backup files found — nothing to clean.` and exit.

**Step CL2 — Dry-run**

```
CLEAN LEGACY DRY RUN
================================================================
File                                                    Size
----------------------------------------------------------------
{implementation_artifacts}/sprint-status.yaml.legacy   {size}
{project-root}/_bmad/pm-calibration.yaml.v1            {size}
...
================================================================
{N} file(s) to delete. These are migration backups — the live files are unaffected.
```

**Step CL3 — Confirm**

Ask: "Delete {N} backup file(s)? This cannot be undone."

If no: print `Clean cancelled — no files deleted.` and exit.

**Step CL4 — Delete**

Delete each file. Log each deletion. If any deletion fails (permissions, locked file), record and continue — do not abort the entire run.

**Step CL5 — Report**

```
DONE — Clean legacy complete.
  Deleted: {n} file(s)
  Failed:  {n} file(s) (list if > 0)
```

---

## Migrate State Mode

Invoked with `migrate-state` argument.

Load `{skill-root}/assets/migrate-state.md` and execute it fully.
