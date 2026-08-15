# Sync Step 02: Detect Platform

Communicate all responses in `{communication_language}`.

Detect the external sync platform and auth method. Bind variables used by step-03 and step-04.

## 1. Check for existing sync configuration

```bash
cat {project-root}/_bmad/sync-mapping.yaml 2>/dev/null || echo "(absent)"
```

If present, read and bind:
- `{sync_platform}` — `github` or `ado` (from `mappings[0].external_system`)
- `{sync_mapping_file}` = `{project-root}/_bmad/sync-mapping.yaml`

If absent and `{sync_mode}` is not `setup`:
```
No sync-mapping.yaml found. Run /l3io-pm-sync setup first to configure the sync platform.
```
BLOCKED: sync not configured.

## 2. Detect platform (setup mode only)

If `{sync_mode}` = `setup`:

Run detection script:
```bash
python3 {skill-root}/scripts/detect-platform.py \
  --project-root {project-root} \
  --auth-method {github_auth_method}
```

The script probes for GitHub MCP tools and ADO PAT token availability.
Bind `{sync_platform}` from the script output (`github` or `ado`).

If detection fails:
```
Could not detect a sync platform. Ensure GitHub MCP or ADO PAT is configured.
```
BLOCKED: platform detection failed.

## 3. Resolve auth method

| Platform | Auth method from config | Check |
|---|---|---|
| `github` | `{github_auth_method}` = `mcp` | GitHub MCP tools available |
| `github` | `{github_auth_method}` = `pat` | `GITHUB_TOKEN` env var set |
| `ado` | `{ado_auth_method}` = `pat` | `ADO_PAT` env var set |

Bind `{auth_method}` = resolved auth method.

## 4. Output

```
Step 02 complete — platform: {sync_platform}, auth: {auth_method}, mapping: {sync_mapping_file}
```
