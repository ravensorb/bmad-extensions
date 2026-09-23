# Module Help Registration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every `module-help.csv` row true, and make every user-initiated capability reachable from BMad's help surface.

**Architecture:** The four `skills/*/assets/module-help.csv` files are what BMad's installer copies into `_bmad/<code>/module-help.csv` and assembles into `_bmad/_config/bmad-help.csv` — verified by diffing a real install against the authored file (identical). They are the routing surface: a capability with no row cannot be selected from the menu, and a row with a wrong flag teaches an LLM to type a command that does not exist. This plan corrects the rows and then adds a `check:module` rule so the registration cannot silently drift from each skill's own keyword table again.

**Tech Stack:** CSV (parsed with `csv-parse`), `scripts/check-module.mjs`, `scripts/tests/check-module.test.mjs`.

**Source:** BMad's own module-builder validation workflow, `.claude/skills/bmad-module-builder/references/validate-module.md` §3 "Quality Assessment". Step 2 (`validate-module.py`) passes for all four modules and cannot see any of this. Full assessment: `/tmp/claude-1384001609/module-builder-step3.md`.

## Global Constraints

- Conventional Commits; **every commit needs DCO sign-off**. `git commit -s` appends `Signed-off-by` last and does not dedupe — write all three trailers into the `-m` body and omit `-s`. Order: `Signed-off-by: Shawn Anderson <sanderson@eye-catcher.com>`, then `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`, then `Claude-Session: https://claude.ai/code/session_014DuCKCCF5scofVSPGvvn97`.
- **Never `git add -A` or `git add .`** — explicit paths only. Other sessions share this checkout.
- Never hand-edit `skills/<skill>/scripts/*` payload copies or any `payload-manifest.json`.
- `pm-status.py`'s version marker and `PM_STATUS_VERSION` must not move.
- `CHANGELOG.md`, `docs/superpowers/plans/**` (except this file), `docs/superpowers/specs/**`, `docs/decision-logs/**` untouched.
- **Use libraries, never hand-rolled parsers.** `csv-parse` and `yaml` are installed; CI runs `npm ci`.
- `uv run`, never bare `python3`.
- All six gates green at the end of **every** task: `check:docs` · `check:scripts` · `check:manifest` · `check:version` · `check:module` · `test:scripts`. Run `test:scripts` alone — it takes ~10 minutes and other sessions share this checkout.
- Adding a `check:module` rule changes no `check:docs` count; adding a `check:docs` check does. Expect check 18 red in that case and fix the prose, not the check.

---

## Phase 0 — Cleanup (do these first)

Added after a full audit of all 21 `l3io-util-doctor` modes (`/tmp/claude-1384001609/doctor-mode-audit.md`) and a correction to the Step 3 assessment. Registration is **last** because Phase 0 changes what there is to register — Task 5 was going to register `normalize`, which Task 0C deletes.

---

### Task 0A: Fix the four live defects

Each is wrong for real users today, and each was verified against the source, not inferred.

**Files:** `skills/l3io-util-doctor/steps/clean-legacy.md`, `steps/health-check.md`, `steps/triage.md`, `steps/bootstrap-state.md`, `steps/update-ai-rules.md`

- [ ] **Step 1: `clean-legacy` sweeps a directory the file is never in**

`clean-legacy.md:19` looks for `*.yaml.v1` in `{project-root}/_bmad/` and attributes it to `migrate-schema`. **Verified:** `skills/_shared/pm-status.py:1206` writes `backup = calibration_path(state_root) + ".v1"` — that is `{pm_state_root}/`, not `_bmad/`. And `grep -c 'backup\|\.v1' steps/schema-migration.md` returns **0**: `migrate-schema` creates no backup at all. Fix the path and the attribution, and fix health-check **Check 9**, which sweeps the same wrong directory. Derive the location from `calibration_path()` rather than typing a second path that can drift the same way.

- [ ] **Step 2: `triage` and Check 13 disagree about their own precondition**

`health-check.md:206-208` states Check 13 is deliberately **not** gated on `issues.yaml` — it flags 1d/1h/1j story-node findings. `triage.md:17` exits immediately when `issues.yaml` is absent. So the health check flags findings the fixer then refuses to look at. Decide which is right, make both agree, and say in the commit which you changed and why.

- [ ] **Step 3: `bootstrap-state` guarantees a placement anomaly**

BS2 `:109` files an all-done **epic** under `archived/done`; BS4 `:242-244` writes an all-done **sprint** as `in-progress`, and BS3 `:145` hardcodes it. The result violates the placement rule the health check then flags. Also resolve the all-done-sprint rule being stated twice, differently — the audit could not determine intent from the files, so decide it and record the decision.

- [ ] **Step 4: `update-ai-rules` has two targets**

`:3`, `SKILL.md:39` and AR1 `:33` all say "the currently running AI system's file". AR5 `:75-77` says "**Always target `AGENTS.md` regardless of which AI system is running**", and restates the gate differently. Pick one, make all four agree.

- [ ] **Step 5: Verify and commit**

Six gates green. One commit per defect is fine and probably clearer.

---

### Task 0B: Guard the installer's silent fallthrough to synthesis

**Files:** `scripts/check-module.mjs`, `scripts/tests/check-module.test.mjs`

BMad's `PluginResolver` tries five strategies per plugin. **Verified at `plugin-resolver.js:219-220`:** `_tryMultipleStandalone` requires *every* listed skill to carry both `assets/module.yaml` and `assets/module-help.csv`; a partial match hits `// Partial match: fall through to strategy 5` and `return null` — **silently**. Strategy 5 synthesizes a stub catalog from frontmatter: `action: activate`, title-cased names, generated menu codes, no relationships. The install exits 0.

This already happened to this package: the `_bmad/` tree from 2026-09-14 holds exactly those stub rows, `l3io-util-cleanup` included.

The margin at HEAD is one file and one list entry. `l3io-pm` resolves by strategy 2 only because `skills/l3io-pm-setup/assets/module-help.csv` exists and that directory is named `*-setup`. The other three resolve by strategy 3 only because their plugin lists **exactly one** skill — adding a second silently drops them to synthesis.

- [ ] **Step 1: Write the failing test first**

Add a second skill to `l3io-arch`'s `skills` array in a fixture and assert exit 1. This is a **scope attack** — deleting a CSV is the easy case and proves less.

- [ ] **Step 2: Implement the rule**

Read `.claude-plugin/marketplace.json`, derive the skill set from it (never a hand-list), and for each plugin determine from the files on disk which strategy `PluginResolver` would select. Fail unless it is 1–4. Mirror the resolver's real conditions — read `plugin-resolver.js`, do not reconstruct them from this description.

- [ ] **Step 3: Prove it and commit**

Confirm the real tree passes, confirm the scope attack fails, revert byte-identical.

---

### Task 0C: Remove, merge and demote the modes the audit found dead or redundant

21 modes → ~14. Every change below carries the audit's evidence; re-derive it rather than trusting this summary.

**Files:** `skills/l3io-util-doctor/SKILL.md` (keyword table), the affected `steps/*.md`, `steps/health-check.md` (its proposals), and every doc naming a removed keyword.

- [ ] **Step 1: Remove `normalize`**

A pure composition of `reconcile-status` + `sort-status`. Zero health-check references, zero shipped docs reference it, and on a migrated project `reconcile-status` exits (`:22-26`) so `normalize` **is** `sort-status`. Both its descriptions are already wrong.

- [ ] **Step 2: Merge `backlog` into `stats`**

`backlog` is one `list-issues` call and `stats` already reads the same `--all` JSON. Preserve the per-item table as an expansion of `stats`; remove the keyword.

- [ ] **Step 3: Fold `split-status` + `reconcile-status` into `migrate-state`**

A closed pair — one produces the shape the other cleans. `assets/migrate-state.md:161-174` already reads the unsplit files as one logical set and `:235-302` performs equivalent status normalization. `split-status.md:11-20` says nothing downstream requires the three-file shape.

- [ ] **Step 4: Fold `rename-active` and `rename-epic-dirs` into their detecting checks**

Single renames with no standalone caller. `rename-active` cannot fire on any migrated project. Keep the behaviour, drop the top-level keywords.

- [ ] **Step 5: Demote `overlay` to a spec**

All three actions report "nothing ships yet" by construction — `assets/overlays/` holds only `README.md`. Keep the file; remove the keyword until a later phase populates it.

- [ ] **Step 6: Sweep every reference**

`SKILL.md`'s table, `health-check.md`'s proposals, `CLAUDE.md`, `README.md`, `docs/l3io-util-reference.md`, `docs/upgrading.md`, `docs/getting-started.md`. A removed keyword named anywhere is a runtime defect, not a doc nit. `check:docs` check 1 will catch skill names but **not** mode keywords — sweep by hand and consider whether a check should.

- [ ] **Step 7: Verify and commit**

Six gates green; `check:module`'s mode-count prose and `CLAUDE.md`'s "twenty-one modes" both change.

---

### Task 1: Delete the two flags that do not exist

The sharpest finding, and the one this repo has explicitly committed to not repeating. `CLAUDE.md` §3 cites it from the project's own history: *"three committed documents prescribed a command-line flag that did not exist; agents followed it for weeks because the instruction read as authoritative."* These sit in the file whose entire purpose is telling an LLM how to invoke these skills.

**Files:**
- Modify: `skills/l3io-pm-setup/assets/module-help.csv` (the `l3io-pm-plan,Plan` row's `args`)
- Modify: `skills/l3io-sec-redteam/assets/module-help.csv` (the `args`)
- Modify: `skills/l3io-sec-redteam/references/first-breath.md:55`

**Interfaces:**
- Produces: `args` columns that name only flags the skills parse.

- [ ] **Step 1: Prove both flags are absent before removing them**

```bash
grep -rn -- '--skip-elaborate' skills/ | grep -v module-help.csv
grep -rn -- '--refresh-cache'  skills/ | grep -v module-help.csv
```
Expected: the first returns nothing; the second returns only `first-breath.md:55`. If either returns an implementation, **stop** — the flag is real and the finding is wrong.

- [ ] **Step 2: Confirm how `l3io-pm-plan` actually parses its argument**

Read `skills/l3io-pm-plan/SKILL.md`'s activation section. It recognises no argument, or an argument beginning `estimate`. There is no flag grammar at all.

- [ ] **Step 3: Empty both `args` cells**

`l3io-pm-plan,Plan` → `args` becomes empty. `l3io-sec-redteam` → `args` becomes empty.

- [ ] **Step 4: Remove the `--refresh-cache` sentence from `first-breath.md`**

Delete the clause offering the flag. Do not replace it with a different flag; there is no cache-refresh path.

- [ ] **Step 5: Verify and commit**

```bash
npm run check:docs && npm run check:module && npm run check:scripts && npm run check:manifest
git add skills/l3io-pm-setup/assets/module-help.csv skills/l3io-sec-redteam/assets/module-help.csv skills/l3io-sec-redteam/references/first-breath.md
```
Commit message must say both flags were advertised and implemented nowhere.

---

### Task 2: Correct `l3io-arch-review`'s fabricated args and wrong output location

**Files:**
- Modify: `skills/l3io-arch-review/assets/module-help.csv`

**Interfaces:**
- Consumes: Task 1's corrected CSV shape.
- Produces: an `args` value the skill parses, and an `output-location` matching where it writes.

- [ ] **Step 1: Establish what the skill actually accepts**

```bash
grep -rn -- '--stack' skills/l3io-arch-review/
sed -n '/Recognized\|On Activation/,/^##/p' skills/l3io-arch-review/SKILL.md
```
`--stack` appears only in the CSV. Record the real mode keywords from `SKILL.md`.

- [ ] **Step 2: Replace `args` with the real grammar**

Drop `[--stack …]` entirely. Keep the mode alternation only if `SKILL.md` parses those words; if it parses different words, use those.

- [ ] **Step 3: Fix `output-location`**

It currently says `implementation_artifacts`; Modes A and C write ADRs to `{project-root}/docs/adr/` and the docs skeleton to `/docs`.

**The column is more flexible than a bare config variable.** Verified against `bmm`'s own values: bare variable names (`implementation_artifacts`, `planning_artifacts`), `{var}`-interpolated paths (`{output_folder}/specs/spec-{slug}`), and plain prose (`repo root`) all appear. `bmad-help/SKILL.md:26-27` says the resolver expands variables in it, and `outputs` patterns are matched *at* the resolved path to infer completion.

So write the real location — an interpolated path is legitimate. If two locations genuinely apply, use the primary one and name the other in `outputs`, since completion detection reads `outputs` at `output-location`.

- [ ] **Step 4: Fix `phase`**

It says `2-planning`; the three l3io siblings say `planning` / `execution` / `anytime`. `2-planning` is `bmm`'s vocabulary. Pick one vocabulary for this package and use it — Task 5 makes the whole set consistent, so choose the value you will standardise on and note it for that task.

- [ ] **Step 5: Verify and commit**

```bash
npm run check:docs && npm run check:module
git add skills/l3io-arch-review/assets/module-help.csv
```

---

### Task 3: Correct the `l3io-pm` rows that misdescribe behaviour

Three separate defects in one file; they share a review surface.

**Files:**
- Modify: `skills/l3io-pm-setup/assets/module-help.csv`

**Interfaces:**
- Produces: `Estimate` and `Plan` rows whose metadata matches the skills.

- [ ] **Step 1: Prove the `Estimate` output-location is wrong**

```bash
grep -n 'plan snapshot\|must not touch' skills/l3io-pm-plan/SKILL.md
```
`SKILL.md` states estimate mode writes state and must not touch any plan snapshot. The row says `output-location: planning_artifacts`, so completion detection can never match.

- [ ] **Step 2: Set `Estimate`'s output-location to where estimate mode writes**

State lives under `{implementation_artifacts}/state/`. Use the column value that names it, matching how `Execute` expresses the same idea.

- [ ] **Step 3: Fix `Plan`'s `required` flag**

It is `false`, telling `bmad-help` the execution phase has no prerequisite. `l3io-pm-execute` reads `plan-output-meta.yaml` by name. Set `required: true` on the `Plan` row, and verify `Execute`'s `preceded-by` names `Plan`.

- [ ] **Step 4: Fix the `APM` menu code**

Every other `l3io-pm` code is `LP?` (`LPP`, `LPE`, `LPH`, `LPS`, `LPU`, `LPL`, `LPC`, `LPT`). `APM` shares no letter with "Estimate" and collides conceptually with `AR`. Use `LPM` if free, otherwise another free `LP?`. Check the whole package for collisions:

```bash
node -e "const {parse}=require('csv-parse/sync');const fs=require('fs');const c=[];for(const f of ['l3io-pm-setup','l3io-util-doctor','l3io-sec-redteam','l3io-arch-review'])for(const r of parse(fs.readFileSync('skills/'+f+'/assets/module-help.csv'),{columns:true}))if(r['menu-code'])c.push(r['menu-code']);console.log(c.sort().join(' '));const d=c.filter((x,i)=>c.indexOf(x)!==i);console.log('dupes:',d.length?d:'none')"
```

- [ ] **Step 5: Verify and commit**

```bash
npm run check:docs && npm run check:module
git add skills/l3io-pm-setup/assets/module-help.csv
```

---

### Task 4: Register `l3io-pm-help`'s two unlisted modes

**Files:**
- Modify: `skills/l3io-pm-setup/assets/module-help.csv`

**Interfaces:**
- Consumes: Task 3's menu-code audit command.
- Produces: rows for `progress` and `list plan`.

- [ ] **Step 1: Confirm the modes and their current routing**

```bash
grep -n 'progress\|list plan' skills/l3io-pm-help/SKILL.md | head
head -4 skills/l3io-pm-help/SKILL.md
```
`progress` is advertised in the skill's own frontmatter description and has no row. Note that `progress` **forwards to `/l3io-util-doctor stats`** — the row must describe what the user gets, and should not duplicate the doctor's own row.

- [ ] **Step 2: Add two rows**

One `Progress`, one `List Plan`, with free `LP?` menu codes, `action` matching the keyword the router recognises, and `output-location` empty (both are read-only).

- [ ] **Step 3: Set the relationship on `Progress`**

Because it forwards, its `followed-by` or description must make the forward visible rather than implying a second implementation exists.

- [ ] **Step 4: Verify and commit**

```bash
npm run check:docs && npm run check:module
git add skills/l3io-pm-setup/assets/module-help.csv
```

---

### Task 5: Register `l3io-util-doctor`'s advertised capabilities, and record the exclusion

The largest finding: 21 modes, 1 row. Neither 1 nor 21 is right.

**⚠ This is the one task where BMad's guidance and BMad's practice disagree, and the scope below is deliberately narrower than the assessment recommended.**

- **Guidance** — the module-builder workflow §3: *"Does every distinct capability of every skill have its own CSV row? A skill with multiple modes or actions should have multiple entries."* That argues for ~12 rows.
- **Practice** — measured in BMad 6.12.0: across `bmm` (16 skills) and `core` (8 skills), **exactly one skill registers more than one row** (`bmad-sprint-planning`, two). The overwhelming convention is one row per skill.
- **Mechanism** — multi-row *is* supported and documented: `bmad-help/SKILL.md:46` defines `skill-name:action` addressing for multi-action skills, and this package's own `l3io-pm-sync` already uses five rows.

Twelve rows for one skill would make `l3io-util-doctor` the most granularly registered skill in the ecosystem by a wide margin, in a menu shared with every other module. So this task registers **only the capabilities something already advertises and cannot route to** — the evidenced failures — and leaves the rest to the health check, which is what `SKILL.md` says sequences them.

**Files:**
- Modify: `skills/l3io-util-doctor/assets/module-help.csv`
- Modify: `skills/l3io-util-doctor/SKILL.md` (the keyword table gains an exclusion marker — see Step 3)

**Interfaces:**
- Produces: the row set Task 7's new rule derives its expectation from.

- [ ] **Step 1: Classify every keyword from the table in `SKILL.md`**

**The classifier is not "is it user-initiated" — it is "does the health check already propose it".** The doctor's design is one diagnosing entry point that detects findings and sequences remediation. A mode the health check proposes does not belong in a global menu: putting it there invites a user to run a migration or a repair *without* the diagnosis that decides whether they need it.

Measured — occurrences of each keyword in `steps/health-check.md`:

```
migrate-state 13 · backlog 11 · triage 9 · split-status 7 · layout-cleanup 6
migrate-adrs 6 · reconcile-status 5 · clean-legacy 5 · bootstrap-state 5
harvest-debt 5 · redrive 5 · rename-active 4 · rename-epic-dirs 4
migrate-schema 4 · sort-status 3 · update-ai-rules 2 · stats 2
normalize 0 · overlay 0 · check-deps 0
```

**Register — the health check never proposes these, because they answer a different question:**
- `check`/`status` — the default health check. **The entry point.** Everything with a non-zero count above is reached *through* it.
- `stats` — "how is the work going", not "is my state healthy". Named in the module's own `module_greeting` as a co-equal entry point.
- `check-deps` — "do my BMad skill dependencies resolve". Zero health-check mentions; `CLAUDE.md` tells users to run it.
- `overlay` — BMad customization overlays. Zero health-check mentions; nothing to do with project state.

**Do not register — the health check detects and sequences them.** Everything with a non-zero count. This includes `migrate-state`, despite `docs/upgrading.md` naming it: **13 mentions means the doctor already tells you when you need it**, and a menu entry would let a user migrate without the check that decides whether they should.

- `normalize` — **the routine-maintenance entry point.** Zero health-check mentions; the health check proposes its two constituents separately and never the shortcut. Its own file says *"Use for routine maintenance instead of running the two commands separately"*, and it works on a **fully-migrated** project: *"a fully-migrated project with no split files left still gets a useful naming check."* Nothing routes to the one command the docs tell you to use routinely.

**Do not register — not capabilities**: `help`/`?`, and `setup`/`configure`/`install`.

This lands at **five rows** — the four above plus `normalize` — and matches how the module already describes itself: *"Run /l3io-util-doctor for a project health check, or /l3io-util-doctor stats for the plan-aware progress dashboard."*

Re-derive the counts rather than trusting the block above, and re-read each `SKILL.md` note. **If a mode has zero health-check mentions and answers a question the health check does not ask, register it** — that is the rule; the four names are its current output.

- [ ] **Step 2: Write the rows**

One per Register keyword. Each description **action-oriented, starting with a verb**, one sentence, specific. Menu codes consistent with each other and colliding with nothing (use Task 3's audit command). `output-location` only where the mode writes; the read-only ones (`stats`, `backlog`, `check-deps`) leave it empty.

- [ ] **Step 3: Mark the exclusions in the keyword table**

Add a column or a consistent note marking each unregistered keyword as `health-check` or `legacy-only`. This is what makes Task 7's rule derivable without a hand-kept list in the checker.

- [ ] **Step 4: Shorten the default row's description**

It is ~370 characters carrying four mode summaries, because those modes had no rows. They have rows now. Cut it to one sentence about the health check.

- [ ] **Step 5: Verify and commit**

```bash
npm run check:docs && npm run check:module && npm run check:manifest
git add skills/l3io-util-doctor/assets/module-help.csv skills/l3io-util-doctor/SKILL.md
```

---

### Task 6: Cross-module consistency — `action`, `phase`, `_meta` rows and relationships

Four corrections that all span every CSV, so they share one review surface.

**Files:**
- Modify: all four `skills/*/assets/module-help.csv`

**Interfaces:**
- Consumes: the rows from Tasks 1–5.
- Produces: one `action` and `phase` vocabulary across the package, a `_meta` row per module, and `preceded-by`/`followed-by` on the cross-module wiring.

- [ ] **Step 0a: Fix `action: run`, which three skills do not recognise**

`l3io-util-doctor`, `l3io-sec-redteam` and `l3io-arch-review` all carry `action: run`. Check each skill's activation section: none parses the word `run` (the doctor reaches its default only by falling through its catch-all). BMad's convention for a default invocation is an **empty** `action` — confirm that against `src/core-skills/module-help.csv` and `src/bmm-skills/module-help.csv` in the unpacked `bmad-method` tarball at `/tmp/claude-1384001609/package/`, then apply whatever those files actually do.

- [ ] **Step 0b: Settle one `phase` vocabulary for the package**

Today: `anytime`, `planning`, `execution`, and one `2-planning`. **Verified against BMad 6.12.0:** `bmm` itself uses a mix (`anytime` ×4, `ship` ×5, `plan` ×6, `2-planning` ×2), and `bmad-help/SKILL.md:41` documents this explicitly — *"Skills group into folders (`plan`, `ship`; some modules use numbered phases) and flow in order; naming varies by module."*

So there is **no ecosystem vocabulary to match** and the bare forms are not wrong. The goal is internal consistency only: pick one form, apply it to all four files, drop the lone `2-planning`. Record in the commit message that per-module naming is documented as free.

- [ ] **Step 1: Copy BMad's own `_meta` shape**

BMad's format, from `src/bmm-skills/module-help.csv` line 2:

```
BMad Method,_meta,,,,,,,,,false,https://docs.bmad-method.org/,
```

`skill` is the literal `_meta`, `required` is `false`, `output-location` carries the module's docs URL, everything else empty. `bmad-help` uses these rows for module doc grounding, and all three BMad modules ship one; none of the four l3io modules does.

- [ ] **Step 2: Add one `_meta` row per module**

Point each at its own reference doc (`docs/l3io-pm-reference.md`, `docs/l3io-util-reference.md`, `docs/l3io-sec-reference.md`, `docs/l3io-arch-reference.md`) as a repository-relative path or published URL — match whichever form BMad's own rows use once you have looked at all three.

- [ ] **Step 3: Wire the documented relationships**

`CLAUDE.md` documents three that the CSVs do not express: the epic architecture gate (`l3io-pm-execute` → `l3io-arch-review`), the closure security review (`l3io-sec-redteam`), and `pm-help progress` → `doctor stats` (Task 4). Set `preceded-by`/`followed-by` for each. Do not invent relationships `CLAUDE.md` does not state.

**Use BMad's documented format**, from `bmad-help/SKILL.md:46`: `skill-name` for single-action skills, **`skill-name:action` for multi-action skills**. Several l3io skills are multi-action (`l3io-pm-sync` has five rows), so a relationship pointing at one of those must name the action, not just the skill. Verified against `bmm`, whose values are bare skill names because its skills are single-action.

Note also `bmad-help/SKILL.md:43`: sequencing is *"soft suggestions, not hard gates — see `required` for gating"*. So these columns advise ordering; Task 3's `required: true` is what actually gates.

- [ ] **Step 4: Verify and commit**

```bash
npm run check:docs && npm run check:module
git add skills/l3io-pm-setup/assets/module-help.csv skills/l3io-util-doctor/assets/module-help.csv skills/l3io-sec-redteam/assets/module-help.csv skills/l3io-arch-review/assets/module-help.csv
```

---

### Task 7: Add `check:module` rule 8 — registration matches the keyword table

Rule 3 of this repo's engineering rules: when you write a rule, write the check that enforces it in the same change. Everything above is a one-time correction; this is what stops it drifting again.

**Files:**
- Modify: `scripts/check-module.mjs` (new rule 8, `help-registration`)
- Modify: `scripts/tests/check-module.test.mjs`
- Modify: `CLAUDE.md` and `scripts/CLAUDE.md` if either states the rule count

**Interfaces:**
- Consumes: Task 5's exclusion markers in `SKILL.md`.
- Produces: rule 8; failure message names the unregistered keyword and its skill.

- [ ] **Step 1: Write the failing test first**

Add to `check-module.test.mjs`, following the shape of the existing `csv-skill-exists` tests:

```javascript
test("check:module rejects a keyword-table entry with no module-help.csv row", (t) => {
  const root = fixture(t);
  // append a new, unexcluded keyword row to the doctor's table
  write(root, "skills/l3io-util-doctor/SKILL.md",
    "\n| `brand-new-mode` | `steps/brand-new-mode.md` |  |\n", true);
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /brand-new-mode/);
});
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `node --test scripts/tests/check-module.test.mjs`
Expected: FAIL — no such rule exists yet.

- [ ] **Step 3: Implement rule 8**

Parse each skill's `SKILL.md` keyword table with a real parser, drop the entries Task 5 marked excluded, and require a `module-help.csv` row for every keyword that remains. **Derive the skill set by walking `skills/`** — never a hand-list. Parse the CSV with `csv-parse`.

- [ ] **Step 4: Confirm the test passes and the real tree is green**

Run: `node --test scripts/tests/check-module.test.mjs && npm run check:module`
Expected: both pass. If the real tree fails, Task 5's row set is incomplete — fix the rows, not the rule.

- [ ] **Step 5: Attack the rule's scope, not just its rule**

Add a test that a skill with **no** keyword table is handled without a false positive, and a test that removing every keyword table fails rather than passing vacuously — an empty expectation set that passes is the trap this project has hit repeatedly. Confirm each new test fails when the rule is neutered, then revert byte-identical.

- [ ] **Step 6: Verify and commit**

```bash
npm run check:module && npm run check:docs && npm run test:scripts
git add scripts/check-module.mjs scripts/tests/check-module.test.mjs
```

---

### Task 8: Record the agent-roster finding and guard the pair

`l3io-sec-redteam`'s roster says `code: redteam`; the skill directory is `l3io-sec-redteam`. BMad's module-builder workflow expects `code` to match a directory basename. **I checked the installer: it does not.** `manifest-generator.js:589`, `:597` and `:608` use `agent.code` only as the TOML section key `[agents.<code>]`, and `project-root.js` never mentions agents. So `redteam` is safe — but the choice is recorded nowhere and nothing enforces the roster/`customize.toml` agreement.

**Files:**
- Modify: `skills/l3io-sec-redteam/assets/module.yaml` (comment recording why `code` is short)
- Modify: `scripts/check-module.mjs` (new rule 9, `agent-roster`)
- Modify: `scripts/tests/check-module.test.mjs`

**Interfaces:**
- Consumes: Task 7's rule scaffolding.
- Produces: a check that every `agents[]` entry agrees with its skill's `customize.toml` `[agent]` block.

- [ ] **Step 1: Re-verify the installer claim before relying on it**

```bash
grep -n 'agent\.code\|agents\.\${' /tmp/claude-1384001609/package/tools/installer/core/manifest-generator.js
grep -n 'agent' /tmp/claude-1384001609/package/tools/installer/lib/project-root.js
```
Expected: `code` used only to build `[agents.<code>]`; no agent handling in `project-root.js`. If either shows a directory resolution, **stop** — `code` must then be renamed to `l3io-sec-redteam` and this task changes shape.

- [ ] **Step 2: Record the decision in `module.yaml`**

A short comment beside `code:` saying it is the TOML section key (`[agents.<code>]`), citing the installer line, and noting BMad's builder guidance expects a directory basename — so the deviation is deliberate and a reader does not "fix" it.

- [ ] **Step 3: Write the failing test**

A fixture where `module.yaml`'s roster `icon` differs from the skill's `customize.toml` `[agent] icon`. Expect exit 1 naming the field.

- [ ] **Step 4: Implement the check**

For every `agents[]` entry: `title`, `icon`, `description` non-empty; `name` present (empty string is valid); and each of `title`/`icon`/`description` equal to the `[agent]` block in `skills/<dir>/customize.toml`. Parse YAML with `yaml` and TOML with whatever the repo already uses — **do not hand-roll either**.

- [ ] **Step 5: Confirm green on the real tree**

The `l3io-sec-redteam` pair currently agrees on every field, so the real tree must pass. If it fails, the assessment was wrong — report rather than adjusting the check.

- [ ] **Step 6: Verify and commit**

```bash
npm run check:module && npm run test:scripts
git add skills/l3io-sec-redteam/assets/module.yaml scripts/check-module.mjs scripts/tests/check-module.test.mjs
```

---

### Deferred (not in this plan): grouping the doctor's command surface

Raised while reviewing Task 5 and **explicitly deferred** — recorded here so the analysis is not lost. The doctor exposes 21 top-level keywords, which is more than a user can hold in their head. The registration fix addresses the *symptom* (the menu) without touching the *surface* (the keywords).

Proposed verbs: **default/all · validate · migrate · cleanup · stats · harvest**.

Mapping, measured against the current keyword table:

| Verb | Members |
|---|---|
| default / all | `check`/`status` — already orchestrates everything below |
| validate | `check-deps`, `backlog`, `sort-status` |
| migrate | `migrate-state`, `migrate-schema`, `migrate-adrs`, `split-status`, `bootstrap-state`, `reconcile-status` |
| cleanup | `clean-legacy`, `layout-cleanup`, `rename-active`, `rename-epic-dirs` |
| *(spans verbs)* | `normalize` — routine maintenance; runs a `migrate`-family step and a `validate`-family step in one pass |
| stats | `stats` |
| harvest | `harvest-debt`, `triage` |
| **no home** | `overlay`, `redrive`, `update-ai-rules` |

`cleanup` earns its place: without it, `clean-legacy`, `layout-cleanup` and the two `rename-*` modes fall under `migrate`, where they do not belong — they tidy a *current* project rather than bring an old one forward. With it, 18 of 21 group cleanly.

The three with no home are not edge cases: `overlay` concerns BMad customization rather than project state, `redrive` rebuilds estimation calibration, `update-ai-rules` rewrites AI instruction files. Forcing them under a verb would be worse than leaving them top-level.

**Why deferred:** it is a breaking change. `CLAUDE.md`, `README.md` and `docs/upgrading.md` cite the current keywords, and `steps/health-check.md` proposes them by name — `migrate-state` alone appears there 13 times. The non-breaking middle path, if this is revisited, is to add the verbs as *dispatching* keywords that list their members and route, leaving every existing keyword working.

---

### Task 9: Re-run BMad's Step 3 against the result

The plan is only finished when the workflow that produced it passes.

**Files:** none — assessment only.

- [ ] **Step 1: Re-run the structural half**

```bash
for m in l3io-pm-setup l3io-util-doctor l3io-sec-redteam l3io-arch-review; do
  uv run .claude/skills/bmad-module-builder/scripts/validate-module.py "skills/$m"
done
```
Expected: unchanged — all pass. This is the half that could never see any of these defects.

- [ ] **Step 2: Re-run the quality half**

Work through `.claude/skills/bmad-module-builder/references/validate-module.md` §3 against the corrected CSVs: completeness, accuracy, description quality, ordering and relationships, menu codes, agent roster.

- [ ] **Step 3: Prove the installer sees the result**

```bash
mkdir -p /tmp/smoke-step3 && bash scripts/smoke-install.sh /tmp/smoke-step3
diff <(cat /tmp/smoke-step3/_bmad/l3io-util/module-help.csv) skills/l3io-util-doctor/assets/module-help.csv
```
Expected: `smoke: PASS`, and the diff empty — the authored rows are what a real install carries. **The repo's own `_bmad/` is a gitignored install artifact from 2026-09-14 and must not be used for this comparison; it predates most of this work.**

- [ ] **Step 4: Report, do not fix**

Any residual finding goes in the report for a decision, not into an unreviewed edit at the end of a plan.
