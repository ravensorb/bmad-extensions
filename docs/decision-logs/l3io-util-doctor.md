---
skill: l3io-util-doctor
phase: complete
classification: simple-workflow
last_touched: 2026-06-15
---

> **Historical authoring record.** This log captures the decisions and rationale from the
> sessions that built this skill. It is kept for provenance and **may not describe current
> behaviour** — the live contracts are the repository's `CLAUDE.md` and this skill's
> `references/`. Where a later note below is marked "Correction," it was added after the
> fact next to the original entry; the original text is left as written.

# Decision Log

## Session 2026-05-15 — Initial Build

**Classification: Simple Workflow.** Full execution sequence fits in ~120 lines of SKILL.md. No workflow.md carve-out needed (threshold is 250 lines). Single file skill.
>
> **Correction (current behaviour):** this skill outgrew the single-file shape. It is now a
> **router**: `SKILL.md` carries the overview, keyword table, safety rules, and state layout,
> and each of its fourteen modes lives in its own `steps/` file loaded only when its keyword
> selects it (the modes were inlined once and `SKILL.md` reached 96,980 B). See `CLAUDE.md`
> § Module Layout.

**Config path: `{project-root}/_bmad/config.yaml` (l3io-util section).** Legacy skill used `{project-root}/_bmad/bmm/config.yaml`. Updated to the standard `{project-root}/_bmad/config.yaml` path for consistency with other l3io-* modules. `implementation_artifacts` and `planning_artifacts` are resolved from the standard BMad config, not a utility-specific config.
>
> **Correction (current behaviour):** there is no `{project-root}/_bmad/config.yaml` — that
> path was itself superseded. Config resolves through BMad core's `resolve_config.py`, which
> merges four TOML layers (`_bmad/config.toml`, `config.user.toml`, `custom/config.toml`,
> `custom/config.user.toml`) and prints `core.*` + `modules.<code>.*`. `implementation_artifacts`
> and `planning_artifacts` resolve from `modules.l3io-pm` for all four modules. See `CLAUDE.md`
> § Key Execution Contracts and this skill's `references/config-resolution.md`.

**No customize.toml customization surface.** Pure one-time utility — no behavior worth customizing via TOML. Minimal customize.toml with empty arrays only.

**Dry-run gate is non-negotiable.** Interactive only: always show the move plan and ask for confirmation before any file changes. A utility that moves files without review is dangerous.

**Classification heuristics extended from legacy.** Added new l3io-pm closure file patterns (`*-clean-release-*.md`, `*-ux-review-*.md`, `*-arch-drift-*.md`) beyond the legacy skill's patterns, since the new workflows produce additional file types. Sprint vs. epic closure disambiguation: sprint-scoped files have `sprint-{SS}` in the name; epic-scoped have `epic-{EE}` only.

**No subagents.** Sequential inline execution — no delegation needed. Simple file scan, print table, confirm, move, reconcile, verify, report.

**Ambiguous reference updates are never auto-applied.** Safety rule preserved from legacy: if one old path could map to multiple destinations or context is uncertain, record for manual review. Only exact 1:1 mappings are auto-updated.

## Session 2026-06-15 — Split Status Mode

**Added `split-status` mode (third mode).** The PM skills now use a three-file state layout
(`sprint-status-active.yaml` / `-backlog.yaml` / `-archived.yaml`) because a single
`sprint-status.yaml` grows large and slow to load on multi-epic projects. This mode is the
one-time, reviewed migration for existing repos; the PM skills also auto-split on first run
via their `references/status-files.md`. Inline procedure (no script), modeled on
`migrate-schema` — same dry-run-then-confirm gate.
>
> **Correction (current behaviour):** the three-file layout described here was itself
> superseded. The PM skills now use the sharded state tree — one directory per epic/sprint
> under `state/{planned,active,archived}/epic-{nnn}/...`, one bare node per file — not a
> flat three-file split. `split-status` survives only as a **legacy-only bridging mode** (a
> convenience shape for `reconcile-status` on the way to `migrate-state`); it is not the
> current target layout. See `CLAUDE.md` § Key Execution Contracts and this skill's
> `steps/split-status.md`, which already carries this correction.

**Partition granularity: epic + sprint, stories travel with their sprint.** Considered
story-level fragmentation (a `backlog` story inside an active sprint living in the backlog
file) but rejected it — it creates excessive churn during the per-story loop and complicates
reads. Once a sprint is active, all its stories live with it. Archive is **epic-close-only**
(done sprints stay in active until their epic closes); the active file holds only in-progress
epics, and all not-yet-started work (whole backlog epics + backlog sprints of active epics as
shells) lives in the backlog file. This matches the placement rule in the PM skills'
`status-files.md` — the two must stay in sync.

**One-way, original preserved.** The split renames the source to `sprint-status.yaml.legacy`
(never deletes) as the rollback. No automated re-merge — by design.
