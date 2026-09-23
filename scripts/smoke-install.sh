#!/usr/bin/env bash
# Install BMad + this package into a throwaway directory and assert the module contract
# holds against a REAL install. CI cannot do this (no network guarantee, and _bmad/ is
# gitignored), so it runs at phase boundaries by hand. See ADR-0006: the 6.12 defects were
# found only by installing by hand and looking.
set -euo pipefail

work="${1:-$(mktemp -d)}"
pkg="$(cd "$(dirname "$0")/.." && pwd)"

# The workdir is validated explicitly, not left to `set -e` on the `cd` below.
#
# Three separate failure modes, all of which end with this script reporting on an install it
# never made:
#   - the directory does not exist. `set -e` does abort on that today (measured: EXIT=1 under
#     bash and `npm run`), but it is one edit away from not doing so -- a `cd "$work" || true`,
#     or this prologue moved into a function called from an `if`, disables `set -e` for it
#     silently. A guard that states the requirement cannot be switched off that way.
#   - the directory exists but is not writable. `cd` succeeds; the installer then fails deep
#     inside npx with an error that does not name the workdir.
#   - the path is RELATIVE. `cd` succeeds, but `$work` is used again AFTER the cd
#     (`view_root="$work/.smoke-module-views"`), so a relative path silently resolves a second
#     time against the new cwd and the module views are built in the wrong place.
# Resolving to an absolute path and asserting the three properties up front removes all three.
if [ ! -d "$work" ]; then
  echo "smoke: FAIL -- workdir '$work' does not exist (create it first, or pass no argument to get a mktemp -d)" >&2
  exit 2
fi
work="$(cd "$work" 2>/dev/null && pwd)" || {
  echo "smoke: FAIL -- workdir '$1' exists but could not be entered (permissions?)" >&2
  exit 2
}
if [ ! -w "$work" ]; then
  echo "smoke: FAIL -- workdir '$work' is not writable" >&2
  exit 2
fi
echo "smoke: workdir $work"
cd "$work"

# --directory is required for a genuinely unattended run: without it, the installer's
# "Installation directory" prompt still renders (and waits) even under --yes when stdin is
# not a real TTY, so cwd alone is not enough here. < /dev/null is a second belt-and-braces
# guard against the same class of hang. --shims matters for the dependency-truth check below:
# this package's inventory declares bmad-create-story/bmad-dev-story/bmad-review-adversarial-
# general "deprecated" (still on disk, as shims) -- true only when shims are installed, and
# BMad's installer omits them by default.
#
# --custom-source "$pkg" is what makes this a REAL install of THIS package, not a bare-BMad
# install with this package's skill directories `cp -r`'d in afterward. Task 11A fix round 1,
# M-1: a hand-copy loop can only ever prove the layout it just built -- it never exercises
# `ManifestGenerator.parseSkillMd()`, the exact code path that silently drops a skill whose
# SKILL.md frontmatter fails a strict YAML parse or whose `name:` disagrees with its directory
# name (H-1/H-2). `--custom-source` runs that real code path: `custom-module-manager.js` reads
# `.claude-plugin/marketplace.json`, `plugin-resolver.js` resolves each plugin's skill set from
# it, and only skills that clear `parseSkillMd()` reach `skill-manifest.csv` and
# `.claude/skills/`. That is the mechanism the checks below now measure, not simulate.
npx --yes bmad-method install --yes --directory "$work" --custom-source "$pkg" \
  --modules bmm,bmb --tools claude-code --shims < /dev/null

fail=0
pending=0
check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }
pending_check() { echo "  PENDING $1 -- $2"; pending=$((pending + 1)); }

echo "== baseline =="
check "core version matches the pinned baseline" \
  "grep -q \"version: $(jq -r .core_version "$pkg/skills/l3io-util-doctor/assets/bmad-baseline.json")\" _bmad/_config/manifest.yaml"

echo "== plugin skill delivery (marketplace.json) =="
# Task 11A fix round 1, M-1: the definitive empirical guard is that every skill
# .claude-plugin/marketplace.json declares actually landed in .claude/skills/ after a REAL
# install -- derived from the manifest's own `plugins[].skills` arrays, never a hand-kept
# list (per ruling-task9-validator-scope.md's prescription and the global rule against
# hand-enumerating scope that a source of truth already states). This is also the check that
# would have caught H-2: a skill whose SKILL.md frontmatter fails BMad's strict parse is
# declared here but does not land, and the loop below reports exactly that skill by name.
declared_skills=$(jq -r '.plugins[].skills[]' "$pkg/.claude-plugin/marketplace.json" | xargs -n1 basename)
# Fix round 2, N-4: a guard whose input set can silently become empty (a marketplace.json
# schema change, a jq path rename) is the exact shape this plan exists to remove -- an empty
# $declared_skills would make the loop below run zero times and this whole section pass in
# silence. Assert non-empty before trusting it.
declared_count=$(printf '%s\n' "$declared_skills" | grep -c . || true)
check "marketplace.json declares at least one skill (the derived set is not empty)" \
  "[ '$declared_count' -gt 0 ]"
for name in $declared_skills; do
  check "marketplace.json-declared skill '$name' landed in .claude/skills/" \
    "test -d '.claude/skills/$name'"
done

echo "== module contract =="
# One validator run PER MODULE, against a view built from marketplace.json's own
# plugins[].skills arrays -- never a hand-kept list. This replaces a single run against the
# bare .claude/skills/ install root, which could not pass and was reported as a permanent
# FAIL. Measured 2026-09-22 against a real install, which is where the reasons came from:
#
#   - validate-module.py assumes a module owns its own directory. In a real install nothing
#     does: every skill lands flat in .claude/skills/ beside all of bmm/core/bmb, and
#     _bmad/<code>/ holds only config.yaml and module-help.csv -- no skills at all.
#   - Pointed at .claude/skills/, find_skill_folders() (validate-module.py:44) claims every
#     sibling with a SKILL.md as part of whichever module it detected, so a real install
#     produced `"status": "fail"` with a missing-entry finding for every bmm/core/bmb skill.
#   - Pointed at skills/l3io-pm-setup alone, line 61's standalone test matches and the four
#     sibling skills its module-help.csv declares become `orphan-entry` findings.
#
# So the module has to be assembled before it can be validated. That is the closing move
# ruling-task9-validator-scope.md wrote up and left unimplemented; ADR-0008 Decision 7
# records why it is needed. Verified both ways: the constructed view is the only one the
# validator can read at all, and the same run before assembly returns a structural `fail`.
#
# The verdict is NOT the validator's own `"status"`, and this comment used to say it was
# ("returns `"status": "pass"` with zero findings"). That stopped being true on 2026-09-23,
# when the package adopted the `_meta` row and cross-module `skill:action` relationships --
# two conventions bmad-help documents and BMad's own modules ship, and validate-module.py
# implements neither. The findings are real output about a tool gap, not about these CSVs;
# BMad's own `bmm` module-help.csv produces the identical four `_meta` findings when put in
# the shape the validator accepts. So the run is piped through
# scripts/check-module-view.mjs, which exempts exactly those two classes, evidenced against
# the module's own CSV, and FAILS on anything else -- a stricter bar than `status`, which
# tolerates a `medium`. Its header states each exemption and the condition that switches it
# off; scripts/tests/check-module-view.test.mjs attacks all four. Nothing here is a blanket
# "ignore findings": plant a real orphan, a duplicate menu code or a broken intra-module ref
# and this goes red.
#
# The `|| true` is on the VALIDATOR, not on the judgement: validate-module.py exits non-zero
# whenever it reports `fail`, and `set -o pipefail` would otherwise fail the pipeline before
# the filter got to decide. The filter itself fails closed on empty or unparseable input, so
# suppressing the exit code cannot turn a crash into a pass.
view_root="$work/.smoke-module-views"
rm -rf "$view_root"
mkdir -p "$view_root"
plugin_count=$(jq -r '.plugins | length' "$pkg/.claude-plugin/marketplace.json")
# Same non-empty guard as the delivery section: a jq path rename would otherwise make this
# whole section pass by running zero times.
check "marketplace.json declares at least one plugin (the derived set is not empty)" \
  "[ '$plugin_count' -gt 0 ]"
for i in $(seq 0 $((plugin_count - 1))); do
  plugin_name=$(jq -r ".plugins[$i].name" "$pkg/.claude-plugin/marketplace.json")
  view="$view_root/$plugin_name"
  mkdir -p "$view"
  for skill in $(jq -r ".plugins[$i].skills[]" "$pkg/.claude-plugin/marketplace.json" | xargs -n1 basename); do
    cp -r ".claude/skills/$skill" "$view/$skill"
  done
  check "validate-module.py reports nothing outside its two known gaps for module '$plugin_name' (view built from marketplace.json)" \
    "{ uv run .claude/skills/bmad-module-builder/scripts/validate-module.py '$view' 2>/dev/null || true; } \
       | node '$pkg/scripts/check-module-view.mjs' '$view'"
done

echo "== pm-status.py sibling path (Task 11A) =="
# Task 11A cut pm-status.py from four payload copies to two: pm-execute/pm-plan/pm-sync no
# longer carry their own, they read l3io-pm-setup's copy as a sibling
# ({skill-root}/../l3io-pm-setup/scripts/pm-status.py, step-00-activate.md Section 2). This is
# checked against the tree the REAL install above produced under .claude/skills/ -- not a
# hand-copied stand-in (Task 11A fix round 1, M-1): if the installer had dropped
# l3io-pm-setup (as it silently did for l3io-pm-sync before H-2's fix), the "declared skill
# landed" loop above would already have failed by name, and the `test -d` guard below would
# also correctly find it absent rather than asserting a layout this script built itself.
if [ -d ".claude/skills/l3io-pm-setup" ] && [ -d ".claude/skills/l3io-pm-execute" ]; then
  sibling=".claude/skills/l3io-pm-execute/../l3io-pm-setup/scripts/pm-status.py"

  check "the sibling path resolves from a real install" \
    "test -f '$sibling'"
  check "the installed copy is runnable via its own shebang (not just present)" \
    "uv run '$sibling' --help >/dev/null 2>&1"
  check "self-install from the sibling path produces a runnable installed copy" \
    "rm -rf _bmad-smoke-dest && mkdir -p _bmad-smoke-dest && \
     uv run '$sibling' self-install --dest \"\$PWD/_bmad-smoke-dest/pm-status.py\" >/dev/null && \
     uv run \"\$PWD/_bmad-smoke-dest/pm-status.py\" --help >/dev/null"

  # Requirement 2: a missing sibling must fail loudly and name l3io-pm-setup, never skip
  # silently -- simulate exactly the hand-copy-one-skill-directory failure mode by hiding the
  # module home and re-running the same guard command step-00-activate.md Section 2
  # documents (`test -f {skill-root}/../l3io-pm-setup/scripts/pm-status.py`).
  mv ".claude/skills/l3io-pm-setup" ".claude/skills/l3io-pm-setup.hidden"
  check "a hand-copied single skill directory makes the sibling guard fail (not silently skip)" \
    "! test -f '$sibling'"
  check "step-00-activate.md's BLOCKED message names l3io-pm-setup by name" \
    "grep -q 'l3io-pm-setup/scripts/pm-status.py is missing beside this skill' \
       '$pkg/skills/l3io-pm-execute/steps/shared/step-00-activate.md'"
  mv ".claude/skills/l3io-pm-setup.hidden" ".claude/skills/l3io-pm-setup"

  # Requirement 3: l3io-pm-help's existing "only reads, does not self-install" precedent must
  # stay true -- it must not have gained a sibling self-install invocation of its own. It is
  # allowed (and expected) to keep saying, in prose, that it does not self-install; what must
  # never appear is an actual `pm-status.py self-install` command.
  # Searched across the whole skill, not one named file. This assertion read SKILL.md alone
  # and went FAIL the moment Task 12 split l3io-pm-help into a router plus steps/: the
  # sentence moved to steps/step-01-config.md byte-for-byte unchanged, and a check that
  # pinned its location broke on text that had not changed. Smoke is not a CI gate, so the
  # failure sat unnoticed from that split until this task re-ran it. Same lesson as
  # ADR-0008's "moving text unchanged can break it".
  check "l3io-pm-help still says it does not self-install pm-status.py" \
    "grep -rq 'does not self-install' '$pkg/skills/l3io-pm-help/'"
  # Its negative twin, and it needs the same reach for the same reason: after Task 12's split
  # the subject matter lives in steps/step-01-config.md, so a self-install invocation appended
  # THERE satisfied a SKILL.md-only grep and left check:docs green too. Broadening the positive
  # assertion above while leaving this one pinned to a file would have checked that the skill
  # still says the right thing without checking that it still does the right thing.
  # Both spellings, not just the literal path form. Every real self-install in this package
  # runs from a payload copy (`uv run {skill-root}/scripts/pm-status.py self-install …`), so
  # the path form is the one that occurs -- but a future author writing `{pm_status}
  # self-install` would be making exactly the mistake this assertion exists to catch, and the
  # old pattern could not see it. Verified by planting both spellings in steps/.
  check "l3io-pm-help carries no self-install invocation of its own" \
    "! grep -rqE '(pm-status\.py|\{pm_status\}) self-install' '$pkg/skills/l3io-pm-help/'"
else
  pending_check "pm-status.py sibling path (Task 11A)" \
    "skills/l3io-pm-setup or skills/l3io-pm-execute not present in this checkout"
fi

echo "== config layer (the path every skill runs first) =="
# M-1 from the whole-branch review, and the gap that let C-1 ship: this script asserted 22
# things about an install whose _bmad/config.toml BMad's own resolver refused to parse, because
# nothing here ever ran the resolver. The nearest assertion (the `modules.l3io-pm` grep below)
# reads _bmad/custom/config.toml -- a DIFFERENT file from the generated _bmad/config.toml that
# held the duplicate table. Every l3io skill and every BMad core skill resolves config through
# resolve_config.py at activation, and references/config-resolution.md §4 tells a skill that
# gets a failure to stop and report "BMad core is not installed" -- which would be false. So
# the resolver itself is the assertion.
check "resolve_config.py parses the installed config layer and exits 0" \
  "uv run _bmad/scripts/resolve_config.py --project-root . >/dev/null 2>&1"

# The direct guard on C-1's mechanism, independent of which keys any module happens to declare:
# TOML forbids declaring the same table twice, and writeCentralConfig has no dedupe -- it emits
# one [modules.<sectionKey>] per installed module, so two modules resolving to the same
# module.yaml (and therefore the same `code`) produce a byte-invalid file.
dup_count=$(grep -oE '^\[(modules|agents)\.[^]]+\]' _bmad/config.toml 2>/dev/null | sort | uniq -d | grep -c . || true)
check "no [modules.*] or [agents.*] table is declared twice in _bmad/config.toml" \
  "[ '$dup_count' -eq 0 ]"

# Every install-time setting a module declares must land under THAT module's code. The pairs
# come from scripts/module-config-keys.mjs, which derives them from each module's own
# assets/module.yaml -- never a hand-kept list (CLAUDE.md rule 4). A module that declares no
# install-time setting contributes no pair and is correctly not asserted about.
resolved_json="$work/.smoke-resolved-config.json"
uv run _bmad/scripts/resolve_config.py --project-root . > "$resolved_json" 2>/dev/null || echo '{}' > "$resolved_json"
expected_pairs="$(node "$pkg/scripts/module-config-keys.mjs" --root "$pkg")"
expected_count=$(printf '%s\n' "$expected_pairs" | grep -c . || true)
# Same non-empty guard as the sections above (fix round 2, N-4): a derived set that silently
# became empty would make the loop below run zero times and pass in silence.
check "at least one module declares an install-time setting (the derived set is not empty)" \
  "[ '$expected_count' -gt 0 ]"
while read -r code key; do
  [ -n "$code" ] || continue
  check "resolved config carries modules.$code.$key (filed under its OWN module code)" \
    "jq -e --arg c '$code' --arg k '$key' '.modules[\$c][\$k] != null' '$resolved_json' >/dev/null"
done <<EOF
$expected_pairs
EOF

echo "== install experience =="
check "no modules.l3io-pm section exists (absence is correct)" \
  "! grep -q 'modules.l3io-pm' _bmad/custom/config.toml 2>/dev/null"
check "the help index exists and the installer owns it" \
  "test -f _bmad/_config/bmad-help.csv"

echo "== dependency truth =="
check "no inventory claim contradicts the manifest" \
  "uv run -q --with 'ruamel.yaml>=0.18' python3 '$pkg/skills/l3io-util-doctor/scripts/bmad-deps.py' verify --project-root . --format json | jq -e '.status_contradictions == []' >/dev/null"

if [ "$fail" -eq 0 ]; then
  [ "$pending" -eq 0 ] && echo "smoke: PASS" || echo "smoke: PASS ($pending pending)"
else
  echo "smoke: FAIL"; exit 1
fi
