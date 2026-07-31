#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
# pm-status-version: 1.0.0   (machine-readable marker; `self-install` compares this across copies — keep at top)
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

PM_STATUS_VERSION = "1.0.0"  # keep in sync with the top-of-file `# pm-status-version:` marker

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


def _epics(data):
    if not data or "epics" not in data or data["epics"] is None:
        return []
    return data["epics"]


def _pad(v) -> str:
    """Normalize an id to a comparable string: zero-pad bare 1-2 digit numbers."""
    s = str(v).strip()
    return s.zfill(2) if s.isdigit() and len(s) <= 2 else s


def find_epic(data, epic_id):
    want = _pad(epic_id)
    for e in _epics(data):
        if _pad(e.get("id")) == want:
            return e
    return None


def find_sprint(data, epic_id, sprint_id):
    e = find_epic(data, epic_id)
    if e is None:
        return None
    want = _pad(sprint_id)
    for s in e.get("sprints") or []:
        if _pad(s.get("id")) == want:
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
    _atomic_dump(y, data, args.file)

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

    _atomic_dump(y, data, args.file)
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

    p.add_argument("--version", action="version", version=f"pm-status.py {PM_STATUS_VERSION}")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
