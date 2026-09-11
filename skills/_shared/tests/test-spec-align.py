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

    def sa(self, *args, spec_paths=None, planning=None):
        g = ["--project-root", self.root, "--planning-root", planning or self.planning,
             "--impl-root", self.impl, "--state-root", self.state, "--pm-status", PM]
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


if __name__ == "__main__":
    unittest.main()
