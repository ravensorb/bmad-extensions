# Calibration Mechanization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the specified estimation-calibration model actually run — samples derived automatically from data already on disk, estimates computed by code rather than by hand.

**Architecture:** All of it lands in `skills/_shared/pm-status.py`, which already owns atomic state writes and self-installs one runtime copy per project. `set-actual` gains automatic sample derivation; three new subcommands (`estimate-story`, `estimate-rollup`, `calibration show`) move estimate arithmetic out of step-file prose. The calibration file is a shared append target, so every write takes flock.

**Tech Stack:** Python 3.11+, `ruamel.yaml>=0.18` (round-trip), `unittest`, `fcntl` flock.

**Spec:** `docs/superpowers/specs/2026-08-16-calibration-mechanization-design.md`

## Global Constraints

- **Never edit per-skill copies.** Author in `skills/_shared/`, then `npm run sync:scripts`. CI runs `npm run check:scripts`.
- **Run tests with:** `python3 skills/_shared/tests/test-pm-status.py` — currently **177 passing**.
- **Exit codes are contractual:** 0 success, 2 usage error, 3 node not found, 4 verification failure, 5 epic locked. Do not add new codes.
- **Metric field names are fixed.** Actuals: `elapsed_hours`, `man_hours`, `tokens_k`, `cost`. Story estimates: `man_hours`, `time_hours`, `tokens_k`, `cost`. Sprint/epic estimates: `man_hours_low/high`, `time_hours_low/high`, `tokens_k_min/max`, `cost_low/high`.
- **The estimate↔actual pairing is NOT identity:** `time_hours` ↔ `elapsed_hours`. The other three match.
- **`N/A` is never guessed.** `_is_na()` already exists; token/cost samples are skipped for `N/A`, never coerced to 0.
- **`--runtime claude` forbids `N/A`** for `tokens_k`/`cost` at write time. Preserve this.
- **Zero-padding:** epic dirs `epic-{nnn}` (3 digits), sprint dirs `sprint-{nn}` (2 digits).
- **Terminology:** layout generations are "sharded", "legacy per-epic", "legacy flat". Never v1/v2/v3 for layouts. `version: 1`/`version: 2` for the *calibration file schema* is a different thing and stays.
- **Commits:** Conventional Commits, DCO sign-off (`git commit -s`). No `!`, no `BREAKING CHANGE:` footer.
- **No external organization references** anywhere.

---

## File Structure

| File | Responsibility after this plan |
|---|---|
| `skills/_shared/pm-status.py` | Adds a bounded calibration section: file I/O, sample derivation, estimate computation, three subcommands. Version → 2.1.0. |
| `skills/_shared/tests/test-pm-status.py` | One test class per new surface. |
| `skills/_shared/metrics-contract.md` | §6 bands cite code; §8 rewritten; §9 loses closed entries. |
| `skills/_shared/steps/shared/step-estimate.md` | Prose arithmetic replaced by subcommand calls. |
| `skills/_shared/steps/sprint/step-04-sprint-closure.md`, `steps/execute/step-06-epic-closure.md` | Drop the manual sample-append instructions. |
| `skills/_shared/status-files.md` | Document the new subcommands. |
| `CLAUDE.md` | Calibration paragraph now describes something that runs. |

---

## Task 1: Calibration file I/O and `calibration show`

**Files:**
- Modify: `skills/_shared/pm-status.py` (new section after the layout-resolution block, before `cmd_set_status`)
- Test: `skills/_shared/tests/test-pm-status.py`

**Interfaces:**
- Consumes: existing `_yaml()`, `_load()`, `_atomic_dump()`, `_flock_write_or_plain()`, `_is_na()`, `_die_usage()`
- Produces:
  - `CALIBRATION_SCHEMA_VERSION = 2`, `MIN_SAMPLES = 3`, `DECAY = 0.8`, `COLD_START_SCOPE_RATIO = 1.0`, `COLD_START_FIX_FACTOR = 1.25`, `CLASSIFICATIONS = ("simple","standard","complex")`
  - `calibration_path(state_root) -> str`
  - `new_calibration(granularity="story") -> CommentedMap`
  - `load_calibration(state_root) -> tuple[YAML, CommentedMap]` — returns a fresh skeleton when absent, never raises
  - `save_calibration(y, cal, state_root) -> None` — **always flock**
  - `migrate_calibration(y, cal, state_root) -> CommentedMap`
  - `weighted_ratio(samples: list[float]) -> float` — exponential decay 0.8, oldest first
  - `active_scope_ratio(cal, classification, metric) -> float | None`
  - `active_closure_ratio(cal, level, metric) -> float | None`
  - `active_fix_factor(cal, classification) -> float | None`
  - `cmd_calibration(args) -> int` for `calibration show`

- [ ] **Step 1: Write the failing tests**

Append to `skills/_shared/tests/test-pm-status.py`:

```python
class TestCalibrationIO(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.root = os.path.join(self.d, "state")
        os.makedirs(self.root)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.d, ignore_errors=True)

    def test_missing_file_yields_skeleton_not_error(self):
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(cal["version"], 2)
        self.assertEqual(cal["granularity"], "story")
        self.assertIn("scope", cal)
        self.assertIn("closure", cal)
        self.assertIn("fix", cal)

    def test_granularity_persists_in_file_not_a_binding(self):
        y, cal = pm.load_calibration(self.root)
        cal["granularity"] = "sprint"
        pm.save_calibration(y, cal, self.root)
        _, again = pm.load_calibration(self.root)
        self.assertEqual(again["granularity"], "sprint")

    def test_weighted_ratio_favours_recent_samples(self):
        # oldest first; decay 0.8 means later samples dominate
        older_heavy = pm.weighted_ratio([2.0, 1.0])
        newer_heavy = pm.weighted_ratio([1.0, 2.0])
        self.assertLess(older_heavy, newer_heavy)

    def test_weighted_ratio_single_sample_is_that_sample(self):
        self.assertAlmostEqual(pm.weighted_ratio([1.4]), 1.4)

    def test_component_below_threshold_is_not_active(self):
        y, cal = pm.load_calibration(self.root)
        cal["scope"]["complex"] = {"man_hours": {"samples": [1.2, 1.3]}}
        pm.save_calibration(y, cal, self.root)
        _, cal2 = pm.load_calibration(self.root)
        self.assertIsNone(pm.active_scope_ratio(cal2, "complex", "man_hours"))

    def test_component_at_threshold_is_active(self):
        y, cal = pm.load_calibration(self.root)
        cal["scope"]["complex"] = {"man_hours": {"samples": [1.2, 1.3, 1.4]}}
        pm.save_calibration(y, cal, self.root)
        _, cal2 = pm.load_calibration(self.root)
        self.assertIsNotNone(pm.active_scope_ratio(cal2, "complex", "man_hours"))

    def test_fix_needs_both_cohorts_at_threshold(self):
        y, cal = pm.load_calibration(self.root)
        cal["fix"]["complex"] = {
            "clean": {"mean_man_hours": 7.0, "samples": 5},
            "reworked": {"mean_man_hours": 9.0, "samples": 0},
        }
        pm.save_calibration(y, cal, self.root)
        _, cal2 = pm.load_calibration(self.root)
        self.assertIsNone(pm.active_fix_factor(cal2, "complex"))

    def test_fix_active_when_both_cohorts_reach_threshold(self):
        y, cal = pm.load_calibration(self.root)
        cal["fix"]["complex"] = {
            "clean": {"mean_man_hours": 8.0, "samples": 3},
            "reworked": {"mean_man_hours": 10.0, "samples": 3},
        }
        pm.save_calibration(y, cal, self.root)
        _, cal2 = pm.load_calibration(self.root)
        self.assertAlmostEqual(pm.active_fix_factor(cal2, "complex"), 1.25)

    def test_v1_file_migrates_and_preserves_original(self):
        p = pm.calibration_path(self.root)
        with open(p, "w") as f:
            f.write("version: 1\nratio: 1.3\n")
        y, cal = pm.load_calibration(self.root)
        cal = pm.migrate_calibration(y, cal, self.root)
        self.assertEqual(cal["version"], 2)
        self.assertTrue(os.path.exists(p + ".v1"))
        # closure and fix start fresh, never seeded from the blended ratio.
        # Assert emptiness per bucket rather than comparing a CommentedMap to a
        # plain dict, which is fragile across ruamel versions.
        for level in ("sprint", "epic"):
            self.assertEqual(len(cal["closure"][level]), 0)
        for c in ("simple", "standard", "complex"):
            self.assertEqual(len(cal["fix"][c]), 0)
        # the blended v1 ratio landed on scope, and only on scope
        self.assertGreater(len(cal["scope"]["complex"]), 0)

    def test_show_on_missing_file_exits_0(self):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(["calibration", "show", "--state-root", self.root])
        except SystemExit as e:
            code = e.code
        self.assertEqual(code, 0)
        self.assertIn("cold-start", buf.getvalue().lower())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 skills/_shared/tests/test-pm-status.py TestCalibrationIO -v`
Expected: FAIL with `AttributeError: module 'pm_status' has no attribute 'load_calibration'`

- [ ] **Step 3: Implement the calibration I/O layer**

Insert into `skills/_shared/pm-status.py` after the layout-resolution block (after `_sprint_key_from_dir`), before the subcommand section:

```python
# --------------------------------------------------------------------------- #
# Calibration — the learning loop. See references/metrics-contract.md §8.
# The file is a SHARED append target: every set-actual across parallel
# subagents may write it, so every write takes flock. Unlike node files,
# which are sharded per story precisely to avoid this.
# --------------------------------------------------------------------------- #
CALIBRATION_SCHEMA_VERSION = 2
MIN_SAMPLES = 3          # a component below this is recorded but not applied
DECAY = 0.8              # exponential decay, applied oldest-first
COLD_START_SCOPE_RATIO = 1.0
COLD_START_FIX_FACTOR = 1.25
CLASSIFICATIONS = ("simple", "standard", "complex")
CLOSURE_LEVELS = ("sprint", "epic")


def calibration_path(state_root: str) -> str:
    return os.path.join(state_root, "pm-calibration.yaml")


def new_calibration(granularity: str = "story"):
    from ruamel.yaml.comments import CommentedMap
    cal = CommentedMap()
    cal["version"] = CALIBRATION_SCHEMA_VERSION
    cal["granularity"] = granularity
    cal["scope"] = CommentedMap((c, CommentedMap()) for c in CLASSIFICATIONS)
    cal["closure"] = CommentedMap((lv, CommentedMap()) for lv in CLOSURE_LEVELS)
    cal["fix"] = CommentedMap((c, CommentedMap()) for c in CLASSIFICATIONS)
    return cal


def load_calibration(state_root: str):
    """Load the calibration file, or a fresh skeleton if absent. Never raises."""
    p = calibration_path(state_root)
    y, data = _load(p)
    if data is None:
        return _yaml(), new_calibration()
    for key, default in (("scope", CLASSIFICATIONS), ("fix", CLASSIFICATIONS),
                         ("closure", CLOSURE_LEVELS)):
        if key not in data or data[key] is None:
            from ruamel.yaml.comments import CommentedMap
            data[key] = CommentedMap((k, CommentedMap()) for k in default)
    if "granularity" not in data:
        data["granularity"] = "story"
    return y, data


def save_calibration(y, cal, state_root: str) -> None:
    """Always flock — this file is written from every set-actual."""
    _flock_write_or_plain(True, y, cal, calibration_path(state_root))


def migrate_calibration(y, cal, state_root: str):
    """version 1 -> 2. Original preserved as .v1 and never read again."""
    if cal.get("version") == CALIBRATION_SCHEMA_VERSION:
        return cal
    p = calibration_path(state_root)
    backup = p + ".v1"
    if os.path.exists(p) and not os.path.exists(backup):
        import shutil
        shutil.copy2(p, backup)
    blended = cal.get("ratio")
    fresh = new_calibration(cal.get("granularity", "story"))
    # The old blended figure maps onto scope only. closure and fix start at
    # zero samples: the v1 file cannot separate them, and seeding from a
    # blended number would import exactly the bias the split removes.
    if isinstance(blended, (int, float)):
        from ruamel.yaml.comments import CommentedMap
        for c in CLASSIFICATIONS:
            entry = CommentedMap()
            entry["samples"] = [float(blended)]
            fresh["scope"][c] = CommentedMap((("man_hours", entry),))
    save_calibration(y, fresh, state_root)
    return fresh


def weighted_ratio(samples: list) -> float:
    """Exponential-decay weighted mean, oldest first (most recent weighs most)."""
    vals = [float(s) for s in samples if _is_number(s)]
    if not vals:
        return None
    n = len(vals)
    num = den = 0.0
    for i, v in enumerate(vals):
        w = DECAY ** (n - 1 - i)
        num += v * w
        den += w
    return num / den if den else None


def _component_samples(cal, component: str, bucket: str, metric: str) -> list:
    node = ((cal.get(component) or {}).get(bucket) or {}).get(metric) or {}
    return list(node.get("samples") or [])


def active_scope_ratio(cal, classification: str, metric: str):
    s = _component_samples(cal, "scope", classification, metric)
    return weighted_ratio(s) if len(s) >= MIN_SAMPLES else None


def active_closure_ratio(cal, level: str, metric: str):
    s = _component_samples(cal, "closure", level, metric)
    return weighted_ratio(s) if len(s) >= MIN_SAMPLES else None


def active_fix_factor(cal, classification: str):
    """Needs BOTH cohorts at threshold — one cohort alone cannot form a ratio."""
    entry = (cal.get("fix") or {}).get(classification) or {}
    clean, rework = entry.get("clean") or {}, entry.get("reworked") or {}
    if int(clean.get("samples", 0)) < MIN_SAMPLES or int(rework.get("samples", 0)) < MIN_SAMPLES:
        return None
    cm, rm = clean.get("mean_man_hours"), rework.get("mean_man_hours")
    if not _is_number(cm) or not _is_number(rm) or float(cm) == 0:
        return None
    return float(rm) / float(cm)


def cmd_calibration(args) -> int:
    _, cal = load_calibration(args.state_root)
    exists = os.path.exists(calibration_path(args.state_root))
    rows = []
    for c in CLASSIFICATIONS:
        for m in ("man_hours", "time_hours", "tokens_k", "cost"):
            n = len(_component_samples(cal, "scope", c, m))
            r = active_scope_ratio(cal, c, m)
            rows.append(("scope", f"{c}/{m}", n, r))
    for lv in CLOSURE_LEVELS:
        for m in ("man_hours", "time_hours", "tokens_k", "cost"):
            n = len(_component_samples(cal, "closure", lv, m))
            r = active_closure_ratio(cal, lv, m)
            rows.append(("closure", f"{lv}/{m}", n, r))
    for c in CLASSIFICATIONS:
        entry = (cal.get("fix") or {}).get(c) or {}
        n = min(int((entry.get("clean") or {}).get("samples", 0)),
                int((entry.get("reworked") or {}).get("samples", 0)))
        rows.append(("fix", c, n, active_fix_factor(cal, c)))

    if getattr(args, "format", "text") == "json":
        import json
        sys.stdout.write(json.dumps({
            "exists": exists,
            "granularity": cal.get("granularity", "story"),
            "components": [{"component": a, "bucket": b, "samples": n,
                            "active_ratio": r} for a, b, n, r in rows],
        }, indent=2) + "\n")
        return 0

    if not exists:
        sys.stdout.write("No calibration file yet — all components cold-start.\n")
    sys.stdout.write(f"granularity: {cal.get('granularity', 'story')}\n")
    sys.stdout.write(f"{'COMPONENT':<10} {'BUCKET':<22} {'SAMPLES':>7}  RATIO\n")
    for a, b, n, r in rows:
        shown = f"{r:.3f}" if r is not None else f"(cold-start, needs {MIN_SAMPLES})"
        sys.stdout.write(f"{a:<10} {b:<22} {n:>7}  {shown}\n")
    return 0
```

Register in `build_parser`:

```python
    cal = sub.add_parser("calibration", help="inspect the calibration file")
    cal.add_argument("action", choices=["show"])
    cal.add_argument("--state-root", required=True)
    cal.add_argument("--format", choices=["text", "json"], default="text")
    cal.set_defaults(func=cmd_calibration)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 skills/_shared/tests/test-pm-status.py TestCalibrationIO -v`
Expected: PASS, 10 tests

- [ ] **Step 5: Run the full suite**

Run: `python3 skills/_shared/tests/test-pm-status.py`
Expected: PASS — 177 + 10 = 187

- [ ] **Step 6: Commit**

```bash
git add skills/_shared/pm-status.py skills/_shared/tests/test-pm-status.py
git commit -s -m "feat(l3io-pm): add calibration file I/O and calibration show

Schema v2 skeleton, decay-weighted ratios, independent per-component
activation with fix requiring both cohorts, and version 1 migration that
starts closure and fix fresh rather than seeding them from a blended ratio."
```

---

## Task 2: `set-estimate` persists the factors it applied

Without this, the scope/fix split is arithmetically impossible — there is nothing to back out and nothing to compare a pure-scope actual against.

**Files:**
- Modify: `skills/_shared/pm-status.py` (`cmd_set_estimate` around line 620, `build_parser`)
- Test: `skills/_shared/tests/test-pm-status.py`

**Interfaces:**
- Consumes: existing `cmd_set_estimate`, `_maybe_set`
- Produces: estimate blocks carrying `fix_factor` and `scope_ratio`; CLI flags `--fix-factor`, `--scope-ratio`

- [ ] **Step 1: Write the failing tests**

```python
class TestEstimateFactors(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_set_estimate_records_factors(self):
        code, out = self.run_main(
            ["set-estimate", "--state-root", self.root, "--story", "E001-S01-003",
             "--man-hours", "6", "--time-hours", "1.5", "--tokens-k", "320",
             "--cost", "4.80", "--fix-factor", "1.25", "--scope-ratio", "1.1"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertAlmostEqual(float(node["estimate"]["fix_factor"]), 1.25)
        self.assertAlmostEqual(float(node["estimate"]["scope_ratio"]), 1.1)

    def test_factors_are_optional_and_absent_when_not_given(self):
        code, out = self.run_main(
            ["set-estimate", "--state-root", self.root, "--story", "E001-S01-003",
             "--man-hours", "6"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertNotIn("fix_factor", node["estimate"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 skills/_shared/tests/test-pm-status.py TestEstimateFactors -v`
Expected: FAIL — `unrecognized arguments: --fix-factor`

- [ ] **Step 3: Implement**

In `cmd_set_estimate`, after the existing story/range branches and before the write, add:

```python
    _maybe_set(est, "fix_factor", getattr(args, "fix_factor", None), float)
    _maybe_set(est, "scope_ratio", getattr(args, "scope_ratio", None), float)
```

In `build_parser`, on the `set-estimate` parser:

```python
    se.add_argument("--fix-factor", dest="fix_factor",
                    help="fix multiplier applied; required for the scope/fix split")
    se.add_argument("--scope-ratio", dest="scope_ratio",
                    help="calibrated scope ratio applied (1.0 when cold-start)")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 skills/_shared/tests/test-pm-status.py TestEstimateFactors -v`
Expected: PASS, 2 tests

- [ ] **Step 5: Commit**

```bash
git add skills/_shared/pm-status.py skills/_shared/tests/test-pm-status.py
git commit -s -m "feat(l3io-pm): record fix_factor and scope_ratio on estimates

The scope/fix split needs to know what multipliers an estimate had baked
in. Without them a pure-scope actual has nothing to be compared against."
```

---

## Task 3: Story sample derivation

**Files:**
- Modify: `skills/_shared/pm-status.py` (calibration section)
- Test: `skills/_shared/tests/test-pm-status.py`

**Interfaces:**
- Consumes: `load_calibration`, `save_calibration`, `_is_na`, `_is_number` (Task 1); estimate `fix_factor`/`scope_ratio` (Task 2)
- Produces:
  - `ESTIMATE_TO_ACTUAL: dict[str, str]` — the non-identity pairing
  - `derive_story_sample(node) -> dict | None` — `{classification, provenance, fix_iterations, scope_ratios: {metric: float}}`
  - `record_story_sample(state_root, node) -> str` — returns a human-readable summary; appends to the calibration file

- [ ] **Step 1: Write the failing tests**

```python
class TestStorySampling(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.root = os.path.join(self.d, "state")
        os.makedirs(self.root)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.d, ignore_errors=True)

    def _story(self, iterations, est=None, act=None):
        est = est or {"man_hours": 6, "time_hours": 1.5, "tokens_k": 320,
                      "cost": 4.80, "fix_factor": 1.25, "scope_ratio": 1.0}
        act = act or {"man_hours": 7, "elapsed_hours": 1.8, "tokens_k": 355,
                      "cost": 5.32}
        node = {"key": "E001-S01-003", "classification": "complex",
                "estimate": est, "actual": act}
        if iterations is not None:
            node["completion_evidence"] = {"fix_iterations": iterations}
        return node

    def test_pairing_is_not_identity(self):
        # the map must send time_hours to elapsed_hours, not to itself
        self.assertEqual(pm.ESTIMATE_TO_ACTUAL["time_hours"], "elapsed_hours")
        self.assertEqual(pm.ESTIMATE_TO_ACTUAL["man_hours"], "man_hours")

    def test_zero_iterations_gives_exact_provenance(self):
        s = pm.derive_story_sample(self._story(0))
        self.assertEqual(s["provenance"], "exact")

    def test_reworked_story_uses_backout_provenance(self):
        s = pm.derive_story_sample(self._story(3))
        self.assertEqual(s["provenance"], "backout")

    def test_absent_iterations_uses_backout(self):
        s = pm.derive_story_sample(self._story(None))
        self.assertEqual(s["provenance"], "backout")

    def test_legacy_estimate_without_factors_is_marked(self):
        est = {"man_hours": 6, "time_hours": 1.5, "tokens_k": 320, "cost": 4.80}
        s = pm.derive_story_sample(self._story(0, est=est))
        self.assertEqual(s["provenance"], "legacy")

    def test_scope_ratio_uses_wall_clock_pairing_correctly(self):
        # estimate.time_hours 1.5 vs actual.elapsed_hours 1.8, fix_factor 1.25
        s = pm.derive_story_sample(self._story(0))
        self.assertAlmostEqual(s["scope_ratios"]["time_hours"], 1.8 * 1.25 / 1.5)

    def test_na_metrics_are_skipped_not_zeroed(self):
        act = {"man_hours": 7, "elapsed_hours": 1.8, "tokens_k": "N/A", "cost": "N/A"}
        s = pm.derive_story_sample(self._story(0, act=act))
        self.assertNotIn("tokens_k", s["scope_ratios"])
        self.assertNotIn("cost", s["scope_ratios"])
        self.assertIn("man_hours", s["scope_ratios"])

    def test_no_estimate_yields_no_sample(self):
        node = {"key": "E001-S01-003", "classification": "complex",
                "actual": {"man_hours": 7}}
        self.assertIsNone(pm.derive_story_sample(node))

    def test_record_appends_to_scope_and_fix_cohort(self):
        pm.record_story_sample(self.root, self._story(0))
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(len(pm._component_samples(cal, "scope", "complex", "man_hours")), 1)
        self.assertEqual(int(cal["fix"]["complex"]["clean"]["samples"]), 1)

    def test_reworked_story_joins_reworked_cohort(self):
        pm.record_story_sample(self.root, self._story(2))
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(int(cal["fix"]["complex"]["reworked"]["samples"]), 1)
        self.assertEqual(int(cal["fix"]["complex"].get("clean", {}).get("samples", 0)), 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 skills/_shared/tests/test-pm-status.py TestStorySampling -v`
Expected: FAIL — `module 'pm_status' has no attribute 'ESTIMATE_TO_ACTUAL'`

- [ ] **Step 3: Implement**

Add to the calibration section:

```python
# The four metrics do NOT pair by name: an estimate's time_hours is an
# actual's elapsed_hours. Zipping keys naively produces a silently wrong
# wall-clock ratio, so the pairing is explicit.
ESTIMATE_TO_ACTUAL = {
    "man_hours": "man_hours",
    "time_hours": "elapsed_hours",
    "tokens_k": "tokens_k",
    "cost": "cost",
}


def derive_story_sample(node):
    """Compute a story's scope samples and its fix cohort. None when not derivable."""
    if not node:
        return None
    est, act = node.get("estimate") or {}, node.get("actual") or {}
    if not est or not act:
        return None

    iters = ((node.get("completion_evidence") or {}).get("fix_iterations"))
    has_factors = _is_number(est.get("fix_factor"))
    fix_factor = float(est["fix_factor"]) if has_factors else 1.0

    if not has_factors:
        provenance = "legacy"
    elif _is_number(iters) and int(iters) == 0:
        provenance = "exact"
    else:
        provenance = "backout"

    ratios = {}
    for e_key, a_key in ESTIMATE_TO_ACTUAL.items():
        e_val, a_val = est.get(e_key), act.get(a_key)
        if e_val is None or a_val is None:
            continue
        if _is_na(e_val) or _is_na(a_val):
            continue          # never coerce N/A to zero
        if not _is_number(e_val) or not _is_number(a_val):
            continue
        e_num = float(str(e_val).lstrip("$"))
        a_num = float(str(a_val).lstrip("$"))
        if e_num == 0:
            continue
        # Both paths multiply by the applied fix factor: a pure-scope actual is
        # still compared against an estimate that had fix baked in.
        ratios[e_key] = a_num * fix_factor / e_num

    if not ratios:
        return None
    return {
        "classification": str(node.get("classification", "standard")),
        "provenance": provenance,
        "fix_iterations": int(iters) if _is_number(iters) else None,
        "scope_ratios": ratios,
        "actual_man_hours": float(act["man_hours"]) if _is_number(act.get("man_hours")) else None,
    }


def _bump_cohort(entry, cohort: str, man_hours):
    """Running mean over a cohort, so a full sample history is not needed."""
    from ruamel.yaml.comments import CommentedMap
    c = entry.get(cohort)
    if c is None:
        c = CommentedMap()
        c["mean_man_hours"] = 0.0
        c["samples"] = 0
        entry[cohort] = c
    if man_hours is None:
        return
    n = int(c.get("samples", 0))
    mean = float(c.get("mean_man_hours", 0.0))
    c["mean_man_hours"] = round((mean * n + man_hours) / (n + 1), 4)
    c["samples"] = n + 1


def record_story_sample(state_root: str, node) -> str:
    sample = derive_story_sample(node)
    if sample is None:
        return "no sample (missing estimate or actual)"
    from ruamel.yaml.comments import CommentedMap
    y, cal = load_calibration(state_root)
    cls = sample["classification"]

    bucket = cal["scope"].setdefault(cls, CommentedMap())
    for metric, ratio in sample["scope_ratios"].items():
        entry = bucket.setdefault(metric, CommentedMap())
        entry.setdefault("samples", [])
        entry["samples"].append(round(ratio, 4))

    fix_entry = cal["fix"].setdefault(cls, CommentedMap())
    iters = sample["fix_iterations"]
    if iters is not None:
        _bump_cohort(fix_entry, "clean" if iters == 0 else "reworked",
                     sample["actual_man_hours"])

    save_calibration(y, cal, state_root)
    return (f"scope+{len(sample['scope_ratios'])} metrics, "
            f"provenance={sample['provenance']}, class={cls}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 skills/_shared/tests/test-pm-status.py TestStorySampling -v`
Expected: PASS, 10 tests

- [ ] **Step 5: Commit**

```bash
git add skills/_shared/pm-status.py skills/_shared/tests/test-pm-status.py
git commit -s -m "feat(l3io-pm): derive story calibration samples

Uses completion_evidence.fix_iterations for an exact split when a story
had no rework, falling back to the approach-A back-out otherwise. The
estimate-to-actual metric pairing is explicit because time_hours maps to
elapsed_hours, not to itself."
```

---

## Task 4: Closure sample derivation

**Files:**
- Modify: `skills/_shared/pm-status.py` (calibration section)
- Test: `skills/_shared/tests/test-pm-status.py`

**Interfaces:**
- Consumes: `list_sprint_dirs`, `list_story_files`, `sprint_file`, `epic_file`, `load_node` (existing); `load_calibration`/`save_calibration` (Task 1)
- Produces: `derive_closure_sample(state_root, level, epic_key, sprint_key=None) -> tuple[dict | None, str]` — `(sample, reason)`; `record_closure_sample(state_root, level, epic_key, sprint_key=None) -> str`

- [ ] **Step 1: Write the failing tests**

```python
class TestClosureSampling(TestLayoutResolution):
    def _write(self, path, mapping):
        import io as _io
        y = pm._yaml()
        with open(path, "w") as f:
            y.dump(mapping, f)

    def _sprint_with_stories(self, story_actuals, sprint_actual, sprint_estimate=None):
        sd = os.path.join(self.root, "active", "epic-001", "sprint-01")
        for f in os.listdir(sd):
            if f.endswith(".yaml") and f != "sprint.yaml":
                os.remove(os.path.join(sd, f))
        for i, a in enumerate(story_actuals, start=1):
            m = {"key": f"E001-S01-{i:03d}", "epic": "E001", "sprint": "S01",
                 "status": "done"}
            if a is not None:
                m["actual"] = {"man_hours": a}
            self._write(os.path.join(sd, f"E001-S01-{i:03d}.yaml"), m)
        sm = {"key": "S01", "epic": "E001", "status": "done"}
        if sprint_actual is not None:
            sm["actual"] = {"man_hours": sprint_actual}
        if sprint_estimate is not None:
            sm["estimate"] = sprint_estimate
        self._write(os.path.join(sd, "sprint.yaml"), sm)

    def test_residual_is_parent_minus_children(self):
        self._sprint_with_stories([3.0, 4.0], 9.0,
                                  {"man_hours_low": 1.0, "man_hours_high": 3.0})
        s, reason = pm.derive_closure_sample(self.root, "sprint", "E001", "S01")
        self.assertIsNotNone(s, reason)
        self.assertAlmostEqual(s["closure_actual"]["man_hours"], 2.0)

    def test_missing_child_actual_skips_with_reason(self):
        self._sprint_with_stories([3.0, None], 9.0,
                                  {"man_hours_low": 1.0, "man_hours_high": 3.0})
        s, reason = pm.derive_closure_sample(self.root, "sprint", "E001", "S01")
        self.assertIsNone(s)
        self.assertIn("actual", reason.lower())

    def test_negative_residual_skips_with_reason(self):
        self._sprint_with_stories([5.0, 5.0], 8.0,
                                  {"man_hours_low": 1.0, "man_hours_high": 3.0})
        s, reason = pm.derive_closure_sample(self.root, "sprint", "E001", "S01")
        self.assertIsNone(s)
        self.assertIn("negative", reason.lower())

    def test_no_parent_actual_skips(self):
        self._sprint_with_stories([3.0, 4.0], None,
                                  {"man_hours_low": 1.0, "man_hours_high": 3.0})
        s, reason = pm.derive_closure_sample(self.root, "sprint", "E001", "S01")
        self.assertIsNone(s)

    def test_record_appends_closure_sample(self):
        self._sprint_with_stories([3.0, 4.0], 9.0,
                                  {"man_hours_low": 1.0, "man_hours_high": 3.0})
        pm.record_closure_sample(self.root, "sprint", "E001", "S01")
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(len(pm._component_samples(cal, "closure", "sprint", "man_hours")), 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 skills/_shared/tests/test-pm-status.py TestClosureSampling -v`
Expected: FAIL — `no attribute 'derive_closure_sample'`

- [ ] **Step 3: Implement**

```python
def _mid(est, low_key, high_key):
    lo, hi = est.get(low_key), est.get(high_key)
    if not _is_number(lo) or not _is_number(hi):
        return None
    return (float(str(lo).lstrip("$")) + float(str(hi).lstrip("$"))) / 2.0


CLOSURE_RANGE_KEYS = {
    "man_hours": ("man_hours_low", "man_hours_high"),
    "time_hours": ("time_hours_low", "time_hours_high"),
    "tokens_k": ("tokens_k_min", "tokens_k_max"),
    "cost": ("cost_low", "cost_high"),
}
CLOSURE_ACTUAL_KEYS = {
    "man_hours": "man_hours",
    "time_hours": "elapsed_hours",
    "tokens_k": "tokens_k",
    "cost": "cost",
}


def derive_closure_sample(state_root: str, level: str, epic_key: str, sprint_key=None):
    """Closure overhead = parent actual - sum(children actuals). (sample, reason)."""
    if level == "sprint":
        ppath = sprint_file(state_root, epic_key, sprint_key)
        child_paths = list_story_files(state_root, epic_key, sprint_key)
    else:
        ppath = epic_file(state_root, epic_key)
        child_paths = [sprint_file(state_root, epic_key, _sprint_key_from_dir(d))
                       for d in list_sprint_dirs(state_root, epic_key)]
    if ppath is None:
        return None, f"{level} node not found"
    _, pnode = load_node(ppath)
    pact = (pnode or {}).get("actual") or {}
    pest = (pnode or {}).get("estimate") or {}
    if not pact:
        return None, f"{level} has no actual yet"

    sums, closure = {}, {}
    for metric, akey in CLOSURE_ACTUAL_KEYS.items():
        total = 0.0
        complete = True
        for cp in child_paths:
            if cp is None:
                complete = False
                break
            _, cn = load_node(cp)
            cv = ((cn or {}).get("actual") or {}).get(akey)
            if cv is None or _is_na(cv) or not _is_number(cv):
                complete = False
                break
            total += float(str(cv).lstrip("$"))
        pv = pact.get(akey)
        if not complete:
            continue          # partial sums understate overhead and bias the ratio low
        if pv is None or _is_na(pv) or not _is_number(pv):
            continue
        residual = float(str(pv).lstrip("$")) - total
        if residual < 0:
            return None, (f"negative closure residual for {metric}: parent "
                          f"{pv} is below children sum {total} — miscounted")
        sums[metric] = total
        closure[metric] = residual

    if not closure:
        return None, "no metric had complete child actuals"

    ratios = {}
    for metric, actual_overhead in closure.items():
        lo, hi = CLOSURE_RANGE_KEYS[metric]
        expected = _mid(pest, lo, hi)
        if expected and expected > 0:
            ratios[metric] = actual_overhead / expected
    return {"level": level, "closure_actual": closure, "ratios": ratios}, "ok"


def record_closure_sample(state_root: str, level: str, epic_key: str, sprint_key=None) -> str:
    sample, reason = derive_closure_sample(state_root, level, epic_key, sprint_key)
    if sample is None:
        return f"no closure sample: {reason}"
    if not sample["ratios"]:
        return "no closure sample: parent has no estimate range to compare against"
    from ruamel.yaml.comments import CommentedMap
    y, cal = load_calibration(state_root)
    bucket = cal["closure"].setdefault(level, CommentedMap())
    for metric, ratio in sample["ratios"].items():
        entry = bucket.setdefault(metric, CommentedMap())
        entry.setdefault("samples", [])
        entry["samples"].append(round(ratio, 4))
    save_calibration(y, cal, state_root)
    return f"closure {level} +{len(sample['ratios'])} metrics"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 skills/_shared/tests/test-pm-status.py TestClosureSampling -v`
Expected: PASS, 5 tests

- [ ] **Step 5: Commit**

```bash
git add skills/_shared/pm-status.py skills/_shared/tests/test-pm-status.py
git commit -s -m "feat(l3io-pm): derive closure calibration samples

Closure overhead is the residual between a parent's actual and its
children's. Skips rather than records when a child actual is missing, the
residual is negative, or a metric is N/A — each of which would silently
bias the ratio."
```

---

## Task 5: Wire sampling into `set-actual`

**Files:**
- Modify: `skills/_shared/pm-status.py` (`cmd_set_actual`, `build_parser`)
- Test: `skills/_shared/tests/test-pm-status.py`

**Interfaces:**
- Consumes: `record_story_sample` (Task 3), `record_closure_sample` (Task 4)
- Produces: `set-actual --no-calibrate`; automatic sample emission after a successful actual write

- [ ] **Step 1: Write the failing tests**

```python
class TestSetActualCalibrates(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _estimated_story(self):
        p = pm.story_file(self.root, "E001-S01-003")
        with open(p, "w") as f:
            f.write("key: 'E001-S01-003'\nepic: 'E001'\nsprint: 'S01'\n"
                    "status: review\nclassification: complex\n"
                    "completion_evidence:\n  fix_iterations: 0\n"
                    "estimate:\n  man_hours: 6\n  time_hours: 1.5\n"
                    "  tokens_k: 320\n  cost: 4.80\n  fix_factor: 1.25\n"
                    "  scope_ratio: 1.0\n")

    def test_actual_write_emits_a_sample(self):
        self._estimated_story()
        code, out = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "story",
             "--story", "E001-S01-003", "--elapsed-hours", "1.8",
             "--man-hours", "7", "--tokens-k", "355", "--cost", "5.32"])
        self.assertEqual(code, 0, out)
        _, cal = pm.load_calibration(self.root)
        self.assertEqual(len(pm._component_samples(cal, "scope", "complex", "man_hours")), 1)

    def test_no_calibrate_suppresses_the_sample(self):
        self._estimated_story()
        code, out = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "story",
             "--story", "E001-S01-003", "--man-hours", "7", "--no-calibrate"])
        self.assertEqual(code, 0, out)
        self.assertFalse(os.path.exists(pm.calibration_path(self.root)))

    def test_story_without_estimate_writes_actual_and_no_sample(self):
        code, out = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "story",
             "--story", "E001-S01-003", "--man-hours", "7"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(node["actual"]["man_hours"], 7)

    def test_calibration_failure_does_not_fail_the_actual_write(self):
        self._estimated_story()
        # make the calibration path unwritable by putting a directory there
        os.makedirs(pm.calibration_path(self.root))
        code, out = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "story",
             "--story", "E001-S01-003", "--man-hours", "7"])
        self.assertEqual(code, 0, out)          # actuals are primary
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(node["actual"]["man_hours"], 7)

    def test_claude_runtime_still_rejects_na(self):
        self._estimated_story()
        code, _ = self.run_main(
            ["set-actual", "--state-root", self.root, "--node", "story",
             "--story", "E001-S01-003", "--tokens-k", "N/A", "--runtime", "claude"])
        self.assertEqual(code, 2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 skills/_shared/tests/test-pm-status.py TestSetActualCalibrates -v`
Expected: FAIL — `unrecognized arguments: --no-calibrate`

- [ ] **Step 3: Implement**

In `cmd_set_actual`, replace the tail (from `save_node(...)` to `return 0`) with:

```python
    save_node(y, node, path, getattr(args, "flock", False))

    calib_note = ""
    if not getattr(args, "no_calibrate", False):
        # Calibration is DERIVED data. A failure here must never fail the
        # actuals write, which is the primary record — but it must be visible,
        # not silent.
        try:
            if kind == "story":
                calib_note = record_story_sample(args.state_root, node)
            elif kind == "sprint":
                calib_note = record_closure_sample(args.state_root, "sprint",
                                                   args.epic, args.sprint)
            elif kind == "epic":
                calib_note = record_closure_sample(args.state_root, "epic", args.epic)
        except Exception as e:                      # noqa: BLE001 - deliberate isolation
            sys.stderr.write(f"pm-status.py: warning — actual written, but calibration "
                             f"sample failed: {e}\n")
            calib_note = "calibration skipped (see stderr)"

    if args.ledger:
        _append_ledger(args.ledger, args.scope or label, f"actual {sorted(provided)}")
    suffix = f" [{calib_note}]" if calib_note else ""
    sys.stdout.write(f"OK set-actual {label} {sorted(provided)}{suffix}\n")
    return 0
```

In `build_parser`, on the `set-actual` parser:

```python
    a.add_argument("--no-calibrate", dest="no_calibrate", action="store_true",
                   help="skip calibration sampling (backfills, replays)")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 skills/_shared/tests/test-pm-status.py TestSetActualCalibrates -v`
Expected: PASS, 5 tests

- [ ] **Step 5: Run the full suite**

Run: `python3 skills/_shared/tests/test-pm-status.py`
Expected: PASS — no regression in the existing `set-actual` tests.

- [ ] **Step 6: Commit**

```bash
git add skills/_shared/pm-status.py skills/_shared/tests/test-pm-status.py
git commit -s -m "feat(l3io-pm): emit calibration samples from set-actual

A sample is arithmetic over data already on disk, so deriving it here
removes the class of failure where an orchestrator forgets to append one.
Calibration failure warns and never fails the actuals write."
```

---

## Task 6: `estimate-story`

**Files:**
- Modify: `skills/_shared/pm-status.py`
- Test: `skills/_shared/tests/test-pm-status.py`

**Interfaces:**
- Consumes: `load_calibration`, `active_scope_ratio`, `active_fix_factor`, `COLD_START_*` (Task 1); `story_file`, `load_node`, `save_node`
- Produces: `BASE_BANDS: dict`, `cmd_estimate_story(args) -> int`, CLI `estimate-story --state-root R --story KEY --classification {simple,standard,complex} [--confidence {low,medium,high}]`

- [ ] **Step 1: Write the failing tests**

```python
class TestEstimateStory(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_cold_start_uses_band_midpoint_times_fix_prior(self):
        code, out = self.run_main(
            ["estimate-story", "--state-root", self.root, "--story", "E001-S01-003",
             "--classification", "complex"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        est = node["estimate"]
        mid = (pm.BASE_BANDS["complex"]["man_hours"][0] +
               pm.BASE_BANDS["complex"]["man_hours"][1]) / 2
        self.assertAlmostEqual(float(est["man_hours"]),
                               round(mid * 1.0 * pm.COLD_START_FIX_FACTOR, 2))
        self.assertAlmostEqual(float(est["fix_factor"]), pm.COLD_START_FIX_FACTOR)
        self.assertAlmostEqual(float(est["scope_ratio"]), pm.COLD_START_SCOPE_RATIO)

    def test_calibrated_ratio_is_applied_once_active(self):
        y, cal = pm.load_calibration(self.root)
        cal["scope"]["complex"] = {"man_hours": {"samples": [1.5, 1.5, 1.5]}}
        pm.save_calibration(y, cal, self.root)
        self.run_main(["estimate-story", "--state-root", self.root,
                       "--story", "E001-S01-003", "--classification", "complex"])
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertAlmostEqual(float(node["estimate"]["scope_ratio"]), 1.5)

    def test_unknown_story_exits_3(self):
        code, _ = self.run_main(
            ["estimate-story", "--state-root", self.root, "--story", "E001-S01-999",
             "--classification", "simple"])
        self.assertEqual(code, 3)

    def test_classification_is_written_to_the_node(self):
        self.run_main(["estimate-story", "--state-root", self.root,
                       "--story", "E001-S01-003", "--classification", "simple"])
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertEqual(node["classification"], "simple")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 skills/_shared/tests/test-pm-status.py TestEstimateStory -v`
Expected: FAIL — `invalid choice: 'estimate-story'`

- [ ] **Step 3: Implement**

```python
# Cold-start base bands (low, high) per classification. These were previously a
# markdown table in steps/shared/step-estimate.md; this is now the single source.
BASE_BANDS = {
    "simple":   {"man_hours": (2, 4),  "time_hours": (0.5, 1.5), "tokens_k": (20, 50),  "cost": (0.10, 0.35)},
    "standard": {"man_hours": (4, 8),  "time_hours": (1, 3),     "tokens_k": (40, 100), "cost": (0.25, 0.70)},
    "complex":  {"man_hours": (8, 16), "time_hours": (2, 6),     "tokens_k": (80, 200), "cost": (0.55, 1.40)},
}


def cmd_estimate_story(args) -> int:
    path = story_file(args.state_root, args.story)
    if path is None:
        _die_notfound(f"story {args.story}")
    y, node = load_node(path)
    if node is None:
        _die_notfound(f"story {args.story} — file is empty")

    cls = args.classification
    _, cal = load_calibration(args.state_root)
    fix = active_fix_factor(cal, cls)
    fix = COLD_START_FIX_FACTOR if fix is None else fix

    from ruamel.yaml.comments import CommentedMap
    est = node.get("estimate")
    if est is None:
        est = CommentedMap()
        node["estimate"] = est

    applied_ratio = None
    for metric, (lo, hi) in BASE_BANDS[cls].items():
        mid = (lo + hi) / 2.0
        ratio = active_scope_ratio(cal, cls, metric)
        if ratio is None:
            ratio = COLD_START_SCOPE_RATIO
        if applied_ratio is None:
            applied_ratio = ratio
        value = mid * ratio * fix
        est[metric] = int(round(value)) if metric == "tokens_k" else round(value, 2)

    est["fix_factor"] = round(fix, 4)
    est["scope_ratio"] = round(applied_ratio, 4)
    if args.confidence:
        est["confidence"] = args.confidence
    node["classification"] = cls
    node["updated_at"] = _now_iso()
    save_node(y, node, path)
    sys.stdout.write(f"OK estimate-story {args.story} class={cls} "
                     f"scope_ratio={est['scope_ratio']} fix_factor={est['fix_factor']}\n")
    return 0
```

Register:

```python
    es = sub.add_parser("estimate-story", help="compute and write a story estimate")
    es.add_argument("--state-root", required=True)
    es.add_argument("--story", required=True)
    es.add_argument("--classification", required=True, choices=list(CLASSIFICATIONS))
    es.add_argument("--confidence", choices=["low", "medium", "high"])
    es.set_defaults(func=cmd_estimate_story)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 skills/_shared/tests/test-pm-status.py TestEstimateStory -v`
Expected: PASS, 4 tests

- [ ] **Step 5: Commit**

```bash
git add skills/_shared/pm-status.py skills/_shared/tests/test-pm-status.py
git commit -s -m "feat(l3io-pm): add estimate-story

The model supplies the classification; the script applies band times
scope ratio times fix factor and records both factors. Base bands move
out of step-file prose into code as the single source."
```

---

## Task 7: `estimate-rollup`

**Files:**
- Modify: `skills/_shared/pm-status.py`
- Test: `skills/_shared/tests/test-pm-status.py`

**Interfaces:**
- Consumes: `list_story_files`, `list_sprint_dirs`, `sprint_file`, `epic_file`, `active_closure_ratio`
- Produces: `cmd_estimate_rollup(args) -> int`, CLI `estimate-rollup --state-root R --epic KEY [--sprint KEY]`

- [ ] **Step 1: Write the failing tests**

```python
class TestEstimateRollup(TestLayoutResolution):
    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _story_estimates(self, values):
        sd = os.path.join(self.root, "active", "epic-001", "sprint-01")
        for f in os.listdir(sd):
            if f.endswith(".yaml") and f != "sprint.yaml":
                os.remove(os.path.join(sd, f))
        for i, v in enumerate(values, start=1):
            with open(os.path.join(sd, f"E001-S01-{i:03d}.yaml"), "w") as f:
                f.write(f"key: 'E001-S01-{i:03d}'\nepic: 'E001'\nsprint: 'S01'\n"
                        f"estimate:\n  man_hours: {v}\n  time_hours: 1\n"
                        f"  tokens_k: 10\n  cost: 0.5\n")

    def test_sprint_rollup_sums_children_plus_closure(self):
        self._story_estimates([4, 6])
        code, out = self.run_main(
            ["estimate-rollup", "--state-root", self.root, "--epic", "E001",
             "--sprint", "S01"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.sprint_file(self.root, "E001", "S01"))
        est = node["estimate"]
        self.assertGreaterEqual(float(est["man_hours_high"]), 10.0)
        self.assertLessEqual(float(est["man_hours_low"]), float(est["man_hours_high"]))

    def test_rollup_writes_range_form_not_single_values(self):
        self._story_estimates([4, 6])
        self.run_main(["estimate-rollup", "--state-root", self.root,
                       "--epic", "E001", "--sprint", "S01"])
        _, node = pm.load_node(pm.sprint_file(self.root, "E001", "S01"))
        self.assertIn("man_hours_low", node["estimate"])
        self.assertNotIn("man_hours", node["estimate"])

    def test_unknown_epic_exits_3(self):
        code, _ = self.run_main(
            ["estimate-rollup", "--state-root", self.root, "--epic", "E999"])
        self.assertEqual(code, 3)

    def test_epic_rollup_sums_sprints(self):
        self._story_estimates([4, 6])
        self.run_main(["estimate-rollup", "--state-root", self.root,
                       "--epic", "E001", "--sprint", "S01"])
        code, out = self.run_main(
            ["estimate-rollup", "--state-root", self.root, "--epic", "E001"])
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.epic_file(self.root, "E001"))
        self.assertIn("man_hours_low", node["estimate"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 skills/_shared/tests/test-pm-status.py TestEstimateRollup -v`
Expected: FAIL — `invalid choice: 'estimate-rollup'`

- [ ] **Step 3: Implement**

```python
# Closure overhead as a fraction of children, used when no calibrated ratio is
# active yet. Deliberately a band, not a point: closure cost is variable.
COLD_START_CLOSURE_BAND = (0.10, 0.25)

ROLLUP_CHILD_KEYS = {          # child single-value key -> parent range keys
    "man_hours": ("man_hours_low", "man_hours_high"),
    "time_hours": ("time_hours_low", "time_hours_high"),
    "tokens_k": ("tokens_k_min", "tokens_k_max"),
    "cost": ("cost_low", "cost_high"),
}


def _child_estimate_value(node, metric):
    est = (node or {}).get("estimate") or {}
    v = est.get(metric)
    if v is not None and _is_number(v):
        return float(str(v).lstrip("$"))
    lo, hi = ROLLUP_CHILD_KEYS[metric]
    return _mid(est, lo, hi)


def cmd_estimate_rollup(args) -> int:
    level = "sprint" if args.sprint else "epic"
    if level == "sprint":
        ppath = sprint_file(args.state_root, args.epic, args.sprint)
        child_paths = list_story_files(args.state_root, args.epic, args.sprint)
    else:
        ppath = epic_file(args.state_root, args.epic)
        child_paths = [sprint_file(args.state_root, args.epic, _sprint_key_from_dir(d))
                       for d in list_sprint_dirs(args.state_root, args.epic)]
    if ppath is None:
        _die_notfound(f"{level} {args.sprint or args.epic}")
    y, pnode = load_node(ppath)
    if pnode is None:
        _die_notfound(f"{level} file is empty")

    _, cal = load_calibration(args.state_root)
    from ruamel.yaml.comments import CommentedMap
    est = CommentedMap()
    counted = 0
    for metric, (lo_key, hi_key) in ROLLUP_CHILD_KEYS.items():
        total = 0.0
        seen = 0
        for cp in child_paths:
            if cp is None:
                continue
            _, cn = load_node(cp)
            v = _child_estimate_value(cn, metric)
            if v is not None:
                total += v
                seen += 1
        if seen == 0:
            continue
        counted = max(counted, seen)
        ratio = active_closure_ratio(cal, level, metric)
        if ratio is None:
            lo = total * (1 + COLD_START_CLOSURE_BAND[0])
            hi = total * (1 + COLD_START_CLOSURE_BAND[1])
        else:
            lo = total * (1 + ratio * COLD_START_CLOSURE_BAND[0])
            hi = total * (1 + ratio * COLD_START_CLOSURE_BAND[1])
        if metric == "tokens_k":
            est[lo_key], est[hi_key] = int(round(lo)), int(round(hi))
        else:
            est[lo_key], est[hi_key] = round(lo, 2), round(hi, 2)

    if counted == 0:
        _die_usage(f"{level} {args.sprint or args.epic} has no child estimates to roll up")

    est["confidence"] = "medium"
    pnode["estimate"] = est
    pnode["updated_at"] = _now_iso()
    save_node(y, pnode, ppath)
    sys.stdout.write(f"OK estimate-rollup {level} {args.sprint or args.epic} "
                     f"from {counted} children\n")
    return 0
```

Register:

```python
    er = sub.add_parser("estimate-rollup", help="roll child estimates up to a sprint or epic")
    er.add_argument("--state-root", required=True)
    er.add_argument("--epic", required=True)
    er.add_argument("--sprint", default="")
    er.set_defaults(func=cmd_estimate_rollup)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 skills/_shared/tests/test-pm-status.py TestEstimateRollup -v`
Expected: PASS, 4 tests

- [ ] **Step 5: Bump the script version and run the full suite**

`self-install` skips when the installed copy is `>=` its own, so without a bump no existing project receives these subcommands. Set BOTH markers to `2.1.0` — line 6 (`# pm-status-version: 2.1.0`) and `PM_STATUS_VERSION = "2.1.0"` — and update `REQUIRED` in `skills/l3io-util-cleanup/assets/migrate-state.md` to match.

Run: `python3 skills/_shared/tests/test-pm-status.py`
Expected: PASS

- [ ] **Step 6: Sync and commit**

```bash
npm run sync:scripts && npm run check:scripts
git add skills/_shared/pm-status.py skills/_shared/tests/test-pm-status.py \
        skills/l3io-util-cleanup/assets/migrate-state.md skills/*/scripts/
git commit -s -m "feat(l3io-pm): add estimate-rollup and bump pm-status.py to 2.1.0

Sprint and epic estimates become the sum of children plus a closure band,
calibrated once the closure component activates. The version bump is
required: self-install skips copies at or above its own version, so
without it no existing project gets the new subcommands."
```

---

## Task 8: Documentation

**Files:**
- Modify: `skills/_shared/metrics-contract.md`, `skills/_shared/steps/shared/step-estimate.md`, `skills/_shared/steps/sprint/step-04-sprint-closure.md`, `skills/_shared/steps/execute/step-06-epic-closure.md`, `skills/_shared/status-files.md`, `CLAUDE.md`

**Interfaces:**
- Consumes: every subcommand from Tasks 1-7
- Produces: documentation that matches the code

- [ ] **Step 1: Rewrite `metrics-contract.md` §8**

Replace the calibration section to describe what now runs:
- The three components, with `fix` requiring **both** cohorts at ≥3 samples and the reason (one cohort cannot form a ratio).
- The new `fix` schema (`clean`/`reworked` with `mean_man_hours` and `samples`, plus derived `avg_fix_factor`).
- The iteration-based split, with approach-A back-out as the documented fallback and `provenance` values `exact` / `backout` / `legacy`.
- `granularity` stored in the file rather than bound from a step.
- Sampling happens inside `set-actual`; `--no-calibrate` opts out.
- Replace "Mechanization status" — it currently says nothing runs. State what does, and that closure sampling skips rather than records on a missing child actual, a negative residual, or an `N/A` metric.

In §6, replace the base-band table with a pointer to `BASE_BANDS` in `pm-status.py` as the single source. In §9, delete the disagreement entries this closes and keep the rest.

- [ ] **Step 2: Rewrite `step-estimate.md`**

Replace sections 1 and 3 (loading calibration, hand-computing estimates) with:

```bash
python3 {pm_status} estimate-story \
  --state-root {pm_state_root} \
  --story {story_key} \
  --classification {simple|standard|complex}
```

and sections 4-5 (sprint/epic roll-up) with:

```bash
python3 {pm_status} estimate-rollup --state-root {pm_state_root} --epic {epic_key} --sprint {sprint_key}
python3 {pm_status} estimate-rollup --state-root {pm_state_root} --epic {epic_key}
```

Remove the base-band table; cite `metrics-contract.md` §6 instead. State that the model's only job is choosing the classification.

- [ ] **Step 3: Drop the manual sample-append prose**

In `steps/sprint/step-04-sprint-closure.md` and `steps/execute/step-06-epic-closure.md`, remove the instructions to append calibration samples by hand. Replace with a one-line note that `set-actual` records the sample automatically, and that a skipped sample is reported on stderr.

- [ ] **Step 4: Update `status-files.md` and `CLAUDE.md`**

Add `estimate-story`, `estimate-rollup`, and `calibration show` to the subcommand documentation in `status-files.md`, and note that `pm-calibration.yaml` is written with flock as a shared append target.

In `CLAUDE.md`, correct the Estimation-calibration paragraph: it describes learning that did not previously happen. State that samples are derived inside `set-actual`, that `fix` needs both cohorts, and that the scope/fix split uses `fix_iterations`.

- [ ] **Step 5: Verify**

```bash
grep -n "Nothing in .pm-status.py. reads or writes" skills/_shared/metrics-contract.md   # must be empty
grep -rn "Base band by classification" skills/_shared/steps/shared/step-estimate.md      # must be empty
python3 skills/_shared/tests/test-pm-status.py
npm run sync:scripts && npm run check:scripts
git status --porcelain    # empty after commit
```

- [ ] **Step 6: Commit**

```bash
git add skills/_shared/ skills/*/references/ skills/*/steps/ CLAUDE.md
git commit -s -m "docs(l3io-pm): document the calibration loop that now runs

metrics-contract.md no longer says nothing is mechanized. Estimate
arithmetic moves out of step-file prose into estimate-story and
estimate-rollup, and base bands cite pm-status.py as their source."
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §1 Interface — `set-actual` extension | 5 |
| §1 Interface — `estimate-story` | 6 |
| §1 Interface — `estimate-rollup` | 7 |
| §1 Interface — `calibration show` | 1 |
| §1 Base bands as code constants | 6 |
| §2 Estimate-block schema change | 2 |
| §2 Metric-name trap | 3 (explicit map + test) |
| §3 Story sampling, exact/fallback/legacy | 3 |
| §3 `fix` schema and both-cohort activation | 1 (activation), 3 (cohort writes) |
| §4 Closure sampling and its three guards | 4 |
| §5 Granularity in the file | 1 |
| §5 Weighting and activation | 1 |
| §5 Failure behaviour | 5 |
| §5 `version: 1` migration | 1 |
| §6 Testing | every task |
| §7 Documentation | 8 |

No spec requirement is unassigned.

**Type consistency:** `state_root` is the parameter name and `--state-root` the flag throughout. `derive_story_sample`/`record_story_sample` and `derive_closure_sample`/`record_closure_sample` follow one naming pattern. `_component_samples` is defined in Task 1 and used by Tasks 3, 4 and their tests. `_mid` is defined in Task 4 and reused by Task 7 — **Task 7 depends on Task 4 for it**, so the order matters. `CLASSIFICATIONS` (Task 1) is reused by Tasks 3 and 6. `ESTIMATE_TO_ACTUAL` (Task 3) and `CLOSURE_ACTUAL_KEYS` (Task 4) both encode the `time_hours`→`elapsed_hours` pairing; they are deliberately separate because one maps single-value estimates and the other maps range estimates, but if either changes both must.

**Ordering constraints:** Tasks 1→2→3→4→5 are strictly sequential (each consumes the previous). Task 6 needs Task 1. Task 7 needs Tasks 1 and 4 (`_mid`). Task 8 needs all.
