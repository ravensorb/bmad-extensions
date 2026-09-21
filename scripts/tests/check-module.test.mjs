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
