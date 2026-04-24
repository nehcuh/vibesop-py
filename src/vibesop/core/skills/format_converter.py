"""SKILL.md format converter for external integrations.

This module provides converters to transform different SKILL.md formats
into the standardized VibeSOP format with YAML front matter.
"""

import re
from pathlib import Path
from typing import Any


class SkillFormatConverter:
    """Base class for SKILL.md format converters."""

    def can_convert(self, content: str) -> bool:
        """Check if this converter can handle the format.

        Args:
            content: SKILL.md file content

        Returns:
            True if this converter can handle the format
        """
        raise NotImplementedError

    def convert(self, content: str, _file_path: Path) -> tuple[str, dict[str, Any]]:
        """Convert content to standardized format.

        Args:
            content: Original SKILL.md content
            file_path: Path to the SKILL.md file

        Returns:
            Tuple of (converted_content, metadata_dict)
        """
        raise NotImplementedError

    def _parse_yaml_front_matter(self, content: str) -> dict[str, Any]:
        """Parse YAML front matter from content.

        Args:
            content: SKILL.md content with YAML front matter

        Returns:
            Dictionary of parsed fields
        """
        metadata = {}
        lines = content.split("\n")

        in_front_matter = False
        for line in lines:
            if line.strip() == "---":
                if in_front_matter:
                    break
                in_front_matter = True
                continue

            if in_front_matter and ":" in line:
                key, value = line.split(":", 1)
                metadata[key.strip()] = value.strip()

        return metadata


class GstackConverter(SkillFormatConverter):
    """Converter for gstack SKILL.md format.

    Gstack uses Markdown field format:
    **Skill ID**: `gstack/review`
    **Namespace**: builtin
    **Version**: 1.0.0
    """

    def can_convert(self, content: str) -> bool:
        """Check if content is in gstack format."""
        return "**Skill ID**:" in content or "**Skill ID**" in content

    def convert(self, content: str, file_path: Path) -> tuple[str, dict[str, Any]]:
        """Convert gstack format to standard format."""
        # Extract metadata from gstack format
        metadata = self._extract_gstack_metadata(content)

        # Try both "skill id" and "skill_id" as keys
        skill_id = metadata.get("skill_id") or metadata.get("skill id", "")
        description = self._extract_description(content)

        if not skill_id:
            # Fallback to directory name
            skill_id = file_path.parent.name

        # Parse skill_id to get name and namespace
        if "/" in skill_id:
            parts = skill_id.split("/", 1)
            namespace = parts[0]
            name = parts[1]
        else:
            namespace = "gstack"
            name = skill_id

        # Use the full skill_id if it already includes namespace
        full_id = skill_id if skill_id.startswith("gstack/") else f"gstack/{name}"

        # Infer intent from skill name or directory
        intent = self._infer_intent(name, file_path)

        # Build standardized metadata
        standard_metadata = {
            "id": full_id,
            "name": name,
            "description": description,
            "intent": intent,
            "namespace": namespace,
            "version": metadata.get("version") or metadata.get("Version", "1.0.0"),
            "type": "prompt",
        }

        # Build new content with YAML front matter
        yaml_front = self._build_yaml_front_matter(standard_metadata)
        new_content = f"{yaml_front}\n\n{content}"

        return new_content, standard_metadata

    def _extract_gstack_metadata(self, content: str) -> dict[str, str]:
        """Extract metadata from gstack format."""
        metadata = {}
        lines = content.split("\n")

        for line in lines[:30]:  # Only check first 30 lines
            # Match **Field**: `value` format
            match = re.match(r'\*\*([^*]+)\*\*:\s*`([^`]+)`', line)
            if match:
                key = match.group(1).strip().lower()
                value = match.group(2).strip()
                metadata[key] = value

        return metadata

    def _extract_description(self, content: str) -> str:
        """Extract description from gstack format."""
        lines = content.split("\n")

        # Description is usually in the first few lines after the title
        for i, line in enumerate(lines[1:10]):
            if line.strip().startswith(">"):
                # Multi-line description
                desc_lines = [line.strip().lstrip(">")]
                for j in range(i + 2, min(i + 5, len(lines))):
                    if lines[j].strip().startswith(">"):
                        desc_lines.append(lines[j].strip().lstrip(">"))
                    else:
                        break
                return " ".join(desc_lines).strip()

        return "No description"

    def _infer_intent(self, name: str, _file_path: Path) -> str:
        """Infer intent from skill name."""
        intent_map = {
            "review": "code-review",
            "qa": "testing",
            "investigate": "debugging",
            "browse": "testing",
            "office-hours": "brainstorming",
            "plan-ceo-review": "planning",
            "plan-eng-review": "planning",
            "plan-design-review": "design",
            "design-consultation": "design",
            "design-review": "design",
            "codex": "code-review",
            "ship": "deployment",
            "retro": "review",
            "careful": "safety",
            "freeze": "safety",
            "guard": "safety",
        }

        return intent_map.get(name, "general")

    def _build_yaml_front_matter(self, metadata: dict[str, str]) -> str:
        """Build YAML front matter from metadata."""
        lines = ["---"]
        for key, value in metadata.items():
            lines.append(f"{key}: {value}")
        lines.append("---")
        return "\n".join(lines)


class SuperpowersConverter(SkillFormatConverter):
    """Converter for superpowers SKILL.md format.

    Superpowers uses simplified YAML front matter:
    ---
    name: brainstorming
    description: "..."
    ---
    """

    def can_convert(self, content: str) -> bool:
        """Check if content is in superpowers format."""
        # Has YAML front matter but missing id field
        metadata = self._parse_yaml_front_matter(content)
        return "name" in metadata and "id" not in metadata

    def convert(self, content: str, _file_path: Path) -> tuple[str, dict[str, Any]]:
        """Convert superpowers format to standard format."""
        metadata = self._parse_yaml_front_matter(content)
        name = metadata.get("name", "")
        description = metadata.get("description", "No description")

        # Infer intent from skill name
        intent = self._infer_intent(name)

        # Build standardized metadata
        standard_metadata = {
            "id": f"superpowers/{name}",
            "name": name,
            "description": description,
            "intent": intent,
            "namespace": "superpowers",
            "version": metadata.get("version", "1.0.0"),
            "type": "prompt",
        }

        # Build new content with YAML front matter
        yaml_front = self._build_yaml_front_matter(standard_metadata)
        new_content = f"{yaml_front}\n\n{content}"

        return new_content, standard_metadata

    def _infer_intent(self, name: str) -> str:
        """Infer intent from skill name."""
        intent_map = {
            "brainstorming": "brainstorming",
            "test-driven-development": "testing",
            "refactor": "refactoring",
            "debugging": "debugging",
            "architect": "architecture",
            "systematic-debugging": "debugging",
            "review": "code-review",
            "optimizing": "optimization",
        }

        return intent_map.get(name, "general")

    def _build_yaml_front_matter(self, metadata: dict[str, str]) -> str:
        """Build YAML front matter from metadata."""
        lines = ["---"]
        for key, value in metadata.items():
            lines.append(f"{key}: {value}")
        lines.append("---")
        return "\n".join(lines)


class FormatConverterRegistry:
    """Registry for format converters."""

    def __init__(self) -> None:
        """Initialize converter registry."""
        self.converters: list[SkillFormatConverter] = [
            GstackConverter(),
            SuperpowersConverter(),
        ]

    def convert(self, content: str, file_path: Path) -> tuple[str, dict[str, Any]] | None:
        """Convert content using appropriate converter.

        Args:
            content: SKILL.md content
            file_path: Path to SKILL.md file

        Returns:
            Tuple of (converted_content, metadata) if converter found, None otherwise
        """
        for converter in self.converters:
            if converter.can_convert(content):
                return converter.convert(content, file_path)

        return None

    def can_convert(self, content: str) -> bool:
        """Check if any converter can handle this format.

        Args:
            content: SKILL.md content

        Returns:
            True if a converter is available
        """
        return any(converter.can_convert(content) for converter in self.converters)


__all__ = [
    "FormatConverterRegistry",
    "GstackConverter",
    "SkillFormatConverter",
    "SuperpowersConverter",
]
