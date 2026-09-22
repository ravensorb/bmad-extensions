#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
"""Print pm-status.py's REAL per-subcommand long-option surface, as JSON.

This is the external anchor for `pmStatusSubcommandOptions()` in scripts/check-docs.mjs.
That function extracts the same surface from `build_parser()`'s source with a regex, because
reaching argparse costs a ~223 ms `uv run` per checker invocation and check-docs.mjs is run
100+ times by its own test suite. Deriving a rule's scope internally is only safe when the
CONTENT is anchored against a second source of truth (ADR-0008, lesson 5) — this is it.

`scripts/tests/check-docs.test.mjs` runs this once, against the same pm-status.py the checker
reads, and asserts the two agree set-for-set in BOTH directions. A build_parser() shape the
regex cannot follow fails there rather than silently narrowing check 4.

Usage:  uv run scripts/tests/dump-pm-status-parser.py <path-to-pm-status.py>
"""

import importlib.util
import json
import sys


def main() -> int:
    if len(sys.argv) != 2:
        sys.stderr.write("usage: dump-pm-status-parser.py <path-to-pm-status.py>\n")
        return 2

    spec = importlib.util.spec_from_file_location("pm_status_under_test", sys.argv[1])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    parser = module.build_parser()
    out: dict[str, list[str]] = {}
    for action in parser._actions:
        # The subparsers action is the only one whose `choices` is a name -> parser mapping.
        if not isinstance(getattr(action, "choices", None), dict):
            continue
        for name, subparser in action.choices.items():
            options = {
                option
                for sub_action in subparser._actions
                for option in sub_action.option_strings
                if option.startswith("--")
            }
            out[name] = sorted(options)

    json.dump(out, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
