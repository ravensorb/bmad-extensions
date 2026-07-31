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
Sprint status file: {status_active}
Target epic: {target_epic}, Sprint: {target_sprint}
Invoke skill: bmad-retrospective
Execute the full sprint retrospective scoped to Epic {target_epic}, Sprint {target_sprint}.
Write to: {closure_output_dir}/epic-{target_epic_padded}-sprint-{target_sprint_padded}-retro-{date}.md
Print when done: DONE — Retro: [path], Action items: N | BLOCKED: [reason]
```

Record `{retro_file_path}` and `{retro_action_count}`. If the status line contains any grave concerns (critical blockers, significant risks), surface them directly to `{user_name}` — do not bury them in the report alone.

Update retro status to `done` in `{status_active}`.

---

## Step 4 — Clean Release Review

Spawn subagent to verify the sprint implemented exactly what was specified — no more, no less — and to produce a concrete, line-level cut list:
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

Report each finding as a concrete, actionable cut — `{file}:{line} — {tag} {what to cut}. {leaner replacement}.` — using exactly one of these tags:
- delete — unused code, dead branches, or speculative features no acceptance criterion requires
- stdlib — a hand-rolled reimplementation of something the language standard library already provides
- native — a dependency or custom layer duplicating a platform/framework capability already available
- yagni — an abstraction (interface, factory, config knob, generic) with exactly one implementation/caller
- shrink — identical behavior achievable in materially fewer lines
NEVER flag as a cut: validation at trust boundaries, error/data-loss handling, security controls, accessibility, or anything an acceptance criterion explicitly requires — these are out of scope for this review even when they look heavy.
End the report with the total count of removable lines, or the single line "Lean already. Ship." if there are no cuts.
Assign severity by leanness impact: a whole speculative subsystem or new dependency that should not exist = High; a premature abstraction or duplicated-platform layer = Medium; a local shrink/tidy = Low.

Also scan the changed files for `bmad-defer:` shortcut markers — `<comment-leader> bmad-defer: <what>. ceiling: <limit>. upgrade: <trigger>.` Each marker is an intentional, recorded deferral, NOT a cut — do not flag the shortcut itself. List each as: DEFER {file}:{line} — {what} (upgrade: {trigger}, or NO-TRIGGER if none stated). These route to the backlog in triage, not to the fix loop.

Write a findings report to: {closure_output_dir}/epic-{target_epic_padded}-sprint-{target_sprint_padded}-clean-release-{date}.md
Print when done: DONE — Findings: N (Critical: N, High: N, Medium: N, Low: N), Removable lines: N, Defer markers: N | BLOCKED: [reason]
```

Record `{clr_critical}` and `{clr_high}` from the status line. Also record `{clr_defer_count}` (the `bmad-defer:` markers found): in Step 9 triage, route every deferral marker to `{defer_items}` (backlog), independent of severity — a recorded deferral is accepted debt, not a closure blocker.

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

Check if `l3io-sec-agent-redteam` is installed (look for `.claude/skills/l3io-sec-agent-redteam/SKILL.md` or `.claude/commands/l3io-sec-agent-redteam.md`). If absent: announce "l3io-sec-agent-redteam not installed — red-team phase skipped", record the skip in `{status_active}`, and continue to Step 7.

If present, spawn subagent:
```
Load config from: {config_file}
Load project context from: {context_file} (if it exists)
Sprint story files: {sprint_story_file_list}
Architecture file: {planning_artifacts}/*architecture*.md (load if it exists)
Invoke skill: l3io-sec-agent-redteam
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
- `bmad-defer:` markers ({clr_defer_count}) → `{defer_items}` (already-recorded, intentional debt — straight to backlog, never the fix loop, regardless of count)
- Undocumented drift → `{fix_now_items}` (fix code; if implementation is intentional, document rationale in the affected story's Dev Agent Record instead)

Announce the auto-classification to `{user_name}` (informational, no confirmation requested):
```
Sprint Orchestrator: Auto-triage — Fix now: {fix_now_count} (Critical {clr_critical+adv_critical+rt_critical+ux_critical}, High {clr_high+adv_high+rt_high+ux_high}, Medium {adv_medium+rt_medium+ux_medium}, Drift {drift_undoc}). Defer to backlog: {defer_count} (Low review findings: {low_count}, bmad-defer markers: {clr_defer_count}). No user decision needed unless the closure fix cap is hit.
```

### Closure Fix Loop

Maintain `{closure_fix_iteration}` = 0. Iterate the fix-and-verify cycle below until `{fix_now_items}` is empty OR `{closure_fix_iteration}` ≥ 10.

For each batch (per iteration):
1. For each item in `{fix_now_items}`:
   a. Spawn fix subagent: invoke `bmad-dev-story` with the issue description and relevant file context
   b. Spawn verification subagent: invoke `bmad-qa-generate-e2e-tests` targeting the fix
   c. If verification passes, remove from `{fix_now_items}`. If it fails, leave in the list for the next iteration.
2. Increment `{closure_fix_iteration}`.

**Post-loop: Defer processing (run once, after all fix iterations complete):**

For each **review-finding** item in `{defer_items}` (process once, not per iteration):
1. Spawn `bmad-create-story` to create a backlog story for the issue
2. Record the created story key in `{deferred_story_keys}`
3. Append to the consolidated `backlog:` list at the top level of `{status_backlog}` (create the list if absent), tagged with `epic`/`sprint` per `references/status-files.md`:
   ```yaml
   - key: {new_story_key}
     epic: '{target_epic_padded}'
     sprint: '{target_sprint_padded}'
     title: {issue_title}
     source: {review_phase} ({finding_id})   # e.g. adversarial (ADV-L-01), red-team (RT-L-03), ux-review (UX-L02)
     severity: Low
     status: backlog
     description: {one-sentence description of the issue}
   ```

For each **`bmad-defer:` marker** item in `{defer_items}` (process once): do **not** spawn `bmad-create-story` — a marker is already self-describing in code. Append directly to the same `backlog:` list, deduping by `{file}:{line}` so re-running closure never double-records a marker:
   ```yaml
   - key: {new_story_key}                  # next free DEBT-NN across the backlog
     epic: '{target_epic_padded}'
     sprint: '{target_sprint_padded}'
     title: {what}                         # the marker's first clause
     source: 'clean-release (code-marker {file}:{line})'
     severity: Low                         # Medium when the marker named NO upgrade trigger (rots silently)
     status: backlog
     description: '{what} (ceiling: {ceiling | none}; upgrade: {upgrade | NONE — no revisit trigger}).'
   ```
This is the inline, sprint-scoped twin of `l3io-util-cleanup harvest-debt` (which sweeps the whole tree on demand); both write the same backlog shape under the same dedupe key, so running either — or both — converges rather than duplicates.

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

Compute `{actual_man_hours}` from the completed sprint stories in `{status_active}` (targeted read of `classification` and `completion_evidence.fix_iterations` only):
- Base hours per classification: Simple = 6, Standard = 18, Complex = 36
- Per-story fix factor = min(1.0 + (`fix_iterations` × 0.25), 2.0)
- Per-story man-hours = base × fix_factor
- `{actual_man_hours}` = round(sum of per-story man-hours + 24, 1)   ← 24h = closure overhead (retro, arch review, QA pass, security)

**Token & cost actuals (HARD RULE — see `references/metrics-contract.md`):**
- If `{runtime}` == `claude`: compute **exactly** using the token/cost capture procedure with `{sprint_start_ts}` as the start (the whole-sprint transcript window, including closure subagents). Bind `{actual_tokens_k}` and `{actual_cost}` (format `$X.XX`).
- If `{runtime}` == `other`: read the runtime's usage source if one exists; otherwise bind `{actual_tokens_k}` = `N/A` and `{actual_cost}` = `N/A`. **Never guess.**

Update the sprint node in `{status_active}`:
- All sprint stories: verified `done`
- `closed: {date}` and `retrospective: {retro_file_path}` — multi-field, edit per schema
- `actual:` (all four metrics — required) — write via the helper, which rejects an `N/A` tokens/cost under `--runtime claude`:
  ```
  {status_script} set-actual --file {status_active} --node sprint --epic {target_epic_padded} --sprint {target_sprint_padded} \
    --elapsed-hours {elapsed_hours} --man-hours {actual_man_hours} \
    --tokens-k {actual_tokens_k} --cost '{actual_cost}' --runtime {runtime} --ledger {progress_ledger}
  ```
- Sprint status → done: `{status_script} set-status --file {status_active} --epic {target_epic_padded} --sprint {target_sprint_padded} --status done --ledger {progress_ledger} --scope E{target_epic_padded}/S{target_sprint_padded}`

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
  AI time:         planned {estimate.time_hours_low}–{estimate.time_hours_high} hours    actual ~{elapsed_hours} hours
  Tokens:          planned {estimate.tokens_k_min}K–{estimate.tokens_k_max}K              actual {actual_tokens_k}K
  Cost:            planned ~{estimate.cost_low}–{estimate.cost_high}                      actual {actual_cost}
  Traditional:     estimated ~{estimate.man_hours_low}–{estimate.man_hours_high} hours    actual ~{actual_man_hours} hours
  (Token/cost actuals are exact under Claude; shown as N/A under other runtimes — never estimated.)
```

In headless mode (called by `l3io-pm-epic-execute`), emit instead:
```
DONE — Stories: {story_count}, Issues resolved: {total_resolved}, Issues deferred: {total_deferred}, Retro: {retro_file_path}, Time: ~{elapsed_hours}h (planned {estimate.time_hours_low}–{estimate.time_hours_high}h), Tokens: {actual_tokens_k}K, Cost: {actual_cost} (planned ~{estimate.cost_low}–{estimate.cost_high})
```

### Post-Sign-Off Status Verification

After writing the sprint node, run `{status_script} verify --file {status_active} --scope sprint --epic {target_epic_padded} --sprint {target_sprint_padded} --runtime {runtime}` (exit `0` = the sprint `actual` block is complete and valid; exit `4` = the printed `FAIL` line names the gap). Then perform a targeted read of the sprint node and all its story nodes in `{status_active}` to confirm all fields are populated:

| Field | Expected |
|---|---|
| Sprint `status` | `done` |
| Sprint `closed` | non-empty date string |
| Sprint `actual.elapsed_hours` | numeric, non-null |
| Sprint `actual.man_hours` | numeric, non-null |
| Sprint `actual.tokens_k` | numeric or `N/A` — field must exist (not absent) |
| Sprint `actual.cost` | `$X.XX` or `N/A` — field must exist (not absent) |
| Every story `status` | `done` |
| Every story `actual` block | present with all 4 metrics |

If any sprint-level field is missing or null: re-write the corrected value before continuing. If a story `actual` block is missing: attempt to reconstruct from available data per `references/metrics-contract.md`; if unresolvable, write `N/A` for the missing metrics and log the gap explicitly — never leave a field absent.

Log the verification result:
```
Sprint sign-off verification — Epic {target_epic}, Sprint {target_sprint}: PASS | WARN [list any gaps corrected]
```

---

## Step 12 — Calibration Update (decomposed)

Update `{project-root}/_bmad/pm-calibration.yaml` so future estimates learn from this sprint. Calibration is **decomposed into `scope` / `closure` / `fix`** — `references/metrics-contract.md` → *Decomposed calibration*, *Emitting calibration samples at close (approach A)*, and *Rolling averages, retention, N/A, and migration* hold the authoritative formulas. This step binds the sprint-specific inputs and writes the file.

**Read** the sprint node's `estimate` + `actual`, and every done story node's `classification`, `completion_evidence.fix_iterations`, and `actual` block ({elapsed_hours, tokens_k, cost, man_hours}). If the file is `version: 1` (or has no `version`), migrate to v2 first (per metrics-contract → *migration*; preserve the original as `pm-calibration.yaml.v1`).

**Scope + fix samples (per done story, approach A).** For each story with class `c` and `fix_factor = min(1.0 + fix_iterations × 0.25, 2.0)`:
- `scope_actual.time = actual.elapsed_hours / fix_factor`; `scope_actual.tokens = actual.tokens_k / fix_factor`; `scope_actual.cost = parse(actual.cost) / fix_factor` — **skip any metric whose story actual is `N/A`**; `scope_actual.man_hours = base(c)` exactly, so its scope ratio sample = 1.0.
- `scope_ratio_sample(c, m) = scope_actual[m] / base_band_mid(c, m)` (base-band mids per metrics-contract).
- `fix_factor_sample(c) = fix_factor`.

**Closure sample (always, per sprint).** `closure_actual[m] = sprint.actual[m] − Σ story.actual[m]` for `m` ∈ {time, tokens, cost} (skip if any contributing actual is `N/A`); `man_hours` closure is the fixed +24 constant → `closure.sprint.man_hours_ratio` sample = 1.0. `closure_ratio_sample.sprint[m] = closure_actual[m] / closure_band_mid(sprint, m)`, using the **same** sprint-closure band the estimate used (include the red-team row when `l3io-sec-agent-redteam` is installed).

**Append history** per `{calibration_granularity}`:
- `"story"` → one entry per done story: `{ kind: story, id: '{story_key}', class: c, date: '{date}', scope: {time_ratio, token_ratio, cost_ratio, man_hours_ratio}, fix_factor }`; each increments `scope.c.sample_count`, `fix.c.sample_count`, and `stories_sampled`.
- `"sprint"` → average the per-class scope ratios and fix_factors across this sprint's done stories; emit one aggregated entry per touched class: `{ kind: sprint-scope, id: 'E{target_epic_padded}-S{target_sprint_padded}', class: c, date: '{date}', scope: {…}, fix_factor }`; each increments the relevant `sample_count`s and `sprints_sampled`.

Always also append the closure entry: `{ kind: sprint-closure, id: 'E{target_epic_padded}-S{target_sprint_padded}', date: '{date}', closure: {time_ratio, token_ratio, cost_ratio, man_hours_ratio} }`; increment `closure.sprint.sample_count`. Omit any ratio key whose metric was `N/A`/skipped.

**Recompute & write.** Keep the most recent **30** history entries; recompute every component ratio (and each `fix.c.avg_fix_factor`) as the decay-0.8 weighted mean over that component's entries, and each `sample_count` from the retained entries (all per metrics-contract → *Rolling averages*; a metric with no real sample keeps its prior of 1.0). Write the v2 file: `version: 2`, `last_updated: '{date}'`, `stories_sampled`, `sprints_sampled`, `epics_sampled` (carry through), and the `scope` / `closure` / `fix` / `history` blocks (schema in metrics-contract → *Decomposed calibration*).

If a ratio cannot be computed (zero denominator or `N/A`), leave that component at its prior (1.0) and note the skip.
