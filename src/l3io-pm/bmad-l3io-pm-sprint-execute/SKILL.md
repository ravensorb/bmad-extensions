---
name: bmad-l3io-pm-sprint-execute
description: Orchestrate a complete sprint execution cycle with quality gates. Use when the user wants to 'execute a sprint' or 'run a sprint end-to-end'.
---

# bmad-l3io-pm-sprint-execute

## Overview

Orchestrates a complete sprint lifecycle — per-story development through closure reviews. Act as Sprint Orchestrator, a lightweight traffic controller: delegate all implementation work to fresh subagents and hold only story keys, statuses, and status-line summaries in context. Each story runs through preparation → development → code review → QA → fix loop (max 10 iterations, fully autonomous). Sprint closes with retrospective, clean release review, adversarial analysis, red-team review, UX review, light architectural drift, auto-triage, and a closure fix loop (max 10 iterations). The sprint does not close until all Critical/High/Medium issues and undocumented drift are resolved; Low findings auto-defer to backlog. Only halts for `{user_name}` if a fix loop hits its 10-iteration cap.

Supports headless invocation when called by `bmad-l3io-pm-epic-execute` — receives story keys and sprint number as arguments, runs all phases, emits a structured status line on completion.

Communicate all responses in `{communication_language}`.

## Conventions

- Bare paths (e.g. `references/story-loop.md`) resolve from the skill root.
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
- `parallel_mode` = `{workflow.parallel_mode}`
- `max_parallel_subagents` = min(`{workflow.max_parallel_subagents}`, 4)
- `deferred_file_cleanup` = `{workflow.deferred_file_cleanup}` — default: `false`
- `date` = current date (system-generated)

### Sprint Scope

Load `{status_file}` — extract story keys and statuses only, never file contents.

If invoked headlessly (epic number, sprint number, and story keys passed as arguments), use those directly. Otherwise, find the first in-progress or backlog epic with non-done stories and confirm with `{user_name}` before proceeding.

Resolve as two-digit zero-padded values: `{target_epic_padded}` (e.g. `01`, `15`) and `{target_sprint_padded}` (e.g. `01`, `02`).

Bind and create if missing:
- `{sprint_root_dir}` = `{implementation_artifacts}/epic-{target_epic_padded}/sprint-{target_sprint_padded}`
- `{story_output_dir}` = `{sprint_root_dir}/stories`
- `{closure_output_dir}` = `{sprint_root_dir}/closure`
- `{test_output_dir}` = `{sprint_root_dir}/tests`
- `{planning_sprint_dir}` = `{planning_artifacts}/epic-{target_epic_padded}/sprint-{target_sprint_padded}`
- `{cleanup_script}` = `{sprint_root_dir}/cleanup-pending.sh` (only written when `{deferred_file_cleanup}` is `true`; subagents create the file on first use — no pre-write needed)

Remove already-`done` stories from `{sprint_stories}`. Derive `{sprint_title}` = "Sprint {target_sprint} — {theme}" where `{theme}` is a 2–4 word summary of the sprint's dominant concern (e.g. "Foundation", "Parsers", "API Layer"); fall back to "Sprint {target_sprint}" if no clear theme is identifiable. Update the sprint node in `{status_file}`: set `status: in-progress`, write `title: {sprint_title}` (create the field if absent).

### Pre-start Estimate

Compute automatically — no user prompt. For each story in `{sprint_stories}`, attempt to read its file from `{planning_sprint_dir}` or `{story_output_dir}`. Count acceptance criteria items and classify:
- **Simple** (1–3 ACs): ~8–12 min, ~40–70K tokens
- **Standard** (4–6 ACs): ~12–20 min, ~70–120K tokens
- **Complex** (7+ ACs or story explicitly marked as deep integration): ~20–35 min, ~120–200K tokens

If story files are not yet available, classify all as Standard. Sum ranges across all stories to get story subtotals. Then add closure overhead:
- Base closure (retro, clean release, adversarial, UX, arch drift, issue triage): 25–50 min, 60–120K tokens
- If `bmad-l3io-sec-agent-redteam` is installed (check `.claude/skills/bmad-l3io-sec-agent-redteam/SKILL.md` or `.claude/commands/bmad-l3io-sec-agent-redteam.md`): add 15–25 min, 30–60K tokens

Bind: `{simple_count}`, `{standard_count}`, `{complex_count}`, `{story_time_low}`, `{story_time_high}`, `{closure_time_low}`, `{closure_time_high}`, `{est_time_low}`, `{est_time_high}`, `{est_tokens_low}`, `{est_tokens_high}` (token values in K).

Compute cost estimates using a blended rate of **$8/MTok** (Sonnet input ~$3/MTok, output ~$15/MTok, ~60/40 split):
- `{est_cost_low}` = `{est_tokens_low}` × 0.008  (formatted as `$X.XX`)
- `{est_cost_high}` = `{est_tokens_high}` × 0.008 (formatted as `$X.XX`)

Per-story cost reference (for announcement):
- Simple (40–70K tokens): ~$0.32–$0.56
- Standard (70–120K tokens): ~$0.56–$0.96
- Complex (120–200K tokens): ~$0.96–$1.60

Compute traditional development equivalents — estimated person-hours a dev team would spend on the same scope without AI tooling (developer + code review + QA per story, plus manual closure overhead):
- Simple story: 4–8 person-hours · Standard: 12–24 · Complex: 24–48
- Closure overhead: 16–32 person-hours (retro, arch review, QA pass, security review)

Bind:
- `{man_hours_low}` = (`{simple_count}` × 4) + (`{standard_count}` × 12) + (`{complex_count}` × 24) + 16
- `{man_hours_high}` = (`{simple_count}` × 8) + (`{standard_count}` × 24) + (`{complex_count}` × 48) + 32

Record start timestamp: run `date +%s` and bind result to `{sprint_start_ts}`.

Compute `{est_time_hours_low}` = round(`{est_time_low}` / 60, 1) and `{est_time_hours_high}` = round(`{est_time_high}` / 60, 1).

Write the `estimate` block to the sprint node in `{status_file}`:
```yaml
estimate:
  time_hours_low: {est_time_hours_low}    # AI-assisted wall-clock time (hours)
  time_hours_high: {est_time_hours_high}
  tokens_k_min: {est_tokens_low}
  tokens_k_max: {est_tokens_high}
  cost_low: '{est_cost_low}'
  cost_high: '{est_cost_high}'
  man_hours_low: {man_hours_low}          # traditional dev equivalent (person-hours)
  man_hours_high: {man_hours_high}
```

**Headless mode (invoked by `bmad-l3io-pm-epic-execute`):** skip the scope confirmation entirely. Announce scope as a one-line log and continue immediately — the epic orchestrator already obtained user confirmation upstream.

**Interactive mode (invoked directly by `{user_name}`):** announce scope and wait for `{user_name}` confirmation before proceeding:
```
Sprint Orchestrator: Epic {target_epic}, Sprint {target_sprint} — {story_count} stories: {story_key_list}
Per story:  Story Prep → Dev → Code Review → QA → Fix Loop
Closure:    Retrospective → Clean Release → Adversarial → Red Team → UX → Arch Drift → Issue Triage
State passes through disk only. All phases use fresh subagents.

Pre-start estimate:
  Stories:         {story_count} ({simple_count} simple · {standard_count} standard · {complex_count} complex)
  Per-story cost:  Simple ~$0.32–$0.56 · Standard ~$0.56–$0.96 · Complex ~$0.96–$1.60  (Sonnet ~$8/MTok blended)
  Est. story time: {story_time_low}–{story_time_high} min
  Est. closure:    {closure_time_low}–{closure_time_high} min
  ────────────────────────────────────────────────────────────────────────────────────
  Total estimate:  {est_time_hours_low}–{est_time_hours_high} hours    Tokens: {est_tokens_low}K–{est_tokens_high}K    Cost: ~{est_cost_low}–{est_cost_high}
  Traditional est: ~{man_hours_low}–{man_hours_high} hours  (actual auto-computed at sprint close)
  (Actuals reported at sprint close. Per-story fix loop and closure fix loop each cap at 10 iterations
  before prompting; Critical/High/Medium and undocumented drift findings auto-fix without per-item prompts.)

Shall I begin? (yes / cancel)
```
Wait for `{user_name}`'s response before any subagent is spawned.

## Stages

| # | Stage | Purpose | Location |
|---|-------|---------|----------|
| 1 | Activation | Config, paths, scope identification | SKILL.md (above) |
| 2 | Per-story execution | Story prep → dev → code review → QA → fix loop, with adaptive parallelism | `references/story-loop.md` |
| 3 | Sprint closure | Retro → clean release → adversarial → red team → UX → arch drift → issue triage → sign-off | `references/sprint-closure.md` |

## Sprint Status File Schema

The `{status_file}` uses the following structure. Fields marked *(written by sprint-execute)* are populated by this skill; all others are pre-existing or written by epic-execute.

```yaml
epics:
- id: '01'
  title: 'Epic 01 — ...'           # written by epic-execute
  goal: '...'                       # written by epic-execute
  status: in-progress               # written by epic-execute
  closed: '2026-05-18'             # written by epic-execute at close
  retrospective: path/to/retro.md  # written by epic-execute at close
  estimate:                         # written by epic-execute after pre-start estimate
    time_hours_low: 3.0
    time_hours_high: 5.7
    tokens_k_min: 800
    tokens_k_max: 1600
    cost_low: '$6.40'
    cost_high: '$12.80'
    man_hours_low: 120
    man_hours_high: 240
  actual:                           # written by epic-execute at close
    elapsed_hours: 4.1
    man_hours: 4.1                  # auto-computed: sum of sprint actual.man_hours + 12h epic closure
  sprints:
  - id: '01'
    title: 'Sprint 01 — Foundation' # *(written by sprint-execute at in-progress)*
    status: done                    # *(written by sprint-execute)*
    closed: '2026-05-18'           # *(written by sprint-execute at sign-off)*
    retrospective: path/to/retro.md # *(written by sprint-execute at sign-off)*
    estimate:                       # *(written by sprint-execute after pre-start estimate)*
      time_hours_low: 0.8           # AI-assisted wall-clock time (hours)
      time_hours_high: 1.4
      tokens_k_min: 250
      tokens_k_max: 480
      cost_low: '$2.00'
      cost_high: '$3.84'
      man_hours_low: 40             # traditional dev equivalent (person-hours)
      man_hours_high: 80
    actual:                         # *(written by sprint-execute at sign-off)*
      elapsed_hours: 1.1            # AI-assisted wall-clock actual
      man_hours: 52.5               # auto-computed: sum of (classification base × fix_factor) + 24h closure
    stories:
    - key: PROJ-E01-S01-ST01
      title: 'Story title...'       # *(written by sprint-execute at ready-for-dev)*
      status: done                  # *(written by sprint-execute)*
      classification: complex       # *(written by sprint-execute at ready-for-dev)*
      completion_evidence:          # *(written by sprint-execute at done)*
        fix_iterations: 2
        tests_passing: 42
        files_changed: 8
        bugs_fixed:                 # omitted when fix_iterations == 0
        - 'Brief description of fix'
  backlog:                          # *(appended by sprint-execute / epic-execute during issue triage)*
  - key: PROJ-E01-BL-01
    title: 'Issue title'
    source: 'adversarial (ADV-L-01)'
    severity: Low
    status: backlog
    description: 'One-sentence description of the deferred issue.'
    resolved: '2026-05-19'        # added when a backlog item is later fixed
    resolution: 'How it was fixed.' # added when a backlog item is later fixed
```

**Supporting references** (loaded by story-loop.md):

| Reference | Purpose |
|-----------|---------|
| `references/testing-guidelines.md` | Unit test quality review and test output caching guidance for dev and QA subagents |
| `references/cicd-guidelines.md` | CI/CD pipeline conventions (modular design, action pinning, multi-runner compatibility, nektos/act, LiquidLogicLabs) — passed to dev subagents when stories involve pipeline work |
