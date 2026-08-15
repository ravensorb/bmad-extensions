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

Read `{bmad_active_root}/{epic_key}-status.yaml`. For each sprint with `status: done`:
Sum `actual.elapsed_hours`, `actual.man_hours`, `actual.tokens_k`, `actual.cost`.

Add orchestration overhead estimate (0.5 man-hours, proportional elapsed).

```bash
python3 {pm_status} set-actual \
  --file {bmad_active_root}/{epic_key}-status.yaml \
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
  --file {bmad_active_root}/{epic_key}-status.yaml \
  --node epic.{epic_key} \
  --field closed.date \
  --value {today_iso}

python3 {pm_status} set-field \
  --file {bmad_active_root}/{epic_key}-status.yaml \
  --node epic.{epic_key} \
  --field retrospective.summary \
  --value "{retrospective_summary}"

python3 {pm_status} set-field \
  --file {bmad_active_root}/{epic_key}-status.yaml \
  --node epic.{epic_key} \
  --field retrospective.learnings \
  --value "{retrospective_learnings}"
```

## 4. Archive epic

Move the epic file to the archived file (flock-protected):

```bash
python3 {pm_status} archive-epic \
  --source {bmad_active_root}/{epic_key}-status.yaml \
  --dest {bmad_archived_file}
```

On success, delete the source active file:
```bash
rm {bmad_active_root}/{epic_key}-status.yaml
```

## 5. Clear ownership lock

(Lock was in the source file, now deleted — no explicit clear needed. Log completion.)

## 6. Update per-epic calibration file

Append epic-level closure overhead sample to `{project-root}/_bmad/pm-calibration-{epic_key}.yaml`:
- Record `level: epic`, metric actuals vs estimates for `man_hours`, `time_hours`, `tokens_k`, `cost`
- Skip `tokens_k` and `cost` ratio if runtime is not Claude (set `ratio: N/A`)

## 7. Output

```
Step 06 complete — {epic_key} archived, actuals written, calibration updated
DONE — Epic {epic_key} complete. Sprints: {N}, Stories: {N}, Cost: {total_cost}
```
