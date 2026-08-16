# Step 06: Epic Closure

Communicate all responses in `{communication_language}`.

Run epic-level closure workflow, write actuals, archive the epic, clear the lock, and update
the per-epic calibration file.

## 1. Load epic-closure workflow

```
{skill-root}/steps/closure/epic-closure.md
```

Execute the full closure workflow from that file. It returns a closure report with:
- Retrospective text
- Any architectural drift findings
- Issue triage results

## 2. Sum sprint actuals → write epic actual

```bash
python3 {pm_status} show --state-root {pm_state_root} --epic {epic_key}
```

For each sprint with `status: done`, sum `actual.elapsed_hours`, `actual.man_hours`,
`actual.tokens_k`, `actual.cost` (read the per-sprint totals from the roll-up above, or each
sprint's own `sprint.yaml` under `{pm_state_root}/active/epic-{epic_nnn}/sprint-*/` if you need
done-only precision the roll-up doesn't separate out).

Add orchestration overhead estimate (0.5 man-hours, proportional elapsed).

```bash
python3 {pm_status} set-actual \
  --state-root {pm_state_root} \
  --node epic --epic {epic_key} \
  --runtime {runtime} \
  --elapsed-hours {total_elapsed} \
  --man-hours {total_man_hours} \
  --tokens-k {total_tokens_k} \
  --cost {total_cost}
```

## 3. Write epic closed + retrospective fields

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

## 4. Archive epic

`archive-epic` moves the epic's whole directory (epic.yaml, every sprint.yaml, every story
file) from `active/` to `archived/` in one step — nothing to delete afterward, since the
directory itself relocates rather than being copied:

```bash
python3 {pm_status} archive-epic --state-root {pm_state_root} --epic {epic_key}
```

## 5. Clear ownership lock

`archive-epic` moves the directory but does not touch `_lock` — clear it explicitly so the
archived epic's file doesn't carry a stale lock forward:

```bash
python3 {pm_status} clear-lock --state-root {pm_state_root} --epic {epic_key}
```

## 6. Calibration

Nothing to do here — the `set-actual --node epic` call in step 2 already derived and
appended the epic's closure calibration sample as part of that write (unless
`--no-calibrate` was passed). Skips are **reported on stdout**, in the `[...]` suffix of
that call's own `OK set-actual …` line, not here and not on stderr. Each names its metric
and its reason (missing sprint actual or estimate, no comparable estimate range, estimated
closure overhead ≤ 0, negative residual); a skipped metric does not stop the others from
recording. A `time_hours` skip naming parallel execution is expected whenever the epic's
sprints ran concurrently. See `references/metrics-contract.md` §8.

## 7. Output

```
Step 06 complete — {epic_key} archived, actuals written, calibration updated
DONE — Epic {epic_key} complete. Sprints: {N}, Stories: {N}, Cost: {total_cost}
```
