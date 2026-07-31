---
name: l3io-pm-plan-execution
description: Analyze epics and dependencies into a phased parallel execution plan. Use when the user says 'plan execution', 'generate execution plan', 'plan these epics', or 'how should I run these epics'.
---

# l3io-pm-plan-execution

## Overview

Reads epic state and `depends_on` declarations from the split status files and produces a phased, parallel-optimized execution plan: which epics can run concurrently, the critical path with wall-clock estimates, and ready-to-run `/l3io-pm-epic-execute` dispatch commands. No work is executed — this is a planning-only skill.

**Scope** (pass as arguments — default is all non-done epics):
- `--epics E01,E02` — named epics only (comma- or space-separated)
- `--stories E01-S01-001,E02-S01-003` — named story keys; their owning epics become the scope

Communicate all responses in `{communication_language}`.

## Conventions

- Bare paths (e.g. `references/status-files.md`) resolve from the skill root.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## On Activation

### Step 1: Resolve the Workflow Block

Run: `python3 {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow`

If the script fails, resolve the `workflow` block yourself by reading these three files in base → team → user order: `{skill-root}/customize.toml`, `{project-root}/_bmad/custom/{skill-name}.toml`, `{project-root}/_bmad/custom/{skill-name}.user.toml`. Scalars override, tables deep-merge, arrays of tables keyed by `code`/`id` replace matching entries and append new ones, all other arrays append.

### Step 2: Execute Prepend Steps

Execute each entry in `{workflow.activation_steps_prepend}` in order.

### Step 3: Load Persistent Facts

Treat every entry in `{workflow.persistent_facts}` as foundational context for the whole run. `file:` entries are paths or globs — load the referenced contents as facts.

### Step 4: Load Config

Load config from `{project-root}/_bmad/config.yaml` and `{project-root}/_bmad/config.user.yaml` (root and `l3io-pm` section). If no `l3io-pm` section exists, inform the user to run `/l3io-pm-sprint-execute setup` first and exit.

Resolve:
- `user_name`, `communication_language`
- `output_folder` — default: `{project-root}/_bmad-output`
- `implementation_artifacts` — default: `{output_folder}/implementation-artifacts`
- `planning_artifacts` — default: `{output_folder}/planning-artifacts`
- `status_active` = `{implementation_artifacts}/sprint-status.yaml`
- `status_backlog` = `{implementation_artifacts}/sprint-status-backlog.yaml`
- `status_archived` = `{implementation_artifacts}/sprint-status-archived.yaml`
- `date` = current date (system-generated)

Load `references/status-files.md` — keep its split-state placement rules in context for all reads.

### Step 5: Execute Append Steps

Execute each entry in `{workflow.activation_steps_append}` in order.

## Scope Resolution

Parse activation arguments to bind `{target_epics}`:
- `--epics E01,E02` → `{target_epics}` = those keys
- `--stories E01-S01-001,E02-S01-003` → derive owning epic from each key's prefix (`E01-*` → `E01`); `{target_epics}` = the resulting epic key set
- No args → `{target_epics}` = all epics in `{status_active}` and `{status_backlog}` with `status: backlog` or `status: in-progress`

If `{target_epics}` is empty after resolution, report "No in-scope epics found" and exit.

## Load State

Read from the split status files per `references/status-files.md` placement rules. For each epic in `{target_epics}`: load `key`, `title`, `status`, `depends_on`, and for each story: `key`, `classification`, `depends_on`. Check `{status_active}` first, then `{status_backlog}` for any not found there. Load `{status_archived}` only to verify whether a referenced prerequisite is `status: done`.

## Build Dependency Graph

For each epic in `{target_epics}`, collect directed edges (this epic ← prerequisite):

1. **Epic-level**: each entry in the epic's `depends_on: []`
2. **Story-level rollup**: for each story's `depends_on: []` entry, derive the owning epic from the story key prefix (`E01-*` → `E01`); if that epic differs from the current epic, add an edge from the current epic to that prerequisite epic. Deduplicate all edges.

For any prerequisite epic not in `{target_epics}`:
- If `status: done` in `{status_archived}` → prerequisite already satisfied; omit the edge
- Otherwise → warn the user and either expand scope to include it or flag it as an unmet external dependency

**Cycle detection**: verify the graph is a DAG before proceeding. If a cycle exists, report the full cycle path (e.g. `E01 → E03 → E01`) and exit.

## Phase Assignment

Topologically sort the dependency graph. Assign each epic a phase number equal to the length of its longest prerequisite chain + 1 (roots are phase 1). Epics at the same phase number with no mutual dependency may execute in parallel within that phase.

## Estimate per Phase

If `{workflow.include_estimates}` is `true`:

For each epic, compute a wall-clock estimate by summing its stories:
- Cold-start base bands per story: **Simple** 4–6h, **Standard** 8–12h, **Complex** 16–24h
- If `{project-root}/_bmad/pm-calibration.yaml` exists with ≥3 scope samples for a classification, apply the learned `scope_ratio` to the base band
- Add sprint closure (2–4h per sprint) and epic closure (4–8h per epic) overhead
- Default unclassified stories to **Standard**

Phase wall-clock = the max epic estimate within the phase (epics run in parallel). Critical path = the sequence of phases whose max-epic estimates sum to the highest total.

## Generate Plan

Produce the execution plan covering: one section per phase with its parallel-or-sequential label, each epic's key, title, story counts by classification, wall-clock estimate range, and dependency list; the critical path as a chain of epic keys with cumulative estimate; and, if `{workflow.include_dispatch_lines}` is `true`, `/l3io-pm-epic-execute {key}` lines grouped by phase with a comment indicating phases that can run in parallel.

If `{workflow.plan_output}` is `"markdown"`: save to `{planning_artifacts}/execution-plan-{date}.md`. If a file for today already exists, append a sequence suffix (`-2`, `-3`, etc.). Display the output path to `{user_name}`.

End with:
```
DONE — execution plan: {phase_count} phases, {epic_count} epics, critical path ~{low}–{high}h wall-clock
```
or `BLOCKED: [one-line reason]`
