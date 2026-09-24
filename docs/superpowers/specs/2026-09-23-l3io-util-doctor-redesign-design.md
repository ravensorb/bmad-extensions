# l3io-util-doctor redesign — design

**Date:** 2026-09-23
**Status:** approved design, not yet planned
**Informed by:** `docs/l3io-util-doctor-gap-analysis.md`

## 1. Why

The doctor grew one mode at a time. Each mode was reasonable on its own; the set
is not. Three problems follow from that history, and this redesign exists to
close them.

**The migrations are prose, so nothing tests them.** `assets/migrate-state.md`
is 817 lines of procedure that constructs state paths by hand —
`mkdir -p {pm_state_root}/{status_dir}/epic-{nnn}/` at `:352` and the sprint
directory at `:355`. It calls exactly two real `pm-status.py` verbs
(`append-issue`, `verify`). Everything else it does to the state tree, it does
itself. `CLAUDE.md` states that `pm-status.py` "is the only place that resolves
a key to a file location"; the doctor's largest procedure is the standing
exception.

**The consequence is live and destructive.** BMad's own
`sprint-status.yaml` — `.claude/skills/bmad-sprint-planning/sprint-status-template.yaml:53-66`
— is a flat `development_status:` **mapping** (`epic-1: backlog`,
`1-1-user-authentication: done`). This package's legacy flat file is an `epics:`
**list**. They share a filename and a default directory. This package contains
**zero** functional references to `development_status` (the only occurrences in
the repo are three inside the gap-analysis document itself). So against a real
base-BMad project, `migrate-state` Stage A parses nothing, Stage E's completeness
gates (`:694-717`) pass vacuously over an empty set, and Stage F (`:721-742`)
`rm -f`s the source — deleting the live tracking file that `bmad-sprint-planning`,
`bmad-build` and `bmad-retrospective` all read, and reporting success.

**And the failure is general, not specific.** Any parse that yields zero nodes
reaches the same destructive step by the same path. Fixing the schema
discriminator alone fixes one cause. The gate belongs in the architecture.

## 2. What the doctor needs to be able to do

Three tiers, distinguished by what they are allowed to touch. The tier is the
user's mental model and the safety contract at once.

| Tier | Contract | Examples |
|---|---|---|
| **Read-only** | Reports. Changes nothing, ever. | health check, `stats`, `check-deps`, drift detection |
| **Safe repair** | Changes only machine-derived data that can be recomputed. Idempotent. | `redrive`, `sort-status`, backlog audit, `triage` |
| **Transition** | Moves a project between layouts or schemas. One-way, backed up, confirmed. | `migrate-state`, `migrate-adrs`, `split-status`, schema migration |

**Decision — one skill, three tiers inside it.** Not three skills. The tiers are
a routing and confirmation property, not a packaging one; splitting them would
triple the install surface and the shared-payload burden for a distinction that
a table column already expresses.

**Decision — detect *and convert* base-BMad projects.** A project arriving from
base BMad is the most likely real-world starting state. Detecting it and refusing
is not enough; the doctor is the documented on-ramp.

**Decision — infer sprints from status transitions.** BMad's schema has no sprint
concept. Sprint boundaries are reconstructed from the order and grouping of status
changes rather than invented as a flat `sprint-01`.

**Decision — mark inferred nodes.** An inferred node carries `origin: inferred`
and an `origin_note`. Absent means "not inferred" — **no schema version bump**,
per the standing "no unapproved version bumps" rule. Nothing reads the field
today; it exists so a later reader, and a human, can tell reconstruction from
record.

**Decision — PASS / FAIL / UNABLE as a rule, plus the three missing probes.**
Every check reports one of three outcomes. "UNABLE" is a first-class result: a
check that could not run has not passed. This is the general form of the vacuous
green that Stage E produces today.

## 3. Architecture — three layers

The rule that resolves "six migration paths" into something testable: **detection
and judgement stay in prose; parsing and writing become code.**

| Layer | Where | Responsibility |
|---|---|---|
| **Readers** | `skills/l3io-util-doctor/scripts/` — one per source layout | Parse a source tree into a list of **normalised records**. Pure: no writes, no locks, no interaction. |
| **Writer** | a new `pm-status.py` verb | Create a state node from a record, under the existing lock/event/exit-code contract. |
| **Prose** | `assets/`, `steps/` | Detect which layout is present, explain what will happen, exercise judgement, confirm, dispose of the source. |

Four readers and one writer replace six hand-written procedures. The readers are
single-consumer code and live in the doctor's own `scripts/` per ADR-0001. The
writer is shared runtime and lives in `skills/_shared/pm-status.py`.

**Layout detection has one home.** There are already three copies of layout
detection in the tree, each carrying a comment asking the next person to keep
them in sync. `scripts/detect-layout.py` already owns this decision and is
already unit-tested; the schema discriminator (`development_status:` mapping vs.
`epics:` list) becomes a **second exit code from that script**, not a fourth copy
and not a new step-file snippet. Per `CLAUDE.md` §3, the rule and its check ship
together.

## 4. `pm-status.py` — do not split it

The question was raised because the file is 6,828 lines. It should not be split,
for four reasons, each checked rather than assumed:

1. **It is layered, not tangled.** Nine named sections with a clean dependency
   direction: resolver → roll-ups → progress model → renderers → subcommands →
   issue store → CLI.
2. **No handler is large.** The biggest is 131 lines. Size is in the count of
   verbs (30), not in any one of them.
3. **The suite is 9,458 lines** and drives the real write path. Splitting the
   module means re-homing all of it for no behavioural gain.
4. **ADR-0001's single-file rule is mechanically load-bearing.** `self-install`
   copies one file and content-guards it by SHA-256 of the bytes. A second file
   is a second thing to install, hash and keep in step — the exact class of drift
   the content guard was introduced to end.

**The invariant was verified, not assumed:** zero state-node path constructions
exist outside lines 475–908. **Add a guard so it stays true** — a `check:scripts`
rule asserting that `epic-`/`sprint-` path assembly appears only in the resolver
section. Writing the rule without the check is how the current `migrate-state`
exception survived in the first place.

## 5. The writer verb

The verb is **`import-node`**. Its handler is `cmd_set_status` copied with
exactly one step swapped: `resolve_node_path(...)` where `set-status` calls
`_load_checked(...)` — because `_load_checked` raises exit 3 ("node not found")
and this verb's whole purpose is the case where the node does not exist yet.
`set-status` itself is not modified.

Everything else is reused unchanged: `_infer_kind`, `_epic_write_lock`,
`save_node`, `append_event`, the status-validity tables, and the exit-code
contract.

**Exactly one new function, and it goes in the resolver section (475–908):**
ensure a node's directory exists, addressed by key. A `mkdir` in the subcommand
body is precisely how the resolver invariant would break — and it is what
`migrate-state:352` does today.

The verb takes the same node-addressing flags as every other
(`--state-root`, `--epic`, `--sprint`, `--story`) plus the record's fields. It
never takes a path.

## 6. The normalised record and the run

Every reader emits the same record:

| Field | Meaning |
|---|---|
| `kind` | `epic` \| `sprint` \| `story` |
| `key` | the node key (`E001`, `E001-S01`, `E001-S01-001`) |
| `status` | a valid status for that kind |
| `title` | from the source, or derived mechanically |
| `origin` | `inferred` when reconstructed; absent when read directly |
| `origin_note` | why, when `origin` is set |
| `source` | the file and location the record came from |

A migration is eight steps:

1. **Detect** — which source layout, via `detect-layout.py`.
2. **Read** — run that layout's reader; get records.
3. **Resolve** — dedupe and merge. **One rule, applied once**, where the lists
   are joined: an epic shell and its full epic are one key, not two. (Today this
   is missing on *both* source paths, `:170` and `:223-226`, and only one of them
   is in the filed issue.)
4. **Plan** — show the user exactly what will be written.
5. **Gate** — **non-empty source and empty plan → BLOCK.** No confirmation
   offered, no writes, source untouched.
6. **Write** — the new verb, record by record.
7. **Verify** — read the tree back and compare it **against the plan**, not
   against itself.
8. **Dispose** — back up, then remove the source. Only after step 7 passes.

**Step 5 is the load-bearing change.** Stage E's checks are not wrong; they run
in the wrong place. Post-write completeness checks over an empty set pass, and
then the source is deleted. The gate sits before the write because that is the
only position from which an empty parse cannot destroy anything.

## 7. Testing

The refactor is what makes the testing affordable. The original trade-off — test
the new path, or backfill six untested ones — assumed migrations stay prose. Once
a reader is a pure function from a source tree to records, testing all of them
stops being a backfill.

| What | Where | Harness |
|---|---|---|
| Readers | `skills/l3io-util-doctor/scripts/tests/` | fixture directories, alongside the existing `test-detect-layout.py` |
| The writer verb | `skills/_shared/tests/test-pm-status.py` | the existing in-process `run_main` |
| End-to-end per path | `skills/l3io-util-doctor/scripts/tests/` | fixture project → run → assert the resulting tree |

One fixture project per source layout: base-BMad adoption, l3io legacy flat,
per-epic `_bmad/state/`, and the split three-file layout. Each asserts node count,
keys, placement, and that the source is preserved.

Four tests exist because of what actually went wrong, not because they are
conventional:

- **The empty-plan gate BLOCKs.** Feed a BMad-schema `sprint-status.yaml` to the
  l3io-flat reader: zero records, non-empty source, must refuse. This is the live
  bug, expressed as a test.
- **Verification compares against the plan.** Write the nodes, corrupt one on
  disk, confirm verify fails — proving it is not checking itself.
- **The source survives a failed run.** Failure at any step leaves the original
  intact.
- **Removing every fixture fails rather than passes.** The suite must not go green
  over an empty corpus.

**Each of those must be shown to fail when the thing it covers is broken.** A test
that passes without exercising its branch is worse than none; that is the vacuous
green this whole design is organised against, and a test suite is not exempt from
it.

## 8. What this closes

Mapped to the ranked gaps in `docs/l3io-util-doctor-gap-analysis.md` §3:

| Gap | Closed by |
|---|---|
| 1. Discriminate `sprint-status.yaml` by schema | §3 — second exit code from `detect-layout.py` |
| 2. Refuse a migration that moved nothing | §6 step 5 — the pre-write gate |
| 5. Dedupe the working epic list on both paths | §6 step 3 — one rule at the join |
| 9. The base-BMad on-ramp | §2 — detect **and convert**, with inferred sprints marked |

Gaps 3, 4, 6, 7, 8 and 10 are health-check and wiring work. They are real and
remain open; they are not part of this design, which is scoped to the migration
architecture and the record contract.

## 9. Out of scope

- Splitting `pm-status.py` — examined in §4 and rejected on evidence.
- A node-schema version bump — the `origin` field is additive and absence is
  meaningful, precisely so no bump is needed.
- The remaining six ranked gaps, above.
