# l3io Customization Layer — Phases 1–2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the package tell the truth about its BMad dependencies, conform to BMad's documented module contract, and reorganize its skills so the customization layer of Phase 3 has a home.

**Architecture:** Two sequential phases over one subsystem. Phase 1 changes data and guards only — no file moves — and is independently shippable. Phase 2 relocates module metadata, adds the two merge scripts BMad's validator requires, creates one setup skill, retires a dead skill and a now-vestigial guard, and splits a monolithic skill into a router. Every task ends with the repository's own gates green.

**Tech Stack:** Node ≥20 (`node --test`, ESM `.mjs`), Python ≥3.11 via `uv run` (PEP-723 inline deps, `unittest`), JSON inventory, TOML config, YAML state (`ruamel.yaml`).

**Spec:** `docs/superpowers/specs/2026-09-20-l3io-customization-layer-design.md`

## Global Constraints

- Conventional Commits required; **every commit needs DCO sign-off** (`git commit -s`).
- Commit message footers, verbatim:
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_014DuCKCCF5scofVSPGvvn97`
- **Never `git add -A` or `git add .`** — stage explicit paths only. Other sessions share this checkout.
- **Never hand-edit** `skills/<skill>/scripts/*` payload copies or `payload-manifest.json`. Edit `skills/_shared/`, then `npm run sync:scripts`, then `node scripts/write-payload-manifest.mjs`.
- `npm run sync:scripts` does **not** regenerate manifests. Run `write-payload-manifest.mjs` separately.
- **Never move `pm-status.py`'s version backwards.** No task here touches it.
- Historical records are **never** edited to match today: `CHANGELOG.md` and everything under `docs/superpowers/plans/` and `docs/superpowers/specs/` except this plan's own spec. `check:docs` excludes them deliberately.
- The four gates that must be green at the end of every task:
  `npm run check:docs` · `npm run check:scripts` · `npm run check:manifest` · `npm run check:version`
  plus `npm run test:scripts` (the check-docs self-tests).
- ADR numbers come from `pm-status.py adr-reserve`, never hand-picked (ADR-0005).

---

# Phase 1 — Truth

No file moves. Shippable on its own.

### Task 1: Teach the inventory a `deprecated` status

A skill BMad still ships but has frozen is neither `required` nor `removed`. Today it is forced into `removed`, which is false and which suppresses the preference check in Task 3.

**Files:**
- Modify: `scripts/check-docs.mjs:1157` (`DEP_STATUSES`) and `checkBmadDependencyInventory()` field validation, ~`:1180`
- Modify: `skills/l3io-util-doctor/scripts/bmad-deps.py:60` (`STATUSES`)
- Test: `scripts/tests/check-docs.test.mjs`

**Interfaces:**
- Consumes: nothing.
- Produces: the string `"deprecated"` as a valid inventory `status`, requiring fields `deprecated_in` (string) and `replaced_by` (string). Tasks 2–4 depend on this.

- [ ] **Step 1: Write the failing test**

Append to `scripts/tests/check-docs.test.mjs`:

```javascript
test("check 17 accepts a deprecated entry carrying deprecated_in and replaced_by", async (t) => {
  const root = await makeFixture(t);
  writeInventory(root, [
    { name: "bmad-create-story", status: "deprecated",
      deprecated_in: "6.12.0", replaced_by: "bmad-build" },
  ]);
  const { code } = runCheckDocs(root);
  assert.equal(code, 0);
});

test("check 17 rejects a deprecated entry missing deprecated_in", async (t) => {
  const root = await makeFixture(t);
  writeInventory(root, [
    { name: "bmad-create-story", status: "deprecated", replaced_by: "bmad-build" },
  ]);
  const { code, out } = runCheckDocs(root);
  assert.equal(code, 1);
  assert.match(out, /is deprecated but lacks replaced_by\/deprecated_in/);
});
```

If `makeFixture`, `writeInventory` or `runCheckDocs` do not already exist in that file, read the existing tests first and reuse whatever fixture helpers they use — do not invent a second harness.

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm run test:scripts`
Expected: FAIL — the first test exits 1 because `deprecated` is an unknown status.

- [ ] **Step 3: Add the status to `check-docs.mjs`**

```javascript
const DEP_STATUSES = ["required", "optional", "deprecated", "removed", "not-a-skill"];
```

and in the per-entry validation chain, immediately before the `removed` arm:

```javascript
    } else if (e.status === "deprecated" && !(e.replaced_by && e.deprecated_in)) {
      failures.push(`${DEP_INVENTORY}: '${e.name}' is deprecated but lacks replaced_by/deprecated_in`);
```

- [ ] **Step 4: Add the status to `bmad-deps.py`**

```python
STATUSES = ("required", "optional", "deprecated", "removed", "not-a-skill")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `npm run test:scripts && npm run check:docs`
Expected: PASS, exit 0 both.

- [ ] **Step 6: Commit**

```bash
git add scripts/check-docs.mjs scripts/tests/check-docs.test.mjs \
        skills/l3io-util-doctor/scripts/bmad-deps.py
git commit -s -m "feat(l3io-util): add a deprecated dependency status distinct from removed

A skill BMad still ships but has frozen is neither required nor removed.
Forcing it into removed is false and suppresses the preference check.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014DuCKCCF5scofVSPGvvn97"
```

---

### Task 2: Correct the three wrong statuses and declare `bmad-build`

**Files:**
- Modify: `skills/l3io-util-doctor/assets/bmad-dependencies.json`
- Modify: `skills/_shared/steps/sprint/step-03-dev-loop.md:73`
- Modify: `skills/_shared/steps/sprint/step-02-story-prep.md` (the "Resolve the enricher" prose)

**Interfaces:**
- Consumes: `"deprecated"` status from Task 1.
- Produces: inventory entries `bmad-build` and `bmad-build-auto` with `status: "optional"`, `module: "bmm"`.

- [ ] **Step 1: Re-encode the three entries**

Replace the three `removed` entries for `bmad-create-story`, `bmad-dev-story` and
`bmad-review-adversarial-general` with:

```json
    { "name": "bmad-create-story", "status": "deprecated", "deprecated_in": "6.12.0",
      "replaced_by": "bmad-build",
      "reason": "ships in 6.12.0 with metadata.lifecycle: shim and its full body retained. Verified against _bmad/_config/skill-manifest.csv on 2026-09-20. ADR-0006 said 'deprecated to shims'; this inventory said 'removed', and the data was wrong, not the ADR" },
    { "name": "bmad-dev-story", "status": "deprecated", "deprecated_in": "6.12.0",
      "replaced_by": "bmad-build",
      "reason": "ships in 6.12.0 with metadata.lifecycle: shim and its full body retained" },
    { "name": "bmad-review-adversarial-general", "status": "deprecated", "deprecated_in": "6.12.0",
      "replaced_by": "bmad-review",
      "reason": "ships in 6.12.0; merged into bmad-review's lens registry" },
```

Leave `bmad-check-implementation-readiness`, `bmad-ux-review` and `bmad-architect` as
`removed` — verified absent from the manifest.

- [ ] **Step 2: Declare the replacement path**

Add to the optional block:

```json
    { "name": "bmad-build", "status": "optional", "module": "bmm",
      "reason": "BMad's official implementation path since 6.12.0. Not dispatched yet; declared so check 17 resolves the token and so Phase 3's overlay has a declared target" },
    { "name": "bmad-build-auto", "status": "optional", "module": "bmm",
      "reason": "unattended variant of bmad-build; declared for the same reason" },
```

- [ ] **Step 3: Update `verified_against` / `verified_on`**

```json
  "verified_against": "6.12.0",
  "verified_on": "2026-09-20",
```

- [ ] **Step 4: Fix the false prose**

In `skills/_shared/steps/sprint/step-03-dev-loop.md`, replace:

> **Resolve the implementer.** The legacy `bmad-dev-story` skill is gone from BMad ≥6.12.0; where it is installed
> it is still what runs, and where it is absent the prompt below is the whole instruction anyway.

with:

> **Resolve the implementer.** BMad 6.12.0 still **ships** `bmad-dev-story`, deprecated to a shim
> (`metadata: lifecycle: shim`) with its full body retained — it is frozen, not gone. Where it is
> installed it is still what runs; where it is absent the prompt below is the whole instruction
> anyway. Phase 3 replaces this probe with a `bmad-build` overlay.

Apply the equivalent correction to the enricher prose in `step-02-story-prep.md`: it must not
claim the skill is gone.

- [ ] **Step 5: Sync the payload copies and regenerate manifests**

```bash
npm run sync:scripts
node scripts/write-payload-manifest.mjs
```

- [ ] **Step 6: Verify all gates**

Run: `npm run check:docs && npm run check:scripts && npm run check:manifest && npm run test:scripts`
Expected: all exit 0.

- [ ] **Step 7: Commit**

```bash
git add skills/l3io-util-doctor/assets/bmad-dependencies.json \
        skills/_shared/steps/sprint/step-03-dev-loop.md \
        skills/_shared/steps/sprint/step-02-story-prep.md \
        skills/l3io-pm-execute/steps/sprint/ skills/l3io-pm-plan/steps/ skills/l3io-pm-sync/steps/ \
        skills/*/payload-manifest.json
git commit -s -m "fix(l3io-util): three dependencies are deprecated, not removed

Verified against _bmad/_config/skill-manifest.csv: 6.12.0 ships
bmad-create-story, bmad-dev-story and bmad-review-adversarial-general.
ADR-0006 said 'deprecated to shims'; the inventory said 'removed'.

Also declares bmad-build/bmad-build-auto, which had zero references.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014DuCKCCF5scofVSPGvvn97"
```

---

### Task 3: Make check 17 fail on *preference*, not just mention

Today check 17 excuses a removed-skill mention when the line carries an `ls .claude/` probe. Both the dev-loop and story-prep directives carry exactly that, so a directive that **prefers** a frozen skill passes. Deprecated entries need the opposite treatment: the probe is fine, but a line that *binds the deprecated name as the chosen agent* must fail once a replacement exists.

**Files:**
- Modify: `scripts/check-docs.mjs`, `checkBmadDependencyInventory()`
- Test: `scripts/tests/check-docs.test.mjs`

**Interfaces:**
- Consumes: `"deprecated"` status and `replaced_by` from Task 1.
- Produces: a failure whenever a `skills/**` line matches `PREFERENCE_RE` against a `deprecated` name.

- [ ] **Step 1: Write the failing test**

```javascript
test("check 17 fails when a directive prefers a deprecated skill", async (t) => {
  const root = await makeFixture(t);
  writeInventory(root, [
    { name: "bmad-dev-story", status: "deprecated",
      deprecated_in: "6.12.0", replaced_by: "bmad-build" },
  ]);
  writeSkillFile(root, "l3io-pm-execute/steps/x.md",
    "bind `{dev_agent}` = the legacy `bmad-dev-story` and spawn that skill\n");
  const { code, out } = runCheckDocs(root);
  assert.equal(code, 1);
  assert.match(out, /prefers deprecated skill 'bmad-dev-story'/);
});

test("check 17 still allows a bare existence probe of a deprecated skill", async (t) => {
  const root = await makeFixture(t);
  writeInventory(root, [
    { name: "bmad-dev-story", status: "deprecated",
      deprecated_in: "6.12.0", replaced_by: "bmad-build" },
  ]);
  writeSkillFile(root, "l3io-pm-execute/steps/x.md",
    "ls {project-root}/.claude/skills/bmad-dev-story/SKILL.md 2>/dev/null\n");
  const { code } = runCheckDocs(root);
  assert.equal(code, 0);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm run test:scripts`
Expected: FAIL — the first test exits 0 because nothing checks deprecated preference yet.

- [ ] **Step 3: Implement the preference check**

Add beside the other module-level constants near `:1157`:

```javascript
// A line that BINDS a name as the chosen agent, as opposed to merely probing for it.
// Anchored on the binding verbs the step files actually use, so a probe or a prose
// mention cannot trip it.
const PREFERENCE_RE = /\b(?:bind|prefer(?:red|s)?|spawn|invoke|dispatch)\b/i;
```

and inside the per-token loop, immediately after the `if (e.status !== "removed") continue;`
arm is evaluated, insert a preceding arm:

```javascript
        if (e.status === "deprecated") {
          const line = lines[i];
          const isProbe = /(?:^|[^\w-])ls\s+\S*\.claude\//.test(line);
          if (!isProbe && PREFERENCE_RE.test(line)) {
            failures.push(`${rel}:${i + 1}: prefers deprecated skill '${name}' — replaced by ` +
              `'${e.replaced_by}' in ${e.deprecated_in}. Preferring a frozen skill is how this ` +
              `package stopped running its own replacement.\n` +
              `      context: ${line.trim().slice(0, 110)}`);
          }
          continue;
        }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm run test:scripts`
Expected: PASS.

- [ ] **Step 5: Confirm the check now fires on the real tree**

Run: `npm run check:docs`
Expected: **FAIL**, naming `step-03-dev-loop.md` and `step-02-story-prep.md` for binding
`bmad-dev-story` / `bmad-create-story`.

This failure is correct and expected — it is the defect the check was written to find. Phase 3
removes the preference. Until then, record the exemption explicitly rather than weakening the
check: add to each offending line's directive an inline marker the check honours.

- [ ] **Step 6: Add the temporary, visible exemption**

Extend the deprecated arm to honour an explicit marker:

```javascript
          const exempt = /bmad-deprecation-exempt:\s*phase-3/.test(line);
          if (!isProbe && !exempt && PREFERENCE_RE.test(line)) {
```

and add the marker to the two binding lines in `skills/_shared/steps/sprint/step-03-dev-loop.md`
and `step-02-story-prep.md`, e.g.:

> If a path printed, bind `{dev_agent}` = the legacy `bmad-dev-story` and spawn that skill.
> <!-- bmad-deprecation-exempt: phase-3 — replaced by a bmad-build overlay; see
> docs/superpowers/specs/2026-09-20-l3io-customization-layer-design.md §5 Phase 3 -->

An exemption that must be written down, names its removal condition, and is greppable is the
point; a check that silently tolerates the case is not.

- [ ] **Step 7: Re-sync, regenerate, verify**

```bash
npm run sync:scripts && node scripts/write-payload-manifest.mjs
npm run check:docs && npm run test:scripts && npm run check:manifest
```
Expected: all exit 0.

- [ ] **Step 8: Commit**

```bash
git add scripts/check-docs.mjs scripts/tests/check-docs.test.mjs \
        skills/_shared/steps/sprint/ skills/l3io-pm-execute/steps/sprint/ \
        skills/l3io-pm-plan/steps/ skills/l3io-pm-sync/steps/ skills/*/payload-manifest.json
git commit -s -m "feat(infra): check 17 fails when a directive prefers a deprecated skill

Check 17 guarded names, not preference: an ls probe on the same line
excused the mention, and the dev-loop and story-prep directives both
carry one. A directive that binds a frozen skill as the chosen agent
now fails unless it carries a dated, greppable exemption marker.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014DuCKCCF5scofVSPGvvn97"
```

---

### Task 4: Derive shipped-ness from BMad's own manifest

The inventory is a hand-kept list that drifted. `_bmad/_config/skill-manifest.csv` is BMad's own declaration of what it ships, is installed, and is machine-readable. The inventory becomes an annotation over a derived set.

**Files:**
- Modify: `skills/l3io-util-doctor/scripts/bmad-deps.py`
- Test: `skills/l3io-util-doctor/scripts/tests/test-bmad-deps.py`

**Interfaces:**
- Consumes: `"deprecated"` status from Task 1.
- Produces:
  - `load_shipped_skills(project_root: Path) -> set[str] | None` — canonical ids from column 1 of `_bmad/_config/skill-manifest.csv`; `None` when the file is absent or unreadable.
  - JSON key `status_contradictions: list[dict]`, each `{name, declared, manifest}` where `manifest` is `"ships"` or `"absent"`.
  - Exit code **5** when `status_contradictions` is non-empty and `--strict` is passed; exit unchanged otherwise.

- [ ] **Step 1: Write the failing test**

```python
    def test_removed_entry_that_still_ships_is_a_contradiction(self):
        root = self.make_project(
            manifest_rows=["bmad-dev-story,Dev Story,desc,bmm,path"],
            inventory=[{"name": "bmad-dev-story", "status": "removed",
                        "removed_in": "6.12.0", "replaced_by": "bmad-build"}],
        )
        code, out, _ = self.run_deps(root, "--format", "json")
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(
            data["status_contradictions"],
            [{"name": "bmad-dev-story", "declared": "removed", "manifest": "ships"}],
        )

    def test_contradiction_exits_5_under_strict(self):
        root = self.make_project(
            manifest_rows=["bmad-dev-story,Dev Story,desc,bmm,path"],
            inventory=[{"name": "bmad-dev-story", "status": "removed",
                        "removed_in": "6.12.0", "replaced_by": "bmad-build"}],
        )
        code, _, _ = self.run_deps(root, "--strict")
        self.assertEqual(code, 5)

    def test_absent_manifest_reports_null_not_contradictions(self):
        root = self.make_project(manifest_rows=None, inventory=[
            {"name": "bmad-dev-story", "status": "removed",
             "removed_in": "6.12.0", "replaced_by": "bmad-build"}])
        code, out, _ = self.run_deps(root, "--format", "json")
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertIsNone(data["shipped_skills"])
        self.assertEqual(data["status_contradictions"], [])
```

Extend the existing `make_project` helper to accept `manifest_rows` (writing
`_bmad/_config/skill-manifest.csv` with the header `canonicalId,name,description,module,path`,
or omitting the file when `None`) and `inventory`. Reuse the file's existing helpers; do not
add a second harness.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run -q --with 'ruamel.yaml>=0.18' python3 skills/l3io-util-doctor/scripts/tests/test-bmad-deps.py`
Expected: FAIL with `KeyError: 'status_contradictions'`.

- [ ] **Step 3: Implement manifest reading**

```python
def load_shipped_skills(project_root: Path) -> set[str] | None:
    """Canonical skill ids BMad declares it ships, from its own manifest.

    Returns None when the manifest is absent or unreadable -- the inventory is then
    unverifiable, which is reported as unknown rather than as agreement.
    """
    path = Path(project_root) / "_bmad" / "_config" / "skill-manifest.csv"
    try:
        with path.open(encoding="utf-8", newline="") as fh:
            rows = csv.reader(fh)
            header = next(rows, None)
            if not header or header[0].strip() != "canonicalId":
                return None
            return {r[0].strip() for r in rows if r and r[0].strip()}
    except (OSError, csv.Error):
        return None
```

Add `import csv` at the top.

- [ ] **Step 4: Implement contradiction detection**

In the verify path, after the inventory is loaded:

```python
SHIPPED_STATUSES = {"required", "optional", "deprecated"}

def find_contradictions(entries, shipped):
    """Inventory claims that BMad's manifest disagrees with. Empty when shipped is None."""
    if shipped is None:
        return []
    out = []
    for e in entries:
        status = e.get("status")
        name = e.get("name")
        if status == "not-a-skill" or not name:
            continue
        in_manifest = name in shipped
        if status == "removed" and in_manifest:
            out.append({"name": name, "declared": status, "manifest": "ships"})
        elif status in SHIPPED_STATUSES and not in_manifest:
            out.append({"name": name, "declared": status, "manifest": "absent"})
    return out
```

Add `shipped_skills` (sorted list or `None`) and `status_contradictions` to the JSON payload,
and print a `CONTRADICTION` line per entry in text format. Add a `--strict` flag; when set and
contradictions exist, return 5.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run -q --with 'ruamel.yaml>=0.18' python3 skills/l3io-util-doctor/scripts/tests/test-bmad-deps.py`
Expected: PASS.

- [ ] **Step 6: Verify against the real install**

Run: `skills/l3io-util-doctor/scripts/bmad-deps.py verify --project-root . --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["status_contradictions"])'`
Expected: `[]` — Task 2 already corrected the three entries. A non-empty result means Task 2 is incomplete.

- [ ] **Step 7: Document the new exit code and flag**

Update the module docstring: `--strict`, exit 5, and the two new JSON keys.

- [ ] **Step 8: Add `--strict` to CI**

In `.github/workflows/checks.yml`, the `bmad-deps.py unit tests` step stays as-is. Do **not**
add a repo-level `--strict` run: CI has no `_bmad/` install (it is gitignored), so the manifest
is absent there and the check would be vacuous. Record that in the docstring instead:

```
Note: CI cannot run --strict. _bmad/ is gitignored, so the manifest is absent and
load_shipped_skills() returns None. Contradiction detection is a runtime check, run
by /l3io-util-doctor check-deps against a real install -- the same division of labour
as the probe-path check.
```

- [ ] **Step 9: Commit**

```bash
git add skills/l3io-util-doctor/scripts/bmad-deps.py \
        skills/l3io-util-doctor/scripts/tests/test-bmad-deps.py
git commit -s -m "feat(l3io-util): derive dependency truth from BMad's own manifest

The inventory was a hand-kept list and it drifted -- three entries said
removed for skills 6.12.0 ships. _bmad/_config/skill-manifest.csv is
BMad's declaration of what it ships, installed and machine-readable.
The inventory is now an annotation over a derived set, and a claim that
contradicts the manifest is reported (exit 5 under --strict).

Derive the scope from the source of truth; never enumerate it by hand.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014DuCKCCF5scofVSPGvvn97"
```

---

### Task 5: Write `[modules.l3io-pm].implementation_artifacts` explicitly at setup

Today the key is absent, l3io falls back to its default, and that default happens to equal `modules.bmm`'s configured value. Two writers share one tree by coincidence. Making it explicit does not change the path — it makes the sharing a recorded decision.

**Files:**
- Modify: `skills/_shared/module-setup.md`
- Modify: `skills/l3io-pm-execute/module.yaml` (and siblings sharing `code: l3io-pm`)
- Test: `skills/_shared/tests/test-write-module-config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `[modules.l3io-pm]` in `_bmad/custom/config.toml` carrying `implementation_artifacts` and `planning_artifacts`, whose default values are read from `modules.bmm` when present.

- [ ] **Step 1: Write the failing test**

```python
    def test_l3io_pm_artifacts_default_to_bmm_values(self):
        root = self.make_project(central_toml=(
            '[modules.bmm]\n'
            'implementation_artifacts = "{project-root}/_bmad-output/implementation-artifacts"\n'
            'planning_artifacts = "{project-root}/_bmad-output/planning-artifacts"\n'))
        self.run_writer(root, module_code="l3io-pm", answers={})
        cfg = tomllib.loads((root / "_bmad" / "custom" / "config.toml").read_text())
        self.assertEqual(cfg["modules"]["l3io-pm"]["implementation_artifacts"],
                         "{project-root}/_bmad-output/implementation-artifacts")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run skills/_shared/tests/test-write-module-config.py`
Expected: FAIL — `KeyError: 'implementation_artifacts'`.

- [ ] **Step 3: Add the two variables to `module.yaml`**

In every `module.yaml` carrying `code: l3io-pm`, add under the variables block:

```yaml
  - key: implementation_artifacts
    prompt: "Where should l3io write implementation artifacts (state, stories, closure)?"
    default: "{project-root}/_bmad-output/implementation-artifacts"
  - key: planning_artifacts
    prompt: "Where do the project's planning artifacts (specs, PRD, architecture) live?"
    default: "{project-root}/_bmad-output/planning-artifacts"
```

Because check 16 requires sibling `module.yaml` files sharing a `code:` to agree on
module-level fields, apply the identical block to all four `l3io-pm` skills. Task 7 collapses
these to one file.

- [ ] **Step 4: Default from `modules.bmm` when unanswered**

In `write-module-config.py`, when a variable has no answer and the module is `l3io-pm`, prefer
the resolved `modules.bmm` value for that same key over the `module.yaml` default, so the
shared tree stays shared unless someone deliberately changes it. Add a comment stating
exactly that.

- [ ] **Step 5: Document the decision in `module-setup.md`**

Add a short paragraph: l3io and bmm point at one artifact tree by default; the value is now
written explicitly so the sharing is visible; changing it de-collides the two writers, and
`/l3io-util-doctor` detects a project holding both layouts.

- [ ] **Step 6: Run the tests and sync**

```bash
uv run skills/_shared/tests/test-write-module-config.py
npm run sync:scripts && node scripts/write-payload-manifest.mjs
npm run check:docs && npm run check:scripts && npm run check:manifest
```
Expected: all exit 0.

- [ ] **Step 7: Commit**

```bash
git add skills/_shared/module-setup.md skills/_shared/write-module-config.py \
        skills/_shared/tests/test-write-module-config.py skills/*/module.yaml \
        skills/*/assets/module-setup.md skills/*/scripts/write-module-config.py \
        skills/*/payload-manifest.json
git commit -s -m "feat(l3io-pm): write implementation_artifacts explicitly at setup

modules.l3io-pm was absent, so l3io ran on a default that happens to
equal modules.bmm's configured value. Two writers shared one tree by
coincidence. The value is unchanged; the sharing is now a decision.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014DuCKCCF5scofVSPGvvn97"
```

**Phase 1 is complete and shippable here.** All five gates green; no file has moved.

---

# Phase 2 — Conform and reorganize

Ordering is load-bearing: Task 6 changes `l3io-util`'s skill count, which decides its module shape in Task 7.

### Task 6: Retire `l3io-util-cleanup`

Deprecated forwarder since 2.1.0, zero uses in the scan window, still consuming skill-listing budget. Retiring it drops `l3io-util` to one skill, which makes it a standalone module in Task 7.

**Files:**
- Delete: `skills/l3io-util-cleanup/` (SKILL.md, customize.toml, module.yaml)
- Delete: `.claude/commands/l3io-util-cleanup.md` if present
- Modify: `docs/upgrading.md`, `README.md`, `docs/getting-started.md`, `docs/l3io-util-reference.md`, `docs/skills-and-sequence.md`, `CLAUDE.md`, `scripts/sync-shared-scripts.mjs` (the explanatory NOTE), `.claude-plugin/marketplace.json`

**Interfaces:**
- Consumes: nothing.
- Produces: `l3io-util` contains exactly one skill, `l3io-util-doctor`.

- [ ] **Step 1: Record the mapping in `docs/upgrading.md` first**

```markdown
### `l3io-util-cleanup` removed in <next-version>

`/l3io-util-cleanup` was a deprecated forwarder from 2.1.0 onward and is now removed.
Use `/l3io-util-doctor` with the same arguments — every mode name is unchanged.
```

Check 1 explicitly permits naming a removed skill when mapping it to its replacement, so this
doc is allowed to say the old name.

- [ ] **Step 2: Remove the skill and every live reference**

```bash
git rm -r skills/l3io-util-cleanup
git rm -f .claude/commands/l3io-util-cleanup.md 2>/dev/null || true
```

Then edit `README.md`, `docs/getting-started.md`, `docs/l3io-util-reference.md`,
`docs/skills-and-sequence.md`, `CLAUDE.md` and `.claude-plugin/marketplace.json` to drop the
skill. **Do not touch** `CHANGELOG.md` or anything under `docs/superpowers/plans/` or
`docs/superpowers/specs/` — historical records.

- [ ] **Step 3: Remove the now-stale NOTE in the sync script**

In `scripts/sync-shared-scripts.mjs`, delete the `allSkillDirs` NOTE explaining why
`l3io-util-cleanup` is excluded. Leaving a comment about a directory that no longer exists is
the same class of stale prose this work is removing.

- [ ] **Step 4: Verify the gates catch any reference you missed**

Run: `npm run check:docs`
Expected: exit 0. A failure here names a live doc still pointing at the removed skill —
fix it rather than exempting it.

- [ ] **Step 5: Confirm the doctor mode count still agrees**

Run: `npm run check:docs -- -v 2>&1 | grep doctor-mode-count`
Expected: the count check passes; retiring the forwarder does not change doctor's own modes.

- [ ] **Step 6: Regenerate manifests and commit**

```bash
node scripts/write-payload-manifest.mjs
git add docs/upgrading.md README.md docs/getting-started.md docs/l3io-util-reference.md \
        docs/skills-and-sequence.md CLAUDE.md .claude-plugin/marketplace.json \
        scripts/sync-shared-scripts.mjs skills/*/payload-manifest.json
git commit -s -m "feat(l3io-util)!: remove the deprecated l3io-util-cleanup forwarder

Deprecated since 2.1.0 and unused. docs/upgrading.md carries the
mapping to /l3io-util-doctor, whose mode names are unchanged.

This drops l3io-util to a single skill, which makes it a standalone
BMad module under the documented contract.

BREAKING CHANGE: /l3io-util-cleanup no longer exists. Use /l3io-util-doctor.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014DuCKCCF5scofVSPGvvn97"
```

---

### Task 7: Relocate `module.yaml` to each module's home and retire check 16

BMad's validator reads `assets/module.yaml` — from the setup skill for multi-skill modules (`validate-module.py:178`) and from the skill itself for standalone ones (`:139`). One per **module**, not one per skill.

**Files:**
- Create: `skills/l3io-pm-setup/assets/module.yaml` (from `skills/l3io-pm-execute/module.yaml`)
- Move: `skills/l3io-util-doctor/module.yaml` → `skills/l3io-util-doctor/assets/module.yaml`
- Move: `skills/l3io-sec-redteam/module.yaml` → `skills/l3io-sec-redteam/assets/module.yaml`
- Move: `skills/l3io-arch-review/module.yaml` → `skills/l3io-arch-review/assets/module.yaml`
- Delete: `module.yaml` from `l3io-pm-execute`, `l3io-pm-plan`, `l3io-pm-help`, `l3io-pm-sync`
- Modify: `scripts/check-docs.mjs` — remove `checkModuleYamlAgreement()`, its call at `:1262`, `MODULE_SHARED_FIELDS`, and the header comment for check 16; renumber 17 → 16 in the header and in `CLAUDE.md`
- Modify: `scripts/check-docs.mjs` — check 17's source list reads `skills/*/module.yaml`; update to `skills/*/assets/module.yaml`

**Interfaces:**
- Consumes: Task 6's single-skill `l3io-util`.
- Produces: exactly four `assets/module.yaml` files, one per module code. `skills/l3io-pm-setup/` exists as a directory (its `SKILL.md` arrives in Task 9).

- [ ] **Step 1: Write the failing test for the source-list change**

```javascript
test("check 17 scans assets/module.yaml, not a skill-root module.yaml", async (t) => {
  const root = await makeFixture(t);
  writeInventory(root, []);
  writeSkillFile(root, "l3io-pm-setup/assets/module.yaml",
    "code: l3io-pm\nname: X\ndescription: uses bmad-nonexistent\n");
  const { code, out } = runCheckDocs(root);
  assert.equal(code, 1);
  assert.match(out, /names 'bmad-nonexistent', not declared/);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm run test:scripts`
Expected: FAIL — exit 0, because the scanner only looks at `skills/*/module.yaml`.

- [ ] **Step 3: Move the files**

```bash
mkdir -p skills/l3io-pm-setup/assets
git mv skills/l3io-pm-execute/module.yaml skills/l3io-pm-setup/assets/module.yaml
git rm skills/l3io-pm-plan/module.yaml skills/l3io-pm-help/module.yaml skills/l3io-pm-sync/module.yaml
for s in l3io-util-doctor l3io-sec-redteam l3io-arch-review; do
  mkdir -p "skills/$s/assets"
  git mv "skills/$s/module.yaml" "skills/$s/assets/module.yaml"
done
```

- [ ] **Step 4: Update check 17's source list**

```javascript
  for (const entry of fs.readdirSync(path.join(repoRoot, "skills"), { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const rel = `skills/${entry.name}/assets/module.yaml`;
    if (exists(rel)) sources.push(rel);
  }
```

- [ ] **Step 5: Delete check 16**

Remove `MODULE_SHARED_FIELDS`, the whole `checkModuleYamlAgreement()` function, its call, and
its header-comment entry. Renumber the header list so `bmad-dependency-inventory` becomes 16,
and update every `check:docs runs seventeen checks` / numbered reference in `CLAUDE.md`,
`README.md` and `docs/` to sixteen.

Check 16 guarded *sibling* `module.yaml` files sharing a `code:`. After this task each module
has exactly one, so it can never fire again. A guard that cannot fire reads as protection that
is not there.

- [ ] **Step 6: Verify**

Run: `npm run test:scripts && npm run check:docs -- -v`
Expected: both exit 0; verbose output lists sixteen checks and no `module-yaml-agreement`.

- [ ] **Step 7: Commit**

```bash
git add -u skills/ scripts/check-docs.mjs scripts/tests/check-docs.test.mjs \
        CLAUDE.md README.md docs/
git add skills/l3io-pm-setup/assets/module.yaml
git commit -s -m "refactor(infra)!: one module.yaml per module, under assets/

BMad's validator reads assets/module.yaml -- from the setup skill for
multi-skill modules, from the skill itself for standalone ones. The
package shipped one per skill at the skill root, which is why
validate-module.py detected no module at all.

Retires check 16 (module-yaml-agreement) in the same change: it guarded
sibling module.yaml files sharing a code, and there are no siblings
left. A guard that can no longer fire is worse than no guard.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014DuCKCCF5scofVSPGvvn97"
```

---

### Task 8: Add the two merge scripts BMad's validator requires

`validate-module.py:137–165` checks these by **presence only** — it never reads them. So they can satisfy the documented contract while writing TOML, which is what core 6.12 actually reads.

**Files:**
- Create: `skills/_shared/merge-config.py`
- Create: `skills/_shared/merge-help-csv.py`
- Test: `skills/_shared/tests/test-merge-help-csv.py`
- Modify: `scripts/sync-shared-scripts.mjs`

**Interfaces:**
- Consumes: `write-module-config.py`'s existing layer logic.
- Produces:
  - `merge-config.py --project-root R --module-yaml Y --answers J` — thin wrapper delegating to `write_module_config.main()`; writes **TOML** to `_bmad/custom/config.toml` / `config.user.toml`.
  - `merge-help-csv.py --project-root R --module-help-csv C --module-code M` — anti-zombie merge into `_bmad/_config/bmad-help.csv`.

- [ ] **Step 1: Write the failing test for the help merger**

```python
    def test_replaces_only_this_modules_rows(self):
        root = self.make_project(existing_help=[
            "skill,module,description",
            "bmad-help,core,Core help",
            "l3io-old,l3io-pm,Stale row",
        ])
        self.run_merge(root, module_code="l3io-pm", rows=[
            "l3io-pm-execute,l3io-pm,Run the plan"])
        text = (root / "_bmad" / "_config" / "bmad-help.csv").read_text()
        self.assertIn("bmad-help,core,Core help", text)
        self.assertIn("l3io-pm-execute,l3io-pm,Run the plan", text)
        self.assertNotIn("l3io-old", text)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run skills/_shared/tests/test-merge-help-csv.py`
Expected: FAIL — file not found.

- [ ] **Step 3: Write `merge-config.py`**

```python
#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["tomlkit>=0.13", "ruamel.yaml>=0.18"]
# ///
"""
merge-config.py -- the name BMad's module validator requires; the behaviour core needs.

bmad-module-builder's scaffolder emits a merge-config.py that writes _bmad/config.yaml
and _bmad/config.user.yaml, and deletes per-module config.yaml files. Core 6.12's
config_utils.load_central_config reads TOML ONLY:

    _bmad/config.toml -> config.user.toml -> custom/config.toml -> custom/config.user.toml

so the scaffolder's writer would make every l3io setting invisible and would delete
installer-generated files that exist. validate-module.py checks this file's PRESENCE
only (lines 137-165) and never reads it, so conforming to the name while keeping the
correct target satisfies the documented contract without breaking config resolution.

See ADR-0007 and docs/superpowers/specs/2026-09-20-l3io-customization-layer-design.md §2.
"""
import runpy
import sys
from pathlib import Path

if __name__ == "__main__":
    target = Path(__file__).with_name("write-module-config.py")
    sys.argv[0] = str(target)
    runpy.run_path(str(target), run_name="__main__")
```

- [ ] **Step 4: Write `merge-help-csv.py`**

```python
#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# ///
"""
merge-help-csv.py -- register a module's capabilities in BMad's help index.

Targets {project-root}/_bmad/_config/bmad-help.csv, which is the file the help system
actually reads. bmb's scaffolder targets _bmad/module-help.csv, which does not exist in
a core 6.12 install. See ADR-0007.

Anti-zombie: every row belonging to --module-code is dropped before the module's current
rows are appended, so a capability removed from the module cannot survive as a stale row.
Other modules' rows keep their original order.
"""
import argparse
import csv
import sys
from pathlib import Path

HELP_REL = ("_bmad", "_config", "bmad-help.csv")
MODULE_COLUMN = 1


def reject_unresolved(label: str, value: str) -> str:
    if "{project-root}" in value:
        sys.stderr.write(
            f"error: {label} contains an unresolved {{project-root}} token: {value}\n"
            "Resolve it to a real path before invoking this script.\n")
        raise SystemExit(2)
    return value


def merge(target: Path, module_code: str, rows: list[list[str]]) -> None:
    header, kept = None, []
    if target.exists():
        with target.open(encoding="utf-8", newline="") as fh:
            all_rows = list(csv.reader(fh))
        if all_rows:
            header, body = all_rows[0], all_rows[1:]
            kept = [r for r in body
                    if len(r) <= MODULE_COLUMN or r[MODULE_COLUMN].strip() != module_code]
    if header is None:
        header = ["skill", "module", "description"]
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(kept)
        writer.writerows(rows)


def main() -> int:
    p = argparse.ArgumentParser(description="Merge a module's help rows into bmad-help.csv.")
    p.add_argument("--project-root", required=True)
    p.add_argument("--module-help-csv", required=True,
                   help="the module's own assets/module-help.csv")
    p.add_argument("--module-code", required=True)
    args = p.parse_args()

    root = Path(reject_unresolved("--project-root", args.project_root))
    source = Path(reject_unresolved("--module-help-csv", args.module_help_csv))

    with source.open(encoding="utf-8", newline="") as fh:
        rows = [r for r in csv.reader(fh) if r]
    if rows and rows[0] and rows[0][0].strip() == "skill":
        rows = rows[1:]

    merge(root.joinpath(*HELP_REL), args.module_code, rows)
    print(f"merged {len(rows)} help row(s) for {args.module_code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run skills/_shared/tests/test-merge-help-csv.py`
Expected: PASS.

- [ ] **Step 6: Add both to the sync scope — module homes only**

In `scripts/sync-shared-scripts.mjs`, add a new group whose destinations are the **four module
homes** (`l3io-pm-setup`, `l3io-util-doctor`, `l3io-sec-redteam`, `l3io-arch-review`):

```javascript
// The two merge scripts BMad's validator requires, and module-setup.md, belong in each
// module's HOME -- the setup skill for multi-skill modules, the skill itself for
// standalone ones. Syncing them into every operational skill would ship four copies of a
// procedure only one of them runs.
const moduleHomeDirs = [
  "l3io-pm-setup", "l3io-util-doctor", "l3io-sec-redteam", "l3io-arch-review",
].map((name) => path.join(repoRoot, "skills", name));

const moduleHomeFiles = [
  { src: path.join(sharedDir, "merge-config.py"), rel: path.join("scripts", "merge-config.py") },
  { src: path.join(sharedDir, "merge-help-csv.py"), rel: path.join("scripts", "merge-help-csv.py") },
];
```

- [ ] **Step 7: Add the new test to CI**

In `.github/workflows/checks.yml`, after the `write-module-config.py unit tests` step:

```yaml
    - name: merge-help-csv.py unit tests
      run: uv run skills/_shared/tests/test-merge-help-csv.py
```

- [ ] **Step 8: Sync, regenerate, verify**

```bash
npm run sync:scripts && node scripts/write-payload-manifest.mjs
npm run check:scripts && npm run check:manifest && npm run check:docs
```
Expected: all exit 0.

- [ ] **Step 9: Commit**

```bash
git add skills/_shared/merge-config.py skills/_shared/merge-help-csv.py \
        skills/_shared/tests/test-merge-help-csv.py scripts/sync-shared-scripts.mjs \
        .github/workflows/checks.yml skills/*/scripts/ skills/*/payload-manifest.json
git commit -s -m "feat(infra): add merge-config.py and merge-help-csv.py

The names BMad's module validator requires, with the behaviour core
needs. The scaffolder's merge-config.py writes _bmad/config.yaml, which
core 6.12's TOML-only resolver never reads, and deletes per-module
config.yaml files that exist here. validate-module.py checks presence
only, so the name conforms while the target stays correct.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014DuCKCCF5scofVSPGvvn97"
```

---

### Task 9: Create `l3io-pm-setup`, the one setup skill

Only `l3io-pm` is multi-skill. `l3io-util`, `l3io-sec` and `l3io-arch` are standalone after Task 6 and self-register as they do today.

**Files:**
- Create: `skills/l3io-pm-setup/SKILL.md`, `skills/l3io-pm-setup/customize.toml`
- Present already: `skills/l3io-pm-setup/assets/module.yaml` (Task 7), `scripts/merge-*.py` (Task 8)
- Create: `skills/l3io-pm-setup/assets/module-help.csv` (consolidated from the four PM skills)
- Create: `.claude/commands/l3io-pm-setup.md` symlink → `../../skills/l3io-pm-setup/SKILL.md`
- Modify: `.claude-plugin/marketplace.json`

**Interfaces:**
- Consumes: `assets/module.yaml`, `scripts/merge-config.py`, `scripts/merge-help-csv.py`.
- Produces: skill `l3io-pm-setup`, invoked as `/l3io-pm-setup`; `customize.toml` root key `[workflow]`.

- [ ] **Step 1: Write `SKILL.md`**

Frontmatter `name: l3io-pm-setup`; description scoped to install/configure intent, e.g.
`Sets up the LiquidLogicLabs PM module in a project. Use when the user requests to 'install l3io-pm', 'configure l3io-pm', or 'setup l3io-pm'.`
Body follows the shared `assets/module-setup.md` procedure and runs the two merge scripts with
resolved absolute paths.

- [ ] **Step 2: Write `customize.toml`**

Root key `[workflow]` — it is a workflow/utility skill, not a memory agent. Using `[agent]`
means overrides are ignored silently.

```toml
[workflow]
activation_steps_prepend = []
activation_steps_append = []
persistent_facts = []
on_complete = ""
```

- [ ] **Step 3: Consolidate the help CSV**

Merge the four PM skills' `assets/module-help.csv` rows into
`skills/l3io-pm-setup/assets/module-help.csv`, then delete the four originals. Keep one row per
distinct capability; check menu codes are unique.

- [ ] **Step 4: Create the command symlink and register in the marketplace**

```bash
ln -s ../../skills/l3io-pm-setup/SKILL.md .claude/commands/l3io-pm-setup.md
```

Add `l3io-pm-setup` to `.claude-plugin/marketplace.json` alongside the other skills.

- [ ] **Step 5: Run BMad's validator**

Run: `uv run .claude/skills/bmad-module-builder/scripts/validate-module.py skills/`
Expected: `"status": "pass"`, with `setup_skill: "l3io-pm-setup"` in `info`.

If it still fails, read the finding rather than guessing: it names the exact missing file.

- [ ] **Step 6: Validate the three standalone modules**

```bash
for s in l3io-util-doctor l3io-sec-redteam l3io-arch-review; do
  echo "== $s =="; uv run .claude/skills/bmad-module-builder/scripts/validate-module.py "skills/$s"
done
```
Expected: `"status": "pass"` and `"standalone": true` for each.

- [ ] **Step 7: Verify the four gates**

Run: `npm run check:docs && npm run check:scripts && npm run check:manifest && npm run test:scripts`
Expected: all exit 0. `check:docs` check 1 (skill-names) now resolves `l3io-pm-setup`.

- [ ] **Step 8: Commit**

```bash
git add skills/l3io-pm-setup/ .claude/commands/l3io-pm-setup.md \
        .claude-plugin/marketplace.json skills/*/payload-manifest.json
git add -u skills/
git commit -s -m "feat(l3io-pm): add l3io-pm-setup, the module's setup skill

l3io-pm is the only multi-skill module, so it is the only one needing a
dedicated setup skill under BMad's documented contract. l3io-util,
l3io-sec and l3io-arch are single-skill and self-register.

validate-module.py now passes for all four modules.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014DuCKCCF5scofVSPGvvn97"
```

---

### Task 10: Detect-and-prompt in the four PM operational skills

The published docs do not say whether a setup skill auto-runs; the installed scaffolder says "run the setup skill". Detect-and-prompt is correct either way: the existing config check ends in a pointer instead of a silent write.

**Files:**
- Modify: `skills/_shared/config-resolution.md` (§5, "An absent module section is not a first-run")
- Modify: `skills/l3io-pm-execute/SKILL.md`, `l3io-pm-plan/SKILL.md`, `l3io-pm-help/SKILL.md`, `l3io-pm-sync/SKILL.md` — the On Activation config step

**Interfaces:**
- Consumes: `l3io-pm-setup` from Task 9.
- Produces: a uniform activation behaviour — missing `modules.l3io-pm` prints one line naming `/l3io-pm-setup` and halts; present config proceeds silently.

- [ ] **Step 1: Write the directive in `config-resolution.md`**

> **When `modules.l3io-pm` is absent.** This is not a first-run and must not trigger setup
> silently. Print exactly one line — `l3io-pm is not configured in this project. Run
> /l3io-pm-setup to configure it.` — and halt. Do not guess defaults and do not write config
> from an operational skill: `l3io-pm-setup` is the only writer, so there is one place where
> the module's settings come from.

Note this replaces the current default-and-proceed behaviour for `l3io-pm` **only**; the three
standalone modules keep auto-registration.

- [ ] **Step 2: Apply to the four SKILL.md files**

Each PM skill's *Load config* activation step gains the check before any state read.

- [ ] **Step 3: Sync and regenerate**

```bash
npm run sync:scripts && node scripts/write-payload-manifest.mjs
```

- [ ] **Step 4: Verify**

Run: `npm run check:docs && npm run check:scripts && npm run check:manifest`
Expected: all exit 0. `check:docs` check 9 (authoring-paths) must still pass — the directive
references `references/config-resolution.md`, never `skills/_shared/`.

- [ ] **Step 5: Commit**

```bash
git add skills/_shared/config-resolution.md skills/l3io-pm-*/SKILL.md \
        skills/*/references/config-resolution.md skills/*/payload-manifest.json
git commit -s -m "feat(l3io-pm): detect missing config and name the setup skill

The published docs do not say whether a setup skill auto-runs; the
scaffolder reference says to run it. Detect-and-prompt is correct under
either reading, and keeps l3io-pm-setup the only writer of the module's
settings.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014DuCKCCF5scofVSPGvvn97"
```

---

### Task 11: Narrow the shared-sync scope to module homes

`assets/module-setup.md` and `write-module-config.py` currently sync into **all 8** skills. Only the four module homes run them. This removes shipped payload.

**Files:**
- Modify: `scripts/sync-shared-scripts.mjs` — `allSkillDirs` / `allSkillFiles`
- Delete: the stale copies the narrowed sync leaves behind

**Interfaces:**
- Consumes: `moduleHomeDirs` from Task 8.
- Produces: `module-setup.md` + all three config/merge scripts present in exactly four skills; `config-resolution.md` still in all skills that resolve config.

- [ ] **Step 1: Move `module-setup.md` and `write-module-config.py` into the module-home group**

Remove them from `allSkillFiles`; add to `moduleHomeFiles`. Leave `config-resolution.md` in
`allSkillFiles` — every skill resolves config, only module homes perform setup.

- [ ] **Step 2: Delete the copies that are no longer synced**

```bash
git rm skills/l3io-pm-execute/assets/module-setup.md \
       skills/l3io-pm-plan/assets/module-setup.md \
       skills/l3io-pm-help/assets/module-setup.md \
       skills/l3io-pm-sync/assets/module-setup.md \
       skills/l3io-pm-execute/scripts/write-module-config.py \
       skills/l3io-pm-plan/scripts/write-module-config.py \
       skills/l3io-pm-help/scripts/write-module-config.py \
       skills/l3io-pm-sync/scripts/write-module-config.py
```

- [ ] **Step 3: Verify the sync check agrees**

Run: `npm run sync:scripts && npm run check:scripts`
Expected: exit 0, and no file reappears in the four PM operational skills.

- [ ] **Step 4: Regenerate manifests and confirm payload shrank**

```bash
node scripts/write-payload-manifest.mjs
npm run check:manifest
du -sh skills/l3io-pm-execute
```
Expected: `check:manifest` exits 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/sync-shared-scripts.mjs skills/*/payload-manifest.json
git add -u skills/
git commit -s -m "refactor(infra): sync setup payload to module homes only

module-setup.md and write-module-config.py shipped into all 8 skills
while only the 4 module homes run them -- the same dead-payload shape
this package removed when it stopped vendoring BMad core scripts.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014DuCKCCF5scofVSPGvvn97"
```

---

### Task 12: Split `l3io-pm-help` into a router plus `steps/`

19,997 B with zero `steps/` files, against `l3io-util-doctor`'s 19,914 B across 20. CLAUDE.md's Module Layout rule was written about exactly this failure.

**Files:**
- Modify: `skills/l3io-pm-help/SKILL.md` → router
- Create: `skills/l3io-pm-help/steps/step-01-config.md`, `step-02-detect-layout.md`, `step-03-read-state.md`, `step-04-health-snapshot.md`, `step-05-recommend.md`, `mode-progress.md`, `mode-list-plan.md`

**Interfaces:**
- Consumes: nothing.
- Produces: `SKILL.md` under 6,000 B carrying overview, the keyword/mode table and safety rules; each mode body in its own file loaded only when selected.

- [ ] **Step 1: Carve the existing sections into `steps/` verbatim**

Map, from the current headings:

| Current section | New file |
|---|---|
| `### 1. Load paths from config` (`:32`) | `steps/step-01-config.md` |
| `### 2. Detect state layout` (`:100`) | `steps/step-02-detect-layout.md` |
| `### 3. Read state files` (`:174`) | `steps/step-03-read-state.md` |
| `### 4. Build health snapshot` (`:203`) | `steps/step-04-health-snapshot.md` |
| `### 5. Recommend next action` (`:234`) | `steps/step-05-recommend.md` |
| `### Progress Mode` (`:261`) | `steps/mode-progress.md` |
| `### List Plan Mode` (`:327`) | `steps/mode-list-plan.md` |

Move the text unchanged in this step — behaviour changes belong in Task 13, not here.

- [ ] **Step 2: Rewrite `SKILL.md` as a router**

Keep frontmatter, overview, On Activation, and add a routing table mapping argument → step
file, mirroring `l3io-util-doctor/SKILL.md`'s shape. Default (no argument) runs steps 01–05 in
order.

- [ ] **Step 3: Fix cross-references**

Any `§N` reference into the moved sections must resolve — `check:docs` check 3 (section-refs)
enforces this, and check 9 (authoring-paths) forbids pointing at `skills/_shared/`.

- [ ] **Step 4: Verify size and gates**

```bash
wc -c skills/l3io-pm-help/SKILL.md
npm run check:docs && npm run check:scripts && npm run check:manifest
```
Expected: `SKILL.md` under 6,000 B; all gates exit 0.

- [ ] **Step 5: Commit**

```bash
git add skills/l3io-pm-help/ skills/*/payload-manifest.json
git commit -s -m "refactor(l3io-pm): split l3io-pm-help into a router and steps/

19,997 B with zero steps/ files, against the doctor's 19,914 B across
20. Every invocation paid for six procedures it would not run -- the
failure CLAUDE.md's Module Layout rule was written about.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014DuCKCCF5scofVSPGvvn97"
```

---

### Task 13: `pm-help progress` forwards to `doctor stats`

Both render a plan-aware phase→epic→sprint→story tree from `pm-status.py report`. `doctor stats` is the richer implementation (dwell times, stuck-item flags, backlog by severity, calibration state).

**Files:**
- Modify: `skills/l3io-pm-help/steps/mode-progress.md`
- Modify: `skills/l3io-pm-help/SKILL.md` (routing table + description)
- Modify: `docs/l3io-util-reference.md`, `docs/skills-and-sequence.md`

**Interfaces:**
- Consumes: Task 12's `steps/` layout.
- Produces: `mode-progress.md` contains only a forwarding directive; the tree-rendering prose is deleted, not duplicated.

- [ ] **Step 1: Replace the body with a forwarder**

```markdown
# Progress Mode — forwards to `/l3io-util-doctor stats`

`stats` is the one plan-aware progress view. It renders the same phase → epic → sprint →
story tree from `pm-status.py report`, and additionally reports per-status dwell time,
stuck-item flags, backlog size by severity and calibration state.

Invoke `skill:l3io-util-doctor` with `stats`, passing through any scope argument the user
gave (`active`, `queued`, `everything`). Report its output unchanged; add no second summary.

If `l3io-util-doctor` is not installed, say so in one line and stop — do not re-implement
the tree here. That duplication is what this forwarder removed.
```

- [ ] **Step 2: Update the skill description**

`l3io-pm-help`'s frontmatter currently advertises `progress` as its own tree. Reword so it
names the forward, keeping the `progress` keyword working.

- [ ] **Step 3: Verify the docs agree**

Run: `npm run check:docs`
Expected: exit 0 — check 1 resolves `l3io-util-doctor`, check 15 (doctor-mode-count) is
unaffected because `stats` already existed.

- [ ] **Step 4: Commit**

```bash
git add skills/l3io-pm-help/ docs/l3io-util-reference.md docs/skills-and-sequence.md \
        skills/*/payload-manifest.json
git commit -s -m "refactor(l3io-pm): pm-help progress forwards to doctor stats

Two modules rendered the same tree from pm-status.py report. doctor
stats is the richer one; pm-help now forwards rather than duplicating.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014DuCKCCF5scofVSPGvvn97"
```

---

### Task 14: Scaffold the overlay owner

Phase 3 produces overlay TOML for `bmad-build`, `bmad-review` and the story skills, and no skill has that job. This task creates the home and its contract; the overlay **content** is Phase 3.

**Files:**
- Create: `skills/l3io-util-doctor/steps/overlay.md`
- Modify: `skills/l3io-util-doctor/SKILL.md` — routing table + mode count
- Create: `skills/l3io-util-doctor/assets/overlays/README.md`

**Interfaces:**
- Consumes: nothing.
- Produces: `/l3io-util-doctor overlay` — three actions: `list` (what is customizable, via
  `list_customizable_skills.py`), `diff` (staged overlay vs current merge), `verify` (via
  `resolve_customization.py --key workflow`). It **stages** overlay files and never writes
  `_bmad/custom/` itself.

- [ ] **Step 1: Write `steps/overlay.md`**

State the constraint prominently: BMad Builder says there is no supported pattern for modules
to write into `_bmad/custom/`, so this mode generates to
`{implementation_artifacts}/l3io/overlays/<skill>.toml`, prints the diff, and tells the user
the one command to place it. Document the three actions and the verification command:

```bash
uv run {project-root}/_bmad/scripts/resolve_customization.py \
  --skill {skill-install-path} --project-root {project-root} --key workflow
```

- [ ] **Step 2: Register the mode**

Add a routing-table row. Check 15 (`doctor-mode-count`) counts modes from the `steps/`
directory **and** the routing table — both must agree, and the stated count in `SKILL.md` and
`CLAUDE.md` must be updated from twenty to twenty-one.

- [ ] **Step 3: Verify the mode count check**

Run: `npm run check:docs -- -v 2>&1 | grep doctor-mode-count`
Expected: passes at twenty-one.

- [ ] **Step 4: Verify all gates**

Run: `npm run check:docs && npm run check:scripts && npm run check:manifest && npm run test:scripts`
Expected: all exit 0.

- [ ] **Step 5: Commit**

```bash
git add skills/l3io-util-doctor/ CLAUDE.md skills/*/payload-manifest.json
git commit -s -m "feat(l3io-util): add the overlay mode, owner of the BMad customization layer

Phase 3 produces overlay TOML for bmad-build and bmad-review, and no
skill had that job. Generates to a staging path, diffs against the
current merge and verifies with resolve_customization.py -- it never
writes _bmad/custom/, which BMad reserves for end users.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014DuCKCCF5scofVSPGvvn97"
```

---

### Task 15: Promote the artifact contract to a named reference

The story, issue and sprint schemas are what the package exists to replace, and they are spread across `pm-execute`/`pm-plan` step files and `_shared/status-files.md` with no single owner. Phase 3's overlays must point BMad's skills at *one* contract; that contract has to exist first.

**Files:**
- Create: `skills/_shared/artifact-contract.md`
- Modify: `skills/_shared/status-files.md` (state-layout content stays; schema content moves out and is linked)
- Modify: `scripts/sync-shared-scripts.mjs` (new entry in `pmRefFiles`)
- Modify: the `pm-execute` / `pm-plan` step files and `SKILL.md`s that inline schema prose

**Interfaces:**
- Consumes: nothing.
- Produces: `references/artifact-contract.md` in the four PM skills and `l3io-util-doctor` — the single source of truth for the story, issue and sprint node schemas. `status-files.md` keeps placement rules, `depends_on` and the read/auto-fallback procedure, and links to it.

- [ ] **Step 1: Create the contract by moving, not rewriting**

`skills/_shared/artifact-contract.md` gains numbered sections so `<file>.md §N` references
resolve (check 3 enforces this):

```markdown
# Artifact contract

The schemas this package writes, and the one place they are defined. `status-files.md`
owns *where* nodes live; this file owns *what is in them*.

## 1. Story node (`E{nnn}-S{nn}-{nnn}.yaml`)
## 2. Sprint node (`sprint.yaml`)
## 3. Epic node (`epic.yaml`)
## 4. Issue record (`issues.yaml`, `issues-resolved.yaml`)
## 5. Story document frontmatter
## 6. Completion evidence
```

Fill each section by **moving** the existing annotated schema out of the skill `SKILL.md`s and
step files verbatim. Do not re-derive it from `pm-status.py` — the point is one copy, and a
rewrite would create a second description that can drift.

- [ ] **Step 2: Replace the vacated prose with pointers**

Each place that carried a schema now names the section: `references/artifact-contract.md §1`.
Never `skills/_shared/...` — that path is not installed, and check 9 fails on it.

- [ ] **Step 3: Add to the sync groups**

Add to `pmRefFiles` (destination `references/artifact-contract.md`) so it reaches the four PM
skills, and to the doctor's group — `l3io-util-doctor` reads and repairs these nodes.

- [ ] **Step 4: Sync, regenerate, verify**

```bash
npm run sync:scripts && node scripts/write-payload-manifest.mjs
npm run check:docs && npm run check:scripts && npm run check:manifest
```
Expected: all exit 0. Check 3 (section-refs) proves every new `§N` pointer resolves; check 9
(authoring-paths) proves none of them points at `skills/_shared/`.

- [ ] **Step 5: Commit**

```bash
git add skills/_shared/artifact-contract.md skills/_shared/status-files.md \
        scripts/sync-shared-scripts.mjs skills/*/references/ skills/l3io-pm-*/ \
        skills/*/payload-manifest.json
git commit -s -m "refactor(l3io-pm): give the artifact contract one home

The story, issue and sprint schemas are what this package exists to
replace, and they were spread across step files and SKILL.mds with no
owner. Phase 3's overlays must point BMad's skills at one contract.

Moved verbatim rather than rewritten -- a second description of the
same schema is the thing that drifts.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014DuCKCCF5scofVSPGvvn97"
```

---

### Task 16: Record ADR-0007 and update `CLAUDE.md`

**Files:**
- Create: `docs/adr/0007-<slug>.md`
- Modify: `docs/adr/0006-bmad-dependency-inventory.md` (amendment note)
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: every preceding task.
- Produces: ADR-0007, accepted, covering the module packaging shape, the TOML-writer deviation and check 16's retirement.

- [ ] **Step 1: Reserve the number**

```bash
uv run _bmad/scripts/pm-status.py adr-reserve --epic E000 --slug module-packaging-shape
```

Use whatever number it returns; do not hand-pick. If the register is absent it starts from
max(register, files on disk) + 1.

- [ ] **Step 2: Write the ADR**

Sections `Status` / `Context` / `Decision` / `Consequences`, matching ADR-0006's shape. Context
must carry the evidence: `validate-module.py:61` and `:178`, `config_utils.load_central_config`
reading TOML only, bmb's `merge-config.py` writing `_bmad/config.yaml` and deleting per-module
files, and the presence-only check at `:137–165`. Decision records the mixed module shape,
detect-and-prompt, the TOML writer under the required name, and check 16's retirement with its
reason.

- [ ] **Step 3: Amend ADR-0006**

Add, without rewriting history:

```markdown
## Amendment — 2026-09-20

ADR-0006 said correctly that bmad-create-story and bmad-dev-story "were deprecated to
shims". The inventory it governs encoded them as `removed`, and three of six removed
entries were wrong. A `deprecated` status now exists, and shipped-ness is derived from
`_bmad/_config/skill-manifest.csv` rather than asserted by hand. See ADR-0007 and
docs/superpowers/specs/2026-09-20-l3io-customization-layer-design.md.
```

- [ ] **Step 4: Update `CLAUDE.md`**

Update: the Skill Directory table (remove `l3io-util-cleanup`, add `l3io-pm-setup`); the
Shared Files sync table (module homes, the two merge scripts, `artifact-contract.md`); the
check count (seventeen → sixteen) and check 16's description; the ADR line in Repository
Purpose; the doctor mode count (twenty → twenty-one); the Dependencies section (`deprecated`
status, `bmad-build`); and the Module Layout note, which must now say that setup lives in each
module's home rather than "embedded in each operational skill".

- [ ] **Step 5: Verify every gate one final time**

Includes `test-merge-help-csv.py` and the four validator runs added by Tasks 8–9.

```bash
npm run check:docs && npm run check:scripts && npm run check:manifest \
  && npm run check:version && npm run test:scripts
uv run .claude/skills/bmad-module-builder/scripts/validate-module.py skills/
for s in l3io-util-doctor l3io-sec-redteam l3io-arch-review; do
  uv run .claude/skills/bmad-module-builder/scripts/validate-module.py "skills/$s"
done
uv run skills/_shared/tests/test-pm-status.py
uv run skills/_shared/tests/test-write-module-config.py
uv run skills/_shared/tests/test-merge-help-csv.py
uv run -q --with 'ruamel.yaml>=0.18' python3 skills/l3io-util-doctor/scripts/tests/test-bmad-deps.py
```
Expected: every command exits 0; all four validator runs report `"status": "pass"`.

- [ ] **Step 6: Commit**

```bash
git add docs/adr/ CLAUDE.md
git commit -s -m "docs(l3io): record ADR-0007, module packaging shape

Records the mixed standalone/multi-skill shape, detect-and-prompt, the
deliberate TOML-writer deviation from bmb's scaffolder, and check 16's
retirement. Amends ADR-0006, whose prose was right and whose data drifted.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014DuCKCCF5scofVSPGvvn97"
```

---

## Out of scope

Phase 3 (overlay content: the `l3io-spec-alignment` review layer, lens exports,
`implementation_handoff`, `persistent_facts`, `on_complete`, and retiring the preference probe)
is specified in §5 of the spec and is **not** implemented by this plan. Task 3's exemption
markers and Task 14's overlay mode are the seams it plugs into.

## Post-merge verification (manual, not CI)

CI has no `_bmad/` install, so two things can only be checked against a real project:

1. `/l3io-util-doctor check-deps` in a consuming project — probe paths resolve, and
   `status_contradictions` is empty.
2. A clean install in a throwaway project — `l3io-util`, `l3io-sec` and `l3io-arch` register
   with no manual step; `l3io-pm` prints the detect-and-prompt line naming `/l3io-pm-setup`.
