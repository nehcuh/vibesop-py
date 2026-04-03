"""OpenCode platform adapter.

This module provides a simplified adapter for the OpenCode platform,
demonstrating the adapter pattern with minimal complexity.
"""

import json
import os
from pathlib import Path
from typing import Any

from vibesop.adapters.base import PlatformAdapter
from vibesop.adapters.models import Manifest, RenderResult


class OpenCodeAdapter(PlatformAdapter):
    """Adapter for OpenCode platform.

    OpenCode is a simplified platform that uses a single YAML
    configuration file. This adapter demonstrates the adapter
    pattern with minimal complexity.

    Example:
        >>> from vibesop.adapters import OpenCodeAdapter, Manifest
        >>>
        >>> adapter = OpenCodeAdapter()
        >>> manifest = Manifest(...)
        >>> result = adapter.render_config(manifest, Path("~/.opencode"))
        >>> print(f"Created {result.file_count} files")
    """

    def __init__(self) -> None:
        """Initialize the OpenCode adapter."""
        super().__init__()

    @property
    def platform_name(self) -> str:
        """Get platform identifier.

        Returns:
            Platform name 'opencode'
        """
        return "opencode"

    @property
    def config_dir(self) -> Path:
        """Get default configuration directory.

        Returns:
            Path to ~/.opencode
        """
        return Path("~/.opencode").expanduser()

    def render_config(self, manifest: Manifest, output_dir: Path) -> RenderResult:
        """Render OpenCode configuration from manifest.

        Generates a single config.yaml file with all settings.

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

            # Generate configuration content
            config_content = self._generate_config(manifest)

            # Write config.yaml
            config_path = output_dir / "config.yaml"
            self.write_file_atomic(
                config_path,
                config_content,
                validate_security=False,  # YAML is safe
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

        except Exception as e:
            result.add_error(f"Failed to render configuration: {e}")
            result.success = False

        return result

    def _generate_config(self, manifest: Manifest) -> str:
        """Generate configuration YAML content.

        Args:
            manifest: Source manifest

        Returns:
            YAML configuration content
        """
        from ruamel.yaml import YAML

        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.default_flow_style = False

        # Build configuration dictionary
        config = {
            "version": manifest.metadata.version,
            "platform": manifest.metadata.platform,
            "generated": manifest.metadata.created_at.isoformat(),
            "security": {
                "scan_external_content": manifest.get_effective_security_policy().scan_external_content,
                "max_file_size_mb": manifest.get_effective_security_policy().max_file_size / (1024 * 1024),
            },
            "routing": {
                "enable_ai_routing": manifest.get_effective_routing_config().enable_ai_routing,
                "confidence_threshold": manifest.get_effective_routing_config().confidence_threshold,
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

        # Add metadata if present
        if manifest.metadata.author:
            config["author"] = manifest.metadata.author
        if manifest.metadata.description:
            config["description"] = manifest.metadata.description

        # Convert to YAML string
        from io import StringIO

        stream = StringIO()
        yaml.dump(config, stream)
        return stream.getvalue()

    def _generate_readme(self, manifest: Manifest) -> str:
        """Generate README content.

        Args:
            manifest: Source manifest

        Returns:
            README markdown content
        """
        lines = [
            "# OpenCode Configuration",
            "",
            f"**Version**: {manifest.metadata.version}",
            f"**Generated**: {manifest.metadata.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Configuration",
            "",
            "This configuration was generated by VibeSOP.",
            "",
            "## Skills",
            "",
        ]

        if manifest.skills:
            for skill in manifest.skills:
                lines.extend([
                    f"### {skill.id}",
                    "",
                    f"**Name**: {skill.name}",
                    f"**Description**: {skill.description}",
                    f"**Trigger**: {skill.trigger_when}",
                    "",
                ])
        else:
            lines.append("No skills configured.")
            lines.append("")

        lines.extend([
            "## Security",
            "",
            f"- Scan External Content: {manifest.get_effective_security_policy().scan_external_content}",
            f"- Max File Size: {manifest.get_effective_security_policy().max_file_size / (1024 * 1024):.1f} MB",
            "",
            "## Routing",
            "",
            f"- AI Routing: {manifest.get_effective_routing_config().enable_ai_routing}",
            f"- Confidence Threshold: {manifest.get_effective_routing_config().confidence_threshold}",
            "",
            "---",
            "*Generated by VibeSOP*",
        ])

        return "\n".join(lines)

    def get_settings_schema(self) -> dict[str, Any]:
        """Get the settings schema for OpenCode.

        Returns a simple JSON schema for OpenCode settings.

        Returns:
            JSON schema as a dictionary
        """
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "OpenCode Settings",
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

    # Note: install_hooks uses the default implementation from PlatformAdapter
    # which returns an empty dict (OpenCode doesn't support hooks)

    def _generate_llm_config(self) -> str:
        """Generate LLM configuration JSON content.

        Creates a complete LLM configuration with provider settings,
        API keys, models, and timeouts. API keys are read from environment
        variables if available, otherwise placeholder values are used.

        Returns:
            JSON configuration content
        """
        # Detect provider from environment
        provider = self._detect_provider()

        # Build configuration
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
        """Detect default LLM provider from environment.

        Priority:
        1. VIBE_LLM_PROVIDER env var
        2. ANTHROPIC_API_KEY env var
        3. OPENAI_API_KEY env var
        4. Default to 'anthropic'

        Returns:
            Provider name ('anthropic' or 'openai')
        """
        explicit_provider = os.getenv("VIBE_LLM_PROVIDER")
        if explicit_provider and explicit_provider in ("anthropic", "openai"):
            return explicit_provider

        if os.getenv("ANTHROPIC_API_KEY"):
            return "anthropic"
        if os.getenv("OPENAI_API_KEY"):
            return "openai"

        return "anthropic"
