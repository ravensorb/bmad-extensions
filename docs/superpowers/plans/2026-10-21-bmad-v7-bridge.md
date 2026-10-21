# BMad v7 Bridge (3.5.x) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make this package tell the truth on a BMad v7 install instead of reporting "BMad is not installed here", and close the transcript-resolution gap that silently costs us token actuals.

**Architecture:** Two independent changes on the v6 release line. `bmad-deps.py` gains generation detection and a degraded-but-honest v7 verification path with its own exit code. `pm-status.py` gains a by-elimination fallback for resolving a session transcript when the environment does not name the session. Neither depends on any 4.0.0 decision; both improve the v6 line on their own.

**Tech Stack:** Python 3.11+ (PEP-723, run through `uv`), `unittest`, stdlib `tomllib`, `ruamel.yaml`.

**Spec:** `docs/superpowers/specs/2026-10-16-bmad-v7-layer-design.md` — §8 and §8.1 only. §2–§7 and §12 are 4.0.0 and are **out of scope here**.

## Global Constraints

- **Never edit a per-skill payload copy.** `pm-status.py` is shared: edit `skills/_shared/pm-status.py`, then run `npm run sync:scripts`. `bmad-deps.py` is **not** shared — it is single-consumer and lives at `skills/l3io-doctor/scripts/bmad-deps.py` per ADR-0001, with no sync group. Edit it directly.
- **Test suites live at `tests/{skill-name}/test-*.py`, never under `skills/`.** `run-python-suites.mjs` discovers `skills/_shared/tests/test-*.py` and `tests/**/test-*.py` only. A suite placed under a skill directory is both undiscovered by CI and shipped as payload on a `--custom-source` install.
- **Regenerate payload manifests after any change under `skills/`:** `node scripts/write-payload-manifest.mjs`. `npm run check:manifest` fails until you do.
- **Run Python through `uv`, never bare `python3`.** A PEP-723 suite run under the wrong interpreter turns one real failure into dozens of fake ones.
- **Run whole suites, not a gate subset.** A value asserted in a test is invisible to every `check:docs`-family gate.
- **Commits:** Conventional Commits, DCO sign-off (`git commit -s`), ending with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **Comments explain the code; they never narrate fix history.** Fix history belongs in the commit message, CHANGELOG, or `docs/upgrading.md`.
- **No new npm dependencies.** Check 28 asserts every bare import in a gate script is declared in `package.json`.
- Exit codes already in use by `bmad-deps.py`: `0`, `2`, `3`, `4`, `5`. This plan adds `6`.

## Review Focus

Five conditions the spec implies that no task's happy path exercises. Each has a test pinned to the task that owns the code.

1. **A v7 install whose skills are under `.agents/skills/` and not `.claude/skills/`** — detection must still find the module record. v7 discovers skills across `.<tool>/skills` generally. → Task 1, Step 9.
2. **A `bmod.toml` that is not valid TOML, or carries `[skill]` but no `[bmod]`** — must cost one unknown module, never a crashed run across the whole verify. → Task 2, Step 5.
3. **A tree carrying both `_bmad/_config/manifest.yaml` and `_bmad/scripts/config_utils.py`** (mid-migration) — must behave exactly as it does today, as v6, with no v7 output at all. → Task 1, Step 7.
4. **Two transcripts that both span the node's window** — the fallback must refuse and say so, never tie-break. Picking the likelier file is the exact failure this command exists to prevent. → Task 4, Step 9.
5. **A project directory holding a very large transcript** (51 MB observed on this machine) — the fallback must reject by `mtime` before parsing, or it reads every transcript on the box on every call. → Task 4, Step 11.

---

## Task 1: Generation detection and the `.agents/` skill root

**Files:**
- Modify: `skills/l3io-doctor/scripts/bmad-deps.py` — `resolve()` at 118–133; add `skill_roots()`, `find_bmod_record()`, `detect_generation()`
- Test: `tests/l3io-doctor/test-bmad-deps.py`

**Interfaces:**
- Consumes: `read_manifest(project_root)` — existing, returns `None` when the v6 manifest is absent or unparseable.
- Produces:
  - `skill_roots(project_root) -> list[str]` — the four base directories that may hold skills.
  - `find_bmod_record(project_root) -> str | None` — path of the first `bmod.toml` carrying a `[bmod]` table.
  - `detect_generation(project_root) -> tuple[str, str]` — `("v6"|"v7"|"", evidence_path)`.

- [ ] **Step 1: Add the v7 fixture builder to the test suite**

In `tests/l3io-doctor/test-bmad-deps.py`, inside `class Base`, after `_tree()`:

```python
    def _v7_tree(self, names=(), layout="skills", tool=".claude",
                 modules=(("core-tools", "6.13.0-next"), ("method", "6.13.0-next")),
                 config_utils=True, bad_record=None):
        """A project root shaped like a v7 install: no _bmad/_config/ at all.

        v7 discovers modules from the bmod.toml files in the skill roots, so the fixture
        writes those rather than a central manifest. `tool` selects the root (.claude or
        .agents). `bad_record` writes one extra bmod.toml with the given raw text.
        """
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        for n in names:
            d = os.path.join(root, tool, layout, n)
            os.makedirs(d, exist_ok=True)
            pathlib.Path(d, "SKILL.md").write_text("x", encoding="utf-8")
        for code, version in modules:
            d = os.path.join(root, tool, "skills", f"bmod-{code}")
            os.makedirs(d, exist_ok=True)
            pathlib.Path(d, "bmod.toml").write_text(
                f'[bmod]\ncode = "{code}"\nversion = "{version}"\n'
                'update_source = "github:bmad-code-org/BMAD-METHOD/skills"\n',
                encoding="utf-8")
        if bad_record is not None:
            d = os.path.join(root, tool, "skills", "bmod-broken")
            os.makedirs(d, exist_ok=True)
            pathlib.Path(d, "bmod.toml").write_text(bad_record, encoding="utf-8")
        if config_utils:
            d = os.path.join(root, "_bmad", "scripts")
            os.makedirs(d, exist_ok=True)
            pathlib.Path(d, "config_utils.py").write_text("# v7\n", encoding="utf-8")
        return root
```

- [ ] **Step 2: Write the failing detection tests**

Add a new class at the end of the suite, before `if __name__ == "__main__":`:

```python
class TestGeneration(Base):
    """detect_generation() is imported directly: it is a pure function of the tree, and
    driving it through the CLI would also exercise the verify() wiring that Task 3 adds."""

    @staticmethod
    def _mod():
        import importlib.util
        spec = importlib.util.spec_from_file_location("bmad_deps", SCRIPT)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def test_v6_manifest_is_detected_as_v6(self):
        root = self._tree(["a-one"])
        gen, evidence = self._mod().detect_generation(root)
        self.assertEqual(gen, "v6")
        self.assertTrue(evidence.endswith("manifest.yaml"))

    def test_config_utils_alone_is_detected_as_v7(self):
        root = self._v7_tree(modules=())
        gen, evidence = self._mod().detect_generation(root)
        self.assertEqual(gen, "v7")
        self.assertTrue(evidence.endswith("config_utils.py"))

    def test_bmod_record_alone_is_detected_as_v7(self):
        root = self._v7_tree(config_utils=False)
        gen, evidence = self._mod().detect_generation(root)
        self.assertEqual(gen, "v7")
        self.assertTrue(evidence.endswith("bmod.toml"))

    def test_empty_tree_is_neither(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        self.assertEqual(self._mod().detect_generation(root), ("", ""))

    def test_unreadable_v6_manifest_falls_through_to_v7(self):
        """A manifest that exists but will not parse is not evidence of a working v6 tree.
        read_manifest() already returns None for it, so calling that tree v6 would send the
        caller down a path that fails again on the same file."""
        root = self._v7_tree(config_utils=True)
        mf = os.path.join(root, "_bmad", "_config")
        os.makedirs(mf, exist_ok=True)
        pathlib.Path(mf, "manifest.yaml").write_text("{[not yaml", encoding="utf-8")
        self.assertEqual(self._mod().detect_generation(root)[0], "v7")
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run tests/l3io-doctor/test-bmad-deps.py TestGeneration -v 2>&1 | tail -20`
Expected: FAIL, `AttributeError: module 'bmad_deps' has no attribute 'detect_generation'`

- [ ] **Step 4: Add `tomllib` to the imports**

In `skills/l3io-doctor/scripts/bmad-deps.py`, the import block currently reads `import argparse / csv / json / os / pathlib / sys`. Add `tomllib` in alphabetical position (after `sys` is wrong — it sorts before `sys`):

```python
import argparse
import csv
import json
import os
import pathlib
import sys
import tomllib
```

- [ ] **Step 5: Implement `skill_roots()` and rewrite `resolve()` to use it**

Replace `resolve()` (lines 118–133) with:

```python
def skill_roots(project_root: str) -> list[str]:
    """Every directory that may hold installed skills: project first, then the user's home.

    `.agents` sits beside `.claude` because v7 discovers skills across `.<tool>/skills`
    generally and names `~/.agents` in its own skill-lock path, so a v7 install need not be
    under `.claude` at all. Probing one tool directory would mis-detect such an install as
    absent -- the same shape as the single-layout probe that once let a gate self-skip.
    """
    return [os.path.join(base, tool)
            for base in (project_root, os.path.expanduser("~"))
            for tool in (".claude", ".agents")]


def resolve(name: str, project_root: str) -> str | None:
    """Return the path `name` resolves to, or None. Both layouts, every root.

    6.12.0 installs skills/<name>/SKILL.md; earlier releases install commands/<name>.md.
    Probing only one layout mis-detects an installed skill as absent on the other version,
    which is how a gate came to self-skip silently -- so both are always tried, under every
    root skill_roots() names.
    """
    for root in skill_roots(project_root):
        for rel in (os.path.join("skills", name, "SKILL.md"),
                    os.path.join("commands", f"{name}.md")):
            p = os.path.join(root, rel)
            if os.path.exists(p):
                return p
    return None
```

- [ ] **Step 6: Implement `find_bmod_record()` and `detect_generation()`**

Insert immediately after `read_manifest()` (which ends at line 157 before this change):

```python
def find_bmod_record(project_root: str) -> str | None:
    """Path of the first `bmod.toml` carrying a `[bmod]` table, or None.

    Every v7 skill ships a `bmod.toml`, but only a MODULE RECORD carries a `[bmod]` table --
    a member skill's file carries `[skill]`. Keying on the table rather than the filename is
    what keeps one member skill from being read as an installed module.
    """
    for root in skill_roots(project_root):
        skills = os.path.join(root, "skills")
        if not os.path.isdir(skills):
            continue
        for name in sorted(os.listdir(skills)):
            p = os.path.join(skills, name, "bmod.toml")
            if not os.path.exists(p):
                continue
            try:
                with open(p, "rb") as fh:
                    if isinstance(tomllib.load(fh).get("bmod"), dict):
                        return p
            except (OSError, tomllib.TOMLDecodeError):
                continue
    return None


def detect_generation(project_root: str) -> tuple:
    """('v6'|'v7'|'', evidence path). Which BMad generation is installed here.

    v6 is decided by a manifest that READS, not one that merely exists: read_manifest()
    already returns None for an unparseable file, and calling such a tree v6 would send the
    caller down a path that fails again on the same file.

    Manifest-first ordering is deliberate. A tree carrying both generations -- mid-migration,
    or a v6 install with v7 skills added beside it -- behaves exactly as it does today, so
    this change cannot alter any existing v6 result.

    v7 has no central manifest: `_config` survives only as a reserved directory name in its
    setup script and nothing writes it. The two positive signals are the shared script that
    v7's own resolve_config.py imports, and any module record on disk.
    """
    if read_manifest(project_root) is not None:
        return "v6", os.path.join(project_root, "_bmad", "_config", "manifest.yaml")
    cu = os.path.join(project_root, "_bmad", "scripts", "config_utils.py")
    if os.path.exists(cu):
        return "v7", cu
    rec = find_bmod_record(project_root)
    return ("v7", rec) if rec else ("", "")
```

- [ ] **Step 7: Add the both-generations-present test (Review Focus 3)**

Append to `class TestGeneration`:

```python
    def test_tree_with_both_generations_reads_as_v6(self):
        """Manifest-first is what makes this change unable to alter any existing v6 result.
        A mid-migration tree, or a v6 install with v7 skills beside it, stays v6."""
        root = self._tree(["a-one"])
        d = os.path.join(root, "_bmad", "scripts")
        os.makedirs(d, exist_ok=True)
        pathlib.Path(d, "config_utils.py").write_text("# v7\n", encoding="utf-8")
        gen, evidence = self._mod().detect_generation(root)
        self.assertEqual(gen, "v6")
        self.assertTrue(evidence.endswith("manifest.yaml"))
```

- [ ] **Step 8: Add the `.agents/` resolve test**

Append to `class TestLayouts`:

```python
    def test_agents_root_is_probed(self):
        """v7 discovers skills across `.<tool>/skills`; an install under .agents/ is not
        absent, and reporting it so would silently self-skip the gate that needs it."""
        inv = self._inv([{"name": "a-one", "status": "required"}])
        root = self._v7_tree(["a-one"], tool=".agents")
        code, out = self.run_cli(["verify", "--project-root", root, "--inventory", inv])
        self.assertIn("ok       a-one", out)
```

- [ ] **Step 9: Add the `.agents/`-only detection test (Review Focus 1)**

Append to `class TestGeneration`:

```python
    def test_v7_detected_when_only_agents_root_exists(self):
        root = self._v7_tree(tool=".agents", config_utils=False)
        gen, evidence = self._mod().detect_generation(root)
        self.assertEqual(gen, "v7")
        self.assertIn(".agents", evidence)
```

- [ ] **Step 10: Run the whole suite**

Run: `uv run tests/l3io-doctor/test-bmad-deps.py 2>&1 | tail -20`
Expected: PASS. All 42 pre-existing tests plus the 7 new ones. `test_agents_root_is_probed` will fail until Step 5 is in place; if any *pre-existing* test fails, stop — `resolve()` was changed incorrectly.

- [ ] **Step 11: Regenerate manifests and commit**

```bash
node scripts/write-payload-manifest.mjs
git add skills/l3io-doctor/scripts/bmad-deps.py skills/l3io-doctor/payload-manifest.json tests/l3io-doctor/test-bmad-deps.py
git commit -s -m "feat(l3io-util): detect the BMad generation and probe the .agents skill root

v7 has no _bmad/_config/manifest.yaml -- _config survives only as a
reserved directory name and nothing writes it -- so read_manifest()
returns None and the verifier reports 'BMad is not installed here' on a
tree where it plainly is.

detect_generation() answers v6 from a manifest that reads, v7 from the
shared config_utils.py or any bmod.toml carrying a [bmod] table, and
neither from an empty tree. Manifest-first, so a tree carrying both
behaves exactly as it does today.

resolve() now probes .agents/ beside .claude/: v7 discovers skills across
.<tool>/skills generally, and probing one tool directory is the same
shape as the single-layout probe that once let a gate self-skip.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: Read v7 module records

**Files:**
- Modify: `skills/l3io-doctor/scripts/bmad-deps.py` — add `read_v7_modules()` after `detect_generation()`
- Test: `tests/l3io-doctor/test-bmad-deps.py`

**Interfaces:**
- Consumes: `skill_roots(project_root)` from Task 1.
- Produces: `read_v7_modules(project_root) -> tuple[str | None, list[str], dict[str, str | None]]` — `(version, sorted_codes, {code: version})`. Shaped to match `read_manifest()`'s `(version, modules, module_versions)` so `verify()` can bind either.

- [ ] **Step 1: Write the failing tests**

Append to `class TestGeneration`:

```python
    def test_read_v7_modules_returns_codes_and_uniform_version(self):
        root = self._v7_tree()
        version, codes, versions = self._mod().read_v7_modules(root)
        self.assertEqual(version, "6.13.0-next")
        self.assertEqual(codes, ["core-tools", "method"])
        self.assertEqual(versions["method"], "6.13.0-next")

    def test_mixed_versions_report_none_not_one_of_them(self):
        """A mixed install is a real state. Reporting one record's version as THE version
        would hide it behind a number that looks authoritative."""
        root = self._v7_tree(modules=(("core-tools", "6.13.0-next"), ("method", "6.14.0")))
        version, codes, versions = self._mod().read_v7_modules(root)
        self.assertIsNone(version)
        self.assertEqual(sorted(versions.values()), ["6.13.0-next", "6.14.0"])

    def test_skill_level_bmod_toml_is_not_a_module(self):
        """A member skill's bmod.toml carries [skill], not [bmod]. Counting it would report
        every installed skill as an installed module."""
        root = self._v7_tree(modules=())
        d = os.path.join(root, ".claude", "skills", "bmad-code-review")
        os.makedirs(d, exist_ok=True)
        pathlib.Path(d, "bmod.toml").write_text(
            '[skill]\nbmod = "bmod-method"\nsource = "github:x"\n', encoding="utf-8")
        self.assertEqual(self._mod().read_v7_modules(root)[1], [])

    def test_no_records_returns_empty(self):
        root = self._v7_tree(modules=())
        self.assertEqual(self._mod().read_v7_modules(root), (None, [], {}))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run tests/l3io-doctor/test-bmad-deps.py TestGeneration -v 2>&1 | tail -20`
Expected: FAIL, `AttributeError: module 'bmad_deps' has no attribute 'read_v7_modules'`

- [ ] **Step 3: Implement `read_v7_modules()`**

Insert after `detect_generation()`:

```python
def read_v7_modules(project_root: str) -> tuple:
    """(version, [codes], {code: version}) from the bmod.toml module records on disk.

    v7 has no central manifest; `bmad setup` discovers installed modules by walking the
    bmod.toml files in the skill roots, and this mirrors that. Shaped to match
    read_manifest()'s (version, modules, module_versions) tail so verify() can bind either.

    `version` is the single value when every record agrees, and None when they disagree. A
    mixed install is a real state, and reporting one record's version as THE version would
    hide it behind a number that reads as authoritative.
    """
    mods = {}
    for root in skill_roots(project_root):
        skills = os.path.join(root, "skills")
        if not os.path.isdir(skills):
            continue
        for name in sorted(os.listdir(skills)):
            p = os.path.join(skills, name, "bmod.toml")
            if not os.path.exists(p):
                continue
            try:
                with open(p, "rb") as fh:
                    data = tomllib.load(fh)
            except (OSError, tomllib.TOMLDecodeError):
                # One unreadable record is one unknown module, not a failed run. The verify
                # it is part of still has every other module and every skill probe to report.
                continue
            bmod = data.get("bmod")
            if not isinstance(bmod, dict):
                continue
            code = bmod.get("code")
            if isinstance(code, str) and code and code not in mods:
                mods[code] = bmod.get("version")
    seen = {v for v in mods.values() if isinstance(v, str) and v}
    return (seen.pop() if len(seen) == 1 else None), sorted(mods), mods
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run tests/l3io-doctor/test-bmad-deps.py TestGeneration -v 2>&1 | tail -20`
Expected: PASS

- [ ] **Step 5: Add the malformed-record test (Review Focus 2)**

Append to `class TestGeneration`:

```python
    def test_malformed_bmod_toml_costs_one_module_not_the_run(self):
        root = self._v7_tree(bad_record="[bmod\ncode = ")
        version, codes, _versions = self._mod().read_v7_modules(root)
        self.assertEqual(codes, ["core-tools", "method"])
        self.assertEqual(version, "6.13.0-next")

    def test_bmod_table_that_is_not_a_table_is_skipped(self):
        root = self._v7_tree(bad_record='bmod = "not-a-table"\n')
        self.assertEqual(self._mod().read_v7_modules(root)[1], ["core-tools", "method"])

    def test_detection_survives_a_malformed_record(self):
        """find_bmod_record must not stop at the broken file and report 'not installed'."""
        root = self._v7_tree(bad_record="[bmod\ncode = ", config_utils=False)
        self.assertEqual(self._mod().detect_generation(root)[0], "v7")
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run tests/l3io-doctor/test-bmad-deps.py TestGeneration -v 2>&1 | tail -20`
Expected: PASS. If `test_detection_survives_a_malformed_record` fails, `find_bmod_record`'s `except` is catching too narrowly — it must `continue`, not return.

- [ ] **Step 7: Regenerate manifests and commit**

```bash
node scripts/write-payload-manifest.mjs
git add skills/l3io-doctor/scripts/bmad-deps.py skills/l3io-doctor/payload-manifest.json tests/l3io-doctor/test-bmad-deps.py
git commit -s -m "feat(l3io-util): read v7 module records from bmod.toml

v7 discovers installed modules by walking the bmod.toml files in the
skill roots rather than from a central manifest. read_v7_modules mirrors
that, keying on the [bmod] table so a member skill's [skill] record is
not counted as a module.

A mixed-version install reports None rather than one record's version,
because a number that reads as authoritative would hide the mix. An
unreadable record costs one unknown module, never the run.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: Degraded v7 verification and exit 6

**Files:**
- Modify: `skills/l3io-doctor/scripts/bmad-deps.py` — `verify()` at 271–394, and the module docstring's exit-code and JSON-field contract at 26–82
- Modify: `skills/l3io-doctor/steps/check-deps.md` — the exit table at 16–24
- Test: `tests/l3io-doctor/test-bmad-deps.py`

**Interfaces:**
- Consumes: `detect_generation()` (Task 1), `read_v7_modules()` (Task 2).
- Produces: exit code `6`; JSON field `bmad_generation` (`"v6"` | `"v7"`); `shims_installed` becomes `null` on v7.

- [ ] **Step 1: Write the failing tests**

Add a new class before `if __name__ == "__main__":`:

```python
class TestV7Verify(Base):
    def test_v7_tree_exits_6_not_4(self):
        """The bug: a v7 tree has no _config/manifest.yaml, so the verifier reported
        'is BMad installed?' on a tree where it is."""
        inv = self._inv([{"name": "a-one", "status": "required"}])
        root = self._v7_tree(["a-one"])
        code, out = self.run_cli(["verify", "--project-root", root, "--inventory", inv])
        self.assertEqual(code, 6)
        self.assertIn("ok       a-one", out)

    def test_v7_exit_6_outranks_missing_required(self):
        """bmad-sprint-planning really is absent on v7, so `missing` is non-empty on every
        v7 install. Returning 3 would make 6 unreachable."""
        inv = self._inv([{"name": "a-gone", "status": "required"}])
        root = self._v7_tree([])
        code, out = self.run_cli(["verify", "--project-root", root, "--inventory", inv])
        self.assertEqual(code, 6)
        self.assertIn("MISSING  a-gone", out)

    def test_v7_does_not_print_the_v6_reinstall_remedy(self):
        """That remedy installs the 6.12 line, which over a v7 tree is worse than silence:
        it reaches the user at the one moment they will paste what they are given."""
        inv = self._inv([{"name": "a-gone", "status": "required"}])
        root = self._v7_tree([])
        self.run_cli(["verify", "--project-root", root, "--inventory", inv])
        self.assertNotIn("bmad-method@latest", self.err)
        self.assertIn("v7", self.err)

    def test_v7_reports_generation_and_modules_in_text(self):
        inv = self._inv([{"name": "a-one", "status": "required"}])
        root = self._v7_tree(["a-one"])
        _code, out = self.run_cli(["verify", "--project-root", root, "--inventory", inv])
        self.assertIn("BMad v7 6.13.0-next", out)
        self.assertIn("core-tools", out)
        self.assertIn("NOTE", out)

    def test_v7_json_shape(self):
        inv = self._inv([{"name": "a-one", "status": "required"}])
        root = self._v7_tree(["a-one"])
        _code, out = self.run_cli(["verify", "--project-root", root,
                                   "--inventory", inv, "--format", "json"])
        data = json.loads(out)
        self.assertEqual(data["bmad_generation"], "v7")
        self.assertEqual(data["bmad_version"], "6.13.0-next")
        self.assertIsNone(data["shims_installed"])
        self.assertIsNone(data["shipped_skills"])
        self.assertEqual(data["status_contradictions"], [])

    def test_v6_json_still_reports_its_generation(self):
        inv = self._inv([{"name": "a-one", "status": "required"}])
        root = self._tree(["a-one"])
        _code, out = self.run_cli(["verify", "--project-root", root,
                                   "--inventory", inv, "--format", "json"])
        data = json.loads(out)
        self.assertEqual(data["bmad_generation"], "v6")
        self.assertIs(data["shims_installed"], False)

    def test_empty_tree_still_exits_4(self):
        """Exit 4 keeps its meaning: 'I could not look'. Only a tree with v7 evidence is 6."""
        inv = self._inv([{"name": "a-one", "status": "required"}])
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        code, _out = self.run_cli(["verify", "--project-root", root, "--inventory", inv])
        self.assertEqual(code, 4)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run tests/l3io-doctor/test-bmad-deps.py TestV7Verify -v 2>&1 | tail -20`
Expected: FAIL — most with `4 != 6`; `test_v7_json_shape` with `KeyError: 'bmad_generation'`

- [ ] **Step 3: Replace the manifest read in `verify()`**

In `verify()`, replace these six lines (currently 288–293):

```python
    man = read_manifest(args.project_root)
    if man is None:
        print(f"cannot read {args.project_root}/_bmad/_config/manifest.yaml — is BMad installed?",
              file=sys.stderr)
        return 4
    version, shims, modules, module_versions = man
```

with:

```python
    generation, _evidence = detect_generation(args.project_root)
    if not generation:
        print(f"cannot read {args.project_root}/_bmad/_config/manifest.yaml — is BMad installed?",
              file=sys.stderr)
        return 4
    if generation == "v6":
        version, shims, modules, module_versions = read_manifest(args.project_root)
    else:
        # v7 has no installShims concept. `False` would be a claim about a key that does not
        # exist; None is the truth, and matches the `shipped_skills` unknown convention.
        version, modules, module_versions = read_v7_modules(args.project_root)
        shims = None
```

- [ ] **Step 4: Add `bmad_generation` to the JSON output**

In the `args.format == "json"` branch, change the first key of the dumped object from
`{"bmad_version": version, ...` to:

```python
        print(json.dumps({"bmad_generation": generation,
                          "bmad_version": version, "shims_installed": shims,
```

leaving every other key exactly as it is.

- [ ] **Step 5: Add the generation and NOTE lines to the text output**

Replace the text-output header line:

```python
        print(f"BMad {version} — modules: {', '.join(str(m) for m in modules)}")
```

with:

```python
        label = "v7 " if generation == "v7" else ""
        print(f"BMad {label}{version} — modules: {', '.join(str(m) for m in modules)}")
        if generation == "v7":
            print("  NOTE     v7 install: manifest-derived checks unavailable "
                  "(no skill-manifest.csv); skill probes still ran")
```

- [ ] **Step 6: Gate the v6 remedy and add a v7 one**

Replace the remedy block at the end of the text branch (`if missing:` through the closing `print(...)`) with:

```python
        if missing and generation == "v6":
            # Flush first: unflushed stdout would otherwise let this summary surface ahead of
            # the report it summarizes whenever the two streams are captured separately.
            sys.stdout.flush()
            # NOT `--modules bmm`: that form is authoritative, so BMad would delete every
            # other installed module (cis, tea, ...) to match the flag. Printing it here is
            # worse than printing nothing, because it reaches the user at the one moment they
            # are already worried about a broken install and will paste what they are given.
            print(f"\n{len(missing)} required skill(s) resolve nowhere. Install them, or run "
                  f"`npx -y bmad-method@latest install --directory . --action quick-update "
                  f"--yes` to refresh every installed module without removing any.",
                  file=sys.stderr)
        elif generation == "v7":
            sys.stdout.flush()
            print(f"\nThis is a BMad v7 install. This package targets 6.12, so verification "
                  f"is degraded: skill probes ran, manifest-derived checks could not. "
                  f"{len(missing)} required skill(s) resolve nowhere, which on v7 means the "
                  f"skill was removed rather than that the install is broken — do NOT run a "
                  f"6.12 installer over this tree.", file=sys.stderr)
```

- [ ] **Step 7: Add the exit-code precedence**

Replace the tail of `verify()`:

```python
    if missing:
        return 3
    if args.strict and contradictions:
        return 5
    return 0
```

with:

```python
    # v7 OUTRANKS a missing required skill, and the ordering is the whole point. On v7
    # bmad-sprint-planning really is absent, so `missing` is non-empty on every v7 install:
    # returning 3 would make 6 unreachable. "You are on an unsupported generation" is also
    # the true and actionable diagnosis, where "a required skill is missing" describes a
    # broken v6 install -- which this is not. Exit 5 cannot collide: contradictions is
    # always [] when shipped_skills is None, which it always is on v7.
    if generation == "v7":
        return 6
    if missing:
        return 3
    if args.strict and contradictions:
        return 5
    return 0
```

- [ ] **Step 8: Run the whole suite**

Run: `uv run tests/l3io-doctor/test-bmad-deps.py 2>&1 | tail -20`
Expected: PASS, all classes. `test_absent_manifest_exits_4` must still pass — it builds a tree with no v7 evidence, so exit 4 is unchanged.

- [ ] **Step 9: Update the script's contract docstring**

In the module docstring, change the exit-code paragraph to name 6, and add the two JSON fields. Replace:

```
Exit 0 when every required skill resolves (optional ones only warn), 2 on a usage error or an
```

with:

```
Exit 0 when every required skill resolves (optional ones only warn), 6 on a BMad v7 install
(verification is degraded there and the code outranks 3 -- see verify()), 2 on a usage error or an
```

and insert into the `--format json` field list, immediately above `bmad_version`:

```
  bmad_generation   "v6" or "v7" -- which generation detect_generation() found. v7 has no
                    central manifest, so every manifest-derived field below reports its
                    unknown value there rather than a measured one.
```

and amend the `shims_installed` line to end with: `null on v7, which has no such concept.`

- [ ] **Step 10: Update `check-deps.md`**

In `skills/l3io-doctor/steps/check-deps.md`, insert after the `Exit 0 with shim lines` bullet:

```markdown
- Exit 6 → `DONE — BMad v7 detected; verification degraded.` Print the NOTE line and the
  v7 summary the script wrote to stderr. Skill probes ran and are trustworthy;
  manifest-derived checks (shipped skills, status contradictions) could not run and report
  unknown, not agreement. A `MISSING` line on v7 means the skill was **removed in v7**, not
  that the install is broken — never recommend a 6.12 installer over a v7 tree.
```

and change the `Exit 0 with shim lines` bullet's trailing clause from "These work today and are removed at BMad v7" to "These work on 6.12 and are gone in v7".

- [ ] **Step 11: Run the docs and manifest gates**

```bash
npm run check:docs 2>&1 | tail -20
node scripts/write-payload-manifest.mjs
npm run check:manifest 2>&1 | tail -5
```
Expected: both clean. If `check:docs` flags the new exit code, it is check 30/4 reading the step file's fenced invocations — fix the step file, not the checker.

- [ ] **Step 12: Commit**

```bash
git add skills/l3io-doctor/scripts/bmad-deps.py skills/l3io-doctor/steps/check-deps.md skills/l3io-doctor/payload-manifest.json tests/l3io-doctor/test-bmad-deps.py
git commit -s -m "feat(l3io-util): verify degraded on v7 and exit 6 instead of 4

A v7 tree has no _bmad/_config/manifest.yaml, so the verifier reported
'is BMad installed?' on a tree where it is, and sent the user to
reinstall something already present.

v7 now runs the skill probes -- which work there unchanged -- and lets
the manifest-derived fields fall to their existing unknown conventions.
Exit 6 outranks 3 because bmad-sprint-planning really is absent on v7,
so 3 would make 6 unreachable, and the exit-3 remedy would reinstall the
6.12 line over a v7 tree.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: Transcript resolution fallback

**Files:**
- Modify: `skills/_shared/pm-status.py` — add `_transcript_span()` and `discover_session_transcript()` after `resolve_session_transcript()` (ends line 5558); wire into `cmd_usage()` at 5750–5762
- Test: `skills/_shared/tests/test-pm-status.py`

**Interfaces:**
- Consumes: `transcript_sessions(path)`, `dispatch_window(state_root, agent, epic, sprint, story)`, `resolve_session_transcript(session_id)`, `_parse_iso(s)` — all existing.
- Produces: `discover_session_transcript(state_root, node_keys) -> tuple[list[str], str, str]` — `(paths, session_id, refusal_reason)`. `paths` empty means refused, and `refusal_reason` says why.

- [ ] **Step 1: Write the failing tests**

Add to `skills/_shared/tests/test-pm-status.py`, as a new class:

Add `from datetime import datetime, timedelta, timezone` to the suite's imports if absent, then:

```python
SECOND = timedelta(seconds=1)


class TestTranscriptFallback(Base):
    """The fallback recovers a transcript when CLAUDE_CODE_SESSION_ID is absent. It accepts
    by ELIMINATION -- exactly one candidate spanning the node's dispatch bracket -- and
    refuses otherwise. Summing the wrong file is the failure `usage` exists to prevent.

    The dispatch bracket is written by the REAL dispatch verb, never stubbed: the window
    derivation is half of what makes a candidate verifiable, and stubbing it would leave the
    suite green over a fallback that accepts anything.
    """

    KEYS = {"agent": "dev-story", "epic": "E001", "sprint": "S01", "story": "E001-S01-003"}

    def setUp(self):
        super().setUp()
        self.root = os.path.join(self.d, "state")
        os.makedirs(self.root)
        self.home = os.path.join(self.d, "home")
        self.projects = os.path.join(self.home, ".claude", "projects", "-fake")
        os.makedirs(self.projects)

    def _bracket(self):
        """Open and close a real dispatch; return (before, after) as aware datetimes that
        straddle the recorded pair."""
        before = datetime.now(timezone.utc)
        for event in ("open", "close"):
            code, out = self.run_main(["dispatch", "--state-root", self.root,
                                       "--event", event,
                                       "--agent", self.KEYS["agent"],
                                       "--epic", self.KEYS["epic"],
                                       "--sprint", self.KEYS["sprint"],
                                       "--story", self.KEYS["story"]])
            self.assertEqual(code, 0, out)
        return before, datetime.now(timezone.utc)

    def _transcript(self, name, records):
        """Write <name>.jsonl holding one assistant record per (session_id, datetime)."""
        lines = [json.dumps({
            "sessionId": sid, "timestamp": when.isoformat(), "type": "assistant",
            "message": {"id": f"msg-{name}-{i}",
                        "usage": {"input_tokens": 10, "output_tokens": 5,
                                  "cache_creation_input_tokens": 0,
                                  "cache_read_input_tokens": 0}}})
            for i, (sid, when) in enumerate(records)]
        p = os.path.join(self.projects, f"{name}.jsonl")
        Path(p).write_text("\n".join(lines) + "\n", encoding="utf-8")
        return p

    def _discover(self, state_root=None):
        with mock.patch.dict(os.environ, {"HOME": self.home}):
            return pm.discover_session_transcript(state_root or self.root, dict(self.KEYS))

    def test_single_spanning_candidate_is_accepted(self):
        lo, hi = self._bracket()
        self._transcript("sess-a", [("sess-a", lo - SECOND), ("sess-a", hi + SECOND)])
        paths, sid, why = self._discover()
        self.assertEqual(why, "")
        self.assertEqual(sid, "sess-a")
        self.assertEqual(len(paths), 1)

    def test_two_spanning_candidates_are_refused(self):
        lo, hi = self._bracket()
        self._transcript("sess-a", [("sess-a", lo - SECOND), ("sess-a", hi + SECOND)])
        self._transcript("sess-b", [("sess-b", lo - SECOND), ("sess-b", hi + SECOND)])
        paths, sid, why = self._discover()
        self.assertEqual(paths, [])
        self.assertEqual(sid, "")
        self.assertIn("refusing to choose", why)

    def test_no_spanning_candidate_is_refused(self):
        lo, _hi = self._bracket()
        self._transcript("sess-a", [("sess-a", lo - SECOND), ("sess-a", lo - SECOND)])
        paths, _sid, why = self._discover()
        self.assertEqual(paths, [])
        self.assertIn("no transcript spans", why)

    def test_file_with_two_session_ids_is_never_a_candidate(self):
        """A file holding two sessions is malformed whatever we were expecting, so it is
        rejected before its span is even considered."""
        lo, hi = self._bracket()
        self._transcript("mixed", [("sess-a", lo - SECOND), ("sess-b", hi + SECOND)])
        paths, _sid, why = self._discover()
        self.assertEqual(paths, [])
        self.assertIn("no transcript spans", why)

    def test_absent_dispatch_bracket_refuses_with_a_reason(self):
        empty = os.path.join(self.d, "empty-state")
        os.makedirs(empty)
        paths, sid, why = self._discover(state_root=empty)
        self.assertEqual(paths, [])
        self.assertEqual(sid, "")
        self.assertIn("no dispatch_open", why)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run skills/_shared/tests/test-pm-status.py TestTranscriptFallback -v 2>&1 | tail -20`
Expected: FAIL, `AttributeError: ... has no attribute 'discover_session_transcript'`

- [ ] **Step 3: Implement `_transcript_span()`**

Insert after `transcript_sessions()` (ends line 5578):

```python
def _transcript_span(path: str) -> tuple:
    """(earliest, latest) aware datetimes in a transcript, or (None, None).

    Read as a pair rather than per-record because the caller asks one question of the whole
    file -- does it cover this node's bracket -- and a partial answer is not useful.
    """
    lo = hi = None
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                when = _parse_iso(rec.get("timestamp")) if isinstance(rec, dict) else None
                if when is None:
                    continue
                lo = when if lo is None or when < lo else lo
                hi = when if hi is None or when > hi else hi
    except OSError:
        return None, None
    return lo, hi
```

- [ ] **Step 4: Implement `discover_session_transcript()`**

Insert immediately after `_transcript_span()`:

```python
def discover_session_transcript(state_root: str, node_keys: dict) -> tuple:
    """(paths, session_id, refusal) for a session the environment cannot name.

    resolve_session_transcript() answers from CLAUDE_CODE_SESSION_ID and returns nothing
    without it, so a Claude run in a context that does not export the variable -- a hook, a
    wrapper that scrubs the environment -- reports N/A while the data sits on disk.

    Recovery is by ELIMINATION, never by preference. Every project directory is scanned
    rather than the one a slugified cwd would name, for the reason
    resolve_session_transcript already gives: a subagent may run under a different working
    directory, and guessing the slug reintroduces the ambiguity. A candidate is accepted
    only when its own records carry exactly one sessionId AND its timestamps span the node's
    dispatch bracket.

    Two survivors is a REFUSAL, not a tie-break. Picking the likelier file is precisely the
    failure this command exists to prevent: the original bad number came from file choice,
    not arithmetic, and it looked plausible because the cache figures matched.
    """
    open_ts, close_ts = dispatch_window(state_root, **node_keys)
    if open_ts is None or close_ts is None:
        return [], "", ("this node has no dispatch_open/dispatch_close pair, so there is no "
                        "window to verify a transcript against")
    root = os.path.expanduser("~/.claude/projects")
    if not os.path.isdir(root):
        return [], "", f"{root} does not exist"
    hits = []
    for d in sorted(os.listdir(root)):
        sub = os.path.join(root, d)
        if not os.path.isdir(sub):
            continue
        for name in sorted(os.listdir(sub)):
            if not name.endswith(".jsonl"):
                continue
            fp = os.path.join(sub, name)
            try:
                # Cheap rejection first: a file last written before the bracket opened cannot
                # span it. Without this the fallback parses every transcript on the machine
                # on every call, and they reach tens of megabytes.
                if datetime.fromtimestamp(os.path.getmtime(fp), tz=timezone.utc) < open_ts:
                    continue
            except OSError:
                continue
            found = transcript_sessions(fp)
            if len(found) != 1:
                continue
            lo, hi = _transcript_span(fp)
            if lo is None or lo > open_ts or hi < close_ts:
                continue
            hits.append((fp, found.pop()))
    if len(hits) != 1:
        return [], "", (f"{len(hits)} transcripts span this node's window; refusing to "
                        f"choose between them" if hits
                        else "no transcript spans this node's window")
    fp, sid = hits[0]
    # Re-resolve from the recovered id so the session's subagent files come too; fall back
    # to the single file if that lookup finds nothing.
    paths, _ = resolve_session_transcript(sid)
    return (paths or [fp]), sid, ""
```

- [ ] **Step 5: Confirm `datetime`/`timezone` are imported**

Run: `grep -nE '^from datetime import|^import datetime' skills/_shared/pm-status.py | head -3`
Expected: a line importing `datetime` and `timezone`. If `timezone` is absent, add it to the existing `from datetime import ...` line rather than adding a second import.

- [ ] **Step 6: Wire the fallback into `cmd_usage()`**

Replace the refusal block (currently 5752–5762):

```python
        if not paths:
            sys.stderr.write(
                "pm-status.py: cannot resolve this session's transcript — "
                + (f"no ~/.claude/projects/*/{want}.jsonl found\n" if want else
                   f"{CLAUDE_SESSION_ENV} is not set\n")
                + "  Pass the transcript path explicitly, or --claude-session ID. Refusing to\n"
                  "  guess: summing the wrong file is the error this command exists to prevent.\n")
            return 2
```

with:

```python
        if not paths:
            keys = {k: getattr(args, k, "") or ""
                    for k in ("agent", "epic", "sprint", "story")}
            why = "no --state-root and node key to derive a window from"
            if args.state_root and any(keys.values()):
                paths, want, why = discover_session_transcript(args.state_root, keys)
            if not paths:
                sys.stderr.write(
                    "pm-status.py: cannot resolve this session's transcript — "
                    + (f"no ~/.claude/projects/*/{want}.jsonl found\n" if want else
                       f"{CLAUDE_SESSION_ENV} is not set\n")
                    + f"  Recovery by elimination also failed: {why}.\n"
                    + "  Pass the transcript path explicitly, or --claude-session ID. Refusing to\n"
                      "  guess: summing the wrong file is the error this command exists to prevent.\n")
                return 2
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run skills/_shared/tests/test-pm-status.py TestTranscriptFallback -v 2>&1 | tail -20`
Expected: PASS

- [ ] **Step 8: Run the whole pm-status suite**

Run: `uv run skills/_shared/tests/test-pm-status.py 2>&1 | tail -20`
Expected: PASS. This suite is large; capture to a file rather than piping to grep if you need to inspect failures.

- [ ] **Step 9: Confirm the two-candidate refusal is real (Review Focus 4)**

The `test_two_spanning_candidates_are_refused` case written in Step 1 must assert on the returned reason, not merely on an empty path list:

```python
        paths, sid, why = ...
        self.assertEqual(paths, [])
        self.assertEqual(sid, "")
        self.assertIn("refusing to choose", why)
```

Then mutate the implementation to prove the test bites: change `if len(hits) != 1:` to `if not hits:` and add `hits = hits[:1]` above it. Re-run; the test must FAIL. Revert the mutation.

- [ ] **Step 10: Run the mutation check for the span guard**

Mutate `if lo is None or lo > open_ts or hi < close_ts:` to `if lo is None:` and re-run `TestTranscriptFallback`. `test_no_spanning_candidate_is_refused` must FAIL. Revert.

- [ ] **Step 11: Add the mtime-prefilter test (Review Focus 5)**

Append to `class TestTranscriptFallback`:

```python
    def test_a_stale_mtime_is_rejected_before_the_file_is_parsed(self):
        """Without the mtime rejection the fallback parses every transcript on the machine on
        every call, and real ones reach tens of megabytes.

        Asserted through behaviour rather than through a read counter: this file WOULD span
        the window if it were parsed, so a missing prefilter surfaces as a two-candidate
        refusal instead of a clean accept.
        """
        lo, hi = self._bracket()
        self._transcript("sess-a", [("sess-a", lo - SECOND), ("sess-a", hi + SECOND)])
        stale = self._transcript("sess-old",
                                 [("sess-old", lo - SECOND), ("sess-old", hi + SECOND)])
        old = (lo - timedelta(days=2)).timestamp()
        os.utime(stale, (old, old))
        paths, sid, why = self._discover()
        self.assertEqual(why, "")
        self.assertEqual(sid, "sess-a")
        self.assertEqual(len(paths), 1)
```

Run: `uv run skills/_shared/tests/test-pm-status.py TestTranscriptFallback -v 2>&1 | tail -20`
Expected: PASS. Then delete the `os.path.getmtime` guard from the implementation and re-run — this test must FAIL with `refusing to choose`. Restore it.

- [ ] **Step 12: Sync the shared script and commit**

```bash
npm run sync:scripts
npm run check:scripts 2>&1 | tail -5
node scripts/write-payload-manifest.mjs
git add skills/_shared/pm-status.py skills/_shared/tests/test-pm-status.py skills/*/scripts/pm-status.py skills/*/payload-manifest.json
git commit -s -m "feat(l3io-pm): recover a session transcript by elimination when the env is silent

resolve_session_transcript answers from CLAUDE_CODE_SESSION_ID and
returns nothing without it, so a Claude run in a hook, or under a
wrapper that scrubs the environment, reported N/A while the usage data
sat on disk the whole time.

The fallback accepts a candidate only when its own records carry exactly
one sessionId and its timestamps span the node's dispatch bracket. Two
survivors is a refusal, not a tie-break: the original bad number came
from file choice rather than arithmetic, and it looked plausible.

Stale files are rejected by mtime before being parsed, since real
transcripts reach tens of megabytes.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: Report the models a dispatch actually used

**Files:**
- Modify: `skills/_shared/pm-status.py` — add `subagent_models()` after `discover_session_transcript()`; extend `cmd_usage()`'s report
- Test: `skills/_shared/tests/test-pm-status.py`

**Interfaces:**
- Consumes: `resolve_session_transcript()`.
- Produces: `subagent_models(session_id) -> dict[str, str]` — `{agent_file_stem: model}` from the `.meta.json` sidecars.

**Scope note.** This reports the models observed and warns when there is more than one. It does **not** re-price per model — that changes the cost derivation, which is frozen-at-capture, and belongs with the 4.0.0 metrics work. The deliverable here is that an operator can see a single `--model` is about to price a mixed run at one rate.

- [ ] **Step 1: Write the failing test**

```python
class TestSubagentModels(Base):
    """subagents/agent-*.meta.json carries `model` beside agentType, description, toolUseId
    and spawnDepth. It carries no sessionId, so it is an attribution input only -- never
    identity proof, which stays with transcript_sessions()."""

    def setUp(self):
        super().setUp()
        self.home = os.path.join(self.d, "home")
        self.projects = os.path.join(self.home, ".claude", "projects", "-fake")
        os.makedirs(self.projects)

    def _sub(self, session_id, agents):
        """agents: {stem: meta dict, raw text, or None for a .jsonl with no sidecar}."""
        d = os.path.join(self.projects, session_id, "subagents")
        os.makedirs(d, exist_ok=True)
        for stem, meta in agents.items():
            Path(d, f"{stem}.jsonl").write_text("{}\n", encoding="utf-8")
            if meta is None:
                continue
            text = meta if isinstance(meta, str) else json.dumps(meta)
            Path(d, f"{stem}.meta.json").write_text(text, encoding="utf-8")

    def _models(self, sid):
        with mock.patch.dict(os.environ, {"HOME": self.home}):
            return pm.subagent_models(sid)

    def test_models_are_read_from_meta_sidecars(self):
        self._sub("sess-a", {
            "agent-aaa": {"agentType": "general-purpose", "description": "re-review",
                          "toolUseId": "toolu_1", "spawnDepth": 1, "model": "sonnet"},
            "agent-bbb": {"agentType": "general-purpose", "description": "verify",
                          "toolUseId": "toolu_2", "spawnDepth": 1, "model": "opus"}})
        self.assertEqual(self._models("sess-a"),
                         {"agent-aaa": "sonnet", "agent-bbb": "opus"})

    def test_missing_meta_is_not_an_error(self):
        """A .jsonl with no sidecar contributes nothing and does not fail the read."""
        self._sub("sess-a", {"agent-aaa": None})
        self.assertEqual(self._models("sess-a"), {})

    def test_unparseable_meta_is_skipped(self):
        self._sub("sess-a", {"agent-aaa": {"model": "sonnet"}, "agent-bad": "{not json"})
        self.assertEqual(self._models("sess-a"), {"agent-aaa": "sonnet"})

    def test_meta_without_a_model_key_contributes_nothing(self):
        self._sub("sess-a", {"agent-aaa": {"agentType": "general-purpose"}})
        self.assertEqual(self._models("sess-a"), {})

    def test_empty_session_id_returns_empty(self):
        self.assertEqual(self._models(""), {})
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run skills/_shared/tests/test-pm-status.py TestSubagentModels -v 2>&1 | tail -20`
Expected: FAIL, `AttributeError: ... has no attribute 'subagent_models'`

- [ ] **Step 3: Implement `subagent_models()`**

```python
def subagent_models(session_id: str) -> dict:
    """{agent file stem: model} from the subagents/*.meta.json sidecars.

    Cost is priced per model and a dispatched agent may run on a different model than the
    session that spawned it, so a single --model prices a mixed run at one rate. The sidecar
    records which model each agent actually used.

    It carries no sessionId and no parent link, so it is an ATTRIBUTION input only -- never
    evidence of whose transcript this is. Identity stays with transcript_sessions().
    """
    out = {}
    if not session_id:
        return out
    root = os.path.expanduser("~/.claude/projects")
    if not os.path.isdir(root):
        return out
    for d in sorted(os.listdir(root)):
        sub = os.path.join(root, d, session_id, "subagents")
        if not os.path.isdir(sub):
            continue
        for name in sorted(os.listdir(sub)):
            if not name.endswith(".meta.json"):
                continue
            try:
                with open(os.path.join(sub, name), "r", encoding="utf-8") as fh:
                    meta = json.load(fh)
            except (OSError, ValueError):
                continue
            model = meta.get("model") if isinstance(meta, dict) else None
            if isinstance(model, str) and model:
                out[name[:-len(".meta.json")]] = model
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run skills/_shared/tests/test-pm-status.py TestSubagentModels -v 2>&1 | tail -20`
Expected: PASS

- [ ] **Step 5: Report the models in `cmd_usage()`**

After the token totals are printed and before the `--tokens-*` flag line, add:

```python
    models = subagent_models(want)
    distinct = sorted(set(models.values()))
    if distinct:
        sys.stderr.write(f"  models observed in dispatched agents: {', '.join(distinct)}\n")
    if len(distinct) > 1 or (distinct and args.model and args.model not in distinct):
        sys.stderr.write("  NOTE: more than one model contributed to this window, or the\n"
                         "  --model given is not among them. The cost below prices every\n"
                         "  class at one rate; treat it as approximate.\n")
```

- [ ] **Step 6: Write the mixed-model warning test**

Append to `class TestSubagentModels`. It drives `usage` with an explicit transcript and
`--claude-session`, so it exercises the report without depending on Task 4's fallback:

```python
    def _usage_stderr(self, argv):
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"HOME": self.home}), redirect_stderr(buf):
            self.run_main(argv)
        return buf.getvalue()

    def _one_record_transcript(self, sid):
        p = os.path.join(self.d, f"{sid}.jsonl")
        Path(p).write_text(json.dumps({
            "sessionId": sid, "timestamp": "2026-10-21T10:00:00+00:00", "type": "assistant",
            "message": {"id": "m1", "usage": {"input_tokens": 10, "output_tokens": 5,
                                              "cache_creation_input_tokens": 0,
                                              "cache_read_input_tokens": 0}}}) + "\n",
            encoding="utf-8")
        return p

    def test_mixed_models_warn_that_cost_is_approximate(self):
        """One --model prices every class at one rate. When the window holds more than one
        model that is approximate, and nothing said so before."""
        self._sub("sess-a", {"agent-aaa": {"model": "sonnet"},
                             "agent-bbb": {"model": "opus"}})
        err = self._usage_stderr(["usage", "--transcript", self._one_record_transcript("sess-a"),
                                  "--claude-session", "sess-a", "--model", "sonnet"])
        self.assertIn("models observed", err)
        self.assertIn("approximate", err)

    def test_a_single_model_matching_the_flag_does_not_warn(self):
        self._sub("sess-a", {"agent-aaa": {"model": "sonnet"}})
        err = self._usage_stderr(["usage", "--transcript", self._one_record_transcript("sess-a"),
                                  "--claude-session", "sess-a", "--model", "sonnet"])
        self.assertIn("models observed", err)
        self.assertNotIn("approximate", err)
```

- [ ] **Step 7: Run the whole suite, sync, commit**

```bash
uv run skills/_shared/tests/test-pm-status.py > /tmp/pm-status-suite.log 2>&1; tail -20 /tmp/pm-status-suite.log
npm run sync:scripts && npm run check:scripts 2>&1 | tail -5
node scripts/write-payload-manifest.mjs
git add skills/_shared/pm-status.py skills/_shared/tests/test-pm-status.py skills/*/scripts/pm-status.py skills/*/payload-manifest.json
git commit -s -m "feat(l3io-pm): report the models a dispatch used, and warn on a mixed window

Cost is priced per model, and a dispatched agent may run on a different
model than the session that spawned it, so one --model prices a mixed
run at a single rate with nothing saying so.

The subagents/*.meta.json sidecars record each agent's model. They carry
no sessionId, so they are an attribution input only and identity stays
with transcript_sessions(). Re-pricing per model is deliberately not
done here: the cost derivation is frozen at capture.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 6: Documentation and the corrections this plan uncovered

**Files:**
- Modify: `docs/upgrading.md` — new section
- Modify: `CLAUDE.md:92` — the suite-discovery glob claim
- Modify: `docs/superpowers/specs/2026-10-16-bmad-v7-layer-design.md` — §8's test-suite bullet

- [ ] **Step 1: Correct the suite-discovery claim in `CLAUDE.md`**

Line 92 reads `globs `skills/**/tests/test-*.py``. That pattern matches nothing the runner uses. Replace that clause with:

```markdown
(`scripts/run-python-suites.mjs`) globs `skills/_shared/tests/test-*.py` and
`tests/**/test-*.py` — shared suites in the first, per-skill suites in the second, which is
where they live precisely so they do not ship as payload when a `--custom-source` install
copies a skill directory — and runs each under `uv
```

- [ ] **Step 2: Correct the spec's test-suite claim**

In `docs/superpowers/specs/2026-10-16-bmad-v7-layer-design.md` §8, the bullet beginning **"A test suite for `bmad-deps.py`, which has none today."** is wrong. Replace the whole bullet with:

```markdown
- **Extend `tests/l3io-doctor/test-bmad-deps.py`**, which already exists and carries 42 cases
  across presence, layouts, unreadable inputs, inventory shape, JSON, fallbacks, shims,
  contradictions and baseline drift. An earlier draft of this spec said the script had no
  suite; that was a search error — the suite lives under the repo-root `tests/` tree, not
  under `skills/`, which is the convention precisely so it does not ship as payload.
  `test_absent_manifest_exits_4` is the case v7 detection changes, and it must keep passing:
  a tree with no v7 evidence still exits 4.
```

- [ ] **Step 3: Add the `bmad migrate` hazard to `docs/upgrading.md`**

Append a section:

```markdown
## BMad v7: do not run `bmad migrate` on an l3io-pm project yet

BMad v7 ships a migration that turns a v6 project into its initiative/ticket layout. Its
detector fires on two things an l3io-pm project can present:

- `sprint-status.yaml` under `implementation_artifacts` — the legacy flat layout
- story files named `<epic>-<story>-<slug>.md` whose frontmatter carries `route:` and
  `status:` — which `pm-status.py sync-story-doc` writes

When it matches, it `git mv`s whole folders into `_bmad-output/initiative-<slug>/`. It takes a
full backup first and will not write anything before you approve its plan, so this is not
destructive by surprise — but two migrations competing over one tree is a mess, and ours has
to run in a known order relative to theirs.

**Until this package ships v7 support, stay on BMad 6.12.** Run `/l3io-doctor check-deps` to
see which generation is installed; exit 6 means v7 was detected and verification is degraded.
```

- [ ] **Step 4: Run the full gate set**

```bash
npm run check:docs 2>&1 | tail -20
npm run check:manifest 2>&1 | tail -5
npm run check:scripts 2>&1 | tail -5
npm run test:python > /tmp/python-suites.log 2>&1; tail -20 /tmp/python-suites.log
```
Expected: all clean. `test:python` takes several minutes — a killed run looks exactly like a failing one, so let it finish.

- [ ] **Step 5: Commit**

```bash
git add docs/upgrading.md CLAUDE.md docs/superpowers/specs/2026-10-16-bmad-v7-layer-design.md
git commit -s -m "docs: warn about bmad migrate on l3io projects, fix two stale claims

Adds the v7 migration hazard to upgrading.md: their detector fires on
sprint-status.yaml and on the route:/status: frontmatter sync-story-doc
writes, and then git mvs whole folders into an initiative.

Corrects two claims this work falsified. CLAUDE.md said the suite runner
globs skills/**/tests/test-*.py, which matches nothing it uses -- the
real patterns are skills/_shared/tests/ and the repo-root tests/ tree,
where per-skill suites live so they do not ship as payload. The v7 spec
said bmad-deps.py has no test suite; it has 42 cases, and the claim came
from searching only under skills/.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Done when

- `/l3io-doctor check-deps` on a v7 tree reports the generation, runs skill probes, names what it could not check, and exits 6 — never "BMad is not installed here".
- The same command on a v6 tree behaves exactly as it does today, including every exit code.
- `pm-status.py usage` recovers a transcript without `CLAUDE_CODE_SESSION_ID`, and refuses rather than guesses when the evidence is ambiguous.
- `npm run check:docs`, `check:manifest`, `check:scripts` and `test:python` are all clean.
