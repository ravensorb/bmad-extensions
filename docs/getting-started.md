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
| **l3io-util** | Project state diagnostics, the progress dashboard, and legacy layout migration |
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

This installs all eight skills and registers the four modules in `.claude-plugin/marketplace.json`.

## First-Run Configuration

Core settings live in installer-owned `{project-root}/_bmad/config.toml` and `config.user.toml`. Your own module settings go in `{project-root}/_bmad/custom/config.toml` (team, committed) and `custom/config.user.toml` (personal, gitignored), under `[modules.<module-code>]`.

No module needs configuring to work — every setting has a default. Run a module's `configure` action only when you want to change one.

### l3io-pm

No explicit setup step. The skills resolve config at activation via `_bmad/scripts/resolve_config.py` and use sensible defaults when `modules.l3io-pm` is absent — which is the normal state for a fresh install.

Key settings (with defaults):

- `output_folder` — default: `{project-root}/_bmad-output`
- `implementation_artifacts` — default: `{output_folder}/implementation-artifacts`
- `planning_artifacts` — default: `{output_folder}/planning-artifacts`

See [l3io-pm reference](l3io-pm-reference.md) for the full config schema.

### l3io-sec

No explicit setup step. The first time you invoke `/l3io-sec-redteam` it initializes its sanctum and, if no `l3io-sec` section exists in config, runs module registration automatically.

For WebSearch to work, ensure the `WebSearch` tool is allowed in your Claude Code permissions.

### l3io-util

No explicit setup step. The first time `/l3io-util-doctor` runs it registers the module automatically before performing cleanup.

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

After upgrading, your `_bmad/custom/config.toml` and `config.user.toml` overrides are preserved — the installer never touches those layers.

### Upgrading from 1.x

The installer refreshes skills; it does not migrate your data. Run `/l3io-util-doctor` once
before any sprint or epic run — it inspects the project and applies every migration you
need, in dependency order, behind one confirmation.

The 1.x → 2.x jump renamed and merged several skills and changed the state layout twice.
See **[Upgrading](upgrading.md)** for the version-by-version notes, the full ordered
sequence, backups and rollback, and current deprecations.

## Before Running l3io-pm

Before your first sprint or epic run, verify:

1. State exists under `{implementation_artifacts}/state/` in the sharded layout — one
   directory per epic, placed in the folder named for its status:

   ```
   state/planned/epic-005/epic.yaml            ← not started
   state/active/epic-001/epic.yaml             ← in progress
   state/active/epic-001/sprint-01/sprint.yaml
   state/active/epic-001/sprint-01/E001-S01-001.yaml
   state/archived/epic-002/epic.yaml           ← done
   ```

   One bare node per file; children are discovered by listing the directory. If you are
   upgrading from a legacy layout — a flat `sprint-status.yaml`, the three-file split, or a
   per-epic `_bmad/state/` tree — run `/l3io-util-doctor` first and let it sequence the
   migration; see [Upgrading](upgrading.md). Originals are preserved as `.legacy`.
2. Planning docs (epics file, PRD, architecture spec) exist under `{planning_artifacts}`
3. If you are unsure what shape your project is in, run `/l3io-util-doctor` — with no
   argument it reports findings and proposes the right actions in order

Story status values: `backlog` → `ready-for-dev` → `in-progress` → `review` → `done`.

### Optional: generate an execution plan first

If you have multiple epics, run `/l3io-pm-plan` before starting execution. It validates
readiness, elaborates thin stories, estimates, reads `depends_on` declarations, and produces
a phased parallel-optimized plan — which epics to run first, which can run in parallel, and
the critical path. It writes a dated snapshot plus the stable `plan-output-meta.yaml`
pointer that `/l3io-pm-execute` reads.

To declare dependencies, add `depends_on` to the epic or story node file. Nodes are stored
**bare** — there is no `epics:` or `stories:` wrapper, and keys are zero-padded:

```yaml
# state/planned/epic-003/epic.yaml — E003 waits for E001 and E002
key: 'E003'
depends_on: ['E001', 'E002']
```

```yaml
# state/planned/epic-003/sprint-01/E003-S01-001.yaml — blocks on a story in another epic
key: 'E003-S01-001'
epic: 'E003'
sprint: 'S01'
depends_on: ['E001-S02-003']
```

## First Sprint Run

There is no separate sprint skill — `/l3io-pm-execute` takes a scope argument. To run one
sprint:

```
/l3io-pm-execute E001-S01
```

The skill loads config, resolves state from the sharded tree, and presents a scope
confirmation:

```
Sprint Orchestrator: E001 / S01 — 3 stories: E001-S01-001, E001-S01-002, E001-S01-003
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

Confirm to start (interactive mode requires explicit `yes` before any subagent runs). The orchestrator delegates each story phase to a fresh subagent and reports progress. At closure, findings are auto-classified — Critical/High/Medium and undocumented drift route to the closure fix loop (auto-fix, max 10 iterations); Low findings auto-defer to `state/issues.yaml` as `BL-` backlog items — never as new stories. The sprint signs off once all Critical/High/Medium issues are resolved. You are only prompted again if a fix loop (per-story or closure) hits its 10-iteration cap.

At sign-off the orchestrator records **actuals** alongside the estimate for all four metrics — compute (wall-clock) hours, man-hours, tokens, and token cost. Under Claude, tokens and cost are captured exactly from the session transcript; under other runtimes (e.g. Copilot) they show as `N/A` rather than a guess. Estimates self-calibrate from this plan-vs-actual history — decomposed into story-scope, closure, and fix components that each activate once they have ≥3 samples — with no setup needed. See the [PM reference](l3io-pm-reference.md#metrics-contract-estimates--actuals) for the full metrics contract and calibration details.

## First Epic Run

Same skill, epic scope:

```
/l3io-pm-execute E001
```

Omit the argument entirely to run the whole plan in phase order. The skill resolves the
target epic and presents a sprint grouping step:

```
E001: My Feature
Total stories:  8
Already done:   0
Remaining:      8 — E001-S01-001 … E001-S01-008

Default: all remaining stories as one sprint.
To split: provide story key groups
  (e.g. Sprint 1: E001-S01-001, E001-S01-002 / Sprint 2: E001-S01-003, …)
```

Confirm the grouping or provide a custom split. The orchestrator dispatches one *headless* subagent invocation of itself per sprint (no per-sprint scope-confirmation prompt), then runs epic-level closure after all sprints complete. Between sprints, the orchestrator continues immediately to the next sprint without prompting. Epic closure auto-triages findings the same way sprints do; only halts if its closure fix loop hits the 10-iteration cap.

## Checking Progress

A full epic run is long. Three ways to see where it is, all read-only.

**Ask, at any time:**

```
/l3io-pm-help progress
```

Renders the plan-aware tree — which phase, which epic, which sprint, and which stories are in
flight, with how long each has sat in its current status and a `⚠ stuck` marker past the
threshold (4h for a story in `review` or `in-progress`):

```
PLAN plan-2026-08-17-v2.yaml   readiness=green

Phase 1/2 (parallel)  █████░░░░░  1/2 epics done
  E001 Foundation               in-progress  8/12 stories
    S02    in-progress  3/7
      E001-S02-004         review         7.5h  ⚠ stuck
      E001-S02-005         in-progress    1.1h
```

**Watch it live**, in a second terminal, while a run is in progress:

```bash
python3 _bmad/scripts/pm-status.py report \
  --state-root {implementation_artifacts}/state \
  --plan {planning_artifacts}/plan-output-meta.yaml \
  --watch 15
```

This is the only way to get per-sprint detail during a *parallel* phase: the run itself
suppresses those renders, because several epics reporting at once would interleave into
unreadable output.

**Read the committed report.** `{implementation_artifacts}/progress-report.md` is regenerated
at every sprint and epic closure, so it is diffable in git and shareable with people who do
not run the CLI. It is a generated view — never hand-edit it.

Pass `--all` to any of these to include finished, archived epics; by default they count toward
each phase's progress bar but are not listed.

Dwell times display with a `~` prefix until `{implementation_artifacts}/state/events.jsonl`
has recorded transitions — before then they are derived from `updated_at`, which any field
write refreshes, so they are approximate. The log starts recording on your next run.

## Using l3io-sec

### Automatic (inside l3io-pm)

`l3io-sec-redteam` runs automatically during both sprint closure and epic closure — as long as the skill is installed. No separate invocation needed.

### Standalone

Invoke directly for ad hoc reviews:

```
/l3io-sec-redteam
```

On first run it initializes its sanctum (persistent memory) at `{project-root}/_bmad/memory/l3io-sec-redteam/`. On subsequent runs it loads its identity from the sanctum and asks for scope and target.

To run a scoped analysis against a specific sprint or epic, provide the scope when prompted. The skill loads relevant platform research cache topics, runs all five threat lenses, and writes a report.

## Using l3io-util

Run with no argument any time you want a health check, or when you have a legacy layout or
flat artifacts to reorganize:

```
/l3io-util-doctor
```

The skill scans `{implementation_artifacts}` and `{planning_artifacts}` flat roots, classifies each file, and presents a dry-run move table before making any changes:

```
DRY RUN — Artifact Cleanup
Source                     → Destination                       Class           Status
1-0-story.md               → epic-001/sprint-01/stories/...   story           move
epic-1-sprint-1-retro.md   → epic-001/sprint-01/closure/...   sprint-closure  move
```

Confirm to execute. Ambiguous references are never auto-updated — they are flagged for manual review.

The layout reorganization is a once-per-project operation; a second run on an already-clean
layout produces zero moves. The diagnostic itself is safe to run any time.

Two modes worth knowing:

```
/l3io-util-doctor migrate-state    # legacy layout → sharded state tree (run this first)
/l3io-util-doctor stats            # plan-aware progress dashboard, read-only
```

> `/l3io-util-cleanup` was renamed to `/l3io-util-doctor` in 2.1.0. The old name still works
> and forwards, but is deprecated.

To split a legacy single `sprint-status.yaml` into the active/backlog/archived three-file layout as a one-time explicit migration (the original is preserved as `sprint-status.yaml.legacy`):

```
/l3io-util-doctor split-status
```

The PM skills also auto-split a legacy single `sprint-status.yaml` on first run, so this explicit step is optional.

To sweep the source tree for `bmad-defer:` deferred-shortcut markers and harvest them into the backlog (report-only until you confirm the merge):

```
/l3io-util-doctor harvest-debt
```

A `bmad-defer:` marker is a one-line comment a developer (or a dev subagent) leaves on a deliberate simplification — `// bmad-defer: <what was simplified>. ceiling: <limit>. upgrade: <trigger>.` — recognized across every common language's comment syntax. Harvesting turns those crumbs into tracked backlog items so they don't rot silently; markers that name no upgrade trigger are flagged at a higher severity. Sprint closure also harvests the markers in each sprint's changed files automatically, so this command is for whole-tree or on-demand sweeps.
