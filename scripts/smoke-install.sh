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
