#!/usr/bin/env bash
# Install BMad + this package into a throwaway directory and assert the module contract
# holds against a REAL install. CI cannot do this (no network guarantee, and _bmad/ is
# gitignored), so it runs at phase boundaries by hand. See ADR-0006: the 6.12 defects were
# found only by installing by hand and looking.
set -euo pipefail

work="${1:-$(mktemp -d)}"
pkg="$(cd "$(dirname "$0")/.." && pwd)"
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
# records why it is needed. Verified both ways: the constructed l3io-pm view returns
# `"status": "pass"` with zero findings, and the same run before assembly returns `fail`.
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
  check "validate-module.py passes for module '$plugin_name' (view built from marketplace.json)" \
    "uv run .claude/skills/bmad-module-builder/scripts/validate-module.py '$view' 2>/dev/null | grep -q '\"status\": \"pass\"'"
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
  check "l3io-pm-help carries no self-install invocation of its own" \
    "! grep -q 'pm-status\.py self-install' '$pkg/skills/l3io-pm-help/SKILL.md'"
else
  pending_check "pm-status.py sibling path (Task 11A)" \
    "skills/l3io-pm-setup or skills/l3io-pm-execute not present in this checkout"
fi

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
