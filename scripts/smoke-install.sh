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
check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }

echo "== baseline =="
check "core version matches the pinned baseline" \
  "grep -q \"version: $(jq -r .core_version "$pkg/skills/l3io-util-doctor/assets/bmad-baseline.json")\" _bmad/_config/manifest.yaml"

echo "== module contract =="
# l3io-pm-setup is Phase 2's module home for l3io-pm (plan Task 9); it does not exist yet at
# this point in the plan, so this copies whatever module homes are on disk today and leaves
# the rest to fail the check below cleanly instead of aborting the whole script on a missing
# directory -- the module-contract assertion is EXPECTED to be red until Phase 2 relocates
# module.yaml under assets/ (Task 7) and adds l3io-pm-setup (Task 9), exactly like Task 6A's
# check staying red until Task 7 makes it green. That is the real finding this step exists to
# surface, not a bug in this script.
for m in l3io-pm-setup l3io-util-doctor l3io-sec-redteam l3io-arch-review; do
  if [ -d "$pkg/skills/$m" ]; then
    cp -r "$pkg/skills/$m" ".claude/skills/$m"
  else
    echo "  note: skills/$m does not exist yet (created in a later phase task) -- skipping copy"
  fi
done
check "validate-module.py passes for the package" \
  "uv run .claude/skills/bmad-module-builder/scripts/validate-module.py .claude/skills 2>/dev/null | grep -q '\"status\": \"pass\"'"

echo "== install experience =="
check "no modules.l3io-pm section exists (absence is correct)" \
  "! grep -q 'modules.l3io-pm' _bmad/custom/config.toml 2>/dev/null"
check "the help index exists and the installer owns it" \
  "test -f _bmad/_config/bmad-help.csv"

echo "== dependency truth =="
check "no inventory claim contradicts the manifest" \
  "uv run -q --with 'ruamel.yaml>=0.18' python3 '$pkg/skills/l3io-util-doctor/scripts/bmad-deps.py' verify --project-root . --format json | jq -e '.status_contradictions == []' >/dev/null"

[ "$fail" -eq 0 ] && echo "smoke: PASS" || { echo "smoke: FAIL"; exit 1; }
