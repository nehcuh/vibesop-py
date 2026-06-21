"""Skill injector — loads matched skill content into agent context.

Platform-specific injection strategies:
- Claude Code: additionalContext via hook JSON output
- OpenCode: experimental.chat.system.transform
- Kimi CLI: Cannot inject → return ReadFile instruction
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vibesop.core.models import ExecutionPlan


class PlatformType(StrEnum):
    """Supported AI agent platforms."""

    CLAUDE_CODE = "claude-code"
    OPENCODE = "opencode"
    KIMI_CLI = "kimi-cli"
    PI = "pi"
    GENERIC = "generic"


class InjectionMethod(StrEnum):
    """How skill content is delivered to the agent."""

    # Direct system prompt modification (OpenCode)
    SYSTEM_PROMPT = "system_prompt"
    # Additional context appended to conversation (Claude Code)
    ADDITIONAL_CONTEXT = "additional_context"
    # Instruction for AI to read skill file (Kimi CLI fallback)
    INSTRUCTION = "instruction"
    # Direct text injection (generic)
    TEXT = "text"


@dataclass
class InjectionResult:
    """Result of skill content injection.

    Attributes:
        method: How the content was/will be injected
        payload: The actual content or injection payload
        skill_id: Which skill was injected
        truncated: Whether content was truncated for length
    """

    method: InjectionMethod
    payload: str | dict[str, Any]
    skill_id: str = ""
    truncated: bool = False


class SkillInjector:
    """Injects matched skill content into agent context.

    Each platform has different capabilities for context modification:
    - Claude Code: Can inject additionalContext via hook response
    - OpenCode: Can directly modify system prompt via transform hook
    - Kimi CLI: No injection capability → returns instructions for AI

    Example:
        >>> injector = SkillInjector(project_root=".")
        >>> result = injector.inject_single_skill("gstack/review", PlatformType.KIMI_CLI)
        >>> result.method
        <InjectionMethod.INSTRUCTION: 'instruction'>
    """

    # Max characters to inject (to avoid context overflow)
    MAX_INJECT_LENGTH: int = 3000

    def __init__(self, project_root: str | Path = ".") -> None:
        self.project_root = Path(project_root).resolve()

    def inject_single_skill(
        self,
        skill_id: str,
        platform: PlatformType,
    ) -> InjectionResult:
        """Inject a single skill's content.

        Args:
            skill_id: The matched skill identifier
            platform: Target platform

        Returns:
            InjectionResult with platform-specific payload
        """
        skill_content = self._load_skill_content(skill_id)
        truncated = False

        if skill_content and len(skill_content) > self.MAX_INJECT_LENGTH:
            skill_content = skill_content[: self.MAX_INJECT_LENGTH]
            truncated = True

        if platform == PlatformType.CLAUDE_CODE:
            return self._inject_claude_code(skill_id, skill_content, truncated)
        elif platform == PlatformType.OPENCODE:
            return self._inject_opencode(skill_id, skill_content, truncated)
        elif platform == PlatformType.KIMI_CLI:
            return self._inject_kimi_cli(skill_id, skill_content, truncated)
        elif platform == PlatformType.PI:
            return self._inject_pi(skill_id, skill_content, truncated)
        else:
            return self._inject_generic(skill_id, skill_content, truncated)

    def inject_execution_plan(
        self,
        plan: ExecutionPlan,
        platform: PlatformType,
    ) -> InjectionResult:
        """Inject an execution plan for multi-step orchestration.

        Args:
            plan: The execution plan with steps
            platform: Target platform

        Returns:
            InjectionResult with platform-specific payload
        """
        plan_content = self._format_execution_plan(plan)

        if platform == PlatformType.CLAUDE_CODE:
            return InjectionResult(
                method=InjectionMethod.ADDITIONAL_CONTEXT,
                payload={"additionalContext": f"\n\n[VibeSOP Execution Plan]\n{plan_content}\n"},
                skill_id="multi-step-plan",
            )
        elif platform == PlatformType.OPENCODE:
            return InjectionResult(
                method=InjectionMethod.SYSTEM_PROMPT,
                payload=f"<vibesop-plan>\n{plan_content}\n</vibesop-plan>",
                skill_id="multi-step-plan",
            )
        elif platform == PlatformType.KIMI_CLI:
            return InjectionResult(
                method=InjectionMethod.INSTRUCTION,
                payload=plan_content,
                skill_id="multi-step-plan",
            )
        else:
            return InjectionResult(
                method=InjectionMethod.TEXT,
                payload=plan_content,
                skill_id="multi-step-plan",
            )

    def _load_skill_content(self, skill_id: str) -> str:
        """Load skill content from filesystem.

        v7.3.5 fix (Round 4 P1): previously only checked 3 paths and missed
        the actual install locations for Claude Code (``~/.claude/skills/``)
        and Pi (``~/.pi/agent/skills/``). Also, routing returns the bare
        ``name:`` field from SKILL.md frontmatter (e.g. ``"diagnose"``),
        but installed directory names carry pack prefixes
        (e.g. ``mattpocock-diagnose`` or ``mattpocock-skills-engineering-diagnose``).
        Without suffix matching, injector always fell back to placeholder text.

        Search order (each path is tried with 3 lookup strategies):
        1. ``core/skills/{skill_id}/SKILL.md`` — project-local builtin skills
        2. ``~/.claude/skills/{...}/SKILL.md`` — Claude Code target dir
        3. ``~/.pi/agent/skills/{...}/SKILL.md`` — Pi target dir
        4. ``~/.kimi-code/skills/{...}/SKILL.md`` — Kimi Code target dir
        5. ``~/.config/skills/{...}/SKILL.md`` — central storage (nested layout)

        For each path, three lookup strategies are tried in order:
        - Exact flat id: ``{skill_id.replace('/', '-')}`` (e.g. ``gstack-review``)
        - Pack-prefix glob: ``*-{flat_id}`` (e.g. ``mattpocock-diagnose``)
        - Nested glob: ``**/{flat_id}/SKILL.md`` (e.g. ``mattpocock/engineering/diagnose``)
        """
        flat_id = skill_id.replace("/", "-")
        home = Path.home()

        # Candidate base directories in priority order
        candidate_dirs: list[Path] = [
            self.project_root / "core" / "skills",
            home / ".claude" / "skills",
            home / ".pi" / "agent" / "skills",
            home / ".kimi-code" / "skills",
            home / ".config" / "skills",
        ]

        for base in candidate_dirs:
            if not base.exists():
                continue

            # Strategy 1: exact flat id (handles "gstack/review" → "gstack-review")
            direct = base / flat_id / "SKILL.md"
            if direct.exists():
                try:
                    return direct.read_text(encoding="utf-8")
                except OSError:
                    pass

            # Strategy 2: pack-prefix glob (handles skill_id="diagnose"
            # resolving to "mattpocock-diagnose")
            if base != self.project_root / "core" / "skills":
                # Only glob user-install dirs (core/skills has no pack prefix)
                try:
                    for candidate in base.glob(f"*-{flat_id}"):
                        skill_file = candidate / "SKILL.md"
                        if skill_file.exists():
                            try:
                                return skill_file.read_text(encoding="utf-8")
                            except OSError:
                                continue
                except (OSError, PermissionError):
                    pass

        # Strategy 3: nested layout in central storage (~/.config/skills/)
        # handles "mattpocock/skills/engineering/diagnose/SKILL.md"
        central = home / ".config" / "skills"
        if central.exists():
            try:
                for match in central.glob(f"**/{flat_id}/SKILL.md"):
                    try:
                        return match.read_text(encoding="utf-8")
                    except OSError:
                        continue
            except (OSError, PermissionError):
                pass

        return f"# Skill: {skill_id}\n\n*Skill content not found at expected locations.*"

    def _inject_claude_code(
        self,
        skill_id: str,
        content: str,
        truncated: bool,
    ) -> InjectionResult:
        """Build Claude Code additionalContext payload."""
        context_text = f"""

[ACTIVE SKILL: {skill_id}]
You MUST follow this skill's workflow. Do not skip steps.

{content}
{"\n[Content truncated]" if truncated else ""}
"""
        return InjectionResult(
            method=InjectionMethod.ADDITIONAL_CONTEXT,
            payload={"additionalContext": context_text},
            skill_id=skill_id,
            truncated=truncated,
        )

    def _inject_opencode(
        self,
        skill_id: str,
        content: str,
        truncated: bool,
    ) -> InjectionResult:
        """Build OpenCode system prompt fragment."""
        fragment = f"""<vibesop-skill id="{skill_id}">
You MUST follow this skill's workflow. Do not skip steps.

{content}
{"\n[Content truncated]" if truncated else ""}
</vibesop-skill>"""
        return InjectionResult(
            method=InjectionMethod.SYSTEM_PROMPT,
            payload=fragment,
            skill_id=skill_id,
            truncated=truncated,
        )

    def _inject_kimi_cli(
        self,
        skill_id: str,
        _content: str,
        _truncated: bool,
    ) -> InjectionResult:
        """Build Kimi CLI instruction (AI must read skill file itself)."""
        flat_id = skill_id.replace("/", "-")
        instruction = (
            f"请先读取 ~/.kimi-code/skills/{flat_id}/SKILL.md "
            f"（或 .kimi-code/skills/{flat_id}/SKILL.md），"
            f"然后严格按照该 skill 的工作流程执行「{skill_id}」。"
            f"不得跳过任何步骤。"
        )
        return InjectionResult(
            method=InjectionMethod.INSTRUCTION,
            payload=instruction,
            skill_id=skill_id,
        )

    def _inject_pi(
        self,
        skill_id: str,
        skill_content: str,
        truncated: bool = False,
    ) -> InjectionResult:
        """Generate Pi Coding Agent injection payload.

        Pi uses AGENTS.md context + prompt templates. Inject skill content
        as a section the agent should read before proceeding.
        """
        truncation_note = (
            f"\n[Content truncated at {self.MAX_INJECT_LENGTH} chars — "
            "refer to skill file for full content]"
            if truncated
            else ""
        )
        payload = (
            f'<vibesop-skill platform="pi">\n'
            f"## Skill: {skill_id}\n"
            f"Read the SKILL.md for `{skill_id}` before proceeding.\n"
            f"```markdown\n{skill_content}{truncation_note}\n```\n"
            f"</vibesop-skill>"
        )
        return InjectionResult(
            method=InjectionMethod.TEXT,
            payload=payload,
            skill_id=skill_id,
            truncated=truncated,
        )

    def _inject_generic(
        self,
        skill_id: str,
        content: str,
        truncated: bool,
    ) -> InjectionResult:
        """Build generic text injection."""
        text = f"""

=== SKILL: {skill_id} ===
{content}
{"\n[Content truncated]" if truncated else ""}
=== END SKILL ===
"""
        return InjectionResult(
            method=InjectionMethod.TEXT,
            payload=text,
            skill_id=skill_id,
            truncated=truncated,
        )

    def _format_execution_plan(self, plan: ExecutionPlan) -> str:
        """Format an execution plan for agent consumption.

        Groups steps by parallel batches and marks dependencies.
        Includes reasoning transparency for debugging and user understanding.
        """
        lines = [
            f"# 执行计划: {plan.original_query}",
            "",
        ]

        # Transparency: show detected intents and reasoning
        if plan.detected_intents:
            lines.extend(
                [
                    "## 检测到的意图",
                    ", ".join(f"- {intent}" for intent in plan.detected_intents),
                    "",
                ]
            )

        if plan.reasoning:
            lines.extend(
                [
                    "## 分解理由",
                    plan.reasoning,
                    "",
                ]
            )

        lines.extend(
            [
                f"## 执行模式: {plan.execution_mode.value}",
                "",
                "你必须按以下步骤执行。每完成一步，报告结果后再继续下一步。",
                "",
            ]
        )

        # Get parallel groups for visualization
        groups = plan.get_parallel_groups()

        for group_num, group in enumerate(groups, 1):
            if len(group) == 1:
                step = group[0]
                lines.extend(
                    [
                        f"## 步骤 {step.step_number}: {step.intent}",
                        f"- 使用 skill: {step.skill_id}",
                        f"- 任务: {step.input_query}",
                        f"- 输出变量: {step.output_as}",
                        "",
                        f"完成此步骤后，请明确声明：『步骤 {step.step_number} 完成，"
                        f"输出已保存到 {step.output_as}』",
                        "",
                    ]
                )
            else:
                lines.append(f"## 并行步骤组 {group_num}")
                lines.append("以下步骤可以并行执行：")
                for step in group:
                    lines.extend(
                        [
                            "",
                            f"### 步骤 {step.step_number}: {step.intent}",
                            f"- 使用 skill: {step.skill_id}",
                            f"- 任务: {step.input_query}",
                        ]
                    )
                lines.extend(
                    [
                        "",
                        f"所有并行步骤完成后，请明确声明：『并行组 {group_num} 全部完成』",
                        "",
                    ]
                )

        lines.extend(
            [
                "",
                "---",
                "执行规则:",
                "1. 严格按照步骤顺序执行",
                "2. 每步必须读取对应的 SKILL.md",
                "3. 每步完成后明确报告",
                "4. 如果某步失败，报告错误并询问是否继续",
            ]
        )

        return "\n".join(lines)


__all__ = [
    "InjectionMethod",
    "InjectionResult",
    "PlatformType",
    "SkillInjector",
]
