# pyright: reportMissingTypeArgument=false
"""Skill discovery and loading.

This module provides unified skill loading from both project-local skills
and external skill packs (superpowers, gstack, etc.).
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from vibesop.core.skills import parser as skill_parser
from vibesop.core.skills.base import (
    PromptSkill,
    Skill,
    WorkflowSkill,
)
from vibesop.core.skills.external_loader import ExternalSkillLoader
from vibesop.spec.models import SkillSpec, SkillType

logger = logging.getLogger(__name__)

# YAML files that live under skills directories but are VibeSOP state/config,
# not skill definitions (``.vibe/skills/auto-config.yaml`` is written by
# SkillConfigManager, ``.vibe/skills/registry.yaml`` by SkillInstaller). The
# id/name guard in ``_load_yaml_skill`` only catches YAML lacking skill fields;
# these files are excluded by name so they never become routing candidates even
# if they happen to contain a top-level "id"/"name" key. The exclusion matches
# the exact filename at any rglob depth (a nested ``sub/dir/auto-config.yaml``
# is excluded too).
NON_SKILL_YAML_FILENAMES = frozenset({"auto-config.yaml", "registry.yaml"})


@dataclass
class LoadedSkill:
    """A skill definition loaded from a file."""

    metadata: SkillSpec
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
        self.project_root = Path(project_root).resolve()
        self._project_hash = self._compute_project_hash()
        self._search_paths = self._default_search_paths()
        if search_paths:
            for p in search_paths:
                path = Path(p)
                if path not in self._search_paths:
                    self._search_paths.append(path)

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
        # Bundled-in-package builtin skills (available on any install, not just
        # the dev repo). force-include'd into the wheel at vibesop/builtin_skills.
        import vibesop as _vibesop

        pkg_builtins = Path(_vibesop.__file__).parent / "builtin_skills"
        return [
            self.project_root / "skills",
            self.project_root / ".vibe" / "skills",
            self.project_root / "core" / "skills",
            pkg_builtins,
        ]

    def _compute_project_hash(self) -> str:
        import hashlib

        return hashlib.md5(str(self.project_root).encode()).hexdigest()[:12]

    @property
    def project_hash(self) -> str:
        return self._project_hash

    def discover_all(self, force_reload: bool = False) -> dict[str, LoadedSkill]:
        """Discover all available skills."""
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

        # Filter out disabled, archived, and out-of-scope skills at discovery time
        from vibesop.core.skills.config_manager import SkillConfigManager, SkillLifecycleState

        filtered: dict[str, LoadedSkill] = {}
        for skill_id, definition in self._skill_cache.items():
            config = SkillConfigManager.get_skill_config(skill_id)
            if config is not None:
                if not config.enabled:
                    continue
                # Auto-archive deprecated skills unused for 90+ days
                if config.lifecycle == SkillLifecycleState.DEPRECATED.value:
                    last_used = config.usage_stats.get("last_used")
                    if last_used:
                        try:
                            from datetime import UTC, datetime

                            last = datetime.fromisoformat(last_used.replace("Z", "+00:00"))
                            now = datetime.now(UTC)
                            days_since = (now - last).days
                            if days_since >= 90:
                                SkillConfigManager.set_lifecycle(
                                    skill_id, SkillLifecycleState.ARCHIVED.value
                                )
                                continue
                        except (ValueError, TypeError, OverflowError):
                            pass
                if config.lifecycle == SkillLifecycleState.ARCHIVED.value:
                    continue
                # Scope isolation: project-scoped skills from other projects are hidden
                if config.scope == "project":
                    skill_project_hash = config.evaluation_context.get("project_hash")
                    if skill_project_hash and skill_project_hash != self._project_hash:
                        continue
            filtered[skill_id] = definition
        self._skill_cache = filtered

        return self._skill_cache

    def _load_external_skills(self) -> None:
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
                # Allow trusted packs through with non-critical audit issues.
                # Trusted external packs (e.g., gstack, superpowers) may contain
                # legitimate role-prompting language that triggers benign
                # role-hijacking heuristics. We still block CRITICAL threats.
                if ext_metadata.is_trusted:
                    audit_result = ext_metadata.audit_result
                    if audit_result and str(audit_result.risk_level) == "critical":
                        continue
                    # Skip logging entirely for performance - trusted skills are expected
                else:
                    continue

            # Convert external metadata to internal format
            definition = self._convert_external_skill(ext_metadata)
            if definition:
                self._skill_cache[skill_id] = definition

    def _convert_external_skill(self, ext_metadata: Any) -> LoadedSkill | None:
        from vibesop.core.skills.external_loader import ExternalSkillMetadata

        if not isinstance(ext_metadata, ExternalSkillMetadata):
            return None

        base = ext_metadata.base_metadata

        # Build skill ID with namespace
        skill_id = f"{ext_metadata.pack_name}/{base.id}" if ext_metadata.pack_name else base.id

        # Override id + namespace on a copy of the parsed SkillSpec.
        # parse_skill_md() already returns SkillSpec; no field-by-field copy needed.
        metadata = base.model_copy(
            update={
                "id": skill_id,
                "namespace": ext_metadata.pack_name or "external",
            }
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
        if not self._skill_cache:
            self.discover_all()

        return self._skill_cache.get(skill_id)

    def read_skill_content(self, skill_id: str) -> str:
        """Read the full SKILL.md content for a skill."""
        skill = self.get_skill(skill_id)
        if skill is None:
            return ""

        if skill.source_file and skill.source_file.exists():
            try:
                return skill.source_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                pass

        if isinstance(skill.content, str):
            return skill.content

        return ""

    def list_skills(
        self,
        namespace: str | None = None,
    ) -> list[LoadedSkill]:
        if not self._skill_cache:
            self.discover_all()

        skills = list(self._skill_cache.values())

        if namespace:
            skills = [s for s in skills if s.metadata.namespace == namespace]

        return skills

    def instantiate(self, skill_id: str) -> Skill | None:
        definition = self.get_skill(skill_id)
        if not definition:
            return None

        metadata = definition.metadata

        match metadata.skill_type:
            case SkillType.PROMPT | SkillType.STANDARD:
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

            # Preserve already-loaded skills so earlier search paths take precedence
            if metadata.id in self._skill_cache:
                return

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
        if file_path.name in NON_SKILL_YAML_FILENAMES:
            logger.debug("Skipping non-skill state file: %s", file_path)
            return
        try:
            yaml_parser = YAML()
            with file_path.open("r", encoding="utf-8") as f:
                data = yaml_parser.load(f)

            if not isinstance(data, dict):
                return

            # Skip non-skill YAML files (e.g., .github/dependabot.yml, CI configs)
            if "id" not in data and "name" not in data:
                logger.debug("Skipping non-skill YAML file: %s", file_path)
                return

            metadata = skill_parser.build_metadata(
                data,
                self._generate_id_from_path(file_path),
                file_path,
            )

            # Preserve already-loaded skills so earlier search paths take precedence
            if metadata.id in self._skill_cache:
                return

            content = {k: v for k, v in data.items() if k not in self._metadata_keys()}

            self._validate_algorithms(metadata)
            definition = LoadedSkill(
                metadata=metadata,
                content=content,
                source_file=file_path,
            )
            self._skill_cache[metadata.id] = definition

        except OSError as e:
            logger.warning("Failed to load YAML skill %s: %s", file_path, e)
        except Exception as e:
            logger.warning(
                "Unexpected error loading YAML skill %s: %s", file_path, e, exc_info=True
            )

    def _validate_algorithms(self, metadata: SkillSpec) -> None:
        if not metadata.algorithms:
            return
        from vibesop.core.algorithms import AlgorithmRegistry

        for algo in metadata.algorithms:
            if not AlgorithmRegistry.is_registered(algo):
                logger.warning(f"Skill '{metadata.id}' declares unknown algorithm: {algo}")

    def _parse_metadata(
        self,
        data: dict[str, Any],
        source_file: Path | None = None,
    ) -> SkillSpec:
        skill_id = data.get("id", self._generate_id_from_path(source_file))
        return skill_parser.build_metadata(data, skill_id, source_file or Path())

    def _generate_id_from_path(self, path: Path | None) -> str:
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
        elif parts[-1].endswith(".yaml"):
            name = parts[-1][:-5]
        elif parts[-1].endswith(".yml"):
            name = parts[-1][:-4]
        else:
            name = parts[-1]

        if "skills" in parts:
            idx = parts.index("skills")
            if idx + 1 < len(parts):
                return f"project/{parts[idx + 1]}/{name}"

        return f"project/{name}"

    def _extract_trigger_from_description(self, description: str) -> str:
        return skill_parser.extract_trigger_from_description(description)

    def _metadata_keys(self) -> set[str]:
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
        self._skill_cache = {}
