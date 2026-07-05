#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

const repoRoot = process.cwd();
const packageJsonPath = path.join(repoRoot, "package.json");
const marketplacePath = path.join(repoRoot, ".claude-plugin", "marketplace.json");
const srcRoot = path.join(repoRoot, "src");

const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, "utf8"));
const releaseVersion = packageJson.version;

// Update every plugin entry in marketplace.json to the release version
const marketplace = JSON.parse(fs.readFileSync(marketplacePath, "utf8"));
if (!Array.isArray(marketplace.plugins) || marketplace.plugins.length === 0) {
  throw new Error(`No plugins found in ${marketplacePath}`);
}
for (const plugin of marketplace.plugins) {
  plugin.version = releaseVersion;
}
fs.writeFileSync(marketplacePath, `${JSON.stringify(marketplace, null, 2)}\n`, "utf8");

console.log(`Synced marketplace plugin versions to ${releaseVersion}`);

// Stamp `module_version:` in every src/**/module.yaml so the installer-facing
// module metadata never drifts from package.json. Covers both the
// installer-discovery copies (src/<module>/module.yaml) and the per-skill
// copies (src/<module>/<skill>/module.yaml). Files changed here are staged so
// they land in the release commit created by commit-and-tag-version.
function findModuleYaml(dir) {
  const found = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) found.push(...findModuleYaml(full));
    else if (entry.name === "module.yaml") found.push(full);
  }
  return found;
}

let stamped = 0;
for (const file of fs.existsSync(srcRoot) ? findModuleYaml(srcRoot) : []) {
  const original = fs.readFileSync(file, "utf8");
  const updated = original.replace(/^(module_version:\s*).*$/m, `$1${releaseVersion}`);
  if (updated !== original) {
    fs.writeFileSync(file, updated, "utf8");
    execFileSync("git", ["add", file], { cwd: repoRoot, stdio: "ignore" });
    stamped += 1;
  }
}

console.log(`Stamped module_version to ${releaseVersion} in ${stamped} module.yaml file(s)`);
