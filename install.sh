#!/usr/bin/env bash
# Install, upgrade, or remove this extension, with the correct BMad command for each.
#
# Why this exists
# ---------------
# The install and upgrade commands are not interchangeable, and getting that wrong has cost
# this estate real data. An upgrade is `--action quick-update`, which derives the module set
# and the IDE list off the existing install and deletes nothing. The first-install form takes
# `--modules` and `--tools`, both of which are AUTHORITATIVE rather than additive: BMad's
# installer `fs.remove`s every installed module `--modules` does not name, and runs
# `cleanupByList` over the target directories of every IDE `--tools` does not name. Neither
# asks for confirmation.
#
# Running the first-install form as an upgrade is survivable only by passing exactly the right
# flags. Two repos here were told to do that. One of them lost the per-module `config.yaml`
# for core, bmm, cis and tea -- files the `bmad-agent-*` skills read -- and got them back only
# because they happened to be committed. The fix is not better flags; it is not taking that
# path for an upgrade. This script encodes which command goes with which intent so nobody has
# to remember, and refuses the combinations that caused the damage.
#
# Where this script lives, and why
# --------------------------------
# The repository ROOT, deliberately not skill payload. A first install cannot come from
# payload -- there is no payload yet -- so the one entry point that has to work on an empty
# tree must be fetchable on its own. Being at the root also keeps the raw URL short enough to
# paste.
#
# Shell, and where it stops
# -------------------------
# `--clean` compares SHA-256 hashes against the per-skill `payload-manifest.json` files to
# decide what is safe to delete. That is JSON parsing plus hashing over a derived file set --
# data handling that has outgrown shell by this package's own standard
# (`standards-shell.md`, "Escalated to a real language if branching or data handling has
# outgrown shell"). So `--clean` dispatches to `clean-payload.py`, which IS payload: cleaning
# requires an install, and an install means that helper is already on disk. This script stays
# a dispatcher -- argument handling, install detection, and the two npx invocations.
set -euo pipefail

# Always the latest BMad release. `@latest` rather than a bare `bmad-method`, because a bare
# `npx` will happily reuse whatever it already cached -- this machine sat on 6.11.0 while the
# fleet ran 6.12.0, which is how a confident answer about the installer came from the wrong
# source. `@latest` resolves the dist-tag every time.
#
# `--bmad-version` exists for the deliberate exception -- bisecting an installer regression,
# or holding a repo back while something upstream is broken -- not as the default. Tracking
# latest means an upstream change reaches every repo on its next upgrade; that is the trade,
# and it is chosen.
BMAD_VERSION_DEFAULT="latest"
SOURCE_DEFAULT="https://github.com/ravensorb/bmad-extensions"
MODULES_DEFAULT="bmm"
TOOLS_DEFAULT="claude-code"

# Where the installer puts skills. Both are checked: an install writes them byte-identically,
# and a project may carry either.
SKILL_ROOTS=(".claude/skills/l3io-doctor" ".agents/skills/l3io-doctor")

action=""
directory="."
apply=0
modules="$MODULES_DEFAULT"
tools="$TOOLS_DEFAULT"
source_url="$SOURCE_DEFAULT"
bmad_version="$BMAD_VERSION_DEFAULT"
dry_run_requested=0

log() { printf '%s\n' "$*" >&2; }
die() {
    printf 'l3io-install: %s\n' "$*" >&2
    exit 2
}

usage() {
    cat <<'EOF'
Usage: l3io-install.sh --action {install|upgrade|clean} [options]

Actions
  --action upgrade   Refresh an EXISTING install. Runs BMad's `--action quick-update`,
                     which derives the module set and IDE list off the install itself,
                     preserves settings, and deletes nothing. Requires an install.
  --action install   FIRST install only. Refuses when BMad is already installed, because
                     the flags it must pass are authoritative and would delete modules
                     and IDE trees the flags do not name. Use --action upgrade instead.
  --action clean     Remove THIS extension's payload only, and nothing else. Reports what
                     it would do and changes nothing unless --apply is given. Never
                     touches project state under the artifacts tree. Requires an install.

Options
  --directory DIR    Project directory (default: .)
  --apply            For --clean: actually delete. Without it, --clean is a dry run.
  --modules LIST     First install only: official modules (default: bmm)
  --tools LIST       First install only: IDE codes, comma-separated (default: claude-code)
  --source URL       First install only: the extension repo (default: this package's)
  --bmad-version V   BMad release to invoke (default: latest). For a deliberate exception,
                     such as bisecting an installer regression -- not for routine use.
  -n, --dry-run      Print the command that would run, and run nothing.
  -h, --help         This text.

Why --install and --upgrade are separate, and why clean/upgrade require an install:
an upgrade on a tree with no install has nothing to derive its module set FROM, and a
clean has no manifest to decide what is safe to delete. Both would have to guess, and
both guesses are destructive.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --action)
            [[ $# -ge 2 ]] || die "--action needs a value: install, upgrade, or clean"
            action="$2"
            shift 2
            ;;
        --action=*)
            action="${1#*=}"
            shift
            ;;
        --directory)
            [[ $# -ge 2 ]] || die "--directory needs a value"
            directory="$2"
            shift 2
            ;;
        --directory=*)
            directory="${1#*=}"
            shift
            ;;
        --modules)
            [[ $# -ge 2 ]] || die "--modules needs a value"
            modules="$2"
            shift 2
            ;;
        --modules=*)
            modules="${1#*=}"
            shift
            ;;
        --tools)
            [[ $# -ge 2 ]] || die "--tools needs a value"
            tools="$2"
            shift 2
            ;;
        --tools=*)
            tools="${1#*=}"
            shift
            ;;
        --source)
            [[ $# -ge 2 ]] || die "--source needs a value"
            source_url="$2"
            shift 2
            ;;
        --source=*)
            source_url="${1#*=}"
            shift
            ;;
        --bmad-version)
            [[ $# -ge 2 ]] || die "--bmad-version needs a value"
            bmad_version="$2"
            shift 2
            ;;
        --bmad-version=*)
            bmad_version="${1#*=}"
            shift
            ;;
        --apply)
            apply=1
            shift
            ;;
        -n | --dry-run)
            dry_run_requested=1
            shift
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        *) die "unknown argument: $1 (try --help)" ;;
    esac
done

[[ -n "$action" ]] || {
    usage >&2
    die "--action is required; there is no safe default, because the right command depends on whether this project is already installed"
}

[[ -d "$directory" ]] || die "--directory $directory does not exist"
project="$(cd "$directory" && pwd -P)"

# Installed-ness is answered by the manifest, never by a config section: a module can be
# installed and unconfigured, and this is the file BMad itself writes to record an install.
manifest="$project/_bmad/_config/manifest.yaml"
installed=0
[[ -f "$manifest" ]] && installed=1

run() {
    if [[ "$dry_run_requested" -eq 1 ]]; then
        printf 'would run: %s\n' "$*"
        return 0
    fi
    log "+ $*"
    "$@"
}

case "$action" in
    upgrade)
        [[ "$installed" -eq 1 ]] || die "no BMad install found at $project (looked for _bmad/_config/manifest.yaml) -- an upgrade derives its module set from the existing install, so there is nothing to upgrade. Run --action install first."
        # No --modules and no --tools, deliberately. quick-update reads both off the install;
        # passing them would switch BMad to the authoritative path this script exists to avoid.
        run npx -y "bmad-method@${bmad_version}" install \
            --directory "$project" \
            --action quick-update \
            --yes
        ;;
    install)
        if [[ "$installed" -eq 1 ]]; then
            die "BMad is already installed at $project -- refusing. The first-install form passes --modules and --tools, which are authoritative: BMad deletes every installed module and every IDE tree they do not name, without confirming. Run --action upgrade instead, or pass --action install against a directory with no _bmad/."
        fi
        run npx -y "bmad-method@${bmad_version}" install \
            --directory "$project" \
            --custom-source "$source_url" \
            --modules "$modules" \
            --tools "$tools" \
            --yes
        ;;
    clean)
        [[ "$installed" -eq 1 ]] || die "no BMad install found at $project (looked for _bmad/_config/manifest.yaml) -- there is no payload manifest to decide what is safe to delete, and guessing is how an over-broad delete happens."
        # The helper is payload, so it is in the installed tree rather than beside this
        # script. That is sound because cleaning REQUIRES an install -- but if the payload is
        # already half-gone, say so plainly instead of failing on a missing path.
        helper=""
        for root in "${SKILL_ROOTS[@]}"; do
            if [[ -f "$project/$root/scripts/clean-payload.py" ]]; then
                helper="$project/$root/scripts/clean-payload.py"
                break
            fi
        done
        [[ -n "$helper" ]] || die "no clean-payload.py found under $project (looked in ${SKILL_ROOTS[*]}) -- this extension's payload is absent or already removed, so there is nothing to clean and nothing to decide it with."
        clean_args=(--project-root "$project")
        [[ "$apply" -eq 1 ]] && clean_args+=(--apply)
        if [[ "$dry_run_requested" -eq 1 ]]; then
            printf 'would run: uv run %s %s\n' "$helper" "${clean_args[*]}"
            exit 0
        fi
        # Not `exec`: the trailing advice below is part of the action's output.
        uv run "$helper" "${clean_args[@]}"
        if [[ "$apply" -eq 0 ]]; then
            log ""
            log "Nothing was changed. Re-run with --apply to delete what is listed above."
        fi
        ;;
    *) die "unknown --action: $action (expected install, upgrade, or clean)" ;;
esac
