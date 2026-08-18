# Sprint Step 04: Sprint Closure

Communicate all responses in `{communication_language}`.

Run closure phases gated by `{work_type}` and `{skip_phases}`. Write sprint actuals, mark sprint
done, and emit the required status line.

## 1. Man-hours re-assessment — do this before anything else touches the estimate

**Required, not a suggestion.** `man_hours` is a **counterfactual** metric: what a developer,
working without AI assistance, would have needed to deliver everything this sprint's stories
shipped. It is assessed, not observed, and it is assessed **from the delivered work** —
review the sprint's diffs, tests, and story scope directly. **You must form this number
before reading this sprint's `estimate.man_hours_low`/`estimate.man_hours_high`** (or any
report that shows them). Reading the estimate first anchors the re-assessment toward it,
which is exactly the bias this ordering exists to prevent. Bind `{sprint_man_hours}` to the
result. Only after it is bound may you read the sprint's estimate, for any other purpose
(e.g. reporting variance in the closure report). See `references/metrics-contract.md` §2, §3.

## 2. Load sprint-closure workflow

```
{execute_skill_root}/steps/closure/sprint-closure.md
```

Execute it fully. It returns: issues found (with severities), retrospective text, carry_over count.

## 3. Sum story actuals → write sprint actual

```bash
python3 {pm_status} show --state-root {pm_state_root} --epic {epic_key} --sprint {sprint_num}
```

Sum `actual.elapsed_hours`, `actual.hitl_hours`, and each `actual.tokens_k` class across all
stories in `{sprint_num}` with `status: done` (the roll-up above lists each story's `actual`
totals; read per-class token counts from each story's own node file — `show` reports only the
`tokens_k.total`). `man_hours` is **not** summed from stories — use `{sprint_man_hours}` from
§1, the sprint-level re-assessment, since a sum of story-level counterfactuals does not equal
the counterfactual effort for the sprint as a whole (it omits integration and cross-story
work). Under `--runtime claude`, pass the summed token classes with `--model`; `set-actual`
derives `cost` — never pass `--cost`. Under any other runtime, pass `--tokens-na` if tokens
are not observable.

```bash
python3 {pm_status} set-actual \
  --state-root {pm_state_root} \
  --node sprint \
  --epic {epic_key} \
  --sprint {sprint_num} \
  --runtime {runtime} \
  --elapsed-hours {total_elapsed} \
  --man-hours {sprint_man_hours} \
  --hitl-hours {total_hitl_hours} \
  --tokens-input {total_tokens_input} \
  --tokens-output {total_tokens_output} \
  --tokens-cache-write {total_tokens_cache_write} \
  --tokens-cache-read {total_tokens_cache_read} \
  --model {model}
```

## 4. Orchestration capture — the orchestrator's own overhead

Separately from the sprint actual above, record what the orchestrator itself spent
coordinating this sprint (dispatching subagents, deciding, waiting) — time and tokens not
already attributed to any story. `--man-hours 0`: orchestration is AI-only overhead, so there
is no human-developer counterfactual for it. Valid on a sprint or epic node only, never a
story:

```bash
python3 {pm_status} set-actual --state-root {pm_state_root} --node sprint \
  --epic {epic_key} --sprint {sprint_num} --block orchestration \
  --elapsed-hours {orch_elapsed} --man-hours 0 --hitl-hours {orch_hitl} \
  --tokens-input {orch_tokens_input} --tokens-output {orch_tokens_output} \
  --tokens-cache-write {orch_tokens_cache_write} --tokens-cache-read {orch_tokens_cache_read} \
  --model {model} --runtime {runtime}
```

This call derives its own calibration sample (the orchestration fraction) and stamps its own
replay marker (`orchestration_sampled_at`), independent of the sprint actual's own marker — a
second call on the same node records nothing. See `references/metrics-contract.md` §6, §8.

## 5. Write sprint closed + retrospective

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

## 6. Mark sprint done

```bash
python3 {pm_status} set-status \
  --state-root {pm_state_root} \
  --epic {epic_key} \
  --sprint {sprint_num} \
  --status done
```

## 7. Calibration

Nothing to do here — the `set-actual --node sprint` call in step 3 already derived and
appended the sprint's closure calibration sample, and the `--block orchestration` call in
step 4 already derived and appended its own orchestration sample, both as a side effect of
those writes (unless `--no-calibrate` was passed). Skips are **reported on stdout**, in the
`[...]` suffix of each call's own `OK set-actual …` line, not here and not on stderr. Each
names its metric and its reason (missing child actual or estimate, no comparable estimate
range, estimated closure overhead ≤ 0, negative residual); a skipped metric does not stop the
others from recording. An `elapsed_hours` skip naming parallel execution is expected whenever
the sprint's stories ran concurrently — the sprint's wall-clock is legitimately below their
sum. See `references/metrics-contract.md` §8.

## 8. Progress render and report regeneration

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

## 9. Required exit status line

```
DONE — Stories: {N}, Issues resolved: {N_resolved}, Issues deferred: {N_deferred}
```
