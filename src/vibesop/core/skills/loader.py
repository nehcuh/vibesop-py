"""Skill discovery and loading."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from vibesop.core.skills.base import (
    PromptSkill,
    Skill,
    SkillMetadata,
    SkillType,
    WorkflowSkill,
)


@dataclass
class SkillDefinition:
    """A skill definition loaded from a file.

    Attributes:
        metadata: Skill metadata
        content: Skill content (prompt template, workflow steps, etc.)
        source_file: Path to the source file
    """

    metadata: SkillMetadata
    content: str | dict[str, Any]
    source_file: Path | None = None


class SkillLoader:
    """Discover and load skills from the filesystem.

    Skills can be defined as:
    1. Markdown files with YAML frontmatter (.md)
    2. YAML files (.yaml, .yml)
    3. Python modules (.py)

    The loader discovers skills in:
    - {project_root}/skills/
    - {project_root}/.vibe/skills/
    - Built-in skills
    """

    def __init__(
        self,
        project_root: str | Path = ".",
        search_paths: list[str] | None = None,
    ) -> None:
        """Initialize the skill loader.

        Args:
            project_root: Project root directory
            search_paths: Additional paths to search for skills
        """
        self.project_root = Path(project_root).resolve()
        self._search_paths = self._default_search_paths()
        if search_paths:
            self._search_paths.extend(search_paths)

        self._skill_cache: dict[str, SkillDefinition] = {}

    def _default_search_paths(self) -> list[Path]:
        """Get default skill search paths.

        Returns:
            List of default search paths
        """
        return [
            self.project_root / "skills",
            self.project_root / ".vibe" / "skills",
        ]

    def discover_all(self, force_reload: bool = False) -> dict[str, SkillDefinition]:
        """Discover all available skills.

        Args:
            force_reload: Force rediscovery even if cached

        Returns:
            Dictionary mapping skill IDs to definitions
        """
        if self._skill_cache and not force_reload:
            return self._skill_cache

        self._skill_cache = {}

        for search_path in self._search_paths:
            if not search_path.exists():
                continue

            # Search for markdown files
            for md_file in search_path.rglob("*.md"):
                self._load_markdown_skill(md_file)

            # Search for YAML files
            for yaml_file in search_path.rglob("*.yaml"):
                self._load_yaml_skill(yaml_file)
            for yaml_file in search_path.rglob("*.yml"):
                self._load_yaml_skill(yaml_file)

        return self._skill_cache

    def get_skill(self, skill_id: str) -> SkillDefinition | None:
        """Get a skill definition by ID.

        Args:
            skill_id: Skill identifier

        Returns:
            Skill definition or None if not found
        """
        if not self._skill_cache:
            self.discover_all()

        return self._skill_cache.get(skill_id)

    def list_skills(
        self,
        namespace: str | None = None,
    ) -> list[SkillDefinition]:
        """List all discovered skills.

        Args:
            namespace: Optional namespace filter

        Returns:
            List of skill definitions
        """
        if not self._skill_cache:
            self.discover_all()

        skills = list(self._skill_cache.values())

        if namespace:
            skills = [s for s in skills if s.metadata.namespace == namespace]

        return skills

    def instantiate(self, skill_id: str) -> Skill | None:
        """Create a Skill instance from a definition.

        Args:
            skill_id: Skill identifier

        Returns:
            Skill instance or None if not found
        """
        definition = self.get_skill(skill_id)
        if not definition:
            return None

        metadata = definition.metadata

        match metadata.skill_type:
            case SkillType.PROMPT:
                if isinstance(definition.content, str):
                    return PromptSkill(
                        metadata=metadata,
                        prompt_template=definition.content,
                    )
                else:
                    return PromptSkill(
                        metadata=metadata,
                        prompt_template=definition.content.get("prompt", ""),
                        system_prompt=definition.content.get("system_prompt"),
                    )
            case SkillType.WORKFLOW:
                if isinstance(definition.content, dict):
                    steps = definition.content.get("steps", [])
                    return WorkflowSkill(metadata=metadata, steps=steps)
            case _:
                return None

        return None

    def _load_markdown_skill(self, file_path: Path) -> None:
        """Load a skill from a markdown file.

        Markdown files can have YAML frontmatter:
        ---
        id: gstack/review
        name: Code Review
        ...
        ---

        Prompt content here.

        Args:
            file_path: Path to markdown file
        """
        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return

        # Check for YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                body = parts[2].strip()

                try:
                    metadata_dict = yaml.safe_load(frontmatter)
                    if not isinstance(metadata_dict, dict):
                        return

                    metadata = self._parse_metadata(metadata_dict, file_path)

                    # Determine skill type from content or metadata
                    if metadata.skill_type == SkillType.WORKFLOW:
                        # Parse workflow from YAML content in body
                        try:
                            workflow = yaml.safe_load(body)
                            content = workflow if isinstance(workflow, dict) else body
                        except yaml.YAMLError:
                            content = body
                    else:
                        content = body

                    definition = SkillDefinition(
                        metadata=metadata,
                        content=content,
                        source_file=file_path,
                    )

                    self._skill_cache[metadata.id] = definition

                except yaml.YAMLError:
                    pass

    def _load_yaml_skill(self, file_path: Path) -> None:
        """Load a skill from a YAML file.

        Args:
            file_path: Path to YAML file
        """
        try:
            with file_path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not isinstance(data, dict):
                return

            # Extract metadata
            metadata = self._parse_metadata(data, file_path)

            # Remaining data is the content
            content = {k: v for k, v in data.items() if k not in self._metadata_keys()}

            definition = SkillDefinition(
                metadata=metadata,
                content=content,
                source_file=file_path,
            )

            self._skill_cache[metadata.id] = definition

        except (OSError, yaml.YAMLError):
            pass

    def _parse_metadata(
        self,
        data: dict[str, Any],
        source_file: Path | None = None,
    ) -> SkillMetadata:
        """Parse skill metadata from dictionary.

        Args:
            data: Metadata dictionary
            source_file: Optional source file path

        Returns:
            SkillMetadata instance
        """
        skill_id = data.get("id", self._generate_id_from_path(source_file))

        # Parse skill type
        skill_type_str = data.get("type", "prompt")
        try:
            skill_type = SkillType(skill_type_str)
        except ValueError:
            skill_type = SkillType.PROMPT

        return SkillMetadata(
            id=skill_id,
            name=data.get("name", skill_id),
            description=data.get("description", ""),
            intent=data.get("intent", data.get("description", "")),
            namespace=data.get("namespace", "project"),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            tags=data.get("tags"),
            skill_type=skill_type,
        )

    def _generate_id_from_path(self, path: Path | None) -> str:
        """Generate a skill ID from file path.

        Args:
            path: File path

        Returns:
            Generated skill ID
        """
        if not path:
            return "unknown/skill"

        # Use path relative to project root
        try:
            rel_path = path.relative_to(self.project_root)
        except ValueError:
            rel_path = path

        # Convert path to ID: skills/review.md -> review
        parts = rel_path.parts
        if parts[-1].endswith(".md"):
            name = parts[-1][:-3]
        elif parts[-1].endswith((".yaml", ".yml")):
            name = parts[-1][5:]
        else:
            name = parts[-1]

        if "skills" in parts:
            idx = parts.index("skills")
            if idx + 1 < len(parts):
                return f"project/{parts[idx + 1]}/{name}"

        return f"project/{name}"

    def _metadata_keys(self) -> set[str]:
        """Get keys that are part of metadata.

        Returns:
            Set of metadata key names
        """
        return {
            "id",
            "name",
            "description",
            "intent",
            "namespace",
            "version",
            "author",
            "tags",
            "type",
        }

    def clear_cache(self) -> None:
        """Clear the skill cache."""
        self._skill_cache = {}
