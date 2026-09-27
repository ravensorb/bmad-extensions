# Phase Gating Unification — Design

**Date:** 2026-08-17
**Status:** Approved design, pending implementation
**Sub-project:** A of three (C shipped; D specced separately in
`2026-08-17-adaptive-parallelism-design.md`)

## Problem

Phase gating is defined in three places that disagree, the fix-loop cap is hardcoded
identically for a broken API contract and a typo, and two pieces of gating machinery are dead.

None of this is currently *breaking* a run — that was verified, and an earlier claim to the
contrary was wrong (see "What is not broken" below). It is a maintenance hazard and a token
cost, not a correctness bug.

### Three definitions of `{skip_phases}`

| Source | Defines | Role |
|---|---|---|
| `steps/shared/step-01-classify-work.md` §4 | tech-AC gate, arch gate, adversarial, red team, UX, ATDD | Binds `{skip_phases}` first |
| `steps/execute/step-05-epic-loop.md:141-145` | adversarial, red team, arch drift, clean release, UX | **Recomputes and overwrites it** |
| `steps/closure/sprint-closure.md` §8 | the 7×4 phase table | What closure actually reads |

### What is not broken

Verified by tracing consumers, not by comparing tables:

- `{skip_phases}` has exactly five consumers, all closure phases in `closure/sprint-closure.md`.
- For DOCS and CONFIG, `step-05`'s list and the §8 table **agree**. The correct phases skip.
- The three entries `step-05` omits never flow through `{skip_phases}` at all: the story
  technical-AC gate is gated on `{work_type}` at `steps/sprint/step-02-story-prep.md:10`, the
  epic arch gate at `steps/execute/step-04-arch-gate.md:11-12`, and ATDD has no consumer.

So the defect is: one variable computed twice from two different definitions, plus a table
listing phases that do not flow through it. A future edit to one definition and not the other
would become a real bug.

### The fix-loop cap is the largest multiplier and is not work-type aware

Hardcoded `10` in three places — `steps/sprint/step-03-dev-loop.md:51`,
`steps/closure/sprint-closure.md:38`, `steps/closure/epic-closure.md:35`. Identical for a
Terraform variable rename and a documentation typo. A 10-iteration autonomous fix loop on prose
is the single most disproportionate cost in the system.

### Dead machinery

- **ATDD.** `step-01` computes whether to skip it and shell-checks whether it is installed
  (lines 70-71), but **no step file ever invokes it**. `CLAUDE.md:166` advertises
  `bmad-testarch-atdd` as a working optional dependency, which is false.
- **Adaptive parallelism.** `CLAUDE.md` documents `parallel_mode`, `parallel_ceiling`, and
  `safe_batch_size` with the formula
  `effective = min(max_parallel_subagents, parallel_ceiling, safe_batch_size)`. None of the
  three is defined in any `customize.toml` or computed in any step file. `step-05:57` cites
  "§15 adaptive parallelism" — the execute `SKILL.md` has three `##` sections, so the
  reference dangles.

## Design

### 1. One matrix, in `step-01-classify-work.md`

`step-01` becomes the single source of truth. It runs first, already owns `{work_type}`
classification, and `{skip_phases}` is its output.

The matrix gains an **Enforced by** column, because two different mechanisms are in play and
conflating them is what produced the current confusion:

| Phase | CODE | DOCS | CONFIG | MIXED | Enforced by |
|---|---|---|---|---|---|
| Retrospective | run | run | run | run | always runs |
| Clean release review | run | skip | run | run | `{skip_phases}` |
| Adversarial analysis | run | skip | skip | run | `{skip_phases}` |
| Red team (`l3io-sec`) | run | skip | skip | run | `{skip_phases}` + installed check |
| UX review | run | **skip** | skip | run | `{skip_phases}` + installed check + UI-facing stories |
| Architectural drift | run | skip | run | run | `{skip_phases}` + installed check |
| Issue triage | run | run | run | run | always runs |
| Story technical-AC gate | run | skip | skip | run | `{work_type}` at `step-02-story-prep.md` |
| Epic arch gate | run | skip | skip | run | `{work_type}` at `step-04-arch-gate.md` |

**Phases enforced at their own step are deliberately not folded into `{skip_phases}`.** A
`{work_type}` check is self-contained; a malformed `{skip_phases}` string would silently
disable a gate. Keeping the two mechanisms distinct — and labelling which is which — costs one
table column and removes a whole class of silent failure.

### 2. `step-05` stops recomputing

Delete the recompute at `step-05-epic-loop.md:141-145`. It passes through the `{skip_phases}`
that `step-01` bound. Nothing else changes about dispatch.

### 3. `sprint-closure.md` §8 drops its table

Replace the 7×4 table with a pointer to `step-01`'s matrix and the existing instruction to skip
phases listed in `{skip_phases}`. Keeping an "illustrative" copy would reintroduce exactly the
duplication being removed.

### 4. UX review no longer runs on DOCS

The §8 table currently runs it. Decision taken: documentation does not need it. This takes DOCS
closure from three phases to two (retrospective, issue triage), on top of the existing
skips.

Note the phase already carries two further gates of its own —
`bmad-ux-review` installed, and the sprint having UI-facing stories
(`sprint-closure.md:52`) — so this change affects only DOCS sprints that would otherwise have
passed both.

### 5. Work-type-aware, configurable fix-loop cap

Replace the three hardcoded `10`s with a setting in each PM skill's `customize.toml`:

```toml
max_fix_iterations          = 10   # CODE and MIXED
max_fix_iterations_non_code = 3    # DOCS and CONFIG
```

Bind `{max_fix_iterations}` at `step-01` alongside `{work_type}` — the same step that already
knows which class the work is — and use that binding at all three sites.

**One cap per work-type class, applied at all three sites.** Not separate story-versus-closure
caps: that would be four knobs for a distinction nothing currently needs. If closure turns out
to want its own value, add it then.

### 6. Remove the dead ATDD gating

Delete the ATDD row from the matrix and the installed-check at `step-01:70-71`, and correct
`CLAUDE.md:166` to stop advertising `bmad-testarch-atdd` as an optional dependency.

If ATDD scaffolding is wanted, that is a feature needing its own spec — an unused install check
is not a step toward it, it is just a check that always answers a question nobody asks.

### 7. Document parallelism honestly, and fix the dangling reference

In scope here (implementation is sub-project D):

- Rewrite the `CLAUDE.md` adaptive-parallelism paragraph to describe what exists —
  `max_parallel_subagents` bounding concurrent epics within a parallel phase, sprints always
  sequential within an epic — and state plainly that `parallel_mode`, `parallel_ceiling`, and
  `safe_batch_size` are **not implemented**, with a pointer to D's spec.
- Fix `step-05:57` so it no longer cites a nonexistent §15.

### 8. Restore the `verify` routing row (carried from C)

Sub-project C's fix wave replaced a correct routing-table row with a less correct one, on the
strength of a review finding that turned out to be wrong. `status-files.md` §7 contains a
subsection titled "`verify` — two different checks behind one subcommand", and §7 line ~101
states "Activation depends on this distinction: it always runs `verify --scope epic`
(structural)". `metrics-contract.md` §5 explicitly defers to §7 for that case.

Add back a row routing a structural `verify --scope epic` failure to `status-files.md` §7,
keeping the `metrics-contract.md` §5 row C added — that one was a genuine improvement.

## Expected effect

For a DOCS sprint: closure drops from three phases to two, and the fix-loop ceiling drops from
10 to 3 at each of three sites. The per-story dev loop's ceiling is where this bites hardest,
since it applies per story rather than once per sprint.

Gating correctness is unchanged — the same phases skip today, just decided in one place instead
of three.

## Verification

1. `grep` proves exactly one computation of `{skip_phases}` remains in `skills/_shared/`.
2. Every phase name in `step-01`'s matrix that is marked `{skip_phases}`-enforced appears in
   `closure/sprint-closure.md`'s phase sections, and vice versa — no orphan on either side.
3. No hardcoded `10` remains as a fix-loop cap; all three sites read `{max_fix_iterations}`.
4. `grep` finds no surviving reference to `parallel_mode`, `parallel_ceiling`, or
   `safe_batch_size` that presents them as available, and no dangling `§15`.
5. `grep` finds no surviving ATDD gating machinery.
6. The restored `§7` routing row resolves, and all other routing anchors still do.
7. `npm run check:scripts` clean; 425 tests pass. **No test covers prose**, so the suite is a
   regression guard on `pm-status.py` only — items 1-6 are the real evidence.

## Out of scope

- Implementing adaptive parallelism (sub-project D).
- Wiring up ATDD.
- Fixing `steps/sprint/step-02-story-prep.md:74`, which calls `set-estimate` without
  `--fix-factor`/`--scope-ratio` and so permanently pins `provenance: legacy`, defeating the
  calibration scope-versus-fix split. Real, pre-existing, and a behavioral change to the
  calibration pipeline — it needs its own spec.
- Token budget enforcement (sub-project B).

## Files affected

**Canonical sources** (fan out to three PM skill payload copies via `npm run sync:scripts`):

- `skills/_shared/steps/shared/step-01-classify-work.md` — the matrix, the
  `{max_fix_iterations}` binding, ATDD removal
- `skills/_shared/steps/execute/step-05-epic-loop.md` — drop the recompute, fix `§15`
- `skills/_shared/steps/closure/sprint-closure.md` — drop the table, UX on DOCS, cap
- `skills/_shared/steps/closure/epic-closure.md` — cap
- `skills/_shared/steps/sprint/step-03-dev-loop.md` — cap
- `skills/_shared/steps/shared/step-00-activate.md` — restore the `§7` routing row

**Per-skill (not generated):** `customize.toml` in `l3io-pm-execute`, `l3io-pm-plan`,
`l3io-pm-sync`, `l3io-pm-help`

**Docs:** `CLAUDE.md` (parallelism paragraph, ATDD optional-dependency claim, fix-cap
description), `docs/l3io-pm-reference.md` (the §8 phase table and the fix-loop caps it
documents)
