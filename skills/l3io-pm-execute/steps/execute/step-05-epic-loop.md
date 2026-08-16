# Step 05: Epic Loop

Communicate all responses in `{communication_language}`.

Execute each epic in `{execution_phases}` order. Within a parallel phase, dispatch epics concurrently
up to `{max_parallel_subagents}`. For each epic, promote it to active, claim the lock, dispatch sprint
subagents sequentially, then trigger epic closure.

## 1. Phase iteration

For each phase in `{execution_phases}`:

If `parallel_flag=true` AND `len(epics) > 1`:
  Dispatch up to `{max_parallel_subagents}` epics concurrently per §15 adaptive parallelism.
  Each epic runs §2–§7 below as an independent execution branch.

If `parallel_flag=false` OR single epic:
  Execute each epic sequentially.

After all epics in a phase complete, verify prerequisites for the next phase are all `status: done`
before starting it.

## 2. Promote epic to active (if needed)

```bash
python3 {pm_status} move-epic --state-root {pm_state_root} --epic {epic_key} --to active
```

`move-epic` moves the epic's whole directory (epic.yaml, every sprint.yaml, every story file)
from `planned/` to `active/` in one step and sets its status to `in-progress` — nothing to
create separately. If the epic is already under `active/` (resumed run), the same-location
move is a no-op, so this call is always safe to make.

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

```bash
python3 {pm_status} show --state-root {pm_state_root} --epic {epic_key}
```

The roll-up lists each sprint under this epic with its `status`. Find all sprints where
`status != done` (sprint directories live at `{pm_state_root}/active/epic-{epic_nnn}/sprint-*/`,
in lexical — i.e. correct — order).
For sprint scope (`{exec_scope}=sprint`), filter to `{scope_sprint_key}` only.

Bind `{pending_sprints}` = ordered list of sprint `num` values (e.g. `["01", "02", "03"]`).

## 5. Sprint dispatch loop

For each sprint in `{pending_sprints}` (always sequential — no parallel sprints within an epic):

Compute `{skip_phases}` from `{work_type}`:
- `CODE`: skip none
- `DOCS`: skip adversarial, red-team, arch-drift, clean-release
- `CONFIG`: skip adversarial, red-team, ux-review
- `MIXED`: skip none

Compute `{story_keys}` = keys of all stories in this sprint with `status != done`.

Spawn headless sprint subagent with context block:

```
# l3io-pm execution context [AUTHORITATIVE — read before any step file]
work_type: {work_type}
skip_phases: {skip_phases}
epic_key: {epic_key}
epic_nnn: {epic_nnn}
sprint_root: {implementation_artifacts}/epic-{epic_nnn}/sprint-{sprint_nn}/
story_keys: [{story_keys}]
sprint_num: {sprint_num}
execute_skill_root: {skill-root}
headless: true

Load and execute in order:
  {skill-root}/steps/shared/step-00-activate.md
  {skill-root}/steps/sprint/step-02-story-prep.md
  {skill-root}/steps/sprint/step-03-dev-loop.md
  {skill-root}/steps/sprint/step-04-sprint-closure.md

End with exactly one of:
  DONE — Stories: N, Issues resolved: N, Issues deferred: N
  BLOCKED: [one-line reason]
  FAILED: [one-line reason]
```

On subagent completion:
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
