# l3io-pm Reference

Full reference for the PM orchestration module — four skills that orchestrate a complete delivery lifecycle from execution planning through epic closure.

## Skills Overview

| Skill | Role |
|-------|------|
| `l3io-pm-plan-execution` | Analyzes epic dependencies and produces a phased, parallel-optimized execution plan |
| `l3io-pm-sprint-execute` | Orchestrates a single sprint: per-story phases plus sprint closure reviews |
| `l3io-pm-epic-execute` | Orchestrates a full epic: delegates to `l3io-pm-sprint-execute` subagents, then runs epic closure |

`l3io-pm-epic-execute` is a wrapper around `l3io-pm-sprint-execute`. It handles sprint grouping, delegates each sprint headlessly, and runs a second level of closure reviews after all sprints complete.

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

All three orchestration skills ship with a `customize.toml` at `{skill-root}/customize.toml`. Override values are layered in this order (last wins):

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
4. If invoked headlessly (by `l3io-pm-epic-execute`), uses the provided epic number, sprint number, and story keys directly. Otherwise, identifies the first in-progress or backlog epic with non-done stories and confirms with the user
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
| Red-team phase (when `l3io-sec-agent-redteam` is installed) | +15–25 min | +30–60K |

Estimates are a **bottom-up roll-up**: each story estimate = `base_band × scope_ratio × fix_mult`, the sprint estimate = Σ story estimates + the calibrated closure band, and (at epic level) the epic estimate = Σ sprint estimates + the epic-closure band. Sprint/epic estimates are *defined as* the sum of their children + closure, so they reconcile exactly. Story estimates are written **up front at the pre-start estimate** and read (not recomputed) during the story loop. A fix reserve (`F`, default 1.25 ≈ one fix pass) is applied as a cold-start prior until calibration has enough samples — see [Estimation Calibration](#estimation-calibration). Actuals are reported at sprint close.

### Per-story phases

Stories run through phases sequentially (by default). Parallel execution is allowed across stories when safe — never across phases within the same story.

| Phase | Step | What happens |
|-------|------|--------------|
| Story Prep | 2a | Technical-AC gate reads the existing story at `{sprint_root}/stories/{story-key}.md` and enriches it in place when technical ACs are missing. Orchestrator presents story title + AC count + task count and waits for confirmation before development |
| Development | 2b | `bmad-dev-story` subagent implements all tasks. Story status set to `in-progress`. Verified complete when all task checkboxes are checked and Dev Agent Record is populated |
| Code Review | 2c | `bmad-code-review` subagent reviews all changed files. Status set to `review`. Critical/High findings route immediately to Fix Loop |
| QA | 2d | `bmad-qa-generate-e2e-tests` subagent generates and runs tests. Test evidence written to `{test_output_dir}`. All tests must pass before story is marked `done`. Failures route to Fix Loop |
| Fix Loop | 2e | `bmad-dev-story` subagent addresses each issue (Critical/High/Medium auto-fixed without per-item prompts). QA re-runs after each fix. Max 10 iterations before the orchestrator halts and presents options to the user |

### Sprint closure phases

All closure outputs go to `{sprint_root_dir}/closure/`. The closure sign-off requires all Critical/High findings resolved.

| Step | Phase | What happens |
|------|-------|--------------|
| 3 | Retrospective | `bmad-retrospective` subagent writes retro to `closure/epic-XX-sprint-YY-retro-{date}.md` |
| 4 | Clean Release Review | Inline analysis — flags added scope and over-engineering as a concrete `{file}:{line} — {tag} {cut}` list (tags: delete / stdlib / native / yagni / shrink) with a removable-line count; never flags validation, error handling, security, or accessibility. Also harvests `bmad-defer:` shortcut markers in the sprint's changed files straight to the backlog |
| 5 | Adversarial Review | `bmad-review-adversarial-general` subagent reviews the sprint increment as a whole |
| 6 | Red-Team Review | `l3io-sec-agent-redteam` subagent (skipped gracefully if not installed) |
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

For each sprint in the plan, the epic orchestrator spawns an `l3io-pm-sprint-execute` subagent with a structured headless prompt containing the epic number, sprint number, story keys, and output root path. The sprint subagent runs all per-story phases and closure phases, then emits:

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
| 4c | Red-Team Review | `l3io-sec-agent-redteam` — full epic attack surface (skipped if not installed) |
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

When `l3io-pm-epic-execute` calls `l3io-pm-sprint-execute`, it passes a structured prompt:

```
Load config from: {config_file}
Load project context from: {context_file} (if it exists)
Sprint status file: {status_file}
Target: Epic {target_epic}, stories: {sprint_story_keys}
Sprint number: {current_sprint_num} (two-digit: {current_sprint_padded})
Expected sprint output root: {epic_root_dir}/sprint-{current_sprint_padded}
Invoke skill: l3io-pm-sprint-execute
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
| `{implementation_artifacts}/sprint-status.yaml` | Story and epic status for in-progress epics — part of the single source of truth |
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

The sprint status tracks story and epic lifecycle, split across three files in `{implementation_artifacts}/`: `sprint-status.yaml` (in-progress epics), `sprint-status-backlog.yaml` (not-yet-started work plus the consolidated top-level deferred-issue `backlog:` list, each item tagged with `epic` and `sprint` keys), and `sprint-status-archived.yaml` (done epics, moved here wholesale at epic close). Placement granularity is epic + sprint — stories always travel inside their owning sprint node, and archiving happens only at epic close. The placement rule, node-move operations, and read/auto-fallback procedure are defined in each PM skill's `references/status-files.md`. Only the orchestrator writes to these files; subagents pass paths but do not write directly. The schema below shows the per-epic node shape that lives in whichever of the three files currently holds that epic.

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
  estimate:                         # roll-up: Σ sprint.estimate + calibrated epic-closure band
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
- key: BL-E01-01                       # BL-E{epic}-{nn}, both zero-padded; BL-E00-{nn} for repo-global
  epic: '01'                           # zero-padded epic id; '00' for repo-global items
  sprint: '02'                         # zero-padded sprint id; '' for an epic-level deferral
  title: 'Issue title'
  source: 'adversarial (ADV-L-01)'     # review phase + finding id
  severity: Low                        # Critical | High | Medium | Low
  status: backlog
  description: 'One-sentence description.'
```

The `backlog:` list is backlog-only — only `status: backlog` items appear. When an item is resolved inline or promoted to a story, it is **removed** from the list. There are no `resolved` or `resolution` fields — done items simply don't exist in this list. When promoted to a story, a story node is created in the target sprint in `sprint-status.yaml` with `title` and `classification` pre-populated; the story then follows the normal lifecycle and archives with its epic at epic close.

To upgrade a sprint status file that is missing these fields, run `/l3io-util-cleanup migrate-schema`. To split a legacy single `sprint-status.yaml` into the active/backlog/archived three-file layout (the original is preserved as `sprint-status.yaml.legacy`), run `/l3io-util-cleanup split-status`; the PM skills also auto-split a legacy file on first run.

## Metrics Contract (estimates & actuals)

Every planning point and every closeout — at **story, sprint, epic, and retrospective** level — records both an `estimate` and an `actual` for all **four** metrics: man-hours, compute (AI wall-clock) hours, tokens, and token cost. This is a hard rule: a sprint or epic does not sign off with any estimate block, actual block, or individual metric missing. The authoritative procedure lives in each PM skill's `references/metrics-contract.md`.

**Runtime-aware token/cost capture.** How the token and cost *actuals* are captured depends on the runtime, detected via the `CLAUDECODE=1` environment variable:

- **Under Claude** — tokens and cost are captured **exactly** from the session transcript `usage` fields (the run is scoped by session id, covering the orchestrator and all subagent transcripts). Never estimated.
- **Under other runtimes** (e.g. Copilot) — if the runtime exposes a usage source it is read; otherwise tokens and cost are recorded as **`N/A`**, never guessed or back-filled. Seeing `N/A` for tokens/cost under a non-Claude runtime is expected behavior, not an error.

Compute hours (measured wall-clock) and man-hours (a modeled traditional-dev-equivalent formula) are always captured in both runtimes.

## Estimation Calibration

Sprint-execute (and epic-execute at epic close) learns from plan-vs-actual deltas and applies corrections to future estimates. No configuration required — it activates automatically, per component, once enough history exists.

### How it works (decomposed)

Calibration is **decomposed into three independent components**, each learned per metric, so a miss can be attributed to story sizing vs closure overhead vs fix churn rather than one blended number:

- **`scope`** — per classification (simple / standard / complex) × per metric: how story-sizing estimates compare to **fix-excluded** actuals.
- **`closure`** — per level (sprint, epic) × per metric: how the static closure bands compare to real closure consumption. (Closure was previously never calibrated — a blind spot this closes.)
- **`fix`** — per classification: the observed average fix multiplier (`avg_fix_factor`), which **replaces** the static fix reserve once learned.

Each component activates once it has **≥3 samples** (independently), using an exponential-decay weighted rolling average (weight = 0.8^n, most recent = 1.0). Until then it uses a cold-start prior: ratio 1.0, or fix reserve `F` = 1.25.

> **Why the fix reserve is only a cold-start prior:** actuals are captured *after* the fix loop while estimates are written *before* it, so every learned ratio already encodes real fix overhead. Multiplying a learned ratio by a static reserve would **double-count** fixes — so `F` retires as soon as the `fix` component has ≥3 samples.

**Sampling granularity** is controlled by `calibration_granularity` in `customize.toml` (`"story"` default — each done story emits a scope/fix sample, so the model converges after ~3 *stories* — or `"sprint"` for coarser per-sprint aggregation). Closure samples are always emitted per sprint / epic. The scope-vs-fix split of measured time/token/cost actuals is computed by backing the fix portion out via `fix_factor` (approach A).

**`token` and `cost` ratios only accumulate from runs with real actuals** (Claude runs); `N/A` entries (non-Claude runtime or unreadable transcript) are skipped — a guessed value is never fed into calibration. `time` and `man_hours` accumulate from every run.

The system is self-correcting: if a component overshoots, its ratio drops below 1.0 and pulls subsequent estimates back down.

### Calibration file

`_bmad/pm-calibration.yaml` (`version: 2`) — project-scoped, add to `.gitignore` if you prefer not to commit it. A legacy `version: 1` file is auto-migrated on first write (original kept as `pm-calibration.yaml.v1`):

```yaml
version: 2
last_updated: '2026-05-28'
stories_sampled: 12
sprints_sampled: 4
epics_sampled: 1
scope:                    # per class × per metric (fix-excluded story sizing)
  simple:   { time_ratio: 1.10, token_ratio: 1.05, cost_ratio: 1.05, man_hours_ratio: 1.0, sample_count: 6 }
  standard: { time_ratio: 1.20, token_ratio: 1.12, cost_ratio: 1.12, man_hours_ratio: 1.0, sample_count: 9 }
  complex:  { time_ratio: 1.35, token_ratio: 1.28, cost_ratio: 1.28, man_hours_ratio: 1.0, sample_count: 3 }
closure:                  # per level × per metric (NEW)
  sprint: { time_ratio: 0.95, token_ratio: 1.08, cost_ratio: 1.08, man_hours_ratio: 1.0, sample_count: 4 }
  epic:   { time_ratio: 1.0,  token_ratio: 1.0,  cost_ratio: 1.0,  man_hours_ratio: 1.0, sample_count: 1 }
fix:                      # per class; supersedes the cold-start reserve at ≥3 samples
  simple:   { avg_fix_factor: 1.10, sample_count: 6 }
  standard: { avg_fix_factor: 1.30, sample_count: 9 }
  complex:  { avg_fix_factor: 1.50, sample_count: 3 }
history:                  # most recent 30 entries
- { kind: story, id: 'E01-S01-ST01', class: complex, date: '2026-05-15', scope: { time_ratio: 1.3, token_ratio: 1.25, cost_ratio: 1.25, man_hours_ratio: 1.0 }, fix_factor: 1.5 }
- { kind: sprint-closure, id: 'E01-S01', date: '2026-05-15', closure: { time_ratio: 0.9, token_ratio: 1.1, cost_ratio: 1.1, man_hours_ratio: 1.0 } }
```

### Announcement format

When any component is calibrated, the pre-start estimate line summarizes which are active:
```
Calibration:  scope.complex ×1.35 (n=3) · fix.complex ×1.50 (n=3) · closure.sprint ×0.95 (n=4)
```
Before any component reaches 3 samples:
```
Calibration:  none yet — formula baseline (components calibrate at ≥3 samples)
```

## Plan Execution Reference

`l3io-pm-plan-execution` analyzes the dependency graph across your epics and produces a phased, parallel-optimized execution plan. It is a read-only planning skill — it does not execute any work.

### Scope arguments

| Argument | Effect |
|----------|--------|
| *(none)* | All non-done epics in the split status files |
| `--epics E01,E02` | Only the named epic keys (comma- or space-separated) |
| `--stories E01-S01-001,E02-S01-003` | Derives owning epics from the story keys; scopes to those epics |

### Output

Saves a markdown plan to `{planning_artifacts}/execution-plan-{date}.md` (configurable). The plan contains one section per phase with parallel/sequential labeling, per-epic story counts and wall-clock estimates, the critical path chain, and ready-to-run `/l3io-pm-epic-execute` dispatch commands.

### customize.toml keys

| Key | Default | Description |
|-----|---------|-------------|
| `plan_output` | `"markdown"` | `"markdown"` saves to `planning_artifacts`; `"console"` displays only |
| `include_dispatch_lines` | `true` | Whether to include `/l3io-pm-epic-execute` dispatch lines in the plan |
| `include_estimates` | `true` | Whether to include per-phase wall-clock estimates and critical path |

### Declaring dependencies

Add `depends_on` to epic or story nodes in the sprint status files. Both fields are optional and default to `[]`.

**Epic-level** — prerequisite epic keys that must be `status: done` before this epic starts:
```yaml
epics:
  - key: 'E03'
    depends_on: ['E01', 'E02']
```

**Story-level** — prerequisite story keys (cross-epic supported); the skill rolls cross-epic story deps up to epic-level edges:
```yaml
stories:
  - key: E03-S01-001
    depends_on: ['E01-S02-003']
```

## Dependency Skills by Phase

| Phase | Skill invoked |
|-------|--------------|
| Story Prep | *(none — enriched in place by the step itself)* |
| Development | `bmad-dev-story` |
| Fix Loop | `bmad-dev-story` |
| Code Review | `bmad-code-review` |
| QA | `bmad-qa-generate-e2e-tests` |
| Retrospective (sprint + epic) | `bmad-retrospective` |
| Adversarial Review (sprint + epic) | `bmad-review-adversarial-general` |
| Red-Team Review (sprint + epic) | `l3io-sec-agent-redteam` (optional) |
| UX Review (sprint + epic) | `bmad-ux-review` (optional) |
| Clean Release, Arch Drift, Functional Completeness | Inline — no skill invoked |
