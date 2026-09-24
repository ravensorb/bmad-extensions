// Tests for scripts/check-module-view.mjs -- the narrow exemption filter smoke-install.sh
// applies to validate-module.py's findings.
//
// A filter that turns a red gate green is the single easiest place in this repo to ship a
// false green, so these tests spend most of their effort ATTACKING the exemptions rather than
// confirming them: every test below that ends in `assert.equal(r.status, 1)` is a shape that
// must NOT be waved through. The header of the script under test states four properties; each
// one has a test here that fails if the property is dropped.
//
// The validator's real output shapes were captured 2026-09-23 from
// `.claude/skills/bmad-module-builder/scripts/validate-module.py` run against the assembled
// module views `scripts/smoke-install.sh` builds, and against BMad's own `bmm` CSV.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const SCRIPT = path.join(REPO, "scripts", "check-module-view.mjs");

const HEADER =
  "module,skill,display-name,menu-code,description,action,args,phase,preceded-by," +
  "followed-by,required,output-location,outputs";
const META_ROW = "Test Module,_meta,,,,,,,,,false,https://example.invalid/docs,";
const REAL_ROW =
  "Test Module,test-skill,Do The Thing,TT,Does the thing.,,,anytime,,,false,out,artifact";

// A view as smoke-install.sh builds one: <view>/<skill>/assets/module-help.csv.
function view(t, { csv = `${HEADER}\n${META_ROW}\n${REAL_ROW}\n`, skill = "test-skill" } = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "module-view-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  if (csv !== null) {
    fs.mkdirSync(path.join(dir, skill, "assets"), { recursive: true });
    fs.writeFileSync(path.join(dir, skill, "assets", "module-help.csv"), csv);
  }
  return dir;
}

// -v by default, so the tests can see WHICH finding was exempted and why, not only the
// count. Quiet-by-default is asserted separately below.
function run(viewDir, validatorJson, args = ["-v"]) {
  return spawnSync(process.execPath, [SCRIPT, ...args, viewDir], {
    cwd: REPO,
    input: typeof validatorJson === "string" ? validatorJson : JSON.stringify(validatorJson),
    encoding: "utf8",
  });
}

// The validator's own wordings. Written out here rather than imported, so that a reworded
// constant in the script cannot make these tests agree with it by construction.
const orphan = (skill) => ({
  severity: "high",
  category: "orphan-entry",
  message: `CSV references skill '${skill}' which does not exist in the module folder`,
  detail: "",
});
const missingField = (entry, field) => ({
  severity: "high",
  category: "missing-field",
  message: `Entry '${entry}' is missing required field: ${field}`,
  detail: "",
});
const invalidRef = (display, field, ref) => ({
  severity: "medium",
  category: "invalid-ref",
  message: `'${display}' ${field} references '${ref}' which is not a valid capability`,
  detail: "Expected format: skill-name:action-name",
});

const META_FINDINGS = [
  orphan("_meta"),
  missingField("", "display-name"),
  missingField("", "menu-code"),
  missingField("", "description"),
];

function result(findings, extra = {}) {
  return {
    status: findings.some((f) => f.severity === "high" || f.severity === "critical")
      ? "fail" : "pass",
    info: {
      standalone: true,
      skill_dir: "test-skill",
      module_code: "l3io-test",
      skill_folders: ["test-skill"],
      csv_skills: ["_meta", "test-skill"],
      ...extra,
    },
    findings,
  };
}

// --- the two exemptions, in the exact shapes that occur ------------------------------------

test("the four _meta findings alone pass, although the validator says fail", (t) => {
  const r = run(view(t), result(META_FINDINGS));
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /0 findings outside the two known validate-module\.py gaps/);
  assert.match(r.stdout, /4 exempt/);
});

test("a cross-module skill:action ref is exempt", (t) => {
  const r = run(view(t), result([invalidRef("Do The Thing", "followed-by", "other-skill:go")]));
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /outside module 'l3io-test'/);
});

test("a real install's whole finding set (both causes together) passes", (t) => {
  const r = run(
    view(t),
    result([...META_FINDINGS, invalidRef("Do The Thing", "preceded-by", "l3io-pm-execute:execute")]),
  );
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /5 exempt, 5 total/);
});

test("a clean module with no findings at all passes", (t) => {
  const r = run(view(t), result([]));
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /0 exempt, 0 total/);
});

// --- attacks on the orphan-entry exemption -------------------------------------------------

test("an orphan naming a skill other than _meta fails", (t) => {
  const r = run(view(t), result([orphan("l3io-ghost")]));
  assert.equal(r.status, 1);
  assert.match(r.stderr, /FINDING \[high\/orphan-entry\].*l3io-ghost/s);
});

test("an orphan for _meta fails when the CSV carries no _meta row", (t) => {
  // The exemption is evidenced against the CSV, not against the name in the message: strip
  // the row and the same finding must stand.
  const dir = view(t, { csv: `${HEADER}\n${REAL_ROW}\n` });
  const r = run(dir, result([orphan("_meta")]));
  assert.equal(r.status, 1);
  assert.match(r.stderr, /orphan-entry/);
});

// --- attacks on the missing-field exemption -------------------------------------------------

test("a missing-field on a NAMED entry fails", (t) => {
  const r = run(view(t), result([missingField("Do The Thing", "menu-code")]));
  assert.equal(r.status, 1);
  assert.match(r.stderr, /Do The Thing/);
});

test("a missing-field for `skill` is never exempt", (t) => {
  const r = run(view(t), result([missingField("", "skill")]));
  assert.equal(r.status, 1);
  assert.match(r.stderr, /missing required field: skill/);
});

test("a fourth unnamed missing-field beyond the _meta budget fails", (t) => {
  // One _meta row leaves `description` empty once, so one exemption is available for it.
  const r = run(view(t), result([missingField("", "description"), missingField("", "description")]));
  assert.equal(r.status, 1);
  assert.match(r.stderr, /1 finding\(s\) with no exemption/);
});

test("the missing-field exemption switches off when an ordinary row is also unnamed", (t) => {
  // THE SCOPE ATTACK. The validator names a row by its display-name, so once a second kind of
  // row can produce an unnamed missing-field, attributing one to _meta is a guess. All four
  // must stand, including the ones that really are _meta's.
  const unnamed = "Test Module,test-skill,,XX,Does the thing.,,,anytime,,,false,out,artifact";
  const dir = view(t, { csv: `${HEADER}\n${META_ROW}\n${unnamed}\n` });
  const r = run(dir, result(META_FINDINGS));
  assert.equal(r.status, 1);
  assert.match(r.stderr, /3 finding\(s\) with no exemption/);
});

test("a missing-field whose _meta column is NOT empty in the CSV fails", (t) => {
  // _meta carries a menu-code here, so the validator could not have raised that finding about
  // it; the budget for menu-code is zero and the finding stands.
  const filled = "Test Module,_meta,,ZZ,,,,,,,false,https://example.invalid/docs,";
  const dir = view(t, { csv: `${HEADER}\n${filled}\n${REAL_ROW}\n` });
  const r = run(dir, result([missingField("", "menu-code")]));
  assert.equal(r.status, 1);
  assert.match(r.stderr, /missing required field: menu-code/);
});

// --- attacks on the invalid-ref exemption ---------------------------------------------------

test("a broken ref to a SIBLING skill of the same module fails", (t) => {
  // test-skill is in the module, so `test-skill:no-such-action` is a real defect the
  // validator is entitled to catch -- a renamed action, a typo -- and must not be waved
  // through with the cross-module refs.
  const r = run(view(t), result([invalidRef("Do The Thing", "followed-by", "test-skill:nope")]));
  assert.equal(r.status, 1);
  assert.match(r.stderr, /test-skill:nope/);
});

test("a broken ref to the module's setup skill fails", (t) => {
  // The setup skill is absent from skill_folders but present in csv_skills; the module-skill
  // set is the union, so it must not read as cross-module.
  const r = run(
    view(t),
    result([invalidRef("Do The Thing", "preceded-by", "l3io-test-setup:configure")], {
      csv_skills: ["_meta", "test-skill", "l3io-test-setup"],
    }),
  );
  assert.equal(r.status, 1);
  assert.match(r.stderr, /l3io-test-setup:configure/);
});

test("a colon-less invalid-ref fails (the validator never skips one, so neither do we)", (t) => {
  const r = run(view(t), result([invalidRef("Do The Thing", "followed-by", "other-skill")]));
  assert.equal(r.status, 1);
});

// --- everything else fails ------------------------------------------------------------------

test("any other finding category fails, whatever its severity", (t) => {
  for (const f of [
    { severity: "high", category: "missing-entry", message: "Skill 'x' has no capability entries in the CSV" },
    { severity: "high", category: "duplicate-menu-code", message: "Menu code 'TT' used by multiple entries: A, B" },
    { severity: "high", category: "csv-header", message: "CSV header mismatch: missing: outputs" },
    { severity: "medium", category: "csv-columns", message: "Row 3 has 12 columns, expected 13" },
    { severity: "high", category: "yaml", message: "module.yaml missing or empty required field: code" },
  ]) {
    const r = run(view(t), result([f]));
    assert.equal(r.status, 1, `${f.category} was waved through`);
    assert.match(r.stderr, new RegExp(f.category));
  }
});

test("a medium finding fails, although validate-module.py's own status would be pass", (t) => {
  const bad = { severity: "medium", category: "csv-columns", message: "Row 3 has 12 columns, expected 13" };
  const payload = result([bad]);
  assert.equal(payload.status, "pass"); // the validator itself tolerates this
  const r = run(view(t), payload);
  assert.equal(r.status, 1);
});

test("a reworded validator message is not exempt", (t) => {
  // The message regexes are the only handle on WHICH row a finding is about. If the wording
  // changes, the finding must fall through to "stands", not to "exempt".
  const r = run(view(t), result([{
    severity: "high",
    category: "orphan-entry",
    message: "csv references skill _meta which is missing",
  }]));
  assert.equal(r.status, 1);
});

// --- fail closed --------------------------------------------------------------------------

test("empty stdin fails rather than reporting success over nothing", (t) => {
  const r = run(view(t), "");
  assert.equal(r.status, 1);
  assert.match(r.stderr, /no validator output on stdin/);
});

test("unparseable stdin fails", (t) => {
  const r = run(view(t), "Traceback (most recent call last):\n  ...\n");
  assert.equal(r.status, 1);
  assert.match(r.stderr, /could not parse validator output as JSON/);
});

test("a result with no findings array fails", (t) => {
  const r = run(view(t), { status: "pass", info: { skill_dir: "test-skill" } });
  assert.equal(r.status, 1);
  assert.match(r.stderr, /no findings array/);
});

test("a validator error result fails", (t) => {
  const r = run(view(t), { status: "error", message: "Not a directory: /nope" });
  assert.equal(r.status, 1);
  assert.match(r.stderr, /validator returned an error/);
});

test("an early structural bail-out fails, with no exemption applied", (t) => {
  // The validator returns `info: {}` when it cannot detect a module at all. There is then no
  // CSV to evidence anything against, so nothing may be exempted -- not even a _meta finding.
  const r = run(view(t), {
    status: "fail",
    info: {},
    findings: [{ severity: "critical", category: "structure", message: "No setup skill found" }, ...META_FINDINGS],
  });
  assert.equal(r.status, 1);
  assert.match(r.stderr, /no module home/);
});

test("a view whose module-help.csv is missing fails", (t) => {
  const dir = view(t, { csv: null });
  const r = run(dir, result(META_FINDINGS));
  assert.equal(r.status, 1);
  assert.match(r.stderr, /module-help\.csv is not there/);
});

test("a multi-skill module's CSV is found under the setup skill", (t) => {
  const dir = view(t, { skill: "l3io-test-setup" });
  const r = run(dir, {
    status: "fail",
    info: {
      setup_skill: "l3io-test-setup",
      module_code: "l3io-test",
      skill_folders: ["test-skill"],
      csv_skills: ["_meta", "test-skill"],
    },
    findings: META_FINDINGS,
  });
  assert.equal(r.status, 0, r.stderr);
});

test("without -v the exemptions are not printed, only the summary", (t) => {
  const r = run(view(t), result(META_FINDINGS), []);
  assert.equal(r.status, 0, r.stderr);
  assert.doesNotMatch(r.stdout, /exempt  \[/);
  assert.match(r.stdout, /4 exempt, 4 total/);
});

test("a failure prints the exemptions beside the findings that stand, without -v", (t) => {
  const r = run(view(t), result([...META_FINDINGS, orphan("l3io-ghost")]), []);
  assert.equal(r.status, 1);
  assert.match(r.stdout, /exempt  \[orphan-entry\]/);
  assert.match(r.stderr, /l3io-ghost/);
});

test("no view argument fails", () => {
  const r = spawnSync(process.execPath, [SCRIPT], { cwd: REPO, input: "{}", encoding: "utf8" });
  assert.equal(r.status, 1);
  assert.match(r.stderr, /usage:/);
});
