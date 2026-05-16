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
| `src/l3io-util/bmad-l3io-util-cleanup/` | One-time artifact migration — reorganizes flat artifact files into `epic-XX/sprint-YY` folder structure |

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
Valid scopes: `infra`, `ci-cd`, `custom`.

## Key Execution Contracts

**Context boundary**: Each phase runs in a fresh subagent. All state passes through disk — never through in-memory hand-off.

**State file** (`sprint-status.yaml`): Located at `{implementation_artifacts}/sprint-status.yaml`. Story statuses: `backlog → ready-for-dev → in-progress → review → done`. Epic statuses: `backlog → in-progress → done`.

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

## Dependencies (consumer repos)

These BMad skills must be present in the target repo:
`bmad-create-story`, `bmad-dev-story`, `bmad-code-review`, `bmad-qa-generate-e2e-tests`, `bmad-retrospective`, `bmad-review-adversarial-general`.

Optional: `bmad-ux-review`.
