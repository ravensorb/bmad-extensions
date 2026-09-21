# Getting Started

Installation and first-run guide for `bmad-l3io-extensions`.

## What this adds to BMad

BMad supplies the agent primitives — story creation, dev, code review, QA, retrospective. This
package adds the layer above them:

- **Orchestration** — dependency-aware phased planning across epics and sprints, so work runs
  in an order that respects what blocks what, and in parallel only where that is safe.
- **Closure discipline** — sprint and epic closure that refuses to sign off while any
  Critical, High or Medium finding is unresolved. Low findings defer to a tracked backlog
  rather than being forgotten.
- **Estimates that learn** — every plan point and closeout records an estimate *and* an
  actual, and future estimates calibrate from that history with no setup.
- **Spec alignment** — acceptance criteria carry pointers back to the spec sections they came
  from, and accepted departures are written back to the spec instead of silently diverging.

Everything runs in short-lived subagents that hand off through files on disk. That is a cost
decision, not an aesthetic one: a session's spend grows with the turns it accumulates, so many
short agents beat one long one.

## Where to start

| You are a… | Start here |
|---|---|
| **Developer** running the work | This guide, then [First Sprint Run](#first-sprint-run) and the [l3io-pm reference](l3io-pm-reference.md) |
| **Project manager** tracking it | [Checking Progress](#checking-progress), then the [estimation guide](estimation-guide.md) for how estimates, actuals and calibration work |
| **Architect** reviewing the model | [Architecture and execution model](architecture.md) — the context boundary, the state contract, and the pre-execution gates |
| **Contributor** to this package | [CONTRIBUTING.md](../CONTRIBUTING.md) — note that `skills/_shared/` holds the only editable copies of shared files |

New to the eight skills? [Skills and sequence](skills-and-sequence.md) explains why each one
exists and which of them run automatically rather than being invoked. When something stops with
a `BLOCKED:` message, see [Troubleshooting](troubleshooting.md); unfamiliar terms are in the
[Glossary](glossary.md).

## Prerequisites

- **An agent IDE** — Claude Code or GitHub Copilot. Both are supported; pick one or both with
  the `--tools` flag at [Install](#install).
- **BMad** installed in the target repo (`npx bmad-method install` or equivalent), including the
  `bmm` module. For every official module BMad offers — which are optional, and which is
  required here — see the module table in the [README](../README.md).
- **[uv](https://docs.astral.sh/uv/)** on your `PATH`. The Python helpers (`pm-status.py`,
  `spec-align.py`) are invoked as `uv run`, which provisions their dependencies from an inline
  PEP 723 header — there is nothing else to install, but without `uv` the first status write
  fails.
- Required BMad skills present, from the `bmm` module. Each site below resolves between two
  names in a deliberately chosen order — for some the 6.12 name is tried first, for others the
  legacy name is tried first because its presence is positive evidence about the install; no
  fixed minimum BMad version is required: `bmad-code-review`, `bmad-qa-generate-e2e-tests`,
  `bmad-retrospective`, `bmad-review` (adversarial lens, tried first; legacy `bmad-review-adversarial-general` used only when `bmad-review` is absent — a disjoint pair, so order is immaterial in practice), and legacy `bmad-check-implementation-readiness` (readiness gate, preferred when installed, since its presence is itself evidence that `intent=readiness` may not be understood on that install; `bmad-sprint-planning intent=readiness` is used only when the legacy skill is absent).
- The legacy `bmad-create-story` / `bmad-dev-story` skills are preferred for story enrichment
  and implementation when installed; this package runs its own in-package agent in their place
  when either is absent, so no shim flag is needed either way.
- Optional — UX review: legacy `bmad-ux-review` is preferred when installed, because it is purpose-built for review; `bmad-ux`'s opt-in Reviewer Gate is used only when `bmad-ux-review` is absent. UX review phases are skipped gracefully when neither is present.
- **WebSearch permission** granted in your IDE if you plan to use `l3io-sec` (required for live cloud/platform best practices research)

Node.js is **not** needed to use the skills — only to develop this package itself, where
`package.json` requires Node 22 or newer.

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
  --modules bmm \
  --tools claude-code \
  --yes
```

**Do not drop `--modules bmm`.** A `--custom-source` install installs BMad's `core` plus the
custom modules only. The required BMad skills listed under
[Prerequisites](#prerequisites) live in the official `bmm` module, so omitting the flag leaves
you with the `l3io` skills and nothing for them to dispatch to. Everything appears to install
correctly and then fails at the first dev phase.

`--tools` selects which agent surfaces are generated: `claude-code` (`.claude/commands/*`),
`github-copilot` (`.github/agents/*.agent.md` plus `.github/copilot-instructions.md`), or both
as a comma-separated list with no spaces.

BMad ≥6.12.0 installs skills to `.claude/skills/<name>/SKILL.md`; earlier releases install to
`.claude/commands/<name>.md`. No `--shims` flag is needed either way — every dependency site in
this package probes both layouts and both name generations and resolves whichever is present.

Interactive path: `npx bmad-method install` -> Community modules -> `bmad-l3io-extensions`
(the installer prompts for which IDEs to target).

This installs all eight skills and registers the four modules in `.claude-plugin/marketplace.json`.

### Verify the install

```
/l3io-util-doctor
```

Run it once, before anything else. With no argument it self-installs the status helper, scans
the project, and prints a findings table — so a clean report confirms both that the skills
resolved and that your project state is readable. If the command is not found, the installer
did not generate a surface for your IDE: re-run the install with the right `--tools` value.

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

No explicit setup step. The first time you invoke `/l3io-arch-review` it registers the module automatically (if no `l3io-arch` section exists in config), then runs. The standards themselves live in the skill's `references/standards-*.md` files — a universal `standards-core.md` plus per-stack overlays that load automatically based on the detected stack. To apply the standards automatically inside core `bmad-architecture` and `bmad-code-review`, run `/bmad-customize` in your project and add the overlays documented in the skill's `assets/customize-architect.md`.

See [l3io-arch reference](l3io-arch-reference.md) for the standards catalog, the three modes, and the customization wiring.

## Upgrading

Re-run the same install command to pull the latest version:

```bash
npx bmad-method install \
  --directory . \
  --custom-source https://github.com/ravensorb/bmad-extensions \
  --modules bmm \
  --tools claude-code \
  --yes
```

Keeping `--modules bmm` here refreshes the BMad skills alongside the extension. If you would
rather leave core BMad untouched and update only this package, use the no-prompt form instead:
`npx bmad-method install --directory . --action quick-update --yes`.

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

The skill loads config and resolves state from the sharded tree. The orchestrator begins
immediately — there is no confirmation prompt. It dispatches story-prep, then one agent per
story, then closure, and reports each phase boundary as it completes.

Per story: Dev → Code Review → Fix Loop (capped at `max_fix_iterations`, default 3). Story
Prep and Closure each run once, for the whole sprint — never per story.

At closure, findings are auto-classified — Critical/High/Medium and undocumented drift route to the closure fix loop (auto-fix, capped at `max_fix_iterations` — default 3); Low findings auto-defer to `state/issues.yaml` as `BL-` backlog items — never as new stories. They stay open until fixed or triaged: `/l3io-pm-plan` offers to promote them into a story, which resolves them automatically when it is done, and `/l3io-util-doctor triage` audits the backlog and closes what is already fixed. The sprint signs off once all Critical/High/Medium issues are resolved. You are only prompted again if a fix loop (per-story or closure) hits its `max_fix_iterations` cap.

At sign-off the orchestrator records **actuals** alongside the estimate for all five metrics — compute (wall-clock) hours, man-hours (a counterfactual re-assessment made at closure, not an observed figure), human-attention (hitl) hours, tokens, and token cost. Cost is never entered directly; it is derived from the captured tokens and the model's rate table. Under Claude, tokens are captured exactly from the session transcript, split by class, and cost is priced from them; under other runtimes (e.g. Copilot) tokens show as `N/A` rather than a guess. Estimates self-calibrate from this plan-vs-actual history — decomposed into story-scope, closure, fix, and orchestration components that each activate once they have enough samples — with no setup needed. See the [PM reference](l3io-pm-reference.md#metrics-contract-estimates--actuals) for the full metrics contract and calibration details.

## First Epic Run

Same skill, epic scope:

```
/l3io-pm-execute E001
```

Omit the argument entirely to run the whole plan in phase order. Sprints must already exist in
state before an epic run — the orchestrator does not group stories into sprints or ask you
to split them. State is created by `/l3io-pm-plan` (recommended) or by
`/l3io-util-doctor bootstrap-state` for projects whose stories were created via the legacy `bmad-create-story` workflow without going through l3io-pm-plan.

The orchestrator dispatches each pending sprint in order. For each sprint it dispatches
*headless* subagent invocations of itself — **one to prep the sprint, one per story, and one to close the sprint** — with no grouping prompt and no per-sprint scope-confirmation prompt — then runs epic-level closure after all sprints complete.

You will see more agents than you might expect, and that is the point: cost grows with the number of turns a single session accumulates, not with the number of sessions. Splitting a sprint across short-lived agents is cheaper than one long one, and costs nothing in continuity because every hand-off is a file on disk. Between sprints, the orchestrator continues immediately to the next sprint without prompting. Epic closure auto-triages findings the same way sprints do; only halts if its closure fix loop hits the `max_fix_iterations` cap.

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
uv run _bmad/scripts/pm-status.py report \
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

> `/l3io-util-cleanup` was renamed to `/l3io-util-doctor` in 2.1.0. The old name's deprecated
> forwarder was removed in 3.0.0 — see [Upgrading](upgrading.md).

To split a legacy single `sprint-status.yaml` into the active/backlog/archived three-file layout as a one-time explicit migration (the original is preserved as `sprint-status.yaml.legacy`):

```
/l3io-util-doctor split-status
```

If a PM skill detects a legacy `sprint-status.yaml`, it halts and tells you to run `/l3io-util-doctor migrate-state` — it never splits it automatically.

> **`split-status` alone is not enough.** The three-file layout it produces is still a legacy
> shape that the PM skills cannot read. It exists only so `reconcile-status` can tidy a messy
> flat file before `migrate-state` consumes it — so always follow it with `migrate-state`, or
> let the health check sequence the whole migration for you. See
> [Upgrading](upgrading.md) for the full ordered sequence.

To sweep the source tree for `bmad-defer:` deferred-shortcut markers and harvest them into the backlog (report-only until you confirm the merge):

```
/l3io-util-doctor harvest-debt
```

A `bmad-defer:` marker is a one-line comment a developer (or a dev subagent) leaves on a deliberate simplification — `// bmad-defer: <what was simplified>. ceiling: <limit>. upgrade: <trigger>.` — recognized across every common language's comment syntax. Harvesting turns those crumbs into tracked backlog items so they don't rot silently; markers that name no upgrade trigger are flagged at a higher severity. Sprint closure also harvests the markers in each sprint's changed files automatically, so this command is for whole-tree or on-demand sweeps.
