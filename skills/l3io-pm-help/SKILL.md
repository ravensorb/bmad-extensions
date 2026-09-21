---
name: l3io-pm-help
description: Read project state and recommend the exact next l3io-pm action. Use /l3io-pm-help progress for a plan-aware progress tree — which phase, epic, sprint, and stories are in flight.
---

# l3io-pm-help

Communicate all responses in `{communication_language}`.

## Overview

Reads project state and recommends the exact next l3io-pm action.

**Default behavior (no argument, or an unrecognized/natural-language description):** load and
run, in order, `steps/step-01-config.md`, `steps/step-02-detect-layout.md`,
`steps/step-03-read-state.md`, `steps/step-04-health-snapshot.md`, then
`steps/step-05-recommend.md`, and report the recommendation.

**Recognized keywords** — if the user's argument exactly matches one of these, load
`steps/step-01-config.md` and `steps/step-02-detect-layout.md` as usual, then load the file
below instead of continuing to `steps/step-03-read-state.md`:

| Keyword | Load | Notes |
|---|---|---|
| `progress` | `steps/mode-progress.md` | read-only — plan-aware progress tree |
| `list plan` | `steps/mode-list-plan.md` | read-only — plan snapshots and their epics |

`setup`, `configure`, and `install` are not recognized arguments — see On Activation.

## On Activation

Run: `uv run {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow`

If the script fails, read `{skill-root}/customize.toml` directly.

`setup`, `configure`, and `install` are not recognized arguments here — `/l3io-pm-setup` is
the module's setup entry point. An absent `modules.l3io-pm` section means the module has no
overrides, not that it needs setup.

Do not add the once-per-project `/l3io-pm-setup` pointer (`config-resolution.md` §5) here:
nothing about it technically requires this to be skipped — it is a placement choice, not a
guard this skill fails. The pointer belongs where a user is about to run PM work and could act
on it; this skill only reads status. It is wired into `l3io-pm-execute`/`l3io-pm-plan` only.

**Recognized argument — `progress`:** load and run `steps/step-01-config.md` (config) and
`steps/step-02-detect-layout.md` (layout detection) exactly as written, then load and run
`steps/mode-progress.md` and stop — do not load `steps/step-03-read-state.md` onward. The
layout gate still applies: a legacy tree short-circuits to the migration recommendation,
because the progress report reads only the sharded layout.

**Recognized argument — `list plan`:** load and run `steps/step-01-config.md` and
`steps/step-02-detect-layout.md` exactly as written, then load and run
`steps/mode-list-plan.md` and stop — do not load `steps/step-03-read-state.md` onward. The
layout gate still applies: a legacy tree short-circuits to the migration recommendation,
because the epic status probes only understand the sharded layout.

**Everything else** (no argument, or an unrecognized/natural-language description) → load and
run `steps/step-01-config.md` through `steps/step-05-recommend.md`, in order.

**Load only what the argument selects.** Every step or mode file read is paid for on every
later turn of the session — the default path never needs the mode files, and a mode path
never needs `steps/step-03-read-state.md` onward.
