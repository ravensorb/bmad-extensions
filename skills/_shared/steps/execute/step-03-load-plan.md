# Step 03: Load Plan

Communicate all responses in `{communication_language}`.

Read the plan snapshot and validate it against current state. If no plan exists, or the plan
pointer is missing or broken, this step rebuilds the plan with `/l3io-plan` and carries on. It
ends `BLOCKED` only when that does not clear the condition, or when the way forward is a risk
the user alone accepts — it has no inbox and never offers a choice it cannot then act on.

The four conditions below that run `/l3io-plan` follow `references/auto-remediation.md`: one
attempt per run, a report before and after, and only a cleared condition continues. Keep one
in-run flag, `{plan_rebuilt}`, set to true **before** the first `/l3io-plan` run in this step.
It is shared by all four sites: a plan already rebuilt in this step is never rebuilt again, and a
pointer or readiness fault that survives the rebuild goes straight to that site's persists halt.

## 1. Read plan-output-meta.yaml

`plan-output-meta.yaml` is the **only** pointer to the current plan. Snapshots accumulate in
`{planning_artifacts}/` as `plan-{YYYY-MM-DD}-v{N}.yaml` and are inert history — never pick one
by scanning the directory when the pointer resolves. Newest-on-disk is not the same question as
current: `l3io-plan` writes the snapshot and the pointer as two separate steps, so the newest
file may be from a run that never finished.

```bash
cat {planning_artifacts}/plan-output-meta.yaml
```

If absent, check for orphaned snapshots before declaring no plan — a pointer write that failed
after its snapshot was written leaves a usable plan that a bare "no plan found" would hide:

```bash
ls -1 {planning_artifacts}/plan-*-v*.yaml 2>/dev/null | sort -V | tail -3
```

If nothing is listed, there is no plan to execute, and `/l3io-plan` builds one. Report:
```
⚙  No plan found at {planning_artifacts}/plan-output-meta.yaml — running /l3io-plan
```
Set `{plan_rebuilt}` = true, then run `/l3io-plan`. There are three outcomes, and only the
first continues.

**Outcome 1 — The remedy succeeds and clears the condition.** Re-read the pointer once. If it
now exists, report and carry on with the pointer's `readiness` below:
```
✓  /l3io-plan wrote plan-output-meta.yaml and a fresh snapshot. Continuing with the new plan.
```

**Outcome 2 — The remedy succeeds and the condition persists.** If the pointer is still
absent:
```
BLOCKED: plan-output-meta.yaml absent. I ran /l3io-plan and it reported success, but no
plan-output-meta.yaml exists in {planning_artifacts}. This needs a decision.
```

**Outcome 3 — The remedy fails.** If `/l3io-plan` errors or halts:
```
BLOCKED: plan-output-meta.yaml absent. I ran /l3io-plan and it failed: {failure}. No plan
exists to execute until this is resolved.
```

If snapshots **are** listed, do not adopt one silently — the pointer is the contract and its
absence means a plan run did not complete:
```
⚠️  plan-output-meta.yaml is missing, but plan snapshots exist:
      {listed_snapshots}
    A plan run likely did not finish, so the newest snapshot may be incomplete.
    Without the pointer there is nothing vouching for any of them, so none is adopted.
```
This is a degraded path, and the snapshots are not trusted: rebuild from current state rather
than adopt one. The rebuild neither deletes nor reads them. Report:
```
⚙  plan-output-meta.yaml is missing but plan snapshots exist — running /l3io-plan to rebuild
   the pointer and readiness from current state
```
Set `{plan_rebuilt}` = true, then run `/l3io-plan`. There are three outcomes, and only the
first continues.

**Outcome 1 — The remedy succeeds and clears the condition.** Re-read the pointer once. If it
now exists, report and carry on with the pointer's `readiness` below:
```
✓  /l3io-plan rebuilt plan-output-meta.yaml from current state; existing snapshots untouched.
   Continuing with the new plan.
```

**Outcome 2 — The remedy succeeds and the condition persists.** If the pointer is still
absent:
```
BLOCKED: plan-output-meta.yaml absent, but snapshots exist ({listed_snapshots}). I ran
/l3io-plan and it reported success, but the pointer is still missing. This needs a decision.
```

**Outcome 3 — The remedy fails.** If `/l3io-plan` errors or halts:
```
BLOCKED: plan-output-meta.yaml absent, but snapshots exist ({listed_snapshots}). I ran
/l3io-plan and it failed: {failure}. Adopting a snapshot is not an option while none is vouched
for.
```

If `readiness: red` → warn:
```
⚠️  Plan readiness is RED for {current_plan_file}. Executing it would produce incomplete
   results.
```
Route 1 is `/l3io-plan`, which resolves the readiness gaps and rebuilds the plan, and it runs
now unless `{plan_rebuilt}` is already true. Route 2, accepting the risk, is **never** performed here: setting readiness to amber is a
risk acceptance and stays the user's alone.

If `{plan_rebuilt}` is already true — a rebuild earlier in this step produced this red plan —
do not run `/l3io-plan` again; go straight to Outcome 2. Otherwise report:
```
⚙  Plan readiness is RED for {current_plan_file} — running /l3io-plan to resolve the gaps
```
Set `{plan_rebuilt}` = true, then run `/l3io-plan`. There are three outcomes, and only the
first continues.

**Outcome 1 — The remedy succeeds and clears the condition.** Re-read the pointer once. If
`readiness` is no longer `red`, rebind `{current_plan_file}` from the new pointer, report, and
continue (`amber` warns and continues as below):
```
✓  /l3io-plan resolved the readiness gaps; readiness is now {readiness}. Continuing with
   {current_plan_file}.
```

**Outcome 2 — The remedy succeeds and the condition persists.** If readiness is still `red`,
this is a degraded path and this step has no inbox to wait on — write what you found and stop:
```
BLOCKED: plan readiness is RED for {current_plan_file}. I ran /l3io-plan and readiness is
RED after it; the readiness findings it reported list the gaps. Two things unblock it:
  1. Resolve those gaps and re-run /l3io-execute.
  2. Accept the risk: say so, and I will set readiness to amber in
     {planning_artifacts}/plan-output-meta.yaml, then you re-run /l3io-execute.
```

**Outcome 3 — The remedy fails.** If `/l3io-plan` errors or halts:
```
BLOCKED: plan readiness is RED for {current_plan_file}. I ran /l3io-plan to resolve the
readiness gaps and it failed: {failure}. Two things unblock it:
  1. Resolve the cause above and re-run /l3io-execute.
  2. Accept the risk: say so, and I will set readiness to amber in
     {planning_artifacts}/plan-output-meta.yaml, then you re-run /l3io-execute.
```
A failed `/l3io-plan` may have left `plan-output-meta.yaml` partly written, so re-read the
pointer before any later edit of it, including the amber edit of route 2.

**Never tell the user to edit that file themselves.** It is written by
`step-06-plan-output.md` §4, so it is ours, and the rule across this package is that the human
decides and the agent edits — "go and change it yourself" is not an outcome we hand back. A
hand edit is not safer here either, only more error-prone: the wrong field, the wrong file, or
damaged YAML, in a pointer `l3io-execute` treats as the sole authority for which plan is
current.

**The friction stays; only the mechanism moves.** Accepting a red plan must remain a
deliberate act, so do not offer this as a menu option or infer it from impatience. Act only on
an explicit statement that the risk is accepted, rewrite **just** the `readiness:` field,
leave every other key untouched, and say plainly what you changed and in which file.

**Do not tell the user to simply re-run `/l3io-execute`.** A re-run reads the same
`readiness: red` from the same pointer and blocks here identically; there is no override flag,
and naming one that does not exist sends them round a loop. Only resolving the gaps or the
explicit risk acceptance changes what this step reads.

If `readiness: amber` → warn and continue without pause.

## 2. Load plan snapshot

Bind `{current_plan_file}` = `{planning_artifacts}/{current_plan}` (from plan-output-meta.yaml).

Verify the pointer's target exists before reading it — a pointer naming a file that was
deleted, renamed, or never written is a broken plan, not an empty one:

```bash
test -f {current_plan_file} && echo OK || echo MISSING
```

If `MISSING`, `/l3io-plan` rebuilds the plan and the pointer. Do not substitute another
snapshot — that would execute a plan the pointer does not vouch for. Nor may a legacy pointer's
`phases:` list stand in for the missing snapshot: current pointers carry only `phase_count`,
and the older duplicated list is by definition as old as the pointer and was never the
authority for phases. Rebuilding is not substituting: the new snapshot is the one the new
pointer names. If `{plan_rebuilt}` is already true, go straight to Outcome 2. Otherwise report:
```
⚙  plan-output-meta.yaml points at {current_plan}, which does not exist — running /l3io-plan
   to rebuild the plan and pointer
```
Set `{plan_rebuilt}` = true, then run `/l3io-plan`. There are three outcomes, and only the
first continues.

**Outcome 1 — The remedy succeeds and clears the condition.** Re-read the pointer once, rebind
`{current_plan_file}` from it, and repeat the `test -f` check. If the file exists, apply the
`readiness` handling from §1 to the new pointer (a red plan goes straight to its Outcome 2),
report, and continue:
```
✓  /l3io-plan rebuilt the plan and pointer; {current_plan_file} exists. Continuing with it.
```

**Outcome 2 — The remedy succeeds and the condition persists.** If the target is still
missing:
```
BLOCKED: plan-output-meta.yaml points at {current_plan}, which does not exist in
{planning_artifacts}. I ran /l3io-plan and the pointer names a missing file after it. This needs a
decision.
```

**Outcome 3 — The remedy fails.** If `/l3io-plan` errors or halts:
```
BLOCKED: plan-output-meta.yaml points at {current_plan}, which does not exist in
{planning_artifacts}. I ran /l3io-plan and it failed: {failure}. No other snapshot is
substituted.
```

Read the snapshot file. Extract and bind:
- `{plan_phases}` — ordered list of phases, each with `parallel` flag and `epics` list
- `{plan_generated}` — ISO timestamp
- `{plan_confidence}` — overall confidence (lowest across phases)

## 2b. Staleness check

The plan is a snapshot of state at `{plan_generated}`. State moves on; the plan does not. Check
whether anything in the state tree has changed since the snapshot was built:

```bash
find {pm_state_root} -name '*.yaml' -newermt "{plan_generated}" -print -quit
```

If this prints a path, state has changed since the plan was generated:
```
⚠️  Plan generated {plan_generated}; project state has changed since.
    Epics may have been added, completed, or re-scoped. Sections 2c–4 report what differs.
    Re-run /l3io-plan for a current plan.
```
Warn and continue — the reconcile in 2c is what actually protects execution.

This is an advisory mtime heuristic: a fresh `git clone` or `git checkout` rewrites mtimes and
can make a current plan look stale. Never halt on it, and never skip 2c because it printed
nothing.

## 2c. Reconcile plan against state

Compare the epic set in `{plan_phases}` against the epic set actually in state. Both directions
matter and neither is caught anywhere else in this skill.

```bash
ls -d {pm_state_root}/planned/epic-*/ {pm_state_root}/active/epic-*/ 2>/dev/null
```

Bind `{state_epic_keys}` = the `E{nnn}` key for each directory found (`epic-001` → `E001`).

**In state but not in any plan phase** — created after the plan was built. Under
`{exec_scope}=full` these would silently never run:
```
⚠️  Not in the plan, will NOT be executed: {missing_from_plan_keys}
    Re-run /l3io-plan to include them.
```

**In the plan but not in `planned/` or `active/`** — the epic is done (under `archived/`) or was
deleted. Drop it from `{execution_phases}`:
```
⏭️  In the plan but no longer pending, dropped from this run: {stale_plan_keys}
```

Both are warnings, not blocks — an out-of-date plan is a normal state to execute from, as long
as the divergence is reported rather than silently acted on. Dropping the stale keys here is
belt-and-braces with the `status=done` guard in step-05 §2; keep both, since epic- and
sprint-scoped runs reach step-05 through different paths.

## 3. Resolve execution order for scoped epics

If `{exec_scope}=full`: execution order = phases in sequence; within each parallel phase, epics may run concurrently up to `{max_parallel_subagents}`.

If `{exec_scope}=epic`: find which phase contains `{scope_epic_keys}[0]`. Execute that epic only. Dependencies from prior phases are assumed satisfied (user asserts this by scoping to a single epic).

If the key is in **no** phase, do not block — step-02 already verified it exists in state, and
naming it explicitly is a stronger signal of intent than the snapshot's contents. Warn and
execute it as a single-epic phase of its own:
```
⚠️  {epic_key} is not in the current plan (plan generated {plan_generated}).
    Executing it standalone — no dependency ordering can be checked for it.
```

If `{exec_scope}=sprint`: find the epic and sprint. Execute only that sprint as a headless subagent directly after this step (skip step-04 arch gate for sprint scope).

Bind `{execution_phases}` = resolved ordered list of (phase, [epic_keys], parallel_flag).

## 4. Validate dependencies for full scope

For each phase beyond phase 1, verify that all `dependencies` listed in the phase have `status: done`:

```bash
uv run {pm_status} show --state-root {pm_state_root} --epic {dep_key}
```

Check `status=done` in the output (the epic may currently sit under `active/` or `archived/` —
`show` resolves either). If any dependency is not done:
```
⚠️  Phase N dependency {epic_key} is not done. Phase N epics will be blocked until it completes.
```
Do not halt — log and continue. The epic loop will enforce ordering at runtime.

## 5. Output

```
Step 03 complete — plan: {current_plan_file} (generated {plan_generated}), phases: {count}, confidence: {plan_confidence}, dropped: {stale_plan_keys}, not-in-plan: {missing_from_plan_keys}
```
