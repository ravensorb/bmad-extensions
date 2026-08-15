# Sprint Step 02: Story Preparation

Communicate all responses in `{communication_language}`.

Validate and prepare all stories in this sprint for development. Run the technical AC gate,
write estimates, and mark stories ready-for-dev.

## 1. Gate eligibility

Skip technical AC gate (proceed to §3) if `{work_type}` is `DOCS` or `CONFIG`.

## 2. Technical AC gate

Read `{epic_status_file}` and bind `{epic_goal}` from the first epic's `goal` field.
This is needed for story enrichment prompts below.

For each story key in `{story_keys}`:

Read story file at `{sprint_root}/stories/{story_key}.md`.

Check for presence of technical ACs — the story must have at least one of:
- Interface contracts (API signatures, data models, events)
- Error and edge case handling specifications
- Observability requirements (logging, metrics, tracing)
- Security requirements (auth, validation, data handling)
- Testability hooks (test entry points, mock boundaries)

If `l3io-arch-review` is installed, use its story-AC-check mode. Otherwise apply the built-in
checklist above.

**If technical ACs are missing (gate: "block" — always enforced):**

For each story missing technical ACs:
1. Spawn `bmad-create-story` subagent with the story file path and this context:
   ```
   Enrich this story with technical ACs. Preserve all existing content. Add:
   - Interface contracts
   - Error and edge case handling
   - Observability requirements
   - Security considerations
   - Testability approach
   Story file: {sprint_root}/stories/{story_key}.md
   Epic goal: {epic_goal}
   work_type: {work_type}
   ```
2. After enrichment, re-check: if still missing after one elaboration pass:
   ```
   BLOCKED: story {story_key} still missing technical ACs after elaboration. Investigate manually.
   ```

## 3. Write story estimates

For each story in `{story_keys}` that does not already have an `estimate` block:

Read classification from story file (`classification: simple|standard|complex`).

Apply estimation model (cold-start or calibrated from `_bmad/pm-calibration-{epic_key}.yaml`):

| Classification | man_hours | time_hours | tokens_k | cost |
|---|---|---|---|---|
| simple | 2 | 0.5 | 20 | 0.14 |
| standard | 4 | 1.5 | 40 | 0.28 |
| complex | 8 | 3.0 | 80 | 0.56 |

If calibration file has ≥3 scope samples for this classification, use calibrated ratios instead
of the table above.

```bash
python3 {pm_status} set-estimate \
  --file {epic_status_file} \
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
  --file {epic_status_file} \
  --story {story_key} \
  --status ready-for-dev
```

## 5. Output

```
Sprint Step 02 complete — stories prepared: {N}, estimates written: {N}, blocked: {N}
```
