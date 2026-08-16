#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
# pm-status-version: 2.0.2   (machine-readable marker; `self-install` compares this across copies — keep at top)
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
  set-status    --state-root S  (--story KEY | --epic ID [--sprint ID])  --status S
                [--title T] [--ledger L] [--scope SCOPE] [--flock]
  set-actual    --state-root S   --node {story,sprint,epic}  (--story KEY | --epic ID [--sprint ID])
                [--elapsed-hours H] [--man-hours H] [--tokens-k K] [--cost C]
                [--runtime {claude,other}] [--ledger L] [--scope SCOPE] [--flock]
  set-estimate  --state-root S  (--story KEY | --epic ID [--sprint ID])
                [--man-hours-low H] [--man-hours-high H] [--time-hours-low H] [--time-hours-high H]
                [--tokens-k-min K] [--tokens-k-max K] [--cost-low C] [--cost-high C]
                (sprint/epic ranges; kind is inferred from --story vs --epic[/--sprint] —
                a story node instead takes the single-value aliases --man-hours H,
                --time-hours H, --tokens-k K, --cost C)
                [--confidence {low,medium,high}] [--flock]
  set-field     --state-root S  (--story KEY | --epic ID [--sprint ID])  --field NAME --value V
  progress      --ledger L  --msg "..."  [--scope "E01/S02/ST03"]
  verify        --state-root S  --scope {story,sprint,epic}  (--story KEY | --epic ID [--sprint ID])
                [--require-tokens] [--runtime {claude,other}]
                (--scope epic checks structural/back-reference integrity across the
                epic's whole subtree; --scope story/sprint check completion of one node)
  show          --state-root S  --epic ID  [--sprint ID]
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

PM_STATUS_VERSION = "2.0.2"  # keep in sync with the top-of-file `# pm-status-version:` marker

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


def _append_ledger(ledger: str, scope: str, msg: str) -> None:
    d = os.path.dirname(os.path.abspath(ledger)) or "."
    os.makedirs(d, exist_ok=True)
    line = f"{_now_iso()}  {scope or '-'}  {msg}\n"
    with open(ledger, "a", encoding="utf-8") as f:
        f.write(line)


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
# subagents may write it, so every write takes flock. Unlike node files,
# which are sharded per story precisely to avoid this.
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
    return cal


def load_calibration(state_root: str):
    """Load the calibration file, or a fresh skeleton if absent. Never raises."""
    p = calibration_path(state_root)
    y, data = _load(p)
    if data is None:
        return _yaml(), new_calibration()
    for key, default in (("scope", CLASSIFICATIONS), ("fix", CLASSIFICATIONS),
                         ("closure", CLOSURE_LEVELS)):
        if key not in data or data[key] is None:
            from ruamel.yaml.comments import CommentedMap
            data[key] = CommentedMap((k, CommentedMap()) for k in default)
    if "granularity" not in data:
        data["granularity"] = "story"
    return y, data


def save_calibration(y, cal, state_root: str) -> None:
    """Always flock — this file is written from every set-actual."""
    _flock_write_or_plain(True, y, cal, calibration_path(state_root))


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


def _component_samples(cal, component: str, bucket: str, metric: str) -> list:
    node = ((cal.get(component) or {}).get(bucket) or {}).get(metric) or {}
    return list(node.get("samples") or [])


def active_scope_ratio(cal, classification: str, metric: str):
    s = _component_samples(cal, "scope", classification, metric)
    return weighted_ratio(s) if len(s) >= MIN_SAMPLES else None


def active_closure_ratio(cal, level: str, metric: str):
    s = _component_samples(cal, "closure", level, metric)
    return weighted_ratio(s) if len(s) >= MIN_SAMPLES else None


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


# The four metrics do NOT pair by name: an estimate's time_hours is an
# actual's elapsed_hours. Zipping keys naively produces a silently wrong
# wall-clock ratio, so the pairing is explicit. Sibling map: CLOSURE_ACTUAL_KEYS
# (range-form parent estimates) encodes the same time_hours -> elapsed_hours
# pairing for a different schema — kept separate deliberately, but if one
# changes, check the other.
ESTIMATE_TO_ACTUAL = {
    "man_hours": "man_hours",
    "time_hours": "elapsed_hours",
    "tokens_k": "tokens_k",
    "cost": "cost",
}


def derive_story_sample(node):
    """Compute a story's scope samples and its fix cohort. None when not derivable."""
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
    for e_key, a_key in ESTIMATE_TO_ACTUAL.items():
        e_val, a_val = est.get(e_key), act.get(a_key)
        if e_val is None or a_val is None:
            continue
        if _is_na(e_val) or _is_na(a_val):
            continue          # never coerce N/A to zero
        if not _is_number(e_val) or not _is_number(a_val):
            continue
        e_num = float(str(e_val).lstrip("$"))
        a_num = float(str(a_val).lstrip("$"))
        if e_num == 0:
            continue
        # Both paths multiply by the applied fix factor: a pure-scope actual is
        # still compared against an estimate that had fix baked in.
        ratios[e_key] = a_num * fix_factor / e_num

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


def record_story_sample(state_root: str, node) -> str:
    """Derive a story's calibration sample and append it to the shared file.

    A write path, unlike load_calibration: migrates a stale schema version
    before appending, so a v1 file is never mistaken for v2 and corrupted by
    samples landing in a structure that doesn't exist there yet.
    """
    sample = derive_story_sample(node)
    if sample is None:
        return "no sample (missing estimate or actual)"
    from ruamel.yaml.comments import CommentedMap
    y, cal = load_calibration(state_root)
    if cal.get("version") != CALIBRATION_SCHEMA_VERSION:
        cal = migrate_calibration(y, cal, state_root)
    cls = sample["classification"]

    bucket = cal["scope"].setdefault(cls, CommentedMap())
    for metric, ratio in sample["scope_ratios"].items():
        entry = bucket.setdefault(metric, CommentedMap())
        entry.setdefault("samples", [])
        entry["samples"].append(round(ratio, 4))

    fix_entry = cal["fix"].setdefault(cls, CommentedMap())
    iters = sample["fix_iterations"]
    if iters is not None:
        _bump_cohort(fix_entry, "clean" if iters == 0 else "reworked",
                     sample["actual_man_hours"])

    save_calibration(y, cal, state_root)
    return (f"scope+{len(sample['scope_ratios'])} metrics, "
            f"provenance={sample['provenance']}, class={cls}")


def cmd_calibration(args) -> int:
    _, cal = load_calibration(args.state_root)
    exists = os.path.exists(calibration_path(args.state_root))
    rows = []
    for c in CLASSIFICATIONS:
        for m in ("man_hours", "time_hours", "tokens_k", "cost"):
            n = len(_component_samples(cal, "scope", c, m))
            r = active_scope_ratio(cal, c, m)
            rows.append(("scope", f"{c}/{m}", n, r))
    for lv in CLOSURE_LEVELS:
        for m in ("man_hours", "time_hours", "tokens_k", "cost"):
            n = len(_component_samples(cal, "closure", lv, m))
            r = active_closure_ratio(cal, lv, m)
            rows.append(("closure", f"{lv}/{m}", n, r))
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
    sys.stdout.write(f"{'COMPONENT':<10} {'BUCKET':<22} {'SAMPLES':>7}  RATIO\n")
    for a, b, n, r in rows:
        shown = f"{r:.3f}" if r is not None else f"(cold-start, needs {MIN_SAMPLES})"
        sys.stdout.write(f"{a:<10} {b:<22} {n:>7}  {shown}\n")
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
        v = actual.get(m)
        if v is None or _is_na(v):
            continue
        try:
            totals[m] = totals.get(m, 0.0) + float(v)
        except (TypeError, ValueError):
            continue


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
        "stories": stories,
    }


def rollup_epic(state_root: str, epic_key: str) -> dict:
    by_status, totals, sprints, story_count = {}, {}, [], 0
    for sd in list_sprint_dirs(state_root, epic_key):
        skey = _sprint_key_from_dir(sd)
        r = rollup_sprint(state_root, epic_key, skey)
        sprints.append(r)
        story_count += r["story_count"]
        for k, v in r["by_status"].items():
            by_status[k] = by_status.get(k, 0) + v
        for k, v in r["actual_totals"].items():
            totals[k] = totals.get(k, 0.0) + v
    ep = epic_file(state_root, epic_key)
    _, enode = load_node(ep) if ep else (None, None)
    return {
        "key": epic_key,
        "status": str((enode or {}).get("status", "unknown")),
        "sprint_count": len(sprints),
        "story_count": story_count,
        "by_status": by_status,
        "actual_totals": totals,
        "sprints": sprints,
    }


def _fmt_actuals(totals: dict) -> str:
    """Render an actuals dict in stable METRIC_FIELDS order."""
    return "  ".join(f"{m}={totals.get(m, 0)}" for m in METRIC_FIELDS)


# --------------------------------------------------------------------------- #
# subcommands
# --------------------------------------------------------------------------- #
def cmd_set_status(args) -> int:
    kind = _infer_kind(args)
    valid = {"story": VALID_STORY_STATUS, "sprint": VALID_SPRINT_STATUS, "epic": VALID_EPIC_STATUS}[kind]
    if args.status not in valid:
        _die_usage(f"invalid {kind} status '{args.status}' — expected one of {sorted(valid)}")

    y, node, path, label = _load_checked(args.state_root, args, kind)
    node["status"] = args.status
    node["updated_at"] = _now_iso()
    if args.title:
        node["title"] = args.title
    save_node(y, node, path, getattr(args, "flock", False))

    if args.ledger:
        scope = args.scope or (args.story or f"{args.epic}" + (f"/{args.sprint}" if args.sprint else ""))
        _append_ledger(args.ledger, scope, f"status -> {args.status}")
    sys.stdout.write(f"OK set-status {label} -> {args.status}\n")
    return 0


def cmd_set_actual(args) -> int:
    kind = args.node
    y, node, path, label = _load_checked(args.state_root, args, kind)

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

    save_node(y, node, path, getattr(args, "flock", False))
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

    # Calibration factors: applied to get from base values to the estimate
    _maybe_set(est, "fix_factor", getattr(args, "fix_factor", None), float)
    _maybe_set(est, "scope_ratio", getattr(args, "scope_ratio", None), float)

    # Confidence: explicit arg wins; else derive from completeness
    if args.confidence:
        est["confidence"] = args.confidence
    elif "confidence" not in est:
        range_keys = ["man_hours_low", "man_hours_high", "time_hours_low", "time_hours_high",
                      "tokens_k_min", "tokens_k_max", "cost_low", "cost_high"]
        story_keys = ["man_hours", "time_hours", "tokens_k", "cost"]
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


def cmd_progress(args) -> int:
    if not args.msg:
        _die_usage("progress needs --msg")
    _append_ledger(args.ledger, args.scope, args.msg)
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
        return 0

    r = rollup_epic(args.state_root, args.epic)
    sys.stdout.write(f"{r['key']}  status={r['status']}  sprints={r['sprint_count']}  "
                     f"stories={r['story_count']}\n")
    for sp in r["sprints"]:
        sys.stdout.write(f"  {sp['key']:<8} status={sp['status']:<12} stories={sp['story_count']}\n")
    sys.stdout.write(f"  actuals: {_fmt_actuals(r['actual_totals'])}\n")
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
    s.add_argument("--ledger")
    s.add_argument("--scope")
    s.add_argument("--flock", action="store_true", help="acquire exclusive flock before write")
    s.set_defaults(func=cmd_set_status)

    a = sub.add_parser("set-actual", help="write a validated actual block")
    a.add_argument("--state-root", required=True, help="path to {implementation_artifacts}/state")
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
    v.add_argument("--state-root", required=True, help="path to {implementation_artifacts}/state")
    v.add_argument("--scope", required=True, choices=["story", "sprint", "epic"])
    node_args(v)
    v.add_argument("--require-tokens", action="store_true")
    v.add_argument("--runtime", choices=["claude", "other"], default="other")
    v.set_defaults(func=cmd_verify)

    sh = sub.add_parser("show", help="render a computed sprint or epic roll-up")
    sh.add_argument("--state-root", required=True)
    sh.add_argument("--epic", required=True)
    sh.add_argument("--sprint", default="")
    sh.set_defaults(func=cmd_show)

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
    cal.add_argument("action", choices=["show"])
    cal.add_argument("--state-root", required=True)
    cal.add_argument("--format", choices=["text", "json"], default="text")
    cal.set_defaults(func=cmd_calibration)

    p.add_argument("--version", action="version", version=f"pm-status.py {PM_STATUS_VERSION}")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
