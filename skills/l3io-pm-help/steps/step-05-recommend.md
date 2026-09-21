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
| Any epic has stale lock | `Epic {key} has a stale lock (claimed {N}m ago). Run: uv run {pm_status} clear-lock --state-root {pm_state_root} --epic {key}` |
| Active epic, no BLOCKED sprint | `Run /l3io-pm-execute {key} to continue the in-progress epic.` |
| No active epics, plan exists, planned epics available | `Run /l3io-pm-execute to start execution (plan is green).` |
| All epics done (active + planned = 0) | `All work complete. Run /l3io-pm-sync to push closure to GitHub/ADO.` |

**One more follow-up, checked after the table above:** if `{pm_status_present}` is `absent`,
prepend it to the recommendation — this takes priority because it explains a failure the user
would otherwise hit with no clue why:
`pm-status.py is missing at {project-root}/_bmad/scripts/pm-status.py. Run /l3io-util-doctor
first to install it — this report read epic.yaml directly instead.`

Output the recommendation as a clear, one-paragraph response with the exact command to run.

