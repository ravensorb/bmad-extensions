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

// ---- real repository integration ----
//
// Everything above exercises the checker against synthetic fixtures. This is the one test
// that runs it against this actual repo's skills/ tree, copied to a temp dir so the real
// checker (CHECK_MODULE_ROOT) is what CI runs -- not an extracted function. The baseline
// count is derived HERE, with its own readdirSync over the copy, never by importing or
// reusing check-docs.mjs's derivedCounts(): two derivations from the same function would
// agree by construction and test nothing. A +/-1 tolerance lets the package gain or lose one
// module home without this test needing an edit for every such change, while still catching
// a checker that suddenly reports zero or a wildly wrong count.
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
  const baseline = 4; // l3io-pm, l3io-util, l3io-sec, l3io-arch, as of this test's authoring
  assert.ok(
    Math.abs(moduleHomes.length - baseline) <= 1,
    `expected ${baseline} +/-1 module home(s), found ${moduleHomes.length}: ${moduleHomes.join(", ")}`,
  );

  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});
