# ADR-0006: One declared BMad dependency inventory, guarded twice

## Status
Accepted — 2026-09-12

## Context
Three BMad releases changed skills this package dispatches, and nothing detected it.
`bmad-create-story` and `bmad-dev-story` were deprecated to shims (#2637, #2641),
`bmad-review-adversarial-general` merged into `bmad-review` (#2603, #2608), and
`bmad-check-implementation-readiness` was removed outright (#2659). A clean v6.12.0 install
therefore could not run the dev loop. Separately, every presence probe read
`.claude/commands/` while 6.12.0 installs to `.claude/skills/`, so an installed reviewer
looked absent and its gate silently self-skipped. Both were found only by installing BMad
by hand and looking.

## Decision
1. Every upstream `bmad-*` name this package references is declared in one inventory,
   `skills/l3io-util-doctor/assets/bmad-dependencies.json`, with its status and its fallback.
2. The inventory is **JSON**. This package has zero runtime node dependencies and
   `check-docs.mjs` imports only `node:fs`/`node:path`; no TOML or YAML parser is available to
   it, and library-first forbids hand-rolling one. `JSON.parse` is native to node and `json`
   is stdlib in Python, so both guards read it with no parsing code.
3. The runtime verifier is **skill-local** at `skills/l3io-util-doctor/scripts/bmad-deps.py`,
   because `l3io-util-doctor` is its only consumer. ADR-0001 places single-consumer code in
   its skill's own `scripts/`; this follows `audit-backlog.py` exactly, including a suite at
   `scripts/tests/` and one CI step. It gets no sync group and no `_shared/` copy.

## Consequences
Dependency truth is one file instead of prose in six `module.yaml` files and a dozen step
files. `check:docs` check 16 asserts the step files agree with it where no BMad install
exists; `bmad-deps.py` asserts a real install agrees with it. A future rename fails CI or
surfaces in `/l3io-util-doctor check-deps` instead of silently disabling a gate.

The inventory is hand-maintained against upstream, so it can lag a BMad release. It records
`verified_against` for exactly that reason: the claim is "checked at this version", not
"true forever".

## Amendment — 2026-09-20

ADR-0006 said correctly that bmad-create-story and bmad-dev-story "were deprecated to
shims". The inventory it governs encoded them as `removed`, and three of six removed
entries were wrong. A `deprecated` status now exists, and shipped-ness is derived from
`_bmad/_config/skill-manifest.csv` rather than asserted by hand. See ADR-0008 and
docs/superpowers/specs/2026-09-20-l3io-customization-layer-design.md.

Two details this amendment's own wording would otherwise leave stale. The check number in
*Consequences* above moved: the inventory check was 16 when this ADR was written, was 17 for
the span of one task, and is 16 again since `module-yaml-agreement` was retired — read
`scripts/check-docs.mjs`'s header for the current number rather than this sentence. And
Decision point 2's reasoning ("no TOML or YAML parser is available to it") no longer holds:
CI installs npm dependencies and the checkers parse with libraries (ADR-0007). The inventory
stays JSON, but now because JSON is the right shape for it, not because nothing else could
be read.
