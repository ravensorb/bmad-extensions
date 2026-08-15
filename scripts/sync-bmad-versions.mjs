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
