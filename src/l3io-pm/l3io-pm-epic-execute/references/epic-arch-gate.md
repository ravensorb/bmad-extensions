# Epic Architecture Gate (pre-execution)

Communicate all responses in `{communication_language}`.

**Purpose.** Close architecture gaps and assumptions **before** any sprint runs, instead of discovering them as implementation churn and a full post-hoc review at closure. This gate reviews the whole epic's design against the LiquidLogicLabs engineering standards and blocks execution on load-bearing findings, recording the decisions (ADRs) and pushing the resulting technical constraints down into the story files the sprints will implement.

**When it runs.** After **Epic Planning (Step 1)** — sprint grouping confirmed, epic promoted to `{status_active}` — and **before** the sprint execution loop (`references/sprint-execution-loop.md`).

**Config.** Bind `epic_arch_gate` = `{workflow.epic_arch_gate}` (default `true`) at activation. If `false`, skip this gate entirely and proceed to the sprint loop (announce the skip once).

**Dependency check.** Confirm `l3io-arch-review` is installed — look for `.claude/skills/l3io-arch-review/SKILL.md` or `.claude/commands/l3io-arch-review.md`. If absent: announce "l3io-arch-review not installed — epic architecture gate skipped", log the skip to `{progress_ledger}`, and proceed to the sprint loop. (This mirrors the optional `l3io-sec-agent-redteam` skip pattern.)

---

## Step 1a — Architecture Review (Mode B)

Announce: "Epic Architecture Gate — reviewing Epic {target_epic} design before execution." Append to `{progress_ledger}`.

Spawn a subagent:
```
Load config from: {config_file}
Load project context from: {context_file} (if it exists)
Planning inputs (load fully if present, skip gracefully if absent):
  - Architecture: {arch_file}
  - PRD: {prd_file}
  - Epics: {epics_file}
Epic story files: all story files for Epic {target_epic} under {planning_epic_dir} and existing story directories (pass their paths).
Invoke skill: l3io-arch-review
Mode: B (architectural review). Scope: the full design of Epic {target_epic} — its stories as a cohesive increment, not story by story.
Assess every loaded standards principle. For each finding state: severity (BLOCKER / MAJOR / MINOR) · principle · location · concrete remediation.
Pay explicit attention to gaps and unstated assumptions that would otherwise be resolved ad hoc by individual dev agents: undefined interfaces/contracts, missing error/edge handling expectations, unspecified data models, absent NFR/observability/security targets, and technology/pattern choices left open.
Write the report to: {epic_closure_dir}/../epic-arch-gate-{date}.md   (i.e. {epic_root_dir}/epic-arch-gate-{date}.md)
Print when done: DONE — Blocker: N, Major: N, Minor: N, Report: [path] | BLOCKED: [reason] | FAILED: [reason]
```

Record `{arch_blocker}`, `{arch_major}`, `{arch_minor}`, and `{arch_report_path}` from the status line. Halt on BLOCKED/FAILED — report to `{user_name}`.

---

## Step 1b — Gate Decision

**Gate rule:** BLOCKER and MAJOR findings must be resolved or ADR-justified before execution; MINOR auto-defers to the backlog (it never blocks).

If `{arch_blocker}` == 0 and `{arch_major}` == 0:
- Announce: "Epic Architecture Gate — clean (no Blocker/Major). {arch_minor} minor finding(s) deferred to backlog." Log to `{progress_ledger}`.
- Route each MINOR to the consolidated backlog in `{status_backlog}` per `references/status-files.md` → *Consolidated backlog item schema* (`source: 'arch-gate ({finding_id})'`, `severity: Low`).
- Proceed to the sprint execution loop.

If `{arch_blocker}` > 0 or `{arch_major}` > 0, resolve them autonomously (no per-finding prompt), then re-gate. For each Blocker/Major finding, spawn a resolution subagent:
```
Load config from: {config_file}
Load project context from: {context_file} (if it exists)
Arch gate report: {arch_report_path}
Finding to resolve: {finding_id} — {finding_title} ({severity}) · principle · location · remediation
Invoke skill: l3io-arch-review
Mode: C (decision support). Weigh the option(s) for this finding against the principle in tension, decide, and record an ADR under {project-root}/docs/adr/ using the skill's adr-template.
Then propagate the decision into the affected Epic {target_epic} story file(s): add or tighten the technical acceptance criteria the decision implies (interface/contract, data model, error/edge handling, NFR/observability/security target, or technology/pattern constraint). Edit the story files in place.
Print when done: DONE — ADR: [path], stories updated: [keys] | BLOCKED: [reason] | FAILED: [reason]
```

Record each ADR path and the updated story keys. Because the resolution patches story files with concrete technical ACs, it also directly serves the story-level gap (the sprint's technical-AC gate will find these already present).

**Re-gate:** after all Blocker/Major findings are addressed, either (a) re-run Step 1a scoped to the changed artifacts to confirm they now pass, or (b) if every finding was ADR-justified rather than code-changed, record the ADR justifications and consider the gate satisfied. Do not enter the sprint loop while any Blocker/Major finding is unresolved and un-justified.

**Escalation:** if a finding cannot be resolved autonomously after one resolution pass (genuine design ambiguity needing a human call), halt and report to `{user_name}` with the finding, the options weighed, and the ADR draft — wait for the decision before proceeding. This is the one place the epic gate may pause.

---

## Output

- Arch gate report → `{epic_root_dir}/epic-arch-gate-{date}.md`
- ADRs → `{project-root}/docs/adr/`
- Story files patched in place with technical ACs
- MINOR findings → consolidated backlog in `{status_backlog}`

Log the gate outcome to `{progress_ledger}` and announce a one-line summary before entering the sprint loop:
```
Epic Architecture Gate — PASS: {arch_blocker+arch_major} blocking finding(s) resolved ({adr_count} ADRs, {stories_patched} stories patched), {arch_minor} minor deferred. Entering sprint execution.
```
