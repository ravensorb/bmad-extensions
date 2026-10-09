# Agent Instruction Block Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write a marker-wrapped l3io section into a consuming project's AI instruction file, maintained across install, upgrade and uninstall, and offered once per harness when the project is opened under a harness that does not have it.

**Architecture:** A pure marker engine (string in, string out, no I/O) sits under a new `pm-status.py` subcommand that maps `{runtime}` to a file path and applies the engine. The block body is a shipped asset under `skills/_shared/`, synced like every other shared file. Install, upgrade and uninstall call the subcommand; activation calls the existing one-time notice ledger.

**Tech Stack:** Python 3.11+ (PEP-723, `uv run`), `ruamel.yaml` (already a dependency of `pm-status.py`), `unittest`, Node for the sync and doc gates.

**Spec:** `docs/superpowers/specs/2026-10-09-agent-instruction-block-design.md`

## Global Constraints

- `skills/_shared/` is the canonical source for every shared file. **Edit there, then run `npm run sync:scripts`.** Per-skill copies are generated and a direct edit is silently overwritten.
- **Never hand-edit a `payload-manifest.json`.** Regenerate with `node scripts/write-payload-manifest.mjs` whenever a payload file changes; `npm run sync:scripts` does not do it.
- `skills/_shared/pm-status.py` stays within the **10,000-line** cap (ADR-0001).
- The shipped asset stays **under 2 KB**, asserted by a test.
- **Never write an instruction file for a harness that is not running** (spec §2.2).
- **Never delete the instruction file**, even if it is empty after removal (spec §3).
- **Nothing outside the marker pair is ever modified.**
- Upgrade compares the **body**, not the version string (spec §2.1).
- Conventional Commits, and every commit signed off: `git commit -s`.
- No flags on any `/l3io-*` invocation in any markdown (check 31).

## Review Focus

These are input classes the spec implies but which no task's happy path exercises. Each has its test assigned to the task that owns the code.

1. **CRLF line endings.** A Windows-authored `CLAUDE.md` has `\r\n`. A marker regex anchored on `\n` alone will either miss the markers or leave a stray `\r` on splice. → Task 1.
2. **Markers inside a fenced code block.** This repo's own docs will show the marker syntax. A naive search matches the example and splices the wrong region. → Task 1.
3. **Two opening markers** from a bad merge or a hand-duplicated block. Replacing "between the markers" is undefined. → Task 1.
4. **A file that is not valid UTF-8.** Reading it raises, and an unhandled raise during install aborts an install that was otherwise fine. → Task 3.
5. **Two skills activating concurrently** against one project. `pm-status.py` locks every other mutation; an unlocked read-modify-write here can interleave and lose a block. → Task 3.

---

### Task 1: The marker engine (pure functions)

**Files:**
- Create: `skills/_shared/agent_instructions.py`
- Test: `skills/_shared/tests/test-agent-instructions.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `BEGIN_RE`, `END_RE`, `find_block(text) -> (start, end, version) | None`, `apply_block(text, body, version) -> (new_text, action)` where `action` is one of `"created"`, `"replaced"`, `"unchanged"`; `remove_block(text) -> (new_text, action)` where `action` is `"removed"` or `"absent"`. Both raise `BlockError` on an unbalanced or duplicated marker.

- [ ] **Step 1: Write the failing tests**

```python
#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Marker engine for the agent instruction block. Pure string transforms, no I/O."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent_instructions import (  # noqa: E402
    BlockError, apply_block, find_block, remove_block,
)

BODY = "## LiquidLogicLabs Extensions (l3io)\n\nState is machine-written.\n"


class TestFind(unittest.TestCase):
    def test_absent_returns_none(self):
        self.assertIsNone(find_block("# My Project\n\nNotes.\n"))

    def test_finds_and_reports_version(self):
        text = f"<!-- l3io:begin v=3.2.6 -->\n{BODY}<!-- l3io:end -->\n"
        start, end, version = find_block(text)
        self.assertEqual(version, "3.2.6")
        self.assertEqual(text[start:end], text)

    def test_crlf_file_is_found(self):
        # Review Focus 1. A Windows-authored instruction file.
        text = f"<!-- l3io:begin v=3.2.6 -->\r\n{BODY}<!-- l3io:end -->\r\n".replace("\n", "\r\n")
        self.assertIsNotNone(find_block(text))

    def test_marker_inside_a_fenced_code_block_is_not_a_block(self):
        # Review Focus 2. Our own docs show this syntax; it must not match.
        text = ("# Docs\n\n```markdown\n<!-- l3io:begin v=1.0.0 -->\nexample\n"
                "<!-- l3io:end -->\n```\n")
        self.assertIsNone(find_block(text))

    def test_two_opening_markers_raise(self):
        # Review Focus 3. A bad merge. "Between the markers" is undefined; refuse.
        text = ("<!-- l3io:begin v=1 -->\na\n<!-- l3io:end -->\n"
                "<!-- l3io:begin v=2 -->\nb\n<!-- l3io:end -->\n")
        with self.assertRaises(BlockError):
            find_block(text)

    def test_opening_without_closing_raises(self):
        with self.assertRaises(BlockError):
            find_block("<!-- l3io:begin v=1 -->\nstranded\n")


class TestApply(unittest.TestCase):
    def test_creates_on_empty_file(self):
        out, action = apply_block("", BODY, "3.2.6")
        self.assertEqual(action, "created")
        self.assertIn("<!-- l3io:begin v=3.2.6 -->", out)
        self.assertIn("<!-- l3io:end -->", out)

    def test_appends_without_disturbing_existing_content(self):
        before = "# My Project\n\nUser notes.\n"
        out, action = apply_block(before, BODY, "3.2.6")
        self.assertEqual(action, "created")
        self.assertTrue(out.startswith(before))

    def test_identical_body_is_unchanged_even_when_version_differs(self):
        # Spec 2.1: upgrade compares the BODY. A version bump alone must not rewrite
        # a file in the user's repo.
        text, _ = apply_block("", BODY, "3.2.6")
        out, action = apply_block(text, BODY, "9.9.9")
        self.assertEqual(action, "unchanged")
        self.assertEqual(out, text)

    def test_changed_body_is_replaced_in_place(self):
        text, _ = apply_block("prefix\n", BODY, "3.2.6")
        out, action = apply_block(text, "## New\n\nDifferent.\n", "3.3.0")
        self.assertEqual(action, "replaced")
        self.assertTrue(out.startswith("prefix\n"))
        self.assertIn("v=3.3.0", out)
        self.assertNotIn("State is machine-written", out)

    def test_content_outside_the_markers_survives_replacement(self):
        before = "TOP\n\n" + apply_block("", BODY, "3.2.6")[0] + "\nBOTTOM\n"
        out, _ = apply_block(before, "## New\n\nX.\n", "3.3.0")
        self.assertTrue(out.startswith("TOP\n\n"))
        self.assertTrue(out.rstrip().endswith("BOTTOM"))

    def test_is_idempotent(self):
        once, _ = apply_block("", BODY, "3.2.6")
        twice, action = apply_block(once, BODY, "3.2.6")
        self.assertEqual(action, "unchanged")
        self.assertEqual(once, twice)


class TestRemove(unittest.TestCase):
    def test_removes_only_the_block(self):
        text = "TOP\n\n" + apply_block("", BODY, "3.2.6")[0] + "\nBOTTOM\n"
        out, action = remove_block(text)
        self.assertEqual(action, "removed")
        self.assertNotIn("l3io:begin", out)
        self.assertIn("TOP", out)
        self.assertIn("BOTTOM", out)

    def test_absent_block_is_not_an_error(self):
        out, action = remove_block("# Nothing here\n")
        self.assertEqual(action, "absent")
        self.assertEqual(out, "# Nothing here\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run skills/_shared/tests/test-agent-instructions.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent_instructions'`

- [ ] **Step 3: Write the implementation**

```python
#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""The marker engine for the agent instruction block: pure string transforms, no I/O.

Separated from the subcommand that calls it so the splice logic can be tested without a
filesystem. Every function takes text and returns text; nothing here opens a file.

WHY THE MARKERS ARE HTML COMMENTS. They render invisibly, survive a markdown reformat, and
are greppable. The repo already uses body markers this way (`resolver-invariant:
canonical-contract`), so this follows a precedent rather than inventing a form.

WHY A FENCED BLOCK IS EXCLUDED. This package's own documentation shows the marker syntax. A
naive search would match the example and splice the wrong region of whatever file documented
the feature -- including, eventually, a user's own notes about it.
"""
import re

BEGIN_RE = re.compile(r"^<!--\s*l3io:begin(?:\s+v=(?P<v>[^\s>]+))?\s*-->[ \t]*$", re.M)
END_RE = re.compile(r"^<!--\s*l3io:end\s*-->[ \t]*$", re.M)
_FENCE_RE = re.compile(r"^[ \t]*(?:```|~~~)", re.M)


class BlockError(Exception):
    """The file's markers are not a single well-formed pair."""


def _fenced_spans(text):
    """Character ranges inside fenced code blocks. Fences toggle; an unclosed fence runs to
    the end of the file, which is what a markdown renderer does too."""
    spans, open_at = [], None
    for m in _FENCE_RE.finditer(text):
        if open_at is None:
            open_at = m.start()
        else:
            spans.append((open_at, m.end()))
            open_at = None
    if open_at is not None:
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


def _render(body, version, nl):
    body = body.strip("\n")
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
    if _strip_markers(current, nl) == _strip_markers(rendered, nl):
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
    out = text[:start] + text[end:]
    while (nl + nl + nl) in out:
        out = out.replace(nl + nl + nl, nl + nl)
    return out, "removed"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run skills/_shared/tests/test-agent-instructions.py`
Expected: PASS, 14 tests.

- [ ] **Step 5: Verify the fence exclusion is load-bearing**

Mutate `find_block` to skip the fence filter (use the raw `finditer` lists), re-run, and confirm `test_marker_inside_a_fenced_code_block_is_not_a_block` fails. Restore.

Run: `uv run skills/_shared/tests/test-agent-instructions.py 2>&1 | tail -3`
Expected after mutation: `FAILED (failures=1)`. After restore: `OK`.

- [ ] **Step 6: Commit**

```bash
git add skills/_shared/agent_instructions.py skills/_shared/tests/test-agent-instructions.py
git commit -s -m "feat(l3io-pm): marker engine for the agent instruction block"
```

---

### Task 2: The shipped asset and its sync wiring

**Files:**
- Create: `skills/_shared/agent-instructions.md`
- Modify: `scripts/sync-shared-scripts.mjs` (new sync group, beside `acDimensionFiles`)
- Modify: `CLAUDE.md` (one row in the Shared Files table)
- Test: `skills/_shared/tests/test-agent-instructions.py` (append a size assertion)

**Interfaces:**
- Consumes: nothing.
- Produces: `skills/_shared/agent-instructions.md`, delivered to each module home as `assets/agent-instructions.md`.

- [ ] **Step 1: Write the failing size test**

Append to `skills/_shared/tests/test-agent-instructions.py`:

```python
class TestShippedAsset(unittest.TestCase):
    ASSET = Path(__file__).resolve().parent.parent / "agent-instructions.md"

    def test_asset_exists(self):
        self.assertTrue(self.ASSET.is_file(), f"missing {self.ASSET}")

    def test_stays_under_2kb(self):
        # This block enters every agent's context in the consuming project, on every
        # invocation, forever. l3io-doctor's SKILL.md once reached 96,980 B and every
        # invocation paid for procedures it never ran; the same discipline applies harder
        # here, because this is not even our file.
        size = self.ASSET.stat().st_size
        self.assertLess(size, 2048, f"asset is {size} B; budget is 2048 B")

    def test_covers_the_six_required_points(self):
        text = self.ASSET.read_text(encoding="utf-8")
        for needle in ["pm-status.py", "never hand-edit", "conversational",
                       "actual", "calibrat", "rates"]:
            self.assertIn(needle.lower(), text.lower(), f"asset omits {needle!r}")

    def test_contains_no_flagged_invocation(self):
        # Check 31's rule, enforced at the source: no /l3io-* invocation carries a --flag.
        text = self.ASSET.read_text(encoding="utf-8")
        self.assertNotRegex(text, r"/l3io-[a-z0-9-]+[^\n`]*\s--[a-z]")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run skills/_shared/tests/test-agent-instructions.py TestShippedAsset`
Expected: FAIL — `missing .../agent-instructions.md`

- [ ] **Step 3: Write the asset**

Create `skills/_shared/agent-instructions.md`:

```markdown
## LiquidLogicLabs Extensions (l3io)

This project has the l3io BMad extensions installed: sprint/epic orchestration, architecture
review, red-team security review, and project-state utilities.

**PM state is machine-written. Never hand-edit a file under the state tree.** Every status,
estimate and actuals write goes through `pm-status.py`, which performs it as one atomic,
comment-preserving operation under a lock. Free-form edits were dropped and malformed under
parallel runs, which is why that writer exists.

**Invocation is conversational.** These skills take plain intent, or a positional scope token
like `E007` or `E007-S02`. None of them parse `--flags`.

- `/l3io-help` — what to do next, based on current project state
- `/l3io-plan` — validate readiness, elaborate stories, estimate, build the execution plan
- `/l3io-execute` — run the plan: dev, review, QA, fix loop, sprint and epic closure
- `/l3io-doctor` — diagnostics and housekeeping; run it with no argument for a health check
- `/l3io-arch-review`, `/l3io-sec-redteam` — architecture and security review
- `/l3io-sync` — mirror state to GitHub Issues

**Estimates and actuals are both mandatory** at story, sprint and epic level, across five
metrics. `cost` is never entered: it is derived from recorded tokens and the model's rate card.

**The system learns from what you record.** Calibration derives its ratios from actuals, so
inaccurate actuals degrade every future estimate in this project — including estimates for work
you have not planned yet. Record what happened, not what was expected.

**Rate cards go stale.** Cost is `tokens × the model's per-class rates`. When the models in use
change, the shipped table may no longer match published pricing. `pm-status.py rates` prints the
table in force, and `modules.l3io-pm.token_rates` overrides it per model. Check current pricing
rather than assuming, whenever you see a model the table does not name.
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run skills/_shared/tests/test-agent-instructions.py TestShippedAsset`
Expected: PASS, 4 tests. If the size test fails, cut prose — do not raise the budget.

- [ ] **Step 5: Add the sync group**

In `scripts/sync-shared-scripts.mjs`, after the `acDimensionFiles` declaration:

```javascript
// The agent instruction block body, shipped to each module home so install/upgrade can write
// it into the consuming project's own instruction file.
const agentInstructionFiles = [
  { src: path.join(sharedDir, "agent-instructions.md"), rel: "assets/agent-instructions.md" },
];
```

And in `syncGroups`, after the `acDimensionFiles` entry:

```javascript
  // the agent instruction block body, into each module's home only
  { files: agentInstructionFiles, dirs: moduleHomeDirs },
```

- [ ] **Step 6: Sync, regenerate manifests, add the CLAUDE.md row**

```bash
npm run sync:scripts
node scripts/write-payload-manifest.mjs
```

Add to the Shared Files table in `CLAUDE.md`, after the `ac-dimensions.md` row:

```markdown
| `skills/_shared/agent-instructions.md` | `assets/agent-instructions.md` | each module's HOME only: `l3io-setup`, `l3io-doctor`, `l3io-sec-redteam`, `l3io-arch-review` — the block body written into a consuming project's AI instruction file |
```

- [ ] **Step 7: Verify the gates**

Run: `npm run check:scripts && npm run check:manifest && npm run check:docs`
Expected: all three pass. `check:docs` fails if the `CLAUDE.md` row is missing — that is check 24 doing its job.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -s -m "feat(l3io-pm): ship the agent instruction block body as a shared asset"
```

---

### Task 3: The `sync-agent-instructions` subcommand

**Files:**
- Modify: `skills/_shared/pm-status.py` (new `cmd_` function and parser registration near the `notice` registration at ~line 8307)
- Test: `skills/_shared/tests/test-pm-status.py` (append a `TestAgentInstructions` class)

**Interfaces:**
- Consumes: `agent_instructions.apply_block`, `remove_block`, `BlockError` from Task 1; the asset from Task 2.
- Produces: `pm-status.py sync-agent-instructions --runtime {claude,codex,copilot,other} --project-root P --body-file F [--version V] [--apply|--remove|--check]`. Exit 0 = acted or already correct; 1 = `--check` found the block absent; 2 = usage error, unreadable file, or ambiguous markers.

- [ ] **Step 1: Write the failing tests**

Append to `skills/_shared/tests/test-pm-status.py`:

```python
class TestAgentInstructions(unittest.TestCase):
    """The instruction-block subcommand. Covers Review Focus 4 (non-UTF-8) and 5 (locking).

    Runs the CLI as a SUBPROCESS rather than through Base.run_main: run_main returns
    (code, stdout) and does not capture stderr, and several assertions here are about the
    refusal message. The concurrency case needs real processes anyway -- the same shape
    TestConcurrentNoticeDistinctKeys already uses.
    """

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)

    def _body(self, text="## l3io\n\nBody.\n"):
        p = Path(self.d) / "body.md"
        p.write_text(text, encoding="utf-8")
        return str(p)

    def _run(self, *argv):
        import subprocess
        return subprocess.run([sys.executable, SCRIPT, "sync-agent-instructions", *argv],
                              capture_output=True, text=True)

    def test_claude_runtime_writes_claude_md(self):
        r = self._run("--runtime", "claude", "--project-root", self.d,
                      "--body-file", self._body(), "--version", "9.9.9", "--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("l3io:begin v=9.9.9",
                      (Path(self.d) / "CLAUDE.md").read_text(encoding="utf-8"))

    def test_copilot_runtime_writes_its_own_file_not_claude(self):
        self._run("--runtime", "copilot", "--project-root", self.d,
                  "--body-file", self._body(), "--apply")
        self.assertTrue((Path(self.d) / ".github" / "copilot-instructions.md").is_file())
        self.assertFalse((Path(self.d) / "CLAUDE.md").exists(),
                         "must never write a file for a harness that is not running")

    def test_apply_is_idempotent(self):
        a = ("--runtime", "claude", "--project-root", self.d,
             "--body-file", self._body(), "--version", "1.0.0", "--apply")
        self._run(*a)
        first = (Path(self.d) / "CLAUDE.md").read_bytes()
        r = self._run(*a)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(first, (Path(self.d) / "CLAUDE.md").read_bytes())
        self.assertIn("unchanged", r.stdout)

    def test_remove_leaves_the_file_and_the_user_content(self):
        f = Path(self.d) / "CLAUDE.md"
        f.write_text("# Mine\n\nKeep me.\n", encoding="utf-8")
        self._run("--runtime", "claude", "--project-root", self.d,
                  "--body-file", self._body(), "--apply")
        r = self._run("--runtime", "claude", "--project-root", self.d, "--remove")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(f.is_file(), "the file must never be deleted")
        text = f.read_text(encoding="utf-8")
        self.assertIn("Keep me.", text)
        self.assertNotIn("l3io:begin", text)

    def test_round_trip_restores_the_file_byte_for_byte(self):
        f = Path(self.d) / "CLAUDE.md"
        original = "# Mine\n\nKeep me.\n"
        f.write_text(original, encoding="utf-8")
        self._run("--runtime", "claude", "--project-root", self.d,
                  "--body-file", self._body(), "--apply")
        self._run("--runtime", "claude", "--project-root", self.d, "--remove")
        self.assertEqual(f.read_text(encoding="utf-8"), original)

    def test_check_reports_absent_with_exit_1(self):
        r = self._run("--runtime", "claude", "--project-root", self.d, "--check")
        self.assertEqual(r.returncode, 1)

    def test_undecodable_file_exits_2_and_writes_nothing(self):
        # Review Focus 4. An unhandled raise here would abort an otherwise fine install.
        f = Path(self.d) / "CLAUDE.md"
        f.write_bytes(b"\xff\xfe not utf-8 \x00")
        before = f.read_bytes()
        r = self._run("--runtime", "claude", "--project-root", self.d,
                      "--body-file", self._body(), "--apply")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(f.read_bytes(), before)
        self.assertIn("utf-8", r.stderr.lower())

    def test_ambiguous_markers_exit_2_and_write_nothing(self):
        f = Path(self.d) / "CLAUDE.md"
        dup = ("<!-- l3io:begin v=1 -->\na\n<!-- l3io:end -->\n"
               "<!-- l3io:begin v=2 -->\nb\n<!-- l3io:end -->\n")
        f.write_text(dup, encoding="utf-8")
        r = self._run("--runtime", "claude", "--project-root", self.d,
                      "--body-file", self._body(), "--apply")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(f.read_text(encoding="utf-8"), dup)

    def test_concurrent_applies_do_not_duplicate_the_block(self):
        # Review Focus 5. Two skills activating at once against one project.
        import subprocess
        body = self._body()
        procs = [subprocess.Popen(
            [sys.executable, SCRIPT, "sync-agent-instructions", "--runtime", "claude",
             "--project-root", self.d, "--body-file", body, "--apply"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(4)]
        for pr in procs:
            pr.communicate()
            self.assertEqual(pr.returncode, 0)
        text = (Path(self.d) / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertEqual(text.count("l3io:begin"), 1,
                         "concurrent writes duplicated the block -- the lock must cover the "
                         "READ as well as the write")

```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run skills/_shared/tests/test-pm-status.py TestAgentInstructions`
Expected: FAIL — `invalid choice: 'sync-agent-instructions'`

- [ ] **Step 3: Implement the subcommand**

Add to `skills/_shared/pm-status.py`, beside the other `cmd_` functions:

```python
_RUNTIME_INSTRUCTION_FILE = {
    "claude": ("CLAUDE.md",),
    "copilot": (".github", "copilot-instructions.md"),
    "codex": ("AGENTS.md",),
    "other": ("AGENTS.md",),
}


def cmd_sync_agent_instructions(args) -> int:
    """Create, replace or remove the l3io block in the running harness's instruction file.

    NEVER writes a file for a harness that is not running: the target comes from --runtime
    alone. That rule is inherited from update-ai-rules Step AR5, where writing AGENTS.md
    under Claude put a block in a file belonging to another AI system.

    NEVER deletes the file. --remove strips the block and leaves whatever else is there,
    including nothing.

    Exit 2 covers usage, an undecodable file, and ambiguous markers -- all cases where we
    must not write. A caller that treats nonzero as "do not proceed" handles them alike.
    """
    from agent_instructions import BlockError, apply_block, remove_block

    parts = _RUNTIME_INSTRUCTION_FILE[args.runtime]
    target = os.path.join(args.project_root, *parts)

    if not args.remove and not args.check and not args.body_file:
        sys.stderr.write("pm-status.py: sync-agent-instructions: --apply needs --body-file\n")
        return 2
    try:
        text = ""
        if os.path.isfile(target):
            with open(target, encoding="utf-8") as fh:
                text = fh.read()
    except UnicodeDecodeError as e:
        sys.stderr.write(f"pm-status.py: sync-agent-instructions: {target} is not valid "
                         f"utf-8 ({e}); refusing to write\n")
        return 2

    try:
        if args.check:
            from agent_instructions import find_block
            return 0 if find_block(text) else 1
        if args.remove:
            out, action = remove_block(text)
        else:
            with open(args.body_file, encoding="utf-8") as fh:
                body = fh.read()
            out, action = apply_block(text, body, args.version or PM_STATUS_VERSION)
    except BlockError as e:
        sys.stderr.write(f"pm-status.py: sync-agent-instructions: {target}: {e}\n")
        return 2

    if action in ("unchanged", "absent"):
        sys.stdout.write(f"OK sync-agent-instructions {action} {target}\n")
        return 0
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    _atomic_text_write(target, out)
    sys.stdout.write(f"OK sync-agent-instructions {action} {target}\n")
    return 0
```

Add the plain-text atomic writer this needs — `pm-status.py` has `_atomic_dump` (YAML only,
and it calls `_require_epic_lock`, which this path has no epic for) and `_atomic_create`
(refuses an existing path). Neither fits, so add a third beside them:

```python
def _atomic_text_write(path: str, text: str) -> None:
    """Temp file in the same directory, then os.replace. Unlike `_atomic_dump` this takes
    no epic lock -- the target is a user-owned document outside the state tree, so the
    epic-lock invariant does not apply and asserting it would fail every call."""
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".l3io-ai-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
```

`newline=""` is load-bearing: the engine already matched the file's CRLF convention, and
Python's default translation would rewrite every line ending on a Windows-authored file.

Wrap the read-modify-write in a `flock` on a sibling lock file, so concurrent activations
serialize. Follow `notices_lock`: the lock must cover the **read** as well as the write, or
two callers each read the pre-write text and the second overwrites the first's block.
Register the parser beside `notice`:

```python
    ai = sub.add_parser("sync-agent-instructions",
                        help="create, replace or remove the l3io block in the running "
                             "harness's AI instruction file")
    ai.add_argument("--runtime", required=True,
                    choices=("claude", "codex", "copilot", "other"))
    ai.add_argument("--project-root", required=True)
    ai.add_argument("--body-file")
    ai.add_argument("--version")
    g = ai.add_mutually_exclusive_group(required=True)
    g.add_argument("--apply", action="store_true")
    g.add_argument("--remove", action="store_true")
    g.add_argument("--check", action="store_true")
    ai.set_defaults(func=cmd_sync_agent_instructions)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run skills/_shared/tests/test-pm-status.py TestAgentInstructions`
Expected: PASS, 9 tests. If the concurrency test fails, the lock is missing or too narrow —
it must cover read *and* write, not just the write.

- [ ] **Step 5: Verify the line cap and the full suite**

Run: `wc -l skills/_shared/pm-status.py && uv run skills/_shared/tests/test-pm-status.py 2>&1 | tail -3`
Expected: under 10,000 lines (ADR-0001), and `OK`.

- [ ] **Step 6: Sync, regenerate manifests, commit**

```bash
npm run sync:scripts && node scripts/write-payload-manifest.mjs
git add -A
git commit -s -m "feat(l3io-pm): sync-agent-instructions writes the block into the harness file"
```

---

### Task 4: Install, upgrade and uninstall wiring

**Files:**
- Modify: `skills/l3io-doctor/steps/install.md` (§2 Upgrade, §3 Clean)
- Modify: `skills/_shared/module-setup.md` (install path)

**Interfaces:**
- Consumes: `pm-status.py sync-agent-instructions` from Task 3; `assets/agent-instructions.md` from Task 2.
- Produces: no code; prose directives validated by `check:docs`.

- [ ] **Step 1: Add the upgrade directive**

In `skills/l3io-doctor/steps/install.md` §2, after the upgrade command succeeds, add:

````markdown
### 2.1 Refresh the agent instruction block

The upgrade may have changed the block body. Refresh it in the running harness's instruction
file — this rewrites only the region between the `l3io:begin`/`l3io:end` markers, and writes
nothing at all when the body is unchanged:

```bash
uv run {pm_status} sync-agent-instructions --runtime {runtime} \
  --project-root {project-root} \
  --body-file {skill-root}/assets/agent-instructions.md --apply
```

Exit 2 means the file has ambiguous markers or is not valid UTF-8; report it and continue —
a documentation block must never fail an upgrade that otherwise succeeded.
````

- [ ] **Step 2: Add the clean directive**

In `skills/l3io-doctor/steps/install.md` §3, after the payload removal, add:

````markdown
### 3.1 Remove the agent instruction block

The block is **not payload** — it lives in a user-owned file and is not covered by the
SHA-256 comparison above, so the payload sweep cannot see it. Remove it by its markers:

```bash
uv run {pm_status} sync-agent-instructions --runtime {runtime} \
  --project-root {project-root} --remove
```

This never deletes the file, only the block. A file left empty is left empty.
````

- [ ] **Step 3: Add the install path**

In `skills/_shared/module-setup.md`, where setup completes, add the same `--apply` call,
preceded by a confirmation when the target file already exists and has no markers — per
ADR-0004, an existing human-authored document is proposed to, never silently appended to.

- [ ] **Step 4: Verify the gates**

Run: `npm run sync:scripts && node scripts/write-payload-manifest.mjs && npm run check:docs`
Expected: PASS. Check 4 validates the `pm-status.py` invocations against the real argparse
surface, so a mistyped flag or a missing required argument fails here.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -s -m "feat(l3io-util): maintain the instruction block across install, upgrade and clean"
```

---

### Task 5: Cross-harness notice and health-check finding

**Files:**
- Modify: `skills/_shared/steps/shared/step-00-activate.md` (new section after §2.5)
- Modify: `skills/l3io-doctor/steps/health-check.md` (new check)
- Modify: `CLAUDE.md` and `CONTRIBUTING.md` if the doctor's stated check count changes

**Interfaces:**
- Consumes: `sync-agent-instructions --check` from Task 3; `notice` (already shipped).
- Produces: no new interface.

- [ ] **Step 1: Add the activation check**

In `skills/_shared/steps/shared/step-00-activate.md`, after §2.5:

````markdown
## 2.6 Offer the agent instruction block, once per harness

A project installed under one harness has no block in another harness's file. Check, and if
it is absent offer it **once ever, per harness** — never blocking, because this fires at
activation and the user started the run for something else:

```bash
uv run {pm_status} sync-agent-instructions --runtime {runtime} \
  --project-root {project-root} --check \
  || uv run {pm_status} notice --state-root {pm_state_root} \
       --key ai-rules-missing:{runtime}
```

When `notice` exits 0, print one line offering to add it and continue. When it exits 1 it has
already been offered for this harness; say nothing. Keying per harness is the point — a single
global flag would mean the second harness is never asked.
````

- [ ] **Step 1a: Write the per-harness notice test**

Spec section 7 requires this and no other task covers it. Append to
`skills/_shared/tests/test-pm-status.py`:

```python
class TestNoticeIsPerHarness(unittest.TestCase):
    """A notice satisfied for one harness must not satisfy another, or a project opened
    under a second harness is never offered the block."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)

    def _notice(self, key):
        import subprocess
        return subprocess.run(
            [sys.executable, SCRIPT, "notice", "--state-root", self.d, "--key", key],
            capture_output=True, text=True).returncode

    def test_claude_and_copilot_keys_are_independent(self):
        self.assertEqual(self._notice("ai-rules-missing:claude"), 0, "first claude = emit")
        self.assertEqual(self._notice("ai-rules-missing:claude"), 1, "second claude = silent")
        self.assertEqual(self._notice("ai-rules-missing:copilot"), 0,
                         "copilot must still be offered after claude was satisfied")
```

Run: `uv run skills/_shared/tests/test-pm-status.py TestNoticeIsPerHarness`
Expected: PASS. This exercises the existing `notice` verb; it should pass immediately. If it
fails, the key scoping is wrong and Task 5's design does not hold.

- [ ] **Step 2: Add the health-check finding**

Append to `skills/l3io-doctor/steps/health-check.md` as the next check number (do not
renumber existing checks -- their numbers are cited by `[check N]` strings elsewhere):

```markdown
**Check {N} — Agent instruction block**
Run `uv run {pm_status} sync-agent-instructions --runtime {runtime} --project-root
{project-root} --check`.
- Exit 1 (block absent for this harness) → flag `install` · Priority: Low · name the file
  that would be written, and say that an agent without it does not know state is
  machine-written
- Exit 2 (ambiguous markers, or the file is not valid UTF-8) → flag for **manual** repair ·
  Priority: Medium · print the message; this one is never auto-fixed, because the file is
  the user's and the markers are already in a state we refused to guess about
- Exit 0 → ✓
```

- [ ] **Step 3: Update the stated mode/check counts**

If `health-check.md`'s check count is stated in `SKILL.md`, `CLAUDE.md` or `CONTRIBUTING.md`,
update every one. `check:docs` check 15 compares the doctor's stated count against reality and
fails on a mismatch, so a missed site is caught — but fix them in this step rather than
discovering it in the gate.

- [ ] **Step 4: Verify the gates and the full suites**

```bash
npm run sync:scripts && node scripts/write-payload-manifest.mjs
npm run check:docs && npm run check:scripts && npm run check:module && npm run check:manifest
npm run test:python
npm run test:scripts
```

Expected: all green.

- [ ] **Step 5: Run the BMad module validation against a real install**

```bash
npm run smoke:install
```

Expected: `smoke: PASS`, all four modules reporting zero findings outside the two known
`validate-module.py` gaps. This needs network and takes about four minutes.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -s -m "feat(l3io-pm): offer the instruction block once per harness"
```
