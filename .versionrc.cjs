const MODULE_NAME = "bmad-extensions";

function readMarketplaceVersion(contents) {
  const parsed = JSON.parse(contents);
  const plugin = (parsed.plugins || []).find((p) => p.name === MODULE_NAME);
  if (!plugin || !plugin.version) {
    throw new Error(`Could not find plugin version for ${MODULE_NAME} in marketplace.json`);
  }
  return plugin.version;
}

function writeMarketplaceVersion(contents, version) {
  const parsed = JSON.parse(contents);
  const plugin = (parsed.plugins || []).find((p) => p.name === MODULE_NAME);
  if (!plugin) {
    throw new Error(`Could not find plugin entry for ${MODULE_NAME} in marketplace.json`);
  }
  plugin.version = version;
  return `${JSON.stringify(parsed, null, 2)}\n`;
}

function readManifestVersion(contents) {
  const match = contents.match(
    /-\s+name:\s+bmad-extensions[\s\S]*?\n\s+version:\s*([0-9]+\.[0-9]+\.[0-9]+)/
  );
  if (!match) {
    throw new Error("Could not find bmad-extensions version in manifest.yaml");
  }
  return match[1];
}

function writeManifestVersion(contents, version) {
  const pattern = /(-\s+name:\s+bmad-extensions[\s\S]*?\n\s+version:\s*)([0-9]+\.[0-9]+\.[0-9]+)/;
  if (!pattern.test(contents)) {
    throw new Error("Could not find bmad-extensions version in manifest.yaml");
  }
  return contents.replace(pattern, `$1${version}`);
}

module.exports = {
  tagPrefix: "v",
  commitAll: true,
  types: [
    { type: "feat", section: "Features" },
    { type: "fix", section: "Fixes" },
    { type: "perf", section: "Performance" },
    { type: "refactor", section: "Refactoring" },
    { type: "docs", section: "Documentation" },
    { type: "chore", section: "Maintenance" },
    { type: "test", section: "Testing" },
    { type: "ci", section: "CI/CD" }
  ],
  packageFiles: [
    { filename: "package.json", type: "json" },
    { filename: ".claude-plugin/marketplace.json", type: "marketplace-json" },
    { filename: "_bmad/_config/manifest.yaml", type: "bmad-manifest-yaml" }
  ],
  bumpFiles: [
    { filename: "package.json", type: "json" },
    { filename: ".claude-plugin/marketplace.json", type: "marketplace-json" },
    { filename: "_bmad/_config/manifest.yaml", type: "bmad-manifest-yaml" }
  ],
  updaters: {
    "marketplace-json": {
      readVersion: readMarketplaceVersion,
      writeVersion: writeMarketplaceVersion
    },
    "bmad-manifest-yaml": {
      readVersion: readManifestVersion,
      writeVersion: writeManifestVersion
    }
  }
};

