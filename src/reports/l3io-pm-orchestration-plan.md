---
title: 'LiquidLogicLabs PM Orchestration Module Plan'
status: 'complete'
module_name: 'LiquidLogicLabs PM Orchestration'
module_code: 'l3io-pm'
module_description: 'Sprint and epic orchestration workflows for LiquidLogicLabs projects — story writing through closure with full quality gates'
architecture: ''
standalone: true
expands_module: ''
skills_planned:
  - bmad-l3io-pm-sprint-execute
  - bmad-l3io-pm-epic-execute
config_variables: []
created: '2026-05-15'
updated: '2026-05-15'
---

# LiquidLogicLabs PM Orchestration Module Plan

## Vision

Sprint and epic orchestration for LiquidLogicLabs projects. Covers the full lifecycle from story generation through closure — including quality gates (fix loops, clean release review), retrospectives, UX review, adversarial and red-team analysis, and architectural drift detection. Designed to produce clean, not over-engineered releases by enforcing quality at every phase.

**Users:** LiquidLogicLabs delivery teams running AI-assisted sprint/epic execution.

## Architecture

**Two workflows:** `bmad-l3io-pm-sprint-execute` and `bmad-l3io-pm-epic-execute`. Workflows (not agents) — no persistent persona is needed between invocations. Each phase runs in a fresh subagent; all state passes through disk. The epic workflow calls the sprint workflow as a subworkflow. No agent memory — purely file-based state via the split sprint status files (sprint-status-active.yaml, sprint-status-backlog.yaml, sprint-status-archived.yaml) and artifact files.

**Rationale:** Sprint and epic are genuinely different journeys with different phase sets, different quality gates, and different closure outputs. Separate workflows keep each coherent and independently invocable. A single agent would add unnecessary persona overhead for what are essentially orchestration pipelines.

### Sprint Phase Sequence

**Per-story loop** (each story runs fully before closure; stories run in parallel when independent, respecting declared dependencies):
1. Story prep — spawn `bmad-create-story`; present title + AC count to user for confirmation; auto-approve if spec clean; migrate legacy flat file if found at old path
2. Development — spawn `bmad-dev-story`; all task checkboxes must be [x]; Dev Agent Record and File List must be populated
3. Code review — spawn `bmad-code-review` against changed files from File List; Critical/High → go to fix loop immediately
4. QA — spawn `bmad-qa-generate-e2e-tests`; all tests must pass; failures → go to fix loop
5. **Fix loop** — spawn `bmad-dev-story` per issue; re-run QA after each fix; max 3 iterations then escalate to user (options: add context, accept tech debt, redesign, skip story)

**Sprint closure** (after all stories are `done`):
6. Retrospective — sprint-scoped; grave concerns surfaced to user directly
7. **Clean release review** — scope: this sprint's changes; flags over-engineering, scope creep, YAGNI violations
8. Adversarial review — `bmad-review-adversarial-general` across all sprint story changes as cohesive increment
9. Red-team review — `bmad-l3io-sec-agent-redteam` if installed (scope=sprint), else skip/fallback
10. UX review — conditional: if UX spec exists, check against spec; else offer standard WCAG/usability review or skip
11. **Light architectural drift review** — sprint-scoped; inline analysis (no skill wrapper); 5 dimensions: data model, API contracts, component boundaries, NFRs, technology/patterns
12. Issue triage — Critical/High must be resolved before sprint closes; Medium: fix now or defer to backlog; Low: backlog or accept; sprint cannot close with unresolved Critical/High
13. Sprint sign-off and closure report

### Epic Phase Sequence

**Epic planning:**
1. Epic planning — generate high-level stories; user confirms sprint groupings (stories can be split across multiple sprints); create epic/sprint directory structure

**Sprint execution loop:**
2. Execute sprints — sequential by default; parallel when sprint groups are proven independent and status merges are serialized; each sprint spawns `bmad-l3io-pm-sprint-execute`; halt on BLOCKED/FAILED; confirm between sprints

**Epic closure** (after all sprints done):
3. Retrospective — epic-scoped; incorporates cross-sprint learnings; grave concerns surfaced to user; **must complete before closure parallels begin**
4. *(parallel batch when outputs are isolated files)* **Clean release review** (epic/solution-scoped) + Adversarial review (`bmad-review-adversarial-general` across full epic) + Red-team review (`bmad-l3io-sec-agent-redteam` if installed, scope=epic) + UX review (conditional)
5. **Architecture drift analysis** — inline, solution-scoped; 5 dimensions: data model, API contracts, component boundaries, NFRs, technology/patterns; findings: intentional / undocumented / spec gap / missing
6. **Functional completeness review** — inline; checks each PRD acceptance criterion is in a story, implemented, and tested; flags PRD discrepancies
7. Issue triage and resolution — Critical/High + undocumented drift + AC gaps must be resolved; fix now (spawn fix subagent + QA verification) or defer to backlog (spawn `bmad-create-story`); epic cannot close with unresolved Critical/High
8. Epic sign-off and final report

### Memory Architecture

**No agent memory.** All state is file-based:
- `{artifacts}/sprint-status-active.yaml`, `{artifacts}/sprint-status-backlog.yaml`, `{artifacts}/sprint-status-archived.yaml` — story statuses and epic/sprint state, split into active (in-progress epics), backlog (not-yet-started work + consolidated deferred-issue list), and archived (done epics, moved at epic close); a legacy single `sprint-status.yaml` is auto-split on first run
- `{artifacts}/epic-XX/sprint-YY/stories/{story-key}.md` — story artifacts
- `{artifacts}/epic-XX/sprint-YY/closure/` — sprint closure outputs (retro, adversarial, redteam, etc.)
- `{artifacts}/epic-XX/sprint-YY/tests/` — QA test artifacts
- `{artifacts}/epic-XX/epic-closure/` — epic closure outputs

### Memory Contract

N/A — file-based state only. See artifact paths above.

### Cross-Agent Patterns

- **Epic → Sprint:** `bmad-l3io-pm-epic-execute` spawns `bmad-l3io-pm-sprint-execute` per sprint with: config path, status file, story keys, sprint number, epic root dir. Sprint writes closure outputs to disk; epic reads status line + targeted disk reads only.
- **Sprint → Security (optional):** At red-team review phase, sprint checks for `bmad-l3io-sec-agent-redteam`. If present, spawns with scope=sprint and sprint artifact path. If absent, skips with recorded note.
- **Orchestrator memory rule:** Both orchestrators hold only keys, sprint groupings, status values, and printed status-line summaries from subagents. Never accumulate file contents, diffs, or story prose.
- **Subagent invocation:** Agent tool preferred (self-contained prompt, no conversation history forwarded); Bash CLI fallback (`claude --print`).
- **Progress reporting:** ETA ranges (not exact timestamps); parallel batch size and queue position reported; elapsed time refreshed after each completion.
- **User escalation:** Fix loop escalates after 3 iterations; grave concerns from retrospective surfaced directly to user; epic/sprint cannot close with unresolved Critical/High without explicit user acknowledgment.
- **Parallel safety gate:** Before each parallel batch — verify no shared output file collisions, no concurrent writes to the sprint status files (sprint-status-active.yaml / sprint-status-backlog.yaml / sprint-status-archived.yaml), no unresolved blocker that invalidates siblings. If uncertain → force sequential.

## Skills

### bmad-l3io-pm-sprint-execute

**Type:** workflow

**Persona:** Sprint Orchestrator — a lightweight traffic controller. Holds only story keys, statuses, and issue summaries. Never accumulates implementation details. All work delegated to fresh subagents.

**Core Outcome:** A fully closed sprint where every story is implemented, reviewed, QA-verified, and all Critical/High issues from closure reviews are resolved.

**The Non-Negotiable:** The sprint does NOT close with unresolved Critical/High issues. All bugs within a sprint must be addressed before closure.

**Capabilities:**

| Capability | Outcome | Inputs | Outputs |
| ---------- | ------- | ------ | ------- |
| Story preparation | Story file exists, user-confirmed, ready for dev | Config, status file, epic/story keys | Story file at structured path |
| Development orchestration | All story tasks implemented, File List populated | Story file path | Updated story file (tasks [x], Dev Agent Record, File List) |
| Code review | Critical/High findings routed to fix loop immediately | Story file, changed files list | Review findings in Dev Agent Record |
| QA orchestration | Tests written and passing | Story file | QA evidence report in `tests/` |
| Fix loop | All issues resolved within max 3 iterations | Issue description, story file | Updated story, re-verified QA |
| Sprint closure reviews | Retro, clean release, adversarial, red team, UX (conditional), light arch drift | All story files, closure output dir | Closure docs in `closure/` |
| Issue triage | All Critical/High resolved; Medium/Low deferred or fixed | Findings from closure reviews | Deferred backlog stories, updated status file |
| Sprint sign-off | Status updated, closure report printed | All closure artifacts | Updated sprint status files, closure report |

**Memory:** None — file-based state only via the split sprint status files (sprint-status-active.yaml, sprint-status-backlog.yaml, sprint-status-archived.yaml) and artifact files.

**Init Responsibility:** Creates sprint directory structure if missing: `stories/`, `closure/`, `tests/`, `planning_sprint_dir`.

**Activation Modes:** Interactive (standalone invocation) and headless (called by bmad-l3io-pm-epic-execute).

**Tool Dependencies:**
- BMad skills (must be installed in target repo): `bmad-create-story`, `bmad-dev-story`, `bmad-code-review`, `bmad-qa-generate-e2e-tests`, `bmad-retrospective`, `bmad-review-adversarial-general`
- Optional: `bmad-l3io-sec-agent-redteam` (red-team review phase; skipped if absent)
- Optional: `bmad-ux-review` (UX review phase; skipped if absent and user declines standard review)
- Config: `{project-root}/_bmad/bmm/config.yaml`

**Design Notes:**
- Parallel execution across stories (not within a story) — phases 2a/2b/2c/2d are candidates; fix loop and issue triage always sequential
- Max parallel subagents default 2, hard cap 4, user-overridable
- Subagent invocation: Agent tool preferred, Bash CLI fallback
- Progress reporting with ETA ranges after every phase
- Legacy flat file migration: if story file found at old flat path, move to structured path before story prep

**Relationships:** Called by `bmad-l3io-pm-epic-execute` as a subworkflow; calls `bmad-l3io-sec-agent-redteam` when installed.

---

### bmad-l3io-pm-epic-execute

**Type:** workflow

**Persona:** Epic Orchestrator — a lightweight traffic controller. Holds only epic/story keys, sprint groupings, and status-line summaries. Never accumulates implementation details, diffs, or story prose.

**Core Outcome:** A fully closed epic where all sprints are delivered, all closure reviews complete, all Critical/High issues resolved, architecture drift documented, functional completeness verified.

**The Non-Negotiable:** The epic does NOT close with unresolved Critical/High issues or uncovered AC gaps. All bugs AND tech debt must be addressed before epic closure.

**Capabilities:**

| Capability | Outcome | Inputs | Outputs |
| ---------- | ------- | ------ | ------- |
| Epic planning | High-level stories generated; sprint groupings confirmed by user | Epic spec, status file | High-level story files, updated status file |
| Sprint execution loop | All sprints executed sequentially (or parallel when safe) | Sprint plan, config | Sprint closure artifacts, updated status file |
| Epic retrospective | Epic-scoped retro with cross-sprint learnings | Sprint summaries, story files | Retro doc in `epic-closure/` |
| Clean release review | Epic/solution-scoped YAGNI and over-engineering check | All story files | Clean release report in `epic-closure/` |
| Adversarial review | Full epic adversarial analysis as cohesive increment | All story files, retro doc | Adversarial findings in `epic-closure/` |
| Red-team review | Epic-scoped security analysis | Architecture file, all story files | Red team findings in `epic-closure/` |
| UX review | Epic-scoped UX check against spec or standard principles | All story files, UX spec (optional) | UX review in `epic-closure/` |
| Architecture drift analysis | 5-dimension drift check (inline, no skill wrapper) | Architecture spec, all story files | Arch drift report in `epic-closure/` |
| Functional completeness review | PRD AC coverage and feature alignment (inline) | PRD file, epic section, all story files | Completeness report in `epic-closure/` |
| Issue triage and resolution | All Critical/High + AC gaps resolved; deferred items backlogged | All closure findings | Fix verification in `epic_test_dir/`, backlog stories |
| Epic sign-off | Status updated, final report printed | All closure artifacts | Updated sprint status files (epic archived to sprint-status-archived.yaml at close), epic closure report |

**Memory:** None — file-based state only.

**Init Responsibility:** Creates epic directory structure if missing: `epic-XX/`, `epic-XX/epic-closure/`, `epic-XX/tests/`, planning epic dir.

**Activation Modes:** Interactive only (user-invoked; each sprint spawns sprint-execute which can run headless).

**Tool Dependencies:**
- `bmad-l3io-pm-sprint-execute` (required — executes each sprint)
- BMad skills: `bmad-retrospective`, `bmad-review-adversarial-general`, `bmad-create-story`, `bmad-dev-story`, `bmad-qa-generate-e2e-tests`
- Optional: `bmad-l3io-sec-agent-redteam`, `bmad-ux-review`
- Config: `{project-root}/_bmad/bmm/config.yaml`

**Design Notes:**
- Epic planning step presents sprint groupings to user — stories can be split across multiple sprints
- Closure batch parallelism: retro runs first (sequential); adversarial/red-team/UX/clean-release can run in parallel when output files don't collide
- Architecture drift and functional completeness are always sequential (inline analysis, no skill wrapper)
- Orchestrator state: keys + groupings + status-line summaries only; never full file contents

**Relationships:** Calls `bmad-l3io-pm-sprint-execute` per sprint; calls `bmad-l3io-sec-agent-redteam` when installed.

---

## Configuration

Config is loaded from `{project-root}/_bmad/bmm/config.yaml`. The module reads standard BMad paths and adds two optional tuning parameters.

| Variable | Prompt | Default | Result Template | User Setting |
| -------- | ------ | ------- | --------------- | ------------ |
| `parallel_mode` | Enable parallel story execution within a sprint? (adaptive/off) | `adaptive` | `parallel_mode: {value}` | Yes |
| `max_parallel_subagents` | Max parallel stories per sprint (2–4) | `2` | `max_parallel_subagents: {value}` | Yes |

All artifact paths (`implementation_artifacts`, `planning_artifacts`, `output_folder`) are resolved from core BMad config — no duplication here.

## External Dependencies

| Dependency | Type | Required By | Setup Notes |
| ---------- | ---- | ----------- | ----------- |
| `bmad-create-story` | BMad skill | bmad-l3io-pm-sprint-execute | Must be installed in target repo |
| `bmad-dev-story` | BMad skill | bmad-l3io-pm-sprint-execute | Must be installed in target repo |
| `bmad-code-review` | BMad skill | bmad-l3io-pm-sprint-execute | Must be installed in target repo |
| `bmad-qa-generate-e2e-tests` | BMad skill | bmad-l3io-pm-sprint-execute | Must be installed in target repo |
| `bmad-retrospective` | BMad skill | Both workflows | Must be installed in target repo |
| `bmad-review-adversarial-general` | BMad skill | Both workflows | Must be installed in target repo |
| `bmad-l3io-sec-agent-redteam` | l3io-sec module skill | Both workflows | Optional; red-team phase skipped if absent |
| `bmad-ux-review` | BMad skill | Both workflows | Optional; UX phase skipped or uses standard review if absent |

## UI and Visualization

No dedicated UI. Progress is communicated via structured console output with ETA ranges and phase-by-phase status lines. Closure reports are Markdown documents written to disk.

## Setup Extensions

No setup extensions beyond config collection. The workflows create required directory structures at runtime.

## Integration

**Standalone value:** Both workflows can be invoked independently — sprint-execute for running a single sprint, epic-execute for running a full epic. Neither requires the other to be pre-run.

**l3io-sec integration:** When `bmad-l3io-sec-agent-redteam` is installed, both workflows automatically delegate red-team review to it. When absent, the phase is skipped with a recorded note. No configuration needed — detection is automatic.

**BMad dependency:** Requires the listed BMad skills to be installed in the target repo. The setup skill will check for these and warn if any are missing.

## Creative Use Cases

- Run sprint-execute on a single story for a focused, fully-reviewed micro-delivery
- Use epic-execute's functional completeness review standalone (via subagent) to audit an existing codebase against its PRD
- Epic planning step can generate high-level stories from a spec without running any sprints — useful for upfront sprint breakdown planning

## Ideas Captured

### Sprint Workflow
- Phase order: story writing (detailed) → development → code review → QA → (fix loop: dev → code review → QA until clean) → retrospective → UX review (conditional) → adversarial review → red-team review → light architectural drift review
- Parallel execution at story level — BUT stories may have dependencies; dependent stories must sequence after their dependencies resolve
- Fix loop: ALL bugs must be addressed before sprint can close — hard gate
- When a story is in the fix loop, independent stories continue in parallel; dependent stories wait
- Light architectural drift = sprint-scoped (changes in this sprint only)
- UX detection: check for existence of UX spec file created by BMad UX agent; if ambiguous, prompt user
- Story auto-approval: if spec is clean enough, workflow generates and approves without user intervention; if spec is ambiguous, prompt user

### Story Writing — Two Levels
- Epic planning phase: generates HIGH-LEVEL stories (feature-level, not implementation-level) from the epic spec
- Sprint planning phase: generates DETAILED stories (implementation-ready, acceptance criteria, etc.) refined from the high-level epic stories
- This means story writing happens at TWO points in the lifecycle, not just at sprint start

### Story Dependencies
- Stories may declare dependencies on other stories within the sprint
- Orchestrator must resolve a dependency order before starting parallel execution
- A story cannot enter development until all its dependencies reach 'done'
- Need to decide: how are dependencies declared? (in story file, in the sprint status files, or inferred?)

### Sprint — Additional Learnings from Legacy Workflow
- Story prep presents title + AC count to user for confirmation before dev starts
- Legacy flat file migration: if story file exists at old flat path, move it to structured path before prep
- Fix loop max 3 iterations, then escalate with 4 options: add context, accept tech debt, redesign, skip story
- Parallel execution: across stories only, never across phases within same story; phases 2a/2b/2c/2d are candidates; fix loop and issue triage are always sequential
- Sprint closure sign-off report format: stories delivered, retro path, Critical/High resolved per review type, deferred backlog keys
- Sub-skills: create-story, dev-story, code-review, qa-generate-e2e-tests, retrospective, adversarial-general, red-team, ux-review

### Epic — Additional Learnings from Legacy Workflow
- Functional completeness review: checks each PRD AC is in a story, implemented, and tested; cross-checks PRD user-facing features
- Epic closure parallel batch: adversarial + red team + UX + (clean release) can run in parallel after retro completes — outputs are isolated files
- Architecture drift: 5 dimensions (data model, API contracts, component boundaries, NFRs, technology/patterns); findings categorized intentional/undocumented/spec gap/missing
- Issue resolution options at epic: fix now (fix subagent + QA verification + evidence stored in epic_test_dir), defer to backlog (create-story), accept with rationale, update docs for spec gaps
- Deferred story keys tracked and reported in epic sign-off
- Epic sign-off: epic status → done; all stories verified done; closure comment with date

### Retrospective
- Sprint retro: scoped to sprint artifacts and story outcomes; audience = dev team
- Epic retro: scoped to epic outcomes and cross-sprint patterns; audience = dev team
- Escalation mechanism: grave concerns (critical issues, blockers, risks) are surfaced to the user directly — not just buried in a report
- Adversarial review: uses bmad-review-adversarial-general (same skill, not a new one)

### Clean Release Goal
- Dedicated review pass — a distinct phase in both sprint and epic closure
- Asks: did we build exactly what was specified, no more? Is anything over-engineered or premature?
- Uses simplify skill internally or equivalent
- Placement: AFTER QA passes, BEFORE adversarial review — so adversarial can also flag any over-engineering the clean release pass surfaces

### Epic Workflow
- Phase order: execute sprints (sequential for now) → epic retrospective → adversarial review → red-team review → full architectural drift review
- Fix loop at epic closure: ALL bugs AND tech debt must be addressed — harder gate than sprint
- Full architectural drift = solution-scoped (entire codebase)
- Parallel sprint execution: deferred — sequential for initial build

### Cross-Module Integration
- Red-team review steps: call bmad-l3io-sec-agent-redteam if security module is installed; otherwise use built-in fallback or skip
- Adversarial review: call bmad-review-adversarial-general

## Build Roadmap

**Recommended build order:**

1. **`bmad-l3io-pm-sprint-execute`** (Build Workflow) — Build first because epic-execute depends on it. The sprint workflow is the core execution unit; getting it right makes epic straightforward.
2. **`bmad-l3io-pm-epic-execute`** (Build Workflow) — Build second. Shares the same orchestration patterns and subagent delegation model as sprint-execute. Pass this plan document as context so the builder understands the sprint workflow it calls.

**Next steps:**
1. Build each skill using **Build a Workflow (BW)** — share this plan document as context
2. When both skills are built, return to **Create Module (CM)** to scaffold the module infrastructure (setup skill, marketplace.json, symlinks)
