### Progress Mode

Invoked with the `progress` argument. Read-only — `report` writes only when `--out` is
passed, and nothing here passes it.

**When `{pm_status_present}` is `absent`:** print this and stop. The report is the one thing
in this skill that genuinely needs the helper — it computes dwell times and phase roll-ups
that cannot be read off `epic.yaml`:

```
pm-status.py is not installed. Run /l3io-util-doctor to install it, then re-run
/l3io-pm-help progress.
```

**Otherwise** run:

```bash
uv run {pm_status} report \
  --state-root {pm_state_root} \
  --plan {planning_artifacts}/plan-output-meta.yaml \
  --format tree
```

**Scope — map what the user asked for to a `--status` filter.** The state tree's three
folders are the vocabulary: `planned` = backlog, `active` = in progress, `archived` = done.

| They asked for | Pass |
|---|---|
| nothing, "progress", "status" | *(nothing — defaults to planned + active)* |
| "what's active", "in flight", "what's running", "in progress", "what's moving" | `--status active` |
| "what's queued", "backlog", "not started", "what's next" | `--status planned` |
| "everything", "including done", "including archived", "all" | `--all` |

Counting is unaffected by the filter: totals and phase denominators always cover every epic,
so a narrowed view never changes what "2/3 epics done" means. When the filter is not the
default the report prints a `SHOWING …` banner itself — do not add your own caveat.

Print the output verbatim. Do not summarize it, re-order it, or re-format it into your own
table — it is already the rendered view, and paraphrasing it invites drift between what the
tool computed and what the user reads.

Then add one line pointing at the live view, because that is what answers "what is happening
right now" during a long run:

```
For a live view during a run: uv run {pm_status} report --state-root {pm_state_root} \
  --plan {planning_artifacts}/plan-output-meta.yaml --watch 15
```

Two follow-ups, only when the output warrants them:

- If the output contains `⚠ STALE LOCK`, append the clear-lock recommendation from section 5
  for each affected epic. Do not re-derive stale-lock state yourself — the report already
  computed it from `_lock.ttl_minutes`.
- If the output ends with the `~ dwell times are approximate` note, add: `Dwell times sharpen
  once state/events.jsonl accumulates transitions — it starts recording on the next
  /l3io-pm-execute run.`

