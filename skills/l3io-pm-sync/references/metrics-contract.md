# Metrics Contract (estimates & actuals)

Communicate all responses in `{communication_language}`.

This file is the single source of truth for **which** numbers l3io-pm records, **what they
are called on disk**, **how they are captured**, **where they are enforced**, and **how
estimates learn from them**. It is a **deep reference, consulted on demand** — do not load it
at activation. `steps/shared/step-00-activate.md` §8 carries the HARD RULE and the runtime
capture rule, plus a routing table naming the section to read for each case that needs this
file: token/cost capture detail (§3), writing an estimate or actual by hand (§4), explaining a
calibration result (§8), or a worked example (§10).

Most of what follows is now mechanized. §6 (roll-up), §7 (fix reserve), and §8 (calibration)
describe what `estimate-story`, `estimate-rollup`, and `set-actual` do themselves — read them
to understand or debug a number, not to perform a calculation by hand.

This file outranks the digest. Where they disagree, this file is correct — and `pm-status.py`
outranks both.

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
  fix_factor: 1.25         # the fix multiplier applied (one per classification)
  scope_ratios:            # the scope ratio applied, PER METRIC — load-bearing
    man_hours: 1.1         #   (see §8: the sample divides these back out)
    time_hours: 1.0
    tokens_k: 1.0
    cost: 1.0

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
  closure_ratios:          # the closure ratio applied, PER METRIC — load-bearing
    man_hours: 1.14        #   (see §8; 1.0 means the cold-start band applied)
    time_hours: 1.0
    tokens_k: 1.0
    cost: 1.0
  confidence: high

# actual — identical at story, sprint, and epic level; always single values
actual:
  elapsed_hours: 3.2       # compute hours — NOT time_hours
  man_hours: 15
  tokens_k: 812
  cost: 12.18

# stamped by set-actual once the node's calibration sample has been emitted;
# a later set-actual on the same node records nothing (§8, Idempotency)
calibration_sampled_at: '2026-08-16T22:34:03Z'
```

`scope_ratios` / `closure_ratios` are written by `estimate-story` / `estimate-rollup`. A
single scalar `scope_ratio` (what `set-estimate --scope-ratio` writes, and what
`estimate-story` wrote before 2.2.0) is still accepted as a fallback for all four metrics,
but it cannot express four independently calibrated corrections and is no longer produced by
`estimate-story`.

`METRIC_FIELDS` in `pm-status.py` is exactly `("elapsed_hours", "man_hours", "tokens_k",
"cost")`. Those four names, in that order, are what `verify` requires and what `show` sums.

**`cost`'s on-disk type is command-dependent** — the writers disagree, and the docs follow
the code rather than pretending otherwise:

| Writer | `cost` is written as |
|---|---|
| `set-actual` | a single-quoted **string** (`_coerce` wraps it in `SingleQuotedScalarString`) |
| `set-estimate` | a **string** (`cost`/`cost_low`/`cost_high` coerced through `str`) |
| `estimate-story` | a **float** (`round(value, 2)`) |
| `estimate-rollup` | a **float** (`round(value, 2)`) |

Every reader on the calibration and roll-up paths goes through `_num_or_none`, which parses
both forms (and strips a leading `$`), so the divergence is harmless there and was left
alone deliberately: normalizing it would rewrite the quoting of every existing state file
for no behavioural gain. `_accumulate_actuals` (what `show` sums) is the one reader that
does a bare `float()` — it handles a plain numeric string fine but **drops a `$`-prefixed
value silently**.

So: pass a **bare decimal with no currency symbol** — `--cost 12.18`, never
`--cost '$12.18'`. Currency symbols belong in prose reports, never in the state files.

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

**`set-estimate` is the direct, manual write** — pass every field yourself. The bottom-up
flow (`step-estimate.md`) does not call it: it uses `estimate-story` (classification in,
band × calibrated ratio × fix factor out) and `estimate-rollup` (children in, closure-banded
range out) instead, so the arithmetic runs once, in `pm-status.py`, not in step-file prose.
`set-estimate` still exists for a manual override or any write outside that flow, and its
contract below is unchanged.

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
- **No calibration enforcement.** `set-actual` derives and appends a calibration sample by
  default, but nothing forces the caller to keep that on — `--no-calibrate` suppresses it
  silently, and a derivation that fails (bad estimate shape, no comparable actual) only warns
  on stderr; the actuals write still succeeds. See §8.

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

`BASE_BANDS` in `pm-status.py` is the single source for these — do not copy the numbers into
a second table that can drift out of sync. `estimate-story` reads it directly:

```bash
python3 {pm_status} estimate-story --state-root {pm_state_root} \
  --story {story_key} --classification {simple|standard|complex} [--confidence {low|medium|high}]
```

The model's only job is choosing the classification; `estimate-story` looks up the band,
applies the calibrated `scope_ratio` (per metric) and `fix_factor`, and writes the estimate
block. See §8 for how those two multipliers are derived.

Stories store the band **midpoint × ratio × fix** as a single value; ranges appear only at
sprint and epic level.

**`estimate-story` records one ratio PER METRIC**, as `estimate.scope_ratios`. This is
load-bearing, not provenance: `derive_story_sample` divides the applied ratio back out so the
next sample is measured against the base band (§8), and four independently calibrated metrics
cannot be reconstructed from one recorded number. An earlier revision wrote a single
`scope_ratio` scalar — whichever metric came first by `BASE_BANDS` key order — on the
grounds that nothing read it back. Something does. A scalar `scope_ratio` is still *read* as
a fallback for all four metrics (that is what `set-estimate --scope-ratio` writes, and what
estimates written before 2.2.0 carry), but it is no longer written by `estimate-story`.

### Roll-up mechanics

`estimate-rollup` computes the sprint/epic range from its children plus a closure band:

```bash
python3 {pm_status} estimate-rollup --state-root {pm_state_root} --epic {epic_key} --sprint {sprint_key}
python3 {pm_status} estimate-rollup --state-root {pm_state_root} --epic {epic_key}
```

- `man_hours_low/high`, `tokens_k_min/max`, `cost_low/high` = Σ child estimate for that
  metric, widened by the closure band.
- `time_hours_low/high` = Σ child `time_hours` (no `parallel_factor` compression is applied
  by `estimate-rollup` — the sum is the wall-clock sum of the children as estimated).
- Closure band: apply the calibrated `closure` ratio for that level when it has activated
  (`total × (1 + ratio × band)`); otherwise the cold-start band applies at both ends, which
  is the same formula at `ratio = 1.0` (`COLD_START_CLOSURE_BAND = (0.10, 0.25)` —
  **10%/25% at every level**, sprint and epic alike; there is no separate 15%/20% split).
- The applied ratios are recorded per metric as `estimate.closure_ratios`, for the same
  reason `estimate-story` records `scope_ratios`: the closure sample divides them back out
  (§8).

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
fix_mult = F (1.25)                       if the fix component for this classification is not active
fix_mult = calibration.fix.avg_fix_factor if it is active
```

Activation for `fix` is stricter than for `scope`/`closure` — see §8 for why it needs
**both** cohorts (`clean` and `reworked`) at ≥3 samples, not just ≥3 samples of one thing.

**`fix_mult` applies to all four metrics**, not just `man_hours`/`time_hours` —
`estimate-story` multiplies every `BASE_BANDS` metric (`man_hours`, `time_hours`,
`tokens_k`, `cost`) by the same `scope_ratio × fix_mult` per metric. There is no metric
exemption from the fix multiplier in the shipped arithmetic.

## 8. Calibration

### Location

| Binding | Resolves to |
|---|---|
| `{pm_calibration_file}` | `{pm_state_root}/pm-calibration.yaml` = `{implementation_artifacts}/state/pm-calibration.yaml` |

The file is **committed**. Learned ratios are team knowledge and expensive to rebuild —
several closed sprints of real work each. It sits beside `issues.yaml` in the state root and
moves nowhere when epics move between `planned/`, `active/`, and `archived/`.

### Three separable components

Each component learns per metric. `scope` and `closure` each **activate independently per
metric** at **≥3 samples**. `fix` is stricter — see "The `fix` cohorts" below.

| Component | Learns | Sampled at |
|---|---|---|
| `scope` | story sizing ratio, per classification | inside `set-actual --node story` |
| `closure` | closure overhead ratio, separately for sprint and epic level | inside `set-actual --node sprint\|epic` |
| `fix` | fix cost, per classification (`clean` vs `reworked` cohorts) | inside `set-actual --node story` |

Splitting them matters because they fail differently: `scope` drifts with codebase
familiarity, `closure` is a near-fixed per-sprint tax that a single blended ratio hides
entirely, and `fix` tracks review strictness. A component below its activation threshold
uses its cold-start prior — ratio `1.0` for `scope` and `closure`, `F` = `1.25` for `fix` —
while its siblings may already be calibrated.

### Sample weighting

`scope` and `closure` samples are **exponentially decay-weighted with decay 0.8**
(`weighted_ratio`) — the most recent sample carries weight 1, the one before it 0.8, then
0.64, and so on. Recent work is a better predictor than early-project work, and the decay
lets ratios track a changing codebase without any explicit window or manual reset.

`fix` does **not** use decay weighting — each cohort (`clean`/`reworked`) keeps a running
**mean**, updated in place (`_bump_cohort`), not a sample list. See "The `fix` cohorts"
below.

### Token and cost samples

`tokens_k` and `cost` ratios accumulate **only from runs with real actuals** — the guard is
generic (`_num_or_none` rejects `N/A`/non-numeric), so it applies on every runtime, but in
practice only Claude runs supply real values for these two metrics. An `N/A` or missing
value is skipped entirely for that metric, never imputed, never counted toward the ≥3
activation threshold — the other three metrics on the same story still record. A project run
mostly on other runtimes therefore keeps calibrated `man_hours` and `time_hours` while
`tokens_k` and `cost` legitimately stay at cold-start.

### The scope/fix split — iteration-based, with back-out as fallback

Approach A alone (dividing the actual by the *assumed* `fix_factor` to recover a scope
figure) is circular for a `fix` sample: it divides by the very number it is trying to learn,
so `fix` could only ever re-derive its own prior. `derive_story_sample` avoids this for the
`fix` side by using `completion_evidence.fix_iterations` directly:

**The sample must be measured against the BASE BAND, not against the last estimate.** The
estimate is `band_mid × scope_ratio_applied × fix_factor`, so a raw `actual / estimate`
measures error against an estimate that already contains the previous ratio. Feeding that
back as the next ratio makes the loop converge to `√(truth ÷ band_mid)` — a permanent
underestimate that no volume of data closes — and means a perfect estimate never produces a
neutral sample. `derive_story_sample` therefore divides the applied ratio back out, per
metric, using `estimate.scope_ratios[metric]` (falling back to a scalar `scope_ratio`, then
to `1.0`).

**The two paths differ arithmetically**, which is what makes approach A a real back-out
rather than a relabelling:

- **`fix_iterations == 0`** (and a `fix_factor` is present) — the story needed no rework, so
  the actual is pure scope. `provenance: exact`:

  ```
  sample = actual × scope_ratio_applied × fix_factor / estimate     ( = actual / band_mid )
  ```

  Man-hours also feed the `clean` cohort of `fix` unmodified.

- **`fix_iterations > 0`, or the field is absent entirely** (a `fix_factor` is present, but
  the completion evidence doesn't say zero) — the actual mixes scope and rework, so the
  scope portion is `actual ÷ fix_factor` and the fix factor **cancels**.
  `provenance: backout`:

  ```
  sample = actual × scope_ratio_applied / estimate     ( = actual / (band_mid × fix_factor) )
  ```

  When `fix_iterations` is a real number `> 0`, man-hours also feed the `reworked` cohort;
  when the field is simply **absent**, no fix-cohort sample is recorded — there's a fix
  factor to back out arithmetically, but no iteration count to say which cohort the
  man-hours belong to.

- **The estimate has no `fix_factor` recorded at all** (a story estimated before
  `estimate-story` existed, or estimated by hand) — `provenance: legacy`, checked first and
  independent of `fix_iterations`. Both missing factors are treated as `1.0`, so the sample
  is `actual / estimate`; the label preserves the imprecision for a later audit. No
  fix-cohort sample is recorded: there is nothing to attribute rework to without knowing
  what fix multiplier, if any, was baked into the estimate.

A consequence worth stating plainly: on the `exact` path a story that consumes its entire
fix reserve without any rework produces a sample of `ratio × fix_factor`, because that
really is evidence that scope was under-modelled by the reserve. On the `backout` path,
`actual == estimate` produces exactly the ratio that was applied — a neutral sample.

**`fix_iterations` must be on the node BEFORE `set-actual` runs.** The sample is derived
inside `set-actual`, so evidence written afterwards is invisible to it:
`provenance: exact` becomes unreachable, neither `fix` cohort ever fills, and `F` = 1.25
freezes. `steps/sprint/step-03-dev-loop.md` §4 writes the completion evidence first for
exactly this reason.

`derive_story_sample` returns `None` — no sample at all — when the node has no `estimate` or
no `actual` block, or when every metric's estimate/actual pair is missing/`N/A`/zero.

### Closure sampling — the residual and its denominator

```
closure actual   = actual(parent) − Σ actual(children)
closure expected = midpoint(parent estimate) − Σ estimate(children)
sample           = closure actual × closure_ratio_applied / closure expected
```

**The denominator must be the quantity the ratio is applied to.** `estimate-rollup` applies
the learned ratio to the closure band alone (`total × (1 + ratio × band)`), so dividing the
residual by the *whole* parent estimate midpoint measures a different quantity than the one
being corrected and the loop cannot converge — with a perfectly consistent history it moved
the roll-up *away* from the observed total. And, exactly as with `scope`, the estimated
overhead already contains the ratio that was applied when the parent estimate was written
(`estimate.closure_ratios[metric]`, `1.0` when absent), so that ratio is divided back out.

Worked: four children estimated 10 each (Σ 40), true closure overhead 8 every time, true
total 48. Cold start rolls up to `40 × (1 + 1.0 × 0.175) = 47`, expected overhead 7, sample
`8 × 1.0 / 7 = 1.143`. Once active, `40 × (1 + 1.143 × 0.175) = 48.0` — the observed total —
and every later generation samples `8 × 1.143 / 8 = 1.143` again, so the ratio holds.

### Idempotency

`set-actual` stamps `calibration_sampled_at` on the node once it has emitted that node's
sample. A second `set-actual` on the same node records nothing and says so in its stdout
suffix (`sample already recorded at … — skipped (replay)`). `--no-calibrate` still exists
for backfills, but correctness no longer depends on the caller remembering it.

### Concurrency

`pm-calibration.yaml` is a shared append target — every `set-actual`, across every parallel
subagent, may append to it. The **whole load → mutate → save cycle** runs under one
exclusive `flock` (`calibration_lock`), not just the save: locking only the save let two
concurrent samplers read the same pre-append state and the second one silently drop the
first's sample. At the default `max_parallel_subagents = 4` that lost roughly half of all
samples, with every call still exiting 0.

### The `fix` cohorts

`fix` does not store a ratio per sample. It keeps two running means per classification,
`clean` and `reworked` — man-hours for stories that needed no fix iteration vs. stories that
needed at least one — and derives `avg_fix_factor = reworked.mean_man_hours /
clean.mean_man_hours` on read.

**Activation requires BOTH cohorts to reach ≥3 samples**, not just one (`active_fix_factor`).
One cohort alone cannot form a ratio — a mean of `reworked` man-hours means nothing without a
comparable `clean` mean to divide by, and vice versa. This is why a project where every story
needs rework never activates `fix`, no matter how many `reworked` samples pile up: it has no
`clean` baseline to compare against, and `F` = 1.25 remains the correct number to keep
using — the asymmetry (unlike `scope`/`closure`, which activate on a single count) is
deliberate, not a bug.

### Granularity

`granularity` lives **in the calibration file itself** (`new_calibration`'s `granularity`
key), not bound from a step file or `customize.toml` — nothing currently varies it, so every
project effectively runs `"story"` granularity: `set-actual --node story` records one scope
sample and (when derivable) one fix-cohort update per closed story; `set-actual --node
sprint|epic` records one closure sample per closed sprint/epic, unconditionally. There is no
`"sprint"`-granularity aggregation path in the shipped code — a project cannot presently opt
into coarser story sampling by changing this key. `calibration show` prints whatever value
is stored for information only; it does not change any sampling behavior.

### Schema

```yaml
version: 2
granularity: story
scope:
  simple:   { man_hours: {samples: [1.02, 1.14, 0.98]}, time_hours: {...}, tokens_k: {...}, cost: {...} }
  standard: { ... }
  complex:  { ... }
closure:
  sprint:   { man_hours: {samples: [1.18, 1.05, 1.22, 0.97]}, ... }
  epic:     { ... }
fix:
  simple:   { clean: {mean_man_hours: 3.1, samples: 4}, reworked: {mean_man_hours: 4.2, samples: 3} }
  standard: { ... }
  complex:  { ... }
```

`scope` and `closure` entries store the **raw ratio samples as a list** (`samples: [...]`,
newest last) — the weighted mean is computed on read by `weighted_ratio`, never persisted.
`fix` entries store a running **mean and an integer count** per cohort — `avg_fix_factor` is
not a file field; it is `active_fix_factor(cal, classification)`, computed on read from the
two cohort means, and only returned once both cohorts clear `MIN_SAMPLES`.

A `scope` ratio is `actual / band_mid` (or `actual / (band_mid × fix_factor)` on the backout
path) and a `closure` ratio is `closure actual / closure expected` — both with the applied
ratio divided back out per "The scope/fix split" and "Closure sampling" above — so `> 1.0`
means the estimates were optimistic. A component
below its activation threshold is recorded but **not applied** — `estimate-story` and
`estimate-rollup` fall back to the cold-start prior for that metric/bucket.

### `version: 1` migration

A `version: 1` file is auto-migrated **the first time a write path touches it**
(`record_story_sample` / `record_closure_sample`, both via `migrate_calibration`). The
original is preserved alongside as `pm-calibration.yaml.v1` and is never read again.
Migration maps the old blended ratio onto the `scope` component and starts `closure` and
`fix` fresh at zero samples — the old file has no way to separate them, and seeding them
from a blended figure would import exactly the bias the split exists to remove.

**`load_calibration` never migrates.** It is deliberately side-effect-free: `calibration
show` and `estimate-story`/`estimate-rollup` (which only read the file to look up active
ratios) call `load_calibration` and treat an unmigrated `version: 1` file as if none of its
scope/closure/fix components had any samples yet, but they never rewrite it. Only the two
sampling write paths migrate, and only at the moment they are about to append.

> This `version:` key is the **calibration file's schema version**. It is unrelated to state
> *layout* generations, which are named "sharded", "legacy per-epic", and "legacy flat".

### Mechanization status

`pm-status.py` now runs this loop; it is not orchestrator prose.

- **`estimate-story`** and **`estimate-rollup`** read the file (`load_calibration`, never
  migrating) and apply whichever ratios are active — cold-start priors otherwise.
- **`set-actual`** derives and appends a sample automatically after every successful actuals
  write (`record_story_sample` for `--node story`; `record_closure_sample` for `--node
  sprint|epic`), unless `--no-calibrate` is passed. A derivation failure is caught, warned on
  stderr, and never fails the actuals write — the actual is the primary record; the
  calibration sample is derived, secondary data. The `set-actual` stdout line reports what
  was recorded (e.g. `scope+3 metrics, provenance=exact, class=complex`) or why nothing was
  (e.g. `no sample (missing estimate or actual)`). **Skip reasons go to stdout**, inside that
  `[...]` suffix — only an unexpected exception warns on stderr.
- **`calibration show`** is read-only. A missing file reports cold-start for every component
  and exits `0` — there is no error state for "no calibration data yet."
- **Closure sampling skips PER METRIC, with a reason**, never aborting the other metrics'
  samples, because recording anyway would silently bias the ratio: a child missing that
  metric's actual or estimate (a partial sum understates overhead, permanently, since a low
  ratio has no marker saying it was incomplete); an estimated closure overhead of `≤ 0`
  (nothing to measure the residual against); a negative residual; and an `N/A`
  `tokens_k`/`cost` on either side. Only when *no* metric produces a residual is the whole
  sample skipped.
- **A negative wall-clock residual is expected, not a miscount.** Under
  `parallel_mode = "auto"` a sprint's stories overlap, so the sprint's `elapsed_hours` is
  legitimately below the sum of its stories'. `time_hours` is skipped with a reason naming
  parallelism; `man_hours`, `tokens_k` and `cost` are additive regardless of concurrency, so
  a negative residual there keeps the miscount warning.

See §9 for the disagreements this closes and the ones that remain open.

## 9. Where `CLAUDE.md` and the code disagree

Documented rather than papered over. In each case the code is authoritative. Two entries
that used to live here — "no step file emits a per-story calibration sample" and "version-1
calibration migration is unimplemented" — are gone: `set-actual` now samples automatically
at story granularity, and `migrate_calibration` is real code, exercised by the write paths.
The `calibration_granularity`/`customize.toml` entry is also gone: CLAUDE.md no longer makes
that claim (§8, Granularity). The rest were untouched by this round and remain open.

1. **"This is enforced, not optional" is true at story and sprint level only.** There is no
   read-back gate on an epic's `actual` block (`verify --scope epic` is structural), and no
   gate on any `estimate` block at any level.

2. **`set-actual` does not require all four metrics.** It requires *at least one*. The
   `--runtime claude` rejection only fires on a metric that was actually passed with an
   `N/A` value.

3. **`--runtime` defaults to `other`.** The strict path is opt-in per call. A `set-actual`
   or `verify` invocation that forgets `--runtime {runtime}` silently runs permissive.

4. **The compute-hours metric has two names** — `time_hours` in estimates, `elapsed_hours`
   in actuals. `CLAUDE.md` names neither.

5. **No `retrospective`-level metric block exists.** See §1.

6. **`--require-tokens` on `verify` is undocumented in `CLAUDE.md`.** It forces the
   Claude-strict token/cost rule irrespective of `--runtime`.

7. **Estimate/actual `cost`'s type depends on which command wrote it** — a quoted string
   from `set-estimate`/`set-actual`, a float from `estimate-story`/`estimate-rollup` —
   despite the single unquoted numeric form shown in `status-files.md` §4's examples. The
   divergence is left as-is deliberately; see §2 for the full table and the currency-symbol
   trap.

## 10. Worked example

Story `E001-S01-003`, classification `complex`, cold-start `fix` (no calibration file yet
covers this classification), but `scope.complex.man_hours` already active at ratio `1.10`
(≥3 samples); every other `scope` metric for `complex` is still cold-start (ratio `1.0`).

**Estimate.** The model supplies only the classification:

```bash
python3 {pm_status} estimate-story --state-root {pm_state_root} \
  --story E001-S01-003 --classification complex
# OK estimate-story E001-S01-003 class=complex scope_ratios[man_hours=1.1 time_hours=1.0 tokens_k=1.0 cost=1.0] fix_factor=1.25
```

`estimate-story` looks up `BASE_BANDS["complex"]` (man_hours 8–16, time_hours 2–6, tokens_k
80–200, cost 0.55–1.40), takes each midpoint, and multiplies by that metric's own scope
ratio and the classification's fix multiplier — `fix_mult` = `F` = `1.25` here, since `fix`
has no active cohorts yet:

```
man_hours = 12 × 1.10 × 1.25 = 16.5      (scope ratio active)
time_hours =  4 × 1.00 × 1.25 =  5.0      (scope ratio cold-start)
tokens_k   =140 × 1.00 × 1.25 =175        (scope ratio cold-start, rounded to int)
cost       =0.975× 1.00 × 1.25 = 1.22     (scope ratio cold-start)
```

The written `estimate.scope_ratios` is `{man_hours: 1.1, time_hours: 1.0, tokens_k: 1.0,
cost: 1.0}` — one entry per metric, each the ratio actually applied to that metric. The
sample derivation reads these back individually; a single recorded number could not
reconstruct four different corrections.

**Actual.** The story runs under Claude, needs **one** fix iteration
(`completion_evidence.fix_iterations: 1`, written via `set-field` before closeout), and
closes at 18.2 man-hours / 6.1 compute hours / 171K tokens / $1.24 read from the transcript
`usage` fields:

```bash
python3 {pm_status} set-actual --state-root {pm_state_root} \
  --node story --story E001-S01-003 --runtime claude \
  --elapsed-hours 6.1 --man-hours 18.2 --tokens-k 171 --cost 1.24
# OK set-actual story E001-S01-003 ['cost', 'elapsed_hours', 'man_hours', 'tokens_k'] [scope+4 metrics, provenance=backout, class=complex]

python3 {pm_status} set-status --state-root {pm_state_root} \
  --story E001-S01-003 --status done

python3 {pm_status} verify --state-root {pm_state_root} \
  --scope story --story E001-S01-003 --runtime claude
# PASS E001-S01-003
```

Had `--cost N/A` been passed with `--runtime claude`, `set-actual` would have exited **2**
before writing anything, and no calibration sample would have been derived.

**What `set-actual` derived, inline.** `fix_iterations` is `1`, not `0`, so this is the
**backout** path: the actual mixes scope and rework, the scope portion is `actual ÷
fix_factor`, and the `fix_factor` cancels out of the ratio. Each metric divides its own
applied `scope_ratios` entry back out, so the comparison lands against the base band:

```
man_hours scope ratio  = 18.2 × 1.10 / 16.5 = 1.2133   ( = 18.2 / (12    × 1.25) )
time_hours scope ratio =  6.1 × 1.00 /  5.0 = 1.2200   ( =  6.1 / ( 4    × 1.25) )
tokens_k scope ratio   =  171 × 1.00 / 175  = 0.9771   ( =  171 / (140   × 1.25) )
cost scope ratio       = 1.24 × 1.00 / 1.22 = 1.0164   ( ≈ 1.24 / (0.975 × 1.25); the
                                                         stored estimate is rounded to 1.22 )
```

Each is appended to `scope.complex.{man_hours,time_hours,tokens_k,cost}.samples`. Because
`fix_iterations > 0`, the 18.2 man-hours actual also updates `fix.complex.reworked`'s running
mean — not `clean`'s — and `fix.complex.clean` gets nothing from this story. `fix` for
`complex` only activates once **both** `clean` and `reworked` separately reach 3 samples; a
run of reworked-only stories, however many, never activates it on its own.

Had `fix_iterations` been `0`, provenance would have been `exact`, the man-hours actual would
have fed the `clean` cohort, **and the four ratios would differ** — the exact path keeps the
`fix_factor` because a zero-rework actual is pure scope measured against a
fix-reserved estimate:

```
man_hours scope ratio (exact) = 18.2 × 1.10 × 1.25 / 16.5 = 1.5167   ( = 18.2 / 12 )
```

A second `set-actual` on this story would record nothing: the node now carries
`calibration_sampled_at`, and the call reports `sample already recorded at … — skipped
(replay)`.
