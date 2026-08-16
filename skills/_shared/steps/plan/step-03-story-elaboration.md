# Step 03: Story Elaboration

Communicate all responses in `{communication_language}`.

This step is **skipped** when `{work_type}` is DOCS or CONFIG (the SKILL.md router does not load it).
This step is a **no-op** when `{readiness}` is green (no technical AC gaps found).

---

## 1. Check elaboration condition

If `{readiness}` is `green` (no technical AC gaps):

Bind `{elaborated_count}` = 0 and `{failed_count}` = 0.

```
Step 03 skipped — all stories have technical ACs.
```

Skip to step 7 (output status line).

## 2. Identify thin stories

From `{planning_artifacts}/readiness-report.md`, extract all stories with an Amber "Technical ACs" finding.

For each thin story, record: `key`, `title`, the path to its story file (`{implementation_artifacts}/epic-{nnn}/sprint-{nn}/stories/{story_key}.md`).

## 3. Confirm with user (unless auto_elaborate = true)

If `{auto_elaborate}` is `false`, present:

```
📝 {count} stories need technical AC elaboration before arch review:

{list of story keys and titles}

Elaborate now? (Recommended — elaborated stories give the arch gate full technical designs.)
Type 'yes' to proceed, 'skip' to continue without elaborating.
```

If user types `skip`, go to step 7 (output status line without elaborating).

If `{auto_elaborate}` is `true`, proceed directly to step 4 without prompting.

## 4. Elaborate each thin story

Elaborate **in place**, directly in this step. Do **not** spawn `bmad-create-story` — it
authors a *new* story from `template.md` at a flat `{implementation_artifacts}/{story_key}.md`
path and auto-discovers work from a legacy flat `sprint-status.yaml`. Neither matches the
sharded state layout (`references/status-files.md`), so it produces orphan files at the wrong
path or halts.

For each thin story in sequence:

```
Elaborating {story_key}: {story_title}...
```

Read the existing story file at
`{implementation_artifacts}/epic-{nnn}/sprint-{nn}/stories/{story_key}.md`.

If `l3io-arch-review` is installed, load `l3io-arch-review/references/standards-core.md` plus
any overlay matching the story's stack, and let those standards shape the ACs you write.

**Edit that file in place.** Preserve every existing section verbatim — elaboration is additive.
Append the technical ACs the story lacks, covering each dimension that applies to the story
(skip a dimension only when it genuinely does not apply, and say so rather than omitting it):

| Dimension | What to add |
|---|---|
| Interface contracts | API signatures, function/CLI surfaces, events, message shapes |
| Data model | New or changed schemas, fields, migrations, persisted formats |
| Error and edge cases | Failure modes, invalid input, partial/empty/concurrent states |
| Observability | Log lines and levels, metrics, trace/correlation IDs |
| Security | AuthN/AuthZ, input validation, secret and PII handling |
| Testability | Unit and integration test anchors, mock boundaries, fixtures |

Constraints:

- Write only to the story file's own path. Create no new files.
- Do not change the story's `classification`, `estimate`, or `status` — step-02 and
  `pm-status.py` own those.

Record result: `elaborated`, or `failed` with the reason.

## 5. Re-run readiness on updated stories

After all stories are processed, re-run the Technical ACs check from step-02 on the elaborated stories only. Update `{readiness}`:

- All previously-amber stories now green → `{readiness}` = `green` (or `amber` if non-AC gaps remain)
- Any story still lacking technical ACs → keep `{readiness}` = `amber`

## 6. Write elaboration-summary.md

Write `{planning_artifacts}/elaboration-summary.md`:

```markdown
# Elaboration Summary

Generated: {timestamp}
Stories elaborated: {elaborated_count}
Stories failed: {failed_count}

## Results

| Story | Result | Notes |
|-------|--------|-------|
| E001-S01-002 | ✅ Elaborated | Technical ACs added (interfaces, error handling, observability) |
| E002-S01-001 | ❌ Failed | story file not found at expected sharded path |
```

If any story was elaborated by a route other than this step's in-place procedure, record that
deviation here — the summary is the audit trail for how the ACs were produced.

## 7. Output status line

```
Step 03 complete — elaborated: {elaborated_count}, failed: {failed_count}, readiness after: {readiness}
```
