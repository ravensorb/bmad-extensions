# Subagent Context Trimming — Design

**Date:** 2026-08-17
**Status:** Approved design, pending implementation
**Sub-project:** C of three (see "Follow-on scope" below)

## Problem

Token cost per sprint is dominated by **instruction reload**, not by the review phases it
appears to come from. Every subagent invocation re-loads the same two large reference files
into context because both instruct it to.

`skills/_shared/status-files.md:6-7`:

> Load it at activation alongside the metrics contract and keep its rules in context for
> every read, every write, and every node move.

`skills/_shared/metrics-contract.md:7-8`:

> Load it at activation alongside `references/status-files.md` and keep its rules in context
> for every estimate write and every closeout.

Measured (canonical sources; payload copies are byte-identical):

| File | Lines | Bytes |
|---|---|---|
| `metrics-contract.md` | 746 | 38,537 |
| `status-files.md` | 432 | 20,861 |
| **mandated total** | **1,178** | **59,398** |

At roughly 4 characters per token that is ~15K tokens of instruction per subagent, before any
project content. A sprint runs between 8 invocations (3-story DOCS sprint, no fix iterations)
and 40+ (fix loops at their 10-iteration caps across story, sprint, and epic closure), so the
reload alone accounts for on the order of **100K–500K tokens per sprint** — more than every
review phase combined.

### How much of it is operative

Most of the mandated content describes behavior that `pm-status.py` now performs itself.

| Reference | Operative for a sprint subagent | Share |
|---|---|---|
| `metrics-contract.md` | §1 hard rule, §3 runtime capture, §4 writing estimates/actuals ≈ 106 lines | 14% |
| `status-files.md` | §3 key schema, §7 addressing, §10 read resolution ≈ 153 lines | 35% |
| **combined** | **≈ 259 of 1,178 lines** | **22%** |

The remainder is background:

- `metrics-contract.md` §8 (calibration) is **256 lines**, and `CLAUDE.md` states outright
  that "`pm-status.py` runs the calibration loop itself — this is not orchestrator prose."
  §6 (roll-up) and §7 (fix reserve) are mechanized the same way by `estimate-story` and
  `estimate-rollup`. §10 is a worked example.
- `status-files.md` §1/§2/§5 describe a layout that `pm-status.py` is the sole resolver of;
  §9 concurrency is enforced by `flock` inside the script.

### Why trimming is safe now and was not before

Those directives were written when skills edited state YAML free-form. The contract had to be
resident in the agent's context to prevent malformed and dropped writes — the exact failure
`pm-status.py` was introduced to end.

`pm-status.py` is now the **only** writer, and it enforces every one of those rules
mechanically: atomic temp-file-plus-rename writes, key-based addressing with no hand-built
paths, `flock` on shared append targets, and schema validation with a read-back `verify`
gate. Keeping 1,178 lines resident is belt-and-braces on a mechanism that cannot be bypassed.

## Design

### 1. Replace the mandatory full load with a compact operative digest

Add a digest of roughly 70 lines to `steps/shared/step-00-activate.md` containing only:

- `pm-status.py` subcommand signatures for the calls a sprint subagent actually makes
  (`set-status`, `set-actual`, `set-estimate`, `estimate-story`, `verify`, `append-issue`,
  `report`)
- Key formats: `E{nnn}`, `S{nn}`, `E{nnn}-S{nn}-{nnn}`, `BL-E{nnn}-{nnn}`
- The estimates-and-actuals HARD RULE, stated in one paragraph
- The runtime-detection rule (`claude` vs `other`, and that token/cost actuals are exact
  under Claude and `N/A` elsewhere — never guessed)

Change both reference headers from "load at activation and keep its rules in context" to
"consult when you need the deep contract."

**The digest must end with a routing table, not a vague invitation to consult.** Telling an
agent "read the reference if you need it" leaves it to search 1,178 lines for the relevant
part — which either costs the tokens the trim was meant to save, or gets skipped. Name the
destination down to the section:

| If you need to… | Read |
|---|---|
| interpret a `verify` failure | `references/status-files.md` §7 (Addressing) |
| know which fields a node carries | `references/status-files.md` §4 (Per-file schema) |
| handle a migration or legacy layout | `references/status-files.md` §10 (Read resolution) |
| declare or read `depends_on` | `references/status-files.md` §11 (Dependency fields) |
| resolve an epic lock question | `references/status-files.md` §6 (Ownership lock) |
| capture token/cost actuals correctly | `references/metrics-contract.md` §3 (Runtime detection) |
| write an estimate or actual by hand | `references/metrics-contract.md` §4 |
| explain a calibration result | `references/metrics-contract.md` §8 |
| see a full worked example | `references/metrics-contract.md` §10 |

Section numbers are load-bearing here, so the implementation must verify each anchor resolves
to the section named — a stale pointer sends the agent to the wrong place, which is worse than
no pointer. Both references already carry stable numbered `##` headings, so this is a
mechanical check, not a judgement call.

**Scope constraint — the digest's one real risk.** A digest is a second copy of content, and
this repository has been bitten repeatedly by duplicated prose drifting. Constrain it to
**only mechanical facts that `pm-status.py` independently enforces** — command signatures and
key formats. Never semantic rules that could drift without anything detecting it.

**Precedence, stated in the digest itself:** `pm-status.py` wins over the reference; the
reference wins over the digest. A reader who finds a disagreement should trust the script,
then the reference, and treat the digest as stale.

### 2. Narrow `persistent_facts`

Present in exactly the four PM skills — `l3io-pm-execute`, `l3io-pm-plan`, `l3io-pm-sync`,
`l3io-pm-help` (`l3io-arch-review`, `l3io-util-doctor`, and the `l3io-util-cleanup` forwarder
already use `[]`):

```toml
persistent_facts = ["file:{project-root}/**/project-context.md"]
```

A recursive glob with no bound, injected into every subagent. In a large repo it can match an
arbitrary number of files, and nothing reports how much it pulled in.

Replace with two explicit, non-recursive paths:

```toml
persistent_facts = [
  "file:{project-root}/project-context.md",
  "file:{project-root}/docs/project-context.md",
]
```

Bounded and predictable. The long tail is already covered without recursion, because the
customization model **appends arrays** across layers: a project keeping its context file
elsewhere adds its own path in `_bmad/custom/{skill-name}.toml` and both are loaded.

**Migration risk, and why it is acceptable.** A project currently keeping
`project-context.md` at a deeper path silently stops having it loaded — a behavior change with
no error, which is the worst kind. Two mitigations, both required:

- The implementation must note this in `docs/upgrading.md` under the release that ships it,
  with the exact `_bmad/custom/` override to restore a custom location.
- The default must include the two locations above rather than root only, so the common cases
  keep working untouched.

### 3. Leave step-file loading alone

Subagents are told to load four step files upfront (~23 KB total: `step-00-activate.md`
7,914 B, `step-02-story-prep.md` 3,228 B, `step-03-dev-loop.md` 4,455 B,
`step-04-sprint-closure.md` 4,013 B, plus `closure/sprint-closure.md` 3,020 B). That is
genuinely operative instruction, the harness likely reads it lazily regardless, and trimming
it trades correctness risk for ~4 KB. Deliberately out of scope — YAGNI.

## Expected effect

Mandated reference load per subagent drops from **59,398 B to roughly 3 KB** (the digest).
Actual per-sprint savings depend on how often a subagent genuinely needs a deep reference; the
floor is the digest alone and the ceiling is unchanged from today if every subagent consults
both files, which no sprint should.

No review phase is removed and no rigor is reduced. This sub-project changes only *what is
loaded*, never *what runs*.

## Verification

Assert, do not assume:

1. **Size measurement before and after** — bytes mandated at activation, recorded in the
   implementation notes rather than estimated.
2. **`verify --scope epic` passes** on a fixture tree after the change, confirming subagents
   still write conformant state.
3. **A real sprint-scoped `report --format tree`** renders correctly, confirming the digest
   carries enough for the calls a subagent makes.
4. **The digest contains no semantic rules** — reviewed against the scope constraint above,
   line by line.
5. **Existing test suite passes** (425 tests). No test covers prose, so this is a regression
   guard on `pm-status.py`, not proof the digest is sufficient; items 2 and 3 cover that.

The failure mode to watch for is a subagent that can no longer answer a schema question. That
is precisely why the deep references remain in place and consultable rather than deleted.

## Out of scope

Removing content from `status-files.md` or `metrics-contract.md`. They stay canonical and
complete. This changes when they are read, not what they say.

## Follow-on scope

Recorded here so the decisions are not lost. Each gets its own spec.

### A. Unify phase gating and scale review depth to work type

Three competing `{skip_phases}` definitions exist, and the wrong one wins:

| Source | Defines |
|---|---|
| `steps/shared/step-01-classify-work.md` §4 | tech-AC gate, arch gate, adversarial, red team, UX, ATDD |
| `steps/execute/step-05-epic-loop.md:141-145` | adversarial, red team, arch drift, clean release, UX |
| `steps/closure/sprint-closure.md` §8 table | the 7×4 matrix closure actually reads |

`step-01` binds `{skip_phases}`; `step-05` then **recomputes and overwrites it**.

**This is inert today — verified, not assumed.** `{skip_phases}` has exactly five consumers,
all closure phases in `closure/sprint-closure.md` (clean release, adversarial, red team, UX,
arch drift), and for both DOCS and CONFIG `step-05`'s list agrees with the §8 table. The three
entries in `step-01`'s table that `step-05` omits are gated independently on `{work_type}` and
never flow through `{skip_phases}` at all:

| Phase in step-01's table | Actually gated by |
|---|---|
| Story technical-AC gate | `{work_type}` — `steps/sprint/step-02-story-prep.md:10` |
| Epic arch gate | `{work_type}` — `steps/execute/step-04-arch-gate.md:11-12` |
| ATDD scaffold | nothing reads it; the table is its only mention |

So the correct phases skip either way, and no tokens are being burned on phases already
decided against. What is wrong is narrower: **one variable computed in two places from two
different definitions**, plus a table that lists three phases which do not flow through it.
That is a maintenance hazard and misleading documentation, not a live defect — it carries A's
normal priority and is not a reason to resequence ahead of C.

Decisions taken:

- **One matrix, one source of truth.** Collapse all three into a single table; every consumer
  reads it and nobody recomputes. Phases gated on `{work_type}` directly should say so in the
  matrix rather than appearing to be `{skip_phases}` entries.
- **No UX review on DOCS.** The §8 table currently runs it. Removing it takes DOCS closure
  from three phases to two.
- **Work-type-aware fix-loop caps, configurable.** The cap is hardcoded as `10` in three
  places (`step-03-dev-loop.md:51`, `closure/sprint-closure.md:38`,
  `closure/epic-closure.md:35`). Replace with settings in `customize.toml`: `10` for
  CODE/MIXED, `3` for DOCS/CONFIG. This is the largest single multiplier in the system and is
  currently identical for a broken API contract and a typo.
- Also fix: `parallel_mode` and `parallel_ceiling` are documented in `CLAUDE.md` but defined
  in no `customize.toml`.

### B. Token budget enforcement

Estimates are computed and recorded but nothing enforces them. A ceiling that halts and
reports beats running to a 10-iteration cap. Sequenced last deliberately: it is the only one
of the three that can leave work half-finished, and a budget set before A and C land would
encode today's waste as the baseline.

## Files affected

**Canonical sources** (fan out to three PM skill payload copies via `npm run sync:scripts`):

- `skills/_shared/steps/shared/step-00-activate.md` — gains the digest
- `skills/_shared/status-files.md` — **header directive only** (lines 6-7); body unchanged
- `skills/_shared/metrics-contract.md` — **header directive only** (lines 7-8); body unchanged

The two references appear here because their loading instruction changes, not their content.
Removing content from them remains out of scope, as stated above.

**Per-skill:** `customize.toml` in `l3io-pm-execute`, `l3io-pm-plan`, `l3io-pm-sync`,
`l3io-pm-help` (the `persistent_facts` glob)

**Docs:** `CLAUDE.md` and `docs/l3io-pm-reference.md` where they describe activation loading
