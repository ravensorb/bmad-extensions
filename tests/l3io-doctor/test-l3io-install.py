#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
Tests for install.sh. Run with:
  uv run tests/l3io-doctor/test-l3io-install.py

Every case drives the real script through bash. `--dry-run` is used wherever the action
would otherwise invoke `npx`, so the tests assert the COMMAND the script chose without a
network call — and the command is the entire point of the script, since picking the wrong
one is what cost this estate data.

The refusals are the other half, and they are not conveniences: an upgrade on a tree with
no install has no module set to derive, and a clean has no manifest to decide what is safe
to delete. Both would have to guess. So each refusal gets a case, and each asserts the exit
code as well as the message, because a refusal that printed advice and exited 0 would let a
caller's `&&` chain carry on as though it had worked.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
# The repo root: install.sh is NOT payload. A first install cannot come from payload --
# there is none yet -- so the entry point that must work on an empty tree lives at the root
# and is fetchable on its own.
_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(_HERE)), "install.sh")


class Base(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d, True)

    def install_marker(self):
        """What BMad writes to record an install, and the only thing this script consults.
        Installed-ness is answered by the manifest, never by a config section: a module can
        be installed and unconfigured."""
        p = self.d / "_bmad" / "_config"
        p.mkdir(parents=True, exist_ok=True)
        (p / "manifest.yaml").write_text("modules: []\n", encoding="utf-8")

    def run_sh(self, *args, directory=True):
        argv = ["bash", _SCRIPT, *args]
        if directory:
            argv += ["--directory", str(self.d)]
        r = subprocess.run(argv, capture_output=True, text=True)
        return r.returncode, r.stdout, r.stderr


class TestUpgrade(Base):
    def test_upgrade_on_an_installed_tree_uses_quick_update(self):
        """The whole reason the script exists. `--action quick-update` derives the module set
        and the IDE list off the install; the first-install form makes you transcribe them and
        deletes whatever you leave out."""
        self.install_marker()
        code, out, err = self.run_sh("--action", "upgrade", "--dry-run")
        self.assertEqual(code, 0, out + err)
        self.assertIn("--action quick-update", out)
        self.assertIn("--yes", out)

    def test_upgrade_passes_neither_modules_nor_tools(self):
        """Passing either would switch BMad to the authoritative path, where it removes every
        module and IDE tree the flags do not name. quick-update reads both off the install."""
        self.install_marker()
        _, out, _ = self.run_sh("--action", "upgrade", "--dry-run")
        self.assertNotIn("--modules", out)
        self.assertNotIn("--tools", out)

    def test_upgrade_refuses_when_nothing_is_installed(self):
        code, out, err = self.run_sh("--action", "upgrade")
        self.assertEqual(code, 2)
        self.assertIn("no BMad install found", err)
        self.assertIn("--action install", err)

    def test_it_always_tracks_the_latest_bmad_release(self):
        """`@latest`, never a pinned version and never a bare `bmad-method`.

        A bare `npx` reuses whatever it already cached -- this machine sat on 6.11.0 while
        the fleet ran 6.12.0, which is how a confident wrong answer about the installer came
        from the wrong source. `@latest` resolves the dist-tag on every run.
        """
        self.install_marker()
        _, out, _ = self.run_sh("--action", "upgrade", "--dry-run")
        self.assertIn("bmad-method@latest", out)
        self.assertNotRegex(out, r"bmad-method@\d+\.\d+\.\d+")

    def test_a_version_can_still_be_forced_for_a_deliberate_exception(self):
        """Bisecting an installer regression, or holding a repo back while something upstream
        is broken. Opt-in only -- never the default."""
        self.install_marker()
        _, out, _ = self.run_sh("--action", "upgrade", "--dry-run",
                                "--bmad-version", "9.9.9")
        self.assertIn("bmad-method@9.9.9", out)


class TestInstall(Base):
    def test_install_on_an_empty_tree_passes_the_custom_source(self):
        """Only the first-install form can introduce a custom module, and a tree with no
        install has no module set to delete — so the authoritative flags are safe here."""
        code, out, err = self.run_sh("--action", "install", "--dry-run")
        self.assertEqual(code, 0, out + err)
        self.assertIn("--custom-source", out)
        self.assertIn("--modules", out)
        self.assertIn("--tools", out)
        self.assertNotIn("quick-update", out)

    def test_install_refuses_an_already_installed_tree(self):
        """This is the refusal that matters most. Running the first-install form over an
        existing install is what deleted another repo's per-module config.yaml."""
        self.install_marker()
        code, out, err = self.run_sh("--action", "install")
        self.assertEqual(code, 2)
        self.assertIn("already installed", err)
        self.assertIn("--action upgrade", err)

    def test_modules_and_tools_are_overridable(self):
        _, out, _ = self.run_sh("--action", "install", "--dry-run",
                                "--modules", "bmm,tea", "--tools", "claude-code,codex")
        self.assertIn("--modules bmm,tea", out)
        self.assertIn("--tools claude-code,codex", out)

    def test_the_source_is_overridable_for_a_fork(self):
        _, out, _ = self.run_sh("--action", "install", "--dry-run",
                                "--source", "https://example.invalid/fork")
        self.assertIn("https://example.invalid/fork", out)


class TestClean(Base):
    def test_clean_refuses_when_nothing_is_installed(self):
        """No manifest means no way to decide what is safe to delete, and guessing is how an
        over-broad delete happens."""
        code, out, err = self.run_sh("--action", "clean")
        self.assertEqual(code, 2)
        self.assertIn("no BMad install found", err)

    def payload(self, with_helper=True):
        """A minimal installed payload: one shipped file, the manifest claiming it, and the
        clean helper itself. Built by hand because no verb of ours installs skills -- the
        installer does -- and `install.sh` is not payload, so it has to FIND the helper in
        the installed tree rather than beside itself."""
        import hashlib
        import json
        d = self.d / ".claude" / "skills" / "l3io-doctor" / "scripts"
        d.mkdir(parents=True, exist_ok=True)
        (d / "a.py").write_text("payload\n", encoding="utf-8")
        h = hashlib.sha256(b"payload\n").hexdigest()
        (d.parent / "payload-manifest.json").write_text(json.dumps(
            {"version": "3.2.4", "generated_from": "skills/_shared/",
             "files": {"scripts/a.py": h}}), encoding="utf-8")
        if with_helper:
            real = os.path.join(os.path.dirname(os.path.dirname(_HERE)),
                                "skills", "l3io-doctor", "scripts", "clean-payload.py")
            shutil.copy(real, d / "clean-payload.py")

    def test_clean_is_a_dry_run_without_apply(self):
        self.install_marker()
        self.payload()
        code, out, err = self.run_sh("--action", "clean")
        self.assertEqual(code, 0, out + err)
        self.assertIn("Would remove", out)
        self.assertIn("Re-run with --apply", out + err)
        self.assertTrue((self.d / ".claude/skills/l3io-doctor/scripts/a.py").exists())

    def test_the_helpers_exit_code_propagates(self):
        """`set -e` carries the helper's status out, so a caller's `&&` chain stops rather
        than treating "nothing found" as done.

        Reaching exit 4 through install.sh needs the helper present with no valid manifest
        beside it -- a half-removed payload. That is reachable and real: the manifest is
        itself removable payload, so an interrupted clean can leave exactly this shape."""
        self.install_marker()
        self.payload()
        os.remove(self.d / ".claude/skills/l3io-doctor/payload-manifest.json")
        code, out, _ = self.run_sh("--action", "clean")
        self.assertEqual(code, 4)
        self.assertIn("no l3io payload found", out)

    def test_clean_says_so_when_the_helper_is_absent(self):
        """The helper is payload, so a tree whose payload is already gone has nothing to
        decide the delete with. That is a clear message, not a missing-file crash."""
        self.install_marker()
        self.payload(with_helper=False)
        code, _, err = self.run_sh("--action", "clean")
        self.assertEqual(code, 2)
        self.assertIn("no clean-payload.py found", err)

    def test_clean_dry_run_names_the_helper_it_would_call(self):
        """The hash comparison lives in Python because JSON plus hashing over a derived file
        set has outgrown shell (standards-shell.md). The dispatch is still visible."""
        self.install_marker()
        self.payload()
        _, out, _ = self.run_sh("--action", "clean", "--dry-run")
        self.assertIn("clean-payload.py", out)

    def test_apply_is_forwarded(self):
        self.install_marker()
        self.payload()
        _, out, _ = self.run_sh("--action", "clean", "--dry-run", "--apply")
        self.assertIn("--apply", out)


class TestArguments(Base):
    def test_action_is_required_with_no_default(self):
        """There is no safe default: the right command depends on whether the project is
        already installed, and choosing wrong in either direction is destructive."""
        code, out, err = self.run_sh()
        self.assertEqual(code, 2)
        self.assertIn("--action is required", err)

    def test_an_unknown_action_is_refused(self):
        code, _, err = self.run_sh("--action", "sideways")
        self.assertEqual(code, 2)
        self.assertIn("unknown --action", err)

    def test_an_unknown_flag_is_refused_rather_than_ignored(self):
        """A silently ignored flag is how somebody believes they passed --apply."""
        code, _, err = self.run_sh("--action", "upgrade", "--wat")
        self.assertEqual(code, 2)
        self.assertIn("unknown argument", err)

    def test_a_flag_missing_its_value_is_refused(self):
        code, _, err = self.run_sh("--action", directory=False)
        self.assertEqual(code, 2)
        self.assertIn("needs a value", err)

    def test_equals_form_is_accepted(self):
        self.install_marker()
        code, out, err = self.run_sh("--action=upgrade", "--dry-run")
        self.assertEqual(code, 0, out + err)
        self.assertIn("quick-update", out)

    def test_a_missing_directory_is_refused(self):
        code, _, err = self.run_sh("--action", "upgrade", "--directory",
                                   str(self.d / "nope"), directory=False)
        self.assertEqual(code, 2)
        self.assertIn("does not exist", err)

    def test_help_exits_zero_and_describes_all_three_actions(self):
        code, out, _ = self.run_sh("--help", directory=False)
        self.assertEqual(code, 0)
        for word in ("install", "upgrade", "clean"):
            self.assertIn(word, out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
