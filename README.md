# bmad-extensions

AI-assisted development workflow extensions for sprint and epic execution with built-in quality gates. Structured as a [BMad community module](https://docs.bmad-method.org/how-to/install-custom-modules/) with adapters for Cursor and GitHub Copilot.

## Workflows

| Skill | What it does |
| ----- | ------------ |
| `bmad-sprint-execute` | Full sprint: story prep → dev → code review → QA → fix loop per story, then retrospective → adversarial review → red team at closure. Sprint does not close until all Critical/High issues resolved. |
| `bmad-epic-execute` | Full epic: runs sprint(s), then epic-level retrospective → adversarial → red team → architecture drift analysis → functional completeness review. |
| `bmad-red-team` | Security and resilience review from four adversarial perspectives: external attacker, malicious insider, chaos engineer, abusive legitimate user. |
| `bmad-migrate-artifacts` | One-time migration utility for existing projects: reorganizes legacy flat artifact files into `epic-XX/sprint-YY` folders (with dry-run first). |

## Install

### Claude Code (BMad) — recommended

```bash
npx bmad-method install \
  --directory . \
  --custom-source https://github.com/ravensorb/bmad-extensions \
  --tools claude-code \
  --yes
```

Or interactively: `npx bmad-method install` → Community modules → bmad-extensions

Slash commands (`/bmad-sprint-execute`, `/bmad-epic-execute`, `/bmad-red-team`, `/bmad-migrate-artifacts`) are available immediately after install.
Use `/bmad-migrate-artifacts` once in existing projects before running the updated orchestrators.

### Cursor

Slash commands are available automatically — no install step needed.

Copying `.mdc` files is optional and only needed if you want ambient/project-level Cursor rules.

Quick enable for the current repo:

```bash
mkdir -p .cursor/rules && cp adapters/cursor/rules/*.mdc .cursor/rules/
```

### GitHub Copilot

Copilot reads `.github/copilot-instructions.md`.

Quick setup for the current repo:

```bash
mkdir -p .github && touch .github/copilot-instructions.md && for f in adapters/copilot/instructions/*.md; do b="$(basename "$f" .md)"; marker="<!-- BMAD:${b}:START -->"; rg -qF "$marker" .github/copilot-instructions.md || { printf "\n%s\n" "$marker" >> .github/copilot-instructions.md; cat "$f" >> .github/copilot-instructions.md; printf "\n<!-- BMAD:%s:END -->\n" "$b" >> .github/copilot-instructions.md; }; done
```

This command is idempotent:

- appends BMAD snippets from `adapters/copilot/instructions/*.md` only if not already present
- preserves unrelated custom content in `.github/copilot-instructions.md`

Alternative (path-specific instructions structure):

```bash
mkdir -p .github/instructions && cp adapters/copilot/instructions/*.md .github/instructions/
```

If you use this alternative, rename copied files to `*.instructions.md` and add `applyTo` frontmatter in each file so Copilot can apply them by path.

### Codex

No manual copy step is required for Codex when BMAD is already installed in the repo.

## Releases and Changelog (Node Standard)

This repo supports a standard Conventional Commits release flow with `commit-and-tag-version`.

Install release tooling:

```bash
npm install
```

Common commands:

- patch release + changelog + tag:
  - `npm run release:patch`
- minor release + changelog + tag:
  - `npm run release:minor`
- major release + changelog + tag:
  - `npm run release:major`
- regenerate changelog only:
  - `npm run changelog`

This flow uses repo config in `.versionrc.cjs` and also bumps:

- `.claude-plugin/marketplace.json` plugin version
- `_bmad/_config/manifest.yaml` `bmad-extensions` module version

## Repo layout

```text
bmad-sprint-execute/     # BMad skill — sprint orchestrator
bmad-epic-execute/       # BMad skill — epic orchestrator
bmad-red-team/           # BMad skill — adversarial security review
processes/               # Platform-agnostic process definitions (canonical source of truth)
adapters/cursor/         # Cursor ambient .mdc rule files
adapters/copilot/        # GitHub Copilot instruction snippets
_bmad/bmad-extensions/   # BMAD module registration (config, manifests, skill symlinks)
```

## Context boundary rule

All three workflows are designed around one core principle: **each unit of work runs with minimal context from previous units.** Fresh context = better focus, no context window exhaustion.

- **Claude Code**: enforced automatically — subagent delegation via `claude --print` or Agent tool
- **Cursor**: enforced manually — start a new Composer session for each story phase
- **Copilot**: enforced manually — start a new chat for each story phase

## Adaptive Parallelism

Execution defaults to sequential and only parallelizes when work is independent and safe.

- default parallel subagents: `2`
- user override allowed when it makes sense
- hard cap: `4`
- safety fallback: force sequential (`1`) when independence/state safety is unclear
- progress updates should include ETA ranges in separate status lines (announce + progress pattern)

## Artifact Conventions

Runtime artifacts are organized with zero-padded epic/sprint folders:

- implementation stories: `.../implementation-artifacts/epic-XX/sprint-YY/stories/`
- implementation closure: `.../implementation-artifacts/epic-XX/sprint-YY/closure/`
- implementation tests: `.../implementation-artifacts/epic-XX/sprint-YY/tests/` and `.../implementation-artifacts/epic-XX/tests/`
- planning artifacts: `.../planning-artifacts/epic-XX/` (and `sprint-YY/` when sprint-scoped)

## Dependencies

Requires these BMad skills to be installed (part of standard BMad bmm module):
`bmad-create-story`, `bmad-dev-story`, `bmad-code-review`, `bmad-qa-generate-e2e-tests`, `bmad-retrospective`, `bmad-review-adversarial-general`

## Changelog

See `CHANGELOG.md` for release history.
