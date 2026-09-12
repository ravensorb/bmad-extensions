# Limits

What this package does not do. Some of these are deliberate design boundaries, some are
features that are specified but not built, and a few are knobs that exist but do nothing. All of
them are stated here so you do not have to discover them mid-run.

## Concurrency

**Parallelism is bounded by a fixed number, not adaptively sized.** Epics within a plan phase
run concurrently up to `max_parallel_subagents` (default 4). The settings `parallel_mode`,
`parallel_ceiling` and `safe_batch_size` appear in design material but are **not implemented** —
they describe an intended adaptive model, not current behaviour.

**Concurrent epics share one working tree, with no source-file independence check.** Nothing
verifies that two epics running in parallel will not touch the same files. This is why spec
editing is guarded by a lease, and it is the main reason to be conservative about parallel
phases on a codebase with shared surfaces.

**Sprints within an epic never run in parallel.** That is deliberate, not a missing feature:
each finished sprint's actuals feed forward into re-estimating the rest, which requires them to
complete in order.

## Platform and runtime

**`l3io-pm-sync` supports GitHub only.** Not GitLab, not Azure DevOps, not Jira. A remote that
does not parse as GitHub stops the run.

**Sync has no field-level conflict resolution.** `push` overwrites the remote issue with local
content — push wins by construction. The configuration template contains `field_rules` and
`status_labels` keys implying per-field authority; its own header states they are not read by
anything. Do not rely on them.

**Token and cost actuals are exact only under Claude.** Other runtimes record what they expose,
and `N/A` where they expose nothing — never a guess. Under `--runtime claude` an `N/A` token
count is refused outright, since a Claude session can read its own usage.

**`--runtime` accepts exactly four values**: `claude`, `codex`, `copilot`, `other`. Anything else
is a hard error, not a silent fallback to the permissive default.

## What the gates check, and what they don't

**The technical-AC gate checks coverage, not correctness.** It verifies that each of the six
dimensions is filled or explicitly marked `N/A` with a reason, and — with spec alignment on —
that each carries a pointer that resolves. It does not judge whether the criteria are
*technically right*. That is what code review is for.

**Blocking severities have no deferral path.** An architecture BLOCKER or MAJOR, or a security
CRITICAL or HIGH, is resolved in code, justified by an accepted ADR, or the run stops. There is
deliberately no mechanism to file one as a backlog item and carry on — so if you are looking for
the severity such a finding would take in the backlog, there isn't one.

**Nothing enforces that a story actually ran tests.** `completion_evidence.tests_passing` is
derived from recorded test runs and cannot be asserted, which prevents an agent claiming a pass
it never earned. But no gate can know which suites *should* have run: a story that changed code
and recorded nothing shows an absent value rather than a failure, and that absence is treated as
a finding at closure rather than caught at run time.

**Reviewer severity vocabularies are not validated.** Only the backlog's four levels are
enforced in code. The architecture and security vocabularies live in prose, so a reviewer
emitting an out-of-vocabulary severity word would not be caught by any gate.

## Things refused on purpose

Each of these exists because the permissive version shipped a bug.

- **`cost` cannot be entered.** It is derived from tokens and rates and frozen at capture.
- **`tests_passing`, `status` and `resolves` cannot be set directly.** Each has a verb that does
  the rest of the work — recording a test run, writing the transition event, scheduling backlog
  items.
- **`self-install` never downgrades.** A strictly newer installed helper is left alone, because
  overwriting it would strand every project already on that version.
- **`migrate-adrs --apply` refuses a dirty tree** rather than attempting a partial repair over
  the remains of an interrupted run.
- **A malformed lock is refused, not interpreted.** An unparseable claim is treated as held
  rather than guessed at.

## Knobs that exist but do nothing

Worth knowing so you do not spend time tuning them.

- **`max_fix_iterations_non_code`** is doubly inert: it is equal to `max_fix_iterations`, and
  every phase containing a fix loop is already skipped for DOCS and CONFIG work.
- **`granularity`** in the calibration file is never varied — every project runs story
  granularity in practice.
- **`sync-config.yaml`'s `field_rules` and `status_labels`** are reserved for the unimplemented
  conflict resolution described above.
- **`last_sync`** in the sync state file is written by nothing.

## Not in scope at all

- **The installer refreshes skills; it does not migrate your data.** Those are separate steps,
  and the second one is `/l3io-util-doctor`.
- **No BMad core script is bundled.** The config and customization resolvers are invoked from
  BMad's own installed location, never vendored here.
- **Test suites are never shipped to consumers.** They stay in the source repository and run in
  its CI.
- **This package does not replace any core BMad skill.** It orchestrates them. Story creation,
  dev, code review, QA and retrospective remain BMad's.

## See also

- [Skills and sequence](skills-and-sequence.md) — what each module does and does not require
- [Troubleshooting](troubleshooting.md) — when one of these boundaries stops a run
- [Architecture and execution model](architecture.md) — the reasoning behind the cost and
  concurrency decisions
