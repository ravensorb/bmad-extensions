# Module Setup

Standalone module self-registration. This file is loaded when:
- The user passes `setup`, `configure`, or `install` as an argument
- The module is not yet registered in `{project-root}/_bmad/config.yaml`
- The skill's first-run check detects a fresh installation

## Overview

Registers the l3io-pm module into a project. Reads module identity from `module.yaml`. Collects user preferences and writes them to three files:

- **`{project-root}/_bmad/config.yaml`** — shared project config: core settings at root plus an `l3io-pm` section. User-only keys (`user_name`, `communication_language`) are **never** written here.
- **`{project-root}/_bmad/config.user.yaml`** — personal settings (gitignored): `user_name`, `communication_language`.
- **`{project-root}/_bmad/module-help.csv`** — registers module capabilities for the help system.

`{project-root}` is a **literal token** in config values — never substitute it with an actual path.

## Check Existing Config

1. Read `module.yaml` for module metadata (use the `code` field as the module identifier).
2. Check `{project-root}/_bmad/config.yaml` — if an `l3io-pm` section already exists, inform the user this is a reconfiguration.

If the user passes inline values or `accept all defaults`, map any values provided, use defaults for the rest, and skip interactive prompting.

## Collect Configuration

Show defaults in brackets. Present all prompts together so the user can respond once.

**Core Config** (collect only if not already present in `config.yaml` or `config.user.yaml`):
- `user_name` (default: `BMad`) — written to `config.user.yaml` only
- Language (default: `English`) — sets both `communication_language` (user only) and `document_output_language` (shared)
- `output_folder` (default: `{project-root}/_bmad-output`) — written to `config.yaml` root

**Module Config** (always collect):
- `implementation_artifacts` (default: `{project-root}/_bmad-output/implementation-artifacts`) — absolute path to dev-facing artifacts
- `planning_artifacts` (default: `{project-root}/_bmad-output/planning-artifacts`) — absolute path to plan outputs

## Write Files

Write a temp JSON file with collected answers. Run both scripts in parallel:

```bash
python3 scripts/merge-config.py \
  --config-path "{project-root}/_bmad/config.yaml" \
  --user-config-path "{project-root}/_bmad/config.user.yaml" \
  --module-yaml module.yaml \
  --answers {temp-file}

python3 scripts/merge-help-csv.py \
  --target "{project-root}/_bmad/module-help.csv" \
  --source assets/module-help.csv \
  --module-code l3io-pm
```

## Create State Directory

After config is written, create the state directory:

```bash
mkdir -p "{project-root}/_bmad/state/active"
```

## Confirm

Show a summary of all values written, then output:

```
✅ l3io-pm module registered. Run /l3io-pm-plan to build your execution plan.
```
