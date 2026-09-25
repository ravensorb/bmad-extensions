module.exports = {
  tagPrefix: "",
  commitAll: true,
  scripts: {
    // Hard gate: refuse to release when payload copies have drifted from
    // skills/_shared/. Drift means a shared source was edited without running
    // `npm run sync:scripts` — releasing would ship mismatched copies.
    // write-payload-manifest.mjs --check is here for the same reason: a manifest whose
    // recorded hash no longer matches the file it names is a checksum that reads as a
    // guarantee and is not one. It ran green at HEAD for three commits while stale.
    // `npm ls --package-lock-only` is here because the lock file drifted for three
    // releases without anyone noticing: package.json gained csv-parse/mvdan-sh/smol-toml
    // and bumped yaml, package-lock.json was never regenerated, and every CI run since
    // 2.5.2 failed at `npm ci` before a single gate step ran — silent red main for a
    // week. Refusing to cut a release without the lock in sync closes that class.
    prerelease: "node scripts/sync-shared-scripts.mjs --check && node scripts/write-payload-manifest.mjs --check && node scripts/check-docs.mjs && node scripts/check-pm-status-version.mjs && npm ls --package-lock-only --all --depth=0 >/dev/null",
    // After the bump, payloads legitimately re-sync (version strings are embedded),
    // so regenerate and stage. `-A` (not `-u`) so NEW skill files are included.
    // Manifests are regenerated AFTER the payload re-sync and BEFORE staging: the bump
    // rewrites version strings inside payload files, so every hash moves and the manifest's
    // own `version` field with them. Skipping this leaves prerelease failing on the NEXT
    // release, over drift the bump itself introduced.
    postbump: "node scripts/sync-bmad-versions.mjs && node scripts/sync-shared-scripts.mjs && node scripts/write-payload-manifest.mjs && git add -A skills/ .claude-plugin/ && git add -u"
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

