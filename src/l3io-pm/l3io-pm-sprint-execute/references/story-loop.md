# Per-Story Execution Loop

Communicate all responses in `{communication_language}`.

Load `references/testing-guidelines.md` and keep its guidance in context for all development and QA phases.

Load `references/cicd-guidelines.md` and keep it in context. Apply it to any dev subagent whose story involves CI/CD pipelines, GitHub Actions workflows, Gitea CI, or deployment automation.

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

**Token/cost self-report (append to the DONE line).** So actuals survive nested runs (see `references/metrics-contract.md` → *Subagent self-report handoff*), append every dev/QA/fix subagent prompt with: `Before your final status line, capture this run's own token/cost per references/metrics-contract.md and append to DONE: "tokens_k=<n|N/A> cost=<$X.XX|N/A>".` The orchestrator reads these and, at story `done`, takes the **larger** of (its own per-story window scrape) and (the summed child self-reports) — a smaller value means rows were missed — then writes the story `actual` via `{status_script} set-actual --runtime {runtime}` (which fails loud on an `N/A` under Claude).

**Deferred cleanup:** When `{deferred_file_cleanup}` is `true`, append the following instruction to every subagent prompt you spawn:
```
DEFERRED CLEANUP ACTIVE: Do not execute rm commands directly. Instead, append each rm command as its own line to {cleanup_script} (create with #!/bin/bash header if it does not exist). Continue all other work normally.
```

**Adaptive parallelism:** Stories may run in parallel — across stories only, never across phases within the same story. Before each parallel batch compute `safe_batch_size`: the number of stories in the batch that pass **all** safety checks — no shared file-path overlap between them, no unresolved blocker that would invalidate siblings, and no concurrent write to the same `{status_active}` node (status writes go through `{status_script}`, which is atomic, so distinct-node writes across parallel stories are safe; same-node contention is not). If any check is uncertain for a story, it drops to the next (sequential) batch.

`effective_parallel_subagents` by `{parallel_mode}`:
- `auto` → `min({max_parallel_subagents}, {parallel_ceiling}, safe_batch_size)` — `safe_batch_size` governs; the orchestrator sizes the batch to the independent work available, capped only by `{parallel_ceiling}`.
- `adaptive` → `min({max_parallel_subagents}, {parallel_ceiling}, safe_batch_size)` as well, but do not exceed `{max_parallel_subagents}` even when more independent work exists (conservative).
- `off` → `1` (force sequential).

**Story ordering:** Before starting parallel execution, check story files or `{status_active}` for `depends_on` fields. A story cannot enter development until all declared dependencies are `done`. Process independent stories in parallel batches; dependent stories wait for their dependencies.

**Progress reporting:** Use ETA ranges (`~2-5 min`), not exact timestamps. Report position (`N/M`) and batch size for parallel runs. Refresh ETA after each completion.

**Status & progress contract (pm-status.py):** Every story-node status transition and every `actual`-block write in this loop goes through `{status_script}` (bound at activation — see SKILL.md → *Load the Status Helper*), which is atomic and round-trip-safe. At **each phase boundary** (prep→dev→review→qa→done, and every fix iteration) do two things: (1) transition the node with `{status_script} set-status … --ledger {progress_ledger}`, and (2) if the phase is long-running, the subagent also emits live `PROGRESS:` markers (below). This keeps `{status_active}` current at every step and leaves a tailable trail in `{progress_ledger}` that survives context compaction — the two failure modes this loop previously had (stale status, silent long phases). If `{status_script}` is absent/errors, fall back to a manual YAML edit per the schema — never skip the transition.

**Long-phase progress markers:** Every dev, QA, and fix subagent prompt below carries the instruction: `Emit a one-line "PROGRESS: <what> (<n>/<m>)" to stdout after each completed task/subtask/test file.` These stream back live so a multi-minute phase is never opaque.

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

The story's `classification` and four-metric `estimate` block were already written up front at the sprint **Pre-start Estimate** (per `references/metrics-contract.md` → *Applying calibration at estimate time* — `story.estimate[m] = base_band(class)[m] × scope_ratio(class, m) × fix_mult(class)`). **Read** them from the story node in `{status_active}` — do **not** recompute. Bind `{story_complexity}` = the node's `classification`, `{story_cost_range}` = `cost_low`–`cost_high` from its `estimate`, and `{story_title}` from the story file header.

**Fallback only if the node has no `estimate`/`classification`** (e.g. a story added after pre-start): classify from the AC count — Simple (1–3 ACs), Standard (4–6 ACs), Complex (7+ ACs) — compute the four-metric estimate via the metrics-contract formula above (HARD RULE — all four metrics), and write `classification` + the `estimate` block to the node now.

### 2a.1 — Technical Acceptance Criteria Gate

Bind `story_technical_ac_gate` at activation (default `"block"`). When `"off"`, skip this gate. Otherwise, before the story reaches `ready-for-dev`, ensure it carries **technical** acceptance criteria — not just functional ones — so implementation is not left to each dev agent's discretion (the recurring "stories lack technical ACs" gap).

Spawn a validation subagent:
```
Load config from: {config_file}
Load project context from: {context_file} (if it exists)
Story file: {story_file_path}
If l3io-arch-review is installed (.claude/skills/l3io-arch-review/SKILL.md or .claude/commands/l3io-arch-review.md): invoke it in review mode against this story and drive the checklist from its references/standards-core.md. Otherwise apply this built-in technical-AC checklist directly.
Verify the story's acceptance criteria specify, where applicable to what the story builds:
  - Interfaces / API contracts (signatures, request/response shapes, status/error codes)
  - Data model (entities, fields, types, persistence/migration expectations)
  - Error, edge-case, and failure/data-loss handling expectations
  - Observability (logging/metrics/tracing the story must emit)
  - Security controls (authz/authn, input validation at trust boundaries, secrets handling)
  - Testability / measurable NFRs (performance or resource targets, how acceptance is verified)
For each dimension that is applicable but unspecified, ADD a concrete technical acceptance criterion to the story file (edit in place; keep functional ACs intact). Do not invent scope beyond the story's intent — only make the implied technical contract explicit.
Print when done: DONE — technical ACs: present {list} / added {list} / n-a {list} | BLOCKED: [reason]
```

Parse the added/present/n-a lists from the status line. Then by `story_technical_ac_gate`:
- `"block"` — if any **applicable** dimension could not be specified (subagent reports it still missing, or BLOCKED), do **not** advance to `ready-for-dev`: report the gap to `{user_name}` and wait for input. Otherwise continue.
- `"warn"` — log any residual gaps as an informational warning and continue regardless.

Log the outcome to `{progress_ledger}` via `{status_script} progress`.

Announce story prep complete to `{user_name}` (informational, no confirmation requested): story title + acceptance criteria count + task count + complexity + cost estimate. Example: "Story {story_key} ready — {ac_count} ACs, {task_count} tasks · {story_complexity} · est. {story_cost_range}". Transition the story: `{status_script} set-status --file {status_active} --story {story_key} --status ready-for-dev --title "{story_title}" --ledger {progress_ledger} --scope {story_key}`. (Write `classification` + the `estimate` block separately only if they were just computed in the fallback — those are multi-field blocks, edit them per the schema.) Continue immediately to development.

---

## 2a.5 — ATDD (Acceptance Test Scaffolds)

Skip this section when either `{atdd_enabled}` is `false` or `bmad-testarch-atdd` is not installed — check `.claude/skills/bmad-testarch-atdd/SKILL.md` or `.claude/commands/bmad-testarch-atdd.md`; if neither path exists, skip silently.

Before spawning, check whether an `atdd-checklist-{story_key}.md` file already exists anywhere under `{test_output_dir}/`. If found, bind `{atdd_checklist_path}` to that path, announce: "ATDD scaffolds already present for {story_key} — reusing.", and proceed to 2b.

Otherwise, spawn a subagent:
```
Load config from: {config_file}
Load project context from: {context_file} (if it exists)
Story file: {story_file_path}
Invoke skill: bmad-testarch-atdd
Select Create mode immediately — do not pause to ask for mode selection.
All generated tests must be in failing (red) state — do not implement any production code.
Print when done: DONE — checklist:{absolute_path_to_checklist_file} | {N} test file(s) generated | SKIPPED: [reason] | BLOCKED: [reason]
```

On DONE: parse `{atdd_checklist_path}` from the `checklist:` field in the status line. Proceed to 2b with `{atdd_checklist_path}` set.
On SKIPPED (e.g. test framework not configured): log the reason, leave `{atdd_checklist_path}` unset, and continue to 2b.
On BLOCKED: report to `{user_name}` and wait for resolution before continuing.

---

## 2b — Development

Announce start. Record the story start timestamp: run `date +%s` and bind to `{story_start_ts}` (used to compute the story's compute-hours and token/cost actuals at done; OS-aware — on a PowerShell harness use `[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()`, see `references/metrics-contract.md` → Recording timestamps). Transition: `{status_script} set-status --file {status_active} --story {story_key} --status in-progress --ledger {progress_ledger} --scope {story_key}`.

Spawn subagent:
```
Load config from: {config_file}
Load project context from: {context_file} (if it exists)
Story file: {story_file_path}
ATDD scaffolds: {atdd_checklist_path} (omit this line when {atdd_checklist_path} is unset — acceptance tests were not generated for this story)
Invoke skill: bmad-dev-story
All tasks and subtasks must be checked [x] before finishing.
When ATDD scaffolds are present, treat them as the acceptance contract: implementation is complete only when those tests pass green.
Prefer the smallest solution that satisfies the acceptance criteria: skip unneeded abstractions, reach for the standard library and already-installed dependencies before adding new ones, and do not build speculative features. Validation at trust boundaries, error/data-loss handling, security, and accessibility are never simplified away.
When you take a deliberate shortcut, mark it with a one-line `bmad-defer:` comment so it can be harvested later: `<comment-leader> bmad-defer: <what was simplified>. ceiling: <the limit this assumes>. upgrade: <the trigger to revisit>.` Always name an upgrade trigger — a marker with none is flagged as silently rotting debt.
Update the story file Dev Agent Record and File List as the skill requires.
Emit a one-line "PROGRESS: <task> (<n>/<m>)" to stdout after each completed task/subtask so the orchestrator can surface live progress during this multi-minute phase.
Unit test guidance: {skill-root}/references/testing-guidelines.md — apply test quality review (coverage, relevance, parallelism) when writing or updating tests.
CI/CD guidance: {skill-root}/references/cicd-guidelines.md — apply if this story involves CI/CD pipelines, GitHub Actions, Gitea workflows, or deployment automation. Follow all conventions (modular design, dual triggers, action pinning, multi-runner compatibility, nektos/act local config).
Print when done: DONE | BLOCKED: [reason] | FAILED: [reason]
```

After completion, verify from `{story_file_path}`: all task checkboxes [x], Dev Agent Record populated, File List populated. Halt on failure — report to `{user_name}` and wait for guidance.

Transition: `{status_script} set-status --file {status_active} --story {story_key} --status review --ledger {progress_ledger} --scope {story_key}`.

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
Emit a one-line "PROGRESS: <test file> (<n>/<m>)" to stdout after each test file written or run so the orchestrator can surface live progress.
Test output caching: pipe all test runs through `tee /tmp/test-run-$(date +%Y%m%d-%H%M%S).log` so failure details are available without re-running. After analysis: if `{deferred_file_cleanup}` is `true`, append `rm /tmp/test-run-*.log` to `{cleanup_script}` (create with #!/bin/bash header if absent) — do not delete inline; otherwise delete the log immediately.
Unit test guidance: {skill-root}/references/testing-guidelines.md — apply test quality review (coverage, relevance, parallelism) when reviewing generated tests.
Write test results summary to the story file Dev Agent Record.
Write QA evidence to: {test_output_dir}/epic-{target_epic_padded}-sprint-{target_sprint_padded}-{story_key}-qa-{date}.md
Print when done: DONE — Tests: N written, N passing | FAILURES: N tests failing — [brief description] | BLOCKED: [reason]
```

If all tests pass: write the `completion_evidence` block to the story node (multi-field — edit per schema: `fix_iterations: {fix_iteration}`, `tests_passing: {tests_passing}` from the QA status line, `files_changed: {files_changed}` counted from the story File List via targeted read). Write the story `actual` block per **Story Actuals** below (via `{status_script} set-actual`). Then transition to done: `{status_script} set-status --file {status_active} --story {story_key} --status done --ledger {progress_ledger} --scope {story_key}`, and confirm it: `{status_script} verify --file {status_active} --scope story --story {story_key} --runtime {runtime}` (exit 4 → a required actual/evidence field is missing; fill it before continuing). Announce: "Story {story_key} — DONE." Move to the next story.

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
Emit a one-line "PROGRESS: <fix step>" to stdout at each meaningful step (diagnosis, patch, re-test) so the phase is not opaque.
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

When all issues are resolved and QA passes: write the `completion_evidence` block to the story node (multi-field — edit per schema: `fix_iterations: {fix_iteration}`, `tests_passing: {tests_passing}` from the final QA status line, `files_changed: {files_changed}` counted from the story File List, `bugs_fixed: [{one-line description per fix-loop iteration}]`). Write the story `actual` block per **Story Actuals** below (via `{status_script} set-actual`). Then transition to done and confirm: `{status_script} set-status --file {status_active} --story {story_key} --status done --ledger {progress_ledger} --scope {story_key}` followed by `{status_script} verify --file {status_active} --scope story --story {story_key} --runtime {runtime}`. Announce: "Story {story_key} — DONE after {fix_iteration} fix iteration(s)."

---

## Story Actuals (HARD RULE — written at `done`)

When a story reaches `done`, write its `actual` block to the story entry in `{status_active}` with all four metrics (see `references/metrics-contract.md`). Write it with the helper — under `--runtime claude` it **rejects** an `N/A` tokens/cost, enforcing the HARD RULE at write time:

```
{status_script} set-actual --file {status_active} --node story --story {story_key} \
  --elapsed-hours {elapsed_hours} --man-hours {man_hours} \
  --tokens-k {story_tokens_k} --cost '{story_cost}' --runtime {runtime} --ledger {progress_ledger}
```

Values (see `references/metrics-contract.md`):

- `elapsed_hours` = round((`date +%s` − `{story_start_ts}`) / 3600, 2) — measured compute (wall-clock) hours (OS-aware — on a PowerShell harness use `[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()` for the end timestamp; see `references/metrics-contract.md` → Recording timestamps).
- `man_hours` = `base × fix_factor`, where `base` = {simple: 6, standard: 18, complex: 36} by `classification`, and `fix_factor` = min(1.0 + `fix_iterations` × 0.25, 2.0). Round to 1 decimal.
- `tokens_k` and `cost`:
  - If `{runtime}` == `claude`: compute **exactly** using the token/cost capture procedure in `references/metrics-contract.md` with `{story_start_ts}` as the start (this story's transcript window). Bind `{story_tokens_k}` and `{story_cost}` (format `$X.XX`).
  - If `{runtime}` == `other`: read the runtime's usage source if one exists; otherwise write `tokens_k: N/A` and `cost: N/A` — **never guess.**

```yaml
actual:
  elapsed_hours: 0.4
  man_hours: 30
  tokens_k: 168        # or N/A under a non-Claude runtime with no usage source
  cost: '$1.10'        # or N/A when tokens_k is N/A
```

---

## Pre-Closure Story Verification

Before continuing to `references/sprint-closure.md`, run `{status_script} verify --file {status_active} --scope story --story {story_key} --runtime {runtime}` for every story in `{sprint_stories}` (exit `0` = all fields present and valid; exit `4` = a gap — the printed `FAIL` line names the missing/invalid field). The helper checks the same conditions listed below; the table remains the spec for what a pass means:

| Check | Expected |
|---|---|
| Every story `status` | `done` |
| Every story `actual.elapsed_hours` | numeric, non-null |
| Every story `actual.man_hours` | numeric, non-null |
| Every story `actual.tokens_k` | present (`N/A` is acceptable under non-Claude runtime; absence is not) |
| Every story `actual.cost` | present (`N/A` is acceptable under non-Claude runtime; absence is not) |
| Every story `completion_evidence` block | present |

If any story is not `done`: halt and report the story key and its current status to `{user_name}` — do not proceed to closure with incomplete work.

If a story's `actual` block is missing or a field is absent (not `N/A` — literally absent): re-write the missing fields now per `references/metrics-contract.md`. If a metric is genuinely unresolvable, write `N/A` — never omit the field.

Log the verification result:
```
Story verification — Epic {target_epic}, Sprint {target_sprint}: {story_count} stories done ✓ | WARN: [list any gaps corrected]
```

When all stories in `{sprint_stories}` are `done` and verified, continue to `references/sprint-closure.md`.
