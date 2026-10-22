# `pm-status.py` becomes a package — design

**Status:** design approved in conversation; spec awaiting review.
**Scope:** `skills/_shared/pm-status.py`, its install contract, and the gates bound to its shape.
**Decision record:** amends ADR-0001. No new ADR number — ADR-0001 says the Option B argument
belongs "here", in that file.

## 1. Why now

`skills/_shared/pm-status.py` is **exactly 10,000 lines**, the hard cap set by ADR-0001's
2026-10-03 amendment and enforced by `check:docs` check 12. Any added line fails the gate.

ADR-0001 is explicit that raising the number again is not a default available to a working
session: *"If that fails, raising the number again becomes a decision made on evidence rather
than a default, and it should be argued here before it is taken."*

**The evidence the ADR asked for exists.** The cap has blocked four changes:

| Blocked | Cost of deferring |
|---|---|
| `subagent_models()` (v7 bridge Task 5) | mixed-model runs priced at one rate |
| a one-line timezone guard in `dispatch_window` | a hand-written `events.jsonl` reproduces a `TypeError` already fixed on the transcript side |
| a `remediate --record` verb (ADR-0012) | the attempt bound lives in prose with no mechanical record |
| check 12's own boundary test | stopped running once the file hit exactly 10,000 |

The fourth is the sharpest: the cap silently disabled a test *about the cap*.

## 2. What the spike measured

ADR-0001 names one successor and one test: *"Option B, a package directory under
`_bmad/scripts/`, whose only surviving objection is atomicity — test whether a directory-level
`os.replace` restores it."*

Four measurements, all in a scratch tree:

1. **The ADR's literal test FAILS.** `os.replace` onto a non-empty directory is refused —
   `OSError [39] Directory not empty`. `rename(2)` will not clobber a populated directory.
   Read strictly, this triggers the ADR's fallback clause.
2. **Atomicity is recoverable by a route the ADR did not consider.** A version-stamped
   directory plus a symlink: `pm-status -> pm-status-3.6.0/`, swapped by a single `os.replace`
   over the *link*. Measured atomic, and measured upgrading a live tree mid-flight.
3. **The Option C killer does not apply.** `uv run pm-status/__main__.py` — through the symlink
   — read the PEP 723 header, installed `ruamel.yaml`, and resolved a submodule import. This is
   the exact mechanism that killed `zipapp`/`shiv`/`pex`, and a package directory survives it.
4. **`__file__` stays the symlink path; `realpath(__file__)` reveals the live version.** Both
   are useful: the first is a stable binding, the second answers "which version is running".

**The symlink objection is weaker than it appears.** Symlink creation on Windows needs
privilege or developer mode — but `pm-status.py` calls `fcntl.flock` at four sites (42
references) and `fcntl` does not exist on Windows. The file is **already POSIX-only**. A
symlink adds no platform restriction that `flock` has not already imposed.

**Decision: adopt Option B**, with the symlink swap as the atom rather than a directory-level
`os.replace`.

## 3. The module map

Boundaries are drawn by **4.0.0 fate**, so the v7 cut deletes directories rather than hunting
scattered verbs.

`docs/superpowers/specs/2026-10-16-bmad-v7-layer-design.md` §4.5 classifies **22 of 43**
subcommands. The remaining 21 are classified here; §4.5 gains an amendment pointing at this
table, because "organise by fate" is not executable while fate is undefined for half the surface.

**Dies at 4.0.0 — 27 verbs, ~5,400 lines**

| Group | Verbs |
|---|---|
| Placement & state tree | `set-status` `move-epic` `archive-epic` `retire-epic` `import-node` `reparent-story` `list-epics` `list-stories` `show` `set-field` `set-depends-on` |
| Epic locks | `check-lock` `clear-lock` `set-lock` |
| Plan shape | `dump-plan` `reorg-log` `reorg-undo` |
| Story documents | `story-doc-init` `sync-story-doc` |
| Issues | `append-issue` `audit-issues` `list-issues` `promote-issue` `repair-issue` `resolve-issue` `schedule-issue` `update-issue` |

`story-doc-init`/`sync-story-doc` die because v7 regenerates leaf `.md` frontmatter
(`tickets.py:1199`), and §3.1 of the v7 design rules that file **never** safe to write.

**Survives — 15 verbs, ~3,100 lines:** `estimate-story` `estimate-rollup` `calibration`
`set-estimate` `set-actual` `add-test-run` `import-actual` `report` `usage` `rates` `dispatch`
`adr-reserve` `notice` `self-install` `sync-agent-instructions`

**Splits — 1:** `verify`. Its node loading (`_load_checked`, `list_sprint_dirs`) dies; its
estimate/actual verification and cost recompute survive. It is cut in two, not assigned.

### 3.1 Layout

```
skills/_shared/pm_status/
  __main__.py        PEP 723 header, CLI dispatch, register() calls      ~550
  __init__.py        re-export facade — see §6.1
  core/              locking, YAML round-trip, versions, self-install,
                     value helpers                                       ~690
  metrics/           calibration, spend attribution, estimates,
                     report model, renderers, usage                    ~2,600   SURVIVES
  instructions/      agent-instruction marker engine (pure, no I/O)       ~740   SURVIVES
  state/             layout resolution, state verbs, locks, issues,
                     reorg, story documents                            ~5,400   DELETED AT 4.0.0
```

`state/` is named for **what the code does**, not for the release that removes it. A `v6/`
directory bakes a prediction into the tree, and v7 has changed shape every week it has been
measured. Each module's docstring records its 4.0.0 fate; the directory name does not.

### 3.2 Parser registration is distributed

Each module exposes `register(subparsers)`; `__main__.py` imports and calls them. Deleting
`state/` at 4.0.0 then removes its 27 verbs by deleting a directory and one import line.
Central registration would leave a 530-line CLI to hand-edit, which is the outcome this
structure exists to avoid.

## 4. The install contract

**Installed layout**, under `{project-root}/_bmad/scripts/`:

```
pm-status  ->  pm-status-3.6.0/        the symlink IS the atom
pm-status-3.6.0/
  __main__.py  __init__.py  core/  metrics/  instructions/  state/
```

**Binding:** `{pm_status}` becomes `{project-root}/_bmad/scripts/pm-status/__main__.py`. The
link name never moves, so the binding is stable across upgrades.

**`self-install`**, five steps, one atomic:

1. Stage into `pm-status-<version>.staging-<pid>/` — non-atomic but invisible; nothing points at it.
2. Compute a **tree digest**: SHA-256 over sorted `(relpath, file-sha256)` pairs.
3. Compare to the installed tree's digest. Reinstall on difference, skip on identical.
   **Content-guarded, never version-guarded** — the marker is hand-maintained and has drifted
   twice, which is why the single-file guard already compares bytes.
4. `os.rename` staging → `pm-status-<version>/`.
5. Create a temp link, then **one `os.replace` over `pm-status`**.

Downgrade refusal is unchanged: a strictly newer installed version is still refused, because
content cannot express ordering.

**Retention.** Keep the live version and the immediately previous; delete older. GC runs
**after** the swap, never before, and never deletes the `realpath` of the live link. A crash
mid-GC leaves a half-deleted *old* version that nothing points at — harmless by construction,
and re-collected on the next install.

**`__file__` is the symlink**, so `self-install` resolves its *source* package from its own real
path. It runs from the skill's own copy, so this is a guard against a future "simplification",
not a live bug.

**Rollback improves.** It becomes a second link swap, because the previous version is still on
disk. Today a bad install has nothing to fall back to.

**No compatibility shim** at the old `pm-status.py` path. Every consumer is in this package and
changes in the same commit, and a shim resolving to a stale single-file copy is exactly the
version skew the content guard exists to prevent.

### 4.1 The legacy file

Every existing project carries `_bmad/scripts/pm-status.py` from earlier installs. Once the
package is live, nothing invokes it.

**`self-install` deletes it after the swap succeeds — but only when its SHA-256 matches a
version this package shipped.** An unmodified copy we installed is ours to remove. A patched or
pinned copy does not match, survives, and is reported instead. Without that condition,
activation would silently destroy a user's local modification.

## 5. Build tooling and gates

**No change needed.** `write-payload-manifest.mjs` already walks skill directories recursively
and excludes `__pycache__`, so `check:manifest` covers a package as-is. `check:lint:py` globs
`skills/`, so ruff picks the modules up free.

**Scope change, mechanical.** These parse or target one file and must target the package:
check 4 (CLI surface), check 10 (module docstring), check 30 (subcommand-required),
`check:types` (mypy), `check:version` (marker location), and `check-bmb`'s exemption keyed on
the `pm-status.py` path.

**`sync-shared-scripts.mjs` is the real work.** Its sync group is `{source: file, dest: file}`
and becomes tree→tree, with `--check` comparing trees. `--dump-deliveries` feeds check 24's
scope, so that contract must keep working — check 24 spawns the checked tree's own copy of this
script, and a broken dump surfaces as ~90 simultaneous failures naming nothing useful.

**Check 26 gets stronger.** It asserts state paths are assembled only in "`pm-status.py`'s
resolver section" — a comment marker inside one file. It becomes `state/layout.py`, a module
boundary the language enforces.

**Check 12 is replaced by a per-file cap of 1,500 lines**, over every `.py` in the package.

A package-*total* cap would rebuild the same wall one level up and would punish growth in
`metrics/`, the half under active development and the half that survives 4.0.0. A per-file cap
enforces the modularity this refactor buys.

1,500 is chosen so the three largest sections cannot move across as single lumps — issue store
2,410, calibration 1,891, subcommands 1,733 all exceed it. Splitting them **is** the
modularisation; a cap they already satisfy would only relocate the wall.

The mechanism is unchanged from check 12 and deliberately so: a hard number in a gate that
fails the build and names ADR-0001. The ~6,000-line prose trigger was crossed silently, and a
number that lives only in an ADR is a number nobody enforces.

## 6. Migration and proof

The suite is **1,009 test methods across 13,629 lines** — larger than the code it covers. It is
what makes this refactor provable, and it invokes two ways: `importlib.spec_from_file_location`
for direct internal calls, and `subprocess [sys.executable, SCRIPT, …]` for end-to-end CLI.

### 6.1 Never move code and its tests in the same step

If the 1,009 tests are repointed to new module paths while the code moves, the safety net and
the thing it protects change together and neither proves anything.

So `pm_status/__init__.py` carries a **re-export facade** of the internals the suite calls,
keeping the suite byte-identical through every extraction. The subprocess arm needs one constant
changed (`SCRIPT` → the package `__main__.py`); the import arm needs nothing.

The facade is a migration instrument, not the end state. Repointing tests to real module paths
is separate work, after green, and it is what finally lets the facade shrink to a genuine
public surface.

### 6.2 Sequencing

Each step ends with the full suite green and committed:

1. Package skeleton, `__main__.py`, distributed `register()`, facade `__init__.py`.
2. Extract one module at a time, least-risk first: `instructions/` (pure string transforms, no
   I/O) → `metrics/` → `core/` → `state/`.
3. Split the three over-cap files as they move. This is where the 1,500 cap does its work.
4. Flip the install contract and the `{pm_status}` bindings **last**, as one commit.

Steps 1–3 leave the package unrunnable by the skills, which is correct for a branch: the suite
exercises it directly, and the install contract is a single atomic change at the end.

### 6.3 Proof of behaviour-identity

The suite covers behaviour. It does **not** cover parser registration, which distributed
`register()` makes newly possible to break: a module whose `register()` is never called loses
its verbs silently, and no behavioural test fires because the test invoking that verb simply
fails to find it — which reads as a test bug.

So: capture `--help` for all 43 subcommands before the work and after, and require a
byte-identical diff. That is the artifact that catches a dropped `register()`.

## 7. Risks and open questions

- **This is the one runtime writer of project state.** The mitigation is §6.2's one-module-at-a-
  time sequencing with a green suite at each commit, not review attention.
- **The facade can become permanent.** A re-export surface that never shrinks means every module
  is reachable from the root and the boundaries are advisory. §6.1 names the shrink as separate
  work; it needs to actually happen, and nothing mechanical forces it.
- **1,500 may be wrong.** It is chosen to force three specific splits, not derived from a
  measurement of readability. If a module lands at 1,480 and is incoherent, the number did not
  help. Revisit on evidence, in ADR-0001, the same discipline as the line cap it replaces.
- **Symlinks on exotic filesystems.** Measured on this machine's ext4 under WSL2. A filesystem
  without symlink support breaks the swap, not merely the atomicity. `flock` already constrains
  this to POSIX, but "POSIX" and "supports symlinks" are not identical claims and only the first
  is currently enforced anywhere.
- **Open: does the per-skill payload copy stay a full tree?** Two skills ship `pm-status.py`
  today (`l3io-setup`, `l3io-doctor`). Each would ship the whole package, roughly doubling the
  payload bytes those two carry. Measure before deciding whether `l3io-doctor`, which only needs
  the installed copy refreshed, can ship less.

## 8. ADR

**Amend ADR-0001.** No new number: ADR-0001 states the Option B argument belongs in that file.
The amendment records the four spike measurements — including that its own named test fails —
the symlink route, the POSIX-only finding that defuses the Windows objection, and the per-file
cap replacing check 12.

`docs/superpowers/specs/2026-10-16-bmad-v7-layer-design.md` §4.5 also gains an amendment
pointing at §3 of this document for the full 43-verb classification.
