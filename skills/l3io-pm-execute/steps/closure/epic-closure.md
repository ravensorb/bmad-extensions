# Epic Closure Workflow

Communicate all responses in `{communication_language}`.

This file is loaded by step-06-epic-closure.md. Run each section in order.

## Dispatch rule for every spawn in this file

Every phase below that spawns or invokes a subagent — retrospective, adversarial review,
red team, UX, arch drift, and any fix-loop re-dispatch — brackets it with
`dispatch --event open` / `--event close`, same `--agent <name> --epic {epic_key}
--session-id {session_id}` identity on both, closed on **every** exit path.

Include `{agent_contract}` (verbatim — see `step-00-activate.md` §8) in every spawn prompt.
These are `bmad-*` and `l3io-*` agents that load no part of the activation digest; without it
they have no instruction to stop rather than wait.

Attribution is unchanged by the bracket: closure phases are **closure** spend, added on top of
the children's sum in the epic's own `actual` — never a child's `actual` and never
`orchestration` (`references/metrics-contract.md` §6). The bracket here buys stall detection,
not a change of bucket.

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
grep -qE "^[[:space:]]*-[[:space:]]*name:[[:space:]]*l3io-arch[[:space:]]*$" \
  {project-root}/_bmad/_config/manifest.yaml 2>/dev/null && echo "present" || echo "absent"
```

If present: invoke l3io-arch-review Mode C (audit — review what was built vs what was planned).
Pass:
- ADR paths: `{implementation_artifacts}/epic-{epic_nnn}/arch/*.md`
- Story file paths: `{implementation_artifacts}/epic-{epic_nnn}/*/stories/*.md`

Findings:
- CRITICAL/HIGH/MEDIUM: must be resolved before closure completes. Open fix loop (max `{max_fix_iterations}` iterations).
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
- Estimate vs actual table (all five metrics)
- Sprint velocity summary
- Retrospective learnings
- Outstanding issues count (by severity)
- ADRs produced (if any)

## 5. Progress render and report regeneration

Epic closure runs once per epic, after all of its sprints have finished, so it is not competing
with sibling sprints for stdout — render unconditionally:

```bash
python3 {pm_status} report \
  --state-root {pm_state_root} \
  --plan {planning_artifacts}/plan-output-meta.yaml \
  --format tree

python3 {pm_status} report \
  --state-root {pm_state_root} \
  --plan {planning_artifacts}/plan-output-meta.yaml \
  --format md --out {implementation_artifacts}/progress-report.md
```

Print the tree verbatim. Both commands are read-only with respect to state; a failure in either
is a reporting problem — note it in one line and continue rather than failing epic closure.
