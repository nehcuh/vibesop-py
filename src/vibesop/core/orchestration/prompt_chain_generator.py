"""PromptChainGenerator — converts ExecutionPlan into structured prompt files.

Generates a sequence of phase-based prompt files (Phase 0 → Phase 1 → … → Final)
that guide Claude Code through multi-agent, multi-stage workflows. Each prompt
file is a self-contained markdown document with prerequisites, step-by-step
instructions, verification checklists, completion markers, and routing hints.

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

# ── Key-point generation rules ────────────────────────────────────────────────

_KEY_POINTS_BY_DOMAIN: dict[str, list[tuple[str, str]]] = {
    "security": [
        ("输入验证", "所有外部输入必须经过清洗和校验"),
        ("最小权限", "子进程和文件访问按最小权限原则"),
        ("审计日志", "敏感操作必须记录审计日志"),
    ],
    "architecture": [
        ("接口契约", "明确定义模块间接口，优先使用 Protocol/ABC"),
        ("依赖方向", "依赖指向核心层（core 不依赖 cli），禁止循环依赖"),
        ("错误隔离", "模块内错误不泄漏到外部，使用自定义异常类型"),
    ],
    "refactor": [
        ("行为保持", "重构前后功能行为不变，测试覆盖所有路径"),
        ("渐进替换", "大重构分步进行，每步可独立验证"),
        ("删除旧代码", "旧代码标记 deprecated 后在确认无引用后删除"),
    ],
    "default": [
        ("接口兼容", "不改变现有函数签名，通过新增字段扩展"),
        ("向后兼容", "默认值与现有行为一致"),
        ("错误处理", "遵循项目现有的错误处理模式"),
    ],
}

# ── Checklist keyword rules ───────────────────────────────────────────────────

_CHECKLIST_KEYWORDS: dict[str, str] = {
    "安全": "无新增安全漏洞，敏感信息不泄漏",
    "性能": "性能不退化，无 N+1 查询",
    "测试": "测试覆盖率达到目标要求",
    "重构": "重构前后功能行为一致，现有测试全部通过",
    "文档": "文档与代码实现一致，无过时内容",
    "兼容": "向后兼容，旧 API 标记 deprecated",
    "评审": "所有发现均有证据支持，无主观判断",
    "配置": "配置项有默认值，配置损坏时有兜底行为",
}


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
        default_factory=list,
        description="真实文件路径，如 src/vibesop/core/router.py",
    )
    verification_checklist: list[str] = Field(
        default_factory=list, description="Items to verify before proceeding"
    )

    # Phase 7.0 enrichment fields
    output_artifacts: list[str] = Field(
        default_factory=list,
        description="本 Phase 产出的文件路径或变量名",
    )
    downstream_phases: list[int] = Field(
        default_factory=list,
        description="依赖本 Phase 的后续 Phase 编号",
    )
    risk_level: str = Field(
        default="low",
        description="风险等级: low / medium / high",
    )
    rollback_strategy: str = Field(
        default="",
        description="如果本 Phase 失败，如何回滚",
    )
    estimated_file_changes: list[str] = Field(
        default_factory=list,
        description="预计会修改的源文件路径列表",
    )
    completion_marker: str = Field(
        default="",
        description="Phase 完成后创建的标记文件路径",
    )


# ── Generator ────────────────────────────────────────────────────────────────


class PromptChainGenerator:
    """Generate Claude Code Prompt Chain from an ExecutionPlan.

    Only activates when the plan's ``workflow_pattern`` is
    ``PROMPT_CHAIN`` (i.e. ``complexity_level == "multi_agent"``).
    For all other plans ``generate()`` returns an empty list so that the
    existing execution paths remain untouched.

    Args:
        llm_client: Optional LLM client for prompt enrichment (reserved).
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

        # Phase 0: fan-out diagnosis (always generated)
        files.append(self._generate_phase_0(plan, ctx, project_name))

        # Phase 1: quick wins only (step_type == "quick_win")
        quick_win_steps = [s for s in steps if s.step_type == "quick_win"]
        has_phase_1 = bool(quick_win_steps)
        if has_phase_1:
            files.append(self._generate_phase_1(plan, ctx, quick_win_steps))

        # Phase 2..N: all remaining steps
        remaining = [s for s in steps if s.step_type != "quick_win"]
        base_phase = 2 if has_phase_1 else 1

        # Build step_id → phase_num mapping for dependency resolution
        step_phase_map: dict[str, int] = {}
        for idx, step in enumerate(remaining):
            step_phase_map[step.step_id] = base_phase + idx

        for idx, step in enumerate(remaining):
            phase_num = base_phase + idx
            files.append(
                self._generate_phase_n(plan, ctx, step, phase_num, step_phase_map)
            )

        # Final phase: adversarial review
        files.append(self._generate_final_phase(plan, ctx, files))

        # Populate downstream_phases
        for pf in files:
            if pf.phase >= 0:
                pf.downstream_phases = [
                    f.phase for f in files
                    if f.phase > pf.phase and f.phase > 0
                ]

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

    # ── Dynamic content generators ────────────────────────────────────────────

    @staticmethod
    def _generate_key_points(step: ExecutionStep) -> str:
        """Generate key implementation points based on step attributes."""
        skill_id = (step.skill_id or "").lower()
        intent = (step.intent or "").lower()
        text = f"{skill_id} {intent}"

        for domain, keywords in [
            ("security", ["security", "安全", "漏洞", "vulnerability"]),
            ("architecture", ["architecture", "架构", "design", "设计", "core"]),
            ("refactor", ["refactor", "重构", "restructure", "rewrite", "重写"]),
        ]:
            if any(kw in text for kw in keywords):
                points = _KEY_POINTS_BY_DOMAIN[domain]
                break
        else:
            points = _KEY_POINTS_BY_DOMAIN["default"]

        lines = ["| 要点 | 实现方式 |", "|------|----------|"]
        for name, desc in points:
            lines.append(f"| {name} | {desc} |")
        return "\n".join(lines)

    @staticmethod
    def _generate_checklist(step: ExecutionStep, phase_num: int) -> list[str]:
        """Generate verification checklist based on step attributes."""
        checklist = [f"Phase {phase_num} 的实现符合需求描述"]
        intent = step.intent or ""
        query = step.input_query or ""

        for keyword, check in _CHECKLIST_KEYWORDS.items():
            if keyword in intent or keyword in query:
                checklist.append(check)

        checklist.append("现有测试全部通过")
        return checklist

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

        # Collect real file paths from step.source_files
        all_source_files: list[str] = []
        for s in steps:
            all_source_files.extend(s.source_files)
        required_files = sorted(set(all_source_files))

        # Skill references for readability
        skill_refs = [
            f"- **{s.skill_id}** — {s.intent or s.input_query[:60]}"
            for s in steps
        ]

        # File path details
        file_refs = (
            [f"- `{f}`" for f in required_files]
            if required_files
            else ["- (无已知文件路径，请根据 skill_id 自行定位)"]
        )

        prerequisites = [
            "项目已在本地可用",
            f"检测到 {len(steps)} 个执行步骤，涉及 {len({s.skill_id for s in steps})} 个技能域",
        ]

        completion_marker = ".vibe/prompts/.phase-0-done"

        content = (
            f"# {project_name} — Phase 0：全局扇出诊断\n\n"
            "## 前置条件\n"
            + "\n".join(f"- [ ] {p}" for p in prerequisites)
            + "\n\n"
            "## 你的任务\n"
            "全面理解当前任务的改造范围，识别所有改造点。\n\n"
            f"### 原始需求\n> {original_query}\n\n"
            "### Step 1：阅读核心文件来理解项目架构\n"
            "以下是与本任务相关的技能/模块：\n"
            + "\n".join(skill_refs)
            + "\n\n#### 具体文件路径\n"
            + "\n".join(file_refs)
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
            "```\n\n"
            "---\n\n"
            "## 完成条件\n"
            "执行完本 Phase 后，创建标记文件：\n"
            "```bash\n"
            f'echo "phase-0 completed at $(date)" > {completion_marker}\n'
            "```\n"
            + _ROUTING_HINT
        )

        return PromptFile(
            phase=0,
            name="fan-out-diagnosis",
            filename="phase-0-fan-out-diagnosis.md",
            content=content,
            prerequisites=prerequisites,
            required_files=required_files,
            verification_checklist=[
                "所有 P0 问题已识别并列出涉及文件",
                "文件依赖关系已描述",
                "分析报告格式符合要求",
            ],
            output_artifacts=["diagnosis_report.md"],
            risk_level="low",
            completion_marker=completion_marker,
        )

    def _generate_phase_1(
        self,
        _plan: ExecutionPlan,
        _context: dict[str, Any],
        quick_win_steps: list[ExecutionStep],
    ) -> PromptFile:
        """Phase 1 — quick wins: small, independent changes."""
        step_items = []
        for s in quick_win_steps:
            step_items.append(
                f"1. **{s.intent or s.skill_id}** — `{s.skill_id}`\n"
                f"   任务：{s.input_query}\n"
                f"   输出变量：`{s.output_as}`"
            )

        # Collect source files from steps
        all_source_files: list[str] = []
        for s in quick_win_steps:
            all_source_files.extend(s.source_files)
        source_files = sorted(set(all_source_files))

        prerequisites = [
            "Phase 0 扇出诊断报告已完成",
            f"已识别 {len(quick_win_steps)} 个可快速执行的独立改动点",
            "检查 Phase 0 完成标记：`ls .vibe/prompts/.phase-0-done`",
        ]

        completion_marker = ".vibe/prompts/.phase-1-done"

        content = (
            "# Quick Wins — Phase 1\n\n"
            "## 前置条件\n"
            + "\n".join(f"- [ ] {p}" for p in prerequisites)
            + "\n\n"
            "## 改动列表\n"
            + "\n".join(step_items)
            + "\n\n"
        )
        if source_files:
            content += (
                "## 涉及文件\n"
                + "\n".join(f"- `{f}`" for f in source_files)
                + "\n\n"
            )
        content += (
            "## 实施要求\n"
            "1. 每个改动必须独立、原子化\n"
            "2. 不引入新的依赖\n"
            "3. 每个改动后运行相关测试验证\n\n"
            "## 验证 Checklist\n"
            "- [ ] 所有改动已实施\n"
            "- [ ] 现有测试全部通过\n"
            "- [ ] 无新增 lint 错误\n\n"
            "---\n\n"
            "## 完成条件\n"
            "执行完本 Phase 后，创建标记文件：\n"
            "```bash\n"
            f'echo "phase-1 completed at $(date)" > {completion_marker}\n'
            "```\n"
            + _ROUTING_HINT
        )

        return PromptFile(
            phase=1,
            name="quick-wins",
            filename="phase-1-quick-wins.md",
            content=content,
            prerequisites=prerequisites,
            required_files=source_files,
            verification_checklist=[
                "所有 quick-win 改动已实施",
                "现有测试通过",
                "无新增 lint 错误",
            ],
            output_artifacts=[f"step_{s.step_number}_result" for s in quick_win_steps],
            risk_level="low",
            rollback_strategy="git revert",
            estimated_file_changes=source_files,
            completion_marker=completion_marker,
        )

    def _generate_phase_n(
        self,
        plan: ExecutionPlan,
        _context: dict[str, Any],
        step: ExecutionStep,
        phase_num: int,
        step_phase_map: dict[str, int] | None = None,
    ) -> PromptFile:
        """Phase 2..N — core rewrites: one prompt per remaining step."""
        # Build dependency prerequisites with phase numbers
        dep_lines: list[str] = []
        for dep_id in step.dependencies:
            dep_step = next(
                (s for s in plan.steps if s.step_id == dep_id), None
            )
            if dep_step:
                dep_phase = (step_phase_map or {}).get(dep_id, dep_step.step_number)
                marker = f".vibe/prompts/.phase-{dep_phase}-done"
                dep_lines.append(
                    f"- Phase {dep_phase}: {dep_step.intent} "
                    f"(`ls {marker}`)"
                )

        prerequisites: list[str] = ["Phase 0 诊断报告已完成"]
        if dep_lines:
            prerequisites.append("以下前置步骤已完成：\n" + "\n".join(dep_lines))

        # Resolve real file paths
        source_files = step.source_files
        file_section = ""
        if source_files:
            file_section = (
                "## 你必须先阅读的当前文件\n"
                + "\n".join(f"- `{f}`" for f in source_files)
                + "\n\n"
            )

        # Generate dynamic key points and checklist
        key_points = self._generate_key_points(step)
        checklist = self._generate_checklist(step, phase_num)

        # ASCII-safe slug for filename
        raw_slug = (step.intent[:40] if step.intent else step.skill_id).lower().replace(" ", "-").replace("/", "-")
        ascii_slug = "".join(c if c.isalnum() or c in "-_" else "" for c in raw_slug)
        if not ascii_slug:
            ascii_slug = f"step-{phase_num}"
        name = ascii_slug

        completion_marker = f".vibe/prompts/.phase-{phase_num}-done"

        content = (
            f"# Phase {phase_num}：{step.intent or step.skill_id}\n\n"
            "## 前置条件\n"
            + "\n".join(f"- [ ] {p}" for p in prerequisites)
            + "\n\n"
            + file_section
            + f"## 需求\n\n"
            f"### 任务描述\n{step.input_query}\n\n"
            f"### 目标技能\n`{step.skill_id}`\n\n"
            f"### 输出变量\n`{step.output_as}`\n\n"
            f"## 关键实现要点\n{key_points}\n\n"
            "## 验证 Checklist\n"
            + "\n".join(f"- [ ] {c}" for c in checklist)
            + "\n\n"
            "---\n\n"
            "## 完成条件\n"
            "执行完本 Phase 后，创建标记文件：\n"
            "```bash\n"
            f'echo "phase-{phase_num} completed at $(date)" > {completion_marker}\n'
            "```\n"
            + _ROUTING_HINT
        )

        # Determine risk level from step
        risk = step.estimated_risk or "medium"
        rollback = "git revert" if risk in ("medium", "high") else ""

        return PromptFile(
            phase=phase_num,
            name=name,
            filename=f"phase-{phase_num}-{name}.md",
            content=content,
            prerequisites=prerequisites,
            required_files=source_files,
            verification_checklist=checklist,
            output_artifacts=[step.output_as],
            risk_level=risk,
            rollback_strategy=rollback,
            estimated_file_changes=source_files,
            completion_marker=completion_marker,
        )

    def _generate_final_phase(
        self,
        _plan: ExecutionPlan,
        _context: dict[str, Any],
        previous_files: list[PromptFile],
    ) -> PromptFile:
        """Final phase — adversarial review of all changes."""
        all_required = sorted({f for pf in previous_files for f in pf.required_files})
        all_checklist: list[str] = []
        for pf in previous_files:
            if pf.phase < 0:
                continue
            for item in pf.verification_checklist:
                all_checklist.append(f"- [ ] [{pf.filename}] {item}")

        file_table_rows = []
        for pf in previous_files:
            if pf.phase < 0:
                continue
            file_table_rows.append(
                f"| {pf.filename} | Phase {pf.phase} | {len(pf.verification_checklist)} 项 |"
            )

        # Cross-phase verification
        phase_numbers = [pf.phase for pf in previous_files if pf.phase >= 0]
        cross_phase_checks: list[str] = []
        if len(phase_numbers) > 1:
            cross_phase_checks = [
                "- [ ] 各 Phase 的输出被后续 Phase 正确消费，数据流无断裂",
                "- [ ] 多个 Phase 对同一文件的修改无冲突（git diff 无矛盾）",
                "- [ ] 所有 Phase 的 completion_marker 文件已创建",
            ]

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
        )

        if cross_phase_checks:
            content += (
                "## 跨维度交叉验证\n"
                + "\n".join(cross_phase_checks)
                + "\n\n"
            )

        content += (
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
            risk_level="low",
        )
