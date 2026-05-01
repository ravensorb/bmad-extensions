# Sprint Execute Workflow

**Goal:** Orchestrate a complete sprint execution cycle — story preparation, development, QA, and defect fixing per story; followed by sprint-level retrospective, adversarial review, and red team. The sprint does NOT close until all Critical and High issues from the closure phase are resolved.

**Your Role:** Sprint Orchestrator — a lightweight traffic controller. You hold only story keys, statuses, and issue summaries. All implementation work is delegated to fresh subagents. You never accumulate story implementation details in your own context.

**Subagent delegation model:**
- Each story phase (create, dev, code-review, qa, fix) spawns a fresh Claude subagent
- Subagents receive only: the skill to invoke + the relevant file paths
- State is passed through disk only: story files and sprint-status.yaml
- After each subagent completes, you read disk state to determine next action
- Closure phase reviews (retro, adversarial, red team) are also subagents

- Communicate all responses in {communication_language}
- Execute all steps in exact order; do NOT skip steps
- Do NOT mark the sprint closed until Step 6 completes with zero unresolved Critical/High issues

---

## INITIALIZATION

### Configuration Loading

Load config from `{project-root}/_bmad/bmm/config.yaml` and resolve:

- `project_name`, `user_name`
- `communication_language`, `document_output_language`
- `planning_artifacts`, `implementation_artifacts`
- `date` as system-generated current datetime

### Paths

- `status_file` = `{implementation_artifacts}/sprint-status.yaml`
- `config_file` = `{project-root}/_bmad/bmm/config.yaml`
- `context_file` = `**/project-context.md` (path only — do NOT load contents)

> **Orchestrator memory rule:** Load config and status file to build the sprint plan. After that, hold only story keys and status values — not file contents, implementation details, or test output. Let disk be the memory.

---

## SUBAGENT INVOCATION PATTERN

When this workflow says **"spawn subagent"**, use the following approach:

**Option A — Agent tool (preferred when available):**
Use the Agent tool with a self-contained prompt. Do NOT forward the current conversation history. Pass only paths and the skill name.

**Option B — Bash CLI:**
```bash
claude --print "$(cat <<'PROMPT'
[self-contained subagent prompt]
PROMPT
)"
```

**Subagent prompt template:**
```
Load config from: {config_file}
Load project context from: {context_file} (if it exists)
[Story file path if applicable]
Invoke skill: [skill-name]
[Any additional targeting: epic num, story num, scope, etc.]
Execute completely. Write all results to disk per the skill's output conventions.
When done, print a one-line status: DONE | BLOCKED: [reason] | FAILED: [reason]
```

**After the subagent completes:**
- Read the relevant story file or status file from disk
- Check the status line the subagent printed
- Decide next action based only on what you read from disk

---

## EXECUTION

<workflow>

<critical>You are a traffic controller. Hold only story keys and statuses. Never accumulate implementation details.</critical>
<critical>Every unit of work is a subagent. You read results from disk, not from conversation history.</critical>
<critical>Execute ALL steps in exact order; do NOT skip steps</critical>
<critical>Do NOT close the sprint until Step 6 completes with zero unresolved Critical/High issues</critical>

<step n="1" goal="Sprint scope identification">

<action>Load {status_file} — extract story keys and statuses only</action>
<action>Load epic file headers only — extract story keys and titles, not full story content</action>

<check if="user provided an epic number or story range">
  <action>Set {{sprint_stories}} = user-specified story keys</action>
</check>
<check if="no scope provided">
  <action>Find the first epic with `in-progress` status, or the first epic with backlog stories</action>
  <action>Set {{target_epic}} and {{sprint_stories}} from that epic's non-done stories</action>
</check>

<action>Remove any stories already at `done` from {{sprint_stories}}</action>
<action>Build ordered execution list (preserve order from {status_file})</action>

<output>
Sprint Orchestrator: "Sprint scope identified — Epic {{target_epic}}, {{story_count}} stories:

{{story_key_list_with_current_status}}

I'll delegate each story phase to a fresh subagent. State passes through disk only.
Execution per story: Story Prep → Dev → Code Review → QA → Fix Loop
Sprint closure: Retrospective → Adversarial Review → Red Team → Issue Resolution

Shall I begin?"
</output>

<ask>Wait for {user_name} to confirm</ask>

</step>

<step n="2" goal="Per-story execution loop">

<action>For each story key in {{sprint_stories}}, in order:</action>

---

**Step 2a — Story Preparation (subagent)**

<action>Check: does `{implementation_artifacts}/{{story_key}}.md` exist on disk?</action>

<check if="story file does NOT exist">
  <action>Announce: "Spawning story prep subagent for {{story_key}}"</action>
  <action>Spawn subagent with prompt:
```
Load config from: {config_file}
Load project context from: {context_file} (if exists)
Invoke skill: bmad-create-story
Target: Epic {{target_epic}}, Story {{story_num}}
Execute completely. Write the story file to {implementation_artifacts}/{{story_key}}.md
Print status when done: DONE | BLOCKED: [reason]
```
  </action>
  <action>Wait for subagent to complete</action>
  <action>Read {implementation_artifacts}/{{story_key}}.md — verify it was created</action>
  <check if="story file was not created or subagent reported BLOCKED">
    <action>HALT and report to {user_name} with the subagent's status output</action>
    <ask>Resolve the blocker before continuing</ask>
  </check>
</check>

<check if="story file already exists">
  <action>Read only the Status and section headers from the story file to verify it is complete</action>
</check>

<action>Present story summary to {user_name}: title + acceptance criteria count + task count (from file headers only)</action>
<ask>Confirm story is ready for development. You may request changes before proceeding.</ask>
<action>Update story status to `ready-for-dev` in {status_file}</action>

---

**Step 2b — Development (subagent)**

<action>Announce: "Spawning dev subagent for {{story_key}}"</action>
<action>Update story status to `in-progress` in {status_file}</action>

<action>Spawn subagent with prompt:
```
Load config from: {config_file}
Load project context from: {context_file} (if exists)
Story file: {implementation_artifacts}/{{story_key}}.md
Invoke skill: bmad-dev-story
Execute completely — all tasks and subtasks must be checked [x] before finishing.
Update the story file Dev Agent Record and File List as the skill requires.
Print status when done: DONE | BLOCKED: [reason] | FAILED: [reason]
```
</action>

<action>Wait for subagent to complete</action>
<action>Read story file — check: are all task checkboxes [x]? Is Dev Agent Record populated? Is File List populated?</action>

<check if="dev subagent reported BLOCKED or FAILED, or tasks are not all checked">
  <action>HALT and report to {user_name} with details read from the story file</action>
  <ask>Provide guidance before retrying</ask>
</check>

<action>Update story status to `review` in {status_file}</action>

---

**Step 2c — Code Review (subagent)**

<action>Announce: "Spawning code review subagent for {{story_key}}"</action>
<action>Read File List section from story file — extract the list of changed files as {{changed_files}}</action>

<action>Spawn subagent with prompt:
```
Load config from: {config_file}
Load project context from: {context_file} (if exists)
Story file: {implementation_artifacts}/{{story_key}}.md
Changed files: {{changed_files}}
Invoke skill: bmad-code-review
Target: the files listed above as changed by this story.
Execute the full review. Write findings to the story file Dev Agent Record section.
Print a brief summary when done:
  DONE — Critical: N, High: N, Medium: N, Low: N
  BLOCKED: [reason]
```
</action>

<action>Wait for subagent to complete</action>
<action>Read the status line printed by the subagent. Note Critical and High counts as {{cr_critical}} and {{cr_high}}</action>

<check if="{{cr_critical}} > 0 OR {{cr_high}} > 0">
  <action>Add to {{story_issues}}: "Code review: {{cr_critical}} Critical, {{cr_high}} High — see story Dev Agent Record"</action>
  <action>Announce: "Code review found Critical/High issues — will fix before QA"</action>
  <goto anchor="step-2e-fix" />
</check>

---

**Step 2d — QA / Test Coverage (subagent)**

<action>Announce: "Spawning QA subagent for {{story_key}}"</action>

<action>Spawn subagent with prompt:
```
Load config from: {config_file}
Load project context from: {context_file} (if exists)
Story file: {implementation_artifacts}/{{story_key}}.md
Invoke skill: bmad-qa-generate-e2e-tests
Target: the feature implemented in this story.
Run all generated tests and verify they pass before finishing.
Write test results summary to the story file Dev Agent Record section.
Print status when done:
  DONE — Tests: N written, N passing
  FAILURES: N tests failing — [brief description]
  BLOCKED: [reason]
```
</action>

<action>Wait for subagent to complete</action>
<action>Read the status line. Note pass/fail counts.</action>

<check if="subagent reported FAILURES">
  <action>Add to {{story_issues}}: "QA: test failures — see story Dev Agent Record for details"</action>
  <goto anchor="step-2e-fix" />
</check>

<check if="subagent reported DONE with all tests passing">
  <action>Update story status to `done` in {status_file}</action>
  <action>Announce: "Story {{story_key}} — DONE. Tests passing."</action>
  <goto anchor="step-2-next-story" />
</check>

---

**Step 2e — Fix Loop (subagents)**

<anchor id="step-2e-fix" />
<action>Initialize: {{fix_iteration}} = 0</action>

<action>For each issue in {{story_issues}}:</action>

<action>Announce: "Spawning fix subagent — iteration {{fix_iteration}} for {{story_key}}"</action>

<action>Spawn subagent with prompt:
```
Load config from: {config_file}
Load project context from: {context_file} (if exists)
Story file: {implementation_artifacts}/{{story_key}}.md
Issue to fix: {{issue_description}}
Invoke skill: bmad-dev-story
Target the specific issue above. Read the story file Dev Agent Record for full context.
After fixing, re-run the affected tests to verify resolution.
Update the story file Dev Agent Record with fix notes.
Print status: FIXED | PARTIAL: [what remains] | FAILED: [reason]
```
</action>

<action>Wait for subagent to complete</action>
<action>Increment {{fix_iteration}}</action>
<action>Read story file Dev Agent Record to assess fix outcome</action>

<check if="fix resolved the issue">
  <action>Remove issue from {{story_issues}}</action>
</check>

<check if="{{story_issues}} is empty">
  <action>Re-run QA subagent (Step 2d) to confirm all tests pass after fixes</action>
  <check if="QA passes">
    <action>Update story status to `done` in {status_file}</action>
    <action>Announce: "Story {{story_key}} — DONE after {{fix_iteration}} fix iteration(s)."</action>
    <goto anchor="step-2-next-story" />
  </check>
</check>

<check if="{{fix_iteration}} >= 3 AND {{story_issues}} still has items">
  <action>HALT — escalate to {user_name}</action>
  <output>
Sprint Orchestrator: "HALT — Story {{story_key}} has had {{fix_iteration}} fix iterations. Remaining issues (from story file):

{{story_issues}}

Options:
1. Provide additional context or constraints for the fix approach
2. Accept the issue and create a tech-debt follow-up story
3. Redesign the approach for this story
4. Skip this story for now and continue the sprint"
  </output>
  <ask>Wait for {user_name} decision</ask>
</check>

<anchor id="step-2-next-story" />
<action>Clear {{story_issues}} for the next story</action>
<action>Move to the next story in {{sprint_stories}}</action>

</step>

<step n="3" goal="Sprint closure — Retrospective (subagent)">

<action>Verify all stories in {{sprint_stories}} show `done` in {status_file}</action>
<action>Announce: "All {{story_count}} stories complete. Beginning sprint closure — spawning retrospective subagent."</action>

<action>Spawn subagent with prompt:
```
Load config from: {config_file}
Load project context from: {context_file} (if exists)
Sprint status file: {status_file}
Target epic: {{target_epic}}
Invoke skill: bmad-retrospective
Execute the full retrospective for Epic {{target_epic}}.
Write the retrospective document to the standard output path.
Print when done:
  DONE — Retro file: [path], Action items: N
  BLOCKED: [reason]
```
</action>

<action>Wait for subagent to complete</action>
<action>Read the status line — record {{retro_file_path}} and {{retro_action_count}}</action>
<action>Update epic-{{target_epic}}-retrospective to `done` in {status_file}</action>

</step>

<step n="4" goal="Sprint closure — Adversarial Review (subagent)">

<action>Announce: "Spawning adversarial review subagent across all sprint changes."</action>
<action>Build {{sprint_story_file_list}} — the paths of all story files in this sprint (do not load their contents)</action>

<action>Spawn subagent with prompt:
```
Load config from: {config_file}
Load project context from: {context_file} (if exists)
Sprint story files (read these to discover changed files):
{{sprint_story_file_list}}
Retrospective: {{retro_file_path}}
Invoke skill: bmad-review-adversarial-general
Content to review: all code changes across all sprint stories (collect File List sections from each story file).
Also consider: "Sprint retrospective at {{retro_file_path}}. Review all stories as a cohesive sprint increment, not story by story."
Execute the full review.
Print findings summary when done:
  DONE — Critical: N, High: N, Medium: N, Low: N
  BLOCKED: [reason]
```
</action>

<action>Wait for subagent to complete</action>
<action>Read the status line — record {{adv_critical}}, {{adv_high}}, {{adv_medium}}, {{adv_low}}</action>

</step>

<step n="5" goal="Sprint closure — Red Team (subagent)">

<action>Announce: "Spawning red team subagent."</action>

<action>Spawn subagent with prompt:
```
Load config from: {config_file}
Load project context from: {context_file} (if exists)
Architecture file: {planning_artifacts}/*architecture*.md (if exists)
Sprint story files: {{sprint_story_file_list}}
Invoke skill: bmad-red-team
Scope: all code changes introduced in this sprint (collect from story file File List sections).
Context: architecture document above. Focus on new attack surface introduced by this sprint.
Execute the full red team review.
Print findings summary when done:
  DONE — Critical: N, High: N, Medium: N, Low: N
  BLOCKED: [reason]
```
</action>

<action>Wait for subagent to complete</action>
<action>Read the status line — record {{rt_critical}}, {{rt_high}}, {{rt_medium}}, {{rt_low}}</action>

</step>

<step n="6" goal="Sprint closure — Issue triage and resolution">

<action>Summarize closure findings from the status lines you recorded:</action>

```
SPRINT CLOSURE ISSUES — Epic {{target_epic}}
============================================
Adversarial Review:  Critical {{adv_critical}}, High {{adv_high}}, Medium {{adv_medium}}, Low {{adv_low}}
Red Team:            Critical {{rt_critical}}, High {{rt_high}}, Medium {{rt_medium}}, Low {{rt_low}}
```

<action>If any Critical or High counts are non-zero, spawn a detail-read subagent to extract the finding titles:</action>

<action>Spawn subagent with prompt:
```
Load the adversarial review findings and red team findings for sprint Epic {{target_epic}}.
Look for review output files in {implementation_artifacts} created today.
List all Critical and High findings with: title, severity, one-sentence description.
Also list Medium findings with title only.
Print the list.
```
</action>

<action>Present the full findings list to {user_name}</action>

<ask>Confirm resolution plan:
- Critical and High: MUST be resolved before sprint closes
- Medium: fix now OR create a backlog story (your choice per item)
- Low: create backlog stories or accept

Which Medium items should be fixed now vs. deferred?</ask>

<action>For each issue marked "fix now":</action>
  1. Announce: "Spawning fix subagent for closure issue: {{issue_title}}"
  2. Spawn subagent: invoke `bmad-dev-story` with the issue description, targeting the relevant story/files
  3. Spawn verification subagent: invoke `bmad-qa-generate-e2e-tests` to verify the fix
  4. Read verification status from output — confirm tests pass

<action>For each issue marked "defer":</action>
  1. Spawn subagent: invoke `bmad-create-story` to create a backlog story for the issue
  2. Read the created story key from output
  3. Add to {{deferred_story_keys}}
  4. Update {status_file} with new story at `backlog`

<check if="any Critical or High issues remain unresolved">
  <action>HALT — sprint cannot close</action>
  <output>
Sprint Orchestrator: "HALT — {{unresolved_count}} Critical/High issue(s) still unresolved. Sprint cannot close until these are fixed or explicitly accepted with documented rationale.

Options:
1. Continue fixing (provide context or approach)
2. Accept risk — document rationale and close anyway (explicit acknowledgment required)
3. Escalate to architect"
  </output>
  <ask>Wait for {user_name} decision</ask>
</check>

</step>

<step n="7" goal="Sprint sign-off and closure report">

<action>Update {status_file}:
- All sprint stories: `done`
- epic-{{target_epic}}-retrospective: `done`
- Add sprint closure comment with date</action>

<output>
Sprint Orchestrator: "Sprint CLOSED — Epic {{target_epic}} — {{date}}

  Stories delivered:   {{story_count}}
  Retrospective:       {{retro_file_path}}
  Adversarial:         {{adv_critical+adv_high}} critical/high resolved, {{adv_medium}} medium ({{adv_deferred_count}} deferred)
  Red team:            {{rt_critical+rt_high}} critical/high resolved, {{rt_medium}} medium ({{rt_deferred_count}} deferred)
  Deferred to backlog: {{deferred_story_keys}}
"
</output>

</step>

</workflow>

---

## Orchestrator State (what the orchestrator holds — nothing else)

| Variable | Type | Description |
|----------|------|-------------|
| `{{target_epic}}` | string | Epic number being executed |
| `{{sprint_stories}}` | list of keys | Ordered story keys for this sprint |
| `{{story_issues}}` | list of strings | Current story's unresolved issue summaries |
| `{{fix_iteration}}` | int | Fix loop counter for current story |
| `{{retro_file_path}}` | string | Path written by retro subagent |
| `{{adv_critical/high/medium/low}}` | int | Counts from adversarial review status line |
| `{{rt_critical/high/medium/low}}` | int | Counts from red team status line |
| `{{deferred_story_keys}}` | list | Backlog stories created during closure |

## Disk handoff contract

| Phase | Subagent writes | Orchestrator reads |
|-------|-----------------|-------------------|
| Story prep | `{implementation_artifacts}/{{story_key}}.md` | File exists? Section headers complete? |
| Dev | Story file — tasks [x], Dev Agent Record, File List | All tasks checked? File List populated? |
| Code review | Story file — Dev Agent Record append | Printed status line (Critical/High counts) |
| QA | Story file — Dev Agent Record + test files | Printed status line (pass/fail counts) |
| Fix | Story file — Dev Agent Record fix notes | Printed status (FIXED/PARTIAL/FAILED) |
| Retro | Retrospective document | Printed path + action item count |
| Adversarial | Review findings document | Printed severity counts |
| Red team | Red team findings document | Printed severity counts |

## Sub-Skills Delegated to Subagents

| Phase | Skill |
|-------|-------|
| Story prep | `bmad-create-story` |
| Development | `bmad-dev-story` |
| Code review | `bmad-code-review` |
| QA / testing | `bmad-qa-generate-e2e-tests` |
| Retrospective | `bmad-retrospective` |
| Adversarial review | `bmad-review-adversarial-general` |
| Red team | `bmad-red-team` |
