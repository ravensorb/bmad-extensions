---
name: l3io-pm-sync
description: Bidirectional sync between l3io-pm state and GitHub Issues. Modes: setup, push, pull, sync, status (default).
---

# l3io-pm-sync

Communicate all responses in `{communication_language}`.

## Conventions

- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives).
- `{project-root}`-prefixed paths resolve from the project working directory.

## On Activation

Run: `python3 {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow`

If the script fails, read `{skill-root}/customize.toml` directly.

If `{project-root}/_bmad/config.yaml` does not have an `l3io-pm` section, load
`{skill-root}/assets/module-setup.md` first.

## Execution

Parse the invocation argument to determine mode:

| Argument | Mode | Description |
|---|---|---|
| (none) or `status` | `status` | Show sync state and drift report |
| `setup` | `setup` | Configure sync platform (GitHub), create sync-mapping.yaml |
| `push` | `push` | Push l3io-pm state to external work items |
| `pull` | `pull` | Pull external status updates into l3io-pm state |
| `sync` | `sync` | Bidirectional sync (push then pull) |

Bind `{sync_mode}` = parsed mode.

Load and execute in order:

```
{skill-root}/steps/shared/step-00-activate.md
{skill-root}/steps/sync/step-02-detect-platform.md
{skill-root}/steps/sync/step-03-operations.md
{skill-root}/steps/sync/step-04-resolve.md
```
