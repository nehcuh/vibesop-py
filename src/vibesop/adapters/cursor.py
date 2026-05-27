"""Cursor IDE platform adapter."""

import json
import os
from pathlib import Path
from typing import Any

from vibesop.adapters.base import PlatformAdapter
from vibesop.adapters.models import Manifest, RenderResult


class CursorAdapter(PlatformAdapter):
    """Adapter for Cursor IDE platform."""

    def __init__(self, project_root: str | Path = ".") -> None:
        super().__init__()
        self._project_root = Path(project_root).resolve()

    @property
    def platform_name(self) -> str:
        return "cursor"

    @property
    def config_dir(self) -> Path:
        return Path("~/.config/cursor").expanduser()

    def render_config_only(
        self,
        manifest: Manifest,
        output_dir: Path,
    ) -> RenderResult:
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

            # Generate configuration content
            config_content = self._generate_config(manifest)
            config_path = output_dir / "config.yaml"
            self.write_file_atomic(
                config_path,
                config_content,
                validate_security=False,
            )
            result.add_file(config_path)

            # Generate README if skills exist
            if manifest.skills:
                readme_content = self._generate_readme(manifest)
                readme_path = output_dir / "README.md"
                self.write_file_atomic(
                    readme_path,
                    readme_content,
                    validate_security=False,
                )
                result.add_file(readme_path)

            # Generate llm-config.json
            llm_config_content = self._generate_llm_config()
            llm_config_path = output_dir / "llm-config.json"
            self.write_file_atomic(
                llm_config_path,
                llm_config_content,
                validate_security=False,
            )
            result.add_file(llm_config_path)

            # Generate AGENTS.md for Cursor AI instructions
            agents_content = self._generate_agents_md(manifest)
            agents_path = output_dir / "AGENTS.md"
            self.write_file_atomic(
                agents_path,
                agents_content,
                validate_security=False,
            )
            result.add_file(agents_path)

            # Generate docs/ directory with detailed content
            from vibesop.adapters._shared import render_docs_files

            docs_paths = render_docs_files(output_dir, manifest.skills)
            for doc_path in docs_paths:
                result.add_file(doc_path)

            # Also generate minimal AGENTS.md at project root
            project_agents_path = self._project_root / "AGENTS.md"
            if not project_agents_path.exists():
                project_agents = self._generate_project_agents_md()
                self.write_file_atomic(
                    project_agents_path,
                    project_agents,
                    validate_security=False,
                )
                result.add_file(project_agents_path)

            # Generate VibeSOP environment setup script
            self._render_env_script(output_dir, result)

            # Generate route hook script for quick command support
            self._render_route_hook(output_dir, result)

        except Exception as e:
            result.add_error(f"Failed to render configuration: {e}")
            result.success = False

        return result

    def render_config(self, manifest: Manifest, output_dir: Path) -> RenderResult:
        """Render Cursor configuration from manifest."""
        result = self.render_config_only(manifest, output_dir)
        if not result.success:
            return result

        try:
            # Render skill definitions
            skills_dir = output_dir / "skills"
            skills_dir.mkdir(parents=True, exist_ok=True)

            for skill in manifest.skills:
                dir_name = skill.id.replace("/", "-")
                skill_dir = skills_dir / dir_name
                skill_dir.mkdir(parents=True, exist_ok=True)
                self._render_skill_content(skill, skill_dir, result, dir_name=dir_name)

        except Exception as e:
            result.add_error(f"Failed to render skills: {e}")
            result.success = False

        return result

    def _generate_config(self, manifest: Manifest) -> str:
        from ruamel.yaml import YAML

        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.default_flow_style = False

        config = {
            "version": manifest.metadata.version,
            "platform": manifest.metadata.platform,
            "generated": manifest.metadata.created_at.isoformat(),
            "security": {
                "scan_external_content": manifest.get_effective_security_policy().scan_external_content,
                "max_file_size_mb": manifest.get_effective_security_policy().max_file_size
                / (1024 * 1024),
            },
            "routing": {
                "enable_ai_routing": manifest.get_effective_routing_policy().enable_ai_routing,
                "confidence_threshold": manifest.get_effective_routing_policy().confidence_threshold,
            },
            "skills": [
                {
                    "id": skill.id,
                    "name": skill.name,
                    "description": skill.description,
                    "trigger": skill.trigger_when,
                }
                for skill in manifest.skills
            ],
        }

        if manifest.metadata.author:
            config["author"] = manifest.metadata.author
        if manifest.metadata.description:
            config["description"] = manifest.metadata.description

        from io import StringIO

        stream = StringIO()
        yaml.dump(config, stream)
        return stream.getvalue()

    def _render_skill_content(
        self,
        skill: Any,
        skill_dir: Path,
        result: RenderResult,
        dir_name: str | None = None,
    ) -> None:
        super()._render_skill_content(skill, skill_dir, result, dir_name=dir_name)

    def _generate_readme(self, manifest: Manifest) -> str:
        lines = [
            "# Cursor Configuration",
            "",
            f"**Version**: {manifest.metadata.version}",
            f"**Generated**: {manifest.metadata.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Routing Protocol",
            "",
            "**MANDATORY: Call `vibe route` before any non-trivial task.**",
            "",
            "```bash",
            'vibe route "<user_request>"',
            "```",
            "",
            "Then read `skills/<matched-skill>/SKILL.md` and follow its steps.",
            "",
            "## Quick Commands",
            "",
            "```bash",
            'vibe route --slash "/vibe-help"',
            'vibe route --slash "/vibe-list"',
            'vibe route --slash "/vibe-install <pack>"',
            "```",
            "",
            "## Skills",
            "",
            "Run `vibe skills list` to see available skills.",
            "",
            "## IDE Integration",
            "",
            "Cursor IDE supports .cursorrules and AGENTS.md for AI instructions.",
            "VibeSOP skills are linked via symlinks to `~/.config/cursor/skills/`.",
            "",
            "```bash",
            "source ~/.config/cursor/vibesop-env.sh",
            "```",
            "",
            "---",
            "*Generated by VibeSOP*",
        ]

        return "\n".join(lines)

    @staticmethod
    def _generate_project_agents_md() -> str:
        """Generate minimal project-level AGENTS.md."""
        from vibesop.adapters._shared import generate_slim_agents_index

        return generate_slim_agents_index(
            include_skills_reference=False,
        )

    def _generate_agents_md(self, manifest: Manifest) -> str:
        """Generate slim AGENTS.md index referencing docs/ for details."""
        from vibesop.adapters._shared import generate_slim_agents_index

        return generate_slim_agents_index(
            version=manifest.metadata.version,
            platform_name="Cursor",
            config_dir_label="~/.config/cursor",
            include_skills_reference=True,
        )

    def get_settings_schema(self) -> dict[str, Any]:
        return {
            "$schema": "https://json.schemastore.org/claude-code-settings.json",
            "title": "Cursor Settings",
            "type": "object",
            "properties": {
                "editor": {
                    "type": "object",
                    "properties": {
                        "theme": {"type": "string"},
                        "fontSize": {"type": "integer"},
                    },
                },
                "security": {
                    "type": "object",
                    "properties": {
                        "scanContent": {"type": "boolean"},
                        "maxFileSize": {"type": "integer"},
                    },
                },
            },
        }

    def _generate_llm_config(self) -> str:
        provider = self._detect_provider()

        config = {
            "version": "1.0.0",
            "default_provider": provider,
            "providers": {
                "anthropic": {
                    "api_key": os.getenv("ANTHROPIC_API_KEY", "YOUR_ANTHROPIC_API_KEY"),
                    "base_url": os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
                    "models": {
                        "default": "claude-sonnet-4-20250514",
                        "fast": "claude-haiku-4-20250514",
                        "powerful": "claude-opus-4-20250514",
                    },
                    "timeout": 120,
                    "max_retries": 3,
                    "enabled": bool(os.getenv("ANTHROPIC_API_KEY")),
                },
                "openai": {
                    "api_key": os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY"),
                    "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                    "models": {
                        "default": "gpt-4o",
                        "fast": "gpt-4o-mini",
                        "powerful": "gpt-4o",
                    },
                    "timeout": 120,
                    "max_retries": 3,
                    "enabled": bool(os.getenv("OPENAI_API_KEY")),
                },
            },
            "routing": {
                "enable_ai_routing": True,
                "confidence_threshold": 0.75,
                "cache_enabled": True,
            },
            "preferences": {
                "preferred_model": "default",
                "stream_responses": True,
                "temperature": 0.7,
                "max_tokens": 4096,
            },
        }

        return json.dumps(config, indent=2)

    def _detect_provider(self) -> str:
        explicit_provider = os.getenv("VIBE_LLM_PROVIDER")
        if explicit_provider and explicit_provider in ("anthropic", "openai"):
            return explicit_provider

        if os.getenv("ANTHROPIC_API_KEY"):
            return "anthropic"
        if os.getenv("OPENAI_API_KEY"):
            return "openai"

        return "anthropic"

    def _render_route_hook(
        self,
        output_dir: Path,
        result: RenderResult,
    ) -> None:
        """Render the vibesop-route.sh hook script using the shared template."""
        try:
            from vibesop.adapters._shared import render_route_hook as _shared_route_hook

            hook_content = _shared_route_hook(
                platform="cursor",
                platform_name="Cursor",
                purpose="Quick command handling and auto-routing for Cursor IDE",
                hook_event_name="",
                enable_explicit_overrides=True,
                enable_orchestration=True,
                include_additional_context=True,
                no_match_message=True,
            )
            hook_path = output_dir / "hooks" / "vibesop-route.sh"
            hook_path.parent.mkdir(parents=True, exist_ok=True)
            self.write_file_atomic(hook_path, hook_content, validate_security=False)
            hook_path.chmod(0o755)
            result.add_file(hook_path)
        except Exception as e:
            result.add_warning(f"Failed to write vibesop-route.sh for Cursor: {e}")

    def _render_env_script(
        self,
        output_dir: Path,
        result: RenderResult,
    ) -> None:
        """Render the vibesop-env.sh environment setup script for Cursor IDE."""
        script_content = """#!/bin/bash
# VibeSOP Environment Setup for Cursor IDE
# Generated by VibeSOP v5.4.5
#
# Usage: source ~/.config/cursor/vibesop-env.sh
# Cursor IDE will pick up AGENTS.md and .cursorrules automatically.

# Generate a stable conversation ID for this project session
if command -v python3 &> /dev/null; then
    export CONVERSATION_ID="cursor-$(python3 -c "import os, hashlib; print(hashlib.sha256(os.getcwd().encode()).hexdigest()[:16])")"
fi

# Wrap the vibe command to automatically pass --conversation
vibe() {
    if [ -n "$CONVERSATION_ID" ]; then
        command vibe --conversation "$CONVERSATION_ID" "$@"
    else
        command vibe "$@"
    fi
}

export -f vibe 2>/dev/null || true
"""
        try:
            script_path = output_dir / "vibesop-env.sh"
            self.write_file_atomic(script_path, script_content, validate_security=False)
            script_path.chmod(0o755)
            result.add_file(script_path)
        except Exception as e:
            result.add_warning(f"Failed to write vibesop-env.sh for Cursor: {e}")
