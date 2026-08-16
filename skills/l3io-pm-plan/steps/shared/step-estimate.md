# Step: Estimate

Communicate all responses in `{communication_language}`.

Callable from l3io-pm-plan and l3io-pm-execute. Computes and writes estimate blocks for
stories, sprints, and epics in scope. All arithmetic — base band lookup, calibrated scope
ratio and fix factor per metric, closure band — runs inside `pm-status.py`; this step's job
is to choose scope and classification and call it.

**Input bindings required before calling this step:**
- `{scope}` — what to estimate: `all`, `E{nnn}`, or `E{nnn}-S{nn}`
- `{pm_state_root}`, `{pm_status}`, `{work_type}` — from step-00-activate and step-01

---

## 1. Determine stories in scope

Based on `{scope}`:
- `all` → all stories under every epic in `{pm_state_root}/planned/` and `{pm_state_root}/active/`
  that are not `status: done`
- `E{nnn}` → all stories under that epic's sprint directories
- `E{nnn}-S{nn}` → all stories under that sprint's directory

Story files are the `*.yaml` files in a sprint directory, excluding `sprint.yaml` (see
`skills/_shared/status-files.md` §4).

For each story, read its `classification` (simple/standard/complex) and any existing
estimate block.

## 2. Estimate stories (bottom-up)

For each unestimated story (or story needing re-estimation), the model supplies only the
classification — `estimate-story` does the rest: looks up the base band
(`references/metrics-contract.md` §6 cites `BASE_BANDS` in `pm-status.py` as the single
source), applies the calibrated per-metric scope ratio and the classification's fix factor
(cold-start priors when either is not yet active), and writes the estimate block.

```bash
python3 {pm_status} estimate-story \
  --state-root {pm_state_root} \
  --story {story_key} \
  --classification {simple|standard|complex} \
  [--confidence {low|medium|high}]
```

`--confidence` is optional — omit it to let `estimate-story` derive `medium`/`low` from
whether a field is present, per `metrics-contract.md` §4. Do not hand-compute the estimate
arithmetic in this step; a re-derivation here can drift from what `estimate-story` actually
applies.

## 3. Roll up sprint and epic estimates

`estimate-rollup` sums the estimates of a node's children and widens the sum by the
calibrated (or cold-start) closure band — see `references/metrics-contract.md` §6 for the
exact mechanics. Run it sprint-first, then epic, since the epic roll-up sums sprint
estimates:

```bash
# each sprint in scope
python3 {pm_status} estimate-rollup --state-root {pm_state_root} --epic {epic_key} --sprint {sprint_key}

# each epic in scope, after all its sprints are rolled up
python3 {pm_status} estimate-rollup --state-root {pm_state_root} --epic {epic_key}
```

No `--flock` needed: each epic's estimate write touches only that epic's own directory (see
`skills/_shared/status-files.md` §9, Concurrency).

## 4. Output estimate summary

After all estimates are written, read each node back (`{pm_status} show`) and output a
summary table:

```
## Estimate Summary (scope: {scope})

| Epic | Sprints | Stories | man-hrs (low–high) | wall-clock (low–high) | cost (low–high) | confidence |
|------|---------|---------|--------------------|-----------------------|-----------------|------------|
| E001 | 2       | 8       | 32–52 hrs          | 9–15 hrs              | $2.80–$4.60     | medium     |
| E002 | 3       | 11      | 48–76 hrs          | 13–21 hrs             | $4.10–$6.50     | low        |

**Total (sequential):** 80–128 man-hrs, 22–36 wall-clock hrs, $6.90–$11.10
**If E001 and E002 run in parallel:** 48–76 man-hrs, 13–21 wall-clock hrs, $4.10–$6.50
```

Confidence levels are per-epic, reflecting the weakest component used.
