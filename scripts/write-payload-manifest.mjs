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
//
// Usage:
//   node scripts/write-payload-manifest.mjs            # regenerate every per-skill manifest
//   node scripts/write-payload-manifest.mjs --check    # verify; nonzero exit on drift (CI)
//
// --check exists because generation alone gates nothing: the manifests were generated once,
// three commits later a payload file was edited, and nothing regenerated them -- so HEAD
// shipped a manifest asserting a hash the file no longer had. A checksum nobody verifies is
// worse than no checksum, because it reads as a guarantee. It mirrors
// sync-shared-scripts.mjs --check: same flag, same exit code, same remedy line.
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { PAYLOAD_TARGETS } from "./sync-shared-scripts.mjs";

const check = process.argv.includes("--check");
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
let drift = 0;
for (const [skill, files] of [...bySkill.entries()].sort(([a], [b]) => a.localeCompare(b))) {
  for (const relPath of Object.keys(files)) {
    const abs = path.join(root, "skills", skill, relPath);
    files[relPath] = createHash("sha256").update(fs.readFileSync(abs)).digest("hex");
  }
  const manifestRel = `skills/${skill}/payload-manifest.json`;
  const manifestPath = path.join(root, manifestRel);
  // Compare (and write) the whole rendered document, not just the hash map: the `version`
  // field drifts too, and byte-comparing what would be written is the only comparison that
  // cannot miss a field this script starts emitting later.
  const rendered =
    JSON.stringify({ version, generated_from: "skills/_shared/", files }, null, 2) + "\n";
  const count = Object.keys(files).length;
  totalFiles += count;

  if (check) {
    const onDisk = fs.existsSync(manifestPath) ? fs.readFileSync(manifestPath, "utf8") : null;
    if (onDisk === rendered) continue;
    drift += 1;
    if (onDisk === null) {
      console.error(`MISSING: ${manifestRel} has never been generated`);
      continue;
    }
    // Name the files whose recorded hash is wrong -- "the manifest differs" sends a reader
    // diffing JSON by hand, and the whole point of the manifest is naming the file.
    let recorded = {};
    try {
      recorded = JSON.parse(onDisk).files || {};
    } catch {
      console.error(`MALFORMED: ${manifestRel} is not valid JSON`);
      continue;
    }
    for (const [relPath, hash] of Object.entries(files)) {
      if (recorded[relPath] !== hash) {
        console.error(`STALE: ${manifestRel} -> ${relPath} (recorded ${recorded[relPath] ?? "nothing"}, actual ${hash})`);
      }
    }
    for (const relPath of Object.keys(recorded)) {
      if (!(relPath in files)) console.error(`STALE: ${manifestRel} -> ${relPath} is no longer a payload file`);
    }
    const recordedVersion = (() => { try { return JSON.parse(onDisk).version; } catch { return undefined; } })();
    if (recordedVersion !== version) {
      console.error(`STALE: ${manifestRel} records version ${recordedVersion}, package.json is at ${version}`);
    }
    continue;
  }

  fs.writeFileSync(manifestPath, rendered);
  console.log(`${manifestRel}: ${count} file(s) at ${version}`);
}

if (check) {
  if (drift > 0) {
    console.error(`\n${drift} payload manifest(s) stale — run: node scripts/write-payload-manifest.mjs`);
    process.exit(1);
  }
  console.log(`Payload manifests are current: ${bySkill.size} skill(s), ${totalFiles} file(s) at ${version}.`);
} else {
  console.log(`payload manifests: ${bySkill.size} skill(s), ${totalFiles} file(s) total at ${version}`);
}
