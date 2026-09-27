# v3.0.0 — State Relocation and Per-Story Sharding

**Date:** 2026-08-16
**Status:** Approved for planning
**Supersedes:** the state-layout sections of `2026-08-14-v2-migration-design.md` (Section 2 and the `_bmad/state/` references throughout)

---

## Problem

The v2.0.0 migration moved sprint/epic state from `{implementation_artifacts}/` to
`{project-root}/_bmad/state/`. That directory is explicitly gitignored:

```
# BMad installer state — managed by npx bmad-method install, not module source
_bmad/
```

Three consequences follow, in descending order of severity:

1. **State is not version-controlled.** Sprint status, epic progress, backlog issues, and
   calibration data do not commit. No history, no team sharing, no PR visibility, and a
   fresh clone or CI checkout starts with no project state.
2. **State lives in an installer-owned tree.** The directory is declared as managed by
   `npx bmad-method install`. Project state sits where another tool claims ownership, so
   a reinstall or upgrade is a plausible path to losing it.
3. **State is undiscoverable.** A leading-underscore, tool-namespaced directory is not
   where anyone browsing the repo or reviewing a PR looks for sprint state.

A secondary problem surfaced during design. Per-epic sharding (`active/E{nnn}-status.yaml`)
was built for parallel subagents on one machine, using `fcntl.flock` and a session-scoped
`_lock` with a 30-minute TTL. Neither mechanism coordinates developers across clones, and
per-epic granularity means two developers working *different stories in the same epic*
collide on one file — a false conflict, since they edit unrelated nodes.

Committing state to git changes the concurrency problem from **locking** to **merging**.

---

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | State moves to `{implementation_artifacts}/state/` | Committed, outside the installer tree, co-located with the artifacts it describes |
| 2 | `pm-calibration.yaml` moves there and is committed | Learned ratios are team knowledge, expensive to rebuild (≥3 samples per component) |
| 3 | Migration blocks activation; `migrate-state` performs it | Explicit and auditable; blocking is honest when a tool cannot find its state |
| 4 | Per-story sharding | Eliminates false conflicts; makes per-story git history legible |
| 5 | State dir naming mirrors the artifact tree | Makes the state↔artifact correspondence a directory diff instead of a YAML parse |
| 6 | Epic directories move between status folders; never collapse | Preserves git history through `git mv`; keeps the mirror permanent |
| 7 | `pm-status.py` takes keys, not paths | Layout knowledge lives in one place; future layout changes stop being breaking |
| 8 | Claim protocol deferred | Layout admits `claimed_by` with no structural change |

---

## Section 1: Layout

```
{implementation_artifacts}/
│
├── state/                                   ← machine-written, pm-status.py only
│   ├── planned/
│   │   └── epic-005/
│   │       ├── epic.yaml                    ← depends_on lives here
│   │       └── sprint-01/
│   │           ├── sprint.yaml
│   │           └── E005-S01-001.yaml
│   ├── active/
│   │   ├── epic-001/
│   │   │   ├── epic.yaml
│   │   │   ├── sprint-01/
│   │   │   │   ├── sprint.yaml
│   │   │   │   ├── E001-S01-001.yaml
│   │   │   │   ├── E001-S01-002.yaml
│   │   │   │   └── E001-S01-003.yaml
│   │   │   └── sprint-02/
│   │   │       ├── sprint.yaml
│   │   │       └── E001-S02-001.yaml
│   │   └── epic-004/…
│   ├── archived/
│   │   └── epic-002/…                       ← done; keeps its full tree
│   ├── issues.yaml                          ← flat BL list
│   └── pm-calibration.yaml
│
├── epic-001/                                ← human/agent-authored artifacts
│   ├── sprint-01/
│   │   ├── stories/
│   │   │   ├── E001-S01-001.md
│   │   │   ├── E001-S01-002.md
│   │   │   └── E001-S01-003.md
│   │   ├── closure/
│   │   └── tests/
│   ├── sprint-02/…
│   ├── tests/
│   └── epic-closure/
├── epic-002/…                               ← artifacts persist after close; never move
└── epic-004/…
                                             ← no epic-005/ — nothing authored until work starts
```

### The two trees

`state/` and the top-level `epic-{nnn}/` directories hold two different *kinds* of fact
about the same epic. They are not duplicates of each other.

| | `state/{status}/epic-001/` | `epic-001/` (top level) |
|---|---|---|
| Holds | Status, estimates, actuals, locks | Story markdown, closure reports, QA tests, ADRs |
| Written by | `pm-status.py` only, atomically | Humans and `bmad-dev-story` / review agents |
| Format | YAML metadata | Prose, code, test files |
| Moves? | Yes — `planned/` → `active/` → `archived/` | Never. Created once, stays forever |
| Answers | "What state is it in?" | "What is it?" |

Two asymmetries follow, both correct:

- **A planned epic has state but no artifacts.** Status and estimates exist before any
  story is authored. State comes into existence first.
- **A done epic keeps both, permanently.** Artifacts never move on close, which is why
  state must not collapse on close either — otherwise the mirror holds for active epics and
  breaks for finished ones.

**Every epic with artifacts has state; not every epic with state has artifacts yet.**

### Placement rule

**An epic's directory lives in the folder named for its status.** Every transition is a
`git mv`:

```
planned/epic-005/  →  active/epic-005/  →  archived/epic-005/
```

This replaces the v2 placement table entirely. There is no separate archive-on-close
operation that reshapes data; `archive-epic` becomes a directory move.

### Sharding rationale

Shard where contention is; leave single files where it is not.

- **Per-story files** in `planned/`, `active/`, and `archived/`. Two developers on
  different stories touch different files and git merges without comment. A genuine
  double-claim becomes a conflict on one small file, which is correct — it *is* a real
  conflict and a human should see it.
- **`issues.yaml` stays flat.** Deferred items are genuinely a flat list, written at low
  frequency. It is the last shared-append target in the design; revisit only if it bites.
- **`pm-calibration.yaml` stays a single document.** One set of learned ratios.

Per-sprint sharding was rejected: the common case in a sprint process is several
developers working one sprint concurrently, so per-sprint files would collide in the
normal case rather than the rare one.

### Why the tree moves rather than collapsing

The v2 contract deleted the active file at epic close and appended its content to
`archived.yaml`. Under sharding that would:

- **Destroy per-story git history** at the moment it becomes most valuable, for
  retrospectives and calibration. `git log` on `E001-S01-003.yaml` is that story's
  lifecycle only if the file survives.
- **Break the mirror.** The artifact tree is permanent — `epic-001/sprint-01/stories/*.md`
  persists after close. A state mirror with an expiry date is a weaker invariant.
- **Require a lossy tree-walk-flatten-and-serialize** in `pm-status.py`.

Moving the tree also **eliminates the flock requirement on shared files.** The v2 contract
mandated `--flock` on `planned.yaml` and `archived.yaml` because multiple actors appended
to them. With per-epic directories, epic-start and epic-close touch only that epic's
directory. `issues.yaml` is the sole remaining shared append target.

Sharding `planned/` additionally removes a contention point the v2 design underweighted:
`l3io-pm-plan` elaborates and estimates stories with parallel subagents, all previously
writing into one `planned.yaml`.

**Cost:** roughly 45 files per epic, so ~2,300 after fifty epics. Unremarkable for git.
Archived state is read almost never — calibration reads `pm-calibration.yaml`, not the
archive.

### Per-file schema

Sharding splits a nested tree into files, so each file's contents must be specified.

**Nodes are stored bare — no `epics:` list wrapper.** The wrapper existed only because one
file held many epics. With one node per file it is pure noise, and removing it makes
`set-field` dot-paths address node fields directly.

**The directory structure replaces the `sprints:` and `stories:` lists.** This is the
largest schema consequence of sharding: `epic.yaml` has no `sprints:` key and `sprint.yaml`
has no `stories:` key. Children are discovered by listing the directory.

**Child files carry a back-reference to their parents** (`epic:`, `sprint:`). The path
already encodes this, so it is redundant — deliberately. It makes each file
self-describing when read standalone or matched by grep, and it lets the health check catch
a file sitting in the wrong directory by comparing path against contents.

```yaml
# state/active/epic-001/epic.yaml
_lock:                                    # machine metadata, underscore-prefixed, first key
  session_id: 'l3io-pm-2026-08-16T10:00:00-abc123'
  claimed_at: '2026-08-16T10:00:00'
  ttl_minutes: 30
key: 'E001'
title: 'Epic 001 — Foundation'
goal: 'Stand up the core platform'
status: in-progress
depends_on: []                            # epic keys; read by l3io-pm-plan
estimate:                                 # ranges at epic/sprint level
  man_hours_low: 40
  man_hours_high: 60
  time_hours_low: 8
  time_hours_high: 12
  tokens_k_min: 2000
  tokens_k_max: 3200
  cost_low: 30.00
  cost_high: 48.00
  confidence: medium
actual:                                   # METRIC_FIELDS — all four required
  elapsed_hours: 11.5
  man_hours: 52
  tokens_k: 2840
  cost: 42.60
# no `sprints:` — sprint-NN/ directories are the list
```

```yaml
# state/active/epic-001/sprint-01/sprint.yaml
key: 'S01'
epic: 'E001'                              # back-reference; path must agree
title: 'Sprint 01 — Foundation'
status: in-progress
estimate:
  man_hours_low: 12
  man_hours_high: 18
  time_hours_low: 2.5
  time_hours_high: 4
  tokens_k_min: 600
  tokens_k_max: 950
  cost_low: 9.00
  cost_high: 14.25
  confidence: high
actual:
  elapsed_hours: 3.2
  man_hours: 15
  tokens_k: 812
  cost: 12.18
# no `stories:` — E001-S01-*.yaml files are the list
```

```yaml
# state/active/epic-001/sprint-01/E001-S01-003.yaml
key: 'E001-S01-003'
epic: 'E001'                              # back-references; path must agree
sprint: 'S01'
title: 'Implement token ledger'
status: review
classification: complex
estimate:                                 # single values at story level
  man_hours: 6
  time_hours: 1.5
  tokens_k: 320
  cost: 4.80
  confidence: high
actual:
  elapsed_hours: 1.8
  man_hours: 7
  tokens_k: 355
  cost: 5.32
```

### Ordering becomes structural

`l3io-util-cleanup` currently ships a `sort-status` mode to validate and sort epic and
sprint ordering, because ordering inside a YAML list can drift. With sharding, order is
directory-listing order, and the zero-padded naming (`epic-001`, `sprint-01`,
`E001-S01-003`) means **lexical sort is already correct order**. Ordering can no longer
drift, and `sort-status` loses most of its purpose. It should be reviewed for removal or
reduction to a naming-convention check during implementation.

### Mirror rule and drift detection

```
state/{planned|active|archived}/epic-001/sprint-01/E001-S01-003.yaml
                                epic-001/sprint-01/stories/E001-S01-003.md
                                └──── identical path suffix ────┘
```

Story *content* lives only in the `.md`; story *status* lives only in the `.yaml`. Neither
duplicates the other's data — they are different facts about the same story. The
correspondence already exists today, implicitly, as a key inside a YAML file that must
match a path on disk, with nothing verifying it.

Mirroring makes that correspondence a directory comparison:

```bash
diff <(ls state/active/epic-001/sprint-01/*.yaml | xargs -n1 basename | sed 's/.yaml//') \
     <(ls epic-001/sprint-01/stories/*.md       | xargs -n1 basename | sed 's/.md//')
```

This becomes a new check in the `l3io-util-cleanup` health scan, spanning all three status
folders.

**Rejected alternative — status in story-markdown frontmatter.** Zero duplication and
drift structurally impossible, but it writes machine-managed fields into the file
`bmad-dev-story` agents actively edit — the malformed-YAML-under-parallelism failure
`pm-status.py` was built to end — and epic- and sprint-level state has no markdown host.
It trades a checkable problem for an uncheckable one.

**Rejected alternative — co-locating state into the artifact tree.** Same objection
(machine writes into agent working directories), plus it makes state non-addressable as a
unit. A `state/` root is what allows `git check-ignore`, backup, migration, health-check,
and sync enumeration against one path.

---

## Section 2: Activation and detection

### Detection order

| Order | Found | Layout | Action |
|---|---|---|---|
| 1 | `{implementation_artifacts}/state/` | v3 | Proceed |
| 2 | `{project-root}/_bmad/state/` | v2 | Block → `/l3io-util-cleanup migrate-state` |
| 3 | `{implementation_artifacts}/sprint-status.yaml` | v1 | Block → same command |
| 4 | none | first run | Create lazily |

**Detection counts matches rather than short-circuiting on the first hit.** If more than
one layout is present, block with a distinct error. An interrupted migration leaves both
v2 and v3 populated; silently preferring v3 would fork project state in two — the worst
failure this design can produce.

### Orphan detection

If `implementation_artifacts` is repointed mid-project, the chain finds nothing at the new
root and falls through to case 4, silently starting a blank project over real work.

On apparent-first-run, before creating anything, activation checks whether git tracks any
`*/state/active/epic-*/epic.yaml`. If it does and the path does not match the resolved
root:

```
State found at <tracked-path> but implementation_artifacts resolves to <configured-path>.
Did implementation_artifacts change? Refusing to start a blank project.
```

A bounded `find` covers the untracked case. This check is only possible because state is
now committed; it was unavailable in the v2 design.

### Gitignore verification

Setup runs `git check-ignore -q` on the resolved state root and refuses to proceed
silently if it is ignored, printing the negation rule to add. This is the check whose
absence caused the v2 problem, so it is a setup gate, not documentation.

---

## Section 3: `pm-status.py` — keys instead of paths

Today the step files construct state paths inline, so layout knowledge is spread across
`skills/_shared/steps/`. Since the contract breaks anyway, layout knowledge consolidates
into `pm-status.py`:

```bash
# v2 — the step file knows the layout
pm-status.py set-status --file _bmad/state/active/E001-status.yaml \
  --story E001-S01-003 --status done

# v3 — only pm-status.py knows the layout
pm-status.py set-status --state-root {pm_state_root} \
  --story E001-S01-003 --status done
```

The script resolves `E001-S01-003` → `{root}/active/epic-001/sprint-01/E001-S01-003.yaml`,
searching the three status folders.

**This means the next layout change will not be a breaking change for the skills** — only
`pm-status.py` would move. On the third layout in three releases, that is the lesson to
bank.

### Bindings

| Binding | Resolves to |
|---|---|
| `{pm_state_root}` | `{implementation_artifacts}/state` |
| `{pm_issues_file}` | `{pm_state_root}/issues.yaml` |
| `{pm_calibration_file}` | `{pm_state_root}/pm-calibration.yaml` |

The v2 bindings `{bmad_state_root}`, `{bmad_active_root}`, `{bmad_planned_file}`,
`{bmad_issues_file}`, and `{bmad_archived_file}` are removed. The four per-node path
variables disappear entirely.

### Subcommand changes

- All node-addressing subcommands accept `--state-root` plus `--epic` / `--sprint` /
  `--story` keys, replacing `--file`.
- `archive-epic` becomes a directory move (`planned|active` → `archived`).
- New: `pm-status.py show --sprint E001-S01` renders the aggregate sprint view, replacing
  the ability to read a whole sprint from one file. **Not** a committed generated file —
  that would churn and conflict on its own.
- Roll-ups (sprint and epic progress, estimate/actual aggregation) become computed from
  child files rather than read from one tree.
- `set-lock` / `check-lock` / `clear-lock` continue to operate on `epic.yaml`.
- Flock is no longer required for `planned` or `archived` writes; it remains for
  `issues.yaml`.

---

## Section 4: Migration

`migrate-state` in `l3io-util-cleanup` gains v2→v3 and reuses its existing v1 logic rather
than duplicating it.

**v1→v3.** Run the existing in-memory normalizations — status normalization, `id:`→`key:`
with zero-pad, deferred-story extraction to BL items — to reach a v2-shaped tree, then
explode. One command, two stages, no new normalization code.

**v2→v3.**

1. Explode each `_bmad/state/active/E{nnn}-status.yaml` into `state/active/epic-{nnn}/`.
2. Split `sprint-status-planned.yaml` into per-epic trees under `state/planned/`.
3. Split `sprint-status-archived.yaml` into per-epic trees under `state/archived/`.
4. Move `sprint-status-issues.yaml` → `state/issues.yaml`.
5. Move `_bmad/pm-calibration.yaml` → `state/pm-calibration.yaml`.

**Both paths.**

- Pre-flight blocks if `{implementation_artifacts}/state/` already exists.
- Originals backed up as `.legacy` (cp-if-not-exists — never overwrite an existing backup).
- Prompt for backup relocation to `_bmad/migration-backup/`, matching v1→v2 behavior.
- Post-migration, run the gitignore verification from Section 2 and the drift check from
  Section 1.

History cannot follow through an explode — one file becoming forty is not a rename git can
track — so migration is a clean break in history. Every transition *after* migration is a
`git mv` that history follows.

---

## Section 5: Scope boundaries

### Deferred to a later release

The claim protocol — `claimed_by` / `claimed_at` fields, a `pm-status.py claim`
subcommand, and GitHub-Issue-as-arbiter via `l3io-pm-sync`. The layout admits an ownership
field on a story file with no structural change, so deferring costs nothing structurally.
This is what makes the "both, eventually" team model work: the layout is designed for
distribution now, and the protocol layers in when the team model is concrete.

Also deferred: git refs as a distributed mutex (`refs/pm/locks/<story-key>`), which gives a
genuine distributed compare-and-swap with no extra infrastructure but needs stale-lock
reaping.

### Explicitly rejected

- **Custom YAML merge driver.** Requires every developer to run
  `git config merge.pmstatus.driver`. The failure mode when someone has not is a silent bad
  merge of project state.
- **Append-only event log / JSONL with union merge.** Merges cleanly, but you could no
  longer open a file and read sprint state. Visibility is the point of this release;
  finer sharding solves the merge problem without that trade.

### Not moving

- `_bmad/sync-mapping.yaml` — connection config, deliberately gitignored.
- `_bmad/scripts/pm-status.py` — regenerable runtime tooling, correctly installer-adjacent.

---

## Section 6: Affected files

`pm-status.py` holds no hardcoded state paths today (9 of its 12 subcommands take a
`--file` argument; `self-install` takes `--dest`), but the step files construct paths
inline. Per-skill copies regenerate via
`npm run sync:scripts`.

| File | Refs | Change |
|---|---|---|
| `skills/_shared/status-files.md` | 19 | Primary rewrite — the contract |
| `skills/_shared/pm-status.py` | — | Key-based resolution, `show`, directory-move archive, computed roll-ups |
| `skills/_shared/steps/shared/step-00-activate.md` | 8 | Detection chain, orphan check, new bindings |
| `skills/l3io-util-cleanup/assets/migrate-state.md` | 9 | v2→v3 path |
| `skills/l3io-util-cleanup/SKILL.md` | 3 | Mode docs, health check #10 |
| `skills/l3io-pm-help/SKILL.md` + `assets/module-setup.md` | 3 | State snapshot reads |
| `skills/_shared/steps/**` | — | Replace inline paths with key-based calls |
| `skills/*/assets/module-setup.md` | — | Gitignore verification gate |
| `CLAUDE.md` | 5 | State layout, calibration commit status |
| `docs/superpowers/specs/2026-08-14-*.md` | 12 | **Not rewritten** — superseding note only |
| `docs/superpowers/plans/2026-08-14-*.md` | 8 | **Not rewritten** — historical record |

The v2 spec and plan document what v2 did. Rewriting them would falsify the record; they
receive a note pointing here.

---

## Release

**Version 3.0.0**, commit type `feat!` — breaking change to the state contract.

Per `CLAUDE.md`: `git add` all new untracked files under `skills/` **before** running
`npm run release:major`, since the `postbump` hook uses `git add -u` and stages only
already-tracked files.
