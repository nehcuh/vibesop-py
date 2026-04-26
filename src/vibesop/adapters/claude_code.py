"""Claude Code platform adapter.

This module provides the adapter for generating Claude Code
configuration files from a manifest.
"""

import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from vibesop.adapters.base import PlatformAdapter
from vibesop.adapters.models import Manifest, RenderResult

logger = logging.getLogger(__name__)


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

    def __init__(self, project_root: str | Path = ".") -> None:
        """Initialize the Claude Code adapter.

        Args:
            project_root: Path to VibeSOP project root (contains core/skills/)
        """
        super().__init__()
        self._template_env: Environment | None = None
        self._project_root = Path(project_root).resolve()

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
                validate_security=False,
            )

            # Write project-level CLAUDE.md (Claude Code reads ./CLAUDE.md with highest priority)
            self._render_project_claude_md(manifest, result)

            # Render rules (always-loaded)
            self._render_and_write(
                "rules/behaviors.md.j2",
                output_dir / "rules" / "behaviors.md",
                manifest,
                result,
                validate_security=False,
            )
            self._render_and_write(
                "rules/routing.md.j2",
                output_dir / "rules" / "routing.md",
                manifest,
                result,
                validate_security=False,
            )
            self._render_and_write(
                "rules/skill-triggers.md.j2",
                output_dir / "rules" / "skill-triggers.md",
                manifest,
                result,
                validate_security=False,
            )
            self._render_and_write(
                "rules/memory-flush.md.j2",
                output_dir / "rules" / "memory-flush.md",
                manifest,
                result,
                validate_security=False,
            )

            # Render docs (on-demand)
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

            # Render Agent Runtime hook scripts
            self._render_route_hook(output_dir, result)
            self._render_track_hook(output_dir, result)

            # Render skill definitions - copy actual content from core/skills/
            for skill in manifest.skills:
                dir_name = skill.id.replace("/", "-")
                skill_dir = output_dir / "skills" / dir_name
                skill_dir.mkdir(parents=True, exist_ok=True)
                self._render_skill_content(skill, skill_dir, manifest, result)

        except Exception as e:
            result.add_error(f"Failed to render configuration: {e}")
            result.success = False

        return result

    def render_config_only(self, manifest: Manifest, output_dir: Path) -> RenderResult:
        """Render configuration without skills.

        This renders CLAUDE.md, rules/, docs/, and settings.json
        but NOT the skills/ directory. Skills are managed separately
        by SkillStorage with symlinks.

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

            # Create directory structure (no skills/ directory)
            (output_dir / "rules").mkdir(exist_ok=True)
            (output_dir / "docs").mkdir(exist_ok=True)
            (output_dir / "hooks").mkdir(exist_ok=True)

            # Render main CLAUDE.md
            self._render_and_write(
                "CLAUDE.md.j2",
                output_dir / "CLAUDE.md",
                manifest,
                result,
                validate_security=False,
            )

            # Write project-level CLAUDE.md (Claude Code reads ./CLAUDE.md with highest priority)
            self._render_project_claude_md(manifest, result)

            # Render rules (always-loaded)
            self._render_and_write(
                "rules/behaviors.md.j2",
                output_dir / "rules" / "behaviors.md",
                manifest,
                result,
                validate_security=False,
            )
            self._render_and_write(
                "rules/routing.md.j2",
                output_dir / "rules" / "routing.md",
                manifest,
                result,
                validate_security=False,
            )
            self._render_and_write(
                "rules/skill-triggers.md.j2",
                output_dir / "rules" / "skill-triggers.md",
                manifest,
                result,
                validate_security=False,
            )
            self._render_and_write(
                "rules/memory-flush.md.j2",
                output_dir / "rules" / "memory-flush.md",
                manifest,
                result,
                validate_security=False,
            )

            # Render docs (on-demand)
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

            # Render Agent Runtime hook scripts
            self._render_route_hook(output_dir, result)
            self._render_track_hook(output_dir, result)

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

    def _render_skill_content(
        self,
        skill: Any,
        skill_dir: Path,
        manifest: Manifest,
        result: RenderResult,
    ) -> None:
        """Render skill content from actual skill file.

        Args:
            skill: Skill definition from manifest
            skill_dir: Directory to write skill files
            manifest: Source manifest
            result: RenderResult to track files
        """
        skill_id = skill.id if hasattr(skill, "id") else skill.get("id", "")
        skill_output_path = skill_dir / "SKILL.md"

        # Try to find actual skill content from core/skills/
        skill_content = self._find_skill_content(skill_id)

        if skill_content:
            # Use actual skill content
            self.write_file_atomic(skill_output_path, skill_content, validate_security=False)
            result.add_file(skill_output_path)
        else:
            # Fallback to template for external skills (superpowers, gstack, etc.)
            self._render_and_write(
                "skills/SKILL.md.j2",
                skill_output_path,
                manifest,
                result,
                skill=skill,
                validate_security=False,
            )

    def _render_project_claude_md(self, manifest: Manifest, result: RenderResult) -> None:
        """Write project-level CLAUDE.md if it doesn't exist.

        Claude Code reads CLAUDE.md from both ~/.claude/CLAUDE.md (global)
        and ./CLAUDE.md (project-level, highest priority). Writing to the
        project root ensures VibeSOP routing instructions are always loaded,
        even when running Claude Code from different project directories.

        Args:
            manifest: Configuration manifest
            result: RenderResult to track files
        """
        project_path = self._project_root / "CLAUDE.md"
        config_path = Path("~/.claude").expanduser() / "CLAUDE.md"
        if project_path.resolve() != config_path.resolve() and not project_path.exists():
            self._render_and_write(
                "CLAUDE.md.j2",
                project_path,
                manifest,
                result,
                validate_security=False,
            )

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

        # Update settings based on policies
        if "allowedCommands" in settings:
            # Configure command permissions based on security policy
            if security_policy.enable_command_blocklist:
                # Add blocked commands to settings
                blocklist = security_policy.command_blocklist or []
                settings["allowedCommands"] = [
                    cmd for cmd in settings.get("allowedCommands", []) if cmd not in blocklist
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
            "$schema": "https://json.schemastore.org/claude-code-settings.json",
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


    def _render_route_hook(
        self,
        output_dir: Path,
        result: RenderResult,
    ) -> None:
        """Render the vibesop-route.sh hook script using the shared template.

        Delegates to ``render_route_hook()`` in ``_shared.py`` so that
        Claude Code, OpenCode, and Kimi CLI all produce the same hook
        script structure.

        Args:
            output_dir: Output directory (hooks/ will be created here)
            result: RenderResult to track files
        """
        try:
            from vibesop.adapters._shared import render_route_hook as _shared_route_hook

            hook_content = _shared_route_hook(
                platform="claude-code",
                platform_name="Claude Code",
                purpose="Trigger VibeSOP routing and inject skill context",
                enable_explicit_overrides=True,
                enable_orchestration=True,
                include_additional_context=True,
                no_match_message=True,
            )
            hook_path = output_dir / "hooks" / "vibesop-route.sh"
            self.write_file_atomic(hook_path, hook_content, validate_security=False)
            hook_path.chmod(0o755)
            result.add_file(hook_path)
        except Exception as e:
            result.add_warning(f"Failed to write vibesop-route.sh: {e}")

    def _render_track_hook(
        self,
        output_dir: Path,
        result: RenderResult,
    ) -> None:
        """Render the vibesop-track.sh hook script.

        This script can be used as a PreToolUse hook on platforms
        that support it. It tracks tool usage for session context.

        Args:
            output_dir: Output directory (hooks/ will be created here)
            result: RenderResult to track files
        """
        try:
            env = self._get_template_env()
            template = env.get_template("hooks/vibesop-track.sh.j2")
            hook_content = template.render(version="4.3.0")
            hook_path = output_dir / "hooks" / "vibesop-track.sh"
            self.write_file_atomic(hook_path, hook_content, validate_security=False)
            hook_path.chmod(0o755)
            result.add_file(hook_path)
        except Exception as e:
            result.add_warning(f"Failed to write vibesop-track.sh: {e}")

    def install_hooks(self, config_dir: Path) -> dict[str, bool]:
        """Install Claude Code hooks.

        Installs the pre-session-end hook for memory flushing,
        plus Agent Runtime hooks (vibesop-route.sh, vibesop-track.sh)
        for platforms that support UserPromptSubmit / PreToolUse hooks.

        Args:
            config_dir: Configuration directory

        Returns:
            Dictionary mapping hook names to installation status
        """
        results: dict[str, bool] = {}

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
            logger.debug(f"Failed to install pre-session-end hook: {e}")
            results["pre-session-end"] = False
            # Note: error but don't fail

        # Install Agent Runtime route hook (uses shared template)
        route_hook_path = config_dir / "hooks" / "vibesop-route.sh"
        try:
            from vibesop.adapters._shared import render_route_hook as _shared_route_hook

            route_content = _shared_route_hook(
                platform="claude-code",
                platform_name="Claude Code",
                purpose="Trigger VibeSOP routing and inject skill context",
                enable_explicit_overrides=True,
                enable_orchestration=True,
                include_additional_context=True,
                no_match_message=True,
            )
            route_hook_path.parent.mkdir(parents=True, exist_ok=True)
            self.write_file_atomic(route_hook_path, route_content, validate_security=False)
            route_hook_path.chmod(0o755)
            results["vibesop-route"] = True
        except Exception as e:
            logger.debug(f"Failed to install vibesop-route hook: {e}")
            results["vibesop-route"] = False

        # Install Agent Runtime track hook
        track_hook_path = config_dir / "hooks" / "vibesop-track.sh"
        try:
            env = self._get_template_env()
            template = env.get_template("hooks/vibesop-track.sh.j2")
            track_content = template.render(version="4.3.0")
            track_hook_path.parent.mkdir(parents=True, exist_ok=True)
            self.write_file_atomic(track_hook_path, track_content, validate_security=False)
            track_hook_path.chmod(0o755)
            results["vibesop-track"] = True
        except Exception as e:
            logger.debug(f"Failed to install vibesop-track hook: {e}")
            results["vibesop-track"] = False

        return results
