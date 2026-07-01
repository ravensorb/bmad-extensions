---
name: l3io-pm-sprint-execute
description: Orchestrate a complete sprint execution cycle with quality gates. Use when the user wants to 'execute a sprint' or 'run a sprint end-to-end'.
---

# l3io-pm-sprint-execute

## Overview

Orchestrates a complete sprint lifecycle — per-story development through closure reviews. Act as Sprint Orchestrator, a lightweight traffic controller: delegate all implementation work to fresh subagents and hold only story keys, statuses, and status-line summaries in context. Each story runs through preparation → development → code review → QA → fix loop (max 10 iterations, fully autonomous). Sprint closes with retrospective, clean release review, adversarial analysis, red-team review, UX review, light architectural drift, auto-triage, and a closure fix loop (max 10 iterations). The sprint does not close until all Critical/High/Medium issues and undocumented drift are resolved; Low findings auto-defer to backlog. Only halts for `{user_name}` if a fix loop hits its 10-iteration cap.

Supports headless invocation when called by `l3io-pm-epic-execute` — receives story keys and sprint number as arguments, runs all phases, emits a structured status line on completion.

Communicate all responses in `{communication_language}`.

## HARD RULE — Estimates & Actuals

Every closeout this skill performs — **story, sprint, and the sprint retrospective** — MUST record both an `estimate` and an `actual` for all four metrics: **man-hours, compute (AI wall-clock) hours, tokens, and token cost.** This is non-negotiable. Token/cost actuals are captured **exactly** when running under Claude and as `N/A` (never guessed) under other runtimes. The full rule, runtime detection, and the exact token/cost capture procedure live in `references/metrics-contract.md` — load it at activation and follow it. Do not sign off a story or sprint with a missing estimate block, a missing actual block, a missing metric, or a guessed token/cost actual.

## Conventions

- Bare paths (e.g. `references/story-loop.md`) resolve from the skill root.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## On Activation

### Resolve the Workflow Block

Run: `python3 {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow`

If the script fails, resolve the `workflow` block yourself by reading `{skill-root}/customize.toml`, `{project-root}/_bmad/custom/{skill-name}.toml`, and `{project-root}/_bmad/custom/{skill-name}.user.toml` in base → team → user order. Scalars override, arrays append.

### First-Run Check

If `{project-root}/_bmad/config.yaml` does not have an `l3io-pm` section — or if the user passes `setup`, `configure`, or `install` as an argument — load `assets/module-setup.md` to register the module first, then continue with the resolved config values.

### Load Config

Load available config from `{project-root}/_bmad/config.yaml` and `{project-root}/_bmad/config.user.yaml` (root and `l3io-pm` section). Resolve:

- `user_name`, `communication_language`, `document_output_language`
- `output_folder` — default: `{project-root}/_bmad-output`
- `implementation_artifacts` — default: `{output_folder}/implementation-artifacts`
- `planning_artifacts` — default: `{output_folder}/planning-artifacts`
- `config_file` = `{project-root}/_bmad/config.yaml`
- `context_file` = `{project-root}/**/project-context.md`
- State files (split layout — see `references/status-files.md`):
  - `status_active` = `{implementation_artifacts}/sprint-status.yaml`
  - `status_backlog` = `{implementation_artifacts}/sprint-status-backlog.yaml`
  - `status_archived` = `{implementation_artifacts}/sprint-status-archived.yaml`
- `parallel_mode` = `{workflow.parallel_mode}`
- `max_parallel_subagents` = min(`{workflow.max_parallel_subagents}`, 4)
- `deferred_file_cleanup` = `{workflow.deferred_file_cleanup}` — default: `false`
- `calibration_granularity` = `{workflow.calibration_granularity}` — default: `"story"` (`"story"` | `"sprint"`; see `references/metrics-contract.md`)
- `date` = current date (system-generated)

### Load the Metrics Contract

Load `references/metrics-contract.md` and keep its rules in context for the whole run. Determine `{runtime}` (`claude` or `other`) using the detection in that file and bind it now — it governs how token/cost actuals are captured at every closeout.

Also load `references/status-files.md` and keep its rules in context. It governs the split state layout — which of the three files (`{status_active}`, `{status_backlog}`, `{status_archived}`) each node is read from and written to, and the node-move operations. Run its **read resolution + auto-fallback** procedure now: bind the three paths, and if only a legacy `sprint-status.yaml` exists, perform the one-time split before proceeding.

### Sprint Scope

Resolve the status files per `references/status-files.md`. Load `{status_active}` and `{status_backlog}` — extract story keys and statuses only, never file contents.

If invoked headlessly (epic number, sprint number, and story keys passed as arguments), use those directly. Otherwise, find the first in-progress or backlog epic with non-done stories (search `{status_active}` first, then `{status_backlog}`) and confirm with `{user_name}` before proceeding.

Resolve as two-digit zero-padded values: `{target_epic_padded}` (e.g. `01`, `15`) and `{target_sprint_padded}` (e.g. `01`, `02`).

Bind and create if missing:
- `{sprint_root_dir}` = `{implementation_artifacts}/epic-{target_epic_padded}/sprint-{target_sprint_padded}`
- `{story_output_dir}` = `{sprint_root_dir}/stories`
- `{closure_output_dir}` = `{sprint_root_dir}/closure`
- `{test_output_dir}` = `{sprint_root_dir}/tests`
- `{planning_sprint_dir}` = `{planning_artifacts}/epic-{target_epic_padded}/sprint-{target_sprint_padded}`
- `{cleanup_script}` = `{sprint_root_dir}/cleanup-pending.sh` (only written when `{deferred_file_cleanup}` is `true`; subagents create the file on first use — no pre-write needed)

Remove already-`done` stories from `{sprint_stories}`. Derive `{sprint_title}` = "Sprint {target_sprint} — {theme}" where `{theme}` is a 2–4 word summary of the sprint's dominant concern (e.g. "Foundation", "Parsers", "API Layer"); fall back to "Sprint {target_sprint}" if no clear theme is identifiable.

**Promote the sprint to active** (per `references/status-files.md` → Move operations): move the sprint node from the `{status_backlog}` epic shell into the epic node in `{status_active}` (creating the epic node in `{status_active}` if this is the first sprint to start under it), set `status: in-progress`, write `title: {sprint_title}` (create the field if absent), and drop the `{status_backlog}` shell once its `sprints:` list is empty. All subsequent sprint/story reads and writes target this node in `{status_active}`.

### Status Pre-check

After promoting the sprint to active, validate the current state of each story node in `{status_active}` before performing any work:

| Story status found | Action |
|---|---|
| `backlog` or `ready-for-dev` | Expected — continue normally |
| `in-progress` | Warn `{user_name}` (informational): "Story {story_key} found in-progress from a prior run — will resume from current state." Continue. |
| `done` | Already filtered out above — if it still appears in `{sprint_stories}`, remove it and log the anomaly. |
| Any other value | **Halt**: report the story key and unexpected status to `{user_name}` — wait for resolution before continuing. |

Also confirm the sprint node itself is present in `{status_active}` with `status: in-progress`. If the sprint node is missing or has a different status, halt and report to `{user_name}` before proceeding.

Log a brief pre-check summary (informational):
```
Sprint pre-check: Epic {target_epic}, Sprint {target_sprint} — status: in-progress ✓  Stories: {story_count} ({ready_count} ready, {in_progress_count} resuming)
```

### Pre-start Estimate

Compute automatically — no user prompt. Estimates follow the **bottom-up roll-up** and **decomposed calibration** defined in `references/metrics-contract.md` (the single source of truth for base bands, closure bands, the `scope`/`closure`/`fix` ratios, and the cold-start fix reserve `F`). Procedure:

1. **Classify every story up front.** For each story in `{sprint_stories}`, read its file from `{planning_sprint_dir}` or `{story_output_dir}`, count acceptance criteria, and classify: **Simple** (1–3 ACs), **Standard** (4–6 ACs), **Complex** (7+ ACs or explicit deep integration). Fall back to Standard only when a file is genuinely absent. Bind `{simple_count}`, `{standard_count}`, `{complex_count}`.

2. **Load calibration.** Read `{project-root}/_bmad/pm-calibration.yaml` if it exists; upgrade `version: 1` → `2` in place per `references/metrics-contract.md` → *migration*. Bind the `scope`, `closure`, and `fix` components. For any component with `sample_count < 3`, use cold-start defaults: `scope_ratio = 1.0`, `closure_ratio = 1.0`, `fix_mult = F = 1.25`. Bind `{cal_status}` = a short readiness string listing the components with `sample_count ≥ 3` and their ratios (e.g. `"scope.complex ×1.2 (n=4) · fix.complex ×1.5 (n=4) · closure.sprint ×1.1 (n=3)"`), or `"none yet — formula baseline (components calibrate at ≥3 samples)"` when none are ready.

3. **Per-story estimates.** For each story and each metric `m` ∈ {time_hours, man_hours, tokens_k, cost}: `story.estimate[m] = base_band(class)[m] × scope_ratio(class, m) × fix_mult(class)` (bands and `cost = tokens_k × 0.008` per metrics-contract). Write the four-metric `estimate` block + `classification` to each story node in `{status_active}` **now** — the story loop reads these, it does not recompute them. Bind `{story_time_low/high}` = Σ story `time_hours`, and the story-subtotal of each other metric, for the announcement.

4. **Sprint estimate = roll-up.** `sprint.estimate[m] = Σ story.estimate[m] + sprint_closure_band[m] × closure_ratio.sprint[m]`, adding the red-team closure row when `l3io-sec-agent-redteam` is installed (check `.claude/skills/l3io-sec-agent-redteam/SKILL.md` or `.claude/commands/l3io-sec-agent-redteam.md`). Bind `{closure_time_low/high}` = the calibrated sprint-closure time term. Write the sprint `estimate` block as this exact sum (it must reconcile to Σ stories + closure):
```yaml
estimate:
  time_hours_low: {sprint_est_time_low}     # Σ story time + calibrated sprint-closure band (hours)
  time_hours_high: {sprint_est_time_high}
  tokens_k_min: {sprint_est_tokens_low}     # Σ story tokens + calibrated closure (K)
  tokens_k_max: {sprint_est_tokens_high}
  cost_low: '{sprint_est_cost_low}'         # derived from tokens at $8/MTok
  cost_high: '{sprint_est_cost_high}'
  man_hours_low: {sprint_est_man_low}       # traditional dev equivalent (person-hours)
  man_hours_high: {sprint_est_man_high}
```

5. **Record start timestamp:** run `date +%s` and bind `{sprint_start_ts}` (OS-aware — on a PowerShell harness use `[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()`; see `references/metrics-contract.md` → Recording timestamps).

**Headless mode (invoked by `l3io-pm-epic-execute`):** skip the scope confirmation entirely. Announce scope as a one-line log and continue immediately — the epic orchestrator already obtained user confirmation upstream.

**Interactive mode (invoked directly by `{user_name}`):** announce scope and wait for `{user_name}` confirmation before proceeding:
```
Sprint Orchestrator: Epic {target_epic}, Sprint {target_sprint} — {story_count} stories: {story_key_list}
Per story:  Story Prep → Dev → Code Review → QA → Fix Loop
Closure:    Retrospective → Clean Release → Adversarial → Red Team → UX → Arch Drift → Issue Triage
State passes through disk only. All phases use fresh subagents.

Pre-start estimate:
  Stories:         {story_count} ({simple_count} simple · {standard_count} standard · {complex_count} complex)
  Per-story cost:  Simple ~$0.32–$0.56 · Standard ~$0.56–$0.96 · Complex ~$0.96–$1.60  (Sonnet ~$8/MTok blended)
  Est. story work: {story_time_low}–{story_time_high} h   (Σ stories, fix reserve included)
  Est. closure:    {closure_time_low}–{closure_time_high} h
  ────────────────────────────────────────────────────────────────────────────────────
  Total estimate:  {sprint_est_time_low}–{sprint_est_time_high} hours    Tokens: {sprint_est_tokens_low}K–{sprint_est_tokens_high}K    Cost: ~{sprint_est_cost_low}–{sprint_est_cost_high}
  Traditional est: ~{sprint_est_man_low}–{sprint_est_man_high} hours  (actual auto-computed at sprint close)
  Calibration:     {cal_status}
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

State is split across three files — `{status_active}`, `{status_backlog}`, `{status_archived}` — see `references/status-files.md` for **which file** each node lives in and the move operations. Every node uses the **same per-node structure** below regardless of which file it currently lives in; the split changes placement, not field shape. Fields marked *(written by sprint-execute)* are populated by this skill; all others are pre-existing or written by epic-execute.

```yaml
epics:
- id: '01'
  title: 'Epic 01 — ...'           # written by epic-execute
  goal: '...'                       # written by epic-execute
  status: in-progress               # written by epic-execute
  closed: '2026-05-18'             # written by epic-execute at close
  retrospective: path/to/retro.md  # written by epic-execute at close
  estimate:                         # written by epic-execute — roll-up: Σ sprint.estimate + calibrated epic-closure band
    time_hours_low: 3.0
    time_hours_high: 5.7
    tokens_k_min: 800
    tokens_k_max: 1600
    cost_low: '$6.40'
    cost_high: '$12.80'
    man_hours_low: 120
    man_hours_high: 240
  actual:                           # written by epic-execute at close (ALL FOUR metrics, HARD RULE)
    elapsed_hours: 4.1
    man_hours: 4.1                  # auto-computed: sum of sprint actual.man_hours + 12h epic closure
    tokens_k: 1180                  # sum of sprint actual.tokens_k (skip/N/A any non-numeric sprint values)
    cost: '$7.85'                   # sum of sprint actual.cost; 'N/A' if no sprint reported a numeric cost
  sprints:
  - id: '01'
    title: 'Sprint 01 — Foundation' # *(written by sprint-execute at in-progress)*
    status: done                    # *(written by sprint-execute)*
    closed: '2026-05-18'           # *(written by sprint-execute at sign-off)*
    retrospective: path/to/retro.md # *(written by sprint-execute at sign-off)*
    estimate:                       # *(written by sprint-execute — roll-up: Σ story.estimate + calibrated closure band)*
      time_hours_low: 0.8           # AI-assisted wall-clock time (hours)
      time_hours_high: 1.4
      tokens_k_min: 250
      tokens_k_max: 480
      cost_low: '$2.00'
      cost_high: '$3.84'
      man_hours_low: 40             # traditional dev equivalent (person-hours)
      man_hours_high: 80
    actual:                         # *(written by sprint-execute at sign-off — ALL FOUR metrics, HARD RULE)*
      elapsed_hours: 1.1            # AI-assisted wall-clock actual (measured)
      man_hours: 52.5               # auto-computed: sum of (classification base × fix_factor) + 24h closure
      tokens_k: 312                 # exact under Claude (transcript usage); 'N/A' under other runtimes — never guessed
      cost: '$2.05'                 # derived from real tokens × model rate; 'N/A' when tokens_k is N/A
    stories:
    - key: PROJ-E01-S01-ST01
      title: 'Story title...'       # *(written by sprint-execute at ready-for-dev)*
      status: done                  # *(written by sprint-execute)*
      classification: complex       # *(written by sprint-execute at pre-start classification)*
      estimate:                     # *(written at pre-start: base_band × scope_ratio × fix reserve, per metrics-contract — HARD RULE)*
        time_hours_low: 0.3
        time_hours_high: 0.6
        tokens_k_min: 120
        tokens_k_max: 200
        cost_low: '$0.96'
        cost_high: '$1.60'
        man_hours_low: 24           # traditional dev equivalent (person-hours)
        man_hours_high: 48
      actual:                       # *(written by sprint-execute at done — ALL FOUR metrics, HARD RULE)*
        elapsed_hours: 0.4          # measured: story dev→done wall-clock
        man_hours: 30               # auto-computed: classification base × fix_factor
        tokens_k: 168               # exact under Claude (story window); 'N/A' under other runtimes
        cost: '$1.10'               # derived from real tokens × model rate; 'N/A' when tokens_k is N/A
      completion_evidence:          # *(written by sprint-execute at done)*
        fix_iterations: 2
        tests_passing: 42
        files_changed: 8
        bugs_fixed:                 # omitted when fix_iterations == 0
        - 'Brief description of fix'
```

Deferred issues are **not** nested under the epic anymore. They go to the consolidated
`backlog:` list at the top level of `{status_backlog}` (tagged with `epic`/`sprint`) —
see `references/status-files.md` → Consolidated backlog item schema.

**Supporting references** (loaded by story-loop.md):

| Reference | Purpose |
|-----------|---------|
| `references/metrics-contract.md` | **HARD RULE** for estimates + actuals (all four metrics at story/sprint/retro), runtime detection, and the exact token/cost capture procedure |
| `references/testing-guidelines.md` | Unit test quality review and test output caching guidance for dev and QA subagents |
| `references/cicd-guidelines.md` | CI/CD pipeline conventions (modular design, action pinning, multi-runner compatibility, nektos/act, LiquidLogicLabs) — passed to dev subagents when stories involve pipeline work |
