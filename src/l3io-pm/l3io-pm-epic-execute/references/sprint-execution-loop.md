# Sprint Execution Loop

Communicate all responses in `{communication_language}`.

**Orchestrator role:** Traffic controller. Hold only sprint summaries (status-line metrics) — never sprint story details, diffs, or implementation content.

**Subagent invocation:** Agent tool preferred (self-contained prompt, no conversation history forwarded). Fallback: `claude --print`. Every subagent must end with exactly one status line:
```
DONE — [brief metrics]
BLOCKED: [one-line reason]
FAILED: [one-line reason]
```

**Adaptive parallelism for sprints:** Sequential by default. Parallel sprint batches only when sprint groups are proven independent (no shared story files, no cross-sprint dependencies) and status merges are serialized. `effective_parallel_subagents` = min(`{max_parallel_subagents}`, 4, safe_batch_size). Force to 1 when `{parallel_mode}` = `off` or any safety check is uncertain.

**Progress reporting:** ETA ranges (`~3-8 min`), not exact timestamps. Report sprint position (`N/M`) and batch size. Refresh ETA after each sprint completes.

---

## Step 2 — Sprint Execution

For each sprint in `{sprint_plan}` (sequential default; parallel batch when safe):

Resolve `{current_sprint_padded}` as a two-digit zero-padded value. Announce:
```
Spawning sprint subagent {current_sprint_num} of {total_sprint_count} — stories: {sprint_story_keys}
```

Spawn subagent:
```
Load config from: {config_file}
Load project context from: {context_file} (if it exists)
State files: split layout under {implementation_artifacts} (sprint-status-active.yaml / -backlog.yaml / -archived.yaml) — resolve per references/status-files.md
Target: Epic {target_epic}, stories: {sprint_story_keys}
Sprint number: {current_sprint_num} (two-digit: {current_sprint_padded})
Expected sprint output root: {epic_root_dir}/sprint-{current_sprint_padded}
Invoke skill: l3io-pm-sprint-execute
Execute the complete sprint for the listed stories — all per-story phases and closure phases.
Promote the sprint to the active state file and update it as stories complete, per references/status-files.md.
Print when done:
  DONE — Stories: N, Issues resolved: N, Issues deferred: N, Retro: [path]
  BLOCKED: [reason]
  FAILED: [reason]
```

Wait for the subagent to complete. Read its status line — record `{sprint_stories_done}`, `{sprint_issues_resolved}`, `{sprint_issues_deferred}`, `{sprint_retro_path}`.

If BLOCKED or FAILED: halt and report the status line to `{user_name}`. Wait for resolution before continuing.

Announce: "Sprint {current_sprint_num} closed — {sprint_stories_done} stories delivered."

Append to `{sprint_summaries}`: sprint number + status-line metrics.

If this is not the last sprint, announce to `{user_name}` (informational, no confirmation requested): "Proceeding to Sprint {next_sprint_num} of {total_sprint_count}." The epic orchestrator continues immediately to the next sprint without waiting.

---

---

## Pre-Closure Validation Gate

All sprints in `{sprint_plan}` have completed. Before proceeding to `references/epic-closure.md`, perform a targeted validation read of all sprint and story nodes for Epic `{target_epic}` in `{status_active}`.

**Sprint completeness check:** For each sprint in `{sprint_plan}`, verify:

| Field | Expected |
|---|---|
| Sprint `status` | `done` |
| Sprint `closed` | non-empty date string |
| Sprint `actual.elapsed_hours` | numeric, non-null |
| Sprint `actual.man_hours` | numeric, non-null |
| Sprint `actual.tokens_k` | numeric or `N/A` — field must exist (not absent) |
| Sprint `actual.cost` | `$X.XX` or `N/A` — field must exist (not absent) |

**Story completeness check:** For each story across all sprints, verify `status == done`.

Report the validation result:
```
PRE-CLOSURE VALIDATION — Epic {target_epic}
Sprints:        {sprint_count} total — {pass_count} fully validated, {gap_count} with gaps
Stories:        {total_stories} total — {done_stories} done, {not_done_stories} not done
Sprint actuals: {actuals_ok_count} complete, {missing_actuals_count} missing/incomplete fields
```

**If all checks pass:** log the report and proceed immediately to `references/epic-closure.md`.

**If gaps exist:** announce to `{user_name}`:
```
Epic Orchestrator: PRE-CLOSURE VALIDATION — gaps found before Epic {target_epic} closure.
{for each gap: sprint ID or story key — specific missing/incorrect field}
Attempting autonomous resolution...
```

Then for each gap type:

- **Sprint not `done` or story not `done`**: spawn a targeted resume subagent — invoke `l3io-pm-sprint-execute` for that sprint with only the remaining (non-done) stories. After it completes, re-run this validation check. If the gap persists after one retry, halt and report to `{user_name}` — do not close the epic with incomplete work.

- **Sprint `actual` block missing or incomplete field**: spawn a targeted recovery subagent:
  ```
  Load config from: {config_file}
  Sprint status file: {status_active}
  Target: Epic {target_epic}, Sprint {sprint_id}
  Sprint start timestamp (if known from sprint sign-off): {sprint_start_ts}
  Task: Re-compute missing actual metrics for this sprint using references/metrics-contract.md.
  - elapsed_hours: derive from closed date vs. sprint start timestamp if available; otherwise use story actual.elapsed_hours sum.
  - tokens_k: sum story actual.tokens_k values (skip N/A); if none are numeric, write N/A.
  - cost: derive from tokens_k × model rate per metrics-contract; write N/A if tokens_k is N/A.
  - man_hours: sum story actual.man_hours values + 24h closure overhead.
  Write the corrected actual block to the sprint node in {status_active}.
  For any metric that is genuinely unresolvable, write N/A — never omit the field.
  Print: DONE — fields recovered: [list] | fields set N/A: [list] | FAILED: [reason]
  ```
  After the subagent completes, re-validate the sprint node.

Once all gaps are resolved or acknowledged (fields written as `N/A` where unresolvable), log the final validation state and proceed to `references/epic-closure.md`.
