// Tests for scripts/check-docs.mjs check 11 (append-issue-pointer). Run: npm run test:scripts
// Each test runs the REAL checker against a temp copy of the repo (via CHECK_DOCS_ROOT),
// so what is tested is the entry point CI runs, not an extracted function.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const CHECK = path.join(REPO, "scripts", "check-docs.mjs");

function fixture(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "check-docs-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  fs.cpSync(REPO, dir, {
    recursive: true,
    filter: (src) =>
      !path.relative(REPO, src).split(path.sep).some((p) => p === ".git" || p === "node_modules"),
  });
  return dir;
}

function run(root) {
  return spawnSync(process.execPath, [CHECK], {
    cwd: REPO,
    env: { ...process.env, CHECK_DOCS_ROOT: root },
    encoding: "utf8",
  });
}

function write(root, rel, text, append = false) {
  const p = path.join(root, rel);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  (append ? fs.appendFileSync : fs.writeFileSync)(p, text);
}

const UNPOINTED = [
  "```bash",
  "python3 {pm_status} append-issue --file {pm_issues_file} \\",
  '  --epic 001 --title "T" --source "qa (Q-1)" --severity Low',
  "```",
  "",
].join("\n");

test("an unmodified copy passes", (t) => {
  const r = run(fixture(t));
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test("scope attack: a producer in a new file in a new directory is caught", (t) => {
  const root = fixture(t);
  write(root, "skills/_shared/steps/brand-new-dir/step-new.md", "# New\n\n" + UNPOINTED);
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /brand-new-dir\/step-new\.md:\d+: append-issue without --description/);
});

test("a producer inside a SKILL.md is caught", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-help/SKILL.md", "\n" + UNPOINTED, true);
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /l3io-pm-help\/SKILL\.md:\d+: append-issue without --description/);
});

test("a producer inside a skill's assets/ is caught", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-util-doctor/assets/brand-new.md", UNPOINTED);
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /assets\/brand-new\.md:\d+/);
});

test("prose mentioning append-issue is not an invocation", (t) => {
  const root = fixture(t);
  write(root, "skills/_shared/steps/brand-new-dir/prose.md",
        "Record it with `pm-status.py append-issue`, pointing at the report.\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});
