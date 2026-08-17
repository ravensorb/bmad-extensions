# CLAUDE.md

## Repository Purpose

`bmad-l3io-extensions` is a BMad community module package with four modules: `l3io-pm` (sprint/epic orchestration), `l3io-sec` (red team security agent), `l3io-util` (artifact utilities), and `l3io-arch` (engineering-standards architecture guardrails & review). It ships as installable Claude Code slash commands.

## Module Layout

Module setup is **embedded** in each operational skill (`assets/module-setup.md` + config `scripts/`); there are no standalone `*-setup/` skill directories. Setup runs on first use or via the module's `configure` action.

## Skill Directory

```
skills/
  _shared/                ← canonical shared files (pm-status.py, resolve_config.py, memlog.py,
  |                          status-files.md, steps/) — NEVER edit per-skill copies
  l3io-pm-execute/        SKILL.md, customize.toml, scripts/, assets/, steps/, module.yaml
  l3io-pm-plan/           SKILL.md, customize.toml, scripts/, assets/, steps/, module.yaml
  l3io-pm-help/           SKILL.md, customize.toml, assets/, module.yaml
  l3io-pm-sync/           SKILL.md, customize.toml, scripts/, assets/, module.yaml
  l3io-sec-redteam/       SKILL.md, customize.toml, scripts/, assets/, references/, module.yaml
  l3io-util-doctor/       SKILL.md, customize.toml, scripts/, assets/, module.yaml
  l3io-util-cleanup/      SKILL.md, customize.toml, module.yaml (deprecated forwarder → l3io-util-doctor; no payload)
  l3io-arch-review/       SKILL.md, customize.toml, scripts/, assets/, references/, module.yaml
.claude/commands/         symlinks → ../../skills/<skill>/SKILL.md
.claude-plugin/           marketplace.json (required for installation)
```

| Skill | Purpose |
|-------|---------|
| `l3io-pm-execute` | Full epic + sprint lifecycle: elaboration → dev → code review → QA → fix loop, then sprint and epic closure reviews. Includes first-run module setup |
| `l3io-pm-plan` | Cross-epic planning — validates readiness, elaborates stories, estimates, builds dependency graph, and produces a phased parallel-optimized execution plan |
| `l3io-pm-help` | Reads project state and recommends the exact next l3io-pm action |
| `l3io-pm-sync` | Bidirectional sync between l3io-pm state and GitHub Issues — setup, push, pull, sync, and status modes |
| `l3io-sec-redteam` | Red team security analysis — five threat lenses + AI poisoning cross-cut, live cloud/platform best practices research |
| `l3io-util-doctor` | Project state diagnostics and housekeeping — default is a health check that reports findings and proposes an ordered fix plan; `stats` is the plan-aware progress dashboard; plus `migrate-state`, `split-status`, `harvest-debt`, `sort-status`, `update-ai-rules`, `clean-legacy`. Renamed from `l3io-util-cleanup` in 2.1.0, which survives as a deprecated forwarder (backward compatible — the old command forwards) |
| `l3io-arch-review` | Engineering-standards architecture guardrails and review — three modes: design guardrails (new project), architectural review (audit), decision support + ADR recording |

## Shared Files

Files in `skills/_shared/` are the canonical sources for content shared across PM skills. Do not edit the per-skill copies directly — they are auto-generated.

| Canonical source | Per-skill destination | Skills |
|---|---|---|
| `skills/_shared/pm-status.py` | `scripts/pm-status.py` | pm-execute, pm-plan, pm-sync |
| `skills/_shared/tests/test-pm-status.py` | `scripts/tests/test-pm-status.py` | pm-execute, pm-plan, pm-sync |
| `skills/_shared/status-files.md` | `references/status-files.md` | pm-execute, pm-plan, pm-sync |
| `skills/_shared/steps/**` | `steps/**` | pm-execute, pm-plan, pm-sync |
| `skills/_shared/config-resolution.md` | `references/config-resolution.md` | **all 8 skills** |
| `skills/_shared/module-setup.md` | `assets/module-setup.md` | **all 8 skills** |
| `skills/_shared/write-module-config.py` | `scripts/write-module-config.py` | **all 8 skills** |

**Never bundle a BMad core script.** `resolve_config.py`, `resolve_customization.py`, and
`memlog.py` are installed by BMad core at `{project-root}/_bmad/scripts/` and must be invoked
from there. This package used to vendor byte-identical copies of all three into skill
`scripts/` directories where nothing invoked them — dead payload that duplicated core and
would rot on the next BMad release.

Sync commands:

```bash
npm run sync:scripts    # regenerate payload copies from skills/_shared/ source
npm run check:scripts   # verify payload copies match source (CI also runs this)
npm run check:docs      # verify docs match the code they describe (CI + release gate)
```

`check:docs` asserts three things that have each drifted in this repo's history: every
`l3io-*` skill named in a live doc resolves to a real `skills/` directory, every mirrored
phase table matches the authoritative matrix in `steps/shared/step-01-classify-work.md` §4
cell for cell, and every `<file>.md §N` cross-reference resolves to a section bearing that
number. It deliberately allows a doc to name a removed skill when mapping it to its
replacement or explaining the change — `docs/upgrading.md` must be able to say
`/l3io-pm-epic-execute` → `/l3io-pm-execute`.

The `postbump` hook chains sync automatically, so every release keeps the payloads in sync.

## Commands

The `postbump` hook auto-syncs the new version into `.claude-plugin/marketplace.json` and all `module.yaml` files — do not manually bump those files.

> **Release gate**: a `prerelease` hook refuses to release when payload copies have drifted from `skills/_shared/` (runs `sync-shared-scripts.mjs --check` for every `release:*` alias, not just `release`). `postbump` now stages with `git add -A skills/` so newly added skill files are included rather than silently dropped.

## Skill Authoring Conventions

### customize.toml root key

Every skill has a `customize.toml`. Use the correct root key:

| Skill type | Root key | When to use |
|---|---|---|
| Workflow / utility skill | `[workflow]` | Any skill that is not a persistent memory agent (pm-execute, pm-plan, pm-help, pm-sync, util-doctor, arch-review) |
| Memory agent | `[agent]` | Skills with a named persona, sanctum, and First Breath (l3io-sec-redteam) |

The BMad resolver (`resolve_customization.py`) is called with `--key workflow` or `--key agent` to match. Using the wrong key means team/user overrides are ignored silently.

## Commit Conventions

Conventional Commits are required (enforced via Commitizen). All commits must include a DCO sign-off (`git commit -s`).

Valid types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `revert`, `WIP`.
Suggested scopes: `l3io-pm`, `l3io-sec`, `l3io-util`, `l3io-arch` (module changes), plus `infra` and `ci-cd` (tooling/pipeline). Custom scopes are also permitted (`allowCustomScopes: true` in `.cz-config.js`); there is no commit-msg hook enforcing the list, so these are conventions, not hard gates.

## Key Execution Contracts

**Context boundary**: Each phase runs in a fresh subagent. All state passes through disk — never through in-memory hand-off.

**Config resolution**: every skill resolves config by running BMad core's
`{project-root}/_bmad/scripts/resolve_config.py`, which merges four TOML layers
(`_bmad/config.toml`, `config.user.toml`, `custom/config.toml`, `custom/config.user.toml`)
and prints JSON as `core.*` + `modules.<code>.*`. **There is no `_bmad/config.yaml`** — do
not reintroduce a read of one. Module settings the skills write go to the `custom/` layers
only (the installer regenerates the other two). `implementation_artifacts` and
`planning_artifacts` resolve from `modules.l3io-pm` for *all four* modules — one artifact
tree, one home for its path. An absent module section is normal and never triggers setup;
setup runs only on an explicit `setup`/`configure`/`install`. Whether an optional module is
installed is answered by `_bmad/_config/manifest.yaml`, never by a config section — a module
can be installed and unconfigured. Full contract: `skills/_shared/config-resolution.md`.

**State files** (sharded layout, under `{implementation_artifacts}/state/`):

- `state/{planned,active,archived}/epic-{nnn}/epic.yaml` — one bare node per epic file, no `sprints:` list wrapper; children are discovered by listing the directory.
- `state/{planned,active,archived}/epic-{nnn}/sprint-{nn}/sprint.yaml` — one bare node per sprint file, no `stories:` list wrapper.
- `state/{planned,active,archived}/epic-{nnn}/sprint-{nn}/{story-key}.yaml` — one bare node per story file (`E{nnn}-S{nn}-{nnn}.yaml`).
- `state/issues.yaml` — deferred issues flat list (`BL-E{nnn}-{nnn}`); items removed when resolved.
- `state/events.jsonl` — append-only transition log, one JSON object per status/actuals write, `flock`-guarded. The only source for per-status dwell time (`updated_at` is overwritten by any field write) and the input to `pm-status.py report`. Absent on pre-existing projects, which fall back to `updated_at` with dwell marked approximate.
- `state/pm-calibration.yaml` — learned estimation-calibration ratios (see Estimation calibration below).

**Placement rule**: an epic's directory lives in the folder named for its status (`planned/`, `active/`, or `archived/`), and every status transition is a `git mv` of that whole directory — sprints and stories travel with it, never moved independently.

**The two trees**: `state/{status}/epic-001/` holds status, estimates, actuals, and locks (machine-written, `pm-status.py` only); the top-level `epic-001/` holds artifacts — stories, closure reports, QA tests (human/agent-authored, never moved). They mirror each other with an identical path suffix. Every epic with artifacts has state; not every epic with state has artifacts yet.

The placement rule, node-move operations, read/auto-fallback procedure, and the optional `depends_on` fields used by `l3io-pm-plan` live in each PM skill's `references/status-files.md` (the single source of truth). Legacy `{implementation_artifacts}/sprint-status.yaml` (flat) and legacy `{project-root}/_bmad/state/` (per-epic file) repos are detected automatically; run `/l3io-util-doctor migrate-state` to upgrade (original preserved as `.legacy`).

Story statuses: `backlog → ready-for-dev → in-progress → review → done`. Epic statuses: `backlog → in-progress → done`.

**Status writes go through the shared `pm-status.py`** (run via `uv run`; deps auto-provisioned from its PEP-723 header). It performs every single-node status transition, `actual`-block write, event-log append, and read-back `verify` as one atomic, `ruamel`-round-trip-safe operation (preserves comments + key order) — this replaced free-form YAML edits that were dropped/malformed under load and parallelism. All node operations address state via `--state-root` plus node keys (`--epic`, `--sprint`, `--story`) — never a hand-built path. Skills never construct state paths themselves; `pm-status.py` is the only place that resolves a key to a file location, so a future layout change touches only that script. Directory moves between `planned/`, `active/`, and `archived/` go through `move-epic`/`archive-epic`, still following `references/status-files.md`. Each PM skill activates it in a *Load the Status Helper* step. Subagents do **not** load `status-files.md` or `metrics-contract.md` at activation; `step-00-activate.md` §8 carries an operative digest (keys, subcommand signatures, exit codes, the estimates hard rule) and a routing table to the section of each reference that a given question needs. Those references remain canonical — script > reference > digest. Every status and actuals write also appends to `{implementation_artifacts}/state/events.jsonl` automatically (opt out per call with `--no-events`, stamp a session with `--session-id`); this replaced an optional `--ledger` flag and `progress` subcommand (both removed) that no step file ever passed, so no progress trail was ever actually written. `pm-status.py report` renders that log plus the state tree as a plan-aware progress view (`--format tree|json|md`, `--watch SECS`, `--all`), read-only unless `--out` is given. Under `--runtime claude`, `set-actual`/`verify` **reject** an `N/A` tokens/cost (enforces the estimates-&-actuals HARD RULE at write time).

`pm-status.py` is a **shared runtime utility** authored once in `skills/_shared/` (with its `tests/`); `npm run sync:scripts` (also chained into `postbump`) generates the per-skill `scripts/` payload copies — **never hand-edit those**. At module setup each PM skill runs `pm-status.py self-install --dest {project-root}/_bmad/scripts/pm-status.py` (version-guarded, self-healing on first use), so there is exactly **one runtime copy per project**, referenced by all PM skills as `{project-root}/_bmad/scripts/pm-status.py`. CI runs `npm run check:scripts` to fail on payload drift from the `skills/_shared/` source.

`status-files.md` is also shared from `skills/_shared/` — it is the canonical state-layout contract (placement rules, `depends_on` schema, read/auto-fallback). `npm run sync:scripts` keeps all PM skill `references/status-files.md` copies in sync. Never edit per-skill copies directly.

**HARD RULE — estimates & actuals.** Every planning point and every closeout — at **story, sprint, epic, and retrospective** level — must record both an `estimate` and an `actual` for all four metrics: **man-hours, compute (AI wall-clock) hours, tokens, and token cost.** This is enforced, not optional. Token/cost actuals are captured **exactly** under Claude (read from the session transcript `usage` fields) and as `N/A` (never guessed) under other runtimes (e.g. Copilot — capture what's exposed, else `N/A`/`0`). The rule, runtime detection, and the exact capture procedure live in each PM skill's `references/metrics-contract.md`.

**Estimates are a bottom-up roll-up.** Per metric, `story.estimate = base_band(class) × scope_ratio × fix_mult`; `sprint.estimate = Σ story.estimate + calibrated sprint-closure band`; `epic.estimate = Σ sprint.estimate + calibrated epic-closure band`. Sprint/epic estimates are *defined as* the sum of their children + closure, so they reconcile by construction (this replaced parallel formulas that could drift). The fix reserve `F` (default 1.25) is a **cold-start prior only** — it fills the gap before a component has ≥3 calibration samples, then the learned ratios (which already encode fix overhead) supersede it; stacking the two would double-count fixes. Full model in `references/metrics-contract.md`.

For the fields the skills write (stories, sprints, epics, backlog items), see the full annotated schema in each skill's `SKILL.md`.

**Artifact paths** (zero-padded):

- Stories: `{implementation_artifacts}/epic-XX/sprint-YY/stories/{story-key}.md`
- Closure outputs: `{implementation_artifacts}/epic-XX/sprint-YY/closure/`
- QA tests: `{implementation_artifacts}/epic-XX/sprint-YY/tests/` and `{implementation_artifacts}/epic-XX/tests/`
- Epic closure: `{implementation_artifacts}/epic-XX/epic-closure/`

**Phase status line**: Every subagent must end with:
```
DONE — [brief metrics]
BLOCKED: [one-line reason]
FAILED: [one-line reason]
```

**Quality gates**: Sprint and epic closure require all Critical, High, and Medium severity findings to be resolved (plus undocumented architecture drift and functional AC gaps at epic level). Low severity findings auto-defer to backlog. The fix loop runs autonomously without per-item prompts and only halts after `max_fix_iterations` iterations (10 for CODE/MIXED, 3 for DOCS/CONFIG, per-skill in `customize.toml`) if items remain unresolved. The DOCS/CONFIG value of 3 is currently inert: every phase that contains a fix loop (dev-loop code review, sprint-closure adversarial analysis, epic-closure architectural drift review) is already skipped for DOCS and CONFIG work types, so `max_fix_iterations_non_code` has nothing to bound today — it takes effect only if a DOCS-reachable phase later gains a fix loop.

**Pre-execution gates (shift-left)**: Two gates catch architecture/spec gaps *before* development instead of at closure. (1) **Epic architecture gate** (`epic_arch_gate`, pm-execute) — before any sprint runs, `l3io-arch-review` Mode B reviews the whole epic's design; BLOCKER/MAJOR block execution, each resolved with an ADR and by patching the affected story files with the technical ACs the decision implies; MINOR defers to backlog. (2) **Story technical-AC gate** (`story_technical_ac_gate`, pm-execute story prep) — verifies each story carries technical ACs (interfaces, data model, error/edge handling, observability, security, testability) and enriches when missing, before `ready-for-dev`; `"block"` (default) prevents advancement on an unfilled applicable dimension. Both self-skip when `l3io-arch-review` is not installed; the story gate then falls back to a built-in checklist. `assets/customize-architect.md` also wires the standards into core `bmad-create-story`/`bmad-architect`/`bmad-code-review` in the consuming repo.

**Parallelism**: within a plan phase marked `parallel: true`, `l3io-pm-execute` dispatches epics concurrently up to `max_parallel_subagents` (default 4, per-skill in `customize.toml`). Sprints within an epic are **always sequential**, so calibration from each finished sprint feeds forward into re-estimating the rest. Phase parallelism is decided at plan time: `steps/plan/step-05-dependency-graph.md` runs a topological sort over `depends_on` and marks a phase parallel only when its epics have no dependency on one another. Atomic status writes via `pm-status.py` are what make concurrent epics safe at the state layer. **`parallel_mode`, `parallel_ceiling`, and `safe_batch_size` are not implemented** — they describe an intended adaptive model specced in `docs/superpowers/specs/2026-08-17-adaptive-parallelism-design.md`, not current behavior. Note that concurrent epics currently share one working tree with no source-file independence check; that spec addresses it.

**Estimation calibration (decomposed, v2, mechanized)**: `pm-status.py` runs the calibration loop itself — this is not orchestrator prose. `set-actual` derives and appends a plan-vs-actual sample to `{implementation_artifacts}/state/pm-calibration.yaml` (`version: 2`) automatically after every successful actuals write, at story granularity for `--node story` and closure granularity for `--node sprint|epic`; `--no-calibrate` opts a call out, and a failed derivation only warns on stderr — it never fails the actuals write. `estimate-story` and `estimate-rollup` read the file back and apply whichever ratios are active. It learns **three separable components**, each per metric: `scope` (story sizing, per classification), `closure` (sprint- and epic-level closure overhead — previously a blind spot), and `fix` (cost of the fix loop, per classification, as `clean`/`reworked` man-hour cohorts). `scope` and `closure` each activate once a metric has **≥3 samples** (exponential-decay weighted, decay 0.8); `fix` needs **both** cohorts at ≥3 — one cohort alone cannot form a ratio, so a project where every story needs rework never activates `fix` and correctly stays on the cold-start prior (ratio 1.0 for `scope`/`closure`, fix `F`=1.25). At estimate time the components combine as the roll-up above. `token`/`cost` ratios only accumulate from runs with **real** actuals (Claude runs); `N/A` entries are skipped — never guessed. `granularity` is a field stored in the calibration file itself, not a step-file or `customize.toml` binding — nothing currently varies it, so every project runs `"story"` granularity in practice. The scope-vs-fix split uses `completion_evidence.fix_iterations`, checked only when the estimate carries a `fix_factor` — an estimate recorded before `estimate-story` existed (no `fix_factor`) is `provenance: legacy` regardless of iterations, and contributes no fix-cohort sample: zero iterations gives an exact scope sample and feeds the `clean` fix cohort; a nonzero count, or the field being absent entirely, falls back to backing fix out of the actual (`actual × fix_factor / estimate`), and only a nonzero count also feeds the `reworked` cohort — an absent field backs out the scope ratio but updates no cohort. A legacy `version: 1` file is auto-migrated the first time a sample is appended (original kept as `pm-calibration.yaml.v1`); read-only commands (`calibration show`, `estimate-story`, `estimate-rollup`) never migrate it. The file lives at `{implementation_artifacts}/state/pm-calibration.yaml`, is committed, and is a shared append target across every epic and parallel subagent — every write takes flock. Full spec in `references/metrics-contract.md` §8.

## Dependencies (consumer repos)

These BMad skills must be present in the target repo:
`bmad-create-story`, `bmad-dev-story`, `bmad-code-review`, `bmad-qa-generate-e2e-tests`, `bmad-retrospective`, `bmad-review-adversarial-general`.

Optional: `bmad-ux-review`. (`bmad-testarch-atdd` was previously listed here, but no step file ever invoked it; its gating machinery has been removed.)

Optional intra-package: `l3io-arch-review` (this package's `l3io-arch` module) — enables the epic architecture gate and drives the story technical-AC gate's checklist. Both gates self-skip (the story gate falls back to a built-in checklist) when it is absent.
