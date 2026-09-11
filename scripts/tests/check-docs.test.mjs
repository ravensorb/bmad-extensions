// Tests for scripts/check-docs.mjs checks 11 (append-issue-pointer) and 12 (pm-status-size).
// Run: npm run test:scripts
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

test("fence attack: a producer after a stray four-backtick fence is caught", (t) => {
  const root = fixture(t);
  write(root, "skills/_shared/steps/brand-new-dir/odd-fence.md", "# Odd\n\n````\nstray\n\n" + UNPOINTED);
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /odd-fence\.md:\d+: append-issue without --description/);
});

test("an inline invocation with flags is caught", (t) => {
  const root = fixture(t);
  write(root, "skills/_shared/steps/brand-new-dir/inline.md",
        'Run `{pm_status} append-issue --epic 001 --title "T" --source "qa (Q-1)" --severity Low` now.\n');
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /inline\.md:\d+: append-issue without --description/);
});

test("split-line attack: a token and its append-issue on continued lines are caught", (t) => {
  const root = fixture(t);
  write(root, "skills/_shared/steps/brand-new-dir/split.md", [
    "```bash",
    "python3 {pm_status} \\",
    '  append-issue --file {pm_issues_file} --epic 001 --title "T" --source "qa (Q-1)" --severity Low',
    "```",
    "",
  ].join("\n"));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /split\.md:2: append-issue without --description/);
});

test("prose mentioning append-issue is not an invocation", (t) => {
  const root = fixture(t);
  write(root, "skills/_shared/steps/brand-new-dir/prose.md",
        "Record it with `pm-status.py append-issue`, pointing at the report.\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test("check 12: pm-status.py over the 8,000-line limit is caught", (t) => {
  const root = fixture(t);
  // Padded with comment-only lines so every other check that parses this file (cli-surface,
  // cli-docstring, metric-list, append-issue-pointer) still sees the same real content and
  // still passes -- only the line count should trip.
  write(root, "skills/_shared/pm-status.py", "# pad\n".repeat(8001), true);
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /pm-status\.py: \d+ lines, over the 8000-line limit/);
});

// Pads the fixture's REAL pm-status.py to exactly `total` lines. Lines are counted the way
// check 12 counts them (newlines, as `wc -l` does), so the boundary tested is the checker's.
function padPmStatusTo(root, total) {
  const rel = "skills/_shared/pm-status.py";
  const have = (fs.readFileSync(path.join(root, rel), "utf8").match(/\n/g) || []).length;
  assert.ok(have < total, `pm-status.py already has ${have} lines; cannot pad to ${total}`);
  write(root, rel, "# pad\n".repeat(total - have), true);
  assert.equal((fs.readFileSync(path.join(root, rel), "utf8").match(/\n/g) || []).length, total);
}

test("check 12 boundary: exactly 8,000 lines passes", (t) => {
  const root = fixture(t);
  padPmStatusTo(root, 8000);
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test("check 12 boundary: 8,001 lines fails on check 12 alone", (t) => {
  const root = fixture(t);
  padPmStatusTo(root, 8001);
  const r = run(root);
  assert.equal(r.status, 1);
  // check-docs.mjs prints "\n<N> documentation problem(s):\n" and then one "  ✗ <failure>"
  // entry per failure. One problem, and that one check 12's, means every other check that
  // reads this file (cli-surface, cli-docstring, metric-list, append-issue-pointer) passed.
  assert.match(r.stderr, /^1 documentation problem\(s\):$/m, r.stderr);
  const entries = r.stderr.split("\n").filter((l) => l.startsWith("  ✗ "));
  assert.equal(entries.length, 1, r.stderr);
  assert.match(entries[0], /pm-status\.py: 8001 lines, over the 8000-line limit .* by 1$/);
});
