# Follow-up: `pm-status.py exists` verb

**Date:** 2026-09-24  
**Tracking:** 5 `check26:allow` markers added in the final-fix wave for
`2026-09-24-l3io-util-doctor-redesign`; this file is what those markers point to.

## Background

Check 26 (`resolverInvariant`) enforces that state-path assembly happens only inside
`pm-status.py`'s resolver section.  During the redesign, two step files were found that
legitimately _read_ the state tree with shell `ls -d`/`diff <(ls ...)` probes — not to write
paths into YAML, but simply to answer "does this epic directory exist in one of the three
status buckets?"

`pm-status.py` has no subcommand for this question (existence check / bucket lookup), so the
step files have to assemble the path themselves.  The `check26:allow` markers document that
these are deliberate read probes, not violations of the resolver-invariant, and point here for
the rationale.

## Sites carrying `check26:allow` markers

| File | Line (approx.) | Purpose |
|---|---|---|
| `skills/l3io-pm-help/steps/mode-list-plan.md` | `ls -d {pm_state_root}/{planned,active,archived}/epic-{nnn}/` | Find which status bucket holds an epic |
| `skills/l3io-util-doctor/steps/health-check.md` | `diff <(ls {pm_state_root}/{active,archived}/epic-{nnn}/sprint-{nn}/*.yaml ...)` | Compare state files against artifact files for drift check |

(The continuation lines of each multi-line command — which have no active verb on the line —
are already exempt via the `ACTIVE_VERB_RE` conjunct added at the same time.)

## What would clear the debt

A new `pm-status.py` subcommand in one of these forms would let the step files stop
assembling state paths directly:

**Option A — `exists` subcommand**
```
uv run {pm_status} exists --state-root {pm_state_root} --epic E001
```
Exit 0 if the epic directory exists in any status bucket (`planned/`, `active/`, `archived/`);
prints the bucket name on stdout.  Exit 1 if not found.  The step file would replace
the three-way `ls -d` with a single call.

**Option B — `list-epics` subcommand**
```
uv run {pm_status} list-epics --state-root {pm_state_root} --format json
```
Returns a JSON list of all epic keys with their status buckets.  The step file would look up
the key in the result instead of probing the filesystem.

Either option would also let the drift-check `diff <(ls ...)` in `health-check.md` be replaced
by a pair of `pm-status.py` read calls, which would be safer (no glob expansion, no `2>/dev/null`
swallowing of errors).

## When this is done

1. Implement the subcommand in `skills/_shared/pm-status.py` and update `skills/_shared/tests/`.
2. Rewrite the two step files to use the new subcommand.
3. Remove the two `check26:allow` markers and this follow-up file.
4. Confirm `npm run check:docs` still exits 0 (the markers are gone, the violations are gone).
