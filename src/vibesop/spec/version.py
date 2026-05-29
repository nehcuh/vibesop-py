"""Spec version tracking and field migration mapping."""

from __future__ import annotations

from enum import StrEnum


class SpecVersion(StrEnum):
    """Versions of the SKILL.md format specification."""

    V1_0 = "1.0"
    V2_0 = "2.0"
    V3_0 = "3.0"

    @property
    def is_current(self) -> bool:
        """Check if this is the current (latest) spec version."""
        return self == SpecVersion.V3_0


# Maps field name -> first spec version that REQUIRES it.
# Fields not in this dict were required since V1_0.
FIELD_VERSION_REQUIREMENTS: dict[str, SpecVersion] = {
    # V1.0 baseline (no mapping needed -- these have always been required)
    # V2.0 additions
    "llm_config": SpecVersion.V2_0,
    "source_config": SpecVersion.V2_0,
    "priority": SpecVersion.V2_0,
    "routing_patterns": SpecVersion.V2_0,
    "category": SpecVersion.V2_0,
    "dependencies": SpecVersion.V2_0,
    "env_vars": SpecVersion.V2_0,
    # V3.0 additions
    "keywords": SpecVersion.V3_0,
    "capabilities": SpecVersion.V3_0,
    "lifecycle": SpecVersion.V3_0,
    "scope": SpecVersion.V3_0,
    "enabled": SpecVersion.V3_0,
    "commands": SpecVersion.V3_0,
    "user_invocable": SpecVersion.V3_0,
    "allowed_tools": SpecVersion.V3_0,
    "mode": SpecVersion.V3_0,
    "algorithms": SpecVersion.V3_0,
    "deprecation_reason": SpecVersion.V3_0,
    "confidence": SpecVersion.V3_0,
    "auto_configured": SpecVersion.V3_0,
}


def detect_spec_version(frontmatter: dict) -> SpecVersion:
    """Detect the spec version of a SKILL.md frontmatter.

    Heuristic: presence of v3-only fields → v3, v2-only → v2, otherwise v1.
    """
    has_v3_fields = any(
        frontmatter.get(f) for f in FIELD_VERSION_REQUIREMENTS
        if FIELD_VERSION_REQUIREMENTS[f] == SpecVersion.V3_0
    )
    if has_v3_fields:
        return SpecVersion.V3_0

    has_v2_fields = any(
        frontmatter.get(f) for f in FIELD_VERSION_REQUIREMENTS
        if FIELD_VERSION_REQUIREMENTS[f] == SpecVersion.V2_0
    )
    if has_v2_fields:
        return SpecVersion.V2_0

    return SpecVersion.V1_0
