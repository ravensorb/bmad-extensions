// Tests for scripts/check-module.mjs.
// Run: npm run test:scripts
// Each test runs the REAL checker (via CHECK_MODULE_ROOT) against a fixture built from an
// EMPTY skills/ tree -- unlike check-docs.test.mjs's fixture(t), this does not copy the repo,
// because these tests construct modules from nothing rather than mutating real ones.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const CHECK = path.join(REPO, "scripts", "check-module.mjs");

function fixture(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "check-module-"));
  fs.mkdirSync(path.join(dir, "skills"), { recursive: true });
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  return dir;
}

function run(root, args = []) {
  return spawnSync(process.execPath, [CHECK, ...args], {
    cwd: REPO,
    env: { ...process.env, CHECK_MODULE_ROOT: root },
    encoding: "utf8",
  });
}

function write(root, rel, text) {
  const p = path.join(root, rel);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, text);
}

function writeModuleHome(root, dir, code) {
  write(root, `skills/${dir}/assets/module.yaml`, `code: ${code}\nname: "${dir}"\ndescription: "test module"\n`);
  write(root, `skills/${dir}/assets/module-setup.md`, "# setup\n");
  write(root, `skills/${dir}/assets/module-help.csv`, `skill,module,description\n${dir},${code},test skill\n`);
  write(root, `skills/${dir}/scripts/merge-config.py`, "# merge-config\n");
  write(root, `skills/${dir}/scripts/merge-help-csv.py`, "# merge-help-csv\n");
}

test("check:module rejects a module.yaml at a skill root", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/module.yaml", "code: l3io-pm\n");
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /module\.yaml at a skill root/);
});

test("check:module rejects two assets/module.yaml sharing one code", (t) => {
  const root = fixture(t);
  write(root, "skills/a/assets/module.yaml", "code: dup\nname: A\ndescription: d\n");
  write(root, "skills/b/assets/module.yaml", "code: dup\nname: B\ndescription: d\n");
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /code 'dup' is declared by 2 module\.yaml files/);
});

test("check:module rejects a module home missing a merge script", (t) => {
  const root = fixture(t);
  write(root, "skills/solo/assets/module.yaml", "code: solo\nname: S\ndescription: d\n");
  write(root, "skills/solo/assets/module-setup.md", "x\n");
  write(root, "skills/solo/assets/module-help.csv", "skill,module,description\n");
  write(root, "skills/solo/scripts/merge-config.py", "x\n");
  // merge-help-csv.py deliberately absent
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /missing scripts\/merge-help-csv\.py/);
});

test("check:module passes on a well-formed standalone module", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "solo", "solo");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// ---- check 5 (home-placement) ----
//
// This is the rule l3io-pm-setup itself exists to satisfy: a module home shared by more than
// one skill must be a dedicated *-setup skill, never one of the module's own operational
// skills. Untested before this task added the first real multi-skill module home
// (l3io-pm-setup) -- a check with no test for its own branch is worse than no check, because
// it reads as covering something it has never actually been proven to catch.
test("check:module rejects a multi-skill module whose home is not a *-setup skill", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "l3io-pm-execute", "l3io-pm"); // home lacks a -setup suffix
  write(root, "skills/l3io-pm-plan/SKILL.md", "# plan\n"); // second sibling under the same code
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /is not a \*-setup directory/);
});

test("check:module passes when a multi-skill module's home is a *-setup skill", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "l3io-pm-setup", "l3io-pm");
  write(root, "skills/l3io-pm-execute/SKILL.md", "# execute\n");
  write(root, "skills/l3io-pm-plan/SKILL.md", "# plan\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// ---- pm-status.py singleton per module ----
//
// Task 11A: pm-status.py used to ship four times (execute/plan/sync/util-doctor), three of
// them in one module self-installing identical bytes to the identical destination. The end
// state is one payload copy per module that self-installs it -- l3io-pm-setup for l3io-pm,
// l3io-util-doctor for l3io-util. This guards the invariant mechanically so a future sync-group
// edit can't silently reintroduce a second copy inside one module.
test("check:module rejects a second pm-status.py payload within one module", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "l3io-pm-setup", "l3io-pm");
  write(root, "skills/l3io-pm-setup/scripts/pm-status.py", "# x\n");
  write(root, "skills/l3io-pm-execute/scripts/pm-status.py", "# x\n");
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /pm-status\.py appears 2 times for module 'l3io-pm'/);
});

test("check:module passes when only one skill in a module carries pm-status.py", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "l3io-pm-setup", "l3io-pm");
  write(root, "skills/l3io-pm-setup/scripts/pm-status.py", "# x\n");
  write(root, "skills/l3io-pm-execute/SKILL.md", "# execute\n");
  write(root, "skills/l3io-pm-plan/SKILL.md", "# plan\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// ---- check 7 (csv-skill-exists) ----
//
// Fix round 1, F-4: three real module-help.csv files each carried a phantom row for a
// "*-setup" skill that never existed and, by design, never will (three of the four modules
// are standalone). validate-module.py (BMad-installed, gitignored, can't run in CI) calls
// this an "orphan-entry" finding; check:module had no repo-side equivalent because check 4
// only asserts the CSV file exists, never parses it. These tests exercise the new check
// against the real CSV format (quoted, comma-bearing description fields), not the
// writeModuleHome() helper's minimal 3-column stand-in.
test("check:module rejects a module-help.csv row naming a skill that does not exist", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "solo", "solo");
  write(root, "skills/solo/assets/module-help.csv",
    "module,skill,display-name,menu-code,description,action,args,phase,preceded-by,followed-by,required,output-location,outputs\n" +
    'Solo,solo,Solo,SOL,"Real skill, real row.",run,,anytime,,,false,,report\n' +
    'Solo,solo-setup,Setup,SST,"Phantom row for a skill that was never built.",configure,,anytime,,,false,,config\n');
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /row names skill 'solo-setup', which is not a directory under skills\//);
});

test("check:module passes a module-help.csv whose rows all name real skills", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "multi-setup", "multi");
  write(root, "skills/multi-a/SKILL.md", "# a\n");
  write(root, "skills/multi-b/SKILL.md", "# b\n");
  write(root, "skills/multi-setup/assets/module-help.csv",
    "module,skill,display-name,menu-code,description,action,args,phase,preceded-by,followed-by,required,output-location,outputs\n" +
    'Multi,multi-a,A,MA,"Does A, and does it well.",run,,anytime,,,false,,report\n' +
    'Multi,multi-b,B,MB,"Does B.",run,,anytime,,,false,,report\n');
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// ---- parsers, not hand-written readers (Task 17) ----
//
// `parseModuleYaml()` was a per-line `key: value` regex plus a hand-written block-scalar
// rule, and `splitCsvLine()` was a character loop; both existed only because CI ran no
// `npm install`. They are now `yaml` and `csv-parse` (see
// docs/adr/0007-ci-installs-npm-dependencies.md). These tests pin what that changes: both
// parsers fail CLOSED on input they cannot read, and the CSV shape the splitter got WRONG
// now parses correctly.

// A quoted field spanning two physical lines is one field. The old splitter worked line by
// line, so the continuation line became a row of its own, and check 7 read its first column
// as a skill name -- a phantom "orphan capability entry" failure on a perfectly valid file.
test("check:module reads a quoted CSV field that spans two lines as one field", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "solo", "solo");
  write(root, "skills/solo/assets/module-help.csv",
    "skill,module,description\n" +
    'solo,solo,"Validate readiness, elaborate stories,\nand build the dependency graph."\n');
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// A CRLF file is not a file whose last column ends in a stray carriage return.
test("check:module reads a CRLF module-help.csv without a trailing carriage return", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "solo", "solo");
  write(root, "skills/solo/assets/module-help.csv",
    "module,description,skill\r\nsolo,a skill,solo\r\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// Fail closed: a module.yaml that is not YAML used to read as an empty field set, which check
// 2 reported as three missing fields and check 3 never saw at all (no `code`). It is now
// reported as what it is.
test("check:module reports a module.yaml that is not valid YAML", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "solo", "solo");
  write(root, "skills/solo/assets/module.yaml",
    "code: solo\nname: Broken: unquoted colon\ndescription: d\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /skills\/solo\/assets\/module\.yaml: is not valid YAML/);
});

// Fail closed: a module-help.csv the parser cannot read is reported, never silently treated
// as zero rows -- which would make check 7 pass over a file it never examined (CLAUDE.md §4).
test("check:module reports a module-help.csv that is not valid CSV", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "solo", "solo");
  write(root, "skills/solo/assets/module-help.csv",
    'skill,module,description\nsolo,solo,"unterminated quote\n');
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /skills\/solo\/assets\/module-help\.csv: is not valid CSV/);
});

// A quoted scalar is its unquoted value. The old reader kept the quote characters in the
// field, so `name: "X"` was the five-character string `"X"` -- harmless for the emptiness
// test it fed, and wrong for anything that ever compares the value.
test("check:module reads a quoted module.yaml scalar as its unquoted value", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "solo", "solo");
  write(root, "skills/solo/assets/module.yaml",
    'code: "solo"\nname: "LiquidLogicLabs Solo"\ndescription: "A solo module."\n');
  write(root, "skills/solo-extra/assets/module.yaml",
    "code: solo\nname: Duplicate\ndescription: d\n");
  const r = run(root);
  // The two files declare the SAME code once unquoted; if the quotes were kept, `"solo"` and
  // `solo` would be different codes and check 3 would see one home each.
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /code 'solo' is declared by 2 module\.yaml files/);
});

// ---- real repository integration ----
//
// Everything above exercises the checker against synthetic fixtures. This is the one test
// that runs it against this actual repo's skills/ tree, copied to a temp dir so the real
// checker (CHECK_MODULE_ROOT) is what CI runs -- not an extracted function. The baseline
// count is derived HERE, with its own readdirSync over the copy, never by importing or
// reusing check-docs.mjs's derivedCounts(): two derivations from the same function would
// agree by construction and test nothing.
//
// Fix round 1, F-7: a prior version compared the module-home count to a hand-typed literal
// (`const baseline = 4`) with a +/-1 tolerance -- exactly the hand-enumeration class this
// plan exists to remove, and loose enough that a module home silently disappearing (4->3)
// would still pass. Compared instead against .claude-plugin/marketplace.json's own `plugins`
// array length: a second, genuinely independent fact about the package (what the installer
// registers) that must agree with the first (what skills/ actually contains) by construction
// -- no module should ever exist as one without the other -- so the comparison is exact, not
// approximate, and needs no maintenance as modules are added or removed.
function fixtureFromRepo(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "check-module-real-"));
  fs.cpSync(REPO, dir, {
    recursive: true,
    filter: (src) =>
      !path.relative(REPO, src).split(path.sep).some((p) => p === ".git" || p === "node_modules"),
  });
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  return dir;
}

test("the real repository passes check:module with the expected module-home shape", (t) => {
  const root = fixtureFromRepo(t);
  const skillsDir = path.join(root, "skills");
  const moduleHomes = fs.readdirSync(skillsDir, { withFileTypes: true })
    .filter((e) => e.isDirectory())
    .map((e) => e.name)
    .filter((name) => fs.existsSync(path.join(skillsDir, name, "assets", "module.yaml")));

  const marketplace = JSON.parse(
    fs.readFileSync(path.join(root, ".claude-plugin", "marketplace.json"), "utf8"),
  );
  const declaredPluginCount = marketplace.plugins.length;
  assert.equal(
    moduleHomes.length,
    declaredPluginCount,
    `found ${moduleHomes.length} module home(s) under skills/ (${moduleHomes.join(", ")}) ` +
      `but .claude-plugin/marketplace.json declares ${declaredPluginCount} plugin(s)`,
  );

  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});
