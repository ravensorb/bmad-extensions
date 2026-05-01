# Epic Execute Workflow

**Goal:** Orchestrate the complete execution of an epic — running sprint(s) for all stories, then applying epic-level retrospective, adversarial review, red team, architectural drift analysis, and functional completeness review. The epic does NOT close until all Critical and High issues from all closure phases are fully resolved.

**Your Role:** Epic Orchestrator — a lightweight traffic controller. You hold only epic/story keys, sprint groupings, and status summaries. All implementation work and all closure analysis is delegated to fresh subagents. You never accumulate implementation details, diff content, or story prose in your own context.

**Subagent delegation model:**
- Each sprint is delegated to a fresh `bmad-sprint-execute` subagent
- Each epic closure phase (retro, adversarial, red team, drift, completeness) is a fresh subagent
- State passes through disk only: story files, sprint-status.yaml, and review output documents
- After each subagent completes, you read disk state (status lines + targeted file reads) to determine next action

- Communicate all responses in {communication_language}
- Execute all steps in exact order; do NOT skip steps
- Do NOT set epic status to `done` until Step 8 completes with zero unresolved Critical/High issues

---

## INITIALIZATION

### Configuration Loading

Load config from `{project-root}/_bmad/bmm/config.yaml` and resolve:

- `project_name`, `user_name`
- `communication_language`, `document_output_language`
- `planning_artifacts`, `implementation_artifacts`
- `date` as system-generated current datetime

### Paths (hold as references, do NOT load file contents)

- `status_file` = `{implementation_artifacts}/sprint-status.yaml`
- `config_file` = `{project-root}/_bmad/bmm/config.yaml`
- `context_file` = `**/project-context.md`
- `arch_file` = `{planning_artifacts}/*architecture*.md`
- `prd_file` = `{planning_artifacts}/*prd*.md`
- `epics_file` = `{planning_artifacts}/*epic*.md`

> **Orchestrator memory rule:** Load config and skim status file for epic/story keys only. After planning, hold only keys, sprint groupings, status values, and printed status-line summaries from subagents. Do not load architecture, PRD, or story file contents into this context.

---

## SUBAGENT INVOCATION PATTERN

When this workflow says **"spawn subagent"**, use:

**Option A — Agent tool (preferred when available):**
Use the Agent tool with a self-contained prompt. Do NOT forward the current conversation history. Pass only paths and the skill name.

**Option B — Bash CLI:**
```bash
claude --print "$(cat <<'PROMPT'
[self-contained subagent prompt]
PROMPT
)"
```

All subagents must end their output with a structured status line:
```
DONE — [brief metrics]
BLOCKED: [reason]
FAILED: [reason]
```

After each subagent completes, read that status line and any targeted disk reads needed for routing. Do not read full file contents unless needed for triage.

---

## EXECUTION

<workflow>

<critical>You are a traffic controller. Hold only keys, sprint groupings, statuses, and status-line summaries.</critical>
<critical>Every unit of work — including each sprint and each closure phase — is a subagent with fresh context.</critical>
<critical>Execute ALL steps in exact order; do NOT skip steps</critical>
<critical>Do NOT set epic status to `done` until Step 8 completes with zero unresolved Critical/High issues</critical>

<step n="1" goal="Epic identification and sprint planning">

<action>Load {status_file} — extract epic and story keys with statuses only (not story content)</action>
<action>Skim {epics_file} headers only — extract story keys and titles, not full epic content</action>

<check if="user provided an epic number">
  <action>Set {{target_epic}} to the user-specified epic number</action>
</check>
<check if="no epic provided">
  <action>Find the first epic with `in-progress` or `backlog` status that has non-done stories</action>
  <action>Set {{target_epic}} from {status_file}</action>
  <action>Present to {user_name} for confirmation</action>
  <ask>Is this the correct epic to execute?</ask>
</check>

<action>Build the story key list for {{target_epic}} from {status_file} — keys and statuses only</action>
<action>Count: {{total_story_count}}, {{done_count}}, {{remaining_count}}</action>

<action>Propose sprint groupings:</action>
```
Epic {{target_epic}}: {{epic_title}}
Total stories:    {{total_story_count}}
Already done:     {{done_count}}
Remaining:        {{remaining_count}} — {{remaining_story_key_list}}

Default: all remaining stories as one sprint.
To split: provide story key groups (e.g. Sprint 1: 15-0, 15-1, 15-2 / Sprint 2: 15-3, 15-4)
```

<ask>Accept default single-sprint plan or provide groupings. Confirm before execution begins.</ask>

<action>Set {{sprint_plan}} = confirmed groupings</action>
<action>Set {{total_sprint_count}} = number of sprints</action>
<action>Update epic-{{target_epic}} to `in-progress` in {status_file}</action>

<output>
Epic Orchestrator: "Execution confirmed for Epic {{target_epic}} — {{epic_title}}.
{{total_sprint_count}} sprint(s), {{remaining_count}} stories.

Each sprint runs as a fresh bmad-sprint-execute subagent.
Epic closure (after all sprints): Retrospective → Adversarial → Red Team → Architecture Drift → Functional Completeness.
All phases are fresh subagents. State passes through disk only.

Beginning Sprint 1 of {{total_sprint_count}}."
</output>

</step>

<step n="2" goal="Sprint execution loop — one fresh subagent per sprint">

<action>For each sprint in {{sprint_plan}}, in order:</action>

<action>Announce: "Spawning sprint subagent {{current_sprint_num}} of {{total_sprint_count}} — stories: {{sprint_story_keys}}"</action>

<action>Spawn subagent with prompt:
```
Load config from: {config_file}
Load project context from: {context_file} (if exists)
Sprint status file: {status_file}
Target: Epic {{target_epic}}, stories: {{sprint_story_keys}}
Invoke skill: bmad-sprint-execute
Execute the complete sprint for the listed stories.
This includes per-story: create-story → dev → code-review → qa → fix loop
Then sprint closure: retrospective → adversarial review → red team → issue resolution.
All story phases must also use subagents per the bmad-sprint-execute subagent delegation model.
Write all results to disk per each skill's output conventions.
Update {status_file} as stories complete.
Print when done:
  DONE — Stories: N, Issues resolved: N, Issues deferred: N, Retro: [path]
  BLOCKED: [reason]
  FAILED: [reason]
```
</action>

<action>Wait for sprint subagent to complete</action>
<action>Read the status line — record {{sprint_stories_done}}, {{sprint_issues_resolved}}, {{sprint_issues_deferred}}, {{sprint_retro_path}}</action>

<check if="subagent reported BLOCKED or FAILED">
  <action>HALT and report the status line to {user_name}</action>
  <ask>Resolve the blocker before continuing to next sprint</ask>
</check>

<action>Announce: "Sprint {{current_sprint_num}} closed — {{sprint_stories_done}} stories delivered."</action>
<action>Append sprint result to {{sprint_summaries}}: sprint num + status-line metrics</action>

<check if="this is not the last sprint">
  <ask>Confirm: proceed to Sprint {{next_sprint_num}}, or pause to adjust remaining plan?</ask>
</check>

</step>

<step n="3" goal="Epic closure — Retrospective (subagent)">

<action>All sprints complete. Announce: "All {{total_sprint_count}} sprint(s) complete. Beginning epic-level closure."</action>
<action>Announce: "Spawning epic retrospective subagent."</action>

<action>Spawn subagent with prompt:
```
Load config from: {config_file}
Load project context from: {context_file} (if exists)
Sprint status file: {status_file}
Target epic: {{target_epic}}
Sprint summaries (for cross-sprint context): {{sprint_summaries}}
Invoke skill: bmad-retrospective
Execute a full epic-level retrospective for Epic {{target_epic}}.
Incorporate cross-sprint learnings — this covers the entire epic, not just the last sprint.
Write the retrospective document to the standard output path.
Print when done:
  DONE — Retro file: [path], Action items: N
  BLOCKED: [reason]
```
</action>

<action>Wait for subagent to complete</action>
<action>Read status line — record {{epic_retro_file}} and {{epic_retro_action_count}}</action>
<action>Update epic-{{target_epic}}-retrospective to `done` in {status_file}</action>

</step>

<step n="4" goal="Epic closure — Adversarial Review (subagent)">

<action>Announce: "Spawning epic adversarial review subagent — full epic scope."</action>
<action>Build {{all_sprint_story_files}}: the list of all story file paths for Epic {{target_epic}} (keys only, not contents)</action>

<action>Spawn subagent with prompt:
```
Load config from: {config_file}
Load project context from: {context_file} (if exists)
All story files for Epic {{target_epic}}: {{all_sprint_story_files}}
Epic retrospective: {{epic_retro_file}}
Invoke skill: bmad-review-adversarial-general
Content to review: all code changes across the entire epic.
  To find them: read the File List section from each story file listed above.
Also consider: "Epic retrospective at {{epic_retro_file}}. Review the entire epic as a cohesive product increment — look for systemic issues only visible across all stories together: inter-story interactions, data flow across features, consistency of approach, patterns that only emerge at scale."
Execute the full adversarial review. Write findings to an output document.
Print when done:
  DONE — Critical: N, High: N, Medium: N, Low: N, Output: [path]
  BLOCKED: [reason]
```
</action>

<action>Wait for subagent to complete</action>
<action>Read status line — record {{adv_critical}}, {{adv_high}}, {{adv_medium}}, {{adv_output_path}}</action>

</step>

<step n="5" goal="Epic closure — Red Team (subagent)">

<action>Announce: "Spawning epic red team subagent — full epic scope."</action>

<action>Spawn subagent with prompt:
```
Load config from: {config_file}
Load project context from: {context_file} (if exists)
Architecture file: {arch_file} (load fully)
All story files for Epic {{target_epic}}: {{all_sprint_story_files}}
Epic retrospective: {{epic_retro_file}}
Invoke skill: bmad-red-team
Scope: all code changes across the entire epic (collect from story file File List sections).
Context: architecture document above, epic retrospective.
Focus on: (1) new attack surface introduced by the entire epic, (2) security properties spanning multiple stories (auth model, data ownership, trust boundaries), (3) failure modes that only emerge when all epic features interact.
Write findings to an output document.
Print when done:
  DONE — Critical: N, High: N, Medium: N, Low: N, Output: [path]
  BLOCKED: [reason]
```
</action>

<action>Wait for subagent to complete</action>
<action>Read status line — record {{rt_critical}}, {{rt_high}}, {{rt_medium}}, {{rt_output_path}}</action>

</step>

<step n="6" goal="Epic closure — Architecture Drift Analysis (subagent)">

<action>Announce: "Spawning architecture drift subagent — implementation vs. specification."</action>

<action>Spawn subagent with prompt:
```
Load config from: {config_file}
Load project context from: {context_file} (if exists)
Architecture specification: {arch_file} (load fully)
All story files for Epic {{target_epic}}: {{all_sprint_story_files}}
No skill to invoke — perform the following analysis directly:

ARCHITECTURE DRIFT ANALYSIS for Epic {{target_epic}}

Compare what was specified in the architecture against what was implemented. Check each dimension:

1. DATA MODEL DRIFT — specified entities, fields, types, relationships vs. source code
2. API CONTRACT DRIFT — specified endpoints, methods, request/response shapes vs. implemented routes
3. COMPONENT ARCHITECTURE DRIFT — specified boundaries vs. actual file/module structure
4. NFR DRIFT — performance targets, security controls, observability requirements specified vs. implemented
5. TECHNOLOGY & PATTERN DRIFT — specified libraries, frameworks, patterns vs. actually used

For each finding, categorize as:
  - INTENTIONAL: documented in a story Dev Agent Record as justified — acceptable
  - UNDOCUMENTED: deviation with no documented rationale — this is an issue
  - SPEC GAP: spec was silent, implementation made a choice — flag for doc update
  - MISSING: specified but not yet implemented

Write a structured findings report to {implementation_artifacts}/epic-{{target_epic}}-arch-drift-{{date}}.md
Print when done:
  DONE — Undocumented deviations: N, Missing implementations: N, Spec gaps: N, Output: [path]
  BLOCKED: [reason]
```
</action>

<action>Wait for subagent to complete</action>
<action>Read status line — record {{drift_undoc}}, {{drift_missing}}, {{drift_gaps}}, {{drift_output_path}}</action>

</step>

<step n="7" goal="Epic closure — Functional Completeness Review (subagent)">

<action>Announce: "Spawning functional completeness subagent — PRD vs. implementation."</action>

<action>Spawn subagent with prompt:
```
Load config from: {config_file}
Load project context from: {context_file} (if exists)
PRD file: {prd_file} (load fully)
Epics file: {epics_file} — load Epic {{target_epic}} section only
All story files for Epic {{target_epic}}: {{all_sprint_story_files}}
No skill to invoke — perform the following analysis directly:

FUNCTIONAL COMPLETENESS REVIEW for Epic {{target_epic}}

For each acceptance criterion in Epic {{target_epic}}:
  - Identify which story implements it
  - Check that story's Dev Agent Record confirms implementation
  - Check that a test covers it
  - Flag if: not in any story, story done but AC unverified, or no test coverage

For each user-facing feature described for Epic {{target_epic}} in the PRD:
  - Identify implementing story/stories
  - Verify story is done
  - Check implementation matches described behavior
  - Flag discrepancies

Check cross-cutting concerns specified at epic level in the PRD (consistent UX patterns, shared data model elements, error handling).

Write a structured findings report to {implementation_artifacts}/epic-{{target_epic}}-functional-completeness-{{date}}.md
Print when done:
  DONE — ACs checked: N, Covered: N, Gaps: N, PRD discrepancies: N, Output: [path]
  BLOCKED: [reason]
```
</action>

<action>Wait for subagent to complete</action>
<action>Read status line — record {{func_ac_gaps}}, {{func_discrepancies}}, {{func_output_path}}</action>

</step>

<step n="8" goal="Epic closure — Issue triage and resolution">

<action>Summarize all closure findings from recorded status lines:</action>

```
EPIC CLOSURE FINDINGS — Epic {{target_epic}}: {{epic_title}}
============================================================
Adversarial review:         Critical {{adv_critical}}, High {{adv_high}}, Medium {{adv_medium}}
Red team:                   Critical {{rt_critical}}, High {{rt_high}}, Medium {{rt_medium}}
Architecture drift:         {{drift_undoc}} undocumented deviations, {{drift_missing}} missing implementations
Functional completeness:    {{func_ac_gaps}} AC gaps, {{func_discrepancies}} PRD discrepancies
```

<check if="any Critical or High counts are non-zero OR drift_undoc > 0 OR func_ac_gaps > 0">
  <action>Spawn a detail-read subagent to extract finding titles for triage:</action>
  <action>Spawn subagent with prompt:
```
Read these review output documents and extract all findings with severity Critical, High, or equivalent:
  Adversarial review: {{adv_output_path}}
  Red team: {{rt_output_path}}
  Architecture drift: {{drift_output_path}}
  Functional completeness: {{func_output_path}}
For each finding print: [SEVERITY] [SOURCE] [Title] — [one-sentence description]
Also list all Medium findings with title only.
```
  </action>
  <action>Wait for subagent to complete</action>
  <action>Present the full findings list to {user_name}</action>
</check>

<ask>Confirm resolution plan:
- Critical and High: MUST be resolved before epic closes
- Undocumented drift: must be fixed (code) or documented (architecture doc update)
- Functional AC gaps: must be implemented or explicitly deferred with rationale
- Medium: fix now OR create a backlog story (decide per item)
- Low: create backlog story or accept with documented rationale
- Spec gaps: update architecture/PRD doc (no code change needed)

Indicate your plan for each item.</ask>

<action>For each issue marked "fix now":</action>
  1. Announce: "Spawning fix subagent: {{issue_title}}"
  2. Spawn subagent: invoke `bmad-create-story` if a new story is needed, else invoke `bmad-dev-story` directly with fix context
  3. Spawn verification subagent: invoke `bmad-qa-generate-e2e-tests`
  4. Read verification status line — confirm tests pass

<action>For each "doc update" (spec gaps, intentional drift documentation):</action>
  1. Spawn subagent to update the relevant architecture or PRD document
  2. Read confirmation from subagent status line

<action>For each "defer / backlog":</action>
  1. Spawn subagent: invoke `bmad-create-story` to create a backlog story
  2. Read created story key from output
  3. Add key to {{deferred_story_keys}}
  4. Update {status_file} with new story at `backlog`

<check if="any Critical or High issues remain unresolved after all fix attempts">
  <action>HALT — epic cannot close</action>
  <output>
Epic Orchestrator: "HALT — {{unresolved_count}} Critical/High issue(s) remain. Epic cannot close until resolved or explicitly accepted.

Options:
1. Continue fixing (provide additional context)
2. Accept risk — document rationale explicitly (requires acknowledgment)
3. Escalate specific issues to architect
4. Split remaining issues into a follow-on hardening epic"
  </output>
  <ask>Wait for {user_name} decision</ask>
</check>

</step>

<step n="9" goal="Epic sign-off and final report">

<action>Update {status_file}:
- epic-{{target_epic}}: `done`
- epic-{{target_epic}}-retrospective: `done`
- All epic stories: verify `done`
- Add closure comment with date</action>

<output>
Epic Orchestrator: "Epic {{target_epic}} — {{epic_title}} — CLOSED — {{date}}

  Sprints executed:           {{total_sprint_count}}
  Stories delivered:          {{total_story_count}}
  Epic retrospective:         {{epic_retro_file}}
  Adversarial critical/high:  resolved
  Red team critical/high:     resolved
  Architecture drift:         {{drift_undoc}} deviations fixed/documented
  Functional completeness:    {{func_ac_gaps}} gaps resolved
  Deferred to backlog:        {{deferred_story_keys}}
"
</output>

</step>

</workflow>

---

## Orchestrator State (what the orchestrator holds — nothing else)

| Variable | Type | Description |
|----------|------|-------------|
| `{{target_epic}}` | string | Epic number being executed |
| `{{sprint_plan}}` | list of key-groups | Sprint groupings confirmed by user |
| `{{sprint_summaries}}` | list of status lines | One status-line summary per completed sprint |
| `{{all_sprint_story_files}}` | list of paths | Story file paths (not contents) |
| `{{epic_retro_file}}` | string | Path written by retro subagent |
| `{{adv_critical/high/medium}}` | int | Counts from adversarial review status line |
| `{{rt_critical/high/medium}}` | int | Counts from red team status line |
| `{{drift_undoc/missing/gaps}}` | int | Counts from drift analysis status line |
| `{{func_ac_gaps/discrepancies}}` | int | Counts from completeness status line |
| `{{deferred_story_keys}}` | list | Backlog stories created during closure |

## Disk handoff contract

| Phase | Subagent writes | Orchestrator reads |
|-------|-----------------|-------------------|
| Each sprint | Story files, sprint-status.yaml updates, sprint retro + review docs | Printed status line (stories done, issues counts) |
| Epic retro | Retrospective document | Printed path + action count |
| Adversarial | Review findings document | Printed severity counts + output path |
| Red team | Red team findings document | Printed severity counts + output path |
| Arch drift | `epic-N-arch-drift-DATE.md` | Printed deviation counts + output path |
| Func completeness | `epic-N-functional-completeness-DATE.md` | Printed gap counts + output path |
| Fix subagents | Story files, updated source code | Printed DONE/FAILED + QA verification status |
| Doc updates | Architecture/PRD documents | Printed DONE confirmation |

## Sub-Skills Delegated to Subagents

| Phase | Skill / Task |
|-------|-------------|
| Each sprint | `bmad-sprint-execute` (which itself delegates all story phases to subagents) |
| Epic retrospective | `bmad-retrospective` |
| Epic adversarial review | `bmad-review-adversarial-general` |
| Epic red team | `bmad-red-team` |
| Architecture drift | Direct analysis (no skill wrapper — subagent performs inline) |
| Functional completeness | Direct analysis (no skill wrapper — subagent performs inline) |
| Fix implementation | `bmad-create-story` + `bmad-dev-story` |
| Fix verification | `bmad-qa-generate-e2e-tests` |
