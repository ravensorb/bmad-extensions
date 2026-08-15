# Migrate State: Old 3-File Layout → New Per-Epic Active Files

Communicate all responses in `{communication_language}`.

Migrates l3io-pm state from the old `{implementation_artifacts}/sprint-status*.yaml` layout
to the new `{project-root}/_bmad/state/` layout used by l3io-pm-plan, l3io-pm-execute, and
l3io-pm-sync.

## Pre-flight

Read `{project-root}/_bmad/config.yaml` to bind `{implementation_artifacts}` and `{planning_artifacts}`.

Check that the old files exist:
```bash
ls {implementation_artifacts}/sprint-status.yaml \
   {implementation_artifacts}/sprint-status-backlog.yaml \
   {implementation_artifacts}/sprint-status-archived.yaml 2>/dev/null
```

If the active-state directory already exists at `{project-root}/_bmad/state/active/`:
```
State already migrated — {project-root}/_bmad/state/active/ already exists.
Run with --force to re-migrate (originals are preserved as .legacy files).
```
BLOCKED unless --force passed.

## Step 1: Create new state directories

```bash
mkdir -p {project-root}/_bmad/state/active
```

## Step 2: Load and normalize all source data

Read all three source files into memory. **Do not write any output yet.**

Apply these normalizations to every epic, sprint, and story node:

| Node type | Legacy status | Condition | Normalized to | Placement |
|-----------|--------------|-----------|---------------|-----------|
| Epic | `deferred` | no sprint has `status: done` | `backlog` | `sprint-status-planned.yaml` |
| Epic | `deferred` | ≥1 sprint has `status: done` | `in-progress` | `active/E{id}-status.yaml` |
| Epic | `superseded` | any | `done` | `sprint-status-archived.yaml` (preserve `superseded_by` field) |
| Sprint | `deferred` | — | `backlog` | within its parent epic node |
| Story | `deferred` | — | extract as backlog issue | remove from story list; add to `sprint-status-issues.yaml` `backlog:` with key `BL-E{epic_id}-{seq}`, `severity: Low`, `source: migrate-state (deferred)` |
| Story | `superseded` | — | `done` | within its parent sprint node |

For deferred stories extracted as backlog issues, assign sequential keys starting after the highest existing `BL-E{epic_id}-{nnn}` key for that epic (or `BL-E{epic_id}-001` if none exist).

Record all normalizations for the Step 6 report.

## Step 3: Split sprint-status-backlog.yaml → planned + issues

Write the normalized epic nodes to `{project-root}/_bmad/state/sprint-status-planned.yaml`.
Write the `backlog:` flat list to `{project-root}/_bmad/state/sprint-status-issues.yaml`.

Then back up and clear the original:
```bash
# Only create .legacy if it does not already exist — never overwrite an existing backup
[ ! -f {implementation_artifacts}/sprint-status-backlog.yaml.legacy ] && \
  cp {implementation_artifacts}/sprint-status-backlog.yaml \
     {implementation_artifacts}/sprint-status-backlog.yaml.legacy
```
Overwrite `{implementation_artifacts}/sprint-status-backlog.yaml` with:
```yaml
epics: []
backlog: []
```

## Step 4: Split sprint-status.yaml → per-epic active files

For each epic with normalized status `in-progress`:
- Write `{project-root}/_bmad/state/active/E{id}-status.yaml`
- File contains: `epics: [{the single epic node}]`

Epics normalized to `backlog` go to `sprint-status-planned.yaml` (already written in Step 3).
Epics normalized to `done` go to `sprint-status-archived.yaml` (Step 5).

Then back up and clear the original:
```bash
[ ! -f {implementation_artifacts}/sprint-status.yaml.legacy ] && \
  cp {implementation_artifacts}/sprint-status.yaml \
     {implementation_artifacts}/sprint-status.yaml.legacy
```
Overwrite `{implementation_artifacts}/sprint-status.yaml` with:
```yaml
epics: []
```

## Step 5: Move archived file + collect done epics

```bash
[ -f {implementation_artifacts}/sprint-status-archived.yaml ] && \
  cp {implementation_artifacts}/sprint-status-archived.yaml \
     {project-root}/_bmad/state/sprint-status-archived.yaml
[ -f {implementation_artifacts}/sprint-status-archived.yaml ] && \
  [ ! -f {implementation_artifacts}/sprint-status-archived.yaml.legacy ] && \
  cp {implementation_artifacts}/sprint-status-archived.yaml \
     {implementation_artifacts}/sprint-status-archived.yaml.legacy
```
Overwrite `{implementation_artifacts}/sprint-status-archived.yaml` with:
```yaml
epics: []
```

Append any epics normalized to `done` (from Step 2) to `{project-root}/_bmad/state/sprint-status-archived.yaml` if not already present.

## Step 6: Report and legacy cleanup

Print the migration summary:

```
migrate-state complete:
  Active epic files created:   {N} ({epic_keys})
  sprint-status-planned.yaml:  {N} planned epics
  sprint-status-issues.yaml:   {N} issues ({N} pre-existing + {N} extracted from deferred stories)
  sprint-status-archived.yaml: {N} archived epics

Status normalizations applied:
  deferred epics (no done sprints) → backlog/planned: {N}
  deferred epics (has done sprints) → in-progress/active: {N}
  superseded epics → done/archived:   {N}  (keys: {key_list or "none"})
  deferred sprints → backlog:         {N}
  deferred stories → backlog issues:  {N}  (keys: {key_list or "none"})
  superseded stories → done:          {N}  (keys: {key_list or "none"})

Legacy backup files:
  {list each .legacy file path on its own line}
```

Then ask:

```
What would you like to do with the legacy backup files?
  M — move to {project-root}/_bmad/migration-backup/ (recommended)
  D — delete them
  K — keep in place (the health check will offer cleanup later)
[M]:
```

**If M (default):**
```bash
mkdir -p {project-root}/_bmad/migration-backup
mv {implementation_artifacts}/sprint-status*.yaml.legacy \
   {project-root}/_bmad/migration-backup/
```
Print: `Legacy files moved to {project-root}/_bmad/migration-backup/`

**If D:**
```bash
rm {implementation_artifacts}/sprint-status*.yaml.legacy
```
Print: `Legacy files deleted.`

**If K:**
Print: `Legacy files left in place. Run /l3io-util-cleanup to remove them later.`

---

```
Next steps:
  Run /l3io-pm-plan to rebuild the execution plan with the new state layout.
```
