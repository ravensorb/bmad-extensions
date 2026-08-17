# Adaptive Parallelism — Design

**Date:** 2026-08-17
**Status:** Specced for later. Not scheduled, not started.
**Sub-project:** D. Depends on A (`2026-08-17-phase-gating-unification-design.md`) only for
A's correction of the `CLAUDE.md` paragraph that currently describes this as if it exists.

## Why this document exists now

`CLAUDE.md` documents an adaptive-parallelism model that is implemented nowhere:
`parallel_mode`, `parallel_ceiling`, and `safe_batch_size` appear in no `customize.toml` and are
computed in no step file, and `steps/execute/step-05-epic-loop.md:57` cites a "§15" that does
not exist. Sub-project A corrects that documentation to describe reality. This spec captures
the design so the intent is not lost, and records one insight that substantially shrinks the
work.

## Set expectations honestly: this does not reduce tokens

Parallelism is roughly **token-neutral in total**. It does not change how much work there is —
the same number of subagents load the same context either way. Running four epics concurrently
consumes four times the tokens per wall-clock minute at the same total cost.

The reasons to build it are **wall-clock** and **safety**, not cost. Two mechanisms do cost
extra tokens, and both should be stated plainly rather than discovered later:

- **Wasted concurrent work on failure.** When one epic goes BLOCKED mid-phase, siblings have
  already spent tokens that sequential execution would never have spent. This is the dominant
  real cost, proportional to how often runs fail mid-phase.
- **Staler calibration for siblings.** `step-05` §6 re-estimates remaining sprints after each
  sprint completes so calibration feeds forward. Concurrent epics cannot see each other's
  samples, so they estimate on older ratios. This costs estimate *quality*, not tokens.

Lock-contention retries and the orchestrator's own coordination context are marginal.

## What is already solved

`CLAUDE.md` defines `safe_batch_size` as "the count of provably-independent items (no shared
files, no cross-dependency, no same-node status contention)." Two of those three are already
handled, which is the key finding of this design:

| Independence requirement | Status |
|---|---|
| **No cross-dependency** | **Already solved.** `steps/plan/step-05-dependency-graph.md` §3 runs Kahn's algorithm over `depends_on` and emits `parallel: true` only for phases whose epics have no dependency on one another. The plan snapshot already carries this per phase. |
| **No same-node status contention** | **Already solved by the layout.** Sharding gives each epic its own directory, so epic-scoped writes touch only that epic's files. `CLAUDE.md` says so directly: "per-epic directories mean epic-scoped writes touch only that epic's files — no flock needed." The three genuinely shared append targets (`issues.yaml`, `events.jsonl`, `pm-calibration.yaml`) each already take `flock`. |
| **No shared files** | **Unsolved, and it is about source files, not state files.** Two dependency-independent epics can still modify the same application source file. |

So D is not "build an independence prover." It is "handle source-file contention, and add the
mode switch."

## The hazard that already exists

This is the part worth acting on. `step-05` §1 **already dispatches epics concurrently** —
`if parallel_flag=true AND len(epics) > 1`, up to `max_parallel_subagents` — with no file-level
independence check of any kind, into **one shared checkout**. Concurrent epic subagents editing
the same working tree can clobber each other's edits, and nothing detects it.

That risk is present today, at `max_parallel_subagents = 4` by default. D's most valuable
contribution is therefore not more parallelism — it is making the parallelism that already runs
safe.

## Design

### 1. Isolation over proof

Do not try to prove two epics touch disjoint files. Inferring a story's file surface before it
runs is unreliable, and asking authors to declare it adds discipline that will decay.

**Give each concurrently-dispatched epic its own git worktree.** File contention stops being a
thing to detect and becomes a thing that cannot happen. Each epic branches, works in isolation,
and merges on completion.

Costs and open questions, stated rather than glossed:

- Disk and setup time per worktree (~hundreds of ms plus a checkout).
- A merge step per epic, with real conflict potential when two epics genuinely did touch the
  same file — but now surfaced as a merge conflict a human can resolve, rather than a silent
  clobber.
- State lives under `{implementation_artifacts}/state/`, which is *inside* the repo. Two
  worktrees mean two copies of the state tree, which must not diverge. **This is the hardest
  open question in this spec** and must be resolved before implementation: either state stays
  in the primary checkout and worktrees reach into it by absolute path, or each worktree's state
  writes are merged back. The first is simpler and preserves `pm-status.py` as the single
  writer against a single tree; it needs `--state-root` to point outside the worktree, which it
  already supports since it takes an explicit path.

### 2. The mode switch

```toml
parallel_mode          = "auto"   # auto | adaptive | off
max_parallel_subagents = 4
parallel_ceiling       = 12
```

- `off` — force sequential. The escape hatch when something is wrong.
- `adaptive` — respect `max_parallel_subagents` as a hard bound.
- `auto` — size each batch as `min(max_parallel_subagents, parallel_ceiling, eligible_epics)`.

With independence already established by the plan's topological sort, `eligible_epics` is
simply the count of epics in the current parallel phase. The elaborate `safe_batch_size`
computation `CLAUDE.md` describes is not needed once isolation replaces proof.

### 3. Sprint-level parallelism is explicitly rejected

Sprints within an epic stay sequential. `step-05` §6 re-estimates remaining sprints after each
one so calibration feeds forward, and sprints in an epic frequently do depend on each other in
ways nothing declares. The wall-clock gain is not worth losing the feed-forward.

## Verification approach

Whoever implements this should plan for:

- A fixture with two dependency-independent epics that deliberately modify the same source
  file, run concurrently — asserting the result is a detectable conflict, never a silent
  clobber.
- `parallel_mode = "off"` producing strictly sequential dispatch.
- State integrity across concurrent epics: `verify --scope epic` passing for every epic
  afterward, and `issues.yaml` / `events.jsonl` / `pm-calibration.yaml` containing every
  expected entry with none lost to a race.
- Worktree cleanup on both success and failure paths, including a BLOCKED epic.

## Out of scope

- Sprint-level or story-level parallelism.
- Reducing token usage — see the expectations section; that is sub-projects B and C.
- Cross-epic file-conflict *prediction*. The design deliberately substitutes isolation.

## Prior art in this repo

The `Agent` tool used by the superpowers workflow already offers `isolation: "worktree"` for
exactly this reason, and its documentation notes the cost as "~200-500ms setup + disk per
agent" and advises using it only when agents mutate files in parallel and would otherwise
conflict. That is precisely this case, and it is a useful sanity check on the approach.
