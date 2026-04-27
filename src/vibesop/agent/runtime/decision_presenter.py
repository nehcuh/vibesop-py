"""Decision presenter — makes routing decisions transparent to users.

Shows:
- Why this skill was matched (confidence, layer, boosts)
- Alternative candidates the user could switch to
- Rejected near-misses (below threshold but close)
- Quality grades and habit learning status
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vibesop.core.models import OrchestrationResult, RoutingResult, SkillRoute


class PlatformType:
    """Re-use from skill_injector to avoid circular import."""

    CLAUDE_CODE = "claude-code"
    OPENCODE = "opencode"
    KIMI_CLI = "kimi-cli"
    GENERIC = "generic"


@dataclass
class PresentResult:
    """Result of presenting a routing decision.

    Attributes:
        message: Human-readable decision explanation
        actions: Available user actions (accept, switch, skip, etc.)
        structured: Machine-readable decision data
    """

    message: str
    actions: list[str] = field(default_factory=list)
    structured: dict[str, object] = field(default_factory=dict)


class DecisionPresenter:
    """Presents routing decisions with full transparency.

    The goal is to answer the user's implicit questions:
    - "Why this skill?"
    - "What else was considered?"
    - "Is there a better match?"
    - "How confident is the system?"

    Example:
        >>> presenter = DecisionPresenter()
        >>> result = presenter.present_single_result(routing_result, "claude-code")
        >>> print(result.message)
        🎯 VibeSOP 路由结果
        匹配技能: gstack/review (82%)
        ...
    """

    def present_single_result(
        self,
        result: RoutingResult,
        platform: str = PlatformType.GENERIC,
    ) -> PresentResult:
        """Present a single-skill routing result.

        Args:
            result: RoutingResult from UnifiedRouter
            platform: Target platform (affects formatting)

        Returns:
            PresentResult with message and available actions
        """
        if result.primary is None:
            return self._present_no_match(result, platform)

        primary = result.primary
        lines: list[str] = []

        # Header with match info
        lines.extend(self._format_header(primary, platform))

        # Routing path transparency
        lines.extend(self._format_routing_path(result))

        # Boost explanations
        lines.extend(self._format_boosts(primary))

        # Alternative candidates
        lines.extend(self._format_alternatives(result.alternatives))

        # Near-misses from layer details (rejected candidates)
        lines.extend(self._format_rejected_candidates(result))

        # Platform-specific actions
        actions = self._single_actions(platform)

        return PresentResult(
            message="\n".join(lines),
            actions=actions,
            structured={
                "primary": {
                    "skill_id": primary.skill_id,
                    "confidence": primary.confidence,
                    "layer": primary.layer.value,
                },
                "alternatives": [
                    {"skill_id": a.skill_id, "confidence": a.confidence}
                    for a in result.alternatives[:3]
                ],
                "routing_path": [layer.value for layer in result.routing_path],
            },
        )

    def present_orchestration_result(
        self,
        result: OrchestrationResult,
        platform: str = PlatformType.GENERIC,
    ) -> PresentResult:
        """Present a multi-intent orchestration result.

        Args:
            result: OrchestrationResult with execution plan
            platform: Target platform

        Returns:
            PresentResult with plan visualization and actions
        """
        if result.mode.value == "single" or result.execution_plan is None:
            # Fallback to single presentation
            from vibesop.core.models import RoutingResult

            if hasattr(result, "primary") and result.primary:
                fake_result = RoutingResult(
                    primary=result.primary,
                    alternatives=result.alternatives,
                    routing_path=result.routing_path,
                    query=result.original_query,
                )
                return self.present_single_result(fake_result, platform)
            return PresentResult(
                message="❓ 未检测到可执行的意图",
                actions=["retry", "skip"],
            )

        plan = result.execution_plan
        lines: list[str] = []

        # Multi-intent header
        lines.extend(
            [
                "🔀 VibeSOP 多意图检测",
                "",
                f"原请求: {plan.original_query}",
                f"检测到 {len(plan.steps)} 个子任务:",
                "",
            ]
        )

        # Show parallel groups
        groups = plan.get_parallel_groups()
        for group_num, group in enumerate(groups, 1):
            if len(group) == 1:
                step = group[0]
                lines.append(f"  {step.step_number}. {step.skill_id} — {step.intent}")
            else:
                lines.append(f"  并行组 {group_num}:")
                for step in group:
                    lines.append(f"    • 步骤 {step.step_number}: {step.skill_id} — {step.intent}")

        # Execution strategy
        lines.extend(
            [
                "",
                f"执行策略: {plan.execution_mode.value.upper()}",
            ]
        )

        if plan.reasoning:
            lines.extend(["", f"分解理由: {plan.reasoning}"])

        # Single fallback
        if result.single_fallback:
            lines.extend(
                [
                    "",
                    f"💡 单技能备选: {result.single_fallback.skill_id} "
                    f"({result.single_fallback.confidence:.0%})",
                ]
            )

        # Plan summary
        summary = plan.get_execution_summary()
        lines.extend(
            [
                "",
                f"计划概要: {summary['total_steps']} 步, "
                f"{summary['parallel_groups']} 个执行组, "
                f"最多并行 {summary['max_parallel']} 步",
            ]
        )

        actions = [
            "execute_plan",
            "use_single",
            "edit_plan",
            "skip_all",
        ]

        return PresentResult(
            message="\n".join(lines),
            actions=actions,
            structured={
                "plan_id": plan.plan_id,
                "steps": [
                    {
                        "step_number": s.step_number,
                        "skill_id": s.skill_id,
                        "intent": s.intent,
                    }
                    for s in plan.steps
                ],
                "execution_mode": plan.execution_mode.value,
                "single_fallback": (
                    result.single_fallback.skill_id if result.single_fallback else None
                ),
            },
        )

    def _format_header(self, primary: SkillRoute | Any, _platform: str) -> list[str]:
        """Format the match header."""
        if primary.layer.value == "fallback_llm":
            return [
                "🤖 VibeSOP Fallback 模式",
                "",
                "未找到 confident 匹配的技能。",
                "AI 将继续以普通模式处理您的请求。",
            ]

        header = [
            "🎯 VibeSOP 路由结果",
            "",
            f"匹配技能: {primary.skill_id}",
            f"置信度: {primary.confidence:.0%}",
            f"匹配层: {primary.layer.value}",
        ]

        if primary.description:
            header.append(f"描述: {primary.description}")

        return header

    def _format_routing_path(self, result: RoutingResult | Any) -> list[str]:
        """Show which layers were tried."""
        if not result.routing_path:
            return []

        path_str = " → ".join(layer.value for layer in result.routing_path)
        return ["", f"路由路径: {path_str}"]

    def _format_boosts(self, primary: SkillRoute | Any) -> list[str]:
        """Show confidence boost explanations."""
        lines: list[str] = []
        meta = primary.metadata or {}

        # Session stickiness
        if meta.get("session_boost"):
            lines.append("💡 会话粘性提升已应用（保持多轮连续性）")

        # Habit boost
        if meta.get("habit_boost"):
            lines.append("💡 习惯学习提升已应用（该查询模式已出现 3+ 次）")

        # Quality boost
        if meta.get("quality_boost"):
            grade = meta.get("grade", "?")
            adjustment = primary.score_breakdown.get("quality_adjustment", 0)
            sign = "+" if adjustment > 0 else ""
            lines.append(f"💡 质量评分提升已应用 (Grade {grade}, {sign}{adjustment:+.2f})")

        # Project context boost
        if meta.get("project_boost"):
            ptype = meta.get("project_type", "unknown")
            lines.append(f"💡 项目上下文提升已应用 (类型: {ptype})")

        # Instinct boost
        if meta.get("instinct_boost"):
            lines.append("💡 经验直觉提升已应用（基于历史学习）")

        return lines if lines else []

    def _format_alternatives(self, alternatives: list[SkillRoute | Any]) -> list[str]:
        """Show alternative candidates."""
        if not alternatives:
            return []

        lines = ["", "其他候选技能:"]
        for alt in alternatives[:3]:
            desc = f" — {alt.description}" if alt.description else ""
            lines.append(f"  • {alt.skill_id} ({alt.confidence:.0%}){desc}")

        return lines

    def _format_rejected_candidates(self, result: RoutingResult | Any) -> list[str]:
        """Show near-miss candidates that were rejected."""
        if not result.layer_details:
            return []

        near_misses: list[str] = []
        for detail in result.layer_details:
            for rejected in getattr(detail, "rejected_candidates", []):
                near_misses.append(
                    f"  • {rejected.skill_id} ({rejected.confidence:.0%}) — {rejected.reason}"
                )

        if not near_misses:
            return []

        return ["", "接近但未达阈值的候选:", *near_misses[:5]]

    def _present_no_match(self, result: RoutingResult | Any, _platform: str) -> PresentResult:
        """Present when no match is found."""
        lines = [
            "🤖 VibeSOP Fallback 模式",
            "",
            f"查询: {result.query}",
            "",
            "未找到匹配的技能。",
        ]

        # Show suggestions if available
        if result.layer_details:
            lines.append("尝试的匹配层:")
            for detail in result.layer_details:
                status = "✅" if detail.matched else "❌"
                lines.append(f"  {status} {detail.layer.value}: {detail.reason}")

        return PresentResult(
            message="\n".join(lines),
            actions=["continue", "browse_skills", "install_skill"],
        )

    def _single_actions(self, _platform: str) -> list[str]:
        """Available actions for single-skill result."""
        return ["accept", "switch_alternative", "skip_skill"]


__all__ = [
    "DecisionPresenter",
    "PresentResult",
]
