# Auto-remediation of orchestrator halts

Skills in this package stop at a `BLOCKED:` line when they cannot proceed. Several of those
halts already know their own remedy, name it, and stop so the user can type it and start the
run over. This reference governs which halts perform the remedy instead.

> When a halt has a remedy we can determine and perform, **perform it, report what was done,
> and continue the run.** Halt only when no remedy exists, when performing one would decide
> something that is the user's to decide, or when the remedy has already been tried.

A halt is classified in exactly one of the two tables at the end of this file. A step file that
remediates a halt points here for the contract; it does not restate it.

## The attempt bound

**One attempt per distinct issue per run.** Record the remedy *before* running it. If the same
halt recurs after its own remedy has run, it becomes a hard halt naming what was tried:

> BLOCKED: I ran `<remedy>` to resolve `<condition>` and the condition persists. `<detail>`.
> This needs a decision.

There is no second attempt under any condition. Three of the remedies re-run `/l3io-plan`,
which carries its own halts; unbounded, a RED plan re-plans into RED forever.

The record is **in-run memory**, not a file: the bound is per run, a run is one orchestrator
invocation, and every remediable site is inline in that invocation rather than inside a
dispatched subagent. **If a site ever moves into a dispatched subagent this is void** — the
package's context boundary passes state through disk, never through in-memory hand-off — and
the record must become a file.

## Reporting — act, then confirm

Per ADR-0004 an agent acts and confirms after the edit lands. Every remediation prints one line
before and one after:

```
⚙  <condition, with counts> — running <remedy>
✓  <what the remedy did>. Continuing <what resumes>.
```

A remediation that cannot report what it changed does not qualify. Silence is never correct:
the user should finish the run knowing what their project needed, not with it hidden.

## When a remedy fails

If the remedy exits non-zero, **halt** — reporting both the original condition and the
remedy's failure. Never continue as though it succeeded, and never retry.

A remedy that succeeds is not yet a remedy that worked: re-check the original condition once.
If it persists, that is the attempt bound's hard halt above, not a reason to continue. Every
remediable site therefore has three explicit outcomes — cleared, succeeded but persists, and
failed — and only the first continues.

## The tables are a live inventory

The two tables below hold one row per halt **site** — a site is a distinct halt condition, and
may be written as more than one `BLOCKED:` line when it has a recurrence form and a failure
form that share their opening words. The row count always equals the number of sites. A task
that converts a halt **moves its row from `Halts` to `Remediable` in the same commit** that
changes the step file, so the tables never disagree with the code.

A site is identified as `<file-stem>: <first six words of the BLOCKED text>`; placeholders in
braces match whatever they hold at runtime.

## Remediable

| Site | Trigger | Remedy | Changes |
|---|---|---|---|
| `step-02-readiness-check: artifact-only stories detected — I ran` | story `.md` files exist with no state YAML | `/l3io-doctor bootstrap-state` | creates state nodes from artifacts; writes no artifact |

## Halts

These stop the run. Rows marked **ABSOLUTE** are hard rules, not defaults: no later change may
convert them, whatever remedy appears to exist. Rows marked *not yet remediated* are destined
for conversion and will move to `Remediable`.

| Site | Why |
|---|---|
| `step-02-scope-resolve: {epic_key} is owned by another session.` | **ABSOLUTE.** Breaking another session's lock is data loss across a boundary `flock` cannot see — lanes exist so two developers work in two clones |
| `step-05-epic-loop: {epic_key} lock held by another session.` | **ABSOLUTE.** Same |
| `step-02-detect-platform: authentication unavailable.` | **ABSOLUTE.** Never touch credentials |
| `step-03-load-plan: plan readiness is RED for {current_plan_file}.` | Not yet remediated — Task 3 converts route 1 (re-plan). **Route 2 is ABSOLUTE:** accepting the risk and setting readiness to amber is the user's alone, and must stay a halt after route 1 converts |
| `step-03-load-plan: plan-output-meta.yaml absent.` | Not yet remediated — Task 3 converts this |
| `step-03-load-plan: plan-output-meta.yaml absent, but snapshots exist ({listed_snapshots}).` | Not yet remediated — Task 3 converts this |
| `step-03-load-plan: plan-output-meta.yaml points at {current_plan}, which does` | Not yet remediated — Task 3 converts this |
| `step-00-activate: legacy state layout — migrate required.` | Not yet remediated — Task 4 converts this |
| `step-00-activate: state found at <printed-path> but implementation_artifacts` | Not yet remediated — Task 4 converts this |
| `step-00-activate: {pm_state_root} is gitignored. Project state must` | Not yet remediated — Task 4 converts this |
| `step-00-activate: multiple state layouts detected (sharded=$SHARDED legacy-per-epic=$LEGACY_EPIC` | Not yet remediated — Task 5 converts this, only where the legacy tree is a strict subset of the sharded one |
| `sprint-closure: sprint {sprint_num} of {epic_key} — {N}` | External dependency; no remedy exists |
| `step-02-readiness-check: readiness gate — red. Do not` | Aggregate of per-story findings; no single remedy |
| `step-02-scope-resolve: unrecognized scope argument.` | User input error |
| `step-02-scope-resolve: {epic_key} not found under {pm_state_root} —` | User input error |
| `step-03-dev-loop: story {story_key} depends on {dep_key}, which` | Ordering fact, not a defect |
| `step-04-arch-gate: arch gate — {N} blocking findings` | Requires design decisions |
| `step-02-detect-platform: platform detection failed.` | Environment, not state |
| `step-02-story-prep: story {story_key} still missing required acceptance` | Content authoring |
| `step-00-activate: l3io-setup/scripts/pm-status.py is missing beside this` | The install itself is broken |
| `step-00-activate: schema verify failed for {epic_key} —` | Unknown state corruption; guessing could worsen it |
| `step-05-dependency-graph: dependency graph has errors — resolve` | Requires `depends_on` decisions |
