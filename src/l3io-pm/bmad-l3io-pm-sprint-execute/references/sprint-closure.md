# Sprint Closure

Communicate all responses in `{communication_language}`.

All stories are `done`. Execute the following closure phases in order. All outputs go to `{closure_output_dir}`.

**Orchestrator role:** Traffic controller. Hold only status-line summaries from subagents. Pass story file paths to subagents — never read story contents into context.

**Subagent invocation:** Agent tool preferred (self-contained prompt, no conversation history forwarded). Fallback: `claude --print`. Every subagent must end with: `DONE — [metrics] | BLOCKED: [reason] | FAILED: [reason]`

Build `{sprint_story_file_list}` — the paths of all story files for this sprint. Pass to subagents as paths only.

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

Check if `bmad-l3io-sec-agent-redteam` is installed (look for `.claude/commands/bmad-l3io-sec-agent-redteam.md` or equivalent). If absent: announce "bmad-l3io-sec-agent-redteam not installed — red-team phase skipped", record the skip in `{status_file}`, and continue to Step 7.

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

If no specs found, ask `{user_name}`:
1. SKIP UX review for this sprint (default)
2. Proceed with standard WCAG/usability review

If SKIP, continue to Step 8.

If specs found or standard review selected, spawn subagent:
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

If any Critical or High counts are non-zero, spawn a detail-read subagent to extract finding titles:
```
Read the closure review files in {closure_output_dir} created today.
List all Critical and High findings: [SEVERITY] [SOURCE] [Title] — [one-sentence description]
List Medium findings: title only.
Print the list. No other output.
```

Present the full findings list to `{user_name}` and ask for a resolution plan:
- **Critical/High:** MUST be resolved before sprint closes
- **Medium:** fix now OR create a backlog story (decide per item)
- **Low:** backlog or accept with rationale
- **Undocumented drift:** fix the code or update the architecture doc

For each "fix now" item:
1. Spawn fix subagent: invoke `bmad-dev-story` with the issue description and relevant file context
2. Spawn verification subagent: invoke `bmad-qa-generate-e2e-tests` targeting the fix
3. Confirm tests pass from the verification status line

For each "defer to backlog":
1. Spawn `bmad-create-story` to create a backlog story for the issue
2. Record the created story key in `{deferred_story_keys}`
3. Update `{status_file}` with the new story at `backlog`

If any Critical/High issues remain unresolved after all fix attempts, halt:
```
Sprint Orchestrator: HALT — {unresolved_count} Critical/High issue(s) remain unresolved.
Sprint cannot close until these are fixed or explicitly accepted.
Options:
1. Continue fixing (provide additional context or approach)
2. Accept risk — document rationale explicitly (requires acknowledgment)
3. Escalate to architect
```
Wait for `{user_name}` decision before proceeding.

---

## Step 10 — Sprint Sign-Off

Update `{status_file}`:
- All sprint stories: verified `done`
- Sprint retrospective: `done`
- Sprint closure comment with `{date}`

Record end timestamp: run `date +%s`, subtract `{sprint_start_ts}`, and bind `{actual_elapsed_min}` = round(elapsed seconds / 60).

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
  Deferred to backlog:  {deferred_story_keys}

  Est. time:            {est_time_low}–{est_time_high} min    Actual: ~{actual_elapsed_min} min
  Est. tokens:          {est_tokens_low}K–{est_tokens_high}K  Actual: not directly trackable
```

In headless mode (called by `bmad-l3io-pm-epic-execute`), emit instead:
```
DONE — Stories: {story_count}, Issues resolved: {total_resolved}, Issues deferred: {total_deferred}, Retro: {retro_file_path}, Time: ~{actual_elapsed_min}min (est {est_time_low}–{est_time_high}min)
```
