# Issue Lifecycle: Resolution, Triage, and Backlog Intake

**Date:** 2026-09-10
**Status:** Draft

---

## Problem

`state/issues.yaml` is write-only. Five producers append deferred findings to it; nothing ever
takes one out, changes one, or turns one into work. The documented contract —
"resolved items are **removed**, not marked" (`docs/l3io-pm-reference.md` Backlog section,
`CLAUDE.md` State files) — has no implementation: `pm-status.py` has exactly two issue verbs,
`append-issue` and `list-issues`. Every consequence below was reproduced against the real
script, not inferred.

1. **Removing an item reuses its key.** `_next_issue_number` allocates "highest surviving
   suffix + 1". Reproduced: append A, B, C (`BL-E001-001..003`), hand-delete C, append an
   unrelated D → D is allocated `BL-E001-003`. Every reference to C — closure reports, triage
   notes, commit messages — now silently names D.
2. **The only removal path races the lock.** `issues.yaml` is one of three shared-append
   files whose whole read-modify-write runs under `issues_lock`. A hand edit takes no lock, so
   a concurrent `append-issue` from a parallel subagent can have its item dropped, or can
   resurrect the removed one — the lost-finding class the lock was added to close.
3. **Promotion is a silent no-op.** `epic-closure.md` §4 tells the agent to promote a Low item
   by re-writing it via `append-issue`. Reproduced: re-appending with `--severity High` prints
   `OK append-issue skipped … nothing written` and exits **0** (content dedupe ignores
   severity); passing the existing `--key` exits 2. The agent is told to report "count
   promoted" and the tool reports success while nothing changed — a false green.
4. **`status` is dead.** Every item is written `status: backlog`; nothing transitions it.
5. **Nothing consumes the backlog.** No `pm-plan` step reads `issues.yaml`; `pm-sync` enumerates
   `bmad_type: backlog` mappings but never acts on them (`sync/step-03-operations.md:94`);
   `archive-epic` ignores it; `pm-help` and `stats` count every item as open forever.
   `harvest-debt.md` says an item "persists until triaged like any other" — triage is not
   defined anywhere.
6. **Resolution leaves no record.** `append-issue` writes no event, so a hand deletion erases
   the only evidence an item existed, when it closed, and why.

Two producer gaps compound this. `epic-closure.md:58` and `:98` call `append-issue` without
specifying `--source` at all, and four of five producers pass no `--description`, so most
items carry no pointer back to the finding they record.

## Goals

- Items can be resolved, re-severitied, and promoted to work through `pm-status.py` verbs that
  hold the lock, never by hand edit.
- A resolved item is preserved with its resolution, not deleted, and its key is never reused.
- A story created from a backlog item resolves that item automatically when the story is done,
  on every path that marks a story done.
- An existing, never-pruned backlog can be audited for items that are already resolved, with
  deterministic evidence where possible and agent judgment otherwise — proposals only, human
  confirmed.
- Every rule above is enforced by code or a check, and the spec says where it is not.

## Non-goals

- **GitHub sync of BL items.** `pm-sync`'s `bmad_type: backlog` mapping stays report-only. This
  spec's `resolve-issue` is the primitive a follow-up sync spec will call on a closed issue.
- **A reopen verb.** A wrongly-resolved `fixed` item resurfaces through `append-issue`'s
  recurrence path (§2.1) when the finding is re-raised.
- **Editing title or description.** Only severity is mutable.
- **Automatic promotion.** No configuration enables it; promotion always needs an explicit choice.
- **Recovering keys already reused** before this ships. No history exists to detect them; §5
  records this as a limitation.
- **Legacy layouts.** `reconcile-status` and health-check Check 8 run only on the legacy split
  layout and are untouched.
- **Citing BL keys in commit messages.** The story's `resolves:` link provides traceability.

## Decisions

Settled during design review, 2026-09-10:

| Question | Decision |
|---|---|
| Scope | Lifecycle **and** intake (backlog → planned work). GitHub sync deferred. |
| Where a promoted story lands | The user names a target epic + sprint. Archived epics and any sprint not in `backlog` are refused. No special debt epic. |
| Which surface | Split by intent: `pm-plan` promotes (planning is when targets are chosen and estimates rolled up); `l3io-util-doctor triage` closes without work and re-severities. |
| Open items of an archived epic | Stay open, keep their key, and are tagged `origin_archived` in every reader. `archive-epic` does not touch the backlog. |
| Storage model | Open items stay in `issues.yaml`; resolved items move to append-only `issues-resolved.yaml`; a per-epic `next:` high-water mark allocates keys. |
| Audit depth | Mechanical checks first (`audit-issues`), a batched review agent for the remainder; every verdict is a proposal the user confirms. |

---

## 1. Data model

### 1.1 `state/issues.yaml` — open items only

Shape unchanged except for one new top-level key.

```yaml
next: {'000': 13, '001': 5}        # per-epic high-water; written only by pm-status.py
backlog:
  - key: BL-E001-004
    epic: '001'
    sprint: '02'                   # '' for an epic-level item
    title: 'Issue title'
    source: 'code-review (E001-S02-003)'
    severity: Low
    status: backlog                # open, untriaged
    description: 'See …/closure/review-E001-S02-003.md'
  - key: BL-E001-002
    epic: '001'
    sprint: '01'
    title: '…'
    source: '…'
    severity: Medium
    status: scheduled              # promoted to work
    story: E003-S02-004            # the story whose `done` resolves this item
    scheduled_at: '2026-09-10T14:02:11Z'
```

### 1.2 `state/issues-resolved.yaml` — new, append-only

A resolved item moves here whole, with its resolution fields added. Nothing edits or removes
an entry once written.

```yaml
resolved:
  - key: BL-E001-003
    epic: '001'
    sprint: '01'
    title: '…'
    source: '…'
    severity: Low
    status: resolved
    resolution: fixed              # fixed | wontfix | duplicate | obsolete
    resolved_at: '2026-09-10T15:40:00Z'
    ref: E003-S02-004              # story key, commit SHA, or (duplicate) the surviving BL key
    note: '…'                      # required for wontfix and obsolete
```

### 1.3 Story node — new `resolves:` field

```yaml
# state/planned/epic-003/sprint-02/E003-S02-004.yaml
key: 'E003-S02-004'
epic: 'E003'
sprint: 'S02'
title: 'Replace linear cache scan'
status: backlog
classification: standard
resolves: [BL-E001-002]            # written only by promote-issue
estimate: { … }                    # written by promote-issue via estimate-story
```

`resolves` is added to `DERIVED_NODE_FIELDS`, so `set-field` refuses it (exit 2) with a message
naming `promote-issue`.

### 1.4 Invariants

Each is asserted by a test (§6) and each violation is an `audit-issues` integrity finding (§3.1).

1. A key exists in exactly one of `issues.yaml` and `issues-resolved.yaml`.
2. `next[epic]` is greater than every numeric suffix for that epic in either file, and never
   decreases.
3. Every `scheduled` item's `story` exists and lists the item's key in `resolves`.
4. Every item in `issues.yaml` has `status` `backlog` or `scheduled`.

### 1.5 Compatibility

- Every existing reader of the `backlog:` list keeps working and becomes **correct** without
  modification: resolved items are no longer in it, so open counts stop inflating.
- `next` is an additive top-level key; readers that ignore it are unaffected. No schema
  version bump.
- A project with no `next` key is seeded on its first mutating call, from the highest suffix per
  epic found in **both** files.
- A project with no `issues-resolved.yaml` behaves as if it were empty; the first resolution
  creates it.

---

## 2. `pm-status.py` verbs and the `done` hook

Every mutating verb runs its whole load → decide → mutate → save cycle under `issues_lock`.
Exit codes follow the existing table: `0` success, `2` usage error or refusal, `3` not found,
`4` verification failure, `5` epic locked by another session.

### 2.1 `append-issue` — changed

Flags unchanged; keeps `--file` for compatibility. The resolved file is the sibling
`issues-resolved.yaml` in `--file`'s directory.

- **Allocation** reads `next[epic]` (seeding per §1.5 when absent), assigns it, and writes
  `next[epic] + 1`. The "highest surviving suffix" scan is used only for seeding.
- **An explicit `--key`** that exists in *either* file is refused (exit 2), and `next[epic]` is
  raised past it if lower.
- **Content dedupe** (normalized title + epic + sprint + source) now also consults resolved
  items:
  - matches an open item → skipped, exit 0 (unchanged);
  - matches a resolved `wontfix`, `duplicate`, or `obsolete` item → skipped, exit 0, output
    names the resolved key and resolution;
  - matches a resolved `fixed` item → **appended** as a new item, output reads
    `OK append-issue BL-… (recurrence of BL-…)`. A fixed finding re-raised is a regression.
- Writes an `issue_opened` event.

### 2.2 `resolve-issue` — new

```
resolve-issue --state-root S --key K --resolution {fixed,wontfix,duplicate,obsolete}
              [--ref R] [--note N]
```

- `fixed` requires `--ref`. `duplicate` requires `--ref` naming an existing BL key other than
  `K`, in either file. `wontfix` and `obsolete` require `--note`. Missing → exit 2.
- `K` already in the resolved file → exit 0, `already resolved (<resolution>)`. This makes the
  `done` hook and crash repair idempotent.
- `K` in neither file → exit 3.
- Appends the item to `issues-resolved.yaml` **first**, then removes it from `issues.yaml`.
  If `K` is found in both files (a prior crash), the resolved entry is kept and the open entry
  removed, without writing a second resolved entry.
- A `scheduled` item may be resolved directly (e.g. `wontfix`); the output notes that story
  `<story>` still lists it in `resolves`, and that story's later `done` is then a no-op for it.
- Writes an `issue_resolved` event.

### 2.3 `update-issue` — new

```
update-issue --state-root S --key K --severity {Low,Medium,High,Critical} [--note N]
```

Changes `severity` on an open item. Exit 3 if `K` is not open. Writes an `issue_updated` event
carrying `from`, `to`, and `note`. Replaces the broken promotion in `epic-closure.md` §4.

### 2.4 `promote-issue` — new

```
promote-issue --state-root S --artifacts-root A --key K [--key K2 …]
              --epic E --sprint S --classification {simple,standard,complex}
              [--title T] [--model M] [--token-rates JSON]
```

**Refusals, checked before any write:**

| Condition | Exit |
|---|---|
| Any `K` not open, or already `scheduled` (message names its story) | 2 |
| More than one `--key` without `--title` | 2 |
| Epic under `archived/` | 2 |
| Sprint `status` is not `backlog` | 2 |
| Epic or sprint not found | 3 |
| Epic holds a live `_lock` from another session | 5 |

**Writes, in this order:**

1. Under `epic_node_lock` on the target `epic.yaml`: allocate the next story number in the
   sprint directory (highest existing suffix + 1) and write the story node (§1.3): `key`,
   `epic`, `sprint`, `title` (`--title`, else the single item's title), `status: backlog`,
   `classification`, `resolves`, `updated_at`.
2. Write the story document at `story_doc_path(A, key)` **only if absent**. The skeleton
   follows `sprint/step-02-story-prep.md`'s, adding a Context section and a functional AC, so
   readiness grades it Amber (functional ACs only) rather than Red (no AC section):

   ```markdown
   ---
   key: 'E003-S02-004'
   title: 'Replace linear cache scan'
   status: backlog
   classification: standard
   ---

   # Replace linear cache scan

   ## Context

   Promoted from deferred finding(s):
   - BL-E001-002 (Medium, code-review (E001-S01-002)) — See …/closure/review-E001-S01-002.md

   ## Acceptance Criteria

   - The deferred finding BL-E001-002 is resolved: <title>
   ```

3. Estimate in-process through the same code paths as `estimate-story` (the new story) and
   `estimate-rollup` (its sprint, then its epic). No story node exists without an estimate,
   honouring the estimates-and-actuals hard rule.
4. Under `issues_lock`: set each item `status: scheduled`, `story`, `scheduled_at`. Writes one
   `issue_scheduled` event per item.

**Lock order.** `promote-issue` is the only verb that holds two locks, and always acquires
`epic_node_lock` before `issues_lock`. No verb acquires them in the reverse order.

**Story-first ordering is deliberate.** A crash between steps 1 and 4 leaves a story whose
`resolves:` still resolves the item on `done` (§2.6). The opposite order would leave a
`scheduled` item pointing at no story.

`bootstrap-state` and hand-created story nodes do not take `epic_node_lock`; allocation is
safe against concurrent `promote-issue` calls only.

### 2.5 `list-issues` — changed

Adds `--status {backlog,scheduled}` and `--resolved` (read `issues-resolved.yaml` instead,
adding `--resolution` as a filter). Every item gains a computed `origin_archived` boolean —
true when the item's epic directory lives under `archived/` — shown as a column in text output
and a field in JSON. Existing filters and defaults are unchanged.

### 2.6 The `done` hook in `set-status`

When `set-status` moves a **story** to `done`, then after the node save succeeds, for each key
in the node's `resolves:` it runs the `resolve-issue` logic in-process with
`--resolution fixed --ref <story key>`.

- Because it lives in the script, it covers all three paths that mark a story done: the dev
  loop (`step-03-dev-loop.md`), sprint closure (`step-04-sprint-closure.md`), and the `pm-sync`
  pull (`sync/step-03-operations.md`).
- It runs regardless of `--no-events`.
- A failure — lock timeout, malformed issues file — writes a warning to stderr and
  `set-status` still exits 0. The status transition is durable and must not be reported as
  failed by a follow-on write; this mirrors the calibration contract in `set-actual`. The miss
  is caught by `audit-issues` integrity check 1c (§3.1) and repaired by `triage`.
- Each resolution prints on stdout: `resolved BL-… (fixed, ref E…)`.

### 2.7 Events

`issue_opened`, `issue_updated`, `issue_scheduled`, `issue_resolved`, each carrying `key`,
`epic`, and the verb-specific fields (`severity`; `from`/`to`; `story`; `resolution`/`ref`).
Written through the existing best-effort `append_event`. The events are history for `report`;
the two YAML files are the record.

---

## 3. Audit and doctor `triage`

### 3.1 `pm-status.py audit-issues` — new, read-only

```
audit-issues --state-root S --artifacts-root A --project-root P [--format {text,json}]
```

Never writes. Emits one verdict per open item, plus integrity findings:

```json
{"key": "BL-E000-012", "verdict": "fixed-candidate", "basis": "mechanical",
 "evidence": "marker text not found in src/cache.py (file present)",
 "pointer": "src/cache.py", "origin_archived": true}
```

Checks run in this order; the first that yields a verdict wins.

1. **Integrity** (exit 4 when any is found; listed separately from item verdicts):
   - a. a key present in both files;
   - b. a `scheduled` item whose story is missing, or does not list it in `resolves`;
   - c. a `done` story whose `resolves:` names an item still open (missed hook);
   - d. a story's `resolves:` naming an item that is open with `status: backlog`
     (crash between promote steps 1 and 4);
   - e. `next[epic]` at or below the highest suffix for that epic in either file;
   - f. an open item whose `status` is not `backlog` or `scheduled`.
2. **Code-marker items** (`source` matches `code-marker (<file>:<line>)`):
   - file absent → `obsolete-candidate`;
   - the marker's `what` text (from `title`) absent from the file → `fixed-candidate`;
   - present → `open`, evidence gives the current line number.
3. **Duplicates** — the item's normalized title equals:
   - another open item's → `duplicate-candidate`, `ref` the older key;
   - a resolved `wontfix`, `duplicate`, or `obsolete` item's → `duplicate-candidate`, `ref`
     that key.
4. **Evidence pointer** for everything else, verdict `needs-review`. The pointer is the first
   of these that resolves to an existing file:
   - a `description` of the form `See <path>`;
   - `source` `code-review (<story>)` → `<A>/epic-<nnn>/sprint-<nn>/closure/review-<story>.md`;
   - `source` `<phase> (<id>)` → the file and line under that sprint's `closure/` directory
     containing `<id>`;
   - otherwise `pointer: null`, evidence `untraceable`.

An unrecognized `source` format never raises; it falls through to step 4.

Exit 0 when there are no integrity findings, whatever the item verdicts; exit 4 otherwise.

### 3.2 Doctor `triage` mode

New `skills/l3io-util-doctor/steps/triage.md`, a keyword-table row in `SKILL.md`, and a help
line under "Ongoing maintenance". Mode files, never inline.

- **T1 — Load config.** As other modes, plus bind `{model_review}` from
  `modules.l3io-pm.model_review` (default `{model}`). Doctor already binds `modules.l3io-pm.*`
  keys at activation; this adds one line and no new configuration.
- **T2 — Audit.** Run `audit-issues --format json`. On exit 4, show integrity findings first
  with one proposed repair each, applied only on confirmation:

  | Finding | Repair |
  |---|---|
  | 1a both files | `resolve-issue` rerun with the resolved entry's resolution and ref |
  | 1b story missing | revert the item to `backlog`, dropping `story` and `scheduled_at` |
  | 1c missed hook | `resolve-issue --resolution fixed --ref <story>` |
  | 1d unlinked promotion | set the item `scheduled` with that story |
  | 1e stale `next` | reseed from the highest suffix |
  | 1f bad status | report only — no automatic repair |

  The 1b, 1d, and 1e repairs need a narrow verb of their own; see §3.3.
- **T3 — Mechanical proposals.** A table of `fixed-`, `obsolete-`, and `duplicate-candidate`
  items with evidence. The user confirms all, picks, or declines.
- **T4 — Agent review.** For `needs-review` items, state the cost first — "14 items need review
  → 2 spawns. Run?" — and spawn nothing without a yes. Batches of at most 8 items, grouped by
  epic, on `{model_review}`, each bracketed with `dispatch --event open/close`
  (`--agent l3io-util-triage`). Per item the agent receives title, severity, source, and
  pointer; it reads the finding at the pointer, checks current code, and returns one of
  `fixed`, `still-present`, `can't-tell`, with `file:line` evidence. It never edits files.
- **T5 — Agent proposals.** A `fixed` verdict with no `file:line` evidence is downgraded to
  `can't-tell` before display. `still-present` and `can't-tell` items stay open. The user
  confirms as in T3.
- **T6 — Manual pass (optional).** Over the remaining open items: re-severity through
  `update-issue`, or close as `wontfix`/`obsolete` with a note.
- **T7 — Apply and summarize.** Every confirmed action goes through `resolve-issue` or
  `update-issue`, with the audit or agent evidence in `ref`/`note`. Summary: resolved count by
  resolution, severity changes, and remaining open items — untriaged, scheduled, and how many
  have an archived origin.

### 3.3 `repair-issue` — new, narrow

```
repair-issue --state-root S --key K --action {unschedule,link,reseed} [--story KEY]
```

Only the three structural repairs in T2 that no lifecycle verb expresses:
`unschedule` (1b), `link --story` (1d, refused unless that story's `resolves:` lists `K`), and
`reseed` (1e; `--key` names any key of the epic to reseed). Runs under `issues_lock`. It is a
repair tool, not a lifecycle verb: it refuses any case its matching audit finding does not
hold (exit 2), so it cannot be used to invent a state the audit would not flag.

### 3.4 Health check

- **Check 13 — Backlog integrity and audit.** Runs `audit-issues`. Exit 4 → flag `triage`,
  priority High. Any `fixed-`, `obsolete-`, or `duplicate-candidate` → flag `triage`, priority
  Medium. `issues.yaml` absent → skip.
- HC2's heading changes from "12 checks" to "13 checks".
- HC6 execution order gains `triage` immediately after `harvest-debt`, so markers harvested in
  the same run are audited in it.

---

## 4. Skill surfaces, producers, readers, docs

### 4.1 `pm-plan` intake step

New `skills/_shared/steps/plan/step-backlog-intake.md` (unnumbered, following the
`shared/step-estimate.md` precedent — step order is `SKILL.md`'s load list, so no existing step
is renumbered). `l3io-pm-plan/SKILL.md` full-plan mode loads it after
`step-01-classify-work.md` and before `step-02-readiness-check.md`. Estimate mode never loads it.

1. `list-issues --format json`. If nothing is open with `status: backlog`, print one line and
   continue.
2. Show `backlog` items grouped Critical → High → Medium → Low, with `origin archived` marked;
   list `scheduled` items separately as already in flight.
3. The user selects items, a target epic + sprint, and a classification — or types `skip`.
4. Call `promote-issue`; show any refusal verbatim and let the user choose a different target.
5. Output: promoted count and resulting story keys.

Running before readiness is what makes intake need no new mechanism: readiness grades the
promoted story Amber, elaboration spawns `bmad-create-story` to add technical ACs, and
`step-estimate` re-prices it with everything else.

### 4.2 Closure and producer fixes

Every producer passes `--description "See <path>"` so each future item carries a pointer.

| File | Change |
|---|---|
| `closure/epic-closure.md` §4 | Promotion via `update-issue`; "count promoted" from its output. The "remove the old entry manually" instruction is deleted. |
| `closure/epic-closure.md:58` | Specify `--source "epic-arch-review (<finding id>)"` and a pointer to the arch review output |
| `closure/epic-closure.md:98` | Specify `--source "epic-redteam (<finding id>)"` and `--description "See …/epic-closure/redteam-report.md"` |
| `closure/sprint-closure.md` §7 | Add `--description "See <that phase's report path>"` |
| `sprint/step-03-dev-loop.md` Low path | Add `--description "See {sprint_root}/closure/review-{story_key}.md"` (the failure path already has it) |
| `execute/step-04-arch-gate.md` | Add a pointer to the arch review output |

### 4.3 Readers

- **`l3io-pm-help`** "Open issues": replace `cat {pm_issues_file}` with
  `list-issues --format json`; report counts by severity split into untriaged / scheduled, plus
  the origin-archived count.
- **Doctor `stats`**: the same split, plus resolved counts by resolution from
  `list-issues --resolved`.
- **Doctor `backlog`**: read through `list-issues --format json`; add status and
  origin-archived columns; close with a pointer to `triage`.
- **Doctor `harvest-debt`**: the dry-run "already harvested" count reads both files
  (`list-issues` and `list-issues --resolved`). The write path is unchanged — `append-issue`'s
  dedupe (§2.1) decides the outcome, so a `wontfix` marker is never re-harvested.

### 4.4 Documentation

Changed in the same commit as the code each describes:

- `CLAUDE.md` — State files: `issues.yaml` is open items with a `next` allocator;
  `issues-resolved.yaml` is added; "items removed when resolved" is deleted. Also the
  `check:docs` description: "runs nine checks" is already stale (the script has ten) — it
  becomes eleven, with check 11 described.
- `skills/_shared/status-files.md` — §1 tree, §3 key allocation, §4 schemas (open item, resolved
  item, story `resolves`), §7 subcommand table, §9 concurrency (lock order).
- `docs/l3io-pm-reference.md` — Backlog section and subcommand table. `check:docs` check 4
  (cli-surface) fails until every new subcommand is documented.
- `pm-status.py` module docstring — a Subcommands entry per new verb (`check:docs` check 10).
- `docs/architecture.md` state tree; `docs/getting-started.md` closure paragraph.
- `skills/_shared/steps/shared/step-00-digest.md` is **not** changed: subagents only append, and
  the digest's byte budget (check 8) is preserved.

### 4.5 `check:docs` check 11 — `append-issue-pointer`

Every `append-issue` invocation inside a fenced code block in any `*.md` under `skills/`
passes both `--source` and `--description`. The file set is found by walking `skills/` — no
hand-kept list — so a producer added in a new file or directory is covered on arrival. A prose
mention of `append-issue` outside a code block is not an invocation and is not checked. The
runtime CLI stays lenient: `--description` remains optional on the command line.

### 4.6 Payload

`pm-status.py` is synced to four skills and `skills/_shared/steps/**` to three by
`npm run sync:scripts`; doctor's `steps/` files are its own. Every payload change requires
`node scripts/write-payload-manifest.mjs`; `check:scripts` and `check:manifest` gate both.

---

## 5. Failure handling

| Failure | Behaviour | Detected / repaired by |
|---|---|---|
| Crash between promote steps 1 and 4 | Story still resolves the item on `done` | Audit 1d → `repair-issue --action link` |
| Crash between resolve's two writes | — | Audit 1a (exit 4) → `resolve-issue` rerun |
| `done` hook fails | stderr warning; `set-status` exits 0 | Audit 1c → `resolve-issue` |
| Promoted story deleted by hand | — | Audit 1b → `repair-issue --action unschedule` |
| Malformed `backlog:` or `resolved:` (not a list) | Every mutating verb refuses, exit 2 (extends the existing `append-issue` guard) | — |
| Malformed `next` (not a mapping, or a non-integer value) | stderr warning; reseed to max(valid `next`, highest suffix + 1). Never decreases. | — |
| Concurrent promotes into one sprint | Serialized by `epic_node_lock` | — |
| Concurrent resolve and append | Serialized by `issues_lock` | — |
| Wrong `fixed` confirmed in triage | No reopen verb | Re-raised finding appended as a recurrence (§2.1) |
| Keys reused before this ships | **Undetectable** — no history exists | Documented limitation |
| Project on a legacy layout | Verbs operate on `--state-root`; an absent `issues.yaml` is an empty backlog | Existing legacy detection at activation |

---

## 6. Testing

### 6.1 `pm-status.py` — `skills/_shared/tests/test-pm-status.py`

Existing `unittest` suite. Fixtures are built by running the real verbs (`pm.main`), never by
hand-writing issue or story shapes; concurrency tests use real subprocesses, as the existing lock
tests do, because `_file_lock`'s re-entrancy counter is per-process.

- **Key reuse (regression):** append three, `resolve-issue` the highest, append → `-004`.
  Fails on the code this replaces.
- **Seeding:** no `next`; open `001`–`005`, resolved `007` → next key `008`.
- **Malformed `next`:** reseeds, never decreases, warns.
- **`resolve-issue`:** every required-flag refusal; idempotent re-resolve; unknown key → 3;
  `duplicate --ref` must exist. Invariant 1 asserted after every operation.
- **Crash injection:** make the second `_atomic_dump` raise during resolve and during promote;
  assert `audit-issues` exits 4 with the expected finding, and the documented repair clears it.
- **`promote-issue` end to end:** story node written with `resolves`; estimate block present;
  sprint and epic roll-ups updated; skeleton document has a non-empty Acceptance Criteria
  section; items `scheduled`. Full refusal matrix, including exit 5 for a live foreign lock.
- **`done` hook:** promote, then `set-status --status done` through the CLI → item in
  `issues-resolved.yaml` with `resolution: fixed`, `ref` the story. Also under `--no-events`.
  A hook failure leaves `set-status` at exit 0 with the warning on stderr.
- **`set-field --field resolves`** → exit 2.
- **Dedupe:** re-append of a `wontfix` finding is skipped; of a `fixed` finding is appended with
  `recurrence of`.
- **`update-issue`:** severity actually changes, and the event records from/to.
- **`audit-issues`:** every verdict; every pointer form; every integrity finding → exit 4; an
  unrecognized `source` format → `untraceable`, not an exception.
- **`repair-issue`:** each action refuses when its audit finding does not hold.
- **Concurrency:** mixed parallel `resolve-issue` and `append-issue` lose nothing and keep
  invariants 1–2; parallel `promote-issue` into one sprint yields distinct story keys.
- **Events:** each verb writes its event; a failing event write never fails the verb.

### 6.2 `check:docs` check 11 — `scripts/tests/check-docs.test.mjs`

Node's built-in `node:test` runner (available on the CI's Node 20; no dependency added). Each
test copies the repository to a temp directory and runs the real `scripts/check-docs.mjs` there,
since the script resolves everything from `process.cwd()`.

- An unmodified copy passes.
- **Scope attack:** an `append-issue` block without `--description` in a *new* step file in a
  *new* directory under `skills/` fails, and the failure names that file.
- The same violation inside a `SKILL.md` fails.
- A prose mention of `append-issue` outside a code block passes.

`package.json` gains `"test:scripts": "node --test scripts/tests/"`, and
`.github/workflows/checks.yml` gains a step running it.

### 6.3 Non-hollow proof

For each new guard — the `next` allocator, integrity check 1a, the `resolves` refusal, and
check 11 — run its test once with the guard reverted and confirm it fails. The implementation
plan lists this as an explicit step per guard.

---

## 7. Enforcement coverage

What is mechanically enforced, and what is not:

| Rule | Enforced by |
|---|---|
| Keys are never reused | `next` allocator + test |
| A key lives in one file | `resolve-issue` write order + audit 1a + test |
| Stories never lack an estimate at promotion | `promote-issue` estimates in-process + test |
| Only `promote-issue` writes `resolves` | `DERIVED_NODE_FIELDS` + test |
| A done story resolves its items | `set-status` hook + audit 1c + test |
| Producers pass a pointer | `check:docs` check 11 + test |
| New verbs are documented | `check:docs` checks 4 and 10 (existing) |
| Triage agent cites `file:line` for `fixed` | **Prose only** — `triage.md` T5 downgrades an uncited verdict, but that downgrade is performed by the orchestrating agent, not code |
| Intake never auto-promotes | **Prose only** — no configuration exists to enable it, and `promote-issue` requires explicit `--key`/`--epic`/`--sprint` |
| Triage and intake apply nothing unconfirmed | **Prose only** — the confirmation prompts live in step files |
