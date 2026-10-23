"""pm_status.verbs -- the status verbs: the single-node writes and the read-only listings.

`set-status`, `set-field`, `set-estimate`, `set-depends-on`, `import-node`,
`sync-story-doc` / `story-doc-init`, the lock verbs (`set-lock`, `clear-lock`,
`check-lock`), `add-test-run`, `notice`, and the read side -- `list-epics`,
`list-stories`, `show`, `verify`.

It is the top of the node-and-metrics stack and sits directly ABOVE `issues`: `set-status`
on a story reaching `done` resolves the issues that story claims (`_resolve_story_items`),
so the status verbs are CONSUMERS of the issue store rather than part of the node layer.
That is the boundary the original "state" bucket got wrong. Nothing below this module
imports it; only `__main__.py` (the parser and `main`) reaches these functions.

CALL STYLE ACROSS MODULES. Every name the suite patches is reached through its MODULE OBJECT:
`core._load` / `core._atomic_dump` / `core.notices_lock`, `nodes.save_node` /
`nodes.epic_file`, `issues.store.resolve_issue_core`. A `from ..issues.store import
resolve_issue_core` binding here would be a private copy the patch could never reach, and
the test would pass while guarding nothing. Names nothing patches are imported by name. None
of the patch targets is re-exported by this module or by `__main__.py`.

`IssueStore` is imported by name: the suite patches a CLASS ATTRIBUTE on it
(`patch.object(pm.IssueStore, "save_open", ...)`), which mutates the one class object every
binding names.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys

from .. import core, issues, nodes
from ..core import (
    METRIC_FIELDS,
    STATUS_FOR_DIR,
    VALID_EPIC_STATUS,
    VALID_SPRINT_STATUS,
    VALID_STORY_STATUS,
    VALID_STORY_TRANSITIONS,
    PMError,
    _coerce,
    _die_notfound,
    _die_usage,
    _event_keys,
    _exit_code_or_fail,
    _is_na,
    _is_number,
    _iter_count,
    _lock_age_minutes,
    _now_iso,
    _num_or_none,
    _parse_iso,
    _run_core,
    _yaml,
    append_event,
    canonical_epic_key,
    epic_node_lock,
    issues_lock,
    notices_path,
    parse_story_key,
    sprint_dirname,
)
from ..issues.store import IssueStore, canonical_bl_key, issues_paths
from ..metrics.events import _block_duration_since_last_open
from ..metrics.rates import TOKEN_CLASSES, cost_from_tokens, rate_overrides
from ..metrics.report import _write_spend
from ..metrics.spend import _fmt_actuals, rollup_epic, rollup_sprint
from ..nodes import (
    BOOL_NODE_FIELDS,
    DERIVED_NODE_FIELDS,
    NUMERIC_NODE_FIELDS,
    _check_lock_verdict,
    _epic_path_or_die,
    _epic_write_lock,
    _infer_kind,
    _load_checked,
    _sprint_key_from_dir,
    check_backrefs,
    deps_list,
    ensure_node_path,
    find_epic_dir,
    init_story_doc,
    iter_epic_dirs,
    iter_story_files,
    list_sprint_dirs,
    list_story_files,
    load_node,
    sprint_file,
    story_doc_path,
    story_file,
)


def cmd_notice(args) -> int:
    """Record a one-time-ever advisory notice for this project. Exit 0 = emit it now (and
    record it), exit 1 = already emitted for this key, exit 2 = usage error OR an unexpected
    failure while recording (lock/I/O). 2 is deliberately overloaded with "usage error"
    rather than given a new number of its own: a caller that treats any nonzero exit as "do
    not print the pointer" already handles it correctly either way, and the one distinction
    that matters -- 1 means "already said, all is well" -- stays unambiguous. A crash must
    never surface as 1: a caller told "already emitted" says nothing further and moves on,
    so a masked crash would silently and permanently suppress the pointer with nothing to
    show for it.

    Scope is the KEY ALONE, not a session: there is no notion of "session" that outlives one
    skill invocation (`{session_id}` in `step-00-activate.md` is bound fresh per invocation
    and no caller of `notice` is ever a dispatched subagent that could inherit one), so a
    per-session key would never repeat and this would fire every single invocation -- exactly
    the nagging it exists to prevent. A key is recorded at most once, ever, per project: once
    a key has fired, it never fires again for that `--state-root`, which is correct for an
    advisory whose content is static ("this exists, configure it if you want") and whose
    trigger condition (`modules.l3io-pm` being absent) is itself a valid permanent state, not
    a transient one to keep re-flagging.

    An absent or unparseable notices file means nothing has been emitted yet -- a notice is
    advisory only, so a damaged file must never block the caller's real work; it is simply
    treated as empty and rewritten clean on this call. That tolerance covers a bad READ only:
    a failure while actually recording (the lock, or the write itself) is a real failure and
    is reported as one, not folded into "already emitted" or silently swallowed as success.
    """
    key = (args.key or "").strip()
    if not key:
        sys.stderr.write("notice: --key must be non-empty\n")
        return 2
    path = notices_path(args.state_root)
    try:
        os.makedirs(args.state_root, exist_ok=True)
        with core.notices_lock(args.state_root):
            # _load returns (yaml_instance, data) -- data is None when the file is absent
            # or fails to parse the way _load's caller expects. Reuse the returned YAML
            # instance for the dump so round-trip settings (width, indent, quote style)
            # match.
            try:
                y, data = core._load(path)
            except Exception:  # noqa: BLE001 -- a notice ledger that cannot be read is rebuilt, never fatal
                y, data = _yaml(), None
            keys = data.get("keys") if isinstance(data, dict) else None
            if not isinstance(keys, list):
                keys = []
            if key in keys:
                return 1
            keys.append(key)
            core._atomic_dump(y, {"keys": keys}, path)
    except Exception as e:  # noqa: BLE001 -- recording a notice must never fail the command it advises
        sys.stderr.write(f"notice: could not record the notice at {path}: {e}\n")
        return 2
    return 0


# --------------------------------------------------------------------------- #
# status verbs
# --------------------------------------------------------------------------- #
def _resolve_story_items(state_root, node, story_key, session) -> None:
    """After a story reaches `done`, resolve every key in its `resolves:` as fixed.

    ADR-0003: this never fails set-status. The status save already happened and is
    durable; reporting it as failed would invite a retry or a rollback of finished
    work. Every exception except KeyboardInterrupt -- SystemExit included -- becomes
    a warning, and audit-issues finding 1c catches what was missed. `resolves:` itself
    is hand-editable YAML, so normalising it (a bare scalar counts as one key; anything
    else is a malformed-field warning) happens INSIDE the catch-all too -- a bad shape
    there must warn, never raise out of set-status."""
    raw = node.get("resolves")
    if not raw:
        return
    try:
        if isinstance(raw, str):
            keys = [raw]
        elif isinstance(raw, (list, tuple)):
            keys = [str(k) for k in raw]
        else:
            sys.stderr.write(f"pm-status.py: warning -- {story_key} has a malformed resolves: "
                             f"({raw!r}); nothing resolved. Run /l3io-doctor triage.\n")
            return
        open_path = issues_paths(state_root)[0]
        with issues_lock(open_path):
            store = IssueStore(open_path)
            for k in keys:
                try:
                    kc = canonical_bl_key(k)
                    was_resolved = bool(kc and store.resolved_items(kc))
                    # Module-qualified, never by name: `resolve_issue_core` is a
                    # mock.patch target, and a re-exported binding here would be a
                    # private copy that `patch.object(pm.issues.store, ...)` could not
                    # reach. `issues` is the package module and is not shadowed by the
                    # local `store` (an IssueStore) above.
                    msg = issues.store.resolve_issue_core(
                        store, k, "fixed", story_key, None, session, "set-status")
                    # `resolved BL-...` is the spec §2.6 output contract for a NEW
                    # resolution only; a key resolved before (a repeat done) gets `ok`.
                    sys.stdout.write(f"{'ok' if was_resolved else 'resolved'} {msg}\n")
                except PMError as e:
                    sys.stderr.write(f"pm-status.py: warning -- could not resolve {k} "
                                     f"for {story_key}: {e.msg} -- run /l3io-doctor "
                                     f"triage\n")
    except KeyboardInterrupt:
        raise
    except BaseException as e:  # noqa: BLE001 -- deliberate, ADR-0003
        sys.stderr.write(f"pm-status.py: warning -- done hook failed for {story_key}: "
                         f"{e!r}; the status write stands. Run /l3io-doctor triage "
                         f"(audit-issues finding 1c) to finish it.\n")


def cmd_set_status(args) -> int:
    kind = _infer_kind(args)
    valid = {"story": VALID_STORY_STATUS, "sprint": VALID_SPRINT_STATUS, "epic": VALID_EPIC_STATUS}[kind]
    if args.status not in valid:
        _die_usage(f"invalid {kind} status '{args.status}' — expected one of {sorted(valid)}")

    # blocked-lifecycle argument guards (story only -- sprint/epic keep no --reason/--resolution).
    reason = str(getattr(args, "reason", "") or "").strip()
    resolution = str(getattr(args, "resolution", "") or "").strip()
    if kind == "story" and args.status == "blocked" and not reason:
        _die_usage("--status blocked requires --reason \"<why>\" -- a blocked story with no reason "
                   "on record is what this flag exists to prevent")
    if kind != "story" and (reason or resolution):
        _die_usage("--reason and --resolution are story-only flags; sprints and epics compose "
                   "from their children")
    if kind == "story" and args.status != "blocked" and reason:
        _die_usage("--reason is only valid with --status blocked; other transitions have no "
                   "reason field to record")

    # An epic node is written under its epic_node_lock. The event append inside is a leaf
    # lock, and the done hook below (issues_lock) runs only for a story, outside any hold.
    with _epic_write_lock(args, kind):
        y, node, path, label = _load_checked(args.state_root, args, kind)
        prior = str(node.get("status", "")) or None

        # Story transitions are per-pair, not per-target. See VALID_STORY_TRANSITIONS.
        if kind == "story" and prior is not None:
            allowed = VALID_STORY_TRANSITIONS.get(prior, set())
            if args.status not in allowed:
                _die_usage(
                    f"invalid story transition {prior!r} -> {args.status!r}; from {prior!r} "
                    f"allowed: {sorted(allowed) or ['(terminal)']}")
            # blocked -> done is the one transition that requires --resolution: the story
            # resolved by the same event that unblocked it (e.g. spec change removed the need).
            if prior == "blocked" and args.status == "done" and not resolution:
                _die_usage("blocked -> done requires --resolution \"<why the story is done "
                           "rather than resumed>\"; use --status in-progress to resume")

        node["status"] = args.status
        node["updated_at"] = _now_iso()
        if args.title:
            node["title"] = args.title
        if kind == "story":
            leaving_blocked = prior == "blocked" and args.status != "blocked"
            entering_blocked = args.status == "blocked" and prior != "blocked"
            if args.status == "blocked":
                node["blocked_reason"] = reason
            elif leaving_blocked and "blocked_reason" in node:
                # Current node reflects only current state; block history lives in the log.
                del node["blocked_reason"]
            if entering_blocked:
                # completion_evidence.blocks_seen: O(1) counter for closure-side
                # observability. Not used for cohort routing -- see §5 of the design.
                # Not decremented on exit (this counts events, not current state).
                from ruamel.yaml.comments import CommentedMap
                ce = node.get("completion_evidence")
                if not isinstance(ce, dict):
                    ce = CommentedMap()
                    node["completion_evidence"] = ce
                ce["blocks_seen"] = int(ce.get("blocks_seen", 0) or 0) + 1
        else:
            leaving_blocked = entering_blocked = False
        nodes.save_node(y, node, path, getattr(args, "flock", False))

        if not getattr(args, "no_events", False):
            payload = {"ts": _now_iso(), "event": "status",
                       "from": prior, "to": args.status,
                       "session": getattr(args, "session_id", None)}
            payload.update(_event_keys(kind, args))
            append_event(args.state_root, payload)
            if entering_blocked:
                bp = {"ts": _now_iso(), "event": "block_open",
                      "story": args.story, "reason": reason,
                      "session": getattr(args, "session_id", None)}
                append_event(args.state_root, bp)
            if leaving_blocked:
                dur = _block_duration_since_last_open(args.state_root, args.story)
                bc = {"ts": _now_iso(), "event": "block_close",
                      "story": args.story, "duration_hours": dur,
                      "session": getattr(args, "session_id", None)}
                if args.status == "done":
                    bc["resolution"] = resolution
                append_event(args.state_root, bc)

    sys.stdout.write(f"OK set-status {label} -> {args.status}\n")
    if kind == "story" and args.status == "done":
        _resolve_story_items(args.state_root, node, args.story,
                             getattr(args, "session_id", None))
    return 0


EPIC_KEY_RE = re.compile(r"^E\d{3}$")
STORY_KEY_RE = re.compile(r"^E\d{3}-S\d{2}-\d{3}$")
# status-files.md §11: `depends_on` lives on BOTH an epic node (epic keys) and a story node
# (story keys). Reading only that section's first sentence gives the epic case and silently
# loses the story case, which is the shape the migration fixtures actually carry.
DEPENDS_ON_KEY_RE = {"epic": EPIC_KEY_RE, "story": STORY_KEY_RE}


def cmd_set_depends_on(args) -> int:
    """Add or remove keys on a node's `depends_on` list.

    `depends_on` is epic-only and list-shaped (status-files.md §11). `set-field --value` takes a
    single string, so routing a list through it would store "['E001']" as a scalar -- worse than
    not writing it at all, because a later reader takes it for one. That is exactly why the
    migration engine WARNed and skipped this field rather than flattening it.

    All-or-nothing: every key is validated before anything is written, because a half-applied
    dependency list is a worse artefact than an absent one -- l3io-plan topologically sorts
    on it, so a missing edge silently reorders a phase.

    --remove EXISTS BECAUSE ITS ABSENCE FORCED A HAND EDIT. This verb was append-only, and
    `set-field` refuses a list, so the only way to drop a dependency was to open epic.yaml and
    edit it -- which the state contract forbids, and for the reason this whole script exists:
    free-form YAML edits were dropped and malformed under parallel execution. A reorg that
    removes the last story edge justifying `E001 depends_on E003` leaves that declaration
    standing, and phases come from epic-level depends_on, so the two epics keep serialising
    and the reorg's whole purpose goes unrealised. There was no command to recommend.

    REMOVING A STILL-JUSTIFIED DEPENDENCY IS REFUSED. If any story under this node still
    depends on a story under the key being removed, dropping the edge tells the planner the
    two can run concurrently when they cannot. `--force` overrides, because an epic
    dependency can also encode a sequencing decision no story edge expresses ("ship the API
    before the client"), and this script cannot tell those apart -- but it can make the
    difference deliberate.
    """
    from ruamel.yaml.comments import CommentedSeq
    from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQ

    kind = _infer_kind(args)
    if kind not in DEPENDS_ON_KEY_RE:
        _die_usage(f"depends_on lives on an epic or a story node, not a {kind} "
                   f"(status-files.md §11)")
    key_re = DEPENDS_ON_KEY_RE[kind]
    self_key = args.epic if kind == "epic" else args.story

    keys = list(args.add or [])
    drops = list(getattr(args, "remove", None) or [])
    if not keys and not drops:
        _die_usage("set-depends-on needs at least one --add KEY or --remove KEY")
    if keys and drops:
        # Refused rather than ordered. Whichever order were chosen, half the readers of a
        # later command would assume the other, and the two are trivially separable calls.
        _die_usage("--add and --remove in one call is refused: the result would depend on an "
                   "order nobody can see. Run them as two commands")
    for k in keys + drops:
        if not key_re.match(k):
            flag = "--add" if k in keys else "--remove"
            _die_usage(f"{flag} {k!r} is not a {kind} key (expected {key_re.pattern}); "
                       f"nothing written")
    for k in keys:
        if k == self_key:
            _die_usage(f"--add {k!r} is the node itself -- it cannot depend on itself; "
                       f"nothing written")

    # The justification check runs BEFORE the lock, because it reads the whole epic tree and
    # refusing is the common outcome on a mistaken call -- taking a write lock to then refuse
    # would block a concurrent legitimate write for no reason.
    if drops and kind == "epic" and not getattr(args, "force", False):
        # Only keys actually PRESENT can be refused. Removing one that is not there is a
        # no-op, and a no-op must not be blocked by a justification for an edge that is
        # already gone -- a caller acting on a stale read would otherwise get an error for
        # asking for a state the tree is already in.
        _p = nodes.epic_file(args.state_root, canonical_epic_key(self_key))
        _cur = []
        if _p:
            _, _n = load_node(_p)
            if isinstance(_n, dict):
                _cur = [str(e) for e in deps_list(_n, _p)]
        present = [k for k in drops if str(k) in _cur]
        blocked = _justifying_story_edges(args.state_root, self_key, present) if present else []
        if blocked:
            shown = ", ".join(f"{a} -> {b}" for a, b in blocked[:5])
            more = f" (+{len(blocked) - 5} more)" if len(blocked) > 5 else ""
            _die_usage(f"refusing to remove {sorted({b for _a, b in blocked})} from "
                       f"{self_key}: {len(blocked)} story dependency(ies) still cross that "
                       f"boundary — {shown}{more}. Dropping the edge would tell the planner "
                       f"these epics can run concurrently when they cannot. Move the stories "
                       f"first (/l3io-plan reorg), or pass --force if this dependency is a "
                       f"sequencing decision no story edge expresses")

    with _epic_write_lock(args, kind):
        y, node, path, label = _load_checked(args.state_root, args, kind)
        existing = node.get("depends_on")
        if not isinstance(existing, list):
            existing = CommentedSeq()
            node["depends_on"] = existing
        added, removed = [], []
        for k in keys:
            if str(k) not in [str(e) for e in existing]:
                existing.append(SQ(k))
                added.append(k)
        for k in drops:
            # Idempotent, like --add: removing a key that is not there is a no-op, not an
            # error. A caller acting on a stale read should not have to care.
            hits = [e for e in existing if str(e) == str(k)]
            for h in hits:
                existing.remove(h)
            if hits:
                removed.append(k)
        # An emptied list is written as `depends_on: []` rather than dropped, so a reader
        # sees "declared, and empty" exactly as it sees "never declared" -- both mean no
        # dependencies, and every reader here treats a missing key and [] the same way.
        node["updated_at"] = _now_iso()
        nodes.save_node(y, node, path, getattr(args, "flock", False))

    if drops:
        sys.stdout.write(f"OK set-depends-on {label} -= {removed or '(nothing present)'}\n")
    else:
        sys.stdout.write(f"OK set-depends-on {label} += {added or '(nothing new)'}\n")
    return 0


def _justifying_story_edges(state_root: str, epic_key: str, targets: list) -> list:
    """(story, target_epic) for every story edge crossing from epic_key into one of targets.

    What makes an epic-level dependency earned: a story under this epic depending on a story
    under that one. Zero such edges is what `plan-graph.py` reports as
    `unneeded-cross-epic-dependency`, and what makes a removal safe.
    """
    want = {canonical_epic_key(t) for t in targets}
    out = []
    for story_key, path in iter_story_files(state_root, canonical_epic_key(epic_key)):
        _, node = load_node(path)
        if not isinstance(node, dict):
            continue
        for dep in deps_list(node, path):
            try:
                dep_epic, _sp, _n = parse_story_key(str(dep))
            except ValueError:
                continue
            if dep_epic in want:
                out.append((story_key, dep_epic))
    return sorted(out)


def cmd_import_node(args) -> int:

    """Create a state node from a migration record. The counterpart to set-status for a
    node that does not exist yet.

    This is cmd_set_status with ONE step swapped -- ensure_node_path() where set-status
    calls _load_checked() -- because _load_checked exits 3 on a missing node, which is
    correct for set-status and fatal for this verb. set-status itself is untouched: it
    must never create anything.

    Idempotent by SKIP, not by overwrite. A migration retried after a partial run must
    not clobber a node a later step already edited, so an existing file is left exactly
    as it is and reported.
    """
    from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQ

    kind = _infer_kind(args)
    valid = {
        "story": VALID_STORY_STATUS,
        "sprint": VALID_SPRINT_STATUS,
        "epic": VALID_EPIC_STATUS,
    }[kind]
    if args.status not in valid:
        _die_usage(
            f"invalid {kind} status '{args.status}' -- expected one of {sorted(valid)}")

    # blocked_reason gate: a story imported at `status: blocked` must carry a --reason
    # the same way set-status does. Migration sources that carry blocked state (bmad-loop
    # is the shape) preserve the reason on the record; a source that reports blocked but
    # cannot preserve the reason is a broken source, not an acceptable import shape.
    # Sprints and epics don't have `blocked` in their status enum, so the guard is
    # story-only by construction.
    reason = str(getattr(args, "reason", "") or "").strip()
    if kind == "story" and args.status == "blocked" and not reason:
        _die_usage("--status blocked requires --reason \"<why>\" -- a blocked story with no "
                   "reason on record is what this flag exists to prevent")
    if kind != "story" and reason:
        _die_usage("--reason is a story-only flag; sprint/epic status sets have no blocked")
    if kind == "story" and args.status != "blocked" and reason:
        _die_usage("--reason is only valid with --status blocked")

    with _epic_write_lock(args, kind, require_exists=False):
        path, label = ensure_node_path(args.state_root, args, kind, args.status)
        if os.path.exists(path):
            sys.stdout.write(f"SKIP import-node {label} -- already exists\n")
            return 0

        node = {}
        if kind == "epic":
            node["key"] = SQ(args.epic)
            node["title"] = args.title or ""
            node["goal"] = ""
        elif kind == "sprint":
            node["key"] = SQ(args.sprint)
            node["epic"] = SQ(args.epic)
            node["title"] = args.title or ""
        else:
            epic_key, sprint_key, _ = parse_story_key(args.story)
            node["key"] = SQ(args.story)
            node["epic"] = SQ(epic_key)
            node["sprint"] = SQ(sprint_key)
            node["title"] = args.title or ""
            node["classification"] = args.classification or "unknown"

        node["status"] = args.status
        node["updated_at"] = _now_iso()
        if args.origin:
            node["origin"] = args.origin
            node["origin_note"] = args.origin_note or ""
        if kind == "story" and args.status == "blocked":
            node["blocked_reason"] = reason
            # completion_evidence.blocks_seen is a counter of OUR events, not the
            # source's history -- import-node predates our history for a migrated node,
            # so the counter starts at 0. A subsequent set-status --status blocked would
            # bump it. Not adding it here.

        nodes.save_node(_yaml(), node, path, getattr(args, "flock", False))

        if not getattr(args, "no_events", False):
            payload = {
                "ts": _now_iso(), "event": "import", "from": None, "to": args.status,
                "session": getattr(args, "session_id", None),
            }
            payload.update(_event_keys(kind, args))
            append_event(args.state_root, payload)
            # For a story imported at blocked, emit a paired block_open so a future
            # set-status transitioning off blocked can derive duration the same way
            # a set-status-created block does. Without this, _block_duration_since_
            # last_open would return None and block_close would land without duration.
            if kind == "story" and args.status == "blocked":
                bp = {"ts": _now_iso(), "event": "block_open",
                      "story": args.story, "reason": reason,
                      "session": getattr(args, "session_id", None)}
                append_event(args.state_root, bp)

    sys.stdout.write(f"OK import-node {label} -> {args.status}\n")
    return 0


def cmd_sync_story_doc(args) -> int:
    """Write `status:` into the story markdown's frontmatter.

    The state YAML is the machine's truth; this file is the human's. They have
    never agreed -- a production audit found 73 of 73 stories divergent, every
    one of them in the same direction, which is an unimplemented write rather
    than drift.

    This NEVER fails its caller. It runs after a set-status that has already
    succeeded, and a documentation write must not be able to strand a state
    transition that is already durable.
    """
    if args.status not in VALID_STORY_STATUS:
        sys.stderr.write(f"ERROR unknown story status {args.status!r}; "
                         f"expected one of {', '.join(sorted(VALID_STORY_STATUS))}\n")
        return 2
    try:
        path = story_doc_path(args.artifacts_root, args.story)
    except ValueError as exc:
        sys.stderr.write(f"ERROR {exc}\n")
        return 2
    if not os.path.exists(path):
        sys.stderr.write(f"WARN no story file at {path} — state was written, "
                         f"document not updated\n")
        return 0

    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if not text.startswith("---\n"):
        sys.stderr.write(f"WARN {path} has no YAML frontmatter — nothing to update\n")
        return 0
    end = text.find("\n---", 3)
    if end == -1:
        sys.stderr.write(f"WARN {path} has an unterminated frontmatter block\n")
        return 0
    head, body = text[4:end + 1], text[end + 4:]

    # ruamel round-trip: preserves key order and comments. Never split on '---'
    # by hand -- a body line of dashes is legal markdown and would corrupt it.
    from ruamel.yaml.comments import CommentedMap
    yaml = _yaml()
    try:
        meta = yaml.load(head)
    except Exception:                                    # noqa: BLE001
        # Deliberately broad. This runs after a set-status that already
        # succeeded, and no parse failure is worth stranding a durable state
        # transition over. The warning is the signal; the exit code is not.
        sys.stderr.write(f"WARN {path} frontmatter does not parse as YAML — "
                         f"state was written, document not updated\n")
        return 0
    if meta is None:
        meta = CommentedMap()
    if not hasattr(meta, "get"):
        sys.stderr.write(f"WARN {path} frontmatter is not a mapping — "
                         f"state was written, document not updated\n")
        return 0
    if meta.get("status") == args.status:
        if not args.quiet:
            sys.stdout.write(f"OK {args.story} document already {args.status}\n")
        return 0
    meta["status"] = args.status
    buf = io.StringIO()
    yaml.dump(meta, buf)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("---\n" + buf.getvalue() + "---" + body)
    if not args.quiet:
        sys.stdout.write(f"OK {args.story} document -> {args.status}\n")
    return 0


def cmd_story_doc_init(args) -> int:
    def run():
        result = init_story_doc(args.state_root, args.artifacts_root, args.story)
        sys.stdout.write(f"OK story-doc-init {args.story} {result} -> "
                         f"{story_doc_path(args.artifacts_root, args.story)}\n")
        return 0
    return _run_core(run)


def cmd_set_lock(args) -> int:
    """Claim the epic ownership lock. Exit 0 on success (claim / re-claim / takeover);
    exit 5 (matching cmd_check_lock's "locked" code) when a foreign lock is live or
    unreadable, in which case the file is left untouched.

    The whole read-existing-lock -> decide -> write-claim cycle runs under
    `epic_node_lock` -- see its docstring for why a bare read-then-write here would be
    the same check-then-act race this function exists to close.
    """
    from ruamel.yaml.comments import CommentedMap
    _epic_path_or_die(args)                     # exit 3 before any lock file is created
    with epic_node_lock(args.state_root, args.epic):
        path = _epic_path_or_die(args)          # again: a move may have landed meanwhile
        y, data = load_node(path)
        if data is None:
            _die_notfound(f"epic {args.epic} file is empty")

        takeover_note = ""
        existing = data.get("_lock")
        if existing is not None:
            if not isinstance(existing, dict):
                sys.stdout.write(
                    f"LOCKED epic {args.epic}: existing _lock is malformed (not a "
                    f"mapping) — a lock that cannot be read is not a lock that may "
                    f"be stolen; refusing to claim\n")
                return 5
            holder = str(existing.get("session_id", ""))
            if holder != args.session_id:
                if "claimed_at" not in existing:
                    sys.stdout.write(
                        f"LOCKED epic {args.epic}: existing _lock held by {holder!r} "
                        f"has no claimed_at — refusing to claim\n")
                    return 5
                claimed = _parse_iso(existing.get("claimed_at"))
                if claimed is None:
                    sys.stdout.write(
                        f"LOCKED epic {args.epic}: existing _lock held by {holder!r} "
                        f"has an unparseable claimed_at "
                        f"({existing.get('claimed_at')!r}) — refusing to claim\n")
                    return 5
                ttl = int(existing.get("ttl_minutes", 30))
                age_minutes = _lock_age_minutes(claimed)
                if age_minutes <= ttl:
                    remaining = ttl - age_minutes
                    sys.stdout.write(
                        f"LOCKED epic {args.epic} held by {holder} "
                        f"({remaining:.1f}m remaining of {ttl}m ttl)\n")
                    return 5
                takeover_note = (f" (took over stale lock from {holder}, "
                                  f"age={age_minutes:.1f}m > ttl={ttl}m)")
            # else: same session — re-claim below, refreshing claimed_at. A retry
            # by the owner must not deadlock or refuse against its own lock.

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
        core._atomic_dump(y, ordered, path)
        sys.stdout.write(
            f"OK set-lock epic {args.epic} session={args.session_id} "
            f"ttl={args.ttl_minutes}m{takeover_note}\n")
    return 0


def cmd_clear_lock(args) -> int:
    """Remove the epic's `_lock`. The read-delete-write runs under epic_node_lock, like every
    epic.yaml write: without it, a concurrent promote-issue roll-up (which saves the whole
    epic node under that lock) could land after this write and restore the lock it removed."""
    absent = f"OK clear-lock epic {args.epic} (epic/file absent — no-op)\n"
    if nodes.epic_file(args.state_root, args.epic) is None:
        sys.stdout.write(absent)                # no lock file for an absent epic
        return 0
    with epic_node_lock(args.state_root, args.epic):
        path = nodes.epic_file(args.state_root, args.epic)     # again: a move may have landed
        if path is None:
            sys.stdout.write(absent)
            return 0
        y, data = load_node(path)
        if data is None:
            sys.stdout.write(f"OK clear-lock epic {args.epic} (file empty — no-op)\n")
            return 0
        if "_lock" not in data:
            sys.stdout.write(f"OK clear-lock epic {args.epic} (no _lock present — no-op)\n")
            return 0
        del data["_lock"]
        core._atomic_dump(y, data, path)
    sys.stdout.write(f"OK clear-lock epic {args.epic}\n")
    return 0


def cmd_check_lock(args) -> int:
    """Exit 0 if epic is free to claim; exit 5 if held by another session within TTL.

    Timestamp parsing and age arithmetic go through `_parse_iso`/`_lock_age_minutes`
    -- the same helpers `cmd_set_lock` uses -- so the two TTL comparisons cannot drift
    apart into two independently-wrong implementations. The verdict itself lives in
    `_check_lock_verdict`, which promote-issue shares.
    """
    path = nodes.epic_file(args.state_root, args.epic)
    if path is None:
        sys.stdout.write("FREE\n")
        return 0
    _y, data = load_node(path)
    if data is None or "_lock" not in data:
        sys.stdout.write("FREE\n")
        return 0
    code, line = _check_lock_verdict(data["_lock"], args.session_id)
    sys.stdout.write(line + "\n")
    return code


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
    with _epic_write_lock(args, kind):
        return _set_estimate(args, kind)


def _set_estimate(args, kind) -> int:
    """cmd_set_estimate's body; the caller holds the epic lock for an epic node."""
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

    nodes.save_node(y, node, path, getattr(args, "flock", False))
    sys.stdout.write(f"OK set-estimate {label}\n")
    return 0


def cmd_set_field(args) -> int:
    """Set an arbitrary nested field at a dot-path within a node.
    --story KEY | --epic ID [--sprint ID] selects the node.
    --field: dot-path within the node, e.g. 'retrospective.summary', 'closed.date'
    --value: string value to set
    """
    # The field itself OR any sub-path of it: an exact-match lookup let `resolves.x` walk
    # into the node and save a mapping under resolves:, and `status.x` crash mid-walk.
    derived = next((d for d in DERIVED_NODE_FIELDS
                    if args.field == d or args.field.startswith(d + ".")), None)
    if derived is not None:
        inside = "" if derived == args.field else f" (it is inside {derived})"
        _die_usage(f"--field {args.field} is not directly writable{inside}: "
                   f"{DERIVED_NODE_FIELDS[derived]}")
    # ...or a PARENT of one: `completion_evidence` would replace the whole mapping and
    # discard the test_runs that tests_passing is derived from.
    contained = next((d for d in sorted(DERIVED_NODE_FIELDS)
                      if d.startswith(args.field + ".")), None)
    if contained is not None:
        _die_usage(f"--field {args.field} is not directly writable (it contains {contained}): "
                   f"{DERIVED_NODE_FIELDS[contained]}")

    kind = _infer_kind(args)
    _check_lane_value(args, kind)
    with _epic_write_lock(args, kind):
        return _set_field(args, kind)


# A lane is a NUMBER, 1..999. Not a style choice -- it is what makes "never a person"
# mechanical instead of hopeful. A word-shaped token cannot be screened: `sarah` and
# `backend` are the same shape, so any regex permitting the second permits the first, and a
# list of names to reject would be both brittle and culturally parochial. Numbering closes
# the question by construction, and it matches the rest of the design: `lane_count` is a
# count, and a lane is a slot in `1..lane_count`.
_LANE_RE = re.compile(r"^[1-9][0-9]{0,2}$")


def _check_lane_value(args, kind) -> None:
    """Guard the `lane` field: epic-only, and never a person's name.

    WHY THE FIELD IS `lane` AND NOT `owner`. `owner` attracts names — somebody commits
    `owner: sarah` and the generic concept erodes by default rather than by decision. A lane
    is a slot in a partition; who fills it lives in the gitignored user layer, so a human's
    name cannot reach the repository at all. The vocabulary is the guardrail, and this
    function is what stops the vocabulary being the ONLY guardrail.

    EPIC-ONLY, because `1 epic = 1 lane` is the invariant everything else rests on: sprints
    and stories live under their epic's directory and inherit its lane by construction. A
    story carrying its own lane would make the lane graph a different graph from the epic
    graph, and every cross-lane question would need its own traversal instead of relabelling
    the epic one.
    """
    if getattr(args, "field", None) != "lane":
        return
    if kind != "epic":
        _die_usage(f"`lane` lives on an epic node, not a {kind}. Sprints and stories inherit "
                   f"their epic's lane from the directory they are in — one epic is one lane, "
                   f"and a story with its own lane would break that")
    value = str(getattr(args, "value", "") or "")
    if not _LANE_RE.match(value):
        _die_usage(f"lane {value!r} is not a lane number. A lane is a SLOT in a partition — "
                   f"1, 2, 3 — never a person: who works a lane is recorded in the gitignored "
                   f"user config, so a name cannot reach the repository. Numbering is what "
                   f"makes that mechanical: a word-shaped token cannot be screened, because "
                   f"`backend` and `sarah` are the same shape. Expected 1-999")


def _set_field(args, kind) -> int:
    """cmd_set_field's body; the caller holds the epic lock for an epic node."""
    y, node, path, label = _load_checked(args.state_root, args, kind)

    field_parts = args.field.split(".")
    target = node
    for part in field_parts[:-1]:
        if target.get(part) is None:
            from ruamel.yaml.comments import CommentedMap
            target[part] = CommentedMap()
        target = target[part]
    value = args.value
    if args.field in NUMERIC_NODE_FIELDS:
        n = _iter_count(value) if args.field.endswith("fix_iterations") else None
        if args.field.endswith("fix_iterations"):
            if n is None:
                _die_usage(
                    f"--field {args.field} needs a non-negative whole number, got {value!r}. "
                    "Stored as text this silently becomes provenance=backout on a story that "
                    "needed no rework, and the clean fix cohort never fills. If the value came "
                    "from a template placeholder, it was not substituted.")
            value = n
        elif _is_number(value):
            value = _coerce(field_parts[-1], value)
    elif args.field in BOOL_NODE_FIELDS:
        low = str(value).strip().lower()
        if low in ("true", "yes", "1"):
            value = True
        elif low in ("false", "no", "0"):
            value = False
    target[field_parts[-1]] = value

    nodes.save_node(y, node, path, getattr(args, "flock", False))
    sys.stdout.write(f"OK set-field {label} {args.field}={args.value!r}\n")
    return 0


def cmd_add_test_run(args) -> int:
    """Append one executed test command and derive tests_passing from the set.

    The boolean it replaces recorded that the agent was satisfied, not that
    anything passed: a story shipped `tests_passing: true` having broken a
    suite it never ran, and the break surfaced two stories later. A command
    and an exit code are falsifiable by anyone who re-runs them.

    DERIVATION RULE: `tests_passing` is `all(exit_code == 0)` over the **last
    run of each distinct command**, not over every run ever appended. Agents
    are told to record every command they ran, failures included, so the normal
    fix-then-rerun cycle -- `pytest` -> 1, fix, `pytest` -> 0 -- appends both.
    Folding history into the boolean would leave that story permanently
    `tests_passing: false` and punish exactly the behavior the record wants.
    The full history stays in `test_runs`: that is the evidence, and dropping
    the failed run to make the boolean come out right would destroy it. A
    command whose last run is non-zero still derives False, however many green
    runs preceded it.
    """
    if args.exit_code < 0:
        sys.stderr.write("ERROR --exit-code must be >= 0\n")
        return 2
    path = story_file(args.state_root, args.story)
    if path is None:
        _die_notfound(f"story {args.story}")
    y, node = load_node(path)
    if node is None:
        _die_notfound(f"story {args.story} — file {path} is empty")
    from ruamel.yaml.comments import CommentedMap
    ce = node.setdefault("completion_evidence", CommentedMap())
    runs = ce.setdefault("test_runs", [])
    entry = CommentedMap()
    entry["command"] = args.command
    entry["exit_code"] = int(args.exit_code)
    runs.append(entry)
    # Last run wins per distinct command (see the docstring's DERIVATION RULE).
    # dict keeps insertion order and a re-run overwrites in place, so this is the
    # latest verdict for each command, in the order the commands first appeared.
    latest = {}
    for r in runs:
        if not isinstance(r, dict):
            # A hand-edited list can hold a scalar; an unreadable entry must never
            # derive a pass, and it has no command to key on -- give it its own slot.
            latest[("__malformed__", id(r))] = r
            continue
        latest[r.get("command")] = r
    ce["tests_passing"] = all(
        _exit_code_or_fail(r.get("exit_code") if isinstance(r, dict) else None) == 0
        for r in latest.values()
    )
    nodes.save_node(y, node, path, use_flock=True)
    sys.stdout.write(f"OK {args.story} test run recorded "
                     f"({args.command} -> {args.exit_code}); "
                     f"tests_passing={ce['tests_passing']}\n")
    return 0


def cmd_list_epics(args) -> int:
    """Enumerate every epic in the state tree with its status bucket.

    Read-only. A missing state root prints nothing and exits 0 -- the shape of a
    project with no state yet, which is the same silent shape the old
    `ls -d ... 2>/dev/null` probe gave callers.

    --format keys (default): one E{nnn} per line, sorted, buckets flattened. Cheap.
    --format json: a list of {key, bucket, status}, sorted by (bucket, key) with
    STATUS_DIRS order preserved so active/planned/archived is a stable read.
    """
    rows = list(iter_epic_dirs(args.state_root))
    if args.format == "json":
        out = [{"key": k, "bucket": b, "status": STATUS_FOR_DIR[b]} for b, k, _ in rows]
        sys.stdout.write(json.dumps(out) + "\n")
    else:
        for _b, k, _p in rows:
            sys.stdout.write(f"{k}\n")
    return 0


def cmd_list_stories(args) -> int:
    """Enumerate story keys for an epic, optionally scoped to one sprint.

    Read-only. A missing epic exits 3 -- absent-vs-empty matters for the caller,
    and the resolver already distinguishes them. A sprint that does not exist
    yields nothing and exits 0: a project can ask about a sprint it has not
    created yet, and the answer is not an error, it is an empty list.

    Filters out sprint.yaml/epic.yaml and anything whose name does not parse as
    a story key -- callers get story keys, no post-processing required.
    """
    if find_epic_dir(args.state_root, args.epic) is None:
        _die_notfound(f"epic {args.epic}")
    sprint = args.sprint if args.sprint else None
    rows = list(iter_story_files(args.state_root, args.epic, sprint))
    if args.format == "json":
        out = []
        for k, _p in rows:
            _e, sk, _ = parse_story_key(k)
            out.append({"key": k, "sprint": sk})
        sys.stdout.write(json.dumps(out) + "\n")
    else:
        for k, _p in rows:
            sys.stdout.write(f"{k}\n")
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
        # Cosmetic wart named in the design (§13): a sprint whose stories are
        # ALL blocked reads as "actively being worked" when its status is
        # still in-progress. Surface it in the header rather than promote it to
        # a status transition (that would need its own transition table).
        header_status = r["status"]
        n_blocked = r.get("blocked_stories", 0)
        if n_blocked and n_blocked == r["story_count"] and r["story_count"] > 0:
            header_status = f"{r['status']} (all {n_blocked} stories blocked)"
        sys.stdout.write(f"{args.epic}/{r['key']}  status={header_status}  "
                         f"stories={r['story_count']}\n")
        for s in r["stories"]:
            suffix = ""
            if s["status"] == "blocked":
                reason = s.get("blocked_reason", "")
                suffix = f"  [blocked: {reason}]" if reason else "  [blocked]"
            sys.stdout.write(f"  {s['key']:<20} {s['status']}{suffix}\n")
        sys.stdout.write(f"  actuals: {_fmt_actuals(r['actual_totals'])}\n")
        _write_spend(r["spend"])
        return 0

    r = rollup_epic(args.state_root, args.epic)
    sys.stdout.write(f"{r['key']}  status={r['status']}  sprints={r['sprint_count']}  "
                     f"stories={r['story_count']}\n")
    for sp in r["sprints"]:
        sys.stdout.write(f"  {sp['key']:<8} status={sp['status']:<12} stories={sp['story_count']}\n")
    sys.stdout.write(f"  actuals: {_fmt_actuals(r['actual_totals'])}\n")
    n_blocked = r.get("blocked_stories", 0)
    if n_blocked > 0:
        cumul = r.get("blocks_seen_cumulative", 0)
        cumul_note = f", {cumul} cumulative block events" if cumul else ""
        sys.stdout.write(f"  blocked_stories: {n_blocked}{cumul_note}\n")
    _write_spend(r["spend"])
    return 0


def cmd_verify(args) -> int:
    kind = args.scope  # story | sprint | epic
    if kind == "epic":
        _y, node, _path, label = _load_checked(args.state_root, args, kind)
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

    _y, node, _path, label = _load_checked(args.state_root, args, kind)

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
                copilot_cost_na = (args.runtime == "copilot" and m == "cost")
                if not copilot_cost_na and (
                    args.require_tokens or args.runtime in ("claude", "codex", "copilot")
                ):
                    problems.append(
                        f"actual.{m}=N/A (forbidden under runtime={args.runtime} "
                        f"/ --require-tokens)")

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
        if args.require_tokens or args.runtime in ("claude", "codex"):
            problems.append(
                f"actual.tokens_k={tk!r} is not the per-class mapping — cost cannot be "
                f"verified against it. Re-capture with set-actual "
                f"--tokens-input/--tokens-output/--tokens-cache-write/--tokens-cache-read "
                f"and --model (metrics-contract.md §3)")

    if kind == "story" and "completion_evidence" not in node:
        problems.append("completion_evidence absent")

    est_model = (node.get("estimate") or {}).get("model")
    act_model = actual.get("model")
    if est_model and act_model and est_model != act_model:
        sys.stdout.write(
            f"WARN {label}: estimate.model={est_model!r} ≠ actual.model={act_model!r}"
            f" — estimate cost denominated in {est_model} rates\n"
        )
    if problems:
        sys.stdout.write(f"FAIL {label}: " + "; ".join(problems) + "\n")
        return 4
    sys.stdout.write(f"PASS {label}\n")
    return 0
