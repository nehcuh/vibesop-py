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

    def __init__(self, project_root: str | Path = ".") -> None:
        """Initialize the OpenCode adapter.

        Args:
            project_root: Path to VibeSOP project root (contains core/skills/)
        """
        super().__init__()
        self._project_root = Path(project_root).resolve()

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

    def render_config_only(
        self,
        manifest: Manifest,
        output_dir: Path,
    ) -> RenderResult:
        """Render configuration without skills.

        This renders config.yaml, README.md, and llm-config.json
        but NOT the skills/ directory. Skills are managed separately.

        Args:
            manifest: Configuration manifest
            output_dir: Directory to write configuration files

        Returns:
            RenderResult with list of created files and any warnings/errors
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

        except Exception as e:
            result.add_error(f"Failed to render configuration: {e}")
            result.success = False

        return result

    def render_config(self, manifest: Manifest, output_dir: Path) -> RenderResult:
        """Render OpenCode configuration from manifest.

        Generates config.yaml, README.md, llm-config.json,
        and copies skill definitions to skills/ directory.

        Args:
            manifest: Configuration manifest
            output_dir: Directory to write configuration files

        Returns:
            RenderResult with list of created files and any warnings/errors
        """
        result = self.render_config_only(manifest, output_dir)
        if not result.success:
            return result

        try:
            # Render skill definitions
            skills_dir = output_dir / "skills"
            skills_dir.mkdir(parents=True, exist_ok=True)

            for skill in manifest.skills:
                skill_dir = skills_dir / skill.id
                skill_dir.mkdir(parents=True, exist_ok=True)
                self._render_skill_content(skill, skill_dir, result)

        except Exception as e:
            result.add_error(f"Failed to render skills: {e}")
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
                "max_file_size_mb": manifest.get_effective_security_policy().max_file_size
                / (1024 * 1024),
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

    def _render_skill_content(
        self,
        skill: Any,
        skill_dir: Path,
        result: RenderResult,
    ) -> None:
        """Render skill content from actual skill file.

        Args:
            skill: Skill definition from manifest
            skill_dir: Directory to write skill files
            result: RenderResult to track files
        """
        skill_id = skill.id if hasattr(skill, "id") else skill.get("id", "")
        skill_output_path = skill_dir / "SKILL.md"

        # Try to find actual skill content from core/skills/
        skill_content = self._find_skill_content(skill_id)

        if skill_content:
            self.write_file_atomic(skill_output_path, skill_content, validate_security=False)
            result.add_file(skill_output_path)
        else:
            # Fallback: generate minimal skill definition
            fallback_content = self._generate_fallback_skill_content(skill)
            self.write_file_atomic(skill_output_path, fallback_content, validate_security=False)
            result.add_file(skill_output_path)

    def _find_skill_content(self, skill_id: str) -> str | None:
        """Find and read actual skill content from core/skills/.

        Args:
            skill_id: Skill identifier (e.g., "systematic-debugging" or "gstack/review")

        Returns:
            Skill file content or None if not found
        """
        if "/" in skill_id:
            # External skill like "gstack/review" or "superpowers/tdd"
            # These don't have local content, return None to use fallback
            return None

        # Built-in skill - try to find in core/skills/
        skill_paths = [
            self._project_root / "core" / "skills" / skill_id / "SKILL.md",
            self._project_root / "skills" / skill_id / "SKILL.md",
            Path(__file__).parent.parent.parent / "core" / "skills" / skill_id / "SKILL.md",
        ]

        for skill_path in skill_paths:
            if skill_path.exists():
                try:
                    return skill_path.read_text(encoding="utf-8")
                except Exception as e:
                    import logging

                    logging.getLogger(__name__).debug(f"Failed to read skill file {skill_path}: {e}")

        return None

    def _generate_fallback_skill_content(self, skill: Any) -> str:
        """Generate minimal fallback SKILL.md for external skills."""
        skill_id = skill.id if hasattr(skill, "id") else skill.get("id", "")
        name = skill.name if hasattr(skill, "name") else skill.get("name", skill_id)
        description = skill.description if hasattr(skill, "description") else skill.get("description", "")
        trigger = skill.trigger_when if hasattr(skill, "trigger_when") else skill.get("trigger_when", "")

        lines = [
            "---",
            f"id: {skill_id}",
            f"name: {name}",
            f"description: {description}",
            "---",
            "",
            f"# {name}",
            "",
            f"{description}",
            "",
        ]
        if trigger:
            lines.extend(["## Trigger", "", f"{trigger}", ""])
        lines.extend(["", "*External skill — install the source pack for full content.*", ""])
        return "\n".join(lines)

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
            "## CRITICAL AGENT INSTRUCTION",
            "",
            "**Do NOT guess or hallucinate rules.** When you need information from any category below, you **MUST** use the appropriate tool to fetch the file contents before proceeding.",
            "",
            "## AI-Powered Skill Routing",
            "",
            "**⚠️ MANDATORY: ALWAYS call vibe route before starting ANY non-trivial task**",
            "This is NOT optional — routing ensures the correct skill is loaded for the task.",
            "",
            "### MANDATORY Workflow (必须遵循 - 无条件执行)",
            "",
            "**Step 1**: Call routing to get recommendations",
            '```bash\nvibe route "<user_request>"\n```',
            "",
            "**Step 2**: Read the recommended skill file ⚠️ CRITICAL STEP",
            "```markdown\nread skills/<matched-skill>/SKILL.md\n```",
            "",
            "**Step 3**: Execute according to the skill's steps",
            "- Do not skip skill definitions",
            "- Strictly follow the workflow described in the skill",
            "",
            "**Step 4**: Run verification after completion",
            "```bash\n# Run appropriate verification commands as required by the skill\n```",
            "",
            "### Example",
            "```bash",
            '# Step 1: Get recommendation\nvibe route "帮我调试这个 bug"\n# Output: Matched skill: systematic-debugging (95% confidence)',
            "",
            "# Step 2: Read skill definition (MANDATORY)",
            "read skills/systematic-debugging/SKILL.md",
            "",
            "# Step 3: Follow systematic debugging workflow",
            "# Gather info → Identify patterns → Form hypotheses → Test → Fix root cause",
            "",
            "# Step 4: Run verification",
            "```",
            "",
            "**Why use AI routing?**",
            "- ✅ **Multi-layer matching** - keyword, TF-IDF, embedding, fuzzy",
            "- ✅ **Semantic understanding** - understands intent, not just keywords",
            "- ✅ **Preference learning** - gets better the more you use it",
            "- ✅ **Context-aware** - considers conversation history and recent work",
            "",
            "**7-Layer Routing System:**",
            "- **Layer 0**: Explicit override (`/review`, `use tdd`)",
            "- **Layer 1**: Scenario patterns (debug, review, refactor, etc.)",
            "- **Layer 2**: AI Semantic Triage (Haiku/GPT, optional)",
            "- **Layer 3**: Keyword matching (exact token matching)",
            "- **Layer 4**: TF-IDF semantic matching (cosine similarity)",
            "- **Layer 5**: Embedding-based matching (vector similarity)",
            "- **Layer 6**: Fuzzy matching (Levenshtein distance for typos)",
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
                lines.extend(
                    [
                        f"### {skill.id}",
                        "",
                        f"**Name**: {skill.name}",
                        f"**Description**: {skill.description}",
                        f"**Trigger**: {skill.trigger_when}",
                        "",
                    ]
                )
        else:
            lines.append("No skills configured.")
            lines.append("")

        lines.extend(
            [
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
            ]
        )

        return "\n".join(lines)

    def get_settings_schema(self) -> dict[str, Any]:
        """Get the settings schema for OpenCode.

        Returns a simple JSON schema for OpenCode settings.

        Returns:
            JSON schema as a dictionary
        """
        return {
            "$schema": "https://json.schemastore.org/claude-code-settings.json",
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
