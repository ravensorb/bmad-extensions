# ADR-0007: CI installs npm dependencies, so the check tooling uses parsers instead of writing them

## Status

Accepted — 2026-09-21.

## Context

`.github/workflows/checks.yml` ran no `npm install`, `npm ci`, or equivalent. `package.json`
declared two devDependencies, both release tooling that no gate invokes, and every gate was a
bare `node scripts/<x>.mjs` whose complete import set was `node:` built-ins plus one relative
import. The six-gate suite therefore passed because it was, by unwritten convention, entirely
dependency-free. Nothing stated that and nothing checked it.

That unstated constraint had a cost, and the cost was paid in hand-written parsers. Four of
them existed in `scripts/`, and the code said so outright at `check-module.mjs:195`: *"this
repo has no npm dependency and CI never runs `npm install` before these checks … so a real CSV
library is not reachable here without also wiring up a package install step."*

- `check-module.mjs` `parseModuleYaml()` — a YAML subset read with a per-line `key: value`
  regex and a hand-written block-scalar rule.
- `check-module.mjs` `splitCsvLine()` — a CSV field splitter, written during a fix round after
  a first attempt reached for a CSV package and reverted.
- `check-docs.mjs` check 17 — `COMMAND_SPLIT_RE = /&&|;|\||&/` standing in for a shell lexer,
  plus a line-at-a-time read of a YAML workflow file. Four fix rounds hardened it and each
  round's review found the next hole: the split was quote-unaware, the exemption could not see
  through `$( )`, and correct commands (`timeout`, `env`, `if`-blocks, quoted YAML scalars,
  `uv  run` with two spaces) were reported red.
- `check-docs.mjs` check 21 — correct, but paying a `uv run` subprocess to borrow `ruamel.yaml`
  because no in-process YAML parser was reachable.

The constraint was also not applied uniformly, which is the test global rule 2 asks for: the
Python half of the same repo depends on `ruamel.yaml`, `pyyaml`, `markdown-it-py` and others
through `uv`, and four CI steps already install them. The one gate that could not have a
dependency was the gate policing the ones that do.

The real hazard of the old arrangement was never a silent failure — `node` exits non-zero on
`ERR_MODULE_NOT_FOUND`. It was the *local-passes / CI-fails* divergence: a developer with
`node_modules/` present sees six green gates and finds out on push.

## Decision

1. `.github/workflows/checks.yml` runs `npm ci` immediately after the toolchain setup steps and
   before every gate. `actions/setup-node@v4` was already there and `package-lock.json` was
   already committed, so this is one step plus `cache: npm`.
2. Check-tooling libraries are **devDependencies only**. Nothing here ships: the install unit is
   `skills/<skill>/`, `payload-manifest.json` scope is derived from `PAYLOAD_TARGETS` (all of
   which are under `skills/<skill>/`), and `node_modules/` is gitignored. `check:manifest`
   cannot see these and does not.
3. The four hand-rolled parsers are replaced:
   `yaml` for `module.yaml` and for SKILL.md frontmatter, `csv-parse` for `module-help.csv`,
   and `mvdan-sh` (the JS build of mvdan/sh) plus `yaml` for check 17's workflow scan.
4. Check 17's rule is expressed over **argv**, not over text: a command that names a python3-ish
   interpreter and hands it a `.py` path or a `{pm_status}`/`{spec_align}` token must be a
   `uv run` carrying a provisioning flag. Quoting, `$( )`, `if`/`then`, `VAR=value`, heredocs,
   backslash continuations and block scalars stop being this repo's problem.

## `mvdan-sh` is deprecated on npm, and is still the right choice today

Stated here because `npm ci` prints the warning and the `package-lock.json` entry this change
added carries it, so the next reader will meet the fact whether or not this ADR admits it:

```
node_modules/mvdan-sh  "deprecated": "See https://github.com/mvdan/sh/issues/1145"
```

`mvdan-sh@0.10.1` is the GopherJS build of mvdan/sh, BSD-3-Clause. It was **published
2022-05-08** — the registry's `time.modified` of 2025-04-10 is when the deprecation was
recorded, not a release, and reading it as one understated the package's age by three years.
The named successor is **`sh-syntax`** — a WASM build of the *same* mvdan/sh parser, MIT,
actively released (0.6.0, 2026-07).

**Why the successor was not taken:** `sh-syntax` is **async-only**. Its API returns promises
because the WASM module must be instantiated before the first parse, and it exposes no
synchronous entry point. `scripts/check-docs.mjs` is synchronous end to end — twenty-one checks
called as bare statements, each pushing into a shared `failures` array that is inspected at
module top level to choose the exit code. Adopting `sh-syntax` means making check 17 async,
which means making the invocation list async, which means restructuring the exit path of a file
whose whole job is to be a reliable gate. Its AST is also shaped differently (a JSON projection
rather than the Go node objects `syntax.Walk` yields), so the rule would be rewritten, not
ported. That is a disproportionate change to buy a maintenance label on a devDependency that
never ships and whose parse behaviour is frozen and correct.

**The deprecation is this section's premise, not a revisit trigger.** None of the three triggers
below has fired as of 2026-09-22: `check-docs.mjs` is still synchronous, all six gates pass on
Node 24, and `npm audit` reports zero advisories. A deprecated package that still parses shell
correctly on a supported runtime is a maintenance risk to *watch*, not a decision to reopen.

**Revisit if** any of these becomes true:

- `check-docs.mjs` becomes asynchronous for some other reason — then the cost of `sh-syntax`
  collapses to a port of the rule, and it should be taken.
- `mvdan-sh` stops working on a Node version this repo supports (`engines.node >= 22`), or its
  transpiled output breaks on a Node release. There is no upstream to fix it.
- A security advisory is filed against it. Deprecated is not unmaintained-and-vulnerable, but it
  does mean nobody will ship the fix.

Until one of those happens, the alternative to `mvdan-sh` is not `sh-syntax`; it is going back to
hand-writing a substitution scanner, an assignment-prefix stripper, a reserved-word list, a
newline splitter and a backslash-continuation joiner, which is what this ADR exists to stop.

## Consequences

- A check script may now use a maintained library. That is the point: it stops the next
  hand-rolled parser before it is written, which is what global rule 1 asks for.
- CI costs one install (~10–20s, cached) and a lockfile that must stay current. `npm ci` fails
  loudly when `package.json` and `package-lock.json` disagree, so drift is caught rather than
  tolerated.
- An undeclared import in a gate script is now a real failure mode. It is not guarded
  mechanically yet: the suggested follow-up (derive every import across `scripts/**.mjs` and
  assert each is `node:`-prefixed, relative, or present in `package.json`) is **not**
  implemented, and this sentence is the record that it is not.
- Check 21 no longer spawns a subprocess and now parses with the same `yaml` package BMad's own
  installer uses, so it agrees with the thing it predicts instead of approximating it. Its old
  `uv`-missing fail-closed branch is replaced by something stronger: the parser is a top-level
  `import`, so a broken `node_modules` stops the whole gate rather than one check.
- Check 21 now parses with the same `yaml` package and the same field predicates as BMad's own
  `manifest-generator.js` (`require('yaml')`, `yaml.parse()`, `^2.7.0` against this repo's
  `^2.9.1` — same major), so it agrees with the thing it predicts rather than approximating it.
- Revisit if: the install becomes a meaningful share of CI time, a dependency introduces a
  supply-chain review burden the maintainer does not want for build tooling, or any of the
  three `mvdan-sh` triggers in the section above fires. **None of those three has fired yet.**
  What is true today is the deprecation itself, which is why that section exists — but a
  deprecation notice is a standing condition to watch, not an event that reopens the decision.
