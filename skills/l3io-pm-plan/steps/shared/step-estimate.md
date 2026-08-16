# Step: Estimate

Communicate all responses in `{communication_language}`.

Callable from l3io-pm-plan and l3io-pm-execute. Computes and writes estimate blocks for
stories, sprints, and epics in scope. Reads calibration data to improve accuracy over time.

**Input bindings required before calling this step:**
- `{scope}` — what to estimate: `all`, `E{nnn}`, or `E{nnn}-S{nn}`
- `{pm_state_root}`, `{pm_calibration_file}`, `{pm_status}`, `{work_type}` — from step-00-activate and step-01

---

## 1. Load calibration data

Read `{pm_calibration_file}` (consolidated, created by l3io-pm-plan). If it does not exist,
all components use cold-start priors.

**Three calibration components** (each activates independently with ≥3 samples):
- `scope` — story sizing ratio per classification (simple/standard/complex)
- `closure` — sprint and epic closure overhead ratio
- `fix` — average fix factor per classification

A component with <3 samples uses cold-start prior: ratio = 1.0, fix factor = 1.25.

## 2. Determine stories in scope

Based on `{scope}`:
- `all` → all stories under every epic in `{pm_state_root}/planned/` and `{pm_state_root}/active/`
  that are not `status: done`
- `E{nnn}` → all stories under that epic's sprint directories
- `E{nnn}-S{nn}` → all stories under that sprint's directory

Story files are the `*.yaml` files in a sprint directory, excluding `sprint.yaml` (see
`skills/_shared/status-files.md` §4).

For each story, read its `classification` (simple/standard/complex) and any existing
estimate block.

## 3. Compute story estimates (bottom-up)

For each unestimated story (or story needing re-estimation):

**Base band by classification (cold-start priors):**

| Classification | man_hours | time_hours | tokens_k | cost_usd |
|---------------|-----------|------------|----------|----------|
| simple        | 2–4       | 0.5–1.5    | 20–50    | $0.10–$0.35 |
| standard      | 4–8       | 1–3        | 40–100   | $0.25–$0.70 |
| complex       | 8–16      | 2–6        | 80–200   | $0.55–$1.40 |

Apply calibrated scope ratio if available (multiply base by ratio).
Apply fix factor to man_hours and time_hours: `estimated = base × fix_factor`.

Write story estimate:
```bash
python3 {pm_status} set-estimate \
  --state-root {pm_state_root} \
  --story {story_key} \
  --man-hours {man_hours} \
  --time-hours {time_hours} \
  --tokens-k {tokens_k_midpoint} \
  --cost {cost_midpoint} \
  --confidence {low|medium|high}
```

Confidence: `high` if ≥3 samples for this classification; `medium` if 1–2 samples;
`low` if cold-start.

## 4. Roll up sprint estimates

For each sprint in scope:
- `man_hours_low/high` = Σ story.estimate.man_hours (apply ±20% band)
- `time_hours_low/high` = Σ story.estimate.time_hours × parallel_factor (sum compressed for
  parallel execution within a sprint; default parallel_factor = 0.6)
- `tokens_k_min/max` = Σ story.estimate.tokens_k (with ±20% band)
- `cost_low/high` = Σ story.estimate.cost (with ±20% band)
- Add closure overhead: apply calibrated `closure` ratio if available, else add 15% flat.

Write sprint estimate:
```bash
python3 {pm_status} set-estimate \
  --state-root {pm_state_root} \
  --epic {epic_key} --sprint {sprint_key} \
  --man-hours-low {low} --man-hours-high {high} \
  --time-hours-low {low} --time-hours-high {high} \
  --tokens-k-min {min} --tokens-k-max {max} \
  --cost-low {low} --cost-high {high} \
  --confidence {confidence}
```

## 5. Roll up epic estimates

For each epic in scope:
- Sum sprint estimates + epic closure overhead (calibrated or 20% flat cold-start).
- Write the epic estimate — `--state-root` plus the epic key resolves to that epic's node
  file wherever it currently sits (`planned/`, `active/`, or `archived/`), so the same call
  works for backlog and in-progress epics alike:

```bash
python3 {pm_status} set-estimate \
  --state-root {pm_state_root} \
  --epic {epic_key} \
  --man-hours-low {low} --man-hours-high {high} \
  --time-hours-low {low} --time-hours-high {high} \
  --tokens-k-min {min} --tokens-k-max {max} \
  --cost-low {low} --cost-high {high} \
  --confidence {confidence}
```

No `--flock` needed: each epic's estimate write touches only that epic's own directory (see
`skills/_shared/status-files.md` §9, Concurrency).

## 6. Output estimate summary

After all estimates are written, output a summary table:

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
