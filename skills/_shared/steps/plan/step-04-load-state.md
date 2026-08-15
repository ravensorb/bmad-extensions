# Step 04: Load State

Communicate all responses in `{communication_language}`.

Reads all state files and builds the full in-scope index. Subsequent steps consume
`{epic_index}` and `{story_index}` directly — do not re-read state files.

---

## 1. Read active epics

List all files matching `{bmad_active_root}/E{nnn}-status.yaml`:

```bash
ls {bmad_active_root}/E*-status.yaml 2>/dev/null || echo "(none)"
```

For each file, read and extract:
- `epics[0].key` (the epic key — one epic per active file)
- `epics[0].status` (always `in-progress` in active files)
- `epics[0].depends_on` (list; empty if absent)
- `epics[0].estimate` (present/absent)
- `epics[0]._lock` (present/absent — flag locked epics)
- All sprints and all their stories with `key`, `status`, `classification`, `estimate`, `depends_on`

Record: `{active_epics}` = list of epic keys from active files.

## 2. Read planned epics

Read `{bmad_planned_file}`. For each epic:
- `key`, `status` (backlog or deferred), `depends_on`, `estimate`, sprint+story subtrees

Separate into:
- `{backlog_epics}` = epics with `status: backlog`
- `{deferred_epics}` = epics with `status: deferred`

## 3. Read archived epic keys

Read `{bmad_archived_file}` (may not exist yet). Extract the list of epic `key` values from the top-level `epics` list. Store as `{archived_epic_keys}`. Do not load full content — only the keys are needed to validate `depends_on` references.

If the file does not exist, `{archived_epic_keys}` = [].

## 4. Build epic index

Construct `{epic_index}` as a mapping from epic key to:
```
{
  "E001": {
    "file": "{bmad_active_root}/E001-status.yaml",
    "status": "in-progress",
    "depends_on": [],
    "estimate_present": true,
    "locked": false
  },
  "E003": {
    "file": "{bmad_planned_file}",
    "status": "backlog",
    "depends_on": ["E001", "E002"],
    "estimate_present": false,
    "locked": false
  }
}
```

## 5. Build story index

Construct `{story_index}` as a mapping from story key to:
```
{
  "E001-S01-001": {
    "epic": "E001",
    "sprint": "S01",
    "status": "done",
    "classification": "standard",
    "estimate_present": true,
    "depends_on": []
  }
}
```

## 6. Report index summary

```
State loaded:
  Active epics:   {active_epic_count} ({active_epic_keys joined by comma})
  Backlog epics:  {backlog_epic_count}
  Deferred epics: {deferred_epic_count}
  Archived epics: {archived_epic_count}
  Stories in scope: {total_story_count}
  Locked epics: {locked_count} (warning if any)
```

If any locked epic is found:
```
⚠️  {epic_key} is locked by session {session_id} (claimed {claimed_at}, TTL {ttl_minutes}m).
    Run: pm-status.py check-lock --file {file} --session-id {your_session_id}
    to verify if the lock is stale. Clear with: pm-status.py clear-lock --file {file}
```

## 7. Output status line

```
Step 04 complete — epics: {total_epic_count} ({active_count} active, {backlog_count} backlog, {deferred_count} deferred), stories: {total_story_count}
```
