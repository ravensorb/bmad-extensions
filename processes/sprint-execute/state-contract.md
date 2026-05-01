# Sprint Execute — State Contract

All state passes through disk. No phase should depend on another phase's in-memory output. This makes each phase independently restartable and enables fresh-context subagent delegation.

## Files written per phase

| Phase | Writes | Other phases read |
|-------|--------|-------------------|
| Story prep | `{artifacts}/{story-key}.md` | Dev, QA, Fix, Closure |
| Dev | Story file — tasks `[x]`, Dev Agent Record, File List | Code review, QA, Fix, Closure |
| Code review | Story file — Dev Agent Record append | Orchestrator (severity counts) |
| QA | Story file — Dev Agent Record + test files | Orchestrator (pass/fail) |
| Fix | Story file — Dev Agent Record fix notes | Orchestrator, next QA run |
| Retrospective | `{artifacts}/epic-{N}-retro-{date}.md` | Adversarial, Red Team |
| Adversarial review | `{artifacts}/sprint-adversarial-{date}.md` | Orchestrator triage |
| Red team | `{artifacts}/sprint-redteam-{date}.md` | Orchestrator triage |

## sprint-status.yaml

The orchestrator's primary tracking file. Located at `{artifacts}/sprint-status.yaml`.

### Story status values (in order)
```
backlog → ready-for-dev → in-progress → review → done
```

### Epic status values
```
backlog → in-progress → done
```

### Retrospective status values
```
optional ↔ done
```

### Example entry
```yaml
development_status:
  epic-15: in-progress
  15-0-client-project-hierarchy: done
  15-1-maturity-scoring-model: in-progress
  15-2-evidence-traceability: backlog
  epic-15-retrospective: optional
```

## Story file sections (required)

Every story file must have these sections. Dev and QA phases write into them.

```markdown
## Status
[backlog | ready-for-dev | in-progress | review | done]

## Acceptance Criteria
- [ ] AC1: ...

## Tasks / Subtasks
- [ ] Task 1
  - [ ] Subtask 1a

## Dev Agent Record
### Debug Log
### Completion Notes
### Fix Log (added during fix loop)

## File List
[all files created or modified by this story]
```

## Phase output status line

Every subagent/session **must print a structured status line** as its last output. The orchestrator reads this to determine next action without loading the full context.

### Format
```
DONE — [brief metrics]
BLOCKED: [one-line reason]
FAILED: [one-line reason]
```

### Examples by phase
```
DONE — Tasks: 8/8 complete, File List: 12 files
DONE — Critical: 0, High: 2, Medium: 3, Low: 4
DONE — Tests: 14 written, 14 passing
DONE — Retro file: _bmad-output/implementation-artifacts/retros/epic-15-retro-2026-05-01.md, Action items: 6
BLOCKED: Missing architecture.md — cannot run drift analysis
FAILED: 3 tests still failing after 3 fix iterations — escalate
```

## Orchestrator state (in-memory only, not persisted)

The orchestrator holds **only**:
- Story key list (`[15-0, 15-1, 15-2, ...]`)
- Current position in the list
- Fix iteration counter for the current story
- Status-line summaries from completed phases (strings, not file contents)
- List of deferred story keys

Everything else comes from disk reads at decision points.
