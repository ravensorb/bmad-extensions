# Step 05: Epic Loop

Communicate all responses in `{communication_language}`.

Execute each epic in `{execution_phases}` order. Within a parallel phase, dispatch epics concurrently
up to `{max_parallel_subagents}`. For each epic, promote it to active, claim the lock, dispatch sprint
subagents sequentially, then trigger epic closure.

## 0. Progress rendering — only where execution is serialized

This step dispatches epics **concurrently** inside a parallel phase. Several epic subagents each
printing a progress tree would interleave into unreadable output, and subagent stdout is buried
anyway — the contract there is a one-line `DONE — [metrics]`. So render only where exactly one
writer is producing output:

| Point | Render |
|---|---|
| Phase start, phase end (this step, top level) | Yes |
| Sprint boundary when the phase holds a single epic | Yes — see `step-04-sprint-closure.md` |
| Sprint boundary inside a parallel phase | No |
| Story boundary | Never |

Nothing is lost by suppressing. Every transition still lands in `{pm_state_root}/events.jsonl`,
so `report --watch 15` in a second terminal gives full-resolution live detail while the run's own
output stays legible. Say that once, at first phase start.

Bind `{progress_cmd}` to:

```bash
python3 {pm_status} report \
  --state-root {pm_state_root} \
  --plan {planning_artifacts}/plan-output-meta.yaml \
  --format tree
```

Print its output verbatim wherever this file says to render. It is read-only and cannot affect
execution, so a non-zero exit from it is a reporting problem only: note it in one line and carry
on with the run. Never block execution on the progress view.

## 1. Phase iteration

For each phase in `{execution_phases}`:

**Render progress (phase start).** Run `{progress_cmd}` and print the output verbatim. On the
first phase of the run only, also print:

```
Live view during this run: python3 {pm_status} report --state-root {pm_state_root} \
  --plan {planning_artifacts}/plan-output-meta.yaml --watch 15
```

Bind `{single_epic_phase}` = `true` when this phase dispatches exactly one epic, else `false`.
Pass it into every sprint subagent's context block — `step-04-sprint-closure.md` reads it to
decide whether it may render.

If `parallel_flag=true` AND `len(epics) > 1`:
  Dispatch up to `{max_parallel_subagents}` epics concurrently (default 4, set per skill in
  `customize.toml`). Sprints within an epic are always sequential.
  Each epic runs §2–§7 below as an independent execution branch.

If `parallel_flag=false` OR single epic:
  Execute each epic sequentially.

After all epics in a phase complete, verify prerequisites for the next phase are all `status: done`
before starting it.

**Render progress (phase end).** Run `{progress_cmd}` and print the output verbatim, so the
phase's net effect is visible in one place before the next phase starts. This is the render that
matters most in a parallel phase: it is the first serialized point after concurrent epics have all
reported, and therefore the first time the whole phase can be shown coherently.

## 2. Skip completed epics, then promote to active (if needed)

**Check status before touching the epic** — this guard is mandatory and must run before
`move-epic`:

```bash
python3 {pm_status} show --state-root {pm_state_root} --epic {epic_key}
```

If `status=done`, skip this epic entirely — do not move it, do not lock it, do not run
sprints or closure:

```
⏭️  {epic_key} is already done — skipping (listed in the plan, completed since).
```
Continue to the next epic in the phase.

This check is not an optimization. `move-epic` resolves an epic key in *any* status folder
and unconditionally rewrites `epic.yaml` status from the destination folder, so calling it on
a finished epic would drag the directory out of `archived/`, flip `done` back to
`in-progress`, and strand it in `active/`. A plan snapshot that predates the epic's
completion is the normal way to hit this, so the guard has to be here rather than left to
the plan being current.

Then promote:

```bash
python3 {pm_status} move-epic --state-root {pm_state_root} --epic {epic_key} --to active
```

`move-epic` moves the epic's whole directory (epic.yaml, every sprint.yaml, every story file)
from `planned/` to `active/` in one step and sets its status to `in-progress` — nothing to
create separately. If the epic is already under `active/` (resumed run), the same-location
move is a no-op, so this call is safe once the `done` case above has been excluded.

## 3. Claim ownership lock

```bash
python3 {pm_status} set-lock \
  --state-root {pm_state_root} \
  --epic {epic_key} \
  --session-id {session_id} \
  --ttl-minutes {epic_lock_ttl_minutes}
```

If this fails (another session holds the lock and TTL is live):
```
BLOCKED: {epic_key} lock held by another session. Skipping this epic.
```
Continue to next epic in phase.

## 4. Identify sprints to run

Reuse the roll-up already read in §2 — it lists each sprint under this epic with its
`status`, so there is no need to run `show` a second time:

```bash
python3 {pm_status} show --state-root {pm_state_root} --epic {epic_key}
```

Find all sprints where `status != done` (sprint directories live at
`{pm_state_root}/active/epic-{epic_nnn}/sprint-*/`, in lexical — i.e. correct — order).
For sprint scope (`{exec_scope}=sprint`), filter to `{scope_sprint_key}` only.

Bind `{pending_sprints}` = ordered list of sprint `num` values (e.g. `["01", "02", "03"]`).

## 5. Sprint dispatch loop

For each sprint in `{pending_sprints}` (always sequential — no parallel sprints within an epic):

`{skip_phases}` was bound by `step-01-classify-work.md` §4 from the phase matrix there. Pass it
through unchanged — do not recompute it. Two computations of one variable is what this replaced.

Compute `{story_keys}` = keys of all stories in this sprint with `status != done`.

**Pass `{session_id}` down unchanged.** It is the orchestrator's, and every subagent stamps
its events and dispatch brackets with it. A subagent that generates its own — which is what
happened while the context block omitted the binding and `step-00-activate.md` §7 said to
generate one — splits a single run across two ids in `events.jsonl`, so the run can no longer
be filtered out of the log, and any `check-lock` from inside the sprint path sees the epic as
owned by a stranger.

**Dispatch tracking — always emit the matching close.** Bracket the sprint spawn exactly as
`steps/sprint/step-03-dev-loop.md` §2 brackets a story spawn, with the same
`--agent`/`--epic`/`--sprint`/`--session-id` identity on both calls. Without this bracket an
epic's orchestration has no recorded boundary at all — only story-level dispatches are
tracked, so a hung sprint subagent is invisible to `report --stall-minutes` and the epic's
`orchestration` block has nothing to separate it from its sprints' spend
(`references/metrics-contract.md` §6):

```bash
python3 {pm_status} dispatch --state-root {pm_state_root} --event open \
  --agent l3io-pm-sprint --epic {epic_key} --sprint {sprint_num} \
  --session-id {session_id}
```

Spawn headless sprint subagent with context block:

```
# l3io-pm execution context [AUTHORITATIVE — read before any step file]
work_type: {work_type}
skip_phases: {skip_phases}
max_fix_iterations: {max_fix_iterations}
epic_key: {epic_key}
epic_nnn: {epic_nnn}
sprint_root: {implementation_artifacts}/epic-{epic_nnn}/sprint-{sprint_nn}/
story_keys: [{story_keys}]
sprint_num: {sprint_num}
execute_skill_root: {skill-root}
single_epic_phase: {single_epic_phase}
headless: true

# Inherited activation — sections 1-7 of step-00-activate.md are ALREADY DONE for this
# project. Do not resolve config, self-install, detect layout, create directories, list
# epics, verify schema, or generate a session id. Use these bindings as given.
communication_language: {communication_language}
implementation_artifacts: {implementation_artifacts}
planning_artifacts: {planning_artifacts}
pm_status: {pm_status}
pm_state_root: {pm_state_root}
pm_issues_file: {pm_issues_file}
pm_calibration_file: {pm_calibration_file}
model: {model}
token_rates_json: {token_rates_json}
runtime: {runtime}
session_id: {session_id}

Load and execute in order:
  {skill-root}/steps/shared/step-00-digest.md
  {skill-root}/steps/sprint/step-02-story-prep.md
  {skill-root}/steps/sprint/step-03-dev-loop.md
  {skill-root}/steps/sprint/step-04-sprint-closure.md

End with exactly one of:
  DONE — Stories: N, Issues resolved: N, Issues deferred: N
  BLOCKED: [one-line reason]
  FAILED: [one-line reason]
```

On subagent completion, **first** close the dispatch — on every exit path, `DONE`, `BLOCKED`
and `FAILED` alike, and before the branch below, so an early halt cannot skip it:

```bash
python3 {pm_status} dispatch --state-root {pm_state_root} --event close \
  --agent l3io-pm-sprint --epic {epic_key} --sprint {sprint_num} \
  --session-id {session_id}
```

A dispatch left open is not merely a missed close: the next sprint that opens the same
identity silently overwrites it in `pm-status.py`'s pending map, and the original hang's
timestamp is lost for good.

Then branch:
- `DONE` → mark sprint done, continue to next sprint
- `BLOCKED` → log reason, halt epic loop, output: `BLOCKED: sprint {sprint_num} of {epic_key} — {reason}`
- `FAILED` → log reason, continue to next sprint (sprint failure is non-fatal at epic level); track count

## 6. Post-sprint re-estimation

After each sprint completes (DONE), trigger re-estimation of remaining unstarted sprints:

```bash
# Update {pm_calibration_file} with this sprint's scope/fix/closure samples
# Then re-run step-estimate over remaining unstarted sprints
```

Load `{skill-root}/steps/shared/step-estimate.md` with `{scope}={epic_key}` (remaining sprints only).
This updates estimate blocks on the epic's sprint/story node files via `pm-status.py set-estimate`.

## 7. Epic completion check

After all sprints in `{pending_sprints}` are processed:
- If any sprint is BLOCKED: output `BLOCKED: {epic_key} — sprint {sprint_num} blocked` and stop.
- If all sprints are `status: done`: proceed to step-06 (epic closure).

## 8. Output

```
Step 05 complete — epic: {epic_key}, sprints completed: {N}/{total}, stories done: {N}
```
