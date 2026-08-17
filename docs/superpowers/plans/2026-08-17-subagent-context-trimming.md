# Subagent Context Trimming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop re-loading 59,398 B of reference material into every subagent, by replacing a mandatory full load with a compact operative digest plus a routing table to the deep references.

**Architecture:** Add a ~70-line digest to `step-00-activate.md` containing only mechanical facts `pm-status.py` independently enforces (command signatures, key formats, the hard rule, runtime detection) and a symptom-to-section routing table. Demote `status-files.md` and `metrics-contract.md` from "load at activation and keep in context" to "consult on demand" — their bodies are unchanged and stay canonical. Narrow the unbounded `persistent_facts` recursive glob.

**Tech Stack:** Markdown step files and TOML customization files. No Python changes. `npm run sync:scripts` fans canonical sources out to three PM skill payload copies; `npm run check:scripts` gates on drift.

**Spec:** `docs/superpowers/specs/2026-08-17-subagent-context-trimming-design.md`

## Global Constraints

- **Never edit per-skill payload copies.** `skills/_shared/**` is the only editable source. `npm run sync:scripts` regenerates `skills/l3io-pm-{execute,plan,sync}/{scripts,references,steps}/`. CI runs `npm run check:scripts`.
- **Do not remove content from `status-files.md` or `metrics-contract.md`.** Only their header directives change (`status-files.md:6-7`, `metrics-contract.md:7-8`). Bodies stay byte-identical.
- **Digest scope limit:** only mechanical facts `pm-status.py` independently enforces — command signatures and key formats. **Never semantic rules**, which could drift with nothing detecting it.
- **Precedence, stated in the digest:** `pm-status.py` wins over the reference; the reference wins over the digest.
- **Routing-table anchors are load-bearing.** Every `§N` must resolve to the section named. A stale pointer is worse than no pointer.
- **No review phase is removed and no rigor is reduced.** This plan changes only *what is loaded*, never *what runs*. Any diff that alters a phase gate is out of scope and wrong.
- **Commits:** Conventional Commits, DCO sign-off. Put `Signed-off-by` and `Co-Authored-By` in the final trailer block (a footer after them breaks git's trailer parsing). Scopes: `l3io-pm`, `infra`.

---

### Task 1: Add the operative digest to step-00-activate.md

**Files:**
- Modify: `skills/_shared/steps/shared/step-00-activate.md` (insert new §8 before the existing `## 8. Output status line` at line 177, which becomes §9)

**Interfaces:**
- Consumes: the authoritative subcommand signatures in `skills/_shared/pm-status.py` docstring lines 27-70
- Produces: a digest section that Task 2 relies on existing before it demotes the references

- [ ] **Step 1: Record the current mandated size, as the before-measurement**

```bash
cd $REPO_ROOT
wc -c skills/_shared/status-files.md skills/_shared/metrics-contract.md
```

Expected: `20861` and `38537`, total `59398`. Note these in the commit message. If they differ, the references changed since the spec was measured — re-read them before continuing.

- [ ] **Step 2: Insert the digest**

In `skills/_shared/steps/shared/step-00-activate.md`, immediately before the line `## 8. Output status line`, insert:

```markdown
## 8. State and metrics digest — keep this in context

This is everything a normal run needs from the state and metrics contracts. **Do not load
`references/status-files.md` or `references/metrics-contract.md` unless the routing table at
the end of this section sends you there** — they are 1,178 lines combined, and re-reading them
per subagent is the single largest avoidable token cost in the system.

**Precedence.** `pm-status.py` is the authority: it enforces every rule below mechanically, so
if its behavior and this digest disagree, the script is right. Then the full reference. This
digest is last — treat it as stale if it conflicts.

### Keys

- Epic `E{nnn}` → directory `epic-{nnn}` · Sprint `S{nn}` → `sprint-{nn}`
- Story `E{nnn}-S{nn}-{nnn}` → file `E{nnn}-S{nn}-{nnn}.yaml` in that sprint's directory
- Backlog item `BL-E{nnn}-{nnn}` (`BL-E000-{nnn}` for repo-global)
- Zero-padded always. Node fields use `key:`, never `id:`.

### Never build a state path by hand

`pm-status.py` is the only component that resolves a key to a location. Address nodes by key;
if you find yourself concatenating `state/active/epic-...`, stop and use a subcommand.

Bind `{pm_status}` = `{project-root}/_bmad/scripts/pm-status.py`.

### The calls a sprint or epic run makes

```
set-status    --state-root S  (--story KEY | --epic ID [--sprint ID])  --status S
              [--title T] [--flock] [--no-events] [--session-id ID]
set-actual    --state-root S  --node {story,sprint,epic}  (--story KEY | --epic ID [--sprint ID])
              [--elapsed-hours H] [--man-hours H] [--tokens-k K] [--cost C]
              [--runtime {claude,other}] [--flock] [--no-calibrate]
set-estimate  --state-root S  (--story KEY | --epic ID [--sprint ID])
              story: --man-hours H --time-hours H --tokens-k K --cost C
              sprint/epic: --man-hours-low/-high, --time-hours-low/-high,
                           --tokens-k-min/-max, --cost-low/-high
              [--confidence {low,medium,high}] [--flock]
set-field     --state-root S  (--story KEY | --epic ID [--sprint ID])  --field NAME --value V
estimate-story   --state-root S  --story KEY  --classification {simple,standard,complex}
estimate-rollup  --state-root S  --epic ID  [--sprint ID]
verify        --state-root S  --scope {story,sprint,epic}  (--story KEY | --epic ID [--sprint ID])
              [--require-tokens] [--runtime {claude,other}]
show          --state-root S  --epic ID  [--sprint ID]
report        --state-root S  [--plan P] [--format tree|json|md] [--out F] [--all] [--watch SECS]
set-lock / clear-lock / check-lock   --state-root S  --epic ID  [--session-id SESS]
move-epic     --state-root S  --epic ID  --to {planned,active,archived}
append-issue  --file F  --key BL-E{nnn}-{nnn}  --epic E  [--sprint S]  --title T
              --source S  --severity {Low,Medium,High,Critical}  [--description D]
```

Exit codes: `0` success · `2` usage error · `3` node not found · `4` verification failure ·
`5` epic locked by another session. Branch on these rather than parsing stdout.

`set-status` and `set-actual` append to `state/events.jsonl` automatically. You never write
that file, and you never pass a flag to make it happen.

### Estimates and actuals — the HARD RULE

Every planning point and every closeout, at story, sprint, and epic level, records **both** an
`estimate` and an `actual` for all four metrics: man-hours, compute (wall-clock) hours, tokens,
and token cost. This is enforced at write time, not advisory.

Under `--runtime claude`, token and cost actuals are read **exactly** from the session
transcript's `usage` fields and `set-actual`/`verify` **reject** `N/A`. Under any other runtime
capture what is exposed and record `N/A` — **never a guess**.

`set-actual` derives the calibration sample itself. Write
`completion_evidence.fix_iterations` **before** calling it, or the scope-versus-fix split
cannot see it.

### When you do need the deep contract

| If you need to… | Read |
|---|---|
| interpret a `verify` failure | `references/status-files.md` §7 (Addressing) |
| know which fields a node carries | `references/status-files.md` §4 (Per-file schema) |
| handle a migration or legacy layout | `references/status-files.md` §10 (Read resolution at activation) |
| declare or read `depends_on` | `references/status-files.md` §11 (Dependency fields) |
| resolve an epic lock question | `references/status-files.md` §6 (Ownership lock) |
| capture token/cost actuals correctly | `references/metrics-contract.md` §3 (Runtime detection and capture) |
| write an estimate or actual by hand | `references/metrics-contract.md` §4 (Writing estimates and actuals) |
| explain a calibration result | `references/metrics-contract.md` §8 (Calibration) |
| see a full worked example | `references/metrics-contract.md` §10 (Worked example) |

```

- [ ] **Step 3: Renumber the output section**

Change `## 8. Output status line` to `## 9. Output status line`.

- [ ] **Step 4: Verify every routing-table anchor resolves**

```bash
cd $REPO_ROOT
python3 - <<'PY'
import re
want = {
 "skills/_shared/status-files.md": {4:"Per-file schema",6:"Ownership lock",7:"Addressing",
                                    10:"Read resolution",11:"Dependency fields"},
 "skills/_shared/metrics-contract.md": {3:"Runtime detection",4:"Writing estimates",
                                        8:"Calibration",10:"Worked example"},
}
bad = 0
for path, expect in want.items():
    heads = {}
    for line in open(path):
        m = re.match(r"^## (\d+)\.\s+(.*)$", line)
        if m: heads[int(m.group(1))] = m.group(2).strip()
    for num, frag in expect.items():
        actual = heads.get(num, "<MISSING>")
        ok = frag.lower() in actual.lower()
        if not ok: bad += 1
        print(f"  {'OK ' if ok else 'BAD'} {path.split('/')[-1]} §{num} → {actual!r}")
raise SystemExit(1 if bad else 0)
PY
```

Expected: 9 `OK` lines, exit 0. Any `BAD` means a section was renumbered — fix the digest's
table to match the file, not the other way round.

- [ ] **Step 5: Verify the digest contains no semantic rules**

```bash
cd $REPO_ROOT
sed -n '/^## 8. State and metrics digest/,/^## 9\./p' skills/_shared/steps/shared/step-00-activate.md | wc -l
```

Expected: roughly 90-110 lines. Then read that section and confirm every claim is either a
command signature, a key format, an exit code, or the two rules `pm-status.py` enforces at
write time (the `N/A` rejection under `--runtime claude`, and the `fix_iterations`-before-
`set-actual` ordering). If any line states a rule that nothing checks, delete it — that is the
drift risk the spec's scope constraint exists to prevent.

- [ ] **Step 6: Sync and gate**

```bash
npm run sync:scripts && npm run check:scripts
```

Expected: sync reports the step file copied to three skills; check exits 0.

- [ ] **Step 7: Commit**

```bash
git add -A skills/
git commit -F - <<'MSG'
perf(l3io-pm): add an operative digest to activation

status-files.md and metrics-contract.md each instruct every subagent to load them
at activation and keep their rules in context -- 1,178 lines / 59,398 B before any
project content, re-paid on every invocation. Only about 22% is operative for a
sprint subagent.

Adds a digest carrying just the mechanical facts pm-status.py independently
enforces: subcommand signatures, key formats, exit codes, the estimates-and-actuals
hard rule, and runtime capture. Ends with a symptom-to-section routing table so a
subagent that genuinely needs the deep contract goes straight to the right section
instead of searching 1,178 lines.

Additive only -- this commit does not yet change what the references instruct.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Signed-off-by: Shawn Anderson <sanderson@eye-catcher.com>
MSG
```

---

### Task 2: Demote the two references from mandatory load to on-demand

**Files:**
- Modify: `skills/_shared/status-files.md:5-7`
- Modify: `skills/_shared/metrics-contract.md:5-8`

**Interfaces:**
- Consumes: the digest section added in Task 1 (`## 8. State and metrics digest` in `step-00-activate.md`) — the new headers point at it by name
- Produces: nothing downstream depends on

- [ ] **Step 1: Rewrite the `status-files.md` header directive**

Replace exactly:

```markdown
This file is the single source of truth for **where** epic/sprint/story/backlog state lives
on disk and **how** to read or write it. Load it at activation alongside the metrics
contract and keep its rules in context for every read, every write, and every node move.
```

with:

```markdown
This file is the single source of truth for **where** epic/sprint/story/backlog state lives
on disk and **how** to read or write it. It is a **deep reference, consulted on demand** — do
not load it at activation. `steps/shared/step-00-activate.md` §8 carries the operative digest
every run needs (keys, subcommand signatures, exit codes) plus a routing table naming the
section to read for each case that genuinely needs this file: a `verify` failure (§7), a
per-file schema question (§4), a migration or legacy layout (§10), `depends_on` (§11), or an
epic lock question (§6).

This file outranks the digest. Where they disagree, this file is correct — and `pm-status.py`
outranks both, since it enforces these rules mechanically.
```

- [ ] **Step 2: Rewrite the `metrics-contract.md` header directive**

Replace exactly:

```markdown
This file is the single source of truth for **which** numbers l3io-pm records, **what they
are called on disk**, **how they are captured**, **where they are enforced**, and **how
estimates learn from them**. Load it at activation alongside `references/status-files.md`
and keep its rules in context for every estimate write and every closeout.
```

with:

```markdown
This file is the single source of truth for **which** numbers l3io-pm records, **what they
are called on disk**, **how they are captured**, **where they are enforced**, and **how
estimates learn from them**. It is a **deep reference, consulted on demand** — do not load it
at activation. `steps/shared/step-00-activate.md` §8 carries the HARD RULE and the runtime
capture rule, plus a routing table naming the section to read for each case that needs this
file: token/cost capture detail (§3), writing an estimate or actual by hand (§4), explaining a
calibration result (§8), or a worked example (§10).

Most of what follows is now mechanized. §6 (roll-up), §7 (fix reserve), and §8 (calibration)
describe what `estimate-story`, `estimate-rollup`, and `set-actual` do themselves — read them
to understand or debug a number, not to perform a calculation by hand.

This file outranks the digest. Where they disagree, this file is correct — and `pm-status.py`
outranks both.
```

- [ ] **Step 3: Verify no other file still mandates loading them**

```bash
cd $REPO_ROOT
grep -rn "Load it at activation\|keep its rules in context\|load .*status-files\.md\|load .*metrics-contract\.md" \
  skills/_shared/ | grep -vi "do not load" || echo "  NO MANDATORY LOAD REMAINS"
```

Expected: `NO MANDATORY LOAD REMAINS`. If a step file mandates a load, rewrite it to point at
the digest instead.

- [ ] **Step 4: Confirm the bodies are unchanged**

```bash
cd $REPO_ROOT
git diff --stat skills/_shared/status-files.md skills/_shared/metrics-contract.md
```

Expected: only the header hunks changed — a handful of insertions and deletions near the top
of each file, nothing below. If the diff touches numbered sections, revert and redo: the
global constraint forbids body edits.

- [ ] **Step 5: Sync and gate**

```bash
npm run sync:scripts && npm run check:scripts
```

Expected: sync reports `references/status-files.md` copied to three skills; check exits 0.

- [ ] **Step 6: Commit**

```bash
git add -A skills/
git commit -F - <<'MSG'
perf(l3io-pm): consult the state and metrics contracts on demand

Both files told every subagent to load them at activation and keep their rules in
context. That was correct when skills edited state YAML free-form and the contract
had to be resident to prevent malformed writes -- the exact failure pm-status.py
was introduced to end.

pm-status.py is now the sole writer and enforces all of it mechanically: atomic
temp-file-plus-rename writes, key-based addressing with no hand-built paths, flock
on shared append targets, and a read-back verify gate. A resident copy is
belt-and-braces on something that cannot be bypassed.

Both headers now point at the activation digest and name the section to read for
each case that genuinely needs the deep file. Bodies are unchanged and stay
canonical; precedence is stated explicitly as script > reference > digest.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Signed-off-by: Shawn Anderson <sanderson@eye-catcher.com>
MSG
```

---

### Task 3: Narrow `persistent_facts` and document the migration

**Files:**
- Modify: `skills/l3io-pm-execute/customize.toml:4`
- Modify: `skills/l3io-pm-plan/customize.toml:4`
- Modify: `skills/l3io-pm-sync/customize.toml:4`
- Modify: `skills/l3io-pm-help/customize.toml:4`
- Modify: `docs/upgrading.md` (new version-notes subsection)

**Interfaces:**
- Consumes: nothing from Tasks 1-2
- Produces: nothing downstream depends on

`customize.toml` files are per-skill and **not** generated by `sync:scripts` — edit all four
directly. `l3io-arch-review`, `l3io-util-doctor`, and `l3io-util-cleanup` already use `[]` and
must not be touched.

- [ ] **Step 1: Confirm the starting state**

```bash
cd $REPO_ROOT
grep -rn "persistent_facts" skills/*/customize.toml
```

Expected: the four PM skills each show `["file:{project-root}/**/project-context.md"]`; the
other three show `[]`.

- [ ] **Step 2: Replace the glob in all four PM skills**

```bash
cd $REPO_ROOT
python3 - <<'PY'
old = 'persistent_facts         = ["file:{project-root}/**/project-context.md"]'
new = ('persistent_facts         = [\n'
       '  "file:{project-root}/project-context.md",\n'
       '  "file:{project-root}/docs/project-context.md",\n'
       ']')
for s in ["l3io-pm-execute", "l3io-pm-plan", "l3io-pm-sync", "l3io-pm-help"]:
    p = f"skills/{s}/customize.toml"
    t = open(p).read()
    assert old in t, f"{p}: pattern not found"
    open(p, "w").write(t.replace(old, new, 1))
    print(f"  {p} updated")
PY
```

- [ ] **Step 3: Verify the TOML still parses**

```bash
cd $REPO_ROOT
python3 - <<'PY'
import tomllib
for s in ["l3io-pm-execute","l3io-pm-plan","l3io-pm-sync","l3io-pm-help",
          "l3io-arch-review","l3io-util-doctor","l3io-util-cleanup"]:
    p = f"skills/{s}/customize.toml"
    with open(p,"rb") as fh: d = tomllib.load(fh)
    facts = (d.get("workflow") or d.get("agent") or {}).get("persistent_facts")
    print(f"  {s:20} {facts}")
PY
```

Expected: the four PM skills each list exactly the two explicit paths with no `**`; the other
three show `[]`. A `tomllib` error means the multi-line array is malformed.

- [ ] **Step 4: Add the migration note to `docs/upgrading.md`**

First determine the version this will ship as:

```bash
cd $REPO_ROOT
npx commit-and-tag-version --dry-run 2>&1 | grep "bumping version in package.json"
```

Use the reported target version as `{VER}` below. In `docs/upgrading.md`, insert a new
subsection immediately after the `## Version notes` intro paragraph and before the existing
`### → 2.1.0` heading:

```markdown
### → {VER}

**`persistent_facts` no longer searches recursively.** The PM skills previously injected
`{project-root}/**/project-context.md` into every subagent — an unbounded recursive glob. It
is now two explicit paths:

```toml
persistent_facts = [
  "file:{project-root}/project-context.md",
  "file:{project-root}/docs/project-context.md",
]
```

**Action required only if your `project-context.md` lives somewhere else.** It will silently
stop being loaded — no error. Restore it by adding your path in
`_bmad/custom/{skill-name}.toml`; the customization model **appends** arrays across layers, so
your path and the defaults are both loaded:

```toml
[workflow]
persistent_facts = ["file:{project-root}/my/path/project-context.md"]
```

Nothing else changes. Subagents also no longer load the full state and metrics contracts at
activation — they carry an operative digest and consult those references on demand — which
cuts token use substantially with no change to which phases run.
```

- [ ] **Step 5: Verify the note renders and the version matches**

```bash
cd $REPO_ROOT
grep -n "persistent_facts no longer searches recursively" docs/upgrading.md
grep -c '\*\*' docs/upgrading.md >/dev/null && echo "  file readable"
```

Expected: the heading line is found, and its version matches what Step 4's dry run reported.

- [ ] **Step 6: Commit**

```bash
git add -A skills/ docs/upgrading.md
git commit -F - <<'MSG'
perf(l3io-pm): bound persistent_facts to explicit paths

persistent_facts was "file:{project-root}/**/project-context.md" in all four PM
skills -- a recursive glob with no bound, injected into every subagent, matching an
arbitrary number of files in a large repo with nothing reporting how much it pulled
in. Replaced with two explicit non-recursive paths.

The long tail needs no glob: the customization model appends arrays across layers,
so a project keeping its context file elsewhere adds its own path in
_bmad/custom/{skill-name}.toml and both are loaded.

This is a silent behavior change for anyone whose context file sits at a deeper
path -- it stops loading with no error. Mitigated twice: the default covers root
and docs/ rather than root only, and docs/upgrading.md documents the exact
override to restore a custom location.

l3io-arch-review, l3io-util-doctor, and the l3io-util-cleanup forwarder already
used [] and are untouched.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Signed-off-by: Shawn Anderson <sanderson@eye-catcher.com>
MSG
```

---

### Task 4: Verify end to end and record the measurement

**Files:**
- Modify: `CLAUDE.md` (the activation-loading description)
- Modify: `docs/l3io-pm-reference.md` (the activation-loading description)

**Interfaces:**
- Consumes: everything from Tasks 1-3
- Produces: the final measurement, recorded in the commit message

- [ ] **Step 1: Measure the after-state and compute the delta**

```bash
cd $REPO_ROOT
DIGEST=$(sed -n '/^## 8. State and metrics digest/,/^## 9\./p' \
  skills/_shared/steps/shared/step-00-activate.md | head -n -1 | wc -c)
REFS=$(( $(wc -c < skills/_shared/status-files.md) + $(wc -c < skills/_shared/metrics-contract.md) ))
echo "  before (mandated): $REFS B"
echo "  after  (mandated): $DIGEST B"
echo "  saved per subagent: $(( REFS - DIGEST )) B"
```

Expected: before ≈ 59,398 B; after ≈ 3,000-4,500 B; saved ≈ 55,000 B. Record the actual
numbers in the Step 6 commit message — the spec requires a measurement, not an estimate.

- [ ] **Step 2: Confirm subagents can still write conformant state**

```bash
cd $REPO_ROOT
T=$(mktemp -d); mkdir -p $T/state/active/epic-001/sprint-01
printf "key: 'E001'\ntitle: 'T'\nstatus: in-progress\n" > $T/state/active/epic-001/epic.yaml
printf "key: 'S01'\nepic: 'E001'\nstatus: in-progress\n" > $T/state/active/epic-001/sprint-01/sprint.yaml
printf "key: 'E001-S01-001'\nepic: 'E001'\nsprint: 'S01'\nstatus: backlog\n" > $T/state/active/epic-001/sprint-01/E001-S01-001.yaml
python3 skills/_shared/pm-status.py set-status --state-root $T/state --story E001-S01-001 --status review
python3 skills/_shared/pm-status.py verify --state-root $T/state --scope epic --epic E001; echo "  verify exit=$?"
python3 skills/_shared/pm-status.py report --state-root $T/state --format tree | head -8
rm -rf $T
```

Expected: `OK set-status`, `verify exit=0`, and a tree naming `E001`, `S01`, `E001-S01-001`.
This confirms the commands the digest documents actually work as written.

- [ ] **Step 3: Cross-check every command in the digest against the real CLI**

```bash
cd $REPO_ROOT
for c in set-status set-actual set-estimate set-field estimate-story estimate-rollup \
         verify show report set-lock clear-lock check-lock move-epic append-issue; do
  python3 skills/_shared/pm-status.py $c --help >/dev/null 2>&1 \
    && echo "  OK  $c" || echo "  MISSING  $c"
done
```

Expected: 14 `OK` lines. A `MISSING` means the digest documents a subcommand that does not
exist — remove it from the digest.

- [ ] **Step 4: Update the two docs that describe activation loading**

In `CLAUDE.md`, find the sentence in the `pm-status.py` paragraph reading
`Each PM skill activates it in a *Load the Status Helper* step.` and append to it:

```markdown
Subagents do **not** load `status-files.md` or `metrics-contract.md` at activation; `step-00-activate.md` §8 carries an operative digest (keys, subcommand signatures, exit codes, the estimates hard rule) and a routing table to the section of each reference that a given question needs. Those references remain canonical — script > reference > digest.
```

In `docs/l3io-pm-reference.md`, in the `### Activation and step order` section, add after the
step-order block:

```markdown
Activation ends with an operative digest (§8 of `step-00-activate.md`) covering keys,
`pm-status.py` signatures, exit codes, and the estimates hard rule. `status-files.md` and
`metrics-contract.md` are **not** loaded at activation — they are deep references consulted on
demand, and the digest's routing table names the section to read for each case. Precedence is
`pm-status.py` > reference > digest.
```

- [ ] **Step 5: Full gate**

```bash
cd $REPO_ROOT
npm run sync:scripts && npm run check:scripts
cd skills/_shared/tests && python3 test-pm-status.py 2>&1 | tail -3
```

Expected: check exits 0; `Ran 425 tests` / `OK`. No test covers prose, so this is a regression
guard on `pm-status.py`, not proof the digest is sufficient — Steps 2 and 3 cover that.

- [ ] **Step 6: Commit**

```bash
git add -A skills/ CLAUDE.md docs/
git commit -F - <<'MSG'
docs(l3io-pm): describe on-demand reference loading, and record the measurement

Mandated per-subagent reference load drops from 59,398 B to <DIGEST> B -- a saving
of <SAVED> B per invocation, measured rather than estimated. At 8-40 invocations
per sprint that is the largest single token reduction available, and no review
phase was removed: this changes only what is loaded, never what runs.

Verified that the digest is sufficient for the calls a run makes -- set-status,
verify --scope epic, and report all succeed against a fixture tree -- and that
every subcommand the digest documents exists in the CLI.

CLAUDE.md and the l3io-pm reference both described activation as loading the two
contracts. Updated, with precedence stated: pm-status.py > reference > digest.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Signed-off-by: Shawn Anderson <sanderson@eye-catcher.com>
MSG
```

Replace `<DIGEST>` and `<SAVED>` with the actual byte counts from Step 1 before committing.

---

## Self-Review

**1. Spec coverage**

| Spec requirement | Task |
|---|---|
| ~70-line operative digest, mechanical facts only | 1 (Step 2), enforced by 1 (Step 5) |
| Digest constrained to what `pm-status.py` enforces | 1 (Step 5) |
| Precedence: script > reference > digest | 1 (Step 2), restated in 2 (Steps 1-2), 4 (Step 4) |
| Routing table, symptom → section | 1 (Step 2) |
| Anchors verified to resolve | 1 (Step 4) |
| Both headers demoted to on-demand | 2 (Steps 1-2) |
| Reference bodies unchanged | 2 (Step 4) |
| `persistent_facts` → two explicit paths | 3 (Step 2) |
| Migration note in `docs/upgrading.md` | 3 (Step 4) |
| Default covers root **and** `docs/` | 3 (Step 2) |
| Step-file loading left alone | not a task — deliberate omission, per spec §3 |
| Verify: size measured before/after | 1 (Step 1), 4 (Step 1) |
| Verify: `verify --scope epic` passes | 4 (Step 2) |
| Verify: `report --format tree` renders | 4 (Step 2) |
| Verify: digest has no semantic rules | 1 (Step 5) |
| Verify: 425 tests pass | 4 (Step 5) |
| Out of scope: no content removed from references | Global Constraints + 2 (Step 4) |

No gaps. One spec item — "the implementation must verify each anchor resolves" — is Task 1
Step 4, which exits non-zero on failure so it cannot be skipped silently.

**2. Placeholder scan**

No `TBD`/`TODO`/"similar to Task N"/"add appropriate error handling". Every step carries a
runnable command with an expected result, or the literal markdown to insert. Two intentional
fill-ins are flagged with explicit instructions to resolve them before committing: `{VER}` in
Task 3 Step 4 (resolved by the dry-run command in that same step) and `<DIGEST>`/`<SAVED>` in
Task 4 Step 6 (resolved by Task 4 Step 1).

**3. Type consistency**

- The digest section is called `## 8. State and metrics digest — keep this in context` in Task 1 and referenced as "`step-00-activate.md` §8" in Tasks 2 and 4 — consistent.
- The `sed` range `/^## 8. State and metrics digest/,/^## 9\./` in Task 1 Step 5 and Task 4 Step 1 depends on Task 1 Step 3 having renumbered the output section to §9. Ordered correctly.
- Section numbers in the routing table (status-files §4/§6/§7/§10/§11, metrics-contract §3/§4/§8/§10) match Task 1 Step 4's verification map exactly, and both match the demoted headers written in Task 2.
- `persistent_facts` array formatting in Task 3 Step 2 matches what Task 3 Step 3 asserts and what Task 3 Step 4 documents.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-08-17-subagent-context-trimming.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session using executing-plans, batched with checkpoints for review.

**Which approach?**
