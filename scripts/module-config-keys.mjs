#!/usr/bin/env node
// Print the module config surface this package declares, derived from the module.yaml files
// themselves -- never from a hand-kept list.
//
// Why this exists: scripts/smoke-install.sh has to assert that a REAL install's
// `_bmad/config.toml` files every module's installer answers under that module's OWN code.
// The set of (code, key) pairs to expect is stated once, in each module's
// `skills/*/assets/module.yaml`: the `code:` field, plus every top-level key whose value is a
// mapping carrying a `prompt:` -- BMad's own rule for "this is an install-time question"
// (tools/installer/core/manifest-generator.js, writeCentralConfig: `'prompt' in value`).
// Enumerating those pairs in the smoke script instead would be exactly the hand-kept scope
// CLAUDE.md rule 4 forbids: it would keep passing over a set that no longer contains the
// module whose attribution broke.
//
// module.yaml is YAML, so it is read with the `yaml` package -- the same rule (and the same
// scar tissue) that removed the hand-written subset parser from check-module.mjs.
//
// Usage:
//   node scripts/module-config-keys.mjs             # "<code> <key>" per declared setting
//   node scripts/module-config-keys.mjs --codes     # "<code>" per module, one line each
//   node scripts/module-config-keys.mjs --root DIR  # read DIR/skills instead of cwd/skills
import fs from "node:fs";
import path from "node:path";
import YAML from "yaml";

const argv = process.argv.slice(2);
const rootIdx = argv.indexOf("--root");
const repoRoot = path.resolve(rootIdx === -1 ? process.cwd() : argv[rootIdx + 1]);
const codesOnly = argv.includes("--codes");

const skillsDir = path.join(repoRoot, "skills");
if (!fs.existsSync(skillsDir)) {
  console.error(`module-config-keys: no skills/ directory under ${repoRoot}`);
  process.exit(1);
}

const codes = [];
const settings = [];

for (const entry of fs.readdirSync(skillsDir, { withFileTypes: true })) {
  if (!entry.isDirectory() || entry.name === "_shared") continue;
  const rel = path.join("skills", entry.name, "assets", "module.yaml");
  const abs = path.join(repoRoot, rel);
  if (!fs.existsSync(abs)) continue;

  let doc;
  try {
    doc = YAML.parse(fs.readFileSync(abs, "utf8"));
  } catch (e) {
    console.error(`module-config-keys: ${rel} is not valid YAML (${String(e.message).split("\n")[0]})`);
    process.exit(1);
  }
  if (!doc || typeof doc !== "object" || Array.isArray(doc)) continue;

  const code = typeof doc.code === "string" ? doc.code.trim() : "";
  if (!code) continue; // check:module rule 2 reports a module.yaml with no code
  codes.push(code);

  for (const [key, value] of Object.entries(doc)) {
    if (value && typeof value === "object" && !Array.isArray(value) && "prompt" in value) {
      settings.push(`${code} ${key}`);
    }
  }
}

const lines = codesOnly ? codes.sort() : settings.sort();
if (lines.length > 0) console.log(lines.join("\n"));
