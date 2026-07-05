# Reference: How BMad discovers `module.yaml` (and why the "could not locate module.yaml" warnings appear)

> Research note validated against BMad Method installer source (`bmad-code-org/BMAD-METHOD`,
> v6.10.x): `tools/installer/project-root.js` and `tools/installer/core/manifest-generator.js`.
> Fetched via `gh api` from `main` on 2026-07-05.

## The warnings

During a consumer install / update ("Generating manifests" phase) BMad prints:

```text
[warn] collectAgentsFromModuleYaml: could not locate module.yaml for 'l3io-pm'.
       Agents declared by this module will not be written to config.toml.
[warn] writeCentralConfig: could not locate module.yaml for 'l3io-pm'.
       Answers from this module will default to team scope — user-scoped keys
       may mis-file into config.toml.
```

Both warnings come from the **same root cause**: the installer's `ManifestGenerator`
could not find a `module.yaml` whose `code:` matches the module name. They are emitted
by `collectAgentsFromModuleYaml()` and `writeCentralConfig()` in
`tools/installer/core/manifest-generator.js`, both of which call the shared resolver
`resolveInstalledModuleYaml(moduleName)` in `tools/installer/project-root.js`.

## Where the installer looks (the discovery contract)

The resolver reads the module's **source** (not the installed `_bmad/<module>/` copy).
For a custom module installed from a Git `repoUrl`, the source is the clone cached at:

```text
~/.bmad/cache/custom-modules/<host>/<owner>/<repo>/
```

For each cached repo root it runs `searchRootAll(root)`, which enumerates every
`module.yaml` at these **exact** locations (relative to the repo root) and then matches
one whose parsed `code:` (or `name:`) equals the requested module name:

| Pattern (relative to repo root) | Matches our layout? |
| --- | --- |
| `skills/module.yaml` | no |
| `src/module.yaml` | no |
| `skills/<dir>/module.yaml` (one level) | no (`skills/` absent) |
| `src/<dir>/module.yaml` (one level) | **yes → `src/l3io-pm/module.yaml`** |
| `<*-setup>/assets/module.yaml` (repo root) | no |
| `src/skills/<*-setup>/assets/module.yaml` | no |
| `skills/<*-setup>/assets/module.yaml` | no |
| `module.yaml` (repo root) | no |

**Critical detail — depth:** the `src/<dir>/` scan is exactly **one level** deep.
Our per-skill copies at `src/l3io-pm/l3io-pm-sprint-execute/module.yaml` (and the
identical copy carried by each sibling skill) are **two levels** under `src/` and are
therefore **never discovered**. The `<*-setup>/assets/module.yaml` convention only works
when a setup skill sits at the repo root, `src/skills/`, or `skills/` — none of which
match this repo, and standalone setup skills were folded into the operational skills, so
there is no `*-setup` directory to match anyway.

### The fix that works for this repo's layout

A per-module `module.yaml` at `src/<module>/module.yaml` — i.e.:

```text
src/l3io-pm/module.yaml     (code: l3io-pm)
src/l3io-sec/module.yaml    (code: l3io-sec)
src/l3io-util/module.yaml   (code: l3io-util)
```

This hits the supported `src/<dir>/module.yaml` (one-level) discovery path and its
`code:` matches the module name. This is a first-class supported location in
`searchRootAll` — no restructuring of the skills tree is required.

## Two conditions must BOTH hold, or the warnings persist

1. **The file must be shipped on the branch/channel the consumer tracks.**
   Consumers install with `source: custom`, `repoUrl: https://github.com/ravensorb/bmad-extensions`,
   `channel: next`, `version: main` (see the consumer's `_bmad/_config/manifest.yaml`).
   A `module.yaml` that exists only locally and is **untracked/uncommitted** never reaches
   the consumer — the installer clones the published `main`, not your working tree.

2. **The consumer's clone cache must be refreshed.**
   The resolver reads `~/.bmad/cache/custom-modules/<host>/<owner>/<repo>/`. A stale cache
   (cloned before the file was added) still lacks it. A `quick-update`
   (`--action quick-update`) re-fetches Git-sourced modules and re-runs manifest generation.

## `module.yaml` schema (fields the installer reads)

- `code:` — **required**; must equal the module name the installer requests. This is the
  match key and also the `[modules.<code>]` TOML section key.
- `name:`, `description:`, `module_version:`, `default_selected:`, `module_greeting:` — module essence.
- Config-prompt keys (any key with a `prompt:`/`default:`/`result:` block, optional
  `scope: user`) — `writeCentralConfig` uses these to decide team vs. user scope. Missing
  `module.yaml` is why user-scoped keys "mis-file into config.toml."
- `agents:` — array of agent essence descriptors collected into `config.toml`. Each entry:

  ```yaml
  agents:
    - code: redteam            # required (string); entries without a string code are skipped
      name: ""                 # optional
      title: "Red Team Agent"  # optional
      icon: "🔴"               # optional
      description: "…"         # optional
      team: <module-code>      # optional; defaults to the module code
  ```

  `module` is always set to the owning module. If `agents:` is absent or not an array,
  the module simply contributes no agents (no error) — but the "could not locate" warning
  still fires unless the `module.yaml` itself is found. So even agent-less modules
  (`l3io-pm`, `l3io-util`) need a discoverable `module.yaml` to silence the warning.

## Maintenance caveats

- **Duplication / drift.** The installer-discovery copy `src/<module>/module.yaml` and the
  per-skill copies `src/<module>/<skill>/module.yaml` are separate files and must be kept
  in sync. They had drifted (all pinned at `module_version: 1.0.13` while `package.json`
  climbed past `1.0.25`). `scripts/sync-bmad-versions.mjs` now stamps `module_version`
  across **every** `src/**/module.yaml` on each release (`postbump`), so this specific
  field no longer drifts — but the other fields (`description`, `module_greeting`,
  `agents:`) are still hand-duplicated and must be edited in lockstep.
- **`.github/agents/*.agent.md`** (e.g. `l3io-sec-agent-redteam.agent.md`) is the **GitHub
  Copilot** custom-agent stub (the parallel to the Claude Code slash-command surface). In
  this repo it is a **gitignored install-time artifact** (this repo dogfoods its own
  modules) — the installer generates it on the *consumer* side from the module's `agents:`
  block for whichever IDEs are enabled (Claude Code and/or GitHub Copilot), so it is
  deliberately not committed here.

## How to verify a fix landed

On the consumer, after pushing to `main` and running a quick-update:

```bash
# 1. cache now contains the discoverable file
find ~/.bmad/cache/custom-modules -path '*bmad-extensions/src/l3io-*/module.yaml'

# 2. run the installer with manifest debug to see agents get collected
BMAD_DEBUG_MANIFEST=true <bmad update command>
#   → [DEBUG] collectAgentsFromModuleYaml: l3io-sec contributed 1 agents from …/src/l3io-sec/module.yaml
```
