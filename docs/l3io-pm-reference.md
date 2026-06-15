# l3io-pm Reference

Full reference for the PM orchestration module — three skills that orchestrate a complete delivery lifecycle from story preparation through epic closure.

## Skills Overview

| Skill | Role |
|-------|------|
| `bmad-l3io-pm-sprint-execute` | Orchestrates a single sprint: per-story phases plus sprint closure reviews |
| `bmad-l3io-pm-epic-execute` | Orchestrates a full epic: delegates to `bmad-l3io-pm-sprint-execute` subagents, then runs epic closure |

`bmad-l3io-pm-epic-execute` is a wrapper around `bmad-l3io-pm-sprint-execute`. It handles sprint grouping, delegates each sprint headlessly, and runs a second level of closure reviews after all sprints complete.

## Configuration

Both execute skills read config from `{project-root}/_bmad/config.yaml` and `{project-root}/_bmad/config.user.yaml` on activation. If values are absent, defaults are used.

### Config files

| File | Contents |
|------|----------|
| `{project-root}/_bmad/config.yaml` | Shared project settings — `output_folder`, `document_output_language`, and the `l3io-pm` module section |
| `{project-root}/_bmad/config.user.yaml` | Personal settings — `user_name`, `communication_language`. Add to `.gitignore` |

### Config variables

| Variable | Section | Default | Description |
|----------|---------|---------|-------------|
| `user_name` | user config | BMad | Name used when the skill addresses the user |
| `communication_language` | user config | English | Language for all skill responses |
| `document_output_language` | config.yaml root | English | Language for written artifacts |
| `output_folder` | config.yaml root | `{project-root}/_bmad-output` | Root directory for all generated output |
| `implementation_artifacts` | l3io-pm section | `{output_folder}/implementation-artifacts` | Root for stories, closure outputs, and tests |
| `planning_artifacts` | l3io-pm section | `{output_folder}/planning-artifacts` | Root for planning documents |

### Workflow customization

Each execute skill ships with a `customize.toml` at `{skill-root}/customize.toml`. Override values are layered in this order (last wins):

1. `{skill-root}/customize.toml` — base defaults shipped with the skill
2. `{project-root}/_bmad/custom/{skill-name}.toml` — team overrides (commit to repo)
3. `{project-root}/_bmad/custom/{skill-name}.user.toml` — personal overrides (gitignore)

| Key | Default | Description |
|-----|---------|-------------|
| `parallel_mode` | `adaptive` | `adaptive` allows parallel story execution when safe; `off` forces sequential |
| `max_parallel_subagents` | `2` | Maximum concurrent subagents (hard capped at 4 regardless of this value) |

## Sprint Execute Reference

### Activation

On activation, the skill:

1. Resolves the workflow block from `customize.toml` (base → team → user)
2. Loads config from `_bmad/config.yaml` and `_bmad/config.user.yaml`
3. Reads the sprint status (the active + backlog split files; a legacy single `sprint-status.yaml` is auto-split on first run) — extracts story keys and statuses only, never file contents
4. If invoked headlessly (by `bmad-l3io-pm-epic-execute`), uses the provided epic number, sprint number, and story keys directly. Otherwise, identifies the first in-progress or backlog epic with non-done stories and confirms with the user
5. Computes pre-start estimates automatically

### Pre-start estimates

Estimated automatically — no user prompting. Stories are classified by acceptance criteria count:

| Classification | AC count | Est. time | Est. tokens |
|----------------|----------|-----------|-------------|
| Simple | 1–3 ACs | 8–12 min | 40–70K |
| Standard | 4–6 ACs | 12–20 min | 70–120K |
| Complex | 7+ ACs | 20–35 min | 120–200K |

Closure overhead is added on top of story totals:

| Component | Time | Tokens |
|-----------|------|--------|
| Base closure (retro, clean release, adversarial, UX, arch drift, issue triage) | 25–50 min | 60–120K |
| Red-team phase (when `bmad-l3io-sec-agent-redteam` is installed) | +15–25 min | +30–60K |

Actuals are reported at sprint close.

### Per-story phases

Stories run through phases sequentially (by default). Parallel execution is allowed across stories when safe — never across phases within the same story.

| Phase | Step | What happens |
|-------|------|--------------|
| Story Prep | 2a | `bmad-create-story` subagent writes story file to `{story_output_dir}/{story-key}.md`. Orchestrator presents story title + AC count + task count and waits for confirmation before development |
| Development | 2b | `bmad-dev-story` subagent implements all tasks. Story status set to `in-progress`. Verified complete when all task checkboxes are checked and Dev Agent Record is populated |
| Code Review | 2c | `bmad-code-review` subagent reviews all changed files. Status set to `review`. Critical/High findings route immediately to Fix Loop |
| QA | 2d | `bmad-qa-generate-e2e-tests` subagent generates and runs tests. Test evidence written to `{test_output_dir}`. All tests must pass before story is marked `done`. Failures route to Fix Loop |
| Fix Loop | 2e | `bmad-dev-story` subagent addresses each issue. QA re-runs after each fix. Max 3 iterations before the orchestrator halts and presents options to the user |

### Sprint closure phases

All closure outputs go to `{sprint_root_dir}/closure/`. The closure sign-off requires all Critical/High findings resolved.

| Step | Phase | What happens |
|------|-------|--------------|
| 3 | Retrospective | `bmad-retrospective` subagent writes retro to `closure/epic-XX-sprint-YY-retro-{date}.md` |
| 4 | Clean Release Review | Inline analysis — checks for YAGNI violations, added scope, premature abstractions |
| 5 | Adversarial Review | `bmad-review-adversarial-general` subagent reviews the sprint increment as a whole |
| 6 | Red-Team Review | `bmad-l3io-sec-agent-redteam` subagent (skipped gracefully if not installed) |
| 7 | UX Review | `bmad-ux-review` subagent (conditional — skipped if no UX specs found and user opts out) |
| 8 | Light Arch Drift | Inline analysis across five dimensions: data model, API contracts, component boundaries, NFRs, technology/patterns |
| 9 | Issue Triage | All severity counts presented; Critical/High must be fixed or explicitly accepted before continuing |
| 10 | Sprint Sign-Off | Status file updated; actual elapsed time reported against estimate |

### Quality gate

The sprint does not close until all Critical/High findings from all closure phases are either resolved or explicitly accepted by the user with documented rationale.

## Epic Execute Reference

### Activation

On activation, the skill:

1. Resolves the workflow block from `customize.toml`
2. Loads config and resolves all paths including `arch_file` and `prd_file`
3. Reads the sprint status (the active + backlog split files; a legacy single `sprint-status.yaml` is auto-split on first run) — extracts epic and story keys with statuses only
4. Presents sprint grouping proposal and waits for user confirmation
5. Computes pre-start estimates across all sprints plus epic closure overhead

### Epic closure overhead (added to sprint estimates)

| Component | Time | Tokens |
|-----------|------|--------|
| Per sprint closure × number of sprints | 25–50 min/sprint | 60–120K/sprint |
| Red-team per sprint (when l3io-sec installed) | +15–25 min/sprint | +30–60K/sprint |
| Epic-level closure (retro, parallel batch, arch drift, functional completeness, issue triage) | 60–120 min | 100–200K |

### Sprint execution loop (Step 2)

For each sprint in the plan, the epic orchestrator spawns an `bmad-l3io-pm-sprint-execute` subagent with a structured headless prompt containing the epic number, sprint number, story keys, and output root path. The sprint subagent runs all per-story phases and closure phases, then emits:

```
DONE — Stories: N, Issues resolved: N, Issues deferred: N, Retro: [path], Time: ~Nmin (est L–Hmin)
```

Between sprints, the orchestrator asks whether to proceed or pause to adjust the remaining plan.

### Epic closure phases

After all sprints complete, the following phases run in order:

| Step | Phase | Notes |
|------|-------|-------|
| 3 | Epic Retrospective | Runs first; must complete before Step 4 batch |
| 4 | Parallel Closure Batch | Up to `effective_parallel_subagents` concurrent subagents |
| 4a | Clean Release Review | Full epic scope — all stories across all sprints |
| 4b | Adversarial Review | `bmad-review-adversarial-general` — systemic issues across all stories |
| 4c | Red-Team Review | `bmad-l3io-sec-agent-redteam` — full epic attack surface (skipped if not installed) |
| 4d | UX Review | `bmad-ux-review` — conditional on UX specs or user opt-in |
| 5 | Architecture Drift | Solution-scoped — four categories: INTENTIONAL, UNDOCUMENTED, SPEC GAP, MISSING |
| 6 | Functional Completeness | PRD coverage check — each epic-level AC verified against stories and tests |
| 7 | Issue Triage and Resolution | All findings presented; Critical/High + undocumented drift + AC gaps must be resolved |
| 8 | Epic Sign-Off | Status file updated; actual elapsed time reported |

### Quality gate

The epic does not close until all of the following are resolved:
- All Critical/High findings from closure phases
- All undocumented architecture drift findings (fix the code or document the rationale)
- All functional completeness AC gaps (implement the missing AC or defer with documented rationale)

## Headless Mode

When `bmad-l3io-pm-epic-execute` calls `bmad-l3io-pm-sprint-execute`, it passes a structured prompt:

```
Load config from: {config_file}
Load project context from: {context_file} (if it exists)
Sprint status file: {status_file}
Target: Epic {target_epic}, stories: {sprint_story_keys}
Sprint number: {current_sprint_num} (two-digit: {current_sprint_padded})
Expected sprint output root: {epic_root_dir}/sprint-{current_sprint_padded}
Invoke skill: bmad-l3io-pm-sprint-execute
Execute the complete sprint for the listed stories — all per-story phases and closure phases.
...
Print when done:
  DONE — Stories: N, Issues resolved: N, Issues deferred: N, Retro: [path]
```

In headless mode, the sprint skill skips the interactive scope confirmation and emits a single status line instead of the full sign-off summary.

## Artifact Paths Reference

All paths use zero-padded two-digit epic/sprint numbers.

| Path | Description |
|------|-------------|
| `{implementation_artifacts}/sprint-status-active.yaml` | Story and epic status for in-progress epics — part of the single source of truth |
| `{implementation_artifacts}/sprint-status-backlog.yaml` | Not-yet-started work plus the consolidated deferred-issue backlog — part of the single source of truth |
| `{implementation_artifacts}/sprint-status-archived.yaml` | Done epics, moved here wholesale at epic close — part of the single source of truth |
| `{implementation_artifacts}/epic-XX/sprint-YY/stories/{story-key}.md` | Story file |
| `{implementation_artifacts}/epic-XX/sprint-YY/closure/` | Sprint closure outputs (retro, adversarial, etc.) |
| `{implementation_artifacts}/epic-XX/sprint-YY/tests/` | Sprint-scoped QA evidence |
| `{implementation_artifacts}/epic-XX/epic-closure/` | Epic closure outputs |
| `{implementation_artifacts}/epic-XX/tests/` | Epic-scoped fix verification evidence |
| `{planning_artifacts}/epic-XX/` | Epic-level planning documents |
| `{planning_artifacts}/epic-XX/sprint-YY/` | Sprint-level planning documents |

Sprint closure filename pattern: `epic-XX-sprint-YY-{type}-{date}.md`
Epic closure filename pattern: `epic-XX-{type}-{date}.md`

Types: `retro`, `clean-release`, `adversarial`, `redteam`, `ux-review`, `arch-drift`, `functional-completeness`

## Status File Schema

The sprint status tracks story and epic lifecycle, split across three files in `{implementation_artifacts}/`: `sprint-status-active.yaml` (in-progress epics), `sprint-status-backlog.yaml` (not-yet-started work plus the consolidated top-level deferred-issue `backlog:` list, each item tagged with `epic` and `sprint` keys), and `sprint-status-archived.yaml` (done epics, moved here wholesale at epic close). Placement granularity is epic + sprint — stories always travel inside their owning sprint node, and archiving happens only at epic close. The placement rule, node-move operations, and read/auto-fallback procedure are defined in each PM skill's `references/status-files.md`. Only the orchestrator writes to these files; subagents pass paths but do not write directly. The schema below shows the per-epic node shape that lives in whichever of the three files currently holds that epic.

Story status lifecycle:

```
backlog → ready-for-dev → in-progress → review → done
```

| Status | Set when |
|--------|----------|
| `backlog` | Initial state |
| `ready-for-dev` | Story prep complete, user confirmed |
| `in-progress` | Development phase started |
| `review` | Development complete, entering code review |
| `done` | All QA tests pass |

Epic status lifecycle: `backlog → in-progress → done`

### Full schema

```yaml
epics:
- id: '01'
  title: 'Epic 01 — ...'           # written at in-progress
  goal: '...'                       # written at in-progress
  status: done
  closed: '2026-05-18'             # written at epic close
  retrospective: path/to/retro.md  # written at epic close
  estimate:                         # written after pre-start estimate
    time_hours_low: 3.0
    time_hours_high: 5.7
    tokens_k_min: 800
    tokens_k_max: 1600
    cost_low: '$6.40'
    cost_high: '$12.80'
    man_hours_low: 120             # traditional dev equivalent (person-hours)
    man_hours_high: 240
  actual:                           # written at epic close
    elapsed_hours: 4.1             # AI-assisted wall-clock actual
    man_hours: 4.1                 # auto-computed: sum of sprint man_hours + 12h closure
  sprints:
  - id: '01'
    title: 'Sprint 01 — Foundation'
    status: done
    closed: '2026-05-18'
    retrospective: path/to/retro.md
    estimate:
      time_hours_low: 0.8
      time_hours_high: 1.4
      tokens_k_min: 250
      tokens_k_max: 480
      cost_low: '$2.00'
      cost_high: '$3.84'
      man_hours_low: 40
      man_hours_high: 80
    actual:
      elapsed_hours: 1.1
      man_hours: 52.5              # auto-computed: sum of (classification base × fix_factor) + 24h closure
    stories:
    - key: PROJ-E01-S01-ST01
      title: 'Story title'
      status: done
      classification: complex      # simple | standard | complex — written at ready-for-dev
      completion_evidence:         # written at done
        fix_iterations: 2
        tests_passing: 42
        files_changed: 8
        bugs_fixed:                # omitted when fix_iterations == 0
        - 'Brief description of fix'
  backlog:
  - key: PROJ-E01-BL-01
    title: 'Issue title'
    source: 'adversarial (ADV-L-01)'
    severity: Low                  # Critical | High | Medium | Low
    status: backlog
    description: 'One-sentence description.'
    resolved: '2026-05-19'        # added when fixed
    resolution: 'How it was fixed.'
```

To upgrade a sprint status file that is missing these fields, run `/bmad-l3io-util-cleanup migrate-schema`. To split a legacy single `sprint-status.yaml` into the active/backlog/archived three-file layout (the original is preserved as `sprint-status.yaml.legacy`), run `/bmad-l3io-util-cleanup split-status`; the PM skills also auto-split a legacy file on first run.

## Estimation Calibration

Sprint-execute learns from plan-vs-actual deltas and applies corrections to future estimates. No configuration required — it activates automatically once enough history exists.

### How it works

At each sprint close (Step 12), the skill computes:
- `time_ratio` = `actual.elapsed_hours` ÷ midpoint of written estimate
- `man_hours_ratio` = `actual.man_hours` ÷ midpoint of written estimate

These are appended to `{project-root}/_bmad/pm-calibration.yaml`. At sprint 4 and beyond, the pre-start estimate multiplies the formula baseline by the weighted rolling average of past ratios (exponential decay, weight = 0.8^n, most recent sprint = 1.0).

The system is self-correcting: if calibration overshoots (estimates become too high), the ratio drops below 1.0 and pulls the factor back down on subsequent sprints.

### Calibration file

`_bmad/pm-calibration.yaml` — project-scoped, add to `.gitignore` if you prefer not to commit it:

```yaml
version: 1
last_updated: '2026-05-28'
sprints_sampled: 4
time_ratio: 1.23          # applied to time_hours estimates
man_hours_ratio: 0.95     # applied to man_hours estimates
history:
- id: E01-S01
  date: '2026-05-15'
  time_ratio: 1.15
  man_hours_ratio: 0.92
  story_mix: { simple: 2, standard: 3, complex: 1 }
```

### Announcement format

When calibration is active, the pre-start estimate line reads:
```
Calibration:  applied — 4 sprints sampled (time ×1.23, man-hours ×0.95)
```
Before 3 sprints are recorded:
```
Calibration:  none yet — estimates are formula baseline (calibration starts after sprint 3)
```

## Dependency Skills by Phase

| Phase | Skill invoked |
|-------|--------------|
| Story Prep | `bmad-create-story` |
| Development | `bmad-dev-story` |
| Fix Loop | `bmad-dev-story` |
| Code Review | `bmad-code-review` |
| QA | `bmad-qa-generate-e2e-tests` |
| Retrospective (sprint + epic) | `bmad-retrospective` |
| Adversarial Review (sprint + epic) | `bmad-review-adversarial-general` |
| Red-Team Review (sprint + epic) | `bmad-l3io-sec-agent-redteam` (optional) |
| UX Review (sprint + epic) | `bmad-ux-review` (optional) |
| Clean Release, Arch Drift, Functional Completeness | Inline — no skill invoked |
