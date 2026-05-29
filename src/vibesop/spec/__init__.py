"""VibeSOP Skill Specification -- the canonical SKILL.md format standard.

This package defines the authoritative specification for the SKILL.md format,
independent of any routing or execution layer concerns. It replaces four
competing definitions previously scattered across the codebase:

    - core/skills/base.py: SkillMetadata (dataclass)
    - core/skills/base.py: SkillDefinition (dataclass)
    - core/skills/config_manager.py: SkillConfig (dataclass)
    - core/models.py: SkillDefinition (Pydantic)
"""

from vibesop.spec.models import SkillSpec, SkillType
from vibesop.spec.validator import SpecValidator, ValidationResult
from vibesop.spec.version import SpecVersion

__all__ = [
    "SkillSpec",
    "SkillType",
    "SpecValidator",
    "ValidationResult",
    "SpecVersion",
]
