## Epic Execute

When the user asks to run epic-execute or execute a full epic end-to-end, act as the Epic Orchestrator using the following process.

**Full process definition:** `docs/processes/epic-execute.md`

> **Context boundary rule:** Each sprint and each closure phase must be a separate Copilot Chat session. Pass only paths and a brief note — not implementation details from prior sessions.

### Phase 1 — Epic identification and sprint planning

Load `sprint-status.yaml` (keys and statuses only). Skim epic file headers.
Determine target epic. Count remaining stories. Propose sprint groupings (default: all remaining = one sprint).
**Ask user to confirm plan.** Update sprint-status.yaml: epic → `in-progress`.

### Phase 2 — Sprint execution loop

For each sprint, direct user to start a **new chat** with sprint-execute instructions active:
```
Apply sprint-execute instructions.
Target: Epic {N}, stories: {story-key-list}
Execute the complete sprint. Print: DONE — Stories: N, Resolved: N, Deferred: N, Retro: [path]
```
After each sprint: present results. **Ask user to confirm proceeding to next sprint.**

### Phase 3–7 — Epic closure phases (each a new chat)

**Retrospective:**
```
Load config. Epic {N}. Sprint summaries: {status-line outputs}.
Run retrospective (cross-sprint view). Print: DONE — Retro: [path], Actions: N
```
Update sprint-status.yaml: retrospective → `done`.

**Adversarial review:**
```
Load config. Story files: {all epic story paths}. Retro: {path}.
Collect File Lists. Run adversarial-review on all epic changes as cohesive product increment.
Look for systemic issues only visible across all stories.
Print: DONE — Critical: N, High: N, Medium: N, Low: N, Output: [path]
```

**Red team:**
```
Load config. Story files: {list}. Architecture: {path}. Retro: {path}.
Run red-team (see red-team instructions). Focus: full-epic attack surface, cross-story security properties.
Print: DONE — Critical: N, High: N, Medium: N, Low: N, Output: [path]
```

**Architecture drift:**
```
Load config. Architecture spec: {path} (full). Story files: {list}.
Compare spec vs. implementation: data models, API contracts, component boundaries, NFRs, technology/patterns.
Categorize: INTENTIONAL | UNDOCUMENTED | SPEC-GAP | MISSING
Write to {artifacts}/epic-{N}-arch-drift-{date}.md
Print: DONE — Undocumented: N, Missing: N, Spec gaps: N, Output: [path]
```

**Functional completeness:**
```
Load config. PRD: {path} (full). Epic {N} section. Story files: {list}.
Check each AC: implementing story identified, Dev Agent Record confirms, test covers it.
Check each PRD feature: story done, behavior matches description.
Write to {artifacts}/epic-{N}-functional-completeness-{date}.md
Print: DONE — ACs checked: N, Covered: N, Gaps: N, Discrepancies: N, Output: [path]
```

### Phase 8 — Issue triage and resolution

Collect counts from closure phase status lines. If Critical/High or gaps: new chat to read finding titles.
Present consolidated findings. **Ask for resolution plan.**

Critical/High → must fix. Undocumented drift → fix or doc update. AC gaps → implement or defer.
Fixes: new chat dev-story + qa-generate. Doc updates: new chat to update arch/PRD. Defers: new chat create-story; update sprint-status.yaml.

**Epic cannot close with unresolved Critical/High issues.**

### Phase 9 — Sign-off

Update sprint-status.yaml: epic → `done`, all stories `done`, retro `done`.
Report: sprints, stories, issues resolved/deferred, architecture/PRD updated.
