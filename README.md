# bmad-l3io-extensions

[![Commitizen friendly](https://img.shields.io/badge/commitizen-friendly-brightgreen.svg)](http://commitizen.github.io/cz-cli/)
![GitHub issues](https://img.shields.io/github/issues/ravensorb/bmad-extensions)
![GitHub](https://img.shields.io/github/license/ravensorb/bmad-extensions)
![GitHub Repo stars](https://img.shields.io/github/stars/ravensorb/bmad-extensions?style=social)
[![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg)](https://www.contributor-covenant.org/)

## Overview

`bmad-l3io-extensions` adds a LiquidLogicLabs-oriented operating model on top of [BMad](https://docs.bmad-method.org/) for sprint and epic execution, quality closure, and security/resilience review.

It ships as four installable BMad modules. Teams can install all four or only the ones they need.

### What it adds

BMad supplies the agent primitives — story creation, dev, code review, QA, retrospective. This
package adds the layer above them:

- **Orchestration** — dependency-aware phased planning across epics and sprints, so work runs
  in an order that respects what blocks what, and in parallel only where that is provably safe.
- **Closure discipline** — sprint and epic closure that will not sign off while any Critical,
  High or Medium finding is unresolved. Low findings defer to a tracked backlog instead of
  being quietly dropped.
- **Estimates that learn** — every planning point and every closeout records an estimate *and*
  an actual for five metrics, and later estimates calibrate from that history automatically.
- **Spec alignment** — acceptance criteria carry pointers back to the spec sections they came
  from, and accepted departures are written back to the spec rather than left to diverge.

Short-lived subagents hand off through files on disk. That is a cost decision: a session's
spend grows with the turns it accumulates, so many short agents beat one long one — see
[Cost Model](#cost-model).

### Where to start

| You are a… | Start here |
|---|---|
| **Developer** running the work | [Getting started](docs/getting-started.md), then the [l3io-pm reference](docs/l3io-pm-reference.md) |
| **Project manager** tracking it | [Checking progress](docs/getting-started.md#checking-progress) and the [estimation guide](docs/estimation-guide.md) |
| **Architect** reviewing the model | [Architecture and execution model](docs/architecture.md) |
| **Contributor** to this package | [CONTRIBUTING.md](CONTRIBUTING.md) — `skills/_shared/` holds the only editable copies of shared files |

### Where it runs

Skills are generated for **Claude Code** and **GitHub Copilot** (`--tools`, below). Token and
cost actuals are captured per runtime — exactly under Claude, as available under Codex and
Copilot, and `N/A` rather than a guess elsewhere; see the
[estimation guide](docs/estimation-guide.md). `/l3io-util-doctor update-ai-rules` additionally
maintains instruction files for Claude, Copilot, Gemini, Cursor and the generic `AGENTS.md`
convention.

**Owner:** Shawn Anderson (shawn@eye-catcher.com)

**Support disclaimer:** LiquidLogicLabs does not provide default support, SLA, or managed services for this extension unless explicitly agreed in writing.

## Modules

| Module | Skills | Description |
|--------|--------|-------------|
| **l3io-pm** | `l3io-pm-plan`, `l3io-pm-execute`, `l3io-pm-help`, `l3io-pm-sync` | Sprint and epic execution orchestration — dependency-aware phased planning, full lifecycle from story preparation through closure reviews, plan-aware progress reporting, and GitHub Issues sync |
| **l3io-sec** | `l3io-sec-redteam` | Adversarial security analysis through five threat lenses with AI poisoning cross-cut and live cloud/platform best practices research |
| **l3io-util** | `l3io-util-doctor` | Project state diagnostics & housekeeping — health check that reports findings and proposes an ordered fix plan (default); `stats` renders the plan-aware progress dashboard; migrate a legacy state layout to the sharded state tree; reorganize legacy flat artifacts into the standard epic/sprint folder structure; harvest `bmad-defer:` deferred-shortcut code markers into the backlog. *(Renamed from `l3io-util-cleanup` in 2.1.0 — the old command still works and forwards, but is deprecated.)* |
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
  --modules bmm \
  --tools claude-code,github-copilot \
  --yes
```

For a single IDE, use just that code, e.g. `--tools claude-code` or `--tools github-copilot`.

**`--modules bmm` is not optional.** A `--custom-source` install brings BMad's `core` plus the
custom modules and nothing else, so without it you get the four `l3io` modules and none of the
BMad skills they dispatch to — `bmad-code-review`, `bmad-retrospective`,
`bmad-qa-generate-e2e-tests` and `bmad-sprint-planning` live in the official `bmm` module, not
in `core`. The failure shows up late: planning works, then the first phase
that dispatches one of them has nothing to invoke. Add other official modules to the same flag
if you use them (`--modules bmm,tea`).

BMad ≥6.12.0 installs skills to `.claude/skills/<name>/SKILL.md`; older installs used
`.claude/commands/<name>.md`. No `--shims` flag is needed for either — this package resolves
both layouts and both name generations at every dependency site.

Interactive path: `npx bmad-method install` -> Community modules -> `bmad-l3io-extensions`
(the installer prompts for which IDEs to target).

After install, run `/l3io-util-doctor` once to initialize the runtime and verify your project state. See [Getting started](docs/getting-started.md) for the full guide.

### Upgrading

Run in the project root — no prompts, no questions:

```bash
npx bmad-method install --directory . --action quick-update --yes
```

Reads the stored install config (tools, custom source) so nothing needs to be re-specified. Omitting `--modules` leaves core BMad skills untouched. Your `_bmad/custom/` config overrides are preserved and skills are refreshed in place.

**The installer refreshes skills; it does not migrate your data.** After upgrading, run
`/l3io-util-doctor` once before any sprint or epic run — it inspects the project and
applies every migration you need, in order, behind one confirmation.

See **[Upgrading](docs/upgrading.md)** for version-by-version notes, the full migration
sequence, backups and rollback, and current deprecations.

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
| `/l3io-pm-plan` | Validate readiness, elaborate stories, estimate, analyze epic `depends_on` declarations, and produce a phased parallel-optimized execution plan — critical path and wall-clock estimates, written as a dated snapshot plus the `plan-output-meta.yaml` pointer. `/l3io-pm-plan estimate [E{nnn}\|E{nnn}-S{nn}]` re-estimates only |
| `/l3io-pm-execute` | Run the plan — full, single epic (`E001`), or single sprint (`E001-S01`). Dispatches **one agent to prep the sprint, one per story, one to close it** — short sessions, because cost grows with the turns a session accumulates. Per story: dev → code review → fix loop (capped at `max_fix_iterations`, default 3). At sprint and epic closure: retro → clean-release + adversarial (one call) → red team → UX → arch drift → auto-triage + closure fix loop (same cap). Nothing closes until all Critical/High/Medium findings are resolved; Low findings auto-defer to the backlog with no prompts. Renders a plan-aware progress tree at each phase boundary |
| `/l3io-pm-help` | Read project state and recommend the exact next action. `/l3io-pm-help progress` renders the plan-aware progress tree — which phase, epic, sprint, and stories are in flight, with per-status dwell times and stuck-item flags |
| `/l3io-pm-sync` | Bidirectional sync between l3io-pm state and GitHub Issues — `setup`, `push`, `pull`, `sync`, `status` (default) |
| `/l3io-sec-redteam` | Adversarial security review through five threat lenses — external attacker, malicious insider, chaos engineer, abusive legitimate user, and design/architecture red team — with AI poisoning cross-cut and live cloud/platform best practices research |
| `/l3io-util-doctor` | **Run without arguments** for a project health check — scans for all known issues (stale file naming, unsplit status, schema gaps, flat artifacts, sort order, untracked debt markers, AI instruction references, ADRs left in the old per-epic home, story spec pointers, and spec-index freshness) and proposes the right actions in order with a single confirmation. Or pass a keyword to skip directly to a specific mode: `layout-cleanup` (reorganize flat artifacts), `migrate-schema` (upgrade status file schema), `split-status` (split legacy single file into three), `rename-active` (migrate old sprint-status-active.yaml naming), `harvest-debt` (sweep for `bmad-defer:` markers), `sort-status` (reorder status file nodes), `update-ai-rules` (update AI instruction files), `migrate-adrs` (move ADRs from the old per-epic home to `docs/adr/`), `triage` (audit the issues backlog and close what is already fixed), `check` (read-only diagnostic only), `stats` (plan-aware progress dashboard), `clean-legacy` (remove migration backups) |
| `/l3io-arch-review` | Apply engineering standards in one of three modes: **design** (new-project guardrails — boundaries, initial ADRs, docs skeleton), **review** (audit a design/component/diff → severity-graded findings against every principle, with a BLOCKER/MAJOR gate), or **decision** (weigh options against the standards and record an ADR). Auto-detects the stack and loads the matching overlay (Python, Node.js, .NET, GitHub Actions). Wire it into core `bmad-architecture` / `bmad-code-review` via `bmad-customize` for automatic application |

## Context Boundary Rule

All workflows are built around one core principle: **each unit of work runs in a fresh subagent with minimal context from previous units.** State passes through disk only — never through in-memory hand-off.

Fresh context means better focus, no context window exhaustion, and restartable runs.

## Adaptive Parallelism

Execution defaults to sequential and only parallelizes when work is independent and safe.

- `max_parallel_subagents = 4` (default, per-skill in `customize.toml`) — bounds how many epics dispatch concurrently within a plan phase marked parallel; sprints within an epic are always sequential
- safety fallback: force sequential when independence or state safety is unclear
- per-story dependencies respected: a story cannot enter development until all declared dependencies are `done`

## Cost Model

Cost tracks **turns**, not tokens-per-turn and not repository size. Every turn re-reads the
accumulated prefix, so a session's spend grows with roughly the square of its turn count. The
repository-size hypothesis was tested directly and failed — deleting 4,415 lines moved the
token composition not at all, and `cache_read` stayed 75–94% of every story either way.

Execution is shaped around that:

- **One agent per story**, plus one to prep the sprint and one to close it — short sessions
  beat long ones, and cost nothing in continuity because every hand-off is a file on disk
- **Never poll**: a spawned agent arms one background wait and stops. A one-line "still
  running?" costs what the whole conversation costs
- **Reviewers get a diff and named spec sections**, never the repository
- **Fix loop capped at 3** — each iteration is a turn multiplier
- **Actuals are read by `pm-status.py usage`**, which resolves its own transcript and refuses
  to sum a file it cannot confirm is yours

See [architecture.md](docs/architecture.md#cost-model) for where each rule is enforced and the
measurement behind it.

## Artifact Conventions

Runtime artifacts are organized with zero-padded epic/sprint folders:

- stories: `{implementation_artifacts}/epic-XX/sprint-YY/stories/{story-key}.md`
- closure outputs: `{implementation_artifacts}/epic-XX/sprint-YY/closure/`
- tests: `{implementation_artifacts}/epic-XX/sprint-YY/tests/` and `{implementation_artifacts}/epic-XX/tests/`
- planning artifacts: `{planning_artifacts}/epic-XX/` and `{planning_artifacts}/epic-XX/sprint-YY/`
- state (sharded layout): `{implementation_artifacts}/state/{planned,active,archived}/epic-XX/` — one directory per epic, living in the folder named for its status, with one bare node per file (`epic.yaml`, `sprint-YY/sprint.yaml`, `sprint-YY/{story-key}.yaml`). Every status change is a `git mv` of the whole directory, so sprints and stories travel with their epic
- deferred issues: `{implementation_artifacts}/state/issues.yaml` (open) and `issues-resolved.yaml` (closed, moved whole with a resolution)

A flat `{implementation_artifacts}/sprint-status.yaml` — optionally split into
`sprint-status{,-backlog,-archived}.yaml` — is the **legacy** layout. The PM skills do not read
it; `/l3io-util-doctor migrate-state` migrates it to the sharded tree and preserves the
original as `.legacy`.

## Dependencies

Each BMad dependency site resolves between two names in a deliberately chosen order — for some
the 6.12 name is tried first, for others the legacy name is tried first because its presence is
positive evidence about the install. No site requires a fixed minimum BMad version.

Required, all from the official `bmm` module: `bmad-code-review`, `bmad-qa-generate-e2e-tests`,
`bmad-retrospective`, `bmad-review` (adversarial lens, tried first; the legacy `bmad-review-adversarial-general` is used only when `bmad-review` is absent — a disjoint pair, so the order is immaterial in practice), `bmad-sprint-planning` (readiness gate, `intent=readiness`) — but here the legacy `bmad-check-implementation-readiness` is preferred **when installed**, since its presence is itself evidence that `intent=readiness` may not be understood on that install; `bmad-sprint-planning` is used only when the legacy `bmad-check-implementation-readiness` is absent.

Story enrichment and implementation prefer the legacy `bmad-create-story` / `bmad-dev-story`
skills when installed; when either is absent this package runs its own in-package agent in its
place instead, so no shim flag is needed either way.

Optional — UX review: the legacy `bmad-ux-review` (also `bmm`) is preferred when installed,
because it is purpose-built for review; `bmad-ux`'s opt-in Reviewer Gate is used only when the
legacy `bmad-ux-review` is absent. UX review phases skip gracefully when neither is present.

`bmm` is an **official module, not part of `core`**, so a `--custom-source` install does not
include it unless you pass `--modules bmm` — see [Quick Start](#quick-start). If these skills
are missing, the l3io skills install and activate normally and then fail at the first phase that
dispatches to one. Run `/l3io-util-doctor check-deps` in a target project to see exactly what
resolved there.

## Repo Layout

Skills live in one flat `skills/` directory — the module a skill belongs to is declared in
its own `module.yaml`, not by its position in the tree.

```
skills/
  _shared/               canonical shared sources — pm-status.py, spec-align.py,
                         write-module-config.py, tests/, status-files.md, metrics-contract.md,
                         calibration-model.md, config-resolution.md, module-setup.md, steps/
  l3io-pm-plan/          SKILL.md, customize.toml, references/, assets/, scripts/, steps/, module.yaml
  l3io-pm-execute/       SKILL.md, customize.toml, references/, assets/, scripts/, steps/, module.yaml
  l3io-pm-help/          SKILL.md, customize.toml, references/, assets/, scripts/, module.yaml
  l3io-pm-sync/          SKILL.md, customize.toml, references/, assets/, scripts/, steps/, module.yaml
  l3io-sec-redteam/      SKILL.md, customize.toml, references/, assets/, scripts/, module.yaml
  l3io-util-doctor/      SKILL.md, customize.toml, references/, assets/, scripts/, steps/, module.yaml
  l3io-util-cleanup/     SKILL.md, customize.toml, module.yaml  (deprecated forwarder → l3io-util-doctor)
  l3io-arch-review/      SKILL.md, customize.toml, references/, assets/, scripts/, module.yaml
.claude/commands/        symlinks → ../../skills/<skill>/SKILL.md
.claude-plugin/          marketplace.json (required for installation)
```

Files under `skills/_shared/` are the **only** editable copies of anything shared. Each PM
skill carries a generated payload copy under its own `scripts/`, `references/`, and `steps/`;
those are regenerated by `npm run sync:scripts` and must never be hand-edited. CI runs
`npm run check:scripts` to fail the build on drift.

Each operational skill embeds its own module setup (`assets/module-setup.md` +
config `scripts/`) — there are no standalone `*-setup` skill directories. Setup
runs automatically on first use, or on demand via the module's `configure` action.

## Documentation

**Start here**

- [Getting started](docs/getting-started.md) — prerequisites, install, first sprint and epic run
- [Skills and sequence](docs/skills-and-sequence.md) — why each skill exists, what runs automatically, and the orders that make sense
- [Upgrading](docs/upgrading.md) — version-by-version notes, the migration sequence, backups and rollback
- [Troubleshooting](docs/troubleshooting.md) — what each `BLOCKED:` and `FAILED:` message means, and how to clear it
- [Glossary](docs/glossary.md) — the terms and enum values this package uses
- [Limits](docs/limits.md) — what this package deliberately does not do

**By role**

- Project manager — [Estimation and actuals guide](docs/estimation-guide.md): how estimates are built, what gets recorded at closure, and how calibration learns from your own history
- Architect — [Architecture and execution model](docs/architecture.md): the context boundary, the state contract, the pre-execution gates, and the measured cost model
- Developer — [l3io-pm reference](docs/l3io-pm-reference.md): the full lifecycle, every `pm-status.py` and `spec-align.py` subcommand, and the state schema

**Per module**

- [l3io-pm reference](docs/l3io-pm-reference.md)
- [l3io-sec reference](docs/l3io-sec-reference.md)
- [l3io-util reference](docs/l3io-util-reference.md)
- [l3io-arch reference](docs/l3io-arch-reference.md)

**Internals**

- [How modules are discovered](docs/bmad-module-yaml-discovery.md) — what `module.yaml` controls and how the installer finds skills
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
npm run release          # bump the level the commits imply (feat -> minor, fix -> patch)
npm run release:patch    # force patch, update changelog, create git tag
npm run release:minor    # force minor
npm run release:major    # force major
npm run changelog        # regenerate changelog only
```

Prefer plain `npm run release`: it derives the level from the Conventional Commit types since
the last tag, so a release carrying any `feat` becomes a minor rather than shipping features
under a patch version. The `release:*` aliases force a level and should be used deliberately.

Both hooks are configured in `.versionrc.cjs`, not in `package.json`:

- **`prerelease`** is a hard gate — it refuses to release when payload copies have drifted from
  `skills/_shared/`, when a `payload-manifest.json` hash is stale, when `check:docs` fails, or
  when `pm-status.py`'s version markers disagree.
- **`postbump`** re-syncs after the bump, because the new version string is embedded inside
  payload files: it rewrites `.claude-plugin/marketplace.json`, every `module.yaml`, and
  `pm-status.py`'s version marker, regenerates the manifests, then stages the result.

See [CHANGELOG.md](CHANGELOG.md) for release history.

## Contact

Raise an issue on [GitHub](https://github.com/ravensorb/bmad-extensions/issues), or see [SECURITY.md](SECURITY.md).

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) and our [code of conduct](https://www.contributor-covenant.org/). All commits must sign the [Developer Certificate of Origin](https://developercertificate.org/).

## Licensing

This extension is available under the MIT license.
