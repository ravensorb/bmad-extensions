# bmad-l3io-extensions

[![Commitizen friendly](https://img.shields.io/badge/commitizen-friendly-brightgreen.svg)](http://commitizen.github.io/cz-cli/)
![GitHub issues](https://img.shields.io/github/issues/ravensorb/bmad-extensions)
![GitHub](https://img.shields.io/github/license/ravensorb/bmad-extensions)
![GitHub Repo stars](https://img.shields.io/github/stars/ravensorb/bmad-extensions?style=social)
[![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg)](https://www.contributor-covenant.org/)

## Overview

`bmad-l3io-extensions` adds a LiquidLogicLabs-oriented operating model on top of [BMad](https://docs.bmad-method.org/) for sprint and epic execution, quality closure, and security/resilience review.

It ships as three installable BMad modules. Teams can install all three or only the ones they need.

**Owner:** Shawn Anderson (shawn@eye-catcher.com)

**Support disclaimer:** LiquidLogicLabs does not provide default support, SLA, or managed services for this extension unless explicitly agreed in writing.

## Modules

| Module | Skills | Description |
|--------|--------|-------------|
| **l3io-pm** | `l3io-pm-sprint-execute`, `l3io-pm-epic-execute` | Sprint and epic execution orchestration — full lifecycle from story preparation through closure reviews |
| **l3io-sec** | `l3io-sec-agent-redteam` | Adversarial security analysis through five threat lenses with AI poisoning cross-cut and live cloud/platform best practices research |
| **l3io-util** | `l3io-util-cleanup` | One-time utility to reorganize legacy flat artifacts into the standard epic/sprint folder structure |

## Quick Start

This package is distributed as [BMad community modules](https://docs.bmad-method.org/how-to/install-custom-modules/).

Install or upgrade in the current repo:

```bash
npx bmad-method install \
  --directory . \
  --custom-source https://github.com/ravensorb/bmad-extensions \
  --tools claude-code \
  --yes
```

Interactive path: `npx bmad-method install` -> Community modules -> `bmad-l3io-extensions`.

After install, each module handles its own first-run configuration:

- `/l3io-pm-sprint-execute` or `/l3io-pm-epic-execute` — reads config on activation, uses sensible defaults if absent
- `/l3io-sec-agent-redteam` — first run triggers its own setup automatically
- `/l3io-util-cleanup` — first run registers the module automatically before cleanup

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
| `/l3io-pm-sprint-execute` | Full sprint: story prep → dev → code review → QA → fix loop per story, then retro → clean release → adversarial → red team → UX → arch drift → issue triage at closure. Sprint does not close until all Critical/High issues are resolved |
| `/l3io-pm-epic-execute` | Full epic: sprint execution loop (one `l3io-pm-sprint-execute` subagent per sprint), then epic-level retro → clean release → adversarial → red team → UX → arch drift → functional completeness → issue triage |
| `/l3io-sec-agent-redteam` | Adversarial security review through five threat lenses — external attacker, malicious insider, chaos engineer, abusive legitimate user, and design/architecture red team — with AI poisoning cross-cut and live cloud/platform best practices research |
| `/l3io-util-cleanup` | Reorganizes legacy flat artifact files into `epic-XX/sprint-YY` folders, reconciles references, and verifies state consistency |

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
- sprint status: `{implementation_artifacts}/sprint-status.yaml`

## Dependencies

Required BMad skills (part of the standard BMad bmm module):

`bmad-create-story`, `bmad-dev-story`, `bmad-code-review`, `bmad-qa-generate-e2e-tests`, `bmad-retrospective`, `bmad-review-adversarial-general`

Optional: `bmad-ux-review`

## Repo Layout

```
skills/
  l3io-pm-sprint-execute/    SKILL.md, references/, customize.toml
  l3io-pm-epic-execute/      SKILL.md, references/, customize.toml
  l3io-sec-agent-redteam/    SKILL.md, references/, assets/, scripts/, customize.toml
  l3io-util-cleanup/         SKILL.md, references/, assets/, scripts/, customize.toml
.claude/commands/            symlinks to skills/*/SKILL.md
.claude-plugin/              marketplace.json
```

## Documentation

- [Getting started](docs/getting-started.md)
- [l3io-pm reference](docs/l3io-pm-reference.md)
- [l3io-sec reference](docs/l3io-sec-reference.md)
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
