# Sprint Closure

Communicate all responses in `{communication_language}`.

All stories are `done`. Execute the following closure phases in order. All outputs go to `{closure_output_dir}`.

**Orchestrator role:** Traffic controller. Hold only status-line summaries from subagents. Pass story file paths to subagents — never read story contents into context.

**Subagent invocation:** Agent tool preferred (self-contained prompt, no conversation history forwarded). Fallback: `claude --print`. Every subagent must end with: `DONE — [metrics] | BLOCKED: [reason] | FAILED: [reason]`

Build `{sprint_story_file_list}` — the paths of all story files for this sprint. Pass to subagents as paths only.

**Deferred cleanup:** When `{deferred_file_cleanup}` is `true`, append the following instruction to every subagent prompt you spawn:
```
DEFERRED CLEANUP ACTIVE: Do not execute rm commands directly. Instead, append each rm command as its own line to {cleanup_script} (create with #!/bin/bash header if it does not exist). Continue all other work normally.
```

---

## Step 3 — Retrospective

Spawn subagent:
```
Load config from: {config_file}
Load project context from: {context_file} (if it exists)
Sprint status file: {status_file}
Target epic: {target_epic}, Sprint: {target_sprint}
Invoke skill: bmad-retrospective
Execute the full sprint retrospective scoped to Epic {target_epic}, Sprint {target_sprint}.
Write to: {closure_output_dir}/epic-{target_epic_padded}-sprint-{target_sprint_padded}-retro-{date}.md
Print when done: DONE — Retro: [path], Action items: N | BLOCKED: [reason]
```

Record `{retro_file_path}` and `{retro_action_count}`. If the status line contains any grave concerns (critical blockers, significant risks), surface them directly to `{user_name}` — do not bury them in the report alone.

Update retro status to `done` in `{status_file}`.

---

## Step 4 — Clean Release Review

Spawn subagent to verify the sprint implemented exactly what was specified — no more, no less:
```
Load config from: {config_file}
Load project context from: {context_file} (if it exists)
Sprint story files: {sprint_story_file_list}
No skill to invoke — perform the following analysis directly:

CLEAN RELEASE REVIEW — Epic {target_epic}, Sprint {target_sprint}

For each story in this sprint, read its acceptance criteria and the File List of changed files. Assess:
1. Does the implementation cover exactly the acceptance criteria, with no added scope?
2. Are there YAGNI violations — code or features not required by any acceptance criterion?
3. Are there premature abstractions or unnecessary complexity beyond what the stories required?
4. Are there simplification opportunities that would not reduce functionality?

Write a findings report to: {closure_output_dir}/epic-{target_epic_padded}-sprint-{target_sprint_padded}-clean-release-{date}.md
Print when done: DONE — Findings: N (Critical: N, High: N, Medium: N) | BLOCKED: [reason]
```

Record `{clr_critical}` and `{clr_high}` from the status line.

---

## Step 5 — Adversarial Review

Spawn subagent:
```
Load config from: {config_file}
Load project context from: {context_file} (if it exists)
Sprint story files (read these to discover changed files): {sprint_story_file_list}
Retrospective: {retro_file_path}
Invoke skill: bmad-review-adversarial-general
Review all code changes across all sprint stories as a cohesive sprint increment — not story by story.
Also consider the retrospective at {retro_file_path}.
Write findings to: {closure_output_dir}/epic-{target_epic_padded}-sprint-{target_sprint_padded}-adversarial-{date}.md
Print when done: DONE — Critical: N, High: N, Medium: N, Low: N | BLOCKED: [reason]
```

Record `{adv_critical}`, `{adv_high}`, `{adv_medium}`, `{adv_low}`.

---

## Step 6 — Red-Team Review

Check if `bmad-l3io-sec-agent-redteam` is installed (look for `.claude/skills/bmad-l3io-sec-agent-redteam/SKILL.md` or `.claude/commands/bmad-l3io-sec-agent-redteam.md`). If absent: announce "bmad-l3io-sec-agent-redteam not installed — red-team phase skipped", record the skip in `{status_file}`, and continue to Step 7.

If present, spawn subagent:
```
Load config from: {config_file}
Load project context from: {context_file} (if it exists)
Sprint story files: {sprint_story_file_list}
Architecture file: {planning_artifacts}/*architecture*.md (load if it exists)
Invoke skill: bmad-l3io-sec-agent-redteam
Scope: sprint
Sprint artifact path: {sprint_root_dir}
Analyze all code changes introduced in this sprint (collect from story File List sections).
Focus on new attack surface introduced by this sprint's changes.
Write findings to: {closure_output_dir}/epic-{target_epic_padded}-sprint-{target_sprint_padded}-redteam-{date}.md
Print when done: DONE — Critical: N, High: N, Medium: N, Low: N | BLOCKED: [reason]
```

Record `{rt_critical}`, `{rt_high}`, `{rt_medium}`, `{rt_low}`.

---

## Step 7 — UX Review

Search `{planning_artifacts}` for UX spec files matching patterns `*ux*`, `*design*`, or similar (`{ux_specs_path}`).

If no specs found, auto-SKIP this step (no prompt). Announce to `{user_name}` (informational): "UX Review: skipped — no UX specs found under {planning_artifacts}." Continue to Step 8.

If specs found, spawn subagent:
```
Load config from: {config_file}
Load project context from: {context_file} (if it exists)
Sprint story files: {sprint_story_file_list}
[If specs found] UX specs: {ux_specs_path} (load fully)
Invoke skill: bmad-ux-review (or equivalent UX evaluation framework)
Scope: all user-facing changes introduced in this sprint (collect from story File List sections).
[If specs found] Review implementation against UX specifications: user flows, component behavior, accessibility, deviations from spec.
[If no specs] Apply standard UX principles: WCAG 2.1 AA, interaction consistency, usability, mobile responsiveness if applicable, error messaging.
Write findings to: {closure_output_dir}/epic-{target_epic_padded}-sprint-{target_sprint_padded}-ux-review-{date}.md
Print when done: DONE — Critical: N, High: N, Medium: N, Low: N | BLOCKED: [reason]
```

Record `{ux_critical}`, `{ux_high}`, `{ux_medium}`, `{ux_low}`.

---

## Step 8 — Light Architectural Drift Review

Spawn subagent for inline sprint-scoped drift analysis:
```
Load config from: {config_file}
Load project context from: {context_file} (if it exists)
Architecture specification: {planning_artifacts}/*architecture*.md (load fully if it exists; skip gracefully if absent)
Sprint story files: {sprint_story_file_list}
No skill to invoke — perform the following analysis directly:

LIGHT ARCHITECTURAL DRIFT REVIEW — Epic {target_epic}, Sprint {target_sprint}
Scope: only the changes introduced in this sprint (from story File List sections).

Compare the architecture specification against what was implemented in this sprint across five dimensions:
1. DATA MODEL DRIFT — specified entities, fields, types vs. code changes in this sprint
2. API CONTRACT DRIFT — specified endpoints, methods, request/response shapes vs. implemented routes
3. COMPONENT BOUNDARIES — specified module/service structure vs. actual structure of changed files
4. NFR DRIFT — performance, security, observability targets vs. what was implemented
5. TECHNOLOGY/PATTERNS — specified libraries, frameworks, patterns vs. actually used

Categorize each finding:
- INTENTIONAL: documented rationale in the story Dev Agent Record — acceptable
- UNDOCUMENTED: deviation with no documented rationale — this is an issue
- SPEC GAP: spec was silent, implementation made a choice — flag for doc update

Write findings to: {closure_output_dir}/epic-{target_epic_padded}-sprint-{target_sprint_padded}-arch-drift-{date}.md
Print when done: DONE — Undocumented: N, Spec gaps: N | BLOCKED: [reason]
```

Record `{drift_undoc}` and `{drift_gaps}`.

---

## Step 9 — Issue Triage

Summarize all closure findings from recorded status lines:
```
SPRINT CLOSURE FINDINGS — Epic {target_epic}, Sprint {target_sprint}
Clean Release:  Critical {clr_critical}, High {clr_high}
Adversarial:    Critical {adv_critical}, High {adv_high}, Medium {adv_medium}, Low {adv_low}
Red Team:       Critical {rt_critical}, High {rt_high}, Medium {rt_medium}, Low {rt_low}
UX Review:      Critical {ux_critical}, High {ux_high}, Medium {ux_medium}, Low {ux_low}
Arch Drift:     {drift_undoc} undocumented deviations, {drift_gaps} spec gaps
```

If any Critical, High, or Medium counts are non-zero, or `drift_undoc` > 0, spawn a detail-read subagent to extract finding titles:
```
Read the closure review files in {closure_output_dir} created today.
List all Critical, High, and Medium findings: [SEVERITY] [SOURCE] [Title] — [one-sentence description]
List Low findings: title only.
List undocumented drift findings: title only.
Print the list. No other output.
```

**Auto-classification (no per-finding prompt).** Bind `{fix_now_items}` and `{defer_items}` programmatically:
- Critical → `{fix_now_items}` (must resolve before sprint closes)
- High → `{fix_now_items}` (must resolve before sprint closes)
- Medium → `{fix_now_items}` (must resolve before sprint closes — same quality bar as Critical/High)
- Low → `{defer_items}` (create backlog story, do not fix this sprint)
- Undocumented drift → `{fix_now_items}` (fix code; if implementation is intentional, document rationale in the affected story's Dev Agent Record instead)

Announce the auto-classification to `{user_name}` (informational, no confirmation requested):
```
Sprint Orchestrator: Auto-triage — Fix now: {fix_now_count} (Critical {clr_critical+adv_critical+rt_critical+ux_critical}, High {clr_high+adv_high+rt_high+ux_high}, Medium {adv_medium+rt_medium+ux_medium}, Drift {drift_undoc}). Defer to backlog: {defer_count} (Low). No user decision needed unless the closure fix cap is hit.
```

### Closure Fix Loop

Maintain `{closure_fix_iteration}` = 0. Iterate the fix-and-verify cycle below until `{fix_now_items}` is empty OR `{closure_fix_iteration}` ≥ 10.

For each batch (per iteration):
1. For each item in `{fix_now_items}`:
   a. Spawn fix subagent: invoke `bmad-dev-story` with the issue description and relevant file context
   b. Spawn verification subagent: invoke `bmad-qa-generate-e2e-tests` targeting the fix
   c. If verification passes, remove from `{fix_now_items}`. If it fails, leave in the list for the next iteration.
2. Increment `{closure_fix_iteration}`.

For each item in `{defer_items}` (process once, not per iteration):
1. Spawn `bmad-create-story` to create a backlog story for the issue
2. Record the created story key in `{deferred_story_keys}`
3. Append to the epic's `backlog:` array in `{status_file}` (create the array under the epic node if absent):
   ```yaml
   - key: {new_story_key}
     title: {issue_title}
     source: {review_phase} ({finding_id})   # e.g. adversarial (ADV-L-01), red-team (RT-L-03), ux-review (UX-L02)
     severity: Low
     status: backlog
     description: {one-sentence description of the issue}
   ```

**Only halt and prompt `{user_name}` if `{closure_fix_iteration}` ≥ 10 and `{fix_now_items}` is non-empty:**
```
Sprint Orchestrator: HALT — Closure fix loop reached the 10-iteration cap.
Unresolved (Critical/High/Medium/Drift): {fix_now_items}
Sprint cannot close until these are fixed or explicitly accepted.
Options:
1. Continue fixing (provide additional context or approach; counter resets)
     Est: ~10–25 min per remaining item, ~50–100K tokens per item
2. Accept risk — defer remaining items to backlog with documented rationale
     Est: ~3–5 min per item, ~15–30K tokens per item (one bmad-create-story + rationale note per item)
3. Escalate to architect (pauses the sprint; sign-off blocked until decision is provided)
     Est: 0 min / 0 tokens here (cost is offline)
```
Wait for `{user_name}` decision before proceeding.

---

## Step 10 — Epic Backlog File

If any items were deferred to backlog during this sprint (`{deferred_story_keys}` is non-empty), append them to a consolidated per-epic backlog file:

```
{implementation_artifacts}/epic-{target_epic_padded}/epic-backlog.md
```

Format — append under a sprint heading (create the file if it does not exist):
```markdown
## Sprint {target_sprint} — {date}

| Story Key | Source | Severity | Title | Rationale |
|-----------|--------|----------|-------|-----------|
| {story_key} | adversarial | Medium | {title} | Auto-deferred after 10 fix iterations |
| {story_key} | red-team | Low | {title} | Auto-deferred |
```

This file accumulates across all sprints in the epic, making it the single place to review outstanding deferred work before epic closure.

---

## Step 11 — Sprint Sign-Off

### Deferred File Cleanup

If `{deferred_file_cleanup}` is `true` and `{cleanup_script}` exists with non-empty content:
Execute `bash {cleanup_script}` to process all deferred file deletions accumulated during this sprint in one batch.
On success, execute `rm {cleanup_script}`.
If `{cleanup_script}` does not exist or is empty, skip this step.

Record end timestamp: run `date +%s` (OS-aware — on a PowerShell harness use `[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()`; see `references/metrics-contract.md` → Recording timestamps), subtract `{sprint_start_ts}`, bind `{actual_elapsed_min}` = round(elapsed seconds / 60), then bind `{elapsed_hours}` = round(`{actual_elapsed_min}` / 60, 1).

Compute `{actual_man_hours}` from the completed sprint stories in `{status_file}` (targeted read of `classification` and `completion_evidence.fix_iterations` only):
- Base hours per classification: Simple = 6, Standard = 18, Complex = 36
- Per-story fix factor = min(1.0 + (`fix_iterations` × 0.25), 2.0)
- Per-story man-hours = base × fix_factor
- `{actual_man_hours}` = round(sum of per-story man-hours + 24, 1)   ← 24h = closure overhead (retro, arch review, QA pass, security)

**Token & cost actuals (HARD RULE — see `references/metrics-contract.md`):**
- If `{runtime}` == `claude`: compute **exactly** using the token/cost capture procedure with `{sprint_start_ts}` as the start (the whole-sprint transcript window, including closure subagents). Bind `{actual_tokens_k}` and `{actual_cost}` (format `$X.XX`).
- If `{runtime}` == `other`: read the runtime's usage source if one exists; otherwise bind `{actual_tokens_k}` = `N/A` and `{actual_cost}` = `N/A`. **Never guess.**

Update the sprint node in `{status_file}`:
- All sprint stories: verified `done`
- `closed: {date}`
- `retrospective: {retro_file_path}`
- `actual:` (all four metrics — required)
  - `elapsed_hours: {elapsed_hours}`
  - `man_hours: {actual_man_hours}`
  - `tokens_k: {actual_tokens_k}`
  - `cost: '{actual_cost}'`

In interactive mode, print:
```
Sprint Orchestrator: Sprint CLOSED — Epic {target_epic}, Sprint {target_sprint} — {date}

  Stories delivered:    {story_count}
  Retrospective:        {retro_file_path}
  Clean release:        {clr_critical+clr_high} critical/high resolved
  Adversarial:          {adv_critical+adv_high} critical/high resolved, {adv_medium} medium
  Red team:             {rt_critical+rt_high} critical/high resolved, {rt_medium} medium
  UX review:            {ux_critical+ux_high} critical/high resolved
  Arch drift:           {drift_undoc} undocumented deviations resolved, {drift_gaps} spec gaps documented
  Deferred to backlog:  {deferred_story_keys} → {implementation_artifacts}/epic-{target_epic_padded}/epic-backlog.md

  ── Planned vs Actual ──────────────────────────────────────────────────────────
  AI time:         planned {est_time_hours_low}–{est_time_hours_high} hours    actual ~{elapsed_hours} hours
  Tokens:          planned {est_tokens_low}K–{est_tokens_high}K                actual {actual_tokens_k}K
  Cost:            planned ~{est_cost_low}–{est_cost_high}                     actual {actual_cost}
  Traditional:     estimated ~{man_hours_low}–{man_hours_high} hours    actual ~{actual_man_hours} hours
  (Token/cost actuals are exact under Claude; shown as N/A under other runtimes — never estimated.)
```

In headless mode (called by `bmad-l3io-pm-epic-execute`), emit instead:
```
DONE — Stories: {story_count}, Issues resolved: {total_resolved}, Issues deferred: {total_deferred}, Retro: {retro_file_path}, Time: ~{actual_elapsed_min}min (planned {est_time_low}–{est_time_high}min), Tokens: {actual_tokens_k}K, Cost: {actual_cost} (planned ~{est_cost_low}–{est_cost_high})
```

---

## Step 12 — Calibration Update

Update the project-level calibration file so future sprint estimates learn from this sprint's plan-vs-actual delta.

**Compute sprint-level ratios** (read `estimate` and `actual` from the sprint node in `{status_file}`):
- `{cal_written_time_mid}` = (`estimate.time_hours_low` + `estimate.time_hours_high`) / 2
- `{cal_written_man_mid}` = (`estimate.man_hours_low` + `estimate.man_hours_high`) / 2
- `{cal_written_tokens_mid}` = (`estimate.tokens_k_min` + `estimate.tokens_k_max`) / 2
- `{cal_written_cost_mid}` = (`estimate.cost_low` + `estimate.cost_high`) / 2   (parse the `$X.XX` strings to numbers)
- `{sprint_time_ratio}` = round(`{elapsed_hours}` / `{cal_written_time_mid}`, 3) — skip if denominator is 0
- `{sprint_man_ratio}` = round(`{actual_man_hours}` / `{cal_written_man_mid}`, 3) — skip if denominator is 0
- `{sprint_token_ratio}` = round(`actual.tokens_k` / `{cal_written_tokens_mid}`, 3) — **skip if `actual.tokens_k` is `N/A`** or the denominator is 0 (never feed a guessed or N/A value into calibration)
- `{sprint_cost_ratio}` = round(`actual.cost` / `{cal_written_cost_mid}`, 3) — **skip if `actual.cost` is `N/A`** or the denominator is 0

**Compute per-classification man-hours ratios** (read `classification` and `completion_evidence.fix_iterations` from each story node in `{status_file}`; bases: simple=6, standard=18, complex=36):
- For each story: `fix_factor` = min(1.0 + `fix_iterations` × 0.25, 2.0); `story_ratio` = `fix_factor` (actual man-hours = base × fix_factor; predicted = base × 1.0)
- For each class c ∈ {simple, standard, complex}: `{class_ratio_c}` = round(avg(`story_ratio`) across done stories of class c, 3) — omit if no stories of that class

**Update history** — read `{project-root}/_bmad/pm-calibration.yaml` if it exists (create fresh if not). Append:
```yaml
- id: 'E{target_epic_padded}-S{target_sprint_padded}'
  date: '{date}'
  time_ratio: {sprint_time_ratio}
  man_hours_ratio: {sprint_man_ratio}
  token_ratio: {sprint_token_ratio}     # omit this key when actual.tokens_k was N/A
  cost_ratio: {sprint_cost_ratio}       # omit this key when actual.cost was N/A
  story_mix: { simple: {simple_count}, standard: {standard_count}, complex: {complex_count} }
  by_classification:                                    # omit class entry if count = 0
    simple:   { man_hours_ratio: {class_ratio_simple},   count: {simple_count} }
    standard: { man_hours_ratio: {class_ratio_standard}, count: {standard_count} }
    complex:  { man_hours_ratio: {class_ratio_complex},  count: {complex_count} }
```
Keep only the most recent 10 entries; discard older ones.

**Recompute weighted rolling averages** using exponential decay (decay = 0.8):
- For N entries ordered oldest→newest, assign weight[i] = 0.8^(N−1−i) so the most recent entry has weight = 1.0
- `{new_time_ratio}` = round(Σ(time_ratio[i] × weight[i]) / Σ(weight[i]), 3)
- `{new_man_hours_ratio}` = round(Σ(man_hours_ratio[i] × weight[i]) / Σ(weight[i]), 3)
- `{new_token_ratio}` = round(Σ(token_ratio[i] × weight[i]) / Σ(weight[i]), 3) — **over only the entries that have a `token_ratio`** (entries where it was N/A are excluded from both sums); leave at 1.0 if no entry has one
- `{new_cost_ratio}` = round(Σ(cost_ratio[i] × weight[i]) / Σ(weight[i]), 3) — same: only entries that carry a `cost_ratio`
- For each class c: `{new_class_ratio_c}` = round(Σ(by_classification.c.man_hours_ratio[i] × weight[i]) / Σ(weight[i] for entries where c.count > 0), 3); `{new_class_count_c}` = total story count across those entries

**Write** `{project-root}/_bmad/pm-calibration.yaml`:
```yaml
version: 1
last_updated: '{date}'
sprints_sampled: {history_count}
time_ratio: {new_time_ratio}           # weighted avg actual/estimate — applied to future time estimates
man_hours_ratio: {new_man_hours_ratio} # weighted avg actual/estimate — overall fallback for man-hours
token_ratio: {new_token_ratio}         # weighted avg actual/estimate — applied to future token estimates (Claude runs only)
cost_ratio: {new_cost_ratio}           # weighted avg actual/estimate — applied to future cost estimates (Claude runs only)
by_classification:                     # per-class man-hours ratios; used when sample_count >= 3
  simple:   { man_hours_ratio: {new_class_ratio_simple},   sample_count: {new_class_count_simple} }
  standard: { man_hours_ratio: {new_class_ratio_standard}, sample_count: {new_class_count_standard} }
  complex:  { man_hours_ratio: {new_class_ratio_complex},  sample_count: {new_class_count_complex} }
history:
  {history_entries}
```

If a ratio cannot be computed (zero denominator), leave that field at 1.0 and note the skip.
