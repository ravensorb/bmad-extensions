### List Plan Mode

Invoked with the `list plan` argument. Enumerates every plan snapshot in `{planning_artifacts}/`,
reads key metadata from each, cross-references its epic set against the current state tree to
determine whether execution has started, and outputs a focused list of plans that have not yet
been run.

**1. Read plan pointer**

```bash
cat {planning_artifacts}/plan-output-meta.yaml 2>/dev/null || echo "(absent)"
```

Bind `{current_plan}` from the `current_plan` field of that file, or `(none)` if the file is
absent.

**2. List all snapshots**

```bash
ls -1 {planning_artifacts}/plan-*-v*.yaml 2>/dev/null | sort -V
```

If no snapshots are listed:

```
No plan snapshots found in {planning_artifacts}/.
Run /l3io-pm-plan to create a plan.
```

Stop.

**3. Read and classify each snapshot**

For each snapshot file, read it and extract:
- `generated` — ISO timestamp
- `readiness` — green | amber | red
- `plan_version` — integer
- `total_epics_in_scope` — count
- The ordered list of phases, and from each phase its `epics` list (e.g. `["E001", "E002"]`)

Collect the full set of epic keys referenced across all phases of this snapshot.

For each epic key `E{nnn}` (where `epic-{nnn}` is the zero-padded directory name), probe state:

```bash
ls -d {pm_state_root}/planned/epic-{nnn}/ \
      {pm_state_root}/active/epic-{nnn}/  \
      {pm_state_root}/archived/epic-{nnn}/ 2>/dev/null
```

Classify the plan using the statuses of all its epics:

| Condition | Status |
|---|---|
| Every epic is in `planned/`, or no epic directory exists in any folder | **unstarted** |
| At least one epic is in `active/`, or some are in `archived/` and some are still in `planned/` | **in progress** |
| Every epic is in `archived/` | **complete** |

An epic with no matching directory in any of the three state folders is treated as `planned`
(not yet started) for classification purposes. If this is true of any epic, note it separately:
`⚠ epic {key} from this plan has no state directory — may have been removed after the plan was
generated.`

**4. Output the list**

Print the snapshots newest-first (reverse of the sorted order from step 2):

```
Plan snapshots in {planning_artifacts}/

  PLAN FILE                      GENERATED              READ  PH  EPICS  STATUS
  plan-2026-08-31-v2.yaml  ◄    2026-08-31T11:00:00Z   grn   2    4     unstarted
  plan-2026-08-31-v1.yaml        2026-08-31T09:00:00Z   grn   2    4     unstarted
  plan-2026-08-15-v1.yaml        2026-08-15T10:30:00Z   grn   3    6     complete

◄ = current (plan-output-meta.yaml → {current_plan})
READ = readiness (grn/amb/red)  PH = phase count
```

Then print a focused list of **unstarted** plans (readiness green or amber only):

```
Unstarted plans ready to execute:

  1. plan-2026-08-31-v2.yaml — 2026-08-31, readiness: green, 2 phases, 4 epics
  2. plan-2026-08-31-v1.yaml — 2026-08-31, readiness: green, 2 phases, 4 epics
```

If no unstarted plans with green or amber readiness exist:

```
No unstarted plans with green or amber readiness found.
Run /l3io-pm-plan to create a new plan.
```

**5. Execution hint**

`/l3io-pm-execute` always reads from `plan-output-meta.yaml` — it has no flag to name a
specific snapshot. The pointer is the only way to select which plan runs.

If `{current_plan}` is unstarted with green or amber readiness:
```
Current plan ({current_plan}) is unstarted and ready — run /l3io-pm-execute to start.
```

If there are unstarted plans and `{current_plan}` is not one of them (or the pointer is
absent), print:
```
To run a specific unstarted plan, update the pointer:

  echo "current_plan: \"<plan-filename>\"
  generated: \"<its-generated-value>\"
  readiness: <its-readiness>
  stories_elaborated: <its-stories_elaborated>
  total_epics_in_scope: <its-total_epics_in_scope>
  phase_count: <its-phase_count>" > {planning_artifacts}/plan-output-meta.yaml

Then run /l3io-pm-execute.
```

Fill in the values from the chosen snapshot. If `{pm_status_present}` is `absent`, prepend:
`pm-status.py is missing at {project-root}/_bmad/scripts/pm-status.py. Run /l3io-util-doctor
first to install it — this report read epic.yaml directly instead.`
