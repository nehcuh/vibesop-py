"""VibeSOP Skill Specification -- the canonical SKILL.md format standard.

This package defines the authoritative specification for the SKILL.md format,
independent of any routing or execution layer concerns. It supersedes
pre-existing definitions:

    - core/skills/base.py: SkillMetadata (dataclass, removed v7.3.0 per ADR-004 Phase 3)
    - core/skills/base.py: SkillDefinition (dataclass, removed v5.5.0)
    - core/models.py: SkillDefinition (Pydantic, removed v7.1.0 per ADR-004 Phase 1)

Note: ``core.skills.config_manager.SkillConfig`` was deprecated in v5.5.0
but undeprecated in v7.1.0 — it serves a different concern (runtime
persistence) from SkillSpec (immutable spec). See ADR-004 Phase 2 withdrawal.

ADR-004 phases (deprecated-types cleanup):
    - Phase 1 (v7.1) ✅: SkillDefinition Pydantic removed. SkillSpec is now the
      canonical type used by core.models.SkillRegistry, adapters.models.Manifest,
      and builder.{manifest,overlay,renderer}.
    - Phase 2 (v7.2) ❌ withdrawn: SkillConfig is NOT redundant with SkillSpec
      (different concerns: persistence vs spec).
    - Phase 3 (v7.3) ✅: SkillMetadata dataclass + local SkillType enum removed.
      ``parse_skill_md()`` now returns SkillSpec directly; ``build_metadata()``
      is a thin alias for ``build_spec()``; ``ExternalSkillMetadata.base_metadata``
      is typed as SkillSpec; ``Skill``/``PromptSkill``/``WorkflowSkill`` accept
      SkillSpec as their ``metadata`` parameter.
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
