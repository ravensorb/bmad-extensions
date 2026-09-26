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

# 2. Migrate the data and refresh the installed pm-status.py — required after every update,
#    not just once at first migration
/l3io-util-doctor
```

Your `_bmad/custom/config.toml` and `config.user.toml` overrides survive step 1 untouched —
the installer never writes those layers.

**Step 2 is required after every skill update, not optional and not one-time.** Step 1
refreshes the skill payloads under `skills/`, but your project's on-disk data is untouched by
a skill refresh, and `/l3io-util-doctor` is the one command that inspects it and applies every
migration you need, in dependency order, behind one confirmation. It also self-installs the
current `pm-status.py` at activation, before it does anything else — but that part is not
unique to it: `l3io-pm-execute`, `l3io-pm-plan`, and `l3io-pm-sync` each self-install the same
current copy at their own activation too (content-guarded — it reinstalls only when the
installed copy differs from the current skills), so a stale script would also self-heal on
your next run of any of those. Migration is what a self-heal never does. Skipping
`/l3io-util-doctor` after an update leaves any migration your project needs undone: a
subcommand the new payloads assume (a newly optional flag, a newly added subcommand) then
fails with a plain argparse error that gives no hint the real cause is a missed migration, or
the run proceeds against a layout the current skills cannot correctly read.

## Why step 2 matters

`/l3io-util-doctor` with no argument inspects the project, reports what it finds, and proposes
every applicable migration **in dependency order** behind a single confirmation. It runs only
the steps your project actually needs.

The full ordered sequence:

```
rename-active → rename-epic-dirs → migrate-schema → split-status → migrate-state
  → bootstrap-state → reconcile-status → layout-cleanup → sort-status → harvest-debt
  → migrate-adrs → triage → update-ai-rules → redrive → untrack-locks → clean-legacy
```

`migrate-state` is the pivot. It is what produces the sharded `state/` tree that 2.0.1+ skills
read; every step before it only prepares its input, and every step after it operates on the
result.

> **Do not run the individual modes by hand unless you know exactly which you need.** Stopping
> before `migrate-state` leaves the project in a layout the PM skills cannot read — and the
> earlier steps each report success on their own, so a partial run looks like a completed one.

The skill is the authority on this sequence. If this document and
`/l3io-util-doctor` ever disagree, the skill is correct and this file is stale.

## Upgrade between runs

Self-install converges every project to one byte-identical `pm-status.py`, but only for
processes that start **after** it runs. A `pm-status.py` invocation already in flight when the
upgrade lands keeps running the copy it loaded — it does not pick up a mid-flight file
replacement.

This matters for locking specifically: an epic's lock file lives at a fixed path per
`pm-status.py` version, and that path was relocated (from inside the epic's own directory to
`{state_root}/epic-NNN.lock`) so it survives a `move-epic`/`archive-epic` `git mv`. A
pre-upgrade process and a post-upgrade process therefore do not lock the *same file* for the
same epic during the transition window, and so do not exclude each other, even though both
believe they hold "the" epic lock.

Concretely: if `l3io-pm-execute` sprint agents are mid-flight on the pre-upgrade copy while
`/l3io-util-doctor` — which self-installs at activation, before dispatching to any mode — runs
and refreshes `pm-status.py` mid-session, the doctor's own writes (and anything dispatched
after it) use the new lock path and will not wait behind the still-running agents' lock, and
vice versa. This is a narrow, self-resolving window: once every process still running has
exited, every subsequent invocation loads the same, current copy and locks the same file. It
is not a reason to avoid running `/l3io-util-doctor` between runs — it is a reason not to run
it, or any manual `pm-status.py` write, against an epic another session is actively executing.

## Lock files leave git

`pm-status.py`'s lock files are empty flock targets: `epic-NNN.lock`, `issues.yaml.lock`,
`pm-calibration.yaml.lock`, `adr-register.yaml.lock` and `.notices.yaml.lock` in
`{implementation_artifacts}/state/`, plus a `.yaml.lock` sidecar beside some node files. The
sprint-closure checkpoint used to commit them. `pm-status.py` now keeps both `*.lock` and the
`.notices.yaml` advisory ledger (§ notice) in `state/.gitignore`, so an existing project sees
two things after upgrading. Both are expected:

- **A new `state/.gitignore`.** The first `pm-status.py` command that takes a lock inside the
  state root writes it,
  and the checkpoint commits it with the rest of `state/`. If a `.gitignore` is already there,
  it keeps its lines and gains whichever of the `*.lock` and `.notices.yaml` lines it is
  missing — an already-current file gains nothing.
- **A commit that deletes the tracked `*.lock` files from git.** The next sprint-closure
  checkpoint untracks them. `/l3io-util-doctor`'s health check does the same (Check 14) and
  stages the removal for you to commit. The files stay on disk; only the index entries go.

The activation gate that refuses a gitignored `state/` is unaffected, because neither `*.lock`
nor `.notices.yaml` matches the directory itself.

## Version notes

Find your starting version and read forward. `npx bmad-method install` upgrades across any
number of these at once, but the migrations must still run.

### → the next release (merged to `main`, not yet tagged)

> **These changes are not in a release yet.** They are merged to `main`; the current release
> is 3.0.0. The next cut is **3.0.1** — released as a patch rather than a minor bump because
> the additive shipments here (list-epics/list-stories read verbs, extras carry-through in
> migrations, additive bootstrap on partial state) are low-risk refinements on top of the
> 3.0.0 architecture rather than a new-shape release.

**No consumer-side migration is required, with one thing to know.** The items below are
additive, but if you are coming from a **pre-3.0 backlog**, see "legacy `deferred` statuses"
below — nothing breaks, and `triage` now offers a one-pass repair instead of several hundred
findings you cannot act on.

**`migrate-adrs` no longer renumbers an ADR you already migrated.** *If you ran, or were about
to run, `migrate-adrs` on a project whose ADRs are already in `docs/adr/`, read this.* The
collision test compared ADR numbers only, so a leftover copy under `epic-*/arch/` of an ADR
already in `docs/adr/` was read as a competing decision and minted under a brand-new number,
with that epic's artifacts rewritten to cite the invented one. On one real project all 14
legacy ADRs were such leftovers, so the run would have created 14 duplicate ADRs and reported
success. A same-number **and same-slug** file is now classified `duplicate`: never moved, never
renumbered, only reported for you to diff and delete. `--apply` on an all-duplicate project is
now a measured no-op — no commit, no number reserved. **Health Check 15 also stopped
recommending the run**, which it previously did to exactly the projects it would harm.

**Legacy `deferred` statuses now have a migration.** Pre-3.0, `deferred` was the resting state
for a deliberately deferred item. `OPEN_ISSUE_STATUSES` is now `(backlog, scheduled)`, so every
such item became an integrity finding (`audit-issues` id `1f`) whose repair text was the literal
string "report only" — one real upgrade produced **453** of them, and `triage` completed having
repaired none. Those items were never at risk; they were just unactionable. Fix them in one
pass:

```bash
uv run {project-root}/_bmad/scripts/pm-status.py repair-issue \
  --state-root {implementation_artifacts}/state --action normalize-status --all-legacy
```

`deferred` maps to `backlog` — open and unscheduled. Nothing is closed and no
`issues-resolved.yaml` is created. A status that is not a known legacy value is refused rather
than guessed, and `triage` offers this command itself when it sees more than a handful.

**It refuses outright if your backlog holds BOTH `deferred` and `backlog` items**, and you should
not work around that. Coexistence is evidence the two meant different things in your project —
typically `deferred` as a *disposition* ("we looked at this and decided not now") against
`backlog` as undecided. Neither current open status carries a decision, so the mapping cannot
preserve one: it would silently convert "we decided" into "nobody decided".

> Found the hard way on a real upgrade: 453 `deferred` alongside 64 `backlog`, of which **444
> sat behind CLOSED epics**. Normalising them turned every one into an undecided finding behind
> a closed epic, and that project's own guard — which refuses to close an epic over an
> undecided finding — went red. A project without such a guard would have taken the loss in
> silence. The items were never at risk; the **decision attached to them** was.

If you hit the refusal, the backlog stays as it is and `audit-issues` keeps reporting those
items as `1f` findings. That is the better trade: a noisy audit beats a lost decision. A
migration that disposes decided items into `issues-resolved.yaml`, where a resolution can
actually hold the decision, is the real fix and is not built yet.

**The backlog auditor resolves more source shapes, and the health check stops overstating.**
`audit-backlog.py` now understands `closure review (E{nnn}-S{nn})` and a story key followed by
free text, and searches artifact **bodies** rather than only filenames — on one real backlog that
took traceable items from 0 to 49. Health Check 13 previously printed "0 candidates" whether it
found nothing to fix or could not read the backlog at all; it now counts and reports
`evidence: untraceable` separately. Expect the check to say more than it used to on a legacy
backlog. That is the same state as before, described honestly.

**Two new read-only `pm-status.py` verbs — `list-epics` and `list-stories`.** Read-only
enumeration of the state tree that lets a caller stop assembling state paths in shell.
`list-epics --state-root S [--format keys|json]` prints every epic with its status bucket;
`list-stories --state-root S --epic E [--sprint S] [--format keys|json]` prints story keys
under an epic, optionally scoped to one sprint. Absent-vs-empty is distinguished by exit code
(3 vs. 0 empty output). The full verb tables in `docs/l3io-pm-reference.md` and
`docs/l3io-util-reference.md` list them; no other changes to existing verbs.

**`migrate-state` and `bootstrap-state` preserve more source fields.** Both modes now
carry `goal` and `superseded_by` through the migration and land them on the created state
node via `pm-status.py set-field` after `import-node`. Three structured fields — `depends_on`,
`estimate`, `actual` — do NOT yet have typed writers, so the engine prints a `WARN` to stderr
naming the record, the field, and the value being skipped. Previously these fields were
dropped silently on migration; now the loss is visible. The three typed writers are tracked
by `docs/superpowers/plans/2026-09-24-followup-migration-extras-typed-writers.md`.

**`bootstrap-state` now runs additively on a project with partial sharded state.** A project
that has state nodes for some stories and orphan `.md` files for others can now use
`bootstrap-state` to fill in the missing state without touching the existing nodes. The
reader (`read-artifacts.py`) skips story files whose key already has a state node, and only
surfaces inferred sprint/epic records for keys the state tree does not already carry. The
plan lists only the genuinely new work, so `verify_against_plan` passes and existing state
is byte-preserved.

**Internal only — `check 26` (resolver-invariant) exemption reads a body marker, not a
filename.** The one derived exemption for the check now looks for
`<!-- resolver-invariant: canonical-contract -->` in the file body instead of comparing
filenames. Contributors and per-skill maintainers only; no user-visible behavior change.

### → 3.0.0

**Doctor modes removed.** `/l3io-util-doctor` keyword removals — if a script, alias, or
habit invokes one of these, switch it to the replacement named here.

| Removed keyword | Use instead |
|---|---|
| `normalize` | `sort-status` (naming report) and, on a legacy split layout, `reconcile-status` — `normalize` only ran those two, and on a migrated project it ran nothing but `sort-status` |
| `backlog` | `stats` — `backlog` and `issues` are now aliases for it, so the keyword still works; the per-item table it printed is a section of the `stats` dashboard, from the same single `list-issues --all` call |
| `rename-active` | `/l3io-util-doctor` — Health Check 1 detects the old filename and renames it inline. There was never a reason to invoke it alone: a renamed flat file is still a legacy layout |
| `rename-epic-dirs` | `/l3io-util-doctor` — Health Check 10 detects two-digit `epic-{nn}/` artifact directories and renames them inline |
| `overlay` | nothing yet — the mode is held back until `assets/overlays/` ships overlay TOML (Phase 3 of the customization-layer design). All three actions reported "nothing ships yet" by construction; the contract is kept at `skills/l3io-util-doctor/assets/overlays/overlay-mode.md` |

**`l3io-util-cleanup` removed.**

`/l3io-util-cleanup` was a deprecated forwarder from 2.1.0 onward and has been removed on
`main`. Use `/l3io-util-doctor` with the same arguments — every mode name is unchanged.

**Module setup no longer routes through `l3io-pm-execute`, `l3io-pm-plan`, `l3io-pm-help`,
or `l3io-pm-sync`.** Those four skills previously loaded `assets/module-setup.md` when you
passed `setup`, `configure`, or `install`; they no longer carry that file at all — only the
module's home skill, `l3io-pm-setup`, does. If a team script, alias, or habit invoked module
setup through one of the other four skills, switch it to `/l3io-pm-setup`. `l3io-pm-sync`'s
own `setup` mode (GitHub sync setup) is unaffected — it was always a different thing from
module setup.

### → 2.1.1

**`persistent_facts` no longer searches recursively.** The PM skills previously injected
`{project-root}/**/project-context.md` into every subagent — an unbounded recursive glob. It
is now two explicit paths:

```toml
persistent_facts = [
  "file:{project-root}/project-context.md",
  "file:{project-root}/docs/project-context.md",
]
```

**Action required only if your `project-context.md` lives somewhere else.** It will silently
stop being loaded — no error. Restore it by adding your path in
`_bmad/custom/{skill-name}.toml`; the customization model **appends** arrays across layers, so
your path and the defaults are both loaded:

```toml
[workflow]
persistent_facts = ["file:{project-root}/my/path/project-context.md"]
```

Nothing else changes. Subagents also no longer load the full state and metrics contracts at
activation — they carry an operative digest and consult those references on demand — which
cuts token use substantially with no change to which phases run.

### → 2.1.0

**`l3io-util-cleanup` was renamed to `l3io-util-doctor`.** "Cleanup" described about three of
its sixteen modes, while the default behavior is a diagnose-report-repair health check.

Backward compatible at the time — no action required. `/l3io-util-cleanup` printed a rename
notice and forwarded. Update any scripts, aliases, or team docs that invoke the old name; it
was deprecated, and has since been removed on `main` ahead of the next release (see above).

**New: progress reporting.** `/l3io-pm-help progress` (which forwards to
`/l3io-util-doctor stats`) and `/l3io-util-doctor stats` itself render a plan-aware tree —
which phase, epic, sprint, and stories are in flight. Nothing to migrate, but
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

Status files were named `sprint-status-active.yaml`. `/l3io-util-doctor` detects this (Check 1)
and renames it inline as the first step of the sequence. There is no `rename-active` keyword to
invoke — and there was never a reason to invoke it alone, because a renamed flat file is still
a legacy layout.

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
| `{implementation_artifacts}/state/pm-calibration.yaml.v1` | first calibration write after a v1 → v2 schema migration (written beside the live calibration file, not under `_bmad/`) |
| `_bmad/migration-backup/` | pre-2.5 `migrate-state` (Stage F's "move" option). The current engine renames sources to `*.yaml.legacy` in place, not to a backup directory — you will only see this if your project was migrated under an older release. |

Nothing deletes these automatically. Once you have verified the result, remove them with:

```
/l3io-util-doctor clean-legacy
```

It dry-runs first and confirms before deleting.

## Deprecations

| Deprecated | Since | Replacement | Removal |
|---|---|---|---|
| `/l3io-util-cleanup` | 2.1.0 | `/l3io-util-doctor` | removed on `main`; ships in the next release (not in 2.5.1) |
| `migrate-schema`, `split-status`, `reconcile-status` | — | legacy-only bridging modes; no longer reachable once `migrate-state` has run | when 1.x migration support is dropped |
