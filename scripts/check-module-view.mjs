#!/usr/bin/env node
// Judge one `validate-module.py` run against one assembled module view.
//
// WHY THIS EXISTS. `scripts/smoke-install.sh` used to gate on the validator's own
// `"status": "pass"`. That gate went red for all four modules the day this package adopted
// two conventions BMad itself documents and ships, but `validate-module.py` does not
// implement:
//
//   1. THE `_meta` ROW. `bmad-help/SKILL.md:29` defines it ("Rows with `_meta` in the `skill`
//      column carry a URL or path in `output-location` pointing to the module's
//      documentation"), and BMad's own installed `bmm`, `core` and `bmb` modules each ship
//      exactly one. `validate-module.py` knows nothing about it: step 8 reports the row as an
//      `orphan-entry` (there is no `_meta/` skill directory, and there is not meant to be),
//      and step 11 reports its deliberately empty `display-name` / `menu-code` /
//      `description` as three `missing-field`s.
//   2. CROSS-MODULE `skill:action` RELATIONSHIPS. The validator skips a colon-LESS ref as
//      cross-module (its own comment at step 10 says so) but requires every `skill:action`
//      ref to resolve inside the single module it was handed. The refs this package writes
//      DO resolve — in `_bmad/_config/bmad-help.csv`, the assembled index bmad-help actually
//      reads and the only place a relationship is ever followed. The validator has no view of
//      it.
//
// Measured 2026-09-23, and this is what makes cause 1 a tool gap rather than a defect in our
// CSVs: BMAD'S OWN `bmm` module fails the validator on it, identically. Pointed straight at
// `<bmad-method>/src/bmm-skills`, the run fails earlier for an unrelated reason (that tree is
// neither of the two shapes the validator accepts — no `*-setup` directory, more than one
// skill — so it bails at the structural critical before reading a single CSV row). Assembled
// into the shape the validator does accept (bmm's own `module.yaml` + `module-help.csv` under
// a `bmm-setup/assets/`, one directory per skill the CSV names), it returns exactly:
//
//     high  orphan-entry   CSV references skill '_meta' which does not exist in the module folder
//     high  missing-field  Entry '' is missing required field: display-name
//     high  missing-field  Entry '' is missing required field: menu-code
//     high  missing-field  Entry '' is missing required field: description
//
// Four findings, all four about `_meta`, and nothing else. The reference implementation of a
// BMad module fails the reference checker in exactly the way this package does.
//
// WHAT THIS DOES NOT DO. It does not ignore findings. A blanket "tolerate `fail`" would have
// destroyed the assertion the smoke gate exists to make. Each exemption below is narrow,
// evidenced against the module's OWN CSV, and refuses itself the moment the evidence stops
// holding:
//
//   - `orphan-entry` is exempt only for the LITERAL skill name `_meta`, and only when the CSV
//     really does carry a `_meta` row. An orphan naming any other skill fails.
//   - `missing-field` is exempt only for `display-name` / `menu-code` / `description`, only on
//     an entry the validator could not name (its `display-name` is empty), only up to the
//     number of `_meta` rows that actually leave that field empty, and ONLY IF no non-`_meta`
//     row in the CSV has an empty `display-name`. That last clause is the scope guard: the
//     validator names a row by its `display-name`, so the moment a second kind of row can
//     produce an unnamed `missing-field` the attribution to `_meta` is no longer sound, and
//     the exemption switches itself off for the whole file rather than guess.
//   - `invalid-ref` is exempt only when the ref names a skill that is NOT part of the module
//     under test — that is, exactly the cross-module case. A broken ref to a SIBLING skill of
//     this module (a real typo, a renamed action) still fails, because that one the validator
//     is entitled to check.
//
// Anything else — any other category, any other severity, a `missing-entry`, a
// `duplicate-menu-code`, a `csv-header` mismatch, a structural `critical` — fails. So does a
// run this script cannot make sense of: unparseable JSON, a missing `findings` array, an
// `info` block that does not say where the module's CSV is, or a CSV that is not there. Fail
// closed, never skip.
//
// The bar is STRICTER than the validator's own: `validate-module.py` sets `status` from
// critical+high alone and lets a `medium` pass. Here ANY non-exempt finding fails, which is
// what `smoke-install.sh`'s comment always claimed it was asserting ("`pass` with zero
// findings") and what it now actually asserts.
//
// Usage:  uv run <validate-module.py> <view> | node scripts/check-module-view.mjs <view>
// Tests:  scripts/tests/check-module-view.test.mjs  (run by `npm run test:scripts`)
import fs from "node:fs";
import path from "node:path";
import { parse as parseCsv } from "csv-parse/sync";

// The validator's message wordings, which are the only machine-readable handle it offers on
// WHICH row a finding is about. Anchored whole, so a reworded message stops matching and the
// finding falls through to "not exempt" — fail closed, not silently exempt.
const ORPHAN_RE = /^CSV references skill '(.+)' which does not exist in the module folder$/;
const MISSING_FIELD_RE = /^Entry '(.*)' is missing required field: (.+)$/;
const INVALID_REF_RE =
  /^'(.*)' (?:preceded-by|followed-by) references '(.+)' which is not a valid capability$/;

const META_SKILL = "_meta";
// The three columns a `_meta` row leaves empty by design. `skill` is NOT here: a `_meta` row
// has `_meta` in it, so a missing `skill` is always a real defect.
const META_EMPTY_FIELDS = new Set(["display-name", "menu-code", "description"]);

function die(msg) {
  console.error(`check-module-view: ${msg}`);
  process.exit(1);
}

function readStdin() {
  try {
    return fs.readFileSync(0, "utf8");
  } catch {
    return "";
  }
}

const args = process.argv.slice(2);
const verbose = args.includes("-v") || args.includes("--verbose");
const viewDir = args.find((a) => !a.startsWith("-"));
if (!viewDir) die("usage: check-module-view.mjs [-v] <view-dir>  (validator JSON on stdin)");

const raw = readStdin();
if (!raw.trim()) {
  die(`no validator output on stdin for view '${viewDir}' — the validator did not run, or ` +
    `crashed before printing JSON. Treated as a failure, not a skip.`);
}

let result;
try {
  result = JSON.parse(raw);
} catch (e) {
  die(`could not parse validator output as JSON for view '${viewDir}': ${e.message}\n` +
    `--- raw output ---\n${raw.slice(0, 2000)}`);
}

if (result.status === "error") {
  die(`validator returned an error for view '${viewDir}': ${result.message ?? "(no message)"}`);
}
if (!Array.isArray(result.findings)) {
  die(`validator output for view '${viewDir}' has no findings array — nothing to judge. ` +
    `A checker that reports success over an absent finding set is worse than no checker.`);
}

const findings = result.findings;
const info = result.info ?? {};

// Where the module's own CSV lives, derived from the validator's own report of which skill
// directory it read — never rebuilt by guessing at the view's layout.
const csvHome = info.skill_dir || info.setup_skill;
if (!csvHome) {
  // Happens when the validator bailed out early with a structural critical. There is no
  // evidence to exempt anything against, so everything stands.
  console.error(`check-module-view: view '${viewDir}': the validator reported no module home ` +
    `(info.skill_dir / info.setup_skill absent), so no exemption has evidence behind it.`);
  for (const f of findings) console.error(`  ${f.severity} ${f.category}: ${f.message}`);
  process.exit(1);
}
const csvPath = path.join(viewDir, csvHome, "assets", "module-help.csv");
if (!fs.existsSync(csvPath)) {
  die(`view '${viewDir}': ${csvHome}/assets/module-help.csv is not there, so the exemptions ` +
    `below have nothing to check themselves against.`);
}

let rows;
try {
  rows = parseCsv(fs.readFileSync(csvPath, "utf8"), {
    columns: true,
    skip_empty_lines: true,
    bom: true,
    relax_column_count: true,
  });
} catch (e) {
  die(`view '${viewDir}': could not parse ${csvPath}: ${e.message}`);
}

const cell = (row, key) => String(row[key] ?? "").trim();
const metaRows = rows.filter((r) => cell(r, "skill") === META_SKILL);
// The scope guard described in the header: if any ordinary row also has an empty
// display-name, an unnamed `missing-field` can no longer be attributed to `_meta`.
const unnamedNonMetaRows = rows.filter(
  (r) => cell(r, "skill") !== META_SKILL && cell(r, "display-name") === "",
);

// One exemption slot per field per `_meta` row that actually leaves that field empty. A
// fourth `missing-field: description` with only one `_meta` row is somebody else's, and fails.
const missingFieldBudget = new Map();
for (const field of META_EMPTY_FIELDS) {
  missingFieldBudget.set(field, metaRows.filter((r) => cell(r, field) === "").length);
}

// Every skill this module owns: the directories the validator found, plus every skill the CSV
// names (which includes the setup skill, excluded from skill_folders), minus `_meta`, which is
// not a skill. A ref into this set is one the validator is entitled to resolve.
const moduleSkills = new Set(
  [...(info.skill_folders ?? []), ...(info.csv_skills ?? [])].filter((s) => s && s !== META_SKILL),
);

const exempt = [];
const standing = [];

for (const f of findings) {
  const message = String(f.message ?? "");
  let why = null;

  if (f.category === "orphan-entry") {
    const m = ORPHAN_RE.exec(message);
    if (m && m[1] === META_SKILL && metaRows.length > 0) {
      why = `the \`${META_SKILL}\` row bmad-help/SKILL.md:29 defines; it is documentation, ` +
        `not a skill directory, and BMad's own modules ship one`;
    }
  } else if (f.category === "missing-field") {
    const m = MISSING_FIELD_RE.exec(message);
    const field = m?.[2];
    if (
      m && m[1] === "" &&
      META_EMPTY_FIELDS.has(field) &&
      unnamedNonMetaRows.length === 0 &&
      (missingFieldBudget.get(field) ?? 0) > 0
    ) {
      missingFieldBudget.set(field, missingFieldBudget.get(field) - 1);
      why = `a column the \`${META_SKILL}\` row leaves empty by design (it carries only a ` +
        `documentation \`output-location\`)`;
    }
  } else if (f.category === "invalid-ref") {
    const m = INVALID_REF_RE.exec(message);
    const ref = m?.[2] ?? "";
    const refSkill = ref.includes(":") ? ref.slice(0, ref.indexOf(":")) : "";
    if (refSkill && !moduleSkills.has(refSkill)) {
      why = `'${ref}' names skill '${refSkill}', which is outside module ` +
        `'${info.module_code ?? "?"}'; it resolves in the assembled ` +
        `_bmad/_config/bmad-help.csv, which is the index bmad-help reads`;
    }
  }

  (why ? exempt : standing).push({ f, why });
}

const label = info.module_code || csvHome || viewDir;
// The exemptions are listed with -v, and always when something stands beside them: a reader
// looking at a failure needs to see what was waved through next to what was not.
if (verbose || standing.length > 0) {
  for (const { f, why } of exempt) {
    console.log(`  exempt  [${f.category}] ${f.message}`);
    console.log(`          ↳ ${why}`);
  }
}
for (const { f } of standing) {
  console.error(`  FINDING [${f.severity}/${f.category}] ${f.message}` +
    (f.detail ? ` (${f.detail})` : ""));
}

if (standing.length > 0) {
  die(`module '${label}': ${standing.length} finding(s) with no exemption behind them ` +
    `(${exempt.length} exempt). See above.`);
}
console.log(`  module '${label}': 0 findings outside the two known validate-module.py gaps ` +
  `(${exempt.length} exempt, ${findings.length} total).`);
