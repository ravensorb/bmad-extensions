# CLAUDE.md — `scripts/`

Build, sync and release tooling for the package. Loads when working under `scripts/`.

The prohibitions themselves — never edit per-skill payload copies, never bundle a BMad core
script, never hand-edit a manifest, never move `pm-status.py`'s version backwards — live in the
root `CLAUDE.md`. This file carries the mechanics behind them.

Each checker's own header comment is the authoritative description of what it asserts;
`scripts/check-docs.mjs` numbers its seventeen checks there.

## Payload manifests

Each skill also carries a **generated** `skills/<skill>/payload-manifest.json` — a SHA-256 per
payload file, keyed relative to that skill's own root so a consumer who installed one skill can
verify that skill alone. It is written by `scripts/write-payload-manifest.mjs`, whose scope is
*imported* from `sync-shared-scripts.mjs` rather than re-listed. **Never hand-edit a manifest,
and regenerate it whenever a payload file changes** — `npm run sync:scripts` does not do it for
you. Generation alone gates nothing: the manifests were generated once, later commits edited a
payload file, and HEAD shipped a manifest asserting a hash the file no longer had, which is
worse than no checksum because it reads as a guarantee. `npm run check:manifest` is now the gate,
in CI and in `prerelease`, and `postbump` regenerates after the payload re-sync (the bump rewrites
version strings inside payload files, so every hash moves).

## Sync and verify

```bash
npm run sync:scripts    # regenerate payload copies from skills/_shared/ source
npm run check:scripts   # verify payload copies match source (CI also runs this)
npm run check:docs      # verify docs match the code they describe (CI + release gate)
npm run check:manifest  # verify per-skill payload-manifest.json matches the payload (CI + release gate)
node scripts/write-payload-manifest.mjs   # regenerate the manifests after editing a payload file
```

## Release

The `postbump` hook auto-syncs the new version into `.claude-plugin/marketplace.json` and all `module.yaml` files — do not manually bump those files.

> **Release gate**: a `prerelease` hook refuses to release when payload copies have drifted from `skills/_shared/` or a `payload-manifest.json` is stale (runs `sync-shared-scripts.mjs --check` and `write-payload-manifest.mjs --check` for every `release:*` alias, not just `release`). `postbump` now stages with `git add -A skills/` so newly added skill files are included rather than silently dropped.
