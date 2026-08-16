---
name: l3io-pm-help
description: Read project state and recommend the exact next l3io-pm action.
---

# l3io-pm-help

Communicate all responses in `{communication_language}`.

## On Activation

Run: `python3 {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow`

If the script fails, read `{skill-root}/customize.toml` directly.

If `{project-root}/_bmad/config.yaml` does not have an `l3io-pm` section, load
`{skill-root}/assets/module-setup.md` first.

## Execution

### 1. Load paths from config

Read `{project-root}/_bmad/config.yaml`. Extract:
- `{implementation_artifacts}` — implementation artifacts path
- `{planning_artifacts}` — planning artifacts path
- Set `{pm_state_root}` = `{implementation_artifacts}/state`
- Set `{pm_issues_file}` = `{pm_state_root}/issues.yaml`
- Set `{pm_status}` = `{project-root}/_bmad/scripts/pm-status.py` (self-installed by the
  other PM skills; l3io-pm-help only reads, it does not self-install)

Then check whether `{pm_status}` is actually on disk and bind `{pm_status_present}`:

```bash
[ -f {project-root}/_bmad/scripts/pm-status.py ] && echo present || echo absent
```

**Never invoke `{pm_status}` when it is absent.** On a fresh install nothing has
self-installed it yet, so every `{pm_status}` call below is conditional: when
`{pm_status_present}` is `absent`, read each `epic.yaml` directly instead (it is plain YAML)
and note in the report:

```
pm-status.py not installed yet — reading epic.yaml files directly. It self-installs the
first time you run /l3io-pm-plan or /l3io-pm-execute.
```

This is a note, not a blocker: everything l3io-pm-help needs can be read without it.

### 2. Detect state layout — before reading anything, and before any recommendation

**This section gates every rule in section 4.** l3io-pm-help is the command an upgrading user
is most likely to run first, and its state probes only understand the sharded layout: against
a legacy tree every probe returns "(none)", which looks identical to an empty new project.
Recommending "create your project backlog" there would author a fresh backlog on top of live
work. So the layout is established first, and a legacy layout short-circuits to the migration
recommendation.

Use the identical three-way count `step-00-activate.md` performs — count all three, do not
stop at the first match:

```bash
SHARDED=$([ -d "{implementation_artifacts}/state" ] && echo 1 || echo 0)
LEGACY_EPIC=$([ -d "{project-root}/_bmad/state" ] && echo 1 || echo 0)
LEGACY_FLAT=$([ -f "{implementation_artifacts}/sprint-status.yaml" ] && echo 1 || echo 0)
echo "sharded=$SHARDED legacy-per-epic=$LEGACY_EPIC legacy-flat=$LEGACY_FLAT"
```

**If more than one is 1** → stop here. Print this and nothing else — do not read state, do
not build a snapshot, do not recommend anything:

```
BLOCKED: multiple state layouts detected (sharded=$SHARDED legacy-per-epic=$LEGACY_EPIC
legacy-flat=$LEGACY_FLAT). An earlier migration did not finish. Do not run any l3io-pm skill
until this is resolved — inspect both locations and remove the stale one, then re-run
/l3io-util-cleanup migrate-state.
```

**If only the legacy per-epic layout or only the legacy flat layout** → stop here. Report
what was found and give exactly one recommendation:

```
⚠️  Legacy state layout detected (legacy per-epic layout = _bmad/state/, legacy flat layout
= flat sprint-status.yaml). Your project has existing l3io-pm state in a layout the current
skills no longer read.

Next action:  /l3io-util-cleanup migrate-state

Nothing else should run first. The migration is non-destructive until its final stage and
keeps your originals as .legacy backups.
```

Never recommend `bmad-create-epics-and-stories`, `/l3io-pm-plan`, or `/l3io-pm-execute` on
this branch — a legacy tree means work already exists, and every one of those would either
block or write over it.

**If only sharded** → continue to section 3.

**If all three are 0** → possible first run. Before treating it as a blank project, rule out
an orphan caused by `implementation_artifacts` having been repointed — this is the same check
`step-00-activate.md` runs, and for the same reason: an empty probe result is not proof there
is no history.

```bash
git -C {project-root} ls-files -- '*/state/active/epic-*/epic.yaml' 'state/active/epic-*/epic.yaml' 2>/dev/null | head -5
find {project-root} -maxdepth 5 -type d -name active -path '*/state/*' 2>/dev/null | head -5
```

(The second pathspec, with no leading `*/`, catches the case where `implementation_artifacts`
equals `project-root` — git's fnmatch-pathname semantics need one literal segment before
`state/`.)

If either prints a path that is not under `{implementation_artifacts}/state`, stop here:

```
BLOCKED: state found at <printed-path> but implementation_artifacts resolves to
{implementation_artifacts}. Did implementation_artifacts change? Refusing to recommend
starting a blank project over existing state.
```

If both print nothing → genuine first run. Continue to section 3; rule 1 in section 4 may
now fire safely.

### 3. Read state files

```bash
ls -d {pm_state_root}/active/epic-*/ 2>/dev/null || echo "(none)"
ls -d {pm_state_root}/planned/epic-*/ 2>/dev/null || echo "(none)"
cat {pm_issues_file} 2>/dev/null || echo "(absent)"
cat {planning_artifacts}/plan-output-meta.yaml 2>/dev/null || echo "(absent)"
```

For each active/planned epic directory found, read its `epic.yaml` directly (key, title,
status, `_lock`, `depends_on`). If `{pm_status_present}` is `present`, you may instead use
`python3 {pm_status} show --state-root {pm_state_root} --epic {key}` for a computed roll-up
including sprint/story counts. If it is `absent`, use the direct read only.

Also surface one read-only health fact — state that is gitignored will never be committed,
which defeats the point of the layout:

```bash
git -C {project-root} check-ignore -q {pm_state_root} && echo IGNORED || echo TRACKED
```

If `IGNORED`, include this in the snapshot (it does not stop the recommendation):
```
⚠️  {pm_state_root} is gitignored — project state will not be committed. Add to .gitignore:
  !{pm_state_root}/
  !{pm_state_root}/**
```

### 4. Build health snapshot

Report to user:

**Active epics** (from `{pm_state_root}/active/epic-*/epic.yaml`):
- List each epic: key, title, current sprint, sprint status
- Flag stale locks: if `_lock.claimed_at` is older than `_lock.ttl_minutes`, mark as ⚠️ STALE LOCK

**Planned epics** (from `{pm_state_root}/planned/epic-*/epic.yaml`):
- Count them, and list any whose `depends_on` names an epic that is not yet `done` (those
  are blocked, not merely waiting). Every epic under `planned/` has `status: backlog` —
  that is the only status `pm-status.py` accepts there — so there is no status breakdown
  to print.

**Open issues** (from `{pm_issues_file}`):
- Count by severity: Critical, High, Medium, Low

**Plan status** (from `plan-output-meta.yaml`):
- `readiness`, `generated` timestamp, `phases` count, `deferred_epics` count
- If absent: note "No plan found"

### 5. Recommend next action

Section 2 has already terminated with its own recommendation on the legacy, multi-layout,
and orphan branches — this table is only reached when the sharded layout is the only one
present, or on a verified genuine first run. Apply the first matching rule:

| Condition | Recommendation |
|---|---|
| No state files, no epics (**only after section 2's first-run check passed**) | `Run bmad-create-epics-and-stories to create your project backlog first.` |
| No plan-output-meta.yaml | `Run /l3io-pm-plan to validate readiness and build the execution plan.` |
| plan readiness = red | `Run /l3io-pm-plan to resolve readiness gaps (readiness: red).` |
| plan readiness = amber | `Run /l3io-pm-plan to address readiness warnings (readiness: amber), or /l3io-pm-execute to proceed.` |
| Any epic has stale lock | `Epic {key} has a stale lock (claimed {N}m ago). Run: python3 {pm_status} clear-lock --state-root {pm_state_root} --epic {key}` |
| Active epic, no BLOCKED sprint | `Run /l3io-pm-execute {key} to continue the in-progress epic.` |
| No active epics, plan exists, planned epics available | `Run /l3io-pm-execute to start execution (plan is green).` |
| All epics done (active + planned = 0) | `All work complete. Run /l3io-pm-sync to push closure to GitHub/ADO.` |
| `plan-output-meta.yaml` lists `deferred_epics` | Surface count: `{N} epic(s) deferred in the current plan. Re-run /l3io-pm-plan to revisit them.` (deferral is recorded in the plan output, not as an epic status — `planned/` epics are always `status: backlog`.) |

Output the recommendation as a clear, one-paragraph response with the exact command to run.
