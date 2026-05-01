# Sprint Execute — Process Definition

## Goal
Execute all stories in a sprint from preparation through done, then run quality closure gates. The sprint does not close until all Critical and High issues from closure are resolved.

## Context boundary rule
**Each story phase must run with minimal context from previous phases.** This prevents context window exhaustion and focus contamination across stories. Pass only: target story file path + project config path.

- Claude Code: enforce via subagent delegation (fresh `claude` invocation per phase)
- Cursor / Copilot: enforce manually — start a new Composer/chat session for each phase

## State
All state passes through disk. See [state-contract.md](./state-contract.md).

## Sub-processes called
`create-story`, `dev-story`, `code-review`, `qa-generate`, `retrospective`, `adversarial-review`, `red-team`
(Adapter maps these to tool-specific invocations.)

---

## Phase 1 — Sprint scope identification

**Orchestrator context — this phase only.**

1. Load `sprint-status.yaml` — extract story keys and statuses only (not story content)
2. Skim epic file headers — extract story keys and titles only
3. Determine sprint scope:
   - If user specified an epic number or story keys → use those
   - Otherwise → find the first epic with `in-progress` status, or the first epic with `backlog` stories
4. Remove any stories already at `done` from the execution list
5. Build an ordered execution list (preserve order from `sprint-status.yaml`)
6. Present scope to user: story key list + current statuses
7. **Wait for user confirmation before proceeding**

---

## Phase 2 — Per-story execution loop

Repeat steps 2a–2e for each story in order. Each step is a separate session/subagent.

### 2a. Story preparation
*Goal: produce a complete, implementation-ready story file.*

1. Check: does `{artifacts}/{story-key}.md` exist?
2. If not → run sub-process `create-story` for this epic/story number
3. Load only the story file's section headers and AC list (not full content)
4. Present summary to user: title + AC count + task count
5. **Wait for user to confirm the story is ready for development**
6. Update `sprint-status.yaml`: story → `ready-for-dev`

### 2b. Development
*Goal: implement all story tasks with passing tests.*

Session/subagent receives: story file path + config paths.

1. Run sub-process `dev-story` with the story file path
2. After completion, read from the story file:
   - Are all task checkboxes `[x]`?
   - Is Dev Agent Record populated?
   - Is File List populated?
3. If any check fails → HALT and report to user
4. Update `sprint-status.yaml`: story → `review`

Output status line: `DONE — Tasks: N/N complete, File List: N files`

### 2c. Code review
*Goal: catch issues before QA.*

Session/subagent receives: story file path (to read File List) + config paths.

1. Read the File List section from the story file
2. Run sub-process `code-review` on those files
3. Record severity counts from the output status line
4. If Critical or High findings exist → go to 2e (Fix Loop) before QA
5. If clean → proceed to 2d

Output status line: `DONE — Critical: N, High: N, Medium: N, Low: N`

### 2d. QA / test coverage
*Goal: all acceptance criteria covered by passing tests.*

Session/subagent receives: story file path + config paths.

1. Run sub-process `qa-generate` targeting the story's implementation
2. All generated tests must be run and results verified
3. If failures → go to 2e (Fix Loop)
4. If all pass → update `sprint-status.yaml`: story → `done`

Output status line: `DONE — Tests: N written, N passing` or `FAILURES: N failing — [description]`

### 2e. Fix loop (max 3 iterations)
*Goal: resolve all issues before marking story done.*

Session/subagent receives: story file path + issue description + config paths.

1. For each unresolved issue:
   - Run sub-process `dev-story` with the story file and issue context
   - Re-run affected tests to verify resolution
   - Remove issue from list if resolved
2. Increment iteration counter
3. If all issues resolved → re-run 2d (QA) to confirm
4. If iteration counter reaches 3 and issues remain → **HALT, escalate to user**

User options at escalation:
- Provide additional context or approach
- Accept issue as tech debt (create a follow-up story)
- Skip this story for now

After escalation decision → update `sprint-status.yaml` accordingly and continue

---

## Phase 3 — Sprint closure

All stories must be at `done` before starting closure. Each closure phase is a separate session/subagent.

### 3a. Retrospective
Session receives: `sprint-status.yaml` path + target epic number.

Run sub-process `retrospective` for the epic.
Write retrospective document to `{artifacts}/epic-{N}-retro-{date}.md`.

Output status line: `DONE — Retro file: [path], Action items: N`

### 3b. Adversarial review
Session receives: list of all story file paths for this sprint (to collect File Lists) + retrospective path.

Run sub-process `adversarial-review`.
Scope: all code changed across all sprint stories.
Also consider: retrospective action items; review as cohesive sprint increment, not story-by-story.

Output status line: `DONE — Critical: N, High: N, Medium: N, Low: N, Output: [path]`

### 3c. Red team
Session receives: list of all story file paths + architecture file path + retrospective path.

Run sub-process `red-team` (see `processes/red-team/process.md`).
Focus: new attack surface introduced by this sprint.

Output status line: `DONE — Critical: N, High: N, Medium: N, Low: N, Output: [path]`

---

## Phase 4 — Issue triage and resolution

**Orchestrator context — this phase only.**

1. Collect severity counts from the recorded status lines of 3b and 3c
2. If any Critical/High counts are non-zero:
   - Spawn a targeted read session to extract finding titles from the output documents
3. Present full consolidated findings list to user
4. **Wait for user to confirm resolution plan:**
   - Critical/High → must fix before sprint closes
   - Medium → fix now or create backlog story (per item)
   - Low → create backlog story or accept
5. For each "fix now":
   - Run `dev-story` with fix context
   - Run `qa-generate` to verify
6. For each "defer":
   - Run `create-story` to create a backlog story
   - Update `sprint-status.yaml` with new story at `backlog`
7. If any Critical/High remain unresolved → **HALT, escalate to user**

User options at escalation:
- Continue fixing
- Accept risk with documented rationale (explicit acknowledgment required)
- Escalate to architect

---

## Phase 5 — Sprint sign-off

1. Verify all sprint stories are at `done` in `sprint-status.yaml`
2. Update `sprint-status.yaml`: retrospective → `done`, add closure comment with date
3. Print sprint closure report:

```
SPRINT CLOSED — Epic {N} — {date}
Stories delivered:    N
Issues resolved:      N
Issues deferred:      N (story keys: [...])
Retrospective:        [path]
```
