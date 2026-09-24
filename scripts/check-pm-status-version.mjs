#!/usr/bin/env node
// pm-status.py's version, and every module's module_version, must equal the package release
// version.
//
// Why pm-status.py's part exists: self-install places one runtime copy per project and
// reports the version it finds. That number used to be maintained by hand, on its own release
// line, and a hand-maintained invariant drifts. It did, twice -- ten commits changed the
// script under 2.3.0, and after the bump to 2.4.0 another changed it again under 2.4.0.
// Projects that installed at either moment kept a stale copy while self-install reported a
// clean skip, because both copies agreed on the number they printed. One sat 920 lines
// behind, missing a Critical fix.
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
// Why the module_version part exists: Task 7 relocated module.yaml under assets/ and, in the
// same change, retired check:docs check 16 (module-yaml-agreement) -- the only place that used
// to READ module_version. sync-bmad-versions.mjs's postbump loop is now the field's only
// consumer; nothing verifies it wrote correctly. A writer with no reader can drift silently:
// the loop could stop finding files (it did, briefly, mid-relocation, until fixed to look
// under assets/) and log a success-shaped line ("No module.yaml files needed version update")
// forever. Scope is derived by walking skills/ for every module home
// (assets/module.yaml, or a not-yet-migrated skill-root module.yaml) -- never a hand-kept
// list of module codes.
//
// Usage: node scripts/check-pm-status-version.mjs [-v]
import fs from "node:fs";
import path from "node:path";

// CHECK_VERSION_ROOT points the checker at another tree -- scripts/tests/check-pm-status-version.test.mjs
// runs it against fixtures built from an empty skills/ tree.
const repoRoot = process.env.CHECK_VERSION_ROOT ? path.resolve(process.env.CHECK_VERSION_ROOT) : process.cwd();
const verbose = process.argv.includes("-v");
const failures = [];

const read = (p) => fs.readFileSync(path.join(repoRoot, p), "utf8");
const exists = (p) => fs.existsSync(path.join(repoRoot, p));

const PM = "skills/_shared/pm-status.py";
const PKG = "package.json";

if (!exists(PM)) {
  console.error(`✗ ${PM} not found`);
  process.exit(1);
}
const text = read(PM);
const marker = (text.match(/^#\s*pm-status-version:\s*([0-9.]+)/m) || [])[1];
const konst = (text.match(/^PM_STATUS_VERSION\s*=\s*"([0-9.]+)"/m) || [])[1];
const pkg = JSON.parse(read(PKG)).version;

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

// Every module home's module_version must equal package.json's version. A module home is
// assets/module.yaml, falling back to a skill-root module.yaml -- read both so this survives a
// tree where only one of the two exists instead of silently checking zero modules. A standalone
// module home carries BOTH (check:module rule 1: the root copy is what BMad's installer
// discovers), and check:module requires them byte-identical, so checking the first found here
// is sufficient: drift between them is a check:module failure, not a silent pass.
const moduleHomes = [];
if (exists("skills")) {
  for (const entry of fs.readdirSync(path.join(repoRoot, "skills"), { withFileTypes: true })) {
    if (!entry.isDirectory() || entry.name === "_shared") continue;
    for (const rel of [`skills/${entry.name}/assets/module.yaml`, `skills/${entry.name}/module.yaml`]) {
      if (exists(rel)) { moduleHomes.push(rel); break; }
    }
  }
}

let moduleChecked = 0;
for (const rel of moduleHomes) {
  const m = read(rel).match(/^module_version:\s*(\S+)/m);
  if (!m) {
    failures.push(`${rel}: no "module_version:" field found`);
    continue;
  }
  moduleChecked += 1;
  if (m[1] !== pkg) {
    failures.push(
      `${rel}: module_version is ${m[1]} but ${PKG} says ${pkg}\n` +
        `      postbump writes every module home's module_version from package.json (see\n` +
        `      sync-bmad-versions.mjs); a mismatch means a release did not complete or the\n` +
        `      file was hand-edited. Do not hand-edit module_version: run a release, or\n` +
        `      "node scripts/sync-bmad-versions.mjs" to bring it back in line.`,
    );
  }
}

if (failures.length) {
  console.error(`\n${failures.length} version problem(s):\n`);
  for (const f of failures) console.error(`  ✗ ${f}\n`);
  process.exit(1);
}
if (verbose) {
  console.log(`  pm-status-version: ${marker} == PM_STATUS_VERSION == ${PKG}`);
  console.log(`  module-version: ${moduleChecked} module home(s) at ${pkg}`);
}
console.log(
  `pm-status.py version check passed: ${marker} in all three places; ` +
    `${moduleChecked} module home(s) at ${pkg}.`,
);
