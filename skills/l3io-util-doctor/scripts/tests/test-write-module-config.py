#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["tomlkit>=0.13", "ruamel.yaml>=0.18"]
# ///
"""
Tests for write-module-config.py.

The contract under test: module settings are recorded in the two human-authored BMad
config layers (`_bmad/custom/config.toml` and `config.user.toml`) and nowhere else. The
installer regenerates `_bmad/config.toml` and `config.user.toml` on every install, so a
write there would be silently lost; `_bmad/config.yaml` does not exist at all.

Run with: uv run test-write-module-config.py
"""
import json
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "write-module-config.py"

TEAM_SEED = """\
# Team / enterprise overrides for _bmad/config.toml.
# Committed to the repo — applies to every developer on the project.

# [agents.bmad-agent-pm]
# description = "Prefers short, bulleted PRDs over narrative drafts."
"""


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class Base(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.bmad = self.root / "_bmad"
        self.custom = self.bmad / "custom"
        write(self.custom / "config.toml", TEAM_SEED)
        self.module_yaml = self.root / "module.yaml"
        write(
            self.module_yaml,
            "code: l3io-pm\n"
            "module_version: 9.9.9\n"
            "variables:\n"
            "  - name: implementation_artifacts\n"
            "  - name: max_parallel_subagents\n"
            "  - name: favourite_colour\n"
            "    user_setting: true\n",
        )

    def run_script(self, answers: dict | None = None, extra: list | None = None):
        cmd = [
            "uv", "run", str(SCRIPT),
            "--project-root", str(self.root),
            "--module-yaml", str(self.module_yaml),
        ]
        if answers is not None:
            answers_path = self.root / "answers.json"
            write(answers_path, json.dumps({"module": answers}))
            cmd += ["--answers", str(answers_path)]
        cmd += extra or []
        proc = subprocess.run(cmd, capture_output=True, text=True)
        return proc

    def team(self) -> dict:
        p = self.custom / "config.toml"
        return tomllib.loads(p.read_text()) if p.exists() else {}

    def user(self) -> dict:
        p = self.custom / "config.user.toml"
        return tomllib.loads(p.read_text()) if p.exists() else {}


class TestDestination(Base):
    def test_team_keys_go_to_custom_config_toml(self):
        proc = self.run_script({"max_parallel_subagents": 6})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.team()["modules"]["l3io-pm"]["max_parallel_subagents"], 6)

    def test_user_settings_go_to_the_gitignored_layer_only(self):
        self.run_script({"favourite_colour": "green", "max_parallel_subagents": 6})
        self.assertEqual(self.user()["modules"]["l3io-pm"]["favourite_colour"], "green")
        # A personal preference must never land in the committed file.
        self.assertNotIn("favourite_colour", self.team()["modules"]["l3io-pm"])

    def test_never_writes_installer_owned_layers_or_a_yaml_config(self):
        self.run_script({"max_parallel_subagents": 6, "favourite_colour": "green"})
        for forbidden in ("config.toml", "config.user.toml", "config.yaml", "config.user.yaml"):
            self.assertFalse(
                (self.bmad / forbidden).exists(),
                f"_bmad/{forbidden} must not be created — installer-owned or nonexistent",
            )

    def test_preserves_surrounding_comments(self):
        self.run_script({"max_parallel_subagents": 6})
        text = (self.custom / "config.toml").read_text()
        self.assertIn("Committed to the repo", text)
        self.assertIn("bmad-agent-pm", text)


class TestAntiZombie(Base):
    def test_dropped_key_does_not_survive_a_rewrite(self):
        self.run_script({"implementation_artifacts": "/a", "max_parallel_subagents": 6})
        self.run_script({"max_parallel_subagents": 8})
        pm = self.team()["modules"]["l3io-pm"]
        self.assertEqual(pm, {"max_parallel_subagents": 8})

    def test_other_modules_are_untouched(self):
        other = self.root / "module-sec.yaml"
        write(other, "code: l3io-sec\nvariables:\n  - name: max_parallel_subagents\n")
        self.run_script({"max_parallel_subagents": 6})
        subprocess.run(
            ["uv", "run", str(SCRIPT), "--project-root", str(self.root),
             "--module-yaml", str(other), "--answers", str(self._answers({"max_parallel_subagents": 2}))],
            capture_output=True, text=True, check=True,
        )
        self.run_script({"max_parallel_subagents": 8})
        modules = self.team()["modules"]
        self.assertEqual(modules["l3io-sec"]["max_parallel_subagents"], 2)
        self.assertEqual(modules["l3io-pm"]["max_parallel_subagents"], 8)

    def _answers(self, values: dict) -> Path:
        p = self.root / "answers-other.json"
        write(p, json.dumps({"module": values}))
        return p


class TestValidation(Base):
    def test_undeclared_key_is_rejected(self):
        proc = self.run_script({"bogus_key": "x"})
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("does not declare", proc.stderr)

    def test_no_variables_declared_writes_nothing(self):
        write(self.module_yaml, "code: l3io-util\nmodule_version: 2.0.1\n")
        proc = self.run_script()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertIn("declares no project-level settings", result["note"])
        self.assertFalse((self.custom / "config.user.toml").exists())
        self.assertNotIn("modules", self.team())

    def test_missing_bmad_directory_is_a_hard_error(self):
        bare = Path(tempfile.mkdtemp())
        proc = subprocess.run(
            ["uv", "run", str(SCRIPT), "--project-root", str(bare),
             "--module-yaml", str(self.module_yaml)],
            capture_output=True, text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("BMad is not installed", proc.stderr)

    def test_dry_run_touches_nothing(self):
        proc = self.run_script({"max_parallel_subagents": 6}, extra=["--dry-run"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["team"]["status"], "would-write")
        self.assertNotIn("modules", self.team())


if __name__ == "__main__":
    unittest.main()
