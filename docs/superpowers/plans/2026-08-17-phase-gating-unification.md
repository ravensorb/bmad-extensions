# Phase Gating Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse three disagreeing definitions of `{skip_phases}` into one matrix, make the fix-loop cap work-type-aware and configurable, and delete two pieces of dead gating machinery.

**Architecture:** `steps/shared/step-01-classify-work.md` becomes the single source of truth for phase gating — it runs first and already owns `{work_type}`. Its matrix gains an *Enforced by* column because two mechanisms are in play (`{skip_phases}` versus a `{work_type}` check at the phase's own step), and conflating them is what produced the current confusion. `step-05` stops recomputing the binding; `closure/sprint-closure.md` drops its duplicate table.

**Tech Stack:** Markdown step files and TOML customization files. No Python changes. `npm run sync:scripts` fans canonical sources out to three PM skill payload copies; `npm run check:scripts` gates on drift.

**Spec:** `docs/superpowers/specs/2026-08-17-phase-gating-unification-design.md`

## Global Constraints

- **Never edit per-skill payload copies.** `skills/_shared/**` is the only editable source. `npm run sync:scripts` regenerates `skills/l3io-pm-{execute,plan,sync}/{scripts,references,steps}/`. CI runs `npm run check:scripts`.
- **`customize.toml` files are per-skill sources, NOT generated.** All four PM skills must be edited directly: `l3io-pm-execute`, `l3io-pm-plan`, `l3io-pm-sync`, `l3io-pm-help`. `l3io-arch-review`, `l3io-util-doctor`, and `l3io-util-cleanup` must not be touched.
- **Exactly one computation of `{skip_phases}` may exist** in `skills/_shared/` when this plan is done.
- **Gating behavior must not change except where the spec says so.** The only intended behavioral changes are: UX review no longer runs on DOCS, and the fix-loop cap becomes 3 for DOCS/CONFIG. Every other phase must skip and run exactly as it does today.
- **Phases enforced by a `{work_type}` check at their own step stay that way.** Do not convert them to `{skip_phases}` entries — a malformed string would silently disable a gate, while a `{work_type}` check cannot be.
- **Fix-loop cap values:** `10` for CODE and MIXED, `3` for DOCS and CONFIG. One cap per work-type class, applied at all three sites. Do not introduce separate story-versus-closure caps.
- **Commits:** Conventional Commits, DCO sign-off. Put `Signed-off-by` and `Co-Authored-By` in the final trailer block — a footer after them breaks git's trailer parsing. Scope: `l3io-pm`.

---

### Task 1: One phase matrix in step-01, and remove the duplicates

**Files:**
- Modify: `skills/_shared/steps/shared/step-01-classify-work.md:42-56` (the matrix) and `:70-71` (the ATDD install check)
- Modify: `skills/_shared/steps/execute/step-05-epic-loop.md:141-145` (drop the recompute)
- Modify: `skills/_shared/steps/closure/sprint-closure.md:8-18` (drop the duplicate table), `:16` (UX on DOCS)

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces: `{skip_phases}` bound once, in `step-01`. Task 2 adds a second binding (`{max_fix_iterations}`) to the same step and relies on this task having established the matrix it sits beside.

- [ ] **Step 1: Replace step-01's §4 matrix**

In `skills/_shared/steps/shared/step-01-classify-work.md`, replace exactly this block:

```markdown
4. Compute `{skip_phases}` from the conditional phase table:

| Phase | Skip when |
|-------|-----------|
| Story technical-AC gate | `{work_type}` is DOCS or CONFIG |
| Arch gate (epic level) | `{work_type}` is DOCS or CONFIG, or l3io-arch-review not installed |
| Adversarial analysis | `{work_type}` is DOCS or CONFIG |
| Red team (l3io-sec) | `{work_type}` is DOCS or CONFIG, or l3io-sec not installed |
| UX review | `{work_type}` is CONFIG |
| ATDD scaffold | `{work_type}` is DOCS or CONFIG, or bmad-testarch-atdd not installed |

Bind `{skip_phases}` = comma-separated list of phase names to skip (empty if none).
```

with:

```markdown
4. Compute `{skip_phases}` from the phase matrix below.

**This matrix is the single source of truth for phase gating.** No other step file computes
`{skip_phases}` — `step-05-epic-loop.md` passes through what is bound here, and
`closure/sprint-closure.md` skips whatever this names. If you are about to recompute it
somewhere else, that is the bug this table exists to prevent.

**Two mechanisms, and the difference matters.** Rows marked `{skip_phases}` are skipped by
being named in that binding. Rows marked with a step file are gated by a `{work_type}` check
inside that step and never appear in `{skip_phases}` at all. Do not migrate the second kind
into the first: a malformed `{skip_phases}` string would silently disable a gate, whereas a
`{work_type}` check cannot be turned off by a typo.

| Phase | CODE | DOCS | CONFIG | MIXED | Enforced by |
|---|---|---|---|---|---|
| Retrospective | run | run | run | run | always runs |
| Clean release review | run | skip | run | run | `{skip_phases}` |
| Adversarial analysis | run | skip | skip | run | `{skip_phases}` |
| Red team (`l3io-sec`) | run | skip | skip | run | `{skip_phases}` + installed check |
| UX review | run | skip | skip | run | `{skip_phases}` + installed check + UI-facing stories |
| Architectural drift | run | skip | run | run | `{skip_phases}` + installed check |
| Issue triage | run | run | run | run | always runs |
| Story technical-AC gate | run | skip | skip | run | `{work_type}` at `steps/sprint/step-02-story-prep.md` |
| Epic arch gate | run | skip | skip | run | `{work_type}` at `steps/execute/step-04-arch-gate.md` |

Bind `{skip_phases}` = comma-separated list of the `{skip_phases}`-enforced phase names that
this `{work_type}` column marks `skip` (empty if none). Rows whose *Enforced by* is a step
file, or "always runs", are never included.

For `{work_type}` = CODE or MIXED, `{skip_phases}` is empty unless an installed check fails.
```

- [ ] **Step 2: Remove the ATDD install check**

In the same file, delete exactly these two lines:

```markdown
- `bmad-testarch-atdd`: command file exists at project or user level (run:
  `ls {project-root}/.claude/commands/bmad-testarch-atdd.md 2>/dev/null || ls ~/.claude/commands/bmad-testarch-atdd.md 2>/dev/null || echo "absent"`)
```

If deleting them leaves the sentence `For the remaining skills:` introducing nothing, remove
that sentence too. Read the surrounding lines and keep the prose grammatical — the two
remaining checks (`l3io-arch`, `l3io-sec`) are covered by the manifest-grep paragraph above it.

- [ ] **Step 3: Stop step-05 recomputing the binding**

In `skills/_shared/steps/execute/step-05-epic-loop.md`, replace exactly:

```markdown
Compute `{skip_phases}` from `{work_type}`:
- `CODE`: skip none
- `DOCS`: skip adversarial, red-team, arch-drift, clean-release
- `CONFIG`: skip adversarial, red-team, ux-review
- `MIXED`: skip none
```

with:

```markdown
`{skip_phases}` was bound by `step-01-classify-work.md` §4 from the phase matrix there. Pass it
through unchanged — do not recompute it. Two computations of one variable is what this replaced.
```

- [ ] **Step 4: Drop the duplicate table from sprint-closure.md and turn UX off for DOCS**

In `skills/_shared/steps/closure/sprint-closure.md`, replace exactly:

```markdown
## Phase table (§8)

| Phase | CODE | DOCS | CONFIG | MIXED |
|---|---|---|---|---|
| Retrospective | run | run | run | run |
| Clean release review | run | skip | run | run |
| Adversarial analysis | run | skip | skip | run |
| Red team (l3io-sec) | run | skip | skip | run |
| UX review | run | run | skip | run |
| Architectural drift | run | skip | run | run |
| Issue triage | run | run | run | run |
```

with:

```markdown
## Phase gating

The phase matrix lives in `steps/shared/step-01-classify-work.md` §4 and is the single source
of truth. It bound `{skip_phases}`; run every phase below except those it names. This file
deliberately carries no copy of that table — the duplicate it used to hold is what let the two
drift.

Note for DOCS work: UX review is skipped. Documentation does not get a UX review pass.
```

That last line is the UX-on-DOCS behavior change, and removing the table is what enacts it —
the old table's `| UX review | run | run | skip | run |` row is the only place DOCS was marked
`run`.

- [ ] **Step 5: Verify exactly one computation remains, and the two sides agree**

```bash
cd $REPO_ROOT
echo "--- computations of {skip_phases} (expect exactly 1) ---"
grep -rn 'Compute `{skip_phases}`' skills/_shared/steps/
echo "--- phases the matrix marks {skip_phases}-enforced ---"
grep -E '^\| .* \| `\{skip_phases\}\`' skills/_shared/steps/shared/step-01-classify-work.md \
  | sed 's/|.*//;s/^| //'
echo "--- phase sections sprint-closure.md actually implements ---"
grep -E '^## [0-9]+\.' skills/_shared/steps/closure/sprint-closure.md
```

Expected: exactly one `Compute` hit, in `step-01-classify-work.md`. Every phase the matrix
marks `{skip_phases}`-enforced must have a corresponding `##` section in
`sprint-closure.md`, and every skippable `##` section there must appear in the matrix — no
orphan on either side. Reconcile by eye and report the pairing.

- [ ] **Step 6: Confirm no gating behavior changed except UX-on-DOCS**

```bash
cd $REPO_ROOT
for wt in CODE DOCS CONFIG MIXED; do
  echo "--- $wt ---"
  awk -v col="$wt" '
    /^\| Phase \| CODE/ {for(i=1;i<=NF;i++) if($i==col) c=i; next}
    /^\| [A-Z]/ {print "  " $2 " " $3 " " $4 ": " $0}
  ' skills/_shared/steps/shared/step-01-classify-work.md | head -0
done
sed -n '/^| Phase | CODE/,/^$/p' skills/_shared/steps/shared/step-01-classify-work.md
```

Compare the printed matrix against this table, which is today's behavior plus the one intended
change. Every cell must match:

| Phase | CODE | DOCS | CONFIG | MIXED |
|---|---|---|---|---|
| Retrospective | run | run | run | run |
| Clean release review | run | skip | run | run |
| Adversarial analysis | run | skip | skip | run |
| Red team | run | skip | skip | run |
| UX review | run | **skip** ← the one change | skip | run |
| Architectural drift | run | skip | run | run |
| Issue triage | run | run | run | run |
| Story technical-AC gate | run | skip | skip | run |
| Epic arch gate | run | skip | skip | run |

- [ ] **Step 7: Sync and gate**

```bash
npm run sync:scripts && npm run check:scripts
```

Expected: sync reports the three step files copied to the PM skills; check exits 0.

- [ ] **Step 8: Commit**

```bash
git add -A skills/
git commit -F - <<'MSG'
refactor(l3io-pm): make step-01 the single source of phase gating

{skip_phases} was computed in two places from two different definitions --
step-01-classify-work.md §4 bound it, then step-05-epic-loop.md recomputed and
overwrote it -- while closure/sprint-closure.md carried a third, 7x4 table of its
own. Tracing the consumers showed this was inert today: {skip_phases} has five
consumers, all closure phases, and step-05's list agreed with the closure table for
DOCS and CONFIG. The three entries step-05 omitted are gated on {work_type} at
their own step and never flowed through the variable at all. So this was a
maintenance hazard, not a live defect, and one edit away from becoming one.

step-01 now owns the only matrix. step-05 passes the binding through;
sprint-closure.md points at step-01 instead of duplicating it. The matrix gains an
"Enforced by" column because two mechanisms are genuinely in play, and rows gated
by a {work_type} check at their own step stay that way deliberately -- a malformed
{skip_phases} string could silently disable a gate, while a {work_type} check
cannot.

One behavior change: UX review no longer runs on DOCS work, taking DOCS closure
from three phases to two. Also removes the ATDD install check, which shell-tested
for a command no step file ever invokes.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Signed-off-by: Shawn Anderson <sanderson@eye-catcher.com>
MSG
```

---

### Task 2: Work-type-aware, configurable fix-loop cap

**Files:**
- Modify: `skills/l3io-pm-execute/customize.toml`, `skills/l3io-pm-plan/customize.toml`, `skills/l3io-pm-sync/customize.toml`, `skills/l3io-pm-help/customize.toml`
- Modify: `skills/_shared/steps/shared/step-01-classify-work.md` (bind `{max_fix_iterations}` after §4)
- Modify: `skills/_shared/steps/sprint/step-03-dev-loop.md:51`
- Modify: `skills/_shared/steps/closure/sprint-closure.md:38` (line number is pre-Task-1; find it by content)
- Modify: `skills/_shared/steps/closure/epic-closure.md:35`

**Interfaces:**
- Consumes: the matrix and `{work_type}` binding established in Task 1 — the new binding sits immediately after §4's matrix
- Produces: `{max_fix_iterations}`, an integer bound at `step-01`, read at three fix-loop sites

- [ ] **Step 1: Add the two settings to all four PM skills**

```bash
cd $REPO_ROOT
python3 - <<'PY'
old = "# Concurrency"
new = ("# Fix loops\n"
       "max_fix_iterations          = 10   # CODE and MIXED work\n"
       "max_fix_iterations_non_code = 3    # DOCS and CONFIG work\n"
       "\n"
       "# Concurrency")
for s in ["l3io-pm-execute"]:
    p = f"skills/{s}/customize.toml"
    t = open(p).read()
    assert old in t, f"{p}: '# Concurrency' anchor not found"
    open(p, "w").write(t.replace(old, new, 1))
    print(f"  {p} updated (anchored on '# Concurrency')")
PY
```

`l3io-pm-execute` has a `# Concurrency` comment to anchor on; the other three do not. For
`l3io-pm-plan`, `l3io-pm-sync`, and `l3io-pm-help`, append the same block to the end of the
`[workflow]` section:

```toml

# Fix loops
max_fix_iterations          = 10   # CODE and MIXED work
max_fix_iterations_non_code = 3    # DOCS and CONFIG work
```

Read each file first — they are short — and place the block after the last existing key in
`[workflow]` so it stays inside that table.

- [ ] **Step 2: Verify all four parse and carry both keys**

```bash
cd $REPO_ROOT
python3 - <<'PY'
import tomllib
for s in ["l3io-pm-execute","l3io-pm-plan","l3io-pm-sync","l3io-pm-help",
          "l3io-arch-review","l3io-util-doctor","l3io-util-cleanup"]:
    p = f"skills/{s}/customize.toml"
    with open(p,"rb") as fh: d = tomllib.load(fh)
    w = d.get("workflow") or d.get("agent") or {}
    print(f"  {s:20} max_fix_iterations={w.get('max_fix_iterations')} "
          f"non_code={w.get('max_fix_iterations_non_code')}")
PY
```

Expected: the four PM skills each show `10` and `3`; the other three show `None` and `None` and
must be untouched. A `tomllib` error means the block landed outside `[workflow]`.

- [ ] **Step 3: Bind `{max_fix_iterations}` in step-01**

In `skills/_shared/steps/shared/step-01-classify-work.md`, immediately after the paragraph
ending `For {work_type} = CODE or MIXED, {skip_phases} is empty unless an installed check fails.`
(added in Task 1), insert:

```markdown
5. Bind `{max_fix_iterations}` from `{work_type}`:

| `{work_type}` | Binding |
|---|---|
| CODE, MIXED | `max_fix_iterations` (default 10) |
| DOCS, CONFIG | `max_fix_iterations_non_code` (default 3) |

Both come from the resolved `customize.toml` `[workflow]` table. This one integer is the cap for
**every** fix loop in the run — per-story in the dev loop, and at sprint and epic closure.
A ten-iteration autonomous fix loop is proportionate to a broken API contract and wildly
disproportionate to a typo, which is why it follows the work type.
```

Renumber any subsequent numbered item in that step accordingly, and check whether the step's
final "Output" block should report the binding — if it already prints `{work_type}` and
`{skip_phases}`, add `{max_fix_iterations}` beside them.

- [ ] **Step 4: Replace the three hardcoded caps**

In `skills/_shared/steps/sprint/step-03-dev-loop.md`, replace:

```markdown
**Fix loop cap:** 10 iterations per story. If findings persist after 10 iterations:
```

with:

```markdown
**Fix loop cap:** `{max_fix_iterations}` iterations per story (bound at
`step-01-classify-work.md` §5 — 10 for CODE/MIXED, 3 for DOCS/CONFIG). If findings persist
after `{max_fix_iterations}` iterations:
```

In `skills/_shared/steps/closure/sprint-closure.md`, replace:

```markdown
- CRITICAL/HIGH: block closure, fix loop (max 10 iterations). MEDIUM: fix in place. LOW: defer.
```

with:

```markdown
- CRITICAL/HIGH: block closure, fix loop (max `{max_fix_iterations}` iterations). MEDIUM: fix in place. LOW: defer.
```

In `skills/_shared/steps/closure/epic-closure.md`, replace:

```markdown
- CRITICAL/HIGH/MEDIUM: must be resolved before closure completes. Open fix loop (max 10 iterations).
```

with:

```markdown
- CRITICAL/HIGH/MEDIUM: must be resolved before closure completes. Open fix loop (max `{max_fix_iterations}` iterations).
```

- [ ] **Step 5: Verify no hardcoded cap survives**

```bash
cd $REPO_ROOT
echo "--- hardcoded 10-iteration caps (expect none) ---"
grep -rn "10 iteration\|max 10 iter" skills/_shared/steps/ || echo "  NONE"
echo "--- sites reading the binding (expect 3 files) ---"
grep -rln "max_fix_iterations" skills/_shared/steps/
```

Expected: `NONE` for the first, and four files for the second — the three fix-loop sites plus
`step-01-classify-work.md` where it is bound.

- [ ] **Step 6: Sync and gate**

```bash
npm run sync:scripts && npm run check:scripts
```

Expected: check exits 0. Note `customize.toml` files are not synced — they are per-skill
sources — so only the step files appear in the sync output.

- [ ] **Step 7: Commit**

```bash
git add -A skills/
git commit -F - <<'MSG'
feat(l3io-pm): scale the fix-loop cap to work type

The cap was hardcoded as 10 in three places -- the per-story dev loop, sprint
closure, and epic closure -- identical for a broken API contract and a
documentation typo. It is the largest single multiplier in the system: a three-story
sprint runs between 8 and 40+ subagent invocations, and almost the whole gap is
fix-loop iterations.

Now bound once at step-01 from {work_type} and read at all three sites: 10 for
CODE/MIXED, 3 for DOCS/CONFIG, both configurable per skill.

One cap per work-type class rather than separate story-versus-closure caps -- that
would be four knobs for a distinction nothing currently needs.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Signed-off-by: Shawn Anderson <sanderson@eye-catcher.com>
MSG
```

---

### Task 3: Honest parallelism docs, and restore the verify routing row

**Files:**
- Modify: `skills/_shared/steps/execute/step-05-epic-loop.md:57` (the dangling `§15`)
- Modify: `skills/_shared/steps/shared/step-00-activate.md` (restore the `§7` routing row)
- Modify: `CLAUDE.md` (adaptive-parallelism paragraph, ATDD optional-dependency claim, fix-cap description)
- Modify: `docs/l3io-pm-reference.md` (the phase table it documents, and the fix-loop caps)

**Interfaces:**
- Consumes: Task 1's matrix (the reference doc must describe it, including UX-off-for-DOCS) and Task 2's `{max_fix_iterations}` binding
- Produces: nothing downstream

- [ ] **Step 1: Fix the dangling §15 reference**

In `skills/_shared/steps/execute/step-05-epic-loop.md`, the line

```markdown
  Dispatch up to `{max_parallel_subagents}` epics concurrently per §15 adaptive parallelism.
```

cites a section that does not exist — the execute `SKILL.md` has three `##` sections. Replace it
with:

```markdown
  Dispatch up to `{max_parallel_subagents}` epics concurrently (default 4, set per skill in
  `customize.toml`). Sprints within an epic are always sequential.
```

- [ ] **Step 2: Correct CLAUDE.md's adaptive-parallelism paragraph**

`CLAUDE.md` describes `parallel_mode`, `parallel_ceiling`, and `safe_batch_size` with the formula
`effective = min(max_parallel_subagents, parallel_ceiling, safe_batch_size)`. None of the three
exists in any `customize.toml` or is computed in any step file. Find that paragraph — it begins
`**Adaptive parallelism**:` — and replace its whole body with:

```markdown
**Parallelism**: within a plan phase marked `parallel: true`, `l3io-pm-execute` dispatches epics concurrently up to `max_parallel_subagents` (default 4, per-skill in `customize.toml`). Sprints within an epic are **always sequential**, so calibration from each finished sprint feeds forward into re-estimating the rest. Phase parallelism is decided at plan time: `steps/plan/step-05-dependency-graph.md` runs a topological sort over `depends_on` and marks a phase parallel only when its epics have no dependency on one another. Atomic status writes via `pm-status.py` are what make concurrent epics safe at the state layer. **`parallel_mode`, `parallel_ceiling`, and `safe_batch_size` are not implemented** — they describe an intended adaptive model specced in `docs/superpowers/specs/2026-08-17-adaptive-parallelism-design.md`, not current behavior. Note that concurrent epics currently share one working tree with no source-file independence check; that spec addresses it.
```

- [ ] **Step 3: Correct the ATDD claim and the fix-cap description in CLAUDE.md**

Find the line reading:

```markdown
Optional: `bmad-ux-review`, `bmad-testarch-atdd`.
```

and replace it with:

```markdown
Optional: `bmad-ux-review`. (`bmad-testarch-atdd` was previously listed here, but no step file ever invoked it; its gating machinery has been removed.)
```

Then find the sentence in the **Quality gates** paragraph reading `only halts after 10 iterations (per-story or closure-level) if items remain unresolved` and replace `10 iterations` with:

```markdown
`max_fix_iterations` iterations (10 for CODE/MIXED, 3 for DOCS/CONFIG, per-skill in `customize.toml`)
```

- [ ] **Step 4: Restore the verify routing row in the activation digest**

Sub-project C's fix wave replaced a correct routing row with a less correct one, acting on a
review finding that proved wrong. `status-files.md` §7 contains a subsection titled
`` `verify` — two different checks behind one subcommand ``, and §7 states "Activation depends on
this distinction: it always runs `verify --scope epic` (structural)". `metrics-contract.md` §5
explicitly defers to §7 for that case.

In `skills/_shared/steps/shared/step-00-activate.md`, the routing table currently has:

```markdown
| understand what a `verify` failure actually checked | `references/metrics-contract.md` §5 (Enforcement — what is actually checked, and where) |
| know which fields a node carries, or diagnose a back-reference/structural `verify` failure | `references/status-files.md` §4 (Per-file schema) |
```

Replace those two rows with three:

```markdown
| diagnose a structural `verify --scope epic` failure | `references/status-files.md` §7 (Addressing — see "`verify` — two different checks behind one subcommand") |
| understand what `verify` enforces for a story or sprint | `references/metrics-contract.md` §5 (Enforcement — what is actually checked, and where) |
| know which fields a node carries | `references/status-files.md` §4 (Per-file schema) |
```

- [ ] **Step 5: Verify all routing anchors still resolve**

```bash
cd $REPO_ROOT
python3 - <<'PY'
import re
for p in ["skills/_shared/status-files.md","skills/_shared/metrics-contract.md"]:
    heads = {}
    for line in open(p):
        m = re.match(r"^## (\d+)\.\s+(.*)$", line)
        if m: heads[int(m.group(1))] = m.group(2).strip()
    print(p); [print(f"  §{k}: {v}") for k,v in sorted(heads.items())]
PY
grep -oE '§[0-9]+' skills/_shared/steps/shared/step-00-activate.md | sort -u | tr '\n' ' '; echo
```

Expected: every `§N` cited in the routing table appears in the printed heading list for the file
it names. Confirm §7 of `status-files.md` really is the Addressing section and really does
contain the `verify` subsection:

```bash
awk '/^## 7\./{f=1} /^## 8\./{f=0} f' skills/_shared/status-files.md | grep -c "two different checks"
```

Expected: `1`.

- [ ] **Step 6: Update docs/l3io-pm-reference.md**

That file documents the sprint-closure phase table and the fix-loop caps, both of which changed.
Find its closure phase table (the 7×4 grid under `### Sprint closure (step-04)`) and change the
UX review row's DOCS cell from `run` to `skip`. Then find every mention of a 10-iteration fix
cap and describe it as `{max_fix_iterations}` (10 CODE/MIXED, 3 DOCS/CONFIG). Locate them with:

```bash
cd $REPO_ROOT
grep -n "10 iteration\|UX review" docs/l3io-pm-reference.md
```

Add one sentence under that table noting the matrix now lives in
`steps/shared/step-01-classify-work.md` §4 and that this table mirrors it.

- [ ] **Step 7: Full gate**

```bash
cd $REPO_ROOT
npm run sync:scripts && npm run check:scripts
cd skills/_shared/tests && python3 test-pm-status.py 2>&1 | tail -3
```

Expected: check exits 0; `Ran 425 tests` / `OK`. **No test covers prose**, so the suite is a
regression guard on `pm-status.py` only — Steps 5 and the greps in Tasks 1 and 2 are the real
evidence for this plan.

- [ ] **Step 8: Verify no phantom knob is still presented as available**

```bash
cd $REPO_ROOT
echo "--- parallel_mode / parallel_ceiling / safe_batch_size outside the D spec ---"
grep -rn "parallel_mode\|parallel_ceiling\|safe_batch_size" \
  skills/ CLAUDE.md README.md docs/*.md 2>/dev/null \
  | grep -v "adaptive-parallelism-design" \
  | grep -vi "not implemented"
echo "--- dangling §15 ---"
grep -rn "§15" skills/ || echo "  NONE"
echo "--- ATDD machinery ---"
grep -rn "testarch" skills/_shared/ || echo "  NONE"
```

Expected: the first command prints only lines that explicitly mark the knobs unimplemented (or
nothing); `NONE` for the other two.

- [ ] **Step 9: Commit**

```bash
git add -A skills/ CLAUDE.md docs/
git commit -F - <<'MSG'
docs(l3io-pm): describe the parallelism that exists, and fix the verify routing row

CLAUDE.md documented parallel_mode, parallel_ceiling, and safe_batch_size with a
formula -- min(max_parallel_subagents, parallel_ceiling, safe_batch_size) -- that
no customize.toml defines and no step file computes, and step-05 cited a "§15" that
does not exist in a SKILL.md with three sections. Replaced with what actually runs,
plus an explicit note that those three knobs are unimplemented and a pointer to the
spec that designs them. Also records that concurrent epics currently share one
working tree with no file-independence check.

Corrects the claim that bmad-testarch-atdd is a working optional dependency -- no
step file ever invoked it -- and describes the fix cap as work-type-aware rather
than a flat 10.

Restores the verify routing row that sub-project C regressed. C's fix wave acted on
a review finding that status-files.md §7 was "addressing prose"; §7 in fact carries
a subsection titled "verify -- two different checks behind one subcommand", and
metrics-contract.md §5 defers to §7 for exactly the structural case activation
blocks on. The table now routes structural failures to §7 and keeps the §5 row C
added, which was a genuine improvement.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Signed-off-by: Shawn Anderson <sanderson@eye-catcher.com>
MSG
```

---

## Self-Review

**1. Spec coverage**

| Spec item | Task |
|---|---|
| §1 One matrix in `step-01`, with *Enforced by* column | 1 (Step 1) |
| §1 `{work_type}`-gated phases stay separate, labelled | 1 (Step 1) — stated in the inserted prose and as a Global Constraint |
| §2 `step-05` stops recomputing | 1 (Step 3) |
| §3 `sprint-closure.md` §8 drops its table | 1 (Step 4) |
| §4 UX review off for DOCS | 1 (Step 4), verified in 1 (Step 6), documented in 3 (Step 6) |
| §5 Work-type-aware configurable fix cap, all three sites | 2 (Steps 1-4) |
| §6 Remove dead ATDD gating | 1 (Step 2) for the machinery, 3 (Step 3) for the CLAUDE.md claim |
| §7 Document parallelism honestly, fix dangling `§15` | 3 (Steps 1-2) |
| §8 Restore the `verify` → §7 routing row | 3 (Step 4) |
| Verification 1: one `{skip_phases}` computation | 1 (Step 5) |
| Verification 2: no orphan phase on either side | 1 (Step 5) |
| Verification 3: no hardcoded `10` | 2 (Step 5) |
| Verification 4: no phantom knob, no dangling `§15` | 3 (Step 8) |
| Verification 5: no ATDD machinery | 3 (Step 8) |
| Verification 6: routing anchors resolve | 3 (Step 5) |
| Verification 7: `check:scripts` + 425 tests | 3 (Step 7) |

No gaps. Task 1 Step 6 adds a check the spec implies but does not list: an explicit cell-by-cell
comparison against today's behavior, so the one intended change is provably the only one.

**2. Placeholder scan**

No `TBD`/`TODO`/"similar to Task N"/"add appropriate error handling". Every step carries either
the literal text to insert or a runnable command with an expected result. Three steps ask the
implementer to read surrounding lines and keep prose grammatical (Task 1 Step 2, Task 2 Step 1,
Task 2 Step 3) — that is a judgement call that cannot be reduced to a literal patch, and each
says exactly what to check.

**3. Type consistency**

- `{max_fix_iterations}` is the binding name in Task 2 Steps 3, 4, 5 and in Task 3 Steps 3 and 6
  — consistent. The TOML keys are `max_fix_iterations` and `max_fix_iterations_non_code`,
  used identically in Task 2 Steps 1, 2 and 3.
- Task 2 Step 3 anchors on the sentence Task 1 Step 1 inserts (`For {work_type} = CODE or MIXED,
  {skip_phases} is empty unless an installed check fails.`) — ordered correctly, Task 1 first.
- Task 2's `sprint-closure.md` line number is marked pre-Task-1 with an instruction to find it by
  content, because Task 1 Step 4 removes ten lines above it.
- Task 3 Step 4's replacement rows cite `status-files.md` §7/§4 and `metrics-contract.md` §5;
  Task 3 Step 5 verifies exactly those.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-08-17-phase-gating-unification.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session using executing-plans, batched with checkpoints for review.

**Which approach?**
