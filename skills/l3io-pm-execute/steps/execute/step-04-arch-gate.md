# Step 04: Architecture Gate

Communicate all responses in `{communication_language}`.

Run a multi-reviewer architecture gate before any sprint executes. Skipped entirely for DOCS and CONFIG
work types, or when l3io-arch-review is not installed (gate never partially skips — minimum one reviewer
is required to run).

## 1. Gate eligibility check

Skip this step entirely and output `Step 04 skipped — work_type: {work_type}` if:
- `{work_type}` is `DOCS` or `CONFIG`

Check for l3io-arch-review installation:
```bash
grep -q "^l3io-arch:" {project-root}/_bmad/config.yaml 2>/dev/null && echo "present" || echo "absent"
```
If absent:
```
Step 04 skipped — l3io-arch-review not installed (required reviewer absent).
```
Halt step and continue to step-05.

## 2. Detect available reviewers

| Reviewer | Detection command |
|---|---|
| `l3io-arch-review` | Already confirmed present |
| `bmad-agent-architect` | `ls {project-root}/.claude/commands/bmad-agent-architect.md 2>/dev/null \|\| ls ~/.claude/commands/bmad-agent-architect.md 2>/dev/null` |
| superpowers | `ls {project-root}/.claude/commands/superpowers:requesting-code-review.md 2>/dev/null \|\| ls ~/.claude/commands/superpowers:requesting-code-review.md 2>/dev/null` |

Bind `{active_reviewers}` = list of detected reviewer names. Minimum: `[l3io-arch-review]`.

## 3. Collect story files for review

For each scoped epic key in `{scope_epic_keys}`:
```bash
ls {implementation_artifacts}/epic-{epic_nnn}/*/stories/*.md 2>/dev/null
```
Bind `{story_file_paths}` = full list of story markdown files across all sprints of the scoped epics.

## 4. Spawn reviewers in parallel

For each reviewer in `{active_reviewers}`, spawn a subagent in parallel. Each receives:
- Paths in `{story_file_paths}` (reads from disk)
- Epic goal and scope context
- l3io-pm context preamble (work_type, epic key, sprint plan)
- Reviewer-specific framing:
  - `l3io-arch-review`: invoke as Mode B (architectural review of existing design)
  - `bmad-agent-architect`: architect persona — design coherence, story quality, artifact completeness
  - superpowers: broad software architecture principles, independent of either framework

Each subagent returns a list of findings in format: `{severity}: {finding_text}`.

## 5. Consolidate findings (§9.3 rules)

Apply these rules to merge findings across reviewer outputs:

| Finding | Rule |
|---|---|
| BLOCKER from any reviewer | → BLOCKER. Never downgraded. |
| MAJOR from ≥2 reviewers | → MAJOR confirmed. Blocks execution. |
| MAJOR from 1 reviewer | → MAJOR flagged (single-source). Still blocks. |
| MINOR from ≥2 reviewers | → MINOR confirmed. Deferred to issues file. |
| MINOR from 1 reviewer | → Auto-deferred to issues file. Not a gate finding. |

Annotate each consolidated finding with its source reviewer(s).

## 6. Gate outcome

**If BLOCKER or MAJOR findings exist:**

For each blocking finding, spawn an ADR resolution subagent:
- Read the affected story files
- Draft an ADR at `{implementation_artifacts}/epic-{epic_nnn}/arch/adr-{nnn}-{slug}.md`
- Patch affected story files with technical ACs implied by the ADR decision
- Return: `ADR written: {path}`

After all ADRs are written, re-validate the same story files with all reviewers (one more pass).
If blocking findings persist after one resolution pass:
```
BLOCKED: arch gate — {N} blocking findings unresolved after ADR resolution.
```

**If MINOR findings only:**

For each MINOR finding, append to issues file:
```bash
python3 {pm_status} append-issue \
  --file {bmad_issues_file} \
  --key BL-{epic_key}-{nnn} \
  --epic {epic_nnn} \
  --sprint "" \
  --title "{finding_text}" \
  --source "arch-gate ({reviewer})" \
  --severity Low
```
Output: `Step 04 complete — findings: 0 blocking, {N} deferred to issues`

**If no findings on non-trivial CODE scope:**

Output:
```
⚠️  Arch gate found zero findings on CODE scope. This is unusual.
   Confirm before continuing: (y/n)
```
Wait for user confirmation.

## 7. Output

```
Step 04 complete — reviewers: {active_reviewers}, blocking: {N}, deferred: {N}
```
