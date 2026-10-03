# CLAUDE.md — `scripts/`

Build, sync and release tooling for the package. Loads when working under `scripts/`.

The prohibitions themselves — never edit per-skill payload copies, never bundle a BMad core
script, never hand-edit a manifest, never move `pm-status.py`'s version backwards — live in the
root `CLAUDE.md`. This file carries the mechanics behind them.

Each checker's own header comment is the authoritative description of what it asserts;
`scripts/check-docs.mjs` numbers its thirty-two checks there.

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
`skills/l3io-setup/` is named `*-setup` and carries both module files; the other three reach
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

**Having a row is not the same as having a reachable one.** Rule 9 asks whether a keyword HAS a
row; rule 7 asks whether a row's `skill` names a real directory. Both compare a row to something
*outside* the file, so neither could see two rows claiming one `menu-code` — the selector a user
types at BMad's menu — which is what shipped in 3.1.3 when `/l3io-help catalog` was given `LPC`,
already held by `/l3io-sync sync`. `check:module` rule 12 compares rows to each other, within
one CSV, case-insensitively. Cross-module reuse is deliberately out of scope: each module
assembles its own menu, and nothing measured says those collide.

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

**`smoke:install` now cleans up after itself, and only after itself.** The script took its
workdir from `work="${1:-$(mktemp -d)}"` and never removed it: eleven full BMad installs,
85 MB, leaked into a tmpfs `/tmp` where every byte is resident RAM. It also broke a rule this
package publishes — `standards-shell.md` requires the `trap` on the line after `mktemp` — in
the only shell script the repo ships.

Two properties the trap deliberately keeps:

- **A workdir passed as `$1` is never removed.** It belongs to the caller; deleting it would
  be the over-broad delete that has already cost this estate a file.
- **A FAILING run keeps its tree** and prints the path. A smoke test that deletes the evidence
  at the moment you need it is hostile to the debugging it exists for. Cleanup happens on
  exit 0 only.

**A gate reports through `writeAllSync`, never `console.error`.** `console.log`/`console.error`
are asynchronous when the stream is a pipe — which is how CI and every suite here run these
scripts — and bytes still queued when `process.exit()` fires are discarded with no error
anywhere. `check-docs.mjs` shipped that for its whole life: a correct "231 documentation
problem(s)" header over 142 delivered findings, in 10 of 20 runs, intact 8/8 through a shell
pipeline, so it only ever truncated where nobody was reading. The trigger is the **number of
queued writes, not the payload size** — a single 128 KB write is intact 20/20, while a
`console.error` loop starts losing findings around 300 lines and delivers as little as 3% at
5000. `scripts/write-all-sync.mjs` has the measured curve. Two rules, both load-bearing:
assemble the whole report as one string and write it through the helper, and set
`process.exitCode` rather than calling `process.exit()`. Where a script genuinely must
terminate — `check-module-view.mjs`'s `die()`, whose callers use it as control flow — the exit
is fine *after* a completed `writeAllSync`, because nothing is left queued.
`scripts/tests/write-all-sync.test.mjs` enforces this, scope derived rather than listed, since
the file that needs the rule is the next one somebody writes.

**That scope is the union of two derivations, and needs to be.** Every `scripts/check-*.mjs`,
*plus* every `scripts/*.mjs` a `check:`/`test:` npm script invokes. A glob over filenames alone
missed two live gates for as long as the rule existed: `check:manifest` is
`write-payload-manifest.mjs` and `check:scripts` is `sync-shared-scripts.mjs`, both of which
report one finding per file in a loop and then exit — the manifest one emits a `STALE:` line
per drifted payload file across 8 skills, which after any `skills/_shared/steps/**` edit is
well past the 300-line onset. The npm side alone would equally have missed
`check-module-view.mjs`, which `smoke-install.sh` invokes rather than npm. Both halves are
anchored separately, not just the union, because a union stays plausibly sized while one of its
derivations has quietly gone to zero.

The banned set is `console.error`, `console.warn`, and the stream API `process.stdout.write` /
`process.stderr.write` — the last of these is the same asynchronous writer under a spelling
that reads deliberate enough to look exempt. **`console.log` is deliberately not banned**: a
success line on a path that falls through to normal shutdown is flushed by the event loop
running to completion, so the hazard is the exit, not the writer. Calling `writeAllSync` once
per line is also fine — the rule is "never queue", not "write once" — and the two mutating
scripts do exactly that, so a run that throws partway still shows what it had already written.

**There is a THIRD failure shape, and the framing above does not reach it.** Everything to this
point measures the class by how much is queued. Misordering is not about quantity at all.
`run-python-suites.mjs` wrote its `=== <suite>` header and then spawned the suite with
`stdio: 'inherit'`: the child writes that fd *directly* while the parent's write is still
queued, so the header can land **after** the output it labels. Nothing is lost — it is
**misattributed**, which is worse, because a truncated report looks wrong and a mislabelled one
looks fine and gets acted on. A 20-byte header carries exactly the same exposure as a 20 KB
one, so no size threshold and no measured curve predicts it. The rule that does cover it is the
narrow one: **never hand an inherited fd to a child with your own write still queued on it.**
That header call is already on `writeAllSync` and says why at the call site; what was missing
was this paragraph. Raised by the downstream package after both our trees had documented
the class purely in terms of queue depth, which is the frame this case escapes.

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

**`check-docs.test.mjs`'s fixture is a *runnable* copy of the repo, and that is load-bearing.**
Check 24 derives its scope by spawning the *checked tree's own* `sync-shared-scripts.mjs
--dump-deliveries`, so the fixture needs this repo's devDependencies resolvable from it — it
symlinks `node_modules` rather than copying it. Without that link the fixture can only run a
script whose every import is a node builtin, which `sync-shared-scripts.mjs` happens to satisfy
today and is exactly the kind of thing that stops being true here, since the table above is a
standing instruction to reach for a library. The adopter package hit it when its sync script
acquired a `yaml` import: `ERR_MODULE_NOT_FOUND` surfaced as `check 24 cannot derive its scope`
across ~90 simultaneous failures, and no message anywhere named `node_modules`. A canary test
plants a library import into the copy and asserts the checker still runs, because a suite that
is green either way proves nothing about the property.

These are **devDependencies**. Nothing here ships: payload scope is `skills/<skill>/` (derived
from `PAYLOAD_TARGETS`), and `node_modules/` is gitignored, so `check:manifest` cannot see them.
Every bare import in a gate script **is** mechanically asserted against `package.json` —
`check-docs.mjs`'s check 28 (`gateImportsDeclared()`, invoked from the check runner), the
follow-up ADR-0007 named. Its scope is derived: every `.mjs` under `scripts/`, recursively,
with `node:` builtins and relative paths excluded and a subpath resolved to its package
(`csv-parse/sync` -> `csv-parse`). This paragraph asserted the opposite until 2026-10-03,
which is the costlier direction of the §3 failure: a doc that claims a guard exists sends a
reader to look and they find nothing, while a doc that claims none exists tells them not to
look. It had already diverged from the root `CLAUDE.md`, which described check 28 correctly.

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
**sync-delivered** payload file, keyed relative to that skill's own root. It is written by
`scripts/write-payload-manifest.mjs`, whose scope is *imported* from `sync-shared-scripts.mjs`
rather than re-listed. **Never hand-edit a manifest, and regenerate it whenever a payload file
changes** — `npm run sync:scripts` does not do it for you.

**Read that scope literally: it is what a sync group delivers, not what a skill ships.** A file
is hashed only if some sync group copies it here from `skills/_shared/`. Skill-owned payload —
authored in the skill, never synced — is **not** in any manifest. Measured 2026-09-30: **69 of
166 shipped files are hashed; 97 are not.** That includes every skill's own `SKILL.md`, all
seventeen of `l3io-doctor`'s `steps/` files and eleven of its `scripts/` (the whole migration
engine and its five readers), and eighteen of `l3io-sec-redteam`'s twenty-three. `pm-status.py`
and `spec-align.py` *are* hashed, in the same directory as those eleven, because they are synced
— same skill, same install, opposite coverage, and a consumer cannot tell which is which.

So this is a **sync-drift detector, and it is complete for that job.** It is not a
consumer-verification artifact, and must not be described as one: an earlier version of this
paragraph said a consumer "can verify that skill alone," which was false for `l3io-doctor` and
`l3io-help` the whole time it was written down. Derived-beats-listed was the right principle
aimed at the wrong question — the scope was derived from *what gets synced*, and what gets
synced is not what gets shipped.

Note the failure mode before trusting a green run: this omission **reads as a guarantee**, the
same way the stale hash below did. `check:manifest` prints `Payload manifests are current: 8
skill(s), 69 file(s)` over an edit to a skill-owned file it cannot see, and regenerating produces
no diff — which looks like confirmation that the change was covered. It was not. Widening the
writer to every shipped file is a small change; deciding whether the manifest should be a
verification artifact is not, and it would make `check:manifest` fail on every skill-owned edit
until regenerated. That decision is open, and is not this paragraph's to make. Generation alone gates nothing: the manifests were generated once, later commits edited a
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
