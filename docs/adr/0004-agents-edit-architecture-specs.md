# ADR-0004: Agents edit architecture specs; PRD, UX and epic docs are proposal-only; edits are confirmed after they land

- **Status:** Accepted
- **Date:** 2026-09-11
- **Deciders:** Package maintainer (brainstorming 2026-09-11)
- **Principle(s) in tension:** keeping specs true to the code vs. keeping product intent under human control

## Context

Sprint and epic drift reviews resolved every departure by a code fix or an accepted ADR.
Nothing ever updated a spec, so each accepted departure left the architecture document
describing a system that no longer existed
(`docs/superpowers/specs/2026-09-11-spec-alignment-design.md`, Problem 3). Specs differ in
who owns them. The architecture document records how the system is built, which the build
itself settles. The PRD, UX and epic documents record what the product should be, which is a
human decision.

## Options considered

| Option | Pros | Cons | Standards fit |
|--------|------|------|---------------|
| A. Agents edit every spec | Specs never lag | An agent rewrites product intent to match what it happened to build | Violates human ownership of requirements |
| B. Agents never edit; everything is a proposal | Full control | Architecture docs lag by every accepted departure until a person finds time | The drift this design exists to remove |
| C. Agents edit architecture sections only; PRD/UX/epics get proposals; every edit is confirmed after it lands | Architecture stays true; product intent stays human; each edit is one revertible commit | A wrong edit is in history until confirmed or rejected | Chosen |
| D. As C, but confirm before editing | Nothing lands unconfirmed | An epic closure blocks on a human, which makes autonomous closure impossible | Rejected |

## Decision

Option C. `spec-align.py disposition` refuses `spec-updated` on any section whose kind is not
`architecture` (exit 2). Spec sync commits each architecture edit as its own
`docs(spec): {epic} {finding} — {title}` commit, made only after a scope guard (the diff stays
inside the pointed-to section) and an anchor guard (no pointed-to anchor silently vanishes).
Each commit opens a `spec-change` backlog item. Doctor `triage` confirms it
(`resolve-issue --resolution fixed`) or rejects it (`spec-align.py reject`: `git revert`,
`wontfix`, and a new defect so the drift becomes a code fix again). PRD, UX and epic changes
become `spec-proposal` items, backed by a proposal file.

## Consequences

- Positive: the architecture document tracks the built system at epic granularity. Each edit
  is reviewable and revertible on its own.
- Negative / trade-offs accepted: an unconfirmed edit is live in history, and a later edit on
  the same file makes a clean revert less likely. `check-stale` (doctor Check 18) reports
  exactly that case.
- Revisit if: proposals accumulate unconfirmed across several epics (people are not acting on
  them), or rejected spec changes become common (the agents' edits are not trustworthy).
