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

import re
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

        Note: For Kimi CLI, this generates a VibeSOP configuration fragment
        that should be merged with the auto-generated Kimi CLI config.
        Users should run 'kimi' first to create the default config,
        then use '/login' to authenticate.

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

            # Generate VibeSOP configuration fragment
            config_content = self._generate_config(manifest)
            config_path = output_dir / "config.toml"

            # Auto-merge with existing config if present (preserves auth/providers)
            if config_path.exists():
                config_content = self._merge_config_with_existing(config_path, config_content)
            else:
                result.add_warning(
                    "Kimi CLI first-time setup: "
                    "1. Run 'kimi' to generate default config, "
                    "2. Run '/login' to authenticate, "
                    "3. Then run 'vibe switch kimi-cli -f' to add VibeSOP hooks"
                )

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

            # Render auto-routing hook script
            self._render_route_hook(output_dir, result)

        except Exception as e:
            result.add_error(f"Failed to render configuration: {e}")
            result.success = False

        return result

    def render_config(self, manifest: Manifest, output_dir: Path) -> RenderResult:
        """Render Kimi Code CLI configuration from manifest.

        Generates config.toml, README.md, AGENTS.md, and copies skill definitions
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
                dir_name = skill.id.replace("/", "-")
                skill_dir = skills_dir / dir_name
                skill_dir.mkdir(parents=True, exist_ok=True)
                self._render_skill_content(skill, skill_dir, result, dir_name=dir_name)

            # Generate AGENTS.md for project-level VibeSOP routing rules
            agents_content = self._generate_agents_md(manifest)
            agents_path = output_dir / "AGENTS.md"
            self.write_file_atomic(
                agents_path,
                agents_content,
                validate_security=False,
            )
            result.add_file(agents_path)

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
            "# ==============================================",
            "# IMPORTANT: Authentication Required",
            "# ==============================================",
            "#",
            "# This configuration requires API authentication.",
            "# Choose ONE of the following methods:",
            "#",
            "# Method 1: Use /login command (Recommended)",
            "#   1. Run: kimi",
            "#   2. Type: /login",
            "#   3. Follow browser authentication",
            "#",
            "# Method 2: Set environment variable",
            '#   export KIMI_API_KEY="sk-your-api-key"',
            "#",
            "# Method 3: Add api_key manually (Not recommended)",
            "#   [providers.kimi-for-coding]",
            '#   api_key = "sk-your-api-key"',
            "#",
            "# ==============================================",
            "",
            "",
        ]

        # Add metadata if present
        if manifest.metadata.author:
            lines.extend(
                [
                    f"# Author: {manifest.metadata.author}",
                    "",
                ]
            )
        if manifest.metadata.description:
            lines.extend(
                [
                    f"# Description: {manifest.metadata.description}",
                    "",
                ]
            )

        # Add security settings
        security = manifest.get_effective_security_policy()
        lines.extend(
            [
                "[vibesop.security]",
                f"scan_external_content = {str(security.scan_external_content).lower()}",
                f"max_file_size_mb = {security.max_file_size / (1024 * 1024):.1f}",
                "",
            ]
        )

        # Add routing settings
        routing = manifest.get_effective_routing_policy()
        lines.extend(
            [
                "[vibesop.routing]",
                f"enable_ai_routing = {str(routing.enable_ai_routing).lower()}",
                f"confidence_threshold = {routing.confidence_threshold}",
                "",
            ]
        )

        # Add skills note
        if manifest.skills:
            lines.extend(
                [
                    "# VibeSOP Skills",
                    f"# {len(manifest.skills)} skills configured.",
                    "# Install them to ~/.kimi/skills/ (or .kimi/skills/ for project-level)",
                    "# and set merge_all_available_skills = true to load from multiple sources.",
                    "",
                ]
            )

        # Add hook configuration for automatic VibeSOP routing
        lines.extend(
            [
                "# ==============================================",
                "# VibeSOP Auto-Routing Hook",
                "# ==============================================",
                "#",
                "# This hook automatically calls 'vibe route' before each user prompt",
                "# to enable context-aware skill routing. Requires the hook script",
                "# to be installed at ~/.kimi/hooks/vibesop-route.sh",
                "#",
                "# NOTE: Kimi CLI event names vary by version. Valid values:",
                "#   - 'UserPromptSubmit' : before sending user message to AI",
                "#   - 'PreToolUse'       : before tool execution",
                "# Adjust the event below to match your Kimi CLI version.",
                "",
                "[[hooks]]",
                'name = "vibesop-route"',
                'event = "UserPromptSubmit"',
                'command = "bash ~/.kimi/hooks/vibesop-route.sh"',
                "",
            ]
        )

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
        text = text.replace("\n", " ")
        text = text.replace("\r", " ")

        # Collapse multiple spaces into one
        import re

        text = re.sub(r"\s+", " ", text)

        # Escape backslashes and quotes
        text = text.replace("\\", "\\\\")
        text = text.replace('"', '\\"')

        return text.strip()

    def _merge_config_with_existing(self, config_path: Path, new_config: str) -> str:
        """Merge new VibeSOP config fragment into existing config.toml.

        Preserves all existing sections (providers, auth, etc.) while
        adding or refreshing the [[hooks]] section from the new config.
        This prevents auth tokens from being lost on re-deploy.

        Args:
            config_path: Path to existing config.toml
            new_config: Fresh VibeSOP config content

        Returns:
            Merged config.toml content
        """
        existing = config_path.read_text()
        lines = existing.split("\n")

        # Remove existing [[hooks]] sections (line-based to preserve formatting)
        result_lines = []
        in_hooks_section = False
        for line in lines:
            if line.startswith("[[hooks]]"):
                in_hooks_section = True
                continue
            if in_hooks_section:
                if line.startswith("["):
                    in_hooks_section = False
                    result_lines.append(line)
                continue
            result_lines.append(line)

        # Trim trailing blank lines
        while result_lines and result_lines[-1].strip() == "":
            result_lines.pop()

        # Append fresh [[hooks]] section from new config
        hooks_match = re.search(r"(\[\[hooks\]\].*)", new_config, flags=re.DOTALL)
        if hooks_match:
            hooks_section = hooks_match.group(1).rstrip()
            result_lines.extend(["", "", hooks_section, ""])

        return "\n".join(result_lines)

    def _render_skill_content(
        self,
        skill: Any,
        skill_dir: Path,
        result: RenderResult,
        dir_name: str | None = None,
    ) -> None:
        """Render skill content from actual skill file.

        Args:
            skill: Skill definition from manifest
            skill_dir: Directory to write skill files
            result: RenderResult to track files
            dir_name: Flattened directory name used for the skill
        """
        skill_id = skill.id if hasattr(skill, "id") else skill.get("id", "")
        skill_output_path = skill_dir / "SKILL.md"

        # Try to find actual skill content from core/skills/
        skill_content = self._find_skill_content(skill_id)

        if skill_content:
            # Kimi CLI only supports "standard" and "flow" skill types.
            # VibeSOP uses "prompt" internally; normalize for Kimi compatibility.
            skill_content = self._normalize_skill_type(skill_content)
            self.write_file_atomic(skill_output_path, skill_content, validate_security=False)
            result.add_file(skill_output_path)
        else:
            # Fallback: generate minimal skill definition
            fallback_content = self._generate_fallback_skill_content(skill, dir_name=dir_name)
            self.write_file_atomic(skill_output_path, fallback_content, validate_security=False)
            result.add_file(skill_output_path)

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
            "### Multi-Intent Handling (多意图处理)",
            "",
            "If `vibe route` detects multiple intents, it will return an execution plan.",
            "You MUST:",
            "- Follow the plan steps in order",
            "- Read each step's SKILL.md before executing",
            "- Report completion after each step",
            "- Parallel steps can be executed simultaneously",
            "",
            "Example:",
            "```bash",
            '# User: "分析架构并优化性能"',
            "# vibe route returns execution plan:",
            "#   Step 1: superpowers-architect — Analyze architecture",
            "#   Step 2: superpowers-optimize — Optimize performance",
            "#",
            "# Execution:",
            "# 1. Read superpowers-architect/SKILL.md",
            "# 2. Follow architect workflow",
            '# 3. Report: "步骤 1 完成"',
            "# 4. Read superpowers-optimize/SKILL.md",
            "# 5. Follow optimize workflow",
            '# 6. Report: "步骤 2 完成"',
            "```",
            "",
            "### Fallback Mode (降级处理)",
            "",
            "If no skill matches your request:",
            "- The system will show the closest candidates",
            "- You may continue with raw LLM mode",
            "- NEVER guess skill rules — always read SKILL.md",
            "",
            "### Quick Commands (快捷命令)",
            "",
            "When a user types a `/vibe-*` command, execute it directly with `vibe route --slash`:",
            "```bash",
            'vibe route --slash "/vibe-help"',
            'vibe route --slash "/vibe-list"',
            'vibe route --slash "/vibe-analyze --deep"',
            'vibe route --slash "/vibe-install gstack"',
            "```",
            "",
            "Available quick commands:",
            "- `/vibe-help` — Show all available commands",
            "- `/vibe-list` — List installed skills and available packs",
            "- `/vibe-route <query>` — Force trigger routing with transparency",
            "- `/vibe-install <pack>` — Install a skill pack",
            "- `/vibe-analyze [--deep]` — Analyze project architecture",
            "- `/vibe-evaluate [--skill <id>]` — Evaluate skill quality",
            "- `/vibe-orchestrate <query>` — Multi-skill orchestration",
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
            "**10-Layer Routing System:**",
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
            "AGENTS.md (if present in project root) is loaded as project context.",
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
                f"- AI Routing: {manifest.get_effective_routing_policy().enable_ai_routing}",
                f"- Confidence Threshold: {manifest.get_effective_routing_policy().confidence_threshold}",
                "",
                "---",
                "*Generated by VibeSOP*",
            ]
        )

        return "\n".join(lines)

    def _generate_agents_md(self, manifest: Manifest) -> str:
        """Generate AGENTS.md for Kimi Code CLI.

        AGENTS.md is loaded by Kimi CLI as project-level system prompt context.
        It contains VibeSOP routing rules that guide the AI to automatically
        trigger skill routing for non-trivial tasks.

        Args:
            manifest: Configuration manifest

        Returns:
            AGENTS.md content
        """
        lines = [
            "# VibeSOP Agent 指令",
            "",
            "> **Generated by VibeSOP** — AI-powered skill routing for Kimi Code CLI",
            "",
            "## 核心规则",
            "",
            "收到任何**非平凡**的用户请求时，你必须：",
            "",
            '1. **先路由**：运行 `vibe route "<用户请求>"` 获取技能推荐',
            "2. **再加载**：读取推荐 skill 的 SKILL.md",
            "3. **后执行**：严格按照 skill 指导执行",
            "",
            "### 判断标准",
            "",
            "以下情况**必须**执行路由：",
            "- 用户请求涉及代码审查、调试、优化、架构设计",
            '- 用户请求包含多个子任务（如"分析并优化"）',
            "- 用户请求长度超过 20 个字符",
            '- 用户使用了明确的技能指示词（如"review","debug","plan"）',
            "",
            "以下情况**可以跳过**路由：",
            '- 简单的问候或确认（"你好"、"ok"）',
            "- 关于 VibeSOP 系统本身的元问题",
            "- 长度少于 10 个字符的查询",
            "",
            "## 多意图处理",
            "",
            "如果 `vibe route` 返回多意图执行计划（包含多个步骤），你必须：",
            "- 按步骤顺序执行",
            "- 每步读取对应的 SKILL.md",
            "- 每步完成后明确报告进度",
            "- 独立步骤可以并行处理",
            "",
            "示例：",
            "```bash",
            '# 用户请求："分析架构并优化性能"',
            "# vibe route 返回：",
            "#   步骤 1: superpowers-architect — 分析架构",
            "#   步骤 2: superpowers-optimize — 优化性能",
            "#",
            "# 执行流程：",
            "# 1. 读取 superpowers-architect/SKILL.md",
            "# 2. 按 skill 指导分析架构",
            "# 3. 声明「步骤 1 完成」",
            "# 4. 读取 superpowers-optimize/SKILL.md",
            "# 5. 按 skill 指导优化性能",
            "# 6. 声明「步骤 2 完成」",
            "```",
            "",
            "## 决策透明化",
            "",
            "每次路由后，向用户展示：",
            "- 匹配的技能名称和置信度",
            "- 其他候选技能（如果有）",
            "- 执行计划（如果是多意图）",
            "",
            "如果用户质疑路由结果，使用 `vibe route --explain` 展示详细决策过程。",
            "",
            "## 降级规则",
            "",
            "如果 `vibe route` 未找到匹配技能（Fallback 模式）：",
            "- 告知用户未找到匹配技能",
            "- 展示最接近的候选（即使 confidence < threshold）",
            "- 询问用户是否继续以普通模式处理",
            "- **不要**猜测或编造 skill 规则",
            "",
            "## 快捷命令（Quick Commands）",
            "",
            "当用户输入 `/vibe-*` 命令时，直接使用 `vibe route --slash` 执行：",
            "```bash",
            'vibe route --slash "/vibe-help"',
            'vibe route --slash "/vibe-list"',
            'vibe route --slash "/vibe-analyze --deep"',
            'vibe route --slash "/vibe-install gstack"',
            "```",
            "",
            "可用快捷命令：",
            "- `/vibe-help` — 显示所有可用命令",
            "- `/vibe-list` — 列出已安装技能和可用包",
            "- `/vibe-route <query>` — 强制触发路由并展示决策过程",
            "- `/vibe-install <pack>` — 安装技能包",
            "- `/vibe-analyze [--deep]` — 分析项目架构",
            "- `/vibe-evaluate [--skill <id>]` — 评估技能质量",
            "- `/vibe-orchestrate <query>` — 多技能编排",
            "",
            "## 上下文感知（Conversation Context）",
            "",
            "为了启用多轮对话上下文感知，你必须在同一个会话中保持稳定的 conversation ID：",
            "",
            "```bash",
            "# 开始会话时生成一个稳定的 conversation ID（跨平台）",
            'CONVERSATION_ID="kimi-$(python3 -c "import os, hashlib; print(hashlib.sha256(os.getcwd().encode()).hexdigest()[:16])")"',
            "",
            "# 每次调用 vibe route 时都传递这个 ID",
            'vibe route --conversation "$CONVERSATION_ID" "<用户请求>"',
            "```",
            "",
            "上下文感知会带来的效果：",
            "- **Session Stickiness**：如果用户连续问相关问题，系统会优先保持当前 skill",
            "- **Habit Learning**：同一查询模式多次使用后，系统会记住用户的偏好",
            "- **Follow-up Detection**：用户说「继续」、「还是报错」等，系统会自动关联上一次的查询",
            "",
            "⚠️ **重要**：如果你不传递 `--conversation`，每次调用都是独立的，上下文感知将失效。",
            "",
            "## 可用技能",
            "",
        ]

        if manifest.skills:
            for skill in manifest.skills:
                lines.extend(
                    [
                        f"### {skill.id}",
                        f"- **名称**: {skill.name}",
                        f"- **描述**: {skill.description}",
                        f"- **触发**: {skill.trigger_when}",
                        "",
                    ]
                )
        else:
            lines.extend(
                [
                    "当前未配置技能。",
                    "",
                    "安装技能：",
                    "```bash",
                    "vibe install <skill-pack-url>",
                    "```",
                    "",
                ]
            )

        lines.extend(
            [
                "---",
                "",
                f"*Generated by VibeSOP v{manifest.metadata.version}*",
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

    def _render_route_hook(
        self,
        output_dir: Path,
        result: RenderResult,
    ) -> None:
        """Render the vibesop-route.sh hook script using the shared template.

        Delegates to ``render_route_hook()`` in ``_shared.py`` so that
        all platform adapters share the same hook script structure.

        Args:
            output_dir: Output directory (hooks/ will be created here)
            result: RenderResult to track files
        """
        try:
            from vibesop.adapters._shared import render_route_hook as _shared_route_hook

            hook_content = _shared_route_hook(
                platform="kimi-cli",
                platform_name="Kimi CLI",
                purpose="Auto-routing via [[hooks]] in config.toml",
                enable_explicit_overrides=False,
                enable_orchestration=False,
                include_additional_context=True,
                no_match_message=True,
            )
            hook_path = output_dir / "hooks" / "vibesop-route.sh"
            hook_path.parent.mkdir(parents=True, exist_ok=True)
            self.write_file_atomic(hook_path, hook_content, validate_security=False)
            hook_path.chmod(0o755)
            result.add_file(hook_path)
        except Exception as e:
            result.add_warning(f"Failed to write vibesop-route.sh for Kimi CLI: {e}")
