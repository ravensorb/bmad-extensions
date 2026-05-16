# l3io-sec Reference

Full reference for the security module — a red team specialist agent that performs adversarial analysis through five threat lenses with an AI poisoning cross-cut and live cloud/platform best practices research.

## Overview

`bmad-l3io-sec-agent-redteam` is a memory-backed agent, not a stateless skill. It maintains a sanctum — a set of persistent identity and memory files at `{project-root}/_bmad/memory/bmad-l3io-sec-agent-redteam/`. The sanctum holds the agent's persona, research cache, session logs, and accumulated knowledge about the project. Each session loads the sanctum and picks up where the previous one left off.

The agent works across three activation modes: called automatically by `l3io-pm`, invoked interactively by the user, or invoked as a subagent with explicit scope from another orchestrator.

## Configuration

| Variable | Section | Default | Description |
|----------|---------|---------|-------------|
| `research_cache_ttl_days` | `l3io-sec` in `config.yaml` | `30` | Number of days before a cached platform best practices topic is considered stale and re-researched |

Config is read from `{project-root}/_bmad/config.yaml` and `{project-root}/_bmad/config.user.yaml`.

## Activation Modes

### Mode 1 — Orchestrator invocation

Triggered when the activation prompt contains an explicit scope, artifact paths, and output path — i.e., when called headlessly by `bmad-l3io-pm-sprint-execute` (Step 6) or `bmad-l3io-pm-epic-execute` (Step 4c).

Behavior:
1. If sanctum is absent, initialize it automatically
2. Load relevant research cache topics from sanctum
3. Load `references/scope-mapping.md`, `references/threat-analysis.md`, `references/platform-research.md`, `references/findings-report.md`
4. Execute full analysis against the provided scope
5. Write Markdown report to the specified output path
6. Emit: `DONE — Critical: N, High: N, Medium: N, Low: N | BLOCKED: [reason] | FAILED: [reason]`

### Mode 2 — First run / no sanctum

Triggered when invoked interactively and no sanctum exists at `{project-root}/_bmad/memory/bmad-l3io-sec-agent-redteam/`.

Behavior:
1. Run `python3 {skill-root}/scripts/init-sanctum.py {project-root} {skill-root}` to create the sanctum
2. Check if `config.yaml` has an `l3io-sec` section; if not, run module setup
3. Load `references/first-breath.md` — the agent comes to life for the first time

### Mode 3 — Normal interactive

Triggered when invoked interactively and sanctum exists.

Behavior:
1. Batch-load from sanctum: `INDEX.md`, `PERSONA.md`, `CREED.md`, `BOND.md`, `MEMORY.md`, `CAPABILITIES.md`
2. Greet the user
3. Ask for scope and target

After any interactive session, the agent writes a session log to `sessions/YYYY-MM-DD.md` and updates the sanctum with anything learned.

## The Five Threat Lenses

Analysis always covers all applicable lenses. Each finding must include a title, attack path, impact, recommendation, and lens code.

### Lens 1 — External Attacker (EXT)

Adversary with no privileged access, attacking from outside. Checks:

- **Injection points:** SQL, command, LDAP, template, path traversal, deserialization
- **Authentication bypass:** weak tokens, predictable resets, missing auth on sensitive routes
- **Authorization gaps:** IDOR, missing ownership checks, horizontal/vertical privilege escalation
- **Data exfiltration:** verbose errors revealing internals, unprotected sensitive fields, improper export controls
- **API abuse:** undocumented endpoints, rate limit bypass, parameter tampering, mass assignment
- **Client-side:** XSS, CSRF, open redirects, insecure storage in browser/local state

### Lens 2 — Malicious Insider (INS)

Adversary with legitimate but limited access, attacking from inside. Checks:

- **Privilege abuse:** accessing data beyond their role; using elevated permissions for unauthorized purposes
- **Out-of-scope data access:** querying other tenants' or users' data; abusing bulk export or reporting features
- **Audit gap exploitation:** operations that succeed without leaving audit trails; log tampering; bypassing monitoring
- **Corruption and deletion:** overwriting others' data; injecting malicious content into shared state
- **Supply chain injection:** inserting malicious code or data via legitimate contribution paths

### Lens 3 — Chaos Engineer (CHA)

Adversary who attacks failure modes, not the happy path. Checks:

- **Failure propagation:** downstream service failure mid-transaction — does the system leave partial state?
- **Partial-write corruption:** failed writes that commit some changes but not others; orphaned records; inconsistent state
- **Race conditions and TOCTOU:** check-then-act patterns; concurrent modifications to shared state; non-atomic operations
- **Resource exhaustion:** unbounded loops, large input processing, memory leaks under load, connection pool exhaustion
- **Non-idempotent retries:** operations that succeed twice causing double-charges, duplicate records, or repeated side effects
- **Recovery path security:** does error handling restore security invariants? Does cleanup code skip access checks?

### Lens 4 — Abusive Legitimate User (ABU)

Adversary who uses the system exactly as designed, but in ways designers didn't intend. Checks:

- **Feature misuse:** scraping, automated bulk operations, feature chaining to escalate access
- **Logic flaws:** operating steps out of expected order; triggering transitions the state machine allows but shouldn't
- **Edge inputs:** zero values, null/empty, maximum values, negative numbers, unicode edge cases, encoding attacks
- **Shared state corruption:** inputs that corrupt other users' experiences; per-tenant resource consumption affecting other tenants
- **Boundary conditions:** behavior at exact limits (max file size, max items, expiry boundaries)

### Lens 5 — Design and Architecture Red Team (DAR)

System-level weaknesses not visible at the code level. Checks:

- **Missing controls:** security controls specified in architecture but absent in implementation
- **Trust boundary violations:** components communicating over boundaries without authentication or validation
- **Defense-in-depth gaps:** single points of failure in security controls; no fallback if one layer fails
- **Observability gaps:** security-relevant events that aren't logged; no alerting on anomalous patterns
- **Recovery capability:** kill switches, revocation mechanisms, audit trails adequate for forensics
- **Secrets exposure:** hardcoded credentials, keys in config, secrets in version control or logs

## AI Poisoning Cross-Cut (AIP)

AIP is not a standalone lens — it is a cross-cut applied across all four adversarial lenses when AI/ML components are present in scope.

| Lens | AIP adds |
|------|----------|
| EXT | Prompt injection from external input — model manipulation. Indirect injection via content the model processes (documents, emails, web pages). Output handling vulnerabilities — where model output reaches code execution or privileged operations |
| INS | Training data poisoning via insider write access to data pipelines. Backdoors planted in model training or fine-tuning workflows. Exfiltration of proprietary prompts, training data, or model artifacts |
| CHA | Model degradation under adversarial input distribution shift. Inference behavior under resource pressure. Recovery behavior when the AI component fails mid-request |
| ABU | Adversarial prompts crafted by legitimate users. Jailbreaking through legitimate-looking inputs. Systematic probing of model behavior to identify exploitable patterns |

## HALT Conditions

Three conditions require the agent to stop analysis and surface a problem before proceeding:

1. **Empty scope** — no artifacts or entry points can be identified: halt and ask for clarification before running any lens

2. **Zero Critical/High on non-trivial scope** — if the scope contains auth code, data access patterns, or external interfaces and zero Critical/High findings surface: mandatory re-analysis required. Choose a different angle, assume a different attacker model, examine from the chaos engineer lens if not done thoroughly. Document why the score is genuinely low before declaring the scope clean.

3. **Auth code with no auth findings** — if scope includes authentication, authorization, or identity management code and zero auth findings surface: re-examine ownership checks, token validation, and privilege escalation paths explicitly. Document the reasoning.

## Platform Best Practices Research (PBR)

### Research cache

The agent maintains a cache of curated cloud and platform best practices at `{project-root}/_bmad/memory/bmad-l3io-sec-agent-redteam/research-cache/`.

Cache topics are created on demand to match whatever platforms appear in scope. Examples:

| Topic file | Covers |
|------------|--------|
| `identity.md` | IAM/RBAC, federation, conditional access, managed identities, OAuth/OIDC |
| `networking.md` | Segmentation, private endpoints, ingress/egress controls, service mesh |
| `storage.md` | Encryption at rest/in transit, access controls, retention, signed URLs |
| `compute.md` | Host hardening, container/image security, serverless runtime security |
| `ai-ml.md` | Responsible AI, model access controls, training data governance, output safety |

New topics are added on demand when scope introduces a service or platform not yet cached.

### TTL behavior

Before each search, the agent checks each relevant topic's `last_updated` date in `INDEX.md`. If the cached entry is ≤ `research_cache_ttl_days` old, it loads from disk — no web search. If older or absent, it runs a live WebSearch, curates the results, and writes back to the cache.

Live searches use authoritative sources for whatever platform or framework is in scope — vendor documentation (AWS, Google Cloud, Azure, Kubernetes, etc.), CIS Benchmarks, OWASP, NIST. The agent stays source-neutral and does not privilege any single vendor.

### WebSearch permission

WebSearch is required for live platform research. If the permission is not granted in Claude Code, the agent will fall back to cached data only. Grant the permission via Claude Code settings or `.claude/settings.json` before running l3io-sec on a project where platform-specific guidance matters.

## Output Formats

| Format | Used when |
|--------|-----------|
| **Markdown** | Writing to l3io-pm closure directories (output path ends in `.md`) |
| **HTML** | Standalone invocation or when output path ends in `.html` — includes severity color-coding |

### Finding fields

Every finding includes:

| Field | Description |
|-------|-------------|
| Severity | CRITICAL, HIGH, MEDIUM, LOW, or OBSERVATION |
| ID | Sequential finding identifier |
| Title | Specific and descriptive — not generic |
| Lens | Lens code(s) that surfaced the finding |
| Attack path | Concrete reproduction steps from an adversary's perspective |
| Impact | What an adversary gains; who is affected; what data or systems are at risk |
| Recommendation | Specific code or design change — not generic advice |

### Severity definitions

| Severity | Meaning |
|----------|---------|
| CRITICAL | Exploitable today with significant impact; blocks release |
| HIGH | Serious risk; fix before release |
| MEDIUM | Meaningful risk; fix in next sprint or create backlog story |
| LOW | Hardening opportunity; backlog or accept with rationale |
| OBSERVATION | Not a vulnerability — monitoring gaps, logging issues, code smells worth noting |

## Lens Code Reference

| Code | Lens |
|------|------|
| EXT | External Attacker |
| INS | Malicious Insider |
| CHA | Chaos Engineer |
| ABU | Abusive Legitimate User |
| DAR | Design and Architecture Red Team |
| AIP | AI Poisoning (cross-cut across EXT/INS/CHA/ABU) |
| PBR | Platform Best Practices Research |
