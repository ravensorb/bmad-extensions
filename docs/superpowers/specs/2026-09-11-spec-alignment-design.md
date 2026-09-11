# Spec Alignment: Specs as Inputs, Drift as Recorded Decisions, One ADR Home

**Date:** 2026-09-11
**Status:** Design approved in brainstorming 2026-09-11 (seven sections, each approved in turn);
awaiting review of this written spec.
**Decision records:** [ADR-0001](../../adr/0001-pm-status-single-self-installed-file.md) governs
where the new script lives (§1). The plan's first task writes two new records:
- ADR-0004: agents edit architecture specs, PRD/UX/epic docs are proposal-only, and the edit
  is confirmed after it is made.
- ADR-0005: there is one ADR home, and allocation takes the higher of the register and the
  files on disk.

---

## Problem

Verified against `main` at `0f818bd`:

1. **No PM step reads the project's spec docs.** `{planning_artifacts}` is used only for the
   package's own plan outputs.
2. **The epic arch gate never sees the spec.** It hands `l3io-arch-review` Mode B the story
   files and the epic goal only (`steps/execute/step-04-arch-gate.md` §3, §3a). The review
   audits against `standards-*.md`, never against the architecture document the stories are
   supposed to implement.
3. **Nothing ever updates a spec.** Sprint and epic drift reviews (`sprint-closure.md` §6,
   `epic-closure.md` §2) compare the diff to the epic's ADRs and stories. Drift is resolved
   only by a code fix or an accepted ADR, so every accepted departure leaves the spec wrong,
   silently.
4. **ADRs have two unconnected homes.**
   - The PM gate and closure write `{implementation_artifacts}/epic-NNN/arch/adr-NNNN-slug.md`,
     numbered by `state/adr-register.yaml`.
   - arch-review Mode C writes `{project-root}/docs/adr/`, and nothing numbers those.
   - `adr-reserve` never looks at `docs/adr/`, so two different ADR-0003s can coexist.
5. **Technical ACs don't say where they came from.** Story prep passes core
   `bmad-create-story` only the epic and sprint, and no AC records which spec section it was
   distilled from. The dev loop is told, correctly, not to open the spec tree
   (`step-03-dev-loop.md`), which makes that missing record the only possible link between
   code and spec.

## Goals

- Specs become an input to the arch gate and to both drift reviews, as an **index plus the
  sections pointed to**, never as whole documents.
- Every technical-AC dimension names its spec source, and a script checks the pointer.
- Every BLOCKER or MAJOR drift finding ends with a recorded disposition.
  - An accepted architecture departure is written back into the architecture doc. Each edit
    is its own reviewable commit that can be reverted on its own.
  - A PRD, UX or epic change becomes a proposal.
- There is one ADR home and one allocator.
- The token overhead is measured, and the budget is at most 5% of an epic's fresh tokens.

## Non-goals

- Agents editing PRD, UX or epic docs. They write proposals.
- Checking that a pointer is semantically *right*. That is the arch gate reviewer's
  judgement (§10).
- Mapping ACs to test coverage. Test evidence still records exit codes; that is a separate
  problem.
- Changing the dev loop's read scope.
- Hard token caps. The budget is relative and measured (§8).
- Index summaries written by an LLM.
- pm-plan changes. Stories that pm-plan elaborates are checked at pm-execute story prep, which
  enriches them there if they need it.

## Decisions (brainstorming record)

| # | Topic | Decision |
|---|---|---|
| 1 | Spec edit authority | Agents edit architecture docs. PRD, UX and epic docs are proposals only. |
| 2 | Confirmation | Edit, then confirm. Each spec edit is its own `docs(spec)` commit. The closure report lists the edits with their SHAs. Unconfirmed edits are tracked as backlog items. A reject runs `git revert`, and the drift is refiled as a code fix. |
| 3 | ADR home | `docs/adr/`, with one register. `adr-reserve` hands out `max(register next, highest number on disk + 1)`. Mode C uses `adr-reserve`. PM ADRs record their epic. |
| 4 | Provenance | Required on every technical-AC dimension that applies: `Spec: <path>#<anchor>`, or `Spec: none — <reason>`. A missing or broken pointer blocks `ready-for-dev`. |
| 5 | Token budget | Relative only: at most 5% of an epic's fresh tokens (input + output + cache_write). Measured on a pilot epic, then tracked per epic. No hard caps. |
| 6 | Tracking | Reuse the issue lifecycle. `spec-change` and `spec-proposal` are item kinds. Confirm is `resolve-issue --resolution fixed`. A reject reverts, resolves the item `wontfix`, and appends a new defect. |
| 7 | Default | `spec_alignment = true` ships **on**. The pilot measures after release, and its result is recorded here as an amendment (§8). |
| 8 | Script location | `skills/_shared/spec-align.py`. pm-execute and util-doctor both use it, so under ADR-0001 it is shared, not single-consumer. |

Two refinements were made while writing this, both within the approved design:
- **The provenance token is `Spec: none — <reason>`**, not `n/a: …`. A dimension that does
  not apply is already written `N/A — <reason>`, and one token must not carry two meanings.
- **Drift finding IDs go in the `#` column of the findings table** that Mode B already writes
  (`references/review-report.md`). There is no new heading format.

## 1. `spec-align.py`

**Location and payload.**
- The canonical source is `skills/_shared/spec-align.py`.
- `sync-shared-scripts.mjs` copies it into `skills/l3io-pm-execute/scripts/` and
  `skills/l3io-util-doctor/scripts/`, and both payload manifests cover it.
- It is invoked from the skill's own `scripts/` copy, like `audit-backlog.py`. It does not
  self-install. Only `pm-status.py` self-installs, because many skills share one runtime copy
  of it.

**Dependencies,** declared in its PEP 723 header and provisioned by `uv run`:

| Package | Used for |
|---|---|
| `markdown-it-py>=3` | Parsing markdown: headings, fences, setext headings, tables |
| `mdit-py-plugins>=0.4` | The `anchors` plugin, which produces GitHub-style slugs with `-1`, `-2` suffixes for duplicates |
| `ruamel.yaml>=0.18` | The disposition files, and reading ADR metadata |
| `unidiff>=0.7` | Parsing `git diff -U0` output for the scope guard. Diff parsing is a library-first domain |
| `tenacity>=8` | Waiting for the lease and retrying on `index.lock`. Retry and backoff are library-first domains |

Git is driven through the `git` CLI via `subprocess`. Probed 2026-09-11 on markdown-it-py 3.0.0
and mdit-py-plugins 0.6.1:
- `# Data Model & Auth` → `data-model--auth`
- a second `## Data model` → `data-model-1`
- a `#` line inside a fence is not a heading
- setext H2s are found

**Common flags.** Callers pass values already bound from config, never a config file path.
- Every subcommand takes `--project-root P`, `--planning-root P` and `--impl-root P`.
- `--spec-path G` is repeatable and comes from pm-execute's `spec_paths`.
- Subcommands that touch issues also take `--state-root`.

**Exit codes:**

| Code | Meaning |
|---|---|
| 0 | OK |
| 1 | A **report-mode** check found problems: `check-pointers --all`, `check-links`, `check-stale`, or `build --check` on a stale index |
| 2 | A **gate** refused: `check-pointers --story`, `check-dispositions`, a `commit` guard, `disposition` validation, or `reject` on a revert conflict. Also invalid input |
| 5 | Lease held by another owner, matching `pm-status.py check-lock` |

**Subcommands:**

| Subcommand | Purpose | Section |
|---|---|---|
| `build [--if-stale] [--check]` | Build the spec index; `--check` reports staleness without writing | §2 |
| `check-pointers (--story F… \| --all)` | Checks that the provenance lines are present and resolve | §3 |
| `sections --stories F…` | Pointers → a de-duplicated list of `path Lstart–end` ranges | §3 |
| `disposition --review F --finding ID --disposition D [--spec PTR] [--adr P]` | Records one finding's disposition | §4 |
| `check-dispositions --review F --expect "Blocker: N, Major: N, Minor: N"` | Finding completeness plus a count cross-check | §4 |
| `sync-plan --epic E [--defer]` | The epic's spec-sync work list; `--defer` writes pointer-only proposals instead | §4 |
| `lease acquire --owner E [--wait-minutes N] [--ttl-minutes N]` / `lease release --owner E` | The spec-edit lease | §4 |
| `commit --epic E --finding ID --paths F… [--rename-anchor OLD=NEW]` | Applies the guards, then makes one `docs(spec)` commit | §4 |
| `reject --state-root S --key K` | Reverts or declines a spec item and refiles the drift as a defect | §5 |
| `adrs --epic E` | Lists the epic's ADRs from both homes | §6 |
| `migrate-adrs (--plan \| --apply)` | Moves ADRs from the old home to `docs/adr/` | §6 |
| `check-links [--epic E]` | Checks that ADRs departing from the spec are linked from that section | §7 |
| `check-stale --state-root S` | Unconfirmed spec changes that later commits have built on | §7 |

## 2. The spec index

**Discovery.** It searches `{planning_artifacts}` recursively, matching `*.md` only. The patterns
are the three planning-artifact kinds in doctor's `layout-cleanup.md` heuristic 5, copied
verbatim; check 13 keeps the two in agreement (§7):

| Kind | Patterns | Precedence |
|---|---|---|
| architecture | `*architecture*`, `*arch-spec*`, `*system-design*`, `*tech-design*` | 1 |
| ux | `*ux-spec*`, `*ux-design*`, `*wireframe*`, `*mockup*`, `*ui-spec*` | 2 |
| prd | `*requirements*`, `*prd*`, `*brief*`, `*spec*` | 3 |

Epic planning docs form a fourth kind, `epics`, matched by `*epics*`, at precedence 4. It is
not in doctor's list, and check 13 compares only the three kinds the two share. Only
`architecture` sections can be `spec-updated` (§4).

Other rules:
- **Precedence.** A file that matches several kinds takes the lowest precedence number. For
  example, `ux-spec.md` is `ux`, not `prd`.
- **Sharded docs.** A directory whose name matches a pattern and contains `index.md` is
  indexed whole, under that kind. That is BMad's sharded layout, for example `prd/index.md`
  plus section files.
- **Override.** A non-empty `spec_paths` (a list of paths or globs in pm-execute's
  `customize.toml`) replaces discovery entirely. It covers specs kept outside
  `{planning_artifacts}`, such as `docs/architecture.md`, and those files take their kind from
  the same pattern table.

**Format.** `{implementation_artifacts}/spec/spec-index.md`:

```
# Spec index — generated by spec-align.py; do not edit
# inputs-sha256: 3f9c…  ·  bytes: 5,412  ·  specs: 3  ·  sections: 41
## architecture · _bmad-output/planning-artifacts/architecture.md
- _bmad-output/planning-artifacts/architecture.md#data-model — Data model: Orders live in Postgres, one row per… (L120–188)
```

- It has one line per heading at H1–H3.
- Paths are **relative to the project root**, and each entry is exactly the pointer a story
  uses.
- The summary is the section's first sentence, cut to about 100 characters.
- The line range runs from the heading line up to the line before the next heading of the
  same or a higher level.
- No section body is ever copied into the index.

**Freshness.**
- **The hash.** `inputs-sha256` is a SHA-256 over the sorted pairs of (path, content hash).
- **`build --if-stale`** rebuilds only when the hash differs, and never rewrites an unchanged
  index.
- **`build --check`** exits 1 when the index is stale and writes nothing.
- **Committed.** The index is committed by both closure checkpoints (§4), so a reviewer can
  see exactly what the agents saw.

**Size.** There is no cap. The header records the bytes and the number of sections, and the
closure report shows them. Above 16 KB, `build` prints a stderr warning that doesn't block
anything.

**No specs, or files it can't read:**
- **No spec found.** The index says `no spec docs found` and the build exits 0.
- **Unreadable or non-UTF-8 files.** Each one is listed as `skipped: <path> (<reason>)`.
- **No gate fails** on either.

## 3. How specs reach each lifecycle point

The switch (§8) gates all of these points except the dev loop, which doesn't change.

**The story's AC layout.** `check-pointers` parses it with markdown-it-py:

```markdown
## Technical acceptance criteria

### Interface contracts
POST /orders accepts {sku, qty}; returns 201 with Location.
Spec: _bmad-output/planning-artifacts/architecture.md#order-api

### Error and edge case handling
N/A — read-only path; failures surface as the framework's 5xx.

### Observability requirements
…
Spec: none — the architecture doc has no observability section
```

The rules:
- **The headings.** The six H3 names are fixed:
  1. Interface contracts
  2. Error and edge case handling
  3. Observability requirements
  4. Security considerations
  5. Testability approach
  6. Existing-library check

  They live in one constant, `DIMENSIONS`, in `spec-align.py`. Check 13 asserts that the
  enrichment prompt names the same six.
- **A dimension that doesn't apply** is a paragraph starting `N/A — `. It needs no `Spec:`
  line.
- **A dimension that applies** ends with either:
  - one or more `Spec: <path>#<anchor>` lines, or
  - exactly one `Spec: none — <reason>`. In a project with no spec docs, the reason is
    `no spec docs in this project`.
- **A pointer must resolve.** Its path must appear in the current index, and its anchor must
  exist in that file.

**`check-pointers --story F…`** exits 2 and names the failing story, dimension and line when:
- a dimension is missing;
- an applicable dimension has no `Spec:` line;
- a pointer doesn't resolve.

A story with no `## Technical acceptance criteria` section is reported as **pre-provenance**.

**Epic arch gate** (`step-04-arch-gate.md`):
- §3 runs `build --if-stale`. §3a adds the index path to the reviewer's named inputs.
- The reviewer framing checks each story against the sections its pointers name, opening only
  those line ranges from `sections`.
- Two new finding types:
  - `spec-conflict`: a story contradicts its spec.
  - `spec-gap`: a story needs a decision its spec doesn't make.
- The severities stay as they are. A BLOCKER or MAJOR is resolved as it is today, by patching
  the story or by writing an ADR. An ADR that departs from the spec fills in its
  `Departs from spec:` line (§6).

**Story prep** (`step-02-story-prep.md` §2):
- **Which stories are thin.** With the switch on, a story is thin when `check-pointers` fails
  for it. This covers stories that already had ACs but no pointers.
- **The enrichment prompt** gets the index path, the layout above, and the rule: "open only
  the sections you point to; cite, do not copy."
- **The re-check** at the end of §2 becomes `check-pointers` over the enriched stories. Exit 2
  produces the existing `BLOCKED: story {story_key} still missing technical ACs…` line.

**Dev loop:** no change. The agent still doesn't open the spec tree. When an AC turns out to
be missing something, its existing fallback now opens the single range the `Spec:` pointer
names, and records that in its completion notes as it does today.

**Sprint drift review** (`sprint-closure.md` §6):
- **Inputs.** The reviewer gets the index path plus the `sections --stories` ranges for this
  sprint's stories.
- **Finding IDs.** Its findings table uses the IDs `SD-{n}`.
- **Extra reading.** A diff hunk with no covering pointer allows one extra section, picked
  from the index.
- **The `Sections read:` footer** lists every range the reviewer opened.
- **Dispositions** are recorded with `disposition` (§4). Spec edits are **not** made at sprint
  level: they are carried to the epic's single spec sync.
- **The sprint gate changes.** For a BLOCKER or MAJOR drift finding, `spec-updated` and
  `spec-proposal` now satisfy sprint closure's gate, alongside the existing code fix and
  accepted ADR. The finding is not dropped: it is recorded, and the edit or proposal happens
  at epic closure.

**Epic drift review** (`epic-closure.md` §2): the same inputs as the sprint review, across all
of the epic's stories, with the IDs `AD-{n}` it uses today.

**The footer rule** applies to all three reviewers: the arch gate, the sprint drift review and
the epic drift review. It is self-reported; §10 says what checks it objectively.

## 4. Drift dispositions and spec sync

**Dispositions.** A finding can have one of four:

| Disposition | Meaning | Constraint |
|---|---|---|
| `resolved-in-code` | The fix loop fixed it | — |
| `adr-justified` | An accepted ADR records the departure | `--adr` names an existing file |
| `spec-updated` | The spec is changed to match what was built | The `--spec` pointer's kind must be `architecture`; anything else exits 2 |
| `spec-proposal` | A PRD, UX or epic change is proposed | The `--spec` pointer resolves |

`disposition` writes `drift-dispositions.yaml` next to the review. For the epic, that is
`epic-closure/drift-dispositions.yaml`; for a sprint, `{sprint_root}/closure/drift-dispositions.yaml`.

```yaml
review: epic-closure/arch-drift-review.md
findings:
  AD-3:
    severity: MAJOR            # from the findings table
    disposition: spec-updated
    spec: _bmad-output/planning-artifacts/architecture.md#order-api
    adr: null
    commit: null               # written by `commit`
    issue: null                # written by spec sync
```

A BLOCKER or MAJOR finding needs a disposition. A MINOR finding may have one; if it doesn't,
it goes to the backlog as it does today.

**`check-dispositions`**:
- It parses the review's findings table: the `#` column for the ID, `Severity` for the
  severity.
- It exits 2 when:
  - a BLOCKER or MAJOR finding has no disposition;
  - the counts it parsed differ from `--expect`, which the orchestrator copies from the
    reviewer's mandatory final line, `DONE — Blocker: N, Major: N, Minor: N`. This catches a
    review written in the wrong shape, which would otherwise pass with zero findings parsed.
- It runs at the end of sprint-closure §6 and epic-closure §2, before those phases can
  complete.

**Spec sync** (a new `epic-closure.md` §2a). It runs after the §2 fix loop and before the §5
closure report, and only when `spec_alignment` is on.

1. **`sync-plan --epic E`** builds the work list, using no LLM tokens. It gathers:
   - every `spec-updated` and `spec-proposal` disposition from the epic's sprint and epic
     disposition files;
   - every accepted ADR from `adrs --epic E` (arch-gate ADRs included) whose
     `Departs from spec:` section doesn't link to it yet.

   Each item carries its finding's row from the review's findings table, its spec pointer
   and section range, and its ADR path if it has one. That is everything the agent needs,
   passed by reference.

   **If the list is empty, spec sync is skipped with no dispatch.**

   **`sync-plan --epic E --defer`** writes a proposal file for every pending item, with no
   agent, and prints the list. Each file holds pointers only: the finding ID, the review
   path, the spec pointer, and the ADR path if there is one. §9's lease-timeout fallback uses
   this.
2. **Lease.** `lease acquire --owner {epic_key} --wait-minutes 15` takes the spec-edit lease.
   - **Where it lives.** It is the file `{implementation_artifacts}/state/spec-sync.lock`,
     written atomically under an `fcntl` flock. It holds `owner`, `acquired_at` and
     `expires_at`, with a default time limit of 30 minutes.
   - **Kept out of git.** The name ends in `.lock`, so pm-status's existing `*.lock` rule in
     `state/.gitignore` covers it. That rule is already in place by epic closure, because
     every `set-status` has taken an epic lock inside the state root by then.
   - **Taking over.** An expired lease is taken over, with a stderr line naming the previous
     owner.
   - **Waiting** uses tenacity, polling until `--wait-minutes` runs out. Then it exits 5.
   - **Release** happens on every exit path.
3. **The dispatch.** One agent, dispatched as `--agent l3io-spec-sync --epic {epic_key}`, gets
   the work list, the index, and the `sections` ranges. It opens nothing else.
   - **For each `spec-updated` item, and each ADR link:**
     - The agent edits only the target section. An ADR link is written as a relative
       markdown link to `docs/adr/NNNN-slug.md`.
     - It then runs `commit --epic {epic_key} --finding AD-3 --paths <file>`. Before
       committing, the script checks:
       - **Scope guard.** It re-resolves the pointer's section against `HEAD`, parses
         `git diff -U0 -- <file>` with `unidiff`, and exits 2 if any changed line falls
         outside that section.
       - **Anchor guard.** It exits 2 if the edit removes or renames an anchor that any story
         points to. `--rename-anchor OLD=NEW` rewrites those `Spec:` lines, and the story
         files join the same commit, so a revert undoes both.
     - If both pass, it commits with
       `git commit -s --only -m "docs(spec): {epic_key} {finding} — {title}" -- <paths>`.
       `--only` commits exactly those paths, even in a shared checkout.
     - It then writes the SHA into the disposition file and prints it.
     - One finding means one commit.
   - **For each `spec-proposal` item:** the agent writes
     `epic-closure/spec-proposals/{finding}.md` and edits no spec. The file gives the target
     pointer, the proposed change, why the change is proposed, and the finding it comes
     from.
   - **Tracking, for both kinds,** is one `append-issue` per item:

     ```bash
     python3 {pm_status} append-issue --state-root {pm_state_root} \
       --epic {epic_nnn} --sprint "" --kind {spec-change|spec-proposal} \
       --ref {sha|proposal path} --title "{finding title}" \
       --source "spec-sync ({finding_id})" --severity {mapped} \
       --description "Confirm or reject: /l3io-util-doctor triage"
     ```

     The finding's severity maps BLOCKER → High, MAJOR → Medium and MINOR → Low. The item's
     key goes into the disposition's `issue:` field.
4. **Release the lease.**

**Epic closure commit checkpoint** (a new `epic-closure.md` §7). It works like sprint-closure's
§9:
- It untracks any `*.lock` files first.
- It stages `{implementation_artifacts}/state/`, `epic-{epic_num}/`,
  `{implementation_artifacts}/spec/` and `{planning_artifacts}/`, by explicit path.
- It commits as `chore({epic_key}): close epic`.

Sprint-closure §9 also adds `{implementation_artifacts}/spec/` to its staged paths.

**Closure report** (`epic-closure.md` §5). A new **Spec changes** section gives:
- one row per disposition: the finding, its disposition, its SHA or proposal file, and its
  backlog key;
- the index size and section count;
- the total number of sections read, summed from the footers;
- spec sync's share of the epic's fresh tokens, from
  `usage --agent l3io-spec-sync --epic {epic_key}`.

A line that doesn't block anything warns when that share is above 5%.

## 5. Issue lifecycle changes (`pm-status.py`)

These are about 100 lines, keeping the file within ADR-0001's 8,000-line limit (6,604 today).
There is no schema version bump.

| Change | Detail |
|---|---|
| `append-issue --kind {defect,spec-change,spec-proposal}` | The default is `defect`. `kind` is written only when it isn't `defect`, so existing files still read correctly |
| `append-issue --ref R` | Stored on the item as `ref`, matching the `ref` that resolved items already carry |
| `list-issues --kind K` | A filter, alongside the existing ones |
| `promote-issue` | Exits 2 on any item whose kind isn't `defect`. Spec items are not story work |
| `audit-issues` 1k | Flags an unknown `kind`, and a `spec-change` or `spec-proposal` with no `ref` |

**Confirm and reject.** Doctor's `triage.md` gets a spec pass, and every write is confirmed.
For each open spec item it shows `git show --stat {ref}` and the diff, or the proposal file,
then asks whether to confirm, reject or skip.
- **Confirm:**
  - a spec change is resolved with `resolve-issue --resolution fixed --ref {sha} --cause triage`;
  - an accepted proposal is resolved `fixed`, with `--ref` naming the commit in which a
    person applied it.
- **Reject:** `spec-align.py reject --state-root S --key K` does the following in order.
  1. **Spec change:** it runs `git revert --no-edit {ref}`.
     - On a conflict it runs `git revert --abort`, leaves the item open, exits 2 and names
       the conflicting files.
     - For a proposal, there is nothing to revert.
  2. It runs `resolve-issue --resolution wontfix` with `--ref` set to the revert SHA, or to
     the proposal path.
  3. It runs `append-issue --kind defect` with the item's severity. The title is "Code
     diverges from spec: …" and `--source "spec-reject ({key})"`. The drift is now a code fix.

pm-help reports the count of unconfirmed spec changes and open proposals, from
`list-issues --kind`.

## 6. One ADR home

**Home.** Every ADR is written to `{project-root}/docs/adr/NNNN-slug.md`. `epic-NNN/arch/`
keeps only `arch-gate-review.md`, which is a review, not an ADR.

**`adr-reserve`.** Its signature doesn't change, so the digest (`step-00-digest.md:117`)
doesn't either. Under its existing flock it now scans two places:
- `docs/adr/[0-9][0-9][0-9][0-9]-*.md`, found as the git top-level of `--state-root` via
  `git rev-parse --show-toplevel`;
- the old home, `<state-root>/../epic-*/arch/adr-[0-9][0-9][0-9][0-9]-*.md`.

The first number it hands out is `max(register next, highest number found + 1)`. The
register is still what records reservations in flight; the scan only stops collisions with
files that already exist. If the state root isn't in a git repo, it scans the old home only
and prints a stderr warning.

**Mode C** (`l3io-arch-review`):
- When `{project-root}/_bmad/scripts/pm-status.py` exists, it calls
  `adr-reserve --state-root {implementation_artifacts}/state --epic n/a --slug {slug}`.
- Otherwise (the arch module installed without l3io-pm), it uses the highest number in
  `docs/adr/` plus one. That fallback is documented in `SKILL.md` as safe for a single writer
  only, and is correct because no PM agents run in that setup. `adr-reserve` would skip those
  numbers later anyway.

**Template.** `assets/adr-template.md` gets two new metadata lines:
- `- **Epic:** E003 | n/a`
- `- **Departs from spec:** <path>#<anchor> | n/a`

The arch gate's ADR subagents are pointed at this template (§6 of the step file), and write to
`docs/adr/`.

**`adrs --epic E`** lists the `docs/adr/` files whose `Epic:` line matches, plus any files
still in the old home under `epic-{nnn}/arch/`, with a stderr warning. It replaces three
hand-written globs:
- `epic-closure.md` §2, the drift review's ADR paths;
- `epic-closure.md` §3, the redteam seeds;
- `step-04-arch-gate.md` §6, where the ADR is drafted.

**Migration.**
- **Detection.** Doctor Check 15, `adr-state`, reports ADRs still in the old home and a
  register that has fallen behind (§7).
- **The mode.** A new doctor mode, `migrate-adrs` (`steps/migrate-adrs.md` plus a table
  row), runs `spec-align.py migrate-adrs --plan`, shows the plan, confirms, then runs
  `--apply`:
  1. **Inventory.** List both homes and pair up any number that appears in both.
  2. **No collision:** `git mv` each file to `docs/adr/NNNN-slug.md`, add its `Epic:` line
     from its directory, and rewrite exact old-path references in
     `{implementation_artifacts}/**/*.md`.
  3. **Collision:**
     - The `docs/adr/` file keeps its number, because it may be cited outside PM artifacts.
     - The epic ADR gets a newly reserved number.
     - `ADR-NNNN` mentions are rewritten only inside that epic's artifact tree.
     - Mentions elsewhere are listed for a person to review, not rewritten.
  4. **Commit once,** by explicit path: `docs(adr): migrate epic ADRs to docs/adr`.
- **Unmigrated projects keep working,** because `adr-reserve` and `adrs` both read the old
  home.

## 7. Mechanical checks

**The rule: the free check runs first and decides whether an agent runs at all.**
- An empty `sync-plan` means no spec-sync dispatch.
- A failing `check-pointers` produces `BLOCKED` before the arch gate or the dev loop spends
  anything.

**Checks in consumer projects:**

| Check | Tool | Where it runs | Blocks? |
|---|---|---|---|
| Provenance present and resolving | `check-pointers --story` | Story prep | Yes |
| Pointers broken by later edits | `check-pointers --all` | Epic closure after sync; doctor Check 16 `spec-pointers` | Health check only reports. Pre-provenance stories are informational |
| Edit outside the section | Scope guard in `commit` | Spec sync | Yes, then the fallback in §9 |
| A pointed-to anchor renamed | Anchor guard in `commit` | Spec sync | Yes, unless `--rename-anchor` |
| Disposition completeness, count cross-check | `check-dispositions` | Sprint and epic closure | Yes |
| An ADR departing from the spec but not linked from it | `check-links` | Feeds `sync-plan`; doctor Check 17 `adr-links` | Health check reports |
| An unconfirmed spec change that later edits build on | `check-stale` (reads `pm-status list-issues --kind spec-change --format json`, then `git log {ref}..HEAD -- <file>`) | Doctor Check 18 `spec-stale`; pm-help | Reports |
| ADRs in the old home; register `next` at or below the highest number on disk | pm-status plus a scan | Doctor Check 15 `adr-state` | Reports; `adr-reserve` fixes the register by itself |
| Committed index stale | `build --check` | Doctor Check 19 `spec-index` | Reports |
| Unknown `kind`; spec item with no `ref` | `audit-issues` 1k | Existing audit | Existing behaviour |

The doctor health check grows from 14 checks to 19.

**Checks in this package's CI** (`check:docs`, with planted-violation tests in
`test:scripts`):
- **Check 4, extended.** The documented `spec-align.py` subcommands agree in both directions
  with its parser. Step files that invoke it are found by walking `skills/`.
- **Check 13, spec-align contract.**
  - The `architecture`, `ux` and `prd` pattern sets in `spec-align.py` match
    `layout-cleanup.md` heuristic 5.
  - The six `DIMENSIONS` names match the enrichment prompt in `step-02-story-prep.md` §2.
- **Check 14, ADR home.** No runtime directive under `skills/` names the old ADR path
  (`arch/adr-` or the glob `arch/*.md`); `arch/arch-gate-review.md` stays legal. The
  exceptions are:
  - `steps/migrate-adrs.md`;
  - `steps/health-check.md`;
  - the scan code in `pm-status.py` and `spec-align.py`.

  Its planted violations test the scope as well as the rule: one sits in a new directory, one
  inside a fence.

## 8. The switch and measurement

**The switch.** `spec_alignment = true` goes under `[workflow]` in pm-execute's
`customize.toml`, next to `spec_paths = []`, and ships **on**.
- **What it gates:** the index given to reviewers, the pointer requirement at story prep, and
  the spec-sync dispatch.
- **With it off,** dispositions are limited to `resolved-in-code` and `adr-justified`, which
  is today's behaviour.
- **Always on:** ADR unification and every doctor check, because they cost no tokens.

**The pilot,** run after merge on one epic in a consumer project that has specs, chosen by the
user:
- **Paired runs.** Each affected dispatch runs twice on the same inputs, once as normal and
  once with the switch off:
  - the arch gate;
  - story-prep enrichment, on copies of the thin stories;
  - each sprint drift review;
  - the epic drift review.

  The baseline runs use the identity `--agent <name>:baseline`, and write their output under
  `epic-{nnn}/pilot/`, where it is discarded.
- **Spec sync** has no baseline, because none of its cost exists without it. It is measured
  under `l3io-spec-sync`.
- **The number.** `usage --agent` gives each pair's fresh tokens. The pilot's result is:
  Σ(on − off) over the pairs, plus spec sync, divided by the epic's fresh tokens.
- **The record.** The result is added to this spec as an amendment.
- **Over 5%,** the index is trimmed: `max_level` goes to 2 and summaries are dropped, in that
  order. Then the pilot is re-measured on the next epic.

**After the pilot:** every epic's closure report carries the measured spec-sync share, the
index size and the number of sections read (§4).

## 9. Failure handling

Spec alignment never blocks an epic's code-quality gates. Every failure below falls back to
something cheaper and is reported in the closure report's **Spec changes** section.

| Failure | Behaviour |
|---|---|
| No spec docs | The index says so; pointers are `Spec: none — no spec docs in this project`; reviewers run as they do today |
| Unreadable or non-UTF-8 spec | `skipped:` in the index |
| Lease still held after `--wait-minutes` (exit 5) | No agent is dispatched. `sync-plan --defer` writes a pointer-only proposal file for each pending item, and the orchestrator appends a `spec-proposal` item for each. Closure continues |
| Lease holder crashed | The time limit expires, and the next `acquire` takes it over and logs it |
| Scope or anchor guard refuses twice for one finding | That finding falls back to `spec-proposal`; the working-tree edit is restored with `git restore -- <file>` |
| Commit hook fails | Same as above |
| `.git/index.lock` contention | `commit` retries with tenacity backoff, up to 5 attempts, then treats it as a failed commit |
| Revert conflict on reject | `git revert --abort`; the item stays open; exit 2 names the files |
| `adr-reserve` outside a git repo | It scans the old home only and warns |
| `markdown-it-py` can't be provisioned | The `uv run` failure takes the step's normal `FAILED:` path, as a missing `ruamel.yaml` does for pm-status |

## 10. Enforcement coverage

**Enforced mechanically:**
- provenance that is present and resolves;
- disposition completeness, and the count cross-check;
- the scope and anchor guards;
- one commit per finding;
- item kind and ref integrity;
- ADR number allocation across both homes;
- the ban on the old ADR home;
- the pattern and dimension-name agreement;
- subcommand documentation.

**Prose only, and how each is covered:**
- **Reviewers read only the ranges they were given.** This is self-reported in the
  `Sections read:` footer. The objective check is `usage --agent`'s `cache_write` for each
  review dispatch, and the pilot compares it against the baseline. A single run is not
  enforced.
- **A pointer that resolves also points at the right section.** This is the arch gate
  reviewer's judgement. Nothing checks it mechanically.
- **Spec-sync edits are correct.** A person confirms each one (§5), and it stays an open
  backlog item until they do.
- **The dev loop's read scope.** This is unchanged, and measured as it is today.

## 11. Testing

- **`skills/_shared/tests/test-spec-align.py`** uses unittest and drives the real CLI through
  `subprocess`. It carries the same private temp-dir guard block as the other five Python
  suites. It covers:
  - **The index.** Nested, setext and fenced headings; duplicate slugs; sharded directories;
    kind precedence; `spec_paths`; non-UTF-8 and unreadable files; an empty project; the
    freshness rules (no rewrite when unchanged, a rewrite on change, `--check` exits 1); the
    size warning.
  - **Pointers.** Each missing dimension; an `N/A — ` dimension with no pointer; a
    `Spec: none — ` dimension; an unresolvable path; an unresolvable anchor; a duplicate-suffix
    anchor; a pre-provenance story; the `sections` de-duplication and ranges.
  - **Dispositions.** Every refusal (`spec-updated` on a PRD, a missing ADR file, an unknown
    value); the table parse; an `--expect` mismatch; a BLOCKER with no disposition.
  - **`sync-plan`.** The sprint and epic union, ADR link items, and an empty plan.
  - **The lease.** Contention between real subprocesses; expiry and takeover; release on
    error.
  - **`commit`, in a real temporary git repo.** The scope guard refuses; the anchor guard
    refuses; `--rename-anchor` rewrites the stories in the same commit; `--only` leaves other
    dirty and staged files alone; the SHA is written back; the retry on `index.lock`.
  - **`reject`.** A clean revert, a conflicting revert that aborts, and a proposal decline.
    Each one checks the resulting pm-status state through `list-issues`.
  - **ADRs.** `adrs` reads the `Epic:` line and lists the old home; `migrate-adrs` covers
    `--plan` and `--apply`, with and without a collision.
  - **`check-links` and `check-stale`,** over real git history.
- **`test-pm-status.py`**:
  - `--kind` and `--ref` round-trips;
  - the `list-issues --kind` filter;
  - `promote-issue` refusing spec items;
  - `audit-issues` 1k;
  - `adr-reserve` taking the max from `docs/adr/`, from the old home, from a register that has
    fallen behind, and outside a git repo;
  - the existing concurrency test, extended with a hand-written ADR already on disk.
- **`test:scripts`**: planted violations for checks 13 and 14 and for the extended check 4,
  including the scope attacks named in §7.
- **Each guard is proven not hollow:** revert the guard, confirm its test fails, then
  restore it.
- **CI:** a new `checks.yml` step,
  `uv run skills/_shared/tests/test-spec-align.py`.

## 12. Files touched

- **New files:**
  - `skills/_shared/spec-align.py`
  - `skills/_shared/tests/test-spec-align.py`
  - `skills/l3io-util-doctor/steps/migrate-adrs.md`
  - `docs/adr/0004-agents-edit-architecture-specs.md`
  - `docs/adr/0005-one-adr-home.md`
- **`skills/_shared/pm-status.py`:** the §5 flags; the `adr-reserve` scan.
- **`skills/_shared/steps/`:**
  - `execute/step-04-arch-gate.md` (§3, §3a, §6)
  - `sprint/step-02-story-prep.md` (§2)
  - `sprint/step-03-dev-loop.md` (the fallback sentence)
  - `closure/sprint-closure.md` (§6)
  - `sprint/step-04-sprint-closure.md` (§9 staging)
  - `closure/epic-closure.md` (§2, §2a, §3, §5, the new §7)
  - `shared/step-00-digest.md`: only if a routing row is needed. Keep it within check 8's
    budget.
- **`skills/l3io-pm-execute/customize.toml`:** `spec_alignment` and `spec_paths`.
- **`skills/l3io-arch-review/`:** `SKILL.md` (Mode C and Output); `assets/adr-template.md`;
  the Mode B framing for the arch gate, carried in the step file rather than in arch-review
  itself.
- **`skills/l3io-util-doctor/`:**
  - `SKILL.md` (the mode table)
  - `steps/health-check.md` (Checks 15–19)
  - `steps/triage.md` (the spec pass)
  - `steps/layout-cleanup.md` (unchanged; it is compared by check 13)
- **`skills/l3io-pm-help/SKILL.md`:** the spec item counts.
- **`skills/_shared/status-files.md`:** the register section, the item `kind` and `ref`, and
  `spec-sync.lock`.
- **Repo tooling:** `scripts/sync-shared-scripts.mjs` (the new sync group);
  `scripts/check-docs.mjs` (checks 4, 13 and 14, and its header);
  `.github/workflows/checks.yml`.
- **Top-level docs:** `CLAUDE.md` (check count, doctor modes, ADR home, the new shared
  script); `docs/l3io-pm-reference.md`.
- **Regenerated, never hand-edited:** the payload copies and manifests.

## 13. Deferred

- Mapping ACs to test coverage.
- Letting agents edit PRD, UX or epic docs. This would be revisited only if proposals pile up
  unconfirmed.
- Trimming the index automatically by budget. Trimming is a code change made after the pilot,
  not a runtime setting.
- The open issue-lifecycle follow-ups (the reseed hint, `triage.md:38` wording, the duplicate
  malformed-list refusal) and the decision on the `move-epic` race. Both are tracked in memory,
  not here.
