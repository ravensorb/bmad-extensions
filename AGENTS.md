# bmad-l3io-extensions

BMad community module package — four modules: `l3io-pm` (sprint/epic orchestration), `l3io-sec` (red team), `l3io-util` (housekeeping), `l3io-arch` (architecture review). Ships as installable Claude Code slash commands. Full developer reference in `CLAUDE.md`.

## Policy

- All commits require Conventional Commits format and a DCO sign-off (`git commit -s`).
- Never push to main without a PR.

## Where things are

- Canonical shared files: `skills/_shared/` — never edit per-skill copies in `scripts/`, `references/`, `assets/`, or `steps/`
- Per-skill payload copies are auto-generated — edit source, then run `npm run sync:scripts`
- Per-skill manifests: `skills/<skill>/payload-manifest.json` — never hand-edit; regenerate with `node scripts/write-payload-manifest.mjs`

## Running and verifying

- `npm run sync:scripts` — regenerate per-skill payload copies from `skills/_shared/`; does NOT regenerate manifests
- `node scripts/write-payload-manifest.mjs` — regenerate all `payload-manifest.json` files after any payload edit
- `npm run check:scripts` — verify payload copies match source (CI gate)
- `npm run check:manifest` — verify manifests match payload (CI gate and release gate)
- `npm run check:docs` — verify docs match the code they describe (CI gate and release gate)

## Conventions that differ from defaults

- `postbump` auto-syncs version strings and payload copies — do not manually bump `marketplace.json` or `module.yaml` files
- `prerelease` blocks a release when payload copies or manifests are stale — run `check:scripts` and `check:manifest` before releasing
- `l3io-util-doctor` modes live one-per-file in `steps/` — never inline a new mode into `SKILL.md`

## Known pitfalls

- `npm run sync:scripts` syncs payload copies but does not regenerate manifests — run `write-payload-manifest.mjs` separately after editing any payload file, or CI will fail on `check:manifest`
- Never bundle BMad core scripts (`resolve_config.py`, `resolve_customization.py`, `memlog.py`) — they are installed by BMad core at `{project-root}/_bmad/scripts/` and must be invoked from there
- Never add test files (`test-pm-status.py`, `test-write-module-config.py`) to skill payloads — they are dead payload; CI runs them from `skills/_shared/tests/` only
