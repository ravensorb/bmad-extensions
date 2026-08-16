# Status File Layout Contract (sharded state tree)

Communicate all responses in `{communication_language}`.

This file is the single source of truth for **where** epic/sprint/story/backlog state lives
on disk and **how** to read or write it. Load it at activation alongside the metrics
contract and keep its rules in context for every read, every write, and every node move.

State is addressed through `pm-status.py` by **key**, never by hand-built path. No skill or
step file should construct a state path itself — see "Addressing" below.

## 1. File locations

All l3io-pm state lives under `{implementation_artifacts}/state/` — committed to git,
co-located with the artifacts it describes. Nothing state-related lives under
`{project-root}/_bmad/` any more; that tree is installer-owned and gitignored.

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

An epic's directory lives in exactly one of `planned/`, `active/`, or `archived/` at any
time (see "Placement rule" below). Every sprint and story of that epic lives inside the same
epic directory, one file per node.

## 2. The two trees

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

## 3. Key schema

- Epic key: `E{nnn}` (3-digit zero-padded string, e.g. `"E001"`) → directory `epic-{nnn}`
- Sprint key: `S{nn}` (2-digit zero-padded string, e.g. `"S01"`) → directory `sprint-{nn}`
- Story key: `E{nnn}-S{nn}-{nnn}` (globally unique, e.g. `"E001-S02-003"`) → file
  `E{nnn}-S{nn}-{nnn}.yaml` inside that sprint's directory
- Backlog item key: `BL-E{nnn}-{nnn}` (e.g. `"BL-E001-001"`; `BL-E000-{nnn}` for repo-global)

Node fields use `key:` (not `id:`) in every file.

## 4. Per-file schema

Sharding splits a nested tree into files, so each file's contents are specified below.

**Nodes are stored bare — no `epics:` list wrapper.** The wrapper existed only when one file
held many epics. With one node per file it is pure noise, and removing it lets `set-field`
dot-paths address node fields directly.

**The directory structure replaces the `sprints:` and `stories:` lists.** This is the
largest schema consequence of sharding: `epic.yaml` has no `sprints:` key and `sprint.yaml`
has no `stories:` key. Children are discovered by listing the directory — sprint
subdirectories under an epic, story `.yaml` files (excluding `sprint.yaml`) under a sprint.

**Child files carry a back-reference to their parents** (`epic:` on sprint and story files,
`sprint:` also on story files). The path already encodes this, so it is redundant —
deliberately. It makes each file self-describing when read standalone or matched by grep,
and it lets `verify --scope epic` catch a file sitting in the wrong directory by comparing
its path against its contents.

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

`_lock` (epic files only) is machine metadata and is always the first key when present —
see "Ownership lock" below.

## 5. Placement rule

**An epic's directory lives in the folder named for its status.** A node lives in exactly
one place at any time; never duplicate a node. Every transition is a directory move:

```
planned/epic-005/  →  active/epic-005/  →  archived/epic-005/
```

There is no separate archive-on-close operation that reshapes data — `archive-epic` is a
directory move, nothing else. The directory name never changes, only its parent folder, so
`git log --follow` keeps working on every file in the tree across every transition.

Sprints and stories never move independently of their epic — they travel with the epic
directory that contains them.

## 6. Ownership lock

When `l3io-pm-execute` claims an epic, `pm-status.py set-lock` writes a `_lock` block as the
**first key** of that epic's `epic.yaml`:

```yaml
_lock:
  session_id: "claude-session-abc123"
  claimed_at: "2026-08-13T14:30:00Z"
  ttl_minutes: 30
```

Check before claiming:

```bash
uv run {pm_status} check-lock --state-root {pm_state_root} --epic E001 --session-id {session_id}
```

- Exit `0` — free (no lock, held by this same session, or stale past its TTL).
- Exit `5` — locked by another session within its TTL.

**Missing-epic asymmetry, deliberate and tested:** `check-lock` and `clear-lock` treat a
nonexistent epic as absent and exit `0` (`check-lock` prints `FREE`; `clear-lock` is a
no-op) — both are queries/cleanup, so "there's nothing to lock/unlock" is success, not an
error. `set-lock` exits `3` (node not found) on a nonexistent epic, because it must have a
file to write the lock into. Do not "fix" this into uniform behavior — it was deliberately
introduced (and tested) as three different contracts for three different verbs.

## 7. Addressing

**All node operations go through `pm-status.py` with `--state-root` plus node keys. Skills
never construct state paths themselves.** Layout knowledge lives in exactly one place —
`pm-status.py` — so a future layout change only touches that script, not every step file.

```bash
# epic node
uv run {pm_status} set-status --state-root {pm_state_root} --epic E001 --status in-progress

# sprint node (epic + sprint key together)
uv run {pm_status} set-status --state-root {pm_state_root} --epic E001 --sprint S01 --status in-progress

# story node (story key alone is enough — it encodes epic + sprint)
uv run {pm_status} set-status --state-root {pm_state_root} --story E001-S01-003 --status done
```

`pm-status.py` resolves `E001-S01-003` to
`{pm_state_root}/{planned|active|archived}/epic-001/sprint-01/E001-S01-003.yaml`, searching
the three status folders (`active` first, as the hottest path). The same resolution applies
to `--epic`/`--sprint` pairs. No caller ever supplies a raw path for a node.

**One exception: `append-issue`.** `issues.yaml` is a flat file, not a resolvable node — it
has no epic/sprint/story key of its own to resolve from — so `append-issue` is the one
subcommand that still takes `--file`:

```bash
uv run {pm_status} append-issue --file {pm_issues_file} \
  --key BL-E001-004 --epic 001 --title "..." --source "..." --severity Medium
```

`append-issue` always writes under an exclusive flock (it is the last remaining
shared-append target — see "Concurrency" below); this is automatic, not a flag.

Subcommand summary (see `pm-status.py --help` for full flags):

| Subcommand | Addressing |
|---|---|
| `set-status`, `set-actual`, `set-estimate`, `set-field`, `verify` | `--state-root` + (`--story KEY` \| `--epic ID [--sprint ID]`) |
| `show` | `--state-root --epic ID [--sprint ID]` — renders a computed roll-up |
| `set-lock`, `clear-lock`, `check-lock` | `--state-root --epic ID` (epic only — locks apply to epics) |
| `move-epic` | `--state-root --epic ID --to {planned,active,archived}` |
| `archive-epic` | `--state-root --epic ID` — alias for `move-epic --to archived` |
| `append-issue` | `--file` (the one exception; see above) |
| `list-issues` | `--state-root` (reads `{state-root}/issues.yaml`) + optional `--epic`/`--sprint`/`--severity`/`--format` filters |
| `progress` | `--ledger` + `--msg` (unrelated to state-root addressing) |

`show --state-root {pm_state_root} --epic E001 [--sprint S01]` renders a computed roll-up
(status, story counts by status, summed actuals) from the child files on disk. It replaces
the old ability to read a whole sprint or epic out of one file. It is **not** a generated
file that gets committed — it is a read-only report to stdout.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success / verified |
| `2` | Usage error |
| `3` | Node not found |
| `4` | Verification failure (missing/invalid field, or structural mismatch) |
| `5` | Epic locked by another session |

### `verify` — two different checks behind one subcommand

`verify --scope epic` and `verify --scope {story,sprint}` check **different things**; do not
assume they are the same test at a different granularity.

- **`--scope epic`** walks the epic's whole subtree (its `epic.yaml`, every `sprint-{nn}/`
  directory, every file in them) and checks **structural / back-reference integrity**: every
  sprint directory must contain a `sprint.yaml`, and every sprint and story file must carry
  `epic:`/`sprint:` back-references that match the directory it was found in. A **missing**
  back-reference fails exactly like a mismatched one — a self-describing file that does not
  describe itself is not verified, and `migrate-state` writes those back-references for the
  first time, so "absent" is the case this most needs to catch. It does **not** check
  completion status — an in-progress epic legitimately contains stories that are not `done`,
  and this scope must not fail on that. Nor can it detect a story file that was never
  written: the directory listing is the only list of children there is (§4), so there is
  nothing to compare an absence against. This is the check activation runs as a corruption
  gate before trusting an epic's files.
- **`--scope story`** and **`--scope sprint`** check **completion of one node**: `status ==
  done`, all four `actual.*` metric fields present and correctly typed (numeric for
  `elapsed_hours`/`man_hours`; `tokens_k`/`cost` may only be `N/A` under a non-Claude
  runtime), and — for stories — `completion_evidence` present.

Activation depends on this distinction: it always runs `verify --scope epic` (structural),
never `--scope story`/`--scope sprint`, because activation is checking "is this file usable"
not "is this work finished."

## 8. Ordering is structural

Zero-padded names — `epic-{nnn}` (3 digits), `sprint-{nn}` (2 digits), story files
`E{nnn}-S{nn}-{nnn}.yaml` (3-digit sequence) — make lexical directory-listing order the
correct display and processing order. There is no separate ordering field to maintain and no
way for order to drift out of sync with intent, the way it could inside a YAML list.

## 9. Concurrency

Per-epic directories mean epic-scoped writes (status, estimate, actual, lock, move) touch
only that epic's own files — **no flock is needed for any of them.** Two developers working
different stories, different sprints, or different epics never contend for the same file.

`issues.yaml` is the one remaining shared-append target: every deferred item from every epic
appends to the same flat file, so `append-issue` always acquires an exclusive flock
internally before writing. It is the only subcommand where this applies — do not add
`--flock` elsewhere; the other subcommands have no `--flock` need because they no longer
share files.

## 10. Read resolution at activation

Run once at startup, before any state read or write:

| Order | Found | Layout | Action |
|---|---|---|---|
| 1 | `{implementation_artifacts}/state/` | current | Proceed |
| 2 | `{project-root}/_bmad/state/` | legacy (per-epic file) | Block → `/l3io-util-cleanup migrate-state` |
| 3 | `{implementation_artifacts}/sprint-status.yaml` | legacy (flat) | Block → same command |
| 4 | none | first run | Create lazily |

**Detection counts matches rather than stopping at the first hit.** If more than one layout
is present, block with a distinct error rather than silently preferring one — an interrupted
migration can leave two layouts populated at once, and guessing which is authoritative would
fork the project's state.

**Orphan check on apparent first-run.** Before creating anything under case 4, check whether
git tracks any `*/state/active/epic-*/epic.yaml` path that does not match the resolved
`{pm_state_root}`. If it does, halt instead of starting a blank project — this usually means
`implementation_artifacts` was repointed, not that the project has no history. A bounded
`find` covers the untracked case too.

**Gitignore verification.** Setup and activation both run `git check-ignore -q` on the
resolved state root and refuse to proceed silently if it is ignored, printing the negation
rule to add. Committing state is the entire point of this layout, so a state root that is
still gitignored is treated as a hard stop, not a warning.

### Bindings

| Binding | Resolves to |
|---|---|
| `{pm_state_root}` | `{implementation_artifacts}/state` |
| `{pm_issues_file}` | `{pm_state_root}/issues.yaml` |
| `{pm_calibration_file}` | `{pm_state_root}/pm-calibration.yaml` |

There are no other state-path bindings. In particular there is no per-status-folder or
per-node-kind path variable — every path below `{pm_state_root}` is resolved internally by
`pm-status.py` from keys, never bound by a step file.

## 11. Dependency fields

`depends_on` on an epic node (`epic.yaml`): list of epic keys that must be `status: done`
before this epic can start. Present regardless of which status folder the epic currently
sits in (most commonly populated while the epic is under `planned/`). Read by
`l3io-pm-plan` to build the execution graph.

`depends_on` on a story node: list of globally-unique story keys (`E{nnn}-S{nn}-{nnn}`) that
must be `status: done` before this story starts. Lives in that story's own file.

`l3io-pm-plan` validates all referenced keys exist and detects cycles before writing the
plan.
