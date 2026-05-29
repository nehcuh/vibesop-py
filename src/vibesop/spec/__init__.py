"""VibeSOP Skill Specification -- the canonical SKILL.md format standard.

This package defines the authoritative specification for the SKILL.md format,
independent of any routing or execution layer concerns. It supersedes four
pre-existing definitions:

    - core/skills/base.py: SkillMetadata (dataclass, deprecated v5.5.0)
    - core/skills/base.py: SkillDefinition (dataclass, removed v5.5.0)
    - core/skills/config_manager.py: SkillConfig (dataclass, deprecated v5.5.0)
    - core/models.py: SkillDefinition (Pydantic, deprecated v5.5.0)

Full removal of deprecated types deferred to v6.0 (they still serve distinct
runtime concerns: SkillMetadata for parser/loader, SkillConfig for persistence,
SkillDefinition Pydantic for builder/manifest/adapters).
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
