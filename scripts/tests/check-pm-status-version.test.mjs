// Tests for scripts/check-pm-status-version.mjs.
// Run: npm run test:scripts
// Each test runs the REAL checker (via CHECK_VERSION_ROOT) against a fixture built from an
// EMPTY tree -- unlike check-docs.test.mjs's fixture(t), this does not copy the repo, because
// these tests construct pm-status.py / package.json / module homes from nothing rather than
// mutating real ones.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const CHECK = path.join(REPO, "scripts", "check-pm-status-version.mjs");

function fixture(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "check-version-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  return dir;
}

function run(root, args = []) {
  return spawnSync(process.execPath, [CHECK, ...args], {
    cwd: REPO,
    env: { ...process.env, CHECK_VERSION_ROOT: root },
    encoding: "utf8",
  });
}

function write(root, rel, text) {
  const p = path.join(root, rel);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, text);
}

function writePkg(root, version) {
  write(root, "package.json", JSON.stringify({ name: "fixture", version }));
}

function writePmStatus(root, version) {
  write(root, "skills/_shared/pm-status.py",
    `# pm-status-version: ${version}\nPM_STATUS_VERSION = "${version}"\n`);
}

function writeModuleHome(root, skill, code, version, { atRoot = false } = {}) {
  const rel = atRoot ? `skills/${skill}/module.yaml` : `skills/${skill}/assets/module.yaml`;
  write(root, rel, `code: ${code}\nname: "${skill}"\ndescription: "test"\nmodule_version: ${version}\n`);
}

test("a consistent tree at one version passes", (t) => {
  const root = fixture(t);
  writePkg(root, "1.2.3");
  writePmStatus(root, "1.2.3");
  writeModuleHome(root, "solo", "solo", "1.2.3");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test("a module home at the wrong version is caught", (t) => {
  const root = fixture(t);
  writePkg(root, "1.2.3");
  writePmStatus(root, "1.2.3");
  writeModuleHome(root, "solo", "solo", "1.2.2");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /skills\/solo\/assets\/module\.yaml: module_version is 1\.2\.2 but package\.json says 1\.2\.3/);
});

test("a legacy skill-root module.yaml is still checked", (t) => {
  const root = fixture(t);
  writePkg(root, "1.2.3");
  writePmStatus(root, "1.2.3");
  writeModuleHome(root, "legacy", "legacy", "0.9.0", { atRoot: true });
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /skills\/legacy\/module\.yaml: module_version is 0\.9\.0 but package\.json says 1\.2\.3/);
});

test("multiple module homes at the release version all pass together", (t) => {
  const root = fixture(t);
  writePkg(root, "2.0.0");
  writePmStatus(root, "2.0.0");
  writeModuleHome(root, "a-setup", "a", "2.0.0");
  writeModuleHome(root, "b", "b", "2.0.0");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test("a module home missing module_version is caught", (t) => {
  const root = fixture(t);
  writePkg(root, "1.0.0");
  writePmStatus(root, "1.0.0");
  write(root, "skills/solo/assets/module.yaml", "code: solo\nname: \"solo\"\ndescription: \"test\"\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /skills\/solo\/assets\/module\.yaml: no "module_version:" field found/);
});

test("_shared is never treated as a module home", (t) => {
  const root = fixture(t);
  writePkg(root, "1.0.0");
  writePmStatus(root, "1.0.0");
  // _shared has no module.yaml of its own, but even if it did, it must never be scanned as a
  // module home -- it is the sync source, not a skill.
  write(root, "skills/_shared/module.yaml", "code: not-a-module\nmodule_version: 0.0.1\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test("no module homes at all still passes on pm-status.py's own invariant", (t) => {
  const root = fixture(t);
  writePkg(root, "1.0.0");
  writePmStatus(root, "1.0.0");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
  assert.match(r.stdout, /0 module home\(s\)/);
});

test("pm-status.py marker/constant disagreement is still caught alongside module checks", (t) => {
  const root = fixture(t);
  writePkg(root, "1.0.0");
  write(root, "skills/_shared/pm-status.py",
    '# pm-status-version: 1.0.0\nPM_STATUS_VERSION = "0.9.9"\n');
  writeModuleHome(root, "solo", "solo", "1.0.0");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /marker says 1\.0\.0 but PM_STATUS_VERSION says 0\.9\.9/);
});
