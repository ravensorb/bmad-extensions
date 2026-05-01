# Epic Execute — Process Definition

## Goal
Execute a complete epic — running one or more sprints for all stories, then applying epic-level quality closure gates. The epic does not close until all Critical and High issues from all closure phases are resolved.

## Context boundary rule
Same as sprint-execute: each unit of work (sprint, closure phase) runs with minimal context from prior units. The epic orchestrator holds only keys, sprint groupings, status summaries, and status-line outputs.

## State
All state passes through disk. See [state-contract.md](./state-contract.md).

## Sub-processes called
`sprint-execute`, `retrospective`, `adversarial-review`, `red-team`
Plus inline analysis (no sub-process): architecture drift, functional completeness.

---

## Phase 1 — Epic identification and sprint planning

**Orchestrator context — this phase only.**

1. Load `sprint-status.yaml` — extract epic and story keys with statuses only
2. Skim epic file headers — story keys and titles only
3. Determine target epic:
   - If user specified → use it
   - Otherwise → find first epic with `in-progress` or `backlog` status with non-done stories
4. Count: total stories, already done, remaining
5. Propose sprint groupings to user:
   - Default: all remaining stories = one sprint
   - User may split into multiple sprints by providing story key groups
6. **Wait for user to confirm execution plan**
7. Update `sprint-status.yaml`: epic → `in-progress`

---

## Phase 2 — Sprint execution loop

For each sprint in the confirmed plan, in order — each sprint is a separate session/subagent.

1. Announce: "Starting Sprint N of M — stories: [keys]"
2. Run sub-process `sprint-execute` for this sprint's story keys
3. Collect output status line from sprint: stories done, issues resolved/deferred
4. After each sprint (except last): present results and **wait for user to confirm** proceeding to next sprint

---

## Phase 3 — Epic closure: Retrospective

Separate session/subagent receives: `sprint-status.yaml` path + target epic number + sprint summaries.

Run sub-process `retrospective` for the full epic (cross-sprint view).
Write to `{artifacts}/epic-{N}-retro-{date}.md`.
Update `sprint-status.yaml`: epic retrospective → `done`.

Output status line: `DONE — Retro file: [path], Action items: N`

---

## Phase 4 — Epic closure: Adversarial review

Separate session/subagent receives: all story file paths for the epic + retrospective path.

Run sub-process `adversarial-review`.
Scope: all code changed across the entire epic (collected from story File List sections).
Focus: systemic issues visible only across all stories — inter-story interactions, data flows, consistency of approach.

Output status line: `DONE — Critical: N, High: N, Medium: N, Low: N, Output: [path]`

---

## Phase 5 — Epic closure: Red team

Separate session/subagent receives: all story file paths + architecture file path + retrospective path.

Run sub-process `red-team` (see [red-team.md](./red-team.md)).
Focus: new attack surface introduced by the entire epic; security properties spanning multiple stories; failure modes that only emerge when all features interact.

Output status line: `DONE — Critical: N, High: N, Medium: N, Low: N, Output: [path]`

---

## Phase 6 — Epic closure: Architecture drift analysis

Separate session/subagent receives: architecture spec file + all story file paths.

Perform systematic comparison — specification vs. implementation — across these dimensions:

1. **Data model drift** — specified entities, fields, types, relationships vs. source code
2. **API contract drift** — specified endpoints, methods, payload shapes vs. implemented routes
3. **Component architecture drift** — specified boundaries vs. actual file/module structure
4. **NFR drift** — performance targets, security controls, observability requirements specified vs. implemented
5. **Technology/pattern drift** — specified libraries, frameworks, patterns vs. actually used

Categorize each finding:
- **Intentional**: documented in a story Dev Agent Record — acceptable
- **Undocumented**: deviation with no documented rationale — this is an issue
- **Spec gap**: spec was silent, implementation made a reasonable choice — flag for doc update
- **Missing**: specified but not yet implemented

Write to `{artifacts}/epic-{N}-arch-drift-{date}.md`.

Output status line: `DONE — Undocumented deviations: N, Missing: N, Spec gaps: N, Output: [path]`

---

## Phase 7 — Epic closure: Functional completeness review

Separate session/subagent receives: PRD file + epic file (target epic section) + all story file paths.

For each acceptance criterion in the epic:
- Identify which story implements it
- Verify story Dev Agent Record confirms implementation
- Check a test covers it
- Flag: not in any story / story done but AC unverified / no test coverage

For each user-facing feature described in the PRD for this epic:
- Identify implementing story/stories
- Verify story is done
- Check implementation matches described behavior

Write to `{artifacts}/epic-{N}-functional-completeness-{date}.md`.

Output status line: `DONE — ACs checked: N, Covered: N, Gaps: N, PRD discrepancies: N, Output: [path]`

---

## Phase 8 — Issue triage and resolution

**Orchestrator context — this phase only.**

1. Collect severity counts from recorded status lines of phases 4–7
2. If any Critical/High counts or undocumented drift/AC gaps are non-zero:
   - Spawn targeted read session to extract finding titles from output documents
3. Present consolidated findings to user
4. **Wait for user to confirm resolution plan:**
   - Critical/High → must fix before epic closes
   - Undocumented drift → fix code OR update architecture doc
   - AC gaps → implement OR explicitly defer with rationale
   - Medium → fix now or create backlog story
   - Low → backlog story or accept
   - Spec gaps → update architecture/PRD doc (no code change)
5. For each "fix now": run `dev-story` + `qa-generate`
6. For each "doc update": update the relevant architecture or PRD document
7. For each "defer": run `create-story` to create a backlog story, update `sprint-status.yaml`
8. If any Critical/High remain unresolved → **HALT, escalate to user**

---

## Phase 9 — Epic sign-off

1. Update `sprint-status.yaml`: epic → `done`, retrospective → `done`, all stories → `done`
2. Print epic closure report:

```
EPIC CLOSED — Epic {N}: {title} — {date}
Sprints executed:         N
Stories delivered:        N
Issues resolved:          N
Issues deferred:          N (story keys: [...])
Architecture updated:     yes/no
PRD updated:              yes/no
Retrospective:            [path]
```
