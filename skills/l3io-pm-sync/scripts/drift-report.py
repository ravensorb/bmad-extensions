#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""
Compute local drift for l3io-pm-sync — what has changed in BMad state files
since the last sync, without making any remote API calls.

Usage: uv run drift-report.py <project-root>

Output (stdout): JSON drift manifest
Errors (stderr): human-readable messages with non-zero exit code

The manifest contains:
  unmapped_local  — BMad entities not yet in sync-state (never pushed)
  changed_local   — entities whose current content hash differs from last_synced_hash
  missing_local   — sync-state entries with no corresponding BMad file (deleted locally)
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import yaml


CONFIG_FILE = "_bmad/config.yaml"
CONFIG_USER_FILE = "_bmad/config.user.yaml"
SYNC_CONFIG_FILE = "_bmad/sync-config.yaml"
SYNC_STATE_FILE = "_bmad/sync-state.yaml"

STATUS_FILES = [
    "sprint-status.yaml",
    "sprint-status-backlog.yaml",
    "sprint-status-archived.yaml",
]


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open() as f:
        return yaml.safe_load(f) or {}


def resolve_config(project_root: Path) -> dict:
    cfg = load_yaml(project_root / CONFIG_FILE)
    user_cfg = load_yaml(project_root / CONFIG_USER_FILE)
    cfg.update({k: v for k, v in user_cfg.items() if v is not None})

    output_folder = cfg.get("output_folder", str(project_root / "_bmad-output"))
    impl = cfg.get("implementation_artifacts") or f"{output_folder}/implementation-artifacts"
    return {"implementation_artifacts": impl}


def load_sync_state(project_root: Path) -> list[dict]:
    state = load_yaml(project_root / SYNC_STATE_FILE)
    return state.get("mappings", [])


def compute_hash(fields: dict) -> str:
    canonical = json.dumps(fields, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:8]


def extract_story_fields(story_path: Path, status: str, story_node: dict) -> dict:
    """Extract the fields that participate in drift detection from a story file and its status node."""
    title = ""
    description = ""
    ac = ""
    assignee = story_node.get("assignee", "")
    tags = sorted(story_node.get("tags", []) or [])

    if story_path.exists():
        content = story_path.read_text(encoding="utf-8")
        # Extract title from first H1
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()

        # Extract description: between H1 and ## Acceptance Criteria
        ac_match = re.search(r"^##\s+Acceptance Criteria", content, re.MULTILINE | re.IGNORECASE)
        h1_match = re.search(r"^#\s+.+$", content, re.MULTILINE)
        if h1_match and ac_match:
            start = h1_match.end()
            end = ac_match.start()
            description = content[start:end].strip()
        elif h1_match:
            description = content[h1_match.end():].strip()

        # Extract AC section
        if ac_match:
            ac_content = content[ac_match.end():]
            # Stop at next H2
            next_h2 = re.search(r"^##\s+", ac_content, re.MULTILINE)
            if next_h2:
                ac = ac_content[:next_h2.start()].strip()
            else:
                ac = ac_content.strip()

    estimate = story_node.get("estimate", {}) or {}
    return {
        "title": title.lower(),
        "description": description,
        "acceptance_criteria": ac,
        "status": status,
        "assignee": str(assignee).strip().lower(),
        "tags": tags,
        "estimates": {
            "time_hours_low": estimate.get("time_hours_low", 0),
            "time_hours_high": estimate.get("time_hours_high", 0),
        },
    }


def collect_bmad_entities(project_root: Path, impl_artifacts: str) -> list[dict]:
    """Walk sprint-status files and collect all stories, sprints, and epics."""
    impl_path = Path(impl_artifacts)
    entities = []

    for status_filename in STATUS_FILES:
        status_path = impl_path / status_filename
        if not status_path.exists():
            continue
        data = load_yaml(status_path)
        for epic in data.get("epics", []):
            epic_id = str(epic.get("id", "")).zfill(2)
            # Epic entity
            entities.append({
                "bmad_key": f"E{epic_id}",
                "bmad_type": "epic",
                "bmad_path": None,
                "fields": {
                    "title": (epic.get("title") or "").strip().lower(),
                    "status": epic.get("status", ""),
                    "goal": (epic.get("goal") or "").strip(),
                },
            })
            for sprint in epic.get("sprints", []):
                sprint_id = str(sprint.get("id", "")).zfill(2)
                # Sprint entity
                entities.append({
                    "bmad_key": f"E{epic_id}-S{sprint_id}",
                    "bmad_type": "sprint",
                    "bmad_path": None,
                    "fields": {
                        "title": (sprint.get("title") or "").strip().lower(),
                        "status": sprint.get("status", ""),
                    },
                })
                for story in sprint.get("stories", []):
                    story_key = story.get("key", "")
                    if not story_key:
                        continue
                    story_path = (
                        impl_path
                        / f"epic-{epic_id}"
                        / f"sprint-{sprint_id}"
                        / "stories"
                        / f"{story_key}.md"
                    )
                    fields = extract_story_fields(
                        story_path, story.get("status", ""), story
                    )
                    entities.append({
                        "bmad_key": story_key,
                        "bmad_type": "story",
                        "bmad_path": str(story_path.relative_to(project_root)),
                        "fields": fields,
                        "file_exists": story_path.exists(),
                    })

        # Backlog items
        for item in data.get("backlog", []):
            key = item.get("key", "")
            if key:
                entities.append({
                    "bmad_key": key,
                    "bmad_type": "backlog",
                    "bmad_path": None,
                    "fields": {
                        "title": (item.get("title") or "").strip().lower(),
                        "status": "backlog",
                    },
                })

    return entities


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="drift-report.py",
        description=(
            "Compute local drift for l3io-pm-sync. "
            "Reports BMad entities that are unmapped, changed, or missing since the last sync. "
            "Does not make remote API calls. Output: JSON drift manifest."
        ),
    )
    parser.add_argument(
        "project_root",
        help="Path to the project root containing _bmad/config.yaml and _bmad/sync-state.yaml",
    )
    args = parser.parse_args()
    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        print(f"ERROR: project-root not found: {project_root}", file=sys.stderr)
        return 1

    cfg = resolve_config(project_root)
    impl_artifacts = cfg["implementation_artifacts"]

    mappings = load_sync_state(project_root)
    mapped_keys = {m["bmad_key"]: m for m in mappings}

    entities = collect_bmad_entities(project_root, impl_artifacts)
    entity_keys = {e["bmad_key"] for e in entities}

    unmapped_local = []
    changed_local = []
    missing_local = []

    # Check each BMad entity against sync-state
    for entity in entities:
        key = entity["bmad_key"]
        current_hash = compute_hash(entity["fields"])

        if key not in mapped_keys:
            unmapped_local.append({
                "bmad_key": key,
                "bmad_type": entity["bmad_type"],
                "bmad_path": entity.get("bmad_path"),
                "current_hash": current_hash,
            })
        else:
            mapping = mapped_keys[key]
            last_hash = mapping.get("last_synced_hash", "")
            if current_hash != last_hash:
                changed_local.append({
                    "bmad_key": key,
                    "bmad_type": entity["bmad_type"],
                    "bmad_path": entity.get("bmad_path"),
                    "remote_id": mapping.get("remote_id"),
                    "remote_url": mapping.get("remote_url"),
                    "current_hash": current_hash,
                    "last_synced_hash": last_hash,
                    "last_synced_at": mapping.get("last_synced_at"),
                })

    # Check for sync-state entries with no corresponding BMad entity
    for mapping in mappings:
        key = mapping["bmad_key"]
        if key not in entity_keys:
            missing_local.append({
                "bmad_key": key,
                "bmad_type": mapping.get("bmad_type"),
                "bmad_path": mapping.get("bmad_path"),
                "remote_id": mapping.get("remote_id"),
                "remote_url": mapping.get("remote_url"),
                "last_synced_at": mapping.get("last_synced_at"),
            })

    report = {
        "implementation_artifacts": impl_artifacts,
        "total_entities": len(entities),
        "total_mapped": len(mappings),
        "unmapped_local": unmapped_local,
        "changed_local": changed_local,
        "missing_local": missing_local,
        "summary": {
            "unmapped": len(unmapped_local),
            "changed": len(changed_local),
            "missing": len(missing_local),
        },
    }

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
