# Step 00: Activate l3io-pm Module

Communicate all responses in `{communication_language}`.

This step runs first in every l3io-pm skill. Complete all actions in order before loading
any subsequent step file.

---

## 1. Load module configuration

Read `{project-root}/_bmad/config.yaml`.

If the file is absent or the `l3io-pm` module block is missing, this is a first-run:
load `{skill-root}/assets/module-setup.md` and execute it fully before continuing
with the steps below.

Extract and bind from config:
- `{implementation_artifacts}` — absolute path to project's implementation artifacts directory
- `{planning_artifacts}` — absolute path to planning artifacts directory
- Set `{pm_state_root}` = `{implementation_artifacts}/state`
- Set `{pm_issues_file}` = `{pm_state_root}/issues.yaml`
- Set `{pm_calibration_file}` = `{pm_state_root}/pm-calibration.yaml`

## 2. Install pm-status.py

Self-install runs here — **before** layout detection — deliberately. Self-install is
layout-independent (it copies a file and needs no state), so nothing in detection depends on
it, and running it first guarantees a current script whichever branch detection takes below.
This also keeps an upgrading user from getting stuck on a stale installed copy: a legacy
layout blocks in section 3 and sends the user to `/l3io-util-cleanup migrate-state`, and that
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
locations and remove the stale one, then re-run /l3io-util-cleanup migrate-state.
```

**If only sharded** → current layout. Continue to section 4.

**If only the legacy per-epic layout or only the legacy flat layout** → halt:
```
⚠️  Legacy state layout detected (legacy per-epic layout = _bmad/state/, legacy flat layout = flat sprint-status.yaml).
Run /l3io-util-cleanup migrate-state to upgrade before continuing.
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

## 8. Output status line

```
Step 00 complete — state: {pm_state_root}, active epics: {count_of_active_epic_keys}, pm-status: installed
```
