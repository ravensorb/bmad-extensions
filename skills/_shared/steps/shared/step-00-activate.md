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
- Set `{bmad_state_root}` = `{project-root}/_bmad/state`
- Set `{bmad_active_root}` = `{project-root}/_bmad/state/active`
- Set `{bmad_planned_file}` = `{project-root}/_bmad/state/sprint-status-planned.yaml`
- Set `{bmad_issues_file}` = `{project-root}/_bmad/state/sprint-status-issues.yaml`
- Set `{bmad_archived_file}` = `{project-root}/_bmad/state/sprint-status-archived.yaml`

## 2. Detect state layout

Check if `{project-root}/_bmad/state/` exists:

**If yes** → new layout. Continue.

**If no** and `{implementation_artifacts}/sprint-status.yaml` exists →
legacy layout detected. Inform the user:
```
⚠️  Legacy state layout detected. Run /l3io-util-cleanup migrate-state to upgrade
the state files to the new layout before continuing.
```
BLOCKED: legacy state layout — migrate required.

**If no and no legacy file** → first run. Create directories (Step 3) and continue.

## 3. Create state directories

```bash
mkdir -p {project-root}/_bmad/state/active
mkdir -p {planning_artifacts}
```

## 4. Install pm-status.py

```bash
uv run {skill-root}/scripts/pm-status.py self-install \
  --dest {project-root}/_bmad/scripts/pm-status.py
```

If `uv` is unavailable, use `python3` instead. A "skipped — already up to date"
message is normal. Failure here is BLOCKED.

Bind `{pm_status}` = `{project-root}/_bmad/scripts/pm-status.py` for use in all
subsequent steps.

## 5. List active epics

```bash
ls {project-root}/_bmad/state/active/E*-status.yaml 2>/dev/null || echo "(none)"
```

Bind `{active_epic_files}` = the list of paths found (empty list is valid on first run).
Bind `{active_epic_keys}` = the `E{nnn}` portion of each filename (e.g. `E001`, `E002`).

## 6. Verify schema of files this skill will touch (if any active files exist)

If `{active_epic_files}` is non-empty AND this skill is `l3io-pm-execute` or `l3io-pm-plan`,
run for each file in scope:

```bash
python3 {pm_status} verify \
  --file {active_epic_file} \
  --scope epic --epic {epic_key}
```

A FAIL result means the file is corrupted. Halt with:
```
BLOCKED: schema verify failed for {active_epic_file} — investigate before continuing.
```

A PASS or "file absent" result is fine.

## 7. Bind session ID

Generate and bind `{session_id}` — a stable unique identifier for this execution session
(e.g., `l3io-pm-{iso_timestamp}-{random_suffix}`). This value must remain constant for the
lifetime of this skill invocation and is used by set-lock / check-lock to identify the
owning session. Generate it once here; never regenerate it in later steps.

## 8. Output status line

```
Step 00 complete — state: {bmad_state_root}, active epics: {count_of_active_epic_files}, pm-status: installed
```
