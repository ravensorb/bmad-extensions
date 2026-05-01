# bmad-extensions

AI-assisted development workflow extensions for sprint and epic execution with built-in quality gates. Structured as a [BMad community module](https://docs.bmad-method.org/how-to/install-custom-modules/) with adapters for Cursor and GitHub Copilot.

## Workflows

| Skill | What it does |
|-------|-------------|
| `bmad-sprint-execute` | Full sprint: story prep → dev → code review → QA → fix loop per story, then retrospective → adversarial review → red team at closure. Sprint does not close until all Critical/High issues resolved. |
| `bmad-epic-execute` | Full epic: runs sprint(s), then epic-level retrospective → adversarial → red team → architecture drift analysis → functional completeness review. |
| `bmad-red-team` | Security and resilience review from four adversarial perspectives: external attacker, malicious insider, chaos engineer, abusive legitimate user. |

## Install

### Claude Code (BMad) — recommended

```bash
npx bmad-method install \
  --custom-source https://github.com/ravensorb/bmad-extensions \
  --tools claude-code
```

Or interactively: `npx bmad-method install` → Community modules → bmad-extensions

Slash commands (`/bmad-sprint-execute`, `/bmad-epic-execute`, `/bmad-red-team`) are available immediately after install.

### Cursor

Slash commands are available automatically — no install step needed. To also get ambient rules that apply to every Cursor session, copy the `.mdc` files into your project:

```bash
cp adapters/cursor/rules/*.mdc /path/to/repo/.cursor/rules/
```

### GitHub Copilot

Append the relevant file(s) from `adapters/copilot/instructions/` to your repo's `.github/copilot-instructions.md`.

## Repo layout

```
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

## Dependencies

Requires these BMad skills to be installed (part of standard BMad bmm module):
`bmad-create-story`, `bmad-dev-story`, `bmad-code-review`, `bmad-qa-generate-e2e-tests`, `bmad-retrospective`, `bmad-review-adversarial-general`
