# Step 01: Classify Work Type

Communicate all responses in `{communication_language}`.

Run after step-00-activate. Determines `{work_type}` for all in-scope epics/stories
before any orchestration begins. `{work_type}` is carried in all subsequent step
instructions and every headless subagent prompt.

---

## Classification rules

Examine the stories in scope (those in the active epics or the epics being planned):

| Type | Condition |
|------|-----------|
| `CODE` | At least one story has implementation ACs (code changes, APIs, services, data model) |
| `DOCS` | All stories are documentation only (no code or infrastructure changes) |
| `CONFIG` | All stories are infrastructure, CI/CD, configuration, or IaC only |
| `MIXED` | Stories span more than one type (e.g. both CODE and DOCS stories in same scope) |

## Classification procedure

1. For each in-scope story (read from story files in `{implementation_artifacts}` or from
   the status file if story files are absent):
   - Read the story's `classification` field if present. Classifications are:
     - `simple`, `standard`, `complex` → these describe sizing, not type. Read the story's
       Acceptance Criteria to determine type.
   - If the story file exists, read its "Acceptance Criteria" section.
   - Assign a type: CODE, DOCS, CONFIG, or MIXED (a single story can be MIXED if its ACs
     span multiple types).

2. Aggregate across all in-scope stories:
   - All DOCS → `{work_type}` = DOCS
   - All CONFIG → `{work_type}` = CONFIG
   - Mix of CODE + anything else → `{work_type}` = MIXED
   - Any CODE (even one story) → `{work_type}` = CODE (if rest are also CODE or unclassified)
   - Unclassifiable stories (no ACs at all) → treat as CODE (conservative default)

3. Bind `{work_type}` for all subsequent steps.

4. Compute `{skip_phases}` from the conditional phase table:

| Phase | Skip when |
|-------|-----------|
| Story technical-AC gate | `{work_type}` is DOCS or CONFIG |
| Arch gate (epic level) | `{work_type}` is DOCS or CONFIG, or l3io-arch-review not installed |
| Adversarial analysis | `{work_type}` is DOCS or CONFIG |
| Red team (l3io-sec) | `{work_type}` is DOCS or CONFIG, or l3io-sec not installed |
| UX review | `{work_type}` is CONFIG |
| ATDD scaffold | `{work_type}` is DOCS or CONFIG, or bmad-testarch-atdd not installed |

Bind `{skip_phases}` = comma-separated list of phase names to skip (empty if none).

To check if a skill is installed:
- `l3io-arch-review`: `_bmad/config.yaml` contains an `l3io-arch:` section (run:
  `grep -q "^l3io-arch:" {project-root}/_bmad/config.yaml 2>/dev/null && echo "present" || echo "absent"`)
- `l3io-sec-redteam`: `_bmad/config.yaml` contains an `l3io-sec:` section (run:
  `grep -q "^l3io-sec:" {project-root}/_bmad/config.yaml 2>/dev/null && echo "present" || echo "absent"`)
- `bmad-testarch-atdd`: command file exists at project or user level (run:
  `ls {project-root}/.claude/commands/bmad-testarch-atdd.md 2>/dev/null || ls ~/.claude/commands/bmad-testarch-atdd.md 2>/dev/null || echo "absent"`)

## Output

Report the classification result:

```
Work type: {work_type}
Skipping phases: {skip_phases or "(none)"}
Rationale: [one sentence explaining the dominant story type]
```

Then continue to the next step.
