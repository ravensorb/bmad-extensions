# Outstanding work — full assessment

**Date:** 2026-09-26 · **Tree:** `main` at 3.1.0 + the check-27 scoping fix, CI green

Every open item in this repository, measured against the tree rather than recalled, sorted by
what should happen to it. Four categories: **do**, **decide**, **retire**, and **already closed**.

The headline: there is much less genuinely open work than the count of files suggests. Eighteen
plan documents exist; **one** describes unfinished work. Four "knobs that do nothing" are real
and removable. Three named gaps are deliberate non-goals that should stop being tracked.

---

## 1. The typed-writers follow-up — still needed, and its plan is not a plan

**Status: OPEN, verified live in the tree.**

`migrate-engine.py` still carries `STRUCTURED_EXTRAS_TO_WARN` and still prints
`WARN <kind> <key>: skipping <field>=<value>` for three fields. `pm-status.py` has **no writer
for `depends_on` at all** (0 occurrences). So a migration silently loses dependency edges,
estimates and actuals from a legacy source — visibly, on stderr, but loses them.

**The existing file is a design sketch, not an executable plan:** 68 lines, **0 tasks, 0 steps**.
It names three pieces and two options for the hardest one. It cannot be handed to an executor.

### What it actually requires

| Piece | Difficulty | Why |
|---|---|---|
| `depends_on` | **Low** | Needs a list-shaped writer. A sibling verb `set-depends-on --add KEY` is safer than `set-field --json-value`, because it stays list-shaped end to end and cannot be mistaken for a scalar write. |
| `estimate` | **Low-medium** | `set-estimate` already writes exactly this shape; the engine just has to walk the mapping and emit the flag set. Story vs sprint/epic ranges are a translation layer. |
| `actual` | **Medium-high** | `set-actual` requires `--runtime`, and under `runtime=claude` rejects anything short of the full four-class token breakout. **A migration cannot invent a runtime or a token split for legacy data.** |

### The decision the sketch leaves open

For `actual`, two shapes:

- **`set-actual --runtime other` with explicit `--tokens-na`** — works today, no new verb, but
  puts the "this is legacy, do not pretend otherwise" judgement on every caller.
- **A new `import-actual` verb**, mirroring `import-node`'s cmd-with-one-swap shape, whose whole
  purpose is "this actual was observed elsewhere, take it verbatim, do **not** derive a
  calibration sample."

**Recommendation: `import-actual`.** The precedent is directly on point — `import-node` exists
because `set-status` correctly refuses to create, and the same logic applies here: `set-actual`
correctly refuses to accept an unmeasured token split, and a migration correctly needs to.
Sharing one verb between "measured now" and "found in legacy data" is how a calibration sample
gets derived from a number nobody measured.

**Estimated size:** 5 tasks. Bigger than the sketch implies, because `import-actual` needs the
calibration-suppression path tested, not just the write.

---

## 2. Genuinely open engineering work

Ordered by consequence, not effort.

| # | Item | Evidence | Size |
|---|---|---|---|
| 1 | **Typed writers** (§1) | `STRUCTURED_EXTRAS_TO_WARN` live; `depends_on` has no writer | 5 tasks |
| 2 | **Structured issue `source`** | Spec `b831496`; 468 of 517 items untraceable on a real project | ~4 tasks, *partly done* — see note |
| 3 | **Concurrent epics share one working tree** | No source-file independence check; `docs/limits.md` Concurrency | Design first |
| 4 | **No check that gate imports are declared in `package.json`** | ADR-0007 names the follow-up; `CLAUDE.md:105-109` | 1 task |
| 5 | **Probe-path correctness has no CI check** | `CLAUDE.md:132`; verified only at runtime by `check-deps` | 1-2 tasks |
| 6 | **Three `standards-*.md` overlays are stubs** | `TODO: promote to full standard` in docker, powershell, shell | 3 tasks |
| 7 | **`l3io-pm-setup` picker validation / install-order gating** | `assets/module.yaml:10` | Unscoped |

**Note on #2:** the write and read halves shipped in 3.1.0 — `--source-phase`/`--source-ref`/
`--source-note` exist, `pointer_for` prefers them, seven call sites converted. What remains is
the *optional* part the spec deliberately left out: making `--source` non-required, and the
`append-issue` normalisation of legacy free text. Both are breaking changes needing their own
decision. **Item 2 is closer to done than the spec's task count suggests.**

**Note on #3:** this is the one item where the *design* is the work. The adaptive-parallelism
spec (2026-08-17) proposes a model; the shared-working-tree hazard is the concrete risk it would
address. `parallel_mode`, `parallel_ceiling` and `safe_batch_size` are **not** shipped knobs —
measured: 0 occurrences under `skills/`. They exist only in design prose, so `limits.md` is
accurate and there is nothing to remove.

---

## 3. Retire — inert surface that should be deleted, not implemented

These are measured as present in the shipped tree and doing nothing. Each costs a reader time
and invites someone to tune it.

| Knob | Where | Why inert | Recommendation |
|---|---|---|---|
| `max_fix_iterations_non_code` | 8 files, incl. `l3io-pm-execute/customize.toml` | **Doubly** inert: equal to `max_fix_iterations`, AND every phase with a fix loop is already skipped for DOCS/CONFIG | **Delete.** It is user-settable, so it actively misleads |
| `field_rules`, `status_labels` | `l3io-pm-sync/assets/sync-config-template.yaml` | Reserved for conflict resolution that was never built | **Delete from the template**, keep the idea in the design doc |
| `last_sync` | 5 files, incl. `drift-report.py` | Written by nothing | **Delete**, or write it — but decide |
| `granularity` | 18 files | Never varied; every project runs `"story"` | **Keep.** It lives in the calibration file, so removing it is a schema change, and the standing rule is no unapproved version bumps |

`granularity` is the one to leave alone, and the reason is worth stating: the cost of removing it
exceeds the cost of documenting it, which `limits.md` already does.

---

## 4. Deliberate non-goals — stop tracking these

Each is a decision already taken with a recorded reason. They appear in "outstanding" lists only
because nobody marked them closed.

- **The eight entries in `limits.md` §"Things refused on purpose"** — `cost` not enterable,
  `tests_passing` not settable, `self-install` never downgrades, and so on. Each exists because
  the permissive version shipped a bug.
- **The four entries in §"Not in scope at all"** — the installer does not migrate data, no BMad
  core script is bundled, test suites are not shipped, this package does not replace core skills.
- **The four gap-analysis items marked "not worth covering"** — orphaned `issues.yaml` epic
  references, consumer-side manifest verification, node-schema versioning, a general
  calibration-drift detector. Re-read the arguments before reviving any; they were arguments,
  not omissions.
- **468 untraceable backlog items on the reporting project** — structural. 76 point at closure
  artifacts that were never written. No parser reaches them; only re-running the work would.

---

## 5. Already closed — retire the records

- **The doctor capability gap analysis: all ten gaps closed** (six in `0238849`, four earlier in
  the redesign). The document is marked closed and now reads as a record.
- **Seventeen dated implementation plans** in `docs/superpowers/plans/` are historical records of
  shipped work, not open items. Their checkboxes are unticked because SDD tracks in its ledger,
  not the plan file — **an unticked box in those files means nothing.**
- **`followup-pm-status-exists-verb.md` was deleted on completion.** That is the right pattern
  and worth keeping: a follow-up file's existence should mean the work is open.

---

## 6. Recommended plan

**Phase 1 — retire (½ day, no risk).** Delete `max_fix_iterations_non_code`, the two reserved
`sync-config` keys, and `last_sync`. Update `limits.md`'s "Knobs that exist but do nothing" to
cover only `granularity`, with its reason. This shrinks the surface before anything is added to
it, and each deletion is independently revertible.

**Phase 2 — typed writers (§1), 5 tasks.** The only item with active data loss. Do
`depends_on` and `estimate` first (both low), then `import-actual` with its
calibration-suppression test. Convert the WARN-focused engine tests to landed-on-disk
assertions, and delete the follow-up file when done.

**Phase 3 — the two missing CI checks (#4, #5), 2-3 tasks.** Both are the same shape as check 27
and both close a "no gate covers this" hole that `CLAUDE.md` already documents. Cheap, and they
protect everything else.

**Phase 4 — decide, do not build.** Item #3 (shared working tree) needs a design decision before
any code. Item #2's remainder is two breaking changes. Item #7 is unscoped. None should be
started as implementation work.

**Explicitly not recommended:** the three `standards-*.md` stubs (#6). They are honest
placeholders that say what they are; promoting them is content work with no defect behind it.

### Sequencing rationale

Phase 1 before Phase 2 deliberately. Every item in Phase 1 is surface that a reader of Phase 2's
code would have to understand and dismiss. Removing dead knobs first is cheaper than carrying
them through a change to the same files.
