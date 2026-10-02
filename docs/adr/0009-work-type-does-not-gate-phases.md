# ADR-0009: `work_type` does not gate phases — a phase is skipped only when the work type leaves it no subject matter

## Status

Accepted — 2026-10-02.

Number allocated through `pm-status.py adr-reserve`, not chosen by hand; see ADR-0005. The
customization-layer design doc names an "ADR-0009" in prose for a different subject, and says in
the same breath that **a reservation that lives only in prose is not a reservation**. That intent
is unaffected: whoever writes it takes its real number from `adr-reserve` at that time.

## Context

Every epic carries a `work_type` — `CODE`, `DOCS`, `CONFIG` or `MIXED` — and the execution steps
read it to decide which phases run. The phase matrix in
`skills/_shared/steps/shared/step-01-classify-work.md` was meant to be a reasoned table: for each
phase, does this kind of work give it anything to act on?

It was not. The `CONFIG` column was filled **by analogy to `DOCS`**, row by row, rather than by
asking the question per row. `DOCS` has a real answer for most phases — a documentation-only epic
has no code to review and no architecture to drift from. Infrastructure and configuration work
has all of it: interfaces, failure modes, security exposure, architectural consequence. The
analogy was wrong, and an infrastructure epic silently skipped story elaboration, the story
technical-AC gate, per-story code review, the epic architecture gate, epic architectural drift
review, epic security review, and adversarial analysis.

The run still finished green, because a skipped phase reports *skipped*, not *failed*. The
observed symptom was an infrastructure epic with twenty well-formed state nodes and zero story
documents.

**The matrix contradicted itself**, which is what made the missing reasoning visible: sprint-level
architectural drift review ran for `CONFIG`; epic-level architectural drift review skipped it.
Same concern, same work type, opposite answers, no principle separating them.

## Decision

**A phase is skipped by `work_type` only when that work type means the phase has no subject
matter at all.** That is true of `DOCS` alone. Every other phase gates on its own applicability
signal — whether the performing skill is installed, whether the epic has UI-facing stories — not
on the work type.

`CONFIG`'s column is now **identical to `CODE` and `MIXED` in every row**. `DOCS` remains the one
suppressing type; re-examining its column row by row was out of scope.

**UX review flips to `run` for `CONFIG`**, even though an infrastructure epic does not need UX
review. UX review is already gated on UI-facing stories independently of `work_type`, so that
check is the operative one and an infrastructure story still gets no UX review — it is not
UI-facing. Leaving the cell `skip` would have made `CONFIG` a second suppressing type and
contradicted the principle for a cell that was already inert.

### Two defects the design missed

Both were found during implementation, in the package this was ported from, and neither is a row
of the matrix. They are the most useful part of this record.

1. **`steps/plan/step-02-readiness-check.md` skipped the technical-ACs check for `CONFIG`.**
   Elaboration only elaborates stories that check grades Amber. With the check skipped, no
   `CONFIG` story could be graded Amber, so none would be elaborated — the whole change would
   have shipped **inert**, still producing zero story documents with every gate green.
2. **`steps/sprint/step-03-dev-loop.md` skipped per-story code review for `CONFIG`.**
   Infrastructure stories were implemented and never reviewed.

**The lesson: the matrix has two enforcement mechanisms** — the `{skip_phases}` binding, and
`work_type` checks written inside individual step files. Changing one without the other makes the
declared single source of truth false, and the second mechanism does not appear in the table.
Nothing mechanical checks either, so a future change to what a work type suppresses must grep the
step files for `work_type` as well as editing the matrix and the binding.

## Consequences

- **A `CONFIG` epic now costs roughly what a `CODE` epic costs.** Every story gains a code-review
  dispatch; the epic gains an architecture gate, an architectural drift review and a security
  review. Expect materially longer wall-clock time and a multiple of the token spend on
  infrastructure work that previously ran nearly bare. Accepted: the old cost was low because the
  work was not being checked.
- **Existing `CONFIG` calibration samples are now stale and will under-predict.**
  `state/pm-calibration.yaml` learned its `CONFIG` ratios from runs where these phases were
  skipped, so the first estimates after this change come in low until new samples accumulate. An
  estimate that is wrong for a knowable reason should be written down rather than rediscovered.
- Infrastructure stories now get story documents, technical ACs and code review, which is the
  outcome the change exists to produce.
