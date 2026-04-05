"""VibeSOP Skill Management System.

This module provides a comprehensive skill management system including:
- Base skill classes and interfaces
- Skill discovery and loading from filesystem
- Central storage with platform symlinks
- High-level skill management API

Usage:
    from vibesop.core.skills import SkillManager, SkillStorage

    # Storage management
    storage = SkillStorage()
    storage.install_skill("systematic-debugging", Path("core/skills/systematic-debugging"))
    storage.link_to_platform("systematic-debugging", "claude-code")

    # Skill execution
    manager = SkillManager()
    skills = manager.list_skills()
    result = await manager.execute_skill("gstack/review", "review my code")
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
from vibesop.core.skills.loader import SkillDefinition, SkillLoader
from vibesop.core.skills.external_loader import (
    ExternalSkillLoader,
    SkillSource as ExternalSkillSource,
    ExternalSkillMetadata,
    discover_external_skills,
    is_skill_safe,
)
from vibesop.core.skills.manager import SkillManager
from vibesop.core.skills.storage import (
    SkillStorage,
    SkillSource,
    SkillManifest,
    get_storage,
    install_skill_from_project,
    link_all_to_platform,
)

__all__ = [
    # Base classes
    "PromptSkill",
    "Skill",
    "SkillContext",
    "SkillMetadata",
    "SkillResult",
    "SkillType",
    "WorkflowSkill",
    # Loader and manager
    "SkillDefinition",
    "SkillLoader",
    "SkillManager",
    # External loading
    "ExternalSkillLoader",
    "ExternalSkillSource",
    "ExternalSkillMetadata",
    "discover_external_skills",
    "is_skill_safe",
    # Storage
    "SkillStorage",
    "SkillSource",
    "SkillManifest",
    "get_storage",
    "install_skill_from_project",
    "link_all_to_platform",
]
