"""Data models for platform adapters.

This module defines the core data structures used for configuration
generation and rendering across different platforms.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator
from vibesop.core.models import SkillDefinition


class SecurityPolicy(BaseModel):
    """Security policy configuration.

    Attributes:
        scan_external_content: Whether to scan external content for threats
        allow_path_traversal: Whether to allow path traversal (should be False)
        max_file_size: Maximum file size in bytes
        require_signed_skills: Whether to require signed skills
    """

    scan_external_content: bool = Field(
        default=True,
        description="Scan external content for security threats",
    )
    allow_path_traversal: bool = Field(
        default=False,
        description="Allow path traversal (should always be False)",
    )
    max_file_size: int = Field(
        default=10 * 1024 * 1024,  # 10MB
        description="Maximum file size in bytes",
    )
    require_signed_skills: bool = Field(
        default=False,
        description="Require skills to be cryptographically signed",
    )
    enable_command_blocklist: bool = Field(
        default=False,
        description="Enable command blocklist filtering",
    )
    command_blocklist: list[str] = Field(
        default_factory=list,
        description="List of blocked command patterns",
    )
    require_command_allowlist: bool = Field(
        default=False,
        description="Require commands to be explicitly allowed",
    )
    command_allowlist: list[str] = Field(
        default_factory=list,
        description="List of allowed command patterns",
    )

    @field_validator("allow_path_traversal")
    @classmethod
    def validate_traversal(cls, v: bool) -> bool:
        """Validate that path traversal is never allowed.

        Args:
            v: Value to validate

        Returns:
            The validated value

        Raises:
            ValueError: If allow_path_traversal is True
        """
        if v:
            msg = "Path traversal must never be allowed for security reasons"
            raise ValueError(msg)
        return v

    @field_validator("max_file_size")
    @classmethod
    def validate_max_file_size(cls, v: int) -> int:
        """Validate maximum file size.

        Args:
            v: Value to validate

        Returns:
            The validated value

        Raises:
            ValueError: If max_file_size is negative or too large
        """
        if v < 0:
            msg = "max_file_size must be non-negative"
            raise ValueError(msg)
        if v > 1024 * 1024 * 1024:  # 1GB
            msg = "max_file_size must be less than 1GB"
            raise ValueError(msg)
        return v


class RoutingConfig(BaseModel):
    """Routing configuration for skill selection.

    Attributes:
        enable_ai_routing: Whether to use AI-powered semantic routing
        confidence_threshold: Minimum confidence for auto-selection
        max_candidates: Maximum number of candidate skills to consider
        enable_preference_learning: Whether to learn from user choices
    """

    enable_ai_routing: bool = Field(
        default=True,
        description="Enable AI-powered semantic routing",
    )
    confidence_threshold: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Minimum confidence for auto-selection",
    )
    max_candidates: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum number of candidates to consider",
    )
    enable_preference_learning: bool = Field(
        default=True,
        description="Learn from user skill choices",
    )


class PolicySet(BaseModel):
    """Collection of policies governing behavior.

    Attributes:
        security: Security policies
        behavior: Behavioral rules
        routing: Routing configuration
        custom: Custom policies for extensions
    """

    security: SecurityPolicy = Field(
        default_factory=SecurityPolicy,
        description="Security policies",
    )
    behavior: dict[str, Any] = Field(
        default_factory=dict,
        description="Behavioral rules",
    )
    routing: RoutingConfig = Field(
        default_factory=RoutingConfig,
        description="Routing configuration",
    )
    custom: dict[str, Any] = Field(
        default_factory=dict,
        description="Custom policies for extensions",
    )


class ManifestMetadata(BaseModel):
    """Metadata about the configuration manifest.

    Attributes:
        version: Manifest version
        platform: Target platform
        created_at: Creation timestamp
        updated_at: Last update timestamp
        author: Manifest author
        description: Manifest description
    """

    version: str = Field(
        default="1.0.0",
        description="Manifest version",
    )
    platform: str = Field(
        ...,
        description="Target platform (e.g., 'claude-code', 'opencode')",
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Creation timestamp",
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        description="Last update timestamp",
    )
    author: str = Field(
        default="",
        description="Manifest author",
    )
    description: str = Field(
        default="",
        description="Manifest description",
    )


class Manifest(BaseModel):
    """Configuration manifest for platform adapters.

    A manifest contains all the information needed to generate
    platform-specific configuration files.

    Attributes:
        skills: List of skill definitions
        policies: Policy set
        security: Security policy (deprecated, use policies.security)
        routing: Routing configuration (deprecated, use policies.routing)
        metadata: Manifest metadata
        overlay: Optional overlay for customizations
    """

    skills: list[SkillDefinition] = Field(
        default_factory=list,
        description="List of skill definitions",
    )
    policies: PolicySet = Field(
        default_factory=PolicySet,
        description="Policy set",
    )
    security: SecurityPolicy | None = Field(
        default=None,
        description="Security policy (deprecated, use policies.security)",
    )
    routing: RoutingConfig | None = Field(
        default=None,
        description="Routing configuration (deprecated, use policies.routing)",
    )
    metadata: ManifestMetadata = Field(
        ...,
        description="Manifest metadata",
    )
    overlay: dict[str, Any] | None = Field(
        default=None,
        description="Optional overlay for customizations",
    )

    @field_validator("overlay")
    @classmethod
    def validate_overlay(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        """Validate overlay structure.

        Args:
            v: Overlay value to validate

        Returns:
            The validated overlay
        """
        if v is None:
            return v
        # Ensure overlay is a dict
        if not isinstance(v, dict):
            msg = "overlay must be a dictionary"
            raise ValueError(msg)
        return v

    def get_effective_security_policy(self) -> SecurityPolicy:
        """Get the effective security policy.

        Handles backward compatibility by using policies.security
        or the deprecated security field.

        Returns:
            The effective security policy
        """
        if self.security is not None:
            return self.security
        return self.policies.security

    def get_effective_routing_config(self) -> RoutingConfig:
        """Get the effective routing config.

        Handles backward compatibility by using policies.routing
        or the deprecated routing field.

        Returns:
            The effective routing config
        """
        if self.routing is not None:
            return self.routing
        return self.policies.routing


class RenderResult(BaseModel):
    """Result of configuration rendering.

    Attributes:
        success: Whether rendering was successful
        files_created: List of files that were created
        warnings: List of warnings
        errors: List of errors
        metadata: Additional metadata
    """

    success: bool = Field(
        ...,
        description="Whether rendering was successful",
    )
    files_created: list[Path] = Field(
        default_factory=list,
        description="List of files created",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="List of warnings",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="List of errors",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata",
    )

    def add_file(self, path: Path) -> None:
        """Add a created file to the result.

        Args:
            path: Path to the created file
        """
        self.files_created.append(path)

    def add_warning(self, warning: str) -> None:
        """Add a warning to the result.

        Args:
            warning: Warning message
        """
        self.warnings.append(warning)

    def add_error(self, error: str) -> None:
        """Add an error to the result.

        Args:
            error: Error message
        """
        self.errors.append(error)

    @property
    def has_warnings(self) -> bool:
        """Check if result has warnings."""
        return len(self.warnings) > 0

    @property
    def has_errors(self) -> bool:
        """Check if result has errors."""
        return len(self.errors) > 0

    @property
    def file_count(self) -> int:
        """Get number of files created."""
        return len(self.files_created)
