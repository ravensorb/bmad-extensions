#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
Tests for clean-payload.py. Run with:
  uv run tests/l3io-doctor/test-clean-payload.py

This script DELETES FILES, so the cases that matter are the ones asserting what it leaves
alone. Each builds a real installed-shaped tree in a temp dir and drives the CLI through
subprocess, so the exit code and the filesystem afterwards are the real ones.

The scope-attacking cases (CLAUDE.md §4) are `TestNeverTouches`: they plant project state,
a foreign skill, and a user-edited payload file, and assert all three survive `--apply`. A
suite that only checked "the right files were removed" would pass over a script that removed
everything, because everything includes the right files.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(_HERE)),
                       "skills", "l3io-doctor", "scripts", "clean-payload.py")

GENERATED_FROM = "skills/_shared/"


class Base(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d, True)
        (self.d / "_bmad" / "_config").mkdir(parents=True)
        (self.d / "_bmad" / "_config" / "manifest.yaml").write_text("modules: []\n",
                                                                    encoding="utf-8")

    def sha(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def skill(self, name, files, generated_from=GENERATED_FROM, root=".claude/skills"):
        """Create an installed skill. `files` maps a relative path to (content, hash-in-manifest)
        where a hash of None means "record the real hash" (an unmodified shipped file)."""
        d = self.d / root / name
        entries = {}
        for rel, (content, recorded) in files.items():
            p = d / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            entries[rel] = recorded if recorded is not None else self.sha(content)
        d.mkdir(parents=True, exist_ok=True)
        (d / "payload-manifest.json").write_text(json.dumps(
            {"version": "3.2.4", "generated_from": generated_from, "files": entries}),
            encoding="utf-8")
        return d

    def run_cli(self, *extra):
        r = subprocess.run([sys.executable, _SCRIPT, "--project-root", str(self.d), *extra],
                           capture_output=True, text=True)
        return r.returncode, r.stdout, r.stderr

    def exists(self, rel):
        return (self.d / rel).exists()


class TestRemoval(Base):
    def test_a_file_matching_its_recorded_hash_is_removed(self):
        self.skill("l3io-doctor", {"scripts/a.py": ("payload\n", None)})
        code, out, err = self.run_cli("--apply")
        self.assertEqual(code, 0, out + err)
        self.assertFalse(self.exists(".claude/skills/l3io-doctor/scripts/a.py"))

    def test_the_manifest_itself_is_removed_too(self):
        """It is our file and it is the last thing describing a tree that is gone."""
        self.skill("l3io-doctor", {"scripts/a.py": ("payload\n", None)})
        self.run_cli("--apply")
        self.assertFalse(self.exists(".claude/skills/l3io-doctor/payload-manifest.json"))

    def test_a_dry_run_changes_nothing(self):
        self.skill("l3io-doctor", {"scripts/a.py": ("payload\n", None)})
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertIn("Would remove", out)
        self.assertTrue(self.exists(".claude/skills/l3io-doctor/scripts/a.py"))

    def test_dry_run_is_the_default(self):
        """`--apply` is opt-in. A destructive default is how a read turns into a delete."""
        self.skill("l3io-doctor", {"scripts/a.py": ("payload\n", None)})
        self.run_cli()
        self.assertTrue(self.exists(".claude/skills/l3io-doctor/scripts/a.py"))

    def test_both_skill_roots_are_covered(self):
        """An install writes .claude/skills and .agents/skills byte-identically. Cleaning one
        and leaving the other would report success over a half-removed extension."""
        self.skill("l3io-doctor", {"scripts/a.py": ("payload\n", None)})
        self.skill("l3io-doctor", {"scripts/a.py": ("payload\n", None)},
                   root=".agents/skills")
        code, out, err = self.run_cli("--apply")
        self.assertEqual(code, 0, out + err)
        self.assertFalse(self.exists(".claude/skills/l3io-doctor/scripts/a.py"))
        self.assertFalse(self.exists(".agents/skills/l3io-doctor/scripts/a.py"))

    def test_no_payload_found_is_exit_4(self):
        code, out, _ = self.run_cli()
        self.assertEqual(code, 4)
        self.assertIn("no l3io payload found", out)


class TestNeverTouches(Base):
    """The cases this script exists to get right. Each plants something that must survive."""

    def test_project_state_survives(self):
        """`state/` is the project's own data — epics, sprints, the backlog, calibration —
        built over months and only READ by our skills. It is in no payload manifest, so the
        derived scope already excludes it; this asserts the exclusion rather than trusting it."""
        state = self.d / "_bmad-output" / "state" / "active" / "epic-001"
        state.mkdir(parents=True)
        (state / "epic.yaml").write_text("key: 'E001'\n", encoding="utf-8")
        (self.d / "_bmad-output" / "state" / "issues.yaml").write_text("backlog: []\n",
                                                                       encoding="utf-8")
        self.skill("l3io-doctor", {"scripts/a.py": ("payload\n", None)})
        code, out, err = self.run_cli("--apply")
        self.assertEqual(code, 0, out + err)
        self.assertTrue(self.exists("_bmad-output/state/active/epic-001/epic.yaml"))
        self.assertTrue(self.exists("_bmad-output/state/issues.yaml"))

    def test_a_modified_payload_file_is_kept_and_reported(self):
        """A differing hash means somebody edited it. That edit is theirs. Leaving it is an
        inconvenience they can see; deleting it is unrecoverable."""
        self.skill("l3io-doctor", {"scripts/edited.py": ("THEIR EDIT\n", "00" * 32)})
        code, out, err = self.run_cli("--apply")
        self.assertEqual(code, 0, out + err)
        self.assertTrue(self.exists(".claude/skills/l3io-doctor/scripts/edited.py"))
        self.assertIn("KEEPING", out)
        self.assertIn("edited.py", out)

    def test_both_generated_from_markers_are_recognised_as_ours(self):
        """The manifest's scope widened from "synced from _shared/" to "what the skill
        ships", and `generated_from` moved with it. Accepting only the new value would walk
        past every project installed before the change — reporting `none-found` and removing
        nothing, which reads exactly like a clean uninstall and is the most dangerous way to
        be wrong on this path."""
        self.skill("l3io-plan", {"scripts/a.py": ("payload\n", None)},
                   generated_from="skills/<skill>/")
        self.skill("l3io-doctor", {"scripts/b.py": ("payload\n", None)},
                   generated_from="skills/_shared/")
        code, out, err = self.run_cli("--apply")
        self.assertEqual(code, 0, out + err)
        self.assertFalse(self.exists(".claude/skills/l3io-plan/scripts/a.py"),
                         "a manifest written after the scope change must be recognised")
        self.assertFalse(self.exists(".claude/skills/l3io-doctor/scripts/b.py"),
                         "a manifest written before it must still be recognised")

    def test_a_foreign_skill_is_untouched_and_unmentioned(self):
        """BMad core skills sit in the same directory and carry their own manifests.
        Identity is our `generated_from`, not a name prefix."""
        self.skill("bmad-code-review", {"scripts/x.py": ("theirs\n", None)},
                   generated_from="somewhere/else/")
        self.skill("l3io-doctor", {"scripts/a.py": ("payload\n", None)})
        code, out, err = self.run_cli("--apply")
        self.assertEqual(code, 0, out + err)
        self.assertTrue(self.exists(".claude/skills/bmad-code-review/scripts/x.py"))
        self.assertTrue(self.exists(".claude/skills/bmad-code-review/payload-manifest.json"))
        self.assertNotIn("bmad-code-review", out)

    def test_an_unlisted_file_in_our_own_skill_is_untouched(self):
        """Not every file under our skill directory is payload — a user may have dropped
        something there. Only manifest entries are ours."""
        d = self.skill("l3io-doctor", {"scripts/a.py": ("payload\n", None)})
        (d / "scripts" / "their-notes.md").write_text("mine\n", encoding="utf-8")
        code, out, err = self.run_cli("--apply")
        self.assertEqual(code, 0, out + err)
        self.assertTrue(self.exists(".claude/skills/l3io-doctor/scripts/their-notes.md"))

    def test_a_directory_holding_a_survivor_is_not_pruned(self):
        """Pruning is rmdir, never recursive: a non-empty directory is left alone, which is
        what stops one stray file taking its whole tree with it."""
        self.skill("l3io-doctor", {"scripts/a.py": ("payload\n", None),
                                   "scripts/edited.py": ("THEIR EDIT\n", "00" * 32)})
        self.run_cli("--apply")
        self.assertTrue(self.exists(".claude/skills/l3io-doctor/scripts"))
        self.assertTrue(self.exists(".claude/skills/l3io-doctor/scripts/edited.py"))

    def test_the_bmad_install_itself_is_untouched(self):
        self.skill("l3io-doctor", {"scripts/a.py": ("payload\n", None)})
        self.run_cli("--apply")
        self.assertTrue(self.exists("_bmad/_config/manifest.yaml"))


class TestSelfInstalledCopy(Base):
    """`_bmad/scripts/pm-status.py` is our payload but lives outside any skill directory."""

    def _self_install(self, content):
        p = self.d / "_bmad" / "scripts"
        p.mkdir(parents=True, exist_ok=True)
        (p / "pm-status.py").write_text(content, encoding="utf-8")

    def test_removed_when_it_matches_a_shipped_copy(self):
        """Safe to remove: self-install rewrites it at the next skill activation."""
        body = "#!/usr/bin/env python3\n# pm-status-version: 3.2.4\n"
        self.skill("l3io-doctor", {"scripts/pm-status.py": (body, None)})
        self._self_install(body)
        code, out, err = self.run_cli("--apply")
        self.assertEqual(code, 0, out + err)
        self.assertFalse(self.exists("_bmad/scripts/pm-status.py"))

    def test_kept_when_it_does_not_match(self):
        """A copy that differs from every shipped one is either locally patched or from
        another version. Either way it is not ours to delete."""
        self.skill("l3io-doctor", {"scripts/pm-status.py": ("shipped\n", None)})
        self._self_install("LOCALLY PATCHED\n")
        code, out, err = self.run_cli("--apply")
        self.assertEqual(code, 0, out + err)
        self.assertTrue(self.exists("_bmad/scripts/pm-status.py"))
        self.assertIn("KEEPING", out)

    def test_bmad_core_scripts_beside_it_survive(self):
        """resolve_config.py and friends are BMad core's, installed in the same directory,
        and this package is explicit that it must never bundle or own them."""
        body = "shipped\n"
        self.skill("l3io-doctor", {"scripts/pm-status.py": (body, None)})
        self._self_install(body)
        (self.d / "_bmad" / "scripts" / "resolve_config.py").write_text("core\n",
                                                                        encoding="utf-8")
        code, out, err = self.run_cli("--apply")
        self.assertEqual(code, 0, out + err)
        self.assertTrue(self.exists("_bmad/scripts/resolve_config.py"))


class TestReporting(Base):
    def test_json_lists_removable_modified_and_missing(self):
        self.skill("l3io-doctor", {"scripts/a.py": ("payload\n", None),
                                   "scripts/edited.py": ("THEIR EDIT\n", "00" * 32),
                                   "scripts/gone.py": ("never written", None)})
        os.remove(self.d / ".claude/skills/l3io-doctor/scripts/gone.py")
        code, out, _ = self.run_cli("--format", "json")
        self.assertEqual(code, 0)
        d = json.loads(out)
        self.assertEqual(d["status"], "dry-run")
        self.assertIn(".claude/skills/l3io-doctor/scripts/a.py", d["removable"])
        self.assertIn(".claude/skills/l3io-doctor/scripts/edited.py", d["modified"])
        self.assertIn(".claude/skills/l3io-doctor/scripts/gone.py", d["missing"])

    def test_a_manifest_entry_already_absent_is_not_an_error(self):
        """An interrupted earlier clean, or a file removed by hand, is a normal state."""
        self.skill("l3io-doctor", {"scripts/gone.py": ("never written", None)})
        os.remove(self.d / ".claude/skills/l3io-doctor/scripts/gone.py")
        code, out, err = self.run_cli("--apply")
        self.assertEqual(code, 0, out + err)
        self.assertIn("already absent", out)

    def test_an_unreadable_manifest_is_skipped_not_fatal(self):
        d = self.d / ".claude" / "skills" / "l3io-broken"
        d.mkdir(parents=True)
        (d / "payload-manifest.json").write_text("{not json", encoding="utf-8")
        self.skill("l3io-doctor", {"scripts/a.py": ("payload\n", None)})
        code, out, err = self.run_cli("--apply")
        self.assertEqual(code, 0, out + err)
        self.assertFalse(self.exists(".claude/skills/l3io-doctor/scripts/a.py"))
        self.assertTrue(self.exists(".claude/skills/l3io-broken/payload-manifest.json"))

    def test_the_output_says_state_is_untouched(self):
        """The operator is about to authorise a delete; the one thing they need to know is
        what is NOT in scope."""
        self.skill("l3io-doctor", {"scripts/a.py": ("payload\n", None)})
        _, out, _ = self.run_cli()
        self.assertIn("state and artifacts are not touched", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
