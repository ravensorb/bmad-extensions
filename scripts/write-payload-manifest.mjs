#!/usr/bin/env node
// Emit a checksum manifest for every file sync-shared-scripts.mjs writes.
//
// The scope is IMPORTED from the sync script, never re-listed here. A second
// hand-kept list would drift from the first, and this file's whole purpose is
// to detect drift -- a drifting drift-detector reports success over the wrong set.
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { PAYLOAD_TARGETS } from "./sync-shared-scripts.mjs";

const root = path.resolve(import.meta.dirname, "..");
const version = JSON.parse(fs.readFileSync(path.join(root, "package.json"))).version;

const files = {};
for (const target of PAYLOAD_TARGETS) {
  const abs = path.join(root, target);
  files[target] = createHash("sha256").update(fs.readFileSync(abs)).digest("hex");
}

fs.writeFileSync(
  path.join(root, "payload-manifest.json"),
  JSON.stringify({ version, generated_from: "skills/_shared/", files }, null, 2) + "\n",
);
console.log(`payload-manifest.json: ${Object.keys(files).length} file(s) at ${version}`);
