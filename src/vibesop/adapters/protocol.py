"""Protocol definitions for platform adapters.

This module defines the protocols (interfaces) that platform adapters
must implement to ensure compatibility with the configuration system.
"""

from pathlib import Path
from typing import Protocol, Any

from vibesop.adapters.models import Manifest, RenderResult


class AdapterProtocol(Protocol):
    """Protocol for platform adapters.

    This protocol defines the interface that all platform adapters
    must implement. It uses structural subtyping (duck typing)
    rather than nominal inheritance.

    Example:
        class MyAdapter:
            platform_name: str = "my-platform"
            config_dir: Path = Path("~/.my-platform")

            def render_config(self, manifest: Manifest, output_dir: Path) -> RenderResult:
                ...

            def get_settings_schema(self) -> dict:
                ...

            def install_hooks(self, config_dir: Path) -> dict[str, bool]:
                ...
    """

    @property
    def platform_name(self) -> str:
        """Platform identifier.

        Returns:
            Unique platform name (e.g., 'claude-code', 'opencode')
        """
        ...

    @property
    def config_dir(self) -> Path:
        """Default configuration directory for this platform.

        Returns:
            Path to the default config directory (e.g., ~/.claude)
        """
        ...

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

    def get_settings_schema(self) -> dict[str, Any]:
        """Get the settings schema for this platform.

        Returns a JSON schema describing the structure of the
        platform's settings file (e.g., settings.json).

        Args:
            None

        Returns:
            JSON schema as a dictionary
        """
        ...

    def install_hooks(self, config_dir: Path) -> dict[str, bool]:
        """Install platform-specific hooks.

        Installs any hook scripts or integrations required by
        the platform. This is an optional method - adapters
        that don't support hooks can return an empty dict.

        Args:
            config_dir: Configuration directory

        Returns:
            Dictionary mapping hook names to installation status
        """
        ...


class TemplateRendererProtocol(Protocol):
    """Protocol for template renderers.

    Defines the interface for rendering templates with Jinja2.
    """

    def render(self, template_name: str, context: dict[str, Any]) -> str:
        """Render a template with the given context.

        Args:
            template_name: Name of the template to render
            context: Template variables

        Returns:
            Rendered template as string
        """
        ...

    def render_to_file(
        self,
        template_name: str,
        output_path: Path,
        context: dict[str, Any],
    ) -> None:
        """Render a template and write to file.

        Args:
            template_name: Name of the template to render
            output_path: Path to write the rendered output
            context: Template variables
        """
        ...


class ValidatorProtocol(Protocol):
    """Protocol for validators.

    Defines the interface for validating manifests and configurations.
    """

    def validate_manifest(self, manifest: Manifest) -> list[str]:
        """Validate a manifest.

        Args:
            manifest: Manifest to validate

        Returns:
            List of validation errors (empty if valid)
        """
        ...

    def validate_config_dir(self, config_dir: Path) -> list[str]:
        """Validate a configuration directory.

        Args:
            config_dir: Configuration directory to validate

        Returns:
            List of validation errors (empty if valid)
        """
        ...
