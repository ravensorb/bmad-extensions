"""pm_status.nodes -- the node layer: the ONLY place a node key becomes a path.

Sharded-layout resolution (`find_epic_dir`, `epic_file`/`sprint_file`/`story_file`,
`resolve_node_path`, `ensure_node_path`), the node load/save pair, the roll-up
enumerators, the node-field schemas `set-field` validates against, the story-document
skeleton, `_check_lock_verdict` and `deps_list`.

It sits directly above `core` and below everything else: the issue store, the metrics
layer, the status verbs and the plan operations all reach state through here. That
position is what breaks the cycle the original "state" bucket contained -- the status
verbs consume the issue store, and the issue store consumes this module, so the two
cannot be one bucket.

check:docs check 26 ("state paths are assembled only in pm-status.py's resolver
section") judges each authored file of the package by ITS OWN marker pair, and the pair
below is the package's only one -- it travelled here with the code it delimits. A file
carrying neither marker has its whole body judged, which is now the rule `__main__.py`
lives under: it assembles no state path at all, and must not start.

CALL STYLE ACROSS MODULES. `core._load` is reached through the MODULE OBJECT, because
the suite patches it (`patch.object(pm.core, "_load", ...)`) and a `from ..core import
_load` binding here would be a private copy the patch could never reach. The other core
names are imported by name -- none of them is a patch target.

THE SAME RULE APPLIES TO THIS MODULE'S OWN EXPORTS. `save_node` and `epic_file` are
mock.patch targets (`pm.nodes.save_node`, `pm.nodes.epic_file`), so `__main__.py` calls
them as `nodes.save_node(...)` / `nodes.epic_file(...)` and does NOT re-export them: a
`pm.save_node` binding left beside `pm.nodes.save_node` is a second thing to patch, and
the wrong one passes silently. Everything else here is re-exported into `__main__` by
name, because `pm_status.<name>` is `__main__`'s globals through the `__init__.py`
facade and the suite reads these directly. Promote a re-exported name to
module-qualified the moment the suite starts patching it.
"""
from __future__ import annotations

import contextlib
import io
import os
import re
import sys

from .. import core
from ..core import (
    DIR_FOR_STATUS,
    STATUS_DIRS,
    PMError,
    _atomic_create,
    _die_notfound,
    _die_usage,
    _flock_write_or_plain,
    _lock_age_minutes,
    _parse_iso,
    _yaml,
    epic_dirname,
    epic_node_lock,
    parse_story_key,
    sprint_dirname,
)


# --------------------------------------------------------------------------- #
# Sharded layout resolution — the ONLY place that knows where nodes live on disk
# --------------------------------------------------------------------------- #
def find_epic_dir(state_root: str, epic_key: str):
    """Absolute path to the epic's directory, whichever status folder holds it."""
    name = epic_dirname(epic_key)
    for status in STATUS_DIRS:
        p = os.path.join(state_root, status, name)
        if os.path.isdir(p):
            return p
    return None


def iter_epic_dirs(state_root: str):
    """Yield (bucket, epic_key, epic_dir_path) for every epic directory in the state tree.

    Missing state root yields nothing. Order: bucket in STATUS_DIRS order (active,
    planned, archived), key sorted within each bucket. Non-conforming entries
    (a directory that does not match epic-{nnn}, a regular file with that name) are
    skipped silently -- they are not this enumerator's concern.

    The one enumerator behind list-epics; also the enumerator a future caller uses to
    answer "does this epic exist and in which bucket?" without probing filesystem paths.
    """
    if not os.path.isdir(state_root):
        return
    for bucket in STATUS_DIRS:
        bucket_dir = os.path.join(state_root, bucket)
        if not os.path.isdir(bucket_dir):
            continue
        for name in sorted(os.listdir(bucket_dir)):
            if not name.startswith("epic-"):
                continue
            p = os.path.join(bucket_dir, name)
            if not os.path.isdir(p):
                continue
            suffix = name[len("epic-"):]
            if not (suffix.isdigit() and len(suffix) == 3):
                continue
            yield bucket, f"E{suffix}", p


def iter_story_files(state_root: str, epic_key: str, sprint_key=None):
    """Yield (story_key, story_file_path) for every story node file under an epic,
    optionally scoped to one sprint.

    A missing epic yields nothing (callers check find_epic_dir separately when they
    want to distinguish absent from empty). Files that are not stories -- sprint.yaml,
    epic.yaml, a .yaml.lock sidecar, anything whose name does not parse as
    E{nnn}-S{nn}-{nnn} -- are filtered out here so callers do not have to.
    """
    d = find_epic_dir(state_root, epic_key)
    if d is None:
        return
    target_sprint_dir = sprint_dirname(sprint_key) if sprint_key is not None else None
    for sd_path in list_sprint_dirs(state_root, epic_key):
        sd_name = os.path.basename(sd_path)
        if target_sprint_dir is not None and sd_name != target_sprint_dir:
            continue
        for name in sorted(os.listdir(sd_path)):
            if not name.endswith(".yaml"):
                continue
            story_key = name[:-len(".yaml")]
            try:
                parse_story_key(story_key)
            except ValueError:
                continue
            yield story_key, os.path.join(sd_path, name)


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
    return core._load(path)


def save_node(y, node, path: str, use_flock: bool = False) -> None:
    _flock_write_or_plain(use_flock, y, node, path)


def check_backrefs(node, epic_key: str, sprint_key: str | None = None) -> list:
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


def ensure_node_path(state_root: str, args, kind: str, status: str):
    """Resolve a node kind + keys to (path, label), CREATING the directory when absent.

    The counterpart to resolve_node_path() for the one case that function cannot serve:
    a node that does not exist yet. It is the ONLY function that creates a state
    directory, and it lives here -- in the section that is the only place a key becomes
    a location -- on purpose. A mkdir in a subcommand body is exactly how that invariant
    breaks; check 26 in check-docs.mjs fails the build if one appears.

    A NEW epic is placed by its status, per the placement rule. An epic that already has
    a directory is left where it is: relocating on a status change is move-epic's job,
    which uses `git mv` so history survives. Sprints and stories require their epic's
    directory to exist and exit 3 when it does not.
    """
    if kind == "epic" and status not in DIR_FOR_STATUS:
        _die_usage(
            f"cannot place a new epic with status {status!r} -- "
            f"expected one of {sorted(DIR_FOR_STATUS)}"
        )
    if kind == "epic":
        if not args.epic:
            _die_usage("--epic is required for an epic node")
        d = find_epic_dir(state_root, args.epic)
        if d is None:
            d = os.path.join(state_root, DIR_FOR_STATUS[status], epic_dirname(args.epic))
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "epic.yaml"), f"epic {args.epic}"

    if kind == "sprint":
        if not (args.epic and args.sprint):
            _die_usage("--epic and --sprint are required for a sprint node")
        d = find_epic_dir(state_root, args.epic)
        if d is None:
            _die_notfound(f"epic {args.epic} (create it before its sprints)")
        sd = os.path.join(d, sprint_dirname(args.sprint))
        os.makedirs(sd, exist_ok=True)
        return os.path.join(sd, "sprint.yaml"), f"epic {args.epic} sprint {args.sprint}"

    if kind == "story":
        if not args.story:
            _die_usage("--story is required for a story node")
        epic_key, sprint_key, _ = parse_story_key(args.story)
        d = find_epic_dir(state_root, epic_key)
        if d is None:
            _die_notfound(f"epic {epic_key} (create it before its stories)")
        sd = os.path.join(d, sprint_dirname(sprint_key))
        os.makedirs(sd, exist_ok=True)
        return os.path.join(sd, f"{args.story}.yaml"), f"story {args.story}"

    _die_usage(f"unknown node kind: {kind}")


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


def _epic_write_lock(args, kind, require_exists: bool = True):
    """epic_node_lock around a node verb's read-modify-write when the node is an epic; no
    lock for a sprint or story, whose files are not epic.yaml. Resolves the epic first, so
    an absent one exits 3 exactly as before with no lock file created; the verb resolves
    again inside the hold, since a move-epic may land while it waits.

    require_exists=False is for import-node, whose whole purpose is the node that does not
    exist yet. It still takes the lock -- a concurrent import of the same epic must
    serialise -- it just does not demand the node be there first. Every other caller keeps
    the default, so their behaviour is unchanged.
    """
    if kind != "epic":
        return contextlib.nullcontext()
    if require_exists:
        resolve_node_path(args.state_root, args, "epic")
    return epic_node_lock(args.state_root, args.epic)


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


# --------------------------------------------------------------------------- #
# Node-field schemas — what `set-field` coerces, and what it refuses outright
# --------------------------------------------------------------------------- #
# Node fields that are numeric or boolean regardless of how they arrive. `set-field`
# takes --value as text, so without this a numeric field lands on disk as a quoted
# string and every later reader has to guess. That is not hypothetical: writing
# fix_iterations through set-field stored '0', and the calibration path then depended
# on that string being int()-parseable. '0' happened to work; '0.0' raised ValueError
# and lost the sample entirely, and an unsubstituted '{fix_iterations}' placeholder --
# or any other non-numeric text -- silently became provenance=backout on a story that
# needed no rework at all.
NUMERIC_NODE_FIELDS = {
    "completion_evidence.fix_iterations",
    "completion_evidence.files_changed",
}
BOOL_NODE_FIELDS = {"completion_evidence.tests_passing"}

# Fields set-field must refuse outright: each is derived from other recorded data
# rather than asserted by an agent. completion_evidence.tests_passing used to be a
# free-form boolean an agent wrote about its own work -- not falsifiable, and not
# even checked against anything it ran. A story once shipped ten green gates and
# tests_passing: true having broken a suite it never ran; the break surfaced two
# stories later by accident. add-test-run records the command and exit code instead,
# and derives the boolean from that recorded set.
DERIVED_NODE_FIELDS = {
    "completion_evidence.tests_passing":
        "derived from completion_evidence.test_runs — record what you ran with "
        "`add-test-run --command CMD --exit-code N` instead of asserting the result",
    "resolves":
        "written by `promote-issue`, which also schedules the items it names -- a hand "
        "write would link a story the backlog does not know about",
    "status":
        "status changes go through `set-status`, which records the transition event and "
        "runs the done hook that resolves a story's backlog items",
}


# --------------------------------------------------------------------------- #
# Story documents — the artifact-tree mirror of a story node, and its skeleton
# --------------------------------------------------------------------------- #
def story_doc_path(artifacts_root: str, story_key: str) -> str:
    """E{nnn}-S{nn}-{nnn} -> {artifacts}/epic-{nnn}/sprint-{nn}/stories/{key}.md

    The artifact tree mirrors the state tree with an identical path suffix but is
    NOT the state tree: artifacts are human-authored and never moved between
    status directories. This is the only place that resolves a story key to a
    document path, for the same reason story_file() is the only place that
    resolves one to a state path.
    """
    m = re.match(r"^E(\d{3})-S(\d{2})-\d{3}$", story_key)
    if not m:
        raise ValueError(f"not a story key: {story_key!r}")
    return os.path.join(artifacts_root, f"epic-{m.group(1)}",
                        f"sprint-{m.group(2)}", "stories", f"{story_key}.md")


def init_story_doc(state_root, artifacts_root, story_key, context_md="", ac_lines=None,
                   must_not_exist=False) -> str:
    """Create a story document's skeleton from its state node -- the only writer of
    that skeleton (story prep and promote-issue both call it). Returns 'created' or
    'exists'. Raises PMError: 2 for a bad key or, under must_not_exist, an existing
    document; 3 for a missing state node."""
    from ruamel.yaml.comments import CommentedMap
    from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQ
    try:
        doc = story_doc_path(artifacts_root, story_key)
    except ValueError as e:
        raise PMError(2, str(e))
    path = story_file(state_root, story_key)
    if path is None:
        raise PMError(3, f"story {story_key}")
    _, node = load_node(path)
    if node is None:
        raise PMError(3, f"story {story_key} — file is empty")
    title = str(node.get("title") or story_key)
    meta = CommentedMap()
    meta["key"] = SQ(story_key)
    meta["title"] = SQ(title)
    meta["status"] = str(node.get("status") or "backlog")
    meta["classification"] = str(node.get("classification") or "standard")
    buf = io.StringIO()
    _yaml().dump(meta, buf)
    parts = ["---\n", buf.getvalue(), "---\n\n", f"# {title}\n\n"]
    if context_md:
        parts.append(context_md.rstrip("\n") + "\n\n")
    parts.append("## Acceptance Criteria\n\n")
    if ac_lines:
        parts.extend(f"- {line}\n" for line in ac_lines)
    else:
        parts.append("<!-- Technical ACs to be added below -->\n")
    if not _atomic_create(doc, "".join(parts)):
        if must_not_exist:
            raise PMError(2, f"story document {doc} already exists -- refusing to adopt it")
        return "exists"
    return "created"


# --------------------------------------------------------------------------- #
# Lock verdict and dependency list — read helpers over an already-loaded node
# --------------------------------------------------------------------------- #
def _check_lock_verdict(lock, session_id) -> tuple:
    """check-lock's verdict on a PRESENT `_lock` value, as (exit, line): 0 when the epic
    is free to claim, 5 when another session holds it within its TTL.

    Extracted verbatim from cmd_check_lock -- same lines, same order of evaluation, and
    the same ValueError on a non-integer ttl_minutes. promote-issue (`_foreign_lock_error`)
    takes this verdict only for a lock it can evaluate (`_unevaluable_lock_reason`), so the
    two agree on every well-formed lock: e.g. `ttl_minutes: 0` is always stale to both,
    where promote used to read it as 30. A lock this verdict calls unreadable is FREE to
    check-lock, a read, but refused by both write verbs, set-lock and promote (Ruling 24).
    cmd_set_lock is deliberately NOT routed through here: it parses the TTL only after the
    timestamp, so sharing would change one of the two verbs."""
    if not isinstance(lock, dict):
        return 0, "FREE (unreadable lock — not a mapping — treating as stale)"
    holder = str(lock.get("session_id", ""))
    if holder == session_id:
        return 0, "FREE (own session)"
    claimed_str = str(lock.get("claimed_at", ""))
    ttl = int(lock.get("ttl_minutes", 30))
    claimed = _parse_iso(claimed_str)
    if claimed is None:
        return 0, "FREE (unreadable lock timestamp — treating as stale)"
    age_minutes = _lock_age_minutes(claimed)
    if age_minutes > ttl:
        return 0, f"FREE (stale lock from {holder}, age={age_minutes:.1f}m > ttl={ttl}m)"
    return 5, f"LOCKED by {holder} (claimed {claimed_str}, ttl={ttl}m)"


def deps_list(node, path) -> list:
    """A node's `depends_on` as a list, refusing (PMError 2) anything else.

    A scalar is not a near-miss, it is an erasure: `depends_on: 'E001'` iterates as
    CHARACTERS, so consumers see `["E", "0", "0", "1"]` and plan-graph's `if d in epics`
    filter drops every one. The epic then reads as having NO dependencies, its phase is
    marked `parallel: true`, and two epics declared sequential are dispatched concurrently
    into one working tree. Phantom dependencies would fail on the first lookup; an empty
    list is indistinguishable from a correct independent epic, so this must refuse.

    Refusing, not coercing: a scalar may have been meant as a one-element list or as a
    string of keys, and promoting it picks one without evidence.
    """
    dep = node.get("depends_on")
    if dep is None or isinstance(dep, list):
        return list(dep or [])
    shown = repr(dep)
    hint = f"[{dep!r}]" if isinstance(dep, str) else "[...]"
    raise PMError(2, f"{path}: depends_on is {type(dep).__name__} ({shown}), not a list -- "
                     f"write it as {hint}. A non-list is read character by character by "
                     f"every consumer, which silently DROPS the dependency and lets the "
                     f"planner run these epics concurrently; fix the file by hand")
