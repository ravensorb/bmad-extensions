# Multi-Runtime Estimation Support (Codex + Copilot) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `pm-status.py`'s runtime enforcement and the PM step files to make Codex CLI and GitHub Copilot first-class runtimes with named `--runtime codex` and `--runtime copilot` values, each with harness-specific token capture enforcement, plus a new user-facing estimation guide.

**Architecture:** Add `codex` and `copilot` to `pm-status.py`'s `choices=["claude","other"]` (becoming 4 values) and introduce per-runtime enforcement branches in `cmd_set_actual` and `cmd_verify`. Codex captures 3 token classes (input, output, cache_read; cache_write=0 due to a known Codex CLI bug) and derives cost from them. Copilot captures a prompt+completion total with no class split, stores it as a scalar, and records cost as N/A. Update the shared step and reference files to give each harness a concrete capture procedure, then add a new user-facing `docs/estimation-guide.md` that explains the system across all runtimes.

**Tech Stack:** Python (pm-status.py), Markdown (step files, reference docs), Node.js (sync scripts), pytest (test suite)

**Spec:** This plan implements the design decided in the 2026-09-01 conversation covering Option A multi-runtime support. Research findings: Codex CLI logs `input_tokens`, `output_tokens`, `cached_input_tokens` in `~/.codex/sessions/**/rollout-*.jsonl` `token_count` events; `cache_write_tokens` is dropped by Codex CLI (GitHub issue #32479). Copilot exposes `prompt_tokens`/`completion_tokens`/`total_tokens` per request; no session transcript file; no cache split accessible to the agent.

## Global Constraints

- `pm-status.py` is a **shared runtime file**: edit only `skills/_shared/pm-status.py` — never per-skill copies. Run `npm run sync:scripts` after every change.
- Never hand-edit `payload-manifest.json`. Run `node scripts/write-payload-manifest.mjs` after all payload changes.
- `TOKEN_CLASSES = ("input", "output", "cache_write", "cache_read")` — order is fixed and canonical.
- `--runtime` default must remain `"other"` (the permissive fail-safe direction).
- `cost` is **never entered** — always derived or N/A. `set-actual` and `set-estimate` reject `--cost*` outright.
- All five `METRIC_FIELDS` must be present in every `actual` block; their absence fails `verify`. Allowed N/A values per runtime are defined below.
- Commit convention: `feat(l3io-pm): <description>`, DCO sign-off (`git commit -s`).
- After changes to `skills/_shared/steps/` or `skills/_shared/metrics-contract.md`, run `npm run sync:scripts` and `npm run check:scripts` before committing.
- After changes to any payload file, run `node scripts/write-payload-manifest.mjs` and `npm run check:manifest` before committing.
- Tests live in `skills/_shared/tests/test-pm-status.py` — never in per-skill directories.

---

## Runtime Enforcement Contract (reference for all tasks)

| Runtime | tokens_k shape | N/A allowed? | cost derived? | model required? |
|---|---|---|---|---|
| `claude` | full 4-class mapping | No | Yes — from all 4 classes | Yes |
| `codex` | 3-class mapping (cache_write=0) | No | Yes — from 3 classes | Yes |
| `copilot` | scalar (input+output total) | No (tokens); Yes (cost) | No | No |
| `other` | any / N/A | Yes | When tokens given | When tokens given |

**Verify N/A rules:**
- `tokens_k=N/A`: fails under `claude`, `codex`, `copilot`
- `cost=N/A`: fails under `claude`, `codex`; **passes** under `copilot` (expected — no class split) and `other`
- scalar `tokens_k`: fails under `claude`, `codex`; passes under `copilot`, `other`

**OpenAI TOKEN_RATES to add** (verify exact values at https://openai.com/api/pricing before implementing — these are best-known as of 2026-09):

```python
"codex-1":  {"input": 5.00, "output": 30.00, "cache_write": 6.25, "cache_read": 2.50},
"gpt-5":    {"input": 5.00, "output": 30.00, "cache_write": 6.25, "cache_read": 2.50},
"gpt-5.4":  {"input": 2.50, "output": 10.00, "cache_write": 3.13, "cache_read": 1.25},
"gpt-5.6":  {"input": 5.00, "output": 30.00, "cache_write": 6.25, "cache_read": 2.50},
```

Note: `cache_write` for OpenAI is 1.25× the input rate (same multiplier as Anthropic); `cache_read` is 50% of the input rate. Confirm from the pricing page before coding.

**Codex CLI session files:** `~/.codex/sessions/**/rollout-*.jsonl`, events with `type: "token_count"`, fields `input_tokens`, `output_tokens`, `cached_input_tokens`. `reasoning_output_tokens` folds into `output_tokens` (add before passing to pm-status.py).

**Copilot per-request:** `usage.prompt_tokens` → input, `usage.completion_tokens` → output. No session file. Agent sums per-request values across the node's dispatch window.

---

## File Map

| File | Action | What changes |
|---|---|---|
| `skills/_shared/pm-status.py` | Modify | TOKEN_RATES (OpenAI), argparse choices, cmd_set_actual enforcement, cmd_verify enforcement |
| `skills/_shared/tests/test-pm-status.py` | Modify | New test classes for codex and copilot enforcement |
| `skills/_shared/steps/shared/step-00-activate.md` | Modify | Runtime detection extended to codex/copilot |
| `skills/_shared/metrics-contract.md` | Modify | §3 split into four named runtime subsections |
| `docs/estimation-guide.md` | Create | New user-facing estimation guide |
| `skills/l3io-pm-execute/scripts/pm-status.py` + others | Auto-generated | `npm run sync:scripts` |
| `skills/*/steps/shared/step-00-activate.md` + others | Auto-generated | `npm run sync:scripts` |
| All `payload-manifest.json` files | Auto-generated | `node scripts/write-payload-manifest.mjs` |

---

## Task 1: Add OpenAI rates and extend argparse runtime choices

**Files:**
- Modify: `skills/_shared/pm-status.py` (lines ~1967–1974 for TOKEN_RATES; line ~4734 and ~4749 for argparse)
- Test: `skills/_shared/tests/test-pm-status.py`

**Interfaces:**
- Produces: `choices=["claude", "codex", "copilot", "other"]` used by Tasks 2 and 3
- Produces: OpenAI model keys in `TOKEN_RATES` used by Task 2 (codex cost derivation)

- [ ] **Step 1: Write failing tests for the new choices**

Add a new test class to `skills/_shared/tests/test-pm-status.py`:

```python
class TestRuntimeChoices(TestLayoutResolution):
    """T-RC: runtime argparse choices include codex and copilot."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def test_codex_is_a_valid_runtime_choice(self):
        # set-actual with --runtime codex but no tokens — should fail for a
        # different reason than "invalid choice", proving codex is accepted
        code, out = self.run_main([
            "set-actual", "--state-root", self.root, "--node", "story",
            "--story", "E001-S01-003", "--runtime", "codex",
            "--elapsed-hours", "1.0", "--man-hours", "4.0", "--hitl-hours", "0.2",
            "--no-calibrate",
        ])
        # exit 0 or 2 (usage error about tokens), never 2 with "invalid choice"
        self.assertNotIn("invalid choice", out)

    def test_copilot_is_a_valid_runtime_choice(self):
        code, out = self.run_main([
            "set-actual", "--state-root", self.root, "--node", "story",
            "--story", "E001-S01-003", "--runtime", "copilot",
            "--elapsed-hours", "1.0", "--man-hours", "4.0", "--hitl-hours", "0.2",
            "--no-calibrate",
        ])
        self.assertNotIn("invalid choice", out)

    def test_invalid_runtime_rejected(self):
        code, out = self.run_main([
            "set-actual", "--state-root", self.root, "--node", "story",
            "--story", "E001-S01-003", "--runtime", "github-copilot",
            "--elapsed-hours", "1.0",
        ])
        self.assertEqual(code, 2)
        self.assertIn("invalid choice", out)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /mnt/source/git/l3io/bmad/bmad-extensions
uv run pytest skills/_shared/tests/test-pm-status.py::TestRuntimeChoices -v 2>&1 | tail -20
```

Expected: FAIL — `codex` and `copilot` are not valid choices yet.

- [ ] **Step 3: Add OpenAI rates to TOKEN_RATES in pm-status.py**

In `skills/_shared/pm-status.py`, locate `TOKEN_RATES = {` (around line 1967). **First verify the rates at https://openai.com/api/pricing**, then add after the last Claude entry:

```python
TOKEN_RATES = {
    "claude-opus-5":      {"input": 5.00,  "output": 25.00, "cache_write": 6.25,  "cache_read": 0.50},
    "claude-opus-5-fast": {"input": 10.00, "output": 50.00, "cache_write": 12.50, "cache_read": 1.00},
    "claude-fable-5":     {"input": 10.00, "output": 50.00, "cache_write": 12.50, "cache_read": 1.00},
    "claude-sonnet-5":    {"input": 3.00,  "output": 15.00, "cache_write": 3.75,  "cache_read": 0.30},
    "claude-sonnet-4-6":  {"input": 3.00,  "output": 15.00, "cache_write": 3.75,  "cache_read": 0.30},
    "claude-haiku-4-5":   {"input": 1.00,  "output": 5.00,  "cache_write": 1.25,  "cache_read": 0.10},
    # OpenAI / Codex — verify at https://openai.com/api/pricing before use
    "codex-1":            {"input": 5.00,  "output": 30.00, "cache_write": 6.25,  "cache_read": 2.50},
    "gpt-5":              {"input": 5.00,  "output": 30.00, "cache_write": 6.25,  "cache_read": 2.50},
    "gpt-5.4":            {"input": 2.50,  "output": 10.00, "cache_write": 3.13,  "cache_read": 1.25},
    "gpt-5.6":            {"input": 5.00,  "output": 30.00, "cache_write": 6.25,  "cache_read": 2.50},
}
```

- [ ] **Step 4: Extend argparse choices in two places**

Find and update both `--runtime` `add_argument` calls (around lines 4734 and 4749):

```python
# set-actual parser (~line 4734)
a.add_argument("--runtime", choices=["claude", "codex", "copilot", "other"], default="other")

# verify parser (~line 4749)
v.add_argument("--runtime", choices=["claude", "codex", "copilot", "other"], default="other")
```

- [ ] **Step 5: Run tests — expect pass**

```bash
uv run pytest skills/_shared/tests/test-pm-status.py::TestRuntimeChoices -v 2>&1 | tail -20
```

Expected: all three tests PASS.

- [ ] **Step 6: Run full test suite to confirm no regressions**

```bash
uv run pytest skills/_shared/tests/test-pm-status.py -x -q 2>&1 | tail -20
```

Expected: all existing tests PASS.

- [ ] **Step 7: Commit**

```bash
git add skills/_shared/pm-status.py skills/_shared/tests/test-pm-status.py
git commit -s -m "feat(l3io-pm): extend runtime choices to codex and copilot, add OpenAI token rates"
```

---

## Task 2: Implement Codex enforcement in cmd_set_actual and cmd_verify

**Files:**
- Modify: `skills/_shared/pm-status.py` (cmd_set_actual ~line 3280, cmd_verify ~line 4576)
- Test: `skills/_shared/tests/test-pm-status.py`

**Interfaces:**
- Consumes: `choices=["claude","codex","copilot","other"]` and OpenAI rates from Task 1
- Produces: `--runtime codex` enforcement used by Task 4 (activation step) and Task 5 (metrics-contract)

**Codex enforcement rules:**
- `--tokens-na` → exit 2 (forbidden, same as claude)
- `--tokens-input` + `--tokens-output` + `--tokens-cache-read` all required; `--tokens-cache-write` defaults to `"0"` when omitted (Codex CLI drops this field — GitHub issue #32479)
- `--model` required (for cost derivation)
- Stores full 4-class mapping with `cache_write=0`; derives `cost`
- `verify`: scalar tokens_k fails (same as claude); N/A for tokens_k or cost fails

- [ ] **Step 1: Write failing tests**

Add to `skills/_shared/tests/test-pm-status.py`:

```python
class TestCodexRuntime(TestLayoutResolution):
    """T-CX: --runtime codex enforcement in set-actual and verify."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _set(self, *extra):
        return self.run_main([
            "set-actual", "--state-root", self.root, "--node", "story",
            "--story", "E001-S01-003", "--runtime", "codex", "--no-calibrate",
            "--elapsed-hours", "2.0", "--man-hours", "8.0", "--hitl-hours", "0.5",
        ] + list(extra))

    def _verify(self, *extra):
        return self.run_main([
            "verify", "--state-root", self.root, "--scope", "story",
            "--story", "E001-S01-003", "--runtime", "codex",
        ] + list(extra))

    def test_tokens_na_forbidden_under_codex(self):
        code, out = self._set("--tokens-na")
        self.assertEqual(code, 2)
        self.assertIn("codex", out)

    def test_codex_requires_input_output_cache_read(self):
        # missing --tokens-cache-read
        code, out = self._set(
            "--tokens-input", "100", "--tokens-output", "20", "--model", "codex-1",
        )
        self.assertEqual(code, 2)
        self.assertIn("cache-read", out)

    def test_codex_cache_write_defaults_to_zero(self):
        # omitting --tokens-cache-write should succeed; cache_write stored as 0
        code, out = self._set(
            "--tokens-input", "100", "--tokens-output", "20",
            "--tokens-cache-read", "300", "--model", "codex-1",
        )
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        tk = node["actual"]["tokens_k"]
        self.assertEqual(int(tk["cache_write"]), 0)
        self.assertEqual(int(tk["total"]), 420)  # 100+20+0+300

    def test_codex_derives_cost_from_three_classes(self):
        code, out = self._set(
            "--tokens-input", "100", "--tokens-output", "20",
            "--tokens-cache-read", "300", "--model", "codex-1",
        )
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        # cost = (100×5 + 20×30 + 0×6.25 + 300×2.5) / 1000 = (500+600+0+750)/1000 = 1.85
        self.assertAlmostEqual(float(node["actual"]["cost"]), 1.85, places=2)

    def test_verify_fails_on_scalar_tokens_under_codex(self):
        # Write a node with scalar tokens_k manually, then verify under codex
        _, node, path, _ = pm.load_node.__module__  # just to get path
        f = pm.story_file(self.root, "E001-S01-003")
        _, n = pm.load_node(f)
        n.setdefault("actual", {})
        n["actual"].update({
            "elapsed_hours": 2.0, "man_hours": 8.0, "hitl_hours": 0.5,
            "tokens_k": 420, "cost": "N/A", "model": "codex-1",
        })
        n["status"] = "done"
        n.setdefault("completion_evidence", {})
        import ruamel.yaml
        y = ruamel.yaml.YAML()
        with open(f, "w") as fh:
            y.dump(n, fh)
        code, out = self._verify()
        self.assertEqual(code, 4)
        self.assertIn("not the per-class mapping", out + self._stderr_capture())

    def test_verify_na_tokens_fails_under_codex(self):
        # Write tokens_k=N/A to a done node, then verify
        f = pm.story_file(self.root, "E001-S01-003")
        _, n = pm.load_node(f)
        n.setdefault("actual", {})
        n["actual"].update({
            "elapsed_hours": 2.0, "man_hours": 8.0, "hitl_hours": 0.5,
            "tokens_k": "N/A", "cost": "N/A", "model": "codex-1",
        })
        n["status"] = "done"
        n.setdefault("completion_evidence", {})
        import ruamel.yaml
        y = ruamel.yaml.YAML()
        with open(f, "w") as fh:
            y.dump(n, fh)
        code, _ = self._verify()
        self.assertEqual(code, 4)
```

> Note on `test_verify_fails_on_scalar_tokens_under_codex`: look at how the existing `TestVerifyScalarTokens` class in the test file sets up its nodes — copy that pattern exactly rather than the partial stub above.

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest skills/_shared/tests/test-pm-status.py::TestCodexRuntime -v 2>&1 | tail -30
```

Expected: FAIL — codex enforcement not yet implemented.

- [ ] **Step 3: Implement codex branch in cmd_set_actual**

In `skills/_shared/pm-status.py`, in `cmd_set_actual` around line 3284, extend the `if args.tokens_na:` check and add a codex branch in the `elif given:` block:

**Change 1** — extend the `--tokens-na` rejection to include codex:
```python
    if args.tokens_na:
        if args.runtime in ("claude", "codex"):
            _die_usage(f"runtime={args.runtime} forbids tokens=N/A — capture the exact "
                       f"per-class counts from the session transcript "
                       f"(see metrics-contract.md §3)")
        provided["tokens_k"] = "N/A"
        provided["cost"] = "N/A"
```

**Change 2** — add codex-specific class enforcement inside the `elif given:` block, immediately after the existing `claude` check:
```python
    elif given:
        if args.runtime == "claude" and len(given) < len(TOKEN_CLASSES):
            # ... existing claude check unchanged ...

        if args.runtime == "codex":
            required_cx = ("input", "output", "cache_read")
            missing_cx = [c for c in required_cx if c not in given]
            if missing_cx:
                _die_usage(
                    "runtime=codex requires --tokens-input, --tokens-output, and "
                    "--tokens-cache-read (read from rollout-*.jsonl token_count events — "
                    "see metrics-contract.md §3). Missing: "
                    + ", ".join("--tokens-" + m.replace("_", "-") for m in missing_cx)
                    + ". Note: --tokens-cache-write defaults to 0 (Codex CLI drops "
                    "cache_write_tokens; see github.com/openai/codex/issues/32479).")
            if "cache_write" not in given:
                given["cache_write"] = "0"  # explicit 0, not N/A — honest, not missing

        if not args.model:
            _die_usage("--model is required whenever token counts are given — the same "
                       "token count prices 2x apart between a $5/M and a $10/M tier")
        try:
            cost = cost_from_tokens(given, args.model, rate_overrides(args))
        except KeyError as e:
            _die_usage(e.args[0])
        provided["tokens_k"] = tokens_block(given)
        provided["cost"] = cost
        provided["model"] = args.model
```

- [ ] **Step 4: Implement codex branch in cmd_verify**

In `cmd_verify` around line 4576, two changes:

**Change 1** — extend N/A rejection for tokens_k and cost:
```python
        else:  # tokens_k, cost
            if _is_na(val):
                # copilot stores cost=N/A (no class split); that is expected and allowed.
                # Every other strict runtime forbids N/A for both fields.
                copilot_cost_na = (args.runtime == "copilot" and m == "cost")
                if not copilot_cost_na and (
                    args.require_tokens or args.runtime in ("claude", "codex", "copilot")
                ):
                    problems.append(
                        f"actual.{m}=N/A (forbidden under runtime={args.runtime} "
                        f"/ --require-tokens)")
```

**Change 2** — extend scalar rejection to include codex (around line 4630):
```python
    elif "tokens_k" in actual and not _is_na(tk):
        # scalar form — copilot stores this intentionally; all others require the mapping
        if args.require_tokens or args.runtime in ("claude", "codex"):
            problems.append(
                f"actual.tokens_k={tk!r} is not the per-class mapping — cost cannot be "
                f"verified against it. Re-capture with set-actual "
                f"--tokens-input/--tokens-output/--tokens-cache-write/--tokens-cache-read "
                f"and --model (metrics-contract.md §3)")
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest skills/_shared/tests/test-pm-status.py::TestCodexRuntime -v 2>&1 | tail -30
```

Expected: all TestCodexRuntime tests PASS.

- [ ] **Step 6: Run full suite**

```bash
uv run pytest skills/_shared/tests/test-pm-status.py -x -q 2>&1 | tail -20
```

Expected: all tests PASS (no regressions — particularly TestStructuredActualTokens and TestVerifyScalarTokens).

- [ ] **Step 7: Commit**

```bash
git add skills/_shared/pm-status.py skills/_shared/tests/test-pm-status.py
git commit -s -m "feat(l3io-pm): add --runtime codex enforcement with 3-class token capture"
```

---

## Task 3: Implement Copilot enforcement in cmd_set_actual and cmd_verify

**Files:**
- Modify: `skills/_shared/pm-status.py` (cmd_set_actual ~line 3280, cmd_verify ~line 4576)
- Test: `skills/_shared/tests/test-pm-status.py`

**Interfaces:**
- Consumes: argparse choices from Task 1; verify changes from Task 2 (both changes coexist)
- Produces: `--runtime copilot` enforcement used by Task 4 and Task 5

**Copilot enforcement rules:**
- `--tokens-na` → exit 2 (forbidden — must provide a total)
- `--tokens-input` + `--tokens-output` required; cache flags ignored/not required
- `--model` NOT required (no cost derivation)
- Stores `tokens_k` as scalar integer (`input + output`); stores `cost = "N/A"`
- `verify`: scalar tokens_k is valid; cost=N/A is valid (only case where copilot differs from other in verify)
- N/A for tokens_k fails under copilot (see Task 2's verify change — `"copilot"` is in the rejection set for tokens_k but not for cost)

- [ ] **Step 1: Write failing tests**

```python
class TestCopilotRuntime(TestLayoutResolution):
    """T-CP: --runtime copilot enforcement in set-actual and verify."""

    def run_main(self, argv):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code
        return code, buf.getvalue()

    def _set(self, *extra):
        return self.run_main([
            "set-actual", "--state-root", self.root, "--node", "story",
            "--story", "E001-S01-003", "--runtime", "copilot", "--no-calibrate",
            "--elapsed-hours", "2.0", "--man-hours", "8.0", "--hitl-hours", "0.5",
        ] + list(extra))

    def _verify(self):
        return self.run_main([
            "verify", "--state-root", self.root, "--scope", "story",
            "--story", "E001-S01-003", "--runtime", "copilot",
        ])

    def test_tokens_na_forbidden_under_copilot(self):
        code, out = self._set("--tokens-na")
        self.assertEqual(code, 2)
        self.assertIn("copilot", out)

    def test_copilot_requires_input_and_output(self):
        # only input, no output
        code, out = self._set("--tokens-input", "150")
        self.assertEqual(code, 2)
        self.assertIn("--tokens-output", out)

    def test_copilot_stores_scalar_total(self):
        code, out = self._set("--tokens-input", "150", "--tokens-output", "50")
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        tk = node["actual"]["tokens_k"]
        # scalar, not a mapping
        self.assertFalse(hasattr(tk, "get"), f"expected scalar, got mapping: {tk}")
        self.assertEqual(int(tk), 200)  # 150 + 50

    def test_copilot_stores_cost_na(self):
        code, out = self._set("--tokens-input", "150", "--tokens-output", "50")
        self.assertEqual(code, 0, out)
        _, node = pm.load_node(pm.story_file(self.root, "E001-S01-003"))
        self.assertTrue(pm._is_na(node["actual"]["cost"]))

    def test_copilot_model_not_required(self):
        # no --model; should succeed (cost=N/A means no pricing needed)
        code, out = self._set("--tokens-input", "150", "--tokens-output", "50")
        self.assertEqual(code, 0, out)

    def test_verify_passes_with_scalar_tokens_and_na_cost_under_copilot(self):
        # Write a complete done node with scalar tokens_k and cost=N/A, then verify
        f = pm.story_file(self.root, "E001-S01-003")
        _, n = pm.load_node(f)
        n.setdefault("actual", {})
        n["actual"].update({
            "elapsed_hours": 2.0, "man_hours": 8.0, "hitl_hours": 0.5,
            "tokens_k": 200, "cost": "N/A",
        })
        n["status"] = "done"
        n.setdefault("completion_evidence", {})
        import ruamel.yaml
        y = ruamel.yaml.YAML()
        with open(f, "w") as fh:
            y.dump(n, fh)
        code, out = self._verify()
        self.assertEqual(code, 0, out)

    def test_verify_rejects_na_tokens_k_under_copilot(self):
        f = pm.story_file(self.root, "E001-S01-003")
        _, n = pm.load_node(f)
        n.setdefault("actual", {})
        n["actual"].update({
            "elapsed_hours": 2.0, "man_hours": 8.0, "hitl_hours": 0.5,
            "tokens_k": "N/A", "cost": "N/A",
        })
        n["status"] = "done"
        n.setdefault("completion_evidence", {})
        import ruamel.yaml
        y = ruamel.yaml.YAML()
        with open(f, "w") as fh:
            y.dump(n, fh)
        code, _ = self._verify()
        self.assertEqual(code, 4)
```

> Note on node setup: look at how `TestVerifyScalarTokens` in the existing test file writes its nodes — copy that pattern for the verify tests above.

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest skills/_shared/tests/test-pm-status.py::TestCopilotRuntime -v 2>&1 | tail -30
```

Expected: FAIL.

- [ ] **Step 3: Implement copilot branch in cmd_set_actual**

In `skills/_shared/pm-status.py`, in `cmd_set_actual`, add the copilot branch. The copilot path must run **before** the `elif given:` block so it exits before the `--model` requirement fires. Insert after the `if args.tokens_na:` block:

```python
    if args.tokens_na:
        if args.runtime in ("claude", "codex", "copilot"):
            _die_usage(f"runtime={args.runtime} forbids --tokens-na — pass "
                       f"--tokens-input and --tokens-output instead "
                       f"(see metrics-contract.md §3)")
        provided["tokens_k"] = "N/A"
        provided["cost"] = "N/A"
    elif args.runtime == "copilot":
        # Copilot exposes prompt_tokens (input) and completion_tokens (output) only.
        # No cache class split is accessible to the agent, so cost cannot be accurately
        # priced — store the total as a scalar and cost as N/A.
        inp = pm._num_or_none(args.tokens_input)
        out_t = pm._num_or_none(args.tokens_output)
        if inp is None or out_t is None:
            _die_usage(
                "runtime=copilot requires --tokens-input (prompt_tokens) and "
                "--tokens-output (completion_tokens) — read these from each API "
                "response's usage object and sum across the node's dispatch window "
                "(see metrics-contract.md §3). --tokens-na is forbidden.")
        total = inp + out_t
        provided["tokens_k"] = int(total) if float(total).is_integer() else round(total, 2)
        provided["cost"] = "N/A"  # no class split → cannot price accurately
    elif given:
        # ... existing claude + codex handling ...
```

Note: `_num_or_none` is already defined in the module. Call it as `pm._num_or_none` is only valid in tests — in the module itself it is just `_num_or_none(args.tokens_input)`.

- [ ] **Step 4: Run tests**

```bash
uv run pytest skills/_shared/tests/test-pm-status.py::TestCopilotRuntime -v 2>&1 | tail -30
```

The verify tests may still fail if Task 2's verify changes haven't been made yet (they handle N/A rejection for copilot tokens_k). If Task 2 is complete, all tests should pass. If Task 2 isn't complete, implement the two verify changes from Task 2 Step 4 now.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest skills/_shared/tests/test-pm-status.py -x -q 2>&1 | tail -20
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add skills/_shared/pm-status.py skills/_shared/tests/test-pm-status.py
git commit -s -m "feat(l3io-pm): add --runtime copilot enforcement with scalar token capture"
```

---

## Task 4: Update step-00-activate.md runtime detection

**Files:**
- Modify: `skills/_shared/steps/shared/step-00-activate.md`
- Auto-synced to: `skills/l3io-pm-execute/steps/shared/step-00-activate.md`, `skills/l3io-pm-plan/steps/shared/step-00-activate.md`, `skills/l3io-pm-sync/steps/shared/step-00-activate.md`

**Interfaces:**
- Consumes: enforcement contract from Tasks 2 and 3
- Produces: `{runtime}` binding used by all step files that call `set-actual` and `verify`

The current text around line 92–104 says to bind `claude` or `other`. Replace the detection section with logic that covers all four named values.

- [ ] **Step 1: Read the current detection section**

```bash
sed -n '88,110p' /mnt/source/git/l3io/bmad/bmad-extensions/skills/_shared/steps/shared/step-00-activate.md
```

- [ ] **Step 2: Replace the runtime detection section**

Replace the current `Bind {runtime}` paragraph (lines ~92–104 in `skills/_shared/steps/shared/step-00-activate.md`) with:

```markdown
Bind `{runtime}` — passed as `--runtime` to every `set-actual` and `verify` call
(`references/metrics-contract.md` §3). The value must be **exactly** one of `claude`,
`codex`, `copilot`, or `other` — `pm-status.py` rejects anything else with exit 2.
The criterion is a **capability**, not a brand check: choose the value whose token capture
procedure you can actually execute.

**Detection procedure:**

1. **`claude`** — bind when `$CLAUDE_CODE_SESSION_ID` is set in the environment. This is the
   Claude Code session identifier; its presence means the `pm-status.py usage` subcommand can
   read the session transcript to extract exact per-class token counts.

2. **`codex`** — bind when running inside Codex CLI and session JSONL files are available at
   `~/.codex/sessions/`. Confirmation: `ls ~/.codex/sessions/ 2>/dev/null | head -1` returns a
   session directory. Token capture reads `token_count` events from `rollout-*.jsonl`; sum
   `input_tokens`, `output_tokens` + `reasoning_output_tokens` (folded into output),
   and `cached_input_tokens` (→ `cache_read`); `cache_write` is `0` (Codex CLI drops this
   field — see metrics-contract.md §3).

3. **`copilot`** — bind when running inside a GitHub Copilot agent session (VS Code Copilot
   extension or Copilot Cloud Agent) where `$CLAUDE_CODE_SESSION_ID` is absent and Codex CLI
   session files are not present. Token capture sums `usage.prompt_tokens` (→ input) and
   `usage.completion_tokens` (→ output) across every API response in the node's dispatch
   window. No cache split is accessible; cost is recorded as N/A.

4. **`other`** — bind in all other cases, including when token data is genuinely not observable.
   Tokens and cost are recorded as N/A; `man_hours`, `hitl_hours`, and `elapsed_hours` are
   still required as real numbers.

**Default to `other` when uncertain** — it is the permissive value, allowing N/A for
tokens/cost. Guessing `claude` without transcript access, or `codex` without readable session
files, would either block every write (exit 2 on `--tokens-na`) or invite a fabricated number,
and both are worse than an honest N/A.
```

- [ ] **Step 3: Run the sync to propagate the change**

```bash
cd /mnt/source/git/l3io/bmad/bmad-extensions && npm run sync:scripts 2>&1 | tail -20
```

- [ ] **Step 4: Verify all per-skill copies updated**

```bash
npm run check:scripts 2>&1 | tail -10
```

Expected: no drift reported.

- [ ] **Step 5: Commit**

```bash
git add skills/_shared/steps/shared/step-00-activate.md \
        skills/l3io-pm-execute/steps/shared/step-00-activate.md \
        skills/l3io-pm-plan/steps/shared/step-00-activate.md \
        skills/l3io-pm-sync/steps/shared/step-00-activate.md
git commit -s -m "feat(l3io-pm): extend runtime detection to codex and copilot in step-00-activate"
```

---

## Task 5: Update metrics-contract.md §3 for all four runtimes

**Files:**
- Modify: `skills/_shared/metrics-contract.md` (§3, lines ~262–305)
- Auto-synced to: per-skill `references/metrics-contract.md` in pm-execute, pm-plan, pm-sync

- [ ] **Step 1: Read the current §3**

```bash
sed -n '260,310p' /mnt/source/git/l3io/bmad/bmad-extensions/skills/_shared/metrics-contract.md
```

- [ ] **Step 2: Replace §3 with four-runtime version**

Replace the entire `## 3. Runtime detection and capture` section with:

```markdown
## 3. Runtime detection and capture

Four runtimes are recognized: `claude`, `codex`, `copilot`, and `other`. Every
metric-writing call takes `--runtime {claude,codex,copilot,other}`, and it
**defaults to `other`** — the permissive value. Bind `{runtime}` at activation
(`step-00-activate.md` §2) and pass it explicitly on every `set-actual` and `verify`
call; relying on the default silently disables all strict paths.

### Under `--runtime claude`

`elapsed_hours`, `man_hours`, and `hitl_hours` are always real numbers. Tokens are captured
**exactly**: run `pm-status.py usage` scoped to the node's dispatch window; it prints the
four per-class totals and the exact `--tokens-*` flags to paste into `set-actual`. Pass
`--tokens-input`/`--tokens-output`/`--tokens-cache-write`/`--tokens-cache-read` and
`--model`. All four classes are required when any is given; `--tokens-na` is **forbidden**.
`set-actual` derives `tokens_k` (the full mapping) and `cost`. See §3 "Do not read the usage
fields by hand — run `usage`" for the deduplication pitfalls.

### Under `--runtime codex`

Codex CLI logs `token_count` events in `~/.codex/sessions/<session>/rollout-*.jsonl`. Each
event carries `input_tokens`, `output_tokens`, `cached_input_tokens`, and
`reasoning_output_tokens`. Capture procedure:

1. Identify the session directory corresponding to the node's dispatch window (use the
   timestamps in `events.jsonl` as the boundary).
2. Parse all `token_count` events in the window. Sum across events:
   - `input_tokens` → `--tokens-input`
   - `output_tokens + reasoning_output_tokens` → `--tokens-output` (fold reasoning in)
   - `cached_input_tokens` → `--tokens-cache-read`
   - `cache_write` → `0` (Codex CLI currently drops `cache_write_tokens`; pass `0` explicitly
     — honest, not missing. See github.com/openai/codex/issues/32479. When Codex fixes this,
     pass the real value instead.)
3. Pass `--model <codex-model-id>` (e.g. `codex-1`). `set-actual` derives `tokens_k` and
   `cost`. `--tokens-na` is **forbidden**.

`verify --runtime codex` requires the full 4-class mapping (scalar fails) and rejects N/A for
both `tokens_k` and `cost`.

### Under `--runtime copilot`

Every Copilot API response includes a `usage` object:
```json
{"usage": {"prompt_tokens": 1024, "completion_tokens": 256, "total_tokens": 1280}}
```

Capture procedure:
1. Across all API responses within the node's dispatch window (use `events.jsonl` timestamps
   as the boundary), sum `usage.prompt_tokens` → input total and
   `usage.completion_tokens` → output total.
2. Pass `--tokens-input <sum> --tokens-output <sum>` to `set-actual`. No `--model` required.
3. `set-actual` stores `tokens_k` as a scalar (`input + output`) and `cost` as N/A — no cache
   class split is accessible, so accurate pricing is not possible.
4. `--tokens-na` is **forbidden** — you must provide the totals you observed.

`verify --runtime copilot` accepts the scalar `tokens_k` and accepts `cost=N/A`. It rejects
`tokens_k=N/A`.

### Under `--runtime other`

Capture whatever the runtime exposes. If tokens are genuinely not observable, pass
`--tokens-na`, which records both `tokens_k` and `cost` as the literal string `N/A`.
`--tokens-na` cannot be combined with any explicit `--tokens-*` count.

**Never estimate, extrapolate, or back-calculate a token or cost actual.** A guessed actual
is worse than a missing one: `N/A` is skipped by calibration, whereas a guess is
indistinguishable from a measurement and permanently corrupts the learned ratio. `man_hours`
and `hitl_hours` are always observable/assessable and must always be real numbers, on every
runtime.

### Do not read the usage fields by hand — run `usage`

[Keep the existing subsection "Do not read the usage fields by hand..." unchanged]
```

- [ ] **Step 3: Sync and check**

```bash
npm run sync:scripts && npm run check:scripts 2>&1 | tail -15
```

- [ ] **Step 4: Run docs check**

```bash
npm run check:docs 2>&1 | tail -15
```

Fix any check failures before committing.

- [ ] **Step 5: Commit**

```bash
git add skills/_shared/metrics-contract.md \
        skills/l3io-pm-execute/references/metrics-contract.md \
        skills/l3io-pm-plan/references/metrics-contract.md \
        skills/l3io-pm-sync/references/metrics-contract.md
git commit -s -m "docs(l3io-pm): document codex and copilot capture procedures in metrics-contract §3"
```

---

## Task 6: Write docs/estimation-guide.md

**Files:**
- Create: `docs/estimation-guide.md`

This is a **user-facing** guide — written for a developer or tech lead who wants to understand how l3io-pm tracks and learns from project effort, not for AI agents running a sprint. It cross-references `metrics-contract.md` for agent-level detail.

- [ ] **Step 1: Create the file**

Write `docs/estimation-guide.md` with the following structure and content:

```markdown
# Estimation Guide

l3io-pm records five effort metrics at story, sprint, and epic level. Over time it learns
from plan-vs-actual comparisons and self-calibrates future estimates. This guide explains
what each metric means, how estimates are built, how actuals are captured (per AI harness),
and how to read calibration data.

**Agent reference:** `references/metrics-contract.md` is the deep contract used by AI agents.
This guide is the human-readable companion.

---

## The five metrics

| Metric | Meaning | Unit | Always observable? |
|---|---|---|---|
| `elapsed_hours` | AI wall-clock time for this node | hours | Yes |
| `man_hours` | **Counterfactual** — what a human developer would have taken to deliver the same scope | hours | No — assessed at closure |
| `hitl_hours` | Human supervisory attention (reading output, approving gates, redirecting) | hours | Yes |
| `tokens_k` | Tokens consumed — shape varies by harness (see below) | thousands (K) | Harness-dependent |
| `cost` | Billed cost — derived from tokens, never entered directly | USD | When tokens are known |

`man_hours` is the most valuable metric for calibration: it lets the system learn how much
real developer effort a story represents, independent of AI speed. It is **not** a record of
how long the AI ran — that is `elapsed_hours`. Assess it at closure by reviewing the
delivered diff, tests, and scope, before looking at the estimate (to avoid anchoring).

`cost` is always computed from `tokens_k × per-class rates` and frozen on the node. You
cannot enter it directly — `pm-status.py` rejects `--cost` outright.

---

## How estimates are built

Estimates flow **bottom-up**:

```
story.estimate   = base_band(classification) × scope_ratio × fix_factor
sprint.estimate  = Σ story.estimate + closure band + orchestration band
epic.estimate    = Σ sprint.estimate + closure band + orchestration band
```

**Classifications:** `simple`, `standard`, `complex` — you choose one per story.
**Base bands** (cold-start, before calibration):

| | man_hours | hitl_hours | elapsed_hours | tokens_k (fresh) |
|---|---|---|---|---|
| simple | 2–4 h | 0.1–0.3 h | 0.5–1.5 h | 20–50 K |
| standard | 4–8 h | 0.2–0.5 h | 1–3 h | 40–100 K |
| complex | 8–16 h | 0.3–1.0 h | 2–6 h | 80–200 K |

Run `pm-status.py estimate-story --story KEY --classification standard` to get an estimate
written to the state file automatically (including cost, fix reserve, and any active
calibration ratios).

---

## Calibration — how estimates improve

After each story closeout, `pm-status.py` compares the estimate to the actual and updates
four learnable components:

| Component | What it learns | Activates after |
|---|---|---|
| `scope` | How accurate the base band is for each classification | ≥3 closes per class |
| `closure` | How much extra work sprint/epic closure phases add | ≥3 closes |
| `fix` | How often stories need rework (clean vs reworked cohorts) | ≥3 in each cohort |
| `orchestration` | What fraction of children's cost is orchestrator overhead | ≥3 closes |

View current calibration:

```bash
python3 _bmad/scripts/pm-status.py calibration show --state-root <state-root>
```

A component shows `(cold-start)` until it has enough samples. Once active, it replaces the
cold-start prior automatically — no configuration needed.

**Tokens and cost calibrate only on Claude runs.** On Codex, calibration works for
`man_hours`, `hitl_hours`, and `elapsed_hours` but skips `tokens_k` (different harness,
different token economics). On Copilot, same — plus the scalar `tokens_k` has no class split
for the calibration model to use. Cross-harness projects accumulate separate calibration
signals for hours-based metrics and fall back to cold-start for tokens.

---

## Capturing actuals per harness

All actuals go through `pm-status.py set-actual --runtime <value>`. The runtime value
determines what is required and what is enforced.

### Claude Code (`--runtime claude`)

Token counts are read exactly from the session transcript. Use the `usage` subcommand — it
handles deduplication, scoping to the node's dispatch window, and sidechain turn inclusion:

```bash
python3 _bmad/scripts/pm-status.py usage \
  --state-root <state-root> --story E001-S01-003 --model claude-sonnet-5
```

It prints the exact `--tokens-*` flags to paste into `set-actual`. Do not sum usage fields
by hand — the transcript format has three known traps that partly cancel each other, making
the result look plausible while being wrong.

### Codex CLI (`--runtime codex`)

Session files live at `~/.codex/sessions/<session>/rollout-*.jsonl`. Each file contains
`token_count` events. Sum across events in the node's dispatch window:

- `input_tokens` → `--tokens-input`
- `output_tokens + reasoning_output_tokens` → `--tokens-output`
- `cached_input_tokens` → `--tokens-cache-read`
- `cache_write` → `--tokens-cache-write 0` (Codex CLI drops this field — explicit 0 is honest)

```bash
python3 _bmad/scripts/pm-status.py set-actual \
  --state-root <state-root> --node story --story E001-S01-003 \
  --runtime codex \
  --elapsed-hours 2.1 --man-hours 8.0 --hitl-hours 0.4 \
  --tokens-input 120 --tokens-output 25 --tokens-cache-write 0 --tokens-cache-read 310 \
  --model codex-1
```

Cost is derived from the three known classes. The `cache_write=0` means cost is slightly
understated until Codex CLI fixes the dropped field.

### GitHub Copilot (`--runtime copilot`)

Every Copilot API response includes `usage.prompt_tokens` and `usage.completion_tokens`. Sum
both across all responses in the node's dispatch window:

```bash
python3 _bmad/scripts/pm-status.py set-actual \
  --state-root <state-root> --node story --story E001-S01-003 \
  --runtime copilot \
  --elapsed-hours 2.1 --man-hours 8.0 --hitl-hours 0.4 \
  --tokens-input 1280 --tokens-output 310
```

No `--model` required — cost is recorded as N/A because no cache class split is available for
accurate pricing. `tokens_k` is stored as a scalar total (`prompt_tokens + completion_tokens`).

### Other runtimes (`--runtime other`)

Pass `--tokens-na` when tokens are not observable:

```bash
python3 _bmad/scripts/pm-status.py set-actual \
  --state-root <state-root> --node story --story E001-S01-003 \
  --runtime other \
  --elapsed-hours 2.1 --man-hours 8.0 --hitl-hours 0.4 \
  --tokens-na
```

`man_hours` and `hitl_hours` are always required as real numbers — there is no N/A path for
either, on any runtime.

---

## Reading the progress report

```bash
python3 _bmad/scripts/pm-status.py report --state-root <state-root> --format tree
```

Columns: `status`, `estimate`, `actual`, `Δ` (delta, negative = under estimate),
`man_hours`, `hitl_hours`, `tokens_k`, `cost`. Tokens show as `N/A` for non-Claude runs
until calibration has enough cross-harness data.

---

## FAQ

**Why can't I set cost directly?**
Cost is derived from `tokens_k × per-model rates` at write time and frozen. A hand-entered
cost has no arithmetic relationship to the tokens it supposedly prices — it would drift as
rates change and silently corrupt any cost-based analysis. `set-actual --cost` exits with
error 2.

**Why is tokens_k N/A for some stories?**
Those stories ran on a runtime other than Claude or Codex where token data is not exposed
(e.g. `--runtime other`). The hours-based metrics still calibrate normally.

**Why does my Codex estimate look low on cost?**
Codex CLI currently drops `cache_write_tokens` from its rollout JSONL files. The cost
calculation uses `cache_write=0`, which understates the true cost by the cache-write billing
for that node. This is a known Codex CLI bug (github.com/openai/codex/issues/32479); once
fixed, pass the real value and cost will be accurate.

**How do I add a model whose rates aren't in the built-in table?**
Add it to `modules.l3io-pm.token_rates` in your project's `custom/config.toml`:
```toml
[modules.l3io-pm.token_rates.my-model]
input = 3.00
output = 15.00
cache_write = 3.75
cache_read = 0.30
```
Run `pm-status.py rates --model my-model` to confirm the effective rates.

**How do I see what calibration ratios are active?**
```bash
python3 _bmad/scripts/pm-status.py calibration show --state-root <state-root>
```
Active ratios show a value; inactive ones show `(cold-start, N samples)`.
```

- [ ] **Step 2: Verify the file renders correctly**

```bash
# Quick check: all section headings are present
grep "^##" /mnt/source/git/l3io/bmad/bmad-extensions/docs/estimation-guide.md
```

Expected output includes: `## The five metrics`, `## How estimates are built`, `## Calibration`, `## Capturing actuals per harness`, `## Reading the progress report`, `## FAQ`

- [ ] **Step 3: Run check:docs to ensure no new failures**

```bash
npm run check:docs 2>&1 | tail -15
```

Expected: same pass/fail as before (the new file adds no cross-references that check:docs validates).

- [ ] **Step 4: Commit**

```bash
git add docs/estimation-guide.md
git commit -s -m "docs(l3io-pm): add estimation-guide.md covering all four runtimes"
```

---

## Task 7: Sync, manifest regeneration, and CI validation

**Files:**
- Auto-updated: all per-skill `scripts/pm-status.py`, `steps/`, `references/`
- Auto-updated: all `payload-manifest.json` files

- [ ] **Step 1: Run full sync**

```bash
cd /mnt/source/git/l3io/bmad/bmad-extensions && npm run sync:scripts 2>&1 | tail -20
```

Expected: all per-skill copies updated to match `skills/_shared/`.

- [ ] **Step 2: Regenerate all manifests**

```bash
node scripts/write-payload-manifest.mjs 2>&1 | tail -20
```

- [ ] **Step 3: Run all CI checks**

```bash
npm run check:scripts && npm run check:manifest && npm run check:docs && npm run check:version
```

Each must pass with no errors. Fix anything that fails before continuing.

- [ ] **Step 4: Run the full test suite one final time**

```bash
uv run pytest skills/_shared/tests/test-pm-status.py -q 2>&1 | tail -20
```

Expected: all tests PASS.

- [ ] **Step 5: Stage and commit all generated files**

```bash
git add skills/ docs/
git status  # review — should be only pm-status.py copies, step copies, reference copies, manifests
git commit -s -m "chore(l3io-pm): sync shared scripts and regenerate manifests for multi-runtime support"
```

---

## Self-Review

**Spec coverage:**
- [x] Named runtimes `codex` and `copilot` added to argparse choices — Task 1
- [x] `codex` enforcement: forbids N/A, requires input+output+cache_read, cache_write=0 default, derives cost — Task 2
- [x] `copilot` enforcement: forbids N/A, requires input+output, scalar storage, cost=N/A — Task 3
- [x] `verify` updated: scalar fails under claude/codex, passes under copilot/other; N/A rules per runtime — Tasks 2, 3
- [x] OpenAI rates added to TOKEN_RATES — Task 1
- [x] step-00-activate.md updated with 4-way detection logic — Task 4
- [x] metrics-contract.md §3 updated with per-harness capture procedures — Task 5
- [x] User-facing estimation-guide.md created — Task 6
- [x] Sync + manifest + CI — Task 7
- [x] `reasoning_output_tokens` folded into `output_tokens` (documented in Tasks 2, 5, 6; enforced by the agent following the step instructions)

**Known gaps / follow-up items (not in this plan):**
- `pm-status.py usage --runtime codex` subcommand to read rollout JSONL automatically (parallel to the Claude path) — deferred; Codex session scoping is not yet well-defined
- Copilot: no session-file equivalent, so dispatch-window scoping requires manual tracking of per-request usage during the session — documenting the procedure (done in Task 6) is the correct first step
- Rate verification: the TOKEN_RATES values for OpenAI models should be confirmed against https://openai.com/api/pricing before the Task 1 commit; rates are overridable via `modules.l3io-pm.token_rates` if they change
