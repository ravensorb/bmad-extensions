# l3io as a Customization Layer over BMad — Design

**Date:** 2026-09-20
**Status:** proposed
**Supersedes approach in:** `2026-09-12-bmad-v612-migration-design.md` (Option A — "own the dev step")
**Amends:** ADR-0006
**Implies:** ADR-0008 (module packaging shape — written, accepted 2026-09-22),
ADR-0009 (l3io capabilities as BMad lenses — not yet written)

> **Renumbered 2026-09-22.** These two were written here as ADR-0007 and ADR-0008. ADR-0007 was
> then taken by an unrelated decision (`0007-ci-installs-npm-dependencies.md`), whose number was
> hand-picked from the highest file on disk rather than allocated. Nothing detected the clash:
> `pm-status.py adr-reserve` allocates against the register and the files in `docs/adr/`, and
> neither knows what a design document has promised. **A reservation that lives only in prose is
> not a reservation** — so "ADR-0009" above is an intent, not an allocation, and whoever writes
> it must take its real number from `adr-reserve` at that time.

## 1. Problem

The package's stated goal is twofold:

1. **Replace** BMad's default artifacts — stories, issues, sprint planning — with a more
   sophisticated set, such that *BMad's own skills use the replacements*.
2. **Extend** with a more robust plan-and-execute methodology that keeps agents and subagents
   on track by validating against spec and stories.

Neither is achieved today, and the current strategy works against both.

### 1.1 The fallback model does the opposite of "replace"

`steps/sprint/step-02-story-prep.md` and `steps/sprint/step-03-dev-loop.md` probe for
`bmad-create-story` / `bmad-dev-story` and *prefer them when present*, falling back to the
in-package `l3io-story-enrich` / `l3io-dev-implement` only when absent.

BMad 6.12.0 ships both skills (`_bmad/_config/skill-manifest.csv`). On every stock install the
probe hits, the legacy path always wins, and the in-package replacements never run. The package
does not replace BMad's story handling — it defers to it.

What it defers to is frozen: both carry `metadata: lifecycle: shim` and a description reading
"Deprecated: `bmad-build` is now the official implementation method", while retaining their full
23.7 KB / 26.9 KB bodies. They work, and they will not improve.

### 1.2 The inventory drifted from its own ADR

ADR-0006 states correctly that these skills "were **deprecated to shims**". The inventory it
governs encodes them as `"status": "removed"`. Three of six `removed` entries are wrong:

| Skill | Inventory | 6.12.0 manifest | Verdict |
|---|---|---|---|
| `bmad-create-story` | removed | **ships** | wrong |
| `bmad-dev-story` | removed | **ships** | wrong |
| `bmad-review-adversarial-general` | removed | **ships** | wrong |
| `bmad-check-implementation-readiness` | removed | absent | correct |
| `bmad-ux-review` | removed | absent | correct |
| `bmad-architect` | removed | absent | correct |

`steps/sprint/step-03-dev-loop.md:73` repeats the error: "The legacy `bmad-dev-story` skill is
gone from BMad ≥6.12.0." It is not gone.

Neither guard catches it:

- **`check:docs` check 17** accepts an `ls .claude/` probe, or the word `legacy`, as evidence a
  mention is historical. The affected directives carry both. It guards *names*, not
  *preference*. `npm run check:docs` passes.
- **`bmad-deps.py`** compares the inventory against files on disk, never against
  `skill-manifest.csv`. It cannot detect that `removed` is false.

This is the failure the global rules name: *derive the scope from the source of truth, never
enumerate it by hand.* The source of truth is installed and machine-readable; nothing reads it.

### 1.3 `bmad-build` is unknown to the package

Zero references under `skills/`, zero inventory entries. It is BMad's official implementation
path and a five-step pipeline — `clarify-and-route → plan → implement → review → present` —
with parallel review layers, `compile-epic-context.md` and `sync-sprint-status.md`.

### 1.4 One artifact tree, two incompatible writers

`modules.l3io-pm.implementation_artifacts` is **absent**, and that is **by design, not drift**.
`skills/_shared/module-setup.md` and `references/config-resolution.md` §5 both record it:
*"None of the l3io modules declare required settings, so a correct install has no section at
all — treating its absence as a first-run made every invocation detour into setup."* No l3io
`module.yaml` declares a `variables:` block, so setup runs and correctly writes nothing.

The consequence is still real: l3io falls back to its documented default
`{output_folder}/implementation-artifacts` (`config-resolution.md:65`), which coincides
exactly with `modules.bmm.implementation_artifacts`. Two systems write one directory in two
layouts: `bmad-build` writes flat `sprint-status.yaml`, l3io writes sharded
`state/{planned,active,archived}/epic-NNN/`. The default is documented; what is undocumented is that it **collides with bmm's configured
value**. The fix is therefore not to declare a config variable — that would give setup
something to collect and make absence meaningful again, re-creating the detour the recorded
decision removed — but to **detect the collision** where it does damage.

**Mitigating:** the collision is conditional. `step-03-implement.md:27` gates the write on
`sprint-status.yaml` already existing, so in a migrated project `bmad-build` self-skips. The
real risk is **silent divergence where both layouts co-exist**.

### 1.5 The package is not a valid BMad module

```
$ uv run validate-module.py skills/
{"status": "fail", "findings": [{"severity": "critical", "category": "structure",
  "message": "No setup skill found (*-setup directory) and no standalone module detected"}]}
```

Standalone detection (`validate-module.py:61`) requires `SKILL.md` **and**
`assets/module.yaml`; the package ships `module.yaml` at the skill root.

| Documented requirement | Shipped | Status |
|---|---|---|
| `assets/module.yaml` | `module.yaml` at skill root | wrong path |
| `assets/module-setup.md` | present | ok |
| `assets/module-help.csv` | present | ok |
| `scripts/merge-config.py` *or* `merge_config.py` | `write-module-config.py` | wrong name |
| `scripts/merge-help-csv.py` *or* `merge_help_csv.py` | absent | missing |
| multi-skill: a `*-setup` directory | none | absent |

Embedded setup is asserted in CLAUDE.md but recorded in no ADR (0001–0006 checked).

**Correction on record:** an earlier reading of this work claimed the current embedded model
*is* the documented standalone pattern. It is not. The docs treat the choice as binary — one
skill self-registers, or several delegate to a setup skill. Several skills each self-registering
under a **shared** module code is not a documented shape. `check:docs` check 16 (sibling
`module.yaml` files sharing a `code:`, "the installer picks one and which one is not defined")
exists to manage an arrangement the docs do not describe.

## 2. Constraint: bmb's module contract is unsafe for a core-integrated module

BMad Builder v2.2.2 and core 6.12.0 disagree about where configuration lives.

**Core** — `config_utils.load_central_config` reads **TOML only**:
`_bmad/config.toml → config.user.toml → custom/config.toml → custom/config.user.toml`.

**bmb's `setup-skill-template/scripts/merge-config.py`** writes `_bmad/config.yaml` and
`_bmad/config.user.yaml`, and **deletes** `{legacy-dir}/core/config.yaml` and
`{legacy-dir}/{module-code}/config.yaml` after merging.

Adopting the template verbatim would:

1. Write `_bmad/config.yaml`, which does not exist in a core 6.12 install and is never read by
   `resolve_config.py` — making every l3io setting invisible.
2. Delete `_bmad/core/config.yaml` and `_bmad/l3io-pm/config.yaml`, which do exist here.
3. Target `_bmad/module-help.csv` for help, when the real file is `_bmad/_config/bmad-help.csv`.

This vindicates CLAUDE.md's existing prohibition — *"There is no `_bmad/config.yaml` — do not
reintroduce a read of one"* — and means **the documented module path cannot be adopted
wholesale without breaking the package.**

**Escape route.** `validate-module.py` checks merge-script **presence only**
(`path.is_file()`, lines 137–165); it never inspects content. `REQUIRED_YAML_FIELDS` is
`{code, name, description}`, already satisfied. The package can therefore be *structurally
conformant* while keeping a *semantically correct* TOML writer.

## 3. Decision

**l3io owns the state and the methodology; BMad owns execution; the customization layer is the
seam.** Stop replacing BMad skills by preference-probing; configure them through BMad's
documented, deterministically-merged override contract.

### 3.1 The override surface

```
1 (wins)  _bmad/custom/<skill>.user.toml   personal, gitignored
2         _bmad/custom/<skill>.toml         team, committed
3 (base)  <skill>/customize.toml            shipped defaults
```

Merge rules: scalars replace · tables deep-merge · **arrays-of-tables merge by `id`/`code` —
matching replaces in place, new ones append** · other arrays append.

37 BMad skills expose a `customize.toml`. All expose `activation_steps_prepend`,
`activation_steps_append`, `persistent_facts`, `on_complete`. `bmad-build` adds
`implementation_handoff`, `review_layers`, `oneshot_review_layers`. **`bmad-review` exposes
`[[workflow.lenses]]` keyed by `code`**, with a commented example (`code = "accessibility"`)
showing custom lenses are an intended extension point.

### 3.2 Module shape

The documented rule is structural: standalone = "a single agent or workflow" (self-registers on
first run); multi-skill = "two or more agents/workflows" with a dedicated `{code}-setup` skill,
guidance being *"for modules with more than 1-2 skills, a setup skill is the better choice."*
Applied here, that is a **mixed** answer:

| Module | Skills *after* §4.6 | Shape | Registration |
|---|---|---|---|
| `l3io-pm` | 4 (execute, plan, help, sync) | multi-skill + `l3io-pm-setup` | once-per-session pointer¹ |
| `l3io-util` | **1** (doctor) | standalone | auto on first run |
| `l3io-sec` | 1 (redteam) | standalone | auto on first run |
| `l3io-arch` | 1 (review) | standalone | auto on first run |

¹ Corrected below — shipped as a once-**per-project** pointer, not once-per-session; see the
"Correction (2026-09-21)" note after the mechanism description.

Note the interaction: retiring `l3io-util-cleanup` (§4.6) drops `l3io-util` to a single skill,
so it qualifies as standalone and needs **no setup skill**. Only `l3io-pm` is multi-skill.
**Exactly one setup skill is created, and three of four modules auto-register with no manual
step** — a materially better install experience than the four-setup-skill shape first
considered, and a direct consequence of doing the reorganization in the same change.

**A once-per-session pointer** is the agreed handling of the multi-skill install experience.

A naive config-presence check would be wrong here: `[modules.l3io-pm]` is absent in a *correct*
install (§1.4), so checking it on every activation would print a pointer on every invocation of
all four PM skills — exactly the detour `config-resolution.md` §5 removed. The pointer is
therefore emitted **at most once per session**, keyed on the `{session_id}` the PM skills
already bind, and it never runs setup.

The mechanism follows the existing `set-lock` / `check-lock` / `clear-lock` trio: a new
`pm-status.py notice --state-root S --session-id SESS --key setup-pointer` subcommand, flock
guarded, recording in `state/.notices.yaml` (gitignored, like the lock files). Exit 0 means
"not yet shown this session — show it and record"; exit 1 means "already shown". State writes
go through `pm-status.py` and nowhere else, so this stays consistent with the existing contract.

**Correction (2026-09-21), found during Task 10 implementation review.** The paragraph above
is wrong: there is no session concept that outlives one skill invocation to key on.
`step-00-activate.md` binds `{session_id}` fresh at the start of every invocation and "must
remain constant for the lifetime of this skill invocation" — a session *is* one invocation.
The only other caller `notice` could have shared a session with is a dispatched sprint
subagent, and `l3io-pm-execute`'s headless mode explicitly does not call `notice`. So no two
`notice` calls were ever going to share a session id, `exit 1` was unreachable by construction,
and an unconfigured project would have seen the pointer on **every** execute/plan invocation —
exactly the nagging this mechanism exists to prevent. `.notices.yaml`, its lock, and any
per-session pruning would have done no observable work.

**What shipped instead: keyed on the notice key alone, "once per working copy, ever."**
`pm-status.py notice --state-root S --key KEY` — no `--session-id`. Exit 0 means "not yet
emitted for this key in this ledger — show it and record it now"; exit 1 means "already
emitted for this key, permanently, in this ledger." **The honest scope is once per working
copy, not "anywhere in this project's history"**: `.notices.yaml` is gitignored
(`_ensure_lock_ignore`) alongside the lock files, so it is never committed and never travels
with the project — a fresh clone, a second worktree, or a CI checkout starts its own ledger
and sees the pointer once more. That is arguably the right behaviour (a new checkout is
usually a new person, or at least a new context, who should hear it once), but it is a claim
about a working copy's local state, not the project's shared history. There is no pruning: a
working copy's set of distinct notice keys stays small by construction, so nothing needs
bounding. This is correct for the setup pointer specifically because the condition it reports
— `modules.l3io-pm` absent — is itself a valid **permanent** state (§1.4) until someone
configures the project, not a transient one that would ever need re-flagging. A working
session-scoped concept was considered and rejected: there is no cross-invocation session
identifier available in this execution model, and inventing one (a time window, a pid file, a
terminal id) would be new machinery built to satisfy a phrase in this spec rather than an
actual need.

The published docs do not state whether setup skills auto-run; only the installed scaffolder
reference (`create-module.md:224`) says "run the setup skill". A bounded, silent-by-default
pointer is safe under either reading.

### 3.3 Known gap

`{workflow.implementation_handoff}` appears only in `step-03-implement.md:31`.
`step-oneshot.md` has `oneshot_review_layers` but **no handoff placeholder** — the oneshot route
hardcodes its implementation. Overrides reach the main route only. This design does not route
through oneshot; the limitation is recorded, not worked around.

## 4. Skill inventory and organization

Six findings, from a review of all eight skills against the goals and BMad's current state.

### 4.1 Two skills are lenses standing up as modules

`l3io-sec-redteam` (five threat lenses + AI-poisoning cross-cut) and `l3io-arch-review`
(standards review) are review lenses. BMad has a lens registry (`[[workflow.lenses]]` by `code`)
and review layers (`review_layers` by `id`). As standalone skills they fire only on explicit
invocation; as registered lenses they fire **inside BMad's own review step** — which is exactly
the stated goal. Both skills are retained for standalone use and *additionally* exposed as
lenses, sharing one set of references.

### 4.2 Progress reporting is duplicated across two modules

`l3io-pm-help progress` and `l3io-util-doctor stats` both render a plan-aware
phase→epic→sprint→story tree from `pm-status.py report`. `doctor stats` is the richer of the two
(dwell times, stuck-item flags, backlog by severity, calibration state) and becomes the owner;
`pm-help progress` forwards to it.

### 4.3 `l3io-pm-help` violates the package's own router rule

| | SKILL.md | `steps/` |
|---|---|---|
| `l3io-util-doctor` | 19,914 B | 20 files |
| `l3io-pm-help` | 19,997 B | **0 files** |

Identical size; one is a router, the other a monolith loaded in full every invocation. CLAUDE.md's
Module Layout rule was written about precisely this failure. `l3io-pm-help` is its unfixed
instance and is split into `steps/`.

### 4.4 Nothing owns the BMad overlay layer

Phase 3 produces overlay TOML for `bmad-build`, `bmad-review` and the story skills. No existing
skill has that job — it does not belong in `pm-execute` (wrong scope) or `arch-review` (wrong
domain). A new capability owns generating, diffing, installing and verifying overlays.

### 4.5 Nothing owns the artifact contract

The story/issue/sprint schemas — the artifacts the package exists to replace — are scattered
across `pm-execute`/`pm-plan` steps and `_shared/status-files.md`. They are promoted to a named
contract with an owner.

### 4.6 `l3io-util-cleanup` is dead

A 1.5 KB deprecated forwarder since 2.1.0, still consuming skill-listing budget. Retired.

## 5. Phases

### Phase 1 — Truth

1. Add a `deprecated` status distinct from `removed`. Re-encode `bmad-create-story`,
   `bmad-dev-story`, `bmad-review-adversarial-general` as `deprecated` with `deprecated_in` and
   `replaced_by`.
2. Declare `bmad-build` and `bmad-build-auto`.
3. Fix the false prose at `steps/sprint/step-03-dev-loop.md:73` and its `_shared` twin.
4. Teach `bmad-deps.py` to read `_bmad/_config/skill-manifest.csv` and **derive** shipped-ness,
   reporting any entry whose declared status contradicts the manifest. The hand-kept list
   becomes an annotation over a derived set.
5. Extend `check:docs` check 17 to fail when a directive *prefers* a name marked `deprecated`.
6. **Detect the layout collision** rather than configuring around it: `l3io-util-doctor`'s
   health check reports a project holding both a flat `sprint-status.yaml` and a sharded
   `state/` tree, and proposes `migrate-state`. No config variable is declared — see §1.4 for
   why declaring one would reverse a recorded decision.

**Gate:** all four `npm run check:*` pass; `bmad-deps.py verify` reports zero contradictions.

### Phase 2 — Conform and reorganize

**Packaging**

1. Relocate `module.yaml` → `assets/module.yaml`, **one per module, not one per skill**. The
   validator reads it from the setup skill for multi-skill modules (`validate-module.py:178`)
   and from the skill itself for standalone ones (`:139`):

   | Module | `assets/module.yaml` lives in | Operational skills |
   |---|---|---|
   | `l3io-pm` | `l3io-pm-setup/` | drop their copies (4 skills) |
   | `l3io-util` | `l3io-util-doctor/` | n/a (is the skill) |
   | `l3io-sec` | `l3io-sec-redteam/` | n/a (is the skill) |
   | `l3io-arch` | `l3io-arch-review/` | n/a (is the skill) |

   This makes `check:docs` check 16 (`module-yaml-agreement`, sibling files sharing a `code:`)
   **vestigial** — each module ends with exactly one `module.yaml`, so there are no siblings to
   disagree. Check 16 is retired in the same change, and its retirement noted in ADR-0008, since
   leaving a guard that can no longer fire is worse than no guard.
2. Add `scripts/merge-config.py` — **writes TOML** to `_bmad/custom/config.toml` /
   `config.user.toml`, wrapping existing `write-module-config.py` logic. Deliberate deviation
   per §2, recorded in ADR-0008. Lives beside its `module.yaml` (setup skill, or the standalone
   skill).
3. Add `scripts/merge-help-csv.py` — targets `_bmad/_config/bmad-help.csv`. Same placement rule.
4. Create **`l3io-pm-setup`** — the only setup skill. `l3io-util-doctor`, `l3io-sec-redteam` and
   `l3io-arch-review` stay standalone and self-registering (§3.2).
5. Two of the four `l3io-pm` operational skills (`l3io-pm-execute`, `l3io-pm-plan` — not
   `l3io-pm-help`/`l3io-pm-sync`) emit a **once-per-project**¹ pointer to `/l3io-pm-setup` via
   the new `pm-status.py notice` subcommand (§3.2) — never a per-invocation check. The three
   standalone skills keep today's auto-registration unchanged.
6. Narrow the `sync-shared-scripts.mjs` scope: `assets/module-setup.md` and the merge scripts
   currently sync into **all 8** skills, but are now needed in only the **4** module homes
   (`l3io-pm-setup`, `l3io-util-doctor`, `l3io-sec-redteam`, `l3io-arch-review`). This removes
   shipped payload rather than adding it. Regenerate every `payload-manifest.json` afterwards —
   `npm run sync:scripts` does not do it.

**Reorganization**

7. Split `l3io-pm-help` into `SKILL.md` router + `steps/` (§4.3).
8. `pm-help progress` forwards to `doctor stats` (§4.2).
9. Retire `l3io-util-cleanup` (§4.6); `docs/upgrading.md` records the mapping.
10. Scaffold the overlay owner (§4.4) — capability shell and contract only; overlay content is
    Phase 3.
11. Correct CLAUDE.md's false pointer to the artifact schema (§4.5). The contract already
    has one home; only the pointer is wrong.

**Gate:** `validate-module.py` returns `status: pass` for all four modules; a clean install in a
throwaway project registers `l3io-util`, `l3io-sec` and `l3io-arch` with no manual step and
prompts correctly for `l3io-pm`; `check:docs` mode-count and skill-name checks pass over the new
layout.

### Phase 3 — Extend (specified, not implemented here)

1. `review_layers` append, `id = "l3io-spec-alignment"` — runs `spec-align.py check-pointers`
   against the diff.
2. `[[workflow.lenses]]` entries exposing redteam's threat lenses and arch-review's standards
   (§4.1).
3. `persistent_facts` with `file:` globs — story technical ACs and `spec-index.md` as run facts.
4. `implementation_handoff` override dispatching the l3io dev agent with `Files in scope` and
   read-scope discipline.
5. `on_complete` writing back through `pm-status.py set-status`, replacing the flat-file write.
6. Retire the preference-probe; in-package agents become the default, reached via overlay
   rather than via absence of a BMad skill.

## 6. Delivery mechanism

Overlays are authored **in the consuming project**, never shipped into `_bmad/custom/` by the
module — per BMad Builder: *"There is no supported pattern for modules to write into
`_bmad/custom/`."* The overlay owner generates to a staging path, prints the diff against the
current merge, and instructs the user to place it. Verified with
`resolve_customization.py --skill <path> --project-root <root> --key workflow`.

**Unresolved:** the package already writes `_bmad/custom/config.toml`, whose rationale (layers
1–2 are installer-generated and wiped on every install — confirmed by their generated timestamp
headers) is empirically sound. bmb says that space is reserved for end users. Both cannot be
right. Resolve with the maintainers before Phase 3; Phases 1–2 do not depend on the answer.

## 7. Risks

| Risk | Mitigation |
|---|---|
| bmb v2.2.2 diverges further from core 6.12 | Conform structurally only; keep the TOML writer; ADR-0008 |
| Projects holding both flat and sharded layouts diverge silently | `doctor` health check detects co-existence, proposes `migrate-state` |
| `implementation_handoff` unreachable on oneshot | Do not route through oneshot (§3.3) |
| Phase 2 touches every skill directory | Gated by `validate-module.py`, the four `check:*` gates, and a clean-install test |
| Retiring `l3io-util-cleanup` breaks existing invocations | `docs/upgrading.md` mapping; check 1 permits naming a removed skill when mapping it |
| A new setup skill bloats the listing | Only one is added (`l3io-pm-setup`) while `l3io-util-cleanup` is retired, so the listing is net neutral |

## 8. Open questions

1. May a module's setup skill author `_bmad/custom/<skill>.toml`? (§6)
2. Is bmb's module contract intended for modules integrating with *core* skills, given the
   YAML/TOML split? (§2)
3. Should l3io and bmm deliberately share one artifact tree, or deliberately separate? Phase 1
   only makes the collision *detectable*; choosing a value is a separate call, and taking it
   would mean declaring a config variable, which §1.4 argues against.
4. Do the lens exports (§4.1) belong in `bmad-review`'s `lenses`, `bmad-build`'s `review_layers`,
   or both? They are different registries with different merge keys.
