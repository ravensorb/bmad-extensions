# CI/CD Pipeline Guidelines

Apply these guidelines whenever a story involves creating or modifying CI/CD pipelines (GitHub Actions workflows, Gitea CI, act-compatible workflows, deployment automation, etc.).

---

## Modular Design

- Break pipelines into reusable, composable units. Extract shared job logic into reusable workflow files (`.github/workflows/reusable-*.yml`) using `workflow_call`.
- Each reusable workflow has one named responsibility. If you need the same job in two or more workflows, extract it.
- Compose top-level workflows by calling reusable ones — avoid copy-pasting job blocks.

---

## Invocation Modes

Every workflow must support both manual execution and being called by another workflow:

```yaml
on:
  workflow_dispatch:
    inputs:
      environment:
        description: Target environment
        type: choice
        options: [dev, staging, prod]
  workflow_call:
    inputs:
      environment:
        type: string
        required: true
  push:
    branches: [main]
```

Add event triggers (`push`, `pull_request`, `schedule`) only when they naturally fit the workflow's purpose.

---

## Actions vs Inline Scripts

- **Prefer actions** over `run:` steps for well-defined tasks (checkout, setup-node, upload-artifact, cache, etc.).
- Use `run:` only for project-specific logic that no action covers well, or for short single-purpose shell commands.
- If a `run:` block exceeds ~15 lines, extract it to a script file (e.g., `.github/scripts/deploy.sh`) and call it via `run: bash .github/scripts/deploy.sh`. This keeps diffs readable and the script testable in isolation.

---

## Version Pinning

Pin third-party actions to their **major version tag**:

```yaml
- uses: actions/checkout@v4
- uses: actions/setup-node@v4
- uses: actions/upload-artifact@v4
```

Exception — security-sensitive actions (e.g., token handling, OIDC): pin to the full commit SHA and include a comment with the human-readable version:

```yaml
# v2.1.3
- uses: some-org/sensitive-action@abc123def456abc123def456abc123def456abc1
```

Do not pin to floating tags like `@main`, `@latest`, or `@master`.

---

## Runner Compatibility (nektos/act · Gitea · GitHub)

Pipelines must run without modification on all three targets.

**Runner label:** use `ubuntu-latest` or a specific Ubuntu version label (e.g., `ubuntu-22.04`). These map cleanly to act container images.

**Avoid runner-specific assumptions:**
- Do not assume large pre-installed tool sets — nektos/act and Gitea runners typically provide only Docker and bash. Use setup actions (e.g., `actions/setup-node`, `actions/setup-python`) explicitly.
- Do not use Windows- or macOS-only steps.
- Do not reference `$RUNNER_TOOL_CACHE` or other GitHub-hosted-runner-specific environment variables in logic.

**Guard GitHub-only steps** with `if: ${{ !env.ACT }}` so they are skipped under act and Gitea runners:

```yaml
- name: Create GitHub deployment status
  if: ${{ !env.ACT }}
  uses: chrnorm/deployment-action@v2
```

**Context portability:** use `github.server_url` and `github.api_url` instead of hardcoded `https://github.com` or `https://api.github.com` — these resolve correctly on both GitHub and Gitea.

---

## nektos/act Local Configuration

For local `act` runs, use these files (all excluded from version control):

| File | Purpose |
|------|---------|
| `.act.secrets` | Secret key/value pairs — one per line: `KEY=value` |
| `.act.env` | Environment variable overrides for local runs |
| `.act.vars` | Variable overrides (maps to the `vars` context in workflows) |

Reference in act invocations:
```bash
act --secret-file .act.secrets --env-file .act.env --var-file .act.vars
```

Provide checked-in example files with placeholder values:
- `.act.secrets.example`
- `.act.env.example`
- `.act.vars.example`

Add the live files to `.gitignore`.

---

## LiquidLogicLabs Actions (Optional)

When LiquidLogicLabs GitHub Actions cover a workflow need, prefer them over custom inline logic:
- Check the LiquidLogicLabs repository for available actions before writing inline scripts for common tasks (environment promotion, notifications, artifact management, release automation, etc.).
- Pin to the latest published **major version** (`liquidlogiclabs/action-name@vN`).
- Apply the same major-version pin rule as all other third-party actions.

---

## Per-Story CI/CD Checklist

Before a CI/CD story is `done`, verify all that apply:

- [ ] Workflow includes both `workflow_dispatch` and `workflow_call` triggers
- [ ] All third-party actions pinned to major version (or SHA with version comment for security-sensitive actions)
- [ ] No `run:` block longer than ~15 lines without extraction to `.github/scripts/`
- [ ] Shared job logic extracted to a reusable workflow file
- [ ] Tested locally with `act` (or confirmed compatible with act container images)
- [ ] `.act.secrets.example`, `.act.env.example`, `.act.vars.example` provided if secrets/env vars are needed
- [ ] Live `.act.*` files added to `.gitignore`
- [ ] `if: ${{ !env.ACT }}` guards applied to GitHub-only steps
- [ ] `runs-on: ubuntu-latest` (or explicit Ubuntu version) — no macOS or Windows runners
- [ ] No hardcoded `github.com` or `api.github.com` URLs in workflow logic
