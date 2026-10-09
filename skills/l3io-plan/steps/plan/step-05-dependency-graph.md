# Step 05: Dependency Graph

Communicate all responses in `{communication_language}`.

Builds the execution dependency graph from `{epic_index}`. Detects cycles,
validates all referenced keys, and produces a topologically sorted phase plan.

---

## 1. Validate depends_on references

For each epic in `{epic_index}`:
- For each key in `depends_on`:
  - If the key is in `{epic_index}` (active or backlog) — valid forward dependency.
  - If the key is in `{archived_epic_keys}` and that epic has `status: done` — valid (already complete).
  - If the key is in `{archived_epic_keys}` but status is not done — flag as **error**: dependency on a non-done archived epic.
  - If the key is not found anywhere — flag as **error**: unknown epic key.
  - If the key equals the epic's own key — flag as **error**: self-dependency.

Story-level `depends_on`:
- Each key must exist in `{story_index}`.
- Unknown story keys → flag as error.

### 1.1 A story dependency that crosses epics must be backed by the epic graph

**Existing is not the same as scheduled.** The checks above ask only whether a story key
resolves. Phases, built in §3, come from **epic-level** `depends_on` — so a story dependency
crossing `E001 → E003` with no `E001 depends_on E003` behind it leaves both epics with no
edge between them, lands them in the **same parallel phase**, and runs them concurrently while
one needs the other finished.

For each story-level `depends_on` whose target sits in a different epic, check that the
depending story's epic declares that epic in its own `depends_on`. Report each one that does
not:

```
⚠️  {n} story dependency(ies) cross an epic boundary the epic graph does not know about:
      E001-S01-001 → E003-S01-001   (E001 does not declare depends_on: [E003])
    Phases come from epic-level dependencies, so these epics can be scheduled to run
    concurrently. Add the epic-level dependency, or move the story.
```

**Report, never halt.** A hand-written story dependency produces this with no reorg involved,
so existing projects are likely to carry one; halting would block a plan run on a defect the
user did not cause. The message names the one line of YAML that fixes it. This is expected to
become an error in a later release once projects are clean — until then it must not change
`{readiness}` or stop the run.

**Do not auto-derive the epic dependency.** Inferring `E001 depends_on E003` from the story
edge would silently rewrite the declared graph, and a story dependency that was itself wrong
would become a wrong phase plan with no trace of where it came from.

`/l3io-plan reorg` reports the same thing as `unbacked-cross-epic-dependency`, from the same
rule, so the two agree by construction.

## 2. Detect cycles (epic level)

Run a depth-first cycle detection over the epic dependency edges:

For each epic E with `depends_on: [A, B, ...]`:
- Traverse the dependency chain recursively.
- If E is encountered again during traversal → cycle detected.

Report all cycles found:
```
🔴 Dependency cycle detected: E001 → E003 → E001
```

If any cycle or invalid reference is found, set `{cycle_detected}` = true and halt:
```
BLOCKED: dependency graph has errors — resolve before continuing.
```

## 3. Topological sort → phases

If no errors, group epics into parallel phases using Kahn's algorithm:

1. Start with all epics that have no `depends_on` (or all dependencies done/archived). → **Phase 1**
2. Remove those epics from the pending set. Any epic whose all dependencies are now in completed phases is eligible for the next phase. → **Phase 2**
3. Repeat until all backlog epics are assigned.

**Parallel within a phase:** Epics in the same phase have no dependencies on each other and can run concurrently.

**Example output:**
```
Phase 1 (parallel): E001, E002
Phase 2 (parallel): E003           ← depends on E001 + E002
Phase 3 (sequential): E004         ← depends on E003 only
```

Record as `{phases}`:
```
phases:
  - phase: 1
    parallel: true
    epics: ["E001", "E002"]
    dependencies: []
  - phase: 2
    parallel: true
    epics: ["E003"]
    dependencies: ["E001", "E002"]
  - phase: 3
    parallel: false
    epics: ["E004"]
    dependencies: ["E003"]
```

`parallel` is true if the phase has more than one epic, or if a single-epic phase has no ordering constraint (always true for Phase 1 with one epic).

## 4. Identify the longest dependency chain (structural)

**This step does not compute the weighted critical path, and must not try.** `step-estimate`
runs *after* this one, so the epic estimates a weighted path needs do not exist here on a first
plan, and on a re-plan they are the previous generation's — about to be overwritten two steps
later. This section used to read `estimate.elapsed_hours_high` from state and fall back to "all
epics in phase order, no differentiation" when it found nothing, which is what every first plan
got: a headline critical path that was just the epic list. The weighted path is computed in
`step-06-plan-output.md` §5, from the per-phase estimate blocks that step builds **after**
estimates are written.

What *is* computable here, because it needs no estimates, is the structural one: the longest
chain of `depends_on` edges. It is the ordering constraint the graph imposes no matter what
anything costs.

Walk the dependency edges and record the longest path by **edge count**:

Record as `{longest_chain_epics}` = the epics on that chain, in dependency order. A graph with
no edges at all has no chain — record an empty list and say so rather than listing every epic,
which would imply an ordering constraint that does not exist.

## 5. Report graph

```
Dependency graph:

Phase 1 (parallel — {count} epics):
  • E001 "Auth Layer" — no dependencies
  • E002 "API Gateway" — no dependencies

Phase 2 (parallel — {count} epics):
  • E003 "Mobile App" — depends on: E001 ✅, E002 ✅

Longest dependency chain: E001 → E003  (3 epics)
```

No hours on this line. Estimates are written two steps later, so any duration printed here
would either be the previous generation's or invented — and the two `estimated_hours_*` tokens
this line used to carry were never bound anywhere, so it printed the token text verbatim.

## 6. Check the plan's shape — here, before anything is estimated

**This is the earliest point the check can run, and the earliest is where it belongs.** Every
finding a reorg can act on is structural — it needs `depends_on` and nothing else — so the
shape of the plan is fully knowable now, three steps before `step-estimate` and four before a
snapshot is written. Reporting it later would mean telling a user their grouping is wrong only
after they have paid to estimate it and generate a snapshot of the shape they are about to
change.

Read-only; writes nothing and takes no lock:

```bash
uv run {pm_status} dump-plan --state-root {pm_state_root} \
  | uv run {skill-root}/scripts/reorg-analyze.py
```

Bind `{shape_advisory}` from the `findings` array, by **severity**, in this order:

1. Any finding of severity `blocker` (`cycle`, `dangling-dependency`) → §2 above has already
   halted on these. Nothing further to say here.
2. Otherwise, any finding of severity `warn` (`cross-epic-coupling`,
   `unbacked-cross-epic-dependency`) →
   `↻ This plan's shape could be improved: {the measured reason, from each finding's "measured" and "suggests"}. Run /l3io-plan reorg to see a proposal.`
3. Otherwise → bind the empty string and print nothing.

**Only `warn` triggers the suggestion, and those two findings are the two things a reorg can
act on.** Moving a story into the epic its dependencies live in removes a crossing edge; nothing
else here is movable. `dependency-chain` and `isolated-story` are `info` and `question`
precisely because no move changes them — a reorg never edits `depends_on` — and they fire on
perfectly healthy plans, so advising on them would print the suggestion after every planning
round. A suggestion that always appears is one people learn to skip past.

**`sprint-imbalance` is not checked here**, and that is not an oversight: it needs
`elapsed_hours`, which `step-estimate` has not written yet. It is checked in
`step-06-plan-output.md` §5.1, where the numbers exist.

Say the measured reason, never a bare recommendation. "3 dependency edges cross E007↔E003" is
checkable by the person reading it; "this plan could be better organised" is not, and a reader
who cannot check it has to either trust it or ignore it.

If the analyzer fails or is absent, bind the empty string and carry on — a missing advisory must
never fail a plan run that otherwise succeeded.

Print `{shape_advisory}` after the graph report above, omitting the line entirely when empty.

## 7. Output status line

```
Step 05 complete — phases: {phase_count}, epics in graph: {in_scope_epic_count}, longest chain: {longest_chain_epics joined by " → "}
```
