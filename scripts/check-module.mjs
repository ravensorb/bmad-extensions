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
// Usage:
//   node scripts/check-module.mjs        # report and exit nonzero on any failure (CI)
//   node scripts/check-module.mjs -v     # also print what passed
import fs from "node:fs";
import path from "node:path";

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

// Tolerant module.yaml line-scanner, copied verbatim from check-docs.mjs's former
// checkModuleYamlAgreement() (was check 16, deleted by Task 7 once module.yaml relocation left
// it with no siblings to compare), so this checker keeps the same parsing behaviour rather
// than re-deriving it. Block scalars (`key: >`) continue over indented lines; this captures
// the whole value.
function parseModuleYaml(text) {
  const fields = {};
  const lines = text.split("\n");
  for (let i = 0; i < lines.length; i += 1) {
    const m = lines[i].match(/^([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$/);
    if (!m) continue;
    let value = m[2].trim();
    if (value === ">" || value === "|" || value === ">-" || value === "|-") {
      const body = [];
      for (let j = i + 1; j < lines.length && /^\s+\S/.test(lines[j]); j += 1) body.push(lines[j].trim());
      value = body.join(" ");
    }
    fields[m[1]] = value.replace(/\s+/g, " ");
  }
  return fields;
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
      const fields = parseModuleYaml(read(rel));
      const code = fields.code;
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
    const fields = parseModuleYaml(read(rel));
    for (const field of REQUIRED_MODULE_FIELDS) {
      if (!fields[field] || fields[field].trim() === "") {
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

// Minimal, tolerant CSV row splitter for module-help.csv, in the same spirit as
// parseModuleYaml() above: this repo has no npm dependency and CI never runs `npm install`
// before these checks (only `node scripts/check-module.mjs` -- see .github/workflows/checks.yml),
// so a real CSV library is not reachable here without also wiring up a package install step.
// Scoped exactly to what these files actually contain -- one row per line, no embedded
// newlines inside a quoted field -- rather than a general RFC4180 parser: handles a quoted
// field containing commas and a doubled `""` as an escaped quote (the one feature these files
// use, e.g. `"Validate readiness, elaborate stories, ..."`), nothing else.
function splitCsvLine(line) {
  const fields = [];
  let field = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i += 1) {
    const c = line[i];
    if (inQuotes) {
      if (c === '"' && line[i + 1] === '"') { field += '"'; i += 1; }
      else if (c === '"') { inQuotes = false; }
      else { field += c; }
    } else if (c === '"') {
      inQuotes = true;
    } else if (c === ",") {
      fields.push(field);
      field = "";
    } else {
      field += c;
    }
  }
  fields.push(field);
  return fields;
}

function parseCsvRows(text) {
  const lines = text.split("\n").filter((l) => l.trim() !== "");
  if (lines.length === 0) return [];
  const header = splitCsvLine(lines[0]);
  return lines.slice(1).map((line) => {
    const values = splitCsvLine(line);
    const row = {};
    header.forEach((h, i) => { row[h] = values[i] ?? ""; });
    return row;
  });
}

// ---------------------------------------------------------------------------
// Task 11A: at most one `scripts/pm-status.py` per distinct module code. `pm-status.py`
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
// 6. Every module-help.csv row's `skill` column names a real directory under skills/. The
// valid skill set is `listSkillDirs()` -- the same filesystem derivation every check above
// uses -- never a hand-list, so a skill directory added or removed is picked up automatically.
function checkCsvSkillsExist(skills) {
  const knownSkills = new Set(skills);
  for (const skill of skills) {
    const rel = `skills/${skill}/assets/module-help.csv`;
    if (!exists(rel)) continue; // check 4 already reports a module home missing this file
    const rows = parseCsvRows(read(rel));
    for (const row of rows) {
      const csvSkill = (row.skill || "").trim();
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
