#!/usr/bin/env python3
"""
Tests for spec-align.py. Run with:
  uv run -q --with 'markdown-it-py>=3' --with 'mdit-py-plugins>=0.4' --with 'ruamel.yaml>=0.18' \
    --with 'unidiff>=0.7' --with 'tenacity>=8' python3 skills/_shared/tests/test-spec-align.py
Every case drives the real CLI in a subprocess. Git behaviour runs in a real temporary repo;
backlog items are created only through the real pm-status.py CLI.
"""
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest


# -- temp-dir leak guard ---------------------------------------------------------------- #
# setUpModule points tempfile.tempdir (this test process) AND the TMPDIR environment variable
# (inherited by every subprocess it spawns) at one private run directory; tearDownModule fails
# the run if anything is left in it, then removes it and restores both to their prior values.
# Covered: every tempfile.mkdtemp()/mkstemp()/NamedTemporaryFile() made by this process or by
# a child that honours TMPDIR. Not covered: a child that writes to a hard-coded directory. The
# one name it ignores is `uv-*.lock`, which `uv run` leaves in TMPDIR by design
# (test-write-module-config spawns `uv run`). Fixtures without cleanup once left 60,936
# directories in /tmp and exhausted its inodes. Set in setUpModule, not at import, so a child
# process that re-imports this module never creates a run directory it would not remove.
_RUN_TMP = None
_PREV_TMPDIR = None             # the TMPDIR environment variable, or None
_PREV_TEMPFILE_TEMPDIR = None   # tempfile.tempdir as it was before setUpModule


def setUpModule():
    global _RUN_TMP, _PREV_TMPDIR, _PREV_TEMPFILE_TEMPDIR
    _PREV_TEMPFILE_TEMPDIR = tempfile.tempdir
    _RUN_TMP = tempfile.mkdtemp(prefix="test-spec-align-")
    tempfile.tempdir = _RUN_TMP
    _PREV_TMPDIR = os.environ.get("TMPDIR")
    os.environ["TMPDIR"] = _RUN_TMP


def tearDownModule():
    tempfile.tempdir = _PREV_TEMPFILE_TEMPDIR
    if _PREV_TMPDIR is None:
        os.environ.pop("TMPDIR", None)
    else:
        os.environ["TMPDIR"] = _PREV_TMPDIR
    leaked = sorted(n for n in os.listdir(_RUN_TMP)
                    if not (n.startswith("uv-") and n.endswith(".lock")))
    shutil.rmtree(_RUN_TMP, ignore_errors=True)
    if leaked:
        raise AssertionError(f"temp-dir leak: {len(leaked)} entr"
                             f"{'y' if len(leaked) == 1 else 'ies'} left by tests without "
                             f"cleanup: {', '.join(leaked[:5])}")


HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "spec-align.py")
PM = os.path.join(os.path.dirname(HERE), "pm-status.py")
GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
PLAN = "_bmad-output/planning-artifacts"
IMPL = "_bmad-output/implementation-artifacts"
ARCH_REL = f"{PLAN}/architecture.md"
# Line numbers matter to the range assertions below:
#  1 # Architecture          5 ## Data model        9 ## Order API        17 ## Data model
# 21 ### Auth: v2 (beta)    23 last line. Sections: architecture L1-23, data-model L5-8,
# order-api L9-16, data-model-1 L17-23, auth-v2-beta L21-23.
ARCH = """# Architecture

Intro paragraph. Second sentence.

## Data model

Orders live in Postgres, one row per order. Items are JSON.

## Order API

POST /orders accepts a body.

```
# not a heading
```

## Data model

Duplicate title section.

### Auth: v2 (beta)

OIDC via the gateway.
"""


class Project(unittest.TestCase):
    """A scratch project: planning + implementation artifacts, optionally a git repo."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.planning = os.path.join(self.root, PLAN)
        self.impl = os.path.join(self.root, IMPL)
        self.state = os.path.join(self.impl, "state")
        os.makedirs(self.planning)
        os.makedirs(self.state)

    def path(self, rel):
        return os.path.join(self.root, rel)

    def write(self, rel, text):
        p = self.path(rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if isinstance(text, bytes):
            with open(p, "wb") as fh:
                fh.write(text)
        else:
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(text)
        return p

    def read(self, rel):
        with open(self.path(rel), encoding="utf-8") as fh:
            return fh.read()

    def sa(self, *args, spec_paths=None, planning=None, pm_status=None):
        g = ["--project-root", self.root, "--planning-root", planning or self.planning,
             "--impl-root", self.impl, "--state-root", self.state, "--pm-status",
             pm_status or PM]
        if spec_paths is not None:
            g += ["--spec-paths", json.dumps(spec_paths)]
        return subprocess.run([sys.executable, SCRIPT, *g, *args], capture_output=True,
                              text=True, env={**os.environ, **GIT_ENV}, cwd=self.root)

    def pm(self, *args):
        return subprocess.run([sys.executable, PM, *args], capture_output=True, text=True,
                              env={**os.environ, **GIT_ENV})

    def git(self, *args, check=True):
        r = subprocess.run(["git", "-C", self.root, *args], capture_output=True, text=True,
                           env={**os.environ, **GIT_ENV})
        if check and r.returncode != 0:
            raise AssertionError(f"git {' '.join(args)}: {r.stderr}")
        return r.stdout

    def init_git(self):
        self.git("init", "-q", "-b", "main")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "init")

    def index(self):
        return self.read(f"{IMPL}/spec/spec-index.md")


class TestBuild(Project):
    def test_indexes_headings_anchors_ranges_and_summaries(self):
        self.write(ARCH_REL, ARCH)
        r = self.sa("build")
        self.assertEqual(r.returncode, 0, r.stderr)
        idx = self.index()
        self.assertTrue(idx.startswith("# Spec index — generated by spec-align.py; do not edit\n"))
        self.assertIn(f"## architecture · {ARCH_REL}", idx)
        self.assertIn(f"- {ARCH_REL}#architecture — Architecture: Intro paragraph. (L1–23)", idx)
        self.assertIn(f"- {ARCH_REL}#data-model — Data model: Orders live in Postgres, one row "
                      f"per order. (L5–8)", idx)
        self.assertIn(f"- {ARCH_REL}#order-api — Order API: POST /orders accepts a body. (L9–16)",
                      idx)
        self.assertIn(f"- {ARCH_REL}#data-model-1 — Data model: Duplicate title section. (L17–23)",
                      idx)
        self.assertIn(f"- {ARCH_REL}#auth-v2-beta — Auth: v2 (beta): OIDC via the gateway. "
                      f"(L21–23)", idx)
        self.assertNotIn("not-a-heading", idx)
        self.assertRegex(idx.splitlines()[1],
                         r"^# inputs-sha256: [0-9a-f]{64}  ·  bytes: [\d,]+  ·  specs: 1  ·  "
                         r"sections: 5$")
        self.assertEqual(idx.splitlines()[2], "# spec-paths: []")

    def test_setext_heading_and_deep_headings_not_listed(self):
        self.write(f"{PLAN}/system-design.md",
                   "Setext\n======\n\nBody.\n\n#### Deep\n\nToo deep.\n")
        self.assertEqual(self.sa("build").returncode, 0)
        idx = self.index()
        self.assertIn(f"{PLAN}/system-design.md#setext — Setext: Body.", idx)
        self.assertNotIn("#deep", idx)

    def test_kinds_and_precedence(self):
        self.write(f"{PLAN}/ux-spec.md", "# UX\n\nScreens.\n")
        self.write(f"{PLAN}/prd.md", "# PRD\n\nGoals.\n")
        self.write(f"{PLAN}/epics.md", "# Epics\n\nList.\n")
        self.write(f"{PLAN}/notes.md", "# Notes\n\nNot a spec.\n")
        self.assertEqual(self.sa("build").returncode, 0)
        idx = self.index()
        self.assertIn(f"## ux · {PLAN}/ux-spec.md", idx)
        self.assertIn(f"## prd · {PLAN}/prd.md", idx)
        self.assertIn(f"## epics · {PLAN}/epics.md", idx)
        self.assertNotIn("notes.md", idx)

    def test_sharded_directory_is_indexed_whole(self):
        self.write(f"{PLAN}/prd/index.md", "# PRD\n\nOverview.\n")
        self.write(f"{PLAN}/prd/goals.md", "# Goals\n\nShip it.\n")
        self.assertEqual(self.sa("build").returncode, 0)
        idx = self.index()
        self.assertIn(f"## prd · {PLAN}/prd/goals.md", idx)
        self.assertIn(f"{PLAN}/prd/goals.md#goals — Goals: Ship it.", idx)

    def test_same_title_in_two_files_is_unsuffixed_in_each(self):
        self.write(ARCH_REL, ARCH)
        self.write(f"{PLAN}/tech-design.md", "# Tech\n\n## Data model\n\nSecond file.\n")
        self.assertEqual(self.sa("build").returncode, 0)
        self.assertIn(f"{PLAN}/tech-design.md#data-model — ", self.index())

    def test_non_utf8_spec_is_skipped_not_fatal(self):
        self.write(ARCH_REL, ARCH)
        self.write(f"{PLAN}/architecture-legacy.md", b"# Old\n\xff\xfe\n")
        r = self.sa("build")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"- skipped: {PLAN}/architecture-legacy.md (not UTF-8)", self.index())

    def test_empty_project(self):
        r = self.sa("build")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("no spec docs found", self.index())

    def test_if_stale_leaves_a_fresh_index_untouched(self):
        self.write(ARCH_REL, ARCH)
        self.assertEqual(self.sa("build").returncode, 0)
        p = self.path(f"{IMPL}/spec/spec-index.md")
        before = os.stat(p).st_mtime_ns
        time.sleep(0.02)
        r = self.sa("build", "--if-stale")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("fresh", r.stdout)
        self.assertEqual(os.stat(p).st_mtime_ns, before)
        self.write(ARCH_REL, ARCH + "\n## Events\n\nKafka.\n")
        self.assertEqual(self.sa("build", "--if-stale").returncode, 0)
        self.assertIn("#events", self.index())

    def test_check_reports_stale_and_writes_nothing(self):
        self.write(ARCH_REL, ARCH)
        r = self.sa("build", "--check")
        self.assertEqual(r.returncode, 1)
        self.assertFalse(os.path.exists(self.path(f"{IMPL}/spec/spec-index.md")))
        self.sa("build")
        self.assertEqual(self.sa("build", "--check").returncode, 0)

    def test_spec_paths_override_is_recorded_and_reused(self):
        self.write(ARCH_REL, ARCH)
        self.write("docs/architecture.md", "# Arch\n\n## Events\n\nKafka.\n")
        r = self.sa("build", spec_paths=["docs/*.md"])
        self.assertEqual(r.returncode, 0, r.stderr)
        idx = self.index()
        self.assertIn("docs/architecture.md#events", idx)
        self.assertNotIn(ARCH_REL, idx)
        self.assertEqual(idx.splitlines()[2], '# spec-paths: ["docs/*.md"]')
        # A caller without --spec-paths (doctor) reuses the recorded list: still fresh.
        self.assertEqual(self.sa("build", "--check").returncode, 0)
        # An explicit empty list means discovery again: stale.
        self.assertEqual(self.sa("build", "--check", spec_paths=[]).returncode, 1)

    def test_bad_spec_paths_json_is_refused(self):
        r = subprocess.run([sys.executable, SCRIPT, "--project-root", self.root, "--impl-root",
                            self.impl, "--spec-paths", "{not json", "build"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("--spec-paths", r.stderr)

    def test_empty_and_whitespace_spec_paths_behave_like_an_empty_list_but_malformed_still_fails(self):
        # An orchestrator that renders "no override" as an empty string rather than the
        # documented `[]`/`[...]` JSON must not turn every build/check-pointers into a hard
        # failure -- empty or whitespace-only means "no override, discover normally", exactly
        # like an explicit `[]`. The leniency this adds must not spill over into genuinely
        # malformed input, which still has to exit 2.
        self.write(ARCH_REL, ARCH)

        def build_with(spec_paths):
            return subprocess.run(
                [sys.executable, SCRIPT, "--project-root", self.root, "--planning-root",
                 self.planning, "--impl-root", self.impl, "--spec-paths", spec_paths, "build"],
                capture_output=True, text=True)

        r_list = build_with("[]")
        self.assertEqual(r_list.returncode, 0, r_list.stderr)
        idx_from_list = self.index()
        self.assertIn(ARCH_REL, idx_from_list)
        self.assertEqual(idx_from_list.splitlines()[2], "# spec-paths: []")

        r_empty = build_with("")
        self.assertEqual(r_empty.returncode, 0, r_empty.stderr)
        self.assertEqual(self.index(), idx_from_list)

        r_whitespace = build_with("   \t  ")
        self.assertEqual(r_whitespace.returncode, 0, r_whitespace.stderr)
        self.assertEqual(self.index(), idx_from_list)

        r_bad = build_with("not-json")
        self.assertEqual(r_bad.returncode, 2)
        self.assertIn("--spec-paths", r_bad.stderr)

    def test_index_never_indexes_itself(self):
        self.write(f"_bmad-output/architecture.md", ARCH)
        parent = os.path.join(self.root, "_bmad-output")
        self.assertEqual(self.sa("build", planning=parent).returncode, 0)
        self.assertEqual(self.sa("build", planning=parent).returncode, 0)
        self.assertNotIn("spec-index.md", self.index())

    def test_size_warning(self):
        body = "".join(f"## Section {i}\n\nThis sentence pads the index entry to a realistic "
                       f"length for the size warning.\n\n" for i in range(400))
        self.write(ARCH_REL, "# Big\n\n" + body)
        r = self.sa("build")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("WARN spec index is", r.stderr)


DIMS = ["Interface contracts", "Error and edge case handling", "Observability requirements",
        "Security considerations", "Testability approach", "Existing-library check"]


def story(dims, head="# E001-S01-001: A story\n\nSome prose.\n"):
    parts = [head, "## Technical acceptance criteria\n"]
    for name in DIMS:
        if name in dims:
            parts.append(f"### {name}\n\n{dims[name]}\n")
    parts.append("## Files in scope\n\n- `src/a.py` — the module\n")
    return "\n".join(parts)


def full_story(**overrides):
    dims = {d: f"Content for {d}.\nSpec: {ARCH_REL}#data-model" for d in DIMS}
    for k, v in overrides.items():
        dims[k.replace("_", " ")] = v
    return story(dims)


STORY_REL = f"{IMPL}/epic-001/sprint-01/stories/E001-S01-001.md"


class TestPointers(Project):
    def setUp(self):
        super().setUp()
        self.write(ARCH_REL, ARCH)

    def check(self, text, rel=STORY_REL):
        self.write(rel, text)
        return self.sa("check-pointers", "--story", self.path(rel))

    def test_complete_story_passes(self):
        r = self.check(full_story())
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_missing_dimension_blocks(self):
        dims = {d: f"x\nSpec: {ARCH_REL}#data-model" for d in DIMS if d != DIMS[2]}
        r = self.check(story(dims))
        self.assertEqual(r.returncode, 2)
        self.assertIn("Observability requirements: missing dimension", r.stderr)

    def test_not_applicable_dimension_needs_no_pointer(self):
        r = self.check(full_story(Security_considerations="N/A — internal batch job, no input."))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_applicable_dimension_without_pointer_blocks(self):
        r = self.check(full_story(Testability_approach="Unit tests at the service boundary."))
        self.assertEqual(r.returncode, 2)
        self.assertIn("Testability approach: no Spec: line", r.stderr)

    def test_spec_none_with_reason_passes(self):
        r = self.check(full_story(
            Observability_requirements="Log each order.\nSpec: none — no observability section"))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_spec_none_without_reason_blocks(self):
        r = self.check(full_story(Observability_requirements="Log it.\nSpec: none"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("needs a reason", r.stderr)

    def test_spec_none_plus_pointer_blocks(self):
        r = self.check(full_story(Observability_requirements=(
            f"Log it.\nSpec: none — nothing\nSpec: {ARCH_REL}#data-model")))
        self.assertEqual(r.returncode, 2)
        self.assertIn("must be the only Spec: line", r.stderr)

    def test_several_pointers_on_one_dimension_pass(self):
        r = self.check(full_story(Interface_contracts=(
            f"POST /orders.\nSpec: {ARCH_REL}#order-api\n- Spec: {ARCH_REL}#data-model-1")))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_unknown_path_and_anchor_block(self):
        r = self.check(full_story(Interface_contracts=(
            "x\nSpec: docs/nowhere.md#a\nSpec: " + ARCH_REL + "#no-such-anchor")))
        self.assertEqual(r.returncode, 2)
        self.assertIn("docs/nowhere.md is not in the spec index", r.stderr)
        self.assertIn("has no anchor #no-such-anchor", r.stderr)

    def test_spec_line_inside_a_fence_does_not_count(self):
        r = self.check(full_story(Interface_contracts=(
            f"Example:\n\n```\nSpec: {ARCH_REL}#data-model\n```\n")))
        self.assertEqual(r.returncode, 2)
        self.assertIn("Interface contracts: no Spec: line", r.stderr)

    def test_pre_provenance_blocks_story_mode(self):
        r = self.check("# Old story\n\nInterface: POST /x.\n")
        self.assertEqual(r.returncode, 2)
        self.assertIn("pre-provenance", r.stderr)

    def test_all_mode_informs_on_pre_provenance_and_reports_broken(self):
        self.write(STORY_REL, "# Old story\n\nNo ACs.\n")
        r = self.sa("check-pointers", "--all")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("INFO pre-provenance", r.stdout)
        self.write(f"{IMPL}/epic-001/sprint-02/stories/E001-S02-001.md",
                   full_story(Interface_contracts=f"x\nSpec: {ARCH_REL}#gone"))
        r = self.sa("check-pointers", "--all")
        self.assertEqual(r.returncode, 1)
        self.assertIn("E001-S02-001.md", r.stderr)

    def test_sections_dedupes_and_prints_ranges(self):
        a = self.write(STORY_REL, full_story(Interface_contracts=f"x\nSpec: {ARCH_REL}#order-api"))
        b = self.write(f"{IMPL}/epic-001/sprint-01/stories/E001-S01-002.md", full_story())
        r = self.sa("sections", "--stories", a, b)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), [f"{ARCH_REL}#data-model L5–8",
                                                 f"{ARCH_REL}#order-api L9–16"])


REVIEW = """# Arch drift review

2 sentences of summary.

## Findings table

| # | Severity | Principle | Location | Finding | Remediation |
|---|----------|-----------|----------|---------|-------------|
| AD-1 | MAJOR | Core §1 | `src/a.py:1` | Orders bypass the repository | route via repo |
| AD-2 | MINOR | Core §7 | `src/b.py:2` | Naming | rename |
| AD-3 | BLOCKER | Core §2 | `src/c.py:3` | PRD says soft delete | use soft delete |
"""
EPIC_REVIEW_REL = f"{IMPL}/epic-003/epic-closure/arch-drift-review.md"
PRD_REL = f"{PLAN}/prd.md"
PRD = "# PRD\n\n## Deletion\n\nOrders are soft-deleted.\n"


class TestDispositions(Project):
    def setUp(self):
        super().setUp()
        self.write(ARCH_REL, ARCH)
        self.write(PRD_REL, PRD)
        self.review = self.write(EPIC_REVIEW_REL, REVIEW)

    def disp(self, fid, disposition, *extra):
        return self.sa("disposition", "--review", self.review, "--finding", fid,
                       "--disposition", disposition, *extra)

    def load(self):
        from ruamel.yaml import YAML
        with open(self.path(f"{IMPL}/epic-003/epic-closure/drift-dispositions.yaml"),
                  encoding="utf-8") as fh:
            return YAML(typ="safe").load(fh)

    def test_resolved_in_code_is_recorded(self):
        r = self.disp("AD-1", "resolved-in-code")
        self.assertEqual(r.returncode, 0, r.stderr)
        d = self.load()
        self.assertEqual(d["review"], EPIC_REVIEW_REL)
        self.assertEqual(d["findings"]["AD-1"]["severity"], "MAJOR")
        self.assertEqual(d["findings"]["AD-1"]["title"], "Orders bypass the repository")
        self.assertEqual(d["findings"]["AD-1"]["disposition"], "resolved-in-code")
        self.assertIsNone(d["findings"]["AD-1"]["commit"])

    def test_unknown_finding_is_refused(self):
        r = self.disp("AD-9", "resolved-in-code")
        self.assertEqual(r.returncode, 2)
        self.assertIn("AD-9 is not in the findings table", r.stderr)

    def test_spec_updated_on_architecture(self):
        r = self.disp("AD-1", "spec-updated", "--spec", f"{ARCH_REL}#order-api")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.load()["findings"]["AD-1"]["spec"], f"{ARCH_REL}#order-api")

    def test_spec_updated_on_a_prd_is_refused(self):
        r = self.disp("AD-3", "spec-updated", "--spec", f"{PRD_REL}#deletion")
        self.assertEqual(r.returncode, 2)
        self.assertIn("record spec-proposal instead", r.stderr)

    def test_spec_proposal_on_a_prd(self):
        r = self.disp("AD-3", "spec-proposal", "--spec", f"{PRD_REL}#deletion")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_spec_dispositions_need_a_resolving_pointer(self):
        r = self.disp("AD-1", "spec-updated")
        self.assertEqual(r.returncode, 2)
        r = self.disp("AD-1", "spec-updated", "--spec", f"{ARCH_REL}#nope")
        self.assertEqual(r.returncode, 2)
        self.assertIn("has no anchor #nope", r.stderr)

    def test_adr_justified_needs_an_existing_adr(self):
        r = self.disp("AD-1", "adr-justified", "--adr", "docs/adr/0009-x.md")
        self.assertEqual(r.returncode, 2)
        self.write("docs/adr/0009-x.md", "# ADR-0009: x\n")
        r = self.disp("AD-1", "adr-justified", "--adr", "docs/adr/0009-x.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.load()["findings"]["AD-1"]["adr"], "docs/adr/0009-x.md")

    def test_switch_off_refuses_spec_dispositions(self):
        r = self.disp("AD-1", "spec-updated", "--spec", f"{ARCH_REL}#order-api",
                      "--spec-alignment", "false")
        self.assertEqual(r.returncode, 2)
        self.assertIn("spec_alignment is off", r.stderr)
        r = self.disp("AD-1", "resolved-in-code", "--spec-alignment", "false")
        self.assertEqual(r.returncode, 0, r.stderr)

    def check(self, expect):
        return self.sa("check-dispositions", "--review", self.review, "--expect", expect)

    def test_check_passes_when_every_blocking_finding_has_one(self):
        self.disp("AD-1", "resolved-in-code")
        self.disp("AD-3", "spec-proposal", "--spec", f"{PRD_REL}#deletion")
        r = self.check("DONE — Blocker: 1, Major: 1, Minor: 1")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_check_blocks_a_blocking_finding_without_one(self):
        self.disp("AD-1", "resolved-in-code")
        r = self.check("Blocker: 1, Major: 1, Minor: 1")
        self.assertEqual(r.returncode, 2)
        self.assertIn("AD-3 (BLOCKER) has no disposition", r.stderr)

    def test_check_blocks_a_count_mismatch(self):
        self.disp("AD-1", "resolved-in-code")
        self.disp("AD-3", "resolved-in-code")
        r = self.check("Blocker: 0, Major: 1, Minor: 1")
        self.assertEqual(r.returncode, 2)
        self.assertIn("Blocker: 1, Major: 1, Minor: 1", r.stderr)

    def test_a_review_in_the_wrong_shape_cannot_pass_silently(self):
        self.write(EPIC_REVIEW_REL, "# Review\n\n- AD-1 MAJOR: something\n")
        r = self.check("Blocker: 0, Major: 1, Minor: 0")
        self.assertEqual(r.returncode, 2)
        self.assertIn("parsed Blocker: 0, Major: 0, Minor: 0", r.stderr)

    def test_sprint_ids_are_sprint_qualified(self):
        rel = f"{IMPL}/epic-003/sprint-02/closure/arch-drift-review.md"
        review = self.write(rel, REVIEW.replace("AD-1", "SD-02-1").replace("AD-2", "SD-02-2")
                            .replace("AD-3", "SD-02-3"))
        r = self.sa("disposition", "--review", review, "--finding", "SD-02-1",
                    "--disposition", "resolved-in-code")
        self.assertEqual(r.returncode, 0, r.stderr)


def adr(num, slug, epic="E003", status="Accepted", departs="n/a"):
    return (f"# ADR-{num:04d}: {slug}\n\n- **Status:** {status}\n- **Date:** 2026-09-11\n"
            f"- **Epic:** {epic}\n- **Departs from spec:** {departs}\n\n## Context\n\nx\n")


class TestAdrs(Project):
    def setUp(self):
        super().setUp()
        self.write(ARCH_REL, ARCH)
        self.write("docs/adr/0001-order-api.md",
                   adr(1, "order-api", departs=f"{ARCH_REL}#order-api"))
        self.write("docs/adr/0002-global.md", adr(2, "global", epic="n/a"))
        self.write("docs/adr/0003-draft.md",
                   adr(3, "draft", status="Proposed", departs=f"{ARCH_REL}#data-model"))
        self.write(f"{IMPL}/epic-003/arch/adr-0005-legacy.md", adr(5, "legacy"))
        self.write(f"{IMPL}/epic-003/arch/arch-gate-review.md", "# Gate\n")

    def test_lists_an_epics_adrs_from_both_homes(self):
        r = self.sa("adrs", "--epic", "E003")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), ["docs/adr/0001-order-api.md",
                                                 "docs/adr/0003-draft.md",
                                                 f"{IMPL}/epic-003/arch/adr-0005-legacy.md"])
        self.assertIn("old ADR home", r.stderr)
        self.assertIn("migrate-adrs", r.stderr)

    def test_an_adr_prefixed_filename_in_the_one_home_is_listed(self):
        """`docs/adr/` holds hand-written ADRs, and `ADR-NNNN-slug.md` is how they are
        usually named. Against the old `^\\d{4}` pattern every one of them was invisible to
        `adrs`, `check-links` and the migration planner alike -- reported as "no ADRs"
        rather than as a naming the reader could not parse."""
        self.write("docs/adr/ADR-0007-prefixed.md", adr(7, "prefixed"))
        r = self.sa("adrs", "--epic", "E003", "--format", "json")
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = json.loads(r.stdout)
        self.assertIn(7, [x["number"] for x in rows])
        self.assertEqual([x["home"] for x in rows if x["number"] == 7], ["docs"])

    def test_a_non_adr_filename_in_the_one_home_is_still_skipped(self):
        """The scope half: the `ADR-` prefix became optional, nothing else did."""
        self.write("docs/adr/README.md", "# How we write ADRs\n")
        self.write("docs/adr/notes-0099-scratch.md", adr(99, "scratch"))
        r = self.sa("adrs", "--epic", "E003", "--format", "json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([x["number"] for x in json.loads(r.stdout)], [1, 3, 5])

    def test_accepts_the_bare_epic_number(self):
        r = self.sa("adrs", "--epic", "3", "--format", "json")
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = json.loads(r.stdout)
        self.assertEqual([x["number"] for x in rows], [1, 3, 5])
        self.assertEqual(rows[0]["departs"], f"{ARCH_REL}#order-api")
        self.assertEqual(rows[2]["home"], "legacy")

    def test_check_links_reports_an_unlinked_departure(self):
        r = self.sa("check-links")
        self.assertEqual(r.returncode, 1)
        self.assertIn("0001-order-api.md", r.stdout)
        self.assertIn("section does not link the ADR", r.stdout)
        self.assertNotIn("0003-draft", r.stdout)            # Proposed: not a departure yet

    def test_check_links_passes_once_the_section_links_it(self):
        self.write(ARCH_REL, ARCH.replace(
            "POST /orders accepts a body.",
            "POST /orders accepts a body. See [ADR-0001](../../docs/adr/0001-order-api.md)."))
        r = self.sa("check-links", "--epic", "E003")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_check_links_reports_a_dangling_pointer(self):
        self.write("docs/adr/0004-gone.md", adr(4, "gone", departs=f"{ARCH_REL}#removed"))
        r = self.sa("check-links")
        self.assertEqual(r.returncode, 1)
        self.assertIn("0004-gone.md", r.stdout)
        self.assertIn("pointer does not resolve", r.stdout)

    def test_check_links_refuses_an_unparseable_epic(self):
        r = self.sa("check-links", "--epic", "not-an-epic")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not-an-epic", r.stderr)


class TestLease(Project):
    def lease(self, *args):
        return self.sa("lease", *args)

    def test_acquire_then_contend(self):
        self.assertEqual(self.lease("acquire", "--owner", "E001", "--wait-minutes", "0")
                         .returncode, 0)
        r = self.lease("acquire", "--owner", "E002", "--wait-minutes", "0")
        self.assertEqual(r.returncode, 5)
        self.assertIn("held by E001", r.stderr)
        self.assertEqual(self.lease("acquire", "--owner", "E001", "--wait-minutes", "0")
                         .returncode, 0)                      # the owner may refresh

    def test_expired_lease_is_taken_over_and_logged(self):
        self.lease("acquire", "--owner", "E001", "--ttl-minutes", "0", "--wait-minutes", "0")
        r = self.lease("acquire", "--owner", "E002", "--wait-minutes", "0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("E001", r.stderr)
        self.assertIn("taking it over", r.stderr)

    def test_release_rules(self):
        self.assertEqual(self.lease("release", "--owner", "E001").returncode, 0)   # free: no-op
        self.lease("acquire", "--owner", "E001", "--wait-minutes", "0")
        r = self.lease("release", "--owner", "E002")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.lease("release", "--owner", "E001").returncode, 0)
        self.assertEqual(self.lease("acquire", "--owner", "E002", "--wait-minutes", "0")
                         .returncode, 0)

    def test_lease_file_lives_in_the_state_root(self):
        self.lease("acquire", "--owner", "E001", "--wait-minutes", "0")
        with open(os.path.join(self.state, "spec-sync.lock"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["owner"], "E001")

    def test_real_processes_contending_get_exactly_one_winner(self):
        g = ["--project-root", self.root, "--impl-root", self.impl, "--state-root", self.state]
        procs = [subprocess.Popen([sys.executable, SCRIPT, *g, "lease", "acquire", "--owner",
                                   f"E{i:03d}", "--wait-minutes", "0"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for i in range(1, 7)]
        codes = [p.wait(timeout=120) for p in procs]
        for p in procs:
            p.stdout.close()
            p.stderr.close()
        self.assertEqual(sorted(codes), [0, 5, 5, 5, 5, 5])

    def test_a_waiter_gets_the_lease_when_the_holder_releases(self):
        self.lease("acquire", "--owner", "E001", "--wait-minutes", "0")
        g = ["--project-root", self.root, "--impl-root", self.impl, "--state-root", self.state]
        waiter = subprocess.Popen([sys.executable, SCRIPT, *g, "lease", "acquire", "--owner",
                                   "E002", "--wait-minutes", "0.5", "--poll-seconds", "0.1"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(0.6)
        self.assertEqual(self.lease("release", "--owner", "E001").returncode, 0)
        out, err = waiter.communicate(timeout=120)
        self.assertEqual(waiter.returncode, 0, err.decode())


class SyncBase(Project):
    """Epic E003 in a real git repo: an architecture spec, a PRD, an epic drift review with a
    spec-updated (AD-1 -> order-api) and a spec-proposal (AD-3 -> PRD deletion), and a story
    pointing at order-api. Tasks 10 and 11 build on this."""

    def setUp(self):
        super().setUp()
        self.write(ARCH_REL, ARCH)
        self.write(PRD_REL, PRD)
        self.review = self.write(EPIC_REVIEW_REL, REVIEW)
        self.story = self.write(f"{IMPL}/epic-003/sprint-01/stories/E003-S01-001.md",
                                full_story(Interface_contracts=f"POST.\nSpec: {ARCH_REL}#order-api"))
        self.write("README.md", "readme\n")
        self.init_git()
        self.dispose("AD-1", "spec-updated", "--spec", f"{ARCH_REL}#order-api")
        self.dispose("AD-3", "spec-proposal", "--spec", f"{PRD_REL}#deletion")

    def dispose(self, fid, disposition, *extra, review=None):
        r = self.sa("disposition", "--review", review or self.review, "--finding", fid,
                    "--disposition", disposition, *extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def plan(self, *extra):
        r = self.sa("sync-plan", "--epic", "E003", *extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def issues(self, kind, resolved=False):
        args = ["list-issues", "--state-root", self.state, "--format", "json"]
        args += ["--resolved"] if resolved else ["--kind", kind]
        r = self.pm(*args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def disp(self):
        from ruamel.yaml import YAML
        with open(self.path(f"{IMPL}/epic-003/epic-closure/drift-dispositions.yaml"),
                  encoding="utf-8") as fh:
            return YAML(typ="safe").load(fh)


class TestSyncPlan(SyncBase):
    def test_plan_lists_pending_spec_items_with_ranges(self):
        items = {i["id"]: i for i in self.plan()["items"]}
        self.assertEqual(set(items), {"AD-1", "AD-3"})
        self.assertEqual(items["AD-1"]["type"], "spec-updated")
        self.assertEqual(items["AD-1"]["range"], "L9–16")
        self.assertEqual(items["AD-1"]["title"], "Orders bypass the repository")
        self.assertEqual(items["AD-3"]["range"], "L3–5")
        self.assertEqual(items["AD-3"]["review"], EPIC_REVIEW_REL)

    def test_an_epic_without_dispositions_plans_nothing(self):
        r = self.sa("sync-plan", "--epic", "E009")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), {"epic": "E009", "items": []})

    def test_sprint_findings_are_included(self):
        rel = f"{IMPL}/epic-003/sprint-01/closure/arch-drift-review.md"
        review = self.write(rel, REVIEW.replace("AD-", "SD-01-"))
        self.dispose("SD-01-1", "spec-updated", "--spec", f"{ARCH_REL}#data-model", review=review)
        self.assertIn("SD-01-1", {i["id"] for i in self.plan()["items"]})

    def test_an_unlinked_accepted_adr_becomes_an_adr_link_item(self):
        self.write("docs/adr/0001-order-api.md",
                   adr(1, "order-api", departs=f"{ARCH_REL}#order-api"))
        items = {i["id"]: i for i in self.plan()["items"]}
        self.assertEqual(items["ADR-0001"]["type"], "adr-link")
        self.assertEqual(items["ADR-0001"]["adr"], "docs/adr/0001-order-api.md")

    def test_defer_writes_pointer_only_proposals_and_backlog_items(self):
        out = self.plan("--defer")
        self.assertEqual({d["id"] for d in out["deferred"]}, {"AD-1", "AD-3"})
        prop = self.read(f"{IMPL}/epic-003/epic-closure/spec-proposals/AD-1.md")
        self.assertIn(f"`{ARCH_REL}#order-api`", prop)
        self.assertIn("(deferred)", prop)
        items = self.issues("spec-proposal")
        self.assertEqual(len(items), 2)
        self.assertEqual({i["ref"] for i in items},
                         {f"{IMPL}/epic-003/epic-closure/spec-proposals/AD-1.md",
                          f"{IMPL}/epic-003/epic-closure/spec-proposals/AD-3.md"})
        self.assertEqual({i["severity"] for i in items}, {"Medium", "High"})
        d = self.disp()["findings"]["AD-1"]
        self.assertEqual((d["disposition"], d["deferred"]), ("spec-proposal", True))
        self.assertTrue(d["issue"].startswith("BL-E003-"))
        self.assertEqual(self.plan()["items"], [])            # nothing left pending

    def test_propose_records_an_agent_written_proposal(self):
        rel = f"{IMPL}/epic-003/epic-closure/spec-proposals/AD-3.md"
        r = self.sa("propose", "--epic", "E003", "--finding", "AD-3")
        self.assertEqual(r.returncode, 2)                     # no file yet
        self.assertIn("write the proposal", r.stderr)
        self.write(rel, "# Proposal\n\nMake deletion hard.\n")
        r = self.sa("propose", "--epic", "E003", "--finding", "AD-3")
        self.assertEqual(r.returncode, 0, r.stderr)
        [it] = self.issues("spec-proposal")
        self.assertEqual(it["ref"], rel)
        self.assertEqual(it["title"], "Spec proposal: PRD says soft delete")
        self.assertEqual(self.disp()["findings"]["AD-3"]["proposal"], rel)

    def test_propose_refuses_a_finding_that_is_not_pending(self):
        r = self.sa("propose", "--epic", "E003", "--finding", "AD-2")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not a pending spec item", r.stderr)

    def test_a_resolved_twin_is_reopened_with_a_new_key_not_reused(self):
        # A rerun after the original backlog item was already resolved must not silently
        # reuse the resolved key: it re-opens the finding under a genuinely new one.
        out = self.plan("--defer")
        key = next(d["issue"] for d in out["deferred"] if d["id"] == "AD-1")
        r = self.pm("resolve-issue", "--state-root", self.state, "--key", key,
                   "--resolution", "wontfix", "--note", "not applicable here", "--cause", "cli")
        self.assertEqual(r.returncode, 0, r.stderr)
        from ruamel.yaml import YAML
        dpath = self.path(f"{IMPL}/epic-003/epic-closure/drift-dispositions.yaml")
        y = YAML()
        with open(dpath, encoding="utf-8") as fh:
            data = y.load(fh)
        data["findings"]["AD-1"]["issue"] = None       # plant: the CLI cannot reach this state
        with open(dpath, "w", encoding="utf-8") as fh:
            y.dump(data, fh)
        out2 = self.plan("--defer")
        key2 = next(d["issue"] for d in out2["deferred"] if d["id"] == "AD-1")
        self.assertNotEqual(key2, key)
        self.assertTrue(key2.startswith("BL-E003-"))
        self.assertIn(key2, {i["key"] for i in self.issues("spec-proposal")})

    def test_a_bad_epic_key_is_refused_by_both_commands(self):
        r = self.sa("sync-plan", "--epic", "not-an-epic")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not-an-epic", r.stderr)
        r = self.sa("propose", "--epic", "not-an-epic", "--finding", "AD-1")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not-an-epic", r.stderr)


class TestCommit(SyncBase):
    def setUp(self):
        super().setUp()
        r = self.sa("lease", "acquire", "--owner", "E003", "--wait-minutes", "0")
        self.assertEqual(r.returncode, 0, r.stderr)

    def edit(self, old, new, rel=ARCH_REL):
        text = self.read(rel)
        self.assertIn(old, text)
        self.write(rel, text.replace(old, new, 1))

    def commit(self, *extra, finding="AD-1"):
        args = ["commit", "--epic", "E003"]
        args += ["--finding", finding] if finding else []
        return self.sa(*args, "--paths", ARCH_REL, *extra)

    def head(self):
        return self.git("rev-parse", "HEAD").strip()

    def test_an_in_scope_edit_is_committed_recorded_and_tracked(self):
        self.edit("POST /orders accepts a body.", "POST /orders accepts a body; returns 201.")
        r = self.commit()
        self.assertEqual(r.returncode, 0, r.stderr)
        msg = self.git("log", "-1", "--format=%B")
        self.assertTrue(msg.startswith("docs(spec): E003 AD-1 — Orders bypass the repository"),
                        msg)
        self.assertIn("Signed-off-by: t <t@example.com>", msg)
        self.assertEqual(self.git("show", "--name-only", "--format=", "HEAD").split(),
                         [ARCH_REL])
        d = self.disp()["findings"]["AD-1"]
        self.assertEqual(d["commit"], self.head())
        [it] = self.issues("spec-change")
        self.assertEqual((it["key"], it["ref"]), (d["issue"], self.head()))
        self.assertEqual(it["severity"], "Medium")
        self.assertNotIn("AD-1", {i["id"] for i in self.plan()["items"]})

    def test_scope_guard_refuses_an_edit_outside_the_section(self):
        before = self.head()
        self.edit("POST /orders accepts a body.", "POST /orders returns 201.")
        self.edit("one row per order.", "one row per order line.")
        r = self.commit()
        self.assertEqual(r.returncode, 2)
        self.assertIn("outside", r.stderr)
        self.assertIn("order-api", r.stderr)
        self.assertEqual(self.head(), before)

    def test_anchor_guard_refuses_a_pointed_rename_unless_told(self):
        self.edit("## Order API", "## Orders API")
        r = self.commit()
        self.assertEqual(r.returncode, 2)
        self.assertIn("E003-S01-001.md", r.stderr)
        self.assertIn("--rename-anchor", r.stderr)
        r = self.commit("--rename-anchor", "order-api=orders-api")
        self.assertEqual(r.returncode, 0, r.stderr)
        story_rel = f"{IMPL}/epic-003/sprint-01/stories/E003-S01-001.md"
        self.assertIn(f"Spec: {ARCH_REL}#orders-api", self.read(story_rel))
        self.assertEqual(sorted(self.git("show", "--name-only", "--format=", "HEAD").split()),
                         sorted([ARCH_REL, story_rel]))
        self.assertEqual(self.disp()["findings"]["AD-1"]["spec"], f"{ARCH_REL}#orders-api")

    def test_rename_anchor_target_must_exist(self):
        self.edit("## Order API", "## Orders API")
        r = self.commit("--rename-anchor", "order-api=no-such")
        self.assertEqual(r.returncode, 2)
        self.assertIn("no-such", r.stderr)

    def test_only_the_named_paths_are_committed(self):
        self.write("README.md", "changed, not committed\n")
        self.write("other.txt", "staged by someone else\n")
        self.git("add", "other.txt")
        self.edit("POST /orders accepts a body.", "POST /orders returns 201.")
        self.assertEqual(self.commit().returncode, 0)
        self.assertIn("README.md", self.git("diff", "--name-only").split())
        self.assertIn("other.txt", self.git("diff", "--cached", "--name-only").split())

    def test_the_lease_is_required(self):
        self.sa("lease", "release", "--owner", "E003")
        self.edit("POST /orders accepts a body.", "POST /orders returns 201.")
        r = self.commit()
        self.assertEqual(r.returncode, 2)
        self.assertIn("lease", r.stderr)

    def test_paths_must_be_the_pointed_file(self):
        self.edit("POST /orders accepts a body.", "POST /orders returns 201.")
        r = self.sa("commit", "--epic", "E003", "--finding", "AD-1", "--paths", "README.md")
        self.assertEqual(r.returncode, 2)

    def test_a_proposal_item_is_never_committed(self):
        r = self.sa("commit", "--epic", "E003", "--finding", "AD-3", "--paths", PRD_REL)
        self.assertEqual(r.returncode, 2)
        self.assertIn("propose", r.stderr)

    def test_a_committed_findings_disposition_cannot_change(self):
        self.edit("POST /orders accepts a body.", "POST /orders returns 201.")
        self.assertEqual(self.commit().returncode, 0)
        r = self.sa("disposition", "--review", self.review, "--finding", "AD-1",
                    "--disposition", "resolved-in-code")
        self.assertEqual(r.returncode, 2)
        self.assertIn("already applied", r.stderr)

    def test_a_briefly_locked_index_is_retried(self):
        self.edit("POST /orders accepts a body.", "POST /orders returns 201.")
        lock = self.path(".git/index.lock")
        with open(lock, "w"):
            pass
        # 1.2 s outlasts interpreter start-up + the diff, so the first attempts really do
        # hit the lock (backoff 0.2, 0.4, 0.8 s) and a later one succeeds.
        threading.Timer(1.2, os.remove, [lock]).start()
        r = self.commit()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_stuck_index_lock_gives_up(self):
        self.edit("POST /orders accepts a body.", "POST /orders returns 201.")
        lock = self.path(".git/index.lock")
        with open(lock, "w"):
            pass
        self.addCleanup(lambda: os.path.exists(lock) and os.remove(lock))
        r = self.commit()
        self.assertEqual(r.returncode, 2)
        self.assertIn("stayed locked", r.stderr)

    def test_pointer_rewrite_is_rolled_back_on_a_failed_commit(self):
        # A rename in play plus a stuck index.lock: git_commit must ultimately fail, and the
        # pointer rewrite it made before failing must be undone, not left stranded -- else a
        # retry would search for the old anchor, no longer find it, and silently skip the
        # story that still needs to move with this commit.
        self.edit("## Order API", "## Orders API")
        lock = self.path(".git/index.lock")
        with open(lock, "w"):
            pass
        self.addCleanup(lambda: os.path.exists(lock) and os.remove(lock))
        r = self.commit("--rename-anchor", "order-api=orders-api")
        self.assertEqual(r.returncode, 2)
        self.assertIn("stayed locked", r.stderr)
        story_rel = f"{IMPL}/epic-003/sprint-01/stories/E003-S01-001.md"
        story = self.read(story_rel)
        self.assertIn(f"Spec: {ARCH_REL}#order-api", story)
        self.assertNotIn(f"Spec: {ARCH_REL}#orders-api", story)

    def test_chained_pointer_renames_are_rolled_back_in_reverse(self):
        # Two --rename-anchor pairs chaining through the same story in one call: the story
        # is rewritten twice in a row (order-api -> orders-api -> orders-api-v2). Undoing in
        # forward order tries the *older* substitution first, against a file that has already
        # moved past it -- a silent no-op -- and leaves the story at the intermediate anchor
        # instead of its true HEAD anchor. Undoing in reverse must land it back at #order-api.
        self.edit("## Order API\n\nPOST /orders accepts a body.\n",
                  "## Orders API V2\n\nPOST /orders accepts a body.\n\n### Orders API\n\n"
                  "See above.\n")
        lock = self.path(".git/index.lock")
        with open(lock, "w"):
            pass
        self.addCleanup(lambda: os.path.exists(lock) and os.remove(lock))
        r = self.commit("--rename-anchor", "order-api=orders-api",
                        "--rename-anchor", "orders-api=orders-api-v2")
        self.assertEqual(r.returncode, 2)
        self.assertIn("stayed locked", r.stderr)
        story_rel = f"{IMPL}/epic-003/sprint-01/stories/E003-S01-001.md"
        story = self.read(story_rel)
        self.assertIn(f"Spec: {ARCH_REL}#order-api", story)
        self.assertNotIn(f"Spec: {ARCH_REL}#orders-api", story)

    def _adr(self):
        self.write("docs/adr/0001-order-api.md",
                   adr(1, "order-api", departs=f"{ARCH_REL}#order-api"))
        self.git("add", "docs/adr/0001-order-api.md")
        self.git("commit", "-q", "-m", "adr")

    def test_an_adr_link_commit(self):
        self._adr()
        self.edit("POST /orders accepts a body.",
                  "POST /orders accepts a body. See [ADR-0001](../../docs/adr/0001-order-api.md).")
        r = self.sa("commit", "--epic", "E003", "--adr", "docs/adr/0001-order-api.md",
                    "--paths", ARCH_REL)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.git("log", "-1", "--format=%s").startswith(
            "docs(spec): E003 link ADR-0001 from "))
        self.assertEqual(self.disp()["adr_links"]["ADR-0001"]["commit"], self.head())
        self.assertNotIn("ADR-0001", {i["id"] for i in self.plan()["items"]})

    def test_an_adr_link_commit_without_the_link_is_refused(self):
        self._adr()
        self.edit("POST /orders accepts a body.", "POST /orders returns 201.")
        r = self.sa("commit", "--epic", "E003", "--adr", "docs/adr/0001-order-api.md",
                    "--paths", ARCH_REL)
        self.assertEqual(r.returncode, 2)
        self.assertIn("does not link", r.stderr)

    def test_an_adr_link_commit_refuses_a_bare_filename_mention(self):
        # A passing mention of the ADR's filename is not a link: the guard's whole job is to
        # confirm the section actually links back to it.
        self._adr()
        self.edit("POST /orders accepts a body.",
                  "POST /orders accepts a body. TODO: link 0001-order-api.md.")
        r = self.sa("commit", "--epic", "E003", "--adr", "docs/adr/0001-order-api.md",
                    "--paths", ARCH_REL)
        self.assertEqual(r.returncode, 2)
        self.assertIn("does not link", r.stderr)

    def test_an_adr_link_commit_into_a_prd_is_refused(self):
        # ADR-0004: agents edit architecture specs only. An ADR whose `Departs from spec:`
        # names a PRD anchor must not be linkable via commit --adr, even though the pointer
        # resolves fine -- the section it resolves to is the wrong kind.
        self.write("docs/adr/0001-order-api.md",
                   adr(1, "order-api", departs=f"{PRD_REL}#deletion"))
        self.git("add", "docs/adr/0001-order-api.md")
        self.git("commit", "-q", "-m", "adr")
        r = self.sa("commit", "--epic", "E003", "--adr", "docs/adr/0001-order-api.md",
                    "--paths", PRD_REL)
        self.assertEqual(r.returncode, 2)
        self.assertIn("architecture specs only", r.stderr)
        self.assertIn("0004-agents-edit-architecture-specs.md", r.stderr)

    def test_a_failed_append_issue_after_commit_prints_a_runnable_recovery_command(self):
        # The docs(spec) commit lands, but the backlog write that follows it fails: the
        # disposition already records the SHA (record_item writes `commit` before
        # append_spec_issue runs), so a rerun cannot re-drive this the way a fresh `commit`
        # normally would -- the printed recovery command is the only way back. Mirrors
        # test_a_failed_refile_after_resolve_prints_a_runnable_recovery_command's mechanism
        # (a wrapper that forwards every subcommand to the real pm-status.py except
        # append-issue), but goes one step further: that sibling test only parses the
        # printed argv, this one actually executes it and confirms it files the item.
        #
        # The wrapper disables append-issue only on its first attempt (a marker file records
        # that the attempt happened) so the identical recovery command, rerun unmodified
        # against the same wrapper, reaches the real pm-status.py the second time -- the
        # way rerunning the exact printed command against a since-fixed environment would.
        marker = self.path("append-issue-attempted")
        wrapper = self.write("fake-pm-status.py", f"""#!/usr/bin/env python3
import os, subprocess, sys
if "append-issue" in sys.argv[1:] and not os.path.exists({marker!r}):
    open({marker!r}, "w").close()
    sys.stderr.write("append-issue disabled by test wrapper (first attempt only)\\n")
    sys.exit(2)
sys.exit(subprocess.run([sys.executable, {PM!r}, *sys.argv[1:]]).returncode)
""")
        os.chmod(wrapper, 0o755)
        self.edit("POST /orders accepts a body.", "POST /orders accepts a body; returns 201.")
        r = self.sa("commit", "--epic", "E003", "--finding", "AD-1", "--paths", ARCH_REL,
                    pm_status=wrapper)
        self.assertEqual(r.returncode, 2)
        sha = self.head()
        self.assertIn(f"commit {sha} already landed and is recorded on AD-1's disposition",
                      r.stderr)
        self.assertIn("finish recording the backlog issue by hand:", r.stderr)
        self.assertIn(wrapper, r.stderr)
        # the commit is already recorded on the disposition; the item is not -- a rerun of
        # `commit` cannot re-drive this the normal way (mirrors
        # test_a_committed_findings_disposition_cannot_change's proof that a disposition
        # is frozen once applied).
        d = self.disp()["findings"]["AD-1"]
        self.assertEqual(d["commit"], sha)
        self.assertIsNone(d.get("issue"))
        r2 = self.sa("disposition", "--review", self.review, "--finding", "AD-1",
                    "--disposition", "resolved-in-code")
        self.assertEqual(r2.returncode, 2)
        self.assertIn("already applied", r2.stderr)
        cmd = r.stderr.strip().rsplit("hand: ", 1)[1]
        argv = shlex.split(cmd)
        self.assertEqual(argv[0], wrapper)
        self.assertEqual(argv[1], "append-issue")
        self.assertEqual(argv[argv.index("--sprint") + 1], "")
        self.assertEqual(argv[argv.index("--ref") + 1], sha)
        self.assertEqual(argv[argv.index("--title") + 1],
                         "Spec change: Orders bypass the repository")
        self.assertEqual(argv[argv.index("--source") + 1], "spec-sync (AD-1)")
        # Execute the printed recovery command for real, unmodified. The marker means the
        # wrapper's outage was a one-time thing, so this run reaches the real pm-status.py
        # and must genuinely file the backlog item -- not merely look plausible.
        rr = subprocess.run(argv, capture_output=True, text=True,
                            env={**os.environ, **GIT_ENV})
        self.assertEqual(rr.returncode, 0, rr.stderr)
        [it] = self.issues("spec-change")
        self.assertEqual(it["ref"], sha)
        self.assertEqual(it["title"], "Spec change: Orders bypass the repository")
        self.assertEqual(it["source"], "spec-sync (AD-1)")
        self.assertEqual(it["severity"], "Medium")


class TestRejectAndStale(SyncBase):
    def setUp(self):
        super().setUp()
        self.sa("lease", "acquire", "--owner", "E003", "--wait-minutes", "0")
        text = self.read(ARCH_REL).replace("POST /orders accepts a body.",
                                           "POST /orders accepts a body; returns 201.")
        self.write(ARCH_REL, text)
        r = self.sa("commit", "--epic", "E003", "--finding", "AD-1", "--paths", ARCH_REL)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.sa("lease", "release", "--owner", "E003")
        self.spec_sha = self.git("rev-parse", "HEAD").strip()
        self.key = self.disp()["findings"]["AD-1"]["issue"]

    def commit_all(self, msg):
        self.git("add", ARCH_REL)
        self.git("commit", "-q", "-m", msg)

    def test_reject_reverts_resolves_and_refiles_the_drift(self):
        r = self.sa("reject", "--key", self.key)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.git("log", "-1", "--format=%s").startswith(
            'Revert "docs(spec): E003 AD-1'))
        self.assertEqual(self.read(ARCH_REL), ARCH)
        [res] = [i for i in self.issues("", resolved=True) if i["key"] == self.key]
        self.assertEqual(res["resolution"], "wontfix")
        self.assertEqual(res["ref"], self.git("rev-parse", "HEAD").strip())
        [fix] = self.issues("defect")
        self.assertEqual(fix["title"], "Code diverges from spec: Orders bypass the repository")
        self.assertEqual(fix["source"], f"spec-reject ({self.key})")
        self.assertEqual(fix["severity"], "Medium")

    def test_a_conflicting_revert_aborts_and_leaves_the_item_open(self):
        self.write(ARCH_REL, self.read(ARCH_REL).replace("returns 201.", "returns 202."))
        self.commit_all("later edit on the same line")
        before = self.git("rev-parse", "HEAD").strip()
        r = self.sa("reject", "--key", self.key)
        self.assertEqual(r.returncode, 2)
        self.assertIn("failed", r.stderr)
        self.assertIn("unmerged: " + ARCH_REL, r.stderr)
        self.assertIn("stays open", r.stderr)
        self.assertFalse(os.path.exists(self.path(".git/REVERT_HEAD")))
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), before)
        self.assertEqual([i["key"] for i in self.issues("spec-change")], [self.key])

    def test_rejecting_a_proposal_declines_it_without_git(self):
        deferred = {d["id"]: d for d in self.plan("--defer")["deferred"]}
        key = deferred["AD-3"]["issue"]
        before = self.git("rev-parse", "HEAD").strip()
        r = self.sa("reject", "--key", key)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), before)
        [res] = [i for i in self.issues("", resolved=True) if i["key"] == key]
        self.assertEqual(res["ref"], deferred["AD-3"]["proposal"])
        self.assertIn("High", {i["severity"] for i in self.issues("defect")})

    def test_reject_refuses_a_defect(self):
        self.pm("append-issue", "--state-root", self.state, "--epic", "003", "--sprint", "",
                "--title", "A bug", "--source", "qa (Q-1)", "--severity", "Low",
                "--description", "d")
        key = self.issues("defect")[0]["key"]
        r = self.sa("reject", "--key", key)
        self.assertEqual(r.returncode, 2)
        self.assertIn("spec-change and spec-proposal items only", r.stderr)

    def test_a_failed_refile_after_resolve_prints_a_runnable_recovery_command(self):
        # resolve-issue succeeds but append-issue fails: the item is now wontfix with nothing
        # refiled, and the printed recovery command is the only way back -- it must actually
        # run, not just read plausibly. A wrapper forwards every subcommand to the real
        # pm-status.py except append-issue, which it fails outright.
        wrapper = self.write("fake-pm-status.py", f"""#!/usr/bin/env python3
import subprocess, sys
if "append-issue" in sys.argv[1:]:
    sys.stderr.write("append-issue disabled by test wrapper\\n")
    sys.exit(2)
sys.exit(subprocess.run([sys.executable, {PM!r}, *sys.argv[1:]]).returncode)
""")
        r = self.sa("reject", "--key", self.key, pm_status=wrapper)
        self.assertEqual(r.returncode, 2)
        self.assertIn("is resolved but the code fix was not filed -- rerun:", r.stderr)
        self.assertIn(wrapper, r.stderr)
        cmd = r.stderr.strip().rsplit("rerun: ", 1)[1]
        argv = shlex.split(cmd)
        self.assertEqual(argv[0], wrapper)
        self.assertEqual(argv[argv.index("--sprint") + 1], "")
        self.assertEqual(argv[argv.index("--title") + 1],
                         "Code diverges from spec: Orders bypass the repository")
        # the item is still wontfix -- reject is not retried, only the code fix is refiled
        [res] = [i for i in self.issues("", resolved=True) if i["key"] == self.key]
        self.assertEqual(res["resolution"], "wontfix")

    def test_check_stale_reports_an_unconfirmed_change_that_was_built_upon(self):
        r = self.sa("check-stale")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.write(ARCH_REL, self.read(ARCH_REL) + "\n## Events\n\nKafka.\n")
        self.commit_all("built on top")
        r = self.sa("check-stale")
        self.assertEqual(r.returncode, 1)
        self.assertIn(self.key, r.stdout)
        self.assertIn("1 later commit", r.stdout)


class TestMigrateAdrs(Project):
    def setUp(self):
        super().setUp()
        self.write("docs/adr/0003-stack.md", adr(3, "stack", epic="n/a"))
        self.write(f"{IMPL}/epic-001/arch/adr-0003-auth.md",
                   "# ADR-0003: auth\n\n- **Status:** Accepted\n\n## Context\n\nx\n")
        self.write(f"{IMPL}/epic-001/arch/adr-0004-cache.md",
                   "# ADR-0004: cache\n\n- **Status:** Accepted\n\n## Context\n\ny\n")
        self.s1 = f"{IMPL}/epic-001/sprint-01/stories/E001-S01-001.md"
        self.s2 = f"{IMPL}/epic-002/sprint-01/stories/E002-S01-001.md"
        self.write(self.s1, f"# S\n\nPer ADR-0003 and {IMPL}/epic-001/arch/adr-0004-cache.md.\n")
        self.write(self.s2, "# S\n\nPer ADR-0003 (the stack).\n")
        self.init_git()

    def run_json(self, *args):
        r = self.sa("migrate-adrs", *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_plan_is_read_only(self):
        out = self.run_json("--plan")
        moves = {m["from"]: m for m in out["moves"]}
        self.assertTrue(moves[f"{IMPL}/epic-001/arch/adr-0003-auth.md"]["collision"])
        self.assertEqual(moves[f"{IMPL}/epic-001/arch/adr-0004-cache.md"]["to"],
                         "docs/adr/0004-cache.md")
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_apply_moves_renumbers_rewrites_and_commits(self):
        out = self.run_json("--apply")
        self.assertEqual(self.git("log", "-1", "--format=%s").strip(),
                         "docs(adr): migrate epic ADRs to docs/adr")
        self.assertEqual(out["commit"], self.git("rev-parse", "HEAD").strip())
        # no collision: moved, Epic line added, exact path reference rewritten
        cache = self.read("docs/adr/0004-cache.md")
        self.assertIn("- **Epic:** E001", cache)
        self.assertIn("docs/adr/0004-cache.md", self.read(self.s1))
        # collision: docs/adr keeps 0003; the epic ADR gets a fresh number (disk max 4 -> 5)
        auth = self.read("docs/adr/0005-auth.md")
        self.assertTrue(auth.startswith("# ADR-0005: auth"))
        self.assertIn("ADR-0005", self.read(self.s1))           # inside epic-001: rewritten
        self.assertIn("ADR-0003", self.read(self.s2))           # elsewhere: left alone...
        self.assertIn(self.s2, {r["file"] for r in out["review"]})   # ...and listed
        self.assertFalse(os.path.exists(self.path(f"{IMPL}/epic-001/arch/adr-0003-auth.md")))
        tracked = self.git("ls-files", "docs/adr").split()
        self.assertEqual(sorted(tracked), ["docs/adr/0003-stack.md", "docs/adr/0004-cache.md",
                                           "docs/adr/0005-auth.md"])
        self.assertEqual(self.git("status", "--porcelain", "--",
                                  "docs", f"{IMPL}/epic-001", f"{IMPL}/epic-002").strip(), "")

    def test_same_number_AND_slug_is_a_duplicate_not_a_collision(self):
        """An epic ADR already migrated is a LEFTOVER, not a competing decision.

        Renumbering it mints a stale duplicate under a fresh number. Observed on a real
        project (houserules, 2026-09-25): all 14 legacy ADRs were same-number-same-slug
        duplicates, and --apply would have invented ADRs 36-49 for them, then rewritten the
        epic artifacts to cite the invented numbers. DOC_ADR_RE matched the slug with `.+`
        but never captured it, so the collision test compared numbers only.
        """
        self.write("docs/adr/0009-cache-policy.md", adr(9, "cache-policy", epic="E003"))
        self.write(f"{IMPL}/epic-003/arch/adr-0009-cache-policy.md",
                   "# ADR-0009: cache-policy\n\n- **Status:** Accepted\n\n## Context\n\nstale\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "duplicate fixture")
        mv = {m["from"]: m for m in self.run_json("--plan")["moves"]}[
            f"{IMPL}/epic-003/arch/adr-0009-cache-policy.md"]
        self.assertTrue(mv["duplicate"], "same number AND slug must classify as duplicate")
        self.assertFalse(mv["collision"], "a duplicate must never be renumbered")
        self.assertIsNone(mv["to"])

    def test_same_number_DIFFERENT_slug_is_still_a_collision(self):
        """The genuine competing-decision case must keep renumbering."""
        mv = {m["from"]: m for m in self.run_json("--plan")["moves"]}[
            f"{IMPL}/epic-001/arch/adr-0003-auth.md"]
        self.assertTrue(mv["collision"])
        self.assertFalse(mv["duplicate"])

    def test_apply_leaves_a_duplicate_in_place_and_reports_it(self):
        """--apply must not move, renumber, or delete a duplicate: it reports it."""
        self.write("docs/adr/0009-cache-policy.md", adr(9, "cache-policy", epic="E003"))
        dup_rel = f"{IMPL}/epic-003/arch/adr-0009-cache-policy.md"
        self.write(dup_rel,
                   "# ADR-0009: cache-policy\n\n- **Status:** Accepted\n\n## Context\n\nstale\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "duplicate fixture")
        out = self.run_json("--apply")
        self.assertTrue(os.path.exists(self.path(dup_rel)),
                        "the duplicate must stay where it is")
        self.assertIn(dup_rel, {d["from"] for d in out["duplicates"]})
        self.assertFalse(os.path.exists(self.path("docs/adr/0010-cache-policy.md")),
                         "no fresh number may be minted for a duplicate")
        self.assertEqual(self.read("docs/adr/0009-cache-policy.md"),
                         adr(9, "cache-policy", epic="E003"),
                         "the canonical docs/adr copy must be untouched")

    def test_nothing_to_move(self):
        self.git("rm", "-q", "-r", f"{IMPL}/epic-001/arch")
        self.git("commit", "-q", "-m", "no legacy")
        out = self.run_json("--apply")
        self.assertEqual((out["moves"], out["commit"]), ([], None))

    def test_register_lag_is_reported(self):
        with open(os.path.join(self.state, "adr-register.yaml"), "w", encoding="utf-8") as fh:
            fh.write("next: 2\nreserved: []\n")
        reg = self.run_json("--plan")["register"]
        self.assertEqual(reg, {"next": 2, "highest_on_disk": 4, "lagging": True})

    def test_collision_between_two_legacy_adrs_in_different_epics_gets_distinct_numbers(self):
        # ADR-0005's most careful scenario: two legacy ADRs in different epics share a number.
        # The first one seen keeps it; the second collides and must be reserved a fresh one,
        # and that renumber must stay scoped to its own epic tree (never the other epic's).
        self.write(f"{IMPL}/epic-005/arch/adr-0007-first.md", adr(7, "first", epic="E005"))
        self.write(f"{IMPL}/epic-006/arch/adr-0007-second.md", adr(7, "second", epic="E006"))
        s5 = f"{IMPL}/epic-005/sprint-01/stories/E005-S01-001.md"
        s6 = f"{IMPL}/epic-006/sprint-01/stories/E006-S01-001.md"
        self.write(s5, "# S\n\nPer ADR-0007.\n")
        self.write(s6, "# S\n\nPer ADR-0007.\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "two legacy ADRs sharing a number")
        out = self.run_json("--apply")
        moved = {m["epic"]: m for m in out["moves"] if m["slug"] in ("first", "second")}
        self.assertFalse(moved["E005"]["collision"])              # first seen: keeps 0007
        self.assertTrue(moved["E006"]["collision"])                # second seen: reserved fresh
        self.assertEqual(moved["E005"]["to"], "docs/adr/0007-first.md")
        n6 = moved["E006"]["renumbered_to"]
        self.assertNotEqual(n6, 7)
        self.assertIn(f"ADR-{n6:04d}", self.read(s6))               # its own story: rewritten
        self.assertNotIn(f"ADR-{n6:04d}", self.read(s5))            # the other epic: untouched
        self.assertIn("ADR-0007", self.read(s5))                    # E005's own number: unchanged
        tracked = set(self.git("ls-files", "docs/adr").split())
        self.assertIn("docs/adr/0007-first.md", tracked)
        self.assertIn(moved["E006"]["to"], tracked)

    def test_add_epic_line_inserts_after_title_when_no_status_line(self):
        self.write(f"{IMPL}/epic-007/arch/adr-0009-nostat.md",
                   "# ADR-0009: nostat\n\n## Context\n\nno status line here\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "legacy ADR without a Status line")
        out = self.run_json("--apply")
        [mv] = [m for m in out["moves"] if m["slug"] == "nostat"]
        body = self.read(mv["to"])
        self.assertTrue(body.startswith("# ADR-0009: nostat\n\n- **Epic:** E007\n"))

    def test_apply_refuses_when_the_touched_paths_are_already_dirty(self):
        self.write(f"{IMPL}/epic-001/arch/stray.md", "stray uncommitted change\n")
        before = self.git("status", "--porcelain")
        r = self.sa("migrate-adrs", "--apply")
        self.assertEqual(r.returncode, 2)
        self.assertIn("uncommitted", r.stderr.lower())
        self.assertFalse(os.path.exists(self.path("docs/adr/0004-cache.md")))   # nothing moved
        self.assertEqual(self.git("status", "--porcelain"), before)             # tree unchanged

    def test_apply_refuses_when_a_non_source_epic_reference_is_dirty(self):
        # A story outside every source epic can still reference the moved ADR's old path (the
        # loop's path_re.sub runs over every *.md under the implementation root, not just the
        # source epics), so the pre-flight must check it individually, not assume it clean.
        ref = f"{IMPL}/epic-003/sprint-01/stories/E003-S01-001.md"
        self.write(ref, f"# S\n\nSee {IMPL}/epic-001/arch/adr-0004-cache.md for context.\n")
        before = self.git("status", "--porcelain")
        r = self.sa("migrate-adrs", "--apply")
        self.assertEqual(r.returncode, 2)
        self.assertIn("uncommitted", r.stderr.lower())
        self.assertFalse(os.path.exists(self.path("docs/adr/0004-cache.md")))   # nothing moved
        self.assertEqual(self.git("status", "--porcelain"), before)             # tree unchanged

    def test_apply_reports_touched_paths_when_the_commit_fails(self):
        # The move loop must succeed -- every ADR already moved and rewritten on disk -- with
        # only the final commit failing (a stuck index.lock, the pattern TestCommit uses). A
        # lock present from the start would also fail the loop's own `git mv`/`git add`, so a
        # background watcher drops it the instant the second move's destination file appears
        # on disk (git mv having already renamed it), leaving plenty of remaining move-loop
        # work (the epic-line write, the md_files rewrite pass, the rewritten/commit-paths
        # split) as headroom before the real commit attempt.
        lock = self.path(".git/index.lock")
        self.addCleanup(lambda: os.path.exists(lock) and os.remove(lock))
        target = self.path("docs/adr/0004-cache.md")

        def drop_lock_once_moved():
            deadline = time.time() + 5
            while not os.path.exists(target) and time.time() < deadline:
                time.sleep(0.01)
            if os.path.exists(target):
                with open(lock, "w"):
                    pass

        threading.Thread(target=drop_lock_once_moved, daemon=True).start()
        r = self.sa("migrate-adrs", "--apply")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("stayed locked", r.stderr)
        self.assertIn("paths already moved or rewritten in this run", r.stderr)
        self.assertIn("docs/adr/0004-cache.md", r.stderr)


if __name__ == "__main__":
    unittest.main()
