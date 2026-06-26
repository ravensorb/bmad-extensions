---
name: l3io-util-cleanup
description: Migration utilities. Use when the user needs to reorganize legacy flat BMad artifact outputs into the structured epic/sprint folder layout, migrate sprint-status.yaml to the current field schema, split it into the three-file layout, harvest deferred-shortcut code markers into the backlog, validate and sort the ordering of epics and sprints in the status files, or update AI system instruction files with the current status file layout.
---

# Artifact Layout Cleanup

## Overview

Migration and housekeeping utilities for BMad artifacts. Four modes:

- **Default (layout cleanup):** Reorganizes flat artifact outputs into a structured epic/sprint folder hierarchy with zero-padded names, reconciles file references, verifies state consistency, and produces a summary report. Run once to bring a legacy project into the standard layout.
- **`migrate-schema`:** Upgrades an existing `sprint-status.yaml` to the current field schema — adds missing fields with zero/empty defaults, never overwrites existing values.
- **`split-status`:** Splits a single `sprint-status.yaml` into the three-file layout the PM skills now use — `sprint-status-active.yaml`, `sprint-status-backlog.yaml`, `sprint-status-archived.yaml` — partitioning every epic/sprint by status. One-time migration; the original is preserved as `sprint-status.yaml.legacy`. (Run `migrate-schema` first if the file predates the current field schema.)
- **`harvest-debt`:** Greps the whole source tree for `bmad-defer:` deferred-shortcut markers (the comment crumbs developers and dev subagents leave when they take an intentional simplification) and harvests them into the consolidated `backlog:` list so deferrals do not rot into "later means never." Language-generic — recognizes the comment syntax of every common language. Re-runnable: dedupes against already-harvested markers. Report-only by default; backlog merge is confirmed.
- **`sort-status`:** Validates that epics, sprints, stories, and backlog items in all three split status files are in the expected sort order, and applies sorting if needed. Dry-run first; confirms before writing. Safe to run at any time — never edits field values, only reorders nodes.
- **`update-ai-rules`:** Scans for AI system instruction files in the project (`CLAUDE.md`, `.github/copilot-instructions.md`, `GEMINI.md`, `AGENTS.md`, `.cursorrules`, and others) and updates any references to the legacy `sprint-status.yaml` to document the current three-file split layout. For files that already exist: updates existing references. For the currently running AI system's file if it does not exist: creates it with a status layout section. Never creates files for other AI systems. Also auto-invoked after a successful `split-status` run. Safe to run repeatedly.

**One-time use (layout cleanup):** Designed to be run once per project. Running again after a successful cleanup produces zero moves (everything already placed) or conflicts (for new flat files added since the first run).

## Conventions

- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## On Activation

If the user passes `migrate-schema` as an argument, skip to [Schema Migration Mode](#schema-migration-mode).

If the user passes `split-status` as an argument, skip to [Split Status Mode](#split-status-mode).

If the user passes `harvest-debt` as an argument, skip to [Harvest Debt Mode](#harvest-debt-mode).

If the user passes `sort-status` as an argument, skip to [Sort Status Mode](#sort-status-mode).

If the user passes `update-ai-rules` as an argument, skip to [Update AI Rules Mode](#update-ai-rules-mode).

If the user passes `setup`, `configure`, or `install` as an argument — or if `{project-root}/_bmad/config.yaml` does not have an `l3io-util` section — load `assets/module-setup.md` to register the module first, then continue.

Load config from `{project-root}/_bmad/config.yaml` and `{project-root}/_bmad/config.user.yaml` (root level and `l3io-util` section). Resolve:
- `implementation_artifacts`
- `planning_artifacts`
- `output_folder`

If `implementation_artifacts` is not set, default to `{output_folder}/implementation-artifacts`.

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

Search reference-holding files: the split status files (`sprint-status-active.yaml`, `sprint-status-backlog.yaml`, `sprint-status-archived.yaml`) or legacy `sprint-status.yaml` (whichever are present), story `.md` files, planning docs, closure and test reports. For each moved file, replace exact old-path occurrences with the new path. If one old path could match multiple targets or context is ambiguous, record for manual review — do not auto-update.

### Step 7 — State Verification

Verify post-move state:
- Epic and sprint folder names are zero-padded (`epic-01` not `epic-1`, `sprint-02` not `sprint-2`)
- Story files under `stories/`, closure outputs under `closure/`, tests under `tests/`
- Check story state entries in whichever status files are present (split layout or legacy `sprint-status.yaml`) for references to missing story files
- Flag any residual flat files that were not classified and remain in the root

**Ordering check (status files):** If the split layout exists (`sprint-status-active.yaml`, `sprint-status-backlog.yaml`, or `sprint-status-archived.yaml`), check their sort order:
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
| `closed`, `retrospective`, `resolved`, `resolution` | Omit — only present when the actual value is known |

### Migration Steps

**Step M1 — Load config and locate status files**

Load config (same as layout cleanup). Detect which layout is present:

1. If `{implementation_artifacts}/sprint-status-active.yaml` exists → **split layout**: bind `{status_files}` to all present split files: `sprint-status-active.yaml`, `sprint-status-backlog.yaml`, `sprint-status-archived.yaml` (include only those that exist).
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
- `source`
- `severity`
- `description`

**Step M3 — Dry-run table**

```
SCHEMA MIGRATION DRY RUN — {status_files}
================================================================
File                          Node                              Field                Value
----------------------------------------------------------------
sprint-status-active.yaml     epics[01]                         title                'Epic 01'
sprint-status-active.yaml     epics[01]                         goal                 ''
sprint-status-active.yaml     epics[01]                         estimate.time_hours_low  0
sprint-status-active.yaml     epics[01].sprints[01]             title                'Sprint 01'
sprint-status-active.yaml     epics[01].sprints[01].stories[ST01]  classification    'unknown'
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
three-file layout the PM skills (`l3io-pm-sprint-execute`, `l3io-pm-epic-execute`)
now read and write. One-time, one-way migration. The original is never deleted — it is
renamed to `sprint-status.yaml.legacy` as the rollback. All [Safety Rules](#safety-rules)
apply: dry-run first, never overwrite an existing destination, preserve node contents
exactly.

This is the same partition the PM skills perform automatically on first run when they find
only a legacy file (see their `references/status-files.md`); running it here is the explicit,
reviewed path.

### Target files

In `{implementation_artifacts}/`:
- `sprint-status-active.yaml` — `epics:` with `status: in-progress`.
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
sprint-status-active.yaml           {a_e}   {a_s}    {a_st}      —
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

Artifact directories are excluded — markers are a **source-code** convention, not an artifact one,
and a marker quoted inside a backlog description must never re-harvest itself.

### Steps

**Step H1 — Load config and resolve the backlog file**

Load config (same as layout cleanup). Resolve the harvest target using the same read-resolution the
PM skills use (split layout is authoritative):

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
**already harvested** if an existing item has `source` containing `code-marker ({file}:{line})` — this matches both entries written by `harvest-debt` itself (`source: 'code-marker ({file}:{line})'`) and entries written by sprint closure Step 9 (`source: 'clean-release (code-marker {file}:{line})'`), so running either tool first does not produce duplicates when the other runs later. Partition the swept markers:
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
truth). Generate keys by continuing the highest existing `DEBT-NN` suffix (zero-padded, repo-global —
code markers are not tied to one epic/sprint):

```yaml
- key: DEBT-{NN}                       # next free DEBT-NN across the existing backlog
  epic: ''                             # markers are repo-global, not epic-scoped
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
- `{status_active}` = `{implementation_artifacts}/sprint-status-active.yaml`
- `{status_backlog}` = `{implementation_artifacts}/sprint-status-backlog.yaml`
- `{status_archived}` = `{implementation_artifacts}/sprint-status-archived.yaml`

Process only files that exist; silently skip absent ones. If no split-layout files exist but a legacy `sprint-status.yaml` is present, print:
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
  sprint-status-active.yaml:   {a_epics} epics, {a_sprints} sprints, {a_stories} stories — ✓ sorted
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
sprint-status-active.yaml         epics                           id 03 appears before id 02
sprint-status-active.yaml         epic 01 → sprints               id 02 appears before id 01
sprint-status-backlog.yaml        backlog items                   DEBT-03 appears before DEBT-01
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
  sprint-status-active.yaml:   {a_changes} list(s) reordered  (or "✓ already sorted")
  sprint-status-backlog.yaml:  {b_changes} list(s) reordered, {bl_changes} backlog items reordered  (or "✓ already sorted")
  sprint-status-archived.yaml: {r_changes} list(s) reordered  (or "✓ already sorted")
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

A `sprint-status.yaml` reference is flagged for update if it is NOT immediately followed by `.legacy` and the same paragraph or section does not already mention `sprint-status-active.yaml`. References that are already updated (mention the split layout) are skipped.

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

- **Inline path** (e.g., `some/path/sprint-status.yaml`): replace `sprint-status.yaml` → `sprint-status-active.yaml` and append ` (split layout: sprint-status-active.yaml / sprint-status-backlog.yaml / sprint-status-archived.yaml)` as a trailing inline note.
- **Standalone keyword** (e.g., "reads sprint-status.yaml"): replace with a brief description: "`sprint-status-active.yaml` (in-progress epics), `sprint-status-backlog.yaml` (backlog), `sprint-status-archived.yaml` (archived)".
- **Section or block** describing the state file: replace the entire description block with the three-file layout explanation, preserving surrounding format.

Read 3 lines of surrounding context before choosing the replacement strategy. Write the updated content to disk.

**Step AR5 — Create new file for current runtime**

For each file in `{to_create}`, create the file (and any parent directories, e.g. `.github/`) and write a minimal AI instruction section covering the PM state file layout:

```markdown
## BMad PM — State File Layout

Sprint and epic state is tracked in three split status files under `{implementation_artifacts}/`:

- `sprint-status-active.yaml` — epics currently in-progress, with their active and done sprints and all stories
- `sprint-status-backlog.yaml` — not-yet-started epics and sprints, plus the consolidated deferred-issue backlog list
- `sprint-status-archived.yaml` — completed epics (moved here wholesale at epic close)

A legacy single `sprint-status.yaml` is auto-split on first PM skill run, or explicitly with `/l3io-util-cleanup split-status`.
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
