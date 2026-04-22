"""Hook installer for VibeSOP.

This module provides a centralized hook installation system
that manages hooks across all supported platforms.
"""

import contextlib
from pathlib import Path
from typing import Any

import jinja2
from jinja2 import Environment, FileSystemLoader

from vibesop.hooks.base import Hook
from vibesop.hooks.points import HOOK_DEFINITIONS, HookPoint


class HookInstaller:
    """Centralized hook installation manager.

    Manages hook installation, uninstallation, and verification
    across all supported platforms.

    Example:
        >>> installer = HookInstaller()
        >>> results = installer.install_hooks("claude-code", Path("~/.claude"))
        >>> print(f"Installed {len(results)} hooks")
    """

    def __init__(self) -> None:
        """Initialize the hook installer."""
        self._template_env: Environment | None = None

    @property
    def template_env(self) -> Environment:
        """Get Jinja2 template environment.

        Returns:
            Jinja2 Environment for rendering hook templates
        """
        if self._template_env is None:
            # Get templates directory
            templates_dir = Path(__file__).parent / "templates"
            self._template_env = Environment(
                loader=FileSystemLoader(templates_dir),
                autoescape=False,
            )
        return self._template_env

    def install_hooks(
        self,
        platform: str,
        config_dir: Path,
        hook_points: list[HookPoint] | None = None,
    ) -> dict[str, bool]:
        """Install hooks for a platform.

        Args:
            platform: Platform identifier (e.g., "claude-code", "kimi-cli")
            config_dir: Configuration directory
            hook_points: List of hook points to install (None = all supported)

        Returns:
            Dictionary mapping hook names to installation status
        """
        results: dict[str, bool] = {}

        # Get hook definitions for platform
        definitions = HOOK_DEFINITIONS.get(platform, {})

        if not definitions:
            return results

        # Determine which hooks to install
        if hook_points is None:
            # Install all supported hooks
            hooks_to_install = [HookPoint(hook_name) for hook_name in definitions]
        else:
            hooks_to_install = hook_points

        # Install each hook
        for hook_point in hooks_to_install:
            hook_name = hook_point.value
            if hook_name in definitions:
                success = self._install_single_hook(
                    platform,
                    hook_point,
                    config_dir,
                    definitions[hook_name],
                )
                results[hook_name] = success

        return results

    def uninstall_hooks(
        self,
        platform: str,
        config_dir: Path,
        hook_points: list[HookPoint] | None = None,
    ) -> dict[str, bool]:
        """Uninstall hooks for a platform.

        Args:
            platform: Platform identifier
            config_dir: Configuration directory
            hook_points: List of hook points to uninstall (None = all)

        Returns:
            Dictionary mapping hook names to uninstallation status
        """
        results: dict[str, bool] = {}

        # Get hook definitions for platform
        definitions = HOOK_DEFINITIONS.get(platform, {})

        if not definitions:
            return results

        # Determine which hooks to uninstall
        if hook_points is None:
            hooks_to_uninstall = [HookPoint(hook_name) for hook_name in definitions]
        else:
            hooks_to_uninstall = hook_points

        # Uninstall each hook
        for hook_point in hooks_to_uninstall:
            hook_name = hook_point.value
            if hook_name in definitions:
                success = self._uninstall_single_hook(
                    config_dir,
                    definitions[hook_name],
                )
                results[hook_name] = success

        return results

    def verify_hooks(
        self,
        platform: str,
        config_dir: Path,
    ) -> dict[str, bool]:
        """Verify hook installation status.

        Args:
            platform: Platform identifier
            config_dir: Configuration directory

        Returns:
            Dictionary mapping hook names to verification status
        """
        results: dict[str, bool] = {}

        # Get hook definitions for platform
        definitions = HOOK_DEFINITIONS.get(platform, {})

        if not definitions:
            return results

        # Verify each hook
        for hook_name, hook_def in definitions.items():
            results[hook_name] = self._verify_single_hook(
                config_dir,
                hook_def,
            )

        return results

    def _install_single_hook(
        self,
        platform: str,
        hook_point: HookPoint,
        config_dir: Path,
        hook_def: dict[str, Any],
    ) -> bool:
        """Install a single hook.

        Args:
            platform: Platform identifier
            hook_point: HookPoint to install
            config_dir: Configuration directory
            hook_def: Hook definition dictionary

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get hook file path
            hook_file = hook_def.get("file", f"hooks/{hook_point.value}.sh")
            hook_path = config_dir / hook_file

            # Render or create hook content
            hook_content = self._render_hook_template(
                platform,
                hook_point,
            )

            # Ensure parent directory exists
            hook_path.parent.mkdir(parents=True, exist_ok=True)

            # Write hook script
            hook_path.write_text(hook_content, encoding="utf-8")

            # Make executable if required
            if hook_def.get("executable", True):
                hook_path.chmod(0o755)

            return True

        except OSError:
            return False

    def _uninstall_single_hook(
        self,
        config_dir: Path,
        hook_def: dict[str, Any],
    ) -> bool:
        """Uninstall a single hook.

        Args:
            config_dir: Configuration directory
            hook_def: Hook definition dictionary

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get hook file path
            hook_file = hook_def.get("file")
            if not hook_file:
                return False

            hook_path = config_dir / hook_file

            # Remove hook file
            if hook_path.exists():
                hook_path.unlink()

                # Try to remove parent directory if empty
                with contextlib.suppress(OSError):
                    hook_path.parent.rmdir()

            return True

        except OSError:
            return False

    def _verify_single_hook(
        self,
        config_dir: Path,
        hook_def: dict[str, Any],
    ) -> bool:
        """Verify a single hook installation.

        Args:
            config_dir: Configuration directory
            hook_def: Hook definition dictionary

        Returns:
            True if hook is installed and valid, False otherwise
        """
        try:
            # Get hook file path
            hook_file = hook_def.get("file")
            if not hook_file:
                return False

            hook_path = config_dir / hook_file

            # Check if hook exists
            if not hook_path.exists():
                return False

            # Check if executable (if required)
            if hook_def.get("executable", True):
                return hook_path.stat().st_mode & 0o111 != 0

            return True

        except OSError:
            return False

    def _render_hook_template(
        self,
        platform: str,
        hook_point: HookPoint,
    ) -> str:
        """Render hook template.

        Args:
            platform: Platform identifier
            hook_point: HookPoint to render

        Returns:
            Rendered hook script content
        """
        # Try to load template
        template_name = f"{hook_point.value}.sh.j2"

        try:
            template = self.template_env.get_template(template_name)
            return template.render(
                platform=platform,
                hook_point=hook_point.value,
            )
        except (jinja2.TemplateNotFound, jinja2.TemplateError):
            # Fallback to default hook content
            return self._get_default_hook_content(platform, hook_point)

    def _get_default_hook_content(
        self,
        platform: str,
        hook_point: HookPoint,
    ) -> str:
        """Get default hook content when template is not available.

        Args:
            platform: Platform identifier
            hook_point: HookPoint to generate content for

        Returns:
            Default hook script content
        """
        if hook_point == HookPoint.PRE_SESSION_END:
            return f"""#!/bin/bash
# Pre-session-end hook for {platform}
# This hook runs before the session ends

# Trigger memory flush
if command -v vibe &> /dev/null; then
    echo "Flushing session memory..."
    # Note: 'vibe memory flush' will be available in v1.1.0
    # This hook is prepared for future memory management feature
    echo "Session ending at $(date)"
fi
"""
        elif hook_point == HookPoint.PRE_TOOL_USE:
            return f"""#!/bin/bash
# Pre-tool-use hook for {platform}
# This hook runs before a tool is used

# Log tool usage
echo "[Hook] Tool use detected: $1"
"""
        elif hook_point == HookPoint.POST_SESSION_START:
            return f"""#!/bin/bash
# Post-session-start hook for {platform}
# This hook runs after the session starts

# Initialize session
echo "[Hook] Session started for {platform}"
"""
        else:
            return f"""#!/bin/bash
# Hook for {platform}
# Hook point: {hook_point.value}
"""

    def create_hook_from_template(
        self,
        hook_name: str,
        hook_point: HookPoint,
        template_path: Path,
        template_vars: dict[str, str] | None = None,
    ) -> Hook:
        """Create a hook from a template.

        Args:
            hook_name: Unique hook identifier
            hook_point: HookPoint for this hook
            template_path: Path to Jinja2 template
            template_vars: Variables for template rendering

        Returns:
            Hook instance
        """
        from vibesop.hooks.base import TemplateHook

        return TemplateHook(
            hook_name=hook_name,
            hook_point=hook_point,
            template_path=template_path,
            template_vars=template_vars or {},
        )

    def get_hook_template_path(self, hook_point: HookPoint) -> Path:
        """Get the template path for a hook point.

        Args:
            hook_point: HookPoint to get template for

        Returns:
            Path to hook template
        """
        template_name = f"{hook_point.value}.sh.j2"
        templates_dir = Path(__file__).parent / "templates"
        return templates_dir / template_name
