#!/usr/bin/env node
// Sync shared files from src/_shared/ into each PM skill's payload directories.
//
// Why: pm-status.py is a *shared runtime utility* (like _bmad/scripts/resolve_customization.py),
// but BMad installs skills independently, so each PM skill must ship a copy to install from.
// status-files.md is the canonical split-state contract shared across all three PM skills.
// The authored source of truth is src/_shared/; the per-skill copies are GENERATED —
// never hand-edit them. At module setup each script copy self-installs to
// {project-root}/_bmad/scripts/pm-status.py, so there is exactly one runtime copy per project.
//
// Usage:
//   node scripts/sync-shared-scripts.mjs           # write the per-skill payload copies
//   node scripts/sync-shared-scripts.mjs --check    # verify copies match source; nonzero exit on drift (CI)
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

const repoRoot = process.cwd();
const check = process.argv.includes("--check");
const sharedDir = path.join(repoRoot, "src", "_shared");

// Scripts synced to sprint-execute and epic-execute only (plan-execution has no runtime scripts)
const pmScriptFiles = [
  { src: path.join(sharedDir, "pm-status.py"), rel: path.join("scripts", "pm-status.py") },
  { src: path.join(sharedDir, "tests", "test-pm-status.py"), rel: path.join("scripts", "tests", "test-pm-status.py") },
];

// Reference docs synced to all three PM skills
const pmRefFiles = [
  { src: path.join(sharedDir, "status-files.md"), rel: path.join("references", "status-files.md") },
];

const pmScriptDirs = [
  path.join(repoRoot, "src", "l3io-pm", "l3io-pm-sprint-execute"),
  path.join(repoRoot, "src", "l3io-pm", "l3io-pm-epic-execute"),
];

const allPmDirs = [
  path.join(repoRoot, "src", "l3io-pm", "l3io-pm-sprint-execute"),
  path.join(repoRoot, "src", "l3io-pm", "l3io-pm-epic-execute"),
  path.join(repoRoot, "src", "l3io-pm", "l3io-pm-plan-execution"),
];

const syncGroups = [
  { files: pmScriptFiles, dirs: pmScriptDirs },
  { files: pmRefFiles,   dirs: allPmDirs },
];

let drift = 0;
let written = 0;

for (const { files, dirs } of syncGroups) {
  for (const { src, rel } of files) {
    if (!fs.existsSync(src)) throw new Error(`Missing canonical source: ${src}`);
    const content = fs.readFileSync(src);
    const mode = fs.statSync(src).mode;
    for (const skillDir of dirs) {
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
    console.error(`\n${drift} shared file copy/copies out of sync — run: npm run sync:scripts`);
    process.exit(1);
  }
  console.log("Shared file payload copies are in sync with src/_shared/.");
} else {
  console.log(`Shared file sync complete (${written} file(s) written).`);
}
