# Metrics Model Rework — Design

**Date:** 2026-08-18
**Status:** Approved for planning
**Origin:** Post-run analysis of epic E000, sprint S03 (`l3io-pm-execute`)

---

## 1. Context

Sprint E000-S03 closed with six stories, six fix passes, zero carry-over. Three of the four
tracked metrics landed at or under their estimate bands. One did not:

| Metric | Estimate | Actual | Verdict |
|---|---|---|---|
| cost | $51.85–58.92 | **$271.58** | 4.6× over |
| tokens (k) | 26,023–29,571 | 20,383 | under band |
| elapsed (h) | 18.27–20.76 | 11.4 | under band |

The spend decomposed as:

| Attribution | Tokens | Share |
|---|---|---|
| six stories | 4,908k | 24% |
| closure review | 806k | 4% |
| **orchestration** | **14,668k** | **72%** |

The orchestration layer carried 157 messages holding only 33,900 output tokens, but 99.8% of
its fresh tokens were `cache_creation` at ~93k per message — roughly thirty blocking waits
each outliving the prompt cache and re-creating the entire prefix.

That surfaced three separate defects, which this design addresses together because they
touch the same nodes, the same script, and the same calibration file.

---

## 2. Problems

### 2.1 `cost` has no arithmetic relationship to `tokens_k` (BL-E000-043)

Two independent breaks, one on each side of the estimate/actual pair:

- **Estimate side.** `BASE_BANDS` (`skills/_shared/pm-status.py`) declares `tokens_k` and
  `cost` as *separate* bands per classification, and `estimate-story` applies each metric's
  own learned scope ratio. Cost is never derived from tokens; it is a parallel guess that
  calibration is free to drift away from tokens without bound. The cold-start bands imply a
  consistent ~$5–7/M, so the coupling looks correct on a fresh project and decays silently.
- **Actual side.** `metrics-contract.md` §3 instructs the capturer to sum the usage fields
  "and **price it** for `cost`" without ever defining the price. Every historical `cost`
  actual was priced by whatever the capturing agent believed at the time.

### 2.2 Orchestration spend is unmodeled *and* unattributable

The roll-up is `Σ children + closure band`, where the cold-start closure band is 10–25% at
every level. A term at 72% of total cannot be represented by that band under any ratio.

Worse, the capture rule attributes tokens to "the messages belonging to the node being
closed" — and orchestrator messages belong to no node. The spend therefore enters neither
story samples nor closure samples, so **calibration cannot self-correct**. More sprints do
not converge the estimate; the largest term never enters the sample stream in any form.

### 2.3 One time metric is doing two jobs

`man_hours` is defined as *human attention — review, direction, unblocking*, yet its base
bands say a complex story is 8–16 hours. That is a developer's build estimate, not
attention. In an autonomous run the two differ by an order of magnitude, and the project
needs both numbers for different reasons: build effort answers "what did this save?",
attention answers "what did it cost me to supervise?".

Separately, the same metric is named `time_hours` on the estimate side and `elapsed_hours`
on the actual side, handled by explicit mapping tables in `pm-status.py` that carry a comment
warning that naive key-zipping is silently wrong.

---

## 3. Non-goals

- **The `.gitea/workflows/` bypass** and **BL-E000-051** (SIGINT during a mutation leaving
  planted AD-5 violations in real `packages/`) are findings about the consuming project, not
  this package. The workflow bypass is the highest-severity item on the overall list given
  the runner fires on check-in, but it is not fixed here.
- **The harness prompt-cache TTL.** The default ephemeral cache TTL is ~5 minutes; a 1-hour
  TTL (`cache_control: {type: "ephemeral", ttl: "1h"}`) would have absorbed every one of the
  waits that produced this run's overrun. That setting belongs to whoever configures the
  harness. It is the single highest-leverage remedy for §2.2's *magnitude* and should be
  raised separately.
- **Sizing the orchestration band.** Deliberately deferred — see §6.4.
- **Bumping the calibration file's `version` field.** It stays at `2` until explicitly
  raised. Compatibility is handled by shape-tolerant reads (§7).

---

## 4. The metric model

Five metrics replace four.

| Metric | Meaning | Observable | Unit |
|---|---|---|---|
| `man_hours` | What a developer would have taken to do this work | No — counterfactual | hours |
| `hitl_hours` | Human attention actually spent supervising the run | Yes | hours |
| `elapsed_hours` | AI wall-clock, dispatch to completion | Yes | hours |
| `tokens_k` | Tokens consumed, broken down by class | Yes | thousands |
| `cost` | **Derived** — never entered | Computed | USD |

### 4.1 On-disk shape

Estimate and actual now use the **same field names**. The `time_hours` → `elapsed_hours`
mapping tables in `pm-status.py` are deleted.

```yaml
# story node
estimate:
  man_hours: 12
  hitl_hours: 0.5
  elapsed_hours: 4
  tokens_k:                  # total x cold-start mix (§4.2)
    total: 1160
    input: 174
    output: 58
    cache_write: 348
    cache_read: 580
  cost: 4.79                 # derived from tokens_k x rates[model]
  model: claude-opus-5       # which rate card priced this
  confidence: high
  fix_factor: 1.25
  scope_ratios: {man_hours: 1.1, hitl_hours: 1.0, elapsed_hours: 1.0, tokens_k: 1.0}

actual:
  man_hours: 14              # re-assessed at closure (§4.4)
  hitl_hours: 0.3
  elapsed_hours: 3.1
  tokens_k:                  # real per-class counts from the transcript
    total: 4999
    input: 412
    output: 34
    cache_write: 4300
    cache_read: 253
  cost: 29.91                # derived, frozen at capture
  model: claude-opus-5
```

Both examples are arithmetically exact under the §5 table. They are illustrative — the
E000-S03 figures are analysed in §1 and §5, not reproduced here, because that run's `cost`
was priced under the undefined rule this design removes.

Sprint and epic estimates keep their `_low`/`_high` and `_min`/`_max` range forms for every
metric except `cost`, which is derived at both ends from the token range.

### 4.2 `tokens_k` — total is banded, classes price it

The estimate's per-class values are **not** independently banded. `BASE_BANDS` carries a
single `tokens_k` *total* band per classification; the per-class split is that total times a
**mix**. This keeps existing scalar `tokens_k` calibration samples comparable to new
structured ones, and keeps exactly one thing being calibrated for sizing.

The mix used at estimate time is:

1. the observed mean mix across calibration samples, once ≥3 story samples carry class data;
2. otherwise the shipped cold-start placeholder below.

```
cold-start mix: {input: 0.15, output: 0.05, cache_write: 0.30, cache_read: 0.50}
```

This placeholder is an assumption about a healthy, cache-warm run, explicitly labeled as
such in `metrics-contract.md`. It is replaced by measurement after three story closes; it is
not a calibrated ratio and gains no component of its own.

Actuals always carry real per-class counts read from the transcript's `usage` fields —
`input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`.
`total` is their sum, and is validated as such.

### 4.3 `cost` is derived

`cost = Σ over classes (tokens_k[class] × rates[model][class]) / 1000`

- `set-actual --cost` and `set-estimate --cost*` become **errors**, not silently-honored
  overrides. The only way to change a cost is to correct the rate table or the token counts.
- `verify` recomputes `cost` from the node's own `tokens_k` and `model` and fails on
  mismatch, so a hand-edited cost cannot survive.
- Cost is computed **once at capture and frozen in the node**. A later rate-table change
  never silently re-prices history. The node records the `model` that priced it.
- The existing `N/A` rules are unchanged in spirit: under `--runtime other`, absent per-class
  counts yield `tokens_k: N/A` and `cost: N/A`, and calibration skips them. Under
  `--runtime claude`, `N/A` remains forbidden for both.

### 4.4 `man_hours` is counterfactual, with a defined capture rule

`man_hours` keeps its existing bands (2–4 / 4–8 / 8–16), which were always developer-effort
shaped and now match the definition.

Its actual is a **re-assessment at closure**, and the closure step is required to compute it
from the delivered diff, tests, and scope changes **before reading the estimate**. This
anti-anchoring rule is the whole point: an assessor who sees the estimate first produces
ratios that drift to 1.0 and a calibration component that learns nothing.

`verify` gates on the assessment being recorded, never on its value.

### 4.5 `hitl_hours` cold-start bands

| Classification | `hitl_hours` band |
|---|---|
| simple | 0.1 – 0.3 |
| standard | 0.2 – 0.5 |
| complex | 0.3 – 1.0 |

Documented as cold-start assumptions, superseded by the learned scope ratio at ≥3 samples
like every other metric.

---

## 5. The rate table

Model-keyed, four classes, shipped as a default in `pm-status.py` and overridable at
`modules.l3io-pm.token_rates` in the `custom/` config layer. Cache-write is 1.25× input;
cache-read is 0.1× input.

| Model | input | output | cache_write | cache_read |
|---|---|---|---|---|
| `claude-opus-5` | $5.00 | $25.00 | $6.25 | $0.50 |
| `claude-opus-5` (fast mode) | $10.00 | $50.00 | $12.50 | $1.00 |
| `claude-fable-5` | $10.00 | $50.00 | $12.50 | $1.00 |
| `claude-sonnet-5` | $3.00 | $15.00 | $3.75 | $0.30 |
| `claude-sonnet-4-6` | $3.00 | $15.00 | $3.75 | $0.30 |
| `claude-haiku-4-5` | $1.00 | $5.00 | $1.25 | $0.10 |

All figures are Anthropic first-party API rates as of 2026-06-24. Partner-operated platforms
(Bedrock, Vertex) price separately and require a config override.

**Why model-keyed matters concretely.** This run's $271.58 over 20,383k tokens is $13.32/M
blended. At `claude-opus-5` standard rates that volume prices at roughly $127. The observed
figure only reconciles against a $10/M input tier — `claude-fable-5`, or `claude-opus-5` in
fast mode. A single blended rate is wrong by 2× on identical token counts.

The estimate-time model comes from `modules.l3io-pm.default_model`. An unknown model id is a
**hard error**, never a silent fallback — a wrong rate must stay visible.

A new read-only subcommand `pm-status.py rates [--model ID]` prints the effective table after
config overrides, so the value in force is inspectable without reading source.

---

## 6. Orchestration as a fourth calibration component

### 6.1 Roll-up

```
story.estimate  = base_band(class) × scope_ratio × fix_mult
sprint.estimate = Σ story.estimate  + closure band + orchestration band
epic.estimate   = Σ sprint.estimate + closure band + orchestration band
```

`sprint`/`epic` estimates remain *defined as* the sum of their children plus overhead, so
they reconcile by construction. The applied orchestration ratios are recorded per metric as
`estimate.orchestration_ratios`, for the same load-bearing reason `scope_ratios` and
`closure_ratios` are recorded: the sample divides them back out.

### 6.2 Attribution

**Orchestrator messages between a node's open and its close belong to that node's
orchestration block.** Those boundaries are already recorded in `events.jsonl`, so the
attribution is derivable rather than judged.

A new `orchestration` block sits beside `estimate` and `actual` on sprint and epic nodes,
carrying the same five metrics. Story nodes have none — a story's orchestration is its
parent sprint's.

### 6.3 Calibration component

`calibration.orchestration` joins `scope`, `closure`, and `fix`, keyed by level
(`sprint` / `epic`), activating at ≥3 samples with the same 0.8 exponential decay, derived
inside `set-actual --block orchestration`.

**It learns a fraction, not a ratio.** `closure` measures a residual against an *estimated*
closure overhead, which requires that estimate to exist. The orchestration band ships `null`
(§6.4), so there is nothing to measure against and a ratio could never bootstrap — the
component would sit inactive forever. The sample is instead
`orchestration_actual / Σ children actual` for that metric: directly observable from the
first closed sprint, and it *is* the band. Applied as `total × (1 + f × spread)` with
spread `(0.8, 1.2)` widening the point estimate into a range.

Because orchestration scales with **dispatch count × context size** while closure scales
with **sprint content**, they must not share a ratio; a single ratio over two uncorrelated
drivers converges on neither.

### 6.4 The band ships unseeded

The cold-start orchestration band is `null`. Every number available today is contaminated by
the wait defect in §2.2 — sizing the term on this run would bake a ~30-cache-expiry bug into
a committed prior applied to the remaining 107 stories, trading a 4× under-estimate for a
comparable over-estimate.

While the band is `null`, `estimate-rollup` emits an explicit warning that orchestration is
unestimated and the resulting cost is known-low. The first three post-fix sprints seed it
from measurement.

---

## 7. Calibration migration — in place, `version: 2` retained

| Existing sample | Disposition | Rationale |
|---|---|---|
| `cost.*` (scope/closure/fix) | **Dropped** | A derived metric must not learn independently |
| `scope.{class}.man_hours` | **Quarantined** as `legacy.scope.{class}.man_hours` | Definition changed; incomparable, but preserved |
| `closure.*.man_hours`, `fix.*` man-hour cohorts | Same quarantine | Same reason |
| `scope.{class}.time_hours` | **Carried**, renamed `elapsed_hours` | Same measurement, new name |
| `scope.{class}.tokens_k` | **Carried**, flagged if outside 0.5–2.0 | Still measured the same way (§4.2) |
| `orchestration`, `hitl_hours`, `token_mix` | **Seeded empty** | No trustworthy data exists |

Reads are **shape-tolerant** rather than version-gated: an absent `orchestration` key means
cold start; a present `legacy` block is never read by the estimator. This is what lets
`version` stay at `2`. The practical exposure is a downgrade to an older `pm-status.py` in a
project whose file has already migrated; `self-install` is package-version-guarded and there
is one runtime copy per project, so this is narrow — but it is a real limitation and is
documented as such rather than engineered around.

The pre-migration file is preserved as `pm-calibration.yaml.pre-metrics`. The migration runs
once, under flock, and prints a report of what moved, what was dropped, and what was flagged.

Flagged `tokens_k` ratios are the test of a standing suspicion: this run's token *estimate*
was ~26,000k for six stories against base bands of 80–200k per complex story, implying a
learned scope ratio in the tens. If past actuals swept orchestration-shaped overhead into
story samples, those ratios are inflated and the flag will show it.

---

## 8. Wait protocol and stall detection

### 8.1 The contract clause

CLAUDE.md already declares "all state passes through disk — never through in-memory
hand-off," but no step file makes it operative, and `step-03-dev-loop.md` — where the five
story agents hung — never mentions `BLOCKED` at all. The clause goes in three places, because
one is not enough to survive a long context:

> **You have no inbox. No message will ever arrive. If you need a decision you cannot make,
> write it to disk and end with `BLOCKED: <one-line reason>`.**

1. `steps/shared/step-00-activate.md` §8 — the digest every subagent keeps in context.
2. `steps/sprint/step-03-dev-loop.md` — every `Spawn ... subagent with:` block, alongside the
   required status line.
3. The dispatch prompts themselves, at the point of spawn.

### 8.2 Stall detection

`append_event` gains `dispatch_open` and `dispatch_close` records carrying node keys, an
agent label, and a timestamp. `cmd_report` grows a stalled-dispatch section listing any
dispatch open longer than `modules.l3io-pm.orchestration_stall_minutes` (default 15).

This cannot interrupt a hang. It makes the next one visible in `report --watch` within
minutes rather than at invoice time. Given §3's note that the root cause is a harness cache
TTL this package does not control, visibility is the honest ceiling for what is fixable here.

---

## 9. Implementation phases

Ordered so the clean-measurement clock starts before anything depends on measurements.

1. **Wait protocol + stall detection.** No schema dependency. Ships first.
2. **Metric schema, rate table, derived cost.** `pm-status.py` + tests: `METRIC_FIELDS`,
   `BASE_BANDS`, structured `tokens_k`, rate lookup, `cost` derivation, `rates` subcommand,
   deletion of the `time_hours`→`elapsed_hours` mapping tables, CLI flag changes.
3. **Orchestration term.** Capture, roll-up arithmetic, calibration component; band `null`.
4. **Calibration migration.** One-shot, on the existing file.
5. **Docs, digest, step files.** `metrics-contract.md` §§2/3/6/8, `step-00-activate.md` §8,
   the closure steps' `man_hours` re-assessment rule, `step-estimate.md` bands, CLAUDE.md's
   HARD RULE (four metrics → five), plus a `check:docs` extension asserting the documented
   metric list matches `METRIC_FIELDS` so this specific drift cannot recur.

### CLI surface changes

| Command | Change |
|---|---|
| `set-actual` | `--tokens-k` → `--tokens-input/--tokens-output/--tokens-cache-write/--tokens-cache-read`; `--model` added; `--hitl-hours` added; `--cost` now an error |
| `set-estimate` | Same token flags plus range forms; `--hitl-hours[-low/-high]` added; `--cost*` now an error; `--time-hours*` accepted as a deprecated alias for `--elapsed-hours*` |
| `estimate-story` | Emits five metrics; tokens as total × mix |
| `estimate-rollup` | Adds the orchestration band; warns while it is `null` |
| `verify` | Required-field list updated; recomputes and checks `cost` |
| `report` | Stalled-dispatch section; spend broken out by story / closure / orchestration |
| `rates` | **New**, read-only |

### Authoring and propagation

Everything is authored in `skills/_shared/` and propagated by `npm run sync:scripts`; the
per-skill `scripts/` and `references/` copies are never hand-edited. `npm run check:scripts`
and `npm run check:docs` both gate.

---

## 10. Testing

Test-first, in `skills/_shared/tests/test-pm-status.py`, since the arithmetic is the product:

- Cost derivation per model and per class, including the fast-mode row.
- Unknown model id is a hard error.
- `--cost` on `set-actual`/`set-estimate` is rejected.
- `verify` fails a hand-edited cost.
- `tokens_k.total` must equal the sum of its classes.
- Estimate-time mix falls back to the placeholder below 3 samples and to the observed mean
  at or above it.
- Roll-up equals `Σ children + closure + orchestration` exactly, at both range ends.
- Orchestration ratio activates at exactly 3 samples, not 2.
- `estimate-rollup` warns while the orchestration band is `null`.
- Migration: `cost` dropped, `man_hours` quarantined and unread, `time_hours` carried under
  its new name, `tokens_k` carried, out-of-range ratios flagged, `version` still `2`,
  `.pre-metrics` written, idempotent on a second run.
- Shape-tolerant reads: a pre-migration file yields cold start rather than an error.
- `N/A` handling under `--runtime other` and rejection under `--runtime claude`.

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| Migration corrupts a committed, expensive-to-rebuild file | Runs once under flock, preserves `.pre-metrics`, idempotent, tested |
| A downgraded `pm-status.py` misreads a migrated file | Narrow by construction (one version-guarded runtime copy per project); documented, not engineered around |
| The counterfactual `man_hours` anchors on its estimate | Closure step computes before reading the estimate; the ratio drifting to 1.0 is the detectable symptom |
| The cold-start token mix is an invented number | Labeled as an assumption, superseded by measurement at 3 samples, and it affects only the *split* — the banded total is unaffected |
| Orchestration stays unestimated for three sprints | Explicit warning on every roll-up; better than a prior known to encode a defect |
| Shipped rates go stale between releases | Cost is frozen at capture; `rates` subcommand makes the effective table inspectable; config override available |

---

## 12. Decisions log

| Question | Decision |
|---|---|
| Token representation | Structured by class; total banded and calibrated, classes price it |
| Rate home | Shipped model-keyed defaults + `custom/` config override |
| Orchestration modeling | Fourth calibration component, band unseeded |
| `man_hours` / `time_hours` | Keep `man_hours` as counterfactual developer effort; add `hitl_hours`; unify the `time_hours`/`elapsed_hours` naming |
| Counterfactual actual | Re-assessed at closure with the estimate hidden |
| Calibration migration | Selective, in place, `version` stays `2` |
| Wait protocol | Contract clause in three places + stall detection in `report` |
