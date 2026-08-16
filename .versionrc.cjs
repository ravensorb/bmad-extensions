module.exports = {
  tagPrefix: "",
  commitAll: true,
  scripts: {
    // Hard gate: refuse to release when payload copies have drifted from
    // skills/_shared/. Drift means a shared source was edited without running
    // `npm run sync:scripts` — releasing would ship mismatched copies.
    prerelease: "node scripts/sync-shared-scripts.mjs --check",
    // After the bump, payloads legitimately re-sync (version strings are embedded),
    // so regenerate and stage. `-A` (not `-u`) so NEW skill files are included.
    postbump: "node scripts/sync-bmad-versions.mjs && node scripts/sync-shared-scripts.mjs && git add -A skills/ .claude-plugin/ && git add -u"
  },
  types: [
    { type: "feat", section: "Features" },
    { type: "fix", section: "Fixes" },
    { type: "perf", section: "Performance" },
    { type: "refactor", section: "Refactoring" },
    { type: "docs", section: "Documentation" },
    { type: "chore", section: "Maintenance" },
    { type: "test", section: "Testing" },
    { type: "ci", section: "CI/CD" }
  ]
};

