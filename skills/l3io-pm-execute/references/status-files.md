# Status File Layout Contract (new state layout)

Communicate all responses in `{communication_language}`.

This file is the single source of truth for **where** sprint/epic/story/backlog state lives
on disk. Load it at activation alongside the metrics contract and keep its rules in context
for every read, every write, and every node move.

## File locations

All l3io-pm state lives under `{project-root}/_bmad/`. The `{implementation_artifacts}/`
directory holds only developer-facing artifacts (stories, tests, closure reports, ADRs).

| File | Purpose | Grows? |
|------|---------|--------|
| `_bmad/state/active/E{nnn}-status.yaml` | One file per active epic (`status: in-progress`). Contains ALL that epic's sprints (backlog, in-progress, done) and all their stories. | Bounded by epic scope |
| `_bmad/state/sprint-status-planned.yaml` | Future epics: `status: backlog` or `status: deferred`. Contains `depends_on` edges and full sprint/story subtrees. | Shrinks as epics start |
| `_bmad/state/sprint-status-issues.yaml` | Deferred issues flat list (`BL-E{nnn}-{nnn}`). Only `status: backlog` items — resolved items removed. | Grows; items removed when resolved |
| `_bmad/state/sprint-status-archived.yaml` | Done epics — full subtree moved here at epic close. Append-only. | Grows forever |

Planning artifacts (plan snapshots, readiness reports, elaboration summaries) live in
`{planning_artifacts}/`. Implementation artifacts (story files, tests, closure, ADRs)
live in `{implementation_artifacts}/epic-{nnn}/`.

## Key schema

- Epic key: `E{nnn}` (3-digit zero-padded string, e.g. `"E001"`)
- Sprint key: `S{nn}` (2-digit zero-padded string, e.g. `"S01"`)
- Story key: `E{nnn}-S{nn}-{nnn}` (globally unique, e.g. `"E001-S02-003"`)
- Backlog item key: `BL-E{nnn}-{nnn}` (e.g. `"BL-E001-001"`; `BL-E000-{nnn}` for repo-global)

Node fields use `key:` (not `id:`) in all new files.

## Placement rule

A node lives in exactly one file at any time. Never duplicate a node.

- Epic `status: in-progress` → `_bmad/state/active/E{nnn}-status.yaml`
- Epic `status: backlog` or `status: deferred` → `_bmad/state/sprint-status-planned.yaml`
- Epic `status: done` → `_bmad/state/sprint-status-archived.yaml`
- All sprints of an active epic (regardless of sprint status) → same active file as their epic
- Issues (deferred) → `_bmad/state/sprint-status-issues.yaml`

## Ownership lock

When `l3io-pm-execute` claims an epic, it writes a `_lock` block to the top of
`_bmad/state/active/E{nnn}-status.yaml`:

```yaml
_lock:
  session_id: "claude-session-abc123"
  claimed_at: "2026-08-13T14:30:00Z"
  ttl_minutes: 30
```

Check before claiming:
```bash
pm-status.py check-lock --file _bmad/state/active/E001-status.yaml --session-id {session_id}
# Exit 0 = free; Exit 5 = held by another session within TTL
```

## Move operations

| Trigger | Source | Destination |
|---------|--------|-------------|
| Epic start | `sprint-status-planned.yaml` epic node | New `active/E{nnn}-status.yaml` (flock on planned during removal) |
| Sprint start | Sprint node in active file (status: backlog) | Same file, status → in-progress |
| Sprint close | Sprint node in active file | Same file, status → done (no move) |
| Epic close | `active/E{nnn}-status.yaml` | Appended to `sprint-status-archived.yaml` (flock); active file removed |
| Issue deferred | New issue | Appended to `sprint-status-issues.yaml` |
| Backlog promoted | Issue in `sprint-status-issues.yaml` | Removed; story node created in active sprint |

## Shared file concurrency

`sprint-status-planned.yaml` and `sprint-status-archived.yaml` require flock-protected
writes. Always pass `--flock` to `pm-status.py set-status` or `set-actual` when writing
to these two files:

```bash
pm-status.py set-status --file _bmad/state/sprint-status-planned.yaml \
  --epic E003 --status in-progress --flock
```

## Read resolution at activation (step-00-activate.md)

Run once at startup:

1. If `_bmad/state/` exists → use new layout (this file).
2. If `{implementation_artifacts}/sprint-status.yaml` exists and `_bmad/state/` absent →
   legacy layout detected. Run `l3io-util-cleanup migrate-state` or alert user.
3. If nothing exists → first run; create `_bmad/state/active/` lazily on first write.

Bind at activation:
- `{bmad_state_root}` → `{project-root}/_bmad/state`
- `{bmad_active_root}` → `{project-root}/_bmad/state/active`
- `{bmad_planned_file}` → `{project-root}/_bmad/state/sprint-status-planned.yaml`
- `{bmad_issues_file}` → `{project-root}/_bmad/state/sprint-status-issues.yaml`
- `{bmad_archived_file}` → `{project-root}/_bmad/state/sprint-status-archived.yaml`

## Dependency fields

`depends_on` on an epic node: list of epic keys that must be `status: done` before this
epic can start. Lives in `sprint-status-planned.yaml`; read by `l3io-pm-plan` to build the
execution graph.

`depends_on` on a story node: list of globally-unique story keys (`E{nnn}-S{nn}-{nnn}`)
that must be `status: done` before this story starts. Lives in the file that owns the story's
epic.

`l3io-pm-plan` validates all referenced keys exist and detects cycles before writing the plan.
