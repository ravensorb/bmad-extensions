# BMad v7 layer — design

**Status:** design approved in conversation; spec awaiting review.
**Branch:** `feat/bmad-v7-layer`.

**Read against a moving target.** Every claim about v7 here is measured against
`bmad-code-org/BMAD-METHOD` on `main`, the v7 preview-alpha branch.

| | |
|---|---|
| Pinned at | `61e01f8` (2026-10-18) |
| Re-measured | 2026-10-20 |
| Previously pinned at | `8f0d50e` (2026-10-13) — 31 commits behind |
| v7 released? | **No.** No `v7` tag; latest release `v6.12.4` (2026-10-14) |

**v7 is four days past its own stated ETA and the preview is churning hard** — 31 commits in
five days, including an agent consolidation that renamed the single skill this design is built
on. Their README still says the preview's "skills, install path, and docs change often," and
that is an understatement. Re-measure before implementing any section; do not treat a quoted
line here as current without checking it. §12 records what moved between the two pins.

## 1. Why this is not a compatibility patch

v7 is not a changed file layout. It is a **scope change**: BMad absorbed the work-management
layer that `l3io-pm` exists to provide, and took an explicit architectural position against
ours. Two lines from their source carry the whole argument:

> `# estimate = 2 # only if the user gives one`
> — `skills/bmad-agent-po/assets/tickets-template.toml:19`

The estimate field exists but is never derived — it carries a number only when a human supplies
one. At the previous pin the comment read "only when the user gives one; **never proposed**";
the prose was trimmed, the semantics were not.

The second position is structural rather than quoted. At the previous pin `board.md` carried
"Progress lives on tickets, not in a separate sprint or status file." That sentence was cut in
the Sofia prose trim, but the architecture it described is unchanged and now shows up more
cleanly: **`sprint` appears nowhere in v7's skills except `bmod-method/retired.toml`,
`migration-1.toml` and `help/help.md`** — that is, only where v6 is being described or
migrated away from. There is no sprint level, and nothing that replaced one.

Both are openings for us rather than threats — but they mean the question is ownership of the
work-item tree, not which skill names resolve.

Treating this as a detection patch over `read_manifest()` was the first approach taken and it
was wrong. It is recorded here because the failure mode generalises: the v6→6.12 work was a
rename problem, and pattern-matching this onto that shape hides a scope change behind a
plausible-looking file diff.

### 1.1 The overlap, measured

**v7 now owns — duplicating it is the error:**

| | v7 | ours (v6) |
|---|---|---|
| Work-item tree | parent initiative → initiative → epic → leaf; `tickets.toml`; ids never reused, high-water allocator | `state/{planned,active,archived}/…` |
| States | planned / backlog / in-progress / review / done / dropped | backlog / ready-for-dev / in-progress / review / done |
| Dependencies | `after` — sibling, cross-epic (`"<epic>.<entry>"`), whole-epic (`"epic-<slug>"`) | `depends_on` |
| Readiness grouping | `tickets.py next` → `ready_to_start` / `blocked` / `ready_to_refine` | our readiness gate |
| Tracker sync | six stores: GitHub, Jira, Linear, Notion, Trello, repo | `l3io-sync`, GitHub Issues only |
| Dev loop | `bmad-build` / `bmad-build-auto` | our dev-loop phases |
| HITL control | `hitl`, `plan_checkpoint`, `done_checkpoint` | our gates |
| Requirement traceability | `covers` → requirement ids | `Spec:` pointers (ours is deeper, see §4.2) |

Their id allocator converged independently on our never-reuse rule (`tickets.py:1003`,
`next_id`), and their tracker abstraction is broader than ours. Neither is worth re-deriving.

**v7 does not have — this is the layer:**

- **The entire measurement layer.** No actuals, no tokens/cost/hours, no estimation model.
  Every `calibrat` hit in their tree is prose/PRD review calibration, not estimation. Our
  five-metric estimate/actual contract and `pm-calibration.yaml` learning loop have no
  counterpart.
- **Sprints** — ruled out by design, not omitted.
- **Phase-based parallel execution.** `next` groups by readiness only; there is no topological
  phase planner, no concurrency ceiling, no dispatch. `bmad-build-auto` is explicitly "one
  iteration of an unattended development loop" — the orchestrator is the caller, and in v7
  there isn't one.
- **Lanes** — multi-developer partitioning across clones.
- **Pre-execution gates** — epic architecture gate, six-dimension story technical-AC gate,
  spec alignment by resolving pointer, business ACs.
- **The autonomous fix loop** with severity policy and iteration cap. Zero hits for the concept.
- **Backlog lifecycle** — promote / schedule / resolve / audit.
- **Event log**, dwell time, usage reporting.

## 2. The boundary

> **v7 decides what the work is. We decide what it costs, what order it runs in, and whether
> it is allowed to start.**

The operative rule, which is testable:

> If v7's tree can express it, we do not store it. If it needs a number v7 **refuses** to
> produce, an order v7 does not compute, or a gate v7 does not run — it is ours.

This retires more of our code than it keeps. That is the correct outcome, and every section
below is an application of it.

## 3. Data placement

### 3.1 What is safe to write, measured

| Target | Machine-rewritten by v7? | Safe for our data |
|---|---|---|
| `tickets/tickets.toml` | **Yes, as of `61e01f8`** — `tickets.py move` writes `next_id` into it | no — see 3.2 |
| leaf `.md` frontmatter | **Yes** — `pull` regenerates it (`write_leaf`, `tickets.py:1199`) | **never** |
| ticket plan file (`…-plan.md`) | **Yes** — `mark` writes status/assignee/blocked there | never, except through `mark` |

**The first row reversed between pins and the spec said the opposite.** At `8f0d50e`,
`tickets.toml` was read-only to `tickets.py` and that was given as the reason extension keys
there were durable. `61e01f8` adds a `move` subcommand that writes `next_id` back into the file:
`# next_id = 7 # written by 'tickets.py move'; the folder's counter never goes below it`
(`tickets-template.toml:5`). The conclusion in §3.2 is unaffected — we had already decided not
to write that file — but the *reason* given was wrong, and would have been load-bearing had we
decided the other way. It is recorded because it is the exact shape of claim this spec warns
about in the header.

There is still no strict-key validation: `tickets.py` reads fields with `.get()`, and the
template header states the intent — "`tickets.py` ignores unknown keys"
(`tickets-template.toml:1`). So user-set `l3io_*` keys still read back. The prefix remains
required, because `unknown`, `estimate`, `risk` and `notes` are theirs.

### 3.2 We do not write `tickets.toml`

Although user-set extension keys still read back, **we write sidecars instead**, for three
reasons:

1. **Contention.** `tickets.py` still has no locking at all — no `flock`, no `fcntl`, no atomic
   rename (verified at `61e01f8`). It got away with that while status lived only in
   **per-ticket** plan files, so parallel work touched different files by construction. That is
   now less true of their own code — `move` writes the shared `tickets.toml` unguarded — and it
   would be false of ours if we wrote actuals there. Writing to the shared per-epic file would
   reintroduce precisely the contention that partitioning removed and that `pm-status.py`
   needed `flock` to survive, now against a writer that takes no lock either.
2. **Ownership.** `tickets.toml` is human- and agent-authored prose-adjacent TOML with
   meaningful comments and table order. Machine-writing it makes round-trip preservation
   (comments, key order) a new requirement — TOML's equivalent of the `ruamel` round-trip
   problem, with a less mature answer.
3. **Rot.** A file we do not write cannot be broken by their schema moving.

Extension keys remain relevant in one direction: a *user* may hand-set `estimate` or an
`l3io_*` key, and we read it as an override.

### 3.3 Where each thing lives

| Data | Written when | Home |
|---|---|---|
| sprint batch, class, lane, estimates | plan time, single-threaded | `l3io.toml` in the container's `tickets/` folder, beside `tickets.toml` |
| actuals, fix iterations, completion evidence | story closeout, concurrent | per-ticket sidecar beside the plan file |
| calibration, events, ADR register, reorg log, notices | project-wide | `{output_folder}/l3io/` |

Project-level data sits at `{output_folder}/l3io/`, **not** under an initiative. Calibration
history must outlive any single initiative; scoping it per-initiative would reset the learned
ratios every time a project starts new work, which is the one thing the model cannot afford.

`issues.yaml` **dissolves.** v7's `backlog/` already holds loose `bug-<slug>.md` /
`story-<slug>.md` leaves with no epic, and `type = "bug"` is first-class. A deferred issue
becomes a backlog ticket; `promote-issue` becomes "move this backlog entry into an epic's
`tickets.toml`", which their model does natively. We keep the *audit* (findings 1a–1l) as a
doctor mode over their tree, and drop the ledger and its key allocator.

## 4. Level mapping and execution

### 4.1 Levels

| Ours | Theirs |
|---|---|
| *(none)* | **parent initiative** — new at `61e01f8`, `[[initiative]]` tables |
| plan scope | initiative |
| epic | epic |
| **sprint** | *(not a level)* — an ordered batch declared in `l3io.toml` |
| story | leaf (`[[entry]]` → pulled `.md`) |

**Their tree grew a level between pins.** `61e01f8` adds a parent initiative over several
initiatives — "propose a parent initiative over several initiatives, not epics inside epics;
every initiative keeps initiative, epic and story" (`references/slice.md:29`). A parent's
`tickets/tickets.toml` holds `[[initiative]]` tables with the same `id` / `slug` / `covers` /
`after` shape as `[[epic]]`.

This does not disturb the mapping — it extends it upward, which is where we had nothing. A plan
scope stays an initiative; a parent initiative is a *portfolio* of plan scopes. Two consequences
worth carrying into the plan: `tickets.py next` and `status` behave differently on a parent
(they "list its child initiatives under `initiatives`", `board.md:13`), so anything reading
their tree must know which kind of container it is pointed at; and the `after` graph now exists
at three levels, not two, so §4.2's topological sort has a third possible scope.

A sprint stops being a tree level and becomes a **batch boundary**. It keeps everything a
sprint actually does — closure unit, retrospective, calibration feed-forward — without a fourth
level or a terminology collision where "epic" means two things in one tree. `depends_on` maps
to `after` at both levels.

### 4.2 Plan (`l3io-plan`)

1. Read their tree: `tickets.py status <initiative>` yields epics with `after`, entries with
   `after`, states, and the longest chain.
2. **Readiness = theirs + ours.** Theirs: `refine = true`, an unsettled `unknown`, `next`'s
   `blocked`. Ours: six-dimension technical ACs, business ACs, resolving `Spec:` pointers, an
   estimate present. We do not re-derive what `next` already computes.
3. Estimate every entry from class × calibration → `l3io.toml`.
4. **Phase graph** — topological sort over the initiative's `[[epic]] after`; a phase is
   parallel when its epics do not depend on one another. Their
   `after = [{ epic = 1, needs = "…" }]` carries a *reason* string ours never had; preserve it
   and surface it in the plan output.
5. Sprint batches within each epic.
6. Lanes on the epic.

### 4.3 Execute (`l3io-execute`)

Phases → epics (parallel to `max_parallel_subagents`) → sprint batches (sequential, so
calibration feeds forward) → per story:

```
gates → tickets.py pull → bmad-build-auto → our code review → fix loop
      → QA → capture actuals → status write
```

Implementation delegates to `bmad-build-auto`. We stop carrying an in-package dev agent and
the `bmad-create-story` / `bmad-dev-story` fallback chain entirely — v7 removed both
(`bmod-method/retired.toml`), and maintaining an implementation path competing with BMad's
official one is what that fallback chain already cost us across three releases.

### 4.4 The status-write constraint

`cmd_mark` **refuses outright** when the store is not `repo`:

> `raise StoreRefusal(f"store is {store}: change status through the store's write verb, not this script")`
> — `tickets.py:1266`

So on a Jira / Linear / GitHub-backed project we **cannot** write status with `mark`. The
status write path must be store-aware, resolved once at activation from
`bmad-agent-po/scripts/read_store.py -k tickets`. An orchestrator that assumes `mark` breaks on
the first transition of every tracker-backed project, and the failure is at run time, in the
middle of an epic.

### 4.5 What `pm-status.py` becomes

Loses `set-status`, `move-epic`, `archive-epic`, `import-node`, `reparent-story`, the entire
placement model, and every issues verb — roughly half the script. Keeps and narrows to what v7
has no answer for: `estimate-story`, `estimate-rollup`, `calibration`, `set-estimate`,
`set-actual`, `add-test-run`, the event log, `adr-reserve`, and `report`.

The HARD RULE on estimates and actuals is unchanged. `cost` stays derived-and-frozen; the
five-metric canonical order stands; `N/A` under non-Claude runtimes stands.

## 5. Review lenses — the contribution model

v7 has an extensible lens architecture, and a third party can append to it. Two targets:

| Target | Array | Keyed by | Reaches |
|---|---|---|---|
| `bmad-review` | `[[workflow.lenses]]` | `code` | general review, code and docs |
| `bmad-code-review` | `[[workflow.quick_lenses]]` / `[[workflow.thorough_lenses]]` | `id` | **the code review inside `bmad-build`'s loop** |

Both keys are in `config_utils.py`'s `_KEYED_MERGE_FIELDS = ("code", "id")`, whose merge rule is
"matching key replaces, new keys append". Their own comment invites it:

> `# Example (add an org-specific lens in team/user override TOML):`
> — `skills/bmad-review/customize.toml:98`

The consequence worth stating: **our engineering standards and threat viewpoints run inside
BMad's dev loop even on projects where nobody invokes an l3io skill.** That is a better
distribution story than a standalone review skill can have.

### 5.1 The split

Our two review skills each do two different kinds of thing, and only one is a lens.

- **Workflows stay skills.** Design guardrails at project start, ADR recording, the
  sanctum/First-Breath persona — multi-step flows with human dialogue, not review passes.
- **Viewpoints become lenses**, registered per viewpoint (~10), with `instruction` pointing
  back at our skill's own reference file. One source of truth per viewpoint, two ways to reach
  it.

`l3io-arch-review` Mode B stops being its own review engine and becomes a thin caller of
`bmad-review` with our lenses selected. One review engine per project, not two — the same
consolidation as the ticket tree, applied to review.

`applies_to` is the first filter and `when` refines it, so specialised lenses stay out of
default reviews without being opt-in-only. AI-poisoning chains behind the threat lenses with
`after`, which matches its existing cross-cut semantics exactly.

### 5.2 The lenses

From `l3io-arch-review`'s engineering standards:

| `code` | `applies_to` | Viewpoint |
|---|---|---|
| `l3io-design-integrity` | any | separation of concerns, reuse, design-by-contract |
| `l3io-testability` | any | testability as a design property, not a test count |
| `l3io-dependency-policy` | any | dependency/GA policy and the existing-library check |
| `l3io-observability` | code | unified correlated logging |
| `l3io-stack-rules` | code | per-stack rules: Python `uv`, Node LTS, .NET self-contained, Actions pinning, Docker digest-pinning/SBOM, PowerShell 7 major-scoped, shell strict-mode |

From `l3io-sec-redteam`'s threat model:

| `code` | `after` | Viewpoint |
|---|---|---|
| `l3io-threat-external` | — | external attacker |
| `l3io-threat-insider` | — | malicious insider |
| `l3io-threat-chaos` | — | chaos engineer |
| `l3io-threat-abuse` | — | abusive legitimate user |
| `l3io-threat-design` | — | design/architecture |
| `l3io-ai-poisoning` | `l3io-threat-external` | AI poisoning cross-cut over the threat findings |

Eleven. The `l3io-stack-rules` and observability lenses are `applies_to = "code"` so they never
join a document review; the threat lenses carry a `when` that keeps them out of a default
review unless the content has a security surface, per §5's filter rules.

`l3io-setup` gains the job of writing these entries into `_bmad/custom/bmad-review.toml` and
`_bmad/custom/bmad-code-review.toml`.

## 6. Skills after 4.0.0

| Skill | Fate |
|---|---|
| `l3io-plan` | Keeps its reason to exist; reads/writes their tree |
| `l3io-execute` | Orchestration, gates, fix loop, closure, metrics; implementation delegated |
| `l3io-doctor` | Loses v6 state modes; gains `migrate-v7` and a tree audit |
| `l3io-help` | Thins — `bmad` answers "what's installed"; we answer "what's the next l3io action" |
| `l3io-setup` | Gains lens registration |
| `l3io-sync` | Deprecated forwarder in 4.0.0, removed in 5.0.0 |
| `l3io-arch-review` | Splits: workflows stay, viewpoints become lenses |
| `l3io-sec-redteam` | Same split |

## 7. Migration

`/l3io-doctor migrate-v7` is a **conductor, not a reimplementation**. It owns detection,
ordering and end-state verification; it delegates BMad's half to `bmad migrate` and owns only
ours. Theirs is a conversational skill — `migration-1.toml` is a guide with questions,
precautions and approval gates, not a script — so reimplementing it would both duplicate BMad
and rot on their next release.

| BMad-side v6 artifacts | l3io state | Action |
|---|---|---|
| present | present | plan both halves, run theirs first, then ours, verify combined |
| present | absent | hand off to `bmad migrate` and stop |
| absent / already v7 | present | our half only; create the initiative if none exists |
| absent | absent | nothing to do, and say so |

Our half runs the existing engine pattern — detect → read → resolve → plan → **gate** → write
→ verify → dispose, with the gate before the write — and moves:

- `epic-{nnn}/` → `epic-<slug>/` with a generated `tickets/tickets.toml` (the file moved into a
  `tickets/` subfolder at `61e01f8`; it was beside the container file at the previous pin)
- stories → `[[entry]]` tables; `depends_on` → `after`; old keys kept in `previous_keys`
- estimates/actuals → the `l3io.toml` and per-ticket sidecars
- `issues.yaml` → `backlog/` as typed leaves
- calibration, events, ADR register → `{output_folder}/l3io/`

**Ordering is load-bearing.** Their `migration-1.toml` detects `sprint-status.yaml` and story
files named `<epic>-<story>-<slug>.md` carrying `route:`/`status:` frontmatter — both of which
an l3io project can present — and then `git mv`s whole folders into
`_bmad-output/initiative-<slug>/`. It backs up first and requires plan approval, so it is not
destructive by surprise, but two migrations competing over one tree is a mess. The doctor must
detect a v7-migratable l3io project and say so loudly, before a user types `bmad migrate` cold.

## 8. Release plan

**3.5.x — the bridge, on the v6 line.** Ships before or immediately after v7 GA:

- v7 detection in `bmad-deps.py`. Today a v7 install hits `read_manifest()` → `None` → exit 4 →
  "BLOCKED: BMad is not installed here", which is false and sends the user to reinstall
  something already present. `_bmad/_config/` does not exist in v7 — `_config` survives only as
  a reserved name in `setup.py:34` and nothing writes it.
  Detection order: readable `_bmad/_config/manifest.yaml` → v6 (existing path, unchanged);
  else `_bmad/scripts/config_utils.py` or any `bmod.toml` carrying a `[bmod]` table → v7;
  else not installed. Manifest-first means an install carrying both behaves exactly as today.
- Degraded verification on v7 rather than a halt: per-skill probes still work, manifest-derived
  fields fall to their existing `null`/`[]` unknown conventions. **New exit 6, which outranks
  exit 3** — because `bmad-sprint-planning` *is* missing on v7, so exit 3 would make 6
  unreachable, and worse, exit 3 prints `npx -y bmad-method@latest install … quick-update`,
  which on a v7 project reinstalls the 6.12 line over it.
- `resolve()` gains `.agents/` beside `.claude/`; v7 discovers skills across `.<tool>/skills`
  and names `~/.agents/` in its own lock path.
- The `bmad migrate` hazard warning in `docs/upgrading.md`.
- **Extend `tests/l3io-doctor/test-bmad-deps.py`**, which already exists. It carried 44 test
  methods before the bridge (measured at the merge base with `main`); the bridge added 27, so 71
  is the current total. They span presence, layouts, unreadable inputs, inventory shape, JSON, fallbacks, shims,
  contradictions and baseline drift. An earlier draft of this spec said the script had no
  suite; that was a search error — the suite lives under the repo-root `tests/` tree, not
  under `skills/`, which is the convention precisely so it does not ship as payload.
  `test_absent_manifest_exits_4` is the case v7 detection changes, and it must keep passing:
  a tree with no v7 evidence still exits 4.

**4.0.0 — the v7-native layer.** Everything in §2–§7.

**3.x becomes the frozen v6.12 maintenance line**, mirroring BMad's own two-line model
(`V6.12` branch + `main`).

### 8.1 Transcript resolution fallback

Independent of v7, and belongs in the bridge because it improves the v6 line too.

`resolve_session_transcript()` begins:

```python
session_id = session_id or os.environ.get(CLAUDE_SESSION_ENV, "")
if not session_id:
    return [], ""
```

Everything downstream of resolution is sound — content-verified identity, dispatch-bracket
windowing, `message.id` deduplication, the `cache_creation` double-count avoided, subagent files
resolved. But all of it hangs on `CLAUDE_CODE_SESSION_ID` being in the environment. Where it is
not — a hook context, a wrapper that scrubs env, a delegated run in another session — a Claude
run reports `N/A` while the data sits on disk the whole time.

**Fallback chain:**

1. `CLAUDE_CODE_SESSION_ID` — exact, unchanged, always preferred.
2. Candidates under `~/.claude/projects/<slug(cwd)>/`, accepted **only** when a candidate's own
   records carry a `sessionId` and span the node's dispatch bracket.
3. Ambiguous (more than one verifies) or none → `N/A`, naming what was found and why it was
   refused.

**The hard constraint is that a fallback must never pick a plausible file.** The worst failure
this contract has recorded was file choice, not arithmetic: pointed at a task `.output` artifact,
a count reported an output figure several times below reality while the cache figures matched
closely, so nothing looked wrong. A wrong transcript poisons calibration silently and looks fine
doing it; `N/A` does not. Identity is verified from record content, never from filename
plausibility, and the degraded path is `N/A` — never a guess.

**Related, and currently missed:** `subagents/agent-*.meta.json` carries `model` (alongside
`agentType`, `description`, `toolUseId`, `spawnDepth`). Cost is priced per model, and a
dispatched agent may run on a different model than its parent, so a mixed run is currently
priced at a single rate. Per-agent model attribution is available on disk and should be used.
The meta file carries no `sessionId` and no parent link, so it is an attribution input only —
never an identity proof.

**These are two implementation plans, not one.** The 3.5.x bridge is self-contained, lands on
the v6 line, and does not depend on any §2–§7 decision — it should be planned and shipped on
its own. 4.0.0 is a rewrite whose surface is still moving (§11) and should not be planned in
detail until v7 GA stops it moving. Planning them together would couple a release that can ship
this week to one that cannot.

### 8.2 What the bridge did not ship

Four things the bridge work uncovered were left undone, each deliberately.

**Task 5 — `subagent_models()` — was dropped.** §8.1 specified reporting which models a
dispatched run used, so a mixed-model window is not priced at a single rate. It is not
implemented. `skills/_shared/pm-status.py` is at exactly 10,000 lines, the hard cap set by
ADR-0001's 2026-10-03 amendment and enforced by `check:docs` check 12 (`PM_STATUS_LINE_LIMIT`).
Landing it means breaking that gate, raising the cap — which the ADR forbids as a default
("raising the number again becomes a decision made on evidence rather than a default, and it
should be argued here before it is taken") — or executing ADR-0001's Option B package-directory
refactor, which is far outside a bridge release. Cost of deferring: mixed-model runs are priced
at one rate, as they are today. No regression; an improvement not yet taken.

> **UPDATE 2026-10-23 — this blocker is gone; the paragraph above is the record of why it was
> deferred, not current state.** ADR-0001's Option B was executed: `pm-status.py` is the package
> `skills/_shared/pm_status/`, `PM_STATUS_LINE_LIMIT` **no longer exists**, and check 12 is a
> per-file 1,500-line cap over every `.py` in the package. `subagent_models()` belongs in
> `metrics/` and no longer has to buy its lines from anything. The same applies to the one-line
> `dispatch_window` timezone guard below.

**The transcript fallback does not yet reach the orchestrator.**
`skills/_shared/steps/shared/step-00-activate.md` binds `runtime=claude` only when
`$CLAUDE_CODE_SESSION_ID` is set. In the env-scrubbed case §8.1's fallback exists for, the step
files therefore bind a non-Claude runtime and record `N/A`, so `usage` is never called and the
recovered number never reaches an actual. The step file's own framing — a capability, not a
brand check — now contradicts its own step-1 test. This was not fixed in the bridge: binding
`claude` on a successful recovery would mis-bind on a Codex or other runtime that merely has a
dormant `~/.claude` tree with an overlapping window, and the contract would then record
exact-looking numbers captured from the wrong tool, which is worse than `N/A`. It needs its own
design. Cost: the fallback helps direct CLI use and any caller that already binds `claude`, and
does not help the orchestrated path.

*Ordering constraint with the in-window guard.* The recovery fallback must not be wired into
`step-00-activate.md`'s runtime binding until a candidate is required to hold a record inside
the dispatch window. A candidate that merely spans the bracket is satisfied by any session left
open and idle across it; it was reproduced end to end as a stranger's transcript accepted, every
record outside the window, and `usage` printing a zero total under a "recovered by elimination"
header. The guard now exists in `discover_session_transcript` (via `_transcript_span`), so the
constraint is met for the code as shipped. The remaining risk is the binding design above: two
sessions that both did work inside the window still refuse, correctly, but an orchestrator that
binds `claude` on a successful recovery inherits the dormant-`~/.claude` mis-binding, which the
guard does not address.

**The `.agents/` probe is asymmetric.** `bmad-deps.py`'s `resolve()` probes `.claude/` and
`.agents/`, project and home, eight paths. Seven step files
carry a runtime probe under `.claude/skills/`: `steps/shared/step-00-activate.md` (which probes
`l3io-doctor`, this package's own sibling skill rather than a BMad dependency),
`steps/execute/step-04-arch-gate.md`, `steps/sprint/step-02-story-prep.md`,
`steps/sprint/step-03-dev-loop.md`, `steps/plan/step-02-readiness-check.md`,
`steps/plan/step-03-story-elaboration.md` and `steps/closure/sprint-closure.md`. All seven probe
`.claude/` only. On a v7 tree whose skills live under
`.agents/`, `check-deps` reports a skill present while the dispatch probe finds nothing and its
phase self-skips silently. Not fixed in the bridge: widening the probes changes dispatch
behaviour across three synced skills, this bridge has no test coverage for those probes, and v7
is unsupported in this release. Cost: on v7 a green `check-deps` does not imply the phase will
run; the mismatch is invisible until a gate is observed to have skipped.

**A one-line safety fix is blocked by the cap.** `dispatch_window` parses `events.jsonl`'s `ts`
with `_parse_iso` and does not check that the result is timezone-aware, so a hand-edited or
externally written `events.jsonl` reproduces, on the dispatch-bracket side, the naive-versus-aware
`TypeError` the fallback closed on the transcript side. Every writer uses `_now_iso()`, so the
bracket is aware in practice. The symmetrical guard is one line and the file has no line left.
The cap is now blocking a one-line safety fix, which is itself evidence toward ADR-0001's stated
"revisit at 10,000". *(2026-10-23: that revisit happened and took Option B — see the update in
§8.2. The guard is no longer blocked; the fix itself is still unwritten.)*

## 9. Tooling and CI impact

v7 has no `tools/installer/`, so the whole v6 packaging apparatus stops mattering.

| Today | After 4.0.0 |
|---|---|
| `module.yaml` ×2 locations, `module-help.csv` | `bmod.toml` per skill (`[skill] bmod = …`) + a `bmod-<code>` module-record skill per module |
| `check:module`'s twelve rules (PluginResolver strategies, agent roster parity, menu codes) | retired with the installer they model |
| `check:bmb` via the `bmad-builder` npm package | `bmod-toolsmith` is in-repo in v7; re-derive or retire |
| `smoke:install` building a module view | rebuild against `bmad setup` |
| `_bmad/_config/manifest.yaml`, `skill-manifest.csv`, `bmad-help.csv` | all gone; module discovery is `bmod.toml` + `skills-lock.json`; help is per-module `help/` markdown |
| four-layer config merge | **three layers** — `_bmad/config.toml` → `custom/config.toml` → `custom/config.user.toml`. The `_bmad/config.user.toml` layer is gone (`config_utils.load_central_config`) |

Surviving unchanged, and worth knowing: `resolve_config.py --project-root --key` and
`resolve_customization.py --skill --project-root --key` keep their CLI surface; `[workflow]` /
`[agent]` root keys still apply; `memlog.py` still ships, so "never bundle a BMad core script"
still holds; and v7 mandates `uv run` everywhere, which we already do.

`check:docs`'s checks need rescoping, not deleting — the ones asserting CLI surface
against code stay valid; the ones asserting v6 paths and skill names need new targets.

## 10. ADRs required

1. **Supersedes ADR-0008** (module packaging shape) — `bmod.toml`, module-record skills, the
   end of the two-location `module.yaml` rule.
2. **v7 owns the work-item tree** — the boundary in §2 and the sidecar decision in §3.2.
3. **Sprint as a batch, not a level** — §4.1.
4. **Review viewpoints are contributed as lenses** — §5, including the "workflows stay skills"
   split.
5. Amends **ADR-0006** (dependency inventory) — `bmad-sprint-planning`,
   `bmad-check-implementation-readiness` and `bmad-create-epics-and-stories` are `removed` in
   v7; `bmad-help` → `bmad`; module code `bmm` → `method`.

Allocate every number through `pm-status.py adr-reserve`, never by hand.

## 11. Risks and open questions

- **The preview moves.** Everything here is measured at `8f0d50e`. Their README says skills,
  install path and docs change often. Re-measure each section before implementing it.
- **v7 has not shipped** as of 2026-10-16 despite being its stated ETA. The bridge release
  should not wait on GA, but 4.0.0 should not start before the surface stops moving.
- **Tracker-backed stores are the untested path.** §4.4's constraint is read from their source,
  not observed. Needs a real Jira or Linear project to verify what the store's own write verb
  is and how our orchestrator reaches it.
- **Concurrency under delegation is unproven.** We currently guarantee atomic status writes with
  `flock`. Under v7 we no longer own that path. Per-ticket partitioning should make it safe, but
  parallel epics writing sidecars plus `bmad-build-auto` writing plan files has not been
  measured.
- **Largely closed — telemetry under delegation.** An earlier draft of this section called this
  the biggest open risk. That overstated it: `pm-status.py usage` already reads the session
  transcript **from disk**, not from context, and already resolves dispatched work at
  `~/.claude/projects/<dir>/<session-id>/subagents/agent-*.jsonl`. `bmad-build-auto` renders a
  workflow for the calling agent to follow, so it runs in-session by construction and lands in
  that same tree. As long as we keep writing our own `dispatch_open`/`dispatch_close` bracket
  around the delegated work — which we control regardless of who implements — the window and
  the arithmetic are unchanged. §4.3 stands.
  The residual gap is narrow and is addressed in §8.1.

## 12. Drift log — `8f0d50e` (2026-10-13) → `61e01f8` (2026-10-18)

31 commits. Re-measured 2026-10-20. **No decision in this spec reverses**, but several facts
moved and one was outright wrong. Recorded per-pin because the next re-measure needs to know
what already shifted once.

### 12.1 Structural

| Change | Effect here |
|---|---|
| **`bmad-ticket` → `bmad-agent-po`** ("Sofia, the Product Owner"). `bmad-spec` and `bmad-correct-course` **removed** and folded into her. | Every path in §3–§7 re-pointed. `tickets.py`, `read_store.py`, `tickets-template.toml`, the six store configs, `board.md`, `slice.md`, `validate.md` all moved **intact** — the model survived, the skill was reframed as an agent. |
| **Parent initiative level added** (`[[initiative]]` tables) | §4.1 extended upward. Does not disturb the mapping; adds a portfolio scope above plan scope. |
| **`tickets.toml` moved into a `tickets/` subfolder** | §3.3 and §7 paths updated. |
| **`tickets.py move` added — it writes `tickets.toml`** | §3.1's "never machine-rewritten" was **false** as of this pin. Conclusion unaffected (we had already chosen sidecars); the stated reason was wrong. |
| Three ticket templates consolidated into one `ticket-template.md`; new `references/replan.md`, `references/spec.md` | Migration target shapes need re-reading before §7 is implemented. |
| `render_skill.py` now prints the rendered workflow rather than its path | §4.3's delegation contract — re-read `bmad-build-auto/SKILL.md` before implementing the dispatch. |

### 12.2 Verified unchanged

Re-measured at `61e01f8`, all still true:

- **The lens model — §5 is fully intact.** `[[workflow.lenses]]` in `bmad-review`,
  `[[workflow.quick_lenses]]`/`[[workflow.thorough_lenses]]` in `bmad-code-review`, and
  `_KEYED_MERGE_FIELDS = ("code", "id")` with "matching key replaces, new keys append". This is
  the most stable part of the design and the least at risk from further churn.
- **Three config layers** — `config.toml` → `custom/config.toml` → `custom/config.user.toml`.
- **`_bmad/_config` still only a reserved name**, so §8's v7 detection signal holds.
- **`StoreRefusal` on non-`repo` stores** (`tickets.py:1266`) — §4.4's constraint stands.
- **No locking anywhere** in `tickets.py` — 0 occurrences of `flock`/`fcntl`.
- **Unknown keys still ignored** — "`tickets.py` ignores unknown keys".
- **No estimation model** — every `calibrat` hit remains prose/PRD review.
- **No sprint level** — `sprint` appears only in `retired.toml`, `migration-1.toml` and
  `help/help.md`, i.e. only where v6 is described or migrated away from. Stronger evidence than
  at the previous pin, since `bmad-correct-course` (which carried sprint prose) is now gone.

### 12.3 What this says about timing

v7 is **past its own stated ETA** with no tag, while the preview absorbed three skills into a
new agent in a single week. §8's split — ship the bridge, hold 4.0.0 until the surface settles —
is not caution, it is the measured read. A 4.0.0 plan written against `8f0d50e` would already
have needed rework in six of its sections.
