# Sprint Step 02: Story Preparation

Communicate all responses in `{communication_language}`.

Validate and prepare all stories in this sprint for development. Run the technical AC gate,
write estimates, and mark stories ready-for-dev.

## 1. Gate eligibility

Skip technical AC gate (proceed to §3) if `{work_type}` is `DOCS` or `CONFIG`.

## 2. Technical AC gate

```bash
python3 {pm_status} show --state-root {pm_state_root} --epic {epic_key}
```

Read `{pm_state_root}/{active|planned|archived}/epic-{epic_nnn}/epic.yaml` (wherever
`find_epic_dir` resolves it — normally `active/` at this point in the flow) and bind
`{epic_goal}` from its `goal` field. This is needed for story enrichment prompts below.

For each story key in `{story_keys}`:

Read story file at `{sprint_root}/stories/{story_key}.md`.

Check for presence of technical ACs — the story must have at least one of:
- Interface contracts (API signatures, data models, events)
- Error and edge case handling specifications
- Observability requirements (logging, metrics, tracing)
- Security requirements (auth, validation, data handling)
- Testability hooks (test entry points, mock boundaries)

Apply the built-in checklist above. If `l3io-arch-review` is installed, also load
`l3io-arch-review/references/standards-core.md` (plus any overlay matching the story's stack)
and hold the story to those standards as well.

**If technical ACs are missing (gate: "block" — always enforced):**

Enrich **in place**, directly in this step. Do **not** spawn `bmad-create-story` — it authors a
*new* story from `template.md` at a flat `{implementation_artifacts}/{story_key}.md` path and
auto-discovers work from a legacy flat `sprint-status.yaml`. Neither matches the sharded state
layout (`references/status-files.md`), so it produces orphan files at the wrong path or halts.

For each story missing technical ACs:

1. Edit `{sprint_root}/stories/{story_key}.md` in place, preserving all existing content
   verbatim. Append the missing technical ACs, informed by `{epic_goal}` and `{work_type}`,
   covering each dimension from the checklist above that applies: interface contracts, data
   model changes, error and edge case handling, observability, security, and testability.
   Write only to that path — create no new files, and do not touch `classification`,
   `estimate`, or `status` (§3 and §4 own those).
2. Re-check against the checklist. If still missing after one enrichment pass:

   ```
   BLOCKED: story {story_key} still missing technical ACs after elaboration. Investigate manually.
   ```

## 3. Write story estimates

For each story in `{story_keys}` that does not already have an `estimate` block:

Read classification from story file (`classification: simple|standard|complex`).

Apply estimation model (cold-start or calibrated from `{pm_calibration_file}`):

| Classification | man_hours | time_hours | tokens_k | cost |
|---|---|---|---|---|
| simple | 2 | 0.5 | 20 | 0.14 |
| standard | 4 | 1.5 | 40 | 0.28 |
| complex | 8 | 3.0 | 80 | 0.56 |

If calibration file has ≥3 scope samples for this classification, use calibrated ratios instead
of the table above.

```bash
python3 {pm_status} set-estimate \
  --state-root {pm_state_root} \
  --story {story_key} \
  --man-hours {h} \
  --time-hours {h} \
  --tokens-k {n} \
  --cost {usd} \
  --confidence {level}
```

## 4. Mark stories ready-for-dev

For each story in `{story_keys}` with `status: backlog`:

```bash
python3 {pm_status} set-status \
  --state-root {pm_state_root} \
  --story {story_key} \
  --status ready-for-dev
```

## 5. Output

```
Sprint Step 02 complete — stories prepared: {N}, estimates written: {N}, blocked: {N}
```
