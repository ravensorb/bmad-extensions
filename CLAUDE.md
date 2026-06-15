# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Purpose

`bmad-l3io-extensions` is a BMad community module package with three modules: `l3io-pm` (sprint/epic orchestration), `l3io-sec` (red team security agent), and `l3io-util` (artifact utilities). It ships as installable Claude Code slash commands.

## Structure

```
src/
  l3io-pm/
    module.yaml                   ← module metadata (read by BMad installer)
    module-help.csv               ← module-level command catalog
    bmad-l3io-pm-sprint-execute/  ← sprint orchestration (SKILL.md, references/, customize.toml)
    bmad-l3io-pm-epic-execute/    ← epic orchestration (SKILL.md, references/, customize.toml)
  l3io-sec/
    module.yaml
    module-help.csv
    bmad-l3io-sec-agent-redteam/  ← red team memory agent (SKILL.md, references/, assets/, scripts/, customize.toml)
  l3io-util/
    module.yaml
    module-help.csv
    bmad-l3io-util-cleanup/       ← artifact cleanup workflow (SKILL.md, references/, assets/, scripts/, customize.toml)
.claude/commands/                 ← symlinks → src/<module>/<skill>/SKILL.md
.claude-plugin/                   ← marketplace.json (required for installation)
```

| Skill | Purpose |
|-------|---------|
| `src/l3io-pm/bmad-l3io-pm-sprint-execute/` | Full sprint lifecycle: story prep → dev → code review → QA → fix loop per story, then closure reviews |
| `src/l3io-pm/bmad-l3io-pm-epic-execute/` | Full epic lifecycle: sprint grouping, sprint execution loop, then epic-level closure reviews |
| `src/l3io-sec/bmad-l3io-sec-agent-redteam/` | Red team security analysis — five threat lenses (EXT/INS/CHA/ABU/DAR) + AI poisoning cross-cut, live cloud/platform best practices research |
| `src/l3io-util/bmad-l3io-util-cleanup/` | Artifact migration utilities — reorganizes flat artifact files into `epic-XX/sprint-YY` folder structure; `migrate-schema` mode upgrades `sprint-status.yaml` to the current field schema; `split-status` mode splits it into the three-file active/backlog/archived layout |

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
Suggested scopes: `l3io-pm`, `l3io-sec`, `l3io-util` (module changes), plus `infra` and `ci-cd` (tooling/pipeline). Custom scopes are also permitted (`allowCustomScopes: true` in `.cz-config.js`); there is no commit-msg hook enforcing the list, so these are conventions, not hard gates.

## Key Execution Contracts

**Context boundary**: Each phase runs in a fresh subagent. All state passes through disk — never through in-memory hand-off.

**State files** (split layout, in `{implementation_artifacts}/`):

- `sprint-status-active.yaml` — epics with `status: in-progress` (their in-progress + done sprints and all stories).
- `sprint-status-backlog.yaml` — not-yet-started work (whole `backlog` epics + backlog sprints of active epics as shells), plus a consolidated top-level `backlog:` deferred-issue list across all epics.
- `sprint-status-archived.yaml` — epics with `status: done`, moved here wholesale at epic close.

Placement is **epic + sprint** granularity (stories travel with their sprint); archive happens **only at epic close**. The placement rule, node-move operations, and read/auto-fallback procedure live in each PM skill's `references/status-files.md` (the single source of truth). A legacy single `sprint-status.yaml` is auto-split on first PM-skill run, or migrate explicitly with `/bmad-l3io-util-cleanup split-status` (original preserved as `sprint-status.yaml.legacy`).

Story statuses: `backlog → ready-for-dev → in-progress → review → done`. Epic statuses: `backlog → in-progress → done`.

**HARD RULE — estimates & actuals.** Every planning point and every closeout — at **story, sprint, epic, and retrospective** level — must record both an `estimate` and an `actual` for all four metrics: **man-hours, compute (AI wall-clock) hours, tokens, and token cost.** This is enforced, not optional. Token/cost actuals are captured **exactly** under Claude (read from the session transcript `usage` fields) and as `N/A` (never guessed) under other runtimes (e.g. Copilot — capture what's exposed, else `N/A`/`0`). The rule, runtime detection, and the exact capture procedure live in each PM skill's `references/metrics-contract.md`.

Key fields written by the skills (see skill SKILL.md files for the full annotated schema):
- **Stories**: `title`, `classification` (simple/standard/complex) and a full `estimate` block (time_hours, tokens_k, cost, man_hours) at `ready-for-dev`; `completion_evidence` (fix_iterations, tests_passing, files_changed, bugs_fixed) and a full `actual` block (elapsed_hours, man_hours, tokens_k, cost) at `done`
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

**Estimation calibration**: Sprint-execute (and epic-execute at epic close) writes plan-vs-actual ratios to `{project-root}/_bmad/pm-calibration.yaml`. It learns all four metrics — `time_ratio`, `man_hours_ratio`, `token_ratio`, `cost_ratio` (plus per-classification man-hours ratios). From sprint 4 onward, pre-start estimates are adjusted by the exponential-decay weighted average of past ratios. `token_ratio`/`cost_ratio` only accumulate from runs with **real** token/cost actuals (Claude runs); entries whose token/cost actual was `N/A` are skipped — a guessed value is never fed into calibration. The calibration file is project-scoped and not committed to the repo by default.

## Dependencies (consumer repos)

These BMad skills must be present in the target repo:
`bmad-create-story`, `bmad-dev-story`, `bmad-code-review`, `bmad-qa-generate-e2e-tests`, `bmad-retrospective`, `bmad-review-adversarial-general`.

Optional: `bmad-ux-review`.
