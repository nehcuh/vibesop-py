"""Skill definition parser.

This module parses SKILL.md files and extracts metadata for routing.
It supports the frontmatter format used by VibeSOP skills.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SkillMetadata:
    """Metadata extracted from a SKILL.md file.

    Attributes:
        id: Skill identifier (directory name)
        name: Display name from frontmatter
        description: Short description from frontmatter
        keywords: Extracted keywords for matching
        triggers: Specific trigger phrases
        intent: High-level intent category
        path: Path to SKILL.md file
        source: Where this skill came from (builtin, project, external)
        version: Skill version
        author: Skill author
        namespace: Skill namespace
        skill_type: Type of skill (prompt, workflow, etc.)
        trigger_when: When to trigger this skill
    """

    id: str
    name: str
    description: str
    keywords: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    intent: str = ""
    path: Path | None = None
    source: str = "builtin"
    version: str = "1.0.0"
    author: str = ""
    namespace: str = "external"
    skill_type: str = "prompt"
    trigger_when: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for matcher consumption."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "keywords": self.keywords,
            "triggers": self.triggers,
            "intent": self.intent,
            "version": self.version,
            "author": self.author,
            "namespace": self.namespace,
            "skill_type": self.skill_type,
        }


class SkillParser:
    """Parser for SKILL.md files.

    Example:
        >>> parser = SkillParser()
        >>> metadata = parser.parse(Path("core/skills/debug/SKILL.md"))
        >>> print(metadata.name)  # "systematic-debugging"
    """

    # Frontmatter pattern
    FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

    # Keyword extraction patterns
    KEYWORD_PATTERNS = [
        r"\*\*([A-Z][A-Z_]+)\*\*",  # **KEYWORD** format
        r"`([A-Z][A-Z_]+)`",  # `KEYWORD` format
    ]

    def parse(self, skill_path: Path) -> SkillMetadata | None:
        """Parse a SKILL.md file and extract metadata.

        Args:
            skill_path: Path to the skill directory or SKILL.md file

        Returns:
            SkillMetadata if parsing succeeded, None otherwise
        """
        # Resolve path
        if skill_path.is_dir():
            skill_file = skill_path / "SKILL.md"
            skill_id = skill_path.name
        else:
            skill_file = skill_path
            skill_id = skill_path.parent.name

        if not skill_file.exists():
            return None

        content = skill_file.read_text()

        # Extract frontmatter
        frontmatter = self._extract_frontmatter(content)
        if not frontmatter:
            return None

        # Parse frontmatter
        metadata = SkillMetadata(
            id=skill_id,
            name=frontmatter.get("name", skill_id),
            description=frontmatter.get("description", ""),
            keywords=frontmatter.get("keywords", []),
            triggers=frontmatter.get("triggers", []),
            intent=frontmatter.get("intent", self._infer_intent(content)),
            path=skill_file,
            source=self._infer_source(skill_file),
        )

        # Auto-extract keywords if not provided
        if not metadata.keywords:
            metadata.keywords = self._extract_keywords(content)

        return metadata

    def _extract_frontmatter(self, content: str) -> dict[str, Any] | None:
        """Extract YAML frontmatter from content."""
        match = self.FRONTMATTER_PATTERN.match(content)
        if not match:
            return None

        frontmatter_text = match.group(1)

        # Simple YAML parsing (no external dependency for basic keys)
        frontmatter: dict[str, Any] = {}
        for line in frontmatter_text.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()

                # Handle different value types
                if value.startswith("[") and value.endswith("]"):
                    # List
                    value = [v.strip() for v in value[1:-1].split(",") if v.strip()]
                elif value.lower() in ("true", "yes"):
                    value = True
                elif value.lower() in ("false", "no"):
                    value = False

                frontmatter[key] = value

        return frontmatter

    def _extract_keywords(self, content: str) -> list[str]:
        """Extract keywords from skill content."""
        keywords = set()

        # Extract from headings
        for match in re.finditer(r"^#+\s*(.*?)$", content, re.MULTILINE):
            heading = match.group(1).strip()
            # Split heading into words
            words = re.findall(r"\b[A-Za-z][A-Za-z-]+\b", heading)
            keywords.update(words.lower() for words in words)

        # Extract from emphasized text
        for pattern in self.KEYWORD_PATTERNS:
            for match in re.finditer(pattern, content):
                keyword = match.group(1).lower()
                if len(keyword) > 2:  # Skip very short keywords
                    keywords.add(keyword)

        return sorted(keywords)

    def _infer_intent(self, content: str) -> str:
        """Infer intent category from content."""
        content_lower = content.lower()

        intent_keywords = {
            "debug": ["debug", "error", "bug", "fix", "issue", "problem"],
            "test": ["test", "testing", "coverage", "spec", "tdd"],
            "refactor": ["refactor", "clean", "simplify", "restructure"],
            "review": ["review", "audit", "check", "inspect"],
            "document": ["document", "doc", "readme", "comment"],
            "optimize": ["optimize", "performance", "speed", "efficient"],
            "plan": ["plan", "design", "architecture", "structure"],
        }

        for intent, keywords in intent_keywords.items():
            if any(kw in content_lower for kw in keywords):
                return intent

        return "general"

    def _infer_source(self, skill_path: Path) -> str:
        """Infer skill source from path."""
        path_str = str(skill_path)

        if "external" in path_str or ".claude/skills" in path_str:
            return "external"
        elif ".vibe/skills" in path_str or "project" in path_str:
            return "project"
        else:
            return "builtin"


# Convenience exports
__all__ = [
    "SkillMetadata",
    "SkillParser",
]
