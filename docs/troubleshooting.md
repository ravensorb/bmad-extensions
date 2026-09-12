# Troubleshooting

Every skill in this package refuses loudly rather than guessing. A run that stops prints
`BLOCKED:`, `FAILED:` or `HALT`, and this page maps those to causes and fixes.

Two general rules first:

- **`BLOCKED:` means nothing was written.** The run stopped before changing state. It is safe to
  fix the cause and re-run.
- **Re-running without changing anything will block identically.** There is no override flag for
  most gates, by design. If a message tells you what to fix, that is the only path forward.

When you do not know where you are, `/l3io-pm-help` reads the project and tells you the next
action. It is read-only and safe at any time.

## Exit codes

Both Python helpers use stable exit codes, useful when scripting around them.

| Code | `pm-status.py` | `spec-align.py` |
|---|---|---|
| 0 | success / verified | ok |
| 1 | — | a report-mode check found problems |
| 2 | usage error | a gate refused, or bad input |
| 3 | node not found | — |
| 4 | verification failure (missing or invalid field) | — |
| 5 | epic locked | the spec-sync lease is held by another owner |

## Setup and environment

### `ruamel.yaml is required`

```
pm-status.py: ruamel.yaml is required. Run via `uv run` (auto-provisions it) or `pip install ruamel.yaml`.
```

The helper's dependencies come from an inline PEP 723 header, which only `uv run` reads. Run it
through `uv`, or `pip install ruamel.yaml` for the interpreter you are using.

Note that missing `uv` alone is not fatal — the skills fall back to `python3`. It only becomes
fatal when that interpreter also lacks the dependency, which is why `uv` is listed as a
prerequisite.

### BMad core is not installed

Config resolution runs BMad core's `resolve_config.py`. If it is missing, the skill blocks and
tells you to run the BMad installer. It will not write a config itself or continue on guesses.

### `{state root} is gitignored`

```
BLOCKED: {pm_state_root} is gitignored. Project state must be committed.
```

Project state is meant to be committed — it is how work survives between sessions and agents.
The message prints the two negation lines to add to `.gitignore`.

## State layout problems

These are the most common blockers on an existing project, and all of them are resolved by the
doctor rather than by hand.

### `multiple state layouts detected`

```
BLOCKED: multiple state layouts detected (sharded=… legacy-per-epic=… legacy-flat=…).
An earlier migration did not finish.
```

The detector counts layouts rather than stopping at the first one it finds, precisely so a
half-finished migration cannot be mistaken for a clean project. Inspect both locations, remove
the stale one, then re-run `/l3io-util-doctor migrate-state`.

### `legacy state layout — migrate required`

A flat `sprint-status.yaml` or a legacy per-epic `_bmad/state/` tree was found. Run
`/l3io-util-doctor migrate-state`. Originals are preserved as `.legacy`.

Do not run the individual migration modes by hand — `split-status` in particular produces a
three-file layout that the PM skills *still* cannot read. Let the doctor sequence the migration.

### `state found at … but implementation_artifacts resolves to …`

```
BLOCKED: … Refusing to start a blank project over existing state.
```

State exists somewhere other than where config now points, which usually means
`implementation_artifacts` was changed after work had already begun. Decide which location is
authoritative and fix the config, or move the state. There is no automatic remediation here, and
that is deliberate — the alternative is silently starting a second, empty project.

### `schema verify failed for {epic}`

An active epic failed integrity verification at activation. Inspect the epic's node files. The
verification detail is printed above the message.

## Planning problems

### `plan-output-meta.yaml absent`

No plan exists. Run `/l3io-pm-plan`.

If snapshots exist but the pointer does not, the message lists them and offers two paths:
re-run `/l3io-pm-plan` to rebuild the pointer (recommended), or write the pointer by hand if you
have verified a particular snapshot is complete.

### `plan readiness is RED`

Two things unblock it: run `/l3io-pm-plan` to resolve the gaps, or — having accepted the risk —
edit `readiness:` in `plan-output-meta.yaml` to `amber` and re-run.

Re-running `/l3io-pm-execute` unchanged will block identically. The step file says so explicitly,
because it is the obvious wrong move.

### `readiness gate — red` at plan time

The readiness check found blocking issues. They are listed in
`{planning_artifacts}/readiness-report.md`. Fix the Red findings and re-run.

### `artifact-only stories detected`

Story markdown files exist without matching state nodes — normal for projects whose stories were
created with the legacy `bmad-create-story` outside this package. Run
`/l3io-util-doctor bootstrap-state` once. It is idempotent: existing correct nodes are skipped.

### `dependency graph has errors`

A cycle, printed as e.g. `E001 → E003 → E001`. Fix the `depends_on` fields on the named nodes.

### `plan-output-meta.yaml points at {file}, which does not exist`

Re-run `/l3io-pm-plan` to rebuild both. Do not substitute another snapshot — the pointer and the
readiness value belong together.

## Execution problems

### `{epic} is owned by another session` / `lock held by another session`

Epic locks are TTL-based. A lock older than the TTL is treated as stale and taken over
automatically, so this means a genuinely live session holds it. Wait for expiry, or clear it
deliberately with `pm-status.py clear-lock`.

A malformed lock field is *also* refused rather than guessed at, which is why a corrupt
`_lock` presents the same way. During a multi-epic run, a locked epic is skipped and the run
continues to the next one rather than halting everything.

### `FAILED: story … findings unresolved after {n} fix iterations`

The per-story fix loop hit its cap (default 3). Before failing, every unresolved finding is
recorded as a backlog item, so nothing is lost, and the story is left at `review`.

There is no automatic retry past the cap — deliberately, because each iteration is a turn
multiplier and cost grows with the square of a session's turn count. Act on the recorded
findings, then re-run the sprint.

### `story … depends on {dep}, which is not done`

The orchestrator dispatches in dependency order, so hitting this points at a dependency-graph
problem upstream rather than a scheduling accident. It does not re-queue — with one agent per
story there is no queue to reorder.

### `story … still missing technical ACs after elaboration`

The six-dimension technical-AC gate re-checked after enrichment and still failed. This one needs
a human: open the story and fill the missing dimension, or mark it `N/A` with a reason. Every
dimension must be satisfied or explicitly excused.

### `arch gate — {n} blocking findings unresolved after ADR resolution`

The epic architecture gate ran its resolution pass and BLOCKER or MAJOR findings survived. There
is no deferral path for blocking severities — they are resolved in code, or justified by an
accepted ADR, or the run stops. That is the gate working as intended.

## Spec alignment problems

### `spec-sync lease held by {owner}`

Exit 5. Parallel epic closures share one working tree, so a lease prevents two of them editing
one architecture document at once. The acquire path retries before failing, and a closure that
cannot get the lease records a deferral rather than blocking outright.

Releasing someone else's lease is refused.

### `Departs from spec: … does not resolve`

An ADR points at a spec section that the spec index cannot find. Fix the pointer so it matches a
real `path#anchor`, or correct the heading it refers to.

### `migrate-adrs --apply refuses: uncommitted changes already sit under …`

A previous run stopped midway, leaving moved files uncommitted. Inspect and commit or revert
**those specific paths** by hand.

Never use a repo-wide discard: other agents may share this checkout, and a blanket reset would
destroy their uncommitted work. The message lists exactly which paths to look at.

## Sync problems

### `platform detection failed`

`l3io-pm-sync` supports GitHub only. Point a remote at a GitHub repository and re-run.

### `authentication unavailable`

Neither path worked. Configure GitHub MCP, or run `gh auth login`. Note that
`github_auth_method` is a preference rather than a guarantee — `mcp` falls through to the `gh`
CLI when no MCP tools are present, so this message means *both* failed.

## Housekeeping problems

### `Cleanup HALT — {n} classifiable file(s) remain after {n} passes`

Layout cleanup could not resolve some filenames after several passes. The residual files are
listed; they usually need manual mapping because their names are genuinely ambiguous. The skill
waits for your guidance rather than guessing.

### `verification failed for {epic} — newly created nodes did not pass integrity check`

From `bootstrap-state`. The state files are on disk and nothing was removed. Inspect the epic's
directory, correct or delete the malformed nodes, and re-run — correct nodes are skipped.

## Things that are refused on purpose

These are not errors to work around. Each one exists because the alternative shipped a bug once.

| You tried | Why it is refused | Do this instead |
|---|---|---|
| `set-actual --cost …` | Cost is derived from tokens × rates, never entered | Fix the token counts, or the `token_rates` override |
| `set-field completion_evidence.tests_passing` | An agent asserting its own tests passed is not falsifiable — one once shipped `true` over a suite it never ran | `add-test-run --command CMD --exit-code N`; the flag is derived from it |
| `set-field status` | Status transitions also write the event log and run the done hook | `set-status` |
| `set-field resolves` | Promotion schedules backlog items | `promote-issue` |
| `--runtime` with any other value | Only `claude`, `codex`, `copilot`, `other` are valid | Use one of the four; `other` when unsure |
| An `N/A` token count under `--runtime claude` | A Claude session can read its own usage | Capture the real figures from the transcript |
| Downgrading the installed `pm-status.py` | Self-install refuses to overwrite a strictly newer copy, which would strand projects already on it | Upgrade the package instead |

## Still stuck?

- `/l3io-pm-help` — what to do next, read-only
- `/l3io-util-doctor check` — the full diagnostic, read-only, changes nothing
- [Limits](limits.md) — it may be something this package deliberately does not do
- [Upgrading](upgrading.md) — if the project came from an older version
