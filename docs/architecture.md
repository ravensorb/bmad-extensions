# Architecture

Execution model and design principles for `bmad-l3io-extensions`.

## Context Boundary Principle

The core design rule: **one phase = one fresh subagent; all state passes through disk.**

No subagent receives conversation history from the orchestrator or from a sibling subagent. Each subagent starts clean, reads what it needs from disk (config files, story files, state nodes), does its work, writes outputs to disk, and terminates with a single status line.

This is not just a performance optimization. It prevents context contamination — where earlier work influences later analysis in ways that reduce quality or introduce inconsistency. A code reviewer that has watched the development process will rationalize what it sees. A fresh code reviewer applies consistent standards.

The same principle applies to `l3io-sec`: the agent's memory is disk-based (its sanctum) precisely so that each session starts with a deliberate reload, not an inherited in-context state.

## Module Relationships

`l3io-pm-execute` is a single skill that runs in two modes. In **normal mode** it is the epic orchestrator; it dispatches each sprint as a **headless** subagent invocation of *itself*. There is no separate sprint skill.

```
l3io-pm-plan          (read-only — produces the plan snapshot + plan-output-meta.yaml)
    |
    v
l3io-pm-execute  (normal mode — epic orchestrator)
    |
    |-- spawns --> l3io-arch-review Mode B  (step-04 arch gate, before any sprint)
    |-- spawns --> bmad-agent-architect / superpowers  (additional gate reviewers, if present)
    |
    |-- spawns --> l3io-pm-execute (headless: true — one per sprint, always sequential)
                       |
                       |-- spawns --> bmad-create-story      (story prep)
                       |-- spawns --> bmad-dev-story         (dev + fix loop)
                       |-- spawns --> bmad-code-review       (code review)
                       |-- spawns --> bmad-retrospective     (closure)
                       |-- spawns --> bmad-review-adversarial-general
                       |-- spawns --> l3io-sec-redteam       (closure, if installed)
                       |-- spawns --> bmad-ux-review         (closure, if installed)
                       |-- spawns --> l3io-arch-review Mode C (drift audit, if installed)

l3io-pm-help            (read-only — recommends the next action)
l3io-pm-sync            (bidirectional GitHub Issues sync)
l3io-sec-redteam        (also invocable standalone)
l3io-util-doctor       (standalone only — migration utilities)
l3io-arch-review        (standalone, plus invoked by the gate and drift reviews above)
```

`l3io-sec` is optionally dependent on `l3io-pm` at runtime (called during closure), but has no build-time or config dependency. It runs standalone and only uses the l3io-pm config section if l3io-pm has already been configured.

`l3io-arch` carries the engineering-standards charter (`references/standards-*.md`). It is invoked by l3io-pm's architecture gate and drift reviews, and is designed to also be wired into core `bmad-architect`, `bmad-create-story`, and `bmad-code-review` via `bmad-customize`, so the standards apply automatically during design and review without forking those core skills.

## Orchestrator Pattern

The orchestrator acts as a traffic controller, not an implementer. Its context holds only:

- Epic, sprint, and story keys with their statuses, obtained from `pm-status.py show`
- Status-line summaries returned by subagents
- Path bindings (no file contents)

It never reads story file contents into its own context. When a story file is needed, it passes the path to a subagent — the subagent reads it. This keeps the orchestrator context small regardless of how many stories exist or how large each story file grows.

Subagent prompts are self-contained. The headless sprint dispatch passes an explicit **authoritative context block** (work type, skip phases, epic key, sprint root, story keys, and the exact ordered list of step files to load). Nothing is implicit.

## State Contract

All l3io-pm state lives under `{implementation_artifacts}/state/`, is committed to git, and is co-located with the artifacts it describes. Nothing state-related lives under `{project-root}/_bmad/` — that tree is installer-owned and gitignored.

State is **sharded**: one bare YAML node per file, with the directory structure replacing the old `sprints:` and `stories:` lists. Children are discovered by listing the directory.

```
{implementation_artifacts}/state/
├── planned/   epic-005/epic.yaml, sprint-01/sprint.yaml, sprint-01/E005-S01-001.yaml
├── active/    epic-001/…
├── archived/  epic-002/…
├── issues.yaml            ← flat BL-E{nnn}-{nnn} deferred-issue list
├── events.jsonl           ← append-only transition log (committed — source of dwell time)
└── pm-calibration.yaml    ← learned estimation ratios (committed — team knowledge)
```

### The two trees

`state/{status}/epic-001/` and the top-level `epic-001/` hold two different *kinds* of fact about the same epic. They are not duplicates.

| | `state/{status}/epic-001/` | `epic-001/` (top level) |
|---|---|---|
| Holds | Status, estimates, actuals, locks | Story markdown, closure reports, QA tests, ADRs |
| Written by | `pm-status.py` only, atomically | Humans and dev / review agents |
| Moves? | Yes — `planned/` → `active/` → `archived/` | Never |

**Every epic with artifacts has state; not every epic with state has artifacts yet.** A planned epic has estimates before any story is authored; a done epic keeps both permanently.

### Placement rule

An epic's directory lives in the folder named for its status. Every transition is a `git mv` of the whole directory, so sprints and stories travel with their epic and `git log --follow` keeps working across every transition. `archive-epic` is a directory move and nothing else.

### Addressing

**All node operations go through `pm-status.py` with `--state-root` plus node keys — never a hand-built path.** Layout knowledge lives in exactly one place, so a future layout change touches only that script.

```bash
uv run {pm_status} set-status --state-root {pm_state_root} --story E001-S01-003 --status done
```

`append-issue` is the one exception: `issues.yaml` is a flat file with no resolvable node key, so it takes `--file`.

**Who writes it:** `pm-status.py` exclusively. Every status transition, `actual` block, estimate, event-log append, and read-back `verify` is one atomic, `ruamel`-round-trip-safe operation preserving comments and key order. This replaced free-form YAML edits that were dropped or malformed under load and parallelism.

**Concurrency:** per-epic directories mean epic-scoped writes touch only that epic's files — **no flock needed**. The three files sharding cannot shard are inherently cross-epic aggregates and all take an automatic exclusive flock: `issues.yaml` (on append), `events.jsonl` (on append), and `pm-calibration.yaml` (whole read-modify-write cycle, since two concurrent samplers would otherwise silently drop one another's samples).

**Reads are lock-free.** Every write goes through an atomic temp-file-plus-rename, so a reader — notably `pm-status.py report --watch` polling during a parallel phase — can never observe a torn node file and needs no lock of its own.

### Lifecycles

```
story:  backlog → ready-for-dev → in-progress → review → done
epic:   backlog → in-progress → done
```

### Ownership lock

`l3io-pm-execute` claims an epic by writing a `_lock` block (session id, claimed-at, TTL — default 30 minutes) as the first key of `epic.yaml`. `check-lock` exits `0` when free or stale, `5` when held by a live session. A nonexistent epic is deliberately treated differently per verb: `check-lock`/`clear-lock` exit `0` (queries and cleanup succeed on absence), while `set-lock` exits `3` — it needs a file to write into.

### Legacy detection

At activation, read resolution checks for the current layout, the legacy per-epic `_bmad/state/` tree, and the legacy flat `sprint-status.yaml`. Detection **counts matches rather than stopping at the first hit** — if more than one layout is present, it blocks rather than guessing which is authoritative. Migration is `/l3io-util-doctor migrate-state`.

## Artifact Directory Structure

Epic directories are 3-digit zero-padded (`epic-001`); sprints are 2-digit (`sprint-01`); story keys are `E{nnn}-S{nn}-{nnn}`. Zero-padding makes lexical directory order the correct processing order, so there is no separate ordering field to drift.

```
{implementation_artifacts}/
  state/                          ← see State Contract above
  epic-001/
    sprint-01/
      stories/E001-S01-001.md
      closure/retrospective.md
      closure/closure-report.md
      tests/
    arch/adr-001-{slug}.md        ← written by the architecture gate
    epic-closure/retrospective.md
    epic-closure/closure-report.md
    tests/

{planning_artifacts}/
  plan-{date}-v{n}.yaml           ← immutable plan snapshots, versioned per day
  plan-output-meta.yaml           ← stable pointer to the current plan
  readiness-report.md
  elaboration-summary.md
```

## Pre-Execution Architecture Gate

Before any sprint runs, `l3io-pm-execute` step-04 gates the whole epic's design. This is a shift-left: architecture gaps surface before development instead of at closure.

The gate is **skipped entirely** for `DOCS` and `CONFIG` work types, and when `l3io-arch-review` is absent — it never partially skips, because at least one reviewer must run for the gate to mean anything.

Reviewers run in parallel (`l3io-arch-review` Mode B always; `bmad-agent-architect` and superpowers when detected), and their findings are consolidated by explicit rules:

| Finding | Rule |
|---|---|
| BLOCKER from any reviewer | BLOCKER — never downgraded |
| MAJOR from ≥2 reviewers | MAJOR confirmed — blocks execution |
| MAJOR from 1 reviewer | MAJOR flagged (single-source) — still blocks |
| MINOR from ≥2 reviewers | MINOR confirmed — deferred to issues |
| MINOR from 1 reviewer | Auto-deferred to issues |

Each blocking finding is resolved by writing an ADR under `epic-{nnn}/arch/` **and** patching the affected story files with the technical ACs the decision implies. One re-validation pass follows; unresolved blockers halt execution.

If the gate finds zero findings on non-trivial CODE scope it asks for confirmation rather than passing silently — a clean result there is unusual enough to be worth a second look.

## Adaptive Parallelism

Parallelism is used only where it is provably safe, and the safety comes from the state design: atomic per-node writes through `pm-status.py` plus per-epic directories mean concurrent branches never contend for a file.

| Level | Concurrency |
|---|---|
| Epics within a plan phase | Parallel, up to `max_parallel_subagents` (default 4) |
| Sprints within an epic | **Always sequential** |
| Stories within a sprint | Sequential, ordered by `depends_on` |
| Arch gate reviewers | Parallel across detected reviewers |

Across phases, the orchestrator verifies every prerequisite epic is `status: done` before starting the next phase. Within an epic, a story with `depends_on` waits until each referenced story is `done`; if a dependency is not in this sprint's scope, the story moves to the end of the queue rather than blocking the sprint.

Epic-level parallelism is additionally bounded by the ownership lock: an epic already claimed by a live session is skipped with a `BLOCKED` line rather than double-executed.

## Quality Gate Contracts

### Sprint closure

Phases run in order, with work-type-driven skips:

| Phase | CODE | DOCS | CONFIG | MIXED |
|---|---|---|---|---|
| Retrospective | run | run | run | run |
| Clean release review | run | skip | run | run |
| Adversarial analysis | run | skip | skip | run |
| Red team (l3io-sec) | run | skip | skip | run |
| UX review | run | run | skip | run |
| Architectural drift | run | skip | run | run |
| Issue triage | run | run | run | run |

Severity routing is uniform across phases: **CRITICAL/HIGH** block closure and open a fix loop (10-iteration cap); **MEDIUM** is fixed in place before the sprint is marked done; **LOW** auto-defers to `issues.yaml` via `pm-status.py append-issue` — a `BL-` item, never a new story, and never a per-item prompt.

### Epic closure

Retrospective across all sprint retros → architectural drift audit (`l3io-arch-review` Mode C, CODE/MIXED only) → issue triage, which re-reviews the epic's deferred Low items for promotion now that full epic context exists → closure report with the estimate-vs-actual table for all four metrics.

CRITICAL/HIGH/MEDIUM drift findings must be resolved before closure completes, under the same 10-iteration fix-loop cap.

## Metrics Contract

Every planning point and every closeout — story, sprint, epic, and retrospective — records both an `estimate` and an `actual` for all four metrics: man-hours, compute (AI wall-clock) hours, tokens, and token cost. This is enforced at write time, not by convention: under `--runtime claude`, `set-actual` and `verify` **reject** an `N/A` tokens/cost value.

Estimates are a strict bottom-up roll-up — `sprint.estimate = Σ story.estimate + calibrated closure band`, `epic.estimate = Σ sprint.estimate + calibrated epic-closure band` — so parents reconcile with children by construction rather than by a parallel formula that could drift.

Full model and capture procedure: each PM skill's `references/metrics-contract.md`.

## Subagent Invocation

**Preferred method:** Agent tool with a self-contained prompt. No conversation history is forwarded — only paths, keys, and the skill to invoke.

**Fallback:** `claude --print` with a heredoc prompt, when the Agent tool is unavailable.

Every subagent ends with exactly one status line:

```
DONE — [brief metrics]
BLOCKED: [one-line reason]
FAILED: [one-line reason]
```

The orchestrator branches on this line. At the sprint level the distinction matters: `BLOCKED` halts the epic loop, while `FAILED` is non-fatal — the orchestrator logs it, tracks the count, and continues to the next sprint.

Headless sprint runs emit a richer DONE line:

```
DONE — Stories: N, Issues resolved: N, Issues deferred: N
```

## Customization Model

Each skill ships with a `customize.toml` at its skill root. Overrides layer in this order:

```
{skill-root}/customize.toml                          (base — shipped, don't edit)
    ↓ override
{project-root}/_bmad/custom/{skill-name}.toml        (team — commit to repo)
    ↓ override
{project-root}/_bmad/custom/{skill-name}.user.toml   (personal — gitignore)
```

Scalar values override; array values append. `resolve_customization.py` performs the merge at activation; if it fails, the skill falls back to reading the three files in order and applying the same precedence.

**The root key must match the skill type**, or overrides are ignored silently:

| Skill type | Root key |
|---|---|
| Workflow / utility (pm-execute, pm-plan, pm-help, pm-sync, util-cleanup, arch-review) | `[workflow]` |
| Memory agent (l3io-sec-redteam) | `[agent]` |

See [l3io-pm-reference.md](l3io-pm-reference.md#workflow-customization) for the shipped keys and their defaults.
