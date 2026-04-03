"""Tests for adapter data models."""

import pytest
from datetime import datetime
from pathlib import Path
from pydantic import ValidationError

from vibesop.adapters.models import (
    Manifest,
    ManifestMetadata,
    PolicySet,
    RenderResult,
    RoutingConfig,
    SecurityPolicy,
)
from vibesop.core.models import SkillDefinition


class TestSecurityPolicy:
    """Test SecurityPolicy model."""

    def test_create_default(self) -> None:
        """Test creating SecurityPolicy with defaults."""
        policy = SecurityPolicy()

        assert policy.scan_external_content is True
        assert policy.allow_path_traversal is False
        assert policy.max_file_size == 10 * 1024 * 1024
        assert policy.require_signed_skills is False

    def test_create_custom(self) -> None:
        """Test creating SecurityPolicy with custom values."""
        policy = SecurityPolicy(
            scan_external_content=False,
            max_file_size=1024,
            require_signed_skills=True,
        )

        assert policy.scan_external_content is False
        assert policy.max_file_size == 1024
        assert policy.require_signed_skills is True

    def test_path_traversal_not_allowed(self) -> None:
        """Test that path traversal is always rejected."""
        with pytest.raises(ValueError, match="must never be allowed"):
            SecurityPolicy(allow_path_traversal=True)

    def test_max_file_size_validation(self) -> None:
        """Test max_file_size validation."""
        # Negative size
        with pytest.raises(ValueError, match="must be non-negative"):
            SecurityPolicy(max_file_size=-1)

        # Too large
        with pytest.raises(ValueError, match="must be less than 1GB"):
            SecurityPolicy(max_file_size=2 * 1024 * 1024 * 1024)

        # Valid sizes
        assert SecurityPolicy(max_file_size=0).max_file_size == 0
        assert SecurityPolicy(max_file_size=100).max_file_size == 100


class TestRoutingConfig:
    """Test RoutingConfig model."""

    def test_create_default(self) -> None:
        """Test creating RoutingConfig with defaults."""
        config = RoutingConfig()

        assert config.enable_ai_routing is True
        assert config.confidence_threshold == 0.6
        assert config.max_candidates == 3
        assert config.enable_preference_learning is True

    def test_create_custom(self) -> None:
        """Test creating RoutingConfig with custom values."""
        config = RoutingConfig(
            enable_ai_routing=False,
            confidence_threshold=0.8,
            max_candidates=5,
            enable_preference_learning=False,
        )

        assert config.enable_ai_routing is False
        assert config.confidence_threshold == 0.8
        assert config.max_candidates == 5
        assert config.enable_preference_learning is False

    def test_confidence_threshold_bounds(self) -> None:
        """Test confidence_threshold validation."""
        # Below minimum
        with pytest.raises(ValueError):
            RoutingConfig(confidence_threshold=-0.1)

        # Above maximum
        with pytest.raises(ValueError):
            RoutingConfig(confidence_threshold=1.1)

        # Valid values
        assert RoutingConfig(confidence_threshold=0.0).confidence_threshold == 0.0
        assert RoutingConfig(confidence_threshold=1.0).confidence_threshold == 1.0

    def test_max_candidates_bounds(self) -> None:
        """Test max_candidates validation."""
        # Below minimum
        with pytest.raises(ValueError):
            RoutingConfig(max_candidates=0)

        # Above maximum
        with pytest.raises(ValueError):
            RoutingConfig(max_candidates=11)

        # Valid values
        assert RoutingConfig(max_candidates=1).max_candidates == 1
        assert RoutingConfig(max_candidates=10).max_candidates == 10


class TestPolicySet:
    """Test PolicySet model."""

    def test_create_default(self) -> None:
        """Test creating PolicySet with defaults."""
        policies = PolicySet()

        assert isinstance(policies.security, SecurityPolicy)
        assert isinstance(policies.routing, RoutingConfig)
        assert policies.behavior == {}
        assert policies.custom == {}

    def test_create_with_values(self) -> None:
        """Test creating PolicySet with values."""
        security = SecurityPolicy(max_file_size=1024)
        routing = RoutingConfig(confidence_threshold=0.8)
        behavior = {"strict": True}
        custom = {"custom_key": "custom_value"}

        policies = PolicySet(
            security=security,
            routing=routing,
            behavior=behavior,
            custom=custom,
        )

        assert policies.security.max_file_size == 1024
        assert policies.routing.confidence_threshold == 0.8
        assert policies.behavior == behavior
        assert policies.custom == custom


class TestManifestMetadata:
    """Test ManifestMetadata model."""

    def test_create_default(self) -> None:
        """Test creating ManifestMetadata with defaults."""
        metadata = ManifestMetadata(platform="test-platform")

        assert metadata.version == "1.0.0"
        assert metadata.platform == "test-platform"
        assert isinstance(metadata.created_at, datetime)
        assert isinstance(metadata.updated_at, datetime)
        assert metadata.author == ""
        assert metadata.description == ""

    def test_create_with_values(self) -> None:
        """Test creating ManifestMetadata with values."""
        now = datetime.now()
        metadata = ManifestMetadata(
            version="2.0.0",
            platform="test-platform",
            author="Test Author",
            description="Test manifest",
            created_at=now,
            updated_at=now,
        )

        assert metadata.version == "2.0.0"
        assert metadata.platform == "test-platform"
        assert metadata.author == "Test Author"
        assert metadata.description == "Test manifest"


class TestManifest:
    """Test Manifest model."""

    def test_create_minimal(self) -> None:
        """Test creating Manifest with minimal required fields."""
        metadata = ManifestMetadata(platform="test-platform")
        manifest = Manifest(metadata=metadata)

        assert manifest.skills == []
        assert isinstance(manifest.policies, PolicySet)
        assert manifest.security is None
        assert manifest.routing is None
        assert manifest.overlay is None

    def test_create_full(self) -> None:
        """Test creating Manifest with all fields."""
        skill = SkillDefinition(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            trigger_when="Testing",
        )
        metadata = ManifestMetadata(platform="test-platform")
        security = SecurityPolicy(max_file_size=1024)
        routing = RoutingConfig(confidence_threshold=0.8)

        manifest = Manifest(
            skills=[skill],
            metadata=metadata,
            security=security,
            routing=routing,
            overlay={"custom": "value"},
        )

        assert len(manifest.skills) == 1
        assert manifest.skills[0].id == "test-skill"
        assert manifest.security is not None
        assert manifest.security.max_file_size == 1024
        assert manifest.routing is not None
        assert manifest.routing.confidence_threshold == 0.8
        assert manifest.overlay == {"custom": "value"}

    def test_get_effective_security_policy(self) -> None:
        """Test get_effective_security_policy method."""
        # With deprecated security field
        security = SecurityPolicy(max_file_size=1024)
        metadata = ManifestMetadata(platform="test-platform")
        manifest = Manifest(
            metadata=metadata,
            security=security,
        )

        effective = manifest.get_effective_security_policy()
        assert effective.max_file_size == 1024

        # Without deprecated field
        manifest2 = Manifest(
            metadata=metadata,
            policies=PolicySet(security=security),
        )

        effective2 = manifest2.get_effective_security_policy()
        assert effective2.max_file_size == 1024

    def test_get_effective_routing_config(self) -> None:
        """Test get_effective_routing_config method."""
        # With deprecated routing field
        routing = RoutingConfig(confidence_threshold=0.8)
        metadata = ManifestMetadata(platform="test-platform")
        manifest = Manifest(
            metadata=metadata,
            routing=routing,
        )

        effective = manifest.get_effective_routing_config()
        assert effective.confidence_threshold == 0.8

        # Without deprecated field
        manifest2 = Manifest(
            metadata=metadata,
            policies=PolicySet(routing=routing),
        )

        effective2 = manifest2.get_effective_routing_config()
        assert effective2.confidence_threshold == 0.8

    def test_overlay_validation(self) -> None:
        """Test overlay validation."""
        metadata = ManifestMetadata(platform="test-platform")

        # Valid overlay
        manifest = Manifest(
            metadata=metadata,
            overlay={"key": "value"},
        )
        assert manifest.overlay == {"key": "value"}

        # Invalid overlay (not a dict) - Pydantic raises ValidationError
        with pytest.raises(ValidationError):
            Manifest(
                metadata=metadata,
                overlay="not a dict",  # type: ignore
            )


class TestRenderResult:
    """Test RenderResult model."""

    def test_create_default(self) -> None:
        """Test creating RenderResult with defaults."""
        result = RenderResult(success=True)

        assert result.success is True
        assert result.files_created == []
        assert result.warnings == []
        assert result.errors == []
        assert result.metadata == {}

    def test_create_with_values(self) -> None:
        """Test creating RenderResult with values."""
        files = [Path("/tmp/file1.txt"), Path("/tmp/file2.txt")]
        warnings = ["Warning 1", "Warning 2"]
        errors = ["Error 1"]
        metadata = {"key": "value"}

        result = RenderResult(
            success=False,
            files_created=files,
            warnings=warnings,
            errors=errors,
            metadata=metadata,
        )

        assert result.success is False
        assert len(result.files_created) == 2
        assert len(result.warnings) == 2
        assert len(result.errors) == 1
        assert result.metadata == metadata

    def test_add_file(self) -> None:
        """Test add_file method."""
        result = RenderResult(success=True)
        result.add_file(Path("/tmp/file1.txt"))
        result.add_file(Path("/tmp/file2.txt"))

        assert len(result.files_created) == 2
        assert result.files_created[0] == Path("/tmp/file1.txt")

    def test_add_warning(self) -> None:
        """Test add_warning method."""
        result = RenderResult(success=True)
        result.add_warning("Warning 1")
        result.add_warning("Warning 2")

        assert len(result.warnings) == 2
        assert result.warnings[0] == "Warning 1"

    def test_add_error(self) -> None:
        """Test add_error method."""
        result = RenderResult(success=True)
        result.add_error("Error 1")
        result.add_error("Error 2")

        assert len(result.errors) == 2
        assert result.errors[0] == "Error 1"

    def test_has_warnings(self) -> None:
        """Test has_warnings property."""
        result = RenderResult(success=True)

        assert result.has_warnings is False

        result.add_warning("Warning")
        assert result.has_warnings is True

    def test_has_errors(self) -> None:
        """Test has_errors property."""
        result = RenderResult(success=True)

        assert result.has_errors is False

        result.add_error("Error")
        assert result.has_errors is True

    def test_file_count(self) -> None:
        """Test file_count property."""
        result = RenderResult(success=True)

        assert result.file_count == 0

        result.add_file(Path("/tmp/file1.txt"))
        result.add_file(Path("/tmp/file2.txt"))
        assert result.file_count == 2
