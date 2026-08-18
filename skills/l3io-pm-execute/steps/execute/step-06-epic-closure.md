# Step 06: Epic Closure

Communicate all responses in `{communication_language}`.

Run epic-level closure workflow, write actuals, archive the epic, clear the lock, and update
the per-epic calibration file.

## 1. Man-hours re-assessment — do this before anything else touches the estimate

**Required, not a suggestion.** `man_hours` is a **counterfactual** metric: what a developer,
working without AI assistance, would have needed to deliver everything this epic shipped. It
is assessed, not observed, and it is assessed **from the delivered work** — review the epic's
sprints, diffs, tests, and story scope directly. **You must form this number before reading
this epic's `estimate.man_hours_low`/`estimate.man_hours_high`** (or any report that shows
them). Reading the estimate first anchors the re-assessment toward it, which is exactly the
bias this ordering exists to prevent. Bind `{epic_man_hours}` to the result. Only after it is
bound may you read the epic's estimate, for any other purpose (e.g. reporting variance in the
closure report). See `references/metrics-contract.md` §2, §3.

## 2. Load epic-closure workflow

```
{skill-root}/steps/closure/epic-closure.md
```

Execute the full closure workflow from that file. It returns a closure report with:
- Retrospective text
- Any architectural drift findings
- Issue triage results

## 3. Sum sprint actuals → write epic actual

```bash
python3 {pm_status} show --state-root {pm_state_root} --epic {epic_key}
```

For each sprint with `status: done`, sum `actual.elapsed_hours`, `actual.hitl_hours`, and each
`actual.tokens_k` class (read the per-sprint totals from the roll-up above, or each sprint's
own `sprint.yaml` under `{pm_state_root}/active/epic-{epic_nnn}/sprint-*/` if you need
done-only precision the roll-up doesn't separate out — the roll-up reports only
`tokens_k.total`, not the per-class split). `man_hours` is **not** summed from sprints — use
`{epic_man_hours}` from §1, the epic-level re-assessment, since a sum of sprint-level
counterfactuals does not equal the counterfactual effort for the epic as a whole (it omits
cross-sprint integration work).

Under `--runtime claude`, pass the summed token classes with `--model`; `set-actual` derives
`cost` — never pass `--cost`. Under any other runtime, pass `--tokens-na` if tokens are not
observable.

```bash
python3 {pm_status} set-actual \
  --state-root {pm_state_root} \
  --node epic --epic {epic_key} \
  --runtime {runtime} \
  --elapsed-hours {total_elapsed} \
  --man-hours {epic_man_hours} \
  --hitl-hours {total_hitl_hours} \
  --tokens-input {total_tokens_input} \
  --tokens-output {total_tokens_output} \
  --tokens-cache-write {total_tokens_cache_write} \
  --tokens-cache-read {total_tokens_cache_read} \
  --model {model}
```

## 4. Orchestration capture — the orchestrator's own overhead

Separately from the epic actual above, record what the orchestrator itself spent coordinating
this epic (dispatching sprints, deciding, waiting) — time and tokens not already attributed
to any sprint. `--man-hours 0`: orchestration is AI-only overhead, so there is no
human-developer counterfactual for it. Valid on a sprint or epic node only, never a story:

```bash
python3 {pm_status} set-actual --state-root {pm_state_root} --node epic \
  --epic {epic_key} --block orchestration \
  --elapsed-hours {orch_elapsed} --man-hours 0 --hitl-hours {orch_hitl} \
  --tokens-input {orch_tokens_input} --tokens-output {orch_tokens_output} \
  --tokens-cache-write {orch_tokens_cache_write} --tokens-cache-read {orch_tokens_cache_read} \
  --model {model} --runtime {runtime}
```

This call derives its own calibration sample (the orchestration fraction) and stamps its own
replay marker (`orchestration_sampled_at`), independent of the epic actual's own marker — a
second call on the same node records nothing. See `references/metrics-contract.md` §6, §8.

## 5. Write epic closed + retrospective fields

```bash
python3 {pm_status} set-field \
  --state-root {pm_state_root} \
  --epic {epic_key} \
  --field closed.date \
  --value {today_iso}

python3 {pm_status} set-field \
  --state-root {pm_state_root} \
  --epic {epic_key} \
  --field retrospective.summary \
  --value "{retrospective_summary}"

python3 {pm_status} set-field \
  --state-root {pm_state_root} \
  --epic {epic_key} \
  --field retrospective.learnings \
  --value "{retrospective_learnings}"
```

## 6. Archive epic

`archive-epic` moves the epic's whole directory (epic.yaml, every sprint.yaml, every story
file) from `active/` to `archived/` in one step — nothing to delete afterward, since the
directory itself relocates rather than being copied:

```bash
python3 {pm_status} archive-epic --state-root {pm_state_root} --epic {epic_key}
```

## 7. Clear ownership lock

`archive-epic` moves the directory but does not touch `_lock` — clear it explicitly so the
archived epic's file doesn't carry a stale lock forward:

```bash
python3 {pm_status} clear-lock --state-root {pm_state_root} --epic {epic_key}
```

## 8. Calibration

Nothing to do here — the `set-actual --node epic` call in step 3 already derived and
appended the epic's closure calibration sample, and the `--block orchestration` call in
step 4 already derived and appended its own orchestration sample, both as a side effect of
those writes (unless `--no-calibrate` was passed). Skips are **reported on stdout**, in the
`[...]` suffix of each call's own `OK set-actual …` line, not here and not on stderr. Each
names its metric and its reason (missing sprint actual or estimate, no comparable estimate
range, estimated closure overhead ≤ 0, negative residual); a skipped metric does not stop the
others from recording. An `elapsed_hours` skip naming parallel execution is expected whenever
the epic's sprints ran concurrently. See `references/metrics-contract.md` §8.

## 9. Output

```
Step 06 complete — {epic_key} archived, actuals written, calibration updated
DONE — Epic {epic_key} complete. Sprints: {N}, Stories: {N}, Cost: {total_cost}
```
