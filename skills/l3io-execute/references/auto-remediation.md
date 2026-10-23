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

There is no second attempt under any condition. Four of the remedies re-run `/l3io-plan`,
which carries its own halts; unbounded, a RED plan re-plans into RED forever.

**Remedies that share one command and one underlying cause share a single attempt.** This
refines the rule above and does not replace it. The four plan-pointer sites in
`step-03-load-plan` all derive their symptom from one `/l3io-plan` run's output, so a second
symptom after a rebuild cannot be independent of the first: a second run over the same state
regenerates the same result. They therefore share the in-run flag `{plan_rebuilt}`, set before
the first run, and a symptom that survives the rebuild goes to its site's persists halt rather
than to a second run.

**The budget is per site id, not per run.** Sites that do not share a command and a cause each
keep their own. A project can be both legacy-layout and have a missing plan pointer: remediating
`step-00-activate: legacy state layout — migrate required.` (`/l3io-doctor migrate-state`) does not consume
`step-03-load-plan: plan-output-meta.yaml absent. I ran /l3io-plan and` (`/l3io-plan`), so both run
in that one invocation, each once. Sharing is the exception above, for
one command and one cause; two different remedies are never one attempt.

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

If the remedy reports failure or errors, **halt** — reporting both the original condition and the
remedy's failure. Never continue as though it succeeded, and never retry.

A remedy that writes to disk has a failure path of its own: a write that errors (permissions, a
read-only checkout) is a failed remedy. Report the original condition **and** the write error,
and leave nothing partly applied. The one write that can hit it is the `config.toml` repoint.

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

A site is identified as `<file-stem>: <first six words of the BLOCKED text>`, or the whole line
if it is shorter; placeholders in braces match whatever they hold at runtime.

**To add, change or convert a halt, you must:**

- Add a table row **in the same commit** as any new `BLOCKED:` line.
- Give a second form of an existing site the first six tokens of the first form **verbatim**,
  so the two collapse to one id.
- **Move** a converted site's row from `Halts` to `Remediable`. Never copy it, and never leave
  a stale row behind.

**Class.** Every row carries a `Class`, and the class travels with the row when it moves:

- `auto` — remediated.
- `halt` — halts; no single remedy.
- `absolute` — halts and may never be converted.
- `auto+absolute` — has a convertible route and an absolute one.

`absolute`, and the `absolute` half of `auto+absolute`, may never be removed by a later task.

**Scope.** The inventory covers `BLOCKED:` lines at column 0 of a shared step file. The
phase status-line template (`BLOCKED: [one-line reason]`, indented in
`execute/step-05-epic-loop.md`) is a report format, not a halt, and is deliberately out of
scope. Outside the inventory, and so not among the 23, are `BLOCKED:` lines this scope does not reach:

- `closure/epic-closure.md:236` (`BLOCKED: {epic_key} — {N} story/ies blocked pending external
  resolution`) — a genuine halt, indented.
- `skills/l3io-doctor/steps/redrive.md:103` — a halt in a doctor mode, not an orchestrator step.
- `skills/l3io-help/steps/step-02-detect-layout.md:26` and `:69` — column-0 halts that **repeat**
  two conditions converted above (multiple state layouts; state outside
  `implementation_artifacts`). They stay halts **deliberately**: `l3io-help` is an advisory skill
  that recommends the next action and does not itself run migrations or write configuration, so
  converting them would make a read-only skill mutate a project. Its step file describes its
  probe as the same three-way probe `step-00-activate.md` runs, reporting where that step
  remediates.

## Re-entry

Four remedies re-run `/l3io-plan` from inside `l3io-execute`, and `/l3io-plan` has first-run
behaviour: the once-per-project setup pointer (`config-resolution.md` §5). **It does not fire
again mid-run.** `pm-status.py notice` reads and writes `state/.notices.yaml` keyed on `--key`
alone, with no session, run or caller in the key, and records a key at most once ever per
project: exit 0 the first time, exit 1 for every call after. `l3io-execute` applies the pointer
at its own entry, before `step-03-load-plan`, so the nested `/l3io-plan` finds `setup-pointer`
already recorded, gets exit 1 and says nothing. When the pointer was not shown at entry, it is
because `modules.l3io-pm` is configured, and `{l3io_pm_section_absent}` is then false for the
nested run too. The remediation therefore needs no suppression of its own.

## Remediable

| Site | Trigger | Remedy | Changes | Class |
|---|---|---|---|---|
| `step-02-readiness-check: artifact-only stories detected — I ran` | story `.md` files exist with no state YAML | `/l3io-doctor bootstrap-state` | creates state nodes from artifacts; writes no artifact | `auto` |
| `step-03-load-plan: plan-output-meta.yaml absent. I ran /l3io-plan and` | no pointer, no snapshots | `/l3io-plan` | writes the pointer and a fresh snapshot | `auto` |
| `step-03-load-plan: plan-output-meta.yaml absent, but snapshots exist ({listed_snapshots}).` | pointer missing, snapshots present | `/l3io-plan` | rebuilds from current state; existing snapshots are not deleted or read, because the newest may be incomplete | `auto` |
| `step-03-load-plan: plan readiness is RED for {current_plan_file}.` | pointer readiness is red | `/l3io-plan` | resolves gaps and rebuilds; route 1 only. **Route 2 is ABSOLUTE and stays a halt:** accepting the risk and setting readiness to amber is a risk acceptance that is the user's alone, so no remediation writes `readiness:` | `auto+absolute` |
| `step-03-load-plan: plan-output-meta.yaml points at {current_plan}, which does` | pointer target missing | `/l3io-plan` | rebuilds plan and pointer; does not substitute another snapshot | `auto` |
| `step-00-activate: legacy state layout — migrate required.` | only a legacy layout present | `/l3io-doctor migrate-state` | migrates to the sharded layout; preserves the original as `.legacy`, which is what makes it reversible | `auto` |
| `step-00-activate: state found at <printed-path> but implementation_artifacts` | state exists outside `implementation_artifacts` | `_bmad/custom/config.toml` | repoints `implementation_artifacts` at the existing tree; records the previous value beside the new one in the same write | `auto` |
| `step-00-activate: multiple state layouts detected (sharded=$SHARDED legacy-per-epic=$LEGACY_EPIC` | **CONDITIONAL — remediates only on evidence.** `SHARDED` and `LEGACY_EPIC` are both present, `LEGACY_FLAT` is absent, **and every epic key in the legacy tree is also in the sharded tree** (equal sets and an empty legacy tree included). A legacy-only epic key, a legacy entry that is not an epic key, or a flat legacy file leaves it a halt that prints the keys that differ | `_bmad/state.superseded` | moves the legacy `_bmad/state/` tree to `_bmad/state.superseded` (moving it back restores it); **the sharded tree is not modified**. Compares epic keys only — sprint or story divergence inside a shared epic key is not examined | `auto` |

## Halts

These stop the run. Rows of class `absolute` (marked **ABSOLUTE**) are hard rules, not defaults: no later change may
convert them, whatever remedy appears to exist.

| Site | Why | Class |
|---|---|---|
| `step-02-scope-resolve: {epic_key} is owned by another session.` | **ABSOLUTE.** Breaking another session's lock is data loss across a boundary `flock` cannot see — lanes exist so two developers work in two clones | `absolute` |
| `step-05-epic-loop: {epic_key} lock held by another session.` | **ABSOLUTE.** Breaking another session's lock is data loss across a boundary `flock` cannot see — lanes exist so two developers work in two clones | `absolute` |
| `step-02-detect-platform: authentication unavailable.` | **ABSOLUTE.** Never touch credentials | `absolute` |
| `sprint-closure: sprint {sprint_num} of {epic_key} — {N}` | External dependency; no remedy exists | `halt` |
| `step-02-readiness-check: readiness gate — red. Do not` | Aggregate of per-story findings; no single remedy | `halt` |
| `step-02-scope-resolve: unrecognized scope argument.` | User input error | `halt` |
| `step-02-scope-resolve: {epic_key} not found under {pm_state_root} —` | User input error | `halt` |
| `step-03-dev-loop: story {story_key} depends on {dep_key}, which` | Ordering fact, not a defect | `halt` |
| `step-04-arch-gate: arch gate — {N} blocking findings` | Requires design decisions | `halt` |
| `step-02-detect-platform: platform detection failed.` | Environment, not state | `halt` |
| `step-02-story-prep: story {story_key} still missing required acceptance` | Content authoring | `halt` |
| `step-00-activate: l3io-setup/scripts/pm_status/__main__.py is missing beside this skill.` | The install itself is broken | `halt` |
| `step-00-activate: schema verify failed for {epic_key} —` | Unknown state corruption; guessing could worsen it | `halt` |
| `step-05-dependency-graph: dependency graph has errors — resolve` | Requires `depends_on` decisions | `halt` |
| `step-00-activate: {pm_state_root} is gitignored. Project state must` | Appending negations was attempted and withdrawn (ADR-0012): `{pm_state_root}` is absolute and gitignore patterns are relative to their file, so the negation matched nothing; relative negations work only if every excluded parent is negated, and when the rule excludes a parent directory git cannot re-include from inside it, which changes what else the repository tracks. The halt locates the rule with `check-ignore -v` and names the file | `halt` |
