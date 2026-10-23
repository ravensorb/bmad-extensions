"""pm_status.metrics.events -- the event log's READERS.

`state/events.jsonl` is append-only and `flock`-guarded, and the WRITER
(`append_event`, `events_path`, `_event_keys`) is a primitive that lives in
`core`: everything that changes a node's status appends, including the node
layer and the status verbs, so the writer sits below them all. The readers are
a different thing entirely -- they derive dwell time, dispatch windows, stuck
flags and blocked hours from a log that already exists -- and they belong up
here with the rest of the measurement layer. Do not pull the writer back.

Nothing in this module patches or is patched; every import is by name.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime

from ..core import (
    _hashable_field,
    _indexable_key,
    _now_iso,
    _parse_iso,
    append_event,
    canonical_epic_key,
    canonical_sprint_key,
    events_path,
)

# Fixed thresholds, in hours. Deliberately not configurable in this iteration: the
# calibration data needed to tune them is what this report will generate.
STUCK_THRESHOLDS = {
    ("story", "in-progress"): 4.0,
    ("story", "review"): 4.0,
    ("sprint", "in-progress"): 24.0,
    ("epic", "in-progress"): 72.0,
}


def build_events_index(state_root: str) -> dict:
    """key -> the most recent *status* event for that key.

    Returns {} when the log is absent, which is the normal case for every project
    predating it — callers then fall back to `updated_at`.
    """
    idx: dict = {}
    p = events_path(state_root)
    if not os.path.isfile(p):
        return idx
    try:
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue  # a torn or hand-mangled line must not kill the report
                if not isinstance(ev, dict):
                    continue
                if ev.get("event") != "status" or not ev.get("key"):
                    continue
                k = _indexable_key(ev["key"])      # a non-empty list is truthy AND unhashable
                if k is None:
                    continue
                prev = idx.get(k)
                if prev is None or str(ev.get("ts", "")) >= str(prev.get("ts", "")):
                    idx[k] = ev
    except OSError as e:
        sys.stderr.write(f"pm-status.py: warning — could not read event log: {e}\n")
    return idx


DEFAULT_STALL_MINUTES = 15


def cmd_dispatch(args) -> int:
    """Record a subagent dispatch opening or closing.

    Two consumers, one event pair rather than two parallel logs that can
    disagree: `open_dispatches` (stall detection) reads it here, and the closing
    agent reads it to place the boundary between a child's spend and the
    orchestrator's (metrics-contract.md §6, "Where the boundary between 'child'
    and 'orchestration' is").

    NOT a derivation of orchestration spend. This script has no access to a
    session transcript and cannot see a token count; it records two timestamps.
    The counts are read from the transcript's `usage` fields by the agent, as for
    every other metric — these events remove the judgement about where one
    bucket ends and the next begins, not the reading.
    """
    payload = {"ts": _now_iso(),
               "event": "dispatch_open" if args.event == "open" else "dispatch_close",
               "agent": args.agent,
               "session": getattr(args, "session_id", None)}
    # Canonical, not raw. This is the fifth write site of the same class and the one that
    # matters: _dispatch_identity is (agent, epic, sprint, story), so an open and a close
    # spelled differently are different dispatches and the close never cancels the open --
    # the dispatch then reports as permanently stalled. --story is strict (a non-canonical
    # key is rejected outright), so it passes through unchanged.
    _canon = {"epic": canonical_epic_key, "sprint": canonical_sprint_key}
    for k in ("epic", "sprint", "story"):
        v = getattr(args, k, None)
        if v:
            payload[k] = _canon[k](v) if k in _canon else v
    # Resolve the match BEFORE appending: this close is itself a close record, so
    # a scan taken afterwards has already cancelled the open it is reporting on.
    matched = None
    if args.event == "close":
        matched = _pending_dispatches(args.state_root).get(_dispatch_identity(payload))
    append_event(args.state_root, payload)
    if args.event != "close":
        sys.stdout.write(f"OK dispatch {args.event} {args.agent}\n")
    elif matched is not None:
        # An orphan close stays exit 0 -- legitimate on a log that may begin
        # mid-run -- but the verb could not previously tell the two cases apart,
        # so a close that cancelled nothing read exactly like one that worked.
        sys.stdout.write(f"OK dispatch close {args.agent} "
                         f"(cancelled open from {matched.get('ts')})\n")
    else:
        sys.stdout.write(f"OK dispatch close {args.agent} (no matching open found)\n")
    return 0


def _dispatch_identity(rec: dict) -> tuple:
    """What makes two dispatch records the same dispatch. Agent plus node keys —
    a story-level retry of the same agent reuses the identity deliberately, so a
    close always cancels the most recent matching open.

    Node keys are canonicalised HERE, on read, rather than trusted as stored. The
    write sites canonicalise too, but a write site can only govern records written
    after it: `events.jsonl` is append-only, so an open written before the
    write-side fix holds the caller's spelling ('01') while every close now holds
    'S01'. Comparing the two raw left those dispatches permanently uncloseable,
    with no CLI route to clear them, because the canonical write path cannot emit
    a close that matches a non-canonical open. Canonicalising on read makes every
    historical spelling comparable with no rewrite of the log, which is sound
    because both key functions are idempotent ('S01' -> 'S01') and total
    (`_norm_num` falls back to the stripped string rather than raising).

    Every element is forced hashable. This tuple is a dict key on the stall
    dashboard's read path, and a record whose field held a list used to raise
    `TypeError: unhashable type` out of `pending[...]` — crashing the exact
    surface `_pending_dispatches` documents itself as reading defensively for.
    Guarding the whole record (`isinstance(rec, dict)`) never covered a single
    field inside it.
    """
    agent, epic = rec.get("agent"), rec.get("epic")
    sprint, story = rec.get("sprint"), rec.get("story")
    return (None if agent is None else _hashable_field(agent),
            None if epic is None else canonical_epic_key(epic),
            None if sprint is None else canonical_sprint_key(sprint),
            None if story is None else _hashable_field(story))


def _pending_dispatches(state_root: str) -> dict:
    """`_dispatch_identity` -> the open record still outstanding for it.

    The one scan behind both `open_dispatches` (which then applies an age
    threshold) and the `dispatch --event close` report, so the question "is there
    an open matching this close?" is answered by the same matching rule that
    decides whether a dispatch shows as stalled. Answering it twice, two ways, is
    how the two could disagree.

    Reads defensively, exactly as `build_events_index` does over the same file:
    the log is appended to by concurrent flock'd writers and is documented as
    possibly torn, so a valid-JSON line that is not an object (a bare `42` from a
    torn write or a hand-edit) must be skipped, not dereferenced, and an OSError
    must warn rather than abort. This is the read behind `report --watch`, the
    stall dashboard — a crash here takes down precisely the surface the stall
    feature exists to provide. `_dispatch_identity` carries the same obligation
    down to the individual field.
    """
    path = events_path(state_root)
    if not os.path.exists(path):
        return {}
    pending: dict = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict):
                    continue
                ev = rec.get("event")
                if ev == "dispatch_open":
                    pending[_dispatch_identity(rec)] = rec
                elif ev == "dispatch_close":
                    pending.pop(_dispatch_identity(rec), None)
    except OSError as e:
        sys.stderr.write(f"pm-status.py: warning — could not read event log: {e}\n")
    return pending


def open_dispatches(state_root: str, threshold_minutes: float, now=None) -> list:
    """Dispatches opened and never closed, older than the threshold, oldest first.

    Cannot interrupt a hang — makes it visible. A close with no matching open is
    ignored rather than treated as an error: events.jsonl is append-only and may
    begin mid-run on a pre-existing project. The close verb reports which case it
    was (see `_dispatch_close_report`), so "ignored" never means "unreported".
    """
    pending = _pending_dispatches(state_root)
    if now is None:
        now = datetime.now(UTC)
    out = []
    for rec in pending.values():
        opened = _parse_iso(rec.get("ts"))
        if opened is None:
            continue
        age = (now - opened).total_seconds() / 60.0
        if age < threshold_minutes:
            continue
        out.append({"agent": rec.get("agent"), "epic": rec.get("epic"),
                    "sprint": rec.get("sprint"), "story": rec.get("story"),
                    "opened_at": rec.get("ts"), "age_minutes": round(age, 1)})
    return sorted(out, key=lambda r: r["opened_at"])


def dwell_hours(node, events_index: dict, now=None):
    """Hours the node has been in its CURRENT status.

    Returns (hours, exact). `exact` is True only when the event log recorded the
    transition into this very status. The `updated_at` fallback is approximate
    because any field write refreshes it, not only a status change.
    """
    if node is None:
        return None, False
    now = now or datetime.now(UTC)
    status = str(node.get("status", ""))
    key = str(node.get("key", ""))
    ev = (events_index or {}).get(key)
    if ev is not None and str(ev.get("to", "")) == status:
        started = _parse_iso(ev.get("ts"))
        if started is not None:
            return max(0.0, (now - started).total_seconds() / 3600.0), True
    started = _parse_iso(node.get("updated_at"))
    if started is None:
        return None, False
    return max(0.0, (now - started).total_seconds() / 3600.0), False


def compute_flags(level: str, key: str, status: str, dwell, exact: bool) -> list:
    """Stuck flags for one node. Terminal and waiting statuses are never flagged."""
    if dwell is None:
        return []
    threshold = STUCK_THRESHOLDS.get((level, str(status)))
    if threshold is None or dwell < threshold:
        return []
    return [{"kind": "stuck", "level": level, "key": key, "status": str(status),
             "dwell_hours": round(dwell, 2), "threshold": threshold, "exact": exact}]


def _total_blocked_hours(state_root: str, story_key: str) -> float:
    """Sum `duration_hours` across every closed block for this story SINCE its
    most recent `dispatch_open`.

    A story with any nonzero blocked time in the current dispatch cycle cannot
    produce an `elapsed_hours` calibration sample -- wall-clock during blocked
    time includes human wait, which would poison the scope ratio for future
    stories. The exclusion is per-metric, not per-sample: other metrics stay
    recorded.

    Scoping to the most recent dispatch cycle avoids the multi-session
    over-exclusion the design's §5 amendment named: a story blocked in Session 1
    and completed cleanly in Session 2 must not get Session 2's `elapsed_hours`
    excluded because of Session 1's blocks. Index-based (not timestamp-based)
    boundary because events.jsonl is append-only and its order reflects
    chronology reliably even under clock skew.

    Fallback: when the story has no `dispatch_open` on record -- either because
    the log was truncated, or because the story predates dispatch bracketing --
    the scan reverts to counting all `block_close` events. That preserves the
    safety-first bias for stories where the dispatch bracket isn't available.

    Returns 0.0 on a missing log, an empty story key, or an unreadable line
    within the log -- lenient enough that a torn write does not silently fail
    the calibration write path this feeds.
    """
    if not story_key:
        return 0.0
    p = events_path(state_root)
    if not os.path.exists(p):
        return 0.0
    try:
        with open(p, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return 0.0
    parsed = []      # (line_index, event, story, duration_hours-or-None)
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        story = rec.get("story")
        if story != story_key:
            continue
        ev = rec.get("event")
        if ev not in ("dispatch_open", "block_close"):
            continue
        parsed.append((i, ev, rec.get("duration_hours")))
    if not parsed:
        return 0.0
    # Find the LATEST dispatch_open index for this story; sum block_close
    # durations after it. If there is no dispatch_open at all, sum everything
    # (safety-first fallback for stories that predate dispatch bracketing).
    last_open_idx = -1
    for i, ev, _ in parsed:
        if ev == "dispatch_open":
            last_open_idx = i
    total = 0.0
    for i, ev, d in parsed:
        if ev != "block_close":
            continue
        if last_open_idx >= 0 and i < last_open_idx:
            continue
        if isinstance(d, (int, float)):
            total += float(d)
    return round(total, 3)


def _block_duration_since_last_open(state_root: str, story_key: str):
    """Hours since the most recent block_open event for `story_key`.

    Returns None when no block_open is found on the story (a caller-side bug the WARN
    downstream can surface without crashing). Reads the events log from the end.
    """
    p = events_path(state_root)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return None
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("event") == "block_open" and rec.get("story") == story_key:
            opened = _parse_iso(rec.get("ts"))
            if opened is None:
                return None
            now = _parse_iso(_now_iso())
            if now is None:
                return None
            delta = (now - opened).total_seconds() / 3600.0
            return round(delta, 3)
    return None
