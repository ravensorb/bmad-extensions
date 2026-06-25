# Metrics Capture Contract (HARD RULE)

Communicate all responses in `{communication_language}`.

This file is the single source of truth for how estimates and actuals are captured across the l3io-pm skills. Load it at activation and keep its rules in context for every estimate and every closeout.

## The Rule (non-negotiable)

**Every planning point and every closeout — at epic, sprint, story, and retrospective level — MUST record both an `estimate` and an `actual` for all four metrics.** This is a hard rule, not an optional step. A missing `estimate` block, a missing `actual` block, a missing metric within a block, or a **guessed** token/cost actual is a contract violation — do not sign off a story, sprint, or epic with any of these missing.

The four metrics (same field names everywhere):

| Metric | Field(s) | Source | Notes |
|--------|----------|--------|-------|
| Compute hours | `time_hours_low/high` (estimate), `elapsed_hours` (actual) | Measured wall-clock via `date +%s` | AI-assisted agent run time. Always available. |
| Man hours | `man_hours_low/high` (estimate), `man_hours` (actual) | Modeled formula (traditional dev equivalent) | A defined equivalent, not a measurement. |
| Tokens | `tokens_k_min/max` (estimate), `tokens_k` (actual) | Measured under Claude; runtime-dependent otherwise | In thousands (K). |
| Token cost | `cost_low/high` (estimate), `cost` (actual) | Derived from real tokens × model rate | Formatted `$X.XX`. |

## Runtime-aware actuals capture

Determine `{runtime}` once at activation and bind it:

Claude Code sets `CLAUDECODE=1` in every Bash **and** PowerShell subprocess (documented). Detect by that alone — do NOT infer `claude` from a `~/.claude/projects` directory, which can linger from a prior Claude Code session on a shared machine and would misclassify a Copilot/Cursor run as Claude (yielding a false `$0.00` instead of `N/A`).

```bash
# bash (Linux / macOS / Git-Bash)
if [ "$CLAUDECODE" = "1" ]; then echo claude; else echo other; fi
```

```powershell
# PowerShell (Windows, or anywhere pwsh is the available shell)
if ($env:CLAUDECODE -eq '1') { 'claude' } else { 'other' }
```

Use whichever shell the harness runs. The two capture procedures below (bash and PowerShell) read the same transcript files and produce identical results — pick the one matching your platform: **bash on Linux/macOS or where `jq` is present; PowerShell on Windows** (or anywhere `bash`/`jq` are absent but PowerShell is).

Bind `{runtime}` = `claude` or `other`.

- **`{runtime}` == `claude` → capture EXACT actuals for tokens and cost.** Claude Code records real per-message usage in the session transcript; read it (procedure below). Never estimate when running under Claude.
- **`{runtime}` == `other` (Copilot / any non-Claude agent) → capture as much as the runtime exposes.** Compute hours (wall-clock) and man-hours (formula) are always available. For tokens and cost: if the runtime exposes a usage source, read it; **if it does not, write the literal value `N/A`** — do **not** guess, approximate, or back-fill from a throughput model. `0` is acceptable only when the runtime genuinely reports zero usage; absence is `N/A`.

Compute hours (`elapsed_hours`) and man-hours (`man_hours`) are captured identically in both runtimes — they do not depend on the transcript.

## Token & cost capture under Claude (EXACT)

Each orchestration phase records an epoch start timestamp (e.g. `{sprint_start_ts}`, `{epic_start_ts}`, `{story_start_ts}`). At close, sum the real `usage` fields from the session transcript JSONL entries for **this run** at/after that start. Discovery is anchored on the session id (`$CLAUDE_CODE_SESSION_ID`, exported by Claude Code into every subprocess) — it reads the main transcript `<sid>.jsonl` **and** every subagent transcript under `<sid>/subagents/`, honoring `CLAUDE_CONFIG_DIR` and remaining independent of the undocumented project-dir name encoding (it globs by id, not by path).

**Do not scope by `cwd`.** The orchestrator and its subagents routinely run from different working directories — subdirs they `cd` into, nested artifact paths, worktrees — so an exact-`cwd` filter silently drops most usage rows and trips the zero-entry guard, yielding a false `N/A` (this was the historical bug). The session id is globally unique, so id-scoping captures 100% of this run with zero contamination from concurrent sessions in other (or the same) repo.

When `$CLAUDE_CODE_SESSION_ID` is absent (older Claude Code, or an unusual harness), fall back to scanning all transcripts filtered by `cwd` **prefix** on the repo root (`git rev-parse --show-toplevel`) — a prefix match still spans every subdirectory, unlike the old exact-equality filter.

```bash
CFG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
START_ISO="$(date -u -d @{start_ts} +%Y-%m-%dT%H:%M:%S 2>/dev/null || date -u -r {start_ts} +%Y-%m-%dT%H:%M:%S)"
SID="$CLAUDE_CODE_SESSION_ID"
if [ -n "$SID" ]; then
  MODE=session; ROOT=""
  mapfile -t TX_FILES < <(find "$CFG/projects" \( -name "$SID.jsonl" -o -path "*/$SID/subagents/*.jsonl" \) 2>/dev/null)
else
  MODE=root; ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  mapfile -t TX_FILES < <(find "$CFG/projects" -name '*.jsonl' 2>/dev/null)
fi
```

Both helpers below consume `$TX_FILES`, `$MODE`, and `$ROOT` — run this preamble first so they are in scope. The `{ [ ... ] && cat ...; }` guard emits nothing when no files match, so `jq -s` sees `[]` and returns `N/A` rather than hanging on an arg-less `cat`.

**Total tokens (K)** — emits the string `"N/A"` when no usage rows match (zero-entry guard: a real phase always records usage, so zero matches means "not recorded here", never a real zero):

```bash
{ [ ${#TX_FILES[@]} -gt 0 ] && cat "${TX_FILES[@]}" 2>/dev/null; } \
  | jq -s --arg s "$START_ISO" --arg mode "$MODE" --arg root "$ROOT" '
      [ .[] | select((.timestamp // "") >= $s)
        | select($mode == "session" or ((.cwd // "") | startswith($root)))
        | .message.usage // empty ] as $u
      | if ($u|length) == 0 then "N/A"
        else ( [ $u[] | (.input_tokens//0)+(.output_tokens//0)
                       +(.cache_creation_input_tokens//0)+(.cache_read_input_tokens//0) ]
               | add ) / 1000 | floor
        end'
```

Bind to `{actual_tokens_k}` (a number, or the literal string `N/A`).

**Cost (USD)** — same guard, derived per-entry from the real model and real token categories:

```bash
{ [ ${#TX_FILES[@]} -gt 0 ] && cat "${TX_FILES[@]}" 2>/dev/null; } \
  | jq -s --arg s "$START_ISO" --arg mode "$MODE" --arg root "$ROOT" '
      def rate(m):
        if   (m|test("opus"))   then {i:5.0, o:25.0}
        elif (m|test("sonnet")) then {i:3.0, o:15.0}
        elif (m|test("haiku"))  then {i:1.0, o:5.0}
        else {i:5.0, o:25.0} end;            # default: Opus (current Claude Code default)
      [ .[] | select((.timestamp // "") >= $s)
        | select($mode == "session" or ((.cwd // "") | startswith($root)))
        | select(.message.usage) | .message ] as $m
      | if ($m|length) == 0 then "N/A"
        else ( [ $m[] | rate(.model // "") as $r | .usage as $u
                 | (($u.input_tokens//0)                * $r.i)
                 + (($u.output_tokens//0)               * $r.o)
                 + (($u.cache_creation_input_tokens//0) * $r.i * 1.25)   # 5-min cache write
                 + (($u.cache_read_input_tokens//0)     * $r.i * 0.1) ]  # cache read
               | add ) / 1000000
        end'
```

Bind to `{actual_cost}` (format `$X.XX`, or the literal string `N/A`).

**Rate table** (per-MTok input/output; cache-write = input × 1.25, cache-read = input × 0.1) is seeded with Anthropic pricing current as of 2026-06: Opus `$5/$25`, Sonnet `$3/$15`, Haiku `$1/$5`. **Update the `rate()` table when Anthropic pricing changes** — this is the only place rates live for actuals.

Notes:
- **Detection is env-var-only** (`CLAUDECODE=1`); a stale `~/.claude/projects` directory never produces a false `claude` classification.
- **Discovery scopes by session id** (`$CLAUDE_CODE_SESSION_ID`), reading the main transcript and every `<sid>/subagents/*.jsonl`. It does **not** filter by `cwd` — the orchestrator and its subagents legitimately run from different directories, and a `cwd` filter drops their rows (the historical cause of false `N/A`). Id-scoping is independent of the undocumented project-dir name encoding and captures every subagent transcript Claude Code writes for the run.
- **Fallback (no session id):** scan all transcripts filtered by `.cwd` **prefix** on the repo root. A prefix match still spans every subdirectory; it can merge a concurrent same-repo session, but that is rare and far preferable to a false `N/A`.
- **Zero-entry guard:** if no usage rows match the window, both helpers emit `N/A` — never `0` / `$0.00`. A false number is therefore impossible even if detection or discovery misfires (a non-Claude run, a relocated/renamed transcript) — the worst case is losing exact capture and recording `N/A`, never a fabricated value.
- ISO-8601 UTC timestamps compare correctly as strings, so the `>= $s` filter is exact.
- If `jq` is unavailable, treat tokens/cost as unreadable → `N/A` (do not guess).

## Token & cost capture under Claude — Windows / PowerShell

PowerShell does the same job natively (no `jq`/`find`/`xargs`). Use this on Windows, or anywhere PowerShell is the available shell. It reads the same transcripts, applies the **same session-id scoping** (with the same repo-root-prefix fallback) and the same zero-entry guard, and produces identical results.

**Total tokens (K)** — emits `N/A` when no usage rows match:

```powershell
$cfg = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $HOME '.claude' }
$startIso = [DateTimeOffset]::FromUnixTimeSeconds([int64]'{start_ts}').UtcDateTime.ToString('yyyy-MM-ddTHH:mm:ss')
$proj = Join-Path $cfg 'projects'
$sid = $env:CLAUDE_CODE_SESSION_ID
if ($sid) {
  $files = Get-ChildItem $proj -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq "$sid.jsonl" -or $_.FullName -match "[\\/]$sid[\\/]subagents[\\/].+\.jsonl$" }
  $root = $null
} else {
  $files = Get-ChildItem $proj -Recurse -Filter *.jsonl -ErrorAction SilentlyContinue
  $root = (git rev-parse --show-toplevel 2>$null); if (-not $root) { $root = (Get-Location).Path }
  $root = $root -replace '\\','/'
}
$rows = $files | Get-Content -ErrorAction SilentlyContinue |
  ForEach-Object { try { $_ | ConvertFrom-Json } catch {} } |
  Where-Object {
    $_.timestamp -ge $startIso -and $_.message.usage -and (
      $sid -or ($_.cwd -and (($_.cwd -replace '\\','/')).StartsWith($root))
    )
  }
if (-not $rows) { 'N/A' } else {
  $t = ($rows | ForEach-Object { $u = $_.message.usage
    [double]$u.input_tokens + [double]$u.output_tokens +
    [double]$u.cache_creation_input_tokens + [double]$u.cache_read_input_tokens } |
    Measure-Object -Sum).Sum
  [math]::Floor($t / 1000)
}
```

Bind to `{actual_tokens_k}`.

**Cost (USD)** — same guard and rate table, derived per-entry from the real model:

```powershell
if (-not $rows) { 'N/A' } else {
  $sum = 0.0
  foreach ($r in $rows) {
    $m = "$($r.message.model)"; $ri = 5.0; $ro = 25.0          # default: Opus
    if     ($m -match 'sonnet') { $ri = 3.0; $ro = 15.0 }
    elseif ($m -match 'haiku')  { $ri = 1.0; $ro = 5.0 }
    $u = $r.message.usage
    $sum += ([double]$u.input_tokens * $ri) + ([double]$u.output_tokens * $ro) +
            ([double]$u.cache_creation_input_tokens * $ri * 1.25) +
            ([double]$u.cache_read_input_tokens * $ri * 0.1)
  }
  '$' + [math]::Round($sum / 1000000, 2).ToString('0.00', [System.Globalization.CultureInfo]::InvariantCulture)
}
```

Bind to `{actual_cost}`. (Null usage fields coerce to 0 in the arithmetic; `InvariantCulture` keeps the `.` decimal separator regardless of system locale.) The `$rows` filter is shared between the two blocks — run the token block first so `$rows` is in scope.

## Recording timestamps (OS-aware)

Each phase records its start as epoch seconds (`{sprint_start_ts}`, `{epic_start_ts}`, `{story_start_ts}`) and computes `elapsed_hours` from it. Use the form matching the shell — this is the one place the surrounding skill steps depend on the OS:

| | Record start (epoch) | `elapsed_hours` at close |
|--|--|--|
| **bash** | `date +%s` | `round((($(date +%s) - {start_ts}) / 3600), 2)` |
| **PowerShell** | `[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()` | `[math]::Round((([DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - {start_ts}) / 3600), 2)` |

Where the closure/story steps say `date +%s`, substitute the PowerShell form when the harness shell is PowerShell. The token/cost capture above consumes the same epoch `{start_ts}`, so it stays correct regardless of which shell recorded it.

## Calibration feedback (all four metrics)

`{project-root}/_bmad/pm-calibration.yaml` must learn `token_ratio` and `cost_ratio` in addition to `time_ratio` and `man_hours_ratio` — but **only feed a ratio when the actual is a real number.** When a token/cost actual is `N/A` (non-Claude runtime, or unreadable transcript), **skip** that ratio for the entry (omit it); never feed `N/A` or a guessed value into the rolling average. The ratio fields are computed and applied exactly like `time_ratio` (mid-estimate divisor, exponential-decay weighting).
