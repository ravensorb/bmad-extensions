---
name: l3io-pm-help
description: Read project state and recommend the exact next l3io-pm action. Use /l3io-pm-help progress to forward to /l3io-util-doctor stats for a plan-aware progress tree — which phase, epic, sprint, and stories are in flight.
---

# l3io-pm-help

Communicate all responses in `{communication_language}`.

## Overview

Reads project state and recommends the exact next l3io-pm action.

**Default behavior (no argument, or an unrecognized/natural-language description):** load and
run, in order, `steps/step-01-config.md`, `steps/step-02-detect-layout.md`,
`steps/step-03-read-state.md`, `steps/step-04-health-snapshot.md`, then
`steps/step-05-recommend.md`, and report the recommendation.

**Recognized keywords** — if the user's argument exactly matches one of these, load the file
below instead of continuing to `steps/step-03-read-state.md`. `list plan` loads
`steps/step-01-config.md` and `steps/step-02-detect-layout.md` first, as usual; `progress`
does not — see the per-keyword notes in On Activation for why:

| Keyword | Load | Notes |
|---|---|---|
| `progress` | `steps/mode-progress.md` | read-only — forwards to `/l3io-util-doctor stats`; no config/layout load first, it is a pure pass-through |
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

**Recognized argument — `progress`:** load and run `steps/mode-progress.md` only, and stop.
`steps/mode-progress.md` is a pure forwarder to `skill:l3io-util-doctor stats` — it reads no
config and no state itself, so it has nothing for `steps/step-01-config.md` or
`steps/step-02-detect-layout.md` to resolve in advance. This is a deliberate change from
before this mode became a forwarder: it used to run both steps first because it read
`{pm_state_root}` and `{pm_status}` directly and needed the layout gate to avoid
recommending a fresh backlog over a legacy tree. `l3io-util-doctor stats`'s own layout check
(`steps/stats.md` Step ST1) reproduces the one branch that actually mattered here — it BLOCKs
with no tree rendered when more than one state layout is present, the same condition and
severity as this skill's own gate and as `l3io-util-doctor`'s health-check Check 2b — so
running the gate here too would duplicate that specific check and risk the two skills
disagreeing on the legacy-layout message. It is not a full copy of every branch
`step-02-detect-layout.md` has: the orphan check for a possible first run (repointed
`implementation_artifacts` hiding real state) has no counterpart in `stats.md` today. If
`l3io-util-doctor` is not installed at all (so its own layout check never runs), the
forwarder in `steps/mode-progress.md` says so and stops — see that file.

**Recognized argument — `list plan`:** load and run `steps/step-01-config.md` and
`steps/step-02-detect-layout.md` exactly as written, then load and run
`steps/mode-list-plan.md` and stop — do not load `steps/step-03-read-state.md` onward. The
layout gate still applies: a legacy tree short-circuits to the migration recommendation,
because the epic status probes only understand the sharded layout. Unlike `progress`,
`list plan` still reads state directly in this skill, so it still needs both steps.

**Everything else** (no argument, or an unrecognized/natural-language description) → load and
run `steps/step-01-config.md` through `steps/step-05-recommend.md`, in order.

**Load only what the argument selects.** Every step or mode file read is paid for on every
later turn of the session — the default path never needs the mode files, a mode path never
needs `steps/step-03-read-state.md` onward, and `progress` needs neither `steps/step-01-config.md`
nor `steps/step-02-detect-layout.md` at all — it is the cheapest path through this skill.
