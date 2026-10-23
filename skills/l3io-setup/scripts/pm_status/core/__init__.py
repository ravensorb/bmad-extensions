"""pm_status.core -- the dependency root: primitives nothing else in the package is
below.

Constants and the status vocabulary, the ruamel round-trip, atomic file writes, the
`.gitignore` rules that keep lock files out of git, every lock family (including the epic
lock), the error/exit-code contract, the key shapes and canonicalisers, the event-log
WRITER, value helpers, `self-install` and `package_root`.

It imports nothing from this package, and that is checked rather than asserted: the
boundary measurement resolves every name referenced in these definitions against the rest
of `__main__.py` and reports zero upward edges. Keep it that way -- a single import back
up makes the package a cycle and `__main__.py` unextractable.

CALL STYLE ACROSS MODULES. Six names here are mock.patch targets in the suite:
`_atomic_dump`, `_load`, `_atomic_text_write`, `notices_lock`, `agent_instructions_lock`
and `_SHIPPED_SHAS`. Reach them as `core.<name>` from the module object, never through a
`from .core import <name>` binding -- that binding is a private copy, so a patch on this
module never reaches it and the test passes while guarding nothing. The other names are
re-exported into `__main__` by name for the facade's sake; promote any of them to
module-qualified calls the moment the suite starts patching it.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import UTC, datetime

try:
    from ruamel.yaml import YAML
except ModuleNotFoundError:  # pragma: no cover - environment guard
    sys.stderr.write(
        "pm-status.py: ruamel.yaml is required. Run via `uv run` (auto-provisions it) "
        "or `pip install ruamel.yaml`.\n"
    )
    sys.exit(2)

# --------------------------------------------------------------------------- #
# Version, and the status/metric vocabulary every layer above validates against.
# --------------------------------------------------------------------------- #
# The constant half of the version. The other half is `__main__.py`'s top-of-file
# `# pm-status-version:` marker, which self-install reads off a copy on disk; check:version
# finds this declaration by searching the package and fails unless the two agree.
PM_STATUS_VERSION = "3.5.2"

VALID_STORY_STATUS = {"backlog", "ready-for-dev", "in-progress", "review", "done", "blocked"}
VALID_SPRINT_STATUS = {"backlog", "in-progress", "review", "done"}
VALID_EPIC_STATUS = {"backlog", "in-progress", "done"}

# Story transitions. Enforced per-story only; sprints and epics keep their looser enum-only
# check because they compose from their children. See
# docs/superpowers/specs/2026-09-25-story-lifecycle-blocked-design.md §3.
#
# The table gates two invariants: the blocked lifecycle (entered only from `in-progress` or
# `review` -- a never-picked-up story is not blocked, just not ready, and its impediment
# belongs in state/issues.yaml -- and exited only back to work or done-with-resolution) and
# the terminality of `done`. Free movement between other statuses stays allowed: existing
# consumers move a story backwards after a fix, and gating that would be scope creep.
VALID_STORY_TRANSITIONS = {
    "backlog":       {"ready-for-dev", "in-progress", "review", "done"},
    "ready-for-dev": {"backlog", "in-progress", "review", "done"},
    "in-progress":   {"backlog", "ready-for-dev", "review", "done", "blocked"},
    "review":        {"backlog", "ready-for-dev", "in-progress", "done", "blocked"},
    "blocked":       {"in-progress", "done"},   # done requires --resolution
    # done is "operationally reopenable" -- reopen paths, idempotent second-done, and
    # the import-node-then-set-status ordering all move a done story to another non-
    # blocked status. The one thing we still forbid is done -> blocked, so a story
    # reopened for more work goes through in-progress before it can block, which keeps
    # `blocked` entered only from active work rather than from history.
    "done":          {"backlog", "ready-for-dev", "in-progress", "review", "done"},
}
METRIC_FIELDS = ("elapsed_hours", "man_hours", "hitl_hours", "tokens_k", "cost")

# The subset of METRIC_FIELDS whose SCOPE ratio is learned. `cost` is derived
# from tokens x rates (Tasks 6/7) rather than entered or actualed on its own,
# so letting it also accumulate a scope-ratio sample would give a derived
# value an independently-learned correction — exactly the drift this rework
# removes. `cost` deliberately stays IN METRIC_FIELDS: it is still stored,
# verified, and reported, just never scope-calibrated. Derived (not restated)
# from METRIC_FIELDS so the two can't drift apart the way separately-typed
# copies did before.
CALIBRATED_METRIC_FIELDS = tuple(m for m in METRIC_FIELDS if m != "cost")


# --------------------------------------------------------------------------- #
# Key shapes and status folders: pure string vocabulary, no filesystem knowledge.
#
# The resolver section in __main__.py owns the other half -- turning one of these
# names into a path that exists. These are here because the primitives below need
# them: _state_root_of_node and _file_lock read STATUS_DIRS, and epic_lock_path
# builds its name from epic_dirname.
# --------------------------------------------------------------------------- #
STATUS_DIRS = ("active", "planned", "archived")  # active first: hottest path

# DIR_FOR_STATUS is DERIVED, never written out a second time -- two hand-kept
# halves of one mapping is how they drift apart.
STATUS_FOR_DIR = {"planned": "backlog", "active": "in-progress", "archived": "done"}
DIR_FOR_STATUS = {status: folder for folder, status in STATUS_FOR_DIR.items()}


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


def canonical_epic_key(v) -> str:
    """'3'/'03'/'003'/'E3'/'e003' -> 'E003'. The KEY form, for files that store keys.

    Two canonical forms exist on purpose and the difference is per-file, not arbitrary:
    `issues.yaml` stores bare digits ('003') because `canonical_bl_key` slices them straight
    out of `BL-E003-007`, and `events.jsonl` stores key form ('E003') because its story
    records already derive `epic` from `parse_story_key`, which yields 'E001'. Forcing one
    form everywhere would either churn every existing backlog record or make a dispatch
    event disagree with the story event beside it. So: normalise to the form the file
    already uses, and never store the caller's spelling.
    """
    return "E" + _norm_num(v, 3)


def canonical_sprint_key(v) -> str:
    """'1'/'01'/'S1'/'s01' -> 'S01'. See canonical_epic_key for why two forms exist."""
    return "S" + _norm_num(v, 2)


# --------------------------------------------------------------------------- #
# YAML round-trip and atomic writes -- the primitives every write in the package goes
# through. _load and _atomic_dump are patch targets: call them as core._load(...)
# from any other module, never through a `from .core import` binding, or a
# mock.patch on this module cannot reach the call.
# --------------------------------------------------------------------------- #
def _yaml() -> YAML:
    y = YAML()  # round-trip mode: preserves comments + key order
    y.preserve_quotes = True
    y.width = 4096  # never line-wrap scalars
    y.indent(mapping=2, sequence=2, offset=0)  # match the flush-dash status-file style
    return y


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(path: str):
    y = _yaml()
    if not os.path.exists(path):
        return y, None
    with open(path, "r", encoding="utf-8") as f:
        return y, y.load(f)


def _atomic_dump(y: YAML, data, path: str) -> None:
    """Write to a temp file in the same directory, then os.replace (atomic on POSIX).

    Every node write reaches the disk through here, so this is where the rule "an epic.yaml
    write holds its epic_node_lock" is checked (`_require_epic_lock`)."""
    _require_epic_lock(path)
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


def _atomic_text_write(path: str, text: str) -> None:
    """Temp file beside the target, fsync, then os.replace. Unlike `_atomic_dump` this takes
    no epic lock -- the target is a user-owned document outside the state tree, so the
    epic-lock invariant does not apply and asserting it would fail every call. `newline=""`
    is load-bearing: the engine already matched the file's CRLF convention, and Python's
    default translation would rewrite every line ending.

    We are a guest in the user's file, so two things are preserved: a symlink (the path is
    resolved first, so the link's real target is what changes and the link survives, with
    the temp file in the RESOLVED directory so os.replace cannot cross devices) and the
    file's mode (mkstemp makes 0600; an existing file's mode is copied, a new file gets
    0666 & ~umask)."""
    path = os.path.realpath(path)
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".l3io-ai-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        if os.path.exists(path):
            shutil.copymode(path, tmp)
        else:
            umask = os.umask(0)
            os.umask(umask)
            os.chmod(tmp, 0o666 & ~umask)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _atomic_create(path: str, text: str) -> bool:
    """Create `path` with `text` only if it does not already exist -- atomically and without
    ever clobbering: write a temp file in the same directory, fsync it, then os.link it into
    place (link fails with FileExistsError when the path exists, where os.replace would
    overwrite). Returns False when the path already existed. The temp file is removed on
    every path, success or failure."""
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".pm-status.", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.link(tmp, path)
        except FileExistsError:
            return False
        return True
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# Lock-file hygiene: one mechanism puts both `*.lock` and the notices ledger into the
# state root's own .gitignore, so neither is ever committed.
# --------------------------------------------------------------------------- #
# State roots whose .gitignore this process has already checked (_ensure_lock_ignore).
_LOCK_IGNORE_CHECKED = set()
_LOCK_IGNORE_LINE = "*.lock"
NOTICES_FILENAME = ".notices.yaml"  # the one-time-ever advisory ledger, keyed on --key
                                     # alone (the `notice` verb, which stays above core) --
                                     # no pruning: a project's set of distinct notice keys
                                     # stays small by construction
# Every filename pm-status.py writes at a state root that must never reach git: the
# per-family lock sidecars (one glob covers all of them) and the notices ledger.
_GITIGNORE_PATTERNS = (_LOCK_IGNORE_LINE, NOTICES_FILENAME)


def _lock_rule_present(text: str, pattern: str = _LOCK_IGNORE_LINE) -> bool:
    """True when git reads `text` (a .gitignore) as ignoring every `pattern`: some line is
    exactly `pattern` and no LATER line is exactly `!pattern`. Parsed as git parses it: split
    on "\\n" only -- never str.splitlines(), which also breaks on U+0085 and other characters
    git keeps inside a line -- and strip exactly one trailing "\\r", then trailing spaces,
    since leading spaces are part of the pattern. The caller decodes with utf-8-sig, so a
    leading UTF-8 BOM is skipped, as git skips it. A narrower negation such as `!keep.lock`
    is a deliberate user choice and is left as written."""
    present = False
    for raw in text.split("\n"):
        line = raw.removesuffix("\r")
        line = line.rstrip(" ")
        if line == pattern:
            present = True
        elif line == "!" + pattern:
            present = False
    return present


def _missing_ignore_patterns(text: str, patterns=_GITIGNORE_PATTERNS):
    """Which of `patterns` git does NOT currently read `text` as ignoring."""
    return [p for p in patterns if not _lock_rule_present(text, p)]


def _ensure_lock_ignore(state_root: str, patterns=_GITIGNORE_PATTERNS) -> None:
    """Make `{state_root}/.gitignore` carry every pattern in `_GITIGNORE_PATTERNS` --
    `*.lock` and `.notices.yaml` -- so neither a lock file nor the notices ledger is ever
    committed.

    Every lock file this script creates is an empty flock target -- the several families in
    the state root and the per-node `.yaml.lock` sidecars below it -- and the sprint-closure
    checkpoint stages the whole state tree; `.notices.yaml` is the one non-lock file this
    script writes at the state root that is equally advisory and equally not for git. Neither
    pattern matches the state-root directory itself, so step-00-activate's `git check-ignore`
    gate still passes.

    Called on EVERY lock acquisition inside a state root, not only when a pattern's file is
    first written: a project whose lock files already exist, or that adopts a newer
    pm-status.py that adds a pattern, gets the missing rule(s) on its next lock. A bare
    `append-issue --file` outside a state root (no status folders, no --state-root) is
    skipped, so it never writes a .gitignore into a repo root (_file_lock). Memoized per
    process, so each state root is checked at most once. Absent file -> created (no-clobber
    _atomic_create) with one comment line and every pattern. Present -> READ first, and only
    when at least one pattern is missing (as git reads it, _lock_rule_present) is it opened
    for append and flocked, then re-checked under the flock so two processes cannot both
    append it -- only the still-missing patterns are written, so an already-satisfied pattern
    is never duplicated; a read-only .gitignore that already has every pattern is never opened
    for writing. Missing lines are appended after a newline when the file lacks a trailing
    one; existing content is never rewritten or reordered. Best-effort: this runs inside the
    lock path, so an OSError or an undecodable file warns once on stderr and returns -- it
    never raises and never fails the verb.

    `patterns` narrows what is written, for a directory that is not a state root: the
    agent-instruction lock under `_bmad/` needs only `*.lock`, not the notices ledger."""
    root = os.path.realpath(state_root or ".")
    if root in _LOCK_IGNORE_CHECKED:
        return
    _LOCK_IGNORE_CHECKED.add(root)
    path = os.path.join(root, ".gitignore")
    try:
        if not os.path.lexists(path) and _atomic_create(
                path, "# pm-status.py state files -- never commit\n" +
                      "".join(f"{p}\n" for p in patterns)):
            return
        with open(path, "rb") as fh:                # read first: needs no write access
            if not _missing_ignore_patterns(fh.read().decode("utf-8-sig"), patterns):
                return
        try:
            import fcntl
        except ImportError:  # pragma: no cover - non-POSIX
            fcntl = None
        with open(path, "a+b") as fh:
            if fcntl is not None:
                fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                fh.seek(0)
                text = fh.read().decode("utf-8-sig")   # re-check under the flock; BOM skipped
                missing = _missing_ignore_patterns(text, patterns)
                if not missing:
                    return
                sep = "" if not text or text.endswith("\n") else "\n"
                fh.write((sep + "".join(f"{p}\n" for p in missing)).encode("utf-8"))
                fh.flush()
            finally:
                if fcntl is not None:
                    fcntl.flock(fh, fcntl.LOCK_UN)
    except (OSError, UnicodeDecodeError) as e:
        sys.stderr.write(f"pm-status.py: warning -- could not add "
                         f"{', '.join(patterns)} to {path}: {e}\n")


def _state_root_of_node(path: str):
    """The state root above a node file: the parent of the nearest ancestor named for a
    status folder (active/planned/archived). None when there is no such ancestor."""
    d = os.path.dirname(os.path.abspath(path))
    while True:
        parent = os.path.dirname(d)
        if os.path.basename(d) in STATUS_DIRS:
            return parent
        if parent == d:
            return None
        d = parent


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
    state_root = _state_root_of_node(path)
    if state_root is not None:                  # never a .gitignore inside a node directory
        _ensure_lock_ignore(state_root)
    with open(lock_path, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            _atomic_dump(y, data, path)
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


# --------------------------------------------------------------------------- #
# Errors and the exit-code contract.
# --------------------------------------------------------------------------- #
def _die_usage(msg: str):
    sys.stderr.write(f"pm-status.py: {msg}\n")
    sys.exit(2)


def _die_notfound(what: str):
    sys.stderr.write(f"pm-status.py: node not found — {what}\n")
    sys.exit(3)


class PMError(Exception):
    """A refusal or failure raised by a non-exiting core function.

    Core functions never call sys.exit: in-process callers -- the set-status done
    hook, promote-issue's estimate -- must be able to catch a failure. Only a cmd_
    wrapper turns one into an exit code, through _run_core."""

    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code = code
        self.msg = msg


def _run_core(fn) -> int:
    """Run a cmd_ body, mapping PMError onto the exit-code contract."""
    try:
        return fn()
    except PMError as e:
        sys.stderr.write(f"pm-status.py: {e.msg}\n")
        return e.code


# --------------------------------------------------------------------------- #
# The event-log WRITER. Its readers (dwell, dispatch windows, the events index) are a
# metrics concern and stay above; appending is a primitive, because every status and
# actuals write reaches it and it must never be able to fail its caller.
# --------------------------------------------------------------------------- #
EVENTS_FILENAME = "events.jsonl"


def events_path(state_root: str) -> str:
    """The one project-level event log. A single log (not one per sprint) keeps the
    progress report a single read and makes cross-epic velocity computable."""
    return os.path.join(state_root, EVENTS_FILENAME)


def append_event(state_root: str, payload: dict) -> None:
    """Append one JSON line under flock. NEVER raises: telemetry must not be able to
    fail a status write, matching the calibration contract in set-actual."""
    try:
        p = events_path(state_root)
        os.makedirs(os.path.dirname(os.path.abspath(p)) or ".", exist_ok=True)
        line = json.dumps(payload, sort_keys=True) + "\n"
        try:
            import fcntl
        except ImportError:  # pragma: no cover - non-POSIX
            fcntl = None
        with open(p, "a", encoding="utf-8") as fh:
            if fcntl is not None:
                fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                fh.write(line)
                fh.flush()
            finally:
                if fcntl is not None:
                    fcntl.flock(fh, fcntl.LOCK_UN)
    except Exception as e:  # noqa: BLE001 - deliberate: never fail the caller
        sys.stderr.write(f"pm-status.py: warning — could not append event: {e}\n")


def _event_keys(kind: str, args) -> dict:
    """Node-identifying fields for an event payload, by node kind."""
    if kind == "story":
        epic_key, sprint_key, _ = parse_story_key(args.story)
        return {"node": "story", "key": args.story, "epic": epic_key, "sprint": sprint_key}
    # Canonical, not raw. `_dispatch_identity` is (agent, epic, sprint, story), so a close
    # spelled differently from its open never cancels it and the dispatch reports as
    # permanently stalled in `report --stall-minutes`. Measured: open --epic 003 then close
    # --epic E003 leaves 1 dispatch open. The story branch above already yields key form via
    # parse_story_key; these two now match it instead of echoing the caller.
    if kind == "sprint":
        sk = canonical_sprint_key(args.sprint)
        return {"node": "sprint", "key": sk, "epic": canonical_epic_key(args.epic), "sprint": sk}
    ek = canonical_epic_key(args.epic)
    return {"node": "epic", "key": ek, "epic": ek, "sprint": None}


# --------------------------------------------------------------------------- #
# State-root files that have a lock family, and the lock families themselves. Each path
# function sits with its lock rather than with the code that reads the file: the lock
# needs it first, and every reader goes through the lock.
# --------------------------------------------------------------------------- #
def calibration_path(state_root: str) -> str:
    return os.path.join(state_root, "pm-calibration.yaml")


def adr_register_path(state_root: str) -> str:
    return os.path.join(state_root, "adr-register.yaml")


def notices_path(state_root: str) -> str:
    return os.path.join(state_root, NOTICES_FILENAME)


# Re-entrant within a process: flock is held per open file description, so a
# second open()+LOCK_EX from the same process would deadlock against itself.
# The depth counter lets save_calibration nest inside calibration_lock (which
# is exactly what the record_* paths do) without reacquiring.
_CAL_LOCK = {"depth": 0, "fh": None}


@contextlib.contextmanager
def _file_lock(lock_path: str, depth_state: dict, state_root: str | None = None):
    """Exclusive flock over a read-modify-write cycle, reentrant per process.

    Extracted from calibration_lock so the ADR register can hold a lock without a
    second implementation. The reentrancy counter is the part that must not be
    re-derived by hand: a nested acquire that re-opens the file drops the outer
    hold on close, and the failure only appears under real parallelism.

    `depth_state` is a dict private to one lock family (e.g. `_CAL_LOCK` or
    `_ADR_LOCK`) with at least a `"depth"` key; each family gets its own dict so
    a calibration hold and an ADR-register hold never share depth counting.

    `state_root` is the root whose .gitignore gets `*.lock` (_ensure_lock_ignore). The
    calibration, ADR and epic families pass theirs, and issues_lock passes the issues file's
    directory whenever that path came from a state root. Without one -- only a bare
    `append-issue --file X` -- the lock's own directory is used only if it holds a status
    folder: X's directory might be the repo root, where `*.lock` would silently ignore
    uv.lock, yarn.lock and Cargo.lock repo-wide.
    """
    if depth_state["depth"] > 0:               # already held by this process
        depth_state["depth"] += 1
        try:
            yield
        finally:
            depth_state["depth"] -= 1
        return
    try:
        import fcntl
    except ImportError:  # pragma: no cover - non-POSIX
        sys.stderr.write(f"pm-status.py: fcntl unavailable — {lock_path} is not "
                         f"lock-protected (non-POSIX)\n")
        yield
        return
    lock_dir = os.path.dirname(os.path.abspath(lock_path)) or "."
    os.makedirs(lock_dir, exist_ok=True)
    if state_root is not None:
        _ensure_lock_ignore(state_root)
    elif any(os.path.isdir(os.path.join(lock_dir, s)) for s in STATUS_DIRS):
        _ensure_lock_ignore(lock_dir)           # a bare --file that does sit in a state root
    fh = open(lock_path, "w")  # noqa: SIM115 -- the fd outlives this statement; flock holds it until the finally
    fcntl.flock(fh, fcntl.LOCK_EX)
    depth_state["depth"], depth_state["fh"] = 1, fh
    try:
        yield
    finally:
        depth_state["depth"], depth_state["fh"] = 0, None
        try:
            fcntl.flock(fh, fcntl.LOCK_UN)
        finally:
            fh.close()


@contextlib.contextmanager
def calibration_lock(state_root: str):
    """Hold an exclusive lock over a whole calibration read-modify-write cycle.

    `save_calibration` alone is not enough: load -> mutate -> save is not atomic,
    so two parallel `set-actual` calls could both load the same file and the
    second save would drop the first's sample. Callers that mutate must wrap the
    load AND the save in this.
    """
    with _file_lock(calibration_path(state_root) + ".lock", _CAL_LOCK, state_root):
        yield


_ADR_LOCK = {"depth": 0, "fh": None}


@contextlib.contextmanager
def adr_register_lock(state_root: str):
    """Hold an exclusive lock over a whole ADR-register read-modify-write cycle.

    Same reasoning as calibration_lock: load -> mutate -> save is not atomic, and
    this is exactly the register two parallel adr-reserve calls must not race on.
    """
    with _file_lock(adr_register_path(state_root) + ".lock", _ADR_LOCK, state_root):
        yield


_NOTICES_LOCK = {"depth": 0, "fh": None}


@contextlib.contextmanager
def notices_lock(state_root: str):
    """Hold an exclusive lock over a whole notices read-modify-write cycle.

    Same reasoning as calibration_lock and adr_register_lock: load -> mutate -> save is
    not atomic, and two concurrent callers -- e.g. `l3io-execute` and `l3io-plan`
    invoked around the same time in one project -- must not both decide the same key has
    not been shown yet and each write their own "now recorded" copy, silently dropping one.
    """
    with _file_lock(notices_path(state_root) + ".lock", _NOTICES_LOCK, state_root):
        yield


_AGENT_INSTR_LOCK = {"depth": 0, "fh": None}


@contextlib.contextmanager
def agent_instructions_lock(project_root: str):
    """Exclusive lock over the whole read-modify-write of an AI instruction file.

    Same reasoning as notices_lock: two skills activating at once must not both read the
    pre-write text and let the second overwrite the first's block. The lock file lives under
    `_bmad/` -- the tool's own directory -- never beside the user's document, and `*.lock`
    is added to `_bmad/.gitignore` on every acquisition (self-healing, additive, via
    `_ensure_lock_ignore`). state_root is None for `_file_lock` because `_bmad/` is not a
    state root and would otherwise also receive the notices pattern.
    """
    bmad = os.path.join(project_root, "_bmad")
    _ensure_lock_ignore(bmad, (_LOCK_IGNORE_LINE,))
    with _file_lock(os.path.join(bmad, ".agent-instructions.lock"),
                    _AGENT_INSTR_LOCK, None):
        yield


_ISSUES_LOCK = {"depth": 0, "fh": None}


@contextlib.contextmanager
def issues_lock(file_path: str, bare_file: bool = False):
    """Hold an exclusive lock over a whole issues.yaml read-modify-write cycle.

    Same reasoning as calibration_lock/adr_register_lock: load -> allocate a key
    -> dedupe-check -> mutate -> save is not atomic, and `issues.yaml` is a shared
    append target across every epic and every parallel subagent -- exactly what
    ADR numbers needed a register for after two parallel agents both read the
    same near-empty directory and chose the same number. The lock file is keyed off
    the OPEN issues file's path: `issues_paths(state_root)[0]` for every issue verb,
    which all address the files through `--state-root` (status-files.md §7), or
    `append-issue`'s compatibility `--file`, which must equal that path when
    `--state-root` is also given -- so both addressing forms contend on one lock. The
    resolved file lives beside it and is covered by the same hold (IssueStore loads
    both issue files under it).

    `bare_file` is True only for `append-issue --file` given without --state-root. Every
    other path is `issues_paths(state_root)[0]`, so its directory IS the state root and is
    passed on as one; a bare --file's directory is not trusted to be one (_file_lock).
    """
    with _file_lock(file_path + ".lock", _ISSUES_LOCK,
                    None if bare_file else os.path.dirname(os.path.abspath(file_path))):
        yield


_EPIC_NODE_LOCK = {"depth": 0, "fh": None, "path": None}


def epic_lock_path(state_root: str, epic_key: str) -> str:
    """One epic's lock file: `{state_root}/epic-{nnn}.lock`.

    OUTSIDE the epic's directory, deliberately. move-epic / archive-epic `git mv` that whole
    directory between status folders. A lock file inside it would travel with it: a waiter
    that had resolved the old path would then lock a file that is no longer there (and
    recreate the old directory to hold it) while later callers lock the moved file -- two
    holders of one lock. A name built from the state root and the epic key alone is the same
    before, during and after a move, and for every spelling of the key ('E001', '001', '1')
    and of the root (relative or absolute -- realpath)."""
    return os.path.join(os.path.realpath(state_root), epic_dirname(epic_key) + ".lock")


@contextlib.contextmanager
def epic_node_lock(state_root: str, epic_key: str):
    """Hold an exclusive lock over one epic's epic.yaml read-modify-write cycle.

    Same reasoning as calibration_lock/adr_register_lock/issues_lock: load -> decide -> save
    is not atomic. set-lock needs the lock for mutual exclusion (two sessions both reading
    "no live foreign lock" and both claiming), and every other epic.yaml writer needs it so a
    concurrent holder cannot overwrite its change with a stale copy -- promote's roll-up once
    restored a `_lock` that clear-lock, which took no lock, had just removed. `_atomic_dump`
    refuses an epic.yaml write made without it (`_require_epic_lock`). Each epic is its own
    contention domain, so the lock is per epic (epic_lock_path), not per state root.

    Callers resolve the epic, take this lock, then RESOLVE AGAIN inside it: move-epic holds
    it too, so a move that landed while a caller waited has moved the directory its first
    answer named. They resolve first as well, so an absent epic exits 3 with no lock file
    created.

    ONE EPIC AT A TIME. The re-entrancy counter is per lock family, not per epic, so a nested
    acquire of a SECOND epic's lock would skip its flock silently; it raises instead.
    Re-entry on the same epic (promote -> rollup_parent_estimate) nests on the one flock.

    LOCK ORDER, enforced: the epic lock is taken first, never under issues_lock or
    calibration_lock. promote holds epic -> issues and set-actual holds epic -> calibration;
    a FRESH epic lock taken inside either would invert that order and can deadlock against
    them, so it raises. A same-epic re-entry is not fresh -- promote's roll-up re-enters its
    epic under issues_lock -- and is allowed."""
    lock_path = epic_lock_path(state_root, epic_key)
    held = _EPIC_NODE_LOCK["path"]
    if held is not None and held != lock_path:
        raise RuntimeError(f"epic_node_lock: {lock_path} requested while {held} is held -- "
                           f"one epic lock at a time")
    if held is None and (_ISSUES_LOCK["depth"] or _CAL_LOCK["depth"]):
        under = "issues_lock" if _ISSUES_LOCK["depth"] else "calibration_lock"
        raise RuntimeError(f"epic_node_lock: lock order -- {lock_path} requested under {under}; "
                           f"the epic lock is taken first, never under issues_lock or "
                           f"calibration_lock")
    with _file_lock(lock_path, _EPIC_NODE_LOCK, state_root):
        _EPIC_NODE_LOCK["path"] = lock_path
        try:
            yield
        finally:
            if held is None:
                _EPIC_NODE_LOCK["path"] = None


def _require_epic_lock(path: str) -> None:
    """Refuse an epic.yaml write unless this process holds THAT epic's epic_node_lock.

    Called from `_atomic_dump`, which every node write reaches, so the rule is checked on
    every write pm-status.py makes rather than trusted to a list of verbs -- the list once
    left clear-lock, move-epic and the node verbs all writing epic.yaml unlocked. Files made
    outside this script (doctor's bootstrap-state heredoc, agent-written migrate-state
    output) are not covered; they only create epic files, so there is nothing to race. A
    RuntimeError, not a PMError: no input causes this, only a code path that skipped the
    lock."""
    if os.path.basename(path) != "epic.yaml":
        return
    epic_dir = os.path.dirname(os.path.abspath(path))
    state_root = os.path.dirname(os.path.dirname(epic_dir))
    want = os.path.join(os.path.realpath(state_root), os.path.basename(epic_dir) + ".lock")
    if _EPIC_NODE_LOCK["path"] != want:
        raise RuntimeError(f"{path} written without its epic_node_lock ({want}) -- "
                           f"every epic.yaml write must hold it")


# --------------------------------------------------------------------------- #
# Value helpers: parsing, coercion and the estimate/actual accessors. Pure, no I/O
# except the two that read a file's bytes.
# --------------------------------------------------------------------------- #
def _parse_iso(ts):
    """Parse a pm-status timestamp into an aware datetime, or None if unusable."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).strip())
    except (TypeError, ValueError):
        return None


def _lock_age_minutes(claimed, now=None) -> float:
    """Minutes elapsed since `claimed` (an aware datetime, e.g. from `_parse_iso`).

    Shared by cmd_check_lock and cmd_set_lock so their TTL arithmetic cannot diverge
    into two independently-wrong implementations.
    """
    return ((now or datetime.now(UTC)) - claimed).total_seconds() / 60.0


def _hashable_field(v):
    """A hashable stand-in for a field read out of `events.jsonl`.

    Used by every reader over that log that keys a dict on a record field. The log is
    append-only, written by concurrent flock'd writers and documented as possibly torn,
    so a field can hold any JSON type -- and a list or a dict is unhashable, which turns
    `idx[rec["key"]]` into `TypeError: unhashable type` and takes down the reader.

    The readers all guarded the RECORD (`isinstance(rec, dict)`) and none guarded a
    field inside it, so the same defect existed four times over: in
    `_dispatch_identity`, where it crashed `report --watch`; in `build_events_index`,
    where `ev.get("key")` was only truthy-checked and a non-empty list is truthy; and in
    `actual_event_times`, where `k not in idx` raises exactly as a subscript does -- a
    membership test is not the safe alternative to indexing.

    `str()` is a floor that keeps the scan alive and the record distinguishable, not a
    conversion any caller should rely on: a malformed field has no correct value, and
    inventing one would be worse than carrying it through as its own repr.

    Carrying through is right HERE and wrong for an index -- see `_indexable_key`.
    """
    return v if isinstance(v, (str, int, float, bool)) else str(v)


def _indexable_key(v):
    """A node key usable as an index key, or None when the field cannot be one.

    The counterpart to `_hashable_field`, and the difference is the reader's job, not a
    preference. `_dispatch_identity` only needs INTERNAL consistency -- an open and its
    close hashing alike -- so a malformed field carried through under its repr still
    matches its own close, and dropping it would make that dispatch permanently
    uncloseable. An index keyed by node key is looked up BY a real node key, so a value
    that no node could ever have is not a key: carrying it adds a phantom entry
    corresponding to nothing, and dropping it loses nothing real.

    Returns None for a list, a dict, or an empty/whitespace-only string. The caller
    skips the record, which is what "a torn line must not kill the read" has always
    meant one level up.
    """
    if not isinstance(v, (str, int, float)) or isinstance(v, bool):
        return None
    k = str(v).strip()
    return k or None


def _num_or_none(v):
    """Parse a metric value, tolerating a leading '$' on cost. None if not numeric.

    Normalizing before the numeric guard (rather than after) matters: a
    check-then-lstrip order lets a '$'-prefixed cost fail _is_number and get
    skipped before the lstrip ever runs, silently starving the cost
    component of samples. This is the single normalization both the guard
    and the parse share, so they can't disagree.
    """
    if v is None or _is_na(v):
        return None
    s = str(v).strip().lstrip("$")
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _actual_metric(actual: dict, metric: str):
    """A metric's numeric actual. tokens_k is a mapping now — the total is what
    is banded and calibrated; the class split prices cost and nothing else.
    """
    v = (actual or {}).get(metric)
    if metric == "tokens_k" and hasattr(v, "get"):
        v = v.get("total")
    return _num_or_none(v)


def _estimate_metric(est: dict, metric: str):
    """A metric's numeric value from an ESTIMATE block. The single-value
    (story) form of `tokens_k` is a MAPPING (`tokens_block`'s `total` + the
    four per-class counts, since Tasks 6/7) — the same shape `_actual_metric`
    unwraps above, mirrored here for the estimate side.

    EVERY reader of an estimate's tokens_k must go through this, never
    `_num_or_none(est.get(metric))` directly. That direct form is exactly what
    silently zeroed two independent things before Task 10 found and fixed the
    first: `_child_estimate_value` (a sprint/epic roll-up would see zero
    children with a tokens_k estimate, `estimate-rollup` would just never emit
    `tokens_k_min`/`tokens_k_max`) and `derive_story_sample` (a story's
    tokens_k scope ratio never accumulated a sample — cold-start forever,
    silently, for the metric the whole cost derivation now hangs off). Both
    call sites now route through here so a fourth instance can't reintroduce
    the same blind spot by hand-duplicating the unwrap.
    """
    v = (est or {}).get(metric)
    if metric == "tokens_k" and hasattr(v, "get"):
        v = v.get("total")
    return _num_or_none(v)


def _iter_count(v):
    """fix_iterations as a non-negative int, or None if it is not one.

    Tolerant on the way in because historical nodes hold strings, and total: an
    unparseable value returns None rather than raising. `int(v)` alone raised
    ValueError on '0.0' -- inside `derive_story_sample` that aborted the whole
    sample, so a story with zero rework contributed nothing instead of the exact
    scope reading it should have.
    """
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != int(f) or f < 0:
        return None
    return int(f)


def _exit_code_or_fail(v) -> int:
    """An exit code that will not parse is a failure, never a pass.

    test_runs is hand-editable YAML, and `_iter_count` already exists here
    because historical nodes hold strings. Same tolerance — but the fallback is
    asymmetric on purpose: an unreadable exit code must never derive
    `tests_passing: true`.
    """
    try:
        return int(v)
    except (TypeError, ValueError):
        return 1


def _mid(est, low_key: str, high_key: str):
    """Midpoint of a range-form estimate. None if either bound is missing/non-numeric."""
    lo, hi = _num_or_none(est.get(low_key)), _num_or_none(est.get(high_key))
    if lo is None or hi is None:
        return None
    return (lo + hi) / 2.0


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
    """Numeric metrics become int/float unless N/A. `cost` is derived, not entered;
    the only string it can be here is N/A."""
    if _is_na(v):
        return v
    try:
        f = float(v)
        return int(f) if f.is_integer() and field != "cost" else f
    except ValueError:
        return v


def _file_sha(path: str):
    """SHA-256 of a file's bytes; None if it cannot be read."""
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


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


# --------------------------------------------------------------------------- #
# self-install: one runtime copy per project, content-guarded.
# --------------------------------------------------------------------------- #
# SHA-256 of pm-status.py at each release tag (all 93, 0.1.2 onward, incl. the pre-skills/ src/
# layout); only a match is ours to delete. Untagged commits are not covered: left, and reported.
_SHIPPED_SHAS = frozenset("""
0b1bf9c58d7a03aa87ea67244ce492bae3f73b8eb5616e573f7511a1c485e8ac 1cb92f322c3dbd0b2d2162d91c67744bc60ec1f78dd1dd9ebcba45837393f118 2835546912fbce53ff4189f5815cecd6b80a3385ef283c92b2a3785e702bdb8c 2d22901b48eee23fcd6344b6824a8eaf6b7b3759b882f21c005e514e6cc28ca1 3a8bb2052565dc99df4138c9783e04ed5ddcd0c10c52b1cf56c6009139a3a882 3b73f41eb6b1cc150f56d1defa0642f1d0dcdb20815cdd8c030c460c24a72b61 3c0aaf1dcba8299a17f54119b9f4ffd5c3ebcb1ea6be6b56a8b13c40e4aeb850 4c2869a33ece0dd3980afd9732fce865e29006d0ccc987041395d394ffdc1e92 5375b917a59672a7d6f9e90aa66557745f8208943d4f850a16293f620da98849
58304be3eff53054ce0e1fcee5ada0960ef42accca0294de510a946b3a091b8d 5a0e57a538350d7b1cef08aa641d945c7d1cd9343ca098a5d2c5074e8f4e094c 5cc905cb72aacd9f067181d75794537ef15239f376607979339890c217513af6 5f07d89cc6f86a8bd4aa7e0a68446db07ef106c6556f1798a27c5f27b7ed9e07 5f6c63a272d6bc76372306cea5d047e001a65045c7c1f6f44445d949d019c0c0 6225f178925f6d4bc99b6584722f539e81266fcfe4bc79ab39515c0b9505e467 6268681451ed45b8b2a7fbacab449b9266fd6f2479ce8bb26e9d4e2ccd4c5211 6da96cbc2fd3d18c28af0e5ae8e4fd921cc0f3928d12cff4151e964696134e0e 6fbaf4d501cc423c41637d5b27a4c633d3455127b4c930d4e0624c7725cc74f7
7683ed28d49add22ba27fb3d5a57110cc35a9f7203880d4494d4675f4a9e781a 7739897271caadaaea5f9f8ced3beeec70d50df2534cc0537e3f501f5585b521 77742439c6c0ffb4889ee9e3f7ffdaa64acd1758d61449e5e6b719b9cd341551 7c0ca2e8e79775060ae8101e3966c6f31a3f773343bf3d55ca18f4f61d063aa3 7edc4cefe0a1873b6fb99552115ba85515e1d18621aec2f225021de8c1d71c19 84401d3c2caa77192a2472872f41598d2182db152ed024ef4a0a3029585ffbfd 89adde0fb9738c86aeae323ede7731cedac5a33d98455147da5bf5fe2fa46f3e 8a3ca57a5add4a7139cf94bfa0926cb7753eb73bd157e5a70f183461871cf13e 919617bf97ccbcec177b193548651e6a7389cff0ef5113c22dbe18fc169d2217
970504a94e3f04d0ba2a9e0e7029d2be245ad977a945171cc1ba57e1043dea9e 983ad9559b66597a537df2501016a293e26925f029bd202ca2adf6ccf0883a3d 9f9035e90881f2e3eeaf901b696e05acc58b6ecd74f31aeb06a23ea8a89aa8ab a11fb30fc8d9eabd42c412bbfc98c65090ef43dc4b201b8373798b3682039712 a27ac9296f50ca5203330ed5aab9125177f86d8a02d8dee757b72b07f3d47274 a4248d7bdeb2b096aed5636de6c8bb22b7dda8d97fa3fd1eee0528956cc358c5 a79c3626b77b88256ce997488919d54010456ddf421f3048a5cda21cb211863a aa58e96235b017b91ed04ed81f1f7a8c19de12aa9e05a5e822828f73bc23cde5 b35c8f3e70794667bb19a2b4e466e698b6df3ee5b9988f3bc7b56106502975ef
b79cd5876f21dc42ead21f6c5e35bad16c884ccd8c7254c7096d44089552db55 baf8864fc988e7914691d4d0f8c2c0f79cfff8963689b55aabd77fa0c29a0b89 bb82cbfc47cb3ee69d8840f8ed2a1d36606efdc2e6cc375887f6c75ccbfb95ef bf6c0df846c8b03cf720c3d76a8f34a90943fdef4ca8f555d8f9da4c5cffe8bd d00dd34e52e4e40b0a8050b373c8add5d95822271273d8f8297293a3bf751349 d9d85d5dc9296b271f4d0ee6151237f42d2b4944b4c94468c553dfcc3660356d db7bad754dd7d717bf13c3ea267d08232634e8b267a845913b08e8c988509a35 dba663676d6d25e8813c4581b559941d0d2e37c7734de5f505983f7f65dedec7 dd7e560a0b06bca442b1aa1d5f434f8d80229570ded8d97adbb0b16f10c3396f
ddfc2d0d899e3b9965ff3dd2bcbf4121ea64e4be06809484bdf76c5972d47ddf e5103515a786c1e8ed56e152d83be3fdb74c380211720d3131847be5a7451a7a ec52c4880d48ba276d1dfc4d5466aee0ed82c9f5c71e1b42fa18ae7d13b1c5a8 ec677e57aab5919bbfb02f9410bb0a9f0ba17c5632d5bd3ee3e08efdf68c84ab ee0a1aaa15909f3e4140d77ed6641886330d1c69d742b93feeea82f02e812be0 f57547e7b9f1a7e153736b10a91fddec743e33164da6d940d624347152ca8ec4 f7bd8595f13b6692d8ca58cdbc81106180d2c923f91cb09ea2c85257aa24b5ef fbeda45557f03b44d164821f48af1174e47e876d369abf0509e37ae93395386e fbf74d157dc9e37bc8d73027c3247f587424c92ecdcf9dcb532dfbabbcbc7756
""".split())  # noqa: SIM905 -- 53 digests: a split string is 6 lines, a list literal is 53


def package_root() -> str:
    """The directory holding this package's own files: what `self-install` copies.

    TWO dirnames, not one. This file lives in the `core/` subpackage, so a single
    dirname names `core/` and self-install would copy a fragment of the package over
    the install. Whatever `core/` is called, it is always exactly one level below the
    package root. tests: test_package_root_is_the_package_dir_not_a_subpackage.
    """
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _tree_files(root: str) -> list:
    """Sorted relpaths under root, skipping bytecode (running an install writes it)."""
    return sorted(os.path.relpath(os.path.join(dp, f), root)
                  for dp, dns, fns in os.walk(root) if "__pycache__" not in dp.split(os.sep)
                  for f in fns if not f.endswith(".pyc"))


def tree_digest(root: str) -> str:
    """SHA-256 over sorted (relpath, file-sha256) pairs: any byte in any file changes it."""
    h = hashlib.sha256()
    for rel in _tree_files(root):
        h.update(f"{rel}\0{_file_sha(os.path.join(root, rel))}\n".encode())
    return h.hexdigest()


def sweep_stale(parent: str) -> list:
    """Remove `pm-status.old-*` / `pm-status.staging-*` siblings a crashed install left."""
    gone = []
    for name in sorted(os.listdir(parent)) if os.path.isdir(parent) else []:
        if name.startswith(("pm-status.old-", "pm-status.staging-")):
            shutil.rmtree(os.path.join(parent, name), ignore_errors=True)
            gone.append(name)
    return gone


def _drop_legacy_file(dest: str) -> None:
    """Delete the pre-package `pm-status.py` only if it is byte-identical to a shipped one."""
    if not os.path.isfile(dest):
        return
    if _file_sha(dest) in _SHIPPED_SHAS:
        os.unlink(dest)
        sys.stdout.write(f"OK removed legacy {dest} (an unmodified shipped copy)\n")
    else:
        sys.stderr.write(f"pm-status.py: left {dest} in place — it matches no shipped version "
                         f"(patched or pinned?); nothing invokes it any more\n")


def cmd_self_install(args) -> int:
    """Install this package as `pm-status/` beside --dest (`--dest` keeps naming the legacy file).

    Content-guarded, never version-guarded: the marker is hand-maintained and has drifted, so
    equal versions mean "compare the bytes". A strictly newer installed copy is still refused,
    since only the version can express a downgrade. Stage, rename the live tree aside, rename
    the stage in; the window between the renames is accepted (spec §4). A failed second rename
    restores the old tree, and every run first sweeps a crashed predecessor's siblings.
    """
    src, dest = package_root(), os.path.abspath(args.dest)
    parent = os.path.dirname(dest)
    live = os.path.join(parent, "pm-status")
    mine = tuple(int(x) for x in PM_STATUS_VERSION.split("."))
    os.makedirs(parent, exist_ok=True)
    sweep_stale(parent)
    theirs = _parse_version_line(os.path.join(live, "__main__.py")) if os.path.isdir(live) else None
    if os.path.isdir(live) and not args.force:
        if tree_digest(live) == tree_digest(src):
            sys.stdout.write(f"OK self-install skipped — {live} is already this exact package "
                             f"({PM_STATUS_VERSION})\n")
            _drop_legacy_file(dest)
            return 0
        if theirs is not None and theirs > mine:
            sys.stdout.write(f"OK self-install skipped — {live} is "
                             f"{'.'.join(map(str, theirs))} > {PM_STATUS_VERSION} "
                             f"(refusing to downgrade)\n")
            return 0
        if theirs == mine:
            sys.stderr.write(f"pm-status: warning — {live} reports {PM_STATUS_VERSION} but its "
                             f"content differs from this copy; reinstalling. A changed script "
                             f"shipped under an unchanged version marker.\n")
    staging, old = (f"{live}.{k}-{os.getpid()}" for k in ("staging", "old"))
    shutil.copytree(src, staging, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    os.chmod(os.path.join(staging, "__main__.py"), 0o755)
    aside = os.path.lexists(live)
    try:
        if aside:
            os.rename(live, old)
        os.rename(staging, live)
    except BaseException as e:
        state = "the previous install was restored"
        try:
            if aside and not os.path.lexists(live):
                os.rename(old, live)
        except OSError as err:
            state = f"ROLLBACK FAILED ({err}); previous install is at {old}, {live} is absent"
        shutil.rmtree(staging, ignore_errors=True)
        sys.stderr.write(f"FAILED self-install {live}: {e!r}; {state}\n")
        if not isinstance(e, OSError):
            raise
        return 1
    shutil.rmtree(old, ignore_errors=True)
    was = ".".join(map(str, theirs)) if theirs else "absent"
    sys.stdout.write(f"OK self-install {live} ({was} -> {PM_STATUS_VERSION})\n")
    _drop_legacy_file(dest)
    return 0
