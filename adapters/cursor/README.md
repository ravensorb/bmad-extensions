# Cursor Adapter

Cursor rule files (`.mdc`) for sprint-execute, epic-execute, and red-team workflows.

## Install

```bash
cp adapters/cursor/rules/*.mdc /path/to/repo/.cursor/rules/
```

## Limitations vs. Claude Code

Cursor does not support automatic subagent delegation. The **context boundary rule** must be enforced manually:

> Start a **new Composer session** for each story phase (create, dev, code-review, qa, fix) and each closure phase (retrospective, adversarial, red team).

Pass only the story file path and a brief context note to each new session — not the full history of prior stories.

## Usage

The rules are set to `alwaysApply: false`. To activate, either:
- Reference them explicitly: `@sprint-execute execute epic 15`
- Or ask Cursor to apply the relevant rule at the start of a new session

## State compatibility

These adapters use the same disk state contract as the Claude Code adapter. Sprint-status.yaml and story files written by Cursor sessions are fully compatible with Claude Code sessions and vice versa.
