# Cost Optimization: Per-Role Model Routing and Turn-Count Reduction — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add configurable per-role model selection to l3io-pm dispatch and reduce fix-loop turn count via two-tier test scoping and a per-story turn cap.

**Architecture:** Six new `modules.l3io-pm` config keys route story dev, review, prep, and closure agents to different models based on story classification; `max_turns_per_story` flows through `customize.toml` → `{agent_contract}`; test guidance in the dev loop distinguishes fix-iteration scope from final full-suite verification. All changes are in `skills/_shared/` canonical sources; `npm run sync:scripts` propagates them to per-skill copies.

**Tech Stack:** Markdown step files, TOML config, `pm-status.py` (Python — read-only, no changes required), `npm run sync:scripts` / `check:scripts` / `write-payload-manifest.mjs` / `check:manifest`.

**Spec:** [docs/superpowers/specs/2026-08-31-cost-optimization-model-routing-design.md](../specs/2026-08-31-cost-optimization-model-routing-design.md)

> **Note — spec correction:** The spec states classification is "printed by `pm-status.py show --epic {epic_key} --sprint {sprint_num}`". Research shows `show --sprint` prints only `key status` per story (no classification). The correct approach is a direct YAML field read (Task 5 below). `claude-sonnet-5` is already in `pm-status.py`'s rate table — no script changes are needed.

## Global Constraints

- Never edit per-skill `steps/`, `references/`, or `scripts/` copies directly — always edit `skills/_shared/` and sync
- `max_turns_per_story` goes only in pm-execute, pm-plan, pm-sync customize.toml (the three skills that ship step-00-digest.md as payload)
- All six model keys default to `{model}` when absent — zero behavior change until a project sets them
- `set-actual --model` must receive the model that actually ran; the context block `model:` binding serves this purpose

---

## File Map

| File | Action | What changes |
|---|---|---|
| `skills/_shared/config-resolution.md` | Modify | Add 6 new binding rows to §3 table; add `max_turns_per_story` note |
| `skills/_shared/steps/shared/step-00-activate.md` | Modify | §1 — extract and bind 6 new model keys after `{model}` |
| `skills/_shared/steps/shared/step-00-digest.md` | Modify | `{agent_contract}` block — add turn-cap rule |
| `skills/_shared/steps/execute/step-05-epic-loop.md` | Modify | §5a model_prep, §5b story model resolution + all model_* in context, §5c model_closure |
| `skills/_shared/steps/sprint/step-03-dev-loop.md` | Modify | §3 model_review hint; §4 two-tier test strategy |
| `skills/l3io-pm-execute/customize.toml` | Modify | Add `max_turns_per_story = 120` |
| `skills/l3io-pm-plan/customize.toml` | Modify | Add `max_turns_per_story = 120` |
| `skills/l3io-pm-sync/customize.toml` | Modify | Add `max_turns_per_story = 120` |

Auto-updated by `npm run sync:scripts` (do NOT edit these directly):
- All per-skill `steps/shared/`, `steps/execute/`, `steps/sprint/`, `references/` copies

---

## Task 1: Update config-resolution.md — document new bindings

**Files:**
- Modify: `skills/_shared/config-resolution.md` (§3 binding table)

**Interfaces:**
- Produces: documented defaults for `{model_story_simple}`, `{model_story_standard}`, `{model_story_complex}`, `{model_review}`, `{model_prep}`, `{model_closure}` used by step-00-activate.md (Task 3)

No automated test for markdown prose. The CI `check:docs` check (9) validates authoring paths — we are not adding any `skills/_shared/` references. Manual verification: read the rendered table.

- [ ] **Open** `skills/_shared/config-resolution.md` and find §3 "Binding values". The current table ends at the `{token_rates_json}` row.

- [ ] **Insert** 6 new rows immediately after the `{model}` row (before `{token_rates_json}`):

  Find this text in the table:
  ```
  | `{model}` | `modules.l3io-pm.default_model` | `claude-opus-5` (`DEFAULT_ESTIMATE_MODEL` in `pm-status.py`) |
  | `{token_rates_json}` | `modules.l3io-pm.token_rates`, **JSON-encoded** | empty — the shipped rate table applies unchanged |
  ```

  Replace with:
  ```
  | `{model}` | `modules.l3io-pm.default_model` | `claude-opus-5` (`DEFAULT_ESTIMATE_MODEL` in `pm-status.py`) |
  | `{model_story_simple}` | `modules.l3io-pm.model_story_simple` | `{model}` |
  | `{model_story_standard}` | `modules.l3io-pm.model_story_standard` | `{model}` |
  | `{model_story_complex}` | `modules.l3io-pm.model_story_complex` | `{model}` |
  | `{model_review}` | `modules.l3io-pm.model_review` | `{model}` |
  | `{model_prep}` | `modules.l3io-pm.model_prep` | `{model}` |
  | `{model_closure}` | `modules.l3io-pm.model_closure` | `{model}` |
  | `{token_rates_json}` | `modules.l3io-pm.token_rates`, **JSON-encoded** | empty — the shipped rate table applies unchanged |
  ```

- [ ] **Append** a note about `max_turns_per_story` at the end of §3 (after the `{token_rates_json}` explanatory paragraph):

  ```
  `{max_turns_per_story}` is resolved from `customize.toml` `[workflow]` (not from BMad config) by
  the BMad harness at skill load time. It is carried in `{agent_contract}` as a soft turn cap for
  story dev agents. Default: `120`.
  ```

- [ ] **Commit:**
  ```bash
  git add skills/_shared/config-resolution.md
  git commit -s -m "docs(l3io-pm): document per-role model routing config keys and turn cap binding"
  ```

---

## Task 2: Add max_turns_per_story to customize.toml (three skills)

**Files:**
- Modify: `skills/l3io-pm-execute/customize.toml`
- Modify: `skills/l3io-pm-plan/customize.toml`
- Modify: `skills/l3io-pm-sync/customize.toml`

**Interfaces:**
- Produces: `{max_turns_per_story}` binding available to step-00-digest.md agent_contract (Task 4)

Only these three skills ship `step-00-digest.md` as payload (confirmed: `find skills/ -name step-00-digest.md` returns only these three). pm-help, sec-redteam, arch-review, util-doctor, and util-cleanup do not.

- [ ] **In each of the three files**, find the `# Fix loops` block (which contains `max_fix_iterations`). Add `max_turns_per_story` in the same block — it is a per-story cap on the same principle.

  In `skills/l3io-pm-execute/customize.toml`, find:
  ```toml
  # Fix loops
  max_fix_iterations          = 3    # CODE and MIXED work — each iteration is a turn multiplier
  max_fix_iterations_non_code = 3    # DOCS and CONFIG work
  ```
  Replace with:
  ```toml
  # Fix loops
  max_fix_iterations          = 3    # CODE and MIXED work — each iteration is a turn multiplier
  max_fix_iterations_non_code = 3    # DOCS and CONFIG work
  max_turns_per_story         = 120  # soft cap per story agent; self-monitored, not mechanically enforced
  ```

- [ ] **Apply the same edit** to `skills/l3io-pm-plan/customize.toml` — find its `max_fix_iterations` block and add the same `max_turns_per_story = 120` line.

- [ ] **Apply the same edit** to `skills/l3io-pm-sync/customize.toml` — same pattern.

- [ ] **Commit:**
  ```bash
  git add skills/l3io-pm-execute/customize.toml \
          skills/l3io-pm-plan/customize.toml \
          skills/l3io-pm-sync/customize.toml
  git commit -s -m "feat(l3io-pm): add max_turns_per_story soft cap to customize.toml"
  ```

---

## Task 3: Update step-00-activate.md — extract six model bindings

**Files:**
- Modify: `skills/_shared/steps/shared/step-00-activate.md` (§1)

**Interfaces:**
- Consumes: `{model}` already bound from `modules.l3io-pm.default_model`
- Produces: `{model_story_simple}`, `{model_story_standard}`, `{model_story_complex}`, `{model_review}`, `{model_prep}`, `{model_closure}` — used by step-05-epic-loop.md (Task 5) and step-03-dev-loop.md (Task 6)

- [ ] **Open** `skills/_shared/steps/shared/step-00-activate.md`. Find §1 "Load module configuration". Locate the bullet that binds `{model}`:

  ```
  - `{model}` — `modules.l3io-pm.default_model` (default `claude-opus-5`). The model id every
    `cost` in this project is priced against. Pass it as `--model {model}` on `estimate-story`,
    `estimate-rollup`, and every `set-actual` that carries token counts. **Not optional** —
  ```

- [ ] **Insert** the following six bullets immediately after the `{model}` bullet (before the `{token_rates_json}` bullet):

  ```
  - `{model_story_simple}` — `modules.l3io-pm.model_story_simple` (default `{model}`). Model
    used when dispatching a story dev agent for a `classification: simple` story. Used as the
    `model:` binding in the dispatch context block and as `--model` on that story's `set-actual`.
  - `{model_story_standard}` — `modules.l3io-pm.model_story_standard` (default `{model}`). Same
    for `classification: standard` stories.
  - `{model_story_complex}` — `modules.l3io-pm.model_story_complex` (default `{model}`). Same
    for `classification: complex` stories.
  - `{model_review}` — `modules.l3io-pm.model_review` (default `{model}`). Model used when
    dispatching `bmad-code-review` from the dev loop. Passed through dispatch context so the dev
    loop agent can use it when spawning the reviewer.
  - `{model_prep}` — `modules.l3io-pm.model_prep` (default `{model}`). Model for sprint prep
    agents.
  - `{model_closure}` — `modules.l3io-pm.model_closure` (default `{model}`). Model for sprint
    and epic closure agents.
  ```

- [ ] **Verify** §1 still reads coherently — the new bullets should appear between `{model}` and `{token_rates_json}`.

- [ ] **Commit:**
  ```bash
  git add skills/_shared/steps/shared/step-00-activate.md
  git commit -s -m "feat(l3io-pm): bind six per-role model keys at activation"
  ```

---

## Task 4: Update step-00-digest.md — add turn cap to agent_contract

**Files:**
- Modify: `skills/_shared/steps/shared/step-00-digest.md`

**Interfaces:**
- Consumes: `{max_turns_per_story}` from customize.toml (Task 2)
- Produces: updated `{agent_contract}` text carried into every spawned story dev and review agent

- [ ] **Open** `skills/_shared/steps/shared/step-00-digest.md`. Find the `{agent_contract}` block — it is the fenced code block under "Never poll — arm one background wait and stop". The block ends with:

  ```
  - Your final line must be exactly one of `DONE — [brief metrics]`,
    `BLOCKED: [one-line reason]`, or `FAILED: [one-line reason]`.
  ```

- [ ] **Insert** the following as a new bullet immediately before the final line bullet:

  ```
  - Stay under {max_turns_per_story} turns for this story. As you approach the cap, skip
    optional verification passes, write what you have completed, and end.
  ```

  The block end should look like:
  ```
  - Stay under {max_turns_per_story} turns for this story. As you approach the cap, skip
    optional verification passes, write what you have completed, and end.
  - Your final line must be exactly one of `DONE — [brief metrics]`,
    `BLOCKED: [one-line reason]`, or `FAILED: [one-line reason]`.
  ```

- [ ] **Commit:**
  ```bash
  git add skills/_shared/steps/shared/step-00-digest.md
  git commit -s -m "feat(l3io-pm): add per-story turn cap to agent_contract"
  ```

---

## Task 5: Update step-05-epic-loop.md — per-role model dispatch

**Files:**
- Modify: `skills/_shared/steps/execute/step-05-epic-loop.md` (§5a, §5b, §5c)

**Interfaces:**
- Consumes: `{model_prep}`, `{model_story_simple/standard/complex}`, `{model_closure}`, `{model_review}`, `{max_turns_per_story}` (Tasks 2–4)
- Produces: dispatch context blocks that carry all model_* bindings so prep, story, closure, and review agents can use them

This task has three sub-changes. Apply them in order.

### 5a. Prep dispatch context — use model_prep

- [ ] **Open** `skills/_shared/steps/execute/step-05-epic-loop.md`. Find §5a "Prep the sprint". Locate the dispatch context block that begins `# l3io-pm execution context [AUTHORITATIVE`. Find the line:

  ```
  model: {model}
  ```

  Replace it with:
  ```
  model: {model_prep}
  model_story_simple: {model_story_simple}
  model_story_standard: {model_story_standard}
  model_story_complex: {model_story_complex}
  model_review: {model_review}
  model_prep: {model_prep}
  model_closure: {model_closure}
  max_turns_per_story: {max_turns_per_story}
  ```

  (The `token_rates_json`, `runtime`, and `session_id` lines follow and are unchanged.)

### 5b. Story dispatch context — per-classification model selection

- [ ] **Find** §5b "One agent per story". Locate the instruction text before the dispatch context block. **Insert** the following classification resolution logic between the `For each {story_key} in that order:` line and the `python3 {pm_status} dispatch ... --event open` command:

  ```
  Before dispatching, read the story's `classification` field to select the correct model:

  ```bash
  story_yaml=$(find {pm_state_root} -name "{story_key}.yaml" 2>/dev/null | head -1)
  story_classification=$(grep -m1 "^classification:" "$story_yaml" 2>/dev/null | awk '{print $2}' || echo "standard")
  ```

  Resolve `{story_model}` from `{story_classification}`:
  - `simple`  → `{model_story_simple}`
  - `standard` → `{model_story_standard}`
  - `complex`  → `{model_story_complex}`
  - anything else (absent, unknown) → `{model}` (safe fallback — never blocks dispatch)
  ```

- [ ] **In the story dispatch context block** (the one that begins `# l3io-pm execution context`), find:

  ```
  model: {model}
  ```

  Replace it with:
  ```
  model: {story_model}
  model_story_simple: {model_story_simple}
  model_story_standard: {model_story_standard}
  model_story_complex: {model_story_complex}
  model_review: {model_review}
  model_prep: {model_prep}
  model_closure: {model_closure}
  max_turns_per_story: {max_turns_per_story}
  ```

- [ ] **Add** an instruction after the dispatch context block (before the `Close the bracket, then branch:` line) to use `{story_model}` as the Agent tool's model parameter:

  ```
  **Use `{story_model}` as the model parameter** when calling the Agent tool to spawn this story
  subagent. The context block's `model: {story_model}` binding is for pricing via `set-actual
  --model`; the Agent tool parameter is what determines which model actually runs.
  ```

### 5c. Closure dispatch context — use model_closure

- [ ] **Find** §5c "Close the sprint". The prose says "Dispatch with the same context block as 5a". **Add** a clarification sentence immediately after that:

  ```
  Use `model: {model_closure}` (not `{model_prep}`) in the context block for closure. All other
  model_* bindings and `max_turns_per_story` are the same as §5a.
  ```

- [ ] **Commit:**
  ```bash
  git add skills/_shared/steps/execute/step-05-epic-loop.md
  git commit -s -m "feat(l3io-pm): per-role model routing in epic loop dispatch (prep/story/closure)"
  ```

---

## Task 6: Update step-03-dev-loop.md — model_review and two-tier test strategy

**Files:**
- Modify: `skills/_shared/steps/sprint/step-03-dev-loop.md` (§3, §4)

**Interfaces:**
- Consumes: `{model_review}` carried in dispatch context block from step-05-epic-loop.md (Task 5)
- Produces: code-review subagents dispatched on `{model_review}`; story agents that run scoped tests during fix iterations and full suite only at end

### 6a. §3 — use model_review when spawning bmad-code-review

- [ ] **Open** `skills/_shared/steps/sprint/step-03-dev-loop.md`. Find §3 "For each story: code review". Locate the paragraph beginning "Spawn `bmad-code-review` subagent with:". **Append** the following as a new bullet in the spawn list (after "the `{agent_contract}` (verbatim…)" bullet):

  ```
  - **Use `{model_review}` as the model parameter** when calling the Agent tool. The context
    block already received `model_review: {model_review}` from the epic loop dispatch; use it
    here. If the context block does not carry `model_review`, fall back to `{model}`.
  ```

### 6b. §4 — two-tier test strategy

- [ ] **Find** §4 "Write completion evidence and story actuals". Locate the sub-section "Determining the required set. Work from the files this story changed, in this order:" and the three numbered bullets that follow it (ending at "3. Record every command you ran…").

  **Replace** the entire "Determining the required set" paragraph and its three bullets with:

  ```markdown
  **Two-tier test strategy — fix iterations vs. final verification.**

  **During fix iterations** (each bmad-dev-story re-dispatch in §3): run only the tests covering
  the files you changed. Use the project's per-module test command, a pattern-matched test file
  path, or the narrowest scope you can establish with confidence. Do not run the full test suite
  during a fix pass — each full-suite run executes at the deepest, most expensive point in the
  session and is re-read on every subsequent turn.

  **After the final iteration — or if no fix was needed:** run the full test suite once before
  writing completion evidence. This is the single mandatory full-suite run per story agent session.

  **Cap:** the full test suite runs at most once per story agent session, regardless of how many
  fix iterations occurred. If you ran the full suite at the end of a fix iteration and no
  further iteration was needed, that run is the final verification — do not re-run it.

  **Determining the required set.** Work from the files this story changed, in this order:

  1. If the project maps areas to test commands — a per-package script, a suite whose path
     mirrors the source tree, a command documented in `CLAUDE.md` or the README — run the
     commands covering the changed files during fix iterations, or all commands for final
     verification.
  2. If you cannot establish a scoped mapping for the fix-iteration run with confidence, **skip
     the scoped run during that iteration** — do not substitute the full suite. Run the full
     suite only once at final verification.
  3. Record every command you ran, including ones that failed. A failing run belongs in the
     record — it is what makes the derived boolean mean anything.
  ```

- [ ] **Commit:**
  ```bash
  git add skills/_shared/steps/sprint/step-03-dev-loop.md
  git commit -s -m "feat(l3io-pm): model_review routing and two-tier test strategy in dev loop"
  ```

---

## Task 7: Sync shared files, regenerate manifests, verify CI checks

**Files:**
- Auto-updated: all per-skill `steps/` and `references/` copies
- Auto-updated: all per-skill `payload-manifest.json`

- [ ] **Run sync** to propagate all `skills/_shared/` edits to per-skill copies:

  ```bash
  npm run sync:scripts
  ```

  Expected: the script reports which files it copied. It should touch per-skill copies of:
  - `steps/shared/step-00-activate.md`
  - `steps/shared/step-00-digest.md`
  - `steps/execute/step-05-epic-loop.md`
  - `steps/sprint/step-03-dev-loop.md`
  - `references/config-resolution.md`

  in pm-execute, pm-plan, and pm-sync (the skills that receive shared steps).

- [ ] **Verify sync is clean:**

  ```bash
  npm run check:scripts
  ```

  Expected: exits 0 with no drift reported.

- [ ] **Regenerate all payload manifests** (payload files changed — hashes have moved):

  ```bash
  node scripts/write-payload-manifest.mjs
  ```

  Expected: outputs one line per skill reporting the manifest was written.

- [ ] **Verify manifests are correct:**

  ```bash
  npm run check:manifest
  ```

  Expected: exits 0 with all manifests verified.

- [ ] **Run docs check** to confirm no cross-reference is broken:

  ```bash
  npm run check:docs
  ```

  Expected: exits 0. The six new config keys are new additions, not quoted in existing docs yet,
  so check (5) is unaffected. Check (9) (authoring-paths) is unaffected — no `skills/_shared/`
  paths were added to step files.

- [ ] **Commit all synced files and manifests:**

  ```bash
  git add skills/
  git commit -s -m "chore(l3io-pm): sync shared steps and regenerate payload manifests after model routing changes"
  ```

- [ ] **Final sanity check — confirm the three customize.toml files are not in the sync diff** (they are per-skill edits, not synced from _shared):

  ```bash
  git show --stat HEAD | grep customize
  ```

  Expected: no customize.toml files in the last commit (they were committed in Task 2).

---

## Self-Review

**Spec coverage check:**

| Spec section | Task |
|---|---|
| 6 new `modules.l3io-pm` config keys | Task 1 (doc) + Task 3 (binding) + Task 5 (dispatch) |
| `max_turns_per_story` in customize.toml | Task 2 |
| step-00-activate.md §1 extract bindings | Task 3 |
| step-00-digest.md agent_contract turn cap | Task 4 |
| step-05-epic-loop.md §5a model_prep | Task 5a |
| step-05-epic-loop.md §5b story model resolution | Task 5b |
| step-05-epic-loop.md §5c model_closure | Task 5c |
| step-03-dev-loop.md §3 model_review | Task 6a |
| step-03-dev-loop.md §4 two-tier test strategy | Task 6b |
| npm run sync:scripts + manifests + CI | Task 7 |

All spec sections covered. No gaps found.

**Placeholder scan:** No TBDs, TODOs, or vague steps. All code blocks contain actual content.

**Consistency check:**
- `{story_model}` is resolved before the dispatch and used in both the context block `model:` and the Agent tool call — consistent.
- `{model_review}` is bound at activation (Task 3), carried in all three dispatch context blocks (Task 5), and consumed in step-03-dev-loop.md §3 (Task 6a) — chain is complete.
- `{max_turns_per_story}` defined in customize.toml (Task 2), documented in config-resolution.md (Task 1), added to agent_contract in step-00-digest.md (Task 4) — chain is complete.
