# Spec Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Specs become an input to the arch gate and both drift reviews, through a generated
index plus pointed-to sections. Every technical AC names its spec source, with the pointer
checked by a script. Drift findings end as recorded dispositions. Accepted architecture
departures are written back as one `docs(spec)` commit each, and ADRs move to a single home.

**Architecture:** a new shared script, `skills/_shared/spec-align.py` (uv PEP 723, no LLM),
does all the mechanical work: index, pointer check, dispositions, lease, guarded commit,
reject, ADR listing and migration. `pm-status.py` gains `--kind`/`--ref` backlog items and
an ADR allocator that scans the disk. Step files in pm-execute and util-doctor call the
script before any agent is dispatched. check-docs gains checks 13 and 14, and check 4 is
extended.

**Tech Stack:** Python 3.11 with markdown-it-py, mdit-py-plugins, ruamel.yaml, unidiff and
tenacity; git CLI; unittest; Node 22 with `node:test` for check-docs.

**Spec:** `docs/superpowers/specs/2026-09-11-spec-alignment-design.md` (commit `c2dd5e0`).

## Global Constraints

**Sources, payload and gates**
- Canonical shared sources live in `skills/_shared/`. **Never edit a per-skill copy.**
  After changing a payload file, run `npm run sync:scripts` and then
  `node scripts/write-payload-manifest.mjs`. Never hand-edit a `payload-manifest.json`.
- These gates must pass at every commit: `npm run check:scripts`, `npm run check:docs`,
  `npm run check:manifest`, `npm run check:version` and `npm run test:scripts`.

**`pm-status.py`**
- `pm-status.py` stays one file within ADR-0001's 8,000 lines. It is 6,604 lines today, and
  this plan adds about 90.
- No version bumps: never edit `# pm-status-version:`, `PM_STATUS_VERSION`, `package.json`
  or `module.yaml` versions.

**`spec-align.py`**
- Its PEP 723 dependencies are exactly `markdown-it-py>=3`, `mdit-py-plugins>=0.4`,
  `ruamel.yaml>=0.18`, `unidiff>=0.7` and `tenacity>=8`, with `requires-python = ">=3.11"`.
- Library-first: markdown goes through markdown-it-py (never regex over raw headings or
  tables); diffs through unidiff; retry and backoff through tenacity; globs through
  `fnmatch`/`glob`; YAML through ruamel.

**Tests**
- Tests use `unittest`, drive the **real CLI through `subprocess`**, and run git behaviour in
  a **real temporary git repo**. Items are created only through pm-status verbs; a file is
  hand-edited only to plant a state the CLI refuses to write.
- Every Python suite carries the private-TMPDIR leak guard (`setUpModule`/`tearDownModule`,
  copied verbatim from `test-pm-status.py:34-67`). Every `mkdtemp` is paired with
  `addCleanup(shutil.rmtree, path, True)`.
- Git in tests: set `GIT_CONFIG_GLOBAL=/dev/null` and `GIT_CONFIG_NOSYSTEM=1`, and give an
  author and committer identity through the environment, so a developer's own
  `commit.gpgsign` or hooks never leak in.
- Every new guard gets a non-hollow proof: revert the guard, confirm its test fails, then
  restore it. Record the proof in the task report.

**Commits**
- Conventional Commits with DCO, and **explicit-path staging only**. Never `git add -A` or
  `git add .` in the repo (in temp test repos it is fine). **Never `git stash`.** Other
  agents may share this checkout. Commit form:
  ```bash
  git commit -s -F - <<'EOF'
  <type>(<scope>): <subject>

  Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01E4PU5edGnYd8Dc12LbhDYY
  EOF
  ```

**Running the spec-align suite:**
`uv run -q --with 'markdown-it-py>=3' --with 'mdit-py-plugins>=0.4' --with 'ruamel.yaml>=0.18' --with 'unidiff>=0.7' --with 'tenacity>=8' python3 skills/_shared/tests/test-spec-align.py`
(the same command is called **SA-TEST** below). The pm-status suite runs as
`python3 skills/_shared/tests/test-pm-status.py` (**PM-TEST**). Always use absolute paths or
the repo root as cwd; never `cd` elsewhere inside a Bash call.

## Rulings made while planning

Each one refines the spec without contradicting it. Executors follow the ruling.

| # | Ruling | Why |
|---|---|---|
| R1 | Sprint drift finding IDs are `SD-{nn}-{n}`, e.g. `SD-02-3`, not `SD-{n}` | `sync-plan` and `commit` address findings across every sprint of an epic, so an ID has to be unique across that epic |
| R2 | `adr-reserve` gains an optional `--adr-dir D`, defaulting to `<git top-level>/docs/adr` | `{project-root}` need not be the git top-level (a BMad project in a monorepo). Step files pass `--adr-dir {project-root}/docs/adr`. The digest adds `[--adr-dir D]` (13 bytes; the budget has 41 left) |
| R3 | `spec-align.py` takes the global flag `--spec-paths JSON`, and the index records `# spec-paths: <json>` on header line 3. A call without the flag reuses the recorded list | Doctor can't read pm-execute's `customize.toml`; this way it checks the same spec set |
| R4 | A new subcommand, `propose --epic E (--finding ID \| --adr P)`, records a proposal the agent wrote and appends its backlog item | Recording proposals is then as mechanical as `commit` |
| R5 | `commit` takes `--finding ID` or `--adr P`. `--paths` must be exactly the pointer's file; stories rewritten by `--rename-anchor` are added by the script | One guard owns the scope decision |
| R6 | `disposition` takes `--spec-alignment {true,false}`; `false` refuses `spec-updated` and `spec-proposal` (exit 2) | Spec §8, enforced mechanically |
| R7 | A `spec_paths` file that matches no kind gets the kind `other`: it is indexed and pointable, but never `spec-updated` | Spec §2 gives no fallback |
| R8 | Discovery skips `{impl-root}/spec/` | `*spec*` would otherwise index the index whenever the planning root contains the implementation root |
| R9 | `disposition` and `check-dispositions` run whether the switch is on or off | They cost no tokens, and record what today's gate already requires |
| R10 | `sync-plan --defer` rewrites a deferred finding's disposition to `spec-proposal` with `deferred: true` | Spec §9: "becomes a `spec-proposal`" |
| R11 | `append-issue` refuses a spec kind without `--ref`, and a `spec-change` whose `--ref` isn't SHA-shaped (exit 2) | A guard at write time, beside audit 1k |
| R12 | The index header's `bytes:` counts the body below the header | A header can't include its own length |
| R13 | The new epic-closure sections are headed `## 2a. Spec sync` and `## 7. Commit checkpoint` | Check 3 parses `§2a` as `§2`, which exists, and existing section numbers stay stable |

## File structure

**New files:**

| File | Responsibility |
|---|---|
| `skills/_shared/spec-align.py` | The whole spec-alignment CLI: index, pointers, dispositions, ADRs, lease, sync plan and proposals, guarded commit, reject, stale check, migration |
| `skills/_shared/tests/test-spec-align.py` | Its suite: real CLI, real git |
| `skills/l3io-util-doctor/steps/migrate-adrs.md` | Doctor mode that wraps `migrate-adrs --plan/--apply` |
| `docs/adr/0004-agents-edit-architecture-specs.md` | ADR |
| `docs/adr/0005-one-adr-home.md` | ADR |

**Modified files:**

| File | Change |
|---|---|
| `skills/_shared/pm-status.py` | `ISSUE_KINDS`; `append-issue --kind/--ref`; `list-issues --kind`; promote refusal; audit 1k; `adr-reserve` disk scan and `--adr-dir` |
| `skills/_shared/tests/test-pm-status.py` | Tests for the above |
| `skills/_shared/steps/execute/step-04-arch-gate.md` | Index and sections as reviewer inputs; spec findings; ADRs to `docs/adr/` |
| `skills/_shared/steps/sprint/step-02-story-prep.md` | Provenance gate; enrichment layout |
| `skills/_shared/steps/sprint/step-03-dev-loop.md` | The fallback sentence |
| `skills/_shared/steps/closure/sprint-closure.md` | §6 inputs, IDs and dispositions |
| `skills/_shared/steps/sprint/step-04-sprint-closure.md` | §9 stages `spec/` |
| `skills/_shared/steps/closure/epic-closure.md` | §2, the new §2a, §3, §5 and the new §7 |
| `skills/_shared/steps/shared/step-00-digest.md` | The `adr-reserve` line |
| `skills/_shared/status-files.md` | Item `kind`/`ref`; the register scan; `spec-sync.lock` |
| `skills/l3io-pm-execute/SKILL.md`, `skills/l3io-pm-execute/customize.toml` | `{spec_align}` binding; `spec_alignment`; `spec_paths` |
| `skills/l3io-util-doctor/SKILL.md`, `steps/health-check.md`, `steps/triage.md` | Binding, mode row, Checks 15–19, spec pass |
| `skills/l3io-util-doctor/scripts/audit-backlog.py`, `scripts/tests/test-audit-backlog.py` | Skip spec items |
| `skills/l3io-pm-help/SKILL.md` | Spec item counts |
| `skills/l3io-arch-review/SKILL.md`, `skills/l3io-arch-review/assets/adr-template.md` | Mode A/C ADR allocation; two template lines |
| `scripts/sync-shared-scripts.mjs` | The `specAlignFiles` group |
| `scripts/check-docs.mjs`, `scripts/tests/check-docs.test.mjs` | Check 4 extension, checks 13 and 14 |
| `.github/workflows/checks.yml` | The spec-align suite step |
| `docs/l3io-pm-reference.md`, `CLAUDE.md` | Documentation |

Generated, never hand-edited: every `skills/<skill>/scripts|steps|references/...` copy and
every `payload-manifest.json`.

---
### Task 1: ADR-0004 and ADR-0005

**Files:**
- Create: `docs/adr/0004-agents-edit-architecture-specs.md`
- Create: `docs/adr/0005-one-adr-home.md`

**Interfaces:**
- Produces: the two decision records the spec names. Check 14's failure message (Task 18)
  cites `docs/adr/0005-one-adr-home.md`.

- [ ] **Step 1: Write ADR-0004**

```markdown
# ADR-0004: Agents edit architecture specs; PRD, UX and epic docs are proposal-only; edits are confirmed after they land

- **Status:** Accepted
- **Date:** 2026-09-11
- **Deciders:** Package maintainer (brainstorming 2026-09-11)
- **Principle(s) in tension:** keeping specs true to the code vs. keeping product intent under human control

## Context

Sprint and epic drift reviews resolved every departure by a code fix or an accepted ADR.
Nothing ever updated a spec, so each accepted departure left the architecture document
describing a system that no longer existed
(`docs/superpowers/specs/2026-09-11-spec-alignment-design.md`, Problem 3). Specs differ in
who owns them. The architecture document records how the system is built, which the build
itself settles. The PRD, UX and epic documents record what the product should be, which is a
human decision.

## Options considered

| Option | Pros | Cons | Standards fit |
|--------|------|------|---------------|
| A. Agents edit every spec | Specs never lag | An agent rewrites product intent to match what it happened to build | Violates human ownership of requirements |
| B. Agents never edit; everything is a proposal | Full control | Architecture docs lag by every accepted departure until a person finds time | The drift this design exists to remove |
| C. Agents edit architecture sections only; PRD/UX/epics get proposals; every edit is confirmed after it lands | Architecture stays true; product intent stays human; each edit is one revertible commit | A wrong edit is in history until confirmed or rejected | Chosen |
| D. As C, but confirm before editing | Nothing lands unconfirmed | An epic closure blocks on a human, which makes autonomous closure impossible | Rejected |

## Decision

Option C. `spec-align.py disposition` refuses `spec-updated` on any section whose kind is not
`architecture` (exit 2). Spec sync commits each architecture edit as its own
`docs(spec): {epic} {finding} — {title}` commit, made only after a scope guard (the diff stays
inside the pointed-to section) and an anchor guard (no pointed-to anchor silently vanishes).
Each commit opens a `spec-change` backlog item. Doctor `triage` confirms it
(`resolve-issue --resolution fixed`) or rejects it (`spec-align.py reject`: `git revert`,
`wontfix`, and a new defect so the drift becomes a code fix again). PRD, UX and epic changes
become `spec-proposal` items, backed by a proposal file.

## Consequences

- Positive: the architecture document tracks the built system at epic granularity. Each edit
  is reviewable and revertible on its own.
- Negative / trade-offs accepted: an unconfirmed edit is live in history, and a later edit on
  the same file makes a clean revert less likely. `check-stale` (doctor Check 18) reports
  exactly that case.
- Revisit if: proposals accumulate unconfirmed across several epics (people are not acting on
  them), or rejected spec changes become common (the agents' edits are not trustworthy).
```

- [ ] **Step 2: Write ADR-0005**

```markdown
# ADR-0005: One ADR home, `docs/adr/`; allocation takes the higher of the register and the files on disk

- **Status:** Accepted
- **Date:** 2026-09-11
- **Deciders:** Package maintainer (brainstorming 2026-09-11)
- **Principle(s) in tension:** a single source of truth for decisions vs. collision-free numbering by parallel agents

## Context

ADRs had two unconnected homes. The PM arch gate and closures wrote
`{implementation_artifacts}/epic-NNN/arch/adr-NNNN-slug.md`, numbered by
`state/adr-register.yaml` under a flock. `l3io-arch-review` Mode C wrote
`{project-root}/docs/adr/`, and nothing numbered those. `adr-reserve` never looked at
`docs/adr/`, so two different ADR-0003s could coexist. The register exists because a
directory listing shows who has finished, not who is in flight: three parallel agents once
took 0013 and 0014 twice each.

## Options considered

| Option | Pros | Cons | Standards fit |
|--------|------|------|---------------|
| A. Keep two homes | No migration | Duplicate numbers; readers must know both homes | Two sources of truth |
| B. `docs/adr/` only; number by directory listing | Simple | Reintroduces the in-flight collision the register fixed | Rejected by production evidence |
| C. `docs/adr/` only; the register allocates, starting at `max(register next, highest number on disk + 1)` under its existing lock | One home; in-flight safety kept; hand-written or unmigrated ADRs can't collide; a lagging register heals itself | A scan per reservation; a migration for existing projects | Chosen |
| D. The implementation-artifacts home only | No change for PM | Mode C and humans keep ADRs in `docs/adr/`, the conventional place | Rejected |

## Decision

Option C. `adr-reserve` scans `--adr-dir` (default `<git top-level of the state root>/docs/adr`;
step files pass `{project-root}/docs/adr`, because a BMad project need not be the repository
root) and the old home, `<state-root>/../epic-*/arch/adr-NNNN-*.md`. Mode C uses
`adr-reserve` when l3io-pm is installed. Without l3io-pm it takes the directory's highest
number plus one, which is safe only because no parallel PM agents exist in that setup. Doctor
Check 15 finds ADRs left in the old home, and the `migrate-adrs` mode moves them. On a number
collision it keeps the `docs/adr/` number and renumbers the epic ADR only inside its own epic
tree.

## Consequences

- Positive: one place to read decisions; `spec-align.py adrs --epic` lists an epic's ADRs
  from their `Epic:` line.
- Negative / trade-offs accepted: a project that does not migrate keeps working, because both
  readers still read the old home, but it carries two homes until it runs `migrate-adrs`.
- Revisit if: ADR numbering needs to span repositories, which a per-repo register cannot do.
```

- [ ] **Step 3: Verify the docs gate, then commit**

Run: `npm run check:docs`
Expected: `Documentation checks passed…` (exit 0).

```bash
git add docs/adr/0004-agents-edit-architecture-specs.md docs/adr/0005-one-adr-home.md
git commit -s -F - <<'EOF'
docs(adr): ADR-0004 spec edit authority, ADR-0005 one ADR home

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01E4PU5edGnYd8Dc12LbhDYY
EOF
```

---

### Task 2: pm-status — backlog item `kind` and `ref`

**Files:**
- Modify: `skills/_shared/pm-status.py`:
  - near `RESOLUTIONS` (line 4742);
  - `_append_issue` (the item block at about 5024–5034);
  - `_promotable_items` (5340);
  - `_audit_findings` (the open-item loop, after the `1f` check at about 5544);
  - `_list_issues` `matches()` (about 5830);
  - the parsers for `append-issue` (6434) and `list-issues` (6503).
- Modify: `skills/_shared/tests/test-pm-status.py` (new class at the end of the file)
- Modify: `skills/_shared/status-files.md` (issue schema at about 247–262; §7 `list-issues`
  row at 411)
- Modify: `docs/l3io-pm-reference.md` (the `append-issue` and `list-issues` rows at 477–478)
- Modify: `skills/l3io-util-doctor/steps/triage.md` (the T2 table's "report only" row)
- Regenerated: payload copies and manifests

**Interfaces:**
- Produces:
  - `ISSUE_KINDS = ("defect", "spec-change", "spec-proposal")` and
    `SPEC_ISSUE_KINDS = ISSUE_KINDS[1:]`.
  - `append-issue --kind K --ref R`, which writes `kind:` only when it isn't `defect` and
    `ref:` when given.
  - `list-issues --kind K`, where an item with no `kind` counts as `defect`.
  - `promote-issue`, which exits 2 on spec items.
  - Audit finding id `1k`.
- Consumed by: spec-align `commit`, `propose`, `sync-plan --defer`, `reject` and `check-stale`
  (Tasks 9–11); `audit-backlog.py` (Task 17).

- [ ] **Step 1: Write the failing tests.** Append this class to the end of
  `skills/_shared/tests/test-pm-status.py`, just before the
  `if __name__ == "__main__":` block if there is one, otherwise at the very end:

```python
class TestIssueKinds(IssueBase):
    """append-issue --kind/--ref, list-issues --kind, promote refusal, audit 1k."""

    SHA = "3f9c2a1"

    def spec_item(self, kind="spec-change", ref=None, title="Spec change: order API"):
        ref = self.SHA if ref is None else ref
        return self.append(title, "001", "", "Medium", "spec-sync (AD-1)",
                           "--kind", kind, "--ref", ref, "--description", "Confirm or reject")

    def item(self, key="BL-E001-001"):
        return next(i for i in self.load_open()["backlog"] if str(i["key"]) == key)

    def test_kind_and_ref_round_trip(self):
        code, out, err = self.spec_item()
        self.assertEqual(code, 0, err)
        it = self.item()
        self.assertEqual(it["kind"], "spec-change")
        self.assertEqual(it["ref"], self.SHA)
        self.assert_invariants()

    def test_defect_writes_no_kind(self):
        code, _, err = self.append("Plain finding")
        self.assertEqual(code, 0, err)
        self.assertNotIn("kind", self.item())
        self.assertNotIn("ref", self.item())

    def test_spec_kind_requires_ref(self):
        code, _, err = self.append("Spec proposal: x", "001", "", "Low", "spec-sync (AD-2)",
                                   "--kind", "spec-proposal")
        self.assertEqual(code, 2)
        self.assertIn("needs --ref", err)
        self.assertEqual(self.open_keys(), [])

    def test_spec_change_ref_must_be_a_sha(self):
        code, _, err = self.spec_item(ref="not-a-sha")
        self.assertEqual(code, 2)
        self.assertIn("commit SHA", err)

    def test_spec_proposal_ref_may_be_a_path(self):
        code, _, err = self.spec_item(kind="spec-proposal",
                                      ref="impl/epic-001/epic-closure/spec-proposals/AD-2.md")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.item()["kind"], "spec-proposal")

    def test_list_issues_kind_filter(self):
        self.append("Plain finding")
        self.spec_item()
        code, out, err = self.run_all(["list-issues", "--state-root", self.root,
                                       "--kind", "spec-change", "--format", "json"])
        self.assertEqual(code, 0, err)
        self.assertEqual([i["key"] for i in json.loads(out)], ["BL-E001-002"])
        code, out, _ = self.run_all(["list-issues", "--state-root", self.root,
                                     "--kind", "defect", "--format", "json"])
        self.assertEqual([i["key"] for i in json.loads(out)], ["BL-E001-001"])

    def test_promote_refuses_spec_items(self):
        self.spec_item()
        code, _, err = self.run_all(["promote-issue", "--state-root", self.root,
                                     "--artifacts-root", self.arts, "--key", "BL-E001-001",
                                     "--epic", "001", "--sprint", "02",
                                     "--classification", "standard"])
        self.assertEqual(code, 2)
        self.assertIn("spec-change", err)
        self.assertIn("triage", err)
        self.assertEqual(self.item().get("status"), "backlog")

    def _edit_open(self, old, new):
        with open(self.issues, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn(old, text)
        with open(self.issues, "w", encoding="utf-8") as fh:
            fh.write(text.replace(old, new, 1))

    def audit(self):
        code, out, err = self.run_all(["audit-issues", "--state-root", self.root,
                                       "--format", "json"])
        return code, json.loads(out)

    def test_audit_1k_unknown_kind(self):
        self.append("Plain finding")
        # A hand edit plants what the CLI refuses to write.
        self._edit_open("status: backlog", "status: backlog\n  kind: bogus")
        code, rep = self.audit()
        self.assertEqual(code, 4)
        self.assertIn(("1k", "BL-E001-001"), {(f["id"], f["key"]) for f in rep["findings"]})

    def test_audit_1k_spec_item_without_ref(self):
        self.spec_item()
        self._edit_open(f"ref: {self.SHA}\n", "")
        code, rep = self.audit()
        self.assertEqual(code, 4)
        hits = [f for f in rep["findings"] if f["id"] == "1k"]
        self.assertEqual(len(hits), 1)
        self.assertIn("no ref", hits[0]["detail"])

    def test_audit_clean_with_valid_spec_items(self):
        self.spec_item()
        code, rep = self.audit()
        self.assertEqual([f for f in rep["findings"] if f["id"] == "1k"], [])
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 skills/_shared/tests/test-pm-status.py TestIssueKinds -q`
Expected: FAIL. argparse rejects `--kind`: `unrecognized arguments` and exit 2 where 0 was
expected.

- [ ] **Step 3: Implement the change in `skills/_shared/pm-status.py`**

(a) Directly below `RESOLUTIONS = ("fixed", "wontfix", "duplicate", "obsolete")`:

```python
# A backlog item's kind. `defect` is the default and is never written, so every file written
# before kinds existed still reads as all defects. The spec kinds come from spec-align.py's
# spec sync (docs/adr/0004-agents-edit-architecture-specs.md): they are confirmed or
# rejected in doctor triage, never promoted to a story.
ISSUE_KINDS = ("defect", "spec-change", "spec-proposal")
SPEC_ISSUE_KINDS = ISSUE_KINDS[1:]
```

(b) In `_append_issue`, directly after the line `norm_title = _norm_issue_title(args.title)`:

```python
    kind = getattr(args, "kind", None) or "defect"
    ref = (getattr(args, "ref", None) or "").strip()
    if kind in SPEC_ISSUE_KINDS and not ref:
        raise PMError(2, f"append-issue: --kind {kind} needs --ref (the docs(spec) commit SHA, "
                         f"or the proposal file's path)")
    if kind == "spec-change" and not _SHA_RE.match(ref):
        raise PMError(2, f"append-issue: --kind spec-change needs --ref to be a commit SHA, "
                         f"not {ref!r}")
```

(c) In `_append_issue`, replace

```python
        item["status"] = "backlog"
        if args.description:
```

with

```python
        item["status"] = "backlog"
        if kind != "defect":
            item["kind"] = kind
        if ref:
            item["ref"] = ref
        if args.description:
```

(d) In `_promotable_items`, directly after the `scheduled` refusal (the line
`raise PMError(2, f"{k} is already scheduled to story {item.get('story')}")`), at the same
indentation as that `if`:

```python
        kind = str(item.get("kind") or "defect")
        if kind != "defect":
            raise PMError(2, f"{k} is a {kind} item -- spec items are confirmed or rejected in "
                             f"/l3io-util-doctor triage, never promoted to a story")
```

(e) In `_audit_findings`: change the docstring's `1a-1j` to `1a-1k`. Then, directly after
the two `1f` lines

```python
        if st not in OPEN_ISSUE_STATUSES:
            add("1f", k, f"open item has status {st!r}", "report only")
```

insert:

```python
        kind = it.get("kind")
        if kind is not None and str(kind) not in ISSUE_KINDS:
            add("1k", k, f"unknown kind {kind!r}", "report only -- fix the kind by hand")
        elif str(kind) in SPEC_ISSUE_KINDS and not str(it.get("ref") or "").strip():
            add("1k", k, f"{kind} item has no ref",
                "report only -- add the commit SHA or the proposal path by hand")
```

(f) In `_list_issues`'s `matches()`, directly after the `args.resolution` check and before
`return True`:

```python
        if getattr(args, "kind", None) and str(item.get("kind") or "defect") != args.kind:
            return False
```

(g) Parser: in the `append-issue` block, after the `--description` argument:

```python
    ai.add_argument("--kind", default="defect", choices=list(ISSUE_KINDS),
                    help="defect (default, not written) | spec-change | spec-proposal")
    ai.add_argument("--ref", default="",
                    help="spec kinds only: the docs(spec) commit SHA, or the proposal path")
```

In the `list-issues` block, after `--resolution`:

```python
    li.add_argument("--kind", choices=list(ISSUE_KINDS),
                    help="items of this kind; an item without `kind` is a defect")
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 skills/_shared/tests/test-pm-status.py TestIssueKinds -q`
Expected: `OK` (10 tests).
Then run PM-TEST in full. Expected: `OK`; the only new tests are these 10.

- [ ] **Step 5: Non-hollow proof.** Temporarily delete insertion (d), the promote refusal, and
  rerun `TestIssueKinds.test_promote_refuses_spec_items`. It must FAIL. Restore it. Do the
  same for (e), with `test_audit_1k_spec_item_without_ref`. Note both in the report.

- [ ] **Step 6: Documentation**

`skills/_shared/status-files.md`, in the `# state/issues.yaml — open items only` example,
directly after `  description: 'See …/closure/review-E001-S02-003.md'`:

```yaml
- key: BL-E003-007
  …
  kind: spec-change                       # absent = defect | spec-change | spec-proposal
  ref: 3f9c2a1                            # spec kinds only: the docs(spec) commit, or the proposal path
```

In the same file's §7 table, append this to the end of the `list-issues` row's second cell:
` \`--kind {defect,spec-change,spec-proposal}\` filters by kind (no \`kind\` = defect).`

`docs/l3io-pm-reference.md`, in the `append-issue` row, append:
` \`--kind {defect,spec-change,spec-proposal}\` (default \`defect\`, written only when not the default) with \`--ref\` — required for the spec kinds, and a commit SHA for \`spec-change\`; \`promote-issue\` refuses spec items (they are confirmed or rejected in \`/l3io-util-doctor triage\`).`
In the `list-issues` row, append the same `--kind` sentence as in `status-files.md`.

`skills/l3io-util-doctor/steps/triage.md`, in the T2 table, change the row
`| \`1b\` naming an unknown key, \`1f\`, \`1h\`, \`1i\` | report only …` so that its first
cell reads `` `1b` naming an unknown key, `1f`, `1h`, `1i`, `1k` ``.

- [ ] **Step 7: Sync, run the gates, and commit**

Run: `npm run sync:scripts && node scripts/write-payload-manifest.mjs && npm run check:scripts && npm run check:docs && npm run check:manifest && npm run check:version && npm run test:scripts`
Expected: every command exits 0.

```bash
git add skills/_shared/pm-status.py skills/_shared/tests/test-pm-status.py \
  skills/_shared/status-files.md docs/l3io-pm-reference.md \
  skills/l3io-util-doctor/steps/triage.md \
  skills/l3io-pm-execute/scripts/pm-status.py skills/l3io-pm-plan/scripts/pm-status.py \
  skills/l3io-pm-sync/scripts/pm-status.py skills/l3io-util-doctor/scripts/pm-status.py \
  skills/l3io-pm-execute/references/status-files.md skills/l3io-pm-plan/references/status-files.md \
  skills/l3io-pm-sync/references/status-files.md \
  skills/*/payload-manifest.json
git status --short   # nothing else of yours may be staged
git commit -s -F - <<'EOF'
feat(l3io-pm): backlog item kind and ref for spec-change and spec-proposal items

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01E4PU5edGnYd8Dc12LbhDYY
EOF
```

(`sync:scripts` already `git add`s the copies it rewrote. The explicit list above is what you
verify with `git status --short`. If a manifest did not change, git ignores it.)

---

### Task 3: pm-status — `adr-reserve` scans the disk

**Files:**
- Modify: `skills/_shared/pm-status.py` (a helper above `cmd_adr_reserve` at 2493; one line
  inside it; the parser at about 6588)
- Modify: `skills/_shared/tests/test-pm-status.py`:
  - the `TestAdrRegister.run_main` stderr capture, and `--adr-dir` in its calls;
  - `TestConcurrentAdrReservation`;
  - a new class.
- Modify: `skills/_shared/steps/shared/step-00-digest.md:117`;
  `skills/_shared/status-files.md` (register paragraph); `docs/l3io-pm-reference.md:487`

**Interfaces:**
- Produces: `highest_adr_on_disk(state_root, adr_dir="") -> int` and
  `adr-reserve … [--adr-dir D]`. The first number handed out is
  `max(register next, highest_adr_on_disk + 1)`.
- Consumed by: spec-align `migrate-adrs` (Task 12) and every step file that reserves (Task 13).

- [ ] **Step 1: Make the existing ADR tests independent of the environment.** Once the scan
  lands, an `adr-reserve` outside a git repo warns on stderr, and inside one it scans that
  repo's `docs/adr`. Existing tests must pin `--adr-dir` to an empty directory.

In `TestAdrRegister`, replace its `run_main` with:

```python
    def run_main(self, argv):
        buf, err = io.StringIO(), io.StringIO()
        code = 0
        if argv and argv[0] == "adr-reserve" and "--adr-dir" not in argv:
            argv = [*argv, "--adr-dir", os.path.join(self.d, "no-adr-dir")]
        try:
            with redirect_stdout(buf), redirect_stderr(err):
                code = pm.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        self.last_err = err.getvalue()
        return code, buf.getvalue()
```

(`TestLayoutResolution.setUp` provides `self.d`; confirm with
`grep -n "self.d = " skills/_shared/tests/test-pm-status.py | head`. If it is named
differently there, use that attribute.)

`test_malformed_reserved_field_is_refused_not_silently_repaired` wraps its call in its own
`redirect_stderr(buf)`. Change that test to read `self.last_err` instead of `buf.getvalue()`,
and drop its `with redirect_stderr(buf):` wrapper.

In `TestConcurrentAdrReservation`, add `"--adr-dir", os.path.join(self.d, "no-adr-dir")`
to the `Popen` argv, right after `"--slug", f"slug-{i}"`.

Run: `python3 skills/_shared/tests/test-pm-status.py TestAdrRegister TestConcurrentAdrReservation -q`
Expected: FAIL. `--adr-dir` is not a known argument yet. That is the expected red for Step 2.

- [ ] **Step 2: Write the failing tests.** Append this to the end of the test file:

```python
class TestAdrReserveScansDisk(unittest.TestCase):
    """adr-reserve starts at max(register next, highest ADR on disk + 1): docs/adr (the one
    home, ADR-0005) and the old epic-*/arch home, under the register's own lock."""

    GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.impl = os.path.join(self.d, "impl")
        self.root = os.path.join(self.impl, "state")
        os.makedirs(self.root)
        self.empty = os.path.join(self.d, "no-adr-dir")

    def touch(self, *parts):
        p = os.path.join(self.d, *parts)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("# ADR\n")

    def reserve(self, *extra):
        import subprocess
        r = subprocess.run([sys.executable, SCRIPT, "adr-reserve", "--state-root", self.root,
                            "--epic", "E001", "--slug", "t", *extra],
                           capture_output=True, text=True, env={**os.environ, **self.GIT_ENV})
        return r.returncode, r.stdout.split(), r.stderr

    def test_explicit_adr_dir_is_scanned(self):
        self.touch("docs", "adr", "0010-z.md")
        code, out, err = self.reserve("--adr-dir", os.path.join(self.d, "docs", "adr"))
        self.assertEqual((code, out), (0, ["0011"]), err)
        self.assertEqual(pm.load_adr_register(self.root)[1]["next"], 12)

    def test_old_home_is_scanned(self):
        self.touch("impl", "epic-001", "arch", "adr-0004-y.md")
        code, out, err = self.reserve("--adr-dir", self.empty)
        self.assertEqual((code, out), (0, ["0005"]), err)

    def test_register_ahead_of_disk_wins(self):
        with open(pm.adr_register_path(self.root), "w", encoding="utf-8") as fh:
            fh.write("next: 20\nreserved: []\n")
        self.touch("docs", "adr", "0007-x.md")
        code, out, _ = self.reserve("--adr-dir", os.path.join(self.d, "docs", "adr"))
        self.assertEqual(out, ["0020"])

    def test_default_adr_dir_is_the_git_toplevel(self):
        import subprocess
        subprocess.run(["git", "init", "-q", self.d], check=True,
                       env={**os.environ, **self.GIT_ENV})
        self.touch("docs", "adr", "0007-x.md")
        code, out, err = self.reserve()
        self.assertEqual((code, out), (0, ["0008"]), err)
        self.assertNotIn("not inside a git work tree", err)

    def test_outside_git_warns_and_scans_old_home_only(self):
        self.touch("docs", "adr", "0007-x.md")      # unreachable without git or --adr-dir
        self.touch("impl", "epic-002", "arch", "adr-0002-y.md")
        code, out, err = self.reserve()
        self.assertEqual((code, out), (0, ["0003"]))
        self.assertIn("not inside a git work tree", err)

    def test_concurrent_reservations_skip_a_hand_written_adr(self):
        import subprocess
        self.touch("docs", "adr", "0003-hand.md")
        adr_dir = os.path.join(self.d, "docs", "adr")
        procs = [subprocess.Popen([sys.executable, SCRIPT, "adr-reserve", "--state-root",
                                   self.root, "--epic", "E001", "--slug", f"s{i}",
                                   "--adr-dir", adr_dir],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for i in range(8)]
        numbers = []
        for p in procs:
            out, err = p.communicate(timeout=120)
            self.assertEqual(p.returncode, 0, err.decode())
            numbers.extend(out.decode().split())
        self.assertEqual(sorted(numbers), [f"{n:04d}" for n in range(4, 12)])
```

Run: `python3 skills/_shared/tests/test-pm-status.py TestAdrReserveScansDisk -q`
Expected: FAIL (unknown `--adr-dir`; the default-dir cases return `0001`).

- [ ] **Step 3: Implement.** First check the imports:
  `grep -n -E "^import (glob|subprocess)$" skills/_shared/pm-status.py`. Add any that are
  missing, in the alphabetical import block at the top of the file. Then, directly above
  `def cmd_adr_reserve(args) -> int:`:

```python
_ADR_DOC_NAME = re.compile(r"^(\d{4})-.+\.md$")
_ADR_OLD_HOME_NAME = re.compile(r"^adr-(\d{4})-.+\.md$")


def _git_toplevel(path: str):
    """The git work tree containing `path`, or None (not a repo, or no git on PATH)."""
    try:
        r = subprocess.run(["git", "-C", path, "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True)
    except OSError:
        return None
    top = r.stdout.strip()
    return top if r.returncode == 0 and top else None


def highest_adr_on_disk(state_root: str, adr_dir: str = "") -> int:
    """Highest ADR number already written, in the one home and in the old one (ADR-0005).

    The register still records who is in flight; this scan only stops a new reservation
    from colliding with a file that already exists: a hand-written ADR, a Mode C ADR, or
    an ADR in a project that has not run `migrate-adrs`. The one home is `adr_dir` when
    given (step files pass {project-root}/docs/adr, since a BMad project need not be the
    repository root), else <git top-level of the state root>/docs/adr."""
    impl = os.path.dirname(os.path.abspath(state_root))
    hi = 0
    for arch in glob.glob(os.path.join(impl, "epic-*", "arch")):
        for name in os.listdir(arch):
            m = _ADR_OLD_HOME_NAME.match(name)
            if m:
                hi = max(hi, int(m.group(1)))
    if not adr_dir:
        top = _git_toplevel(state_root if os.path.isdir(state_root) else impl)
        if top is None:
            sys.stderr.write(f"pm-status.py: adr-reserve: {state_root} is not inside a git work "
                             f"tree -- scanned only the old ADR home (epic-*/arch/); pass "
                             f"--adr-dir to scan docs/adr too\n")
        else:
            adr_dir = os.path.join(top, "docs", "adr")
    if adr_dir and os.path.isdir(adr_dir):
        for name in os.listdir(adr_dir):
            m = _ADR_DOC_NAME.match(name)
            if m:
                hi = max(hi, int(m.group(1)))
    return hi
```

In `cmd_adr_reserve`, directly after

```python
        if start < 1:
            start = 1
```

add:

```python
        start = max(start, highest_adr_on_disk(args.state_root, args.adr_dir) + 1)
```

Parser: in the `adr-reserve` block, after `ar.add_argument("--count", type=int, default=1)`:

```python
    ar.add_argument("--adr-dir", dest="adr_dir", default="",
                    help="the one ADR home to scan (default: <git top-level>/docs/adr)")
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 skills/_shared/tests/test-pm-status.py TestAdrRegister TestConcurrentAdrReservation TestAdrReserveScansDisk -q`
Expected: `OK`. Then run PM-TEST in full. Expected: `OK`, with no `not inside a git work
tree` lines on the console. Check with
`python3 skills/_shared/tests/test-pm-status.py -q 2>&1 | grep -c "not inside a git"`, which
must print `0`.

- [ ] **Step 5: Non-hollow proof.** Comment out the `start = max(...)` line and rerun
  `TestAdrReserveScansDisk`. At least four tests must fail. Restore the line.

- [ ] **Step 6: Documentation**
  - `step-00-digest.md:117`: the line becomes
    `adr-reserve   --state-root S  --epic ID  --slug SLUG  [--count N]  [--adr-dir D]`.
    Then run `wc -c skills/_shared/steps/shared/step-00-digest.md`. It must stay at or under
    12600 (check 8).
  - `docs/l3io-pm-reference.md:487`, `adr-reserve` row: after `optional \`--count N\`
    (default 1)`, insert
    `and \`--adr-dir D\` (the one ADR home to scan; default \`<git top-level>/docs/adr\`)`.
    After `prints one zero-padded number per line.`, insert:
    `The first number is the larger of the register's \`next\` and the highest ADR number
    already on disk — in \`--adr-dir\` and in the old per-epic home \`epic-*/arch/\` — plus
    one (ADR-0005); outside a git work tree without \`--adr-dir\` it scans the old home only,
    with a stderr warning.`
  - `skills/_shared/status-files.md`: find the paragraph describing `adr-register.yaml` in §9
    (around line 526–540), and append the same sentence.

- [ ] **Step 7: Sync, run the gates, and commit.** Use Task 2 Step 7's gate command. Stage
  `skills/_shared/pm-status.py`, `skills/_shared/tests/test-pm-status.py`,
  `skills/_shared/steps/shared/step-00-digest.md`, `skills/_shared/status-files.md`,
  `docs/l3io-pm-reference.md`, the four `scripts/pm-status.py` copies, the three
  `steps/shared/step-00-digest.md` copies (pm-execute, pm-plan, pm-sync), the three
  `references/status-files.md` copies, and the changed manifests. Commit with the subject
  `feat(l3io-pm): adr-reserve scans docs/adr and the old ADR home before allocating`.

---
### Task 4: `spec-align.py` scaffold and `build` (the spec index)

**Files:**
- Create: `skills/_shared/spec-align.py`
- Create: `skills/_shared/tests/test-spec-align.py`
- Modify: `scripts/sync-shared-scripts.mjs` (new group; header comment)
- Modify: `.github/workflows/checks.yml` (new step after the `drift-report.py` step)
- Generated: `skills/l3io-pm-execute/scripts/spec-align.py`,
  `skills/l3io-util-doctor/scripts/spec-align.py`, and both manifests

**Interfaces:**
- Produces, and used by every later spec-align task:
  - **Classes:** `SAError(code, msg)`; `Ctx` (fields `project`, `planning`, `impl`,
    `state_root`, `pm_status`, `spec_paths_arg`; methods `need(*"impl"|"state"|"pm")`,
    `rel(p)`, `abs(p)`, `index_path()`); `Section` (`level`, `title`, `anchor`, `start`,
    `end`, `summary`; lines are 1-based and inclusive).
  - **Functions:** `md()`, `parse_sections(text) -> [Section]`, `kind_of(name)`,
    `discover(ctx) -> [(rel, kind)]`, `effective_spec_paths(ctx)`, `atomic_write(path, text)`,
    `read_text(path)`, `_under(path, root)`.
  - **`load_catalog(ctx) -> {rel: {"kind", "sections", "anchors": {anchor: Section}, "error", "sha"}}`.**
  - **`build_parser()`** ends with the marker comment
    `# Later tasks register their subcommands above this line.`, and each later task inserts
    its parser block directly above that line.
  - The CLI global flags `--project-root --planning-root --impl-root --state-root --pm-status
    --spec-paths`.

- [ ] **Step 1: Write the failing tests.** Create `skills/_shared/tests/test-spec-align.py`:

````python
#!/usr/bin/env python3
"""
Tests for spec-align.py. Run with:
  uv run -q --with 'markdown-it-py>=3' --with 'mdit-py-plugins>=0.4' --with 'ruamel.yaml>=0.18' \
    --with 'unidiff>=0.7' --with 'tenacity>=8' python3 skills/_shared/tests/test-spec-align.py
Every case drives the real CLI in a subprocess. Git behaviour runs in a real temporary repo;
backlog items are created only through the real pm-status.py CLI.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest


# -- temp-dir leak guard ---------------------------------------------------------------- #
# setUpModule points tempfile.tempdir (this test process) AND the TMPDIR environment variable
# (inherited by every subprocess it spawns) at one private run directory; tearDownModule fails
# the run if anything is left in it, then removes it and restores both to their prior values.
# Covered: every tempfile.mkdtemp()/mkstemp()/NamedTemporaryFile() made by this process or by
# a child that honours TMPDIR. Not covered: a child that writes to a hard-coded directory. The
# one name it ignores is `uv-*.lock`, which `uv run` leaves in TMPDIR by design
# (test-write-module-config spawns `uv run`). Fixtures without cleanup once left 60,936
# directories in /tmp and exhausted its inodes. Set in setUpModule, not at import, so a child
# process that re-imports this module never creates a run directory it would not remove.
_RUN_TMP = None
_PREV_TMPDIR = None             # the TMPDIR environment variable, or None
_PREV_TEMPFILE_TEMPDIR = None   # tempfile.tempdir as it was before setUpModule


def setUpModule():
    global _RUN_TMP, _PREV_TMPDIR, _PREV_TEMPFILE_TEMPDIR
    _PREV_TEMPFILE_TEMPDIR = tempfile.tempdir
    _RUN_TMP = tempfile.mkdtemp(prefix="test-spec-align-")
    tempfile.tempdir = _RUN_TMP
    _PREV_TMPDIR = os.environ.get("TMPDIR")
    os.environ["TMPDIR"] = _RUN_TMP


def tearDownModule():
    tempfile.tempdir = _PREV_TEMPFILE_TEMPDIR
    if _PREV_TMPDIR is None:
        os.environ.pop("TMPDIR", None)
    else:
        os.environ["TMPDIR"] = _PREV_TMPDIR
    leaked = sorted(n for n in os.listdir(_RUN_TMP)
                    if not (n.startswith("uv-") and n.endswith(".lock")))
    shutil.rmtree(_RUN_TMP, ignore_errors=True)
    if leaked:
        raise AssertionError(f"temp-dir leak: {len(leaked)} entr"
                             f"{'y' if len(leaked) == 1 else 'ies'} left by tests without "
                             f"cleanup: {', '.join(leaked[:5])}")


HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "spec-align.py")
PM = os.path.join(os.path.dirname(HERE), "pm-status.py")
GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
PLAN = "_bmad-output/planning-artifacts"
IMPL = "_bmad-output/implementation-artifacts"
ARCH_REL = f"{PLAN}/architecture.md"
# Line numbers matter to the range assertions below:
#  1 # Architecture          5 ## Data model        9 ## Order API        17 ## Data model
# 21 ### Auth: v2 (beta)    23 last line. Sections: architecture L1-23, data-model L5-8,
# order-api L9-16, data-model-1 L17-23, auth-v2-beta L21-23.
ARCH = """# Architecture

Intro paragraph. Second sentence.

## Data model

Orders live in Postgres, one row per order. Items are JSON.

## Order API

POST /orders accepts a body.

```
# not a heading
```

## Data model

Duplicate title section.

### Auth: v2 (beta)

OIDC via the gateway.
"""


class Project(unittest.TestCase):
    """A scratch project: planning + implementation artifacts, optionally a git repo."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.planning = os.path.join(self.root, PLAN)
        self.impl = os.path.join(self.root, IMPL)
        self.state = os.path.join(self.impl, "state")
        os.makedirs(self.planning)
        os.makedirs(self.state)

    def path(self, rel):
        return os.path.join(self.root, rel)

    def write(self, rel, text):
        p = self.path(rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if isinstance(text, bytes):
            with open(p, "wb") as fh:
                fh.write(text)
        else:
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(text)
        return p

    def read(self, rel):
        with open(self.path(rel), encoding="utf-8") as fh:
            return fh.read()

    def sa(self, *args, spec_paths=None, planning=None):
        g = ["--project-root", self.root, "--planning-root", planning or self.planning,
             "--impl-root", self.impl, "--state-root", self.state, "--pm-status", PM]
        if spec_paths is not None:
            g += ["--spec-paths", json.dumps(spec_paths)]
        return subprocess.run([sys.executable, SCRIPT, *g, *args], capture_output=True,
                              text=True, env={**os.environ, **GIT_ENV}, cwd=self.root)

    def pm(self, *args):
        return subprocess.run([sys.executable, PM, *args], capture_output=True, text=True,
                              env={**os.environ, **GIT_ENV})

    def git(self, *args, check=True):
        r = subprocess.run(["git", "-C", self.root, *args], capture_output=True, text=True,
                           env={**os.environ, **GIT_ENV})
        if check and r.returncode != 0:
            raise AssertionError(f"git {' '.join(args)}: {r.stderr}")
        return r.stdout

    def init_git(self):
        self.git("init", "-q", "-b", "main")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "init")

    def index(self):
        return self.read(f"{IMPL}/spec/spec-index.md")


class TestBuild(Project):
    def test_indexes_headings_anchors_ranges_and_summaries(self):
        self.write(ARCH_REL, ARCH)
        r = self.sa("build")
        self.assertEqual(r.returncode, 0, r.stderr)
        idx = self.index()
        self.assertTrue(idx.startswith("# Spec index — generated by spec-align.py; do not edit\n"))
        self.assertIn(f"## architecture · {ARCH_REL}", idx)
        self.assertIn(f"- {ARCH_REL}#architecture — Architecture: Intro paragraph. (L1–23)", idx)
        self.assertIn(f"- {ARCH_REL}#data-model — Data model: Orders live in Postgres, one row "
                      f"per order. (L5–8)", idx)
        self.assertIn(f"- {ARCH_REL}#order-api — Order API: POST /orders accepts a body. (L9–16)",
                      idx)
        self.assertIn(f"- {ARCH_REL}#data-model-1 — Data model: Duplicate title section. (L17–23)",
                      idx)
        self.assertIn(f"- {ARCH_REL}#auth-v2-beta — Auth: v2 (beta): OIDC via the gateway. "
                      f"(L21–23)", idx)
        self.assertNotIn("not-a-heading", idx)
        self.assertRegex(idx.splitlines()[1],
                         r"^# inputs-sha256: [0-9a-f]{64}  ·  bytes: [\d,]+  ·  specs: 1  ·  "
                         r"sections: 5$")
        self.assertEqual(idx.splitlines()[2], "# spec-paths: []")

    def test_setext_heading_and_deep_headings_not_listed(self):
        self.write(f"{PLAN}/system-design.md",
                   "Setext\n======\n\nBody.\n\n#### Deep\n\nToo deep.\n")
        self.assertEqual(self.sa("build").returncode, 0)
        idx = self.index()
        self.assertIn(f"{PLAN}/system-design.md#setext — Setext: Body.", idx)
        self.assertNotIn("#deep", idx)

    def test_kinds_and_precedence(self):
        self.write(f"{PLAN}/ux-spec.md", "# UX\n\nScreens.\n")
        self.write(f"{PLAN}/prd.md", "# PRD\n\nGoals.\n")
        self.write(f"{PLAN}/epics.md", "# Epics\n\nList.\n")
        self.write(f"{PLAN}/notes.md", "# Notes\n\nNot a spec.\n")
        self.assertEqual(self.sa("build").returncode, 0)
        idx = self.index()
        self.assertIn(f"## ux · {PLAN}/ux-spec.md", idx)
        self.assertIn(f"## prd · {PLAN}/prd.md", idx)
        self.assertIn(f"## epics · {PLAN}/epics.md", idx)
        self.assertNotIn("notes.md", idx)

    def test_sharded_directory_is_indexed_whole(self):
        self.write(f"{PLAN}/prd/index.md", "# PRD\n\nOverview.\n")
        self.write(f"{PLAN}/prd/goals.md", "# Goals\n\nShip it.\n")
        self.assertEqual(self.sa("build").returncode, 0)
        idx = self.index()
        self.assertIn(f"## prd · {PLAN}/prd/goals.md", idx)
        self.assertIn(f"{PLAN}/prd/goals.md#goals — Goals: Ship it.", idx)

    def test_same_title_in_two_files_is_unsuffixed_in_each(self):
        self.write(ARCH_REL, ARCH)
        self.write(f"{PLAN}/tech-design.md", "# Tech\n\n## Data model\n\nSecond file.\n")
        self.assertEqual(self.sa("build").returncode, 0)
        self.assertIn(f"{PLAN}/tech-design.md#data-model — ", self.index())

    def test_non_utf8_spec_is_skipped_not_fatal(self):
        self.write(ARCH_REL, ARCH)
        self.write(f"{PLAN}/architecture-legacy.md", b"# Old\n\xff\xfe\n")
        r = self.sa("build")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"- skipped: {PLAN}/architecture-legacy.md (not UTF-8)", self.index())

    def test_empty_project(self):
        r = self.sa("build")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("no spec docs found", self.index())

    def test_if_stale_leaves_a_fresh_index_untouched(self):
        self.write(ARCH_REL, ARCH)
        self.assertEqual(self.sa("build").returncode, 0)
        p = self.path(f"{IMPL}/spec/spec-index.md")
        before = os.stat(p).st_mtime_ns
        time.sleep(0.02)
        r = self.sa("build", "--if-stale")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("fresh", r.stdout)
        self.assertEqual(os.stat(p).st_mtime_ns, before)
        self.write(ARCH_REL, ARCH + "\n## Events\n\nKafka.\n")
        self.assertEqual(self.sa("build", "--if-stale").returncode, 0)
        self.assertIn("#events", self.index())

    def test_check_reports_stale_and_writes_nothing(self):
        self.write(ARCH_REL, ARCH)
        r = self.sa("build", "--check")
        self.assertEqual(r.returncode, 1)
        self.assertFalse(os.path.exists(self.path(f"{IMPL}/spec/spec-index.md")))
        self.sa("build")
        self.assertEqual(self.sa("build", "--check").returncode, 0)

    def test_spec_paths_override_is_recorded_and_reused(self):
        self.write(ARCH_REL, ARCH)
        self.write("docs/architecture.md", "# Arch\n\n## Events\n\nKafka.\n")
        r = self.sa("build", spec_paths=["docs/*.md"])
        self.assertEqual(r.returncode, 0, r.stderr)
        idx = self.index()
        self.assertIn("docs/architecture.md#events", idx)
        self.assertNotIn(ARCH_REL, idx)
        self.assertEqual(idx.splitlines()[2], '# spec-paths: ["docs/*.md"]')
        # A caller without --spec-paths (doctor) reuses the recorded list: still fresh.
        self.assertEqual(self.sa("build", "--check").returncode, 0)
        # An explicit empty list means discovery again: stale.
        self.assertEqual(self.sa("build", "--check", spec_paths=[]).returncode, 1)

    def test_bad_spec_paths_json_is_refused(self):
        r = subprocess.run([sys.executable, SCRIPT, "--project-root", self.root, "--impl-root",
                            self.impl, "--spec-paths", "{not json", "build"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("--spec-paths", r.stderr)

    def test_index_never_indexes_itself(self):
        self.write(f"_bmad-output/architecture.md", ARCH)
        parent = os.path.join(self.root, "_bmad-output")
        self.assertEqual(self.sa("build", planning=parent).returncode, 0)
        self.assertEqual(self.sa("build", planning=parent).returncode, 0)
        self.assertNotIn("spec-index.md", self.index())

    def test_size_warning(self):
        body = "".join(f"## Section {i}\n\nThis sentence pads the index entry to a realistic "
                       f"length for the size warning.\n\n" for i in range(400))
        self.write(ARCH_REL, "# Big\n\n" + body)
        r = self.sa("build")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("WARN spec index is", r.stderr)


if __name__ == "__main__":
    unittest.main()
````

Run: SA-TEST
Expected: FAIL/ERROR (`spec-align.py` does not exist; every subprocess exits 2 with
"can't open file").

- [ ] **Step 2: Create `skills/_shared/spec-align.py`**

````python
#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "markdown-it-py>=3",
#   "mdit-py-plugins>=0.4",
#   "ruamel.yaml>=0.18",
#   "unidiff>=0.7",
#   "tenacity>=8",
# ]
# ///
"""
spec-align.py -- keeps a project's specs and its implementation in step, for l3io-pm.

Subcommands: build, check-pointers, sections, disposition, check-dispositions, adrs,
check-links, lease, sync-plan, propose, commit, reject, check-stale, migrate-adrs.

It never calls a model. Each spec-alignment point in l3io-pm-execute runs one of these
first, and the result decides whether an agent is dispatched at all.

Global flags come before the subcommand: --project-root (required), --planning-root,
--impl-root, --state-root (default <impl-root>/state), --pm-status, --spec-paths JSON.

Exit codes: 0 ok; 1 a report-mode check found problems; 2 a gate refused, or bad input;
5 the spec-sync lease is held by another owner.

Design: docs/superpowers/specs/2026-09-11-spec-alignment-design.md in the package repo;
decisions: docs/adr/0004-agents-edit-architecture-specs.md, docs/adr/0005-one-adr-home.md.
"""
import argparse
import fnmatch
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

INDEX_FORMAT = 1
INDEX_REL = os.path.join("spec", "spec-index.md")
INDEX_MAX_LEVEL = 3
SUMMARY_CHARS = 100
SIZE_WARN_BYTES = 16384
HEADER_TITLE = "# Spec index — generated by spec-align.py; do not edit"
DIGEST_RE = re.compile(r"^# inputs-sha256: ([0-9a-f]{64})\b")
SPEC_PATHS_RE = re.compile(r"^# spec-paths: (.*)$")

# Spec kinds in precedence order: a name matching several kinds takes the first. The
# architecture, ux and prd patterns are copied verbatim from
# l3io-util-doctor/steps/layout-cleanup.md heuristic 5 -- check-docs check 13 compares them.
KINDS = (
    ("architecture", ("*architecture*", "*arch-spec*", "*system-design*", "*tech-design*")),
    ("ux", ("*ux-spec*", "*ux-design*", "*wireframe*", "*mockup*", "*ui-spec*")),
    ("prd", ("*requirements*", "*prd*", "*brief*", "*spec*")),
    ("epics", ("*epics*",)),
)
KIND_ORDER = {k: i for i, (k, _) in enumerate(KINDS)}


class SAError(Exception):
    """A refusal: `code` is the exit status; the message goes to stderr."""

    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


class Ctx:
    """The paths every subcommand resolves against, from the global flags."""

    def __init__(self, a):
        self.project = os.path.abspath(a.project_root)
        self.planning = os.path.abspath(a.planning_root) if a.planning_root else None
        self.impl = os.path.abspath(a.impl_root) if a.impl_root else None
        self.state_root = (os.path.abspath(a.state_root) if a.state_root
                           else (os.path.join(self.impl, "state") if self.impl else None))
        self.pm_status = a.pm_status or None
        self.spec_paths_arg = None
        if a.spec_paths is not None:
            try:
                value = json.loads(a.spec_paths)
            except ValueError as e:
                raise SAError(2, f"--spec-paths is not JSON: {e}")
            if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
                raise SAError(2, "--spec-paths must be a JSON list of strings")
            self.spec_paths_arg = value

    def need(self, *what):
        flags = {"impl": ("--impl-root", self.impl), "state": ("--state-root", self.state_root),
                 "pm": ("--pm-status", self.pm_status)}
        missing = [flags[w][0] for w in what if not flags[w][1]]
        if missing:
            raise SAError(2, f"this subcommand needs {', '.join(missing)}")

    def rel(self, p):
        return os.path.relpath(os.path.abspath(p), self.project).replace(os.sep, "/")

    def abs(self, p):
        return p if os.path.isabs(p) else os.path.join(self.project, p)

    def index_path(self):
        self.need("impl")
        return os.path.join(self.impl, INDEX_REL)


def _under(path, root):
    path, root = os.path.abspath(path), os.path.abspath(root)
    return path == root or path.startswith(root + os.sep)


def read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def atomic_write(path, text):
    """Write via a sibling temp file + os.replace, so a reader never sees half a file."""
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".spec-align-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# -- markdown ------------------------------------------------------------------------------ #

_MD = None


def md():
    """One parser for every read. Anchors are computed over every heading level, so duplicate
    suffixes (-1, -2) count the same headings GitHub does; the index lists H1-H3 only."""
    global _MD
    if _MD is None:
        from markdown_it import MarkdownIt
        from mdit_py_plugins.anchors import anchors_plugin
        _MD = MarkdownIt("commonmark").enable("table").use(anchors_plugin,
                                                           min_level=1, max_level=6)
    return _MD


class Section:
    __slots__ = ("level", "title", "anchor", "start", "end", "summary")

    def __init__(self, level, title, anchor, start, end, summary):
        self.level, self.title, self.anchor = level, title, anchor
        self.start, self.end, self.summary = start, end, summary


def first_sentence(text):
    s = " ".join(text.split())
    m = re.match(r"(.+?[.!?])(?:\s|$)", s)
    if m:
        s = m.group(1)
    return s if len(s) <= SUMMARY_CHARS else s[:SUMMARY_CHARS - 1].rstrip() + "…"


def parse_sections(text):
    """Every heading as a Section. A section runs from its heading line to the line before
    the next heading of the same or a higher level (1-based, inclusive)."""
    tokens = md().parse(text)
    nlines = len(text.splitlines())
    heads = [(i, int(t.tag[1:]), t.attrs.get("id"), t.map[0], tokens[i + 1].content.strip())
             for i, t in enumerate(tokens) if t.type == "heading_open"]
    out = []
    for n, (i, level, anchor, line0, title) in enumerate(heads):
        end = nlines
        for _, level2, _, line2, _ in heads[n + 1:]:
            if level2 <= level:
                end = line2
                break
        stop = heads[n + 1][0] if n + 1 < len(heads) else len(tokens)
        summary = ""
        for j in range(i + 3, stop):
            if (tokens[j].type == "paragraph_open" and j + 1 < stop
                    and tokens[j + 1].type == "inline"):
                summary = first_sentence(tokens[j + 1].content)
                break
        out.append(Section(level, title, anchor, line0 + 1, max(end, line0 + 1), summary))
    return out


# -- discovery and the catalog -------------------------------------------------------------- #

def kind_of(name):
    low = name.lower()
    for kind, patterns in KINDS:
        if any(fnmatch.fnmatchcase(low, p) for p in patterns):
            return kind
    return None


def _kind_for_path(p):
    """A file takes its own name's kind, else its directory's (a sharded doc's section)."""
    return kind_of(os.path.basename(p)) or kind_of(os.path.basename(os.path.dirname(p)))


def recorded_spec_paths(ctx):
    """The spec-paths list the current index was built with, or None."""
    if not ctx.impl:
        return None
    p = os.path.join(ctx.impl, INDEX_REL)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as fh:
        for n, line in enumerate(fh):
            if n > 4:
                break
            m = SPEC_PATHS_RE.match(line.rstrip("\n"))
            if m:
                try:
                    value = json.loads(m.group(1))
                except ValueError:
                    return None
                return value if isinstance(value, list) else None
    return None


def effective_spec_paths(ctx):
    """--spec-paths when given; else the list the index records (so doctor, which cannot read
    pm-execute's customize.toml, checks the same spec set); else [] (discover)."""
    if ctx.spec_paths_arg is not None:
        return list(ctx.spec_paths_arg)
    rec = recorded_spec_paths(ctx)
    return rec if rec is not None else []


def discover(ctx):
    """[(project-relative path, kind)], sorted. spec_paths replaces discovery entirely."""
    found = {}
    skip = os.path.join(ctx.impl, "spec") if ctx.impl else None      # never index the index
    patterns = effective_spec_paths(ctx)
    if patterns:
        for pat in patterns:
            for hit in glob.glob(os.path.join(ctx.project, pat), recursive=True):
                if os.path.isfile(hit) and hit.endswith(".md") and not (skip and _under(hit, skip)):
                    found[ctx.rel(hit)] = _kind_for_path(hit) or "other"
    elif ctx.planning and os.path.isdir(ctx.planning):
        for dirpath, dirnames, filenames in os.walk(ctx.planning):
            if skip and _under(dirpath, skip):
                dirnames[:] = []
                continue
            keep = []
            for d in sorted(dirnames):
                full = os.path.join(dirpath, d)
                kind = kind_of(d)
                if skip and _under(full, skip):
                    continue
                if kind and os.path.isfile(os.path.join(full, "index.md")):
                    for sub_dir, _, sub_files in os.walk(full):
                        for f in sub_files:
                            if f.endswith(".md"):
                                found[ctx.rel(os.path.join(sub_dir, f))] = kind
                else:
                    keep.append(d)
            dirnames[:] = keep
            for f in filenames:
                if f.endswith(".md"):
                    kind = kind_of(f)
                    if kind:
                        found[ctx.rel(os.path.join(dirpath, f))] = kind
    return sorted(found.items())


def load_catalog(ctx):
    """{rel: {"kind", "sections", "anchors", "error", "sha"}} for every discovered spec."""
    cat = {}
    for rel, kind in discover(ctx):
        e = {"kind": kind, "sections": [], "anchors": {}, "error": None, "sha": ""}
        try:
            with open(ctx.abs(rel), "rb") as fh:
                raw = fh.read()
        except OSError as exc:
            e["error"], e["sha"] = f"unreadable: {exc.strerror or exc}", "unreadable"
        else:
            e["sha"] = hashlib.sha256(raw).hexdigest()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                e["error"] = "not UTF-8"
            else:
                e["sections"] = parse_sections(text)
                e["anchors"] = {s.anchor: s for s in e["sections"]}
        cat[rel] = e
    return cat


def inputs_hash(ctx, cat):
    h = hashlib.sha256()
    h.update(f"format={INDEX_FORMAT}\n"
             f"spec-paths={json.dumps(effective_spec_paths(ctx))}\n".encode())
    for rel in sorted(cat):
        h.update(f"{rel}\0{cat[rel]['sha']}\n".encode())
    return h.hexdigest()


def render_index(ctx, cat, digest):
    body, skipped, n_specs, n_sections = [], [], 0, 0
    for rel in sorted(cat, key=lambda r: (KIND_ORDER.get(cat[r]["kind"], 99), r)):
        e = cat[rel]
        if e["error"]:
            skipped.append(f"- skipped: {rel} ({e['error']})")
            continue
        n_specs += 1
        body.append(f"## {e['kind']} · {rel}")
        for s in e["sections"]:
            if s.level > INDEX_MAX_LEVEL:
                continue
            n_sections += 1
            summary = f": {s.summary}" if s.summary else ""
            body.append(f"- {rel}#{s.anchor} — {s.title}{summary} (L{s.start}–{s.end})")
    if skipped:
        body += ["## skipped", *skipped]
    if not cat:
        body.append("no spec docs found")
    text = "\n".join(body) + "\n"
    nbytes = len(text.encode("utf-8"))            # R12: the body below the header
    header = (f"{HEADER_TITLE}\n"
              f"# inputs-sha256: {digest}  ·  bytes: {nbytes:,}  ·  specs: {n_specs}  ·  "
              f"sections: {n_sections}\n"
              f"# spec-paths: {json.dumps(effective_spec_paths(ctx))}\n")
    return header + text, nbytes, n_specs, n_sections


def index_digest(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh):
            if n > 4:
                break
            m = DIGEST_RE.match(line)
            if m:
                return m.group(1)
    return None


def cmd_build(ctx, a):
    path = ctx.index_path()
    cat = load_catalog(ctx)
    digest = inputs_hash(ctx, cat)
    fresh = index_digest(path) == digest
    if a.check:
        if fresh:
            print(f"OK build --check: {ctx.rel(path)} is fresh")
            return 0
        print(f"STALE {ctx.rel(path)}: the specs changed since it was built "
              f"(or it does not exist) -- run build")
        return 1
    if a.if_stale and fresh:
        print(f"OK build: {ctx.rel(path)} is fresh; not rewritten")
        return 0
    text, nbytes, n_specs, n_sections = render_index(ctx, cat, digest)
    atomic_write(path, text)
    if nbytes > SIZE_WARN_BYTES:
        sys.stderr.write(f"WARN spec index is {nbytes:,} bytes (> {SIZE_WARN_BYTES:,}); every "
                         f"reviewer reads it -- consider trimming (spec §8)\n")
    print(f"OK build: wrote {ctx.rel(path)} ({n_specs} spec(s), {n_sections} section(s), "
          f"{nbytes:,} bytes)")
    return 0


# -- CLI -------------------------------------------------------------------------------------- #

def build_parser():
    p = argparse.ArgumentParser(prog="spec-align.py",
                                description="Spec/implementation alignment for l3io-pm.")
    p.add_argument("--project-root", required=True)
    p.add_argument("--planning-root", default="")
    p.add_argument("--impl-root", default="")
    p.add_argument("--state-root", default="", help="default: <impl-root>/state")
    p.add_argument("--pm-status", default="", help="path to pm-status.py")
    p.add_argument("--spec-paths", default=None,
                   help="JSON list of project-relative paths/globs; replaces discovery")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="build the spec index (no LLM)")
    g = b.add_mutually_exclusive_group()
    g.add_argument("--if-stale", action="store_true", help="rewrite only when the specs changed")
    g.add_argument("--check", action="store_true", help="exit 1 when stale; write nothing")
    b.set_defaults(func=cmd_build)

    # Later tasks register their subcommands above this line.
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        return a.func(Ctx(a), a)
    except SAError as e:
        sys.stderr.write(f"spec-align.py {a.cmd}: {e}\n")
        return e.code


if __name__ == "__main__":
    sys.exit(main())
````

Make it executable: `chmod +x skills/_shared/spec-align.py`.

- [ ] **Step 3: Run the tests and confirm they pass**

Run: SA-TEST
Expected: `OK` (13 tests), and no leak error. If
`test_indexes_headings_anchors_ranges_and_summaries` fails only on an anchor spelling,
**print the real anchors** with
`uv run -q --with markdown-it-py --with mdit-py-plugins python3 -c "..."` and fix the
**test's expectation** only if the plugin's slug is GitHub-compatible. The spec probe of
2026-09-11 produced `data-model--auth`, `data-model-1`, `setext-h2` and `api-v2-beta`.

- [ ] **Step 4: Non-hollow proof.** Comment out the `if skip and _under(dirpath, skip):`
  block, and the `if skip and _under(full, skip): continue` line, in `discover`. Rerun
  `TestBuild.test_index_never_indexes_itself`. It must FAIL. Restore both.

- [ ] **Step 5: Add the sync group.** In `scripts/sync-shared-scripts.mjs`:

(a) In the header comment's "Shared files:" list, after the `pm-status.py (no tests)` entry:

```js
//   spec-align.py → scripts/ in l3io-pm-execute (arch gate, story prep, closures) and
//   l3io-util-doctor (health Checks 15-19, triage's spec pass, migrate-adrs); shared because
//   it has two consumers (ADR-0001), run from each skill's own copy, never self-installed
```

(b) After the `pmStatusOnlyFiles` declaration:

```js
// spec-align.py: two consumers (pm-execute, util-doctor), so shared per ADR-0001. Each runs
// its own copy via `uv run {skill-root}/scripts/spec-align.py`; its test suite stays in
// skills/_shared/tests/ like every other suite.
const specAlignFiles = [
  { src: path.join(sharedDir, "spec-align.py"), rel: path.join("scripts", "spec-align.py") },
];
```

(c) In `syncGroups`, as the last entry:

```js
  // spec-align.py into its two consumers
  { files: specAlignFiles, dirs: [...newPmExecuteDirs, ...newUtilDoctorDirs] },
```

Run: `npm run sync:scripts && node scripts/write-payload-manifest.mjs && npm run check:scripts && npm run check:manifest`
Expected: two `Synced skills/…/scripts/spec-align.py` lines; both checks exit 0.

- [ ] **Step 6: Add the CI step.** In `.github/workflows/checks.yml`, directly after the
  `drift-report.py unit tests` step:

```yaml
    - name: spec-align.py unit tests
      run: uv run -q --with 'markdown-it-py>=3' --with 'mdit-py-plugins>=0.4' --with 'ruamel.yaml>=0.18' --with 'unidiff>=0.7' --with 'tenacity>=8' python3 skills/_shared/tests/test-spec-align.py
```

- [ ] **Step 7: Run the gates and commit**

Run: `npm run check:scripts && npm run check:docs && npm run check:manifest && npm run check:version && npm run test:scripts`
Expected: every command exits 0.

```bash
git add skills/_shared/spec-align.py skills/_shared/tests/test-spec-align.py \
  scripts/sync-shared-scripts.mjs .github/workflows/checks.yml \
  skills/l3io-pm-execute/scripts/spec-align.py skills/l3io-util-doctor/scripts/spec-align.py \
  skills/l3io-pm-execute/payload-manifest.json skills/l3io-util-doctor/payload-manifest.json
git commit -s -F - <<'EOF'
feat(l3io-pm): spec-align.py with the spec index (build)

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01E4PU5edGnYd8Dc12LbhDYY
EOF
```

---
### Task 5: `check-pointers` and `sections` (provenance)

**Files:**
- Modify: `skills/_shared/spec-align.py`. Add a pointer block after `cmd_build`, and two
  parser blocks above the marker line.
- Modify: `skills/_shared/tests/test-spec-align.py`. Add a class before
  `if __name__ == "__main__":`.
- Generated: the two `scripts/spec-align.py` copies and their manifests.

**Interfaces:**
- **Consumes:** `load_catalog`, `md`, `Ctx`, `SAError` from Task 4.
- **Produces:**
  - Constants: `DIMENSIONS` (the six names, in order), `TAC_HEADING`, `SPEC_LINE_RE`,
    `PTR_RE`.
  - `story_dimensions(text) -> (found: bool, {casefolded name: (h3_line, [(lineno, line)])})`,
    which excludes lines inside fences.
  - `check_story(cat, text) -> None | [(lineno, msg)]`, where `None` means pre-provenance.
  - `resolve_pointer(cat, value) -> ((path, anchor, Section, kind) | None, why)`.
  - `story_pointers(text) -> [(lineno, dim, value)]`.
  - `all_story_files(ctx) -> [abs path]`.
- The `DIMENSIONS` tuple is parsed by check-docs check 13 (Task 18): keep it a literal tuple
  of double-quoted strings, one per line.

- [ ] **Step 1: Write the failing tests.** Add this to `test-spec-align.py` before the
  `__main__` block:

````python
DIMS = ["Interface contracts", "Error and edge case handling", "Observability requirements",
        "Security considerations", "Testability approach", "Existing-library check"]


def story(dims, head="# E001-S01-001: A story\n\nSome prose.\n"):
    parts = [head, "## Technical acceptance criteria\n"]
    for name in DIMS:
        if name in dims:
            parts.append(f"### {name}\n\n{dims[name]}\n")
    parts.append("## Files in scope\n\n- `src/a.py` — the module\n")
    return "\n".join(parts)


def full_story(**overrides):
    dims = {d: f"Content for {d}.\nSpec: {ARCH_REL}#data-model" for d in DIMS}
    for k, v in overrides.items():
        dims[k.replace("_", " ")] = v
    return story(dims)


STORY_REL = f"{IMPL}/epic-001/sprint-01/stories/E001-S01-001.md"


class TestPointers(Project):
    def setUp(self):
        super().setUp()
        self.write(ARCH_REL, ARCH)

    def check(self, text, rel=STORY_REL):
        self.write(rel, text)
        return self.sa("check-pointers", "--story", self.path(rel))

    def test_complete_story_passes(self):
        r = self.check(full_story())
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_missing_dimension_blocks(self):
        dims = {d: f"x\nSpec: {ARCH_REL}#data-model" for d in DIMS if d != DIMS[2]}
        r = self.check(story(dims))
        self.assertEqual(r.returncode, 2)
        self.assertIn("Observability requirements: missing dimension", r.stderr)

    def test_not_applicable_dimension_needs_no_pointer(self):
        r = self.check(full_story(Security_considerations="N/A — internal batch job, no input."))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_applicable_dimension_without_pointer_blocks(self):
        r = self.check(full_story(Testability_approach="Unit tests at the service boundary."))
        self.assertEqual(r.returncode, 2)
        self.assertIn("Testability approach: no Spec: line", r.stderr)

    def test_spec_none_with_reason_passes(self):
        r = self.check(full_story(
            Observability_requirements="Log each order.\nSpec: none — no observability section"))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_spec_none_without_reason_blocks(self):
        r = self.check(full_story(Observability_requirements="Log it.\nSpec: none"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("needs a reason", r.stderr)

    def test_spec_none_plus_pointer_blocks(self):
        r = self.check(full_story(Observability_requirements=(
            f"Log it.\nSpec: none — nothing\nSpec: {ARCH_REL}#data-model")))
        self.assertEqual(r.returncode, 2)
        self.assertIn("must be the only Spec: line", r.stderr)

    def test_several_pointers_on_one_dimension_pass(self):
        r = self.check(full_story(Interface_contracts=(
            f"POST /orders.\nSpec: {ARCH_REL}#order-api\n- Spec: {ARCH_REL}#data-model-1")))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_unknown_path_and_anchor_block(self):
        r = self.check(full_story(Interface_contracts=(
            "x\nSpec: docs/nowhere.md#a\nSpec: " + ARCH_REL + "#no-such-anchor")))
        self.assertEqual(r.returncode, 2)
        self.assertIn("docs/nowhere.md is not in the spec index", r.stderr)
        self.assertIn("has no anchor #no-such-anchor", r.stderr)

    def test_spec_line_inside_a_fence_does_not_count(self):
        r = self.check(full_story(Interface_contracts=(
            f"Example:\n\n```\nSpec: {ARCH_REL}#data-model\n```\n")))
        self.assertEqual(r.returncode, 2)
        self.assertIn("Interface contracts: no Spec: line", r.stderr)

    def test_pre_provenance_blocks_story_mode(self):
        r = self.check("# Old story\n\nInterface: POST /x.\n")
        self.assertEqual(r.returncode, 2)
        self.assertIn("pre-provenance", r.stderr)

    def test_all_mode_informs_on_pre_provenance_and_reports_broken(self):
        self.write(STORY_REL, "# Old story\n\nNo ACs.\n")
        r = self.sa("check-pointers", "--all")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("INFO pre-provenance", r.stdout)
        self.write(f"{IMPL}/epic-001/sprint-02/stories/E001-S02-001.md",
                   full_story(Interface_contracts=f"x\nSpec: {ARCH_REL}#gone"))
        r = self.sa("check-pointers", "--all")
        self.assertEqual(r.returncode, 1)
        self.assertIn("E001-S02-001.md", r.stderr)

    def test_sections_dedupes_and_prints_ranges(self):
        a = self.write(STORY_REL, full_story(Interface_contracts=f"x\nSpec: {ARCH_REL}#order-api"))
        b = self.write(f"{IMPL}/epic-001/sprint-01/stories/E001-S01-002.md", full_story())
        r = self.sa("sections", "--stories", a, b)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), [f"{ARCH_REL}#data-model L5–8",
                                                 f"{ARCH_REL}#order-api L9–16"])
````

Run: SA-TEST
Expected: the new tests fail (argparse: `invalid choice: 'check-pointers'`, exit 2 where 0 or
1 was expected); `TestBuild` still passes.

- [ ] **Step 2: Implement.** In `spec-align.py`, after `cmd_build`:

````python
# -- provenance pointers ---------------------------------------------------------------------- #

# The six technical-AC dimensions, in the order the enrichment prompt writes them
# (steps/sprint/step-02-story-prep.md §2). check-docs check 13 compares this tuple with the
# prompt's layout block; keep it a literal, one name per line.
DIMENSIONS = (
    "Interface contracts",
    "Error and edge case handling",
    "Observability requirements",
    "Security considerations",
    "Testability approach",
    "Existing-library check",
)
TAC_HEADING = "Technical acceptance criteria"
SPEC_LINE_RE = re.compile(r"^\s*(?:[-*]\s+)?Spec:\s*(.*?)\s*$")
NONE_RE = re.compile(r"^none\s*(?:—|--|-)\s*(\S.*)$", re.I)
PTR_RE = re.compile(r"^([^\s#`]+\.md)#([^\s#`]+)$")
NA_RE = re.compile(r"^\s*N/A\s*(?:—|--|-)\s*\S")


def story_dimensions(text):
    """(found, {casefolded dimension: (h3 line, [(lineno, line), ...])}) under the story's
    `## Technical acceptance criteria`. Lines inside fenced or indented code are dropped."""
    tokens = md().parse(text)
    lines = text.splitlines()
    fenced = set()
    for t in tokens:
        if t.type in ("fence", "code_block") and t.map:
            fenced.update(range(t.map[0], t.map[1]))
    heads = [(t.map[0], int(t.tag[1:]), tokens[i + 1].content.strip())
             for i, t in enumerate(tokens) if t.type == "heading_open"]
    tac = next((ln for ln, lvl, title in heads
                if lvl == 2 and title.casefold() == TAC_HEADING.casefold()), None)
    if tac is None:
        return False, {}
    tac_end = next((ln for ln, lvl, _ in heads if ln > tac and lvl <= 2), len(lines))
    h3 = [(ln, title) for ln, lvl, title in heads if tac < ln < tac_end and lvl == 3]
    dims = {}
    for n, (ln, title) in enumerate(h3):
        end = h3[n + 1][0] if n + 1 < len(h3) else tac_end
        body = [(i + 1, lines[i]) for i in range(ln + 1, end) if i not in fenced]
        dims[title.casefold()] = (ln + 1, body)
    return True, dims


def resolve_pointer(cat, value):
    """((path, anchor, Section, kind), None) or (None, why)."""
    m = PTR_RE.match(value.strip().strip("`"))
    if not m:
        return None, f"not a pointer: {value!r} (expected <path>#<anchor>)"
    path, anchor = m.groups()
    e = cat.get(path)
    if e is None:
        return None, f"{path} is not in the spec index"
    if e["error"]:
        return None, f"{path} is unreadable ({e['error']})"
    s = e["anchors"].get(anchor)
    if s is None:
        return None, f"{path} has no anchor #{anchor}"
    return (path, anchor, s, e["kind"]), None


def story_pointers(text):
    """[(lineno, dimension, value)] for every Spec: line under a known dimension."""
    found, dims = story_dimensions(text)
    out = []
    for dim in DIMENSIONS:
        for n, line in (dims.get(dim.casefold()) or (0, []))[1]:
            m = SPEC_LINE_RE.match(line)
            if m:
                out.append((n, dim, m.group(1)))
    return out


def check_story(cat, text):
    """None when the story has no AC section (pre-provenance), else a list of problems."""
    found, dims = story_dimensions(text)
    if not found:
        return None
    errs = []
    for dim in DIMENSIONS:
        d = dims.get(dim.casefold())
        if d is None:
            errs.append((0, f"{dim}: missing dimension (### {dim})"))
            continue
        h3_line, body = d
        content = [(n, line) for n, line in body if line.strip()]
        if not content:
            errs.append((h3_line, f"{dim}: empty"))
            continue
        if NA_RE.match(content[0][1]):
            continue
        specs = [(n, SPEC_LINE_RE.match(line).group(1)) for n, line in content
                 if SPEC_LINE_RE.match(line)]
        if not specs:
            errs.append((h3_line, f"{dim}: no Spec: line -- end it with `Spec: <path>#<anchor>` "
                                  f"or `Spec: none — <reason>`"))
            continue
        nones = [(n, v) for n, v in specs if v.lower().startswith("none")]
        if nones:
            if len(specs) > 1:
                errs.append((nones[0][0], f"{dim}: `Spec: none` must be the only Spec: line"))
            elif not NONE_RE.match(nones[0][1]):
                errs.append((nones[0][0], f"{dim}: `Spec: none` needs a reason after the dash"))
            continue
        for n, v in specs:
            hit, why = resolve_pointer(cat, v)
            if hit is None:
                errs.append((n, f"{dim}: {why}"))
    return errs


def all_story_files(ctx):
    ctx.need("impl")
    return sorted(glob.glob(os.path.join(ctx.impl, "epic-*", "sprint-*", "stories", "*.md")))


def cmd_check_pointers(ctx, a):
    cat = load_catalog(ctx)
    stories = all_story_files(ctx) if a.all else [ctx.abs(s) for s in a.story]
    broken, pre = 0, []
    for s in stories:
        rel = ctx.rel(s)
        try:
            text = read_text(s)
        except (OSError, UnicodeDecodeError) as e:
            sys.stderr.write(f"{rel}: unreadable ({e})\n")
            broken += 1
            continue
        errs = check_story(cat, text)
        if errs is None:
            pre.append(rel)
            if not a.all:
                sys.stderr.write(f"{rel}: pre-provenance: no '## {TAC_HEADING}' section -- "
                                 f"treat it as thin and enrich it\n")
                broken += 1
            continue
        for n, msg in errs:
            sys.stderr.write(f"{rel}:{n}: {msg}\n")
        broken += bool(errs)
    if a.all:
        for rel in pre:
            print(f"INFO pre-provenance: {rel}")
        if broken:
            print(f"check-pointers --all: {broken} story file(s) with broken pointers")
            return 1
        print(f"OK check-pointers --all: {len(stories)} story file(s), "
              f"{len(pre)} pre-provenance")
        return 0
    if broken:
        return 2
    print(f"OK check-pointers: {len(stories)} story file(s)")
    return 0


def cmd_sections(ctx, a):
    cat = load_catalog(ctx)
    seen = {}
    for s in a.stories:
        for _, _, value in story_pointers(read_text(ctx.abs(s))):
            hit, _ = resolve_pointer(cat, value)
            if hit is not None:
                seen[(hit[0], hit[1])] = hit[2]
    for (path, anchor), sec in sorted(seen.items(), key=lambda kv: (kv[0][0], kv[1].start)):
        print(f"{path}#{anchor} L{sec.start}–{sec.end}")
    if not seen:
        print("(no resolvable pointers)")
    return 0
````

Parser blocks, directly above the marker line:

```python
    cp = sub.add_parser("check-pointers", help="provenance: every dimension's Spec: line")
    g = cp.add_mutually_exclusive_group(required=True)
    g.add_argument("--story", nargs="+", help="gate mode: exit 2 on any problem")
    g.add_argument("--all", action="store_true",
                   help="report mode over every story: exit 1 on broken pointers")
    cp.set_defaults(func=cmd_check_pointers)

    se = sub.add_parser("sections", help="the stories' pointers as de-duplicated line ranges")
    se.add_argument("--stories", nargs="+", required=True)
    se.set_defaults(func=cmd_sections)
```

- [ ] **Step 3: Run the tests and confirm they pass**

Run: SA-TEST
Expected: `OK` (26 tests).

- [ ] **Step 4: Non-hollow proof.** Remove `if i not in fenced` from `story_dimensions`, and
  rerun `test_spec_line_inside_a_fence_does_not_count`. It must FAIL. Restore it.

- [ ] **Step 5: Sync, run the gates, and commit.**
  - Run `npm run sync:scripts && node scripts/write-payload-manifest.mjs`, then the gate
    command from Task 4 Step 7.
  - Stage `skills/_shared/spec-align.py`, `skills/_shared/tests/test-spec-align.py`, both
    `scripts/spec-align.py` copies, and both manifests.
  - Commit with the subject
    `feat(l3io-pm): spec-align check-pointers and sections (story provenance)`.

---

### Task 6: `disposition` and `check-dispositions`

**Files:**
- Modify: `skills/_shared/spec-align.py`. Add a dispositions block after `cmd_sections`, and
  two parser blocks.
- Modify: `skills/_shared/tests/test-spec-align.py`.
- Generated: the copies and manifests.

**Interfaces:**
- **Consumes:** `resolve_pointer`, `load_catalog`, `atomic_write` and `read_text`.
- **Produces:**
  - Constants: `DISPOSITIONS`, `SPEC_DISPOSITIONS = ("spec-updated", "spec-proposal")`,
    `FINDING_ID_RE` (`AD-{n}` | `SD-{nn}-{n}`, per R1), `DISP_FILE = "drift-dispositions.yaml"`.
  - YAML helpers: `load_yaml(path)` and `dump_yaml(path, data)`, which are ruamel round-trip.
  - Tables: `md_tables(text) -> [[row cells]]`.
  - `review_findings(path) -> {id: {"severity", "title"}}`.
  - `load_dispositions(dpath, review_rel) -> CommentedMap{review, findings}`.
  - A disposition entry has the keys `severity`, `title`, `disposition`, `spec`, `adr`,
    `commit` and `issue`.

- [ ] **Step 1: Write the failing tests** (before `__main__`):

````python
REVIEW = """# Arch drift review

2 sentences of summary.

## Findings table

| # | Severity | Principle | Location | Finding | Remediation |
|---|----------|-----------|----------|---------|-------------|
| AD-1 | MAJOR | Core §1 | `src/a.py:1` | Orders bypass the repository | route via repo |
| AD-2 | MINOR | Core §7 | `src/b.py:2` | Naming | rename |
| AD-3 | BLOCKER | Core §2 | `src/c.py:3` | PRD says soft delete | use soft delete |
"""
EPIC_REVIEW_REL = f"{IMPL}/epic-003/epic-closure/arch-drift-review.md"
PRD_REL = f"{PLAN}/prd.md"
PRD = "# PRD\n\n## Deletion\n\nOrders are soft-deleted.\n"


class TestDispositions(Project):
    def setUp(self):
        super().setUp()
        self.write(ARCH_REL, ARCH)
        self.write(PRD_REL, PRD)
        self.review = self.write(EPIC_REVIEW_REL, REVIEW)

    def disp(self, fid, disposition, *extra):
        return self.sa("disposition", "--review", self.review, "--finding", fid,
                       "--disposition", disposition, *extra)

    def load(self):
        from ruamel.yaml import YAML
        with open(self.path(f"{IMPL}/epic-003/epic-closure/drift-dispositions.yaml"),
                  encoding="utf-8") as fh:
            return YAML(typ="safe").load(fh)

    def test_resolved_in_code_is_recorded(self):
        r = self.disp("AD-1", "resolved-in-code")
        self.assertEqual(r.returncode, 0, r.stderr)
        d = self.load()
        self.assertEqual(d["review"], EPIC_REVIEW_REL)
        self.assertEqual(d["findings"]["AD-1"]["severity"], "MAJOR")
        self.assertEqual(d["findings"]["AD-1"]["title"], "Orders bypass the repository")
        self.assertEqual(d["findings"]["AD-1"]["disposition"], "resolved-in-code")
        self.assertIsNone(d["findings"]["AD-1"]["commit"])

    def test_unknown_finding_is_refused(self):
        r = self.disp("AD-9", "resolved-in-code")
        self.assertEqual(r.returncode, 2)
        self.assertIn("AD-9 is not in the findings table", r.stderr)

    def test_spec_updated_on_architecture(self):
        r = self.disp("AD-1", "spec-updated", "--spec", f"{ARCH_REL}#order-api")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.load()["findings"]["AD-1"]["spec"], f"{ARCH_REL}#order-api")

    def test_spec_updated_on_a_prd_is_refused(self):
        r = self.disp("AD-3", "spec-updated", "--spec", f"{PRD_REL}#deletion")
        self.assertEqual(r.returncode, 2)
        self.assertIn("record spec-proposal instead", r.stderr)

    def test_spec_proposal_on_a_prd(self):
        r = self.disp("AD-3", "spec-proposal", "--spec", f"{PRD_REL}#deletion")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_spec_dispositions_need_a_resolving_pointer(self):
        r = self.disp("AD-1", "spec-updated")
        self.assertEqual(r.returncode, 2)
        r = self.disp("AD-1", "spec-updated", "--spec", f"{ARCH_REL}#nope")
        self.assertEqual(r.returncode, 2)
        self.assertIn("has no anchor #nope", r.stderr)

    def test_adr_justified_needs_an_existing_adr(self):
        r = self.disp("AD-1", "adr-justified", "--adr", "docs/adr/0009-x.md")
        self.assertEqual(r.returncode, 2)
        self.write("docs/adr/0009-x.md", "# ADR-0009: x\n")
        r = self.disp("AD-1", "adr-justified", "--adr", "docs/adr/0009-x.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.load()["findings"]["AD-1"]["adr"], "docs/adr/0009-x.md")

    def test_switch_off_refuses_spec_dispositions(self):
        r = self.disp("AD-1", "spec-updated", "--spec", f"{ARCH_REL}#order-api",
                      "--spec-alignment", "false")
        self.assertEqual(r.returncode, 2)
        self.assertIn("spec_alignment is off", r.stderr)
        r = self.disp("AD-1", "resolved-in-code", "--spec-alignment", "false")
        self.assertEqual(r.returncode, 0, r.stderr)

    def check(self, expect):
        return self.sa("check-dispositions", "--review", self.review, "--expect", expect)

    def test_check_passes_when_every_blocking_finding_has_one(self):
        self.disp("AD-1", "resolved-in-code")
        self.disp("AD-3", "spec-proposal", "--spec", f"{PRD_REL}#deletion")
        r = self.check("DONE — Blocker: 1, Major: 1, Minor: 1")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_check_blocks_a_blocking_finding_without_one(self):
        self.disp("AD-1", "resolved-in-code")
        r = self.check("Blocker: 1, Major: 1, Minor: 1")
        self.assertEqual(r.returncode, 2)
        self.assertIn("AD-3 (BLOCKER) has no disposition", r.stderr)

    def test_check_blocks_a_count_mismatch(self):
        self.disp("AD-1", "resolved-in-code")
        self.disp("AD-3", "resolved-in-code")
        r = self.check("Blocker: 0, Major: 1, Minor: 1")
        self.assertEqual(r.returncode, 2)
        self.assertIn("Blocker: 1, Major: 1, Minor: 1", r.stderr)

    def test_a_review_in_the_wrong_shape_cannot_pass_silently(self):
        self.write(EPIC_REVIEW_REL, "# Review\n\n- AD-1 MAJOR: something\n")
        r = self.check("Blocker: 0, Major: 1, Minor: 0")
        self.assertEqual(r.returncode, 2)
        self.assertIn("parsed Blocker: 0, Major: 0, Minor: 0", r.stderr)

    def test_sprint_ids_are_sprint_qualified(self):
        rel = f"{IMPL}/epic-003/sprint-02/closure/arch-drift-review.md"
        review = self.write(rel, REVIEW.replace("AD-1", "SD-02-1").replace("AD-2", "SD-02-2")
                            .replace("AD-3", "SD-02-3"))
        r = self.sa("disposition", "--review", review, "--finding", "SD-02-1",
                    "--disposition", "resolved-in-code")
        self.assertEqual(r.returncode, 0, r.stderr)
````

Run: SA-TEST
Expected: the new tests fail with `invalid choice: 'disposition'`.

- [ ] **Step 2: Implement.** After `cmd_sections`:

````python
# -- drift dispositions ----------------------------------------------------------------------- #

DISPOSITIONS = ("resolved-in-code", "adr-justified", "spec-updated", "spec-proposal")
SPEC_DISPOSITIONS = ("spec-updated", "spec-proposal")
# R1: epic findings AD-{n}; sprint findings SD-{sprint nn}-{n}, unique across an epic.
FINDING_ID_RE = re.compile(r"^(AD-\d+|SD-\d{2}-\d+)$")
SEVERITIES = ("BLOCKER", "MAJOR", "MINOR")
EXPECT_RE = re.compile(r"Blocker:\s*(\d+),\s*Major:\s*(\d+),\s*Minor:\s*(\d+)", re.I)
DISP_FILE = "drift-dispositions.yaml"


def _yaml():
    from ruamel.yaml import YAML
    y = YAML()
    y.width = 4096
    y.preserve_quotes = True
    return y


def load_yaml(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return _yaml().load(fh)


def dump_yaml(path, data):
    import io
    buf = io.StringIO()
    _yaml().dump(data, buf)
    atomic_write(path, buf.getvalue())


def md_tables(text):
    """Every markdown table as a list of rows (header row first), cells as plain text."""
    tables, rows, row = [], None, None
    for t in md().parse(text):
        if t.type == "table_open":
            rows = []
        elif t.type == "tr_open" and rows is not None:
            row = []
        elif t.type in ("th_open", "td_open") and row is not None:
            row.append("")
        elif t.type == "inline" and row is not None and rows is not None:
            row[-1] = t.content.strip()
        elif t.type == "tr_close" and rows is not None:
            rows.append(row)
            row = None
        elif t.type == "table_close":
            tables.append(rows)
            rows = None
    return tables


def review_findings(path):
    """{id: {"severity", "title"}} from a review's findings table -- the shape
    l3io-arch-review's references/review-report.md prescribes, IDs in the `#` column."""
    try:
        text = read_text(path)
    except OSError as e:
        raise SAError(2, f"cannot read review {path}: {e.strerror or e}")
    out = {}
    for rows in md_tables(text):
        if not rows:
            continue
        head = [c.strip().casefold() for c in rows[0]]
        if "#" not in head or "severity" not in head:
            continue
        ci, si = head.index("#"), head.index("severity")
        ti = head.index("finding") if "finding" in head else None
        for r in rows[1:]:
            fid = r[ci].strip().strip("`") if ci < len(r) else ""
            if not FINDING_ID_RE.match(fid):
                continue
            if fid in out:
                raise SAError(2, f"{path}: finding {fid} appears twice")
            title = r[ti] if ti is not None and ti < len(r) and r[ti] else fid
            out[fid] = {"severity": r[si].strip().strip("*").upper(), "title": title}
    return out


def load_dispositions(dpath, review_rel=None):
    from ruamel.yaml.comments import CommentedMap
    data = load_yaml(dpath)
    if data is None:
        data = CommentedMap()
        data["review"] = review_rel
        data["findings"] = CommentedMap()
    if not isinstance(data.get("findings"), dict):
        raise SAError(2, f"{dpath}: 'findings' is not a mapping")
    return data


def cmd_disposition(ctx, a):
    from ruamel.yaml.comments import CommentedMap
    review = ctx.abs(a.review)
    f = review_findings(review).get(a.finding)
    if f is None:
        raise SAError(2, f"{a.finding} is not in the findings table of {ctx.rel(review)}")
    if a.spec_alignment.lower() != "true" and a.disposition in SPEC_DISPOSITIONS:
        raise SAError(2, f"spec_alignment is off: {a.finding} can only be resolved-in-code "
                         f"or adr-justified")
    spec = adr = None
    if a.adr:
        if not os.path.isfile(ctx.abs(a.adr)):
            raise SAError(2, f"--adr {a.adr} does not exist")
        adr = ctx.rel(ctx.abs(a.adr))
    elif a.disposition == "adr-justified":
        raise SAError(2, "adr-justified needs --adr naming the accepted ADR")
    if a.disposition in SPEC_DISPOSITIONS:
        if not a.spec:
            raise SAError(2, f"{a.disposition} needs --spec <path>#<anchor>")
        hit, why = resolve_pointer(load_catalog(ctx), a.spec)
        if hit is None:
            raise SAError(2, f"--spec {a.spec}: {why}")
        if a.disposition == "spec-updated" and hit[3] != "architecture":
            raise SAError(2, f"spec-updated edits architecture sections only; {hit[0]} is a "
                             f"{hit[3]} spec -- record spec-proposal instead (ADR-0004)")
        spec = f"{hit[0]}#{hit[1]}"
    dpath = os.path.join(os.path.dirname(review), DISP_FILE)
    data = load_dispositions(dpath, ctx.rel(review))
    prior = data["findings"].get(a.finding)
    if prior is not None and (prior.get("commit") or prior.get("issue")):
        raise SAError(2, f"{a.finding} was already applied "
                         f"({prior.get('commit') or prior.get('issue')}); its disposition "
                         f"cannot change")
    e = CommentedMap()
    e["severity"], e["title"], e["disposition"] = f["severity"], f["title"], a.disposition
    e["spec"], e["adr"], e["commit"], e["issue"] = spec, adr, None, None
    data["findings"][a.finding] = e
    dump_yaml(dpath, data)
    print(f"OK disposition {a.finding} ({f['severity']}) -> {a.disposition}")
    return 0


def cmd_check_dispositions(ctx, a):
    m = EXPECT_RE.search(a.expect)
    if not m:
        raise SAError(2, f"--expect {a.expect!r} has no 'Blocker: N, Major: N, Minor: N'")
    review = ctx.abs(a.review)
    findings = review_findings(review)
    expected = dict(zip(SEVERITIES, map(int, m.groups())))
    got = {s: sum(1 for f in findings.values() if f["severity"] == s) for s in SEVERITIES}
    problems = []
    odd = sorted({f["severity"] for f in findings.values()} - set(SEVERITIES))
    if odd:
        problems.append(f"unknown severities in the findings table: {', '.join(odd)}")
    if got != expected:
        problems.append(f"parsed Blocker: {got['BLOCKER']}, Major: {got['MAJOR']}, Minor: "
                        f"{got['MINOR']} from {ctx.rel(review)} but the reviewer reported "
                        f"Blocker: {expected['BLOCKER']}, Major: {expected['MAJOR']}, Minor: "
                        f"{expected['MINOR']} -- is the findings table in the "
                        f"references/review-report.md shape, IDs in the # column?")
    data = load_dispositions(os.path.join(os.path.dirname(review), DISP_FILE))
    for fid, f in sorted(findings.items()):
        if f["severity"] in ("BLOCKER", "MAJOR") and fid not in data["findings"]:
            problems.append(f"{fid} ({f['severity']}) has no disposition")
    for p in problems:
        sys.stderr.write(f"check-dispositions: {p}\n")
    if problems:
        return 2
    print(f"OK check-dispositions: {len(findings)} finding(s), every BLOCKER/MAJOR disposed")
    return 0
````

Parser blocks above the marker:

```python
    dp = sub.add_parser("disposition", help="record one drift finding's disposition")
    dp.add_argument("--review", required=True)
    dp.add_argument("--finding", required=True, help="AD-{n} or SD-{nn}-{n}")
    dp.add_argument("--disposition", required=True, choices=list(DISPOSITIONS))
    dp.add_argument("--spec", default="", help="<path>#<anchor> (spec dispositions)")
    dp.add_argument("--adr", default="", help="the ADR (adr-justified; optional otherwise)")
    dp.add_argument("--spec-alignment", default="true", help="pm-execute's spec_alignment")
    dp.set_defaults(func=cmd_disposition)

    cd = sub.add_parser("check-dispositions", help="gate: every BLOCKER/MAJOR disposed")
    cd.add_argument("--review", required=True)
    cd.add_argument("--expect", required=True,
                    help="the reviewer's final 'Blocker: N, Major: N, Minor: N'")
    cd.set_defaults(func=cmd_check_dispositions)
```

- [ ] **Step 3: Run the tests and confirm they pass**

Run: SA-TEST
Expected: `OK` (39 tests).

- [ ] **Step 4: Non-hollow proof.** Replace `if got != expected:` with `if False:`, and
  rerun `test_a_review_in_the_wrong_shape_cannot_pass_silently`. It must FAIL. Restore.

- [ ] **Step 5: Sync, run the gates, and commit** (the same files as Task 5), with the
  subject `feat(l3io-pm): spec-align disposition and check-dispositions`.

---
### Task 7: `adrs` and `check-links`

**Files:**
- Modify: `skills/_shared/spec-align.py`. Add an ADR block after `cmd_check_dispositions`,
  and two parser blocks.
- Modify: `skills/_shared/tests/test-spec-align.py`.
- Generated: the copies and manifests.

**Interfaces:**
- **Consumes:** `load_catalog`, `resolve_pointer`, `read_text`.
- **Produces:**
  - `epic_key(value) -> "E003" | None`.
  - `DOC_ADR_RE`, `LEGACY_ADR_RE`.
  - `adr_meta(path) -> {"Status", "Epic", "Departs from spec"}` (missing keys are absent).
  - `all_adrs(ctx) -> [{"path", "number", "home": "docs"|"legacy", "epic", "status", "departs"}]`.
  - `link_gaps(ctx, cat, adrs) -> [(adr, pointer, why)]`, where `why` is one of:
    - `"not a pointer"`
    - `"pointer does not resolve"`
    - `"section does not link the ADR"`

- [ ] **Step 1: Write the failing tests** (before `__main__`):

````python
def adr(num, slug, epic="E003", status="Accepted", departs="n/a"):
    return (f"# ADR-{num:04d}: {slug}\n\n- **Status:** {status}\n- **Date:** 2026-09-11\n"
            f"- **Epic:** {epic}\n- **Departs from spec:** {departs}\n\n## Context\n\nx\n")


class TestAdrs(Project):
    def setUp(self):
        super().setUp()
        self.write(ARCH_REL, ARCH)
        self.write("docs/adr/0001-order-api.md",
                   adr(1, "order-api", departs=f"{ARCH_REL}#order-api"))
        self.write("docs/adr/0002-global.md", adr(2, "global", epic="n/a"))
        self.write("docs/adr/0003-draft.md",
                   adr(3, "draft", status="Proposed", departs=f"{ARCH_REL}#data-model"))
        self.write(f"{IMPL}/epic-003/arch/adr-0005-legacy.md", adr(5, "legacy"))
        self.write(f"{IMPL}/epic-003/arch/arch-gate-review.md", "# Gate\n")

    def test_lists_an_epics_adrs_from_both_homes(self):
        r = self.sa("adrs", "--epic", "E003")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), ["docs/adr/0001-order-api.md",
                                                 "docs/adr/0003-draft.md",
                                                 f"{IMPL}/epic-003/arch/adr-0005-legacy.md"])
        self.assertIn("old ADR home", r.stderr)
        self.assertIn("migrate-adrs", r.stderr)

    def test_accepts_the_bare_epic_number(self):
        r = self.sa("adrs", "--epic", "3", "--format", "json")
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = json.loads(r.stdout)
        self.assertEqual([x["number"] for x in rows], [1, 3, 5])
        self.assertEqual(rows[0]["departs"], f"{ARCH_REL}#order-api")
        self.assertEqual(rows[2]["home"], "legacy")

    def test_check_links_reports_an_unlinked_departure(self):
        r = self.sa("check-links")
        self.assertEqual(r.returncode, 1)
        self.assertIn("0001-order-api.md", r.stdout)
        self.assertIn("section does not link the ADR", r.stdout)
        self.assertNotIn("0003-draft", r.stdout)            # Proposed: not a departure yet

    def test_check_links_passes_once_the_section_links_it(self):
        self.write(ARCH_REL, ARCH.replace(
            "POST /orders accepts a body.",
            "POST /orders accepts a body. See [ADR-0001](../../docs/adr/0001-order-api.md)."))
        r = self.sa("check-links", "--epic", "E003")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_check_links_reports_a_dangling_pointer(self):
        self.write("docs/adr/0004-gone.md", adr(4, "gone", departs=f"{ARCH_REL}#removed"))
        r = self.sa("check-links")
        self.assertEqual(r.returncode, 1)
        self.assertIn("0004-gone.md", r.stdout)
        self.assertIn("pointer does not resolve", r.stdout)
````

Run: SA-TEST
Expected: the new tests fail (`invalid choice: 'adrs'`).

- [ ] **Step 2: Implement.** After `cmd_check_dispositions`:

````python
# -- ADRs (one home: docs/adr/, ADR-0005) ------------------------------------------------------- #

DOC_ADR_RE = re.compile(r"^(\d{4})-.+\.md$")
LEGACY_ADR_RE = re.compile(r"^adr-(\d{4})-(.+)\.md$")
ADR_META_RE = re.compile(r"^-\s+\*\*(Status|Epic|Departs from spec):\*\*\s*(.*?)\s*$")


def epic_key(value):
    """'E003', 'e3', '003', '3' -> 'E003'; anything else (n/a, empty) -> None."""
    m = re.fullmatch(r"\s*E?(\d{1,3})\s*", str(value or ""), re.I)
    return f"E{int(m.group(1)):03d}" if m else None


def adr_meta(path):
    """The metadata bullets before the first `##` heading (assets/adr-template.md shape)."""
    meta = {}
    for line in read_text(path).splitlines():
        if line.startswith("## "):
            break
        m = ADR_META_RE.match(line)
        if m:
            meta[m.group(1)] = m.group(2).strip().strip("`")
    return meta


def all_adrs(ctx):
    out = []
    docs = os.path.join(ctx.project, "docs", "adr")
    if os.path.isdir(docs):
        for name in sorted(os.listdir(docs)):
            m = DOC_ADR_RE.match(name)
            if m:
                p = os.path.join(docs, name)
                meta = adr_meta(p)
                out.append({"path": ctx.rel(p), "number": int(m.group(1)), "home": "docs",
                            "epic": epic_key(meta.get("Epic")), "status": meta.get("Status", ""),
                            "departs": meta.get("Departs from spec", "")})
    if ctx.impl:
        for p in sorted(glob.glob(os.path.join(ctx.impl, "epic-*", "arch", "adr-*.md"))):
            m = LEGACY_ADR_RE.match(os.path.basename(p))
            em = re.search(r"epic-(\d{3})", os.path.basename(os.path.dirname(os.path.dirname(p))))
            if m and em:
                meta = adr_meta(p)
                out.append({"path": ctx.rel(p), "number": int(m.group(1)), "home": "legacy",
                            "epic": f"E{em.group(1)}", "status": meta.get("Status", ""),
                            "departs": meta.get("Departs from spec", "")})
    return out


def link_gaps(ctx, cat, adrs):
    """Accepted ADRs whose `Departs from spec:` section does not link back to them."""
    gaps = []
    for x in adrs:
        dep = (x["departs"] or "").strip()
        if not x["status"].lower().startswith("accepted") or not dep or dep.lower() == "n/a":
            continue
        if not PTR_RE.match(dep):
            gaps.append((x, dep, "not a pointer"))
            continue
        hit, _ = resolve_pointer(cat, dep)
        if hit is None:
            gaps.append((x, dep, "pointer does not resolve"))
            continue
        sec = hit[2]
        body = read_text(ctx.abs(hit[0])).splitlines()[sec.start - 1:sec.end]
        if not any(os.path.basename(x["path"]) in line for line in body):
            gaps.append((x, dep, "section does not link the ADR"))
    return gaps


def cmd_adrs(ctx, a):
    ek = epic_key(a.epic)
    if ek is None:
        raise SAError(2, f"--epic {a.epic!r} is not an epic key")
    rows = [x for x in all_adrs(ctx) if x["epic"] == ek]
    for x in rows:
        if x["home"] == "legacy":
            sys.stderr.write(f"WARN {x['path']} is in the old ADR home -- run "
                             f"/l3io-util-doctor migrate-adrs\n")
    if a.format == "json":
        print(json.dumps(rows, indent=2))
    else:
        for x in rows:
            print(x["path"])
    return 0


def cmd_check_links(ctx, a):
    adrs = all_adrs(ctx)
    if a.epic:
        ek = epic_key(a.epic)
        adrs = [x for x in adrs if x["epic"] == ek]
    gaps = link_gaps(ctx, load_catalog(ctx), adrs)
    for x, dep, why in gaps:
        print(f"{x['path']}: departs from {dep} -- {why}")
    if gaps:
        return 1
    print(f"OK check-links: {len(adrs)} ADR(s)")
    return 0
````

Parser blocks:

```python
    ad = sub.add_parser("adrs", help="an epic's ADRs, from docs/adr and the old home")
    ad.add_argument("--epic", required=True)
    ad.add_argument("--format", choices=["text", "json"], default="text")
    ad.set_defaults(func=cmd_adrs)

    cl = sub.add_parser("check-links", help="report ADRs their spec section does not link")
    cl.add_argument("--epic", default="")
    cl.set_defaults(func=cmd_check_links)
```

- [ ] **Step 3: Run the tests and confirm they pass**

Run: SA-TEST
Expected: `OK` (44 tests).

- [ ] **Step 4: Non-hollow proof.** In `link_gaps`, change `if not any(...)` to `if False`,
  and rerun `test_check_links_reports_an_unlinked_departure`. It must FAIL. Restore.

- [ ] **Step 5: Sync, run the gates, and commit** with the subject
  `feat(l3io-pm): spec-align adrs and check-links`.

---

### Task 8: the spec-sync lease

**Files:**
- Modify: `skills/_shared/spec-align.py`. Add a lease block after `cmd_check_links`, and one
  parser block with nested subcommands.
- Modify: `skills/_shared/tests/test-spec-align.py`.
- Generated: the copies and manifests.

**Interfaces:**
- **Consumes:** `Ctx.need("state")`, `epic_key`.
- **Produces:**
  - `LEASE_NAME = "spec-sync.lock"`.
  - `lease_holder(ctx) -> dict | None`, the current unexpired lease (`owner`,
    `acquired_at`, `expires_at`).
  - `lease acquire --owner E [--wait-minutes N] [--ttl-minutes N] [--poll-seconds S]`
    (exit 0, or 5 when held).
  - `lease release --owner E`.
- The nested parser variable **must** be named `lease_sub`, not `sub`. Check-docs' surface
  regex is `\bsub\.add_parser` (Task 18), so `acquire` and `release` must not read as
  top-level subcommands.

- [ ] **Step 1: Write the failing tests** (before `__main__`):

````python
class TestLease(Project):
    def lease(self, *args):
        return self.sa("lease", *args)

    def test_acquire_then_contend(self):
        self.assertEqual(self.lease("acquire", "--owner", "E001", "--wait-minutes", "0")
                         .returncode, 0)
        r = self.lease("acquire", "--owner", "E002", "--wait-minutes", "0")
        self.assertEqual(r.returncode, 5)
        self.assertIn("held by E001", r.stderr)
        self.assertEqual(self.lease("acquire", "--owner", "E001", "--wait-minutes", "0")
                         .returncode, 0)                      # the owner may refresh

    def test_expired_lease_is_taken_over_and_logged(self):
        self.lease("acquire", "--owner", "E001", "--ttl-minutes", "0", "--wait-minutes", "0")
        r = self.lease("acquire", "--owner", "E002", "--wait-minutes", "0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("E001", r.stderr)
        self.assertIn("taking it over", r.stderr)

    def test_release_rules(self):
        self.assertEqual(self.lease("release", "--owner", "E001").returncode, 0)   # free: no-op
        self.lease("acquire", "--owner", "E001", "--wait-minutes", "0")
        r = self.lease("release", "--owner", "E002")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.lease("release", "--owner", "E001").returncode, 0)
        self.assertEqual(self.lease("acquire", "--owner", "E002", "--wait-minutes", "0")
                         .returncode, 0)

    def test_lease_file_lives_in_the_state_root(self):
        self.lease("acquire", "--owner", "E001", "--wait-minutes", "0")
        with open(os.path.join(self.state, "spec-sync.lock"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["owner"], "E001")

    def test_real_processes_contending_get_exactly_one_winner(self):
        g = ["--project-root", self.root, "--impl-root", self.impl, "--state-root", self.state]
        procs = [subprocess.Popen([sys.executable, SCRIPT, *g, "lease", "acquire", "--owner",
                                   f"E{i:03d}", "--wait-minutes", "0"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for i in range(1, 7)]
        codes = [p.wait(timeout=120) for p in procs]
        for p in procs:
            p.stdout.close()
            p.stderr.close()
        self.assertEqual(sorted(codes), [0, 5, 5, 5, 5, 5])

    def test_a_waiter_gets_the_lease_when_the_holder_releases(self):
        self.lease("acquire", "--owner", "E001", "--wait-minutes", "0")
        g = ["--project-root", self.root, "--impl-root", self.impl, "--state-root", self.state]
        waiter = subprocess.Popen([sys.executable, SCRIPT, *g, "lease", "acquire", "--owner",
                                   "E002", "--wait-minutes", "0.5", "--poll-seconds", "0.1"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(0.6)
        self.assertEqual(self.lease("release", "--owner", "E001").returncode, 0)
        out, err = waiter.communicate(timeout=120)
        self.assertEqual(waiter.returncode, 0, err.decode())
````

Run: SA-TEST
Expected: the new tests fail (`invalid choice: 'lease'`).

- [ ] **Step 2: Implement.** After `cmd_check_links`:

````python
# -- the spec-sync lease ---------------------------------------------------------------------- #
# Parallel epic closures share one working tree: without a lease two agents can edit one
# architecture doc at once, or one commits the other's half-made edit. It is a lease, not a
# flock, because it must survive an agent's many turns; the flock only guards the file's
# read-decide-write. The `.lock` name puts it under pm-status's `*.lock` rule in
# state/.gitignore, which exists by epic closure (every set-status takes an epic lock there).

LEASE_NAME = "spec-sync.lock"


class LeaseHeld(Exception):
    pass


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s):
    from datetime import datetime, timezone
    try:
        return datetime.strptime(str(s), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _lease_path(ctx):
    ctx.need("state")
    os.makedirs(ctx.state_root, exist_ok=True)
    return os.path.join(ctx.state_root, LEASE_NAME)


def _lease_read(fh):
    fh.seek(0)
    raw = fh.read().strip()
    if not raw:
        return None
    try:
        cur = json.loads(raw)
    except ValueError:
        sys.stderr.write(f"WARN {LEASE_NAME} is not JSON; treating the lease as free\n")
        return None
    return cur if isinstance(cur, dict) else None


def _lease_write(fh, value):
    fh.seek(0)
    fh.truncate()
    if value is not None:
        fh.write(json.dumps(value))
    fh.flush()
    os.fsync(fh.fileno())


def lease_holder(ctx):
    """The current lease if it is held and unexpired, else None."""
    import fcntl
    path = _lease_path(ctx)
    if not os.path.exists(path):
        return None
    with open(path, "a+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_SH)
        try:
            cur = _lease_read(fh)
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
    if cur and (_parse_iso(cur.get("expires_at")) or _now()) > _now():
        return cur
    return None


def _lease_try(path, owner, ttl_minutes):
    import fcntl
    from datetime import timedelta
    with open(path, "a+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            cur, now = _lease_read(fh), _now()
            if cur and cur.get("owner") != owner:
                expires = _parse_iso(cur.get("expires_at"))
                if expires is not None and expires > now:
                    raise LeaseHeld(cur)
                sys.stderr.write(f"WARN spec-sync lease held by {cur.get('owner')} expired at "
                                 f"{cur.get('expires_at')}; taking it over\n")
            new = {"owner": owner, "acquired_at": _iso(now),
                   "expires_at": _iso(now + timedelta(minutes=ttl_minutes))}
            _lease_write(fh, new)
            return new
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def cmd_lease(ctx, a):
    import fcntl
    owner = epic_key(a.owner)
    if owner is None:
        raise SAError(2, f"--owner {a.owner!r} is not an epic key")
    path = _lease_path(ctx)
    if a.lease_cmd == "acquire":
        from tenacity import retry, retry_if_exception_type, stop_after_delay, wait_fixed

        @retry(retry=retry_if_exception_type(LeaseHeld), reraise=True,
               stop=stop_after_delay(a.wait_minutes * 60), wait=wait_fixed(a.poll_seconds))
        def attempt():
            return _lease_try(path, owner, a.ttl_minutes)

        try:
            new = attempt()
        except LeaseHeld as e:
            cur = e.args[0]
            sys.stderr.write(f"spec-sync lease held by {cur.get('owner')} until "
                             f"{cur.get('expires_at')}\n")
            return 5
        print(f"OK lease acquired by {owner} until {new['expires_at']}")
        return 0
    with open(path, "a+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            cur = _lease_read(fh)
            if not cur:
                print("OK lease already free")
                return 0
            if cur.get("owner") != owner:
                raise SAError(2, f"the lease is held by {cur.get('owner')}, not {owner}")
            _lease_write(fh, None)
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
    print(f"OK lease released by {owner}")
    return 0
````

Parser block:

```python
    le = sub.add_parser("lease", help="the spec-sync lease (acquire | release)")
    lease_sub = le.add_subparsers(dest="lease_cmd", required=True)
    la = lease_sub.add_parser("acquire")
    la.add_argument("--owner", required=True, help="the epic key")
    la.add_argument("--wait-minutes", type=float, default=15.0)
    la.add_argument("--ttl-minutes", type=float, default=30.0)
    la.add_argument("--poll-seconds", type=float, default=5.0)
    lr = lease_sub.add_parser("release")
    lr.add_argument("--owner", required=True)
    le.set_defaults(func=cmd_lease)
```

- [ ] **Step 3: Run the tests and confirm they pass**

Run: SA-TEST
Expected: `OK` (50 tests).

- [ ] **Step 4: Non-hollow proof.** Delete `fcntl.flock(fh, fcntl.LOCK_EX)` in `_lease_try`
  (leave the `try:`), and rerun
  `test_real_processes_contending_get_exactly_one_winner` five times. It must fail at least
  once. If it never fails in five runs, insert `time.sleep(0.05)` between `_lease_read` and
  the owner check while the flock is removed, which proves the race. Restore both, and note
  the result.

- [ ] **Step 5: Sync, run the gates, and commit** with the subject
  `feat(l3io-pm): spec-align spec-sync lease`.

---
### Task 9: `sync-plan` (with `--defer`) and `propose`

**Files:**
- Modify: `skills/_shared/spec-align.py`. Add a spec-sync planning block after `cmd_lease`,
  and two parser blocks.
- Modify: `skills/_shared/tests/test-spec-align.py`. Add the `SyncBase` fixture, which
  Tasks 10 and 11 reuse, and a test class.
- Generated: the copies and manifests.

**Interfaces:**
- **Consumes:** `load_dispositions`, `dump_yaml`, `resolve_pointer`, `all_adrs`, `link_gaps`,
  `epic_key`, `SPEC_DISPOSITIONS`, `DISP_FILE`.
- **Produces:**
  - `SEV_MAP` (BLOCKER→High, MAJOR→Medium, MINOR→Low).
  - `_pm(ctx, *args) -> CompletedProcess`, which runs pm-status with `sys.executable`.
  - `append_spec_issue(ctx, nnn, kind, ref, ident, title, severity, pointer, where) -> "BL-…"`.
  - `epic_nnn(value) -> "003"`, which exits 2 on a bad key.
  - `disposition_files(ctx, nnn)`, `epic_disp_path(ctx, nnn)`, `proposal_path(ctx, nnn, ident)`.
  - `pending_items(ctx, nnn, cat) -> [item]`. Each item has `type`
    (`spec-updated` | `spec-proposal` | `adr-link`), `id`, `severity`, `title`, `spec`,
    `range`, `problem`, `adr`, `review` and `dispositions`.
  - `find_item(ctx, nnn, ident, cat)` and `record_item(ctx, item, **fields)`, which writes
    into the finding entry, or into `adr_links[ident]` in the epic's dispositions file.
  - `adr_ident(ctx, path) -> "ADR-0012"`.

- [ ] **Step 1: Write the failing tests** (before `__main__`):

````python
class SyncBase(Project):
    """Epic E003 in a real git repo: an architecture spec, a PRD, an epic drift review with a
    spec-updated (AD-1 -> order-api) and a spec-proposal (AD-3 -> PRD deletion), and a story
    pointing at order-api. Tasks 10 and 11 build on this."""

    def setUp(self):
        super().setUp()
        self.write(ARCH_REL, ARCH)
        self.write(PRD_REL, PRD)
        self.review = self.write(EPIC_REVIEW_REL, REVIEW)
        self.story = self.write(f"{IMPL}/epic-003/sprint-01/stories/E003-S01-001.md",
                                full_story(Interface_contracts=f"POST.\nSpec: {ARCH_REL}#order-api"))
        self.write("README.md", "readme\n")
        self.init_git()
        self.dispose("AD-1", "spec-updated", "--spec", f"{ARCH_REL}#order-api")
        self.dispose("AD-3", "spec-proposal", "--spec", f"{PRD_REL}#deletion")

    def dispose(self, fid, disposition, *extra, review=None):
        r = self.sa("disposition", "--review", review or self.review, "--finding", fid,
                    "--disposition", disposition, *extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def plan(self, *extra):
        r = self.sa("sync-plan", "--epic", "E003", *extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def issues(self, kind, resolved=False):
        args = ["list-issues", "--state-root", self.state, "--format", "json"]
        args += ["--resolved"] if resolved else ["--kind", kind]
        r = self.pm(*args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def disp(self):
        from ruamel.yaml import YAML
        with open(self.path(f"{IMPL}/epic-003/epic-closure/drift-dispositions.yaml"),
                  encoding="utf-8") as fh:
            return YAML(typ="safe").load(fh)


class TestSyncPlan(SyncBase):
    def test_plan_lists_pending_spec_items_with_ranges(self):
        items = {i["id"]: i for i in self.plan()["items"]}
        self.assertEqual(set(items), {"AD-1", "AD-3"})
        self.assertEqual(items["AD-1"]["type"], "spec-updated")
        self.assertEqual(items["AD-1"]["range"], "L9–16")
        self.assertEqual(items["AD-1"]["title"], "Orders bypass the repository")
        self.assertEqual(items["AD-3"]["range"], "L3–5")
        self.assertEqual(items["AD-3"]["review"], EPIC_REVIEW_REL)

    def test_an_epic_without_dispositions_plans_nothing(self):
        r = self.sa("sync-plan", "--epic", "E009")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), {"epic": "E009", "items": []})

    def test_sprint_findings_are_included(self):
        rel = f"{IMPL}/epic-003/sprint-01/closure/arch-drift-review.md"
        review = self.write(rel, REVIEW.replace("AD-", "SD-01-"))
        self.dispose("SD-01-1", "spec-updated", "--spec", f"{ARCH_REL}#data-model", review=review)
        self.assertIn("SD-01-1", {i["id"] for i in self.plan()["items"]})

    def test_an_unlinked_accepted_adr_becomes_an_adr_link_item(self):
        self.write("docs/adr/0001-order-api.md",
                   adr(1, "order-api", departs=f"{ARCH_REL}#order-api"))
        items = {i["id"]: i for i in self.plan()["items"]}
        self.assertEqual(items["ADR-0001"]["type"], "adr-link")
        self.assertEqual(items["ADR-0001"]["adr"], "docs/adr/0001-order-api.md")

    def test_defer_writes_pointer_only_proposals_and_backlog_items(self):
        out = self.plan("--defer")
        self.assertEqual({d["id"] for d in out["deferred"]}, {"AD-1", "AD-3"})
        prop = self.read(f"{IMPL}/epic-003/epic-closure/spec-proposals/AD-1.md")
        self.assertIn(f"`{ARCH_REL}#order-api`", prop)
        self.assertIn("(deferred)", prop)
        items = self.issues("spec-proposal")
        self.assertEqual(len(items), 2)
        self.assertEqual({i["ref"] for i in items},
                         {f"{IMPL}/epic-003/epic-closure/spec-proposals/AD-1.md",
                          f"{IMPL}/epic-003/epic-closure/spec-proposals/AD-3.md"})
        self.assertEqual({i["severity"] for i in items}, {"Medium", "High"})
        d = self.disp()["findings"]["AD-1"]
        self.assertEqual((d["disposition"], d["deferred"]), ("spec-proposal", True))
        self.assertTrue(d["issue"].startswith("BL-E003-"))
        self.assertEqual(self.plan()["items"], [])            # nothing left pending

    def test_propose_records_an_agent_written_proposal(self):
        rel = f"{IMPL}/epic-003/epic-closure/spec-proposals/AD-3.md"
        r = self.sa("propose", "--epic", "E003", "--finding", "AD-3")
        self.assertEqual(r.returncode, 2)                     # no file yet
        self.assertIn("write the proposal", r.stderr)
        self.write(rel, "# Proposal\n\nMake deletion hard.\n")
        r = self.sa("propose", "--epic", "E003", "--finding", "AD-3")
        self.assertEqual(r.returncode, 0, r.stderr)
        [it] = self.issues("spec-proposal")
        self.assertEqual(it["ref"], rel)
        self.assertEqual(it["title"], "Spec proposal: PRD says soft delete")
        self.assertEqual(self.disp()["findings"]["AD-3"]["proposal"], rel)

    def test_propose_refuses_a_finding_that_is_not_pending(self):
        r = self.sa("propose", "--epic", "E003", "--finding", "AD-2")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not a pending spec item", r.stderr)
````

Run: SA-TEST
Expected: the new tests fail (`invalid choice: 'sync-plan'`).

- [ ] **Step 2: Implement.** After `cmd_lease`:

````python
# -- spec sync: the plan, deferral, proposals ---------------------------------------------- #

SEV_MAP = {"BLOCKER": "High", "MAJOR": "Medium", "MINOR": "Low"}
ISSUE_KEY_RE = re.compile(r"\b(BL-E\d{3}-\d{3})\b")


def _pm(ctx, *args):
    ctx.need("pm")
    return subprocess.run([sys.executable, ctx.pm_status, *args], capture_output=True, text=True)


def append_spec_issue(ctx, nnn, kind, ref, ident, title, severity, pointer, where):
    """One spec-change/spec-proposal backlog item through pm-status; returns its key. A rerun
    after a crash finds the open twin (append-issue skips a content duplicate and names it)."""
    ctx.need("state")
    label = "Spec change" if kind == "spec-change" else "Spec proposal"
    args = ["append-issue", "--state-root", ctx.state_root, "--epic", nnn, "--sprint", "",
            "--kind", kind, "--ref", ref, "--title", f"{label}: {title}",
            "--source", f"spec-sync ({ident})", "--severity", SEV_MAP.get(severity, "Low"),
            "--description", f"Confirm or reject: /l3io-util-doctor triage. Spec: {pointer}. "
                             f"From: {where}."]
    r = _pm(ctx, *args)
    if r.returncode == 0 and "resolved as" in r.stdout:     # matched a resolved twin, not open
        r = _pm(ctx, *args, "--allow-duplicate")
    m = ISSUE_KEY_RE.search(r.stdout)
    if r.returncode != 0 or not m:
        raise SAError(2, f"append-issue failed: {(r.stderr or r.stdout).strip()}")
    return m.group(1)


def epic_nnn(value):
    ek = epic_key(value)
    if ek is None:
        raise SAError(2, f"--epic {value!r} is not an epic key")
    return ek[1:]


def epic_disp_path(ctx, nnn):
    ctx.need("impl")
    return os.path.join(ctx.impl, f"epic-{nnn}", "epic-closure", DISP_FILE)


def disposition_files(ctx, nnn):
    ctx.need("impl")
    files = sorted(glob.glob(os.path.join(ctx.impl, f"epic-{nnn}", "sprint-*", "closure",
                                          DISP_FILE)))
    ep = epic_disp_path(ctx, nnn)
    return files + ([ep] if os.path.isfile(ep) else [])


def proposal_path(ctx, nnn, ident):
    return os.path.join(ctx.impl, f"epic-{nnn}", "epic-closure", "spec-proposals", f"{ident}.md")


def adr_ident(ctx, path):
    m = DOC_ADR_RE.match(os.path.basename(path))
    if not m or not os.path.isfile(ctx.abs(path)):
        raise SAError(2, f"--adr {path} is not an ADR under docs/adr/")
    return f"ADR-{int(m.group(1)):04d}"


def _range(hit):
    return f"L{hit[2].start}–{hit[2].end}" if hit else None


def pending_items(ctx, nnn, cat):
    items = []
    for f in disposition_files(ctx, nnn):
        data = load_dispositions(f)
        for fid, e in data["findings"].items():
            if (e.get("disposition") not in SPEC_DISPOSITIONS or e.get("commit")
                    or e.get("issue")):
                continue
            hit, why = resolve_pointer(cat, e.get("spec") or "")
            items.append({"type": e["disposition"], "id": fid, "severity": e.get("severity"),
                          "title": e.get("title"), "spec": e.get("spec"), "range": _range(hit),
                          "problem": why, "adr": e.get("adr"), "review": data.get("review"),
                          "dispositions": ctx.rel(f)})
    ep = epic_disp_path(ctx, nnn)
    done = (load_yaml(ep) or {}).get("adr_links") or {}
    for x, dep, why in link_gaps(ctx, cat, [a for a in all_adrs(ctx) if a["epic"] == f"E{nnn}"]):
        ident = f"ADR-{x['number']:04d}"
        if why != "section does not link the ADR" or ident in done:
            continue
        hit, _ = resolve_pointer(cat, dep)
        items.append({"type": "adr-link", "id": ident, "severity": "MINOR",
                      "title": f"Link {ident} from {dep}", "spec": dep, "range": _range(hit),
                      "problem": None, "adr": x["path"], "review": None,
                      "dispositions": ctx.rel(ep)})
    return items


def find_item(ctx, nnn, ident, cat):
    hits = [i for i in pending_items(ctx, nnn, cat) if i["id"] == ident]
    if not hits:
        raise SAError(2, f"{ident} is not a pending spec item for E{nnn} (see sync-plan)")
    return hits[0]


def record_item(ctx, item, **fields):
    from ruamel.yaml.comments import CommentedMap
    dpath = ctx.abs(item["dispositions"])
    data = load_dispositions(dpath)
    if item["type"] == "adr-link":
        if data.get("adr_links") is None:
            data["adr_links"] = CommentedMap()
        entry = data["adr_links"].get(item["id"])
        if entry is None:
            entry = data["adr_links"][item["id"]] = CommentedMap()
    else:
        entry = data["findings"][item["id"]]
    for k, v in fields.items():
        entry[k] = v
    dump_yaml(dpath, data)


def _deferred_text(it):
    lines = [f"# Spec proposal — {it['id']} (deferred)", "",
             f"- **Finding:** {it['id']}" + (f" in `{it['review']}`" if it["review"] else ""),
             f"- **Severity:** {it['severity']}",
             f"- **Spec:** `{it['spec']}` ({it['range'] or 'pointer does not resolve'})"]
    if it["adr"]:
        lines.append(f"- **ADR:** `{it['adr']}`")
    lines += ["- **Why deferred:** the spec-sync lease was held by another epic's closure, so "
              "nothing was edited.", "",
              "Apply the change the finding describes to that section, then confirm this item "
              "in `/l3io-util-doctor triage`.", ""]
    return "\n".join(lines)


def cmd_sync_plan(ctx, a):
    nnn = epic_nnn(a.epic)
    items = pending_items(ctx, nnn, load_catalog(ctx))
    if not a.defer:
        print(json.dumps({"epic": f"E{nnn}", "items": items}, indent=2))
        return 0
    done = []
    for it in items:
        rel = ctx.rel(proposal_path(ctx, nnn, it["id"]))
        atomic_write(ctx.abs(rel), _deferred_text(it))
        key = append_spec_issue(ctx, nnn, "spec-proposal", rel, it["id"], it["title"],
                                it["severity"], it["spec"], it["review"] or it["adr"])
        fields = {"proposal": rel, "issue": key}
        if it["type"] != "adr-link":
            fields.update(disposition="spec-proposal", deferred=True)     # R10
        record_item(ctx, it, **fields)
        done.append({"id": it["id"], "proposal": rel, "issue": key})
    print(json.dumps({"epic": f"E{nnn}", "deferred": done}, indent=2))
    return 0


def cmd_propose(ctx, a):
    nnn = epic_nnn(a.epic)
    ident = a.finding or adr_ident(ctx, a.adr)
    it = find_item(ctx, nnn, ident, load_catalog(ctx))
    rel = ctx.rel(proposal_path(ctx, nnn, ident))
    p = ctx.abs(rel)
    if not os.path.isfile(p) or not read_text(p).strip():
        raise SAError(2, f"write the proposal at {rel} first (target pointer, the change, why, "
                         f"and the finding)")
    key = append_spec_issue(ctx, nnn, "spec-proposal", rel, ident, it["title"], it["severity"],
                            it["spec"], it["review"] or it["adr"])
    fields = {"proposal": rel, "issue": key}
    if it["type"] == "spec-updated":
        fields["disposition"] = "spec-proposal"
    record_item(ctx, it, **fields)
    print(f"OK propose {ident} -> {key} ({rel})")
    return 0
````

Parser blocks:

```python
    sp = sub.add_parser("sync-plan", help="the epic's pending spec-sync items (JSON)")
    sp.add_argument("--epic", required=True)
    sp.add_argument("--defer", action="store_true",
                    help="write pointer-only proposals + backlog items instead (lease timeout)")
    sp.set_defaults(func=cmd_sync_plan)

    pr = sub.add_parser("propose", help="record an agent-written proposal and its backlog item")
    pr.add_argument("--epic", required=True)
    g = pr.add_mutually_exclusive_group(required=True)
    g.add_argument("--finding", default="")
    g.add_argument("--adr", default="")
    pr.set_defaults(func=cmd_propose)
```

- [ ] **Step 3: Run the tests and confirm they pass**

Run: SA-TEST
Expected: `OK` (57 tests).

- [ ] **Step 4: Non-hollow proof.** In `pending_items`, delete `or e.get("issue")` from the
  skip condition, and rerun `test_defer_writes_pointer_only_proposals_and_backlog_items`. Its
  last assertion must FAIL, because the items come back. Restore.

- [ ] **Step 5: Sync, run the gates, and commit** with the subject
  `feat(l3io-pm): spec-align sync-plan, --defer and propose`.

---
### Task 10: `commit` — the guarded `docs(spec)` commit

**Files:**
- Modify: `skills/_shared/spec-align.py`. Add a git/commit block after `cmd_propose`, and
  one parser block.
- Modify: `skills/_shared/tests/test-spec-align.py`.
- Generated: the copies and manifests.

**Interfaces:**
- **Consumes:** `find_item`, `record_item`, `append_spec_issue`, `lease_holder`,
  `parse_sections`, `all_story_files`, `all_adrs`, `adr_ident`, `epic_disp_path`,
  `load_yaml`, `PTR_RE`.
- **Produces:**
  - `_git(ctx, *args, check=True) -> CompletedProcess`, which exits 2 on failure when
    `check`.
  - `git_commit(ctx, message, paths) -> sha`, using `git commit -s --only -- paths` with
    tenacity retry on `index.lock` (5 attempts, exponential backoff from 0.2 s, max 2 s).
  - `adr_link_item(ctx, nnn, path) -> item`.
  - `changed_hunks(ctx, rel) -> [(source_start, source_length)]`, from
    `git diff -U0 HEAD`, parsed by unidiff.
  - `hunks_outside(hunks, section) -> [...]`.
  - `pointing_stories(ctx, rel, anchor)`, `rewrite_pointer(path, rel, old, new)`.
  - `commit --epic E (--finding ID | --adr P) --paths F [--rename-anchor OLD=NEW]...`

- [ ] **Step 1: Write the failing tests** (before `__main__`):

````python
class TestCommit(SyncBase):
    def setUp(self):
        super().setUp()
        r = self.sa("lease", "acquire", "--owner", "E003", "--wait-minutes", "0")
        self.assertEqual(r.returncode, 0, r.stderr)

    def edit(self, old, new, rel=ARCH_REL):
        text = self.read(rel)
        self.assertIn(old, text)
        self.write(rel, text.replace(old, new, 1))

    def commit(self, *extra, finding="AD-1"):
        args = ["commit", "--epic", "E003"]
        args += ["--finding", finding] if finding else []
        return self.sa(*args, "--paths", ARCH_REL, *extra)

    def head(self):
        return self.git("rev-parse", "HEAD").strip()

    def test_an_in_scope_edit_is_committed_recorded_and_tracked(self):
        self.edit("POST /orders accepts a body.", "POST /orders accepts a body; returns 201.")
        r = self.commit()
        self.assertEqual(r.returncode, 0, r.stderr)
        msg = self.git("log", "-1", "--format=%B")
        self.assertTrue(msg.startswith("docs(spec): E003 AD-1 — Orders bypass the repository"),
                        msg)
        self.assertIn("Signed-off-by: t <t@example.com>", msg)
        self.assertEqual(self.git("show", "--name-only", "--format=", "HEAD").split(),
                         [ARCH_REL])
        d = self.disp()["findings"]["AD-1"]
        self.assertEqual(d["commit"], self.head())
        [it] = self.issues("spec-change")
        self.assertEqual((it["key"], it["ref"]), (d["issue"], self.head()))
        self.assertEqual(it["severity"], "Medium")
        self.assertNotIn("AD-1", {i["id"] for i in self.plan()["items"]})

    def test_scope_guard_refuses_an_edit_outside_the_section(self):
        before = self.head()
        self.edit("POST /orders accepts a body.", "POST /orders returns 201.")
        self.edit("one row per order.", "one row per order line.")
        r = self.commit()
        self.assertEqual(r.returncode, 2)
        self.assertIn("outside", r.stderr)
        self.assertIn("order-api", r.stderr)
        self.assertEqual(self.head(), before)

    def test_anchor_guard_refuses_a_pointed_rename_unless_told(self):
        self.edit("## Order API", "## Orders API")
        r = self.commit()
        self.assertEqual(r.returncode, 2)
        self.assertIn("E003-S01-001.md", r.stderr)
        self.assertIn("--rename-anchor", r.stderr)
        r = self.commit("--rename-anchor", "order-api=orders-api")
        self.assertEqual(r.returncode, 0, r.stderr)
        story_rel = f"{IMPL}/epic-003/sprint-01/stories/E003-S01-001.md"
        self.assertIn(f"Spec: {ARCH_REL}#orders-api", self.read(story_rel))
        self.assertEqual(sorted(self.git("show", "--name-only", "--format=", "HEAD").split()),
                         sorted([ARCH_REL, story_rel]))
        self.assertEqual(self.disp()["findings"]["AD-1"]["spec"], f"{ARCH_REL}#orders-api")

    def test_rename_anchor_target_must_exist(self):
        self.edit("## Order API", "## Orders API")
        r = self.commit("--rename-anchor", "order-api=no-such")
        self.assertEqual(r.returncode, 2)
        self.assertIn("no-such", r.stderr)

    def test_only_the_named_paths_are_committed(self):
        self.write("README.md", "changed, not committed\n")
        self.write("other.txt", "staged by someone else\n")
        self.git("add", "other.txt")
        self.edit("POST /orders accepts a body.", "POST /orders returns 201.")
        self.assertEqual(self.commit().returncode, 0)
        self.assertIn("README.md", self.git("diff", "--name-only").split())
        self.assertIn("other.txt", self.git("diff", "--cached", "--name-only").split())

    def test_the_lease_is_required(self):
        self.sa("lease", "release", "--owner", "E003")
        self.edit("POST /orders accepts a body.", "POST /orders returns 201.")
        r = self.commit()
        self.assertEqual(r.returncode, 2)
        self.assertIn("lease", r.stderr)

    def test_paths_must_be_the_pointed_file(self):
        self.edit("POST /orders accepts a body.", "POST /orders returns 201.")
        r = self.sa("commit", "--epic", "E003", "--finding", "AD-1", "--paths", "README.md")
        self.assertEqual(r.returncode, 2)

    def test_a_proposal_item_is_never_committed(self):
        r = self.sa("commit", "--epic", "E003", "--finding", "AD-3", "--paths", PRD_REL)
        self.assertEqual(r.returncode, 2)
        self.assertIn("propose", r.stderr)

    def test_a_committed_findings_disposition_cannot_change(self):
        self.edit("POST /orders accepts a body.", "POST /orders returns 201.")
        self.assertEqual(self.commit().returncode, 0)
        r = self.sa("disposition", "--review", self.review, "--finding", "AD-1",
                    "--disposition", "resolved-in-code")
        self.assertEqual(r.returncode, 2)
        self.assertIn("already applied", r.stderr)

    def test_a_briefly_locked_index_is_retried(self):
        self.edit("POST /orders accepts a body.", "POST /orders returns 201.")
        lock = self.path(".git/index.lock")
        with open(lock, "w"):
            pass
        # 1.2 s outlasts interpreter start-up + the diff, so the first attempts really do
        # hit the lock (backoff 0.2, 0.4, 0.8 s) and a later one succeeds.
        threading.Timer(1.2, os.remove, [lock]).start()
        r = self.commit()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_stuck_index_lock_gives_up(self):
        self.edit("POST /orders accepts a body.", "POST /orders returns 201.")
        lock = self.path(".git/index.lock")
        with open(lock, "w"):
            pass
        self.addCleanup(lambda: os.path.exists(lock) and os.remove(lock))
        r = self.commit()
        self.assertEqual(r.returncode, 2)
        self.assertIn("stayed locked", r.stderr)

    def _adr(self):
        self.write("docs/adr/0001-order-api.md",
                   adr(1, "order-api", departs=f"{ARCH_REL}#order-api"))
        self.git("add", "docs/adr/0001-order-api.md")
        self.git("commit", "-q", "-m", "adr")

    def test_an_adr_link_commit(self):
        self._adr()
        self.edit("POST /orders accepts a body.",
                  "POST /orders accepts a body. See [ADR-0001](../../docs/adr/0001-order-api.md).")
        r = self.sa("commit", "--epic", "E003", "--adr", "docs/adr/0001-order-api.md",
                    "--paths", ARCH_REL)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.git("log", "-1", "--format=%s").startswith(
            "docs(spec): E003 link ADR-0001 from "))
        self.assertEqual(self.disp()["adr_links"]["ADR-0001"]["commit"], self.head())
        self.assertNotIn("ADR-0001", {i["id"] for i in self.plan()["items"]})

    def test_an_adr_link_commit_without_the_link_is_refused(self):
        self._adr()
        self.edit("POST /orders accepts a body.", "POST /orders returns 201.")
        r = self.sa("commit", "--epic", "E003", "--adr", "docs/adr/0001-order-api.md",
                    "--paths", ARCH_REL)
        self.assertEqual(r.returncode, 2)
        self.assertIn("does not link", r.stderr)
````

Run: SA-TEST
Expected: the new tests fail (`invalid choice: 'commit'`).

- [ ] **Step 2: Implement.** After `cmd_propose`:

````python
# -- git and the guarded docs(spec) commit ----------------------------------------------------- #

class IndexLocked(Exception):
    pass


def _git(ctx, *args, check=True):
    try:
        r = subprocess.run(["git", "-C", ctx.project, *args], capture_output=True, text=True)
    except OSError as e:
        raise SAError(2, f"git is not available: {e}")
    if check and r.returncode != 0:
        raise SAError(2, f"git {' '.join(args)} failed: {(r.stderr or r.stdout).strip()}")
    return r


def git_commit(ctx, message, paths):
    """`git commit -s --only -- paths`: exactly those paths, even in a checkout other agents
    share. A held index.lock is retried with backoff (tenacity), then refused."""
    from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

    @retry(retry=retry_if_exception_type(IndexLocked), reraise=True,
           stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.2, max=2))
    def attempt():
        r = _git(ctx, "commit", "-s", "--only", "-m", message, "--", *paths, check=False)
        if r.returncode != 0:
            err = (r.stderr or r.stdout).strip()
            if "index.lock" in err:
                raise IndexLocked(err)
            raise SAError(2, f"git commit failed: {err}")

    try:
        attempt()
    except IndexLocked as e:
        raise SAError(2, f"the git index stayed locked after 5 attempts: {e}")
    return _git(ctx, "rev-parse", "HEAD").stdout.strip()


def changed_hunks(ctx, rel):
    from unidiff import PatchSet
    diff = _git(ctx, "diff", "-U0", "HEAD", "--", rel).stdout
    if not diff.strip():
        return []
    return [(h.source_start, h.source_length) for pf in PatchSet(diff) for h in pf]


def hunks_outside(hunks, sec):
    """Hunks (in HEAD line numbers) not contained in the section. A pure insertion
    (length 0) lands after line `start`, which must itself be inside the section."""
    bad = []
    for start, length in hunks:
        inside = (sec.start <= start <= sec.end) if length == 0 else (
            sec.start <= start and start + length - 1 <= sec.end)
        if not inside:
            bad.append((start, length))
    return bad


def _pointer_re(rel, anchor):
    return re.compile(rf"^(\s*(?:[-*]\s+)?Spec:\s*){re.escape(rel)}#{re.escape(anchor)}(\s*)$",
                      re.M)


def pointing_stories(ctx, rel, anchor):
    pat = _pointer_re(rel, anchor)
    return [s for s in all_story_files(ctx) if pat.search(read_text(s))]


def rewrite_pointer(path, rel, old, new):
    pat = _pointer_re(rel, old)
    atomic_write(path, pat.sub(lambda m: f"{m.group(1)}{rel}#{new}{m.group(2)}",
                               read_text(path)))


def adr_link_item(ctx, nnn, path):
    """The adr-link item for an ADR, built from its own metadata -- not from sync-plan, whose
    gap disappears the moment the agent has written the link this commit is for."""
    ident = adr_ident(ctx, path)
    rows = [x for x in all_adrs(ctx) if x["path"] == ctx.rel(ctx.abs(path))]
    if not rows or rows[0]["epic"] != f"E{nnn}":
        raise SAError(2, f"{path} is not an ADR of E{nnn} (its Epic: line)")
    dep = (rows[0]["departs"] or "").strip()
    if not PTR_RE.match(dep):
        raise SAError(2, f"{path} has no `Departs from spec:` pointer to link from")
    if ident in ((load_yaml(epic_disp_path(ctx, nnn)) or {}).get("adr_links") or {}):
        raise SAError(2, f"{ident} is already linked or proposed for E{nnn}")
    return {"type": "adr-link", "id": ident, "severity": "MINOR",
            "title": f"Link {ident} from {dep}", "spec": dep, "adr": rows[0]["path"],
            "review": None, "dispositions": ctx.rel(epic_disp_path(ctx, nnn))}


def cmd_commit(ctx, a):
    ctx.need("impl", "state", "pm")
    nnn = epic_nnn(a.epic)
    holder = lease_holder(ctx)
    if not holder or holder.get("owner") != f"E{nnn}":
        raise SAError(2, f"the spec-sync lease is not held by E{nnn} -- run "
                         f"`lease acquire --owner E{nnn}` first")
    if a.finding:
        item = find_item(ctx, nnn, a.finding, load_catalog(ctx))
        if item["type"] != "spec-updated":
            raise SAError(2, f"{a.finding} is a {item['type']} item: proposals are never "
                             f"edited -- write the proposal and run `propose`")
    else:
        item = adr_link_item(ctx, nnn, a.adr)
    ident = item["id"]
    rel, anchor = PTR_RE.match(item["spec"]).groups()
    if [ctx.rel(ctx.abs(p)) for p in a.paths] != [rel]:
        raise SAError(2, f"--paths must be exactly {rel}, the file {ident} points at")
    head = _git(ctx, "show", f"HEAD:{rel}", check=False)
    if head.returncode != 0:
        raise SAError(2, f"{rel} is not committed at HEAD; spec sync edits committed specs only")
    head_secs = {s.anchor: s for s in parse_sections(head.stdout)}
    sec = head_secs.get(anchor)
    if sec is None:
        raise SAError(2, f"{rel} has no #{anchor} at HEAD")
    hunks = changed_hunks(ctx, rel)
    if not hunks:
        raise SAError(2, f"{rel} has no change to commit")
    bad = hunks_outside(hunks, sec)
    if bad:
        spots = ", ".join(f"L{s}" + (f"–{s + n - 1}" if n > 1 else "") for s, n in bad)
        raise SAError(2, f"the edit to {rel} changes line(s) outside #{anchor} "
                         f"(L{sec.start}–{sec.end} at HEAD): {spots} -- edit only that section")
    work = parse_sections(read_text(ctx.abs(rel)))
    after = {s.anchor for s in work}
    renames = {}
    for pair in a.rename_anchor:
        old, _, new = pair.partition("=")
        if not old or not new or new not in after:
            raise SAError(2, f"--rename-anchor {pair}: {new or '(empty)'} is not an anchor in "
                             f"the edited {rel}")
        renames[old] = new
    unhandled = {}
    for gone in sorted(set(head_secs) - after):
        stories = pointing_stories(ctx, rel, gone)
        if stories and gone not in renames:
            unhandled[gone] = [ctx.rel(s) for s in stories]
    if unhandled:
        detail = "; ".join(f"#{k} <- {', '.join(v)}" for k, v in unhandled.items())
        raise SAError(2, f"the edit removes anchor(s) stories point to: {detail} -- keep the "
                         f"heading, or pass --rename-anchor OLD=NEW to rewrite those pointers")
    target = renames.get(anchor, anchor)
    if item["type"] == "adr-link":
        wsec = next((s for s in work if s.anchor == target), None)
        body = read_text(ctx.abs(rel)).splitlines()[wsec.start - 1:wsec.end] if wsec else []
        if not any(os.path.basename(item["adr"]) in line for line in body):
            raise SAError(2, f"the edit does not link {item['adr']} from #{target}")
    paths = [rel]
    for old, new in renames.items():
        for s in pointing_stories(ctx, rel, old):
            rewrite_pointer(s, rel, old, new)
            paths.append(ctx.rel(s))
    message = (f"docs(spec): E{nnn} {ident} — {item['title']}" if item["type"] == "spec-updated"
               else f"docs(spec): E{nnn} link {ident} from {item['spec']}")
    sha = git_commit(ctx, message, paths)
    fields = {"commit": sha}
    if target != anchor and item["type"] == "spec-updated":
        fields["spec"] = f"{rel}#{target}"
        item["spec"] = fields["spec"]
    record_item(ctx, item, **fields)
    key = append_spec_issue(ctx, nnn, "spec-change", sha, ident, item["title"],
                            item["severity"], item["spec"], item["review"] or item["adr"])
    record_item(ctx, item, issue=key)
    print(f"OK commit {sha[:12]} {ident} -> {key}")
    return 0
````

Parser block:

```python
    co = sub.add_parser("commit", help="guarded docs(spec) commit for one finding or ADR link")
    co.add_argument("--epic", required=True)
    g = co.add_mutually_exclusive_group(required=True)
    g.add_argument("--finding", default="")
    g.add_argument("--adr", default="")
    co.add_argument("--paths", nargs="+", required=True, help="exactly the pointed-to spec file")
    co.add_argument("--rename-anchor", action="append", default=[], metavar="OLD=NEW")
    co.set_defaults(func=cmd_commit)
```

- [ ] **Step 3: Run the tests and confirm they pass**

Run: SA-TEST
Expected: `OK` (70 tests).

- [ ] **Step 4: Non-hollow proofs.** Do each of the following, rerunning the named test and
  confirming it FAILS before restoring the code:
  1. Make `hunks_outside` return `[]` →
     `test_scope_guard_refuses_an_edit_outside_the_section`.
  2. Replace `if unhandled:` with `if False:` →
     `test_anchor_guard_refuses_a_pointed_rename_unless_told`.
  3. In `git_commit`, replace `"--only", "-m", message, "--", *paths` with `"-m", message`,
     so that it commits whatever is staged →
     `test_only_the_named_paths_are_committed`. Dropping `--only` alone proves nothing,
     because `git commit -- <paths>` already implies it.
  Record all three in the report.

- [ ] **Step 5: Sync, run the gates, and commit** with the subject
  `feat(l3io-pm): spec-align commit with scope and anchor guards`.

---
### Task 11: `reject` and `check-stale`

**Files:**
- Modify: `skills/_shared/spec-align.py`:
  - add `import time` to the import block, in alphabetical order after `tempfile`;
  - add a reject/stale block after `cmd_commit`;
  - add two parser blocks.
- Modify: `skills/_shared/tests/test-spec-align.py`.
- Generated: the copies and manifests.

**Interfaces:**
- **Consumes:** `_pm`, `_git`, `ISSUE_KEY_RE`, and the kind/ref items from Task 2.
- **Produces:**
  - `_open_items(ctx, *extra) -> [item dict]`, read through `pm-status list-issues`.
  - `reject --key K`: a `spec-change` is reverted with `git revert --no-edit --signoff`,
    which aborts on conflict; a `spec-proposal` is declined. Either way the item is resolved
    `wontfix` (ref = the revert SHA, or the proposal path), and a new defect is appended with
    the title `Code diverges from spec: …`, the source `spec-reject (K)`, and the item's
    severity.
  - `check-stale`: exit 1 when a later commit touches a file an unconfirmed `spec-change`
    edited.

- [ ] **Step 1: Write the failing tests** (before `__main__`):

````python
class TestRejectAndStale(SyncBase):
    def setUp(self):
        super().setUp()
        self.sa("lease", "acquire", "--owner", "E003", "--wait-minutes", "0")
        text = self.read(ARCH_REL).replace("POST /orders accepts a body.",
                                           "POST /orders accepts a body; returns 201.")
        self.write(ARCH_REL, text)
        r = self.sa("commit", "--epic", "E003", "--finding", "AD-1", "--paths", ARCH_REL)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.sa("lease", "release", "--owner", "E003")
        self.spec_sha = self.git("rev-parse", "HEAD").strip()
        self.key = self.disp()["findings"]["AD-1"]["issue"]

    def commit_all(self, msg):
        self.git("add", ARCH_REL)
        self.git("commit", "-q", "-m", msg)

    def test_reject_reverts_resolves_and_refiles_the_drift(self):
        r = self.sa("reject", "--key", self.key)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.git("log", "-1", "--format=%s").startswith(
            'Revert "docs(spec): E003 AD-1'))
        self.assertEqual(self.read(ARCH_REL), ARCH)
        [res] = [i for i in self.issues("", resolved=True) if i["key"] == self.key]
        self.assertEqual(res["resolution"], "wontfix")
        self.assertEqual(res["ref"], self.git("rev-parse", "HEAD").strip())
        [fix] = self.issues("defect")
        self.assertEqual(fix["title"], "Code diverges from spec: Orders bypass the repository")
        self.assertEqual(fix["source"], f"spec-reject ({self.key})")
        self.assertEqual(fix["severity"], "Medium")

    def test_a_conflicting_revert_aborts_and_leaves_the_item_open(self):
        self.write(ARCH_REL, self.read(ARCH_REL).replace("returns 201.", "returns 202."))
        self.commit_all("later edit on the same line")
        before = self.git("rev-parse", "HEAD").strip()
        r = self.sa("reject", "--key", self.key)
        self.assertEqual(r.returncode, 2)
        self.assertIn("conflicts", r.stderr)
        self.assertIn("stays open", r.stderr)
        self.assertFalse(os.path.exists(self.path(".git/REVERT_HEAD")))
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), before)
        self.assertEqual([i["key"] for i in self.issues("spec-change")], [self.key])

    def test_rejecting_a_proposal_declines_it_without_git(self):
        deferred = {d["id"]: d for d in self.plan("--defer")["deferred"]}
        key = deferred["AD-3"]["issue"]
        before = self.git("rev-parse", "HEAD").strip()
        r = self.sa("reject", "--key", key)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), before)
        [res] = [i for i in self.issues("", resolved=True) if i["key"] == key]
        self.assertEqual(res["ref"], deferred["AD-3"]["proposal"])
        self.assertIn("High", {i["severity"] for i in self.issues("defect")})

    def test_reject_refuses_a_defect(self):
        self.pm("append-issue", "--state-root", self.state, "--epic", "003", "--sprint", "",
                "--title", "A bug", "--source", "qa (Q-1)", "--severity", "Low",
                "--description", "d")
        key = self.issues("defect")[0]["key"]
        r = self.sa("reject", "--key", key)
        self.assertEqual(r.returncode, 2)
        self.assertIn("spec-change and spec-proposal items only", r.stderr)

    def test_check_stale_reports_an_unconfirmed_change_that_was_built_upon(self):
        r = self.sa("check-stale")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.write(ARCH_REL, self.read(ARCH_REL) + "\n## Events\n\nKafka.\n")
        self.commit_all("built on top")
        r = self.sa("check-stale")
        self.assertEqual(r.returncode, 1)
        self.assertIn(self.key, r.stdout)
        self.assertIn("1 later commit", r.stdout)
````

Run: SA-TEST
Expected: the new tests fail (`invalid choice: 'reject'`).

- [ ] **Step 2: Implement.** Add `import time` to the imports. After `cmd_commit`:

````python
# -- confirm/reject support ------------------------------------------------------------------- #

def _open_items(ctx, *extra):
    ctx.need("state", "pm")
    r = _pm(ctx, "list-issues", "--state-root", ctx.state_root, "--format", "json", *extra)
    if r.returncode != 0:
        raise SAError(2, f"list-issues failed: {(r.stderr or r.stdout).strip()}")
    return json.loads(r.stdout or "[]")


def cmd_reject(ctx, a):
    it = next((i for i in _open_items(ctx) if i.get("key") == a.key), None)
    if it is None:
        raise SAError(2, f"{a.key} is not an open backlog item")
    kind = it.get("kind") or "defect"
    if kind not in ("spec-change", "spec-proposal"):
        raise SAError(2, f"{a.key} is a {kind} item; reject handles spec-change and "
                         f"spec-proposal items only")
    ref = str(it.get("ref") or "")
    if kind == "spec-change":
        r = _git(ctx, "revert", "--no-edit", "--signoff", ref, check=False)
        if r.returncode != 0:
            conflicts = _git(ctx, "diff", "--name-only", "--diff-filter=U",
                             check=False).stdout.split()
            _git(ctx, "revert", "--abort", check=False)
            raise SAError(2, f"git revert {ref} conflicts in "
                             f"{', '.join(conflicts) or '(see git status)'}; aborted -- "
                             f"{a.key} stays open. Revert by hand, then resolve it.")
        res_ref = _git(ctx, "rev-parse", "HEAD").stdout.strip()
    else:
        res_ref = ref
    r = _pm(ctx, "resolve-issue", "--state-root", ctx.state_root, "--key", a.key,
            "--resolution", "wontfix", "--ref", res_ref, "--note",
            f"{kind} rejected in triage", "--cause", "triage")
    if r.returncode != 0:
        raise SAError(2, f"resolve-issue failed after {res_ref}: "
                         f"{(r.stderr or r.stdout).strip()}")
    title = re.sub(r"^Spec (change|proposal):\s*", "", str(it.get("title", "")))
    args = ["append-issue", "--state-root", ctx.state_root, "--epic", str(it.get("epic", "")),
            "--sprint", "", "--title", f"Code diverges from spec: {title}",
            "--source", f"spec-reject ({a.key})", "--severity", str(it.get("severity") or "Medium"),
            "--description", (f"{kind} {a.key} was rejected, so the code must change to match "
                              f"the spec. {it.get('description') or ''}").strip()]
    r = _pm(ctx, *args)
    m = ISSUE_KEY_RE.search(r.stdout)
    if r.returncode != 0 or not m:
        raise SAError(2, f"{a.key} is resolved but the code fix was not filed -- rerun: "
                         f"pm-status.py {' '.join(args)}")
    print(f"OK reject {a.key} ({kind}) -> wontfix {res_ref}; code fix {m.group(1)}")
    return 0


def cmd_check_stale(ctx, a):
    items = _open_items(ctx, "--kind", "spec-change")
    findings = []
    for it in items:
        ref = str(it.get("ref") or "")
        if not ref:
            continue                                  # audit-issues 1k reports a missing ref
        files = _git(ctx, "show", "--name-only", "--format=", ref, check=False).stdout.split()
        if not files:
            findings.append(f"{it['key']}: its commit {ref} is not in this repository")
            continue
        later = _git(ctx, "log", "--format=%h", f"{ref}..HEAD", "--", *files,
                     check=False).stdout.split()
        if later:
            ct = _git(ctx, "show", "-s", "--format=%ct", ref, check=False).stdout.strip()
            age = f"{(time.time() - int(ct)) / 86400:.0f} day(s) old, " if ct.isdigit() else ""
            findings.append(f"{it['key']}: unconfirmed spec change {ref[:12]} ({age}"
                            f"{len(later)} later commit(s) on {', '.join(files)}) -- confirm "
                            f"or reject it in /l3io-util-doctor triage")
    for f in findings:
        print(f)
    if findings:
        return 1
    print(f"OK check-stale: {len(items)} unconfirmed spec change(s), none built upon")
    return 0
````

Parser blocks:

```python
    rj = sub.add_parser("reject", help="revert/decline a spec item and refile it as a code fix")
    rj.add_argument("--key", required=True)
    rj.set_defaults(func=cmd_reject)

    cs = sub.add_parser("check-stale", help="report unconfirmed spec changes built upon")
    cs.set_defaults(func=cmd_check_stale)
```

- [ ] **Step 3: Run the tests and confirm they pass**

Run: SA-TEST
Expected: `OK` (75 tests).

- [ ] **Step 4: Non-hollow proof.** Remove the `_git(ctx, "revert", "--abort", check=False)`
  line, and rerun `test_a_conflicting_revert_aborts_and_leaves_the_item_open`. It must FAIL
  (`REVERT_HEAD` remains). Restore.

- [ ] **Step 5: Sync, run the gates, and commit** with the subject
  `feat(l3io-pm): spec-align reject and check-stale`.

---

### Task 12: `migrate-adrs`

**Files:**
- Modify: `skills/_shared/spec-align.py`. Add a migration block after `cmd_check_stale`,
  and one parser block.
- Modify: `skills/_shared/tests/test-spec-align.py`.
- Generated: the copies and manifests.

**Interfaces:**
- **Consumes:** `_git`, `_pm` (`adr-reserve … --adr-dir`, from Task 3), `git_commit`,
  `DOC_ADR_RE`, `LEGACY_ADR_RE`, `load_yaml`.
- **Produces:** `migrate-adrs --plan | --apply`. Both print JSON with these keys:
  - `moves`: `[{from, number, slug, epic, collision, to, renumbered_to?}]`
  - `register`: `{next, highest_on_disk, lagging}`
  - `rewritten`: `[file]`
  - `review`: `[{file, line, text}]`
  - `commit`: `sha | null`

  `--plan` writes nothing. Doctor Check 15 and the `migrate-adrs` mode read this output
  (Task 16).

- [ ] **Step 1: Write the failing tests** (before `__main__`):

````python
class TestMigrateAdrs(Project):
    def setUp(self):
        super().setUp()
        self.write("docs/adr/0003-stack.md", adr(3, "stack", epic="n/a"))
        self.write(f"{IMPL}/epic-001/arch/adr-0003-auth.md",
                   "# ADR-0003: auth\n\n- **Status:** Accepted\n\n## Context\n\nx\n")
        self.write(f"{IMPL}/epic-001/arch/adr-0004-cache.md",
                   "# ADR-0004: cache\n\n- **Status:** Accepted\n\n## Context\n\ny\n")
        self.s1 = f"{IMPL}/epic-001/sprint-01/stories/E001-S01-001.md"
        self.s2 = f"{IMPL}/epic-002/sprint-01/stories/E002-S01-001.md"
        self.write(self.s1, f"# S\n\nPer ADR-0003 and {IMPL}/epic-001/arch/adr-0004-cache.md.\n")
        self.write(self.s2, "# S\n\nPer ADR-0003 (the stack).\n")
        self.init_git()

    def run_json(self, *args):
        r = self.sa("migrate-adrs", *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_plan_is_read_only(self):
        out = self.run_json("--plan")
        moves = {m["from"]: m for m in out["moves"]}
        self.assertTrue(moves[f"{IMPL}/epic-001/arch/adr-0003-auth.md"]["collision"])
        self.assertEqual(moves[f"{IMPL}/epic-001/arch/adr-0004-cache.md"]["to"],
                         "docs/adr/0004-cache.md")
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_apply_moves_renumbers_rewrites_and_commits(self):
        out = self.run_json("--apply")
        self.assertEqual(self.git("log", "-1", "--format=%s").strip(),
                         "docs(adr): migrate epic ADRs to docs/adr")
        self.assertEqual(out["commit"], self.git("rev-parse", "HEAD").strip())
        # no collision: moved, Epic line added, exact path reference rewritten
        cache = self.read("docs/adr/0004-cache.md")
        self.assertIn("- **Epic:** E001", cache)
        self.assertIn("docs/adr/0004-cache.md", self.read(self.s1))
        # collision: docs/adr keeps 0003; the epic ADR gets a fresh number (disk max 4 -> 5)
        auth = self.read("docs/adr/0005-auth.md")
        self.assertTrue(auth.startswith("# ADR-0005: auth"))
        self.assertIn("ADR-0005", self.read(self.s1))           # inside epic-001: rewritten
        self.assertIn("ADR-0003", self.read(self.s2))           # elsewhere: left alone...
        self.assertIn(self.s2, {r["file"] for r in out["review"]})   # ...and listed
        self.assertFalse(os.path.exists(self.path(f"{IMPL}/epic-001/arch/adr-0003-auth.md")))
        tracked = self.git("ls-files", "docs/adr").split()
        self.assertEqual(sorted(tracked), ["docs/adr/0003-stack.md", "docs/adr/0004-cache.md",
                                           "docs/adr/0005-auth.md"])
        self.assertEqual(self.git("status", "--porcelain", "--", "docs", IMPL).strip(), "")

    def test_nothing_to_move(self):
        self.git("rm", "-q", "-r", f"{IMPL}/epic-001/arch")
        self.git("commit", "-q", "-m", "no legacy")
        out = self.run_json("--apply")
        self.assertEqual((out["moves"], out["commit"]), ([], None))

    def test_register_lag_is_reported(self):
        with open(os.path.join(self.state, "adr-register.yaml"), "w", encoding="utf-8") as fh:
            fh.write("next: 2\nreserved: []\n")
        reg = self.run_json("--plan")["register"]
        self.assertEqual(reg, {"next": 2, "highest_on_disk": 4, "lagging": True})
````

Run: SA-TEST
Expected: the new tests fail (`invalid choice: 'migrate-adrs'`).

- [ ] **Step 2: Implement.** After `cmd_check_stale`:

````python
# -- migrate-adrs: the old per-epic home -> docs/adr (ADR-0005) ------------------------------- #

def _migration_plan(ctx):
    ctx.need("impl", "state")
    docs_dir = os.path.join(ctx.project, "docs", "adr")
    docs_nums = set()
    if os.path.isdir(docs_dir):
        docs_nums = {int(m.group(1)) for m in map(DOC_ADR_RE.match, os.listdir(docs_dir)) if m}
    moves, taken = [], set(docs_nums)
    for p in sorted(glob.glob(os.path.join(ctx.impl, "epic-*", "arch", "adr-*.md"))):
        m = LEGACY_ADR_RE.match(os.path.basename(p))
        em = re.search(r"epic-(\d{3})", os.path.basename(os.path.dirname(os.path.dirname(p))))
        if not (m and em):
            continue
        n, slug = int(m.group(1)), m.group(2)
        moves.append({"from": ctx.rel(p), "number": n, "slug": slug, "epic": f"E{em.group(1)}",
                      "collision": n in taken,
                      "to": None if n in taken else f"docs/adr/{n:04d}-{slug}.md"})
        taken.add(n)
    reg = load_yaml(os.path.join(ctx.state_root, "adr-register.yaml")) or {}
    try:
        nxt = int(reg.get("next", 1))
    except (TypeError, ValueError):
        nxt = 1
    hi = max([*docs_nums, *(mv["number"] for mv in moves)], default=0)
    return {"moves": moves,
            "register": {"next": nxt, "highest_on_disk": hi, "lagging": hi > 0 and nxt <= hi},
            "rewritten": [], "review": [], "commit": None}


def _add_epic_line(text, ek):
    if re.search(r"^-\s+\*\*Epic:\*\*", text, re.M):
        return text
    text2, n = re.subn(r"^(-\s+\*\*Status:\*\*.*)$", rf"\1\n- **Epic:** {ek}", text,
                       count=1, flags=re.M)
    return text2 if n else re.sub(r"^(#[^\n]*\n)", rf"\1\n- **Epic:** {ek}\n", text, count=1)


def cmd_migrate_adrs(ctx, a):
    plan = _migration_plan(ctx)
    if a.plan or not plan["moves"]:
        print(json.dumps(plan, indent=2))
        return 0
    if _git(ctx, "rev-parse", "--is-inside-work-tree", check=False).stdout.strip() != "true":
        raise SAError(2, "migrate-adrs --apply needs a git work tree")
    docs_dir = os.path.join(ctx.project, "docs", "adr")
    os.makedirs(docs_dir, exist_ok=True)
    md_files = sorted(set(glob.glob(os.path.join(ctx.impl, "**", "*.md"), recursive=True)))
    other_docs = sorted(glob.glob(os.path.join(ctx.project, "docs", "**", "*.md"),
                                  recursive=True))
    commit_paths, rewritten = [], set()
    for mv in plan["moves"]:
        old, nnn = mv["number"], mv["epic"][1:]
        new = old
        if mv["collision"]:
            r = _pm(ctx, "adr-reserve", "--state-root", ctx.state_root, "--epic", mv["epic"],
                    "--slug", f"migrate-{mv['slug']}", "--adr-dir", docs_dir)
            if r.returncode != 0 or not r.stdout.split():
                raise SAError(2, f"adr-reserve failed: {(r.stderr or r.stdout).strip()}")
            new = int(r.stdout.split()[0])
            mv["renumbered_to"] = new
            mv["to"] = f"docs/adr/{new:04d}-{mv['slug']}.md"
        tracked = _git(ctx, "ls-files", "--error-unmatch", "--", mv["from"],
                       check=False).returncode == 0
        if tracked:
            _git(ctx, "mv", "--", mv["from"], mv["to"])
            commit_paths += [mv["from"], mv["to"]]
        else:
            os.replace(ctx.abs(mv["from"]), ctx.abs(mv["to"]))
            _git(ctx, "add", "--", mv["to"])
            commit_paths.append(mv["to"])
        body = read_text(ctx.abs(mv["to"]))
        if new != old:
            body = re.sub(rf"\bADR-{old:04d}\b", f"ADR-{new:04d}", body)
        atomic_write(ctx.abs(mv["to"]), _add_epic_line(body, mv["epic"]))
        path_re = re.compile(rf"[\w./-]*epic-{nnn}/arch/adr-{old:04d}-{re.escape(mv['slug'])}\.md")
        num_re = re.compile(rf"\bADR-{old:04d}\b")
        epic_tree = os.path.join(ctx.impl, f"epic-{nnn}")
        for f in md_files:
            if not os.path.isfile(f):
                continue
            text = read_text(f)
            inside = _under(f, epic_tree)
            if new != old and not inside:
                for i, line in enumerate(text.splitlines(), 1):
                    if num_re.search(line):
                        plan["review"].append({"file": ctx.rel(f), "line": i,
                                               "text": line.strip()})
            text2 = path_re.sub(mv["to"], text)
            if new != old and inside:
                text2 = num_re.sub(f"ADR-{new:04d}", text2)
            if text2 != text:
                atomic_write(f, text2)
                rewritten.add(ctx.rel(f))
        if new != old:
            for f in other_docs:
                if re.match(rf"{old:04d}-", os.path.basename(f)) and _under(f, docs_dir):
                    continue                          # that number's rightful owner
                for i, line in enumerate(read_text(f).splitlines(), 1):
                    if num_re.search(line):
                        plan["review"].append({"file": ctx.rel(f), "line": i,
                                               "text": line.strip()})
    for rel in sorted(rewritten):
        if _git(ctx, "ls-files", "--error-unmatch", "--", rel, check=False).returncode == 0:
            commit_paths.append(rel)
        else:
            sys.stderr.write(f"WARN {rel} was rewritten but is not tracked; not committed\n")
    plan["rewritten"] = sorted(rewritten)
    plan["commit"] = git_commit(ctx, "docs(adr): migrate epic ADRs to docs/adr",
                                list(dict.fromkeys(commit_paths)))
    print(json.dumps(plan, indent=2))
    return 0
````

Parser block:

```python
    mi = sub.add_parser("migrate-adrs", help="move ADRs from epic-*/arch/ to docs/adr/")
    g = mi.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan", action="store_true")
    g.add_argument("--apply", action="store_true")
    mi.set_defaults(func=cmd_migrate_adrs)
```

- [ ] **Step 3: Run the tests and confirm they pass**

Run: SA-TEST
Expected: `OK` (79 tests). If
`test_apply_moves_renumbers_rewrites_and_commits` fails on the git status assertion because
the moved ADR's Epic-line edit is uncommitted, check that `git_commit` receives `mv["to"]`
(it is in `commit_paths`). `--only` then commits the edited working-tree content.

- [ ] **Step 4: Non-hollow proof.** Delete `if new != old and inside:` together with its
  `num_re.sub` line, and rerun the apply test. It must FAIL (epic-001 still says ADR-0003).
  Restore.

- [ ] **Step 5: Sync, run the gates, and commit** with the subject
  `feat(l3io-util): spec-align migrate-adrs (old epic ADR home -> docs/adr)`.

---
### Task 13: pm-execute wiring — the binding, the switch, and the arch gate

**Files:**
- Modify: `skills/l3io-pm-execute/SKILL.md` (Conventions list)
- Modify: `skills/l3io-pm-execute/customize.toml` (after the Concurrency block)
- Modify: `skills/_shared/steps/execute/step-05-epic-loop.md` (context blocks 5a and 5b)
- Modify: `skills/_shared/steps/execute/step-04-arch-gate.md` (§3, §4, §6)
- Modify: `docs/l3io-pm-reference.md` ("Architecture gate (step-04)")
- Generated: the execute-step copies and the pm-execute manifest

**Interfaces:**
- **Produces:**
  - Bindings: `{spec_align}` (the command prefix, global flags included) and
    `{spec_alignment}` (`true`/`false`).
  - Customize keys: `spec_alignment` and `spec_paths`.
  - Arch gate bindings: `{spec_index_path}` and `{spec_sections}`.
  - ADR subagents write to `{project-root}/docs/adr/`.
- **Consumed by:** Tasks 14–15, which use the same `{spec_align}` form, and check 4 (Task 18),
  which validates every `{spec_align} <sub>` against the real CLI.

- [ ] **Step 1: The binding.** In `skills/l3io-pm-execute/SKILL.md`'s `## Conventions`
  list, append:

```markdown
- `{spec_align}` = `uv run {skill-root}/scripts/spec-align.py --project-root {project-root} --planning-root {planning_artifacts} --impl-root {implementation_artifacts} --state-root {implementation_artifacts}/state --pm-status {project-root}/_bmad/scripts/pm-status.py --spec-paths '{spec_paths}'` — the spec-alignment helper; it never calls a model. `{spec_paths}` is `customize.toml`'s list rendered as JSON (`[]` by default). Step files run it only where `{spec_alignment}` is `true`, except `disposition`, `check-dispositions` and `adrs`, which run either way. Headless sprint subagents receive both bindings in their context block (`steps/execute/step-05-epic-loop.md` §5a).
```

- [ ] **Step 2: The switch.** In `skills/l3io-pm-execute/customize.toml`, after the
  `# Concurrency` block:

```toml

# Spec alignment (docs/adr/0004-agents-edit-architecture-specs.md in the package repo)
spec_alignment = true   # spec index to reviewers, Spec: pointers at story prep, epic-closure spec sync
spec_paths     = []     # replaces spec discovery: project-root-relative paths/globs; [] = discover under planning_artifacts
```

- [ ] **Step 3: The context blocks.** In `step-05-epic-loop.md` there are two blocks:
  5a, the prep block, which the closure dispatch reuses, and 5b, the story block. In each,
  directly after the line `execute_skill_root: {skill-root}`, insert:

```
spec_alignment: {spec_alignment}
spec_align: uv run {skill-root}/scripts/spec-align.py --project-root {project-root} --planning-root {planning_artifacts} --impl-root {implementation_artifacts} --state-root {implementation_artifacts}/state --pm-status {project-root}/_bmad/scripts/pm-status.py --spec-paths '{spec_paths}'
```

Verify with `grep -c "^spec_align: uv run" skills/_shared/steps/execute/step-05-epic-loop.md`.
It must print `2`.

- [ ] **Step 4: Arch gate §3.** Directly after the line
  `Bind \`{story_file_paths}\` = full list of story markdown files across all sprints of the scoped epics.`,
  insert:

````markdown

**Spec inputs (when `{spec_alignment}` is `true`).** Refresh the spec index and turn the
stories' `Spec:` pointers into line ranges. Neither step calls a model, and `build --if-stale`
rewrites nothing when the specs are unchanged:

```bash
{spec_align} build --if-stale
{spec_align} sections --stories {story_file_paths}
```

Bind `{spec_index_path}` = `{implementation_artifacts}/spec/spec-index.md` and
`{spec_sections}` = the `sections` output, one `path#anchor Lstart–end` per line. Stories
prepared before spec alignment carry no pointers, so `{spec_sections}` may be short or
`(no resolvable pointers)`; the index still goes to the reviewer.
````

- [ ] **Step 5: Arch gate §4.** In the input list, directly after
  `- l3io-pm context preamble (work_type, epic key, sprint plan)`, insert:

```markdown
- When `{spec_alignment}` is `true`: `{spec_index_path}` and `{spec_sections}` — the specs by
  pointer, never whole. Open only those line ranges; when a story needs a section it does not
  point to, pick that one section from the index. End the review with a `Sections read:`
  footer listing every range opened.
```

Then replace the line
`  - \`l3io-arch-review\`: invoke as Mode B (architectural review of existing design)` with:

```markdown
  - `l3io-arch-review`: invoke as Mode B (architectural review of existing design). When
    `{spec_alignment}` is `true`, also check each story against the spec sections it points
    to: a story that contradicts its spec is a `spec-conflict` finding, and a story that needs
    a decision its spec does not make is a `spec-gap` finding — both at the usual severities.
```

- [ ] **Step 6: Arch gate §6.** Replace

```
python3 {pm_status} adr-reserve --state-root {pm_state_root} --epic {epic_key} \
  --slug arch-gate --count {blocking_finding_count}
```

with

```
python3 {pm_status} adr-reserve --state-root {pm_state_root} --epic {epic_key} \
  --slug arch-gate --count {blocking_finding_count} --adr-dir {project-root}/docs/adr
```

and replace the two lines

```
- Draft an ADR at `{implementation_artifacts}/epic-{epic_nnn}/arch/adr-{adr_number}-{slug}.md`
  using the number you were given. Do not derive it, do not list the directory to check it.
```

with

```
- Draft an ADR at `{project-root}/docs/adr/{adr_number}-{slug}.md` — the one ADR home — from
  `l3io-arch-review/assets/adr-template.md`, using the number you were given. Do not derive
  it, do not list the directory to check it. Fill `- **Epic:** {epic_key}`, and fill
  `- **Departs from spec:**` with the `path#anchor` of the spec section the decision departs
  from, or `n/a`.
```

Confirm nothing else in the file names the old home:
`grep -n "arch/adr-" skills/_shared/steps/execute/step-04-arch-gate.md` must print nothing.
`arch/arch-gate-review.md` stays; it is a review, not an ADR.

- [ ] **Step 7: The reference doc.** In `docs/l3io-pm-reference.md` "Architecture gate
  (step-04)", make three changes:
  1. In the `adr-reserve … --count\n{blocking_finding_count}` command, append
     ` --adr-dir {project-root}/docs/adr`.
  2. Replace
     `written\nto \`{implementation_artifacts}/epic-{nnn}/arch/adr-{adr_number}-{slug}.md\` using its reserved\nnumber`
     with
     `written\nto \`{project-root}/docs/adr/{adr_number}-{slug}.md\` (the one ADR home, ADR-0005) using its reserved\nnumber, with its \`Epic:\` and \`Departs from spec:\` lines filled`.
  3. Before the paragraph starting "Zero findings on non-trivial CODE scope", add:

```markdown
With `spec_alignment` on (the default, pm-execute `customize.toml`), the reviewer also receives
the spec index (`{implementation_artifacts}/spec/spec-index.md`, built by
`spec-align.py build` without a model) and the line ranges the stories' `Spec:` pointers name
— never whole spec documents — and may raise `spec-conflict` and `spec-gap` findings. Every
reviewer ends with a `Sections read:` footer, so extra reading is measurable.
```

- [ ] **Step 8: Sync, run the gates, and commit**

Run: `npm run sync:scripts && node scripts/write-payload-manifest.mjs && npm run check:scripts && npm run check:docs && npm run check:manifest && npm run check:version && npm run test:scripts`
Expected: all exit 0.

Stage these paths:
- `skills/l3io-pm-execute/SKILL.md`
- `skills/l3io-pm-execute/customize.toml`
- `skills/_shared/steps/execute/step-04-arch-gate.md`
- `skills/_shared/steps/execute/step-05-epic-loop.md`
- `skills/l3io-pm-execute/steps/execute/step-04-arch-gate.md`
- `skills/l3io-pm-execute/steps/execute/step-05-epic-loop.md`
- `docs/l3io-pm-reference.md`
- `skills/l3io-pm-execute/payload-manifest.json`

Run `git status --short` to check nothing else is staged, then commit with the subject
`feat(l3io-pm): spec inputs to the arch gate; ADRs to docs/adr; spec_alignment switch`.

---

### Task 14: story prep provenance and the dev-loop fallback

**Files:**
- Modify: `skills/_shared/steps/sprint/step-02-story-prep.md` (§2)
- Modify: `skills/_shared/steps/sprint/step-03-dev-loop.md` (one sentence)
- Modify: `docs/l3io-pm-reference.md` ("The technical-AC gate — six dimensions")
- Generated: the pm-execute step copies and the manifest

**Interfaces:**
- **Consumes:** `{spec_align} build --if-stale` and `{spec_align} check-pointers --story F…`
  (exit 2 = fail), from Task 5.
- **Produces:** the enrichment prompt's layout block: an indented
  `## Technical acceptance criteria` line, then six `### <name>` lines matching
  `spec-align.py DIMENSIONS` in order. Check 13 (Task 18) parses exactly this.

- [ ] **Step 1: The provenance gate.** In §2, directly after the paragraph that ends
  `and hold the story to those standards as well.`, insert:

````markdown

**Provenance (when `{spec_alignment}` is `true`).** Every applicable dimension must also name
the spec section it came from. This is checked mechanically: no model is called, and a fresh
index is not rewritten.

```bash
{spec_align} build --if-stale
{spec_align} check-pointers --story {one {sprint_root}/stories/{story_key}.md per key in {story_keys}}
```

Bind `{spec_index_path}` = `{implementation_artifacts}/spec/spec-index.md`. Exit 0 → every
story carries a resolving `Spec:` line on each applicable dimension. Exit 2 → every story it
names on stderr fails this gate: a missing dimension, a missing or broken `Spec:` line, or no
`## Technical acceptance criteria` section at all. Add those stories to `{thin_story_keys}`
below, even if they passed the six-dimension check.
````

- [ ] **Step 2: The enrichment layout.** In the enrichment prompt, replace these lines

```
1. Enrich it with technical ACs, addressing ALL SIX dimensions, marking any that genuinely
   do not apply as "N/A — <one-line reason>" rather than omitting them:
   - Interface contracts
   - Error and edge case handling
   - Observability requirements
   - Security considerations
   - Testability approach
   - Existing-library check: name the library or platform capability that covers this work,
     or state why none does and custom code is warranted. Do not propose hand-written code
     for a problem a maintained library already solves.
```

with

```
1. Enrich it with technical ACs under exactly this layout — all six `###` headings, in this
   order. A dimension that genuinely does not apply is a paragraph starting
   "N/A — <one-line reason>", never an omitted heading:

   ## Technical acceptance criteria

   ### Interface contracts
   ### Error and edge case handling
   ### Observability requirements
   ### Security considerations
   ### Testability approach
   ### Existing-library check

   The existing-library check names the library or platform capability that covers this
   work, or states why none does and custom code is warranted. Do not propose hand-written
   code for a problem a maintained library already solves.

   Provenance (only when spec_alignment is true): end every applicable dimension with one or
   more `Spec: <path>#<anchor>` lines copied from the spec index at {spec_index_path} — cite
   the section, never copy its text — or with exactly one `Spec: none — <reason>` when no
   spec section covers it (`Spec: none — no spec docs in this project` when the index is
   empty). Open only the index and the sections you cite.
```

Then, in the prompt's tail, directly after `work_type: {work_type}`, insert:

```
spec_alignment: {spec_alignment}
Spec index: {spec_index_path}
```

- [ ] **Step 3: The re-check.** Replace

```
After enrichment, re-check every key in `{thin_story_keys}` against all six dimensions. For
any still carrying an unfilled applicable dimension:
```

with

```
After enrichment, re-check every key in `{thin_story_keys}` against all six dimensions — and,
when `{spec_alignment}` is `true`, rerun `{spec_align} check-pointers --story …` over those
story files (exit 2 is a failure). For any still carrying an unfilled applicable dimension or
a failing pointer:
```

- [ ] **Step 4: The dev loop.** In `step-03-dev-loop.md`, the sentence ending
  `…rather than widening the read for the rest of the run.` gets this appended, in the same
  paragraph:
  ` When that dimension carries a \`Spec: <path>#<anchor>\` line, the section it names is the one to open — its line range is in \`{implementation_artifacts}/spec/spec-index.md\` — and nothing wider.`

- [ ] **Step 5: The reference doc.** In "The technical-AC gate — six dimensions", after the
  paragraph ending `…are otherwise indistinguishable.`, add:

```markdown
**Provenance.** With `spec_alignment` on (the default), the ACs use a fixed layout — a
`## Technical acceptance criteria` section with one `###` heading per dimension — and each
applicable dimension ends with `Spec: <path>#<anchor>`, a pointer into the spec index, or
`Spec: none — <reason>`. `spec-align.py check-pointers` checks every story mechanically before
`ready-for-dev`; a story it rejects is enriched like any thin story. The dev loop still never
opens the spec tree: when an AC falls short, the pointer names the one section to read.
```

- [ ] **Step 6: Sync, run the gates, and commit.** Use Task 13's gate command. Stage both
  `_shared` step files, their two pm-execute copies, the reference doc and the pm-execute
  manifest. Commit with the subject
  `feat(l3io-pm): story prep requires spec provenance pointers`.

---

### Task 15: closures — dispositions, spec sync, and the epic commit checkpoint

**Files:**
- Modify: `skills/_shared/steps/closure/sprint-closure.md` (§6)
- Modify: `skills/_shared/steps/sprint/step-04-sprint-closure.md` (§9)
- Modify: `skills/_shared/steps/closure/epic-closure.md` (§2, new §2a, §3, §5, new §7)
- Modify: `docs/l3io-pm-reference.md` ("Sprint closure (step-04)", "Epic closure (step-06)")
- Generated: the copies and the manifest

**Interfaces:**
- **Consumes:** the `disposition`, `check-dispositions`, `adrs`, `build`, `sections`,
  `sync-plan`, `lease`, `commit`, `propose` and `check-pointers` subcommands.
- **Produces:** the dispatch identity `l3io-spec-sync`, which `usage --agent` reads for the
  closure report's token share.

- [ ] **Step 1: Sprint closure §6.** Replace the body of
  `## 6. Sprint architectural drift review (skip if in skip_phases)`, the five lines from
  `If \`l3io-arch-review\` is installed:` through `MINOR: defer to issues file (as \`--severity Low\` — see §7).`,
  with:

````markdown
If `l3io-arch-review` is installed: invoke Mode B (architectural review) on this sprint's
stories and **diff**, plus the ADRs and standard sections they bear on, by path — not the
repository (see §2–3). List the epic's ADRs with `{spec_align} adrs --epic {epic_key}`. Output
path: `{sprint_root}/closure/arch-drift-review.md`. Its findings table follows
`references/review-report.md`, with each ID in the `#` column as `SD-{nn}-{n}`, where `{nn}` is
this sprint's two-digit number (the `sprint-{nn}` in `{sprint_root}`) — for example `SD-02-3`.

When `{spec_alignment}` is `true`, also pass the spec index and the ranges this sprint's
pointers name:

```bash
{spec_align} build --if-stale
{spec_align} sections --stories {sprint_root}/stories/*.md
```

The reviewer opens only those ranges, plus one section picked from
`{implementation_artifacts}/spec/spec-index.md` for a diff hunk no pointer covers, and ends
with a `Sections read:` footer listing every range it opened.

Record a disposition for every BLOCKER and MAJOR finding (a MINOR may have one too), then gate
on them against the reviewer's final `Blocker: N, Major: N, Minor: N` line:

```bash
{spec_align} disposition --review {sprint_root}/closure/arch-drift-review.md \
  --finding {finding_id} --disposition {disposition} [--spec {path#anchor}] [--adr {adr path}] \
  --spec-alignment {spec_alignment}
{spec_align} check-dispositions --review {sprint_root}/closure/arch-drift-review.md \
  --expect "{the reviewer's Blocker/Major/Minor line}"
```

BLOCKER/MAJOR are resolved before the sprint is marked done. Each one is either:
- fixed in code (`resolved-in-code`);
- justified by an accepted ADR (`adr-justified`); or
- when `{spec_alignment}` is `true`, carried to epic closure as a spec edit (`spec-updated`,
  architecture sections only) or as a proposal (`spec-proposal`).

A `check-dispositions` exit 2 blocks the sprint. MINOR: defer to the issues file (as
`--severity Low` — see §7).
````

- [ ] **Step 2: Sprint closure §9.** In `step-04-sprint-closure.md`'s commit block, add
  `        {implementation_artifacts}/spec/ \` directly after the
  `{implementation_artifacts}/epic-{epic_num}/ \` line.

- [ ] **Step 3: Epic closure §2 inputs.** Replace the bullet
  `- ADR paths: \`{implementation_artifacts}/epic-{epic_nnn}/arch/*.md\`` with:

```markdown
- ADR paths: the output of `{spec_align} adrs --epic {epic_key}` — the epic's ADRs in
  `docs/adr/`, plus any still in the old per-epic home
- When `{spec_alignment}` is `true`: `{implementation_artifacts}/spec/spec-index.md` and the
  ranges from `{spec_align} build --if-stale` followed by
  `{spec_align} sections --stories {implementation_artifacts}/epic-{epic_nnn}/*/stories/*.md`.
  Open only those ranges, plus one index-picked section for a diff hunk no pointer covers,
  and end the review with a `Sections read:` footer listing every range opened.
```

- [ ] **Step 4: Epic closure §2 findings.** Replace

```
Findings:
- BLOCKER/MAJOR: must be resolved before closure completes (fix loop, max
  `{max_fix_iterations}` iterations) or recorded as an accepted ADR that justifies leaving it.
```

with

````markdown
Findings — record a disposition for every BLOCKER and MAJOR (a MINOR may have one), then gate
on them, exactly as sprint closure §6 does:

```bash
{spec_align} disposition --review {implementation_artifacts}/epic-{epic_nnn}/epic-closure/arch-drift-review.md \
  --finding {finding_id} --disposition {disposition} [--spec {path#anchor}] [--adr {adr path}] \
  --spec-alignment {spec_alignment}
{spec_align} check-dispositions --review {implementation_artifacts}/epic-{epic_nnn}/epic-closure/arch-drift-review.md \
  --expect "{the reviewer's Blocker/Major/Minor line}"
```

- BLOCKER/MAJOR: must be resolved before closure completes. Each one is either:
  - fixed in code under the fix loop (max `{max_fix_iterations}` iterations,
    `resolved-in-code`);
  - recorded as an accepted ADR that justifies leaving it (`adr-justified`); or
  - when `{spec_alignment}` is `true`, written back to the architecture spec
    (`spec-updated`) or proposed for the PRD/UX/epic docs (`spec-proposal`), both carried out
    by §2a.

  A `check-dispositions` exit 2 blocks closure.
````

(The MINOR bullet and its `append-issue` block stay exactly as they are.)

- [ ] **Step 5: Epic closure §2a.** Insert before `## 3. Epic security review`:

````markdown
## 2a. Spec sync (only when `{spec_alignment}` is `true`)

Runs after §2's fix loop. The plan costs no tokens, and it decides whether an agent runs at
all:

```bash
{spec_align} sync-plan --epic {epic_key}
```

It prints JSON `{"epic": …, "items": […]}`. **If `items` is empty, go to §3 — nothing is
dispatched.**

Otherwise take the lease. Parallel epic closures share one working tree:

```bash
{spec_align} lease acquire --owner {epic_key} --wait-minutes 15
```

**Exit 5** (still held after 15 minutes): dispatch nothing. Turn every pending item into a
pointer-only proposal and backlog item, then go to §3:

```bash
{spec_align} sync-plan --epic {epic_key} --defer
```

**Exit 0:** dispatch one agent as `--agent l3io-spec-sync --epic {epic_key}`, bracketed per
this file's dispatch rule. Give it the `items` JSON,
`{implementation_artifacts}/spec/spec-index.md` and `{agent_contract}`, with these
instructions:

- **Each `spec-updated` item.** Edit only the section its `range` names, so that the spec
  describes what was built. When the item has an ADR, add a relative link to it. Then run
  `{spec_align} commit --epic {epic_key} --finding {id} --paths {the spec file}`.
  - Exit 2 names the problem: an edit outside the section, or a renamed anchor that stories
    point to. Pass `--rename-anchor OLD=NEW` when the rename is intended.
  - Fix and retry once. On a second refusal, restore the file
    (`git -C {project-root} restore -- {the spec file}`) and handle the item as a proposal
    (below).
- **Each `adr-link` item.** Add a relative link to the ADR inside the section, then run
  `{spec_align} commit --epic {epic_key} --adr {adr} --paths {the spec file}`.
- **Each `spec-proposal` item**, and any item refused twice above. Write
  `{implementation_artifacts}/epic-{epic_nnn}/epic-closure/spec-proposals/{id}.md`, giving the
  target pointer, the proposed change, why, and the finding. Then run
  `{spec_align} propose --epic {epic_key} --finding {id}` (use `--adr {adr}` for an ADR link).
- Open nothing but the index, the listed ranges, and the review rows the items carry.

`commit` and `propose` record each backlog item themselves (`spec-change`, `spec-proposal`) —
do not call `append-issue` for them.

Release the lease on **every** exit path:

```bash
{spec_align} lease release --owner {epic_key}
```

Then run `{spec_align} check-pointers --all`, and carry any broken pointer it prints into the
closure report. It does not block.
````

- [ ] **Step 6: Epic closure §3.** Replace the line
  `  (\`{implementation_artifacts}/epic-{epic_nnn}/arch/*.md\`).` with
  `  (\`{spec_align} adrs --epic {epic_key}\`).`

- [ ] **Step 7: Epic closure §5.** After `- ADRs produced (if any)`, append:

```markdown
- **Spec changes** (when `{spec_alignment}` is `true`):
  - one row per disposition in the epic's `drift-dispositions.yaml` files: finding,
    disposition, commit SHA or proposal file, and backlog key;
  - the spec index's `bytes` and `sections` (its header line 2);
  - the number of ranges across every review's `Sections read:` footer;
  - spec sync's share of the epic's fresh tokens (input + output + cache_write): run
    `usage --agent l3io-spec-sync --epic {epic_key}` with the same transcript arguments as
    this epic's actuals capture, and divide by the epic's `actual.tokens_k` fresh total.

  When the share is above 5%, add the line `⚠ spec sync used {share}% of fresh tokens
  (budget 5%)`. It blocks nothing.
```

- [ ] **Step 8: Epic closure §7.** Append to the end of `epic-closure.md`:

````markdown

## 7. Commit checkpoint

Epic closure writes actuals, calibration samples, dispositions, proposals and the spec index.
Commit them as sprint closure does (`steps/sprint/step-04-sprint-closure.md` §9). The
`docs(spec)` commits that §2a made are already in history.

```bash
git -C {project-root} rm -r --cached --quiet --ignore-unmatch -- '{implementation_artifacts}/state/*.lock'
git add {implementation_artifacts}/state/ \
        {implementation_artifacts}/epic-{epic_nnn}/ \
        {implementation_artifacts}/spec/ \
        {planning_artifacts}/
git status --short
git commit -s -m "chore({epic_key}): close epic"
```

If unrelated files appear in `git status`, stage only these paths. If nothing is staged, skip
the commit.
````

- [ ] **Step 9: The reference doc.**
  - **Sprint closure.** Before "Closure ends with a commit checkpoint", add:
    `Its architectural-drift phase gives every finding an ID (\`SD-{nn}-{n}\`), records a disposition for each BLOCKER/MAJOR, and gates on \`spec-align.py check-dispositions\`; with \`spec_alignment\` on it also receives the spec index and the ranges the stories' \`Spec:\` pointers name.`
    In the commit-checkpoint sentence, change `stages \`state/\` and the sprint's artifacts`
    to `stages \`state/\`, the sprint's artifacts and \`spec/\``.
  - **Epic closure.**
    - Replace list item 2 with:
      `2. **Architectural drift** — \`l3io-arch-review\` Mode B over the epic's ADRs (\`spec-align.py adrs\`), story files and cumulative diff, plus the spec index and pointed-to ranges when \`spec_alignment\` is on. CODE/MIXED only, and only when installed. Every BLOCKER/MAJOR gets a disposition — \`resolved-in-code\` (fix loop, \`{max_fix_iterations}\` cap, 3), \`adr-justified\`, \`spec-updated\` or \`spec-proposal\` — gated by \`spec-align.py check-dispositions\`; MINOR defers to the issues file`
      (Keep the \`spec-align.py\` prefix: check 4's pm-status pass flags a bare backticked
      \`check-*\` name in a live doc until Task 18 teaches it the spec-align names.)
    - Insert after item 2:
      `2a. **Spec sync** — when \`spec_alignment\` is on and \`spec-align.py sync-plan\` finds pending items: one \`l3io-spec-sync\` agent under a spec-edit lease writes each accepted architecture departure back as its own \`docs(spec)\` commit (a scope guard keeps it inside the section; an anchor guard protects story pointers) and writes proposals for PRD/UX/epic changes; each becomes a \`spec-change\` or \`spec-proposal\` backlog item, confirmed or rejected in \`/l3io-util-doctor triage\`. An empty plan dispatches nothing.`
    - Append item `6. **Commit checkpoint** — stages \`state/\`, the epic's artifacts, \`spec/\` and planning artifacts, and commits \`chore({epic_key}): close epic\``.
    - In item 5, append `, and a Spec changes section (dispositions, commits, proposals, index size, sections read, spec sync's token share against the 5% budget)`.

- [ ] **Step 10: Check the old home is gone, sync, run the gates, and commit**

Run: `grep -rn -E "arch/adr-|arch/\*\.md" skills/_shared/steps`
Expected: no output.

Run the Task 13 gate command. Stage the three `_shared` files, their pm-execute copies
(`skills/l3io-pm-execute/steps/closure/sprint-closure.md`,
`skills/l3io-pm-execute/steps/closure/epic-closure.md`,
`skills/l3io-pm-execute/steps/sprint/step-04-sprint-closure.md`), the reference doc and the
pm-execute manifest. Commit with the subject
`feat(l3io-pm): drift dispositions, epic spec sync, and the epic commit checkpoint`.

---
### Task 16: doctor — binding, the `migrate-adrs` mode, and health Checks 15–19

**Files:**
- Create: `skills/l3io-util-doctor/steps/migrate-adrs.md`
- Modify: `skills/l3io-util-doctor/SKILL.md`: the description frontmatter; the mode count
  (lines 55–56); the mode bullets (near line 33); the mode table; the help block; the
  `{spec_align}` binding after the `{pm_status}` binding.
- Modify: `skills/l3io-util-doctor/steps/health-check.md`: the HC2 heading and intro; new
  Checks 15–19 after Check 14; HC3 table rows; the HC6 action order.

**Interfaces:**
- **Consumes:** `migrate-adrs --plan/--apply` JSON (`moves`, `register`, `review`,
  `commit`), plus `check-pointers --all`, `check-links`, `check-stale` and `build --check`
  (exit 1 = findings).
- **Produces:** the doctor binding `{spec_align}`, which passes no `--spec-paths` (R3), and the
  mode keyword `migrate-adrs`. Check 14 (Task 18) allowlists
  `skills/l3io-util-doctor/steps/migrate-adrs.md` and `steps/health-check.md`.

- [ ] **Step 1: The binding.** In `SKILL.md`, directly after
  `Bind \`{pm_status}\` = \`{project-root}/_bmad/scripts/pm-status.py\` for use in all mode files\nbelow.`,
  add:

```markdown

Bind `{spec_align}` = `uv run {skill-root}/scripts/spec-align.py --project-root {project-root} --planning-root {planning_artifacts} --impl-root {implementation_artifacts} --state-root {pm_state_root} --pm-status {pm_status}`
for health Checks 15–19, triage's spec pass and `migrate-adrs`. It passes no `--spec-paths`,
so it checks the spec set the project's spec index recorded (pm-execute's `spec_paths`).
```

- [ ] **Step 2: The mode.** Make these edits in `SKILL.md`:
  - The mode count: `carries seventeen procedures` → `carries eighteen procedures`, and
    `invocation for sixteen it would not execute` →
    `invocation for seventeen it would not execute`.
  - The mode table, a row directly after the `triage` row:
    `| \`migrate-adrs\` | \`steps/migrate-adrs.md\` | move ADRs from the old per-epic home to \`docs/adr/\` — confirms before writing |`
  - The help block's "One-time migrations" group, after the `bootstrap-state` entry and its
    continuation line:
    `  migrate-adrs       Move ADRs from epic-*/arch/ to docs/adr/, the one ADR home`
  - The bullet list, after the `triage` bullet:
    `- **\`migrate-adrs\`:** Moves ADRs from the old per-epic home (\`{implementation_artifacts}/epic-*/arch/\`) to \`{project-root}/docs/adr/\`, renumbering a colliding one only inside its own epic's artifacts; plans first, confirms, commits once.`
  - The description frontmatter: after `triage the backlog (audit it and resolve findings that are already fixed),`
    insert ` move ADRs from the old per-epic home to docs/adr/,`.

- [ ] **Step 3: The mode file.** Create `skills/l3io-util-doctor/steps/migrate-adrs.md`:

````markdown
## Migrate ADRs Mode

Moves ADRs from the old per-epic home, `{implementation_artifacts}/epic-*/arch/adr-NNNN-*.md`,
to `{project-root}/docs/adr/NNNN-slug.md`, the one ADR home. Health Check 15 detects them. A
project that never migrates keeps working: `adr-reserve` and `spec-align.py adrs` still read
the old home.

### Step MA1 — Plan (read-only)

```bash
{spec_align} migrate-adrs --plan
```

Print a table of `moves`: from, to, epic, and collision. A collision has an empty `to`,
because `docs/adr/` already holds that number. At apply time:
- the `docs/adr/` file keeps its number, since it may be cited outside PM artifacts;
- the epic ADR gets a newly reserved number;
- `ADR-NNNN` mentions are rewritten **only inside that epic's artifact tree**;
- every other mention is listed for a person, and not rewritten.

If `moves` is empty, print `✓ No ADRs in the old home.` and exit.

### Step MA2 — Confirm

Ask: `Move {n} ADR(s) to docs/adr/ and commit? (y/n)`. On `n`, exit with no changes.

### Step MA3 — Apply

```bash
{spec_align} migrate-adrs --apply
```

Print its summary:
- **moved:** from → to;
- **renumbered:** old → new, from `renumbered_to`;
- **rewritten:** the files;
- **commit:** the SHA (a single `docs(adr): migrate epic ADRs to docs/adr` commit);
- **every `review` entry.** Those mentions were not rewritten; ask the user to check each
  one by hand.
````

- [ ] **Step 4: Health Checks 15–19.**
  - Change `### Step HC2 — Scan (14 checks, read-only)` to
    `### Step HC2 — Scan (19 checks, read-only)`.
  - Append this sentence to the intro paragraph under it:
    ` Checks 15–19 run \`{spec_align}\` in its read-only modes, which write nothing.`
  - Insert the following directly before `### Step HC3 — Report findings`:

````markdown
**Check 15 — ADR home and register**
Run only if `{implementation_artifacts}` exists.

```bash
{spec_align} migrate-adrs --plan
```

- `moves` non-empty → flag `migrate-adrs` · Priority: **Medium** · note the count, and how
  many are a `collision`
- `register.lagging` is true → report
  `adr-register next {next} ≤ highest ADR on disk {highest_on_disk}`. This is report only:
  the next `adr-reserve` corrects it by itself
- otherwise → ✓

**Check 16 — Spec pointers**
Run only if `{implementation_artifacts}/spec/spec-index.md` exists, meaning the project has
run spec alignment.

```bash
{spec_align} check-pointers --all
```

- exit 1 → report every broken pointer it printed on stderr. This is report only: fix the
  story's `Spec:` line, or let story prep re-enrich it
- exit 0 → ✓, noting its pre-provenance count

**Check 17 — ADR links**

```bash
{spec_align} check-links
```

- exit 1 → report each ADR it names. This is report only: the next epic closure's spec sync
  links it
- exit 0 → ✓

**Check 18 — Unconfirmed spec changes that have been built upon**
Run only if `{project-root}` is a git work tree (`git -C {project-root} rev-parse --is-inside-work-tree`
prints `true`).

```bash
{spec_align} check-stale
```

- exit 1 → flag `triage` · Priority: **Medium**. Its spec pass confirms or rejects them;
  each later commit on the same file makes a clean revert less likely
- exit 0 → ✓

**Check 19 — Spec index freshness**
Run only if the index exists.

```bash
{spec_align} build --check
```

- exit 1 → report `spec index is stale`. This is report only: the next pm-execute run
  rebuilds it, or `{spec_align} build` rebuilds it now
- exit 0 → ✓

````

- [ ] **Step 5: HC3 rows.** In the HC3 example table, directly after the
  `Tracked lock files …` row, add:

```
ADR home & register             ⚠ 2 ADR(s) in epic-*/arch/     migrate-adrs
Spec pointers                   ⚠ 1 broken pointer             — (report only)
ADR links                       ⚠ 1 unlinked departure         — (report only)
Unconfirmed spec changes        ⚠ 1 built upon                 triage
Spec index freshness            ✓ Fresh                        —
```

- [ ] **Step 6: HC6 order.** Replace the numbered list in "Step HC6 — Execute in order"
  with:

```
1. `rename-active`
2. `rename-epic-dirs`
3. `migrate-schema`
4. `split-status`
5. `migrate-state`
6. `bootstrap-state`
7. `reconcile-status`
8. `layout-cleanup`
9. `sort-status`
10. `harvest-debt`
11. `migrate-adrs`
12. `triage`
13. `update-ai-rules`
14. `redrive`
15. `untrack-locks`
16. `clean-legacy`
```

Then add this paragraph after the one that explains `redrive`'s position:

```markdown
`migrate-adrs` runs before `triage` so that ADR paths a backlog item cites are already the new
ones when triage reads them. It keeps its own plan and confirmation (Step MA2), like `triage`
does, because it commits.
```

The paragraph that begins `**\`triage\` keeps its own confirmations here.**` stays. Add, right
after it: `**\`migrate-adrs\` keeps its own confirmation too** — it moves files and commits.`

- [ ] **Step 7: Verify.** Run `npm run check:docs && npm run test:scripts`. Expected: exit 0.
  Check 3 resolves no new `§` refs here, and check 1 finds no unknown skill names.

- [ ] **Step 8: Commit.** Stage `skills/l3io-util-doctor/SKILL.md`,
  `skills/l3io-util-doctor/steps/health-check.md` and
  `skills/l3io-util-doctor/steps/migrate-adrs.md`. Commit with the subject
  `feat(l3io-util): doctor migrate-adrs mode and spec-alignment health Checks 15-19`.

---

### Task 17: triage spec pass, audit-backlog skip, pm-help counts, arch-review ADR allocation

**Files:**
- Modify: `skills/l3io-util-doctor/steps/triage.md` (new Step T3b; T7 summary)
- Modify: `skills/l3io-util-doctor/scripts/audit-backlog.py` (`audit()` filter; docstring)
- Modify: `skills/l3io-util-doctor/scripts/tests/test-audit-backlog.py` (new class)
- Modify: `skills/l3io-pm-help/SKILL.md` ("Open issues" bullet)
- Modify: `skills/l3io-arch-review/SKILL.md` (Mode A, Mode C, Output)
- Modify: `skills/l3io-arch-review/assets/adr-template.md`

**Interfaces:**
- **Consumes:** `list-issues --kind`, `resolve-issue`, `{spec_align} reject --key K`.
- **Produces:** `audit-backlog.py` emits no verdict for items whose `kind` is not `defect`.

- [ ] **Step 1: Write the failing test.** In `test-audit-backlog.py`, add this directly
  before `if __name__ == "__main__":`:

```python
class TestSpecItemsSkipped(Base):
    """spec-change/spec-proposal items are confirmed or rejected in triage's spec pass; the
    mechanical audit must not propose resolving them as obsolete or needs-review."""

    def test_spec_items_get_no_verdict(self):
        self.pm("append-issue", "--state-root", self.state, "--epic", "001", "--sprint", "",
                "--title", "Spec change: order API", "--source", "spec-sync (AD-1)",
                "--severity", "Medium", "--kind", "spec-change", "--ref", "3f9c2a1",
                "--description", "Confirm or reject: /l3io-util-doctor triage")
        self.append("A defect", "code-review (E001-S01-001)")
        v = self.verdicts()
        self.assertNotIn("BL-E001-001", v)
        self.assertIn("BL-E001-002", v)
```

Run: `uv run -q --with 'ruamel.yaml>=0.18' python3 skills/l3io-util-doctor/scripts/tests/test-audit-backlog.py TestSpecItemsSkipped`
Expected: FAIL. `BL-E001-001` gets a `needs-review` verdict.

- [ ] **Step 2: Implement.** In `audit-backlog.py`, make `audit()`'s first statement, before
  `verdicts, warnings = [], []`:

```python
    # Spec items (docs/adr/0004) are confirmed or rejected in triage's spec pass, never here.
    open_items = [it for it in open_items if str(it.get("kind") or "defect") == "defect"]
```

Append this sentence to the module docstring's first paragraph:
`Spec items (kind spec-change / spec-proposal) are skipped: triage's spec pass handles them.`

Run the Step 1 command again. Expected: `OK`. Then run the whole suite:
`uv run -q --with 'ruamel.yaml>=0.18' python3 skills/l3io-util-doctor/scripts/tests/test-audit-backlog.py`
Expected: `OK` (23 tests).

- [ ] **Step 3: Non-hollow proof.** Comment out the filter line and rerun Step 1's command.
  It must FAIL. Restore it.

- [ ] **Step 4: The triage spec pass.** In `triage.md`, insert directly before
  `### Step T4 — Agent review (optional; costs tokens)`:

````markdown
### Step T3b — Spec changes and proposals

```bash
uv run {pm_status} list-issues --state-root {pm_state_root} --kind spec-change --format json
uv run {pm_status} list-issues --state-root {pm_state_root} --kind spec-proposal --format json
```

Skip this step when both are empty. Otherwise take each item in turn, oldest first:
- `spec-change`: show `git -C {project-root} show --stat {ref}`, then the diff
  (`git -C {project-root} show {ref}`)
- `spec-proposal`: show the proposal file at `{ref}`

Ask: `Confirm, reject, or skip {key}? (c/r/s)`.

- **Confirm a spec change** →
  `uv run {pm_status} resolve-issue --state-root {pm_state_root} --key {key} --resolution fixed --ref {ref} --session-id {triage_session} --cause triage`
- **Confirm a proposal** → ask for the commit that changed the spec, then run the same
  command with `--ref {that sha}`. If there is no such commit yet, skip the item. A proposal
  is confirmed only once the spec actually says it.
- **Reject either kind** → `{spec_align} reject --key {key}`. It does three things:
  - reverts a spec change (`git revert`; a proposal needs nothing reverted);
  - resolves the item `wontfix`;
  - files the drift as a code fix (`Code diverges from spec: …`, at the original severity).

  Exit 2 on a revert conflict means it aborted the revert and left the item open: print its
  message. Nothing else changed.
- **Skip** → leave the item open. Health Check 18 reports it once a later commit builds on it.
````

In Step T7's summary block, directly after the `Re-severitied:` line, add:

```
  Spec items:         {n}  (confirmed {a} · rejected {r} · still open {o})
```

- [ ] **Step 5: pm-help.** In `skills/l3io-pm-help/SKILL.md`'s **Open issues** bullet,
  append:
  ` Count \`spec-change\` items (unconfirmed spec edits) and \`spec-proposal\` items (proposed PRD/UX/epic changes) separately, by their \`kind\` field — with the \`cat\` fallback read each item's \`kind:\`; an item without one is a defect. If any are open, recommend \`/l3io-util-doctor triage\` (its spec pass confirms or rejects them).`

- [ ] **Step 6: arch-review.** In `skills/l3io-arch-review/SKILL.md`, make three edits:
  1. Mode A bullet: append ` — numbered and placed as in Mode C` after
     `using \`assets/adr-template.md\``.
  2. Mode C: replace
     `recommend, and **record an ADR** (\`assets/adr-template.md\`). Never let a load-bearing call go\nunrecorded.`
     with:

```markdown
recommend, and **record an ADR** (`assets/adr-template.md`) at
`{project-root}/docs/adr/NNNN-slug.md`, the one ADR home. When
`{project-root}/_bmad/scripts/pm-status.py` exists, take the number from the l3io-pm
register:
`python3 {project-root}/_bmad/scripts/pm-status.py adr-reserve --state-root {implementation_artifacts}/state --epic n/a --slug {slug} --adr-dir {project-root}/docs/adr`
prints it. Without l3io-pm there is no register, so use the highest number in `docs/adr/`
plus one. That is safe only for a single writer, which is the only case without the
register, and `adr-reserve` skips those numbers later. Fill `Epic:` (`n/a` outside an epic)
and `Departs from spec:` (a `path#anchor`, or `n/a`). Never let a load-bearing call go
unrecorded.
```

  3. Output: change
     `- **Design/Decision** → ADRs under \`{project-root}/docs/adr/\` and the docs skeleton.`
     to
     `- **Design/Decision** → ADRs under \`{project-root}/docs/adr/\` (numbered by \`adr-reserve\` when l3io-pm is installed — Mode C) and the docs skeleton.`

In `assets/adr-template.md`, directly after `- **Deciders:** <names/roles>`, add:

```markdown
- **Epic:** <E{nnn} | n/a>
- **Departs from spec:** <path>#<anchor> | n/a
```

- [ ] **Step 7: Gates and commit.** Run `npm run check:docs && npm run test:scripts`, then
  the audit-backlog suite. Stage these files:
  - `skills/l3io-util-doctor/steps/triage.md`
  - `skills/l3io-util-doctor/scripts/audit-backlog.py`
  - `skills/l3io-util-doctor/scripts/tests/test-audit-backlog.py`
  - `skills/l3io-pm-help/SKILL.md`
  - `skills/l3io-arch-review/SKILL.md`
  - `skills/l3io-arch-review/assets/adr-template.md`

  Commit with the subject
  `feat(l3io-util): triage spec pass; spec items skip the mechanical audit; ADR allocation in arch-review`.

---
### Task 18: check-docs — check 4 covers spec-align, and new checks 13 and 14

**Files:**
- Modify: `scripts/check-docs.mjs`: the header list; check 4; two new functions; the runner.
- Modify: `scripts/tests/check-docs.test.mjs`: new tests.
- Modify: `docs/l3io-pm-reference.md`: a new `### \`spec-align.py\` subcommands` section,
  directly after the `pm-status.py` subcommand table.

**Interfaces:**
- **Consumes:**
  - `spec-align.py`'s `\bsub.add_parser("…")` registrations, and its literal `KINDS` and
    `DIMENSIONS` tuples;
  - `layout-cleanup.md` heuristic 5;
  - the enrichment layout in `step-02-story-prep.md`.
- **Produces:** check 4 (extended) with the `spec-align` surface; check 13
  `spec-align-contract`; check 14 `adr-home`.

- [ ] **Step 1: Document the surface.** In `docs/l3io-pm-reference.md`, directly after the
  last row of the `pm-status.py` subcommands table and before `### Legacy migration`, add:

```markdown
### `spec-align.py` subcommands

The spec-alignment helper (`skills/_shared/spec-align.py`, shipped in pm-execute's and
util-doctor's `scripts/`; ADR-0004, ADR-0005). It runs with `uv run` and never calls a model.
Global flags go before the subcommand: `--project-root`, `--planning-root`, `--impl-root`,
`--state-root`, `--pm-status`, `--spec-paths JSON`. Exit codes: 0 ok · 1 report-mode findings ·
2 a gate refused, or bad input · 5 the lease is held.

| Subcommand | What it does |
|---|---|
| `build` | Writes `{implementation_artifacts}/spec/spec-index.md`: one line per H1–H3 heading (anchor, first sentence, line range) of every discovered spec. `--if-stale` rewrites only when the specs changed; `--check` exits 1 when stale |
| `check-pointers` | `--story F…`: gate, exit 2 unless every applicable dimension ends with a resolving `Spec:` line (or `Spec: none — <reason>`). `--all`: report, exit 1 on broken pointers |
| `sections` | `--stories F…`: the pointers as de-duplicated `path#anchor Lstart–end` ranges |
| `disposition` | Records a drift finding's disposition (`resolved-in-code`, `adr-justified`, `spec-updated` — architecture sections only — or `spec-proposal`) in `drift-dispositions.yaml` beside the review |
| `check-dispositions` | Gate: every BLOCKER/MAJOR has a disposition, and the parsed findings match the reviewer's `Blocker: N, Major: N, Minor: N` |
| `adrs` | `--epic E`: the epic's ADRs from `docs/adr/` (its `Epic:` line) and the old per-epic home |
| `check-links` | Report: accepted ADRs whose `Departs from spec:` section does not link back |
| `lease` | `acquire --owner E` / `release --owner E`: the spec-edit lease (`state/spec-sync.lock`) |
| `sync-plan` | `--epic E`: pending spec-sync items as JSON; `--defer` writes pointer-only proposals and backlog items instead |
| `propose` | Records an agent-written proposal file and its `spec-proposal` backlog item |
| `commit` | One guarded `docs(spec)` commit per finding or ADR link: the diff must stay inside the section, pointed-to anchors may not vanish (`--rename-anchor OLD=NEW` rewrites story pointers in the same commit); opens the `spec-change` backlog item |
| `reject` | `--key K`: reverts a spec change (or declines a proposal), resolves it `wontfix`, and files the drift as a code fix |
| `check-stale` | Report: unconfirmed spec changes that a later commit has built upon |
| `migrate-adrs` | `--plan` / `--apply`: moves ADRs from `epic-*/arch/` to `docs/adr/`, renumbering a collision only inside its own epic's artifacts, in one commit |
```

- [ ] **Step 2: Write the failing node tests.** Append this to
  `scripts/tests/check-docs.test.mjs`:

```js
// ---- check 4 (spec-align surface), 13 (spec-align contract), 14 (adr-home) ----

test("check 4: a step file naming a spec-align subcommand the CLI lacks is caught", (t) => {
  const root = fixture(t);
  write(root, "skills/_shared/steps/brand-new-dir/sa.md",
        "```bash\n{spec_align} frobnicate --epic E001\n```\n");
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /sa\.md:2: names spec-align\.py subcommand 'frobnicate'/);
});

test("check 4: an undocumented spec-align subcommand is caught", (t) => {
  const root = fixture(t);
  const rel = "docs/l3io-pm-reference.md";
  const text = fs.readFileSync(path.join(root, rel), "utf8");
  write(root, rel, text.replace(/^\| `check-stale` \|.*\n/m, ""));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /does not document spec-align\.py subcommand 'check-stale'/);
});

test("check 4: spec-align names in backticks are not read as pm-status subcommands", (t) => {
  const root = fixture(t);
  write(root, "CLAUDE.md", "\nRun `check-pointers`, then `check-stale`.\n", true);
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test("check 13: a pattern added to layout-cleanup alone is caught", (t) => {
  const root = fixture(t);
  const rel = "skills/l3io-util-doctor/steps/layout-cleanup.md";
  const text = fs.readFileSync(path.join(root, rel), "utf8");
  write(root, rel, text.replace("`*tech-design*`", "`*tech-design*`, `*blueprint*`"));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /architecture patterns differ.*\*blueprint\*/s);
});

test("check 13: a renamed dimension in the enrichment prompt is caught", (t) => {
  const root = fixture(t);
  const rel = "skills/_shared/steps/sprint/step-02-story-prep.md";
  const text = fs.readFileSync(path.join(root, rel), "utf8");
  write(root, rel, text.replace("   ### Testability approach", "   ### Test approach"));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /dimensions differ/);
});

test("check 13 scope: a prompt that lost its layout block is caught", (t) => {
  const root = fixture(t);
  const rel = "skills/_shared/steps/sprint/step-02-story-prep.md";
  const text = fs.readFileSync(path.join(root, rel), "utf8");
  write(root, rel, text.replace(/^\s*## Technical acceptance criteria\s*$/m, ""));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /no '## Technical acceptance criteria' layout block/);
});

test("check 14: the old ADR home in a new directory is caught", (t) => {
  const root = fixture(t);
  write(root, "skills/_shared/steps/brand-new-dir/adr.md",
        "Write it to `{implementation_artifacts}/epic-001/arch/adr-0001-x.md`.\n");
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /adr\.md:1: .*arch\/adr-0001-x\.md/);
});

test("check 14: the old ADR glob inside a fence is caught", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-util-doctor/assets/brand-new.md",
        "```\nls {implementation_artifacts}/epic-*/arch/*.md\n```\n");
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /brand-new\.md:2/);
});

test("check 14: naming the old home as legacy, and the gate review file, pass", (t) => {
  const root = fixture(t);
  write(root, "skills/_shared/steps/brand-new-dir/ok.md",
        "The old home `epic-*/arch/adr-*` is legacy.\n" +
        "The review lives at `{implementation_artifacts}/epic-001/arch/arch-gate-review.md`.\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});
```

Run: `npm run test:scripts`
Expected: the new tests fail (no `names spec-align.py subcommand` output; check 13 and 14 do
not exist). The existing tests still pass.

- [ ] **Step 3: Implement in `scripts/check-docs.mjs`.**

(a) Header list. Change `//   4. cli-surface   documented pm-status.py subcommands and the real CLI agree, both ways` to
`//   4. cli-surface   documented pm-status.py and spec-align.py subcommands and the real CLIs agree, both ways`.
After the `12. pm-status-size` entry, add:

```js
//  13. spec-align-contract spec-align.py's spec kinds match layout-cleanup.md heuristic 5, and
//                    its six DIMENSIONS match the enrichment prompt's layout block
//  14. adr-home      no runtime directive names the old per-epic ADR home (epic-*/arch/adr-*)
```

(b) Directly after `function cliSubcommands() { … }`, add:

```js
const SPEC_ALIGN = "skills/_shared/spec-align.py";
const SPEC_ALIGN_HEADING = "### `spec-align.py` subcommands";

function specAlignSubcommands() {
  // Top-level registrations only: `\bsub.` excludes nested parsers such as lease_sub.
  if (!exists(SPEC_ALIGN)) return new Set();
  return new Set([...read(SPEC_ALIGN).matchAll(/\bsub\.add_parser\(\s*"([a-z-]+)"/g)]
    .map((m) => m[1]));
}

// The text of a markdown section: from its heading to the next ##/### heading.
function docSection(text, heading) {
  const i = text.indexOf(heading);
  if (i < 0) return "";
  const rest = text.slice(i + heading.length);
  const end = rest.search(/\n#{2,3} /);
  return end < 0 ? rest : rest.slice(0, end);
}
```

(c) In `checkCliSurface`, directly after `const real = cliSubcommands();`, add
`const saReal = specAlignSubcommands();`. Directly before the line
`if (!explicit && !/^(set|estimate|move|archive|append|list|check|clear|self)-/.test(name)) continue;`,
add:

```js
      // spec-align.py has check-* subcommands of its own; they are not pm-status claims.
      if (!explicit && saReal.has(name)) continue;
```

(d) After `tableRowSubcommands`, add check 4's spec-align half:

```js
// 4 (continued). The spec-align.py CLI surface, both ways. Step files invoke it through the
// `{spec_align}` binding, so forward reads `{spec_align} <sub>` anywhere, and the explicit
// `spec-align.py <sub>` form only inside code (a fence or a backtick span) -- prose such as
// "spec-align.py stays one file" is not a claim. Scope: every live doc and every skill doc.
function checkSpecAlignSurface() {
  const real = specAlignSubcommands();
  if (real.size === 0) {
    failures.push(`${SPEC_ALIGN}: no sub.add_parser() calls found — has the CLI moved?`);
    return;
  }
  let checked = 0;
  for (const rel of [...LIVE_DOCS, ...walkMarkdown("skills")]) {
    let inFence = false;
    read(rel).split("\n").forEach((line, i) => {
      if (/^\s*```/.test(line)) inFence = !inFence;
      const spans = [...line.matchAll(/`[^`]*`/g)].map((m) => [m.index, m.index + m[0].length]);
      const inCode = (at) => inFence || spans.some(([a, b]) => at > a && at < b);
      for (const m of line.matchAll(/\{spec_align\}\s+([a-z][a-z-]*)/g)) {
        checked += 1;
        if (!real.has(m[1])) {
          failures.push(`${rel}:${i + 1}: names spec-align.py subcommand '${m[1]}', which ` +
            `the CLI does not have\n      CLI has: ${[...real].sort().join(", ")}`);
        }
      }
      for (const m of line.matchAll(/spec-align\.py\s+([a-z][a-z-]*)/g)) {
        if (!inCode(m.index) || PROSE_AFTER_CMD.has(m[1])) continue;
        checked += 1;
        if (!real.has(m[1])) {
          failures.push(`${rel}:${i + 1}: names spec-align.py subcommand '${m[1]}', which ` +
            `the CLI does not have\n      CLI has: ${[...real].sort().join(", ")}`);
        }
      }
    });
  }
  const section = docSection(exists(CLI_REFERENCE_DOC) ? read(CLI_REFERENCE_DOC) : "",
                             SPEC_ALIGN_HEADING);
  const documented = tableRowSubcommands(section);
  for (const name of real) {
    checked += 1;
    if (documented.has(name)) continue;
    failures.push(`${CLI_REFERENCE_DOC}: does not document spec-align.py subcommand '${name}' ` +
      `as a table row under "${SPEC_ALIGN_HEADING}"`);
  }
  if (verbose) console.log(`  spec-align-surface: ${checked} claim(s) checked both ways`);
}
```

(e) After `checkPmStatusSize`, add checks 13 and 14:

```js
// ---------------------------------------------------------------------------
// 13. spec-align.py's contract with the docs it mirrors.
//
// Its spec kinds are copied from doctor's layout-cleanup heuristic 5 (the spec says one source
// of truth), and its DIMENSIONS must be the six headings the enrichment prompt tells the agent
// to write -- check-pointers rejects any other name, so a drift here blocks every story.
// ---------------------------------------------------------------------------
const LAYOUT_CLEANUP = "skills/l3io-util-doctor/steps/layout-cleanup.md";
const STORY_PREP = "skills/_shared/steps/sprint/step-02-story-prep.md";
const KIND_LABELS = { architecture: "Architecture", prd: "Requirements / PRD", ux: "UX spec" };

function pyTuple(src, name) {
  const m = src.match(new RegExp(`^${name} = \\(([\\s\\S]*?)^\\)`, "m"));
  return m ? m[1] : null;
}

function checkSpecAlignContract() {
  if (!exists(SPEC_ALIGN)) return;
  const src = read(SPEC_ALIGN);
  const kindsBlock = pyTuple(src, "KINDS");
  const dimsBlock = pyTuple(src, "DIMENSIONS");
  if (!kindsBlock || !dimsBlock) {
    failures.push(`${SPEC_ALIGN}: KINDS or DIMENSIONS is no longer a literal tuple`);
    return;
  }
  const kinds = {};
  for (const m of kindsBlock.matchAll(/\(\s*"([a-z]+)",\s*\(([^)]*)\)\s*\)/g)) {
    kinds[m[1]] = [...m[2].matchAll(/"([^"]+)"/g)].map((x) => x[1]).sort();
  }
  const doctor = read(LAYOUT_CLEANUP).split("\n");
  for (const [kind, label] of Object.entries(KIND_LABELS)) {
    const line = doctor.find((l) => l.includes(`**${label}**:`));
    const theirs = line ? [...line.matchAll(/`([^`]+)`/g)].map((m) => m[1]).sort() : [];
    const ours = kinds[kind] || [];
    if (JSON.stringify(theirs) !== JSON.stringify(ours)) {
      failures.push(`${kind} patterns differ: ${SPEC_ALIGN} has [${ours.join(", ")}], ` +
        `${LAYOUT_CLEANUP} heuristic 5 has [${theirs.join(", ")}]`);
    }
  }
  const dims = [...dimsBlock.matchAll(/"([^"]+)"/g)].map((x) => x[1]);
  const lines = read(STORY_PREP).split("\n");
  const at = lines.findIndex((l) => /^\s*## Technical acceptance criteria\s*$/.test(l));
  if (at < 0) {
    failures.push(`${STORY_PREP}: no '## Technical acceptance criteria' layout block in the ` +
      `enrichment prompt — ${SPEC_ALIGN} check-pointers requires it`);
    return;
  }
  const prompt = [];
  for (const l of lines.slice(at + 1)) {
    if (/^\s*## /.test(l) || /^\s*```/.test(l) || prompt.length === dims.length) break;
    const m = l.match(/^\s*### (.+?)\s*$/);
    if (m) prompt.push(m[1]);
  }
  if (JSON.stringify(prompt) !== JSON.stringify(dims)) {
    failures.push(`dimensions differ: ${SPEC_ALIGN} DIMENSIONS is [${dims.join(", ")}], the ` +
      `enrichment prompt in ${STORY_PREP} lays out [${prompt.join(", ")}]`);
  }
  if (verbose) console.log(`  spec-align-contract: ${Object.keys(KIND_LABELS).length} kinds, ${dims.length} dimensions`);
}

// ---------------------------------------------------------------------------
// 14. No runtime directive names the old per-epic ADR home.
//
// ADR-0005 makes docs/adr/ the one home; spec-align.py adrs lists an epic's ADRs. A step file
// still globbing epic-*/arch/*.md would hand a reviewer only the ADRs nobody has migrated.
// Scope is every markdown file under skills/ (walked, not listed). Allowed: the migration mode
// and the health check that detects the old home, plus any line that calls it legacy/old.
// arch/arch-gate-review.md is a review, not an ADR, and stays legal.
// ---------------------------------------------------------------------------
const ADR_OLD_HOME = /arch\/adr-|arch\/\*\.md/;
const ADR_OLD_HOME_ALLOWED = new Set([
  "skills/l3io-util-doctor/steps/migrate-adrs.md",
  "skills/l3io-util-doctor/steps/health-check.md",
]);

function checkAdrHome() {
  const offenders = [];
  for (const rel of walkMarkdown("skills")) {
    if (ADR_OLD_HOME_ALLOWED.has(rel.split(path.sep).join("/"))) continue;
    read(rel).split("\n").forEach((line, i) => {
      if (!ADR_OLD_HOME.test(line)) return;
      if (/\b(old home|old per-epic home|legacy|migrat)/i.test(line)) return;
      offenders.push(`${rel}:${i + 1}: ${line.trim()}`);
    });
  }
  if (offenders.length) {
    failures.push(`runtime directives name the old per-epic ADR home:\n      ` +
      `${offenders.join("\n      ")}\n      ADRs live in {project-root}/docs/adr/ ` +
      `(docs/adr/0005-one-adr-home.md); list an epic's with \`{spec_align} adrs --epic\`.`);
  }
  if (verbose) console.log(`  adr-home:       ${offenders.length} offending directive(s)`);
}
```

(f) Runner: after `checkCliSurface();`, add `checkSpecAlignSurface();`. After
`checkPmStatusSize();`, add `checkSpecAlignContract();` and `checkAdrHome();`.

- [ ] **Step 4: Run and fix real hits.**

Run: `npm run check:docs`
Expected: exit 0. If check 14 lists real lines, each is either an ADR path to rewrite to
`docs/adr/` (or to `{spec_align} adrs --epic {epic_key}`), or a sentence to reword as legacy.
Likely candidates: the `status-files.md` tree, and pm-execute/pm-plan `SKILL.md`. Fix the
`_shared` source, never a copy, and resync. If check 4 lists a real hit, the named
subcommand is wrong in that doc: fix the doc.

Run: `npm run test:scripts`
Expected: every test passes, the nine new ones included.

- [ ] **Step 5: Non-hollow proofs.** For each change below, rerun `npm run test:scripts`,
  confirm the named test FAILS, then restore the code:
  1. Remove `checkSpecAlignSurface();` from the runner → "check 4: a step file naming a
     spec-align subcommand…".
  2. Remove the `saReal.has(name)` skip → "check 4: spec-align names in backticks…".
  3. Remove `checkSpecAlignContract();` → both check 13 tests.
  4. Change `walkMarkdown("skills")` in `checkAdrHome` to `walkMarkdown("skills/_shared/steps/closure")`
     → "check 14: the old ADR home in a new directory is caught". This is the scope attack.

- [ ] **Step 6: Sync (if Step 4 touched `_shared`), run the gates, and commit.** Stage
  `scripts/check-docs.mjs`, `scripts/tests/check-docs.test.mjs` and
  `docs/l3io-pm-reference.md`, plus any source files, copies and manifests Step 4 fixed.
  Commit with the subject
  `feat(infra): check-docs covers the spec-align surface (check 4) and adds checks 13, 14`.

---

### Task 19: `CLAUDE.md` and the remaining documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `skills/_shared/status-files.md` (`spec-sync.lock` in §9)
- Generated: the status-files copies and manifests

- [ ] **Step 1: Update `CLAUDE.md`.** Make these edits in order:
  1. **Repository Purpose.** Append to the sentence that starts `Architecture decisions are recorded in \`docs/adr/\``:
     `; ADR-0004: agents edit architecture specs, PRD/UX/epic docs are proposal-only, and every edit is confirmed after it lands; ADR-0005: \`docs/adr/\` is the one ADR home and \`adr-reserve\` allocates from max(register, files on disk).`
  2. **Module Layout.** `each of its seventeen modes` → `each of its eighteen modes`.
  3. **Skill Directory tree.** In the `_shared/` comment, after `pm-status.py,`, add
     `spec-align.py,`.
  4. **Skill table.** In the `l3io-util-doctor` row's mode list, after `triage`, add
     `, \`migrate-adrs\``.
  5. **Shared Files table.** Add this row after the `pm-status.py` row:
     `| \`skills/_shared/spec-align.py\` | \`scripts/spec-align.py\` | pm-execute, **l3io-util-doctor** — run from each skill's own copy, never self-installed; its suite \`tests/test-spec-align.py\` stays in \`_shared/tests/\` |`
  6. **The "Test suites are never shipped" paragraph.** After
     `skills/_shared/tests/test-write-module-config.py`, insert
     `and \`skills/_shared/tests/test-spec-align.py\``.
  7. **The `check:docs` paragraph.**
     - `runs twelve checks` → `runs fourteen checks`.
     - In (4), `the documented \`pm-status.py\` CLI surface agrees with the real one` →
       `the documented \`pm-status.py\` and \`spec-align.py\` CLI surfaces agree with the real ones`.
     - Before `Check (1) deliberately allows`, add:
       `(13) **spec-align-contract** — \`spec-align.py\`'s spec kinds match \`layout-cleanup.md\` heuristic 5 and its six \`DIMENSIONS\` match the enrichment prompt's \`## Technical acceptance criteria\` layout; (14) **adr-home** — no runtime directive under \`skills/\` names the old per-epic ADR home (\`epic-*/arch/adr-*\`), found by walking \`skills/\`.`
  8. **State files.**
     - In the `state/issues.yaml` bullet, after `(\`BL-E{nnn}-{nnn}\`, \`status\` \`backlog\` or \`scheduled\`)`, insert
       `, each with an optional \`kind\` (\`spec-change\` | \`spec-proposal\`; absent = defect) and \`ref\``.
     - Append to the `adr-register.yaml` bullet:
       ` The first number handed out is the larger of the register's \`next\` and the highest ADR number already on disk — in \`--adr-dir\` (default \`<git top-level>/docs/adr\`) and in the old per-epic home — plus one.`
     - Add a new bullet after it:
       `- \`state/spec-sync.lock\` — the spec-edit lease (\`spec-align.py lease\`): owner and expiry as JSON, taken by an epic closure's spec sync so parallel closures sharing one tree never edit or commit a spec at once; ignored by the \`*.lock\` rule.`
  9. **Pre-execution gates paragraph.** After the sentence that ends
     `…standards into core \`bmad-create-story\`/\`bmad-architect\`/\`bmad-code-review\` in the consuming repo.`, add:
     `With \`spec_alignment\` on (pm-execute \`customize.toml\`, default \`true\`), both gates also take the project's specs — by pointer, never whole: \`spec-align.py build\` indexes every spec under \`{planning_artifacts}\` (headings, anchors, first sentences, line ranges; no model), the arch gate's reviewer reads only the ranges the stories point to, and every technical-AC dimension must end with a resolving \`Spec: <path>#<anchor>\` line (or \`Spec: none — <reason>\`), checked by \`spec-align.py check-pointers\` before \`ready-for-dev\`. Sprint and epic drift reviews record a disposition for every BLOCKER/MAJOR finding, and epic closure's spec sync writes accepted architecture departures back as one guarded \`docs(spec)\` commit each, confirmed or rejected in \`/l3io-util-doctor triage\`. Design: \`docs/superpowers/specs/2026-09-11-spec-alignment-design.md\`.`

- [ ] **Step 2: `status-files.md` §9.** After the bullet about
  `issues.yaml.lock`, `pm-calibration.yaml.lock` and `adr-register.yaml.lock`, add:

```markdown
- `spec-sync.lock` — the spec-edit lease written by `spec-align.py lease` (JSON: `owner`,
  `acquired_at`, `expires_at`), not an empty flock target: an epic closure's spec sync holds it
  across an agent's turns. It is a `*.lock`, so the same ignore rule keeps it out of git.
```

- [ ] **Step 3: Sync, run the gates, and commit.** Run the full gate command from Task 13.
  Stage `CLAUDE.md`, `skills/_shared/status-files.md`, the three
  `references/status-files.md` copies, and the changed manifests. Commit with the subject
  `docs(l3io-pm): document spec alignment, spec-align.py and the one ADR home`.

---

### Task 20: Final verification

Nothing is written in this task unless a step fails. It proves the branch is green.

- [ ] **Step 1: Every suite.** Run each suite below; each must print `OK`:

```bash
python3 skills/_shared/tests/test-pm-status.py -q
uv run -q --with 'markdown-it-py>=3' --with 'mdit-py-plugins>=0.4' --with 'ruamel.yaml>=0.18' --with 'unidiff>=0.7' --with 'tenacity>=8' python3 skills/_shared/tests/test-spec-align.py
uv run skills/_shared/tests/test-write-module-config.py
uv run --with pyyaml skills/l3io-pm-sync/scripts/tests/test-drift-report.py
uv run skills/l3io-sec-redteam/scripts/tests/test-init-sanctum.py
uv run -q --with 'ruamel.yaml>=0.18' python3 skills/l3io-util-doctor/scripts/tests/test-audit-backlog.py
npm run test:scripts
```

Expected totals: pm-status 1157 + 16 = **1173**; spec-align **79**; audit-backlog **23**;
write-module-config **10**; drift-report **13**; init-sanctum **11**.

- [ ] **Step 2: Every gate.**
  `npm run check:scripts && npm run check:docs && npm run check:manifest && npm run check:version`
  must exit 0.

- [ ] **Step 3: The budgets.**
  - `wc -l skills/_shared/pm-status.py` must be ≤ 8000; it is expected at about 6,700.
  - `wc -c skills/_shared/steps/shared/step-00-digest.md` must be ≤ 12600.

- [ ] **Step 4: No stderr noise, and no temp leaks.**
  - `python3 skills/_shared/tests/test-pm-status.py -q 2>&1 | grep -c -E "WARN|not inside a git"`
    must print `0`.
  - Run SA-TEST once more and confirm its final line is `OK`, with no `temp-dir leak`.
  - `ls /tmp | wc -l` must be the same before and after the whole run. Record both numbers.

- [ ] **Step 5: A smoke run of the real script against this repo.** It is read-only:

```bash
uv run skills/_shared/spec-align.py --project-root . --planning-root docs --impl-root /tmp/sa-smoke-$$ build --check; echo "exit $?"
rm -rf /tmp/sa-smoke-$$
```

Expected: `STALE …` and `exit 1`. There is no index in a fresh implementation root, and the
command writes nothing. This proves the PEP 723 header resolves under `uv run`.

- [ ] **Step 6: Report.** List every commit on the branch (`git log --oneline main..HEAD`),
  the suite totals, and every non-hollow proof recorded across the tasks.

---

## Self-review record

**Spec coverage.** Each spec section maps to tasks:

| Spec section | Tasks |
|---|---|
| §1 | 4 |
| §2 | 4 |
| §3 | 5, 13, 14, 15 |
| §4 | 6, 8, 9, 10, 15 |
| §5 | 2, 11, 17 |
| §6 | 3, 7, 12, 13, 16, 17 |
| §7 | 5, 7, 11, 12, 16, 18 |
| §8 | 13, 15 |
| §9 | 8, 9, 10, 11 |
| §10 | 18, 19 |
| §11 | 2–12, 17, 18 |
| §12 | all |

**Deliberately not done (spec §13):** AC-to-test mapping, and any automatic trimming of the
index.

**The pilot (spec §8)** runs after merge, on an epic the user picks. It is a procedure, not
code: its paired baseline dispatches use the existing `usage --agent` with a `:baseline`
identity.

**Type and name consistency.** These names were checked across tasks:

| Name | Defined in | Used in |
|---|---|---|
| `DIMENSIONS` | Task 5 | Task 18 |
| `KINDS` | Task 4 | Task 18 |
| `ISSUE_KINDS` | Task 2 | Task 17, via `--kind` |
| `adr-reserve --adr-dir` | Task 3 | Tasks 12, 13, 17 |
| `{spec_align}` | Tasks 13, 16 | Tasks 14, 15, 17 |
| `SD-{nn}-{n}` | Task 6 regex | Task 15 text |
| `l3io-spec-sync` | Task 15 | Task 15 closure report |
