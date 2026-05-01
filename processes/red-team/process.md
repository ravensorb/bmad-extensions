# Red Team Review — Process Definition

## Goal
Perform an adversarial security and resilience review from four distinct threat actor perspectives. Surface vulnerabilities, abuse scenarios, and failure modes that builders miss because they think like builders, not attackers.

## Inputs
- **scope** — What to review: code changes, story implementation, epic deliverable, API surface, architecture doc, or diff
- **context** (optional) — Architecture docs, prior reviews, threat model, deployment environment

## Halt conditions
- Scope is empty or unreadable → ask for clarification, stop
- Zero Critical/High findings on non-trivial scope → re-analyze before reporting; a clean report is suspicious

---

## Step 1 — Scope and surface mapping

Map the attack surface before analyzing:
- External entry points (APIs, file uploads, webhooks, auth flows, webhooks)
- Trust boundaries and where they are enforced
- User-controlled data flows (where does untrusted input travel?)
- Authentication and authorization checkpoints
- Persistent state (database, cache, files, sessions, queues)

---

## Step 2 — Multi-perspective threat analysis

Attack from all four viewpoints. Do not stop at the first finding per category.

### 2a. External Attacker
- **Injection:** SQL/NoSQL, command injection, path traversal, template injection, LDAP
- **Authentication bypass:** weak tokens, predictable IDs, session fixation, JWT algorithm confusion, replay attacks
- **Authorization gaps:** IDOR, privilege escalation, horizontal movement, missing ownership checks
- **Data exfiltration:** verbose errors, timing oracles, enumeration, mass assignment
- **API abuse:** missing rate limits, quota bypass, parameter pollution, HTTP verb tampering
- **Client-side:** XSS, CSRF, clickjacking, open redirects, unsafe deserialization

### 2b. Malicious Insider (authenticated user acting in bad faith)
- Privilege abuse beyond granted role (what can a low-privilege user do that they shouldn't?)
- Data access beyond scope of their own records/projects/tenants
- Audit log gaps — what actions are unlogged or undetectable?
- Ability to corrupt or delete data for other users
- Backdoor or supply-chain injection opportunities

### 2c. Chaos Engineer
- Service failure propagation — what breaks downstream when dependency X fails?
- Data corruption under partial failures (writes that half-succeed, transactions that don't roll back)
- Race conditions and TOCTOU (check-then-act gaps)
- Resource exhaustion — memory leaks, connection pool starvation, disk fill, CPU spin loops
- Non-idempotent operations called multiple times (retry storms, duplicate inserts)
- Recovery paths — can the system come back to a consistent state after a mid-operation crash?

### 2d. Abusive Legitimate User
- Feature misuse to extract disproportionate value (scraping, automation, bulk exports)
- Logic flaws that allow operations in unintended order or system state
- Edge inputs that corrupt shared state (oversized payloads, special characters, Unicode edge cases, null bytes)
- Denial of service against other users within the same tenant or org
- Boundary conditions: zero, negative, max, max+1, empty string, null, extremely long strings

---

## Step 3 — Design and architecture red team

- Missing security controls specified in the design but not implemented
- Trust boundary violations (data crossing boundaries without re-validation)
- Defense-in-depth gaps (single control protecting a critical path with no fallback)
- Observability gaps — can you detect an attack in progress? Would you know afterward?
- Recovery capability — can you restore consistent state after a successful attack?
- Secrets exposure vectors — env vars leaked in logs, error messages, client bundles, stack traces

---

## Step 4 — Structured findings report

Group findings by severity. For each finding include:
- **Title** (short, specific)
- **Attack path** (how to reproduce or exploit)
- **Impact** (what an attacker achieves)
- **Recommendation** (specific, actionable fix)

### Severity levels
| Level | Meaning |
|-------|---------|
| **CRITICAL** | Exploitable in production today — blocks shipping |
| **HIGH** | Significant exploitable risk — should fix before shipping |
| **MEDIUM** | Meaningful risk — fix in next sprint |
| **LOW** | Hardening / defense-in-depth — good to fix |
| **OBSERVATION** | Non-vulnerability: monitoring gap, missing logging, code smell with security implications |

---

## Step 5 — Executive summary

One paragraph: what was reviewed, overall risk posture, the single most dangerous finding, and the most important recommendation.

---

## Output status line (required last line)
```
DONE — Critical: N, High: N, Medium: N, Low: N, Observations: N
```
