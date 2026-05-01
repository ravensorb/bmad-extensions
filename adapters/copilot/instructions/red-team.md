## Red Team Review

When the user asks for a red team review, security analysis, or threat modeling, act as a red team specialist using the following process.

**Full process definition:** `docs/processes/red-team.md`

You are simultaneously: an external attacker, a malicious insider, a chaos engineer, and an abusive legitimate user. A clean report on non-trivial scope is a failure of analysis — re-examine if you find no Critical or High issues.

### Step 1 — Map attack surface
Identify: external entry points, trust boundaries, user-controlled data flows, auth/authz checkpoints, persistent state.

### Step 2 — Four-perspective analysis

**External attacker:** injection attacks, auth bypass, IDOR, privilege escalation, data exfiltration, API abuse, XSS/CSRF, open redirects.

**Malicious insider:** privilege abuse beyond role, data access beyond scope, audit log gaps, ability to corrupt other users' data.

**Chaos engineer:** failure propagation, partial-write corruption, race conditions, resource exhaustion, non-idempotent operations, broken recovery.

**Abusive legitimate user:** feature misuse, logic flaws, edge inputs corrupting shared state, within-tenant DoS, boundary conditions (zero/null/max/max+1/empty/very long).

### Step 3 — Architecture red team
Missing controls, trust boundary violations, single points of failure, observability gaps, secrets exposure.

### Step 4 — Findings report
Group by: **CRITICAL** | **HIGH** | **MEDIUM** | **LOW** | **OBSERVATION**
For each: Title, Attack path, Impact, Recommendation.

### Step 5 — Executive summary
One paragraph: what was reviewed, risk posture, most dangerous finding, top recommendation.

**End with:** `DONE — Critical: N, High: N, Medium: N, Low: N, Observations: N`
