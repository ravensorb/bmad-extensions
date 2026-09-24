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
import { resolverInvariant } from "../check-docs.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const CHECK = path.join(REPO, "scripts", "check-docs.mjs");

function fixture(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "check-docs-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  fs.cpSync(REPO, dir, {
    recursive: true,
    // __pycache__ is filtered for the same reason check 22 asks git rather than readdirSync:
    // it is gitignored build noise, it lands under skill payload directories whenever the
    // Python suites run, and in a fixture (which is not a git work tree, so check 22 falls
    // back to the filesystem) it would make every test in this file fail over a README row
    // that is correct. Running `npm run test:scripts` after the Python tests used to do
    // exactly that.
    filter: (src) =>
      !path.relative(REPO, src).split(path.sep)
        .some((p) => p === ".git" || p === "node_modules" || p === "__pycache__"),
  });
  return dir;
}

function run(root, args = []) {
  return spawnSync(process.execPath, [CHECK, ...args], {
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

// The hand-kept prefix list in the forward arm's fallback (the ^(set|estimate|move|archive|
// append|list|check|clear|self)- test) judges any hyphenated backtick token in that shape, on
// any line, even one that names neither pm-status.py nor {pm_status}. `check-deps` (a
// l3io-util-doctor mode keyword) and `check-ignore` (git's own subcommand) both start with
// "check-", so both used to be misjudged as claimed pm-status.py subcommands.
test("check 4: an l3io-util-doctor mode keyword (check-deps) is not read as a claimed pm-status subcommand", (t) => {
  const root = fixture(t);
  write(root, "CLAUDE.md", "\nSee `check-deps` for the BMad dependency report.\n", true);
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test("check 4: a token structurally naming another tool's subcommand (grep `check-ignore`) is not read as a claimed pm-status subcommand", (t) => {
  const root = fixture(t);
  write(root, "CLAUDE.md", "\nSanity check: grep `check-ignore` in the health check step file.\n", true);
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test("check 4: a genuinely fabricated pm-status.py subcommand in that same shape is still caught", (t) => {
  const root = fixture(t);
  write(root, "CLAUDE.md", "\nRun `check-frobnicate` before shipping a release.\n", true);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr,
    /documents pm-status\.py subcommand 'check-frobnicate', which the CLI does not have/);
});

test("check 10: a spec-align.py subcommand missing from its own docstring is caught", (t) => {
  const root = fixture(t);
  const rel = "skills/_shared/spec-align.py";
  const text = fs.readFileSync(path.join(root, rel), "utf8");
  write(root, rel, text.replace(
    'sub = p.add_subparsers(dest="cmd", required=True)',
    'sub = p.add_subparsers(dest="cmd", required=True)\n\n'
      + '    fr = sub.add_parser("frobnicate", help="not in the docstring")\n'
      + '    fr.set_defaults(func=cmd_build)',
  ));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /spec-align\.py: module docstring's Subcommands list is missing 1 subcommand\(s\).*frobnicate/s);
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
//
// These three probes plant one extra (or one altered) mode on top of the REAL doctor tree,
// so their expected numbers must be derived from that tree rather than typed as literals --
// a literal drifts the moment a real mode is added or removed, which is exactly the class of
// bug check 15 exists to catch in the docs it polices. See the repo rule: derive scope from
// the source of truth, never enumerate it by hand -- applied here to the tests that police it.

// Same source of truth check 15 itself counts from: .md files under doctor's steps/.
function realModeCount(root) {
  return fs.readdirSync(path.join(root, "skills", "l3io-util-doctor", "steps"))
    .filter((f) => f.endsWith(".md")).length;
}

// The English number word CLAUDE.md currently states, read back rather than assumed.
function claudeModeWord(root) {
  const text = fs.readFileSync(path.join(root, "CLAUDE.md"), "utf8");
  const m = text.match(/each of its ([a-z-]+) modes lives in its own `steps\/` file/);
  return m ? m[1] : null;
}

// Local lookup, not imported from check-docs.mjs (awkward from a test file since the script
// has no exports) -- but every use below indexes it by a count derived from the tree, never
// by a hard-coded number.
const NUMBER_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
  "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
  "seventeen", "eighteen", "nineteen", "twenty", "twenty-one", "twenty-two", "twenty-three",
  "twenty-four", "twenty-five", "twenty-six"];

test("check 15: a stated count one below the real one is caught", (t) => {
  const root = fixture(t);
  const n = realModeCount(root);
  const word = claudeModeWord(root);
  assert.equal(NUMBER_WORDS.indexOf(word), n,
    "fixture's CLAUDE.md claim should match the real steps/ count before this test mutates it");
  const wrong = NUMBER_WORDS[n - 1];
  write(root, "CLAUDE.md",
        fs.readFileSync(path.join(root, "CLAUDE.md"), "utf8")
          .replace(`each of its ${word} modes lives in its own \`steps/\` file`,
                   `each of its ${wrong} modes lives in its own \`steps/\` file`));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, new RegExp(`CLAUDE\\.md: says "${wrong}" modes, but the doctor has ${n} mode\\(s\\)`));
});

test("check 15: the correct count passes", (t) => {
  const root = fixture(t);
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test("check 15 scope attack: a new steps file plus its routing row, prose unchanged, is caught", (t) => {
  const root = fixture(t);
  const n = realModeCount(root);
  const word = claudeModeWord(root);
  assert.equal(NUMBER_WORDS.indexOf(word), n,
    "fixture's CLAUDE.md claim should match the real steps/ count before this test mutates it");
  write(root, "skills/l3io-util-doctor/steps/zzz-extra-mode.md", "# Extra mode\n");
  const rel = "skills/l3io-util-doctor/SKILL.md";
  const text = fs.readFileSync(path.join(root, rel), "utf8");
  // Anchored on the check-deps routing row rather than a literal that carries prose: the
  // stats row was this anchor until its Notes cell was reworded, and the replace silently
  // became a no-op, so the test planted a steps file with no row and asserted the wrong
  // branch. Assert the anchor before using it -- a future reword fails HERE, loudly.
  const anchor = "| `check-deps` | `steps/check-deps.md` |";
  assert.ok(text.includes(anchor), `the routing row this test anchors on must exist: ${anchor}`);
  write(root, rel, text.replace(anchor,
    "| `zzz-extra` | `steps/zzz-extra-mode.md` | test-only extra mode |\n" + anchor));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, new RegExp(`says "${word}" modes, but the doctor has ${n + 1} mode\\(s\\)`));
});

test("check 15: a steps file with no routing row trips the derivations-disagree branch", (t) => {
  const root = fixture(t);
  const n = realModeCount(root);
  write(root, "skills/l3io-util-doctor/steps/zzz-orphan-mode.md", "# Orphan mode\n");
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, new RegExp(
    `mode count derivations disagree — ${n + 1} steps\\/ file\\(s\\), ${n} routing row\\(s\\), ${n} file\\(s\\) referenced`));
});

// ---- check 16 (bmad-dependency-inventory) ----
//
// The check's scope is derived by walking skills/ markdown plus every skills/<dir>/assets/module.yaml,
// so the planted violations below go into new files, a new skills/ directory, and a module.yaml,
// not only into files the check's author happened to think of.

const DEP_INV = "skills/l3io-util-doctor/assets/bmad-dependencies.json";

// Rewrites the fixture's REAL inventory through JSON.parse/stringify, so what is tested is the
// schema the check reads, not a hand-built stand-in.
function editInventory(root, mutate) {
  const inv = JSON.parse(fs.readFileSync(path.join(root, DEP_INV), "utf8"));
  mutate(inv);
  write(root, DEP_INV, `${JSON.stringify(inv, null, 2)}\n`);
}

test("check 16: an undeclared bmad-* token is caught", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/x-undeclared.md",
        "Spawn `bmad-frobnicate` with the story path.\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /x-undeclared\.md:1: names 'bmad-frobnicate', not declared in/);
});

test("check 16: a step file dispatching a removed skill fails", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/x.md",
        "Spawn `bmad-architect` subagent with the story path.\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /dispatches removed skill 'bmad-architect'/);
});

test("check 16: a module.yaml naming an undeclared skill is caught", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-arch-review/assets/module.yaml", "\n# also requires bmad-frobnicate\n", true);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /l3io-arch-review\/assets\/module\.yaml:\d+: names 'bmad-frobnicate', not declared in/);
});

test("check 16: an entry missing a status-required field is caught", (t) => {
  const root = fixture(t);
  editInventory(root, (inv) => {
    delete inv.skills.find((e) => e.name === "bmad-code-review").module;
  });
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /'bmad-code-review' is required but names no module/);
});

test("check 16: a duplicate inventory entry is caught", (t) => {
  const root = fixture(t);
  editInventory(root, (inv) => {
    inv.skills.push({ name: "bmad-help", status: "optional", module: "bmm" });
  });
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /duplicate entry 'bmad-help'/);
});

test("check 16 scope attack: a brand-new skills/<dir>/ with a new step file is caught", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-brandnew-gate/steps/step-new.md",
        "Dispatch `bmad-frobnicate` for the gate review.\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /l3io-pm-brandnew-gate\/steps\/step-new\.md:1: names 'bmad-frobnicate'/);
});

test("check 16: the real tree passes", (t) => {
  const r = run(fixture(t));
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test("check 16: a removed skill named beside its replacement is allowed", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/x-mapped.md",
        "Migrated: `bmad-architect` is now `bmad-architecture`.\n");
  const r = run(root, ["-v"]);
  assert.equal(r.status, 0, r.stderr + r.stdout);
  assert.match(r.stdout,
               /x-mapped\.md:1: names removed skill 'bmad-architect' as history/);
});

test("check 16: a removed skill on a line saying legacy is allowed", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/x-legacy.md",
        "The `bmad-ux-review` name is legacy.\n");
  const r = run(root, ["-v"]);
  assert.equal(r.status, 0, r.stderr + r.stdout);
  assert.match(r.stdout, /x-legacy\.md:1: names removed skill 'bmad-ux-review' as history/);
});

// The two cases below look alike and prove different things; both are needed.
//
// This one plants "removed", which is NOT one of check 16's three evidence arms. It therefore
// fails wherever it sits, and that is all it shows: that a plausible-sounding explanatory word
// is not an arm. It does NOT test the same-line rule — widening the `legacy` arm to test the
// whole joined file leaves this case failing exactly as before, i.e. green.
test("check 16: 'removed' is not an evidence arm, so it never excuses a dispatch", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/x-window.md",
        "This skill was removed upstream.\n\n\n\nSpawn `bmad-architect` subagent.\n");
  const r = run(root);
  assert.equal(r.status, 1, "check 1's ±4-line window would have allowed this; check 16 must not");
  assert.match(r.stderr, /dispatches removed skill/);
});

// This one carries a REAL arm (`legacy`) four lines from the dispatch, so it is the case that
// actually discriminates line-scoped evidence from file-scoped evidence: it fails at HEAD
// (correct — the dispatch line itself carries nothing) and passes the moment the arm is widened
// from `.test(line)` to `.test(lines.join("\n"))`. Verified by mutation, both directions.
// Line 1 is allowed on its own merits — it names the removed skill AND says `legacy`, on one
// line — which is precisely why the failure must come from line 5 and nowhere else.
test("check 16: the word `legacy` four lines away does NOT excuse a dispatch", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/x-window-legacy.md",
        "The bmad-architect skill is legacy.\n\n\n\nSpawn `bmad-architect` subagent.\n");
  const r = run(root);
  assert.equal(r.status, 1, "evidence must be on the dispatch line; a whole-file test would pass this");
  assert.match(r.stderr, /x-window-legacy\.md:5: dispatches removed skill 'bmad-architect'/);
});

test("check 16: a leading underscore yields no token (_bmad-output, _bmad-frobnicate)", (t) => {
  const root = fixture(t);
  // _bmad-output is declared not-a-skill, so on its own it would pass either way; the second
  // path is undeclared and fails the moment the lookbehind is dropped from BMAD_TOKEN_RE.
  write(root, "skills/l3io-pm-execute/steps/x-underscore.md",
        "Reports land in `{project-root}/_bmad-output/` and `{project-root}/_bmad-frobnicate/`.\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test("check 16: not-a-skill tokens are skipped via their status", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/x-not-a-skill.md",
        "The `bmad-defer:` marker in a `bmad-l3io-extensions` checkout.\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test("check 16: a not-a-skill entry without a reason is caught", (t) => {
  const root = fixture(t);
  editInventory(root, (inv) => {
    delete inv.skills.find((e) => e.name === "bmad-defer").reason;
  });
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /'bmad-defer' is not-a-skill but gives no reason/);
});

test("check 16: a fallback naming an undeclared skill is caught", (t) => {
  const root = fixture(t);
  editInventory(root, (inv) => {
    inv.skills.find((e) => e.name === "bmad-ux").fallback = "bmad-nonexistent";
  });
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /'bmad-ux' falls back to 'bmad-nonexistent', not declared/);
});

// Case 15 — the probe arm. Without this the check rejects the resolution blocks that
// implement tolerance, i.e. it would forbid the fix it exists to protect.
test("check 16: an existence probe naming a removed skill is allowed", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/x-probe.md",
        "```bash\nls {project-root}/.claude/skills/bmad-architect/SKILL.md 2>/dev/null\n```\n");
  const r = run(root);
  assert.equal(r.status, 0, "a probe line cannot dispatch anything; it must pass");
});

// The probe arm has the same substring hole the replaced_by arm was hardened against: a bare
// line.includes("ls ") is satisfied by "tools ", "details " or "controls ". Case 15 passes under
// both the weak and the strong predicate, so without this test a revert would be silent.
test("check 16: a word ending in 'ls' does not make a dispatch line a probe", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/x-tools.md",
        "Check the tools installed under `.claude/skills/` before spawning `bmad-architect`.\n");
  const r = run(root);
  assert.equal(r.status, 1, "'tools ' plus '.claude/' is not an `ls` probe");
  assert.match(r.stderr, /dispatches removed skill 'bmad-architect'/);
});

// Case 16 — the token-boundary hole. bmad-ux-review's replaced_by is bmad-ux, which is a
// SUBSTRING of it, so a naive includes() check would let the guard pass its own worst case.
test("check 16: replaced_by must match as a token, not a substring", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/x-substring.md",
        "Invoke `bmad-ux-review` with the story files.\n");
  const r = run(root);
  assert.equal(r.status, 1, "bmad-ux-review contains 'bmad-ux'; substring matching would pass this");
  assert.match(r.stderr, /dispatches removed skill 'bmad-ux-review'/);
});

const INVENTORY = path.join("skills", "l3io-util-doctor", "assets", "bmad-dependencies.json");

function setStatus(root, name, patch) {
  const p = path.join(root, INVENTORY);
  const inv = JSON.parse(fs.readFileSync(p, "utf8"));
  const e = inv.skills.find((x) => x.name === name);
  assert.ok(e, `${name} must exist in the inventory fixture`);
  Object.assign(e, patch);
  fs.writeFileSync(p, JSON.stringify(inv, null, 2));
  return p;
}

test("check 16 accepts a deprecated entry carrying deprecated_in and replaced_by", (t) => {
  const root = fixture(t);
  setStatus(root, "bmad-create-story",
    { status: "deprecated", deprecated_in: "6.12.0", replaced_by: "bmad-build",
      removed_in: undefined });
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

test("check 16 rejects a deprecated entry missing deprecated_in", (t) => {
  const root = fixture(t);
  setStatus(root, "bmad-create-story",
    { status: "deprecated", replaced_by: "bmad-build", deprecated_in: undefined,
      removed_in: undefined });
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /is deprecated but lacks replaced_by\/deprecated_in/);
});

test("check 16 fails when a directive prefers a deprecated skill", (t) => {
  const root = fixture(t);
  setStatus(root, "bmad-dev-story",
    { status: "deprecated", deprecated_in: "6.12.0", replaced_by: "bmad-build",
      removed_in: undefined });
  write(root, "skills/l3io-pm-execute/steps/scope-attack.md",
    "bind `{dev_agent}` = the legacy `bmad-dev-story` and spawn that skill\n");
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /prefers deprecated skill 'bmad-dev-story'/);
});

test("check 16 still allows a bare existence probe of a deprecated skill", (t) => {
  const root = fixture(t);
  setStatus(root, "bmad-dev-story",
    { status: "deprecated", deprecated_in: "6.12.0", replaced_by: "bmad-build",
      removed_in: undefined });
  write(root, "skills/l3io-pm-execute/steps/probe-only.md",
    "ls {project-root}/.claude/skills/bmad-dev-story/SKILL.md 2>/dev/null\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// Scope attack: both tests above phrase the binding with a verb (bind/spawn/...). A binding
// phrased as a bare `{placeholder}` = assignment carries none of those verbs and would escape
// PREFERENCE_RE alone — this is exactly how `steps/plan/step-03-story-elaboration.md:66` stayed
// invisible to fix-round-1's implementation. Planted in a different skill (l3io-pm-plan) than
// the verb-phrased tests above, so this also proves the check isn't scoped to one skill's files.
test("check 16 scope attack: an assignment-style binding with no verb is still caught", (t) => {
  const root = fixture(t);
  setStatus(root, "bmad-dev-story",
    { status: "deprecated", deprecated_in: "6.12.0", replaced_by: "bmad-build",
      removed_in: undefined });
  write(root, "skills/l3io-pm-plan/steps/assignment-attack.md",
    "A path printed → `{dev_agent}` = the legacy `bmad-dev-story`. Nothing printed →\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /prefers deprecated skill 'bmad-dev-story'/);
});

// Scope attack: a Markdown heading naming a deprecated skill carries neither a binding verb
// nor a `=` assignment, but still scopes an entire section to that skill — the real-tree case
// was `l3io-arch-review/assets/customize-architect.md:21`.
test("check 16 scope attack: a heading naming a deprecated skill is still caught", (t) => {
  const root = fixture(t);
  setStatus(root, "bmad-dev-story",
    { status: "deprecated", deprecated_in: "6.12.0", replaced_by: "bmad-build",
      removed_in: undefined });
  write(root, "skills/l3io-arch-review/assets/heading-attack.md",
    "## Overlay for the implementer — legacy `bmad-dev-story`\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /prefers deprecated skill 'bmad-dev-story'/);
});

// ---- check 17 (pep723-invocation) ----

test("check 17: a PEP-723 helper invoked with python3 is caught", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/bad-invocation.md",
    "```bash\npython3 {pm_status} set-status --state-root x\n```\n");
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /invokes a PEP-723 script with python3/);
});

test("check 17: uv run of the same helper passes", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/good-invocation.md",
    "```bash\nuv run {pm_status} set-status --state-root x\n```\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

test("check 17: the documented python3 fallback line is allowed", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/fallback.md",
    "If `uv` is unavailable, use `python3` instead.\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// The word-boundary case from the design table: "--use-python3" must not be mistaken for the
// `python3` invocation token, and a script path invoked correctly with `uv run` must not trip
// the check just because it also ends in `.py`.
test("check 17: word boundary holds and an unrelated uv run line passes", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/decoys.md",
    "The option --use-python3 {pm_status} is not real.\n\n" +
    "```bash\nuv run scripts/check.py --flag\n```\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// The fallback test above never exercises the qualifier branch: PY_INVOKE_RE never matches
// "python3` instead." at all (a backtick, not whitespace, follows `python3`), so that test
// passing proves nothing about the tolerance itself. This one plants a line where PY_INVOKE_RE
// DOES match a real invocation, with the uv/unavailable qualifier on the same line, so the
// exemption branch must actually fire for the line to pass.
test("check 17: a same-line uv-unavailable qualifier exempts a real invocation", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/same-line-fallback.md",
    "If `uv` is unavailable, run `python3 {pm_status} verify --state-root x` instead.\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// Scope attack: every other check-17 test above plants under skills/l3io-pm-execute/steps/.
// This one plants under a different skill AND a different subdirectory (assets/, not steps/)
// to prove walkMarkdown("skills") actually reaches there rather than the check having been
// implicitly scoped to steps/ files by every test happening to live in one.
test("check 17 scope attack: a violation under a different skill's assets/ is caught", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-util-doctor/assets/scope-attack.md",
    "```bash\npython3 {skill-root}/scripts/detect-platform.py {project-root}\n```\n");
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /scope-attack\.md:\d+: invokes a PEP-723 script with python3/);
});

// Scope attack: the scan set was widened a second time to LIVE_DOCS. The rule was enforced in
// the files agents read (skills/**) and unenforced in the files PEOPLE read: docs/
// estimation-guide.md shipped fifteen bare `python3 {pm_status} ...` invocations of a script
// whose PEP-723 header declares ruamel.yaml, and two more sat in the arch and sec reference
// docs. These plant the same shape in a BRAND-NEW file under docs/ and in README.md, so the
// widened corpus has to be derived (LIVE_DOCS) rather than a hand-kept list of the docs that
// happened to be wrong on the day.
test("check 17 scope attack: a violation in a new file under docs/ is caught", (t) => {
  const root = fixture(t);
  write(root, "docs/brand-new-guide.md",
    "# New guide\n\n```bash\npython3 {pm_status} set-status --state-root x\n```\n");
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /brand-new-guide\.md:\d+: invokes a PEP-723 script with python3/);
});

test("check 17 scope attack: a violation in README.md is caught", (t) => {
  const root = fixture(t);
  write(root, "README.md", "\n```bash\npython3 {pm_status} verify --state-root x\n```\n", true);
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /README\.md:\d+: invokes a PEP-723 script with python3/);
});

// The other side of the same scope claim: docs/superpowers/** is a historical record and is
// EXCLUDED on purpose -- rewriting a shipped design spec to match today would falsify it. A
// violation planted there must NOT fail, or the exclusion is a comment rather than a fact.
test("check 17: docs/superpowers/** is excluded, and a violation there does not fail", (t) => {
  const root = fixture(t);
  write(root, "docs/superpowers/specs/2020-01-01-historical.md",
    "# Historical\n\n```bash\npython3 {pm_status} set-status --state-root x\n```\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

// Scope attack: the scan set was widened to .github/workflows/** because a real CI step
// once installed a dependency into the runner's ambient interpreter and invoked a PEP-723
// script (test-pm-status.py) with plain `python3`, while every sibling step in the same
// workflow used `uv run` -- and nothing caught it because this check only ever walked
// skills/. This plants the same shape of violation directly in the workflow file to prove
// the widened scope actually reaches it, not just skills/.
test("check 17 scope attack: a bare python3 invocation in .github/workflows/ is caught", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/checks.yml",
    "    - name: bad step\n      run: python3 skills/_shared/tests/test-pm-status.py\n",
    /* append */ true);
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /\.github\/workflows\/checks\.yml:\d+: invokes a PEP-723 script with python3/);
});

// A `uv run --with <extra-deps> python3 <script>.py` invocation is uv choosing and managing
// the interpreter itself (used by test-audit-backlog.py, test-bmad-deps.py, and
// test-spec-align.py's real CI steps, which need dependencies beyond their own header) --
// the opposite of the bare python3 this check exists to catch. Confirms the widened scope
// does not turn every real, already-passing `uv run ... python3 ...` CI line into a false
// positive.
test("check 17: uv run managing its own python3 interpreter in a workflow is not a violation", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/checks.yml",
    "    - name: extra-deps step\n" +
    "      run: uv run -q --with 'ruamel.yaml>=0.18' python3 skills/_shared/tests/test-pm-status.py\n",
    /* append */ true);
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// Fix round 1, F-1: the position-only exemption above ("uv run" appears anywhere earlier on
// the line) was defeated by a real checker run planting these two exact strings, both of
// which passed (exit 0) under the old logic. Both are real, cheap edits: `uv run python3
// <script>.py` is uv invoking the *interpreter*, not the script, so the header is never read
// -- the original defect, verbatim, wearing a `uv run` prefix. `uv run A.py && python3 B.py`
// is a second command on the same line, exempted only because an unrelated `uv run` preceded
// it. Both must now fail.
test("check 17 F-1: `uv run python3 <script>.py` does not honour the header and must fail", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/checks.yml",
    "    - name: fix-round-1 regression a\n" +
    "      run: uv run python3 skills/_shared/tests/test-pm-status.py\n",
    /* append */ true);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /invokes a PEP-723 script with python3/);
});

test("check 17 F-1: a `python3` command chained after an unrelated `uv run` must fail", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/checks.yml",
    "    - name: fix-round-1 regression b\n" +
    "      run: uv run scripts/a.py && python3 skills/_shared/tests/test-pm-status.py\n",
    /* append */ true);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /invokes a PEP-723 script with python3/);
});

// The three real lines in .github/workflows/checks.yml that must keep passing: each is a
// single command, starts with `uv run`, and carries a `--with` for a dependency beyond the
// script's own PEP-723 header. Written out individually (rather than relying only on "an
// unmodified copy passes") so the exemption's positive cases are pinned as explicitly as its
// negative ones.
for (const [label, line] of [
  ["test-spec-align.py (multiple --with flags)",
    "uv run -q --with 'markdown-it-py>=3' --with 'mdit-py-plugins>=0.4' --with 'ruamel.yaml>=0.18' " +
    "--with 'unidiff>=0.7' --with 'tenacity>=8' python3 skills/_shared/tests/test-spec-align.py"],
  ["test-audit-backlog.py",
    "uv run -q --with 'ruamel.yaml>=0.18' python3 skills/l3io-util-doctor/scripts/tests/test-audit-backlog.py"],
  ["test-bmad-deps.py",
    "uv run -q --with 'ruamel.yaml>=0.18' python3 skills/l3io-util-doctor/scripts/tests/test-bmad-deps.py"],
]) {
  test(`check 17 F-1: real legitimate line (${label}) still passes`, (t) => {
    const root = fixture(t);
    write(root, ".github/workflows/checks.yml",
      `    - name: legitimate ${label}\n      run: ${line}\n`,
      /* append */ true);
    const r = run(root);
    assert.equal(r.status, 0, r.stderr);
  });
}

// Fix round 2, N-1: `--with` was matched anywhere on the whole command, not anchored before
// the python3 token, so F-1's own defect string still passed with a trailing, inert flag
// appended -- nothing is provisioned; `--with-coverage` is a script argument sitting AFTER
// python3, not a uv flag before it, and is not even a real uv flag name.
test("check 17 N-1: `uv run python3 <script>.py --with-coverage` still does not honour the header", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/checks.yml",
    "    - name: fix-round-2 regression n1a\n" +
    "      run: uv run python3 skills/_shared/tests/test-pm-status.py --with-coverage\n",
    /* append */ true);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /invokes a PEP-723 script with python3/);
});

// A single `&` (background) was not in the split set, so a second command joined by `&`
// inherited an unrelated `uv run --with` that precedes it on the same line.
test("check 17 N-1: a `python3` command joined by a single `&` must fail", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/checks.yml",
    "    - name: fix-round-2 regression n1c\n" +
    "      run: uv run --with 'ruamel.yaml>=0.18' A.py & python3 skills/_shared/tests/test-pm-status.py\n",
    /* append */ true);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /invokes a PEP-723 script with python3/);
});

// `--with-editable` and `--with-requirements` are real uv flags (uv genuinely provisions an
// environment for them), so a command using one, correctly positioned before the python3
// token, must still be exempt -- the fix narrows the match to real flag tokens, it does not
// remove the family.
test("check 17 N-1: a real `--with-editable` flag before python3 still passes", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/checks.yml",
    "    - name: fix-round-2 legitimate with-editable\n" +
    "      run: uv run --with-editable . python3 skills/_shared/tests/test-pm-status.py\n",
    /* append */ true);
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// Fix round 2, N-2: the `uv run` anchor was too strict for two ordinary GitHub Actions
// spellings of the exact line the exemption exists to admit, both exiting 1 (CI red)
// although both do the right thing.
test("check 17 N-2: the `- run:` step form (no separate `- name:`) still passes", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/checks.yml",
    "    - run: uv run -q --with 'ruamel.yaml>=0.18' python3 skills/_shared/tests/test-pm-status.py\n",
    /* append */ true);
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

test("check 17 N-2: a leading per-step environment-variable assignment still passes", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/checks.yml",
    "    - name: fix-round-2 legitimate env prefix\n" +
    "      run: UV_CACHE_DIR=/tmp uv run -q --with 'ruamel.yaml>=0.18' python3 skills/_shared/tests/test-pm-status.py\n",
    /* append */ true);
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// Fix round 2, N-3: PY_FALLBACK_QUALIFIER exempted the whole line when it contained the word
// "fallback" or "uv ... unavailable" -- a tolerance meant for markdown prose describing an
// escape hatch, not for an executable workflow `run:` line, where it was the cheapest
// possible silencer for a bare python3 invocation. Now scoped to markdown only.
test("check 17 N-3: a `# fallback` comment in a workflow run: line does not exempt it", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/checks.yml",
    "    - name: fix-round-2 regression n3\n" +
    "      run: python3 skills/_shared/tests/test-pm-status.py  # fallback until uv lands\n",
    /* append */ true);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /invokes a PEP-723 script with python3/);
});

// The same qualifier must still exempt real markdown prose describing the documented
// `uv`-unavailable fallback -- confirms the N-3 scoping is by file type, not a removal.
test("check 17 N-3: the documented python3 fallback in markdown prose still passes", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/fallback-still-allowed.md",
    "If `uv` is unavailable, use `python3 {pm_status} verify --state-root x` instead.\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// Fix round 3, M-1: PY_INVOKE_RE required the .py path (or {pm_status}/{spec_align}) to be
// python3's FIRST argument, so an interpreter flag or a minor-version suffix between
// `python3` and the script path defeated the predicate entirely -- no exemption logic even
// runs when the pattern never matches in the first place, making these cheaper than every
// string the first three fix rounds closed.
for (const [label, line] of [
  ["a `-u` flag", "python3 -u skills/_shared/tests/test-pm-status.py"],
  ["a `-X utf8` flag (flag + its own separate argument)",
    "python3 -X utf8 skills/_shared/tests/test-pm-status.py"],
  ["a `python3.12` minor-version suffix", "python3.12 skills/_shared/tests/test-pm-status.py"],
]) {
  test(`check 17 M-1: python3 with ${label} still does not honour the header`, (t) => {
    const root = fixture(t);
    write(root, ".github/workflows/checks.yml",
      `    - name: fix-round-3 regression\n      run: ${line}\n`,
      /* append */ true);
    const r = run(root);
    assert.equal(r.status, 1, r.stdout);
    assert.match(r.stderr, /invokes a PEP-723 script with python3/);
  });
}

// Positive control: a provisioned line using an interpreter flag must still pass -- the
// widening happens INSIDE the match, before the python3 token the exemption's beforeMatch
// looks at, so it must not defeat the exemption.
test("check 17 M-1: a provisioned `uv run --with ... python3 -u <script>.py` still passes", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/checks.yml",
    "    - name: fix-round-3 legitimate\n" +
    "      run: uv run --with 'ruamel.yaml>=0.18' python3 -u skills/_shared/tests/test-pm-status.py\n",
    /* append */ true);
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// Negative control: mentioning python3 with no .py/{helper} argument at all must still not
// match -- confirms the widening did not turn PY_INVOKE_RE into a bare "python3" scan.
test("check 17 M-1: python3 with no script argument does not trip the check", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/checks.yml",
    "    - name: fix-round-3 no-op\n      run: python3 --version\n",
    /* append */ true);
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// Fix round 4, R-1: M-1's token skip (`(?:\S+\s+)*?`) accepted ANY intervening tokens, not
// just interpreter flags, so ordinary English prose that mentions `python3` and separately
// mentions some `.py` file matched -- a false red on correct documentation, in a scan whose
// main corpus is prose. Each line below is a realistic markdown sentence, planted in the
// markdown corpus (not a workflow) where the fallback tolerance is also live, and none of
// them carries a uv/unavailable or `fallback` qualifier: they must pass on the invocation
// predicate alone, not on the exemption.
for (const [label, line] of [
  ["a semicolon-joined sentence", "prose: python3 is required; see setup.py for details"],
  ["a plain `and then` sentence", "Install python3 and then edit pyproject.py"],
  ["a flag with no script argument", "python3 --version"],
  ["a sentence break before an unrelated uv run",
    "You need python3. Run the suite with uv run foo.py"],
  ["a later-in-the-sentence generated file",
    "run python3 later; the file build.py is generated"],
  // The five above are the reported repro set, and only the second of them actually turned
  // CI red: the two semicolon-joined ones are masked by COMMAND_SPLIT_RE (which splits on
  // `;`) and the other two never matched even the round-3 pattern, so on their own they are
  // not mutation-discriminating. The four below are realistic prose with NO shell-split
  // character anywhere on the line, so nothing but the invocation predicate itself can save
  // them -- each one fails if PY_INVOKE_RE loses the flag-shape constraint.
  ["a pip bootstrap sentence",
    "Run python3 -m pip install -r requirements.txt before running build.py"],
  ["a parenthetical version note", "python3 (3.11+) is needed to run a.py"],
  ["a dashed aside", "We dropped python3 support - see migrate.py"],
  ["a bare version number after the interpreter",
    "install python3 3.12 then run a.py with uv"],
]) {
  test(`check 17 R-1: prose with ${label} is not a python3 invocation`, (t) => {
    const root = fixture(t);
    write(root, "skills/l3io-pm-execute/steps/round4-prose.md", `${line}\n`);
    const r = run(root);
    assert.equal(r.status, 0, r.stderr + r.stdout);
  });
}

// Positive controls for the SAME change: constraining the skip to flag shapes must not lose
// any real invocation. These are the shapes the flag constraint is most likely to drop --
// an absolute interpreter path (no flags at all), two stacked flags where the first carries
// its own argument and the second does not (only backtracking resolves that ambiguity), and
// a flag run ending at a `{...}` helper token rather than a `.py` path.
for (const [label, line] of [
  ["an absolute interpreter path", "/usr/bin/python3 skills/_shared/tests/test-pm-status.py"],
  ["`-X utf8 -u` (argful flag then argless flag)",
    "python3 -X utf8 -u skills/_shared/tests/test-pm-status.py"],
  ["`-m` with a module argument",
    "python3 -m pytest skills/_shared/tests/test-pm-status.py"],
]) {
  test(`check 17 R-1: python3 with ${label} still does not honour the header`, (t) => {
    const root = fixture(t);
    write(root, ".github/workflows/checks.yml",
      `    - name: fix-round-4 regression\n      run: ${line}\n`,
      /* append */ true);
    const r = run(root);
    assert.equal(r.status, 1, r.stdout);
    assert.match(r.stderr, /invokes a PEP-723 script with python3/);
  });
}

// The `{...}` helper-token branch behind a flag run, in the markdown corpus where those
// tokens actually appear. Guards the same branch as the workflow cases above against a
// flag-shape constraint that only ever got exercised on `.py` paths.
test("check 17 R-1: python3 with flags before a {spec_align} helper token is caught", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/round4-helper.md",
    "```bash\npython3 -X utf8 -u {spec_align} build\n```\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /round4-helper\.md:\d+: invokes a PEP-723 script with python3/);
});

// ---- check 17, rebuilt on real parsers (Task 17) ----
//
// The workflow half of check 17 no longer reads a YAML file line by line, and no longer
// splits a command with /&&|;|\||&/. The file is parsed with `yaml`, each `run:` script is
// parsed with `mvdan-sh`, and the rule is applied to the resulting argv. Every string below
// was MEASURED against the previous checker earlier in this plan: the bypasses exited 0 and
// should not have, the false reds exited 1 and should not have. None of them is reachable by
// a better regex -- each needs a parser to know what is quoted, what is a substitution, what
// is an assignment prefix and what is a wrapper command.
const TASK17_BYPASSES = [
  ["a quoted `&` inside an env-assignment prefix",
    "NOTE='x & uv run --with y' python3 skills/_shared/tests/test-pm-status.py"],
  ["a quoted `&&` inside an env-assignment prefix",
    "NOTE='x && uv run --with y' python3 skills/_shared/tests/test-pm-status.py"],
  ["a quoted `;` inside an env-assignment prefix",
    "NOTE='x ; uv run --with y' python3 skills/_shared/tests/test-pm-status.py"],
  ["a double-quoted `&&` inside an env-assignment prefix",
    'NOTE="x && uv run --with y" python3 skills/_shared/tests/test-pm-status.py'],
  // These two are the deliberate over-approximation: the shell would run `echo`/`grep` and
  // never python3, so the check reports them with the WORDING that says exactly that, rather
  // than claiming an invocation that does not happen. (Fix round 1, L-2.)
  ["a decoy `uv run --with` quoted as an echo argument",
    "echo 'a & uv run --with y' python3 skills/_shared/tests/test-pm-status.py",
    /contains an unquoted `python3 [^`]+` sequence outside a provisioned `uv run`/],
  ["a decoy `uv run --with` quoted as a grep pattern",
    "grep -q 'x | uv run --with y' python3 skills/_shared/tests/test-pm-status.py",
    /contains an unquoted `python3 [^`]+` sequence outside a provisioned `uv run`/],
  ["a `$( )` substitution under an otherwise-provisioned uv run",
    "uv run --with 'x' echo \"$(python3 skills/_shared/tests/test-pm-status.py)\""],
  ["a backtick substitution under an otherwise-provisioned uv run",
    "uv run --with 'x' echo \"`python3 skills/_shared/tests/test-pm-status.py`\""],
  ["a substitution beside a genuinely provisioned invocation",
    "uv run --with 'x' python3 A.py --arg \"$(python3 skills/_shared/tests/test-pm-status.py)\""],
  ["a shell variable standing in for the interpreter",
    "PY=python3; $PY skills/_shared/tests/test-pm-status.py"],
];

for (const [label, line, expected] of TASK17_BYPASSES) {
  test(`check 17 Task 17: ${label} no longer bypasses the check`, (t) => {
    const root = fixture(t);
    write(root, ".github/workflows/checks.yml",
      `    - name: task-17 bypass\n      run: ${line}\n`,
      /* append */ true);
    const r = run(root);
    assert.equal(r.status, 1, r.stdout);
    assert.match(r.stderr, expected ?? /invokes a PEP-723 script with python3/);
  });
}

// A literal `\n` inside a DOUBLE-QUOTED YAML scalar is a real newline once the document is
// parsed, so it is two commands -- the first a legitimate `uv run`, the second a bare python3
// invocation that the old line-at-a-time read could never see as separate.
test("check 17 Task 17: a literal \\n inside a double-quoted run: scalar is two commands", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/checks.yml",
    "    - name: task-17 escaped newline\n" +
    '      run: "uv run A.py\\npython3 skills/_shared/tests/test-pm-status.py"\n',
    /* append */ true);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /invokes a PEP-723 script with python3/);
});

// The mirror set: correct, provisioned invocations the old checker reported RED. A guard that
// cries wolf gets switched off, so these are pinned as explicitly as the bypasses above.
const TASK17_FALSE_REDS = [
  ["a `timeout` wrapper",
    "timeout 600 uv run --with 'x' python3 skills/_shared/tests/test-pm-status.py"],
  ["an `env VAR=value` wrapper",
    "env FOO=1 uv run --with 'x' python3 skills/_shared/tests/test-pm-status.py"],
  ["a `sudo` wrapper",
    "sudo uv run --with 'x' python3 skills/_shared/tests/test-pm-status.py"],
  ["a `nice -n 10` wrapper",
    "nice -n 10 uv run --with 'x' python3 skills/_shared/tests/test-pm-status.py"],
  ["an if/then shell block",
    "if [ -f x ]; then uv run --with 'x' python3 skills/_shared/tests/test-pm-status.py; fi"],
  ["two spaces between `uv` and `run`",
    "uv  run --with 'x' python3 skills/_shared/tests/test-pm-status.py"],
  ["a `|` inside a --with value",
    "uv run --with 'a|b' python3 skills/_shared/tests/test-pm-status.py"],
  ["an `&` inside a --with URL",
    "uv run --with 'pkg @ https://host/x.whl?a=1&b=2' python3 skills/_shared/tests/test-pm-status.py"],
];

for (const [label, line] of TASK17_FALSE_REDS) {
  test(`check 17 Task 17: ${label} is not a violation`, (t) => {
    const root = fixture(t);
    write(root, ".github/workflows/checks.yml",
      `    - name: task-17 false red\n      run: ${line}\n`,
      /* append */ true);
    const r = run(root);
    assert.equal(r.status, 0, r.stderr);
  });
}

// The provisioning flag must sit BETWEEN `run` and the interpreter. A real `--with` spelled
// AFTER the script is a script argument, not a uv flag, and provisions nothing.
//
// Found by mutation: replacing `argv.slice(2, pyIndex)` with `argv.slice(2)` -- dropping the
// position requirement entirely -- left the whole suite green, because N-1's existing case
// (`--with-coverage`) is rejected on the flag NAME and never exercised the position. This is
// the case that does.
test("check 17 Task 17: a real `--with` after the script does not provision anything", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/checks.yml",
    "    - name: task-17 trailing with\n" +
    "      run: uv run python3 skills/_shared/tests/test-pm-status.py --with 'ruamel.yaml>=0.18'\n",
    /* append */ true);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /invokes a PEP-723 script with python3/);
});

// The whole command inside a quoted YAML scalar: the old checker stripped the `run:` key
// textually and was then left with a leading quote character, so its `^uv run` anchor could
// never match. A YAML parser hands over the scalar's VALUE, with no quote to trip over.
test("check 17 Task 17: a provisioned command inside a single-quoted YAML scalar passes", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/checks.yml",
    "    - name: task-17 single-quoted scalar\n" +
    `      run: 'uv run --with "x" python3 skills/_shared/tests/test-pm-status.py'\n`,
    /* append */ true);
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

test("check 17 Task 17: a provisioned command inside a double-quoted YAML scalar passes", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/checks.yml",
    "    - name: task-17 double-quoted scalar\n" +
    `      run: "uv run --with 'x' python3 skills/_shared/tests/test-pm-status.py"\n`,
    /* append */ true);
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// A multi-line `run: |` block is one script, not a sequence of unrelated lines: the
// provisioned command on its first line must not exempt the bare one on its second, and the
// offence must be reported against the second line's own file position.
test("check 17 Task 17: a block scalar is read as a script, with per-line attribution", (t) => {
  const root = fixture(t);
  const before = fs.readFileSync(path.join(root, ".github/workflows/checks.yml"), "utf8");
  const offendingLine = before.split("\n").length + 3;
  write(root, ".github/workflows/checks.yml",
    "    - name: task-17 block scalar\n" +
    "      run: |\n" +
    "        uv run --with 'x' python3 skills/_shared/tests/test-pm-status.py\n" +
    "        python3 skills/_shared/tests/test-write-module-config.py\n",
    /* append */ true);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr,
    new RegExp(`checks\\.yml:${offendingLine}: invokes a PEP-723 script with python3`));
});

// Both new parsers fail CLOSED. A workflow file the YAML parser cannot read, or a `run:` body
// the shell parser cannot read, is reported -- never skipped, which would silently shrink the
// set this check examines (repo CLAUDE.md §4).
test("check 17 Task 17: a workflow file that is not valid YAML is reported, not skipped", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/broken.yml", "jobs:\n  a: [unclosed\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /broken\.yml:.*does not parse as YAML/);
});

test("check 17 Task 17: a run: body that is not valid shell is reported, not skipped", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/badshell.yml",
    "name: bad\non: [push]\njobs:\n  a:\n    runs-on: ubuntu-latest\n" +
    "    steps:\n    - run: 'if [ -f x ]; then'\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /badshell\.yml:\d+: this run: script does not parse as shell/);
});

// Scope attack on the rebuild: the workflow set is still derived by listing
// .github/workflows/, so a violation in a workflow file this repo does not have yet is still
// found. Plants in a NEW file rather than appending to checks.yml, which every other
// workflow test above uses.
test("check 17 Task 17 scope attack: a violation in a new workflow file is caught", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/nightly.yml",
    "name: nightly\non: [schedule]\njobs:\n  a:\n    runs-on: ubuntu-latest\n" +
    "    steps:\n    - run: python3 skills/_shared/tests/test-pm-status.py\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /nightly\.yml:\d+: invokes a PEP-723 script with python3/);
});

// The markdown half keeps PY_INVOKE_RE as its candidate finder precisely so it keeps reaching
// decoration that is not shell at all: no shell parser accepts a markdown table row, and a list
// bullet lexes with `-` as argv[0]. Both must stay caught -- and each must keep its OWN failure
// wording, which is pinned by the M-7 pair in the fix-round-2 block below. (These two shapes
// were a single loop asserting "either wording", which left the direct/indirect split
// invertible with the suite green.)

// ---- check 17, python3's option arity is pinned, not just documented (fix round 1, M-2) ----
//
// `pythonTarget()` models python3's own CLI so it can tell an interpreter flag from the script
// it eventually runs. Two of those behaviours were asserted in the check header, in the commit
// message AND in docs/adr/0007 -- and tested nowhere: deleting `if (tok === "-c") return null;`
// left the whole suite green while flipping a real verdict. That is the same class of hole the
// M6 mutation found, so the sweep is finished here rather than left for the next reviewer.

// `-c` runs a command STRING. A `.py` path after it is sys.argv[1], never executed, so no
// PEP-723 header is bypassed and this must stay exit 0. Deleting the `-c` line makes it red.
test("check 17 M-2: `python3 -c 'code' <script>.py` executes no script and is not a violation", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/checks.yml",
    "    - name: m-2 dash-c\n" +
    "      run: python3 -c 'import sys; print(sys.version)' skills/_shared/tests/test-pm-status.py\n",
    /* append */ true);
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// `-m <runner>` is judged by the runner's FIRST non-flag argument -- which is what separates
// `-m pytest <script>.py` (caught, pinned by the R-1 positive control above) from
// `-m pip install … build.py`, where `build.py` is a package-name argument to `install` and
// nothing executes it. A rule that scanned for ANY `.py` among the module's arguments would
// turn this ordinary line red.
test("check 17 M-2: `python3 -m pip install … build.py` runs no script and is not a violation", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/checks.yml",
    "    - name: m-2 dash-m\n" +
    "      run: python3 -m pip install -r requirements.txt --target build.py\n",
    /* append */ true);
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// After `-m`, the remaining flags belong to the MODULE, so python3's own arity table has to
// stop applying to them. `-X` is a python3 option that takes a separate value; as a runner's
// flag it takes none, and applying python3's arity would swallow the script path behind it and
// miss the invocation entirely. (`-W`, `-Q` and `-X` are all plausible third-party runner flag
// names, which is why this is a hazard and not a curiosity.) This is the case that pins the
// `-m` branch's existence: without it, `-m` falls through to PY_VALUE_OPTS and this goes green.
test("check 17 M-2: after `-m`, python3's flag arity stops applying to the runner's own flags", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/checks.yml",
    "    - name: m-2 runner flag\n" +
    "      run: python3 -m pytest -X skills/_shared/tests/test-pm-status.py\n",
    /* append */ true);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /invokes a PEP-723 script with python3/);
});

// ---- check 17, what the third mutation sweep found unpinned (fix round 2) ----
//
// An 81-mutation sweep over every decision point in check 17 found 21 mutations that stayed
// GREEN while changing a real verdict. None was a defect in the checker -- every one was a gap
// in what this suite PINS. The tests below close the ones that guard a recorded historical
// defect or a scope boundary. Each is written against a named mutation, and each was confirmed
// to go RED under it.
//
// Source-derived, never hand-listed: the option and helper-token sets below are read back out
// of scripts/check-docs.mjs. A hand-kept copy would drift from the table it mirrors in exactly
// the way the table drifted from its tests (repo CLAUDE.md §4).

function checkDocsSource() {
  return fs.readFileSync(path.join(REPO, "scripts", "check-docs.mjs"), "utf8");
}

// Every option in PY_VALUE_OPTS, read from the literal itself.
function pyValueOpts() {
  const m = checkDocsSource().match(/const PY_VALUE_OPTS = new Set\(\[([\s\S]*?)\]\);/);
  assert.ok(m, "PY_VALUE_OPTS literal not found in check-docs.mjs -- has it been renamed? " +
    "This test derives its scope from that set and must fail rather than silently test nothing");
  const opts = [...m[1].matchAll(/"([^"]+)"/g)].map((x) => x[1]);
  assert.ok(opts.length > 0, "PY_VALUE_OPTS parsed as empty");
  for (const o of opts) assert.match(o, /^-/, `PY_VALUE_OPTS entry '${o}' is not an option`);
  return opts;
}

// An option that pythonTarget() handles with a branch of its own (`-c`, `-m` today) is not
// decided by the arity table, so the "still finds the script behind it" case does not apply to
// it. Derived by looking for that branch, not by naming the options.
function hasOwnBranch(opt) {
  return new RegExp(`if \\(tok === "${opt.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}"\\)`)
    .test(checkDocsSource());
}

function workflowStep(root, label, body) {
  write(root, ".github/workflows/checks.yml", `    - name: ${label}\n      run: ${body}\n`, true);
}

// ---- M-3: the provisioning flag's NAME, not just its position ----
//
// The existing N-1 test puts `--with-coverage` AFTER the script, so it is rejected on position
// and the flag name is never consulted. Widening UV_PROVISION_FLAG_RE to a bare `^--with` is
// therefore invisible -- and `--with-coverage` in front of the interpreter is the exact bypass
// three earlier fix rounds were spent closing. uv has no such flag; nothing is provisioned.
test("check 17 M-3: `--with-coverage` before the interpreter provisions nothing", (t) => {
  const root = fixture(t);
  workflowStep(root, "m-3 flag name",
    "uv run --with-coverage python3 skills/_shared/tests/test-pm-status.py");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /invokes a PEP-723 script with python3/);
});

test("check 17 M-3: a real `--with` in the same position still provisions", (t) => {
  const root = fixture(t);
  workflowStep(root, "m-3 control",
    "uv run --with 'ruamel.yaml>=0.18' python3 skills/_shared/tests/test-pm-status.py");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// ---- M-4: every entry in PY_VALUE_OPTS, both directions ----
//
// `-c`, `-m` and `-X` were held by the M-2 tests; removing `-W`, `-Q` or
// `--check-hash-based-pycs` from the set was GREEN, and each one hides a real invocation by
// letting the option's own value be mistaken for the script.
//
// MEMBERSHIP FIRST, and this is the load-bearing part. The behaviour tests below TEMPLATE over
// whatever PY_VALUE_OPTS contains, so a newly added option is exercised without being typed
// here -- but that alone cannot catch an option being DELETED, because the deletion removes its
// own test and the suite passes vacuously. (Measured: removing `-W` and re-running left the
// templated tests green, having silently generated one fewer case.) So the set's membership is
// asserted against python3's documented CLI, which is the external source of truth here -- it
// belongs to CPython, not to this repo, and changes on CPython's release schedule rather than
// ours. Adding an option to the model without adding it here is caught the same way.
const CPYTHON_VALUE_TAKING_OPTIONS = ["--check-hash-based-pycs", "-W", "-X", "-Q", "-c", "-m"];

test("check 17 M-4: PY_VALUE_OPTS matches python3's documented value-taking options", () => {
  assert.deepEqual(
    pyValueOpts().slice().sort(),
    CPYTHON_VALUE_TAKING_OPTIONS.slice().sort(),
    "PY_VALUE_OPTS and python3's value-taking options disagree. Removing one lets that " +
    "option's own value be mistaken for the script, hiding a real invocation; adding one " +
    "that python3 does not have swallows the script path after it. Update both, or neither.",
  );
});

for (const opt of pyValueOpts()) {
  // Direction 1, uniform across the whole set: the option CONSUMES the next token, so a `.py`
  // sitting there is the option's argument and nothing is executed.
  test(`check 17 M-4: \`${opt}\` consumes its value, so \`${opt} x.py\` executes no script`, (t) => {
    const root = fixture(t);
    workflowStep(root, `m-4 consumes ${opt}`, `python3 ${opt} value.py`);
    const r = run(root);
    assert.equal(r.status, 0, r.stderr);
  });

  // Direction 2, for the options the arity table actually decides: having consumed its value,
  // the real script behind it is still found.
  if (hasOwnBranch(opt)) continue;
  test(`check 17 M-4: \`${opt} <value>\` does not hide the script behind it`, (t) => {
    const root = fixture(t);
    workflowStep(root, `m-4 finds past ${opt}`,
      `python3 ${opt} someval skills/_shared/tests/test-pm-status.py`);
    const r = run(root);
    assert.equal(r.status, 1, r.stdout);
    assert.match(r.stderr, /invokes a PEP-723 script with python3/);
  });
}

// ---- M-5: quoting, at all three positions that matter ----
//
// Every pre-existing quoting test quotes a DECOY -- a fake `uv run --with` inside a string.
// None quotes the interpreter, the provisioning flag, or the target, so deleting wordLiteral's
// `DblQuoted` or `SglQuoted` arm was GREEN while silencing real invocations, including
// `python3 "{pm_status}" verify`. These use block scalars where the shell quoting would
// otherwise collide with YAML's own.
for (const [label, quoted] of [
  ["single-quoted interpreter", "'python3' skills/_shared/tests/test-pm-status.py"],
  ["double-quoted interpreter", '"python3" skills/_shared/tests/test-pm-status.py'],
  ["single-quoted target", "python3 'skills/_shared/tests/test-pm-status.py'"],
  ["double-quoted target", 'python3 "skills/_shared/tests/test-pm-status.py"'],
]) {
  test(`check 17 M-5: a ${label} is still an invocation`, (t) => {
    const root = fixture(t);
    write(root, ".github/workflows/checks.yml",
      `    - name: m-5 ${label}\n      run: |\n        ${quoted}\n`, /* append */ true);
    const r = run(root);
    assert.equal(r.status, 1, r.stdout);
    assert.match(r.stderr, /invokes a PEP-723 script with python3/);
  });
}

// The mirror: a quoted provisioning FLAG must still be recognised as one, or the exemption
// collapses and every legitimate quoted line goes red.
test("check 17 M-5: a quoted `--with` is still a provisioning flag", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/checks.yml",
    "    - name: m-5 quoted flag\n      run: |\n" +
    `        uv run "--with" 'ruamel.yaml>=0.18' python3 skills/_shared/tests/test-pm-status.py\n`,
    /* append */ true);
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// The helper tokens are the shape the skills actually write, and they are routinely quoted.
// Derived from PEP723_HELPER_RE so a third token added later is tested without being typed here.
function pep723HelperTokens() {
  const m = checkDocsSource().match(/const PEP723_HELPER_RE = (\/\S+\/);/);
  assert.ok(m, "PEP723_HELPER_RE literal not found -- this test derives its scope from it");
  const alt = m[1].match(/\(\?:([^)]+)\)/);
  assert.ok(alt, `PEP723_HELPER_RE has no alternation group: ${m[1]}`);
  const tokens = alt[1].split("|");
  assert.ok(tokens.length > 0, "PEP723_HELPER_RE alternation parsed as empty");
  return tokens;
}

for (const token of pep723HelperTokens()) {
  test(`check 17 M-5: a double-quoted {${token}} helper token is still an invocation`, (t) => {
    const root = fixture(t);
    write(root, "skills/l3io-pm-execute/steps/m5-quoted-helper.md",
      "```bash\n" + `python3 "{${token}}" verify\n` + "```\n");
    const r = run(root);
    assert.equal(r.status, 1, r.stdout);
    assert.match(r.stderr, /m5-quoted-helper\.md:\d+: invokes a PEP-723 script with python3/);
  });
}

// ---- M-6: the workflow scope covers both spellings of the extension ----
//
// walkWorkflowFiles() matches /\.ya?ml$/, and the only scope-attack test planted a `.yml`
// file -- so narrowing that pattern to /\.yml$/ was GREEN while a violation in
// `.github/workflows/*.yaml` became invisible. The rule was proven; its REACH was not
// (repo CLAUDE.md §4).
for (const ext of ["yml", "yaml"]) {
  test(`check 17 M-6 scope attack: a violation in a new .${ext} workflow is caught`, (t) => {
    const root = fixture(t);
    write(root, `.github/workflows/scheduled.${ext}`,
      "name: scheduled\non: [schedule]\njobs:\n  a:\n    runs-on: ubuntu-latest\n" +
      "    steps:\n    - run: python3 skills/_shared/tests/test-pm-status.py\n");
    const r = run(root);
    assert.equal(r.status, 1, r.stdout);
    assert.match(r.stderr,
      new RegExp(`scheduled\\.${ext}:\\d+: invokes a PEP-723 script with python3`));
  });
}

// ---- M-7: each decoration shape asserts ITS OWN wording ----
//
// Fix round 1 split the failure message into a direct and an indirect form, and loosened these
// two assertions to accept either -- which left the `direct` computation invertible with the
// suite still green. That is the fix for one finding creating the next one, so they are split
// and pinned exactly.
//
// A list bullet LEXES: argv[0] is `-`, python3 is an argv word of something else, so it takes
// the indirect wording and says so honestly.
test("check 17 M-7: a bullet-decorated directive is caught with the indirect wording", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/m7-bullet.md",
    "- python3 {pm_status} set-status --state-root x\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr,
    /m7-bullet\.md:\d+: contains an unquoted python3-plus-script sequence outside a provisioned/);
  assert.doesNotMatch(r.stderr, /m7-bullet\.md:\d+: invokes a PEP-723 script/);
});

// A table row does NOT lex -- a leading `|` is a shell syntax error -- so there is no argv to
// classify and the direct wording is the honest one: PY_INVOKE_RE matched a python3-plus-script
// sequence and nothing exempted it.
test("check 17 M-7: a table-cell directive is caught with the direct wording", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/m7-table.md",
    "| `python3 {pm_status} verify` | wrong |\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /m7-table\.md:\d+: invokes a PEP-723 script with python3/);
  assert.doesNotMatch(r.stderr, /m7-table\.md:\d+: contains an unquoted/);
});

// ---- check 18 (docs-check-count) ----
//
// Same derive-don't-type discipline as the check 15 tests above: the expected counts and
// words are read back from the fixture's real files before mutation, never typed as literals.

function realHeaderCount(root) {
  const src = fs.readFileSync(path.join(root, "scripts", "check-docs.mjs"), "utf8");
  const usageAt = src.indexOf("// Usage:");
  const header = usageAt < 0 ? src : src.slice(0, usageAt);
  return [...header.matchAll(/^\/\/\s+(\d+)\.\s/gm)].length;
}

function claudeCheckCountWord(root) {
  const text = fs.readFileSync(path.join(root, "CLAUDE.md"), "utf8");
  const m = text.match(/`check:docs` runs ([a-z-]+) checks/);
  return m ? m[1] : null;
}

test("check 18: the correct count passes", (t) => {
  const root = fixture(t);
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test("check 18: a stated count one below the real one is caught in CLAUDE.md", (t) => {
  const root = fixture(t);
  const n = realHeaderCount(root);
  const word = claudeCheckCountWord(root);
  assert.equal(NUMBER_WORDS.indexOf(word), n,
    "fixture's CLAUDE.md claim should match the real header count before this test mutates it");
  const wrong = NUMBER_WORDS[n - 1];
  const p = path.join(root, "CLAUDE.md");
  fs.writeFileSync(p, fs.readFileSync(p, "utf8")
    .replace(`\`check:docs\` runs ${word} checks`, `\`check:docs\` runs ${wrong} checks`));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, new RegExp(`CLAUDE\\.md: says "${wrong}" checks, but .* runs ${n}`));
});

test("check 18: a stated count one below the real one is caught in scripts/CLAUDE.md", (t) => {
  const root = fixture(t);
  const n = realHeaderCount(root);
  const p = path.join(root, "scripts", "CLAUDE.md");
  const text = fs.readFileSync(p, "utf8");
  const m = text.match(/numbers its ([a-z-]+) checks there/);
  assert.equal(NUMBER_WORDS.indexOf(m[1]), n,
    "fixture's scripts/CLAUDE.md claim should match the real header count before mutation");
  const wrong = NUMBER_WORDS[n - 1];
  fs.writeFileSync(p, text.replace(`numbers its ${m[1]} checks there`,
    `numbers its ${wrong} checks there`));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, new RegExp(`scripts/CLAUDE\\.md: says "${wrong}" checks, but .* runs ${n}`));
});

test("check 18: an invocation added without a header entry trips the derivations-disagree branch", (t) => {
  const root = fixture(t);
  const p = path.join(root, "scripts", "check-docs.mjs");
  const text = fs.readFileSync(p, "utf8");
  // Add a genuine extra top-level invocation of an existing check function, matching the
  // exact "checkXxx();" shape derivation B scans for, without touching the header count.
  fs.writeFileSync(p, text.replace("checkSkillNames();", "checkSkillNames();\ncheckSkillNames();"));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /check count derivations disagree/);
});

// ---- check 19 (derived-counts) ----

// The real skill count, derived from the fixture's own skills/ tree (never a literal), so
// this test does not need editing every time a skill is added or removed — exactly the
// discipline check 19 itself enforces on the docs.
function realSkillCount(root) {
  return fs.readdirSync(path.join(root, "skills"), { withFileTypes: true })
    .filter((e) => e.isDirectory() && e.name.startsWith("l3io-"))
    .filter((e) => fs.existsSync(path.join(root, "skills", e.name, "SKILL.md")))
    .length;
}

test("check 19: a stale total-skill count is caught", (t) => {
  const root = fixture(t);
  const n = realSkillCount(root);
  const word = NUMBER_WORDS[n];
  const p = path.join(root, "docs", "getting-started.md");
  const before = fs.readFileSync(p, "utf8");
  const m = before.match(/New to the ([a-z-]+) skills\?/);
  assert.equal(NUMBER_WORDS.indexOf(m[1]), n,
    "fixture's getting-started.md claim should match the real skill count before mutation");
  const wrong = NUMBER_WORDS[n + 1];
  fs.writeFileSync(p, before.replace(`New to the ${word} skills?`, `New to the ${wrong} skills?`));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, new RegExp(`says "${wrong}" skill\\(s\\), but the package has ${n}`));
});

test("check 19: a stale module count is caught", (t) => {
  const root = fixture(t);
  const p = path.join(root, "CLAUDE.md");
  const before = fs.readFileSync(p, "utf8");
  fs.writeFileSync(p, before.replace("package with four modules:", "package with five modules:"));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /says "five" module\(s\), but the package has 4/);
});

test("check 19: scope attack — adding a skill directory must break the count claims", (t) => {
  const root = fixture(t);
  const n = realSkillCount(root);
  write(root, "skills/l3io-newthing/SKILL.md", "---\nname: l3io-newthing\ndescription: d\n---\n");
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, new RegExp(`skill\\(s\\), but the package has ${n + 1}`));
});

test("check 19: a reworded claim sentence fails loudly rather than passing", (t) => {
  const root = fixture(t);
  const p = path.join(root, "docs", "l3io-pm-reference.md");
  const before = fs.readFileSync(p, "utf8");
  fs.writeFileSync(p, before.replace(/four skills that cover the delivery lifecycle/,
    "several skills covering the lifecycle"));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /claim was not found — has the sentence been reworded/);
});

// ---- check 20 (shared-files-table) ----

test("check 20: a _shared file in a sync group with no table row is caught", (t) => {
  const root = fixture(t);
  write(root, "skills/_shared/brand-new-thing.md", "x\n");
  const p = path.join(root, "scripts", "sync-shared-scripts.mjs");
  const before = fs.readFileSync(p, "utf8");
  fs.writeFileSync(p, before.replace(
    'const moduleHomeFiles = [',
    'const moduleHomeFiles = [\n  { src: path.join(sharedDir, "brand-new-thing.md"), rel: path.join("assets", "brand-new-thing.md") },'));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /brand-new-thing\.md is synced but has no row/);
});

test("check 20: a table row naming a nonexistent _shared source is caught", (t) => {
  const root = fixture(t);
  const p = path.join(root, "CLAUDE.md");
  const before = fs.readFileSync(p, "utf8");
  fs.writeFileSync(p, before.replace(
    "| `skills/_shared/pm-status.py` |",
    "| `skills/_shared/ghost.py` | `scripts/ghost.py` | nobody |\n| `skills/_shared/pm-status.py` |"));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /ghost\.py.*no such file/);
});

test("check 20: the real tree passes", (t) => {
  const root = fixture(t);
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// ---- check 21 (skill-frontmatter) ----
//
// Task 11A fix round 1, H-1: BMad's installer silently drops a skill whose SKILL.md
// frontmatter fails a strict YAML parse, or whose `name:` disagrees with its directory name.
// l3io-pm-sync/SKILL.md's unquoted "Modes: setup, push, ..." did exactly this (H-2) and no
// other check here would have caught it. These tests plant the same class of break in a
// DIFFERENT skill than the one that broke in production, so the guard is proven general
// rather than special-cased to the one file that happened to fail first.

test("check 21: an unquoted colon in a description breaks the YAML parse and is caught", (t) => {
  const root = fixture(t);
  const p = path.join(root, "skills", "l3io-pm-help", "SKILL.md");
  const before = fs.readFileSync(p, "utf8");
  const after = before.replace(
    /^description:.*$/m,
    "description: Read project state. Modes: progress, help.",
  );
  assert.notEqual(before, after, "fixture SKILL.md did not contain the expected description line");
  fs.writeFileSync(p, after);
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /skills\/l3io-pm-help\/SKILL\.md: frontmatter fails a strict YAML parse/);
});

test("check 21: a frontmatter name that disagrees with the directory name is caught", (t) => {
  const root = fixture(t);
  const p = path.join(root, "skills", "l3io-pm-plan", "SKILL.md");
  const before = fs.readFileSync(p, "utf8");
  const after = before.replace(/^name: l3io-pm-plan$/m, "name: l3io-pm-plan-renamed");
  assert.notEqual(before, after, "fixture SKILL.md did not contain the expected name line");
  fs.writeFileSync(p, after);
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(
    r.stderr,
    /skills\/l3io-pm-plan\/SKILL\.md: frontmatter 'name: l3io-pm-plan-renamed' does not match its directory name 'l3io-pm-plan'/,
  );
});

test("check 21: the real tree's SKILL.md frontmatter all strict-parse and match their directory names", (t) => {
  const root = fixture(t);
  const r = run(root, ["-v"]);
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /skill-frontmatter: \d+ SKILL\.md file\(s\) strict-parsed/);
});

test("check 21: a frontmatter name rendered as a non-string type shows the actual type, not a stringified join", (t) => {
  const root = fixture(t);
  const p = path.join(root, "skills", "l3io-util-doctor", "SKILL.md");
  const before = fs.readFileSync(p, "utf8");
  const after = before.replace(/^name: l3io-util-doctor$/m, "name: [l3io-util-doctor, other]");
  assert.notEqual(before, after, "fixture SKILL.md did not contain the expected name line");
  fs.writeFileSync(p, after);
  const r = run(root);
  assert.equal(r.status, 1);
  // Fix round 2, N-2: a template-literal join used to render this as the misleading
  // "name: l3io-util-doctor,other" (looks like a near-miss typo). JSON.stringify shows the
  // real shape -- a list -- instead.
  assert.match(r.stderr, /frontmatter 'name: \["l3io-util-doctor","other"\]' does not match/);
});

// ---- check 21, `description` (Fix round 2, N-1) ----
//
// The re-review ran BMad 6.12.0's real ManifestGenerator.parseSkillMd() and found it drops a
// skill whose `description` is anything other than a non-empty string -- a check that only
// validated `name` (fix round 1's scope) passed all seven of these DROP shapes while a real
// install silently shipped without the skill. Demonstrated end to end against l3io-arch-review
// during the re-review (the skill the fix round 1 mutation tests never touched); these tests
// plant the same seven shapes so the guard is proven for the class, not just the one instance
// the reviewer happened to try.
const DESCRIPTION_DROP_SHAPES = [
  {
    label: "description key absent entirely",
    replace: (text) => text.replace(/^description:.*$\n/m, ""),
    expect: /the 'description' key is missing/,
  },
  {
    label: "description is an empty string",
    replace: (text) => text.replace(/^description:.*$/m, 'description: ""'),
    expect: /'description' is an empty string/,
  },
  {
    label: "description is null",
    replace: (text) => text.replace(/^description:.*$/m, "description: null"),
    expect: /'description' is null/,
  },
  {
    label: "description is a list",
    replace: (text) => text.replace(/^description:.*$/m, "description: [a, b]"),
    expect: /'description' is a list, not a string/,
  },
  {
    label: "description is a mapping",
    replace: (text) => text.replace(/^description:.*$/m, "description: {a: b}"),
    expect: /'description' is a mapping, not a string/,
  },
  {
    label: "description is a number",
    replace: (text) => text.replace(/^description:.*$/m, "description: 42"),
    expect: /'description' is a number, not a string/,
  },
  {
    label: "description is a boolean",
    replace: (text) => text.replace(/^description:.*$/m, "description: true"),
    expect: /'description' is a boolean, not a string/,
  },
];

for (const shape of DESCRIPTION_DROP_SHAPES) {
  test(`check 21: ${shape.label} is caught (BMad drops the skill; this must too)`, (t) => {
    const root = fixture(t);
    const p = path.join(root, "skills", "l3io-arch-review", "SKILL.md");
    const before = fs.readFileSync(p, "utf8");
    const after = shape.replace(before);
    assert.notEqual(before, after, "fixture SKILL.md did not contain the expected description line");
    fs.writeFileSync(p, after);
    const r = run(root);
    assert.equal(r.status, 1);
    assert.match(r.stderr, /skills\/l3io-arch-review\/SKILL\.md:/);
    assert.match(r.stderr, shape.expect);
  });
}

test("check 21: a valid non-empty string description does not trip the description check", (t) => {
  const root = fixture(t);
  const p = path.join(root, "skills", "l3io-arch-review", "SKILL.md");
  const before = fs.readFileSync(p, "utf8");
  const after = before.replace(/^description:.*$/m, 'description: "A perfectly ordinary description."');
  assert.notEqual(before, after, "fixture SKILL.md did not contain the expected description line");
  fs.writeFileSync(p, after);
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// ---------------------------------------------------------------------------
// Check 4, skills/ arm (pm-status-invocations).
//
// The arm exists because the commands agents actually run live in skills/**/*.md and were
// checked by nothing: check 4's live-docs arm reads README/CLAUDE.md/docs only, and judges
// subcommand NAMES, never flags. Task 12 inlined a `clear-lock --state-root ... --epic ...`
// into l3io-pm-help, Task 13 put a second copy in l3io-util-doctor, and the two are
// cross-linked in prose alone.
//
// Every plant below goes into a BRAND-NEW file in a BRAND-NEW directory, so each test attacks
// the scope (is skills/ really walked?) as well as the rule.
// ---------------------------------------------------------------------------
const PLANT_FILE = path.join("skills", "l3io-util-doctor", "steps", "brand-new-invocation-dir",
  "planted.md");

function plantInvocation(root, command) {
  write(root, PLANT_FILE, ["# Planted", "", "```bash", command, "```", ""].join("\n"));
}

test("check 4/skills: an invocation naming a subcommand the CLI does not have is caught", (t) => {
  const root = fixture(t);
  plantInvocation(root, "uv run {pm_status} progress --state-root {pm_state_root}");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /planted\.md:\d+: invokes pm-status\.py subcommand 'progress'/);
});

test("check 4/skills: an invocation passing a flag the CLI never registers is caught", (t) => {
  const root = fixture(t);
  plantInvocation(root, "uv run {pm_status} clear-lock --state-root {pm_state_root} --ledger {f}");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /planted\.md:\d+: invokes 'clear-lock --ledger'/);
});

test("check 4/skills: a flag on a `\\`-continued line is still seen", (t) => {
  const root = fixture(t);
  write(root, PLANT_FILE, [
    "# Planted", "", "```bash",
    "uv run {pm_status} clear-lock --state-root {pm_state_root} \\",
    "  --no-such-flag {epic_key}",
    "```", "",
  ].join("\n"));
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /invokes 'clear-lock --no-such-flag'/);
});

test("check 4/skills: an invocation inside a markdown table cell is seen", (t) => {
  const root = fixture(t);
  write(root, PLANT_FILE, [
    "# Planted", "",
    "| When | Run |",
    "|---|---|",
    "| stale lock | `uv run {pm_status} clear-lock --state-root {r} --not-a-flag {e}` |",
    "",
  ].join("\n"));
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /invokes 'clear-lock --not-a-flag'/);
});

test("check 4/skills: a correct invocation does not fire", (t) => {
  const root = fixture(t);
  plantInvocation(root,
    "uv run {pm_status} clear-lock --state-root {pm_state_root} --epic {epic_key}");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// The option union is read from add_argument(...) calls, which may register several spellings
// in ONE call: `se.add_argument("--elapsed-hours", "--time-hours", dest="elapsed_hours")`.
// A regex that captured only the first spelling missed three real flags (--time-hours,
// --time-hours-low, --time-hours-high) -- measured against the parser object itself, built
// under uv from build_parser(), before this check shipped. This pins the alias case, so that
// simplification fails loudly instead of inventing three phantom violations.
// This one plants under l3io-pm rather than at PLANT_FILE, because it is the only
// expect-GREEN plant that names a subcommand l3io-util-doctor does not really run: check 4's
// module-reference arm would rightly demand a docs/l3io-util-reference.md row for it, and this
// test is about flag ALIASES, not about module documentation. docs/l3io-pm-reference.md
// documents the whole CLI, so the module arm has nothing to add there. Still a brand-new file
// in a brand-new directory, so it still attacks the scope.
test("check 4/skills: a second spelling registered in the same add_argument() is accepted", (t) => {
  const root = fixture(t);
  const cli = fs.readFileSync(path.join(root, "skills", "_shared", "pm-status.py"), "utf8");
  assert.match(cli, /add_argument\(\s*"--elapsed-hours",\s*"--time-hours"/,
    "pm-status.py no longer registers --time-hours as an alias; this test needs a new one");
  write(root, path.join("skills", "l3io-pm-execute", "steps", "brand-new-alias-dir", "planted.md"),
    ["# Planted", "", "```bash",
     "uv run {pm_status} set-estimate --state-root {r} --story {s} --time-hours 2",
     "```", ""].join("\n"));
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

test("check 4/skills: prose naming pm-status.py outside a uv run command is not an invocation", (t) => {
  const root = fixture(t);
  write(root, PLANT_FILE, [
    "# Planted", "", "```",
    "BLOCKED: a status that makes every later pm-status.py write on that node fail.",
    "```", "",
  ].join("\n"));
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// ---------------------------------------------------------------------------
// Check 4, module-reference arm. The completeness arm was bound to one hand-typed constant,
// docs/l3io-pm-reference.md, so docs/l3io-util-reference.md -- a reference for a skill whose
// mode files invoke {pm_status} directly -- was checked by nothing in either direction. The
// set is now derived from each skill's module.yaml `code:` and the repo's own `<code>-*`
// naming convention. These tests attack that derivation, not just the rule.
// ---------------------------------------------------------------------------

test("check 4/modules: a subcommand a module runs but its reference doc omits is caught", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-util-doctor/steps/planted-mode.md",
    "Run `uv run {pm_status} estimate-story --state-root x --story E001-S01-001`.\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr,
    /docs\/l3io-util-reference\.md: does not document pm-status\.py subcommand 'estimate-story' as a table row, but l3io-util's own skills invoke it/);
});

// Scope attack on module MEMBERSHIP: a brand-new skill directory is bound to its module by the
// `<code>-*` naming convention, never by a list. A checker that iterated a hand-kept set of
// skills would generate no case here and pass in silence.
test("check 4/modules scope attack: a brand-new skill in a module is covered on arrival", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-util-newskill/steps/x.md",
    "Run `uv run {pm_status} estimate-rollup --state-root x --epic E001`.\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr,
    /docs\/l3io-util-reference\.md: does not document pm-status\.py subcommand 'estimate-rollup' as a table row/);
});

// A per-skill file whose bytes match a skills/_shared/ file is a GENERATED copy of shared
// contract text, not something the module chose to run -- syncing status-files.md into
// l3io-util-doctor must not start demanding rows for the subcommands the shared state contract
// quotes. The exclusion is derived from content, so this plants the same bytes in both places.
test("check 4/modules: a synced copy of a shared reference demands no row", (t) => {
  const root = fixture(t);
  const body = "# Shared\n\nRun `uv run {pm_status} estimate-story --state-root x --story S`.\n";
  write(root, "skills/_shared/planted-shared.md", body);
  write(root, "skills/l3io-util-doctor/references/planted-shared.md", body);
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

// ...and the control for it: one byte different and it is no longer a synced copy, so the row
// is demanded again. Without this, the test above would pass just as well if the arm had
// stopped looking at l3io-util-doctor entirely.
test("check 4/modules: a NEAR-copy of a shared reference is not exempt", (t) => {
  const root = fixture(t);
  const body = "# Shared\n\nRun `uv run {pm_status} estimate-story --state-root x --story S`.\n";
  write(root, "skills/_shared/planted-shared.md", body);
  write(root, "skills/l3io-util-doctor/references/planted-shared.md", body + "\nLocal note.\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr,
    /docs\/l3io-util-reference\.md: does not document pm-status\.py subcommand 'estimate-story'/);
});

// Both directions of the DOC set, so neither side can silently shrink. A module whose
// reference doc disappears must fail rather than quietly stop being checked...
test("check 4/modules: a module with no reference doc is caught", (t) => {
  const root = fixture(t);
  fs.rmSync(path.join(root, "docs", "l3io-sec-reference.md"));
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr,
    /docs\/l3io-sec-reference\.md: module 'l3io-sec' has no reference doc among the live docs/);
});

// ...and a reference doc for a module that does not exist must fail too, rather than being
// silently skipped as "not one of ours".
test("check 4/modules: a reference doc naming no real module is caught", (t) => {
  const root = fixture(t);
  write(root, "docs/l3io-ghost-reference.md", "# Ghost\n\nNothing here.\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr,
    /docs\/l3io-ghost-reference\.md: is a reference doc for module 'l3io-ghost', which no skills\/\*\/module\.yaml declares/);
});

// ---------------------------------------------------------------------------
// LIVE_DOCS scope (G3). The list was a single non-recursive readdirSync of docs/, so every
// subdirectory -- the eight ADRs among them -- sat outside checks 1, 3, 4's forward arm, 5, 6
// and 17. Not one rule in check-docs.mjs had ever read an ADR, for any reason. These tests
// pin the recursion, the two deliberate exclusions, and the anchor that keeps the exclusion
// list from going stale in silence.
// ---------------------------------------------------------------------------

test("LIVE_DOCS scope: a violation in docs/adr/ is caught", (t) => {
  const root = fixture(t);
  write(root, "docs/adr/0099-planted.md",
    "# ADR-0099\n\nSee `/l3io-pm-ghost-skill` for details.\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr,
    /docs\/adr\/0099-planted\.md: names skill 'l3io-pm-ghost-skill'/);
});

// Deeper than one level, so "recursive" means recursive and not "docs/ plus its children".
test("LIVE_DOCS scope: a violation two directories below docs/ is caught", (t) => {
  const root = fixture(t);
  write(root, "docs/adr/appendix/notes.md", "See `/l3io-pm-ghost-skill`.\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /docs\/adr\/appendix\/notes\.md: names skill 'l3io-pm-ghost-skill'/);
});

// The exclusions are facts, not comments: the same violation planted in each historical tree
// must NOT fail. docs/decision-logs/ says so in its own header ("Historical authoring record
// ... may not describe current behaviour"), and rewriting either to match today would falsify
// the record.
test("LIVE_DOCS scope: docs/superpowers/** stays excluded", (t) => {
  const root = fixture(t);
  write(root, "docs/superpowers/specs/2020-01-01-old.md", "See `/l3io-pm-ghost-skill`.\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test("LIVE_DOCS scope: docs/decision-logs/** stays excluded", (t) => {
  const root = fixture(t);
  write(root, "docs/decision-logs/l3io-ghost.md", "See `/l3io-pm-ghost-skill`.\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

// Scope attack on the exclusion list itself. A hand-named path that quietly stops matching is
// exactly how a guard's reach rots: renaming the tree would either drag a historical record
// into every live-doc check or, if the rename went the other way, drop a live tree out of view
// with every gate green. Renaming it must fail HERE, loudly.
test("LIVE_DOCS scope attack: renaming an excluded tree fails loudly", (t) => {
  const root = fixture(t);
  fs.renameSync(path.join(root, "docs", "decision-logs"),
    path.join(root, "docs", "authoring-logs"));
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr,
    /docs\/decision-logs is named as a historical-record tree excluded from LIVE_DOCS/);
});

// ---------------------------------------------------------------------------
// Check 22 (readme-repo-layout).
//
// The block drifted three times in three consecutive tasks -- the l3io-pm-help row, the
// l3io-pm-plan row claiming a deleted scripts/, and the l3io-pm-setup row omitting an
// existing references/ -- and nothing read it, so all three survived six green gates.
// ---------------------------------------------------------------------------

// The expected row count is derived HERE, with its own readdirSync, rather than from the
// checker's own derivation: two derivations from one function agree by construction and could
// no longer catch a bug in it. A checker that silently examined zero rows would pass every
// negative test below by never looking; this assertion is what rules that out.
test("check 22: every l3io-* skill directory is matched against the block", (t) => {
  const root = fixture(t);
  const expected = fs.readdirSync(path.join(root, "skills"), { withFileTypes: true })
    .filter((e) => e.isDirectory() && e.name.startsWith("l3io-")).length;
  assert.ok(expected >= 8, `expected at least the 8 shipped skills, found ${expected}`);
  const r = run(root, ["-v"]);
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, new RegExp(`readme-repo-layout: ${expected} skill row\\(s\\)`));
});

test("check 22: a row claiming a directory that does not exist is caught", (t) => {
  const root = fixture(t);
  const p = path.join(root, "README.md");
  const before = fs.readFileSync(p, "utf8");
  const after = before.replace(/^(\s*l3io-pm-help\/\s+.*)$/m, "$1, assets/");
  assert.notEqual(before, after, "README has no l3io-pm-help Repo Layout row to amend");
  fs.writeFileSync(p, after);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr,
    /the skills\/l3io-pm-help\/ row lists assets\/, which does not exist on disk/);
});

test("check 22: a directory on disk that no row claims is caught", (t) => {
  const root = fixture(t);
  write(root, path.join("skills", "l3io-pm-help", "brand-new-dir", "file.md"), "# hi\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /the skills\/l3io-pm-help\/ row does not list brand-new-dir\//);
});

// Scope attack: the skill set must come from disk, not from the block's own rows. A checker
// that iterated the rows instead would generate one fewer case here and pass in silence --
// the vacuous-green shape an earlier task paid for.
test("check 22: scope attack — a brand-new skill directory with no row is caught", (t) => {
  const root = fixture(t);
  write(root, path.join("skills", "l3io-zzz-newskill", "references", "x.md"), "# x\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /Repo Layout has no row for skills\/l3io-zzz-newskill\//);
});

test("check 22: a row naming a skill directory that does not exist is caught", (t) => {
  const root = fixture(t);
  const p = path.join(root, "README.md");
  const before = fs.readFileSync(p, "utf8");
  const after = before.replace(/^(\s*l3io-pm-help\/\s+.*)$/m,
    "  l3io-pm-ghost/        SKILL.md, references/\n$1");
  assert.notEqual(before, after, "README has no l3io-pm-help Repo Layout row to anchor on");
  fs.writeFileSync(p, after);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /lists 'l3io-pm-ghost\/', which is not a directory under skills\//);
});

// A fixture that is a REAL git work tree. Every other fixture is a plain temp copy, so check
// 22 falls back to the filesystem in all of them -- which means none of them exercise the git
// path at all. These two build an index from the real repository's own tracked list (explicit
// paths, read from `git ls-files`, never a wildcard add) so what is asserted below is the
// derivation CI actually runs. No commit is needed: `git ls-files` reads the index.
function gitFixture(t) {
  const dir = fixture(t);
  const listed = spawnSync("git", ["-C", REPO, "ls-files", "-z"],
    { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
  assert.equal(listed.status, 0, "could not read the real repository's tracked file list");
  assert.equal(spawnSync("git", ["-C", dir, "init", "-q"]).status, 0, "git init failed");
  const added = spawnSync("git",
    ["-C", dir, "add", "-f", "--pathspec-from-file=-", "--pathspec-file-nul"],
    { input: listed.stdout, encoding: "utf8" });
  assert.equal(added.status, 0, added.stderr);
  return dir;
}

// The defect this derivation exists to kill, planted exactly as it occurred: an interpreter
// left a gitignored __pycache__/ under skills/l3io-pm-plan/scripts/ AFTER that skill's
// pm-status.py payload copy was cut, and check 22 -- asking readdirSync -- demanded a README
// row for a scripts/ directory the repository does not have. The row was correct; the gate was
// red; there was nothing to fix. Reverting trackedEntries() to readdirSync turns this red.
test("check 22: a gitignored build artifact under a skill demands no README row", (t) => {
  const root = gitFixture(t);
  fs.mkdirSync(path.join(root, "skills", "l3io-pm-plan", "scripts", "__pycache__"),
    { recursive: true });
  fs.writeFileSync(
    path.join(root, "skills", "l3io-pm-plan", "scripts", "__pycache__", "x.pyc"), "");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

// ...and the other direction, in the same git work tree, so the fix cannot have been "stop
// looking". A TRACKED directory missing from the block must still be caught, with the message
// naming the set the run actually consulted.
test("check 22: in a git work tree, a tracked directory no row claims is still caught", (t) => {
  const root = gitFixture(t);
  const rel = path.join("skills", "l3io-pm-help", "brand-new-dir", "file.md");
  write(root, rel, "# hi\n");
  assert.equal(spawnSync("git", ["-C", root, "add", "-f", "--", rel]).status, 0);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr,
    /the skills\/l3io-pm-help\/ row does not list brand-new-dir\/, which is tracked in the repository/);
});

// Scope attack against the git path itself: the untracked-artifact tolerance must not have
// become "ignore everything git has not been told about". A brand-new SKILL directory whose
// files are tracked has no row, and must fail.
test("check 22: in a git work tree, a tracked brand-new skill with no row is caught", (t) => {
  const root = gitFixture(t);
  const rel = path.join("skills", "l3io-zzz-newskill", "references", "x.md");
  write(root, rel, "# x\n");
  assert.equal(spawnSync("git", ["-C", root, "add", "-f", "--", rel]).status, 0);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /Repo Layout has no row for skills\/l3io-zzz-newskill\//);
});

test("check 22: a restructured Repo Layout section fails loudly rather than silently", (t) => {
  const root = fixture(t);
  const p = path.join(root, "README.md");
  const before = fs.readFileSync(p, "utf8");
  fs.writeFileSync(p, before.replace("## Repo Layout", "## How This Repo Is Laid Out"));
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /no fenced block found under "## Repo Layout"/);
});

// ---------------------------------------------------------------------------
// Check 18's third claim site (CONTRIBUTING.md).
// ---------------------------------------------------------------------------
test("check 18: CONTRIBUTING.md's check count is read, and a wrong one fails", (t) => {
  const root = fixture(t);
  const p = path.join(root, "CONTRIBUTING.md");
  const before = fs.readFileSync(p, "utf8");
  const after = before.replace(/the code it describes — [a-z-]+ checks/,
    "the code it describes — nine checks");
  assert.notEqual(before, after, "CONTRIBUTING.md no longer states a check count in its table");
  fs.writeFileSync(p, after);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /CONTRIBUTING\.md: says "nine" checks/);
});

// A command soft-wrapped inside one `...` code span, which is how the second copy of the
// duplicated clear-lock remedy is written in l3io-util-doctor/steps/stats.md. Without the
// open-span join the flags sit on the line after the subcommand and are never judged -- so
// one copy of the duplication would be checked and the other not, which is the failure this
// arm exists to prevent. Verified on the real file: planting --epic-key on its second source
// line is reported against stats.md:175.
test("check 4/skills: flags soft-wrapped onto the next line inside one code span are seen", (t) => {
  const root = fixture(t);
  write(root, PLANT_FILE, [
    "# Planted", "",
    "- If a lock is stale, recommend: `Epic {key} is locked. Run: uv run {pm_status} clear-lock",
    "  --state-root {r} --epic-key {key}`. Do not re-derive the lock state yourself.",
    "",
  ].join("\n"));
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /invokes 'clear-lock --epic-key'/);
});

// MAX_LINE_JOINS bounds the open-span join, and the observable difference is the reported
// line number: a stray unclosed backtick in prose never closes, so without the cap every
// following line -- to end of file -- folds into one logical line, and every violation below
// it is reported at the stray backtick's line instead of its own. Here the violation is on
// line 7 and the stray backtick on line 3.
test("check 4/skills: a stray backtick does not swallow the lines below it", (t) => {
  const root = fixture(t);
  write(root, PLANT_FILE, [
    "# Planted",                                                    // 1
    "",                                                             // 2
    "A stray ` backtick opens a span that never closes.",           // 3
    "filler one",                                                   // 4
    "filler two",                                                   // 5
    "filler three",                                                 // 6
    "uv run {pm_status} clear-lock --state-root {r} --epic-key {k}", // 7
    "",
  ].join("\n"));
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /planted\.md:7: invokes 'clear-lock --epic-key'/);
});

// Continuation DEPTH. A single shared join cap covered both continuation kinds and stopped at
// three, so the checker read part of a `\`-continued command and judged it as if it were
// whole: 68 pm-status invocations in this repo run deeper than that, and 154 long-flag tokens
// were never judged (1019 of 1173 checked, measured with the checker's own -v counter). The
// two kinds are now counted separately and only the span join is capped.
//
// This first test pins a fixed depth so the boundary holds whatever the tree does: four joins,
// one past the old cap, with the bogus flag on the last line.
test("check 4/skills: a flag one continuation past the old cap is seen", (t) => {
  const root = fixture(t);
  write(root, PLANT_FILE, [
    "# Planted", "", "```bash",
    "uv run {pm_status} set-actual --state-root {r} \\",
    "  --node story --story {s} \\",
    "  --elapsed-hours 1 \\",
    "  --man-hours 2 \\",
    "  --hitl-hours 3 --not-a-real-flag 4",
    "```", "",
  ].join("\n"));
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /invokes 'set-actual --not-a-real-flag'/);
});

// ...and this one attacks the depth the REAL corpus contains, rather than a depth the test
// author chose. It finds the deepest `\`-continued run carrying a pm-status token anywhere in
// the fixture, appends a bogus flag to that run's final line, and requires the checker to have
// read that far. Any cap below the tree's own depth -- today or after the tree grows -- turns
// this red, which a fixed-depth test alone cannot promise.
test("check 4/skills: the deepest real continuation in the tree is read to its end", (t) => {
  const root = fixture(t);

  const mdFiles = [];
  const walk = (dir) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) walk(p);
      else if (e.name.endsWith(".md")) mdFiles.push(p);
    }
  };
  walk(path.join(root, "skills"));

  let deepest = null;
  for (const file of mdFiles) {
    const lines = fs.readFileSync(file, "utf8").split("\n");
    for (let i = 0; i < lines.length; i++) {
      if (!/\\\s*$/.test(lines[i])) continue;
      let j = i;
      while (j < lines.length && /\\\s*$/.test(lines[j])) j += 1;
      const block = lines.slice(i, j + 1).join(" ");
      const joins = j - i;
      if (/\{pm_status\}|pm-status\.py/.test(block) && (!deepest || joins > deepest.joins)) {
        deepest = { file, last: j, joins };
      }
      i = j;
    }
  }

  assert.ok(deepest, "no `\\`-continued pm-status invocation found in the fixture");
  assert.ok(deepest.joins > 3,
    `the deepest real continuation is only ${deepest.joins} join(s); this test needs one ` +
    `deeper than the old shared cap of 3 to prove anything`);

  const lines = fs.readFileSync(deepest.file, "utf8").split("\n");
  lines[deepest.last] += " --not-a-real-flag X";
  fs.writeFileSync(deepest.file, lines.join("\n"));

  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /--not-a-real-flag', but pm-status\.py registers no such option/);
});

// ---------------------------------------------------------------------------
// Check 4, the reach extensions (whole-branch review, M-2).
//
// Three gaps were measured as escaping every gate. Each is planted below in the shape the
// review measured, run against the REAL checker, with the fixture otherwise byte-identical to
// the repo.

// The external anchor. pmStatusSubcommandOptions() extracts the per-subcommand option surface
// from build_parser()'s SOURCE, because reaching argparse costs ~223 ms per checker run and
// this suite runs the checker 100+ times. Deriving internally is only safe when the CONTENT is
// anchored externally, so this asserts the extraction against the real argparse objects, in
// both directions, for every subcommand. If build_parser() grows a shape the regex cannot
// follow, this goes red -- rather than check 4 silently narrowing back to the union.
test("the static per-subcommand option surface matches the real argparse, both ways", () => {
  const dumper = path.join(REPO, "scripts", "tests", "dump-pm-status-parser.py");
  const pmStatus = path.join(REPO, "skills", "_shared", "pm-status.py");
  const real = spawnSync("uv", ["run", dumper, pmStatus], { cwd: REPO, encoding: "utf8" });
  assert.equal(real.status, 0,
    `could not run the real build_parser() (uv is required for this anchor): ${real.stderr}`);

  const staticDump = spawnSync(process.execPath, [CHECK, "--dump-subcommand-options"],
    { cwd: REPO, encoding: "utf8" });
  assert.equal(staticDump.status, 0, staticDump.stderr);

  const fromArgparse = JSON.parse(real.stdout);
  const fromSource = JSON.parse(staticDump.stdout);

  assert.ok(Object.keys(fromArgparse).length > 20,
    `only ${Object.keys(fromArgparse).length} subcommand(s) found — the dump looks empty`);
  assert.deepEqual(Object.keys(fromSource).sort(), Object.keys(fromArgparse).sort(),
    "the set of subcommands differs between build_parser() and the source extraction");
  for (const sub of Object.keys(fromArgparse)) {
    assert.deepEqual(fromSource[sub], fromArgparse[sub],
      `option set for '${sub}' differs between build_parser() and the source extraction`);
  }
});

// M-2(2): the digest's CLI synopsis is a SECOND copy of the CLI surface, loaded standalone by
// every dispatched subagent, and nothing verified it.
const DIGEST_REL = "skills/_shared/steps/shared/step-00-digest.md";
const DIGEST_ANCHOR_LINE = "clear-lock    --state-root S  --epic ID";

function plantInDigest(root, rel, line) {
  const p = path.join(root, rel);
  const text = fs.readFileSync(p, "utf8");
  assert.ok(text.includes(DIGEST_ANCHOR_LINE),
    `${rel}: the synopsis entry this test plants beside is gone — re-anchor the test`);
  fs.writeFileSync(p, text.replace(DIGEST_ANCHOR_LINE, `${DIGEST_ANCHOR_LINE}\n${line}`));
}

test("check 4 catches a fabricated subcommand in the subagent CLI synopsis", (t) => {
  const root = fixture(t);
  plantInDigest(root, DIGEST_REL, "totally-made-up --state-root S");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr,
    /step-00-digest\.md:\d+: the subagent CLI synopsis documents subcommand 'totally-made-up'/);
});

test("check 4 catches a real flag given to the wrong subcommand in the synopsis", (t) => {
  const root = fixture(t);
  // --stall-minutes is real -- on `report`, never on `clear-lock`. A union membership test,
  // which is what the invocation arm used to apply, passes this.
  plantInDigest(root, DIGEST_REL, "clear-lock    --state-root S  --epic ID --stall-minutes N");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr,
    /the subagent CLI synopsis gives 'clear-lock' the flag '--stall-minutes'/);
});

// Scope attack, not a rule attack: the arm must judge every digest copy it FINDS, including
// one in a skill that has never carried a digest. A hand-kept list of the three synced copies
// would pass every test above while checking nothing new here.
test("scope attack: a digest copy in a skill that had none is checked on arrival", (t) => {
  const root = fixture(t);
  const rel = "skills/l3io-util-doctor/steps/shared/step-00-digest.md";
  write(root, rel, fs.readFileSync(path.join(root, DIGEST_REL), "utf8"));
  plantInDigest(root, rel, "also-not-real --state-root S");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr,
    /l3io-util-doctor\/steps\/shared\/step-00-digest\.md:\d+: the subagent CLI synopsis documents subcommand 'also-not-real'/);
});

// The other half of the scope question: an arm whose input set can become empty passes in
// silence. Removing every digest must be a failure, not a green run over nothing.
test("scope attack: removing every digest copy fails rather than passing vacuously", (t) => {
  const root = fixture(t);
  const removed = [];
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(p);
      else if (entry.name === "step-00-digest.md") { fs.rmSync(p); removed.push(p); }
    }
  };
  walk(path.join(root, "skills"));
  assert.ok(removed.length > 0, "no digest copies found to remove");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /no steps\/shared\/step-00-digest\.md found under skills\//);
});

// M-2(1): an invocation with no literal `uv run` in front of it escaped the arm entirely.
test("check 4 catches a bare {pm_status} invocation with no uv run", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-util-doctor/steps/triage.md",
    "\n| `zz` | `{pm_status} totally-made-up --nope X` |\n", true);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /triage\.md:\d+: invokes pm-status\.py subcommand 'totally-made-up'/);
});

// A FLAGLESS bare-binding invocation. Under the first version of this arm -- which judged a
// bare-binding fragment only when it carried a long flag -- this escaped entirely, and two
// real ones shipped that way (`{pm_status} usage` in the digest's routing table,
// `{pm_status} show` in step-estimate.md §4), so renaming either subcommand would have left
// them stale with every gate green.
test("check 4 catches a FLAGLESS bare {pm_status} invocation", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-util-doctor/steps/triage.md",
    "\n| `zz` | run `{pm_status} totally-made-up` once |\n", true);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /triage\.md:\d+: invokes pm-status\.py subcommand 'totally-made-up'/);
});

// The false-positive half, and the reason the qualifier is CODE FORMATTING rather than the
// presence of a long flag. The flag predicate held on this corpus only incidentally: every
// prose use but two sits in a backtick span, and a span closes the fragment before a flag can
// appear in it. The two exceptions are real and shipped -- assets/migrate-state.md:43 and :62
// write an un-backticked {pm_status} inside a fenced BLOCKED message -- so an author adding a
// flag to either sentence would have turned CI red with a message about a subcommand called
// 'not'. Measured against the previous checker on exactly this fixture: it reported
// "invokes pm-status.py subcommand 'not'". It must not now.
test("prose naming {pm_status} outside code formatting is not an invocation, flag or no flag", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-util-doctor/steps/triage.md", [
    "",
    "```",
    "BLOCKED: {pm_status} not found. Self-install did not complete --flock — check the path.",
    "BLOCKED: {pm_status} is version {found}, but this needs {required} --state-root or newer.",
    "```",
    "",
    "`{pm_status}` not found. Self-install at activation did not complete.",
    "`{pm_status}` is version {found}, but this migration requires {required} or newer.",
    "Run `{pm_status} ...` once the state root is known.",
    "",
  ].join("\n"), true);
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

// M-2(3): a real flag on the wrong subcommand, in an executed directive rather than a synopsis.
test("check 4 catches a real flag invoked on a subcommand that does not take it", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-util-doctor/steps/triage.md",
    "\n| `zy` | `uv run {pm_status} set-status --state-root S --scope story` |\n", true);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr,
    /invokes 'set-status --scope', but pm-status\.py registers that option on other subcommands only/);
});

// ---------------------------------------------------------------------------
// Check 23 (marketplace-deps). M-4 of the whole-branch review: marketplace.json's
// `dependencies` block declared three DEPRECATED shims as required, omitted two skills that
// really are required, and listed one BMad had removed. Nothing read it.

const MARKETPLACE_REL = ".claude-plugin/marketplace.json";
const INVENTORY_REL = "skills/l3io-util-doctor/assets/bmad-dependencies.json";

function readJson(root, rel) {
  return JSON.parse(fs.readFileSync(path.join(root, rel), "utf8"));
}

function writeJson(root, rel, value) {
  fs.writeFileSync(path.join(root, rel), JSON.stringify(value, null, 2) + "\n");
}

test("check 23 catches a deprecated shim declared as a required dependency", (t) => {
  const root = fixture(t);
  const mp = readJson(root, MARKETPLACE_REL);
  mp.dependencies["required-skills"].push("bmad-create-story");
  writeJson(root, MARKETPLACE_REL, mp);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /names 'bmad-create-story', which .* declares 'deprecated' — not 'required'/);
});

test("check 23 catches a required dependency the marketplace block omits", (t) => {
  const root = fixture(t);
  const mp = readJson(root, MARKETPLACE_REL);
  mp.dependencies["required-skills"] =
    mp.dependencies["required-skills"].filter((n) => n !== "bmad-sprint-planning");
  writeJson(root, MARKETPLACE_REL, mp);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /omits 'bmad-sprint-planning', which .* declares 'required'/);
});

test("check 23 catches a removed skill listed as optional", (t) => {
  const root = fixture(t);
  const mp = readJson(root, MARKETPLACE_REL);
  mp.dependencies["optional-skills"].push("bmad-ux-review");
  writeJson(root, MARKETPLACE_REL, mp);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /names 'bmad-ux-review', which .* declares 'removed' — not 'optional'/);
});

test("check 23 catches a non-bmad entry that is not a skill directory", (t) => {
  const root = fixture(t);
  const mp = readJson(root, MARKETPLACE_REL);
  mp.dependencies["optional-skills"].push("l3io-not-a-skill");
  writeJson(root, MARKETPLACE_REL, mp);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr,
    /names 'l3io-not-a-skill', which is neither a bmad-\* skill nor a directory under skills\//);
});

// The scope attack: the EXPECTED sets are derived from the inventory's `status` field, not
// typed into the checker. Reclassifying a skill there must move the requirement, so the
// marketplace block that was correct a moment ago becomes wrong. A hand-listed expectation
// would sail through this.
test("scope attack: reclassifying a skill in the inventory moves what check 23 demands", (t) => {
  const root = fixture(t);
  const inventory = readJson(root, INVENTORY_REL);
  const entry = inventory.skills.find((s) => s.name === "bmad-code-review");
  assert.ok(entry, "bmad-code-review is no longer in the inventory — re-anchor this test");
  assert.equal(entry.status, "required");
  entry.status = "optional";
  writeJson(root, INVENTORY_REL, inventory);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /dependencies\.optional-skills omits 'bmad-code-review'/);
  assert.match(r.stderr, /dependencies\.required-skills names 'bmad-code-review'/);
});

// An input set that can silently become empty is the failure this repo keeps meeting.
test("check 23 fails rather than passing when the inventory declares nothing", (t) => {
  const root = fixture(t);
  writeJson(root, INVENTORY_REL, { verified_against: "6.12.0", skills: [] });
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /declares no skills — check 23 would compare against an empty set/);
});

// ---------------------------------------------------------------------------
// check 24 — shared-pointers
//
// Every test below plants into skills/_shared/, because that is what the check reads: the
// authored source, not the generated per-skill copies (check:scripts owns those).
// ---------------------------------------------------------------------------
function read(root, rel) {
  return fs.readFileSync(path.join(root, rel), "utf8");
}

// Write a skills/_shared/ reference AND every per-skill copy of it, the way `npm run
// sync:scripts` would. Editing only the source is not a realistic tree: check 4's
// module-reference arm excludes a per-skill file by SHA-256 match against skills/_shared/,
// so a source edited alone turns every synced copy into "something this module chose to
// run" and reports unrelated offences. Check 24 reads the source, so mirroring costs it
// nothing.
function writeSharedReference(root, basename, text) {
  write(root, `skills/_shared/${basename}`, text);
  for (const skill of fs.readdirSync(path.join(root, "skills"))) {
    const rel = `skills/${skill}/references/${basename}`;
    if (fs.existsSync(path.join(root, rel))) write(root, rel, text);
  }
}

// Re-plant one of the pointers this check was built to catch: metrics-contract.md ships to
// l3io-pm-execute, l3io-pm-plan and l3io-pm-sync, and the sprint-closure step file it cites
// ships to l3io-pm-execute alone. Reverting the qualifier must turn CI red again.
test("check 24 catches a re-planted bare pointer in a shared reference", (t) => {
  const root = fixture(t);
  const before = read(root, "skills/_shared/metrics-contract.md");
  const planted = before.replace(
    "`l3io-pm-execute/steps/sprint/step-04-sprint-closure.md`",
    "`steps/sprint/step-04-sprint-closure.md`");
  assert.notEqual(planted, before, "the qualified pointer is gone — re-anchor this test");
  writeSharedReference(root, "metrics-contract.md", planted);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr,
    /metrics-contract\.md:\d+: `steps\/sprint\/step-04-sprint-closure\.md` does not exist in l3io-pm-plan, l3io-pm-sync/);
});

// The same shape in the file that made this class visible: status-files.md is the one shared
// reference l3io-util-doctor carries, so its onward pointers must hold in a doctor install too.
test("check 24 catches a bare onward pointer in the reference shipped to l3io-util-doctor", (t) => {
  const root = fixture(t);
  writeSharedReference(root, "status-files.md",
    read(root, "skills/_shared/status-files.md") +
    "\nSee `references/calibration-model.md` for the ratios.\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr,
    /status-files\.md:\d+: `references\/calibration-model\.md` does not exist in l3io-util-doctor/);
});

// THE SCOPE ATTACK. The corpus and the destination set both come from syncGroups, read out of
// the checked tree's own sync script -- not from a list in check-docs.mjs. A brand-new shared
// file, registered in an existing group, must be in scope the moment it is registered. A
// hand-kept corpus would sail straight past this. (`skills/_shared/steps/**` is already a
// wildcard row in CLAUDE.md's Shared Files table, so check 20 stays green.)
test("scope attack: a pointer in a newly registered shared file is in scope at once", (t) => {
  const root = fixture(t);
  write(root, "skills/_shared/steps/plan/step-99-brand-new.md",
    "# New\n\nSee `steps/execute/step-05-epic-loop.md` §5.\n");
  const syncRel = "scripts/sync-shared-scripts.mjs";
  const sync = read(root, syncRel);
  const anchor = `const planStepFiles = [\n`;
  assert.ok(sync.includes(anchor), "planStepFiles has moved — re-anchor this test");
  write(root, syncRel, sync.replace(anchor, anchor +
    `  { src: path.join(sharedDir, "steps", "plan", "step-99-brand-new.md"), ` +
    `rel: path.join("steps", "plan", "step-99-brand-new.md") },\n`));
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr,
    /step-99-brand-new\.md:\d+: `steps\/execute\/step-05-epic-loop\.md` does not exist in l3io-pm-plan/);
});

// A skill-qualified pointer is judged against the skill it names, so the replacement shape
// this class was fixed with is guarded too -- not just the bare shape it replaced.
test("check 24 catches a qualified pointer naming a skill that does not carry it", (t) => {
  const root = fixture(t);
  writeSharedReference(root, "config-resolution.md",
    read(root, "skills/_shared/config-resolution.md") +
    "\nSee `l3io-pm-help/references/metrics-contract.md` for the metrics.\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr,
    /config-resolution\.md:\d+: `l3io-pm-help\/references\/metrics-contract\.md` does not exist in l3io-pm-help/);
});

// FALSE-POSITIVE PIN. The exemption is attribution, and it must hold: a line that names a real
// skill directory which really does carry the file is correct prose, and reddening on it is
// the failure mode this repo already shipped once. This is the shape every cross-skill
// citation in the tree uses.
test("check 24 stays green on a bare pointer attributed to a skill that has it", (t) => {
  const root = fixture(t);
  writeSharedReference(root, "config-resolution.md",
    read(root, "skills/_shared/config-resolution.md") +
    "\n`l3io-pm-execute`'s own `steps/execute/step-04-arch-gate.md` runs the epic arch gate.\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

// ...and naming a skill that does NOT have it exempts nothing. Attribution is checked against
// the filesystem, not taken on the sentence's word.
test("check 24 does not accept attribution to a skill that lacks the file", (t) => {
  const root = fixture(t);
  writeSharedReference(root, "config-resolution.md",
    read(root, "skills/_shared/config-resolution.md") +
    "\n`l3io-pm-help`'s own `steps/execute/step-04-arch-gate.md` runs the epic arch gate.\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /`steps\/execute\/step-04-arch-gate\.md` does not exist in/);
});

// An input set that can silently become empty is the failure this repo keeps meeting: if the
// sync script cannot be read, check 24 must say so rather than pass over nothing.
test("check 24 fails loudly when it cannot derive its scope", (t) => {
  const root = fixture(t);
  write(root, "scripts/sync-shared-scripts.mjs", "throw new Error('broken');\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /check 24 cannot derive its scope/);
});

// ---------------------------------------------------------------------------
// check 17 — indirect invocation and non-literal variables
//
// Each of these was an entry in check 17's "Known gaps" list. One test per closure, planting
// the exact shape the entry named, plus the one entry that claimed a gap it did not have.
// ---------------------------------------------------------------------------
const STEP = (name, run) => `    - name: ${name}\n      run: ${run}\n`;

test("check 17: `bash -c '…python3 S.py'` is caught", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/checks.yml",
    STEP("indirect bash -c", "bash -c 'python3 skills/_shared/tests/test-pm-status.py'"), true);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /invokes a PEP-723 script with python3.*test-pm-status\.py/);
});

test("check 17: `sh -lc \"…python3 S.py\"` is caught, clustered short options and all", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/checks.yml",
    STEP("indirect sh -lc", 'sh -lc "python3 skills/_shared/tests/test-pm-status.py"'), true);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /invokes a PEP-723 script with python3.*test-pm-status\.py/);
});

// The old note claimed xargs was NOT caught, then a later fix round corrected the note. This
// pins the correction so the next rewrite of that paragraph cannot un-correct it.
test("check 17: `xargs python3 S.py` is caught, as the gap list says it is", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/checks.yml",
    STEP("xargs", "xargs python3 skills/_shared/tests/test-pm-status.py < list.txt"), true);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /unquoted `python3 skills\/_shared\/tests\/test-pm-status\.py` sequence/);
});

test("check 17: `PY=$(which python3); $PY S.py` resolves and is caught", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/checks.yml",
    STEP("which", "PY=$(which python3); $PY skills/_shared/tests/test-pm-status.py"), true);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /invokes a PEP-723 script with python3.*test-pm-status\.py/);
});

test("check 17: a variable from the workflow's own env: is resolved", (t) => {
  const root = fixture(t);
  const wf = "name: probe\non: [push]\nenv:\n  PY: python3\njobs:\n  a:\n" +
    "    runs-on: ubuntu-latest\n    steps:\n" +
    STEP("env var", "$PY skills/_shared/tests/test-pm-status.py");
  write(root, ".github/workflows/probe.yml", wf);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /probe\.yml:\d+: invokes a PEP-723 script with python3/);
});

test("check 17: a job-level env: var beats the workflow-level one it shadows", (t) => {
  const root = fixture(t);
  const wf = "name: probe\non: [push]\nenv:\n  PY: echo\njobs:\n  a:\n" +
    "    runs-on: ubuntu-latest\n    env:\n      PY: python3\n    steps:\n" +
    STEP("env var", "$PY skills/_shared/tests/test-pm-status.py");
  write(root, ".github/workflows/probe.yml", wf);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /probe\.yml:\d+: invokes a PEP-723 script with python3/);
});

// FALSE-POSITIVE PIN for the env: seeding. A `${{ }}` expression is not a literal, and an
// env var that is not an interpreter must not make an ordinary command look like one.
test("check 17: a non-literal env: value seeds nothing and reddens nothing", (t) => {
  const root = fixture(t);
  const wf = "name: probe\non: [push]\nenv:\n  PY: ${{ matrix.python }}\n  TOOL: echo\njobs:\n  a:\n" +
    "    runs-on: ubuntu-latest\n    steps:\n" +
    STEP("ok a", "$PY skills/_shared/tests/test-pm-status.py") +
    STEP("ok b", "$TOOL skills/_shared/tests/test-pm-status.py");
  write(root, ".github/workflows/probe.yml", wf);
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

// FALSE-POSITIVE PIN for the shell -c recursion: a shell invoked with something other than a
// script, and a `bash -c` whose script is clean, must both stay green.
test("check 17: `bash -c` around a clean uv run is not a violation", (t) => {
  const root = fixture(t);
  write(root, ".github/workflows/checks.yml",
    STEP("clean bash -c", "bash -c 'uv run skills/_shared/tests/test-pm-status.py'"), true);
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// ---------------------------------------------------------------------------
// check 4 — the facets closed in this round
// ---------------------------------------------------------------------------
const DIRECTIVE = (cmd) => "# Probe\n\n```bash\n" + cmd + "\n```\n";
// The probe lives in an EXISTING subdirectory of l3io-pm-execute, deliberately:
// skills/l3io-util-doctor/steps/ is where check 15 counts the doctor's modes (a new file
// there fails it), and l3io-pm's reference doc is the one that documents every pm-status
// subcommand, so check 4's module-reference arm has nothing to complain about either.
const PROBE_MD = "skills/l3io-pm-execute/references/zz-probe.md";

test("check 4: a short option on a pm-status.py invocation is caught", (t) => {
  const root = fixture(t);
  write(root, PROBE_MD, DIRECTIVE("uv run {pm_status} set-status -s done --state-root S --story K"));
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /invokes 'set-status -s', but pm-status\.py registers no such short option/);
});

test("check 4: a flag value outside argparse's choices is caught", (t) => {
  const root = fixture(t);
  write(root, PROBE_MD,
    DIRECTIVE("uv run {pm_status} verify --state-root S --scope story --story K --runtime martian"));
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /invokes 'verify --runtime martian', but pm-status\.py accepts only/);
});

// The choices came from `choices=list(RESOLUTIONS)`, a module constant -- not a literal list
// -- so this also pins the constant resolution.
test("check 4: a flag value from a choices=list(CONST) set is judged too", (t) => {
  const root = fixture(t);
  write(root, PROBE_MD,
    DIRECTIVE("uv run {pm_status} resolve-issue --state-root S --key BL-E001-001 --resolution maybe"));
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /invokes 'resolve-issue --resolution maybe', but pm-status\.py accepts only/);
});

test("check 4: a value-taking flag given no value is caught", (t) => {
  const root = fixture(t);
  write(root, PROBE_MD, DIRECTIVE("uv run {pm_status} set-status --state-root --story K --status done"));
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /invokes 'set-status --state-root' with no value/);
});

test("check 4: a required positional left out is caught", (t) => {
  const root = fixture(t);
  write(root, PROBE_MD, DIRECTIVE("uv run {pm_status} calibration --state-root S"));
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /invokes 'calibration' with no action, but pm-status\.py requires/);
});

test("check 4: a positional outside its choices is caught", (t) => {
  const root = fixture(t);
  write(root, PROBE_MD, DIRECTIVE("uv run {pm_status} calibration explode --state-root S"));
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /invokes 'calibration explode', but pm-status\.py accepts only/);
});

// FALSE-POSITIVE PINS for the value rule. An optional positional (`usage`'s transcript is
// nargs="*") must not be demanded, and a value written as a binding or a placeholder -- which
// is what every real directive writes -- must not be compared against choices.
test("check 4: an optional positional and placeholder values stay green", (t) => {
  const root = fixture(t);
  write(root, PROBE_MD,
    DIRECTIVE("uv run {pm_status} usage --state-root S --story {story_key} --model {model}\n" +
              "uv run {pm_status} verify --state-root S --scope {scope} --story {story_key} " +
              "--runtime {runtime}"));
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

// A usage synopsis is not valid shell; before the normalise-and-retry it was skipped whole,
// flags and all. Plant a bogus flag inside one and require it to be reported.
test("check 4: a bogus flag inside a usage-synopsis fragment is no longer skipped", (t) => {
  const root = fixture(t);
  write(root, PROBE_MD,
    DIRECTIVE("uv run {pm_status} set-actual --state-root S \\\n" +
              "  --node story (--story KEY | --epic ID) --nope 1"));
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /invokes 'set-actual --nope'/);
});

test("check 4: a spec-align.py flag its subcommand does not have is caught", (t) => {
  const root = fixture(t);
  write(root, PROBE_MD,
    DIRECTIVE("uv run {spec_align} check-pointers --nope X"));
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /invokes 'spec-align\.py check-pointers --nope'/);
});

// spec-align's `lease acquire --owner E001` is a nested subparser; its options must fold into
// `lease` or every real invocation of it would be reported. Green, and the bogus one red.
test("check 4: spec-align's nested lease subcommand folds its options into lease", (t) => {
  const root = fixture(t);
  write(root, PROBE_MD,
    DIRECTIVE("uv run {spec_align} lease acquire --owner E001 --ttl-minutes 30"));
  assert.equal(run(root).status, 0, "a real nested-subparser invocation must stay green");
  write(root, PROBE_MD,
    DIRECTIVE("uv run {spec_align} lease acquire --owner E001 --nope 1"));
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /invokes 'spec-align\.py lease --nope'/);
});

// The derived half of the live-docs forward arm: a hyphenated name whose first segment is a
// real subcommand's, on a line that also names pm-status.py. `add-test-run` reaches the check
// through this path and through no other.
test("check 4: a stale hyphenated subcommand on a pm-status.py line is caught", (t) => {
  const root = fixture(t);
  write(root, "docs/architecture.md",
    read(root, "docs/architecture.md") +
    "\n`pm-status.py` records evidence through `add-bogus-run`, appended per command.\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /documents pm-status\.py subcommand 'add-bogus-run'/);
});

// FALSE-POSITIVE PIN for that derived half, and the reason it is qualified on the line. Both
// of these are real, correct prose in the tree today: `update-ai-rules` is a doctor mode and
// `adr-justified` is a spec-align disposition, and both share a first segment with a real
// pm-status subcommand. On a line that does not name pm-status.py they must stay green.
test("check 4: a doctor mode and a disposition value are not subcommand claims", (t) => {
  const root = fixture(t);
  write(root, "docs/glossary.md",
    read(root, "docs/glossary.md") +
    "\nThe doctor's `update-ai-rules` mode rewrites them, and a finding may be `adr-justified`.\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

// ---------------------------------------------------------------------------
// Check 25 — doctor-mode-keywords
//
// Task 0C removed five doctor mode keywords by hand. Nothing mechanical would have caught a
// leftover reference to one: the router sends an unrecognised argument to the health check,
// so a stale `/l3io-util-doctor overlay` in a runtime directive silently runs a project scan
// instead of erroring. These tests attack the RULE and the SCOPE separately.
// ---------------------------------------------------------------------------

const DOCTOR_TABLE_ROW = "| `triage` | `steps/triage.md` |";

test("check 25: a live doc naming a removed mode keyword is caught", (t) => {
  const root = fixture(t);
  write(root, "docs/l3io-util-reference.md",
    read(root, "docs/l3io-util-reference.md") +
    "\nRun `/l3io-util-doctor overlay` to inspect the customization layer.\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /names \/l3io-util-doctor overlay, which is not a keyword/);
});

// SCOPE ATTACK. Deleting a reference from a file the check already reads proves little. This
// plants the violation in a file type the check was never told about by name -- a Python
// script, not markdown -- in a directory the corpus reaches only because it is DERIVED by
// walking skills/. pm-status.py and spec-align.py both print these invocations in real error
// messages, so this is the shape the check exists for.
test("check 25: scope attack — a stale keyword in a skills/ .py message is caught", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-util-doctor/scripts/probe-25.py",
    '#!/usr/bin/env python3\nprint("Run /l3io-util-doctor rename-epic-dirs first.")\n');
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /probe-25\.py:2: names \/l3io-util-doctor rename-epic-dirs/);
});

// SCOPE ATTACK on the valid set. If the keyword list were hand-kept here, renaming a live
// keyword in SKILL.md's routing table would change nothing. It must instead turn every real
// invocation of the old name red, because the table is the only source of truth for the set.
test("check 25: scope attack — the valid set follows SKILL.md's routing table", (t) => {
  const root = fixture(t);
  const skill = "skills/l3io-util-doctor/SKILL.md";
  const text = read(root, skill);
  assert.ok(text.includes(DOCTOR_TABLE_ROW), "the routing row this test edits must exist");
  write(root, skill, text.replace(DOCTOR_TABLE_ROW, "| `triage-x` | `steps/triage.md` |"));
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /names \/l3io-util-doctor triage, which is not a keyword/);
});

// A table that stops parsing must fail loudly, not derive an empty set and pass everything.
test("check 25: an unparseable routing table fails rather than passing vacuously", (t) => {
  const root = fixture(t);
  const skill = "skills/l3io-util-doctor/SKILL.md";
  write(root, skill, read(root, skill).replace(/^\| `/gm, "| "));
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /the routing table did not parse/);
});

// FALSE-POSITIVE PIN. The exemption in gap 1 is what keeps this check at zero false positives
// on the live tree; these three shapes are real, correct prose and must stay green.
test("check 25: prose after a bare command invocation is not a keyword claim", (t) => {
  const root = fixture(t);
  write(root, "docs/glossary.md",
    read(root, "docs/glossary.md") +
    "\nRun /l3io-util-doctor for a health check, /l3io-util-doctor once per upgrade, or\n" +
    "/l3io-util-doctor to install the helper.\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

// SECOND ARM. steps/sort-status.md pointed at steps/rename-epic-dirs.md after that mode was
// folded into the health check, and survived a hand sweep plus all six gates. A directive to
// load a file that is not there is worse than a stale keyword.
test("check 25: a step file pointing at a mode file the doctor does not carry is caught", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-util-doctor/steps/sort-status.md",
    read(root, "skills/l3io-util-doctor/steps/sort-status.md") +
    "\nApply the fix with `steps/rename-epic-dirs.md` (Rename Epic Dirs Mode).\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /points at steps\/rename-epic-dirs\.md, which skills\/l3io-util-doctor does not carry/);
});

// FALSE-POSITIVE PIN for the second arm: a pointer qualified with another skill resolves
// against THAT skill and must stay green. Both of the doctor's real cross-skill pointers are
// written this way.
test("check 25: a cross-skill qualified mode-file pointer is not a doctor pointer", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-util-doctor/steps/sort-status.md",
    read(root, "skills/l3io-util-doctor/steps/sort-status.md") +
    "\nThe same walk runs in `l3io-pm-help/steps/step-02-detect-layout.md`.\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

// ---- check 26 (resolver-invariant) ----
// These four tests import resolverInvariant() directly rather than spawning a subprocess,
// so they run against the real repo tree (not a fixture copy).

test('check 26: scope is derived from the tree, not enumerated', () => {
  const { scannedFiles } = resolverInvariant()
  assert.ok(scannedFiles.length > 20,
    `expected the scan to reach the whole skills tree, saw ${scannedFiles.length}`)
  assert.ok(scannedFiles.some(f => f.includes('l3io-util-doctor')),
    'the doctor must be in scope')
  assert.ok(scannedFiles.some(f => f.includes('l3io-pm-execute')),
    'every skill must be in scope, not only the doctor')
})

test('check 26: a planted markdown violation is caught', () => {
  const { violations } = resolverInvariant({
    extraSources: [{
      file: 'skills/fake-skill/steps/planted.md',
      text: 'mkdir -p {pm_state_root}/{status_dir}/epic-{nnn}/',
    }],
  })
  assert.ok(violations.some(v => v.includes('planted.md')),
    `expected the planted violation to be caught, got: ${JSON.stringify(violations)}`)
})

test('check 26: the canonical contract is exempt', () => {
  const { violations } = resolverInvariant({
    extraSources: [{
      file: 'skills/_shared/status-files.md',
      text: 'state/{planned,active,archived}/epic-{nnn}/sprint-{nn}/',
    }],
  })
  assert.ok(!violations.some(v => v.includes('_shared/status-files.md')),
    'the canonical contract must not be reported')
})

test('check 26: a planted pm-status.py violation outside the resolver section is caught', () => {
  const { violations } = resolverInvariant({
    plantInPmStatus: { line: 4000, text: '    d = os.path.join(state_root, "planned", "epic-{nnn}")' },
  })
  assert.ok(violations.some(v => v.includes('pm-status.py:4000')),
    `expected the planted pm-status violation, got: ${JSON.stringify(violations)}`)
})

test('check 26: SKILL.md is exempt', () => {
  const { violations } = resolverInvariant({
    extraSources: [{
      file: 'skills/fake-skill/SKILL.md',
      text: 'The state layout is `{pm_state_root}/planned/epic-{nnn}/`.',
    }],
  })
  assert.ok(!violations.some(v => v.includes('fake-skill/SKILL.md')),
    'SKILL.md files must be exempt from check 26')
})

test('check 26: test-*.py files are exempt', () => {
  const { violations } = resolverInvariant({
    extraSources: [{
      file: 'skills/fake-skill/scripts/tests/test-something.py',
      text: 'p = os.path.join(state_root, "planned", "epic-{nnn}")',
    }],
  })
  assert.ok(!violations.some(v => v.includes('test-something.py')),
    'test-*.py files must be exempt from check 26')
})

test('check 26: python comments and docstrings in .py files are skipped', () => {
  const { violations } = resolverInvariant({
    extraSources: [{
      file: 'skills/fake-skill/scripts/thing.py',
      text: '# example: state_root/planned/epic-{nnn}/epic.yaml\n"""example: state_root/active/epic-{nnn}/"""\nx = 1',
    }],
  })
  assert.ok(!violations.some(v => v.includes('fake-skill/scripts/thing.py')),
    'python comments and docstrings must be skipped')
})

test('check 26: description-only prose without active verb is exempt', () => {
  const { violations } = resolverInvariant({
    extraSources: [{
      file: 'skills/fake-skill/steps/prose.md',
      text: 'The layout is `{pm_state_root}/planned/epic-{nnn}/epic.yaml` -- pure prose.',
    }],
  })
  assert.ok(!violations.some(v => v.includes('prose.md')),
    'prose without a filesystem verb must be exempt')
})

test('check 26: active verb with state path is caught', () => {
  const { violations } = resolverInvariant({
    extraSources: [{
      file: 'skills/fake-skill/steps/directive.md',
      text: 'ls -d {pm_state_root}/planned/epic-{nnn}/',
    }],
  })
  assert.ok(violations.some(v => v.includes('directive.md')),
    'active verb with state path must be flagged')
})

test('check 26: check26:allow marker on preceding line suppresses the flag', () => {
  const { violations } = resolverInvariant({
    extraSources: [{
      file: 'skills/fake-skill/steps/suppressed.md',
      text: '# check26:allow reason: existence probe pending exists verb\nls -d {pm_state_root}/planned/epic-{nnn}/',
    }],
  })
  assert.ok(!violations.some(v => v.includes('suppressed.md')),
    'marker on preceding line must suppress the flag')
})
