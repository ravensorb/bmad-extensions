# CLAUDE.md

## Repository Purpose

`bmad-l3io-extensions` is a BMad community module package with four modules: `l3io-pm` (sprint/epic orchestration), `l3io-sec` (red team security agent), `l3io-util` (artifact utilities), and `l3io-arch` (engineering-standards architecture guardrails & review). It ships as installable Claude Code slash commands.

## Module Layout

Module setup is **embedded** in each operational skill (`assets/module-setup.md` + config `scripts/`); there are no standalone `*-setup/` skill directories. Setup runs on first use or via the module's `configure` action.

## Commands

The `postbump` hook auto-syncs the new version into `.claude-plugin/marketplace.json` — do not manually bump that file.

## Commit Conventions

Conventional Commits are required (enforced via Commitizen). All commits must include a DCO sign-off (`git commit -s`).

Valid types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `revert`, `WIP`.
Suggested scopes: `l3io-pm`, `l3io-sec`, `l3io-util`, `l3io-arch` (module changes), plus `infra` and `ci-cd` (tooling/pipeline). Custom scopes are also permitted (`allowCustomScopes: true` in `.cz-config.js`); there is no commit-msg hook enforcing the list, so these are conventions, not hard gates.

## Key Execution Contracts

**Context boundary**: Each phase runs in a fresh subagent. All state passes through disk — never through in-memory hand-off.

**State files** (split layout, in `{implementation_artifacts}/`):

- `sprint-status-active.yaml` — epics with `status: in-progress` (their in-progress + done sprints and all stories).
- `sprint-status-backlog.yaml` — not-yet-started work (whole `backlog` epics + backlog sprints of active epics as shells), plus a consolidated top-level `backlog:` deferred-issue list across all epics.
- `sprint-status-archived.yaml` — epics with `status: done`, moved here wholesale at epic close.

Placement is **epic + sprint** granularity (stories travel with their sprint); archive happens **only at epic close**. The placement rule, node-move operations, and read/auto-fallback procedure live in each PM skill's `references/status-files.md` (the single source of truth). A legacy single `sprint-status.yaml` is auto-split on first PM-skill run, or migrate explicitly with `/l3io-util-cleanup split-status` (original preserved as `sprint-status.yaml.legacy`).

Story statuses: `backlog → ready-for-dev → in-progress → review → done`. Epic statuses: `backlog → in-progress → done`.

**Status writes go through the shared `pm-status.py`** (run via `uv run`; deps auto-provisioned from its PEP-723 header). It performs every single-node status transition, `actual`-block write, progress-ledger append, and read-back `verify` as one atomic, `ruamel`-round-trip-safe operation (preserves comments + key order) — this replaced free-form YAML edits that were dropped/malformed under load and parallelism. Multi-node moves between the three files still follow `references/status-files.md`. Each PM skill activates it in a *Load the Status Helper* step and writes a per-run progress trail to `{sprint|epic_root_dir}/progress.log`. Under `--runtime claude`, `set-actual`/`verify` **reject** an `N/A` tokens/cost (enforces the estimates-&-actuals HARD RULE at write time).

`pm-status.py` is a **shared runtime utility** (the `resolve_customization.py` category, not the per-skill `merge-config.py` bootstrap category). It is authored **once** in `src/l3io-pm/_shared/` (with its `tests/`); `npm run sync:scripts` (also chained into `postbump`) generates the per-skill `scripts/` payload copies — **never hand-edit those**. At module setup each PM skill runs `pm-status.py self-install --dest {project-root}/_bmad/scripts/pm-status.py` (version-guarded, self-healing on first use), so there is exactly **one runtime copy per project**, referenced by both skills as `{project-root}/_bmad/scripts/pm-status.py`. CI runs `npm run check:scripts` to fail on payload drift from the `_shared/` source.

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

**Quality gates**: Sprint and epic closure require all Critical, High, and Medium severity findings to be resolved (plus undocumented architecture drift and functional AC gaps at epic level). Low severity findings auto-defer to backlog. The fix loop runs autonomously without per-item prompts and only halts after 10 iterations (per-story or closure-level) if items remain unresolved.

**Pre-execution gates (shift-left)**: Two gates catch architecture/spec gaps *before* development instead of at closure. (1) **Epic architecture gate** (`epic_arch_gate`, epic-execute) — before any sprint runs, `l3io-arch-review` Mode B reviews the whole epic's design; BLOCKER/MAJOR block execution, each resolved with an ADR and by patching the affected story files with the technical ACs the decision implies; MINOR defers to backlog. (2) **Story technical-AC gate** (`story_technical_ac_gate`, sprint-execute story prep) — verifies each story carries technical ACs (interfaces, data model, error/edge handling, observability, security, testability) and enriches when missing, before `ready-for-dev`; `"block"` (default) prevents advancement on an unfilled applicable dimension. Both self-skip when `l3io-arch-review` is not installed; the story gate then falls back to a built-in checklist. `assets/customize-architect.md` also wires the standards into core `bmad-create-story`/`bmad-architect`/`bmad-code-review` in the consuming repo.

**Adaptive parallelism**: `parallel_mode = "auto"` (default) lets the orchestrator size each batch itself — `effective = min(max_parallel_subagents, parallel_ceiling, safe_batch_size)`, where `safe_batch_size` is the count of provably-independent items (no shared files, no cross-dependency, no same-node status contention) and governs in `auto`. Defaults: `max_parallel_subagents = 4`, `parallel_ceiling = 12` (the hard upper bound). `"adaptive"` keeps the same safety checks but never exceeds `max_parallel_subagents`; `"off"` forces sequential. Atomic status writes via `pm-status.py` are what make higher concurrency safe.

**Estimation calibration (decomposed, v2)**: Sprint-execute (and epic-execute at epic close) writes plan-vs-actual data to `{project-root}/_bmad/pm-calibration.yaml` (`version: 2`). It learns **three separable components**, each per metric: `scope` (story sizing, per classification), `closure` (sprint- and epic-level closure overhead — previously a blind spot), and `fix` (observed `avg_fix_factor` per classification). Each component activates once it has **≥3 samples** (exponential-decay weighted, decay 0.8), independently; until then it uses a cold-start prior (ratio 1.0, fix `F`=1.25). At estimate time the components combine as the roll-up above. `token`/`cost` ratios only accumulate from runs with **real** actuals (Claude runs); `N/A` entries are skipped — never guessed. Sampling granularity is set by `calibration_granularity` in each skill's `customize.toml` (`"story"` default — each done story emits a scope/fix sample, converging after ~3 stories — or `"sprint"` for coarser per-sprint aggregation); closure is always sampled per sprint/epic. The scope-vs-fix split of measured actuals uses approach A (back out fix via `fix_factor`); a legacy `version: 1` file is auto-migrated on first write (original kept as `pm-calibration.yaml.v1`). The file is project-scoped and not committed by default. Full spec in `references/metrics-contract.md`.

## Dependencies (consumer repos)

These BMad skills must be present in the target repo:
`bmad-create-story`, `bmad-dev-story`, `bmad-code-review`, `bmad-qa-generate-e2e-tests`, `bmad-retrospective`, `bmad-review-adversarial-general`.

Optional: `bmad-ux-review`, `bmad-testarch-atdd`.

Optional intra-package: `l3io-arch-review` (this package's `l3io-arch` module) — enables the epic architecture gate and drives the story technical-AC gate's checklist. Both gates self-skip (the story gate falls back to a built-in checklist) when it is absent.
