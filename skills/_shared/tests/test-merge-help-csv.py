#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# ///
"""
Tests for merge-help-csv.py.

The contract under test: rows belonging to --module-code are replaced wholesale (anti-
zombie -- a capability dropped from the module cannot survive as a stale row), every
other module's rows and their order are preserved, and an unresolved {project-root}
token in either path argument is rejected rather than silently written under a literal
path containing braces.

Run with: uv run test-merge-help-csv.py
"""
import csv
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "merge-help-csv.py"


def write_csv(path: Path, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        for row in rows:
            fh.write(row + "\n")


# -- temp-dir leak guard, matching test-write-module-config.py's pattern --------------- #
_RUN_TMP = None
_PREV_TMPDIR = None
_PREV_TEMPFILE_TEMPDIR = None


def setUpModule():
    global _RUN_TMP, _PREV_TMPDIR, _PREV_TEMPFILE_TEMPDIR
    _PREV_TEMPFILE_TEMPDIR = tempfile.tempdir
    _RUN_TMP = tempfile.mkdtemp(prefix="test-merge-help-csv-")
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


class Base(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)

    def make_project(self, existing_help: list[str] | None = None) -> Path:
        if existing_help is not None:
            write_csv(self.root / "_bmad" / "_config" / "bmad-help.csv", existing_help)
        return self.root

    def run_merge(self, root: Path, module_code: str, rows: list[str],
                  header: str = "skill,module,description"):
        source = self.root / f"module-help-{module_code}.csv"
        write_csv(source, [header] + rows)
        cmd = [
            "uv", "run", str(SCRIPT),
            "--project-root", str(root),
            "--module-help-csv", str(source),
            "--module-code", module_code,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        return proc

    def help_csv_rows(self) -> list[list[str]]:
        path = self.root / "_bmad" / "_config" / "bmad-help.csv"
        with path.open(encoding="utf-8", newline="") as fh:
            return list(csv.reader(fh))


class TestAntiZombieMerge(Base):
    def test_replaces_only_this_modules_rows(self):
        root = self.make_project(existing_help=[
            "skill,module,description",
            "bmad-help,core,Core help",
            "l3io-old,l3io-pm,Stale row",
        ])
        proc = self.run_merge(root, module_code="l3io-pm", rows=[
            "l3io-pm-execute,l3io-pm,Run the plan"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        text = (root / "_bmad" / "_config" / "bmad-help.csv").read_text()
        self.assertIn("bmad-help,core,Core help", text)
        self.assertIn("l3io-pm-execute,l3io-pm,Run the plan", text)
        self.assertNotIn("l3io-old", text)

    def test_other_modules_rows_keep_their_order(self):
        root = self.make_project(existing_help=[
            "skill,module,description",
            "bmad-help,core,Core help",
            "l3io-sec-redteam,l3io-sec,Red team",
            "l3io-old,l3io-pm,Stale row",
            "l3io-arch-review,l3io-arch,Arch review",
        ])
        self.run_merge(root, module_code="l3io-pm", rows=[
            "l3io-pm-execute,l3io-pm,Run the plan"])
        rows = self.help_csv_rows()
        module_col = [r[1] for r in rows[1:]]
        self.assertEqual(
            [m for m in module_col if m in ("core", "l3io-sec", "l3io-arch")],
            ["core", "l3io-sec", "l3io-arch"],
        )

    def test_creates_the_file_when_absent(self):
        root = self.make_project(existing_help=None)
        proc = self.run_merge(root, module_code="l3io-util", rows=[
            "l3io-util-doctor,l3io-util,Diagnostics"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        text = (root / "_bmad" / "_config" / "bmad-help.csv").read_text()
        self.assertIn("l3io-util-doctor,l3io-util,Diagnostics", text)

    def test_a_second_merge_with_fewer_rows_drops_the_removed_capability(self):
        root = self.make_project(existing_help=None)
        self.run_merge(root, module_code="l3io-pm", rows=[
            "l3io-pm-execute,l3io-pm,Run the plan",
            "l3io-pm-help,l3io-pm,Get help",
        ])
        self.run_merge(root, module_code="l3io-pm", rows=[
            "l3io-pm-execute,l3io-pm,Run the plan",
        ])
        text = (root / "_bmad" / "_config" / "bmad-help.csv").read_text()
        self.assertIn("l3io-pm-execute", text)
        self.assertNotIn("l3io-pm-help", text)

    def test_source_header_row_is_not_duplicated_into_the_target(self):
        root = self.make_project(existing_help=None)
        self.run_merge(root, module_code="l3io-pm", rows=[
            "l3io-pm-execute,l3io-pm,Run the plan"])
        rows = self.help_csv_rows()
        self.assertEqual(rows[0], ["skill", "module", "description"])
        self.assertEqual(sum(1 for r in rows if r == rows[0]), 1)


class TestUnresolvedTokenRejected(Base):
    def test_unresolved_project_root_token_is_rejected(self):
        source = self.root / "module-help.csv"
        write_csv(source, ["skill,module,description", "x,l3io-pm,y"])
        proc = subprocess.run(
            ["uv", "run", str(SCRIPT),
             "--project-root", "{project-root}",
             "--module-help-csv", str(source),
             "--module-code", "l3io-pm"],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("{project-root}", proc.stderr)

    def test_unresolved_module_help_csv_token_is_rejected(self):
        proc = subprocess.run(
            ["uv", "run", str(SCRIPT),
             "--project-root", str(self.root),
             "--module-help-csv", "{project-root}/assets/module-help.csv",
             "--module-code", "l3io-pm"],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 2, proc.stderr)


if __name__ == "__main__":
    unittest.main()
