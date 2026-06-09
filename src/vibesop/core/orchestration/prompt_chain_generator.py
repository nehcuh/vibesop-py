"""PromptChainGenerator — converts ExecutionPlan into structured prompt files.

Generates a sequence of phase-based prompt files (Phase 0 → Phase 1 → … → Final)
that guide Claude Code through multi-agent, multi-stage workflows. Each prompt
file is a self-contained markdown document with prerequisites, step-by-step
instructions, verification checklists, and recursive routing hints.

Phase 7.0 (v7.0.0): Prompt Chain Generator
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from vibesop.core.models import WorkflowPattern

if TYPE_CHECKING:
    from vibesop.core.models import ExecutionPlan, ExecutionStep

logger = logging.getLogger(__name__)

_ROUTING_HINT = (
    "\n\n### 技能路由提示\n\n"
    "在执行本阶段的每个步骤时，如果遇到需要选择工具的决策点，\n"
    '请运行 `vibe route "<当前子任务描述>"` 来动态选择最合适的技能。\n'
)


# ── Data models ──────────────────────────────────────────────────────────────


class PromptFile(BaseModel):
    """A single generated prompt file in the chain."""

    phase: int = Field(..., description="Phase number (0, 1, 2, …, -1 for final)")
    name: str = Field(..., description="Short slug, e.g. 'fan-out-diagnosis'")
    filename: str = Field(..., description="Filename, e.g. 'phase-0-fan-out-diagnosis.md'")
    content: str = Field(..., description="Full markdown content")
    prerequisites: list[str] = Field(
        default_factory=list, description="Conditions that must be true before starting"
    )
    required_files: list[str] = Field(
        default_factory=list, description="Files the agent must read first"
    )
    verification_checklist: list[str] = Field(
        default_factory=list, description="Items to verify before proceeding"
    )


# ── Generator ────────────────────────────────────────────────────────────────


class PromptChainGenerator:
    """Generate Claude Code Prompt Chain from an ExecutionPlan.

    Only activates when the plan's ``workflow_pattern`` is
    ``PROMPT_CHAIN`` (i.e. ``complexity_level == "multi_agent"``).
    For all other plans ``generate()`` returns an empty list so that the
    existing execution paths remain untouched.

    Args:
        llm_client: Optional LLM client for prompt enrichment.
        output_dir: Directory where prompt files are written.
    """

    def __init__(
        self,
        llm_client: Any | None = None,
        output_dir: str = ".vibe/prompts",
    ) -> None:
        self._llm = llm_client
        self._output_dir = Path(output_dir)

    # ── Public API ────────────────────────────────────────────────────────────

    def generate(
        self,
        plan: ExecutionPlan,
        context: dict[str, Any] | None = None,
    ) -> list[PromptFile]:
        """Generate prompt chain from *plan*.

        Returns an empty list when the plan does not require prompt-chain
        generation (backward compatible).
        """
        if plan.workflow_pattern != WorkflowPattern.PROMPT_CHAIN:
            return []

        ctx = context or {}
        project_name = ctx.get("project_name", Path().resolve().name)
        steps = plan.steps

        files: list[PromptFile] = []

        # Phase 0: fan-out diagnosis
        files.append(self._generate_phase_0(plan, ctx, project_name))

        # Phase 1: quick wins (independent, zero-dependency steps)
        quick_win_steps = [s for s in steps if not s.dependencies]
        if quick_win_steps:
            files.append(self._generate_phase_1(plan, ctx, quick_win_steps))

        # Phase 2-N: one prompt per remaining dependent step
        dependent_steps = [s for s in steps if s.dependencies]
        for idx, step in enumerate(dependent_steps):
            phase_num = 2 + idx
            files.append(
                self._generate_phase_n(plan, ctx, step, phase_num)
            )

        # Final phase: adversarial review
        files.append(self._generate_final_phase(plan, ctx, files))

        return files

    def write_files(
        self,
        prompt_files: list[PromptFile],
        output_dir: str | Path | None = None,
    ) -> list[Path]:
        """Write generated prompts to disk and return written paths."""
        target = Path(output_dir) if output_dir else self._output_dir
        target.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for pf in prompt_files:
            path = target / pf.filename
            path.write_text(pf.content, encoding="utf-8")
            written.append(path)
        logger.info("Wrote %d prompt files to %s", len(written), target)
        return written

    # ── Phase generators ──────────────────────────────────────────────────────

    def _generate_phase_0(
        self,
        plan: ExecutionPlan,
        _context: dict[str, Any],
        project_name: str,
    ) -> PromptFile:
        """Phase 0 — fan-out diagnosis: read everything, produce analysis."""
        steps = plan.steps
        original_query = plan.original_query

        # Collect all skill_ids and intents as "files to read"
        skill_refs = []
        for s in steps:
            skill_refs.append(f"- `{s.skill_id}` — {s.intent or s.input_query[:60]}")

        # Build a synthetic "required files" list from step skill_ids
        required = list({s.skill_id for s in steps})

        prerequisites = [
            "项目已在本地可用",
            f"检测到 {len(steps)} 个执行步骤，涉及 {len(required)} 个技能域",
        ]

        content = (
            f"# {project_name} — Phase 0：全局扇出诊断\n\n"
            f"## 前置条件\n"
            + "\n".join(f"- [x] {p}" for p in prerequisites)
            + "\n\n"
            f"## 你的任务\n"
            f"全面理解当前任务的改造范围，识别所有改造点。\n\n"
            f"### 原始需求\n> {original_query}\n\n"
            f"### Step 1：阅读核心文件来理解项目架构\n"
            f"阅读以下技能/模块的文档：\n"
            + "\n".join(skill_refs)
            + "\n\n"
            "### Step 2：识别核心问题\n"
            "请找出以下关键问题的答案：\n"
            "1. 当前各模块的职责边界是什么？\n"
            "2. 需要修改哪些模块？\n"
            "3. 需要新建哪些模块？\n"
            "4. 模块间的依赖关系是什么？\n\n"
            "### Step 3：输出分析报告\n"
            "按照以下格式输出：\n\n"
            "```markdown\n"
            "# 扇出诊断报告\n\n"
            "## P0（必须修复 — 核心能力缺失）\n"
            "1. [问题描述] — [涉及文件] — [改造思路]\n\n"
            "## P1（重要改进 — 体验提升）\n"
            "1. ...\n\n"
            "## P2（锦上添花 — 可后续优化）\n"
            "1. ...\n\n"
            "## 文件依赖图\n"
            "（用文字描述模块间的依赖关系）\n"
            "```\n"
            + _ROUTING_HINT
        )

        return PromptFile(
            phase=0,
            name="fan-out-diagnosis",
            filename="phase-0-fan-out-diagnosis.md",
            content=content,
            prerequisites=prerequisites,
            required_files=required,
            verification_checklist=[
                "所有 P0 问题已识别并列出涉及文件",
                "文件依赖关系已描述",
                "分析报告格式符合要求",
            ],
        )

    def _generate_phase_1(
        self,
        _plan: ExecutionPlan,
        _context: dict[str, Any],
        quick_win_steps: list[ExecutionStep],
    ) -> PromptFile:
        """Phase 1 — quick wins: independent, zero-dependency changes."""
        step_items = []
        for s in quick_win_steps:
            step_items.append(
                f"1. **{s.intent or s.skill_id}** — `{s.skill_id}`\n"
                f"   任务：{s.input_query}\n"
                f"   输出变量：`{s.output_as}`"
            )

        prerequisites = [
            "Phase 0 扇出诊断报告已完成",
            f"已识别 {len(quick_win_steps)} 个独立可执行的改动点",
        ]

        content = (
            "# Quick Wins — Phase 1\n\n"
            "## 前置条件\n"
            + "\n".join(f"- [ ] {p}" for p in prerequisites)
            + "\n\n"
            "## 改动列表\n"
            + "\n".join(step_items)
            + "\n\n"
            "## 实施要求\n"
            "1. 每个改动必须独立、原子化\n"
            "2. 不引入新的依赖\n"
            "3. 每个改动后运行相关测试验证\n\n"
            "## 验证 Checklist\n"
            "- [ ] 所有改动已实施\n"
            "- [ ] 现有测试全部通过\n"
            "- [ ] 无新增 lint 错误\n"
            + _ROUTING_HINT
        )

        return PromptFile(
            phase=1,
            name="quick-wins",
            filename="phase-1-quick-wins.md",
            content=content,
            prerequisites=prerequisites,
            required_files=[s.skill_id for s in quick_win_steps],
            verification_checklist=[
                "所有 quick-win 改动已实施",
                "现有测试通过",
                "无新增 lint 错误",
            ],
        )

    def _generate_phase_n(
        self,
        plan: ExecutionPlan,
        _context: dict[str, Any],
        step: ExecutionStep,
        phase_num: int,
    ) -> PromptFile:
        """Phase 2..N — core rewrites: one prompt per dependent step."""
        dep_names = []
        for dep_id in step.dependencies:
            dep_step = next(
                (s for s in plan.steps if s.step_id == dep_id), None
            )
            if dep_step:
                dep_names.append(
                    f"- Phase {dep_step.step_number}: {dep_step.intent} (`{dep_step.skill_id}`)"
                )

        prerequisites = [
            "Phase 0 诊断报告已完成",
            "Phase 1 Quick Wins 已实施（如有）",
        ]
        if dep_names:
            prerequisites.append("以下前置步骤已完成：\n" + "\n".join(dep_names))

        slug = step.intent[:40].lower().replace(" ", "-") if step.intent else step.skill_id.replace("/", "-")
        name = slug

        content = (
            f"# Phase {phase_num}：{step.intent or step.skill_id}\n\n"
            f"## 前置条件\n"
            + "\n".join(f"- [ ] {p}" for p in prerequisites)
            + "\n\n"
            f"## 你必须先阅读的当前文件\n"
            f"- 技能 `{step.skill_id}` 的 SKILL.md\n"
            + ("\n".join(f"- {d}" for d in dep_names) + "\n" if dep_names else "")
            + "\n"
            f"## 需求\n\n"
            f"### 任务描述\n{step.input_query}\n\n"
            f"### 目标技能\n`{step.skill_id}`\n\n"
            f"### 输出变量\n`{step.output_as}`\n\n"
            f"## 关键实现要点\n"
            f"| 要点 | 实现方式 |\n"
            f"|------|----------|\n"
            f"| 接口兼容 | 不改变现有函数签名，通过新增字段扩展 |\n"
            f"| 向后兼容 | 默认值与现有行为一致 |\n"
            f"| 错误处理 | 遵循项目现有的错误处理模式 |\n\n"
            f"## 验证 Checklist\n"
            f"- [ ] 实现符合需求描述\n"
            f"- [ ] 现有测试不因新增代码而失败\n"
            f"- [ ] 新增逻辑有对应的测试覆盖\n"
            + _ROUTING_HINT
        )

        return PromptFile(
            phase=phase_num,
            name=name,
            filename=f"phase-{phase_num}-{name}.md",
            content=content,
            prerequisites=prerequisites,
            required_files=[step.skill_id],
            verification_checklist=[
                f"步骤 {phase_num} 实现符合需求",
                "现有测试通过",
                "新增测试覆盖",
            ],
        )

    def _generate_final_phase(
        self,
        _plan: ExecutionPlan,
        _context: dict[str, Any],
        previous_files: list[PromptFile],
    ) -> PromptFile:
        """Final phase — adversarial review of all changes."""
        all_required = sorted({f for pf in previous_files for f in pf.required_files})
        all_checklist = []
        for pf in previous_files:
            for item in pf.verification_checklist:
                all_checklist.append(f"- [ ] [{pf.filename}] {item}")

        file_table_rows = []
        for pf in previous_files:
            file_table_rows.append(f"| {pf.filename} | Phase {pf.phase} | {len(pf.verification_checklist)} 项 |")

        content = (
            "# Final Phase：对抗式审查\n\n"
            "## 前置条件\n"
            "- [ ] 所有 Phase 0-N 的改动已实施\n"
            "- [ ] 所有中间验证 checklist 已通过\n\n"
            "## 全量文件清单验证\n\n"
            "| 文件 | 阶段 | 验证项数 |\n"
            "|------|------|----------|\n"
            + "\n".join(file_table_rows)
            + "\n\n"
            "## 安全审查\n"
            "- [ ] 无命令注入风险（不拼接用户输入到 shell 命令）\n"
            "- [ ] 无路径遍历风险（已验证所有路径参数）\n"
            "- [ ] 无子进程权限泄露（子进程不继承多余权限）\n"
            "- [ ] 无 DoS 风险（循环/递归有边界限制）\n\n"
            "## 编译验证\n"
            "- [ ] `uv run pytest tests/` 全部通过\n"
            "- [ ] 无 import 错误\n"
            "- [ ] 无类型错误（如使用 type checker）\n\n"
            "## 功能验证清单\n"
            + "\n".join(all_checklist)
            + "\n\n"
            "## 输出\n"
            "确认所有验证项通过后，输出最终完成报告。\n"
            + _ROUTING_HINT
        )

        return PromptFile(
            phase=-1,
            name="adversarial-review",
            filename="phase-final-adversarial-review.md",
            content=content,
            prerequisites=[
                "所有 Phase 0-N 改动已实施",
                "所有中间验证通过",
            ],
            required_files=all_required,
            verification_checklist=[
                "安全审查通过",
                "编译验证通过",
                "功能验证清单全部通过",
            ],
        )
