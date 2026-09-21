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
npx --yes bmad-method install --yes --directory "$work" --modules bmm,bmb --tools claude-code \
  --shims < /dev/null

fail=0
pending=0
check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }
pending_check() { echo "  PENDING $1 -- $2"; pending=$((pending + 1)); }

echo "== baseline =="
check "core version matches the pinned baseline" \
  "grep -q \"version: $(jq -r .core_version "$pkg/skills/l3io-util-doctor/assets/bmad-baseline.json")\" _bmad/_config/manifest.yaml"

echo "== module contract =="
# l3io-pm-setup is Phase 2's module home for l3io-pm (plan Task 9); it does not exist yet at
# this point in the plan, so this copies whatever module homes are on disk today and leaves
# the rest to the state-derived check below instead of aborting the whole script on a missing
# directory.
for m in l3io-pm-setup l3io-util-doctor l3io-sec-redteam l3io-arch-review; do
  if [ -d "$pkg/skills/$m" ]; then
    cp -r "$pkg/skills/$m" ".claude/skills/$m"
  else
    echo "  note: skills/$m does not exist yet (created in a later phase task) -- skipping copy"
  fi
done
# The l3io-pm module's OTHER operational skills, copied alongside its home for the same
# reason a real plugin install would put them there: .claude-plugin/marketplace.json declares
# l3io-pm as one plugin covering all five of execute/plan/help/sync/setup, installed flat under
# .claude/skills/<name>/ as siblings of one another (never nested under the module home). Task
# 11A's Step 2 self-install depends on exactly this shape -- pm-execute/pm-plan/pm-sync read
# l3io-pm-setup's payload copy as `{skill-root}/../l3io-pm-setup/scripts/pm-status.py` -- so the
# claim only means something proven against a real install that actually has all five skills
# laid out this way, not just the module home copied in isolation.
for m in l3io-pm-execute l3io-pm-plan l3io-pm-help l3io-pm-sync; do
  if [ -d "$pkg/skills/$m" ]; then
    cp -r "$pkg/skills/$m" ".claude/skills/$m"
  else
    echo "  note: skills/$m does not exist yet -- skipping copy"
  fi
done
# State-derived, not hardcoded: whether the module contract has landed is read from the
# package's own tree (any skills/*/assets/module.yaml), the thing Phase 2 Task 7 creates by
# relocating module.yaml under assets/ -- never from a hand-kept "skip until Task 9" marker
# that someone has to remember to delete. Until that file exists anywhere in the package, the
# check can only ever fail (module.yaml still lives at each skill's root, and there is no
# *-setup/ directory for a multi-skill module either), so it reports PENDING and does not
# count against the exit code. Once Task 7 (and Task 9's l3io-pm-setup) land, this branch
# stops matching on its own and the same assertion below starts running for real, with no
# edit needed here.
#
# Do not point the validator at the bare .claude/skills/ install root even once module.yaml
# has landed: BMad's own bmad-bmb-setup directory lives there too, and find_setup_skill()
# matches the first "*-setup" directory it sees -- so the whole flat tree (every bmm/core/bmb
# skill plus the l3io ones just copied in) gets validated as if it were the bmb module,
# producing dozens of unrelated "missing capability entry" findings. Confirmed by hand against
# a real 6.12.0+bmb install.
if ls "$pkg"/skills/*/assets/module.yaml >/dev/null 2>&1; then
  check "validate-module.py passes for the package" \
    "uv run .claude/skills/bmad-module-builder/scripts/validate-module.py .claude/skills 2>/dev/null | grep -q '\"status\": \"pass\"'"
else
  pending_check "validate-module.py passes for the package" \
    "no skills/*/assets/module.yaml yet (Phase 2 Task 7 creates it); this check activates automatically once it lands"
fi

echo "== pm-status.py sibling path (Task 11A) =="
# Task 11A cut pm-status.py from four payload copies to two: pm-execute/pm-plan/pm-sync no
# longer carry their own, they read l3io-pm-setup's copy as a sibling
# ({skill-root}/../l3io-pm-setup/scripts/pm-status.py, step-00-activate.md Section 2). That
# claim is only trustworthy proven against a REAL install, not by reasoning about the
# marketplace manifest -- this is that proof, and it is why this section copied l3io-pm's
# other four skills above instead of just its module home.
if [ -d "$pkg/skills/l3io-pm-setup" ] && [ -d "$pkg/skills/l3io-pm-execute" ]; then
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
  check "l3io-pm-help still says it does not self-install pm-status.py" \
    "grep -q 'does not self-install' '$pkg/skills/l3io-pm-help/SKILL.md'"
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
