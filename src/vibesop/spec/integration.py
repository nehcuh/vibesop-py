"""Skill integration protocol -- the standard for platform adapters.

Defines the canonical integration modes and targets that any AI platform
can implement to support the SKILL.md specification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from vibesop.spec.models import SkillSpec


class IntegrationMode(StrEnum):
    """How a platform integrates SkillSpec content."""

    FILE_BASED = "file_based"      # CLAUDE.md/AGENTS.md with file references
    HOOK_BASED = "hook_based"      # Shell/TS hooks intercept prompts at runtime
    SDK_BASED = "sdk_based"        # Native Python/TS import of vibesop library


class IntegrationTarget(StrEnum):
    """What an integration produces."""

    CONTEXT_FILE = "context_file"         # CLAUDE.md or AGENTS.md
    SKILL_DIRECTORY = "skill_directory"    # skills/ with symlinks or copies
    HOOK_SCRIPT = "hook_script"           # Shell script or TS extension
    PROMPT_TEMPLATE = "prompt_template"   # Agent-specific prompt format
    SETTINGS_FILE = "settings_file"       # Platform settings (settings.json etc.)
    BEHAVIOR_RULES = "behavior_rules"     # Always-loaded behavior rules
    DOCS_REFERENCE = "docs_reference"     # On-demand documentation files
    ENV_SCRIPT = "env_script"             # Environment setup script


@dataclass
class ConformanceManifest:
    """Self-declaration of what a platform integration supports."""

    platform_name: str
    mode: IntegrationMode
    targets: list[IntegrationTarget] = field(default_factory=list)
    spec_versions: list[str] = field(default_factory=lambda: ["1.0", "2.0", "3.0"])
    skill_types: list[str] = field(default_factory=lambda: ["prompt", "workflow", "command", "hybrid", "standard"])
    max_skills: int | None = None
    notes: str = ""


@runtime_checkable
class SkillIntegrationProtocol(Protocol):
    """Protocol that all platform integrations must implement.

    This is the interface contract between VibeSOP and any AI platform.
    Implementations produce the correct context files, skill directories,
    and hook scripts for their target platform.

    The protocol is intentionally minimal -- each platform only needs to
    implement what it actually supports (declared via get_conformance_manifest).
    """

    @property
    def platform_name(self) -> str: ...

    @property
    def integration_mode(self) -> IntegrationMode: ...

    def render(
        self,
        specs: list[SkillSpec],
        output_dir: Path,
        **kwargs: Any,
    ) -> Any:  # RenderResult or platform-specific equivalent
        """Render platform configuration from SkillSpec definitions.

        Args:
            specs: List of skill specifications to install.
            output_dir: Target directory for generated files.
            **kwargs: Platform-specific rendering options.

        Returns:
            Platform-specific render result.
        """
        ...

    def get_conformance_manifest(self) -> ConformanceManifest:
        """Return the platform's conformance self-declaration."""
        ...
