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

### 2. Read state files

```bash
ls -d {pm_state_root}/active/epic-*/ 2>/dev/null || echo "(none)"
ls -d {pm_state_root}/planned/epic-*/ 2>/dev/null || echo "(none)"
cat {pm_issues_file} 2>/dev/null || echo "(absent)"
cat {planning_artifacts}/plan-output-meta.yaml 2>/dev/null || echo "(absent)"
```

For each active/planned epic directory found, read its `epic.yaml` directly (key, title,
status, `_lock`, `depends_on`), or use `python3 {pm_status} show --state-root {pm_state_root}
--epic {key}` for a computed roll-up including sprint/story counts.

### 3. Build health snapshot

Report to user:

**Active epics** (from `{pm_state_root}/active/epic-*/epic.yaml`):
- List each epic: key, title, current sprint, sprint status
- Flag stale locks: if `_lock.claimed_at` is older than `_lock.ttl_minutes`, mark as ⚠️ STALE LOCK

**Planned epics** (from `{pm_state_root}/planned/epic-*/epic.yaml`):
- Count by status: `backlog`, `deferred`

**Open issues** (from `{pm_issues_file}`):
- Count by severity: Critical, High, Medium, Low

**Plan status** (from `plan-output-meta.yaml`):
- `readiness`, `generated` timestamp, `phases` count
- If absent: note "No plan found"

### 4. Recommend next action

Apply the first matching rule:

| Condition | Recommendation |
|---|---|
| No state files, no epics | `Run bmad-create-epics-and-stories to create your project backlog first.` |
| No plan-output-meta.yaml | `Run /l3io-pm-plan to validate readiness and build the execution plan.` |
| plan readiness = red | `Run /l3io-pm-plan to resolve readiness gaps (readiness: red).` |
| plan readiness = amber | `Run /l3io-pm-plan to address readiness warnings (readiness: amber), or /l3io-pm-execute to proceed.` |
| Any epic has stale lock | `Epic {key} has a stale lock (claimed {N}m ago). Run: python3 {pm_status} clear-lock --state-root {pm_state_root} --epic {key}` |
| Active epic, no BLOCKED sprint | `Run /l3io-pm-execute {key} to continue the in-progress epic.` |
| No active epics, plan exists, planned epics available | `Run /l3io-pm-execute to start execution (plan is green).` |
| All epics done (active + planned = 0) | `All work complete. Run /l3io-pm-sync to push closure to GitHub/ADO.` |
| Deferred epics exist | Surface count: `{N} epic(s) deferred. Review with /l3io-pm-plan to update deferral status.` |

Output the recommendation as a clear, one-paragraph response with the exact command to run.
