#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["tomlkit>=0.13", "ruamel.yaml>=0.18"]
# ///
"""
Tests for merge-config.py -- the runpy wrapper around write-module-config.py.

The wrapper has no logic of its own beyond delegation, but a wrapper that silently
swallowed a failure (wrong exit code, wrong argv[0], never reaching the delegate) would
be worse than no wrapper at all. These tests exercise the delegation itself, not
write-module-config.py's own behaviour (covered by test-write-module-config.py).

Run with: uv run test-merge-config-wrapper.py
"""
import subprocess
import unittest
from pathlib import Path


class TestWrapperDelegation(unittest.TestCase):
    SCRIPT = Path(__file__).resolve().parents[1] / "merge-config.py"

    def run_wrapper(self, *args):
        return subprocess.run(["uv", "run", str(self.SCRIPT), *args],
                              capture_output=True, text=True)

    def test_missing_required_arg_propagates_argparse_exit_2(self):
        r = self.run_wrapper()
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_unresolved_project_root_token_is_rejected(self):
        r = self.run_wrapper("--project-root", "{project-root}",
                             "--module-yaml", "x", "--answers", "y")
        self.assertNotEqual(r.returncode, 0)

    def test_delegates_to_write_module_config(self):
        r = self.run_wrapper("--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("custom/config.toml", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
