---
name: bmad-migrate-artifacts
description: Migrate existing flat BMAD artifact outputs into the zero-padded epic/sprint folder layout. Use when enabling the new epic-XX/sprint-YY artifact structure in an existing project.
---

# Artifact Layout Migration

## Goal
Migrate legacy flat files in implementation and planning artifacts into the new folder structure:
- `epic-{EE}/sprint-{SS}/stories/{story-key}.md`
- `epic-{EE}/sprint-{SS}/closure/...`
- `epic-{EE}/sprint-{SS}/tests/...`
- `epic-{EE}/epic-closure/...`
- `epic-{EE}/tests/...`
- `planning_artifacts/epic-{EE}/...`

`EE` and `SS` must be zero-padded two-digit values (`01`, `02`, etc.).

## Safety Rules
- Run a dry run first and show a migration plan before changing files.
- Never overwrite an existing destination file.
- If a destination exists, keep source in place and record a conflict.
- Preserve file contents exactly; this is a move-only migration.

## Inputs
Load config from `{project-root}/_bmad/bmm/config.yaml` and resolve:
- `implementation_artifacts`
- `planning_artifacts`
- `output_folder`

If `implementation_artifacts` is unavailable, default to:
`{output_folder}/implementation-artifacts`

## Migration Heuristics
1. Story files in flat root:
   - Pattern: `{implementation_artifacts}/{story-key}.md`
   - Story key regex: `^([0-9]+)-[0-9]+.*\.md$`
   - Epic number = first capture group
   - Destination sprint = `01` unless user provides a mapping
   - Move to: `{implementation_artifacts}/epic-{EE}/sprint-{SS}/stories/{story-key}.md`

2. Sprint closure files in flat root:
   - Patterns include sprint retro/review files (for example, `epic-*-sprint-*-retro-*.md`, `sprint-adversarial-*.md`, `sprint-redteam-*.md`)
   - If epic number can be inferred, move to:
     `{implementation_artifacts}/epic-{EE}/sprint-{SS}/closure/{filename}`
   - Default sprint = `01` unless user mapping provided

3. Epic closure files in flat root:
   - Patterns: `epic-*-arch-drift-*.md`, `epic-*-functional-completeness-*.md`, epic retros explicitly marked epic-level
   - Move to:
     `{implementation_artifacts}/epic-{EE}/epic-closure/{filename}`

4. Test evidence files in flat root:
   - Patterns include `*qa*.md`, `*test*.md`, `*verification*.md`
   - Sprint-scoped test evidence → `{implementation_artifacts}/epic-{EE}/sprint-{SS}/tests/{filename}`
   - Epic-level test evidence → `{implementation_artifacts}/epic-{EE}/tests/{filename}`

5. Planning artifacts:
   - If planning files are in a flat planning root and epic number can be inferred, move to:
     `{planning_artifacts}/epic-{EE}/{filename}`
   - Sprint-scoped planning files should move to:
     `{planning_artifacts}/epic-{EE}/sprint-{SS}/{filename}`

6. Unknown files:
   - Leave in place
   - Record as "unclassified" for user review

## Execution Sequence
1. Scan and classify files
2. Print dry-run migration table:
   - source path
   - destination path
   - classification
   - status: move/conflict/unclassified
3. Ask for confirmation
4. Create required destination directories
5. Execute moves
6. Print summary report

## Required Last Output
```
DONE — Moved: N, Conflicts: N, Unclassified: N, Root: [implementation_artifacts]
```

