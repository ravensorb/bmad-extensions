# BMad v6.12.0 Dependency Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every BMad skill this package dispatches resolve on both current (≥6.12.0) and older BMad installs, and add a two-level guard so a renamed or removed upstream skill can never again go unnoticed.

**Architecture:** Every dispatch site resolves its skill by name with a fallback instead of naming one hard-coded skill. One declared JSON inventory is the single source of truth for which names exist, which are gone, and what each falls back to; `check:docs` check 17 asserts the step files agree with it at CI time, and a new `bmad-deps.py` plus a `check-deps` doctor mode asserts a real install agrees with it at runtime.

**Tech Stack:** Markdown step files, Node (`scripts/check-docs.mjs`, zero runtime deps, `node:test`), Python 3.11 via `uv run` with PEP 723 headers (`ruamel.yaml`), JSON for the inventory.

**Spec:** `docs/superpowers/specs/2026-09-12-bmad-v612-migration-design.md` (commit `82b984c`)

## Global Constraints

- **Do not break a working install.** This repo's own BMad is **6.11.0** (`_bmad/_config/manifest.yaml`), with `l3io-pm`/`l3io-sec`/`l3io-util` installed from `channel: next`. A hard switch would break this machine. Every migration is name-tolerant.
- **Resolution order: resolve the name a working install would have, first.** For disjoint pairs (`bmad-review` vs `bmad-review-adversarial-general`) order is irrelevant — only one can exist. For *overlapping* pairs the old name wins when present, because its presence is positive evidence of an older install: `bmad-check-implementation-readiness` before `bmad-sprint-planning intent=readiness`, and `bmad-ux-review` before `bmad-ux`. This implements spec §4.1's stated guarantee ("a project working today is behaviorally unchanged").
- Canonical sources live in `skills/_shared/` **only**. Never edit a per-skill copy. After any payload edit: `npm run sync:scripts`, then `node scripts/write-payload-manifest.mjs`.
- `bmad-deps.py` is skill-local (single consumer, ADR-0001, exactly like `audit-backlog.py`). It gets **no** sync group.
- Five gates must pass: `check:scripts`, `check:docs`, `check:manifest`, `check:version`, `test:scripts`, plus every Python suite.
- Tests drive the real CLI via `subprocess` with real temp dirs and the private-`TMPDIR` leak-guard block. Never hand-written fixtures, never a custom harness.
- Every guard needs a **non-hollow proof**: revert the guard, confirm the test fails, restore.
- **Naming a removed skill: the same-physical-line rule.** Check 17 (Task 10) inspects one line at a time. Wherever prose names a `removed` skill, that **same physical line** must also carry the word `legacy` (or `historical`), or the replacement's exact token. Reflow the sentence if a line break would separate them — `legacy` at the end of one line and the skill name at the start of the next does **not** pass. Three arms satisfy the check: (a) same-line `legacy`/`historical`; (b) same-line `replaced_by` as a whole token; (c) the line is a filesystem existence probe (contains `ls ` and `.claude/`), which the tolerance design requires and which cannot dispatch anything.
- **No version bumps.** `pm-status.py`'s version marker, `PM_STATUS_VERSION`, and every `module.yaml` `module_version` stay untouched.
- Conventional Commits, `git commit -s`, explicit-path staging only (never `-A`), never `git stash`. Trailers on every commit:
  ```
  Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01E4PU5edGnYd8Dc12LbhDYY
  ```
- **Never push.** Three commits are already unpushed (`82b984c`, `9583b4b`, `3c5df13`).
- Concurrent agents may share this checkout: stage only the paths your task names.

## Ordering constraint (do not reorder)

Check 17 (Task 10) fails any file that *dispatches* a `removed` skill. It must therefore land **after** Tasks 3–9. Inventory (Task 2) must precede Tasks 10 and 11. Task 11 precedes Task 12 (the mode invokes the script).

**Check 17 scans `module.yaml` `post-install-notes` too, not only step files.** The four `l3io-pm-*/module.yaml` files currently name four removed skills with no same-line evidence, so their rewrite is part of **Task 9**, before check 17 exists. Task 13 handles only the remaining prose (`CLAUDE.md`, `README.md`, `docs/`), which check 17 does not scan.

## File Structure

**Created:**
- `docs/adr/0006-bmad-dependency-inventory.md` — records the three decisions in spec §10.
- `skills/l3io-util-doctor/assets/bmad-dependencies.json` — the inventory; the one place every `bmad-*` name is declared.
- `skills/l3io-util-doctor/scripts/bmad-deps.py` — runtime verifier, `verify` subcommand.
- `skills/l3io-util-doctor/scripts/tests/test-bmad-deps.py` — its suite.
- `skills/l3io-util-doctor/steps/check-deps.md` — the doctor mode.

**Modified (canonical sources):**
- `skills/_shared/steps/sprint/step-03-dev-loop.md` — implementer resolution + harvested review instructions.
- `skills/_shared/steps/sprint/step-02-story-prep.md`, `skills/_shared/steps/plan/step-03-story-elaboration.md`, `skills/_shared/steps/plan/step-backlog-intake.md` — enricher resolution.
- `skills/_shared/steps/closure/sprint-closure.md` — adversarial reviewer + UX resolution.
- `skills/_shared/steps/plan/step-02-readiness-check.md` — readiness resolution.
- `skills/_shared/steps/execute/step-04-arch-gate.md` — probe paths.
- `skills/_shared/metrics-contract.md`, `skills/_shared/status-files.md` — agent-name references.

**Modified (not generated — edit directly):**
- `scripts/check-docs.mjs`, `scripts/tests/check-docs.test.mjs`, `.github/workflows/checks.yml`
- `skills/l3io-util-doctor/SKILL.md`, `skills/l3io-util-doctor/assets/migrate-state.md`
- `skills/l3io-arch-review/module.yaml`, `SKILL.md`, `assets/customize-architect.md`
- Four `l3io-pm-*/module.yaml`; `CLAUDE.md`; `README.md`; `docs/*.md`

---

### Task 1: ADR-0006

**Files:**
- Create: `docs/adr/0006-bmad-dependency-inventory.md`

**Interfaces:**
- Produces: the decision record Tasks 2, 10 and 11 cite. No code interface.

- [ ] **Step 1: Write the ADR**

Match the style of `docs/adr/0005-one-adr-home.md` (read it first for heading shape). Content must record all three decisions:

```markdown
# ADR-0006: One declared BMad dependency inventory, guarded twice

## Status
Accepted — 2026-09-12

## Context
Three BMad releases changed skills this package dispatches, and nothing detected it.
`bmad-create-story` and `bmad-dev-story` were deprecated to shims (#2637, #2641),
`bmad-review-adversarial-general` merged into `bmad-review` (#2603, #2608), and
`bmad-check-implementation-readiness` was removed outright (#2659). A clean v6.12.0 install
therefore could not run the dev loop. Separately, every presence probe read
`.claude/commands/` while 6.12.0 installs to `.claude/skills/`, so an installed reviewer
looked absent and its gate silently self-skipped. Both were found only by installing BMad
by hand and looking.

## Decision
1. Every upstream `bmad-*` name this package references is declared in one inventory,
   `skills/l3io-util-doctor/assets/bmad-dependencies.json`, with its status and its fallback.
2. The inventory is **JSON**. This package has zero runtime node dependencies and
   `check-docs.mjs` imports only `node:fs`/`node:path`; no TOML or YAML parser is available to
   it, and library-first forbids hand-rolling one. `JSON.parse` is native to node and `json`
   is stdlib in Python, so both guards read it with no parsing code.
3. The runtime verifier is **skill-local** at `skills/l3io-util-doctor/scripts/bmad-deps.py`,
   because `l3io-util-doctor` is its only consumer. ADR-0001 places single-consumer code in
   its skill's own `scripts/`; this follows `audit-backlog.py` exactly, including a suite at
   `scripts/tests/` and one CI step. It gets no sync group and no `_shared/` copy.

## Consequences
Dependency truth is one file instead of prose in six `module.yaml` files and a dozen step
files. `check:docs` check 17 asserts the step files agree with it where no BMad install
exists; `bmad-deps.py` asserts a real install agrees with it. A future rename fails CI or
surfaces in `/l3io-util-doctor check-deps` instead of silently disabling a gate.

The inventory is hand-maintained against upstream, so it can lag a BMad release. It records
`verified_against` for exactly that reason: the claim is "checked at this version", not
"true forever".
```

- [ ] **Step 2: Commit**

```bash
git add docs/adr/0006-bmad-dependency-inventory.md
git commit -s -m "docs(adr): record ADR-0006, one guarded BMad dependency inventory"
```

---

### Task 2: The dependency inventory

**Files:**
- Create: `skills/l3io-util-doctor/assets/bmad-dependencies.json`

**Interfaces:**
- Produces: the file both guards read. Consumed by Task 10 (`DEP_INVENTORY`) and Task 11 (`--inventory` default). Schema exactly as below — Tasks 10 and 11 validate these field names.

- [ ] **Step 1: Write the inventory**

The set is complete as given; it was derived by dry-running check 17's scope against this repo and cross-checking every token against the 29 skills a default v6.12.0 install provides. An incomplete inventory fails check 17 on its first run.

```json
{
  "verified_against": "6.12.0",
  "verified_on": "2026-09-12",
  "skills": [
    { "name": "bmad-code-review", "status": "required", "module": "bmm" },
    { "name": "bmad-retrospective", "status": "required", "module": "bmm" },
    { "name": "bmad-qa-generate-e2e-tests", "status": "required", "module": "bmm" },
    { "name": "bmad-review", "status": "required", "module": "core",
      "invoked_as": "lenses=adversarial",
      "fallback": "bmad-review-adversarial-general" },
    { "name": "bmad-sprint-planning", "status": "required", "module": "bmm",
      "invoked_as": "intent=readiness",
      "fallback": "bmad-check-implementation-readiness" },
    { "name": "bmad-architecture", "status": "optional", "module": "bmm",
      "fallback": "bmad-architect" },

    { "name": "bmad-agent-architect", "status": "optional", "module": "bmm" },
    { "name": "bmad-ux", "status": "optional", "module": "bmm",
      "fallback": "bmad-ux-review" },
    { "name": "bmad-help", "status": "optional", "module": "core" },
    { "name": "bmad-customize", "status": "optional", "module": "core" },
    { "name": "bmad-brainstorming", "status": "optional", "module": "core" },
    { "name": "bmad-forge-idea", "status": "optional", "module": "core" },
    { "name": "bmad-create-epics-and-stories", "status": "optional", "module": "bmm" },

    { "name": "bmad-create-story", "status": "removed", "removed_in": "6.12.0",
      "replaced_by": "l3io-story-enrich" },
    { "name": "bmad-dev-story", "status": "removed", "removed_in": "6.12.0",
      "replaced_by": "l3io-dev-implement" },
    { "name": "bmad-review-adversarial-general", "status": "removed", "removed_in": "6.12.0",
      "replaced_by": "bmad-review" },
    { "name": "bmad-check-implementation-readiness", "status": "removed", "removed_in": "6.12.0",
      "replaced_by": "bmad-sprint-planning" },
    { "name": "bmad-ux-review", "status": "removed", "removed_in": "6.12.0",
      "replaced_by": "bmad-ux" },
    { "name": "bmad-architect", "status": "removed", "removed_in": "6.12.0",
      "replaced_by": "bmad-architecture" },

    { "name": "bmad-output", "status": "not-a-skill",
      "reason": "matches inside _bmad-output, the core.output_folder default" },
    { "name": "bmad-defer", "status": "not-a-skill",
      "reason": "the bmad-defer: deferred-shortcut marker that harvest-debt sweeps for" },
    { "name": "bmad-l3io-extensions", "status": "not-a-skill",
      "reason": "this package's own name" },
    { "name": "bmad-deps", "status": "not-a-skill",
      "reason": "this package's own runtime verifier script, scripts/bmad-deps.py" }
  ]
}
```

Note `bmad-create-story`/`bmad-dev-story` carry a `replaced_by` that is an in-package agent identity, not a BMad skill. Task 10's fallback validation only checks `fallback` targets, never `replaced_by`, so this is intentional and valid.

**Amended after the final review.** Three corrections landed against this block, and the shipped `skills/l3io-util-doctor/assets/bmad-dependencies.json` is authoritative over it: (a) `bmad-architecture` is `optional`, not `required` — nothing dispatches it, see Task 14 Step 5; (b) `bmad-deps` was added as a fourth `not-a-skill` entry; (c) `bmad-review`, `bmad-help`, `bmad-customize`, `bmad-brainstorming` and `bmad-forge-idea` ship in `core`, not `bmm` — measured against a core-only install, where all five resolve and every genuinely-`bmm` entry reports MISSING.

- [ ] **Step 2: Verify it parses**

Run: `node -e "const i=require('./skills/l3io-util-doctor/assets/bmad-dependencies.json');console.log(i.skills.length+' entries')"`
Expected: `22 entries`

- [ ] **Step 3: Regenerate manifests and commit**

`assets/` is part of doctor's payload, so the manifest moves.

```bash
node scripts/write-payload-manifest.mjs
git add skills/l3io-util-doctor/assets/bmad-dependencies.json skills/l3io-util-doctor/payload-manifest.json
git commit -s -m "feat(l3io-util): declare every BMad dependency in one inventory"
```

---

### Task 3: Dev-loop implementer resolution

**Files:**
- Modify: `skills/_shared/steps/sprint/step-03-dev-loop.md` (lines 73–76, 95–135, 185–210, 324)
- Modify: `skills/_shared/status-files.md:94`

**Interfaces:**
- Produces: `{dev_agent}`, bound to `bmad-dev-story` or `l3io-dev-implement`. Used as the `--agent` value on every dispatch bracket in this file, and referenced by Task 13's docs.

- [ ] **Step 1: Insert the resolution block before §2's dispatch**

Immediately before the existing `dispatch --event open` fence at line 73, add:

```markdown
**Resolve the implementer.** The legacy `bmad-dev-story` skill is gone from BMad ≥6.12.0; where it is installed
it is still what runs, and where it is absent the prompt below is the whole instruction anyway.

```bash
ls {project-root}/.claude/skills/bmad-dev-story/SKILL.md 2>/dev/null \
  || ls {project-root}/.claude/commands/bmad-dev-story.md 2>/dev/null \
  || ls ~/.claude/skills/bmad-dev-story/SKILL.md 2>/dev/null \
  || ls ~/.claude/commands/bmad-dev-story.md 2>/dev/null
```

If a path printed, bind `{dev_agent}` = the legacy `bmad-dev-story` and spawn that skill. If
nothing printed, bind `{dev_agent}` = `l3io-dev-implement` and spawn a **general subagent** — no skill
invocation — with the identical inputs. `{dev_agent}` is the `--agent` label on every dispatch
bracket in this step, so a working install keeps its existing `usage --agent` history.
```

- [ ] **Step 2: Replace every hard-coded agent name in this file**

Four dispatch brackets (73–76, 120–123, 188–191, 200–203): `--agent bmad-dev-story` → `--agent {dev_agent}`.

Line 103 `Spawn \`bmad-dev-story\` subagent with:` → `Spawn `{dev_agent}` with (a general subagent when `{dev_agent}` is `l3io-dev-implement`):`

Line 194 `Spawn \`bmad-dev-story\` subagent again with the findings **path**` → `Spawn `{dev_agent}` again with the findings **path**`

Line 98 `usage --agent bmad-dev-story --story {story_key}` → `usage --agent {dev_agent} --story {story_key}`

Line 186 `` `bmad-dev-story` call `` → `` `{dev_agent}` call ``

Line 324 `(each bmad-dev-story re-dispatch in §3)` → `(each `{dev_agent}` re-dispatch in §3)`

- [ ] **Step 3: Update the state-layout reference**

`skills/_shared/status-files.md:94`, currently:

```
| Written by | `pm-status.py` only, atomically | Humans and `bmad-dev-story` / review agents |
```

becomes:

```
| Written by | `pm-status.py` only, atomically | Humans and the story implementer (legacy `bmad-dev-story`) / review agents |
```

The word `legacy` satisfies check 17's same-line rule (Task 10).

- [ ] **Step 4: Sync, regenerate, verify no hard-coded name survives**

```bash
npm run sync:scripts && node scripts/write-payload-manifest.mjs
grep -n "agent bmad-dev-story" skills/_shared/steps/sprint/step-03-dev-loop.md
```
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add skills/_shared/steps/sprint/step-03-dev-loop.md skills/_shared/status-files.md \
        skills/l3io-pm-execute skills/l3io-pm-plan skills/l3io-pm-sync skills/l3io-util-doctor
git commit -s -m "fix(l3io-pm): resolve the dev-loop implementer instead of hard-coding it"
```

---

### Task 4: Story-enricher resolution

**Files:**
- Modify: `skills/_shared/steps/sprint/step-02-story-prep.md:99,193`
- Modify: `skills/_shared/steps/plan/step-03-story-elaboration.md:58,63,91,116`
- Modify: `skills/_shared/steps/plan/step-backlog-intake.md:9`
- Modify: `skills/_shared/metrics-contract.md:650`

**Interfaces:**
- Consumes: the resolution idiom from Task 3.
- Produces: `{enrich_agent}`, bound to `bmad-create-story` or `l3io-story-enrich`.

- [ ] **Step 1: Add resolution to story-prep §2, before line 99's bracket**

```markdown
**Resolve the enricher.** Same shape as the dev loop's implementer.

```bash
ls {project-root}/.claude/skills/bmad-create-story/SKILL.md 2>/dev/null \
  || ls {project-root}/.claude/commands/bmad-create-story.md 2>/dev/null \
  || ls ~/.claude/skills/bmad-create-story/SKILL.md 2>/dev/null \
  || ls ~/.claude/commands/bmad-create-story.md 2>/dev/null
```

A path printed → `{enrich_agent}` = the legacy `bmad-create-story`. Nothing printed →
`{enrich_agent}` = `l3io-story-enrich`, dispatched as a general subagent. The instruction below is unchanged either
way, including the batching rule: **one spawn for the whole sprint, not one per story.**
```

- [ ] **Step 2: Replace the names**

`step-02-story-prep.md` lines 99 and 193: `--agent bmad-create-story` → `--agent {enrich_agent}`.

`step-03-story-elaboration.md`: line 58 `--agent bmad-create-story` → `--agent {enrich_agent}`; line 63 `Spawn \`bmad-create-story\` with:` → `Spawn `{enrich_agent}` with:`. Add the same resolution block before line 58.

Line 91, currently `Record result: \`elaborated\` or \`failed\` (if bmad-create-story is not installed or errors).` → `Record result: `elaborated` or `failed` (if `{enrich_agent}` errors).` The old parenthetical is now wrong: absence no longer causes failure, it selects the fallback.

Line 116's example table row `| E002-S01-001 | ❌ Failed | bmad-create-story not installed |` → `| E002-S01-001 | ❌ Failed | enrichment agent returned an error |`

`step-backlog-intake.md:9`, currently `functional ACs only), elaboration (\`bmad-create-story\` adds the technical ACs), and` → `functional ACs only), elaboration (the enricher adds the technical ACs), and`

`metrics-contract.md:650` — replace `\`bmad-create-story\`` with `the enricher (legacy `bmad-create-story`)` in the attribution row.

- [ ] **Step 3: Sync, regenerate, verify**

```bash
npm run sync:scripts && node scripts/write-payload-manifest.mjs
grep -rn "agent bmad-create-story" skills/_shared/
```
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add skills/_shared/steps/sprint/step-02-story-prep.md \
        skills/_shared/steps/plan/step-03-story-elaboration.md \
        skills/_shared/steps/plan/step-backlog-intake.md \
        skills/_shared/metrics-contract.md \
        skills/l3io-pm-execute skills/l3io-pm-plan skills/l3io-pm-sync skills/l3io-util-doctor
git commit -s -m "fix(l3io-pm): resolve the story enricher instead of hard-coding it"
```

---

### Task 5: Sprint-closure reviewer and UX resolution

**Files:**
- Modify: `skills/_shared/steps/closure/sprint-closure.md:43,67,121,123-124`

**Interfaces:**
- Produces: `{adversarial_reviewer}` and `{ux_reviewer}`.

- [ ] **Step 1: Resolve the adversarial reviewer**

The pair is **disjoint** — `bmad-review` exists only on ≥6.12.0, `bmad-review-adversarial-general` only below it — so probe order does not matter. Replace line 43's parenthetical and add a resolution block before line 67.

Line 43, currently:
```
scope. They are the same reviewer (`bmad-review-adversarial-general`) over the same changed
```
becomes:
```
scope. They are the same reviewer (`{adversarial_reviewer}`) over the same changed
```

Before line 67 insert:

```markdown
**Resolve the reviewer.** `bmad-review-adversarial-general` merged into `bmad-review` at 6.12.0,
where its behavior is the `adversarial` lens.

```bash
ls {project-root}/.claude/skills/bmad-review/SKILL.md 2>/dev/null \
  || ls {project-root}/.claude/commands/bmad-review.md 2>/dev/null \
  || ls ~/.claude/skills/bmad-review/SKILL.md 2>/dev/null \
  || ls ~/.claude/commands/bmad-review.md 2>/dev/null
```

A path printed → `{adversarial_reviewer}` = `bmad-review`, invoked as
`skill:bmad-review lenses=adversarial`, with the clean-release checklist passed as
`also_consider` (a documented `bmad-review` input). Nothing printed → probe
the legacy `bmad-review-adversarial-general` the same four ways and invoke it with both scopes exactly as
before. Neither present → skip the phase and say so in the phase output, so a skipped review is
never mistaken for a passed one.
```

Line 67 `Invoke \`bmad-review-adversarial-general\` with **the sprint's diff** and the scopes that` → `Invoke `{adversarial_reviewer}` with **the sprint's diff** and the scopes that`

- [ ] **Step 2: Resolve the UX reviewer — old name first**

`bmad-ux-review` and `bmad-ux` can **both** be absent or the old one present on a working install, and `bmad-ux` is an *authoring* skill whose review capability is an opt-in Reviewer Gate. So the purpose-built skill wins when present. Replace lines 121–124:

```markdown
If a UX reviewer is installed and the sprint has UI-facing stories:
```bash
for n in bmad-ux-review bmad-ux; do
  ls {project-root}/.claude/skills/$n/SKILL.md 2>/dev/null \
    || ls {project-root}/.claude/commands/$n.md 2>/dev/null \
    || ls ~/.claude/skills/$n/SKILL.md 2>/dev/null \
    || ls ~/.claude/commands/$n.md 2>/dev/null
done | head -1
```
Bind `{ux_reviewer}` to whichever resolved — the legacy `bmad-ux-review` preferred because it is
built for review, `bmad-ux` used via its **Reviewer Gate** (opt-in, lens-selectable) when it is all that
exists. Empty result → skip the phase.
```

- [ ] **Step 3: Sync, regenerate, commit**

```bash
npm run sync:scripts && node scripts/write-payload-manifest.mjs
git add skills/_shared/steps/closure/sprint-closure.md \
        skills/l3io-pm-execute skills/l3io-pm-plan skills/l3io-pm-sync skills/l3io-util-doctor
git commit -s -m "fix(l3io-pm): resolve closure reviewers across BMad versions"
```

---

### Task 6: Readiness-check resolution

**Files:**
- Modify: `skills/_shared/steps/plan/step-02-readiness-check.md:46,83,85`

**Interfaces:**
- Produces: `{readiness_checker}`.

- [ ] **Step 1: Replace §3's probe — old name first, deliberately**

`bmad-sprint-planning` exists on older BMad too, but `intent=readiness` is the 6.12.0 shape (#2659) and older copies were never verified to accept it. The old skill's presence is positive evidence of an older install, so it is probed **first**. Replace lines 83–85:

```markdown
Resolve the readiness checker. The legacy `bmad-check-implementation-readiness` skill was folded into `bmad-sprint-planning` at 6.12.0.
The old name is probed first: where it exists, this is an older install and `intent=readiness`
may not be understood.

```bash
for n in bmad-check-implementation-readiness bmad-sprint-planning; do
  ls {project-root}/.claude/skills/$n/SKILL.md 2>/dev/null \
    || ls {project-root}/.claude/commands/$n.md 2>/dev/null \
    || ls ~/.claude/skills/$n/SKILL.md 2>/dev/null \
    || ls ~/.claude/commands/$n.md 2>/dev/null
done | head -1
```

Bind `{readiness_checker}` to whichever name resolved; an empty result leaves it unbound.

- `{readiness_checker}` = the legacy `bmad-check-implementation-readiness` → invoke it per story with the
  story file path, as before.
- `{readiness_checker}` = `bmad-sprint-planning` → invoke it once with `intent=readiness`; it runs its own
  readiness gate and returns `gate` as `PASS`, `CONCERNS`, or `FAIL`. Map `CONCERNS` → amber and
  `FAIL` → red. It is headless-aware ("When invoked headless, do not ask").
- Neither → skip this section; `{readiness}` is decided by §1–§2 alone.

Fold "not ready" findings into the gate:
- Fewer than half the stories flagged as not ready → amber
- Half or more flagged → red
```

- [ ] **Step 2: Fix the historical mention at line 46**

Currently `(e.g. via bmad-create-story without going through l3io-pm-plan).` → `(e.g. via the legacy `bmad-create-story` workflow, without going through l3io-pm-plan).`

- [ ] **Step 3: Sync, regenerate, commit**

```bash
npm run sync:scripts && node scripts/write-payload-manifest.mjs
git add skills/_shared/steps/plan/step-02-readiness-check.md \
        skills/l3io-pm-execute skills/l3io-pm-plan skills/l3io-pm-sync skills/l3io-util-doctor
git commit -s -m "fix(l3io-pm): resolve the readiness checker across BMad versions"
```

---

### Task 7: Probe-path fix in the architecture gate

**Files:**
- Modify: `skills/_shared/steps/execute/step-04-arch-gate.md:34,35`

**Interfaces:**
- Consumes: nothing. Produces: a correct `{active_reviewers}` binding.

This is the silent-failure fix: `bmad-agent-architect` **is** installed on 6.12.0, but the gate probes `.claude/commands/` and self-skips.

- [ ] **Step 1: Replace both detection commands**

Line 34's cell becomes:

```
`ls {project-root}/.claude/skills/bmad-agent-architect/SKILL.md 2>/dev/null \|\| ls {project-root}/.claude/commands/bmad-agent-architect.md 2>/dev/null \|\| ls ~/.claude/skills/bmad-agent-architect/SKILL.md 2>/dev/null \|\| ls ~/.claude/commands/bmad-agent-architect.md 2>/dev/null`
```

Line 35's cell, same four-way shape for `superpowers:requesting-code-review` (note: `.claude/skills/superpowers:requesting-code-review/SKILL.md` and the `commands/*.md` form).

- [ ] **Step 2: Verify the fix against the real install**

This repo has BMad 6.11.0, so `.claude/commands/` is the live layout here; the scratch 6.12.0 install at `/tmp/.../inst-default` has the other. Confirm both resolve:

```bash
ls <scratch>/inst-default/.claude/skills/bmad-agent-architect/SKILL.md
```
Expected: the path prints (proving the new layout is what 6.12.0 produces).

- [ ] **Step 3: Sync, regenerate, commit**

```bash
npm run sync:scripts && node scripts/write-payload-manifest.mjs
git add skills/_shared/steps/execute/step-04-arch-gate.md \
        skills/l3io-pm-execute skills/l3io-pm-plan skills/l3io-pm-sync skills/l3io-util-doctor
git commit -s -m "fix(l3io-pm): probe both skill layouts so the arch gate stops self-skipping"
```

---

### Task 8: Harvested review instructions

**Files:**
- Modify: `skills/_shared/steps/sprint/step-03-dev-loop.md` (§3, the code-review dispatch)

**Interfaces:**
- Consumes: Task 3's edits to the same file. Produces: findings carrying `kind` in `{sprint_root}/closure/review-{story_key}.md`.

Folded into the existing dispatch as instructions — **not** new reviewer passes, which would multiply turns.

- [ ] **Step 1: Add both checks to the code-review prompt**

Append to the reviewer's instruction block in §3:

```markdown
Two additional passes, both reported into the same findings file:

- **Deletion check** — run only if the diff removed or replaced meaningful code (ignore pure
  renames and whitespace). For each removed chunk, ask: did it carry behavior or a contract that
  this change neither re-established nor intended to drop? These are inferences, so rate each
  `high` / `medium` / `low` confidence. Tag them `kind: deletion`. Add nothing if nothing
  qualifies.
- **Claims check** — read the story's functional and technical ACs as the change's own claims,
  and report only where the code contradicts one. Quote or tightly paraphrase the claim as the
  trigger condition, and name where the code contradicts it as the location. Tag them
  `kind: claim`. Verified claims produce nothing.

Report what is real — never pad to reach a count.
```

- [ ] **Step 2: Sync, regenerate, commit**

```bash
npm run sync:scripts && node scripts/write-payload-manifest.mjs
git add skills/_shared/steps/sprint/step-03-dev-loop.md \
        skills/l3io-pm-execute skills/l3io-pm-plan skills/l3io-pm-sync skills/l3io-util-doctor
git commit -s -m "feat(l3io-pm): add deletion and claims checks to story code review"
```

---

### Task 9: Stale names in non-generated files

**Files:**
- Modify: `skills/l3io-arch-review/module.yaml:10,18`, `skills/l3io-arch-review/SKILL.md:87`, `skills/l3io-arch-review/assets/customize-architect.md:12,21`
- Modify: `skills/l3io-util-doctor/SKILL.md:3,25,84,114`, `skills/l3io-util-doctor/assets/migrate-state.md:122`, `skills/l3io-util-doctor/steps/bootstrap-state.md:9`
- Modify: `skills/l3io-pm-execute/module.yaml`, `skills/l3io-pm-plan/module.yaml`, `skills/l3io-pm-help/module.yaml`, `skills/l3io-pm-sync/module.yaml` (lines 13, 15, 17 each)

**Interfaces:**
- Produces: a `skills/` tree where every `removed` token either is gone or carries same-line historical evidence — the precondition for Task 10.

These files are **not** generated. Edit them directly; `sync:scripts` will not touch them.

- [ ] **Step 1: `bmad-architect` → `bmad-architecture` in l3io-arch-review**

Four sites. `module.yaml:10` `Wire the standards into core bmad-architect and bmad-code-review via bmad-customize —` → `...core bmad-architecture and bmad-code-review via bmad-customize —`. `module.yaml:18` likewise. `SKILL.md:87` `into** the core \`bmad-architect\` and` → `` into** the core `bmad-architecture` and ``. `customize-architect.md:12` heading `## Overlay for \`bmad-architect\` (design + decisions)` → `` ## Overlay for `bmad-architecture` (design + decisions) ``.

- [ ] **Step 2: The create-story overlay heading**

`customize-architect.md:21`, `## Overlay for \`bmad-create-story\` (technical acceptance criteria)` → `` ## Overlay for the story enricher — legacy `bmad-create-story` (technical acceptance criteria) ``. The word `legacy` satisfies Task 10's rule while keeping the heading accurate for repos that still have the skill.

- [ ] **Step 3: Doctor's historical mentions gain `legacy`**

Six mentions describe legacy projects truthfully; add the word rather than rewriting the claim. Example — `SKILL.md:84`:

```
| `bootstrap-state` | `steps/bootstrap-state.md` | create state nodes from story .md artifacts (legacy `bmad-create-story` workflow) |
```

Do the same at `SKILL.md:3,25,114` and `assets/migrate-state.md:122`, and at
`steps/bootstrap-state.md:9`, which currently reads:

```
created via `bmad-create-story` (or another workflow) without going through `l3io-pm-plan`
```

and becomes:

```
created via the legacy `bmad-create-story` workflow (or another) without going through `l3io-pm-plan`
```

**Doctor's `steps/` are hand-authored, not generated** — `skills/_shared/steps/**` syncs only to
pm-execute, pm-plan and pm-sync. Edit this file directly; do not look for it under `_shared/`.

- [ ] **Step 4: Rewrite the four `l3io-pm` post-install-notes**

These are non-generated files naming four removed skills with no same-line evidence, so they must
be clean before check 17 exists (Task 10). Check 16 requires all four to be **byte-identical** in
the shared fields — edit all four together, with exactly this text:

```yaml
post-install-notes: >
  Required BMad skills from the bmm module: bmad-code-review, bmad-qa-generate-e2e-tests,
  bmad-retrospective, bmad-review (adversarial lens), bmad-sprint-planning (readiness gate).
  bmm is not part of core, so install it with `--modules bmm` if you have not already.
  Story enrichment and implementation run as in-package agents when BMad's
  legacy bmad-create-story / bmad-dev-story skills are absent, so no shim flag is needed.
  Optional: bmad-ux (UX phases skip when absent), l3io-arch-review (epic architecture gate
  and drift reviews), l3io-sec-redteam (closure security review).
  Run /l3io-util-doctor check-deps to confirm what resolved in this project.
  /l3io-pm-sync additionally needs an authenticated GitHub CLI (gh) or a configured GitHub
  MCP server.
  Requires uv on PATH: the Python helpers run via `uv run`.
```

Note the deliberate reflow: `legacy` sits on the **same physical line** as both skill names. An
earlier draft ended the previous line with `legacy`, which check 17 rejects — it inspects one line
at a time. Do not re-wrap this block.

- [ ] **Step 4b: Work from the MEASURED violation list, not from the file list above**

The file lists in this task were assembled by reading citations; a dry run of check 17's real
three-arm logic against the tree found **26 violations**, because several lines carry more than
one dead token. This is the authoritative target list — every entry must end up satisfying an
arm (same-line `legacy`/`historical`, same-line whole-word `replaced_by`, or an `ls … .claude/`
probe):

| File | Line | Token |
|---|---|---|
| `skills/l3io-arch-review/SKILL.md` | 87 | `bmad-architect` |
| `skills/l3io-arch-review/assets/customize-architect.md` | 12 | `bmad-architect` |
| `skills/l3io-arch-review/assets/customize-architect.md` | 21 | `bmad-create-story` |
| `skills/l3io-arch-review/module.yaml` | 10, 18 | `bmad-architect` |
| each of the **four** `l3io-pm-*/module.yaml` | 13 | `bmad-create-story` **and** `bmad-dev-story` |
| each of the **four** `l3io-pm-*/module.yaml` | 15 | `bmad-review-adversarial-general` |
| each of the **four** `l3io-pm-*/module.yaml` | 17 | `bmad-ux-review` |
| `skills/l3io-util-doctor/SKILL.md` | 25, 84, 114 | `bmad-create-story` |
| `skills/l3io-util-doctor/assets/migrate-state.md` | 122 | `bmad-create-story` |
| `skills/l3io-util-doctor/steps/bootstrap-state.md` | 9 | `bmad-create-story` |

The four `module.yaml` files contribute **16** of the 26 — four tokens each — which the earlier
"lines 13/15/17" phrasing understated. The `post-install-notes` rewrite in Step 4 removes all
sixteen at once by replacing that whole block.

**`skills/l3io-util-doctor/SKILL.md:3` is NOT in the list** — it already satisfies an arm. Do not
edit it.

- [ ] **Step 5: Verify every removed token now has same-line evidence**

Mirror check 17's three arms exactly — drop a line if it carries `legacy`/`historical`, or is an
existence probe. Do not exclude by variable name; that would mask real misses.

```bash
grep -rn "bmad-create-story\|bmad-dev-story\|bmad-review-adversarial-general\|bmad-ux-review\|bmad-check-implementation-readiness\|bmad-architect\b" \
  skills/ --include=*.md --include=*.yaml | grep -v superpowers \
  | grep -viE "legacy|historical" \
  | grep -vE "ls .*\.claude/" \
  | grep -vE "bmad-architecture"
```
Expected: no output. Any line printed is one check 17 will reject in Task 10 — fix it here.

- [ ] **Step 6: Regenerate manifests and commit**

```bash
node scripts/write-payload-manifest.mjs
git add skills/l3io-arch-review skills/l3io-util-doctor \
        skills/l3io-pm-execute/module.yaml skills/l3io-pm-plan/module.yaml \
        skills/l3io-pm-help/module.yaml skills/l3io-pm-sync/module.yaml
git commit -s -m "docs: retire stale BMad skill names outside the shared sources"
```

---

### Task 10: check:docs check 17

**Files:**
- Modify: `scripts/check-docs.mjs` (header list after line 1068's entry 16; new function; runner call after `checkModuleYamlAgreement();` at line 1154)
- Modify: `scripts/tests/check-docs.test.mjs` (14 new cases)
- Modify: `CLAUDE.md` ("sixteen checks" → "seventeen")

**Interfaces:**
- Consumes: Task 2's inventory schema (`name`, `status`, `module`, `replaced_by`, `removed_in`, `reason`, `fallback`), and the `read`/`exists`/`walkMarkdown`/`failures`/`notes`/`verbose` helpers already in the script.
- Produces: `checkBmadDependencyInventory()`.

- [ ] **Step 1: Write the failing tests first**

Add to `scripts/tests/check-docs.test.mjs`, following its existing planted-violation pattern (a temp repo, a doctored file, run the checker, assert exit). All 16:

```js
// 1 undeclared token fails; 2 dispatching a removed skill with no same-line evidence fails;
// 3 module.yaml naming an undeclared skill fails; 4 entry missing a status-required field fails;
// 5 duplicate name fails; 6 SCOPE ATTACK: a brand-new skills/<dir>/ with a new step file naming
// an undeclared skill fails; 7 a valid tree passes (exit 0); 8 removed skill on a line that also
// names its replaced_by is allowed + notes; 9 removed skill on a line containing "legacy" is
// allowed + notes; 10 DIVERGENCE FROM CHECK 1: removed skill whose only explanatory word is four
// lines away STILL fails; 11 "_bmad-output" yields no token (lookbehind); 12 bmad-defer and
// bmad-l3io-extensions skipped via not-a-skill; 13 not-a-skill without reason fails;
// 14 fallback naming an undeclared skill fails; 15 THE PROBE ARM: an `ls .claude/...` existence
// probe naming a removed skill is allowed, while a prose dispatch of the same name still fails;
// 16 THE TOKEN-BOUNDARY HOLE: a line naming only bmad-ux-review fails, even though its
// replaced_by (bmad-ux) is a substring of it.

test("check 17: a step file dispatching a removed skill fails", async () => {
  const repo = await plantRepo();
  await writeFile(join(repo, "skills/l3io-pm-execute/steps/x.md"),
    "Spawn `bmad-dev-story` subagent with the story path.\n");
  const { code, stderr } = await runCheckDocs(repo);
  assert.equal(code, 1);
  assert.match(stderr, /dispatches removed skill 'bmad-dev-story'/);
});

test("check 17: an explanatory word four lines away does NOT excuse a dispatch", async () => {
  const repo = await plantRepo();
  await writeFile(join(repo, "skills/l3io-pm-execute/steps/x.md"),
    "This skill was removed upstream.\n\n\n\nSpawn `bmad-dev-story` subagent.\n");
  const { code, stderr } = await runCheckDocs(repo);
  assert.equal(code, 1, "check 1's ±4-line window would have allowed this; check 17 must not");
  assert.match(stderr, /dispatches removed skill/);
});

// Case 15 — the probe arm. Without this the check rejects the resolution blocks that
// implement tolerance, i.e. it would forbid the fix it exists to protect.
test("check 17: an existence probe naming a removed skill is allowed", async () => {
  const repo = await plantRepo();
  await writeFile(join(repo, "skills/l3io-pm-execute/steps/x.md"),
    "```bash\nls {project-root}/.claude/skills/bmad-dev-story/SKILL.md 2>/dev/null\n```\n");
  const { code } = await runCheckDocs(repo);
  assert.equal(code, 0, "a probe line cannot dispatch anything; it must pass");
});

// Case 16 — the token-boundary hole. bmad-ux-review's replaced_by is bmad-ux, which is a
// SUBSTRING of it, so a naive includes() check would let the guard pass its own worst case.
test("check 17: replaced_by must match as a token, not a substring", async () => {
  const repo = await plantRepo();
  await writeFile(join(repo, "skills/l3io-pm-execute/steps/x.md"),
    "Invoke `bmad-ux-review` with the story files.\n");
  const { code, stderr } = await runCheckDocs(repo);
  assert.equal(code, 1, "bmad-ux-review contains 'bmad-ux'; substring matching would pass this");
  assert.match(stderr, /dispatches removed skill 'bmad-ux-review'/);
});
```

Write the remaining fourteen in the same shape, one assertion each.

- [ ] **Step 2: Run them to verify they fail**

Run: `npm run test:scripts`
Expected: the 16 new tests fail (`checkBmadDependencyInventory is not defined` or no failure raised).

- [ ] **Step 3: Implement the check**

Insert after the check-16 block, matching its header-comment style:

```js
// ---------------------------------------------------------------------------
// 17. Every bmad-* name a runtime directive uses is declared in one inventory.
//
// Three BMad releases renamed or removed skills this package dispatches and nothing noticed:
// bmad-create-story and bmad-dev-story became shims, bmad-review-adversarial-general merged
// into bmad-review, and bmad-check-implementation-readiness was removed. A clean v6.12.0
// install could not run the dev loop, and the failure was invisible until someone installed
// BMad by hand and looked.
//
// A removed name may still appear where the mention is self-evidently historical, but the
// evidence must be on the SAME LINE. Check 1 widens to a ±4-line window; dry-run here, that
// window excused l3io-util-doctor/SKILL.md:84 because an unrelated routing row nearby said
// "remove migration backup files". An accidental pass is how a guard starts crying wolf.
//
// Scope is derived by walking skills/ markdown and every skills/<dir>/module.yaml, never a list.
// ---------------------------------------------------------------------------
const DEP_INVENTORY = "skills/l3io-util-doctor/assets/bmad-dependencies.json";
const BMAD_TOKEN_RE = /(?<![\w-])bmad-[a-z0-9-]+/g;
const DEP_STATUSES = ["required", "optional", "removed", "not-a-skill"];

function checkBmadDependencyInventory() {
  if (!exists(DEP_INVENTORY)) {
    failures.push(`${DEP_INVENTORY}: missing — it is the one place every bmad-* name is declared`);
    return;
  }
  let inv;
  try {
    inv = JSON.parse(read(DEP_INVENTORY));
  } catch (e) {
    failures.push(`${DEP_INVENTORY}: not valid JSON — ${e.message}`);
    return;
  }
  const byName = new Map();
  for (const e of inv.skills ?? []) {
    if (!e.name) { failures.push(`${DEP_INVENTORY}: an entry has no name`); continue; }
    if (byName.has(e.name)) { failures.push(`${DEP_INVENTORY}: duplicate entry '${e.name}'`); continue; }
    byName.set(e.name, e);
    if (!DEP_STATUSES.includes(e.status)) {
      failures.push(`${DEP_INVENTORY}: '${e.name}' has unknown status '${e.status}'`);
    } else if ((e.status === "required" || e.status === "optional") && !e.module) {
      failures.push(`${DEP_INVENTORY}: '${e.name}' is ${e.status} but names no module`);
    } else if (e.status === "removed" && !(e.replaced_by && e.removed_in)) {
      failures.push(`${DEP_INVENTORY}: '${e.name}' is removed but lacks replaced_by/removed_in`);
    } else if (e.status === "not-a-skill" && !e.reason) {
      failures.push(`${DEP_INVENTORY}: '${e.name}' is not-a-skill but gives no reason`);
    }
  }
  for (const e of byName.values()) {
    if (e.fallback && !byName.has(e.fallback)) {
      failures.push(`${DEP_INVENTORY}: '${e.name}' falls back to '${e.fallback}', not declared`);
    }
  }

  const sources = [...walkMarkdown("skills")];
  for (const entry of fs.readdirSync(path.join(repoRoot, "skills"), { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const rel = `skills/${entry.name}/module.yaml`;
    if (exists(rel)) sources.push(rel);
  }

  let checked = 0;
  for (const rel of sources) {
    const lines = read(rel).split("\n");
    for (let i = 0; i < lines.length; i += 1) {
      for (const m of lines[i].matchAll(BMAD_TOKEN_RE)) {
        const name = m[0];
        checked += 1;
        const e = byName.get(name);
        if (!e) {
          failures.push(`${rel}:${i + 1}: names '${name}', not declared in ${DEP_INVENTORY}\n` +
            `      context: ${lines[i].trim().slice(0, 110)}`);
          continue;
        }
        if (e.status !== "removed") continue;
        const line = lines[i];
        // Three arms. (c) is load-bearing: the tolerance design REQUIRES step files to probe
        // for the pre-6.12 names, so a rule forbidding the name would forbid the fix. A probe
        // line cannot dispatch anything. (b) must be token-bounded — "bmad-ux-review".includes
        // ("bmad-ux") is true, which would let the guard pass its own worst case.
        const isProbe = line.includes("ls ") && line.includes(".claude/");
        const replacedByToken = new RegExp(`(?<![\\w-])${e.replaced_by.split(" ")[0]}(?![\\w-])`);
        const historical = isProbe || replacedByToken.test(line) ||
          /\blegacy\b|\bhistorical\b/i.test(line);
        if (historical) {
          notes.push(`${rel}:${i + 1}: names removed skill '${name}' as history — allowed`);
          continue;
        }
        failures.push(`${rel}:${i + 1}: dispatches removed skill '${name}' — replaced by ` +
          `'${e.replaced_by}'. If the mention is historical, say so on the same line.\n` +
          `      context: ${line.trim().slice(0, 110)}`);
      }
    }
  }
  if (verbose) {
    console.log(`  bmad-dependency-inventory: ${checked} reference(s), ${byName.size} declared`);
  }
}
```

Add the header-list entry beside the others and the runner call after `checkModuleYamlAgreement();`:

```js
checkBmadDependencyInventory();
```

- [ ] **Step 4: Run the tests and the real checker**

```bash
npm run test:scripts && npm run check:docs
```
Expected: all tests pass; `check:docs` exits 0 against the real tree (Tasks 3–9 made it clean).

- [ ] **Step 5: Non-hollow proof**

Comment out the `checkBmadDependencyInventory();` call, run `npm run test:scripts`, confirm the 14 cases fail, then restore and re-run to green.

- [ ] **Step 6: Bump the check count and commit**

`CLAUDE.md`: "sixteen checks" → "seventeen checks". Also extend that paragraph with check 17's one-line description, in the style of the existing entries.

```bash
git add scripts/check-docs.mjs scripts/tests/check-docs.test.mjs CLAUDE.md
git commit -s -m "feat(infra): add check 17, every BMad dependency is declared"
```

---

### Task 11: bmad-deps.py and its suite

**Files:**
- Create: `skills/l3io-util-doctor/scripts/bmad-deps.py`
- Create: `skills/l3io-util-doctor/scripts/tests/test-bmad-deps.py`
- Modify: `.github/workflows/checks.yml` (one step after the `audit-backlog.py` step)

**Interfaces:**
- Consumes: Task 2's inventory; `_bmad/_config/manifest.yaml` with keys `installation.version`, `installation.installShims` (absent pre-6.12), `modules[].name`, `ides[]`.
- Produces: `verify` exiting 0/2/3/4, and `--format json` emitting `{"bmad_version", "shims_installed", "modules", "resolved": [{"name","status","resolved_as","path"}], "missing_required": [...], "shims_in_use": [...]}`.

- [ ] **Step 1: Write the failing suite first**

Copy the leak-guard block verbatim from `skills/l3io-util-doctor/scripts/tests/test-audit-backlog.py` (setUpModule/tearDownModule, prefix `test-bmad-deps-`). Drive the real CLI via `subprocess`; build fixture trees with `tempfile.mkdtemp()`. All 14 cases:

```python
# 1 all required present -> 0; 2 required missing -> 3; 3 optional missing -> 0 + warning;
# 4 v6.12 layout <name>/SKILL.md detected; 5 legacy flat <name>.md detected;
# 6 manifest absent -> 4; 7 malformed inventory -> 2; 8 --format json shape;
# 9 preferred absent + fallback present -> 0, output names the fallback;
# 10 both present -> 0, resolves to the PREFERRED name;
# 11 both absent, required -> 3; 12 both absent, optional -> 0 + warning;
# 13 a tree holding only pre-6.12 names resolves EVERY site via fallback (spec 12.2);
# 14 a removed skill present on disk is reported as a shim in use.

def _tree(self, names, layout="skills", version="6.12.0"):
    """Build a project root whose .claude/<layout>/ contains `names`."""
    root = tempfile.mkdtemp()
    for n in names:
        if layout == "skills":
            d = os.path.join(root, ".claude", "skills", n)
            os.makedirs(d, exist_ok=True)
            pathlib.Path(d, "SKILL.md").write_text("x", encoding="utf-8")
        else:
            d = os.path.join(root, ".claude", "commands")
            os.makedirs(d, exist_ok=True)
            pathlib.Path(d, f"{n}.md").write_text("x", encoding="utf-8")
    mf = os.path.join(root, "_bmad", "_config")
    os.makedirs(mf, exist_ok=True)
    pathlib.Path(mf, "manifest.yaml").write_text(
        f"installation:\n  version: {version}\nmodules:\n  - name: core\n"
        f"  - name: bmm\nides:\n  - claude-code\n", encoding="utf-8")
    return root

def test_fallback_resolves_when_preferred_absent(self):
    root = self._tree(["bmad-review-adversarial-general"], layout="commands", version="6.11.0")
    code, out = self.run_cli(["verify", "--project-root", root, "--format", "json"])
    self.assertEqual(code, 0)
    entry = next(r for r in json.loads(out)["resolved"] if r["name"] == "bmad-review")
    self.assertEqual(entry["resolved_as"], "bmad-review-adversarial-general")

def test_preferred_wins_when_both_present(self):
    root = self._tree(["bmad-review", "bmad-review-adversarial-general"])
    code, out = self.run_cli(["verify", "--project-root", root, "--format", "json"])
    self.assertEqual(code, 0)
    entry = next(r for r in json.loads(out)["resolved"] if r["name"] == "bmad-review")
    self.assertEqual(entry["resolved_as"], "bmad-review")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run -q --with 'ruamel.yaml>=0.18' python3 skills/l3io-util-doctor/scripts/tests/test-bmad-deps.py`
Expected: FAIL — the script does not exist.

- [ ] **Step 3: Implement the script**

```python
#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
"""
bmad-deps.py -- verify the installed BMad skills against the declared inventory. Read-only.

Why this exists
---------------
Three BMad releases renamed or removed skills this package dispatches, and nothing noticed
until someone installed 6.12.0 by hand: bmad-create-story and bmad-dev-story became shims,
bmad-review-adversarial-general merged into bmad-review, and
bmad-check-implementation-readiness was removed. Separately every presence probe read
.claude/commands/ while 6.12.0 installs to .claude/skills/, so an installed reviewer looked
absent and its gate silently self-skipped -- a skipped gate is indistinguishable from a
passed one.

check:docs check 17 asserts the step files agree with the inventory, but CI has no BMad
install (_bmad/ is gitignored). This script is the other half: it compares the same inventory
against a real install. Single consumer (l3io-util-doctor), so it ships in doctor's own
scripts/ per ADR-0001, like audit-backlog.py, with no sync group.

Usage
-----
  bmad-deps.py verify --project-root R [--inventory PATH] [--format {text,json}]

Exit 0 when every required skill resolves (optional ones only warn), 2 on a usage error or an
unparseable inventory, 3 when a required skill resolves nowhere, 4 when the inventory or the
BMad manifest cannot be read.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

from ruamel.yaml import YAML

DEFAULT_INVENTORY = pathlib.Path(__file__).resolve().parent.parent / "assets" / "bmad-dependencies.json"


def resolve(name: str, project_root: str) -> str | None:
    """Return the path `name` resolves to, or None. Both layouts, both roots."""
    roots = [os.path.join(project_root, ".claude"),
             os.path.join(os.path.expanduser("~"), ".claude")]
    for root in roots:
        for rel in (os.path.join("skills", name, "SKILL.md"), os.path.join("commands", f"{name}.md")):
            p = os.path.join(root, rel)
            if os.path.exists(p):
                return p
    return None


def read_manifest(project_root: str):
    """(version, shims_installed, [module names]) or None when unreadable."""
    mf = os.path.join(project_root, "_bmad", "_config", "manifest.yaml")
    if not os.path.exists(mf):
        return None
    try:
        with open(mf, encoding="utf-8") as fh:
            data = YAML(typ="safe").load(fh) or {}
    except Exception:
        return None
    inst = data.get("installation") or {}
    mods = [m.get("name") for m in (data.get("modules") or []) if isinstance(m, dict)]
    return inst.get("version"), bool(inst.get("installShims", False)), mods


def verify(args: argparse.Namespace) -> int:
    try:
        inv = json.loads(pathlib.Path(args.inventory).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read inventory {args.inventory}: {exc}", file=sys.stderr)
        return 4
    man = read_manifest(args.project_root)
    if man is None:
        print(f"cannot read {args.project_root}/_bmad/_config/manifest.yaml — is BMad installed?",
              file=sys.stderr)
        return 4
    version, shims, modules = man

    resolved, missing, shims_in_use, warnings = [], [], [], []
    for e in inv.get("skills") or []:
        status = e.get("status")
        name = e.get("name")
        if status == "not-a-skill":
            continue
        if status == "removed":
            hit = resolve(name, args.project_root)
            if hit:
                shims_in_use.append({"name": name, "path": hit,
                                     "replaced_by": e.get("replaced_by")})
            continue
        hit, used = resolve(name, args.project_root), name
        if hit is None and e.get("fallback"):
            hit, used = resolve(e["fallback"], args.project_root), e["fallback"]
        if hit is None:
            (missing if status == "required" else warnings).append(name)
            continue
        resolved.append({"name": name, "status": status, "resolved_as": used, "path": hit})

    if args.format == "json":
        print(json.dumps({"bmad_version": version, "shims_installed": shims,
                          "modules": modules, "resolved": resolved,
                          "missing_required": missing, "optional_absent": warnings,
                          "shims_in_use": shims_in_use}, indent=2))
    else:
        print(f"BMad {version} — modules: {', '.join(modules)}")
        for r in resolved:
            note = "" if r["resolved_as"] == r["name"] else f"  (via {r['resolved_as']})"
            print(f"  ok       {r['name']}{note}")
        for n in warnings:
            print(f"  absent   {n} (optional — its phase self-skips)")
        for s in shims_in_use:
            print(f"  shim     {s['name']} is a deprecated shim; {s['replaced_by']} replaces it")
        for n in missing:
            print(f"  MISSING  {n} (required)")
        if missing:
            print(f"\n{len(missing)} required skill(s) resolve nowhere. Install them, or run "
                  f"`npx bmad-method install --modules bmm` to refresh.", file=sys.stderr)

    return 3 if missing else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify", help="check the installed skills against the inventory")
    v.add_argument("--project-root", required=True)
    v.add_argument("--inventory", default=str(DEFAULT_INVENTORY))
    v.add_argument("--format", choices=("text", "json"), default="text")
    v.set_defaults(fn=verify)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the suite to green**

Run: `uv run -q --with 'ruamel.yaml>=0.18' python3 skills/l3io-util-doctor/scripts/tests/test-bmad-deps.py`
Expected: all 14 pass.

- [ ] **Step 5: Run it against this repo's real 6.11.0 install**

Run: `uv run -q --with 'ruamel.yaml>=0.18' python3 skills/l3io-util-doctor/scripts/bmad-deps.py verify --project-root "$PWD"`
Expected: exit 0. `bmad-review` resolves **via** `bmad-review-adversarial-general`, and readiness via `bmad-check-implementation-readiness` — the live proof of spec §12 criterion 2.

- [ ] **Step 6: Non-hollow proof**

Break `resolve()` to only check `commands/`, confirm the v6.12-layout tests fail, restore, re-run green.

- [ ] **Step 7: Add the CI step and commit**

In `.github/workflows/checks.yml`, after the `audit-backlog.py unit tests` step:

```yaml
    - name: bmad-deps.py unit tests
      run: uv run -q --with 'ruamel.yaml>=0.18' python3 skills/l3io-util-doctor/scripts/tests/test-bmad-deps.py
```

```bash
node scripts/write-payload-manifest.mjs
git add skills/l3io-util-doctor/scripts/bmad-deps.py \
        skills/l3io-util-doctor/scripts/tests/test-bmad-deps.py \
        skills/l3io-util-doctor/payload-manifest.json .github/workflows/checks.yml
git commit -s -m "feat(l3io-util): verify installed BMad skills against the inventory"
```

---

### Task 12: The check-deps doctor mode

**Files:**
- Create: `skills/l3io-util-doctor/steps/check-deps.md`
- Modify: `skills/l3io-util-doctor/SKILL.md` (routing row; lines 56–57 counts)
- Modify: `CLAUDE.md:12` (mode count)
- Modify: `docs/l3io-util-reference.md` (mode table row)

**Interfaces:**
- Consumes: Task 11's `bmad-deps.py verify`.

**Do not touch `docs/l3io-util-reference.md:86`.** Its "nineteen numbered read-only checks (Checks 1–19)" is the *health-check's* count, not the mode count, and check 15 does not read it.

- [ ] **Step 1: Write the mode file**

```markdown
# check-deps — verify BMad dependencies

Invoked with `check-deps`. **Read-only.** Reports which BMad skills this package needs, which
resolved, and which deprecated shims are still being used.

## 1. Run the verifier

```bash
uv run {skill-root}/scripts/bmad-deps.py verify --project-root {project-root}
```

## 2. Report

Print the output as-is. Then:

- Exit 0, nothing absent → `DONE — all BMad dependencies resolve.`
- Exit 0 with `absent` lines → `DONE — <n> optional dependency(ies) absent; their phases
  self-skip.` Name them, so a self-skipped gate is never mistaken for a passed one.
- Exit 0 with `shim` lines → `DONE — <n> deprecated shim(s) in use.` These work today and are
  removed at BMad v7; recommend upgrading the install.
- Exit 3 → `BLOCKED: <n> required BMad skill(s) resolve nowhere.` Print the remedy the script
  printed.
- Exit 4 → `BLOCKED: BMad is not installed here, or its manifest is unreadable.`
- Exit 2 → `FAILED: <the script's stderr>`

Change nothing. This mode never writes.
```

- [ ] **Step 2: Add the routing row**

In `SKILL.md`'s keyword table, after the `backlog` row (keeping read-only modes together):

```
| `check-deps` | `steps/check-deps.md` | read-only — verify BMad skill dependencies resolve |
```

- [ ] **Step 3: Bump both mode-count claims**

Check 15 derives the count from `steps/`, the routing table, and the files SKILL.md references, then compares two named claim sites. Adding one mode makes it **twenty**:

- `SKILL.md:56` `carries nineteen procedures and a run needs one, so inlining them all charged every` → `carries twenty procedures ...`
- `SKILL.md:57` `invocation for eighteen it would not execute.` → `invocation for nineteen it would not execute.`
- `CLAUDE.md:12` `each of its nineteen modes lives in its own \`steps/\` file` → `each of its twenty modes ...`

- [ ] **Step 4: Add the reference row**

In `docs/l3io-util-reference.md`'s mode table (rows near lines 42–63), add:

```
| `check-deps` | Verifies every BMad skill this package dispatches resolves in this project, reports deprecated shims still in use, and names optional dependencies whose phases will self-skip. Read-only. |
```

- [ ] **Step 5: Verify check 15 agrees**

Run: `npm run check:docs`
Expected: exit 0. A count mismatch prints `mode count derivations disagree` or `says "nineteen" procedures, but the doctor has 20 mode(s)`.

- [ ] **Step 6: Regenerate and commit**

```bash
node scripts/write-payload-manifest.mjs
git add skills/l3io-util-doctor/steps/check-deps.md skills/l3io-util-doctor/SKILL.md \
        skills/l3io-util-doctor/payload-manifest.json CLAUDE.md docs/l3io-util-reference.md
git commit -s -m "feat(l3io-util): add the check-deps doctor mode"
```

---

### Task 13: Documentation and configuration truth

**Files:**
- Modify: four `skills/l3io-pm-*/module.yaml` (lines 13, 15, 17 each)
- Modify: `CLAUDE.md` (Dependencies section)
- Modify: `docs/l3io-pm-reference.md:898,919`, `docs/l3io-arch-reference.md:9,96`, `docs/architecture.md:57`, `docs/getting-started.md:136`
- Modify: `README.md`, `docs/getting-started.md` (install notes)

**Interfaces:**
- Consumes: the resolution behavior from Tasks 3–7. Check 16 requires all four `l3io-pm` files to stay **byte-identical** in the shared fields — edit all four together.

- [ ] **Step 1: Confirm the four `l3io-pm` module.yaml files still agree**

Their `post-install-notes` were rewritten in Task 9 (they had to be clean before check 17
existed). This step only verifies check 16's byte-identical requirement still holds after the
intervening tasks:

```bash
npm run check:docs 2>&1 | grep -i "module.yaml" || echo "module.yaml fields agree"
```
Expected: `module.yaml fields agree`.

- [ ] **Step 2: Update CLAUDE.md's Dependencies section**

Replace the required/optional lists with the tolerance-aware version, naming `check-deps` as the way to verify, and stating that no minimum BMad version is required.

- [ ] **Step 3: Fix the reference rows**

`docs/l3io-pm-reference.md:898` and `:919` — replace `bmad-check-implementation-readiness` with `bmad-sprint-planning intent=readiness (legacy bmad-check-implementation-readiness)`.

`docs/l3io-arch-reference.md:9,96`, `docs/architecture.md:57`, `docs/getting-started.md:136` — `bmad-architect` → `bmad-architecture`.

- [ ] **Step 4: Add the install note**

In `README.md` and `docs/getting-started.md`, beside the install command: BMad ≥6.12.0 installs skills to `.claude/skills/` and needs no `--shims` flag; older installs keep working unchanged. **Do not state a minimum version.**

- [ ] **Step 5: Verify and commit**

```bash
npm run check:docs && npm run check:manifest
git add skills/l3io-pm-execute/module.yaml skills/l3io-pm-plan/module.yaml \
        skills/l3io-pm-help/module.yaml skills/l3io-pm-sync/module.yaml \
        CLAUDE.md README.md docs/getting-started.md docs/l3io-pm-reference.md \
        docs/l3io-arch-reference.md docs/architecture.md
git commit -s -m "docs: state BMad dependencies as they resolve on both install shapes"
```

---

### Task 14: Full verification

**Files:** none created or modified unless a gate fails.

- [ ] **Step 1: Regenerate from source and confirm no drift**

```bash
npm run sync:scripts && node scripts/write-payload-manifest.mjs
git status --porcelain
```
Expected: empty. A non-empty result means an earlier task edited a generated copy instead of its `_shared/` source — fix at the source and re-sync.

- [ ] **Step 2: All five gates**

```bash
npm run check:scripts && npm run check:docs && npm run check:manifest \
  && npm run check:version && npm run test:scripts
```
Expected: all exit 0.

- [ ] **Step 3: Every Python suite**

```bash
python3 -m pip install --quiet 'ruamel.yaml>=0.18'
python3 skills/_shared/tests/test-pm-status.py
uv run skills/_shared/tests/test-write-module-config.py
uv run --with pyyaml skills/l3io-pm-sync/scripts/tests/test-drift-report.py
uv run -q --with 'markdown-it-py>=3' --with 'mdit-py-plugins>=0.4' --with 'ruamel.yaml>=0.18' --with 'unidiff>=0.7' --with 'tenacity>=8' python3 skills/_shared/tests/test-spec-align.py
uv run skills/l3io-sec-redteam/scripts/tests/test-init-sanctum.py
uv run -q --with 'ruamel.yaml>=0.18' python3 skills/l3io-util-doctor/scripts/tests/test-audit-backlog.py
uv run -q --with 'ruamel.yaml>=0.18' python3 skills/l3io-util-doctor/scripts/tests/test-bmad-deps.py
```
Expected: all pass.

- [ ] **Step 4: Acceptance 1 — a clean v6.12.0 install**

```bash
D=$(mktemp -d) && git -C "$D" init -q .
npx --yes bmad-method@latest install --yes --modules bmm --tools claude-code --directory "$D"
uv run -q --with 'ruamel.yaml>=0.18' python3 skills/l3io-util-doctor/scripts/bmad-deps.py \
  verify --project-root "$D"
```
Expected: exit 0, every required skill resolves, **no shim in use**.

- [ ] **Step 5: Acceptance 2 — an install that works today is unchanged**

```bash
uv run -q --with 'ruamel.yaml>=0.18' python3 skills/l3io-util-doctor/scripts/bmad-deps.py \
  verify --project-root "$PWD" --format json
```
Expected: **exit 3** against this repo's real BMad **6.11.0**, and that is the correct result — not a
failure of the migration. Measured directly: this checkout is a **core-only** install. `bmm` is not
installed (`modules: core, l3io-pm, l3io-sec, l3io-util`), so four required skills *and their
fallbacks* are genuinely absent: `bmad-code-review`, `bmad-retrospective`,
`bmad-qa-generate-e2e-tests`, `bmad-sprint-planning`. The script is reporting
this machine truthfully. (`bmad-architecture` was the fifth until the final fix wave
reclassified it `optional` — nothing dispatches it; see spec §7.1 — so it now appears as an
absent optional instead, and the count is four. The exit code is unchanged at 3.)

Two further things to confirm in the JSON, both of which an earlier draft of this step predicted
wrongly:

- `bmad-review` resolves as the **preferred** name, not via its fallback — it is a *core* skill and
  is present at `.claude/skills/bmad-review/`. `resolved_as` must equal `bmad-review`.
- `shims_installed` is `false`, read from a manifest that has **no `installShims` key at all** (6.11.0
  predates it). This is the live proof that the key is treated as absent-means-false rather than
  assumed present — a script that assumed it would crash on exactly the older install this design
  protects.
- `shims_in_use` contains `bmad-review-adversarial-general`, since that legacy skill is on disk here.

**The backward-compatibility guarantee is not proven by this run**, because this machine has no
`bmm` to fall back within. It is proven machine-independently by
`test_pre_612_only_tree_resolves_every_site_via_fallback` in
`skills/l3io-util-doctor/scripts/tests/test-bmad-deps.py`, which builds a tree holding **only**
pre-6.12 names and asserts every site resolves via `fallback`. Confirm that test is present and
passing; it is the executable form of the design spec's second acceptance criterion, and a stronger
proof than any single machine's state.

- [ ] **Step 6: Confirm nothing was pushed and no version moved**

```bash
git log --oneline origin/main..HEAD
git diff origin/main..HEAD -- package.json | grep -E "^\+.*version" || echo "no version change"
```
Expected: the task commits plus the three pre-existing ones; `no version change`.
