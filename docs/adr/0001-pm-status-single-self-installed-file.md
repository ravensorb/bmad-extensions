# ADR-0001: `pm-status.py` stays one self-installed file

- **Status:** Accepted (records a constraint already in force)
- **Date:** 2026-09-10
- **Deciders:** Package maintainer; reviewed by `l3io-arch-review` Mode B
- **Principle(s) in tension:** Core §1 separation of concerns vs. an atomic, single-copy runtime install

## Context

`pm-status.py` is the one runtime writer of l3io-pm state, used by `l3io-execute`,
`l3io-plan`, `l3io-sync`, and `l3io-doctor`. Each skill ships a synced copy, and at
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
`l3io-doctor/scripts/audit-backlog.py`, while its integrity checks stay in `pm-status.py`.

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

## Amendment (2026-10-03) — the limit is raised to 10,000, and Option C is withdrawn

Check 12 tripped at 8,025 lines, adding `repair-issue --action normalize-keys`. **Decision:
raise the hard limit to 10,000 and keep Option A.** Option C is withdrawn as the named
successor, because the evaluation the 2026-09-11 amendment asked for was finally done and
the ground it assumed is gone.

**What the evaluation found.** Both bundlers that amendment named are abandoned: `stickytape`
0.2.1 was last released 2021-01-29 (5.7 years) and `pinliner` 0.2.0 on 2016-04-03 (10.5
years). Adopting either fails the same global rule 1 that forbids hand-rolling one. The
maintained alternatives — `shiv`, `pex`, `zipapp` — all produce an archive rather than a text
script, and that breaks two things this package depends on:

- **PEP 723 provisioning.** `uv` reads inline metadata only from a text script. Measured with
  identical content in both shapes: a `.pyz` raised `ModuleNotFoundError`, the `.py` printed
  `Installed 1 package`. Every script here gets `ruamel.yaml` that way, with no venv on the
  consuming project.
- **Byte-reproducibility.** Two zipapp builds of unchanged source differ, because zip stores
  mtimes. That breaks `check:scripts` and the per-file SHA-256 in `payload-manifest.json`.

So Option C has no viable tool, not merely no chosen one.

**Why not Option B instead.** It is cheaper than it was — it was rejected partly for needing a
multi-file hash guard, and `payload-manifest.json` now is one, verified by `check:manifest`.
What has not changed is that `self-install` does a single `os.replace`, which is atomic;
installing N files is not, and a crash mid-install leaves a half-written runtime writing
project state. A directory-level `os.replace` may answer that, and is the first thing to test
if this is reopened.

**What 10,000 is and is not.** It is not a judgement that the file is fine at 10,000 lines; it
is headroom bought deliberately while the structural options are unavailable. The mechanism
stays exactly as the previous amendment built it — a hard number in check 12, failing the
build, naming this ADR — because the lesson that produced it still holds: the ~6,000 prose
trigger was crossed silently, and a number that only lives in an ADR is a number nobody
enforces. The dependency trigger (a verb needing a dependency its other callers do not) is
unchanged and still applies independently.

**Option C is RETIRED, not deferred — do not re-evaluate these.** `stickytape`, `pinliner`
and the archive family (`zipapp`, `shiv`, `pex`) are closed, with the evidence above:

| Candidate | Why it is dead |
|---|---|
| `stickytape` | last release 2021-01-29; unmaintained, so global rule 1 forbids it as surely as hand-rolling |
| `pinliner` | last release 2016-04-03; same |
| `zipapp` / `shiv` / `pex` | produce an archive, so `uv` cannot read a PEP 723 header from it and the artifact is not byte-reproducible — two mechanisms this package depends on, measured, not assumed |

A future proposal in this space is only worth hearing if it produces a **single text script**
AND preserves PEP 723 provisioning AND is byte-reproducible AND is maintained. Nothing on the
table does, and re-testing the four above wastes the evaluation already recorded here.

**Revisit at 10,000 with one option:** Option B, a package directory under
`_bmad/scripts/`, whose only surviving objection is atomicity — test whether a directory-level
`os.replace` restores it. If that fails, raising the number again becomes a decision made on
evidence rather than a default, and it should be argued here before it is taken.

