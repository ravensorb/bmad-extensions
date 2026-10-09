# Agent instruction block — onboarding the extension into a project's AI instruction file

**Date:** 2026-10-09
**Status:** proposed
**Relates to:** ADR-0004 (agents propose, never silently edit, human-authored documents)

## 1. Problem

A project installs four modules and twelve skills, and its AI instruction file learns nothing.
The agent working in that project discovers l3io only when a human types a slash command. It has
no standing instruction that these skills exist, when to reach for them, or — the sharp edge —
that PM state is machine-written and must never be hand-edited.

An agent that does not know `pm-status.py` is the only writer will edit a state YAML directly.
That is precisely the failure the atomic writer exists to prevent: free-form YAML edits were
dropped and malformed under load and parallelism, which is why the writer was built.

**`update-ai-rules` does not solve this and was never meant to.** It is a *migration* tool: it
rewrites references to a *legacy* state layout into the current one. It is reachable only when a
user types it, when `split-status` calls it, or when health-check Check 7 proposes it after
finding legacy references. Install and setup never call it. On a project with no legacy history
it correctly does nothing — and the agent still knows nothing.

## 2. What this adds

A **marker-wrapped instruction block**, written into the running harness's instruction file,
maintained across install, upgrade and uninstall, and offered once per harness when a project is
opened under a harness that does not yet have it.

### 2.1 The markers

```markdown
<!-- l3io:begin v=3.2.6 -->
## LiquidLogicLabs Extensions (l3io)
…
<!-- l3io:end -->
```

HTML comment markers, following the body-marker precedent already used in this repo
(`<!-- resolver-invariant: canonical-contract -->`). They are invisible when rendered, survive a
file being reformatted, and are greppable.

The version in the opening marker records **which version generated the content that is
there** — it is not a trigger. Upgrade compares the *body*, not the version: identical body means
no write, even across a release. Otherwise every release would churn a file in the user's repo to
bump a string they did not ask about. The consequence is that the marker version can lag the
installed version, and that is correct rather than stale: it answers "what produced this text",
which is the question a reader actually has.

### 2.2 Target file — the running harness, and only that one

`{runtime}` is already bound at activation across four recognised values (`claude`, `codex`,
`copilot`, `other`); the metrics contract requires it, because token capture is exact under
Claude and `N/A` elsewhere. The target file follows from it:

| `{runtime}` | File |
|---|---|
| `claude` | `{project-root}/CLAUDE.md` |
| `copilot` | `{project-root}/.github/copilot-instructions.md` |
| `codex` / `other` | `{project-root}/AGENTS.md` |

**Never write a file for a harness that is not running.** This rule is inherited verbatim from
`update-ai-rules` Step AR5, where it was learned the hard way: that step used to say "always
target `AGENTS.md`", and restated its gate as "no instruction file of any kind exists" — a
different predicate. On a repo holding `AGENTS.md` but no `CLAUDE.md`, running under Claude,
that wrote a file for another AI system which was already present and possibly rewritten
earlier in the same run.

Adopting the existing rule rather than writing a second one is deliberate. Three disagreeing
definitions of "DEPRECATED forwarder" accumulated in this repo the other way, and were only
fixed by factoring them into one place.

## 3. Lifecycle

| Case | Behaviour |
|---|---|
| Install, file absent | Create the file with the block |
| Install, file present, no markers | **Propose**: show the block, confirm, then append |
| Install/upgrade, markers present, version differs | Replace content between markers in place |
| Upgrade, markers present, content identical | **No write at all** |
| Uninstall | Remove the block and its markers. **Never delete the file**, even if nothing remains |

**Uninstall needs its own path.** `steps/install.md`'s clean path removes payload by SHA-256
against each skill's `payload-manifest.json`. This block is **not payload** — it lives in a
user-owned file and is findable only by its markers. A clean that ignored it would leave the
instruction block behind, describing an extension that is no longer installed, which is worse
than leaving nothing.

**Uninstall never deletes the file.** An earlier draft said "delete it if empty and we created
it" — but nothing records who created it, so that rule had no source of truth and would have
needed a provenance field to answer a cosmetic question. Removing the block and leaving an empty
file is the honest outcome; deleting a file in the user's repo to save them one empty file is a
bad trade.

**Nothing outside the markers is ever touched.** Replacement is bounded by the marker pair. If
the opening marker is present without a closing one — a hand-edit, a bad merge — the operation
**refuses and reports**, rather than guessing where the block ends. A guess there would
truncate a user's own content.

## 4. Cross-harness discovery

A project installed under Claude, later opened under Copilot, has a `CLAUDE.md` block and an
instruction file for Copilot with none.

At activation, with `{runtime}` already bound, check the target file for `l3io:begin`. If
absent, emit a **one-time advisory** through the existing ledger:

```
uv run {pm_status} notice --state-root {pm_state_root} --key ai-rules-missing:{runtime}
```

`notice` is the one-time-**ever** ledger already backing the setup-pointer: exit 0 means "not
yet emitted for this key", exit 1 means "already shown, permanently". It is keyed on `--key`
alone, written under `notices_lock`, and already gitignored alongside the lock files.

Keying per **harness** is the point. A single global "already offered" flag would mean the
second harness is never asked.

**The notice is advisory and never blocks.** It fires at activation, which can be in the middle
of a run the user started for another reason; interrupting that to ask about a documentation
file is disproportionate. The same condition also surfaces as a `l3io-doctor` health-check
finding, where interruption is expected. Visible in two places, blocking in neither.

## 5. Content

The binding constraint is **size**, not completeness. This block enters every agent's context in
that project, on every invocation, forever. `l3io-doctor`'s `SKILL.md` once reached 96,980 B and
every invocation paid for fifteen procedures it would not run; the same discipline applies with
more force here, because this is not even our file.

Target: **under 2 KB, asserted by a test over the shipped asset** so it cannot grow unnoticed. It is a router, not a manual — it says what exists and what is
dangerous, and points at the skills for everything else.

What earns its place:

1. **State is machine-written.** `pm-status.py` is the only writer; never hand-edit a state
   YAML. First, because it is the one that causes damage.
2. **The skills**, one line each — when to reach for them, not how they work.
3. **Invocation is conversational.** No flags; these skills take positional scope tokens
   (`E{nnn}`, `E{nnn}-S{nn}`) or plain intent. This is what check 31 enforces in our own tree,
   and a user's agent should know it too.
4. **Estimates and actuals are both mandatory**, at story, sprint and epic level; `cost` is
   **derived** from tokens and a rate card, never entered.
5. **The system learns from actuals.** Calibration derives ratios from recorded actuals, so
   inaccurate actuals degrade every future estimate. This is the "why" that makes (4) stick —
   without it, (4) reads as bureaucracy.
6. **Rate cards go stale.** `cost` is `tokens_k × the model's per-class rates`. When the models
   in use change, the shipped table may no longer match published pricing. `pm-status.py rates`
   prints the table in force; `modules.l3io-pm.token_rates` overrides it per model. The
   instruction tells the agent to **check rather than assume** when it sees an unfamiliar model.

## 6. Where it lives

- `skills/_shared/agent-instructions.md` — the canonical block body, synced like every other
  shared asset. One source, so the four module homes cannot drift.
- `pm-status.py sync-agent-instructions --runtime R --project-root P {--apply|--remove|--check}`
  is the writer — a subcommand rather than prose, for the same reason
  every other file mutation here is: it must be idempotent, marker-bounded, and testable.
  Prose that "replaces between the markers" is not testable and will drift.
- Install, upgrade and uninstall call it from `steps/install.md`; activation calls the notice
  check from `steps/shared/step-00-activate.md`.

## 7. Testing

- Round-trip: install → upgrade → uninstall leaves the file byte-identical to before install.
- Idempotency: install twice writes once; the second run reports no change.
- Bounded replacement: content outside the markers is byte-identical after an upgrade, with a
  fixture whose file has user content both before and after the block.
- Refusal: an opening marker with no closing marker refuses and reports, and writes nothing.
- Per-harness: a notice satisfied for `claude` does not satisfy `copilot`.
- Create-vs-append: a project with no file gets one; a project with a file gets a proposal.
- Uninstall restraint: a file containing user content beyond the block is *not* deleted.

## 8. Explicitly out of scope

- Rewriting legacy state references — `update-ai-rules` owns that and keeps it.
- Writing instruction files for harnesses that are not running.
- Any change to `update-ai-rules`' detection rule or its `.legacy` exclusion.
