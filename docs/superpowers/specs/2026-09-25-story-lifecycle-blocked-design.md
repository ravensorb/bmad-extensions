# Story-lifecycle `blocked` status — design

**Date:** 2026-09-25
**Status:** proposed design, not yet planned
**Informed by:** bmad-loop's terminal `blocked` state; peer-alignment conversation on 2026-09-25 with `avanade-bmad-extension`.

## 1. Why

The story status enum today has no clean way to say *"work started, cannot
complete pending external intervention."* The five states —
`backlog → ready-for-dev → in-progress → review → done` — describe a story's
progress toward completion but do not distinguish two very different reasons a
story might not reach `done`:

- **Failed** — the code doesn't do what the spec says; the fix loop iterates.
- **Halted** — the spec itself is under-specified, or an external dependency is
  missing, or a decision has not been made. No amount of fix-loop iteration
  moves the story forward until that condition changes.

Today those two collapse into "story stuck in `in-progress` or `review`." The
consequences show up in three places:

**The fix loop iterates against halted stories.** Per `customize.toml`,
`max_fix_iterations = 3`; a story that will never complete on this run consumes
three fresh subagent dispatches before being deferred to closure. That is a
turn-count cost multiplied by a session-cost curve that grows with the square of
turns.

**Calibration cohorts silently misclassify.** `derive_story_sample` (behind
every `set-actual` on a story) reads `completion_evidence.fix_iterations` to
route a sample into `clean` vs `reworked` cohorts (`calibration-model.md` §90).
A story that closed as `done` after external intervention resolved a spec gap
is not "reworked" in the sense the cohort is meant to capture, but there is no
signal today to keep it out.

**Sprint/epic closure treats halts as ordinary failures.** `sprint-closure.md`
reads story statuses at close and reports unresolved findings; a story `stuck
in review pending external decision` is functionally indistinguishable from a
story `stuck in review because a Critical finding is unresolved`. Different
remedies; same closure report.

**And bmad-loop already has this concept.** The peer conversation this design
came out of noted that bmad-loop's terminal status set is `draft /
ready-for-dev / in-progress / in-review / done / blocked`. Aligning on
`blocked` gives interop a working vocabulary for the one status that has real
semantic weight (`draft` vs `backlog` is cosmetic; `in-review` vs `review` is
cosmetic; `blocked` is not).

## 2. What `blocked` means

**A story enters `blocked` when work has started AND cannot complete without an
external change of state.** External means: outside the dev loop's control.

Examples that qualify:

- A spec question the story cannot proceed against until answered.
- A missing dependency (a service, a library version, a credential, another
  story's output) the fix loop cannot produce.
- A decision only a human can make — approval, priority, architecture
  direction.
- A failure of a system the story integrates with that requires operator
  intervention.

Examples that do NOT qualify:

- A failing test whose cause is in the story's own diff (that is `in-progress`,
  the fix loop's territory).
- An unresolved Critical/High/Medium finding from code review (that is
  `review` — closure will surface it).
- A story the team has decided to drop (that is `done` with a rejection note,
  or a resolve of the tracking issue; still to be decided which — see §11).

The distinction that matters: **fix loop iterations do not help.** If iterating
would help, use `in-progress`. If it would not, use `blocked`.

## 3. Transitions

`blocked` is entered only from active states and exited only to active states.
It is never a terminal state alongside `done`; it always resolves.

```
       ┌────────────────────┐
       ▼                    │
   backlog                  │
       │                    │
       ▼                    │
   ready-for-dev            │
       │                    │
       ▼                    │
   in-progress ◄──┐         │
       │          │         │
       ▼          │         │
    review ──────┤         │
       │          │         │
       ▼          ▼         │
     done      blocked ─────┘
                  │
                  └── (exit-to-done requires --resolution)
```

**Valid entries:** `in-progress → blocked`, `review → blocked`.

**Valid exits:** `blocked → in-progress` (unblocked, resume work).
Also `blocked → done` **only when `--resolution` is supplied** (the story was
resolved by the same event that unblocked it, e.g. "spec change removed the
need for this story"). This is a rare path; the ordinary shape is unblock →
resume.

**Not permitted:** `backlog → blocked`, `ready-for-dev → blocked` (a story that
hasn't started can't be blocked; it's just not ready — file the impediment as a
backlog issue instead), `done → blocked` (`done` is terminal).

**Enforcement:** `pm-status.py set-status` gains a transition table (below) and
exits 2 on any invalid pair, naming both the current and requested statuses.
Today set-status only validates the *target* against `VALID_STORY_STATUS`; the
new gate is per-transition.

**Amendment (2026-09-25, during Stage 1 implementation).** The strict linear
diagram above is the DESIGN INTENT; the SHIPPED table is deliberately looser.
Fourteen existing pm-status.py tests exercise transitions the strict table
forbids (`backlog → done`, `ready-for-dev → done`, `done → done` for
idempotence, `done → in-progress` for reopen paths driven by `repair-issue
--action reopen`, `done → review` after `import-node`, and so on). These are
long-standing, correct behaviours — reopen for more work, idempotent
re-application, import-then-adjust flows — and forbidding them would either
break existing consumers or force cosmetic waypoint transitions that add turn
cost with no invariant gain.

**The two invariants the shipped table actually gates:**

1. **The blocked lifecycle is clean.** `blocked` can only be entered from
   `in-progress` or `review`; can only be exited to `in-progress` or `done`
   (the latter requiring `--resolution`). `backlog → blocked` and
   `ready-for-dev → blocked` and `done → blocked` are refused. This
   preserves the design's core: `blocked` names work that has *started* and
   halted, never work that has never started or already finished.
2. **`done → blocked` is refused specifically** so that a done story
   reopened for more work must go through `done → in-progress → blocked`
   rather than `done → blocked` directly. This keeps `blocked` entered only
   from active work.

**Free movement between non-blocked, non-done statuses is allowed.** So is
`done → non-blocked` for reopen and idempotent noops. The design's linear
diagram remains the *narrative* shape of the healthy path; the shipped table
is the *gated* shape.

## 4. `pm-status.py` changes

**Status enum.** `VALID_STORY_STATUS` grows one entry:

```python
VALID_STORY_STATUS = {"backlog", "ready-for-dev", "in-progress", "review",
                      "done", "blocked"}
```

Sprint and epic status sets are unchanged. A sprint or epic status of `blocked`
is a separate design decision, kept out of scope here — sprints and epics
compose from their children, and a "sprint one of whose stories is blocked" is
already visible as `blocked_stories > 0` in the roll-up.

**Transition validator.** A new module-level constant. Note the amendment
in §3 explaining why the shipped shape is looser than the diagram:

```python
VALID_STORY_TRANSITIONS = {
    "backlog":       {"ready-for-dev", "in-progress", "review", "done"},
    "ready-for-dev": {"backlog", "in-progress", "review", "done"},
    "in-progress":   {"backlog", "ready-for-dev", "review", "done", "blocked"},
    "review":        {"backlog", "ready-for-dev", "in-progress", "done", "blocked"},
    "blocked":       {"in-progress", "done"},   # done requires --resolution
    "done":          {"backlog", "ready-for-dev", "in-progress", "review", "done"},
    # done -> blocked deliberately forbidden: reopen must go through in-progress
}
```

`cmd_set_status` reads the node's current `status` before writing, checks
`(current, new)` against the table, and exits 2 with
`invalid story transition {current} -> {new}` when the pair is not present.
The special case `blocked → done` additionally requires
`--resolution "<free text>"` be present; missing it exits 2.

**Reason field on blocked writes.** `cmd_set_status --status blocked` requires
`--reason "<free text>"`. Stored on the node as `blocked_reason`; also written
to the event log payload. Missing reason exits 2 with a clear message. When a
subsequent transition leaves `blocked`, `blocked_reason` is removed from the
node (blocked history lives in the event log; the current node reflects only
current state).

**Event log.** Every status transition already appends a `status` event. Add
two paired events for blocked spans:

```jsonl
{"ts": ..., "event": "block_open",  "story": "E001-S01-002", "reason": "..."}
{"ts": ..., "event": "block_close", "story": "E001-S01-002",
 "duration_hours": 6.5, "resolution": "..."}
```

Duration is derived at close from the `block_open`'s ts. `resolution` is
present only when the close was `blocked → done`; on `blocked → in-progress`
it's absent. These events are emitted alongside the corresponding `status`
event, not in place of it — a caller reading `status` events alone still sees
the full lifecycle (`in-progress → blocked → in-progress → review → done`).

**`--no-events` behavior is unchanged** — a blocked status write opts out of
BOTH the `status` event AND the `block_open` event under one flag. Same rule
that applies elsewhere.

## 5. Calibration semantics

A story that spent any time `blocked` is **excluded from `elapsed_hours` sample
generation**, and the exclusion is visible to the operator:

- `elapsed_hours` measures AI wall-clock. A blocked story's wall-clock includes
  time waiting on humans; folding that into calibration would poison the
  `scope` ratio for future stories.
- `set-actual`, when the node's event log shows any `block_open` for this
  story since its most recent `dispatch_open`, emits
  `WARN blocked story {key} — elapsed_hours sample deferred (event log shows
  {N.N}h in blocked); man_hours, hitl_hours, tokens_k still recorded` and
  skips the `elapsed_hours` contribution to the sample. Other metrics are
  unaffected. The inline duration lets an operator eyeball whether the
  exclusion is warranted — a 5-minute block that resolved quickly probably
  didn't poison much; a 6-day block obviously did — without cross-referencing
  the event log.
- `man_hours` and `hitl_hours` are ASSESSED, not observed, so they are
  unpoisoned by real time in blocked — they measure counterfactual effort and
  human attention respectively.

**`completion_evidence.blocks_seen: int` for O(1) closure observability.**
Closure walks story nodes at close time; a per-story `block_open` event scan
is O(n) per story. Adding a small counter on the node:

```yaml
completion_evidence:
  blocks_seen: 2
  fix_iterations: 1
```

incremented on every `block_open` for this story, gives closure an O(1) read.
Not used for cohort routing (Q4 keeps that clean); purely observability so
closure reports `Blocked stories (2, cumulative block events: 5)` without
re-scanning the log. Cheap counter, load-bearing under wide sprints.

**`fix_iterations` semantics under `blocked`.** A story that enters `blocked`
from `in-progress` and later resumes does **not** count the block as a fix
iteration. `completion_evidence.fix_iterations` remains the count of
review-driven fix cycles; a block is neither a review finding nor a fix.
`derive_story_sample`'s `clean`/`reworked` cohort routing keeps its current
rule: `fix_iterations == 0` → `clean`, `> 0` → `reworked`. Blocks are
orthogonal.

**Long-term follow-up (out of scope here):** a `block_hours` field on the
per-story sample so calibration eventually learns the "how long do stories
spend blocked" distribution. Named here so a future design considers it.

## 6. Fix loop interaction

`l3io-pm-execute`'s per-story fix loop (`customize.toml`'s
`max_fix_iterations`) already has an exit path when review returns clean. Add
one more:

**If review returns `blocked`, the fix loop halts immediately for THIS story.**
No further iterations are attempted for this story on this run. The story
remains `blocked` on disk with its `blocked_reason`. Neither `fix_iterations`
nor any subsequent sample is written for this story on this dispatch.

**Per-story, not per-sprint.** The sprint's other stories continue through
their own dispatches. A block halts only the story it happened to; sibling
stories are unaffected. Step-file authors reading this design need this
distinction explicit — the halt is one story-scope out of the batch, and the
batch continues.

The alternative — iterating the fix loop against a `blocked` story — would
either loop N times producing no progress (fix loop assumes local defect) or
require an in-loop check that duplicates §5's decision. Halting at first block
is simpler and matches the semantics.

## 7. Sprint / epic closure interaction

Sprint and epic closure both walk their child stories at close time.

**A blocked story fails closure with a distinct diagnostic.** Currently
`sprint-closure.md` lists undone stories under "unresolved findings" (with
Critical/High/Medium finding blocking). Blocked stories get their own line:

```
BLOCKED stories:
  - E001-S01-002 — Spec question: does the token refresh accept a jitter?
```

Closure exits `BLOCKED:` (not `FAILED:`), matching the phase-status vocabulary
`step-05-epic-loop.md:464` already uses. The distinction matters for the
operator: `FAILED:` says "the run produced work that failed"; `BLOCKED:` says
"the run produced work that halted pending action."

**Epic closure preserves the same distinction.** A single blocked story blocks
the epic (`BLOCKED:` at that level too); resolving all blocked stories AND
having no unresolved Critical/High/Medium findings is what unblocks epic
closure.

## 8. Reports and metrics

**`pm-status.py report`.** Every format (`tree`, `json`, `md`) grows a
"Blocked stories" section listing key + reason + time-in-blocked. In the
`tree` format:

```
Blocked stories (2):
  E001-S01-002  blocked 6.5h  Spec question: token refresh jitter
  E002-S02-004  blocked 1.1h  Missing credential — auth provider
```

**Stalled dispatch.** `--stall-minutes` already flags long-running dispatches.
Blocked stories are shown separately even when their dispatch has closed —
they are stalled at the WORK level rather than the DISPATCH level, which is
what the operator needs to see.

**Show.** `pm-status.py show --sprint` already prints per-story status.
Blocked stories appear with `[blocked: <reason>]` inline. `show --epic` prints
the sprint roll-up; a `blocked_stories: N` field appears when N > 0.

## 9. Alignment with bmad-loop

bmad-loop's terminal status set is
`draft / ready-for-dev / in-progress / in-review / done / blocked`.

After this design lands, ours becomes
`backlog / ready-for-dev / in-progress / review / done / blocked`.

The three points of comparison:

- **`blocked`** — same term, same semantics on both sides (work halted
  pending external intervention). This is the interoperable bit.
- **`backlog` (ours) vs `draft` (bmad-loop)** — cosmetic difference. Their
  `draft` is "planning incomplete"; our `backlog` is "planned, not yet
  ready-for-dev." Similar-enough intent; distinct names because our lifecycle
  originates from planning rather than from intake.
- **`review` (ours) vs `in-review` (bmad-loop)** — cosmetic difference.

**No renames on our side.** The two cosmetic differences are stable; renaming
them for parity would break every consumer that reads our status names for no
functional gain. `blocked` alignment is the win.

**Peer-alignment commitment (2026-09-25):** the two extension packages have
agreed to align on `blocked`'s enum position and semantics before either side
lands the implementation. This design doc is what gets pinged over.

## 10. Upgrade path

**No migration required for existing projects.** All existing stories are
non-blocked; the enum expansion is additive. Reading a pre-`blocked` project
under the new code is a no-op.

**Prose that switches on `story.status` needs an audit at land time.**
Concretely:

- Every `set-status --status X` invocation in a step file — must not attempt
  to write `blocked` without `--reason`.
- Every `if status == "..."` in step-file prose — must decide whether the
  `blocked` branch is handled.
- Every `report`/`show`/`stats` rendering path — must have a display for
  blocked stories (§8).

The audit is grep-driven at land time, not a mechanical check. `check-docs`
check 4 already verifies `set-status --status` values against the enum, so a
prose call to `--status blocked` without `--reason` will fail check 4 at land
time if the enum-validation extension covers required flags per value; that is
worth adding.

**Check 4 extension is reusable across sibling packages** (2026-09-25 peer
observation). A required-flag-per-status rule is a general shape:
`set-status --status blocked` requires `--reason`, and future statuses may
have similar rules. The extension itself — reading each subcommand's argparse
choices and asserting per-choice required companion flags — is portable across
any sibling package with the same check 4 shape. Ping the peer before landing
the extension so either side can reuse the same code path.

## 11. Open questions

Questions left explicit so the mid-design ping with the peer knows what is
still fluid:

- **Where does the reason string live on disk when blocked?** Recommendation:
  `blocked_reason` field on the story node, cleared on exit-from-blocked. The
  event log carries the history.
- **Do we distinguish "blocked by human" vs "blocked by machine (missing
  dependency)"?** Recommendation: no. The reason string captures the shape;
  adding a taxonomy prematurely commits to categories that projects may
  disagree on.  Observation (2026-09-25 peer review): projects that track a
  blocked story via `resolves:` back to a backlog issue in `state/issues.yaml`
  get a human/machine axis for free through the issue's `severity`
  (`Low`/`Medium`/`High`/`Critical`) and `kind`
  (`defect`/`spec-change`/`spec-proposal`). Do not build a formal
  cross-reference or an inheriting taxonomy — the redundancy would double the
  fields to keep in sync — but do name the shape here so an operator asking
  "why is this blocked" has one place to look.
- **What about a story we're dropping?** Recommendation: keep this out of
  `blocked` semantics. A dropped story is either `done` with a
  `--resolution "not built — <reason>"` (the story shipped as nothing, the
  event log carries why), or the tracking backlog issue is resolved with
  `wontfix`. `blocked` is for halts intended to resume. The `--resolution`
  vocabulary maps cleanly onto `state/issues-resolved.yaml`'s
  `resolution: fixed | wontfix | duplicate | obsolete` — the story-level
  resolution and the issue-level resolution use the same words.
- **Does the fix loop's exit-to-blocked count as a fix iteration?** Recommend:
  no (§6). But this is worth calling out in the mid-design ping because it
  affects the `reworked` cohort's semantics.
- **Should `blocked` propagate up to sprint/epic status?** Recommend: no
  initially; the roll-up already surfaces `blocked_stories: N`, and sprint/epic
  `blocked` would need its own transition table and closure semantics. Related
  cosmetic wart named in §13 out of scope.
- **Does a story `depends_on` a blocked story auto-inherit `blocked`?**
  Recommendation: **no automatic transitions.** If E001-S01-001 has
  `depends_on: [E001-S01-002]` and E001-S01-002 transitions to `blocked`,
  E001-S01-001 stays at its current status (`ready-for-dev` or `in-progress`).
  When a dispatched subagent picks up E001-S01-001 and discovers its dep is
  blocked, THAT is when it explicitly runs
  `set-status --status blocked --reason "blocked on dep E001-S01-002"`.
  Explicit-and-narrow beats automatic-and-implicit: an auto-cascade would
  multiply the blast radius of a single block (five dependent stories all go
  blocked with no operator involvement, each requiring its own resolution
  even when the root cause is one thing). `depends_on` is
  a *planning-time* input to phase parallelism (`step-05-dependency-graph.md`)
  and a *dispatch-time* check for the subagent; making it a status-cascade
  vector is a different design.

## 12. Adjacent decision — inventory `note` field

The same peer conversation flagged the inventory `note` field on
`bmad-dependencies.json` entries. Current state after `e630516`: `note` is
read from `related` entries and rendered as the second line of the `related`
row in `bmad-deps.py verify`'s output. `bmad-deps.py` reads any entry's `note`
in the JSON output, but the text rendering only surfaces it for `related`.

**Decision — keep `note` scoped to `related` output in text mode.**

Reasoning:

- **`required` and `optional` entries** already have `reason` fields (visible
  in the JSON output for inventory maintainers). A `note` field for the CLI
  would either duplicate `reason` or force a distinction between "what an
  inventory maintainer needs" and "what a CLI user needs" that this codebase
  has not felt pressure to make.
- **`deprecated` entries** carry `replaced_by`, which is exactly the note a
  CLI user needs. Adding a `note` would add a second string competing with
  it.
- **`related` entries** are the case where a CLI user needs to know what the
  detected skill IS — they are third-party tooling users may not recognize.
  `related bmad-loop-sweep is installed alongside this package — <what this
  skill does>` is the shape that adds real information at read time.

**When to revisit.** If a `required` or `optional` entry ever needs to surface
a per-installation hint to end users (not just to inventory maintainers), the
argument changes and a broader `note` field earns its keep. Naming the trigger
here so a future contributor can identify it.

## 13. Out of scope

- **Sprint / epic `blocked` status.** Out of scope; the roll-up already
  surfaces `blocked_stories: N` and adding node-level statuses for the
  parents would double the transition-table work.
  **Known cosmetic wart** (2026-09-25 peer observation): a sprint whose stories
  are all `blocked` still reports `status: in-progress` with
  `blocked_stories: N` where N == total. Technically correct; user-facing
  reads as "actively being worked" when nothing is. `pm-status.py show
  --sprint` should surface this by rendering the sprint header as
  `S01  status=in-progress (all N stories blocked)` when the ratio is 1.0.
  Not a design flaw, not a status transition, just a display refinement worth
  taking at implementation time.
- **Automatic block detection.** Whether the fix loop can classify a review
  finding as "unresolvable within this loop" and auto-transition to `blocked`
  is a separate design. First cut: transitions are explicit, from step files
  or from a human via `pm-status.py set-status`.
- **`block_hours` per-sample calibration metric.** Named in §5 as a follow-up;
  belongs in a future calibration-model rework, not this design.
- **A dedicated `pm-status.py block` / `unblock` subcommand as sugar over
  `set-status --status blocked/--status in-progress`.** Weigh at implementation
  time; keeping it out of this design leaves it open.
