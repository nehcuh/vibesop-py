"""Skill definition parser.

This module parses SKILL.md files and extracts metadata for routing.
It supports the frontmatter format used by VibeSOP skills.

Enhanced in v4.1.0 to support workflow parsing for external skill execution.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML, YAMLError

from vibesop.core.skills.base import SkillMetadata, SkillType
from vibesop.core.skills.workflow import Workflow, parse_workflow_from_markdown

logger = logging.getLogger(__name__)


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

    frontmatter, _ = extract_frontmatter(content)
    if frontmatter is None:
        return None

    return build_metadata(frontmatter, skill_id, skill_file)


def extract_frontmatter(content: str) -> tuple[dict[str, Any] | None, str]:
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
    except (YAMLError, ValueError, TypeError):
        return None, content


def build_metadata(
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
        trigger_when = extract_trigger_from_description(description)

    algorithms = data.get("algorithms") or []
    if isinstance(algorithms, str):
        algorithms = [a.strip() for a in algorithms.split(",") if a.strip()]

    source = infer_source(skill_file)

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


def extract_trigger_from_description(description: str) -> str:
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


def infer_source(skill_path: Path) -> str:
    """Infer skill source from path."""
    path_str = str(skill_path)
    if ".claude/skills" in path_str or ".config/skills" in path_str:
        return "external"
    if ".vibe/skills" in path_str:
        return "project"
    return "builtin"


def infer_skill_id(skill_path: Path) -> str:
    """Infer skill ID from SKILL.md path."""
    return skill_path.parent.name if skill_path.is_file() else skill_path.name


class SkillParser:
    """Enhanced skill parser with workflow support.

    This class provides parsing capabilities for both metadata extraction
    and workflow definition extraction from SKILL.md files.

    Example:
        >>> parser = SkillParser()
        >>> metadata = parser.parse_metadata(skill_path)
        >>> workflow = parser.parse_workflow(skill_path)
    """

    def __init__(self) -> None:
        """Initialize the skill parser."""
        self._yaml = YAML()

    def parse_metadata(self, skill_path: Path) -> SkillMetadata | None:
        """Parse skill metadata from SKILL.md file.

        Args:
            skill_path: Path to skill directory or SKILL.md file

        Returns:
            SkillMetadata if parsing succeeded, None otherwise
        """
        return parse_skill_md(skill_path)

    def parse_workflow(self, skill_path: Path) -> Workflow:
        """Parse workflow from SKILL.md file.

        This method extracts the workflow definition from a SKILL.md file,
        including steps, instructions, and metadata.

        Args:
            skill_path: Path to skill directory or SKILL.md file

        Returns:
            Parsed Workflow

        Raises:
            FileNotFoundError: If SKILL.md doesn't exist
            ValueError: If workflow cannot be parsed

        Example:
            >>> parser = SkillParser()
            >>> workflow = parser.parse_workflow(Path("skills/tdd/SKILL.md"))
            >>> print(f"Workflow: {workflow.name}")
            >>> for step in workflow.steps:
            ...     print(f"  - {step.description}")
        """
        skill_file = skill_path if skill_path.is_file() else skill_path / "SKILL.md"

        if not skill_file.exists():
            raise FileNotFoundError(f"SKILL.md not found: {skill_file}")

        skill_id = skill_file.parent.name if skill_path.is_file() else skill_path.name

        # Read file content
        try:
            content = skill_file.read_text(encoding="utf-8")
        except Exception as e:
            raise ValueError(f"Failed to read SKILL.md: {e}") from e

        # Parse workflow from markdown
        try:
            workflow = parse_workflow_from_markdown(content, skill_id)
            logger.debug(f"Parsed workflow for {skill_id}: {len(workflow.steps)} steps")
            return workflow
        except Exception as e:
            raise ValueError(f"Failed to parse workflow: {e}") from e

    def parse_skill_file(
        self,
        skill_path: Path,
    ) -> tuple[SkillMetadata | None, Workflow | None]:
        """Parse both metadata and workflow from SKILL.md file.

        Args:
            skill_path: Path to skill directory or SKILL.md file

        Returns:
            Tuple of (metadata, workflow). Either can be None if parsing fails.

        Example:
            >>> parser = SkillParser()
            >>> metadata, workflow = parser.parse_skill_file(Path("skills/tdd/SKILL.md"))
            >>> if metadata:
            ...     print(f"Skill: {metadata.name}")
            >>> if workflow:
            ...     print(f"Steps: {len(workflow.steps)}")
        """
        try:
            metadata = self.parse_metadata(skill_path)
        except Exception as e:
            logger.debug(f"Failed to parse metadata: {e}")
            metadata = None

        try:
            workflow = self.parse_workflow(skill_path)
        except Exception as e:
            logger.debug(f"Failed to parse workflow: {e}")
            workflow = None

        return metadata, workflow


__all__ = [
    "SkillMetadata",
    "SkillParser",
    "build_metadata",
    "extract_frontmatter",
    "extract_trigger_from_description",
    "infer_skill_id",
    "infer_source",
    "parse_skill_md",
]
