# CLAUDE.md

## Repository Purpose

`bmad-l3io-extensions` is a BMad community module package with four modules: `l3io-pm` (sprint/epic orchestration), `l3io-sec` (red team security agent), `l3io-util` (artifact utilities), and `l3io-arch` (engineering-standards architecture guardrails & review). It ships as installable Claude Code slash commands.

Architecture decisions are recorded in `docs/adr/` — ADR-0001: `pm-status.py` stays one self-installed file; single-consumer code lives in its skill's own `scripts/`; ADR-0004: agents edit architecture specs, PRD/UX/epic docs are proposal-only, and every edit is confirmed after it lands; ADR-0005: `docs/adr/` is the one ADR home and `adr-reserve` allocates from max(register, files on disk).

## Module Layout

`l3io-util-doctor` routes: `SKILL.md` carries the overview, the keyword table, safety rules
and the state layout, and each of its twenty modes lives in its own `steps/` file loaded
only when its keyword selects it. Add a mode as a file plus a table row — never inline. The
modes were inlined once and `SKILL.md` reached 96,980 B, so every invocation paid for fifteen
procedures it would not run.

Module setup lives at each module's **home**: a dedicated `l3io-pm-setup` skill for `l3io-pm` (the package's only multi-skill module), and the skill itself for the three single-skill modules (`l3io-util`, `l3io-sec`, `l3io-arch`), each of which self-registers. Setup never runs implicitly — only on an explicit `setup`, `configure`, or `install` request. An absent `[modules.<code>]` config section is normal, not a first-run trigger; see `references/config-resolution.md` §5.

## Skill Directory

| Skill | Purpose |
|-------|---------|
| `l3io-pm-execute` | Full epic + sprint lifecycle: elaboration → dev → code review → QA → fix loop, then sprint and epic closure reviews |
| `l3io-pm-plan` | Cross-epic planning — validates readiness, elaborates stories, estimates, builds dependency graph, and produces a phased parallel-optimized execution plan |
| `l3io-pm-help` | Reads project state and recommends the exact next l3io-pm action |
| `l3io-pm-sync` | Bidirectional sync between l3io-pm state and GitHub Issues — setup, push, pull, sync, and status modes |
| `l3io-sec-redteam` | Red team security analysis — five threat lenses + AI poisoning cross-cut, live cloud/platform best practices research |
| `l3io-util-doctor` | Project state diagnostics and housekeeping — default is a health check that reports findings and proposes an ordered fix plan; `stats` is the plan-aware progress dashboard; plus `triage`, `migrate-adrs`, `migrate-state`, `split-status`, `harvest-debt`, `sort-status`, `update-ai-rules`, `clean-legacy`, `redrive`. Renamed from `l3io-util-cleanup` in 2.1.0; the deprecated forwarder was removed in 3.0.0 (see `docs/upgrading.md`) |
| `l3io-arch-review` | Engineering-standards architecture guardrails and review — three modes: design guardrails (new project), architectural review (audit), decision support + ADR recording |
| `l3io-pm-setup` | Records `l3io-pm`'s project-level settings and registers its capabilities for the help system — the module's dedicated setup skill, run only on an explicit `setup`/`configure`/`install` request |

## Shared Files

Files in `skills/_shared/` are the canonical sources for content shared across PM skills. Do not edit the per-skill copies directly — they are auto-generated.

| Canonical source | Per-skill destination | Skills |
|---|---|---|
| `skills/_shared/pm-status.py` | `scripts/pm-status.py` | pm-execute, pm-plan, pm-sync, **l3io-util-doctor** (no test suite — see below) |
| `skills/_shared/spec-align.py` | `scripts/spec-align.py` | pm-execute, **l3io-util-doctor** — run from each skill's own copy, never self-installed; its suite `tests/test-spec-align.py` stays in `_shared/tests/` |
| `skills/_shared/status-files.md` | `references/status-files.md` | pm-execute, pm-plan, pm-sync |
| `skills/_shared/metrics-contract.md` | `references/metrics-contract.md` | pm-execute, pm-plan, pm-sync |
| `skills/_shared/calibration-model.md` | `references/calibration-model.md` | pm-execute, pm-plan, pm-sync |
| `skills/_shared/steps/**` | `steps/**` | pm-execute, pm-plan, pm-sync |
| `skills/_shared/config-resolution.md` | `references/config-resolution.md` | **all 8 skills** |
| `skills/_shared/module-setup.md` | `assets/module-setup.md` | **all 8 skills** |
| `skills/_shared/write-module-config.py` | `scripts/write-module-config.py` | **all 8 skills** |
| `skills/_shared/merge-config.py` | `scripts/merge-config.py` | each module's HOME only: `l3io-pm-setup`, `l3io-util-doctor`, `l3io-sec-redteam`, `l3io-arch-review` |
| `skills/_shared/merge-help-csv.py` | `scripts/merge-help-csv.py` | each module's HOME only: `l3io-pm-setup`, `l3io-util-doctor`, `l3io-sec-redteam`, `l3io-arch-review` |

**Test suites are never shipped as payload.** `skills/_shared/tests/test-pm-status.py`,
`skills/_shared/tests/test-write-module-config.py` and `skills/_shared/tests/test-spec-align.py` stay in `skills/_shared/tests/` only — CI
runs all three straight from there (`.github/workflows/checks.yml`), no consumer skill invokes
any of them, and `sync-shared-scripts.mjs` deliberately excludes them from every sync group. Ten
copies (`test-pm-status.py` into pm-execute/pm-plan/pm-sync, `test-write-module-config.py`
into all 8) shipped as dead payload — ~842 KB across the package — until removed; do not add
either back to a manifest.

**Never bundle a BMad core script.** `resolve_config.py`, `resolve_customization.py`, and
`memlog.py` are installed by BMad core at `{project-root}/_bmad/scripts/` and must be invoked
from there. This package used to vendor byte-identical copies of all three into skill
`scripts/` directories where nothing invoked them — dead payload that duplicated core and
would rot on the next BMad release.

Each skill also carries a **generated** `skills/<skill>/payload-manifest.json` — a SHA-256 per
payload file, keyed relative to that skill's own root so a consumer who installed one skill can
verify that skill alone. **Never hand-edit a manifest, and regenerate it whenever a payload file
changes** — `npm run sync:scripts` does not do it for you. The manifest contract, the sync/verify
commands and the release gates live in `scripts/CLAUDE.md`.

`check:docs` runs twenty checks asserting facts that have each drifted in this repo's history.
They are numbered and described in `scripts/check-docs.mjs`'s own header — read them there rather
than restating them here. Two things that header does not tell you:

- Check 16 guards dependency **names** only: **no `check:docs` check verifies probe *paths***. A
  step file that reverted to probing `.claude/commands/<name>.md` alone would pass every CI gate and
  then silently self-skip its phase on a 6.12 install — the failure mode §1.2 of
  `docs/superpowers/specs/2026-09-12-bmad-v612-migration-design.md` calls worse than a missing
  skill. Probe-path correctness is verified only at **runtime**, against a real install, by
  `/l3io-util-doctor check-deps`; a CI check for it is deferred, not implied.
- Check 1 deliberately allows a doc to name a removed skill when mapping it to its replacement or
  explaining the change — `docs/upgrading.md` must be able to say `/l3io-pm-epic-execute` →
  `/l3io-pm-execute`. Docs are allowed to quote values inline; they are not allowed to quote them
  wrongly.

The `postbump` hook chains sync automatically, so every release keeps the payloads in sync.

## Commands

The `postbump` hook auto-syncs the new version into `.claude-plugin/marketplace.json` and all
`module.yaml` files — do not manually bump those files. The release gates and the rest of the
build tooling are documented in `scripts/CLAUDE.md`.

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
- `state/issues.yaml` — OPEN deferred issues (`BL-E{nnn}-{nnn}`, `status` `backlog` or `scheduled`), each with an optional `kind` (`spec-change` | `spec-proposal`; absent = defect) and `ref`, plus a per-epic `next:` key allocator that never decreases, so a key is never reused. Changed only through `pm-status.py` verbs (`append-issue`, `update-issue`, `promote-issue`, `resolve-issue`, `repair-issue`), all under `issues_lock`.
- `state/issues-resolved.yaml` — resolved items, moved whole with `resolution` (`fixed` | `wontfix` | `duplicate` | `obsolete`), `resolved_at`, `ref`, `note`. A story's `resolves:` list is resolved as `fixed` automatically when `set-status` marks the story `done`. `audit-issues` checks integrity; `/l3io-util-doctor triage` audits and closes what is already fixed. Design: `docs/superpowers/specs/2026-09-10-issue-lifecycle-design.md`, ADR-0002.
- `state/events.jsonl` — append-only transition log, `flock`-guarded, one JSON object per status/actuals write plus a `dispatch_open`/`dispatch_close` pair per subagent dispatch (`pm-status.py dispatch`, unconditional — no `--no-events` opt-out). The only source for per-status dwell time (`updated_at` is overwritten by any field write) and the input to `pm-status.py report`, including its `--stall-minutes` flag and `usage --agent` scoping, both of which read the dispatch records exclusively. Absent on pre-existing projects, which fall back to `updated_at` with dwell marked approximate.
- `state/pm-calibration.yaml` — learned estimation-calibration ratios (see Estimation calibration below).
- `state/adr-register.yaml` — the ADR number allocator (`next:` plus a `reserved:` list). `pm-status.py adr-reserve --epic E --slug S [--count N]` hands out sequential numbers under a flock **before** dispatch, so parallel arch-gate agents cannot both claim ADR-0007. Absent, empty, or an unparseable `next` all resolve to "start at 1" — a project that has never recorded an ADR still works. A malformed `reserved` (not a list) is the one exception: that field is the record of who is in flight, so `adr-reserve` refuses outright (exit 2) rather than discarding it, since silently resetting it to `[]` could let a new reservation collide with one already in flight. The first number handed out is the larger of the register's `next` and the highest ADR number already on disk — in `--adr-dir` (default `<git top-level>/docs/adr`) and in the old per-epic home — plus one.
- `state/spec-sync.lock` — the spec-edit lease (`spec-align.py lease`): owner and expiry as JSON, taken by an epic closure's spec sync so parallel closures sharing one tree never edit or commit a spec at once; ignored by the `*.lock` rule.

**Placement rule**: an epic's directory lives in the folder named for its status (`planned/`, `active/`, or `archived/`), and every status transition is a `git mv` of that whole directory — sprints and stories travel with it, never moved independently.

**The two trees**: `state/{status}/epic-001/` holds status, estimates, actuals, and locks (machine-written, `pm-status.py` only); the top-level `epic-001/` holds artifacts — stories, closure reports, QA tests (human/agent-authored, never moved). They mirror each other with an identical path suffix. Every epic with artifacts has state; not every epic with state has artifacts yet.

The placement rule, node-move operations, read/auto-fallback procedure, and the optional `depends_on` fields used by `l3io-pm-plan` live in each PM skill's `references/status-files.md` (the single source of truth). Legacy `{implementation_artifacts}/sprint-status.yaml` (flat) and legacy `{project-root}/_bmad/state/` (per-epic file) repos are detected automatically; run `/l3io-util-doctor migrate-state` to upgrade (original preserved as `.legacy`).

Story statuses: `backlog → ready-for-dev → in-progress → review → done`. Epic statuses: `backlog → in-progress → done`.

**Status writes go through the shared `pm-status.py`** (run via `uv run`; deps auto-provisioned from its PEP-723 header). It performs every single-node status transition, `actual`-block write, event-log append, and read-back `verify` as one atomic, `ruamel`-round-trip-safe operation (preserves comments + key order) — this replaced free-form YAML edits that were dropped/malformed under load and parallelism. All node operations address state via `--state-root` plus node keys (`--epic`, `--sprint`, `--story`) — never a hand-built path. Skills never construct state paths themselves; `pm-status.py` is the only place that resolves a key to a file location, so a future layout change touches only that script. Directory moves between `planned/`, `active/`, and `archived/` go through `move-epic`/`archive-epic`, still following `references/status-files.md`. Each PM skill activates it in a *Load the Status Helper* step. Subagents do **not** load `status-files.md` or `metrics-contract.md` at activation; `steps/shared/step-00-digest.md` carries an operative digest, loaded on its own by dispatched subagents (keys, subcommand signatures, exit codes, the estimates hard rule) and a routing table to the section of each reference that a given question needs. Those references remain canonical — script > reference > digest. Every status and actuals write also appends to `{implementation_artifacts}/state/events.jsonl` automatically (opt out per call with `--no-events`, stamp a session with `--session-id`); this replaced an optional `--ledger` flag and `progress` subcommand (both removed) that no step file ever passed, so no progress trail was ever actually written. `pm-status.py report` renders that log plus the state tree as a plan-aware progress view (`--format tree|json|md`, `--watch SECS`, `--all`), read-only unless `--out` is given. Under `--runtime claude`, `set-actual`/`verify` **reject** an `N/A` tokens/cost (enforces the estimates-&-actuals HARD RULE at write time). Three subcommands beyond the status/actuals core: **`sync-story-doc`** mirrors a status into the story markdown's frontmatter (called after every `set-status` on a story; a missing or frontmatter-less document warns on stderr and returns 0, because the state transition it follows is already durable); **`add-test-run --command CMD --exit-code N`** appends one executed test command to `completion_evidence.test_runs` and **derives** `completion_evidence.tests_passing` from it — `all(exit_code == 0)` over the **last run of each distinct command**, so the ordinary fix-then-rerun cycle closes green while the failed run stays in the record; `set-field` now **refuses** `completion_evidence.tests_passing` outright (exit 2), since an agent asserting its own tests passed is not falsifiable and once shipped `true` over a suite it never ran. **`adr-reserve`** allocates ADR numbers from `state/adr-register.yaml` (above).

`pm-status.py` is a **shared runtime utility** authored once in `skills/_shared/` (with its `tests/`); `npm run sync:scripts` (also chained into `postbump`) generates the per-skill `scripts/` payload copies — **never hand-edit those**. Every skill that invokes `{pm_status}` needs a copy to self-install/heal it from, not just the PM execution skills: each PM skill runs `pm-status.py self-install --dest {project-root}/_bmad/scripts/pm-status.py` at module setup, and `l3io-util-doctor` runs the same self-install **at activation**, before dispatching to any mode (not gated on `setup`/`configure`) — it is the documented post-upgrade entry point and invokes `{pm_status}` in seven of its mode files, so it cannot assume some other skill already refreshed the installed copy. Self-install is **content-guarded**, self-healing on first use, so there is exactly **one runtime copy per project**, referenced by all these skills as `{project-root}/_bmad/scripts/pm-status.py`. The guard compares a SHA-256 of the bytes, not the version marker: it reinstalls whenever the installed copy differs, and skips only when it is byte-identical. A strictly newer installed copy is still refused as a downgrade — that is the one thing content cannot express. Comparing versions alone was a live defect: the marker is hand-maintained and drifted twice, leaving projects pinned to a copy 920 lines stale that self-install kept reporting as current. **`pm-status.py` shares the package's release line** — its top-of-file marker and `PM_STATUS_VERSION` are written from `package.json` by `sync-bmad-versions.mjs` at `postbump`, alongside `marketplace.json` and every `module.yaml`. Never hand-edit either, and **never move the version backwards**: `self-install` refuses to overwrite a strictly newer installed copy, so a lowered version strands every project already on the higher one. The two lines were merged at 2.4.2, jumping the package up past the script's 2.4.1 for exactly that reason. CI runs `npm run check:scripts` to fail on payload drift from the `skills/_shared/` source, and `npm run check:version` (also chained into `prerelease`) to assert `marker == PM_STATUS_VERSION == package.json version` — an invariant that holds at every commit, not only at release.

`status-files.md` is also shared from `skills/_shared/` — it is the canonical state-layout contract (placement rules, `depends_on` schema, read/auto-fallback). `npm run sync:scripts` keeps all PM skill `references/status-files.md` copies in sync. Never edit per-skill copies directly.

**HARD RULE — estimates & actuals.** Every planning point and every closeout — at **story, sprint, epic, and retrospective** level — must record both an `estimate` and an `actual` for all five metrics, in canonical order: **`elapsed_hours`** (AI wall-clock), **`man_hours`** (counterfactual — what a developer would have taken to do this work by hand; assessed at closure from the delivered diff/tests/scope, never observed), **`hitl_hours`** (human attention actually spent supervising the run — observable), **`tokens_k`** (a mapping of `total` plus the `input`/`output`/`cache_write`/`cache_read` classes), and **`cost`**. This is enforced, not optional. **`cost` is never entered — it is derived once, at capture time, from `tokens_k × the model's per-class rate table` and frozen; `set-actual`/`set-estimate` reject a `--cost*` flag outright (exit 2), and `verify` recomputes and fails on any mismatch.** Token/cost actuals are captured **exactly** under Claude (read from the session transcript `usage` fields, split by class, priced via `--model`) and as `N/A` (never guessed) under other runtimes (e.g. Copilot — capture what's exposed, else `N/A`). `man_hours` and `hitl_hours` are always observable/assessable and must always be real numbers, on every runtime. The rule, runtime detection, and the exact capture procedure live in each PM skill's `references/metrics-contract.md`.

**Estimates are a bottom-up roll-up.** Per metric, `story.estimate = base_band(class) × scope_ratio × fix_mult`. For `tokens_k` the band is **fresh tokens only** (`input + output + cache_write`) and the scope ratio is measured fresh-against-fresh; `cache_read` is projected from the observed mix on top, never banded, because it tracks corpus × agent count rather than story size — folding it in made the ratio compare a cache-inclusive actual to a fresh band, ~1000× apart, and silently poisoned the affected buckets.  `sprint.estimate = Σ story.estimate + calibrated sprint-closure band + calibrated orchestration band`; `epic.estimate = Σ sprint.estimate + calibrated epic-closure band + calibrated orchestration band`. Sprint/epic estimates are *defined as* the sum of their children + closure + orchestration, so they reconcile by construction (this replaced parallel formulas that could drift). `cost` has no band of its own — it is priced from the rolled-up `tokens_k` total (split across classes by the observed or cold-start mix) rather than banded and calibrated independently, so it can no longer drift apart from the token estimate it prices. The fix reserve `F` (default 1.25) is a **cold-start prior only** — it fills the gap before a component has ≥3 calibration samples, then the learned ratios (which already encode fix overhead) supersede it; stacking the two would double-count fixes. **Orchestration is a fourth calibration component** (alongside scope, closure, and fix), keyed by level (sprint/epic), learning a *fraction* of children's actuals rather than a ratio — its band ships unseeded, with nothing to measure a ratio against until `set-actual --block orchestration` records real observations. Full model in `references/metrics-contract.md`.

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

**Quality gates**: Sprint and epic closure require all Critical, High, and Medium severity findings to be resolved (plus undocumented architecture drift and functional AC gaps at epic level). Low severity findings auto-defer to backlog. The fix loop runs autonomously without per-item prompts and only halts after `max_fix_iterations` iterations (**3**, per-skill in `customize.toml`) if items remain unresolved. The cap was 10 until measurement showed each fix iteration is a *turn* multiplier inside an already-long session, and session cost grows with the square of turn count — 10 bought a tail of retries at the steepest part of that curve. `max_fix_iterations_non_code` is also 3 and remains doubly inert: the two values are now equal, and every phase containing a fix loop is already skipped for DOCS and CONFIG work types, so it has nothing to bound either way.

**Pre-execution gates (shift-left)**: Two gates catch architecture/spec gaps *before* development instead of at closure. (1) **Epic architecture gate** (`epic_arch_gate`, pm-execute) — before any sprint runs, `l3io-arch-review` Mode B reviews the whole epic's design **alone**, escalating to the other detected reviewers in parallel only on a BLOCKER or MAJOR — a single MAJOR already blocks, so extra reviewers cannot turn a clean verdict into a blocking one and were buying a corroboration label for two extra full-epic reads on the common path; BLOCKER/MAJOR block execution, each resolved with an ADR and by patching the affected story files with the technical ACs the decision implies; MINOR defers to backlog. (2) **Story technical-AC gate** (`story_technical_ac_gate`, pm-execute story prep) — verifies each story carries technical ACs across **six** dimensions — interfaces/data model, error and edge handling, observability, security, testability, and an **existing-library check** (which library or platform capability covers this, or why custom code is warranted) — and enriches when missing, before `ready-for-dev`. Every dimension is either satisfied or explicitly marked N/A with a reason; an unfilled applicable dimension blocks advancement — this is always enforced, not a configurable option. The step file read "at least one of" until 2026-08-19, which made the gate five times weaker than this description and let a story with interface contracts alone reach `ready-for-dev`. The library dimension is paired with a reused-before-written check in the dev loop's code review, so the rule is enforced at both specification and implementation — it was previously stated in neither. Both self-skip when `l3io-arch-review` is not installed; the story gate then falls back to a built-in checklist. `assets/customize-architect.md` also wires the standards into core `bmad-architecture`/`bmad-code-review` and the legacy `bmad-create-story` in the consuming repo. With `spec_alignment` on (pm-execute `customize.toml`, default `true`), both gates also take the project's specs — by pointer, never whole: `spec-align.py build` indexes every spec under `{planning_artifacts}` (headings, anchors, first sentences, line ranges; no model), the arch gate's reviewer reads only the ranges the stories point to, and every technical-AC dimension must end with a resolving `Spec: <path>#<anchor>` line (or `Spec: none — <reason>`), checked by `spec-align.py check-pointers` before `ready-for-dev`. Sprint and epic drift reviews record a disposition for every BLOCKER/MAJOR finding, and epic closure's spec sync writes accepted architecture departures back as one guarded `docs(spec)` commit each, confirmed or rejected in `/l3io-util-doctor triage`. Design: `docs/superpowers/specs/2026-09-11-spec-alignment-design.md`.

**Parallelism**: within a plan phase marked `parallel: true`, `l3io-pm-execute` dispatches epics concurrently up to `max_parallel_subagents` (default 4, per-skill in `customize.toml`). Sprints within an epic are **always sequential**, so calibration from each finished sprint feeds forward into re-estimating the rest. Phase parallelism is decided at plan time: `steps/plan/step-05-dependency-graph.md` runs a topological sort over `depends_on` and marks a phase parallel only when its epics have no dependency on one another. Atomic status writes via `pm-status.py` are what make concurrent epics safe at the state layer. **`parallel_mode`, `parallel_ceiling`, and `safe_batch_size` are not implemented** — they describe an intended adaptive model specced in `docs/superpowers/specs/2026-08-17-adaptive-parallelism-design.md`, not current behavior. Note that concurrent epics currently share one working tree with no source-file independence check; that spec addresses it.

**Estimation calibration (decomposed, v2, mechanized)**: `pm-status.py` runs the calibration loop itself — this is not orchestrator prose. `set-actual` derives and appends a plan-vs-actual sample to `{implementation_artifacts}/state/pm-calibration.yaml` (`version: 2`) automatically after every successful actuals write, at story granularity for `--node story` and closure granularity for `--node sprint|epic`; `--no-calibrate` opts a call out, and a failed derivation only warns on stderr — it never fails the actuals write. `estimate-story` and `estimate-rollup` read the file back and apply whichever ratios are active. It learns **three separable components**, each per metric: `scope` (story sizing, per classification), `closure` (sprint- and epic-level closure overhead — previously a blind spot), and `fix` (cost of the fix loop, per classification, as `clean`/`reworked` man-hour cohorts). `scope` and `closure` each activate once a metric has **≥3 samples** (exponential-decay weighted, decay 0.8); `fix` needs **both** cohorts at ≥3 — one cohort alone cannot form a ratio, so a project where every story needs rework never activates `fix` and correctly stays on the cold-start prior (ratio 1.0 for `scope`/`closure`, fix `F`=1.25). At estimate time the components combine as the roll-up above. `token`/`cost` ratios only accumulate from runs with **real** actuals (Claude runs); `N/A` entries are skipped — never guessed. `granularity` is a field stored in the calibration file itself, not a step-file or `customize.toml` binding — nothing currently varies it, so every project runs `"story"` granularity in practice. The scope-vs-fix split uses `completion_evidence.fix_iterations`, checked only when the estimate carries a `fix_factor` — an estimate recorded before `estimate-story` existed (no `fix_factor`) is `provenance: legacy` regardless of iterations, and contributes no fix-cohort sample: zero iterations gives an exact scope sample and feeds the `clean` fix cohort; a nonzero count, or the field being absent entirely, falls back to backing fix out of the actual (`actual × fix_factor / estimate`), and only a nonzero count also feeds the `reworked` cohort — an absent field backs out the scope ratio but updates no cohort. A legacy `version: 1` file is auto-migrated the first time a sample is appended (original kept as `pm-calibration.yaml.v1`); read-only commands (`calibration show`, `estimate-story`, `estimate-rollup`) never migrate it. The file lives at `{implementation_artifacts}/state/pm-calibration.yaml`, is committed, and is a shared append target across every epic and parallel subagent — every write takes flock. Full spec in `references/calibration-model.md` (split out of `metrics-contract.md`, which keeps a short §8 summary — `pm-status.py` performs the whole loop, so a normal run never loads the model).

## Dependencies (consumer repos)

Each dependency site resolves between two names in a deliberately chosen order — for some the
6.12 name is tried first, for others the legacy name is tried first because its presence is
positive evidence about the install. No site requires a fixed minimum BMad version.

Required, from the official `bmm` module: `bmad-code-review`, `bmad-qa-generate-e2e-tests`,
`bmad-retrospective`, `bmad-review` (adversarial lens, tried first; the legacy `bmad-review-adversarial-general` is used only when `bmad-review` is absent — a disjoint pair, so the order is immaterial in practice), `bmad-sprint-planning` (readiness gate, invoked with `intent=readiness`) — but here the legacy `bmad-check-implementation-readiness` is preferred **when installed**: its presence is itself evidence that `intent=readiness` may not be understood on that install, so `bmad-sprint-planning` is used only when the legacy `bmad-check-implementation-readiness` is absent.

Story enrichment and implementation: the legacy `bmad-create-story` / `bmad-dev-story` skills
are preferred when installed; when either is absent, this package runs its own in-package
agent in its place, so no shim flag is ever needed.

Optional — UX review: the legacy `bmad-ux-review` is preferred when installed, because it is purpose-built for review; `bmad-ux`'s opt-in Reviewer Gate is used only when the legacy `bmad-ux-review` is absent. UX review phases skip gracefully when neither is present. (`bmad-testarch-atdd` was previously listed here, but no step file ever invoked it; its gating machinery has been removed.)

Optional intra-package: `l3io-arch-review` (this package's `l3io-arch` module) — enables the
epic architecture gate and drives the story technical-AC gate's checklist, and can wire the
standards into core `bmad-architecture` via `bmad-customize`. Both gates self-skip (the story
gate falls back to a built-in checklist) when `l3io-arch-review` is absent.

Run `/l3io-util-doctor check-deps` in a target project to see exactly what resolved there — the
declared inventory lives at `skills/l3io-util-doctor/assets/bmad-dependencies.json`.
