---
skill: l3io-sec-redteam
phase: complete
classification: memory-agent
last_touched: 2026-05-15
---

> **Historical authoring record.** This log captures the decisions and rationale from the
> sessions that built this skill. It is kept for provenance and **may not describe current
> behaviour** — the live contracts are the repository's `CLAUDE.md` and this skill's
> `references/`. Where a later note below is marked "Correction," it was added after the
> fact next to the original entry; the original text is left as written.

# Decision Log

## Session 2026-05-15 — Initial Build

**Classification: Memory Agent.** The agent uses memory for its research cache — cloud/platform best practices results cached per topic domain with a TTL. This requires a sanctum but does not require PULSE (no autonomous background behavior). SKILL.md is a lean bootloader with Four capability reference files.

**Four capabilities, not ten.** The plan listed ten capabilities, but most were subdivisions of the same adversarial mindset. Consolidated to: scope-mapping (SM), threat-analysis (TA), platform-research (PBR), findings-report (FR). The agent's persona handles the HOW of adversarial thinking; capability prompts specify the WHAT.

**Threat analysis unified in one file.** All five lenses, AI poisoning cross-cut, and design/architecture red team live in threat-analysis.md. Splitting them would create five near-identical "apply adversarial thinking to X" files with no added value. The unified file is cleaner and loads once.

**HALT conditions in threat-analysis.md.** Three explicit halt conditions: empty scope (abort), zero Critical/High on non-trivial scope (re-analyze), auth code with no auth findings (re-examine). Placed in the capability file, not in SKILL.md, because they govern analysis behavior rather than activation routing.

**Orchestrator invocation detection.** Activation routing checks whether the prompt includes explicit scope + artifact paths + output path (the l3io-pm subagent invocation pattern). This is checked first (before the no-sanctum check) to handle the case where l3io-pm calls the agent for the first time with no sanctum — init runs, then analysis proceeds without First Breath.

**Configuration-style First Breath.** This is a focused domain tool, not a long-term creative companion. Five config questions cover: scope, tech stack, report audience, known findings, out-of-scope. Warm but quick.

**Not customizable via TOML.** Sanctum (PERSONA/CREED/BOND/CAPABILITIES) is the primary customization surface. research_cache_ttl_days is loaded from `{project-root}/_bmad/config.yaml` (l3io-sec section), not from customize.toml, because it's a functional parameter for the project, not an agent behavior override.
>
> **Correction (current behaviour):** there is no `{project-root}/_bmad/config.yaml`. `research_cache_ttl_days` resolves from `modules.l3io-sec` via BMad core's `resolve_config.py`, which merges the four TOML layers (`_bmad/config.toml`, `config.user.toml`, `custom/config.toml`, `custom/config.user.toml`). See `CLAUDE.md` and this skill's `references/config-resolution.md`.

**research-cache/ in sanctum.** Cache lives at `{project-root}/_bmad/memory/l3io-sec-redteam/research-cache/`. The init script creates this directory. INDEX.md has a Research Cache section the agent maintains as cache inventory.

**HTML recommended for standalone output.** Findings report capability supports both HTML (standalone) and Markdown (l3io-pm closure). The decision of which to use is based on output path extension. HTML provides severity color-coding useful for stakeholder communication.
