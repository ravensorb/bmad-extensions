# `/l3io-plan reorg` — detect, propose and apply a better plan shape

**Date:** 2026-10-09
**Status:** proposed
**Relates to:** ADR-0004 (human-authored documents are proposal-only), ADR-0005 (ADR numbers
come from `adr-reserve`), ADR-0010 (config scalars vs arrays)

## 1. Problem

`l3io-plan` validates that a plan is *runnable* — no dependency cycles, no invalid references,
a topological phase order. It never asks whether the plan is *well shaped*. A plan can be
perfectly legal and still group unrelated work into one sprint, scatter one concern across
three epics, serialise work that could run in parallel, or carry epics nobody needs.

Today step-05 **halts** on a cycle. That is correct and also the end of the help it offers: the
user is told their plan is broken and left to re-shape it by hand.

## 2. What good looks like

This section is the acceptance criterion for the whole feature. Everything below serves it.

### 2.1 The outcome, stated plainly

**A good reorg is one the user can evaluate in about a minute and then accept or reject with
confidence.** Not one that produces the mathematically optimal arrangement. A proposal nobody
can check is worse than no proposal, because applying it is an act of faith over their plan.

That has three consequences, and they drive the design more than the algorithm does:

1. **Every proposed move carries its reason, and the reason cites evidence** — a measured
   signal, not an assertion. "These three stories all point at `auth.md#token-refresh`" is
   checkable. "These belong together" is not.
2. **The report leads with the delta, not the arrangement.** What changes about time, effort,
   cost, risk and ordering — then the moves that produce it.
3. **Rejecting is free and partial acceptance is possible.** The user can decline the whole
   proposal, or decline the retirements and keep the moves.

### 2.2 Hard constraints — a proposal that violates any of these is refused, not shown

These are mechanical and non-negotiable. Validation judges the **target state** (§5.3.1) and
refuses it whole, naming the offending row — not the derived operations, which are this
tooling's own output and cannot be wrong independently of the target that produced them.

- The resulting epic graph is **acyclic**.
- No story or epic is ordered before something it `depends_on`.
- **Nothing outside `planned/` is written.** Active and archived work is read-only input.
- Every `key` in the target resolves to a node that exists today in `planned/`.
- The target is **total**: every planned story appears exactly once across `target` and
  `retire`. An omitted node is an error, never an implied "leave it alone".
- No retirement orphans a dependent that is not also retired.
- The allocator can supply every new key.

### 2.3 The objective — one primary, stated, with guardrails

Optimising several things at once produces proposals nobody can argue with or against. So:

**Primary objective: reduce the cost of discovering a problem late.** Concretely, minimise the
**critical path** — the longest `depends_on` chain weighted by `elapsed_hours` estimate —
because every hour on it is an hour where nothing else can proceed and a late discovery
invalidates the most downstream work.

**Guardrails — a proposal that regresses any of these needs a stated reason in its rationale,
and the report shows the regression rather than hiding it:**

| Guardrail | Measured as |
|---|---|
| Cross-epic coupling | count of `depends_on` edges crossing an epic boundary |
| Sprint cohesion | overlap of `Spec:` anchors cited by stories within a sprint |
| Sprint balance | spread of sprint `elapsed_hours` estimates within an epic |
| Total effort | summed `estimate-rollup` across all five metrics |

**Total effort is a guardrail, not an objective.** A reorg that reduces the critical path by
moving work off it has not made the work smaller; it has made it more parallel. Treating effort
reduction as the goal would make retirement — deleting scope — the highest-scoring move
available, which is exactly the wrong incentive to give this.

### 2.4 What a good *report* contains

Because §2.1 makes the report part of the deliverable rather than a byproduct:

```
REORG PROPOSAL — 4 moves, 1 retirement
================================================================
Critical path   18.5h → 12.0h   (-6.5h, -35%)
Cross-epic deps        7 → 3
Sprint cohesion     0.41 → 0.68   (spec-anchor overlap)
Total effort          — unchanged beyond the retirement (-3.0h)
Cost              $41.20 → $38.10

WHY
  E007-S02 blocks three epics and contains one story that does not
  belong to it: E007-S02-004 cites only auth.md#token-refresh, which
  E003's stories also cite. Moving it to E003-S01 removes the block.
  → evidence: 3 depends_on edges removed; anchor overlap 0.0 → 0.8

MOVES
  E007-S02-004  →  E003-S01-005    (new key; was E007-S02-004)
  …
RETIRE
  E041  "Legacy export shim"  — nothing depends on it, resolves no
        backlog item, and its spec anchor was removed in docs/adr/0008
        → archived/, not deleted; recoverable with `undo`
```

### 2.5 Explicit non-goals — what "good" does *not* mean

- **Not "the optimal plan."** This proposes one improvement, shows its evidence, and stops.
- **Not autonomous re-planning.** It does not add, split or invent work. It moves, reorders and
  retires what is already planned.
- **Not a substitute for judgment about scope.** Retirement proposals are the weakest
  recommendations in the system and are always confirmed separately.

### 2.6 How we will know it worked, after shipping

- A reorg the user **accepts** should show its predicted critical-path reduction in the next
  plan's phase structure — the prediction is checkable against the plan it produces.
- A reorg the user **rejects** is a signal about the objective function, not a failure of the
  run. Rejections should be rare and, if they are not, the signals are wrong.
- **`undo` should be nearly unused.** It exists so accepting is safe. Frequent use means the
  report is not conveying what the proposal actually does.

## 3. Complexity — an honest assessment

This is **substantially harder than the agent-instruction block**, and most of the difficulty is
not in the analysis. It is in the fact that *every move re-keys a node*.

### 3.1 What makes it hard

**Re-keying is unavoidable and far-reaching.** A story key `E{nnn}-S{nn}-{nnn}` encodes both its
epic and its sprint, so moving a story *anywhere* — even between sprints of the same epic —
changes its key. `parse_story_key` has **15 call sites** in `pm-status.py`: the key is how the
resolver finds a story's file, its epic write lock, and its event records. The alternative —
decoupling key from location — breaks the invariant check 26 exists to protect.

**A re-key invalidates references the moving node does not own:** other nodes' `depends_on`,
backlog items' `ref`, the story document's own frontmatter `key:`, its filename on disk, and
`l3io-sync`'s `sync-state.yaml` mapping to a remote issue.

**Keys are currently reusable, and that is a correctness bug waiting for this feature.**
`_next_story_key` is "highest on disk + 1", so a vacated number is immediately reusable. If
story A moves out of `E032-S01-001` and story B moves in and takes that key, then sync's
mapping still points issue #412 at `E032-S01-001` — which now resolves to *different work*. The
issue is silently retargeted and nothing errors. **This must be fixed before reorg is safe**,
and the fix is a prerequisite, not part of the feature.

**Two documented invariants do not contemplate this operation.** The placement rule says
sprints and stories "travel with" their epic and are "never moved independently"; the two-trees
rule says artifacts are "never moved". Both were written about *status transitions*. Re-parenting
is a second axis they never considered, and amending them needs an ADR.

### 3.2 What is straightforward

- The analysis signals are computable from data that already exists: `depends_on`, estimates,
  `work_type`, and `spec-align`'s anchor index.
- Cycle detection and the topological sort already exist in step-05.
- Impact needs no new estimation logic — it is `estimate-rollup` run against the proposed shape
  and diffed.
- Retirement is the *cheap* operation: a `git mv` to `archived/`, no re-key.
- `undo` is tractable because the journal records the pre-state and keys are never reused, so
  the original key is still free.

### 3.3 Rough size

Re-assessed after the target-state change (§5.3). That change does **not** make this smaller —
it adds a format, a validator for it, and a derivation step. It makes it **safer**, by moving
work out of the agent's hands and into testable mechanical code. That is the trade, stated
plainly.

| Piece | Size | Risk | Changed by target-state? |
|---|---|---|---|
| Per-sprint key allocator (prerequisite) | small | **high** | — |
| `reparent-story` / `reparent-sprint` / `retire-node` verbs | large | **high** | — |
| Analyzer (mechanical signals) | medium | low | — |
| Target format + parser + validator | small | medium | **new** |
| Derivation: current ⊖ target → ordered operations | medium | medium | **new** |
| ~~Proposal (operation-list) validator~~ | — | — | **removed** |
| Journal + `undo` | small | low | **simpler** — undo is the previous target re-applied |
| Sync reconciliation via `previous_keys` | small | medium | — |
| Mode prose, report rendering, confirmation | medium | low | — |

**Six to eight tasks**, one more than before. The allocator still lands and releases
*separately*, ahead of everything else, because it changes key allocation for every project
whether or not they ever reorganise.

### 3.4 Where this most likely goes wrong

Re-assessed. Two of the four original failure modes are now substantially harder to reach.

1. **A partial apply.** Half the operations land and the tree is neither shape.
   **Reduced.** Still possible, but no longer silent: re-diffing current against the target
   answers "what is left?" exactly. Mitigated further by one epic write lock around the
   application and the migration engine's gate-before-write ordering.
2. **The objective rewards the wrong thing.** See §2.3 — effort as an objective makes deleting
   scope the best available move. **Unchanged, and still the subtlest risk here.** No amount of
   mechanical validation catches a proposal that is legal, correctly applied, and wrong.
3. **Silent reference rot** — a `depends_on` or `ref` pointing at a key that no longer exists.
   **Reduced.** The validator judges the post-state derived from the target rather than
   reasoning forward through an operation list, so a dangling reference is a property of a tree
   that can be checked directly.
4. **The user cannot evaluate the proposal.** **Unchanged, and now the largest risk in the
   feature.** It is the failure §2 is written to prevent and the one least likely to appear in
   any test, because every test asserts a property the code has; none asserts that a human
   understood the output. The only real mitigations are that the report leads with the delta,
   every move cites measured evidence, and rejection is cheap.

**A risk the target-state model introduces:** the target is *total*, so a proposal touching four
stories still enumerates every planned story. A reviewer skimming it could miss a row that moved
among dozens that did not. This is why the **report is rendered from the derived diff, never
from the target** — the user reads moves, not the placement table. If that ever inverts, the
feature loses the property §2.1 exists to protect.

## 4. Scope

**Writable:** epics in `planned/`, their sprints and stories.
**Read-only input:** `active/` work that is not complete, and `archived/`, for dependency
satisfaction and ordering constraints. A proposal that would require writing them is refused at
validation, never silently trimmed.

## 5. Mechanics

### 5.1 The allocator (prerequisite)

A per-sprint `next:` high-water on the sprint node, seeded on first use from `max(on disk)`,
never decreasing — modelled on `issues.yaml`'s per-epic allocator, which exists for exactly this
reason and is documented as "a high-water mark that never decreases, so a deleted or resolved
key is never reused". Needs an audit finding for a stale value and a `reseed`-style repair, both
of which have a shape to copy.

### 5.2 Two operations, deliberately distinct

**Re-parent** (changes identity, re-keys): moves the state node, the story document, rewrites
the document's frontmatter `key:`, and rewrites every inbound `depends_on` and `ref`. The
optional `-slug` filename suffix is preserved verbatim. Both trees move together under one epic
write lock; if either half fails, neither commits.

**Retire** (changes status, no re-key): `git mv` the state directory to `archived/`. Artifacts
stay — that is the existing placement rule, unchanged. **Never deleted** unless explicitly
asked.

### 5.3 The engine — target state in, operations derived

**The agent proposes a target placement. It never proposes operations, and it never names a
new key.** The tooling diffs current against target and derives the operations itself.

1. **Analyze** (script): emits findings, each with an id, the nodes involved, a *measured*
   value, and what it suggests. Signals per §2.3 plus cycles, inversions and blocked-by-active.
   **An orphan — a story nothing depends on — is reported as a question, never as a retirement
   finding.** Leaf work is often the actual deliverable.
2. **Propose** (agent): reads the findings plus story content and the spec index, writes a
   **target placement** (§5.3.1) with rationale per group.
3. **Validate** (script): judges the *target* against §2.2 and refuses it whole, naming the
   offending row. Agent output never reaches disk unvalidated.
4. **Derive** (script): diffs the current planned tree against the target and emits the
   operation list — re-parents, creations, retirements — in dependency-safe order.
5. **Apply** (script): executes that list under one lock, gate before write.

#### 5.3.1 The target format, and why it is deliberately impoverished

```yaml
target:
  - key: E007-S02-004        # the node's CURRENT key — the agent never writes a new one
    epic: E003               # where it belongs
    sprint: S01              # sprint within that epic; may not exist yet
    order: 5                 # position within the sprint
  - key: E007-S02-005
    epic: E007
    sprint: S02
    order: 1                 # unchanged rows are allowed and are a no-op
retire:
  - key: E041
    reason: "…"
```

**Placement and ordering are the only things expressible.** No titles, no estimates, no
`depends_on` edits, no new keys. This is the whole safety argument for handing a target tree to
an agent: drift is not mitigated, it is **unrepresentable**. An agent that wanted to quietly
reword a story has nowhere to put the words.

It is also *smaller* than the operation list it replaces, because an unchanged row is one line
and a move is the same one line with different values.

**The target must be total over the planned set.** Every planned story appears exactly once in
`target` or once in `retire`. An omission is a **validation error, not an implied "leave it
alone"** — silence is the one thing a target state must never mean, because an agent that
forgets a node and an agent that intends to leave it are indistinguishable, and the second is
far more common.

#### 5.3.2 What the derivation handles that an operation list hid

- **A target sprint or epic that does not exist yet** is created as part of the derived
  operations, in dependency order, before anything moves into it.
- **Key assignment is entirely the allocator's.** The derivation asks for the next key in the
  destination sprint; the agent's target never contains one.
- **Ordering within a sprint** is normalised from `order` to the allocator's sequence, so the
  agent may use any monotonic integers — gaps and ties are resolved mechanically rather than
  being an error it has to avoid.
- **"What is left?"** is answerable at any time by re-diffing current against target, which is
  what makes a partial apply detectable rather than silent.

### 5.4 Impact

`estimate-rollup` run against the proposed structure, diffed against current, across all five
metrics. No new estimation logic. `cost` derives from `tokens_k` so it cannot drift from the
token delta.

### 5.5 Confirmation

`modules.l3io-pm.reorg_auto_apply`, a scalar (ADR-0010's merge reasoning): `never` (default),
`moves` (apply moves, still confirm retirements), `always`. Pre-authorisation skips the
**prompt**, never the **record**. All interaction is conversational — no flags (check 31).

### 5.6 Journal and undo

`state/reorg-log.yaml`: per reorg an id, timestamp, the verbatim proposal, the rationale, the
pre-state tree hash, and every operation with enough to invert it — including prior `depends_on`
values, which no surviving node carries.

Nodes carry **`previous_keys`** — an ordered list, oldest first, appended to. Not a single
`previous_key`: a node reorganised twice would lose its first hop, breaking sync reconciliation
for anything mapped before the first reorg.

`undo` recomputes the planned-tree hash and **refuses if anything changed since**, listing what
differs. Because keys are never reused, undo restores the *exact* prior key.

Under the target-state model undo is simply **the previous placement re-applied**: the journal
stores the pre-reorg placement as a target, and undo runs the same derive-and-apply path
forward. There is no separate inverse-operation code to write, and therefore no second code
path that can be wrong in a way the forward path is not.

### 5.7 Sync reconciliation

One rule added to `l3io-sync` step-04: before treating a `missing_local` as a deletion, look for
a node whose `previous_keys` contains that key and `upsert` the mapping to the new key. Platform
-agnostic by construction — it reconciles on our key, not the remote's, so it fixes GitHub, ADO
and a future Jira identically.

## 6. Invariant amendments

The placement rule and the two-trees rule become explicitly about *status transitions*. A new
rule covers re-parenting: a re-parent moves the state node and its artifact siblings together,
in one operation, preserving the identical-path-suffix mirror. **Needs an ADR, with its number
taken from `adr-reserve` at implementation time** — not chosen here, per ADR-0005.

## 7. Testing

- Analyzer and validator: pure functions over fixture trees.
- Every validator refusal gets a test that plants the violation it must catch.
- `undo` round-trip: reorg → undo → tree byte-identical to pre-state.
- The hash guard refuses after an intervening write.
- Sync reconciliation for the **two-hop** case — the one a single `previous_key` would break.
- Allocator: a vacated key is never reissued; a stale `next` is audited and repairable.
- **Partial-apply survival:** kill the application mid-way and assert the tree is the old shape,
  not a hybrid. Then assert a re-diff against the target reports exactly the outstanding work —
  the property the target-state model exists to provide.
- **The target format cannot express drift:** a target carrying a `title`, an `estimate` or a
  `depends_on` is rejected by the parser, not ignored by it.
- **Totality:** a target omitting one planned story is refused, and the message names the story.
- **Derivation:** a target requiring a sprint that does not exist creates it before moving into
  it; `order` values with gaps and ties normalise deterministically.
- **The agent never supplies a key:** a target whose row carries a destination key is refused.

## 8. Out of scope

- Reorganising active or completed work.
- Rewriting `events.jsonl` — it is append-only; a moved story's history stays under the key it
  had, and the journal ties the two together.
- Adding, splitting or inventing work.
- Model-selection advice (see the follow-up below).

## 9. Named follow-up

**Per-model calibration.** `actual.model` is already recorded and mandatory, and
`completion_evidence.fix_iterations` sits on the same node, so "model X on class Y reworked N%
of the time" is learnable. Recommending a model on rate-card price alone would systematically
pick the *more expensive* option, because a cheaper model that needs two extra fix iterations
costs more — fix iterations are turn multipliers and session cost grows with the square of turn
count. This needs a `pm-calibration.yaml` schema migration and is its own piece of work.
