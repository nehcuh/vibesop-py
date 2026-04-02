"""VibeSOP Skill Management System.

This module provides a comprehensive skill management system including:
- Base skill classes and interfaces
- Skill discovery and loading from filesystem
- High-level skill management API

Usage:
    from vibesop.core.skills import SkillManager, SkillContext

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
from vibesop.core.skills.manager import SkillManager

__all__ = [
    "PromptSkill",
    "Skill",
    "SkillContext",
    "SkillDefinition",
    "SkillLoader",
    "SkillManager",
    "SkillMetadata",
    "SkillResult",
    "SkillType",
    "WorkflowSkill",
]
