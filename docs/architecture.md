# Architecture

Execution model and design principles for `bmad-l3io-extensions`.

## Context Boundary Principle

The core design rule: **one phase = one fresh subagent; all state passes through disk.**

No subagent receives conversation history from the orchestrator or from a sibling subagent. Each subagent starts clean, reads what it needs from disk (config files, story files, status file), does its work, writes outputs to disk, and terminates with a single status line.

This is not just a performance optimization. It prevents context contamination — where earlier work influences later analysis in ways that reduce quality or introduce inconsistency. A code reviewer that has watched the development process will rationalize what it sees. A fresh code reviewer applies consistent standards.

The same principle applies to `l3io-sec`: the agent's memory is disk-based (its sanctum) precisely so that each session starts with a deliberate reload, not an inherited in-context state.

## Module Relationships

```
l3io-pm-epic-execute
    |
    |-- spawns --> l3io-pm-sprint-execute (one per sprint, headless)
                       |
                       |-- spawns --> l3io-sec-agent-redteam (closure Step 6, if installed)
                       |-- spawns --> bmad-* skills (per phase)

l3io-sec-agent-redteam  (also invocable standalone)

l3io-util-cleanup       (standalone only — no orchestrator relationship)

l3io-arch-review        (standalone only — new-project design, review audits, ADR decisions)
```

`l3io-sec` is optionally dependent on `l3io-pm` at runtime (called during closure), but has no build-time or config dependency. It runs standalone and only uses the l3io-pm config section if l3io-pm has already been configured.

`l3io-arch` is fully standalone — no orchestrator relationship and no runtime dependency on the other modules. It carries the engineering-standards charter (`references/standards-*.md`) and is designed to also be wired into core `bmad-architect` and `bmad-code-review` via `bmad-customize`, so the standards apply automatically during design and review without forking those core skills.

## Orchestrator Pattern

The orchestrators (`l3io-pm-sprint-execute`, `l3io-pm-epic-execute`) act as traffic controllers, not implementers. Their context holds only:

- Story keys and statuses from the sprint status files (`sprint-status.yaml` and `sprint-status-backlog.yaml`)
- Status-line summaries returned by subagents
- Path bindings (no file contents)

They never read story file contents into their own context. When a story file is needed, they pass its path to a subagent — the subagent reads it. This keeps the orchestrator context small and focused regardless of how many stories or how large each story file grows.

Subagent prompts are self-contained: they include config file paths, relevant artifact paths, the skill to invoke, and expected output format. They carry nothing implicit.

## State Contract

The sprint status is the single source of truth for story and epic lifecycle, split across three files in `{implementation_artifacts}/`:

- `sprint-status.yaml` — epics with `status: in-progress` only, carrying their in-progress and done sprints and all their stories. (Old repos using `sprint-status-active.yaml` are auto-renamed on first PM-skill run.)
- `sprint-status-backlog.yaml` — all not-yet-started work (whole `backlog`-status epics, plus the not-yet-started sprints of in-progress epics held under an epic "shell"), plus a consolidated top-level `backlog:` deferred-issue list across all epics (each item tagged with `epic` and `sprint` keys).
- `sprint-status-archived.yaml` — epics with `status: done`, moved here wholesale at epic close.

Placement granularity is epic + sprint (stories always travel inside their owning sprint node); archiving happens only at epic close (done sprints stay in the active file until their whole epic closes). The single source of truth for the placement rule, node-move operations, and read/auto-fallback procedure is each PM skill's `references/status-files.md`. A legacy single `sprint-status.yaml` is auto-detected and split on first run (the original is renamed to `sprint-status.yaml.legacy`).

**Who reads it:** Both execute skills read the active + backlog files on activation to identify scope and current state.

**Who writes it:** The orchestrator writes to the status files after each status transition. Subagents do not write to the status files — they notify the orchestrator via status line, and the orchestrator updates the files.

**Concurrency rule:** No two subagents write to the sprint status files concurrently. Before each parallel batch, the orchestrator verifies this constraint; if uncertain, it runs sequentially.

Story status lifecycle:

```
backlog  →  ready-for-dev  →  in-progress  →  review  →  done
```

Epic status lifecycle: `backlog → in-progress → done`

A sprint is in-progress when the orchestrator sets it to `in-progress` in the status file at the start of execution. It transitions to `done` only at sign-off, after all quality gates pass.

## Artifact Directory Structure

All runtime artifacts use zero-padded two-digit epic/sprint numbers. The full canonical layout:

```
{implementation_artifacts}/
  sprint-status.yaml
  sprint-status-backlog.yaml
  sprint-status-archived.yaml
  epic-01/
    sprint-01/
      stories/
        1-0-feature-name.md
        1-1-another-feature.md
      closure/
        epic-01-sprint-01-retro-2026-05-15.md
        epic-01-sprint-01-clean-release-2026-05-15.md
        epic-01-sprint-01-adversarial-2026-05-15.md
        epic-01-sprint-01-redteam-2026-05-15.md
        epic-01-sprint-01-ux-review-2026-05-15.md
        epic-01-sprint-01-arch-drift-2026-05-15.md
      tests/
        epic-01-sprint-01-1-0-qa-2026-05-15.md
    sprint-02/
      ...
    epic-closure/
      epic-01-retro-2026-05-15.md
      epic-01-adversarial-2026-05-15.md
      epic-01-redteam-2026-05-15.md
      epic-01-arch-drift-2026-05-15.md
      epic-01-functional-completeness-2026-05-15.md
    tests/
      epic-01-fix-verification-2026-05-15.md

{planning_artifacts}/
  epic-01/
    sprint-01/
      stories/
    epic-name-prd.md
    epic-name-architecture.md
    epic-name-epics.md
```

This structure is enforced by the orchestrators (they create missing directories on activation) and verified by `l3io-util-cleanup` (which migrates legacy flat layouts into it).

## Adaptive Parallelism

Default execution is sequential. Parallelism is used only when safe.

### When parallel execution is used

- `l3io-pm-sprint-execute`: stories within a sprint can run in parallel across independent stories
- `l3io-pm-epic-execute`: sprints can run in parallel when sprint groups are independent; closure Step 4 (clean release, adversarial, red team, UX) runs as a parallel batch after the sequential retrospective

### Three pre-flight checks

Before each parallel batch, the orchestrator verifies:

1. **No shared file paths** — no two concurrent subagents write to the same file path
2. **No concurrent status file writes** — the sprint status files (`sprint-status.yaml`, `sprint-status-backlog.yaml`, `sprint-status-archived.yaml`) are written only by the orchestrator, not subagents, but the orchestrator must not merge conflicting updates
3. **No unresolved blockers** — a blocker in one subagent could invalidate the work of its siblings

If any check is uncertain, the orchestrator runs sequentially.

### Hard cap

`effective_parallel_subagents` = min(`max_parallel_subagents`, 4, `safe_batch_size`)

The hard cap of 4 applies regardless of the `max_parallel_subagents` setting. Setting `parallel_mode = off` in `customize.toml` forces sequential execution (effective value = 1).

### Story dependencies

Story files may contain a `depends_on` field. A story cannot enter development until all declared dependencies are `done`. The orchestrator checks `depends_on` before building parallel batches and only groups independent stories together.

## Quality Gate Contracts

### Sprint quality gate

The sprint does not close (Step 10 sign-off does not execute) until all **Critical, High, and Medium** findings from all closure phases — plus all undocumented architecture drift — are either:

- Fixed and verified (fix subagent + QA verification subagent confirms tests pass), or
- Explicitly accepted by `{user_name}` with documented rationale (only after the closure fix loop hits its 10-iteration cap)

Low findings are auto-deferred to backlog (one `bmad-create-story` per item, no prompt). The sprint signs off with the deferred story keys listed. The auto-triage step files findings to fix-now vs. defer-to-backlog without per-item user prompts; the closure fix loop iterates fix → QA → re-check up to 10 times before halting.

### Epic quality gate

The epic does not close (Step 8 sign-off does not execute) until all of the following are resolved:

- All Critical, High, and Medium findings from all epic closure phases
- All undocumented architecture drift findings (fix the code or document the rationale in the affected story's Dev Agent Record)
- All functional completeness AC gaps (implement the missing AC or defer with documented rationale)

Low findings auto-defer to backlog. Spec gaps (architecture or PRD was silent) trigger an automatic documentation update under `{planning_epic_dir}` with no code change. The closure fix loop iterates fix → QA → re-check up to 10 times before halting for `{user_name}` input.

## Subagent Invocation

**Preferred method:** Agent tool with a self-contained prompt. No conversation history is forwarded — only paths, keys, and the skill name to invoke.

**Fallback:** `claude --print` with a heredoc prompt, used when the Agent tool is unavailable.

Every subagent must end with exactly one status line in one of these forms:

```
DONE — [brief metrics]
BLOCKED: [one-line reason]
FAILED: [one-line reason]
```

The orchestrator reads this status line to determine next steps. If a subagent ends with BLOCKED or FAILED, the orchestrator halts and surfaces the reason to the user before proceeding.

In headless sprint execution (called by epic orchestrator), the sprint skill emits a richer DONE line that the epic orchestrator uses to populate its `{sprint_summaries}`:

```
DONE — Stories: N, Issues resolved: N, Issues deferred: N, Retro: [path], Time: ~Nmin (est L–Hmin)
```

## Customization Model

Each execute skill ships with a `customize.toml` at its skill root. Overrides layer in this order:

```
{skill-root}/customize.toml          (base — shipped with the skill, don't edit)
    ↓ override
{project-root}/_bmad/custom/{skill-name}.toml     (team overrides — commit to repo)
    ↓ override
{project-root}/_bmad/custom/{skill-name}.user.toml  (personal overrides — gitignore)
```

Scalar values override. Array values append.

The `resolve_customization.py` script handles the merge on activation. If the script fails, the skill falls back to manual resolution: reading the three files in order and applying the same precedence rules.

**Team override example** — set a shared parallel mode for the whole project:

`_bmad/custom/l3io-pm-sprint-execute.toml`:
```toml
[workflow]
parallel_mode = "off"
```

**Personal override example** — increase parallelism for a fast local machine:

`_bmad/custom/l3io-pm-sprint-execute.user.toml`:
```toml
[workflow]
max_parallel_subagents = 3
```
