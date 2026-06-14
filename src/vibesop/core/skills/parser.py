"""Skill definition parser.

This module parses SKILL.md files and extracts metadata for routing.
It supports the frontmatter format used by VibeSOP skills.

Enhanced in v4.1.0 to support workflow parsing for external skill execution.
Updated in v5.5.0 to use SkillSpec (spec v3) internally.
Updated in v7.3.0: ``parse_skill_md()`` now returns ``SkillSpec`` directly;
the deprecated ``build_metadata()`` wrapper and ``SkillMetadata`` alias
were removed (ADR-004 Phase 3).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML, YAMLError

from vibesop.core.skills.workflow import Workflow, parse_workflow_from_markdown
from vibesop.spec.models import SkillSpec

logger = logging.getLogger(__name__)


def parse_skill_md(skill_path: Path) -> SkillSpec | None:
    """Parse a SKILL.md file and extract metadata using ruamel.yaml.

    Args:
        skill_path: Path to the skill directory or SKILL.md file

    Returns:
        SkillSpec if parsing succeeded, None otherwise
    """
    skill_file = skill_path if skill_path.is_file() else skill_path / "SKILL.md"
    if not skill_file.exists():
        return None

    skill_id = skill_file.parent.name if skill_path.is_file() else skill_path.name
    content = skill_file.read_text(encoding="utf-8")

    frontmatter, _ = extract_frontmatter(content)
    if frontmatter is None:
        return None

    return build_spec(frontmatter, skill_id, skill_file)


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


def build_spec(
    data: dict[str, Any],
    skill_id: str,
    skill_file: Path,
) -> "SkillSpec":
    """Build a SkillSpec from parsed frontmatter (spec v3 canonical path).

    Captures all 29 fields including the 12 previously discarded by build_metadata().
    This is the preferred path for new code.

    Args:
        data: Parsed YAML frontmatter dict.
        skill_id: Fallback skill ID (from directory name).
        skill_file: Path to the SKILL.md file (for source inference).

    Returns:
        SkillSpec with all available metadata.
    """
    from vibesop.spec.models import SkillSpec, SkillType as SpecSkillType, SkillLifecycle as SpecSkillLifecycle

    description = data.get("description", "")

    # Resolve type -- accept both 'type' and 'skill_type', spec v3 standardizes on 'type'
    skill_type_str = data.get("type") or data.get("skill_type") or "prompt"
    try:
        skill_type = SpecSkillType(skill_type_str)
    except ValueError:
        skill_type = SpecSkillType.PROMPT

    # tags and keywords are now separate concepts
    tags = _parse_list_field(data.get("tags"))
    keywords = _parse_list_field(data.get("keywords"))

    triggers = _parse_list_field(data.get("triggers"))

    trigger_when = data.get("trigger_when", "")
    if not trigger_when and not triggers and description:
        trigger_when = extract_trigger_from_description(description)

    # intent is optional; auto-derive only when None and only during routing (not parsing)
    intent = data.get("intent")

    algorithms = _parse_list_field(data.get("algorithms"))
    capabilities = _parse_list_field(data.get("capabilities"))

    # v3 fields that were previously discarded
    commands = _parse_list_field(data.get("commands"))
    user_invocable = bool(data.get("user_invocable", False))
    allowed_tools = _parse_list_field(data.get("allowed_tools") or data.get("allowed-tools"))
    mode = data.get("mode", "")
    routing_patterns = _parse_list_field(data.get("routing_patterns") or data.get("routing-patterns"))
    priority = int(data.get("priority", 50))
    category = str(data.get("category", "development"))
    dependencies = _parse_list_field(data.get("dependencies"))
    env_vars = _parse_list_field(data.get("env_vars") or data.get("env-vars"))
    deprecation_reason = data.get("deprecation_reason")

    # LLM config (v2 spec)
    llm_config = None
    if data.get("llm_config"):
        from vibesop.spec.models import LLMConfigSpec

        lc = data["llm_config"]
        if isinstance(lc, dict):
            llm_config = LLMConfigSpec(
                provider=lc.get("provider"),
                model=lc.get("model"),
                temperature=lc.get("temperature"),
                api_key=lc.get("api_key"),
                api_base=lc.get("api_base"),
                parameters=lc.get("parameters", {}),
                fallback=lc.get("fallback"),
            )

    # Source config (v2 spec)
    source_config = None
    if data.get("source_config"):
        from vibesop.spec.models import SourceConfigSpec

        sc = data["source_config"]
        if isinstance(sc, dict):
            source_config = SourceConfigSpec(
                type=sc.get("type", "github"),
                repository=sc.get("repository"),
                checksum=sc.get("checksum"),
                ref=sc.get("ref"),
            )

    source = infer_source(skill_file)

    # Lifecycle
    lifecycle_str = data.get("lifecycle", "active")
    try:
        lifecycle = SpecSkillLifecycle(lifecycle_str)
    except ValueError:
        lifecycle = SpecSkillLifecycle.ACTIVE

    return SkillSpec(
        id=data.get("id", skill_id),
        name=data.get("name", skill_id),
        description=description,
        version=data.get("version", "1.0.0"),
        author=data.get("author", ""),
        namespace=data.get("namespace", source),
        skill_type=skill_type,
        intent=intent,
        trigger_when=trigger_when,
        triggers=triggers,
        routing_patterns=routing_patterns,
        priority=priority,
        tags=tags,
        keywords=keywords,
        category=category,
        capabilities=capabilities,
        algorithms=algorithms,
        commands=commands,
        user_invocable=user_invocable,
        allowed_tools=allowed_tools,
        mode=mode,
        lifecycle=lifecycle,
        scope=str(data.get("scope", "global")),
        enabled=bool(data.get("enabled", True)),
        deprecation_reason=deprecation_reason,
        dependencies=dependencies,
        env_vars=env_vars,
        llm_config=llm_config,
        source_config=source_config,
        confidence=float(data.get("confidence", 0.5)),
        auto_configured=bool(data.get("auto_configured", False)),
        metadata=data.get("metadata", {}),
    )


def _parse_list_field(value: Any) -> list[str]:
    """Parse a frontmatter field that can be a list or comma-separated string."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return []


def build_metadata(
    data: dict[str, Any],
    skill_id: str,
    skill_file: Path,
) -> SkillSpec:
    """Build SkillSpec from parsed frontmatter.

    Canonical builder since v7.3.0 (ADR-004 Phase 3). Historically this
    function returned a deprecated ``SkillMetadata`` dataclass; it now
    returns ``SkillSpec`` directly. Callers that depended on the
    ``SkillMetadata`` shape should consume ``SkillSpec`` instead — it is
    a strict field superset.
    """
    return build_spec(data, skill_id, skill_file)


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
            # Truncate at newline to avoid pulling in multi-line YAML descriptions
            raw = match.group(1).strip().split("\n")[0]
            # Cap length to avoid matching entire descriptions that lack punctuation
            if len(raw) > 80:
                raw = raw[:80].rsplit(" ", 1)[0] + "..."
            return raw

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

    def parse_metadata(self, skill_path: Path) -> SkillSpec | None:
        """Parse skill metadata from SKILL.md file.

        Args:
            skill_path: Path to skill directory or SKILL.md file

        Returns:
            SkillSpec if parsing succeeded, None otherwise
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
    ) -> tuple[SkillSpec | None, Workflow | None]:
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
    "SkillParser",
    "build_metadata",
    "build_spec",
    "extract_frontmatter",
    "extract_trigger_from_description",
    "infer_skill_id",
    "infer_source",
    "parse_skill_md",
]
