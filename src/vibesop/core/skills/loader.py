# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportMissingTypeArgument=false, reportUnknownParameterType=false
"""Skill discovery and loading.

This module provides unified skill loading from both project-local skills
and external skill packs (superpowers, gstack, etc.).
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence
from typing import Any

from ruamel.yaml import YAML

from vibesop.core.skills import parser as skill_parser
from vibesop.core.skills.base import (
    PromptSkill,
    Skill,
    SkillMetadata,
    SkillType,
    WorkflowSkill,
)
from vibesop.core.skills.external_loader import ExternalSkillLoader

logger = logging.getLogger(__name__)


@dataclass
class LoadedSkill:
    """A skill definition loaded from a file.

    Attributes:
        metadata: Skill metadata
        content: Skill content (prompt template, workflow steps, etc.)
        source_file: Path to the source file
        external_metadata: External skill metadata (if from external pack)
    """

    metadata: SkillMetadata
    content: str | dict[str, Any]
    source_file: Path | None = None
    external_metadata: Any = None  # ExternalSkillMetadata if from external pack


class SkillLoader:
    """Discover and load skills from the filesystem.

    Skills can be defined as:
    1. Markdown files with YAML frontmatter (.md)
    2. YAML files (.yaml, .yml)
    3. Python modules (.py)

    The loader discovers skills in:
    - {project_root}/skills/
    - {project_root}/.vibe/skills/
    - ~/.claude/skills/ (Claude Code skills)
    - ~/.config/skills/ (External skill packs)
    - Built-in skills
    """

    def __init__(
        self,
        project_root: str | Path = ".",
        search_paths: Sequence[str | Path] | None = None,
        enable_external: bool = True,
        require_audit: bool = True,
    ) -> None:
        """Initialize the skill loader.

        Args:
            project_root: Project root directory
            search_paths: Additional paths to search for skills
            enable_external: Whether to load external skills from ~/.claude/skills/
            require_audit: Whether to require security audit for external skills
        """
        self.project_root = Path(project_root).resolve()
        self._search_paths = self._default_search_paths()
        if search_paths:
            self._search_paths.extend([Path(p) for p in search_paths])

        self._skill_cache: dict[str, LoadedSkill] = {}
        self._enable_external = enable_external
        self._require_audit = require_audit
        self._external_loader: ExternalSkillLoader | None = None

        # Initialize external loader if enabled
        if enable_external:
            self._external_loader = ExternalSkillLoader(
                require_audit=require_audit,
                project_root=self.project_root,
            )

    def _default_search_paths(self) -> list[Path]:
        """Get default skill search paths.

        Returns:
            List of default search paths
        """
        return [
            self.project_root / "skills",
            self.project_root / ".vibe" / "skills",
        ]

    def discover_all(self, force_reload: bool = False) -> dict[str, LoadedSkill]:
        """Discover all available skills.

        Args:
            force_reload: Force rediscovery even if cached

        Returns:
            Dictionary mapping skill IDs to definitions
        """
        if self._skill_cache and not force_reload:
            return self._skill_cache

        self._skill_cache = {}

        # Load project-local skills
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

        # Load external skills from packs (superpowers, gstack, etc.)
        if self._enable_external and self._external_loader:
            self._load_external_skills()

        return self._skill_cache

    def _load_external_skills(self) -> None:
        """Load skills from external packs.

        Discovers skills from ~/.claude/skills/, ~/.config/skills/, etc.
        Only loads skills that pass security audit.
        """
        if not self._external_loader:
            return

        # Discover all external skills
        external_skills = self._external_loader.discover_all()

        for skill_id, ext_metadata in external_skills.items():
            # Skip if already loaded (project-local takes precedence)
            if skill_id in self._skill_cache:
                continue

            # Check if safe to load
            if self._require_audit and not ext_metadata.is_safe:
                continue

            # Convert external metadata to internal format
            definition = self._convert_external_skill(ext_metadata)
            if definition:
                self._skill_cache[skill_id] = definition

    def _convert_external_skill(self, ext_metadata: Any) -> LoadedSkill | None:
        """Convert external skill metadata to internal LoadedSkill.

        Args:
            ext_metadata: ExternalSkillMetadata from ExternalSkillLoader

        Returns:
            LoadedSkill or None if conversion failed
        """
        from vibesop.core.skills.external_loader import ExternalSkillMetadata

        if not isinstance(ext_metadata, ExternalSkillMetadata):
            return None

        base = ext_metadata.base_metadata

        # Build skill ID with namespace
        skill_id = f"{ext_metadata.pack_name}/{base.id}" if ext_metadata.pack_name else base.id

        # Convert skill type string to enum
        skill_type_str = getattr(base, "skill_type", "prompt")
        try:
            skill_type = SkillType(skill_type_str)
        except ValueError:
            skill_type = SkillType.PROMPT

        # Create metadata
        metadata = SkillMetadata(
            id=skill_id,
            name=base.name,
            description=base.description,
            intent=base.intent or base.description,
            namespace=ext_metadata.pack_name or "external",
            version=getattr(base, "version", "1.0.0"),
            author=getattr(base, "author", ""),
            tags=getattr(base, "tags", None),
            skill_type=skill_type,
            trigger_when=getattr(base, "trigger_when", ""),
            algorithms=getattr(base, "algorithms", None),
        )
        self._validate_algorithms(metadata)

        # Read skill content from source file
        content = ""
        if ext_metadata.install_path:
            skill_file = ext_metadata.install_path / "SKILL.md"
            if skill_file.exists():
                try:
                    content = skill_file.read_text(encoding="utf-8")
                    # Parse to extract just the content (after frontmatter)
                    if content.startswith("---"):
                        parts = content.split("---", 2)
                        if len(parts) >= 3:
                            content = parts[2].strip()
                except (OSError, UnicodeDecodeError):
                    pass

        return LoadedSkill(
            metadata=metadata,
            content=content,
            source_file=ext_metadata.install_path / "SKILL.md"
            if ext_metadata.install_path
            else None,
            external_metadata=ext_metadata,
        )

    def get_skill(self, skill_id: str) -> LoadedSkill | None:
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
    ) -> list[LoadedSkill]:
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
        """Load a skill from a markdown file."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return

        frontmatter, body = skill_parser.extract_frontmatter(content)
        if frontmatter is None:
            return

        try:
            metadata = skill_parser.build_metadata(
                frontmatter,
                skill_parser.infer_skill_id(file_path),
                file_path,
            )

            # Determine skill type from content or metadata
            skill_content: str | dict[str, Any] = body
            if metadata.skill_type == SkillType.WORKFLOW:
                try:
                    yaml_parser = YAML()
                    workflow = yaml_parser.load(body)
                    skill_content = workflow if isinstance(workflow, dict) else body
                except Exception as e:
                    logger.debug(f"Failed to parse workflow YAML in {file_path.name}: {e}")

            self._validate_algorithms(metadata)
            definition = LoadedSkill(
                metadata=metadata,
                content=skill_content,
                source_file=file_path,
            )
            self._skill_cache[metadata.id] = definition
        except Exception as e:
            logger.debug(f"Failed to load skill from {file_path}: {e}")

    def _load_yaml_skill(self, file_path: Path) -> None:
        """Load a skill from a YAML file."""
        try:
            yaml_parser = YAML()
            with file_path.open("r", encoding="utf-8") as f:
                data = yaml_parser.load(f)

            if not isinstance(data, dict):
                return

            metadata = skill_parser.build_metadata(
                data,
                self._generate_id_from_path(file_path),
                file_path,
            )
            content = {k: v for k, v in data.items() if k not in self._metadata_keys()}

            self._validate_algorithms(metadata)
            definition = LoadedSkill(
                metadata=metadata,
                content=content,
                source_file=file_path,
            )
            self._skill_cache[metadata.id] = definition

        except (OSError, Exception):
            pass

    def _validate_algorithms(self, metadata: SkillMetadata) -> None:
        """Warn if a skill declares algorithms that are not registered."""
        if not metadata.algorithms:
            return
        from vibesop.core.algorithms import AlgorithmRegistry

        for algo in metadata.algorithms:
            if not AlgorithmRegistry.is_registered(algo):
                logger.warning(
                    f"Skill '{metadata.id}' declares unknown algorithm: {algo}"
                )

    def _parse_metadata(
        self,
        data: dict[str, Any],
        source_file: Path | None = None,
    ) -> SkillMetadata:
        """Parse skill metadata from dictionary (delegates to unified parser)."""
        skill_id = data.get("id", self._generate_id_from_path(source_file))
        return skill_parser.build_metadata(data, skill_id, source_file or Path())

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

    def _extract_trigger_from_description(self, description: str) -> str:
        """Extract trigger conditions from skill description (delegates to parser)."""
        return skill_parser.extract_trigger_from_description(description)

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
