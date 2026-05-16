---
name: bmad-l3io-pm-epic-execute
description: Orchestrate a complete epic execution cycle — sprints through closure reviews. Use when the user wants to 'execute an epic' or 'run an epic end-to-end'.
---

# bmad-l3io-pm-epic-execute

## Overview

Orchestrates a complete epic lifecycle — from high-level story generation and sprint planning through all closure reviews. Act as Epic Orchestrator, a lightweight traffic controller: delegate all sprint execution to `bmad-l3io-pm-sprint-execute` subagents (running headlessly, no per-sprint pause) and hold only epic/story keys, sprint groupings, and status-line summaries in context. After all sprints complete, runs epic closure: retrospective, clean release review, adversarial analysis, red-team review, UX review, architecture drift analysis, functional completeness review, auto-triage, and a closure fix loop (max 10 iterations). The epic does not close until all Critical/High/Medium issues, undocumented drift, and functional AC gaps are resolved; Low findings auto-defer to backlog. Only halts for `{user_name}` if the closure fix loop hits its 10-iteration cap.

Communicate all responses in `{communication_language}`.

## Conventions

- Bare paths (e.g. `references/sprint-execution-loop.md`) resolve from the skill root.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## On Activation

### Resolve the Workflow Block

Run: `python3 {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow`

If the script fails, resolve the `workflow` block yourself by reading `{skill-root}/customize.toml`, `{project-root}/_bmad/custom/{skill-name}.toml`, and `{project-root}/_bmad/custom/{skill-name}.user.toml` in base → team → user order. Scalars override, arrays append.

### Load Config

Load available config from `{project-root}/_bmad/config.yaml` and `{project-root}/_bmad/config.user.yaml` (root and `l3io-pm` section). Resolve:

- `user_name`, `communication_language`, `document_output_language`
- `output_folder` — default: `{project-root}/_bmad-output`
- `implementation_artifacts` — default: `{output_folder}/implementation-artifacts`
- `planning_artifacts` — default: `{output_folder}/planning-artifacts`
- `config_file` = `{project-root}/_bmad/config.yaml`
- `context_file` = `{project-root}/**/project-context.md`
- `status_file` = `{implementation_artifacts}/sprint-status.yaml`
- `arch_file` = `{planning_artifacts}/*architecture*.md`
- `prd_file` = `{planning_artifacts}/*prd*.md`
- `epics_file` = `{planning_artifacts}/*epic*.md`
- `parallel_mode` = `{workflow.parallel_mode}`
- `max_parallel_subagents` = min(`{workflow.max_parallel_subagents}`, 4)
- `date` = current date (system-generated)

### Epic Planning (Step 1)

Load `{status_file}` — extract epic and story keys with statuses only (not story content). Skim `{epics_file}` headers only — extract story keys and titles, not full content.

If the user provided an epic number, use it. Otherwise find the first epic with `in-progress` or `backlog` status that has non-done stories and confirm with `{user_name}`.

Resolve `{target_epic_padded}` as a two-digit zero-padded value. Bind and create if missing:
- `{epic_root_dir}` = `{implementation_artifacts}/epic-{target_epic_padded}`
- `{epic_closure_dir}` = `{epic_root_dir}/epic-closure`
- `{epic_test_dir}` = `{epic_root_dir}/tests`
- `{planning_epic_dir}` = `{planning_artifacts}/epic-{target_epic_padded}`

Count `{total_story_count}`, `{done_count}`, `{remaining_count}`. Build `{remaining_story_key_list}`.

Present sprint grouping proposal to `{user_name}`:
```
Epic {target_epic}: {epic_title}
Total stories:  {total_story_count}
Already done:   {done_count}
Remaining:      {remaining_count} — {remaining_story_key_list}

Default: all remaining stories as one sprint.
To split: provide story key groups (e.g. Sprint 1: 15-0, 15-1 / Sprint 2: 15-2, 15-3)
```

Wait for `{user_name}` to confirm or provide groupings. Set `{sprint_plan}` and `{total_sprint_count}`.

Update epic to `in-progress` in `{status_file}`.

### Pre-start Estimate

Compute automatically — no user prompt. For each story in `{remaining_story_key_list}`, attempt to read its file from `{planning_epic_dir}` or any existing story directories. Count acceptance criteria items and classify:
- **Simple** (1–3 ACs): ~8–12 min, ~40–70K tokens
- **Standard** (4–6 ACs): ~12–20 min, ~70–120K tokens
- **Complex** (7+ ACs or story explicitly marked as deep integration): ~20–35 min, ~120–200K tokens

If story files are not yet available, classify all as Standard. Sum story ranges, then add:
- Per-sprint closure overhead × `{total_sprint_count}`: 25–50 min, 60–120K tokens per sprint
- If `bmad-l3io-sec-agent-redteam` is installed (check `.claude/commands/bmad-l3io-sec-agent-redteam.md`): add 15–25 min, 30–60K tokens per sprint
- Epic-level closure (retro, parallel batch, arch drift, functional completeness, issue triage): 60–120 min, 100–200K tokens

Bind: `{simple_count}`, `{standard_count}`, `{complex_count}`, `{epic_est_time_low}`, `{epic_est_time_high}`, `{epic_est_tokens_low}`, `{epic_est_tokens_high}` (token values in K).

Record start timestamp: run `date +%s` and bind result to `{epic_start_ts}`.

Announce confirmed execution plan:
```
Epic Orchestrator: Execution confirmed for Epic {target_epic} — {epic_title}.
{total_sprint_count} sprint(s), {remaining_count} stories.
Each sprint runs as a fresh bmad-l3io-pm-sprint-execute subagent.
Sprint outputs: {epic_root_dir}/sprint-XX/
Epic closure outputs: {epic_closure_dir}/

Pre-start estimate:
  Stories:        {remaining_count} ({simple_count} simple, {standard_count} standard, {complex_count} complex)
  Total estimate: {epic_est_time_low}–{epic_est_time_high} min    Token estimate: {epic_est_tokens_low}K–{epic_est_tokens_high}K
  (Includes {total_sprint_count} sprint closure(s) + epic closure. Actuals reported at epic close.)

Beginning Sprint 1 of {total_sprint_count}.
```

## Stages

| # | Stage | Purpose | Location |
|---|-------|---------|----------|
| 1 | Epic planning | Config, paths, story keys, sprint grouping confirmation | SKILL.md (above) |
| 2 | Sprint execution loop | Execute each sprint as bmad-l3io-pm-sprint-execute subagent | `references/sprint-execution-loop.md` |
| 3 | Epic closure | Retro → clean release → adversarial → red team → UX → arch drift → functional completeness → issue triage → sign-off | `references/epic-closure.md` |
