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

// ---- check 16 (module-yaml-agreement) ----

test("check 16: siblings sharing a code disagreeing on description is caught", (t) => {
  const root = fixture(t);
  const p = path.join(root, "skills", "l3io-pm-help", "module.yaml");
  const before = fs.readFileSync(p, "utf8");
  fs.writeFileSync(p, before.replace(/^description: .*$/m, 'description: "Something else."'));
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /sharing `code: l3io-pm` disagree on `description`/);
});

test("check 16: a divergent post-install-notes block scalar is caught", (t) => {
  const root = fixture(t);
  const p = path.join(root, "skills", "l3io-pm-sync", "module.yaml");
  fs.appendFileSync(p, "\nextra-key: >\n  only on this sibling\n");
  fs.writeFileSync(p, fs.readFileSync(p, "utf8")
    .replace(/^post-install-notes: >$/m, "post-install-notes: >\n  A different first line."));
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /disagree on `post-install-notes`/);
});

test("check 16: a module with only one module.yaml is not compared", (t) => {
  const root = fixture(t);
  // l3io-arch and l3io-sec each have exactly one file; changing one must stay clean.
  const p = path.join(root, "skills", "l3io-arch-review", "module.yaml");
  const before = fs.readFileSync(p, "utf8");
  fs.writeFileSync(p, before.replace(/^description: .*$/m, 'description: "Solo module, changed."'));
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test("check 16: scope attack — a new skill joining a module must agree too", (t) => {
  const root = fixture(t);
  const dir = path.join(root, "skills", "l3io-pm-brandnew");
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, "module.yaml"),
    'code: l3io-pm\nname: "Different Name"\ndescription: "New sibling."\n' +
    "module_version: 0.0.1\ndefault_selected: true\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /sharing `code: l3io-pm` disagree on/);
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

// ---- check 17 (bmad-dependency-inventory) ----
//
// The check's scope is derived by walking skills/ markdown plus every skills/<dir>/module.yaml,
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

test("check 17: an undeclared bmad-* token is caught", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/x-undeclared.md",
        "Spawn `bmad-frobnicate` with the story path.\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /x-undeclared\.md:1: names 'bmad-frobnicate', not declared in/);
});

test("check 17: a step file dispatching a removed skill fails", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/x.md",
        "Spawn `bmad-dev-story` subagent with the story path.\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /dispatches removed skill 'bmad-dev-story'/);
});

test("check 17: a module.yaml naming an undeclared skill is caught", (t) => {
  const root = fixture(t);
  // Appended as a comment so check 16 (module-yaml-agreement) sees no new field and stays green:
  // this must fail on check 17 alone.
  write(root, "skills/l3io-arch-review/module.yaml", "\n# also requires bmad-frobnicate\n", true);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /l3io-arch-review\/module\.yaml:\d+: names 'bmad-frobnicate', not declared in/);
});

test("check 17: an entry missing a status-required field is caught", (t) => {
  const root = fixture(t);
  editInventory(root, (inv) => {
    delete inv.skills.find((e) => e.name === "bmad-code-review").module;
  });
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /'bmad-code-review' is required but names no module/);
});

test("check 17: a duplicate inventory entry is caught", (t) => {
  const root = fixture(t);
  editInventory(root, (inv) => {
    inv.skills.push({ name: "bmad-help", status: "optional", module: "bmm" });
  });
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /duplicate entry 'bmad-help'/);
});

test("check 17 scope attack: a brand-new skills/<dir>/ with a new step file is caught", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-brandnew-gate/steps/step-new.md",
        "Dispatch `bmad-frobnicate` for the gate review.\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /l3io-pm-brandnew-gate\/steps\/step-new\.md:1: names 'bmad-frobnicate'/);
});

test("check 17: the real tree passes", (t) => {
  const r = run(fixture(t));
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test("check 17: a removed skill named beside its replacement is allowed", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/x-mapped.md",
        "Migrated: `bmad-review-adversarial-general` is now `bmad-review`.\n");
  const r = run(root, ["-v"]);
  assert.equal(r.status, 0, r.stderr + r.stdout);
  assert.match(r.stdout,
               /x-mapped\.md:1: names removed skill 'bmad-review-adversarial-general' as history/);
});

test("check 17: a removed skill on a line saying legacy is allowed", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/x-legacy.md",
        "The `bmad-ux-review` name is legacy.\n");
  const r = run(root, ["-v"]);
  assert.equal(r.status, 0, r.stderr + r.stdout);
  assert.match(r.stdout, /x-legacy\.md:1: names removed skill 'bmad-ux-review' as history/);
});

// The two cases below look alike and prove different things; both are needed.
//
// This one plants "removed", which is NOT one of check 17's three evidence arms. It therefore
// fails wherever it sits, and that is all it shows: that a plausible-sounding explanatory word
// is not an arm. It does NOT test the same-line rule — widening the `legacy` arm to test the
// whole joined file leaves this case failing exactly as before, i.e. green.
test("check 17: 'removed' is not an evidence arm, so it never excuses a dispatch", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/x-window.md",
        "This skill was removed upstream.\n\n\n\nSpawn `bmad-dev-story` subagent.\n");
  const r = run(root);
  assert.equal(r.status, 1, "check 1's ±4-line window would have allowed this; check 17 must not");
  assert.match(r.stderr, /dispatches removed skill/);
});

// This one carries a REAL arm (`legacy`) four lines from the dispatch, so it is the case that
// actually discriminates line-scoped evidence from file-scoped evidence: it fails at HEAD
// (correct — the dispatch line itself carries nothing) and passes the moment the arm is widened
// from `.test(line)` to `.test(lines.join("\n"))`. Verified by mutation, both directions.
// Line 1 is allowed on its own merits — it names the removed skill AND says `legacy`, on one
// line — which is precisely why the failure must come from line 5 and nowhere else.
test("check 17: the word `legacy` four lines away does NOT excuse a dispatch", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/x-window-legacy.md",
        "The bmad-dev-story skill is legacy.\n\n\n\nSpawn `bmad-dev-story` subagent.\n");
  const r = run(root);
  assert.equal(r.status, 1, "evidence must be on the dispatch line; a whole-file test would pass this");
  assert.match(r.stderr, /x-window-legacy\.md:5: dispatches removed skill 'bmad-dev-story'/);
});

test("check 17: a leading underscore yields no token (_bmad-output, _bmad-frobnicate)", (t) => {
  const root = fixture(t);
  // _bmad-output is declared not-a-skill, so on its own it would pass either way; the second
  // path is undeclared and fails the moment the lookbehind is dropped from BMAD_TOKEN_RE.
  write(root, "skills/l3io-pm-execute/steps/x-underscore.md",
        "Reports land in `{project-root}/_bmad-output/` and `{project-root}/_bmad-frobnicate/`.\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test("check 17: not-a-skill tokens are skipped via their status", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/x-not-a-skill.md",
        "The `bmad-defer:` marker in a `bmad-l3io-extensions` checkout.\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test("check 17: a not-a-skill entry without a reason is caught", (t) => {
  const root = fixture(t);
  editInventory(root, (inv) => {
    delete inv.skills.find((e) => e.name === "bmad-defer").reason;
  });
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /'bmad-defer' is not-a-skill but gives no reason/);
});

test("check 17: a fallback naming an undeclared skill is caught", (t) => {
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
test("check 17: an existence probe naming a removed skill is allowed", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/x-probe.md",
        "```bash\nls {project-root}/.claude/skills/bmad-dev-story/SKILL.md 2>/dev/null\n```\n");
  const r = run(root);
  assert.equal(r.status, 0, "a probe line cannot dispatch anything; it must pass");
});

// The probe arm has the same substring hole the replaced_by arm was hardened against: a bare
// line.includes("ls ") is satisfied by "tools ", "details " or "controls ". Case 15 passes under
// both the weak and the strong predicate, so without this test a revert would be silent.
test("check 17: a word ending in 'ls' does not make a dispatch line a probe", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/x-tools.md",
        "Check the tools installed under `.claude/skills/` before spawning `bmad-dev-story`.\n");
  const r = run(root);
  assert.equal(r.status, 1, "'tools ' plus '.claude/' is not an `ls` probe");
  assert.match(r.stderr, /dispatches removed skill 'bmad-dev-story'/);
});

// Case 16 — the token-boundary hole. bmad-ux-review's replaced_by is bmad-ux, which is a
// SUBSTRING of it, so a naive includes() check would let the guard pass its own worst case.
test("check 17: replaced_by must match as a token, not a substring", (t) => {
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

test("check 17 accepts a deprecated entry carrying deprecated_in and replaced_by", (t) => {
  const root = fixture(t);
  setStatus(root, "bmad-create-story",
    { status: "deprecated", deprecated_in: "6.12.0", replaced_by: "bmad-build",
      removed_in: undefined });
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

test("check 17 rejects a deprecated entry missing deprecated_in", (t) => {
  const root = fixture(t);
  setStatus(root, "bmad-create-story",
    { status: "deprecated", replaced_by: "bmad-build", deprecated_in: undefined,
      removed_in: undefined });
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /is deprecated but lacks replaced_by\/deprecated_in/);
});

// ---- check 18 (pep723-invocation) ----

test("check 18: a PEP-723 helper invoked with python3 is caught", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/bad-invocation.md",
    "```bash\npython3 {pm_status} set-status --state-root x\n```\n");
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /invokes a PEP-723 script with python3/);
});

test("check 18: uv run of the same helper passes", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/good-invocation.md",
    "```bash\nuv run {pm_status} set-status --state-root x\n```\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

test("check 18: the documented python3 fallback line is allowed", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/fallback.md",
    "If `uv` is unavailable, use `python3` instead.\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// The word-boundary case from the design table: "--use-python3" must not be mistaken for the
// `python3` invocation token, and a script path invoked correctly with `uv run` must not trip
// the check just because it also ends in `.py`.
test("check 18: word boundary holds and an unrelated uv run line passes", (t) => {
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
test("check 18: a same-line uv-unavailable qualifier exempts a real invocation", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/steps/same-line-fallback.md",
    "If `uv` is unavailable, run `python3 {pm_status} verify --state-root x` instead.\n");
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// Scope attack: every other check-18 test above plants under skills/l3io-pm-execute/steps/.
// This one plants under a different skill AND a different subdirectory (assets/, not steps/)
// to prove walkMarkdown("skills") actually reaches there rather than the check having been
// implicitly scoped to steps/ files by every test happening to live in one.
test("check 18 scope attack: a violation under a different skill's assets/ is caught", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-util-doctor/assets/scope-attack.md",
    "```bash\npython3 {skill-root}/scripts/detect-platform.py {project-root}\n```\n");
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /scope-attack\.md:\d+: invokes a PEP-723 script with python3/);
});

// ---- check 19 (docs-check-count) ----
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

test("check 19: the correct count passes", (t) => {
  const root = fixture(t);
  const r = run(root);
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test("check 19: a stated count one below the real one is caught in CLAUDE.md", (t) => {
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

test("check 19: a stated count one below the real one is caught in scripts/CLAUDE.md", (t) => {
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

test("check 19: an invocation added without a header entry trips the derivations-disagree branch", (t) => {
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

// ---- check 20 (derived-counts) ----

test("check 20: a stale total-skill count is caught", (t) => {
  const root = fixture(t);
  const p = path.join(root, "docs", "getting-started.md");
  const before = fs.readFileSync(p, "utf8");
  fs.writeFileSync(p, before.replace("New to the eight skills?", "New to the nine skills?"));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /says "nine" skill\(s\), but the package has 8/);
});

test("check 20: a stale module count is caught", (t) => {
  const root = fixture(t);
  const p = path.join(root, "CLAUDE.md");
  const before = fs.readFileSync(p, "utf8");
  fs.writeFileSync(p, before.replace("package with four modules:", "package with five modules:"));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /says "five" module\(s\), but the package has 4/);
});

test("check 20: scope attack — adding a skill directory must break the count claims", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-newthing/SKILL.md", "---\nname: l3io-newthing\ndescription: d\n---\n");
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /skill\(s\), but the package has 9/);
});

test("check 20: a reworded claim sentence fails loudly rather than passing", (t) => {
  const root = fixture(t);
  const p = path.join(root, "docs", "l3io-pm-reference.md");
  const before = fs.readFileSync(p, "utf8");
  fs.writeFileSync(p, before.replace(/four skills that cover the delivery lifecycle/,
    "several skills covering the lifecycle"));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /claim was not found — has the sentence been reworded/);
});
