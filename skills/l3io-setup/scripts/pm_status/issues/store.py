"""pm_status.issues.store -- issues.yaml / issues-resolved.yaml and the verbs over them.

The bottom of the `issues` layer: `IssueStore` (both files loaded together under one
`issues_lock`), the key canonicaliser, the issue schema constants, and the append /
resolve / update core. `promote` and `audit` sit above it and nothing here imports either.

`resolve_issue_core` IS A mock.patch TARGET and is deliberately NOT re-exported -- not by
`issues/__init__.py` and not by `__main__.py`. Every caller outside this file reaches it as
`issues.store.resolve_issue_core(...)`, so a `patch.object(pm.issues.store, ...)` is seen by
all of them; a re-exported binding would be a private copy the patch could not reach, and
the test would pass while guarding nothing. Inside this file it is a plain global lookup,
which is exactly what that patch rebinds, so `cmd_resolve_issue` sees it too. Leaving it out
of the re-exports is also what makes a half-done repoint loud: a repoint with a bare call
site left behind is a ruff F821, and a bare patch target with no repoint is an AttributeError.

`IssueStore` is different and is re-exported: the suite patches a CLASS ATTRIBUTE
(`patch.object(pm.IssueStore, "save_open")`), which mutates the one class object every
binding names, so it bites wherever the class is reached.

THE `TYPE_CHECKING` IMPORT BELOW IS LOAD-BEARING AND TRAVELLED HERE WITH `IssueStore`.
Every ruamel import in this package is lazy or guarded (core carries the readable
ModuleNotFoundError message), so `CommentedSeq` is out of scope at module level and an
annotation naming a type mypy cannot resolve degrades SILENTLY to `Any` -- calling `Any` is
permitted, so the `backlog`/`resolved` accessors would type-check nothing and
`check:types`' "not callable" arm would report success over the exact bug it exists for.
`check:types` gates `[name-defined]` for this reason: deleting the import is that error, so
the gate fails instead of going quietly blind. See scripts/check-types.mjs's header.
"""

from __future__ import annotations

import os
import re
import sys
from typing import TYPE_CHECKING

from .. import core
from ..core import (
    PMError,
    _die_usage,
    _norm_num,
    _now_iso,
    _run_core,
    append_event,
    issues_lock,
)

if TYPE_CHECKING:
    from ruamel.yaml.comments import CommentedSeq


_BL_KEY_RE = re.compile(r"^BL-E(\d+)-(\d+)$")


# --------------------------------------------------------------------------- #
# Issue store -- issues.yaml (open items) + issues-resolved.yaml (resolved).
# Spec: docs/superpowers/specs/2026-09-10-issue-lifecycle-design.md; ADR-0002.
# --------------------------------------------------------------------------- #
ISSUES_FILENAME = "issues.yaml"
RESOLVED_FILENAME = "issues-resolved.yaml"
OPEN_ISSUE_STATUSES = ("backlog", "scheduled")
# Statuses the PRE-3.0 schema used for an open item, mapped to their current equivalent.
# `deferred` was that schema's resting state for a deliberate deferral -- open, unscheduled --
# which is exactly `backlog` now. A project upgrading with a legacy backlog otherwise gets one
# undifferentiated 1f per item (453 on a real one) whose repair text is "report only", so
# triage reports everything and can act on nothing. Mapping to a RESOLVED state instead would
# be a judgement, not a migration, so it is deliberately not done here.
LEGACY_OPEN_STATUSES = {"deferred": "backlog"}


RESOLUTIONS = ("fixed", "wontfix", "duplicate", "obsolete", "deferred")
# A backlog item's kind. `defect` is the default and is never written, so every file written
# before kinds existed still reads as all defects. The spec kinds come from spec-align.py's
# spec sync (docs/adr/0004-agents-edit-architecture-specs.md): they are confirmed or
# rejected in doctor triage, never promoted to a story.
ISSUE_KINDS = ("defect", "spec-change", "spec-proposal")
SPEC_ISSUE_KINDS = ISSUE_KINDS[1:]
SEVERITY_RANK = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}


def _int_or_none(v):
    if isinstance(v, bool):
        return None
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def canonical_bl_key(key):
    """'BL-E1-2' -> 'BL-E001-002'. None when the key cannot be written canonically."""
    m = _BL_KEY_RE.match(str(key).strip())
    if not m:
        return None
    epic, n = int(m.group(1)), int(m.group(2))
    if epic > 999 or n > 999 or n < 1:
        return None
    return f"BL-E{epic:03d}-{n:03d}"


def issues_paths(state_root: str) -> tuple:
    return (os.path.join(state_root, ISSUES_FILENAME),
            os.path.join(state_root, RESOLVED_FILENAME))


def _remove_identity(lst, obj) -> None:
    """Remove `obj` itself -- not an equal mapping -- from a list."""
    for i, x in enumerate(lst):
        if x is obj:
            del lst[i]
            return


class IssueStore:
    """Both issue files, loaded together. The caller holds issues_lock(open_path)
    across the whole load -> mutate -> save cycle; the resolved file lives beside
    the open one, so one lock covers both."""

    def __init__(self, open_path: str):
        from ruamel.yaml.comments import CommentedMap, CommentedSeq
        self.open_path = open_path
        self.state_root = os.path.dirname(os.path.abspath(open_path))
        self.resolved_path = os.path.join(self.state_root, RESOLVED_FILENAME)
        self.y, self.open = core._load(open_path)
        self.yr, self.res = core._load(self.resolved_path)
        if self.open is None:
            self.open = CommentedMap()
        if self.open.get("backlog") is None:
            self.open["backlog"] = CommentedSeq()
        if self.res is None:
            self.res = CommentedMap()
        if self.res.get("resolved") is None:
            self.res["resolved"] = CommentedSeq()
        for name, lst, path in (("backlog", self.open["backlog"], open_path),
                                ("resolved", self.res["resolved"], self.resolved_path)):
            if not isinstance(lst, list):
                raise PMError(2, f"{path} has a malformed '{name}' field (expected a list, "
                                 f"got {type(lst).__name__}: {lst!r}); refusing to write -- "
                                 f"a list that cannot say what is recorded cannot be trusted "
                                 f"to receive more. Fix or restore it by hand, then retry.")

    # Annotated so reading these as methods -- `store.backlog()` -- is a type error rather
    # than a runtime TypeError. The annotations only bind because of the TYPE_CHECKING
    # import at the top of this file; without it they resolve to `Any` and check nothing.
    @property
    def backlog(self) -> CommentedSeq:
        return self.open["backlog"]

    @property
    def resolved(self) -> CommentedSeq:
        return self.res["resolved"]

    @staticmethod
    def _matching(lst, key):
        return [i for i in lst if isinstance(i, dict) and str(i.get("key", "")) == key]

    def open_items(self, key):
        return self._matching(self.backlog, key)

    def resolved_items(self, key):
        return self._matching(self.resolved, key)

    def single_open(self, key):
        """The one open item with this key, or None. PMError(2) when the key appears
        more than once -- no verb may act on an ambiguous key (audit-issues 1i)."""
        opens = self.open_items(key)
        if len(opens) > 1:
            raise PMError(2, f"{key} appears {len(opens)} times in {self.open_path} -- "
                             f"resolve it by hand (audit-issues finding 1i)")
        return opens[0] if opens else None

    def highest_suffix(self, epic_norm: str) -> int:
        highest = 0
        for item in list(self.backlog) + list(self.resolved):
            if not isinstance(item, dict):
                continue
            m = _BL_KEY_RE.match(str(item.get("key", "")))
            if m and _norm_num(m.group(1), 3) == epic_norm:
                highest = max(highest, int(m.group(2)))
        return highest

    def stored_next(self, epic_norm: str):
        nxt = self.open.get("next")
        if not isinstance(nxt, dict) or epic_norm not in nxt:
            return None
        n = _int_or_none(nxt.get(epic_norm))
        if n is None:
            sys.stderr.write(f"pm-status.py: warning -- next[{epic_norm!r}] = "
                             f"{nxt.get(epic_norm)!r} is not an integer; ignoring it\n")
        return n

    def _next_map(self):
        from ruamel.yaml.comments import CommentedMap
        nxt = self.open.get("next")
        if nxt is not None and not isinstance(nxt, dict):
            sys.stderr.write(f"pm-status.py: warning -- {self.open_path} has a malformed "
                             f"'next' ({nxt!r}); rebuilding it from the highest keys\n")
            nxt = None
        if nxt is None:
            nxt = CommentedMap()
            if "next" in self.open:
                self.open["next"] = nxt
            else:
                self.open.insert(0, "next", nxt)
        return nxt

    def raise_next(self, epic_norm: str, at_least: int) -> None:
        """`next` never decreases: store max(what is stored, at_least)."""
        stored = self.stored_next(epic_norm)
        self._next_map()[epic_norm] = max(stored or 0, at_least)

    def allocate(self, epic_norm: str) -> str:
        n = max(self.stored_next(epic_norm) or 1, self.highest_suffix(epic_norm) + 1)
        if n > 999:
            raise PMError(2, f"epic {epic_norm} has used every backlog key: BL-E{epic_norm}-999 "
                             f"is the last a three-digit suffix can name, and keys are never "
                             f"reused -- nothing written")
        self.raise_next(epic_norm, n + 1)
        return f"BL-E{epic_norm}-{n:03d}"

    def save_open(self) -> None:
        core._atomic_dump(self.y, self.open, self.open_path)

    def save_resolved(self) -> None:
        core._atomic_dump(self.yr, self.res, self.resolved_path)


def _issue_event(state_root, event, item, session=None, cause="cli", **fields) -> None:
    payload = {"ts": _now_iso(), "event": event, "key": str(item.get("key", "")),
               "epic": str(item.get("epic", "")), "session": session, "cause": cause}
    payload.update(fields)
    append_event(state_root, payload)


def _norm_issue_title(title) -> str:
    """Strip, collapse internal whitespace, and casefold -- for duplicate MATCHING
    only. The stored title is never rewritten to this normalized form."""
    return " ".join(str(title).split()).casefold()


SOURCE_PHASE_RE = re.compile(r"^[A-Za-z][\w-]*$")


def resolve_source(args):
    """Return (source_string, phase, ref) for an append-issue call.

    `--source` is free text stored verbatim and validated nowhere, and it is the only link an
    issue has back to the artifact that raised it. A real backlog grew 100+ distinct shapes,
    and audit-backlog.py accumulated five regexes trying to read them -- every one of which
    has been wrong about some shape. This package's own step-03-dev-loop.md even emits a
    source its own primary reader rejects, surviving only because an earlier regex uses
    .search rather than .match.

    So the structured form DERIVES the string rather than sitting beside it: a caller cannot
    produce a phase/ref pair that disagrees with the text, because it does not write the text.
    Validation here guarantees the result parses as `{phase} ({ref})`, which is the invariant
    the readers depend on.

    `--source` stays accepted and stored byte-for-byte: _content_matches compares it exactly
    as one of four duplicate-detection keys, deliberately, because over-matching loses a real
    finding.
    """
    raw = getattr(args, "source", None)
    phase = getattr(args, "source_phase", None)
    ref = getattr(args, "source_ref", None)
    note = getattr(args, "source_note", "") or ""

    if raw and phase:
        _die_usage("--source and --source-phase are alternatives -- pass one, not both")
    if not raw and not phase:
        _die_usage("append-issue needs --source, or --source-phase with --source-ref")
    if note and not phase:
        _die_usage("--source-note applies only to --source-phase")
    if raw:
        return raw, None, None

    if not ref:
        _die_usage("--source-phase requires --source-ref")
    if not SOURCE_PHASE_RE.match(phase):
        _die_usage(f"--source-phase {phase!r} must match {SOURCE_PHASE_RE.pattern} -- the "
                   f"derived source has to parse as '{{phase}} ({{ref}})', which a space or a "
                   f"punctuation character breaks")
    if "(" in ref or ")" in ref:
        _die_usage(f"--source-ref {ref!r} must not contain parentheses -- they delimit the ref "
                   f"in the derived source string")

    derived = f"{phase} ({ref})" + (f" — {note}" if note else "")
    return derived, phase, ref


def _content_matches(item, epic_norm: str, sprint_norm: str, source: str, norm_title: str) -> bool:

    return (isinstance(item, dict)
            and _norm_num(item.get("epic", ""), 3) == epic_norm
            and _norm_num(item.get("sprint", "") or "", 2) == sprint_norm
            and str(item.get("source", "")) == source
            and _norm_issue_title(item.get("title", "")) == norm_title)


def _find_issue_by_content(backlog, epic_norm: str, sprint_norm: str, source: str, norm_title: str):
    """Match on all four of normalized title + epic + sprint + source, deliberately.
    Over-matching (e.g. title alone) loses a real finding; under-matching leaves
    noise. Losing data is the worse failure, so this only catches near-certain
    repeats -- a re-run of the same story re-deferring the same finding."""
    for item in backlog:
        if _content_matches(item, epic_norm, sprint_norm, source, norm_title):
            return item
    return None


def _last_resolved_match(resolved, epic_norm, sprint_norm, source, norm_title):
    """The NEWEST resolved item with the same content. issues-resolved.yaml is appended
    in resolution order, so the last match is the newest."""
    hits = [r for r in resolved if _content_matches(r, epic_norm, sprint_norm, source, norm_title)]
    return hits[-1] if hits else None


def cmd_append_issue(args) -> int:
    """Append a BL item to the backlog list in state/issues.yaml.

    The whole load -> allocate-key -> dedupe-check -> mutate -> save cycle runs
    under one exclusive lock (`issues_lock`): `issues.yaml` is a shared append
    target across every epic and every parallel subagent, and locking only the
    write (as this used to) lets two concurrent callers read the same pre-write
    backlog, allocate the same next number, and have the second save silently
    drop the first's item -- the same collision class production ADR numbers
    hit (three parallel agents, one directory listing, two agents each picking
    0013 and 0014).

    `--key` is optional. Omitted, the next number for `--epic` is allocated
    here (never by the caller -- nothing bound `{nnn}` anywhere, which is
    exactly how two callers used to invent the same one). Given, and it
    already names an existing item, that is refused (exit 2) rather than
    silently renumbered: a caller naming a key means it. Either way, a content
    duplicate (same normalized title + epic + sprint + source) is skipped --
    the caller's desired end state, "this finding is recorded", already holds
    -- unless `--allow-duplicate` forces a second entry.

    Keys come from `IssueStore.allocate`: `max(next[epic], highest suffix in
    either issue file + 1)`, so a deleted or resolved item's key is never
    handed out again.
    """
    return _run_core(lambda: _append_issue(args))


def _issues_open_path(args) -> str:
    """The open issues file from --state-root, or from --file (compatibility)."""
    sr = getattr(args, "state_root", "") or ""
    f = getattr(args, "file", "") or ""
    if sr:
        p = issues_paths(sr)[0]
        if f and os.path.abspath(f) != os.path.abspath(p):
            raise PMError(2, f"append-issue: --file {f} is not {p} -- pass --state-root "
                             f"alone (--file is kept only for compatibility)")
        return p
    if f:
        return f
    raise PMError(2, "append-issue: pass --state-root (or, for compatibility, --file)")


def _append_issue(args) -> int:
    from ruamel.yaml.comments import CommentedMap
    # Resolved before the lock: a usage error should not hold issues.yaml while it exits.
    source_str, source_phase, source_ref = resolve_source(args)
    open_path = _issues_open_path(args)
    epic_norm = _norm_num(args.epic, 3)
    sprint_norm = _norm_num(args.sprint, 2) if args.sprint else ""
    norm_title = _norm_issue_title(args.title)
    kind = getattr(args, "kind", None) or "defect"
    ref = (getattr(args, "ref", None) or "").strip()
    if kind in SPEC_ISSUE_KINDS and not ref:
        raise PMError(2, f"append-issue: --kind {kind} needs --ref (the docs(spec) commit SHA, "
                         f"or the proposal file's path)")
    if kind == "spec-change" and not _SHA_RE.match(ref):
        raise PMError(2, f"append-issue: --kind spec-change needs --ref to be a commit SHA, "
                         f"not {ref!r}")
    explicit = None
    if args.key:
        explicit = canonical_bl_key(args.key)
        if explicit is None:
            raise PMError(2, f"append-issue: --key {args.key!r} is not a backlog key "
                             f"(expected BL-E{{nnn}}-{{nnn}})")
        if explicit[4:7] != epic_norm:
            raise PMError(2, f"append-issue: --key {explicit} belongs to epic "
                             f"{explicit[4:7]}, not --epic {epic_norm}")
    with issues_lock(open_path, bare_file=not (getattr(args, "state_root", "") or "")):
        store = IssueStore(open_path)
        if explicit is not None:
            clash = store.open_items(explicit) + store.resolved_items(explicit)
            if clash:
                raise PMError(2, f"append-issue: --key {explicit!r} already exists "
                                 f"(title: {clash[0].get('title', '')!r}) -- refusing to "
                                 f"silently assign a different key; pick a key that is not "
                                 f"already taken, or omit --key to auto-allocate the next "
                                 f"one for this epic")
        note = ""
        if not args.allow_duplicate:
            dup = _find_issue_by_content(store.backlog, epic_norm, sprint_norm,
                                         source_str, norm_title)
            if dup is not None:
                sys.stdout.write(
                    f"OK append-issue skipped -- matches existing {dup.get('key', '')} "
                    f"(same title/epic/sprint/source); nothing written. Pass "
                    f"--allow-duplicate to force a second entry.\n")
                return 0
            prior = _last_resolved_match(store.resolved, epic_norm, sprint_norm,
                                         source_str, norm_title)
            if prior is not None:
                res, psev = str(prior.get("resolution", "")), str(prior.get("severity", ""))
                if res == "fixed":
                    note = f" (recurrence of {prior.get('key')})"
                elif SEVERITY_RANK.get(args.severity, 0) > SEVERITY_RANK.get(psev, 0):
                    note = f" (re-raised above {prior.get('key')} {res} at {psev})"
                else:
                    sys.stdout.write(
                        f"OK append-issue skipped -- matches {prior.get('key')} resolved as "
                        f"{res} (severity {psev}); nothing written. Pass --allow-duplicate "
                        f"to force a second entry.\n")
                    return 0
        if explicit is not None:
            key = explicit
            store.raise_next(epic_norm, int(explicit[-3:]) + 1)
        else:
            key = store.allocate(epic_norm)
        item = CommentedMap()
        item["key"] = key
        # epic_norm/sprint_norm, not args.*: both are computed at the top of this function
        # and already trusted for the key, the --key cross-check, dedupe matching and
        # store.allocate(). Storing the caller's spelling instead let one epic appear as
        # '3', '03', '003', 'E3', 'E003' and 'e003' in one file -- all six accepted, all
        # six producing the same correct key.
        item["epic"] = epic_norm
        item["sprint"] = sprint_norm
        item["title"] = args.title
        item["source"] = source_str
        if source_phase:
            item["source_phase"] = source_phase
            item["source_ref"] = source_ref
        item["severity"] = args.severity
        item["status"] = "backlog"
        if kind != "defect":
            item["kind"] = kind
        if ref:
            item["ref"] = ref
        if args.description:
            item["description"] = args.description
        store.backlog.append(item)
        store.save_open()
    _issue_event(store.state_root, "issue_opened", item,
                 getattr(args, "session_id", None), "cli", severity=args.severity)
    sys.stdout.write(f"OK append-issue {key} -> {open_path}{note}\n")
    return 0


_STORY_KEY_RE = re.compile(r"^E\d{3}-S\d{2}-\d{3}$")
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")

# The backlog fields holding a STORY key, and so the fields a re-key invalidates: `story`
# (an open item's scheduling target, copied through to its resolved entry) and `ref` (what
# resolved it). `ref` is overloaded -- on a spec-change/spec-proposal item it is a commit
# SHA or a proposal path -- so every reader must match _STORY_KEY_RE before treating a
# value as a story pointer. `story` is named first in messages: its loss costs more.
STORY_REF_FIELDS = ("story", "ref")


def _validate_resolution_flags(resolution, ref, note) -> None:
    # DEFENSIVE, and unreachable from every current caller -- do not write a fixture for it.
    # argparse constrains --resolution to `choices=list(RESOLUTIONS)`, and the two in-process
    # callers pass the literals "fixed" and "deferred". It guards the next caller, which is a
    # real risk here because resolve_issue_core is invoked internally as well as from the CLI.
    if resolution not in RESOLUTIONS:
        raise PMError(2, f"--resolution must be one of {', '.join(RESOLUTIONS)}")
    if resolution == "fixed":
        if not ref:
            raise PMError(2, "--resolution fixed needs --ref (a story key or a commit SHA)")
        if not (_STORY_KEY_RE.match(ref) or _SHA_RE.match(ref)):
            raise PMError(2, f"--ref {ref!r} is neither a story key (E{{nnn}}-S{{nn}}-{{nnn}}) "
                             f"nor a commit SHA")
    elif resolution == "duplicate":
        if not ref:
            raise PMError(2, "--resolution duplicate needs --ref naming the surviving BL key")
    elif not (note or "").strip():
        raise PMError(2, f"--resolution {resolution} needs --note saying why")


def resolve_issue_core(store, key, resolution, ref=None, note=None,
                       session=None, cause="cli") -> str:
    """Resolve one open item. The caller holds issues_lock(store.open_path).

    Order is the contract (spec §2.2): a key already in the resolved file has any
    stale open copy removed BEFORE the idempotent return, so a crash between the
    two writes below is always cleared by a rerun; otherwise the item is appended
    to the resolved file first and removed from the open file second, so a crash
    can duplicate it but never lose it."""
    from ruamel.yaml.comments import CommentedMap
    _validate_resolution_flags(resolution, ref, note)
    k = canonical_bl_key(key)
    if k is None:
        raise PMError(2, f"{key!r} is not a backlog key")
    item, done = store.single_open(k), store.resolved_items(k)
    if done:
        prior = done[-1].get("resolution")
        if item is not None:
            _remove_identity(store.backlog, item)
            store.save_open()
            return f"{k} already resolved ({prior}); removed the stale open copy"
        return f"{k} already resolved ({prior})"
    if item is None:
        raise PMError(3, f"{k} is in neither {store.open_path} nor {store.resolved_path}")
    if resolution == "duplicate":
        r = canonical_bl_key(ref)
        if r is None or r == k:
            raise PMError(2, f"--ref {ref!r} must name a different BL key")
        t_open, t_res = store.open_items(r), store.resolved_items(r)
        if not t_open and not t_res:
            raise PMError(2, f"--ref {r} does not exist")
        if not t_open and all(str(t.get("resolution")) == "duplicate" for t in t_res):
            raise PMError(2, f"--ref {r} is itself resolved as a duplicate -- point at the "
                             f"item it duplicates")
        ref = r
    entry = CommentedMap()
    for kk, vv in item.items():
        entry[kk] = vv
    entry["status"] = "resolved"
    entry["resolution"] = resolution
    entry["resolved_at"] = _now_iso()
    if ref:
        entry["ref"] = ref
    if note:
        entry["note"] = note
    store.resolved.append(entry)
    store.save_resolved()
    _remove_identity(store.backlog, item)
    store.save_open()
    _issue_event(store.state_root, "issue_resolved", entry, session, cause,
                 resolution=resolution, ref=ref)
    tail = ""
    if str(item.get("status")) == "scheduled" and cause != "set-status":
        tail = f"; story {item.get('story')} still lists it in resolves"
    return f"{k} ({resolution}{', ref ' + ref if ref else ''}){tail}"


def cmd_resolve_issue(args) -> int:
    def run():
        open_path = issues_paths(args.state_root)[0]
        with issues_lock(open_path):
            msg = resolve_issue_core(IssueStore(open_path), args.key, args.resolution,
                                     args.ref, args.note, args.session_id, args.cause)
        sys.stdout.write(f"OK resolve-issue {msg}\n")
        return 0
    return _run_core(run)


def update_issue_core(store, key, severity, note=None, session=None, cause="cli") -> str:
    """Change an open item's severity. The caller holds issues_lock(store.open_path)."""
    k = canonical_bl_key(key)
    if k is None:
        raise PMError(2, f"{key!r} is not a backlog key")
    done = store.resolved_items(k)
    if done:
        raise PMError(2, f"{k} is resolved ({done[-1].get('resolution')}) -- only open "
                         f"items can be re-severitied")
    item = store.single_open(k)
    if item is None:
        raise PMError(3, f"{k} is in neither {store.open_path} nor {store.resolved_path}")
    before = str(item.get("severity", ""))
    if before == severity:
        # No change is not an update: no save, and no issue_updated event with from == to.
        # A --note lives only in that event, so say it was dropped rather than drop it silently.
        return (f"{k} severity {severity} unchanged"
                f"{' (note not recorded)' if note is not None else ''}")
    item["severity"] = severity
    store.save_open()
    _issue_event(store.state_root, "issue_updated", item, session, cause,
                 **{"from": before, "to": severity, "note": note})
    return f"{k} severity {before} -> {severity}"


def cmd_update_issue(args) -> int:
    def run():
        open_path = issues_paths(args.state_root)[0]
        with issues_lock(open_path):
            msg = update_issue_core(IssueStore(open_path), args.key, args.severity,
                                    args.note, args.session_id, args.cause)
        sys.stdout.write(f"OK update-issue {msg}\n")
        return 0
    return _run_core(run)
