# Sprint Step 03: Development Loop

Communicate all responses in `{communication_language}`.

Execute each story in the sprint: develop, code review, iterate on fixes. Write actuals and
completion evidence when done.

## 1. Story scope and dependencies

`{story_keys}` normally holds **exactly one** story: `step-05-epic-loop.md` §5b dispatches one
agent per story so that no session accumulates the turn count of a whole sprint. Process every
key it does hold, in order, and then end — never look for more work.

Before starting a story, check that each of its `depends_on` entries is `status: done`:

```bash
python3 {pm_status} show --state-root {pm_state_root} --epic {epic_key} --sprint {sprint_num}
```

lists every story in this sprint with its status.

If a dependency is not done, **end with `BLOCKED`** — do not wait and do not re-queue:

```
BLOCKED: story {story_key} depends on {dep_key}, which is not done.
```

Re-queueing was the right move when one agent held the whole sprint and could come back to a
story later. With one story per agent there is no queue to reorder, and nothing will change
inside this session — the orchestrator already dispatches in dependency order, so a dependency
that is still open means the ordering or the graph is wrong, and that is worth surfacing rather
than working around.

## 2. For each story: develop

Mark story in-progress:
```bash
python3 {pm_status} set-status \
  --state-root {pm_state_root} \
  --story {story_key} \
  --status in-progress
```

Keep the story document in step with the state — the state YAML is what the machine reads and
this file is what a reviewer opens, and they have not agreed until now:

```bash
python3 {pm_status} sync-story-doc --artifacts-root {implementation_artifacts} \
  --story {story_key} --status in-progress
```

This never fails: a missing or frontmatter-less document warns on stderr and returns 0, because
the state transition it follows is already durable and must not be rolled back by a
documentation write.

**Dispatch tracking — always emit the matching close.** Every subagent spawn in this step
brackets with `pm-status.py dispatch --event open` immediately before and `--event close`
immediately after, using the same `--agent`/`--epic`/`--sprint`/`--story`/`--session-id`
identity for both. Two things read this pair: `report --stall-minutes` flags a hung subagent
from it, and closure uses it to place the boundary between a story's own spend and the
orchestrator's (`references/metrics-contract.md` §6). It records the boundary only — the token
counts on either side of it are still read from the session transcript's `usage` fields by the
closing agent, exactly as for every other metric; `pm-status.py` derives nothing from these
events.
**Close on every exit path — `DONE`, `BLOCKED`, and `FAILED` alike.** A dispatch left open
because this step exited early is not just a missed close: a later retry that opens the same
identity (same agent, same story) before that stale open is closed silently overwrites it in
`pm-status.py`'s pending-dispatch map, and the original hang's timestamp is lost for good. That
overwrite-on-duplicate-identity behavior is intentional in `pm-status.py` (a retry of the same
agent on the same node reuses the identity on purpose) — the burden it places on this step is
simply: never skip the close.

```bash
python3 {pm_status} dispatch --state-root {pm_state_root} --event open \
  --agent bmad-dev-story --epic {epic_key} --sprint {sprint_num} --story {story_key} \
  --session-id {session_id}
```

**Give the dev agent a starting set — its own ACs bound the rest.** A reviewer can be handed a
closed input set because the diff *is* its input. A dev agent has to explore, so the reviewer
rule below does not transfer: "never the repository" would simply make it fail. What it must
not do is open the spec tree to work out *what to build*. That is what the story's technical
ACs are for — `steps/sprint/step-02-story-prep.md` §2 already required this story to carry its
interface and data-model contracts, error and edge handling, observability, security,
testability, and the existing-library answer. When those are present the dev reads the story,
the files it changes, and their direct collaborators; it does not re-read the specs those ACs
were distilled from. Every token read in early is re-read on every later turn
(`steps/execute/step-05-epic-loop.md` §5), so a spec opened whole to recover one contract is
spend the AC gate already paid to make unnecessary. If an AC turns out **not** to carry what
the dev needs, that is a story-prep defect: name the missing dimension and the section that
supplied it in the completion notes, rather than widening the read for the rest of the run.

**Nothing enforces this at run time** — it is prose a subagent can ignore, and no CI check can
see what a dispatched agent chose to read. It is measurable afterwards, which is the next best
thing: `usage --agent bmad-dev-story --story {story_key}` scopes to this dispatch bracket, and
the `cache_write` it reports is very nearly the volume the agent read in. An outlier there is
this rule being broken, not a large story — per-file spend measured between 19k and 138k
tokens across one sprint on stories of comparable size.

Spawn `bmad-dev-story` subagent with:
- Story file path: `{sprint_root}/stories/{story_key}.md`
- Project context: the config resolved at activation (`references/config-resolution.md`) —
  pass the bound values, not a config file path
- Sprint root: `{sprint_root}`
- **Read scope**: this story, the files it changes, and their direct collaborators. The
  technical ACs carry the contracts — do not open the spec tree to rediscover them. Widening
  beyond this is a decision worth recording, not a default.
- `{agent_contract}` (verbatim — see `steps/shared/step-00-digest.md`)

```bash
python3 {pm_status} dispatch --state-root {pm_state_root} --event close \
  --agent bmad-dev-story --epic {epic_key} --sprint {sprint_num} --story {story_key} \
  --session-id {session_id}
```

On completion, collect: files changed, tests passing (boolean), fix iterations attempted.

## 3. For each story: code review (CODE and MIXED only)

Skip if `{work_type}` is DOCS or CONFIG.

```bash
python3 {pm_status} dispatch --state-root {pm_state_root} --event open \
  --agent bmad-code-review --epic {epic_key} --sprint {sprint_num} --story {story_key} \
  --session-id {session_id}
```

**Scope every reviewer to the diff and named sections — never the repository.** Pass the
changed files (or the diff itself) plus the *specific* spec/standard sections that apply, by
path and section number. Never point a reviewer at the project and let it decide what to
read: a reviewer that loads the corpus pays a full `cache_write` over it before its first
thought, and then re-reads that prefix on every turn it takes. Scoped this way a reviewer's
spend measures at roughly **3.4% of a story's tokens**; unscoped it is a multiple of the work
under review. If a reviewer says it lacks context, name the additional section — do not widen
it to the repository.

Spawn `bmad-code-review` subagent with:
- Story file path
- **The diff** for the files the dev subagent changed — not the repository, not the
  directories they sit in
- Only the standard/spec sections the story's ACs invoke, by path and section number
- Review against the story's technical ACs — all six dimensions
  (`steps/sprint/step-02-story-prep.md` §2), not only whether the code works
- **Reused-before-written check.** Flag any non-trivial logic that a maintained library or
  a platform/stdlib capability already provides — retries and backoff, date and timezone
  handling, config merging, HTTP clients, parsing, validation, caching. Severity by
  consequence, as for any finding: a hand-rolled equivalent of a well-tested library is
  normally HIGH, since it is code that must be maintained and reviewed forever to reach
  parity a dependency already has. If the story's dimension-6 answer justified writing it,
  that is the answer — check the code matches the justification rather than re-litigating it.
- `{agent_contract}` (verbatim — see `steps/shared/step-00-digest.md`)

```bash
python3 {pm_status} dispatch --state-root {pm_state_root} --event close \
  --agent bmad-code-review --epic {epic_key} --sprint {sprint_num} --story {story_key} \
  --session-id {session_id}
```

Code review returns findings by severity.

**If CRITICAL or HIGH findings:** spawn dev subagent again to fix (fix iteration). Bracket this
re-dispatch with its own open/close pair — same agent name and story identity as §2's
`bmad-dev-story` call, so a hang here is flagged the same way:

```bash
python3 {pm_status} dispatch --state-root {pm_state_root} --event open \
  --agent bmad-dev-story --epic {epic_key} --sprint {sprint_num} --story {story_key} \
  --session-id {session_id}
```

Spawn `bmad-dev-story` subagent again with the findings and the changed files — not a fresh
read of the story tree. The same read scope as §2 applies, and a fix round starts from a
narrower position than the original: the reviewer already named the files and the sections.

```bash
python3 {pm_status} dispatch --state-root {pm_state_root} --event close \
  --agent bmad-dev-story --epic {epic_key} --sprint {sprint_num} --story {story_key} \
  --session-id {session_id}
```

Increment fix counter.

**Fix loop cap:** `{max_fix_iterations}` iterations per story (bound at
`step-01-classify-work.md` §5 — 3 for every work type). If findings persist
after `{max_fix_iterations}` iterations:
```
FAILED: story {story_key} — {N} critical/high findings unresolved after {max_fix_iterations} fix iterations.
```
Mark story `status: review` (not done) and continue to next story. Log the issue.

**If MEDIUM findings:** fix in current iteration (one more dev pass), then mark done.

**If LOW findings:** defer to issues file (do not re-develop):
```bash
python3 {pm_status} append-issue \
  --file {pm_issues_file} \
  --key BL-{epic_key}-{nnn} \
  --epic {epic_nnn} \
  --sprint {sprint_num} \
  --title "{finding_text}" \
  --source "code-review ({story_key})" \
  --severity Low
```

## 4. Write completion evidence and story actuals

When a story reaches done state:

**Completion evidence first — this order is load-bearing.** `set-actual` derives the
story's calibration sample inline, and that derivation reads
`completion_evidence.fix_iterations` to decide the sample's provenance (`exact` vs
`backout`) and which `fix` cohort the man-hours join. Writing `fix_iterations` after
`set-actual` means it is always absent at derivation time: `provenance: exact` becomes
unreachable, neither `fix` cohort ever fills, and the fix factor is frozen at the 1.25
cold-start prior forever — silently. See `references/metrics-contract.md` §8.

```bash
python3 {pm_status} set-field \
  --state-root {pm_state_root} \
  --story {story_key} \
  --field completion_evidence.fix_iterations \
  --value {fix_iterations}

python3 {pm_status} set-field \
  --state-root {pm_state_root} \
  --story {story_key} \
  --field completion_evidence.files_changed \
  --value {files_changed}
```

**Record what you ran, not what you concluded.** For every test command the story's scope
required — the suites covering the files this story changed, not only the ones you chose to
run — record the command and its real exit code:

```bash
python3 {pm_status} add-test-run --state-root {pm_state_root} --story {story_key} \
  --command "npm test" --exit-code 0
```

`completion_evidence.tests_passing` is derived from these and is no longer writable directly;
`set-field` refuses it. The required set comes from the story's scope: if the story changed a
file, the suite covering that file is required whether or not you ran it. A story once shipped
`tests_passing: true` having broken a suite it never ran, and the break was found two stories
later by accident.

**`man_hours` is a re-assessment, not an observation.** Bind `{man_hours}` from your own
judgment of what a developer, working without AI assistance, would have needed to implement
this story's delivered diff and tests — never a self-report of how long the dev/review
subagents actually ran (that figure is `{elapsed}`). See `references/metrics-contract.md` §2.
`{hitl_hours}` is the human attention actually spent supervising this story (observable).

Then write the actuals. Under `--runtime claude`, capture the four token classes from the
session transcript's `usage` fields (in thousands) and pass `--model`; `set-actual` derives
`cost` — never pass `--cost`, it is rejected. Under any other runtime, pass `--tokens-na` if
tokens are not observable:

```bash
python3 {pm_status} set-actual \
  --state-root {pm_state_root} \
  --node story \
  --story {story_key} \
  --runtime {runtime} \
  --elapsed-hours {elapsed} \
  --man-hours {man_hours} \
  --hitl-hours {hitl_hours} \
  --tokens-input {tokens_input} \
  --tokens-output {tokens_output} \
  --tokens-cache-write {tokens_cache_write} \
  --tokens-cache-read {tokens_cache_read} \
  --model {model} \
  [--token-rates '{token_rates_json}']
```

`{model}` and `{token_rates_json}` are bound at activation (`step-00-activate.md` §1) from
`modules.l3io-pm.default_model` / `.token_rates`. Pass `--model` always; add `--token-rates`
only when `{token_rates_json}` is non-empty, and pass the same override to any `verify` on
this node — `verify` re-derives `cost` and fails against the shipped rates otherwise.

`set-actual` prints what it sampled in a `[...]` suffix on its own stdout line — e.g.
`[scope+4 metrics, provenance=exact, class=complex]`. A `provenance=backout` on a story you
know needed no rework means `fix_iterations` did not reach the node before this call; a
`skipped (replay)` means this node already emitted its sample and the second call correctly
recorded nothing.

Mark story done:
```bash
python3 {pm_status} set-status \
  --state-root {pm_state_root} \
  --story {story_key} \
  --status done
```

Keep the story document in step with the state — the state YAML is what the machine reads and
this file is what a reviewer opens, and they have not agreed until now:

```bash
python3 {pm_status} sync-story-doc --artifacts-root {implementation_artifacts} \
  --story {story_key} --status done
```

This never fails: a missing or frontmatter-less document warns on stderr and returns 0, because
the state transition it follows is already durable and must not be rolled back by a
documentation write.

## 5. Output

```
Sprint Step 03 complete — stories done: {N}/{total}, fix iterations: {total_fix}, issues deferred: {N}
```
