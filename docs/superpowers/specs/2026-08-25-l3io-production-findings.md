# l3io skill suite — findings from production use

**Reporter:** House Rules monorepo (`houserules`), l3io suite 2.4.7
**Period:** E000–E003, ~40 stories closed; E003 sprint 01 measured in detail
**Date:** 2026-08-25

Everything below was hit in a real run, and each finding carries the command that reproduces
it. Findings marked **[fixed locally]** have been patched in this project's vendored copy
(commit `c28eabd`); they are reported because the fix belongs upstream, not because this
project needs anything.

Severity is by consequence: **High** = wrong data or wrong money with no signal;
**Medium** = an agent is misled or a documented protection does not reach; **Low** = drift.

---

## 1. Story-file status is never written back — 73 of 73 divergent — **High**

`set-status` updates `state/<status>/epic-NNN/sprint-NN/E*.yaml`. Nothing in any step writes
the `status:` frontmatter of the story markdown at
`epic-NNN/sprint-NN/stories/E*.md`. Every story in this project that reached `done` still
reads `backlog` or `ready-for-dev` in the file a human opens.

```
73 story-file / state divergences
  E000-S01-001   state=done   story=backlog
  E000-S03-001   state=done   story=ready-for-dev
  ...
```

73 out of 73 in the same direction is not drift — it is an unimplemented write. The state
YAML is the machine's truth and the markdown is the human's, and they have never agreed.
Either the step files should write both, or the markdown should not carry a `status` field
at all; the current arrangement guarantees that the file a reviewer opens is wrong.

## 2. Post-sprint re-estimation is a stub, and its one concrete instruction is wrong — **High**

`steps/execute/step-05-epic-loop.md` §6. The bash block contains only comments:

```bash
# Update {pm_calibration_file} with this sprint's scope/fix/closure samples
# Then re-run step-estimate over remaining unstarted sprints
```

Three problems compound:

- The first line describes work `set-actual` already does inline (`metrics-contract.md` §8
  — "`set-actual` derives the calibration sample itself"). An agent following it literally
  either no-ops or double-writes.
- It then loads `steps/shared/step-estimate.md` for "remaining unstarted sprints", but that
  step's §1 for scope `E{nnn}` selects *all* stories under the epic including `done` ones,
  and its §2 says "each unestimated story (or story needing re-estimation)" with **no rule
  for what needs re-estimation**. `estimate-story` does overwrite unconditionally
  (`node["estimate"] = est`, `pm-status.py:2044`), so the machinery works — but nothing
  tells the agent to invoke it on an already-estimated story, and `step-02-story-prep.md`
  §3 explicitly skips those.
- Net effect: the loop that exists to propagate calibration into later sprints most likely
  does nothing.

Observed here: E003 sprint 01 estimated **$83.08** and cost **$288.97** (3.5×), and nothing
re-priced sprint 02. This is the feedback loop the whole calibration model is built around.

## 3. `completion_evidence.tests_passing` is an undefined boolean — **High**

`pm-status.py:1049` coerces it (`BOOL_NODE_FIELDS`); `step-03-dev-loop.md:213` writes it.
Nothing anywhere defines *which* suites constitute "tests", and nothing derives the required
set from what the story touched.

Consequence observed: a story reported ten green gates and `tests_passing: true` having
broken a suite it never ran, and the break was found two stories later by accident. The
boolean is not falsifiable — it records that the agent was satisfied, not that anything
passed.

Suggestion: record the commands run and their exit codes, and derive the required set from
the story's scope rather than the agent's choice.

## 4. Shared files are copied per skill with nothing detecting divergence — **Medium**

Eight files exist byte-identical in two or more skills:

```
references/status-files.md · metrics-contract.md · calibration-model.md
references/config-resolution.md · assets/module-setup.md
steps/shared/step-00-activate.md · step-00-digest.md · step-estimate.md
```

They were all identical, which is the good case — but nothing keeps them so. Editing one
copy of `step-00-digest.md` produced two versions instantly, with no check reporting it.
The headers say "Canonical source: `skills/_shared/…`", so a canonical source exists at
authoring time; a checksum manifest or a build step would make the copies verifiable at rest.

Reproduce: hash each shared-by-name file across skills and group.

## 5. Five in-body references point at a path that does not exist at runtime — **Medium**

`skills/_shared/status-files.md` is the authoring path; the installed path is
`references/status-files.md`. The *header* provenance notes are fine. These five are
directives telling an agent to go read something:

```
l3io-pm-execute/steps/shared/step-estimate.md:25, :86
l3io-pm-plan/steps/shared/step-estimate.md:25, :86
l3io-util-doctor/SKILL.md:154
l3io-util-doctor/steps/layout-cleanup.md:4
l3io-util-doctor/steps/split-status.md:12
```

## 6. The arch gate blocks on an interactive prompt, inside a step that forbids waiting — **Medium**

`steps/execute/step-04-arch-gate.md` §6, the zero-findings path:

```
⚠️  Arch gate found zero findings on CODE scope. This is unusual.
   Confirm before continuing: (y/n)
```
> Wait for user confirmation.

The same file's §3a hands every subagent a contract reading *"a reviewer that waits for an
answer it can never receive is exactly the failure that clause exists to prevent."* If the
gate is ever reached under `headless: true` or from a dispatched agent, it hangs — and it
hangs on the only path where nothing is wrong.

## 7. A stale zero survived a migration that dropped three valid samples — **Medium**

`pm-status.py`'s `derive_closure_sample` docstring is explicit and correct: *"A ZERO RESIDUAL
IS A SKIP, NOT A SAMPLE OF 0.0 … after three such sprints `active_closure_ratio` returns 0.0,
`cmd_estimate_rollup` accepts it, and the closure band contributes nothing to any future
estimate."* The runtime guard now refuses to create one.

But this project's calibration file still holds one, and the way it got there is backwards:

```
pm-calibration.yaml.pre-redrive   closure.sprint.tokens_k.samples: [3.7378, 0.0, 132.8062, 48.2812]
pm-calibration.yaml (current)     closure.sprint.tokens_k.samples: [0.0]
```

The redrive dropped the three real samples and kept the one the code calls poison.
`closure.sprint.elapsed_hours` likewise still carries a `0.0` among four. Whether the redrive
filtered or re-derived, the migration has no equivalent of the runtime guard. Suggestion: the
migration should drop zero closure samples on the same rule the runtime already applies.

## 8. `{agent_contract}` permitted two failure modes, both observed in one sprint — **Medium** [fixed locally]

The clause forbids waiting and polling. Neither of these is either:

1. **An agent ended a turn asking for an input.** Not a wait, not `BLOCKED` — it simply
   stopped, mid-story, with 47 files half-written. Recovering it took a manual message. The
   contract says "never wait"; it did not say "never stop on a question", and stopping is
   worse than waiting because the work is abandoned rather than recorded.
2. **An agent armed a background wait after producing its final line.** Each wake delivered
   it into a completed task, it replied "nothing outstanding", and stopped — firing another.
   Five echoes before it was killed manually. "Arm ONE wait" does not cover arming one *after
   you are done*.

Suggested clauses are in this project's patched digest.

## 9. The cost model steers agents away from the largest lever — **High** [fixed locally]

`steps/execute/step-05-epic-loop.md` §5 asserted *"Repository size is not the driver. Turn
count is."* Measured on E003 sprint 01, that is half of one model and the missing half is
where the money is:

| story | files changed | content read (`cache_write`) | per file | turns | cost |
|---|---:|---:|---:|---:|---:|
| S01-001 | 63 | 2,858k | 45k | ~67 | $67.73 |
| S01-003 | 46 | 2,589k | 56k | ~87 | $75.84 |
| S01-004 | 47 | 3,043k | 65k | ~64 | $69.19 |
| S01-006 | 13 | 1,792k | **138k** | ~82 | $49.55 |
| S01-007 | 20 | 376k | **19k** | **~249** | **$26.66** |

S01-007 took three times the turns of S01-006 and cost half as much. A token entering a
context is re-read on every turn after it, so:

```
cost ≈ C × ($6.25 + T/2 × $0.50) per million      C = cache_write, cache_read = C × T/2
```

At the T≈80 this system runs, **content read into a context costs ~$25 per million tokens**,
not the $0.50 the cache-read rate suggests. Both terms matter and both are settable.

The consequence is that the suite bounds the wrong agent. `step-03-dev-loop.md:92` has scoped
*reviewers* to the diff since reviewer spend was first measured — and a scoped reviewer is
3.4% of a story. The `bmad-dev-story` spawn (`:67`) receives a story path, a config block and
a sprint root, then decides for itself what to read. That is the 19k→138k spread above, on
the ~90% of the spend.

Fixes applied locally: state the `C × T` model; add a "What a read costs" section to the
digest and a read-cost clause to `{agent_contract}`; have stories carry a `Files in scope`
block written at prep and passed to the dev agent verbatim; add a ~25-file story-size ceiling
with the atomic exception stated; have code review write findings to a file and return a
one-line pointer; add orchestrator turn discipline, since every existing rule governs
dispatched agents and the orchestrator outlives all of them.

## 10. Parallel ADR subagents race on numbering — **Medium** [fixed locally]

`step-04-arch-gate.md` §6 spawns one ADR subagent per blocking finding, each told to write to
`adr-{nnn}-{slug}.md`, with no source for `{nnn}`. Three dispatched in parallel each read the
same near-empty directory: two chose `0013` and two chose `0014`. `ADR-0014` was then cited by
four stories meaning two different documents, resolving to whichever file won the filename.
Repair cost more than the gate.

A directory listing shows who has finished; only a register knows who is *in flight*. The fix
is to assign every number from the register before dispatch and pass it into the prompt.

## 11. The arch gate's re-validation pass re-reads everything — **Low** [fixed locally]

§6: *"re-validate the same story files with all reviewers (one more pass)"* — paying the whole
gate a second time to check a patch. Scoping the second pass to the ADRs written, the sections
they patched, and the finding each was resolving asks the same question for a fraction.

## 12. Vestigial multi-story language in the dev loop — **Low**

`step-03-dev-loop.md` §1 now guarantees exactly one story per agent, but §5's output template
still prints `stories done: {N}/{total}` and §3's fix-loop prose says "continue to next story".
Left over from the pre-split design; harmless but confusing to an agent holding one key.

---

## What is working, for calibration

Worth saying, because it is the reason the findings above are legible at all:

- **The turn-count model and the prep/story/closure split are correct** and measurably so.
  The reasoning in §5 about two 200-turn agents beating one 400-turn agent is right; it was
  simply incomplete.
- **`step-00-digest.md` as a subagent-scoped digest** is a good design — the routing table at
  the end genuinely keeps the three big references out of dispatched contexts.
- **The escalate-on-signal arch gate** (§4: run one reviewer, widen only on BLOCKER/MAJOR)
  is the right shape, and the argument for why it does not weaken the gate holds.
- **Batching story enrichment into one spawn** (`step-02-story-prep.md` §2) is correct and
  for the right reason.
- **`--cost` being rejected everywhere**, with cost derived from tokens × the model rate
  table, made every number in this report reproducible. Without it none of the above would
  have been measurable.

---

## Upstream verification (2026-08-25, against 2.4.7 `skills/_shared/`)

Each finding was checked against the source before planning. Result: **11 confirmed as
reported, 1 confirmed as an observation with a falsified mechanism.**

| # | Verdict | Evidence |
|---|---|---|
| 1 | CONFIRMED | `stories/{story_key}.md` appears only as a read (`step-02-story-prep.md:24`) or a path handed to a spawn (`step-03-dev-loop.md:89`). No write exists. |
| 2 | CONFIRMED | `step-05-epic-loop.md` §6 is a two-line comment-only bash block, then loads `step-estimate.md`. |
| 3 | CONFIRMED | `tests_passing` is coerced at `pm-status.py:1049` and written at `step-03-dev-loop.md:215` from `{tests_passing}`. No step defines the required suite set. |
| 4 | PARTLY — reframed | Upstream **does** detect divergence: `npm run check:scripts` covers all eight files. The real gap is downstream: an installed package carries no manifest, so copies are unverifiable *at rest in the consumer*. Fix belongs in what ships, not in CI. |
| 5 | CONFIRMED, undercounted | 10 runtime directives point at the authoring path, not 5 — the report missed `l3io-pm-sync/steps/shared/step-estimate.md:25,:86` and `l3io-util-doctor/steps/health-check.md:84`. Header provenance notes (e.g. `assets/migrate-state.md:9`) are correctly excluded. |
| 6 | CONFIRMED | `step-04-arch-gate.md:152-154` — `(y/n)` prompt followed by "Wait for user confirmation." |
| 7 | **MECHANISM FALSIFIED — finding upgraded** | See below. |
| 8 | CONFIRMED | `step-00-digest.md:59-66` carries exactly three clauses. Neither "stopped to ask a question" nor "armed a wait after the final line" is covered by any of them. |
| 9 | CONFIRMED — model fixed 2026-08-25 | The `C × T` model, the dev read scope, and the digest's cost line are corrected upstream. The five other local fixes listed are not yet upstream. |
| 10 | CONFIRMED | `step-04-arch-gate.md:122` writes `adr-{nnn}-{slug}.md` with no source for `{nnn}` and no register. |
| 11 | CONFIRMED | `step-04-arch-gate.md:126` — "re-validate the same story files with all reviewers (one more pass)". |
| 12 | CONFIRMED | `step-03-dev-loop.md:177` ("continue to next story") and `:275` (`stories done: {N}/{total}`). |

### Finding 7 — the redrive did not do this, and that makes it worse

The report attributes the loss of three `closure.sprint.tokens_k` samples to `calibration
redrive`. That is not what happened. Three code paths were read in full:

- `redrive_story_samples` (`pm-status.py:1650-1695`) replaces **only** `cal["scope"]` and
  `cal["fix"]`, mutating the loaded map in place. `closure` is never addressed.
- `migrate_calibration_token_basis` purges `scope.*.tokens_k` **only** — its docstring names
  "every non-tokens_k component" and closure as deliberate survivors.
- `migrate_calibration_metrics` drops `cost`, renames `time_hours`, quarantines `man_hours`.
  It removes no `tokens_k` samples from any component.

No code path in 2.4.7 removes a closure sample. The disappearance is therefore unexplained
and cannot be planned against without the two files.

**But the more important half of the finding survives, and is larger than reported.** The
zero-residual rule is enforced **on write only** (`derive_closure_sample`, `pm-status.py:1351`).
The read side does not apply it:

```python
def active_closure_ratio(cal, level, metric):
    s = _component_samples(cal, "closure", level, metric)
    return weighted_ratio(s) if len(s) >= MIN_SAMPLES else None   # 0.0 counted like any sample
```

So every file that already contains a zero — written by any version predating the write guard,
from any cause — stays poisoned permanently, and the guard that exists cannot help it. A
migration-side fix as the report suggests would repair files someone remembers to migrate. A
read-side filter repairs all of them, retroactively, with no migration and no schema change.
That is the fix this plan takes, and it makes the unexplained disappearance non-blocking:
whatever put the zero there, it can no longer train the band to zero.
