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

Spawn `bmad-dev-story` subagent with:
- Story file path: `{sprint_root}/stories/{story_key}.md`
- Project context: `{project-root}/_bmad/config.yaml`
- Sprint root: `{sprint_root}`

On completion, collect: files changed, tests passing (boolean), fix iterations attempted.

## 3. For each story: code review (CODE and MIXED only)

Skip if `{work_type}` is DOCS or CONFIG.

Spawn `bmad-code-review` subagent with:
- Story file path
- Files changed by dev subagent

Code review returns findings by severity.

**If CRITICAL or HIGH findings:** spawn dev subagent again to fix (fix iteration). Increment fix counter.

**Fix loop cap:** 10 iterations per story. If findings persist after 10 iterations:
```
FAILED: story {story_key} — {N} critical/high findings unresolved after 10 fix iterations.
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

## 4. Write story actuals and completion evidence

When a story reaches done state:

```bash
python3 {pm_status} set-actual \
  --state-root {pm_state_root} \
  --node story \
  --story {story_key} \
  --runtime {runtime} \
  --elapsed-hours {elapsed} \
  --man-hours {man_hours} \
  --tokens-k {tokens_k} \
  --cost {cost}
```

Write completion evidence via set-field:
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
