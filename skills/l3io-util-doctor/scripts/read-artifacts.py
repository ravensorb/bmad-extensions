#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
"""
read-artifacts.py -- derive records from story .md artifacts alone, for a project that
has stories but no status file.

This replaces the inline write_node() in steps/bootstrap-state.md, which assembled state
paths at six sites and wrote nodes directly -- bypassing the epic write lock, the event
log and status validation.

Stories are READ: each `{artifacts}/epic-XX/sprint-YY/stories/*.md` carries YAML
frontmatter with its key, title and status. Sprints and epics are INFERRED from the
directory structure the stories already sit in, and are marked `origin: inferred` with a
note, because nothing in the source states them -- the stories imply them by location.
Absence of `origin` means "read directly", which is why no schema version bump is needed.

Inference rule, stated ONCE and applied at both levels so they cannot drift:
    done        -- every child is done
    backlog     -- no child has started (all backlog or ready-for-dev)
    in-progress -- otherwise

Frontmatter is parsed as YAML, never by regex. A story with no parseable frontmatter, or
with a status this package does not recognise, is SKIPPED: guessing would feed calibration
a sample nobody measured.

Reader contract: pure. No writes, no refusal on an empty result.

Usage:  read-artifacts.py --dir PATH [--format json]
Exit 0 -- parsed (zero records is success)
Exit 1 -- the directory does not exist
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "state_record", os.path.join(_HERE, "state-record.py"))
sr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sr)

_EPIC_DIR = re.compile(r"^epic-(\d+)$")
_SPRINT_DIR = re.compile(r"^sprint-(\d+)$")

_NOT_STARTED = {"backlog", "ready-for-dev"}


def parse_frontmatter(text: str) -> dict:
    """Return the YAML frontmatter block as a dict, or {} when absent or malformed."""
    from ruamel.yaml import YAML
    from ruamel.yaml.error import YAMLError

    if not text.startswith("---"):
        return {}
    lines = text.splitlines()
    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break
    if end is None:
        return {}
    try:
        data = YAML(typ="safe").load("\n".join(lines[1:end]))
    except YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _roll_up(child_statuses: list) -> str:
    """One rule, used for both sprint-from-stories and epic-from-sprints."""
    if not child_statuses:
        return "backlog"
    if all(s == "done" for s in child_statuses):
        return "done"
    if all(s in _NOT_STARTED for s in child_statuses):
        return "backlog"
    return "in-progress"


def read(artifacts_dir: Path) -> list:
    """Derive records from a tree of story artifacts."""
    root = Path(artifacts_dir)
    if not root.is_dir():
        return []

    stories = []
    grouped = {}

    for epic_dir in sorted(root.iterdir()):
        m_epic = _EPIC_DIR.match(epic_dir.name) if epic_dir.is_dir() else None
        if not m_epic:
            continue
        epic_key = f"E{int(m_epic.group(1)):03d}"

        for sprint_dir in sorted(epic_dir.iterdir()):
            m_sprint = _SPRINT_DIR.match(sprint_dir.name) if sprint_dir.is_dir() else None
            if not m_sprint:
                continue
            sprint_num = int(m_sprint.group(1))
            sprint_key = f"{epic_key}-S{sprint_num:02d}"

            stories_dir = sprint_dir / "stories"
            if not stories_dir.is_dir():
                continue
            for md in sorted(stories_dir.glob("*.md")):
                try:
                    meta = parse_frontmatter(md.read_text(encoding="utf-8"))
                except OSError:
                    continue
                key = str(meta.get("key", "")).strip()
                status = str(meta.get("status", "")).strip()
                if not key or status not in sr.VALID_STATUS["story"]:
                    continue
                stories.append(sr.make_record(
                    "story", key, status, str(meta.get("title", "")),
                    str(md.relative_to(root)),
                    classification=str(meta.get("classification", "")).strip() or None,
                    extras=sr.collect_extras(meta)))
                grouped.setdefault((epic_key, sprint_key), []).append(status)

    if not stories:
        return []

    sprints = []
    by_epic = {}
    for (epic_key, sprint_key), statuses in sorted(grouped.items()):
        status = _roll_up(statuses)
        sprints.append(sr.make_record(
            "sprint", sprint_key, status, f"Sprint {sprint_key.split('-S')[1]}",
            f"{len(statuses)} story file(s) under {sprint_key}",
            origin="inferred",
            origin_note="derived from the story artifacts in this sprint directory"))
        by_epic.setdefault(epic_key, []).append(status)

    epics = []
    for epic_key, sprint_statuses in sorted(by_epic.items()):
        epics.append(sr.make_record(
            "epic", epic_key, _roll_up(sprint_statuses), "",
            f"{len(sprint_statuses)} sprint directory/ies under {epic_key}",
            origin="inferred",
            origin_note="derived from the sprint directories holding this epic's stories"))

    return sr.dedupe(epics + sprints + stories)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="derive records from story artifacts")
    parser.add_argument("--dir", required=True,
                        help="the implementation_artifacts directory")
    parser.add_argument("--format", choices=["json"], default="json")
    args = parser.parse_args(argv)

    d = Path(args.dir)
    if not d.is_dir():
        sys.stderr.write(f"read-artifacts.py: no such directory: {d}\n")
        return 1
    json.dump(read(d), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
