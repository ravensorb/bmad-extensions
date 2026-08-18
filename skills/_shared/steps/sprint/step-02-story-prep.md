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

The model's only job is supplying the classification — `estimate-story` does the rest: it
looks up the cold-start base band (or the calibrated per-metric scope ratio once a metric has
≥3 samples), applies the classification's fix factor, and derives `cost` from the resulting
`tokens_k` and `--model`. **Do not hand-compute the base bands or ratios here** — they live in
`BASE_BANDS` inside `pm-status.py`, not in this file, and a re-derivation here can drift from
what `estimate-story` actually applies. See `references/metrics-contract.md` §6.

```bash
python3 {pm_status} estimate-story \
  --state-root {pm_state_root} \
  --story {story_key} \
  --classification {simple|standard|complex} \
  --model {model} \
  [--token-rates '{token_rates_json}'] \
  [--confidence {low|medium|high}]
```

`{model}` and `{token_rates_json}` are bound at activation (`step-00-activate.md` §1). Pass
`--model` always; add `--token-rates` only when `{token_rates_json}` is non-empty.

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
