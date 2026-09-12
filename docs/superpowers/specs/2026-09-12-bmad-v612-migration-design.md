# BMad v6.12.0 Dependency Migration — Design

**Date:** 2026-09-12
**Status:** proposed
**Approach:** Option A — own the dev step; harvest BMad's ideas, not its orchestrator

## 1. Problem

Two defects, both confirmed empirically by installing `bmad-method@6.12.0` into a throwaway
directory with the command this package's own README prescribes:

```
npx bmad-method install --yes --modules bmm --tools claude-code
```

That install produces `_bmad/core` and `_bmad/bmm` (so `core` is implicit — naming `bmm` alone
is correct) and **29 skills in `.claude/skills/`**.

### 1.1 Three required dependencies do not exist; two more are gone outright

| Declared dependency | Default install | With `--shims` |
|---|---|---|
| `bmad-code-review` | present | present |
| `bmad-qa-generate-e2e-tests` | present | present |
| `bmad-retrospective` | present | present |
| `bmad-create-story` | **absent** | shim only |
| `bmad-dev-story` | **absent** | shim only |
| `bmad-review-adversarial-general` | **absent** | shim only |
| `bmad-ux-review` (optional) | **absent** | **no shim** |
| `bmad-check-implementation-readiness` | **absent** | **no shim** |

`bmad-create-story` and `bmad-dev-story` are spawned unconditionally by the dev loop, so a clean
install per our own instructions cannot run an epic. Shims exist only behind `--shims` and BMad
removes them at the v7 cut, so depending on them is a deadline, not a fix.

Upstream provenance: `bmad-create-story`/`bmad-dev-story` deprecated (#2637, #2641);
`bmad-review-adversarial-general` merged into `bmad-review` as a lens (#2603, #2608);
`bmad-check-implementation-readiness` removed and folded into `bmad-sprint-planning` (#2659).

### 1.2 Presence probes read the wrong directory — and fail silently

Our probes test `.claude/commands/`:

```
steps/execute/step-04-arch-gate.md:34    ls {project-root}/.claude/commands/bmad-agent-architect.md
steps/closure/sprint-closure.md:123      ls {project-root}/.claude/commands/bmad-ux-review.md
steps/plan/step-02-readiness-check.md:83 .claude/commands/bmad-check-implementation-readiness.md
```

A fresh v6.12.0 install leaves `.claude/commands/` **empty**; skills land in `.claude/skills/`
as directories (`.claude/skills/<name>/SKILL.md`). `bmad-agent-architect` **is installed**, but
the epic architecture gate probes the wrong path, concludes it is absent, and self-skips.

This is worse than 1.1 because self-skipping is correct behavior on absence, so nothing reports
it: one of the two shift-left quality gates is silently disabled on every current BMad install.
It went unnoticed because this repo's `.claude/commands/` holds symlinks to our own skills, so
`l3io-*` probes resolve.

## 2. Non-goals

- Adopting `bmad-build-auto` as the implement step (evaluated and rejected — §9).
- Declarative review layers (deferred — §9.1).
- Adding a dependency check to `health-check`'s numbered checks (deferred — §7.3).
- Any version bump. `pm-status.py`'s version line and all `module.yaml` versions stay untouched.

## 3. Decision summary

The dev loop's dependency on `bmad-create-story` and `bmad-dev-story` is **nominal, not
behavioral**. Both dispatch sites hand the subagent a complete instruction authored here — the
six-dimension technical-AC layout, the `## Files in scope` rules, spec provenance pointers, the
read-scope rule, `{agent_contract}`, and the batching policy. The skill name's only load-bearing
use is the `--agent` label on `pm-status.py dispatch` events.

**The honest limit of that claim:** it describes what we *send*, not proof the skill contributes
nothing. Where the skill exists, its own `SKILL.md` loads alongside our prompt, so removing the
invocation would remove whatever that added. That is unmeasured, so this design does not rely on
it being nothing.

Therefore: keep invoking the BMad skill wherever it is installed, and fall back to a general
subagent carrying the **same prompt unchanged** only where it is absent (§4.1). Migrate the
reviewer and readiness sites the same tolerant way. A working install keeps working; a clean
v6.12.0 install starts working.

This preserves token discipline (no added subagents, no nested fix loop), keeps `pm-status.py`
the sole writer of story frontmatter, and removes shim dependence entirely.

## 4. The mapping

| Dead name | Becomes | Mechanism |
|---|---|---|
| `bmad-create-story` | itself when installed, else a general subagent as `l3io-story-enrich` | name-tolerant (§4.1) |
| `bmad-dev-story` | itself when installed, else a general subagent as `l3io-dev-implement` | name-tolerant (§4.1) |
| `bmad-review-adversarial-general` | `bmad-review lenses=adversarial`, else itself | name-tolerant (§4.1) |
| `bmad-check-implementation-readiness` | `bmad-sprint-planning intent=readiness`, else itself | name-tolerant (§4.1) |
| `bmad-ux-review` | `bmad-ux` Reviewer Gate, else itself | name-tolerant (§4.1) |
| `bmad-agent-architect` | unchanged — it exists | probe path only (§5) |
| `bmad-architect` | `bmad-architecture` | `l3io-arch` customization-overlay target |

`bmad-architect` is a fourth stale name, found by dry-running check 17's scope: the install ships
`bmad-agent-architect` (the agent) and `bmad-architecture` (the workflow), but no
`bmad-architect`. It appears only as a `bmad-customize` overlay target in the `l3io-arch` module.
The overlay's own text — "Before finalizing any architecture or technology decision" — identifies
the workflow, so the replacement is `bmad-architecture`. `bmad-agent-architect` is a separate
concern: the arch gate detects it as a *reviewer* (§5).

### 4.1 Name tolerance — the binding rule

**No migration is a switch.** Every site resolves its skill by preferred name first, falls back
to the pre-6.12 name when that is the one installed, and only then degrades. A project running
today on an older BMad must behave **identically** after this change; the only behavior that
changes is on installs where the preferred name is what exists, or where neither does.

For the two dev-loop spawns, degrading means dispatching a general subagent with the existing
prompt body **verbatim**, under `--agent l3io-story-enrich` / `l3io-dev-implement`. When the BMad
skill is present it is still invoked, and the `--agent` label keeps its current value so
`usage --agent` continuity is preserved on working installs.

This supersedes any reading of §3 as "always use a plain subagent."

Sites to change:

- `steps/sprint/step-03-dev-loop.md` — lines 75, 98, 103, 122, 186, 190, 202, 324
- `steps/sprint/step-02-story-prep.md` — lines 99, 193
- `steps/plan/step-03-story-elaboration.md` — lines 58, 63, 91, 116
- `steps/plan/step-backlog-intake.md` — line 9 (prose)
- `steps/plan/step-02-readiness-check.md` — lines 46, 83, 85
- `steps/closure/sprint-closure.md` — lines 43, 67 (adversarial), 121, 123–124 (ux)
- `metrics-contract.md` — line 650 (attribution table)
- `status-files.md` — line 94
- `skills/l3io-arch-review/module.yaml` — lines 10, 18; `skills/l3io-arch-review/SKILL.md` — line
  87; `skills/l3io-arch-review/assets/customize-architect.md` — line 12 (`bmad-architect`) and
  **line 21** (`## Overlay for bmad-create-story`)
- The four `l3io-pm-*/module.yaml` files — `post-install-notes` lines 13, 15, 17 in each of
  `l3io-pm-execute`, `l3io-pm-plan`, `l3io-pm-help`, `l3io-pm-sync`
- Doctor's **historical** mentions, which describe legacy projects accurately and are therefore
  kept, not reworded: `skills/l3io-util-doctor/SKILL.md:3,25,84,114` and
  `skills/l3io-util-doctor/assets/migrate-state.md:122` (see §7.2's allowance)

**Calibration is unaffected.** `set-actual` keys samples by classification and level, never by
agent name, so `pm-calibration.yaml` ratios carry over intact. Only `usage --agent
bmad-dev-story` queries span the rename: historical events keep resolving, new runs use the new
identity. This is documented in `docs/l3io-pm-reference.md`, not engineered around.

`skills/_shared/tests/test-pm-status.py:5740,5743` use `"bmad-dev-story"` as an arbitrary event
label. They test event plumbing, not skill resolution, and may stay as-is.

## 5. Probe-path fix

Every presence probe checks both layouts, so current and older BMad installs both work:

```bash
ls {project-root}/.claude/skills/<name>/SKILL.md 2>/dev/null \
  || ls {project-root}/.claude/commands/<name>.md 2>/dev/null \
  || ls ~/.claude/skills/<name>/SKILL.md 2>/dev/null \
  || ls ~/.claude/commands/<name>.md 2>/dev/null
```

Applies to `steps/execute/step-04-arch-gate.md:34,35` and `steps/closure/sprint-closure.md:123`.

**Not guarded at CI — stated plainly, because it is not.** The mechanical guard in §7 covers
dependency **names**, not probe **paths**. `check:docs` check 17 will pass a step file that
reverts to a single `.claude/commands/<name>.md` probe, reintroducing exactly the silent
self-skip §1.2 describes: no CI check examines the shape above, and none should be assumed to.
It is verified only at **runtime**, against a real install, by `/l3io-util-doctor check-deps`
(§7.3) — `bmad-deps.py` resolves every declared name through all four locations and names each
absent optional one, so a self-skipped gate is not mistaken for a passed one. A CI check for
probe shape is **deferred**, not implied: it needs its own tests and its own proof that it can
fail, which is a task of its own rather than a line in a fix wave.

### 5.1 The canonical resolver

Every name-tolerant site (§4.1) uses this one shape — preferred name, then fallback, across both
layouts and both roots. Bind the first hit; an empty result means absent.

```bash
for n in <preferred-name> <fallback-name>; do
  ls {project-root}/.claude/skills/$n/SKILL.md 2>/dev/null \
    || ls {project-root}/.claude/commands/$n.md 2>/dev/null \
    || ls ~/.claude/skills/$n/SKILL.md 2>/dev/null \
    || ls ~/.claude/commands/$n.md 2>/dev/null
done | head -1
```

`steps/plan/step-02-readiness-check.md:83`'s single-directory probe is **replaced, not merely
repaired**: it resolves through §4.1's two-name resolver rather than testing one hard-coded name
in one directory.

An earlier draft of this paragraph said the check "calls `bmad-sprint-planning` unconditionally"
because that skill ships in the default install. That contradicted §4.1, which is the binding
rule, and §4.1 governs. The reason is concrete: `bmad-sprint-planning` **predates** 6.12.0, but
`intent=readiness` is the 6.12.0 shape of it, and older copies were never verified to accept that
argument. So this is one of the two overlapping pairs where the *old* name is probed first — its
presence is positive evidence of an older install. Calling the new shape unconditionally would
break exactly the working installs this design exists to protect, including this repo's own
BMad 6.11.0.

## 6. Harvested from `bmad-build-auto`

Taken as **instructions folded into the existing code-review dispatch** in
`steps/sprint/step-03-dev-loop.md` §3 — not as new reviewer passes, which would multiply turns:

- **Deletion check.** For each chunk of removed or replaced code (ignoring pure renames and
  whitespace), ask whether it carried behavior or a contract the change neither re-established
  nor intended to drop. Findings are rated `high`/`medium`/`low` confidence, since they are
  inferences. We have no equivalent today.
- **Claims check.** Falsify the story's own claims — its functional and technical ACs — against
  the code produced. Verified claims produce nothing; only falsified ones become findings.

Findings from both carry a `kind` (`deletion` / `claim`) in the review findings file the dev loop
already writes, `{sprint_root}/closure/review-{story_key}.md` — the same file the fix round is
handed by path.

**Refused, with reasons:**

- *Finding-floor arithmetic* (`N = min(floor(sqrt(kB) + 1), 10)`, "find at least N issues") —
  mandates a count regardless of whether defects exist. BMad's own `bmad-review` contradicts it:
  "Report what is real — never pad to look thorough."
- *In-file `Review Triage Log` and `deferred` frontmatter list* — `issues.yaml` is strictly
  better: machine-written under `flock`, with a key allocator that never reuses a key. Theirs is
  free-form YAML edited by an agent, the pattern `pm-status.py` exists to eliminate.
- *`<intent-contract>` block* — the useful part is the taxonomy, not the format (§6.1).
- *Per-story `baseline_revision`* and *`render_skill.py` content-addressed snapshots* — real
  value, unrelated to this migration.

### 6.1 Taxonomy: adopted as vocabulary, not as control flow

Build-auto routes root causes as `intent_gap` / `bad_spec` / `patch` / `defer`. That distinction
already exists here under different names: `spec-align.py` dispositions (`resolved-in-code`,
`adr-justified`, `spec-updated`, `spec-proposal`) and `issues.yaml` `kind` (`defect`,
`spec-change`, `spec-proposal`). Their `intent_gap` is our `spec-change`/`spec-proposal`; their
`bad_spec`/`patch` is our `defect`.

Phase 1 uses that vocabulary to **label** review findings. Changing the fix loop so an
intent-level finding escalates instead of consuming all three iterations is a control-flow
change that deserves its own measurement, and is deferred.

## 7. The mechanical guard

`_bmad/` is gitignored (`.gitignore:752`), so CI has no BMad install. Two levels, each catching
one defect from §1.

### 7.1 The inventory

`skills/l3io-util-doctor/assets/bmad-dependencies.json` — the single declaration of every
upstream skill this package references.

**JSON is forced, and correctly so.** This package has zero runtime node dependencies
(`dependencies: {}`) and `check-docs.mjs` imports only `node:fs` and `node:path`. No TOML or
YAML parser is available to it, library-first forbids hand-rolling another one, and adding a
dependency to a deliberately zero-dependency package costs more than the checker is worth.
`JSON.parse` is native to node and `json` is stdlib in Python.

```json
{
  "verified_against": "6.12.0",
  "verified_on": "2026-09-12",
  "skills": [
    { "name": "bmad-code-review", "status": "required", "module": "bmm" },
    { "name": "bmad-review", "status": "required", "module": "bmm",
      "invoked_as": "lenses=adversarial" },
    { "name": "bmad-sprint-planning", "status": "required", "module": "bmm",
      "invoked_as": "intent=readiness" },
    { "name": "bmad-ux", "status": "optional", "module": "bmm" },
    { "name": "bmad-create-story", "status": "removed", "removed_in": "6.12.0",
      "replaced_by": "l3io-story-enrich (in-package subagent)" },
    { "name": "bmad-defer", "status": "not-a-skill",
      "reason": "deferred-shortcut marker `bmad-defer:`, swept by harvest-debt" }
  ]
}
```

The example above is illustrative. The inventory must be **complete**, or check 17 fails on its
first run. The full set, from the dry run cross-checked against the 29 skills a default v6.12.0
install provides:

- `required` (referenced and present): `bmad-code-review`, `bmad-retrospective`,
  `bmad-qa-generate-e2e-tests`, `bmad-review`, `bmad-sprint-planning`
- `optional` (referenced, present, every use self-skips when absent): `bmad-agent-architect`,
  `bmad-architecture`, `bmad-ux`, `bmad-help`, `bmad-customize`, `bmad-brainstorming`,
  `bmad-forge-idea`, `bmad-create-epics-and-stories`
- `removed`: `bmad-create-story`, `bmad-dev-story`, `bmad-review-adversarial-general`,
  `bmad-ux-review`, `bmad-check-implementation-readiness`, `bmad-architect`
- `not-a-skill`: `bmad-output`, `bmad-defer`, `bmad-l3io-extensions`

`bmad-architecture` was `required` in the first draft of this list and that was wrong on this
section's own definition of the word: **nothing dispatches it.** Its only four references are
`bmad-customize` overlay *documentation* (`skills/l3io-arch-review/module.yaml:10,18`,
`SKILL.md:87`, `assets/customize-architect.md:12`) — documentation, which has nothing to
self-skip, so `optional` is the nearest honest status rather than a word-for-word match for the
definition above. It landed in `required` only because check 17 needed some declaration
for the stale `bmad-architect` token those docs used to carry, which is an argument for
declaring it, never for requiring it. Reclassified `optional` in the final fix wave.

Fields: `name` (required); `status` one of `required` | `optional` | `removed` | `not-a-skill`;
`module` required when status is `required`/`optional`, naming the module the skill actually
ships in — which is not always `bmm`: `bmad-review`, `bmad-help`, `bmad-customize`,
`bmad-brainstorming` and `bmad-forge-idea` are `core`, measured on a core-only install. **No
check validates this value** — check 17 asserts only that the field is non-empty, so a wrong
module is invisible to CI and shows up as misdirected install advice; `replaced_by` and `removed_in` required
when status is `removed`; `reason` required when status is `not-a-skill`, and allowed on any
entry as an explanatory note — JSON has no comments, so this is where a "why is this declared
at all" answer goes; `invoked_as` optional;
`fallback` optional — the pre-6.12 name this entry resolves to when the preferred name is absent,
which is what makes §4.1's tolerance declared data rather than scattered prose.

`not-a-skill` exists because a dry run of check 17's scope found three `bmad-`-prefixed tokens
that are not skills: `bmad-output` (matched inside `_bmad-output`, the `output_folder` default),
`bmad-defer` (the deferred-shortcut marker `bmad-defer:` that `harvest-debt` sweeps for), and
`bmad-l3io-extensions` (this package's own name). Declaring them here rather than hiding an
exclusion list inside the script keeps the inventory the single source of truth — a hidden list
would rot silently, which is the failure mode this guard exists to prevent.

### 7.2 Level 1 — CI, `check:docs` check 17 (`bmad-dependency-inventory`)

Two scopes, both **derived by walking, never enumerated by hand**:

1. Every `bmad-*` token in markdown under `skills/`, found with the existing `walkMarkdown`
   generator (`scripts/check-docs.mjs:176`, which already skips `superpowers` directories).
   `.py` files are out of scope — dependency declarations live in the prose that dispatches
   agents.

   The token pattern is `/(?<![\w-])bmad-[a-z0-9-]+/g`. The lookbehind is load-bearing: without
   it, `_bmad-output` yields a spurious `bmad-output`. Tokens whose inventory status is
   `not-a-skill` are then skipped.
2. Every `bmad-*` token in each `skills/*/module.yaml` `post-install-notes`.

Assertions:

- Every token found in either scope is declared in the inventory.
- No token in either scope names a skill whose status is `removed`, **except** where the
  mention is self-evidently historical: the **same line** also names that entry's `replaced_by`,
  or contains `legacy` or `historical`. A note is recorded (`notes.push`, as check 1 does) and
  the mention is allowed. This is the regression guard: a step file dispatching a dead skill
  fails CI, while prose accurately describing a legacy project passes.

  **Deliberately tighter than check 1**, which widens to a ±4-line window matching
  `/renam|deprecat|remov|previously|no longer|.../i`. Dry-run against this repo, that window
  passes `l3io-util-doctor/SKILL.md:84` only because an unrelated routing row four lines away
  says "remove migration backup files" — an accidental pass, which is how a guard starts crying
  wolf and gets switched off. Same-line evidence cannot be satisfied by a neighbour.

  Cost of the tighter rule: the five historical mentions in §4's site list need the word
  `legacy` added (e.g. `SKILL.md:84` → "(legacy `bmad-create-story` workflow)"). That is a
  one-word edit per line and it makes each claim self-documenting.
- Inventory self-consistency: required fields present for each `status`, no duplicate `name`.

Raises the check count from sixteen to **seventeen** (CLAUDE.md and the script header).

### 7.3 Level 2 — runtime, `bmad-deps.py` + a doctor mode

Skill-local, not shared: `l3io-util-doctor` is the only consumer, which is exactly what ADR-0001
prescribes. It follows the existing precedent of `audit-backlog.py` verbatim — script at
`skills/l3io-util-doctor/scripts/bmad-deps.py`, suite at
`skills/l3io-util-doctor/scripts/tests/test-bmad-deps.py`, one CI step. **No sync group, no
`_shared/` copy.**

PEP 723 header, run via `uv run`, dependency `ruamel.yaml>=0.18` (to read
`_bmad/_config/manifest.yaml`).

```
bmad-deps.py verify --project-root R [--inventory PATH] [--format text|json]
```

Behavior: read the inventory (default `{skill-root}/assets/bmad-dependencies.json`, i.e. the
skill's own installed copy); read `_bmad/_config/manifest.yaml` for installed modules; probe
each declared skill in all four locations from §5, handling both the v6.12 directory layout
(`<name>/SKILL.md`) and the older flat layout (`<name>.md`). Report each required skill as
present or missing, each optional skill as detected or absent, and each `removed` skill still
found on disk as a shim in use.

Exit codes, following `pm-status.py`'s convention: `0` all required present; `2` usage error or
refusal; `3` a required skill missing; `4` inventory or manifest unreadable. An absent optional
skill is a warning line with exit `0`.

Doctor mode: keyword `check-deps`, file `steps/check-deps.md`, read-only. Adding it raises the
mode count from nineteen to **twenty** at both claim sites — `skills/l3io-util-doctor/SKILL.md:56-57`
("nineteen procedures", "eighteen it would not execute") and `CLAUDE.md:12`.

`docs/l3io-util-reference.md:86`'s "nineteen numbered read-only checks (Checks 1–19)" is the
**health-check's** count, a different nineteen. It must not be touched: `check-deps` is a
standalone mode, deliberately not a health-check numbered check, so that count stays valid.

## 8. Documentation and configuration truth

- The **four** `l3io-pm-*/module.yaml` `post-install-notes` (`l3io-pm-execute`, `l3io-pm-plan`,
  `l3io-pm-help`, `l3io-pm-sync`, each at lines 13/15/17) — restate the dependency list in
  tolerance terms: name the preferred skill and note that an older install resolves to the
  pre-6.12 name automatically. Keep `--modules bmm` (verified against
  `docs/start/install-bmad.md:105`). Do **not** assert a minimum BMad version.
- `skills/l3io-arch-review/module.yaml:10,18` — `bmad-architect` → `bmad-architecture`.
- `docs/l3io-pm-reference.md:898,919` — the `bmad-check-implementation-readiness` rows.
- `docs/l3io-util-reference.md` — the new `check-deps` mode row.
- `CLAUDE.md` — the Dependencies section; "sixteen checks" → "seventeen"; mode count → twenty.
- The four **docs/** sites naming `bmad-architect`, which check 17 does not scan but users read:
  `docs/l3io-arch-reference.md:9,96`, `docs/architecture.md:57`, `docs/getting-started.md:136`.
- The five doctor historical mentions gain the word `legacy` so §7.2's same-line rule is
  satisfied without weakening it: `skills/l3io-util-doctor/SKILL.md:3,25,84,114` and
  `skills/l3io-util-doctor/assets/migrate-state.md:122`.
- `docs/getting-started.md` and `README.md` — state that BMad ≥6.12.0 installs skills to
  `.claude/skills/` and needs no `--shims` flag, **and** that older installs keep working
  unchanged. This is information, not a version floor.

## 9. Rejected: adopting `bmad-build-auto`

Evaluated in full and rejected. Its headline benefit is inheriting an implement step whose
behavior we already override completely, against concrete costs:

1. **Two writers on one story file.** It writes `status`, `baseline_revision`, `warnings`,
   `review_loop_iteration` and an `## Auto Run Result` block into the story doc, with no lock
   against `sync-story-doc`. This repo already runs concurrent epics in one checkout.
2. **Nested fix loops.** Its `review_loop_iteration` cycle sits inside `max_fix_iterations = 3`,
   multiplying turns in the metric the token program targets.
3. **Three extra review subagents per story** by default (blind-hunter, edge-case-hunter,
   verification-gap), suppressible only by shipping a `_bmad/custom/bmad-build-auto.toml`
   override — this package configuring another module's skill, with silent 3× review cost if the
   override goes missing.
4. **Status vocabulary mismatch** — `review` vs `in-review`, and `backlog` unrecognized.
5. Its 900–1600-token SCOPE STANDARD stamps `oversized` into frontmatter; our stories carry six
   AC dimensions plus scope and provenance. *(Predicted, not measured.)*
6. Duplicate context machinery — it compiles `epic-<N>-context.md` by subagent; `spec-align.py`
   already provides a byte-budgeted index.

### 9.1 Deferred to Phase 2

Its `[[workflow.review_layers]]` pattern — arrays of tables merged by `id`, `when` gating a
layer, empty `instruction` disabling one — is the best structural idea in the package, and cheap
because BMad core's `resolve_customization.py` already implements the merge semantics. It would
replace ad-hoc `ls` probes with declarative config. It is deferred because it converts a
four-site path fix into a reviewer-configuration refactor across the arch gate, sprint closure,
and four `customize.toml` files.

## 10. ADR-0006

Records: the dependency checker is skill-local because it has one consumer (ADR-0001), following
`audit-backlog.py`; the inventory is JSON because node has no parser and library-first forbids
hand-rolling one; and dependency truth lives in one declared inventory with a CI guard plus a
runtime guard, because prose dependency lists drifted undetected through three BMad releases.

## 11. Testing

**Check 17** — `node:test` cases in `scripts/tests/check-docs.test.mjs`:

1. a step file naming an undeclared `bmad-*` skill fails
2. a step file **dispatching** a `removed` skill, with no same-line evidence, fails
3. a `module.yaml` `post-install-notes` naming an undeclared skill fails
4. an inventory entry missing a required field for its status fails
5. a duplicate `name` in the inventory fails
6. **scope attack** — a new skill directory with a new step file naming an undeclared skill fails
7. negative case — a valid inventory with valid references passes (exit 0)
8. a `removed` skill named on a line that **also names its `replaced_by`** is allowed, and
   records a note
9. a `removed` skill named on a line containing `legacy` is allowed, and records a note
10. **the divergence from check 1** — a `removed` skill whose only explanatory word (`removed`,
    `renamed`, …) sits four lines away **still fails**. This is the accidental pass that check
    1's ±4-line window admits; without this case the tighter rule is untested and will erode
    back to the loose one.
11. `_bmad-output` yields **no** token — proves the `(?<![\w-])` lookbehind
12. `bmad-defer` and `bmad-l3io-extensions` are skipped via their `not-a-skill` status
13. an entry with `status: not-a-skill` and no `reason` fails
14. an entry carrying `fallback` validates; a `fallback` naming an undeclared skill fails

**`bmad-deps.py`** — `unittest` driven through the real CLI via `subprocess`, real temp
directories, and the private-`TMPDIR` leak-guard block used by the other Python suites:

1. all required present → exit 0
2. a required skill missing → exit 3
3. an optional skill missing → exit 0 with a warning line
4. v6.12 directory layout (`<name>/SKILL.md`) detected
5. legacy flat layout (`<name>.md`) detected
6. `manifest.yaml` absent → exit 4
7. malformed inventory → exit 2
8. `--format json` emits the documented shape

The tolerance guarantee (§4.1) is the point of this migration, so it gets its own cases. Without
these, "a working install keeps working" is an assertion, not a tested property:

9. **preferred absent, `fallback` present** → exit 0, and the output names the fallback as the
   resolved skill
10. **both present** → exit 0, and the output resolves to the *preferred* name
11. **both absent, status `required`** → exit 3
12. **both absent, status `optional`** → exit 0 with a warning
13. a fixture tree holding only pre-6.12 names resolves **every** site via `fallback` — this is
    the executable form of §12's acceptance criterion 2
14. a `removed` skill found on disk is reported as a shim in use

Each guard needs a non-hollow proof: revert the guard, confirm the test fails.

**CI** — one step in `.github/workflows/checks.yml` mirroring line 42:

```yaml
- run: uv run -q --with 'ruamel.yaml>=0.18' python3 skills/l3io-util-doctor/scripts/tests/test-bmad-deps.py
```

## 12. Verification

Step files are shared sources, so after editing: `npm run sync:scripts`, then
`node scripts/write-payload-manifest.mjs`. Then all five gates must pass: `check:scripts`,
`check:docs`, `check:manifest`, `check:version`, `test:scripts`, plus the Python suites.

Acceptance, both halves required:

1. A clean `npx bmad-method install --yes --modules bmm --tools claude-code` followed by
   `/l3io-util-doctor check-deps` reports every required dependency present and no shim in use.
2. **An install carrying the pre-6.12 skill names still resolves every site to those names**, so
   a project working today is behaviorally unchanged. Verified by running `check-deps` against a
   fixture tree holding the old names and confirming each resolves via `fallback`.
