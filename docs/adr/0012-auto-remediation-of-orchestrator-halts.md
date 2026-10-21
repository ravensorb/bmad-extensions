# ADR-0012 — Orchestrator halts with a determinable remedy perform it

**Status:** Accepted
**Date:** 2026-10-21
**Design:** `docs/superpowers/specs/2026-10-21-auto-remediation-design.md`
**Contract:** `skills/_shared/auto-remediation.md`, delivered to `references/auto-remediation.md` in `l3io-execute`, `l3io-plan` and `l3io-sync`

## Context

`l3io-execute` and `l3io-plan` stop at a `BLOCKED:` line when they cannot proceed. Of the 23
column-0 `BLOCKED:` sites in the shared step files, several already name their own remedy —
`/l3io-doctor migrate-state`, `/l3io-plan`, `/l3io-doctor bootstrap-state` — and stop so the
user can type it and start the run over. The user learns what the project needed only by being
interrupted, and the run does not resume where it stopped.

The cost of automating this is not uniform. Some remedies are mechanical and reversible. Others
decide something that is the user's alone, or reach across a boundary the tooling cannot see.
Without a recorded rule, each new halt would be argued case by case, and a later task could
convert one that must never be converted.

## Decision

**When a halt has a remedy we can determine and perform, perform it, report what was done, and
continue the run.** Halt only when no remedy exists, when performing one would decide something
that is the user's to decide, or when the remedy has already been tried.

This follows ADR-0004: the agent acts and confirms after the edit lands. Every remediation
prints one line before and one after, and a remediation that cannot report what it changed does
not qualify.

### Nine sites remediate

| Site | Remedy |
|---|---|
| artifact-only stories (story `.md` files, no state YAML) | `/l3io-doctor bootstrap-state` |
| four plan-pointer sites in `step-03-load-plan` (pointer absent, absent with snapshots, readiness RED, target missing) | `/l3io-plan` |
| legacy state layout | `/l3io-doctor migrate-state` |
| `implementation_artifacts` moved away from existing state | repoint `_bmad/custom/config.toml`, recording the previous value |
| gitignored state root | append negation lines to the work-tree `.gitignore` that `git check-ignore -v` names |
| multiple state layouts | **conditional** — move the legacy tree to `_bmad/state.superseded` only when every legacy epic key is also in the sharded tree |

The last is the only remedy that depends on evidence. It compares epic keys alone: sprint or
story divergence inside a shared epic key is not examined. A legacy-only epic key, a legacy
entry that is not an epic key, or a flat legacy file leaves it a halt that prints the keys that
differ.

### Fourteen sites halt

Eleven are ordinary halts with no single remedy: external dependencies, user input errors,
ordering facts, aggregate findings, content authoring, a broken install, unknown state
corruption, platform detection. Three are absolute.

### Three refusals are absolute

`absolute`, and the `absolute` half of `auto+absolute`, may never be removed by a later task.

1. **Another session's epic lock** (two sites: `step-02-scope-resolve`, `step-05-epic-loop`).
   Breaking a lock another session holds is data loss across a boundary `flock` cannot see.
   Lanes exist so that two developers work in two clones; a lock held by one of them is the
   only signal the other has, and the orchestrator cannot tell a dead holder from a live one.
2. **Credentials** (`step-02-detect-platform`, authentication unavailable). The package never
   touches them. No remedy is conditional on the credential being benign, because the
   orchestrator cannot establish that.
3. **Accepting plan risk.** The RED-readiness halt has two routes. Route 1, re-plan, is
   remediable. Route 2 — set `readiness:` to amber — is a risk acceptance, and accepting risk on
   the user's behalf lets an incomplete plan execute while the record says it was fine. The site
   is therefore `auto+absolute`: no remediation writes `readiness:`.

### One attempt per distinct issue per run

The remedy is recorded **before** it runs. If the same halt recurs after its own remedy has run,
it becomes a hard halt naming what was tried. There is no second attempt under any condition.
Four remedies re-run `/l3io-plan`, which carries halts of its own; unbounded, a RED plan
re-plans into RED forever.

The budget is **per site id, not per run**: a tree can be both legacy-layout and gitignored, and
each remedy runs once in the same activation. The one exception is that remedies sharing **one
command and one underlying cause share a single attempt**. The four plan-pointer sites derive
their symptom from one `/l3io-plan` run's output, so a second symptom after a rebuild cannot be
independent of the first; a second run over the same state regenerates the same result. They
share the in-run flag `{plan_rebuilt}`, set before the first run.

Every remediable site has three outcomes — cleared, succeeded but persists, and failed — and
only the first continues. Failure and persistence both halt, naming the original condition and
what the remedy reported.

### The attempt record is memory, not a file

The bound is per run, a run is one orchestrator invocation, and all nine sites are inline in
that invocation. `shared/step-00-activate.md`, `plan/step-02-readiness-check.md` and
`execute/step-03-load-plan.md` are orchestrator-level; `l3io-execute` dispatches *sprint*
subagents, and none of these sites is in that context. A file would outlive the run and
suppress a remedy the next run legitimately needs.

**This is void if a site ever moves into a dispatched subagent.** The package's context
boundary passes state through disk, never through in-memory hand-off, so a dispatched subagent
cannot see the orchestrator's record and would attempt again. The record must then become a
file.

### The inventory is enforced

`check:docs` check 36 compares the two tables in the contract to the `BLOCKED:` lines in
`skills/_shared/steps/**`: every site classified, every declared remedy present in its step
file, every row's `Class` valid. A task that converts a halt moves its row from `Halts` to
`Remediable` in the same commit.

The inventory is of 23 sites at column 0. One indented genuine halt,
`closure/epic-closure.md` (`{epic_key} — {N} story/ies blocked pending external resolution`),
is not inventoried, so 23 is not every halt in the package.

## Consequences

- A project whose stories exist only as `.md` files, whose plan pointer is stale, whose layout is
  legacy, or whose state root is ignored, proceeds in one invocation, and the run reports what
  it changed.
- Every remedy is reversible or non-destructive: `migrate-state` preserves the original as
  `.legacy`; the repoint records the previous value beside the new; the legacy tree moves
  rather than being deleted; bootstrap writes no artifact.
- Re-entry costs nothing extra. `/l3io-plan` run from inside `l3io-execute` does not repeat its
  setup pointer, because `pm-status.py notice` records a key at most once ever per project.
- A halt that was added without a table row, or converted without moving it, fails CI.

## Evidence toward ADR-0001's "revisit at 10,000"

The natural home for the attempt record was a remediation-record verb in `pm-status.py`. It was unavailable:
`skills/_shared/pm-status.py` is at exactly 10,000 lines, the cap ADR-0001's 2026-10-03
amendment set and check 12 enforces. That is the fourth change the cap has blocked or
redirected:

1. **`subagent_models()`** in the v7 bridge — dropped; spec
   `2026-10-16-bmad-v7-layer-design.md` §8.2.
2. **A one-line timezone-awareness guard in `dispatch_window`** — a safety fix, not a feature,
   in the same spec's §8.2.
3. **The `pm-status.py remediate` verb** — this decision's own attempt record.
4. **The `check 12 boundary: exactly 10,000 lines passes` test**, which could not run at all
   once the file reached the cap: its padding helper asserted the file was still below the
   target and failed before exercising check 12 (repaired in `92e78bd`). The one state the
   project is actually in was the one state the suite had stopped checking.

ADR-0001 says raising the number again "becomes a decision made on evidence rather than a
default, and it should be argued here before it is taken." Four independent changes, one of
them a safety fix and one a test of the cap itself, are that evidence. This ADR does not take
the decision; it records that the revisit is due.
