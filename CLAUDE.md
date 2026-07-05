# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Purpose

`bmad-l3io-extensions` is a BMad community module package with four modules: `l3io-pm` (sprint/epic orchestration), `l3io-sec` (red team security agent), `l3io-util` (artifact utilities), and `l3io-arch` (engineering-standards architecture guardrails & review). It ships as installable Claude Code slash commands.

## Structure

```
src/
  l3io-pm/
    l3io-pm-sprint-execute/ ← sprint orchestration (SKILL.md, references/, assets/, scripts/, customize.toml)
    l3io-pm-epic-execute/   ← epic orchestration (SKILL.md, references/, assets/, scripts/, customize.toml)
  l3io-sec/
    l3io-sec-agent-redteam/ ← red team memory agent (SKILL.md, references/, assets/, scripts/, customize.toml)
  l3io-util/
    l3io-util-cleanup/      ← artifact cleanup workflow (SKILL.md, references/, assets/, scripts/, customize.toml)
  l3io-arch/
    l3io-arch-review/       ← architecture standards & review (SKILL.md, references/, assets/, scripts/, module.yaml)
.claude/commands/           ← symlinks → src/<module>/<skill>/SKILL.md
.claude-plugin/             ← marketplace.json (required for installation)
```

Module setup is **embedded** in each operational skill (`assets/module-setup.md` + config `scripts/`); there are no standalone `*-setup/` skill directories. Setup runs on first use or via the module's `configure` action.

| Skill | Purpose |
|-------|---------|
| `src/l3io-pm/l3io-pm-sprint-execute/` | Full sprint lifecycle: story prep → dev → code review → QA → fix loop per story, then closure reviews |
| `src/l3io-pm/l3io-pm-epic-execute/` | Full epic lifecycle: sprint grouping, sprint execution loop, then epic-level closure reviews |
| `src/l3io-sec/l3io-sec-agent-redteam/` | Red team security analysis — five threat lenses (EXT/INS/CHA/ABU/DAR) + AI poisoning cross-cut, live cloud/platform best practices research |
| `src/l3io-util/l3io-util-cleanup/` | Artifact migration & housekeeping utilities — reorganizes flat artifact files into `epic-XX/sprint-YY` folder structure; `migrate-schema` mode upgrades `sprint-status.yaml` to the current field schema; `split-status` mode splits it into the three-file active/backlog/archived layout; `harvest-debt` mode sweeps `bmad-defer:` deferred-shortcut code markers into the consolidated backlog |
| `src/l3io-arch/l3io-arch-review/` | Engineering-standards architecture guardrails & review — three modes (design guardrails / review audit / decision + ADR); universal principles in `references/standards-core.md` plus per-stack overlays (Python, Node.js, .NET, GitHub Actions; Docker/PowerShell/shell stubbed); wires into core `bmad-architect`/`bmad-code-review` via `bmad-customize` (`assets/customize-architect.md`) |

## Commands

Install release tooling first:

```bash
npm install
```

Release commands:

```bash
npm run release:patch    # bump patch, update changelog, create git tag
npm run release:minor    # bump minor, update changelog, create git tag
npm run release:major    # bump major, update changelog, create git tag
```

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

**HARD RULE — estimates & actuals.** Every planning point and every closeout — at **story, sprint, epic, and retrospective** level — must record both an `estimate` and an `actual` for all four metrics: **man-hours, compute (AI wall-clock) hours, tokens, and token cost.** This is enforced, not optional. Token/cost actuals are captured **exactly** under Claude (read from the session transcript `usage` fields) and as `N/A` (never guessed) under other runtimes (e.g. Copilot — capture what's exposed, else `N/A`/`0`). The rule, runtime detection, and the exact capture procedure live in each PM skill's `references/metrics-contract.md`.

**Estimates are a bottom-up roll-up.** Per metric, `story.estimate = base_band(class) × scope_ratio × fix_mult`; `sprint.estimate = Σ story.estimate + calibrated sprint-closure band`; `epic.estimate = Σ sprint.estimate + calibrated epic-closure band`. Sprint/epic estimates are *defined as* the sum of their children + closure, so they reconcile by construction (this replaced parallel formulas that could drift). The fix reserve `F` (default 1.25) is a **cold-start prior only** — it fills the gap before a component has ≥3 calibration samples, then the learned ratios (which already encode fix overhead) supersede it; stacking the two would double-count fixes. Full model in `references/metrics-contract.md`.

Key fields written by the skills (see skill SKILL.md files for the full annotated schema):
- **Stories**: `title`, `classification` (simple/standard/complex) and a full `estimate` block (time_hours, tokens_k, cost, man_hours) written **up front at the sprint pre-start estimate** (read, not recomputed, in the story loop); `completion_evidence` (fix_iterations, tests_passing, files_changed, bugs_fixed) and a full `actual` block (elapsed_hours, man_hours, tokens_k, cost) at `done`
- **Sprints**: `title`, `status`, `estimate` (time_hours_low/high, tokens_k_min/max, cost_low/high, man_hours_low/high) at start; `closed`, `retrospective`, `actual` (elapsed_hours, man_hours, tokens_k, cost) at sign-off
- **Epics**: `title`, `goal`, `status`, `estimate` at start; `closed`, `retrospective`, `actual` (elapsed_hours, man_hours, tokens_k, cost) at sign-off
- **Backlog items** (consolidated top-level `backlog:` list in `sprint-status-backlog.yaml`): `key`, `epic`, `sprint`, `title`, `source`, `severity`, `status`, `description`; `resolved`/`resolution` added when fixed

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

**Adaptive parallelism**: Default sequential. Parallel subagents: default 2, hard cap 4.

**Estimation calibration (decomposed, v2)**: Sprint-execute (and epic-execute at epic close) writes plan-vs-actual data to `{project-root}/_bmad/pm-calibration.yaml` (`version: 2`). It learns **three separable components**, each per metric: `scope` (story sizing, per classification), `closure` (sprint- and epic-level closure overhead — previously a blind spot), and `fix` (observed `avg_fix_factor` per classification). Each component activates once it has **≥3 samples** (exponential-decay weighted, decay 0.8), independently; until then it uses a cold-start prior (ratio 1.0, fix `F`=1.25). At estimate time the components combine as the roll-up above. `token`/`cost` ratios only accumulate from runs with **real** actuals (Claude runs); `N/A` entries are skipped — never guessed. Sampling granularity is set by `calibration_granularity` in each skill's `customize.toml` (`"story"` default — each done story emits a scope/fix sample, converging after ~3 stories — or `"sprint"` for coarser per-sprint aggregation); closure is always sampled per sprint/epic. The scope-vs-fix split of measured actuals uses approach A (back out fix via `fix_factor`); a legacy `version: 1` file is auto-migrated on first write (original kept as `pm-calibration.yaml.v1`). The file is project-scoped and not committed by default. Full spec in `references/metrics-contract.md`.

## Dependencies (consumer repos)

These BMad skills must be present in the target repo:
`bmad-create-story`, `bmad-dev-story`, `bmad-code-review`, `bmad-qa-generate-e2e-tests`, `bmad-retrospective`, `bmad-review-adversarial-general`.

Optional: `bmad-ux-review`.
