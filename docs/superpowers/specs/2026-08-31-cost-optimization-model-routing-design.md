# Cost Optimization: Per-Role Model Routing and Turn-Count Reduction

**Date:** 2026-08-31
**Status:** Draft

---

## Problem

E003 and E004 story actuals show that 97–98% of tokens are `cache_read`, not fresh reads. The
mechanism is multiplication: cost ≈ Σ(context_size at each turn). Every tool call re-reads the
full accumulated transcript, so a token read early is paid for again on every subsequent turn.

Two structural drivers remain unaddressed at the framework level:

1. **Uniform model selection.** Every dispatched agent — simple stories, complex stories, code
   review, sprint closure — runs on `default_model` (`claude-opus-5`). Sonnet is ~3× cheaper per
   token on every class and adequate for the majority of story work.

2. **Full test suites on every fix iteration.** The current test guidance makes full-suite the
   fallback with no distinction between fix passes and final verification. A story that runs three
   fix iterations with a full suite each time (e.g., 90-file Vitest + selftest at 4.5 min) may
   accumulate 60–90 extra turns, all carrying the deepest, most expensive context of the session.

Measurements from production runs (E003: 1.25B tokens, 23 story agents; E004: 184M tokens, 8
story agents) confirm the turn axis dominates. The cheapest lever is fewer turns; context size
matters only when turns come down too.

---

## Goals

- Make model selection configurable per agent role and per story complexity class, defaulting to
  current behavior when unset.
- Reduce turn count in the fix loop by scoping tests to changed files during iterations and
  running the full suite at most once, at the end.
- Add an explicit per-story turn cap that agents carry in their contract.

## Non-goals

- Story batching (combining multiple simple stories into one agent session) — deferred; failure
  handling complexity outweighs the marginal gain after model routing lands.
- Reducing what agents read (context discipline is already addressed in step-00-digest.md and
  step-03-dev-loop.md §2; no changes needed).
- Changing how reviews are spawned — already a separate subagent by design; E003 inlining was a
  one-off workaround.

---

## Design

### 1. New config keys (`modules.l3io-pm`)

Six optional keys in the BMad config system under `modules.l3io-pm`. All default to
`modules.l3io-pm.default_model` when absent. No behavior change until a project sets them.

| Key | Controls | Default |
|---|---|---|
| `model_story_simple` | Story dev agent, `classification: simple` | `{model}` |
| `model_story_standard` | Story dev agent, `classification: standard` | `{model}` |
| `model_story_complex` | Story dev agent, `classification: complex` | `{model}` |
| `model_review` | Code review agent (`bmad-code-review`) spawned from dev loop | `{model}` |
| `model_prep` | Sprint prep agent | `{model}` |
| `model_closure` | Sprint and epic closure agents | `{model}` |

**Example project config** (`_bmad/custom/config.user.toml` — gitignored, user-scoped):

```toml
[modules.l3io-pm]
default_model        = "claude-opus-5"
model_story_simple   = "claude-sonnet-5"
model_story_standard = "claude-sonnet-5"
model_story_complex  = "claude-opus-5"
model_review         = "claude-opus-5"
# model_prep and model_closure unset → inherit default_model
```

**Pricing accuracy.** `set-actual --model` must receive the model the agent actually ran on. The
context block's `model:` binding serves this purpose: each dispatch passes the resolved model for
that role/classification, and the receiving agent uses it for `--model` on every `set-actual` and
`verify` call. A `{story_model}` that differs from `{model}` means the calibration sample is
priced at `{story_model}` — correct, because that is what ran.

### 2. Turn cap config (`customize.toml`)

Add to the `[workflow]` section of **pm-execute, pm-plan, and pm-sync** only — the three skills
that carry `step-00-digest.md` as payload (confirmed by `find skills/ -name step-00-digest.md`).
pm-help, sec-redteam, arch-review, util-doctor, and util-cleanup do not ship the digest and do
not need this key.

```toml
max_turns_per_story = 120   # soft cap; story agents self-monitor and wrap early
```

The BMad harness resolves this at skill load time; it becomes available as `{max_turns_per_story}`
in the orchestrator's context. The cap is soft — no mechanical enforcement — but it is carried
verbatim in `{agent_contract}` so every dispatched story agent sees it.

`claude-sonnet-5` is already in `pm-status.py`'s shipped rate table ($3/M input, $15/M output,
$3.75/M cache_write, $0.30/M cache_read) — no changes to `pm-status.py` are required for
model routing to price correctly.

### 3. Changes to `step-00-activate.md` §1

After binding `{model}` from `modules.l3io-pm.default_model`, extract and bind the six per-role
keys:

```
{model_story_simple}   ← modules.l3io-pm.model_story_simple   (default: {model})
{model_story_standard} ← modules.l3io-pm.model_story_standard (default: {model})
{model_story_complex}  ← modules.l3io-pm.model_story_complex  (default: {model})
{model_review}         ← modules.l3io-pm.model_review         (default: {model})
{model_prep}           ← modules.l3io-pm.model_prep           (default: {model})
{model_closure}        ← modules.l3io-pm.model_closure        (default: {model})
```

All six, plus `max_turns_per_story`, are carried through every dispatch context block so
downstream agents have them for prompt construction and pricing.

### 4. Changes to `step-05-epic-loop.md`

**§5a — Prep dispatch context block:** replace `model: {model}` with `model: {model_prep}`.
Include all six `model_*` bindings in the context block so the prep agent has them if needed.

**§5b — Story dispatch:** before spawning each story agent, resolve `{story_model}` from the
story's `classification` field:

```
simple   → {model_story_simple}
standard → {model_story_standard}
complex  → {model_story_complex}
absent or unknown → {model}  (safe fallback — never blocks)
```

The story's classification is already stored in its YAML node and printed by
`pm-status.py show --epic {epic_key} --sprint {sprint_num}`. Read it from there; do not re-open
the story file separately.

Replace `model: {model}` in the dispatch context block with `model: {story_model}`. Also include
all six `model_*` bindings so the dev-loop agent can pass `{model_review}` when it spawns
`bmad-code-review`.

**Use `{story_model}` as the model parameter** when calling the Agent tool to spawn the story
subagent. This is what determines which model actually runs; the context block `model:` binding is
for pricing.

**§5c — Closure dispatch context block:** replace `model: {model}` with `model: {model_closure}`.
Include all six `model_*` bindings.

### 5. Changes to `step-03-dev-loop.md`

**§3 — Code review spawn:** when spawning `bmad-code-review`, use `{model_review}` as the model
parameter. The agent_contract note for reviewers already scopes them tightly to the diff; no
other changes to §3.

**§4 — Test strategy (two-tier rule):** replace the current "full-suite is the fallback" guidance
with:

> **During fix iterations (§3 dev re-pass):** run only the tests covering the files you changed.
> Use the project's per-module test command, pattern-matched test files, or the narrowest scope
> you can establish with confidence. Do not run the full suite during a fix pass — it executes at
> the deepest point in the session and re-reads the longest context on every turn.
>
> **After the final iteration — or if no fix was needed — run the full test suite once** before
> writing completion evidence. This is the only full-suite run per story. If you ran a narrower
> scope during fix iterations and the final full-suite run fails on something outside the changed
> files, that is a finding worth naming in the completion notes; it is not a reason to re-open the
> fix loop.
>
> **Cap:** the full test suite runs at most once per story agent session, regardless of how many
> fix iterations occurred.
>
> **If you cannot establish a scoped command:** note it in the completion notes, skip the scoped
> run during fix iterations, and run the full suite only at the final verification. Do not run the
> full suite during each fix pass as a substitute for scoping — that is what this rule exists to
> prevent.

### 6. Changes to `step-00-digest.md` — `{agent_contract}`

Add one rule to the `{agent_contract}` block:

```
- Stay under {max_turns_per_story} turns for this story. As you approach the cap, skip
  optional verification passes, write what you have completed, and end.
```

This binds `{max_turns_per_story}` from the resolved customize.toml value and reaches every
bmad-dev-story and bmad-code-review subagent via the verbatim pass of `{agent_contract}`.

### 7. Changes to `config-resolution.md` §3

Add six rows to the binding table after the existing `{model}` row:

| Binding | Source key | Default |
|---|---|---|
| `{model_story_simple}` | `modules.l3io-pm.model_story_simple` | `{model}` |
| `{model_story_standard}` | `modules.l3io-pm.model_story_standard` | `{model}` |
| `{model_story_complex}` | `modules.l3io-pm.model_story_complex` | `{model}` |
| `{model_review}` | `modules.l3io-pm.model_review` | `{model}` |
| `{model_prep}` | `modules.l3io-pm.model_prep` | `{model}` |
| `{model_closure}` | `modules.l3io-pm.model_closure` | `{model}` |

Also document `max_turns_per_story` (resolved from `customize.toml`, not BMad config) in the
section that documents other customize.toml bindings.

---

## Files Affected

### Modified (canonical sources — never edit per-skill copies):

| File | Section | Change |
|---|---|---|
| `skills/_shared/steps/shared/step-00-activate.md` | §1 | Extract 6 new model bindings |
| `skills/_shared/steps/shared/step-00-digest.md` | `{agent_contract}` | Add turn-cap rule |
| `skills/_shared/steps/execute/step-05-epic-loop.md` | §5a, §5b, §5c | Per-role model in dispatch; story classification → model resolution in §5b |
| `skills/_shared/steps/sprint/step-03-dev-loop.md` | §3, §4 | `{model_review}` in review spawn; two-tier test strategy |
| `skills/_shared/config-resolution.md` | §3 | Document 6 new config keys |

### Modified (per-skill, not shared):

`max_turns_per_story` added only to the three skills that ship `step-00-digest.md` as payload —
confirmed by `find skills/ -name step-00-digest.md`:

| File | Change |
|---|---|
| `skills/l3io-pm-execute/customize.toml` | Add `max_turns_per_story = 120` |
| `skills/l3io-pm-plan/customize.toml` | Add `max_turns_per_story = 120` |
| `skills/l3io-pm-sync/customize.toml` | Add `max_turns_per_story = 120` |

### Auto-synced by `npm run sync:scripts`:

All per-skill `references/config-resolution.md` copies and the shared step files in each skill's
`steps/` directory.

### CI impact:

`check:docs` check (5) validates `customize.toml` values quoted in docs — no doc currently quotes
`max_turns_per_story`, so no check update is needed. Check (4) validates CLI surface of
`pm-status.py` — no `pm-status.py` changes, so no update needed. The six new config keys live in
the BMad config layer, not in `pm-status.py` or `customize.toml`, so check (5) is also unaffected.

---

## Backward Compatibility

All six model keys default to `{model}` when absent. `max_turns_per_story` defaults to 120.
Projects that do not configure the new keys see zero behavior change. A project that previously ran
everything on `claude-opus-5` and sets no overrides continues to do so.

---

## Expected Impact

Based on E003/E004 actuals (~$3/M Sonnet input vs ~$15/M Opus input):

| Lever | Estimated reduction |
|---|---|
| Sonnet for simple + standard stories (~60–70% of story volume) | 2–3× cost reduction on those stories |
| Scoped tests during fix iterations | 20–40% turn reduction in stories with 1+ fix iterations |
| Turn cap | Prevents tail outliers (one story measured 263 turns, 130 of which were polls — already addressed; cap catches future cases) |

The levers are independent and compound. A sprint where 70% of stories are standard-class, all
running on Sonnet, and none running full suites during fix iterations, would plausibly cost 40–60%
of the equivalent Opus-only run.
