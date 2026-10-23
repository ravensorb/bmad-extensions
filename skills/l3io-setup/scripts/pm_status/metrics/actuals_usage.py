"""pm_status.metrics.actuals_usage -- writing actuals, and reading the transcript they come from.

`set-actual`/`import-actual` (which also drive the calibration append), the Claude
session-transcript discovery and `usage` reading that make token and cost actuals
EXACT under Claude rather than guessed, and `dispatch_window`.

It sits above `calibration` and `rates`: an actuals write prices through the rate
table and then appends a calibration sample, so it depends on both and neither
depends on it.

`dispatch_window` is a mock.patch target (`pm.metrics.actuals_usage.dispatch_window`)
and so is NOT re-exported. `cmd_usage` calls it as a plain global in this module,
which is exactly the binding `patch.object` rebinds. `nodes.save_node` is
module-qualified for the same reason.
"""

from __future__ import annotations

import glob
import json
import os
import sys
from datetime import UTC, datetime

from .. import nodes
from ..core import (
    _coerce,
    _die_usage,
    _event_keys,
    _now_iso,
    _num_or_none,
    _parse_iso,
    append_event,
    events_path,
)
from ..nodes import (
    _epic_write_lock,
    _load_checked,
)
from .calibration import (
    record_closure_sample,
    record_orchestration_sample,
    record_story_sample,
)
from .rates import (
    TOKEN_CLASSES,
    cost_from_tokens,
    rate_overrides,
    tokens_block,
)


def cmd_import_actual(args) -> int:
    """set-actual with the migration contract baked into defaults that cannot be overridden.

    A migrated actual needs three things, each easy to forget and dangerous to forget:

      runtime = other   it has no Claude provenance to claim
      tokens  = N/A     legacy data carries no four-class split, and 0 would be consumed by
                        calibration as a real measurement, dragging the learned ratio to zero
      no calibration    a bulk import must not append hundreds of samples in one pass;
                        `calibration redrive` rebuilds from the nodes afterwards if wanted

    set-actual can express all three -- that is why this verb delegates rather than
    reimplements, and why set-actual is left exactly as it is. What it cannot do is stop a
    caller omitting one: forget --tokens-na under runtime=claude and you get a refusal, but
    forget --no-calibrate and the ratios are quietly poisoned with unmeasured data. This verb
    removes that choice. --runtime, --tokens-*, --model and --calibrate are not in its surface
    at all, so a wrong call is a usage error rather than a silent one.
    """
    args.runtime = "other"
    args.tokens_na = True
    args.no_calibrate = True
    args.block = "actual"
    args.model = ""
    args.token_rates = ""
    args.cost = None
    for f in ("tokens_input", "tokens_output", "tokens_cache_write", "tokens_cache_read"):
        setattr(args, f, None)
    return cmd_set_actual(args)


def cmd_set_actual(args) -> int:

    kind = args.node
    block = getattr(args, "block", "actual")
    if block == "orchestration" and kind == "story":
        _die_usage("--block orchestration is only valid on a sprint or epic — a story's "
                   "orchestration belongs to its parent sprint")
    if args.cost is not None:   # a usage error on any node: refused before the epic lock
        _die_usage("--cost is not accepted: cost is derived from tokens x rates. "
                   "Fix the token counts or modules.l3io-pm.token_rates instead.")
    # Both the node save and, for a sprint or epic, the calibration sample's replay marker
    # (_mark_sampled) write the node, so an epic's whole cycle runs under its lock. Lock
    # order: epic_node_lock, then calibration_lock inside the record_* helpers.
    with _epic_write_lock(args, kind):
        return _set_actual(args, kind, block)


def _set_actual(args, kind, block) -> int:
    """cmd_set_actual's body; the caller holds the epic lock for an epic node."""
    y, node, path, label = _load_checked(args.state_root, args, kind)

    provided = {
        "elapsed_hours": args.elapsed_hours,
        "man_hours": args.man_hours,
        "hitl_hours": args.hitl_hours,
    }

    classes = {c: getattr(args, "tokens_" + c) for c in TOKEN_CLASSES}
    given = {c: v for c, v in classes.items() if v is not None}
    if args.tokens_na and given:
        _die_usage("--tokens-na cannot be combined with explicit token counts")
    if args.tokens_na:
        if args.runtime == "claude":
            _die_usage("runtime=claude forbids tokens=N/A — capture the exact per-class "
                       "counts from the session transcript (see metrics-contract.md §3)")
        elif args.runtime == "codex":
            _die_usage("runtime=codex forbids tokens=N/A — capture input_tokens, "
                       "output_tokens+reasoning_output_tokens, and cached_input_tokens "
                       "from rollout-*.jsonl token_count events "
                       "(see metrics-contract.md §3)")
        elif args.runtime == "copilot":
            _die_usage("runtime=copilot forbids tokens=N/A — pass --tokens-input "
                       "(prompt_tokens) and --tokens-output (completion_tokens) summed "
                       "across the node's dispatch window (see metrics-contract.md §3)")
        provided["tokens_k"] = "N/A"
        provided["cost"] = "N/A"
    elif args.runtime == "copilot":
        # Copilot exposes prompt_tokens (input) and completion_tokens (output) only.
        # No cache class split is accessible to the agent, so cost cannot be accurately
        # priced — store the total as a scalar and cost as N/A.
        inp = _num_or_none(args.tokens_input)
        out_t = _num_or_none(args.tokens_output)
        if inp is None or out_t is None:
            _die_usage(
                "runtime=copilot requires --tokens-input (prompt_tokens) and "
                "--tokens-output (completion_tokens) — read these from each API "
                "response's usage object and sum across the node's dispatch window "
                "(see metrics-contract.md §3). --tokens-na is forbidden.")
        total = inp + out_t
        provided["tokens_k"] = int(total) if float(total).is_integer() else round(total, 2)
        provided["cost"] = "N/A"  # no class split → cannot price accurately
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
        if args.runtime == "codex":
            required_cx = ("input", "output", "cache_read")
            missing_cx = [c for c in required_cx if c not in given]
            if missing_cx:
                _die_usage(
                    "runtime=codex requires --tokens-input, --tokens-output, and "
                    "--tokens-cache-read (read from rollout-*.jsonl token_count events — "
                    "see metrics-contract.md §3). Missing: "
                    + ", ".join("--tokens-" + m.replace("_", "-") for m in missing_cx)
                    + ". Note: --tokens-cache-write defaults to 0 (Codex CLI drops "
                    "cache_write_tokens; see github.com/openai/codex/issues/32479).")
            if "cache_write" not in given:
                given["cache_write"] = "0"
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

    nodes.save_node(y, node, path, getattr(args, "flock", False))

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
    est_model = (node.get("estimate") or {}).get("model")
    act_model = provided.get("model")
    if est_model and act_model and est_model != act_model:
        suffix += (f" [model mismatch: estimated at {est_model!r},"
                   f" executed at {act_model!r} — costs not comparable]")
    sys.stdout.write(f"OK set-actual {label} {sorted(provided)}{suffix}\n")
    return 0


CLAUDE_SESSION_ENV = "CLAUDE_CODE_SESSION_ID"


def resolve_session_transcript(session_id: str = "") -> tuple:
    """(paths, session_id) for a Claude session's own transcript. ([], id) if not found.

    A session transcript is named `<session-id>.jsonl` under
    `~/.claude/projects/<slugified-cwd>/`, and every record inside carries the same
    `sessionId`. The id itself is in the environment as CLAUDE_CODE_SESSION_ID. So a
    session can identify its own transcript exactly, and does not have to be told.

    Searched across every project directory rather than only the slug for the current
    cwd: a subagent may run with a different working directory than the session that
    spawned it, and guessing the slug would reintroduce exactly the ambiguity this
    function exists to remove.
    """
    session_id = session_id or os.environ.get(CLAUDE_SESSION_ENV, "")
    if not session_id:
        return [], ""
    root = os.path.expanduser("~/.claude/projects")
    if not os.path.isdir(root):
        return [], session_id
    hits = []
    for d in sorted(os.listdir(root)):
        fp = os.path.join(root, d, f"{session_id}.jsonl")
        if os.path.exists(fp):
            hits.append(fp)
        # Subagent turns are NOT in the parent file -- no record anywhere carries
        # isSidechain in the main transcript. They live in a sibling directory named
        # for the session, and they carry the SAME sessionId, so identity still
        # verifies. Resolving only the .jsonl reported sidechain=0 and silently
        # omitted every dispatched agent's spend.
        sub = os.path.join(root, d, session_id, "subagents")
        if os.path.isdir(sub):
            hits.extend(os.path.join(sub, n) for n in sorted(os.listdir(sub))
                        if n.endswith(".jsonl"))
    return hits, session_id


def transcript_sessions(path: str) -> set:
    """The distinct `sessionId` values in a .jsonl file. Empty set if it carries none."""
    out = set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:  # blank and malformed lines alike
                    continue
                if isinstance(rec, dict) and rec.get("sessionId"):
                    out.add(str(rec["sessionId"]))
    except OSError:
        return set()
    return out


def _transcript_span(path: str, open_ts, close_ts) -> tuple:
    """(earliest, latest) aware datetimes in a transcript, or (None, None).

    A naive timestamp makes the file unusable: it cannot be ordered against the aware
    bracket, and assuming an offset would guess at someone else's clock. So does holding no
    record in [open_ts, close_ts]: a merely idle session spans it and sums to a false zero."""
    lo = hi = None
    inside = False
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                when = _parse_iso(rec.get("timestamp")) if isinstance(rec, dict) else None
                if when is None:
                    continue
                if when.tzinfo is None:
                    return None, None
                lo = when if lo is None or when < lo else lo
                hi = when if hi is None or when > hi else hi
                inside = inside or open_ts <= when <= close_ts
    except OSError:
        return None, None
    return (lo, hi) if inside else (None, None)


def discover_session_transcript(state_root: str, node_keys: dict) -> tuple:
    """(paths, session_id, refusal) for a session the environment cannot name.

    Recovery is by ELIMINATION, never preference: a candidate under any project directory
    (a subagent may run under another cwd, so no slug is guessed) is accepted only when its
    records carry exactly one sessionId, span the node's dispatch bracket, AND hold a record
    inside it. Two survivors is a REFUSAL, not a tie-break -- the original bad number came from file
    choice, not arithmetic, and it looked plausible because the cache figures matched."""
    open_ts, close_ts = dispatch_window(state_root, **node_keys)
    if open_ts is None or close_ts is None:
        gap = ("dispatch_open and dispatch_close" if open_ts is None and close_ts is None
               else "dispatch_close (the node is still in flight)" if close_ts is None
               else "dispatch_open")
        return [], "", f"no {gap} recorded for this node, so there is no complete window"
    root = os.path.expanduser("~/.claude/projects")
    hits = []
    for fp in sorted(glob.glob(os.path.join(glob.escape(root), "*", "*.jsonl"))):
        try:
            # A file last written before the bracket opened cannot span it; skipping it
            # avoids parsing every transcript on the machine (tens of MB each).
            if datetime.fromtimestamp(os.path.getmtime(fp), tz=UTC) < open_ts:
                continue
        except OSError:
            continue
        found = transcript_sessions(fp)
        lo, hi = _transcript_span(fp, open_ts, close_ts) if len(found) == 1 else (None, None)
        if lo and lo <= open_ts and hi >= close_ts:
            hits.append((fp, found.pop()))
    if len(hits) != 1:
        return [], "", (f"{len(hits)} transcripts span this node's window; refusing to "
                        f"choose between them" if hits
                        else "no transcript spans this node's window")
    fp, sid = hits[0]
    # The verified file leads and is never dropped: the lookup matches by filename, so a file
    # not named for its session would otherwise be left out of the sum.
    paths, _ = resolve_session_transcript(sid)
    return [fp] + [p for p in paths if p != fp], sid, ""


def read_transcript_usage(paths, since=None, until=None) -> dict:
    """Sum a session transcript's real token usage, by class. THE executable form of
    "read the usage fields".

    That instruction was not executable, and an agent asked to follow it by hand hit
    every trap below at once. Two of them inflate and one deflates, so the wrong answer
    came out plausible rather than obviously broken: the errors partly cancel.
    Each is handled here, and each is a property of the real file format, verified
    against a 2,482-record transcript rather than assumed:

    1. INFLATES -- **the same API call appears many times.** Assistant records are
       written repeatedly as a message streams and is revised, carrying an identical
       `message.id` and identical `usage` each time. The sample held 2,482 assistant
       records for 953 distinct ids: summing records rather than ids overstates by
       roughly 2.6x. Deduplicated here by `message.id`, keeping the first occurrence.

    2. INFLATES -- **cache creation is reported twice, two ways.** `usage` carries both
       the flat `cache_creation_input_tokens` and a nested `cache_creation` mapping of
       `ephemeral_5m/1h` counts. They are the same tokens: the nested values summed
       equalled the flat field in 2,482 of 2,482 records. Adding both double-counts the
       most expensive class. Only the flat field is read.

    3. DEFLATES -- **subagent turns are easy to miss.** Work dispatched to a subagent is
       recorded with `isSidechain: true`, and often in a different file entirely. Reading
       one file, or filtering sidechains out, silently drops whole phases -- which is the
       deflating half that made the net error look small. Sidechain records are counted,
       and `paths` accepts directories so a run split across files is summed whole.

    Returns the four class totals plus counts that let a caller sanity-check the read.
    """
    files = []
    for entry in (paths if isinstance(paths, (list, tuple)) else [paths]):
        if os.path.isdir(entry):
            for root, _dirs, names in os.walk(entry):
                files.extend(os.path.join(root, n) for n in sorted(names)
                             if n.endswith(".jsonl"))
        elif os.path.exists(entry):
            files.append(entry)

    totals = {c: 0 for c in TOKEN_CLASSES}
    seen, records, sidechain, outside, undated = set(), 0, 0, 0, 0
    for fp in files:
        try:
            fh = open(fp, "r", encoding="utf-8")  # noqa: SIM115 -- catch OSError on open, then `with fh:` below
        except OSError as e:
            sys.stderr.write(f"pm-status.py: warning — cannot read {fp}: {e}\n")
            continue
        with fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue          # torn or partial line; the log is appended to live
                if not isinstance(rec, dict) or rec.get("type") != "assistant":
                    continue
                msg = rec.get("message")
                if not isinstance(msg, dict):
                    continue
                usage = msg.get("usage")
                if not isinstance(usage, dict):
                    continue
                # Trap 1: one id, one contribution. Fall back to identity when a record
                # carries no id, so an unidentifiable turn is counted rather than dropped
                # -- erring toward the inflating side is safe here, silently losing a
                # turn is not.
                key = msg.get("id") or f"{fp}:{records}"
                records += 1
                if key in seen:
                    continue
                seen.add(key)
                # A session transcript spans everything that session ever did. One
                # observed file covered a whole epic lineage: its bare total was 330.5M
                # tokens, ~66x the sprint actually being closed, and recording that as a
                # node's actual would have poisoned calibration for the rest of the epic.
                # A window is how a node's own span is cut out of it.
                if since is not None or until is not None:
                    when = _parse_iso(rec.get("timestamp"))
                    if when is None:
                        undated += 1
                        continue
                    if (since is not None and when < since) or \
                       (until is not None and when > until):
                        outside += 1
                        continue
                if rec.get("isSidechain"):
                    sidechain += 1
                totals["input"] += _num_or_none(usage.get("input_tokens")) or 0
                totals["output"] += _num_or_none(usage.get("output_tokens")) or 0
                # Trap 2: the flat field only, never the nested mapping as well.
                totals["cache_write"] += _num_or_none(usage.get("cache_creation_input_tokens")) or 0
                totals["cache_read"] += _num_or_none(usage.get("cache_read_input_tokens")) or 0

    return {"tokens": totals, "files": len(files), "records": records,
            "unique_messages": len(seen), "sidechain_messages": sidechain,
            "outside_window": outside, "undated_skipped": undated,
            "windowed": since is not None or until is not None}


def dispatch_window(state_root: str, agent: str = "", epic: str = "",
                    sprint: str = "", story: str = ""):
    """(open_ts, close_ts) for a node's dispatch bracket. (None, None) if unbracketed.

    This is what makes a node's actual measurable at all. A session transcript records
    everything that session ever did -- one observed file spanned a whole epic lineage --
    so "the transcript" is not the same question as "this story's spend". The
    dispatch_open/dispatch_close pair already marks exactly that boundary for every spawn
    (metrics-contract.md §6); this reads it back so the token count can be cut to it.

    Matches on the keys given and ignores those left empty, so a sprint-level query does
    not have to know its stories. Uses the FIRST open and the LAST close, because a story
    is re-dispatched on every fix iteration and all of it is that story's spend.
    """
    path = events_path(state_root)
    if not os.path.exists(path):
        return None, None
    want = {"agent": agent, "epic": epic, "sprint": sprint, "story": story}
    want = {k: v for k, v in want.items() if v}
    first_open = last_close = None
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
                if rec.get("event") not in ("dispatch_open", "dispatch_close"):
                    continue
                if any(str(rec.get(k, "")) != v for k, v in want.items()):
                    continue
                when = _parse_iso(rec.get("ts"))
                if when is None:
                    continue
                if rec["event"] == "dispatch_open":
                    if first_open is None or when < first_open:
                        first_open = when
                else:
                    if last_close is None or when > last_close:
                        last_close = when
    except OSError as e:
        sys.stderr.write(f"pm-status.py: warning — could not read event log: {e}\n")
    return first_open, last_close


def cmd_usage(args) -> int:
    """Print a transcript's token usage, and the set-actual flags to record it.

    IDENTITY IS CHECKED BEFORE ARITHMETIC. Summing the wrong file is the failure this
    command exists to prevent, and it is the one that produced the original bad number:
    pointed at a task `.output` artifact instead of a session transcript, a hand-count
    reported an output figure several times below what the agent that ran the story had
    itself reported. The cache figures matched closely, so nothing looked wrong -- it was
    file choice, not arithmetic. A reader that can be aimed at the wrong file has not fixed that; it has
    moved it one step earlier.

    So: with no path, resolve this session's own transcript from the environment. With a
    path, verify the file actually is a session transcript and belongs to the expected
    session. Refuse rather than guess. `--allow-unidentified` is the deliberate override,
    and it has to be typed.
    """
    want = args.claude_session or os.environ.get(CLAUDE_SESSION_ENV, "")
    paths = list(args.transcript)
    resolved = False
    recovered = False

    if not paths:
        paths, want = resolve_session_transcript(args.claude_session)
        resolved = True
        if not paths:
            keys = {k: getattr(args, k, "") or "" for k in ("agent", "epic", "sprint", "story")}
            why = "no --state-root and node key to derive a window from"
            if args.claude_session:  # an explicit session is a constraint, never overridden
                why = "--claude-session was given, so no other session is considered"
            elif args.state_root and any(keys.values()):
                paths, found_sid, why = discover_session_transcript(args.state_root, keys)
                want = found_sid or want
                recovered = bool(paths)
            if not paths:
                sys.stderr.write(
                    "pm-status.py: cannot resolve this session's transcript — "
                    + (f"no ~/.claude/projects/*/{want}.jsonl found\n" if want else
                       f"{CLAUDE_SESSION_ENV} is not set\n")
                    + f"  Recovery by elimination also failed: {why}.\n"
                    + "  Pass the transcript path explicitly, or --claude-session ID. Refusing to\n"
                      "  guess: summing the wrong file is the error this command exists to prevent.\n")
                return 2

    if not args.allow_unidentified:
        problems = []
        for fp in paths:
            targets = [fp]
            if os.path.isdir(fp):
                targets = [os.path.join(r, n) for r, _d, ns in os.walk(fp)
                           for n in sorted(ns) if n.endswith(".jsonl")]
            for t in targets:
                found = transcript_sessions(t)
                if not found:
                    problems.append(f"{t}: carries no sessionId — this is not a session "
                                    f"transcript (a task .output artifact looks like this)")
                elif len(found) > 1:
                    # Checked BEFORE membership: a file holding two sessions is malformed
                    # whatever we were expecting, and "mixes N sessions" is the actionable
                    # diagnosis. Testing membership first reported it as a plain mismatch
                    # and hid the fact that the file itself is wrong.
                    problems.append(f"{t}: mixes {len(found)} sessions {sorted(found)}")
                elif want and want not in found:
                    problems.append(f"{t}: belongs to session(s) {sorted(found)}, not {want}")
        if problems:
            sys.stderr.write("pm-status.py: refusing to sum — cannot confirm whose transcript "
                             "this is:\n")
            for pr in problems:
                sys.stderr.write(f"  {pr}\n")
            sys.stderr.write("  Pass the right file, set --claude-session, or --allow-unidentified\n"
                             "  to override deliberately.\n")
            return 2

    since = _parse_iso(args.since) if args.since else None
    until = _parse_iso(args.until) if args.until else None
    scope_src = "explicit --since/--until" if (since or until) else ""
    node_keys = {k: getattr(args, k, "") or "" for k in ("agent", "epic", "sprint", "story")}
    if not (since or until) and any(node_keys.values()):
        if not args.state_root:
            _die_usage("--state-root is required to derive a window from a node's dispatch "
                       "bracket (or pass --since/--until yourself)")
        since, until = dispatch_window(args.state_root, **node_keys)
        named = " ".join(f"{k}={v}" for k, v in node_keys.items() if v)
        if since is None and until is None:
            sys.stderr.write(
                f"pm-status.py: no dispatch bracket found for {named} in events.jsonl —\n"
                "  refusing to report an unscoped total for a node. A session transcript spans\n"
                "  everything that session did; without the bracket there is nothing to cut it\n"
                "  to. Bracket the spawn (metrics-contract.md §6) or pass --since/--until.\n")
            return 2
        scope_src = f"dispatch bracket for {named}"

    res = read_transcript_usage(paths, since=since, until=until)
    res["scope"] = scope_src
    res["since"], res["until"] = since, until
    if not res["files"]:
        sys.stderr.write("pm-status.py: no .jsonl transcript found at the given path(s)\n")
        return 3
    # Only claim a session when identity was actually CHECKED. Printing the id from the
    # environment beside numbers read out of an unverified file is the same lie in a new
    # place -- a header that asserts provenance it does not have.
    verified = not args.allow_unidentified
    res["session"] = (want or "(unverified)") if verified else "(UNVERIFIED — --allow-unidentified)"
    res["source"] = ("recovered by elimination: the one transcript spanning the dispatch window"
                     if recovered
                     else "resolved from environment" if resolved
                     else "given on the command line, identity checked" if verified
                     else "given on the command line, identity NOT checked")
    res["paths"] = paths
    t = res["tokens"]
    total = sum(t.values())
    if args.format == "json":
        # since/until are datetimes; ISO-8601 is the shape --since/--until accept back.
        window = {k: res[k].isoformat() if res[k] is not None else None
                  for k in ("since", "until")}
        sys.stdout.write(json.dumps({**res, **window, "total": total},
                                    indent=2, sort_keys=True) + "\n")
        return 0

    k = {c: t[c] / 1000.0 for c in TOKEN_CLASSES}
    sys.stdout.write(f"session {res['session']} ({res['source']})\n")
    if res.get("scope"):
        sys.stdout.write(f"scope   {res['scope']}\n")
        sys.stdout.write(f"        {res['since']} .. {res['until']}\n")
    for fp in res["paths"]:
        sys.stdout.write(f"  {fp}\n")
    sys.stdout.write(
        f"files={res['files']} records={res['records']} "
        f"unique={res['unique_messages']} sidechain={res['sidechain_messages']}\n")
    if res["records"] > res["unique_messages"]:
        dropped = res["records"] - res["unique_messages"]
        sys.stdout.write(f"  deduplicated {dropped} repeated record(s) of the same message\n")
    if res["sidechain_messages"] == 0 and res["files"] == 1:
        sys.stdout.write("  note: no subagent (sidechain) turns seen in this file — if this "
                         "run dispatched subagents, pass their transcripts too\n")
    if res.get("windowed"):
        sys.stdout.write(f"  excluded {res['outside_window']} message(s) outside the window"
                         + (f", {res['undated_skipped']} undated\n" if res["undated_skipped"]
                            else "\n"))
    else:
        sys.stdout.write(
            "  ** UNSCOPED — this is the WHOLE SESSION, not one node. A session transcript\n"
            "     spans every story it ever ran; one observed file totalled ~66x the sprint\n"
            "     being closed. Do NOT pass this to set-actual. Scope it with --story/--sprint\n"
            "     /--epic (+ --state-root) or --since/--until. **\n")
    for c in TOKEN_CLASSES:
        sys.stdout.write(f"  {c:<12} {t[c]:>12,}  ({k[c]:.1f}k)\n")
    sys.stdout.write(f"  {'TOTAL':<12} {total:>12,}  ({total / 1000.0:.1f}k)\n\n")
    if args.model:
        try:
            sys.stdout.write(f"cost {cost_from_tokens(k, args.model, rate_overrides(args)):.2f} "
                             f"USD at {args.model} rates\n\n")
        except KeyError as e:
            _die_usage(e.args[0])
    if not res.get("windowed"):
        sys.stdout.write("set-actual flags withheld: an unscoped session total is not a "
                         "node's actual.\n")
        return 0
    sys.stdout.write("set-actual flags:\n  " + " ".join(
        f"--tokens-{c.replace('_', '-')} {k[c]:.3f}" for c in TOKEN_CLASSES) + "\n")
    return 0
