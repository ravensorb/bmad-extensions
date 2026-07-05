# Getting Started

Installation and first-run guide for `bmad-l3io-extensions`.

## Prerequisites

- **Claude Code** installed and working
- **BMad** installed in the target repo (`npx bmad-method install` or equivalent)
- Required BMad skills present: `bmad-create-story`, `bmad-dev-story`, `bmad-code-review`, `bmad-qa-generate-e2e-tests`, `bmad-retrospective`, `bmad-review-adversarial-general`
- Optional: `bmad-ux-review` (UX review phases are skipped gracefully when absent)
- **WebSearch permission** granted in Claude Code if you plan to use `l3io-sec` (required for live cloud/platform best practices research)

## Module Selection

You can install all four modules or only the ones you need:

| Module | Install if you want |
|--------|---------------------|
| **l3io-pm** | Sprint and epic orchestration |
| **l3io-sec** | Adversarial security review (standalone or automatic inside l3io-pm closure) |
| **l3io-util** | One-time cleanup of legacy flat artifact layouts |
| **l3io-arch** | Engineering-standards architecture guardrails and review (new-project design, review audits, and ADR-recorded decisions) |

All four modules are installed by the same `npx bmad-method install` command. Each module handles its own first-run configuration — no separate setup step required.

## Install

Run in the project repo where you want to use the extension:

```bash
npx bmad-method install \
  --directory . \
  --custom-source https://github.com/ravensorb/bmad-extensions \
  --tools claude-code \
  --yes
```

Interactive path: `npx bmad-method install` -> Community modules -> `bmad-l3io-extensions`.

This installs all five skills and registers the four modules in `.claude-plugin/marketplace.json`.

## First-Run Configuration

Config is written to `{project-root}/_bmad/config.yaml` (shared project settings) and `{project-root}/_bmad/config.user.yaml` (personal settings — add this to `.gitignore`).

Each module auto-configures on first use — no explicit setup step required.

### l3io-pm

No explicit setup step. The sprint and epic skills read config from `{project-root}/_bmad/config.yaml` on activation and use sensible defaults when the `l3io-pm` section is absent. On first run, module registration happens automatically.

Key settings (with defaults):

- `output_folder` — default: `{project-root}/_bmad-output`
- `implementation_artifacts` — default: `{output_folder}/implementation-artifacts`
- `planning_artifacts` — default: `{output_folder}/planning-artifacts`

See [l3io-pm reference](l3io-pm-reference.md) for the full config schema.

### l3io-sec

No explicit setup step. The first time you invoke `/l3io-sec-agent-redteam` it initializes its sanctum and, if no `l3io-sec` section exists in config, runs module registration automatically.

For WebSearch to work, ensure the `WebSearch` tool is allowed in your Claude Code permissions.

### l3io-util

No explicit setup step. The first time `/l3io-util-cleanup` runs it registers the module automatically before performing cleanup.

### l3io-arch

No explicit setup step. The first time you invoke `/l3io-arch-review` it registers the module automatically (if no `l3io-arch` section exists in config), then runs. The standards themselves live in the skill's `references/standards-*.md` files — a universal `standards-core.md` plus per-stack overlays that load automatically based on the detected stack. To apply the standards automatically inside core `bmad-architect` and `bmad-code-review`, run `/bmad-customize` in your project and add the overlays documented in the skill's `assets/customize-architect.md`.

See [l3io-arch reference](l3io-arch-reference.md) for the standards catalog, the three modes, and the customization wiring.

## Upgrading

Re-run the same install command to pull the latest version:

```bash
npx bmad-method install \
  --directory . \
  --custom-source https://github.com/ravensorb/bmad-extensions \
  --tools claude-code \
  --yes
```

After upgrading, your existing `_bmad/config.yaml` values are preserved — no re-configuration needed unless the upgrade notes call out schema changes.

## Before Running l3io-pm

Before your first sprint or epic run, verify:

1. The sprint status files exist under `{implementation_artifacts}/` — the split layout is `sprint-status.yaml` (in-progress epics), `sprint-status-backlog.yaml` (not-yet-started work plus the consolidated deferred-issue backlog), and `sprint-status-archived.yaml` (done epics) — and your stories are present with status `backlog`. If you only have a legacy single `sprint-status.yaml`, the PM skills auto-split it on first run (renaming the original to `sprint-status.yaml.legacy`); you can also split it explicitly with `/l3io-util-cleanup split-status`
2. Planning docs (epics file, PRD, architecture spec) exist under `{planning_artifacts}`
3. If you have existing flat artifacts from a prior layout, run `/l3io-util-cleanup` first

Story status values: `backlog` → `ready-for-dev` → `in-progress` → `review` → `done`.

## First Sprint Run

Invoke:

```
/l3io-pm-sprint-execute
```

The skill loads config, reads the sprint status (the active + backlog split files; a legacy single `sprint-status.yaml` is auto-split on first run), identifies the first in-progress or backlog epic with non-done stories, and presents a scope confirmation:

```
Sprint Orchestrator: Epic 01, Sprint 01 — 3 stories: 1-0, 1-1, 1-2
Per story:  Story Prep → Dev → Code Review → QA → Fix Loop
Closure:    Retrospective → Clean Release → Adversarial → Red Team → UX → Arch Drift → Issue Triage
...
Pre-start estimate:
  Stories:         3 (0 simple, 3 standard, 0 complex)
  Est. story work: 0.6–1.0 h   (Σ stories, fix reserve included)
  Est. closure:    0.4–0.8 h
  ────────────────────────────────────────────────────────
  Total estimate:  1.0–1.8 hours    Tokens: 270K–480K    Cost: ~$2.16–$3.84
  Calibration:     none yet — formula baseline (components calibrate at ≥3 samples)
  (Actuals reported at sprint close.)

Shall I begin?
```

Confirm to start (interactive mode requires explicit `yes` before any subagent runs). The orchestrator delegates each story phase to a fresh subagent and reports progress. At closure, findings are auto-classified — Critical/High/Medium and undocumented drift route to the closure fix loop (auto-fix, max 10 iterations); Low findings auto-defer to backlog as new stories. The sprint signs off once all Critical/High/Medium issues are resolved. You are only prompted again if a fix loop (per-story or closure) hits its 10-iteration cap.

At sign-off the orchestrator records **actuals** alongside the estimate for all four metrics — compute (wall-clock) hours, man-hours, tokens, and token cost. Under Claude, tokens and cost are captured exactly from the session transcript; under other runtimes (e.g. Copilot) they show as `N/A` rather than a guess. Estimates self-calibrate from this plan-vs-actual history — decomposed into story-scope, closure, and fix components that each activate once they have ≥3 samples — with no setup needed. See the [PM reference](l3io-pm-reference.md#metrics-contract-estimates--actuals) for the full metrics contract and calibration details.

## First Epic Run

Invoke:

```
/l3io-pm-epic-execute
```

The skill reads the sprint status (the active + backlog split files; a legacy single `sprint-status.yaml` is auto-split on first run), identifies the target epic, and presents a sprint grouping step:

```
Epic 01: My Feature
Total stories:  8
Already done:   0
Remaining:      8 — 1-0, 1-1, 1-2, 1-3, 1-4, 1-5, 1-6, 1-7

Default: all remaining stories as one sprint.
To split: provide story key groups (e.g. Sprint 1: 1-0, 1-1 / Sprint 2: 1-2, 1-3)
```

Confirm the grouping or provide a custom split. The epic orchestrator spawns one `l3io-pm-sprint-execute` subagent per sprint (running headlessly — no per-sprint scope-confirmation prompt), then runs epic-level closure after all sprints complete. Between sprints, the orchestrator continues immediately to the next sprint without prompting. Epic closure auto-triages findings the same way sprints do; only halts if its closure fix loop hits the 10-iteration cap.

## Using l3io-sec

### Automatic (inside l3io-pm)

`l3io-sec-agent-redteam` runs automatically as Step 6 of sprint closure and Step 4c of epic closure — as long as the skill is installed. No separate invocation needed.

### Standalone

Invoke directly for ad hoc reviews:

```
/l3io-sec-agent-redteam
```

On first run it initializes its sanctum (persistent memory) at `{project-root}/_bmad/memory/l3io-sec-agent-redteam/`. On subsequent runs it loads its identity from the sanctum and asks for scope and target.

To run a scoped analysis against a specific sprint or epic, provide the scope when prompted. The skill loads relevant platform research cache topics, runs all five threat lenses, and writes a report.

## Using l3io-util

Run when you have legacy flat artifacts that need to be reorganized:

```
/l3io-util-cleanup
```

The skill scans `{implementation_artifacts}` and `{planning_artifacts}` flat roots, classifies each file, and presents a dry-run move table before making any changes:

```
DRY RUN — Artifact Cleanup
Source                     → Destination                       Class           Status
1-0-story.md               → epic-01/sprint-01/stories/...    story           move
epic-1-sprint-1-retro.md   → epic-01/sprint-01/closure/...    sprint-closure  move
```

Confirm to execute. Ambiguous references are never auto-updated — they are flagged for manual review.

Run `/l3io-util-cleanup` once per project. A second run on an already-clean layout produces zero moves.

To upgrade an existing sprint status file to the current field schema (adds missing estimate, actual, classification, and completion_evidence fields with zero/empty defaults):

```
/l3io-util-cleanup migrate-schema
```

To split a legacy single `sprint-status.yaml` into the active/backlog/archived three-file layout as a one-time explicit migration (the original is preserved as `sprint-status.yaml.legacy`):

```
/l3io-util-cleanup split-status
```

The PM skills also auto-split a legacy single `sprint-status.yaml` on first run, so this explicit step is optional.

To sweep the source tree for `bmad-defer:` deferred-shortcut markers and harvest them into the backlog (report-only until you confirm the merge):

```
/l3io-util-cleanup harvest-debt
```

A `bmad-defer:` marker is a one-line comment a developer (or a dev subagent) leaves on a deliberate simplification — `// bmad-defer: <what was simplified>. ceiling: <limit>. upgrade: <trigger>.` — recognized across every common language's comment syntax. Harvesting turns those crumbs into tracked backlog items so they don't rot silently; markers that name no upgrade trigger are flagged at a higher severity. Sprint closure also harvests the markers in each sprint's changed files automatically, so this command is for whole-tree or on-demand sweeps.
