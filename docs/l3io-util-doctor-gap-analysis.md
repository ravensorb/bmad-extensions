# l3io-util-doctor — capability gap analysis

> **Assessment, measured 2026-09-23 at commit `47effcd`.** A point-in-time coverage review, not a
> contract. It records what the doctor detects, what it can fix, and what is invisible to it, each
> with file:line evidence at the time of measurement. Fixing any gap below makes the corresponding
> row stale — the live contracts remain `CLAUDE.md` and the skill's own `references/`.


Repo: `/home/ravenwolf.org/sanderson/source/git/ravensorb/bmad/bmad-extensions`, `main`, HEAD `47effcd`, clean.
No files were changed. Every claim below carries file:line evidence, re-derived from the tree at
this commit — the `/tmp/claude-1384001609/doctor-mode-audit.md` mode list was **not** used.

## 0. Current mode set, re-derived from `SKILL.md`

`skills/l3io-util-doctor/SKILL.md:74-91` is the dispatch table. Sixteen loadable targets:

| Keyword(s) | File | Kind |
|---|---|---|
| `help` / `?` | — (inline) | not a capability |
| `check` / `status` / *(default)* | `steps/health-check.md` | diagnose + repair |
| `stats` / `backlog` / `issues` | `steps/stats.md` | read-only |
| `check-deps` | `steps/check-deps.md` | read-only |
| `layout-cleanup` | `steps/layout-cleanup.md` | fix |
| `migrate-schema` | `steps/schema-migration.md` | legacy-only |
| `split-status` | `steps/split-status.md` | legacy-only |
| `harvest-debt` | `steps/harvest-debt.md` | fix |
| `reconcile-status` | `steps/reconcile-status.md` | legacy-only |
| `sort-status` | `steps/sort-status.md` | report-only |
| `redrive` | `steps/redrive.md` | fix |
| `triage` | `steps/triage.md` | fix |
| `migrate-adrs` | `steps/migrate-adrs.md` | fix |
| `update-ai-rules` | `steps/update-ai-rules.md` | fix |
| `clean-legacy` | `steps/clean-legacy.md` | fix |
| `migrate-state` | `steps/migrate-state.md` → `assets/migrate-state.md` | migration |
| `bootstrap-state` | `steps/bootstrap-state.md` | migration |
| `setup`/`configure`/`install` | `assets/module-setup.md` | not a capability |

Plus three inline actions with no file, run only by the health check
(`SKILL.md:95-98`, `steps/health-check.md:429-482`): `rename-active`, `rename-epic-dirs`,
`untrack-locks`.

The health check runs **19 checks** (`steps/health-check.md:16-319`) and an ordered 16-step
execution sequence (`:391-416`).

**Structural fact that shapes everything below:** `check-deps` has **zero** references in
`steps/health-check.md` (verified by grep — no match for `check-deps`, `bmad-deps`, or
`baseline` in that file). The default `/l3io-util-doctor` run never looks at BMad at all.

---

## 1. Coverage matrix

### A. Drift within a project's own files

| Failure mode | Detected? | Fixable? | Evidence |
|---|---|---|---|
| **State node vs story markdown disagree on status** | **No.** No check reads story frontmatter. The only frontmatter read in the whole skill is `bootstrap-state.md:65-90`, and only for *creating* a node. | **No** (`pm-status.py sync-story-doc` exists but is a write-path helper called after `set-status`; the doctor never calls it, never diffs) | grep for `frontmatter|sync-story-doc` across `steps/` + `assets/*.md` returns only `bootstrap-state.md:65` and `:261` |
| **State exists for a story whose artifact was deleted** (state-without-artifacts) | **Yes** — your guess was wrong. Check 11 diffs both directions; `<` lines = "state files with no story artifact" | **No** — explicitly report-only, "never auto-correct" | `health-check.md:144-166`, esp. `:159-165`; re-stated at `:484-487` |
| **Artifact exists, no state** (artifact-without-state) | **Yes**, twice: Check 2c and Check 11's `>` lines | **Yes** — `bootstrap-state` | `health-check.md:72-91`; `steps/bootstrap-state.md` |
| **`issues.yaml` references a story that no longer exists** | **Partly.** `audit-issues` 1b fires when a **`scheduled`** item points at a missing story, and when a story's `resolves:` names a key in neither file. A `backlog`-status item with a stale `story:` field is never evaluated. | Yes for the detected subset — `repair-issue --action unschedule`, driven by `triage` | `skills/_shared/pm-status.py:5755-5758` (the `if st == "scheduled":` guard at `:5754`), `:5766-5768`; wired at `health-check.md:212-235` |
| **`issues.yaml` references an epic that no longer exists** | **No.** `1e` validates the `next:` allocator per epic number but never checks that `E{nnn}` has a directory anywhere under `state/`. | No | `pm-status.py:5789-5813` — the loop is over `sorted(nxt, …)`, never over the state tree |
| **Calibration drifts from the actuals it was derived from** | **Narrowly.** Check 12 detects exactly one cause — a string `completion_evidence.fix_iterations` from a fixed defect. General drift (hand-edited file, deleted nodes, re-stated actuals) is undetected: the file "stores bare rounded ratios with no provenance recorded". | **Yes, and the fixer is broader than the detector** — `redrive` rebuilds `scope`+`fix` from the nodes unconditionally. But `closure`, `orchestration` and `token_mix` have **no rebuild path at all**. | `health-check.md:168-210`; `steps/redrive.md:14-45`; `pm-status.py:2186-2210` |
| **Artifact tree and state tree disagree on which epics exist** | **Partly.** Check 11 iterates *from the state side*, per sprint dir — an artifact epic directory with no state epic is never visited. It is caught only if it contains `sprint-*/stories/E*.md` (then Check 2c fires). An artifact epic holding only `closure/`, `tests/` or `epic-closure/` is invisible. | Partly (`bootstrap-state` for the story case) | `health-check.md:147` — the loop is "for each sprint directory under `{pm_state_root}/…`" |
| **`completion_evidence` claims tests that never ran** | **No.** `set-field` refuses `tests_passing` and `add-test-run` derives it, so it cannot be *newly* forged — but a node migrated from a legacy layout keeps whatever it had, and `migrate-schema` is explicitly instructed to "preserve it as-is … never touch or retype it". Nothing later audits a `tests_passing: true` with empty `test_runs`. | No | `steps/schema-migration.md:16` and `:58` |
| **Placement: epic directory whose folder ≠ its status** | **Yes, but not by the health check.** `pm-status.py report` emits a `placement` flag, which `stats` surfaces. The 19 checks have no placement check. | **No fixer is wired.** The repair is `move-epic`; no mode calls it, and `stats` is read-only. | `pm-status.py:3376-3393`; `steps/stats.md:84-85`, `:115` |
| **`{pm_state_root}` is gitignored** | **No** in the health check. `migrate-state` Stage E1 checks it, pm-execute activation and pm-help check it — the doctor's own `bootstrap-state` creates a state tree and never checks it. | n/a | grep `check-ignore` in `health-check.md` → no match; present at `assets/migrate-state.md:560-575`, `skills/l3io-pm-help/steps/step-03-read-state.md:20`, `skills/_shared/steps/shared/step-00-activate.md:234` |
| **`implementation_artifacts` repointed, real state orphaned elsewhere** | **No** in the health check. `stats` and `l3io-pm-help` both BLOCK on it; the health check's Check 2b treats "none present" as "new project → ✓". | n/a | `steps/stats.md:49-60` vs `health-check.md:58` |
| **Tracked `*.lock` files** | Yes (Check 14) | Yes (`untrack-locks`, inline) | `health-check.md:237-258`, `:464-482` |
| **Backlog rot (fixed/obsolete/duplicate items)** | Yes (Check 13 + `audit-backlog.py`) | Yes (`triage`) | `health-check.md:212-235` |
| **ADRs in the old home / register lagging** | Yes (Check 15) | `migrate-adrs` (moves); register lag is report-only and self-corrects | `health-check.md:260-272` |
| **Broken spec pointers / unlinked ADRs / stale spec index** | Yes (Checks 16, 17, 19) | Report-only for all three | `health-check.md:274-296`, `:310-319` |
| **Unconfirmed spec changes built upon** | Yes (Check 18) | `triage` | `health-check.md:298-308` |
| **Stale `pm-calibration.yaml.pre-redrive` backup** | **No.** Check 9 and `clean-legacy` CL1 enumerate `.yaml.legacy`, `*.yaml.v1`, `state.legacy/`, `migration-backup/`. `redrive` — a doctor mode — writes `.pre-redrive` and nothing sweeps it. | No | `health-check.md:128-131`; `steps/clean-legacy.md:14-38`; writer at `pm-status.py:2209` |

### B. Upgrades from base BMad

**The load-bearing fact, verified against the real 6.12.0 install in this checkout
(`_bmad/_config/manifest.yaml:2` → `version: 6.12.0`):**

BMad's own `sprint-status.yaml` and this package's "legacy flat `sprint-status.yaml`" are
**two different file formats at the same path**, and nothing in the package knows it.

- BMad 6.12 schema — `.claude/skills/bmad-sprint-planning/sprint-status-template.yaml:53-66`:
  a flat `development_status:` **mapping** (`epic-1: backlog`, `1-1-user-authentication: done`,
  `epic-1-retrospective: optional`), plus `action_items:`, `story_location:`, `project_key:`.
  Written to `{implementation_artifacts}/sprint-status.yaml`
  (`.claude/skills/bmad-sprint-planning/SKILL.md:46`).
- l3io's legacy flat schema — an `epics:` **list** with nested `sprints:` → `stories:`, nodes
  carrying `id:` (`steps/schema-migration.md:45-60`, `assets/migrate-state.md:182-200`).
- `grep -rn "development_status" skills/ docs/ scripts/ README.md` → **zero hits.**

| Failure mode | Detected? | Fixable? | Evidence |
|---|---|---|---|
| **Project with BMad's own `sprint-status.yaml`, never l3io's** | **Mis-detected as l3io legacy flat.** Check 2 reads it as "a `sprint-status.yaml` with done or backlog epics" → flags `split-status`. Check 2b sees exactly one legacy layout → flags `migrate-state` High. Nothing inspects the schema. | **No — and the prescribed fix is destructive.** `migrate-state` Stage A loads "all `epics:` lists found" (`assets/migrate-state.md:170`) → there is no `epics:` key → the working epic list is **empty**. Stage B writes nothing. Stage E's four gates pass **vacuously** (E2 is "for every epic key produced in Stage B" — zero; E3 and E4 iterate empty sets) (`:694-717`). Stage F then `rm -f`s the original (`:721-742`). Net: BMad's live tracking file is removed (a `.legacy` copy survives), `bmad-build`'s sync stops (it writes only when the file exists), `bmad-sprint-planning` and `bmad-retrospective` lose their input, and the report says "migration complete". | as cited |
| **Flat + sharded collision** (`bmad-build` writing alongside l3io) | Yes — `detect-layout.py`, Critical | The remedy Check 2b prints is *exactly* the vacuous-destructive path above, because the colliding flat file is by construction the **BMad-schema** one — Check 2b's own rationale says so (`health-check.md:37-39` cites `bmad-build`'s `step-03-implement.md:27`) | `health-check.md:43-53`; `scripts/detect-layout.py:45-50` |
| **Project that used `bmad-create-story`/`bmad-dev-story`, artifacts but no l3io state** | **Partly.** BMad 6.12 writes stories **flat** into `{implementation_artifacts}` (`--stories-dir {implementation_artifacts}`, `.claude/skills/bmad-sprint-planning/references/generate-tracking.md:12`) with names like `1-1-user-authentication.md`. Check 2c only globs `epic-*/sprint-*/stories/E*.md` (`health-check.md:79`) — it sees none. Check 4 / `layout-cleanup` heuristic 1 (`^([0-9]+)-[0-9]+.*\.md$`, `steps/layout-cleanup.md:44`) **does** match them. | **The chain does not close.** Heuristic 1's destination is `epic-{nnn}/sprint-{nn}/stories/{story-key}.md` but `{story-key}` is never defined for a BMad filename, and no step says to rename `1-1-user-authentication.md` → `E001-S01-001.md`. If the name is preserved, `bootstrap-state`'s `find -name 'E*.md'` (`bootstrap-state.md:21`) never matches it and the story stays stateless. Sprint is also defaulted to `01` with no mapping prompt. | as cited |
| **First `/l3io-util-doctor` run in such a project** | It **detects** (flags `split-status` + `migrate-state`, possibly `layout-cleanup`) and **proposes**. HC5 asks once, HC6 runs the whole sequence. It does not fail loudly. | The sequence rule at `health-check.md:363-367` forbids ending before `migrate-state`, so the destructive step is *guaranteed* to run once `split-status` is flagged. | as cited |
| **The story `.md` frontmatter BMad writes** | `bootstrap-state` reads `title`/`status`/`classification` with defaults (`bootstrap-state.md:83-85`). BMad's story files are not guaranteed to carry `classification`; the default `standard` is silently assumed. | n/a — acceptable | as cited |

### C. Upgrades from earlier versions of this package

| Layout / schema | Path to current | Complete? | Tested? |
|---|---|---|---|
| **Legacy flat** `sprint-status.yaml` (l3io schema) | `migrate-schema` → `split-status` → `reconcile-status` → `migrate-state` Stage A | Yes, end to end, with `id:`→`key:` conversion, status normalization (`deferred`/`superseded` → issues), backups, a four-gate verify and an explicit disposal prompt | **No automated test.** All four are prose step files. `scripts/tests/` holds only `test-audit-backlog.py`, `test-bmad-deps.py`, `test-detect-layout.py`; `skills/_shared/tests/` holds only script suites. The 337 tests never execute a migration. |
| **Legacy per-epic** `_bmad/state/` | `migrate-state` "Loading the working lists" path (`assets/migrate-state.md:213-232`) | Yes — **except the known dedupe defect**: "Concatenate the `epics:` list from every `active/E{nnn}-status.yaml` file, from `sprint-status-planned.yaml`, and from `sprint-status-archived.yaml` into one working epic list" (`:223-226`). No dedupe, no merge rule. An epic shell in `planned` plus the full epic in `active` yields **two nodes with the same key**; Stage B writes them to two different status folders, or one silently wins. **The same defect exists on the legacy-flat path** (`:170` — "Load all `epics:` lists found across whichever files are present"), which is not mentioned in the filed issue. | No |
| **Split three-file** `sprint-status{,-backlog,-archived}.yaml` | Consumed directly by `migrate-state` Stage A; `reconcile-status` cleans it first | Yes | No |
| **`sprint-status-active.yaml`** (pre-1.0.20) | Check 1 → inline `rename-active` with a conflict guard and a YAML re-parse rollback | Yes | No |
| **Two-digit `epic-{nn}/` artifact dirs** | Check 10 → inline `rename-epic-dirs`, conflict-skipping | Yes | No |
| **`pm-calibration.yaml` v1 → v2** | Automatic inside `pm-status.py` on first sample append; backup `.v1` swept by `clean-legacy` | Yes | Yes (`skills/_shared/tests/test-pm-status.py`) |
| **Other schema versions** | **There are none.** `CALIBRATION_SCHEMA_VERSION = 2` (`pm-status.py:935`) is the only versioned artifact. `issues.yaml`, `issues-resolved.yaml`, `events.jsonl`, `adr-register.yaml`, the spec index and every node file are **unversioned**. A future node-schema change has no marker to migrate *from* — the next migration will have to sniff shape. | Structural, not yet a live defect | n/a |
| **Config written before `_bmad/custom/` was the layer** | `references/config-resolution.md:27-31` states there is no `_bmad/config.yaml` and that per-module `_bmad/{code}/config.yaml` files "are ignored". `merge-config.py` exists precisely because bmb v2.2.2's scaffolder writes YAML (`scripts/merge-config.py:9-19`). **But no check detects a project that actually has one of those files**, so an l3io setting stranded in `_bmad/config.yaml` or `_bmad/l3io-pm/config.yaml` resolves as absent and every path falls back to a default, silently. | Not detected, not fixable | as cited |
| **Removed keyword a user's script still calls** (`normalize`, `overlay`, the `l3io-util-cleanup` forwarder, `rename-active`, `rename-epic-dirs`) | **Silently mis-dispatched.** `SKILL.md:93-94`: "Everything else (no argument, **unrecognized text**, or a natural-language description) → load `steps/health-check.md`." invoking the doctor with the removed `normalize` argument runs a full health check and proposes writes, with no notice that the keyword is gone. The mapping table exists only in `docs/upgrading.md:122-129`, which the runtime never reads. | Documented, not enforced | as cited |

### D. BMad core moving underneath

| Failure mode | Detected? | Fixable? | Evidence |
|---|---|---|---|
| **Core upgraded 6.11 → 6.12 while the project stays put** | **Only if the user types `check-deps`.** Nothing in the 19 checks looks at `_bmad/_config/manifest.yaml`. | n/a | grep: `check-deps` appears 0 times in `health-check.md` |
| **What `bmad-baseline.json` gates** | **Nothing.** `compute_baseline_drift` produces `baseline_drift`, and the module docstring says explicitly: "This is a WARNING, never a failure … It never changes the exit code, including under `--strict`." | n/a | `scripts/bmad-deps.py:64-72`, `:246-352` |
| **What happens when core moves past it** | One `BASELINE core_version drift: pinned '6.12.0', installed '6.13.0'` line inside `check-deps` output — and **`steps/check-deps.md` never tells the agent to interpret it.** Its report list (`:9-20`) covers exit 0 / absent / shim / 3 / 4 / 2 only; `CONTRADICTION` and `BASELINE` lines fall under "Print the output as-is" and get no verdict, no severity, no remedy. | No | `scripts/bmad-deps.py:334-336`; `steps/check-deps.md:6-21` |
| **A dispatched BMad skill renamed or removed upstream** | Yes, **at runtime only**, via `check-deps` → exit 3 BLOCKED for a required skill, a warning line for an optional one. Both install layouts (`skills/<n>/SKILL.md` and `commands/<n>.md`) and both roots (project, `~`) are probed. `status_contradictions` cross-checks the hand-kept inventory against `_bmad/_config/skill-manifest.csv`. | Not fixable by the doctor (it prints `npx bmad-method install --modules bmm`) | `scripts/bmad-deps.py:95-113`, `:184-204`, `:340-350` |
| **A step file probing the wrong path** (`.claude/commands/<n>.md` only) | Runtime only, by `check-deps`. `CLAUDE.md` already records that **no `check:docs` check verifies probe paths.** | n/a | confirmed unchanged |
| **A partial or corrupted skill install in a consumer project** | **No.** Each skill ships a generated `payload-manifest.json` whose stated purpose is "a consumer who installed one skill can verify that skill alone", but the only consumer of it is `scripts/write-payload-manifest.mjs --check`, run as `check:manifest` **in this repo's CI**. No doctor mode verifies it in a target project. `pm-status.py` self-heals by content hash; nothing else does. | No | `package.json:14`; `scripts/write-payload-manifest.mjs:16-17` |

---

## 2. The three direct answers

### Do we have gaps?

Yes. Ranked by likelihood × damage:

1. **The doctor cannot tell BMad's `sprint-status.yaml` from l3io's, and the mis-identification
   leads to a destructive no-op.** Highest likelihood (it is the *normal* state of any project
   that ran `bmad-sprint-planning` or `bmad-build` — which `check-deps` lists as a **required**
   dependency), highest damage (removes a live tracking file that three required BMad skills
   read, while reporting success), and it is reached through the health check's own Critical
   remedy, so a user who does exactly what the tool says hits it.

2. **The default run is blind to BMad entirely.** `check-deps` is a separate keyword nobody is
   prompted to type. `/l3io-util-doctor` after a BMad upgrade that removed a required skill
   prints "✓ Project is healthy — no actions needed", and the first symptom is a gate that
   self-skips during an epic run — the exact failure `bmad-deps.py`'s own docstring says it
   exists to prevent.

3. **Vacuous passes.** Three distinct conditions make the whole health check report green over a
   project it never actually read: `implementation_artifacts` repointed (`stats` BLOCKs here,
   the health check does not), a gitignored `state/` (pm-execute BLOCKs, the health check does
   not), and `migrate-state`'s empty-working-list path. The pattern is the same each time — a
   scope the check derives from a path it assumes is right.

4. **Status drift between a story `.md` and its state node is completely invisible.** These are
   the two halves of the same story, `sync-story-doc` keeps them aligned on the write path, and
   nothing ever re-checks. A hand-edited markdown, a failed `sync-story-doc` (which "warns on
   stderr and returns 0" by design), or a story resurrected from git all produce a silent
   disagreement that `stats` will render confidently.

5. **The per-epic concatenation defect, on both source paths.** Already filed for the per-epic
   path; the legacy-flat path at `assets/migrate-state.md:170` has the same shape and is not in
   the filed issue.

6. **Removed keywords silently become a health check.** Low damage (the health check confirms
   before writing) but it is a guaranteed-surprise class: the user asked for X and got Y.

7. **No migration is covered by a test.** 337 tests, none of which run a migration — they test
   `pm-status.py`, `spec-align.py`, `audit-backlog.py`, `bmad-deps.py`, `detect-layout.py`,
   `write-module-config.py`, `merge-*`. Every migration is prose. This is not itself a gap in
   capability; it is why the gaps above went unnoticed.

8. **`bmad-baseline.json` gates nothing** and `check-deps.md` gives its output no verdict. The
   pin is documentation that happens to be machine-readable.

9. **Minor, real, cheap:** `.pre-redrive` never swept; `closure`/`orchestration` calibration
   components have no rebuild path; `issues.yaml` referencing a vanished epic is undetected;
   `tests_passing: true` with no `test_runs` survives migration unchallenged; no consumer-side
   `payload-manifest.json` verification.

### Can we handle drift in our files?

**Partly — the state tree is well covered, the state↔artifact seam is half covered, and the
state↔markdown seam is not covered at all.**

- **Detected and fixable:** backlog integrity and rot (13 → `triage`), ADR home (15 →
  `migrate-adrs`), tracked locks (14 → `untrack-locks`), two-digit epic dirs (10 →
  `rename-epic-dirs`), naming (5 → `sort-status`, report-only by design since the sharded layout
  cannot mis-sort), unconfirmed spec changes (18 → `triage`), the one calibration poisoning
  cause (12 → `redrive`), deferred markers (6 → `harvest-debt`), stale AI rules (7 →
  `update-ai-rules`), backup litter (9 → `clean-legacy`).
- **Detected, deliberately not fixable:** state↔artifact orphans in both directions (11), broken
  spec pointers (16), unlinked ADRs (17), stale spec index (19). The "report only, a human
  decides" call is correct for 11 — a dropped artifact and an abandoned node genuinely look
  identical — and 16/17/19 self-heal on the next run. This is the right shape.
- **Detected but nowhere near the fixer:** epic placement. `pm-status.py` flags it, `stats`
  prints it, the health check never asks, and `move-epic` (the actual repair) is called by no
  mode. A placement anomaly is the one state defect that makes `git mv`-based history and every
  status-folder query wrong at once.
- **Invisible:** status disagreement between node and markdown; `issues.yaml` → dead epic;
  forged `tests_passing`; general calibration drift; artifact epics with no stories and no
  state; a gitignored or orphaned state root.

### Can we handle upgrades from base BMad and earlier versions?

**From earlier versions of this package: yes, every declared path is complete** — pre-1.0.20
`sprint-status-active.yaml`, 1.x flat, the three-file split, 2.0.0 per-epic `_bmad/state/`,
two-digit epic dirs, calibration v1→v2. The sequencing (`health-check.md:391-416`), the
never-end-before-`migrate-state` rule (`:363-367`), the four-gate Stage E and the
backup-before-delete ordering in Stage F are genuinely careful work. Two qualifications: the
duplicate-key concatenation on **both** source paths, and the complete absence of test coverage
for any of it.

**From base BMad: no. That path dead-ends, and one of its branches is destructive.**

- ✅ Works: `l3io` state absent, artifacts already in `epic-*/sprint-*/stories/E*.md` form →
  Check 2c → `bootstrap-state`. This is the only clean base-BMad on-ramp, and it assumes the
  artifacts are already in l3io's layout and naming, which base BMad does not produce.
- ⚠️ Incomplete: BMad's flat story files → Check 4 → `layout-cleanup` moves them but never
  defines the destination story key, so `bootstrap-state` cannot pick them up.
- ❌ Destructive: BMad's `sprint-status.yaml` → Check 2/2b → `split-status` + `migrate-state` →
  zero epics migrated, all four verify gates vacuously green, original file deleted.

**From BMad core moving underneath: only if the user knows to type `check-deps`.** The
mechanism is good — dual-layout probing, dual roots, fallback names, manifest cross-check — and
it is not wired into the entry point that the docs call the post-upgrade step
(`docs/upgrading.md:14-19`).

---

## 3. Gaps ranked by what I would actually close

Each with the failure it prevents. Assessment only — nothing here is a plan.

1. **Discriminate `sprint-status.yaml` by schema before any status-file action.**
   *Prevents:* deleting a live BMad tracking file that `bmad-sprint-planning`,
   `bmad-build` and `bmad-retrospective` all read, while reporting a successful migration.
   The discriminator is one key: `development_status:` (mapping) = BMad's, `epics:` (list) =
   l3io's. It belongs beside `detect-layout.py`, which already owns this decision and is already
   unit-tested — the right shape is a second exit code from that script, not a new step-file
   snippet. **Worth covering: unambiguously.** This is the most likely real-world state of a
   target project.

2. **Make `migrate-state` refuse to complete a migration that moved nothing.**
   *Prevents:* the vacuous Stage E → destructive Stage F chain, for this cause and every future
   one. A gate of the form "Stage B produced zero epics and the source was non-empty → BLOCK"
   is independent of *why* the parse failed, which is what makes it worth more than fixing
   cause #1 alone. **Worth covering: yes** — it is the general form of the specific bug.

3. **Run `check-deps` as a check inside the health check.**
   *Prevents:* a required BMad skill disappearing under a project and surfacing as a silently
   self-skipped gate mid-epic. Exit 3 is already a clean Critical signal; `baseline_drift` is
   already a clean informational one. **Worth covering: yes, and it is nearly free** — the
   script, the inventory and the mode file all exist; only the wiring is missing. It also gives
   `bmad-baseline.json` its first actual consumer.

4. **Add the two vacuous-pass guards the health check is missing but its siblings have.**
   *Prevents:* "✓ Project is healthy" printed over a project whose state is orphaned by a
   repointed `implementation_artifacts`, or is on disk but gitignored and therefore about to be
   lost. Both probes already exist verbatim in `steps/stats.md:49-60` and
   `assets/migrate-state.md:560-575`; the health check is the one place they are absent, and it
   is the place users are told to run. **Worth covering: yes** — and per `CLAUDE.md` §3 the
   duplication these create should be resolved by one shared source, not a fourth copy (there
   are already three copies of layout detection, each with a comment asking the next person to
   keep them in sync).

5. **Dedupe the working epic list on both source paths in `migrate-state`.**
   *Prevents:* an epic shell and its full epic merging into two nodes with one key, landing in
   two status folders. Already filed for the per-epic path; **the legacy-flat path at `:170`
   has the same defect and is not in the filed issue.** Worth covering: yes, and the fix should
   be one rule applied where the lists are joined, not two.

6. **A status-drift check between story `.md` frontmatter and its state node.**
   *Prevents:* `stats` and every plan-aware view rendering a confident tree over a story whose
   two halves disagree — the failure mode `sync-story-doc`'s deliberate warn-and-return-0 leaves
   behind by design. Detection is cheap (Check 11 already opens both sides); the repair is not
   mechanical (which side is right is a judgment), so this should be **report-only, like Check
   11**. Worth covering: yes, as a check — not as a fixer.

7. **Surface epic placement in the health check and wire `move-epic` to it.**
   *Prevents:* an epic whose folder and status disagree staying wrong indefinitely. `pm-status.py`
   already computes the flag and `move-epic` already performs the repair; only the doctor never
   asks. Worth covering: yes — this is a mode-shaped hole with both ends already built.

8. **Reject removed keywords by name instead of falling through to the health check.**
   *Prevents:* the doctor silently running something else when invoked with the removed `normalize` argument, instead of something else and proposing
   writes the user did not ask for. The replacement table already exists in
   `docs/upgrading.md:122-129`; per `CLAUDE.md` §3 it should live where the dispatch happens,
   with `check:module` rule 9's mechanism extended to cover it. Worth covering: yes, cheap.

9. **Finish the base-BMad story on-ramp, or state plainly that it does not exist.**
   *Prevents:* a user following `layout-cleanup` → `bootstrap-state` and ending with moved files
   and still no state. Either define the `{story-key}` derivation for a BMad-named story file
   (and prompt for the epic/sprint mapping instead of defaulting sprint to `01`), or say in
   `SKILL.md` that base-BMad story artifacts must be renamed by hand first. **Worth covering:
   yes — but the honest "not supported" is worth nearly as much as the code**, and costs a
   paragraph.

10. **Sweep `.pre-redrive`, and give `closure`/`orchestration` a rebuild path.**
    *Prevents:* a backup accumulating forever from the doctor's own mode, and a calibration
    component that can be wrong with no way to repair it short of hand-editing. Both small.
    Worth covering: the `.pre-redrive` sweep yes (it is a one-line scope fix in a scan that
    already enumerates three other suffixes — and the enumeration itself is the CLAUDE.md §4
    smell); the rebuild path only if `closure` drift is ever actually observed.

**Not worth covering, in my judgment:**

- `issues.yaml` naming a vanished epic — an epic directory is removed only by a deliberate
  `git rm`, and the orphan is harmless: `list-issues` still returns it and `triage` still
  reviews it. Cost exceeds benefit.
- Consumer-side `payload-manifest.json` verification — `pm-status.py` (the file where a partial
  install actually hurts) already self-heals by content hash, and the installer is not known to
  produce partial installs. Build it if one is ever seen, not before.
- Versioning the node schema — real, but it is a cost you pay at the *next* schema change, and
  the memory note "no unapproved version bumps" says that change is not being made. Revisit when
  a node-schema change is actually on the table.
- A general calibration-vs-nodes drift detector — `redrive` is idempotent, cheap and safe to run
  blind, so a detector buys less than simply running the fixer. The current Check 12 → `redrive`
  wiring is the wrong shape (a narrow detector gating a broad fixer), but the cheap correction
  is to widen when `redrive` is *offered*, not to build a new detector.
