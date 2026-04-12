"""Skill definition parser.

This module parses SKILL.md files and extracts metadata for routing.
It supports the frontmatter format used by VibeSOP skills.
"""

from __future__ import annotations

import re
from pathlib import Path  # noqa: TC003
from typing import Any

from ruamel.yaml import YAML

from vibesop.core.skills.base import SkillMetadata, SkillType


def parse_skill_md(skill_path: Path) -> SkillMetadata | None:
    """Parse a SKILL.md file and extract metadata using ruamel.yaml.

    Args:
        skill_path: Path to the skill directory or SKILL.md file

    Returns:
        SkillMetadata if parsing succeeded, None otherwise
    """
    skill_file = skill_path if skill_path.is_file() else skill_path / "SKILL.md"
    if not skill_file.exists():
        return None

    skill_id = skill_file.parent.name if skill_path.is_file() else skill_path.name
    content = skill_file.read_text(encoding="utf-8")

    frontmatter, _ = _extract_frontmatter(content)
    if frontmatter is None:
        return None

    return _build_metadata(frontmatter, skill_id, skill_file)


def _extract_frontmatter(content: str) -> tuple[dict[str, Any] | None, str]:
    """Extract YAML frontmatter from markdown content.

    Returns:
        Tuple of (frontmatter dict, body content). If no valid frontmatter,
        returns (None, original content).
    """
    if not content.startswith("---"):
        return None, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return None, content

    yaml_text = parts[1]
    body = parts[2].strip()

    try:
        yaml_parser = YAML()
        data = yaml_parser.load(yaml_text)
        if not isinstance(data, dict):
            return None, content
        return data, body
    except Exception:
        return None, content


def _build_metadata(
    data: dict[str, Any],
    skill_id: str,
    skill_file: Path,
) -> SkillMetadata:
    """Build SkillMetadata from parsed frontmatter."""
    description = data.get("description", "")
    skill_type_str = data.get("type", "prompt")
    try:
        skill_type = SkillType(skill_type_str)
    except ValueError:
        skill_type = SkillType.PROMPT

    tags = data.get("tags") or data.get("keywords") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    triggers = data.get("triggers") or []
    if isinstance(triggers, str):
        triggers = [t.strip() for t in triggers.split(",") if t.strip()]

    trigger_when = data.get("trigger_when", "")
    if not trigger_when and description:
        trigger_when = _extract_trigger_from_description(description)

    algorithms = data.get("algorithms") or []
    if isinstance(algorithms, str):
        algorithms = [a.strip() for a in algorithms.split(",") if a.strip()]

    source = _infer_source(skill_file)

    return SkillMetadata(
        id=data.get("id", skill_id),
        name=data.get("name", skill_id),
        description=description,
        intent=data.get("intent", description),
        namespace=data.get("namespace", source),
        version=data.get("version", "1.0.0"),
        author=data.get("author", ""),
        tags=tags,
        skill_type=skill_type,
        trigger_when=trigger_when,
        algorithms=algorithms,
    )


def _extract_trigger_from_description(description: str) -> str:
    """Extract trigger conditions from skill description."""
    if not description:
        return ""

    patterns = [
        (r"Use when asked to ([^.]+)",),
        (r"Triggered when ([^.]+)",),
        (r"Auto-trigger on ([^.]+)",),
        (r"Proactively suggest when ([^.]+)",),
    ]

    for pattern in patterns:
        match = re.search(pattern[0], description, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return ""


def _infer_source(skill_path: Path) -> str:
    """Infer skill source from path."""
    path_str = str(skill_path)
    if ".claude/skills" in path_str or ".config/skills" in path_str:
        return "external"
    if ".vibe/skills" in path_str:
        return "project"
    return "builtin"


def _infer_skill_id(skill_path: Path) -> str:
    """Infer skill ID from SKILL.md path."""
    return skill_path.parent.name if skill_path.is_file() else skill_path.name


__all__ = [
    "SkillMetadata",
    "parse_skill_md",
]
