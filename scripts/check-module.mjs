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
// introduced this file. The thirteen assertions:
//
//   1. discovery-layout     the layout BMad's INSTALLER discovers, which is not the layout
//                            `validate-module.py` validates. Three parts:
//                            (a) every standalone (non-`*-setup`) module home also carries
//                                `module.yaml` at its SKILL ROOT, byte-identical to its
//                                `assets/module.yaml`;
//                            (b) `skills/module.yaml` exists and declares neither `code:`,
//                                `name:` nor `agents:`;
//                            (c) `skills/module-help.csv` does NOT exist.
//                            See docs/bmad-module-yaml-discovery.md and ADR-0008. This rule
//                            used to be `no-root-module-yaml`, which FORBADE (a) -- the only
//                            location bmad-method 6.12.0's `project-root.js` discovers for a
//                            non-`*-setup` skill. It was derived from `validate-module.py`
//                            alone, and it made a branch that validated clean install broken.
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
//                            are standalone). ONE exemption: the literal `_meta`, which
//                            bmad-help reserves for a module's documentation row and is not
//                            a skill -- see the rule for why, and its two tests for its scope.
//   8. plugin-resolver-strategy
//                            every plugin in `.claude-plugin/marketplace.json` resolves, from
//                            the files on disk, to one of PluginResolver's AUTHORED strategies
//                            (1-4) rather than its strategy-5 synthesized fallback. Mirrors
//                            bmad-method 6.12.0's
//                            `tools/installer/modules/plugin-resolver.js` condition for
//                            condition. Strategy 5 ignores every authored `module-help.csv`
//                            and builds a stub catalog from SKILL.md frontmatter -- `action:
//                            activate` on every row, title-cased display names, generated
//                            3-letter menu codes, no relationships, no `output-location` --
//                            and the install still EXITS 0. Nothing warns. This package has
//                            already shipped that: the gitignored `_bmad/` tree from the
//                            2026-09-14 install holds exactly those stub rows, including one
//                            for `l3io-util-cleanup`, a skill that no longer exists.
//                            The margin at the time this check was written was one file and
//                            one list entry: `l3io-pm` reaches strategy 2 only because
//                            `skills/l3io-setup/` is named `*-setup` and carries both
//                            files, and the other three reach strategy 3 only because
//                            `_trySingleStandalone` requires EXACTLY ONE existing skill --
//                            adding a second skill to any of their `skills` arrays, with
//                            nothing deleted, drops that module to synthesis.
//   9. help-registration     every mode keyword a skill documents in its SKILL.md routing
//                            table either carries a `module-help.csv` row or is marked
//                            excluded in that table's own `Menu` column. A capability with
//                            no row cannot be selected from BMad's help menu at all; the
//                            module-help-registration plan corrected four CSVs by hand and
//                            nothing would have caught the next drift. The exclusion set is
//                            READ FROM THE TABLE, not listed here, and the expectation
//                            survives the table being deleted -- see the rule's own header.
//  10. agent-roster          every `agents[]` entry in a module.yaml agrees, field for
//                            field, with the `[agent]` block in the customize.toml of the
//                            skill that implements it, and each block is listed by exactly
//                            one roster. The installer writes the ROSTER into
//                            `_bmad/config.toml` as `[agents.<code>]`; the skill reads its
//                            OWN block at activation, so drift gives the agent two
//                            identities. `code` is the TOML section key, never a directory
//                            name -- see the rule's own header for the verification.
//  11. setup-singleton       at most ONE `*-setup` directory per module code. BMad resolves a
//                            module's setup skill by scanning for the FIRST directory whose
//                            name ends in `-setup` and returning it -- `find_setup_skill()` in
//                            `validate-module.py`, and the same scan inside PluginResolver
//                            strategy 2. First match wins in filesystem order, so a second
//                            `*-setup` directory makes the module home a lottery. Shipped in
//                            3.1.7: `skills/l3io-pm-setup/` (a bare DEPRECATED forwarder --
//                            SKILL.md and customize.toml, no `module.yaml` at all) sat beside
//                            `skills/l3io-setup/`, the real home. The order is not even random
//                            everywhere: `'l3io-pm-setup' < 'l3io-setup'` ('p' < 's'), so on
//                            any filesystem returning sorted entries (APFS/HFS+, many NFS/SMB
//                            mounts) the FORWARDER won every time and module registration got
//                            a directory carrying no `module.yaml`. On ext4's hash order this
//                            repo happened to draw the right one, which is why every gate here
//                            was green over a broken shape. Rule 3 could not see it -- the
//                            forwarder declares no code, so nothing was duplicated -- and rule
//                            5 could not either, since it asks whether the home IS `*-setup`,
//                            never whether something else also is. Reported by the adopter
//                            package, which hit the same shape and whose smoke install caught
//                            it there first.
//                            The general rule, which rules 8 and 11 enforce between them:
//                            A DEPRECATED FORWARDER IS SAFE ONLY AT A NAME THE RESOLVER
//                            DERIVES NO MEANING FROM. Two derivations exist in 6.12 -- the
//                            `*-setup` suffix (strategy 2, this rule) and the exactly-one-skill
//                            count (strategy 3, rule 8). A rename whose OLD name collides with
//                            either cannot carry a forwarder at that name.
//  12. menu-code-unique     no two rows in one `module-help.csv` share a `menu-code`. The menu
//                            code is the SELECTOR a user types to pick a capability out of
//                            BMad's help menu, so a duplicate makes one of the two capabilities
//                            unreachable, and which one loses is decided by the menu builder,
//                            not by anything either row says. Shipped in 3.1.3: `/l3io-help
//                            catalog` was added carrying `LPC`, which `l3io-sync`'s Sync row
//                            already held, and it survived five releases because every gate
//                            over that CSV asked a different question -- rule 7 asks whether a
//                            row's `skill` names a real directory, rule 9 asks whether every
//                            documented keyword HAS a row, and neither compares two rows to
//                            each other. `validate-module.py` does report it, but it needs a
//                            real BMad install, so it only runs in `smoke:install`, which is
//                            not in CI.
//  13. forwarder-shape      a DEPRECATED forwarder forwards to the skill it claims, and only
//                            to that one. Rules 8 and 11 say WHERE a forwarder may sit; this
//                            says whether it works. Every forwarder here was made by copying
//                            its neighbour and editing five names, and nothing checked that
//                            all five were edited -- a missed one leaves a skill that
//                            activates, prints a confident deprecation notice, and runs
//                            somebody else's workflow. Asserts: the target exists and is not
//                            itself a forwarder; the body invokes exactly `skill:<target>`;
//                            no third skill is named anywhere in it; the NOTICE line names the
//                            forwarder as deprecated and the target as the replacement; the
//                            directory carries only SKILL.md and customize.toml (payload on a
//                            forwarder is the road to the rule 11 defect); and the rename and
//                            removal versions agree between frontmatter and body. Plus the one
//                            clause that fires without anyone editing the tree: THE REMOVAL
//                            VERSION MUST STILL BE IN THE FUTURE, so the release that reaches
//                            4.0.0 fails until the forwarders promising removal there are
//                            actually deleted. Scope is derived from the `DEPRECATED forwarder
//                            for /<target>` description shape, not a list of names.
//
// Scope for checks 1-7 and 9-13 is derived by walking `skills/` and for check 8 from
// `.claude-plugin/marketplace.json`'s own `plugins` array -- never from a hand-kept list of
// module codes, skill names or plugin names -- so a code or a plugin nobody told this script
// about is still found and checked. Check 9 derives a second scope the same way: which
// keywords must be registered, and which are deliberately exempt, is read from each skill's
// own routing table, never from a list of exemptions kept here.
// Check 8 must read the marketplace, not the filesystem:
// what a plugin LISTS is the input PluginResolver runs on, and a plugin's skill list can
// change shape while every file on disk stays exactly where it was.
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
// Parsing: `module.yaml` is read with the `yaml` package, `module-help.csv` and the SKILL.md
// routing tables with `csv-parse`, `customize.toml` with `smol-toml`, and `marketplace.json`
// with `JSON.parse`. The first two used to be
// hand-written readers, kept that way only because CI ran no
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
import { parse as parseToml } from "smol-toml";
import { writeAllSync } from "./write-all-sync.mjs";

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
// 1. The layout BMad's INSTALLER discovers.
//
// `validate-module.py` reads `assets/module.yaml` and nothing else; it neither requires nor
// forbids a copy at the skill root. `tools/installer/project-root.js` is a different tool with
// a different contract, and it is the one that decides which module's settings land under
// which `[modules.<code>]`. Its `searchRootAll()` (6.12.0, line 109) recognises
// `assets/module.yaml` ONLY under a directory whose name ends in `-setup` (line 134); for any
// other skill the only location it sees is `skills/<skill>/module.yaml`.
//
// This rule's predecessor, `no-root-module-yaml`, forbade exactly that file -- reasoned, like
// ADR-0008, from the validator alone. The result passed every gate and produced an install
// whose `_bmad/config.toml` BMad's own resolver refused to parse. Discovery wins.
//
// Scope is derived from `byCode`: the standalone module homes are the ones that must carry the
// root copy, and every other skill must not. Nothing is enumerated by hand.
function checkDiscoveryLayout(byCode, skills) {
  const standaloneHomes = new Set();
  for (const [, { assets }] of byCode) {
    if (assets.length !== 1) continue; // check 3 reports these
    const home = assets[0].skill;
    if (!home.endsWith("-setup")) standaloneHomes.add(home);
  }

  for (const skill of skills) {
    const rootRel = `skills/${skill}/module.yaml`;
    const assetsRel = `skills/${skill}/assets/module.yaml`;
    if (standaloneHomes.has(skill)) {
      if (!exists(rootRel)) {
        failures.push(
          `standalone module home skills/${skill} has no ${rootRel} -- BMad's installer ` +
          `(project-root.js searchRootAll) only looks under assets/ for a *-setup skill, so ` +
          `without this copy the module's own module.yaml is undiscoverable and its settings ` +
          `are filed under another module's code. It must be byte-identical to ${assetsRel}.`
        );
      } else if (read(rootRel) !== read(assetsRel)) {
        failures.push(
          `${rootRel} and ${assetsRel} differ -- they are the same module declaration read by ` +
          `two different BMad tools (the installer's discovery, and validate-module.py). ` +
          `Copy one over the other.`
        );
      }
    } else if (exists(rootRel)) {
      failures.push(
        `module.yaml at a skill root that is not a standalone module home: ${rootRel} -- ` +
        `a *-setup module home is discovered at assets/module.yaml, and a skill that is not a ` +
        `module home declares no module at all.`
      );
    }
  }

  // `skills/module.yaml` is the multi-module marker: it is what searchRootAll() returns FIRST
  // for a local `--custom-source` install, where `searchRoot()` takes all[0] with no matching
  // on the requested module's code. Declaring no `code:` there makes the TOML section key fall
  // back to each module's own name; declaring no `agents:` there stops one agent block being
  // emitted once per installed module. Both produce a duplicate TOML table, which `tomllib`
  // rejects outright. The file itself documents the mechanism.
  const markerRel = "skills/module.yaml";
  if (!exists(markerRel)) {
    failures.push(
      `${markerRel} is missing -- it is the first candidate BMad's searchRootAll() returns, ` +
      `and without it a local --custom-source install resolves every module to whichever ` +
      `skills/*/module.yaml the filesystem happens to list first.`
    );
  } else {
    const marker = parseModuleYaml(markerRel, read(markerRel));
    for (const forbidden of ["code", "name", "agents"]) {
      if (marker[forbidden] !== undefined) {
        failures.push(
          `${markerRel} declares '${forbidden}' -- it must declare none of code/name/agents. ` +
          `A 'code' there becomes the [modules.<code>] section key for EVERY installed module; ` +
          `an 'agents' array there is emitted once per installed module. Either produces a ` +
          `duplicate TOML table and a config layer no skill can read.`
        );
      }
    }
  }

  // PluginResolver strategy 1 (_tryRootModuleFiles) fires when module.yaml AND module-help.csv
  // both sit at the common parent of a plugin's skills. Every plugin here has `skills/` as that
  // common parent, so a `skills/module-help.csv` would collapse all four plugins into one
  // module. The marker above is safe precisely because this file does not exist.
  if (exists("skills/module-help.csv")) {
    failures.push(
      `skills/module-help.csv exists -- with skills/module.yaml beside it, BMad's ` +
      `PluginResolver strategy 1 would resolve every plugin in marketplace.json to a single ` +
      `module. It must not exist.`
    );
  }
}

// Collects every module.yaml under skills/ -- at a skill root (what BMad's installer
// discovers, check 1) or under assets/ (the module home that validate-module.py reads) --
// grouped by the code each declares. Root-level files are included here so a code that exists
// ONLY at a skill root is still known, and reported as missing its home by check 3, instead of
// being invisible because nothing under assets/ mentions it yet.
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

    // "Which skills belong to this module" — see the shared derivation below.
    const siblings = siblingsOfCode(code, skills, byCode);
    const siblingCount = siblings.size;
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
    const siblings = [...siblingsOfCode(code, skills, byCode)];
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
//
// `_meta` is the ONE reserved value that is not a skill. bmad-help/SKILL.md ("Module docs")
// defines it: a row whose `skill` column is the literal `_meta` carries the module's
// documentation URL or path in `output-location`, and bmad-help fetches it to answer general
// questions about that module. Both of BMad 6.12.0's own catalogs ship one
// (src/bmm-skills/module-help.csv:2, src/core-skills/module-help.csv:2). The exemption is
// exactly that one literal -- every other non-skill value is still an orphan.
const CSV_META_SKILL = "_meta";

function checkCsvSkillsExist(skills) {
  const knownSkills = new Set(skills);
  for (const skill of skills) {
    const rel = `skills/${skill}/assets/module-help.csv`;
    if (!exists(rel)) continue; // check 4 already reports a module home missing this file
    const rows = parseCsvRows(rel, read(rel));
    for (const row of rows) {
      const csvSkill = fieldText(row.skill).trim();
      if (!csvSkill) continue;
      if (csvSkill === CSV_META_SKILL) continue; // reserved module-documentation row
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
// 8. plugin-resolver-strategy: every plugin in .claude-plugin/marketplace.json must resolve to
// an AUTHORED PluginResolver strategy (1-4), never the synthesized fallback (5).
//
// The functions below mirror bmad-method 6.12.0's
// tools/installer/modules/plugin-resolver.js -- `resolve()`, `_tryRootModuleFiles`,
// `_trySetupSkill`, `_trySingleStandalone`, `_tryMultipleStandalone` and
// `_computeCommonParent` -- condition for condition, from the source and not from a summary of
// it. Four of its conditions are easy to get wrong from a description, and each has a test:
//
//   * a listed skill path that does not EXIST on disk is dropped by resolve() before any
//     strategy runs, so `skillPaths.length === 1` (strategy 3) counts existing skills, not
//     listed ones;
//   * a listed path that escapes the repo root (`..`, or an absolute path) is dropped by the
//     same loop;
//   * strategy 1 looks for `module.yaml` + `module-help.csv` at the skills' COMMON PARENT
//     directory itself -- not under an `assets/` subdirectory -- and for a single-skill plugin
//     that common parent is `skills/`. Check 1(c) forbidding `skills/module-help.csv` is what
//     keeps strategy 1 from firing here and collapsing all four plugins into one module;
//   * `_readModuleYaml` returns `yaml.parse(content)` and every strategy bails on a FALSY
//     result, so an empty or unparseable `module.yaml` is not a `module.yaml`. Existence alone
//     is not the resolver's test.
//
// Reported per plugin under -v so a reader can see what this concluded, rather than trusting
// that it concluded anything.
const MARKETPLACE_REL = ".claude-plugin/marketplace.json";

// "Which skills belong to this module code" derives from three sources, tried in a
// deliberate order:
//
//   1. If a skill's own module.yaml declares a code, THAT is the answer for that skill (source
//      of truth — a skill that says "I'm code X" cannot be a sibling of code Y).
//   2. Otherwise, the naming convention `<code>-*` (or exact `<code>`) still applies. The
//      3.1.3 rename replaced `l3io-pm-execute`/`l3io-pm-plan` with `l3io-execute`/`l3io-plan`
//      — names that no longer match the l3io-pm convention — so this fallback is not enough
//      on its own.
//   3. Otherwise, the plugin's own `skills[]` array in marketplace.json (the source of truth
//      once a plugin lists them). Also gated by (1): a skill listed in one plugin but
//      declaring a different code in its own module.yaml belongs to the code it declares,
//      not the plugin that lists it. Test "check:module passes a two-skill plugin where both
//      skills carry the module files" pins this: plugin `alpha` lists `alpha` and `beta`,
//      but `beta` declares `code: beta` and is a sibling of code beta, not alpha.
//
// Returns a Set of skill directory names.
function siblingsOfCode(code, skills, byCode) {
  // codeOfSkill: skill → declared code (from any of the byCode entries for it), or null.
  const codeOfSkill = new Map();
  for (const [c, { assets, root }] of byCode) {
    for (const { skill } of [...assets, ...root]) {
      codeOfSkill.set(skill, c);
    }
  }
  const marketplaceSkills = new Set(marketplaceSkillsForCode(code));
  const out = new Set();
  for (const s of skills) {
    const explicit = codeOfSkill.get(s);
    if (explicit !== undefined) {
      if (explicit === code) out.add(s);
      continue;
    }
    if (s === code || s.startsWith(`${code}-`)) out.add(s);
    else if (marketplaceSkills.has(s)) out.add(s);
  }
  return out;
}

// Return the skill directory names declared in marketplace.json for the plugin whose `name`
// matches the given module code (in this package, the plugin `name` IS the module code).
// Skill paths like "./skills/l3io-execute" collapse to their leaf directory ("l3io-execute").
// Any parse or shape error yields an empty list — the check's siblings computation unions
// this with the naming-convention fallback, so a partial answer here still counts naming
// matches, and a broken marketplace is already reported by check 8.
function marketplaceSkillsForCode(code) {
  if (!exists(MARKETPLACE_REL)) return [];
  let marketplace;
  try { marketplace = JSON.parse(read(MARKETPLACE_REL)); } catch { return []; }
  if (!marketplace || !Array.isArray(marketplace.plugins)) return [];
  const plugin = marketplace.plugins.find(
    (p) => p && typeof p === "object" && fieldText(p.name).trim() === code);
  if (!plugin || !Array.isArray(plugin.skills)) return [];
  return plugin.skills
    .map((s) => (typeof s === "string" ? path.basename(s) : ""))
    .filter(Boolean);
}

const STRATEGY_NAMES = {
  1: "root module files at the skills' common parent",
  2: "a *-setup skill's assets/",
  3: "the single listed skill's assets/",
  4: "every listed skill's assets/",
  5: "SYNTHESIZED fallback from SKILL.md frontmatter",
};

// plugin-resolver.js `_readModuleYaml`: parse, and treat any parse failure or falsy document
// (an empty file parses to null) as "no module.yaml here".
function resolverReadsModuleYaml(absPath) {
  let text;
  try {
    text = fs.readFileSync(absPath, "utf8");
  } catch {
    return false;
  }
  try {
    return Boolean(YAML.parse(text));
  } catch {
    return false;
  }
}

// plugin-resolver.js: a skill is usable by strategies 2/3/4 when BOTH assets files exist and
// the module.yaml parses to something truthy.
function hasAssetsModuleFiles(skillAbs) {
  return (
    fs.existsSync(path.join(skillAbs, "assets", "module.yaml")) &&
    fs.existsSync(path.join(skillAbs, "assets", "module-help.csv")) &&
    resolverReadsModuleYaml(path.join(skillAbs, "assets", "module.yaml"))
  );
}

// plugin-resolver.js `_computeCommonParent`: the deepest common ancestor, and for a single
// path the path's own dirname.
function computeCommonParent(absPaths) {
  if (absPaths.length === 0) return "/";
  if (absPaths.length === 1) return path.dirname(absPaths[0]);
  const segments = absPaths.map((p) => p.split(path.sep));
  const minLen = Math.min(...segments.map((s) => s.length));
  const common = [];
  for (let i = 0; i < minLen; i++) {
    const segment = segments[0][i];
    if (segments.every((s) => s[i] === segment)) common.push(segment);
    else break;
  }
  return common.join(path.sep) || "/";
}

// plugin-resolver.js `resolve()`: normalize, constrain to the repo root, drop what is not on
// disk, then try the five strategies in order. Returns the strategy number, or null when
// resolve() would return [] -- no module installed at all.
function resolvePluginStrategy(plugin) {
  const skillRelPaths = Array.isArray(plugin.skills) ? plugin.skills : [];
  if (skillRelPaths.length === 0) return { strategy: null, reason: "no-skills" };

  const skillPaths = [];
  for (const rel of skillRelPaths) {
    if (typeof rel !== "string") continue;
    const normalized = rel.replace(/^\.\//, "");
    const abs = path.resolve(repoRoot, normalized);
    if (!abs.startsWith(repoRoot + path.sep) && abs !== repoRoot) continue;
    if (fs.existsSync(abs)) skillPaths.push(abs);
  }
  if (skillPaths.length === 0) return { strategy: null, reason: "no-skill-exists" };

  // Strategy 1
  const commonParent = computeCommonParent(skillPaths);
  if (
    fs.existsSync(path.join(commonParent, "module.yaml")) &&
    fs.existsSync(path.join(commonParent, "module-help.csv")) &&
    resolverReadsModuleYaml(path.join(commonParent, "module.yaml"))
  ) {
    return { strategy: 1, skillPaths, where: path.relative(repoRoot, commonParent) || "." };
  }

  // Strategy 2
  for (const skillAbs of skillPaths) {
    if (!path.basename(skillAbs).endsWith("-setup")) continue;
    if (!hasAssetsModuleFiles(skillAbs)) continue;
    return { strategy: 2, skillPaths, where: path.relative(repoRoot, skillAbs) };
  }

  // Strategy 3
  if (skillPaths.length === 1) {
    if (hasAssetsModuleFiles(skillPaths[0])) {
      return { strategy: 3, skillPaths, where: path.relative(repoRoot, skillPaths[0]) };
    }
  }

  // Strategy 4 -- ALL listed skills, or plugin-resolver.js falls through to synthesis.
  if (skillPaths.length >= 2) {
    const resolved = skillPaths.filter((skillAbs) => hasAssetsModuleFiles(skillAbs));
    if (resolved.length === skillPaths.length) {
      return { strategy: 4, skillPaths, where: resolved.map((p) => path.relative(repoRoot, p)).join(", ") };
    }
  }

  return { strategy: 5, skillPaths };
}

function checkPluginResolverStrategy() {
  if (!exists(MARKETPLACE_REL)) {
    failures.push(
      `${MARKETPLACE_REL} is missing -- it is the scope this check derives its plugin set ` +
      `from, and it is what BMad's installer resolves. Without it nothing here is checked.`
    );
    return [];
  }

  let marketplace;
  try {
    marketplace = JSON.parse(read(MARKETPLACE_REL));
  } catch (e) {
    failures.push(`${MARKETPLACE_REL}: is not valid JSON (${String(e.message).split("\n")[0]})`);
    return [];
  }

  if (!Array.isArray(marketplace?.plugins)) {
    failures.push(
      `${MARKETPLACE_REL} declares no 'plugins' array -- BMad's installer resolves one module ` +
      `per entry there, so an absent or non-array 'plugins' installs nothing.`
    );
    return [];
  }

  const report = [];
  for (const plugin of marketplace.plugins) {
    const name = fieldText(plugin?.name).trim() || "(unnamed)";
    if (!plugin || typeof plugin !== "object" || Array.isArray(plugin)) {
      failures.push(`${MARKETPLACE_REL}: plugin entry ${name} is not an object`);
      continue;
    }

    const result = resolvePluginStrategy(plugin);

    if (result.strategy === null) {
      const why = result.reason === "no-skills"
        ? `plugin '${name}' declares no 'skills' array`
        : `plugin '${name}' lists only skill paths that do not exist under the repository root`;
      failures.push(
        `${why} -- BMad's PluginResolver.resolve() returns an empty result for it, so the ` +
        `installer registers no module for this plugin at all. Listed: ` +
        `${JSON.stringify(plugin.skills ?? null)}.`
      );
      continue;
    }

    report.push(`  plugin '${name}' resolves by PluginResolver strategy ${result.strategy} ` +
                `(${STRATEGY_NAMES[result.strategy]})${result.where ? ` -> ${result.where}` : ""}`);

    if (result.strategy === 5) {
      failures.push(
        `plugin '${name}' resolves by PluginResolver strategy 5 (${STRATEGY_NAMES[5]}) -- ` +
        `BMad's installer would IGNORE every authored module-help.csv for this plugin and ` +
        `synthesize a stub catalog instead: 'action: activate' on every row, title-cased ` +
        `display names, generated 3-letter menu codes, no relationships and no ` +
        `output-location. The install still exits 0 and nothing warns. ` +
        `Existing skills it listed: ` +
        `${result.skillPaths.map((p) => path.relative(repoRoot, p)).join(", ") || "(none)"}. ` +
        `To reach an authored strategy: give the plugin exactly one existing skill carrying ` +
        `assets/module.yaml + assets/module-help.csv (strategy 3), give EVERY listed skill ` +
        `both files (strategy 4), or add a '*-setup' skill carrying both (strategy 2).`
      );
    }
  }

  return report;
}

// ---------------------------------------------------------------------------
// 9. help-registration: every mode keyword a skill documents must either carry a
// `module-help.csv` row or be excluded, in the routing table itself, by name.
//
// Why: a capability with no CSV row cannot be selected from BMad's help menu at all, and the
// registration and the keyword table are two copies of the same fact in two files. Tasks 1-6
// of the module-help-registration plan corrected that by hand across four CSVs -- two
// advertised flags that no skill parsed, a fabricated `args` value, two unregistered
// `l3io-help` modes and a doctor registering one capability out of twenty-one. Nothing
// would have caught any of it, and nothing would catch the next one (repo CLAUDE.md §3: when
// you write a rule, write the check that enforces it in the same change).
//
// THE EXCLUSION SET IS DERIVED, NOT LISTED HERE. `skills/l3io-doctor/SKILL.md`'s routing
// table carries a `Menu` column whose value per keyword is:
//
//   registered       -- carries its own row, whose `action` column equals the keyword
//   default          -- served by the module's bare-invocation row (empty `action`, which is
//                       BMad's own convention for a default invocation)
//   health-check     -- deliberately unregistered: the health check already proposes it, and
//                       a global menu entry would invite running a migration or a repair
//                       WITHOUT the diagnosis that decides whether it is needed
//   not-a-capability -- help output or module setup
//
// A checker holding its own copy of that list would drift from it exactly the way the rows
// drifted from the skills (root CLAUDE.md §4: derive the scope from the source of truth,
// never enumerate it by hand). An unrecognised value is a FAILURE rather than an exclusion,
// so a typo cannot quietly drop a keyword out of scope, and a table with NO `Menu` column
// claims every keyword it lists is registered -- deleting the column makes the rule stricter.
//
// SCOPE, and how it survives the table being deleted. Deriving the expectation only from the
// table under test would pass vacuously the moment the table went away. Two anchors outside
// it, each independently sufficient, make a skill OWE a keyword table:
//
//   (a) mode files on disk -- a top-level `steps/<name>.md` that is not part of a numbered
//       `step-NN-*.md` sequence IS a mode (root CLAUDE.md, "Module Layout": add a mode as a
//       file plus a table row). Sixteen of them under l3io-doctor, two under
//       l3io-help; the sequential step files of the PM skills are not modes and are not
//       counted.
//   (b) the "Recognized keywords" paragraph both real tables sit under, for a skill whose
//       modes are not one-file-per-mode.
//
// KNOWN GAP, stated rather than implied: the check is one-directional per keyword. It does
// not require every CSV row to map back to a table entry, because three skills
// (l3io-plan, l3io-sync, l3io-execute) document their modes in prose rather than a
// routing table, and l3io-help's `status` row is served by its default fallthrough rather
// than a keyword. Rows whose `action` no skill parses are check 25 of check:docs's territory
// for the doctor, and nobody's for the rest.
//
// Parsing: the routing table is split with `csv-parse` on a `|` delimiter with quoting
// disabled -- markdown cells are not CSV fields, and a hand-written splitter is what this
// repo's global rule 1 exists to prevent. A cell containing a literal `|` inside backticks
// would still split wrongly; no table here has one.
const KEYWORD_HEADER = "keyword";
const MENU_HEADER = "menu";
const MENU_REGISTERED = "registered";
const MENU_DEFAULT = "default";
const MENU_VALUES = new Set([MENU_REGISTERED, MENU_DEFAULT, "health-check", "not-a-capability"]);
const RECOGNIZED_KEYWORDS_RE = /\*\*Recognized keywords\*\*/i;
const TABLE_DIVIDER_CELL_RE = /^:?-+:?$/;
const NUMBERED_STEP_RE = /^step-\d/;

// One markdown table row as trimmed cells, or null when the line is not a table row. The
// leading and trailing empty cells a `| a | b |` row produces are dropped.
function pipeCells(rel, line) {
  if (!line.trimStart().startsWith("|")) return null;
  let records;
  try {
    records = parseCsv(line, {
      delimiter: "|",
      quote: false,
      escape: false,
      relax_column_count: true,
      skip_empty_lines: true,
      trim: false,
    });
  } catch (e) {
    failures.push(`${rel}: table row is unreadable (${String(e.message).split("\n")[0]})`);
    return null;
  }
  const cells = (records[0] ?? []).map((c) => c.trim());
  if (cells.length && cells[0] === "") cells.shift();
  if (cells.length && cells[cells.length - 1] === "") cells.pop();
  return cells;
}

// Every routing table in a SKILL.md: a header row whose first column is `Keyword`, its
// divider row, and the contiguous rows under it.
function keywordTables(rel, text) {
  const lines = text.split("\n");
  const tables = [];
  for (let i = 0; i < lines.length; i++) {
    const header = pipeCells(rel, lines[i]);
    if (!header || header.length < 2) continue;
    if (header[0].toLowerCase() !== KEYWORD_HEADER) continue;
    const divider = pipeCells(rel, lines[i + 1] ?? "");
    if (!divider || !divider.every((c) => TABLE_DIVIDER_CELL_RE.test(c))) continue;
    const rows = [];
    let j = i + 2;
    for (; j < lines.length; j++) {
      const cells = pipeCells(rel, lines[j]);
      if (!cells) break;
      rows.push({ cells, line: j + 1 });
    }
    tables.push({ headers: header.map((h) => h.toLowerCase()), rows, line: i + 1 });
    i = j;
  }
  return tables;
}

const backticked = (cell) => [...cell.matchAll(/`([^`]+)`/g)].map((m) => m[1].trim()).filter(Boolean);

// Top-level `steps/*.md` files that are modes: a numbered `step-NN-*.md` is one step of a
// single procedure, not a mode with a keyword of its own.
function modeFiles(skill) {
  const abs = path.join(repoRoot, "skills", skill, "steps");
  if (!fs.existsSync(abs)) return [];
  return fs.readdirSync(abs, { withFileTypes: true })
    .filter((e) => e.isFile() && e.name.endsWith(".md") && !NUMBERED_STEP_RE.test(e.name))
    .map((e) => `steps/${e.name}`)
    .sort();
}

function checkHelpRegistration(skills) {
  // Every row of every module-help.csv in the tree, indexed by the skill it registers. A
  // skill's rows do not necessarily live in its own directory: the whole l3io-pm module is
  // registered from skills/l3io-setup/assets/module-help.csv.
  const actionsBySkill = new Map();
  for (const skill of skills) {
    const rel = `skills/${skill}/assets/module-help.csv`;
    if (!exists(rel)) continue;
    for (const row of parseCsvRows(rel, read(rel))) {
      const registered = fieldText(row.skill).trim();
      if (!registered || registered === CSV_META_SKILL) continue;
      if (!actionsBySkill.has(registered)) actionsBySkill.set(registered, new Set());
      actionsBySkill.get(registered).add(fieldText(row.action).trim());
    }
  }

  let tableCount = 0;
  let keywordCount = 0;
  let requiredCount = 0;

  for (const skill of skills) {
    const rel = `skills/${skill}/SKILL.md`;
    if (!exists(rel)) continue;
    const text = read(rel);
    const tables = keywordTables(rel, text);

    if (tables.length === 0) {
      const modes = modeFiles(skill);
      const owes = modes.length > 0 || RECOGNIZED_KEYWORDS_RE.test(text);
      if (owes) {
        const why = modes.length > 0
          ? `it carries ${modes.length} mode file(s) (${modes.join(", ")})`
          : `it has a "Recognized keywords" section`;
        failures.push(
          `${rel}: no keyword table, but ${why} -- a mode is a file plus a routing row, and ` +
          `the routing table is where this check reads which keywords are registered in ` +
          `module-help.csv and which are deliberately not. With the table gone there is ` +
          `nothing to check and every keyword would pass unregistered.`
        );
      }
      continue;
    }

    for (const table of tables) {
      tableCount += 1;
      const menuIndex = table.headers.indexOf(MENU_HEADER);
      if (table.rows.length === 0) {
        failures.push(`${rel}:${table.line}: keyword table has no rows -- it documents no keyword at all.`);
        continue;
      }
      for (const { cells, line } of table.rows) {
        const aliases = backticked(cells[0] ?? "");
        if (aliases.length === 0) {
          failures.push(
            `${rel}:${line}: keyword table row names no backticked keyword -- ` +
            `first cell: '${cells[0] ?? ""}'.`
          );
          continue;
        }
        keywordCount += 1;

        // No Menu column at all: the table claims every keyword it lists is registered.
        const menu = menuIndex === -1 ? MENU_REGISTERED : (cells[menuIndex] ?? "").trim();
        if (!MENU_VALUES.has(menu)) {
          failures.push(
            `${rel}:${line}: keyword ${aliases.map((a) => `\`${a}\``).join(" / ")} has Menu ` +
            `value '${menu}', which is not one of ${[...MENU_VALUES].join(", ")} -- this ` +
            `column is the source of truth for which keywords must be registered, so an ` +
            `unrecognised value is a failure rather than a silent exclusion.`
          );
          continue;
        }
        if (menu !== MENU_REGISTERED && menu !== MENU_DEFAULT) continue; // excluded, by name

        requiredCount += 1;
        const actions = actionsBySkill.get(skill) ?? new Set();
        const want = menu === MENU_DEFAULT ? [""] : aliases;
        if (want.some((a) => actions.has(a))) continue;

        const shown = aliases.map((a) => `\`${a}\``).join(" / ");
        failures.push(
          menu === MENU_DEFAULT
            ? `${rel}:${line}: keyword ${shown} is marked '${MENU_DEFAULT}', but no ` +
              `module-help.csv row registers skill '${skill}' with an empty 'action' column ` +
              `-- that bare-invocation row is what the default keyword routes to.`
            : `${rel}:${line}: keyword ${shown} is marked '${MENU_REGISTERED}', but no ` +
              `module-help.csv row registers skill '${skill}' with a matching 'action' ` +
              `column (rows found: ${[...actions].map((a) => `'${a}'`).join(", ") || "none"}) ` +
              `-- a capability with no row cannot be reached from BMad's help menu. Add the ` +
              `row, or mark the keyword excluded in the Menu column and say why.`
        );
      }
    }
  }

  if (verbose) {
    console.log(`  help-registration: ${tableCount} keyword table(s), ${keywordCount} keyword(s), ` +
      `${requiredCount} of them expecting a module-help.csv row`);
  }
}

// ---------------------------------------------------------------------------
// 10. agent-roster: every `agents[]` entry in a module.yaml agrees, field for field, with the
// `[agent]` block in the customize.toml of the skill that implements it.
//
// Why: these are the same declaration in two files that are read by two different things at
// two different times. The installer reads the ROSTER
// (manifest-generator.js `collectAgentsFromModuleYaml`) and writes each entry into
// `_bmad/config.toml` as `[agents.<code>]` with `name`, `title`, `icon` and `description`;
// the skill reads its OWN `[agent]` block at activation through
// `resolve_customization.py --key agent`. A drifted icon or title therefore shows one
// identity in the installed config and another when the agent speaks, and nothing compared
// them -- the last cross-file pair in this repo with no guard. BMad's own module-builder
// validation workflow calls out icon drift by name.
//
// `code` IS NOT A DIRECTORY NAME, and this check is where that is recorded mechanically.
// BMad's module-builder guidance suggests matching the skill directory's basename, and
// `l3io-sec-redteam` deliberately does not: its roster says `code: redteam`. Verified against
// bmad-method 6.12.0 before relying on it -- `manifest-generator.js:589`, `:597` and `:608`
// use `agent.code` only to build the `[agents.<code>]` TOML section key, and
// `tools/installer/project-root.js` never mentions agents at all (its one `agent` match is a
// `src/core-skills/agents` probe for BMad's own source tree). So the roster entry is matched
// to its skill through the `[agent] code` in that skill's customize.toml, never through the
// directory name -- which also means the pair is checked in both directions:
//
//   * a roster entry whose code no skill in that module declares is an agent the installer
//     writes into config.toml and nothing implements;
//   * a customize.toml `[agent]` block that no roster lists is an agent that is never written
//     to config.toml at all -- the silent direction, because the skill still activates.
//
// `name` may be empty (a First-Breath agent fills it after activation) but the KEY must be
// present on both sides; `title`, `icon` and `description` must be non-empty on both.
//
// Scope is derived: the module codes come from `byCode`, a module's skills the same way
// checks 5 and 6 derive them (the directory named exactly the code, or prefixed `{code}-`),
// and the `[agent]` blocks by walking `skills/`. Nothing here is a hand-kept list.
//
// TOML is parsed with `smol-toml`, not a regex (global rule 1). check-docs.mjs's `tomlInt()`
// reads a single integer key with a regex and is not a parser; an identity comparison needs
// the real quoting and escaping rules.
const AGENT_TEXT_FIELDS = ["title", "icon", "description"];

// The `[agent]` table of a skill's customize.toml, or null when the file is absent or
// declares a `[workflow]` instead (every non-agent skill).
function parseCustomizeAgent(rel) {
  if (!exists(rel)) return null;
  let doc;
  try {
    doc = parseToml(read(rel));
  } catch (e) {
    failures.push(`${rel}: is not valid TOML (${String(e.message).split("\n")[0]})`);
    return null;
  }
  const agent = doc?.agent;
  if (!agent || typeof agent !== "object" || Array.isArray(agent)) return null;
  return agent;
}

function checkAgentRoster(byCode, skills) {
  const agentSkills = new Map(); // skill -> { rel, agent }
  for (const skill of skills) {
    const rel = `skills/${skill}/customize.toml`;
    const agent = parseCustomizeAgent(rel);
    if (agent) agentSkills.set(skill, { rel, agent });
  }

  const claimed = new Set(); // `${skill}\0${code}` pairs a roster entry resolved to
  let entryCount = 0;

  for (const [code, { assets }] of byCode) {
    for (const { rel, fields } of assets) {
      const roster = fields.agents;
      if (roster === undefined) continue;
      if (!Array.isArray(roster)) {
        failures.push(
          `${rel}: 'agents' is ${JSON.stringify(fieldText(roster))}, not a list -- the ` +
          `installer iterates it to write one [agents.<code>] block per entry, and a ` +
          `non-list contributes nothing.`
        );
        continue;
      }
      const siblings = [...siblingsOfCode(code, skills, byCode)];

      for (const [i, entry] of roster.entries()) {
        entryCount += 1;
        const where = `${rel}: agents[${i}]`;
        if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
          failures.push(`${where} is not a mapping: ${JSON.stringify(fieldText(entry))}`);
          continue;
        }
        const agentCode = fieldText(entry.code).trim();
        if (!agentCode) {
          failures.push(
            `${where}: missing or empty 'code' -- it is the [agents.<code>] section key the ` +
            `installer writes into _bmad/config.toml, and manifest-generator.js skips an ` +
            `entry whose code is not a string.`
          );
          continue;
        }
        if (!("name" in entry)) {
          failures.push(
            `${where} ('${agentCode}'): no 'name' key -- an EMPTY name is valid (a ` +
            `First-Breath agent fills it after activation), an absent one is not: the ` +
            `installer writes name = '' either way, so the omission is indistinguishable ` +
            `from a forgotten field.`
          );
        }
        for (const field of AGENT_TEXT_FIELDS) {
          if (fieldText(entry[field]).trim() === "") {
            failures.push(
              `${where} ('${agentCode}'): '${field}' is missing or empty -- the installer ` +
              `writes it into [agents.${agentCode}] verbatim, and an empty one is what the ` +
              `user sees in the agent roster.`
            );
          }
        }

        const matches = siblings.filter(
          (s) => agentSkills.has(s) && fieldText(agentSkills.get(s).agent.code).trim() === agentCode
        );
        if (matches.length === 0) {
          failures.push(
            `${where}: declares agent '${agentCode}', but no skill in module '${code}' has a ` +
            `customize.toml [agent] block with that code (looked in: ` +
            `${siblings.map((s) => `skills/${s}`).join(", ") || "no sibling skills"}) -- the ` +
            `installer would write [agents.${agentCode}] into _bmad/config.toml for an agent ` +
            `nothing implements. The roster entry is matched to its skill through that ` +
            `[agent] code, never through the directory name.`
          );
          continue;
        }
        if (matches.length > 1) {
          failures.push(
            `${where}: agent code '${agentCode}' is declared by more than one skill ` +
            `(${matches.map((s) => `skills/${s}/customize.toml`).join(", ")}) -- one code is ` +
            `one [agents.<code>] TOML table, so two skills claiming it is a duplicate table.`
          );
          continue;
        }

        const skill = matches[0];
        claimed.add(`${skill}\u0000${agentCode}`);
        const { rel: tomlRel, agent } = agentSkills.get(skill);
        if (!("name" in agent)) {
          failures.push(
            `${tomlRel}: [agent] has no 'name' key, but ${where} declares one -- the two are ` +
            `the same field read by the installer and by the skill itself.`
          );
        }
        for (const field of AGENT_TEXT_FIELDS) {
          const rosterValue = fieldText(entry[field]);
          const skillValue = fieldText(agent[field]);
          if (rosterValue === skillValue) continue;
          failures.push(
            `${where} ('${agentCode}'): '${field}' is ${JSON.stringify(rosterValue)}, but ` +
            `${tomlRel}'s [agent] block says ${JSON.stringify(skillValue)} -- the installer ` +
            `writes the roster value into _bmad/config.toml and the skill reads its own at ` +
            `activation, so the agent has two identities. Make them equal.`
          );
        }
      }
    }
  }

  for (const [skill, { rel, agent }] of agentSkills) {
    const agentCode = fieldText(agent.code).trim();
    if (!agentCode) {
      failures.push(
        `${rel}: [agent] declares no 'code' -- it is what ties this block to its module.yaml ` +
        `roster entry and what becomes the [agents.<code>] section key.`
      );
      continue;
    }
    if (claimed.has(`${skill}\u0000${agentCode}`)) continue;
    failures.push(
      `${rel}: declares agent '${agentCode}', but no module.yaml roster in its module lists ` +
      `it -- the installer writes [agents.<code>] blocks from the roster ALONE, so this ` +
      `agent never reaches _bmad/config.toml. The skill still activates, which is why this ` +
      `direction fails silently.`
    );
  }

  if (verbose) {
    console.log(`  agent-roster: ${entryCount} roster entry/entries, ` +
      `${agentSkills.size} skill [agent] block(s)`);
  }
}

// ---------------------------------------------------------------------------
// 11. setup-singleton: at most one `*-setup` directory per module code.
//
// BMad picks a module's setup skill with a first-match scan and no tie-break:
//
//     for d in module_dir.iterdir():
//         if d.is_dir() and d.name.endswith("-setup"):
//             return d
//
// So a second `*-setup` directory does not add a candidate, it REPLACES the answer roughly
// half the time -- and deterministically, on any filesystem that returns entries sorted, if
// the wrong name happens to sort first. Membership is derived with `siblingsOfCode()`, the
// same derivation checks 5 and 6 use, so a renamed or added skill is picked up without
// telling this rule about it.
//
// The failure is silent at every layer above it: the forwarder that caused this carried no
// `module.yaml`, so module registration resolved to a directory with nothing to register and
// the install still exited 0.
function checkSetupSingleton(byCode, skills) {
  for (const code of byCode.keys()) {
    const setups = [...siblingsOfCode(code, skills, byCode)].filter((s) => s.endsWith("-setup"));
    if (setups.length > 1) {
      const sorted = [...setups].sort();
      failures.push(
        `module '${code}' has ${setups.length} *-setup directories: ${setups.map((s) => `skills/${s}`).join(", ")} -- ` +
        `BMad's find_setup_skill() returns the FIRST one in filesystem order, so the module ` +
        `home is whichever the filesystem hands back. On a sorted-order filesystem that is ` +
        `always skills/${sorted[0]}. Exactly one directory per module may end in '-setup'.`
      );
    }
  }
}

// ---------------------------------------------------------------------------
// 12. menu-code-unique: no two rows in one module's module-help.csv share a `menu-code`.
//
// The menu code is the SELECTOR a user types to pick a capability out of BMad's help menu.
// Two rows carrying the same one is not a cosmetic duplicate: one of the two capabilities
// becomes unreachable, and which one loses is decided by whatever the menu builder does with
// the collision -- not by anything either row says.
//
// Shipped in 3.1.3: `/l3io-help catalog` was added with menu code LPC, which `l3io-sync`'s
// Sync row already held. It survived five releases because every gate over the CSV asked a
// different question -- rule 7 asks whether each row's `skill` column names a real directory,
// rule 9 asks whether every documented keyword HAS a row -- and none of them compared two rows
// to each other. `validate-module.py` does report it, but it needs a real BMad install, so it
// only runs in `smoke:install`, which is not in CI.
//
// Scope is every `skills/*/assets/module-help.csv`, derived by walking `skills/` like every
// other rule here. Codes are compared case-insensitively: they are typed by a human at a menu,
// and `lpc` selecting a row that wrote `LPC` is the same collision.
//
// `_meta` rows are not capabilities and carry no menu code; a row with an empty code is
// skipped rather than counted as colliding with every other empty one.
//
// What it does NOT reach: a code reused by two DIFFERENT modules. Each module's rows are
// assembled into its own menu, so that is a different question and no evidence here says it
// collides; as of this writing the four CSVs share no code anyway, so widening the scope would
// assert something unmeasured over a set that happens to pass.
function checkMenuCodeUnique(skills) {
  for (const skill of skills) {
    const rel = `skills/${skill}/assets/module-help.csv`;
    if (!exists(rel)) continue;
    const seen = new Map();
    for (const row of parseCsvRows(rel, read(rel))) {
      const code = fieldText(row["menu-code"]).trim();
      if (!code) continue;
      const key = code.toLowerCase();
      const prior = seen.get(key);
      if (prior) {
        failures.push(
          `${rel}: menu-code '${code}' is claimed by two rows -- ` +
          `'${prior.skill}' (${prior.name}) and '${fieldText(row.skill)}' (${fieldText(row["display-name"])}). ` +
          `The menu code is what a user types to select a capability, so a duplicate makes one ` +
          `of the two unreachable from BMad's help menu.`
        );
        continue;
      }
      seen.set(key, { skill: fieldText(row.skill), name: fieldText(row["display-name"]) });
    }
  }
}

// ---------------------------------------------------------------------------
// 13. forwarder-shape: a DEPRECATED forwarder actually forwards, to the skill it claims.
//
// Rules 8 and 11 already carry the forwarder PLACEMENT law -- a deprecated forwarder is safe
// only at a name BMad's resolver derives no meaning from. This is the other half, and it is a
// different question: given that a forwarder sits at a legal name, does it send the user to
// the right place? Nothing checked that. A forwarder is the one kind of skill whose entire
// body is a claim about another skill, and every one of them here was produced by copying its
// neighbour and editing the names -- five edits per file, in four files, with no gate over
// whether an edit was missed. The failure mode is silent in the worst way: the skill activates,
// prints a confident deprecation notice, and runs somebody else's workflow.
//
// SCOPE IS DERIVED, like every other rule here: a forwarder is any `skills/*/SKILL.md` whose
// frontmatter `description` begins `DEPRECATED forwarder for /<target>`. No list of forwarder
// names exists anywhere in this repo, and adding one here would be the thing that goes stale
// the first time somebody renames a skill without telling this file.
//
// What it asserts, per forwarder:
//   - the TARGET exists as a real skill directory, and is not itself a forwarder (no chains --
//     a forwarder to a forwarder still resolves today, but it resolves through a skill that is
//     already scheduled for deletion, so it breaks on a date nobody is tracking);
//   - the body invokes `skill:<target>` and nothing else -- exactly one distinct `skill:` ref;
//   - every `/skill-name` the body mentions is either the forwarder or its target, which is
//     what catches the copy-paste that edits four of the five names;
//   - a NOTICE line exists, and it names the forwarder as the deprecated one and the target as
//     the replacement -- not the other way round, and not a third skill;
//   - the directory carries nothing but SKILL.md and customize.toml. A forwarder that grows
//     payload has stopped being a forwarder, and payload is the road to `assets/module.yaml`,
//     which is precisely how 3.1.7 shipped a module home that was a lottery (rule 11);
//   - the rename version and the removal version agree between the frontmatter and the body.
//
// And the one that makes forwarders finite: THE REMOVAL VERSION MUST STILL BE IN THE FUTURE.
// A forwarder promises "removed in 4.0.0" and nothing makes that true; `postbump` writes the
// new version into package.json, so the release that reaches 4.0.0 turns every such promise
// into a failing gate and the forwarders get deleted instead of accumulating forever. That is
// the only clause here that fires on a tree nobody edited.
//
// What it does NOT reach: a forwarder written without the `DEPRECATED forwarder for /<target>`
// description shape is invisible to this rule -- it is the handle the scope is derived from.
// That is a false negative, and it is the honest trade against a hand-kept list. Check 21 in
// check-docs.mjs separately asserts every SKILL.md frontmatter parses and that `name:` equals
// the directory, so those are not re-checked here.
const FORWARDER_RE = /^DEPRECATED forwarder for \/([a-z0-9-]+)/;
const FORWARDER_ALLOWED_FILES = new Set(["SKILL.md", "customize.toml"]);

// The frontmatter block of a SKILL.md as an object, or null when there is not one. Tolerant by
// design: check-docs.mjs check 21 is what fails a SKILL.md whose frontmatter does not parse,
// and a rule that also threw there would report the same defect twice in different words.
function parseSkillFrontmatter(text) {
  if (!text.startsWith("---\n")) return null;
  const end = text.indexOf("\n---", 3);
  if (end === -1) return null;
  try {
    const doc = YAML.parse(text.slice(4, end + 1));
    return doc && typeof doc === "object" && !Array.isArray(doc) ? doc : null;
  } catch {
    return null;
  }
}

// Every `v?N.N.N` following `renamed ... in` / `removed in`, normalised without the `v`.
function versionsAfter(text, verb) {
  const re = new RegExp(`${verb}[^.\\n]*?\\bin v?(\\d+\\.\\d+\\.\\d+)`, "g");
  return [...text.matchAll(re)].map((m) => m[1]);
}

// Index of `/name` in `line` as a whole skill reference, or -1. Whole-reference matching
// matters because one skill name can be a prefix of another (`/l3io-sync` inside
// `/l3io-sync-status`), and a bare indexOf would report the longer one as the shorter.
function slashRefIndex(line, name) {
  const re = new RegExp(`/${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![a-z0-9-])`);
  return line.search(re);
}

function comparableVersion(v) {
  return v.split(".").map((n) => Number(n));
}

// a < b
function versionLess(a, b) {
  const [x, y] = [comparableVersion(a), comparableVersion(b)];
  for (let i = 0; i < 3; i++) {
    if (x[i] !== y[i]) return x[i] < y[i];
  }
  return false;
}

function checkForwarderShape(skills) {
  // Pass 1: which skills are forwarders, and what does each claim as its target? Collected
  // first because the no-chains clause needs to ask whether a TARGET is itself a forwarder.
  const forwarders = new Map(); // skill -> { rel, text, description, target }
  for (const skill of skills) {
    const rel = `skills/${skill}/SKILL.md`;
    if (!exists(rel)) continue;
    const text = read(rel);
    const fm = parseSkillFrontmatter(text);
    const description = fieldText(fm?.description).trim();
    const m = FORWARDER_RE.exec(description);
    if (!m) continue;
    // Everything after the closing `---`, so the frontmatter's own mention of the target is
    // not mistaken for the body making the same claim -- they are two separate assertions.
    const close = text.indexOf("\n---", 3);
    const body = close === -1 ? text : text.slice(close + 4);
    forwarders.set(skill, { rel, body, description, target: m[1] });
  }
  if (forwarders.size === 0) return;

  const skillSet = new Set(skills);
  let packageVersion = "";
  try {
    packageVersion = fieldText(JSON.parse(read("package.json"))?.version).trim();
  } catch {
    packageVersion = ""; // Reported by check:version; not this rule's business to duplicate.
  }

  for (const [skill, fwd] of forwarders) {
    const { rel, body, description, target } = fwd;

    if (!skillSet.has(target)) {
      failures.push(
        `${rel}: forwards to '/${target}', which is not a skill directory under skills/. ` +
        `A forwarder whose target does not exist fails only when a user invokes the old name.`
      );
      continue;
    }
    if (forwarders.has(target)) {
      failures.push(
        `${rel}: forwards to '/${target}', which is itself a DEPRECATED forwarder ` +
        `(to '/${forwarders.get(target).target}'). Forward to the real skill instead -- a chain ` +
        `breaks when the middle link reaches its own removal version.`
      );
    }

    // Exactly one `skill:` invocation, and it is the target.
    const invoked = [...new Set([...body.matchAll(/\bskill:([a-z0-9-]+)/g)].map((m) => m[1]))];
    if (invoked.length !== 1 || invoked[0] !== target) {
      failures.push(
        `${rel}: declares itself a forwarder to '/${target}' but its body invokes ` +
        `${invoked.length === 0 ? "no skill at all" : invoked.map((s) => `skill:${s}`).join(", ")}. ` +
        `A forwarder must invoke exactly skill:${target} -- this is the edit a copied forwarder misses.`
      );
    }

    // Every /skill-name the body mentions is the forwarder itself or its target. Restricted to
    // names that are real skill directories, so a path or URL fragment cannot false-positive.
    const mentioned = [...new Set([...body.matchAll(/\/([a-z0-9-]+)/g)].map((m) => m[1]))]
      .filter((n) => skillSet.has(n) && n !== skill && n !== target);
    if (mentioned.length > 0) {
      failures.push(
        `${rel}: names ${mentioned.map((n) => `'/${n}'`).join(", ")}, which is neither this ` +
        `forwarder nor its target '/${target}'. A forwarder's body is a claim about exactly two ` +
        `skills; a third one in it means a copied file was not fully edited.`
      );
    }

    // The NOTICE line: present, naming both skills, AND pointing the right way round. Presence
    // alone is not enough -- a notice with the two names swapped tells the user to migrate TO
    // the name that is going away, which is worse than no notice at all, and it contains both
    // names so any presence-only test passes it.
    const notice = body.split("\n").find((l) => l.includes("NOTICE:"));
    const at = (line, name) => slashRefIndex(line, name);
    if (!notice) {
      failures.push(
        `${rel}: has no NOTICE: line. The deprecation notice is the only signal a user of the ` +
        `old name gets that it is going away.`
      );
    } else if (at(notice, skill) === -1 || at(notice, target) === -1) {
      failures.push(
        `${rel}: its NOTICE line does not name both '/${skill}' (deprecated) and '/${target}' ` +
        `(the replacement): ${notice.trim()}`
      );
    } else if (at(notice, skill) > at(notice, target)) {
      failures.push(
        `${rel}: its NOTICE line names '/${target}' before '/${skill}', which reads as the ` +
        `replacement being deprecated in favour of the old name -- the two are swapped: ` +
        `${notice.trim()}`
      );
    }

    // Nothing but SKILL.md and customize.toml.
    const entries = fs.readdirSync(path.join(repoRoot, "skills", skill));
    const extra = entries.filter((e) => !FORWARDER_ALLOWED_FILES.has(e)).sort();
    if (extra.length > 0) {
      failures.push(
        `${rel.replace(/\/SKILL\.md$/, "")}: a forwarder carries only SKILL.md and ` +
        `customize.toml, but this one also has ${extra.join(", ")}. Payload on a forwarder is ` +
        `how a second module home appears (see rule 11) -- move it to skills/${target}/.`
      );
    }

    // Rename and removal versions agree between the frontmatter and the body.
    for (const [verb, label] of [["renamed", "rename"], ["removed", "removal"]]) {
      const found = [...new Set([...versionsAfter(description, verb), ...versionsAfter(body, verb)])];
      if (found.length === 0) {
        failures.push(`${rel}: states no ${label} version. A forwarder must say when it ${verb === "renamed" ? "replaced the old name" : "goes away"}.`);
      } else if (found.length > 1) {
        failures.push(
          `${rel}: gives ${found.length} different ${label} versions (${found.join(", ")}). ` +
          `The frontmatter and the body must agree.`
        );
      } else if (verb === "removed" && packageVersion && !versionLess(packageVersion, found[0])) {
        failures.push(
          `${rel}: promises removal in ${found[0]}, but this package is already at ` +
          `${packageVersion}. The promise came due -- delete skills/${skill}/ and its entry in ` +
          `.claude-plugin/marketplace.json, or move the removal version out.`
        );
      }
    }
  }
}

// ---------------------------------------------------------------------------
const skills = listSkillDirs();
checkRequiredFields(skills);
const byCode = collectModuleYamlByCode(skills);
checkDiscoveryLayout(byCode, skills);
checkOneHomePerCode(byCode);
checkModuleHomes(byCode, skills);
checkPmStatusSingleton(byCode, skills);
checkCsvSkillsExist(skills);
checkHelpRegistration(skills);
checkAgentRoster(byCode, skills);
checkSetupSingleton(byCode, skills);
checkMenuCodeUnique(skills);
checkForwarderShape(skills);
const strategyReport = checkPluginResolverStrategy();

if (verbose) {
  console.log(`  skills: ${skills.length}, module codes discovered: ${byCode.size}`);
  for (const line of strategyReport) console.log(line);
}

// One buffered write, then `process.exitCode` -- never a console.error loop and never
// `process.exit()`. See scripts/write-all-sync.mjs for why, and for the measured line counts at
// which the loop starts losing findings.
if (failures.length > 0) {
  writeAllSync(2,
    `\n${failures.length} module structure problem(s):\n\n` +
    failures.map((f) => `  ✗ ${f}\n\n`).join("") +
    "These are the structural facts the module layout must hold. Fix the tree, not this check.\n");
  process.exitCode = 1;
} else {
  console.log("Module structure checks passed: one module.yaml per module, correctly homed.");
}
