#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
"""
bmad-deps.py -- verify the installed BMad skills against the declared inventory. Read-only.

Why this exists
---------------
Three BMad releases renamed or removed skills this package dispatches, and nothing noticed
until someone installed 6.12.0 by hand: bmad-create-story and bmad-dev-story became shims,
bmad-review-adversarial-general merged into bmad-review, and
bmad-check-implementation-readiness was removed. Separately every presence probe read
.claude/commands/ while 6.12.0 installs to .claude/skills/, so an installed reviewer looked
absent and its gate silently self-skipped -- a skipped gate is indistinguishable from a
passed one.

check:docs check 17 asserts the step files agree with the inventory, but CI has no BMad
install (_bmad/ is gitignored). This script is the other half: it compares the same inventory
against a real install. Single consumer (l3io-util-doctor), so it ships in doctor's own
scripts/ per ADR-0001, like audit-backlog.py, with no sync group.

Usage
-----
  bmad-deps.py verify --project-root R [--inventory PATH] [--format {text,json}]

Exit 0 when every required skill resolves (optional ones only warn), 2 on a usage error or an
unparseable inventory, 3 when a required skill resolves nowhere, 4 when the inventory or the
BMad manifest cannot be read.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

from ruamel.yaml import YAML

DEFAULT_INVENTORY = pathlib.Path(__file__).resolve().parent.parent / "assets" / "bmad-dependencies.json"


def resolve(name: str, project_root: str) -> str | None:
    """Return the path `name` resolves to, or None. Both layouts, both roots.

    6.12.0 installs skills/<name>/SKILL.md; earlier releases install commands/<name>.md.
    Probing only one layout mis-detects an installed skill as absent on the other version,
    which is how a gate came to self-skip silently -- so both are always tried, under the
    project root first and then the user's home.
    """
    roots = [os.path.join(project_root, ".claude"),
             os.path.join(os.path.expanduser("~"), ".claude")]
    for root in roots:
        for rel in (os.path.join("skills", name, "SKILL.md"), os.path.join("commands", f"{name}.md")):
            p = os.path.join(root, rel)
            if os.path.exists(p):
                return p
    return None


def read_manifest(project_root: str):
    """(version, shims_installed, [module names]) or None when unreadable.

    `installShims` exists only from 6.12.0 on, so it is read as absent-means-false: a
    KeyError here would crash on precisely the older install this script exists to protect.
    `modules` is a list of maps; a bare-string entry is skipped rather than fatal.
    """
    mf = os.path.join(project_root, "_bmad", "_config", "manifest.yaml")
    if not os.path.exists(mf):
        return None
    try:
        with open(mf, encoding="utf-8") as fh:
            data = YAML(typ="safe").load(fh) or {}
    except Exception:
        return None
    inst = data.get("installation") or {}
    mods = [m.get("name") for m in (data.get("modules") or []) if isinstance(m, dict)]
    return inst.get("version"), bool(inst.get("installShims", False)), mods


def verify(args: argparse.Namespace) -> int:
    # Unreadable and unparseable are different failures with different exit codes: 4 says
    # "I could not look", 2 says "I looked and the inventory is broken".
    try:
        text = pathlib.Path(args.inventory).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"cannot read inventory {args.inventory}: {exc}", file=sys.stderr)
        return 4
    try:
        inv = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"cannot parse inventory {args.inventory}: {exc}", file=sys.stderr)
        return 2
    man = read_manifest(args.project_root)
    if man is None:
        print(f"cannot read {args.project_root}/_bmad/_config/manifest.yaml — is BMad installed?",
              file=sys.stderr)
        return 4
    version, shims, modules = man

    resolved, missing, shims_in_use, warnings = [], [], [], []
    for e in inv.get("skills") or []:
        status = e.get("status")
        name = e.get("name")
        if status == "not-a-skill":
            continue
        if status == "removed":
            hit = resolve(name, args.project_root)
            if hit:
                shims_in_use.append({"name": name, "path": hit,
                                     "replaced_by": e.get("replaced_by")})
            continue
        hit, used = resolve(name, args.project_root), name
        if hit is None and e.get("fallback"):
            hit, used = resolve(e["fallback"], args.project_root), e["fallback"]
        if hit is None:
            (missing if status == "required" else warnings).append(name)
            continue
        resolved.append({"name": name, "status": status, "resolved_as": used, "path": hit})

    if args.format == "json":
        print(json.dumps({"bmad_version": version, "shims_installed": shims,
                          "modules": modules, "resolved": resolved,
                          "missing_required": missing, "optional_absent": warnings,
                          "shims_in_use": shims_in_use}, indent=2))
    else:
        print(f"BMad {version} — modules: {', '.join(str(m) for m in modules)}")
        for r in resolved:
            note = "" if r["resolved_as"] == r["name"] else f"  (via {r['resolved_as']})"
            print(f"  ok       {r['name']}{note}")
        for n in warnings:
            print(f"  absent   {n} (optional — its phase self-skips)")
        for s in shims_in_use:
            print(f"  shim     {s['name']} is a deprecated shim; {s['replaced_by']} replaces it")
        for n in missing:
            print(f"  MISSING  {n} (required)")
        if missing:
            # Flush first: unflushed stdout would otherwise let this summary surface ahead of
            # the report it summarizes whenever the two streams are captured separately.
            sys.stdout.flush()
            print(f"\n{len(missing)} required skill(s) resolve nowhere. Install them, or run "
                  f"`npx bmad-method install --modules bmm` to refresh.", file=sys.stderr)

    return 3 if missing else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bmad-deps.py", description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify", help="check the installed skills against the inventory")
    v.add_argument("--project-root", required=True)
    v.add_argument("--inventory", default=str(DEFAULT_INVENTORY))
    v.add_argument("--format", choices=("text", "json"), default="text")
    v.set_defaults(fn=verify)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
