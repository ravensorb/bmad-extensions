# Handoff — bmad-extensions

**Resume line:** *"You are `bmad-extensions`. Read your handoff note, then continue."*

**Last updated:** 2026-09-27 · **HEAD:** `b46a27f` · **Released:** 3.1.2 · main in sync, tree clean

> **Naming is an assumption.** No agent name was assigned to this session; `bmad-extensions`
> is chosen after the repo. Rename the file if the user has another convention.

## What this agent owns

`bmad-l3io-extensions` — the four l3io BMad modules and their build/check tooling. Nothing in
the home-lab estate.

**Read first, in this order.** All of it is authoritative; this note points and does not restate.

1. `CLAUDE.md` — module layout, state contract, the estimates/actuals HARD RULE, calibration.
2. `scripts/check-docs.mjs` header — the 29 numbered checks **and** its `KNOWN GAPS` block.
   A numbered entry gives a check's rule; only that block gives its reach. Different questions.
3. `scripts/CLAUDE.md` — manifest contract, sync/verify commands, release gates.
4. `docs/adr/` — ADR-0005 (one ADR home) and ADR-0008 (packaging shape) are the load-bearing ones.

## Standing constraints from the user

- Use `uv run`, never bare `python`.
- Use maintained libraries over hand-rolled code; the escape hatch is an ADR (`CLAUDE.md` §1).
- Do not assume — verify against the tree.
- Never `git add -A` / `-u` broadly. See the churn note below for why that is sharper here.
- No unapproved version bumps; releases are the user's call.

## In flight

- [done] Six defects reported by two peer projects, verified in-tree and fixed — ADR filename
  scan, readiness deadlock, estimate-block deadlock, calibration redrive ordering, `1e` audit
  message, dev-loop agent contract. Released as 3.1.2, CI green.
- [done] CI now discovers Python suites instead of listing them (`npm run test:python`), and
  gates on BMad Builder's scanners (`npm run check:bmb`). Both green on the runner.
- [todo] `scripts/smoke-install.sh` never removes its `mktemp -d` workdir — no `trap`, no
  cleanup on any path. 11 leaked workdirs, 85 MB, 2026-09-21→26. `/tmp` here is **tmpfs**, so
  that is RAM. One line fixes it, and it makes our own shell standard true of our own script:
  `skills/l3io-arch-review/references/standards-shell.md` §"Temporary files and cleanup"
  mandates a trap on the next line, and the repo's only shell script has zero traps.
- [todo] Node test suites have no temp-dir leak guard. The Python suites do — see the
  `setUpModule`/`tearDownModule` guard in
  `skills/l3io-util-doctor/scripts/tests/test-detect-layout.py`, which **fails the run** if
  anything is left behind. Four `/tmp/check-docs-*` dirs (92 MB) leaked over five days because
  the Node side only cleans up and never asserts it cleaned up.
- [todo] 224 KB of test files ship to consumers. The installer copies whole skill directories,
  so `skills/*/scripts/tests/` lands in `.claude/skills/...` in every install — verified in a
  real smoke tree. `payload-manifest.json` reports **0** files under `tests/`, so the guard
  reads as an all-clear on a question it never asks. Options: exclude at install, move the
  suites out of skill dirs, or stop claiming tests are not shipped.
- [todo] Peer `docker apps source - agent 1` is on 3.0.1 and needs to update the plugin, not
  re-run self-install — self-install reads the payload copies inside the installed skills, so
  it cannot pull anything newer than the installed plugin.

## Decisions pending (user's, not the agent's)

- [blocked] Clearing the 85 MB of leaked smoke workdirs. Nine of eleven predate this session
  and ownership is unproven; the user has not asked for `/tmp` cleanup. Needs a yes.
- [blocked] Calibration: no cross-classification monotonicity guard, `MIN_SAMPLES = 3`, so a
  calibrated `complex` can price below a calibrated `standard`. Real behaviour, by design.
  Changing the threshold on one project's report is the decision being declined, not deferred.
- [blocked] `--source` becoming non-required on `append-issue` — breaking. Scoped out in
  `docs/superpowers/specs/2026-09-26-issue-source-structure-design.md` §9.
- [blocked] Concurrent epics share one working tree with no source-file independence check.
  Design exists (`docs/superpowers/specs/2026-08-17-adaptive-parallelism-design.md`); the
  adaptive-parallelism knobs it describes are **not implemented** (`CLAUDE.md`).
- [todo] Spec-alignment §8 pilot token measurement. The design says the pilot runs after
  release and its result is recorded as an amendment; the amendment was never written, so the
  5%-of-fresh-tokens budget is unmeasured.

## Two numbers that read as failure without their cause

Carry both halves or the next session re-derives them.

- **517-item backlog, 49 traceable — a ceiling, not a shortfall.** 76 of the untraceable items
  point at artifacts that were never written, so no reader can resolve them. Cause and method:
  `docs/superpowers/specs/2026-09-26-issue-source-structure-design.md` §1. The fix is structured
  `--source-phase`/`--source-ref` at the write boundary; §5 explains why backfilling is refused.
- **`migrate-adrs` once minted 14 duplicate ADRs and reported success.** *Fixed* in `eb448c8`,
  first released in **3.0.2**; the guard and its evidence are in `skills/_shared/spec-align.py`
  at `dup = docs_by_num.get(n) == slug`. **Still live for any consumer below 3.0.2**, and Health
  Check 15 recommends the mode to exactly those projects. Upgrade is the remedy.

## Churn caveat — this tooling causes it

The l3io skills self-install `pm-status.py` at activation, and `/l3io-util-doctor update-ai-rules`
writes AI instruction files (`CLAUDE.md`, `AGENTS.md`, `.cursorrules`, …) at the **project root**.

In *this* repo `.agents/`, `.claude/skills/` and `.claude/settings.local.json` are gitignored, so
the churn is invisible to `git status`. **In a consuming repo they usually are not**, and the AI
rules files never are. A peer reported 78 files appearing mid-operation and regenerating twice
during a stash. Stage explicit paths; never `-A`/`-u` in a repo where these skills run.

*(Inference: the 78-file figure is the peer's observation, not measured here. The mechanism above
is verified in this tree; the blast radius in a consumer repo is not.)*

## Not carried forward

A peer attributed two further findings to this agent — "453 integrity findings with 0 applicable
repairs" and two notes in a shared KB — plus `n=1` / "flat-planning-tree" labels. No record of any
of them exists in this session or this repo. They are most likely another agent's and are left out
rather than restated unverified.
