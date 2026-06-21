"""File-based platform adapter — shared base for OpenCode, Kimi CLI, Cursor.

Extracts common rendering logic that was previously duplicated across
opencode.py, kimi_cli.py, and cursor.py. Each platform now only overrides
the 3-5 things that are genuinely different.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from vibesop.adapters._shared import (
    generate_slim_agents_index,
    render_docs_files,
    render_route_hook,
)
from vibesop.adapters.base import PlatformAdapter
from vibesop.adapters.models import Manifest, RenderResult


class FileBasedAdapter(PlatformAdapter):
    """Base class for file-based platform integrations.

    File-based platforms inject skills through AGENTS.md context files
    and on-demand documentation. Subclasses only override:
      - platform_name, config_dir
      - config_format() -> "yaml" or "toml"
      - _generate_config() if the config structure differs
      - _detect_provider() if provider detection differs
    """

    # ---- Subclasses MUST override ----
    @property
    def platform_name(self) -> str:
        raise NotImplementedError

    @property
    def config_dir(self) -> Path:
        raise NotImplementedError

    @property
    def config_format(self) -> str:
        """Config file format: 'yaml' or 'toml'."""
        return "yaml"

    @property
    def platform_label(self) -> str:
        """Human-readable platform name for docs."""
        return self.platform_name.replace("-", " ").title()

    @property
    def config_dir_label(self) -> str:
        """Config directory path label for docs."""
        return str(self.config_dir)

    # ---- Hook configuration (subclasses can override) ----
    def _get_hook_event_name(self) -> str:
        return ""

    def _get_enable_explicit_overrides(self) -> bool:
        return True

    def _get_enable_orchestration(self) -> bool:
        return True

    def _get_include_additional_context(self) -> bool:
        return False

    def _get_no_match_message(self) -> bool:
        return False

    # ---- Provider detection ----
    def _detect_provider(self) -> str:
        """Detect the default LLM provider from environment."""
        if os.getenv("ANTHROPIC_API_KEY"):
            return "anthropic"
        if os.getenv("OPENAI_API_KEY"):
            return "openai"
        return "anthropic"

    def _detect_api_key(self) -> str | None:
        """Detect the API key for the default provider."""
        provider = self._detect_provider()
        if provider == "anthropic":
            return os.getenv("ANTHROPIC_API_KEY")
        if provider == "openai":
            return os.getenv("OPENAI_API_KEY")
        return None

    def _detect_model(self) -> str:
        """Detect the default model for the provider."""
        provider = self._detect_provider()
        if provider == "anthropic":
            return "claude-sonnet-4-6"
        return "gpt-4o"

    # ---- Config generation ----
    def _generate_config(self, manifest: Manifest) -> str:
        """Generate platform config file content.

        Override in subclasses if the config format differs.
        """
        import yaml

        config = {
            "version": manifest.metadata.version,
            "platform": self.platform_name,
            "security": {
                "scan_external": manifest.get_effective_security_policy().scan_external_content,
                "max_file_size": manifest.get_effective_security_policy().max_file_size,
            },
            "routing": {
                "enable_ai_routing": manifest.get_effective_routing_policy().enable_ai_routing,
                "confidence_threshold": manifest.get_effective_routing_policy().confidence_threshold,
            },
            "skills": [s.id for s in manifest.skills],
        }
        return yaml.dump(config, default_flow_style=False, allow_unicode=True)

    def _generate_readme(self, manifest: Manifest) -> str:
        """Generate README for the platform config directory."""
        readme_lines = [
            f"# VibeSOP Configuration for {self.platform_label}",
            "",
            f"This directory is managed by VibeSOP v{manifest.metadata.version}.",
            "Do not edit these files manually — use `vibe switch` to update.",
            "",
            "## Skills Installed",
            "",
        ]
        for s in manifest.skills:
            readme_lines.append(f"- **{s.id}** — {s.description}")
        readme_lines.extend(
            [
                "",
                "## Documentation",
                "",
                "- `AGENTS.md` — AI agent context file",
                "- `docs/routing.md` — Routing protocol details",
                "- `docs/session-lifecycle.md` — Session lifecycle events",
                "- `docs/skills-catalog.md` — Full skill catalog",
                "- `docs/quick-commands.md` — Quick command reference",
            ]
        )
        return "\n".join(readme_lines) + "\n"

    def _generate_llm_config(self) -> str:
        """Generate llm-config.json for provider/model detection."""
        provider = self._detect_provider()
        model = self._detect_model()
        api_key = self._detect_api_key()

        config = {
            "provider": provider,
            "models": {
                provider: {
                    "default": model,
                    "available": [model],
                }
            },
            "routing": {
                "vibesop_enabled": True,
                "confidence_threshold": 0.6,
            },
        }
        if api_key:
            config["api_key_env"] = (
                "ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY"
            )

        return json.dumps(config, indent=2) + "\n"

    def _generate_agents_md(self, manifest: Manifest) -> str:
        """Generate AGENTS.md context file for the platform."""
        return generate_slim_agents_index(
            platform_name=self.platform_label,
            config_dir_label=self.config_dir_label,
            include_skills_reference=bool(manifest.skills),
        )

    def _render_env_script(self, output_dir: Path, result: RenderResult) -> None:
        """Render vibesop-env.sh environment script."""
        env_content = self._generate_env_script()
        env_path = output_dir / "vibesop-env.sh"
        self.write_file_atomic(env_path, env_content, validate_security=False)
        result.add_file(env_path)

    def _generate_env_script(self) -> str:
        """Generate environment setup script."""
        return (
            "#!/usr/bin/env bash\n"
            f"# VibeSOP environment setup for {self.platform_label}\n"
            'export CONVERSATION_ID="$(date +%s)-$$"\n'
            'vibe() { command vibe "$@" --conversation "$CONVERSATION_ID"; }\n'
        )

    def _render_route_hook(self, output_dir: Path, result: RenderResult) -> None:
        """Render the route interceptor hook script."""
        hook_content = render_route_hook(
            platform=self.platform_name,
            platform_name=self.platform_label,
            hook_event_name=self._get_hook_event_name(),
            enable_explicit_overrides=self._get_enable_explicit_overrides(),
            enable_orchestration=self._get_enable_orchestration(),
            include_additional_context=self._get_include_additional_context(),
            no_match_message=self._get_no_match_message(),
        )
        hooks_dir = output_dir / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        hook_path = hooks_dir / "vibesop-route.sh"
        self.write_file_atomic(hook_path, hook_content, validate_security=False)
        hook_path.chmod(0o755)
        result.add_file(hook_path)

    # ---- Main rendering pipeline ----
    def render_config_only(
        self,
        manifest: Manifest,
        output_dir: Path,
    ) -> RenderResult:
        """Render all configuration files except skills.

        This is the unified rendering pipeline shared by OpenCode, Kimi CLI,
        and Cursor. Subclasses override individual steps rather than the
        whole pipeline.
        """
        result = self.create_render_result(success=True)

        try:
            errors = self.validate_manifest(manifest)
            if errors:
                for error in errors:
                    result.add_error(error)
                result.success = False
                return result

            output_dir = self.ensure_output_dir(output_dir)

            # 1. Config file (yaml or toml depending on config_format)
            self._render_config_file(manifest, output_dir, result)

            # 2. README if skills exist
            if manifest.skills:
                readme_content = self._generate_readme(manifest)
                readme_path = output_dir / "README.md"
                self.write_file_atomic(readme_path, readme_content, validate_security=False)
                result.add_file(readme_path)

            # 3. LLM config (shared across all file-based adapters)
            llm_config = self._generate_llm_config()
            llm_path = output_dir / "llm-config.json"
            self.write_file_atomic(llm_path, llm_config, validate_security=False)
            result.add_file(llm_path)

            # 4. AGENTS.md context file
            agents_content = self._generate_agents_md(manifest)
            agents_path = output_dir / "AGENTS.md"
            self.write_file_atomic(agents_path, agents_content, validate_security=False)
            result.add_file(agents_path)

            # 5. Docs files
            docs_paths = render_docs_files(output_dir, manifest.skills)
            for doc_path in docs_paths:
                result.add_file(doc_path)

            # 6. Project-level AGENTS.md (only if it doesn't exist)
            project_agents = self._project_root / "AGENTS.md"
            if not project_agents.exists():
                slim_agents = generate_slim_agents_index(
                    platform_name=self.platform_label,
                    config_dir_label=self.config_dir_label,
                    include_skills_reference=False,
                )
                self.write_file_atomic(project_agents, slim_agents, validate_security=False)

            # 7. Environment script
            self._render_env_script(output_dir, result)

            # 8. Route hook
            self._render_route_hook(output_dir, result)

        except Exception as e:
            result.add_error(str(e))
            result.success = False

        return result

    def _render_config_file(
        self, manifest: Manifest, output_dir: Path, result: RenderResult
    ) -> None:
        """Render the platform config file. Override in subclasses if needed."""
        config_content = self._generate_config(manifest)
        ext = "toml" if self.config_format == "toml" else "yaml"
        config_path = output_dir / f"config.{ext}"
        self.write_file_atomic(config_path, config_content, validate_security=False)
        result.add_file(config_path)

    def render_config(self, manifest: Manifest, output_dir: Path) -> RenderResult:
        """Full render: config + skills."""
        result = self.render_config_only(manifest, output_dir)
        if not result.success:
            return result

        skills_dir = output_dir / "skills"
        for skill in manifest.skills:
            dir_name = skill.id.replace("/", "-")
            skill_dir = skills_dir / dir_name
            skill_dir.mkdir(parents=True, exist_ok=True)
            self._render_skill_content(
                skill,
                skill_dir,
                result,
                dir_name=dir_name,
                manifest=manifest,
            )

        self.clean_orphan_skills(manifest, output_dir)
        return result

    def get_settings_schema(self) -> dict[str, Any]:
        """Get the settings schema for this platform."""
        return {
            "type": "object",
            "properties": {
                "version": {"type": "string"},
                "platform": {"type": "string"},
                "security": {"type": "object"},
                "routing": {"type": "object"},
                "skills": {"type": "array", "items": {"type": "string"}},
            },
        }
