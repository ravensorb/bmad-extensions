# Sync Step 04: Resolve

Communicate all responses in `{communication_language}`.

Resolve any conflicts surfaced by step-03 and write the final sync report.

## 1. Conflict resolution (push/pull/sync modes only)

If step-03 reported conflicts (local status != external status for the same item):

For each conflict, present to user:
```
Conflict: {ava_key}
  Local status:    {local_status}
  External status: {external_status} (last synced: {synced_at})
  Resolution: [local-wins | external-wins | skip]
```

Default resolution: `local-wins` — l3io-pm is the authoritative source.

Apply resolutions:
- `local-wins`: update external item status to match local
- `external-wins`: run `python3 {pm_status} set-status --file ... --story {ava_key} --status {external_mapped_status}`
- `skip`: log as unresolved, do not update either side

## 2. Update sync-mapping.yaml timestamps

For all items successfully synced in this run, update `synced_at` in `{sync_mapping_file}`.

## 3. Write sync report

Write `{project-root}/_bmad/sync-report-{iso_date}.md`:
- Mode run, platform, timestamp
- Items pushed/pulled/synced
- Conflicts resolved (with resolution chosen)
- Unresolved conflicts (if any)
- Unmapped items (not yet pushed)

## 4. Output

```
Step 04 complete — sync report: {project-root}/_bmad/sync-report-{iso_date}.md
```
