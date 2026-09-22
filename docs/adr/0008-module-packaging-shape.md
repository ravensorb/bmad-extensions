# ADR-0008: Module packaging shape — one setup skill, three standalone modules, and a TOML writer under BMad's required name

## Status

Accepted — 2026-09-22.

Number allocated by `pm-status.py adr-reserve --epic E000 --slug module-packaging-shape`, not
chosen by hand. See *A reservation that lives only in prose is not a reservation*, below.

## Context

This package ships four modules — `l3io-pm`, `l3io-util`, `l3io-sec`, `l3io-arch` — as eight
Claude Code skills in one flat `skills/` directory. BMad 6.12.0 plus BMad Builder v2.2.2 expect
a module to be laid out one of two ways, and the two differ in what they require. The evidence
below was read out of the installed BMad tree (`_bmad/`, `.claude/skills/bmad-module-builder/`),
not inferred from its documentation.

**BMad's validator accepts exactly two shapes.**
`validate-module.py:61` recognises a *standalone* module: a directory that is itself a skill,
carrying both `SKILL.md` and `assets/module.yaml`. `validate-module.py:178` covers the other
shape: a multi-skill module, whose `assets/module.yaml`, `assets/module-help.csv` and `SKILL.md`
must live in a dedicated `*-setup` skill beside its siblings. A module is one or the other;
there is no third arrangement the validator understands.

**The validator checks presence, not content.** `validate-module.py:137–165` — the standalone
branch — builds two dictionaries of required paths and asks `Path.is_file()` of each. An empty
`merge-config.py` satisfies it exactly as well as a working one. Conformance to this validator
is therefore a statement about *shape*, and nothing at all about behaviour.

**BMad core reads TOML. BMad Builder's scaffolder writes YAML.**
`_bmad/scripts/config_utils.py:98` `load_central_config()` merges exactly four layers, and every
one of them is TOML: `_bmad/config.toml`, `config.user.toml`, `custom/config.toml`,
`custom/config.user.toml`. The `merge-config.py` that bmb's scaffolder emits
(`.claude/skills/bmad-module-builder/assets/setup-skill-template/scripts/merge-config.py`)
writes `_bmad/config.yaml` and `_bmad/config.user.yaml` instead, and on a successful merge
**deletes** the legacy per-module `config.yaml` files it read from. Running the scaffolded
script as written would produce a file core never reads, and remove files in the process.

**One guard had become unfireable.** `check:docs` check 16 at the time — `module-yaml-agreement`
— asserted that sibling `module.yaml` files sharing a `code:` agreed with one another. Once each
module has exactly one `module.yaml`, at its home, there are no siblings left to disagree, and
the check could not fail for any tree the other checks permit.

## Decision

1. **The module shape is mixed, because the modules are.** `l3io-pm` is the only multi-skill
   module, so it gets the dedicated setup skill the validator's second shape requires:
   `l3io-pm-setup`, carrying `assets/module.yaml`, `assets/module-help.csv` and
   `assets/module-setup.md` for the whole module. `l3io-util`, `l3io-sec` and `l3io-arch` are
   single-skill modules and take the standalone shape — `l3io-util-doctor`,
   `l3io-sec-redteam` and `l3io-arch-review` are each their own module home and self-register.
   One `module.yaml` per module code, always at that module's home, never at a skill root.

2. **Setup is never implicit.** An absent `[modules.<code>]` config section is a valid, permanent
   state — a module can be installed and unconfigured — so it is not a first-run trigger. Setup
   runs only on an explicit `setup` / `configure` / `install` request.

3. **`l3io-pm-execute` and `l3io-pm-plan` emit a pointer to `/l3io-pm-setup` at most once per
   project working copy**, via `pm-status.py notice --state-root S --key KEY`, and only when the
   config section is absent. This was specified as *once per session*, and shipped that way
   first; it did not work. `{session_id}` is bound per skill invocation, so no two `notice` calls
   could ever share one, the "already shown" exit was unreachable, and an unconfigured project
   would have been told on every single invocation — the exact nagging the mechanism existed to
   prevent. The ledger is keyed on `--key` alone. It lives in the state root's `.notices.yaml`,
   which is gitignored, so the honest scope is **once per working copy**: a fresh clone sees the
   pointer once more. Five review passes accepted "once per session" before one asked whether the
   feature does what it promises rather than whether it matches the brief.

4. **`scripts/merge-config.py` keeps BMad's required *name* and rejects its *behaviour*.** It is
   a `runpy` wrapper over this package's existing `write-module-config.py`, so it writes TOML
   into `_bmad/custom/config.toml` / `config.user.toml` — the two layers `load_central_config()`
   actually reads and the installer does not regenerate. It deletes nothing. The file exists at
   the path and name the validator demands; what it does is governed by what core reads. The
   deviation is recorded in the script's own docstring, not only here.

5. **`scripts/merge-help-csv.py` exists for the same reason and is not wired into setup.** The
   installer assembles `_bmad/_config/bmad-help.csv` from each module's `module-help.csv`;
   `module-setup.md` states that setup must not write it. The script satisfies the validator's
   presence check and serves manual re-registration. That constraint is written in the script's
   own docstring, where the next reader meets it.

6. **Check 16 `module-yaml-agreement` is retired, and `check:module` replaces it.** A guard that
   cannot fire is worse than no guard: it reads as coverage and stops the next person looking.
   `scripts/check-module.mjs` asserts the invariant that actually matters now — one `module.yaml`
   per module code, at the module home, with the payload its shape requires, and never at a skill
   root — with both the skill set and the module set derived by walking `skills/`. Retiring 16
   renumbered the checks above it; three separate sweeps, each with a different search pattern,
   found 4 then 5 then 3 stale `check N` references, twelve in all. Numbered cross-references in
   prose are effectively unguardable, and this is the evidence for that claim.

7. **BMad's validator is not a repository gate, and `check:module` is.** The validator assumes a
   module occupies its own directory, and this package's `skills/` tree is flat, so it cannot
   read `l3io-pm` from source at all. Measured, 2026-09-22, both ways round:

   | Invocation | Result |
   |---|---|
   | `validate-module.py skills/l3io-util-doctor` | `pass`, `standalone: true` |
   | `validate-module.py skills/l3io-sec-redteam` | `pass`, `standalone: true` |
   | `validate-module.py skills/l3io-arch-review` | `pass`, `standalone: true` |
   | `validate-module.py skills/l3io-pm-setup` | `fail` — 4 × `orphan-entry` |
   | `validate-module.py skills/` | `fail` — no module detected / cross-module findings |

   Pointed at `l3io-pm-setup` alone, line 61's standalone test matches (the home has both
   `SKILL.md` and `assets/module.yaml`), so the module is read as single-skill and the four
   sibling skills its `module-help.csv` declares become `orphan-entry` findings — the CSV is
   right and the directory is only part of the module. Pointed at `skills/`,
   `find_skill_folders()` (`validate-module.py:44`) claims every sibling carrying a `SKILL.md`,
   assigning three other modules' skills to whichever module is under examination. **Neither
   failure is a defect in the package**, and neither can be fixed by rearranging files without
   giving up the flat tree.

   A real install does not help by itself, and the obvious guess is wrong: skills land **flat**
   in `.claude/skills/` beside every `bmm`/`core`/`bmb` skill, and `_bmad/<code>/` holds only
   `config.yaml` and `module-help.csv` — no skills at all. Measured on a real
   `npx bmad-method install`: pointed at `.claude/skills/`, the validator detects
   `l3io-pm-setup`, claims the entire flat tree as `l3io-pm`, and emits a `missing-entry`
   finding for every unrelated skill.

   **So the module must be assembled before it can be validated, and `npm run smoke:install`
   now does that.** It builds one view per plugin from `marketplace.json`'s own
   `plugins[].skills` arrays — never a hand-kept list — copying those skills out of the real
   install, and validates each view. Result: all four modules `"status": "pass"`, `l3io-pm`
   with zero findings. This is the closing move `ruling-task9-validator-scope.md` wrote up and
   left unimplemented; it is implemented, because the alternative was a smoke check that could
   only ever print FAIL, which trains people to ignore the run.

   The repository-side invariant remains `check:module`'s, derived from the tree. What stays
   true is the narrower statement: **from the flat source tree alone, `l3io-pm` cannot be
   validated** — only the three standalone modules can.

## Consequences

- The package satisfies BMad's installed-shape contract for all four modules without adopting a
  config format core does not read. `npm run smoke:install` proves this against a real
  `npx bmad-method install`, including that every skill `marketplace.json` declares actually
  lands in `.claude/skills/`.
- `/l3io-pm-setup` is installed with its siblings — `marketplace.json` installs the `l3io-pm`
  plugin as one unit — but never has to be *run*. It is also `pm-status.py`'s single payload copy
  for the whole `l3io-pm` module; its four sibling skills self-install from it.
- `merge-config.py`'s deviation must be re-checked whenever BMad Builder's scaffolder changes.
  Nothing detects that automatically. **Revisit if** BMad core starts reading a YAML config
  layer, if bmb's template starts writing TOML, or if the validator begins checking content
  rather than presence — at which point the wrapper may be able to go away entirely.
- The `l3io-pm` flat-tree conformance gap in Decision 7 stays open, deliberately. This sentence
  is the record that nothing closes it from source.

## What this plan's execution taught, with the evidence that cost it

These are findings, not maxims. Each is recorded because something shipped, or nearly shipped,
without it.

1. **"The tests pass" is evidence about the tests, not about the code.** Three mutation sweeps of
   `check:docs` check 17 found seven behaviours asserted in prose and pinned by no test. The
   third sweep ran 81 mutations across every decision point: 51 RED, 8 provably equivalent, and
   **21 GREEN while changing a real verdict**. No shipped behaviour of the check was wrong; every
   survivor was a hole in what the suite held. Only the sweep distinguishes those two states.

2. **A guard's header states what it was tested against, not what it is believed to mirror.**
   Check 21 `skill-frontmatter` was written to mirror what BMad's installer requires. Measured
   against BMad's real parser over 25 shapes, it agreed on 18 — and never looked at
   `description`, which BMad requires to be a non-empty string. Seven shapes were DROP in BMad
   and PASS for us; deleting one line from a `SKILL.md` left three gates green while a real
   install dropped the skill. The guard built to close the silent-drop class closed half of it
   through the field it checked, and left the rule open through the field beside it.

3. **A guard proves a rule; it does not prove the rule's reach.** Check 17 enforced the right
   rule over `skills/` while `.github/workflows/checks.yml` — the place the defect actually lived
   — sat outside its scope. Ask what set a check examines before asking whether its rule is
   right.

4. **Moving text unchanged can break it, even when the text is byte-identical.** Splitting
   `l3io-pm-help` into a router plus `steps/` was verified lossless by concatenate-and-diff: zero
   differing bytes. It was still broken. Two mode files referenced "section 5 of the main flow"
   for a `clear-lock` remedy, and the router forbids those paths from loading step-05. A
   cross-reference is only valid if the referenced file is on the reader's load path, and
   splitting a file changes every load path in it.

5. **Derive the scope internally; anchor the content externally.** Deriving a test's cases from
   the list under test defends against the list *growing* and defends against nothing when it
   *shrinks*: removing `-W` from `PY_VALUE_OPTS` removed the `-W` case, and the suite passed
   having silently generated one fewer test. A vacuous green produced by following the
   derive-don't-enumerate rule correctly. The repair keeps the templating *and* adds a membership
   assertion against an external source of truth. This ADR's own check 22 does the same: scope
   from `skills/`, expected row count re-derived independently inside the test.

   The cleanest demonstration in this repo sits in check 22's own suite. Replace its scope
   derivation with a hand-list of today's eight skills and the test asserting *"every `l3io-*`
   skill directory is matched against the block"* **still passes** — the list happens to equal
   the tree. Only the scope-attack test, which plants a ninth skill directory, goes red. A test
   that measures the rule over the current scope cannot tell you the scope is derived; only one
   that changes the scope can.

6. **Verifying the fix is a separate act from verifying the diagnosis.** One brief proved an
   existing documentation pointer wrong and prescribed a replacement — which was also wrong, in
   the same sentence, in the same commit, while reporting the problem solved. The proof step
   covered only the diagnosis.

7. **A reservation that lives only in prose is not a reservation.** `adr-reserve` allocates
   against the register and the ADR files on disk. Neither knows what a design document has
   promised. This plan's design doc had spoken for ADR-0007 in four places; a later task
   hand-picked 0007 from max-on-disk for an unrelated decision, and the collision was invisible
   to every mechanical check. The rule is the one the Global Constraints already state — allocate
   through `adr-reserve`, never by hand — and the cost of ignoring it is paid in stale references.

8. **Each repair is itself unreviewed work.** In the check-17 work, round 1's fix created round
   2's finding, and round 2's first attempt at that finding created its own vacuous test. A fix
   round is not a smaller kind of change; it is a change made under more time pressure and less
   review.
