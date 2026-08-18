# Sprint Step 03: Development Loop

Communicate all responses in `{communication_language}`.

Execute each story in the sprint: develop, code review, iterate on fixes. Write actuals and
completion evidence when done.

## 1. Story iteration order

Process stories from `{story_keys}` in order. Stories with `depends_on` entries must wait until
all referenced story keys are `status: done` (check each referenced story's own node file —
`python3 {pm_status} show --state-root {pm_state_root} --epic {epic_key} --sprint {sprint_num}`
lists every story in this sprint with its status — before starting each).

If a dependency story is not done and is not in this sprint's `{story_keys}`, log:
```
⚠️  Story {story_key} depends on {dep_key} which is not done — skipping until dep resolves.
```
Move the blocked story to the end of the queue.

## 2. For each story: develop

Mark story in-progress:
```bash
python3 {pm_status} set-status \
  --state-root {pm_state_root} \
  --story {story_key} \
  --status in-progress
```

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

Spawn `bmad-dev-story` subagent with:
- Story file path: `{sprint_root}/stories/{story_key}.md`
- Project context: the config resolved at activation (`references/config-resolution.md`) —
  pass the bound values, not a config file path
- Sprint root: `{sprint_root}`
- **You have no inbox.** No reply will arrive. If you need a decision you cannot
  make, write it to disk and end with `BLOCKED: <reason>`. Never wait.
- Your final line must be exactly one of `DONE — [brief metrics]`,
  `BLOCKED: [one-line reason]`, or `FAILED: [one-line reason]`.

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

Spawn `bmad-code-review` subagent with:
- Story file path
- Files changed by dev subagent
- **You have no inbox.** No reply will arrive. If you need a decision you cannot
  make, write it to disk and end with `BLOCKED: <reason>`. Never wait.
- Your final line must be exactly one of `DONE — [brief metrics]`,
  `BLOCKED: [one-line reason]`, or `FAILED: [one-line reason]`.

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

Spawn `bmad-dev-story` subagent again with the code review findings to fix.

```bash
python3 {pm_status} dispatch --state-root {pm_state_root} --event close \
  --agent bmad-dev-story --epic {epic_key} --sprint {sprint_num} --story {story_key} \
  --session-id {session_id}
```

Increment fix counter.

**Fix loop cap:** `{max_fix_iterations}` iterations per story (bound at
`step-01-classify-work.md` §5 — 10 for CODE/MIXED, 3 for DOCS/CONFIG). If findings persist
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
  --field completion_evidence.tests_passing \
  --value {tests_passing}

python3 {pm_status} set-field \
  --state-root {pm_state_root} \
  --story {story_key} \
  --field completion_evidence.files_changed \
  --value {files_changed}
```

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
  --model {model}
```

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

## 5. Output

```
Sprint Step 03 complete — stories done: {N}/{total}, fix iterations: {total_fix}, issues deferred: {N}
```
