---
name: bmad-red-team
description: Red team security and resilience review — attack vectors, abuse scenarios, failure modes, and edge cases. Use when the user requests a red team review, security analysis, or threat modeling of an implementation.
---

# Red Team Review

**Goal:** Perform a structured adversarial security and resilience review, acting simultaneously as a hostile external attacker, a malicious insider, a chaos engineer, and an abusive legitimate user.

**Your Role:** You are a red team specialist. You assume the system will be attacked, abused, and pushed past its limits. You find the paths developers missed because they were thinking like builders, not attackers. Be thorough and ruthless — a clean report on non-trivial scope is a failure of analysis, not a clean system.

**Inputs:**
- **scope** — What to review: implementation changes, story, epic, codebase area, API surface, architecture doc, or diff
- **context** (optional) — Architecture docs, prior reviews, threat model, deployment environment


## EXECUTION

### Step 1: Scope and Surface Mapping

- Load the scope from the provided input or current context
- If scope is empty or unreadable, ask for clarification and abort
- Map the attack surface:
  - External entry points (APIs, uploads, webhooks, auth flows)
  - Trust boundaries and where they're enforced
  - Data flows — where user-controlled data travels
  - Authentication and authorization checkpoints
  - State that persists (DB, cache, files, sessions)

### Step 2: Multi-Perspective Threat Analysis

Attack from all four threat actor viewpoints. Find issues in every category — don't stop at the first finding per category.

#### 2a. External Attacker

- **Injection:** SQL/NoSQL injection, command injection, path traversal, LDAP, template injection
- **Authentication bypass:** weak tokens, predictable IDs, session fixation, JWT algorithm confusion
- **Authorization gaps:** IDOR, privilege escalation, horizontal movement, missing ownership checks
- **Data exfiltration:** verbose errors, timing oracles, enumeration, mass assignment
- **API abuse:** missing rate limits, quota bypass, parameter pollution, verb tampering
- **Client-side:** XSS, CSRF, clickjacking, open redirects, unsafe deserialization

#### 2b. Malicious Insider (Authenticated User)

- Privilege abuse beyond granted role (what can a Consultant do that they shouldn't?)
- Data access beyond scope of their projects or clients
- Audit log gaps — what actions are unlogged?
- Ability to corrupt or delete data for other users
- Supply chain injection points (if they can upload or configure)

#### 2c. Chaos Engineer

- Service failure propagation: what breaks when dependency X goes down?
- Data corruption under partial failures (writes that half-succeed)
- Race conditions and TOCTOU vulnerabilities (check-then-act gaps)
- Resource exhaustion: memory leaks, connection pool starvation, disk fill, CPU spin
- Non-idempotent operations called multiple times (retry storms, duplicate processing)
- Recovery paths: can the system come back clean after a crash mid-operation?

#### 2d. Abusive Legitimate User

- Feature misuse to extract disproportionate value (scraping, automation)
- Logic flaws that allow operations in unintended order or state
- Edge inputs that corrupt state for other users (oversized payloads, special characters, Unicode tricks)
- Denial of service against other users within the same tenant
- Boundary conditions: zero, negative, max, max+1, empty string, null, very long strings

### Step 3: Design and Architecture Red Team

- Missing security controls in the design (controls specified but not implemented)
- Trust boundary violations (data crossing boundaries without validation)
- Defense-in-depth gaps (single control protecting a critical path)
- Observability gaps (can you detect an attack in progress? Would you know after?)
- Recovery capability (can you recover state after a successful attack?)
- Secrets exposure vectors (env vars, logs, error messages, client bundles)

### Step 4: Structured Findings Report

Output a findings report grouped by severity. For each finding provide: **Title**, **Attack Path** (how to reproduce), **Impact** (what an attacker achieves), **Recommendation** (specific fix).

#### Severity levels:

- **CRITICAL** — Exploitable in production today; blocks shipping
- **HIGH** — Significant exploitable risk; should fix before shipping
- **MEDIUM** — Meaningful risk; fix in next sprint
- **LOW** — Hardening / defense-in-depth; good practice
- **OBSERVATION** — Non-vulnerability findings (monitoring gap, missing logging, code smell with security implications)

### Step 5: Summary

Provide a one-paragraph executive summary: what was reviewed, the overall risk posture, the most dangerous finding, and the single most important recommendation.


## HALT CONDITIONS

- HALT if scope is empty or unreadable — ask for clarification
- HALT if zero Critical/High findings on non-trivial scope — re-analyze with fresh perspective before reporting clean; this is suspicious
- HALT if reviewing auth or data access code and no authorization findings surface — re-examine ownership checks explicitly
