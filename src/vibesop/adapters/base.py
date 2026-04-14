"""Base class for platform adapters.

This module provides the abstract base class that all platform
adapters must inherit from, along with shared utility methods.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from vibesop.adapters.models import Manifest, RenderResult
from vibesop.security import PathSafety, SecurityScanner


class PlatformAdapter(ABC):
    """Abstract base class for platform adapters.

    Provides a common interface and shared utilities for all
    platform-specific adapters.

    Example:
        class ClaudeCodeAdapter(PlatformAdapter):
            @property
            def platform_name(self) -> str:
                return "claude-code"

            @property
            def config_dir(self) -> Path:
                return Path("~/.claude").expanduser()

            def render_config(self, manifest: Manifest, output_dir: Path) -> RenderResult:
                # Implementation
                ...

            def get_settings_schema(self) -> dict:
                # Implementation
                ...
    """

    # Safety validators
    _path_safety: PathSafety
    _security_scanner: SecurityScanner

    def __init__(self) -> None:
        """Initialize the platform adapter."""
        self._path_safety = PathSafety()
        self._security_scanner = SecurityScanner()

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Platform identifier.

        Returns:
            Unique platform name (e.g., 'claude-code', 'opencode')
        """
        ...

    @property
    @abstractmethod
    def config_dir(self) -> Path:
        """Default configuration directory for this platform.

        Returns:
            Path to the default config directory (e.g., ~/.claude)
        """
        ...

    @abstractmethod
    def render_config(self, manifest: Manifest, output_dir: Path) -> RenderResult:
        """Render platform configuration from manifest.

        This method generates all necessary configuration files
        for the target platform based on the provided manifest.

        Args:
            manifest: Configuration manifest
            output_dir: Directory to write configuration files

        Returns:
            RenderResult with list of created files and any warnings/errors
        """
        ...

    @abstractmethod
    def get_settings_schema(self) -> dict[str, Any]:
        """Get the settings schema for this platform.

        Returns a JSON schema describing the structure of the
        platform's settings file (e.g., settings.json).

        Returns:
            JSON schema as a dictionary
        """
        ...

    def install_hooks(self, _config_dir: Path) -> dict[str, bool]:
        """Install platform-specific hooks.

        Default implementation does nothing. Override this method
        if your platform supports hooks.

        Args:
            config_dir: Configuration directory

        Returns:
            Dictionary mapping hook names to installation status
        """
        return {}

    # Utility methods

    def validate_manifest(self, manifest: Manifest) -> list[str]:
        """Validate a manifest before rendering.

        Performs basic validation checks on the manifest to ensure
        it's ready for rendering.

        Args:
            manifest: Manifest to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check metadata
        if not manifest.metadata:
            errors.append("Manifest metadata is required")

        # Check platform compatibility
        if manifest.metadata.platform != self.platform_name:
            errors.append(
                f"Manifest platform '{manifest.metadata.platform}' "
                f"does not match adapter platform '{self.platform_name}'"
            )

        # Check security policy
        security_policy = manifest.get_effective_security_policy()
        if security_policy.allow_path_traversal:
            errors.append("Security policy must not allow path traversal")

        return errors

    def ensure_output_dir(self, output_dir: Path) -> Path:
        """Ensure output directory exists and is safe.

        Creates the output directory if it doesn't exist,
        after validating it's safe to write to.

        Args:
            output_dir: Desired output directory

        Returns:
            Path to the validated output directory

        Raises:
            ValueError: If output directory is unsafe
        """
        output_dir = Path(output_dir).expanduser().resolve()

        # Ensure it's safe
        self._path_safety.ensure_safe_output_path(
            output_dir / "dummy.txt",
            output_dir.parent,
            create_parents=True,
        )

        # Create if needed
        output_dir.mkdir(parents=True, exist_ok=True)

        return output_dir

    def write_file_atomic(
        self,
        path: Path,
        content: str,
        validate_security: bool = True,
        base_dir: Path | None = None,
    ) -> None:
        """Write content to file atomically.

        Writes to a temporary file first, then renames to ensure
        atomic operation and prevent corruption.

        Args:
            path: Path to write to
            content: Content to write
            validate_security: Whether to scan content for threats
            base_dir: Base directory for path safety validation

        Raises:
            ValueError: If path is unsafe or content contains threats
            IOError: If write operation fails
        """
        path = Path(path).expanduser().resolve()

        # Determine base directory for safety check
        base_dir = path.parent if base_dir is None else Path(base_dir).expanduser().resolve()

        # Create parent directories if needed
        path.parent.mkdir(parents=True, exist_ok=True)

        # Validate path safety (now that parent exists)
        self._path_safety.ensure_safe_output_path(
            path,
            base_dir,
        )

        # Validate content security if enabled
        if validate_security and self._security_scanner:
            scan_result = self._security_scanner.scan(content)
            if not scan_result.safe:
                msg = f"Content contains security threats: {scan_result.summary}"
                raise ValueError(msg)

        # Write to temporary file
        tmp_path = path.with_suffix(".tmp")
        try:
            tmp_path.write_text(content, encoding="utf-8")
            # Atomic rename
            tmp_path.replace(path)
        finally:
            # Clean up temp file if it still exists
            tmp_path.unlink(missing_ok=True)

    def render_template_string(
        self,
        template_string: str,
        context: dict[str, Any],
    ) -> str:
        """Render a template string with context.

        Simple template rendering without external dependencies.
        Supports {variable} substitution.

        Args:
            template_string: Template string
            context: Template variables

        Returns:
            Rendered string
        """
        try:
            return template_string.format(**context)
        except KeyError as e:
            msg = f"Missing template variable: {e}"
            raise ValueError(msg) from e

    def get_template_context(self, manifest: Manifest) -> dict[str, Any]:
        """Get standard template context from manifest.

        Extracts common variables that all templates might need.

        Args:
            manifest: Source manifest

        Returns:
            Template context dictionary
        """
        return {
            "manifest": manifest,
            "skills": manifest.skills,
            "policies": manifest.policies,
            "security": manifest.get_effective_security_policy(),
            "routing": manifest.get_effective_routing_config(),
            "metadata": manifest.metadata,
            "platform": self.platform_name,
            "version": manifest.metadata.version,
        }

    def create_render_result(
        self,
        success: bool,
        files_created: list[Path] | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> RenderResult:
        """Create a RenderResult object.

        Helper method for creating standardized render results.

        Args:
            success: Whether rendering was successful
            files_created: List of files created
            warnings: List of warnings
            errors: List of errors

        Returns:
            RenderResult object
        """
        return RenderResult(
            success=success,
            files_created=files_created or [],
            warnings=warnings or [],
            errors=errors or [],
        )

    def scan_for_threats(self, text: str) -> list[str]:
        """Scan text for security threats.

        Args:
            text: Text to scan

        Returns:
            List of threat descriptions (empty if safe)
        """
        if not self._security_scanner:
            return []

        result = self._security_scanner.scan(text)
        if result.safe:
            return []

        return [f"{t.type.value}: {t.description}" for t in result.threats]

    def is_safe_path(self, path: Path, base_dir: Path) -> bool:
        """Check if a path is safe (no traversal).

        Args:
            path: Path to check
            base_dir: Base directory

        Returns:
            True if path is safe, False otherwise
        """
        return self._path_safety.check_traversal(path, base_dir)
