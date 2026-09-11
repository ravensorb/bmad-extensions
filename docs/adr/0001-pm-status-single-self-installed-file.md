# ADR-0001: `pm-status.py` stays one self-installed file

- **Status:** Accepted (records a constraint already in force)
- **Date:** 2026-09-10
- **Deciders:** Package maintainer; reviewed by `l3io-arch-review` Mode B
- **Principle(s) in tension:** Core §1 separation of concerns vs. an atomic, single-copy runtime install

## Context

`pm-status.py` is the one runtime writer of l3io-pm state, used by `l3io-pm-execute`,
`l3io-pm-plan`, `l3io-pm-sync`, and `l3io-util-doctor`. Each skill ships a synced copy, and at
setup or activation runs `self-install --dest {project-root}/_bmad/scripts/pm-status.py`.
`cmd_self_install` copies exactly `__file__` under one SHA-256 content guard and one
`os.replace`. A sibling module would never reach `_bmad/scripts/`, so the installed copy could
not import it.

The file is 5,060 lines and handles state transitions, estimation, calibration, reporting,
usage capture, and self-install. The issue-lifecycle design
(`docs/superpowers/specs/2026-09-10-issue-lifecycle-design.md`) adds further verbs. Until now the
constraint existed only as prose in `CLAUDE.md`.

The constraint does not apply uniformly: `write-module-config.py`, `drift-report.py`, and
`init-sanctum.py` all run from their own skill directory. It binds only code that more than one
skill needs at runtime.

## Options considered

| Option | Pros | Cons | Standards fit |
|--------|------|------|---------------|
| A. One self-installed file; single-consumer code lives in its skill's own `scripts/` | Atomic install; one-hash guard; one-file footprint in BMad core's directory; no packaging | The file keeps growing | Honors §1 where it can (single-consumer code moves out); accepts one large shared file |
| B. A package directory under `_bmad/scripts/` | Normal module boundaries | Multi-file hash guard; loses the atomic `os.replace`; more files in core's directory | Better §1; worse install integrity |
| C. Build-time bundling into one file | Modular source, single-file artifact | A bundler to adopt (stickytape, pinliner — unevaluated) or hand-roll (forbidden by global rule 1); a build step in a repo that has none | Neutral §1; adds tooling |

## Decision

Option A. Anything that more than one skill runs at runtime stays inside `pm-status.py`. Code
with a single consumer ships in that skill's own `scripts/` and reaches `pm-status.py` only
through its CLI. The first application: the issue audit's heuristic checks go to
`l3io-util-doctor/scripts/audit-backlog.py`, while its integrity checks stay in `pm-status.py`.

## Consequences

- Positive: installs stay atomic and verifiable by one hash; no new tooling.
- Negative / trade-offs accepted: `pm-status.py` remains a large file, owned by the package
  maintainers.
- Follow-ups / exit plan: revisit when the file passes ~6,000 lines, or when a verb needs a
  dependency its other callers do not; Option C is the first candidate then, after evaluating an
  existing bundler.

## Amendment (2026-09-11)

The ~6,000-line size trigger fired: `skills/_shared/pm-status.py` was 6,479 lines at this
commit. Decision: **keep Option A.** The file is still one runtime writer with one
self-install hash guard, and no verb yet needs a dependency its other callers do not — the
dependency trigger is unchanged.

The revisit trigger is replaced with a hard, mechanically enforced number: **8,000 lines.**
`npm run check:docs` gains check 12 (`pm-status-size`), which reads
`skills/_shared/pm-status.py` and fails when its line count exceeds 8,000, naming the count,
the limit, and this ADR. This is deliberately a different mechanism from the ~6,000-line
prose trigger it replaces — a number that only lives in an ADR's prose was exactly the
failure mode global rule 3 warns about (a rule that isn't checked is a rule that gets missed
at 8,000 the same way it was crossed silently at 6,000).

When check 12 trips, **Option C stays the first candidate** — after evaluating an existing
bundler (for example `stickytape` or `pinliner`), not a hand-rolled one, per global rule 1.
The dependency trigger from the original decision (a verb needing a dependency its other
callers do not) is unchanged and still applies independently of line count.
