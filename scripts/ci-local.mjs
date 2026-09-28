#!/usr/bin/env node
// Thin wrapper: `npm run ci:local` invokes act against the checks workflow with
// sensible defaults. Requires: act on PATH (nektos/act >=0.2.88), Docker daemon
// running. Prints act's stdout/stderr and exits with act's exit code.
//
// First-time setup: seed the local image cache by running act once without
// --pull=false, or manually: docker pull catthehacker/ubuntu:act-latest
//
// Known limitation: act's catthehacker/ubuntu:act-latest image lacks `uv`,
// so the "check-pm-status.py unit tests" step will fail locally. On GitHub's
// ubuntu-latest runners, `uv` is pre-installed and that step passes. Use
// -P ubuntu-latest=catthehacker/ubuntu:full-latest for a closer match (but
// note the full image is ~17 GB — the medium image is sufficient for most steps).
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const args = [
    "push",
    "-W", ".github/workflows/checks.yml",
    "--pull=false",  // reuse local image cache; run act --pull once manually to seed
];
const extra = process.argv.slice(2);
const result = spawnSync("act", args.concat(extra), {
    cwd: repoRoot,
    stdio: "inherit",
});
process.exit(result.status ?? 1);
