# Epic Closure

Communicate all responses in `{communication_language}`.

All sprints complete. Execute closure phases in the order below. All outputs go to `{epic_closure_dir}`.

**Orchestrator role:** Traffic controller. Hold only status-line summaries — never full file contents. Pass story file paths to subagents; build `{all_sprint_story_files}` (paths only) by listing all story files under `{epic_root_dir}/sprint-*/stories/`.

**Subagent invocation:** Agent tool preferred (self-contained prompt, no conversation history forwarded). Fallback: `claude --print`. Every subagent must end with: `DONE — [metrics] | BLOCKED: [reason] | FAILED: [reason]`

Announce: "All {total_sprint_count} sprint(s) complete. Beginning epic-level closure."

---

## Step 3 — Epic Retrospective

This step runs first and must complete before the parallel batch in Step 4.

Spawn subagent:
```
Load config from: {config_file}
Load project context from: {context_file} (if it exists)
Sprint status file: {status_file}
Target epic: {target_epic}
Sprint summaries (cross-sprint context): {sprint_summaries}
Invoke skill: bmad-retrospective
Execute a full epic-level retrospective for Epic {target_epic} — cross-sprint learnings, not just the last sprint.
Write to: {epic_closure_dir}/epic-{target_epic_padded}-retro-{date}.md
Print when done: DONE — Retro: [path], Action items: N | BLOCKED: [reason]
```

Record `{epic_retro_file}` and `{epic_retro_action_count}`. Surface any grave concerns directly to `{user_name}`.

Update epic retrospective to `done` in `{status_file}`.

---

## Step 4 — Parallel Closure Batch

Before launching the parallel batch, verify: no shared output file paths, no concurrent `{status_file}` writes, no unresolved blocker from Step 3. If any check is uncertain, run sequentially.

Spawn the following subagents in parallel (up to `effective_parallel_subagents` = min(`{max_parallel_subagents}`, 4)):

### 4a — Clean Release Review
```
Load config from: {config_file}
Load project context from: {context_file} (if it exists)
All story files for Epic {target_epic}: {all_sprint_story_files}
No skill to invoke — perform the following analysis directly:

CLEAN RELEASE REVIEW — Epic {target_epic} (full solution scope)

For each story across all sprints, read its acceptance criteria and File List. Assess across the full epic:
1. Does the implementation cover exactly what the stories specified, with no added scope?
2. Are there YAGNI violations — code or features not required by any acceptance criterion?
3. Are there premature abstractions, over-engineered solutions, or unnecessary complexity?
4. Are there simplification opportunities that would not reduce functionality?

Write to: {epic_closure_dir}/epic-{target_epic_padded}-clean-release-{date}.md
Print when done: DONE — Findings: N (Critical: N, High: N) | BLOCKED: [reason]
```

### 4b — Adversarial Review
```
Load config from: {config_file}
Load project context from: {context_file} (if it exists)
All story files for Epic {target_epic}: {all_sprint_story_files}
Epic retrospective: {epic_retro_file}
Invoke skill: bmad-review-adversarial-general
Content to review: all code changes across the entire epic (collect from story File List sections).
Review as a cohesive product increment — look for systemic issues only visible across all stories together: inter-story interactions, data flow across features, consistency of approach, patterns that only emerge at scale.
Also consider the epic retrospective at {epic_retro_file}.
Write to: {epic_closure_dir}/epic-{target_epic_padded}-adversarial-{date}.md
Print when done: DONE — Critical: N, High: N, Medium: N, Low: N | BLOCKED: [reason]
```

### 4c — Red-Team Review
Check if `l3io-sec-agent-redteam` is installed (look for `.claude/commands/l3io-sec-agent-redteam.md` or equivalent). If absent, skip 4c and record the skip.

If present:
```
Load config from: {config_file}
Load project context from: {context_file} (if it exists)
Architecture file: {arch_file} (load fully)
All story files for Epic {target_epic}: {all_sprint_story_files}
Epic retrospective: {epic_retro_file}
Invoke skill: l3io-sec-agent-redteam
Scope: epic
Epic artifact path: {epic_root_dir}
Focus on: (1) new attack surface introduced by the entire epic, (2) security properties spanning multiple stories — auth model, data ownership, trust boundaries, (3) failure modes that only emerge when all epic features interact.
Write to: {epic_closure_dir}/epic-{target_epic_padded}-redteam-{date}.md
Print when done: DONE — Critical: N, High: N, Medium: N, Low: N | BLOCKED: [reason]
```

### 4d — UX Review (conditional)
Search `{planning_artifacts}` for UX spec files matching `*ux*`, `*design*`, or similar (`{ux_specs_path}`). If none found, ask `{user_name}`: SKIP (default) or proceed with standard review. If SKIP, omit 4d.

If proceeding:
```
Load config from: {config_file}
Load project context from: {context_file} (if it exists)
All story files for Epic {target_epic}: {all_sprint_story_files}
[If specs found] UX specs: {ux_specs_path} (load fully)
Invoke skill: bmad-ux-review (or equivalent UX evaluation framework)
Scope: all user-facing changes across the entire epic.
[If specs found] Review against UX specs: all specified user flows and interactions, design patterns, accessibility, cross-feature consistency, deviations from spec.
[If no specs] Apply standard UX principles at epic scale: WCAG 2.1 AA, interaction consistency across all sprint stories, mobile responsiveness if applicable, error messaging consistency, cross-feature UX patterns.
Write to: {epic_closure_dir}/epic-{target_epic_padded}-ux-review-{date}.md
Print when done: DONE — Critical: N, High: N, Medium: N, Low: N | BLOCKED: [reason]
```

Wait for all parallel subagents in Step 4 to complete. Record severity counts from each status line:
- `{clr_critical}`, `{clr_high}` from clean release
- `{adv_critical}`, `{adv_high}`, `{adv_medium}` from adversarial
- `{rt_critical}`, `{rt_high}`, `{rt_medium}` from red team (0 if skipped)
- `{ux_critical}`, `{ux_high}`, `{ux_medium}` from UX (0 if skipped)

---

## Step 5 — Architecture Drift Analysis

Spawn subagent for inline solution-scoped drift analysis:
```
Load config from: {config_file}
Load project context from: {context_file} (if it exists)
Architecture specification: {arch_file} (load fully)
All story files for Epic {target_epic}: {all_sprint_story_files}
No skill to invoke — perform the following analysis directly:

ARCHITECTURE DRIFT ANALYSIS — Epic {target_epic} (full solution scope)

Compare the architecture specification against what was implemented across all sprints. Check five dimensions:
1. DATA MODEL DRIFT — specified entities, fields, types, relationships vs. source code
2. API CONTRACT DRIFT — specified endpoints, methods, request/response shapes vs. implemented routes
3. COMPONENT ARCHITECTURE DRIFT — specified module/service boundaries vs. actual file/module structure
4. NFR DRIFT — performance targets, security controls, observability requirements specified vs. implemented
5. TECHNOLOGY & PATTERN DRIFT — specified libraries, frameworks, patterns vs. actually used

Categorize each finding:
- INTENTIONAL: documented rationale in a story Dev Agent Record — acceptable
- UNDOCUMENTED: deviation with no documented rationale — this is an issue requiring fix or documentation
- SPEC GAP: spec was silent, implementation made a choice — flag for architecture doc update
- MISSING: specified but not yet implemented

Write to: {epic_closure_dir}/epic-{target_epic_padded}-arch-drift-{date}.md
Print when done: DONE — Undocumented: N, Missing: N, Spec gaps: N | BLOCKED: [reason]
```

Record `{drift_undoc}`, `{drift_missing}`, `{drift_gaps}`, `{drift_output_path}`.

---

## Step 6 — Functional Completeness Review

Spawn subagent for inline PRD coverage analysis:
```
Load config from: {config_file}
Load project context from: {context_file} (if it exists)
PRD file: {prd_file} (load fully)
Epics file: {epics_file} — load Epic {target_epic} section only
All story files for Epic {target_epic}: {all_sprint_story_files}
No skill to invoke — perform the following analysis directly:

FUNCTIONAL COMPLETENESS REVIEW — Epic {target_epic}

For each acceptance criterion in Epic {target_epic}:
- Identify which story implements it
- Check that story's Dev Agent Record confirms implementation
- Check that a test covers it
- Flag if: not in any story, story done but AC unverified, or no test coverage

For each user-facing feature described for Epic {target_epic} in the PRD:
- Identify implementing story/stories
- Verify story is done
- Check implementation matches described behavior
- Flag discrepancies

Check cross-cutting concerns specified at epic level in the PRD: consistent UX patterns, shared data model elements, error handling consistency.

Write to: {epic_closure_dir}/epic-{target_epic_padded}-functional-completeness-{date}.md
Print when done: DONE — ACs checked: N, Covered: N, Gaps: N, PRD discrepancies: N | BLOCKED: [reason]
```

Record `{func_ac_gaps}`, `{func_discrepancies}`, `{func_output_path}`.

---

## Step 7 — Issue Triage and Resolution

Summarize all closure findings from recorded status lines:
```
EPIC CLOSURE FINDINGS — Epic {target_epic}: {epic_title}
Clean Release:          Critical {clr_critical}, High {clr_high}
Adversarial:            Critical {adv_critical}, High {adv_high}, Medium {adv_medium}
Red Team:               Critical {rt_critical}, High {rt_high}, Medium {rt_medium}
UX Review:              Critical {ux_critical}, High {ux_high}, Medium {ux_medium}
Architecture Drift:     {drift_undoc} undocumented, {drift_missing} missing, {drift_gaps} spec gaps
Functional Completeness:{func_ac_gaps} AC gaps, {func_discrepancies} PRD discrepancies
```

If any Critical/High counts are non-zero, or `drift_undoc` > 0, or `func_ac_gaps` > 0, spawn a detail-read subagent:
```
Read the closure review files in {epic_closure_dir} created today.
List all Critical and High findings: [SEVERITY] [SOURCE] [Title] — [one-sentence description]
List Medium findings: title only.
List undocumented drift findings: title only.
List functional completeness gaps: AC or feature name.
Print the list. No other output.
```

Present the full findings list to `{user_name}` and ask for a resolution plan per item:
- **Critical/High:** MUST be resolved before epic closes
- **Undocumented drift:** fix the code OR update the architecture doc
- **Functional AC gaps:** implement the missing AC OR explicitly defer with documented rationale
- **Medium:** fix now OR create a backlog story
- **Low:** backlog or accept
- **Spec gaps:** update the architecture or PRD doc (no code change needed)

For each "fix now" item:
1. Spawn fix subagent: invoke `bmad-create-story` if a new story is needed; otherwise invoke `bmad-dev-story` with the issue context
2. Spawn verification subagent: invoke `bmad-qa-generate-e2e-tests` targeting the fix
3. Write verification evidence to: `{epic_test_dir}/epic-{target_epic_padded}-fix-verification-{date}.md`
4. Confirm tests pass from the verification status line

For each "doc update" (spec gaps, intentional drift documentation):
1. Spawn subagent to update the architecture or PRD document (store new files under `{planning_epic_dir}`)
2. Confirm from subagent status line

For each "defer to backlog":
1. Spawn `bmad-create-story` to create a backlog story
2. Record the story key in `{deferred_story_keys}`
3. Update `{status_file}` with the new story at `backlog`

If any Critical/High issues remain unresolved after all fix attempts, halt:
```
Epic Orchestrator: HALT — {unresolved_count} Critical/High issue(s) remain unresolved.
Epic cannot close. Options:
1. Continue fixing (provide additional context)
2. Accept risk — document rationale explicitly (requires acknowledgment)
3. Escalate to architect
4. Split remaining issues into a follow-on hardening epic
```
Wait for `{user_name}` decision.

---

## Step 8 — Epic Sign-Off

Update `{status_file}`:
- epic-`{target_epic}`: `done`
- All epic stories: verified `done`
- epic-`{target_epic}`-retrospective: `done`
- Closure comment with `{date}`

Record end timestamp: run `date +%s`, subtract `{epic_start_ts}`, and bind `{epic_actual_elapsed_min}` = round(elapsed seconds / 60).

Print:
```
Epic Orchestrator: Epic {target_epic} — {epic_title} — CLOSED — {date}

  Sprints executed:             {total_sprint_count}
  Stories delivered:            {total_story_count}
  Epic retrospective:           {epic_retro_file}
  Clean release critical/high:  resolved
  Adversarial critical/high:    resolved
  Red team critical/high:       resolved
  UX review critical/high:      resolved
  Architecture drift:           {drift_undoc} deviations fixed/documented, {drift_gaps} spec gaps documented
  Functional completeness:      {func_ac_gaps} gaps resolved
  Deferred to backlog:          {deferred_story_keys}

  Est. time:                    {epic_est_time_low}–{epic_est_time_high} min    Actual: ~{epic_actual_elapsed_min} min
  Est. tokens:                  {epic_est_tokens_low}K–{epic_est_tokens_high}K  Actual: not directly trackable
```
