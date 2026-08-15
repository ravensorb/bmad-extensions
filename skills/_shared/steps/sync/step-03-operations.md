# Sync Step 03: Operations

Communicate all responses in `{communication_language}`.

Execute the sync operation specified by `{sync_mode}`.

## Mode: setup

Create `{project-root}/_bmad/sync-mapping.yaml` if absent.

```bash
python3 {skill-root}/scripts/sync-state.py setup \
  --project-root {project-root} \
  --platform {sync_platform} \
  --auth-method {auth_method} \
  --mapping-file {project-root}/_bmad/sync-mapping.yaml
```

Test the connection and report: platform reachable, auth valid, mapping file created.

## Mode: push

Read all active epics and planned epics. For each story not yet mapped:
1. Create an external work item (GitHub Issue or ADO work item)
2. Append mapping entry to `{project-root}/_bmad/sync-mapping.yaml`

```bash
python3 {skill-root}/scripts/sync-state.py push \
  --project-root {project-root} \
  --platform {sync_platform} \
  --auth-method {auth_method} \
  --mapping-file {sync_mapping_file} \
  --state-root {project-root}/_bmad/state
```

Report: items created, items updated, items skipped (already mapped).

## Mode: pull

Read the sync mapping. For each mapped item, fetch the external work item status.
Update l3io-pm story status if the external item is closed/done.

```bash
python3 {skill-root}/scripts/sync-state.py pull \
  --project-root {project-root} \
  --platform {sync_platform} \
  --auth-method {auth_method} \
  --mapping-file {sync_mapping_file} \
  --state-root {project-root}/_bmad/state
```

Report: status updates applied, conflicts detected (if any).

## Mode: sync

Run push then pull sequentially. Collect both reports.

## Mode: status

Generate a drift report:

```bash
python3 {skill-root}/scripts/drift-report.py \
  --project-root {project-root} \
  --platform {sync_platform} \
  --auth-method {auth_method} \
  --mapping-file {sync_mapping_file} \
  --state-root {project-root}/_bmad/state
```

Report: items in sync, items out of sync (local ahead / external ahead), unmapped items.

## Output

```
Step 03 complete — mode: {sync_mode}, items processed: {N}, conflicts: {N}
```
