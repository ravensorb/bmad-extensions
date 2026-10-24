# ADR-0001: `pm-status.py` stays one self-installed file

- **Status:** Accepted, then **SUPERSEDED IN PART** — the single-file half of this decision was
  reversed on 2026-10-23 (see the final amendment: Option B is taken and `pm-status` is a
  package). The title records what was decided in 2026-09-10 and is **no longer an
  instruction**: new code goes in the module that owns it, never into `__main__.py` to keep a
  file count down. Everything else here — self-install, the content guard, single-consumer code
  living in its own skill's `scripts/` — still stands.
- **Date:** 2026-09-10
- **Deciders:** Package maintainer; reviewed by `l3io-arch-review` Mode B
- **Principle(s) in tension:** Core §1 separation of concerns vs. an atomic, single-copy runtime install

## Context

`pm-status.py` is the one runtime writer of l3io-pm state, used by `l3io-execute`,
`l3io-plan`, `l3io-sync`, and `l3io-doctor`. Each skill ships a synced copy, and at
setup or activation runs `self-install --dest {project-root}/_bmad/scripts/pm-status.py`.
`cmd_self_install` copies exactly `__file__` under one SHA-256 content guard and one
`os.replace`. A sibling module would never reach `_bmad/scripts/`, so the installed copy could
not import it.

The file is 5,060 lines and handles state transitions, estimation, calibration, reporting,
usage capture, and self-install. The issue-lifecycle design
(`docs/superpowers/specs/2026-09-10-issue-lifecycle-design.md`) adds further verbs. Until now the
constraint existed only as prose in `CLAUDE.md`.

The constraint does not apply uniformly: `write-module-config.py`, `drift-report.py`, and
`init-sanctum.py` all run from their own skill directory. It binds only code that more than one
skill needs at runtime.

## Options considered

| Option | Pros | Cons | Standards fit |
|--------|------|------|---------------|
| A. One self-installed file; single-consumer code lives in its skill's own `scripts/` | Atomic install; one-hash guard; one-file footprint in BMad core's directory; no packaging | The file keeps growing | Honors §1 where it can (single-consumer code moves out); accepts one large shared file |
| B. A package directory under `_bmad/scripts/` | Normal module boundaries | Multi-file hash guard; loses the atomic `os.replace`; more files in core's directory | Better §1; worse install integrity |
| C. Build-time bundling into one file | Modular source, single-file artifact | A bundler to adopt (stickytape, pinliner — unevaluated) or hand-roll (forbidden by global rule 1); a build step in a repo that has none | Neutral §1; adds tooling |

## Decision

Option A. Anything that more than one skill runs at runtime stays inside `pm-status.py`. Code
with a single consumer ships in that skill's own `scripts/` and reaches `pm-status.py` only
through its CLI. The first application: the issue audit's heuristic checks go to
`l3io-doctor/scripts/audit-backlog.py`, while its integrity checks stay in `pm-status.py`.

## Consequences

- Positive: installs stay atomic and verifiable by one hash; no new tooling.
- Negative / trade-offs accepted: `pm-status.py` remains a large file, owned by the package
  maintainers.
- Follow-ups / exit plan: revisit when the file passes ~6,000 lines, or when a verb needs a
  dependency its other callers do not. (This clause named Option C as the successor; **the
  2026-10-03 amendment RETIRED Option C** — see that section for the evidence. The sentence is
  removed rather than left standing, because an exit plan is read as an instruction and this one
  pointed at a closed door.)

## Amendment (2026-09-11)

The ~6,000-line size trigger fired: `skills/_shared/pm-status.py` was 6,479 lines at this
commit. Decision: **keep Option A.** The file is still one runtime writer with one
self-install hash guard, and no verb yet needs a dependency its other callers do not — the
dependency trigger is unchanged.

The revisit trigger is replaced with a hard, mechanically enforced number: **8,000 lines.**
`npm run check:docs` gains check 12 (`pm-status-size`), which reads
`skills/_shared/pm-status.py` and fails when its line count exceeds 8,000, naming the count,
the limit, and this ADR. This is deliberately a different mechanism from the ~6,000-line
prose trigger it replaces — a number that only lives in an ADR's prose was exactly the
failure mode global rule 3 warns about (a rule that isn't checked is a rule that gets missed
at 8,000 the same way it was crossed silently at 6,000).

This amendment named Option C as the candidate to reach for when check 12 trips. **That
sentence is withdrawn: the 2026-10-03 amendment below retired Option C outright**, after doing
the bundler evaluation this one asked for. The dependency trigger from the original decision (a
verb needing a dependency its other callers do not) is unchanged and still applies
independently of line count.

## Amendment (2026-10-03) — the limit is raised to 10,000, and Option C is withdrawn

Check 12 tripped at 8,025 lines, adding `repair-issue --action normalize-keys`. **Decision:
raise the hard limit to 10,000 and keep Option A.** Option C is withdrawn as the named
successor, because the evaluation the 2026-09-11 amendment asked for was finally done and
the ground it assumed is gone.

**What the evaluation found.** Both bundlers that amendment named are abandoned: `stickytape`
0.2.1 was last released 2021-01-29 (5.7 years) and `pinliner` 0.2.0 on 2016-04-03 (10.5
years). Adopting either fails the same global rule 1 that forbids hand-rolling one. The
maintained alternatives — `shiv`, `pex`, `zipapp` — all produce an archive rather than a text
script, and that breaks two things this package depends on:

- **PEP 723 provisioning.** `uv` reads inline metadata only from a text script. Measured with
  identical content in both shapes: a `.pyz` raised `ModuleNotFoundError`, the `.py` printed
  `Installed 1 package`. Every script here gets `ruamel.yaml` that way, with no venv on the
  consuming project.
- **Byte-reproducibility.** Two zipapp builds of unchanged source differ, because zip stores
  mtimes. That breaks `check:scripts` and the per-file SHA-256 in `payload-manifest.json`.

So Option C has no viable tool, not merely no chosen one.

**Why not Option B instead.** It is cheaper than it was — it was rejected partly for needing a
multi-file hash guard, and `payload-manifest.json` now is one, verified by `check:manifest`.
What has not changed is that `self-install` does a single `os.replace`, which is atomic;
installing N files is not, and a crash mid-install leaves a half-written runtime writing
project state. A directory-level `os.replace` may answer that, and is the first thing to test
if this is reopened.

**What 10,000 is and is not.** It is not a judgement that the file is fine at 10,000 lines; it
is headroom bought deliberately while the structural options are unavailable. The mechanism
stays exactly as the previous amendment built it — a hard number in check 12, failing the
build, naming this ADR — because the lesson that produced it still holds: the ~6,000 prose
trigger was crossed silently, and a number that only lives in an ADR is a number nobody
enforces. The dependency trigger (a verb needing a dependency its other callers do not) is
unchanged and still applies independently.

**Option C is RETIRED, not deferred — do not re-evaluate these.** `stickytape`, `pinliner`
and the archive family (`zipapp`, `shiv`, `pex`) are closed, with the evidence above:

| Candidate | Why it is dead |
|---|---|
| `stickytape` | last release 2021-01-29; unmaintained, so global rule 1 forbids it as surely as hand-rolling |
| `pinliner` | last release 2016-04-03; same |
| `zipapp` / `shiv` / `pex` | produce an archive, so `uv` cannot read a PEP 723 header from it and the artifact is not byte-reproducible — two mechanisms this package depends on, measured, not assumed |

A future proposal in this space is only worth hearing if it produces a **single text script**
AND preserves PEP 723 provisioning AND is byte-reproducible AND is maintained. Nothing on the
table does, and re-testing the four above wastes the evaluation already recorded here.

**Revisit at 10,000 with one option:** Option B, a package directory under
`_bmad/scripts/`, whose only surviving objection is atomicity — test whether a directory-level
`os.replace` restores it. If that fails, raising the number again becomes a decision made on
evidence rather than a default, and it should be argued here before it is taken.

## Amendment (2026-10-23) — `_bmad/scripts/` is BMad's directory, and it is wiped on every install

**This ADR has always described self-install as "content-guarded, self-healing on first use"
without recording what it is healing *from*.** The answer, found while evaluating Option B:
**BMad deletes that directory and recreates it from its own sources on every install or update
— on both generations.**

| Generation | Mechanism |
|---|---|
| 6.12.4 | `tools/installer/core/installer.js`, `_installSharedScripts()`: `await fs.remove(paths.scriptsDir)` then `ensureDir`, then copies `src/scripts/*`. BMad's own comment: *"Wipes the destination first so files removed or renamed in source don't linger and get recorded as installed."* |
| 7 preview (`61e01f8`) | `skills/bmad/scripts/setup.py`, `ensure_scripts()`: `tree_matches` is exact equality, so any foreign file marks the tree stale; repair is `shutil.rmtree(dest)` then recreate from the declared tree. |

Read from source at both pins; not executed — there is no v7 release to test against.

**Three consequences, none of which were written down:**

1. **The re-run at every activation is load-bearing, not defensive.** `self-install` is invoked
   on activation by `l3io-execute`, `l3io-plan`, `l3io-sync` and `l3io-doctor`. That looks like
   belt-and-braces and is not: a BMad install or update between two runs deletes the installed
   copy, and the next activation is what puts it back. **Do not "optimise" it to run once**, and
   do not gate it behind a first-run check.
2. **The content guard is why the deletion is invisible.** Because the guard compares bytes and
   treats missing as different, a wiped copy is simply reinstalled. The mechanism has been
   absorbing this since it was written, which is why nobody noticed the directory was not ours.
3. **`_bmad/scripts/` is not a safe home for anything of ours that must persist on its own.**
   Anything placed there must be re-derivable from a skill's shipped payload. Nothing of ours
   may be the only copy of itself there — a user's local patch to the installed file is
   destroyed by the next BMad install, by BMad, not by us.

This does not change the Option A/B decision. It corrects the premise both options were
weighed against: the atomicity of *our* write was argued at length, while the fact that BMad
periodically removes the file outright was not considered at all.

**The v7 successor is a different mechanism, and belongs with the v7 work, not here.** v7 lets a
module declare its scripts (`scripts = [...]` under `[skill]` in `bmod.toml`) and installs them
itself, which makes them part of the declared set the wipe rebuilds *from* rather than foreign
files it removes. Note that `skills/bmad-toolsmith/shapes/script-utility/shape.md` states that
destination as `_bmad/scripts/` while `read_module_scripts()` says `_bmad/<code>/scripts/`;
the code is the one that runs, and this needs verifying against a real install once v7 tags.


## Amendment (2026-10-23) — Option B is taken: `pm-status` is a package, and the cap is per file

The 2026-10-03 amendment set the revisit at 10,000 lines with exactly one option and exactly
one test: *"Option B, a package directory under `_bmad/scripts/`, whose only surviving
objection is atomicity — test whether a directory-level `os.replace` restores it."* The file
reached 10,000, the test was run, and **Option B is adopted.** `skills/_shared/pm-status.py`
is now `skills/_shared/pm_status/`, an entry file plus seven modules.

### The spike: four measurements

Run in a scratch tree, re-run independently when this amendment was written.

1. **The test this ADR named FAILS.** `os.replace` onto a **non-empty** directory is refused:
   `OSError [Errno 39] ENOTEMPTY — Directory not empty`. `rename(2)` will not clobber a
   populated directory. (Onto an *empty* one it succeeds — which is not the case that matters,
   since the destination is a live install.) Read strictly, this triggers the fallback clause.
2. **Atomicity is recoverable by a route this ADR did not consider.** A version-stamped
   directory plus a symlink — `pm-status -> pm-status-3.6.0/` — swapped by a single
   `os.replace` over the **link**. Measured atomic, and measured swapping a live tree.
3. **The Option C killer does not apply to a package.** `uv run <link>/pm_status/__main__.py`
   read the PEP 723 header through the symlink, installed `ruamel.yaml`, and resolved a
   submodule import. That is the exact mechanism that retired `zipapp`/`shiv`/`pex` above, and
   a package directory survives it.
4. **`__file__` stays the symlink path; `realpath(__file__)` reveals the live version.** Both
   are useful: a stable binding, and an answer to "which version is actually running".

**The Windows objection to symlinks is already moot here.** Creating a symlink on Windows needs
privilege or developer mode — but the locking core calls `fcntl.flock` at four sites (8 calls,
21 `fcntl` references, all in `core/`), and `fcntl` does not exist on Windows. This code is
**already POSIX-only**; a symlink adds no restriction `flock` has not already imposed.

### The decision, and the distinction that matters in the record

**Option B is adopted with the PLAIN-DIRECTORY install, not the symlink.** `self-install`
stages into a sibling, renames the live tree aside, and renames staging into place.

That is a **deliberate economy, not a second failure to clear the bar**, and the difference is
why the spike was worth running. The objection that blocked Option B in 2026-10-03 turns out to
be **answerable** — measurement 2 is a genuinely atomic directory swap. We are declining to
spend it: `2026-10-16-bmad-v7-layer-design.md` §3.4 retires `self-install` entirely at 4.0.0,
when v7 installs a module's declared scripts itself. The symlink design carries a retention
rule, a GC pass that must never delete the live tree, and a `realpath`-vs-`__file__` subtlety —
care spent on a mechanism with a death date. **If `self-install` ever outlives 4.0.0, the
symlink design is specified in measurement 2 and in `2026-10-22-pm-status-package-split-design.md`
§2, and should be taken.**

The accepted cost is recorded rather than buried: between the two renames there is no
`pm-status/` directory for the duration of one `rename(2)`. It is self-healing (the content
guard treats missing as different, so the next activation reinstalls — the same property that
has been absorbing BMad's own wipe of `_bmad/scripts/`, per the amendment above), it fails
loudly rather than writing a wrong answer to project state, and a crashed install leaves
`*.old-*`/`*.staging-*` siblings that the next run sweeps. It is still a regression against the
single-file `os.replace`, which had no window at all.

### Check 12 becomes a PER-FILE cap of 1,500 lines

`PM_STATUS_LINE_LIMIT = 10000` is **deleted**. Check 12 now reads every `.py` under
`skills/_shared/pm_status/` and fails on any file over **1,500 lines** — `__main__.py`
included, on the same number as every module, since the extraction finished. There is one
limit, not two.

**Splitting the module is the answer to tripping it. Raising the number is not.** This is the
substantive difference from every previous amendment: at 8,000 and again at 10,000 the only
available response was more headroom, because the structural options were unavailable. They are
available now — a file over 1,500 lines has a seam, and finding it is the work the cap exists
to force. A package-*total* cap was rejected for rebuilding the same wall one level up.

**Where 1,500 came from, measured rather than as the design document states it.** The spec
justified the number by three sections that would exceed it — "issue store 2,410, calibration
1,891, subcommands 1,733". Those are **banner-derived and wrong**, the same flawed measurement
that put `instructions` at 737 lines when it is 277; the real per-definition carve
(`boundary-measurement.md`) gives issues **1,967**, calibration **1,220** and the subcommand
verbs **1,100**, so two of the three named lumps are *under* the cap.

What 1,500 actually forced is a level up, and it is the thing that mattered: it made the
four-bucket carve impossible as four files. `state` (4,345) had to become `nodes` + `issues` +
`verbs` + `plan`, `metrics` (3,475) had to become seven modules, and `issues` (1,967) had to
split four ways again. No module in the finished package reaches the cap — `verbs/__init__.py`
is the largest at 1,386 — which is the intended end state, not a sign the number was slack.

It remains a forcing number, not a measurement of readability: **if a module lands just under
it and is incoherent, the number did not help — revisit it here, on evidence, the same
discipline as the line cap it replaces.**

The mechanism is deliberately unchanged: a hard number in a gate that fails the build and names
this ADR. The ~6,000-line prose trigger was crossed silently, and a number that lives only in an
ADR is a number nobody enforces.

### What this does NOT change

- **Single-consumer code still lives in its own skill's `scripts/`.** The original decision's
  second half is untouched; `audit-backlog.py` stays where it is.
- **Never bundle a BMad core script**, and Option C stays **RETIRED** — the bundler and archive
  evaluation above is not reopened by this.
- **The dependency trigger** (a verb needing a dependency its other callers do not) is
  unchanged, and is now cheap to satisfy: a module can carry its own import.
- **`_bmad/scripts/` is still BMad's directory**, wiped on every BMad install, which is why
  self-install runs at every activation. A directory is wiped exactly as a file was.

Full design, including the 43-verb classification by 4.0.0 fate and the install contract:
`docs/superpowers/specs/2026-10-22-pm-status-package-split-design.md`.
