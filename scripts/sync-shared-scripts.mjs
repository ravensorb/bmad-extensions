#!/usr/bin/env node
// Sync canonical shared files from skills/_shared/ into each PM skill's directory.
//
// Why: BMad installs skills independently, so each skill must ship its own copy of any
// shared file. The authored source of truth is skills/_shared/; the per-skill copies are
// GENERATED — never hand-edit them.
//
// Shared files:
//   pm-status.py / test-pm-status.py → scripts/ in PM execution skills
//   status-files.md / metrics-contract.md → references/ in PM skills
//   write-module-config.py → scripts/, config-resolution.md → references/,
//   module-setup.md → assets/ in EVERY l3io skill
//
// Not shared, deliberately: resolve_config.py, resolve_customization.py and memlog.py are
// installed by BMad core at {project-root}/_bmad/scripts/ and are never bundled by a skill.
// Vendoring them shipped a stale duplicate of a core script that nothing invoked.
//
// Usage:
//   node scripts/sync-shared-scripts.mjs           # write the per-skill payload copies
//   node scripts/sync-shared-scripts.mjs --check    # verify copies match source; nonzero exit on drift (CI)
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

const repoRoot = process.cwd();
const check = process.argv.includes("--check");
const sharedDir = path.join(repoRoot, "skills", "_shared");

// source -> relative destination under each skill dir (pmScriptDirs) or all PM skill dirs (allPmDirs)
const pmScriptFiles = [
  { src: path.join(sharedDir, "pm-status.py"), rel: path.join("scripts", "pm-status.py") },
  { src: path.join(sharedDir, "tests", "test-pm-status.py"), rel: path.join("scripts", "tests", "test-pm-status.py") },
];

// Files every l3io skill ships, regardless of module: the config contract, the setup
// procedure that points at it, and the script that setup runs.
const allSkillFiles = [
  { src: path.join(sharedDir, "write-module-config.py"), rel: path.join("scripts", "write-module-config.py") },
  { src: path.join(sharedDir, "tests", "test-write-module-config.py"), rel: path.join("scripts", "tests", "test-write-module-config.py") },
  { src: path.join(sharedDir, "config-resolution.md"), rel: path.join("references", "config-resolution.md") },
  { src: path.join(sharedDir, "module-setup.md"), rel: path.join("assets", "module-setup.md") },
];

const pmRefFiles = [
  { src: path.join(sharedDir, "status-files.md"), rel: path.join("references", "status-files.md") },
  { src: path.join(sharedDir, "metrics-contract.md"), rel: path.join("references", "metrics-contract.md") },
  // The calibration model, split out of metrics-contract.md: pm-status.py performs all of it
  // and a normal run never reads it, so it must not sit in the contract a capture agent loads.
  { src: path.join(sharedDir, "calibration-model.md"), rel: path.join("references", "calibration-model.md") },
];

// PM skills that ship pm-status.py as an install payload (execution skills only)
// Legacy slots kept for backward compat shape; new skills use newPmPlanDirs / newPmExecuteDirs groups below.
const pmScriptDirs = [];

// All PM skills that reference status-files.md
// Legacy slots kept for backward compat shape; new skills use newPmPlanDirs / newPmExecuteDirs / newPmSyncDirs groups below.
const allPmDirs = [];

// New skill directories (created in Tasks 5-9)
const newPmPlanDirs = [
  path.join(repoRoot, "skills", "l3io-pm-plan"),
];
const newPmExecuteDirs = [
  path.join(repoRoot, "skills", "l3io-pm-execute"),
];
const newPmSyncDirs = [
  path.join(repoRoot, "skills", "l3io-pm-sync"),
];

// Every skill in the package — the four l3io modules' skills all resolve config and all
// carry the same setup procedure.
const allSkillDirs = [
  "l3io-arch-review",
  "l3io-pm-execute",
  "l3io-pm-help",
  "l3io-pm-plan",
  "l3io-pm-sync",
  "l3io-sec-redteam",
  "l3io-util-doctor",
  // NOTE: skills/l3io-util-cleanup is deliberately absent. It is a deprecated forwarder that
  // resolves no config and reads no state — it prints a rename notice and delegates to
  // l3io-util-doctor. Syncing the shared payload into it would bundle a config-resolution
  // reference and write-module-config.py that nothing there invokes, which is the same dead
  // payload this package removed when it stopped vendoring BMad core scripts.
].map((name) => path.join(repoRoot, "skills", name));

// Shared step files: source path → relative dest path within each skill's steps/ dir
const sharedStepFiles = [
  {
    src: path.join(sharedDir, "steps", "shared", "step-00-activate.md"),
    rel: path.join("steps", "shared", "step-00-activate.md"),
  },
  {
    // The digest, split out of step-00-activate.md §8: dispatched subagents load it alone,
    // inheriting the bootstrap in sections 1-7 rather than re-running it per dispatch.
    src: path.join(sharedDir, "steps", "shared", "step-00-digest.md"),
    rel: path.join("steps", "shared", "step-00-digest.md"),
  },
  {
    src: path.join(sharedDir, "steps", "shared", "step-01-classify-work.md"),
    rel: path.join("steps", "shared", "step-01-classify-work.md"),
  },
  {
    src: path.join(sharedDir, "steps", "shared", "step-estimate.md"),
    rel: path.join("steps", "shared", "step-estimate.md"),
  },
];

const planStepFiles = [
  { src: path.join(sharedDir, "steps", "plan", "step-02-readiness-check.md"), rel: path.join("steps", "plan", "step-02-readiness-check.md") },
  { src: path.join(sharedDir, "steps", "plan", "step-03-story-elaboration.md"), rel: path.join("steps", "plan", "step-03-story-elaboration.md") },
  { src: path.join(sharedDir, "steps", "plan", "step-04-load-state.md"), rel: path.join("steps", "plan", "step-04-load-state.md") },
  { src: path.join(sharedDir, "steps", "plan", "step-05-dependency-graph.md"), rel: path.join("steps", "plan", "step-05-dependency-graph.md") },
  { src: path.join(sharedDir, "steps", "plan", "step-06-plan-output.md"), rel: path.join("steps", "plan", "step-06-plan-output.md") },
];

const executeStepFiles = [
  { src: path.join(sharedDir, "steps", "execute", "step-02-scope-resolve.md"), rel: path.join("steps", "execute", "step-02-scope-resolve.md") },
  { src: path.join(sharedDir, "steps", "execute", "step-03-load-plan.md"), rel: path.join("steps", "execute", "step-03-load-plan.md") },
  { src: path.join(sharedDir, "steps", "execute", "step-04-arch-gate.md"), rel: path.join("steps", "execute", "step-04-arch-gate.md") },
  { src: path.join(sharedDir, "steps", "execute", "step-05-epic-loop.md"), rel: path.join("steps", "execute", "step-05-epic-loop.md") },
  { src: path.join(sharedDir, "steps", "execute", "step-06-epic-closure.md"), rel: path.join("steps", "execute", "step-06-epic-closure.md") },
  { src: path.join(sharedDir, "steps", "sprint", "step-02-story-prep.md"), rel: path.join("steps", "sprint", "step-02-story-prep.md") },
  { src: path.join(sharedDir, "steps", "sprint", "step-03-dev-loop.md"), rel: path.join("steps", "sprint", "step-03-dev-loop.md") },
  { src: path.join(sharedDir, "steps", "sprint", "step-04-sprint-closure.md"), rel: path.join("steps", "sprint", "step-04-sprint-closure.md") },
  { src: path.join(sharedDir, "steps", "closure", "sprint-closure.md"), rel: path.join("steps", "closure", "sprint-closure.md") },
  { src: path.join(sharedDir, "steps", "closure", "epic-closure.md"), rel: path.join("steps", "closure", "epic-closure.md") },
];

const syncStepFiles = [
  { src: path.join(sharedDir, "steps", "sync", "step-02-detect-platform.md"), rel: path.join("steps", "sync", "step-02-detect-platform.md") },
  { src: path.join(sharedDir, "steps", "sync", "step-03-operations.md"),       rel: path.join("steps", "sync", "step-03-operations.md") },
  { src: path.join(sharedDir, "steps", "sync", "step-04-resolve.md"),           rel: path.join("steps", "sync", "step-04-resolve.md") },
];

// Combined sync manifest: [{files, dirs, skipMissing}]
const syncGroups = [
  // Config contract + setup procedure + its writer script into every skill
  { files: allSkillFiles, dirs: allSkillDirs },
  // Legacy: pm-status.py into old execution skills (kept for backward compat shape; skill dirs created in Tasks 5-9)
  { files: pmScriptFiles, dirs: pmScriptDirs },
  { files: pmRefFiles, dirs: allPmDirs },
  // New: shared steps into new skills (dirs only created in Tasks 5-9; skip missing dirs)
  { files: sharedStepFiles, dirs: [...newPmPlanDirs, ...newPmExecuteDirs, ...newPmSyncDirs], skipMissing: true },
  { files: planStepFiles, dirs: newPmPlanDirs, skipMissing: true },
  { files: executeStepFiles, dirs: newPmExecuteDirs, skipMissing: true },
  { files: syncStepFiles, dirs: newPmSyncDirs, skipMissing: true },
  // pm-status.py into new skills that ship it (plan + execute)
  { files: pmScriptFiles, dirs: [...newPmPlanDirs, ...newPmExecuteDirs], skipMissing: true },
  // pm-status.py and status-files.md into l3io-pm-sync
  { files: pmScriptFiles, dirs: newPmSyncDirs, skipMissing: true },
  // status-files.md into new PM skills (plan + execute)
  { files: pmRefFiles, dirs: [...newPmPlanDirs, ...newPmExecuteDirs], skipMissing: true },
  { files: pmRefFiles, dirs: newPmSyncDirs, skipMissing: true },
];

let drift = 0;
let written = 0;

for (const { files, dirs, skipMissing } of syncGroups) {
  for (const { src, rel } of files) {
    if (!fs.existsSync(src)) {
      if (skipMissing) continue;  // step files not created yet — skip
      throw new Error(`Missing canonical source: ${src}`);
    }
    const content = fs.readFileSync(src);
    const mode = fs.statSync(src).mode;
    for (const skillDir of dirs) {
      if (skipMissing && !fs.existsSync(skillDir)) continue;  // skill not created yet
      const dest = path.join(skillDir, rel);
      const exists = fs.existsSync(dest);
      const same = exists && fs.readFileSync(dest).equals(content);
      if (check) {
        if (!same) {
          drift += 1;
          console.error(`DRIFT: ${path.relative(repoRoot, dest)} does not match ${path.relative(repoRoot, src)}`);
        }
        continue;
      }
      if (same) continue;
      fs.mkdirSync(path.dirname(dest), { recursive: true });
      fs.writeFileSync(dest, content);
      fs.chmodSync(dest, mode);
      execFileSync("git", ["add", dest], { cwd: repoRoot, stdio: "ignore" });
      written += 1;
      console.log(`Synced ${path.relative(repoRoot, dest)}`);
    }
  }
}

if (check) {
  if (drift > 0) {
    console.error(`\n${drift} shared-script copy/copies out of sync — run: npm run sync:scripts`);
    process.exit(1);
  }
  console.log("Shared-script payload copies are in sync with skills/_shared/.");
} else {
  console.log(`Shared-script sync complete (${written} file(s) written).`);
}
