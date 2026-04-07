"""VibeSOP Skill Management System.

This module provides a comprehensive skill management system including:
- Base skill classes and interfaces
- Skill discovery and loading from filesystem
- Central storage with platform symlinks
- High-level skill management API

**⚠️ POSITIONING**: VibeSOP is a ROUTING ENGINE (discovery), not execution.

Usage:
    from vibesop.core.skills import SkillManager, SkillStorage
    from vibesop.core.routing import UnifiedRouter  # For routing

    # Storage management
    storage = SkillStorage()
    storage.install_skill("systematic-debugging", Path("core/skills/systematic-debugging"))
    storage.link_to_platform("systematic-debugging", "claude-code")

    # Skill discovery (routing engine)
    manager = SkillManager()
    skills = manager.list_skills()
    info = manager.get_skill_info("gstack/review")

    # Route queries to skills (RECOMMENDED)
    router = UnifiedRouter()
    result = router.route("review my code")  # Returns which skill matches
    # For execution, use `vibe execute` CLI command or your own logic
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
    # External loading
    "ExternalSkillLoader",
    "ExternalSkillMetadata",
    "ExternalSkillSource",
    # Base classes
    "PromptSkill",
    "Skill",
    "SkillContext",
    # Loader and manager
    "LoadedSkill",
    "SkillLoader",
    "SkillManager",
    "SkillManifest",
    "SkillMetadata",
    "SkillResult",
    "SkillSource",
    # Storage
    "SkillStorage",
    "SkillType",
    "WorkflowSkill",
    "discover_external_skills",
    "get_storage",
    "install_skill_from_project",
    "is_skill_safe",
    "link_all_to_platform",
]
