# Parallel Lanes — Design

**Status:** Draft for review
**Date:** 2026-10-11

**Goal:** Let several developers, each with their own BMad install and agents, work the same
plan concurrently without colliding — and make the collisions that remain visible rather than
discovered at integration.

---

## 1. The assumption that breaks

Every concurrency guarantee in this package is `flock`: `epic_node_lock`, `issues_lock`,
`calibration_lock`, `adr_register_lock`. State is **committed to git**, so across two clones
there is no shared lock at all. Concurrency stops being mediated by the filesystem and becomes
mediated by `git merge`, and nothing in the package handles that today.

So the partition question is not primarily "who does which work". It is **"who may write which
state files"**, because that is the only thing standing between two developers and a silent
collision.

## 2. The invariant: 1 epic = 1 lane

`state/{status}/epic-{nnn}/` holds everything for an epic — sprints, stories, locks. Two lanes
owning disjoint epics never touch each other's node files, and **git merges disjoint paths
cleanly**. That property is the whole foundation, and it is why the invariant is not a
simplification to be relaxed later:

**If a story could be lane-assigned independently of its epic, the lane graph would be a
different graph from the epic graph**, and every cross-lane question would need its own
traversal. With `1 epic = 1 lane` the lane graph is the epic graph with **relabelled nodes** —
a colouring, not a second graph — so everything already built for epics works for lanes by
quotient. `coupling[(src, dst)]` in `plan-graph.py` is already keyed by epic pair; mapping epic
→ lane turns it into a lane-pair count with no new walk.

**Moving work between lanes is therefore moving a story between epics**, which is a reorg —
`reparent-story`, the validator, the derivation, the journal. It re-keys the story and
`l3io-sync` re-points its remote issue. That is heavier than dragging a card between columns,
and deliberately so: a lane move gets the same scrutiny as any other re-placement.

## 3. Where each fact lives

The existing config layers already give the right split, which is what makes "generic, not
named" enforceable rather than merely conventional.

| Fact | Where | Committed |
|---|---|---|
| How many lanes this project runs | `modules.l3io-pm.lane_count`, set at setup | **yes** — team |
| Which lane owns this epic | `lane:` on the epic node | **yes** — state |
| **Which lane I am** | `modules.l3io-pm.lane`, user layer | **no** — gitignored |

The name of a human **cannot reach the repository**, because the only file that knows it is not
tracked. The partition is structural and public; identity is personal and local.

### 3.1 The field name is a guardrail

`owner:` would attract names — within a month someone commits `owner: sarah` and the generic
concept erodes by default rather than by decision. **`lane:`** makes `sarah` look obviously
wrong in it. Same reasoning that makes `TAC_HEADING` load-bearing: the vocabulary enforces the
constraint.

Reinforced mechanically: reject a `lane` value containing `@`, or longer than a short token.
Cheap, and it fails when someone tries rather than at review.

### 3.2 Setup asks

`/l3io-setup` asks how many lanes the project runs and writes `lane_count` to the team layer.
**Absent or `1` means lanes are off**, and nothing in this design applies — single-developer
use is the overwhelming majority and must not pay for a feature it does not use.

Individuals set their own `lane` in the gitignored user layer; nothing asks them to commit it.

## 4. The four shared files

Disjoint epic directories merge cleanly. Exactly four files do not, and they are not equally
hard — which is the useful finding.

| File | Behaviour across clones | Answer |
|---|---|---|
| `events.jsonl` | Both sides append different lines | `merge=union` in `.gitattributes` — literally the right semantics; there is no `.gitattributes` in the repo today |
| `pm-calibration.yaml` | Order-independent samples | A lost sample **degrades estimates without corrupting state** — the one tolerable failure here |
| `issues.yaml` | `next:` is **per-epic**, so disjoint owners allocate disjoint keys | Textual conflict only, no semantic collision |
| `adr-register.yaml` | A **global** `next:` | The one real collision — see below |

**ADR numbers already have their answer, in a verb built for another reason.**
`adr-reserve --count N` allocates a contiguous block. Run at *plan* time by whoever assembles
the assignment, it gives each lane a reserved range, committed in the same push everyone starts
from. A reservation made **before the fork needs no lock at all**, which is why the flock's
inability to cross clones stops mattering.

## 5. Execution protocol

**Everything is committed and pushed before execution begins.** This does not eliminate the
merge; it bounds it. Everyone forks from one commit, each lane writes only its own epic
directories, and integration has a known, four-file surface rather than an open one.

## 6. What the dependency map must warn about

A story moving between lanes has three outcomes, and only one is dangerous.

1. **Clean** — its dependencies travel with it. Lanes stay independent.
2. **Leaves a vestige** — the old epic dependency is now unjustified. Already detected:
   `unneeded-epic-dependency`.
3. **Serialises two lanes** — after the move, a story in Lane 2's epic depends on one in Lane
   1's, so Lane 2's epic needs `depends_on` Lane 1's. **Two parallel developers become a
   queue.** Already detected as `unbacked-cross-epic-dependency`; lanes make the *consequence*
   legible — "this makes Lane 2 wait for Lane 1" rather than "E003 needs depends_on E001".

So the warning composes from findings that already exist. The new finding is
`cross-lane-dependency`, mirroring `cross-epic-coupling` with lane labels.

**Warn, never refuse.** Sometimes the right answer is to accept the serialisation. Consistent
with every other judgement in this package: report the measurement, name the consequence, let a
human decide.

## 7. Enforcement

**Opt-in and escapable**, both from the start:

- **Unset means unrestricted.** No `lane_count`, or no `lane` in the user layer → no checks. A
  partition feature that taxes single-developer use gets turned off and then rots.
- **There must be a `--force`.** A hotfix, an underestimated dependency, a colleague on
  holiday. A hard refusal with no escape gets worked around by deleting the field, which is
  worse than a warning. Same shape as `set-depends-on --force`.

## 8. What this does NOT solve

**Source-file collisions.** The phase graph proves two epics have no `depends_on` between them.
It says nothing about whether both rewrite `auth/session.py`. Committing beforehand gives a
clean start and says nothing about two lanes diverging on the same file for a week — the
failure that makes teams abandon parallel work, and the one invisible to every signal here.

That is the **functional-area axis**, and the data to compute it does not exist: story
enrichment already asks the agent to *"list the files the story will add or change"*, but that
lands in the story document's prose, not a queryable field. A `touches:` field on a story node
would make file independence computable and turn lane assignment into a partition over two edge
types rather than one.

Out of scope here, and named so nobody reads lane isolation as more than it is.

## 9. `l3io-sync` later

Sync today carries **title, body, labels and a key mapping** — an issue-tracker bridge, not a
state channel. Estimates, actuals, calibration and events do not cross it.

The better division, when we get there, is not to widen it into a database: the **remote answers
"who is doing what, and is it done"** — the question a team actually needs — while estimates and
calibration stay local history that merges by union and degrades gracefully.

## 10. Resolved

Settled 2026-10-11.

**1. The epic declares its lane.** A registry (`state/lanes.yaml`: lane → epics) would be a
*fifth* shared file, and the one file **every** lane writes — reassigning any epic touches it,
so it collides precisely when lanes are most active. A field on `epic.yaml` lives in a file only
its owning lane writes. The cost is that "what does Lane 2 own" is derived by scanning epics
rather than read from one place; that is a `dump-plan` query, not a problem.

**2. `plan-graph.py` proposes the partition — when there is something to propose.** The trigger
is `lane_count > 1` **and no epic declares a lane**. That second condition is self-describing:
"never been set" needs no ledger, because an unset tree says so. Once lanes are assigned the
proposal never fires again — an existing partition is a decision, not a gap.

**3. The hand-off artifact is a filter.** "The plan, Lane 2's view" is generated from the
snapshot on demand. A per-lane document would be a second source of truth and would go stale
the first time the plan is re-run — the problem `estimates_as_of` already exists to make
visible. It may be *rendered* to a file, but the rendering carries the snapshot's identity so a
printed copy says which plan it came from.

## 11. Proposing a partition

`nx.community.greedy_modularity_communities(U, best_n=k, cutoff=k)` over the **undirected**
epic graph — crossing is direction-free — yields exactly `k` groups. Measured on an eight-epic
fixture with two natural clusters: `k=2` finds them with **zero** cross-lane edges; `k=3` costs
**two**.

**That second number is the point.** Asking for more lanes than the work supports has a price,
and the proposal must state it: *"You asked for 3 lanes. The work splits naturally into 2; a
third costs 2 cross-lane dependencies."* A lead deciding whether to put a third person on this
needs that before assigning, not after.

**Report two things, because they are different objectives.** Minimising cross-lane edges and
keeping every lane busy are not the same: a partition perfect by connectivity can leave Lane 2
with nothing until Lane 1 finishes. So the proposal reports cross-lane edges **and** per-lane
phase coverage — a lane owning epics in phases 1–3 is busy throughout; one owning only phase-3
epics waits.
