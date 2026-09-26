# Outstanding work — full assessment

**Date:** 2026-09-26 · **Tree:** `main` at 3.1.0 + the check-27 scoping fix, CI green

Every open item in this repository, measured against the tree rather than recalled, sorted by
what should happen to it. Four categories: **do**, **decide**, **retire**, and **already closed**.

The headline: there is much less genuinely open work than the count of files suggests. Eighteen
plan documents exist; **one** describes unfinished work. Of four "knobs that do nothing", only
**one** is actually removable — see the correction in §3. Sixteen tracked items are deliberate
non-goals that should stop being tracked at all.

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
| `field_rules`, `status_labels` | `l3io-pm-sync/assets/sync-config-template.yaml` | Not consumed by any script **yet** | **KEEP.** Corrected — see below |
| `last_sync` | 1 site: `sync-state.py:36` | Top-level key, written `None`, never updated | **KEEP.** Corrected — see below |
| `granularity` | 18 files | Never varied; every project runs `"story"` | **Keep.** It lives in the calibration file, so removing it is a schema change, and the standing rule is no unapproved version bumps |

### Correction — two of these should NOT be deleted

The first draft of this assessment recommended deleting `field_rules`, `status_labels` and
`last_sync`. That was wrong on both counts, and the error is worth recording because it came
from a grep that conflated two different things.

**`field_rules` / `status_labels` are a deliberate reserved interface, not debris.** The
template says so at the point of use: *"not yet consumed by any script; they are reserved for
a future field-authority/label-mapping feature."* A reader is warned in the file itself, so
they mislead nobody, and `l3io-pm-sync` is documented as GitHub-only *today* — the phrasing in
`docs/limits.md` and `l3io-pm-reference.md` treats GitLab, Azure DevOps and Jira as absent
rather than rejected. Deleting a designed extension point because it is not wired yet is how
you pay for it twice.

**`last_sync` was a conflated grep.** There are two distinct things:

| Field | Where | Status |
|---|---|---|
| `last_sync` | one site, `sync-state.py:36`, in the state-file scaffold | written `None`, never updated — genuinely inert |
| `last_synced_at`, `last_synced_hash` | per-mapping entries; written at `sync-state.py:143-144`, read at `drift-report.py:351,361,374` | **load-bearing** — drift detection depends on them |

The original "5 files incl. `drift-report.py`" count was the second family, not the first.
Deleting on that evidence would have broken drift detection. The genuinely inert one is a
single key in a `version: 1` state file, so removing it is a schema change — the same reason
`granularity` stays.

`granularity` is likewise left alone: the cost of removing it exceeds the cost of documenting
it, which `limits.md` already does.

**Net: Phase 1 is one deletion, not four.**

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

**Phase 1 — retire (small, no risk).** Delete `max_fix_iterations_non_code` only, and correct
`limits.md` to distinguish inert-and-removable from inert-and-kept. This shrinks the surface before anything is added to
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

---

## 7. Addendum — the epic-aware issue migration (new, 2026-09-26)

Added after `normalize-status` was found lossy and gated (`0949006`). The gate makes the current
state safe; this is the real fix, **designed but not built**, and it needs one decision.

### The problem

`deferred` was a *disposition* — "we looked at this and decided not now". `OPEN_ISSUE_STATUSES`
is `(backlog, scheduled)` and neither carries a decision, so **no mapping into an open status can
preserve one**. Items behind a CLOSED epic are the sharp case: converting them to `backlog` makes
them undecided findings behind an epic that has already closed.

### Discriminator — settled: use the simple rule

Measured on the reporting fixture, 520 open items:

| Rule | Count |
|---|---|
| A — behind a CLOSED/archived epic | 518 |
| B — archived epic **and** never scheduled | 518 |

**Identical, and structurally so.** `status: scheduled` occurs **zero** times, and there is no
scheduled-to field; `epic`/`sprint` are mandatory *provenance* (where a finding was filed), not
destination. Rule B collapses into Rule A because nothing in this schema can say an issue *is*
scheduled.

**Take Rule A** — not because the data prefers it, but because the data cannot distinguish them
and the more complex rule buys nothing measurable on the only real fixture. Revisit if a project
ever populates `status: scheduled`. The 2 items not behind an archived epic belong to a `planned`
epic, and Rule A correctly leaves them alone.

### Resolution vocabulary — evidence, and the open decision

From the same project's own resolution prose (free text, but the vocabulary word is
parenthesised and therefore countable):

| Value | In 291 resolved | In 520 open |
|---|---|---|
| `wontfix` | **26** | — |
| `deferred` | **3** | 307 |
| `obsolete` | **0** | — |

Three things follow:

- **`obsolete` is wrong.** Zero instances in 291 resolved items, and it asserts the finding
  stopped mattering — which 307 still-open items contradict.
- **`wontfix` has real local precedent**, 26 uses, with matching prose: *"TRIAGED (wontfix).
  Accepted cost…"*. No enum change needed.
- **`deferred` already appears as a RESOLUTION**, three times. So the concept has precedent in
  the resolved file, not only as an open status.

**The decision:** `wontfix` conflates "decided against" with "decided not now"; a new `deferred`
resolution keeps them apart and makes the migration reversible, at the cost of growing
`RESOLUTIONS = ("fixed", "wontfix", "duplicate", "obsolete")`.

**Recommendation: add `deferred` to the vocabulary.** The migration would otherwise assert a
decision the author never wrote, and this whole defect exists because a mapping asserted meaning
it could not carry. Growing an enum additively is cheaper than repeating that mistake — and it is
checkable afterwards: no finding behind a closed epic should remain in the open list.

**Caveat, stated because it is load-bearing:** all of the above is **n=1**. One project's
resolution prose is evidence of that project's habits, not of the vocabulary's correct shape.
