"""Tests for ManifestBuilder and related functionality."""

import tempfile
from pathlib import Path

import pytest
from vibesop.builder import (
    ManifestBuilder,
    QuickBuilder,
    OverlayMerger,
    create_overlay,
    validate_overlay,
)
from vibesop.adapters.models import Manifest, ManifestMetadata


class TestManifestBuilder:
    """Test ManifestBuilder functionality."""

    def test_create_builder(self) -> None:
        """Test creating ManifestBuilder."""
        builder = ManifestBuilder()
        assert builder.config_loader is not None
        assert builder.project_root == Path(".").resolve()

    def test_build_from_registry(self, tmp_path: Path) -> None:
        """Test building manifest from registry."""
        # Create a minimal registry for testing
        registry_dir = tmp_path / "core"
        registry_dir.mkdir(parents=True)
        registry_file = registry_dir / "registry.yaml"
        registry_file.write_text("""
skills:
  - id: test-skill
    name: Test Skill
    description: A test skill
    trigger_when: Testing
    namespace: builtin
""")

        builder = ManifestBuilder(project_root=tmp_path)
        manifest = builder.build_from_registry()

        assert isinstance(manifest, Manifest)
        assert manifest.metadata.platform == "claude-code"
        assert len(manifest.skills) > 0

    def test_build_with_custom_platform(self, tmp_path: Path) -> None:
        """Test building with custom platform."""
        builder = ManifestBuilder()
        manifest = builder.build(platform="custom-platform")

        assert manifest.metadata.platform == "custom-platform"

    def test_build_with_overlay(self, tmp_path: Path) -> None:
        """Test building with overlay."""
        # Create overlay file
        overlay_file = tmp_path / "overlay.yaml"
        overlay_file.write_text("""
metadata:
  author: Test Author
  description: Test Description
security:
  scan_external_content: false
""")

        builder = ManifestBuilder(project_root=tmp_path)
        manifest = builder.build(overlay_path=overlay_file)

        assert manifest.metadata.author == "Test Author"
        assert manifest.metadata.description == "Test Description"

    def test_build_from_file(self, tmp_path: Path) -> None:
        """Test building from manifest file."""
        manifest_file = tmp_path / "manifest.yaml"
        manifest_file.write_text("""
metadata:
  platform: test-platform
  version: 2.0.0
  author: Test Author
skills:
  - id: skill-1
    name: Skill 1
    description: Description 1
    trigger_when: Trigger 1
policies:
  security:
    scan_external_content: false
  routing:
    enable_ai_routing: false
""")

        builder = ManifestBuilder()
        manifest = builder.build_from_file(manifest_file)

        assert manifest.metadata.platform == "test-platform"
        assert manifest.metadata.version == "2.0.0"
        assert manifest.metadata.author == "Test Author"
        assert len(manifest.skills) == 1
        assert manifest.skills[0].id == "skill-1"

    def test_build_from_file_not_found(self, tmp_path: Path) -> None:
        """Test building from non-existent file."""
        builder = ManifestBuilder()

        with pytest.raises(FileNotFoundError):
            builder.build_from_file(tmp_path / "does_not_exist.yaml")

    def test_load_skills_empty_registry(self, tmp_path: Path) -> None:
        """Test loading skills from empty registry."""
        registry_dir = tmp_path / "core"
        registry_dir.mkdir(parents=True)
        (registry_dir / "registry.yaml").write_text("skills: []")

        builder = ManifestBuilder(project_root=tmp_path)
        skills = builder._load_skills()

        assert skills == []

    def test_load_policies_default(self, tmp_path: Path) -> None:
        """Test loading default policies."""
        builder = ManifestBuilder(project_root=tmp_path)
        policies = builder._load_policies()

        assert policies is not None
        assert policies.security is not None
        assert policies.routing is not None


class TestQuickBuilder:
    """Test QuickBuilder convenience methods."""

    def test_default_manifest(self) -> None:
        """Test creating default manifest."""
        manifest = QuickBuilder.default()

        assert isinstance(manifest, Manifest)
        assert manifest.metadata.platform == "claude-code"

    def test_minimal_manifest(self) -> None:
        """Test creating minimal manifest."""
        manifest = QuickBuilder.minimal()

        assert isinstance(manifest, Manifest)
        assert manifest.skills == []
        assert manifest.metadata.platform == "claude-code"

    def test_with_custom_policies(self) -> None:
        """Test creating manifest with custom policies."""
        manifest = QuickBuilder.with_custom_policies(
            security={"scan_external_content": False},
            routing={"confidence_threshold": 0.8},
        )

        security = manifest.get_effective_security_policy()
        routing = manifest.get_effective_routing_config()

        assert security.scan_external_content is False
        assert routing.confidence_threshold == 0.8


class TestOverlayMerger:
    """Test OverlayMerger functionality."""

    def test_merge_overlay(self, tmp_path: Path) -> None:
        """Test merging overlay with manifest."""
        from vibesop.adapters.models import Manifest, ManifestMetadata

        # Create base manifest
        metadata = ManifestMetadata(platform="test-platform")
        base_manifest = Manifest(metadata=metadata)

        # Create overlay file
        overlay_file = tmp_path / "overlay.yaml"
        overlay_file.write_text("""
metadata:
  author: Overlay Author
  version: 2.0.0
""")

        # Merge
        merger = OverlayMerger()
        merged = merger.merge(base_manifest, overlay_file)

        assert merged.metadata.author == "Overlay Author"
        assert merged.metadata.version == "2.0.0"
        assert merged.metadata.platform == "test-platform"  # Preserved

    def test_merge_overlay_not_found(self, tmp_path: Path) -> None:
        """Test merging with non-existent overlay."""
        from vibesop.adapters.models import Manifest, ManifestMetadata

        metadata = ManifestMetadata(platform="test")
        manifest = Manifest(metadata=metadata)
        merger = OverlayMerger()

        with pytest.raises(FileNotFoundError):
            merger.merge(manifest, tmp_path / "does_not_exist.yaml")

    def test_deep_merge(self, tmp_path: Path) -> None:
        """Test deep merge functionality."""
        merger = OverlayMerger()

        base = {
            "key1": "value1",
            "nested": {
                "key2": "value2",
                "key3": "value3",
            },
        }

        overlay = {
            "nested": {
                "key2": "overridden",
            },
            "key4": "value4",
        }

        merged = merger._deep_merge(base, overlay)

        assert merged["key1"] == "value1"  # Preserved
        assert merged["nested"]["key2"] == "overridden"  # Overridden
        assert merged["nested"]["key3"] == "value3"  # Preserved
        assert merged["key4"] == "value4"  # Added


class TestCreateOverlay:
    """Test create_overlay utility."""

    def test_create_overlay_basic(self, tmp_path: Path) -> None:
        """Test creating basic overlay."""
        overlay_path = tmp_path / "overlay.yaml"

        create_overlay(
            overlay_path,
            skills=["skill-1", "skill-2"],
            security={"scan_external_content": False},
        )

        assert overlay_path.exists()
        content = overlay_path.read_text()
        assert "skill-1" in content
        assert "skill-2" in content
        assert "scan_external_content" in content

    def test_create_overlay_creates_directories(self, tmp_path: Path) -> None:
        """Test that create_overlay creates parent directories."""
        overlay_path = tmp_path / "subdir" / "overlay.yaml"

        create_overlay(overlay_path)

        assert overlay_path.exists()
        assert overlay_path.parent.is_dir()

    def test_create_overlay_empty(self, tmp_path: Path) -> None:
        """Test creating empty overlay."""
        overlay_path = tmp_path / "overlay.yaml"

        create_overlay(overlay_path)

        assert overlay_path.exists()


class TestValidateOverlay:
    """Test validate_overlay utility."""

    def test_validate_valid_overlay(self, tmp_path: Path) -> None:
        """Test validating valid overlay."""
        overlay_file = tmp_path / "overlay.yaml"
        overlay_file.write_text("""
skills:
  - id: skill-1
""")

        errors = validate_overlay(overlay_file)

        assert errors == []

    def test_validate_missing_overlay(self, tmp_path: Path) -> None:
        """Test validating missing overlay."""
        errors = validate_overlay(tmp_path / "does_not_exist.yaml")

        assert len(errors) > 0
        assert "not found" in errors[0]

    def test_validate_invalid_structure(self, tmp_path: Path) -> None:
        """Test validating overlay with invalid structure."""
        # Create invalid YAML
        overlay_file = tmp_path / "overlay.yaml"
        overlay_file.write_text("[")

        errors = validate_overlay(overlay_file)

        assert len(errors) > 0
