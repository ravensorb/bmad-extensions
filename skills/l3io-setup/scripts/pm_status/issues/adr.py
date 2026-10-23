"""pm_status.issues.adr -- the ADR number allocator (`adr-reserve`, ADR-0005).

Hands out sequential ADR numbers from `state/adr-register.yaml` under a flock, so two
parallel arch-gate agents cannot both claim ADR-0007. The first number handed out is the
larger of the register's `next` and the highest ADR already on disk, plus one -- and when
that disk scan is impossible (not in a git work tree and no `--adr-dir`) it REFUSES rather
than printing a number derived from a home it never read.

Standalone within `issues`: it shares the bucket because the register is issue-lifecycle
state, not because it depends on the store. Nothing here imports `store`, `promote` or
`audit`; `audit` imports `load_adr_register` from here for finding 1k.

`adr_register_path` and `adr_register_lock` are in `core`, not here -- check 26 requires
state-path assembly to live with the resolver, and the lock is a core primitive.
"""

from __future__ import annotations

import glob
import os
import re
import subprocess
import sys

from .. import core
from ..core import _now_iso, adr_register_lock, adr_register_path, canonical_epic_key


def load_adr_register(state_root: str):
    """Load the ADR register, or a fresh skeleton if absent, empty, or malformed.

    Never raises: an absent file, an empty file, and a `next` that fails to
    parse as an int are all legal states that resolve to "start at 1" — a
    project with no adr-register.yaml yet must still work.
    """
    p = adr_register_path(state_root)
    y, data = core._load(p)
    if data is None:
        from ruamel.yaml.comments import CommentedMap
        reg = CommentedMap()
        reg["next"] = 1
        reg["reserved"] = []
        return y, reg
    if data.get("reserved") is None:
        data["reserved"] = []
    return y, data


# The `ADR-` prefix is optional on the one home and case-insensitive on both. The
# scan's whole reason for existing (see `highest_adr_on_disk`) is the ADR nobody
# allocated through the register -- a hand-written one -- and hand-written ADRs are
# commonly named `ADR-NNNN-slug.md`, which matched neither pattern. A real directory
# holding ADR-0004..ADR-0025 scanned as "highest is 0", exactly as confidently as an
# empty one, and `adr-reserve` then issued numbers that were already on disk.
# Widening can only raise the floor the allocator starts from, never lower it.
_ADR_DOC_NAME = re.compile(r"^(?:[Aa][Dd][Rr]-)?(\d{4})-.+\.md$")
_ADR_OLD_HOME_NAME = re.compile(r"^[Aa][Dd][Rr]-(\d{4})-.+\.md$")


def _git_toplevel(path: str):
    """The git work tree containing `path`, or None (not a repo, or no git on PATH)."""
    try:
        r = subprocess.run(["git", "-C", path, "rev-parse", "--show-toplevel"],
                           capture_output=True, check=False, text=True)
    except OSError:
        return None
    top = r.stdout.strip()
    return top if r.returncode == 0 and top else None


class AdrHomeUnresolved(Exception):
    """The one ADR home (ADR-0005) could not be located, so the disk scan is impossible.

    Raised rather than warned-and-continued. `adr-reserve` is the only thing standing
    between two agents and one ADR number, so a number allocated from a scan that never
    happened is worse than no number at all: the caller reads exit 0 and a four-digit
    string off stdout and has no way to tell it apart from a real allocation. The old
    behaviour printed `0001` next to a stderr warning nobody captured.
    """


def highest_adr_on_disk(state_root: str, adr_dir: str = "") -> int:
    """Highest ADR number already written, in the one home and in the old one (ADR-0005).

    The register still records who is in flight; this scan only stops a new reservation
    from colliding with a file that already exists: a hand-written ADR, a Mode C ADR, or
    an ADR in a project that has not run `migrate-adrs`. The one home is `adr_dir` when
    given (step files pass {project-root}/docs/adr, since a BMad project need not be the
    repository root), else <git top-level of the state root>/docs/adr.

    Raises AdrHomeUnresolved when neither is available. The default is deliberately NOT
    widened to some guess (the state root's parent, the cwd): scanning the wrong tree
    reports "highest is 0" just as confidently as scanning an empty right one.
    """
    impl = os.path.dirname(os.path.abspath(state_root))
    hi = 0
    for arch in glob.glob(os.path.join(impl, "epic-*", "arch")):
        for name in os.listdir(arch):
            m = _ADR_OLD_HOME_NAME.match(name)
            if m:
                hi = max(hi, int(m.group(1)))
    if not adr_dir:
        top = _git_toplevel(state_root if os.path.isdir(state_root) else impl)
        if top is None:
            raise AdrHomeUnresolved(
                f"{state_root} is not inside a git work tree, so the one ADR home "
                f"(<git top-level>/docs/adr) cannot be located, and the old home "
                f"(epic-*/arch/) alone does not say what numbers docs/adr already "
                f"holds. Pass --adr-dir DIR naming the project's ADR directory "
                f"(normally {{project-root}}/docs/adr) and retry.")
        adr_dir = os.path.join(top, "docs", "adr")
    if adr_dir and os.path.isdir(adr_dir):
        for name in os.listdir(adr_dir):
            m = _ADR_DOC_NAME.match(name)
            if m:
                hi = max(hi, int(m.group(1)))
    return hi


def cmd_adr_reserve(args) -> int:
    """Allocate ADR numbers before dispatch, under a lock.

    A directory listing shows who has FINISHED writing. Only a register knows
    who is in flight. Three parallel ADR agents read the same near-empty
    directory and two of them chose 0013 while two chose 0014; the surviving
    ADR-0014 was cited by four stories meaning two different documents, and
    repairing that cost more than the gate it came from.
    """
    if args.count < 1:
        sys.stderr.write("ERROR --count must be >= 1\n")
        return 2
    from ruamel.yaml.comments import CommentedMap
    with adr_register_lock(args.state_root):
        yaml, reg = load_adr_register(args.state_root)
        # Unlike a malformed `next` (recoverable -- reset to 1 and keep going),
        # a malformed `reserved` is refused outright rather than repaired: this
        # list is the record of who is in flight, which is the entire reason
        # the register exists. Silently replacing it with [] would let a new
        # reservation collide with an in-flight one it can no longer see.
        reserved = reg.get("reserved")
        if not isinstance(reserved, list):
            sys.stderr.write(
                f"pm-status.py: adr-register.yaml has a malformed 'reserved' field "
                f"(expected a list, got {type(reserved).__name__}: {reserved!r}); "
                f"refusing to reserve -- a register that cannot say who is already "
                f"in flight cannot be trusted to hand out a new number. Fix or "
                f"restore adr-register.yaml by hand, then retry.\n")
            return 2
        try:
            start = int(reg.get("next", 1))
        except (TypeError, ValueError):
            sys.stderr.write(f"pm-status.py: adr-register.yaml has a malformed "
                             f"'next' ({reg.get('next')!r}); resetting to 1\n")
            start = 1
        start = max(start, 1)
        # Refuse rather than guess. Every other failure in this function returns 2
        # before a number is printed, and so does this one: a caller capturing stdout
        # cannot tell a guessed 0001 from a scanned one.
        try:
            on_disk = highest_adr_on_disk(args.state_root, args.adr_dir)
        except AdrHomeUnresolved as exc:
            sys.stderr.write(f"pm-status.py: adr-reserve: refusing to allocate -- {exc}\n")
            return 2
        start = max(start, on_disk + 1)
        numbers = list(range(start, start + args.count))
        for n in numbers:
            entry = CommentedMap()
            entry["number"] = n
            entry["slug"] = args.slug
            entry["epic"] = canonical_epic_key(args.epic)
            entry["reserved_at"] = _now_iso()
            reg.setdefault("reserved", []).append(entry)
        reg["next"] = start + args.count
        core._atomic_dump(yaml, reg, adr_register_path(args.state_root))
    sys.stdout.write("\n".join(f"{n:04d}" for n in numbers) + "\n")
    return 0
