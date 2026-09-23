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

// Every fixture carries the multi-module marker skills/module.yaml, because check 1 requires
// it of any tree with a skills/ directory. Tests that are about the marker itself overwrite or
// delete it explicitly.
const MARKER = "multi_module_marketplace: true\n";

// Every fixture also carries a .claude-plugin/marketplace.json, because check 8 derives its
// scope from that file and fails closed when it is absent -- a checker that skipped a missing
// marketplace would report success over the empty set (root CLAUDE.md §4). The synthetic
// fixtures declare no plugins; the tests that are about check 8 write their own plugins array.
const EMPTY_MARKETPLACE = JSON.stringify({ name: "fixture", plugins: [] }, null, 2) + "\n";

function fixture(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "check-module-"));
  fs.mkdirSync(path.join(dir, "skills"), { recursive: true });
  fs.writeFileSync(path.join(dir, "skills", "module.yaml"), MARKER);
  fs.mkdirSync(path.join(dir, ".claude-plugin"), { recursive: true });
  fs.writeFileSync(path.join(dir, ".claude-plugin", "marketplace.json"), EMPTY_MARKETPLACE);
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
  const moduleYaml = `code: ${code}\nname: "${dir}"\ndescription: "test module"\n`;
  write(root, `skills/${dir}/assets/module.yaml`, moduleYaml);
  // A standalone (non-*-setup) module home must also carry the byte-identical skill-root copy
  // BMad's installer discovers -- check 1(a). A *-setup home must not.
  if (!dir.endsWith("-setup")) write(root, `skills/${dir}/module.yaml`, moduleYaml);
  write(root, `skills/${dir}/assets/module-setup.md`, "# setup\n");
  write(root, `skills/${dir}/assets/module-help.csv`, `skill,module,description\n${dir},${code},test skill\n`);
  write(root, `skills/${dir}/scripts/merge-config.py`, "# merge-config\n");
  write(root, `skills/${dir}/scripts/merge-help-csv.py`, "# merge-help-csv\n");
}

// ---- check 1 (discovery-layout) ----
//
// This rule is the one the whole-branch review's C-1/H-1 landed on, and it replaced its own
// inverse: `no-root-module-yaml` forbade exactly the file BMad's installer discovers for a
// non-*-setup skill. Every assertion below was reproduced against bmad-method 6.12.0's
// tools/installer/project-root.js before being written here.

test("check:module rejects a module.yaml at a skill root that is not a standalone module home", (t) => {
  const root = fixture(t);
  write(root, "skills/l3io-pm-execute/module.yaml", "code: l3io-pm\n");
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /module\.yaml at a skill root that is not a standalone module home/);
});

test("check:module rejects a standalone module home with no skill-root module.yaml", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "solo", "solo");
  fs.rmSync(path.join(root, "skills/solo/module.yaml"));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /standalone module home skills\/solo has no skills\/solo\/module\.yaml/);
});

test("check:module rejects a skill-root module.yaml that has drifted from its assets copy", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "solo", "solo");
  write(root, "skills/solo/module.yaml", "code: solo\nname: S\ndescription: drifted\n");
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /skills\/solo\/module\.yaml and skills\/solo\/assets\/module\.yaml differ/);
});

test("check:module rejects a *-setup module home carrying a skill-root module.yaml", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "pm-setup", "pm");
  write(root, "skills/pm-setup/module.yaml", "code: pm\n");
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /module\.yaml at a skill root that is not a standalone module home/);
});

test("check:module rejects a missing skills/module.yaml marker", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "solo", "solo");
  fs.rmSync(path.join(root, "skills/module.yaml"));
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /skills\/module\.yaml is missing/);
});

// The scope attack, not just the rule: the marker being PRESENT is not the property that
// matters -- what matters is that it declares no code, no name and no agents. A marker that
// grew a `code:` would make every module's settings land under that one code, and a marker
// that grew an `agents:` array would emit one agent block per installed module. Both are
// duplicate TOML tables, which is a config layer no skill can read.
for (const [field, yaml] of [
  ["code", "code: l3io-pm\nmulti_module_marketplace: true\n"],
  ["name", "name: Everything\nmulti_module_marketplace: true\n"],
  ["agents", "multi_module_marketplace: true\nagents:\n  - code: redteam\n"],
]) {
  test(`check:module rejects a skills/module.yaml marker declaring '${field}'`, (t) => {
    const root = fixture(t);
    writeModuleHome(root, "solo", "solo");
    write(root, "skills/module.yaml", yaml);
    const r = run(root);
    assert.equal(r.status, 1);
    assert.match(r.stderr, new RegExp(`skills/module\\.yaml declares '${field}'`));
  });
}

test("check:module rejects a skills/module-help.csv beside the marker", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "solo", "solo");
  write(root, "skills/module-help.csv", "module,skill,display-name\n");
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /skills\/module-help\.csv exists/);
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

// `_meta` is the one reserved value in the `skill` column that is not a skill:
// bmad-help/SKILL.md ("Module docs") defines it as the row carrying a module's documentation
// URL, and both of BMad 6.12.0's own catalogs ship one. Before this exemption, adding the row
// BMad's own format prescribes failed check 7 as an "orphan capability entry".
test("check:module accepts the reserved _meta documentation row", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "solo", "solo");
  write(root, "skills/solo/assets/module-help.csv",
    "module,skill,display-name,menu-code,description,action,args,phase,preceded-by,followed-by,required,output-location,outputs\n" +
    "Solo,_meta,,,,,,,,,false,https://example.invalid/docs/solo.md,\n" +
    'Solo,solo,Solo,SOL,"Real skill, real row.",,,anytime,,,false,,report\n');
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
});

// THE SCOPE ATTACK on that exemption: it must cover the one literal `_meta` and nothing more.
// A rule that skipped every underscore-prefixed value, or every row with an empty
// display-name, would pass this file too -- and then no phantom row would ever be caught
// again, because a phantom is exactly a row whose skill column names nothing on disk.
test("check:module still rejects a non-_meta phantom row beside a real _meta row", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "solo", "solo");
  write(root, "skills/solo/assets/module-help.csv",
    "module,skill,display-name,menu-code,description,action,args,phase,preceded-by,followed-by,required,output-location,outputs\n" +
    "Solo,_meta,,,,,,,,,false,https://example.invalid/docs/solo.md,\n" +
    "Solo,__meta,,,,,,,,,false,https://example.invalid/docs/nope.md,\n" +
    'Solo,solo-setup,Setup,SST,"Phantom row for a skill that was never built.",configure,,anytime,,,false,,config\n');
  const r = run(root);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /row names skill 'solo-setup', which is not a directory under skills\//);
  assert.match(r.stderr, /row names skill '__meta', which is not a directory under skills\//);
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

// ---- check 8 (plugin-resolver-strategy) ----
//
// BMad's installer resolves every plugin in .claude-plugin/marketplace.json through
// PluginResolver's five strategies. Strategies 1-4 use the authored module.yaml +
// module-help.csv; strategy 5 SYNTHESIZES a stub catalog from SKILL.md frontmatter --
// `action: activate` on every row, title-cased display names, generated menu codes, no
// relationships, no output-location -- and the install still exits 0. Nothing warns. The
// authored CSVs are simply not used.
//
// This package has already shipped that: the gitignored _bmad/ tree from the 2026-09-14
// install holds exactly those stub rows, including one for `l3io-util-cleanup`, a skill that
// no longer exists.
//
// Every assertion below was reproduced against bmad-method 6.12.0's
// tools/installer/modules/plugin-resolver.js before being written here.

function writeMarketplace(root, plugins) {
  write(root, ".claude-plugin/marketplace.json", JSON.stringify({ name: "fixture", plugins }, null, 2) + "\n");
}

// Give a fixture skill enough shape to be a standalone module home for check 8's purposes.
// (writeModuleHome already writes assets/module.yaml + assets/module-help.csv, which is what
// PluginResolver strategies 2/3/4 look for.)

// THE SCOPE ATTACK. Deleting a module-help.csv is the easy mutation: it tests the rule. What
// matters here is the rule's REACH -- whether the check still sees a plugin after the plugin
// itself changes shape. `l3io-arch` resolves by strategy 3 for one reason only:
// _trySingleStandalone requires `skillPaths.length === 1`. Adding a second skill to its
// `skills` array -- an entirely ordinary change, nothing deleted, every authored file still in
// place -- drops it to synthesis, silently. A check that derived its plugin set or its skill
// lists from the filesystem instead of marketplace.json would not notice.
test("check:module rejects a plugin that a second skill drops to synthesized fallback", (t) => {
  const root = fixtureFromRepo(t);
  const mpPath = path.join(root, ".claude-plugin", "marketplace.json");
  const marketplace = JSON.parse(fs.readFileSync(mpPath, "utf8"));
  const arch = marketplace.plugins.find((p) => p.name === "l3io-arch");
  assert.ok(arch, "fixture precondition: marketplace.json declares an l3io-arch plugin");
  assert.deepEqual(arch.skills, ["./skills/l3io-arch-review"], "fixture precondition: one skill");
  arch.skills.push("./skills/l3io-pm-help");
  fs.writeFileSync(mpPath, JSON.stringify(marketplace, null, 2) + "\n");

  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /plugin 'l3io-arch'/);
  assert.match(r.stderr, /strategy 5/);
});

// The positive half of the same fact: the real tree resolves every plugin by an authored
// strategy, and -v names which one, so a reader can see what the check concluded rather than
// trusting that it concluded anything.
test("the real repository resolves every plugin by an authored PluginResolver strategy", (t) => {
  const root = fixtureFromRepo(t);
  const r = run(root, ["-v"]);
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /plugin 'l3io-pm' resolves by PluginResolver strategy 2/);
  assert.match(r.stdout, /plugin 'l3io-sec' resolves by PluginResolver strategy 3/);
  assert.match(r.stdout, /plugin 'l3io-util' resolves by PluginResolver strategy 3/);
  assert.match(r.stdout, /plugin 'l3io-arch' resolves by PluginResolver strategy 3/);
});

// _tryMultipleStandalone's partial-match branch: `resolved.length === skillPaths.length` or
// `return null`. One skill without both files is enough to synthesize the whole plugin.
test("check:module rejects a two-skill plugin where only one skill carries the module files", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "alpha", "alpha");
  write(root, "skills/beta/SKILL.md", "---\nname: beta\n---\n");
  writeMarketplace(root, [{ name: "alpha", skills: ["./skills/alpha", "./skills/beta"] }]);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /plugin 'alpha' .*strategy 5/s);
});

// The same plugin, with the second skill made a module home too, resolves by strategy 4.
test("check:module passes a two-skill plugin where both skills carry the module files", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "alpha", "alpha");
  writeModuleHome(root, "beta", "beta");
  writeMarketplace(root, [{ name: "alpha", skills: ["./skills/alpha", "./skills/beta"] }]);
  const r = run(root, ["-v"]);
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /plugin 'alpha' resolves by PluginResolver strategy 4/);
});

// _trySetupSkill `continue`s past a -setup skill missing either file, so a multi-skill plugin
// whose setup home lost its CSV synthesizes even though the directory is named correctly.
test("check:module rejects a plugin whose -setup home is missing module-help.csv", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "multi-setup", "multi");
  write(root, "skills/multi-a/SKILL.md", "---\nname: multi-a\n---\n");
  fs.rmSync(path.join(root, "skills/multi-setup/assets/module-help.csv"));
  writeMarketplace(root, [{ name: "multi", skills: ["./skills/multi-setup", "./skills/multi-a"] }]);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /plugin 'multi' .*strategy 5/s);
});

// resolve() filters a listed skill path that does not exist on disk BEFORE any strategy runs,
// so `skillPaths.length === 1` is a count of EXISTING skills, not of listed ones. A check that
// counted the marketplace array instead would call this plugin multi-skill and wrongly expect
// strategy 4. Pinned here because it is a condition the summary of the resolver did not state.
test("check:module ignores a marketplace skill path that does not exist on disk", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "alpha", "alpha");
  writeMarketplace(root, [{ name: "alpha", skills: ["./skills/alpha", "./skills/never-built"] }]);
  const r = run(root, ["-v"]);
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /plugin 'alpha' resolves by PluginResolver strategy 3/);
});

// _readModuleYaml returns yaml.parse(content) and every strategy bails on a falsy result, so
// an EMPTY module.yaml is not a module.yaml -- existence alone is not the resolver's test.
test("check:module rejects a plugin whose module.yaml parses to nothing", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "alpha", "alpha");
  write(root, "skills/alpha/assets/module.yaml", "\n");
  write(root, "skills/alpha/module.yaml", "\n");
  writeMarketplace(root, [{ name: "alpha", skills: ["./skills/alpha"] }]);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /plugin 'alpha' .*strategy 5/s);
});

// resolve() returns [] for a plugin with no skills array and for one whose skills all fail to
// resolve: no module is installed at all, which is worse than synthesis, not better.
test("check:module rejects a plugin that declares no skills", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "alpha", "alpha");
  writeMarketplace(root, [{ name: "alpha" }]);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /plugin 'alpha' declares no 'skills'/);
});

// Fail closed on the scope source itself. A checker that skipped a missing or unreadable
// marketplace.json would report success over the empty set -- the failure mode root CLAUDE.md
// §4 exists to prevent.
test("check:module reports a missing .claude-plugin/marketplace.json", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "alpha", "alpha");
  fs.rmSync(path.join(root, ".claude-plugin", "marketplace.json"));
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /\.claude-plugin\/marketplace\.json is missing/);
});

test("check:module reports a marketplace.json with no plugins array", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "alpha", "alpha");
  write(root, ".claude-plugin/marketplace.json", JSON.stringify({ name: "fixture" }) + "\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /declares no 'plugins' array/);
});

// ---- check 9 (help-registration) ----
//
// Every mode keyword a skill documents in its SKILL.md routing table must either carry a
// module-help.csv row or be explicitly excluded in that table's own `Menu` column. The
// exclusion set is read from the table -- never from a list inside the checker -- because a
// hand-kept list of exempt keywords is exactly the drift this rule exists to stop (root
// CLAUDE.md §4).
//
// The rule's SCOPE is attacked as hard as the rule: a table whose `Menu` column is deleted
// makes every keyword required rather than exempt, an unknown `Menu` value fails instead of
// quietly excluding, and a skill whose mode files exist but whose whole table has been
// deleted fails rather than passing over an empty expectation set.

const HELP_CSV_HEADER =
  "module,skill,display-name,menu-code,description,action,args,phase,preceded-by,followed-by,required,output-location,outputs\n";

// A skill that documents its modes the way the real ones do: a "Recognized keywords"
// paragraph, a routing table, and one steps/<mode>.md file per row.
function writeKeywordSkill(root, dir, rows, { menuColumn = true, table = true } = {}) {
  const header = menuColumn
    ? "| Keyword | Load | Menu | Notes |\n|---|---|---|---|\n"
    : "| Keyword | Load | Notes |\n|---|---|---|\n";
  const body = rows
    .map((r) => (menuColumn
      ? `| \`${r.keyword}\` | \`${r.load}\` | ${r.menu} | note |\n`
      : `| \`${r.keyword}\` | \`${r.load}\` | note |\n`))
    .join("");
  write(root, `skills/${dir}/SKILL.md`,
    `# ${dir}\n\n**Recognized keywords** — match the argument and load that file:\n\n` +
    (table ? header + body : "") + "\n**Everything else** → the default.\n");
  for (const r of rows) write(root, `skills/${dir}/${r.load}`, `# ${r.keyword}\n`);
}

// The canonical failure: a keyword documented in the table, marked as registered, with no row
// anywhere. This is the drift Tasks 1-6 corrected by hand.
test("check:module rejects a keyword-table entry with no module-help.csv row", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "solo", "solo");
  writeKeywordSkill(root, "solo", [
    { keyword: "stats", load: "steps/stats.md", menu: "registered" },
    { keyword: "brand-new-mode", load: "steps/brand-new-mode.md", menu: "registered" },
  ]);
  write(root, "skills/solo/assets/module-help.csv", HELP_CSV_HEADER +
    'Solo,solo,Stats,SST,"Render the dashboard.",stats,,anytime,,,false,,report\n');
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /brand-new-mode/);
});

// The shape the real tree ships: a `default` keyword served by the module's bare-invocation
// row (empty `action`, BMad's convention), a `registered` keyword matched by action, and
// excluded keywords carrying no row at all.
test("check:module passes a keyword table whose registered keywords all have rows", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "solo", "solo");
  writeKeywordSkill(root, "solo", [
    { keyword: "check", load: "steps/health-check.md", menu: "default" },
    { keyword: "stats", load: "steps/stats.md", menu: "registered" },
    { keyword: "migrate-state", load: "steps/migrate-state.md", menu: "health-check" },
    { keyword: "setup", load: "steps/setup.md", menu: "not-a-capability" },
  ]);
  write(root, "skills/solo/assets/module-help.csv", HELP_CSV_HEADER +
    'Solo,solo,Doctor,SDR,"Scan project state.",,,anytime,,,false,,findings\n' +
    'Solo,solo,Stats,SST,"Render the dashboard.",stats,,anytime,,,false,,report\n');
  const r = run(root, ["-v"]);
  assert.equal(r.status, 0, r.stderr);
});

// A `default` keyword needs the bare-invocation row to actually exist: with every row
// carrying an action, nothing routes the bare command.
test("check:module rejects a default keyword with no empty-action row", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "solo", "solo");
  writeKeywordSkill(root, "solo", [
    { keyword: "check", load: "steps/health-check.md", menu: "default" },
  ]);
  write(root, "skills/solo/assets/module-help.csv", HELP_CSV_HEADER +
    'Solo,solo,Stats,SST,"Render the dashboard.",stats,,anytime,,,false,,report\n');
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /`check`/);
});

// SCOPE ATTACK 1: the exclusion marker itself. An unrecognised `Menu` value -- a typo, or a
// new word someone invents -- must fail loudly. A rule that treated "anything that is not
// `registered`" as excluded would let one keystroke silently drop a keyword out of scope.
test("check:module rejects an unrecognised Menu value in a keyword table", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "solo", "solo");
  writeKeywordSkill(root, "solo", [
    { keyword: "stats", load: "steps/stats.md", menu: "healthcheck" },
  ]);
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /healthcheck/);
});

// SCOPE ATTACK 2: deleting the Menu column must make the rule STRICTER, never weaker. A table
// with no exclusion column claims every keyword it lists is registered.
test("check:module requires a row for every keyword when the table has no Menu column", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "solo", "solo");
  writeKeywordSkill(root, "solo", [
    { keyword: "progress", load: "steps/mode-progress.md" },
  ], { menuColumn: false });
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /progress/);
});

// No false positive on a skill that documents no keywords at all: most skills have one mode
// and no routing table, and the rule must be silent about them.
test("check:module passes a skill with no keyword table at all", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "solo", "solo");
  write(root, "skills/solo/SKILL.md", "---\nname: solo\n---\n\n# solo\n\nOne mode, no table.\n");
  const r = run(root, ["-v"]);
  assert.equal(r.status, 0, r.stderr);
});

// SCOPE ATTACK 3 -- THE VACUITY TEST. Removing every keyword table must FAIL, not pass over an
// empty expectation set. The expectation is anchored outside the table: the mode files on disk
// under steps/, which is what a mode IS (root CLAUDE.md, "Module Layout"). A rule that derived
// its cases only from the table under test could not catch the table being deleted.
test("check:module rejects a skill whose mode files exist but whose keyword table was removed", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "solo", "solo");
  writeKeywordSkill(root, "solo", [
    { keyword: "stats", load: "steps/stats.md", menu: "registered" },
    { keyword: "triage", load: "steps/triage.md", menu: "health-check" },
  ], { table: false });
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /no keyword table/);
  assert.match(r.stderr, /steps\/stats\.md/);
});

// The second net under the same attack: the "Recognized keywords" paragraph left behind with
// no table under it. Catches a deletion in a skill whose modes are not one-file-per-mode.
test("check:module rejects a Recognized-keywords section with no table under it", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "solo", "solo");
  write(root, "skills/solo/SKILL.md", "# solo\n\n**Recognized keywords** — match and load:\n\nnone yet.\n");
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /no keyword table/);
});

// ---- check 10 (agent-roster) ----
//
// A module.yaml `agents:` roster and the agent skill's own `customize.toml` `[agent]` block
// are the same declaration in two files, and nothing compared them. The installer writes the
// roster into `_bmad/config.toml` as `[agents.<code>]` (manifest-generator.js:589, :597,
// :608) and the skill reads its own block through `resolve_customization.py --key agent`, so
// a drifted title or icon shows one identity at install time and another at activation.
// BMad's own module-builder workflow calls out icon drift specifically.

// A module whose roster and agent skill agree. `rosterOverrides` perturbs exactly one field
// of the module.yaml side so each test isolates one drift.
function writeAgentModule(root, dir, code, { roster = {}, agent = {}, rosterAgents } = {}) {
  const entry = {
    code: "redteam", name: "", title: "Red Team Agent", icon: "🔴",
    description: "Adversarial analysis.", ...roster,
  };
  const entries = rosterAgents ?? [entry];
  const agentLines = entries.map((e) => [
    `  - code: ${JSON.stringify(e.code)}`,
    ...(("name" in e) ? [`    name: ${JSON.stringify(e.name)}`] : []),
    `    title: ${JSON.stringify(e.title ?? "")}`,
    `    icon: ${JSON.stringify(e.icon ?? "")}`,
    `    description: ${JSON.stringify(e.description ?? "")}`,
  ].join("\n")).join("\n");
  const moduleYaml =
    `code: ${code}\nname: "${dir}"\ndescription: "test module"\nagents:\n${agentLines}\n`;
  write(root, `skills/${dir}/assets/module.yaml`, moduleYaml);
  if (!dir.endsWith("-setup")) write(root, `skills/${dir}/module.yaml`, moduleYaml);
  write(root, `skills/${dir}/assets/module-setup.md`, "# setup\n");
  write(root, `skills/${dir}/assets/module-help.csv`, `skill,module,description\n${dir},${code},test skill\n`);
  write(root, `skills/${dir}/scripts/merge-config.py`, "# merge-config\n");
  write(root, `skills/${dir}/scripts/merge-help-csv.py`, "# merge-help-csv\n");
  const a = { code: "redteam", name: "", title: "Red Team Agent", icon: "🔴",
    description: "Adversarial analysis.", ...agent };
  write(root, `skills/${dir}/customize.toml`,
    `[agent]\ncode        = ${JSON.stringify(a.code)}\n` +
    (("name" in a) ? `name        = ${JSON.stringify(a.name)}\n` : "") +
    `title       = ${JSON.stringify(a.title)}\n` +
    `icon        = ${JSON.stringify(a.icon)}\n` +
    `description = ${JSON.stringify(a.description)}\n` +
    `agent_type  = "memory"\n`);
}

// The canonical drift, and the one BMad's own validation workflow names: the icon.
test("check:module rejects a roster icon that differs from the skill's customize.toml", (t) => {
  const root = fixture(t);
  writeAgentModule(root, "sec-redteam", "sec", { roster: { icon: "🟥" } });
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /icon/);
  assert.match(r.stderr, /redteam/);
});

test("check:module rejects a roster title that differs from the skill's customize.toml", (t) => {
  const root = fixture(t);
  writeAgentModule(root, "sec-redteam", "sec", { agent: { title: "Red Team Analyst" } });
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /title/);
});

test("check:module rejects an empty roster description", (t) => {
  const root = fixture(t);
  writeAgentModule(root, "sec-redteam", "sec", { roster: { description: "" }, agent: { description: "" } });
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /description/);
});

// `name` is the one roster field that may be empty -- a First-Breath agent fills it after
// activation -- but the KEY must be present: the installer writes `name = ''` from it either
// way, and an absent key is indistinguishable from a forgotten one.
test("check:module accepts an empty roster name and rejects an absent one", (t) => {
  const ok = fixture(t);
  writeAgentModule(ok, "sec-redteam", "sec");
  assert.equal(run(ok, ["-v"]).status, 0, run(ok).stderr);

  const bad = fixture(t);
  writeAgentModule(bad, "sec-redteam", "sec", { rosterAgents: [
    { code: "redteam", title: "Red Team Agent", icon: "🔴", description: "Adversarial analysis." },
  ] });
  const r = run(bad);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /name/);
});

// SCOPE: the roster entry is matched to its skill through the `[agent] code` in
// customize.toml -- NOT through the directory name, because `code: redteam` deliberately does
// not match `skills/l3io-sec-redteam` (the installer uses it only as the `[agents.<code>]`
// TOML section key). A roster entry whose code no skill claims declares an agent that no
// skill implements.
test("check:module rejects a roster entry whose code no skill in the module declares", (t) => {
  const root = fixture(t);
  writeAgentModule(root, "sec-redteam", "sec", { roster: { code: "ghost" } });
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /ghost/);
});

// The other direction, which is the one that fails SILENTLY in production: a skill declaring
// an [agent] block that no roster lists is never written to config.toml at all.
test("check:module rejects a customize.toml [agent] block with no roster entry", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "sec-redteam", "sec");
  write(root, "skills/sec-redteam/customize.toml",
    '[agent]\ncode        = "redteam"\nname        = ""\ntitle       = "Red Team Agent"\n' +
    'icon        = "🔴"\ndescription = "Adversarial analysis."\n');
  const r = run(root);
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stderr, /redteam/);
});

// A workflow skill's customize.toml carries [workflow], not [agent], and must not be dragged
// into the roster rule.
test("check:module ignores a customize.toml with no [agent] block", (t) => {
  const root = fixture(t);
  writeModuleHome(root, "solo", "solo");
  write(root, "skills/solo/customize.toml", "[workflow]\nmax_fix_iterations = 3\n");
  const r = run(root, ["-v"]);
  assert.equal(r.status, 0, r.stderr);
});
