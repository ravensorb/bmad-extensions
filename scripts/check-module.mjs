#!/usr/bin/env node
// Validate the module structure Phase 2 of the l3io-customization-layer change depends on.
//
// Why: `validate-module.py` (BMad core) is the tool that actually validates a module's
// shape, but it lives under `_bmad/`, which is gitignored -- CI has no BMad install at all, so
// it can never run there. Without a repo-side guard, the module restructuring this checker was
// written ahead of could regress silently, exactly the way the bmad-dependency inventory did
// before check:docs check 16 existed. This script asserts the same structural facts from the
// repo alone, so CI can catch a regression even though the real validator never runs here.
//
// Deliberately narrow, and deliberately RED against today's layout -- see the commit that
// introduced this file. The seven assertions:
//
//   1. no-root-module-yaml   no `module.yaml` sits at any skill root any more
//   2. required-fields       every `skills/*/assets/module.yaml` has non-empty code/name/description
//   3. one-home-per-code     exactly one `assets/module.yaml` declares each distinct module code
//   4. home-payload          each module home carries module-setup.md, module-help.csv, and
//                            both merge-*.py scripts
//   5. home-placement        a module home is a dedicated `*-setup` skill, or the module's only skill
//   6. pm-status-singleton   at most one `scripts/pm-status.py` payload copy per module code --
//                            Task 11A cut this from three copies inside l3io-pm to one
//   7. csv-skill-exists      every module-help.csv row's `skill` column names a real directory
//                            under skills/ -- BMad's validate-module.py calls the opposite an
//                            "orphan-entry" finding, but it lives under a gitignored,
//                            BMad-installed path CI can never run; this is the repo-side
//                            substitute. Found three real phantom rows (fix round 1, F-4):
//                            l3io-{util,sec,arch}-setup, written for setup skills that never
//                            existed and, by design, never will (three of the four modules
//                            are standalone).
//
// Scope for all seven is derived by walking `skills/` -- never from a hand-kept list of module
// codes or skill names -- so a code nobody told this script about is still found and checked.
//
// Numbering here is prose, not mechanically cross-checked the way check-docs.mjs's own check 18
// (docs-check-count) verifies ITS header against ITS invocation list (Task 11A fix round 1,
// L-1 asked whether that could extend to this file). It cannot port directly: check 18 compares
// a header-numbered-entry COUNT to an invoked-function COUNT, and here `checkModuleHomes()`
// alone implements two numbered entries (4 home-payload, 5 home-placement), so a naive count
// comparison would permanently read 7 header entries against 6 function calls even when
// correctly numbered -- a broken guard is worse than an honest "not mechanically checked" note
// (repo CLAUDE.md §3). Splitting `checkModuleHomes()` into two functions would make the port
// exact, if this numbering drifts again in practice; not done here since it was not observed to
// have drifted a second time.
//
// Parsing: `module.yaml` is read with the `yaml` package and `module-help.csv` with
// `csv-parse`. Both used to be hand-written readers, kept that way only because CI ran no
// `npm install`; it now runs `npm ci` before every gate, so run `npm ci` once before invoking
// this locally. See docs/adr/0007-ci-installs-npm-dependencies.md.
//
// Usage:
//   node scripts/check-module.mjs        # report and exit nonzero on any failure (CI)
//   node scripts/check-module.mjs -v     # also print what passed
import fs from "node:fs";
import path from "node:path";
import YAML from "yaml";
import { parse as parseCsv } from "csv-parse/sync";

// CHECK_MODULE_ROOT points the checker at another tree -- scripts/tests/check-module.test.mjs
// runs it against fixtures built from an empty skills/ tree.
const repoRoot = process.env.CHECK_MODULE_ROOT ? path.resolve(process.env.CHECK_MODULE_ROOT) : process.cwd();
const verbose = process.argv.includes("-v") || process.argv.includes("--verbose");
const failures = [];

const read = (p) => fs.readFileSync(path.join(repoRoot, p), "utf8");
const exists = (p) => fs.existsSync(path.join(repoRoot, p));

const REQUIRED_MODULE_FIELDS = ["code", "name", "description"];
const REQUIRED_MODULE_HOME_FILES = [
  "assets/module-setup.md",
  "assets/module-help.csv",
  "scripts/merge-config.py",
  "scripts/merge-help-csv.py",
];

function listSkillDirs() {
  const skillsDir = path.join(repoRoot, "skills");
  if (!fs.existsSync(skillsDir)) return [];
  return fs.readdirSync(skillsDir, { withFileTypes: true })
    .filter((e) => e.isDirectory())
    .map((e) => e.name)
    .filter((name) => name !== "_shared");
}

// module.yaml is YAML, so it is read with a YAML parser (`yaml`), not a line-scanner.
//
// What was here before: a tolerant subset parser -- a per-line `key: value` regex plus a
// hand-written block-scalar continuation rule -- carried over from check-docs.mjs's former
// checkModuleYamlAgreement(). It was written under the belief that no library was reachable,
// because CI ran no `npm install`; adding one `npm ci` step to .github/workflows/checks.yml
// removed that constraint and this with it (global rule 1: never hand-roll what a maintained
// library already does -- and this repo's own scar tissue is a hand-written YAML parser).
//
// The parse is now strict: a module.yaml that is not valid YAML is a failure here rather than
// a file silently read as an empty field set. `fieldText()` below tolerates a non-string
// value (a number, a date, a list) the way a checker must -- it reports the value rather than
// throwing on it -- so a mistyped `code:` surfaces as the field problem it is.
function parseModuleYaml(rel, text) {
  try {
    const doc = YAML.parse(text);
    return doc && typeof doc === "object" && !Array.isArray(doc) ? doc : {};
  } catch (e) {
    failures.push(`${rel}: is not valid YAML (${String(e.message).split("\n")[0]})`);
    return {};
  }
}

// A module.yaml field as comparable text. A string is itself; anything else (a number, a
// boolean, a list, a mapping, null) is rendered so a failure message shows what was actually
// found rather than throwing or stringifying into something that reads like a typo.
function fieldText(value) {
  if (typeof value === "string") return value;
  if (value === undefined || value === null) return "";
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

// ---------------------------------------------------------------------------
// 1. No module.yaml at any skill root.
function checkNoRootModuleYaml(skills) {
  for (const skill of skills) {
    const rel = `skills/${skill}/module.yaml`;
    if (exists(rel)) {
      failures.push(
        `module.yaml at a skill root: ${rel} -- it belongs at ` +
        `skills/${skill}/assets/module.yaml (the module home), not the skill root.`
      );
    }
  }
}

// Collects every module.yaml under skills/ -- at a skill root (legacy/not-yet-migrated) or
// under assets/ (the target module home) -- grouped by the code each declares. Root-level
// files are included here (not just in check 1) so a code that currently exists only at a
// skill root is still known and reported as missing its home in check 3, instead of being
// invisible because nothing under assets/ mentions it yet.
function collectModuleYamlByCode(skills) {
  const byCode = new Map(); // code -> { assets: [{skill, rel, fields}], root: [...] }
  for (const skill of skills) {
    for (const [kind, rel] of [
      ["assets", `skills/${skill}/assets/module.yaml`],
      ["root", `skills/${skill}/module.yaml`],
    ]) {
      if (!exists(rel)) continue;
      const fields = parseModuleYaml(rel, read(rel));
      const code = fieldText(fields.code).trim();
      if (!code) continue;
      if (!byCode.has(code)) byCode.set(code, { assets: [], root: [] });
      byCode.get(code)[kind].push({ skill, rel, fields });
    }
  }
  return byCode;
}

// ---------------------------------------------------------------------------
// 2. Every skills/*/assets/module.yaml carries non-empty code, name, description.
function checkRequiredFields(skills) {
  for (const skill of skills) {
    const rel = `skills/${skill}/assets/module.yaml`;
    if (!exists(rel)) continue;
    const fields = parseModuleYaml(rel, read(rel));
    for (const field of REQUIRED_MODULE_FIELDS) {
      if (fieldText(fields[field]).trim() === "") {
        failures.push(`${rel}: missing or empty required field '${field}'`);
      }
    }
  }
}

// ---------------------------------------------------------------------------
// 3. Exactly one assets/module.yaml per distinct code.
function checkOneHomePerCode(byCode) {
  for (const [code, { assets }] of byCode) {
    if (assets.length === 0) {
      failures.push(
        `code '${code}' has no assets/module.yaml -- it is declared only at a skill root ` +
        `(not yet migrated to a module home).`
      );
    } else if (assets.length > 1) {
      const files = assets.map((a) => a.rel).join(", ");
      failures.push(`code '${code}' is declared by ${assets.length} module.yaml files: ${files}`);
    }
  }
}

// ---------------------------------------------------------------------------
// 4 & 5. Each valid module home (exactly one assets/module.yaml for its code) carries the
// required payload, and is either a *-setup directory or the module's only skill. Codes with
// zero or multiple homes are already reported by check 3 above and are skipped here.
function checkModuleHomes(byCode, skills) {
  for (const [code, { assets }] of byCode) {
    if (assets.length !== 1) continue;
    const home = assets[0].skill;

    for (const req of REQUIRED_MODULE_HOME_FILES) {
      const rel = `skills/${home}/${req}`;
      if (!exists(rel)) {
        failures.push(`module home skills/${home} (code '${code}') is missing ${req}`);
      }
    }

    const siblingCount = skills.filter((s) => s === code || s.startsWith(`${code}-`)).length;
    if (siblingCount > 1 && !home.endsWith("-setup")) {
      failures.push(
        `module home skills/${home} (code '${code}') is not a *-setup directory, but the ` +
        `module has ${siblingCount} skills -- a module home shared across multiple skills ` +
        `must be a dedicated *-setup skill.`
      );
    }
  }
}

// module-help.csv is CSV, so it is read with a CSV parser (`csv-parse`), not a hand-written
// field splitter.
//
// What was here before: `splitCsvLine()`, a character loop that handled a quoted field with
// embedded commas and a doubled `""` escape and nothing else -- written, like
// parseModuleYaml() above, only because no npm dependency was believed reachable from CI.
// That belief was never a decision; `npm ci` in .github/workflows/checks.yml removed it.
// `csv-parse` additionally gets embedded newlines inside a quoted field, CRLF and a BOM
// right, none of which the splitter did.
//
// `relax_column_count` keeps the splitter's tolerance of a ragged row: a row with too few
// columns yields an empty string for the missing ones rather than aborting the whole file,
// so check 7 still reports the rows it CAN read instead of going silent on the first
// malformed one. A file that is not CSV at all is a failure here, not an empty row set.
function parseCsvRows(rel, text) {
  try {
    return parseCsv(text, {
      columns: true,
      bom: true,
      skip_empty_lines: true,
      relax_column_count: true,
      trim: false,
    });
  } catch (e) {
    failures.push(`${rel}: is not valid CSV (${String(e.message).split("\n")[0]})`);
    return [];
  }
}

// ---------------------------------------------------------------------------
// 6. pm-status-singleton: at most one `scripts/pm-status.py` per distinct module code. `pm-status.py`
// used to ship four times -- three of them inside the l3io-pm module, self-installing
// identical bytes to the identical destination -- until this task cut it to one payload copy
// per module that self-installs it. Membership in a module is derived the same way check 5
// (home-placement) derives it: a skill directory named exactly the code, or prefixed
// `{code}-`, belongs to that module -- never a hand-kept list of skill names, so a renamed or
// added skill is picked up automatically.
function checkPmStatusSingleton(byCode, skills) {
  for (const code of byCode.keys()) {
    const siblings = skills.filter((s) => s === code || s.startsWith(`${code}-`));
    const carriers = siblings.filter((s) => exists(`skills/${s}/scripts/pm-status.py`));
    if (carriers.length > 1) {
      const files = carriers.map((s) => `skills/${s}/scripts/pm-status.py`).join(", ");
      failures.push(
        `pm-status.py appears ${carriers.length} times for module '${code}': ${files} -- ` +
        `one runtime copy per project (ADR-0001) needs only one payload copy per module.`
      );
    }
  }
}

// ---------------------------------------------------------------------------
// 7. Every module-help.csv row's `skill` column names a real directory under skills/. The
// valid skill set is `listSkillDirs()` -- the same filesystem derivation every check above
// uses -- never a hand-list, so a skill directory added or removed is picked up automatically.
function checkCsvSkillsExist(skills) {
  const knownSkills = new Set(skills);
  for (const skill of skills) {
    const rel = `skills/${skill}/assets/module-help.csv`;
    if (!exists(rel)) continue; // check 4 already reports a module home missing this file
    const rows = parseCsvRows(rel, read(rel));
    for (const row of rows) {
      const csvSkill = fieldText(row.skill).trim();
      if (!csvSkill) continue;
      if (!knownSkills.has(csvSkill)) {
        failures.push(
          `${rel}: row names skill '${csvSkill}', which is not a directory under skills/ -- ` +
          `an orphan capability entry.`
        );
      }
    }
  }
}

// ---------------------------------------------------------------------------
const skills = listSkillDirs();
checkNoRootModuleYaml(skills);
checkRequiredFields(skills);
const byCode = collectModuleYamlByCode(skills);
checkOneHomePerCode(byCode);
checkModuleHomes(byCode, skills);
checkPmStatusSingleton(byCode, skills);
checkCsvSkillsExist(skills);

if (verbose) {
  console.log(`  skills: ${skills.length}, module codes discovered: ${byCode.size}`);
}

if (failures.length > 0) {
  console.error(`\n${failures.length} module structure problem(s):\n`);
  for (const f of failures) console.error(`  ✗ ${f}\n`);
  console.error("These are the structural facts the module layout must hold. Fix the tree, not this check.");
  process.exit(1);
}

console.log("Module structure checks passed: one module.yaml per module, correctly homed.");
