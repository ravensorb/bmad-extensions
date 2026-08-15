# Epic Closure Workflow

Communicate all responses in `{communication_language}`.

This file is loaded by step-06-epic-closure.md. Run each section in order.

## 1. Retrospective

Spawn `bmad-retrospective` (or inline if not installed):
- Review all sprint retrospectives for this epic
- Summarize velocity, recurring pain points, and process improvements
- Identify top 3 learnings to carry forward

Produce:
- `retrospective_summary` (2–4 sentences)
- `retrospective_learnings` (bullet list, max 5 items)

Write retrospective report to `{implementation_artifacts}/epic-{epic_nnn}/epic-closure/retrospective.md`.

## 2. Architectural drift review

Run only if `{work_type}` is CODE or MIXED AND `l3io-arch-review` is installed.

```bash
grep -q "^l3io-arch:" {project-root}/_bmad/config.yaml 2>/dev/null && echo "present" || echo "absent"
```

If present: invoke l3io-arch-review Mode C (audit — review what was built vs what was planned).
Pass:
- ADR paths: `{implementation_artifacts}/epic-{epic_nnn}/arch/*.md`
- Story file paths: `{implementation_artifacts}/epic-{epic_nnn}/*/stories/*.md`

Findings:
- CRITICAL/HIGH/MEDIUM: must be resolved before closure completes. Open fix loop (max 10 iterations).
- LOW: append to issues file via `pm-status.py append-issue`.

## 3. Issue triage

Collect all Low severity issues identified during the epic's sprint closures (already in issues file).
Review for any that should be promoted to Medium/High given the full epic context.

For any promoted items: update severity in the issues file (re-write the item via `append-issue`
after removing the old entry manually, or note for the implementer to do so in-place).

Output triage summary: count of issues by severity, count promoted.

## 4. Closure report

Write `{implementation_artifacts}/epic-{epic_nnn}/epic-closure/closure-report.md` containing:
- Epic goal and final status
- Estimate vs actual table (all four metrics)
- Sprint velocity summary
- Retrospective learnings
- Outstanding issues count (by severity)
- ADRs produced (if any)
