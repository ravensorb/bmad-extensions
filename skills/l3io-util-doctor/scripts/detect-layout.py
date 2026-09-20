#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# ///
"""
detect-layout.py -- detect a project holding both state layouts at once. Read-only.

Why this exists
----------------
`bmad-build` writes a flat `sprint-status.yaml` under the artifact root; this package's PM
skills read and write a sharded `state/` tree under the same root. Both default to the same
`{implementation_artifacts}` value, so a project can end up with both writers active at once,
each blind to the other's changes. `bmad-build` only writes the flat file when it already
exists (bmm's `step-03-implement.md:27`), so the collision is conditional -- once the flat
file is gone (migrated or deleted), the second writer stops on its own.

`migrate-state` resolves this by renaming the flat file to `sprint-status.yaml.legacy`, a name
this check does not match. Proving that a post-migration project reads clean -- not just that
a colliding one is flagged -- is the load-bearing case in this script's test suite: a detector
that still fires after the fix becomes permanent noise people learn to ignore.

A shell snippet inside a step file cannot be unit-tested, so the decision lives here and
`steps/health-check.md` only calls it and interprets the exit code.

Usage
-----
  detect-layout.py --artifacts DIR

Exit 0 -- no collision: only one layout present, neither present, or the flat file has
          already been migrated to its `.legacy` form.
Exit 1 -- both a flat sprint-status.yaml and a sharded state/ tree exist under DIR; prints a
          `layout-collision: ...` line naming both paths.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def detect(artifacts: Path) -> tuple[int, str]:
    """Return (exit_code, message). message is empty when there is no collision."""
    flat = artifacts / "sprint-status.yaml"
    sharded = artifacts / "state"
    if flat.is_file() and sharded.is_dir():
        return 1, f"layout-collision: both {flat} and {sharded}/ exist\n"
    return 0, ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifacts", required=True,
        help="{implementation_artifacts} directory to check for the flat file and state/ tree",
    )
    args = parser.parse_args(argv)

    code, message = detect(Path(args.artifacts))
    if message:
        sys.stdout.write(message)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
