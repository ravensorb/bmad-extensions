# bmad-extensions v2.0.0 Migration Implementation Plan

> **Superseded (2026-08-16).** The state-layout sections of this document — `_bmad/state/`,
> per-epic `E{nnn}-status.yaml` files, and the three flat status files — are superseded by
> `docs/superpowers/specs/2026-08-16-v3-state-relocation-design.md`. This document is
> preserved as the historical record of the legacy per-epic migration design; do not
> implement from its state layout sections.

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate bmad-extensions from v1.x to v2.0.0, matching the reference implementation's architecture with l3io branding and GitHub-only sync.

**Architecture:** Copy-and-adapt from the reference implementation for all structural content; author `l3io-pm-sync` Python scripts fresh (GitHub-only, no ADO); rewrite `sync-shared-scripts.mjs` for the new flat layout; finish with `npm run release:major`.

**Tech Stack:** Python 3.11+, ruamel.yaml (auto-provisioned via uv/PEP-723), Node.js 18+, uv, bash

**Spec:** `docs/superpowers/specs/2026-08-14-v2-migration-design.md`

## Global Constraints

- `REF` = `/mnt/source/git/avanade/bmad/avanade-extensions` — reference implementation root (read-only source)
- All commits must be signed: `git commit -s`
- **No external org name** in any file, comment, commit message, or changelog
- **Global rename tokens** — apply to every file copied from REF:

  | Find | Replace |
  |---|---|
  | `ava-pm` | `l3io-pm` |
  | `ava-sec` | `l3io-sec` |
  | `ava-util` | `l3io-util` |
  | `ava-arch` | `l3io-arch` |
  | Any remaining `ava-` prefix | `l3io-` |
  | `Avanade PM` | `LiquidLogicLabs PM` |
  | `Avanade` (standalone) | `LiquidLogicLabs` or remove |
  | menu codes `APE/APH/APS/APU/APL/APC/APT` | `LPE/LPH/LPS/LPU/LPL/LPC/LPT` |

- All new skills live at `skills/<skill-name>/` (flat — no module subdirectory)
- Before `npm run release:major`: `git add` all new files explicitly (`postbump` uses `git add -u` only)
- **Source reference is now at 2.0.4** — copy from HEAD, not the 2.0.0 tag. All post-2.0.0 fixes are incorporated automatically when copying step files and assets from the reference.

## Post-2.0.0 Fixes Incorporated by Copying from HEAD

The following fixes landed after 2.0.0 and are **automatically picked up** by copying from REF HEAD. No extra steps required unless noted:

| Commit | Scope | What changed | Plan impact |
|---|---|---|---|
| `51d8cef` | step files (all) | Skill detection: `l3io-arch`/`l3io-sec` now check `_bmad/config.yaml` not `.claude/commands/`; user-level skills fall back to `~/.claude/commands` | Task 4 sed covers this — `ava-arch:` → `l3io-arch:` in grep patterns ✓ |
| `21cc22f` | util-cleanup SKILL.md + migrate-state.md | Health Check 2b detects migrate-state need; HC6 sequence gains `migrate-state` after `split-status`; legacy status normalization in migrate-state | Task 11 merge description already accounts for this ✓ |
| `ca202a8` | migrate-state.md | Epic-level normalization: deferred epic with ≥1 done sprint → in-progress; superseded epic → done (archived) | Covered by copy of migrate-state.md from HEAD ✓ |
| `6dbfc94` | migrate-state.md | Clear originals after backup; reorder load/normalize before write; Steps 2-6 restructured | Covered by copy of migrate-state.md from HEAD ✓ |
| `cc8f287` | migrate-state.md | Step 6 prompts user: move to `_bmad/migration-backup/` (default) / delete / keep legacy backups | Covered by copy of migrate-state.md from HEAD ✓ |
| `00f828e` | package-lock.json | brace-expansion DoS vulnerability patched (1.1.14 → 1.1.18) | **Requires `npm install` in Task 14 to update our own lockfile** |

---

### Task 1: pm-status.py v2.0.0

**Files:**
- Create: `skills/_shared/pm-status.py`
- Create: `skills/_shared/tests/test-pm-status.py`

**Interfaces:**
- Produces: `pm-status.py` with version marker `pm-status-version: 2.0.0` and subcommands: `set-status`, `set-actual`, `set-estimate`, `progress`, `verify`, `self-install`, `set-lock`, `clear-lock`, `check-lock`, `set-field`, `append-issue`, `archive-epic`

- [ ] **Step 1: Create directory**
```bash
mkdir -p skills/_shared/tests
```

- [ ] **Step 2: Copy pm-status.py from reference**
```bash
cp "$REF/skills/_shared/pm-status.py" skills/_shared/pm-status.py
```
No branding to strip — script is organization-neutral. Verify version marker exists on line 6:
```bash
grep "pm-status-version: 2.0.0" skills/_shared/pm-status.py
```

- [ ] **Step 3: Copy and adapt tests**
```bash
cp "$REF/skills/_shared/tests/test-pm-status.py" skills/_shared/tests/test-pm-status.py
```
The reference test file uses `key:` schema in its SAMPLE fixture. Verify:
```bash
grep "key:" skills/_shared/tests/test-pm-status.py | head -3
```

- [ ] **Step 4: Run tests**
```bash
cd skills/_shared && uv run --quiet --with pytest tests/test-pm-status.py -v
```
Expected: all tests PASS. If `uv` is unavailable: `python3 -m pytest tests/test-pm-status.py -v` (requires ruamel.yaml installed).

- [ ] **Step 5: Commit**
```bash
git add skills/_shared/pm-status.py skills/_shared/tests/test-pm-status.py
git commit -s -m "feat(infra): add pm-status.py v2.0.0 with lock, field, issue, and archive subcommands"
```

---

### Task 2: New Runtime Scripts

**Files:**
- Create: `skills/_shared/resolve_config.py`
- Create: `skills/_shared/memlog.py`

**Interfaces:**
- Produces: `resolve_config.py` CLI — `--project-root PATH [--key dotted.path]` → JSON to stdout
- Produces: `memlog.py` CLI — subcommands `init`, `append`, `set`

- [ ] **Step 1: Copy resolve_config.py**
```bash
cp "$REF/_bmad/scripts/resolve_config.py" skills/_shared/resolve_config.py
```
No branding to strip. Verify it exits cleanly with `--help`:
```bash
python3 skills/_shared/resolve_config.py --help
```

- [ ] **Step 2: Copy memlog.py**
```bash
cp "$REF/_bmad/scripts/memlog.py" skills/_shared/memlog.py
```

- [ ] **Step 3: Smoke-test memlog.py**
```bash
cd /tmp && mkdir -p memlog-test
python3 /mnt/source/git/l3io/bmad/bmad-extensions/skills/_shared/memlog.py \
  init --workspace /tmp/memlog-test --field "topic=test"
python3 /mnt/source/git/l3io/bmad/bmad-extensions/skills/_shared/memlog.py \
  append --workspace /tmp/memlog-test --text "first entry" --type note
cat /tmp/memlog-test/.memlog.md
rm -rf /tmp/memlog-test
```
Expected: file has frontmatter + one `- (note) first entry` line.

- [ ] **Step 4: Commit**
```bash
git add skills/_shared/resolve_config.py skills/_shared/memlog.py
git commit -s -m "feat(infra): add resolve_config.py and memlog.py runtime scripts"
```

---

### Task 3: skills/_shared/ Base Files

**Files:**
- Create: `skills/_shared/status-files.md` (updated for new `_bmad/state/` layout)
- Delete after later tasks: `src/_shared/` (removed in Task 14)

**Interfaces:**
- Produces: `status-files.md` documenting `_bmad/state/active/E{nnn}-status.yaml` layout, `sprint-status-planned.yaml`, `sprint-status-issues.yaml`, `sprint-status-archived.yaml`, and the `key:` node schema

- [ ] **Step 1: Copy updated status-files.md**
```bash
cp "$REF/skills/ava-pm-execute/references/status-files.md" skills/_shared/status-files.md
```
Apply global rename tokens (sed in-place):
```bash
sed -i 's/ava-pm/l3io-pm/g; s/ava-sec/l3io-sec/g; s/ava-util/l3io-util/g; s/ava-arch/l3io-arch/g; s/ava-/l3io-/g; s/Avanade/LiquidLogicLabs/g' skills/_shared/status-files.md
```

- [ ] **Step 2: Verify key schema documented**
```bash
grep "key:" skills/_shared/status-files.md | head -5
grep "_bmad/state" skills/_shared/status-files.md | head -3
```
Both greps must return results.

- [ ] **Step 3: Commit**
```bash
git add skills/_shared/status-files.md
git commit -s -m "feat(infra): add updated status-files.md for _bmad/state/ layout"
```

---

### Task 4: Shared Step Files

**Files:**
- Create: `skills/_shared/steps/shared/step-00-activate.md`
- Create: `skills/_shared/steps/shared/step-01-classify-work.md`
- Create: `skills/_shared/steps/shared/step-estimate.md`
- Create: `skills/_shared/steps/plan/step-02-readiness-check.md` through `step-06-plan-output.md`
- Create: `skills/_shared/steps/execute/step-02-scope-resolve.md` through `step-06-epic-closure.md`
- Create: `skills/_shared/steps/sprint/step-02-story-prep.md` through `step-04-sprint-closure.md`
- Create: `skills/_shared/steps/closure/sprint-closure.md` and `epic-closure.md`
- Create: `skills/_shared/steps/sync/step-02-detect-platform.md` through `step-04-resolve.md`

**Interfaces:**
- Produces: all shared step files that `sync-shared-scripts.mjs` will distribute to skills

- [ ] **Step 1: Create directory tree**
```bash
mkdir -p skills/_shared/steps/{shared,plan,execute,sprint,closure,sync}
```

- [ ] **Step 2: Copy all step files from reference**
```bash
cp "$REF/skills/_shared/steps/shared/"*.md skills/_shared/steps/shared/
cp "$REF/skills/_shared/steps/plan/"*.md   skills/_shared/steps/plan/
cp "$REF/skills/_shared/steps/execute/"*.md skills/_shared/steps/execute/
cp "$REF/skills/_shared/steps/sprint/"*.md  skills/_shared/steps/sprint/
cp "$REF/skills/_shared/steps/closure/"*.md skills/_shared/steps/closure/
cp "$REF/skills/_shared/steps/sync/"*.md    skills/_shared/steps/sync/
```

- [ ] **Step 3: Apply global rename tokens to all step files**
```bash
find skills/_shared/steps -name "*.md" -exec sed -i \
  's/ava-pm/l3io-pm/g; s/ava-sec/l3io-sec/g; s/ava-util/l3io-util/g; s/ava-arch/l3io-arch/g; s/ava-/l3io-/g; s/Avanade/LiquidLogicLabs/g' {} \;
```

- [ ] **Step 4: Verify key contracts in activate step**
```bash
grep "_bmad/state" skills/_shared/steps/shared/step-00-activate.md | head -3
grep "self-install" skills/_shared/steps/shared/step-00-activate.md
grep "check-lock" skills/_shared/steps/execute/step-02-scope-resolve.md
grep "parallel_factor\|0\.6" skills/_shared/steps/shared/step-estimate.md
```
All four greps must return results.

- [ ] **Step 5: Verify no Avanade references remain**
```bash
grep -r "Avanade\|ava-pm\|ava-sec\|ava-util\|ava-arch" skills/_shared/steps/ && echo "FAIL: references remain" || echo "PASS"
```

- [ ] **Step 6: Commit**
```bash
git add skills/_shared/steps/
git commit -s -m "feat(infra): add shared step files for all PM skill categories"
```

---

### Task 5: sync-shared-scripts.mjs Rewrite

**Files:**
- Modify: `scripts/sync-shared-scripts.mjs`

**Interfaces:**
- Produces: script that syncs `resolve_config.py`, `memlog.py`, `pm-status.py`, `test-pm-status.py`, all step files, and `status-files.md` into `skills/l3io-pm-execute`, `skills/l3io-pm-plan`, `skills/l3io-pm-sync`

- [ ] **Step 1: Replace sync-shared-scripts.mjs**

Write the full new content (adapt from `$REF/scripts/sync-shared-scripts.mjs`, applying global rename tokens and replacing the old `pmScriptDirs`/`allPmDirs` arrays with the new skill dirs):

```bash
cp "$REF/scripts/sync-shared-scripts.mjs" scripts/sync-shared-scripts.mjs
sed -i \
  's|skills.*ava-pm-plan|skills/l3io-pm-plan|g; s|skills.*ava-pm-execute|skills/l3io-pm-execute|g; s|skills.*ava-pm-sync|skills/l3io-pm-sync|g; s|ava-pm|l3io-pm|g; s|ava-|l3io-|g' \
  scripts/sync-shared-scripts.mjs
```

Then open `scripts/sync-shared-scripts.mjs` and:
1. Ensure `sharedDir` points to `path.join(repoRoot, "skills", "_shared")`
2. Ensure `newPmPlanDirs`, `newPmExecuteDirs`, `newPmSyncDirs` reference the `l3io-` directories
3. Add `resolve_config.py` and `memlog.py` to the `pmScriptFiles` array (alongside `pm-status.py`)
4. Clear `pmScriptDirs` and `allPmDirs` to `[]`

- [ ] **Step 2: Also update sync-bmad-versions.mjs**
```bash
cp "$REF/scripts/sync-bmad-versions.mjs" scripts/sync-bmad-versions.mjs
```
Open the file and verify the glob reads from `skills/*/module.yaml` (not `src/`). Apply any remaining rename tokens.

- [ ] **Step 3: Verify (skill dirs don't exist yet — should report nothing synced, not error)**
```bash
node scripts/sync-shared-scripts.mjs
```
Expected: "Shared-script sync complete (0 file(s) written)" — skills don't exist yet so all dirs are skipped via `skipMissing: true`.

- [ ] **Step 4: Commit**
```bash
git add scripts/sync-shared-scripts.mjs scripts/sync-bmad-versions.mjs
git commit -s -m "feat(infra): rewrite sync-shared-scripts.mjs for skills/ flat layout and new script manifest"
```

---

### Task 6: l3io-pm-execute Skill

**Files:**
- Create: `skills/l3io-pm-execute/SKILL.md`
- Create: `skills/l3io-pm-execute/customize.toml`
- Create: `skills/l3io-pm-execute/module.yaml`
- Create: `skills/l3io-pm-execute/assets/module-help.csv`
- Create: `skills/l3io-pm-execute/assets/module-setup.md`
- Create: `skills/l3io-pm-execute/scripts/merge-config.py`
- Create: `skills/l3io-pm-execute/scripts/merge-help-csv.py`
- Create: `skills/l3io-pm-execute/scripts/resolve_customization.py`

Note: `scripts/pm-status.py`, `scripts/tests/test-pm-status.py`, `references/status-files.md`, and all `steps/` files are populated by `sync-shared-scripts.mjs` in Task 13 — do not create them manually.

- [ ] **Step 1: Scaffold from reference**
```bash
mkdir -p skills/l3io-pm-execute/{assets,scripts,references}
cp "$REF/skills/ava-pm-execute/SKILL.md"          skills/l3io-pm-execute/SKILL.md
cp "$REF/skills/ava-pm-execute/customize.toml"    skills/l3io-pm-execute/customize.toml
cp "$REF/skills/ava-pm-execute/module.yaml"       skills/l3io-pm-execute/module.yaml
cp "$REF/skills/ava-pm-execute/assets/module-help.csv"   skills/l3io-pm-execute/assets/module-help.csv
cp "$REF/skills/ava-pm-execute/assets/module-setup.md"   skills/l3io-pm-execute/assets/module-setup.md
cp "$REF/skills/ava-arch-review/scripts/merge-config.py"      skills/l3io-pm-execute/scripts/merge-config.py
cp "$REF/skills/ava-arch-review/scripts/merge-help-csv.py"    skills/l3io-pm-execute/scripts/merge-help-csv.py
cp "$REF/skills/ava-sec-redteam/scripts/merge-config.py"      skills/l3io-pm-execute/scripts/merge-config.py 2>/dev/null || \
cp "$REF/skills/ava-util-cleanup/scripts/merge-config.py"     skills/l3io-pm-execute/scripts/merge-config.py
cp "$REF/skills/ava-util-cleanup/scripts/merge-help-csv.py"   skills/l3io-pm-execute/scripts/merge-help-csv.py
# resolve_customization.py — updated v2 version
cp "$REF/_bmad/scripts/resolve_customization.py"  skills/l3io-pm-execute/scripts/resolve_customization.py
```

- [ ] **Step 2: Apply global rename tokens to all files**
```bash
find skills/l3io-pm-execute -type f -exec sed -i \
  's/ava-pm/l3io-pm/g; s/ava-sec/l3io-sec/g; s/ava-util/l3io-util/g; s/ava-arch/l3io-arch/g; s/ava-/l3io-/g; s/Avanade PM/LiquidLogicLabs PM/g; s/Avanade/LiquidLogicLabs/g; s/APE/LPE/g' {} \;
```

- [ ] **Step 3: Verify SKILL.md**
```bash
grep "l3io-pm-execute" skills/l3io-pm-execute/SKILL.md
grep "headless" skills/l3io-pm-execute/SKILL.md
grep "step-00-activate" skills/l3io-pm-execute/SKILL.md
grep -i "avanade\|ava-" skills/l3io-pm-execute/SKILL.md && echo "FAIL" || echo "PASS"
```

- [ ] **Step 4: Verify customize.toml parses and has required keys**
```bash
python3 -c "
import tomllib
with open('skills/l3io-pm-execute/customize.toml','rb') as f: d=tomllib.load(f)
assert 'workflow' in d
assert 'max_parallel_subagents' in d['workflow']
assert 'epic_lock_ttl_minutes' in d['workflow']
print('PASS')
"
```

- [ ] **Step 5: Commit**
```bash
git add skills/l3io-pm-execute/
git commit -s -m "feat(l3io-pm): add l3io-pm-execute skill (merged sprint+epic execution)"
```

---

### Task 7: l3io-pm-plan Skill

**Files:**
- Create: `skills/l3io-pm-plan/` (same structure as execute, minus execute-only refs)

- [ ] **Step 1: Scaffold from reference**
```bash
mkdir -p skills/l3io-pm-plan/{assets,scripts,references}
for f in SKILL.md customize.toml module.yaml; do
  cp "$REF/skills/ava-pm-plan/$f" skills/l3io-pm-plan/$f
done
cp "$REF/skills/ava-pm-plan/assets/"* skills/l3io-pm-plan/assets/
cp "$REF/skills/ava-pm-execute/scripts/merge-config.py"     skills/l3io-pm-plan/scripts/
cp "$REF/skills/ava-pm-execute/scripts/merge-help-csv.py"   skills/l3io-pm-plan/scripts/
cp "$REF/_bmad/scripts/resolve_customization.py"            skills/l3io-pm-plan/scripts/
```

- [ ] **Step 2: Apply global rename tokens**
```bash
find skills/l3io-pm-plan -type f -exec sed -i \
  's/ava-pm/l3io-pm/g; s/ava-/l3io-/g; s/Avanade PM/LiquidLogicLabs PM/g; s/Avanade/LiquidLogicLabs/g; s/APH/LPH/g; s/APP/LPP/g' {} \;
```

- [ ] **Step 3: Verify customize.toml knobs**
```bash
python3 -c "
import tomllib
with open('skills/l3io-pm-plan/customize.toml','rb') as f: d=tomllib.load(f)
wf = d['workflow']
assert 'include_estimates' in wf
assert 'plan_output' in wf
print('PASS')
"
```

- [ ] **Step 4: Commit**
```bash
git add skills/l3io-pm-plan/
git commit -s -m "feat(l3io-pm): add l3io-pm-plan skill (renamed from plan-execution, steps architecture)"
```

---

### Task 8: l3io-pm-help Skill

**Files:**
- Create: `skills/l3io-pm-help/` (no steps/ or references/ — single-step skill)

- [ ] **Step 1: Scaffold from reference**
```bash
mkdir -p skills/l3io-pm-help/{assets,scripts}
for f in SKILL.md customize.toml module.yaml; do
  cp "$REF/skills/ava-pm-help/$f" skills/l3io-pm-help/$f
done
cp "$REF/skills/ava-pm-help/assets/"* skills/l3io-pm-help/assets/
cp "$REF/skills/ava-pm-execute/scripts/merge-config.py"   skills/l3io-pm-help/scripts/
cp "$REF/skills/ava-pm-execute/scripts/merge-help-csv.py" skills/l3io-pm-help/scripts/
cp "$REF/_bmad/scripts/resolve_customization.py"          skills/l3io-pm-help/scripts/
```

- [ ] **Step 2: Apply global rename tokens**
```bash
find skills/l3io-pm-help -type f -exec sed -i \
  's/ava-pm/l3io-pm/g; s/ava-/l3io-/g; s/Avanade PM/LiquidLogicLabs PM/g; s/Avanade/LiquidLogicLabs/g; s/APH/LPH/g' {} \;
```

- [ ] **Step 3: Verify decision table present**
```bash
grep "l3io-pm-plan\|l3io-pm-execute\|l3io-pm-sync" skills/l3io-pm-help/SKILL.md
grep "stale lock\|plan-output-meta" skills/l3io-pm-help/SKILL.md
```

- [ ] **Step 4: Commit**
```bash
git add skills/l3io-pm-help/
git commit -s -m "feat(l3io-pm): add l3io-pm-help skill (state snapshot + next-action recommendation)"
```

---

### Task 9: l3io-pm-sync Skill (GitHub-Only)

**Files:**
- Create: `skills/l3io-pm-sync/SKILL.md`, `customize.toml`, `module.yaml`
- Create: `skills/l3io-pm-sync/assets/module-help.csv`, `module-setup.md`, `sync-config-template.yaml`
- Create: `skills/l3io-pm-sync/scripts/detect-platform.py` (GitHub-only)
- Create: `skills/l3io-pm-sync/scripts/sync-state.py` (GitHub-only)
- Create: `skills/l3io-pm-sync/scripts/drift-report.py`
- Create: `skills/l3io-pm-sync/scripts/merge-config.py`, `merge-help-csv.py`, `resolve_customization.py`

**ADO rule:** Do not copy `ado-client.py`. In all other copied scripts, remove any code block inside `if platform == "azure-devops":` or `elif platform == "ado":` conditions — keep only the `github` branches.

- [ ] **Step 1: Scaffold static files from reference**
```bash
mkdir -p skills/l3io-pm-sync/{assets,scripts,steps/sync,steps/shared,references}
for f in SKILL.md customize.toml module.yaml; do
  cp "$REF/skills/ava-pm-sync/$f" skills/l3io-pm-sync/$f
done
cp "$REF/skills/ava-pm-sync/assets/module-help.csv"          skills/l3io-pm-sync/assets/
cp "$REF/skills/ava-pm-sync/assets/module-setup.md"          skills/l3io-pm-sync/assets/
cp "$REF/skills/ava-pm-sync/assets/sync-config-template.yaml" skills/l3io-pm-sync/assets/
cp "$REF/skills/ava-pm-execute/scripts/merge-config.py"       skills/l3io-pm-sync/scripts/
cp "$REF/skills/ava-pm-execute/scripts/merge-help-csv.py"     skills/l3io-pm-sync/scripts/
cp "$REF/_bmad/scripts/resolve_customization.py"              skills/l3io-pm-sync/scripts/
```

- [ ] **Step 2: Apply global rename tokens to static files**
```bash
find skills/l3io-pm-sync -type f ! -path "*/scripts/detect-platform.py" \
  ! -path "*/scripts/sync-state.py" ! -path "*/scripts/drift-report.py" \
  -exec sed -i \
  's/ava-pm/l3io-pm/g; s/ava-/l3io-/g; s/Avanade PM/LiquidLogicLabs PM/g; s/Avanade/LiquidLogicLabs/g; s/APS/LPS/g; s/APU/LPU/g; s/APL/LPL/g; s/APC/LPC/g; s/APT/LPT/g' {} \;
```

- [ ] **Step 3: Strip ADO from sync-config-template.yaml**

Open `skills/l3io-pm-sync/assets/sync-config-template.yaml` and remove the entire `azure_devops:` block (lines from `# Azure DevOps connection` through the closing `auth_method: pat` line). Also update the `platform:` comment to remove `| azure-devops`. The file should only document `platform: github`.

- [ ] **Step 4: Copy and strip ADO from Python scripts**
```bash
cp "$REF/skills/ava-pm-sync/scripts/detect-platform.py" skills/l3io-pm-sync/scripts/detect-platform.py
cp "$REF/skills/ava-pm-sync/scripts/sync-state.py"      skills/l3io-pm-sync/scripts/sync-state.py
cp "$REF/skills/ava-pm-sync/scripts/drift-report.py"    skills/l3io-pm-sync/scripts/drift-report.py
```

For each script: apply global rename tokens, then open the file and remove ADO-specific branches:
- In `detect-platform.py`: remove any ADO detection/auth code; if the script returns a platform string, ensure it only ever returns `"github"`; remove any `ADO_PAT` env var references
- In `sync-state.py`: remove any `if platform == "azure-devops"` / `elif "ado"` branches and all ADO API calls; keep only GitHub branches
- In `drift-report.py`: remove ADO-specific output formatting if any; keep GitHub-only output

Apply rename tokens to all three:
```bash
sed -i 's/ava-pm/l3io-pm/g; s/ava-/l3io-/g; s/Avanade/LiquidLogicLabs/g' \
  skills/l3io-pm-sync/scripts/detect-platform.py \
  skills/l3io-pm-sync/scripts/sync-state.py \
  skills/l3io-pm-sync/scripts/drift-report.py
```

- [ ] **Step 5: Verify no ADO references in scripts**
```bash
grep -i "azure.devops\|ADO_PAT\|AZURE_DEVOPS\|ado-client" skills/l3io-pm-sync/scripts/*.py \
  && echo "FAIL: ADO references remain" || echo "PASS"
```

- [ ] **Step 6: Verify SKILL.md**
```bash
grep "github" skills/l3io-pm-sync/SKILL.md
grep "step-02-detect-platform\|step-03-operations\|step-04-resolve" skills/l3io-pm-sync/SKILL.md
grep -i "avanade\|ava-\|azure.devops\|ADO" skills/l3io-pm-sync/SKILL.md && echo "FAIL" || echo "PASS"
```

- [ ] **Step 7: Commit**
```bash
git add skills/l3io-pm-sync/
git commit -s -m "feat(l3io-pm): add l3io-pm-sync skill (GitHub Issues bidirectional sync)"
```

---

### Task 10: l3io-sec-redteam Rename

**Files:**
- Create: `skills/l3io-sec-redteam/` (copy of `src/l3io-sec/l3io-sec-agent-redteam/`)
- Delete later: old directory (Task 14)

- [ ] **Step 1: Copy to new flat location**
```bash
mkdir -p skills/l3io-sec-redteam
cp -r src/l3io-sec/l3io-sec-agent-redteam/. skills/l3io-sec-redteam/
```

- [ ] **Step 2: Apply rename tokens**
```bash
find skills/l3io-sec-redteam -type f -exec sed -i \
  's/l3io-sec-agent-redteam/l3io-sec-redteam/g' {} \;
```
Also update the `customize.toml` to ensure root key is `[agent]` (not `[workflow]`):
```bash
grep "^\[agent\]" skills/l3io-sec-redteam/customize.toml || echo "WARN: check customize.toml root key"
```

- [ ] **Step 3: Update resolve_customization.py to v2**
```bash
cp "$REF/_bmad/scripts/resolve_customization.py" skills/l3io-sec-redteam/scripts/resolve_customization.py
```

- [ ] **Step 4: Verify**
```bash
grep "l3io-sec-redteam" skills/l3io-sec-redteam/SKILL.md
grep -r "l3io-sec-agent-redteam" skills/l3io-sec-redteam/ && echo "FAIL: old name remains" || echo "PASS"
```

- [ ] **Step 5: Commit**
```bash
git add skills/l3io-sec-redteam/
git commit -s -m "feat(l3io-sec): rename l3io-sec-agent-redteam → l3io-sec-redteam (flat layout)"
```

---

### Task 11: l3io-util-cleanup Migration

**Files:**
- Create: `skills/l3io-util-cleanup/` (copy from `src/l3io-util/l3io-util-cleanup/`, add `assets/migrate-state.md`)

- [ ] **Step 1: Copy to flat location**
```bash
mkdir -p skills/l3io-util-cleanup
cp -r src/l3io-util/l3io-util-cleanup/. skills/l3io-util-cleanup/
```

- [ ] **Step 2: Add migrate-state.md**
```bash
cp "$REF/skills/ava-util-cleanup/assets/migrate-state.md" skills/l3io-util-cleanup/assets/migrate-state.md
sed -i 's/ava-pm/l3io-pm/g; s/ava-util/l3io-util/g; s/ava-/l3io-/g; s/Avanade/LiquidLogicLabs/g' \
  skills/l3io-util-cleanup/assets/migrate-state.md
```

- [ ] **Step 3: Merge updated SKILL.md**

The existing `SKILL.md` has the old health check (7 checks). The reference has 9 checks including `migrate-state`. Rather than a full replace (which would overwrite l3io-specific content), do a targeted update:

Open `skills/l3io-util-cleanup/SKILL.md` and:
1. Add `migrate-state` to the keyword dispatch table (after `split-status`)
2. Update the Health Check section to add check 2b (`_bmad/state/active/` absent → flag `migrate-state`) and check 9 (`*.yaml.legacy` files → flag `clean-legacy`)
3. Add `migrate-state` to the HC6 fixed execution order (after `split-status`, before `reconcile-status`)
4. Add the `migrate-state` mode description: "Delegates entirely to `assets/migrate-state.md`"

Reference the updated SKILL.md at `$REF/skills/ava-util-cleanup/SKILL.md` for the exact wording, applying global rename tokens.

- [ ] **Step 4: Update resolve_customization.py to v2**
```bash
cp "$REF/_bmad/scripts/resolve_customization.py" skills/l3io-util-cleanup/scripts/resolve_customization.py
```

- [ ] **Step 5: Verify**
```bash
grep "migrate-state" skills/l3io-util-cleanup/SKILL.md
grep "migrate-state" skills/l3io-util-cleanup/assets/migrate-state.md | head -3
grep "_bmad/state" skills/l3io-util-cleanup/assets/migrate-state.md | head -3
grep -i "avanade\|ava-" skills/l3io-util-cleanup/assets/migrate-state.md && echo "FAIL" || echo "PASS"
```

- [ ] **Step 6: Commit**
```bash
git add skills/l3io-util-cleanup/
git commit -s -m "feat(l3io-util): add migrate-state mode and 9-check health check to util-cleanup"
```

---

### Task 12: l3io-arch-review Migration

**Files:**
- Create: `skills/l3io-arch-review/` (copy from `src/l3io-arch/l3io-arch-review/`, content unchanged)

- [ ] **Step 1: Copy to flat location**
```bash
mkdir -p skills/l3io-arch-review
cp -r src/l3io-arch/l3io-arch-review/. skills/l3io-arch-review/
```

- [ ] **Step 2: Update resolve_customization.py to v2**
```bash
cp "$REF/_bmad/scripts/resolve_customization.py" skills/l3io-arch-review/scripts/resolve_customization.py
```

- [ ] **Step 3: Verify**
```bash
ls skills/l3io-arch-review/references/
grep "l3io-arch-review" skills/l3io-arch-review/SKILL.md
```

- [ ] **Step 4: Commit**
```bash
git add skills/l3io-arch-review/
git commit -s -m "chore(l3io-arch): move l3io-arch-review to flat skills/ layout"
```

---

### Task 13: Build Pipeline, Symlinks, and CLAUDE.md

**Files:**
- Modify: `.claude/commands/` — remove old symlinks, add new ones
- Modify: `.claude-plugin/marketplace.json`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update .claude/commands/ symlinks**
```bash
cd .claude/commands
# Remove old
rm -f l3io-pm-sprint-execute.md l3io-pm-epic-execute.md l3io-pm-plan-execution.md l3io-sec-agent-redteam.md
# Add new (relative symlinks from .claude/commands/ → ../../skills/<skill>/SKILL.md)
ln -s ../../skills/l3io-pm-execute/SKILL.md l3io-pm-execute.md
ln -s ../../skills/l3io-pm-plan/SKILL.md l3io-pm-plan.md
ln -s ../../skills/l3io-pm-help/SKILL.md l3io-pm-help.md
ln -s ../../skills/l3io-pm-sync/SKILL.md l3io-pm-sync.md
ln -s ../../skills/l3io-sec-redteam/SKILL.md l3io-sec-redteam.md
ln -s ../../skills/l3io-util-cleanup/SKILL.md l3io-util-cleanup.md
ln -s ../../skills/l3io-arch-review/SKILL.md l3io-arch-review.md
cd ../..
```
Verify:
```bash
ls -la .claude/commands/
# All new symlinks must resolve:
for f in .claude/commands/*.md; do test -f "$f" && echo "OK: $f" || echo "BROKEN: $f"; done
```

- [ ] **Step 2: Update marketplace.json**

Replace the `plugins` array with the new flat skill list:
```json
{
  "name": "bmad-l3io-extensions",
  "owner": {
    "name": "Shawn Anderson",
    "email": "shawn@eye-catcher.com"
  },
  "license": "MIT",
  "homepage": "https://github.com/ravensorb/bmad-extensions",
  "repository": "https://github.com/ravensorb/bmad-extensions",
  "keywords": ["bmad", "liquidlogiclabs", "sprint-execution", "epic-execution", "red-team", "security", "sync"],
  "plugins": [
    {
      "name": "l3io-pm",
      "source": "./skills",
      "description": "PM orchestration for LiquidLogicLabs delivery teams — plan, execute, help, and sync.",
      "version": "2.0.0",
      "author": { "name": "Shawn Anderson", "email": "shawn@eye-catcher.com" },
      "skills": [
        "./skills/l3io-pm-execute",
        "./skills/l3io-pm-plan",
        "./skills/l3io-pm-help",
        "./skills/l3io-pm-sync"
      ]
    },
    {
      "name": "l3io-sec",
      "source": "./skills",
      "description": "Adversarial security analysis — five threat lenses with AI poisoning cross-cut.",
      "version": "2.0.0",
      "author": { "name": "Shawn Anderson", "email": "shawn@eye-catcher.com" },
      "skills": ["./skills/l3io-sec-redteam"]
    },
    {
      "name": "l3io-util",
      "source": "./skills",
      "description": "Utility skills for BMad projects — artifact organization and state migration.",
      "version": "2.0.0",
      "author": { "name": "Shawn Anderson", "email": "shawn@eye-catcher.com" },
      "skills": ["./skills/l3io-util-cleanup"]
    },
    {
      "name": "l3io-arch",
      "source": "./skills",
      "description": "Engineering-standards architecture guardrails — universal best practices plus per-stack overlays.",
      "version": "2.0.0",
      "author": { "name": "Shawn Anderson", "email": "shawn@eye-catcher.com" },
      "skills": ["./skills/l3io-arch-review"]
    }
  ],
  "dependencies": {
    "bmad-module": "bmm",
    "required-skills": [
      "bmad-create-story", "bmad-dev-story", "bmad-code-review",
      "bmad-qa-generate-e2e-tests", "bmad-retrospective", "bmad-review-adversarial-general"
    ],
    "optional-skills": ["bmad-ux-review", "l3io-arch-review", "bmad-testarch-atdd"]
  }
}
```
Validate JSON: `python3 -c "import json; json.load(open('.claude-plugin/marketplace.json')); print('PASS')"`

- [ ] **Step 3: Update CLAUDE.md**

Open `CLAUDE.md` and update:
1. **Module Layout** section: change `src/` → `skills/`, remove the two-level nesting description, update the directory tree to show flat `skills/<skill>/` layout
2. **Skill Directory table**: replace old skill rows with new inventory (execute, plan, help, sync, sec-redteam, util-cleanup, arch-review)
3. **State files** section: update to `_bmad/state/active/E{nnn}-status.yaml` layout, remove old `sprint-status-active.yaml` → `sprint-status.yaml` description, update the three-file split to the four-file layout
4. **Shared Files** table: update canonical sources to `skills/_shared/`, add `resolve_config.py` and `memlog.py`, add step files sync group

- [ ] **Step 4: Commit**
```bash
git add .claude/commands/ .claude-plugin/marketplace.json CLAUDE.md
git commit -s -m "feat(infra): update commands symlinks, marketplace.json, and CLAUDE.md for v2 layout"
```

---

### Task 14: Run Sync, Remove src/, and Release

**Files:**
- Delete: `src/` (entire directory)
- Verify: all sync groups pass

- [ ] **Step 1: Run sync to populate step files into skills**
```bash
npm run sync:scripts
```
Expected output lists synced files for `l3io-pm-execute`, `l3io-pm-plan`, `l3io-pm-sync`. No errors.

- [ ] **Step 2: Verify sync is clean**
```bash
npm run check:scripts
```
Expected: "Shared-script payload copies are in sync."

- [ ] **Step 3: Spot-check a synced skill**
```bash
ls skills/l3io-pm-execute/steps/shared/
ls skills/l3io-pm-execute/scripts/pm-status.py
ls skills/l3io-pm-execute/references/status-files.md
```
All must exist.

- [ ] **Step 4: Run pm-status tests against the synced copy**
```bash
cd skills/l3io-pm-execute && uv run --quiet --with pytest scripts/tests/test-pm-status.py -v
```
All tests must PASS.

- [ ] **Step 5: Stage all new skills (postbump uses git add -u)**
```bash
git add skills/
```

- [ ] **Step 6: Remove src/**
```bash
git rm -r src/
git commit -s -m "chore: remove src/ — all skills migrated to flat skills/ layout"
```

- [ ] **Step 7: Final no-Avanade check**
```bash
grep -r "Avanade\|ava-pm\|ava-sec\|ava-util\|ava-arch\|ava-" skills/ .claude-plugin/ CLAUDE.md \
  && echo "FAIL: external references remain" || echo "PASS"
```

- [ ] **Step 8: Fix brace-expansion vulnerability (npm install)**
```bash
npm install
git add package-lock.json
git commit -s -m "fix(infra): patch brace-expansion DoS vulnerability in lockfile"
```
Verify: `npm audit` should report no brace-expansion advisory.

- [ ] **Step 9: Release**
```bash
npm run release:major
```
Expected: creates `2.0.0` git tag, updates `CHANGELOG.md`, syncs version into all `module.yaml` files and `marketplace.json` via `postbump`.

- [ ] **Step 10: Verify release**
```bash
git log --oneline -3
node -e "const p=require('./.claude-plugin/marketplace.json'); console.log(p.plugins[0].version)"
grep "module_version" skills/l3io-pm-execute/module.yaml
```
All should show `2.0.0`.
