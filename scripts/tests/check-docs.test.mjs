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
  "twenty-four", "twenty-five"];

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
  write(root, rel, text.replace(
    "| `stats` | `steps/stats.md` | read-only — plan-aware progress dashboard |",
    "| `stats` | `steps/stats.md` | read-only — plan-aware progress dashboard |\n" +
      "| `zzz-extra` | `steps/zzz-extra-mode.md` | test-only extra mode |"));
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
// decoration that is not shell at all. These two shapes are why: no shell parser accepts a
// markdown table row, and a list bullet lexes with `-` as argv[0]. Both must stay caught.
for (const [label, line] of [
  ["a list bullet", "- python3 {pm_status} set-status --state-root x"],
  ["a table cell", "| `python3 {pm_status} verify` | wrong |"],
]) {
  test(`check 17 Task 17: a directive decorated as ${label} is still caught in markdown`, (t) => {
    const root = fixture(t);
    write(root, "skills/l3io-pm-execute/steps/task17-decorated.md", `${line}\n`);
    const r = run(root);
    assert.equal(r.status, 1, r.stdout);
    assert.match(r.stderr, /task17-decorated\.md:\d+: (invokes a PEP-723 script with python3|contains an unquoted python3-plus-script sequence)/);
  });
}

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
