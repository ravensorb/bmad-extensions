#!/usr/bin/env node
// Refuse to ship a changed pm-status.py under an unchanged version marker.
//
// Why: self-install places one runtime copy per project and has to decide whether an
// installed copy is current. The marker is hand-maintained, so it drifts -- and it did,
// twice. Ten commits changed the script under 2.3.0; after the bump to 2.4.0 another
// changed it again under 2.4.0. Projects that installed at either moment kept a stale
// copy, and because both copies agreed on the number they printed, nothing looked wrong.
// One sat 920 lines behind, missing a Critical fix.
//
// self-install now compares content, so a stale copy self-heals. That fixes the symptom.
// This check fixes the cause: a version number that lies is still a defect, because it is
// the only thing that can express a genuine downgrade, and every consumer reads it.
//
//   1. the top-of-file marker and PM_STATUS_VERSION agree with each other
//   2. if the script's content changed since the last release tag, the version moved too
//
// Usage: node scripts/check-pm-status-version.mjs [-v]
import fs from "node:fs";
import { execFileSync } from "node:child_process";

const PM = "skills/_shared/pm-status.py";
const verbose = process.argv.includes("-v");
const failures = [];

const markerOf = (text) => (text.match(/^#\s*pm-status-version:\s*([0-9.]+)/m) || [])[1];
const constOf = (text) => (text.match(/^PM_STATUS_VERSION\s*=\s*"([0-9.]+)"/m) || [])[1];

const git = (args) => execFileSync("git", args, { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] });

if (!fs.existsSync(PM)) {
  console.error(`✗ ${PM} not found`);
  process.exit(1);
}
const now = fs.readFileSync(PM, "utf8");
const marker = markerOf(now);
const konst = constOf(now);

// 1. The two declarations must agree. Today only a code comment asks them to.
if (!marker) failures.push(`${PM}: no "# pm-status-version:" marker found`);
if (!konst) failures.push(`${PM}: no PM_STATUS_VERSION constant found`);
if (marker && konst && marker !== konst) {
  failures.push(
    `${PM}: marker says ${marker} but PM_STATUS_VERSION says ${konst}\n` +
      `      self-install reads the marker off a copy on disk and compares it against the\n` +
      `      constant in the running script, so these disagreeing makes it compare a version\n` +
      `      against a different version. Set both to the same value.`,
  );
}

// 2. Content changed since the last release => the version must have moved.
let tag = null;
try {
  tag = git(["describe", "--tags", "--abbrev=0"]).trim();
} catch {
  if (verbose) console.log("  pm-status-version: no release tag yet — content check skipped");
}
if (tag) {
  let old = null;
  try {
    old = git(["show", `${tag}:${PM}`]);
  } catch {
    if (verbose) console.log(`  pm-status-version: ${PM} absent at ${tag} — content check skipped`);
  }
  if (old !== null) {
    const changed = old !== now;
    const oldMarker = markerOf(old);
    if (changed && oldMarker === marker) {
      failures.push(
        `${PM}: content changed since ${tag} but the version is still ${marker}\n` +
          `      Every project installs one runtime copy of this script and self-install\n` +
          `      reports the version it sees. Shipping different bytes under the same number\n` +
          `      makes that report a lie, and removes the only signal a downgrade can use.\n` +
          `      Bump the marker AND PM_STATUS_VERSION, then re-run npm run sync:scripts.`,
      );
    }
    if (verbose) {
      console.log(
        `  pm-status-version: ${marker} (was ${oldMarker} at ${tag}) — ` +
          `content ${changed ? "changed" : "unchanged"}`,
      );
    }
  }
}

if (failures.length) {
  console.error(`\n${failures.length} pm-status.py version problem(s):\n`);
  for (const f of failures) console.error(`  ✗ ${f}\n`);
  process.exit(1);
}
console.log("pm-status.py version check passed: marker and constant agree, version tracks content.");
