"""pm_status.instructions -- the agent-instruction block: the marker engine and the
instruction-file sync.

A leaf over `core`: it needs `PM_STATUS_VERSION`, `_atomic_text_write` and
`agent_instructions_lock`, and nothing above `core` imports from here except
`__main__`'s parser registration and its re-export.

CALL STYLE ACROSS MODULES. `core` is reached as a module object, never by
`from .core import <name>`: that binding is a private copy, so a mock.patch on `core`
(`_atomic_text_write` and `agent_instructions_lock` are both patched by the suite) would
never reach it and the test would pass while guarding nothing.
"""
from __future__ import annotations

import os
import re
import sys

from .. import core

# --------------------------------------------------------------------------- #
# agent instruction block -- the marker engine: pure string transforms, no I/O
#
# The markers are HTML comments: invisible when rendered, reformat-proof, greppable, and the
# repo already uses body markers this way. A FENCED block is excluded because this package's
# own docs show the marker syntax, and a naive search would splice the example's region.
# --------------------------------------------------------------------------- #
BEGIN_RE = re.compile(r"^<!--\s*l3io:begin(?:\s+v=(?P<v>[^\s>]+))?\s*-->[ \t]*(?=\r?$)", re.MULTILINE)
END_RE = re.compile(r"^<!--\s*l3io:end\s*-->[ \t]*(?=\r?$)", re.MULTILINE)
# `(?=\r?$)`, not `$`: with re.MULTILINE `$` stops only before "\n", so a CRLF file's markers never matched.
_FENCE_RE = re.compile(r"^[ \t]*(?P<run>`{3,}|~{3,})(?P<rest>[^\r\n]*)", re.MULTILINE)


class BlockError(Exception):
    """The file's markers are not a single well-formed pair."""


def _fenced_spans(text):
    """Character ranges inside fenced code blocks. A fence closes only on the same character,
    at least as long as the opener, with nothing after it but whitespace (CommonMark) -- so a
    four-backtick fence may contain a three-backtick line, and a tilde fence is not closed by
    backticks. An unclosed fence runs to the end of the file, as a renderer treats it."""
    spans, opener, open_at = [], None, None
    for m in _FENCE_RE.finditer(text):
        run = m.group("run")
        if opener is None:
            opener, open_at = run, m.start()
        elif run[0] == opener[0] and len(run) >= len(opener) and not m.group("rest").strip():
            spans.append((open_at, m.end()))
            opener = open_at = None
    if opener is not None:
        spans.append((open_at, len(text)))
    return spans


def _outside_fences(matches, spans):
    return [m for m in matches
            if not any(lo <= m.start() < hi for lo, hi in spans)]


def find_block(text):
    """(start, end, version) of the block, or None. Raises BlockError when the markers are
    not exactly one well-formed pair -- a duplicated or stranded marker makes "between the
    markers" undefined, and guessing would truncate the user's own content."""
    spans = _fenced_spans(text)
    begins = _outside_fences(list(BEGIN_RE.finditer(text)), spans)
    ends = _outside_fences(list(END_RE.finditer(text)), spans)
    if not begins and not ends:
        return None
    if len(begins) != 1 or len(ends) != 1:
        raise BlockError(
            f"expected exactly one l3io:begin/l3io:end pair, found "
            f"{len(begins)} begin and {len(ends)} end marker(s). Fix the file by hand: "
            f"replacing between ambiguous markers could delete content that is not ours.")
    b, e = begins[0], ends[0]
    if e.start() < b.start():
        raise BlockError("l3io:end appears before l3io:begin")
    return b.start(), e.end(), b.group("v")


def _normalise_nl(text, nl):
    """Every line ending in `text` becomes `nl`, whatever it was."""
    return text.replace("\r\n", "\n").replace("\n", nl)


def _render(body, version, nl):
    body = _normalise_nl(body.strip("\n"), nl)
    return nl.join([f"<!-- l3io:begin v={version} -->", body, "<!-- l3io:end -->"])


def _newline(text):
    """Match the file's existing convention so a CRLF file stays CRLF."""
    return "\r\n" if "\r\n" in text else "\n"


def apply_block(text, body, version):
    """Create, replace, or leave alone. Returns (text, 'created'|'replaced'|'unchanged')."""
    nl = _newline(text)
    found = find_block(text)
    rendered = _render(body, version, nl)
    if found is None:
        sep = "" if text == "" else (nl if text.endswith(nl) else nl + nl)
        return text + sep + rendered + nl, "created"
    start, end, _ = found
    current = text[start:end]
    # Compare BODY, not version: a release that does not change the text must not rewrite a
    # file in the user's repo just to bump a string they did not ask about.
    if _strip_markers(_normalise_nl(current, nl), nl) == _strip_markers(rendered, nl):
        return text, "unchanged"
    return text[:start] + rendered + text[end:], "replaced"


def _strip_markers(block, nl):
    lines = block.split(nl)
    return nl.join(lines[1:-1]).strip()


def remove_block(text):
    """Returns (text, 'removed'|'absent'). Never deletes anything outside the pair."""
    found = find_block(text)
    if found is None:
        return text, "absent"
    nl = _newline(text)
    start, end, _ = found
    before, after = text[:start], text[end:]
    # Touch only the seam: the block's own line terminator, plus at most one separator blank
    # line that `apply_block` put there. Blank lines anywhere else belong to the user.
    after = after.removeprefix(nl)
    if before.endswith(nl + nl) and (after == "" or after.startswith(nl)):
        before = before[:-len(nl)]
    out = before + after
    return out, "removed"


_RUNTIME_INSTRUCTION_FILE = {
    "claude": ("CLAUDE.md",),
    "copilot": (".github", "copilot-instructions.md"),
    "codex": ("AGENTS.md",),
    "other": ("AGENTS.md",),
}


def _other_instruction_files(project_root: str, runtime: str) -> list:
    """Every known instruction file that is NOT the running harness's, deduplicated.

    `codex` and `other` share AGENTS.md, so the distinct paths are fewer than the runtimes.
    Order is stable for reproducible output.
    """
    mine = os.path.join(project_root, *_RUNTIME_INSTRUCTION_FILE[runtime])
    seen, out = {mine}, []
    for rt in sorted(_RUNTIME_INSTRUCTION_FILE):
        p = os.path.join(project_root, *_RUNTIME_INSTRUCTION_FILE[rt])
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _foreign_blocks(project_root: str, runtime: str) -> list:
    """`(path, version)` for every OTHER harness's instruction file already holding our block.

    A project that switches harness -- or that was set up before the target was decided by
    `--runtime` alone -- keeps our block in the file the old harness used. That block is ours
    and carries our version marker, so leaving it is not neutrality: two blocks that disagree
    are two sets of instructions, and harnesses routinely read more than one of these files.
    A file with no block of ours is not listed; it is simply not ours to touch.
    """
    out = []
    for p in _other_instruction_files(project_root, runtime):
        if not os.path.isfile(p):
            continue
        try:
            with open(p, encoding="utf-8", newline="") as fh:
                found = find_block(fh.read())
        except (UnicodeDecodeError, OSError, BlockError):
            continue        # unreadable or ambiguous: reported by the running file's own path
        if found:
            out.append((p, found[2]))       # (start, end, version)
    return out


def cmd_sync_agent_instructions(args) -> int:
    """Create, replace or remove the l3io block in the running harness's instruction file.

    NEVER CREATES a file for a harness that is not running: the target comes from --runtime
    alone, so running under Claude never puts a block into AGENTS.md.

    THE OTHER HALF OF THAT RULE LIVES IN `l3io-doctor/steps/update-ai-rules.md` Step AR5,
    which applies it to the legacy-reference migration. Same rule, two mechanisms, and it has
    to change in both: it was argued correctly in AR5 for a long time while this side was
    silently missing the refresh half below. A rule argued in the mechanism that happened to
    need it first does not propagate itself.

    ALWAYS REFRESHES a block already present in another harness's file. The two rules are
    not in tension -- the first is about whose file we may colonise, the second about our own
    content. A project that switches harness, or that predates the --runtime rule, keeps our
    block where the old harness read it; that block carries our version marker, and leaving
    it stale means two sets of our instructions disagreeing in one repo, which harnesses
    that read several of these files will both pick up. Refreshing, not removing, because a
    project may genuinely still use the other harness.

    NEVER deletes the file. --remove strips the block from every file that has one and
    leaves whatever else is there, including nothing.

    Exit 0 = acted or already correct; 1 = --check found the block absent for this harness;
    2 = usage, an undecodable file, or ambiguous markers -- all cases where we must not
    write; 3 = --check found this harness's block current but another harness's file holding
    a STALE copy, which --apply repairs.
    """
    target = os.path.join(args.project_root, *_RUNTIME_INSTRUCTION_FILE[args.runtime])

    if not args.remove and not args.check and not args.body_file:
        sys.stderr.write("pm-status.py: sync-agent-instructions: --apply needs --body-file\n")
        return 2
    def _undecodable(path, e):
        sys.stderr.write(f"pm-status.py: sync-agent-instructions: {path} is not valid "
                         f"utf-8 ({e}); refusing to write\n")
        return 2

    extra = []
    body = ""
    if not args.remove and not args.check:
        try:
            # Default universal newlines: the body is normalised, only the TARGET keeps its
            # own convention (a CRLF body would otherwise leave a stray \r in an LF file).
            with open(args.body_file, encoding="utf-8") as fh:
                body = fh.read()
        except UnicodeDecodeError as e:
            return _undecodable(args.body_file, e)
        except OSError as e:
            sys.stderr.write(f"pm-status.py: sync-agent-instructions: {e}\n")
            return 2

    def _read_target():
        if not os.path.isfile(target):
            return ""
        with open(target, encoding="utf-8", newline="") as fh:
            return fh.read()

    try:
        if args.check:
            # A pure query: no lock, so it never creates _bmad/ or a lock file (it runs at
            # every skill activation, and under a mistyped --project-root). Its answer is
            # advisory and inherently racy, so the lock would buy nothing.
            try:
                here = find_block(_read_target())
            except UnicodeDecodeError as e:
                return _undecodable(target, e)
            if not here:
                return 1
            stale = [(p, v) for p, v in _foreign_blocks(args.project_root, args.runtime)
                     if v != (args.version or core.PM_STATUS_VERSION)]
            for p, v in stale:
                sys.stderr.write(f"pm-status.py: sync-agent-instructions: {p} holds an l3io "
                                 f"block at v={v}, not v="
                                 f"{args.version or core.PM_STATUS_VERSION} -- --apply refreshes "
                                 f"it\n")
            return 3 if stale else 0
        # The lock spans the READ as well as the write: otherwise two callers each read the
        # pre-write text and the second silently overwrites the first's block.
        with core.agent_instructions_lock(args.project_root):
            try:
                text = _read_target()
            except UnicodeDecodeError as e:
                return _undecodable(target, e)
            if args.remove:
                out, action = remove_block(text)
            else:
                out, action = apply_block(text, body, args.version or core.PM_STATUS_VERSION)
            if action not in ("unchanged", "absent"):
                os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
                core._atomic_text_write(target, out)
            # Our block in the other harnesses' files, refreshed in place. Existing blocks
            # only -- `apply_block` is never reached for a file without one, so no file is
            # created here and a file we never wrote to stays untouched.
            for p, _v in _foreign_blocks(args.project_root, args.runtime):
                with open(p, encoding="utf-8", newline="") as fh:
                    ftext = fh.read()
                if args.remove:
                    fout, faction = remove_block(ftext)
                else:
                    fout, faction = apply_block(ftext, body,
                                                args.version or core.PM_STATUS_VERSION)
                if faction not in ("unchanged", "absent"):
                    core._atomic_text_write(p, fout)
                    extra.append(f"{faction} {p}")
    except BlockError as e:
        sys.stderr.write(f"pm-status.py: sync-agent-instructions: {target}: {e}\n")
        return 2
    except OSError as e:
        sys.stderr.write(f"pm-status.py: sync-agent-instructions: {e}\n")
        return 2
    tail = ("; also " + ", ".join(extra)) if extra else ""
    sys.stdout.write(f"OK sync-agent-instructions {action} {target}{tail}\n")
    return 0
