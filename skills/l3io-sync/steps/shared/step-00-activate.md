# Step 00: Activate l3io-pm Module

Communicate all responses in `{communication_language}`.

This step runs first in every l3io-pm skill. Complete all actions in order before loading
any subsequent step file.

---

## 1. Load module configuration

Resolve config through BMad core's resolver — the full contract, including every
binding and its default, is `{skill-root}/references/config-resolution.md`:

```bash
uv run --python 3.11 {project-root}/_bmad/scripts/resolve_config.py --project-root {project-root}
```

If the resolver is missing or the command fails, BMad core is not installed in this
project: **BLOCKED** — tell the user to run the BMad installer. Do not write config
yourself and do not continue.

`modules.l3io-pm` being absent is **not** a first-run and **not** an error — it means the
module has no project-level overrides, which is the normal state. Bind the defaults below
and continue. This skill never loads module setup, regardless of argument —
`/l3io-setup` is the module's setup entry point.

Bind `{l3io_pm_section_absent}` = `true` when `modules.l3io-pm` is absent from the resolved
JSON, else `false`. This reuses the same resolved JSON already read above — it is not a second
resolve. It exists solely for the once-per-project setup-pointer check in `l3io-execute` and
`l3io-plan` (`config-resolution.md` §5) — not once per session: there is no cross-invocation
session identifier available, so a session-keyed check would fire on every invocation instead.
The pointer's only useful message is "you have not configured this," so it must say nothing
once a section exists. This flag is never a trigger for setup itself — no argument to this
skill triggers module setup; `/l3io-setup` is the module's setup entry point.

Extract and bind from the resolved JSON:
- `{communication_language}` — `core.communication_language` (default `English`)
- `{output_folder}` — `core.output_folder` (default `{project-root}/_bmad-output`)
- `{implementation_artifacts}` — `modules.l3io-pm.implementation_artifacts`
  (default `{output_folder}/implementation-artifacts`)
- `{planning_artifacts}` — `modules.l3io-pm.planning_artifacts`
  (default `{output_folder}/planning-artifacts`)
- `{model}` — `modules.l3io-pm.default_model` (default `claude-opus-5`). The model id every
  `cost` in this project is priced against. Pass it as `--model {model}` on `estimate-story`,
  `estimate-rollup`, and every `set-actual` that carries token counts. **Not optional** —
  leaving it unbound prices every estimate at `claude-opus-5` regardless of what the project
  actually runs on, and the same token volume prices ~2× apart between a $3/M and a $10/M
  input tier. An unknown id is a hard error, exit 2, never a silent fallback.
- `{model_story_simple}` — `modules.l3io-pm.model_story_simple` (default `{model}`). Model
  used when dispatching a story dev agent for a `classification: simple` story. Used as the
  `model:` binding in the dispatch context block and as `--model` on that story's `set-actual`.
- `{model_story_standard}` — `modules.l3io-pm.model_story_standard` (default `{model}`). Same
  for `classification: standard` stories.
- `{model_story_complex}` — `modules.l3io-pm.model_story_complex` (default `{model}`). Same
  for `classification: complex` stories.
- `{model_review}` — `modules.l3io-pm.model_review` (default `{model}`). Model used when
  dispatching `bmad-code-review` from the dev loop. Passed through dispatch context so the dev
  loop agent can use it when spawning the reviewer.
- `{model_prep}` — `modules.l3io-pm.model_prep` (default `{model}`). Model for sprint prep
  agents.
- `{model_closure}` — `modules.l3io-pm.model_closure` (default `{model}`). Model for sprint
  and epic closure agents.
- `{token_rates_json}` — `modules.l3io-pm.token_rates`, serialized to compact JSON; empty
  when the key is absent, which is the normal case (the shipped rate table applies). When it
  is **non-empty**, add `--token-rates '{token_rates_json}'` to `estimate-story`,
  `estimate-rollup`, `set-actual`, **and `verify`**; when it is empty, omit the flag
  entirely. Passing it to the writers but not to `verify` makes `verify` recompute `cost`
  against the shipped rates and fail every node the override priced. See
  `references/config-resolution.md` §3.
- Set `{pm_state_root}` = `{implementation_artifacts}/state`
- Set `{pm_issues_file}` = `{pm_state_root}/issues.yaml`
- Set `{pm_calibration_file}` = `{pm_state_root}/pm-calibration.yaml`

## 2. Install pm-status.py

`pm-status.py` ships once per module, not once per skill. For `l3io-pm` it lives at
`l3io-setup/scripts/pm-status.py` — the module's home — not here in this skill's own
`scripts/`. That is a module-home read, not the cross-skill path read `l3io-help/SKILL.md`
says it avoids for its own, unrelated staleness question: `.claude-plugin/marketplace.json`
declares the whole `l3io-pm` plugin — all five of its skills, including `l3io-setup` — as
one unit, and BMad's installer resolves and copies that unit as siblings under
`.claude/skills/`. `/l3io-setup` itself stays **optional**: nothing here requires the setup
skill to ever have been *run*, only installed beside this one.

**That co-installation is conditional, not absolute — say so plainly.** BMad's installer only
carries a skill into `.claude/skills/` and `_bmad/_config/skill-manifest.csv` when its
`SKILL.md` frontmatter strict-YAML-parses and its `name:` equals its directory name; a skill
that fails either test is silently dropped from the plugin, with no install-time warning. This
happened for real: `l3io-sync/SKILL.md`'s unquoted `Modes: …` line broke the parse and a
real install shipped only four of `l3io-pm`'s five skills until it was quoted (Task 11A fix
round 1; `check:docs`'s `skill-frontmatter` check now guards this mechanically going forward,
but a project on an older, unpatched copy of this package could still hit it).

First confirm the sibling payload is actually on disk — the manifest states the intent, but
only this on-disk check states the fact, whether the cause is the installer dropping the
skill or someone hand-copying a single skill directory out of the plugin (or shipping a
partial checkout). Either way the failure must name the missing piece rather than fail
silently or opaquely inside `uv run`:

```bash
test -f {skill-root}/../l3io-setup/scripts/pm-status.py
```

If absent, halt:
```
BLOCKED: l3io-setup/scripts/pm-status.py is missing beside this skill.
Check {project-root}/_bmad/_config/skill-manifest.csv for an l3io-setup row: if it is
missing, the installer rejected that skill (a SKILL.md frontmatter or naming defect) and
reinstalling the l3io-pm plugin will reproduce the same result until that is fixed upstream.
If the row IS present, a skill directory was likely hand-copied or the checkout is partial —
reinstalling the l3io-pm plugin resolves that case.
```

Self-install compares the installed copy's **bytes** against this one and reinstalls on any
difference, so a project pinned to a stale copy heals itself on the next run. It skips only a
byte-identical copy, and refuses to overwrite a strictly newer one. Pass `--force` to
reinstall regardless.

Self-install runs here — **before** layout detection — deliberately. Self-install is
layout-independent (it copies a file and needs no state), so nothing in detection depends on
it, and running it first guarantees a current script whichever branch detection takes below.
This also keeps an upgrading user from getting stuck on a stale installed copy: a legacy
layout blocks in section 3 and sends the user to `/l3io-doctor migrate-state`, and that
command needs a current `{pm_status}` to succeed — which this section guarantees regardless of
which layout branch section 3 takes.

```bash
uv run {skill-root}/../l3io-setup/scripts/pm-status.py self-install \
  --dest {project-root}/_bmad/scripts/pm-status.py
```

If `uv` is unavailable, use `python3` instead. A "skipped — already up to date"
message is normal. Failure here is BLOCKED.

Bind `{pm_status}` = `{project-root}/_bmad/scripts/pm-status.py` for use in all
subsequent steps.

Bind `{runtime}` — passed as `--runtime` to every `set-actual` and `verify` call
(`references/metrics-contract.md` §3). The value must be **exactly** one of `claude`,
`codex`, `copilot`, or `other` — `pm-status.py` rejects anything else with exit 2.
The criterion is a **capability**, not a brand check: choose the value whose token capture
procedure you can actually execute.

**Detection procedure:**

1. **`claude`** — bind when `$CLAUDE_CODE_SESSION_ID` is set in the environment. This is the
   Claude Code session identifier; its presence means the `pm-status.py usage` subcommand can
   read the session transcript to extract exact per-class token counts.

2. **`codex`** — bind when running inside Codex CLI and session JSONL files are available at
   `~/.codex/sessions/`. Confirmation: `ls ~/.codex/sessions/ 2>/dev/null | head -1` returns a
   session directory. Token capture reads `token_count` events from `rollout-*.jsonl`; sum
   `input_tokens`, `output_tokens` + `reasoning_output_tokens` (folded into output),
   and `cached_input_tokens` (→ `cache_read`); `cache_write` is `0` (Codex CLI drops this
   field — see metrics-contract.md §3).

3. **`copilot`** — bind when running inside a GitHub Copilot agent session (VS Code Copilot
   extension or Copilot Cloud Agent) where `$CLAUDE_CODE_SESSION_ID` is absent and Codex CLI
   session files are not present. Token capture sums `usage.prompt_tokens` (→ input) and
   `usage.completion_tokens` (→ output) across every API response in the node's dispatch
   window. No cache split is accessible; cost is recorded as N/A.

4. **`other`** — bind in all other cases, including when token data is genuinely not observable.
   Tokens and cost are recorded as N/A; `man_hours`, `hitl_hours`, and `elapsed_hours` are
   still required as real numbers.

**Default to `other` when uncertain** — it is the permissive value, allowing N/A for
tokens/cost. Guessing `claude` without transcript access, or `codex` without readable session
files, would either block every write (exit 2 on `--tokens-na`) or invite a fabricated number,
and both are worse than an honest N/A.

## 2.5. Verify the l3io-doctor sibling module is installed

`l3io-doctor` is a required intra-package module (CLAUDE.md "Dependencies") — the PM
skills forward migrations, health checks, and the plan-aware progress dashboard to it, and
`l3io-help` invokes `check-pm-status` on every activation. A standard install carries the
whole marketplace bundle so this is only false when someone has manually stripped the module.

The check probes the 6.12 (`.claude/skills/`) and pre-6.12 (`.claude/commands/`) layouts,
project-root first then user home. It looks under `.claude/` only; `bmad-deps.py`'s resolve()
also probes `.agents/`, but it cannot be used here because it *is* the doctor:

```bash
if   [ -f "{project-root}/.claude/skills/l3io-doctor/SKILL.md" ] \
  || [ -f "{project-root}/.claude/commands/l3io-doctor.md" ] \
  || [ -f "$HOME/.claude/skills/l3io-doctor/SKILL.md" ] \
  || [ -f "$HOME/.claude/commands/l3io-doctor.md" ]; then
  doctor=present
else
  doctor=absent
fi
```

**Warn but do not block.** This skill can complete without the doctor for its own core path;
the failure is deferred to whichever specific step tries to forward to it (`migrate-state`,
`bootstrap-state`, `check-pm-status`). Surfacing the warning up front turns "skill not found"
into a diagnosable install anomaly instead of a downstream mystery.

When `doctor=absent`, print exactly once at activation (do not repeat later):

```
⚠️  l3io-doctor is not installed — this is a required module of the LiquidLogicLabs
    extension. The marketplace bundle in .claude-plugin/marketplace.json ships it alongside
    l3io-pm, so this state is an install anomaly. Some steps below (state-layout migrations,
    the progress dashboard, and `check-pm-status`) will fail if reached. Reinstall
    the extension with `--modules ...,l3io-util,...` or reinstall the plugin bundle whole to
    restore it.
```

Continue to section 3 either way.

## 2.6. Offer the agent instruction block, once per harness

A project installed under one harness has no block in another harness's instruction file.
Check, and if the block is absent offer it **once ever, per harness**. This is **advisory and
never blocking**: it fires at activation, the user started this run for something else, and
interrupting it to ask about a documentation file is disproportionate. Print the offer and
continue. (The health check, `/l3io-doctor`, is the second surface, where interruption is
expected.) `{runtime}` is the value bound in section 2.

```bash
uv run {pm_status} sync-agent-instructions --runtime {runtime} \
  --project-root {project-root} --check
rc=$?
if [ "$rc" -eq 1 ]; then
  uv run {pm_status} notice --state-root {pm_state_root} --key ai-rules-missing:{runtime}
fi
```

`--check` is read-only and takes no lock. Act on its exit code:

- **0** — the block is present. Say nothing.
- **1** — absent. Run `notice`. When it exits 0, print one line and continue:
  `This project's {runtime} instruction file has no l3io block — an agent without it does not
  know project state is machine-written. Add it with /l3io-doctor (health check).`
  When `notice` exits 1 it has already been offered for this harness; say nothing. Keying per
  harness is the point — a single global key would mean the second harness is never asked.
- **2** — the file is not valid UTF-8, or its `l3io:begin`/`l3io:end` markers are ambiguous.
  **Do not offer to add a block, and never repair this on your own judgement.** The script
  refused precisely because it could not tell which marker was real, and picking one is the
  damage it exists to prevent.

  **Refusing to guess is not the same as refusing to help.** Deciding which block is right is
  the user's; finding the markers and splicing the lines is not, and handing that back gives
  them the easy half. So:

  1. **Show the ambiguity.** Name each `l3io:begin` and `l3io:end` with its line number and a
     few surrounding lines — "two `l3io:begin`, lines 42 and 118; the one at 42 has no
     matching end" — so they can see what they are choosing between. For invalid UTF-8, name
     the byte offset instead; there is nothing to choose, only to report.
  2. **Ask which reading is right.** The one question only a human can answer.
  3. **Make the edit yourself**, touching nothing outside the markers they resolved, and say
     what you changed.

  If they decline to choose, say so and continue — never edit on a guess, and never block the
  run. Print one line while unresolved —
  `⚠️  {runtime} instruction file could not be read for the l3io block (invalid UTF-8 or
  ambiguous markers). Tell me which block is current and I will fix it.` — and continue. This
  line is not recorded in the notice ledger, so it repeats until the file is fixed.
- Any other exit — say nothing and continue; a documentation probe never fails the run.

## 3. Detect state layout

Count how many of these three layouts are present — do **not** stop at the first match:

```bash
SHARDED=$([ -d "{implementation_artifacts}/state" ] && echo 1 || echo 0)
LEGACY_EPIC=$([ -d "{project-root}/_bmad/state" ] && echo 1 || echo 0)
LEGACY_FLAT=$([ -f "{implementation_artifacts}/sprint-status.yaml" ] && echo 1 || echo 0)
echo "sharded=$SHARDED legacy-per-epic=$LEGACY_EPIC legacy-flat=$LEGACY_FLAT"
```

**If more than one is 1** → an earlier migration died partway and left state in two places.
Guessing which is authoritative would fork the project's state, and a wrong guess deletes work,
so the only remedy here is one the evidence makes unambiguous
(`references/auto-remediation.md` is the contract; this is its one **conditional** row).

*When the evidence exists.* It exists for exactly one combination: `SHARDED` and `LEGACY_EPIC`
are 1 and `LEGACY_FLAT` is 0. A per-epic legacy tree names its epics in its entry names, so its
keys can be listed and compared. A flat `sprint-status.yaml` holds its epics inside one file
this step does not parse, so when `LEGACY_FLAT` is 1 there is nothing to compare: halt with the
**uncomparable** line below and remediate nothing.

*What is compared.* **Epic keys only.** A legacy tree holding an epic the sharded tree lacks is
the case that loses work, and it is what this comparison detects. Sprint or story divergence
*inside an epic key both trees share* is a different problem that this remedy does not claim to
solve: such a pair passes the comparison, so what it licenses is moving the legacy tree aside
(reversibly, below), not a judgment that the two copies of that epic agree.

```bash
LEG="{project-root}/_bmad/state"
LEGACY_KEYS=$(ls -A "$LEG" | grep -E '^(E|epic-)[0-9]{3}' | sed -E 's/^(E|epic-)([0-9]{3}).*/E\2/' | sort -u)
LEGACY_OTHER=$(ls -A "$LEG" | grep -vE '^(E|epic-)[0-9]{3}')
SHARDED_KEYS=$(ls -d {pm_state_root}/planned/epic-* {pm_state_root}/active/epic-* {pm_state_root}/archived/epic-* 2>/dev/null | sed -E 's|.*/epic-([0-9]+)$|E\1|' | sort -u)
ONLY_LEGACY=$(comm -23 <(printf '%s\n' "$LEGACY_KEYS" | sed '/^$/d') <(printf '%s\n' "$SHARDED_KEYS" | sed '/^$/d'))
```

*The rule.* The legacy keys must all be present in the sharded tree — `ONLY_LEGACY` empty **and**
`LEGACY_OTHER` empty. Sets that are equal qualify: a migration that copied every epic and died
before its cleanup leaves exactly equal sets, which is the commonest interrupted migration, and
nothing in the legacy tree is lost by moving it aside. A legacy entry that is not an epic key
(`LEGACY_OTHER`) is content this comparison cannot account for, so it fails the rule and is named
in the halt rather than ignored. Keys only in the sharded tree are expected after a migration
and do not fail it.

*The empty legacy tree is decided, not inherited.* An empty `_bmad/state/` (no entries at all,
hidden ones included) is vacuously a subset, and this step treats that as qualifying: an empty
leftover directory is the interrupted-migration case in its simplest form, there is nothing in it
to lose, and refusing it would halt every run forever over a directory that holds nothing. It is
backed up like any other, so the move is still reversible and still reported with its count of
zero.

**Qualifies** → remediate, once. Set `{layouts_reconciled}` = `true` **before** moving anything —
and if it is already `true`, this is a recurrence: go straight to the **Succeeded but persists**
halt below and run nothing. If `{project-root}/_bmad/state.superseded` already exists, do not
overwrite or merge into it: halt as **Failed** naming it. Print:
```
⚙  multiple state layouts detected; the legacy tree holds {n} epic(s), all present in the
   sharded tree — an interrupted migration that copied everything. Backing it up.
```
Move it aside with `mv {project-root}/_bmad/state {project-root}/_bmad/state.superseded` and
re-run the three-layout probe once. The sharded tree is never written, and moving the directory
back restores the original exactly. Three outcomes, and only the first continues:

- **Cleared** — only `SHARDED` is 1. Print
  `✓  moved _bmad/state to _bmad/state.superseded. Continuing on the sharded layout.`
  and continue to section 4.
- **Succeeded but persists** — the move reported success and the probe still finds more than one
  layout. Halt, naming what was tried:
```
BLOCKED: multiple state layouts detected (sharded=$SHARDED legacy-per-epic=$LEGACY_EPIC legacy-flat=$LEGACY_FLAT) and the layouts
persist. I moved _bmad/state to _bmad/state.superseded and the probe still finds more than one. This needs a decision.
```
- **Failed** — the move errored, or the destination already exists. Halt, reporting the original
  condition and the error; nothing was moved, so the legacy tree is as it was:
```
BLOCKED: multiple state layouts detected (sharded=$SHARDED legacy-per-epic=$LEGACY_EPIC legacy-flat=$LEGACY_FLAT) and I could not
back up the legacy tree: <its error>. Nothing was moved. This needs a decision.
```

**Does not qualify** (a legacy-only key, a legacy entry that is not an epic key) → halt, and print
which keys differ, so the user is not left to find the difference. Remediate nothing:
```
BLOCKED: multiple state layouts detected (sharded=$SHARDED legacy-per-epic=$LEGACY_EPIC legacy-flat=$LEGACY_FLAT) and they diverge,
so neither can be shown to be a copy of the other.
  only in legacy ({project-root}/_bmad/state): {ONLY_LEGACY}
  legacy entries that are not epic keys: {LEGACY_OTHER}
  only in sharded ({pm_state_root}): {keys in SHARDED_KEYS but not LEGACY_KEYS}
Guessing which is authoritative would fork the project's state. Inspect both and remove
the stale one, then re-run /l3io-doctor migrate-state.
```

**`LEGACY_FLAT` is 1** (uncomparable) → halt, remediating nothing:
```
BLOCKED: multiple state layouts detected (sharded=$SHARDED legacy-per-epic=$LEGACY_EPIC legacy-flat=$LEGACY_FLAT). An earlier migration
did not finish, and a flat sprint-status.yaml cannot be compared with another layout here. Do not run any l3io-pm skill until this is resolved — inspect both
locations and remove the stale one, then re-run /l3io-doctor migrate-state.
```

**If only sharded** → current layout. Continue to section 4.

**If only the legacy per-epic layout or only the legacy flat layout** → remediate, once
(`references/auto-remediation.md` is the contract). `{pm_status}` was just
self-installed in section 2, so `migrate-state` runs against a current copy, and it preserves the
original as `.legacy` — which is what makes this reversible. Set `{layout_migrated}` = `true`
**before** running it — and if it is already `true`, this is a recurrence: go straight to the
**Succeeded but persists** halt below and run nothing. Then print:
```
⚙  legacy state layout detected (per-epic = _bmad/state/, flat = sprint-status.yaml) — running /l3io-doctor migrate-state
```
Run `/l3io-doctor migrate-state`, then re-run the three-layout probe above once. Three outcomes,
and only the first continues:

- **Cleared** — only `SHARDED` is 1. Print
  `✓  migrated to the sharded layout; the original is kept as .legacy. Continuing activation.`
  and continue to section 4.
- **Succeeded but persists** — `migrate-state` reported success and the probe still finds a
  legacy layout or more than one layout. Halt, naming what was tried:
```
BLOCKED: legacy state layout — migrate required. I ran `/l3io-doctor migrate-state` and the layout
persists (sharded=$SHARDED legacy-per-epic=$LEGACY_EPIC legacy-flat=$LEGACY_FLAT). This needs a decision.
```
- **Failed** — `migrate-state` errored, including a write failure. Re-run the three-layout
  probe once and halt, reporting the legacy layout, the migration's own error and the layouts
  now present — a migration can fail after it has begun writing, so do not claim the original is
  untouched:
```
BLOCKED: legacy state layout — migrate required. `/l3io-doctor migrate-state` failed: <its error>.
Layouts now present: sharded=$SHARDED legacy-per-epic=$LEGACY_EPIC legacy-flat=$LEGACY_FLAT. Check them before re-running.
```

**If all three are 0** → possible first run. Before creating anything, rule out an orphan
caused by `implementation_artifacts` having been repointed:

```bash
git -C {project-root} ls-files -- '*/state/active/epic-*/epic.yaml' 'state/active/epic-*/epic.yaml' 2>/dev/null | head -5
find {project-root} -maxdepth 5 -type d -name active -path '*/state/*' 2>/dev/null | head -5
```

The second pathspec (`state/active/epic-*/epic.yaml`, no leading `*/`) catches the case where
`implementation_artifacts` equals `project-root`: git's fnmatch-pathname semantics require at
least one literal path segment before `state/`, so the first pathspec alone would miss a
root-level match.

If either prints a path that is not under `{implementation_artifacts}/state`, the found tree is
the real state and the configuration moved — so adopt it rather than start a blank project over
it (`references/auto-remediation.md` is the contract). Derive `{found}` as the
directory above the printed `state/`. If the printed paths name more than one distinct
`{found}`, there is no single tree to adopt: halt with the line below, listing them.

Otherwise remediate, once. If `{state_repointed}` is already `true`, this is a recurrence — the
repoint did not hold — so go straight to the persists halt and write nothing. Before writing,
capture `{configured}` = the current `{implementation_artifacts}`, and read
`{project-root}/_bmad/custom/config.user.toml`: it is the one layer merged after the file we
write, so a `modules.l3io-pm.implementation_artifacts` there would win over the repoint. If it
sets one, halt as **Succeeded but persists** now, naming that file, before writing anything.
Otherwise set `{state_repointed}` = `true` and print:
```
⚙  state found at {found} but implementation_artifacts resolves to {configured} — repointing
```
Then repoint implementation_artifacts in {project-root}/_bmad/custom/config.toml — this
package's own layer — under `[modules.l3io-pm]`, writing the previous value beside it as a
comment (`# was: {configured}`) so the change is revertible by inspection. Create
the file and section if absent; change no other key. Re-run the resolver from section 1 once.
Three outcomes, and only the first continues:

- **Cleared** — it now resolves to `{found}`. Re-bind `{implementation_artifacts}` and
  `{pm_state_root}` (`{configured}` keeps the old value), print
  `✓  implementation_artifacts = {found} (was {configured}). Continuing activation.`
  and re-run the three-layout probe above once before continuing.
- **Succeeded but persists** — the resolver still returns another value, or the overriding
  layer above was found before the write. Halt, naming the layer. If the write had landed, say
  so plainly: `custom/config.toml` now carries the repoint and a `# was:` comment, and the
  override still wins. Do not edit a layer the user owns.
- **Failed** — the write errored (permissions, a read-only checkout). Halt, reporting the
  original condition and the write error; the file is left as it was.

All three halts use this line:
```
BLOCKED: state found at <printed-path> but implementation_artifacts resolves to
{implementation_artifacts}. Did implementation_artifacts change? Refusing to start a
blank project over existing state. <what was tried and the result, or why no tree could be adopted>
```

If both print nothing → genuine first run. Continue to section 4.

## 4. Create state directories

```bash
mkdir -p {pm_state_root}/active {pm_state_root}/planned {pm_state_root}/archived
mkdir -p {planning_artifacts}
```

Verify the state root is not gitignored — this is what keeps state in version control:

```bash
git -C {project-root} check-ignore -q {pm_state_root} && echo IGNORED || echo TRACKED
```

If `IGNORED`, remediate, once (`references/auto-remediation.md` is the contract). If
`{gitignore_fixed}` is already `true`, this is a recurrence: halt as **Succeeded but persists**
and write nothing. **Locate the ignoring rule first** — the rule may be in any ignore source git
reads:

```bash
git -C {project-root} check-ignore -v {pm_state_root}
```

The output is `source:line:pattern`; the file holding the rule is the path before the first
colon. If it prints nothing while the probe said `IGNORED`, halt and change nothing:
```
BLOCKED: {pm_state_root} is gitignored. Project state must be committed, but I could not locate
the ignoring rule (`check-ignore -v` printed nothing), so I changed nothing.
```

**Edit only a real `.gitignore` inside this work tree.** Take the source path (relative to
`{project-root}` when git prints it so) and test it with these commands:

```bash
cd {project-root} && test -L <source> && echo SYMLINK
cd {project-root} && realpath <source>
cd {project-root} && realpath "$(git -C {project-root} rev-parse --show-toplevel)"
```

Every command runs from `{project-root}`, so a relative source names the file that will be
appended to. It qualifies only if all three hold: it is not a symlink (no `SYMLINK` printed); its
file name is `.gitignore`; and its `realpath` lies under the `realpath` of the toplevel,
comparing the two resolved values (never a resolved path against an unresolved one). "Under" is
a path-component test, not a string prefix: the source's real path must be the toplevel's real
path, then `/`, then at least one more component — in shell,
`case "$source_real" in "$top_real"/?*) ;; *) halt ;; esac` — and both values must be non-empty
first (halt if either is empty: an empty `$top_real` makes the pattern `/?*`, which matches every
absolute path) — so a sibling such as
`/home/u/repo-evil/.gitignore` does not pass for `/home/u/repo`. A symlinked `.gitignore`
halts even when its target resolves inside the tree: appending writes through the link to a file
the project does not own at the path it suggests, and whoever made the link did so deliberately.
Anything else halts and edits nothing: `.git/info/exclude`, a global excludes file
(`core.excludesFile`, typically `~/.config/git/ignore`), any path outside the repository, or a
symlink. Those are local, deliberate, user-owned rules; a negation there would reach nobody
else, mask a choice the user made, or change a file outside the project. Halt with the rule,
its file (for a symlink, the link and its target) and:
```
BLOCKED: {pm_state_root} is gitignored. Project state must be committed, but the rule is in
<file>, which is local to this machine or a symlink, so I did not edit it. Remove that rule, or negate it in
the project .gitignore:
  !{pm_state_root}/
  !{pm_state_root}/**
```

For a work-tree `.gitignore`: set `{gitignore_fixed}` = `true` **before** the write, print
`⚙  {pm_state_root} is gitignored by <rule> in <file> — appending negations`, then append
the two negation lines to the resolved path that passed the three conditions, and to nothing
re-derived from the raw `check-ignore -v` output:
```
!{pm_state_root}/
!{pm_state_root}/**
```
Re-run the `check-ignore -q` probe once. Three outcomes, and only the first continues:
- **Cleared** — prints `TRACKED`. Print
  `✓  appended two negation lines to <file>. Continuing activation.` and continue.
- **Succeeded but persists** — the write landed and the probe still prints `IGNORED` (a later
  rule re-ignores it). Halt, naming the file edited and the rule that still matches (run `check-ignore -v` again to read it).
- **Failed** — the write errored (permissions, a read-only checkout). Halt, reporting the
  original condition and the write error; nothing is half-applied.

Both persists and failed halts use this line, with what was found or tried after it:
```
BLOCKED: {pm_state_root} is gitignored. Project state must be committed. I appended the
negations and the rule persists, or the write failed — details follow.
```

## 5. List active epics

```bash
ls -d {pm_state_root}/active/epic-*/ 2>/dev/null || echo "(none)"
```

Bind `{active_epic_keys}` = the `E{nnn}` key for each directory found (`epic-001` → `E001`).
An empty list is valid on first run.

## 6. Verify schema of files this skill will touch (if any active epics exist)

If `{active_epic_keys}` is non-empty AND this skill is `l3io-execute` or `l3io-plan`,
run for each epic key in scope:

```bash
uv run {pm_status} verify --state-root {pm_state_root} --epic {epic_key} --scope epic
```

A FAIL result means the epic's files are corrupted. Halt with:
```
BLOCKED: schema verify failed for {epic_key} — investigate before continuing.
```

A PASS or "epic absent" result is fine.

## 7. Bind session ID

Generate and bind `{session_id}` — a stable unique identifier for this execution session
(e.g., `l3io-pm-{iso_timestamp}-{random_suffix}`). This value must remain constant for the
lifetime of this skill invocation and is used by set-lock / check-lock to identify the
owning session. Generate it once here; never regenerate it in later steps.

**Only an orchestrator generates one.** If your context block supplies `session_id`, that
value is the run's — bind it and do not mint another. Two ids for one run cannot be
reconciled afterwards: `events.jsonl` is append-only and the stamp is all there is.

## 8. Load the state and metrics digest

```
{skill-root}/steps/shared/step-00-digest.md
```

Load it now and keep it in context for the rest of this invocation. It carries the keys,
subcommand signatures, exit codes, the estimates-and-actuals HARD RULE, the `{agent_contract}`
binding, and a routing table to the reference section a given question needs.

It is a separate file so that a dispatched subagent — which inherits everything sections 1–7
established and must not redo it — can load the digest alone.

## 9. Output status line

```
Step 00 complete — state: {pm_state_root}, active epics: {count_of_active_epic_keys}, pm-status: installed, runtime: {runtime}
```
