---
name: bmad-l3io-util-cleanup
description: One-time migration utility. Use when the user needs to reorganize legacy flat BMad artifact outputs into the structured epic/sprint folder layout with zero-padded names, reconcile file references, and verify state consistency.
---

# Artifact Layout Cleanup

## Overview

One-time migration utility. Reorganizes flat artifact outputs into a structured epic/sprint folder hierarchy with zero-padded names, reconciles file references, verifies state consistency, and produces a summary report. Run once to bring a legacy project into the standard layout.

**One-time use:** Designed to be run once per project. Running again after a successful cleanup produces zero moves (everything already placed) or conflicts (for new flat files added since the first run).

## Conventions

- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## On Activation

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

Search reference-holding files: `sprint-status.yaml`, story `.md` files, planning docs, closure and test reports. For each moved file, replace exact old-path occurrences with the new path. If one old path could match multiple targets or context is ambiguous, record for manual review — do not auto-update.

### Step 7 — State Verification

Verify post-move state:
- Epic and sprint folder names are zero-padded (`epic-01` not `epic-1`, `sprint-02` not `sprint-2`)
- Story files under `stories/`, closure outputs under `closure/`, tests under `tests/`
- If `sprint-status.yaml` exists: flag story state entries referencing missing story files
- Flag any residual flat files that were not classified and remain in the root

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
