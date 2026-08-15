# Step 06: Plan Output

Communicate all responses in `{communication_language}`.

Writes the plan snapshot and updates the stable pointer. This is the final step of full plan mode.

---

## 1. Determine plan filename

Today's date: read from the system (`date +%Y-%m-%d`).

List existing plan snapshots in `{planning_artifacts}/`:
```bash
ls {planning_artifacts}/plan-{today}-v*.yaml 2>/dev/null | sort -V | tail -1
```

If none exist for today → filename = `plan-{today}-v1.yaml`.
If the highest existing version is `vN` → filename = `plan-{today}-v{N+1}.yaml`.

Set `{plan_filename}` = `plan-{today}-v{version_number}.yaml`.

## 2. Build the plan snapshot

Construct `{plan_snapshot}` with this structure (write verbatim to file — preserve all fields):

```yaml
generated: "{timestamp}"               # ISO-8601 UTC
plan_version: {version_number}         # integer; auto-increments per-day, resets on new date
readiness: {readiness}                 # green | amber | red
stories_elaborated: {elaborated_count} # from step-03; 0 if step was skipped
total_epics_in_scope: {in_scope_count} # active + backlog (not deferred, not archived)

phases:
{phases_yaml_block}                    # exactly the phases list from step-05

readiness_detail:
{readiness_detail_yaml_block}          # per-epic: key, status (green/amber/red), gaps list

arch_gate_summary:
  ran: false                           # always false at plan time — arch gate runs in l3io-pm-execute
  reviewers: []
  findings: []

deferred_epics:
{deferred_epics_yaml_block}            # list of {key, title, deferred_reason, deferred_date}
```

Where `{phases_yaml_block}` includes the estimate sub-block for each phase if estimates are present:

```yaml
phases:
  - phase: 1
    parallel: true
    epics: ["E001", "E002"]
    dependencies: []
    estimate:
      wall_clock_hours_low: {max(epic.time_hours_low) if parallel else Σ time_hours_low}
      wall_clock_hours_high: {max(epic.time_hours_high) if parallel else Σ time_hours_high}
      man_hours_low: {Σ man_hours_low}
      man_hours_high: {Σ man_hours_high}
      tokens_k_min: {Σ tokens_k_min}
      tokens_k_max: {Σ tokens_k_max}
      cost_low: {Σ cost_low}
      cost_high: {Σ cost_high}
      confidence: {weakest confidence across epics}
```

For parallel phases, wall_clock = max(epic.time_hours) not sum — parallel phases run concurrently. For sequential phases, wall_clock = sum.

## 3. Write plan snapshot

```bash
# Write to {planning_artifacts}/{plan_filename}
# The file must not already exist (new unique snapshot each run)
```

Write `{plan_snapshot}` as YAML to `{planning_artifacts}/{plan_filename}`.

## 4. Update plan-output-meta.yaml

Write `{planning_artifacts}/plan-output-meta.yaml` (overwrite):

```yaml
current_plan: "{plan_filename}"
generated: "{timestamp}"
readiness: {readiness}
stories_elaborated: {elaborated_count}
total_epics_in_scope: {in_scope_count}
phases:
{phases_summary_yaml_block}            # same phases list, estimates included if present
```

## 5. Output plan summary

Always print the human-readable summary:

```
📋 Plan complete — {plan_filename}

Scope: {in_scope_count} epics across {phase_count} phases

Phase 1 (parallel): {epic_keys} — est. {time_low}–{time_high} hrs wall-clock, {cost_low}–{cost_high} cost
Phase 2 (sequential): {epic_keys} — est. {time_low}–{time_high} hrs wall-clock, {cost_low}–{cost_high} cost

Critical path: {critical_path_str} ({total_time_low}–{total_time_high} hrs)
Deferred: {deferred_count} epics not in plan

Readiness: {readiness}
Plan written to: {planning_artifacts}/{plan_filename}
Stable pointer: {planning_artifacts}/plan-output-meta.yaml

Next: run /l3io-pm-execute to start execution.
```

If `{plan_output}` is `console`, skip writing files in steps 3 and 4 — print only.

## 6. Output status line

```
Step 06 complete — plan: {plan_filename}, phases: {phase_count}, readiness: {readiness}
DONE — Plan: {plan_filename}, epics: {in_scope_count}, phases: {phase_count}
```
