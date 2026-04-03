"""Tests for ConfigRenderer."""

from pathlib import Path

import pytest
from vibesop.builder import ConfigRenderer, RenderProgressTracker
from vibesop.builder import QuickBuilder
from vibesop.adapters.models import Manifest, ManifestMetadata


class TestConfigRenderer:
    """Test ConfigRenderer functionality."""

    def test_create_renderer(self) -> None:
        """Test creating ConfigRenderer."""
        renderer = ConfigRenderer()
        assert renderer is not None

    def test_get_supported_platforms(self) -> None:
        """Test getting supported platforms."""
        renderer = ConfigRenderer()
        platforms = renderer.get_supported_platforms()

        assert isinstance(platforms, list)
        assert "claude-code" in platforms
        assert "opencode" in platforms

    def test_is_platform_supported(self) -> None:
        """Test platform support check."""
        renderer = ConfigRenderer()

        assert renderer.is_platform_supported("claude-code")
        assert renderer.is_platform_supported("opencode")
        assert not renderer.is_platform_supported("unknown-platform")

    def test_get_adapter_supported_platform(self) -> None:
        """Test getting adapter for supported platform."""
        renderer = ConfigRenderer()
        adapter = renderer._get_adapter("claude-code")

        assert adapter is not None
        assert adapter.platform_name == "claude-code"

    def test_get_adapter_unsupported_platform(self) -> None:
        """Test getting adapter for unsupported platform."""
        renderer = ConfigRenderer()

        with pytest.raises(ValueError, match="Unsupported platform"):
            renderer._get_adapter("unknown-platform")

    def test_render_with_auto_detection(self, tmp_path: Path) -> None:
        """Test rendering with automatic platform detection."""
        renderer = ConfigRenderer()
        metadata = ManifestMetadata(platform="opencode")
        manifest = QuickBuilder.minimal(platform="opencode")

        result = renderer.render(manifest, tmp_path / "output")

        assert result.success
        assert (tmp_path / "output" / "config.yaml").exists()

    def test_render_with_default_output_dir(self, tmp_path: Path) -> None:
        """Test rendering with default output directory."""
        renderer = ConfigRenderer()
        metadata = ManifestMetadata(platform="opencode")
        manifest = QuickBuilder.minimal(platform="opencode")

        # Use adapter's default config_dir
        result = renderer.render(manifest)

        assert result.success
        # Should have used ~/.opencode
        assert "/.opencode" in str(result.files_created[0]) or ".opencode" in str(result.files_created[0])

    def test_render_invalid_platform(self) -> None:
        """Test rendering with unsupported platform."""
        renderer = ConfigRenderer()

        # Create manifest with unsupported platform
        metadata = ManifestMetadata(platform="unknown-platform")
        manifest = QuickBuilder.minimal(platform="unknown-platform")

        result = renderer.render(manifest, Path("/tmp/test"))

        assert not result.success
        assert len(result.errors) > 0

    def test_render_multiple(self, tmp_path: Path) -> None:
        """Test rendering multiple manifests."""
        renderer = ConfigRenderer()

        manifests = [
            QuickBuilder.minimal(platform="claude-code"),
            QuickBuilder.minimal(platform="opencode"),
        ]

        results = renderer.render_multiple(manifests, tmp_path / "configs")

        assert len(results) == 2
        assert "claude-code" in results
        assert "opencode" in results

        # Check both succeeded
        assert results["claude-code"].success
        assert results["opencode"].success

    def test_render_multiple_one_fails(self, tmp_path: Path) -> None:
        """Test that rendering continues even if one manifest fails."""
        renderer = ConfigRenderer()

        manifests = [
            QuickBuilder.minimal(platform="claude-code"),
            QuickBuilder.minimal(platform="unknown-platform"),  # This will fail
        ]

        results = renderer.render_multiple(manifests, tmp_path / "configs")

        assert len(results) == 2
        assert results["claude-code"].success
        assert not results["unknown-platform"].success

    def test_create_quick_manifest(self) -> None:
        """Test creating quick manifest."""
        manifest = ConfigRenderer.create_quick_manifest(
            platform="opencode",
            skills=["skill-1", "skill-2"],
            author="Test Author",
        )

        assert manifest.metadata.platform == "opencode"
        assert manifest.metadata.author == "Test Author"
        assert len(manifest.skills) == 2
        assert manifest.skills[0].id == "skill-1"


class TestRenderProgressTracker:
    """Test RenderProgressTracker functionality."""

    def test_create_tracker(self) -> None:
        """Test creating tracker."""
        tracker = RenderProgressTracker()
        assert tracker.stages == []
        assert tracker.current_percent == 0

    def test_update_progress(self) -> None:
        """Test updating progress."""
        tracker = RenderProgressTracker()

        tracker.update("detect", "Detecting platform", 10)
        tracker.update("render", "Rendering", 50)

        assert len(tracker.stages) == 2
        assert tracker.current_percent == 50

    def test_get_summary(self) -> None:
        """Test getting progress summary."""
        tracker = RenderProgressTracker()

        tracker.update("detect", "Detecting", 25)
        tracker.update("render", "Rendering", 75)

        summary = tracker.get_summary()

        assert summary["total_stages"] == 2
        assert summary["current_stage"] == "render"
        assert summary["percent"] == 75
        assert not summary["complete"]

    def test_get_summary_complete(self) -> None:
        """Test summary when complete."""
        tracker = RenderProgressTracker()

        tracker.update("complete", "Done", 100)

        summary = tracker.get_summary()

        assert summary["complete"]
        assert summary["percent"] == 100

    def test_get_summary_empty(self) -> None:
        """Test summary when no stages."""
        tracker = RenderProgressTracker()

        summary = tracker.get_summary()

        assert summary["total_stages"] == 0
        assert summary["percent"] == 0
        assert not summary["complete"]

    def test_print_progress(self, capsys: pytest.fixture) -> None:
        """Test printing progress."""
        tracker = RenderProgressTracker()

        tracker.update("stage1", "Message 1", 50)
        tracker.update("stage2", "Message 2", 100)

        # Just verify it runs without error
        tracker.print_progress()

        # Verify stages were recorded
        assert len(tracker.stages) == 2


class TestConfigRendererIntegration:
    """Integration tests for ConfigRenderer."""

    def test_full_render_workflow(self, tmp_path: Path) -> None:
        """Test complete render workflow with progress tracking."""
        tracker = RenderProgressTracker()
        renderer = ConfigRenderer(on_progress=tracker.update)

        manifest = ConfigRenderer.create_quick_manifest(
            platform="opencode",
            version="1.0.0",
        )

        result = renderer.render(manifest, tmp_path / "output")

        assert result.success
        assert len(tracker.stages) > 0
        assert tracker.stages[-1]["percent"] == 100

    def test_render_creates_expected_files(self, tmp_path: Path) -> None:
        """Test that rendering creates expected files."""
        renderer = ConfigRenderer()

        manifest = ConfigRenderer.create_quick_manifest(
            platform="opencode",
            skills=["test-skill"],
        )

        result = renderer.render(manifest, tmp_path / "output")

        assert result.success
        assert (tmp_path / "output" / "config.yaml").exists()

    def test_auto_detects_platform(self, tmp_path: Path) -> None:
        """Test that platform is auto-detected from manifest."""
        renderer = ConfigRenderer()

        # Test with claude-code
        manifest_cc = ConfigRenderer.create_quick_manifest(platform="claude-code")
        result_cc = renderer.render(manifest_cc, tmp_path / "cc")
        assert result_cc.success
        # Claude Code creates more files
        assert result_cc.file_count > 1

        # Test with opencode
        manifest_oc = ConfigRenderer.create_quick_manifest(platform="opencode")
        result_oc = renderer.render(manifest_oc, tmp_path / "oc")
        assert result_oc.success
        # OpenCode creates fewer files
        assert result_oc.file_count >= 1
