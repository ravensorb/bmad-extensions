#!/usr/bin/env node
// pm-status.py's version must equal the package release version, in both places it is written.
//
// Why this exists: self-install places one runtime copy per project and reports the version
// it finds. That number used to be maintained by hand, on its own release line, and a
// hand-maintained invariant drifts. It did, twice -- ten commits changed the script under
// 2.3.0, and after the bump to 2.4.0 another changed it again under 2.4.0. Projects that
// installed at either moment kept a stale copy while self-install reported a clean skip,
// because both copies agreed on the number they printed. One sat 920 lines behind, missing
// a Critical fix.
//
// Two changes retired that failure. self-install now compares content, so a stale copy heals
// itself. And the script's version is no longer its own: postbump writes it from
// package.json, alongside marketplace.json and every module.yaml. Nobody has to remember it.
//
// This check asserts the invariant that makes both true:
//
//   marker == PM_STATUS_VERSION == package.json version
//
// It holds at every point in the cycle, not just at release -- mid-cycle all three sit at the
// last released version -- so it is checkable on any commit, which the previous tag-diff
// heuristic was not.
//
// Usage: node scripts/check-pm-status-version.mjs [-v]
import fs from "node:fs";

const PM = "skills/_shared/pm-status.py";
const PKG = "package.json";
const verbose = process.argv.includes("-v");
const failures = [];

if (!fs.existsSync(PM)) {
  console.error(`✗ ${PM} not found`);
  process.exit(1);
}
const text = fs.readFileSync(PM, "utf8");
const marker = (text.match(/^#\s*pm-status-version:\s*([0-9.]+)/m) || [])[1];
const konst = (text.match(/^PM_STATUS_VERSION\s*=\s*"([0-9.]+)"/m) || [])[1];
const pkg = JSON.parse(fs.readFileSync(PKG, "utf8")).version;

if (!marker) failures.push(`${PM}: no "# pm-status-version:" marker found`);
if (!konst) failures.push(`${PM}: no PM_STATUS_VERSION constant found`);

if (marker && konst && marker !== konst) {
  failures.push(
    `${PM}: marker says ${marker} but PM_STATUS_VERSION says ${konst}\n` +
      `      self-install reads the marker off a copy on disk and compares it against the\n` +
      `      constant in the running script, so these disagreeing makes it compare a version\n` +
      `      against a different version.`,
  );
}

if (marker && konst && marker === konst && marker !== pkg) {
  failures.push(
    `${PM}: version is ${marker} but ${PKG} says ${pkg}\n` +
      `      These share one release line. postbump writes pm-status.py's version from\n` +
      `      package.json, so a mismatch means either the script was hand-edited or a release\n` +
      `      did not complete. Do not hand-edit the version: run a release, or\n` +
      `      "node scripts/sync-bmad-versions.mjs" to bring it back in line.\n` +
      `      NEVER set it backwards -- self-install refuses to overwrite a strictly newer\n` +
      `      installed copy, so a lowered version strands every project already on the higher one.`,
  );
}

if (failures.length) {
  console.error(`\n${failures.length} pm-status.py version problem(s):\n`);
  for (const f of failures) console.error(`  ✗ ${f}\n`);
  process.exit(1);
}
if (verbose) console.log(`  pm-status-version: ${marker} == PM_STATUS_VERSION == ${PKG}`);
console.log(`pm-status.py version check passed: ${marker} in all three places.`);
