# Sprint Closure Workflow

Communicate all responses in `{communication_language}`.

This file is loaded by step-04-sprint-closure.md. Run each phase; skip phases listed in
`{skip_phases}`.

## Phase table (§8)

| Phase | CODE | DOCS | CONFIG | MIXED |
|---|---|---|---|---|
| Retrospective | run | run | run | run |
| Clean release review | run | skip | run | run |
| Adversarial analysis | run | skip | skip | run |
| Red team (l3io-sec) | run | skip | skip | run |
| UX review | run | run | skip | run |
| Architectural drift | run | skip | run | run |
| Issue triage | run | run | run | run |

## 1. Retrospective

Spawn `bmad-retrospective` (or inline if not installed):
- Summarize stories completed, velocity vs estimate, blockers encountered
- Produce `retrospective_summary` (2–3 sentences) and `carry_over_count`
- Write report to `{sprint_root}/closure/retrospective.md`

## 2. Clean release review (skip if in skip_phases)

Invoke `bmad-review-adversarial-general` with scope `clean-release`:
- Check for dead code, commented-out code, debug artifacts, TODO markers
- Check for secrets or credentials in changed files
- CRITICAL/HIGH: fix immediately (re-invoke dev subagent). MEDIUM/LOW: defer to issues.

## 3. Adversarial analysis (skip if in skip_phases)

Invoke `bmad-review-adversarial-general` with scope `adversarial`:
- Threat-model the sprint's changes
- CRITICAL/HIGH: block closure, fix loop (max 10 iterations). MEDIUM: fix in place. LOW: defer.

## 4. Red team (skip if in skip_phases)

If `l3io-sec-redteam` is installed:
```bash
grep -q "^l3io-sec:" {project-root}/_bmad/config.yaml 2>/dev/null && echo "present" || echo "absent"
```
If present: spawn l3io-sec-redteam with the sprint's changed files.
CRITICAL/HIGH findings: block until resolved. LOW: defer to issues file.

## 5. UX review (skip if in skip_phases)

If `bmad-ux-review` is installed and sprint has UI-facing stories:
```bash
ls {project-root}/.claude/commands/bmad-ux-review.md 2>/dev/null \
  || ls ~/.claude/commands/bmad-ux-review.md 2>/dev/null \
  || echo "absent"
```
If present: invoke with story files that have UX acceptance criteria.
HIGH: fix. LOW/MEDIUM: defer.

## 6. Architectural drift review (skip if in skip_phases)

If `l3io-arch-review` is installed: invoke Mode C (audit) on this sprint's stories and changed files.
CRITICAL/HIGH/MEDIUM: resolve before marking sprint done. LOW: defer to issues file.

## 7. Issue triage

Collect all Low severity issues found across phases 2–6. For each:

```bash
python3 {pm_status} append-issue \
  --file {bmad_issues_file} \
  --key BL-{epic_key}-{nnn} \
  --epic {epic_nnn} \
  --sprint {sprint_num} \
  --title "{issue_title}" \
  --source "{phase} ({finding_id})" \
  --severity Low
```

Write closure summary to `{sprint_root}/closure/closure-report.md`:
- Stories done, estimates vs actuals
- Issues resolved: count by severity
- Issues deferred: count by severity
- Phases run vs skipped
