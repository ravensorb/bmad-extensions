# Parallel Lanes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let several developers, each with their own BMad install and agents, work one plan
concurrently — and make the collisions that remain visible rather than discovered at
integration.

**Spec:** `docs/superpowers/specs/2026-10-11-parallel-lanes-design.md`

**Why this is cheap:** `1 epic = 1 lane` makes the lane graph the epic graph with **relabelled
nodes** — a colouring, not a second graph. `coupling[(src, dst)]` in `plan-graph.py` is already
keyed by epic pair, so lanes ride on computations that exist. Had a story been lane-assignable
independently of its epic, every cross-lane question would have needed its own traversal.

## Decisions

Settled 2026-10-10/11. Recorded so no task re-opens them.

| # | Decision | Rationale |
|---|---|---|
| D1 | **The epic declares its lane** (`lane:` on `epic.yaml`) | A registry would be a fifth shared file, and the one file *every* lane writes — colliding precisely when lanes are most active |
| D2 | **Field is `lane`, never `owner`** | `owner` attracts names; `lane` makes `sarah` look wrong in it. The vocabulary is the guardrail |
| D3 | **Setup ASKS the mode** — single-developer or multi-lane — and records `lane_count` in the team layer; **`lane` identity in the gitignored user layer** | The mode is a decision, not an inference. A person's name cannot reach the repo, because the only file that knows it is untracked |
| D4 | **`lane_count` absent or `1` → lanes off.** Absent means never asked; `1` means deliberately single. Behaviourally identical, factually different | Single-developer use is the majority and must not pay for a feature it does not use. Absent cannot prompt — `config-resolution.md` §5 makes an absent module section a valid permanent state |
| D5 | **Warn, never refuse**, on cross-lane dependency; `--force` on any enforcement | A hard refusal with no escape gets worked around by deleting the field |
| D6 | **The mode is CONFIGURED, never inferred.** Propose when `lane_count > 1`; the epic scan only gates whether assignment already happened | Deriving the mode from epic state makes "not assigned yet" indistinguishable from "runs single-developer" |
| D7 | **Hand-off is a filter, not a document** | A per-lane document is a second source of truth and goes stale on the next plan run |
| D8 | **Moving work between lanes is a reorg** | 1 epic = 1 lane means a lane move is an epic move, which re-keys the story. Heavier than a field change, and deliberately so |

## Global Constraints

- **This repo's `CLAUDE.md` does not ship.** Everything a consuming agent must follow belongs in a step file or a script docstring.
- `skills/_shared/` is canonical. **Edit there, then `npm run sync:scripts`**, then `node scripts/write-payload-manifest.mjs`.
- **Run `npm run test:python` and `npm run test:scripts` after changing any value**, not a subset of `check:*` gates. A value asserted in a test is invisible to every docs-family gate by construction — that is how a red build got tagged on 2026-10-11.
- Run PEP-723 suites with `uv run`, never bare `python3`: the wrong runner manufactures failures that bury the real one.
- **Check 26:** no file under `skills/` assembles a state path.
- **Check 31:** no `/l3io-*` invocation in markdown carries a `--flag`.
- **Check 34:** no runtime directive asks a user to hand-edit — the human decides, the agent edits.
- `pm-status.py` takes **no graph library** (616 ms import against 92 call sites). Graph work lives in `plan-graph.py`.
- Conventional Commits, signed off (`git commit -s`).

## Review Focus

Input classes the goal implies that no happy path exercises.

1. **A project with `lane_count` unset, or set to 1.** Every lane behaviour must be inert, and **unset must prompt nothing** — an absent module section is a valid permanent state, so a feature that treats it as a first-run breaks that contract. This is the majority case and the one most likely to be broken by a feature that assumes it is on. → Tasks 1, 2 and 4.
2. **An epic with a `lane` the config does not know about** — `lane_count: 2` and an epic declaring lane 3, after someone lowered the count. Report; do not crash. → Task 2.
3. **A partially assigned tree** — some epics carry `lane`, some do not. D6's trigger is "no epic declares a lane", so this must *not* re-propose, and the unassigned epics must be visible rather than silently lane-less. → Task 5.
4. **More lanes than the graph supports.** `k=3` on a two-cluster graph cost 2 cross-lane edges in testing. The proposal must state the price, not silently produce a worse partition. → Task 5.
5. **A lane that owns only late-phase epics.** Connectivity-optimal can leave a lane idle until another finishes. Cross-lane edges and phase coverage are different objectives and both must be reported. → Task 5.
6. **A lane value that is a person's name.** D2 is a convention until something rejects `sarah` and `s@example.com`. → Task 1.

---

## Phase A — the field and the config

### - [ ] Task 1: `lane` on the epic node, with validation

- Schema in `skills/_shared/status-files.md`: `lane` is an optional scalar on an **epic** node only. Sprints and stories inherit it from their directory and must never carry one.
- Writing it: `set-field --epic E001 --field lane --value A` already works mechanically. Add a field-specific rule, the same shape as the existing refusal of `completion_evidence.tests_passing`: reject a value containing `@`, or longer than a short token, naming D2's reasoning. A convention nothing enforces is a convention that erodes.
- **Tests:** accepted on an epic; refused on a sprint or story; a name-shaped value is refused; absent is normal and never an error.

### - [ ] Task 2: setup asks the mode; `lane` in the user layer

**`l3io-setup` asks whether the project is single-developer or multi-lane, and records the
answer.** On multi-lane it asks how many and writes `modules.l3io-pm.lane_count` to the **team**
layer (`custom/config.toml`); single-developer writes `lane_count: 1`.

The question is the point. Inferring the mode from whether a number happens to be set makes
lanes discoverable only by reading documentation, and makes *"we never asked"* indistinguishable
from *"they chose one developer"*.

- Three states, two behaviours: **absent** (never asked) and **`1`** (deliberately single) both
  mean lanes off; `N > 1` means on. Absent must **never prompt** — `config-resolution.md` §5
  makes an absent `modules.l3io-pm` section a valid permanent state.
- `{lane}` resolves from `modules.l3io-pm.lane` in the **user** layer
  (`custom/config.user.toml`, gitignored). Document in `config-resolution.md` that it belongs
  there and why: the name must not reach the repo.
- An epic declaring a lane outside `1..lane_count` is **reported, not fatal** (Review Focus 2).
- **Tests:** unset behaves exactly as today and prompts nothing; `lane_count: 1` likewise;
  `N > 1` turns lanes on; an out-of-range lane is reported; setup run twice does not duplicate
  or re-ask destructively.

---

## Phase B — making lanes visible

### - [ ] Task 3: `dump-plan` emits `lane`

One line, same shape as adding `previous_keys` to stories. Without it nothing downstream can
see lanes, since check 26 forbids them reading state directly.

### - [ ] Task 4: `cross-lane-dependency` in `plan-graph.py`

- Map epic → lane, relabel the existing `coupling` dict. **No new traversal.**
- New finding `cross-lane-dependency`, mirroring `cross-epic-coupling`, carrying the lane pair and edge count.
- Severity: `warn` — unlike `unneeded-epic-dependency`, a reorg *can* act on this by moving the story.
- **Silent when lanes are off** (Review Focus 1).
- **Tests:** fires on a story edge crossing a lane boundary; silent within a lane; silent when no epic declares a lane; the lane pair is reported, not just the epic pair.

### - [ ] Task 5: propose a partition when there is one to propose

Trigger: **`lane_count > 1`** — the configured mode (D6), never inferred from the tree. A
second condition, *no epic declares a lane yet*, gates only whether assignment has already
happened, so an existing partition is not re-proposed. That is a guard on the action; the mode
comes from setup.

- `nx.community.greedy_modularity_communities(U, best_n=k, cutoff=k)` over the **undirected** epic graph — crossing is direction-free.
- Report **both objectives**, because they differ (Review Focus 5): cross-lane edge count, and per-lane phase coverage. A lane owning only phase-3 epics waits.
- **State the price of over-partitioning** (Review Focus 4). Measured on an eight-epic fixture: `k=2` gives zero cross-lane edges, `k=3` costs two. Say so — *"the work splits naturally into 2; a third lane costs 2 cross-lane dependencies"* — before a lead assigns a third person.
- Propose, confirm, then write `lane` to each epic. Never assign without confirmation.
- **Tests:** two natural clusters at `k=2` give zero crossings; `k=3` reports the cost; a partially assigned tree does not re-propose; determinism.

---

## Phase C — the hand-off

### - [ ] Task 6: the per-lane view

A **filter** over the plan snapshot (D7), not a new document. Shows the lane's epics, its
phases, what it waits for, what waits on it, and its reserved ADR block.

May be rendered to a file, but the rendering carries the snapshot's identity so a printed copy
says which plan it came from — the problem `estimates_as_of` exists to make visible.

### - [ ] Task 7: the execution protocol, written down

- `.gitattributes` with `merge=union` for `state/events.jsonl` — append-only and line-oriented, so union is literally the right semantics. There is no `.gitattributes` in the repo today.
- A step file documenting the protocol: commit and push before execution; each lane writes only its own epic directories; `adr-reserve --count N` per lane at plan time, **before the fork**, because a reservation made before the fork needs no lock.
- State plainly what this does **not** solve: source-file collisions. The phase graph says nothing about two lanes both rewriting `auth/session.py` — the failure that makes teams abandon parallel work, invisible to every signal here.

---

## Validation Strategy

| Probe | Asserts |
|---|---|
| A tree with no `lane_count` | every lane behaviour inert — the majority case |
| Two natural clusters, `k=2` then `k=3` | the partition is found, and over-partitioning reports its price |
| A story edge crossing a lane boundary | `cross-lane-dependency` fires with the lane pair |
| A partially assigned tree | no re-proposal; unassigned epics visible |
| `lane: sarah` | refused |

**Mutation testing required** for Task 1 (drop the name validation → its test must fail) and
Task 4 (drop the lanes-off guard → the inert test must fail).

**Gates:** all seven, `test:python`, `test:scripts`, and `smoke:install` before release.

## Risks

- **A partition proposal is an opinion with authority.** A lead may take it as correct because it is computed. The report must show its cost — cross-lane edges and idle phases — so it reads as a trade rather than an answer.
- **Lanes make the source-file gap worse, not better.** More parallelism against one working tree per lane, with no independence check. Named in Task 7 rather than discovered.
- **D4 is load-bearing.** If lanes-off is not genuinely inert, a feature serving a minority of projects taxes all of them, gets disabled, and rots.
