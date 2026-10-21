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

### Eight sites remediate

| Site | Remedy |
|---|---|
| artifact-only stories (story `.md` files, no state YAML) | `/l3io-doctor bootstrap-state` |
| four plan-pointer sites in `step-03-load-plan` (pointer absent, absent with snapshots, readiness RED, target missing) | `/l3io-plan` |
| legacy state layout | `/l3io-doctor migrate-state` |
| `implementation_artifacts` moved away from existing state | repoint `_bmad/custom/config.toml`, recording the previous value |
| multiple state layouts | **conditional** — move the legacy tree to `_bmad/state.superseded` only when every legacy epic key is also in the sharded tree |

The last is the only remedy that depends on evidence. It compares epic keys alone: sprint or
story divergence inside a shared epic key is not examined. A legacy-only epic key, a legacy
entry that is not an epic key, or a flat legacy file leaves it a halt that prints the keys that
differ.

### Fifteen sites halt

Twelve are ordinary halts with no single remedy: external dependencies, user input errors,
ordering facts, aggregate findings, content authoring, a broken install, unknown state
corruption, platform detection, and the gitignored state root. Three are absolute.

### The gitignored state root was attempted and withdrawn

The halt was first converted: append `!{pm_state_root}/` and `!{pm_state_root}/**` to the
`.gitignore` that `git check-ignore -v` names. Measured in a scratch repository, it does not
work:

| `.gitignore` | `check-ignore -v` |
|---|---|
| `out/` | `.gitignore:1:out/` — ignored |
| plus `!<ABS>/out/impl/state/` and `!<ABS>/out/impl/state/**` | `.gitignore:1:out/` — still ignored |
| plus `!out/`, `!out/impl/`, `!out/impl/state/` | `.gitignore:6:!out/impl/state/` — tracked |

`{pm_state_root}` is bound as `{implementation_artifacts}/state`, an absolute path, and a
gitignore pattern is relative to the directory of the file that holds it, so an absolute negation
matches nothing: the conversion appended two dead lines to a file the project does not own and
then halted blaming a later rule. Only relative negations work, and each must negate **every**
excluded parent. When the ignoring rule excludes a parent directory (`_bmad-output/`, say), git
cannot re-include from inside it at all, and negating the parents changes what else in the
repository becomes tracked. That is a judgement about the user's repository, not a mechanical
remedy, so the site is a halt. It keeps the `check-ignore -v` locate step and the guard chain
that classifies the source (symlink, file name, real path under the work tree), so the halt
names the exact file and rule, and it writes nothing.

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

The bound is per run, a run is one orchestrator invocation, and all eight sites are inline in
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
`skills/_shared/steps/**`. It enforces **classification**: every `BLOCKED:` site is classified,
no row is stale, every row's `Class` is valid, and each Remediable row names a remedy that
appears near its halt and on at least one line outside any `BLOCKED:` block. That last clause is
the only part that reaches implementation. It was added because the earlier rule, a remedy string
present near the halt, passed for 10 of 20 matched sites on the halt message alone (distance 0):
the pre-branch text already named its remedy and stopped, so restoring the old halt-and-name form
left the check green. A remedy appearing outside a `BLOCKED:` block shows that some prose
performs it, not that the prose is correct. A task that converts a halt moves its row from `Halts`
to `Remediable` in the same commit.

The inventory is of 23 sites at column 0 of `skills/_shared/steps/**`. Not inventoried:
`closure/epic-closure.md:236` (indented), `skills/l3io-doctor/steps/redrive.md:103`, and
`skills/l3io-help/steps/step-02-detect-layout.md:24` and `:67`. The last two are verbatim copies
of conditions converted above and stay halts deliberately: `l3io-help` is an advisory skill and
does not write to a project. So 23 is not every halt in the package.

## Consequences

- A project whose stories exist only as `.md` files, whose plan pointer is stale, whose layout is
  legacy, proceeds in one invocation, and the run reports what
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
3. **A remediation-record verb in `pm-status.py`** — this decision's own attempt record.
4. **The `check 12 boundary: exactly 10,000 lines passes` test**, which could not run at all
   once the file reached the cap: its padding helper asserted the file was still below the
   target and failed before exercising check 12 (repaired in `92e78bd`). The one state the
   project is actually in was the one state the suite had stopped checking.

ADR-0001 says raising the number again "becomes a decision made on evidence rather than a
default, and it should be argued here before it is taken." Four independent changes, one of
them a safety fix and one a test of the cap itself, are that evidence. This ADR does not take
the decision; it records that the revisit is due.
