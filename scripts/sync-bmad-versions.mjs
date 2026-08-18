#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const repoRoot = process.cwd();
const packageJsonPath = path.join(repoRoot, "package.json");
const marketplacePath = path.join(repoRoot, ".claude-plugin", "marketplace.json");

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

// Update pm-status.py's two version declarations to the release version.
//
// This is the whole reason the script's version line was merged into the release line: the
// marker used to be hand-maintained, and a hand-maintained invariant drifts. It did, twice
// -- ten commits changed the script under 2.3.0, then another changed it under 2.4.0 -- and
// self-install, which compared versions, kept reporting a stale copy as current. One project
// sat 920 lines behind under an identical number. Nobody has to remember this now.
//
// Runs before sync-shared-scripts.mjs in postbump, so the per-skill payload copies inherit
// the new version rather than drifting from _shared.
const pmStatusPath = path.join(repoRoot, "skills", "_shared", "pm-status.py");
{
  const before = fs.readFileSync(pmStatusPath, "utf8");
  const after = before
    .replace(/^(#\s*pm-status-version:\s*)[0-9.]+/m, `$1${releaseVersion}`)
    .replace(/^(PM_STATUS_VERSION\s*=\s*")[0-9.]+"/m, `$1${releaseVersion}"`);
  if (!/^#\s*pm-status-version:\s*[0-9.]+/m.test(after) ||
      !/^PM_STATUS_VERSION\s*=\s*"[0-9.]+"/m.test(after)) {
    throw new Error(`Could not rewrite both version declarations in ${pmStatusPath}`);
  }
  if (after !== before) {
    fs.writeFileSync(pmStatusPath, after, "utf8");
    console.log(`Synced pm-status.py version to ${releaseVersion}`);
  }
}

// Update module_version in all skills/*/module.yaml files
const skillsDir = path.join(repoRoot, "skills");
let moduleYamlCount = 0;
for (const skillName of fs.readdirSync(skillsDir)) {
  const moduleYamlPath = path.join(skillsDir, skillName, "module.yaml");
  if (!fs.existsSync(moduleYamlPath)) continue;
  const content = fs.readFileSync(moduleYamlPath, "utf8");
  const updated = content.replace(
    /^module_version:\s*.+$/m,
    `module_version: ${releaseVersion}`
  );
  if (updated !== content) {
    fs.writeFileSync(moduleYamlPath, updated, "utf8");
    console.log(`Synced module_version in skills/${skillName}/module.yaml to ${releaseVersion}`);
    moduleYamlCount++;
  }
}
if (moduleYamlCount === 0) {
  console.log("No module.yaml files needed version update");
}
