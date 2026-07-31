# Status File Layout Contract (split state)

Communicate all responses in `{communication_language}`.

This file is the single source of truth for **where** sprint/epic/story/backlog state lives
on disk. Load it at activation alongside `metrics-contract.md` and keep its rules in context
for every read, every write, and every node move. The metrics rules (what to capture) are
unchanged — this file only governs **which file** each node is written to and read from.

## The three files

State is split across three files in `{implementation_artifacts}/` (each created lazily — a
file that does not yet exist is treated as empty, not an error):

| Binding | File | Holds |
|---------|------|-------|
| `{status_active}` | `sprint-status.yaml` | `epics:` with `status: in-progress` only. Each carries its `in-progress` and `done` sprints (and all their stories). |
| `{status_backlog}` | `sprint-status-backlog.yaml` | `epics:` = not-yet-started work (shells for in-progress epics + whole backlog epics); `backlog:` = flat list of pending deferred issues — only `status: backlog` items; resolved or promoted items are removed from this list. |
| `{status_archived}` | `sprint-status-archived.yaml` | `epics:` with `status: done` — full subtree, moved here at epic close. |

All three share the **same node schema** as the legacy single `sprint-status.yaml` (epic →
sprints → stories, with `estimate`/`actual`/`completion_evidence` blocks). The only schema
additions are the consolidated `backlog:` item (see below) and the optional `depends_on`
fields (see [Dependency fields](#dependency-fields)). The split changes *placement*, not
field shape.

## Placement rule (the single source of truth)

- **Granularity = epic + sprint.** Stories always travel inside their owning sprint node;
  there is no story-level fragmentation. Once a sprint is in `{status_active}`, every one of
  its stories lives there too, whatever each story's individual status.
- An **epic** node lives in `{status_archived}` iff `status: done`; in `{status_active}` iff
  `status: in-progress`; in `{status_backlog}` iff `status: backlog`.
- For an **in-progress epic**, its `in-progress` and `done` sprints live in `{status_active}`
  under the epic node. Its not-yet-started (`backlog`) sprints live in `{status_backlog}`
  under an epic **shell** — `id`, `title`, `goal`, and a `sprints:` list of the backlog sprints only (no `estimate`, `actual`, or `status` fields) — so they stay locatable. A node appears in exactly one file at a time.
- The consolidated `backlog:` deferred-issue list lives only in `{status_backlog}`.

## Read resolution + auto-fallback (run once at activation)

Resolve in order — stop at the first matching case:

1. **Split layout detected** — if `sprint-status-backlog.yaml` OR `sprint-status-archived.yaml`
   exists in `{implementation_artifacts}/`:
   - If `sprint-status.yaml` also exists → bind `{status_active}` to it and proceed. A missing
     backlog or archived file is an empty set (not an error).
   - Else if `sprint-status-active.yaml` exists → rename it to `sprint-status.yaml`
     (auto-migrate old naming — content is unchanged), then bind `{status_active}` to the
     renamed path. Alert: "Renamed sprint-status-active.yaml → sprint-status.yaml
     (one-time naming migration)."
   - Else → `{status_active}` is absent (treat as empty, create lazily on first write).

2. **Legacy full-content file** — if only `sprint-status.yaml` exists (no backlog or archived
   files): perform the one-time split **inline** — rename `sprint-status.yaml` →
   `sprint-status.yaml.legacy` (never delete — it is the rollback), write active content to
   `sprint-status.yaml`, backlog content to `sprint-status-backlog.yaml`, archived content to
   `sprint-status-archived.yaml`, partitioning every epic/sprint per the placement rule above.
   This is the same partition the `l3io-util-cleanup split-status` mode performs; doing it here
   makes adoption automatic on first run.

3. **No state** → no files exist yet. Create files lazily as the first node of each kind is
   written.

Bind `{status_active}`, `{status_backlog}`, `{status_archived}` to the three paths.

**To locate a target epic/sprint:** search `{status_active}` first, then `{status_backlog}`.
A `done` epic (in `{status_archived}`) is normally not a target for new work; read it only
when a roll-up explicitly needs historical nodes.

## Move operations (who triggers what)

A "move" = remove the node from its source file and write it into the destination file
(preserving all fields). After every move, re-parse all touched files to confirm valid YAML.

| Trigger | Step | Move |
|---------|------|------|
| **Epic start** | epic-execute "Epic Planning" | Epic identity → `{status_active}` as `status: in-progress`. Its not-yet-started sprints remain in `{status_backlog}` under the epic shell. (If the epic was a whole `backlog` epic, split it: epic header → active, backlog sprints → shell.) If there are no not-yet-started sprints, no shell is created. |
| **Sprint start** | sprint-execute "Sprint Scope" | Move that sprint node from the `{status_backlog}` epic shell → the epic node in `{status_active}`, set `status: in-progress`. Remove the shell once its `sprints:` list is empty. |
| **Sprint close** | sprint-closure sign-off | **No file move** — the sprint stays `done` in `{status_active}` until its epic closes (archive is epic-close-only). |
| **Epic close** | epic-closure sign-off | Do all metric/calibration reads from `{status_active}` **first**, then move the whole epic node (all done sprints + stories) `{status_active}` → `{status_archived}`. Remove any leftover shell for that epic from `{status_backlog}`. |
| **Issue triage** | sprint-closure / epic-closure triage | Append deferred items to the `backlog:` section of `{status_backlog}` (tagged with `epic`/`sprint`) — **not** a per-epic nested `backlog:` array. Items are appended only; nothing is removed from the sprint node. |
| **Backlog item promoted to story** | sprint planning / triage | Remove item from `backlog:` list in `{status_backlog}`. Create a story node in the target sprint in `{status_active}` with `title` and `classification` pre-populated, `status: backlog`. The story archives with its epic at epic close. |
| **Backlog item resolved inline** | sprint work / closure triage | Remove item from `backlog:` list in `{status_backlog}`. Items are deleted when resolved — never kept with a resolved status. |

## Consolidated backlog item schema

The `backlog:` list lives at the top level of `{status_backlog}` (one flat list across all
epics). Key format: `BL-E{epic}-{nn}` where both epic and nn are zero-padded two-digit values (e.g. `BL-E01-01`, `BL-E02-37`). For repo-global items not tied to a specific epic (e.g. harvest-debt code markers), use `BL-E00-{nn}`.

**Lifecycle:** Only `status: backlog` items appear in this list. When an item is resolved inline or promoted to a story, it is **removed** from the list — done items are never kept with a resolved status.

**Promotion to story:** Remove the item from `{status_backlog}`. Create a story node in the target sprint in `{status_active}` with `title` and `classification` pre-populated from the backlog item, `status: backlog`. The story then follows the normal story lifecycle and archives with its epic at epic close.

```yaml
backlog:
- key: BL-E01-01                         # BL-E{epic}-{nn}, both zero-padded
  epic: '01'                             # zero-padded epic id; '00' for repo-global items
  sprint: '02'                           # zero-padded sprint id; '' for an epic-level deferral
  title: 'Issue title'
  source: 'adversarial (ADV-L-01)'       # review phase + finding id
  severity: Low
  status: backlog
  description: 'One-sentence description of the deferred issue.'
```

## Dependency fields

Two optional `depends_on` fields extend the node schema. Both are written during story/planning phases and read by `l3io-pm-plan-execution` to produce a phased parallel execution plan. They have no effect on the sprint/epic execution skills.

**Epic-level** — list of epic keys that must reach `status: done` before this epic starts:

```yaml
epics:
  - key: 'E03'
    depends_on: ['E01', 'E02']   # E03 cannot start until E01 and E02 are done
```

**Story-level** — list of globally-unique story keys (cross-epic keys are supported) that must be `status: done` before this story starts. When a story depends on a story in a different epic, `l3io-pm-plan-execution` rolls this up to an epic-level edge:

```yaml
stories:
  - key: E03-S01-001
    depends_on: ['E01-S02-003']  # cross-epic: E01 must complete before E03 starts
```

Both fields default to `[]` (empty — no dependencies) and may be omitted entirely.

## Notes

- A node is in exactly one of the three files at any time; never duplicate it. Moves are
  remove-then-write.
- Empty files are valid (treat a missing file as empty); only write a file once it has at
  least one node, to avoid littering empty YAML.
- The split is one-way. To re-merge, the `sprint-status.yaml.legacy` rollback from the
  initial split is the recovery path; there is no automated re-merge.
