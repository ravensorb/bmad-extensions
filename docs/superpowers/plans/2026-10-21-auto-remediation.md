# Auto-Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When an orchestrator halt has a remedy we can perform, perform it, report it, and continue the run — instead of telling the user to go run a command and start over.

**Architecture:** A shared reference carries the rule and a two-table classification of every `BLOCKED:` site (auto-remediable vs never). Each halt site keeps its own prose and gains a declared remedy. A `check:docs` rule asserts the reference and the step files agree, which is what makes prose changes testable. Nine sites become auto-remediable; fourteen stay halts.

**Tech Stack:** Markdown step files, `scripts/check-docs.mjs` (Node), `scripts/sync-shared-scripts.mjs`.

**Spec:** `docs/superpowers/specs/2026-10-21-auto-remediation-design.md`

## Global Constraints

- **Shared sources only.** Edit `skills/_shared/**`; never a per-skill copy. Then `npm run sync:scripts`, then `node scripts/write-payload-manifest.mjs`.
- **A new shared reference lives FLAT** at `skills/_shared/<name>.md` and is delivered to `references/<name>.md` by a sync group in `scripts/sync-shared-scripts.mjs`. **The spec says `skills/_shared/references/` — that is wrong and is corrected in Task 6.**
- **Destinations, verified on disk:** `steps/shared/step-00-activate.md` → l3io-execute, l3io-plan, l3io-sync. `steps/plan/step-02-readiness-check.md` → l3io-plan. `steps/execute/step-03-load-plan.md` → l3io-execute.
- **`pm-status.py` is at exactly 10,000 lines (ADR-0001 cap, `check:docs` check 12). Nothing in this plan may add a line to it.** If a task seems to need one, stop and report.
- **Attempt record is in-run memory, not a file.** All nine sites are inline in the orchestrator. No new state file.
- **Three refusals are absolute:** another session's epic lock, credentials, and accepting plan risk (`readiness: red` → amber).
- Conventional Commits, DCO sign-off (`git commit -s`), trailer `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Comments and prose explain what and why; never narrate fix history.
- No new npm dependencies (`check:docs` check 28 enforces this).
- **Derive the site list from the step files, not from this plan's tables.** The spec's own enumeration was wrong once.

## Review Focus

Five conditions the spec implies that no task's happy path exercises. Each has its test pinned to the task that owns it.

1. **The remedy itself fails** — `bootstrap-state` exits non-zero. The run must halt reporting *both* the original condition and the remedy's failure, never continue as if remediated. → Task 1, Step 7.
2. **`/l3io-plan` re-entry fires first-run behaviour** — three defaults re-run `/l3io-plan` mid-run. If that is indistinguishable from a user invocation, the setup-pointer notice (`config-resolution.md` §5) fires again mid-run. → Task 3, Step 6.
3. **Two halts fire in one run** — e.g. legacy layout *and* gitignored state root. Each needs its own attempt record; one remedy must not consume the other's budget. → Task 4, Step 7.
4. **The legacy tree is empty** — an empty set is vacuously a subset, so a naive subset test auto-proceeds and backs up nothing. That may be right, but it must be decided, not fallen into. → Task 5, Step 5.
5. **The working tree is read-only** — a remediation that cannot write (permissions, a read-only checkout) must fail loudly as in (1), not half-apply. → Task 4, Step 8.

---

## Task 1: The shared reference, and the first vertical slice

**Files:**
- Create: `skills/_shared/auto-remediation.md`
- Modify: `scripts/sync-shared-scripts.mjs` — add a sync group
- Modify: `skills/_shared/steps/plan/step-02-readiness-check.md:29-49`
- Generated: `skills/{l3io-execute,l3io-plan,l3io-sync}/references/auto-remediation.md`, `skills/l3io-plan/steps/plan/step-02-readiness-check.md`, three `payload-manifest.json`

**Interfaces:**
- Produces: `references/auto-remediation.md` containing a **Remediable** table (one row per auto site: *site id · file · trigger · remedy command · what it changes*) and a **Never remediable** list (the other fourteen, each with its reason). Later tasks add rows to the first table.
- Produces: the site-id convention `<file-stem>:<BLOCKED line text, first 6 words>` used by the Task 2 checker to match a reference row to a step-file block.

- [ ] **Step 1: Write the reference's rule and contract sections**

Create `skills/_shared/auto-remediation.md`. Open with the rule verbatim from the spec §2, then:

```markdown
## The attempt bound

**One attempt per distinct issue per run.** Record the remedy *before* running it. If the same
halt recurs after its own remedy has run, it becomes a hard halt naming what was tried:

> BLOCKED: I ran `<remedy>` to resolve `<condition>` and the condition persists. `<detail>`.
> This needs a decision.

There is no second attempt under any condition. Three of the remedies below re-run
`/l3io-plan`, which carries its own halts — unbounded, a RED plan re-plans into RED forever.

The record is **in-run memory**, not a file: the bound is per run, a run is one orchestrator
invocation, and every site below is inline in that invocation rather than inside a dispatched
subagent. **If a site ever moves into a dispatched subagent this is void** — the package's
context boundary passes state through disk, never through in-memory hand-off — and the record
must become a file.

## Reporting — act, then confirm

Per ADR-0004 an agent acts and confirms after the edit lands. Every remediation prints one
line before and one after:

⚙  <condition, with counts> — running <remedy>
✓  <what the remedy did>. Continuing <what resumes>.

A remediation that cannot report what it changed does not qualify. Silence is never correct:
the user should finish the run knowing what their project needed, not with it hidden.

## When a remedy fails

If the remedy exits non-zero, **halt** — reporting both the original condition and the
remedy's failure. Never continue as though it succeeded, and never retry.
```

- [ ] **Step 2: Write the two classification tables**

Append to the same file. The **Remediable** table starts with one row (later tasks add theirs):

```markdown
## Remediable

| Site | Trigger | Remedy | Changes |
|---|---|---|---|
| `step-02-readiness-check: artifact-only stories detected` | story `.md` files exist with no state YAML | `/l3io-doctor bootstrap-state` | creates state nodes from artifacts; writes no artifact |

## Never remediable

These halt. The first three are hard rules, not defaults.

| Site | Why |
|---|---|
| `step-02-scope-resolve: {epic_key} is owned by another session` | Breaking another session's lock is data loss across a boundary `flock` cannot see — lanes exist so two developers work in two clones |
| `step-05-epic-loop: {epic_key} lock held by another session` | Same |
| `step-02-detect-platform: authentication unavailable` | Never touch credentials |
| `step-03-load-plan: plan readiness is RED` (route 2 only) | Downgrading readiness to amber is a risk acceptance. Route 1 (re-plan) IS remediable and is listed above; accepting the risk is the user's alone |
| `sprint-closure: sprint {n} — {N} story/ies blocked pending external` | External dependency; no remedy exists |
| `step-02-readiness-check: readiness gate — red` | Aggregate of per-story findings; no single remedy |
| `step-02-scope-resolve: unrecognized scope argument` | User input error |
| `step-02-scope-resolve: {epic_key} not found` | User input error |
| `step-03-dev-loop: story depends on {dep_key}` | Ordering fact, not a defect |
| `step-04-arch-gate: {N} blocking findings unresolved` | Requires design decisions |
| `step-02-detect-platform: platform detection failed` | Environment, not state |
| `step-02-story-prep: story still missing required ACs after elaboration` | Content authoring |
| `step-00-activate: l3io-setup/scripts/pm-status.py is missing` | The install itself is broken |
| `step-00-activate: schema verify failed for {epic_key}` | Unknown state corruption; guessing could worsen it |
| `step-05-dependency-graph: dependency graph has errors` | Requires `depends_on` decisions |
```

Note the `step-03-load-plan: plan readiness is RED` row appears in **both** tables — route 1 remediable, route 2 never. Task 3 adds its Remediable row; keep the Never row's qualifier exact.

- [ ] **Step 3: Register the sync group**

In `scripts/sync-shared-scripts.mjs`, beside the existing `acDimensionFiles` / `configResolutionFiles` declarations, add:

```js
const autoRemediationFiles = [
  { src: path.join(sharedDir, "auto-remediation.md"), rel: "references/auto-remediation.md" },
];
```

and add it to the `syncGroups` entry covering `l3io-execute`, `l3io-plan` and `l3io-sync` — the three skills that carry `steps/shared/step-00-activate.md`, whose halts this reference governs. Follow the shape of the group that already delivers `metrics-contract.md` to those same three.

- [ ] **Step 4: Run to verify it fails**

Run: `npm run check:scripts 2>&1 | tail -5`
Expected: FAIL — the new source has no delivered copies yet.

- [ ] **Step 5: Sync and regenerate**

```bash
npm run sync:scripts && npm run check:scripts 2>&1 | tail -3
node scripts/write-payload-manifest.mjs && npm run check:manifest 2>&1 | tail -3
```
Expected: both clean; `references/auto-remediation.md` now exists in all three skills.

- [ ] **Step 6: Convert the artifact-only halt**

In `skills/_shared/steps/plan/step-02-readiness-check.md`, replace lines 32-49 (the block from `If **any artifact-only stories are found**, halt immediately` through the `BLOCKED:` line) with:

```markdown
If **any artifact-only stories are found**, remediate per `references/auto-remediation.md` —
their state nodes are reconstructible from the artifacts, and this is the one remedy:

```
⚙  {count} story artifact(s) have no state node — running /l3io-doctor bootstrap-state
```

Record the attempt, then run `/l3io-doctor bootstrap-state`. On success:

```
✓  bootstrap-state created {n} state node(s). Continuing readiness check.
```

Re-run the artifact-only scan once. If artifact-only stories remain, halt — the remedy has
been tried:

```
BLOCKED: I ran /l3io-doctor bootstrap-state and {count} story artifact(s) still have no
state node:
{list each path}
These may be malformed, or outside the epic/sprint layout bootstrap-state reads.
```

If `bootstrap-state` itself exits non-zero, halt reporting both:

```
BLOCKED: {count} story artifact(s) have no state node, and /l3io-doctor bootstrap-state
failed: {stderr}. The stories remain invisible to planning until this is resolved.
```

If no artifact-only stories are found (or no `.md` files exist at all), continue to §1.
```

- [ ] **Step 7: Verify the failure paths are specified (Review Focus 1)**

Re-read what you wrote. Three outcomes must each have explicit prose: remedy succeeds and clears the condition; remedy succeeds and the condition persists; remedy fails. Confirm none of the three falls through to "continue". If any does, fix it now — a remediation that continues after a failed remedy produces a plan over state that does not exist.

- [ ] **Step 8: Sync, regenerate, verify, commit**

```bash
npm run sync:scripts && node scripts/write-payload-manifest.mjs
npm run check:docs 2>&1 | tail -3
npm run check:scripts 2>&1 | tail -3
npm run check:manifest 2>&1 | tail -3
git add skills/_shared/auto-remediation.md skills/_shared/steps/plan/step-02-readiness-check.md scripts/sync-shared-scripts.mjs skills/*/references/auto-remediation.md skills/l3io-plan/steps/plan/step-02-readiness-check.md skills/*/payload-manifest.json
git commit -s -m "feat(l3io-pm): remediate artifact-only stories instead of halting

A story .md with no state YAML is invisible to planning, and the halt
already named the single remedy and told the user to go run it. It now
runs it, reports what it created, and continues the readiness check.

Adds references/auto-remediation.md carrying the rule, the attempt bound
and the two-table classification of every BLOCKED site. The bound is
load-bearing: later remedies re-run /l3io-plan, which has halts of its
own.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: The gate — reference and step files must agree

**Files:**
- Modify: `scripts/check-docs.mjs` — add a numbered check
- Test: `scripts/tests/check-docs.test.mjs`

**Interfaces:**
- Consumes: `skills/_shared/auto-remediation.md`'s two tables (Task 1).
- Produces: `check:docs` check N (take the next free number from the file's header) failing when a `BLOCKED:` site in a shared step file appears in neither table, or when a Remediable row names a remedy command the step file's block does not contain.

- [ ] **Step 1: Write the failing test**

In `scripts/tests/check-docs.test.mjs`, following the file's existing fixture pattern (it copies the repo and symlinks `node_modules`):

```js
test("autoRemediation: a BLOCKED site in neither table fails", async (t) => {
  const tree = await fixture(t);
  await appendFile(join(tree, "skills/_shared/steps/plan/step-02-readiness-check.md"),
    "\nBLOCKED: a brand new unclassified condition.\n");
  const r = runCheck(tree);
  assert.match(r.output, /unclassified condition/);
  assert.notEqual(r.code, 0);
});

test("autoRemediation: a Remediable row whose step file omits the remedy fails", async (t) => {
  const tree = await fixture(t);
  const p = join(tree, "skills/_shared/steps/plan/step-02-readiness-check.md");
  await writeFile(p, (await readFile(p, "utf8")).replace("/l3io-doctor bootstrap-state", "echo nope"));
  const r = runCheck(tree);
  assert.match(r.output, /bootstrap-state/);
  assert.notEqual(r.code, 0);
});

test("autoRemediation: the shipped tree passes", async (t) => {
  assert.equal(runCheck(await fixture(t)).code, 0);
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `node --test scripts/tests/check-docs.test.mjs 2>&1 | tail -12`
Expected: the first two fail (the check does not exist, so nothing errors); the third passes vacuously.

- [ ] **Step 3: Implement the check**

The highest existing check is **35**, so this is **check 36**. Add a numbered header entry in the file's existing comment style, then the pure function and its reporter. Scope is **derived** — the step files and the reference, never a list:

```js
// ---------------------------------------------------------------------------
// 36. Every `BLOCKED:` site is classified, and every declared remedy is present.
//
// Step-file prose has no unit test, so the reference and the step files agreeing IS the
// testable artifact. Two failure modes: a halt nobody classified (so nobody decided whether
// it should self-heal), and a Remediable row whose remedy the step file does not actually
// run (a declared remedy that was never implemented reads as a capability and is not one).
// Scope is derived from both sides, so a new halt is covered with no edit here.
const REMEDIATION_REF = "skills/_shared/auto-remediation.md";

// A site id: the BLOCKED text's first six words, placeholders collapsed, lowercased.
// Placeholders collapse because `{epic_key}` in the step file is `{epic_key}` in the table
// but `E001` at runtime -- matching on the literal would be matching on an example.
function siteId(text) {
  return text.replace(/\{[^}]*\}/g, "{}").replace(/\s+/g, " ").trim()
             .split(" ").slice(0, 6).join(" ").toLowerCase();
}

function remediationCoverage() {
  const ref = readFileSync(path.join(repoRoot, REMEDIATION_REF), "utf8");
  const rows = (section) => {
    const body = ref.split(`## ${section}`)[1]?.split(/^## /m)[0] ?? "";
    return body.split("\n").filter((l) => l.startsWith("|") && !/^\|\s*-+/.test(l))
      .map((l) => l.split("|").slice(1, -1).map((c) => c.trim()))
      .filter((c) => c.length >= 2 && !/^site$/i.test(c[0]))
      .map((c) => ({ id: siteId(c[0].replace(/`/g, "").split(":").slice(1).join(":")), cells: c }));
  };
  const remediable = rows("Remediable");
  const never = rows("Never remediable");
  const classified = new Map([...never, ...remediable].map((r) => [r.id, r]));

  const violations = [];
  let examined = 0;
  for (const file of stepFiles()) {                 // every skills/_shared/steps/**/*.md
    const lines = readFileSync(file, "utf8").split("\n");
    lines.forEach((line, i) => {
      if (!line.startsWith("BLOCKED:")) return;
      examined++;
      const id = siteId(line.slice("BLOCKED:".length));
      if (!classified.has(id)) {
        violations.push(`${rel(file)}:${i + 1} halt is in neither table of ${REMEDIATION_REF}: "${line.slice(0, 70)}"`);
        return;
      }
      const row = remediable.find((r) => r.id === id);
      if (!row) return;                              // never-remediable: nothing more to check
      // The remedy must appear in the surrounding block, not merely be declared.
      const window = lines.slice(Math.max(0, i - 40), i + 40).join("\n");
      const remedy = row.cells[2].replace(/`/g, "").replace(/\*\*.*?\*\*/g, "").trim();
      if (remedy && !window.includes(remedy.split(" ")[0])) {
        violations.push(`${rel(file)}:${i + 1} declares remedy "${remedy}" in ${REMEDIATION_REF} but the step file never runs it`);
      }
    });
  }
  return { violations, examined, classified: classified.size };
}

function checkRemediationCoverage() {
  const { violations, examined, classified } = remediationCoverage();
  for (const v of violations) failures.push(`[check 36] ${v}`);
  if (verbose) {
    console.log(`  remediation-coverage: ${examined} halt(s), ${classified} classified, ` +
                `${violations.length} violation(s)`);
  }
}
```

Register it beside the others at the bottom of the file:

```js
checkRemediationCoverage();
```

Reuse the file's existing helpers for `repoRoot`, `rel()` and `failures`/`verbose` rather than redeclaring them, and reuse or add a `stepFiles()` walker matching how check 24 enumerates shared files. If the surrounding code uses a different idiom for any of these, follow it — this block's logic is the contract, not its spelling.

- [ ] **Step 4: Run to verify they pass**

Run: `node --test scripts/tests/check-docs.test.mjs 2>&1 | tail -12`
Expected: all three pass.

- [ ] **Step 5: Confirm it runs in the gate**

Run: `npm run check:docs 2>&1 | tail -3`
Expected: clean, and the check's name appears in the run's check list.

- [ ] **Step 6: Commit**

```bash
git add scripts/check-docs.mjs scripts/tests/check-docs.test.mjs
git commit -s -m "feat(infra): gate that every BLOCKED site is classified and its remedy named

Step-file prose has no unit test, so the reference and the step files
agreeing is the testable artifact. The check fails when a BLOCKED site
appears in neither of auto-remediation.md's tables, and when a Remediable
row names a remedy its step file does not contain -- the drift that would
leave a declared remedy unimplemented.

Scope is derived from the step files and the reference, so a new halt is
covered with no edit here.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: The four plan-pointer halts

**Files:**
- Modify: `skills/_shared/steps/execute/step-03-load-plan.md:33, 46, 60, 98`
- Modify: `skills/_shared/auto-remediation.md` — four Remediable rows
- Generated: `skills/l3io-execute/steps/execute/step-03-load-plan.md`, references, manifests

**Interfaces:**
- Consumes: the reference's tables and site-id convention (Task 1); the Task 2 check now gates this work.
- Produces: four Remediable rows, three of whose remedy is `/l3io-plan`.

- [ ] **Step 1: Add the four Remediable rows**

| Site | Trigger | Remedy | Changes |
|---|---|---|---|
| `step-03-load-plan: plan-output-meta.yaml absent` | no pointer, no snapshots | `/l3io-plan` | writes the pointer and a fresh snapshot |
| `step-03-load-plan: plan-output-meta.yaml absent, but snapshots exist` | pointer missing, snapshots present | `/l3io-plan` | rebuilds from current state; **existing snapshots are not deleted or read** |
| `step-03-load-plan: plan readiness is RED` | pointer readiness red | `/l3io-plan` (**route 1 only**) | resolves gaps and rebuilds; **never sets amber** |
| `step-03-load-plan: plan-output-meta.yaml points at {current_plan}` | pointer target missing | `/l3io-plan` | rebuilds plan and pointer; **does not substitute another snapshot** |

- [ ] **Step 2: Convert the two simple pointer halts (lines 33, 98)**

Both become: report, record the attempt, run `/l3io-plan`, re-read the pointer once, continue. On recurrence or failure, halt per the reference's two failure forms. Preserve the existing prohibition verbatim at line 98's site — *"Do not substitute another snapshot — that would execute a plan the pointer does not vouch for."* It remains true: we rebuild rather than substitute.

- [ ] **Step 3: Convert the snapshots-exist halt (line 46)**

Same shape. The existing text already calls re-running "(recommended)"; the remediation performs that recommendation. **Keep the warning that the newest snapshot may be incomplete** — it is why we rebuild instead of adopting it.

- [ ] **Step 4: Convert the RED-readiness halt (line 60) — route 1 only**

Remediate route 1. **Route 2 must survive verbatim as a halt**, including its wording that the user may accept the risk and ask for amber. After the re-plan, if readiness is still red:

```
BLOCKED: I ran /l3io-plan to resolve the readiness gaps and readiness is still RED for
{current_plan_file}. The gaps are: {list}. Two things unblock it:
  1. Resolve the gaps above and re-run /l3io-execute.
  2. Accept the risk: say so, and I will set readiness to amber in
     {planning_artifacts}/plan-output-meta.yaml, then you re-run /l3io-execute.
```

Keep **"Never tell the user to edit that file themselves"** exactly where it is.

- [ ] **Step 5: Verify the absolute refusal held**

Run: `grep -n 'set readiness to amber' skills/_shared/steps/execute/step-03-load-plan.md`
Expected: it appears only inside a `BLOCKED:` block, never inside a `⚙`/`✓` remediation block. If a remediation ever sets amber, this task has violated the spec's hardest rule — revert that hunk.

- [ ] **Step 6: Specify re-entry (Review Focus 2)**

`/l3io-plan` re-entered mid-run must not re-fire first-run behaviour. Read `skills/_shared/config-resolution.md` §5 and the notices contract, determine whether the setup-pointer notice would fire again, and write the answer into the reference under a short **Re-entry** heading. If it would fire, state how the remediation suppresses it (the notices ledger is keyed on `--key` alone and is one-time-ever, so a notice already shown stays shown — confirm this rather than assume it). If it would not, say so and why, so the next reader does not re-derive it.

- [ ] **Step 7: Sync, verify, commit**

```bash
npm run sync:scripts && node scripts/write-payload-manifest.mjs
npm run check:docs 2>&1 | tail -3
git add skills/_shared/auto-remediation.md skills/_shared/steps/execute/step-03-load-plan.md skills/l3io-execute/ skills/*/references/auto-remediation.md skills/*/payload-manifest.json
git commit -s -m "feat(l3io-pm): rebuild a missing or stale plan pointer instead of halting

Four halts in step-03-load-plan named re-running /l3io-plan as their
remedy -- one of them marked recommended -- and stopped so the user could
type it. They now run it and continue.

Route 2 of the RED-readiness halt is deliberately untouched: downgrading
readiness to amber is a risk acceptance and stays the user's alone.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: Three activation halts

**Files:**
- Modify: `skills/_shared/steps/shared/step-00-activate.md:289, 307, 329`
- Modify: `skills/_shared/auto-remediation.md` — three Remediable rows
- Generated: three skills' copies, manifests

- [ ] **Step 1: Add the three Remediable rows**

| Site | Trigger | Remedy | Changes |
|---|---|---|---|
| `step-00-activate: legacy state layout — migrate required` | only a legacy layout present | `/l3io-doctor migrate-state` | migrates to sharded; **preserves the original as `.legacy`** |
| `step-00-activate: state found at` | state exists outside `implementation_artifacts` | repoint `implementation_artifacts` in `_bmad/custom/config.toml` | records the previous value in the same write |
| `step-00-activate: {pm_state_root} is gitignored` | `git check-ignore` reports IGNORED | append the two negation lines | edits the **ignoring** file, located with `git check-ignore -v` |

- [ ] **Step 2: Convert the legacy-layout halt (line 289)**

Report, record, run `/l3io-doctor migrate-state`, re-run the three-layout probe once, continue. State in the prose that the original is preserved as `.legacy` — that is what makes this reversible and therefore remediable.

- [ ] **Step 3: Convert the repoint halt (line 307)**

The found tree is the real state; the config moved. Repoint `implementation_artifacts` in `{project-root}/_bmad/custom/config.toml` — our own layer — writing the previous value alongside as a comment so the change is revertible by inspection. Report both values:

```
⚙  state found at {found} but implementation_artifacts resolves to {configured} — repointing
✓  implementation_artifacts = {found} (was {configured}). Continuing activation.
```

Keep the existing refusal's intent: we are not starting a blank project over existing state. We are adopting the state that exists.

- [ ] **Step 4: Convert the gitignored halt (line 329)**

**Locate the ignoring rule first** — it may be in the project `.gitignore`, a parent directory's, or `.git/info/exclude`:

```bash
git -C {project-root} check-ignore -v {pm_state_root}
```

Append the two negation lines to the file that output names. If it names `.git/info/exclude`, that is a local-only file the user chose — report and halt rather than editing it, because a negation there would not reach anyone else and would mask the user's intent.

- [ ] **Step 5: Sync and verify**

```bash
npm run sync:scripts && node scripts/write-payload-manifest.mjs && npm run check:docs 2>&1 | tail -3
```

- [ ] **Step 6: Verify the untouched fourth halt**

Run: `grep -n 'BLOCKED: multiple state layouts' skills/_shared/steps/shared/step-00-activate.md`
Expected: still present and unchanged. Task 5 owns it. If this task altered it, revert that hunk.

- [ ] **Step 7: Specify multi-halt budgeting (Review Focus 3)**

A tree can be both legacy-layout *and* gitignored. Write into the reference, under the attempt bound, that the budget is **per site id**, not per run: remediating the layout must not consume the gitignore budget. Add one sentence and one worked example naming those two sites.

- [ ] **Step 8: Specify the read-only case (Review Focus 5)**

Each of these three writes to disk. Write into the reference's **When a remedy fails** section that a write failure — permissions, a read-only checkout — is the failure path, reporting both the original condition and the write error, never a partial apply. Name `config.toml` and `.gitignore` as the two writes that can hit it.

- [ ] **Step 9: Commit**

```bash
git add skills/_shared/auto-remediation.md skills/_shared/steps/shared/step-00-activate.md skills/l3io-execute/ skills/l3io-plan/ skills/l3io-sync/ skills/*/payload-manifest.json
git commit -s -m "feat(l3io-pm): migrate, repoint and un-ignore state during activation

Three activation halts each named one remedy and stopped. They now run
it. migrate-state preserves the original as .legacy, the repoint records
the previous value, and the gitignore fix edits the file git check-ignore
names rather than assuming the project .gitignore.

A rule in .git/info/exclude is still a halt: a negation there reaches
nobody else and would mask a choice the user made locally.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: Multiple state layouts — evidenced, never guessed

**Files:**
- Modify: `skills/_shared/steps/shared/step-00-activate.md:265-277`
- Modify: `skills/_shared/auto-remediation.md` — one Remediable row with its condition

**Interfaces:**
- Consumes: the three-layout probe already in the step file (`SHARDED`/`LEGACY_EPIC`/`LEGACY_FLAT`).
- Produces: a comparison that auto-resolves only the subset case.

- [ ] **Step 1: Add the conditional Remediable row**

| Site | Trigger | Remedy | Changes |
|---|---|---|---|
| `step-00-activate: multiple state layouts detected` | more than one layout present **and the legacy tree's node keys are a strict subset of the sharded tree's** | back up the legacy tree, proceed on sharded | moves the legacy tree aside; **sharded is not modified** |

Mark the condition explicitly in the row — this is the only conditional entry in the table, and a reader must not take it as unconditional.

- [ ] **Step 2: Write the comparison**

Enumerate node keys from each layout and compare as sets. Epic keys are sufficient — a legacy tree holding an epic the sharded tree lacks is the losable case, and sprint/story divergence within a shared epic key is a different problem this remedy does not claim to solve. Say that in the prose rather than leaving it implied.

- [ ] **Step 3: Remediate the subset case only**

```
⚙  multiple state layouts detected; the legacy tree holds {n} epic(s), all present in the
   sharded tree — an interrupted migration that copied everything. Backing it up.
✓  moved {legacy_path} to {legacy_path}.superseded. Continuing on the sharded layout.
```

- [ ] **Step 4: Halt with the diff otherwise**

```
BLOCKED: multiple state layouts detected and they diverge — neither is a superset.
  only in legacy ({legacy_path}): {keys}
  only in sharded ({sharded_path}): {keys}
Guessing which is authoritative would fork the project's state. Inspect both and remove
the stale one, then re-run /l3io-doctor migrate-state.
```

This is strictly better than today's message, which says "inspect both locations" without naming what differs.

- [ ] **Step 5: Decide the empty-legacy case (Review Focus 4)**

An empty legacy tree is vacuously a subset, so Step 3 would back up an empty directory and proceed. **Decide this explicitly and write the decision into the prose**: either that is correct (an empty leftover directory is exactly the interrupted-migration case, and moving it aside is right), or it needs its own branch. Do not leave it to fall out of set semantics — a reader must be able to see it was considered.

- [ ] **Step 6: Verify the hard case still halts**

Construct the divergent case by hand in a scratch directory — a legacy tree with an epic key absent from the sharded tree — and confirm the prose directs a halt, not a backup. Record what you constructed in your report. This is the case the spec says can lose work.

- [ ] **Step 7: Sync, verify, commit**

```bash
npm run sync:scripts && node scripts/write-payload-manifest.mjs && npm run check:docs 2>&1 | tail -3
git add skills/_shared/ skills/l3io-execute/ skills/l3io-plan/ skills/l3io-sync/ skills/*/payload-manifest.json
git commit -s -m "feat(l3io-pm): resolve an interrupted migration when the evidence is unambiguous

Two state layouts means a migration died partway. Where the legacy tree's
epic keys are a strict subset of the sharded tree's, it copied everything
and died before cleanup -- that is unambiguous, so back it up and
continue.

Where the trees diverge, still halt, but print which keys differ. The
previous message said 'inspect both locations' and left the user to find
the difference.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 6: ADR, and the corrections this plan found

**Files:**
- Create: `docs/adr/{reserved}-auto-remediation-of-orchestrator-halts.md`
- Modify: `docs/superpowers/specs/2026-10-21-auto-remediation-design.md` — §6.2 path
- Modify: `CLAUDE.md`

- [ ] **Step 1: Reserve the ADR number**

```bash
uv run {pm_status} adr-reserve --epic INFRA --slug auto-remediation
```

**Never hand-pick a number.** `adr-reserve` allocates under a flock from max(register, files on disk). If it refuses (not in a git work tree, or no `--adr-dir`), pass `--adr-dir docs/adr` rather than choosing one yourself.

- [ ] **Step 2: Write the ADR**

Record: the rule; the nine remediable sites and the fourteen that are not; the three absolute refusals and why each is absolute; the attempt bound and why it is load-bearing; and that the attempt record is in-run memory with the condition that voids it.

- [ ] **Step 3: Correct the spec's reference path**

§6.2 says `skills/_shared/references/auto-remediation.md`. Shared references live **flat** at `skills/_shared/<name>.md` and are delivered to `references/<name>.md`. Correct it and note the actual location.

- [ ] **Step 4: Record the capability in CLAUDE.md**

Add a short paragraph to the Key Execution Contracts section: halts with a single determinable remedy now self-heal, one attempt per site per run, three refusals are absolute, and `references/auto-remediation.md` is the contract. Keep it to the density of the surrounding entries.

- [ ] **Step 5: Full gate run**

```bash
npm run check:docs
npm run check:scripts
npm run check:manifest
npm run check:lock
npm run test:python > /tmp/py.log 2>&1; tail -5 /tmp/py.log
node --test scripts/tests/ 2>&1 | tail -5
```
`test:python` takes several minutes — capture to a file, never pipe to grep, and let it finish. A killed run looks exactly like a failing one. Report actual numbers.

- [ ] **Step 6: Commit**

```bash
git add docs/adr/ docs/superpowers/specs/2026-10-21-auto-remediation-design.md CLAUDE.md
git commit -s -m "docs(infra): record the auto-remediation decision and fix two stale claims

Adds the ADR for auto-remediation of orchestrator halts: the rule, the
nine remediable sites, the fourteen that are not, the three absolute
refusals, and the attempt bound.

Corrects the spec's reference path -- shared references live flat in
skills/_shared/, not under a references/ subdirectory -- and records the
capability in CLAUDE.md.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Done when

- A project whose stories exist only as `.md` files gets them bootstrapped and the plan proceeds, in one invocation.
- A missing or stale plan pointer rebuilds itself; a RED plan re-plans once and then halts with its gaps named.
- A legacy layout migrates, a moved `implementation_artifacts` repoints, a gitignored state root is un-ignored — each reporting what it changed.
- Two diverging state layouts still halt, now naming which epic keys differ.
- `readiness: red` → amber never happens without the user asking.
- `check:docs` fails if any `BLOCKED:` site is unclassified or any declared remedy is missing from its step file.
