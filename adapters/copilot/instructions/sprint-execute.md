## Sprint Execute

When the user asks to run sprint-execute or execute a sprint end-to-end, act as the Sprint Orchestrator using the following process.

**Full process definition:** `docs/processes/sprint-execute.md`  
**State contract:** `docs/processes/state-contract.md`

> **Context boundary rule:** Each story phase must be a separate Copilot Chat session. Tell the user: "Please start a new chat for the next phase. Paste this prompt: [prompt]". Pass only file paths — not prior story implementation details.

### Phase 1 — Identify sprint scope

Load `sprint-status.yaml` (keys and statuses only). Skim epic file headers for story keys and titles.
Determine scope (user-specified or first non-done epic). Remove `done` stories.
Present ordered list. **Ask user to confirm before proceeding.**

### Phase 2 — Per-story loop

For each story, direct the user to start a **new chat** for each of these phases:

**2a. Story prep** — New chat prompt:
```
Load project config. Story to create: {story-key} in Epic {N}.
Run the create-story workflow. Write story file. Print: DONE — [path] | BLOCKED: [reason]
```
After: verify file exists. Present AC count. Ask user to confirm ready. Update sprint-status.yaml → `ready-for-dev`.

**2b. Development** — New chat prompt:
```
Load project config. Story file: {path}.
Run dev-story workflow. Complete all tasks [x], populate Dev Agent Record and File List.
Print: DONE — Tasks: N/N, Files: N | BLOCKED: [reason]
```
After: verify all tasks `[x]`, File List populated. Update sprint-status.yaml → `review`.

**2c. Code review** — New chat prompt:
```
Load project config. Story file: {path} (read File List for changed files).
Run code-review on those files. Print: DONE — Critical: N, High: N, Medium: N, Low: N
```
After: record counts. If Critical/High > 0 → go to 2e before 2d.

**2d. QA** — New chat prompt:
```
Load project config. Story file: {path}.
Run qa-generate for this story's implementation. Run all generated tests.
Print: DONE — Tests: N written, N passing | FAILURES: N — [description]
```
After: if all pass → update sprint-status.yaml → `done`. If failures → go to 2e.

**2e. Fix loop** (max 3, new chat each) — Prompt:
```
Load project config. Story file: {path}. Issue: {description}.
Run dev-story targeting this issue. Re-run affected tests.
Print: FIXED | PARTIAL: [what remains] | FAILED: [reason]
```
After 3 iterations unresolved → HALT, present escalation options to user.

### Phase 3 — Sprint closure

All stories must be `done`. Each phase is a new chat.

**3a. Retrospective** — Prompt: `Load config. Run retrospective for Epic {N}. Print: DONE — Retro: [path], Actions: N`

**3b. Adversarial review** — Prompt: `Load config. Story files: {list}. Collect File Lists. Run adversarial-review on all sprint changes as one cohesive increment. Print: DONE — Critical: N, High: N, Medium: N, Low: N, Output: [path]`

**3c. Red team** — Prompt: `Load config. Story files: {list}. Architecture: {path}. Collect File Lists. Run red-team (see red-team instructions). Print: DONE — Critical: N, High: N, Medium: N, Low: N, Output: [path]`

### Phase 4 — Issue triage

Collect counts from 3b/3c. If Critical/High > 0: new chat to read finding titles from output files.
Present to user. **Ask for resolution plan.** Fix now → new chat dev-story + qa-generate. Defer → new chat create-story; update sprint-status.yaml. **Cannot close with unresolved Critical/High.**

### Phase 5 — Sign-off

Update sprint-status.yaml: all stories `done`, retro `done`. Report: stories, issues resolved/deferred.
