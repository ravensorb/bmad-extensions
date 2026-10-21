# Auto-remediation — design

**Status:** design approved in conversation; spec awaiting review.
**Scope:** `l3io-pm`'s orchestrator-level halts. No change to dispatched subagent phases.

## 1. The problem

A user asked `/l3io-plan` to plan their work and was told there were no stories, and the run
stopped. Nothing was wrong with the halt — it was correct, and the alternative (reporting green
readiness over an empty set, writing a plan of 0 epics across 0 phases, and recommending
`/l3io-execute`) is strictly worse. The problem is what the halt leaves the user holding.

The package has **23 `BLOCKED:` sites** across `skills/_shared/steps/`. Several of them already
know their own remedy, name it, and call it "(recommended)" — and then stop, so that the user
can type the command themselves and start over. Three examples, verbatim:

- "Fix: run `/l3io-doctor bootstrap-state` to create state nodes from your artifact files."
- "Run `/l3io-doctor migrate-state` to upgrade before continuing."
- "Decide: re-run `/l3io-plan` to rebuild the pointer and readiness from current state
  (recommended), or…"

Where a remedy is known and performable, making the user perform it buys nothing. It costs a
round trip, a lost run, and — in the readiness case — a second full traversal of state that the
tool was already holding.

## 2. The rule

> When a halt has a remedy we can determine and perform, **perform it, report what was done,
> and continue the run.** Halt only when no remedy exists, when performing one would decide
> something that is the user's to decide, or when the remedy has already been tried.

This is house style rather than a new invention. Three precedents:

- **`pm-status.py` self-install** already detects a stale installed copy and repairs it without
  asking, with exactly one deliberate refusal (never overwrite a strictly newer copy).
- **ADR-0004** establishes that agents act and **confirm after the edit lands**, not before.
- Four of the halts already name their own remedy and mark it recommended.

## 3. The attempt bound — load-bearing, not optional

**One attempt per distinct issue per run.** The remedy is recorded *before* it runs. If the same
halt recurs after its own remedy, it becomes a hard halt whose message names what was tried:

```
BLOCKED: I ran /l3io-plan to resolve the readiness gaps and readiness is still RED.
The gaps are: <list>. This needs a decision.
```

That message is strictly more informative than today's, which cannot say whether anything was
attempted.

The bound is not defensive polish. **Three of the nine defaults are "re-run `/l3io-plan`", and
`/l3io-plan` carries its own halts** — including the no-stories halt that prompted this work.
Unbounded, a RED plan triggers a re-plan that goes RED again, indefinitely. There is no third
attempt under any condition.

## 4. The envelope

Nine sites qualify. The other fourteen keep halting (§5).

### 4.1 Deterministic — one remedy, already named

These remedies were written before implementation. Where they differ from `skills/_shared/auto-remediation.md`, that contract is authoritative.

| Halt | Auto-action |
|---|---|
| artifact-only stories (`plan/step-02-readiness-check.md`) | run `bootstrap-state`, continue |
| legacy state layout (`shared/step-00-activate.md`) | run `migrate-state` — preserves the original as `.legacy` — continue |
| `plan-output-meta.yaml` absent (`execute/step-03-load-plan.md`) | re-run `/l3io-plan`, continue |
| meta **points at a plan file that does not exist** (`execute/step-03-load-plan.md`) | re-run `/l3io-plan`, continue |
| state root is gitignored (`shared/step-00-activate.md`) | append the two negation lines to the work-tree `.gitignore` that `git check-ignore -v` names, report it, continue |

The fifth row was missed in the conversational pass that produced this design and found by
reconciling the site counts: it names one remedy ("Re-run `/l3io-plan` to rebuild the plan and
pointer") and explicitly forbids the alternative ("Do not substitute another snapshot — that
would execute a plan the pointer does not vouch for"). It is the same shape as the row above it
and qualifies for the same reason. Recorded because an enumeration that was wrong once in a
design is worth distrusting in implementation: **derive the site list from the step files, not
from this table.**

### 4.2 Ambiguous — a default chosen per site

| Halt | Default | Why it is safe |
|---|---|---|
| meta absent **but snapshots exist** | re-run `/l3io-plan` | The step file already marks this "(recommended)". It rebuilds from current state rather than trusting a snapshot its own text calls possibly-incomplete. Snapshots are not touched. |
| plan readiness **RED** | re-run `/l3io-plan`, **route 1 only** | See §5 — route 2 never automates. |
| state found outside `implementation_artifacts` | repoint `implementation_artifacts` at the found tree, recording the previous value | `_bmad/custom/config.toml` is our own layer; we already write it. The recorded previous value makes it revertible. |
| **multiple state layouts** | **conditional — §4.3** | |

### 4.3 Multiple state layouts — evidenced, never guessed

The step file's own words are that guessing which layout is authoritative "would fork the
project's state." A blind default is not defensible. An evidenced one is:

- Compare the trees by node key. **If the legacy tree is a strict subset of the sharded tree**,
  the migration copied everything and died before cleanup. That is unambiguous: back up the
  legacy tree and proceed on sharded.
- **If either tree holds a node the other lacks**, halt — and **print the diff**, naming which
  node keys differ.

This automates the common case and refuses the one that can lose work. The halt improves even
when it fires: today it says "inspect both locations", leaving the user to find the difference
themselves.

## 5. What never automates

Three are hard rules, not defaults:

- **An epic lock held by another session.** Lanes exist so two developers work in two clones;
  breaking another session's lock is data loss across a boundary `flock` cannot see.
- **Authentication unavailable.** Never touch credentials.
- **Accepting plan risk.** The RED-readiness halt offers a second route: *"accept the risk: say
  so, and I will set readiness to amber."* Downgrading readiness is a risk acceptance, and
  accepting risk on the user's behalf is the definition of what must not be automated — it
  would let an incomplete plan execute while the record says it was fine.

The remaining eleven are ordinary halts with no single remedy: an unrecognised scope argument,
an epic key not found, a dependency not done, unresolved arch-gate findings, a story still
missing ACs after elaboration, a failed schema verify, a missing sibling `pm-status.py` (the
install itself is broken), platform detection failure, and the aggregate readiness gate.

## 6. Mechanism

### 6.1 Not in `pm-status.py`

The natural home would be a verb — `remediate --record`. It is unavailable: `pm-status.py` is at
**exactly 10,000 lines**, ADR-0001's cap, enforced by `check:docs` check 12. This is the third
design in two days that the cap has redirected (see the v7 bridge spec §8.2). Recorded here as
further evidence toward ADR-0001's stated "revisit at 10,000".

### 6.2 A shared reference

`skills/_shared/auto-remediation.md` carries the rule, the attempt contract, the
nine-site table, and the never-automate list. Each halt site keeps its own prose and gains a
declared remedy. Shared references live flat at `skills/_shared/<name>.md`, not in a
`references/` subdirectory; `npm run sync:scripts` delivers this one to `references/auto-remediation.md`
in `l3io-execute`, `l3io-plan` and `l3io-sync`.

### 6.3 The attempt record is in-run memory, not a file

The bound is *per run*; a run is one orchestrator invocation; **all nine sites are inline in
that invocation**, not inside a dispatched subagent. Verified: `shared/step-00-activate.md`,
`plan/step-02-readiness-check.md` and `execute/step-03-load-plan.md` are all orchestrator-level.
`l3io-execute` dispatches *sprint* subagents, and every halt in that dispatched context is in the
never-automate list.

So no new state file, no schema, nothing to migrate. This matters because the package's context
boundary rule is that state passes through disk and never through in-memory hand-off — that rule
binds across a dispatch, and these sites do not cross one.

**If a qualifying halt ever moves into a dispatched subagent, this decision is void** and the
record must go to disk. The reference says so at the point of use.

## 7. What the user sees

Act, then confirm (ADR-0004). One line before, one after:

```
⚙  12 story artifact(s) have no state node — running /l3io-doctor bootstrap-state
✓  bootstrap-state created 12 state nodes. Continuing readiness check.
```

Silence is not an option. The user should finish the run knowing what their project needed, not
with it hidden. A remediation that cannot report what it changed does not qualify under §2.

## 8. Risks and open questions

- **A default can be wrong.** Four of the nine are judgement calls (§4.2). Each is reversible —
  `migrate-state` keeps `.legacy`, the config repoint records its previous value, re-planning
  leaves snapshots intact — but reversible is not the same as unnoticed. §7's reporting is what
  makes a wrong default recoverable.
- **The bound depends on the agent honouring prose.** There is no mechanical enforcement of
  "record before you run it". A checker could assert that every declared remedy in a step file
  appears in the reference's table, which catches drift but not a skipped record.
- **Open: does `/l3io-plan` re-entry need a distinct flag?** Three defaults re-run `/l3io-plan`
  from inside a run. If that re-entry is indistinguishable from a user invocation, the
  setup-pointer notice and any first-run behaviour fire again mid-run. Needs checking against
  `config-resolution.md` §5 before implementation.
- **Not addressed: epics that hold no stories.** That halt (`§1.1b`) has no single remedy —
  decomposing an epic into stories is authoring, and the skill that used to do it,
  `bmad-create-epics-and-stories`, was removed in BMad v7 with no replacement. It stays a halt.
  Its message should still be improved to name a concrete path, which is a separate change.

## 9. ADR

One ADR required: **auto-remediation of orchestrator halts**, recording the rule, the three
hard refusals, and the attempt bound. Allocate the number through
`pm-status.py adr-reserve` — never by hand.
