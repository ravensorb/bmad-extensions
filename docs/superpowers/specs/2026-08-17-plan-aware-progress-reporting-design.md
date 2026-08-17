# Plan-Aware Progress Reporting — Design

**Date:** 2026-08-17
**Status:** Approved design, pending implementation

## Problem

There is no way to see progress against the plan during a long-running
`/l3io-pm-execute` run. Answering "which phase are we in, which epic is holding it
up, which sprint is live, and which stories are in flight" currently requires
running `pm-status.py show --epic <key>` once per epic and joining the results by
hand against the plan snapshot.

## Current state — three gaps

1. **No plan↔state join.** The plan snapshot (`{planning_artifacts}/plan-{date}-v{n}.yaml`)
   holds `phases: [{phase, parallel, epics, dependencies, estimate}]`. The state tree
   under `{implementation_artifacts}/state/` holds per-node status, estimates, and
   actuals. Nothing reads both, so phase-level progress is not computable.

2. **Roll-ups are per-epic only.** `rollup_sprint` and `rollup_epic` exist in
   `pm-status.py`, but the `show` command requires `--epic`. There is no project-wide
   walk, so the caller must already know which epics to ask about.

3. **No event history — the blocking gap.** `set-status` writes
   `node["updated_at"] = _now_iso()` and overwrites the previous value. State can
   therefore answer "last changed N hours ago" but never "spent 3h in dev, entered
   review at 10:42". Per-status dwell time, velocity, and "is this stuck?" — the
   actual questions of a long-running run — are not derivable from state alone.

Existing plumbing worth reusing: `_append_ledger` already appends timestamped lines,
and both `set-status` and `set-actual` already accept `--ledger`/`--scope`. The
facility is dead only because no step file ever passes those flags.

## Design

One builder, one normalized model, several thin renderers. The builder lives in
`pm-status.py`, which is already the only component permitted to resolve a node key
to a file path (see `references/status-files.md` §Addressing). No surface walks the
state tree itself.

### The progress model

A single function returns a plain dict. Every renderer and every surface consumes
this and nothing else.

```python
{
  "generated": "2026-08-17T10:42:31",
  "state_root": "<abs path>",
  "plan": {                       # null when no plan pointer was supplied or found
    "current_plan": "plan-2026-08-17-v2.yaml",
    "generated": "...",
    "readiness": "green",
    "phase_count": 3
  },
  "phases": [
    {
      "phase": 1,
      "parallel": true,
      "epics": ["E001", "E002", "E004"],   # membership, from the snapshot
      "dependencies": [],
      "epic_total": 3,                     # counted from `epics`, always complete
      "epic_done": 2,
      "epics_detail": [ <epic>, ... ]      # display list; archived filtered unless --all
    }
  ],
  "unplanned_epics": [ <epic>, ... ],      # in state, absent from every phase
  "totals": {
    "epics":   {"backlog": 1, "in-progress": 1, "done": 2},
    "sprints": {...},
    "stories": {...}
  },
  "flags": [ <flag>, ... ]                 # flat, all levels, for a summary block
}
```

Epic entry:

```python
{
  "key": "E001", "title": "Foundation", "status": "in-progress",
  "dir_status": "active",              # folder it lives in; mismatch = placement anomaly
  "sprint_count": 2, "story_count": 18,
  "by_status": {"done": 12, "in-progress": 1, ...},
  "estimate": {...}, "actual_totals": {...},
  "updated_at": "...", "dwell_hours": 6.4,
  "lock": {"session_id": "...", "claimed_at": "...", "ttl_minutes": 30, "stale": false},
  "flags": [...],
  "sprints": [ <sprint>, ... ]
}
```

Sprint and story entries follow the same shape at their level; story entries carry
`estimate`, `actual`, `updated_at`, `dwell_hours`, and `flags`, and no children.

**Reader safety.** `save_node` writes through `_atomic_dump` (temp file + rename), so
a reader polling during concurrent writes never observes a torn file. The builder
needs no locking. A node that fails to parse is skipped and recorded as a flag rather
than raising — a report must not die because one file is mid-migration.

### The event log

New append-only `{state_root}/events.jsonl`, a sibling of `issues.yaml` and
`pm-calibration.yaml` (both already shared append targets). One JSON object per line:

```json
{"ts":"2026-08-17T10:42:31","event":"status","node":"story","key":"E001-S02-004",
 "epic":"E001","sprint":"S02","from":"in-progress","to":"review","session":null}
```

`event` is `status` or `actual`. `from` is read off the node before the overwrite, so
no new bookkeeping is required. `session` is populated when an optional
`--session-id` is passed and null otherwise.

Two decisions, both deliberate:

- **The write is automatic, not flag-driven.** The path is derived from
  `--state-root` inside `set-status`/`set-actual`. The existing `--ledger` flag is
  precisely why the current ledger is dead: anything the orchestrator must remember
  to pass in prose eventually is not passed. This mirrors how calibration sampling
  was moved inside `set-actual` rather than left to orchestrator instructions.
  `--no-events` opts a single call out; a failed append warns on stderr and never
  fails the status write (same contract as calibration).
- **One project-level log, not per-sprint.** `CLAUDE.md` currently describes
  `{sprint|epic_root_dir}/progress.log`. Per-sprint files fragment the timeline and
  turn cross-epic velocity into a multi-file join. One log keeps the report a single
  read; volume is a few KB per epic.

Appends take `flock`, consistent with every other shared append target. The existing
`_append_ledger` uses a bare `open(..., "a")`; short single-line `O_APPEND` writes are
atomic on Linux in practice, but relying on that while every neighbouring writer locks
is an inconsistency worth closing.

`--ledger`/`progress` are retained unchanged for backward compatibility.

### Renderers

| Format | Output |
|---|---|
| `tree` | Indented terminal hierarchy: phase → epic → sprint → story, with progress bars, dwell times, and stuck markers |
| `json` | The model verbatim — what `--watch` and any future consumer eats |
| `md` | Markdown tables for the committed report file |

`--watch <secs>` re-renders `tree` on an interval. Polling a local directory tree is
cheap and the atomic writes make it correct; no daemon, no IPC.

### Surfaces

| Surface | Invocation |
|---|---|
| CLI | `pm-status.py report --state-root S [--plan P] [--format tree\|json\|md] [--out F] [--all] [--watch N]` |
| `/l3io-pm-help` | `progress` argument — reuses help's config resolution, layout detection, and `pm_status_present` fallback |
| `/l3io-pm-execute` | Live render at serialized points only (below) |
| `/l3io-util-doctor` | `stats` mode swaps its flat counts for the hierarchy, keeping backlog/calibration/anomaly sections |

`/l3io-pm-plan` is deliberately **not** a surface.

The command is read-only unless `--out` is passed. This is what lets `stats` — which
must not write — call the same code path.

#### Execute-loop render points

`step-05-epic-loop.md` dispatches **epics concurrently** within a parallel phase and
sprints sequentially within an epic. Several epic subagents printing trees at once
would interleave into noise, and subagent stdout is buried anyway (the contract there
is a one-line `DONE — [metrics]`). So the tree renders only where execution is
serialized:

| Point | Renders |
|---|---|
| Phase start / phase end (top-level orchestrator) | Yes — always serialized |
| Sprint boundary, single epic in flight | Yes |
| Sprint boundary, inside a parallel phase | No — event log only |
| Story boundary | Never — in-flight stories already appear in the tree |

Nothing is lost by suppressing: every transition still lands in `events.jsonl`, so
`--watch` in a second terminal gives full-resolution live detail during a parallel
phase while the run's own output stays legible.

The `md` report is regenerated at **sprint and epic closure boundaries** plus on
demand — not per transition, which would churn git on every story move and put
parallel subagents in contention over one file.

The `md` file is a view, never a source of truth. It carries a generated-by header
naming the command that produces it. This follows the stance already taken for
`plan-output-meta.yaml` ("never a second copy of the plan").

### Archived epics

Omitted from the tree unless `--all`. The builder still reads archived `epic.yaml`
files in order to count them: phase progress needs a true denominator, so
`Phase 1/3 ████████░░ 2/3 epics done` stays correct with zero archived rows shown.
Phase membership comes from the snapshot's `epics` list, which is authoritative for
what belongs to a phase regardless of where the directory currently sits.

### Stuck flags

Fixed thresholds, no configuration in this iteration — the calibration data needed to
tune them is what this view will generate.

| Level | Status | Threshold |
|---|---|---|
| Story | `in-progress` | 4h |
| Story | `review` | 4h |
| Story | `ready-for-dev` | none — waiting is normal |
| Sprint | `in-progress` | 24h |
| Epic | `in-progress` | 72h |

Epic-level staleness reuses the existing `_lock.ttl_minutes` check rather than
introducing a second definition; `check-lock` and `/l3io-pm-help` already flag stale
locks that way, and two competing definitions would eventually disagree.

### Degradation

Every one of these must produce useful output, not an error:

| Condition | Behavior |
|---|---|
| No `events.jsonl` (all existing projects) | Fall back to `updated_at` for dwell time; label it as an approximation |
| No plan pointer / no snapshot | Emit the state hierarchy with `plan: null` and no phase framing |
| Legacy state layout | Callers short-circuit to the existing migrate-state recommendation |
| `pm-status.py` not self-installed | `/l3io-pm-help` reads `epic.yaml` directly, as it already does |
| Unparseable node file | Skip, record a flag, continue |

## Testing

Extends `skills/_shared/tests/test-pm-status.py` (in-process `main()` runner against a
tempdir fixture). Written test-first:

- Builder: hierarchy assembly; archived omitted by default and present under `--all`;
  `epic_done`/`epic_total` correct while archived rows are hidden; `unplanned_epics`
  populated for state-only epics; `plan: null` path.
- Events: appended on `set-status` with correct `from`/`to`; appended on `set-actual`;
  suppressed by `--no-events`; append failure warns without failing the write;
  concurrent appends under `flock` lose no lines.
- Dwell/flags: threshold boundaries per level; `updated_at` fallback when no events;
  stale lock detection.
- Renderers: `json` round-trips; `tree` and `md` emit without raising on an empty
  tree, a plan-less tree, and a full tree.
- Read-only guarantee: `report` without `--out` creates and modifies no files.

## Out of scope

Burndown charts, HTML dashboards, cost projection, web UI, configurable thresholds.
`--format json` means any of these can be built later without touching the core.

## Related chores (no spec needed, mechanical)

1. **Delete `src/`.** Contains no tracked files — only two orphaned
   `__pycache__/pm-status.cpython-311.pyc` caches left behind by commit `1a23e74`,
   compiled from a pre-sharding `pm-status.py` under the long-gone skill name
   `l3io-pm-epic-execute`.
2. **Rename `l3io-util-cleanup` → `l3io-util-doctor`.** "Cleanup" describes about 3
   of its 15 modes; the default behavior is a diagnose-report-repair health check.
   Ships with a deprecation-forwarder skill at the old name, following the
   `bmad-editorial-review` → `bmad-review` precedent. Historical records
   (`CHANGELOG.md`, `docs/superpowers/plans|specs/*`) are left unrewritten.

## Files affected

**Shared source** (fans out to 3 PM skill payload copies via `npm run sync:scripts`):
`skills/_shared/pm-status.py`, `skills/_shared/tests/test-pm-status.py`,
`skills/_shared/status-files.md`, `skills/_shared/steps/execute/step-05-epic-loop.md`,
`skills/_shared/steps/sprint/step-03-dev-loop.md`,
`skills/_shared/steps/closure/{sprint,epic}-closure.md`,
`skills/_shared/steps/shared/step-00-activate.md`

**Per-skill:** `skills/l3io-pm-help/SKILL.md`, the renamed util skill's `SKILL.md` /
`module.yaml` / `customize.toml`, plus a new forwarder skill directory.

**Repo:** `.claude-plugin/marketplace.json`, `scripts/sync-shared-scripts.mjs`,
`.claude/commands/`, `README.md`, `CLAUDE.md`, `docs/getting-started.md`,
`docs/architecture.md`, `docs/l3io-util-reference.md`
