# Estimation Guide

**Audience:** Engineers using l3io-pm across any AI harness — Claude Code, Codex CLI, GitHub Copilot, or any other runtime.

This guide covers what you need to record metrics accurately: which numbers the system tracks, how to capture them on each harness, the rules around N/A, and how cost is derived. For the full enforcement contract and the calibration model, see `references/metrics-contract.md` in each PM skill.

---

## The five metrics

Every story, sprint, and epic node records both an `estimate` block and an `actual` block. Each block covers exactly five metrics, in this order:

| Metric | What it measures | Unit | Can be N/A? |
|---|---|---|---|
| `elapsed_hours` | AI wall-clock time from dispatch to completion | hours | Never |
| `man_hours` | **Counterfactual** — what a human developer, working without AI, would have needed to deliver this diff and tests | hours | Never |
| `hitl_hours` | Human supervisory attention actually spent on the run | hours | Never |
| `tokens_k` | Tokens consumed (a per-class mapping or scalar; see §Runtime) | thousands (K) | Only under `--runtime other` |
| `cost` | Billed cost for those tokens | USD | Derived, never entered |

**`man_hours` is a re-assessment, not an observation.** At closeout, review the delivered diff and scope and form an independent estimate of the developer-hours it would have taken — before reading the node's own estimate. It is not how long the AI ran (that is `elapsed_hours`), and it is not derived from any formula.

**`cost` is always derived from `tokens_k × the rate table` and stored.** There is no flag to set it directly — the CLI rejects `--cost`, `--cost-low`, and `--cost-high` with exit 2. If the rate table does not match your project's negotiated rates, override it via `modules.l3io-pm.token_rates` in your config (see `references/config-resolution.md` §3).

---

## Detecting your runtime

`step-00-activate.md` §2 binds `{runtime}` at activation. The value is **capability-based** — it determines which token capture procedure you can actually execute, not which brand you are using.

Detection runs in priority order:

1. **`claude`** — `$CLAUDE_CODE_SESSION_ID` is set in the environment. The `pm-status.py usage` subcommand can read the session transcript to extract exact per-class token counts.

2. **`codex`** — Running inside Codex CLI, with session JSONL files available at `~/.codex/sessions/`. Confirmed by: `ls ~/.codex/sessions/ 2>/dev/null | head -1` returns a session directory.

3. **`copilot`** — Running inside a GitHub Copilot agent session (VS Code Copilot extension or Copilot Cloud Agent) where neither Claude Code session ID nor Codex session files are present.

4. **`other`** — All other cases, including when token data is genuinely not observable.

**Default to `other` when uncertain.** It is the permissive value. Guessing `claude` without transcript access would block every write (exit 2 on `--tokens-na`). Guessing `codex` without readable session files invites a fabricated number. An honest `N/A` is better than either.

The bound `{runtime}` value is passed as `--runtime` on every `set-actual` and `verify` call. Omitting it silently uses the `other` default and disables the strict enforcement path — pass it explicitly on every call.

---

## Per-runtime capture procedures

### Claude (`--runtime claude`)

Tokens are captured **exactly** from the session transcript. Use the `pm-status.py usage` helper — it handles deduplication, transcript identity verification, and subagent turn aggregation automatically:

```bash
# Read the token counts for a story's own dispatch window
python3 {pm_status} usage \
  --state-root {pm_state_root} --story {story_key} --model {model}

# For a sprint or an explicit time window
python3 {pm_status} usage \
  --state-root {pm_state_root} --epic {epic_key} --sprint {sprint_num} --model {model}
```

The helper prints the four per-class totals and the exact `--tokens-*` flags to paste into `set-actual`. **Do not sum the raw transcript by hand** — a streaming transcript holds multiple records per message (inflating by ~2.6×), carries `cache_creation_input_tokens` in two forms (double-counting if both are summed), and omits subagent turns (which live in separate sidechain files). The helper avoids all three traps.

**All four token classes are required** — pass an explicit `0` for any class that is genuinely zero. Passing fewer than four is a usage error (exit 2). Passing `--tokens-na` is forbidden (exit 2).

### Codex (`--runtime codex`)

Tokens are read from session event logs at `~/.codex/sessions/**/rollout-*.jsonl`. Find the `token_count` events that fall inside the node's dispatch window and extract:

- `input_tokens` → `--tokens-input`
- `output_tokens` + `reasoning_output_tokens` (fold reasoning into output) → `--tokens-output`
- `cached_input_tokens` → `--tokens-cache-read`
- `cache_write_tokens` is not exposed by Codex CLI — **always pass `0`** for `--tokens-cache-write`, or omit the flag entirely (the CLI defaults it to 0)

**Three token flags are required** (`input`, `output`, `cache_read`). Passing `--tokens-na` is forbidden (exit 2). `--model` is required so cost can be derived from the three classes.

Cost is derived and stored normally; `tokens_k` is written as the full four-class mapping with `cache_write: 0`.

### Copilot (`--runtime copilot`)

Tokens are observable per request, but no per-class split is available. Aggregate `usage.prompt_tokens` and `usage.completion_tokens` across every API response that falls inside the node's dispatch window:

- Sum of `usage.prompt_tokens` → `--tokens-input`
- Sum of `usage.completion_tokens` → `--tokens-output`

`--tokens-na` is forbidden (exit 2). `--model` is NOT required — because no per-class split is available, cost cannot be accurately priced and is recorded as `N/A` instead.

`tokens_k` is stored as a scalar integer (`input + output`). The cache classes are not recorded. This scalar form is valid for `verify` under `--runtime copilot` (it is the expected shape).

### Other (`--runtime other`)

Capture whatever the runtime exposes. If token information is not available or not applicable, pass `--tokens-na` — this records both `tokens_k` and `cost` as the literal string `N/A` and satisfies `verify`.

`--tokens-na` cannot be combined with any explicit `--tokens-*` count flag; pick one or the other.

`man_hours`, `hitl_hours`, and `elapsed_hours` are still required as real numbers on every runtime — there is no N/A for these three.

---

## Writing actuals: set-actual examples

### Claude

```bash
# 1. Get the token counts from the session transcript
python3 {pm_status} usage \
  --state-root {pm_state_root} --story E001-S01-003 --model {model}
# Prints: --tokens-input 122 --tokens-output 41 --tokens-cache-write 244 --tokens-cache-read 405

# 2. Write the actual (paste the --tokens-* flags from usage output)
python3 {pm_status} set-actual \
  --state-root {pm_state_root} \
  --node story --story E001-S01-003 \
  --runtime claude \
  --elapsed-hours 3.2 --man-hours 15 --hitl-hours 1.8 \
  --tokens-input 122 --tokens-output 41 --tokens-cache-write 244 --tokens-cache-read 405 \
  --model {model}

# 3. Set status and verify
python3 {pm_status} set-status \
  --state-root {pm_state_root} --story E001-S01-003 --status done
python3 {pm_status} verify \
  --state-root {pm_state_root} --scope story --story E001-S01-003 --runtime claude
```

### Codex

```bash
# Sum token_count events from rollout-*.jsonl, then:
python3 {pm_status} set-actual \
  --state-root {pm_state_root} \
  --node story --story E001-S01-003 \
  --runtime codex \
  --elapsed-hours 2.5 --man-hours 10 --hitl-hours 0.6 \
  --tokens-input 100 --tokens-output 20 --tokens-cache-read 300 \
  --model gpt-5.6-terra

# verify
python3 {pm_status} verify \
  --state-root {pm_state_root} --scope story --story E001-S01-003 --runtime codex
```

Note: `--tokens-cache-write` is omitted — the CLI defaults it to `0`. Passing it explicitly as `0` is also correct.

### Copilot

```bash
# Sum prompt_tokens / completion_tokens from API responses in the dispatch window, then:
python3 {pm_status} set-actual \
  --state-root {pm_state_root} \
  --node story --story E001-S01-003 \
  --runtime copilot \
  --elapsed-hours 1.8 --man-hours 8 --hitl-hours 0.5 \
  --tokens-input 150 --tokens-output 50

# verify (cost=N/A and scalar tokens_k are expected and valid here)
python3 {pm_status} verify \
  --state-root {pm_state_root} --scope story --story E001-S01-003 --runtime copilot
```

Note: no `--model` flag — Copilot stores `cost: N/A` so no pricing is needed.

### Other (tokens not available)

```bash
python3 {pm_status} set-actual \
  --state-root {pm_state_root} \
  --node story --story E001-S01-003 \
  --runtime other \
  --elapsed-hours 2.0 --man-hours 6 --hitl-hours 0.3 \
  --tokens-na

python3 {pm_status} verify \
  --state-root {pm_state_root} --scope story --story E001-S01-003 --runtime other
```

### Sprint and epic orchestration block

The orchestrator's own coordination overhead (dispatching subagents, waiting on them) goes into a separate `--block orchestration` on the parent node. This applies to sprint and epic nodes only — not to stories.

```bash
python3 {pm_status} set-actual \
  --state-root {pm_state_root} \
  --node sprint --epic E001 --sprint S01 \
  --block orchestration \
  --runtime claude \
  --elapsed-hours 0.6 --man-hours 0 --hitl-hours 0.1 \
  --tokens-input 14 --tokens-output 5 --tokens-cache-write 27 --tokens-cache-read 44 \
  --model {model}
```

`--man-hours 0` is always correct for the orchestration block — it is AI-only overhead with no human-developer counterfactual.

---

## N/A: when it is allowed and when it is forbidden

| Context | N/A allowed? |
|---|---|
| `tokens_k` under `--runtime claude` | No — exit 2 |
| `tokens_k` under `--runtime codex` | No — exit 2 |
| `tokens_k` under `--runtime copilot` | No — exit 2 (tokens must be provided as `input + output`) |
| `tokens_k` under `--runtime other` | Yes — via `--tokens-na` |
| `cost` under `--runtime copilot` | Yes — automatically stored as N/A (no class split available) |
| `cost` under any other runtime | N/A only if `tokens_k` is also N/A (the `--runtime other` path) |
| `man_hours` | Never — assessed at closure on every runtime |
| `hitl_hours` | Never — observed on every runtime |
| `elapsed_hours` | Never — observed on every runtime |

`verify` checks these rules at read-back. Under `--runtime claude`, it also checks that `tokens_k` is the full four-class mapping (not a scalar), and that `cost` matches what `tokens_k × rate_table` prices out to within $0.005.

An **absent** field is not the same as N/A. Absence fails `verify`; an explicit N/A string passes it under the permissive runtimes.

---

## Cost derivation

Cost is derived inside `set-actual`, `estimate-story`, and `estimate-rollup` from `tokens_k × the per-model, per-class rate table`. It is never entered directly.

The rate table (`TOKEN_RATES` in `pm-status.py`) holds per-class USD-per-million-token rates for Anthropic Claude models and OpenAI Codex/GPT models. To inspect what is in force for your project:

```bash
python3 {pm_status} rates [--model MODEL] [--token-rates JSON]
```

If your project negotiates different rates, set `modules.l3io-pm.token_rates` in `_bmad/custom/config.toml` (see `references/config-resolution.md` §3). Pass `--model` on every `set-actual` call that carries token counts — the same token volume prices ~2× apart between a $3/M and a $10/M input tier.

**Never pass `--cost` or `--cost-low` / `--cost-high`.** The CLI rejects these flags with exit 2. If a stored cost looks wrong, re-derive it by fixing the `tokens_k` values or the rate table override, then re-running `set-actual` (it is replay-guarded, so add `--no-calibrate` if the calibration sample was already emitted and a re-derive is all that is needed).

---

## Cross-runtime planning

A project planned on one runtime and executed on another works correctly at the data level — each node stores its own `estimate.model` and `actual.model` independently, and `verify` always prices against the actual's model. However, estimate costs and actual costs are denominated in different rate tables and are not directly comparable.

**What you will see when models differ:**

`set-actual` appends a note to its OK line:
```
OK set-actual E001-S01-003 [...] [model mismatch: estimated at 'claude-opus-5', executed at 'gpt-5.6-terra' — costs not comparable]
```

`verify` emits a WARN line before PASS/FAIL (exit code unchanged):
```
WARN E001-S01-003: estimate.model='claude-opus-5' ≠ actual.model='gpt-5.6-terra' — estimate cost denominated in claude-opus-5 rates
```

Neither blocks the write or changes the outcome — both are informational.

**Calibration impact.** Token and cost calibration samples are skipped when values are `N/A` (Copilot, `--runtime other`). When two runtimes both produce real token counts (e.g. Claude and Codex), scope-metric buckets collect samples from both; `calibration show` warns when this mixing is detected:

```
WARN: scope calibration contains mixed-model samples — ratios may be unreliable.
Consider `calibration redrive` after settling on one model:
  standard/elapsed_hours (claude-opus-5, gpt-5.6-terra)
```

If a project switches runtimes mid-stream, run `calibration redrive` once the new runtime is established to rebuild scope and fix ratios from story nodes — closure and token_mix are unaffected by redrive.

**`man_hours` and `hitl_hours` calibrate normally on every runtime** and are not affected by model mismatch.

## Calibration overview

Every successful `set-actual` call derives a plan-vs-actual sample and appends it to `{implementation_artifacts}/state/pm-calibration.yaml`. After three samples in a component and classification, the system activates that component's learned ratio and applies it to future estimates automatically.

Four components are learned, each per metric:

- **scope** — story sizing accuracy, per classification (simple / standard / complex)
- **closure** — sprint- and epic-level closure-phase overhead
- **fix** — cost of the fix loop (requires both `clean` and `reworked` cohorts at ≥3 samples each)
- **orchestration** — orchestrator coordination overhead as a fraction of children's actuals

`cost` is never calibrated — it is always derived from the calibrated `tokens_k`, so a second learned copy could only disagree with the tokens it prices.

The calibration file is committed and shared across parallel subagents; every write takes a file lock. To inspect current calibration state:

```bash
python3 {pm_status} calibration show --state-root {pm_state_root}
```

**Full calibration model:** `references/calibration-model.md`

---

## Full contract

This guide covers the user-facing procedures. For the enforcement contract (what `set-actual` and `verify` check, exit codes, the worked example, the roll-up formula, and every edge case), see:

```
references/metrics-contract.md
```

Sections of interest:

| Question | Section |
|---|---|
| Token/cost capture detail for a specific runtime | §3 |
| Writing an estimate or actual by hand | §4 |
| What `verify` checks and its exit codes | §5 |
| The estimation roll-up formula | §6 |
| The fix reserve and when it deactivates | §7 |
| Explaining a calibration result | §8 |
| Where the code and the docs disagree | §9 |
| Worked example (estimate → actual → calibration sample) | §10 |

`pm-status.py` is the authoritative implementation. Where this guide, `metrics-contract.md`, and the script disagree, the script is correct.
