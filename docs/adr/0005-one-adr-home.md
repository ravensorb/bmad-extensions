# ADR-0005: One ADR home, `docs/adr/`; allocation takes the higher of the register and the files on disk

- **Status:** Accepted
- **Date:** 2026-09-11
- **Deciders:** Package maintainer (brainstorming 2026-09-11)
- **Principle(s) in tension:** a single source of truth for decisions vs. collision-free numbering by parallel agents

## Context

ADRs had two unconnected homes. The PM arch gate and closures wrote
`{implementation_artifacts}/epic-NNN/arch/adr-NNNN-slug.md`, numbered by
`state/adr-register.yaml` under a flock. `l3io-arch-review` Mode C wrote
`{project-root}/docs/adr/`, and nothing numbered those. `adr-reserve` never looked at
`docs/adr/`, so two different ADR-0003s could coexist. The register exists because a
directory listing shows who has finished, not who is in flight: three parallel agents once
took 0013 and 0014 twice each.

## Options considered

| Option | Pros | Cons | Standards fit |
|--------|------|------|---------------|
| A. Keep two homes | No migration | Duplicate numbers; readers must know both homes | Two sources of truth |
| B. `docs/adr/` only; number by directory listing | Simple | Reintroduces the in-flight collision the register fixed | Rejected by production evidence |
| C. `docs/adr/` only; the register allocates, starting at `max(register next, highest number on disk + 1)` under its existing lock | One home; in-flight safety kept; hand-written or unmigrated ADRs can't collide; a lagging register heals itself | A scan per reservation; a migration for existing projects | Chosen |
| D. The implementation-artifacts home only | No change for PM | Mode C and humans keep ADRs in `docs/adr/`, the conventional place | Rejected |

## Decision

Option C. `adr-reserve` scans `--adr-dir` (default `<git top-level of the state root>/docs/adr`;
step files pass `{project-root}/docs/adr`, because a BMad project need not be the repository
root) and the old home, `<state-root>/../epic-*/arch/adr-NNNN-*.md`. Mode C uses
`adr-reserve` when l3io-pm is installed. Without l3io-pm it takes the directory's highest
number plus one, which is safe only because no parallel PM agents exist in that setup. Doctor
Check 15 finds ADRs left in the old home, and the `migrate-adrs` mode moves them. On a number
collision it keeps the `docs/adr/` number and renumbers the epic ADR only inside its own epic
tree.

## Consequences

- Positive: one place to read decisions; `spec-align.py adrs --epic` lists an epic's ADRs
  from their `Epic:` line.
- Negative / trade-offs accepted: a project that does not migrate keeps working, because both
  readers still read the old home, but it carries two homes until it runs `migrate-adrs`.
- Revisit if: ADR numbering needs to span repositories, which a per-repo register cannot do.

## Amendment (2026-09-26) — the scan tolerates the `ADR-` filename prefix

The scan above was implemented as `^\d{4}-.+\.md$` in the one home and `^adr-\d{4}-.+\.md$`
in the old one. Neither matches `ADR-NNNN-slug.md`, which is how a hand-written ADR is
commonly named — and the hand-written ADR is the first case the Decision names as the reason
to scan disk at all. A consumer project with `docs/adr/ADR-0004…ADR-0025` scanned as "highest
is 0", indistinguishable from an empty directory, and `adr-reserve` issued numbers that were
already taken.

Both patterns now accept an optional, case-insensitive `ADR-` prefix. This changes no
decision: the allocator still takes `max(register next, highest on disk) + 1`, and widening
what counts as an ADR on disk can only raise that floor, never lower it. The package still
*writes* `{adr_number}-{slug}.md`; the tolerance is for files it did not write.
