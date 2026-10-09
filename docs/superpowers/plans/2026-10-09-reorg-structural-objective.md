# Reorg: Structural Objective + Dependency-Safe Balancing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorient `/l3io-plan reorg` to optimise **dependency structure** rather than effort, move its check to where its data exists, and add a dependency-safe balancing pass — after closing the two validation holes that make balancing unsafe today.

**Why:** Reorg structurally cannot change effort — it moves stories, it never makes work smaller. The one way it moves effort is second-order, through closure and orchestration bands as sprint/epic counts change. Meanwhile the effort data is usually absent exactly when a plan is cheapest to reshape, and `depends_on` is a declared fact where `elapsed_hours` is a band times a calibration ratio — two inferences deep. Optimising hard on the softer number is backwards.

**Spec:** `docs/superpowers/specs/2026-10-09-plan-reorg-design.md` (§2 is revised by Task 5)

**Tech Stack:** Python 3.11+ (PEP-723, `uv run`), `ruamel.yaml`, `unittest`; Node for the doc and sync gates.

## Decisions

Settled in discussion 2026-10-09; recorded so no task re-opens them.

| # | Decision | Rationale |
|---|---|---|
| D1 | Unbacked cross-epic story dependency **warns now, errors later** | Existing projects likely carry these. Erroring on upgrade blocks runs on a defect they did not cause. Promote to error once projects are clean. |
| D2 | Balancing is a **second pass inside `reorg`**, not its own mode | Balance is meaningless until structure is settled; coupling them reflects that. One journal entry, one confirmation. |
| D3 | **One release** when all four phases land | User's call, made with the cost stated: the phase-scheduling defect (Task 2) stays in the wild until then. |
| D4 | `sprint-imbalance` **survives as a reported impact**, never a driver | Still measured and shown; becomes Stage B's input rather than Stage A's finding. |

## Global Constraints

- `skills/_shared/` is canonical. **Edit there, then `npm run sync:scripts`.** Per-skill edits are silently overwritten.
- **Never hand-edit a `payload-manifest.json`.** Regenerate with `node scripts/write-payload-manifest.mjs`; `sync:scripts` does not do it.
- **Put each thing where it belongs, and reuse what exists.** The reorg scripts are single-consumer, so balancing logic belongs in `l3io-plan/scripts/`, not in `pm-status.py` — by ADR-0001's placement rule, not by line count. Before adding any helper, check whether `pm-status.py` or the reorg scripts already do it; a duplicated helper that drifts is the failure mode this rule exists to prevent.
- `skills/_shared/pm-status.py` is under a **10,000-line** cap enforced by check 12 (at **9,462** now). Treat it as a tripwire, never as a design input: ADR-0001 says plainly it "is not a judgement that the file is fine at 10,000 lines; it is headroom bought deliberately while the structural options are unavailable." **Never move code out of `pm-status.py` to stay under it** — pressure to keep the number down is pressure to misclassify a multi-consumer helper as single-consumer and copy it, which is worse than the growth avoided. If a change genuinely belongs in `pm-status.py` and trips the cap, that is the conversation the cap exists to force: ADR-0001's revisit path is Option B (a package directory under `_bmad/scripts/`), whose only surviving objection is install atomicity — test whether a directory-level `os.replace` answers it.
- **Single-consumer code lives in its skill's `scripts/`** (ADR-0001). The reorg scripts stay in `l3io-plan`.
- **Check 26:** no file under `skills/` assembles a state path. Address state by `--state-root` plus node keys.
- **Check 31:** no `/l3io-*` invocation in markdown carries a `--flag`.
- **Check 4:** every code-formatted `pm-status.py` invocation must parse against the real argparse surface.
- **Check 24:** a pointer in a shared file must resolve in **every** skill its sync group delivers to. `reorg-*.py` lives only in `l3io-plan`, so only files delivered to `l3io-plan` alone may name it.
- Reorg writes **planned work only**. Active and archived are read-only input.
- **Nothing is deleted.** Retirement archives with a reason.
- The agent emits a **target placement**, never operations. Operations are derived by diffing.
- ADR numbers come from `pm-status.py adr-reserve` at the moment of writing (ADR-0005). **Never hand-picked.**
- Conventional Commits, every commit signed off (`git commit -s`).

## Review Focus

Input classes the goal implies that no task's happy path exercises. Each has its test assigned to the task that owns the code.

1. **A dependency that crosses both an epic and a sprint boundary.** Task 1's rule is scoped to same-epic ordering; Task 2's to cross-epic backing. A single edge that is both must be judged by exactly one of them, not double-reported and not dropped between them. → Tasks 1 and 2, with a shared test.
2. **An epic whose sprint keys are non-contiguous** (`S01`, `S03`, `S07`). Sprint *index* ordering must derive from sorted key order, not from the numeric gap, or a dependency from `S03` to `S07` reads as adjacent. → Task 1.
3. **A dependency on a story in `active/` or `archived/`.** Those are out of the writable set and carry no target row. Ordering rules must skip them rather than treat the missing row as "position unknown" and refuse. → Task 1.
4. **A plan with zero estimates reaching the balance pass.** Stage B must self-skip, not divide by zero or propose a balance from absent data. → Task 7.
5. **A Stage B move that is legal in isolation but undoes Stage A.** Balance must not re-create a crossing edge Stage A removed. → Task 7.
6. **A cycle introduced only by the combination of both stages.** Each stage's target is validated alone; the composition is what ships. → Task 7.

---

## Phase 1 — Close the validation holes

Both are live defects today, reachable by a hand-written story dependency with no reorg involved. Stage B cannot be built on top of either.

### - [x] Task 1: Ordering compares sprint position within an epic

`reorg-validate.py`'s ordering rule fires only when two stories share a sprint:

```python
if (ke, ks) == (de, ds) and isinstance(ko, int) and isinstance(do, int) and ko <= do:
```

Sprints inside an epic are **always sequential**, so a dependency placed in a later sprint of the same epic is backward and is accepted today. Verified 2026-10-09: same-sprint violation refused, cross-sprint violation returns `OK target is valid`, exit 0.

- Compare position as `(sprint_index, order)` for same-epic pairs; derive `sprint_index` from **sorted sprint key order**, not numeric arithmetic (Review Focus 2).
- Different-epic pairs stay out of this rule — the phase graph orders epics, and epics in one phase run concurrently. Task 2 owns that edge.
- A dependency outside the planned set is skipped, not refused (Review Focus 3).
- **Tests:** promote today's reproduction verbatim; non-contiguous sprint keys; same-sprint regression must still pass; dependency on active/archived skipped.
- **Mutation check:** revert the rule to same-sprint-only — the cross-sprint test must fail.

### - [x] Task 2: An unbacked cross-epic story dependency is reported

`E001-S01-001` depending on `E003-S01-001` with no `E001 depends_on E003` is invisible three ways: the analyzer is silent (one crossing edge is below the `cross-epic-coupling` threshold, deliberately), the validator returns `OK`, and the phase graph is built from **epic-level** declarations so both epics land in the same parallel phase. `step-05` checks story-level keys **exist**, never what they imply for ordering.

Per D1 this **warns**, and does not halt.

- `reorg-analyze.py`: new finding `unbacked-cross-epic-dependency`, severity `warn`, **no minimum-edge threshold** — one is already a scheduling error, unlike ordinary coupling.
- `step-05-dependency-graph.md`: report each unbacked edge, naming the epic-level `depends_on` that would back it. Do not halt, do not auto-derive (D1).
- Record in the step file **why** it warns rather than errors, and what would promote it.
- **Tests:** single unbacked edge is reported (today it is silent); a *backed* edge is not reported; an edge that is both cross-epic and cross-sprint is judged once (Review Focus 1).

### - [x] Task 3: Phase 1 regression suite

- Fold Tasks 1–2 tests into `tests/l3io-plan/test-reorg-validate.py` and `test-reorg-analyze.py`.
- Confirm all 26 Python suites and seven gates pass.

---

## Phase 2 — Reorient the objective

### - [x] Task 4: Analyzer measures structure

- Keep `cross-epic-coupling`. Add **chain depth in hops** and **cohesion** (stories that depend on each other, or cite the same `Spec:` anchors, belong together).
- Demote `sprint-imbalance` to an impact: still measured and emitted, severity `info`, never a proposal driver (D4).
- The weighted critical path stops being the objective. Chain depth in hops serves the spec's stated goal — *"reduce the cost of discovering a problem late"* — better than hours do: each hop is a handoff where a wrong assumption propagates.
- **Tests:** an **unestimated** plan still yields actionable findings (guarantees today's test A); determinism; `sprint-imbalance` never appears at `warn`.

### - [x] Task 5: Revise the spec and record the ADR

- `2026-10-09-plan-reorg-design.md` §2: objective becomes dependency structure. State plainly that reorg cannot change effort, and that effort moves only through closure/orchestration overhead.
- Reorg's report stops using the words "critical path" — it says what it measures. This also removes the two-different-critical-paths-in-one-output problem.
- **ADR via `adr-reserve`** at the moment of writing, covering both this objective change and the re-parenting invariant amendment still outstanding (placement and two-trees rules are about *status* transitions; re-parenting is a second axis).

---

## Phase 3 — Move the check to where its data is

### - [ ] Task 6: Structural check early, weighted check late

- Structural shape check after `step-05` — needs `depends_on` only, so it is available there. If findings, suggest `/l3io-plan reorg` **before** estimation and snapshot generation, so a user is not paying for a shape they are about to change.
- `step-06` §5.1 keeps only what needs estimates.
- **Tests:** empty tree silent; unestimated tree yields structural findings at the early point and nothing at the late one; badly-shaped estimated tree yields both, at the right points.

---

## Phase 4 — Dependency-safe balancing

### - [ ] Task 7: Stage B

Per D2, a second pass inside `reorg`, running only when estimates exist.

- Same engine: `dump-plan → analyze → target → validate → derive → apply → journal`. Today's test D confirms the target format, validator and derive already handle balance-shaped moves unchanged.
- **Constrained move set:** Stage B may shuffle membership only where dependencies permit, and may not re-create a crossing edge Stage A removed (Review Focus 5).
- Self-skips with a stated reason when no estimates exist (Review Focus 4).
- One journal entry covering both stages, one confirmation.
- **Tests:** a balancing target that moves a story past its dependent **must be refused** — impossible to assert before Task 1, which is the proof Task 1 was the prerequisite; Stage B self-skips unestimated; the composition of both stages is cycle-free (Review Focus 6).

---

## Validation Strategy

Every phase is validated by **building the tree and running the real scripts**, not by reading. Today's four probes become the regression baseline:

| Probe | Asserts | Status today |
|---|---|---|
| A — structural findings with zero estimates | Stage A can run pre-estimation | ✅ passes; Task 4 guarantees it |
| D — balance move validates and derives | the engine needs no changes for Stage B | ✅ passes |
| B — backward dependency across sprints | ordering is enforced | ❌ **accepted** → Task 1 |
| C — unbacked cross-epic story dependency | scheduling errors are visible | ❌ **silent** → Task 2 |

**Mutation testing is required, not optional**, for Tasks 1 and 2: revert the rule, confirm the test fails. A test that passes against the pre-change source did not arrive — the discipline that caught eight silently-lost hunks in the adopter's port.

**Gates:** all seven, plus `npm run test:python` (26 suites) and `smoke:install` before release.

## Risks

- **Task 2 is reported but not enforced (D1).** A project can keep an unbacked edge and keep mis-scheduling. Accepted deliberately; the warning names the fix.
- **D3 holds the Phase 1 defect fixes until all four phases land.** Stated at decision time.
- **Two stages, one engine** risks Stage B silently undoing Stage A. Review Focus 5 and Task 7's test are the guard; the validator is the only thing that makes it structural rather than conventional.
