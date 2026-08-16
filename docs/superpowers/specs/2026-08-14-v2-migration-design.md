# bmad-extensions v2.0.0 Migration Design

> **Superseded (2026-08-16).** The state-layout sections of this document — `_bmad/state/`,
> per-epic `E{nnn}-status.yaml` files, and the three flat status files — are superseded by
> `docs/superpowers/specs/2026-08-16-v3-state-relocation-design.md`. This document is
> preserved as the historical record of the legacy per-epic migration design; do not
> implement from its state layout sections.

**Date:** 2026-08-14
**Type:** Architectural — major version migration
**Approach:** Hybrid (copy proven architecture, author differences fresh)

---

## Overview

A full architectural overhaul of bmad-extensions from v1.x to v2.0.0. Breaking changes throughout. Existing users must run `/l3io-util-cleanup migrate-state` before using any PM skill after upgrading.

Key changes:
- `src/` → `skills/` directory rename with flat skill layout
- State files move to `_bmad/state/` with per-epic sharding
- Node key schema change: `id:` → `key:` in all state files
- `l3io-pm-sprint-execute` + `l3io-pm-epic-execute` merged into `l3io-pm-execute`
- `l3io-pm-plan-execution` renamed to `l3io-pm-plan`
- Two new skills: `l3io-pm-help`, `l3io-pm-sync` (GitHub Issues only)
- `l3io-sec-agent-redteam` renamed to `l3io-sec-redteam`
- New `_bmad/scripts/`: `resolve_config.py`, `memlog.py`
- `pm-status.py` upgraded to v2.0.0 with six new subcommands and flock-protected writes
- Skills restructured into `steps/` subdirectories with shared step files
- `module-help.csv` expanded to 13-column format

---

## Section 1: Repository Structure & Skill Inventory

### Directory rename

`src/` → `skills/`, including `src/_shared/` → `skills/_shared/`.

The nesting level also flattens: previously `src/<module>/<skill>/`, now `skills/<skill>/`. Module grouping moves to `marketplace.json` metadata only.

`.claude/commands/` symlinks updated from `src/<module>/<skill>/SKILL.md` → `skills/<skill>/SKILL.md`.

### Skill inventory

| Old name | New name | Change |
|---|---|---|
| `l3io-pm-sprint-execute` | *(removed)* | merged into `l3io-pm-execute` |
| `l3io-pm-epic-execute` | *(removed)* | merged into `l3io-pm-execute` |
| `l3io-pm-plan-execution` | `l3io-pm-plan` | renamed + steps architecture |
| *(new)* | `l3io-pm-execute` | merges sprint + epic execution |
| *(new)* | `l3io-pm-help` | new — recommends next action |
| *(new)* | `l3io-pm-sync` | new — GitHub Issues sync |
| `l3io-sec-agent-redteam` | `l3io-sec-redteam` | directory + symlink rename only |
| `l3io-util-cleanup` | `l3io-util-cleanup` | adds `migrate-state` mode; health check updated |
| `l3io-arch-review` | `l3io-arch-review` | unchanged |

### Shared steps layout

`skills/_shared/steps/` is the canonical source for step files shared across PM skills. `sync-shared-scripts.mjs` syncs all step files into consuming skill directories alongside `pm-status.py` and `status-files.md`.

```
skills/_shared/
  pm-status.py
  resolve_config.py       ← new runtime script (synced per-skill)
  memlog.py               ← new runtime script (synced per-skill)
  status-files.md
  tests/
    test-pm-status.py
  steps/
    shared/
      step-00-activate.md     ← runs first in every PM skill
      step-01-classify-work.md
      step-estimate.md
    execute/
      step-02-scope-resolve.md
      step-03-load-plan.md
      step-04-arch-gate.md
      step-05-epic-loop.md
      step-06-epic-closure.md
    sprint/
      step-02-story-prep.md
      step-03-dev-loop.md
      step-04-sprint-closure.md
    plan/
      step-02-readiness-check.md
      step-03-story-elaboration.md
      step-04-load-state.md
      step-05-dependency-graph.md
      step-06-plan-output.md
    closure/
      sprint-closure.md
      epic-closure.md
    sync/
      step-02-detect-platform.md
      step-03-operations.md
      step-04-resolve.md
```

`resolve_customization.py` remains per-skill (not in `_shared/`). It is updated to v2 in each skill's `scripts/` directory individually.

### module-help.csv — 13-column format

All `assets/module-help.csv` files expand from 11 to 13 columns:

```
module,skill,display-name,menu-code,description,action,args,phase,preceded-by,followed-by,required,output-location,outputs
```

New columns are `output-location` (e.g. `implementation_artifacts`, `_bmad/state`) and `outputs` (human description of produced artifacts). All existing skills updated; new skills authored in this format from the start.

---

## Section 2: State Layout (Breaking Change)

### New location

State files move from `{implementation_artifacts}/` to `{project-root}/_bmad/state/`.

### Directory structure

```
{project-root}/_bmad/state/
  active/
    E001-status.yaml    ← one file per in-progress epic
    E002-status.yaml
  sprint-status-planned.yaml    ← backlog epics (was sprint-status-backlog.yaml)
  sprint-status-issues.yaml     ← new: deferred issues flat list
  sprint-status-archived.yaml   ← done epics (append-only)
```

### Node key schema change (breaking)

All state files use `key:` as the primary node identifier instead of `id:`. Epic keys: `E{nnn}` (3-digit zero-padded string). Sprint keys: `S{nn}`. Story keys: `E{nnn}-S{nn}-{nnn}`. Backlog item keys: `BL-E{nnn}-{nnn}`; repo-global items use `BL-E000-{nnn}`.

`pm-status.py` handles both schemas: `key:` first, then `id:` with zero-pad normalization as legacy fallback. All new files are written with `key:`.

### Per-epic sharding

Each `active/E{nnn}-status.yaml` wraps exactly one epic in an `epics: [{...}]` list. This eliminates YAML write contention between parallel subagents operating on different epics.

### Lock mechanism

Each `active/E{nnn}-status.yaml` gains a `_lock` block, always written as the **first key** in the file (ordered YAML rewrite):

```yaml
_lock:
  session_id: "l3io-pm-2026-08-14T10:00:00-abc123"
  claimed_at: "2026-08-14T10:00:00"
  ttl_minutes: 30
```

**Exit code contract for `check-lock`:** exit 5 specifically means "locked by another session within TTL." Orchestrators must branch on exit 5 (not generic non-zero). Exit 0 means free (including own session or stale lock). `epic_lock_ttl_minutes` defaults to 30, configurable in `customize.toml`.

### Legacy auto-detect and blocking

`step-00-activate.md` (shared, runs in every PM skill) checks for `_bmad/state/` on activation:

- **Present** → new layout, continue
- **Absent + `{implementation_artifacts}/sprint-status.yaml` exists** → legacy layout detected, block:
  ```
  ⚠️  Legacy state layout detected. Run /l3io-util-cleanup migrate-state to upgrade
  the state files to the new layout before continuing.
  ```
- **Absent + no legacy file** → first run, create directories and continue

### `migrate-state` mode in `l3io-util-cleanup`

Reads legacy files and applies status normalizations before writing, then splits into the new layout.

**Status normalizations (applied in memory, before any writes):**

| Node | Legacy status | Condition | Normalized to | Destination |
|---|---|---|---|---|
| Epic | `deferred` | no sprint has `status: done` | `backlog` | `sprint-status-planned.yaml` |
| Epic | `deferred` | ≥1 sprint has `status: done` | `in-progress` | `active/E{nnn}-status.yaml` |
| Epic | `superseded` | any | `done` | `sprint-status-archived.yaml` (preserve `superseded_by` field) |
| Sprint | `deferred` | — | `backlog` | within parent epic node |
| Story | `deferred` | — | extracted as BL issue, status `backlog` | `sprint-status-issues.yaml` with `severity: Low`, `source: migrate-state (deferred)` |
| Story | `superseded` | — | `done` | within parent sprint node |

Deferred story key assignment: sequential starting after highest `BL-E{epic_id}-{nnn}` for that epic (or `BL-E{epic_id}-001` if none).

**Write sequence:**
1. Pre-flight: block if `_bmad/state/active/` already exists
2. Normalize all statuses in memory
3. Split `sprint-status-backlog.yaml` → `sprint-status-planned.yaml` + `sprint-status-issues.yaml`; overwrite old backlog file with `epics: []\nbacklog: []`
4. Split `sprint-status.yaml` → per-epic `active/E{nnn}-status.yaml` files; overwrite old file with `epics: []`
5. Copy `sprint-status-archived.yaml` to `_bmad/state/sprint-status-archived.yaml`; append normalized-to-done epics if not already present
6. Backup originals as `.legacy` (cp-if-not-exists — never overwrite existing backup)
7. Prompt user: Move to `_bmad/migration-backup/` (default) / Delete / Keep in place

---

## Section 3: Skills Redesign

### Reference file disposal

PM skills (`l3io-pm-execute`, `l3io-pm-plan`, `l3io-pm-sync`) retain only `references/status-files.md` (synced from `_shared/`). All other reference files (`metrics-contract.md`, `cicd-guidelines.md`, `story-loop.md`, `testing-guidelines.md`, `epic-arch-gate.md`, `sprint-execution-loop.md`, `epic-closure.md`, `sprint-closure.md`) are eliminated — their content is absorbed into the step files.

### `l3io-pm-execute`

**customize.toml knobs:**
```toml
[workflow]
activation_steps_prepend = []
activation_steps_append  = []
persistent_facts         = ["file:{project-root}/**/project-context.md"]
max_parallel_subagents   = 4
epic_lock_ttl_minutes    = 30
```

**Headless mode** (dispatched by the epic loop with a context block containing `headless: true`):
```
steps/shared/step-00-activate.md
steps/sprint/step-02-story-prep.md
steps/sprint/step-03-dev-loop.md
steps/sprint/step-04-sprint-closure.md
```

**Normal mode** (user invokes directly):
```
steps/shared/step-00-activate.md
steps/shared/step-01-classify-work.md
steps/execute/step-02-scope-resolve.md
steps/execute/step-03-load-plan.md
steps/execute/step-04-arch-gate.md
steps/execute/step-05-epic-loop.md
steps/execute/step-06-epic-closure.md
```

**step-01-classify-work behavioral contracts:**
- Classifies all in-scope stories into `{work_type}`: CODE, DOCS, CONFIG, MIXED
- Stories with no ACs → treated as CODE (conservative default)
- `skip_phases` derivation:
  - Story technical-AC gate: skipped for DOCS or CONFIG
  - Arch gate: skipped for DOCS or CONFIG, or if `l3io-arch-review` not installed
  - Adversarial analysis: skipped for DOCS or CONFIG
  - Red team: skipped for DOCS or CONFIG, or if `l3io-sec-redteam` not installed
  - UX review: skipped for CONFIG only (DOCS still gets UX review)
  - ATDD scaffold: skipped for DOCS or CONFIG, or if `bmad-testarch-atdd` not installed
- Installation detection: checks `.claude/commands/{skill-name}.md` presence

**step-02-scope-resolve behavioral contracts:**
- Scope argument patterns:
  - None or `all` → `exec_scope=full`, process all active non-done epics
  - `E{nnn}` → `exec_scope=epic`, single epic
  - `E{nnn}-S{nn}` → `exec_scope=sprint`, single sprint
- Checks active file or planned file for epic existence; BLOCKED if neither found
- Lock pre-check: calls `check-lock`; exit code 5 → BLOCKED with stale-lock guidance

**module-help.csv:**
```
LiquidLogicLabs PM,l3io-pm-execute,Execute,LPE,"Run the l3io-pm plan — full run or scoped to a single epic or sprint. Dispatches sprint subagents with context injection and writes actuals to state.",execute,[E{nnn}|E{nnn}-S{nn}],execution,l3io-pm-plan:plan,l3io-pm-sync:sync,false,implementation_artifacts,"epic-{nnn}/sprint-{nn}/stories/, epic-{nnn}/sprint-{nn}/closure/, epic-{nnn}/epic-closure/"
```

### `l3io-pm-plan`

**customize.toml knobs:**
```toml
[workflow]
activation_steps_prepend = []
activation_steps_append  = []
persistent_facts         = ["file:{project-root}/**/project-context.md"]
auto_elaborate           = false   # true: runs without user confirmation
include_estimates        = true    # false: skip step-estimate entirely
plan_output              = "markdown"  # "console": print summary only, skip writing plan file
```

Step sequence:
```
steps/shared/step-00-activate.md
steps/shared/step-01-classify-work.md
steps/plan/step-02-readiness-check.md
steps/plan/step-03-story-elaboration.md
steps/plan/step-04-load-state.md
steps/plan/step-05-dependency-graph.md
steps/plan/step-06-plan-output.md
```

Outputs `plan-output-meta.yaml` to `{planning_artifacts}/`.

**step-estimate behavioral contracts:**
- Cold-start base bands per classification:
  - simple: man_hours 2–4, time_hours 0.5–1.5, tokens_k 20–50, cost $0.10–$0.35
  - standard: man_hours 4–8, time_hours 1–3, tokens_k 40–100, cost $0.25–$0.70
  - complex: man_hours 8–16, time_hours 2–6, tokens_k 80–200, cost $0.55–$1.40
- Sprint time_hours uses `parallel_factor = 0.6` (wall-clock compressed for parallel execution within sprint)
- Writing to `sprint-status-planned.yaml` requires `--flock` flag (hardcoded, not optional)
- Confidence: `high` if ≥3 calibration samples; `medium` if 1–2; `low` if cold-start

### `l3io-pm-help`

Single-step skill (no `steps/` subdirectory, no `references/`).

**customize.toml:**
```toml
[workflow]
activation_steps_prepend = []
activation_steps_append  = []
persistent_facts         = ["file:{project-root}/**/project-context.md"]
```

Reads `_bmad/state/` snapshot and applies a priority-ordered decision table:

| Condition | Recommendation |
|---|---|
| No state files, no epics | Run story creation first |
| No `plan-output-meta.yaml` | Run `/l3io-pm-plan` |
| Plan readiness = red | Run `/l3io-pm-plan` to resolve gaps |
| Plan readiness = amber | Run `/l3io-pm-plan` or proceed with `/l3io-pm-execute` |
| Stale lock on active epic | Run `pm-status.py clear-lock` for that epic |
| Active epic, no blocked sprint | Run `/l3io-pm-execute {key}` |
| No active epics, plan green | Run `/l3io-pm-execute` |
| All epics done | Run `/l3io-pm-sync` to push closure |
| Deferred epics remain | Surface count, suggest `/l3io-pm-plan` |

### `l3io-pm-sync`

GitHub Issues only. Modes: `status` (default), `setup`, `push`, `pull`, `sync`.

**customize.toml:**
```toml
[workflow]
activation_steps_prepend = []
activation_steps_append  = []
persistent_facts         = ["file:{project-root}/**/project-context.md"]
github_auth_method       = "mcp"   # "pat" requires GITHUB_TOKEN env var
```

Step sequence:
```
steps/shared/step-00-activate.md
steps/sync/step-02-detect-platform.md
steps/sync/step-03-operations.md
steps/sync/step-04-resolve.md
```

**`sync-mapping.yaml`** (connection config, written by `setup`, gitignored):
```yaml
version: 1
platform: github
github:
  owner: ""
  repo: ""
  project_number: 0
  auth_method: mcp    # mcp | pat
field_rules:          # authority: bmad | remote | ask | merge
  title: ask
  description: bmad
  acceptance_criteria: bmad
  status: remote
  assignee: remote
  estimates: bmad
  linked_items: merge
  tags: merge
status_labels:        # GitHub label names for BMad statuses
  backlog: backlog
  ready_for_dev: ready
  in_progress: in-progress
  review: in-review
```

Scripts (authored fresh, GitHub-only — no ADO):
- `detect-platform.py` — confirms GitHub availability, reads `sync-mapping.yaml` for `{sync_platform}` binding
- `sync-state.py` — bidirectional sync engine (`--state-root {project-root}/_bmad/state`)
- `drift-report.py` — compares local state vs GitHub Issues, reports drift

**Conflict resolution:** default is `local-wins` — l3io-pm is the authoritative source. Per-conflict options: `local-wins` (update external), `external-wins` (run `pm-status set-status`), `skip` (log unresolved).

**Sync report:** written to `{project-root}/_bmad/sync-report-{iso_date}.md` — mode, platform, timestamp, items pushed/pulled/synced, conflicts, unresolved, unmapped. `synced_at` updated in `sync-mapping.yaml` for successfully synced items.

**module-help.csv (5 rows):**
```
module,skill,display-name,menu-code,description,action,args,phase,preceded-by,followed-by,required,output-location,outputs
LiquidLogicLabs PM,l3io-pm-sync,Sync Setup,LPS,Configure GitHub Issues sync connection.,setup,,anytime,,l3io-pm-sync:push,false,_bmad/state,sync-mapping.yaml
LiquidLogicLabs PM,l3io-pm-sync,Sync Push,LPU,Push l3io-pm state to GitHub Issues.,push,,anytime,l3io-pm-sync:setup,,false,,sync report
LiquidLogicLabs PM,l3io-pm-sync,Sync Pull,LPL,Pull GitHub Issue status updates into l3io-pm state.,pull,,anytime,l3io-pm-sync:setup,,false,,sync report
LiquidLogicLabs PM,l3io-pm-sync,Sync,LPC,Bidirectional sync (push then pull).,sync,,anytime,l3io-pm-sync:setup,,false,,sync report
LiquidLogicLabs PM,l3io-pm-sync,Sync Status,LPT,Show sync drift report between local state and GitHub Issues.,status,,anytime,,,false,,drift report printed to console
```

### `l3io-sec-redteam`

Directory rename from `l3io-sec-agent-redteam` only. SKILL.md, `customize.toml` (`[agent]` root key), and all references unchanged. `.claude/commands/` symlink updated.

### `l3io-util-cleanup`

**Health check — 9 checks (HC2), fixed execution order (HC6):**

Checks run in priority order:
1. `sprint-status-active.yaml` exists → flag `rename-active` (Critical — must run first)
2. Split layout absent → flag `split-status` (High)
2b. `_bmad/state/active/` absent → flag `migrate-state` (High; runs after split-status)
3. Schema completeness → flag `migrate-schema` (Medium; run before split-status)
4. Flat classifiable files in artifact roots → flag `layout-cleanup` (Medium)
5. Sort order of split files → flag `sort-status` (Low)
6. Unharvested `bmad-defer:` markers → flag `harvest-debt` (Low)
7. Stale state file references in AI instruction files → flag `update-ai-rules` (Low)
8. Misplaced epics / nested backlogs / empty shells → flag `reconcile-status` (High)
9. `*.yaml.legacy` and `*.yaml.v1` files → flag `clean-legacy` (Low)

Fixed execution order: rename-active → migrate-schema → split-status → migrate-state → reconcile-status → layout-cleanup → sort-status → harvest-debt → update-ai-rules → clean-legacy

**reconcile-status placement rule:** `sprint-status.yaml` / active files are home for ALL non-done epics regardless of status (backlog, deferred, pending, not-started). Only `status: done` goes to archived. Backlog file holds only epic shells + flat issues list.

**New `migrate-state` mode:** delegates entirely to `assets/migrate-state.md` (see Section 2 for full spec).

### `l3io-arch-review`

Unchanged. Open-source standards files (dotnet, nodejs, python, docker, github-actions, powershell, shell) remain as-is.

---

## Section 4: `pm-status.py` v2.0.0

`pm-status.py` is upgraded to v2.0.0. Version marker: `# pm-status-version: 2.0.0` in the first line of the file (machine-readable by `self-install`).

### Exit code contract

| Code | Meaning |
|---|---|
| 0 | success / verified |
| 2 | usage error |
| 3 | node not found |
| 4 | verification failure |
| 5 | file locked by another session (`check-lock` only) |

### Write discipline

Round-trip ruamel.yaml load/dump (preserves key order and comments). `width=4096` (never line-wraps scalars). Atomic writes: temp file → fsync → `os.replace`. flock sidecar file: `{path}.lock` (persistent across calls). Non-POSIX (Windows): falls back to plain write with stderr warning.

### All subcommands

**Existing subcommands (updated):**
- `set-status` — adds `--flock` flag
- `set-actual` — `--runtime claude` hard-forbids N/A for `tokens_k` and `cost` (die_usage, not warning); cost stored as SingleQuotedScalarString
- `set-estimate` — added; story aliases: `--tokens-k` → output key `tokens_k`, `--cost` → output key `cost`; range fields for sprints/epics (`--man-hours-low/high`, etc.); `--confidence {low,medium,high}` auto-derived if absent
- `progress` — unchanged
- `verify` — adds `--require-tokens` flag
- `self-install` — reads first 80 lines for version marker; skips if dest version ≥ self; `--force` bypasses guard; makes dest executable (chmod 755)

**New subcommands:**

`set-lock`:
- `--file F`, `--session-id`, `--ttl-minutes` (default 30)
- Rebuilds YAML map with `_lock` as the **first key** (ordered rewrite — not just inserting a field)
- Plain atomic dump (no flock)

`clear-lock`:
- `--file F`
- No-op if file absent or no `_lock` present
- Plain atomic dump

`check-lock`:
- `--file F`, `--session-id` (caller's session)
- File absent or no lock → stdout `FREE`, **exit 0**
- Own session → stdout `FREE (own session)`, **exit 0**
- Locked by another within TTL → stdout `LOCKED by {holder}`, **exit 5**
- TTL expired → stdout `FREE (stale lock ...)`, **exit 0**
- Unreadable timestamp → stdout `FREE (unreadable lock timestamp — treating as stale)`, **exit 0**

`set-field`:
- `--file F`, `--node` (format: `epic.KEY`, `sprint.EPIC.SPRINT`, `story.KEY`), `--field` (dot-path within node), `--value`
- Creates intermediate CommentedMap nodes if dot-path components don't exist
- Plain atomic dump (no flock option)

`append-issue`:
- `--file F` (target: `sprint-status-issues.yaml`), `--key` (format `BL-E{nnn}-{nnn}`), `--epic`, `--sprint` (default `""`), `--title`, `--source`, `--severity` (Low/Medium/High/Critical), `--description` (default `""`)
- Always written with `status: backlog`
- Always flock-protected (hardcoded `flock=True`)
- Creates file with `backlog: []` if absent

`archive-epic`:
- `--source` (active file, e.g. `active/E001-status.yaml`), `--dest` (archived file)
- Reads `epics[0]` from source (per-epic files have exactly one epic)
- Sets epic `status = "done"`, appends to dest file's `epics:` list
- Always flock-protected (hardcoded)
- Creates dest file with `epics: []` if absent

---

## Section 5: New `_bmad/scripts/` Components

### `resolve_config.py`

4-layer TOML merge for central BMad config. Layer priority (highest last):
1. `_bmad/config.toml` (installer-owned team)
2. `_bmad/config.user.toml` (installer-owned user)
3. `_bmad/custom/config.toml` (human-authored team, committed)
4. `_bmad/custom/config.user.toml` (human-authored user, gitignored)

Usage: `python3 {project-root}/_bmad/scripts/resolve_config.py --project-root {project-root} --key modules.l3io-pm`

No third-party dependencies — stdlib `tomllib` only (Python 3.11+).

### `memlog.py`

Append-only memory log with atomic writes. Subcommands: `init`, `append`, `set`.

Used by skills needing persistent, session-resumable working memory (the security agent's sanctum, and future stateful skills).

File shape: `{workspace}/.memlog.md` with YAML frontmatter + flat chronological entry list.

### `resolve_customization.py` (update, per-skill)

Existing per-skill script updated to v2 (improved keyed-merge logic for arrays with mixed `code`/`id` fields). Drop-in replacement in every skill's `scripts/` directory. Not synced from `_shared/` — updated directly in each skill.

### Installation

`resolve_config.py` and `memlog.py` are shipped in `skills/_shared/` and synced by `sync-shared-scripts.mjs` into each PM skill's `scripts/` directory (alongside `pm-status.py`).

`step-00-activate.md` installs runtime scripts to `{project-root}/_bmad/scripts/`:

```bash
mkdir -p {project-root}/_bmad/scripts
# pm-status.py: version-guarded self-install
uv run {skill-root}/scripts/pm-status.py self-install \
  --dest {project-root}/_bmad/scripts/pm-status.py
# resolve_config.py and memlog.py: copy if absent
cp -n {skill-root}/scripts/resolve_config.py {project-root}/_bmad/scripts/resolve_config.py
cp -n {skill-root}/scripts/memlog.py {project-root}/_bmad/scripts/memlog.py
```

`pm-status.py` uses version-guarded self-install (skips if dest version ≥ self). The other two use `cp -n` (no-overwrite) — no version header to compare.

---

## Section 6: Build Pipeline

### `sync-shared-scripts.mjs` rewrite

Updated for `skills/` root and flat skill layout. New sync manifest:

- `sharedScriptFiles` (`resolve_config.py`, `memlog.py`, `pm-status.py`, `test-pm-status.py`) → `l3io-pm-execute`, `l3io-pm-plan`, `l3io-pm-sync`
- `sharedStepFiles` (`steps/shared/`) → all three PM skills
- `planStepFiles` → `l3io-pm-plan`
- `executeStepFiles` → `l3io-pm-execute`
- `syncStepFiles` → `l3io-pm-sync`
- `pmRefFiles` (`status-files.md`) → `l3io-pm-execute`, `l3io-pm-plan`, `l3io-pm-sync`

Old `pmScriptDirs` and `allPmDirs` arrays emptied (old skills removed at cutover).

### `sync-bmad-versions.mjs`

Updated glob pattern finds `module.yaml` under `skills/` (flat, `skills/*/module.yaml`) instead of `src/<module>/<skill>/module.yaml`. Regex replaces `module_version:` line in each matched file.

### `.claude/commands/` symlinks

Removed: `l3io-pm-sprint-execute`, `l3io-pm-epic-execute`, `l3io-pm-plan-execution`, `l3io-sec-agent-redteam`
Added: `l3io-pm-execute`, `l3io-pm-plan`, `l3io-pm-help`, `l3io-pm-sync`, `l3io-sec-redteam`

### `.claude-plugin/marketplace.json`

Skill list updated to new inventory. `postbump` handles version sync automatically.

### Staging reminder

Before `npm run release:major`, explicitly `git add` all new files under `skills/` — the `postbump` hook uses `git add -u` (only already-tracked files).

---

## Section 7: Versioning & Release

**Version: `1.1.1` → `2.0.0`**

Released via `npm run release:major`.

### CHANGELOG entry

Top-level `BREAKING CHANGE` block:
- State layout: files move to `_bmad/state/`, per-epic sharding in `active/`
- Node schema: `id:` → `key:` in all state files
- Skill consolidation: sprint-execute + epic-execute → `l3io-pm-execute`
- Renamed: `l3io-pm-plan-execution` → `l3io-pm-plan`, `l3io-sec-agent-redteam` → `l3io-sec-redteam`
- New skills: `l3io-pm-help`, `l3io-pm-sync` (GitHub Issues)
- `pm-status.py` v2.0.0: six new subcommands, flock-protected writes, exit code 5 for check-lock
- New runtime scripts: `resolve_config.py`, `memlog.py`
- Directory: `src/` → `skills/`, flat skill layout
- `module-help.csv` expanded to 13 columns
- Migration: run `/l3io-util-cleanup migrate-state` before using any PM skill

### Commit convention

All commits signed (`-s` DCO). Breaking structural changes use `feat!` scope. No external project references in any commit message, comment, or changelog entry.

---

## No-External-Reference Rule

Zero references to any external organization in: code, comments, docstrings, commit messages, CHANGELOG, this spec, or any generated file. When copying scripts, strip or generalize any attribution to `bmad-extensions` / `l3io`.
