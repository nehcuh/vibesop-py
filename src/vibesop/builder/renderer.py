"""Configuration renderer for high-level config generation.

This module provides a high-level interface for rendering platform
configurations from manifests, with automatic platform detection
and enhanced error handling.
"""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from vibesop.adapters import (
    ClaudeCodeAdapter,
    OpenCodeAdapter,
    PlatformAdapter,
)
from vibesop.adapters.models import Manifest, RenderResult


class ConfigRenderer:
    """High-level configuration renderer.

    Automatically detects the target platform from the manifest
    and uses the appropriate adapter to generate configuration files.

    Provides additional features:
    - Pre-render validation
    - Platform auto-detection
    - Progress tracking callbacks
    - Enhanced error messages

    Example:
        >>> renderer = ConfigRenderer()
        >>> result = renderer.render(manifest, Path("~/.claude"))
        >>> print(f"✅ Generated {result.file_count} files")
    """

    # Platform adapter registry
    _adapters: ClassVar[dict[str, Callable[..., PlatformAdapter]]] = {
        "claude-code": ClaudeCodeAdapter,
        "opencode": OpenCodeAdapter,
    }

    def __init__(
        self,
        on_progress: Callable[[str, str, int], None] | None = None,
        project_root: str | Path = ".",
    ) -> None:
        """Initialize the config renderer.

        Args:
            on_progress: Optional callback for progress updates
                           Signature: (stage, message, percent)
            project_root: Path to VibeSOP project root (contains core/skills/)
        """
        self.on_progress = on_progress
        self._project_root = Path(project_root).resolve()

    def render(
        self,
        manifest: Manifest,
        output_dir: Path | None = None,
    ) -> RenderResult:
        """Render configuration from manifest.

        Automatically detects the target platform and uses the
        appropriate adapter to generate configuration files.

        Args:
            manifest: Configuration manifest
            output_dir: Output directory (defaults to adapter's config_dir)

        Returns:
            RenderResult with files created and any warnings/errors

        Raises:
            ValueError: If platform is not supported
        """
        try:
            self._notify_progress("detect", "Detecting platform", 0)

            # Detect platform
            platform = manifest.metadata.platform
            adapter = self._get_adapter(platform)

            # Use adapter's default config_dir if not specified
            if output_dir is None:
                output_dir = adapter.config_dir

            self._notify_progress("validate", "Validating manifest", 20)

            # Pre-render validation
            errors = adapter.validate_manifest(manifest)
            if errors:
                result = RenderResult(success=False, errors=errors)
                self._notify_progress("error", "Validation failed", 100)
                return result

            self._notify_progress("render", f"Rendering {platform} configuration", 40)

            # Render configuration
            result = adapter.render_config(manifest, output_dir)

            self._notify_progress("complete", "Rendering complete", 100)

            return result

        except ValueError as e:
            # Convert ValueError to RenderResult
            self._notify_progress("error", f"Error: {e}", 100)
            return RenderResult(
                success=False,
                errors=[str(e)],
            )
        except Exception as e:
            # Catch other errors
            self._notify_progress("error", f"Unexpected error: {e}", 100)
            return RenderResult(
                success=False,
                errors=[f"Unexpected error: {e}"],
            )

    def render_config_only(
        self,
        manifest: Manifest,
        output_dir: Path,
    ) -> RenderResult:
        """Render only config files (CLAUDE.md, rules/, docs/), not skills.

        This is used by the installer which handles skills separately
        via SkillStorage.sync_project_skills().

        Args:
            manifest: Configuration manifest
            output_dir: Output directory for config files

        Returns:
            RenderResult with files created and any warnings/errors
        """
        # For now, this is the same as render() since adapters
        # handle config and skills separately anyway
        return self.render(manifest, output_dir)

    def render_multiple(
        self,
        manifests: list[Manifest],
        output_base_dir: Path,
    ) -> dict[str, RenderResult]:
        """Render multiple manifests to different directories.

        Args:
            manifests: List of manifests to render
            output_base_dir: Base directory for all outputs

        Returns:
            Dictionary mapping platform name to RenderResult
        """
        results = {}

        for i, manifest in enumerate(manifests):
            platform = manifest.metadata.platform
            output_dir = output_base_dir / platform

            percent = int((i / len(manifests)) * 100)
            self._notify_progress(
                "batch", f"Rendering {platform} ({i + 1}/{len(manifests)})", percent
            )

            try:
                result = self.render(manifest, output_dir)
                results[platform] = result
            except Exception as e:
                # Continue rendering other platforms even if one fails
                results[platform] = RenderResult(
                    success=False,
                    errors=[str(e)],
                )

        return results

    def get_supported_platforms(self) -> list[str]:
        """Get list of supported platforms.

        Returns:
            List of platform identifiers
        """
        return list(self._adapters.keys())

    def is_platform_supported(self, platform: str) -> bool:
        """Check if a platform is supported.

        Args:
            platform: Platform identifier

        Returns:
            True if supported, False otherwise
        """
        return platform in self._adapters

    def _get_adapter(self, platform: str) -> PlatformAdapter:
        """Get adapter instance for platform.

        Args:
            platform: Platform identifier

        Returns:
            Platform adapter instance

        Raises:
            ValueError: If platform is not supported
        """
        if platform not in self._adapters:
            supported = ", ".join(self.get_supported_platforms())
            msg = f"Unsupported platform: {platform}. Supported platforms: {supported}"
            raise ValueError(msg)

        adapter_class = self._adapters[platform]
        # Pass project_root to ClaudeCodeAdapter for skill content lookup
        if platform == "claude-code":
            return adapter_class(project_root=self._project_root)
        return adapter_class()

    def _notify_progress(self, stage: str, message: str, percent: int) -> None:
        """Notify progress if callback is set.

        Args:
            stage: Current stage (detect, validate, render, etc.)
            message: Progress message
            percent: Progress percentage (0-100)
        """
        if self.on_progress:
            self.on_progress(stage, message, percent)

    @staticmethod
    def create_quick_manifest(
        platform: str = "claude-code",
        skills: list[str] | None = None,
        **kwargs: Any,
    ) -> Manifest:
        """Create a quick manifest for common scenarios.

        Convenience method for creating manifests without using
        ManifestBuilder.

        Args:
            platform: Target platform
            skills: List of skill IDs to include (None = all)
            **kwargs: Additional manifest parameters

        Returns:
            Configured Manifest
        """
        from datetime import datetime

        from vibesop.adapters.models import ManifestMetadata, PolicySet
        from vibesop.core.models import SkillDefinition

        # Create metadata
        metadata = ManifestMetadata(
            platform=platform,
            created_at=datetime.now(),
            **{k: v for k, v in kwargs.items() if k in ["version", "author", "description"]},
        )

        # Create simple skills list if provided
        manifest_skills = []
        if skills:
            for skill_id in skills:
                manifest_skills.append(
                    SkillDefinition(
                        id=skill_id,
                        name=skill_id.replace("-", " ").title(),
                        description=f"Skill: {skill_id}",
                        trigger_when="Manual",
                    )
                )

        # Create manifest
        return Manifest(
            skills=manifest_skills,
            policies=PolicySet(),  # Use defaults
            metadata=metadata,
        )


class RenderProgressTracker:
    """Track rendering progress for UI feedback.

    Example:
        >>> tracker = RenderProgressTracker()
        >>> renderer = ConfigRenderer(on_progress=tracker.update)
        >>> result = renderer.render(manifest, output_dir)
        >>> print(f"Stages: {tracker.stages}")
    """

    def __init__(self) -> None:
        """Initialize the progress tracker."""
        self.stages: list[dict[str, Any]] = []
        self.current_stage: str | None = None
        self.current_percent: int = 0

    def update(
        self,
        stage: str,
        message: str,
        percent: int,
    ) -> None:
        """Update progress.

        Args:
            stage: Current stage
            message: Progress message
            percent: Progress percentage (0-100)
        """
        self.current_stage = stage
        self.current_percent = percent

        self.stages.append(
            {
                "stage": stage,
                "message": message,
                "percent": percent,
                "timestamp": datetime.now(),
            }
        )

    def get_summary(self) -> dict[str, Any]:
        """Get progress summary.

        Returns:
            Summary dictionary
        """
        if not self.stages:
            return {
                "total_stages": 0,
                "complete": False,
                "percent": 0,
            }

        return {
            "total_stages": len(self.stages),
            "current_stage": self.current_stage,
            "percent": self.current_percent,
            "complete": self.current_percent == 100,
            "stages": self.stages,
        }

    def print_progress(self) -> None:
        """Print progress to console."""
        for stage_info in self.stages:
            print(f"[{stage_info['percent']}%] {stage_info['stage']}: {stage_info['message']}")
