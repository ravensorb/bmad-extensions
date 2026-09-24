# Reference: How BMad discovers `module.yaml`

> **Re-measured 2026-09-22 against the installed bmad-method **6.12.0** tree**
> (`tools/installer/project-root.js`, `tools/installer/modules/plugin-resolver.js`,
> `tools/installer/core/manifest-generator.js`, `tools/installer/ui.js`), by running that
> code against this repository and against a real install. Everything below cites a file and
> a line in that tree. The previous revision of this file was validated against v6.10.x, was
> written from the mechanism alone, and reached a **false** conclusion — see
> [What the earlier revision got wrong](#what-the-earlier-revision-got-wrong).

## There are TWO discovery mechanisms, not one

This is the single most important fact in this document, and the one the branch that broke
the install did not have. BMad finds a `module.yaml` twice, with two different code paths,
two different contracts, and two different failure modes.

### 1. Install-time plugin resolution — `PluginResolver.resolve()`

`tools/installer/modules/plugin-resolver.js:29`. Per plugin, driven by the `skills` array in
`.claude-plugin/marketplace.json`. Five strategies, first match wins:

| # | Strategy | Requires |
| --- | --- | --- |
| 1 | `_tryRootModuleFiles` (`:72`) | `module.yaml` **and** `module-help.csv` at the **common parent** of the plugin's skills |
| 2 | `_trySetupSkill` (`:106`) | a listed skill whose directory name ends in `-setup`, with `assets/module.yaml` **and** `assets/module-help.csv` |
| 3 | `_trySingleStandalone` (`:146`) | exactly **one** listed skill, with `assets/module.yaml` **and** `assets/module-help.csv` |
| 4 | `_tryMultipleStandalone` (`:183`) | **every** listed skill has both files — each becomes its own module |
| 5 | `_synthesizeFallback` (`:229`) | nothing; code/name are invented from `marketplace.json` and SKILL.md frontmatter, **and every install-time setting the module declares is lost** |

This is what decides the module's code, name, and which install-time questions get asked.
It is per-plugin and it is correct. Measured against this repo:

```text
plugin l3io-pm    -> code=l3io-pm    strategy=2  skills/l3io-pm-setup/assets/module.yaml
plugin l3io-sec   -> code=l3io-sec   strategy=3  skills/l3io-sec-redteam/assets/module.yaml
plugin l3io-util  -> code=l3io-util  strategy=3  skills/l3io-util-doctor/assets/module.yaml
plugin l3io-arch  -> code=l3io-arch  strategy=3  skills/l3io-arch-review/assets/module.yaml
```

> **Strategy 1 is a trap for this repo.** Every plugin here lists skills directly under
> `skills/`, so `_computeCommonParent` (`:278`) returns `skills/` for *all four* — including
> the single-skill ones, where the common parent of one path is its `dirname`. If
> `skills/module-help.csv` ever existed beside `skills/module.yaml`, strategy 1 would fire
> first and resolve **all four plugins to one module**. `check:module` rule 1 forbids that
> file for this reason.

### 2. Config-writing resolution — `resolveInstalledModuleYaml()`

`tools/installer/project-root.js:102`. Called per **module name** by
`collectAgentsFromModuleYaml` (`manifest-generator.js:249`) and `writeCentralConfig`
(`manifest-generator.js:448`/`:560`) while the manifests are written. This is the one that
decides **which `[modules.<code>]` section each module's answers are written under**, and
which agents reach `[agents.*]`.

`searchRootAll(root)` (`:109`) collects candidates in this **fixed priority order**:

| # | Pattern (relative to the source root) | Source line |
| --- | --- | --- |
| 1 | `skills/module.yaml` | `:112` (`dir` loop, `direct`) |
| 2 | `skills/<dir>/module.yaml` — one level | `:120` |
| 3 | `src/module.yaml` | `:112` |
| 4 | `src/<dir>/module.yaml` — one level | `:120` |
| 5 | `<*-setup>/assets/module.yaml` at the root, under `src/skills/`, and under `skills/` | `:129`–`:137` |
| 6 | `module.yaml` at the root | `:140` |

**The rule that broke this branch:** `assets/module.yaml` is recognised **only** under a
directory whose name ends in `-setup` (`:134`). For any other skill directory the **only**
location this resolver sees is `skills/<skill>/module.yaml` — the skill **root**.

Then the caller picks one of two branches, and they do **not** behave the same:

| Install source | Branch | Behaviour |
| --- | --- | --- |
| Git URL (`source: custom, repoUrl: …`) — the documented consumer path | `:190`–`:212`, the `~/.bmad/cache/custom-modules` walk | parses **every** candidate and matches `parsed.code === moduleName \|\| parsed.name === moduleName`. **Correct per module.** |
| Local `--custom-source <dir>` — what `npm run smoke:install` uses | `:171`–`:181`, the `CustomModuleManager._resolutionCache` branch | calls `searchRoot(localPath)`, which is `all[0]` (`:149`) — **no matching on the requested module at all**. Every plugin in the repo shares one `localPath` (`ui.js:1212`, `sourceResult.rootDir`), so **all four modules resolve to the same first candidate.** |

The URL branch was extended for multi-plugin repos ("Url-source repos can host multiple
plugins (discovery mode), so we need all matches, not just the first", `:107`). The local
branch was not. For a repository that hosts more than one module — which this one does —
**the local branch cannot attribute per module, whatever the layout.**

### What first-match-wins does downstream

Two places consume the (wrong) file, and both write TOML without a dedupe:

- `manifest-generator.js:560` — `sectionKey = codeByModuleName[moduleName] || moduleName`.
  With every module resolving to one file, every module gets that file's `code:` as its TOML
  section key. Two modules with install answers ⇒ `[modules.<code>]` **declared twice**.
- `manifest-generator.js:608` — one `[agents.<code>]` block per collected agent, and agents
  are collected once **per module** (`:279`, `module: moduleName`, inside the
  `for (const moduleName of this.updatedModules)` loop at `:248`). An `agents:` array in
  whichever file wins ⇒ `[agents.redteam]` emitted **four times**.

TOML forbids both. `tomllib` refuses the file, `resolve_config.py` exits 1, and
`references/config-resolution.md` §4 then tells every l3io skill *and* every BMad core skill
to stop and report "BMad core is not installed" — which is false.

## The contract this repository follows

| Module shape | Where `module.yaml` must live | Why |
| --- | --- | --- |
| Multi-skill, with a `*-setup` skill (`l3io-pm`) | `skills/l3io-pm-setup/assets/module.yaml` | PluginResolver strategy 2 and `searchRootAll` pattern 5 both read exactly this path |
| Standalone single-skill (`l3io-sec`, `l3io-util`, `l3io-arch`) | **both** `skills/<skill>/assets/module.yaml` **and** `skills/<skill>/module.yaml`, byte-identical | `assets/` is what PluginResolver strategy 3 and `validate-module.py` read; the **skill root** is the only place `searchRootAll` looks for a non-`*-setup` skill |
| The repository itself | `skills/module.yaml`, declaring **no** `code:`, **no** `name:`, **no** `agents:` | it is `searchRootAll`'s first candidate, so it is what the local branch's `all[0]` returns for every module; with no `code:` the section key falls back to each module's own name (`manifest-generator.js:560`), and with no `agents:` no agent block is emitted more than once |

`check:module` rule 1 enforces all three, deriving the module homes from the tree rather than
from a list. The marker file `skills/module.yaml` documents its own mechanism inline.

Measured on the **URL-source** path (the documented consumer path), before and after:

```text
before (assets/ only)                  after (skill-root copies added)
  l3io-pm   -> l3io-pm-setup/assets/     l3io-pm   -> skills/l3io-pm-setup/assets/module.yaml
  l3io-sec  -> NULL                      l3io-sec  -> skills/l3io-sec-redteam/module.yaml
  l3io-util -> NULL                      l3io-util -> skills/l3io-util-doctor/module.yaml
  l3io-arch -> NULL                      l3io-arch -> skills/l3io-arch-review/module.yaml
```

Measured on the **local `--custom-source`** path, from a real install:

```text
before                                  after
  [modules.l3io-pm]                       [modules.l3io-sec]
  research_cache_ttl_days = "30"          research_cache_ttl_days = "30"
  [modules.l3io-pm]      <-- twice        [modules.l3io-arch]
  preferred_diagram_format = "mermaid"    preferred_diagram_format = "mermaid"
  resolve_config.py EXIT=1                resolve_config.py EXIT=0
```

### Known limitation, stated rather than hidden

On the local `--custom-source` path the `[agents.redteam]` block declared by
`l3io-sec`'s `module.yaml` is **not** written, and the `[warn] could not locate module.yaml`
lines do not appear (a file *is* located — the marker). That is the cost of the only
arrangement that keeps the file parseable on that path: `searchRoot()` returns `all[0]`
without consulting the module being asked about, so no layout can make it answer four
different questions with four different files. On the **URL-source** path — how consumers
actually install — each module resolves to its own `module.yaml` and the agent block is
written normally. When BMad's local branch learns to match by code the way its URL branch
already does, `skills/module.yaml` becomes inert rather than wrong: it matches no code.

## What the earlier revision got wrong

The previous revision recorded the `-setup`-only rule correctly, then wrote that the three
standalone modules' `assets/module.yaml` "match no pattern in the table above" and called
them **"unaffected"**. Both halves of that sentence are in the file; only the first is true.
Matching no pattern is precisely *being* affected: it is `resolveInstalledModuleYaml`
returning `NULL`, which is what the "could not locate module.yaml" warnings this document
exists to explain actually are.

Two lessons, both already in `CLAUDE.md` as general rules and both earned here:

1. **Conformance to one BMad tool is not conformance to BMad.** `validate-module.py` and
   `project-root.js` ship in the same tree, read the same file, and disagree about where it
   lives. `ADR-0008` reasoned from the validator alone and produced a layout that validated
   clean and did not install.
2. **A hedge has to be attached to the claim it covers.** The previous revision's hedge
   ("has not been re-verified against BMad's installer source") was attached to the
   `l3io-pm` case it thought had *improved*, not to the three it declared unaffected.

## Verifying a change here

Two commands, both against a real install — never by reading the table above:

```bash
# 1. A real install, including the resolver assertion added for this defect.
mkdir -p /tmp/l3io-smoke && bash scripts/smoke-install.sh /tmp/l3io-smoke

# 2. Inside that install: exactly one table per module, each under its own code.
grep -nE '^\[(modules|agents)\.' /tmp/l3io-smoke/_bmad/config.toml
cd /tmp/l3io-smoke && uv run _bmad/scripts/resolve_config.py --project-root .
```

`BMAD_DEBUG_MANIFEST=true` on the install prints which `module.yaml` each module resolved to,
straight from `collectAgentsFromModuleYaml`.

## `module.yaml` schema (fields the installer reads)

- `code:` — **required** in a real module home; the match key on the URL path, and the
  `[modules.<code>]` TOML section key. Deliberately **absent** from `skills/module.yaml`.
- `name:`, `description:`, `module_version:`, `default_selected:`, `module_greeting:`,
  `post-install-notes:` — module essence. `module_version` is stamped from `package.json` by
  `scripts/sync-bmad-versions.mjs` at `postbump`, in the `assets/` copy **and** the skill-root
  copy.
- Install-time settings — any top-level key whose value is a mapping containing `prompt:`
  (`manifest-generator.js`, `'prompt' in value`). `scope: user` files the answer into
  `config.user.toml`; anything else, including `user_setting: true`, is team scope.
  `scripts/module-config-keys.mjs` derives the full set from these files for the smoke test.
- `agents:` — array of agent essence descriptors collected into `[agents.*]`. Each entry:

  ```yaml
  agents:
    - code: redteam            # required (string); entries without a string code are skipped
      name: ""                 # optional
      title: "Red Team Agent"  # optional
      icon: "🔴"               # optional
      description: "…"         # optional
      team: <module-code>      # optional; defaults to the module code
  ```

  `module` is always set to the owning module.

## Consumer-side conditions that still apply

1. **The file must be on the branch the consumer tracks.** Consumers install with
   `source: custom`, `repoUrl: https://github.com/ravensorb/bmad-extensions`. A `module.yaml`
   that exists only in a working tree never reaches them.
2. **The consumer's clone cache must be refreshed.** The URL path reads
   `~/.bmad/cache/custom-modules/<host>/<owner>/<repo>/`. A cache cloned before the file was
   added still lacks it; `--action quick-update` re-fetches and re-runs manifest generation.
