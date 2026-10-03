#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
"""
Tests for report-version.py. Run with:
  uv run tests/l3io-doctor/test-report-version.py

Every case builds a fake installed skills tree in a temp dir and drives the real script
through subprocess, so the exit code is the one `/l3io-doctor version` actually returns.
The exit codes are the interface (0 agree, 3 mixed, 4 none found), so each gets a case.

The cases that matter most here attack the SCOPE, not the rule: this script reports
agreement over whatever set it discovered, so a discovery that silently covers fewer
skills than are installed would report `current` over a tree that disagrees. Two cases
plant exactly that -- a disagreeing skill that must be found, and a foreign skill that
must not be.
"""
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
                       "skills", "l3io-doctor", "scripts", "report-version.py")
if not os.path.exists(_SCRIPT):   # running from the repo root layout
    _SCRIPT = os.path.join(os.path.dirname(os.path.dirname(_HERE)),
                           "bmad-extensions", "skills", "l3io-doctor", "scripts",
                           "report-version.py")


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.skills = Path(self.d) / "skills"
        self.skills.mkdir()

    def skill(self, name, version, generated_from="skills/_shared/",
              module=None, manifest_text=None, module_text=None):
        """Create one skill directory. `manifest_text`/`module_text` write raw bytes so a
        case can plant a corrupt file; otherwise both are generated."""
        d = self.skills / name
        d.mkdir(parents=True, exist_ok=True)
        body = manifest_text if manifest_text is not None else json.dumps(
            {"version": version, "generated_from": generated_from, "files": {}})
        (d / "payload-manifest.json").write_text(body, encoding="utf-8")
        if module or module_text is not None:
            (d / "assets").mkdir(exist_ok=True)
            my = module_text if module_text is not None else (
                f"code: {module}\nname: \"m\"\nmodule_version: {version}\n")
            (d / "assets" / "module.yaml").write_text(my, encoding="utf-8")
        return d

    def run_cli(self, *extra):
        r = subprocess.run([sys.executable, _SCRIPT, "--skills-root", str(self.skills),
                            *extra], capture_output=True, text=True)
        return r.returncode, r.stdout, r.stderr


class TestAgreement(Base):
    def test_all_skills_agreeing_is_exit_0_and_one_headline_version(self):
        self.skill("l3io-execute", "3.2.4")
        self.skill("l3io-doctor", "3.2.4", module="l3io-util")
        code, out, err = self.run_cli()
        self.assertEqual(code, 0, err)
        self.assertIn("l3io-extensions 3.2.4", out)
        self.assertIn("2 skills installed", out)

    def test_a_module_home_reports_its_module_code_and_version(self):
        self.skill("l3io-setup", "3.2.4", module="l3io-pm")
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertIn("module l3io-pm 3.2.4", out)

    def test_a_skill_without_module_yaml_is_not_a_finding(self):
        """Only the four module homes carry module.yaml. The other four payload-bearing
        skills correctly have none, and that must not read as an error."""
        self.skill("l3io-execute", "3.2.4")
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertNotIn("!", out)

    def test_a_directory_with_no_manifest_is_skipped_silently(self):
        """The deprecated forwarders ship no payload, so they carry no manifest. Their
        absence is the designed state, not an incomplete install."""
        self.skill("l3io-execute", "3.2.4")
        (self.skills / "l3io-pm-execute").mkdir()
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertIn("1 skills installed", out)
        self.assertNotIn("l3io-pm-execute", out)


class TestScope(Base):
    """These are the cases the reporter exists to get right. It reports agreement over
    the set it discovered, so narrow discovery produces a confident wrong answer."""

    def test_a_disagreeing_skill_is_found_and_turns_the_verdict_mixed(self):
        """Plant the violation against the SCOPE: if discovery missed this skill, the
        script would print `l3io-extensions 3.2.4` over a half-upgraded tree."""
        self.skill("l3io-execute", "3.2.4")
        self.skill("l3io-plan", "3.2.2")
        code, out, _ = self.run_cli()
        self.assertEqual(code, 3, out)
        self.assertIn("MIXED VERSIONS", out)
        self.assertIn("3.2.2", out)
        self.assertIn("3.2.4", out)

    def test_a_module_version_disagreeing_with_its_own_payload_is_mixed(self):
        """The two surfaces are written by different build steps, so they can disagree
        with each other inside a single skill -- not only across skills."""
        d = self.skill("l3io-doctor", "3.2.4")
        (d / "assets").mkdir(exist_ok=True)
        (d / "assets" / "module.yaml").write_text(
            "code: l3io-util\nmodule_version: 3.1.9\n", encoding="utf-8")
        code, out, _ = self.run_cli()
        self.assertEqual(code, 3, out)
        self.assertIn("3.1.9", out)

    def test_a_foreign_skill_with_its_own_manifest_is_not_counted(self):
        """BMad core skills live in the same .claude/skills/ directory. Identity is our
        `generated_from`, not a name prefix, so a foreign manifest -- even one carrying a
        `version` -- cannot drag the verdict to mixed."""
        self.skill("l3io-execute", "3.2.4")
        self.skill("bmad-code-review", "6.12.0", generated_from="somewhere/else/")
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0, out)
        self.assertIn("1 skills installed", out)
        self.assertNotIn("6.12.0", out)

    def test_no_l3io_skills_is_exit_4_and_names_the_fix(self):
        code, out, _ = self.run_cli()
        self.assertEqual(code, 4)
        self.assertIn("no l3io skills found", out)
        self.assertIn("--skills-root", out)


class TestCorruptInput(Base):
    def test_an_unreadable_manifest_is_reported_not_crashed(self):
        self.skill("l3io-execute", "3.2.4")
        self.skill("l3io-plan", "x", manifest_text="{not json")
        code, out, _ = self.run_cli()
        self.assertIn("payload-manifest.json unreadable", out)
        self.assertIn("l3io-extensions 3.2.4", out)
        self.assertEqual(code, 0, out)

    def test_an_unreadable_module_yaml_is_reported_not_crashed(self):
        self.skill("l3io-doctor", "3.2.4", module_text="code: [unclosed\n")
        code, out, _ = self.run_cli()
        self.assertIn("module.yaml unreadable", out)
        self.assertEqual(code, 0, out)


class TestPmStatusSecondary(Base):
    """The self-installed copy is reported, but never as the headline: the installer does
    not write it, so right after a correct upgrade it is legitimately the old version."""

    def _project(self, marker=None):
        p = Path(self.d) / "proj" / "_bmad" / "scripts"
        p.mkdir(parents=True)
        if marker:
            (p / "pm-status.py").write_text(
                f"#!/usr/bin/env python3\n# pm-status-version: {marker}\n", encoding="utf-8")
        return str(Path(self.d) / "proj")

    def test_absent_installed_copy_is_explained_not_flagged(self):
        self.skill("l3io-doctor", "3.2.4", module="l3io-util")
        code, out, _ = self.run_cli("--project-root", self._project())
        self.assertEqual(code, 0, out)
        self.assertIn("absent", out)
        self.assertIn("not by the installer", out)

    def test_a_lagging_installed_copy_does_not_change_the_exit_code(self):
        """This is the STALE transient that made check-pm-status the wrong tool for the
        question. Reporting it must not turn a correct install into a failure."""
        self.skill("l3io-doctor", "3.2.4", module="l3io-util")
        code, out, _ = self.run_cli("--project-root", self._project("3.2.2"))
        self.assertEqual(code, 0, out)
        self.assertIn("self-installed pm-status.py: 3.2.2", out)
        self.assertIn("refreshed at the next skill activation", out)

    def test_a_matching_installed_copy_carries_no_caveat(self):
        self.skill("l3io-doctor", "3.2.4", module="l3io-util")
        code, out, _ = self.run_cli("--project-root", self._project("3.2.4"))
        self.assertEqual(code, 0, out)
        self.assertIn("self-installed pm-status.py: 3.2.4", out)
        self.assertNotIn("refreshed at the next", out)


class TestJson(Base):
    def test_json_carries_status_version_and_every_skill(self):
        self.skill("l3io-execute", "3.2.4")
        self.skill("l3io-doctor", "3.2.4", module="l3io-util")
        code, out, _ = self.run_cli("--format", "json")
        self.assertEqual(code, 0, out)
        d = json.loads(out)
        self.assertEqual(d["status"], "current")
        self.assertEqual(d["version"], "3.2.4")
        self.assertEqual(sorted(s["skill"] for s in d["skills"]),
                         ["l3io-doctor", "l3io-execute"])

    def test_json_mixed_leaves_version_null_and_lists_both(self):
        """A single `version` cannot describe a mixed tree, so it is null rather than an
        arbitrary pick -- a consumer reading only that field gets nothing, not a wrong
        answer."""
        self.skill("l3io-execute", "3.2.4")
        self.skill("l3io-plan", "3.2.2")
        code, out, _ = self.run_cli("--format", "json")
        self.assertEqual(code, 3)
        d = json.loads(out)
        self.assertIsNone(d["version"])
        self.assertEqual(d["versions"], ["3.2.2", "3.2.4"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
