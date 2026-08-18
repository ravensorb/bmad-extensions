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
an `estimate` block and an `actual` block, and each block covers all five metrics.**

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

## 2. The five metrics

`METRIC_FIELDS` in `pm-status.py` is exactly `("elapsed_hours", "man_hours", "hitl_hours",
"tokens_k", "cost")`, in that order. That order is canonical wherever the five are listed.

| Metric | Meaning | Unit | Observable? |
|---|---|---|---|
| `elapsed_hours` | AI wall-clock time from dispatch to completion | hours (decimal) | Yes |
| `man_hours` | **Counterfactual** — what a developer, working without AI assistance, would have needed to deliver this work | hours (decimal) | **No — re-assessed at closure, not observed** |
| `hitl_hours` | Human attention actually spent supervising the run | hours (decimal) | Yes |
| `tokens_k` | Total tokens consumed — a **mapping**, not a scalar (see below) | thousands (K) | Yes (Claude); N/A elsewhere |
| `cost` | Billed cost for those tokens | USD (decimal) | **No — derived, never entered** |

**`man_hours` is counterfactual, not an observation of the run.** It answers "how long would
a human developer have taken to build exactly what this diff, these tests, and this scope
delivered?" — assessed by reviewing the delivered work itself, at closure. It is **not** a
self-report of how long the dev/review subagents ran (that is `elapsed_hours`), and it is
**not** derived by any formula from the other metrics. **Anti-anchoring requirement:** form
this number **before** reading the node's own `estimate.man_hours` (or any report that shows
it) — reading the estimate first anchors the re-assessment toward it. This requirement is
agent discipline, "specified, not mechanized" (§9) — no script enforces the read order. The
closure step files (`steps/sprint/step-04-sprint-closure.md`, `steps/execute/step-06-epic-closure.md`)
place the re-assessment as their first step for exactly this reason.

**`hitl_hours` is new and observable.** It is the human's own supervisory attention — reading
output, approving a gate, redirecting a stuck run — not the AI's wall-clock time and not a
developer counterfactual. Cold-start bands (per `BASE_BANDS`, §6): simple 0.1–0.3, standard
0.2–0.5, complex 0.3–1.0.

**`elapsed_hours` is the only wall-clock name.** There used to be a differently-spelled
wall-clock key on the estimate side (a "time hours" name) and `elapsed_hours` on the actual
side — two names for the same metric, needing a translation table (`ESTIMATE_TO_ACTUAL`)
everywhere the two were compared. That table is gone: estimate and actual now use the **same
field name**, `elapsed_hours`, at every level. The old estimate-side flags survive on
`set-estimate` only as **deprecated CLI aliases** (`--time-hours`/`--time-hours-low`/
`--time-hours-high`) that write the `elapsed_hours*` keys — the old key name does not appear
on disk anywhere, in a freshly-written node.

**`tokens_k` is a mapping, not a scalar**, wherever it is written by the mechanized paths
(`estimate-story`, `estimate-rollup`, `set-actual`):

```yaml
tokens_k:
  total: 320          # what is banded, calibrated, and priced
  input: 48
  output: 16
  cache_write: 96
  cache_read: 160
```

`total` is stored, not recomputed on read, so a node stays self-describing to anything that
does not know the class list — but it is always the class sum, and `verify` checks that (§5).
The **total** is what activates scope/closure/orchestration calibration and what a report
shows by default; the **class split** exists only to price `cost` and to make an input/output
or cache-hit-rate mix shift visible. `TOKEN_CLASSES` is `("input", "output", "cache_write",
"cache_read")`, in that order.

**`cost` is derived, never entered.** `cost = Σ(class tokens × that class's per-model rate) /
1000`, computed once at capture time (inside `set-actual`, `estimate-story`, or
`estimate-rollup`) and frozen on the node alongside the `model` field that priced it.
`set-actual` and `set-estimate` **reject** `--cost`/`--cost-low`/`--cost-high` outright — exit
`2` — with a message pointing at the token counts or `modules.l3io-pm.token_rates` instead.
`verify` recomputes `cost` from the stored `tokens_k` and `model` and fails if they disagree by
more than $0.005 (§5) — a hand-edited `cost` cannot survive `verify`.

**Rate table.** `TOKEN_RATES` in `pm-status.py` is a per-model, per-class USD-per-million-token
table (Anthropic first-party rates). It is overridable via `modules.l3io-pm.token_rates`
(merged in, not replaced — an override for one model does not blank the rest) and reaches the
CLI as `--token-rates '<json>'` on `set-actual`, `set-estimate`* , `estimate-story`,
`estimate-rollup`, `verify`, and `rates`. An unknown model is a hard error (`KeyError`, exit
`2`) — never a silent default; a silently-wrong rate is exactly the failure this model exists
to remove. `--model` is **required** whenever any `--tokens-*` flag is given: the same token
count prices roughly 2× apart between, e.g., a $3/M and a $10/M-input tier, so there is no
safe default to fall back to. `pm-status.py rates [--model ID] [--token-rates JSON]` prints
the effective table (read-only) so the value actually in force — including any override — is
inspectable without reading source or guessing.

*(`set-estimate` accepts `--token-rates` too, but only to reject `--cost*` with a clear usage
error, per the point above — it never derives a cost itself; only `estimate-story`/
`estimate-rollup` do.)*

### Field names on disk

Because estimate and actual now share field names, the schema is closer to symmetric than it
used to be — but two divergences remain and matter:

```yaml
# story node — estimate is single values
estimate:
  man_hours: 6
  hitl_hours: 0.8
  elapsed_hours: 1.5
  tokens_k: {total: 320, input: 48, output: 16, cache_write: 96, cache_read: 160}
  cost: 4.80                # derived by estimate-story from tokens_k x rates; never entered
  model: claude-opus-5
  confidence: high           # low | medium | high
  fix_factor: 1.25           # the fix multiplier applied (one per classification)
  scope_ratios:               # the scope ratio applied, PER CALIBRATED METRIC — load-bearing
    man_hours: 1.1            #   (see §8: the sample divides these back out)
    hitl_hours: 1.0
    elapsed_hours: 1.0
    tokens_k: 1.0

# sprint and epic nodes — estimate is low/high ranges
estimate:
  man_hours_low: 12
  man_hours_high: 18
  hitl_hours_low: 1.5
  hitl_hours_high: 2.5
  elapsed_hours_low: 2.5
  elapsed_hours_high: 4
  tokens_k_min: 600
  tokens_k_max: 950
  cost_low: 9.00              # derived by estimate-rollup from tokens_k_min/max x rates
  cost_high: 14.25
  model: claude-opus-5
  closure_ratios:              # the closure ratio applied, PER CALIBRATED METRIC — load-bearing
    man_hours: 1.14            #   (see §8; 1.0 means the cold-start band applied)
    hitl_hours: 1.0
    elapsed_hours: 1.0
    tokens_k: 1.0
  orchestration_ratios:        # the orchestration FRACTION applied, per calibrated metric
    man_hours: 0               #   (0 while unseeded — see §6, §8)
    hitl_hours: 0.09
    elapsed_hours: 0.11
    tokens_k: 0
  confidence: high

# actual — identical shape at story, sprint, and epic level; always single values
actual:
  elapsed_hours: 3.2
  man_hours: 15               # counterfactual re-assessment at closure — NOT observed
  hitl_hours: 1.8
  tokens_k: {total: 812, input: 122, output: 41, cache_write: 244, cache_read: 405}
  cost: 12.18                 # derived; written by the tool, never by hand
  model: claude-sonnet-5

# sprint/epic only — the orchestrator's own overhead, a SEPARATE block from `actual`
orchestration:
  elapsed_hours: 0.6
  man_hours: 0                # AI-only overhead; no human-developer counterfactual
  hitl_hours: 0.1
  tokens_k: {total: 90, input: 14, output: 5, cache_write: 27, cache_read: 44}
  cost: 1.35
  model: claude-sonnet-5

# stamped by set-actual once the node's calibration sample has been emitted;
# a later set-actual on the same block records nothing (§8, Idempotency)
calibration_sampled_at: '2026-08-16T22:34:03Z'
orchestration_sampled_at: '2026-08-16T22:41:10Z'   # separate marker for the orchestration block
```

**Divergence 1 — `tokens_k`'s shape depends on which command wrote it.** The mechanized paths
(`estimate-story`, `estimate-rollup`, `set-actual`) always write the full mapping above. The
**manual** `set-estimate` path writes `tokens_k` (story) / `tokens_k_min`/`tokens_k_max`
(sprint, epic) as a **plain scalar** — it has no per-class flags, so there is nothing to build
a mapping from. Every reader that needs a metric's numeric value — `_estimate_metric`,
`_actual_metric` — checks for the mapping shape first (`hasattr(v, "get")`) and falls back to
treating a bare scalar as the total, so both shapes read correctly; but a story estimated by
hand through `set-estimate` will show a scalar `tokens_k` next to a mechanized sibling's
mapping. Prefer `estimate-story`/`estimate-rollup` for anything that should carry a class
split.

**Divergence 2 — `cost`'s on-disk type is command-dependent.** The writers disagree, and the
docs follow the code rather than pretending otherwise:

| Writer | `cost` is written as |
|---|---|
| `set-actual` | a **string** (`_coerce` special-cases `cost` to never int-coerce it) |
| `estimate-story` | a **float** (`round(value, 2)`) |
| `estimate-rollup` | a **float** (`round(value, 2)`) |

Every reader on the calibration and roll-up paths goes through `_num_or_none`, which parses
both forms (and strips a leading `$`), so the divergence is harmless there and was left
alone deliberately: normalizing it would rewrite the quoting of every existing state file
for no behavioural gain. `_accumulate_actuals` (what `show` sums) is the one reader that
does a bare `float()` — it handles a plain numeric string fine but **drops a `$`-prefixed
value silently**.

So: pass a **bare decimal with no currency symbol** if you are ever constructing one by hand
for a test or a backfill — `4.80`, never `'$4.80'`. Currency symbols belong in prose reports,
never in the state files. In normal operation this never arises: `cost` is derived, not typed
in.

`tokens_k.total` (and each class) is stored as an int when the value is integral, otherwise a
float. `elapsed_hours`, `man_hours`, and `hitl_hours` are floats.

## 3. Runtime detection and capture

Two runtimes are recognized: `claude` and `other`. Every metric-writing call takes
`--runtime {claude,other}`, and it **defaults to `other`** — the permissive value. Bind
`{runtime}` at activation and pass it explicitly on every `set-actual` and `verify` call;
relying on the default silently disables the strict path.

### Under `--runtime claude`

`elapsed_hours`, `man_hours`, and `hitl_hours` are always real numbers — no runtime has an
`N/A` path for these three. Tokens are captured **exactly**: sum `input_tokens`,
`output_tokens`, and the two cache-token classes from the session transcript's `usage`
fields, scoped to the messages belonging to the node being closed, convert to thousands, and
pass them as `--tokens-input`/`--tokens-output`/`--tokens-cache-write`/`--tokens-cache-read`
along with `--model`. `set-actual` derives `tokens_k` (the mapping) and `cost` from them —
never pass `--cost`; it is rejected.

`N/A` (via `--tokens-na`) is **forbidden** for tokens here — `set-actual` exits `2` if
`--tokens-na` is combined with `--runtime claude`. This is the mechanical enforcement point of
the HARD RULE (§5).

### Under `--runtime other`

Capture whatever the runtime exposes. If tokens are genuinely not observable (e.g. Copilot),
pass `--tokens-na`, which records both `tokens_k` and `cost` as the literal string `N/A`.
`--tokens-na` cannot be combined with any explicit `--tokens-*` count — pick one or the other.

**Never estimate, extrapolate, or back-calculate a token or cost actual.** A guessed actual
is worse than a missing one: `N/A` is skipped by calibration, whereas a guess is
indistinguishable from a measurement and permanently corrupts the learned ratio. `man_hours`
and `hitl_hours` are always observable/assessable and must always be real numbers, on every
runtime — there is no `N/A` for either, ever.

Values treated as `N/A` by `_is_na`: `N/A`, `NA`, `NONE`, and the empty string, in any
case, after stripping. An **absent** field is not the same as `N/A` — absence fails
`verify`, an explicit `N/A` passes it under `--runtime other`.

## 4. Writing estimates and actuals

All writes go through `pm-status.py`. Never hand-edit a state file.

**`set-estimate` is the direct, manual write** — pass every field yourself. The bottom-up
flow (`step-estimate.md`) does not call it: it uses `estimate-story` (classification in,
band × calibrated ratio × fix factor out, `cost` priced from the resulting `tokens_k`) and
`estimate-rollup` (children in, closure- and orchestration-widened range out, `cost` priced
from the rolled-up `tokens_k` range) instead, so the arithmetic runs once, in `pm-status.py`,
not in step-file prose. `set-estimate` still exists for a manual override or any write outside
that flow.

```bash
# story estimate — single-value aliases
python3 {pm_status} set-estimate --state-root {pm_state_root} \
  --story E001-S01-003 \
  --man-hours 6 --hitl-hours 0.8 --elapsed-hours 1.5 --tokens-k 320 \
  --confidence high

# sprint or epic estimate — ranges
python3 {pm_status} set-estimate --state-root {pm_state_root} \
  --epic E001 [--sprint S01] \
  --man-hours-low 12 --man-hours-high 18 \
  --hitl-hours-low 1.5 --hitl-hours-high 2.5 \
  --elapsed-hours-low 2.5 --elapsed-hours-high 4 \
  --tokens-k-min 600 --tokens-k-max 950 \
  --confidence high

# actual — same metric flags at every level; tokens are per-class, cost is derived
python3 {pm_status} set-actual --state-root {pm_state_root} \
  --node {story|sprint|epic} (--story KEY | --epic ID [--sprint ID]) \
  --runtime {runtime} \
  --elapsed-hours 3.2 --man-hours 15 --hitl-hours 1.8 \
  --tokens-input 122 --tokens-output 41 --tokens-cache-write 244 --tokens-cache-read 405 \
  --model claude-sonnet-5

# orchestration block — sprint/epic only, never story; --man-hours 0 always (AI-only overhead)
python3 {pm_status} set-actual --state-root {pm_state_root} \
  --node {sprint|epic} --epic ID [--sprint ID] --block orchestration \
  --runtime {runtime} \
  --elapsed-hours 0.6 --man-hours 0 --hitl-hours 0.1 \
  --tokens-input 14 --tokens-output 5 --tokens-cache-write 27 --tokens-cache-read 44 \
  --model claude-sonnet-5
```

`--cost`/`--cost-low`/`--cost-high` on either subcommand are **rejected, exit 2** — "cost is
derived from tokens x rates and cannot be set directly." Fix the token counts or
`modules.l3io-pm.token_rates` instead.

Node kind for `set-estimate` is **inferred** from which selector flags are present
(`--story` → story; `--epic` with or without `--sprint` → sprint/epic). `set-actual` takes
an explicit `--node`.

**`--block {actual,orchestration}`** (default `actual`) selects which block `set-actual`
writes. `--block orchestration` on a story node is a **usage error, exit 2** — a story's
orchestration overhead belongs to its parent sprint, not to itself. Everything else about the
call (flags, calibration side effect, event logging) works the same for either block; only the
target block and which calibration component samples (§8) differ.

**Flag/kind mismatches are silently ignored, not rejected.** On a story node the range
flags are dropped; on a sprint or epic node the single-value flags are dropped. `--tokens-k`
and `--tokens-k-min` share an argparse destination (the alias exists for the story form), so
passing both in one `set-estimate` call means the last one parsed wins. Use exactly the form
that matches the node kind.

`--confidence` is optional. When omitted and no confidence is already set, it is **derived**:
`medium` if every field for that kind is present, `low` otherwise. It is never derived as
`high` — pass `--confidence high` explicitly when the calibration data justifies it (§8). Note
that `set-estimate`'s own completeness check for a story still names `cost` among the fields
it looks for even though `set-estimate` itself never writes `cost` (only `estimate-story`
does) — a story estimated purely by hand through `set-estimate` therefore never reaches
`medium` confidence on that path alone.

Write the actual, the completion evidence, and the status transition as separate calls, then
gate on `verify`. Story closeout additionally requires `completion_evidence` (written via
`set-field`), which `verify --scope story` checks.

## 5. Enforcement — what is actually checked, and where

The HARD RULE is enforced in **two halves**. Neither half alone is sufficient, so both must
run.

### Half 1 — `set-actual`, at write time

Under `--runtime claude`, passing `--tokens-na` (in place of the `--tokens-*` counts) is a
**usage error, exit 2**, with a message pointing at the exact per-class capture procedure in
this file. `--cost`/`--cost-low`/`--cost-high` are rejected on **every** runtime, unconditionally
— cost has no runtime exemption because it is never entered at all.

Limits of this check, which the orchestrator must compensate for:

- It only inspects metrics **actually passed**. `set-actual` requires at least one of
  `--elapsed-hours`/`--man-hours`/`--hitl-hours`/`--tokens-*`/`--tokens-na`, not all of them —
  under `--runtime claude`, simply *omitting* the token flags succeeds (exit 0). Always pass
  every metric in one call.
- It does not apply to `elapsed_hours`, `man_hours`, or `hitl_hours`; those are caught later by
  `verify`, which requires them to be numeric on every runtime.

### Half 2 — `verify`, at read-back

`verify` is the completeness gate. `--scope story` and `--scope sprint` check **completion
of one node**:

- `status == done`
- all five `actual.*` fields **present**
- `elapsed_hours`, `man_hours`, and `hitl_hours` numeric and not `N/A`
- `tokens_k` and `cost` may be `N/A` **only** under `--runtime other` and without
  `--require-tokens`; `--runtime claude` or `--require-tokens` makes `N/A` a failure
- when `tokens_k` is the structured mapping, `tokens_k.total` must equal the sum of its four
  classes (tolerance 0.01, wider than `cost`'s because `total` is rounded at write time and an
  unrounded re-sum can legitimately differ by up to half the last decimal place)
- `cost` must equal what `tokens_k` prices out to under the node's own `model` and the
  effective rate table (tolerance $0.005 — half of the smallest unit either figure can carry).
  A hand-edited `cost`, or a `tokens_k` edited without re-deriving `cost`, fails here. A missing
  `model` when `tokens_k` is structured also fails ("cost cannot be verified")
- `completion_evidence` present (story scope only)

```bash
python3 {pm_status} verify --state-root {pm_state_root} \
  --scope {story|sprint} (--story KEY | --epic ID --sprint ID) \
  --runtime {runtime} [--require-tokens] [--token-rates JSON]
```

`--scope epic` is a **different check**: it walks the epic's whole subtree and validates
structural / back-reference integrity (every sprint directory has a `sprint.yaml`; every
sprint and story file carries `epic:`/`sprint:` back-references matching its directory). It
does **not** look at `status`, `estimate`, or `actual` at all. See `status-files.md` §7.

Exit codes (identical across all subcommands):

| Code | Meaning |
|---|---|
| `0` | Success / verified |
| `2` | Usage error — including `runtime=claude` + `--tokens-na`, and any `--cost*` flag |
| `3` | Node not found |
| `4` | Verification failure (missing/invalid field, cost/token mismatch, or structural mismatch) |
| `5` | Epic locked by another session |

### What is *not* enforced

- **No machine check on the `estimate` block, ever.** `verify` inspects `actual` only.
  `set-estimate` has no required flags and never fails on an incomplete estimate — it
  records `confidence: low` instead. The estimate half of the HARD RULE is orchestrator
  discipline, as is the anti-anchoring read-order for `man_hours` (§2) — no script checks
  either.
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
children plus a closure band plus an orchestration band, so they reconcile with their children
by construction. Do not compute a sprint or epic estimate by any independent formula —
parallel formulas drift.

Per calibrated metric (`elapsed_hours`, `man_hours`, `hitl_hours`, `tokens_k` — never `cost`,
which is priced separately, below):

```
story.estimate  = base_band(classification) × scope_ratio × fix_mult
sprint.estimate = Σ story.estimate + calibrated sprint-closure band + calibrated orchestration band
epic.estimate   = Σ sprint.estimate  + calibrated epic-closure band + calibrated orchestration band
```

### Base bands (cold-start priors, per story)

`BASE_BANDS` in `pm-status.py` is the single source for these — do not copy the numbers into
a second table that can drift out of sync. It has **no `cost` row** — see "Pricing `cost`"
below. `estimate-story` reads it directly:

```bash
python3 {pm_status} estimate-story --state-root {pm_state_root} \
  --story {story_key} --classification {simple|standard|complex} \
  [--confidence {low|medium|high}] [--model ID] [--token-rates JSON]
```

| Classification | man_hours | hitl_hours | elapsed_hours | tokens_k |
|---|---|---|---|---|
| simple | 2–4 | 0.1–0.3 | 0.5–1.5 | 20–50 |
| standard | 4–8 | 0.2–0.5 | 1–3 | 40–100 |
| complex | 8–16 | 0.3–1.0 | 2–6 | 80–200 |

The model's only job is choosing the classification; `estimate-story` looks up the band,
applies the calibrated `scope_ratio` (per metric) and `fix_factor`, and writes the estimate
block. See §8 for how those two multipliers are derived.

Stories store the band **midpoint × ratio × fix** as a single value per metric; ranges appear
only at sprint and epic level.

**`estimate-story` records one ratio PER CALIBRATED METRIC**, as `estimate.scope_ratios`. This
is load-bearing, not provenance: `derive_story_sample` divides the applied ratio back out so the
next sample is measured against the base band (§8), and four independently calibrated metrics
cannot be reconstructed from one recorded number. A scalar `scope_ratio` (what
`set-estimate --scope-ratio` writes, or an estimate written before per-metric ratios existed)
is still *read* as a fallback for every metric, but `estimate-story` no longer writes it.

### Pricing `cost`

`cost` is **not** one of the banded/calibrated metrics. `estimate-story` prices it by splitting
the banded `tokens_k` total across the four classes — using `observed_mix` (the mean observed
split once ≥3 story samples carry class data) or, below that, the cold-start assumption
`COLD_START_TOKEN_MIX = {input: 0.15, output: 0.05, cache_write: 0.30, cache_read: 0.50}` — and
running the split through `cost_from_tokens` for `--model` (falling back to
`DEFAULT_ESTIMATE_MODEL = "claude-opus-5"` when omitted). `estimate-rollup` does the same for
the rolled-up `tokens_k_min`/`tokens_k_max` range. This keeps `cost` arithmetically bound to
the token estimate it prices — it cannot drift apart from it the way an independently banded
and independently calibrated cost figure could (and, before this rework, did).

`COLD_START_TOKEN_MIX` is an **assumption, not a measurement** — it affects only how a banded
total is *split* across classes, never the banded total itself. `observed_mix` reads
`cal["token_mix"]["samples"]`, a list of per-story observed class fractions recorded by
`record_story_sample` whenever a story's actual `tokens_k` mapping has a positive `total`; it
is a derived statistic, not a calibration *component* — it has no activation threshold beyond
requiring ≥3 usable samples (`MIN_SAMPLES`), and it never appears in `CALIBRATED_METRIC_FIELDS`.

### Roll-up mechanics

`estimate-rollup` computes the sprint/epic range from its children plus a closure band plus an
orchestration band:

```bash
python3 {pm_status} estimate-rollup --state-root {pm_state_root} --epic {epic_key} --sprint {sprint_key} [--model ID] [--token-rates JSON]
python3 {pm_status} estimate-rollup --state-root {pm_state_root} --epic {epic_key} [--model ID] [--token-rates JSON]
```

For each calibrated metric:

- `total` = Σ child estimate for that metric (a story's single value, or a sprint's range
  midpoint).
- Closure band: apply the calibrated `closure` ratio for that level when it has activated
  (`total × (1 + ratio × band)`); otherwise the cold-start band applies at both ends, which
  is the same formula at `ratio = 1.0` (`COLD_START_CLOSURE_BAND = (0.10, 0.25)` —
  **10%/25% at every level**, sprint and epic alike; there is no separate 15%/20% split).
- Orchestration band: apply the calibrated `orchestration` **fraction** for that level when it
  has activated (`total × fraction × ORCH_SPREAD`, `ORCH_SPREAD = (0.8, 1.2)`); otherwise it
  contributes **nothing** — there is no cold-start prior for orchestration, unlike closure (see
  §8's `active_orchestration_fraction` for why: every measurement available when this was
  designed was contaminated by a cache-eviction defect, so there was nothing safe to seed a
  prior from). `estimate-rollup` warns on stderr, naming the inactive metrics, whenever
  **any** calibrated metric's orchestration component is still unseeded at that level — this
  estimate is known-low on those metrics until real observations exist.
- The combined low/high bound for a metric is:
  `total × (1 + closure_ratio × COLD_START_CLOSURE_BAND[i] + orch_fraction × ORCH_SPREAD[i])`
  for `i` = low, high.
- The applied closure ratios and orchestration fractions are recorded per metric as
  `estimate.closure_ratios` and `estimate.orchestration_ratios`, for the same reason
  `estimate.scope_ratios` exists on a story: the closure/orchestration sample divides them
  back out (§8).

`cost_low`/`cost_high` are then priced from `tokens_k_min`/`tokens_k_max` as described above,
under "Pricing `cost`."

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

Activation for `fix` is stricter than for `scope`/`closure`/`orchestration` — see §8 for why it
needs **both** cohorts (`clean` and `reworked`) at ≥3 samples, not just ≥3 samples of one thing.

**`fix_mult` applies to every calibrated metric** — `estimate-story` multiplies each of
`man_hours`, `hitl_hours`, `elapsed_hours`, and `tokens_k` by the same `scope_ratio ×
fix_mult` for that metric. `cost` has no `fix_mult` of its own to apply: it is priced from the
already-fix-adjusted `tokens_k`, so the fix reserve reaches it indirectly, through the token
total it prices.

## 8. Calibration

### Location

| Binding | Resolves to |
|---|---|
| `{pm_calibration_file}` | `{pm_state_root}/pm-calibration.yaml` = `{implementation_artifacts}/state/pm-calibration.yaml` |

The file is **committed**. Learned ratios are team knowledge and expensive to rebuild —
several closed sprints of real work each. It sits beside `issues.yaml` in the state root and
moves nowhere when epics move between `planned/`, `active/`, and `archived/`.

### Four separable components

Each component learns per metric. `scope`, `closure`, and `orchestration` each **activate
independently per metric** at **≥3 samples**. `fix` is stricter — see "The `fix` cohorts"
below.

| Component | Learns | Sampled at |
|---|---|---|
| `scope` | story sizing ratio, per classification | inside `set-actual --node story` |
| `closure` | closure overhead ratio, separately for sprint and epic level | inside `set-actual --node sprint\|epic` |
| `fix` | fix cost, per classification (`clean` vs `reworked` cohorts) | inside `set-actual --node story` |
| `orchestration` | orchestration overhead as a **fraction** of children's actuals, separately for sprint and epic level | inside `set-actual --block orchestration --node sprint\|epic` |

`CALIBRATED_METRIC_FIELDS` is `METRIC_FIELDS` minus `cost` — `("elapsed_hours", "man_hours",
"hitl_hours", "tokens_k")`. `cost` never calibrates on any component, at any level: it is
derived from `tokens_k × rates`, so letting it also accumulate an independently-learned
correction would give a derived value its own drift, undoing exactly what deriving it was for.

Splitting the four components matters because they fail differently: `scope` drifts with
codebase familiarity, `closure` is a near-fixed per-sprint tax that a single blended ratio
hides entirely, `fix` tracks review strictness, and `orchestration` tracks how much
supervision/coordination overhead a run actually needs. A component below its activation
threshold uses its cold-start prior — ratio `1.0` for `scope`/`closure`, `F` = `1.25` for
`fix`, and **nothing** for `orchestration` — while its siblings may already be calibrated.

**`orchestration` learns a FRACTION, not a ratio — the one component that does.** Every other
component corrects an existing number: a ratio is `actual / estimate`-shaped, dividing out
what was already applied. Orchestration has no such number to correct: its band ships
unseeded by design, because the only overhead measurements available when this was built were
contaminated by an operational defect (roughly thirty blocking waits that each outlived the
prompt cache and re-created a ~93k-token prefix), and sizing a cold-start prior on that data
would have committed the bug to every future estimate. So the sample **is** the band:
`orchestration_actual / Σ children's actual`, for a given metric, directly observable from the
first closed sprint or epic that carries an `orchestration` block. This is why
`active_orchestration_fraction` returns `None` (not a cold-start value) below `MIN_SAMPLES` —
there is nothing to fall back to.

### Sample weighting

`scope`, `closure`, and `orchestration` samples are **exponentially decay-weighted with decay
0.8** (`weighted_ratio`) — the most recent sample carries weight 1, the one before it 0.8, then
0.64, and so on. Recent work is a better predictor than early-project work, and the decay
lets ratios (or, for orchestration, fractions) track a changing codebase or process without
any explicit window or manual reset.

`fix` does **not** use decay weighting — each cohort (`clean`/`reworked`) keeps a running
**mean**, updated in place (`_bump_cohort`), not a sample list. See "The `fix` cohorts"
below.

### Token samples and the observed mix

`tokens_k` ratios accumulate **only from runs with real actuals** — the guard is generic
(`_num_or_none` rejects `N/A`/non-numeric), so it applies on every runtime, but in practice
only Claude runs supply real token values. An `N/A` or missing value is skipped entirely for
that metric, never imputed, never counted toward the ≥3 activation threshold — the other
calibrated metrics on the same story still record. A project run mostly on other runtimes
therefore keeps calibrated `man_hours`, `hitl_hours`, and `elapsed_hours` while `tokens_k`
legitimately stays at cold-start.

Separately, `record_story_sample` also appends to `cal["token_mix"]["samples"]` whenever a
story's actual `tokens_k` mapping has a positive total — the observed per-class split as a
fraction of that total. This is **not** a calibration component (§6): it feeds `observed_mix`,
which supplies the class split used to price `cost` at estimate time, once ≥3 usable samples
exist; below that, `COLD_START_TOKEN_MIX` (an assumption, not a measurement) is used instead.

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
calibrated metric, using `estimate.scope_ratios[metric]` (falling back to a scalar
`scope_ratio`, then to `1.0`).

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

**Because `man_hours`'s definition changed, its `clean`/`reworked` cohort mean is now a mean
of counterfactual re-assessments, not observed effort.** The mechanics above are unaffected —
`_bump_cohort` still accumulates whatever `actual.man_hours` says — but a project migrating
from before this rework must not mix pre- and post-rework `man_hours` samples in the same
cohort mean; that is exactly what the metrics migration (below) quarantines.

**`fix_iterations` must be on the node BEFORE `set-actual` runs.** The sample is derived
inside `set-actual`, so evidence written afterwards is invisible to it:
`provenance: exact` becomes unreachable, neither `fix` cohort ever fills, and `F` = 1.25
freezes. `steps/sprint/step-03-dev-loop.md` §4 writes the completion evidence first for
exactly this reason.

`derive_story_sample` returns `None` — no sample at all — when the node has no `estimate` or
no `actual` block, or when every calibrated metric's estimate/actual pair is
missing/`N/A`/zero.

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

Closure sampling skips **per metric, with a reason**, never aborting the other metrics'
samples: a child missing that metric's actual or estimate (a partial sum understates
overhead, permanently, since a low ratio has no marker saying it was incomplete); an
estimated closure overhead of `≤ 0` (nothing to measure the residual against); a negative
residual (a miscount — except for `elapsed_hours`, where a negative residual is *expected*
if children ever overlap in wall-clock time; today's step files run children strictly in
order, so this is defensive, not currently reachable); and an `N/A` `tokens_k` on either
side. Only when *no* calibrated metric produces a residual is the whole sample skipped.

### The orchestration sample — denominator completeness

```
sample(metric) = orchestration.actual(metric) / Σ children's actual(metric)
```

recorded only when **every** child has a numeric actual for that metric — a partial sum would
silently understate the true total and inflate the fraction, permanently and invisibly. This
is the same completeness guard `derive_closure_sample` applies to its residual, reused here
rather than duplicated. `cost` is not sampled (it is outside `CALIBRATED_METRIC_FIELDS`); its
fraction is already implied by the `tokens_k` fraction, and a second, independently-drifting
copy would add nothing but disagreement.

### Idempotency

`set-actual` stamps `calibration_sampled_at` on the node once it has emitted that node's
`actual`-block sample, and a separate `orchestration_sampled_at` once it has emitted the
`orchestration`-block sample — **two markers on one node**, deliberately independent: a
sprint or epic node carries both an `actual` and an `orchestration` block, and one marker
would let whichever write happens first silently suppress the other. A second `set-actual`
on the same block records nothing and says so in its stdout suffix (`sample already recorded
at … — skipped (replay)`). `--no-calibrate` still exists for backfills, but correctness no
longer depends on the caller remembering it.

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
using — the asymmetry (unlike `scope`/`closure`/`orchestration`, which activate on a single
count) is deliberate, not a bug.

### Granularity

`granularity` lives **in the calibration file itself** (`new_calibration`'s `granularity`
key), not bound from a step file or `customize.toml` — nothing currently varies it, so every
project effectively runs `"story"` granularity: `set-actual --node story` records one scope
sample and (when derivable) one fix-cohort update per closed story; `set-actual --node
sprint|epic` records one closure sample per closed sprint/epic, unconditionally, and
`set-actual --block orchestration --node sprint|epic` records one orchestration sample per
closed sprint/epic that carries an `orchestration` block. There is no `"sprint"`-granularity
aggregation path in the shipped code — a project cannot presently opt into coarser story
sampling by changing this key. `calibration show` prints whatever value is stored for
information only; it does not change any sampling behavior.

### Schema

```yaml
version: 2
granularity: story
metrics_migrated_at: '2026-08-18T09:00:00Z'   # present once the metrics migration (below) has run
scope:
  simple:   { man_hours: {samples: [1.02, 1.14, 0.98]}, hitl_hours: {...}, elapsed_hours: {...}, tokens_k: {...} }
  standard: { ... }
  complex:  { ... }
closure:
  sprint:   { man_hours: {samples: [1.18, 1.05, 1.22, 0.97]}, ... }
  epic:     { ... }
orchestration:                                  # per level x per calibrated metric; FRACTION samples
  sprint:   { man_hours: {samples: [0.08, 0.11, 0.09]}, hitl_hours: {...}, elapsed_hours: {...}, tokens_k: {...} }
  epic:     { ... }
fix:
  simple:   { clean: {mean_man_hours: 3.1, samples: 4}, reworked: {mean_man_hours: 4.2, samples: 3} }
  standard: { ... }
  complex:  { ... }
token_mix:                                      # derived statistic, not a calibration component
  samples:
  - { input: 0.14, output: 0.06, cache_write: 0.29, cache_read: 0.51 }
legacy:                                          # quarantined pre-rework man_hours/fix samples
  fix: { ... }                                  # never read again by any active path
```

`scope`, `closure`, and `orchestration` entries store the **raw sample list** (`samples:
[...]`, newest last) — the weighted mean (a ratio for `scope`/`closure`, a fraction for
`orchestration`) is computed on read by `weighted_ratio`, never persisted. `fix` entries store
a running **mean and an integer count** per cohort — `avg_fix_factor` is not a file field; it
is `active_fix_factor(cal, classification)`, computed on read from the two cohort means, and
only returned once both cohorts clear `MIN_SAMPLES`.

A `scope` ratio is `actual / band_mid` (or `actual / (band_mid × fix_factor)` on the backout
path), a `closure` ratio is `closure actual / closure expected`, and an `orchestration` sample
is `orchestration_actual / Σ children_actual` — the first two divide the applied ratio back
out per "The scope/fix split" and "Closure sampling" above; orchestration has no prior ratio
to divide out, since it is not correcting anything (see "Four separable components"). A
component below its activation threshold is recorded but **not applied** — `estimate-story`
and `estimate-rollup` fall back to the cold-start prior for that metric/bucket (or, for
orchestration, to contributing nothing).

### The metrics migration (`calibration migrate-metrics`)

A calibration file written **before this metrics rework** — even one already at
`version: 2` under the older four-metric schema — needs reshaping, not just a version bump,
because the metric set itself changed. `migrate_calibration_metrics` does this in place:

- **`cost` samples are dropped**, from every `scope`/`closure`/`orchestration` bucket that has
  one. `cost` is derived now and never independently calibrated again (§2, §6).
- **The old wall-clock samples are renamed to the `elapsed_hours` key**, in every bucket,
  matching the estimate side's field-name unification (§2).
- **`man_hours` samples, and the whole `fix` block, are quarantined under `legacy`** —
  `legacy.<component>.<bucket>.man_hours` for scope/closure, `legacy.fix` wholesale. The
  metric's definition changed from observed human attention to counterfactual developer
  effort, so old samples measure a different quantity and are not comparable; they are kept
  for audit, never read by any active calibration path again.
- **A `tokens_k` weighted ratio outside `TOKENS_SANITY_RANGE = (0.5, 2.0)` is flagged, not
  dropped** — carried forward as-is, with a log line suggesting it may be contaminated by
  orchestration-shaped overhead that leaked into story samples under the old rules (exactly
  the defect `orchestration` now isolates into its own component).
- **`orchestration` and `token_mix` are seeded empty**, but only when this pass actually found
  and moved legacy content (not unconditionally — seeding them on a brand-new project's first,
  no-op pass would recreate a conflict this design deliberately avoids).

This runs **once**, gated on `CALIBRATION_METRICS_MARKER = "metrics_migrated_at"` — a
positive marker stamped at the end of every real pass, **even a no-op one** on a brand-new
project, so a later legitimate `man_hours`/`fix` sample is never revisited and wrongly
quarantined. Once past the gate, `man_hours` and `fix` quarantine **unconditionally** — no
corroborating `cost` sample, or old wall-clock sample, is required in the same bucket, because a
non-Claude-runtime project may never have accumulated `cost`/token samples at all, and
requiring one would leave old-definition `man_hours` silently uncaught. This is **not** a
`version` bump — the schema version stays `2` throughout; `metrics_migrated_at` records a
reshape of the file, not a new schema generation (the same way `orchestration`, `token_mix`,
and `legacy` are data about the file, not schema versions).

The file is preserved beforehand as `pm-calibration.yaml.pre-metrics` (parallel to
`pm-calibration.yaml.v1` for the older version-1-to-2 migration below), and the migration is
idempotent — a second run is a no-op because the marker is already set.

Both `record_story_sample` and `record_closure_sample` (and `record_orchestration_sample`) run
this migration automatically, inline, before appending a new sample — so it happens
transparently the first time any project touches its calibration file after upgrading. It is
also exposed directly:

```bash
python3 {pm_status} calibration migrate-metrics --state-root {pm_state_root} [--format {text,json}]
```

**Never runs from a read-only command.** `calibration show`, `estimate-story`, and
`estimate-rollup` only read the file (`load_calibration`) and never migrate it — a
never-migrated file just reads as "nothing sampled yet" for `man_hours`/`fix`/`orchestration`
until a write path actually runs.

### `version: 1` migration

Distinct from the metrics migration above — this is the older schema-shape migration, still
present and unaffected by this rework. A `version: 1` file is auto-migrated **the first time a
write path touches it** (`record_story_sample` / `record_closure_sample`, both via
`migrate_calibration`). The original is preserved alongside as `pm-calibration.yaml.v1` and is
never read again. Migration maps the old blended ratio onto the `scope` component and starts
`closure`, `fix`, and `orchestration` fresh at zero samples — the old file has no way to
separate them, and seeding them from a blended figure would import exactly the bias the split
exists to remove.

**`load_calibration` never migrates**, either version-1-to-2 or the metrics reshape above. It
is deliberately side-effect-free: `calibration show` and `estimate-story`/`estimate-rollup`
(which only read the file to look up active ratios) call `load_calibration` and treat an
unmigrated file as if the missing components had no samples yet, but they never rewrite it.
Only the sampling write paths migrate, and only at the moment they are about to append.

> The `version:` key is the **calibration file's schema-shape version** (1 vs. 2 — the
> component structure: scope/closure/fix, later joined by orchestration/token_mix/legacy). It
> is unrelated to state *layout* generations ("sharded", "legacy per-epic", "legacy flat") and
> unrelated to `metrics_migrated_at`, which tracks a content reshape within version 2.

### Mechanization status

`pm-status.py` now runs this loop; it is not orchestrator prose.

- **`estimate-story`** and **`estimate-rollup`** read the file (`load_calibration`, never
  migrating) and apply whichever ratios/fractions are active — cold-start priors (or, for
  orchestration, nothing) otherwise.
- **`set-actual`** derives and appends a sample automatically after every successful actuals
  write (`record_story_sample` for `--node story`; `record_closure_sample` for `--node
  sprint|epic` on the `actual` block; `record_orchestration_sample` for the `orchestration`
  block), unless `--no-calibrate` is passed. A derivation failure is caught, warned on
  stderr, and never fails the actuals write — the actual is the primary record; the
  calibration sample is derived, secondary data. The `set-actual` stdout line reports what
  was recorded (e.g. `scope+4 metrics, provenance=exact, class=complex`, or `orchestration
  sprint +3 metrics`) or why nothing was (e.g. `no sample (missing estimate or actual)`).
  **Skip reasons go to stdout**, inside that `[...]` suffix — only an unexpected exception
  warns on stderr.
- **`calibration show`** is read-only. A missing file reports cold-start for every component
  and exits `0` — there is no error state for "no calibration data yet."
- **`calibration migrate-metrics`** performs the one-time reshape described above and reports
  a change log; also run automatically, inline, by the two sampling write paths.

See §9 for the disagreements this closes and the ones that remain open.

## 9. Where `CLAUDE.md` and the code disagree

Documented rather than papered over. In each case the code is authoritative.

1. **"This is enforced, not optional" is true at story and sprint level only.** There is no
   read-back gate on an epic's `actual` block (`verify --scope epic` is structural), and no
   gate on any `estimate` block at any level.

2. **`set-actual` does not require all five metrics.** It requires *at least one*. The
   `--runtime claude` rejection only fires on tokens, and only when tokens were actually
   passed as `--tokens-na`.

3. **`--runtime` defaults to `other`.** The strict path is opt-in per call. A `set-actual`
   or `verify` invocation that forgets `--runtime {runtime}` silently runs permissive.

4. **No `retrospective`-level metric block exists.** See §1.

5. **`--require-tokens` on `verify` is undocumented in `CLAUDE.md`.** It forces the
   Claude-strict token rule irrespective of `--runtime`.

6. **The anti-anchoring read-order for `man_hours` (§2) is agent discipline, not a script
   check.** Nothing in `pm-status.py` inspects when a node's estimate was read relative to
   when its actual was formed; the closure step files enforce the ordering by instruction, not
   by any mechanism `verify` can see.

## 10. Worked example

Story `E001-S01-003`, classification `complex`, cold-start `fix` (no calibration file yet
covers this classification), but `scope.complex.man_hours` already active at ratio `1.10`
(≥3 samples); every other `scope` metric for `complex` is still cold-start (ratio `1.0`).

**Estimate.** The model supplies only the classification:

```bash
python3 {pm_status} estimate-story --state-root {pm_state_root} \
  --story E001-S01-003 --classification complex
# OK estimate-story E001-S01-003 class=complex scope_ratios[man_hours=1.1 hitl_hours=1.0 elapsed_hours=1.0 tokens_k=1.0] fix_factor=1.25
```

`estimate-story` looks up `BASE_BANDS["complex"]` (man_hours 8–16, hitl_hours 0.3–1.0,
elapsed_hours 2–6, tokens_k 80–200), takes each midpoint, and multiplies by that metric's own
scope ratio and the classification's fix multiplier — `fix_mult` = `F` = `1.25` here, since
`fix` has no active cohorts yet:

```
man_hours     = 12    × 1.10 × 1.25 = 16.5      (scope ratio active)
hitl_hours    = 0.65  × 1.00 × 1.25 =  0.81      (scope ratio cold-start)
elapsed_hours =  4    × 1.00 × 1.25 =  5.0       (scope ratio cold-start)
tokens_k      =140    × 1.00 × 1.25 =175         (scope ratio cold-start, rounded to int)
```

`cost` is then priced from that 175K `tokens_k` total: split across the four classes by
`observed_mix` (or, below 3 samples, `COLD_START_TOKEN_MIX`) and run through `cost_from_tokens`
for the model bound at estimate time (`--model`, or `DEFAULT_ESTIMATE_MODEL` if omitted) —
say `cost = 1.22` under the cold-start mix and `claude-opus-5` rates.

The written `estimate.scope_ratios` is `{man_hours: 1.1, hitl_hours: 1.0, elapsed_hours: 1.0,
tokens_k: 1.0}` — one entry per calibrated metric, each the ratio actually applied to that
metric. The sample derivation reads these back individually; a single recorded number could
not reconstruct four different corrections.

**Actual.** The story runs under Claude, needs **one** fix iteration
(`completion_evidence.fix_iterations: 1`, written via `set-field` before closeout). The
closing agent first re-assesses `man_hours` — reviewing the delivered diff and tests, before
reading the estimate above — and settles on 18.2 as the counterfactual developer-hours figure.
Compute hours (6.1) and human-attention hours (0.9) are read from the run itself, and the four
token classes (say totaling 171K) are read from the transcript `usage` fields:

```bash
python3 {pm_status} set-actual --state-root {pm_state_root} \
  --node story --story E001-S01-003 --runtime claude \
  --elapsed-hours 6.1 --man-hours 18.2 --hitl-hours 0.9 \
  --tokens-input 26 --tokens-output 9 --tokens-cache-write 51 --tokens-cache-read 85 \
  --model claude-opus-5
# OK set-actual E001-S01-003 ['cost', 'elapsed_hours', 'hitl_hours', 'man_hours', 'model', 'tokens_k'] [scope+4 metrics, provenance=backout, class=complex]

python3 {pm_status} set-status --state-root {pm_state_root} \
  --story E001-S01-003 --status done

python3 {pm_status} verify --state-root {pm_state_root} \
  --scope story --story E001-S01-003 --runtime claude
# PASS E001-S01-003
```

Had `--tokens-na` been passed with `--runtime claude`, `set-actual` would have exited **2**
before writing anything, and no calibration sample would have been derived. Had `--cost 1.24`
been passed instead of letting it derive, `set-actual` would have exited **2** for the same
reason — cost is never an input.

**What `set-actual` derived, inline.** `fix_iterations` is `1`, not `0`, so this is the
**backout** path: the actual mixes scope and rework, the scope portion is `actual ÷
fix_factor`, and the `fix_factor` cancels out of the ratio. Each calibrated metric divides its
own applied `scope_ratios` entry back out, so the comparison lands against the base band:

```
man_hours scope ratio     = 18.2 × 1.10 /  16.5 = 1.2133   ( = 18.2 /  (12   × 1.25) )
hitl_hours scope ratio    =  0.9 × 1.00 /  0.81 = 1.1111   ( =  0.9 / (0.65  × 1.25) )
elapsed_hours scope ratio =  6.1 × 1.00 /  5.0  = 1.2200   ( =  6.1 /  ( 4   × 1.25) )
tokens_k scope ratio      =  171 × 1.00 / 175   = 0.9771   ( =  171 / (140   × 1.25) )
```

Each is appended to `scope.complex.{man_hours,hitl_hours,elapsed_hours,tokens_k}.samples`.
Because `fix_iterations > 0`, the 18.2 man-hours actual also updates
`fix.complex.reworked`'s running mean — not `clean`'s — and `fix.complex.clean` gets nothing
from this story. `fix` for `complex` only activates once **both** `clean` and `reworked`
separately reach 3 samples; a run of reworked-only stories, however many, never activates it
on its own.

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

**Orchestration, at sprint closure.** Suppose this story's sprint closes with an
`orchestration` block recording `elapsed_hours: 0.6`, and the sprint's children (this story
plus its siblings) sum to `elapsed_hours: 5.4` in their own `actual` blocks. Assuming
`orchestration.sprint.elapsed_hours` has already cleared 3 samples elsewhere, the sample this
closure adds is `0.6 / 5.4 = 0.1111` — a fraction, appended to
`orchestration.sprint.elapsed_hours.samples`, not divided against any estimate (there is
nothing to divide out — see §8). If any sibling story is missing its `elapsed_hours` actual,
this metric is skipped for this sample entirely, rather than computed from a partial sum.
