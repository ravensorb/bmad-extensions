# Step 03: Load Plan

Communicate all responses in `{communication_language}`.

Read the plan snapshot and validate it against current state. If no plan exists, offer to run
`l3io-pm-plan` first.

## 1. Read plan-output-meta.yaml

```bash
cat {planning_artifacts}/plan-output-meta.yaml
```

If absent:
```
No plan found at {planning_artifacts}/plan-output-meta.yaml.
Run /l3io-pm-plan first to build the execution plan.
```
BLOCKED: plan-output-meta.yaml absent.

If `readiness: red` → warn:
```
⚠️  Plan readiness is RED. Proceeding may produce incomplete results.
   Run /l3io-pm-plan to resolve readiness gaps, or continue at your own risk.
```
Pause for user confirmation before continuing.

If `readiness: amber` → warn and continue without pause.

## 2. Load plan snapshot

Bind `{current_plan_file}` = `{planning_artifacts}/{current_plan}` (from plan-output-meta.yaml).

Read the snapshot file. Extract and bind:
- `{plan_phases}` — ordered list of phases, each with `parallel` flag and `epics` list
- `{plan_generated}` — ISO timestamp
- `{plan_confidence}` — overall confidence (lowest across phases)

## 3. Resolve execution order for scoped epics

If `{exec_scope}=full`: execution order = phases in sequence; within each parallel phase, epics may run concurrently up to `{max_parallel_subagents}`.

If `{exec_scope}=epic`: find which phase contains `{scope_epic_keys}[0]`. Execute that epic only. Dependencies from prior phases are assumed satisfied (user asserts this by scoping to a single epic).

If `{exec_scope}=sprint`: find the epic and sprint. Execute only that sprint as a headless subagent directly after this step (skip step-04 arch gate for sprint scope).

Bind `{execution_phases}` = resolved ordered list of (phase, [epic_keys], parallel_flag).

## 4. Validate dependencies for full scope

For each phase beyond phase 1, verify that all `dependencies` listed in the phase have `status: done`
in `{bmad_archived_file}` or `{bmad_active_root}`. If any dependency is not done:
```
⚠️  Phase N dependency {epic_key} is not done. Phase N epics will be blocked until it completes.
```
Do not halt — log and continue. The epic loop will enforce ordering at runtime.

## 5. Output

```
Step 03 complete — plan: {current_plan_file}, phases: {count}, confidence: {plan_confidence}
```
