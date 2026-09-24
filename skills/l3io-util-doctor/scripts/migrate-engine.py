#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
"""
migrate-engine.py -- the eight-step migration run.

    detect -> read -> resolve -> plan -> GATE -> write -> verify -> dispose

The gate sits BEFORE the write, and that position is the whole point. The previous prose
migration ran its completeness checks AFTER writing and before deleting the source, so a
parse that produced zero nodes passed every check vacuously and then `rm -f`'d a live
BMad tracking file while reporting success. A gate placed before the write cannot do
that, whatever the cause of the empty parse -- including causes nobody has met yet.

Steps 1-4 are read-only and safe to run at any time. Steps 5-8 run only under --apply.

Usage:
  migrate-engine.py --artifacts DIR --project-root DIR --plan [--format json|text]
  migrate-engine.py --artifacts DIR --project-root DIR --apply --state-root DIR \\
                    --pm-status PATH [--dispose]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_HERE, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sr = _load("state_record", "state-record.py")
detect_layout = _load("detect_layout", "detect-layout.py")
_l3io = _load("read_l3io_flat", "read-l3io-flat.py")
_bmad = _load("read_bmad_flat", "read-bmad-flat.py")
_per_epic = _load("read_per_epic", "read-per-epic.py")
_split = _load("read_split", "read-split.py")
_artifacts = _load("read_artifacts", "read-artifacts.py")

# Keyed by the fixture directory name. test-engine.py asserts this key set equals the
# directories on disk, so a deleted fixture fails the suite rather than shrinking the
# corpus silently.
READERS = {
    "l3io-flat": lambda art, root: _l3io.read(art / "sprint-status.yaml"),
    "bmad-flat": lambda art, root: _bmad.read(art / "sprint-status.yaml"),
    "per-epic": lambda art, root: _per_epic.read(root / "_bmad" / "state"),
    "split": lambda art, root: _split.read(art),
    "artifacts": lambda art, root: _artifacts.read(art),
}

_KIND_ORDER = ("epic", "sprint", "story")


def detect(artifacts_dir: Path, project_root: Path) -> str:
    """Name the source layout present, or 'none'.

    Order matters. The split layout is checked FIRST because a split project also carries
    sprint-status.yaml, so checking the flat file first would misread every split project.
    And the flat file's SCHEMA is what separates l3io-flat from bmad-flat -- never its
    path, which both share.
    """
    art, root = Path(artifacts_dir), Path(project_root)

    if (art / "sprint-status-backlog.yaml").is_file() or \
       (art / "sprint-status-archived.yaml").is_file():
        return "split"

    flat = art / "sprint-status.yaml"
    if flat.is_file():
        schema = detect_layout.classify_flat(flat)
        if schema == "bmad":
            return "bmad-flat"
        if schema == "l3io":
            return "l3io-flat"

    legacy = root / "_bmad" / "state"
    if legacy.is_dir() and any(legacy.glob("*.yaml")):
        return "per-epic"

    if art.is_dir() and any(art.glob("epic-*/sprint-*/stories/*.md")):
        return "artifacts"

    return "none"


def gather(layout: str, artifacts_dir: Path, project_root: Path) -> list:
    """Run the reader for `layout`. An unknown layout yields zero records."""
    reader = READERS.get(layout)
    if reader is None:
        return []
    return sr.dedupe(reader(Path(artifacts_dir), Path(project_root)))


def source_is_empty(layout: str, artifacts_dir: Path, project_root: Path) -> bool:
    """True when the source this layout names holds no bytes worth parsing.

    Distinguishes 'there was nothing to migrate' (fine) from 'there was something and we
    parsed none of it' (the gate's business).
    """
    art, root = Path(artifacts_dir), Path(project_root)
    if layout in ("l3io-flat", "bmad-flat"):
        candidates = [art / "sprint-status.yaml"]
    elif layout == "split":
        candidates = [art / n for n in _split.SPLIT_FILES]
    elif layout == "per-epic":
        candidates = sorted((root / "_bmad" / "state").glob("*.yaml"))
    elif layout == "artifacts":
        candidates = sorted(art.glob("epic-*/sprint-*/stories/*.md"))
    else:
        candidates = []
    for p in candidates:
        try:
            if p.is_file() and p.read_text(encoding="utf-8").strip():
                return False
        except OSError:
            continue
    return True


def build_plan(records: list) -> dict:
    """Order records parents-first and report counts plus validation problems.

    Parents first is a hard requirement, not a nicety: `import-node` exits 3 on a sprint
    whose epic directory does not exist yet.
    """
    ordered = sorted(
        records,
        key=lambda r: _KIND_ORDER.index(r["kind"])
        if r.get("kind") in _KIND_ORDER else len(_KIND_ORDER))
    counts = {k: 0 for k in _KIND_ORDER}
    problems = []
    for rec in ordered:
        for p in sr.validate(rec):
            problems.append(f"{rec.get('kind')} {rec.get('key')!r}: {p}")
        if rec.get("kind") in counts:
            counts[rec["kind"]] += 1
    return {"records": ordered, "counts": counts, "problems": problems}


def render_plan(layout: str, plan: dict) -> str:
    lines = [
        f"MIGRATION PLAN -- source layout: {layout}",
        "=" * 64,
        f"  epics   {plan['counts']['epic']:>4}",
        f"  sprints {plan['counts']['sprint']:>4}",
        f"  stories {plan['counts']['story']:>4}",
    ]
    inferred = [r for r in plan["records"] if r.get("origin") == "inferred"]
    if inferred:
        lines.append(f"  ({len(inferred)} node(s) inferred, marked origin: inferred)")
    if plan["problems"]:
        lines.append("")
        lines.append("PROBLEMS:")
        lines.extend(f"  - {p}" for p in plan["problems"])
    lines.append("=" * 64)
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="the doctor's migration engine")
    parser.add_argument("--artifacts", required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--plan", action="store_true", help="read-only: show the plan")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args(argv)

    art, root = Path(args.artifacts), Path(args.project_root)
    layout = detect(art, root)
    if layout == "none":
        sys.stdout.write("No migratable source layout found -- nothing to do.\n")
        return 0

    plan = build_plan(gather(layout, art, root))
    if args.format == "json":
        json.dump({"layout": layout, **plan}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_plan(layout, plan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
