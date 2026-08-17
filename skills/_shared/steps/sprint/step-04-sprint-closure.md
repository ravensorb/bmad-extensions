# Sprint Step 04: Sprint Closure

Communicate all responses in `{communication_language}`.

Run closure phases gated by `{work_type}` and `{skip_phases}`. Write sprint actuals, mark sprint
done, and emit the required status line.

## 1. Load sprint-closure workflow

```
{execute_skill_root}/steps/closure/sprint-closure.md
```

Execute it fully. It returns: issues found (with severities), retrospective text, carry_over count.

## 2. Sum story actuals → write sprint actual

```bash
python3 {pm_status} show --state-root {pm_state_root} --epic {epic_key} --sprint {sprint_num}
```

Sum `actual.*` across all stories in `{sprint_num}` with `status: done` (the roll-up above
lists each story's `actual` totals). Add sprint orchestration overhead (0.2 man-hours,
proportional elapsed).

```bash
python3 {pm_status} set-actual \
  --state-root {pm_state_root} \
  --node sprint \
  --epic {epic_key} \
  --sprint {sprint_num} \
  --runtime {runtime} \
  --elapsed-hours {total_elapsed} \
  --man-hours {total_man_hours} \
  --tokens-k {total_tokens_k} \
  --cost {total_cost}
```

## 3. Write sprint closed + retrospective

```bash
python3 {pm_status} set-field \
  --state-root {pm_state_root} \
  --epic {epic_key} --sprint {sprint_num} \
  --field closed.date \
  --value {today_iso}

python3 {pm_status} set-field \
  --state-root {pm_state_root} \
  --epic {epic_key} --sprint {sprint_num} \
  --field retrospective.summary \
  --value "{retrospective_summary}"

python3 {pm_status} set-field \
  --state-root {pm_state_root} \
  --epic {epic_key} --sprint {sprint_num} \
  --field retrospective.velocity \
  --value {stories_done}

python3 {pm_status} set-field \
  --state-root {pm_state_root} \
  --epic {epic_key} --sprint {sprint_num} \
  --field retrospective.carry_over \
  --value {carry_over_count}
```

## 4. Mark sprint done

```bash
python3 {pm_status} set-status \
  --state-root {pm_state_root} \
  --epic {epic_key} \
  --sprint {sprint_num} \
  --status done
```

## 5. Calibration

Nothing to do here — the `set-actual --node sprint` call in step 2 already derived and
appended the sprint's closure calibration sample as part of that write (unless
`--no-calibrate` was passed). Skips are **reported on stdout**, in the `[...]` suffix of
that call's own `OK set-actual …` line, not here and not on stderr. Each names its metric
and its reason (missing child actual or estimate, no comparable estimate range, estimated
closure overhead ≤ 0, negative residual); a skipped metric does not stop the others from
recording. A `time_hours` skip naming parallel execution is expected whenever the sprint's
stories ran concurrently — the sprint's wall-clock is legitimately below their sum. See
`references/metrics-contract.md` §8.

## 6. Progress render and report regeneration

**Render (conditional).** Only when `{single_epic_phase}` is `true`. Inside a parallel phase this
output would interleave with sibling epics and is suppressed by design — see §0 of
`step-05-epic-loop.md`. When it is `true`:

```bash
python3 {pm_status} report \
  --state-root {pm_state_root} \
  --plan {planning_artifacts}/plan-output-meta.yaml \
  --format tree
```

**Regenerate the committed report (always, both branches).** Closure is a natural commit point.
Regenerating per story transition instead would churn git on every status move and put parallel
subagents in contention over one file:

```bash
python3 {pm_status} report \
  --state-root {pm_state_root} \
  --plan {planning_artifacts}/plan-output-meta.yaml \
  --format md --out {implementation_artifacts}/progress-report.md
```

That file is a generated view and says so in its own header. Never hand-edit it; regenerate it.
Both commands are read-only with respect to state — a failure in either is a reporting problem,
so note it in one line and continue to the exit status line rather than failing the sprint.

## 7. Required exit status line

```
DONE — Stories: {N}, Issues resolved: {N_resolved}, Issues deferred: {N_deferred}
```
