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

// ---- check 4 (spec-align surface), 13 (spec-align contract), 14 (adr-home) ----

test("check 4: a step file naming a spec-align subcommand the CLI lacks is caught", (t) => {
  const root = fixture(t);
  write(root, "skills/_shared/steps/brand-new-dir/sa.md",
        "```bash\n{spec_align} frobnicate --epic E001\n```\n");
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /sa\.md:2: names spec-align\.py subcommand 'frobnicate'/);
});

test("check 4: an undocumented spec-align subcommand is caught", (t) => {
  const root = fixture(t);
  const rel = "docs/l3io-pm-reference.md";
  const text = fs.readFileSync(path.join(root, rel), "utf8");
  write(root, rel, text.replace(/^\| `check-stale` \|.*\n/m, ""));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /does not document spec-align\.py subcommand 'check-stale'/);
});

test("check 4: spec-align names in backticks are not read as pm-status subcommands", (t) => {
  const root = fixture(t);
  write(root, "CLAUDE.md", "\nRun `check-pointers`, then `check-stale`.\n", true);
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test("check 13: a pattern added to layout-cleanup alone is caught", (t) => {
  const root = fixture(t);
  const rel = "skills/l3io-util-doctor/steps/layout-cleanup.md";
  const text = fs.readFileSync(path.join(root, rel), "utf8");
  write(root, rel, text.replace("`*tech-design*`", "`*tech-design*`, `*blueprint*`"));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /architecture patterns differ.*\*blueprint\*/s);
});

test("check 13: a renamed dimension in the enrichment prompt is caught", (t) => {
  const root = fixture(t);
  const rel = "skills/_shared/steps/sprint/step-02-story-prep.md";
  const text = fs.readFileSync(path.join(root, rel), "utf8");
  write(root, rel, text.replace("   ### Testability approach", "   ### Test approach"));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /dimensions differ/);
});

test("check 13 scope: a prompt that lost its layout block is caught", (t) => {
  const root = fixture(t);
  const rel = "skills/_shared/steps/sprint/step-02-story-prep.md";
  const text = fs.readFileSync(path.join(root, rel), "utf8");
  write(root, rel, text.replace(/^\s*## Technical acceptance criteria\s*$/m, ""));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /no '## Technical acceptance criteria' layout block/);
});

test("check 14: the old ADR home in a new directory is caught", (t) => {
  const root = fixture(t);
  write(root, "skills/_shared/steps/brand-new-dir/adr.md",
        "Write it to `{implementation_artifacts}/epic-001/arch/adr-0001-x.md`.\n");
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /adr\.md:1: .*arch\/adr-0001-x\.md/);
});

test("check 14: the old ADR glob inside a fence is caught", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-util-doctor/assets/brand-new.md",
        "```\nls {implementation_artifacts}/epic-*/arch/*.md\n```\n");
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /brand-new\.md:2/);
});

test("check 14: naming the old home as legacy, and the gate review file, pass", (t) => {
  const root = fixture(t);
  write(root, "skills/_shared/steps/brand-new-dir/ok.md",
        "The old home `epic-*/arch/adr-*` is legacy.\n" +
        "The review lives at `{implementation_artifacts}/epic-001/arch/arch-gate-review.md`.\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test("check 14: a qualifier word appended after the path does not exempt it", (t) => {
  const root = fixture(t);
  write(root, "skills/_shared/steps/brand-new-dir/bypass.md",
        "Write it to `{implementation_artifacts}/epic-001/arch/adr-0001-x.md` for legacy reasons.\n");
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /bypass\.md:1: .*arch\/adr-0001-x\.md/);
});

test("check 14: a qualifier that introduces the path still exempts it", (t) => {
  const root = fixture(t);
  write(root, "skills/_shared/steps/brand-new-dir/prose.md",
        "See the old per-epic home (`epic-*/arch/adr-*`) for background.\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test("check 14: an abbreviation's period between the qualifier and the path does not break the sentence", (t) => {
  const root = fixture(t);
  write(root, "skills/_shared/steps/brand-new-dir/eg.md",
        "This describes the old per-epic home, e.g. `epic-001/arch/adr-0001-x.md`, for background.\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test("check 14: a genuine new sentence after the qualifier is still caught", (t) => {
  const root = fixture(t);
  write(root, "skills/_shared/steps/brand-new-dir/new-sentence.md",
        "That was the legacy layout. Read `epic-001/arch/adr-0001-x.md` now.\n");
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /new-sentence\.md:1: .*arch\/adr-0001-x\.md/);
});

// ---- check 15 (doctor-mode-count) ----

test("check 15: a stated count one below the real one is caught", (t) => {
  const root = fixture(t);
  write(root, "CLAUDE.md",
        fs.readFileSync(path.join(root, "CLAUDE.md"), "utf8")
          .replace("each of its nineteen modes lives in its own `steps/` file",
                   "each of its eighteen modes lives in its own `steps/` file"));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /CLAUDE\.md: says "eighteen" modes, but the doctor has 19 mode\(s\)/);
});

test("check 15: the correct count passes", (t) => {
  const root = fixture(t);
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test("check 15 scope attack: a new steps file plus its routing row, prose unchanged, is caught", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-util-doctor/steps/zzz-extra-mode.md", "# Extra mode\n");
  const rel = "skills/l3io-util-doctor/SKILL.md";
  const text = fs.readFileSync(path.join(root, rel), "utf8");
  write(root, rel, text.replace(
    "| `stats` | `steps/stats.md` | read-only — plan-aware progress dashboard |",
    "| `stats` | `steps/stats.md` | read-only — plan-aware progress dashboard |\n" +
      "| `zzz-extra` | `steps/zzz-extra-mode.md` | test-only extra mode |"));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /says "nineteen" modes, but the doctor has 20 mode\(s\)/);
});

test("check 15: a steps file with no routing row trips the derivations-disagree branch", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-util-doctor/steps/zzz-orphan-mode.md", "# Orphan mode\n");
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /mode count derivations disagree — 20 steps\/ file\(s\), 19 routing row\(s\), 19 file\(s\) referenced/);
});
