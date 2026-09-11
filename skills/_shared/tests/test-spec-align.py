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


if __name__ == "__main__":
    unittest.main()
