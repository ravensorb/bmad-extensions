#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
# pm-status-version: 2.4.1   (machine-readable marker; `self-install` compares this across copies — keep at top)
"""
pm-status.py — deterministic, atomic, round-trip-safe writer for the l3io-pm
sharded state tree, and the reader behind its progress report.

Why this exists
---------------
Status transitions used to be free-form YAML edits the model performed between
phases. Under load or parallel execution those edits were skipped, malformed, or
they reordered/stripped the file. This script makes every transition a single
deterministic operation:

  * node addressing follows references/status-files.md (epic -> sprints -> stories),
  * writes are atomic (temp file + os.replace) so a crash never leaves a partial file,
  * ruamel round-trip load/dump preserves key order and comments so diffs stay clean,
  * `verify` is a hard read-back gate the orchestrator can branch on (exit code).

BMad standardizes on `uv run`; the PEP-723 header above lets `uv` provision
ruamel.yaml automatically. A plain `python3 pm-status.py ...` also works wherever
ruamel.yaml is already importable.

Subcommands
-----------
  set-status    --state-root S  (--story KEY | --epic ID [--sprint ID])  --status S
                [--title T] [--flock] [--no-events] [--session-id ID]
  set-actual    --state-root S   --node {story,sprint,epic}  (--story KEY | --epic ID [--sprint ID])
                [--elapsed-hours H] [--man-hours H] [--hitl-hours H]
                [--tokens-input K] [--tokens-output K] [--tokens-cache-write K] [--tokens-cache-read K]
                (any --tokens-* requires --model M; under --runtime claude ALL FOUR are
                required once any is given — an explicit 0 counts; [--token-rates JSON]
                overrides its rate card;
                cost is DERIVED from tokens x rates — --cost is declared but always rejected)
                [--tokens-na]   (in place of --tokens-*; runtime=other only, forbidden under runtime=claude)
                [--runtime {claude,other}] [--flock] [--no-events] [--session-id ID]
                [--no-calibrate]
                (derives the node's calibration sample inline — write
                completion_evidence.fix_iterations BEFORE this call, or the scope/fix
                split cannot see it; the sample is emitted at most once per node,
                guarded by a `calibration_sampled_at` marker)
  set-estimate  --state-root S  (--story KEY | --epic ID [--sprint ID])
                [--man-hours-low H] [--man-hours-high H] [--hitl-hours-low H] [--hitl-hours-high H]
                [--elapsed-hours-low H] [--elapsed-hours-high H]
                [--tokens-k-min K] [--tokens-k-max K]
                (sprint/epic ranges; kind is inferred from --story vs --epic[/--sprint] —
                a story node instead takes the single-value aliases --man-hours H,
                --hitl-hours H, --elapsed-hours H, --tokens-k K;
                --time-hours* accepted as a deprecated alias for --elapsed-hours*;
                cost is DERIVED from tokens x rates — --cost/--cost-low/--cost-high are
                declared but always rejected; use estimate-story/estimate-rollup instead)
                [--confidence {low,medium,high}] [--flock]
  set-field     --state-root S  (--story KEY | --epic ID [--sprint ID])  --field NAME --value V
  verify        --state-root S  --scope {story,sprint,epic}  (--story KEY | --epic ID [--sprint ID])
                [--require-tokens] [--runtime {claude,other}]
                (--scope epic checks structural/back-reference integrity across the
                epic's whole subtree; --scope story/sprint check completion of one node)
  show          --state-root S  --epic ID  [--sprint ID]
  report        --state-root S  [--plan P] [--format tree|json|md] [--out F]
                [--all] [--watch SECS]
  set-lock      --state-root S  --epic ID  --session-id SESS  [--ttl-minutes N]
  clear-lock    --state-root S  --epic ID
  check-lock    --state-root S  --epic ID  --session-id SESS
  append-issue  --file F  --key BL-E{nnn}-{nnn}  --epic E  [--sprint S]  --title T
                --source S  --severity {Low,Medium,High,Critical}  [--description D]
  list-issues   --state-root S  [--epic E] [--sprint S]
                [--severity {Low,Medium,High,Critical}] [--format {text,json}]
                (filters combine with AND; a repeated --severity ORs the given severities;
                a missing issues.yaml, or a filter matching nothing, is success — exit 0
                with an empty result, not an error)
  move-epic     --state-root S  --epic ID  --to {planned,active,archived}
  archive-epic  --state-root S  --epic ID   (alias for move-epic --to archived)
  calibration   show  --state-root S  [--format {text,json}]
                (inspects pm-calibration.yaml; a missing file is a normal
                cold-start state, not an error)
  self-install  --dest PATH  [--force]

Exit codes: 0 = success/verified, 2 = usage error, 3 = node not found,
4 = verification failure (missing/invalid field), 5 = epic locked. Errors go
to stderr; machine output (verify summaries) goes to stdout.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import hashlib
import tempfile
from datetime import datetime, timezone

try:
    from ruamel.yaml import YAML
except ModuleNotFoundError:  # pragma: no cover - environment guard
    sys.stderr.write(
        "pm-status.py: ruamel.yaml is required. Run via `uv run` (auto-provisions it) "
        "or `pip install ruamel.yaml`.\n"
    )
    sys.exit(2)

PM_STATUS_VERSION = "2.4.1"  # keep in sync with the top-of-file `# pm-status-version:` marker

VALID_STORY_STATUS = {"backlog", "ready-for-dev", "in-progress", "review", "done"}
VALID_SPRINT_STATUS = {"backlog", "in-progress", "done"}
VALID_EPIC_STATUS = {"backlog", "in-progress", "done"}
METRIC_FIELDS = ("elapsed_hours", "man_hours", "hitl_hours", "tokens_k", "cost")

# The subset of METRIC_FIELDS whose SCOPE ratio is learned. `cost` is derived
# from tokens x rates (Tasks 6/7) rather than entered or actualed on its own,
# so letting it also accumulate a scope-ratio sample would give a derived
# value an independently-learned correction — exactly the drift this rework
# removes. `cost` deliberately stays IN METRIC_FIELDS: it is still stored,
# verified, and reported, just never scope-calibrated. Derived (not restated)
# from METRIC_FIELDS so the two can't drift apart the way separately-typed
# copies did before.
CALIBRATED_METRIC_FIELDS = tuple(m for m in METRIC_FIELDS if m != "cost")


def _yaml() -> YAML:
    y = YAML()  # round-trip mode: preserves comments + key order
    y.preserve_quotes = True
    y.width = 4096  # never line-wrap scalars
    y.indent(mapping=2, sequence=2, offset=0)  # match the flush-dash status-file style
    return y


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(path: str):
    y = _yaml()
    if not os.path.exists(path):
        return y, None
    with open(path, "r", encoding="utf-8") as f:
        return y, y.load(f)


def _atomic_dump(y: YAML, data, path: str) -> None:
    """Write to a temp file in the same directory, then os.replace (atomic on POSIX)."""
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".pm-status.", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            y.dump(data, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _flock_write_or_plain(use_flock: bool, y: YAML, data, path: str) -> None:
    """Acquire an exclusive flock on `path` (or a sidecar .lock file) then atomic-dump."""
    if not use_flock:
        _atomic_dump(y, data, path)
        return
    try:
        import fcntl
    except ImportError:
        # Windows or environments without fcntl — fall back to plain write with a warning
        sys.stderr.write("pm-status.py: fcntl unavailable — writing without flock (non-POSIX)\n")
        _atomic_dump(y, data, path)
        return
    lock_path = path + ".lock"
    d = os.path.dirname(os.path.abspath(lock_path)) or "."
    os.makedirs(d, exist_ok=True)
    with open(lock_path, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            _atomic_dump(y, data, path)
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


# --------------------------------------------------------------------------- #
# Sharded layout resolution — the ONLY place that knows where nodes live on disk
# --------------------------------------------------------------------------- #
STATUS_DIRS = ("active", "planned", "archived")  # active first: hottest path


def epic_dirname(epic_key: str) -> str:
    """'E001' -> 'epic-001'. Accepts unpadded input ('E42' -> 'epic-042')."""
    n = str(epic_key).strip().lstrip("Ee")
    if not n.isdigit():
        raise ValueError(f"bad epic key: {epic_key!r}")
    return f"epic-{int(n):03d}"


def sprint_dirname(sprint_key: str) -> str:
    """'S01' -> 'sprint-01'. Accepts unpadded input ('S7' -> 'sprint-07')."""
    n = str(sprint_key).strip().lstrip("Ss")
    if not n.isdigit():
        raise ValueError(f"bad sprint key: {sprint_key!r}")
    return f"sprint-{int(n):02d}"


def parse_story_key(key: str) -> tuple:
    """'E001-S01-003' -> ('E001', 'S01', '003')."""
    parts = str(key).strip().split("-")
    if len(parts) != 3 or not parts[0].startswith("E") or not parts[1].startswith("S"):
        raise ValueError(f"bad story key: {key!r} (expected E{{nnn}}-S{{nn}}-{{nnn}})")
    return parts[0], parts[1], parts[2]


def find_epic_dir(state_root: str, epic_key: str):
    """Absolute path to the epic's directory, whichever status folder holds it."""
    name = epic_dirname(epic_key)
    for status in STATUS_DIRS:
        p = os.path.join(state_root, status, name)
        if os.path.isdir(p):
            return p
    return None


def epic_file(state_root: str, epic_key: str):
    d = find_epic_dir(state_root, epic_key)
    if d is None:
        return None
    p = os.path.join(d, "epic.yaml")
    return p if os.path.exists(p) else None


def sprint_file(state_root: str, epic_key: str, sprint_key: str):
    d = find_epic_dir(state_root, epic_key)
    if d is None:
        return None
    p = os.path.join(d, sprint_dirname(sprint_key), "sprint.yaml")
    return p if os.path.exists(p) else None


def story_file(state_root: str, story_key: str):
    epic_key, sprint_key, _ = parse_story_key(story_key)
    d = find_epic_dir(state_root, epic_key)
    if d is None:
        return None
    p = os.path.join(d, sprint_dirname(sprint_key), f"{story_key}.yaml")
    return p if os.path.exists(p) else None


def load_node(path: str):
    """Load a bare node file (no `epics:` wrapper). Returns (yaml, node|None)."""
    return _load(path)


def save_node(y, node, path: str, use_flock: bool = False) -> None:
    _flock_write_or_plain(use_flock, y, node, path)


def check_backrefs(node, epic_key: str, sprint_key: str = None) -> list:
    """Compare a node's parent back-references against its resolved location.

    An ABSENT back-reference is a failure, not a pass. Sprint and story files are
    required to carry `epic:` (and stories `sprint:`) — see status-files.md §4 — and
    migrate-state adds them as a brand-new step, so "field missing entirely" is exactly
    the case this check has to catch. Epic nodes have no parent and are never passed
    here (callers skip them).
    """
    problems = []
    if node is None:
        return ["node is empty"]
    got_epic = str(node.get("epic", "")).strip()
    if not got_epic:
        problems.append(f"epic back-reference absent (expected {str(epic_key).strip()!r})")
    elif got_epic != str(epic_key).strip():
        problems.append(f"epic back-reference {got_epic!r} != path epic {epic_key!r}")
    if sprint_key is not None:
        got_sprint = str(node.get("sprint", "")).strip()
        if not got_sprint:
            problems.append(f"sprint back-reference absent (expected {str(sprint_key).strip()!r})")
        elif got_sprint != str(sprint_key).strip():
            problems.append(f"sprint back-reference {got_sprint!r} != path sprint {sprint_key!r}")
    return problems


def resolve_node_path(state_root: str, args, kind: str):
    """Resolve a node kind + keys to (path, label). Exits 3 when the node is absent."""
    if kind == "story":
        if not args.story:
            _die_usage("--story is required for a story node")
        p = story_file(state_root, args.story)
        label = f"story {args.story}"
    elif kind == "sprint":
        if not (args.epic and args.sprint):
            _die_usage("--epic and --sprint are required for a sprint node")
        p = sprint_file(state_root, args.epic, args.sprint)
        label = f"epic {args.epic} sprint {args.sprint}"
    elif kind == "epic":
        if not args.epic:
            _die_usage("--epic is required for an epic node")
        p = epic_file(state_root, args.epic)
        label = f"epic {args.epic}"
    else:
        _die_usage(f"unknown node kind: {kind}")
    if p is None:
        _die_notfound(label)
    return p, label


def _load_checked(state_root: str, args, kind: str):
    """Resolve, load, and validate back-references. Exits 3 (missing) or 4 (misplaced)."""
    path, label = resolve_node_path(state_root, args, kind)
    y, node = load_node(path)
    if node is None:
        _die_notfound(f"{label} — file {path} is empty")
    if kind == "story":
        ek, sk, _ = parse_story_key(args.story)
        problems = check_backrefs(node, ek, sk)
    elif kind == "sprint":
        problems = check_backrefs(node, args.epic)
    else:
        problems = []
    if problems:
        sys.stderr.write(f"pm-status.py: back-reference mismatch for {label}: {'; '.join(problems)}\n")
        sys.exit(4)
    return y, node, path, label


def _infer_kind(args) -> str:
    if args.story:
        return "story"
    if args.epic and args.sprint:
        return "sprint"
    if args.epic:
        return "epic"
    _die_usage("specify --story, or --epic [--sprint]")


def _die_usage(msg: str):
    sys.stderr.write(f"pm-status.py: {msg}\n")
    sys.exit(2)


def _die_notfound(what: str):
    sys.stderr.write(f"pm-status.py: node not found — {what}\n")
    sys.exit(3)


EVENTS_FILENAME = "events.jsonl"


def events_path(state_root: str) -> str:
    """The one project-level event log. A single log (not one per sprint) keeps the
    progress report a single read and makes cross-epic velocity computable."""
    return os.path.join(state_root, EVENTS_FILENAME)


def append_event(state_root: str, payload: dict) -> None:
    """Append one JSON line under flock. NEVER raises: telemetry must not be able to
    fail a status write, matching the calibration contract in set-actual."""
    try:
        p = events_path(state_root)
        os.makedirs(os.path.dirname(os.path.abspath(p)) or ".", exist_ok=True)
        line = json.dumps(payload, sort_keys=True) + "\n"
        try:
            import fcntl
        except ImportError:  # pragma: no cover - non-POSIX
            fcntl = None
        with open(p, "a", encoding="utf-8") as fh:
            if fcntl is not None:
                fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                fh.write(line)
                fh.flush()
            finally:
                if fcntl is not None:
                    fcntl.flock(fh, fcntl.LOCK_UN)
    except Exception as e:  # noqa: BLE001 - deliberate: never fail the caller
        sys.stderr.write(f"pm-status.py: warning — could not append event: {e}\n")


def _event_keys(kind: str, args) -> dict:
    """Node-identifying fields for an event payload, by node kind."""
    if kind == "story":
        epic_key, sprint_key, _ = parse_story_key(args.story)
        return {"node": "story", "key": args.story, "epic": epic_key, "sprint": sprint_key}
    if kind == "sprint":
        return {"node": "sprint", "key": args.sprint, "epic": args.epic, "sprint": args.sprint}
    return {"node": "epic", "key": args.epic, "epic": args.epic, "sprint": None}


# Fixed thresholds, in hours. Deliberately not configurable in this iteration: the
# calibration data needed to tune them is what this report will generate.
STUCK_THRESHOLDS = {
    ("story", "in-progress"): 4.0,
    ("story", "review"): 4.0,
    ("sprint", "in-progress"): 24.0,
    ("epic", "in-progress"): 72.0,
}


def _parse_iso(ts):
    """Parse a pm-status timestamp into an aware datetime, or None if unusable."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


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
                prev = idx.get(ev["key"])
                if prev is None or str(ev.get("ts", "")) >= str(prev.get("ts", "")):
                    idx[ev["key"]] = ev
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
    for k in ("epic", "sprint", "story"):
        v = getattr(args, k, None)
        if v:
            payload[k] = v
    append_event(args.state_root, payload)
    sys.stdout.write(f"OK dispatch {args.event} {args.agent}\n")
    return 0


def _dispatch_identity(rec: dict) -> tuple:
    """What makes two dispatch records the same dispatch. Agent plus node keys —
    a story-level retry of the same agent reuses the identity deliberately, so a
    close always cancels the most recent matching open."""
    return (rec.get("agent"), rec.get("epic"), rec.get("sprint"), rec.get("story"))


def open_dispatches(state_root: str, threshold_minutes: float, now=None) -> list:
    """Dispatches opened and never closed, older than the threshold, oldest first.

    Cannot interrupt a hang — makes it visible. A close with no matching open is
    ignored rather than treated as an error: events.jsonl is append-only and may
    begin mid-run on a pre-existing project.

    Reads defensively, exactly as `build_events_index` does over the same file:
    the log is appended to by concurrent flock'd writers and is documented as
    possibly torn, so a valid-JSON line that is not an object (a bare `42` from a
    torn write or a hand-edit) must be skipped, not dereferenced, and an OSError
    must warn rather than abort. This is the read behind `report --watch`, the
    stall dashboard — a crash here takes down precisely the surface the stall
    feature exists to provide.
    """
    path = events_path(state_root)
    if not os.path.exists(path):
        return []
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
    if now is None:
        now = datetime.now(timezone.utc)
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
    now = now or datetime.now(timezone.utc)
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


def _epic_path_or_die(args) -> str:
    """Resolve epic path from args.state_root and args.epic; exit 3 if not found."""
    p = epic_file(args.state_root, args.epic)
    if p is None:
        _die_notfound(f"epic {args.epic}")
    return p


# --------------------------------------------------------------------------- #
# computed roll-ups — sprint/epic aggregates over per-story child files
# --------------------------------------------------------------------------- #
def list_sprint_dirs(state_root: str, epic_key: str) -> list:
    """Sorted sprint directories for an epic. Lexical sort is correct order (zero-padded)."""
    d = find_epic_dir(state_root, epic_key)
    if d is None:
        return []
    return sorted(os.path.join(d, n) for n in os.listdir(d)
                  if n.startswith("sprint-") and os.path.isdir(os.path.join(d, n)))


def _sprint_key_from_dir(sprint_dir_path: str) -> str:
    """'.../epic-001/sprint-01' -> 'S01'. Inverse of sprint_dirname for a path from
    list_sprint_dirs."""
    return "S" + os.path.basename(sprint_dir_path).split("-")[1]


# --------------------------------------------------------------------------- #
# Calibration — the learning loop. See references/metrics-contract.md §8.
# The file is a SHARED append target: every set-actual across parallel
# subagents may append to it, so the WHOLE read-modify-write cycle runs under
# one exclusive lock (`calibration_lock`) — not just the write. Locking only
# the write let two concurrent samplers each read the same pre-append state and
# the second one silently clobber the first's sample. Unlike node files, which
# are sharded per story precisely to avoid contention.
# --------------------------------------------------------------------------- #
CALIBRATION_SCHEMA_VERSION = 2
MIN_SAMPLES = 3          # a component below this is recorded but not applied
DECAY = 0.8              # exponential decay, applied oldest-first
COLD_START_SCOPE_RATIO = 1.0
COLD_START_FIX_FACTOR = 1.25
CLASSIFICATIONS = ("simple", "standard", "complex")
CLOSURE_LEVELS = ("sprint", "epic")


def calibration_path(state_root: str) -> str:
    return os.path.join(state_root, "pm-calibration.yaml")


def new_calibration(granularity: str = "story"):
    from ruamel.yaml.comments import CommentedMap
    cal = CommentedMap()
    cal["version"] = CALIBRATION_SCHEMA_VERSION
    cal["granularity"] = granularity
    cal["scope"] = CommentedMap((c, CommentedMap()) for c in CLASSIFICATIONS)
    cal["closure"] = CommentedMap((lv, CommentedMap()) for lv in CLOSURE_LEVELS)
    cal["fix"] = CommentedMap((c, CommentedMap()) for c in CLASSIFICATIONS)
    # Unlike closure, orchestration has no estimated band to measure a ratio
    # against (it ships null by design — see record_orchestration_sample), so
    # it is seeded empty here and filled by set-actual --block orchestration.
    cal["orchestration"] = CommentedMap((lv, CommentedMap()) for lv in CLOSURE_LEVELS)
    return cal


def load_calibration(state_root: str):
    """Load the calibration file, or a fresh skeleton if absent. Never raises."""
    p = calibration_path(state_root)
    y, data = _load(p)
    if data is None:
        return _yaml(), new_calibration()
    for key, default in (("scope", CLASSIFICATIONS), ("fix", CLASSIFICATIONS),
                         ("closure", CLOSURE_LEVELS), ("orchestration", CLOSURE_LEVELS)):
        if key not in data or data[key] is None:
            from ruamel.yaml.comments import CommentedMap
            data[key] = CommentedMap((k, CommentedMap()) for k in default)
    if "granularity" not in data:
        data["granularity"] = "story"
    return y, data


# Re-entrant within a process: flock is held per open file description, so a
# second open()+LOCK_EX from the same process would deadlock against itself.
# The depth counter lets save_calibration nest inside calibration_lock (which
# is exactly what the record_* paths do) without reacquiring.
_CAL_LOCK = {"depth": 0, "fh": None}


@contextlib.contextmanager
def calibration_lock(state_root: str):
    """Hold an exclusive lock over a whole calibration read-modify-write cycle.

    `save_calibration` alone is not enough: load -> mutate -> save is not atomic,
    so two parallel `set-actual` calls could both load the same file and the
    second save would drop the first's sample. Callers that mutate must wrap the
    load AND the save in this.
    """
    if _CAL_LOCK["depth"] > 0:                 # already held by this process
        _CAL_LOCK["depth"] += 1
        try:
            yield
        finally:
            _CAL_LOCK["depth"] -= 1
        return
    try:
        import fcntl
    except ImportError:  # pragma: no cover - non-POSIX
        sys.stderr.write("pm-status.py: fcntl unavailable — calibration write is "
                         "not lock-protected (non-POSIX)\n")
        yield
        return
    lock_path = calibration_path(state_root) + ".lock"
    os.makedirs(os.path.dirname(os.path.abspath(lock_path)) or ".", exist_ok=True)
    fh = open(lock_path, "w")
    fcntl.flock(fh, fcntl.LOCK_EX)
    _CAL_LOCK["depth"], _CAL_LOCK["fh"] = 1, fh
    try:
        yield
    finally:
        _CAL_LOCK["depth"], _CAL_LOCK["fh"] = 0, None
        try:
            fcntl.flock(fh, fcntl.LOCK_UN)
        finally:
            fh.close()


def save_calibration(y, cal, state_root: str) -> None:
    """Always locked — this file is written from every set-actual."""
    with calibration_lock(state_root):
        _atomic_dump(y, cal, calibration_path(state_root))


def migrate_calibration(y, cal, state_root: str):
    """version 1 -> 2. Original preserved as .v1 and never read again."""
    if cal.get("version") == CALIBRATION_SCHEMA_VERSION:
        return cal
    p = calibration_path(state_root)
    backup = p + ".v1"
    if os.path.exists(p) and not os.path.exists(backup):
        import shutil
        shutil.copy2(p, backup)
    blended = cal.get("ratio")
    fresh = new_calibration(cal.get("granularity", "story"))
    # The old blended figure maps onto scope only. closure and fix start at
    # zero samples: the v1 file cannot separate them, and seeding from a
    # blended number would import exactly the bias the split removes.
    if isinstance(blended, (int, float)):
        from ruamel.yaml.comments import CommentedMap
        for c in CLASSIFICATIONS:
            entry = CommentedMap()
            entry["samples"] = [float(blended)]
            fresh["scope"][c] = CommentedMap((("man_hours", entry),))
    save_calibration(y, fresh, state_root)
    return fresh


def weighted_ratio(samples: list) -> float:
    """Exponential-decay weighted mean, oldest first (most recent weighs most)."""
    vals = [float(s) for s in samples if _is_number(s)]
    if not vals:
        return None
    n = len(vals)
    num = den = 0.0
    for i, v in enumerate(vals):
        w = DECAY ** (n - 1 - i)
        num += v * w
        den += w
    return num / den if den else None


# A calibration sample outside this range is not wrong by construction — it
# is a ratio (actual/estimate-ish, see derive_story_sample), and most real
# ratios sit near 1.0 — but one this far off is exactly the shape a story
# sample would have if orchestration-shaped overhead (a defect this rework
# separately isolates into its own `orchestration` component) leaked into
# it under the old rules. FLAG surfaces that suspicion for human review; it
# never drops or corrects the sample itself.
TOKENS_SANITY_RANGE = (0.5, 2.0)

# Stamped once, at the top level of the calibration file itself, the first
# time migrate_calibration_metrics finishes a real pass over it — including
# a pass that finds nothing to migrate. This is NOT a version bump: `version`
# stays CALIBRATION_SCHEMA_VERSION == 2. A timestamp recording that a reshape
# happened is data about the file, exactly like `orchestration`, `token_mix`,
# and `legacy` below — not a schema generation.
#
# This replaces an earlier, REJECTED design that inferred "already migrated"
# from the presence/absence of the old `cost`/`time_hours` keys. That
# inference has a silent blind spot: a non-Claude-runtime project never
# accumulates `cost` samples (cost is N/A there and skipped by calibration),
# so a file that also happens to have no `time_hours` samples — for any
# reason — would read as "already migrated" under that design and never have
# its old-definition `man_hours`/`fix` samples quarantined. No error, no log
# line, just silently wrong ratios applied to every future estimate — the
# exact failure this migration exists to prevent. A positive marker has no
# such blind spot: its absence always means "run it," regardless of which
# sample types the file happens to contain.
CALIBRATION_METRICS_MARKER = "metrics_migrated_at"


def migrate_calibration_metrics(y, cal, state_root: str) -> list:
    """Reshape a pre-metrics-rework calibration file in place. Returns a
    change log (empty when there was nothing to migrate).

    Gated on CALIBRATION_METRICS_MARKER, a positive marker stamped at the end
    of every real pass through this function — even a no-op one. A brand-new
    project has nothing to migrate on its first write, but still gets
    stamped right there, before that same write appends its first (entirely
    legitimate) sample: this is what stops a LATER real man_hours or fix
    sample from ever being revisited and wrongly quarantined (see
    test_man_hours_written_after_the_one_time_cutover_is_never_revisited).

    Once past the gate, `man_hours` and `fix` quarantine UNCONDITIONALLY —
    no corroborating cost/time_hours marker is required in the same bucket
    or file (see test_man_hours_quarantined_even_without_cost_or_time_hours_markers,
    the case that falsified an earlier key-presence-based design). `version`
    stays 2 throughout: compatibility is by shape-tolerant reads, never a
    version gate.
    """
    if cal.get(CALIBRATION_METRICS_MARKER):
        return []

    log = []
    p = calibration_path(state_root)
    backup = p + ".pre-metrics"
    if os.path.exists(p) and not os.path.exists(backup):
        import shutil
        shutil.copy2(p, backup)
        log.append(f"backup {os.path.basename(backup)}")

    def _reshape(component: str):
        buckets = cal.get(component) or {}
        for bucket, metrics in list(buckets.items()):
            if not hasattr(metrics, "items"):
                continue
            if "cost" in metrics:
                del metrics["cost"]
                log.append(f"DROP {component}.{bucket}.cost (derived from tokens x rates "
                           f"since Task 10 — never independently calibrated again)")
            if "time_hours" in metrics:
                metrics["elapsed_hours"] = metrics.pop("time_hours")
                log.append(f"RENAME {component}.{bucket}.time_hours -> elapsed_hours")
            if "man_hours" in metrics:
                from ruamel.yaml.comments import CommentedMap
                dest = (cal.setdefault("legacy", CommentedMap())
                           .setdefault(component, CommentedMap())
                           .setdefault(bucket, CommentedMap()))
                dest["man_hours"] = metrics.pop("man_hours")
                log.append(f"QUARANTINE {component}.{bucket}.man_hours (definition changed: "
                           f"human attention -> counterfactual developer effort — old "
                           f"samples are incomparable, preserved under legacy.{component}.{bucket})")
            samples = list((metrics.get("tokens_k") or {}).get("samples") or [])
            if samples:
                r = weighted_ratio(samples)
                if r is not None and not (TOKENS_SANITY_RANGE[0] <= r <= TOKENS_SANITY_RANGE[1]):
                    log.append(
                        f"FLAG {component}.{bucket}.tokens_k ratio={r:.2f} outside "
                        f"{TOKENS_SANITY_RANGE} — carried forward as-is, but review "
                        f"before trusting (possible orchestration overhead swept "
                        f"into story samples under the old rules)")

    for component in ("scope", "closure"):
        _reshape(component)

    fix = cal.get("fix") or {}
    fix_had_content = any(bool(v) for v in fix.values())
    if fix_had_content:
        from ruamel.yaml.comments import CommentedMap
        cal.setdefault("legacy", CommentedMap())["fix"] = fix
        cal["fix"] = CommentedMap((c, CommentedMap()) for c in CLASSIFICATIONS)
        log.append("QUARANTINE fix (wholesale — every cohort is measured in "
                   "mean_man_hours, the same definition change as scope/closure "
                   "man_hours; fix has no per-metric split to act on selectively, "
                   "preserved under legacy.fix)")

    # token_mix seeding stays tied to "did this pass actually find and move
    # legacy content" (log non-empty), NOT to the marker gate above: seeding
    # it unconditionally on every first-ever pass (including a no-op one on
    # a brand-new project) would recreate the exact conflict Task 9 hit and
    # routed around for new_calibration — see
    # test_record_skips_token_mix_when_actual_lacks_a_total, which asserts
    # token_mix stays ABSENT on a fresh project's first write when there is
    # nothing to observe yet.
    if log and "token_mix" not in cal:
        from ruamel.yaml.comments import CommentedMap
        cal["token_mix"] = CommentedMap((("samples", []),))
        log.append("SEED token_mix (empty — new component, nothing to migrate from)")

    cal[CALIBRATION_METRICS_MARKER] = _now_iso()
    return log


def _component_samples(cal, component: str, bucket: str, metric: str) -> list:
    node = ((cal.get(component) or {}).get(bucket) or {}).get(metric) or {}
    return list(node.get("samples") or [])


def active_scope_ratio(cal, classification: str, metric: str):
    s = _component_samples(cal, "scope", classification, metric)
    return weighted_ratio(s) if len(s) >= MIN_SAMPLES else None


def active_closure_ratio(cal, level: str, metric: str):
    s = _component_samples(cal, "closure", level, metric)
    return weighted_ratio(s) if len(s) >= MIN_SAMPLES else None


def active_orchestration_fraction(cal, level: str, metric: str):
    """Learned orchestration overhead as a FRACTION of the children's total.

    Every other component here (scope, closure) learns a RATIO: actual over
    an estimate, correcting a number that already exists. Orchestration has
    no such number to correct — the band ships `null` (spec §6.4) because
    every measurement available at design time was contaminated by an
    operational defect (repeated cache-eviction on blocking waits), and
    sizing a prior on contaminated data would commit that bug to every future
    estimate. So there is nothing to measure a ratio against, and a
    ratio-based component could never bootstrap from its first sample.

    Instead the sample IS the band: orchestration_actual / sum(children
    actual), directly observable from the first closed sprint or epic. A
    future maintainer tempted to "fix" this into a ratio for consistency with
    closure would remove the one thing that lets it start learning at all.

    None until MIN_SAMPLES, same decay as every other component.
    """
    samples = _component_samples(cal, "orchestration", level, metric)
    return weighted_ratio(samples) if len(samples) >= MIN_SAMPLES else None


def active_fix_factor(cal, classification: str):
    """Needs BOTH cohorts at threshold — one cohort alone cannot form a ratio."""
    entry = (cal.get("fix") or {}).get(classification) or {}
    clean, rework = entry.get("clean") or {}, entry.get("reworked") or {}
    if int(clean.get("samples", 0)) < MIN_SAMPLES or int(rework.get("samples", 0)) < MIN_SAMPLES:
        return None
    cm, rm = clean.get("mean_man_hours"), rework.get("mean_man_hours")
    if not _is_number(cm) or not _is_number(rm) or float(cm) == 0:
        return None
    return float(rm) / float(cm)


def _num_or_none(v):
    """Parse a metric value, tolerating a leading '$' on cost. None if not numeric.

    Normalizing before the numeric guard (rather than after) matters: a
    check-then-lstrip order lets a '$'-prefixed cost fail _is_number and get
    skipped before the lstrip ever runs, silently starving the cost
    component of samples. This is the single normalization both the guard
    and the parse share, so they can't disagree.
    """
    if v is None or _is_na(v):
        return None
    s = str(v).strip().lstrip("$")
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _applied_scope_ratio(est, metric):
    """The scope ratio that was applied to `metric` when this estimate was written.

    `estimate-story` records one ratio PER METRIC (`scope_ratios`), because the
    five metrics calibrate independently. A single scalar `scope_ratio` is the
    older/manual form (`set-estimate --scope-ratio`) and is accepted as a
    fallback for every metric. Missing entirely -> 1.0.
    """
    m = est.get("scope_ratios")
    if hasattr(m, "get"):
        v = _num_or_none(m.get(metric))
        if v is not None and v > 0:
            return v
    v = _num_or_none(est.get("scope_ratio"))
    return v if v is not None and v > 0 else 1.0


def _actual_metric(actual: dict, metric: str):
    """A metric's numeric actual. tokens_k is a mapping now — the total is what
    is banded and calibrated; the class split prices cost and nothing else.
    """
    v = (actual or {}).get(metric)
    if metric == "tokens_k" and hasattr(v, "get"):
        v = v.get("total")
    return _num_or_none(v)


def _estimate_metric(est: dict, metric: str):
    """A metric's numeric value from an ESTIMATE block. The single-value
    (story) form of `tokens_k` is a MAPPING (`tokens_block`'s `total` + the
    four per-class counts, since Tasks 6/7) — the same shape `_actual_metric`
    unwraps above, mirrored here for the estimate side.

    EVERY reader of an estimate's tokens_k must go through this, never
    `_num_or_none(est.get(metric))` directly. That direct form is exactly what
    silently zeroed two independent things before Task 10 found and fixed the
    first: `_child_estimate_value` (a sprint/epic roll-up would see zero
    children with a tokens_k estimate, `estimate-rollup` would just never emit
    `tokens_k_min`/`tokens_k_max`) and `derive_story_sample` (a story's
    tokens_k scope ratio never accumulated a sample — cold-start forever,
    silently, for the metric the whole cost derivation now hangs off). Both
    call sites now route through here so a fourth instance can't reintroduce
    the same blind spot by hand-duplicating the unwrap.
    """
    v = (est or {}).get(metric)
    if metric == "tokens_k" and hasattr(v, "get"):
        v = v.get("total")
    return _num_or_none(v)


def derive_story_sample(node):
    """Compute a story's scope samples and its fix cohort. None when not derivable.

    THE SAMPLE MUST BE MEASURED AGAINST THE BASE BAND, NOT AGAINST THE LAST
    ESTIMATE. The estimate is `band_mid x scope_ratio_applied x fix_factor`, so a
    raw `actual / estimate` (or `actual x fix / estimate`) measures error against
    an estimate that already contains the previous ratio. Feeding that back as
    the next ratio makes the loop converge to sqrt(truth / band_mid) — a
    permanent underestimate no volume of data closes — and means a perfect
    estimate never produces a neutral sample. Dividing the applied ratio back
    out fixes both:

      exact   (fix_iterations == 0, the actual is pure scope):
          sample = actual x scope_ratio_applied x fix_factor / estimate
                 = actual / band_mid
      backout (rework present or unknown — the actual mixes scope and rework):
          scope portion is actual / fix_factor, so the fix factor cancels:
          sample = actual x scope_ratio_applied / estimate
                 = actual / (band_mid x fix_factor)
      legacy  (estimate predates the recorded factors): both default to 1.0,
          sample = actual / estimate, labelled `legacy` so an audit can tell
          the imprecision apart.
    """
    if not node:
        return None
    est, act = node.get("estimate") or {}, node.get("actual") or {}
    if not est or not act:
        return None

    iters = ((node.get("completion_evidence") or {}).get("fix_iterations"))
    has_factors = _is_number(est.get("fix_factor"))
    fix_factor = float(est["fix_factor"]) if has_factors else 1.0

    if not has_factors:
        provenance = "legacy"
    elif _is_number(iters) and int(iters) == 0:
        provenance = "exact"
    else:
        provenance = "backout"

    ratios = {}
    for metric in CALIBRATED_METRIC_FIELDS:
        e_num, a_num = _estimate_metric(est, metric), _actual_metric(act, metric)
        if e_num is None or a_num is None:
            continue          # missing, N/A, or non-numeric — never coerced to zero
        if e_num == 0:
            continue
        applied = _applied_scope_ratio(est, metric) if has_factors else 1.0
        if provenance == "backout":
            # actual/fix_factor is the scope portion; the fix_factor cancels.
            ratios[metric] = a_num * applied / e_num
        else:
            ratios[metric] = a_num * applied * fix_factor / e_num

    if not ratios:
        return None
    return {
        "classification": str(node.get("classification", "standard")),
        "provenance": provenance,
        "fix_iterations": int(iters) if _is_number(iters) else None,
        "scope_ratios": ratios,
        "actual_man_hours": float(act["man_hours"]) if _is_number(act.get("man_hours")) else None,
    }


def _bump_cohort(entry, cohort: str, man_hours):
    """Running mean over a cohort, so a full sample history is not needed."""
    from ruamel.yaml.comments import CommentedMap
    c = entry.get(cohort)
    if c is None:
        c = CommentedMap()
        c["mean_man_hours"] = 0.0
        c["samples"] = 0
        entry[cohort] = c
    if man_hours is None:
        return
    n = int(c.get("samples", 0))
    mean = float(c.get("mean_man_hours", 0.0))
    c["mean_man_hours"] = round((mean * n + man_hours) / (n + 1), 4)
    c["samples"] = n + 1


CALIBRATION_MARKER = "calibration_sampled_at"
# The orchestration sample is a SEPARATE fact from the actual/closure sample,
# and a sprint or epic node can carry both — one marker cannot gate both
# without one silently suppressing the other (a closed sprint's closure
# sample would forever block its later orchestration sample, or vice versa).
# So orchestration gets its own marker, using the exact same guard mechanism
# below (a `marker` parameter), rather than a second copy of the mechanism.
ORCHESTRATION_MARKER = "orchestration_sampled_at"


def _already_sampled(node, marker=CALIBRATION_MARKER):
    """The replay guard: a node that already emitted its sample carries a marker."""
    v = (node or {}).get(marker)
    return str(v) if v else None


def _mark_sampled(node, node_path, y=None, marker=CALIBRATION_MARKER) -> None:
    """Stamp the node so a second set-actual on it cannot double-count.

    Idempotency lives on the node, not in the caller: `--no-calibrate` only
    helps someone who remembers to pass it, and a duplicated sample is
    invisible afterwards.
    """
    if node is None or not node_path:
        return
    node[marker] = _now_iso()
    _atomic_dump(y or _yaml(), node, node_path)


def record_story_sample(state_root: str, node, node_path: str = None, y=None) -> str:
    """Derive a story's calibration sample and append it to the shared file.

    A write path, unlike load_calibration: migrates a stale schema version
    before appending, so a v1 file is never mistaken for v2 and corrupted by
    samples landing in a structure that doesn't exist there yet. The whole
    load->mutate->save runs under one exclusive lock so parallel samplers
    cannot clobber each other's appends.
    """
    prior = _already_sampled(node)
    if prior:
        return f"sample already recorded at {prior} — skipped (replay)"
    sample = derive_story_sample(node)
    if sample is None:
        return "no sample (missing estimate or actual)"
    from ruamel.yaml.comments import CommentedMap
    with calibration_lock(state_root):
        y_cal, cal = load_calibration(state_root)
        if cal.get("version") != CALIBRATION_SCHEMA_VERSION:
            cal = migrate_calibration(y_cal, cal, state_root)
        for line in migrate_calibration_metrics(y_cal, cal, state_root):
            sys.stderr.write(f"pm-status.py: calibration migration: {line}\n")
        cls = sample["classification"]

        bucket = cal["scope"].setdefault(cls, CommentedMap())
        for metric, ratio in sample["scope_ratios"].items():
            entry = bucket.setdefault(metric, CommentedMap())
            entry.setdefault("samples", [])
            entry["samples"].append(round(ratio, 4))

        # The observed per-class split, as a fraction of the actual's total —
        # feeds observed_mix() once 3 samples accrue, superseding
        # COLD_START_TOKEN_MIX. Independent of the scope-ratio samples above:
        # this is about how a token total divides across classes, not about
        # how big the total itself is.
        tk = (node.get("actual") or {}).get("tokens_k")
        if hasattr(tk, "get"):
            total = _num_or_none(tk.get("total"))
            if total and total > 0:
                mix_bucket = cal.setdefault("token_mix", CommentedMap())
                mix_bucket.setdefault("samples", [])
                mix_bucket["samples"].append(
                    {c: round((_num_or_none(tk.get(c)) or 0.0) / total, 4) for c in TOKEN_CLASSES})

        fix_entry = cal["fix"].setdefault(cls, CommentedMap())
        iters = sample["fix_iterations"]
        if iters is not None:
            _bump_cohort(fix_entry, "clean" if iters == 0 else "reworked",
                         sample["actual_man_hours"])

        save_calibration(y_cal, cal, state_root)
    _mark_sampled(node, node_path, y)
    return (f"scope+{len(sample['scope_ratios'])} metrics, "
            f"provenance={sample['provenance']}, class={cls}")


def _mid(est, low_key: str, high_key: str):
    """Midpoint of a range-form estimate. None if either bound is missing/non-numeric."""
    lo, hi = _num_or_none(est.get(low_key)), _num_or_none(est.get(high_key))
    if lo is None or hi is None:
        return None
    return (lo + hi) / 2.0


CLOSURE_RANGE_KEYS = {
    "man_hours":     ("man_hours_low", "man_hours_high"),
    "hitl_hours":    ("hitl_hours_low", "hitl_hours_high"),
    "elapsed_hours": ("elapsed_hours_low", "elapsed_hours_high"),
    "tokens_k":      ("tokens_k_min", "tokens_k_max"),
}
# No "cost" row: cost is derived from the rolled-up tokens_k range (see
# cmd_estimate_rollup) rather than banded and calibrated on its own — the
# story-level equivalent of this was already true (BASE_BANDS has no cost
# row either). Keeping a separate closure-cost band was the last place the
# old defect survived: a cost figure with no arithmetic tie to the token
# figure it should track, drifting apart as the two calibrated independently.


# Wall-clock metrics legitimately go NEGATIVE as a closure residual: if a closure
# node's children ever overlap in wall-clock time, the parent's wall-clock can be
# below the sum of its children's by design (today's step files run children
# strictly in order, so this does not arise in practice; the check stays
# defensive). That is topology, not a miscount, and must not be reported as one.
# Man-hours, tokens and cost are additive regardless of concurrency, so a
# negative residual there really is a miscount.
WALL_CLOCK_METRICS = ("elapsed_hours",)


def _closure_nodes(state_root: str, level: str, epic_key: str, sprint_key=None):
    """(parent path, child paths) for a closure sample at `level`."""
    if level == "sprint":
        return (sprint_file(state_root, epic_key, sprint_key),
                list_story_files(state_root, epic_key, sprint_key))
    return (epic_file(state_root, epic_key),
            [sprint_file(state_root, epic_key, _sprint_key_from_dir(d))
             for d in list_sprint_dirs(state_root, epic_key)])


def _skip_summary(skipped: dict) -> str:
    return "; ".join(f"{m}: {r}" for m, r in skipped.items()) or "no metrics available"


def derive_closure_sample(state_root: str, level: str, epic_key: str, sprint_key=None):
    """Closure overhead = parent actual - sum(children actuals). Returns (sample, reason).

    THE RATIO'S DENOMINATOR MUST BE THE QUANTITY THE RATIO IS APPLIED TO.
    `estimate-rollup` applies the learned ratio to the CLOSURE BAND alone
    (`total x (1 + ratio x closure_band + fraction x ORCH_SPREAD)`), so the
    residual has to be divided by the ESTIMATED CLOSURE OVERHEAD ALONE, never
    by the whole parent estimate and never by closure-plus-orchestration.
    Dividing by the whole parent made learn and apply different quantities,
    and a perfectly consistent history moved the estimate AWAY from its own
    observed truth.

    THE ORCHESTRATION BAND IS NOT PART OF THIS DENOMINATOR. Since the
    orchestration term joined the roll-up, `pmid - sum(child estimates)` is
    the closure band PLUS the orchestration band, while the residual it
    divides (`parent actual - sum(children actual)`) is closure-only —
    orchestration lives in its own `orchestration` block, outside `actual`.
    Leaving the orchestration band in the denominator understated every
    closure sample by exactly the factor the two bands differ by (with an
    active fraction of 0.5 and children summing to 20, a true overhead of 5
    recorded as 0.3704 instead of 1.4286 — 3.9x low, and worse as the
    fraction grows). So the applied fraction (`estimate.orchestration_ratios`,
    the same divide-it-back-out record `closure_ratios` and `scope_ratios`
    are) is subtracted back off at its band MIDPOINT (`ORCH_MID`), leaving
    exactly `est_total x closure_ratio_applied x mid(COLD_START_CLOSURE_BAND)`
    — the quantity the closure ratio is applied to and nothing else.

    And, as with the story scope ratio, the estimated overhead already contains
    the ratio that was applied when the parent estimate was written, so that
    ratio is divided back out (`closure_ratios` on the estimate block, 1.0 when
    absent). Without it the loop settles on a geometric mean instead of the
    truth. Concretely: children estimated 40, closure overhead truly 8 every
    time. Estimated overhead cold-start = 47 - 40 = 7, sample 8/7 = 1.143, and
    `40 x (1 + 1.143 x 0.175) = 48.0` — the observed total, and stable on every
    later generation because the applied ratio cancels.

    Guards, each skipping just THAT METRIC with a reason rather than aborting
    the whole sample: any child missing that metric's actual (a partial sum
    understates overhead and biases the ratio low, permanently); a negative
    residual (a miscount — except for wall-clock, where parallel execution makes
    it expected); a ZERO residual (see below); an estimated overhead <= 0
    (nothing to measure against); and N/A tokens, which skips just that metric
    while man-hours still record under non-Claude runtimes where tokens are
    legitimately absent.

    A ZERO RESIDUAL IS A SKIP, NOT A SAMPLE OF 0.0 — and "zero" means within a
    relative tolerance, on both signs, not exactly 0.0 in binary. A parent actual
    equal to the sum of its children means the closure phases' own spend
    (adversarial analysis, retrospective, QA generation — real, measurable
    work) was attributed to nothing. Recording that as a legitimate 0.0
    sample is worse than recording nothing: 0.0 is not None, so after three
    such sprints `active_closure_ratio` returns 0.0, `cmd_estimate_rollup`
    accepts it, and the closure band contributes nothing to any future
    estimate — permanently, with no marker saying why. The step files now
    instruct the parent actual as "sum of children PLUS this level's own
    closure-phase spend" precisely so this does not arise; when it does, it
    is a capture defect and must be reported as one, not learned from. Both
    signs route to that one reason because a bare sum over decimal inputs lands
    on either side of zero depending on the values (0.3 + 0.6 vs 0.9 leaves
    +1.11e-16; 1.1 + 2.2 vs 3.3 leaves -4.44e-16), and calling the second a
    "miscount" would tell the reader something false.

    Iterates CALIBRATED_METRIC_FIELDS, not CLOSURE_RANGE_KEYS or the full
    METRIC_FIELDS: `cost` never produces a closure sample (Task 10) — it is
    derived from the rolled-up tokens_k range at estimate-rollup time, so a
    residual measured against its own band would have nothing left to divide
    against and nothing calibrating it downstream would ever read the sample.
    """
    ppath, child_paths = _closure_nodes(state_root, level, epic_key, sprint_key)
    if ppath is None:
        return None, f"{level} node not found"
    _, pnode = load_node(ppath)
    pact = (pnode or {}).get("actual") or {}
    pest = (pnode or {}).get("estimate") or {}
    if not pact:
        return None, f"{level} has no actual yet"

    children = []
    for cp in child_paths:
        if cp is None:
            children.append(None)
            continue
        _, cn = load_node(cp)
        children.append(cn)

    applied_ratios = pest.get("closure_ratios")
    applied_orch = pest.get("orchestration_ratios")
    closure, ratios, skipped = {}, {}, {}
    for metric in CALIBRATED_METRIC_FIELDS:
        total = 0.0
        complete = True
        for cn in children:
            cv = _actual_metric((cn or {}).get("actual"), metric) if cn is not None else None
            if cv is None:
                complete = False   # missing, N/A, or non-numeric child actual
                break
            total += cv
        if not complete:
            skipped[metric] = "a child is missing this metric's actual"
            continue
        pv = _actual_metric(pact, metric)
        if pv is None:
            skipped[metric] = f"{level} actual is missing or N/A for this metric"
            continue
        residual = pv - total
        # Near-zero is checked FIRST, and on BOTH signs. `residual` is unrounded
        # float arithmetic over decimal inputs, so `== 0` only catches a residual
        # that happens to land exactly on zero in binary. Children of 0.3 and 0.6
        # against a parent written as the bare sum 0.9 leave +1.11e-16, which
        # sails past `== 0` and records three 0.0 samples — C2 reopened, on
        # ordinary tenths-of-an-hour input. The mirror (1.1 + 2.2 vs 3.3) leaves
        # -4.44e-16 and would otherwise be reported as a miscount that did not
        # happen. One relative tolerance, both signs, one reason. The tolerance is
        # relative to the parent so it stays meaningful at any magnitude, and
        # floored at 1.0 so it never collapses to nothing for small values; at
        # 1e-9 it is many orders below the smallest real closure overhead and many
        # above double-precision summation noise.
        if abs(residual) <= 1e-9 * max(1.0, abs(pv)):
            skipped[metric] = (
                f"zero residual (parent {pv} equals children sum {total} to within float "
                f"tolerance) — this {level}'s own closure-phase spend was attributed to "
                f"nothing; a 0.0 sample would train the closure component to zero "
                f"permanently. Re-capture the {level} actual as children + this level's "
                f"closure-phase spend (metrics-contract.md §6)")
            continue
        if residual < 0:
            if metric in WALL_CLOCK_METRICS:
                skipped[metric] = (f"negative wall-clock residual (parent {pv} below children "
                                   f"sum {total}) — expected under parallel execution, not a miscount")
            else:
                skipped[metric] = (f"negative residual (parent {pv} below children sum "
                                   f"{total}) — miscounted")
            continue
        closure[metric] = residual

        lo, hi = CLOSURE_RANGE_KEYS[metric]
        pmid = _mid(pest, lo, hi)
        if pmid is None:
            skipped[metric] = f"{level} has no estimate range for this metric"
            continue
        est_total, all_est = 0.0, True
        for cn in children:
            v = _child_estimate_value(cn, metric) if cn is not None else None
            if v is None:
                all_est = False
                break
            est_total += v
        if not all_est:
            skipped[metric] = "a child is missing this metric's estimate"
            continue
        # Back out the orchestration band before dividing: `pmid - est_total` is
        # closure band PLUS orchestration band, and `residual` is closure-only.
        orch_f = 0.0
        if hasattr(applied_orch, "get"):
            f = _num_or_none(applied_orch.get(metric))
            if f is not None and f > 0:
                orch_f = f
        expected = pmid - est_total - est_total * orch_f * ORCH_MID
        if expected <= 0:
            skipped[metric] = (f"estimated closure overhead is {round(expected, 4)} (<= 0) — "
                               f"nothing to measure the residual against")
            continue
        applied = 1.0
        if hasattr(applied_ratios, "get"):
            a = _num_or_none(applied_ratios.get(metric))
            if a is not None and a > 0:
                applied = a
        ratios[metric] = residual * applied / expected

    if not closure:
        return None, "no metric produced a closure residual — " + _skip_summary(skipped)
    return {"level": level, "closure_actual": closure, "ratios": ratios,
            "skipped": skipped}, "ok"


def record_closure_sample(state_root: str, level: str, epic_key: str, sprint_key=None) -> str:
    """Derive a sprint/epic's closure sample and append it to the shared file.

    A write path, unlike load_calibration: migrates a stale schema version
    before appending, so a v1 file is never mistaken for v2 and corrupted by
    samples landing in a structure that doesn't exist there yet.
    """
    ppath, _ = _closure_nodes(state_root, level, epic_key, sprint_key)
    y_node, pnode = load_node(ppath) if ppath else (None, None)
    prior = _already_sampled(pnode)
    if prior:
        return f"sample already recorded at {prior} — skipped (replay)"

    sample, reason = derive_closure_sample(state_root, level, epic_key, sprint_key)
    if sample is None:
        return f"no closure sample: {reason}"
    if not sample["ratios"]:
        return "no closure sample: " + _skip_summary(sample["skipped"])

    from ruamel.yaml.comments import CommentedMap
    with calibration_lock(state_root):
        y, cal = load_calibration(state_root)
        if cal.get("version") != CALIBRATION_SCHEMA_VERSION:
            cal = migrate_calibration(y, cal, state_root)
        for line in migrate_calibration_metrics(y, cal, state_root):
            sys.stderr.write(f"pm-status.py: calibration migration: {line}\n")
        bucket = cal["closure"].setdefault(level, CommentedMap())
        for metric, ratio in sample["ratios"].items():
            entry = bucket.setdefault(metric, CommentedMap())
            entry.setdefault("samples", [])
            entry["samples"].append(round(ratio, 4))
        save_calibration(y, cal, state_root)
    _mark_sampled(pnode, ppath, y_node)
    note = f"closure {level} +{len(sample['ratios'])} metrics"
    if sample["skipped"]:
        note += f" (skipped — {_skip_summary(sample['skipped'])})"
    return note


def record_orchestration_sample(state_root: str, level: str, epic_key: str,
                                 sprint_key=None) -> str:
    """Append one closed sprint/epic's orchestration-vs-children fraction.

    THE FRACTION, NOT A RATIO. Every other component here (scope, closure)
    learns a ratio — actual over an ESTIMATE, correcting a number that
    already exists. Orchestration has nothing to correct: the band ships
    `null` by design, because every number available when this was built was
    contaminated by an operational defect (roughly thirty blocking waits each
    outlived the prompt cache and re-created a ~93k-token prefix), and sizing
    a prior on that would commit the bug to every future estimate. So there
    is no estimate to divide by, and a ratio-based component could never
    bootstrap — it would need the very thing it doesn't have. Instead the
    sample IS the band: orchestration_actual / sum(children actual), directly
    observable from the first closed sprint or epic. Do not "fix" this into a
    ratio for consistency with closure — that would remove the one thing
    that lets it start learning at all.

    THE DENOMINATOR MUST BE COMPLETE, per metric, the same guard
    derive_closure_sample applies to its residual: if any child that exists
    is missing that metric's actual, the sum silently understates the true
    total and the fraction is inflated — a wrong number that looks right, and
    permanently so once it feeds calibration. So a metric is sampled only
    when EVERY child carries a numeric actual for it; a partial sum is
    treated as no sample, not as a smaller one.

    `cost` is deliberately absent from CALIBRATED_METRIC_FIELDS: it is
    derived from tokens x rates, so its fraction is already implied by the
    tokens_k fraction and a second, independently-drifting copy would add
    nothing but disagreement.

    REPLAY-GUARDED, like every other record_*_sample here: a second
    `set-actual --block orchestration` on the same node (a retry, a
    corrected number, a replayed closure step) must not append a second
    sample and skew the learned fraction with nothing on disk to explain it.
    Gated on its own ORCHESTRATION_MARKER rather than the closure/story
    CALIBRATION_MARKER, because a sprint or epic node carries both an
    actual/closure sample and an orchestration sample — one marker would let
    whichever writes first silently suppress the other. `_closure_nodes`
    resolves the same parent path for both sprint and epic level, so this
    one guard covers both without a level-specific branch.
    """
    ppath, cpaths = _closure_nodes(state_root, level, epic_key, sprint_key)
    if ppath is None:
        return ""
    y_node, pnode = load_node(ppath)
    prior = _already_sampled(pnode, marker=ORCHESTRATION_MARKER)
    if prior:
        return f"sample already recorded at {prior} — skipped (replay)"
    orch = (pnode or {}).get("orchestration") or {}
    if not orch:
        return ""

    children = []
    for cp in cpaths:
        if cp is None:
            children.append(None)
            continue
        _, cn = load_node(cp)
        children.append(cn)

    from ruamel.yaml.comments import CommentedMap
    recorded, skipped = {}, {}
    for metric in CALIBRATED_METRIC_FIELDS:
        over = _actual_metric(orch, metric)
        if over is None:
            continue  # orchestration itself has no actual for this metric
        total, complete = 0.0, True
        for cn in children:
            cv = _actual_metric((cn or {}).get("actual"), metric) if cn is not None else None
            if cv is None:
                complete = False
                break
            total += cv
        if not complete:
            skipped[metric] = "a child is missing this metric's actual"
            continue
        if total <= 0:
            skipped[metric] = "children's total is zero or negative — nothing to divide by"
            continue
        recorded[metric] = round(over / total, 4)

    if not recorded:
        return "" if not skipped else "no orchestration sample: " + _skip_summary(skipped)

    with calibration_lock(state_root):
        y, cal = load_calibration(state_root)
        if cal.get("version") != CALIBRATION_SCHEMA_VERSION:
            cal = migrate_calibration(y, cal, state_root)
        for line in migrate_calibration_metrics(y, cal, state_root):
            sys.stderr.write(f"pm-status.py: calibration migration: {line}\n")
        bucket = cal.setdefault("orchestration", CommentedMap()).setdefault(level, CommentedMap())
        for metric, frac in recorded.items():
            entry = bucket.setdefault(metric, CommentedMap())
            entry.setdefault("samples", [])
            entry["samples"].append(frac)
        save_calibration(y, cal, state_root)
    _mark_sampled(pnode, ppath, y_node, marker=ORCHESTRATION_MARKER)

    note = f"orchestration {level} +{len(recorded)} metrics"
    if skipped:
        note += f" (skipped — {_skip_summary(skipped)})"
    return note


def cmd_calibration(args) -> int:
    if getattr(args, "action", "show") == "migrate-metrics":
        with calibration_lock(args.state_root):
            y, cal = load_calibration(args.state_root)
            if cal.get("version") != CALIBRATION_SCHEMA_VERSION:
                cal = migrate_calibration(y, cal, args.state_root)
            log = migrate_calibration_metrics(y, cal, args.state_root)
            save_calibration(y, cal, args.state_root)
        for line in log:
            sys.stdout.write(line + "\n")
        sys.stdout.write(f"OK calibration migrate-metrics ({len(log)} changes)\n")
        return 0

    _, cal = load_calibration(args.state_root)
    exists = os.path.exists(calibration_path(args.state_root))
    rows = []
    for c in CLASSIFICATIONS:
        for m in CALIBRATED_METRIC_FIELDS:  # cost never scope-calibrates (derived, see above)
            n = len(_component_samples(cal, "scope", c, m))
            r = active_scope_ratio(cal, c, m)
            rows.append(("scope", f"{c}/{m}", n, r))
    for lv in CLOSURE_LEVELS:
        # Closure no longer calibrates `cost` on its own (Task 10): the rolled-up
        # cost is now derived from the rolled-up tokens_k range, so this loop
        # moves onto CALIBRATED_METRIC_FIELDS like the scope loop above, rather
        # than the full METRIC_FIELDS it used while closure cost was still real.
        for m in CALIBRATED_METRIC_FIELDS:
            n = len(_component_samples(cal, "closure", lv, m))
            r = active_closure_ratio(cal, lv, m)
            rows.append(("closure", f"{lv}/{m}", n, r))
    for lv in CLOSURE_LEVELS:
        # Orchestration never calibrates `cost` (derived from tokens x
        # rates — see record_orchestration_sample), so this loop uses
        # CALIBRATED_METRIC_FIELDS, exactly like the scope and closure loops
        # above. All three agree; none of them iterates the full METRIC_FIELDS
        # any more.
        for m in CALIBRATED_METRIC_FIELDS:
            n = len(_component_samples(cal, "orchestration", lv, m))
            r = active_orchestration_fraction(cal, lv, m)
            rows.append(("orchestration", f"{lv}/{m}", n, r))
    for c in CLASSIFICATIONS:
        entry = (cal.get("fix") or {}).get(c) or {}
        n = min(int((entry.get("clean") or {}).get("samples", 0)),
                int((entry.get("reworked") or {}).get("samples", 0)))
        rows.append(("fix", c, n, active_fix_factor(cal, c)))

    if getattr(args, "format", "text") == "json":
        import json
        sys.stdout.write(json.dumps({
            "exists": exists,
            "granularity": cal.get("granularity", "story"),
            "components": [{"component": a, "bucket": b, "samples": n,
                            "active_ratio": r} for a, b, n, r in rows],
        }, indent=2) + "\n")
        return 0

    if not exists:
        sys.stdout.write("No calibration file yet — all components cold-start.\n")
    sys.stdout.write(f"granularity: {cal.get('granularity', 'story')}\n")
    sys.stdout.write(f"{'COMPONENT':<14} {'BUCKET':<22} {'SAMPLES':>7}  RATIO\n")
    for a, b, n, r in rows:
        shown = f"{r:.3f}" if r is not None else f"(cold-start, needs {MIN_SAMPLES})"
        sys.stdout.write(f"{a:<14} {b:<22} {n:>7}  {shown}\n")
    return 0


TOKEN_CLASSES = ("input", "output", "cache_write", "cache_read")

# USD per 1M tokens, Anthropic first-party API rates as of 2026-06-24.
# cache_write is 1.25x input; cache_read is 0.1x input.
# Partner-operated platforms (Bedrock, Vertex) price separately and need a
# config override at modules.l3io-pm.token_rates.
TOKEN_RATES = {
    "claude-opus-5":      {"input": 5.00,  "output": 25.00, "cache_write": 6.25,  "cache_read": 0.50},
    "claude-opus-5-fast": {"input": 10.00, "output": 50.00, "cache_write": 12.50, "cache_read": 1.00},
    "claude-fable-5":     {"input": 10.00, "output": 50.00, "cache_write": 12.50, "cache_read": 1.00},
    "claude-sonnet-5":    {"input": 3.00,  "output": 15.00, "cache_write": 3.75,  "cache_read": 0.30},
    "claude-sonnet-4-6":  {"input": 3.00,  "output": 15.00, "cache_write": 3.75,  "cache_read": 0.30},
    "claude-haiku-4-5":   {"input": 1.00,  "output": 5.00,  "cache_write": 1.25,  "cache_read": 0.10},
}


def resolve_rates(model: str, overrides=None) -> dict:
    """The rate card for `model`, config overrides winning per model.

    An unknown model is a KeyError, never a default. A silently-wrong rate is
    exactly the failure this whole change exists to remove: the same token count
    prices 2x apart between a $5/M and a $10/M tier.
    """
    table = dict(TOKEN_RATES)
    if overrides:
        for k, v in overrides.items():
            table[k] = {**table.get(k, {}), **v}
    if model not in table:
        raise KeyError(f"unknown model {model!r} — add it to modules.l3io-pm.token_rates "
                       f"or use one of {sorted(table)}")
    return table[model]


def cost_from_tokens(tokens: dict, model: str, overrides=None) -> float:
    """USD for a per-class token count. `tokens` values are in THOUSANDS, rates
    are per million, hence the /1000."""
    rates = resolve_rates(model, overrides)
    total = 0.0
    for cls in TOKEN_CLASSES:
        v = _num_or_none((tokens or {}).get(cls))
        if v is None:
            continue
        # An override-only model can define a subset of the four classes. A bare
        # rates[cls] would surface as KeyError('cache_read') — which callers
        # print verbatim as e.args[0], giving the user the single word
        # "cache_read". Same hard-error policy as an unknown model, but with a
        # message that says what to do.
        if cls not in rates:
            raise KeyError(f"model {model!r} has no {cls!r} rate — modules.l3io-pm.token_rates "
                           f"must define all of {list(TOKEN_CLASSES)} for a model it adds")
        total += v * rates[cls]
    return round(total / 1000.0, 2)


def tokens_block(counts: dict):
    """A tokens_k mapping: the four classes plus their validated total.

    `total` is stored rather than recomputed on read so that a node remains
    self-describing when read by anything that does not know the class list.
    It is always the sum — never an independently-entered number.
    """
    from ruamel.yaml.comments import CommentedMap

    tk = CommentedMap()
    total = 0.0
    for cls in TOKEN_CLASSES:
        v = _num_or_none(counts.get(cls)) or 0.0
        tk[cls] = int(v) if float(v).is_integer() else v
        total += v
    out = CommentedMap()
    out["total"] = int(total) if float(total).is_integer() else round(total, 2)
    for cls in TOKEN_CLASSES:
        out[cls] = tk[cls]
    return out


def rate_overrides(args):
    """Parse --token-rates into the overrides dict resolve_rates expects."""
    raw = getattr(args, "token_rates", "") or ""
    if not raw.strip():
        return None
    try:
        return json.loads(raw)
    except ValueError as e:
        _die_usage(f"--token-rates is not valid JSON: {e}")


def cmd_rates(args) -> int:
    """Print the effective rate table. Read-only; exists so the value actually in
    force — including any --token-rates override — is inspectable without
    reading source or guessing."""
    overrides = rate_overrides(args)
    # The EFFECTIVE table, per design §5 — so an override-only model (one that
    # exists solely in modules.l3io-pm.token_rates, e.g. a Bedrock or Vertex
    # rate card) is listed rather than silently omitted. Listing sorted(TOKEN_RATES)
    # alone made `rates` report the shipped defaults while pricing used something
    # else, which is the one thing this read-only subcommand exists to prevent.
    models = [args.model] if args.model else sorted(set(TOKEN_RATES) | set(overrides or {}))
    for m in models:
        try:
            r = resolve_rates(m, overrides)
        except KeyError as e:
            # e.args[0], not str(e) — KeyError.__str__ repr-quotes its argument,
            # which would double-wrap a message that already reads as prose.
            sys.stderr.write(f"pm-status.py: {e.args[0]}\n")
            return 2
        # `r.get`, not `r[...]`: an override-only model (one this table has no
        # shipped defaults to merge over) can legitimately define a subset of
        # the four classes, and listing it must report the gap rather than
        # raise KeyError on the model the user added by hand.
        cells = "  ".join(f"{c}=" + (f"{r[c]:.2f}" if _is_number(r.get(c)) else "n/a")
                          for c in TOKEN_CLASSES)
        sys.stdout.write(f"{m:<22} {cells}\n")
    return 0


# The estimate-time model. Skills pass modules.l3io-pm.default_model through
# --model; this is the fallback for a direct CLI call, and it is a REAL model
# id so an unknown-model error can never be produced by the default itself.
DEFAULT_ESTIMATE_MODEL = "claude-opus-5"

# Cold-start assumption about a healthy, cache-warm run. NOT a calibrated
# ratio and not a component of its own: it is replaced by the observed mean
# once three story samples carry class data (see observed_mix below). It
# affects only how a banded TOTAL is SPLIT across classes — the banded total
# itself is untouched by it.
COLD_START_TOKEN_MIX = {"input": 0.15, "output": 0.05,
                        "cache_write": 0.30, "cache_read": 0.50}


def observed_mix(cal) -> dict:
    """Mean observed token mix, or the cold-start assumption below MIN_SAMPLES."""
    samples = ((cal or {}).get("token_mix") or {}).get("samples") or []
    # hasattr(s, "get") first: a stray non-mapping entry (hand-edit, bad
    # merge, partial corruption of the committed, shared calibration file)
    # must fall back to cold-start like every other malformed shape here —
    # not crash `estimate-story` for the whole project. Same guard as the
    # tokens_k mapping check in record_story_sample above.
    usable = [s for s in samples if hasattr(s, "get") and
              all(_num_or_none(s.get(c)) is not None for c in TOKEN_CLASSES)]
    if len(usable) < MIN_SAMPLES:
        return dict(COLD_START_TOKEN_MIX)
    mix = {c: sum(float(s[c]) for s in usable) / len(usable) for c in TOKEN_CLASSES}
    total = sum(mix.values())
    if total <= 0:
        return dict(COLD_START_TOKEN_MIX)
    return {c: v / total for c, v in mix.items()}   # renormalize; means need not sum to 1


def split_tokens(total: float, mix: dict) -> dict:
    """Split a banded total across classes, preserving the total exactly.

    Rounding drift goes to the largest class rather than being dropped, so
    `sum(classes) == total` is an invariant a test can assert and a reader can
    trust.
    """
    out = {c: int(round(total * float(mix.get(c, 0.0)))) for c in TOKEN_CLASSES}
    drift = int(round(total)) - sum(out.values())
    if drift:
        biggest = max(TOKEN_CLASSES, key=lambda c: out[c])
        out[biggest] += drift
    return out


# Cold-start base bands (low, high) per classification. These were previously a
# markdown table in steps/shared/step-estimate.md; this is now the single source.
# No `cost` row: cost is derived from the tokens_k total (split across classes,
# then priced per model) rather than banded and calibrated on its own — see
# cmd_estimate_story. Keeping a separate cost band was the original defect: a
# cost estimate with no arithmetic relationship to the token estimate it should
# follow, drifting apart from it as the two calibrated independently.
BASE_BANDS = {
    "simple":   {"man_hours": (2, 4),  "hitl_hours": (0.1, 0.3), "elapsed_hours": (0.5, 1.5),
                 "tokens_k": (20, 50)},
    "standard": {"man_hours": (4, 8),  "hitl_hours": (0.2, 0.5), "elapsed_hours": (1, 3),
                 "tokens_k": (40, 100)},
    "complex":  {"man_hours": (8, 16), "hitl_hours": (0.3, 1.0), "elapsed_hours": (2, 6),
                 "tokens_k": (80, 200)},
}


def cmd_estimate_story(args) -> int:
    """Compute and write a story's estimate block: band midpoint x scope ratio x fix
    factor, per metric. Classification is the model's judgment; everything after it
    is arithmetic, done here so it's error-checked and reproducible.

    Each metric queries its own calibrated scope ratio — man_hours and tokens_k may
    be calibrated independently once each has >=3 samples, so ratios are looked up
    per metric, never hoisted out and reused across all four in BASE_BANDS.

    All four applied ratios are recorded as `estimate.scope_ratios`, per metric.
    This is load-bearing, not provenance: `derive_story_sample` divides the applied
    ratio back out to measure the next sample against the base band, and one
    scalar cannot reconstruct four metrics' corrections.

    `cost` is not one of the banded/calibrated metrics: it is priced from the
    banded tokens_k TOTAL, split across classes by `observed_mix` (or the
    cold-start assumption below three samples), then run through
    `cost_from_tokens` for `--model` (falling back to DEFAULT_ESTIMATE_MODEL).
    This keeps cost arithmetically bound to the token estimate it prices —
    the two can no longer drift apart the way a separately-banded,
    separately-calibrated cost could.
    """
    path = story_file(args.state_root, args.story)
    if path is None:
        _die_notfound(f"story {args.story}")
    y, node = load_node(path)
    if node is None:
        _die_notfound(f"story {args.story} — file is empty")

    cls = args.classification
    _, cal = load_calibration(args.state_root)
    fix = active_fix_factor(cal, cls)
    fix = COLD_START_FIX_FACTOR if fix is None else fix

    from ruamel.yaml.comments import CommentedMap
    est = node.get("estimate")
    if est is None:
        est = CommentedMap()
        node["estimate"] = est

    applied = CommentedMap()
    for metric, (lo, hi) in BASE_BANDS[cls].items():
        mid = (lo + hi) / 2.0
        ratio = active_scope_ratio(cal, cls, metric)
        if ratio is None:
            ratio = COLD_START_SCOPE_RATIO
        applied[metric] = round(ratio, 4)
        value = mid * ratio * fix
        est[metric] = int(round(value)) if metric == "tokens_k" else round(value, 2)

    total_tokens = est.pop("tokens_k")
    counts = split_tokens(total_tokens, observed_mix(cal))
    est["tokens_k"] = tokens_block(counts)
    model = args.model or DEFAULT_ESTIMATE_MODEL
    try:
        est["cost"] = cost_from_tokens(counts, model, rate_overrides(args))
    except KeyError as e:
        # e.args[0], not str(e) — KeyError.__str__ repr-quotes its argument,
        # which would double-wrap a message that already reads as prose.
        _die_usage(e.args[0])
    est["model"] = model

    est["fix_factor"] = round(fix, 4)
    est["scope_ratios"] = applied
    est.pop("scope_ratio", None)   # the superseded single-value form
    if args.confidence:
        est["confidence"] = args.confidence
    node["classification"] = cls
    node["updated_at"] = _now_iso()
    save_node(y, node, path)
    shown = " ".join(f"{m}={v}" for m, v in applied.items())
    sys.stdout.write(f"OK estimate-story {args.story} class={cls} "
                     f"scope_ratios[{shown}] fix_factor={est['fix_factor']}\n")
    return 0


# Closure overhead as a fraction of children, used when no calibrated ratio is
# active yet. Deliberately a band, not a point: closure cost is variable.
COLD_START_CLOSURE_BAND = (0.10, 0.25)

# The orchestration fraction (active_orchestration_fraction) is a point
# estimate; these widen it into a range the same way COLD_START_CLOSURE_BAND
# widens the closure ratio. There is NO cold-start pair here, unlike closure
# — and that asymmetry is deliberate, not an oversight to "fix" by adding one.
# While the component is inactive (< MIN_SAMPLES) the fraction is 0 and the
# band contributes nothing to the roll-up at all; a cold-start orchestration
# band would put a number on a quantity this rework explicitly refuses to
# guess (see active_orchestration_fraction's docstring — every pre-existing
# measurement was contaminated by a cache-eviction defect). The stderr
# warning `cmd_estimate_rollup` emits while unseeded is what stands in for
# that number instead.
ORCH_SPREAD = (0.8, 1.2)

# The orchestration band's contribution to the roll-up MIDPOINT, per unit of
# applied fraction. `derive_closure_sample` subtracts `est_total x fraction x
# ORCH_MID` off the parent estimate midpoint so what remains is the closure
# band alone — the quantity the closure ratio is actually applied to. Derived
# from ORCH_SPREAD rather than restated as `1.0`, so widening the spread
# asymmetrically can never silently desynchronise the two.
ORCH_MID = (ORCH_SPREAD[0] + ORCH_SPREAD[1]) / 2.0


def _child_estimate_value(node, metric):
    """A child's value for `metric`: single-value form first (a story), else
    the midpoint of its range form (a sprint). None if neither is present.

    Reuses CLOSURE_RANGE_KEYS (metric -> parent low/high key names) rather
    than a second near-duplicate mapping, and `_estimate_metric` (not a local
    unwrap) for the single-value read — see that function's docstring for why
    duplicating the tokens_k unwrap here is exactly the mistake to avoid.
    """
    est = (node or {}).get("estimate") or {}
    v = _estimate_metric(est, metric)
    if v is not None:
        return v
    lo, hi = CLOSURE_RANGE_KEYS[metric]
    return _mid(est, lo, hi)


def cmd_estimate_rollup(args) -> int:
    """Roll a sprint's story estimates, or an epic's sprint estimates, up to
    the parent as a range: sum(children) + a closure band + an orchestration
    band. Output is always range form, even when every child estimate is
    single-value (the story form).

    The closure band scales by the calibrated closure ratio for level/metric
    once active (>=3 samples), else the cold-start band applies (equivalently,
    ratio 1.0). The orchestration band scales by the calibrated orchestration
    FRACTION for level/metric once active, else it contributes nothing — there
    is no cold-start prior for orchestration (see ORCH_SPREAD, and
    active_orchestration_fraction's docstring for why). Both bands widen by a
    fixed spread (COLD_START_CLOSURE_BAND, ORCH_SPREAD respectively) rather
    than landing on a single point.

    The applied ratios/fractions are recorded as `estimate.closure_ratios` and
    `estimate.orchestration_ratios`, per metric, so `derive_closure_sample` and
    a future orchestration-sample reader can divide them back out — the same
    reason `estimate.scope_ratios` exists on a story.

    `cost` is not one of the banded metrics (see CLOSURE_RANGE_KEYS): it is
    derived from the rolled-up tokens_k range, split across classes by
    `observed_mix`, then priced for `--model` (falling back to
    DEFAULT_ESTIMATE_MODEL) — the sprint/epic-level mirror of what
    `cmd_estimate_story` already does for a story. This keeps the rolled-up
    cost arithmetically bound to the rolled-up token estimate it prices,
    instead of banding and calibrating a second, independently-drifting cost.
    """
    level = "sprint" if args.sprint else "epic"
    if level == "sprint":
        ppath = sprint_file(args.state_root, args.epic, args.sprint)
        child_paths = list_story_files(args.state_root, args.epic, args.sprint)
    else:
        ppath = epic_file(args.state_root, args.epic)
        child_paths = [sprint_file(args.state_root, args.epic, _sprint_key_from_dir(d))
                       for d in list_sprint_dirs(args.state_root, args.epic)]
    if ppath is None:
        _die_notfound(f"{level} {args.sprint or args.epic}")
    y, pnode = load_node(ppath)
    if pnode is None:
        _die_notfound(f"{level} file is empty")

    _, cal = load_calibration(args.state_root)
    from ruamel.yaml.comments import CommentedMap
    est = CommentedMap()
    applied = CommentedMap()
    orch_applied = CommentedMap()
    counted = 0
    for metric, (lo_key, hi_key) in CLOSURE_RANGE_KEYS.items():
        total = 0.0
        seen = 0
        for cp in child_paths:
            if cp is None:
                continue
            _, cn = load_node(cp)
            v = _child_estimate_value(cn, metric)
            if v is not None:
                total += v
                seen += 1
        if seen == 0:
            continue
        counted = max(counted, seen)
        ratio = active_closure_ratio(cal, level, metric)
        if ratio is None:
            ratio = 1.0            # cold start: the closure band applies unscaled
        applied[metric] = round(ratio, 4)

        frac = active_orchestration_fraction(cal, level, metric)
        orch_applied[metric] = round(frac, 4) if frac is not None else 0
        of = frac or 0.0
        lo = total * (1 + ratio * COLD_START_CLOSURE_BAND[0] + of * ORCH_SPREAD[0])
        hi = total * (1 + ratio * COLD_START_CLOSURE_BAND[1] + of * ORCH_SPREAD[1])
        if metric == "tokens_k":
            est[lo_key], est[hi_key] = int(round(lo)), int(round(hi))
        else:
            est[lo_key], est[hi_key] = round(lo, 2), round(hi, 2)

    if counted == 0:
        _die_usage(f"{level} {args.sprint or args.epic} has no child estimates to roll up")

    est["closure_ratios"] = applied
    est["orchestration_ratios"] = orch_applied
    # ANY inactive metric warns, not just "every metric inactive" (`not any(...)`
    # would under-fire: orchestration calibrates per metric, and a metric is
    # sampled only when every child carries a numeric actual for it, so under a
    # mixed runtime man_hours can activate while tokens_k never does — `any()`
    # would then be true and stay silent on exactly the metric the warning
    # exists to flag). Named, not blanket: listing which metrics are still
    # unestimated makes the warning actionable instead of a caveat that is
    # "always true anyway" once any single metric has activated.
    inactive = [m for m, v in orch_applied.items() if not v]
    if inactive:
        sys.stderr.write(
            "pm-status.py: warning — orchestration is unestimated for "
            f"{', '.join(inactive)} (component has <{MIN_SAMPLES} samples at "
            f"{level} level); this estimate is known-low on those metrics.\n")

    model = args.model or DEFAULT_ESTIMATE_MODEL
    mix = observed_mix(cal)
    try:
        for bound, key in (("tokens_k_min", "cost_low"), ("tokens_k_max", "cost_high")):
            tv = _num_or_none(est.get(bound))
            if tv is not None:
                est[key] = cost_from_tokens(split_tokens(tv, mix), model, rate_overrides(args))
    except KeyError as e:
        # e.args[0], not str(e) — KeyError.__str__ repr-quotes its argument,
        # which would double-wrap a message that already reads as prose.
        _die_usage(e.args[0])
    est["model"] = model

    est["confidence"] = "medium"
    pnode["estimate"] = est
    pnode["updated_at"] = _now_iso()
    save_node(y, pnode, ppath)
    sys.stdout.write(f"OK estimate-rollup {level} {args.sprint or args.epic} "
                     f"from {counted} children\n")
    return 0


def list_story_files(state_root: str, epic_key: str, sprint_key: str) -> list:
    """Sorted story files in a sprint, excluding sprint.yaml."""
    d = find_epic_dir(state_root, epic_key)
    if d is None:
        return []
    sd = os.path.join(d, sprint_dirname(sprint_key))
    if not os.path.isdir(sd):
        return []
    return sorted(os.path.join(sd, n) for n in os.listdir(sd)
                  if n.endswith(".yaml") and n != "sprint.yaml")


def _accumulate_actuals(totals: dict, node) -> None:
    actual = (node or {}).get("actual") or {}
    for m in METRIC_FIELDS:
        v = _actual_metric(actual, m)
        if v is None:
            continue
        totals[m] = totals.get(m, 0.0) + v


# --------------------------------------------------------------------------- #
# spend attribution — the three buckets metrics-contract.md §6 defines
#
# The estimate has three terms (children + closure band + orchestration band), so
# a report of what was actually spent has to have the same three, or the largest
# term stays invisible: on the run that motivated this model, orchestration was
# 72% of total spend and stories were 24%. Recording it on disk and omitting it
# from every rendered report leaves the number nobody can act on. Design §9's CLI
# table specifies this breakout for `report`; `show` carries it too, since it is
# the per-node view of the same three buckets.
# --------------------------------------------------------------------------- #
SPEND_BUCKETS = ("stories", "closure", "orchestration")


def _block_totals(node, block: str = "actual") -> dict:
    """One metric block's numeric values. Absent and `N/A` entries are omitted
    rather than coerced to zero — a missing measurement is not a measured zero."""
    b = (node or {}).get(block) or {}
    out = {}
    for m in METRIC_FIELDS:
        v = _actual_metric(b, m)
        if v is not None:
            out[m] = v
    return out


def _add_totals(dst: dict, src: dict) -> None:
    for k, v in (src or {}).items():
        dst[k] = dst.get(k, 0.0) + v


def _closure_totals(parent_actual: dict, children_total: dict) -> dict:
    """A node's own closure-phase spend: its `actual` minus its children's sum.

    The same residual `derive_closure_sample` measures its component from, so the
    report and the calibration loop can never disagree about what "closure" means.
    Only metrics BOTH sides carry are reported — a parent metric with no comparable
    children sum has no residual, not a residual equal to the whole parent. Clamped
    at zero for display: a negative residual is a wall-clock overlap or a miscount
    (`derive_closure_sample` names which), not negative spend.
    """
    out = {}
    for m, pv in (parent_actual or {}).items():
        cv = (children_total or {}).get(m)
        if cv is None:
            continue
        out[m] = max(0.0, pv - cv)
    return out


def _new_spend() -> dict:
    return {b: {} for b in SPEND_BUCKETS}


def _merge_spend(dst: dict, src: dict) -> None:
    for b in SPEND_BUCKETS:
        _add_totals(dst[b], (src or {}).get(b) or {})


def _spend_total(spend: dict) -> dict:
    """The three buckets summed — what the level actually cost, end to end."""
    out = {}
    for b in SPEND_BUCKETS:
        _add_totals(out, (spend or {}).get(b) or {})
    return out


def _sprint_spend(story_totals: dict, snode) -> dict:
    return {"stories": dict(story_totals),
            "closure": _closure_totals(_block_totals(snode, "actual"), story_totals),
            "orchestration": _block_totals(snode, "orchestration")}


def _has_spend(spend: dict) -> bool:
    return any((spend or {}).get(b) for b in SPEND_BUCKETS)


def rollup_sprint(state_root: str, epic_key: str, sprint_key: str) -> dict:
    by_status, totals, stories = {}, {}, []
    for p in list_story_files(state_root, epic_key, sprint_key):
        _, node = load_node(p)
        if node is None:
            continue
        st = str(node.get("status", "unknown"))
        by_status[st] = by_status.get(st, 0) + 1
        _accumulate_actuals(totals, node)
        stories.append({"key": node.get("key", os.path.basename(p)), "status": st})
    sp = sprint_file(state_root, epic_key, sprint_key)
    _, snode = load_node(sp) if sp else (None, None)
    return {
        "key": sprint_key,
        "status": str((snode or {}).get("status", "unknown")),
        "story_count": len(stories),
        "by_status": by_status,
        "actual_totals": totals,
        "node_actual": _block_totals(snode, "actual"),
        "spend": _sprint_spend(totals, snode),
        "stories": stories,
    }


def rollup_epic(state_root: str, epic_key: str) -> dict:
    by_status, totals, sprints, story_count = {}, {}, [], 0
    spend, sprint_actual_sum = _new_spend(), {}
    for sd in list_sprint_dirs(state_root, epic_key):
        skey = _sprint_key_from_dir(sd)
        r = rollup_sprint(state_root, epic_key, skey)
        sprints.append(r)
        story_count += r["story_count"]
        for k, v in r["by_status"].items():
            by_status[k] = by_status.get(k, 0) + v
        for k, v in r["actual_totals"].items():
            totals[k] = totals.get(k, 0.0) + v
        _merge_spend(spend, r["spend"])
        _add_totals(sprint_actual_sum, r["node_actual"])
    ep = epic_file(state_root, epic_key)
    _, enode = load_node(ep) if ep else (None, None)
    # The epic's OWN closure residual sits on top of its sprints' — one bucket,
    # two levels, because both are "the closing level's own closure phases".
    _add_totals(spend["closure"],
                _closure_totals(_block_totals(enode, "actual"), sprint_actual_sum))
    _add_totals(spend["orchestration"], _block_totals(enode, "orchestration"))
    return {
        "key": epic_key,
        "status": str((enode or {}).get("status", "unknown")),
        "sprint_count": len(sprints),
        "story_count": story_count,
        "by_status": by_status,
        "actual_totals": totals,
        "node_actual": _block_totals(enode, "actual"),
        "spend": spend,
        "sprints": sprints,
    }


def _fmt_actuals(totals: dict) -> str:
    """Render an actuals dict in stable METRIC_FIELDS order."""
    return "  ".join(f"{m}={_norm_spend(totals.get(m))}" for m in METRIC_FIELDS)


def _norm_spend(v):
    """Display form for a summed metric: 0 when absent, trimmed of float noise.

    Summing floats produces 3.9000000000000004; a report that prints that is
    reporting its own arithmetic rather than the number. Rounded to 4 places
    (well past any metric's real precision) and shown as an int when integral.
    """
    if v is None:
        return 0
    try:
        f = round(float(v), 4)
    except (TypeError, ValueError):
        return v
    return int(f) if f.is_integer() else f


# --------------------------------------------------------------------------- #
# progress model — one builder, consumed by every renderer and every surface
# --------------------------------------------------------------------------- #
def list_all_epics(state_root: str) -> list:
    """(epic_key, dir_status) for every epic in every status folder, sorted by key.

    The directory name is authoritative for the key: 'epic-001' -> 'E001'. Reading the
    key from the file instead would let a mis-keyed file hide an epic entirely.
    """
    found = []
    for status in STATUS_DIRS:
        base = os.path.join(state_root, status)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            if not name.startswith("epic-"):
                continue
            if not os.path.isdir(os.path.join(base, name)):
                continue
            suffix = name[len("epic-"):]
            if not suffix.isdigit():
                continue
            found.append((f"E{int(suffix):03d}", status))
    return sorted(found, key=lambda t: t[0])


def _build_sprint_detail(state_root: str, epic_key: str, sprint_key: str,
                         events_index: dict, now=None) -> dict:
    """One sprint and its stories.

    `detail["flags"]` holds only the sprint's OWN flags (its stuck state, and any story
    file too broken to become a node of its own). Story flags live on their story. The
    flat aggregate is assembled later by `_collect_flags` — an earlier version pushed
    descendants' flags up into the parent, which made every ancestor row report "stuck"
    whenever one story was.
    """
    flags: list = []
    sp = sprint_file(state_root, epic_key, sprint_key)
    snode = {}
    if sp is not None:
        try:
            _, loaded = load_node(sp)
            snode = loaded or {}
        except Exception as e:  # noqa: BLE001 - a bad file must not kill the report
            flags.append({"kind": "unreadable", "level": "sprint",
                          "key": f"{epic_key}/{sprint_key}", "detail": str(e)})

    s_status = str(snode.get("status", "unknown"))
    s_dwell, s_exact = dwell_hours({"key": sprint_key, "status": s_status,
                                    "updated_at": snode.get("updated_at")},
                                   events_index, now)
    flags += compute_flags("sprint", f"{epic_key}/{sprint_key}", s_status, s_dwell, s_exact)

    stories, by_status, totals = [], {}, {}
    for p in list_story_files(state_root, epic_key, sprint_key):
        try:
            _, node = load_node(p)
        except Exception as e:  # noqa: BLE001
            # No story node exists to hang this on, so it belongs to the sprint.
            flags.append({"kind": "unreadable", "level": "story",
                          "key": os.path.basename(p), "detail": str(e)})
            continue
        if node is None:
            continue
        st = str(node.get("status", "unknown"))
        key = str(node.get("key", os.path.basename(p)))
        by_status[st] = by_status.get(st, 0) + 1
        _accumulate_actuals(totals, node)
        d, ex = dwell_hours(node, events_index, now)
        stories.append({"key": key, "status": st,
                        "estimate": dict(node.get("estimate") or {}),
                        "actual": dict(node.get("actual") or {}),
                        "updated_at": node.get("updated_at"),
                        "dwell_hours": None if d is None else round(d, 2),
                        "dwell_exact": ex,
                        "flags": compute_flags("story", key, st, d, ex)})

    return {"key": sprint_key, "status": s_status, "story_count": len(stories),
            "by_status": by_status, "actual_totals": totals,
            "node_actual": _block_totals(snode, "actual"),
            "spend": _sprint_spend(totals, snode),
            "estimate": dict(snode.get("estimate") or {}),
            "updated_at": snode.get("updated_at"),
            "dwell_hours": None if s_dwell is None else round(s_dwell, 2),
            "dwell_exact": s_exact, "flags": flags, "stories": stories}


def _collect_flags(epic_detail: dict) -> list:
    """Flatten one epic subtree's flags for the model-level aggregate."""
    out = list(epic_detail.get("flags") or [])
    for sp in epic_detail.get("sprints") or []:
        out += list(sp.get("flags") or [])
        for st in sp.get("stories") or []:
            out += list(st.get("flags") or [])
    return out


def build_epic_detail(state_root: str, epic_key: str, dir_status: str,
                      events_index: dict, now=None) -> dict:
    """One epic subtree, enriched with dwell times, flags, and placement checks."""
    flags: list = []
    ep = epic_file(state_root, epic_key)
    y_node = None
    if ep is not None:
        try:
            _, y_node = load_node(ep)
        except Exception as e:  # noqa: BLE001
            flags.append({"kind": "unreadable", "level": "epic", "key": epic_key,
                          "detail": str(e)})
    enode = y_node or {}

    status = str(enode.get("status", "unknown"))
    expected = STATUS_FOR_DIR.get(dir_status)
    if expected and status != "unknown" and status != expected:
        flags.append({"kind": "placement", "level": "epic", "key": epic_key,
                      "detail": f"status {status!r} but sits in {dir_status}/ "
                                f"(expected {expected!r})"})

    lock = None
    raw_lock = enode.get("_lock")
    if isinstance(raw_lock, dict):
        claimed = _parse_iso(raw_lock.get("claimed_at"))
        ttl = raw_lock.get("ttl_minutes")
        stale = False
        if claimed is not None and ttl:
            try:
                age_min = ((now or datetime.now(timezone.utc))
                           - claimed).total_seconds() / 60.0
                stale = age_min > float(ttl)
            except (TypeError, ValueError):
                stale = False
        lock = {"session_id": raw_lock.get("session_id"),
                "claimed_at": raw_lock.get("claimed_at"),
                "ttl_minutes": ttl, "stale": stale}
        if stale:
            flags.append({"kind": "stale-lock", "level": "epic", "key": epic_key,
                          "detail": f"lock claimed {raw_lock.get('claimed_at')} "
                                    f"exceeds ttl {ttl}m"})

    dwell, exact = dwell_hours({"key": epic_key, "status": status,
                                "updated_at": enode.get("updated_at")},
                               events_index, now)
    flags += compute_flags("epic", epic_key, status, dwell, exact)

    sprints, totals, by_status, story_count = [], {}, {}, 0
    spend, sprint_actual_sum = _new_spend(), {}
    for sd in list_sprint_dirs(state_root, epic_key):
        skey = _sprint_key_from_dir(sd)
        s_detail = _build_sprint_detail(state_root, epic_key, skey, events_index, now)
        sprints.append(s_detail)
        story_count += s_detail["story_count"]
        for k, v in s_detail["by_status"].items():
            by_status[k] = by_status.get(k, 0) + v
        for k, v in s_detail["actual_totals"].items():
            totals[k] = totals.get(k, 0.0) + v
        _merge_spend(spend, s_detail["spend"])
        _add_totals(sprint_actual_sum, s_detail["node_actual"])
    _add_totals(spend["closure"],
                _closure_totals(_block_totals(enode, "actual"), sprint_actual_sum))
    _add_totals(spend["orchestration"], _block_totals(enode, "orchestration"))

    return {
        "key": epic_key, "title": enode.get("title"), "status": status,
        "dir_status": dir_status, "sprint_count": len(sprints),
        "story_count": story_count, "by_status": by_status,
        "estimate": dict(enode.get("estimate") or {}),
        "actual_totals": totals, "node_actual": _block_totals(enode, "actual"),
        "spend": spend, "updated_at": enode.get("updated_at"),
        "dwell_hours": None if dwell is None else round(dwell, 2),
        "dwell_exact": exact, "lock": lock, "flags": flags, "sprints": sprints,
    }


def load_plan(plan_pointer: str):
    """Load plan phases via the stable pointer.

    `plan-output-meta.yaml` is a pointer plus summary scalars and deliberately holds no
    phases list (step-06-plan-output.md §4), so the phases come from the snapshot it
    names, resolved in the pointer's own directory. A dangling pointer yields the meta
    with empty phases rather than an error: the state hierarchy is still worth showing.
    """
    if not plan_pointer or not os.path.isfile(plan_pointer):
        return None
    try:
        _, meta = _load(plan_pointer)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"pm-status.py: warning — could not read plan pointer: {e}\n")
        return None
    if not meta:
        return None
    meta = dict(meta)
    phases = []
    snap_name = meta.get("current_plan")
    if snap_name:
        snap = os.path.join(os.path.dirname(os.path.abspath(plan_pointer)), str(snap_name))
        if os.path.isfile(snap):
            try:
                _, snode = _load(snap)
                phases = [dict(p) for p in ((snode or {}).get("phases") or [])]
            except Exception as e:  # noqa: BLE001
                sys.stderr.write(f"pm-status.py: warning — could not read plan "
                                 f"snapshot: {e}\n")
        else:
            sys.stderr.write(f"pm-status.py: warning — plan pointer names a missing "
                             f"snapshot: {snap_name}\n")
    return {"meta": meta, "phases": phases}


DEFAULT_REPORT_STATUSES = ("planned", "active")


def build_progress_model(state_root: str, plan=None, statuses=None,
                         include_archived: bool = False, now=None) -> dict:
    """The one model every renderer and every surface consumes.

    `statuses` selects which state folders appear in the DISPLAY lists — pass a subset of
    STATUS_DIRS, e.g. {"active"} for only what is moving. Defaults to planned + active, so
    finished work stays out of the way until asked for.

    Every epic is built regardless of the filter. Phase progress needs a true denominator:
    a bar reading "2/3 epics done" must mean the same thing whatever you chose to look at,
    so counting always sees the whole tree and only the listing narrows.

    `include_archived` is the older boolean form, kept so existing callers keep working;
    it is equivalent to adding "archived" to the default set.
    """
    if statuses is None:
        statuses = set(DEFAULT_REPORT_STATUSES)
        if include_archived:
            statuses.add("archived")
    statuses = set(statuses)
    unknown = statuses - set(STATUS_DIRS)
    if unknown:
        raise ValueError(f"unknown status folder(s): {sorted(unknown)} "
                         f"— expected a subset of {list(STATUS_DIRS)}")
    events_index = build_events_index(state_root)
    details, flags = {}, []
    totals = {"epics": {}, "sprints": {}, "stories": {}}
    spend = _new_spend()

    for epic_key, dir_status in list_all_epics(state_root):
        d = build_epic_detail(state_root, epic_key, dir_status, events_index, now)
        details[epic_key] = d
        flags += _collect_flags(d)
        # Spend, like the status counts below, is summed over EVERY epic, not only
        # the visible ones: "what has this project cost" must not change because
        # the caller narrowed the listing to `active`.
        _merge_spend(spend, d["spend"])
        totals["epics"][d["status"]] = totals["epics"].get(d["status"], 0) + 1
        for sp in d["sprints"]:
            totals["sprints"][sp["status"]] = totals["sprints"].get(sp["status"], 0) + 1
        for k, v in d["by_status"].items():
            totals["stories"][k] = totals["stories"].get(k, 0) + v

    def visible(d):
        return d["dir_status"] in statuses

    phases, claimed = [], set()
    for ph in (plan or {}).get("phases") or []:
        members = [str(k) for k in (ph.get("epics") or [])]
        claimed.update(members)
        present = [details[k] for k in members if k in details]
        phases.append({
            "phase": ph.get("phase"), "parallel": bool(ph.get("parallel")),
            "epics": members, "dependencies": list(ph.get("dependencies") or []),
            "epic_total": len(members),
            "epic_done": sum(1 for d in present if d["status"] == "done"),
            "epics_detail": [d for d in present if visible(d)],
        })

    return {
        "generated": _now_iso(),
        "state_root": os.path.abspath(state_root),
        "statuses": sorted(statuses),
        "plan": (plan or {}).get("meta"),
        "phases": phases,
        "unplanned_epics": [d for k, d in sorted(details.items())
                            if k not in claimed and visible(d)],
        "totals": totals,
        "spend": spend,
        "spend_total": _spend_total(spend),
        "flags": flags,
    }


# --------------------------------------------------------------------------- #
# renderers — thin: they consume the model and nothing else
# --------------------------------------------------------------------------- #
def _bar(done: int, total: int, width: int = 10) -> str:
    if total <= 0:
        return "░" * width
    filled = int(round(width * max(0, min(done, total)) / total))
    return "█" * filled + "░" * (width - filled)


def _dwell_str(node: dict) -> str:
    h = node.get("dwell_hours")
    if h is None:
        return ""
    approx = "" if node.get("dwell_exact") else "~"
    return f"{approx}{h:.1f}h"


def _stuck_suffix(node: dict) -> str:
    return "  ⚠ stuck" if any(f["kind"] == "stuck" for f in node.get("flags") or []) else ""


def _render_epic_tree(d: dict, out: list, indent: str = "  ") -> None:
    done = d["by_status"].get("done", 0)
    out.append(f"{indent}{d['key']} {(d.get('title') or ''):<24} {d['status']:<12} "
               f"{done}/{d['story_count']} stories  {_dwell_str(d)}{_stuck_suffix(d)}")
    if d.get("lock") and d["lock"].get("stale"):
        out.append(f"{indent}  ⚠ STALE LOCK — claimed {d['lock'].get('claimed_at')} "
                   f"(ttl {d['lock'].get('ttl_minutes')}m)")
    for sp in d["sprints"]:
        s_done = sp["by_status"].get("done", 0)
        out.append(f"{indent}  {sp['key']:<6} {sp['status']:<12} "
                   f"{s_done}/{sp['story_count']}  {_dwell_str(sp)}{_stuck_suffix(sp)}")
        for st in sp["stories"]:
            if st["status"] == "done":
                continue  # counts above carry finished work; the tree shows what is live
            out.append(f"{indent}    {st['key']:<20} {st['status']:<14} "
                       f"{_dwell_str(st)}{_stuck_suffix(st)}")


def render_tree(model: dict) -> str:
    out: list = []
    plan = model.get("plan")
    if plan:
        out.append(f"PLAN {plan.get('current_plan')}   readiness={plan.get('readiness')}"
                   f"   generated={plan.get('generated')}")
    else:
        out.append("PLAN (none — showing state only)")
    out.append(f"STATE {model['state_root']}")
    # Name the filter whenever it is not the default, so a short list is never mistaken for
    # an empty project. "only" would be a lie when every folder is shown, so word that case
    # differently.
    shown = model.get("statuses") or list(DEFAULT_REPORT_STATUSES)
    if sorted(shown) == sorted(STATUS_DIRS):
        out.append("SHOWING every status, including archived")
    elif sorted(shown) != sorted(DEFAULT_REPORT_STATUSES):
        out.append(f"SHOWING {', '.join(shown)} only "
                   f"(totals and phase counts still cover every epic)")
    out.append("")

    total_phases = len(model["phases"])
    for ph in model["phases"]:
        kind = "parallel" if ph["parallel"] else "sequential"
        out.append(f"Phase {ph['phase']}/{total_phases} ({kind})  "
                   f"{_bar(ph['epic_done'], ph['epic_total'])}  "
                   f"{ph['epic_done']}/{ph['epic_total']} epics done")
        if ph["dependencies"]:
            out.append(f"  depends on: {', '.join(str(x) for x in ph['dependencies'])}")
        if not ph["epics_detail"]:
            out.append("  (all epics in this phase are archived — pass --all to show)")
        for d in ph["epics_detail"]:
            _render_epic_tree(d, out)
        out.append("")

    if model["unplanned_epics"]:
        out.append("Not in any plan phase:" if model["phases"] else "Epics:")
        for d in model["unplanned_epics"]:
            _render_epic_tree(d, out)
        out.append("")

    if not model["phases"] and not model["unplanned_epics"]:
        out.append("No epics found — nothing to report.")
        out.append("")

    out.append("Totals")
    for level in ("epics", "sprints", "stories"):
        counts = model["totals"].get(level) or {}
        body = "  ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none"
        out.append(f"  {level:<9} {body}")

    spend = model.get("spend") or {}
    if _has_spend(spend):
        out.append("")
        out.append("Spend (actual, by attribution — covers every epic, not just those listed)")
        for bucket in SPEND_BUCKETS:
            out.append(f"  {bucket:<14} {_fmt_actuals(spend.get(bucket) or {})}")
        out.append(f"  {'TOTAL':<14} {_fmt_actuals(model.get('spend_total') or {})}")

    other = [f for f in model["flags"] if f["kind"] != "stuck"]
    if other:
        out.append("")
        out.append("Anomalies")
        for f in other:
            out.append(f"  [{f['kind']}] {f.get('key')} — {f.get('detail', '')}")

    if any(f["kind"] == "stuck" and not f.get("exact") for f in model["flags"]):
        out.append("")
        out.append("~ dwell times are approximate (no event log yet — derived from "
                   "updated_at, which any field write refreshes)")
    # Column padding leaves ragged trailing spaces on rows with no dwell/flag suffix.
    return "\n".join(line.rstrip() for line in out) + "\n"


def render_md(model: dict) -> str:
    plan = model.get("plan")
    out = ["# Progress Report", "",
           f"Generated by `pm-status.py report` at {model['generated']}. This file is a "
           "view, not a source of truth — do not hand-edit; regenerate it.", ""]
    if plan:
        out.append(f"**Plan:** `{plan.get('current_plan')}` — readiness "
                   f"`{plan.get('readiness')}`, generated {plan.get('generated')}")
    else:
        out.append("**Plan:** none found — state only.")
    out.append("")

    if model["phases"]:
        out += ["## Phases", "", "| Phase | Mode | Epics done | Members |",
                "|---|---|---|---|"]
        for ph in model["phases"]:
            mode = "parallel" if ph["parallel"] else "sequential"
            out.append(f"| {ph['phase']} | {mode} | {ph['epic_done']}/{ph['epic_total']} "
                       f"| {', '.join(ph['epics'])} |")
        out.append("")

    rows = [d for ph in model["phases"] for d in ph["epics_detail"]] + model["unplanned_epics"]
    out += ["## Epics", "", "| Epic | Title | Status | Sprints | Stories done | Dwell |",
            "|---|---|---|---|---|---|"]
    if not rows:
        out.append("| _none_ | | | | | |")
    for d in rows:
        out.append(f"| {d['key']} | {d.get('title') or ''} | {d['status']} "
                   f"| {d['sprint_count']} | {d['by_status'].get('done', 0)}/"
                   f"{d['story_count']} | {_dwell_str(d) or '—'} |")
    out.append("")

    live = [(d, sp, st) for d in rows for sp in d["sprints"] for st in sp["stories"]
            if st["status"] not in ("done", "backlog")]
    if live:
        out += ["## Stories in flight", "",
                "| Story | Epic | Sprint | Status | Dwell | Stuck |",
                "|---|---|---|---|---|---|"]
        for d, sp, st in live:
            stuck = "yes" if any(f["kind"] == "stuck" for f in st["flags"]) else ""
            out.append(f"| {st['key']} | {d['key']} | {sp['key']} | {st['status']} "
                       f"| {_dwell_str(st) or '—'} | {stuck} |")
        out.append("")

    out += ["## Totals", "", "| Level | Counts |", "|---|---|"]
    for level in ("epics", "sprints", "stories"):
        counts = model["totals"].get(level) or {}
        body = ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none"
        out.append(f"| {level} | {body} |")
    out.append("")

    spend = model.get("spend") or {}
    if _has_spend(spend):
        out += ["## Spend", "",
                "Actual spend by attribution, over every epic in the tree (not only the "
                "epics listed above). `stories` is the sum of the leaf actuals, `closure` "
                "each level's own closure-phase residual, `orchestration` the separate "
                "orchestration block.", "",
                "| Attribution | " + " | ".join(METRIC_FIELDS) + " |",
                "|---|" + "---|" * len(METRIC_FIELDS)]
        rows = [(b, spend.get(b) or {}) for b in SPEND_BUCKETS]
        rows.append(("**total**", model.get("spend_total") or {}))
        for label, vals in rows:
            cells = " | ".join(str(_norm_spend(vals.get(m))) for m in METRIC_FIELDS)
            out.append(f"| {label} | {cells} |")
        out.append("")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- #
# subcommands
# --------------------------------------------------------------------------- #
def cmd_set_status(args) -> int:
    kind = _infer_kind(args)
    valid = {"story": VALID_STORY_STATUS, "sprint": VALID_SPRINT_STATUS, "epic": VALID_EPIC_STATUS}[kind]
    if args.status not in valid:
        _die_usage(f"invalid {kind} status '{args.status}' — expected one of {sorted(valid)}")

    y, node, path, label = _load_checked(args.state_root, args, kind)
    prior = str(node.get("status", "")) or None
    node["status"] = args.status
    node["updated_at"] = _now_iso()
    if args.title:
        node["title"] = args.title
    save_node(y, node, path, getattr(args, "flock", False))

    if not getattr(args, "no_events", False):
        payload = {"ts": _now_iso(), "event": "status",
                   "from": prior, "to": args.status,
                   "session": getattr(args, "session_id", None)}
        payload.update(_event_keys(kind, args))
        append_event(args.state_root, payload)

    sys.stdout.write(f"OK set-status {label} -> {args.status}\n")
    return 0


def cmd_set_actual(args) -> int:
    kind = args.node
    block = getattr(args, "block", "actual")
    if block == "orchestration" and kind == "story":
        _die_usage("--block orchestration is only valid on a sprint or epic — a story's "
                   "orchestration belongs to its parent sprint")
    y, node, path, label = _load_checked(args.state_root, args, kind)

    provided = {
        "elapsed_hours": args.elapsed_hours,
        "man_hours": args.man_hours,
        "hitl_hours": args.hitl_hours,
    }

    if args.cost is not None:
        _die_usage("--cost is not accepted: cost is derived from tokens x rates. "
                   "Fix the token counts or modules.l3io-pm.token_rates instead.")

    classes = {c: getattr(args, "tokens_" + c) for c in TOKEN_CLASSES}
    given = {c: v for c, v in classes.items() if v is not None}
    if args.tokens_na and given:
        _die_usage("--tokens-na cannot be combined with explicit token counts")
    if args.tokens_na:
        if args.runtime == "claude":
            _die_usage("runtime=claude forbids tokens=N/A — capture the exact per-class "
                       "counts from the session transcript (see metrics-contract.md §3)")
        provided["tokens_k"] = "N/A"
        provided["cost"] = "N/A"
    elif given:
        # Under runtime=claude an incomplete class set is a usage error, not a
        # zero-fill. `tokens_block` defaults an omitted class to 0, `total` sums
        # to the classes that were passed, `cost` derives from those, and
        # `verify` then confirms all three agree with each other — internally
        # consistent and therefore unfalsifiable. One forgotten flag understates
        # a node by an order of magnitude: cache classes dominate real runs
        # (99.8% cache_creation on the motivating run), so an omitted
        # --tokens-cache-write is not a rounding error. An explicit 0 stays
        # valid — the requirement is that the capturer looked at all four, not
        # that all four are nonzero. runtime=other stays permissive: a runtime
        # that exposes only some classes is exactly what --runtime other is for.
        if args.runtime == "claude" and len(given) < len(TOKEN_CLASSES):
            missing = [c for c in TOKEN_CLASSES if c not in given]
            _die_usage(
                "runtime=claude requires all four token classes when any is given — "
                f"missing: {', '.join('--tokens-' + m.replace('_', '-') for m in missing)}. "
                "Read input_tokens, output_tokens, cache_creation_input_tokens and "
                "cache_read_input_tokens from the session transcript's usage fields "
                "(metrics-contract.md §3); pass an explicit 0 for a class that really "
                "is zero.")
        if not args.model:
            _die_usage("--model is required whenever token counts are given — the same "
                       "token count prices 2x apart between a $5/M and a $10/M tier")
        try:
            cost = cost_from_tokens(given, args.model, rate_overrides(args))
        except KeyError as e:
            # e.args[0], not str(e) — KeyError.__str__ repr-quotes its argument,
            # which would double-wrap a message that already reads as prose.
            _die_usage(e.args[0])
        provided["tokens_k"] = tokens_block(given)
        provided["cost"] = cost
        provided["model"] = args.model

    provided = {k: v for k, v in provided.items() if v is not None}
    if not provided:
        _die_usage("set-actual needs at least one of --elapsed-hours/--man-hours/"
                   "--hitl-hours/--tokens-* /--tokens-na")

    block_data = node.get(block)
    if block_data is None:
        from ruamel.yaml.comments import CommentedMap

        block_data = CommentedMap()
        node[block] = block_data
    for k, v in provided.items():
        block_data[k] = v if not isinstance(v, str) else _coerce(k, v)

    save_node(y, node, path, getattr(args, "flock", False))

    calib_note = ""
    if not getattr(args, "no_calibrate", False):
        # Calibration is DERIVED data. A failure here must never fail the
        # actuals write, which is the primary record — but it must be visible,
        # not silent.
        try:
            if block == "orchestration":
                # kind is "sprint" or "epic" here — a story was already rejected above.
                calib_note = record_orchestration_sample(
                    args.state_root, kind, args.epic, args.sprint if kind == "sprint" else None)
            elif kind == "story":
                # path + y so the sample can stamp its replay marker on the node
                calib_note = record_story_sample(args.state_root, node, path, y)
            elif kind == "sprint":
                calib_note = record_closure_sample(args.state_root, "sprint",
                                                   args.epic, args.sprint)
            elif kind == "epic":
                calib_note = record_closure_sample(args.state_root, "epic", args.epic)
        except Exception as e:                      # noqa: BLE001 - deliberate isolation
            sys.stderr.write(f"pm-status.py: warning — actual written, but calibration "
                             f"sample failed: {e}\n")
            calib_note = "calibration skipped (see stderr)"

    if not getattr(args, "no_events", False):
        payload = {"ts": _now_iso(), "event": "actual",
                   "from": None, "to": None,
                   "session": getattr(args, "session_id", None)}
        payload.update(_event_keys(kind, args))
        append_event(args.state_root, payload)

    suffix = f" [{calib_note}]" if calib_note else ""
    sys.stdout.write(f"OK set-actual {label} {sorted(provided)}{suffix}\n")
    return 0


def _parse_version_line(path: str):
    """Read the `# pm-status-version: X.Y.Z` marker from a copy on disk; None if absent."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            for _ in range(80):  # marker is at the top (just under the PEP-723 header)
                line = f.readline()
                if not line:
                    break
                if "pm-status-version:" in line:
                    token = line.split("pm-status-version:")[1].strip().split()[0]  # first token only
                    return tuple(int(x) for x in token.split("."))
    except (OSError, ValueError):
        return None
    return None


def _file_sha(path: str):
    """SHA-256 of a file's bytes; None if it cannot be read."""
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def cmd_self_install(args) -> int:
    """Copy this script to --dest unless the destination is already this exact script.

    This is how the module shares one runtime copy: each PM skill's setup (and its activation
    self-heal) calls `self-install --dest {project-root}/_bmad/scripts/pm-status.py`, so both
    skills reference a single installed copy — the `resolve_customization.py` pattern.

    THE GUARD IS CONTENT, NOT VERSION. It used to skip whenever the destination's version
    marker was >= this one, which made an equal version mean "identical" — an assumption the
    marker cannot carry, because it is hand-maintained and therefore drifts. It did: ten
    commits changed this script under 2.3.0, and after the bump to 2.4.0 another changed it
    again under 2.4.0. A project that installed at either moment kept a stale copy forever,
    with self-install cheerfully reporting a skip every time, and the staleness was invisible
    because both copies agreed on the number they printed. One such copy sat 920 lines behind
    and was missing a Critical fix.

    A strictly newer destination is still protected — that is a genuine downgrade and the
    version is the only thing that can express it. What no longer happens is treating "same
    number" as "same file".
    """
    src = os.path.abspath(__file__)
    dest = os.path.abspath(args.dest)
    mine = tuple(int(x) for x in PM_STATUS_VERSION.split("."))
    theirs = _parse_version_line(dest) if os.path.exists(dest) else None

    if os.path.exists(dest) and not args.force:
        same = _file_sha(src) is not None and _file_sha(src) == _file_sha(dest)
        if same:
            sys.stdout.write(f"OK self-install skipped — {dest} is already this exact script "
                             f"({PM_STATUS_VERSION})\n")
            return 0
        if theirs is not None and theirs > mine:
            sys.stdout.write(f"OK self-install skipped — {dest} is "
                             f"{'.'.join(map(str, theirs))} > {PM_STATUS_VERSION} "
                             f"(refusing to downgrade)\n")
            return 0
        if theirs is not None and theirs == mine:
            # Same number, different bytes. Installing is right; saying nothing is not --
            # this means a release shipped a changed script without moving the marker, and
            # the only place that can be noticed is here.
            sys.stderr.write(f"pm-status.py: warning — {dest} reports {PM_STATUS_VERSION} but "
                             f"its content differs from this copy; reinstalling. A changed "
                             f"script shipped under an unchanged version marker.\n")
    d = os.path.dirname(dest) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".pm-status.", suffix=".tmp", dir=d)
    try:
        with open(src, "r", encoding="utf-8") as rf, os.fdopen(fd, "w", encoding="utf-8") as wf:
            wf.write(rf.read())
            wf.flush()
            os.fsync(wf.fileno())
        os.chmod(tmp, 0o755)
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    was = ".".join(map(str, theirs)) if theirs else "absent"
    sys.stdout.write(f"OK self-install {dest} ({was} -> {PM_STATUS_VERSION})\n")
    return 0


def cmd_set_lock(args) -> int:
    path = _epic_path_or_die(args)
    y, data = load_node(path)
    if data is None:
        _die_notfound(f"epic {args.epic} file is empty")
    from ruamel.yaml.comments import CommentedMap
    lock = CommentedMap()
    lock["session_id"] = args.session_id
    lock["claimed_at"] = _now_iso()
    lock["ttl_minutes"] = args.ttl_minutes
    data["_lock"] = lock
    # _lock must appear first — rebuild with _lock at top
    ordered = CommentedMap()
    ordered["_lock"] = lock
    for k, v in data.items():
        if k != "_lock":
            ordered[k] = v
    _atomic_dump(y, ordered, path)
    sys.stdout.write(f"OK set-lock epic {args.epic} session={args.session_id} ttl={args.ttl_minutes}m\n")
    return 0


def cmd_clear_lock(args) -> int:
    path = epic_file(args.state_root, args.epic)
    if path is None:
        sys.stdout.write(f"OK clear-lock epic {args.epic} (epic/file absent — no-op)\n")
        return 0
    y, data = load_node(path)
    if data is None:
        sys.stdout.write(f"OK clear-lock epic {args.epic} (file empty — no-op)\n")
        return 0
    if "_lock" not in data:
        sys.stdout.write(f"OK clear-lock epic {args.epic} (no _lock present — no-op)\n")
        return 0
    del data["_lock"]
    _atomic_dump(y, data, path)
    sys.stdout.write(f"OK clear-lock epic {args.epic}\n")
    return 0


def cmd_check_lock(args) -> int:
    """Exit 0 if epic is free to claim; exit 5 if held by another session within TTL."""
    from datetime import datetime, timezone, timedelta
    path = epic_file(args.state_root, args.epic)
    if path is None:
        sys.stdout.write("FREE\n")
        return 0
    y, data = load_node(path)
    if data is None or "_lock" not in data:
        sys.stdout.write("FREE\n")
        return 0
    lock = data["_lock"]
    holder = str(lock.get("session_id", ""))
    if holder == args.session_id:
        sys.stdout.write(f"FREE (own session)\n")
        return 0
    claimed_str = str(lock.get("claimed_at", ""))
    ttl = int(lock.get("ttl_minutes", 30))
    try:
        claimed = datetime.fromisoformat(claimed_str.replace("Z", "+00:00"))
        age_minutes = (datetime.now(timezone.utc) - claimed).total_seconds() / 60
        if age_minutes > ttl:
            sys.stdout.write(f"FREE (stale lock from {holder}, age={age_minutes:.1f}m > ttl={ttl}m)\n")
            return 0
    except (ValueError, TypeError):
        sys.stdout.write(f"FREE (unreadable lock timestamp — treating as stale)\n")
        return 0
    sys.stdout.write(f"LOCKED by {holder} (claimed {claimed_str}, ttl={ttl}m)\n")
    return 5


def _maybe_set(d, key: str, val, coerce):
    if val is not None:
        try:
            d[key] = coerce(val)
        except (ValueError, TypeError):
            d[key] = val


def cmd_set_estimate(args) -> int:
    # Rejected before anything else is touched: cost is derived from tokens x
    # rates (cmd_estimate_story / cmd_estimate_rollup), never accepted as
    # direct input. --cost, --cost-low, and --cost-high stay declared (with
    # help=argparse.SUPPRESS) purely so this is a clear usage error instead of
    # an argparse "unrecognized arguments" one.
    if getattr(args, "cost", None) is not None or getattr(args, "cost_low", None) is not None \
            or getattr(args, "cost_high", None) is not None:
        _die_usage("cost is derived from tokens x rates and cannot be set directly — "
                   "fix the token counts or modules.l3io-pm.token_rates instead")

    kind = _infer_kind(args)
    y, node, path, label = _load_checked(args.state_root, args, kind)

    from ruamel.yaml.comments import CommentedMap
    est = node.get("estimate")
    if est is None:
        est = CommentedMap()
        node["estimate"] = est

    if kind == "story":
        # Stories: single values (not ranges)
        _maybe_set(est, "man_hours", args.man_hours, float)
        _maybe_set(est, "hitl_hours", args.hitl_hours, float)
        _maybe_set(est, "elapsed_hours", args.elapsed_hours, float)
        _maybe_set(est, "tokens_k", args.tokens_k_min, int)
    else:
        # Sprints and epics: low/high ranges
        _maybe_set(est, "man_hours_low", args.man_hours_low, float)
        _maybe_set(est, "man_hours_high", args.man_hours_high, float)
        _maybe_set(est, "hitl_hours_low", args.hitl_hours_low, float)
        _maybe_set(est, "hitl_hours_high", args.hitl_hours_high, float)
        _maybe_set(est, "elapsed_hours_low", args.elapsed_hours_low, float)
        _maybe_set(est, "elapsed_hours_high", args.elapsed_hours_high, float)
        _maybe_set(est, "tokens_k_min", args.tokens_k_min, int)
        _maybe_set(est, "tokens_k_max", args.tokens_k_max, int)

    # Calibration factors: applied to get from base values to the estimate
    _maybe_set(est, "fix_factor", getattr(args, "fix_factor", None), float)
    _maybe_set(est, "scope_ratio", getattr(args, "scope_ratio", None), float)

    # Confidence: explicit arg wins; else derive from completeness
    if args.confidence:
        est["confidence"] = args.confidence
    elif "confidence" not in est:
        # No cost/cost_low/cost_high in EITHER list: set-estimate never writes
        # any of them (cost is derived, not settable — see the rejection above),
        # so requiring one would make the estimate permanently "low" confidence.
        # The story list used to name `cost`, which set-estimate rejects at the
        # top of this function and can therefore never satisfy — so every
        # hand-written story estimate came out `low` no matter how complete it
        # was, and the derivation could only ever report one of its two values.
        range_keys = ["man_hours_low", "man_hours_high", "hitl_hours_low", "hitl_hours_high",
                      "elapsed_hours_low", "elapsed_hours_high",
                      "tokens_k_min", "tokens_k_max"]
        story_keys = ["man_hours", "hitl_hours", "elapsed_hours", "tokens_k"]
        check = story_keys if kind == "story" else range_keys
        est["confidence"] = "medium" if all(k in est for k in check) else "low"

    save_node(y, node, path, getattr(args, "flock", False))
    sys.stdout.write(f"OK set-estimate {label}\n")
    return 0


def cmd_set_field(args) -> int:
    """Set an arbitrary nested field at a dot-path within a node.
    --story KEY | --epic ID [--sprint ID] selects the node.
    --field: dot-path within the node, e.g. 'retrospective.summary', 'closed.date'
    --value: string value to set
    """
    kind = _infer_kind(args)
    y, node, path, label = _load_checked(args.state_root, args, kind)

    field_parts = args.field.split(".")
    target = node
    for part in field_parts[:-1]:
        if target.get(part) is None:
            from ruamel.yaml.comments import CommentedMap
            target[part] = CommentedMap()
        target = target[part]
    target[field_parts[-1]] = args.value

    save_node(y, node, path, getattr(args, "flock", False))
    sys.stdout.write(f"OK set-field {label} {args.field}={args.value!r}\n")
    return 0


def cmd_append_issue(args) -> int:
    """Append a BL item to the backlog: list in state/issues.yaml (flock-protected)."""
    y, data = _load(args.file)
    if data is None:
        from ruamel.yaml.comments import CommentedMap, CommentedSeq
        data = CommentedMap()
        data["backlog"] = CommentedSeq()

    if data.get("backlog") is None:
        from ruamel.yaml.comments import CommentedSeq
        data["backlog"] = CommentedSeq()

    from ruamel.yaml.comments import CommentedMap
    item = CommentedMap()
    item["key"] = args.key
    item["epic"] = args.epic
    item["sprint"] = args.sprint if args.sprint else ""
    item["title"] = args.title
    item["source"] = args.source
    item["severity"] = args.severity
    item["status"] = "backlog"
    if args.description:
        item["description"] = args.description

    data["backlog"].append(item)
    _flock_write_or_plain(True, y, data, args.file)
    sys.stdout.write(f"OK append-issue {args.key} -> {args.file}\n")
    return 0


def _norm_num(v, width: int) -> str:
    """Normalize a possibly key-prefixed or unpadded numeric id to a zero-padded digit
    string: 'E1'/'001' -> '001' (width=3); 'S1'/'01' -> '01' (width=2). Falls back to the
    stripped original string when it is not purely numeric, so a malformed stored value
    still compares by equality instead of raising."""
    s = str(v).strip()
    core = s.lstrip("EeSs")
    if core.isdigit():
        return f"{int(core):0{width}d}"
    return s


def cmd_list_issues(args) -> int:
    """List (with optional filters) the flat backlog in issues.yaml.

    A missing issues.yaml and a filter set that matches nothing are both success
    (exit 0) — an empty backlog is a normal project state, not a failure. Filters
    combine with AND; a repeated --severity ORs the given severities together.
    """
    path = os.path.join(args.state_root, "issues.yaml")
    _, data = _load(path)
    items = list((data or {}).get("backlog") or [])

    epic_filter = _norm_num(args.epic, 3) if args.epic else None
    sprint_filter = _norm_num(args.sprint, 2) if args.sprint else None
    severity_filter = set(args.severity) if args.severity else None

    def matches(item) -> bool:
        if epic_filter is not None and _norm_num(item.get("epic", ""), 3) != epic_filter:
            return False
        if sprint_filter is not None:
            item_sprint = str(item.get("sprint", "") or "").strip()
            # empty sprint = epic-level item; it never satisfies a --sprint filter
            if not item_sprint or _norm_num(item_sprint, 2) != sprint_filter:
                return False
        if severity_filter is not None and item.get("severity") not in severity_filter:
            return False
        return True

    filtered = [i for i in items if matches(i)]

    if args.format == "json":
        import json
        sys.stdout.write(json.dumps([dict(i) for i in filtered], indent=2) + "\n")
        return 0

    if not filtered:
        sys.stdout.write("(no matching issues)\n")
        return 0

    headers = ["KEY", "EPIC", "SPRINT", "SEVERITY", "STATUS", "TITLE"]
    rows = [[str(i.get("key", "")), str(i.get("epic", "")), str(i.get("sprint", "")) or "-",
             str(i.get("severity", "")), str(i.get("status", "")), str(i.get("title", ""))]
            for i in filtered]
    widths = [max(len(headers[c]), *(len(r[c]) for r in rows)) for c in range(len(headers))]

    def _fmt_row(cells):
        last = len(cells) - 1
        return "  ".join(c if idx == last else c.ljust(widths[idx]) for idx, c in enumerate(cells))

    sys.stdout.write(_fmt_row(headers) + "\n")
    for r in rows:
        sys.stdout.write(_fmt_row(r) + "\n")
    return 0


STATUS_FOR_DIR = {"planned": "backlog", "active": "in-progress", "archived": "done"}


def move_epic(state_root: str, epic_key: str, to_status: str) -> str:
    """Move an epic directory between status folders, preferring `git mv`.

    The directory name never changes — only its parent folder — so git records a
    rename and `git log --follow` keeps working on every file in the tree.

    Every path handed to `git mv` is absolutized first, and so is its `cwd`. A relative
    `state_root` would otherwise be resolved twice — once by the caller's process cwd when
    the operands were built, and again by `cwd=state_root` inside the subprocess — so git
    would be told to move a path that does not exist, fail, and drop silently through to
    the `shutil.move` fallback with exit 0 and no rename recorded. Preserving history via
    `git mv` is the entire reason this function moves directories instead of collapsing
    them, so that degradation must not be silent: the fallback now warns on stderr.
    """
    if to_status not in STATUS_DIRS:
        raise ValueError(f"bad status folder {to_status!r} — expected one of {list(STATUS_DIRS)}")
    state_root = os.path.abspath(state_root)
    src = find_epic_dir(state_root, epic_key)
    if src is None:
        raise FileNotFoundError(f"epic {epic_key} not found under {state_root}")
    src = os.path.abspath(src)
    dest_parent = os.path.join(state_root, to_status)
    dest = os.path.abspath(os.path.join(dest_parent, epic_dirname(epic_key)))
    if src == dest:
        return dest
    if os.path.exists(dest):
        raise FileExistsError(f"destination already exists: {dest}")
    os.makedirs(dest_parent, exist_ok=True)

    moved = False
    reason = "git mv was not attempted"
    try:
        import subprocess
        r = subprocess.run(["git", "mv", src, dest], cwd=state_root,
                           capture_output=True, text=True)
        moved = r.returncode == 0
        if not moved:
            reason = (r.stderr.strip() or r.stdout.strip()
                      or f"git mv exited {r.returncode}").replace("\n", " ")
    except (OSError, ImportError) as e:
        moved = False
        reason = f"could not run git: {e}"
    if not moved:
        import shutil
        sys.stderr.write(
            f"pm-status.py: WARNING — `git mv` failed ({reason}); falling back to a plain "
            f"filesystem move of {src} -> {dest}. Git will see this as delete+add, not a "
            f"rename, so `git log --follow` will not cross it for these files.\n"
        )
        shutil.move(src, dest)

    p = os.path.join(dest, "epic.yaml")
    if os.path.exists(p):
        y, node = load_node(p)
        if node is not None:
            node["status"] = STATUS_FOR_DIR[to_status]
            node["updated_at"] = _now_iso()
            save_node(y, node, p)
    return dest


def cmd_move_epic(args) -> int:
    to = getattr(args, "to", None) or "archived"
    try:
        dest = move_epic(args.state_root, args.epic, to)
    except FileNotFoundError as e:
        _die_notfound(str(e))
    except (ValueError, FileExistsError) as e:
        _die_usage(str(e))
    sys.stdout.write(f"OK move-epic {args.epic} -> {to} ({dest})\n")
    return 0


def cmd_show(args) -> int:
    """Render a computed sprint or epic roll-up. Exits 3 if the epic (or,
    when --sprint is given, that sprint within it) does not resolve — an
    empty roll-up must never be printed for a node that doesn't exist."""
    d = find_epic_dir(args.state_root, args.epic)
    if d is None:
        _die_notfound(f"epic {args.epic}")

    if args.sprint:
        sd = os.path.join(d, sprint_dirname(args.sprint))
        if not os.path.isdir(sd):
            _die_notfound(f"epic {args.epic} sprint {args.sprint}")
        r = rollup_sprint(args.state_root, args.epic, args.sprint)
        sys.stdout.write(f"{args.epic}/{r['key']}  status={r['status']}  stories={r['story_count']}\n")
        for s in r["stories"]:
            sys.stdout.write(f"  {s['key']:<20} {s['status']}\n")
        sys.stdout.write(f"  actuals: {_fmt_actuals(r['actual_totals'])}\n")
        _write_spend(r["spend"])
        return 0

    r = rollup_epic(args.state_root, args.epic)
    sys.stdout.write(f"{r['key']}  status={r['status']}  sprints={r['sprint_count']}  "
                     f"stories={r['story_count']}\n")
    for sp in r["sprints"]:
        sys.stdout.write(f"  {sp['key']:<8} status={sp['status']:<12} stories={sp['story_count']}\n")
    sys.stdout.write(f"  actuals: {_fmt_actuals(r['actual_totals'])}\n")
    _write_spend(r["spend"])
    return 0


def _write_spend(spend: dict) -> None:
    """The three-bucket breakout under a `show` roll-up.

    The `actuals:` line above is the CHILDREN's sum only — that is what it has
    always been, and callers parse it. Closure and orchestration are printed
    beside it rather than folded into it, because the whole point of the model is
    that the three are separately attributable (metrics-contract.md §6).
    """
    if not _has_spend(spend):
        return
    for bucket in SPEND_BUCKETS:
        vals = (spend or {}).get(bucket) or {}
        if vals:
            sys.stdout.write(f"  spend/{bucket:<14} {_fmt_actuals(vals)}\n")
    sys.stdout.write(f"  spend/{'TOTAL':<14} {_fmt_actuals(_spend_total(spend))}\n")


def cmd_report(args) -> int:
    """Plan-aware progress report. Read-only unless --out is given, which is what lets
    read-only callers (l3io-util-doctor stats) share this exact code path."""
    if not os.path.isdir(args.state_root):
        _die_notfound(f"state root {args.state_root}")

    if args.all and args.status:
        _die_usage("pass --all or --status, not both")
    if args.status:
        statuses = {x.strip() for x in args.status.split(",") if x.strip()}
        unknown = statuses - set(STATUS_DIRS)
        if unknown:
            _die_usage(f"unknown --status value(s) {sorted(unknown)} "
                       f"— expected a subset of {list(STATUS_DIRS)}")
    elif args.all:
        statuses = set(STATUS_DIRS)
    else:
        statuses = set(DEFAULT_REPORT_STATUSES)

    def once() -> str:
        plan = load_plan(args.plan) if args.plan else None
        model = build_progress_model(args.state_root, plan=plan, statuses=statuses)
        stalled = open_dispatches(args.state_root,
                                  getattr(args, "stall_minutes", DEFAULT_STALL_MINUTES))
        if args.format == "json":
            model["stalled_dispatches"] = stalled
            return json.dumps(model, indent=2, sort_keys=True) + "\n"
        text = render_md(model) if args.format == "md" else render_tree(model)
        if stalled:
            lines = ["", "STALLED DISPATCH (open past threshold):"]
            for s in stalled:
                where = " ".join(x for x in (s["epic"], s["sprint"], s["story"]) if x)
                lines.append(f"  {s['agent']:<20} {where:<28} "
                             f"{s['age_minutes']}m  since {s['opened_at']}")
            text = text + "\n".join(lines) + "\n"
        return text

    if args.watch:
        import time
        try:
            while True:
                sys.stdout.write("\x1b[2J\x1b[H")   # clear + home
                sys.stdout.write(once())
                sys.stdout.write(f"\n[refreshing every {args.watch}s — Ctrl-C to stop]\n")
                sys.stdout.flush()
                time.sleep(args.watch)
        except KeyboardInterrupt:
            return 0

    text = once()
    if args.out:
        d = os.path.dirname(os.path.abspath(args.out)) or "."
        os.makedirs(d, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        sys.stdout.write(f"OK report {args.out} ({args.format})\n")
        return 0
    sys.stdout.write(text)
    return 0


def cmd_verify(args) -> int:
    kind = args.scope  # story | sprint | epic
    if kind == "epic":
        y, node, path, label = _load_checked(args.state_root, args, kind)
        failures: list[str] = []
        for sd in list_sprint_dirs(args.state_root, args.epic):
            skey = _sprint_key_from_dir(sd)
            sp = sprint_file(args.state_root, args.epic, skey)
            if sp is None:
                failures.append(f"{skey}: sprint.yaml missing")
            else:
                _, snode = load_node(sp)
                failures += [f"{skey}: {p}" for p in check_backrefs(snode, args.epic)]
            for stf in list_story_files(args.state_root, args.epic, skey):
                _, stnode = load_node(stf)
                if stnode is None:
                    failures.append(f"{os.path.basename(stf)}: empty")
                    continue
                failures += [f"{stnode.get('key', '?')}: {p}"
                             for p in check_backrefs(stnode, args.epic, skey)]
        if failures:
            for f in failures:
                sys.stderr.write(f"FAIL {f}\n")
            return 4
        sys.stdout.write(f"PASS epic {args.epic}\n")
        return 0

    y, node, path, label = _load_checked(args.state_root, args, kind)

    problems: list[str] = []
    if node.get("status") != "done":
        problems.append(f"status={node.get('status')!r} (expected done)")

    actual = node.get("actual") or {}
    required = list(METRIC_FIELDS)
    for m in required:
        if m not in actual:
            problems.append(f"actual.{m} absent")
            continue
        val = actual[m]
        # Numeric fields must be numeric; token/cost may be N/A only under non-claude runtime.
        if m in ("elapsed_hours", "man_hours", "hitl_hours"):
            if _is_na(val) or not _is_number(val):
                problems.append(f"actual.{m}={val!r} (must be numeric)")
        else:  # tokens_k, cost
            if _is_na(val):
                if args.require_tokens or args.runtime == "claude":
                    problems.append(f"actual.{m}=N/A (forbidden under runtime=claude / --require-tokens)")

    # tokens_k, once structured, is self-verifying: its total must equal the sum
    # of its four classes, and its cost must equal what those tokens price out to
    # under its own recorded model. A hand-edited cost is exactly the failure
    # this closes — without it, a bogus number survives in committed state
    # indefinitely because nothing ever recomputes it.
    tk = actual.get("tokens_k")
    if hasattr(tk, "get"):
        parts = sum(_num_or_none(tk.get(c)) or 0.0 for c in TOKEN_CLASSES)
        total = _num_or_none(tk.get("total"))
        # Unlike cost (below), total and parts are NOT on the same rounding grid:
        # `total` was rounded to 2dp once at write time (tokens_block), but
        # `parts` here is an unrounded re-sum of the class values. That write-time
        # rounding alone can separate a legitimate total from its exact sum by up
        # to half the last decimal place (0.005) with no error involved at all —
        # so tightening this to cost's 0.005 would risk failing correctly-rounded
        # data. 0.01 keeps a safe margin above that rounding noise while still
        # catching any genuine (typically integer-scale, since counts are whole
        # thousands of tokens) divergence.
        if total is None or abs(total - parts) > 0.01:
            problems.append(f"actual.tokens_k.total={total!r} != sum of classes ({parts})")
        model = actual.get("model")
        if not model:
            problems.append("actual.model absent (cost cannot be verified)")
        else:
            try:
                expect = cost_from_tokens(tk, str(model), rate_overrides(args))
            except KeyError as e:
                # e.args[0], not str(e) — KeyError.__str__ repr-quotes its argument,
                # which would double-wrap a message that already reads as prose.
                problems.append(e.args[0])
            else:
                got = _num_or_none(actual.get("cost"))
                # Both got and expect are already rounded to cents (the smallest
                # unit either can carry), so the smallest genuine divergence is
                # exactly one cent (0.01). A tolerance of 0.01 would not fire on
                # it — the tolerance would be exactly the size of the error it
                # exists to catch. Half the discrete unit still absorbs true
                # float-summation noise (~1e-9 to 1e-14) with enormous margin
                # while catching any one-cent divergence.
                if got is None or abs(got - expect) > 0.005:
                    problems.append(f"actual.cost={got!r} != derived {expect} "
                                    f"for model {model}")
    elif "tokens_k" in actual and not _is_na(tk):
        # A bare scalar tokens_k has no class split, so the cost invariant above
        # cannot run at all — `tokens_k: 500` next to `cost: 9999.99` used to
        # return PASS. Design §4.3 says a hand-edited cost cannot survive verify;
        # keeping the pre-rework scalar shape was a one-line way around it. The
        # scalar form stays legitimate under runtime=other (set-estimate writes
        # it, and a runtime with no per-class visibility has nothing better), so
        # this fires only where exact per-class capture is required.
        if args.require_tokens or args.runtime == "claude":
            problems.append(
                f"actual.tokens_k={tk!r} is not the per-class mapping — cost cannot be "
                f"verified against it. Re-capture the four classes with set-actual "
                f"--tokens-input/--tokens-output/--tokens-cache-write/--tokens-cache-read "
                f"and --model (metrics-contract.md §3)")

    if kind == "story" and "completion_evidence" not in node:
        problems.append("completion_evidence absent")

    if problems:
        sys.stdout.write(f"FAIL {label}: " + "; ".join(problems) + "\n")
        return 4
    sys.stdout.write(f"PASS {label}\n")
    return 0


# --------------------------------------------------------------------------- #
# value helpers
# --------------------------------------------------------------------------- #
def _is_na(v) -> bool:
    return isinstance(v, str) and v.strip().upper() in {"N/A", "NA", "NONE", ""}


def _is_number(v) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    if isinstance(v, str):
        try:
            float(v)
            return True
        except ValueError:
            return False
    return False


def _coerce(field: str, v: str):
    """Numeric metrics become int/float unless N/A. `cost` is derived, not entered;
    the only string it can be here is N/A."""
    if _is_na(v):
        return v
    try:
        f = float(v)
        return int(f) if f.is_integer() and field != "cost" else f
    except ValueError:
        return v


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pm-status.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def node_args(sp):
        sp.add_argument("--story", help="story key (addresses a story node)")
        sp.add_argument("--epic", help="zero-paddable epic id")
        sp.add_argument("--sprint", help="zero-paddable sprint id")

    s = sub.add_parser("set-status", help="set a node's status atomically")
    s.add_argument("--state-root", required=True, help="path to {implementation_artifacts}/state")
    node_args(s)
    s.add_argument("--status", required=True)
    s.add_argument("--title")
    s.add_argument("--flock", action="store_true", help="acquire exclusive flock before write")
    s.add_argument("--no-events", dest="no_events", action="store_true",
                   help="skip the events.jsonl append for this call")
    s.add_argument("--session-id", dest="session_id", default=None,
                   help="recorded in the event payload; null when omitted")
    s.set_defaults(func=cmd_set_status)

    a = sub.add_parser("set-actual", help="write a validated actual block")
    a.add_argument("--state-root", required=True, help="path to {implementation_artifacts}/state")
    a.add_argument("--node", required=True, choices=["story", "sprint", "epic"])
    node_args(a)
    a.add_argument("--block", choices=["actual", "orchestration"], default="actual",
                   help="which metric block to write (orchestration: sprint/epic only)")
    a.add_argument("--elapsed-hours", dest="elapsed_hours")
    a.add_argument("--man-hours", dest="man_hours")
    a.add_argument("--hitl-hours", dest="hitl_hours",
                   help="human attention actually spent supervising (hours)")
    a.add_argument("--tokens-input", dest="tokens_input")
    a.add_argument("--tokens-output", dest="tokens_output")
    a.add_argument("--tokens-cache-write", dest="tokens_cache_write")
    a.add_argument("--tokens-cache-read", dest="tokens_cache_read")
    a.add_argument("--tokens-na", dest="tokens_na", action="store_true",
                   help="record tokens/cost as N/A (runtime=other only)")
    a.add_argument("--model", default="", help="model id that priced these tokens")
    a.add_argument("--token-rates", dest="token_rates", default="",
                   help="JSON object of per-model rate overrides")
    a.add_argument("--cost", default=None, help=argparse.SUPPRESS)
    a.add_argument("--runtime", choices=["claude", "other"], default="other")
    a.add_argument("--flock", action="store_true", help="acquire exclusive flock before write")
    a.add_argument("--no-calibrate", dest="no_calibrate", action="store_true",
                   help="skip calibration sampling (backfills, replays)")
    a.add_argument("--no-events", dest="no_events", action="store_true",
                   help="skip the events.jsonl append for this call")
    a.add_argument("--session-id", dest="session_id", default=None,
                   help="recorded in the event payload; null when omitted")
    a.set_defaults(func=cmd_set_actual)

    v = sub.add_parser("verify", help="read-back gate; nonzero exit on any gap")
    v.add_argument("--state-root", required=True, help="path to {implementation_artifacts}/state")
    v.add_argument("--scope", required=True, choices=["story", "sprint", "epic"])
    node_args(v)
    v.add_argument("--require-tokens", action="store_true")
    v.add_argument("--runtime", choices=["claude", "other"], default="other")
    v.add_argument("--token-rates", dest="token_rates", default="",
                   help="JSON object of per-model rate overrides")
    v.set_defaults(func=cmd_verify)

    sh = sub.add_parser("show", help="render a computed sprint or epic roll-up")
    sh.add_argument("--state-root", required=True)
    sh.add_argument("--epic", required=True)
    sh.add_argument("--sprint", default="")
    sh.set_defaults(func=cmd_show)

    rp = sub.add_parser("report", help="plan-aware progress report (read-only unless --out)")
    rp.add_argument("--state-root", required=True)
    rp.add_argument("--plan", default="", help="path to plan-output-meta.yaml")
    rp.add_argument("--format", choices=["tree", "json", "md"], default="tree")
    rp.add_argument("--out", default="", help="write to this file instead of stdout")
    rp.add_argument("--all", action="store_true",
                    help="show every status folder (sugar for --status planned,active,archived)")
    rp.add_argument("--status", default="",
                    help="comma list of state folders to display: planned, active, archived "
                         "(default: planned,active). Counting is unaffected — phase "
                         "denominators always see the whole tree")
    rp.add_argument("--watch", type=int, default=0, metavar="SECS",
                    help="re-render on an interval (tree only in practice)")
    rp.add_argument("--stall-minutes", dest="stall_minutes", type=float,
                    default=DEFAULT_STALL_MINUTES,
                    help="flag dispatches open longer than this (default 15)")
    rp.set_defaults(func=cmd_report)

    dp = sub.add_parser("dispatch", help="record a subagent dispatch open/close")
    dp.add_argument("--state-root", required=True)
    dp.add_argument("--event", required=True, choices=["open", "close"])
    dp.add_argument("--agent", required=True)
    dp.add_argument("--epic", default="")
    dp.add_argument("--sprint", default="")
    dp.add_argument("--story", default="")
    dp.add_argument("--session-id", dest="session_id", default=None)
    dp.set_defaults(func=cmd_dispatch)

    si = sub.add_parser("self-install", help="copy this script to --dest, version-guarded")
    si.add_argument("--dest", required=True, help="target path, e.g. {project-root}/_bmad/scripts/pm-status.py")
    si.add_argument("--force", action="store_true", help="overwrite even if dest is same/newer")
    si.set_defaults(func=cmd_self_install)

    sl = sub.add_parser("set-lock", help="write _lock block to a per-epic active file")
    sl.add_argument("--state-root", required=True)
    sl.add_argument("--epic", required=True, help="epic key, e.g. E001")
    sl.add_argument("--session-id", dest="session_id", required=True)
    sl.add_argument("--ttl-minutes", dest="ttl_minutes", type=int, default=30)
    sl.set_defaults(func=cmd_set_lock)

    cl = sub.add_parser("clear-lock", help="remove _lock block from a per-epic active file")
    cl.add_argument("--state-root", required=True)
    cl.add_argument("--epic", required=True, help="epic key, e.g. E001")
    cl.set_defaults(func=cmd_clear_lock)

    ck = sub.add_parser("check-lock", help="check if a per-epic file is free to claim; exit 5 if held")
    ck.add_argument("--state-root", required=True)
    ck.add_argument("--epic", required=True, help="epic key, e.g. E001")
    ck.add_argument("--session-id", dest="session_id", required=True, help="caller's session id")
    ck.set_defaults(func=cmd_check_lock)

    se = sub.add_parser("set-estimate", help="write estimate block to a story, sprint, or epic node")
    se.add_argument("--state-root", required=True, help="path to {implementation_artifacts}/state")
    node_args(se)
    # Range fields (sprint/epic)
    se.add_argument("--man-hours-low", dest="man_hours_low")
    se.add_argument("--man-hours-high", dest="man_hours_high")
    se.add_argument("--hitl-hours-low", dest="hitl_hours_low")
    se.add_argument("--hitl-hours-high", dest="hitl_hours_high")
    se.add_argument("--elapsed-hours-low", "--time-hours-low", dest="elapsed_hours_low")
    se.add_argument("--elapsed-hours-high", "--time-hours-high", dest="elapsed_hours_high")
    se.add_argument("--tokens-k-min", dest="tokens_k_min")
    se.add_argument("--tokens-k-max", dest="tokens_k_max")
    # --cost / --cost-low / --cost-high are declared but SUPPRESSed from --help
    # and rejected in cmd_set_estimate: cost is derived from tokens x rates,
    # never accepted as direct input (see the rejection at the top of
    # cmd_set_estimate). Declaring them here — rather than leaving them
    # unrecognized — turns that rejection into a clear usage error instead of
    # argparse's generic "unrecognized arguments".
    se.add_argument("--cost-low", dest="cost_low", help=argparse.SUPPRESS)
    se.add_argument("--cost-high", dest="cost_high", help=argparse.SUPPRESS)
    # Single-value fields (story)
    se.add_argument("--man-hours", dest="man_hours")
    se.add_argument("--hitl-hours", dest="hitl_hours",
                    help="human attention actually spent supervising (hours)")
    se.add_argument("--elapsed-hours", "--time-hours", dest="elapsed_hours",
                    help="--time-hours is a deprecated alias")
    se.add_argument("--tokens-k", dest="tokens_k_min")  # alias to tokens_k_min for story use
    se.add_argument("--cost", dest="cost", help=argparse.SUPPRESS)
    se.add_argument("--confidence", choices=["low", "medium", "high"])
    se.add_argument("--fix-factor", dest="fix_factor",
                    help="fix multiplier applied; required for the scope/fix split")
    se.add_argument("--scope-ratio", dest="scope_ratio",
                    help="calibrated scope ratio applied (1.0 when cold-start)")
    se.add_argument("--flock", action="store_true", help="acquire exclusive flock before write")
    se.set_defaults(func=cmd_set_estimate)

    sf = sub.add_parser("set-field", help="set a nested field at a dot-path within a node")
    sf.add_argument("--state-root", required=True, help="path to {implementation_artifacts}/state")
    node_args(sf)
    sf.add_argument("--field", required=True, help="dot-path within the node, e.g. 'retrospective.summary'")
    sf.add_argument("--value", required=True, help="string value to set")
    sf.set_defaults(func=cmd_set_field)

    ai = sub.add_parser("append-issue", help="append a BL item to state/issues.yaml")
    ai.add_argument("--file", required=True)
    ai.add_argument("--key", required=True, help="BL-E{nnn}-{nnn}")
    ai.add_argument("--epic", required=True, help="zero-padded epic number, e.g. '001'")
    ai.add_argument("--sprint", default="", help="zero-padded sprint number; empty for epic-level")
    ai.add_argument("--title", required=True)
    ai.add_argument("--source", required=True, help="review phase + finding ID")
    ai.add_argument("--severity", required=True, choices=["Low", "Medium", "High", "Critical"])
    ai.add_argument("--description", default="")
    ai.set_defaults(func=cmd_append_issue)

    li = sub.add_parser("list-issues", help="list (with filters) the flat backlog in issues.yaml")
    li.add_argument("--state-root", required=True, help="path to {implementation_artifacts}/state")
    li.add_argument("--epic", help="epic id — accepts 'E001' or '001'")
    li.add_argument("--sprint", help="sprint id — accepts 'S01' or '01'; never matches an epic-level (empty-sprint) item")
    li.add_argument("--severity", action="append", choices=["Low", "Medium", "High", "Critical"],
                    help="filter by severity; repeat to OR multiple severities")
    li.add_argument("--format", choices=["text", "json"], default="text")
    li.set_defaults(func=cmd_list_issues)

    mv = sub.add_parser("move-epic", help="move an epic directory between status folders")
    mv.add_argument("--state-root", required=True)
    mv.add_argument("--epic", required=True)
    mv.add_argument("--to", required=True, choices=list(STATUS_DIRS))
    mv.set_defaults(func=cmd_move_epic)

    ae = sub.add_parser("archive-epic", help="alias for move-epic --to archived")
    ae.add_argument("--state-root", required=True)
    ae.add_argument("--epic", required=True)
    ae.set_defaults(func=cmd_move_epic, to="archived")

    cal = sub.add_parser("calibration", help="inspect the calibration file")
    cal.add_argument("action", choices=["show", "migrate-metrics"])
    cal.add_argument("--state-root", required=True)
    cal.add_argument("--format", choices=["text", "json"], default="text")
    cal.set_defaults(func=cmd_calibration)

    es = sub.add_parser("estimate-story", help="compute and write a story estimate")
    es.add_argument("--state-root", required=True)
    es.add_argument("--story", required=True)
    es.add_argument("--classification", required=True, choices=list(CLASSIFICATIONS))
    es.add_argument("--confidence", choices=["low", "medium", "high"])
    es.add_argument("--model", default="",
                    help="model id to price the derived cost; falls back to DEFAULT_ESTIMATE_MODEL")
    es.add_argument("--token-rates", dest="token_rates", default="",
                    help="JSON object of per-model rate overrides")
    es.set_defaults(func=cmd_estimate_story)

    er = sub.add_parser("estimate-rollup", help="roll child estimates up to a sprint or epic")
    er.add_argument("--state-root", required=True)
    er.add_argument("--epic", required=True)
    er.add_argument("--sprint", default="")
    er.add_argument("--model", default="",
                    help="model id to price the derived cost; falls back to DEFAULT_ESTIMATE_MODEL")
    er.add_argument("--token-rates", dest="token_rates", default="",
                    help="JSON object of per-model rate overrides")
    er.set_defaults(func=cmd_estimate_rollup)

    rt = sub.add_parser("rates", help="print the effective token rate table (read-only)")
    rt.add_argument("--model", default="")
    rt.add_argument("--token-rates", dest="token_rates", default="",
                    help="JSON object of per-model rate overrides")
    rt.set_defaults(func=cmd_rates)

    p.add_argument("--version", action="version", version=f"pm-status.py {PM_STATUS_VERSION}")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
