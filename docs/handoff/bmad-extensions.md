# Handoff — bmad-extensions

**Resume line:** *"You are `bmad-extensions`. Read your handoff note, then continue."*

**Released:** 3.1.2. For the rest — current HEAD, whether main is in sync, whether the
tree is clean — run `git log --oneline -5` and `git status -sb`. An earlier revision of
this line pinned a commit by hand and was stale one commit later, which is the same
defect the rest of this note is about.

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

**Skills were renamed verb-first in 3.1.3.** `l3io-pm-execute`/`-plan`/`-help`/`-setup`/`-sync`
→ `l3io-execute`/`l3io-plan`/`l3io-help`/`l3io-setup`/`l3io-sync`, with deprecated forwarders
until 4.0.0; `l3io-util-doctor` → `l3io-doctor` with **no forwarder**. Full mapping and the
reasoning: `docs/upgrading.md`. This note was written before that release and is corrected,
not rewritten — treat any stale name elsewhere in it as a transcription error, not a second skill.

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
  `skills/l3io-doctor/scripts/tests/test-detect-layout.py`, which **fails the run** if
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

The l3io skills self-install `pm-status.py` at activation, and `/l3io-doctor update-ai-rules`
writes AI instruction files (`CLAUDE.md`, `AGENTS.md`, `.cursorrules`, …) at the **project root**.

In *this* repo `.agents/`, `.claude/skills/` and `.claude/settings.local.json` are gitignored, so
the churn is invisible to `git status`. **In a consuming repo they usually are not**, and the AI
rules files never are. A peer reported 78 files appearing mid-operation and regenerating twice
during a stash. Stage explicit paths; never `-A`/`-u` in a repo where these skills run.

*(Inference: the 78-file figure is the peer's observation, not measured here. The mechanism above
is verified in this tree; the blast radius in a consumer repo is not.)*

## Findings held in the shared KB, not restated here

Two notes written earlier in this session are in the shared basic-memory KB. **Read them
before re-deriving anything below** — they carry the method, the corrections and the
sampling caveats, which these one-liners do not.

- **Agent Session Cost, Measured**
- **BMAD and l3io Skill Behaviour** — merged by the KB owner from two notes this agent
  wrote, one of them titled *BMAD/l3io Skill Traps and Invariants*, which may still appear
  as a stale link target. If neither title resolves, search the content: `migrate-adrs`
  appears in it under any title. Prefer a content term over a title when citing the KB —
  a retitle left 17 dangling wikilinks across it, one of them pointing at the old title
  of this very note from the cost note beside it.

Three entries need a pointer *and* a caveat, because the bare number misleads:

- [done] **453 `audit-issues` findings with no applicable repair, on any pre-3.0 backlog** —
  all id `1f`, all "open item has status `deferred`". **This is now repairable**, which the KB
  note predates: `repair-issue --action normalize-status --all-legacy` (added this session,
  epic-aware) does it in one pass. `steps/triage.md` records 452 normalized on a real upgrade
  against the 453 findings measured then; the two counts come from different runs and neither
  has been reconciled — do not treat the gap as a defect without checking.
- [done] **Backlog traceability 0-of-517 → 49 after three fixes.** 49 is a hard ceiling, not a
  shortfall: 76 items point at artifacts that were never written. Method in
  `docs/superpowers/specs/2026-09-26-issue-source-structure-design.md` §1.
- **Session cost, measured over 1,868 turns:** 942.9 M tokens / $667, of which `cache_read`
  was 916.6 M / $458 — about 69%. Per-turn `cache_read` grew 179k → 873k between compactions
  and reset at each one. Relevant to any decision about turn counts, fix-loop caps or agent
  fan-out; `CLAUDE.md`'s note that cost scales with turns per session is the same effect.

**`n=1` labels are load-bearing — keep them.** Several measurements come from a single
consuming project. The flat-planning-tree shape in particular must not be generalised.

## A correction worth keeping, about this note

An earlier revision of this file disclaimed the four items above as "another agent's,
unverified". They are this agent's own, from earlier in this session, and were lost to a
context compaction. Checking the session and the tree found nothing, so the conclusion
followed correctly from the evidence available — the evidence was incomplete in a way that is
invisible from inside. A peer who still had the exchange corrected it, and the claims were
then confirmed against this session's own transcript under
`~/.claude/projects/<project>/452abcf5-*.jsonl`.

The lesson for the next session, which is the same failure mode as every defect fixed today:
**absent from context is indistinguishable from never existed.** Before recording that
something does not exist, check a source that outlives the context window — the transcript,
the KB, or git.
