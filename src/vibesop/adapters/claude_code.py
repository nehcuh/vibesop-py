"""Claude Code platform adapter.

This module provides the adapter for generating Claude Code
configuration files from a manifest.
"""

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from vibesop.adapters.base import PlatformAdapter
from vibesop.adapters.models import Manifest, RenderResult


class ClaudeCodeAdapter(PlatformAdapter):
    """Adapter for Claude Code platform.

    Generates Claude Code configuration files including:
    - CLAUDE.md (main entry point)
    - rules/*.md (always-loaded rules)
    - docs/*.md (on-demand documentation)
    - skills/*/SKILL.md (skill definitions)
    - settings.json (permissions configuration)

    Example:
        >>> from vibesop.adapters import ClaudeCodeAdapter, Manifest
        >>>
        >>> adapter = ClaudeCodeAdapter()
        >>> manifest = Manifest(...)
        >>> result = adapter.render_config(manifest, Path("~/.claude"))
        >>> print(f"Created {result.file_count} files")
    """

    def __init__(self) -> None:
        """Initialize the Claude Code adapter."""
        super().__init__()
        self._template_env: Environment | None = None

    @property
    def platform_name(self) -> str:
        """Get platform identifier.

        Returns:
            Platform name 'claude-code'
        """
        return "claude-code"

    @property
    def config_dir(self) -> Path:
        """Get default configuration directory.

        Returns:
            Path to ~/.claude
        """
        return Path("~/.claude").expanduser()

    def _get_template_env(self) -> Environment:
        """Get or create Jinja2 template environment.

        Returns:
            Jinja2 Environment configured for Claude Code templates
        """
        if self._template_env is None:
            template_dir = Path(__file__).parent / "templates" / "claude-code"
            self._template_env = Environment(
                loader=FileSystemLoader(template_dir),
                autoescape=select_autoescape(),
                trim_blocks=True,
                lstrip_blocks=True,
            )
        return self._template_env

    def render_config(self, manifest: Manifest, output_dir: Path) -> RenderResult:
        """Render Claude Code configuration from manifest.

        Args:
            manifest: Configuration manifest
            output_dir: Directory to write configuration files

        Returns:
            RenderResult with list of created files and any warnings/errors
        """
        result = self.create_render_result(success=True)

        try:
            # Validate manifest
            errors = self.validate_manifest(manifest)
            if errors:
                for error in errors:
                    result.add_error(error)
                result.success = False
                return result

            # Ensure output directory exists
            output_dir = self.ensure_output_dir(output_dir)

            # Create directory structure
            (output_dir / "rules").mkdir(exist_ok=True)
            (output_dir / "docs").mkdir(exist_ok=True)
            (output_dir / "skills").mkdir(exist_ok=True)
            (output_dir / "hooks").mkdir(exist_ok=True)

            # Render main CLAUDE.md
            self._render_and_write(
                "CLAUDE.md.j2",
                output_dir / "CLAUDE.md",
                manifest,
                result,
            )

            # Render rules (always-loaded)
            self._render_and_write(
                "rules/behaviors.md.j2",
                output_dir / "rules" / "behaviors.md",
                manifest,
                result,
            )
            self._render_and_write(
                "rules/routing.md.j2",
                output_dir / "rules" / "routing.md",
                manifest,
                result,
            )
            self._render_and_write(
                "rules/skill-triggers.md.j2",
                output_dir / "rules" / "skill-triggers.md",
                manifest,
                result,
            )
            self._render_and_write(
                "rules/memory-flush.md.j2",
                output_dir / "rules" / "memory-flush.md",
                manifest,
                result,
            )

            # Render docs (on-demand)
            # Note: docs contain threat examples, skip security validation
            self._render_and_write(
                "docs/safety.md.j2",
                output_dir / "docs" / "safety.md",
                manifest,
                result,
                validate_security=False,
            )
            self._render_and_write(
                "docs/skills.md.j2",
                output_dir / "docs" / "skills.md",
                manifest,
                result,
                validate_security=False,
            )
            self._render_and_write(
                "docs/task-routing.md.j2",
                output_dir / "docs" / "task-routing.md",
                manifest,
                result,
                validate_security=False,
            )

            # Render settings.json
            self._render_settings_json(output_dir, manifest, result)

            # Render skill definitions
            for skill in manifest.skills:
                skill_dir = output_dir / "skills" / skill.id
                skill_dir.mkdir(exist_ok=True)
                self._render_and_write(
                    "skills/SKILL.md.j2",
                    skill_dir / "SKILL.md",
                    manifest,
                    result,
                    skill=skill,
                )

        except Exception as e:
            result.add_error(f"Failed to render configuration: {e}")
            result.success = False

        return result

    def _render_and_write(
        self,
        template_name: str,
        output_path: Path,
        manifest: Manifest,
        result: RenderResult,
        validate_security: bool = True,
        **extra_context: Any,
    ) -> None:
        """Render a template and write to file.

        Args:
            template_name: Name of the template to render
            output_path: Path to write the rendered output
            manifest: Source manifest
            result: RenderResult to track files
            validate_security: Whether to validate content security
            **extra_context: Additional template variables
        """
        try:
            env = self._get_template_env()
            template = env.get_template(template_name)

            # Build context
            context = self.get_template_context(manifest)
            context.update(extra_context)

            # Render and write
            content = template.render(**context)
            self.write_file_atomic(output_path, content, validate_security=validate_security)

            result.add_file(output_path)

        except Exception as e:
            result.add_error(f"Failed to render {template_name}: {e}")

    def _render_settings_json(
        self,
        output_dir: Path,
        manifest: Manifest,
        result: RenderResult,
    ) -> None:
        """Render settings.json file.

        Args:
            output_dir: Output directory
            manifest: Source manifest
            result: RenderResult to track files
        """
        import json

        settings = self.get_settings_schema()

        # Apply manifest policies to settings
        security_policy = manifest.get_effective_security_policy()
        routing_config = manifest.get_effective_routing_config()

        # Update settings based on policies
        if "allowedCommands" in settings:
            # Configure command permissions based on security policy
            if security_policy.enable_command_blocklist:
                # Add blocked commands to settings
                blocklist = security_policy.command_blocklist or []
                settings["allowedCommands"] = [
                    cmd for cmd in settings.get("allowedCommands", [])
                    if cmd not in blocklist
                ]

            if security_policy.require_command_allowlist:
                # Only allow explicitly permitted commands
                allowlist = security_policy.command_allowlist or []
                if allowlist:
                    settings["allowedCommands"] = allowlist

        # Write settings.json
        settings_path = output_dir / "settings.json"
        try:
            self.write_file_atomic(
                settings_path,
                json.dumps(settings, indent=2),
                validate_security=False,  # JSON is safe
            )
            result.add_file(settings_path)
        except Exception as e:
            result.add_error(f"Failed to write settings.json: {e}")

    def get_settings_schema(self) -> dict[str, Any]:
        """Get the settings schema for Claude Code.

        Returns a JSON schema describing the structure of Claude Code's
        settings.json file.

        Returns:
            JSON schema as a dictionary
        """
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "Claude Code Settings",
            "type": "object",
            "properties": {
                "allowedCommands": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of allowed commands",
                },
                "allowedTools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of allowed tools",
                },
                "permissions": {
                    "type": "object",
                    "properties": {
                        "network": {"type": "boolean"},
                        "filesystem": {
                            "type": "object",
                            "properties": {
                                "read": {"type": "array", "items": {"type": "string"}},
                                "write": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                    },
                },
                "hooks": {
                    "type": "object",
                    "properties": {
                        "preSessionEnd": {"type": "string"},
                        "postSessionStart": {"type": "string"},
                    },
                },
            },
        }

    def install_hooks(self, config_dir: Path) -> dict[str, bool]:
        """Install Claude Code hooks.

        Installs the pre-session-end hook for memory flushing.

        Args:
            config_dir: Configuration directory

        Returns:
            Dictionary mapping hook names to installation status
        """
        results = {}

        # Install pre-session-end hook
        hook_path = config_dir / "hooks" / "pre-session-end.sh"
        try:
            hook_content = """#!/bin/bash
# Pre-session-end hook for VibeSOP
# This hook runs before the session ends

# Trigger memory flush
if command -v vibe &> /dev/null; then
    echo "Flushing session memory..."
    # Note: 'vibe memory flush' command will be available in future release
    # For now, just log that session is ending
    echo "Session ending at $(date)"
fi
"""
            hook_path.parent.mkdir(parents=True, exist_ok=True)
            self.write_file_atomic(hook_path, hook_content, validate_security=False)

            # Make executable
            hook_path.chmod(0o755)

            results["pre-session-end"] = True
        except Exception as e:
            results["pre-session-end"] = False
            # Note: error but don't fail

        return results
