# Upgrading

Version-to-version upgrade notes for `bmad-l3io-extensions`, plus the one command that
handles data migration.

**The installer refreshes skills. It does not migrate your data.** Those are separate steps,
and skipping the second is the single most common way to end up with a project the skills
cannot read.

## The short version

```bash
# 1. Refresh the skills
npx bmad-method install --directory . --action quick-update --yes

# 2. Migrate the data — once, before any sprint or epic run
/l3io-util-doctor
```

Your `_bmad/custom/config.toml` and `config.user.toml` overrides survive step 1 untouched —
the installer never writes those layers.

## Why step 2 matters

`/l3io-util-doctor` with no argument inspects the project, reports what it finds, and proposes
every applicable migration **in dependency order** behind a single confirmation. It runs only
the steps your project actually needs.

The full ordered sequence:

```
rename-active → rename-epic-dirs → migrate-schema → split-status → migrate-state
  → reconcile-status → layout-cleanup → sort-status → harvest-debt
  → update-ai-rules → clean-legacy
```

`migrate-state` is the pivot. It is what produces the sharded `state/` tree that 2.0.1+ skills
read; every step before it only prepares its input, and every step after it operates on the
result.

> **Do not run the individual modes by hand unless you know exactly which you need.** Stopping
> before `migrate-state` leaves the project in a layout the PM skills cannot read — and the
> earlier steps each report success on their own, so a partial run looks like a completed one.

The skill is the authority on this sequence. If this document and
`/l3io-util-doctor` ever disagree, the skill is correct and this file is stale.

## Version notes

Find your starting version and read forward. `npx bmad-method install` upgrades across any
number of these at once, but the migrations must still run.

### → 2.1.0

**`l3io-util-cleanup` was renamed to `l3io-util-doctor`.** "Cleanup" described about three of
its fifteen modes, while the default behavior is a diagnose-report-repair health check.

Backward compatible — no action required. `/l3io-util-cleanup` still works: it prints a rename
notice and forwards. Update any scripts, aliases, or team docs that invoke the old name; it is
deprecated and will be removed in a future major release.

**New: progress reporting.** `/l3io-pm-help progress` and `/l3io-util-doctor stats` render a
plan-aware tree — which phase, epic, sprint, and stories are in flight. Nothing to migrate, but
one thing to know: per-status dwell times display with a `~` prefix until
`{implementation_artifacts}/state/events.jsonl` accumulates transitions. Before then they are
derived from `updated_at` and are approximate. The log starts recording on your next
`/l3io-pm-execute` run. See [Progress Reporting](l3io-pm-reference.md#progress-reporting).

### From 2.0.0 → 2.0.1+

**State relocated from `{project-root}/_bmad/state/` to `{implementation_artifacts}/state/`,
and sharded into one file per node.** `_bmad/` is installer-owned and gitignored, so state
living there was never committed — which defeated the point of tracking it.

Run `/l3io-util-doctor` (it will flag `migrate-state`). The original tree is preserved as
`_bmad/state.legacy/`.

### From 1.x → 2.x

The largest jump. Several things changed at once in 2.0.0:

| 1.x | 2.x |
|---|---|
| `/l3io-pm-plan-execution` | `/l3io-pm-plan` |
| `/l3io-pm-sprint-execute` | `/l3io-pm-execute E{nnn}-S{nn}` |
| `/l3io-pm-epic-execute` | `/l3io-pm-execute E{nnn}` |
| `/l3io-sec-agent-redteam` | `/l3io-sec-redteam` |
| flat `sprint-status.yaml` (or the three-file split) | sharded `state/` tree, one file per node |
| nested `src/<module>/<skill>/` | flat `skills/<skill>/` |

Sprint and epic execution **merged into one skill**. `/l3io-pm-execute` takes a scope argument
— no argument runs the whole plan in phase order, `E001` runs one epic, `E001-S01` one sprint.
There is no separate sprint or epic skill to invoke.

Also new in 2.x: `/l3io-pm-help` (state snapshot and next-action recommendation) and
`/l3io-pm-sync` (bidirectional GitHub Issues sync).

Node schema changed with sharding: nodes are stored **bare**, with no `epics:` or `stories:`
list wrapper, and keys are zero-padded (`E001`, `S01`, `E001-S01-001` — not `E1`, `1-0`).
Children are discovered by listing the directory. `migrate-state` handles the conversion; you
do not hand-edit it.

If your sanctum lived at `_bmad/memory/l3io-sec-agent-redteam/`, the current path is
`_bmad/memory/l3io-sec-redteam/`.

### From before 1.0.20

Status files were named `sprint-status-active.yaml`. `/l3io-util-doctor` detects this and runs
`rename-active` automatically as the first step of the sequence — you do not need to invoke it
yourself, and invoking it alone is not enough, because a renamed flat file is still a legacy
layout.

## Verifying the upgrade

```
/l3io-util-doctor check     # read-only: confirms nothing is left flagged
/l3io-pm-help               # confirms state resolves and recommends the next action
```

`/l3io-pm-help` also warns if `state/` is gitignored — worth checking after a migration, since
state that is not committed defeats the layout.

## Backups and rollback

Every one-time migration preserves what it replaced:

| Backup | Left by |
|---|---|
| `*.yaml.legacy` | `split-status`, `migrate-state` |
| `_bmad/state.legacy/` | `migrate-state` (per-epic → sharded) |
| `_bmad/pm-calibration.yaml.legacy` | `migrate-state` |
| `pm-calibration.yaml.v1` | first calibration write after a v1 → v2 schema migration |
| `_bmad/migration-backup/` | `migrate-state` Stage F, when you pick its default "move" option |

Nothing deletes these automatically. Once you have verified the result, remove them with:

```
/l3io-util-doctor clean-legacy
```

It dry-runs first and confirms before deleting.

## Deprecations

| Deprecated | Since | Replacement | Removal |
|---|---|---|---|
| `/l3io-util-cleanup` | 2.1.0 | `/l3io-util-doctor` | a future major release |
| `migrate-schema`, `split-status`, `reconcile-status` | — | legacy-only bridging modes; no longer reachable once `migrate-state` has run | when 1.x migration support is dropped |
| `pm-status.py progress --ledger` | 2.3.0 (script version) | automatic `state/events.jsonl` appends | not yet scheduled |
