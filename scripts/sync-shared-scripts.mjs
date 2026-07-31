#!/usr/bin/env node
// Sync the single canonical shared runtime script (and its tests) from
// src/l3io-pm/_shared/ into each PM skill's scripts/ directory as install payload.
//
// Why: pm-status.py is a *shared runtime utility* (like _bmad/scripts/resolve_customization.py),
// but BMad installs skills independently, so each PM skill must ship a copy to install from.
// The authored source of truth is src/l3io-pm/_shared/; the per-skill copies are GENERATED —
// never hand-edit them. At module setup each copy self-installs to
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
const sharedDir = path.join(repoRoot, "src", "l3io-pm", "_shared");

// source -> relative destination under each skill dir
const files = [
  { src: path.join(sharedDir, "pm-status.py"), rel: path.join("scripts", "pm-status.py") },
  { src: path.join(sharedDir, "tests", "test-pm-status.py"), rel: path.join("scripts", "tests", "test-pm-status.py") },
];

const skillDirs = [
  path.join(repoRoot, "src", "l3io-pm", "l3io-pm-sprint-execute"),
  path.join(repoRoot, "src", "l3io-pm", "l3io-pm-epic-execute"),
];

let drift = 0;
let written = 0;

for (const { src, rel } of files) {
  if (!fs.existsSync(src)) throw new Error(`Missing canonical source: ${src}`);
  const content = fs.readFileSync(src);
  const mode = fs.statSync(src).mode;
  for (const skillDir of skillDirs) {
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

if (check) {
  if (drift > 0) {
    console.error(`\n${drift} shared-script copy/copies out of sync — run: npm run sync:scripts`);
    process.exit(1);
  }
  console.log("Shared-script payload copies are in sync with src/l3io-pm/_shared/.");
} else {
  console.log(`Shared-script sync complete (${written} file(s) written).`);
}
