# CLAUDE.md — `scripts/`

Build, sync and release tooling for the package. Loads when working under `scripts/`.

The prohibitions themselves — never edit per-skill payload copies, never bundle a BMad core
script, never hand-edit a manifest, never move `pm-status.py`'s version backwards — live in the
root `CLAUDE.md`. This file carries the mechanics behind them.

Each checker's own header comment is the authoritative description of what it asserts;
`scripts/check-docs.mjs` numbers its twenty-six checks there.

**`module.yaml` lives in more than one place, on purpose.** BMad reads it with two different
tools that disagree about where it is: `validate-module.py` reads `assets/module.yaml`, and
`tools/installer/project-root.js` — the one that decides which `[modules.<code>]` a module's
settings land under — reads a **skill-root** `module.yaml` for any skill whose directory name
does not end in `-setup`. So a standalone module home carries both, byte-identical, and
`skills/module.yaml` is a marker declaring no `code:`/`name:`/`agents:`. `check:module` rule 1
enforces all of it; `docs/bmad-module-yaml-discovery.md` has the measured contract. Do not
"tidy up" the duplicate — a branch that did exactly that shipped an install whose
`_bmad/config.toml` BMad's own resolver refused to parse.

**A plugin's `skills` array decides whether its authored `module-help.csv` is used at all.**
BMad's `PluginResolver` tries five strategies per plugin in `.claude-plugin/marketplace.json`;
the fifth **synthesizes** a stub catalog from `SKILL.md` frontmatter and the install still exits
0, with no warning, ignoring every authored CSV. `l3io-pm` reaches strategy 2 only because
`skills/l3io-pm-setup/` is named `*-setup` and carries both module files; the other three reach
strategy 3 only because `_trySingleStandalone` requires **exactly one** existing skill. Adding a
second skill to any of those three plugins — nothing deleted, every file where it was — drops
that module to synthesis. `check:module` rule 8 mirrors the resolver's conditions and fails on
anything that would land on strategy 5; run it with `-v` to see the strategy it derived per
plugin.

**An agent is declared twice, and the two copies are read by different things.** A module's
`agents:` roster is what the installer writes into `_bmad/config.toml` as `[agents.<code>]`;
the skill's own `customize.toml` `[agent]` block is what it reads at activation. `check:module`
rule 10 requires them equal on `title`, `icon` and `description`, with `name` present on both
(empty is valid — a First-Breath agent fills it) — and checks the pair both ways, because a
`[agent]` block no roster lists never reaches `config.toml` at all while the skill still
activates. The entry is tied to its skill through the `[agent] code`, **not** the directory
name: `l3io-sec-redteam` declares `code: redteam`, which the installer uses only as the TOML
section key (`manifest-generator.js:608`). `skills/l3io-sec-redteam/assets/module.yaml` records
why beside the field.

**A mode keyword with no `module-help.csv` row is unreachable from BMad's menu.** The routing
table in a skill's `SKILL.md` and the module's CSV are two copies of the same fact, and they
drifted: the doctor advertised twenty-one modes and registered one. `check:module` rule 9
requires every keyword in a routing table to carry a row or to be marked excluded in that
table's own **Menu** column (`registered` · `default` · `health-check` · `not-a-capability`)
— the exclusion set is read from the table, never kept in the checker, and an unrecognized
value fails rather than quietly exempting a keyword. The expectation is anchored outside the
table too, so deleting a table fails instead of passing over an empty set: a top-level
`steps/<name>.md` that is not part of a numbered `step-NN-*.md` sequence is a mode, and a
skill with mode files (or a "Recognized keywords" section) owes a table.

**`smoke:install` judges the validator's findings, not its verdict.** `validate-module.py` does
not implement two conventions `bmad-help` documents and BMad's own modules ship — the `_meta`
documentation row, and cross-module `skill:action` relationships — so it returns `fail` for all
four of this package's modules, and for BMad's own `bmm` CSV when that is put in a shape it can
read. `scripts/smoke-install.sh` therefore pipes each run through
`scripts/check-module-view.mjs`, which exempts exactly those two classes, evidenced against the
module's own CSV, and fails on anything else — including a `medium`, which the validator's own
`status` tolerates, so the bar is stricter than the one it replaces. The script's header states
each exemption and the condition that switches it off; `scripts/tests/check-module-view.test.mjs`
attacks all of them and runs in CI, which `smoke:install` does not. ADR-0008 Decision 7's
2026-09-23 amendment has the measurements.

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
| `check-module.mjs` | `skills/module.yaml`, `skills/*/module.yaml`, `skills/*/assets/module.yaml` | `yaml` |
| `check-module.mjs` | `skills/*/assets/module-help.csv` | `csv-parse` |
| `check-module-view.mjs` | the assembled view's `<skill>/assets/module-help.csv` | `csv-parse` |
| `check-module.mjs` check 9 | each `skills/*/SKILL.md` routing table, split on `\|` | `csv-parse` |
| `check-module.mjs` check 10 | `skills/*/customize.toml` | `smol-toml` |
| `check-module.mjs` check 8 | `.claude-plugin/marketplace.json` | `JSON.parse` |
| `module-config-keys.mjs` | `skills/*/assets/module.yaml` | `yaml` |
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

### Action versions across `.github/workflows/*.yml`

`checks.yml` and `reviewdog.yml` keep every shared `uses:` on the same version — verify the
current major against the upstream repo before bumping either file, rather than assuming the
other workflow's pin is still current. Two pinning rules, and they differ because the publishers
differ:

- `actions/checkout`, `actions/setup-node`, `astral-sh/setup-uv` are pinned by major tag
  (`@v7`, `@v10.2.0` respectively) *only when the publisher maintains a rolling tag* for that
  major — check with `git ls-remote https://github.com/<owner>/<repo>.git refs/tags/vN` first.
  `astral-sh/setup-uv` does not carry one (no `v10` ref exists at all), so it is pinned to the
  exact release tag instead of a major, unlike its GitHub-first-party siblings.
- Anything else — third-party, or a first-party action without a maintained major tag — is
  pinned to an exact release tag, or a commit SHA if no tag exists. Never a branch float
  (`@master`/`@main`): `reviewdog/action-detect-secrets` ran `@master` in a secret-scanning job,
  meaning whatever landed on that branch ran unreviewed on this repo's PRs; it is now
  `@v0.31.0`, the action's own latest release tag.

`actions/setup-python` is intentionally absent from `checks.yml`: every Python entry point is a
PEP-723 script (`# requires-python = ">=3.11"` in its own header) invoked through `uv run`, and
`uv` provisions a matching interpreter itself — `astral-sh/setup-uv` is the only Python
toolchain step either workflow needs. Re-check this if a future script needs a system Python
`uv` cannot provision (e.g. one requiring OS packages only `apt`/`setup-python` install).

Both workflows are meant to run clean under `nektos/act` (`/usr/local/bin/act` locally) as well
as GitHub — run `act push -W .github/workflows/checks.yml` and `act pull_request -W
.github/workflows/reviewdog.yml` after touching either file. `reviewdog.yml`'s job posts a
review to a real pull request via the GitHub API using `github.token`; under `act` there is no
real PR to review, so that job is GitHub-only by design, not a local-parity gap — a clean `act`
run there proves the container starts and the action's inputs are well-formed, not that the
review gets posted.

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
npm run check:lock      # verify package.json and package-lock.json agree (CI + release gate)
node scripts/write-payload-manifest.mjs   # regenerate the manifests after editing a payload file
```

## Release

The `postbump` hook auto-syncs the new version into `.claude-plugin/marketplace.json` and all `module.yaml` files — do not manually bump those files.

> **Release gate**: a `prerelease` hook refuses to release when payload copies have drifted from `skills/_shared/`, a `payload-manifest.json` is stale, or `package-lock.json` no longer matches `package.json` (runs `sync-shared-scripts.mjs --check`, `write-payload-manifest.mjs --check`, `check-docs.mjs`, `check-pm-status-version.mjs`, and `npm ls --package-lock-only` for every `release:*` alias, not just `release`). `postbump` now stages with `git add -A skills/` so newly added skill files are included rather than silently dropped.

**Lock-drift is the same shape as manifest-drift, and it bit us the same way.** In 2026-09 the check-tooling devDependencies (`csv-parse`, `mvdan-sh`, `smol-toml`) were added to `package.json` and a `yaml` patch was bumped, but `package-lock.json` was never regenerated. CI's `npm ci` refused to install and every push from 2.5.2 through 3.0.1 died at that step — before any gate could run — so main was red for a week and nobody noticed until someone thought to look. `check:lock` runs `npm ls --package-lock-only --all --depth=0`, which is instantaneous, network-free, and prints `Missing: X from lock file` per drifted dep. It runs in CI as its own step *before* `npm ci` (so a red run names the drift cleanly rather than burying it under `npm ci`'s usage output) and in the release gate (so a release refuses to cut with drift, the same discipline as payload manifests). The class this closes is *the check is on CI and CI keeps dying before it reaches the check* — a green gate somewhere earlier that has to hold for the check to matter.
