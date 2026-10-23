"""pm_status.plan -- the plan operations: moving, re-keying, dumping and retiring nodes,
and the reorg journal.

`move-epic`, `reparent-story`, `dump-plan`, `retire-epic`, and the `/l3io-plan reorg`
journal with its undo (`reorg-log`, `reorg-undo`). It is the top of the library stack: it
consumes `core`, `nodes` and the issue store, and nothing below imports it; only
`__main__.py` (the parser and `main`) reaches these functions.

CALL STYLE ACROSS MODULES. Every name the suite patches is reached through its MODULE
OBJECT -- `core._load`, `core._atomic_dump`, `core._atomic_text_write`, `nodes.save_node`,
`nodes.epic_file` -- never `from ..core import _load`, which would be a private copy a
`mock.patch` on `core` could not reach. None of them is re-exported here or by
`__main__.py`. Names nothing patches are imported by name. `IssueStore` is imported by
name: the suite patches a CLASS ATTRIBUTE on it, which mutates the one class object every
binding names.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import sys

from .. import core, nodes
from ..core import (
    STATUS_DIRS,
    STATUS_FOR_DIR,
    PMError,
    _die_notfound,
    _die_usage,
    _file_lock,
    _now_iso,
    _run_core,
    _yaml,
    canonical_epic_key,
    canonical_sprint_key,
    epic_dirname,
    epic_node_lock,
    issues_lock,
    parse_story_key,
    sprint_dirname,
)
from ..issues.promote import _next_story_key, _walk_story_nodes
from ..issues.store import STORY_REF_FIELDS, IssueStore, issues_paths
from ..nodes import (
    deps_list,
    find_epic_dir,
    iter_epic_dirs,
    load_node,
    sprint_file,
    story_file,
)


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

    The move and the epic.yaml status write run under the epic's epic_node_lock. Its lock
    file lives outside the directory being moved (epic_lock_path), so the move cannot carry
    it away from a waiter; every waiter resolves the epic again once it holds the lock, and
    so finds the moved directory. Two movers serialize the same way.
    """
    if to_status not in STATUS_DIRS:
        raise ValueError(f"bad status folder {to_status!r} — expected one of {list(STATUS_DIRS)}")
    state_root = os.path.abspath(state_root)
    if find_epic_dir(state_root, epic_key) is None:          # before any lock file exists
        raise FileNotFoundError(f"epic {epic_key} not found under {state_root}")
    with epic_node_lock(state_root, epic_key):
        return _move_epic_locked(state_root, epic_key, to_status)


def _move_epic_locked(state_root: str, epic_key: str, to_status: str) -> str:
    """move_epic's body; the caller holds the epic's lock and passes an absolute root."""
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
                           capture_output=True, check=False, text=True)
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
            nodes.save_node(y, node, p)
    return dest


def _story_doc_on_disk(artifacts_root: str, story_key: str):
    """The story's document path, whatever its filename shape, or None.

    `story_doc_path` only ever GENERATES the unslugged name, but the documented artifact
    shape allows an optional trailing slug (`E032-S01-001-centralized-file-config.md`). A
    re-parent must find and move whichever shape is actually there, and must preserve the
    slug across the rename -- the key prefix is canonical, the slug is UX.
    """
    try:
        epic_key, sprint_key, _ = parse_story_key(story_key)
    except ValueError:
        return None
    d = os.path.join(artifacts_root, epic_dirname(epic_key), sprint_dirname(sprint_key),
                     "stories")
    if not os.path.isdir(d):
        return None
    for name in sorted(os.listdir(d)):
        if not name.endswith(".md"):
            continue
        # Exactly the key, or the key followed by a slug separator. `startswith(story_key)`
        # alone would also match a longer key sharing this one's prefix, which cannot happen
        # with fixed-width keys today but costs nothing to exclude.
        if name == f"{story_key}.md" or name.startswith(f"{story_key}-"):
            return os.path.join(d, name)
    return None


def _doc_slug(path: str, story_key: str) -> str:
    """The `-slug` part of a story document filename, or '' -- preserved across a re-parent."""
    base = os.path.basename(path)
    stem = base.removesuffix(".md")
    return stem[len(story_key):] if stem.startswith(story_key) else ""


def _rewrite_references(state_root: str, old_key: str, new_key: str) -> None:
    """Repoint every reference to `old_key` at `new_key`.

    A re-key invalidates references the moving node does not own, and they are the half of
    this operation most likely to rot silently: a `depends_on` naming a key that no longer
    exists does not fail until something tries to order it, and a backlog `ref` pointing at
    a vanished story reads as an unlinked promotion in `audit-issues` rather than as damage
    this operation did.

    Two kinds: `depends_on` lists on story nodes, and the two story-key fields on backlog
    items -- `ref` (what fixed it) and `story` (what it is scheduled to) -- in BOTH issue
    files. Both fields in both files, because a resolved entry carries `story` as well
    (`resolve_issue_core` copies every field of the open item), and a `story` left on the
    old key reads as audit finding 1b, whose repair discards the scheduling rather than
    restoring it.
    """
    for _k, _sdir, node, path in _walk_story_nodes(state_root):
        # deps_list, not an isinstance guard: a guard would skip a malformed `depends_on`
        # silently, leaving the stale key behind. reparent_story pre-flights the same check
        # before its first write, so this cannot raise mid-move.
        if old_key in deps_list(node, path):
            y, n = load_node(path)
            n["depends_on"] = [new_key if v == old_key else v for v in deps_list(n, path)]
            nodes.save_node(y, n, path)

    # Either file, not just the open one: a project whose every issue is closed still has
    # resolved refs to repoint. cmd_audit_issues takes no lock when neither exists because
    # it is read-only; this is a write path, so creating the lock file is correct.
    open_path, res_path = issues_paths(state_root)
    if os.path.exists(open_path) or os.path.exists(res_path):
        with issues_lock(open_path):
            store = IssueStore(open_path)
            hit = False
            for lst in (store.backlog, store.resolved):
                for item in lst:
                    if not isinstance(item, dict):
                        continue
                    for field in STORY_REF_FIELDS:
                        if item.get(field) == old_key:
                            item[field] = new_key
                            hit = True
            if hit:
                store.save_open()
                store.save_resolved()


def _raise_sprint_high_water(state_root: str, epic_key: str, sprint_key: str,
                             at_least: int) -> None:
    """Raise a sprint's story-key high-water, so a departing key is never reissued.

    WHY THIS IS NEEDED ON TOP OF THE ALLOCATOR. `_next_story_key`'s high-water only protects
    keys it ISSUED. Every story that exists today predates it, so its sprint carries no
    `next:` at all -- and once such a story moves away, nothing on disk or in the node
    remembers its number and the floor drops back. The departure is the moment we learn the
    key was in use, so that is where it gets recorded.

    Monotonic by construction: it only ever raises. The caller holds the sprint's epic lock,
    because a lost update here WOULD matter -- two concurrent departures raising to 5 and 7
    could leave 5, and 6 would then be reissued to different work.
    """
    spath = sprint_file(state_root, epic_key, sprint_key)
    if spath is None:
        return                                   # no sprint node to record it on
    y, node = load_node(spath)
    if not isinstance(node, dict):
        return
    try:
        stored = int(node.get("next") or 0)
    except (TypeError, ValueError):
        stored = 0
    if stored >= at_least:
        return
    node["next"] = at_least
    nodes.save_node(y, node, spath)


def reparent_story(state_root: str, artifacts_root: str, story_key: str,
                   to_epic: str, to_sprint: str) -> str:
    """Move one planned story to another sprint, re-keying it. Returns the new key.

    BOTH TREES MOVE TOGETHER. The state node and the story document are siblings with an
    identical path suffix, and a re-parent that moved one without the other would break the
    mirror the whole layout depends on. The document may not exist yet (a story planned but
    not elaborated), which is fine; what is not fine is moving one of two that both exist.

    GATE BEFORE WRITE. Everything that can refuse -- scope, existence, destination, key
    availability -- is checked before the first byte moves. `migrate-engine.py` runs its
    completeness checks after the write once, and an empty parse passed vacuously and then
    deleted the source; this orders it the other way for the same reason.

    PLANNED WORK ONLY. A story under `active/` or `archived/` carries actuals, calibration
    samples and `events.jsonl` history keyed to its current key, none of which this moves.
    Refusing is the scope rule, not a limitation to work around.
    """
    state_root = os.path.abspath(state_root)
    artifacts_root = os.path.abspath(artifacts_root)
    from_epic, from_sprint, _ = parse_story_key(story_key)
    to_epic = canonical_epic_key(to_epic)
    to_sprint = canonical_sprint_key(to_sprint)

    # TWO LOCKS, SEQUENTIALLY, NEVER NESTED. `epic_node_lock` refuses to hold two epics at
    # once and that guard is right: its re-entrancy counter is per lock FAMILY rather than per
    # epic, so a nested acquire would silently skip the second flock and hand back the illusion
    # of a lock. Taking them one after the other respects it and needs nothing widened.
    #
    # Phase 1 records the departing key in the SOURCE sprint's high-water. Between the phases
    # another process can only read a source whose high-water is already raised, or race the
    # same move and fail on a missing source -- both safe.
    src_probe = story_file(state_root, from_epic + "-" + from_sprint + "-" + story_key[-3:])
    if src_probe is not None and os.sep + "planned" + os.sep in src_probe + os.sep:
        with epic_node_lock(state_root, from_epic):
            _raise_sprint_high_water(state_root, from_epic, from_sprint,
                                     int(story_key[-3:]) + 1)

    # THE DESTINATION EPIC'S LOCK FOR THE REST.
    #
    # `epic_node_lock` refuses to hold two epics at once, rightly: its re-entrancy counter is
    # per lock FAMILY, so a nested acquire of a second epic would silently skip its flock. The
    # answer is to need less of it. What this operation read-modify-writes is the DESTINATION
    # sprint's allocator; the source epic's `epic.yaml` is untouched and its sprint's `next` is
    # a never-decreasing high-water, and `_require_epic_lock` guards `epic.yaml` writes, of
    # which a re-parent makes none. The source side needs no lock because the move is a single
    # rename: a concurrent second re-parent finds the source gone and fails cleanly.
    with epic_node_lock(state_root, to_epic):
        # --- GATE -------------------------------------------------------------------
        src_node = story_file(state_root, story_key)
        if src_node is None:
            raise PMError(3, f"story {story_key} not found under {state_root}")
        if os.sep + "planned" + os.sep not in src_node + os.sep:
            raise PMError(2, f"{story_key} is not in planned/ — reorg writes planned work "
                             f"only; its actuals, calibration samples and events.jsonl "
                             f"history are keyed to its current key and are not moved")
        dest_sprint_node = sprint_file(state_root, to_epic, to_sprint)
        if dest_sprint_node is None:
            raise PMError(3, f"destination sprint {to_epic}-{to_sprint} does not exist — "
                             f"create it before moving work into it")
        # BOTH ENDS MUST BE PLANNED, not just the source. `sprint_file` resolves through
        # `find_epic_dir`, which searches every bucket, so without this a planned story
        # could be moved INTO an active or archived epic -- past the placement rule, which
        # says an epic's directory lives in the folder named for its status and its stories
        # travel with it. The story would then sit in `archived/` while still reading
        # `status: backlog`, and the next `move-epic` would carry it somewhere nobody chose.
        if os.sep + "planned" + os.sep not in dest_sprint_node + os.sep:
            raise PMError(2, f"destination {to_epic}-{to_sprint} is not in planned/ — reorg "
                             f"writes planned work only, at both ends of a move")
        if (from_epic, from_sprint) == (to_epic, to_sprint):
            return story_key                      # already there; a no-op, not an error

        new_key = _next_story_key(state_root, artifacts_root, to_epic, to_sprint)
        dest_node = os.path.join(os.path.dirname(dest_sprint_node), f"{new_key}.yaml")
        if os.path.exists(dest_node):
            raise PMError(2, f"allocator handed out {new_key} but {dest_node} exists")

        src_doc = _story_doc_on_disk(artifacts_root, story_key)
        dest_doc = None
        if src_doc is not None:
            slug = _doc_slug(src_doc, story_key)
            dest_doc = os.path.join(artifacts_root, epic_dirname(to_epic),
                                    sprint_dirname(to_sprint), "stories",
                                    f"{new_key}{slug}.md")
            if os.path.exists(dest_doc):
                raise PMError(2, f"destination document already exists: {dest_doc}")

        # Every node `_rewrite_references` will read, validated before the first move: it
        # runs after the node and document have been renamed, so a refusal raised there
        # would leave the move half-applied.
        for _k, _sd, _n, _p in _walk_story_nodes(state_root):
            deps_list(_n, _p)

        # --- WRITE ------------------------------------------------------------------
        _git_or_plain_move(src_node, dest_node, state_root)
        if src_doc is not None:
            os.makedirs(os.path.dirname(dest_doc), exist_ok=True)
            _git_or_plain_move(src_doc, dest_doc, artifacts_root)

        from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQ
        y, node = load_node(dest_node)
        if not isinstance(node, dict):
            raise PMError(2, f"{dest_node} did not parse after the move")
        node["key"] = SQ(new_key)
        node["epic"] = SQ(to_epic)
        node["sprint"] = SQ(to_sprint)
        prev = node.get("previous_keys")
        if not isinstance(prev, list):
            prev = []
        prev.append(story_key)                     # ordered, oldest first; never replaced
        node["previous_keys"] = prev
        node["updated_at"] = _now_iso()
        nodes.save_node(y, node, dest_node)

        if dest_doc is not None:
            _rewrite_doc_key(dest_doc, story_key, new_key)

        _rewrite_references(state_root, story_key, new_key)

        # --- VERIFY -----------------------------------------------------------------
        if story_file(state_root, story_key) is not None:
            raise PMError(2, f"{story_key} still resolves after the move")
        if story_file(state_root, new_key) is None:
            raise PMError(2, f"{new_key} does not resolve after the move")
        return new_key


def _rewrite_doc_key(path: str, old_key: str, new_key: str) -> None:
    """Repoint the story document's frontmatter `key:` at the new key.

    Touches that one field and nothing else: the document is human-authored and everything
    below the frontmatter belongs to its author.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError):
        return                                    # a doc we cannot read is not ours to fix
    out = re.sub(rf"^(key:\s*['\"]?){re.escape(old_key)}(['\"]?\s*)$",
                 rf"\g<1>{new_key}\g<2>", text, count=1, flags=re.MULTILINE)
    if out != text:
        core._atomic_text_write(path, out)


def _git_or_plain_move(src: str, dest: str, cwd: str) -> None:
    """`git mv`, falling back to a filesystem move with a LOUD warning.

    Same contract as move_epic's: preserving history is why this moves files rather than
    rewriting them, so a silent degradation to delete+add would defeat the point.
    """
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    moved = False
    reason = "git mv was not attempted"
    try:
        import subprocess
        r = subprocess.run(["git", "mv", os.path.abspath(src), os.path.abspath(dest)],
                           cwd=os.path.abspath(cwd), capture_output=True, check=False,
                           text=True)
        moved = r.returncode == 0
        if not moved:
            reason = (r.stderr.strip() or r.stdout.strip()
                      or f"git mv exited {r.returncode}").replace("\n", " ")
    except (OSError, ImportError) as e:
        reason = f"could not run git: {e}"
    if not moved:
        import shutil
        sys.stderr.write(
            f"pm-status.py: WARNING — `git mv` failed ({reason}); falling back to a plain "
            f"move of {src} -> {dest}. Git will see this as delete+add, not a rename, so "
            f"`git log --follow` will not cross it.\n")
        shutil.move(src, dest)


def dump_plan(state_root: str) -> dict:
    """The planned tree plus its read-only context, as one JSON-able structure.

    WHY THIS VERB EXISTS. The reorg analyzer lives in `l3io-plan`'s own `scripts/` (ADR-0001:
    single-consumer code lives in its skill), and check 26 forbids any file under `skills/`
    from assembling a state path -- `pm-status.py` is the only place that resolves a key to a
    location. So the analyzer cannot walk the tree; it asks for it. One read verb is the whole
    interface between the resolver and every consumer that wants the shape of a plan.

    WHAT IS AND IS NOT INCLUDED. `planned` carries the writable set, with the fields an
    analyzer reasons over: `depends_on`, `estimate`, `classification` and `previous_keys`
    (the last for `l3io-sync`, which needs it to distinguish re-keyed from deleted).
    `active` carries
    only KEYS and their dependencies -- enough to constrain ordering, nothing more, because
    active work is read-only input and a consumer that could see its estimates would be
    tempted to re-plan it. Archived work appears only as keys, for dependency satisfaction.

    Read-only: takes no lock and writes nothing.
    """
    out = {"planned": [], "active": [], "archived": []}
    for bucket, epic_key, epic_dir in iter_epic_dirs(state_root):
        epath = os.path.join(epic_dir, "epic.yaml")
        enode = {}
        if os.path.exists(epath):
            _, n = load_node(epath)
            if isinstance(n, dict):
                enode = n
        if bucket != "planned":
            out[bucket].append({
                "key": epic_key,
                "status": str(enode.get("status") or ""),
                "depends_on": [str(v) for v in deps_list(enode, epath)],
            })
            continue

        epic = {
            "key": epic_key,
            "status": str(enode.get("status") or ""),
            "depends_on": [str(v) for v in deps_list(enode, epath)],
            # Absent when lanes are not in use, which is the normal single-developer state.
            # Consumers cannot read state directly (check 26), so this is the only way the
            # partition reaches plan-graph.py.
            "lane": str(enode["lane"]) if enode.get("lane") is not None else None,
            "estimate": _plain(enode.get("estimate")),
            "sprints": [],
        }
        for sname in sorted(os.listdir(epic_dir)):
            sdir = os.path.join(epic_dir, sname)
            spath = os.path.join(sdir, "sprint.yaml")
            if not os.path.isdir(sdir) or not os.path.exists(spath):
                continue
            _, sn = load_node(spath)
            sn = sn if isinstance(sn, dict) else {}
            sprint = {
                "key": str(sn.get("key") or ""),
                "status": str(sn.get("status") or ""),
                "estimate": _plain(sn.get("estimate")),
                "stories": [],
            }
            for fname in sorted(os.listdir(sdir)):
                if fname == "sprint.yaml" or not fname.endswith(".yaml"):
                    continue
                stpath = os.path.join(sdir, fname)
                _, st = load_node(stpath)
                if not isinstance(st, dict):
                    continue
                sprint["stories"].append({
                    "key": str(st.get("key") or ""),
                    "status": str(st.get("status") or ""),
                    "classification": str(st.get("classification") or ""),
                    # stpath, not spath: a refusal must name the file that holds the defect,
                    # and the sprint.yaml beside it is not where anyone would look.
                    "depends_on": [str(v) for v in deps_list(st, stpath)],
                    # The whole chain, oldest first. `l3io-sync` reads this to tell a
                    # RE-KEYED story from a DELETED one: without it a reorg produces a
                    # `missing_local` for the old key AND an `unmapped_local` for the new,
                    # which pushes as a duplicate issue plus an orphaned one.
                    "previous_keys": [str(v) for v in (st.get("previous_keys") or [])],
                    "estimate": _plain(st.get("estimate")),
                })
            epic["sprints"].append(sprint)
        out["planned"].append(epic)
    return out


def _plain(v):
    """ruamel's CommentedMap/Seq -> plain dict/list/scalar, so json.dumps can take it."""
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_plain(x) for x in v]
    return v


def cmd_dump_plan(args) -> int:
    # COMPACT, and `--pretty` when a human is reading it.
    #
    # Every consumer of this is a script that parses it — the reorg analyzer, the validator,
    # the derivation, and the two plan-run advisories — and it is piped on every plan run.
    # `indent=2` measured 16,895 B against 8,349 B compact on the same 10-epic/40-story tree:
    # 2.09x the raw YAML it came from, versus 1.03x. Same data, half the bytes, and the only
    # thing lost is readability for a person running it by hand, which `--pretty` restores.
    pretty = bool(getattr(args, "pretty", False))
    sep = None if pretty else (",", ":")

    # Through _run_core: dump_plan refuses a malformed `depends_on` (deps_list). Every
    # consumer is a script reading stdout, so a refusal has to be exit 2 with stdout empty
    # -- parseable -- rather than a traceback.
    def run():
        sys.stdout.write(json.dumps(dump_plan(args.state_root),
                                    indent=2 if pretty else None, separators=sep) + "\n")
        return 0
    return _run_core(run)


def retire_epic(state_root: str, epic_key: str, reason: str) -> str:
    """Retire an epic: move it to `archived/` and record why. Returns the destination.

    RETIREMENT IS EPIC-LEVEL, and that is the layout's doing rather than a simplification.
    `planned/`, `active/` and `archived/` are folders of EPIC directories; sprints and stories
    live inside one and have nowhere else to be. There is no place to put a single retired
    story, so there is no verb for it.

    A THIN WRAPPER OVER `move_epic`, deliberately. The move itself -- git mv, the lock, the
    status write -- is already correct there and must not be reimplemented; this adds only the
    two fields that distinguish "retired by a reorg, for this reason" from "archived because it
    finished". Without them an undo could restore the directory but not the fact that a human
    was told why it went.

    NEVER DELETES. The spec is explicit: retire moves, and only an explicit request deletes.
    """
    if not str(reason or "").strip():
        raise PMError(2, "retire-epic requires a --reason: an epic retired without one leaves "
                         "nobody able to judge later whether it should come back")
    dest = move_epic(state_root, epic_key, "archived")
    with epic_node_lock(state_root, epic_key):
        p = os.path.join(dest, "epic.yaml")
        if os.path.exists(p):
            from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQ
            y, node = load_node(p)
            if isinstance(node, dict):
                node["retired_reason"] = SQ(str(reason).strip())
                node["retired_at"] = SQ(_now_iso())
                nodes.save_node(y, node, p)
    return dest


def cmd_retire_epic(args) -> int:
    try:
        dest = retire_epic(args.state_root, args.epic, args.reason)
    except PMError:
        raise
    except FileNotFoundError as e:
        _die_notfound(str(e))
    except (ValueError, FileExistsError) as e:
        _die_usage(str(e))
    sys.stdout.write(f"OK retire-epic {args.epic} -> {dest}\n")
    return 0


def cmd_reparent_story(args) -> int:
    # Through _run_core, like every other verb: main() has no PMError handler, so a
    # re-raise here would reach the caller as a traceback and exit 1 rather than one stderr
    # line and exit 2. This verb's refusals are usage errors and must read as such.
    def run():
        try:
            new_key = reparent_story(args.state_root, args.artifacts_root, args.story,
                                     args.to_epic, args.to_sprint)
        except FileNotFoundError as e:
            _die_notfound(str(e))
        except (ValueError, FileExistsError) as e:
            _die_usage(str(e))
        sys.stdout.write(f"OK reparent-story {args.story} -> {new_key}\n")
        return 0
    return _run_core(run)


# --------------------------------------------------------------------------------------
# The reorg journal: what was done, why, and enough to put it back.
# --------------------------------------------------------------------------------------

REORG_LOG_FILENAME = "reorg-log.yaml"
_REORG_OP_FIELDS = {
    "reparent-story": {"story", "new_key", "from_epic", "from_sprint",
                       "to_epic", "to_sprint"},
    "retire-epic": {"epic", "reason", "from_status"},
    "create-sprint": {"epic", "sprint"},
}


def reorg_log_path(state_root: str) -> str:
    return os.path.join(state_root, REORG_LOG_FILENAME)


_REORG_LOG_LOCK = {"depth": 0, "fh": None}


@contextlib.contextmanager
def reorg_log_lock(state_root: str):
    """Exclusive lock over a whole reorg-log read-modify-write cycle.

    Same reasoning as issues_lock: allocate an id -> append -> save is not atomic, and the
    log is a single shared append target. The log file itself is COMMITTED -- it is the
    traceback record a human reads months later -- so only its `.lock` sidecar is ignored,
    which `_ensure_lock_ignore`'s existing `*.lock` rule already covers.

    NEVER HELD ACROSS A MOVE. `reparent_story` and `move_epic` take `epic_node_lock`, and
    the enforced order is epic-lock-first. `reorg-undo` therefore takes this lock to claim
    an entry, RELEASES it, performs the moves, and takes it again to record the result.
    """
    with _file_lock(reorg_log_path(state_root) + ".lock", _REORG_LOG_LOCK, state_root):
        yield


def plan_shape_hash(state_root: str) -> str:
    """A digest of WHERE planned work sits -- epic, sprint and story placement, nothing else.

    THE GUARD UNDO RESTS ON. An undo computed against a tree that has moved on since the
    reorg would put stories somewhere neither the user nor the journal intended: it replays
    placements derived from a plan that no longer exists. Comparing this digest before acting
    turns that from a silent wrong answer into a refusal.

    PLACEMENT ONLY, DELIBERATELY. Estimates, titles, statuses and dependencies are excluded
    because an undo moves nodes and nothing else -- re-estimating a story between the reorg
    and the undo is ordinary work, and refusing over it would make the guard fire constantly
    for a change it does not care about. Adding or removing a story DOES change placement,
    and that is exactly the case the guard must catch.
    """
    plan = dump_plan(state_root)
    rows = []
    for e in plan.get("planned", []):
        rows.append(f"E\t{e['key']}")
        for sp in e.get("sprints", []):
            rows.append(f"S\t{e['key']}\t{sp['key']}")
            for st in sp.get("stories", []):
                rows.append(f"T\t{e['key']}\t{sp['key']}\t{st['key']}")
    body = "\n".join(sorted(rows))
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def _load_reorg_log(state_root: str):
    y, node = core._load(reorg_log_path(state_root))
    if not isinstance(node, dict):
        node = {"version": 1, "next": 1, "entries": []}
    node.setdefault("version", 1)
    node.setdefault("next", 1)
    if not isinstance(node.get("entries"), list):
        node["entries"] = []
    return y, node


def _validate_reorg_record(rec) -> list:
    """Every reason to refuse a record. Empty means accept.

    AN OP WE CANNOT INVERT MUST NOT BE JOURNALED. The log's only purpose is to make an undo
    possible, so recording an operation of a kind undo does not understand would hand a user
    an entry that looks undoable and is not. Unknown kinds and missing fields are refusals.
    """
    errs = []
    if not isinstance(rec, dict):
        return ["the record must be a mapping with `rationale`, `pre_hash` and `operations`"]
    if not str(rec.get("rationale") or "").strip():
        errs.append("`rationale` is required and must be the proposal the user accepted, "
                    "verbatim — an entry nobody can read is not a traceback record")
    if not str(rec.get("pre_hash") or "").strip():
        errs.append("`pre_hash` is required — capture it with `reorg-log --hash` BEFORE "
                    "applying the first operation")
    ops = rec.get("operations")
    if not isinstance(ops, list) or not ops:
        errs.append("`operations` must be a non-empty list")
        return errs
    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            errs.append(f"operations[{i}]: each operation must be a mapping")
            continue
        kind = str(op.get("op") or "")
        if kind not in _REORG_OP_FIELDS:
            errs.append(f"operations[{i}]: unknown op {kind!r} — undo would not know how to "
                        f"invert it, so journaling it would promise an undo that cannot run")
            continue
        missing = _REORG_OP_FIELDS[kind] - set(op)
        if missing:
            errs.append(f"operations[{i}] ({kind}): missing {sorted(missing)}")
    return errs


def record_reorg(state_root: str, rec: dict) -> str:
    """Append one reorg to the journal. Returns the new entry id."""
    errs = _validate_reorg_record(rec)
    if errs:
        raise PMError(2, "refusing this reorg record:\n  " + "\n  ".join(errs))
    from ruamel.yaml.scalarstring import LiteralScalarString as LS
    from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQ
    post = plan_shape_hash(state_root)
    # A block scalar, not an escaped one-liner. The rationale is the proposal a human reads
    # months later to decide whether to undo; `"...\n...\n"` is technically the same text and
    # unreadable in the file it lives in. Block style needs every line to end in one.
    rationale = str(rec["rationale"])
    if "\n" in rationale:
        rationale = LS(rationale if rationale.endswith("\n") else rationale + "\n")
    with reorg_log_lock(state_root):
        y, log = _load_reorg_log(state_root)
        try:
            n = int(log.get("next") or 1)
        except (TypeError, ValueError):
            n = 1
        n = max(n, 1)
        entry_id = f"R{n:04d}"
        log["next"] = n + 1
        log["entries"].append({
            "id": SQ(entry_id),
            "at": SQ(_now_iso()),
            "rationale": rationale,
            "pre_hash": SQ(str(rec["pre_hash"])),
            "post_hash": SQ(post),
            "operations": _plain(rec["operations"]),
        })
        core._atomic_dump(y, log, reorg_log_path(state_root))
    return entry_id


def _find_entry(log: dict, entry_id: str):
    for e in log.get("entries", []):
        if isinstance(e, dict) and str(e.get("id")) == entry_id:
            return e
    return None


def undo_reorg(state_root: str, artifacts_root: str, entry_id: str,
               check_only: bool = False) -> dict:
    """Put a recorded reorg back. Returns a result mapping.

    UNDO IS THE FORWARD PATH RUN BACKWARDS, not a special restore. Each operation is inverted
    with the same `reparent_story` / `move_epic` primitives that applied it, so an undo takes
    the same locks, the same gates and the same git-mv handling. A bespoke restore path would
    be a second implementation of the riskiest code in the file, exercised only in the rare
    case nobody tests by hand.

    REVERSE ORDER, for the same reason the forward order exists: a story that left a retiring
    epic has to come back AFTER that epic is un-archived, or it has nowhere to land.

    KEYS ARE NOT RESTORED, AND CANNOT BE. The allocator's high-water never decreases -- that
    is what stops a freed key being reissued to different work and silently retargeting its
    remote issue. So an undone story returns to its original SPRINT with a new number, and the
    chain of `previous_keys` records the whole journey. Undo restores placement, not keys; the
    result mapping names every key that changed so the caller can say so.

    A CREATED SPRINT IS LEFT STANDING. Undoing it would mean deleting a directory, and
    deletion is the one thing this feature never does unasked. An empty sprint is inert; the
    result reports it so a user can remove it deliberately.
    """
    with reorg_log_lock(state_root):
        y, log = _load_reorg_log(state_root)
        entry = _find_entry(log, entry_id)
        if entry is None:
            raise PMError(3, f"no reorg journal entry {entry_id} in "
                             f"{reorg_log_path(state_root)}")
        if entry.get("undone_at"):
            raise PMError(2, f"{entry_id} was already undone at {entry['undone_at']}")
        if entry.get("undo_started_at") and not check_only:
            raise PMError(2, f"{entry_id} has an undo in flight since "
                             f"{entry['undo_started_at']} — if it failed part way, the "
                             f"journal and `dump-plan` together say how far it got")
        now_hash = plan_shape_hash(state_root)
        want = str(entry.get("post_hash") or "")
        if now_hash != want:
            raise PMError(2,
                          f"refusing to undo {entry_id}: the planned tree has changed since "
                          f"the reorg was applied (recorded {want}, now {now_hash}). An undo "
                          f"replays placements derived from a plan that no longer exists, so "
                          f"it would move work somewhere nobody chose. Re-plan instead.")
        if check_only:
            return {"id": entry_id, "undoable": True, "hash": now_hash,
                    "operations": len(entry.get("operations") or [])}
        from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQ
        entry["undo_started_at"] = SQ(_now_iso())
        core._atomic_dump(y, log, reorg_log_path(state_root))

    # --- the moves, with NO journal lock held: they take epic locks, which come first ---
    restored, left_standing = {}, []
    for op in reversed(list(entry.get("operations") or [])):
        kind = str(op.get("op") or "")
        if kind == "retire-epic":
            move_epic(state_root, str(op["epic"]), str(op.get("from_status") or "planned"))
            with epic_node_lock(state_root, str(op["epic"])):
                p = nodes.epic_file(state_root, str(op["epic"]))
                if p:
                    ey, en = load_node(p)
                    if isinstance(en, dict):
                        en.pop("retired_reason", None)
                        en.pop("retired_at", None)
                        nodes.save_node(ey, en, p)
        elif kind == "reparent-story":
            back = reparent_story(state_root, artifacts_root, str(op["new_key"]),
                                  str(op["from_epic"]), str(op["from_sprint"]))
            restored[str(op["new_key"])] = back
        elif kind == "create-sprint":
            left_standing.append(f"{op['epic']}-{op['sprint']}")

    from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQ
    after = plan_shape_hash(state_root)
    with reorg_log_lock(state_root):
        y, log = _load_reorg_log(state_root)
        entry = _find_entry(log, entry_id) or {}
        entry["undone_at"] = SQ(_now_iso())
        entry["undo_restored"] = {str(k): SQ(v) for k, v in sorted(restored.items())}
        entry["post_undo_hash"] = SQ(after)
        core._atomic_dump(y, log, reorg_log_path(state_root))
    return {"id": entry_id, "undone": True, "restored": restored,
            "sprints_left_standing": left_standing, "hash": after}


def cmd_reorg_log(args) -> int:
    if args.hash:
        sys.stdout.write(plan_shape_hash(args.state_root) + "\n")
        return 0
    if args.record:
        from ruamel.yaml.error import YAMLError
        y = _yaml()
        try:
            with open(args.record, encoding="utf-8") as fh:
                rec = y.load(fh)
        except FileNotFoundError:
            _die_notfound(f"record file {args.record}")
        except (OSError, UnicodeDecodeError, YAMLError) as e:
            _die_usage(f"could not read the record file {args.record}: {e}")
        entry_id = record_reorg(args.state_root, _plain(rec))
        sys.stdout.write(f"OK reorg-log recorded {entry_id}\n")
        return 0

    _, log = _load_reorg_log(args.state_root)
    entries = [e for e in log.get("entries", []) if isinstance(e, dict)]
    if args.show:
        e = _find_entry(log, args.show)
        if e is None:
            _die_notfound(f"reorg journal entry {args.show}")
        entries = [e]
    if args.format == "json":
        sys.stdout.write(json.dumps({"entries": [_plain(e) for e in entries]},
                                    indent=2) + "\n")
        return 0
    if not entries:
        sys.stdout.write("no reorgs recorded\n")
        return 0
    for e in entries:
        state = "undone" if e.get("undone_at") else "applied"
        sys.stdout.write(f"{e.get('id')}  {e.get('at')}  {state}  "
                         f"{len(e.get('operations') or [])} operation(s)\n")
        if args.show:
            sys.stdout.write("\n" + str(e.get("rationale") or "").rstrip() + "\n\n")
            for op in e.get("operations") or []:
                sys.stdout.write(f"  - {json.dumps(_plain(op), sort_keys=True)}\n")
    return 0


def cmd_reorg_undo(args) -> int:
    try:
        res = undo_reorg(args.state_root, args.artifacts_root, args.id, args.check)
    except PMError:
        raise
    except FileNotFoundError as e:
        _die_notfound(str(e))
    except (ValueError, FileExistsError) as e:
        _die_usage(str(e))
    if args.check:
        sys.stdout.write(f"OK {res['id']} can be undone "
                         f"({res['operations']} operation(s))\n")
        return 0
    sys.stdout.write(f"OK reorg-undo {res['id']} — {len(res['restored'])} story(ies) "
                     f"restored\n")
    for old, new in sorted(res["restored"].items()):
        sys.stdout.write(f"  {old} -> {new}\n")
    if res["sprints_left_standing"]:
        sys.stdout.write("  sprints created by the reorg were left in place (empty, never "
                         "deleted unasked): " + ", ".join(res["sprints_left_standing"]) + "\n")
    return 0


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



# --------------------------------------------------------------------------- #
