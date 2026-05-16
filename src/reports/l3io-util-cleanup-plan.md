---
title: 'LiquidLogicLabs Utilities Module Plan'
status: 'complete'
module_name: 'LiquidLogicLabs Utilities'
module_code: 'l3io-util'
module_description: 'Utility skills for LiquidLogicLabs BMad projects — one-time and housekeeping operations for artifact organization'
architecture: ''
standalone: true
expands_module: ''
skills_planned:
  - bmad-l3io-util-cleanup
config_variables: []
created: '2026-05-15'
updated: '2026-05-15'
---

# LiquidLogicLabs Utilities Module Plan

## Vision

One-time migration utility for LiquidLogicLabs BMad projects. Reorganizes flat artifact outputs into a structured epic/sprint folder hierarchy with zero-padded names, reconciles file references, verifies state consistency, and produces a clear summary report. Run once to bring a legacy project into the standard layout.

**Users:** LiquidLogicLabs teams with existing BMad project output that predates the structured folder conventions.

## Architecture

**Single workflow:** `bmad-l3io-util-cleanup`. No agent persona needed — this is a deterministic, sequential file operation with a dry-run gate. No memory. Config-driven via core BMad config.

**Rationale:** Pure workflow — sequential steps, a confirmation gate, deterministic operations. An agent persona would add overhead with no benefit.

### Memory Architecture

None required.

### Memory Contract

N/A.

### Cross-Agent Patterns

None — standalone, no subagents.

## Skills

### bmad-l3io-util-cleanup

**Type:** workflow

**Persona:** N/A — deterministic workflow, no persona.

**Core Outcome:** All flat artifact files moved to their correct structured paths, references updated, state consistency verified, summary report printed.

**The Non-Negotiable:** Never overwrite an existing destination file. Always dry-run first and get confirmation before moving anything.

**Capabilities:**

| Capability | Outcome | Inputs | Outputs |
| ---------- | ------- | ------ | ------- |
| File scan and classification | All files classified into 6 types (story, sprint closure, epic closure, test evidence, planning, unknown) | implementation_artifacts, planning_artifacts dirs | Classification table (internal) |
| Dry-run plan | Full table of proposed moves shown before any action | Classification results | Printed dry-run table: source, destination, classification, status (move/conflict/unclassified) |
| User confirmation | Explicit go/no-go before any file moves | Dry-run table | Confirmed move map |
| File moves | All classified files moved to structured paths; conflicts kept in place and recorded | Confirmed move map | Moved files at new paths |
| Reference reconciliation | Exact old-path references in status files, story files, planning docs, closure/test reports updated to new paths | Confirmed move map, reference-holding files | Updated file references |
| State verification | Folder names zero-padded, files in correct subdirs, sprint-status.yaml consistency, residual flat files flagged | Post-move filesystem state | Issues list |
| Summary report | Final tally printed | All operation results | `DONE - Moved: N, Conflicts: N, Unclassified: N, Refs Updated: N, Ref Conflicts: N, State Issues: N, Root: [path]` |

**Memory:** None.

**Init Responsibility:** None — no first-run setup required.

**Activation Modes:** Interactive only — requires user confirmation at dry-run gate.

**Tool Dependencies:**
- Config: `{project-root}/_bmad/bmm/config.yaml` — resolves `implementation_artifacts`, `planning_artifacts`, `output_folder`

**Design Notes:**
- File classification heuristics: story key regex `^([0-9]+)-[0-9]+.*\.md$`; sprint closure patterns `epic-*-sprint-*-retro-*.md`, `sprint-adversarial-*.md`, `sprint-redteam-*.md`; epic closure patterns `epic-*-arch-drift-*.md`, `epic-*-functional-completeness-*.md`; test evidence `*qa*.md`, `*test*.md`, `*verification*.md`
- Default sprint for ambiguous stories: `01` unless user provides a mapping
- Reference updates: auto-update only exact old-path matches that map to one known moved file; ambiguous references are recorded for manual review, never auto-updated
- Unknown files left in place and listed as unclassified — never moved without explicit classification

**Relationships:** Standalone — no dependencies on other ava-* modules.

---

## Configuration

This module requires no custom configuration beyond core BMad settings. All paths are resolved from `{project-root}/_bmad/bmm/config.yaml`.

## External Dependencies

None.

## UI and Visualization

No dedicated UI. The dry-run table and summary report are console output. The dry-run table format (source → destination, classification, status) provides clear pre-flight visibility before any changes are made.

## Setup Extensions

None.

## Integration

**Standalone:** Fully independent. Can be run on any BMad project with flat artifact outputs, regardless of which other ava-* modules are installed.

## Creative Use Cases

- Run after importing a legacy project into BMad to immediately bring it into the standard layout
- Use the dry-run output alone (without confirming) as an audit of how disorganized the current artifact structure is
- Run the state verification step mentally as a checklist when manually creating sprint folders

## Ideas Captured

### Cleanup / Reorganize Utility
- Purpose: reorganize flat artifact outputs into a structured epic/sprint folder layout
- Based on legacy skill `bmad-l3io-cleanup-artifacts` — modernized with new module code

### Target Folder Structure
```
{implementation_artifacts}/epic-{EE}/sprint-{SS}/stories/{story-key}.md
{implementation_artifacts}/epic-{EE}/sprint-{SS}/closure/...
{implementation_artifacts}/epic-{EE}/sprint-{SS}/tests/...
{implementation_artifacts}/epic-{EE}/epic-closure/...
{implementation_artifacts}/epic-{EE}/tests/...
{planning_artifacts}/epic-{EE}/...
{planning_artifacts}/epic-{EE}/sprint-{SS}/...
```
- EE and SS are zero-padded two-digit values (01, 02, etc.)

### Safety Rules (must preserve from legacy)
- Dry run first — show full cleanup plan before changing any files
- Never overwrite an existing destination file
- If destination exists: keep source in place, record conflict
- Preserve file contents exactly — move only, no edits
- Reference updates: auto-update only exact old-path matches that map to one known moved file; if ambiguous, record for manual review

### Inputs
- Load config from `{project-root}/_bmad/bmm/config.yaml`
- Resolve: `implementation_artifacts`, `planning_artifacts`, `output_folder`
- Default `implementation_artifacts` → `{output_folder}/implementation-artifacts` if not set

### Cleanup Heuristics (6 file types)
1. Story files in flat root — regex `^([0-9]+)-[0-9]+.*\.md$`; epic from first capture group; default sprint = 01
2. Sprint closure files — patterns: `epic-*-sprint-*-retro-*.md`, `sprint-adversarial-*.md`, `sprint-redteam-*.md`
3. Epic closure files — patterns: `epic-*-arch-drift-*.md`, `epic-*-functional-completeness-*.md`, epic retros
4. Test evidence files — patterns: `*qa*.md`, `*test*.md`, `*verification*.md`; sprint or epic-scoped
5. Planning artifacts — flat planning root → `planning_artifacts/epic-{EE}/[sprint-{SS}/]`
6. Unknown files — leave in place, record as "unclassified"

### Execution Sequence (8 steps)
1. Scan and classify all files
2. Print dry-run table: source path, destination path, classification, status (move/conflict/unclassified)
3. Ask for confirmation
4. Create required destination directories
5. Execute moves
6. Reconcile references in status files, story files, planning docs, closure/test reports
7. Verify artifact state: zero-padding, correct subdirectory placement, sprint-status.yaml consistency, residual flat files
8. Print summary report

### Required Output Format
```
DONE - Moved: N, Conflicts: N, Unclassified: N, Refs Updated: N, Ref Conflicts: N, State Issues: N, Root: [implementation_artifacts]
```

## Build Roadmap

**Recommended build order:**

1. **`bmad-l3io-util-cleanup`** (Build a Workflow) — Single skill module; the legacy SKILL.md is a near-complete specification. Build is mostly modernization (new module code, updated config paths, add dry-run table formatting).

**Next steps:**
1. Build the skill using **Build a Workflow (BW)** — share this plan document and the legacy skill at `skills.tmp/bmad-l3io-utils/bmad-l3io-cleanup-artifacts/SKILL.md` as context
2. When built, return to **Create Module (CM)** to scaffold the module infrastructure
