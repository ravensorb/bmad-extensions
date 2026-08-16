# Metrics Contract (estimates & actuals)

Communicate all responses in `{communication_language}`.

This file is the single source of truth for **which** numbers l3io-pm records, **what they
are called on disk**, **how they are captured**, **where they are enforced**, and **how
estimates learn from them**. Load it at activation alongside `references/status-files.md`
and keep its rules in context for every estimate write and every closeout.

`status-files.md` owns *where state lives*. This file owns *what the numbers in it mean*.

Where this document and `CLAUDE.md` disagree, **this document follows the code**
(`pm-status.py`) and says so explicitly in §9. Anything described here as "specified, not
mechanized" is agent discipline only — no script checks it.

---

## 1. The HARD RULE

**Every planning point and every closeout — at story, sprint, and epic level — records both
an `estimate` block and an `actual` block, and each block covers all four metrics.**

A story, sprint, or epic does not sign off with an estimate block missing, an actual block
missing, or any individual metric missing from either.

Why it exists: estimation only improves if plan-vs-actual is captured at the same
granularity every time. A single skipped closeout does not just lose one data point — it
silently biases every calibration ratio derived from that component, and the bias is
invisible afterwards because there is no record that the sample was ever due. The rule is
therefore absolute rather than best-effort, and it is checked mechanically at write time
and again at read-back (§5).

**Retrospective level.** `CLAUDE.md` states the rule at "story, sprint, epic, and
retrospective" level. There is no retrospective *node* — retrospective data is written onto
the sprint or epic node as `retrospective.summary`, `retrospective.velocity`,
`retrospective.carry_over`, `retrospective.learnings` via `set-field`, and it carries no
metric fields of its own. The retrospective's numbers **are** its sprint's or epic's
`estimate`/`actual` blocks. Do not invent a separate metric block under `retrospective.`.

## 2. The four metrics

| Metric | Meaning | Unit |
|---|---|---|
| Man-hours | Human attention spent — review, direction, unblocking | hours (decimal) |
| Compute hours | AI wall-clock time from dispatch to completion | hours (decimal) |
| Tokens | Total tokens consumed, input + output | thousands (K) |
| Token cost | Billed cost for those tokens | USD (decimal) |

### Field names on disk

The two blocks do **not** use the same field names, and the compute-hours metric is named
differently in each. This is the actual schema — do not normalize it:

```yaml
# story node — estimate is single values
estimate:
  man_hours: 6
  time_hours: 1.5          # compute hours
  tokens_k: 320
  cost: 4.80
  confidence: high         # low | medium | high

# sprint and epic nodes — estimate is low/high ranges
estimate:
  man_hours_low: 12
  man_hours_high: 18
  time_hours_low: 2.5      # compute hours
  time_hours_high: 4
  tokens_k_min: 600
  tokens_k_max: 950
  cost_low: 9.00
  cost_high: 14.25
  confidence: high

# actual — identical at story, sprint, and epic level; always single values
actual:
  elapsed_hours: 3.2       # compute hours — NOT time_hours
  man_hours: 15
  tokens_k: 812
  cost: 12.18
```

`METRIC_FIELDS` in `pm-status.py` is exactly `("elapsed_hours", "man_hours", "tokens_k",
"cost")`. Those four names, in that order, are what `verify` requires and what `show` sums.

**`cost` is written as a string.** `set-actual` coerces `cost` to a single-quoted scalar
regardless of what is passed; `set-estimate` coerces `cost`/`cost_low`/`cost_high` through
`str`. Pass a **bare decimal with no currency symbol** — `--cost 12.18`, never
`--cost '$12.18'`. A `$`-prefixed value is stored without complaint but fails the `float()`
conversion in the roll-up accumulator, so it is silently dropped from every `show` total.
Currency symbols belong in prose reports, never in the state files.

`tokens_k` is stored as an int when the value is integral, otherwise a float.
`elapsed_hours` and `man_hours` are floats.

## 3. Runtime detection and capture

Two runtimes are recognized: `claude` and `other`. Every metric-writing call takes
`--runtime {claude,other}`, and it **defaults to `other`** — the permissive value. Bind
`{runtime}` at activation and pass it explicitly on every `set-actual` and `verify` call;
relying on the default silently disables the strict path.

### Under `--runtime claude`

All four metrics are captured **exactly**. Man-hours and compute hours come from the
orchestrator's own timing of the phase. Tokens and cost are read from the session
transcript's `usage` fields — sum `input_tokens`, `output_tokens`, and the cache
input-token fields across the messages belonging to the node being closed, divide by 1000
for `tokens_k`, and price it for `cost`.

`N/A` is **forbidden** for `tokens_k` and `cost` here. This is the mechanical enforcement
point of the HARD RULE (§5).

### Under `--runtime other`

Capture whatever the runtime exposes. If tokens or cost are genuinely not observable
(e.g. Copilot), write the literal string `N/A`.

**Never estimate, extrapolate, or back-calculate a token or cost actual.** A guessed actual
is worse than a missing one: `N/A` is skipped by calibration, whereas a guess is
indistinguishable from a measurement and permanently corrupts the learned ratio. Man-hours
and compute hours are always observable and must always be real numbers, on every runtime.

Values treated as `N/A` by `_is_na`: `N/A`, `NA`, `NONE`, and the empty string, in any
case, after stripping. An **absent** field is not the same as `N/A` — absence fails
`verify`, an explicit `N/A` passes it under `--runtime other`.

## 4. Writing estimates and actuals

All writes go through `pm-status.py`. Never hand-edit a state file.

```bash
# story estimate — single-value aliases
python3 {pm_status} set-estimate --state-root {pm_state_root} \
  --story E001-S01-003 \
  --man-hours 6 --time-hours 1.5 --tokens-k 320 --cost 4.80 \
  --confidence high

# sprint or epic estimate — ranges
python3 {pm_status} set-estimate --state-root {pm_state_root} \
  --epic E001 [--sprint S01] \
  --man-hours-low 12 --man-hours-high 18 \
  --time-hours-low 2.5 --time-hours-high 4 \
  --tokens-k-min 600 --tokens-k-max 950 \
  --cost-low 9.00 --cost-high 14.25 \
  --confidence high

# actual — same four flags at every level
python3 {pm_status} set-actual --state-root {pm_state_root} \
  --node {story|sprint|epic} (--story KEY | --epic ID [--sprint ID]) \
  --runtime {runtime} \
  --elapsed-hours 3.2 --man-hours 15 --tokens-k 812 --cost 12.18
```

Node kind for `set-estimate` is **inferred** from which selector flags are present
(`--story` → story; `--epic` with or without `--sprint` → sprint/epic). `set-actual` takes
an explicit `--node`.

**Flag/kind mismatches are silently ignored, not rejected.** On a story node the range
flags are dropped; on a sprint or epic node the single-value flags are dropped. `--tokens-k`
and `--cost` share argparse destinations with `--tokens-k-min` and `--cost-low`, so passing
both forms in one call means the last one parsed wins. Use exactly the form that matches
the node kind.

`--confidence` is optional. When omitted and no confidence is already set, it is **derived**:
`medium` if every field for that kind is present, `low` otherwise. It is never derived as
`high` — pass `--confidence high` explicitly when the calibration data justifies it (§8).

Write the actual, the completion evidence, and the status transition as separate calls, then
gate on `verify`. Story closeout additionally requires `completion_evidence` (written via
`set-field`), which `verify --scope story` checks.

## 5. Enforcement — what is actually checked, and where

The HARD RULE is enforced in **two halves**. Neither half alone is sufficient, so both must
run.

### Half 1 — `set-actual`, at write time

Under `--runtime claude`, passing `N/A` (or `NA`/`NONE`/empty) for `--tokens-k` or `--cost`
is a **usage error, exit 2**, with the message:

```
runtime=claude forbids tokens_k=N/A — capture the exact value (see metrics-contract.md)
```

Limits of this check, which the orchestrator must compensate for:

- It only inspects metrics **actually passed**. `set-actual` requires at least one of the
  four flags, not all four — under `--runtime claude`, simply *omitting* `--tokens-k`
  succeeds (exit 0). Always pass all four flags in one call.
- It does not apply to `elapsed_hours` or `man_hours`; those are caught later by `verify`,
  which requires them to be numeric on every runtime.

### Half 2 — `verify`, at read-back

`verify` is the completeness gate. `--scope story` and `--scope sprint` check **completion
of one node**:

- `status == done`
- all four `actual.*` fields **present**
- `elapsed_hours` and `man_hours` numeric and not `N/A`
- `tokens_k` and `cost` may be `N/A` **only** under `--runtime other` and without
  `--require-tokens`; `--runtime claude` or `--require-tokens` makes `N/A` a failure
- `completion_evidence` present (story scope only)

```bash
python3 {pm_status} verify --state-root {pm_state_root} \
  --scope {story|sprint} (--story KEY | --epic ID --sprint ID) \
  --runtime {runtime} [--require-tokens]
```

`--scope epic` is a **different check**: it walks the epic's whole subtree and validates
structural / back-reference integrity (every sprint directory has a `sprint.yaml`; every
sprint and story file carries `epic:`/`sprint:` back-references matching its directory). It
does **not** look at `status`, `estimate`, or `actual` at all. See `status-files.md` §7.

Exit codes (identical across all subcommands):

| Code | Meaning |
|---|---|
| `0` | Success / verified |
| `2` | Usage error — including the `runtime=claude` + `N/A` rejection |
| `3` | Node not found |
| `4` | Verification failure (missing/invalid field, or structural mismatch) |
| `5` | Epic locked by another session |

### What is *not* enforced

- **No machine check on the `estimate` block, ever.** `verify` inspects `actual` only.
  `set-estimate` has no required flags and never fails on an incomplete estimate — it
  records `confidence: low` instead. The estimate half of the HARD RULE is orchestrator
  discipline.
- **No metric check at epic scope.** Because `verify --scope epic` is structural, the
  epic-level actual has no read-back gate. Close an epic by running
  `verify --scope sprint` on every sprint, then writing the epic actual and confirming it
  by reading the node back.
- **No calibration enforcement.** Nothing in `pm-status.py` reads or writes the calibration
  file (§8).

## 6. The estimation roll-up

**Estimates are bottom-up.** Sprint and epic estimates are *defined as* the sum of their
children plus a closure band, so they reconcile with their children by construction. Do not
compute a sprint or epic estimate by any independent formula — parallel formulas drift.

Per metric:

```
story.estimate  = base_band(classification) × scope_ratio × fix_mult
sprint.estimate = Σ story.estimate + calibrated sprint-closure band
epic.estimate   = Σ sprint.estimate  + calibrated epic-closure band
```

### Base bands (cold-start priors, per story)

| Classification | man_hours | time_hours | tokens_k | cost |
|---|---|---|---|---|
| simple | 2–4 | 0.5–1.5 | 20–50 | 0.10–0.35 |
| standard | 4–8 | 1–3 | 40–100 | 0.25–0.70 |
| complex | 8–16 | 2–6 | 80–200 | 0.55–1.40 |

Stories store the band **midpoint** as a single value; ranges appear only at sprint and epic
level.

### Roll-up mechanics

- `man_hours_low/high` = Σ story `man_hours`, ±20% band.
- `time_hours_low/high` = Σ story `time_hours` × `parallel_factor` (default `0.6`), ±20%
  band. Compute hours compress under parallel execution within a sprint; man-hours, tokens,
  and cost do not.
- `tokens_k_min/max` = Σ story `tokens_k`, ±20% band.
- `cost_low/high` = Σ story `cost`, ±20% band.
- Closure band: apply the calibrated `closure` ratio for that level when it has activated;
  otherwise add a flat **15%** at sprint level and **20%** at epic level.

## 7. The fix reserve

`F` (default **1.25**) reserves headroom for the fix loop — the rework a story needs after
code review and QA findings.

**`F` is a cold-start prior only.** It fills the gap before a component has ≥3 calibration
samples. Once the learned ratios activate they already encode observed fix overhead, because
they are measured against actuals that *include* the fix loop.

> **Never stack `F` on top of an activated learned ratio.** Doing so double-counts fixes and
> inflates every downstream estimate. `fix_mult` is `F` **or** the learned factor, never
> their product.

Precisely:

```
fix_mult = F (1.25)                      if the fix component for this classification has <3 samples
fix_mult = calibration.fix.avg_fix_factor if it has ≥3 samples
```

The fix multiplier applies to `man_hours` and `time_hours`. Token and cost bands already
span fix-loop variance, so applying `fix_mult` to them as well over-inflates them.

> Note: `steps/shared/step-estimate.md` §3 reads "Apply calibrated scope ratio if available.
> Apply fix factor…" as two independent sentences. That wording permits stacking. The rule
> above is the contract; read the step file through it.

## 8. Calibration

### Location

| Binding | Resolves to |
|---|---|
| `{pm_calibration_file}` | `{pm_state_root}/pm-calibration.yaml` = `{implementation_artifacts}/state/pm-calibration.yaml` |

The file is **committed**. Learned ratios are team knowledge and expensive to rebuild —
several closed sprints of real work each. It sits beside `issues.yaml` in the state root and
moves nowhere when epics move between `planned/`, `active/`, and `archived/`.

### Three separable components

Each component learns per metric, and each **activates independently** at **≥3 samples**:

| Component | Learns | Sampled at |
|---|---|---|
| `scope` | story sizing ratio, per classification | story close (or sprint close, per granularity) |
| `closure` | closure overhead ratio, separately for sprint and epic level | every sprint close and epic close |
| `fix` | `avg_fix_factor`, per classification | story close (or sprint close, per granularity) |

Splitting them matters because they fail differently: `scope` drifts with codebase
familiarity, `closure` is a near-fixed per-sprint tax that a single blended ratio hides
entirely, and `fix` tracks review strictness. A component with <3 samples uses its
cold-start prior — ratio `1.0` for `scope` and `closure`, `F` = `1.25` for `fix` — while its
siblings may already be calibrated.

### Sample weighting

Samples are **exponentially decay-weighted with decay 0.8** — the most recent sample carries
weight 1, the one before it 0.8, then 0.64, and so on. Recent work is a better predictor
than early-project work, and the decay lets ratios track a changing codebase without any
explicit window or manual reset.

### Token and cost samples

`token` and `cost` ratios accumulate **only from runs with real actuals** — Claude runs. An
`N/A` entry is skipped entirely, never imputed, never counted toward the ≥3 activation
threshold. A project run mostly on other runtimes therefore keeps calibrated `man_hours` and
`time_hours` while `tokens_k` and `cost` legitimately stay at cold-start.

### Scope-vs-fix split (approach A)

A measured actual is one number covering both original scope and fix rework. It is split by
**backing out the fix**: divide the actual by the observed `fix_factor` for that story to
recover the scope portion, and attribute the remainder to `fix`.

```
scope_actual = total_actual / fix_factor
fix_actual   = total_actual − scope_actual
```

This is lossy when `fix_factor` is itself poorly estimated, which is accepted: it needs no
extra instrumentation in the dev loop.

### Granularity

`calibration_granularity` selects how `scope` and `fix` are sampled:

- `"story"` (default) — every done story emits one scope sample and one fix sample.
  Converges after roughly 3 stories.
- `"sprint"` — one aggregated sample per sprint. Coarser, slower to converge, less noisy on
  projects with very small stories.

`closure` is always sampled per sprint and per epic regardless of this setting.

### Schema

```yaml
version: 2
scope:
  simple:   { man_hours: {ratio: 1.14, samples: 5}, time_hours: {...}, tokens_k: {...}, cost: {...} }
  standard: { ... }
  complex:  { ... }
closure:
  sprint:   { man_hours: {ratio: 1.18, samples: 4}, ... }
  epic:     { ... }
fix:
  simple:   { avg_fix_factor: 1.08, samples: 5 }
  standard: { ... }
  complex:  { ... }
```

A ratio is `actual / estimate`, so `> 1.0` means the estimates were optimistic. A component
entry with `samples < 3` is recorded but **not applied**.

### `version: 1` migration

A `version: 1` file is auto-migrated on first write. The original is preserved alongside as
`pm-calibration.yaml.v1` and is never read again. Migration maps the old blended ratio onto
the `scope` component and starts `closure` and `fix` fresh at zero samples — the old file
has no way to separate them, and seeding them from a blended figure would import exactly the
bias the split exists to remove.

> This `version:` key is the **calibration file's schema version**. It is unrelated to state
> *layout* generations, which are named "sharded", "legacy per-epic", and "legacy flat".

### Mechanization status

**Nothing in `pm-status.py` reads or writes the calibration file.** There is no calibration
subcommand. Every part of this section — appending samples, decay weighting, activation
thresholds, the approach-A split, `version: 1` migration — is performed by the orchestrator
following prose in `steps/shared/step-estimate.md`,
`steps/sprint/step-04-sprint-closure.md`, and `steps/execute/step-06-epic-closure.md`. Treat
it as a contract you must execute, not a service that runs for you. See §9 for the specific
gaps.

## 9. Where `CLAUDE.md` and the code disagree

Documented rather than papered over. In each case the code is authoritative.

1. **`calibration_granularity` is not a real setting.** `CLAUDE.md` says it is set "in each
   skill's `customize.toml`". No `customize.toml` in this repo declares it and nothing reads
   it. Treat `"story"` as the fixed behaviour and the key as aspirational until a skill
   actually resolves it.

2. **No step file emits a per-story calibration sample.** `steps/sprint/step-03-dev-loop.md`
   writes story actuals but appends nothing to the calibration file. Only sprint close and
   epic close append samples. So the effective granularity today is `"sprint"` for `scope`
   and `fix`, whatever the setting would say.

3. **"This is enforced, not optional" is true at story and sprint level only.** There is no
   read-back gate on an epic's `actual` block (`verify --scope epic` is structural), and no
   gate on any `estimate` block at any level.

4. **`set-actual` does not require all four metrics.** It requires *at least one*. The
   `--runtime claude` rejection only fires on a metric that was actually passed with an
   `N/A` value.

5. **`--runtime` defaults to `other`.** The strict path is opt-in per call. A `set-actual`
   or `verify` invocation that forgets `--runtime {runtime}` silently runs permissive.

6. **The compute-hours metric has two names** — `time_hours` in estimates, `elapsed_hours`
   in actuals. `CLAUDE.md` names neither.

7. **No `retrospective`-level metric block exists.** See §1.

8. **`--require-tokens` on `verify` is undocumented in `CLAUDE.md`.** It forces the
   Claude-strict token/cost rule irrespective of `--runtime`.

9. **Estimate/actual `cost` is a string, not a number**, despite the unquoted numeric form
   shown in `status-files.md` §4's examples. See §2 for the currency-symbol trap.

10. **Version-1 calibration migration is unimplemented.** No code path detects `version: 1`
    or writes `pm-calibration.yaml.v1`.

## 10. Worked example

Story `E001-S01-003`, classification `complex`. The `scope` component has 4 samples for
`complex` (activated, `man_hours` ratio `1.10`); the `fix` component has 1 sample (not
activated, so `F` applies).

**Estimate.** Base band midpoint for `complex` man-hours is 12. Scope ratio `1.10` and
`fix_mult` = `F` = `1.25`, applied once:

```
man_hours = 12 × 1.10 × 1.25 = 16.5
```

Compute hours follow the same path (`4 × 1.10 × 1.25 = 5.5`); tokens and cost take the scope
ratio only (`140 × 1.10 = 154`; `0.98 × 1.10 = 1.08`). Confidence is `medium` — the scope
component is calibrated but `fix` is not.

```bash
python3 {pm_status} set-estimate --state-root {pm_state_root} \
  --story E001-S01-003 \
  --man-hours 16.5 --time-hours 5.5 --tokens-k 154 --cost 1.08 \
  --confidence medium
```

**Actual.** The story runs under Claude, needs one fix iteration, and closes at 18.2
man-hours / 6.1 compute hours / 171K tokens / $1.24 read from the transcript `usage` fields:

```bash
python3 {pm_status} set-actual --state-root {pm_state_root} \
  --node story --story E001-S01-003 --runtime claude \
  --elapsed-hours 6.1 --man-hours 18.2 --tokens-k 171 --cost 1.24

python3 {pm_status} set-status --state-root {pm_state_root} \
  --story E001-S01-003 --status done

python3 {pm_status} verify --state-root {pm_state_root} \
  --scope story --story E001-S01-003 --runtime claude
# PASS E001-S01-003
```

Had `--cost N/A` been passed with `--runtime claude`, `set-actual` would have exited **2**
before writing anything.

**Resulting calibration samples.** Observed `fix_factor` for this story was `1.12` (one fix
iteration). Backing the fix out of the man-hours actual:

```
scope_actual = 18.2 / 1.12 = 16.25
fix_actual   = 18.2 − 16.25 = 1.95
scope_ratio_sample = 16.25 / (12 × 1.10) = 1.23
```

That contributes a `scope.complex.man_hours` sample of `1.23` (weighted 1.0 as the newest,
prior samples decayed by 0.8 each) and a `fix.complex` sample of `1.12`, taking `fix` to 2
samples — still one short of activation, so the next story for this classification still
uses `F` = 1.25. Because the runtime was Claude, the `tokens_k` and `cost` ratios also take
real samples; on `--runtime other` those two would have been skipped entirely.
