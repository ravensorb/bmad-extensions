# Step 00: Activate l3io-pm Module

Communicate all responses in `{communication_language}`.

This step runs first in every l3io-pm skill. Complete all actions in order before loading
any subsequent step file.

---

## 1. Load module configuration

Resolve config through BMad core's resolver — the full contract, including every
binding and its default, is `{skill-root}/references/config-resolution.md`:

```bash
uv run --python 3.11 {project-root}/_bmad/scripts/resolve_config.py --project-root {project-root}
```

If the resolver is missing or the command fails, BMad core is not installed in this
project: **BLOCKED** — tell the user to run the BMad installer. Do not write config
yourself and do not continue.

`modules.l3io-pm` being absent is **not** a first-run and **not** an error — it means the
module has no project-level overrides, which is the normal state. Bind the defaults below
and continue. Load `{skill-root}/assets/module-setup.md` only when the user explicitly
passes `setup`, `configure`, or `install`.

Extract and bind from the resolved JSON:
- `{communication_language}` — `core.communication_language` (default `English`)
- `{output_folder}` — `core.output_folder` (default `{project-root}/_bmad-output`)
- `{implementation_artifacts}` — `modules.l3io-pm.implementation_artifacts`
  (default `{output_folder}/implementation-artifacts`)
- `{planning_artifacts}` — `modules.l3io-pm.planning_artifacts`
  (default `{output_folder}/planning-artifacts`)
- Set `{pm_state_root}` = `{implementation_artifacts}/state`
- Set `{pm_issues_file}` = `{pm_state_root}/issues.yaml`
- Set `{pm_calibration_file}` = `{pm_state_root}/pm-calibration.yaml`

## 2. Install pm-status.py

Self-install runs here — **before** layout detection — deliberately. Self-install is
layout-independent (it copies a file and needs no state), so nothing in detection depends on
it, and running it first guarantees a current script whichever branch detection takes below.
This also keeps an upgrading user from getting stuck on a stale installed copy: a legacy
layout blocks in section 3 and sends the user to `/l3io-util-doctor migrate-state`, and that
command needs a current `{pm_status}` to succeed — which this section guarantees regardless of
which layout branch section 3 takes.

```bash
uv run {skill-root}/scripts/pm-status.py self-install \
  --dest {project-root}/_bmad/scripts/pm-status.py
```

If `uv` is unavailable, use `python3` instead. A "skipped — already up to date"
message is normal. Failure here is BLOCKED.

Bind `{pm_status}` = `{project-root}/_bmad/scripts/pm-status.py` for use in all
subsequent steps.

Bind `{runtime}` — passed as `--runtime` to every `set-actual` and `verify` call
(`references/metrics-contract.md` §3). The value must be **exactly** `claude` or
`other` — `pm-status.py` declares `--runtime` with `choices=["claude", "other"]` and
rejects anything else with exit 2, so never widen this to a runtime name or version
string. The criterion is a capability, not a brand check: bind `claude` only when this
execution can read its own session transcript's `usage` fields to capture exact
`tokens_k`/`cost` for the session (Claude Code, or any Claude-based agent with that
transcript access); bind `other` otherwise. **Default to `other` when uncertain** — it
is the permissive value, allowing `N/A` for `tokens_k`/`cost`, while `claude` forbids
`N/A` there; guessing `claude` without the ability to produce exact figures would either
block every write or invite a fabricated number, and both are worse than an honest
`N/A`. Do not treat this default as a bug to "fix" later — it is the deliberate
fail-safe direction.

## 3. Detect state layout

Count how many of these three layouts are present — do **not** stop at the first match:

```bash
SHARDED=$([ -d "{implementation_artifacts}/state" ] && echo 1 || echo 0)
LEGACY_EPIC=$([ -d "{project-root}/_bmad/state" ] && echo 1 || echo 0)
LEGACY_FLAT=$([ -f "{implementation_artifacts}/sprint-status.yaml" ] && echo 1 || echo 0)
echo "sharded=$SHARDED legacy-per-epic=$LEGACY_EPIC legacy-flat=$LEGACY_FLAT"
```

**If more than one is 1** → halt immediately. An interrupted migration left state in two
places, and guessing which is authoritative would fork the project's state:
```
BLOCKED: multiple state layouts detected (sharded=$SHARDED legacy-per-epic=$LEGACY_EPIC legacy-flat=$LEGACY_FLAT). An earlier migration
did not finish. Do not run any l3io-pm skill until this is resolved — inspect both
locations and remove the stale one, then re-run /l3io-util-doctor migrate-state.
```

**If only sharded** → current layout. Continue to section 4.

**If only the legacy per-epic layout or only the legacy flat layout** → halt:
```
⚠️  Legacy state layout detected (legacy per-epic layout = _bmad/state/, legacy flat layout = flat sprint-status.yaml).
Run /l3io-util-doctor migrate-state to upgrade before continuing.
```
BLOCKED: legacy state layout — migrate required. (`{pm_status}` was just self-installed in
section 2, so `migrate-state` runs against a current copy.)

**If all three are 0** → possible first run. Before creating anything, rule out an orphan
caused by `implementation_artifacts` having been repointed:

```bash
git -C {project-root} ls-files -- '*/state/active/epic-*/epic.yaml' 'state/active/epic-*/epic.yaml' 2>/dev/null | head -5
find {project-root} -maxdepth 5 -type d -name active -path '*/state/*' 2>/dev/null | head -5
```

The second pathspec (`state/active/epic-*/epic.yaml`, no leading `*/`) catches the case where
`implementation_artifacts` equals `project-root`: git's fnmatch-pathname semantics require at
least one literal path segment before `state/`, so the first pathspec alone would miss a
root-level match.

If either prints a path that is not under `{implementation_artifacts}/state`, halt:
```
BLOCKED: state found at <printed-path> but implementation_artifacts resolves to
{implementation_artifacts}. Did implementation_artifacts change? Refusing to start a
blank project over existing state.
```

If both print nothing → genuine first run. Continue to section 4.

## 4. Create state directories

```bash
mkdir -p {pm_state_root}/active {pm_state_root}/planned {pm_state_root}/archived
mkdir -p {planning_artifacts}
```

Verify the state root is not gitignored — this is what keeps state in version control:

```bash
git -C {project-root} check-ignore -q {pm_state_root} && echo IGNORED || echo TRACKED
```

If `IGNORED`, halt:
```
BLOCKED: {pm_state_root} is gitignored. Project state must be committed. Add to .gitignore:
  !{pm_state_root}/
  !{pm_state_root}/**
```

## 5. List active epics

```bash
ls -d {pm_state_root}/active/epic-*/ 2>/dev/null || echo "(none)"
```

Bind `{active_epic_keys}` = the `E{nnn}` key for each directory found (`epic-001` → `E001`).
An empty list is valid on first run.

## 6. Verify schema of files this skill will touch (if any active epics exist)

If `{active_epic_keys}` is non-empty AND this skill is `l3io-pm-execute` or `l3io-pm-plan`,
run for each epic key in scope:

```bash
python3 {pm_status} verify --state-root {pm_state_root} --epic {epic_key} --scope epic
```

A FAIL result means the epic's files are corrupted. Halt with:
```
BLOCKED: schema verify failed for {epic_key} — investigate before continuing.
```

A PASS or "epic absent" result is fine.

## 7. Bind session ID

Generate and bind `{session_id}` — a stable unique identifier for this execution session
(e.g., `l3io-pm-{iso_timestamp}-{random_suffix}`). This value must remain constant for the
lifetime of this skill invocation and is used by set-lock / check-lock to identify the
owning session. Generate it once here; never regenerate it in later steps.

## 8. State and metrics digest — keep this in context

This is everything a normal run needs from the state and metrics contracts. **Do not load
`references/status-files.md` or `references/metrics-contract.md` unless the routing table at
the end of this section sends you there** — they are 1,178 lines combined, and re-reading them
per subagent is the single largest avoidable token cost in the system.

**Precedence.** `pm-status.py` is the authority: it enforces every rule below mechanically, so
if its behavior and this digest disagree, the script is right. Then the full reference. This
digest is last — treat it as stale if it conflicts.

### Keys

- Epic `E{nnn}` → directory `epic-{nnn}` · Sprint `S{nn}` → `sprint-{nn}`
- Story `E{nnn}-S{nn}-{nnn}` → file `E{nnn}-S{nn}-{nnn}.yaml` in that sprint's directory
- Backlog item `BL-E{nnn}-{nnn}` (`BL-E000-{nnn}` for repo-global)
- Zero-padded always. Node fields use `key:`, never `id:`.

### Never build a state path by hand

`pm-status.py` is the only component that resolves a key to a location. Address nodes by key;
if you find yourself concatenating `state/active/epic-...`, stop and use a subcommand.

Bind `{pm_status}` = `{project-root}/_bmad/scripts/pm-status.py`.

### The calls a sprint or epic run makes

```
set-status    --state-root S  (--story KEY | --epic ID [--sprint ID])  --status S
              [--title T] [--flock] [--no-events] [--session-id ID]
set-actual    --state-root S  --node {story,sprint,epic}  (--story KEY | --epic ID [--sprint ID])
              [--elapsed-hours H] [--man-hours H] [--tokens-k K] [--cost C]
              [--runtime {claude,other}] [--flock] [--no-calibrate]
set-estimate  --state-root S  (--story KEY | --epic ID [--sprint ID])
              story: --man-hours H --time-hours H --tokens-k K --cost C
              sprint/epic: --man-hours-low/-high, --time-hours-low/-high,
                           --tokens-k-min/-max, --cost-low/-high
              [--confidence {low,medium,high}] [--flock]
set-field     --state-root S  (--story KEY | --epic ID [--sprint ID])  --field NAME --value V
estimate-story   --state-root S  --story KEY  --classification {simple,standard,complex}
estimate-rollup  --state-root S  --epic ID  [--sprint ID]
verify        --state-root S  --scope {story,sprint,epic}  (--story KEY | --epic ID [--sprint ID])
              [--require-tokens] [--runtime {claude,other}]
show          --state-root S  --epic ID  [--sprint ID]
report        --state-root S  [--plan P] [--format tree|json|md] [--out F] [--all] [--watch SECS]
set-lock      --state-root S  --epic ID  --session-id SESS  [--ttl-minutes N]
clear-lock    --state-root S  --epic ID
check-lock    --state-root S  --epic ID  --session-id SESS
move-epic     --state-root S  --epic ID  --to {planned,active,archived}
append-issue  --file F  --key BL-E{nnn}-{nnn}  --epic E  [--sprint S]  --title T
              --source S  --severity {Low,Medium,High,Critical}  [--description D]
```

Exit codes: `0` success · `2` usage error · `3` node not found · `4` verification failure ·
`5` epic locked by another session. Branch on these rather than parsing stdout.

`set-status` and `set-actual` append to `state/events.jsonl` automatically. You never write
that file, and you never pass a flag to make it happen.

### Estimates and actuals — the HARD RULE

Every planning point and every closeout, at story, sprint, and epic level, records **both** an
`estimate` and an `actual` for all four metrics: man-hours, compute (wall-clock) hours, tokens,
and token cost. This is enforced at write time, not advisory.

Under `--runtime claude`, token and cost actuals are read **exactly** from the session
transcript's `usage` fields and `set-actual`/`verify` **reject** `N/A`. Under any other runtime
capture what is exposed and record `N/A` — **never a guess**.

`set-actual` derives the calibration sample itself. Write
`completion_evidence.fix_iterations` **before** calling it, or the scope-versus-fix split
cannot see it.

### When you do need the deep contract

| If you need to… | Read |
|---|---|
| interpret a `verify` failure | `references/status-files.md` §7 (Addressing) |
| know which fields a node carries | `references/status-files.md` §4 (Per-file schema) |
| handle a migration or legacy layout | `references/status-files.md` §10 (Read resolution at activation) |
| declare or read `depends_on` | `references/status-files.md` §11 (Dependency fields) |
| resolve an epic lock question | `references/status-files.md` §6 (Ownership lock) |
| capture token/cost actuals correctly | `references/metrics-contract.md` §3 (Runtime detection and capture) |
| write an estimate or actual by hand | `references/metrics-contract.md` §4 (Writing estimates and actuals) |
| explain a calibration result | `references/metrics-contract.md` §8 (Calibration) |
| see a full worked example | `references/metrics-contract.md` §10 (Worked example) |

## 9. Output status line

```
Step 00 complete — state: {pm_state_root}, active epics: {count_of_active_epic_keys}, pm-status: installed, runtime: {runtime}
```
