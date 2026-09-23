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
// introduced this file. The eight assertions:
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
//                            `skills/l3io-pm-setup/` is named `*-setup` and carries both
//                            files, and the other three reach strategy 3 only because
//                            `_trySingleStandalone` requires EXACTLY ONE existing skill --
//                            adding a second skill to any of their `skills` arrays, with
//                            nothing deleted, drops that module to synthesis.
//
// Scope for checks 1-7 is derived by walking `skills/` and for check 8 from
// `.claude-plugin/marketplace.json`'s own `plugins` array -- never from a hand-kept list of
// module codes, skill names or plugin names -- so a code or a plugin nobody told this script
// about is still found and checked. Check 8 must read the marketplace, not the filesystem:
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
// Parsing: `module.yaml` is read with the `yaml` package, `module-help.csv` with
// `csv-parse`, and `marketplace.json` with `JSON.parse`. The first two used to be
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
const skills = listSkillDirs();
checkRequiredFields(skills);
const byCode = collectModuleYamlByCode(skills);
checkDiscoveryLayout(byCode, skills);
checkOneHomePerCode(byCode);
checkModuleHomes(byCode, skills);
checkPmStatusSingleton(byCode, skills);
checkCsvSkillsExist(skills);
const strategyReport = checkPluginResolverStrategy();

if (verbose) {
  console.log(`  skills: ${skills.length}, module codes discovered: ${byCode.size}`);
  for (const line of strategyReport) console.log(line);
}

if (failures.length > 0) {
  console.error(`\n${failures.length} module structure problem(s):\n`);
  for (const f of failures) console.error(`  ✗ ${f}\n`);
  console.error("These are the structural facts the module layout must hold. Fix the tree, not this check.");
  process.exit(1);
}

console.log("Module structure checks passed: one module.yaml per module, correctly homed.");
