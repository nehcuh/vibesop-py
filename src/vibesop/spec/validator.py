"""Skill specification validator.

Validates SKILL.md files against the canonical spec, producing structured
ValidationResult with errors (hard failures) and warnings (soft suggestions).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vibesop.spec.models import SkillType
from vibesop.spec.version import SpecVersion, detect_spec_version

logger = logging.getLogger(__name__)


@dataclass
class SpecIssue:
    """A single validation issue -- either an error or a warning."""

    field: str
    message: str
    severity: str  # "error" or "warning"
    spec_version: SpecVersion | None = None


@dataclass
class ValidationResult:
    """Result of validating a SKILL.md file against the spec."""

    valid: bool
    skill_id: str
    spec_version: SpecVersion
    errors: list[SpecIssue] = field(default_factory=list)
    warnings: list[SpecIssue] = field(default_factory=list)
    source_file: Path | None = None

    @property
    def issue_count(self) -> int:
        return len(self.errors) + len(self.warnings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "skill_id": self.skill_id,
            "spec_version": self.spec_version.value,
            "errors": [
                {"field": e.field, "message": e.message, "severity": e.severity}
                for e in self.errors
            ],
            "warnings": [
                {"field": w.field, "message": w.message, "severity": w.severity}
                for w in self.warnings
            ],
            "source_file": str(self.source_file) if self.source_file else None,
        }


class SpecValidator:
    """Validates SKILL.md files against the canonical specification.

    Usage:
        validator = SpecValidator()
        result = validator.validate_file(Path("skills/my-skill/SKILL.md"))
        if not result.valid:
            for error in result.errors:
                print(f"ERROR: {error.message}")
    """

    # Fields that must be present (non-empty) for any valid SKILL.md
    REQUIRED_FIELDS: tuple[str, ...] = ("id", "name", "description", "version")

    # Valid values for the 'type' field
    VALID_TYPES: tuple[str, ...] = tuple(t.value for t in SkillType)

    # Fields that existed in v1/v2 but were renamed or merged in v3
    MIGRATED_FIELDS: dict[str, str] = {
        "skill_type": "type",  # v3 uses 'type', 'skill_type' is accepted as alias
    }

    def __init__(self, strict: bool = False) -> None:
        """Initialize the validator.

        Args:
            strict: If True, v1/v2 fields that should be migrated produce errors,
                    not warnings.
        """
        self.strict = strict

    def validate_file(self, path: Path) -> ValidationResult:
        """Validate a SKILL.md file.

        Args:
            path: Path to SKILL.md file or directory containing one.

        Returns:
            ValidationResult with errors and warnings.
        """
        skill_file = path if path.is_file() else path / "SKILL.md"
        if not skill_file.exists():
            return ValidationResult(
                valid=False,
                skill_id=str(path),
                spec_version=SpecVersion.V3_0,
                errors=[
                    SpecIssue(
                        field="file",
                        message=f"SKILL.md not found at {skill_file}",
                        severity="error",
                    )
                ],
                source_file=skill_file,
            )

        content = skill_file.read_text(encoding="utf-8")
        frontmatter, body = _extract_frontmatter_raw(content)

        if frontmatter is None:
            return ValidationResult(
                valid=False,
                skill_id=skill_file.parent.name,
                spec_version=SpecVersion.V3_0,
                errors=[
                    SpecIssue(
                        field="frontmatter",
                        message="No valid YAML frontmatter found",
                        severity="error",
                    )
                ],
                source_file=skill_file,
            )

        return self.validate_frontmatter(frontmatter, skill_file)

    def validate_frontmatter(
        self, data: dict[str, Any], source_file: Path | None = None
    ) -> ValidationResult:
        """Validate parsed frontmatter data against the spec.

        Args:
            data: Parsed YAML frontmatter dict.
            source_file: Optional source file path for context.

        Returns:
            ValidationResult with errors and warnings.
        """
        errors: list[SpecIssue] = []
        warnings: list[SpecIssue] = []

        skill_id = data.get("id", source_file.parent.name if source_file else "unknown")
        detected_version = detect_spec_version(data)

        # 1. Check required fields
        for field in self.REQUIRED_FIELDS:
            if not data.get(field):
                errors.append(
                    SpecIssue(
                        field=field,
                        message=f"Required field '{field}' is missing or empty",
                        severity="error",
                        spec_version=SpecVersion.V3_0,
                    )
                )

        # 2. Validate 'type' field maps to a known SkillType
        type_value = data.get("type") or data.get("skill_type")
        if type_value:
            if type_value not in self.VALID_TYPES:
                errors.append(
                    SpecIssue(
                        field="type",
                        message=f"Invalid skill type '{type_value}'. Valid types: {', '.join(self.VALID_TYPES)}",
                        severity="error",
                        spec_version=SpecVersion.V3_0,
                    )
                )
        else:
            warnings.append(
                SpecIssue(
                    field="type",
                    message="No 'type' field specified, defaults to 'prompt'",
                    severity="warning",
                    spec_version=SpecVersion.V3_0,
                )
            )

        # 3. Check for v1/v2 naming conventions that should migrate
        if data.get("skill_type") and not data.get("type"):
            warnings.append(
                SpecIssue(
                    field="skill_type",
                    message="Use 'type' instead of 'skill_type' (spec v3 standard)",
                    severity="warning",
                    spec_version=SpecVersion.V3_0,
                )
            )

        # 4. Check for 'standard' type (was buggy before v3)
        if type_value == "standard" and detected_version != SpecVersion.V3_0:
            warnings.append(
                SpecIssue(
                    field="type",
                    message="type: 'standard' was not a valid SkillType before spec v3.0 "
                    "(silently fell back to 'prompt' in older parsers)",
                    severity="warning",
                    spec_version=SpecVersion.V3_0,
                )
            )

        # 5. Check that keywords and tags are separate (not merged)
        has_both = bool(data.get("tags")) and bool(data.get("keywords"))
        if has_both:
            tags_set = set(data["tags"]) if isinstance(data["tags"], list) else set()
            kw_set = set(data["keywords"]) if isinstance(data["keywords"], list) else set()
            if tags_set == kw_set:
                warnings.append(
                    SpecIssue(
                        field="tags/keywords",
                        message="'tags' and 'keywords' are identical. In spec v3 these are separate concepts: "
                        "tags are for categorization, keywords are for search.",
                        severity="warning",
                        spec_version=SpecVersion.V3_0,
                    )
                )

        # 6. Check for fields that exist in spec but are never parsed (pre-v3)
        orphan_fields = {
            "commands": "spec v3 stores commands for CLI registration",
            "user_invocable": "spec v3 stores user_invocable for slash command detection",
            "allowed_tools": "spec v3 stores allowed_tools for tool permission checks",
            "mode": "spec v3 stores mode for operational behavior control",
        }
        for field, explanation in orphan_fields.items():
            if field in data and detected_version != SpecVersion.V3_0:
                warnings.append(
                    SpecIssue(
                        field=field,
                        message=f"'{field}' is present but was discarded by pre-v3 parsers. {explanation}.",
                        severity="warning",
                        spec_version=detected_version,
                    )
                )

        # 7. Validate version string format (should be SemVer-like)
        version = data.get("version", "")
        if version and not _looks_like_semver(version):
            warnings.append(
                SpecIssue(
                    field="version",
                    message=f"Version '{version}' does not look like SemVer (e.g. '1.2.3')",
                    severity="warning",
                    spec_version=SpecVersion.V3_0,
                )
            )

        # 8. Check for LLM config without source_config when remote
        if data.get("llm_config") and not data.get("source_config"):
            warnings.append(
                SpecIssue(
                    field="source_config",
                    message="Skill has llm_config but no source_config -- consider adding "
                    "source verification info",
                    severity="warning",
                    spec_version=SpecVersion.V2_0,
                )
            )

        valid = len(errors) == 0

        return ValidationResult(
            valid=valid,
            skill_id=skill_id,
            spec_version=detected_version,
            errors=errors,
            warnings=warnings,
            source_file=source_file,
        )

    def validate_package(self, archive_path: Path) -> ValidationResult:
        """Validate a .skill archive file.

        Currently a stub -- full archive validation is planned for a future release.
        """
        if not archive_path.exists():
            return ValidationResult(
                valid=False,
                skill_id=archive_path.stem,
                spec_version=SpecVersion.V3_0,
                errors=[
                    SpecIssue(
                        field="archive",
                        message=f"Archive not found: {archive_path}",
                        severity="error",
                    )
                ],
                source_file=archive_path,
            )
        return ValidationResult(
            valid=True,
            skill_id=archive_path.stem,
            spec_version=SpecVersion.V3_0,
        )


def _extract_frontmatter_raw(content: str) -> tuple[dict[str, Any] | None, str]:
    """Extract YAML frontmatter from markdown content.

    Uses ruamel.yaml for parsing (preserves comments, consistent with parser.py).

    Returns:
        Tuple of (frontmatter dict, body content). If no valid frontmatter,
        returns (None, original content).
    """
    if not content.startswith("---"):
        return None, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return None, content

    yaml_text = parts[1]
    body = parts[2].strip()

    try:
        from ruamel.yaml import YAML

        yaml_parser = YAML()
        data = yaml_parser.load(yaml_text)
        if not isinstance(data, dict):
            return None, content
        return data, body
    except Exception:
        return None, content


def _looks_like_semver(version: str) -> bool:
    """Check if a version string looks like SemVer (X.Y.Z)."""
    import re

    return bool(re.match(r"^\d+\.\d+\.\d+", version))
