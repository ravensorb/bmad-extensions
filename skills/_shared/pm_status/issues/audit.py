"""pm_status.issues.audit -- audit-issues, repair-issue, the legacy normalisers, list-issues.

The integrity layer over the issue store: `_audit_findings` enumerates every finding class
(1a..1l), `_repair_issue` performs the one repair a finding names, and the normalisers
rewrite a pre-3.0 file into the current schema. `/l3io-doctor triage` is the consumer.

The top of the `issues` layer -- it imports `store`, `promote` and `adr`, and nothing in
the bucket imports it.

`resolve_issue_core` is reached as `store.resolve_issue_core(...)`, never imported by name:
it is a mock.patch target, and a by-name import here would be a private copy a patch on
`pm.issues.store` could not reach. See store.py's header.
"""

from __future__ import annotations

import json
import os
import sys

from .. import core
from ..core import (
    PMError,
    _norm_num,
    _now_iso,
    _run_core,
    adr_register_lock,
    adr_register_path,
    canonical_epic_key,
    issues_lock,
)
from ..nodes import find_epic_dir

# `store` is a PARAMETER NAME all over this file -- an IssueStore instance -- so the module
# cannot be bound under its own name here: inside `_normalize_one_legacy(store, ...)` the
# parameter shadows it and `store.resolve_issue_core` becomes an attribute lookup on an
# IssueStore, i.e. an AttributeError at the one call site that needs the module. Bound under
# a name nothing shadows instead. It is the SAME module object, so
# `patch.object(pm.issues.store, "resolve_issue_core")` is seen through it -- which is the
# whole point of reaching it through a module rather than importing the name.
from . import store as store_module
from .adr import load_adr_register
from .promote import _dead_claim, _walk_story_nodes
from .store import (
    _STORY_KEY_RE,
    ISSUE_KINDS,
    ISSUES_FILENAME,
    LEGACY_OPEN_STATUSES,
    OPEN_ISSUE_STATUSES,
    RESOLVED_FILENAME,
    SPEC_ISSUE_KINDS,
    STORY_REF_FIELDS,
    IssueStore,
    _int_or_none,
    _issue_event,
    _remove_identity,
    canonical_bl_key,
    issues_paths,
)

# BL keys run 001-999, so next[epic] -- the NEXT key to hand out -- is at most 1000.
_BL_NEXT_MAX = 1000


def _stale_story_refs(item, stories, moved) -> list:
    """The (field, old_key, new_key | None) triples on one backlog item whose story key no
    longer exists AND is recorded in some story's `previous_keys`. `new_key` is that story
    when exactly one records it, and None when more than one does (ambiguous: reported,
    never guessed at).

    A dangling key that NO story records is deliberately not reported here: that is the
    ordinary shape of a story whose directory was removed or whose epic was retired, no
    verb here can repair it, and the one actionable case -- an open item scheduled to a
    story that no longer exists -- is finding 1b, whose `unschedule` repair is correct
    precisely because there is no key to point at instead.

    A field is only considered when its value PARSES as a story key: `ref` also carries a
    commit SHA or a proposal path for a spec-change item, and neither is a broken pointer.
    A key that still names a live story is never stale -- including the case where the key
    was re-issued to different work, which reads as resolved and is indistinguishable from
    here. The allocator's high-water is what prevents that, not this check.
    """
    out = []
    for field in STORY_REF_FIELDS:
        v = str(item.get(field) or "")
        if not _STORY_KEY_RE.match(v) or v in stories:
            continue
        heirs = moved.get(v, [])
        if heirs:
            out.append((field, v, heirs[0] if len(heirs) == 1 else None))
    return out


def _story_index(state_root):
    """One walk of every story node, as the four maps the backlog checks read.

    stories: key -> (status folder, status).
    claims:  BL key -> every story listing it in `resolves` (1b and 1j read it).
    live:    the same minus dead claims (`_dead_claim`) -- 1d and 1h read only live claims,
             so the 1g repair leaves a clean audit.
    moved:   old story key -> the stories that now carry it in `previous_keys`, which is how
             a reference orphaned by reparent-story is told apart from one that never
             resolved at all (1l).
    """
    stories, claims, live, moved = {}, {}, {}, {}
    for skey, sdir, node, _ in _walk_story_nodes(state_root):
        stories[skey] = (sdir, str(node.get("status", "")))
        dead = _dead_claim(sdir, node)
        for k in node.get("resolves") or []:
            claims.setdefault(str(k), []).append(skey)
            if not dead:
                live.setdefault(str(k), []).append(skey)
        for pk in node.get("previous_keys") or []:
            moved.setdefault(str(pk), []).append(skey)
    return stories, claims, live, moved


def _story_key_maps(state_root):
    """`(stories, moved)` -- the two maps `_stale_story_refs` needs. The repoint repair
    re-derives them from the same walk audit-issues used, so the gate and the write can
    never disagree about which story carries an old key."""
    stories, _claims, _live, moved = _story_index(state_root)
    return stories, moved


def _audit_findings(state_root, store) -> list:
    """Structural integrity findings 1a-1l (spec §3.1). The caller holds issues_lock."""
    findings = []

    def add(fid, key, detail, repair, story=None, epic=None):
        findings.append({"id": fid, "key": key, "story": story, "epic": epic,
                         "detail": detail, "repair": repair})

    stories, claims, live, moved = _story_index(state_root)
    open_by, res_by = {}, {}
    for lst, by in ((store.backlog, open_by), (store.resolved, res_by)):
        for it in lst:
            if isinstance(it, dict):
                by.setdefault(str(it.get("key", "")), []).append(it)

    for by, fname in ((open_by, ISSUES_FILENAME), (res_by, RESOLVED_FILENAME)):
        for k, its in by.items():
            if len(its) > 1:
                add("1i", k, f"appears {len(its)} times in {fname}",
                    "report only -- rekey or merge by hand")
            elif canonical_bl_key(k) != k:
                add("1i", k, f"non-canonical key in {fname}", "report only -- rekey by hand")
    for k in open_by:
        if k in res_by:
            add("1a", k, "present in both issue files",
                "resolve-issue rerun -- it clears the open copy")

    # 1l -- a story-key field pointing at a key a re-key moved. Computed before the loops
    # below because 1b defers to it: a scheduled item with a repointable heir must be
    # repointed, and 1b's `unschedule` would discard the scheduling instead. A dangling key
    # no story records is not 1l at all (see `_stale_story_refs`), so 1b still owns every
    # case where unschedule is the right answer.
    stale = {}
    for by, fname in ((open_by, ISSUES_FILENAME), (res_by, RESOLVED_FILENAME)):
        for k, its in by.items():
            if len(its) != 1:
                continue        # 1i: an ambiguous key is never evaluated
            if by is open_by and k in res_by:
                continue        # Ruling 8, resolved first: the open copy is 1a, and the
                                # rerun that clears it would discard any repoint done here
            for fld, old, new in _stale_story_refs(its[0], stories, moved):
                stale.setdefault(k, []).append((fld, old, new, fname))
    for k in sorted(stale):
        for fld, old, new, fname in stale[k]:
            if new is not None:
                add("1l", k, f"{fld}: {old} in {fname} names no story; {new} records it in "
                             f"previous_keys (it was re-keyed by reparent-story)",
                    f"repair-issue --action repoint --key {k}", story=new)
            else:
                add("1l", k, f"{fld}: {old} in {fname} names no story, and {len(moved[old])} "
                             f"stories record it in previous_keys "
                             f"({', '.join(sorted(moved[old]))})",
                    "report only -- which story this means is not derivable; the duplicate "
                    "previous_keys entry is the defect, so fix that and rerun repoint")

    def repointable(k) -> bool:
        return any(f == "story" and n is not None for f, _o, n, _fn in stale.get(k, []))

    for k in open_by:
        if k in res_by:
            continue            # Ruling 8, resolved first: the stale open copy is 1a only
        try:
            it = store.single_open(k)
        except PMError:
            continue            # 1i (reported above): an ambiguous key is never evaluated
        st = str(it.get("status", ""))
        if st in LEGACY_OPEN_STATUSES:
            add("1f", k, f"open item has legacy status {st!r} (pre-3.0 resting state)",
                f"run: pm-status.py repair-issue --state-root S --key {k} "
                f"--action normalize-status  # -> {LEGACY_OPEN_STATUSES[st]}")
        elif st not in OPEN_ISSUE_STATUSES:
            add("1f", k, f"open item has status {st!r}", "report only")
        kind = it.get("kind")
        if kind is not None and str(kind) not in ISSUE_KINDS:
            add("1k", k, f"unknown kind {kind!r}", "report only -- fix the kind by hand")
        elif str(kind) in SPEC_ISSUE_KINDS and not str(it.get("ref") or "").strip():
            add("1k", k, f"{kind} item has no ref",
                "report only -- add the commit SHA or the proposal path by hand")
        if st == "scheduled" and repointable(k):
            pass                # 1l owns it: repoint, do not unschedule
        elif st == "scheduled":
            sk = str(it.get("story", "") or "")
            if sk not in stories or sk not in claims.get(k, []):
                add("1b", k, f"scheduled to {sk or '(none)'}, which is missing or does not "
                             f"list it", "repair-issue --action unschedule", story=sk or None)
            elif stories[sk][0] == "archived" and stories[sk][1] != "done":
                add("1g", k, f"scheduled to {sk}, which is archived and not done",
                    "repair-issue --action unschedule", story=sk)
    for k, sks in claims.items():
        lsks = live.get(k, [])
        if len(lsks) > 1:
            add("1h", k, f"listed in resolves of {', '.join(lsks)}",
                "report only -- decide which story owns it")
        if k not in open_by and k not in res_by:
            add("1b", k, f"named in resolves of {', '.join(sks)} but in neither issue file",
                "report only -- remove it from resolves by hand", story=sks[0])
            continue
        if k not in open_by or k in res_by:     # Ruling 8: resolved first
            continue
        try:
            it = store.single_open(k)
        except PMError:
            continue                            # 1i: an ambiguous key is never evaluated
        for sk in lsks:
            if sk not in stories:
                continue
            if stories[sk][1] == "done":
                add("1c", k, f"story {sk} is done but {k} is still open",
                    f"resolve-issue --key {k} --resolution fixed --ref {sk}", story=sk)
            elif str(it.get("status", "")) == "backlog":
                add("1d", k, f"story {sk} lists {k}, which is still backlog",
                    f"repair-issue --action link --story {sk}", story=sk)
    nxt = store.open.get("next")
    by_hand = f"fix it by hand; reseed refuses a value above {_BL_NEXT_MAX}"
    hand_fix = f"report only -- {by_hand}"
    if nxt is not None and not isinstance(nxt, dict):
        add("1e", "next", f"next is malformed ({nxt!r})", "repair-issue --action reseed")
    elif nxt:
        # Sort on the normalised epic: a hand-edited unquoted key (`1: 5`) is an int, and
        # sorting it against the string keys raised TypeError.
        for e in sorted(nxt, key=lambda e: (_norm_num(str(e), 3), str(e))):
            en = _norm_num(str(e), 3)
            stored, highest = _int_or_none(nxt.get(e)), store.highest_suffix(en)
            beyond = stored is not None and stored > _BL_NEXT_MAX
            if e != en:
                # User decision: allocate reads only the canonical key, so an alias (`1` or
                # '1' for '001') is 1e whatever its value; reseed folds it in by max -- except
                # past the key space, which reseed refuses (exit 2), so that alias gets the
                # same hand-fix repair as its key-space finding below, not a reseed it can't run.
                advice = by_hand if beyond else "run repair-issue --action reseed"
                # Name the raw bytes, not just the parsed key. The parsed key can differ
                # from what is in the file in two ways at once -- an unquoted `019` loads
                # as `19`, losing both the quoting AND the leading zero -- so an operator
                # shown only `19` goes looking for a writer that emits integers and finds
                # none. The usual cause is an external YAML round-trip rather than any
                # pm-status verb: PyYAML's safe_dump quotes `001`-`007` and `012`, whose
                # digits resolve as octal, but emits `008`, `009`, `018`, `019` bare
                # because 8 and 9 are not octal digits -- so a project can round-trip this
                # file for weeks and only corrupt the epics with an 8 or 9 behind the
                # leading zero. Cost a consumer project a wrongly-filed defect against
                # append-issue, which normalises correctly in every spelling.
                add("1e", f"BL-E{en}", f"next has a non-canonical key {e!r} for epic {en} "
                                      f"(= {nxt.get(e)!r}); allocate reads only the quoted "
                                      f"{en!r}. Check the raw bytes -- a bare (unquoted) "
                                      f"{en} in the file parses as {e!r}, and an external "
                                      f"YAML round-trip is a likelier cause than any "
                                      f"pm-status write -- {advice}",
                    hand_fix if beyond else "repair-issue --action reseed", epic=en)
            elif stored is None or stored <= highest:
                add("1e", f"BL-E{en}", f"next[{e}] = {nxt.get(e)!r} but the highest key is "
                                      f"{highest:03d}", "repair-issue --action reseed", epic=en)
            if beyond:
                add("1e", f"BL-E{en}", f"next[{e!r}] = {stored} exceeds the BL key space (keys "
                                      f"stop at 999, so next is at most {_BL_NEXT_MAX})",
                    hand_fix, epic=en)
    for k, its in res_by.items():
        it = its[-1]
        ref = str(it.get("ref", "") or "")
        # Only a ref story whose resolves: lists the key: a legitimate `--ref <story in
        # progress>` never claimed it, and reopening it would manufacture a 1b.
        if (str(it.get("resolution")) == "fixed" and ref in stories
                and stories[ref][1] != "done" and ref in claims.get(k, [])):
            add("1j", k, f"resolved fixed by {ref}, which is now {stories[ref][1]!r}",
                "repair-issue --action reopen", story=ref)
    return findings


def cmd_audit_issues(args) -> int:
    """Structural integrity of the backlog (spec §3.1). Read-only. Both issue files are
    read under issues_lock whenever either one exists, so a concurrent resolve cannot
    fake a finding. When neither exists, no lock is taken -- a read-only command must
    not create issues.yaml.lock -- and the story walk still runs, unlocked, over an
    empty store, so finding 1b can still report a resolves: key that names neither
    file. Exit 4 when anything is found. A malformed issue file, or a story node that
    does not parse, is not valid UTF-8 or is not a mapping (Rulings F1/F4: the existing
    channel, not a new finding id), also exits 4; under
    --format json it still prints a parseable document, {"findings": [], "error": MSG},
    because triage and the health check parse it. Heuristic checks live in
    l3io-doctor/scripts/audit-backlog.py."""
    findings = []
    open_path, res_path = issues_paths(args.state_root)
    try:
        if os.path.exists(open_path) or os.path.exists(res_path):
            with issues_lock(open_path):
                findings = _audit_findings(args.state_root, IssueStore(open_path))
        elif os.path.isdir(args.state_root):
            findings = _audit_findings(args.state_root, IssueStore(open_path))
    except PMError as e:
        sys.stderr.write(f"pm-status.py: {e.msg}\n")
        if args.format == "json":   # triage T2 and health-check Check 13 parse this document
            sys.stdout.write(json.dumps({"findings": [], "error": e.msg}, indent=2) + "\n")
        return 4
    if args.format == "json":
        sys.stdout.write(json.dumps({"findings": findings}, indent=2) + "\n")
    elif not findings:
        sys.stdout.write("audit-issues: no integrity findings\n")
    else:
        for f in findings:
            sys.stdout.write(f"{f['id']}  {f['key']}  {f['detail']}\n"
                             f"      repair: {f['repair']}\n")
    return 4 if findings else 0


def cmd_repair_issue(args) -> int:
    """Narrow structural repairs (spec §3.4). Each action refuses (exit 2) unless its
    audit finding holds for --key, so it can only move the backlog toward a state
    audit-issues accepts -- never invent one it would flag. `unschedule` and `link` act on
    an open item, so they also refuse a key with a resolved entry (Ruling 8, resolved
    first): a stale open copy is finding 1a, cleared by a resolve-issue rerun. `repoint`
    acts on whichever file holds the item -- the resolved entry when there is one, for the
    same reason: repointing an open copy a resolve-issue rerun is about to delete is work
    thrown away."""
    return _run_core(lambda: _repair_issue(args))


def _epic_is_archived(state_root, item) -> bool | None:
    """True/False for an item's epic, or None when its status cannot be established.

    None matters: an item whose epic has no state node cannot be classified, and guessing
    either way is the error this whole path exists to avoid.
    """
    epic = str(item.get("epic", "")).strip()
    if not epic:
        return None
    d = find_epic_dir(state_root, f"E{_norm_num(epic, 3)}")
    if d is None:
        return None
    return os.path.basename(os.path.dirname(d)) == "archived"


def _normalize_one_legacy(store, state_root, item, session, cause):
    """Apply the epic-aware rule to one legacy-status item. Returns a verb string for the
    report: 'resolved', 'normalized', or 'skipped'.

    The rule, and why it is not a flat mapping: `deferred` was a DISPOSITION -- "we looked at
    this and decided not now". `backlog` means open and undecided, and neither open status
    carries a decision, so mapping every `deferred` to `backlog` erases one.

      behind an OPEN epic      -> backlog. The loss is harmless: the item is open either way.
      behind an ARCHIVED epic  -> resolved `deferred`. It will not be picked up in that epic,
                                  and issues-resolved.yaml is where a resolution can actually
                                  hold the decision.
      epic status unknown      -> skipped, reported, untouched.

    Measured on the project that found this: 518 of 520 open items sat behind archived epics,
    and mapping them to `backlog` made 444 undecided findings behind closed epics, reddening
    that project's guard against exactly that.
    """
    was = str(item.get("status", ""))
    archived = _epic_is_archived(state_root, item)
    key = str(item.get("key", ""))
    if archived is None:
        return "skipped"
    if archived:
        store_module.resolve_issue_core(
            store, key, "deferred",
            note=f"migrated from the pre-3.0 open status {was!r}; the epic was "
                 f"already closed, so the deferral is recorded as a resolution "
                 f"rather than reopened as undecided",
            session=session, cause=cause)
        return "resolved"
    item["status"] = LEGACY_OPEN_STATUSES[was]
    _issue_event(store.state_root, "issue_status_normalized", item, session, cause,
                 note=f"{was} -> {item['status']}")
    return "normalized"


def _normalize_all_legacy(args) -> int:
    """Normalize every legacy open status in one pass, under one lock.

    Measured on a real upgrade: 452 items. One-at-a-time that is 452 subprocesses, each
    taking the issues lock, inside a triage step that confirms per item -- reported back as
    impractical, and it is. Batching adds no judgement: the mapping is mechanical, and the
    same LEGACY_OPEN_STATUSES membership test gates each item exactly as the single-key path
    does, so anything unrecognised is left alone rather than swept along.
    """
    open_path = issues_paths(args.state_root)[0]
    with issues_lock(open_path):
        store = IssueStore(open_path)
        # Snapshot first: resolve_issue_core mutates the open list, so iterating it live
        # would skip items.
        legacy = [it for it in list(store.open.get("backlog") or [])
                  if isinstance(it, dict) and str(it.get("status", "")) in LEGACY_OPEN_STATUSES]
        if not legacy:
            sys.stdout.write("OK normalize-status --all-legacy: no legacy status found\n")
            return 0
        tally = {"resolved": 0, "normalized": 0, "skipped": 0}
        skipped_keys = []
        for it in legacy:
            verb = _normalize_one_legacy(store, args.state_root, it,
                                         args.session_id, args.cause)
            tally[verb] += 1
            if verb == "skipped":
                skipped_keys.append(str(it.get("key", "")))
        store.save_open()
    sys.stdout.write(
        f"OK normalize-status --all-legacy: {tally['normalized']} normalized to backlog "
        f"(open epic), {tally['resolved']} resolved as deferred (closed epic), "
        f"{tally['skipped']} skipped\n")
    if skipped_keys:
        sys.stdout.write(
            f"  skipped -- epic status could not be established, left untouched: "
            f"{', '.join(skipped_keys)}\n")
    return 0


def _normalize_keys(args) -> int:
    """Rewrite every stored epic/sprint to its canonical form, wherever one is stored.

    Fixes records written before the write sites normalised: --epic accepted '3', '03',
    '003', 'E3', 'E003' and 'e003', all six produced the same correct key, and all six were
    stored verbatim. One consuming project measured 116 bare-digit against 7 E-prefixed in
    one file. No verb could repair them -- update-issue changes severity only and the other
    repair actions do not touch these fields -- and hand-editing is forbidden by the state
    contract, so they were simply stuck.

    Whole-file by default with no --key, because unlike normalize-status there is no
    per-item judgement: the canonical form of a key is not a decision. Two files, each kept
    in the form it already uses (see canonical_epic_key): issues.yaml stores bare digits,
    adr-register.yaml stores key form.
    """
    changed = {"issues": 0, "register": 0}
    open_path = issues_paths(args.state_root)[0]
    with issues_lock(open_path):
        store = IssueStore(open_path)
        for lst in (store.backlog, store.resolved):
            for it in lst:
                if not isinstance(it, dict):
                    continue
                for field, width in (("epic", 3), ("sprint", 2)):
                    cur = it.get(field)
                    if cur in (None, ""):
                        continue
                    want = _norm_num(cur, width)
                    if str(cur) != want:
                        it[field] = want
                        changed["issues"] += 1
        if changed["issues"]:
            store.save_open()
            store.save_resolved()

    with adr_register_lock(args.state_root):
        y, reg = load_adr_register(args.state_root)
        for entry in reg.get("reserved") or []:
            if not isinstance(entry, dict) or not entry.get("epic"):
                continue
            want = canonical_epic_key(entry["epic"])
            if str(entry["epic"]) != want:
                entry["epic"] = want
                changed["register"] += 1
        if changed["register"]:
            core._atomic_dump(y, reg, adr_register_path(args.state_root))

    total = changed["issues"] + changed["register"]
    if total == 0:
        sys.stdout.write("OK normalize-keys: every stored epic/sprint is already canonical\n")
        return 0
    sys.stdout.write(
        f"OK normalize-keys: {changed['issues']} field(s) in issues.yaml, "
        f"{changed['register']} in adr-register.yaml\n")
    return 0


def _repair_issue(args) -> int:
    from ruamel.yaml.comments import CommentedMap
    if getattr(args, "all_legacy", False):
        if args.action != "normalize-status":
            raise PMError(2, "--all-legacy applies only to --action normalize-status")
        return _normalize_all_legacy(args)
    # normalize-keys is whole-file by construction: the canonical form of a key is not a
    # judgement call, so there is nothing for a --key to scope and nothing to confirm.
    if args.action == "normalize-keys":
        return _normalize_keys(args)
    if not args.key:
        raise PMError(2, "--key is required, or --all-legacy with --action normalize-status, "
                         "or --action normalize-keys")
    k = canonical_bl_key(args.key)
    if k is None:
        raise PMError(2, f"--key {args.key!r} is not a backlog key")
    epic = k[4:7]
    act = args.action
    open_path = issues_paths(args.state_root)[0]
    with issues_lock(open_path):
        store = IssueStore(open_path)
        findings = _audit_findings(args.state_root, store)

        def holds(ids, story=None):
            return any(f["id"] in ids and f["key"] == k and (story is None or f["story"] == story)
                       for f in findings)

        if act == "link" and not args.story:
            raise PMError(2, "--action link needs --story")
        if act in ("unschedule", "link"):
            done = store.resolved_items(k)      # Ruling 8: resolved first
            if done:
                raise PMError(2, f"{act}: {k} is already resolved "
                                 f"({done[-1].get('resolution')}) -- audit finding 1a: rerun "
                                 f"resolve-issue --key {k} (any valid --resolution; the "
                                 f"recorded one is kept) to clear a stale open copy")
        if act == "unschedule":
            opens = store.open_items(k)
            if not (holds({"1b", "1g"}) and len(opens) == 1
                    and str(opens[0].get("status")) == "scheduled"):
                raise PMError(2, f"unschedule: audit finding 1b/1g does not hold for {k}")
            it = opens[0]
            story = it.get("story")
            it["status"] = "backlog"
            it.pop("story", None)
            it.pop("scheduled_at", None)
            store.save_open()
            # scheduled -> backlog is a status transition; the events are its history
            _issue_event(store.state_root, "issue_unscheduled", it, args.session_id,
                         args.cause, story=str(story) if story is not None else None)
            msg = f"{k} unscheduled -> backlog"
        elif act == "link":
            if not holds({"1d"}, story=args.story):
                raise PMError(2, f"link: audit finding 1d does not hold for {k} and {args.story}")
            it = store.single_open(k)           # 1i refusal, never an arbitrary copy
            it["status"] = "scheduled"
            it["story"] = args.story
            it["scheduled_at"] = _now_iso()
            store.save_open()
            # via: tells a repaired scheduling apart from promote's, which has no via field
            _issue_event(store.state_root, "issue_scheduled", it, args.session_id, args.cause,
                         story=args.story, via="repair-link")
            msg = f"{k} scheduled to {args.story}"
        elif act == "normalize-status":
            # Gated like every other action: only a status this schema once used, and only
            # to its documented equivalent. An unrecognised status has no safe mapping, so
            # it stays 1f/report-only rather than being guessed into backlog.
            opens = store.open_items(k)
            if len(opens) != 1:
                raise PMError(2, f"normalize-status: {k} does not resolve to one open item")
            it = opens[0]
            was = str(it.get("status", ""))
            if was not in LEGACY_OPEN_STATUSES:
                raise PMError(2, f"normalize-status: {k} has status {was!r}, which is not a "
                                 f"known legacy status ({', '.join(sorted(LEGACY_OPEN_STATUSES))})"
                                 f" -- audit finding 1f does not hold in its legacy form")
            verb = _normalize_one_legacy(store, args.state_root, it,
                                         args.session_id, args.cause)
            store.save_open()
            if verb == "skipped":
                msg = (f"{k} left at {was!r} -- its epic has no state node, so whether the "
                       f"epic is closed cannot be established and the mapping would be a guess")
            elif verb == "resolved":
                msg = f"{k} {was} -> resolved as deferred (its epic is closed)"
            else:
                msg = f"{k} {was} -> {it['status']} (legacy status normalized)"
        elif act == "repoint":
            # Gated like the rest, but on 1l AND on there being exactly one heir to point
            # at: a key no story records is reported, never guessed at. The heir is
            # re-derived here rather than read off the finding, so the gate and the write
            # cannot disagree about which story that is.
            if not holds({"1l"}):
                raise PMError(2, f"repoint: audit finding 1l does not hold for {k}")
            opens, done = store.open_items(k), store.resolved_items(k)
            # Ruling 8, resolved first: repointing an open copy that a resolve-issue rerun
            # is about to delete would be work thrown away, and 1l skips it for that reason.
            items = [done[-1]] if done else opens
            if len(items) != 1:
                raise PMError(2, f"repoint: {k} does not resolve to one item")
            stories, moved = _story_key_maps(args.state_root)
            fixes = [(f, o, n) for f, o, n in _stale_story_refs(items[0], stories, moved)
                     if n is not None]
            if not fixes:
                raise PMError(2, f"repoint: {k} has a stale story key, but no story records "
                                 f"it in previous_keys -- there is nothing to repoint it to")
            for field, old, new in fixes:
                items[0][field] = new
            if done:
                store.save_resolved()
            else:
                store.save_open()
            _issue_event(store.state_root, "issue_repointed", items[0], args.session_id,
                         args.cause, story=str(items[0].get("story") or "") or None,
                         fields={f: [o, n] for f, o, n in fixes})
            msg = f"{k} " + ", ".join(f"{f} {o} -> {n}" for f, o, n in fixes)
        elif act == "reseed":
            if not any(f["id"] == "1e" and (f["epic"] == epic or f["key"] == "next")
                       for f in findings):
                raise PMError(2, f"reseed: audit finding 1e does not hold for epic {epic}")
            nxt = store.open.get("next")
            if not isinstance(nxt, dict):
                nxt = CommentedMap()
                store.open["next"] = nxt
                epics = sorted({canonical_bl_key(str(i.get("key", "")))[4:7]
                                for i in list(store.backlog) + list(store.resolved)
                                if isinstance(i, dict) and canonical_bl_key(str(i.get("key", "")))})
                for e in epics:
                    nxt[e] = store.highest_suffix(e) + 1
            else:
                # Drop non-canonical aliases of the epic (a hand-edited `1:`), which audit
                # would otherwise keep reporting as 1e -- folding their values into the max,
                # so `next` never decreases.
                aliases = [a for a in nxt if _norm_num(str(a), 3) == epic]
                # ...but never fold a value past the key space into the canonical key: that
                # is a hand edit gone wrong, and the max would make it permanent.
                for a in aliases:
                    v = _int_or_none(nxt.get(a))
                    if v is not None and v > _BL_NEXT_MAX:
                        raise PMError(2, f"reseed: next[{a!r}] = {v} exceeds the BL key space "
                                         f"(keys stop at 999, so next is at most "
                                         f"{_BL_NEXT_MAX}) -- fix it by hand; nothing written")
                known = [v for v in (_int_or_none(nxt.get(a)) for a in aliases) if v is not None]
                for a in aliases:
                    if a != epic:
                        del nxt[a]
                nxt[epic] = max([store.highest_suffix(epic) + 1] + known)
            store.save_open()
            msg = f"next reseeded ({', '.join(f'{e}={v}' for e, v in nxt.items())})"
        else:  # reopen
            if not holds({"1j"}):
                raise PMError(2, f"reopen: audit finding 1j does not hold for {k}")
            entry = store.resolved_items(k)[-1]
            ref = str(entry.get("ref"))
            if not store.open_items(k):        # absent unless a previous reopen was interrupted
                item = CommentedMap()
                for kk, vv in entry.items():
                    if kk not in ("resolution", "resolved_at", "ref", "note"):
                        item[kk] = vv
                item["status"] = "scheduled"
                item["story"] = ref
                item["scheduled_at"] = _now_iso()
                store.backlog.append(item)
                store.save_open()               # add first: an item is never lost
            _remove_identity(store.resolved, entry)
            store.save_resolved()
            _issue_event(store.state_root, "issue_reopened", entry, args.session_id,
                         args.cause, story=ref)
            msg = f"{k} reopened, scheduled to {ref}"
    sys.stdout.write(f"OK repair-issue {msg}\n")
    return 0


def _origin_archived(state_root, epic) -> bool:
    try:
        d = find_epic_dir(state_root, "E" + _norm_num(epic, 3))
    except ValueError:
        return False
    return d is not None and os.path.basename(os.path.dirname(d)) == "archived"


def cmd_list_issues(args) -> int:
    """List (with optional filters) the open items in issues.yaml; with --resolved, the
    resolved items in issues-resolved.yaml; with --all (JSON only), both.

    A missing issues.yaml and a filter set that matches nothing are both success
    (exit 0) — an empty backlog is a normal project state, not a failure. Filters
    combine with AND; a repeated --severity ORs the given severities together.

    --all reads both files under one issues_lock so a concurrent resolve cannot
    tear the snapshot.
    """
    return _run_core(lambda: _list_issues(args))


def _list_issues(args) -> int:
    if args.resolution and not args.resolved:
        raise PMError(2, "--resolution filters resolved items; add --resolved")
    if args.status and (args.resolved or args.all):
        raise PMError(2, "--status filters open items; drop --resolved/--all")
    if args.all and args.format != "json":
        raise PMError(2, "--all is JSON only; add --format json")
    open_path, res_path = issues_paths(args.state_root)
    if args.all:
        if not (os.path.exists(open_path) or os.path.exists(res_path)):
            opened, resolved = [], []
        else:
            with issues_lock(open_path):
                od, rd = core._load(open_path)[1] or {}, core._load(res_path)[1] or {}
            for name, data, path in (("backlog", od, open_path), ("resolved", rd, res_path)):
                if data.get(name) is not None and not isinstance(data.get(name), list):
                    raise PMError(2, f"{path} has a malformed '{name}' field")
            opened = list(od.get("backlog") or [])
            resolved = list(rd.get("resolved") or [])
    else:
        src = res_path if args.resolved else open_path
        items = list((core._load(src)[1] or {}).get("resolved" if args.resolved else "backlog") or [])

    epic_filter = _norm_num(args.epic, 3) if args.epic else None
    sprint_filter = _norm_num(args.sprint, 2) if args.sprint else None
    severity_filter = set(args.severity) if args.severity else None

    def matches(item) -> bool:
        if not isinstance(item, dict):
            return False
        if epic_filter is not None and _norm_num(item.get("epic", ""), 3) != epic_filter:
            return False
        if sprint_filter is not None:
            item_sprint = str(item.get("sprint", "") or "").strip()
            # empty sprint = epic-level item; it never satisfies a --sprint filter
            if not item_sprint or _norm_num(item_sprint, 2) != sprint_filter:
                return False
        if severity_filter is not None and item.get("severity") not in severity_filter:
            return False
        if args.status and str(item.get("status", "")) != args.status:
            return False
        if args.resolution and str(item.get("resolution", "")) != args.resolution:
            return False
        return not (getattr(args, "kind", None) and str(item.get("kind") or "defect") != args.kind)

    def as_json(item):
        d = dict(item)
        d["origin_archived"] = _origin_archived(args.state_root, item.get("epic", ""))
        return d

    if args.all:
        sys.stdout.write(json.dumps({"open": [as_json(i) for i in opened if matches(i)],
                                     "resolved": [as_json(i) for i in resolved if matches(i)]},
                                    indent=2) + "\n")
        return 0
    filtered = [i for i in items if matches(i)]
    if args.format == "json":
        sys.stdout.write(json.dumps([as_json(i) for i in filtered], indent=2) + "\n")
        return 0
    if not filtered:
        sys.stdout.write("(no matching issues)\n")
        return 0
    state_col = "RESOLUTION" if args.resolved else "STATUS"
    headers = ["KEY", "EPIC", "SPRINT", "SEVERITY", state_col, "ORIGIN", "TITLE"]
    rows = [[str(i.get("key", "")), str(i.get("epic", "")), str(i.get("sprint", "")) or "-",
             str(i.get("severity", "")),
             str(i.get("resolution" if args.resolved else "status", "")),
             "archived" if _origin_archived(args.state_root, i.get("epic", "")) else "-",
             str(i.get("title", ""))] for i in filtered]
    widths = [max(len(headers[c]), *(len(r[c]) for r in rows)) for c in range(len(headers))]

    def _fmt_row(cells):
        last = len(cells) - 1
        return "  ".join(c if idx == last else c.ljust(widths[idx]) for idx, c in enumerate(cells))

    sys.stdout.write(_fmt_row(headers) + "\n")
    for r in rows:
        sys.stdout.write(_fmt_row(r) + "\n")
    return 0
