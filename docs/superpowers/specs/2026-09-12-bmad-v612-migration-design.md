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

Therefore: replace the two spawns with plain subagents under stable in-package identities,
carrying the **same prompts unchanged**, and migrate only the two sites that consume real BMad
behavior.

This preserves token discipline (no added subagents, no nested fix loop), keeps `pm-status.py`
the sole writer of story frontmatter, and removes shim dependence entirely.

## 4. The mapping

| Dead name | Becomes | Mechanism |
|---|---|---|
| `bmad-create-story` | plain subagent, `--agent l3io-story-enrich` | prompts unchanged |
| `bmad-dev-story` | plain subagent, `--agent l3io-dev-implement` | prompts unchanged |
| `bmad-review-adversarial-general` | `bmad-review` with `lenses=adversarial` | real migration |
| `bmad-check-implementation-readiness` | `bmad-sprint-planning` with `intent=readiness` | real migration |
| `bmad-ux-review` | `bmad-ux` (Reviewer Gate), presence-gated | real migration |
| `bmad-agent-architect` | unchanged — it exists | probe path only (§5) |

**Mechanism for the two replaced spawns:** dispatch a general subagent with no skill invocation,
keeping the existing prompt body verbatim. The only edits are the skill name in the "Spawn ..."
directive and the `--agent` label on the `pm-status.py dispatch` bracket. No `bmad-*` name
remains in either dispatch.

Sites to change:

- `steps/sprint/step-03-dev-loop.md` — lines 75, 98, 103, 122, 186, 190, 202, 324
- `steps/sprint/step-02-story-prep.md` — lines 99, 193
- `steps/plan/step-03-story-elaboration.md` — lines 58, 63, 91, 116
- `steps/plan/step-backlog-intake.md` — line 9 (prose)
- `steps/plan/step-02-readiness-check.md` — lines 46, 83, 85
- `steps/closure/sprint-closure.md` — lines 43, 67 (adversarial), 121, 123–124 (ux)
- `metrics-contract.md` — line 650 (attribution table)
- `status-files.md` — line 94

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

`steps/plan/step-02-readiness-check.md:83`'s probe is **removed, not fixed**: the skill it tests
for no longer exists, and its replacement `bmad-sprint-planning` ships in the default install, so
the readiness check calls it unconditionally (§4).

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
      "replaced_by": "l3io-story-enrich (in-package subagent)" }
  ]
}
```

Fields: `name` (required); `status` one of `required` | `optional` | `removed`; `module` required
when status is `required`/`optional`; `replaced_by` and `removed_in` required when status is
`removed`; `invoked_as` optional.

### 7.2 Level 1 — CI, `check:docs` check 17 (`bmad-dependency-inventory`)

Two scopes, both **derived by walking, never enumerated by hand**:

1. Every `bmad-*` token in markdown under `skills/`, found with the existing `walkMarkdown`
   generator (`scripts/check-docs.mjs:176`, which already skips `superpowers` directories).
   `.py` files are out of scope — dependency declarations live in the prose that dispatches
   agents.
2. Every `bmad-*` token in each `skills/*/module.yaml` `post-install-notes`.

Assertions:

- Every token found in either scope is declared in the inventory.
- No token in either scope names a skill whose status is `removed`. This is the regression guard:
  a step file naming a dead skill fails CI.
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

- Six `module.yaml` `post-install-notes` — replace the required-skills list; keep `--modules bmm`
  (verified correct against `docs/start/install-bmad.md:105`); state that `bmad-ux` is optional.
- `docs/l3io-pm-reference.md:898,919` — the `bmad-check-implementation-readiness` rows.
- `docs/l3io-util-reference.md` — the new `check-deps` mode row.
- `CLAUDE.md` — the Dependencies section; "sixteen checks" → "seventeen"; mode count → twenty.
- `docs/getting-started.md` and `README.md` — note that BMad ≥6.12.0 installs to
  `.claude/skills/`, and that no `--shims` flag is needed.

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
2. a step file naming a `removed` skill fails
3. a `module.yaml` `post-install-notes` naming an undeclared skill fails
4. an inventory entry missing a required field for its status fails
5. a duplicate `name` in the inventory fails
6. **scope attack** — a new skill directory with a new step file naming an undeclared skill fails
7. negative case — a valid inventory with valid references passes (exit 0)

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

Each guard needs a non-hollow proof: revert the guard, confirm the test fails.

**CI** — one step in `.github/workflows/checks.yml` mirroring line 42:

```yaml
- run: uv run -q --with 'ruamel.yaml>=0.18' python3 skills/l3io-util-doctor/scripts/tests/test-bmad-deps.py
```

## 12. Verification

Step files are shared sources, so after editing: `npm run sync:scripts`, then
`node scripts/write-payload-manifest.mjs`. Then all five gates must pass: `check:scripts`,
`check:docs`, `check:manifest`, `check:version`, `test:scripts`, plus the Python suites.

Acceptance: a clean `npx bmad-method install --yes --modules bmm --tools claude-code` followed by
`/l3io-util-doctor check-deps` reports every required dependency present and no shim in use.
