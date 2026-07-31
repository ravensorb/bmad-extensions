# bmad-l3io-extensions

[![Commitizen friendly](https://img.shields.io/badge/commitizen-friendly-brightgreen.svg)](http://commitizen.github.io/cz-cli/)
![GitHub issues](https://img.shields.io/github/issues/ravensorb/bmad-extensions)
![GitHub](https://img.shields.io/github/license/ravensorb/bmad-extensions)
![GitHub Repo stars](https://img.shields.io/github/stars/ravensorb/bmad-extensions?style=social)
[![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg)](https://www.contributor-covenant.org/)

## Overview

`bmad-l3io-extensions` adds a LiquidLogicLabs-oriented operating model on top of [BMad](https://docs.bmad-method.org/) for sprint and epic execution, quality closure, and security/resilience review.

It ships as four installable BMad modules. Teams can install all four or only the ones they need.

**Owner:** Shawn Anderson (shawn@eye-catcher.com)

**Support disclaimer:** LiquidLogicLabs does not provide default support, SLA, or managed services for this extension unless explicitly agreed in writing.

## Modules

| Module | Skills | Description |
|--------|--------|-------------|
| **l3io-pm** | `l3io-pm-plan-execution`, `l3io-pm-sprint-execute`, `l3io-pm-epic-execute` | Sprint and epic execution orchestration — dependency-aware phased planning, full lifecycle from story preparation through closure reviews |
| **l3io-sec** | `l3io-sec-agent-redteam` | Adversarial security analysis through five threat lenses with AI poisoning cross-cut and live cloud/platform best practices research |
| **l3io-util** | `l3io-util-cleanup` | Artifact migration & housekeeping utilities — reorganize legacy flat artifacts into the standard epic/sprint folder structure; migrate the sprint status file to the current field schema; split a legacy single `sprint-status.yaml` into the active/backlog/archived layout; harvest `bmad-defer:` deferred-shortcut code markers into the backlog |
| **l3io-arch** | `l3io-arch-review` | Engineering-standards architecture guardrails and review — applies universal best practices (separation of concerns, reuse, design-by-contract, testability, dependency/GA policy, unified correlated logging, documentation with diagrams) plus per-stack overlays (Python, Node.js, .NET, GitHub Actions) at new-project design time, during an architectural review, or when recording an architecture/technology decision (ADR) |

## Quick Start

This package is distributed as [BMad community modules](https://docs.bmad-method.org/how-to/install-custom-modules/).

The modules work with both **Claude Code** and **GitHub Copilot**. Pick your IDE(s)
with the `--tools` flag (comma-separated codes — no spaces):

| IDE | `--tools` code | Generated agent surface |
|-----|----------------|-------------------------|
| Claude Code | `claude-code` | `.claude/commands/*` slash commands |
| GitHub Copilot | `github-copilot` | `.github/agents/*.agent.md` + `.github/copilot-instructions.md` |

Install (or re-run to upgrade) in the current repo — this example installs both IDEs; drop
whichever code you don't use:

```bash
npx bmad-method install \
  --directory . \
  --custom-source https://github.com/ravensorb/bmad-extensions \
  --tools claude-code,github-copilot \
  --yes
```

For a single IDE, use just that code, e.g. `--tools claude-code` or `--tools github-copilot`.

Interactive path: `npx bmad-method install` -> Community modules -> `bmad-l3io-extensions`
(the installer prompts for which IDEs to target).

After install, each module auto-configures on first use — no explicit setup step required.

### Upgrading

Two ways to pull the latest extension, both safe to re-run — existing config
(`_bmad/config.yaml`) is preserved and skills/agents are refreshed in place:

- **Re-run the install command** above (same `--tools` codes you installed with). Omit
  `--modules` so BMad core modules are left untouched.
- **Quick update** — refreshes every module from its original source (re-fetches this
  Git-hosted extension) and regenerates the IDE agent manifests:

  ```bash
  npx bmad-method install --action quick-update --yes
  ```

  Use this if a prior install is stale — it re-clones the custom source and re-runs
  manifest generation for all configured IDEs (Claude Code and/or GitHub Copilot).

If upgrading from a version before 1.0.20 and you have an existing `sprint-status-active.yaml`, run `/l3io-util-cleanup rename-active` once after upgrading to migrate the file to the new name.

For projects upgrading from an older flat artifact layout, run `/l3io-util-cleanup` once before starting sprint or epic orchestration.

See [docs/getting-started.md](docs/getting-started.md) for a full installation and first-run walkthrough.

## Why This Extension Exists

BMad gives strong primitives, but teams still hit common delivery issues in long-running work:

- orchestration drift across stories, sprints, and epics
- inconsistent quality gates between dev, review, QA, and security
- context bloat that reduces focus and output quality
- weak closure discipline where high-severity findings get deferred implicitly

This extension standardizes those patterns so teams can run a repeatable, auditable workflow.

## Workflows

| Slash command | What it does |
|---------------|--------------|
| `/l3io-pm-plan-execution` | Analyze epic `depends_on` declarations and produce a phased, parallel-optimized execution plan — critical path, wall-clock estimates, and ready-to-run `/l3io-pm-epic-execute` dispatch commands. Pass `--epics` or `--stories` to scope the plan |
| `/l3io-pm-sprint-execute` | Full sprint: story prep → dev → code review → QA → fix loop per story (max 10 iterations), then retro → clean release → adversarial → red team → UX → arch drift → auto-triage + closure fix loop (max 10 iterations) at closure. Sprint does not close until all Critical/High/Medium issues are resolved. Low findings auto-defer to backlog with no prompts |
| `/l3io-pm-epic-execute` | Full epic: sprint execution loop (one `l3io-pm-sprint-execute` subagent per sprint), then epic-level retro → clean release → adversarial → red team → UX → arch drift → functional completeness → issue triage |
| `/l3io-sec-agent-redteam` | Adversarial security review through five threat lenses — external attacker, malicious insider, chaos engineer, abusive legitimate user, and design/architecture red team — with AI poisoning cross-cut and live cloud/platform best practices research |
| `/l3io-util-cleanup` | **Run without arguments** for a project health check — scans for all known issues (stale file naming, unsplit status, schema gaps, flat artifacts, sort order, untracked debt markers, AI instruction references) and proposes the right actions in order with a single confirmation. Or pass a keyword to skip directly to a specific mode: `layout-cleanup` (reorganize flat artifacts), `migrate-schema` (upgrade status file schema), `split-status` (split legacy single file into three), `rename-active` (migrate old sprint-status-active.yaml naming), `harvest-debt` (sweep for `bmad-defer:` markers), `sort-status` (reorder status file nodes), `update-ai-rules` (update AI instruction files), `check` (read-only diagnostic only) |
| `/l3io-arch-review` | Apply engineering standards in one of three modes: **design** (new-project guardrails — boundaries, initial ADRs, docs skeleton), **review** (audit a design/component/diff → severity-graded findings against every principle, with a BLOCKER/MAJOR gate), or **decision** (weigh options against the standards and record an ADR). Auto-detects the stack and loads the matching overlay (Python, Node.js, .NET, GitHub Actions). Wire it into core `bmad-architect` / `bmad-code-review` via `bmad-customize` for automatic application |

## Context Boundary Rule

All workflows are built around one core principle: **each unit of work runs in a fresh subagent with minimal context from previous units.** State passes through disk only — never through in-memory hand-off.

Fresh context means better focus, no context window exhaustion, and restartable runs.

## Adaptive Parallelism

Execution defaults to sequential and only parallelizes when work is independent and safe.

- default parallel subagents: `2`
- hard cap: `4`
- safety fallback: force sequential (`1`) when independence or state safety is unclear
- per-story dependencies respected: a story cannot enter development until all declared dependencies are `done`

## Artifact Conventions

Runtime artifacts are organized with zero-padded epic/sprint folders:

- stories: `{implementation_artifacts}/epic-XX/sprint-YY/stories/{story-key}.md`
- closure outputs: `{implementation_artifacts}/epic-XX/sprint-YY/closure/`
- tests: `{implementation_artifacts}/epic-XX/sprint-YY/tests/` and `{implementation_artifacts}/epic-XX/tests/`
- planning artifacts: `{planning_artifacts}/epic-XX/` and `{planning_artifacts}/epic-XX/sprint-YY/`
- sprint status (three-file split layout): `{implementation_artifacts}/sprint-status.yaml` (in-progress epics), `{implementation_artifacts}/sprint-status-backlog.yaml` (not-yet-started work + consolidated deferred-issue backlog), `{implementation_artifacts}/sprint-status-archived.yaml` (done epics)

## Dependencies

Required BMad skills (part of the standard BMad bmm module):

`bmad-create-story`, `bmad-dev-story`, `bmad-code-review`, `bmad-qa-generate-e2e-tests`, `bmad-retrospective`, `bmad-review-adversarial-general`

Optional: `bmad-ux-review`

## Repo Layout

```
src/
  l3io-pm/
    _shared/                status-files.md (canonical), pm-status.py (canonical) + tests/
    l3io-pm-plan-execution/ SKILL.md, references/, assets/, customize.toml
    l3io-pm-sprint-execute/ SKILL.md, references/, assets/, scripts/, customize.toml
    l3io-pm-epic-execute/   SKILL.md, references/, assets/, scripts/, customize.toml
  l3io-sec/
    l3io-sec-agent-redteam/ SKILL.md, references/, assets/, scripts/, customize.toml
  l3io-util/
    l3io-util-cleanup/      SKILL.md, references/, assets/, scripts/, customize.toml
  l3io-arch/
    l3io-arch-review/       SKILL.md, references/, assets/, scripts/, module.yaml
.claude/commands/           symlinks to src/<module>/<skill>/SKILL.md
.claude-plugin/             marketplace.json
```

Each operational skill embeds its own module setup (`assets/module-setup.md` +
config `scripts/`) — there are no standalone `*-setup` skill directories. Setup
runs automatically on first use, or on demand via the module's `configure` action.

## Documentation

- [Getting started](docs/getting-started.md)
- [l3io-pm reference](docs/l3io-pm-reference.md)
- [l3io-sec reference](docs/l3io-sec-reference.md)
- [l3io-util reference](docs/l3io-util-reference.md)
- [l3io-arch reference](docs/l3io-arch-reference.md)
- [Architecture and execution model](docs/architecture.md)
- [Contributing](CONTRIBUTING.md)

For BMad core guidance, see [BMad docs](https://docs.bmad-method.org/).

## Releases

This repo uses Conventional Commits with `commit-and-tag-version`.

Install release tooling:

```bash
npm install
```

Release commands:

```bash
npm run release:patch    # bump patch, update changelog, create git tag
npm run release:minor    # bump minor, update changelog, create git tag
npm run release:major    # bump major, update changelog, create git tag
npm run changelog        # regenerate changelog only
```

The `postbump` hook auto-syncs the new version into `.claude-plugin/marketplace.json`.

See [CHANGELOG.md](CHANGELOG.md) for release history.

## Contact

Raise an issue on [GitHub](https://github.com/ravensorb/bmad-extensions/issues), or see [SECURITY.md](SECURITY.md).

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) and our [code of conduct](https://www.contributor-covenant.org/). All commits must sign the [Developer Certificate of Origin](https://developercertificate.org/).

## Licensing

This extension is available under the MIT license.
