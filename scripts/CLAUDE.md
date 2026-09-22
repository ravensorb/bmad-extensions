# CLAUDE.md — `scripts/`

Build, sync and release tooling for the package. Loads when working under `scripts/`.

The prohibitions themselves — never edit per-skill payload copies, never bundle a BMad core
script, never hand-edit a manifest, never move `pm-status.py`'s version backwards — live in the
root `CLAUDE.md`. This file carries the mechanics behind them.

Each checker's own header comment is the authoritative description of what it asserts;
`scripts/check-docs.mjs` numbers its twenty-two checks there.

## Dependencies

The checkers are **not** dependency-free, and have not been since
`docs/adr/0007-ci-installs-npm-dependencies.md`. `.github/workflows/checks.yml` runs `npm ci`
immediately after the toolchain setup steps and **before every gate**; a gate step added above
that install fails on `ERR_MODULE_NOT_FOUND`. Locally, run `npm ci` (or `npm install`) once
before `npm run check:*`.

Everything the checkers parse, they parse with a library — never a hand-written reader
(root `CLAUDE.md`, global rule 1, and this repo's own history with a hand-written YAML parser):

| Where | Parses | With |
|---|---|---|
| `check-module.mjs` | `skills/*/assets/module.yaml` | `yaml` |
| `check-module.mjs` | `skills/*/assets/module-help.csv` | `csv-parse` |
| `check-docs.mjs` check 17 | `.github/workflows/*.yml` and `*.yaml` | `yaml` |
| `check-docs.mjs` check 17 | each `run:` script, into argv | `mvdan-sh` |
| `check-docs.mjs` check 21 | `skills/*/SKILL.md` frontmatter | `yaml` (the package BMad's installer uses) |

`mvdan-sh` is **deprecated on npm** — `npm ci` says so, and the lockfile entry carries it. It is
still the right choice here and the ADR says why, which successor was considered (`sh-syntax`,
async-only against a synchronous `check-docs.mjs`) and what would make us switch. Do not reach
for it in new code without reading that section.

These are **devDependencies**. Nothing here ships: payload scope is `skills/<skill>/` (derived
from `PAYLOAD_TARGETS`), and `node_modules/` is gitignored, so `check:manifest` cannot see them.
Nothing mechanically asserts that a gate script's imports are declared in `package.json` — that
follow-up is named in the ADR and is not implemented.

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
