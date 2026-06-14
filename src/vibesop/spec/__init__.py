"""VibeSOP Skill Specification -- the canonical SKILL.md format standard.

This package defines the authoritative specification for the SKILL.md format,
independent of any routing or execution layer concerns. It supersedes four
pre-existing definitions:

    - core/skills/base.py: SkillMetadata (dataclass, deprecated v5.5.0) -- ADR-004 Phase 3
    - core/skills/base.py: SkillDefinition (dataclass, removed v5.5.0)
    - core/skills/config_manager.py: SkillConfig (dataclass, deprecated v5.5.0) -- ADR-004 Phase 2
    - core/models.py: SkillDefinition (Pydantic, removed v7.1.0 per ADR-004 Phase 1)

ADR-004 phases (deprecated-types cleanup):
    - Phase 1 (v7.1): SkillDefinition Pydantic removed. SkillSpec is now the
      canonical type used by core.models.SkillRegistry, adapters.models.Manifest,
      and builder.{manifest,overlay,renderer}.
    - Phase 2 (v7.2): SkillConfig → SkillSpec.
    - Phase 3 (v7.3): SkillMetadata → SkillSpec.
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
