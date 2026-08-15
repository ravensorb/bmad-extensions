#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
# pm-status-version: 2.0.0   (machine-readable marker; `self-install` compares this across copies — keep at top)
"""
pm-status.py — deterministic, atomic, round-trip-safe writer for the l3io-pm
split status files and the per-sprint progress ledger.

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
  set-status  --file F  (--story KEY | --epic ID [--sprint ID])  --status S
              [--title T] [--ledger L]
  set-actual  --file F   --node {story,sprint,epic}  (--story KEY | --epic ID [--sprint ID])
              [--elapsed-hours H] [--man-hours H] [--tokens-k K] [--cost C]
              [--runtime {claude,other}] [--ledger L]
  progress    --ledger L  --msg "..."  [--scope "E01/S02/ST03"]
  verify      --file F  --scope {story,sprint}  (--story KEY | --epic ID [--sprint ID])
              [--require-tokens] [--runtime {claude,other}]

Exit codes: 0 = success/verified, 2 = usage error, 3 = node not found,
4 = verification failure (missing/invalid field). Errors go to stderr; machine
output (verify summaries) goes to stdout.
"""
from __future__ import annotations

import argparse
import os
import sys
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

PM_STATUS_VERSION = "2.0.0"  # keep in sync with the top-of-file `# pm-status-version:` marker

VALID_STORY_STATUS = {"backlog", "ready-for-dev", "in-progress", "review", "done"}
VALID_SPRINT_STATUS = {"backlog", "in-progress", "done"}
VALID_EPIC_STATUS = {"backlog", "in-progress", "done"}
METRIC_FIELDS = ("elapsed_hours", "man_hours", "tokens_k", "cost")


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


def _epics(data):
    if not data or "epics" not in data or data["epics"] is None:
        return []
    return data["epics"]


def _pad(v) -> str:
    """Normalize an id to a comparable string: zero-pad bare 1-2 digit numbers."""
    s = str(v).strip()
    return s.zfill(2) if s.isdigit() and len(s) <= 2 else s


def find_epic(data, epic_id):
    want = str(epic_id).strip()
    for e in _epics(data):
        # key-first (new schema), id fallback (legacy schema)
        if str(e.get("key", "")).strip() == want or _pad(e.get("id")) == _pad(want):
            return e
    return None


def find_sprint(data, epic_id, sprint_id):
    e = find_epic(data, epic_id)
    if e is None:
        return None
    want = str(sprint_id).strip()
    for s in e.get("sprints") or []:
        if str(s.get("key", "")).strip() == want or _pad(s.get("id")) == _pad(want):
            return s
    return None


def find_story(data, story_key):
    """Locate a story node by its `key` anywhere in epics -> sprints -> stories."""
    for e in _epics(data):
        for s in e.get("sprints") or []:
            for st in s.get("stories") or []:
                if str(st.get("key")) == str(story_key):
                    return st
    return None


def _resolve_node(data, args, node_kind: str):
    if node_kind == "story":
        if not args.story:
            _die_usage("--story is required for a story node")
        return find_story(data, args.story), f"story {args.story}"
    if node_kind == "sprint":
        if not (args.epic and args.sprint):
            _die_usage("--epic and --sprint are required for a sprint node")
        return find_sprint(data, args.epic, args.sprint), f"epic {args.epic} sprint {args.sprint}"
    if node_kind == "epic":
        if not args.epic:
            _die_usage("--epic is required for an epic node")
        return find_epic(data, args.epic), f"epic {args.epic}"
    _die_usage(f"unknown node kind: {node_kind}")


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


def _append_ledger(ledger: str, scope: str, msg: str) -> None:
    d = os.path.dirname(os.path.abspath(ledger)) or "."
    os.makedirs(d, exist_ok=True)
    line = f"{_now_iso()}  {scope or '-'}  {msg}\n"
    with open(ledger, "a", encoding="utf-8") as f:
        f.write(line)


# --------------------------------------------------------------------------- #
# subcommands
# --------------------------------------------------------------------------- #
def cmd_set_status(args) -> int:
    kind = _infer_kind(args)
    valid = {"story": VALID_STORY_STATUS, "sprint": VALID_SPRINT_STATUS, "epic": VALID_EPIC_STATUS}[kind]
    if args.status not in valid:
        _die_usage(f"invalid {kind} status '{args.status}' — expected one of {sorted(valid)}")

    y, data = _load(args.file)
    if data is None:
        _die_notfound(f"status file {args.file} is empty or missing")
    node, label = _resolve_node(data, args, kind)
    if node is None:
        _die_notfound(label)

    node["status"] = args.status
    node["updated_at"] = _now_iso()
    if args.title:
        node["title"] = args.title
    _flock_write_or_plain(getattr(args, "flock", False), y, data, args.file)

    if args.ledger:
        scope = args.scope or (args.story or f"E{_pad(args.epic)}" + (f"/S{_pad(args.sprint)}" if args.sprint else ""))
        _append_ledger(args.ledger, scope, f"status -> {args.status}")
    sys.stdout.write(f"OK set-status {label} -> {args.status}\n")
    return 0


def cmd_set_actual(args) -> int:
    kind = args.node
    y, data = _load(args.file)
    if data is None:
        _die_notfound(f"status file {args.file} is empty or missing")
    node, label = _resolve_node(data, args, kind)
    if node is None:
        _die_notfound(label)

    provided = {
        "elapsed_hours": args.elapsed_hours,
        "man_hours": args.man_hours,
        "tokens_k": args.tokens_k,
        "cost": args.cost,
    }
    provided = {k: v for k, v in provided.items() if v is not None}
    if not provided:
        _die_usage("set-actual needs at least one of --elapsed-hours/--man-hours/--tokens-k/--cost")

    # HARD RULE: under Claude, token/cost must be a real value, never absent or N/A.
    if args.runtime == "claude":
        for m in ("tokens_k", "cost"):
            if m in provided and _is_na(provided[m]):
                _die_usage(f"runtime=claude forbids {m}=N/A — capture the exact value (see metrics-contract.md)")

    actual = node.get("actual")
    if actual is None:
        from ruamel.yaml.comments import CommentedMap

        actual = CommentedMap()
        node["actual"] = actual
    for k, v in provided.items():
        actual[k] = _coerce(k, v)

    _flock_write_or_plain(getattr(args, "flock", False), y, data, args.file)
    if args.ledger:
        _append_ledger(args.ledger, args.scope or label, f"actual {sorted(provided)}")
    sys.stdout.write(f"OK set-actual {label} {sorted(provided)}\n")
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


def cmd_self_install(args) -> int:
    """Copy this script to --dest, version-guarded (dest missing or self newer), unless --force.

    This is how the module shares one runtime copy: each PM skill's setup (and its activation
    self-heal) calls `self-install --dest {project-root}/_bmad/scripts/pm-status.py`, so both
    skills reference a single installed copy — the `resolve_customization.py` pattern.
    """
    src = os.path.abspath(__file__)
    dest = os.path.abspath(args.dest)
    mine = tuple(int(x) for x in PM_STATUS_VERSION.split("."))
    theirs = _parse_version_line(dest) if os.path.exists(dest) else None

    if os.path.exists(dest) and not args.force and theirs is not None and theirs >= mine:
        sys.stdout.write(f"OK self-install skipped — {dest} is {'.'.join(map(str, theirs))} ≥ {PM_STATUS_VERSION}\n")
        return 0
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
    y, data = _load(args.file)
    if data is None:
        _die_notfound(f"status file {args.file} is empty or missing")
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
    _atomic_dump(y, ordered, args.file)
    sys.stdout.write(f"OK set-lock {args.file} session={args.session_id} ttl={args.ttl_minutes}m\n")
    return 0


def cmd_clear_lock(args) -> int:
    y, data = _load(args.file)
    if data is None:
        sys.stdout.write(f"OK clear-lock {args.file} (file absent — no-op)\n")
        return 0
    if "_lock" not in data:
        sys.stdout.write(f"OK clear-lock {args.file} (no lock present — no-op)\n")
        return 0
    del data["_lock"]
    _atomic_dump(y, data, args.file)
    sys.stdout.write(f"OK clear-lock {args.file}\n")
    return 0


def cmd_check_lock(args) -> int:
    """Exit 0 if file is free to claim; exit 5 if held by another session within TTL."""
    from datetime import datetime, timezone, timedelta
    y, data = _load(args.file)
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
    kind = _infer_kind(args)
    y, data = _load(args.file)
    if data is None:
        _die_notfound(f"status file {args.file} is empty or missing")
    node, label = _resolve_node(data, args, kind)
    if node is None:
        _die_notfound(label)

    from ruamel.yaml.comments import CommentedMap
    est = node.get("estimate")
    if est is None:
        est = CommentedMap()
        node["estimate"] = est

    if kind == "story":
        # Stories: single values (not ranges)
        _maybe_set(est, "man_hours", args.man_hours, float)
        _maybe_set(est, "time_hours", args.time_hours, float)
        _maybe_set(est, "tokens_k", args.tokens_k_min, int)
        _maybe_set(est, "cost", args.cost_low, str)
    else:
        # Sprints and epics: low/high ranges
        _maybe_set(est, "man_hours_low", args.man_hours_low, float)
        _maybe_set(est, "man_hours_high", args.man_hours_high, float)
        _maybe_set(est, "time_hours_low", args.time_hours_low, float)
        _maybe_set(est, "time_hours_high", args.time_hours_high, float)
        _maybe_set(est, "tokens_k_min", args.tokens_k_min, int)
        _maybe_set(est, "tokens_k_max", args.tokens_k_max, int)
        _maybe_set(est, "cost_low", args.cost_low, str)
        _maybe_set(est, "cost_high", args.cost_high, str)

    # Confidence: explicit arg wins; else derive from completeness
    if args.confidence:
        est["confidence"] = args.confidence
    elif "confidence" not in est:
        range_keys = ["man_hours_low", "man_hours_high", "time_hours_low", "time_hours_high",
                      "tokens_k_min", "tokens_k_max", "cost_low", "cost_high"]
        story_keys = ["man_hours", "time_hours", "tokens_k", "cost"]
        check = story_keys if kind == "story" else range_keys
        est["confidence"] = "medium" if all(k in est for k in check) else "low"

    _flock_write_or_plain(getattr(args, "flock", False), y, data, args.file)
    sys.stdout.write(f"OK set-estimate {label}\n")
    return 0


def cmd_set_field(args) -> int:
    """Set an arbitrary nested field at a dot-path within a found node.
    --node format: 'epic.E001', 'sprint.E001.S01', or 'story.E001-S01-001'
    --field: dot-path within the node, e.g. 'retrospective.summary', 'closed.date'
    --value: string value to set
    """
    parts = args.node.split(".", 1)
    if len(parts) < 2:
        _die_usage("--node must be 'epic.KEY', 'sprint.EPIC.SPRINT', or 'story.KEY'")
    kind, ref = parts[0], parts[1]

    y, data = _load(args.file)
    if data is None:
        _die_notfound(f"status file {args.file} is empty or missing")

    if kind == "epic":
        node = find_epic(data, ref)
        label = f"epic {ref}"
    elif kind == "sprint":
        sub = ref.split(".", 1)
        if len(sub) < 2:
            _die_usage("--node sprint requires 'sprint.EPIC.SPRINT'")
        node = find_sprint(data, sub[0], sub[1])
        label = f"sprint {sub[0]}.{sub[1]}"
    elif kind == "story":
        node = find_story(data, ref)
        label = f"story {ref}"
    else:
        _die_usage(f"unknown node kind '{kind}' — use epic, sprint, or story")

    if node is None:
        _die_notfound(label)

    field_parts = args.field.split(".")
    target = node
    for part in field_parts[:-1]:
        if target.get(part) is None:
            from ruamel.yaml.comments import CommentedMap
            target[part] = CommentedMap()
        target = target[part]
    target[field_parts[-1]] = args.value

    _atomic_dump(y, data, args.file)
    sys.stdout.write(f"OK set-field {label} {args.field}={args.value!r}\n")
    return 0


def cmd_append_issue(args) -> int:
    """Append a BL item to the backlog: list in sprint-status-issues.yaml (flock-protected)."""
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


def cmd_archive_epic(args) -> int:
    """Read epics[0] from source file, append to dest file's epics list (flock-protected)."""
    y, src_data = _load(args.source)
    if src_data is None:
        _die_notfound(f"source file {args.source} is empty or missing")

    src_epics = _epics(src_data)
    if not src_epics:
        _die_notfound(f"no epic node found in {args.source}")

    epic_node = src_epics[0]  # per-epic active files have exactly one epic
    epic_node["status"] = "done"

    y2, dest_data = _load(args.dest)
    if dest_data is None:
        from ruamel.yaml.comments import CommentedMap, CommentedSeq
        dest_data = CommentedMap()
        dest_data["epics"] = CommentedSeq()

    if dest_data.get("epics") is None:
        from ruamel.yaml.comments import CommentedSeq
        dest_data["epics"] = CommentedSeq()

    dest_data["epics"].append(epic_node)
    _flock_write_or_plain(True, y2, dest_data, args.dest)
    sys.stdout.write(f"OK archive-epic {epic_node.get('key', '?')} -> {args.dest}\n")
    return 0


def cmd_progress(args) -> int:
    if not args.msg:
        _die_usage("progress needs --msg")
    _append_ledger(args.ledger, args.scope, args.msg)
    return 0


def cmd_verify(args) -> int:
    kind = args.scope  # story | sprint
    y, data = _load(args.file)
    if data is None:
        _fail(f"status file {args.file} is empty or missing")
    node, label = _resolve_node(data, args, kind)
    if node is None:
        _fail(f"node not found — {label}")

    problems: list[str] = []
    if node.get("status") != "done":
        problems.append(f"status={node.get('status')!r} (expected done)")

    actual = node.get("actual") or {}
    required = ["elapsed_hours", "man_hours", "tokens_k", "cost"]
    for m in required:
        if m not in actual:
            problems.append(f"actual.{m} absent")
            continue
        val = actual[m]
        # Numeric fields must be numeric; token/cost may be N/A only under non-claude runtime.
        if m in ("elapsed_hours", "man_hours"):
            if _is_na(val) or not _is_number(val):
                problems.append(f"actual.{m}={val!r} (must be numeric)")
        else:  # tokens_k, cost
            if _is_na(val):
                if args.require_tokens or args.runtime == "claude":
                    problems.append(f"actual.{m}=N/A (forbidden under runtime=claude / --require-tokens)")

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
    """cost stays a string ($X.XX / N/A); numeric metrics become int/float unless N/A."""
    if field == "cost":
        from ruamel.yaml.scalarstring import SingleQuotedScalarString

        return SingleQuotedScalarString(v)  # match the schema's quoted '$X.XX' style
    if _is_na(v):
        return v
    try:
        f = float(v)
        return int(f) if field == "tokens_k" and f.is_integer() else f
    except ValueError:
        return v


def _fail(msg: str):
    sys.stdout.write(f"FAIL {msg}\n")
    sys.exit(4)


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
    s.add_argument("--file", required=True)
    node_args(s)
    s.add_argument("--status", required=True)
    s.add_argument("--title")
    s.add_argument("--ledger")
    s.add_argument("--scope")
    s.add_argument("--flock", action="store_true", help="acquire exclusive flock before write")
    s.set_defaults(func=cmd_set_status)

    a = sub.add_parser("set-actual", help="write a validated actual block")
    a.add_argument("--file", required=True)
    a.add_argument("--node", required=True, choices=["story", "sprint", "epic"])
    node_args(a)
    a.add_argument("--elapsed-hours", dest="elapsed_hours")
    a.add_argument("--man-hours", dest="man_hours")
    a.add_argument("--tokens-k", dest="tokens_k")
    a.add_argument("--cost")
    a.add_argument("--runtime", choices=["claude", "other"], default="other")
    a.add_argument("--ledger")
    a.add_argument("--scope")
    a.add_argument("--flock", action="store_true", help="acquire exclusive flock before write")
    a.set_defaults(func=cmd_set_actual)

    pr = sub.add_parser("progress", help="append a line to the progress ledger")
    pr.add_argument("--ledger", required=True)
    pr.add_argument("--msg", required=True)
    pr.add_argument("--scope")
    pr.set_defaults(func=cmd_progress)

    v = sub.add_parser("verify", help="read-back gate; nonzero exit on any gap")
    v.add_argument("--file", required=True)
    v.add_argument("--scope", required=True, choices=["story", "sprint", "epic"])
    node_args(v)
    v.add_argument("--require-tokens", action="store_true")
    v.add_argument("--runtime", choices=["claude", "other"], default="other")
    v.set_defaults(func=cmd_verify)

    si = sub.add_parser("self-install", help="copy this script to --dest, version-guarded")
    si.add_argument("--dest", required=True, help="target path, e.g. {project-root}/_bmad/scripts/pm-status.py")
    si.add_argument("--force", action="store_true", help="overwrite even if dest is same/newer")
    si.set_defaults(func=cmd_self_install)

    sl = sub.add_parser("set-lock", help="write _lock block to a per-epic active file")
    sl.add_argument("--file", required=True)
    sl.add_argument("--session-id", dest="session_id", required=True)
    sl.add_argument("--ttl-minutes", dest="ttl_minutes", type=int, default=30)
    sl.set_defaults(func=cmd_set_lock)

    cl = sub.add_parser("clear-lock", help="remove _lock block from a per-epic active file")
    cl.add_argument("--file", required=True)
    cl.set_defaults(func=cmd_clear_lock)

    ck = sub.add_parser("check-lock", help="check if a per-epic file is free to claim; exit 5 if held")
    ck.add_argument("--file", required=True)
    ck.add_argument("--session-id", dest="session_id", required=True, help="caller's session id")
    ck.set_defaults(func=cmd_check_lock)

    se = sub.add_parser("set-estimate", help="write estimate block to a story, sprint, or epic node")
    se.add_argument("--file", required=True)
    node_args(se)
    # Range fields (sprint/epic)
    se.add_argument("--man-hours-low", dest="man_hours_low")
    se.add_argument("--man-hours-high", dest="man_hours_high")
    se.add_argument("--time-hours-low", dest="time_hours_low")
    se.add_argument("--time-hours-high", dest="time_hours_high")
    se.add_argument("--tokens-k-min", dest="tokens_k_min")
    se.add_argument("--tokens-k-max", dest="tokens_k_max")
    se.add_argument("--cost-low", dest="cost_low")
    se.add_argument("--cost-high", dest="cost_high")
    # Single-value fields (story)
    se.add_argument("--man-hours", dest="man_hours")
    se.add_argument("--time-hours", dest="time_hours")
    se.add_argument("--tokens-k", dest="tokens_k_min")  # alias to tokens_k_min for story use
    se.add_argument("--cost", dest="cost_low")           # alias to cost_low for story use
    se.add_argument("--confidence", choices=["low", "medium", "high"])
    se.add_argument("--flock", action="store_true", help="acquire exclusive flock before write")
    se.set_defaults(func=cmd_set_estimate)

    sf = sub.add_parser("set-field", help="set a nested field at a dot-path within a node")
    sf.add_argument("--file", required=True)
    sf.add_argument("--node", required=True, help="'epic.KEY', 'sprint.EPIC.SPRINT', or 'story.KEY'")
    sf.add_argument("--field", required=True, help="dot-path within the node, e.g. 'retrospective.summary'")
    sf.add_argument("--value", required=True, help="string value to set")
    sf.set_defaults(func=cmd_set_field)

    ai = sub.add_parser("append-issue", help="append a BL item to sprint-status-issues.yaml")
    ai.add_argument("--file", required=True)
    ai.add_argument("--key", required=True, help="BL-E{nnn}-{nnn}")
    ai.add_argument("--epic", required=True, help="zero-padded epic number, e.g. '001'")
    ai.add_argument("--sprint", default="", help="zero-padded sprint number; empty for epic-level")
    ai.add_argument("--title", required=True)
    ai.add_argument("--source", required=True, help="review phase + finding ID")
    ai.add_argument("--severity", required=True, choices=["Low", "Medium", "High", "Critical"])
    ai.add_argument("--description", default="")
    ai.set_defaults(func=cmd_append_issue)

    ae = sub.add_parser("archive-epic", help="move epic node from active file to archived file")
    ae.add_argument("--source", required=True, help="source active file, e.g. active/E001-status.yaml")
    ae.add_argument("--dest", required=True, help="destination archived file")
    ae.set_defaults(func=cmd_archive_epic)

    p.add_argument("--version", action="version", version=f"pm-status.py {PM_STATUS_VERSION}")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
