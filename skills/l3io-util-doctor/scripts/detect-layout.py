#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
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
Exit 3 -- --classify only: the flat sprint-status.yaml carries BMad's `development_status:`
          mapping, not this package's `epics:` list. Deleting or migrating it as if it were
          ours would destroy the file bmad-sprint-planning, bmad-build and bmad-retrospective
          all read. argparse owns exit 2, which is why this is 3.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def classify_flat(path: Path) -> str:
    """Classify a flat sprint-status.yaml by its top-level schema.

    BMad's own file (bmad-sprint-planning/sprint-status-template.yaml) is a
    `development_status:` MAPPING of node-id -> status. This package's legacy flat
    file is an `epics:` LIST. They share this filename and default directory, so the
    discriminator must be the schema, never the path.

    Returns 'bmad', 'l3io', 'empty', or 'unreadable'. Never raises.
    """
    from ruamel.yaml import YAML
    from ruamel.yaml.error import YAMLError

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "unreadable"
    if not text.strip():
        return "empty"
    try:
        data = YAML(typ="safe").load(text)
    except YAMLError:
        return "unreadable"
    if not isinstance(data, dict):
        return "unreadable"
    if isinstance(data.get("development_status"), dict):
        return "bmad"
    if isinstance(data.get("epics"), list):
        return "l3io"
    return "unreadable"


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
    parser.add_argument(
        "--classify", action="store_true",
        help="classify the flat sprint-status.yaml by schema instead of checking for a collision",
    )
    args = parser.parse_args(argv)

    if args.classify:
        flat = Path(args.artifacts) / "sprint-status.yaml"
        if not flat.is_file():
            sys.stdout.write("flat-schema: absent\n")
            return 0
        schema = classify_flat(flat)
        sys.stdout.write(f"flat-schema: {schema}\n")
        return 3 if schema == "bmad" else 0

    code, message = detect(Path(args.artifacts))
    if message:
        sys.stdout.write(message)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
