"""Pi Coding Agent platform adapter.

The Pi adapter generates configuration for the Pi coding agent harness,
including AGENTS.md context file, TypeScript extensions for route interception
and session tracking, skill deployments, and prompt templates.

Pi differs from Claude Code in several key ways:
- Uses AGENTS.md instead of CLAUDE.md for context
- Uses TypeScript extensions instead of shell hooks for event interception
- Uses prompt templates (.pi/prompts/) instead of slash commands
- Uses the Agent Skills standard (SKILL.md) for skills
- Has no built-in slash command system — extensions register commands
"""

import json
import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from vibesop.adapters.base import PlatformAdapter
from vibesop.adapters.models import Manifest, RenderResult

logger = logging.getLogger(__name__)


class PiCodingAgentAdapter(PlatformAdapter):
    """Adapter for Pi Coding Agent platform."""

    def __init__(self, project_root: str | Path = ".") -> None:
        super().__init__()
        self._template_env: Environment | None = None
        self._project_root = Path(project_root).resolve()

    @property
    def platform_name(self) -> str:
        return "pi"

    @property
    def config_dir(self) -> Path:
        # Write to project-local .pi/ directory (Pi auto-discovers from here)
        # Note: Pi also auto-discovers from ~/.pi/agent/ globally,
        # but VibeSOP deploys per-project so .pi/ is the right target.
        return self._project_root / ".pi"

    def _get_template_env(self) -> Environment:
        if self._template_env is None:
            template_dir = Path(__file__).parent / "templates" / "pi"
            self._template_env = Environment(
                loader=FileSystemLoader(template_dir),
                autoescape=select_autoescape(),
                trim_blocks=True,
                lstrip_blocks=True,
            )
        return self._template_env

    def render_config(self, manifest: Manifest, output_dir: Path) -> RenderResult:
        """Render Pi Coding Agent configuration from manifest."""
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
            (output_dir / "extensions").mkdir(exist_ok=True)
            (output_dir / "skills").mkdir(exist_ok=True)
            (output_dir / "prompts").mkdir(exist_ok=True)
            (output_dir / "docs").mkdir(exist_ok=True)

            # Render main AGENTS.md to project root (Pi discovers from cwd/parent dirs)
            self._render_and_write(
                "AGENTS.md.j2",
                self._project_root / "AGENTS.md",
                manifest,
                result,
                validate_security=False,
            )

            # Write project-level AGENTS.md only if different from global (~/.pi/agent/)
            self._render_project_agents_md(manifest, result)

            # Render extensions
            self._render_and_write(
                "extensions/vibesop-route.ts.j2",
                output_dir / "extensions" / "vibesop-route.ts",
                manifest,
                result,
                validate_security=False,
            )
            self._render_and_write(
                "extensions/vibesop-track.ts.j2",
                output_dir / "extensions" / "vibesop-track.ts",
                manifest,
                result,
                validate_security=False,
            )

            # Render settings.json
            self._render_settings_json(output_dir, manifest, result)

            # Render docs
            doc_templates = [
                "session-lifecycle.md.j2",
                "routing-protocol.md.j2",
                "safety.md.j2",
                "skills.md.j2",
                "task-routing.md.j2",
            ]
            for doc_template in doc_templates:
                base_name = doc_template.replace(".j2", "")
                self._render_and_write(
                    f"docs/{doc_template}",
                    output_dir / "docs" / base_name,
                    manifest,
                    result,
                    validate_security=False,
                )

            # Render prompt templates for vibe commands
            prompt_templates = [
                "vibe-route.md.j2",
                "vibe-install.md.j2",
                "vibe-list.md.j2",
                "vibe-help.md.j2",
                "vibe-orchestrate.md.j2",
            ]
            for template_name in prompt_templates:
                base_name = template_name.replace(".j2", "")
                self._render_and_write(
                    f"prompts/{template_name}",
                    output_dir / "prompts" / base_name,
                    manifest,
                    result,
                    validate_security=False,
                )

            # Render skill definitions
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
        """Render configuration without skills."""
        result = self.create_render_result(success=True)

        try:
            errors = self.validate_manifest(manifest)
            if errors:
                for error in errors:
                    result.add_error(error)
                result.success = False
                return result

            output_dir = self.ensure_output_dir(output_dir)

            # Create directory structure (no skills/ directory)
            (output_dir / "extensions").mkdir(exist_ok=True)
            (output_dir / "prompts").mkdir(exist_ok=True)
            (output_dir / "docs").mkdir(exist_ok=True)

            # Render main AGENTS.md to project root (Pi discovers from cwd/parent dirs)
            self._render_and_write(
                "AGENTS.md.j2",
                self._project_root / "AGENTS.md",
                manifest,
                result,
                validate_security=False,
            )

            # Write project-level AGENTS.md only if different from global (~/.pi/agent/)
            self._render_project_agents_md(manifest, result)

            # Render extensions
            self._render_and_write(
                "extensions/vibesop-route.ts.j2",
                output_dir / "extensions" / "vibesop-route.ts",
                manifest,
                result,
                validate_security=False,
            )
            self._render_and_write(
                "extensions/vibesop-track.ts.j2",
                output_dir / "extensions" / "vibesop-track.ts",
                manifest,
                result,
                validate_security=False,
            )

            # Render settings.json
            self._render_settings_json(output_dir, manifest, result)

            # Render docs
            doc_templates = [
                "session-lifecycle.md.j2",
                "routing-protocol.md.j2",
                "safety.md.j2",
                "skills.md.j2",
                "task-routing.md.j2",
            ]
            for doc_template in doc_templates:
                base_name = doc_template.replace(".j2", "")
                self._render_and_write(
                    f"docs/{doc_template}",
                    output_dir / "docs" / base_name,
                    manifest,
                    result,
                    validate_security=False,
                )

            # Render prompt templates
            prompt_templates = [
                "vibe-route.md.j2",
                "vibe-install.md.j2",
                "vibe-list.md.j2",
                "vibe-help.md.j2",
                "vibe-orchestrate.md.j2",
            ]
            for template_name in prompt_templates:
                base_name = template_name.replace(".j2", "")
                self._render_and_write(
                    f"prompts/{template_name}",
                    output_dir / "prompts" / base_name,
                    manifest,
                    result,
                    validate_security=False,
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
        """Render a template and write to file."""
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
        super()._render_skill_content(
            skill, skill_dir, result, manifest=manifest,
        )

    def _fallback_skill_content(
        self,
        skill: Any,
        skill_output_path: Path,
        result: RenderResult,
        *,
        dir_name: str | None = None,  # noqa: ARG002
        manifest: Manifest | None = None,
    ) -> None:
        self._render_and_write(
            "skills/SKILL.md.j2",
            skill_output_path,
            manifest,
            result,
            skill=skill,
            validate_security=False,
        )

    def _render_project_agents_md(self, manifest: Manifest, result: RenderResult) -> None:
        """Write project-level AGENTS.md if it doesn't exist."""
        project_path = self._project_root / "AGENTS.md"
        config_path = Path("~/.pi/agent").expanduser() / "AGENTS.md"
        if project_path.resolve() != config_path.resolve() and not project_path.exists():
            self._render_and_write(
                "AGENTS.md.project.j2",
                project_path,
                manifest,
                result,
                validate_security=False,
            )

    def _render_settings_json(
        self,
        output_dir: Path,
        _manifest: Manifest,
        result: RenderResult,
    ) -> None:
        """Render .pi/settings.json with extension and skill configuration."""
        # Use the project-level .pi directory for settings
        project_pi_dir = self._project_root / ".pi"
        project_pi_dir.mkdir(parents=True, exist_ok=True)

        settings_path = project_pi_dir / "settings.json"

        # Merge with existing settings if present
        settings: dict[str, Any] = {
            "extensions": [
                "extensions/vibesop-route.ts",
                "extensions/vibesop-track.ts",
            ],
            "skills": [
                "skills",
            ],
            "prompts": [
                "prompts",
            ],
        }

        if settings_path.exists():
            try:
                existing = json.loads(settings_path.read_text())
                if isinstance(existing, dict):
                    # Merge — our keys take precedence
                    merged = {**existing, **settings}
                    settings = merged
            except (json.JSONDecodeError, OSError):
                pass

        self.write_file_atomic(
            settings_path,
            json.dumps(settings, indent=2),
            validate_security=False,
        )
        result.add_file(settings_path)

    def get_settings_schema(self) -> dict[str, Any]:
        return {
            "$schema": "https://json.schemastore.org/pi-settings.json",
            "title": "Pi Coding Agent Settings",
            "type": "object",
            "properties": {
                "extensions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Paths to extension files",
                },
                "skills": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Paths to skill directories",
                },
                "prompts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Paths to prompt template directories",
                },
            },
        }

    def install_hooks(self, config_dir: Path) -> dict[str, bool]:
        """Install Pi extensions and configuration.

        For Pi, this means ensuring the .pi/ directory has the right
        extensions and skills deployed.
        """
        results: dict[str, bool] = {}

        # Ensure .pi/extensions/ directory exists
        extensions_dir = config_dir / "extensions"
        extensions_dir.mkdir(parents=True, exist_ok=True)

        # Write the route interceptor extension
        route_ext_path = extensions_dir / "vibesop-route.ts"
        try:
            route_content = self._render_extension("vibesop-route.ts.j2")
            self.write_file_atomic(route_ext_path, route_content, validate_security=False)
            results["vibesop-route"] = True
        except Exception as e:
            logger.debug(f"Failed to write vibesop-route.ts: {e}")
            results["vibesop-route"] = False

        # Write the session tracker extension
        track_ext_path = extensions_dir / "vibesop-track.ts"
        try:
            track_content = self._render_extension("vibesop-track.ts.j2")
            self.write_file_atomic(track_ext_path, track_content, validate_security=False)
            results["vibesop-track"] = True
        except Exception as e:
            logger.debug(f"Failed to write vibesop-track.ts: {e}")
            results["vibesop-track"] = False

        return results

    def _render_extension(self, template_name: str) -> str:
        """Render an extension template standalone (without manifest context)."""
        try:
            env = self._get_template_env()
            template = env.get_template(f"extensions/{template_name}")
            context = {
                "version": "0.0.0",
            }
            return template.render(**context)
        except Exception as e:
            logger.warning(f"Failed to render extension template {template_name}: {e}")
            return ""
