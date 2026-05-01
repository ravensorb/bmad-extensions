# GitHub Copilot Adapter

Instruction snippets for sprint-execute, epic-execute, and red-team workflows.

## Install

Append the relevant file(s) to your repo's `.github/copilot-instructions.md`:

```bash
cat adapters/copilot/instructions/sprint-execute.md >> .github/copilot-instructions.md
cat adapters/copilot/instructions/red-team.md >> .github/copilot-instructions.md
```

Or copy just the sections you need.

## Limitations vs. Claude Code

Copilot does not support automatic subagent delegation. The **context boundary rule** must be enforced manually:

> Start a **new Copilot Chat session** for each story phase (create, dev, code-review, qa, fix) and each closure phase.

Pass only the story file path and a brief context note to each new chat — not the full history.

## Usage

Once added to `copilot-instructions.md`, Copilot will follow the workflows when you ask:
- "Run sprint-execute for Epic 15"
- "Red team this implementation"
- "Execute epic 15 end-to-end"

## State compatibility

These adapters use the same disk state contract as the Claude Code adapter. `sprint-status.yaml` and story files written in Copilot sessions are fully compatible with Claude Code and Cursor sessions.
