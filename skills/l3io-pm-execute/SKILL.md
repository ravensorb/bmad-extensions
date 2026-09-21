---
name: l3io-pm-execute
description: Run the l3io-pm plan — full, single epic, or single sprint. Reads plan-output-meta.yaml and executes epics in phase order, dispatching sprint subagents with full context injection.
---

# l3io-pm-execute

Communicate all responses in `{communication_language}`.

## Conventions

- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives).
- `{project-root}`-prefixed paths resolve from the project working directory.
- Bare paths (e.g. `steps/shared/step-00-activate.md`) resolve from `{skill-root}`.
- `{spec_align}` = `uv run {skill-root}/scripts/spec-align.py --project-root {project-root} --planning-root {planning_artifacts} --impl-root {implementation_artifacts} --state-root {implementation_artifacts}/state --pm-status {project-root}/_bmad/scripts/pm-status.py --spec-paths '{spec_paths}'` — the spec-alignment helper; it never calls a model. `{spec_paths}` is `customize.toml`'s list rendered as JSON (`[]` by default). Step files run it only where `{spec_alignment}` is `true`, except `disposition`, `check-dispositions` and `adrs`, which run either way. Headless sprint subagents receive both bindings in their context block (`steps/execute/step-05-epic-loop.md` §5a).

## On Activation

Run: `uv run {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow`

If the script fails, resolve the `workflow` block by reading `{skill-root}/customize.toml`, then
`{project-root}/_bmad/custom/l3io-pm-execute.toml` (team), then
`{project-root}/_bmad/custom/l3io-pm-execute.user.toml` (personal) in order. Scalars override, arrays append.

Load `{skill-root}/assets/module-setup.md` first **only** when the user passes `setup`,
`configure`, or `install`. Config itself is resolved in step-00-activate per
`{skill-root}/references/config-resolution.md`; an absent `modules.l3io-pm` section means the
module has no overrides, not that it needs setup.

## Execution

**Headless mode** — when `headless: true` is present in the injected context block, load
step-00-activate for variable binding (pm_status path, state dirs), then the sprint steps.
step-01-classify-work is skipped because `{work_type}` is already injected in the context block.
No setup pointer here: this is a dispatched sprint subagent, not the entry a user is starting
work from, and it inherits `{session_id}` from the orchestrator that dispatched it, which
already had its own chance to print the pointer.

```
{skill-root}/steps/shared/step-00-activate.md
{skill-root}/steps/sprint/step-02-story-prep.md
{skill-root}/steps/sprint/step-03-dev-loop.md
{skill-root}/steps/sprint/step-04-sprint-closure.md
```

**Normal mode** — no `headless: true` in context. Load shared steps, then execute steps in order:

```
{skill-root}/steps/shared/step-00-activate.md
```

Once `{session_id}` is bound and before reading any further state, apply the once-per-session
setup pointer (`{skill-root}/references/config-resolution.md` §5) — this skill is one of the
two orchestrators the pointer is scoped to:

```bash
uv run {pm_status} notice --state-root {pm_state_root} \
  --session-id {session_id} --key setup-pointer && \
  echo "l3io-pm has no project settings. /l3io-pm-setup configures it if you want to."
```

Exit 1 means it was already said this session — print nothing and continue. Never halt on it.

```
{skill-root}/steps/shared/step-01-classify-work.md
{skill-root}/steps/execute/step-02-scope-resolve.md
{skill-root}/steps/execute/step-03-load-plan.md
{skill-root}/steps/execute/step-04-arch-gate.md
{skill-root}/steps/execute/step-05-epic-loop.md
{skill-root}/steps/execute/step-06-epic-closure.md
```
