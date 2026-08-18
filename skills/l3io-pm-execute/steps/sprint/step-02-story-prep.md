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

Bind `{thin_story_keys}` = every story in `{story_keys}` that failed the check. If it is
empty, go to §3.

**One spawn for the whole sprint, not one per story.** An enrichment agent's cost is
dominated by reading the project — the specs, the architecture, the standards — and that read
is the same whether it then enriches one story or five. Spawning per story pays it per story.
Batching pays it once and is the single largest saving available in this step: a five-story
sprint goes from five cold reads to one. If `{thin_story_keys}` exceeds 8, split into batches
of at most 8 — past that a single agent's attention per story starts to thin, which is the
thing being bought here.

Bracket the spawn with `dispatch --event open` / `--event close`, same
`--agent bmad-create-story --epic {epic_key} --sprint {sprint_num} --session-id {session_id}`
identity on both, closing on every exit path. The bracket carries no `--story` because the
span covers several.

```
Enrich each story listed below with technical ACs. Preserve all existing content in every
file. For each story add:
- Interface contracts
- Error and edge case handling
- Observability requirements
- Security considerations
- Testability approach

Treat each story on its own terms — shared context is why these are batched, but a story
that needs a different interface contract from its neighbour must get one.

Story files (enrich every one):
{one {sprint_root}/stories/{story_key}.md per line, for each key in {thin_story_keys}}
Epic goal: {epic_goal}
work_type: {work_type}
{agent_contract}
```

Attribution: the span enriched `len({thin_story_keys})` stories, so split its spend evenly
across their `actual` blocks (`references/metrics-contract.md` §6). The even split is an
approximation and is meant to be — the alternative is paying N project reads to measure a
number that feeds calibration as a ratio, and prep cost does scale roughly with story count.

After enrichment, re-check every key in `{thin_story_keys}`. For any still missing ACs:
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
