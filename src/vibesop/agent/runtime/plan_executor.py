"""Plan executor — guides AI agents through multi-step execution plans.

Since most AI agent platforms cannot be "forced" to follow a plan,
this module generates detailed prompts that strongly guide the agent
through each step. Platform hooks (where available) can add enforcement.

Execution strategies:
- Universal: Inject step-by-step instructions into context
- Claude Code: PostToolUse hook tracks step completion
- OpenCode: Plugin monitors tool usage for progress tracking
- Kimi CLI: Pure prompt-based guidance (no enforcement possible)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from vibesop.core.models import ExecutionMode

if TYPE_CHECKING:
    from vibesop.core.models import ExecutionPlan


@dataclass
class ExecutionGuide:
    """A guide for executing an execution plan.

    Attributes:
        prompt: The full instruction prompt for the agent
        step_markers: Text markers the agent should emit after each step
        completion_check: How to verify plan completion
    """

    prompt: str
    step_markers: list[str]
    completion_check: str


class PlanExecutor:
    """Generates execution guides for multi-step plans.

    AI agents cannot be directly "controlled" — they can only be guided
    through detailed instructions. This module creates prompts that:
    1. Clearly enumerate steps in order
    2. Define completion markers for each step
    3. Specify data dependencies between steps
    4. Provide fallback instructions for step failures

    Example:
        >>> executor = PlanExecutor()
        >>> guide = executor.build_guide(plan)
        >>> print(guide.prompt[:100])
        # 执行计划: Analyze and optimize...
    """

    def build_guide(self, plan: ExecutionPlan) -> ExecutionGuide:
        """Build an execution guide for the given plan.

        Args:
            plan: The execution plan to guide through

        Returns:
            ExecutionGuide with prompt and markers
        """
        prompt = self._build_prompt(plan)
        markers = self._extract_step_markers(plan)
        completion = self._build_completion_check(plan)

        return ExecutionGuide(
            prompt=prompt,
            step_markers=markers,
            completion_check=completion,
        )

    def build_step_transition_prompt(
        self,
        plan: ExecutionPlan,
        completed_step_number: int,
    ) -> str:
        """Build a prompt for transitioning to the next step.

        Called after a step is completed to guide the agent forward.

        Args:
            plan: The execution plan
            completed_step_number: Which step was just completed

        Returns:
            Transition prompt text
        """
        next_steps = [
            s for s in plan.steps
            if s.step_number > completed_step_number
            and s.status.value == "pending"
        ]

        if not next_steps:
            return "✅ 所有步骤已完成。请汇总结果并报告。"

        next_step = min(next_steps, key=lambda s: s.step_number)

        lines = [
            f"✅ 步骤 {completed_step_number} 已完成。",
            "",
            f"下一步: 步骤 {next_step.step_number}",
            f"- Skill: {next_step.skill_id}",
            f"- 任务: {next_step.intent}",
            f"- 输入: {next_step.input_query}",
        ]

        if next_step.dependencies:
            deps = ", ".join(next_step.dependencies)
            lines.append(f"- 依赖: {deps}")

        lines.extend([
            "",
            f"请先读取 {next_step.skill_id} 的 SKILL.md，然后执行。",
        ])

        return "\n".join(lines)

    def build_progress_summary(self, plan: ExecutionPlan) -> str:
        """Build a progress summary of the plan.

        Useful for showing current status to users.

        Args:
            plan: The execution plan

        Returns:
            Progress summary text
        """
        total = len(plan.steps)
        completed = sum(1 for s in plan.steps if s.status.value == "completed")
        in_progress = sum(1 for s in plan.steps if s.status.value == "in_progress")

        lines = [
            f"📊 执行进度: {completed}/{total} 完成",
        ]

        if in_progress:
            lines.append(f"   {in_progress} 进行中")

        lines.append("")

        for step in plan.steps:
            icon = {
                "pending": "⏳",
                "in_progress": "🔄",
                "completed": "✅",
                "skipped": "⏭️",
            }.get(step.status.value, "❓")

            lines.append(f"  {icon} 步骤 {step.step_number}: {step.skill_id} — {step.intent}")

        return "\n".join(lines)

    def _build_prompt(self, plan: ExecutionPlan) -> str:
        """Build the main execution prompt."""
        lines = [
            f"# 🎯 执行计划: {plan.original_query}",
            "",
            "⚠️ 重要: 你必须严格按照以下步骤执行。每完成一步，明确报告后再继续。",
            "",
            f"总步骤数: {len(plan.steps)}",
            f"执行模式: {plan.execution_mode.value.upper()}",
            "",
        ]

        # Group by parallel batches
        # For PARALLEL mode without dependencies, treat all steps as one parallel group
        if plan.execution_mode == ExecutionMode.PARALLEL and not any(s.dependencies for s in plan.steps):
            groups = [plan.steps]
        else:
            groups = plan.get_parallel_groups()

        for group_num, group in enumerate(groups, 1):
            if len(group) == 1:
                step = group[0]
                lines.extend(self._format_single_step(step))
            else:
                lines.extend(self._format_parallel_group(group_num, group))

        # Execution rules
        lines.extend([
            "",
            "---",
            "## 执行规则",
            "",
            "1. **每步必须读取 SKILL.md**: 在执行任何步骤前，先读取对应 skill 的 SKILL.md 文件",
            "2. **严格按顺序**: 不要跳过步骤，不要改变顺序",
            "3. **明确报告**: 每步完成后，必须声明『步骤 N 完成』",
            "4. **处理依赖**: 如果某步依赖前一步输出，确保前一步已完成",
            "5. **失败处理**: 如果某步失败，报告错误并询问是否继续剩余步骤",
            "6. **最终汇总**: 所有步骤完成后，汇总结果并给出整体结论",
            "",
            "## 步骤完成标记",
            "",
            "完成每一步后，请使用以下格式报告:",
            "",
        ])

        for step in plan.steps:
            lines.append(f"- 步骤 {step.step_number}: 『步骤 {step.step_number} 完成』")

        lines.extend([
            "",
            "## 数据传递",
            "",
            "步骤间通过输出变量传递数据:",
        ])

        for step in plan.steps:
            if step.output_as:
                lines.append(f"- 步骤 {step.step_number} 输出: `{step.output_as}`")

        return "\n".join(lines)

    def _format_single_step(self, step) -> list[str]:
        """Format a single sequential step."""
        lines = [
            f"## 步骤 {step.step_number}: {step.intent}",
            f"- **Skill**: {step.skill_id}",
            f"- **任务**: {step.input_query}",
        ]

        if step.output_as:
            lines.append(f"- **输出变量**: {step.output_as}")

        if step.dependencies:
            deps = ", ".join(step.dependencies)
            lines.append(f"- **依赖**: 必须等 {deps} 完成后才能开始")

        lines.extend([
            "",
            f"完成此步骤后声明: 『步骤 {step.step_number} 完成』",
            "",
        ])

        return lines

    def _format_parallel_group(self, group_num: int, group: list) -> list[str]:
        """Format a parallel step group."""
        lines = [
            f"## 并行组 {group_num}",
            "",
            "以下步骤可以**并行执行**（相互独立，无依赖）:",
            "",
        ]

        for step in group:
            lines.extend([
                f"### 步骤 {step.step_number}: {step.intent}",
                f"- **Skill**: {step.skill_id}",
                f"- **任务**: {step.input_query}",
            ])
            if step.output_as:
                lines.append(f"- **输出变量**: {step.output_as}")
            lines.append("")

        lines.extend([
            f"并行组 {group_num} 的所有步骤完成后，声明: "
            f"『并行组 {group_num} 全部完成』",
            "",
        ])

        return lines

    def _extract_step_markers(self, plan: ExecutionPlan) -> list[str]:
        """Extract the completion markers for each step."""
        markers = []
        # Use same grouping logic as _build_prompt
        if plan.execution_mode == ExecutionMode.PARALLEL and not any(s.dependencies for s in plan.steps):
            groups = [plan.steps]
        else:
            groups = plan.get_parallel_groups()

        for group_num, group in enumerate(groups, 1):
            if len(group) == 1:
                step = group[0]
                markers.append(f"步骤 {step.step_number} 完成")
            else:
                markers.append(f"并行组 {group_num} 全部完成")

        return markers

    def _build_completion_check(self, plan: ExecutionPlan) -> str:
        """Build the completion verification criteria."""
        total = len(plan.steps)
        return (
            f"所有 {total} 个步骤均标记为完成。"
            f"请检查是否收到所有步骤的『完成』声明。"
        )


__all__ = [
    "ExecutionGuide",
    "PlanExecutor",
]
