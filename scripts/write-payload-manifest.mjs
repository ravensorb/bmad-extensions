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
// THE SCOPE IS WHAT SHIPS, not what is synced. BMad's installer copies the whole skill
// directory (`_copyResolvedSkills` -> `copyModuleWithFiltering`, which filters only shim and
// `-sidecar` directories), so every file under skills/<skill>/ lands on a consumer's disk and
// every one of them is ours.
//
// This used to import PAYLOAD_TARGETS from the sync script, which made the scope "files that
// arrived here by being synced from _shared/". That was true of all payload once, and then
// skill-local files appeared -- SKILL.md, customize.toml, skill-local steps/ and scripts/ --
// and were invisible to it. 123 shipped files went unhashed; the manifest covered 38% of what
// ships. The consequence was not academic: clean-payload.py derives its delete set from this
// manifest and treats anything absent as "not ours. Not touched, not mentioned", so
// /l3io-doctor uninstall silently left behind migrate-engine.py, sync-state.py, every reorg
// script -- and clean-payload.py itself, the file whose own docstring calls this manifest "the
// answer to which files are ours".
//
// How a file got here is not the question the manifest answers. Deriving from the directory
// means a new skill-local file is covered the moment it exists, with nothing to remember.
//
// A skill is a directory with a SKILL.md. That excludes skills/_shared/, which is the
// canonical source tree and ships nothing.
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
import { writeAllSync } from "./write-all-sync.mjs";

const check = process.argv.includes("--check");
const root = path.resolve(import.meta.dirname, "..");
const version = JSON.parse(fs.readFileSync(path.join(root, "package.json"))).version;

// Excluded from the scope, each for its own reason:
//
//   payload-manifest.json  a file cannot contain its own hash.
//   tests/                 never shipped as payload (root CLAUDE.md). No shipped skill has
//                          one today -- suites live in tests/<skill>/ at the repo root -- so
//                          this is a guard against a future one, not a live filter.
//   __pycache__/           build detritus from importing a script, already gitignored.
const EXCLUDED_DIRS = new Set(["tests", "__pycache__"]);
const EXCLUDED_FILES = new Set(["payload-manifest.json"]);

function walkSkill(skillDir, rel = "") {
  const out = [];
  for (const entry of fs.readdirSync(path.join(skillDir, rel), { withFileTypes: true })) {
    const childRel = rel ? `${rel}/${entry.name}` : entry.name;
    if (entry.isDirectory()) {
      if (EXCLUDED_DIRS.has(entry.name)) continue;
      out.push(...walkSkill(skillDir, childRel));
    } else if (entry.isFile()) {
      if (!rel && EXCLUDED_FILES.has(entry.name)) continue;
      out.push(childRel);
    }
    // Anything else (symlink, socket, fifo) is not payload we can hash meaningfully.
  }
  return out;
}

const bySkill = new Map();
const skillsDir = path.join(root, "skills");
for (const entry of fs.readdirSync(skillsDir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
  if (!entry.isDirectory()) continue;
  const skillDir = path.join(skillsDir, entry.name);
  // A skill is a directory with a SKILL.md. That is what BMad installs and what the
  // marketplace declares; it excludes skills/_shared/, the canonical source tree, which
  // ships nothing and carries the test suites.
  if (!fs.existsSync(path.join(skillDir, "SKILL.md"))) continue;
  const files = {};
  for (const relPath of walkSkill(skillDir).sort()) files[relPath] = null; // hashed below
  bySkill.set(entry.name, files);
}

let totalFiles = 0;
let drift = 0;
let missing = 0;
const report = [];
for (const [skill, files] of [...bySkill.entries()].sort(([a], [b]) => a.localeCompare(b))) {
  // Task 11A fix round 1, L-2: a manifest-listed payload file that is missing on disk (e.g.
  // deleted by hand, or a sync group narrowed without a matching `git rm`) used to crash this
  // whole process with a raw Node ENOENT stack trace -- exit non-zero either way, so CI was
  // never unsafe, but the operator saw a crash instead of a diagnosis naming the missing path.
  // Skip a missing file here (in both --check and generation mode) and let the loop below
  // report it by name instead of throwing.
  let skillHasMissingFile = false;
  for (const relPath of Object.keys(files)) {
    const abs = path.join(root, "skills", skill, relPath);
    if (!fs.existsSync(abs)) {
      report.push(`MISSING FILE: skills/${skill}/${relPath} is listed as a payload target but does not exist on disk`);
      missing += 1;
      skillHasMissingFile = true;
      continue;
    }
    files[relPath] = createHash("sha256").update(fs.readFileSync(abs)).digest("hex");
  }
  if (skillHasMissingFile) continue;
  const manifestRel = `skills/${skill}/payload-manifest.json`;
  const manifestPath = path.join(root, manifestRel);
  // Compare (and write) the whole rendered document, not just the hash map: the `version`
  // field drifts too, and byte-comparing what would be written is the only comparison that
  // cannot miss a field this script starts emitting later.
  const rendered =
    JSON.stringify({ version, generated_from: "skills/<skill>/", files }, null, 2) + "\n";
  const count = Object.keys(files).length;
  totalFiles += count;

  if (check) {
    const onDisk = fs.existsSync(manifestPath) ? fs.readFileSync(manifestPath, "utf8") : null;
    if (onDisk === rendered) continue;
    drift += 1;
    if (onDisk === null) {
      report.push(`MISSING: ${manifestRel} has never been generated`);
      continue;
    }
    // Name the files whose recorded hash is wrong -- "the manifest differs" sends a reader
    // diffing JSON by hand, and the whole point of the manifest is naming the file.
    let recorded = {};
    try {
      recorded = JSON.parse(onDisk).files || {};
    } catch {
      report.push(`MALFORMED: ${manifestRel} is not valid JSON`);
      continue;
    }
    for (const [relPath, hash] of Object.entries(files)) {
      if (recorded[relPath] !== hash) {
        report.push(`STALE: ${manifestRel} -> ${relPath} (recorded ${recorded[relPath] ?? "nothing"}, actual ${hash})`);
      }
    }
    for (const relPath of Object.keys(recorded)) {
      if (!(relPath in files)) report.push(`STALE: ${manifestRel} -> ${relPath} is no longer a payload file`);
    }
    const recordedVersion = (() => { try { return JSON.parse(onDisk).version; } catch { return undefined; } })();
    if (recordedVersion !== version) {
      report.push(`STALE: ${manifestRel} records version ${recordedVersion}, package.json is at ${version}`);
    }
    continue;
  }

  fs.writeFileSync(manifestPath, rendered);
  // Written as it happens: this arm has already written the manifest above it, so a buffer
  // flushed at the end would lose the record of what changed on a run that throws partway.
  writeAllSync(1, `${manifestRel}: ${count} file(s) at ${version}\n`);
}

if (missing > 0) {
  report.push(`\n${missing} payload file(s) listed as a target but missing on disk — fix ` +
    `the tree (restore the file, or remove it if it should no longer ship), then ` +
    `re-run.`);
  writeAllSync(2, report.join("\n") + "\n");
  process.exit(1);
}

if (check) {
  if (drift > 0) {
    report.push(`\n${drift} payload manifest(s) stale — run: node scripts/write-payload-manifest.mjs`);
    writeAllSync(2, report.join("\n") + "\n");
    process.exit(1);
  }
  writeAllSync(1, `Payload manifests are current: ${bySkill.size} skill(s), ${totalFiles} file(s) at ${version}.\n`);
} else {
  writeAllSync(1, `payload manifests: ${bySkill.size} skill(s), ${totalFiles} file(s) total at ${version}\n`);
}
