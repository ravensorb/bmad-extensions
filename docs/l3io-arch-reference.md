# l3io-arch Reference

Engineering-standards architecture guardrails and review.

## Overview

`l3io-arch` applies a LiquidLogicLabs engineering-standards charter to a project's architecture. It operates in three modes — **design guardrails** (new project), **review** (audit a design, component, or diff), and **decision support** (weigh options and record an ADR). The standards are the single source of truth in the skill's `references/standards-*.md` files; the skill applies and cites them rather than inventing rules.

The module is standalone — no orchestrator relationship and no runtime dependency on the other l3io modules. It is also designed to be wired into core `bmad-architecture` and `bmad-code-review` via `bmad-customize`, so the standards apply automatically during design and review without forking those core skills.

Skill: `/l3io-arch-review`.

## Configuration

Config is resolved via `{project-root}/_bmad/scripts/resolve_config.py` — `core.*` for shared settings and `modules.l3io-arch.*` for this module. No section is required; every value has a default.

Key settings (with defaults):

- `preferred_diagram_format` — `mermaid` (fallback `ascii`). Preferred format for architecture diagrams. This is the **only** setting `modules.l3io-arch` owns, and the only one this module's `module.yaml` declares.

Two paths this module reads are **not** its own keys:

- `output_folder` — `core.output_folder`, default `{project-root}/_bmad-output`. The installer owns it.
- `implementation_artifacts` — `modules.l3io-pm.implementation_artifacts`, default `{output_folder}/implementation-artifacts`. `l3io-pm` owns the state tree, so it owns the path, and all four modules resolve it from there — there is one artifact tree, not one per module. Setting `modules.l3io-arch.implementation_artifacts` in `_bmad/custom/config.toml` has **no effect**.

Review reports write to `implementation_artifacts`; ADRs and the docs skeleton write under `{project-root}/docs/`.

## The Standards Charter

The universal principles live in `references/standards-core.md`. Each is written for **design**, **review**, and **decision** use, with red flags and a review severity (BLOCKER / MAJOR / MINOR).

| # | Principle | Core rule |
|---|-----------|-----------|
| 1 | Separation of concerns | Each module owns one responsibility; concern leakage across boundaries is a defect. |
| 2 | Reuse over copy-paste | Duplication of non-trivial logic is not allowed; refactor to reuse rather than copy. |
| 3 | Design by contract | Declare preconditions, postconditions, invariants; validate at boundaries, trust inside. |
| 4 | Testability | If it is hard to test, the design is wrong — inject dependencies, isolate side effects. |
| 5 | Brevity without sacrificing readability | Least code a competent reader understands on first pass; flag both golfing and ceremony. |
| 6 | Comment discipline | Comments explain current state and intent, not change history; no comment-per-fix. |
| 7 | Dependency selection | Prefer established, actively-maintained, well-licensed packages; every dep is a liability. |
| 8 | GA over alpha/beta | Depend on generally-available releases; preview/non-GA use needs an ADR-recorded justification. |
| 9 | Unified correlated logging | One structured logging approach; a correlation/trace ID propagates across every boundary. |
| 10 | Documentation with diagrams | Architectural / developer / operational docs, well-organized; Mermaid-preferred (ASCII fallback) diagrams. |

## Stack Overlays

The skill auto-detects the stack in scope and loads the matching overlay on top of `standards-core.md`.

| Overlay | Detected via | Headline rules |
|---------|--------------|----------------|
| `standards-python.md` | `pyproject.toml`, `uv.lock`, `poetry.lock` | **uv or Poetry for ALL apps and packages**; committed lockfile; supported Python; ruff/mypy; structured logging. |
| `standards-nodejs.md` | `package.json` | **Latest active LTS**, pinned (`engines` + `.nvmrc`); committed lockfile; TypeScript strict; `pino`-style structured logging. |
| `standards-dotnet.md` | `*.csproj`, `*.sln` | **Latest supported .NET**; deployable apps publish **self-contained** with explicit RID; nullable + warnings-as-errors; `ILogger` structured logging. |
| `standards-github-actions.md` | `.github/workflows/*` | **Marketplace actions over custom scripting**; **pin to major** (trusted) or SHA (third-party); least-privilege `permissions`; Dependabot. |
| `standards-docker.md` | Dockerfiles | **Pin every `FROM` by digest AND tag**; minimal/distroless final stage carrying no build toolchain; secrets via `--mount=type=secret`, never `ARG`/`ENV`; `--sbom=true --provenance=true` at build time; non-root numeric `USER`; exec-form entrypoint so signals land. |
| `standards-powershell.md` | `*.ps1` | **7.6 LTS** — 7.4/7.5 lose security fixes 10 Nov 2026; `#Requires` + `Set-StrictMode -Version Latest` + `$ErrorActionPreference = 'Stop'`; approved verbs, objects not formatted strings; PSScriptAnalyzer clean, Pester 5 via `[PesterConfiguration]`; SecretManagement. |
| `standards-shell.md` | `*.sh` | `#!/usr/bin/env bash` + `set -euo pipefail`; quote every expansion, `"$@"` not `$@`; `mktemp` with `trap … EXIT` on the next line; ShellCheck clean with justified suppressions; escalate to a real language once branching outgrows shell. |

## Modes

### Mode A — Design guardrails (new project)

Walk `standards-core.md` §1–10 plus each loaded overlay as a design checklist. Produce a boundaries/architecture sketch (C4 context + at least one flow diagram), the initial ADR set for every load-bearing call (numbered and placed as in Mode C), a `/docs` skeleton across the architectural / developer / operational axes, and a dependency policy note.

### Mode B — Review

Audit the target against every principle. Each finding names **severity · principle · location · remediation** and rolls up into a report (see `references/review-report.md`) with an executive summary and a severity-graded table. **Gate:** BLOCKER and MAJOR findings must be resolved or ADR-justified; MINOR auto-defers to backlog.

### Mode C — Decision support

Identify the principle(s) in tension, weigh options against them, recommend, and record an ADR (`assets/adr-template.md`) at `{project-root}/docs/adr/NNNN-slug.md` — the one ADR home.

**Numbering.** When `{project-root}/_bmad/scripts/pm-status.py` is present, take the number from the l3io-pm register rather than choosing one:

```bash
uv run {project-root}/_bmad/scripts/pm-status.py adr-reserve \
  --state-root {implementation_artifacts}/state --epic n/a --slug {slug} \
  --adr-dir {project-root}/docs/adr
```

A directory listing shows who has finished, not who is in flight, so parallel writers that derive a number from one will collide. Without l3io-pm there is no register: use the highest number in `docs/adr/` plus one, which is safe only for the single-writer case that implies, and `adr-reserve` skips those numbers later.

Fill `Epic:` (`n/a` outside an epic) and `Departs from spec:` with the `path#anchor` of the spec section the decision departs from, or `n/a`.

Invocation shortcuts: `/l3io-arch-review design|review|decision [--stack python|nodejs|dotnet|github-actions]`.

### `pm-status.py` subcommands this skill runs

| Subcommand | Used by | For |
|---|---|---|
| `adr-reserve` | Mode C, and Mode A's initial ADR set | Allocates the next ADR number under a lock, from `l3io-pm`'s register, before the file is written. Optional: without `l3io-pm` installed there is no register and the skill falls back to the highest number on disk plus one. Full signature in the [l3io-pm reference](l3io-pm-reference.md). |

## Severity Model

| Severity | Meaning |
|----------|---------|
| **BLOCKER** | Violates a hard rule; blocks sign-off. |
| **MAJOR** | Clear deviation; must be fixed or ADR-justified. |
| **MINOR** | Improvement opportunity; auto-defers to backlog. |

## Wiring into Core BMad

`assets/customize-architect.md` documents the `bmad-customize` overlays to author **in the consuming project** (the core skills live there, not in this extension repo):

- **`bmad-architecture`** — load the standards before finalizing any architecture/technology decision; hold the design against every principle; record ADRs; produce diagrams and the docs skeleton.
- **the story enricher, legacy `bmad-create-story`** — when drafting a story's acceptance criteria, make the technical contract explicit wherever the story implies one (interfaces/API contracts, data model, error and edge handling, observability, security controls, testability), adding one concrete technical AC per applicable dimension without expanding scope. This is the same contract `l3io-pm-execute`'s story technical-AC gate checks, applied at authoring time.
- **`bmad-code-review`** (and/or `l3io-sec-redteam`) — additionally check standards compliance during review; treat BLOCKER/MAJOR as gating, MINOR as backlog.

The overlays point at the standards files rather than duplicating them, keeping a single source of truth.

## Artifacts Produced

- **Review** → severity-graded findings report at `implementation_artifacts`.
- **Design / Decision** → ADRs under `{project-root}/docs/adr/` — the one ADR home — from `assets/adr-template.md`, numbered by `adr-reserve` when l3io-pm is installed (see Mode C), plus a docs skeleton.
