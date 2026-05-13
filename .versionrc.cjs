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
  ]
};

