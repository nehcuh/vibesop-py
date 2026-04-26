"""Plan executor — guides AI agents through multi-step execution plans.

Since most AI agent platforms cannot be "forced" to follow a plan,
this module generates detailed prompts and execution manifests
that strongly guide the agent through each step.

Execution strategies:
- Universal: Inject step-by-step instructions into context
- Claude Code: PostToolUse hook tracks step completion
- OpenCode: Plugin monitors tool usage for progress tracking
- Kimi CLI: Pure prompt-based guidance (no enforcement possible)

The ExecutionManifest (new in v5.2) embeds full SKILL.md content
and upstream step outputs so the agent never needs to load files manually.
The standardized completion marker `[StepCompleted:N]` allows downstream
tooling to detect step completion.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from vibesop.core.models import (
    ExecutionManifest,
    ExecutionMode,
    StepManifest,
)

if TYPE_CHECKING:
    from vibesop.core.models import ExecutionPlan


COMPLETION_MARKER_PREFIX = "[StepCompleted:"

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
    """Generates execution guides and manifests for multi-step plans.

    Two output modes:
    - build_guide() — text-only prompt (backward compatible, v4.4+)
    - build_manifest() — rich ExecutionManifest with embedded SKILL.md
      content and upstream context (v5.2+, recommended for orchestration)

    Example:
        >>> executor = PlanExecutor(project_root=Path.cwd())
        >>> manifest = executor.build_manifest(plan)
        >>> # Write the execution sequence file for the agent
        >>> manifest_path = Path(manifest.context_file)
        >>> manifest_path.parent.mkdir(parents=True, exist_ok=True)
        >>> manifest_path.write_text(manifest.to_markdown())
    """

    def __init__(self, project_root: str | Path = "."):
        self._project_root = Path(project_root).resolve()

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

    def build_manifest(self, plan: ExecutionPlan) -> ExecutionManifest:
        """Build a full ExecutionManifest with embedded skill content.

        Unlike build_guide() which produces text-only prompts, this method
        reads each step's SKILL.md content and embeds it directly into the
        manifest. The AI agent can follow the manifest step-by-step without
        manually loading skill files or hunting for context.

        Args:
            plan: The execution plan to manifest

        Returns:
            ExecutionManifest with embedded skill content and context
        """
        from vibesop.core.skills import SkillLoader

        loader = SkillLoader(project_root=self._project_root)
        steps: list[StepManifest] = []

        for step in plan.steps:
            skill_content = loader.read_skill_content(step.skill_id)
            skill = loader.get_skill(step.skill_id)
            skill_name = skill.metadata.name if skill else step.skill_id
            skill_path = str(skill.source_file) if skill and skill.source_file else ""

            input_context = self._resolve_input_context(plan, step)

            manifest_step = StepManifest(
                step_number=step.step_number,
                skill_id=step.skill_id,
                skill_name=skill_name,
                skill_path=skill_path,
                skill_content=skill_content,
                input_context=input_context,
                output_slot=step.output_as,
                completion_marker=StepManifest.completion_marker_for(step.step_number),
                instruction=(
                    f"使用 {step.skill_id} 技能执行: {step.intent}\n"
                    f"具体查询: {step.input_query}"
                ),
            )
            steps.append(manifest_step)

        plan_dir = self._project_root / ".vibe" / "plans" / plan.plan_id
        context_file = str(plan_dir / "context.md")

        return ExecutionManifest(
            plan_id=plan.plan_id,
            original_query=plan.original_query,
            strategy=plan.execution_mode.value,
            steps=steps,
            context_file=context_file,
        )

    def _resolve_input_context(
        self, plan: ExecutionPlan, current_step
    ) -> str:
        """Resolve the input context for a step from its upstream dependencies."""
        if not current_step.dependencies:
            return ""

        upstream_outputs: list[str] = []
        for dep_id in current_step.dependencies:
            for upstream in plan.steps:
                if upstream.step_id == dep_id and upstream.output_as:
                    upstream_outputs.append(
                        f"- {upstream.output_as}: 来自步骤 {upstream.step_number} "
                        f"({upstream.skill_id}) 的输出"
                    )
                    if upstream.result_summary:
                        upstream_outputs.append(f"  摘要: {upstream.result_summary}")

        if upstream_outputs:
            return "本步骤依赖以下前置步骤的输出:\n" + "\n".join(upstream_outputs)

        return ""

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
            return "\u2705 所有步骤已完成。请汇总结果并报告。"

        next_step = min(next_steps, key=lambda s: s.step_number)

        marker = StepManifest.completion_marker_for(completed_step_number)
        lines = [
            f"\u2705 步骤 {completed_step_number} 已完成 (marker: {marker})。",
            "",
            f"下一步: 步骤 {next_step.step_number}",
            f"- Skill: {next_step.skill_id}",
            f"- 任务: {next_step.intent}",
            f"- 输入: {next_step.input_query}",
        ]

        if next_step.dependencies:
            deps = ", ".join(next_step.dependencies)
            lines.append(f"- 依赖: {deps}")

        next_marker = StepManifest.completion_marker_for(next_step.step_number)
        lines.append(f"- 完成标记: `<!-- {next_marker} -->`")

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
            f"\U0001f4ca 执行进度: {completed}/{total} 完成",
        ]

        if in_progress:
            lines.append(f"   {in_progress} 进行中")

        lines.append("")

        for step in plan.steps:
            icon = {
                "pending": "\u23f3",
                "in_progress": "\U0001f504",
                "completed": "\u2705",
                "skipped": "\u23ed\ufe0f",
            }.get(step.status.value, "\u2753")

            lines.append(f"  {icon} 步骤 {step.step_number}: {step.skill_id} \u2014 {step.intent}")

        return "\n".join(lines)

    def _build_prompt(self, plan: ExecutionPlan) -> str:
        """Build the main execution prompt."""
        lines = [
            f"# \U0001f3af 执行计划: {plan.original_query}",
            "",
            "\u26a0\ufe0f 重要: 你必须严格按照以下步骤执行。每完成一步，明确报告后再继续。",
            "",
            f"总步骤数: {len(plan.steps)}",
            f"执行模式: {plan.execution_mode.value.upper()}",
            "",
        ]

        # Group by parallel batches
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
            "3. **明确报告**: 每步完成后，必须声明" + f"`<!-- {COMPLETION_MARKER_PREFIX}N] -->`" + " 标记",
            "4. **处理依赖**: 如果某步依赖前一步输出，确保前一步已完成",
            "5. **失败处理**: 如果某步失败，报告错误并询问是否继续剩余步骤",
            "6. **最终汇总**: 所有步骤完成后，汇总结果并给出整体结论",
            "",
        ])

        return "\n".join(lines)

    def _format_single_step(self, step) -> list[str]:
        """Format a single sequential step."""
        marker = StepManifest.completion_marker_for(step.step_number)
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
            f"完成此步骤后声明: `<!-- {marker} -->` 并附上结果摘要",
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
            marker = StepManifest.completion_marker_for(step.step_number)
            lines.extend([
                f"### 步骤 {step.step_number}: {step.intent}",
                f"- **Skill**: {step.skill_id}",
                f"- **任务**: {step.input_query}",
            ])
            if step.output_as:
                lines.append(f"- **输出变量**: {step.output_as}")
            lines.append(f"- 完成后声明: `<!-- {marker} -->`")
            lines.append("")

        lines.extend([
            f"并行组 {group_num} 的所有步骤完成后，声明: "
            f"\u2018并行组 {group_num} 全部完成\u2019",
            "",
        ])

        return lines

    def _extract_step_markers(self, plan: ExecutionPlan) -> list[str]:
        """Extract the completion markers for each step."""
        markers = []
        if plan.execution_mode == ExecutionMode.PARALLEL and not any(s.dependencies for s in plan.steps):
            groups = [plan.steps]
        else:
            groups = plan.get_parallel_groups()

        for group_num, group in enumerate(groups, 1):
            if len(group) == 1:
                step = group[0]
                markers.append(StepManifest.completion_marker_for(step.step_number))
            else:
                markers.append(f"并行组 {group_num} 全部完成")

        return markers

    def _build_completion_check(self, plan: ExecutionPlan) -> str:
        """Build the completion verification criteria."""
        total = len(plan.steps)
        markers = [StepManifest.completion_marker_for(i + 1) for i in range(total)]
        return (
            f"所有 {total} 个步骤均标记为完成。"
            f"请检查是否收到所有步骤的标记: {', '.join(markers)}"
        )


__all__ = [
    "COMPLETION_MARKER_PREFIX",
    "ExecutionGuide",
    "PlanExecutor",
]
