---
name: l3io-util-cleanup
description: Migration and housekeeping utilities for BMad artifacts and l3io-pm state. Use when the user needs to migrate a legacy state layout (flat sprint-status.yaml, or legacy per-epic _bmad/state/) to the current sharded state tree, reorganize legacy flat artifact outputs into the structured epic/sprint folder layout, harvest deferred-shortcut code markers into the issues backlog, validate zero-padded naming in the state tree, review the issues backlog or a project state dashboard, or update AI system instruction files to describe the current state layout. Also carries older legacy-only bridging modes (migrate-schema, split-status, reconcile-status) for repos that have not yet migrated. Run without arguments for an auto-diagnostic that scans project state and proposes the right actions.
---

# Artifact Layout Cleanup

## Overview

Migration and housekeeping utilities for BMad artifacts.

**Default behavior (no argument or unrecognized text):** Runs a project health check — scans for all known issues, reports findings in a priority table, and proposes the right actions in the correct execution order. One confirmation runs them all.

Modes (pass as argument to skip directly to that mode):

**Diagnostic (read-only)**
- **`check` / `status`:** Read-only health check — same diagnostic scan as the default but prints the findings table and exits without prompting to make changes.
- **`stats`:** Project state dashboard — walks the sharded state tree for counts of epics, sprints, and stories by status, backlog size by severity, and last closed sprint/epic. No files changed.
- **`backlog`:** Lists all items in the `backlog:` list of `{pm_state_root}/issues.yaml` in a readable table grouped by severity. No files changed.

**One-time migrations (run in this order)**
- **`migrate-schema`:** *(legacy-only)* Upgrades an existing legacy flat `sprint-status.yaml` to the current field schema — adds missing fields with zero/empty defaults, never overwrites existing values.
- **`split-status`:** *(legacy-only)* Splits a legacy flat `sprint-status.yaml` into the three-file `sprint-status{,-backlog,-archived}.yaml` form, partitioning every epic/sprint by status. The PM skills do **not** read these files — this is an intermediate shape that lets `reconcile-status` clean up a messy flat file before `migrate-state` consumes it. One-time; the original is preserved as `sprint-status.yaml.legacy`.
- **`migrate-state`:** Migrates from either legacy layout (flat `sprint-status*.yaml`, or legacy per-epic `_bmad/state/`) to the sharded state tree under `{implementation_artifacts}/state/`. Preserves originals as `.legacy` files.

**Ongoing maintenance (safe to repeat)**
- **`normalize`:** Convenience shortcut — runs `reconcile-status` then `sort-status` in one confirmed pass. Use for routine maintenance instead of running two commands separately.
- **`reconcile-status`:** *(legacy-only)* Audits the three split status files for placement and structure issues: epics in the wrong file for their `status`, nested per-epic `backlog:` arrays that should be flattened into the consolidated top-level list, stale backlog items whose status is no longer `backlog`, and empty epic shells in the backlog file. Dry-run first; confirms before writing. Safe to run at any time.
- **`sort-status`:** Validates state file and directory naming against the zero-padded convention (`epic-{nnn}/`, `sprint-{nn}/`, `E{nnn}-S{nn}-{nnn}.yaml`). Ordering itself can no longer drift under the sharded layout — directory listing order is correct order — so this mode no longer reorders anything. It reports misnamed entries, which would sort incorrectly and break key resolution.
- **`layout-cleanup`:** Runs only the artifact layout reorganization (the original default behavior) — reorganizes flat artifact outputs into the structured epic/sprint folder hierarchy, reconciles references, verifies state consistency.

**Source & external sync**
- **`harvest-debt`:** Greps the whole source tree for `bmad-defer:` deferred-shortcut markers (the comment crumbs developers and dev subagents leave when they take an intentional simplification) and harvests them into the consolidated `backlog:` list so deferrals do not rot into "later means never." Language-generic — recognizes the comment syntax of every common language. Re-runnable: dedupes against already-harvested markers. Report-only by default; backlog merge is confirmed. Respects `harvest_exclude_dirs` in the `l3io-util` config section for additional exclusions beyond the built-in list.
- **`update-ai-rules`:** Scans for AI system instruction files in the project (`CLAUDE.md`, `.github/copilot-instructions.md`, `GEMINI.md`, `AGENTS.md`, `.cursorrules`, and others) and rewrites any reference to a legacy state layout (flat `sprint-status*.yaml`, the three-file split, or `_bmad/state/`) to describe the current sharded state tree. For files that already exist: updates existing references. For the currently running AI system's file if it does not exist: creates it with a state layout section. Never creates files for other AI systems. Also auto-invoked after a successful `split-status` run. Safe to run repeatedly.

**Setup & housekeeping**
- **`clean-legacy`:** Removes migration backup files and directories left behind by one-time migration commands — `.yaml.legacy` files, `.v1` calibration backups, the pre-migration `_bmad/state.legacy/` directory and `_bmad/pm-calibration.yaml.legacy` file, and the `_bmad/migration-backup/` directory `migrate-state` Stage F's default "move" option relocates everything into. Dry-run first; confirms before deleting. Safe to run once migrations have been verified.
- **`rename-active`:** Renames `sprint-status-active.yaml` → `sprint-status.yaml`. Rarely needed directly — the health check detects and runs this automatically when the old naming is found.
- **`rename-epic-dirs`:** Renames legacy two-digit `epic-{nn}/` artifact directories to the current three-digit `epic-{nnn}/` form. Rarely needed directly — the health check detects and runs this automatically when the old naming is found.

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
| `rename-epic-dirs` | [Rename Epic Dirs Mode](#rename-epic-dirs-mode) |
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
  backlog            List issues.yaml backlog items grouped by severity

One-time migrations (run in this order)
  migrate-schema     (legacy-only) Add missing fields to a legacy flat sprint-status.yaml
  split-status       (legacy-only) Split flat sprint-status.yaml into the 3-file form
  migrate-state      Migrate either legacy layout to the sharded state tree  <- the one
                     that makes a legacy project usable by the PM skills again

Ongoing maintenance (safe to repeat)
  normalize          Reconcile then sort all status files in one pass
  reconcile-status   (legacy-only) Fix misplaced epics, nested backlogs, stale items
  sort-status        Validate zero-padded naming (epic-{nnn}/, sprint-{nn}/, story keys)
  layout-cleanup     Reorganize flat artifact files into epic/sprint folder structure

Source & external sync
  harvest-debt       Sweep source for bmad-defer: markers and harvest into backlog
  update-ai-rules    Update AI instruction files to describe the sharded state tree

Setup & housekeeping
  setup              Register l3io-util module config for this project
  clean-legacy       Remove .legacy/.v1 migration backup files and the state.legacy/ and
                     migration-backup/ backup directories after confirmation
  rename-active      (Rarely needed) Rename sprint-status-active.yaml → sprint-status.yaml;
                     the health check detects and runs this automatically when needed.
  rename-epic-dirs   (Rarely needed) Rename legacy epic-{nn}/ dirs to epic-{nnn}/; the health
                     check detects and runs this automatically when needed.

Run without arguments to let the health check decide what's needed.
```

If `{project-root}/_bmad/config.yaml` does not have an `l3io-util` section, load `assets/module-setup.md` to register the module first.

Load config from `{project-root}/_bmad/config.yaml` and `{project-root}/_bmad/config.user.yaml` (root level and `l3io-util` section). Resolve:
- `implementation_artifacts`
- `planning_artifacts`
- `output_folder`

If `implementation_artifacts` is not set, default to `{output_folder}/implementation-artifacts`.

Then bind the state paths every mode below uses (identical to the PM skills' bindings —
see `skills/_shared/status-files.md` §10, the canonical contract):

- `{pm_state_root}` = `{implementation_artifacts}/state`
- `{pm_issues_file}` = `{pm_state_root}/issues.yaml`
- `{pm_calibration_file}` = `{pm_state_root}/pm-calibration.yaml`

**Current vs. legacy-only modes.** The sharded state tree under `{pm_state_root}` is the
layout the PM skills read and write today; they hard-block on anything else. Three modes
here — `migrate-schema`, `split-status`, `reconcile-status` — operate on the **legacy flat**
`sprint-status*.yaml` files only. They exist to bridge a repo that has not migrated yet, and
they are dead ends on a migrated repo. Where a mode is legacy-only it says so in its own
header; do not read those sections as descriptions of current behaviour.

## Project Health Check

The default mode — runs when no recognized keyword is passed, or when `check`/`status` is passed. Scans the project and reports what needs attention in a structured table. When not in read-only mode (`check`/`status`), proposes the ordered set of actions and executes them after a single confirmation.

### Step HC1 — Load config

Load config same as described above under On Activation.

### Step HC2 — Scan (11 checks, read-only)

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
Count which of the three state layouts are present: sharded (`{pm_state_root}` i.e.
`{implementation_artifacts}/state/` exists), legacy per-epic (`{project-root}/_bmad/state/`
exists), legacy flat (`sprint-status*.yaml` exists in `{implementation_artifacts}/`).
- Only sharded present, or none present (new project) → ✓
- Exactly one legacy layout present, sharded absent → flag `migrate-state` · Priority: High
  (runs after `split-status` if both are flagged)
- More than one layout present → flag `migrate-state` · Priority: Critical — an interrupted
  migration left state in two places; do not run any other action until this is resolved

**Check 3 — Status file schema**
For each present status file, spot-check the first epic node and first sprint node for missing required fields (the full field list is in Schema Migration Mode Step M2). If any required field is absent, the full `migrate-schema` analysis is needed.
- Gaps detected → flag `migrate-schema` · Priority: Medium (run before `split-status` if both are needed)
- No gaps → ✓

**Check 4 — Artifact layout**
Scan the top level of `{implementation_artifacts}` and `{planning_artifacts}` for flat classifiable files (story files matching heuristic 1, sprint/epic closure files matching heuristics 2–3, test files matching heuristic 4, misplaced planning docs matching heuristic 5 — all from [File Classification Heuristics](#file-classification-heuristics)).
- Flat classifiable files found → flag `layout-cleanup` · Priority: Medium · note count
- None → ✓

**Check 5 — State file naming**
If `{pm_state_root}` exists, run the naming validation from Sort Status Mode Step SO2 over it.
- Misnamed entries found → flag `sort-status` · Priority: Low
- No `{pm_state_root}` yet, or all names valid → ✓

**Check 6 — Deferred code markers**
Run the `bmad-defer:` grep from Harvest Debt Mode (Step H2 grep command). Dedupe against the existing `backlog:` list (Step H3 logic). Count new (unharvested) markers.
- New markers found → flag `harvest-debt` · Priority: Low · note count
- None or all already harvested → ✓

**Check 7 — AI instruction references**
Run the scan from Update AI Rules Mode Step AR1 across all well-known instruction file locations.
- Stale legacy state references found (flat `sprint-status*.yaml`, the three-file split, or `_bmad/state/`) → flag `update-ai-rules` · Priority: Low · list files
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
Scan `{implementation_artifacts}/` for `*.yaml.legacy` files (e.g., `sprint-status.yaml.legacy`); `{project-root}/_bmad/` for `*.yaml.v1` calibration backups (e.g., `pm-calibration.yaml.v1`) and for `pm-calibration.yaml.legacy`; and `{project-root}/_bmad/` for the `state.legacy/` and `migration-backup/` backup directories left by `migrate-state` (see Clean Legacy Mode's Step CL1 for exactly what each holds).
- Any found → flag `clean-legacy` · Priority: Low · note count (files and directories separately)
- None → ✓

**Check 10 — Epic directory padding (legacy two-digit form)**
Scan the top level of `{implementation_artifacts}/` for directories matching `epic-[0-9][0-9]`
(exactly two digits).
- Any found → flag `rename-epic-dirs` · Priority: **High** · list directories — state path
  resolution (`epic-{nnn}` under `state/`) and the state/artifact mirror both depend on the
  three-digit form; a two-digit `epic-{nn}/` will never match its `state/{status}/epic-{nnn}/`
  counterpart or be found by Check 11's drift diff.
- None → ✓

**Check 11 — State/artifact drift**
`{pm_state_root}` = `{implementation_artifacts}/state` (see `skills/_shared/status-files.md`,
the canonical state-layout contract, for the full sharded schema this check reads). For each
sprint directory under `{pm_state_root}/{planned,active,archived}/epic-{nnn}/sprint-{nn}/`,
compare story state files against story artifacts by basename. Only `active/` and `archived/` are
checked — a `planned/` epic legitimately has state and no artifacts yet (stories are authored after
planning), so that asymmetry is not drift:

```bash
diff <(ls {pm_state_root}/{active,archived}/epic-{nnn}/sprint-{nn}/*.yaml 2>/dev/null \
        | xargs -n1 basename | sed 's/.yaml//' | grep -v '^sprint$') \
     <(ls {implementation_artifacts}/epic-{nnn}/sprint-{nn}/stories/*.md 2>/dev/null \
        | xargs -n1 basename | sed 's/.md//')
```

Lines starting `<` are state files with no story artifact; lines starting `>` are story
artifacts with no state. Also flag any story or sprint file whose `epic:`/`sprint:`
back-reference disagrees with the directory it was found in.
- Any mismatch found → flag for report · Priority: **Medium** · list the orphaned keys —
  report only, **never auto-correct**: an orphan on either side needs a human decision about
  which side is right (a dropped story file vs. an abandoned state node look identical from
  the diff alone).
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
Epic directory padding          ⚠ 1 legacy epic-{nn}/ dir       rename-epic-dirs
State/artifact drift            ⚠ 2 orphaned key(s)             — (report only)
================================================================
```

If flagged items exist, append the recommended execution sequence (only flagged actions shown, in priority order):
```
Recommended actions (in order): rename-active → rename-epic-dirs → reconcile-status → layout-cleanup → harvest-debt
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
2. `rename-epic-dirs`
3. `migrate-schema`
4. `split-status`
5. `migrate-state`
6. `reconcile-status`
7. `layout-cleanup`
8. `sort-status`
9. `harvest-debt`
10. `update-ai-rules`
11. `clean-legacy`

Before each action, print a separator header:
```
─── Running: {action-name} ──────────────────────────────────
```

Each action runs its full mode implementation from its own section. **Suppress the per-mode confirmation prompts** — the user already confirmed in HC5; proceed as if they answered yes at each mode's own confirm step. The per-mode dry-run output and verify steps still run and are shown.

If any action fails (exits with FAILED), stop and report — do not run remaining actions.

**State/artifact drift (Check 11) is report-only** — it never appears in this execution list.
It has no fixer action; its findings surface in Step HC3's table for the user to resolve by
hand (author the missing story, or clean up the orphaned state node).

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

There are two mirrored trees under `{implementation_artifacts}/` — `state/` (machine-written
status/estimate/actual data, see `skills/_shared/status-files.md` for the full schema) and the
top-level `epic-{nnn}/` directories (human/agent-authored artifacts, the ones this skill
reorganizes). They share an identical path suffix — `epic-{nnn}/sprint-{nn}/...` — which is
what lets Health Check 11 diff the two sides directly.

```
{implementation_artifacts}/
├── state/                                   ← machine-written, pm-status.py only — reference only
│   ├── planned/epic-{nnn}/epic.yaml, sprint-{nn}/sprint.yaml, sprint-{nn}/{story-key}.yaml
│   ├── active/epic-{nnn}/...                 (same shape as planned/, one dir per active epic)
│   ├── archived/epic-{nnn}/...               (same shape as planned/, one dir per archived epic)
│   ├── issues.yaml
│   └── pm-calibration.yaml
│
└── epic-{nnn}/                               ← human/agent-authored artifacts (this skill's domain,
    │                                            one such directory per epic)
    ├── sprint-{nn}/
    │   ├── stories/{story-key}.md
    │   ├── closure/...
    │   └── tests/...
    ├── tests/...
    └── epic-closure/...
```

```
{planning_artifacts}/epic-{nnn}/...
{planning_artifacts}/epic-{nnn}/sprint-{nn}/...
```

`nnn` is a zero-padded three-digit epic number (`001`, `002`) and `nn` a zero-padded two-digit
sprint number (`01`, `02`), matching the epic key `E{nnn}` and sprint key `S{nn}`.

This skill never writes under `state/` — that tree is owned exclusively by `pm-status.py`.
It is shown here only so the mirror (and Health Check 11's drift comparison) is clear.

## Safety Rules

- Dry-run first — show full cleanup plan before changing any files
- Never overwrite an existing destination file
- If destination exists: keep source in place, record conflict
- Preserve file contents exactly — move only, no edits
- Reference updates: auto-update only exact old-path matches that map to one known moved file; if ambiguous, record for manual review — never auto-update ambiguous references

## File Classification Heuristics

1. **Story files** (flat implementation root): regex `^([0-9]+)-[0-9]+.*\.md$` — epic from first capture group; default sprint = `01` unless user provides mapping. Move to: `epic-{nnn}/sprint-{nn}/stories/{story-key}.md`
2. **Sprint closure files** (flat implementation root): patterns `epic-*-sprint-*-retro-*.md`, `*-sprint-*-adversarial-*.md`, `*-sprint-*-redteam-*.md`, `*-sprint-*-clean-release-*.md`, `*-sprint-*-ux-review-*.md`, `*-sprint-*-arch-drift-*.md`. Move to: `epic-{nnn}/sprint-{nn}/closure/{filename}`
3. **Epic closure files** (flat implementation root): patterns `epic-*-adversarial-*.md` (epic-scoped), `epic-*-redteam-*.md`, `epic-*-arch-drift-*.md`, `epic-*-functional-completeness-*.md`, `epic-*-clean-release-*.md`, `epic-*-ux-review-*.md`. Move to: `epic-{nnn}/epic-closure/{filename}`
4. **Test evidence files** (flat roots): patterns `*qa*.md`, `*test*.md`, `*verification*.md`. Sprint-scoped → `epic-{nnn}/sprint-{nn}/tests/`. Epic-scoped → `epic-{nnn}/tests/`.
5. **Planning artifacts** (misplaced under `{planning_artifacts}` or `{implementation_artifacts}`): covers brainstorming, architecture, research, UX specs, and requirements docs — never story or epic tracking files (those are implementation artifacts). Classify by filename pattern:
   - **Architecture**: `*architecture*`, `*arch-spec*`, `*system-design*`, `*tech-design*`
   - **Requirements / PRD**: `*requirements*`, `*prd*`, `*brief*`, `*spec*` (excluding story files matched by heuristic 1)
   - **UX spec**: `*ux-spec*`, `*ux-design*`, `*wireframe*`, `*mockup*`, `*ui-spec*`
   - **Research / spike**: `*research*`, `*spike*`, `*investigation*`, `*discovery*`
   - **Brainstorming**: `*brainstorm*`, `*ideation*`, `*mind-map*`
   Determine placement scope from the filename: if `sprint-{nn}` or `sprintSS` is present → `{planning_artifacts}/epic-{nnn}/sprint-{nn}/{filename}`; otherwise → `{planning_artifacts}/epic-{nnn}/{filename}`. If epic cannot be inferred from the filename, ask for a mapping before proceeding.
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
- Epic and sprint folder names are zero-padded (`epic-001` not `epic-01` or `epic-1`, `sprint-02` not `sprint-2`)
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
Status file ordering: {N} issue(s) detected in {files} — no automated fix; this split-file
  layout predates the sharded state/ convention, where ordering can't drift. Reorder the
  list(s) manually, or run `migrate-state` to move to the sharded layout.
```
If all files are in order, append:
```
Status file ordering: ✓ all files sorted correctly
```

### Step 8 — Deferred Work Files

For each epic that has conflicts, unclassified files, or manual-review reference items, write a consolidated deferred work file:

```
{implementation_artifacts}/epic-{nnn}/cleanup-deferred.md
```

Format:
```markdown
# Cleanup Deferred Work — Epic {nnn}
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

**Legacy-only mode — bridging step, not the current layout.**

Invoked with `split-status` argument. Splits a single legacy flat `sprint-status.yaml` into
the three-file `sprint-status{,-backlog,-archived}.yaml` layout. One-time, one-way. The
original is never deleted — it is renamed to `sprint-status.yaml.legacy` as the rollback.
All [Safety Rules](#safety-rules) apply: dry-run first, never overwrite an existing
destination, preserve node contents exactly.

**The PM skills do not read or write these three files.** They read the sharded state tree
at `{pm_state_root}` and hard-block on any legacy layout (`skills/_shared/status-files.md`
§10). The three-file split is an *intermediate* form on the way there: it is a convenient
shape for `reconcile-status` to clean up a messy flat file before `migrate-state` consumes
it, and `migrate-state` reads all three as one logical set. Nothing else consumes them.

Do not run this mode expecting it to make a project usable — `migrate-state` is what does
that. Run this only if you need `reconcile-status` on a legacy flat file first. On a project
that has already migrated there is nothing here to do; run `/l3io-util-cleanup migrate-state`
or nothing at all.

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

**Step S8 — Post-split ordering note**

The split preserves each node's original order exactly — nothing is reordered during the
split, so if the source `sprint-status.yaml` was already out of order, that carries through
unchanged. [Sort Status Mode](#sort-status-mode) no longer covers this: it validates naming in
the sharded `{pm_state_root}` tree, not ordering in this split-file layout. There is no
automated ordering fix for the split layout; append to the report:
```
Ordering: preserved from source order (not validated — sort-status covers the sharded
  state/ layout only, not this split-file layout)
```

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

Bind `{status_backlog}` = `{pm_issues_file}` (`{pm_state_root}/issues.yaml`) — the single flat
deferred-issue list of the current layout. Then check for a legacy layout using the same
three-way count Check 2b uses, and refuse to write past one:

1. If a legacy layout is present (legacy flat `sprint-status*.yaml`, or legacy per-epic
   `_bmad/state/`) and `{pm_state_root}` does not exist → print:
   ```
   State is still on a legacy layout — harvest-debt writes to {pm_issues_file}, which does
   not exist yet. Run /l3io-util-cleanup migrate-state first, then re-run harvest-debt.
   ```
   and exit (never write into a legacy file).
2. Else → `{status_backlog}` is the target. It is created lazily in Step H6 if absent,
   containing only a top-level `backlog:` list (the shape `append-issue` writes).

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
truth). Prefer writing each item through `uv run {project-root}/_bmad/scripts/pm-status.py append-issue --file {pm_issues_file} ...` when that script is present — it appends under an exclusive flock, which is what makes `issues.yaml` safe as the one shared-append target. Generate keys by continuing the highest existing `BL-E000-{nnn}` suffix (check existing items with `epic: '000'`; also check for any legacy `DEBT-NN` or narrower-padded `BL-E00-NN` items to avoid gap collisions, parsing sequence numbers numerically):

```yaml
- key: BL-E000-001                     # BL-E000-{nnn} — repo-global, not epic-scoped
  epic: '000'                          # '000' = repo-global marker
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

Invoked with `sort-status` argument. Validates state file and directory naming in the sharded
`{pm_state_root}` tree against the zero-padded convention. **Read-only** — reports misnamed
entries, does not rename or reorder anything. Ordering itself can no longer drift under the
sharded layout: nodes are individual files, and zero-padded names (`epic-{nnn}`, `sprint-{nn}`,
`E{nnn}-S{nn}-{nnn}`) make directory-listing order the correct order, so there is no separate
sort step the way there was when a whole epic's sprints and stories lived as one YAML list
that could be edited out of order. What *can* still go wrong is a misnamed entry — created or
edited outside `pm-status.py` — and a misnamed entry is not cosmetic: `pm-status.py` resolves
every node path from its key, so a wrongly-padded directory or file is silently unreachable by
key lookup rather than merely out of order. That is what this mode checks for.

If you want a rename applied rather than just reported, the two-digit legacy epic form is
fixed by [Rename Epic Dirs Mode](#rename-epic-dirs-mode) (`rename-epic-dirs`) — this mode does
not duplicate that rename logic itself.

**Naming convention checked:**

| Entry | Expected form |
|---|---|
| Epic directory | `epic-{nnn}` — exactly three digits |
| Sprint directory | `sprint-{nn}` — exactly two digits |
| Story file | `E{nnn}-S{nn}-{nnn}.yaml` |
| Epic node file | `epic.yaml` (exactly one per epic directory) |
| Sprint node file | `sprint.yaml` (exactly one per sprint directory) |

### Steps

**Step SO1 — Load config and resolve state root**

Load config (same as layout cleanup). Resolve `{pm_state_root}` = `{implementation_artifacts}/state`.

If `{pm_state_root}` does not exist:
```
No state directory found at {pm_state_root} — nothing to validate.
```
Exit. (State is created lazily by `pm-status.py` on first write — there is no separate setup
command to point to, and `split-status` is a decommissioned migration path for a different,
older layout; do not suggest it here.)

**Step SO2 — Walk and validate naming**

Walk `{pm_state_root}/{planned,active,archived}/`. For each entry found, check:
1. Each top-level directory matches `epic-[0-9]{3}` exactly (three digits). Flag deviations —
   most commonly the legacy two-digit `epic-{nn}` form, but also unpadded or non-numeric
   suffixes.
2. Within each epic directory, each subdirectory matches `sprint-[0-9]{2}` exactly (two
   digits). Flag deviations.
3. Within each sprint directory, every `.yaml` file other than `sprint.yaml` matches
   `E[0-9]{3}-S[0-9]{2}-[0-9]{3}\.yaml` exactly. Flag deviations.
4. Each epic directory contains exactly one `epic.yaml`; each sprint directory contains
   exactly one `sprint.yaml`. Flag missing or duplicate node files.
5. Each story filename's embedded `E{nnn}-S{nn}` segment matches the epic/sprint directories
   it was found under. Flag mismatches. (This checks the *filename* against its path; Health
   Check 11's back-reference check reads the file's *contents* against its path — the two are
   independent and both worth running.)

Accumulate all findings as `{naming_issues}`.

**Step SO3 — Report**

If `{naming_issues}` is empty:
```
STATE NAMING CHECK — {pm_state_root}
  planned/:  {p_epics} epic(s) — ✓ all names valid
  active/:   {a_epics} epic(s) — ✓ all names valid
  archived/: {r_epics} epic(s) — ✓ all names valid
Ordering is not checked separately — zero-padded names make directory-listing order the
correct order, so there is nothing that can drift the way a YAML list could.
```
Exit.

Otherwise:
```
STATE NAMING ISSUES — {pm_state_root}
================================================================
Path                                              Issue
----------------------------------------------------------------
{pm_state_root}/active/epic-01/                   expected epic-{nnn} (three digits)
{pm_state_root}/active/epic-001/sprint-1/         expected sprint-{nn} (two digits)
{pm_state_root}/active/epic-001/sprint-01/E1-S01-002.yaml   expected E{nnn}-S{nn}-{nnn}.yaml
...
================================================================
{N} naming issue(s) found. Report only — this mode does not rename or move anything.
Two-digit epic-{nn}/ directories: fix with `/l3io-util-cleanup rename-epic-dirs`.
Other naming issues need manual correction — they usually mean a file was created or edited
outside pm-status.py.
```

```
DONE — State naming check complete.
  Issues found: {N}  (0 means state is clean)
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

## Rename Epic Dirs Mode

Invoked with `rename-epic-dirs` argument. One-time-per-occurrence migration for epic artifact
directories still using the legacy two-digit form (`epic-{nn}/`). Renames each to the current
three-digit form (`epic-{nnn}/`) so it matches the epic key `E{nnn}` and its
`state/{status}/epic-{nnn}/` counterpart — the identical-path-suffix property the state/artifact
drift check (Health Check 11) depends on. Content is not changed — directory name only.

### Steps

**Step RE1 — Load config and scan**

Load config (same as layout cleanup). Scan the top level of `{implementation_artifacts}/` for
directories matching `epic-[0-9][0-9]` (exactly two digits).

If none found:
```
No legacy two-digit epic-{nn}/ directories found — nothing to rename.
```
Exit.

**Step RE2 — Dry-run**

For each matched directory, compute the three-digit destination by zero-padding the epic
number. If that destination already exists, record a conflict instead of a rename (skip it;
never overwrite).

```
RENAME EPIC DIRS DRY RUN
================================================================
{implementation_artifacts}/epic-{nn}/  →  {implementation_artifacts}/epic-{nnn}/
...
================================================================
{N} director(y/ies) to rename, {C} conflict(s) (destination already exists — skipped).
Contents unchanged — directory name only.
```

If `{N}` is 0 (all conflicts): print the conflict list and exit without prompting.

**Step RE3 — Confirm**

Ask: "Rename {N} epic director(y/ies) to the three-digit form? Conflicts are skipped."

If no: print `Rename cancelled — no changes made.` and exit.

**Step RE4 — Rename**

For each non-conflicting directory, rename `epic-{nn}/` → `epic-{nnn}/`. Log each rename.

**Step RE5 — Verify**

Re-scan `{implementation_artifacts}/` top level. Confirm no `epic-[0-9][0-9]` (two-digit)
directories remain except recorded conflicts.

**Step RE6 — Report**

```
DONE — Rename epic dirs complete.
  Renamed:   {n} director(y/ies)
  Conflicts: {n} (destination already existed — left in place; list if > 0)
```

If conflicts remain, note that they need manual resolution (merge or remove one side) before
Health Check 11's drift comparison can be trusted for that epic.

---

## Update AI Rules Mode

Invoked with `update-ai-rules` argument, or automatically from [Split Status Mode](#split-status-mode) Step S9. Scans for AI system instruction files in the project and updates any references to a **legacy** state layout — the flat `sprint-status*.yaml` files or the legacy per-epic `_bmad/state/` tree — so they describe the **current sharded state tree** under `{pm_state_root}`. For instruction files that already exist: updates existing references. For the currently running AI system's file that does not yet exist: creates it with a state layout section. Never creates instruction files for other AI systems. Safe to run repeatedly — already-updated files are skipped.

**This mode writes into the consuming repo's own instruction files, and those files then
steer every future agent in that repo.** It must therefore only ever emit the current
layout. Emitting the decommissioned three-file layout here would teach every agent in the
consuming repo to look for files the PM skills hard-block on.

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

A reference is flagged for update if it names any legacy state location — `sprint-status.yaml`, `sprint-status-backlog.yaml`, `sprint-status-archived.yaml`, `sprint-status-planned.yaml`, `sprint-status-issues.yaml`, `E{nnn}-status.yaml`, or `_bmad/state/` — and is NOT immediately followed by `.legacy`. A reference is already current, and skipped, when its paragraph or section describes the sharded tree (mentions `state/active/`, `state/planned/`, `state/archived/`, or `{pm_state_root}`).

Note the direction of travel: the three-file split (`sprint-status-backlog.yaml` / `sprint-status-archived.yaml`) is itself a **legacy** layout now and is flagged for update, not treated as the target.

### Steps

**Step AR1 — Scan**

Check each well-known instruction file location. For each file that exists, grep for `sprint-status[-a-z]*\.yaml`, `E[0-9]*-status\.yaml`, and `_bmad/state` (case-sensitive) and collect all matches with surrounding context (2 lines before/after). Apply the detection rule. Build a findings list: `{file}` + `{line}` + `{context}`.

Also determine the current AI runtime (Claude, Copilot, Gemini, etc.) from execution context. If the current runtime's instruction file does not exist and was not found above, add it to a `{to_create}` list.

If no existing instruction files found AND `{to_create}` is empty: print `No AI instruction files found — nothing to update.` and exit.

If existing files found but no flagged references AND `{to_create}` is empty: print `AI instruction files are already current — no legacy state-layout references detected.` listing files checked, and exit.

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

- **Inline path** (e.g., `some/path/sprint-status.yaml`): replace the path with `{pm_state_root}` (rendered as the project's actual relative path, e.g. `docs/implementation-artifacts/state/`) and append ` (sharded state tree — one YAML file per epic/sprint/story)`.
- **Standalone keyword** (e.g., "reads sprint-status.yaml"): replace with a brief description: "the sharded state tree under `{pm_state_root}` — `active/epic-{nnn}/`, `planned/epic-{nnn}/`, `archived/epic-{nnn}/`, one YAML file per node".
- **Section or block** describing the state files: replace the entire description block with the state layout section from Step AR5 below, preserving surrounding format.

Read 3 lines of surrounding context before choosing the replacement strategy. Write the updated content to disk.

**Step AR5 — Create new file for current runtime**

For each file in `{to_create}`, create the file (and any parent directories, e.g. `.github/`) and write a minimal AI instruction section covering the PM state file layout:

````markdown
## BMad PM — State File Layout

Epic, sprint, and story state lives in a **sharded state tree** under `{pm_state_root}`
(`{implementation_artifacts}/state/`) — one bare YAML file per node, committed to git:

```
state/
├── planned/epic-{nnn}/     ← status: backlog
├── active/epic-{nnn}/      ← status: in-progress
│   ├── epic.yaml
│   └── sprint-{nn}/
│       ├── sprint.yaml
│       └── E{nnn}-S{nn}-{nnn}.yaml
├── archived/epic-{nnn}/    ← status: done
├── issues.yaml             ← flat deferred-issue backlog (BL-E{nnn}-{nnn})
└── pm-calibration.yaml
```

- **An epic's directory lives in the folder named for its status.** Every status transition is a directory move, so `git log --follow` keeps working across it.
- **The directory structure replaces child lists** — `epic.yaml` has no `sprints:` key and `sprint.yaml` has no `stories:` key. Children are discovered by listing the directory.
- **State is written only by `pm-status.py`**, addressed by node key, never by hand-built path:
  `uv run _bmad/scripts/pm-status.py set-status --state-root {pm_state_root} --story E001-S01-003 --status done`
- Do not hand-edit these files, and do not create parallel status files.

Older layouts (a flat `sprint-status*.yaml`, or a per-epic `_bmad/state/` tree) are legacy. Migrate with `/l3io-util-cleanup migrate-state`.
````

Adapt the heading style and surrounding content to match the existing file format for that AI system.

**Step AR6 — Verify and report**

Re-read each updated and created file. Confirm no legacy state reference (per the Detection rule — `sprint-status*.yaml`, `E{nnn}-status.yaml`, `_bmad/state/`, non-`.legacy`) remains. If any remain, list them as unresolved.

```
DONE — AI rules update complete.
  References updated: {N} across {M} file(s)
  Files created:      {C}
  Unresolved:         {U} (list if > 0)
  Files checked (no changes needed): {files}
```

---

## Normalize Mode

Invoked with `normalize` argument. Convenience shortcut that runs [Reconcile Status Mode](#reconcile-status-mode) (if the legacy split layout is present) and the naming check from [Sort Status Mode](#sort-status-mode) (if sharded state is present) in one pass. The two operate on different, unrelated layouts — reconcile on the legacy split status files, naming-check on the current sharded `{pm_state_root}` tree — so normalize simply runs whichever applies and reports both; a fully-migrated project with no split files left still gets a useful naming check. Use for routine maintenance instead of running the two commands separately.

### Steps

**Step NM1 — Load config and detect layouts present**

Load config (same as layout cleanup). Determine what's present:
- Split layout: any of `sprint-status.yaml`, `sprint-status-backlog.yaml`, `sprint-status-archived.yaml` exists in `{implementation_artifacts}/`.
- Sharded state: `{pm_state_root}` (`{implementation_artifacts}/state`) exists.

If neither is present:
```
No split layout and no sharded state found — nothing to normalize.
```
Exit.

**Step NM2 — Reconcile (only if split layout present)**

If the split layout is present: run the full Reconcile Status Mode (Steps RC1–RC7) with one modification: **present the dry-run report but defer confirmation** — print the reconcile findings and the naming-check findings together in Step NM4 before asking to proceed.

If the split layout is absent, skip reconcile and carry forward "Reconcile: — (no split layout present)" for Step NM4/NM6.

**Step NM3 — Naming analysis (only if sharded state present)**

If `{pm_state_root}` is present: run Sort Status Mode's naming validation (Steps SO1–SO2). Collect `{naming_issues}`.

If `{pm_state_root}` is absent, carry forward "Naming check: — (no sharded state present)".

**Step NM4 — Combined dry-run and confirm**

Print the reconcile dry-run output (or its not-applicable note) followed by the naming-check
report (or its not-applicable note). Naming issues are report-only — there is nothing to
confirm for them, only reconcile changes need a confirmation:

```
Apply {reconcile_total} reconciliation change(s)?
  Y — proceed
  n — exit, no changes
```

If `n`: print `Normalize cancelled — no changes made.` and exit.

If `{reconcile_total}` is 0 (nothing to apply — regardless of any naming issues found, which
were already shown above and need no confirmation): print `✓ Nothing to reconcile.` and exit
without prompting.

**Step NM5 — Execute reconcile**

If reconcile has changes: apply Steps RC5–RC7 (execute, verify, report). On failure, stop and report.

**Step NM6 — Summary**

```
DONE — Normalize complete.
  Reconcile: {reconcile summary line, or "not applicable — no split layout"}
  Naming:    {N} issue(s) found (or "✓ clean", or "not applicable — no sharded state")
```

---

## Stats Mode

Invoked with `stats` argument. Read-only project state dashboard — walks the sharded state
tree and prints counts. No files are changed.

### Steps

**Step ST1 — Load config and detect layout**

Load config (same as layout cleanup). Run the same three-way count Check 2b uses:

```bash
SHARDED=$([ -d "{pm_state_root}" ] && echo 1 || echo 0)
LEGACY_EPIC=$([ -d "{project-root}/_bmad/state" ] && echo 1 || echo 0)
LEGACY_FLAT=$([ -f "{implementation_artifacts}/sprint-status.yaml" ] && echo 1 || echo 0)
```

- **Sharded present** → walk it (Step ST2). This is the normal path.
- **Sharded absent, a legacy layout present** → the dashboard cannot read it. Print and exit:
  ```
  State is still on a legacy layout ({legacy per-epic | legacy flat}) — stats reads the
  sharded state tree at {pm_state_root}. Run /l3io-util-cleanup migrate-state first.
  ```
- **Nothing present** → print `No state found at {pm_state_root} — nothing to report.` and exit.

**Step ST2 — Walk the sharded tree and count**

The tree is one bare-node YAML file per node; the directory structure *is* the child list
(`skills/_shared/status-files.md` §4). Enumerate:

```bash
ls -d {pm_state_root}/{planned,active,archived}/epic-*/ 2>/dev/null
```

For each epic directory: read `epic.yaml`; for each `sprint-{nn}/` inside it read
`sprint.yaml`; for each `*.yaml` in that sprint directory other than `sprint.yaml` read the
story node. Accumulate:

- **Epics** by `status` (backlog, in-progress, done) — count per status, total. The status
  folder and the node's `status` agree by construction (`planned`→backlog, `active`→in-progress,
  `archived`→done); if any epic disagrees with its folder, note it as a placement anomaly.
- **Sprints** by `status` (backlog, in-progress, done) — count per status, total.
- **Stories** by `status` (backlog, ready-for-dev, in-progress, review, done) — count per status, total.
- **Backlog items** — the `backlog:` list in `{pm_issues_file}` — count by severity (Critical, High, Medium, Low, unknown), total. Absent file = zero items, not an error.
- **Last closed sprint** — across all epics, the highest `epic-{nnn}/sprint-{nn}` whose `sprint.yaml` has `status: done` (lexical order over the zero-padded names is the correct order — §8).
- **Last closed epic** — the highest `epic-{nnn}` under `{pm_state_root}/archived/`; note its key and title.
- **Calibration file** — check `{pm_calibration_file}` (`{pm_state_root}/pm-calibration.yaml` — migrate-state moves it here from `{project-root}/_bmad/`); if present, note its version and the number of scope/closure/fix sample entries.

**Step ST3 — Print dashboard**

```
PROJECT STATE — {pm_state_root}
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
Last sprint closed:  Epic {nnn} / Sprint {nn}  (or "none")
Last epic closed:    E{nnn} — {title}          (or "none")
Calibration file:    {version}, {n} scope samples  (or "not found")
Layout:              Sharded state tree
Placement anomalies: none  (or list epics whose status disagrees with their folder)
================================================================
```

---

## Backlog Mode

Invoked with `backlog` argument. Read-only — lists all items in the consolidated `backlog:` list from the issues file in a readable table grouped by severity. No files are changed.

### Steps

**Step BL1 — Load config and resolve the issues file**

Load config (same as layout cleanup). The backlog lives in `{pm_issues_file}`
(`{pm_state_root}/issues.yaml`) — the single flat deferred-issue list the current layout
uses, written by `pm-status.py append-issue`. If it does not exist, decide which case this is
using the layout detection from Check 2b:

- **A legacy layout is present** (legacy flat `sprint-status*.yaml`, or legacy per-epic
  `_bmad/state/`):
  ```
  No issues file at {pm_issues_file} — this project is still on a legacy state layout.
  Run /l3io-util-cleanup migrate-state to migrate; the backlog is carried over as part of it.
  ```
- **The sharded tree exists but has no issues file yet**, or nothing exists at all:
  ```
  Backlog is empty — no issues file at {pm_issues_file} yet. It is created the first time a
  review defers an item.
  ```

Exit in either case.

**Step BL2 — Parse**

Read the top-level `backlog:` list. If the list is absent or empty, print `Backlog is empty — no items found.` and exit.

**Step BL3 — Print table**

Group items by severity (Critical → High → Medium → Low → unknown). Within each group, sort by `epic` ascending then `key` ascending. Print:

```
BACKLOG — {pm_issues_file}
================================================================
Sev      Key           Epic  Sprint  Title
----------------------------------------------------------------
Critical
  CRIT   BL-E001-001   001   02      {title (truncated to 50 chars)}
  ...
High
  HIGH   BL-E001-002   001   —       {title}
  ...
Medium
  MED    BL-E000-001   000   —       {title}
  ...
Low
  LOW    BL-E002-001   002   03      {title}
  ...
================================================================
Total: {n} item(s)  (Critical: {n}  High: {n}  Medium: {n}  Low: {n})
```

Truncate titles at 50 characters with `…`. Sprint shown as `—` when blank.

---

## Clean Legacy Mode

Invoked with `clean-legacy` argument. Removes migration backup files *and directories* left
behind by one-time migration commands: `.yaml.legacy` files, `.v1` calibration backups, the
pre-migration `state.legacy/` directory and `pm-calibration.yaml.legacy` file `migrate-state`
Stage D leaves at their original `_bmad/` location, and the `migration-backup/` directory
Stage F's default "move" option relocates everything into. Dry-run first; confirms before
deleting. Safe to run once migrations have been verified.

### Steps

**Step CL1 — Load config and scan**

Load config (same as layout cleanup). Scan for:
1. `*.yaml.legacy` files anywhere under `{implementation_artifacts}/` (e.g.,
   `sprint-status.yaml.legacy`, `sprint-status-backlog.yaml.legacy`,
   `sprint-status-archived.yaml.legacy`) — `migrate-state` Stage D's per-file backups,
   present here when the F2 backup disposal chose "K" (keep in place) or has not run yet.
2. `*.yaml.v1` files in `{project-root}/_bmad/` (e.g., `pm-calibration.yaml.v1`) —
   `migrate-schema`'s field-upgrade backups.
3. `{project-root}/_bmad/pm-calibration.yaml.legacy` (file) — `migrate-state` Stage D's
   pre-migration calibration backup, at its original location.
4. `{project-root}/_bmad/state.legacy/` (directory) — `migrate-state` Stage D's whole-tree
   backup of a legacy per-epic `_bmad/state/` source, at its original location.
5. `{project-root}/_bmad/migration-backup/` (directory) — `migrate-state` Stage F2's default
   "move" destination. When present it already holds copies of some/all of items 1, 3, and 4
   (the flat `.legacy` files, `pm-calibration.yaml.legacy`, and `state.legacy/`), relocated
   there in one pass by F2. Treat it as a single item in the scan and report — do not also
   descend into it and list its contents as separate items. Items 1/3/4 above only match
   files/directories at their *original* `_bmad/`-or-`{implementation_artifacts}/` locations,
   so there is no double-counting: a repo that ran F2 with "M" has items 1/3/4 empty and item
   5 present; a repo that chose "K" has items 1/3/4 present and item 5 absent.

If nothing found: print `No legacy backup files or directories found — nothing to clean.` and exit.

**Step CL2 — Dry-run**

For each plain file, get its size (`stat`/`du -h`). For each directory (items 4 and 5), get
its total recursive size (`du -sh`) and a one-line content summary — top-level entry names
plus a recursive file count — so the user sees what is inside *before* agreeing to remove it:

```
CLEAN LEGACY DRY RUN
================================================================
File / Directory                                         Size     Contents
----------------------------------------------------------------
{implementation_artifacts}/sprint-status.yaml.legacy      {size}   —
{project-root}/_bmad/pm-calibration.yaml.v1                {size}   —
{project-root}/_bmad/pm-calibration.yaml.legacy             {size}   —
{project-root}/_bmad/state.legacy/                          {size}   DIR — {n} files (epic-001/, epic-002/, ...)
{project-root}/_bmad/migration-backup/                       {size}   DIR — {n} files (sprint-status.yaml.legacy, state.legacy/, pm-calibration.yaml.legacy)
...
================================================================
{N} file(s) and {M} director(y/ies) to remove. These are migration backups — the live files
are unaffected.
```

**Step CL3 — Confirm**

Ask: "Remove {N} backup file(s) and {M} backup director(y/ies)? This cannot be undone."

If no: print `Clean cancelled — nothing removed.` and exit.

**Step CL4 — Delete**

Delete each file with `rm -f`. Remove each directory with `rm -rf` **only after** its
contents were shown in the Step CL2 dry-run and the user confirmed in Step CL3 — never
remove a directory whose contents the user has not seen. Log each removal individually. If
any removal fails (permissions, locked file), record and continue — do not abort the entire
run.

**Step CL5 — Report**

```
DONE — Clean legacy complete.
  Removed: {n} file(s), {m} director(y/ies)
  Failed:  {n} file(s)/director(y/ies) (list if > 0)
```

---

## Migrate State Mode

Invoked with `migrate-state` argument.

Load `{skill-root}/assets/migrate-state.md` and execute it fully.
