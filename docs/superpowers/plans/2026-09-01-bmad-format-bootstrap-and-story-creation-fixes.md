# BMad Format Bootstrap & Story Creation Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four related bugs: (1) migrate-state says "nothing to migrate" when legacy BMad format is present; (2) story elaboration updates epic.md instead of creating story files; (3) l3io-pm-plan silently finds zero stories when only artifact .md files exist without state YAML; (4) add a bootstrap-state mode that creates state YAML from existing story artifacts.

**Architecture:** Bug 2 is a prompt fix (tell bmad-create-story to create-if-absent). Bugs 3 and 4 are addressed together by a new `bootstrap-state` mode in l3io-util-doctor plus a new pre-flight check in step-02-readiness-check that detects artifact-only stories and blocks with an actionable message. Bug 1 is addressed by adding diagnostic output to migrate-state (showing exactly which paths were checked) and a fourth pre-flight detection case for the artifact-only layout.

**Tech Stack:** Markdown instruction files (LLM step files), no compiled code changes. One bash snippet addition to migrate-state. `npm run sync:scripts` propagates `skills/_shared/steps/**` changes to per-skill copies.

**Spec:** This plan implements the root causes identified in the 2026-09-01 systematic debugging session. The four bugs share a common root: the system has no path from "BMad story .md artifact files" to "l3io-pm sharded state YAML," and the story elaboration instruction assumes artifact files already exist.

## Global Constraints

- All `skills/_shared/steps/**` changes must be propagated via `npm run sync:scripts` before any CI check runs
- Never hand-edit per-skill `steps/` copies — they are generated
- `skills/l3io-util-doctor/assets/` and `steps/` files are NOT shared — edit them directly
- Every mode added to l3io-util-doctor SKILL.md must have a corresponding `steps/` file — never inline
- `npm run check:scripts`, `npm run check:docs`, `npm run check:manifest` must all pass after every task
- Story state YAML must carry required back-references: `epic:` on sprint/story nodes, `epic:` + `sprint:` on story nodes
- All YAML node files are bare (no `epics:` / `sprints:` / `stories:` wrapper)
- `npm run sync:scripts` does NOT regenerate manifests — run `node scripts/write-payload-manifest.mjs` separately after payload changes

---

### Task 1: Fix story elaboration — create-if-absent before enrich

**Files:**
- Modify: `skills/_shared/steps/plan/step-03-story-elaboration.md` (lines 63–75)
- Modify: `skills/_shared/steps/sprint/step-02-story-prep.md` (lines 81–115)

**Interfaces:**
- Consumes: `bmad-create-story` skill (BMad core, not this repo)
- Produces: story `.md` files at `{implementation_artifacts}/epic-{nnn}/sprint-{nn}/stories/{story_key}.md`

**Why this matters:** Both steps pass story file paths to `bmad-create-story` with "enrich in place" or "preserve existing content," which presupposes the files exist. When they don't, the agent falls back to updating the nearest document it can find (`epic.md`). The fix is to explicitly tell the agent to create a minimal skeleton first if the path doesn't exist.

- [ ] **Step 1: Update step-03-story-elaboration.md §4 spawn instruction**

In `skills/_shared/steps/plan/step-03-story-elaboration.md`, replace the spawn instruction block (currently lines 63–75):

```markdown
Spawn `bmad-create-story` with:
- Every thin story file path in the batch, as input artifacts to enrich in place
- Instruction to add technical ACs to **each** story, covering: interface contracts, data
  model changes, error handling and edge cases, observability requirements, security
  considerations, testability (unit + integration test anchors) — treating each story on its
  own terms rather than applying one answer across the batch
- Context preamble: `epic_key: {epic_key}`, `work_type: {work_type}`, `skill: l3io-pm-plan`
- `{agent_contract}` (verbatim — see `steps/shared/step-00-digest.md`)
```

Replace with:

```markdown
Spawn `bmad-create-story` with:
- Every thin story file path in the batch. **For each path: if the file does not yet exist,
  create it first** with this minimal skeleton (substituting the story's `key` and `title`
  from its state YAML node), then enrich:
  ```markdown
  ---
  key: '{story_key}'
  title: '{story_title}'
  status: backlog
  classification: standard
  ---

  # {story_title}

  ## Acceptance Criteria

  <!-- Technical ACs to be added below -->
  ```
- Instruction to add technical ACs to **each** story, covering: interface contracts, data
  model changes, error handling and edge cases, observability requirements, security
  considerations, testability (unit + integration test anchors) — treating each story on its
  own terms rather than applying one answer across the batch
- Context preamble: `epic_key: {epic_key}`, `work_type: {work_type}`, `skill: l3io-pm-plan`
- `{agent_contract}` (verbatim — see `steps/shared/step-00-digest.md`)
```

- [ ] **Step 2: Update step-02-story-prep.md §2 spawn prompt**

In `skills/_shared/steps/sprint/step-02-story-prep.md`, replace lines 81–83 (the start of the spawn prompt):

```
Two things for each story file listed below. Preserve all existing content in every file.
```

Replace with:

```
Two things for each story file listed below.
**If a story file does not exist at its given path, create it first** with this minimal
skeleton (substituting the story's `key` and `title` from the state node at
`{pm_state_root}/.../sprint-{nn}/{story_key}.yaml`), then perform both actions:
```markdown
---
key: '{story_key}'
title: '{story_title}'
status: {story_status}
classification: standard
---

# {story_title}

## Acceptance Criteria

<!-- Technical ACs to be added below -->
```
For existing files, preserve all existing content.
```

- [ ] **Step 3: Sync shared steps to per-skill copies**

```bash
cd /mnt/source/git/l3io/bmad/bmad-extensions
npm run sync:scripts
```

Expected: "Sync complete" or similar with 0 diffs reported.

- [ ] **Step 4: Verify sync and docs pass**

```bash
npm run check:scripts
npm run check:docs
```

Both must exit 0. If check:docs fails on a gating-table mismatch, re-read the phase matrix in `steps/shared/step-01-classify-work.md` §4 and ensure the changed files didn't accidentally alter it.

- [ ] **Step 5: Regenerate manifests and verify**

```bash
node scripts/write-payload-manifest.mjs
npm run check:manifest
```

Both must exit 0.

- [ ] **Step 6: Commit**

```bash
git add skills/_shared/steps/plan/step-03-story-elaboration.md \
        skills/_shared/steps/sprint/step-02-story-prep.md \
        skills/l3io-pm-plan/steps/plan/step-03-story-elaboration.md \
        skills/l3io-pm-execute/steps/sprint/step-02-story-prep.md \
        skills/l3io-pm-sync/steps/sprint/step-02-story-prep.md \
        skills/l3io-pm-plan/payload-manifest.json \
        skills/l3io-pm-execute/payload-manifest.json \
        skills/l3io-pm-sync/payload-manifest.json
git commit -s -m "fix(l3io-pm): create story artifact file if absent before elaboration

Step-03-story-elaboration and sprint step-02-story-prep both passed story
file paths to bmad-create-story with 'enrich in place' / 'preserve existing
content' — language that presupposes the files exist. When story .md files
were absent (state YAML exists but no artifact yet), the agent fell back to
updating the nearest markdown it could find (epic.md). Both steps now
instruct the agent to create a minimal frontmatter skeleton at the given
path first, then enrich with technical ACs."
```

---

### Task 2: Detect artifact-only stories in readiness check (Bug 3)

**Files:**
- Modify: `skills/_shared/steps/plan/step-02-readiness-check.md`

**Interfaces:**
- Consumes: artifact tree at `{implementation_artifacts}/epic-*/sprint-*/stories/*.md`
- Consumes: state tree at `{pm_state_root}/(active|planned|archived)/epic-*/sprint-*/*.yaml`
- Produces: Red gate blocking l3io-pm-plan with actionable message when artifact-only stories found

**Why this matters:** step-02 enumerates stories from state YAML files only. If story `.md` files exist in the artifact tree with no corresponding state YAML, the readiness check finds zero stories and silently passes — the plan is generated with no stories to execute. The fix adds a pre-scan that detects this mismatch and blocks with a clear message pointing to `bootstrap-state`.

- [ ] **Step 1: Add §0 pre-scan to step-02-readiness-check.md**

In `skills/_shared/steps/plan/step-02-readiness-check.md`, insert a new section **§0** before the existing §1. Place it after the header/intro and before "## 1. Collect stories in scope":

```markdown
## 0. Pre-scan: artifact-only story detection

Before reading state, check whether the artifact tree holds story `.md` files that have
no corresponding state YAML. Run regardless of `{work_type}`.

```bash
find {implementation_artifacts}/epic-*/sprint-*/stories -name 'E*.md' 2>/dev/null \
  | sort
```

For each `.md` file found (pattern `{implementation_artifacts}/epic-{nnn}/sprint-{nn}/stories/{story_key}.md`):

Derive the expected state path by resolving the story key across all three status directories:

```bash
find {pm_state_root}/active {pm_state_root}/planned {pm_state_root}/archived \
  -name "{story_key}.yaml" 2>/dev/null | head -1
```

If the above `find` prints nothing, the story has an artifact but no state node — collect it as an **artifact-only** story.

If **any artifact-only stories are found**, halt immediately:

```
🔴 Readiness check FAILED — {count} story artifact(s) found with no state node.

These stories exist as .md files in the artifact tree but have no corresponding
state YAML under {pm_state_root}/. l3io-pm-plan reads state only, so these stories
are invisible to planning, estimation, and execution.

Artifact-only stories:
{list each: {implementation_artifacts}/epic-{nnn}/sprint-{nn}/stories/{story_key}.md}

Fix: run /l3io-util-doctor bootstrap-state to create state nodes from your artifact
files. This is a one-time step for projects whose stories were created outside l3io-pm.
```

BLOCKED: artifact-only stories detected — run /l3io-util-doctor bootstrap-state first.

If no artifact-only stories are found, continue to §1.
```

Also renumber the existing sections from §1–§7 → §1–§7 (no change needed, §0 is a new prefix section, not a replacement).

Update the output status line in §7:

Current:
```
Step 02 complete — readiness: {readiness}, stories: {total_story_count}, gaps: {amber_count} amber / {red_count} red
```

No change needed — §0 does not reach this line when it fires (it halts early). The status line only fires on the green/amber path.

- [ ] **Step 2: Sync shared steps to per-skill copies**

```bash
cd /mnt/source/git/l3io/bmad/bmad-extensions
npm run sync:scripts
```

- [ ] **Step 3: Verify checks pass**

```bash
npm run check:scripts
npm run check:docs
```

If check:docs fails on `section-refs` (because §0 is a new section and cross-references may mention §1–§7 elsewhere), trace those references and verify they still resolve correctly. The §0 prefix doesn't change §1–§7 numbering.

- [ ] **Step 4: Regenerate manifests**

```bash
node scripts/write-payload-manifest.mjs
npm run check:manifest
```

- [ ] **Step 5: Commit**

```bash
git add skills/_shared/steps/plan/step-02-readiness-check.md \
        skills/l3io-pm-plan/steps/plan/step-02-readiness-check.md \
        skills/l3io-pm-plan/payload-manifest.json
git commit -s -m "fix(l3io-pm): detect artifact-only stories before readiness check

l3io-pm-plan step-02 enumerated stories exclusively from state YAML files.
If story .md artifacts existed but had no corresponding state nodes
(the 'legacy BMad format' case), planning found zero stories and generated
an empty plan with no error. A new §0 pre-scan detects this mismatch and
blocks with an actionable message pointing to /l3io-util-doctor bootstrap-state."
```

---

### Task 3: Add bootstrap-state mode to l3io-util-doctor (Bugs 3 + 4)

**Files:**
- Create: `skills/l3io-util-doctor/steps/bootstrap-state.md`
- Modify: `skills/l3io-util-doctor/SKILL.md` (keyword table, help output, description, On Activation)
- Modify: `skills/l3io-util-doctor/steps/health-check.md` (add Check 2c)

**Interfaces:**
- Consumes: artifact tree `{implementation_artifacts}/epic-{nnn}/sprint-{nn}/stories/{story_key}.md`
- Consumes: epic markdown at `{implementation_artifacts}/epic-{nnn}/epic.md` (optional, for title/goal)
- Produces: sharded state YAML nodes at `{pm_state_root}/planned/epic-{nnn}/` (new files only)

**Why this matters:** There is currently no path from "BMad story .md artifact files" to "l3io-pm sharded state YAML." A user who created stories via `bmad-create-story` without going through l3io-pm-plan has artifacts but no state — migrate-state says "nothing to migrate" and l3io-pm-plan finds zero stories. bootstrap-state fills this gap as a one-time setup step.

- [ ] **Step 1: Create skills/l3io-util-doctor/steps/bootstrap-state.md**

Create the file with this content:

```markdown
## Bootstrap State Mode

Invoked with `bootstrap-state` argument.

Creates sharded state YAML nodes from existing story artifact `.md` files. Use this
once when a project has stories authored via `bmad-create-story` (or any BMad workflow)
but no corresponding l3io-pm state files.

**This mode only writes new files.** It never overwrites an existing state node.
If `{pm_state_root}` already exists with any content, it halts rather than guess
which side is authoritative.

---

## Bindings

Resolve config same as described in `SKILL.md` On Activation. Bindings `{implementation_artifacts}`,
`{pm_state_root}`, `{pm_status}` must be set before proceeding.

---

## Pre-flight

**Check 1 — No existing sharded state:**

```bash
SHARDED=$([ -d "{pm_state_root}" ] && echo 1 || echo 0)
echo "sharded=$SHARDED"
```

If `SHARDED=1`:
```
BLOCKED: {pm_state_root} already exists. bootstrap-state only runs on projects with
no state yet. If you have state in a legacy format, run /l3io-util-doctor migrate-state
instead. If you have both state and artifact-only stories, resolve the mismatch manually
(see the drift report from /l3io-util-doctor check).
```

**Check 2 — Artifact tree exists with story files:**

```bash
find {implementation_artifacts}/epic-*/sprint-*/stories -name 'E*.md' 2>/dev/null | head -5
```

If no `.md` files are found:
```
Nothing to bootstrap — no story artifact files found under
{implementation_artifacts}/epic-*/sprint-*/stories/.
If this is a new project, state will be created automatically on first use of any
l3io-pm skill.
```
Exit (not an error).

**Check 3 — Artifact epic directories use three-digit padding:**

```bash
find {implementation_artifacts} -maxdepth 1 -type d -name 'epic-[0-9][0-9]' 2>/dev/null
```

If any two-digit `epic-{nn}/` directories are found, halt:
```
BLOCKED: Found legacy two-digit epic directories:
  {list}
Run /l3io-util-doctor rename-epic-dirs first to upgrade them to three-digit form
(epic-{nnn}/), then re-run bootstrap-state.
```

---

## Stage A — Scan artifact tree

Collect the full artifact inventory:

```bash
# Epic directories
find {implementation_artifacts} -maxdepth 1 -type d -name 'epic-[0-9][0-9][0-9]' | sort

# Sprint directories per epic
find {implementation_artifacts}/epic-*/sprint-[0-9][0-9] -maxdepth 0 -type d 2>/dev/null | sort

# Story files
find {implementation_artifacts}/epic-*/sprint-*/stories -name 'E*.md' 2>/dev/null | sort
```

For each story file at path `{implementation_artifacts}/epic-{nnn}/sprint-{nn}/stories/{story_key}.md`:
- Derive `epic_key` = `E{nnn}` (from directory name, zero-pad to 3 digits)
- Derive `sprint_key` = `S{nn}` (from directory name, already 2 digits)
- `story_key` = basename without `.md` extension (must match `E{nnn}-S{nn}-{nnn}` pattern)
- Read the file's YAML frontmatter block (between the first pair of `---` delimiters, if present)
- Extract `title` from frontmatter if present; otherwise derive from filename or set `''`
- Extract `classification` from frontmatter if present; default to `standard`
- Extract `status` from frontmatter if present; if the value is not one of
  `backlog|ready-for-dev|in-progress|review|done`, default to `backlog`

Skip any story file whose basename does not match `E{nnn}-S{nn}-{nnn}.md` exactly
(the three-segment zero-padded key format). Record skipped files for the final report.

For each epic directory `{implementation_artifacts}/epic-{nnn}/`:
- `epic_key` = `E{nnn}`
- Check for `{implementation_artifacts}/epic-{nnn}/epic.md` — read its frontmatter if present
  - Extract `title` if present
  - Extract `goal` if present
  - Fallback: `title` = `Epic {nnn}`, `goal` = `''`

For each sprint directory `{implementation_artifacts}/epic-{nnn}/sprint-{nn}/`:
- `sprint_key` = `S{nn}`
- `title` = `Sprint {nn}`

Build three working lists:
- `{epic_list}` = unique epic keys found (deduplicated from story paths + epic directories)
- `{sprint_list}` = `(epic_key, sprint_key)` pairs found
- `{story_list}` = `(epic_key, sprint_key, story_key, title, classification, status)` tuples

---

## Stage B — Confirm with user

Print the bootstrap plan:

```
📋 Bootstrap State — Dry Run
============================

Will create {pm_state_root}/ with:
  Epics:   {N} ({list epic keys})
  Sprints: {N} total
  Stories: {N} total

All epics will be placed in planned/ (status: backlog).
Stories with status 'in-progress', 'review', or 'done' in their frontmatter
will be placed in active/ under their epic.

Stories skipped (non-standard filename): {skipped_count}
  {list skipped files if any}

Proceed? [Y/n]:
```

If user types `n` or `no` — exit without writing anything. Not an error.

If user confirms (blank or `y`/`Y`) — continue to Stage C.

---

## Stage C — Write state directories and nodes

Create the state root directories:

```bash
mkdir -p {pm_state_root}/planned {pm_state_root}/active {pm_state_root}/archived
```

For each epic in `{epic_list}`:

Determine `status_dir`:
- If all of this epic's stories have `status: done` → `archived`
- Else if any story has `status: in-progress` or `status: review` → `active`
- Else → `planned`

Write `{pm_state_root}/{status_dir}/epic-{nnn}/epic.yaml` (skip if already exists — never overwrite):

```yaml
key: 'E{nnn}'
title: '{epic_title}'
goal: '{epic_goal}'
status: {backlog if planned, in-progress if active, done if archived}
updated_at: '{iso_timestamp}'
```

For each `(epic_key, sprint_key)` in `{sprint_list}`:

Write `{pm_state_root}/{status_dir}/epic-{nnn}/sprint-{nn}/sprint.yaml` (skip if exists):

```yaml
key: 'S{nn}'
epic: 'E{nnn}'
title: 'Sprint {nn}'
status: backlog
updated_at: '{iso_timestamp}'
```

For each `(epic_key, sprint_key, story_key, title, classification, status)` in `{story_list}`:

Determine `story_status`: use the value from frontmatter (default `backlog`) — but
normalize any invalid value to `backlog`.

Write `{pm_state_root}/{status_dir}/epic-{nnn}/sprint-{nn}/{story_key}.yaml`
(skip if exists — never overwrite):

```yaml
key: '{story_key}'
epic: 'E{nnn}'
sprint: 'S{nn}'
title: '{story_title}'
status: {story_status}
classification: {classification}
updated_at: '{iso_timestamp}'
```

`{status_dir}` matches the **epic's** resolved directory (all of an epic's nodes live
under the same status directory — sprint and story nodes do not get their own placement).

---

## Stage D — Verify

For each epic created, run:

```bash
python3 {pm_status} verify --state-root {pm_state_root} --epic {epic_key} --scope epic
```

If any verification fails, report:
```
⚠️  Verification failed for {epic_key} — {error detail}
    The state files were written; this failure means back-references are mismatched.
    Investigate {pm_state_root}/{status_dir}/epic-{nnn}/ manually.
```

Do not remove the created files on verify failure — partial state is better than no state
for investigation; the user can re-run `/l3io-util-doctor check` to see the exact drift.

---

## Final report

```
bootstrap-state complete:
  Epics created:    {N} (planned: {N}, active: {N}, archived: {N})
  Sprints created:  {N}
  Stories created:  {N}
  Skipped (non-standard names): {N}
  Verification:     {N}/{N} epics passed

Next steps:
  1. Run /l3io-pm-plan to validate readiness, estimate, and generate an execution plan.
  2. Run /l3io-util-doctor check to confirm the new state looks correct.
  3. If any stories were skipped, create their state nodes manually using the schema
     at {pm_state_root}/planned/epic-{nnn}/sprint-{nn}/ as a template.
```
```

- [ ] **Step 2: Add `bootstrap-state` to SKILL.md keyword table**

In `skills/l3io-util-doctor/SKILL.md`, in the keyword table (after `migrate-state` row, line 78):

Add after the `migrate-state` row:
```
| `bootstrap-state` | `steps/bootstrap-state.md` | creates sharded state from artifact .md files — one-time for projects whose stories were authored outside l3io-pm |
```

- [ ] **Step 3: Add bootstrap-state to help output in SKILL.md**

In the help output block, under "One-time migrations (run in this order)", after the `migrate-state` line:
```
  bootstrap-state    Create state nodes from story artifact .md files — use when stories
                     were authored via bmad-create-story without going through l3io-pm-plan
```

- [ ] **Step 4: Update SKILL.md description (first paragraph)**

In the skill description (the `description:` field in the YAML front matter at the top of SKILL.md), append to the description:

Current end of description: `...Run without arguments for an auto-diagnostic that scans project state and proposes the right actions.`

Change to: `...Run without arguments for an auto-diagnostic that scans project state and proposes the right actions. Use bootstrap-state when a project has story artifact files (from bmad-create-story) but no l3io-pm state YAML — this is the one-time import path for projects set up outside l3io-pm.`

- [ ] **Step 5: Add Check 2c to health-check.md**

In `skills/l3io-util-doctor/steps/health-check.md`, after **Check 2b — State layout migration** (around line 28), insert a new **Check 2c — Artifact-only stories (no state YAML)**:

```markdown
**Check 2c — Artifact-only stories (no state YAML)**
Only runs when Check 2b result is "Only sharded present, or none present (new project)".
Scan story artifact files and check each against state:

```bash
find {implementation_artifacts}/epic-*/sprint-*/stories -name 'E*.md' 2>/dev/null | sort
```

For each `.md` found at `{implementation_artifacts}/epic-{nnn}/sprint-{nn}/stories/{story_key}.md`:

```bash
find {pm_state_root}/active {pm_state_root}/planned {pm_state_root}/archived \
  -name "{story_key}.yaml" 2>/dev/null | head -1
```

- Any `.md` file with no corresponding `.yaml` → flag `bootstrap-state` · Priority: **High** ·
  note count — state is absent for these stories, so l3io-pm-plan finds zero stories and
  generates an empty plan. The fix is a one-time import, not a repeat migration.
- None found (all artifact stories have matching state) → ✓
- No `.md` files found at all → ✓ (new project or all stories are state-only, which is normal
  for `planned/` epics)
```

- [ ] **Step 6: Verify SKILL.md routing table completeness**

Read `skills/l3io-util-doctor/SKILL.md` and verify:
- `bootstrap-state` appears in the keyword table pointing to `steps/bootstrap-state.md`
- `steps/bootstrap-state.md` now exists
- The help output lists `bootstrap-state` under "One-time migrations"

- [ ] **Step 7: Run check:docs**

```bash
npm run check:docs
```

check:docs check (1) `skill-names` verifies that every `l3io-*` skill named in a live doc resolves to a real `skills/` directory. We are not adding a new skill (only a new mode to an existing skill), so this check should still pass.

If check:docs fails on `digest-size` (step-00-digest byte budget), that means bootstrap-state's new text was accidentally included in the digest — investigate `steps/shared/step-00-digest.md` to ensure it was not modified.

- [ ] **Step 8: Regenerate manifests**

```bash
node scripts/write-payload-manifest.mjs
npm run check:manifest
```

- [ ] **Step 9: Commit**

```bash
git add skills/l3io-util-doctor/steps/bootstrap-state.md \
        skills/l3io-util-doctor/SKILL.md \
        skills/l3io-util-doctor/steps/health-check.md \
        skills/l3io-util-doctor/payload-manifest.json
git commit -s -m "feat(l3io-util): add bootstrap-state mode for artifact-only projects

Projects whose stories were created via bmad-create-story (outside l3io-pm)
have artifact .md files but no sharded state YAML. migrate-state correctly
reported 'nothing to migrate' (no legacy state format to convert), but there
was no path to create state from artifacts. bootstrap-state fills this gap:
it scans the artifact tree, creates minimal YAML nodes for each epic/sprint/
story found, verifies back-references, and reports what was created.

Health check now includes Check 2c detecting this case and flagging it as High
priority with a clear action."
```

---

### Task 4: Improve migrate-state diagnostics and detection (Bug 1 + Bug 4 pre-flight)

**Files:**
- Modify: `skills/l3io-util-doctor/assets/migrate-state.md`

**Interfaces:**
- Consumes: `{implementation_artifacts}` and `{project-root}` bindings from config resolver
- Produces: clearer "nothing to migrate" output showing exactly which paths were checked

**Why this matters:** When step-00-activate blocks on a legacy format but migrate-state says "nothing to migrate," the user is stuck with no way to debug why. The paths checked need to be printed so the user can verify `{implementation_artifacts}` is resolving correctly. Also, migrate-state doesn't detect the artifact-only case — it should route to bootstrap-state.

- [ ] **Step 1: Add diagnostic output to "nothing to migrate" exit**

In `skills/l3io-util-doctor/assets/migrate-state.md`, in the **Pre-flight** section, find the final `else` branch (the "nothing to migrate" case):

Current:
```
**Else (`LEGACY_FLAT=0`, `LEGACY_EPIC=0`, `SHARDED=0`)** → nothing to migrate:
```
Nothing to migrate — no legacy flat, legacy per-epic, or sharded state found under
{implementation_artifacts} or {project-root}/_bmad/state/. If this is a new project,
state will be created lazily on first use of any l3io-pm skill.
```
Exit. This is not an error.
```

Replace with:

```
**Else (`LEGACY_FLAT=0`, `LEGACY_EPIC=0`, `SHARDED=0`)** → check artifact-only case:

```bash
ARTIFACT_STORIES=$(find {implementation_artifacts}/epic-*/sprint-*/stories \
  -name 'E*.md' 2>/dev/null | wc -l | tr -d ' ')
echo "artifact_stories=$ARTIFACT_STORIES"
```

If `ARTIFACT_STORIES` is non-zero → artifact-only project. Print:
```
Story artifacts found but no state of any format. These stories were created
outside l3io-pm and need state nodes before the PM skills can use them.

Run: /l3io-util-doctor bootstrap-state
```
Exit. This is not an error; the correct next step is bootstrap-state.

If `ARTIFACT_STORIES=0` → nothing to migrate at all:
```
Nothing to migrate — checked:
  Sharded:      {implementation_artifacts}/state/ — not found
  Legacy epic:  {project-root}/_bmad/state/ — not found
  Legacy flat:  {implementation_artifacts}/sprint-status.yaml — not found
  Artifacts:    {implementation_artifacts}/epic-*/sprint-*/stories/E*.md — none found

If you expected to find a legacy layout here, verify that {implementation_artifacts}
resolves correctly for this project. Run:
  uv run --python 3.11 {project-root}/_bmad/scripts/resolve_config.py \
    --project-root {project-root}
and check the value of modules.l3io-pm.implementation_artifacts.

If this is a new project, state will be created lazily on first use of any l3io-pm skill.
```
Exit. This is not an error.
```

- [ ] **Step 2: Add artifact-only sprint-status.yaml fallback check**

In the same Pre-flight section, in the LEGACY_FLAT detection bash snippet, add an additional check for sprint-status.yaml at the project root (a common location when `{implementation_artifacts}` is misconfigured):

After:
```bash
SHARDED=$([ -d "{implementation_artifacts}/state" ] && echo 1 || echo 0)
LEGACY_EPIC=$([ -d "{project-root}/_bmad/state" ] && echo 1 || echo 0)
LEGACY_FLAT=$([ -f "{implementation_artifacts}/sprint-status.yaml" ] && echo 1 || echo 0)
echo "sharded=$SHARDED legacy-per-epic=$LEGACY_EPIC legacy-flat=$LEGACY_FLAT"
```

Add:
```bash
# Fallback: also check sprint-status.yaml at project root (common when
# implementation_artifacts is not configured and the file was created there)
if [ "$LEGACY_FLAT" = "0" ]; then
  LEGACY_FLAT_ROOT=$([ -f "{project-root}/sprint-status.yaml" ] && echo 1 || echo 0)
  if [ "$LEGACY_FLAT_ROOT" = "1" ]; then
    echo "NOTE: sprint-status.yaml found at {project-root}/sprint-status.yaml"
    echo "      (not at {implementation_artifacts}/sprint-status.yaml)"
    echo "      Treating as legacy-flat. If this is wrong, check your config."
    LEGACY_FLAT=1
    SPRINT_STATUS_PATH="{project-root}/sprint-status.yaml"
  else
    SPRINT_STATUS_PATH="{implementation_artifacts}/sprint-status.yaml"
  fi
else
  SPRINT_STATUS_PATH="{implementation_artifacts}/sprint-status.yaml"
fi
```

Then, all later references to `{implementation_artifacts}/sprint-status.yaml` in Stage A should use `{sprint_status_path}` instead. Update Stage A's flat file reading:

Current opening of Stage A:
```bash
ls {implementation_artifacts}/sprint-status.yaml \
   {implementation_artifacts}/sprint-status-backlog.yaml \
   {implementation_artifacts}/sprint-status-archived.yaml 2>/dev/null
```

Replace with:
```bash
# {sprint_status_path} is bound above (may be project-root or implementation_artifacts)
SPRINT_DIR=$(dirname "{sprint_status_path}")
ls {sprint_status_path} \
   {sprint_dir}/sprint-status-backlog.yaml \
   {sprint_dir}/sprint-status-archived.yaml 2>/dev/null
```

And update Stage D's backup step for legacy flat:
Current:
```bash
[ ! -f {implementation_artifacts}/sprint-status.yaml.legacy ] && \
  cp {implementation_artifacts}/sprint-status.yaml \
     {implementation_artifacts}/sprint-status.yaml.legacy
```

Replace with:
```bash
[ ! -f {sprint_status_path}.legacy ] && \
  cp {sprint_status_path} {sprint_status_path}.legacy
```

And Stage F's rm step:
Current:
```bash
rm -f {implementation_artifacts}/sprint-status.yaml \
      {implementation_artifacts}/sprint-status-backlog.yaml \
      {implementation_artifacts}/sprint-status-archived.yaml
```

Replace with:
```bash
rm -f {sprint_status_path} \
      {sprint_dir}/sprint-status-backlog.yaml \
      {sprint_dir}/sprint-status-archived.yaml
```

- [ ] **Step 3: Run check:docs**

```bash
npm run check:docs
```

check:docs check (6) `status-values` may scan migrate-state.md. Ensure any status values mentioned in the added text are from the accepted set (`backlog`, `in-progress`, `done` for epics/sprints; `backlog`, `ready-for-dev`, `in-progress`, `review`, `done` for stories).

- [ ] **Step 4: Regenerate manifests**

```bash
node scripts/write-payload-manifest.mjs
npm run check:manifest
```

- [ ] **Step 5: Commit**

```bash
git add skills/l3io-util-doctor/assets/migrate-state.md \
        skills/l3io-util-doctor/payload-manifest.json
git commit -s -m "fix(l3io-util): improve migrate-state diagnostics and artifact-only detection

When migrate-state reported 'nothing to migrate', the user had no way to
verify whether {implementation_artifacts} was resolving correctly, making
it impossible to debug the case where step-00-activate detected a legacy
format but migrate-state did not.

Changes:
- Print all checked paths when nothing is found, so misconfigured
  {implementation_artifacts} is immediately visible
- Check for sprint-status.yaml at {project-root}/ as a fallback (common
  placement when implementation_artifacts is not explicitly configured)
- Detect artifact-only projects (stories in epic-*/sprint-*/stories/ but
  no state) and route to /l3io-util-doctor bootstrap-state"
```

---

### Task 5: Fix inaccurate doc claim and final verification

**Files:**
- Modify: `docs/getting-started.md`

**Why this matters:** The getting-started docs say "state (created by `/l3io-pm-plan` or manually)." l3io-pm-plan does NOT create story state YAML files from scratch — it only reads/estimates existing nodes. This doc error is what sent users looking for a non-existent creation mechanism.

- [ ] **Step 1: Fix getting-started.md claim**

In `docs/getting-started.md`, find:
```
Sprints must already exist in
state (created by `/l3io-pm-plan` or manually) before an epic run
```

Replace with:
```
Sprints must already exist in
state (created manually or via `/l3io-util-doctor bootstrap-state` for artifact-only
projects) before an epic run
```

Also update the "Before Running l3io-pm" section to mention bootstrap-state. Find:
```
   upgrading from a legacy layout — a flat `sprint-status.yaml`, the three-file split, or a
   per-epic `_bmad/state/` tree — run `/l3io-util-doctor` first and let it sequence the
   migration; see [Upgrading](upgrading.md). Originals are preserved as `.legacy`.
```

Replace with:
```
   upgrading from a legacy layout — a flat `sprint-status.yaml`, the three-file split, or a
   per-epic `_bmad/state/` tree — run `/l3io-util-doctor` first and let it sequence the
   migration; see [Upgrading](upgrading.md). Originals are preserved as `.legacy`.
   If you created stories via `bmad-create-story` without going through l3io-pm-plan
   (the "legacy BMad format" case), run `/l3io-util-doctor bootstrap-state` to create
   state nodes from your artifact files.
```

- [ ] **Step 2: Run the full check suite**

```bash
npm run check:scripts
npm run check:docs
npm run check:manifest
```

All three must exit 0 before committing.

If check:docs fails on `section-refs` due to the new §0 in step-02-readiness-check, trace the cross-reference and fix the reference in whichever file points to the old section number.

- [ ] **Step 3: Commit**

```bash
git add docs/getting-started.md
git commit -s -m "docs: fix inaccurate claim that l3io-pm-plan creates story state

l3io-pm-plan reads and estimates existing state nodes; it does not create
them from scratch. The 'created by /l3io-pm-plan or manually' phrasing led
users to expect a creation mechanism that does not exist. Updated to name
bootstrap-state as the correct import path for artifact-only projects."
```

---

## Self-Review

### Spec coverage check

| Bug | Task that addresses it |
|-----|----------------------|
| Bug 1: legacy format detected by step-00 but not by migrate-state | Task 4 — diagnostic output + fallback root-path check |
| Bug 2: bmad-create-story updates epic.md instead of creating story files | Task 1 — create-if-absent instruction |
| Bug 3: l3io-pm-plan finds zero stories from artifact-only projects | Task 2 (blocks with message) + Task 3 (bootstrap-state) |
| Bug 4: migrate-state says "nothing to migrate" for legacy BMad format | Task 4 (artifact-only detection) + Task 3 (bootstrap-state) |

### Placeholder scan

- All step file edits include literal YAML/bash/markdown content — no "TBD" or "implement appropriately"
- bootstrap-state.md is fully specified through all stages
- Task 4's bash snippets are exact

### Type consistency

- `{sprint_status_path}` is introduced in Task 4 Step 2 and used consistently throughout that step
- `{story_key}` format is `E{nnn}-S{nn}-{nnn}` throughout — consistent with existing code
- Status values used in bootstrap-state.md (`backlog`, `in-progress`, `done`, `ready-for-dev`, `review`) match `VALID_*_STATUS` in pm-status.py

### Gaps

- **pm-status.py has no `create-node` command** — bootstrap-state.md writes state YAML directly (as migrate-state's Stage B already does), which is intentional: adding a pm-status.py subcommand would require updating the cli-surface reference doc and is out of scope for a step-file-only fix. The direct-write approach is already used in migrate-state.
- **bootstrap-state does not set `estimate` blocks** — that is correct; l3io-pm-plan's step-estimate will compute them on the first plan run after bootstrap.
- **bootstrap-state writes all epics as `planned/` by default** — this is intentional; an epic whose stories are `in-progress` in their frontmatter gets placed in `active/`. The user can move epics with `pm-status.py move-epic` after bootstrap if the placement is wrong.
