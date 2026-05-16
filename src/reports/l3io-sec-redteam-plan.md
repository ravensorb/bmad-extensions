---
title: 'LiquidLogicLabs Red Team Module Plan'
status: 'complete'
module_name: 'LiquidLogicLabs Red Team'
module_code: 'l3io-sec'
module_description: 'Red team security analysis agent for LiquidLogicLabs projects — full adversarial analysis at epic, sprint, or solution scope'
architecture: ''
standalone: true
expands_module: ''
skills_planned:
  - bmad-l3io-sec-agent-redteam
config_variables: []
created: '2026-05-15'
updated: '2026-05-15'
---

# LiquidLogicLabs Red Team Module Plan

## Vision

Adversarial security analysis for LiquidLogicLabs projects at sprint, epic, or full solution scope. Examines the target through five lenses — external attacker, malicious insider, chaos engineer, abusive legitimate user, and cloud/platform best practices researcher — with AI poisoning applied as a cross-cutting concern across all four original lenses. Live research against current cloud and platform documentation ensures findings cite real, up-to-date guidance. Can be invoked standalone or called by the `l3io-pm` module at closure.

**Users:** LiquidLogicLabs delivery teams and security reviewers seeking structured adversarial analysis.

## Architecture

**Single agent:** `bmad-l3io-sec-agent-redteam`. Interactive persona — asks clarifying questions about scope before running. Produces a structured findings report. Agent (not workflow) because scope disambiguation, follow-up questions, and nuanced analysis benefit from a conversational persona.

**Rationale:** The five lenses are all variations of the same adversarial mindset applied to different threat models. A single agent with rich internal capabilities keeps the experience coherent. Splitting into five separate agents would fragment what should be a unified analysis.

### Memory Architecture

**Personal memory only** — used as a research cache for cloud/platform best practices.

```
{project-root}/_bmad/memory/bmad-l3io-sec-agent-redteam/
  index.md                    ← orientation: what cache files exist, last updated dates
  research-cache/
    networking.md       ← cached platform best practices, with last_updated timestamp
    identity.md
    storage.md
    compute.md
    ai-ml.md
    [topic].md                ← new topics added on demand
```

Cache invalidation: re-fetch if entry is older than 30 days (configurable), or on explicit user request (`--refresh-cache`).

### Memory Contract

| File | Read by | Written by | Content |
|------|---------|------------|---------|
| `index.md` | Agent on activation | Agent after cache updates | Cache inventory with last_updated per topic |
| `research-cache/{topic}.md` | Agent during platform best practices lens | Agent after live research | Curated platform guidance with citations, last_updated timestamp |

### Cross-Agent Patterns

- **Called by l3io-pm:** When invoked by the PM module, receives scope (sprint/epic/solution) and artifact path as arguments; runs non-interactively and writes findings report to the closure folder.
- **Standalone:** User invokes directly; agent asks about scope and target before running.
- **User is the router:** No orchestration between lenses — the agent manages all five perspectives internally within a single analysis run.

## Skills

### bmad-l3io-sec-agent-redteam

**Type:** agent

**Persona:** Red team specialist — adversarial, methodical, and thorough. Assumes the system will be attacked, abused, and pushed past its limits. A clean report on non-trivial scope is treated as a failure of analysis, not a clean system. Asks scope-clarifying questions before running when invoked interactively.

**Core Outcome:** A structured findings report covering all five threat lenses with severity-graded findings, attack paths, impact descriptions, specific recommendations, and an executive summary.

**The Non-Negotiable:** Never produce a clean report on non-trivial scope without a mandatory re-analysis pass. If reviewing auth or data access code, authorization findings must surface or re-examine explicitly.

**Capabilities:**

| Capability | Outcome | Inputs | Outputs |
| ---------- | ------- | ------ | ------- |
| Scope and surface mapping | Attack surface documented (entry points, trust boundaries, data flows, auth checkpoints, persistent state) | Scope target (sprint/epic/solution artifact paths or codebase area) | Surface map (internal, not written to disk) |
| External attacker analysis | Injection, auth bypass, authz gaps, data exfil, API abuse, client-side findings | Scoped artifacts/code | Findings added to report |
| Malicious insider analysis | Privilege abuse, out-of-scope data access, audit gaps, corruption vectors, supply chain injection | Scoped artifacts/code | Findings added to report |
| Chaos engineer analysis | Failure propagation, partial-write corruption, race conditions, resource exhaustion, non-idempotent retries, recovery paths | Scoped artifacts/code | Findings added to report |
| Abusive legitimate user analysis | Feature misuse, logic flaws, edge input corruption, per-tenant DoS, boundary conditions | Scoped artifacts/code | Findings added to report |
| cloud/platform best practices research | Current cloud/platform guidance violations cited with source links | Scoped artifacts, research cache | Findings added to report; cache updated |
| AI poisoning cross-cut | AI poisoning applied across all four original lenses | Scoped artifacts | Findings added to each relevant lens section |
| Design and architecture red team | Missing controls, trust boundary violations, defense-in-depth gaps, observability gaps, secrets exposure | Architecture doc (optional) | Findings added to report |
| Structured findings report | Severity-graded findings with title, attack path, impact, recommendation | All analysis results | HTML report written to closure dir — good candidate for HTML output |
| Executive summary | One-paragraph risk posture summary | All findings | Appended to report |

**Memory:**
- Reads `index.md` on activation to check cache inventory and last-updated dates
- Loads only relevant `research-cache/{topic}.md` files for the current analysis scope
- Writes new cache entries and updates `index.md` after live platform research
- Daily log tag: `[l3io-sec-redteam]`

**Init Responsibility:** On first run, creates memory folder structure: `index.md`, `research-cache/` directory. Writes initial `index.md` noting no cache entries yet.

**Activation Modes:** Interactive (standalone — asks about scope, target, context before running) and headless (called by `l3io-pm` workflows — receives scope and artifact paths as arguments, runs non-interactively, writes report to provided output path).

**Tool Dependencies:**
- **WebSearch** (required) — live research for cloud/platform best practices. Agent must have web access configured.
- Cache TTL: 30 days default (configurable). Re-fetches entries older than TTL or on `--refresh-cache` flag.

**Design Notes:**
- HALT conditions: scope empty → ask and abort; zero Critical/High on non-trivial scope → re-analyze with fresh perspective; reviewing auth code with no auth findings → re-examine ownership explicitly
- Scope determines surface area, not depth: solution > epic > sprint in what files are examined; the five-lens approach applies at all scopes
- When called headlessly by l3io-pm, writes report to: `{closure_dir}/{scope}-redteam-{date}.md`
- HTML report output is strongly recommended for findings — structured table with severity color-coding improves usability

**Relationships:** Called by `bmad-l3io-pm-sprint-execute` (scope=sprint) and `bmad-l3io-pm-epic-execute` (scope=epic). Can also be invoked standalone at solution scope.

---

## Configuration

| Variable | Prompt | Default | Result Template | User Setting |
| -------- | ------ | ------- | --------------- | ------------ |
| `research_cache_ttl_days` | How many days before platform best practices cache entries are refreshed? | `30` | `research_cache_ttl_days: {value}` | Yes |

## External Dependencies

| Dependency | Type | Required By | Setup Notes |
| ---------- | ---- | ----------- | ----------- |
| WebSearch | Claude tool | bmad-l3io-sec-agent-redteam | Must be enabled in Claude Code permissions for live platform research |

## UI and Visualization

Findings report is a strong candidate for **HTML output** — a structured findings table with severity color-coding (CRITICAL=red, HIGH=orange, MEDIUM=yellow, LOW=blue, OBSERVATION=grey) and an executive summary panel. Improves usability significantly over raw Markdown for stakeholder-facing reports.

## Setup Extensions

No setup extensions beyond config collection. Memory folder structure is created on first agent run.

## Integration

**Standalone value:** Can be invoked directly by the user to run a red team analysis at any scope without any PM module present.

**l3io-pm integration:** When installed, l3io-pm workflows automatically delegate red-team phases to this agent. The agent accepts a `--headless` flag and runs non-interactively, writing findings to the PM workflow's closure directory.

## Creative Use Cases

- Run at solution scope before a major release as a comprehensive pre-ship security gate
- Use the platform best practices lens standalone to audit an existing cloud architecture for compliance gaps
- Invoke with `--refresh-cache` after a major platform policy update to get current guidance
- Run at epic scope after multiple sprints to catch cross-sprint security patterns invisible at sprint level

## Ideas Captured

### Red Team Agent
- Scope: epic, sprint, or solution — scope determines surface area, not approach
  - Solution-level: full codebase analysis
  - Epic-level: cross-sprint concerns and cumulative risk
  - Sprint-level: implementation of that sprint's stories and changes
- Called by l3io-pm module when installed (cross-module integration)
- Can also be invoked standalone by the user directly
- Agent (not workflow) — interactive persona, asks clarifying questions about scope

### Legacy Skill Learnings (bmad-l3io-red-team)
- Role framing: "You assume the system will be attacked, abused, and pushed past its limits. A clean report on non-trivial scope is a failure of analysis, not a clean system."
- Step 1: Scope and surface mapping (entry points, trust boundaries, data flows, auth checkpoints, persistent state)
- Step 3: Design and Architecture Red Team — missing controls, trust boundary violations, defense-in-depth gaps, observability gaps, recovery capability, secrets exposure
- Step 4: Findings report format — Title, Attack Path (reproduce steps), Impact, Recommendation; grouped by severity
- Step 5: Executive summary — what was reviewed, overall risk posture, most dangerous finding, single most important recommendation
- Severity levels: CRITICAL (exploitable today, blocks ship), HIGH (fix before ship), MEDIUM (fix next sprint), LOW (hardening), OBSERVATION (non-vuln: monitoring gaps, logging, code smells)
- HALT conditions: scope empty → ask and abort; zero Critical/High on non-trivial scope → re-analyze; reviewing auth code with no auth findings → re-examine ownership checks explicitly

### Attack Perspectives / Lenses (5 total)
1. **External attacker** — injection, auth bypass, authz gaps, data exfil, API abuse, client-side (XSS/CSRF/etc.)
2. **Malicious insider** — privilege abuse, out-of-scope data access, audit log gaps, corruption/deletion of others' data, supply chain injection
3. **Chaos engineer** — failure propagation, partial-write corruption, race conditions/TOCTOU, resource exhaustion, non-idempotent retries, recovery paths
4. **Abusive legitimate user** — feature misuse/scraping, logic flaws (wrong order/state), edge inputs corrupting shared state, per-tenant DoS, boundary conditions (zero/null/max/overflow)
5. **cloud/platform best practices researcher** — researches cloud and platform best practices being violated (networking, identity, storage, compute, AI/ML governance); cites specific platform docs; live web search with cached results

### AI Poisoning — Cross-Cutting Concern
- Applied ACROSS the four original lenses (not a separate lens):
  - External attacker + AI: prompt injection, model manipulation from outside
  - Malicious insider + AI: training data poisoning, backdoors via data access
  - Chaos engineer + AI: model degradation under adversarial conditions, input distribution shift
  - Abusive legitimate user + AI: adversarial prompts, jailbreaking, indirect injection via content
- platform best practices lens also covers AI/ML governance (Responsible AI, model safety)

### Platform Best Practices Research
- Mechanism: LIVE web search — agent actively queries current cloud/platform docs at analysis time
- Research results are CACHED in agent memory — keyed by topic/domain so the same networking guidance isn't re-fetched on every run
- Cache invalidation: by date (e.g. re-fetch if cached entry is older than N days) or on user request
- Should cover at minimum: networking, identity (IAM/identity), storage, compute, AI/ML governance
- Output should cite specific platform guidance docs where violations are found
- Requires WebSearch as a configured tool dependency
- This means the security module DOES need memory architecture (research cache)

## Build Roadmap

**Recommended build order:**

1. **`bmad-l3io-sec-agent-redteam`** (Build an Agent) — Single skill module; build it, then go straight to Create Module (CM).

**Next steps:**
1. Build the skill using **Build an Agent (BA)** — share this plan document as context
2. When built, return to **Create Module (CM)** to scaffold the module infrastructure
