# Payload Manifest Scope + `plan-graph.py` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the payload manifest cover what actually ships, and fold the plan's phase
computation into a renamed, networkx-backed graph script.

**Two independent pieces.** Phase A fixes a live defect with a user-visible consequence and
touches no skill behaviour. Phase B is the graph work. Neither depends on the other; A is
ordered first because it is the one with a bug behind it.

## Findings this plan acts on

All measured 2026-10-09/10 against the shipped tree, not inferred.

**Delivery is correct.** A real `smoke:install` puts all three `reorg-*.py` in
`.claude/skills/l3io-plan/scripts/`. BMad's `_copyResolvedSkills` copies the whole skill
directory, filtering only shim and `-sidecar` dirs. Nothing about shipping needs fixing.

**Verification is not.** `write-payload-manifest.mjs` derives its scope from
`sync-shared-scripts.mjs`'s sync groups, so it covers **only synced files**. Everything
skill-local is invisible to it: `SKILL.md`, `customize.toml`, skill-local `steps/`, and all 18
skill-local `scripts/*.py`. **123 shipped files are unhashed — the manifest covers 38% of what
ships.**

**The consequence is not theoretical.** `clean-payload.py` derives its delete set from the
manifest, with an explicit rule in its own docstring:

> `not in manifest -> not ours. Not touched, not mentioned.`

So `/l3io-doctor uninstall` silently leaves every skill-local file behind — 198 KB of Python
including `migrate-engine.py` (which deletes a project's source layout), `sync-state.py`,
`init-sanctum.py`, all three `reorg-*.py`, **and `clean-payload.py` itself**. The same script
whose docstring says the manifest *"already IS the answer to 'which files are ours'"* is a file
the manifest does not claim. The four deprecated forwarders have no manifest at all, so
uninstall leaves those four directories standing too.

**This is pre-existing**, not introduced by the reorg work: `l3io-doctor` alone accounts for 53
of the 123. The rule was correct when all payload was synced; skill-local files broke the
assumption and no check noticed, because `check:manifest` only verifies that what it *does*
cover is current.

**No deletion risk in widening it.** Verified: no skill directory is a runtime write target,
and `l3io-sec-redteam`'s sanctum lives at `_bmad/memory/<skill>/`, outside the skill tree.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Manifest scope = **every file that ships in the skill directory**, minus the exclusions below | It is the answer to "which files are ours", so it must be derived from what ships, not from how a file got there |
| D2 | Exclusions: `payload-manifest.json` (cannot hash itself), `tests/` (CLAUDE.md; no shipped skill has one today, keep the guard), `__pycache__/` | |
| D3 | Rename `reorg-analyze.py` → **`plan-graph.py`**, modes `analyze` and `phases` | The name stops being true once it computes plan phases. One graph build from `dump-plan`, two outputs |
| D4 | `plan-graph.py` takes **networkx**; `pm-status.py` takes **no** graph library | networkx costs 616 ms to import. `pm-status.py` has 92 call sites at ~0.21 s startup; `plan-graph.py` runs once per plan |
| D5 | Both phases ship in **one release** | Consistent with the reorg plan's D3 |

## Global Constraints

- `skills/_shared/` is canonical. **Edit there, then `npm run sync:scripts`.** Per-skill edits are silently overwritten.
- **Never hand-edit a `payload-manifest.json`.** Regenerate with `node scripts/write-payload-manifest.mjs`.
- **Single-consumer code lives in its skill's `scripts/`** (ADR-0001). `plan-graph.py` stays in `l3io-plan`.
- **Check 26:** no file under `skills/` assembles a state path. `plan-graph.py` takes `dump-plan` JSON on **stdin** and assembles nothing — the existing pattern.
- **Check 31:** no `/l3io-*` invocation in markdown carries a `--flag`.
- **Check 24:** a pointer in a shared file must resolve in every skill its sync group delivers to. `step-05-dependency-graph.md` is delivered to `l3io-plan` **only**, which is why it may name `{skill-root}/scripts/plan-graph.py`. Verify that is still true before relying on it.
- Conventional Commits, every commit signed off (`git commit -s`).

## Review Focus

Input classes the goal implies that no happy path exercises.

1. **A widened manifest changes the contributor workflow.** Today editing `SKILL.md` needs no regeneration; afterwards it does, and `sync:scripts` does **not** regenerate manifests. Every contributor will hit this. → Task A3 must make the failure message say what to run.
2. **`customize.toml` becomes hashed.** A user who edits it in place gets `clean-payload`'s "hash differs → REPORTED, never removed" path. That is correct, but it must not read as an error. → Task A2.
3. **The four deprecated forwarders.** They ship a `SKILL.md` and have no manifest, so uninstall leaves them. Under D1 they would gain one. `CLAUDE.md` currently says they should not have one, on the grounds that they "ship no payload at all" — which a shipped `SKILL.md` contradicts. → Task A4 decides this explicitly rather than letting the scope change decide it silently.
4. **`dump-plan`'s JSON is `indent=2`** and measured at 2.09× the raw YAML; compact separators halve it at no information loss. `plan-graph.py` consumes it on every plan run. → Task B4, optional but cheap.
5. **`nx.dag_longest_path` raises on a cyclic graph** where the current `longest_path` stays total, pinned by `test_a_cycle_does_not_hang_or_corrupt_the_critical_path`. → Task B1 must guard with `is_directed_acyclic_graph` first.
6. **Phases output must match what the snapshot consumes.** `step-06` §2 builds per-phase estimate blocks from `{phases}`, and `l3io-execute` step-03 reads phases out of the written snapshot. A shape change breaks execution, not just planning. → Task B2.

---

## Phase A — the manifest covers what ships

### - [x] Task A1: Derive manifest scope from the skill directory

- `write-payload-manifest.mjs`: replace the sync-group-derived scope with a walk of each skill directory, applying D2's exclusions.
- Keep the existing key shape — relative to the skill's own root — so a consumer who installed one skill can still verify that skill alone.
- **Tests:** a skill-local script is hashed; a synced file is still hashed; `tests/` and `__pycache__` are excluded; `payload-manifest.json` does not appear in its own file list.

### - [x] Task A2: Confirm `clean-payload.py` behaves correctly with the wider set

No code change expected — the point is to prove the widened manifest does what the docstring
already promises, and to see the three outcomes on files that previously had none.

- **Tests:** an unmodified skill-local script is removed; a modified one is **reported, never removed**; a file outside the manifest is still untouched and unmentioned.
- Check the report wording for Review Focus 2 — a modified `customize.toml` must read as a deliberate hand-off, not a failure.

### - [x] Task A3: Correct the documentation the gap made false

- `CLAUDE.md` claims each manifest carries "a SHA-256 per payload file". True after A1; record that it was not, and why, so the next reader does not re-derive it.
- Make `check:manifest`'s failure message name `node scripts/write-payload-manifest.mjs` (Review Focus 1).

### - [x] Task A4: Decide the forwarders explicitly

They ship a `SKILL.md` and uninstall currently leaves four directories behind. Either they gain
a manifest (and uninstall removes them), or they are excluded by name with a stated reason.
**Do not let the scope change answer this silently** — record the decision in `CLAUDE.md` beside
the claim it corrects.

---

## Phase B — `plan-graph.py`

### - [x] Task B1: Rename, add networkx, add the `phases` mode

- `reorg-analyze.py` → `plan-graph.py`. Modes: `analyze` (today's findings) and `phases`.
- PEP-723 header gains `networkx>=3.6` — the floor that still supports Python 3.11, so **no interpreter change is needed**. (uv provisions interpreters on demand if we ever do want one; verified.)
- Replace `find_cycles` (38 lines) and `longest_path` (42 lines) with `nx.simple_cycles` and `nx.dag_longest_path`, guarding the cyclic case per Review Focus 5.
- `phases` mode emits the `{phases}` structure via `nx.topological_generations`.
- **Tests:** rename the suite to `test-plan-graph.py`; every existing analyze assertion must still pass unchanged; `phases` matches a hand-computed expectation on a known graph; a cyclic graph does not crash the chain finding.

### - [x] Task B2: `step-05` calls the script instead of describing the algorithm

- §3 currently tells the agent to execute Kahn's algorithm in prose — ~2,949 B of step-05 is hand-executed algorithm, and this is the computation that decides what runs in parallel.
- Replace with a `plan-graph.py phases` call. Keep the worked example: a reader still needs to know what the output means.
- **The emitted shape must be byte-compatible with what `step-06` §2 and `l3io-execute` step-03 consume** (Review Focus 6). Assert this, do not assume it.

### - [x] Task B3: Update every caller and regenerate

- `step-05` (structural advisory), `step-06` §5.1 (balance advisory), `steps/reorg/step-reorg.md`.
- `npm run sync:scripts` then `node scripts/write-payload-manifest.mjs` — and after A1 the manifest now covers the renamed script, so a stale name fails the gate rather than shipping.

### - [x] Task B4: Compact `dump-plan` output

`json.dumps(..., indent=2)` measures 16,895 B where compact separators give 8,349 B on the same
10-epic/40-story tree — 51% of the JSON, no information lost. Every plan run pipes this.
Judgement call: compact JSON is harder to read when debugging by hand.

---

## Validation Strategy

Build the tree and run the real thing; do not assert from reading.

| Probe | Asserts |
|---|---|
| `smoke:install` into a kept workdir, then `find` for each skill-local file | the manifest's new scope matches what actually lands |
| `clean-payload.py --dry-run` against a real install | unmodified removed, modified reported, foreign untouched |
| `plan-graph.py phases` vs the current prose on a known graph | the script and the algorithm it replaces agree |
| existing `test-reorg-analyze.py` assertions, renamed | the rename and networkx swap changed no behaviour |

**Mutation testing required** for A1 (drop an exclusion → a test must fail) and B1 (remove the
cyclic guard → the cycle test must fail).

**Gates:** all seven, `npm run test:python`, and `smoke:install` before release.

## Risks

- **A1 widens what uninstall deletes.** That is the fix, but it is the one change here that removes files from a user's project. Task A2 exists to prove the three outcomes before it ships, and `clean-payload`'s existing bias — report rather than delete — is what makes it safe.
- **B2 moves a computation out of the agent's judgement into code.** That is the goal, and it also means a bug in `plan-graph.py phases` is silent where a prose mistake was at least visible in the transcript. The byte-compatibility assertion is the guard.
- **Two graph libraries do not appear.** `pm-status.py` takes none (D4). Record that in the ADR if one is written, so nobody later "consolidates" and puts a 616 ms import in front of 92 call sites.
