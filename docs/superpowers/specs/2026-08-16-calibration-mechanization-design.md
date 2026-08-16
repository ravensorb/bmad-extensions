# Calibration Mechanization

**Date:** 2026-08-16
**Status:** Approved for planning
**Amends:** `skills/_shared/metrics-contract.md` §6–§8 (the roll-up, the fix reserve, and calibration)

---

## Problem

`metrics-contract.md` §8 states it plainly:

> **Nothing in `pm-status.py` reads or writes the calibration file.** There is no calibration
> subcommand. Every part of this section — appending samples, decay weighting, activation
> thresholds, the approach-A split, `version: 1` migration — is performed by the orchestrator
> following prose.

The estimation model is fully specified — base bands, three separable components, ≥3-sample
activation, exponential decay 0.8 — and `pm-calibration.yaml` has a documented `version: 2`
schema. But no code path emits a sample or consumes a ratio. Every estimate therefore uses
cold-start priors forever, and the system never learns.

This is the same failure mode `pm-status.py` was built to end. Its docstring records that
status transitions used to be free-form YAML edits which "under load or parallel execution
were skipped, malformed, or reordered." Calibration sits in that state today — and worse,
because a dropped status write fails loudly while a dropped calibration sample is silent.

Two further defects surfaced during design, documented in their sections below: **approach A
is circular**, and **the estimate block cannot support the scope/fix split it is supposed to
feed**.

---

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | Samples derive automatically inside `set-actual` | A sample is arithmetic over data already on disk; nothing can forget to emit one |
| 2 | The script computes estimates; the model supplies only classification | Judgment stays with the model, arithmetic moves to code |
| 3 | All of it lives in `pm-status.py` | Automatic derivation needs in-process access, and two coupled self-installed scripts would risk version skew |
| 4 | `set-estimate` persists `fix_factor` and `scope_ratio` applied | Without them the scope/fix split is arithmetically impossible |
| 5 | Scope/fix split is iteration-based, falling back to approach A | Approach A alone can only re-learn its own prior |
| 6 | `calibration_granularity` is stored in the calibration file | Avoids another unbound step-file variable |
| 7 | A calibration failure never fails the actuals write | Actuals are primary; calibration is derived |

---

## Section 1: Interface

Four surfaces on `pm-status.py`.

### `set-actual` (existing, extended)

After writing the `actual` block, if the node also carries an `estimate`, derive and append
the calibration sample. Adds `--no-calibrate` to suppress this for backfills and replays.

### `estimate-story` (new)

```
estimate-story --state-root R --story KEY --classification {simple,standard,complex}
               [--confidence {low,medium,high}]
```

Reads calibration, applies `base_band(classification) × scope_ratio × fix_factor`, writes the
estimate block including the two factors it used. The model supplies only the classification.

### `estimate-rollup` (new)

```
estimate-rollup --state-root R --epic KEY [--sprint KEY]
```

`Σ children + calibrated closure band`. Sprint scope sums its stories; epic scope sums its
sprints. Written as the range form (`man_hours_low/high`, …) that sprint and epic estimates
already use.

### `calibration show` (new)

```
calibration show --state-root R [--format {text,json}]
```

Current ratios, sample counts per component, and which components are active. Read-only.
A missing file is not an error — report cold-start and exit 0.

### Base bands become code constants

The bands currently live as a markdown table in `steps/shared/step-estimate.md`:

| Classification | man_hours | time_hours | tokens_k | cost_usd |
|---|---|---|---|---|
| simple | 2–4 | 0.5–1.5 | 20–50 | $0.10–$0.35 |
| standard | 4–8 | 1–3 | 40–100 | $0.25–$0.70 |
| complex | 8–16 | 2–6 | 80–200 | $0.55–$1.40 |

They move into `pm-status.py` as the single source. The step file cites them; it no longer
defines them.

---

## Section 2: The estimate-block schema change

Approach A divides a measured actual by "the observed `fix_factor` for that story". No such
value is recorded anywhere. `set-estimate` writes only the four metric values and
`confidence` (`pm-status.py:627-640`), so at `set-actual` time there is nothing to divide by.

**`set-estimate` must additionally persist what it applied:**

```yaml
estimate:
  man_hours: 6
  time_hours: 1.5
  tokens_k: 320
  cost: 4.80
  confidence: high
  fix_factor: 1.25        # NEW — the multiplier applied
  scope_ratio: 1.0        # NEW — the calibrated ratio applied (1.0 when cold-start)
```

This is load-bearing on **both** split paths, not only the fallback. Even a zero-rework story
whose actual is pure scope must be compared against an estimate that had the fix multiplier
baked in, so the comparison is `actual × fix_factor ÷ estimate`.

Estimates written before this change lack both fields. Treat a missing `fix_factor` as 1.0
and a missing `scope_ratio` as 1.0, and mark the resulting sample `provenance: legacy` so a
later audit can tell it apart from a fully-instrumented one.

### The metric-name trap

The four metrics do not pair by name across the two blocks:

| Estimate field | Actual field |
|---|---|
| `man_hours` | `man_hours` |
| `time_hours` | **`elapsed_hours`** |
| `tokens_k` | `tokens_k` |
| `cost` | `cost` |

Any derivation that zips estimate keys onto actual keys produces a silently wrong ratio for
AI wall-clock. The pairing must be an explicit map, and a test must cover it.

---

## Section 3: Story sampling

### Why approach A alone does not work

§8 requires dividing by "the **observed** `fix_factor`", while also claiming the method
"needs no extra instrumentation in the dev loop". Both cannot hold. With nothing observing a
per-story fix factor, the only available divisor is the factor assumed at estimate time —
so the `fix` component re-derives its own prior and never learns from evidence.

The instrumentation does exist. `steps/sprint/step-03-dev-loop.md:91` writes
`completion_evidence.fix_iterations` on every story.

### The split

| `fix_iterations` | Scope sample | Fix cohort |
|---|---|---|
| `0` | **Exact** — the actual is pure scope | clean |
| `> 0` | Approach-A back-out (lossy) | reworked |
| absent | Approach-A back-out | none |

Scope ratio per metric, both paths:

```
scope_ratio_sample = actual × fix_factor_applied / estimate
```

For the exact path this is a true measurement. For the fallback it inherits approach A's
looseness, which is accepted and recorded via `provenance`.

### The `fix` component's schema changes

A cohort comparison needs both sides, so `{avg_fix_factor, samples}` is insufficient:

```yaml
fix:
  complex:
    clean:    { mean_man_hours: 7.1, samples: 4 }
    reworked: { mean_man_hours: 9.6, samples: 5 }
    avg_fix_factor: 1.35        # derived: reworked ÷ clean
```

**Activation is stricter than the other components:** `fix` activates only when **both**
cohorts reach 3 samples, because one cohort alone cannot form a ratio. A project where every
story needs rework never activates `fix` and continues on the 1.25 prior — correct, since it
has no baseline to measure against.

---

## Section 4: Closure sampling

Closure overhead is the residual between a parent's actual and its children's:

```
sprint closure actual = actual(sprint) − Σ actual(stories in sprint)
epic   closure actual = actual(epic)   − Σ actual(sprints in epic)
```

Emitted when `set-actual` writes a sprint or epic node. Three guards, each of which skips the
sample and warns on stderr rather than recording something wrong:

- **Any child missing an actual** — a partial sum understates the parent's own overhead and
  would bias the ratio low.
- **Negative residual** — a parent whose actual is below its children's sum is miscounted;
  recording negative overhead corrupts the ratio silently.
- **`N/A` tokens or cost** — under `--runtime other` those metrics are `N/A`. Man-hours and
  wall-clock samples still record; token and cost samples are skipped for that node rather
  than coerced to zero. §8 already requires this.

---

## Section 5: Granularity, weighting, and failure behaviour

### Granularity lives in the file

`calibration_granularity` is currently declared in no `customize.toml` and read by nothing.
Rather than adding another step-file variable — `{runtime}` failed in exactly that way,
unbound while being passed to a strict-`choices` flag — the setting is written into
`pm-calibration.yaml` at creation:

```yaml
version: 2
granularity: story        # or "sprint"
```

Self-contained, nothing to bind. `story` (default) emits a scope and fix sample per done
story; `sprint` aggregates per sprint. Closure is always sampled per sprint and per epic
regardless.

### Weighting and activation

Unchanged from §8: exponential decay 0.8 applied oldest-first, each component activating
independently at ≥3 samples (except `fix`, per Section 3). A component below threshold is
recorded but not applied. `token` and `cost` ratios accumulate only from runs with real
actuals; `N/A` entries are skipped, never guessed.

### Failure behaviour

A calibration write failure must never fail the actuals write. Actuals are the primary
record; calibration is derived and reconstructible. On failure `set-actual` warns on stderr
naming the reason and still exits 0 for the status write.

This is a deliberate asymmetry, and the opposite of the current behaviour — which is not
"fail" but *silence*, since nothing runs at all.

### `version: 1` migration

Unchanged from §8: auto-migrated on first write, original preserved as
`pm-calibration.yaml.v1`, the old blended ratio mapped onto `scope`, with `closure` and `fix`
starting fresh at zero samples. Seeding them from a blended figure would import exactly the
bias the split exists to remove.

---

## Section 6: Testing

`pm-status.py` has 177 tests; this adds a class per surface. The cases that matter most are
the ones where a wrong implementation still looks plausible:

- **The metric-name pairing** — `time_hours` ↔ `elapsed_hours` mapped correctly, asserted by
  a case that fails if the map is identity.
- **Exact vs fallback split** — a `fix_iterations: 0` story produces an exact scope sample; a
  reworked story produces a back-out sample marked `provenance`.
- **Fix activation needs both cohorts** — 5 clean samples and 0 reworked must NOT activate.
- **Closure guards** — missing child actual, negative residual, and `N/A` metrics each skip
  the sample and warn, and do not corrupt the file.
- **Failure isolation** — an unwritable calibration file leaves the `actual` block correctly
  written and exits 0.
- **Legacy estimates** — an estimate lacking `fix_factor`/`scope_ratio` yields a sample
  marked `legacy` rather than crashing.
- **Cold start** — a missing calibration file yields priors and exit 0, not an error.

---

## Section 7: Documentation to update

- `skills/_shared/metrics-contract.md` — §6 base bands now cite code; §7 fix reserve;
  §8 rewritten for the iteration-based split, the new `fix` schema, in-file granularity, and
  a corrected "Mechanization status" that no longer says nothing runs. §9's disagreement
  register loses the entries this closes.
- `skills/_shared/steps/shared/step-estimate.md` — replace the hand-computed arithmetic with
  `estimate-story` / `estimate-rollup` calls. Remove the base-band table in favour of a
  citation.
- `skills/_shared/steps/sprint/step-04-sprint-closure.md`, `steps/execute/step-06-epic-closure.md`
  — drop the prose instructions to append samples; `set-actual` now does it.
- `skills/_shared/status-files.md` — document the new subcommands.
- `CLAUDE.md` — the calibration paragraph currently describes a system that does not run.

---

## Out of scope

- The other 15 discrepancies in `metrics-contract.md` §9. This closes only the ones caused by
  calibration being unmechanized.
- Changing the base band values themselves. They move location; their numbers are unchanged
  and remain cold-start priors superseded by learned ratios.
- Making `set-actual` require all four metrics. It currently requires only one, which is a
  real gap in HARD RULE enforcement, but it is a separate change with its own blast radius.
