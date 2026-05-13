# Changelog

All notable changes to this project will be documented in this file. See [commit-and-tag-version](https://github.com/absolute-version/commit-and-tag-version) for commit guidelines.

## [0.1.3](https://github.com/ravensorb/bmad-extensions/compare/v0.1.2...v0.1.3) (2026-05-13)


### Features

* rename artifact cleanup skill and expand validation ([432e203](https://github.com/ravensorb/bmad-extensions/commit/432e2036db8e5f38436e0f287c4882ea3ba99a92))

## [0.1.2] - 2026-05-13

### Added

- Adaptive parallel execution controls for sprint and epic orchestration:
  - default parallelism `2`
  - user-requested override support
  - hard cap `4`
  - effective concurrency safety fallback to sequential
- Standardized progress and ETA reporting guidance (announce + separate progress status line).
- New migration skill `bmad-migrate-artifacts` for existing projects moving from flat artifact layout.

### Changed (0.1.2)

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
