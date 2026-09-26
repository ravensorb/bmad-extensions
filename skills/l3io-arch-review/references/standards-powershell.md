# Engineering Standards — PowerShell Overlay

Loaded on top of `standards-core.md` when the project (or the component under review) is
PowerShell.

## Version — 7.6 LTS, and 7.4/7.5 are about to stop receiving security fixes

**Rule.** New work targets **PowerShell 7.6 LTS** (released March 2026, on .NET 10 LTS,
supported to November 2028). Windows PowerShell 5.1 is not a target for new code.

- **Time-critical as of this writing** — **PowerShell 7.4 and 7.5 lose all updates, including
  security fixes, on 10 November 2026.** A project pinned to either has a dated support cliff,
  not a preference. Treat "we are on 7.4" as a finding with a deadline attached, and verify the
  date against Microsoft's support-lifecycle page rather than trusting this line indefinitely.
- **5.1 interop** — where a script genuinely must run under Windows PowerShell (a constrained
  endpoint, a legacy agent), say so in the file header and keep it to the compatible subset.
  Do not silently write 5.1-compatible code in a 7.x project and lose the newer constructs.
- **Review** — Flag: `#Requires -Version 5.1` in new code, or no `#Requires` at all. A version
  floor is a contract (core §3), and its absence means the script's requirements are unstated.

## Script contract — strict, failing, and shaped like a cmdlet

**Rule.** Every non-trivial script or function opens with the same three lines, and advanced
functions carry `[CmdletBinding()]`.

```powershell
#Requires -Version 7.6
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
```

- **Why all three** — `StrictMode` turns a typo'd variable from a silent `$null` into an error;
  `ErrorActionPreference = 'Stop'` makes non-terminating errors actually stop, which is almost
  never what you want off. Neither is the default, and both change whether a bug is visible.
- **Approved verbs** — `Get-Verb`; a non-approved verb warns on module import and signals the
  function is doing something other than what its name implies.
- **Output objects, not formatted strings** — emit `[pscustomobject]`, let the caller format.
  A function that `Write-Host`s its result cannot be composed, tested, or piped (core §1).
  `Write-Host` is for interactive progress only; never for data.
- **Comment-based help** (`.SYNOPSIS`, `.PARAMETER`, `.EXAMPLE`) on anything exported (core §10).

## Quality toolchain

- **Lint** — **PSScriptAnalyzer** clean in CI, with a committed `PSScriptAnalyzerSettings.psd1`
  so local and CI agree. A suppression carries a justification comment (core §6).
- **Test** — **Pester 5**, invoked through a `[PesterConfiguration]` object rather than the
  older `Invoke-Pester` parameter set, which is why a Pester 4 invocation in CI is a finding
  rather than a style point. Keep logic in functions so it is testable (core §4).
- **Modules** — install with **PSResourceGet** (`Install-PSResource`), not the deprecated
  `PowerShellGet` v2 path. Pin versions for CI reproducibility.

## Secrets and logging

- **Never plaintext** — use the **SecretManagement** module with a vault; no credentials in
  source, in `$env:`, or echoed to a transcript.
- `[SecureString]`/`[pscredential]` at boundaries; do not `ConvertFrom-SecureString -AsPlainText`
  except at the exact point of use.
- **Structured logging with a correlation ID** (core §9). Prefer emitting objects a downstream
  collector can parse over free-text `Write-Verbose` narration.

## Review checklist (PowerShell-specific)

- [ ] Targets 7.6 LTS; any 7.4/7.5 pin flagged against the 10 Nov 2026 support end.
- [ ] `#Requires`, `Set-StrictMode -Version Latest`, `$ErrorActionPreference = 'Stop'`.
- [ ] Approved verbs; `[CmdletBinding()]` on advanced functions.
- [ ] Emits objects, not formatted strings; `Write-Host` only for interactive progress.
- [ ] PSScriptAnalyzer clean with committed settings; suppressions justified.
- [ ] Pester 5 via `[PesterConfiguration]`; meaningful coverage of branching logic.
- [ ] Secrets via SecretManagement; nothing plaintext in source, env or transcript.
- [ ] Comment-based help on exported functions (core §10).
