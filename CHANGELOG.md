# Changelog

All notable changes to this project are documented in this file.

## [0.1.2] - 2026-05-13

### Added
- Adaptive parallel execution controls for sprint and epic orchestration:
  - default parallelism `2`
  - user-requested override support
  - hard cap `4`
  - effective concurrency safety fallback to sequential
- Standardized progress and ETA reporting guidance (announce + separate progress status line).
- New migration skill `bmad-migrate-artifacts` for existing projects moving from flat artifact layout.

### Changed
- Standardized artifact layout across implementation and planning outputs:
  - `epic-XX/sprint-YY/stories`
  - `epic-XX/sprint-YY/closure`
  - `epic-XX/sprint-YY/tests`
  - `epic-XX/epic-closure`
  - `planning-artifacts/epic-XX(/sprint-YY)`
- Updated orchestrator docs and adapters (Cursor/Copilot) to match artifact and parallelism conventions.
- Updated module discovery metadata to latest BMAD `plugins[]` manifest schema.

### Notes
- For existing projects, run `/bmad-migrate-artifacts` once before using updated sprint/epic workflows.

