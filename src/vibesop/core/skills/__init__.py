"""VibeSOP Skill Management System.

Part of the SkillOS (Skill Operating System) — manages the full lifecycle of
AI development skills: discovery → installation → routing → orchestration →
evaluation → retention/deprecation.

This module provides:
- Base skill classes and interfaces
- Skill discovery and loading from filesystem
- Central storage with platform symlinks
- High-level skill management API
- Lifecycle state management (DRAFT → ACTIVE → DEPRECATED → ARCHIVED)
- Quality evaluation and retention policies

Usage:
    from vibesop.core.skills import SkillManager, SkillStorage
    from vibesop.core.routing import UnifiedRouter

    # Storage management
    storage = SkillStorage()
    storage.install_skill("systematic-debugging", Path("core/skills/systematic-debugging"))
    storage.link_to_platform("systematic-debugging", "claude-code")

    # Skill discovery and lifecycle management
    manager = SkillManager()
    skills = manager.list_skills()
    info = manager.get_skill_info("gstack/review")

    # Route queries to skills
    router = UnifiedRouter()
    result = router.route("review my code")
"""

from vibesop.core.skills.base import (
    PromptSkill,
    Skill,
    SkillContext,
    SkillMetadata,
    SkillResult,
    SkillType,
    WorkflowSkill,
)
from vibesop.core.skills.external_loader import (
    ExternalSkillLoader,
    ExternalSkillMetadata,
    discover_external_skills,
    is_skill_safe,
)
from vibesop.core.skills.external_loader import (
    SkillSource as ExternalSkillSource,
)
from vibesop.core.skills.format_converter import (
    FormatConverterRegistry,
    GstackConverter,
    SkillFormatConverter,
    SuperpowersConverter,
)
from vibesop.core.skills.loader import LoadedSkill, SkillLoader
from vibesop.core.skills.manager import SkillManager
from vibesop.core.skills.storage import (
    SkillManifest,
    SkillSource,
    SkillStorage,
    get_storage,
    install_skill_from_project,
    link_all_to_platform,
)

__all__ = [
    "ExternalSkillLoader",
    "ExternalSkillMetadata",
    "ExternalSkillSource",
    "FormatConverterRegistry",
    "GstackConverter",
    "LoadedSkill",
    "PromptSkill",
    "Skill",
    "SkillContext",
    "SkillFormatConverter",
    "SkillLoader",
    "SkillManager",
    "SkillManifest",
    "SkillMetadata",
    "SkillResult",
    "SkillSource",
    "SkillStorage",
    "SkillType",
    "SuperpowersConverter",
    "WorkflowSkill",
    "discover_external_skills",
    "get_storage",
    "install_skill_from_project",
    "is_skill_safe",
    "link_all_to_platform",
]
