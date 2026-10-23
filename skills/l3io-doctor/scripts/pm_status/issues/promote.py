"""pm_status.issues.promote -- promote-issue and schedule-issue, and the story-key allocator.

`promote-issue` creates a story for a backlog item; `schedule-issue` attaches one to a story
that already exists. Both are write verbs, so both fail safe on a lock they cannot evaluate
(Ruling 24), and both go through `_next_story_key`, whose floor is the max of the sprint
node's high-water and the highest story key on disk -- a key is never handed out twice.

Sits above `store` (it builds `IssueStore`s and reads the schema constants) and below
`audit`, which reuses `_walk_story_nodes` and `_dead_claim` from here.

`metrics` IS REACHED AS A MODULE, two levels up. `_promote_issue` is the only external
caller of `metrics.estimates.compute_story_estimate` and `metrics.estimates.
rollup_parent_estimate`, both mock.patch targets, so the calls must stay module-qualified
or the patch stops biting -- silently. `from .. import metrics` at this depth keeps the
call text character-for-character what it was in `__main__.py`, including through the
`sys.modules[__name__] = _main` facade. `nodes.save_node` and `nodes.epic_file` are
module-qualified for the same reason.
"""

from __future__ import annotations

import os
import re
import sys

from .. import core, metrics, nodes
from ..core import (
    STATUS_DIRS,
    PMError,
    _norm_num,
    _now_iso,
    _parse_iso,
    _run_core,
    _yaml,
    epic_dirname,
    epic_node_lock,
    issues_lock,
    parse_story_key,
    sprint_dirname,
)
from ..metrics.estimates import DEFAULT_ESTIMATE_MODEL
from ..metrics.rates import TOKEN_CLASSES, rate_overrides, resolve_rates
from ..nodes import (
    _check_lock_verdict,
    check_backrefs,
    find_epic_dir,
    init_story_doc,
    load_node,
    sprint_file,
    story_doc_path,
    story_file,
)
from .store import IssueStore, _issue_event, canonical_bl_key, issues_paths

# A story FILE in either tree. The optional `-slug` is the documented artifact shape
# (CLAUDE.md gives `E032-S01-001-centralized-file-config.md` as its own example), and it was
# not matched here -- so a slugged document did NOT count toward the allocator's disk floor,
# and its key could be handed out again. `story_doc_path` only ever generates the UNSLUGGED
# name, so promote-issue's existence check could not see the collision either. One consumer
# (the disk floor), and widening it can only ever ADD to that floor, which is the safe
# direction: more things reserve a key, nothing releases one.
_STORY_FILE_RE = re.compile(r"^E\d{3}-S\d{2}-(\d{3})(?:-[^.]*)?\.(yaml|md)$")


def _unevaluable_lock_reason(lock, session_id):
    """Why promote cannot evaluate a present `_lock`, or None when it can (Ruling 24).

    promote is a write verb, like set-lock, so it fails safe: a foreign lock whose shape it
    cannot read refuses, even where check-lock (a read) reports such a lock FREE. A lock
    naming this session is this session's own and is not refused -- set-lock re-claims its
    own lock the same way, whatever else the block holds. Everything this returns None for
    is exactly what `_check_lock_verdict` can judge without raising.

    The holder is compared to the caller EXACTLY (Ruling F2), as `_check_lock_verdict` and
    cmd_set_lock compare it: a hand-edited 'me ' is foreign to `me` in all three paths, so a
    padded id fails safe. Only the presence check strips, reading a whitespace-only
    session_id as missing."""
    if not isinstance(lock, dict):
        return "not a mapping"
    holder = str(lock.get("session_id", "") or "")
    if not holder.strip():
        return "no session_id"
    if session_id and holder == session_id:
        return None
    claimed = _parse_iso(str(lock.get("claimed_at", "")))
    if claimed is None:
        return "claimed_at is missing or unparseable"
    if claimed.tzinfo is None:
        return "claimed_at has no timezone"
    try:
        int(lock.get("ttl_minutes", 30))
    except (TypeError, ValueError):
        return f"ttl_minutes {lock.get('ttl_minutes')!r} is not a whole number"
    return None


def _foreign_lock_error(epath: str, session_id, epic_key: str):
    """PMError(5) when the epic's `_lock` blocks this session, else None.

    A lock promote cannot evaluate (`_unevaluable_lock_reason`) refuses, naming the epic
    and clear-lock for an abandoned one (Ruling 24). A well-formed lock gets check-lock's
    own verdict (`_check_lock_verdict`, carryover 16), so promote shares its TTL semantics:
    a stale lock -- including any `ttl_minutes: 0` -- does not block. An absent or null
    `_lock` is no lock, as set-lock reads it."""
    _, data = load_node(epath)
    lock = (data or {}).get("_lock")
    if lock is None:
        return None
    why = _unevaluable_lock_reason(lock, session_id)
    if why:
        return PMError(5, f"epic {epic_key} holds a _lock that cannot be evaluated ({why}) "
                          f"-- refusing to write; if the lock is abandoned, remove it with "
                          f"clear-lock --epic {epic_key}")
    code, line = _check_lock_verdict(lock, session_id)
    if code == 0:
        return None
    return PMError(5, f"epic {epic_key} is {line} -- pass that --session-id, or wait for the "
                      f"lock to expire")


def _highest_story_on_disk(state_root, artifacts_root, epic_key, sprint_key) -> int:
    """Highest story number present in the sprint, across the state directory AND the
    artifact stories/ directory. A document without a state node still owns its key."""
    prefix = f"{epic_key}-{sprint_key}-"
    epic_dir = find_epic_dir(state_root, epic_key)
    dirs = [os.path.join(artifacts_root, epic_dirname(epic_key), sprint_dirname(sprint_key),
                         "stories")]
    if epic_dir is not None:
        dirs.insert(0, os.path.join(epic_dir, sprint_dirname(sprint_key)))
    highest = 0
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            m = _STORY_FILE_RE.match(name)
            if m and name.startswith(prefix):
                highest = max(highest, int(m.group(1)))
    return highest


def _next_story_key(state_root, artifacts_root, epic_key, sprint_key) -> str:
    """Allocate the sprint's next story key: `max(sprint.next, highest-on-disk + 1)`.

    WHY A HIGH-WATER AND NOT JUST THE DISK. Deriving from the disk alone makes a vacated
    number immediately reusable. That is harmless while stories only ever appear, but it is a
    live defect the moment one can MOVE: a story leaving E032-S01-001 frees that key, the next
    story takes it, and `l3io-sync`'s mapping still points that key's remote issue at what is
    now DIFFERENT WORK. Nothing errors -- the issue is silently retargeted. `issues.yaml`
    carries a per-epic `next:` for exactly this reason, documented there as "a high-water mark
    that never decreases, so a deleted or resolved key is never reused".

    WHY STILL CONSULT THE DISK. Taking the max of both, rather than trusting `next` alone, is
    what keeps this small. An absent `next` (every project today) behaves exactly as before,
    so there is no migration. A `next` that is somehow too LOW cannot cause a reuse, because
    the disk floor still applies -- it is self-healing, which is why this needs no audit
    finding and no reseed verb, unlike the allocator it is modelled on. A `next` that is too
    high is honoured: it wastes a number, which is the safe direction.

    The only consequence for an ordinary project is that keys become sparse where a story is
    deleted, instead of the next one backfilling the hole.

    Callers hold the epic write lock (see cmd_promote_issue), so the read-modify-write below
    is already serialised; it takes no lock of its own.
    """
    prefix = f"{epic_key}-{sprint_key}-"
    floor = _highest_story_on_disk(state_root, artifacts_root, epic_key, sprint_key) + 1

    spath = sprint_file(state_root, epic_key, sprint_key)
    y = node = None
    stored = 0
    if spath is not None:
        y, node = load_node(spath)
        if isinstance(node, dict):
            try:
                stored = int(node.get("next") or 0)
            except (TypeError, ValueError):
                stored = 0          # unparseable is treated as absent; the disk floor holds

    number = max(stored, floor)
    if isinstance(node, dict):
        node["next"] = number + 1   # never decreases: number >= stored, so this only grows
        nodes.save_node(y, node, spath)
    return f"{prefix}{number:03d}"


def _yaml_error_reason(e) -> str:
    """One line from a ruamel parse error: its problem and where, not the multi-line dump."""
    problem = getattr(e, "problem", None) or (str(e).splitlines() or [type(e).__name__])[0]
    mark = getattr(e, "problem_mark", None)
    if mark is None:
        return problem
    return f"{problem} (line {mark.line + 1}, column {mark.column + 1})"


def _walk_story_nodes(state_root):
    """Yield (story_key, status_dir, node, path) for every story node in every status folder.

    A node that does not parse, is not valid UTF-8, or is not a mapping (Ruling F4) is
    PMError(2) naming the file (Ruling F1): every caller is a
    verb that must refuse before its first write rather than exit 1 with a traceback.
    audit-issues maps it onto its existing error channel (exit 4), not a new finding id."""
    from ruamel.yaml.error import YAMLError
    for sdir in STATUS_DIRS:
        base = os.path.join(state_root, sdir)
        if not os.path.isdir(base):
            continue
        for ename in sorted(os.listdir(base)):
            edir = os.path.join(base, ename)
            if not (ename.startswith("epic-") and os.path.isdir(edir)):
                continue
            for sname in sorted(os.listdir(edir)):
                spd = os.path.join(edir, sname)
                if not (sname.startswith("sprint-") and os.path.isdir(spd)):
                    continue
                for fname in sorted(os.listdir(spd)):
                    if not fname.endswith(".yaml") or fname == "sprint.yaml":
                        continue
                    path = os.path.join(spd, fname)
                    try:
                        node = load_node(path)[1]
                    except YAMLError as e:
                        raise PMError(2, f"{path} does not parse: {_yaml_error_reason(e)} -- "
                                         f"fix the file by hand")
                    except UnicodeDecodeError as e:
                        raise PMError(2, f"{path} is not valid UTF-8 ({e.reason} at byte "
                                         f"{e.start}) -- fix the file by hand")
                    if node is None:
                        continue
                    if not isinstance(node, dict):
                        held = "a list" if isinstance(node, list) else "a scalar"
                        raise PMError(2, f"{path} is not a mapping (it holds {held}) -- fix "
                                         f"the file by hand")
                    yield str(node.get("key") or fname[:-5]), sdir, node, path


def _dead_claim(status_dir, node) -> bool:
    """A story under archived/ that is not `done` is ignored as a claimant, because its
    epic is closed: promote's resume and audit 1d/1h skip it. If that story is later marked
    `done` (cmd_set_status has no archived guard, and pm-sync pull runs `set-status done`),
    the claim revives, and audit 1h reports the double listing; audit 1g still reports an
    item SCHEDULED to it (1g is keyed on the item's `story:`)."""
    return status_dir == "archived" and str(node.get("status", "")) != "done"


def _partial_promotion(state_root, keys):
    """The story (if any) that already claims these `keys` via its `resolves`, across EVERY
    epic -- keys spread across stories, or a story listing a superset/subset of what was
    asked for, are both claims that must refuse rather than silently mint a second story
    (audit-issues 1d/1h). Resumes only the exact match: exactly one claimant, whose
    `resolves` set equals `keys` exactly, and whose status is not `done`. Anything else --
    no exact claimant, more than one claimant, or a lone claimant whose resolves is a
    superset/subset or who is already done -- refuses (PMError 2) rather than guess.
    A dead claim (`_dead_claim`) is not a claimant at all: after the 1g repair the item is
    backlog again and a re-promotion must mint a new story, not resume the archived one.
    The caller refuses a returned claimant outside its own --epic/--sprint, which parses the
    claimant's key -- so a malformed one is refused here, naming the node, before any write."""
    keyset = set(keys)
    claimants = {}
    for story_key, sdir, node, path in _walk_story_nodes(state_root):
        if _dead_claim(sdir, node):
            continue
        resolves = {str(k) for k in (node.get("resolves") or [])}
        if resolves & keyset:
            claimants[story_key] = (node, path)
    if not claimants:
        return None
    if len(claimants) == 1:
        (story_key, (node, path)), = claimants.items()
        resolves = {str(k) for k in (node.get("resolves") or [])}
        if resolves == keyset and str(node.get("status", "")) != "done":
            try:
                parse_story_key(story_key)
            except ValueError:
                raise PMError(2, f"story node {path} has a malformed key {story_key!r} -- fix "
                                 f"it by hand, then rerun")
            return story_key
    raise PMError(2, f"{', '.join(keys)} already claimed by {sorted(claimants)} -- run "
                     f"/l3io-doctor triage (audit-issues 1d/1h)")


def _promotable_items(store, keys):
    """Resolved is checked FIRST, then the single-open guard (Ruling 8 + Ruling 5): a
    key present in issues-resolved.yaml is resolved even if a stale open copy remains
    (resolve's crash window), and IssueStore.single_open raises PMError(2) itself for
    an ambiguous key (audit-issues finding 1i)."""
    items = []
    for k in keys:
        done = store.resolved_items(k)
        if done:
            raise PMError(2, f"{k} is already resolved ({done[-1].get('resolution')})")
        item = store.single_open(k)
        if item is None:
            raise PMError(2, f"{k} is not an open backlog item")
        if str(item.get("status", "backlog")) == "scheduled":
            raise PMError(2, f"{k} is already scheduled to story {item.get('story')}")
        kind = str(item.get("kind") or "defect")
        if kind != "defect":
            raise PMError(2, f"{k} is a {kind} item -- spec items are confirmed or rejected in "
                             f"/l3io-doctor triage, never promoted to a story")
        items.append(item)
    return items


def _promotion_context(items) -> str:
    lines = ["## Context", "", "Promoted from deferred finding(s):"]
    for it in items:
        desc = str(it.get("description", "") or "").strip()
        lines.append(f"- {it.get('key')} ({it.get('severity')}, {it.get('source')})"
                     + (f" — {desc}" if desc else ""))
    return "\n".join(lines)


def _promote_target(sr, epic_key, sprint_key):
    """(epic path, sprint path) for promote-issue, refusing an absent (3) or archived (2)
    epic and an absent (3) or already-started (2) sprint. Run once before the epic lock, to
    refuse fast, and again under it, where the answer is decisive."""
    epath = nodes.epic_file(sr, epic_key)
    if epath is None:
        raise PMError(3, f"epic {epic_key} not found under {sr}")
    if os.path.basename(os.path.dirname(os.path.dirname(epath))) == "archived":
        raise PMError(2, f"epic {epic_key} is archived -- promote into a planned or active epic")
    spath = sprint_file(sr, epic_key, sprint_key)
    if spath is None:
        raise PMError(3, f"sprint {epic_key}-{sprint_key} not found")
    sstatus = str((load_node(spath)[1] or {}).get("status", ""))
    if sstatus != "backlog":
        raise PMError(2, f"sprint {epic_key}-{sprint_key} is {sstatus!r}, not backlog -- "
                         f"promote into a sprint that has not started")
    return epath, spath


def cmd_promote_issue(args) -> int:
    """Turn open BL items into a new story (spec §2.4). Every refusal is checked before
    the first write. An early advisory `issues_lock` check refuses fast, before the epic
    lock is even taken. Then, under `epic_node_lock`, a decisive foreign-lock re-check is
    followed by ONE `issues_lock` hold spanning the decisive item check through the
    schedule save: the item check, partial-promotion detection, the story-document
    pre-check, the story node + estimate save, the story document, both roll-ups, and
    finally marking the items scheduled and saving -- all under that single nested
    `issues_lock`, so a concurrent `resolve-issue` on the same key can never land between
    the check and the write (Ruling 12a). Story first among the writes, so a failure after
    it (e.g. the scheduling save itself failing) leaves a story whose `resolves` still
    names the items, and a retry resumes it via `_partial_promotion`."""
    return _run_core(lambda: _promote_issue(args))


def _promote_issue(args) -> int:
    from ruamel.yaml.comments import CommentedMap, CommentedSeq
    from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQ
    sr, ar = args.state_root, args.artifacts_root
    keys = []
    for raw in args.key:
        k = canonical_bl_key(raw)
        if k is None:
            raise PMError(2, f"--key {raw!r} is not a backlog key")
        # REFUSED, not deduped. The --title rule below reads len(keys), so collapsing a
        # repeat would disarm the one guard that makes a multi-item promotion deliberate:
        # the call asks for two items, yields one, and is never prompted for the title two
        # distinct keys would demand. The caller here is usually an agent assembling this
        # list from a user's prose (steps/plan/step-backlog-intake.md §3), which is exactly
        # the caller that can name one item twice.
        #
        # schedule-issue keeps the dedup on purpose: nothing downstream of it reads the key
        # count, so a repeat there changes nothing observable. Same shape, different
        # decision, because the consequence differs -- not an inconsistency to tidy up.
        if k in keys:
            raise PMError(2, f"--key {k} was given twice. Promoting several items into one "
                             f"story needs --title, and a repeated key would skip that "
                             f"check by collapsing to one. Drop the duplicate, or name the "
                             f"other key you meant.")
        keys.append(k)
    if len(keys) > 1 and not args.title:
        raise PMError(2, "promoting several items into one story needs --title")
    model = args.model or DEFAULT_ESTIMATE_MODEL
    overrides = rate_overrides(args)                      # bad JSON exits 2 here, pre-write
    try:
        rates = resolve_rates(model, overrides)
    except KeyError as e:
        raise PMError(2, e.args[0])
    missing = [c for c in TOKEN_CLASSES if c not in rates]
    if missing:
        raise PMError(2, f"model {model!r} has no rate for {missing}")
    epic_key = "E" + _norm_num(args.epic, 3)
    sprint_key = "S" + _norm_num(args.sprint, 2)
    epath, spath = _promote_target(sr, epic_key, sprint_key)
    open_path = issues_paths(sr)[0]
    with issues_lock(open_path):
        _promotable_items(IssueStore(open_path), keys)     # advisory: refuse fast, no epic lock yet
    err = _foreign_lock_error(epath, args.session_id, epic_key)          # advisory
    if err:
        raise err
    with epic_node_lock(sr, epic_key):
        # Resolve again under the lock: move-epic holds it too, so a move that landed while
        # this call waited has moved the directory the paths above name, and writing
        # through them would recreate the old directory as a ghost.
        epath, spath = _promote_target(sr, epic_key, sprint_key)
        err = _foreign_lock_error(epath, args.session_id, epic_key)      # decisive
        if err:
            raise err
        # One issues_lock hold spans the decisive item check through the schedule save
        # (Ruling 12a): nothing in between (compute_story_estimate, init_story_doc,
        # rollup_parent_estimate/save_node) takes issues_lock itself, so a concurrent
        # resolve-issue on the same key blocks here rather than landing between this
        # check and the write that would otherwise orphan an estimated story.
        with issues_lock(open_path):
            store = IssueStore(open_path)
            items = _promotable_items(store, keys)             # decisive
            story_key = _partial_promotion(sr, keys)
            resumed = story_key is not None
            if resumed:
                # Resume only the interrupted call itself (spec §2.4, "a story in the target
                # epic"): a claimant elsewhere was never locked or foreign-lock-checked here,
                # and the roll-ups below would target --epic, not the claimant's epic.
                c_epic, c_sprint, _ = parse_story_key(story_key)
                if (c_epic, c_sprint) != (epic_key, sprint_key):
                    raise PMError(2, f"{', '.join(keys)} were partly promoted into {story_key} "
                                     f"-- retry with --epic {c_epic[1:]} --sprint {c_sprint[1:]}")
            else:
                story_key = _next_story_key(sr, ar, epic_key, sprint_key)
                # DEFENSIVE, and deliberately kept without a fixture. `_next_story_key` above
                # already skips a key whose artifact document exists, so the key it just
                # returned cannot have one -- this arm is unreachable from inside the call.
                # It is not dead, though: it guards against a writer outside our locks, and
                # agents in this system do author story documents directly. The two locks
                # held here exclude another promote, never an external author.
                if os.path.exists(story_doc_path(ar, story_key)):
                    raise PMError(2, f"story document for {story_key} already exists -- "
                                     f"refusing to adopt it")
                node = CommentedMap()
                node["key"] = SQ(story_key)
                node["epic"] = SQ(epic_key)
                node["sprint"] = SQ(sprint_key)
                node["title"] = args.title or str(items[0].get("title", ""))
                node["status"] = "backlog"
                node["classification"] = args.classification
                seq = CommentedSeq(keys)
                seq.fa.set_flow_style()
                node["resolves"] = seq
                metrics.estimates.compute_story_estimate(
                    sr, node, args.classification, model, overrides)
                core._atomic_dump(_yaml(), node,
                            os.path.join(os.path.dirname(spath), f"{story_key}.yaml"))
            init_story_doc(sr, ar, story_key, context_md=_promotion_context(items),
                           ac_lines=[f"The deferred finding {i.get('key')} is resolved: "
                                     f"{i.get('title')}" for i in items],
                           must_not_exist=not resumed)
            _, story_sprint, _ = parse_story_key(story_key)
            metrics.estimates.rollup_parent_estimate(sr, epic_key, story_sprint,
                                                     model, overrides)
            metrics.estimates.rollup_parent_estimate(sr, epic_key, None,
                                                     model, overrides)
            for it in items:
                it["status"] = "scheduled"
                it["story"] = story_key
                it["scheduled_at"] = _now_iso()
            store.save_open()
    for it in items:
        _issue_event(sr, "issue_scheduled", it, args.session_id, args.cause, story=story_key)
    sys.stdout.write(f"OK promote-issue {', '.join(keys)} -> {story_key}"
                     f"{' (resumed)' if resumed else ''}\n")
    return 0


def _schedulable_items(store, keys, story_key):
    """Split `keys` into (to_schedule, already_here) for a named existing story.

    Gate order mirrors `_promotable_items`: resolved FIRST (Ruling 8), because a key in
    issues-resolved.yaml is resolved even if a stale open copy survives resolve's crash
    window, then the single-open guard (Ruling 5, finding 1i). It differs in exactly one
    place. An item already scheduled to THIS story is a skip rather than a refusal,
    because the mapping that drives this verb is executed as a batch and re-running the
    whole batch has to be safe -- the alternative is asking the operator to track which
    of 28 rows applied. An item scheduled to a DIFFERENT story is still a refusal:
    moving it silently would rewrite a scheduling decision somebody made and leave the
    old story's `resolves` naming an item it no longer owns, which is audit finding 1e.
    """
    to_schedule, already_here = [], []
    for k in keys:
        done = store.resolved_items(k)
        if done:
            raise PMError(2, f"{k} is already resolved ({done[-1].get('resolution')})")
        item = store.single_open(k)
        if item is None:
            raise PMError(2, f"{k} is not an open backlog item")
        kind = str(item.get("kind") or "defect")
        if kind != "defect":
            raise PMError(2, f"{k} is a {kind} item -- spec items are confirmed or rejected "
                             f"in /l3io-doctor triage, never scheduled to a story")
        if str(item.get("status", "backlog")) == "scheduled":
            at = str(item.get("story") or "")
            if at == story_key:
                already_here.append(item)
                continue
            raise PMError(2, f"{k} is already scheduled to story {at} -- unschedule it first "
                             f"(repair-issue --action unschedule --key {k}) rather than "
                             f"moving it silently")
        to_schedule.append(item)
    return to_schedule, already_here


def _schedule_target(sr, epic_key, story_key):
    """(epic path, story path, story node) for schedule-issue, refusing a home the work
    will never reach. Run once before the epic lock to refuse fast, and again under it,
    where the answer is decisive.

    Deliberately NOT `_promote_target`: that one also requires the sprint to be
    `backlog`, which is right for allocating a new story and wrong here -- attaching a
    finding to an existing story in a sprint already under way is the ordinary case.

    The two refusals are the failure this verb exists to avoid: an item silently
    acquiring a home nobody will work. `done` and `archived` are checked separately
    because neither implies the other -- a story under `archived/` can still read
    `status: backlog`, which is how 34 open items on one consumer tree came to be keyed
    to an epic that had been archived out from under them.
    """
    epath = nodes.epic_file(sr, epic_key)
    if epath is None:
        raise PMError(3, f"epic {epic_key} not found under {sr}")
    if os.path.basename(os.path.dirname(os.path.dirname(epath))) == "archived":
        raise PMError(2, f"epic {epic_key} is archived -- schedule into a planned or active "
                         f"epic, or move the epic back first (move-epic)")
    spath = story_file(sr, story_key)
    if spath is None:
        raise PMError(3, f"story {story_key} not found under {sr} -- schedule-issue attaches "
                         f"to a story that exists; use promote-issue to create one")
    node = load_node(spath)[1]
    if node is None:
        raise PMError(3, f"story {story_key} -- file {spath} is empty")
    ek, sk, _ = parse_story_key(story_key)
    problems = check_backrefs(node, ek, sk)
    if problems:
        raise PMError(4, f"back-reference mismatch for story {story_key}: "
                         f"{'; '.join(problems)}")
    status = str(node.get("status", ""))
    if status == "done":
        raise PMError(2, f"story {story_key} is done -- its acceptance criteria are already "
                         f"closed, so an unfixed finding attached here is lost. Schedule it "
                         f"to an open story, or promote-issue a new one")
    return epath, spath, node


def cmd_schedule_issue(args) -> int:
    """Attach open BL items to a story that ALREADY EXISTS (the counterpart to
    promote-issue, which only ever creates one).

    Locking mirrors promote-issue exactly, including the nesting order, so the two
    cannot deadlock against each other: an advisory `issues_lock` check to refuse fast,
    an advisory foreign-lock check, then `epic_node_lock`, a re-resolve under it because
    move-epic holds the same lock and may have moved the directory while this call
    waited, a decisive foreign-lock re-check, and ONE `issues_lock` hold spanning the
    decisive item check through the schedule save (Ruling 12a) so a concurrent
    resolve-issue on the same key cannot land between the check and the write.

    Story node first among the writes, matching promote: a failure after it leaves a
    story whose `resolves` names the items while they still read `backlog`, which is
    audit finding 1d -- the state `repair-issue --action link` exists to repair. The
    reverse order would leave items pointing at a story that never claimed them, which
    is finding 1e and has no single-key repair.

    It does NOT re-estimate the story or re-roll-up its parents. The story's estimate was
    set when it was written, by whoever sized it; attaching a finding whose fix its
    acceptance criteria already imply is not a resize, and overwriting a human's estimate
    as a side effect of a bookkeeping verb would be worse than leaving it stale.
    """
    return _run_core(lambda: _schedule_issue(args))


def _schedule_issue(args) -> int:
    from ruamel.yaml.comments import CommentedSeq
    sr = args.state_root
    keys = []
    for raw in args.key:
        k = canonical_bl_key(raw)
        if k is None:
            raise PMError(2, f"--key {raw!r} is not a backlog key")
        if k not in keys:
            keys.append(k)
    try:
        epic_key, _sprint_key, _ = parse_story_key(args.story)
    except ValueError as e:
        raise PMError(2, str(e)) from None

    open_path = issues_paths(sr)[0]
    _schedule_target(sr, epic_key, args.story)                    # advisory: refuse fast
    with issues_lock(open_path):
        _schedulable_items(IssueStore(open_path), keys, args.story)   # advisory
    err = _foreign_lock_error(nodes.epic_file(sr, epic_key), args.session_id, epic_key)
    if err:
        raise err
    with epic_node_lock(sr, epic_key):
        # Re-resolve under the lock: move-epic holds it too, so a move that landed while
        # this call waited has moved the directory the paths above name.
        epath, spath, node = _schedule_target(sr, epic_key, args.story)
        err = _foreign_lock_error(epath, args.session_id, epic_key)    # decisive
        if err:
            raise err
        with issues_lock(open_path):
            store = IssueStore(open_path)
            items, already = _schedulable_items(store, keys, args.story)   # decisive
            if items:
                existing = [str(x) for x in (node.get("resolves") or [])]
                seq = node.get("resolves")
                if not isinstance(seq, CommentedSeq):
                    seq = CommentedSeq(existing)
                    seq.fa.set_flow_style()
                    node["resolves"] = seq
                for it in items:
                    k = str(it.get("key"))
                    if k not in existing:        # a story may already claim it (finding 1d)
                        seq.append(k)
                nodes.save_node(_yaml(), node, spath)
                stamp = _now_iso()
                for it in items:
                    it["status"] = "scheduled"
                    it["story"] = args.story
                    it["scheduled_at"] = stamp
                store.save_open()
    for it in items:
        # via: a third route to `scheduled`. promote-issue writes no via, repair-link
        # writes "repair-link"; without a distinct value the log cannot say how an item
        # got its story, which is the only record of whether a human chose it.
        _issue_event(sr, "issue_scheduled", it, args.session_id, args.cause,
                     story=args.story, via="schedule")
    done_keys = [str(i.get("key")) for i in items]
    skipped = [str(i.get("key")) for i in already]
    parts = []
    if done_keys:
        parts.append(f"{', '.join(done_keys)} -> {args.story}")
    if skipped:
        parts.append(f"{', '.join(skipped)} already scheduled to {args.story} (skipped)")
    sys.stdout.write(f"OK schedule-issue {'; '.join(parts)}\n")
    return 0
