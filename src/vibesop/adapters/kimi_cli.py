"""Kimi Code CLI platform adapter.

This module provides the adapter for generating Kimi Code CLI
configuration files from a manifest.

Kimi Code CLI uses a single TOML configuration file (~/.kimi/config.toml)
and discovers skills from ~/.kimi/skills/ directory. The skill format
(SKILL.md with YAML frontmatter) is fully compatible with the Agent Skills
open standard used by Claude Code.

Example:
    >>> from vibesop.adapters import KimiCliAdapter, Manifest
    >>>
    >>> adapter = KimiCliAdapter()
    >>> manifest = Manifest(...)
    >>> result = adapter.render_config(manifest, Path("~/.kimi"))
    >>> print(f"Created {result.file_count} files")
"""

from pathlib import Path
from typing import Any

from vibesop.adapters.base import PlatformAdapter
from vibesop.adapters.models import Manifest, RenderResult


class KimiCliAdapter(PlatformAdapter):
    """Adapter for Kimi Code CLI platform.

    Generates Kimi Code CLI configuration files including:
    - config.toml (main configuration)
    - skills/*/SKILL.md (skill definitions)
    - README.md (skill catalog and usage guide)

    Kimi Code CLI uses the Agent Skills open standard, making its
    skill format fully compatible with Claude Code skills.

    Example:
        >>> from vibesop.adapters import KimiCliAdapter, Manifest
        >>>
        >>> adapter = KimiCliAdapter()
        >>> manifest = Manifest(...)
        >>> result = adapter.render_config(manifest, Path("~/.kimi"))
        >>> print(f"Created {result.file_count} files")
    """

    def __init__(self, project_root: str | Path = ".") -> None:
        """Initialize the Kimi CLI adapter.

        Args:
            project_root: Path to VibeSOP project root (contains core/skills/)
        """
        super().__init__()
        self._project_root = Path(project_root).resolve()

    @property
    def platform_name(self) -> str:
        """Get platform identifier.

        Returns:
            Platform name 'kimi-cli'
        """
        return "kimi-cli"

    @property
    def config_dir(self) -> Path:
        """Get default configuration directory.

        Returns:
            Path to ~/.kimi
        """
        return Path("~/.kimi").expanduser()

    def render_config_only(
        self,
        manifest: Manifest,
        output_dir: Path,
    ) -> RenderResult:
        """Render configuration without skills.

        This renders config.toml and README.md but NOT the skills/
        directory. Skills are managed separately.

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
            config_path = output_dir / "config.toml"
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

        except Exception as e:
            result.add_error(f"Failed to render configuration: {e}")
            result.success = False

        return result

    def render_config(self, manifest: Manifest, output_dir: Path) -> RenderResult:
        """Render Kimi Code CLI configuration from manifest.

        Generates config.toml, README.md, and copies skill definitions
        to skills/ directory.

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
        """Generate configuration TOML content.

        Args:
            manifest: Source manifest

        Returns:
            TOML configuration content
        """
        lines: list[str] = [
            "# VibeSOP Configuration for Kimi Code CLI",
            f"# Generated: {manifest.metadata.created_at.isoformat()}",
            f"# Version: {manifest.metadata.version}",
            f"# Platform: {manifest.metadata.platform}",
            "",
            "# Merge skills from all brand directories (kimi, claude, codex)",
            "merge_all_available_skills = true",
            "",
            "# Default model for coding tasks",
            'default_model = "kimi-for-coding"',
            "",
            "# Default settings",
            "default_thinking = false",
            "default_yolo = false",
            "default_plan_mode = false",
            "",
            "[models.kimi-for-coding]",
            'provider = "kimi-for-coding"',
            'model = "kimi-for-coding"',
            "max_context_size = 262144",
            "",
            "[loop_control]",
            "max_steps_per_turn = 500",
            "max_retries_per_step = 3",
            "max_ralph_iterations = 0",
            "reserved_context_size = 50000",
            "compaction_trigger_ratio = 0.85",
            "",
            "[background]",
            "max_running_tasks = 4",
            "keep_alive_on_exit = false",
            "agent_task_timeout_s = 900",
            "",
        ]

        # Add metadata if present
        if manifest.metadata.author:
            lines.extend([
                f"# Author: {manifest.metadata.author}",
                "",
            ])
        if manifest.metadata.description:
            lines.extend([
                f"# Description: {manifest.metadata.description}",
                "",
            ])

        # Add security settings
        security = manifest.get_effective_security_policy()
        lines.extend([
            "[vibesop.security]",
            f"scan_external_content = {str(security.scan_external_content).lower()}",
            f"max_file_size_mb = {security.max_file_size / (1024 * 1024):.1f}",
            "",
        ])

        # Add routing settings
        routing = manifest.get_effective_routing_config()
        lines.extend([
            "[vibesop.routing]",
            f"enable_ai_routing = {str(routing.enable_ai_routing).lower()}",
            f"confidence_threshold = {routing.confidence_threshold}",
            "",
        ])

        # Add skills catalog
        if manifest.skills:
            lines.extend([
                "# Skills configured by VibeSOP",
                "# Skills are installed in ~/.kimi/skills/",
                "",
                "[[vibesop.skills]]",
            ])
            for skill in manifest.skills:
                # Escape quotes and remove newlines for TOML strings
                safe_description = self._escape_toml_string(skill.description)
                safe_trigger = self._escape_toml_string(skill.trigger_when)

                lines.extend([
                    f'id = "{skill.id}"',
                    f'name = "{skill.name}"',
                    f'description = "{safe_description}"',
                    f'trigger = "{safe_trigger}"',
                    "",
                    "[[vibesop.skills]]",
                ])
            # Remove the last empty [[vibesop.skills]]
            lines.pop()

        return "\n".join(lines)

    def _escape_toml_string(self, text: str) -> str:
        """Escape text for safe use in TOML double-quoted strings.

        Args:
            text: Input text that may contain newlines, quotes, or other special characters

        Returns:
            Escaped text safe for TOML double-quoted strings
        """
        if not text:
            return ""

        # Remove newlines and replace with spaces
        text = text.replace('\n', ' ')
        text = text.replace('\r', ' ')

        # Collapse multiple spaces into one
        import re
        text = re.sub(r'\s+', ' ', text)

        # Escape backslashes and quotes
        text = text.replace('\\', '\\\\')
        text = text.replace('"', '\\"')

        return text.strip()

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
            "# Kimi Code CLI Configuration",
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
            "This configuration was generated by VibeSOP for Kimi Code CLI.",
            "",
            "Kimi Code CLI loads skills automatically from:",
            "- `~/.kimi/skills/` (brand directory, highest priority)",
            "- `~/.config/agents/skills/` (generic directory)",
            "- `.kimi/skills/` (project-level, when inside project)",
            "",
            "Skills are compatible with the Agent Skills open standard.",
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
        """Get the settings schema for Kimi Code CLI.

        Returns a JSON schema for Kimi Code CLI settings.

        Returns:
            JSON schema as a dictionary
        """
        return {
            "$schema": "https://json.schemastore.org/kimi-cli-settings.json",
            "title": "Kimi Code CLI Settings",
            "type": "object",
            "properties": {
                "default_model": {
                    "type": "string",
                    "description": "Default model name",
                },
                "default_thinking": {
                    "type": "boolean",
                    "description": "Enable thinking mode by default",
                },
                "default_yolo": {
                    "type": "boolean",
                    "description": "Enable YOLO (auto-approve) mode by default",
                },
                "theme": {
                    "type": "string",
                    "enum": ["dark", "light"],
                    "description": "Terminal color theme",
                },
                "merge_all_available_skills": {
                    "type": "boolean",
                    "description": "Merge skills from all brand directories",
                },
                "loop_control": {
                    "type": "object",
                    "properties": {
                        "max_steps_per_turn": {"type": "integer"},
                        "max_retries_per_step": {"type": "integer"},
                        "reserved_context_size": {"type": "integer"},
                        "compaction_trigger_ratio": {"type": "number"},
                    },
                },
            },
        }

    # Note: install_hooks uses the default implementation from PlatformAdapter
    # which returns an empty dict. Kimi Code CLI supports hooks via inline
    # [[hooks]] arrays in config.toml, which is a different mechanism from
    # Claude Code's file-based hooks. Future versions may implement config.toml
    # hook injection.
