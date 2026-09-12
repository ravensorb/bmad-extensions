# Glossary

Terms and enum values this package uses. Where a value is one of a fixed set, the set is given
— those are the ones worth looking up, because most of them are enforced and an invalid value
is rejected rather than coerced.

### ADR — Architecture Decision Record

A recorded decision, written to `{project-root}/docs/adr/NNNN-slug.md` — the one ADR home.
Numbers are allocated from `state/adr-register.yaml` by `pm-status.py adr-reserve` under a lock,
*before* any ADR agent is dispatched, so parallel reviewers cannot both claim the same number. A
directory listing shows who has finished, not who is in flight.

### backlog item kind

One of **`defect`** (the default, and assumed when the field is absent), **`spec-change`**, or
**`spec-proposal`**. The two spec kinds each require a `--ref` — the commit that changed the
spec, or the proposal file — and are confirmed or rejected in `/l3io-util-doctor triage`.

### calibration component

One of the separable ratios estimation learns, per metric: **scope** (story sizing, per
classification), **closure** (sprint- and epic-level overhead), **fix** (the fix loop's cost, as
`clean` and `reworked` cohorts), and **orchestration** (see below). Scope and closure activate at
three samples; fix needs three in *both* cohorts, so a project where every story needs rework
never activates it and correctly stays on the cold-start prior.

### classification

A story's size class — **simple**, **standard**, or **complex**. Selects the model used for the
story and is the key under which scope calibration is learned.

### closure

The wrap-up phase at the end of a sprint or an epic: retrospective, drift review, security
review, UX review, triage, and a report. Nothing closes while a Critical, High or Medium finding
is unresolved.

### disposition

How a drift finding was settled. One of **`resolved-in-code`**, **`adr-justified`**,
**`spec-updated`**, or **`spec-proposal`**. The last two require spec alignment to be on and a
`--spec` pointer; `spec-updated` is refused for anything but an architecture section, because
PRD, UX and epic documents are proposal-only.

### drift

The gap between what was planned and what was built. The architectural drift review compares an
epic's cumulative diff, ADRs and story files, gives every finding an ID, and requires a
disposition for each BLOCKER or MAJOR before closure is allowed.

### dwell time

How long a node has sat in its current status. Computed from the append-only event log, because
`updated_at` is refreshed by any field write and so cannot measure it. Without the log, dwell
falls back to `updated_at` and is displayed with a `~` prefix to mark it approximate.

### epic

The top-level unit of work. One directory per epic, living in the folder named for its status;
status flows `backlog → in-progress → done`. Every status change moves the whole directory, so
sprints and stories travel with it.

### estimate and actual

Every planning point and every closeout records both, for five metrics in this order:
`elapsed_hours` (wall clock), `man_hours` (a counterfactual assessed at closure — what a
developer would have taken by hand), `hitl_hours` (human attention actually spent), `tokens_k`,
and `cost`. Cost is never entered; it is derived from tokens and the model's rate table, and a
`--cost` flag is refused outright.

### headless dispatch

A subagent invocation carrying `headless: true` in its context block: it runs without
interactive prompts and skips the activation work its orchestrator already did, using the
bindings it was handed. This is how a sprint's story agents are launched.

### lease

A holdable claim on spec editing (`state/spec-sync.lock`), taken by an epic closure's spec sync.
Parallel epic closures share one working tree, so without it two of them could edit one
architecture document at once, or one could commit the other's half-finished edit. A closure
that cannot take the lease defers gracefully rather than failing.

### lens

One of the viewpoints `l3io-sec-redteam` analyses from — external attacker, malicious insider,
chaos engineer, abusive legitimate user, and a design red team — with an AI-poisoning cross-cut
applied across them when AI components are in scope. The cross-cut is not a sixth lens.

### node

The generic addressable unit — an epic, a sprint, or a story. Every operation addresses one by
key (`--epic`, `--sprint`, `--story`) rather than by path, so only one place in the system
resolves a key to a file location.

### orchestration band

A fourth calibration component, keyed by level (sprint or epic). Unlike the others it learns a
*fraction* of its children's actuals rather than a ratio, and it ships unseeded — there is
nothing to measure it against until real observations are recorded.

### phase

A group of epics that may run concurrently, computed at plan time by a topological sort over
`depends_on`. Epics within a parallel phase run concurrently up to a configured limit; sprints
within an epic are always sequential.

### provenance

Used two ways. On a story, whether its acceptance criteria carry resolving `Spec:` pointers — a
story with no technical-AC section at all is *pre-provenance*. On a calibration sample, how the
sample was derived: `exact`, `backout`, or `legacy`.

### readiness

A plan's gate value — **green**, **amber**, or **red**. Any red finding makes the plan red,
which blocks execution; amber warns and continues with affected estimates marked
low-confidence; green is clean. There is no override flag: red is cleared by fixing the findings
or by deliberately editing the value.

### sanctum

The persistent identity and memory store for `l3io-sec-redteam`, the package's one memory agent.
Its absence is what signals a first run. It holds the agent's persona, creed, memory and a
research cache.

### sharded layout

The current state design: one bare node per file, with children discovered by listing the
directory rather than by a list wrapper. It replaced a flat `sprint-status.yaml` and a legacy
per-epic tree, both of which are migrated by `/l3io-util-doctor migrate-state`.

### spec index

A compact catalogue of a project's specifications — every heading with its anchor, first
sentence and line range — written to `{implementation_artifacts}/spec/spec-index.md` and built
without a model. It exists so reviewers receive pointers and line ranges instead of whole
documents.

### sprint

A unit within an epic. Sprints run strictly sequentially, so each finished sprint's actuals
feed forward into re-estimating the rest.

### story

The smallest unit, one file each, keyed `E{nnn}-S{nn}-{nnn}`. Status flows
`backlog → ready-for-dev → in-progress → review → done`. One agent handles one story.

### stuck

A computed flag, not a figure of speech. A node is flagged when its dwell time passes a fixed
threshold for its level and status: **4 hours** for a story in `in-progress` or `review`,
**24 hours** for a sprint, **72 hours** for an epic. Terminal and waiting statuses are never
flagged.

### technical acceptance criteria

The six dimensions every story must cover before reaching `ready-for-dev`: interface contracts,
error and edge case handling, observability requirements, security considerations, testability
approach, and an existing-library check. Each must be satisfied or explicitly marked `N/A` with
a reason — an unfilled applicable dimension blocks advancement, and this is not configurable.

### work type

A scope's classification — **CODE**, **DOCS**, **CONFIG**, or **MIXED** — decided by what its
stories contain. It determines which phases run: fix loops and the architecture and security
gates apply to code-bearing work only. Anything unclassifiable defaults conservatively to CODE.

## See also

- [Skills and sequence](skills-and-sequence.md) — what each skill is for
- [l3io-pm reference](l3io-pm-reference.md) — the full schema and every subcommand
- [Troubleshooting](troubleshooting.md) — when one of these appears in an error
