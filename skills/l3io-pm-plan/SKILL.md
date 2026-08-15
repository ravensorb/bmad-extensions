---
name: l3io-pm-plan
description: Validate readiness, elaborate stories, estimate, build dependency graph, and produce an executable plan. Use /l3io-pm-plan for a full plan, /l3io-pm-plan estimate [E{nnn}|E{nnn}-S{nn}] to re-estimate only.
---

# l3io-pm-plan

Communicate all responses in `{communication_language}`.

## Conventions

- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives).
- `{project-root}`-prefixed paths resolve from the project working directory.
- Bare paths (e.g. `steps/shared/step-00-activate.md`) resolve from `{skill-root}`.

## On Activation

Run: `python3 {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow`

If the script fails, resolve the `workflow` block by reading `{skill-root}/customize.toml`, then `{project-root}/_bmad/custom/l3io-pm-plan.toml` (team), then `{project-root}/_bmad/custom/l3io-pm-plan.user.toml` (personal) in order. Scalars override, arrays append.

If `{project-root}/_bmad/config.yaml` does not have an `l3io-pm` section — or the user passes `setup`, `configure`, or `install` — load `{skill-root}/assets/module-setup.md` first.

## Execution

**All modes — load first:**
```
{skill-root}/steps/shared/step-00-activate.md
{skill-root}/steps/shared/step-01-classify-work.md
```

**Full plan mode** (default — no args, or args that do not start with `estimate`):

Bind `{scope}` = `all` before loading step-estimate.

```
{skill-root}/steps/plan/step-02-readiness-check.md
{skill-root}/steps/plan/step-03-story-elaboration.md   ← skipped if work_type is DOCS or CONFIG
{skill-root}/steps/plan/step-04-load-state.md
{skill-root}/steps/plan/step-05-dependency-graph.md
{skill-root}/steps/shared/step-estimate.md
{skill-root}/steps/plan/step-06-plan-output.md
```

**Estimate mode** (args start with `estimate`):

Parse scope from arg: `estimate` → `{scope}=all`; `estimate E{nnn}` → `{scope}=E{nnn}`; `estimate E{nnn}-S{nn}` → `{scope}=E{nnn}-S{nn}`. Then load:
```
{skill-root}/steps/shared/step-estimate.md
```
Output estimate summary only. No graph, no elaboration, no plan document.
