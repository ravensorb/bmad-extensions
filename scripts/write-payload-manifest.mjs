#!/usr/bin/env node
// Emit a checksum manifest per skill for the files sync-shared-scripts.mjs writes into it.
//
// Why per-skill: the install unit is the named skill directory (skills/<skill>/) -- nothing
// at the repo root, and nothing outside a named skill directory, survives install. A single
// root-level manifest is unreachable by any consumer. A consumer who installed only one
// skill must be able to verify that skill alone, so each skill carries its own
// skills/<skill>/payload-manifest.json, keyed by paths relative to that skill's own root
// (a consumer's disk has no skills/<skill>/ prefix once the skill is installed).
//
// The scope is IMPORTED from the sync script, never re-listed here. A second hand-kept list
// would drift from the first, and this file's whole purpose is to detect drift -- a drifting
// drift-detector reports success over the wrong set.
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { PAYLOAD_TARGETS } from "./sync-shared-scripts.mjs";

const root = path.resolve(import.meta.dirname, "..");
const version = JSON.parse(fs.readFileSync(path.join(root, "package.json"))).version;

// Group repo-relative targets ("skills/<skill>/<rest>") by skill, keeping only the
// skill-relative remainder as the manifest key. A target that is not under skills/<skill>/
// can't belong to any per-skill manifest and is skipped -- PAYLOAD_TARGETS never produces
// one today, but this keeps the grouping honest rather than assuming the shape.
const bySkill = new Map();
for (const target of PAYLOAD_TARGETS) {
  const parts = target.split(path.sep);
  if (parts[0] !== "skills" || parts.length < 3) continue;
  const skill = parts[1];
  const relPath = parts.slice(2).join(path.sep);
  // Defensive: never let a manifest hash itself, even if a future sync group somehow
  // targeted this filename.
  if (relPath === "payload-manifest.json") continue;
  if (!bySkill.has(skill)) bySkill.set(skill, {});
  bySkill.get(skill)[relPath] = null; // placeholder; hashed below
}

let totalFiles = 0;
for (const [skill, files] of [...bySkill.entries()].sort(([a], [b]) => a.localeCompare(b))) {
  for (const relPath of Object.keys(files)) {
    const abs = path.join(root, "skills", skill, relPath);
    files[relPath] = createHash("sha256").update(fs.readFileSync(abs)).digest("hex");
  }
  const manifestPath = path.join(root, "skills", skill, "payload-manifest.json");
  fs.writeFileSync(
    manifestPath,
    JSON.stringify({ version, generated_from: "skills/_shared/", files }, null, 2) + "\n",
  );
  const count = Object.keys(files).length;
  totalFiles += count;
  console.log(`skills/${skill}/payload-manifest.json: ${count} file(s) at ${version}`);
}
console.log(`payload manifests: ${bySkill.size} skill(s), ${totalFiles} file(s) total at ${version}`);
