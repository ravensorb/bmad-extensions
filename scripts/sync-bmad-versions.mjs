#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const repoRoot = process.cwd();
const packageJsonPath = path.join(repoRoot, "package.json");
const marketplacePath = path.join(repoRoot, ".claude-plugin", "marketplace.json");
const manifestPath = path.join(repoRoot, "_bmad", "_config", "manifest.yaml");
const moduleName = "bmad-extensions";

const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, "utf8"));
const releaseVersion = packageJson.version;

const marketplace = JSON.parse(fs.readFileSync(marketplacePath, "utf8"));
const plugin = (marketplace.plugins || []).find((entry) => entry.name === moduleName);
if (!plugin) {
  throw new Error(`Could not find plugin ${moduleName} in ${marketplacePath}`);
}
plugin.version = releaseVersion;
fs.writeFileSync(marketplacePath, `${JSON.stringify(marketplace, null, 2)}\n`, "utf8");

const manifestRaw = fs.readFileSync(manifestPath, "utf8");
const manifestPattern = /(-\s+name:\s+bmad-extensions[\s\S]*?\n\s+version:\s*)([0-9]+\.[0-9]+\.[0-9]+)/;
if (!manifestPattern.test(manifestRaw)) {
  throw new Error(`Could not find module version for ${moduleName} in ${manifestPath}`);
}
const manifestUpdated = manifestRaw.replace(manifestPattern, `$1${releaseVersion}`);
fs.writeFileSync(manifestPath, manifestUpdated, "utf8");

console.log(`Synced BMAD module versions to ${releaseVersion}`);

