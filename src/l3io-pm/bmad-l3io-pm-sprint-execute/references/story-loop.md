# Per-Story Execution Loop

Communicate all responses in `{communication_language}`.

Load `references/testing-guidelines.md` and keep its guidance in context for all development and QA phases.

**Orchestrator role:** Traffic controller. Hold only story keys and statuses. Never read story file contents into context — pass paths to subagents and read only status lines plus targeted field checks from disk.

**Subagent invocation:** Use the Agent tool with a self-contained prompt — never forward conversation history, pass only paths and the skill to invoke. Fallback when Agent tool is unavailable:
```bash
claude --print "$(cat <<'PROMPT'
[self-contained prompt]
PROMPT
)"
```
Every subagent must end with exactly one status line:
```
DONE — [brief metrics]
BLOCKED: [one-line reason]
FAILED: [one-line reason]
```

**Deferred cleanup:** When `{deferred_file_cleanup}` is `true`, append the following instruction to every subagent prompt you spawn:
```
DEFERRED CLEANUP ACTIVE: Do not execute rm commands directly. Instead, append each rm command as its own line to {cleanup_script} (create with #!/bin/bash header if it does not exist). Continue all other work normally.
```

**Adaptive parallelism:** Stories may run in parallel — across stories only, never across phases within the same story. Before each parallel batch: verify no shared file path overlap between stories, no concurrent writes to `{status_file}`, no unresolved blocker that would invalidate siblings. If any check is uncertain, run sequentially. `effective_parallel_subagents` = min(`{max_parallel_subagents}`, 4, safe_batch_size). Force to 1 when `{parallel_mode}` = `off`.

**Story ordering:** Before starting parallel execution, check story files or `{status_file}` for `depends_on` fields. A story cannot enter development until all declared dependencies are `done`. Process independent stories in parallel batches; dependent stories wait for their dependencies.

**Progress reporting:** Use ETA ranges (`~2-5 min`), not exact timestamps. Report position (`N/M`) and batch size for parallel runs. Refresh ETA after each completion.

---

## 2a — Story Preparation

For each story in `{sprint_stories}`:

Set `{story_file_path}` = `{story_output_dir}/{story_key}.md`.

Check for a legacy flat file at `{implementation_artifacts}/{story_key}.md`. If found and `{story_file_path}` does not exist, move it to `{story_file_path}` before proceeding.

If `{story_file_path}` exists, read only its Status field and section headers to verify completeness — do not load full content into context.

If `{story_file_path}` does not exist, spawn a story preparation subagent:
```
Load config from: {config_file}
Load project context from: {context_file} (if it exists — do not fail if absent)
Invoke skill: bmad-create-story
Target: Epic {target_epic}, Story {story_num}
Write the story file to: {story_file_path}
Place any planning documents under: {planning_sprint_dir}/stories/
If the skill writes to a legacy flat path, the orchestrator will relocate it.
Print when done: DONE | BLOCKED: [reason]
```

Halt on BLOCKED — report to `{user_name}` and wait for resolution before continuing.

Announce story prep complete to `{user_name}` (informational, no confirmation requested): story title + acceptance criteria count + task count (from file headers only). Update status to `ready-for-dev` in `{status_file}` and continue immediately to development.

---

## 2b — Development

Announce start. Update status to `in-progress` in `{status_file}`.

Spawn subagent:
```
Load config from: {config_file}
Load project context from: {context_file} (if it exists)
Story file: {story_file_path}
Invoke skill: bmad-dev-story
All tasks and subtasks must be checked [x] before finishing.
Update the story file Dev Agent Record and File List as the skill requires.
Unit test guidance: {skill-root}/references/testing-guidelines.md — apply test quality review (coverage, relevance, parallelism) when writing or updating tests.
Print when done: DONE | BLOCKED: [reason] | FAILED: [reason]
```

After completion, verify from `{story_file_path}`: all task checkboxes [x], Dev Agent Record populated, File List populated. Halt on failure — report to `{user_name}` and wait for guidance.

Update status to `review` in `{status_file}`.

---

## 2c — Code Review

Read the File List section from `{story_file_path}` — extract `{changed_files}` (this targeted read only; do not load the full file).

Spawn subagent:
```
Load config from: {config_file}
Load project context from: {context_file} (if it exists)
Story file: {story_file_path}
Changed files: {changed_files}
Invoke skill: bmad-code-review
Review the changed files listed above as implemented in this story.
Write findings to the story file Dev Agent Record section.
Print when done: DONE — Critical: N, High: N, Medium: N, Low: N | BLOCKED: [reason]
```

Record `{cr_critical}` and `{cr_high}` from the status line. If either is non-zero, add findings to `{story_issues}` and route immediately to Step 2e.

---

## 2d — QA

Spawn subagent:
```
Load config from: {config_file}
Load project context from: {context_file} (if it exists)
Story file: {story_file_path}
Invoke skill: bmad-qa-generate-e2e-tests
Target: the feature implemented in this story.
Run all generated tests and verify they pass before finishing.
Test output caching: pipe all test runs through `tee /tmp/test-run-$(date +%Y%m%d-%H%M%S).log` so failure details are available without re-running. After analysis: if `{deferred_file_cleanup}` is `true`, append `rm /tmp/test-run-*.log` to `{cleanup_script}` (create with #!/bin/bash header if absent) — do not delete inline; otherwise delete the log immediately.
Unit test guidance: {skill-root}/references/testing-guidelines.md — apply test quality review (coverage, relevance, parallelism) when reviewing generated tests.
Write test results summary to the story file Dev Agent Record.
Write QA evidence to: {test_output_dir}/epic-{target_epic_padded}-sprint-{target_sprint_padded}-{story_key}-qa-{date}.md
Print when done: DONE — Tests: N written, N passing | FAILURES: N tests failing — [brief description] | BLOCKED: [reason]
```

If all tests pass: update status to `done` in `{status_file}`. Announce: "Story {story_key} — DONE." Move to the next story.

If FAILURES: add to `{story_issues}` and route to Step 2e.

---

## 2e — Fix Loop

Maintain `{fix_iteration}` = 0 and `{story_issues}` (list of unresolved issue descriptions from code review or QA).

For each issue, spawn a fix subagent:
```
Load config from: {config_file}
Load project context from: {context_file} (if it exists)
Story file: {story_file_path}
Issue to fix: {issue_description}
Invoke skill: bmad-dev-story
Target the specific issue above. Read the story Dev Agent Record for full context.
After fixing, re-run the affected tests to verify resolution. Cache test output: pipe through `tee /tmp/test-run-$(date +%Y%m%d-%H%M%S).log`. After analysis: if `{deferred_file_cleanup}` is `true`, append `rm /tmp/test-run-*.log` to `{cleanup_script}` (create with #!/bin/bash header if absent) — do not delete inline; otherwise delete the log.
Update the story Dev Agent Record with fix notes.
Print when done: FIXED | PARTIAL: [what remains] | FAILED: [reason]
```

Increment `{fix_iteration}`. After fix, re-run Step 2d (QA) to confirm all tests pass before marking the story done.

**Max 10 iterations.** Keep looping fix → QA → re-check as long as issues remain and `{fix_iteration}` < 10. No interim prompts. Only halt and ask `{user_name}` if `{fix_iteration}` ≥ 10 and issues still remain:
```
Sprint Orchestrator: HALT — Story {story_key} has reached the 10-iteration fix cap.
Remaining issues: {story_issues}
Options:
1. Provide additional context or constraints for the fix approach (continue with reset counter)
     Est: ~3–8 min × additional rounds, ~15–40K tokens per round
2. Accept and create a tech-debt follow-up story
     Est: ~2–5 min, ~10–25K tokens (single bmad-create-story call)
3. Redesign the approach for this story
     Est: ~20–35 min, ~100–200K tokens (full story prep + dev + review + QA cycle)
4. Skip this story and continue the sprint
     Est: 0 min, 0 tokens
```
Wait for decision before proceeding.

When all issues are resolved and QA passes: update status to `done` in `{status_file}`. Announce: "Story {story_key} — DONE after {fix_iteration} fix iteration(s)."

---

When all stories in `{sprint_stories}` are `done`, continue to `references/sprint-closure.md`.
