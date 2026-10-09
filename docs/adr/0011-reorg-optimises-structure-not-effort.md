# ADR-0011 — Reorg optimises dependency structure, not effort

**Status:** Accepted
**Date:** 2026-10-09
**Supersedes:** the primary objective stated in `docs/superpowers/specs/2026-10-09-plan-reorg-design.md` §2

## Context

`/l3io-plan reorg` shipped in 3.3.0 with its primary objective stated as *minimise the critical
path* — the longest `depends_on` chain weighted by `elapsed_hours` — and total effort named as a
guardrail. Implementation and use surfaced three problems with that, each independently
sufficient.

**Reorg cannot change effort.** It moves stories between sprints and epics. It never makes work
smaller, never splits a story, never re-estimates one. The spec already conceded this in passing
— *"a reorg that cuts the critical path has not made the work smaller; it has made it more
parallel"* — without following the concession to its conclusion. The one way a reorg moves
effort is second-order: `sprint.estimate = Σ stories + closure band + orchestration band`, so
changing how many sprints and epics exist changes how many closure bands are paid. That is
overhead, not work.

**The effort data is usually absent exactly when a plan is cheapest to reshape.** A plan is
normally reorganised before everything is estimated. The analyzer's own test said so. So the
primary objective degraded to nothing on precisely the plans that most needed it.

**Effort is a guess where structure is a fact.** `depends_on` is declared about the work.
`elapsed_hours` is a base band times a calibration ratio — two inferences deep, and on a
cold-start project both are priors. Optimising hard on the softer number is backwards.

A fourth problem was mechanical: with reorg weighting a critical path and `step-06` printing
one, a plan run could report the critical path twice, computed at different granularities, and
disagree with itself.

## Decision

**Reorg's objective is the dependency structure it can actually change. Effort is reported as
an impact, never pursued as a goal.**

Concretely:

1. **The two `warn` findings are the two things a reorg can act on** — `cross-epic-coupling` and
   `unbacked-cross-epic-dependency`. Moving a story into the epic its dependencies live in
   removes a crossing edge. That is the lever.
2. **`dependency-chain` is measured in hops, not hours, and is `info`.** A reorg never edits
   `depends_on`, so **no move it can make shortens the chain**. It is reported as context for a
   proposal, never as its target. Hops also serve the spec's stated goal — *"reduce the cost of
   discovering a problem late"* — more directly than hours: each hop is a handoff where a wrong
   assumption propagates.
3. **`sprint-imbalance` is demoted to `info`.** Still measured and shown, never a driver.
4. **No weighted critical path is computed by reorg at all**, which removes the
   reported-twice-and-disagreeing failure.

## Consequences

**A reorg proposal can no longer say "this saves eleven hours."** It says "this removes three
serialisation points." That is a less satisfying headline and a more honest one — the hours
claim was never something the tool could stand behind, because the move set cannot produce it.

**Reorg's check can run before estimation.** Structural findings need only `depends_on`, so the
shape check moves to directly after the dependency graph is built — before a user pays for
estimation and a snapshot of a shape they are about to change. This is the direct practical
benefit of the decision.

**Treating effort as the objective would have made retirement the highest-scoring move.**
Deleting scope reduces total effort more than any regrouping can. An objective that rewards it
is the wrong incentive to hand this feature, and the analyzer's refusal to recommend retirement
— `isolated-story` is a `question`, never a retirement signal — was holding that line against
the objective rather than with it.

**Sprint load still matters, and now belongs to the balancing pass.** That pass runs after
estimation, where the data exists, with a move set constrained by the structure this pass
produced. `sprint-imbalance` is its input.

## Alternatives considered

**Keep the weighted critical path as the objective, and skip reorg when estimates are absent.**
Rejected: it makes the feature unavailable precisely when it is most useful, and it does not fix
the deeper problem that no move changes the chain.

**Weight the chain by story count rather than hours.** Rejected as a distinction without a
difference — it is still a measure of something a reorg cannot move, dressed as a target.

**Keep effort as a guardrail with a threshold.** Rejected: a guardrail that cannot be breached
by any legal move is not a guardrail. Reorg's effect on effort runs through closure and
orchestration bands only, which is better reported as an impact than policed as a bound.

## Amendment path

If a future reorg gains a move set that *can* change effort — splitting a story, merging two,
re-classifying one — this decision must be revisited, because its entire argument rests on the
move set being pure re-placement. Record that as an amendment here rather than reopening the
objective silently.
